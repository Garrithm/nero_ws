import math
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence


def _ensure_pyagxarm_importable() -> None:
    try:
        import pyAgxArm  # noqa: F401
        return
    except ImportError:
        workspace_root = Path(__file__).resolve().parents[2]
        repo_candidate = workspace_root / "pyAgxArm"
        if repo_candidate.exists():
            sys.path.insert(0, str(repo_candidate))


_ensure_pyagxarm_importable()

from pyAgxArm import AgxArmFactory, ArmModel, NeroFW, create_agx_arm_config  # noqa: E402


PoseCallback = Callable[["PoseMessage"], None]


@dataclass
class PoseMessage:
    frame_id: str
    pose: List[float]
    timestamp: float


@dataclass
class CommandPoseDebug:
    tcp_pose: List[float]
    flange_pose: List[float]
    motion_mode: str
    timestamp: float


class NeroPoseSDKBridge:
    def __init__(
        self,
        interface: str = "socketcan",
        channel: str = "nero_can",
        firmware_version: str = "default",
        tcp_offset: Optional[Sequence[float]] = None,
        motion_mode: str = "l",
        speed_percent: int = 15,
        publish_rate_hz: float = 20.0,
        auto_enable: bool = True,
        command_timeout_sec: float = 10.0,
        enable_timeout_sec: float = 5.0,
        feedback_timeout_sec: float = 3.0,
        normal_mode_settle_sec: float = 0.2,
        command_repeats: int = 3,
        command_repeat_interval_sec: float = 0.08,
        refresh_normal_mode_before_pose_command: bool = False,
    ) -> None:
        self.interface = interface
        self.channel = channel
        self.firmware_version = self._resolve_firmware_version(firmware_version)
        self.tcp_offset = self._normalize_pose6(tcp_offset or [0.0] * 6, "tcp_offset")
        self.motion_mode = motion_mode.lower()
        self.speed_percent = int(speed_percent)
        self.publish_rate_hz = float(publish_rate_hz)
        self.auto_enable = bool(auto_enable)
        self.command_timeout_sec = float(command_timeout_sec)
        self.enable_timeout_sec = float(enable_timeout_sec)
        self.feedback_timeout_sec = float(feedback_timeout_sec)
        self.normal_mode_settle_sec = float(normal_mode_settle_sec)
        self.command_repeats = int(command_repeats)
        self.command_repeat_interval_sec = float(command_repeat_interval_sec)
        self.refresh_normal_mode_before_pose_command = bool(refresh_normal_mode_before_pose_command)

        if self.motion_mode not in ("l", "p"):
            raise ValueError("motion_mode must be 'l' or 'p'")
        if not 1 <= self.speed_percent <= 100:
            raise ValueError("speed_percent must be in [1, 100]")
        if self.publish_rate_hz <= 0.0:
            raise ValueError("publish_rate_hz must be > 0")
        if self.command_timeout_sec <= 0.0:
            raise ValueError("command_timeout_sec must be > 0")
        if self.enable_timeout_sec <= 0.0:
            raise ValueError("enable_timeout_sec must be > 0")
        if self.feedback_timeout_sec <= 0.0:
            raise ValueError("feedback_timeout_sec must be > 0")
        if self.normal_mode_settle_sec < 0.0:
            raise ValueError("normal_mode_settle_sec must be >= 0")
        if self.command_repeats <= 0:
            raise ValueError("command_repeats must be > 0")
        if self.command_repeat_interval_sec < 0.0:
            raise ValueError("command_repeat_interval_sec must be >= 0")

        self.pose_queue: "queue.Queue[PoseMessage]" = queue.Queue(maxsize=1)
        self.target_queue: "queue.Queue[List[float]]" = queue.Queue()

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._publisher_thread: Optional[threading.Thread] = None
        self._target_thread: Optional[threading.Thread] = None
        self._pose_callback: Optional[PoseCallback] = None
        self._robot = None
        self._latest_pose: Optional[PoseMessage] = None
        self._last_command_debug: Optional[CommandPoseDebug] = None

    def connect(self) -> None:
        cfg = create_agx_arm_config(
            robot=ArmModel.NERO,
            firmeware_version=self.firmware_version,
            interface=self.interface,
            channel=self.channel,
        )
        robot = AgxArmFactory.create_arm(cfg)
        try:
            robot.connect()
            robot.set_tcp_offset(self.tcp_offset)

            self._robot = robot
            if self.auto_enable and not self._wait_until_enabled(self.enable_timeout_sec):
                raise RuntimeError("failed to enable robot")

            self._set_normal_mode_and_settle()
            if not self._wait_feedback_ready(self.feedback_timeout_sec):
                raise RuntimeError("failed to receive joint feedback after set_normal_mode")

            robot.set_speed_percent(self.speed_percent)
        except Exception:
            try:
                robot.disconnect()
            finally:
                self._robot = None
            raise

    def start(self, pose_callback: Optional[PoseCallback] = None) -> None:
        if self._robot is None:
            self.connect()

        self._pose_callback = pose_callback
        self._stop_event.clear()

        self._publisher_thread = threading.Thread(
            target=self._publisher_loop,
            name="nero_pose_publisher",
            daemon=True,
        )
        self._target_thread = threading.Thread(
            target=self._target_loop,
            name="nero_target_consumer",
            daemon=True,
        )
        self._publisher_thread.start()
        self._target_thread.start()

    def stop(self, disable: bool = False) -> None:
        self._stop_event.set()

        for thread in (self._publisher_thread, self._target_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)

        if self._robot is not None:
            with self._lock:
                try:
                    if disable:
                        self._robot.disable()
                finally:
                    self._robot.disconnect()
            self._robot = None

    def get_latest_pose(self) -> Optional[PoseMessage]:
        return self._latest_pose

    def get_current_tcp_pose(self) -> Optional[PoseMessage]:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        with self._lock:
            pose_msg = self._robot.get_tcp_pose()

        if pose_msg is None:
            return None

        message = PoseMessage(
            frame_id="base_link",
            pose=[float(v) for v in pose_msg.msg],
            timestamp=float(pose_msg.timestamp),
        )
        self._latest_pose = message
        return message

    def preview_target_command(self, pose: Sequence[float]) -> CommandPoseDebug:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        target_tcp_pose = self._normalize_pose6(pose, "target_pose")
        with self._lock:
            target_flange_pose = self._robot.get_tcp2flange_pose(list(target_tcp_pose))
        return CommandPoseDebug(
            tcp_pose=list(target_tcp_pose),
            flange_pose=[float(value) for value in target_flange_pose],
            motion_mode=self.motion_mode,
            timestamp=time.time(),
        )

    def get_last_command_debug(self) -> Optional[CommandPoseDebug]:
        return self._last_command_debug

    def submit_target_pose(self, pose: Sequence[float]) -> None:
        target_pose = self._normalize_pose6(pose, "target_pose")
        self.target_queue.put(target_pose)

    def move_to_target_pose(
        self,
        pose: Sequence[float],
        wait: bool = True,
        timeout: Optional[float] = None,
    ) -> bool:
        target_pose = self._normalize_pose6(pose, "target_pose")
        self._execute_target_pose(target_pose)
        if not wait:
            return True
        return self.wait_motion_done(timeout=timeout)

    def move_to_joint_positions(
        self,
        joints: Sequence[float],
        wait: bool = True,
        timeout: Optional[float] = None,
        degrees: bool = False,
    ) -> bool:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        target_joints = [float(value) for value in joints]
        joint_nums = int(getattr(self._robot, "joint_nums", len(target_joints)))
        if len(target_joints) != joint_nums:
            raise ValueError(f"joint target must contain {joint_nums} values")

        if degrees:
            target_joints = [math.radians(value) for value in target_joints]

        with self._lock:
            self._robot.move_j(target_joints)

        if not wait:
            return True
        return self.wait_motion_done(timeout=timeout)

    def wait_motion_done(self, timeout: Optional[float] = None) -> bool:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        deadline = time.monotonic() + (timeout or self.command_timeout_sec)
        time.sleep(0.3)
        while time.monotonic() < deadline:
            with self._lock:
                status = self._robot.get_arm_status()
            if status is not None and getattr(status.msg, "motion_status", None) == 0:
                return True
            time.sleep(0.1)
        return False

    def _publisher_loop(self) -> None:
        period = 1.0 / self.publish_rate_hz
        while not self._stop_event.is_set():
            try:
                pose = self.get_current_tcp_pose()
                if pose is not None:
                    self._replace_latest_queue_item(pose)
                    if self._pose_callback is not None:
                        self._pose_callback(pose)
            except Exception:
                pass
            time.sleep(period)

    def _target_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                target_pose = self.target_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                self._execute_target_pose(target_pose)
            finally:
                self.target_queue.task_done()

    def _execute_target_pose(self, target_tcp_pose: Sequence[float]) -> None:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        with self._lock:
            if self.refresh_normal_mode_before_pose_command:
                self._robot.set_normal_mode()
                if self.normal_mode_settle_sec > 0.0:
                    time.sleep(self.normal_mode_settle_sec)
            normalized_target_tcp = self._normalize_pose6(target_tcp_pose, "target_pose")
            target_flange_pose = self._robot.get_tcp2flange_pose(list(normalized_target_tcp))
            self._last_command_debug = CommandPoseDebug(
                tcp_pose=list(normalized_target_tcp),
                flange_pose=[float(value) for value in target_flange_pose],
                motion_mode=self.motion_mode,
                timestamp=time.time(),
            )
            for attempt in range(self.command_repeats):
                if self.motion_mode == "l":
                    self._robot.move_l(target_flange_pose)
                else:
                    self._robot.move_p(target_flange_pose)
                if attempt + 1 < self.command_repeats and self.command_repeat_interval_sec > 0.0:
                    time.sleep(self.command_repeat_interval_sec)

    def _replace_latest_queue_item(self, pose: PoseMessage) -> None:
        try:
            self.pose_queue.get_nowait()
        except queue.Empty:
            pass
        self.pose_queue.put_nowait(pose)

    def _wait_feedback_ready(self, timeout: float) -> bool:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                joint_angles = self._robot.get_joint_angles()
            if joint_angles is not None and getattr(joint_angles, "hz", 0) > 0:
                return True
            time.sleep(0.05)
        return False

    def _wait_until_enabled(self, timeout: float) -> bool:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._robot.enable():
                    return True
                self._robot.set_normal_mode()
            time.sleep(0.05)
        return False

    def _set_normal_mode_and_settle(self) -> None:
        if self._robot is None:
            raise RuntimeError("bridge is not connected")

        with self._lock:
            self._robot.set_normal_mode()
        if self.normal_mode_settle_sec > 0.0:
            time.sleep(self.normal_mode_settle_sec)

    def _resolve_firmware_version(self, firmware_version: str) -> str:
        version = firmware_version.strip().lower()
        if version == "default":
            return NeroFW.DEFAULT
        if version == "v111":
            return NeroFW.V111
        raise ValueError("firmware_version must be 'default' or 'v111'")

    def _normalize_pose6(self, values: Sequence[float], name: str) -> List[float]:
        pose = [float(v) for v in values]
        if len(pose) != 6:
            raise ValueError(f"{name} must contain 6 values")
        return pose
