import argparse
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional, Sequence

from pose_bridge import NeroPoseSDKBridge
from xvisio_wireless import XvisioPoseMessage, XvisioWirelessController

from pyAgxArm.utiles.tf import T16_to_pose6, inv_T16, matmul16_to, pose6_to_T16


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pure CLI demo for Nero arm + Xvisio controller follow")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel", default="nero_can")
    parser.add_argument("--firmware-version", default="default", choices=["default", "v111"])
    parser.add_argument("--motion-mode", default="p", choices=["l", "p"])
    parser.add_argument("--speed-percent", type=int, default=15)
    parser.add_argument("--publish-rate-hz", type=float, default=100.0)
    parser.add_argument("--enable-timeout-sec", type=float, default=5.0)
    parser.add_argument("--feedback-timeout-sec", type=float, default=3.0)
    parser.add_argument(
        "--initial-joints-deg",
        type=float,
        nargs=7,
        metavar=("J1", "J2", "J3", "J4", "J5", "J6", "J7"),
        # default=[0.0, -90.0, 0.0, 123.0, 0.0, 0.0, 33.0],
        default=[0.0, -10.0, 0.0, 123.0, 0.0, 0.0, -20.0],
    )
    parser.add_argument("--initial-joint-timeout-sec", type=float, default=20.0)
    parser.add_argument(
        "--tcp-offset",
        type=float,
        nargs=6,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        default=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    )
    parser.add_argument("--xvisio-lib", default=None, help="path to libwirelessController.so")
    parser.add_argument("--controller-side", default="right", choices=["left", "right"])
    parser.add_argument("--controller-poll-hz", type=float, default=500.0)
    parser.add_argument("--controller-print-interval-sec", type=float, default=2.0)
    parser.add_argument("--device-info-interval-sec", type=float, default=5.0)
    parser.add_argument("--control-rate-hz", type=float, default=100.0)
    parser.add_argument("--start-key-value", type=int, default=16)
    parser.add_argument("--monitor-only", action="store_true")
    parser.add_argument("--interactive-target", action="store_true")
    # Kept for compatibility: auto-start is now the default behavior.
    parser.add_argument("--auto-start", action="store_true")
    parser.add_argument("--wait-for-key", action="store_true")
    # Kept for compatibility: orientation follow is now enabled by default.
    parser.add_argument("--follow-orientation", action="store_true")
    parser.add_argument("--position-only", action="store_true")
    parser.add_argument("--rotation-only", action="store_true")
    parser.add_argument(
        "--trigger-test-offset",
        type=float,
        nargs=6,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        default=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        help="optional one-shot tcp offset applied immediately after key trigger",
    )
    parser.add_argument(
        "--position-scale",
        type=float,
        nargs=3,
        metavar=("SX", "SY", "SZ"),
        default=[1.0, 1.0, 1.0],
    )
    parser.add_argument(
        "--controller-position-axes",
        "--position-axes",
        dest="controller_position_axes",
        default="xyz",
        help="手柄位置输入轴，可选 x/y/z，支持 x、yz、x,z、none",
    )
    parser.add_argument(
        "--rotation-scale",
        type=float,
        nargs=3,
        metavar=("SROLL", "SPITCH", "SYAW"),
        default=[1.0, 1.0, 1.0],
    )
    parser.add_argument(
        "--controller-orientation-axes",
        "--orientation-axes",
        dest="controller_orientation_axes",
        default="rpy",
        help="手柄姿态输入轴，可选 r/p/y 或 roll/pitch/yaw，支持 r、py、r,y、none",
    )
    parser.add_argument(
        "--position-signs",
        type=float,
        nargs=3,
        metavar=("SIGNX", "SIGNY", "SIGNZ"),
        default=[1.0, 1.0, 1.0],
    )
    parser.add_argument(
        "--rotation-signs",
        type=float,
        nargs=3,
        metavar=("SIGNR", "SIGNP", "SIGNY"),
        default=[1.0, 1.0, 1.0],
    )
    parser.add_argument(
        "--max-position-delta",
        type=float,
        nargs=3,
        metavar=("DX", "DY", "DZ"),
        default=[0.20, 0.20, 0.20],
    )
    parser.add_argument(
        "--max-orientation-delta-deg",
        type=float,
        nargs=3,
        metavar=("DROLL", "DPITCH", "DYAW"),
        default=[45.0, 45.0, 60.0],
    )
    parser.add_argument("--position-deadband", type=float, default=0.003)
    parser.add_argument("--rotation-deadband-deg", type=float, default=2.0)
    parser.add_argument("--smoothing-alpha", type=float, default=0.18)
    parser.add_argument("--disable-on-exit", action="store_true")
    return parser


def format_robot_pose(pose) -> str:
    values = ", ".join(f"{value:+.5f}" for value in pose.pose)
    return f"[{values}] @ {pose.frame_id}"


def format_pose_values(values: Sequence[float], precision: int = 4) -> str:
    return "[" + ", ".join(f"{value:+.{precision}f}" for value in values) + "]"


def format_controller_pose(message: XvisioPoseMessage) -> str:
    position = ", ".join(f"{value:+.3f}" for value in message.position)
    quaternion = ", ".join(f"{value:+.3f}" for value in message.quaternion)
    return (
        f"position=[{position}] "
        f"quaternion=[{quaternion}] "
        f"keys=(key={message.key}, trigger={message.key_trigger}, side={message.key_side}, "
        f"rocker=({message.rocker_x}, {message.rocker_y}))"
    )


def resolve_controller_side(name: str) -> int:
    # The SDK sample in XvisioSDK/test.cpp uses `2` for the right controller.
    mapping = {
        "left": XvisioWirelessController.LEFT,
        "right": XvisioWirelessController.RIGHT,
    }
    return mapping[name]


def clamp_scalar(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def clamp_rpy(roll: float, pitch: float, yaw: float) -> list[float]:
    return [
        math.atan2(math.sin(roll), math.cos(roll)),
        max(-math.pi / 2.0, min(math.pi / 2.0, pitch)),
        math.atan2(math.sin(yaw), math.cos(yaw)),
    ]


def normalize_quaternion(quaternion: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in quaternion))
    if norm <= 1e-8:
        return [0.0, 0.0, 0.0, 1.0]
    return [value / norm for value in quaternion]


def mat3_mul(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [
        a[0] * b[0] + a[1] * b[3] + a[2] * b[6],
        a[0] * b[1] + a[1] * b[4] + a[2] * b[7],
        a[0] * b[2] + a[1] * b[5] + a[2] * b[8],
        a[3] * b[0] + a[4] * b[3] + a[5] * b[6],
        a[3] * b[1] + a[4] * b[4] + a[5] * b[7],
        a[3] * b[2] + a[4] * b[5] + a[5] * b[8],
        a[6] * b[0] + a[7] * b[3] + a[8] * b[6],
        a[6] * b[1] + a[7] * b[4] + a[8] * b[7],
        a[6] * b[2] + a[7] * b[5] + a[8] * b[8],
    ]


def mat3_transpose(matrix: Sequence[float]) -> list[float]:
    return [
        matrix[0],
        matrix[3],
        matrix[6],
        matrix[1],
        matrix[4],
        matrix[7],
        matrix[2],
        matrix[5],
        matrix[8],
    ]


def mat3_vec3_mul(matrix: Sequence[float], vector: Sequence[float]) -> list[float]:
    return [
        matrix[0] * vector[0] + matrix[1] * vector[1] + matrix[2] * vector[2],
        matrix[3] * vector[0] + matrix[4] * vector[1] + matrix[5] * vector[2],
        matrix[6] * vector[0] + matrix[7] * vector[1] + matrix[8] * vector[2],
    ]


def T16_rotation_matrix(transform: Sequence[float]) -> list[float]:
    return [
        transform[0],
        transform[1],
        transform[2],
        transform[4],
        transform[5],
        transform[6],
        transform[8],
        transform[9],
        transform[10],
    ]


def build_T16(rotation: Sequence[float], translation: Sequence[float]) -> list[float]:
    return [
        rotation[0],
        rotation[1],
        rotation[2],
        translation[0],
        rotation[3],
        rotation[4],
        rotation[5],
        translation[1],
        rotation[6],
        rotation[7],
        rotation[8],
        translation[2],
        0.0,
        0.0,
        0.0,
        1.0,
    ]


# 世界坐标下，当前约定为:
# - 基座坐标系: x 向后, y 向右, z 向上
# - TCP 坐标系: x 向上, y 向前, z 向左
# - 手柄坐标系: x 向右, y 向下, z 向前
#
# 因此手柄位置/姿态换算到基座坐标时:
#   x_base = -z_ctrl
#   y_base = +x_ctrl
#   z_base = -y_ctrl
CONTROLLER_TO_BASE_BASIS = [
    0.0,
    0.0,
    -1.0,
    1.0,
    0.0,
    0.0,
    0.0,
    -1.0,
    0.0,
]


def controller_pose_to_T16(message: XvisioPoseMessage) -> list[float]:
    qx, qy, qz, qw = normalize_quaternion(message.quaternion)
    xx = qx * qx
    yy = qy * qy
    zz = qz * qz
    xy = qx * qy
    xz = qx * qz
    yz = qy * qz
    xw = qx * qw
    yw = qy * qw
    zw = qz * qw
    controller_rotation = [
        1.0 - 2.0 * (yy + zz),
        2.0 * (xy - zw),
        2.0 * (xz + yw),
        2.0 * (xy + zw),
        1.0 - 2.0 * (xx + zz),
        2.0 * (yz - xw),
        2.0 * (xz - yw),
        2.0 * (yz + xw),
        1.0 - 2.0 * (xx + yy),
    ]
    basis = CONTROLLER_TO_BASE_BASIS
    robot_rotation = mat3_mul(
        mat3_mul(basis, controller_rotation),
        mat3_transpose(basis),
    )
    robot_position = mat3_vec3_mul(
        basis,
        [
            float(message.position[0]),
            float(message.position[1]),
            float(message.position[2]),
        ],
    )
    return [
        robot_rotation[0],
        robot_rotation[1],
        robot_rotation[2],
        robot_position[0],
        robot_rotation[3],
        robot_rotation[4],
        robot_rotation[5],
        robot_position[1],
        robot_rotation[6],
        robot_rotation[7],
        robot_rotation[8],
        robot_position[2],
        0.0,
        0.0,
        0.0,
        1.0,
    ]


@dataclass
class FollowConfig:
    control_rate_hz: float
    wait_for_key: bool
    start_key_value: int
    follow_orientation: bool
    position_axes_enabled: list[bool]
    orientation_axes_enabled: list[bool]
    position_scale: list[float]
    rotation_scale: list[float]
    position_signs: list[float]
    rotation_signs: list[float]
    max_position_delta: list[float]
    max_orientation_delta: list[float]
    position_deadband: float
    rotation_deadband: float
    smoothing_alpha: float
    trigger_test_offset: list[float]


@dataclass
class FollowComputation:
    controller_position_delta_raw: list[float]
    controller_position_offset: list[float]
    controller_rotation_delta_raw: list[float]
    controller_rotation_offset: list[float]
    target_tcp_pose: list[float]


def parse_axis_selection(raw_value: str, name: str, aliases: dict[str, int]) -> list[bool]:
    normalized = raw_value.strip().lower().replace(" ", "")
    if normalized in {"", "all"}:
        enabled = [False, False, False]
        for index in aliases.values():
            enabled[index] = True
        return enabled
    if normalized in {"none", "off"}:
        return [False, False, False]

    tokens = [token for token in normalized.replace(",", " ").split() if token]
    if not tokens:
        tokens = [normalized]

    enabled = [False, False, False]
    for token in tokens:
        if token in aliases:
            enabled[aliases[token]] = True
            continue
        if len(token) > 1 and all(char in aliases for char in token):
            for char in token:
                enabled[aliases[char]] = True
            continue
        raise ValueError(f"{name} 包含非法轴: {token}")
    return enabled


def format_enabled_axes(enabled: Sequence[bool], labels: Sequence[str]) -> str:
    selected = [label for flag, label in zip(enabled, labels) if flag]
    if not selected:
        return "none"
    return ",".join(selected)


class XvisioTcpFollower:
    def __init__(self, bridge: NeroPoseSDKBridge, config: FollowConfig) -> None:
        self._bridge = bridge
        self._config = config
        self._latest_controller_pose: Optional[XvisioPoseMessage] = None
        self._reference_controller_pose: Optional[XvisioPoseMessage] = None
        self._reference_controller_transform: Optional[list[float]] = None
        self._reference_robot_pose: Optional[list[float]] = None
        self._reference_robot_transform: Optional[list[float]] = None
        self._filtered_position_offset: list[float] = [0.0, 0.0, 0.0]
        self._filtered_rotation_offset: list[float] = [0.0, 0.0, 0.0]
        self._last_command_pose: Optional[list[float]] = None
        self._last_log_time = 0.0
        self._waiting_for_key_printed = False
        self._follow_started = False
        self._trigger_test_sent = False
        self._last_key_active = False
        self._lock = threading.Lock()

    def reset_reference(self) -> bool:
        with self._lock:
            robot_pose = self._bridge.get_current_tcp_pose()
            if robot_pose is None:
                return False
            self._latest_controller_pose = None
            self._reference_controller_pose = None
            self._reference_controller_transform = None
            self._reference_robot_pose = list(robot_pose.pose)
            self._reference_robot_transform = pose6_to_T16(list(robot_pose.pose))
            self._filtered_position_offset = [0.0, 0.0, 0.0]
            self._filtered_rotation_offset = [0.0, 0.0, 0.0]
            self._last_command_pose = None
            return True

    def handle_controller_pose(self, controller_pose: XvisioPoseMessage) -> None:
        with self._lock:
            self._latest_controller_pose = controller_pose
            key_active = is_tracking_start_key_pressed(
                controller_pose,
                self._config.start_key_value,
            )
            if key_active != self._last_key_active:
                print(
                    "手柄启动键状态变化: "
                    f"active={key_active} "
                    f"key={controller_pose.key} "
                    f"trigger={controller_pose.key_trigger} "
                    f"side={controller_pose.key_side} "
                    f"required_key={self._config.start_key_value}"
                )
                self._last_key_active = key_active

            if self._config.wait_for_key and not self._follow_started:
                if not key_active:
                    if not self._waiting_for_key_printed:
                        print(f"等待手柄启动键 key={self._config.start_key_value}，按下后开始跟随")
                        self._waiting_for_key_printed = True
                    return
                self._follow_started = True
                self._waiting_for_key_printed = False
                print(
                    "已检测到启动跟随按键: "
                    f"key={controller_pose.key} "
                    f"trigger={controller_pose.key_trigger} "
                    f"side={controller_pose.key_side} "
                    f"required_key={self._config.start_key_value}"
                )
            elif not self._config.wait_for_key and not self._follow_started:
                self._follow_started = True
                print("无需按键，已直接开始跟随")

    def step(self) -> None:
        latest_controller_pose = None
        target_pose = None
        computation = None
        now = time.monotonic()

        with self._lock:
            if not self._follow_started:
                return

            latest_controller_pose = self._latest_controller_pose
            if latest_controller_pose is None:
                return

            if self._reference_controller_pose is None:
                robot_pose = self._bridge.get_current_tcp_pose()
                if robot_pose is None:
                    return
                self._reference_controller_pose = latest_controller_pose
                self._reference_controller_transform = controller_pose_to_T16(latest_controller_pose)
                self._reference_robot_pose = list(robot_pose.pose)
                self._reference_robot_transform = pose6_to_T16(list(robot_pose.pose))
                self._filtered_position_offset = [0.0, 0.0, 0.0]
                self._filtered_rotation_offset = [0.0, 0.0, 0.0]
                self._last_command_pose = list(robot_pose.pose)
                print("已锁定跟随参考点")
                print(f"手柄初始位置: {format_pose_values(latest_controller_pose.position, 3)}")
                print(f"手柄初始四元数: {format_pose_values(latest_controller_pose.quaternion, 3)}")
                print(f"机械臂初始 TCP: {format_pose_values(robot_pose.pose, 4)}")

                if not self._trigger_test_sent and any(abs(value) > 0.0 for value in self._config.trigger_test_offset):
                    trigger_pose = [
                        robot_pose.pose[index] + self._config.trigger_test_offset[index]
                        for index in range(6)
                    ]
                    trigger_pose[3:] = clamp_rpy(*trigger_pose[3:])
                    print(f"触发测试 TCP 位姿: {format_pose_values(trigger_pose, 4)}")
                    self._reference_robot_pose = list(trigger_pose)
                    self._reference_robot_transform = pose6_to_T16(list(trigger_pose))
                    self._last_command_pose = list(trigger_pose)
                    target_pose = trigger_pose
                    self._trigger_test_sent = True
                else:
                    return
            else:
                computation = self._compute_target_pose(latest_controller_pose)
                if computation is None:
                    return
                target_pose = computation.target_tcp_pose
                if self._last_command_pose is not None and self._is_within_deadband(
                    target_pose,
                    self._last_command_pose,
                ):
                    return

        self._bridge.move_to_target_pose(target_pose, wait=False)

        with self._lock:
            self._last_command_pose = list(target_pose)

            if computation is not None and now - self._last_log_time >= 1.0:
                command_debug = self._bridge.get_last_command_debug()
                print(
                    "手柄相对参考点增量: "
                    f"pos={format_pose_values(computation.controller_position_delta_raw, 4)} "
                    f"rot={format_pose_values(computation.controller_rotation_delta_raw, 4)}"
                )
                print(
                    "映射后参考偏移: "
                    f"pos={format_pose_values(computation.controller_position_offset, 4)} "
                    f"rot={format_pose_values(computation.controller_rotation_offset, 4)}"
                )
                print(f"跟随目标 TCP: {format_pose_values(target_pose, 4)}")
                if command_debug is not None:
                    print(f"SDK 目标法兰位姿: {format_pose_values(command_debug.flange_pose, 4)}")
                self._last_log_time = now

    def _compute_target_pose(self, controller_pose: XvisioPoseMessage) -> Optional[FollowComputation]:
        if (
            self._reference_controller_transform is None
            or self._reference_robot_transform is None
            or self._reference_robot_pose is None
        ):
            return None

        current_controller_transform = controller_pose_to_T16(controller_pose)
        reference_controller_position = [
            float(self._reference_controller_transform[3]),
            float(self._reference_controller_transform[7]),
            float(self._reference_controller_transform[11]),
        ]
        current_controller_position = [
            float(current_controller_transform[3]),
            float(current_controller_transform[7]),
            float(current_controller_transform[11]),
        ]
        raw_position_delta = [
            current - reference
            for current, reference in zip(current_controller_position, reference_controller_position)
        ]
        position_delta = []
        for index in range(3):
            raw_delta = raw_position_delta[index]
            if not self._config.position_axes_enabled[index]:
                position_delta.append(0.0)
                continue
            mapped_delta = (
                raw_delta
                * self._config.position_scale[index]
                * self._config.position_signs[index]
            )
            position_delta.append(clamp_scalar(mapped_delta, self._config.max_position_delta[index]))

        reference_controller_rotation = T16_rotation_matrix(self._reference_controller_transform)
        current_controller_rotation = T16_rotation_matrix(current_controller_transform)
        relative_controller_rotation = mat3_mul(
            current_controller_rotation,
            mat3_transpose(reference_controller_rotation),
        )
        raw_rotation_delta = T16_to_pose6(
            build_T16(relative_controller_rotation, [0.0, 0.0, 0.0])
        )[3:]
        rotation_delta = [0.0, 0.0, 0.0]
        if self._config.follow_orientation:
            for index in range(3):
                if not self._config.orientation_axes_enabled[index]:
                    rotation_delta[index] = 0.0
                    continue
                mapped_delta = (
                    raw_rotation_delta[index]
                    * self._config.rotation_scale[index]
                    * self._config.rotation_signs[index]
                )
                mapped_delta = clamp_scalar(mapped_delta, self._config.max_orientation_delta[index])
                rotation_delta[index] = mapped_delta
        alpha = self._config.smoothing_alpha
        self._filtered_position_offset = [
            current + alpha * (target - current)
            for current, target in zip(self._filtered_position_offset, position_delta)
        ]
        self._filtered_rotation_offset = [
            current + alpha * (target - current)
            for current, target in zip(self._filtered_rotation_offset, rotation_delta)
        ]
        filtered_rotation_transform = pose6_to_T16(
            [0.0, 0.0, 0.0] + clamp_rpy(*self._filtered_rotation_offset)
        )
        filtered_rotation = T16_rotation_matrix(filtered_rotation_transform)
        reference_robot_rotation = T16_rotation_matrix(self._reference_robot_transform)
        target_rotation = mat3_mul(filtered_rotation, reference_robot_rotation)
        target_position = [
            self._reference_robot_pose[index] + self._filtered_position_offset[index]
            for index in range(3)
        ]
        target_transform = build_T16(target_rotation, target_position)
        target_pose = T16_to_pose6(target_transform)

        return FollowComputation(
            controller_position_delta_raw=[float(value) for value in raw_position_delta],
            controller_position_offset=[float(value) for value in position_delta],
            controller_rotation_delta_raw=[float(value) for value in raw_rotation_delta],
            controller_rotation_offset=[float(value) for value in rotation_delta],
            target_tcp_pose=list(target_pose),
        )

    def _is_within_deadband(self, target_pose: Sequence[float], last_pose: Sequence[float]) -> bool:
        for index in range(3):
            if abs(target_pose[index] - last_pose[index]) > self._config.position_deadband:
                return False
        for index in range(3, 6):
            if abs(target_pose[index] - last_pose[index]) > self._config.rotation_deadband:
                return False
        return True


def run_follow_loop(
    follower: XvisioTcpFollower,
    stop_event: threading.Event,
    control_rate_hz: float,
) -> None:
    period = 1.0 / max(control_rate_hz, 1.0)
    last_error_print_time = 0.0

    while not stop_event.is_set():
        loop_start = time.monotonic()
        try:
            follower.step()
        except Exception as exc:
            now = time.monotonic()
            if now - last_error_print_time >= 1.0:
                print(f"跟随线程告警: {exc}")
                last_error_print_time = now

        elapsed = time.monotonic() - loop_start
        sleep_time = max(0.0, period - elapsed)
        if sleep_time > 0.0:
            time.sleep(sleep_time)


def is_tracking_start_key_pressed(
    controller_pose: XvisioPoseMessage,
    required_key_value: int,
) -> bool:
    return int(controller_pose.key) == int(required_key_value)


def run_controller_loop(
    controller: XvisioWirelessController,
    stop_event: threading.Event,
    poll_hz: float,
    print_interval_sec: float,
    device_info_interval_sec: float,
    pose_callback=None,
) -> None:
    poll_period = 1.0 / max(poll_hz, 1.0)
    last_pose_print_time = 0.0
    last_device_info_time = 0.0
    last_error_print_time = 0.0

    while not stop_event.is_set():
        now = time.monotonic()
        try:
            pose = controller.get_pose()
            if pose is not None:
                if pose_callback is not None:
                    pose_callback(pose)
                if now - last_pose_print_time >= print_interval_sec:
                    print(f"Xvisio 位姿: {format_controller_pose(pose)}")
                    last_pose_print_time = now

            if now - last_device_info_time >= device_info_interval_sec:
                status = controller.get_device_status()
                if status.battery > 0 or status.sn:
                    print(
                        "Xvisio 设备信息: "
                        f"sn={status.sn or 'unknown'} "
                        f"battery={status.battery} "
                        f"temp={status.temp} "
                        f"sleep={status.sleep} "
                        f"charging={status.charging}"
                    )
                last_device_info_time = now
        except Exception as exc:
            if now - last_error_print_time >= 1.0:
                print(f"Xvisio 读取告警: {exc}")
                last_error_print_time = now

        time.sleep(poll_period)


def interactive_target_loop(bridge: NeroPoseSDKBridge) -> None:
    print("请输入目标位姿: x y z roll pitch yaw")
    print("所有值都是 base_link 坐标系下的 TCP 位姿")
    print("输入 q 退出")

    while True:
        line = input("> ").strip()
        if not line:
            continue
        if line.lower() in {"q", "quit", "exit"}:
            break

        parts = line.split()
        if len(parts) != 6:
            print("请输入 6 个数字")
            continue

        try:
            target_pose = [float(value) for value in parts]
        except ValueError:
            print("输入包含非法数字")
            continue

        print(f"已接收目标位姿: {target_pose}")
        if bridge.move_to_target_pose(target_pose, wait=True):
            print("运动完成")
        else:
            print("等待运动完成超时")


def build_follow_config(args) -> FollowConfig:
    if bool(args.position_only) and bool(args.rotation_only):
        raise ValueError("--position-only 和 --rotation-only 不能同时使用")

    alpha = max(0.0, min(1.0, float(args.smoothing_alpha)))
    position_axes_enabled = parse_axis_selection(
        args.controller_position_axes,
        "controller_position_axes",
        {"x": 0, "y": 1, "z": 2},
    )
    orientation_axes_enabled = parse_axis_selection(
        args.controller_orientation_axes,
        "controller_orientation_axes",
        {"r": 0, "roll": 0, "p": 1, "pitch": 1, "y": 2, "yaw": 2},
    )
    if bool(args.rotation_only):
        position_axes_enabled = [False, False, False]

    follow_orientation = bool(args.follow_orientation) or not bool(args.position_only)
    if not follow_orientation:
        orientation_axes_enabled = [False, False, False]

    wait_for_key = bool(args.wait_for_key) or not bool(args.auto_start)
    return FollowConfig(
        control_rate_hz=max(1.0, float(args.control_rate_hz)),
        wait_for_key=wait_for_key,
        start_key_value=int(args.start_key_value),
        follow_orientation=follow_orientation,
        position_axes_enabled=position_axes_enabled,
        orientation_axes_enabled=orientation_axes_enabled,
        position_scale=[float(value) for value in args.position_scale],
        rotation_scale=[float(value) for value in args.rotation_scale],
        position_signs=[float(value) for value in args.position_signs],
        rotation_signs=[float(value) for value in args.rotation_signs],
        max_position_delta=[abs(float(value)) for value in args.max_position_delta],
        max_orientation_delta=[math.radians(abs(float(value))) for value in args.max_orientation_delta_deg],
        position_deadband=abs(float(args.position_deadband)),
        rotation_deadband=math.radians(abs(float(args.rotation_deadband_deg))),
        smoothing_alpha=alpha,
        trigger_test_offset=[float(value) for value in args.trigger_test_offset],
    )


def main() -> None:
    args = build_parser().parse_args()

    bridge = NeroPoseSDKBridge(
        interface=args.interface,
        channel=args.channel,
        firmware_version=args.firmware_version,
        tcp_offset=args.tcp_offset,
        motion_mode=args.motion_mode,
        speed_percent=args.speed_percent,
        publish_rate_hz=args.publish_rate_hz,
        enable_timeout_sec=args.enable_timeout_sec,
        feedback_timeout_sec=args.feedback_timeout_sec,
        command_repeats=1,
        command_repeat_interval_sec=0.0,
    )

    stop_event = threading.Event()
    controller = None
    controller_thread = None
    follower_thread = None
    last_robot_print_time = 0.0

    def on_robot_pose(pose) -> None:
        nonlocal last_robot_print_time
        now = time.monotonic()
        if now - last_robot_print_time >= 2.0:
            print(f"当前 TCP 位姿: {format_robot_pose(pose)}")
            last_robot_print_time = now

    try:
        print(f"正在连接机械臂: {args.interface}:{args.channel}")
        bridge.start(pose_callback=on_robot_pose)
        print("机械臂已连接、已使能，并进入 normal mode")

        print(f"机械臂移动到初始关节角(度): {args.initial_joints_deg}")
        if bridge.move_to_joint_positions(
            args.initial_joints_deg,
            wait=True,
            timeout=args.initial_joint_timeout_sec,
            degrees=True,
        ):
            print("机械臂已到达初始关节位")
        else:
            print("警告: 初始关节运动超时")

        print("正在启动 Xvisio 无线手柄")
        controller = XvisioWirelessController(
            library_path=args.xvisio_lib,
            device_type=resolve_controller_side(args.controller_side),
        )
        controller.start()

        controller_callback = None
        follower = None
        if not args.monitor_only and not args.interactive_target:
            follow_config = build_follow_config(args)
            follower = XvisioTcpFollower(bridge, follow_config)
            controller_callback = follower.handle_controller_pose
            print("已开启跟随模式: Xvisio 参考点映射位姿 -> TCP 目标")
            print(
                "跟随配置: "
                f"wait_for_key={follow_config.wait_for_key} "
                f"start_key_value={follow_config.start_key_value} "
                f"controller_position_axes={format_enabled_axes(follow_config.position_axes_enabled, ['x', 'y', 'z'])} "
                f"position_scale={follow_config.position_scale} "
                f"position_signs={follow_config.position_signs} "
                f"max_position_delta={follow_config.max_position_delta} "
                f"follow_orientation={follow_config.follow_orientation}"
            )
            if any(abs(value) > 0.0 for value in follow_config.trigger_test_offset):
                print(
                    "已开启触发测试偏移: "
                    f"{format_pose_values(follow_config.trigger_test_offset, 4)}"
                )
            if follow_config.follow_orientation:
                orientation_deg = [
                    round(math.degrees(value), 2) for value in follow_config.max_orientation_delta
                ]
                print(
                    "姿态跟随配置: "
                    f"controller_orientation_axes={format_enabled_axes(follow_config.orientation_axes_enabled, ['roll', 'pitch', 'yaw'])} "
                    f"rotation_scale={follow_config.rotation_scale} "
                    f"rotation_signs={follow_config.rotation_signs} "
                    f"max_orientation_delta_deg={orientation_deg}"
                )
            if follow_config.wait_for_key:
                print(
                    f"请先稳住手柄，按下启动键 key={follow_config.start_key_value} 后开始参考点映射跟随"
                )
            else:
                print("请先稳住手柄，系统将自动开始参考点映射跟随")

        controller_thread = threading.Thread(
            target=run_controller_loop,
            args=(
                controller,
                stop_event,
                args.controller_poll_hz,
                args.controller_print_interval_sec,
                args.device_info_interval_sec,
                controller_callback,
            ),
            name="xvisio_controller_loop",
            daemon=True,
        )
        controller_thread.start()

        if follower is not None:
            follower_thread = threading.Thread(
                target=run_follow_loop,
                args=(follower, stop_event, follow_config.control_rate_hz),
                name="xvisio_follow_loop",
                daemon=True,
            )
            follower_thread.start()

        if args.interactive_target:
            interactive_target_loop(bridge)
        elif args.monitor_only:
            print("当前为仅监视模式，按 Ctrl+C 退出")
            while not stop_event.is_set():
                time.sleep(0.2)
        else:
            if follow_config.wait_for_key:
                print(
                    f"机械臂已到初始位，等待手柄启动键 key={follow_config.start_key_value} 开始参考点映射跟随"
                )
            else:
                print("机械臂已到初始位，自动参考点映射 TCP 跟随已启动")
            while not stop_event.is_set():
                time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if follower_thread is not None and follower_thread.is_alive():
            follower_thread.join(timeout=1.0)
        if controller_thread is not None and controller_thread.is_alive():
            controller_thread.join(timeout=1.0)
        try:
            if controller is not None:
                controller.stop()
        finally:
            bridge.stop(disable=args.disable_on_exit)
        print("示例已停止")


if __name__ == "__main__":
    main()
