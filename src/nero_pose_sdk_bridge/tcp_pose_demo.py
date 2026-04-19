import argparse
import sys
import time
from pathlib import Path
from platform import system
from typing import Sequence


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal Nero TCP control demo")
    parser.add_argument("--interface", default="socketcan")
    parser.add_argument("--channel", default="nero_can")
    parser.add_argument("--firmware-version", default="default", choices=["default", "v111"])
    parser.add_argument("--speed-percent", type=int, default=15)
    parser.add_argument("--motion-mode", default="p", choices=["p", "l"])
    parser.add_argument("--enable-timeout-sec", type=float, default=5.0)
    parser.add_argument("--feedback-timeout-sec", type=float, default=3.0)
    parser.add_argument("--wait-timeout-sec", type=float, default=10.0)
    parser.add_argument(
        "--tcp-offset",
        type=float,
        nargs=6,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        default=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        help="TCP offset relative to flange: [m, m, m, rad, rad, rad]",
    )
    parser.add_argument(
        "--target-tcp",
        type=float,
        nargs=6,
        metavar=("X", "Y", "Z", "ROLL", "PITCH", "YAW"),
        default=None,
        help="Absolute TCP target pose in base frame",
    )
    parser.add_argument(
        "--target-offset",
        type=float,
        nargs=6,
        metavar=("DX", "DY", "DZ", "DROLL", "DPITCH", "DYAW"),
        default=None,
        help="Offset applied to the current TCP pose",
    )
    parser.add_argument(
        "--loop-x-step",
        type=float,
        default=None,
        help="Increment X by this amount each cycle based on the latest TCP pose",
    )
    parser.add_argument(
        "--loop-count",
        type=int,
        default=3,
        help="Number of looped X moves when --loop-x-step is used",
    )
    parser.add_argument(
        "--loop-pause-sec",
        type=float,
        default=0.5,
        help="Pause between looped X moves",
    )
    return parser


def resolve_firmware_version(name: str) -> str:
    if name == "default":
        return NeroFW.DEFAULT
    if name == "v111":
        return NeroFW.V111
    raise ValueError("firmware_version must be 'default' or 'v111'")


def create_demo_config(interface: str, channel: str, firmware_version: str):
    platform_system = system()
    if platform_system == "Windows":
        return create_agx_arm_config(
            robot=ArmModel.NERO,
            firmeware_version=resolve_firmware_version(firmware_version),
            interface="agx_cando" if interface == "socketcan" else interface,
            channel="0" if channel == "nero_can" else channel,
        )
    if platform_system == "Linux":
        return create_agx_arm_config(
            robot=ArmModel.NERO,
            firmeware_version=resolve_firmware_version(firmware_version),
            interface=interface,
            channel=channel,
        )
    if platform_system == "Darwin":
        return create_agx_arm_config(
            robot=ArmModel.NERO,
            firmeware_version=resolve_firmware_version(firmware_version),
            interface="slcan" if interface == "socketcan" else interface,
            channel="/dev/ttyACM0" if channel == "nero_can" else channel,
        )
    raise RuntimeError("Unsupported platform")


def format_pose(values: Sequence[float]) -> str:
    return "[" + ", ".join(f"{value:+.5f}" for value in values) + "]"


def wait_until_enabled(robot, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if robot.enable():
            return True
        robot.set_normal_mode()
        time.sleep(0.05)
    return False


def wait_feedback_ready(robot, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        joint_angles = robot.get_joint_angles()
        if joint_angles is not None and getattr(joint_angles, "hz", 0) > 0:
            return True
        time.sleep(0.05)
    return False


def wait_motion_done(robot, timeout: float = 10.0, poll_interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    time.sleep(0.3)
    while time.monotonic() < deadline:
        status = robot.get_arm_status()
        if status is not None and getattr(status.msg, "motion_status", None) == 0:
            return True
        time.sleep(poll_interval)
    return False


def read_current_tcp_pose(robot):
    tcp_pose = robot.get_tcp_pose()
    if tcp_pose is None:
        raise RuntimeError(
            "failed to read current tcp pose; make sure the arm is enabled and set_normal_mode() has been called"
        )
    return [float(value) for value in tcp_pose.msg]


def format_status_snapshot(robot) -> str:
    status = robot.get_arm_status()
    if status is None:
        return "arm_status unavailable"

    msg = status.msg
    parts = [
        f"ctrl_mode={msg.ctrl_mode}",
        f"arm_status={msg.arm_status}",
        f"mode_feedback={msg.mode_feedback}",
        f"motion_status={msg.motion_status}",
        f"trajectory_num={msg.trajectory_num}",
        f"err_code={msg.err_code}",
    ]
    return ", ".join(parts)


def move_with_tcp_target(robot, target_tcp: Sequence[float], motion_mode: str) -> None:
    flange_target = robot.get_tcp2flange_pose(list(target_tcp))
    print(f"target tcp pose    : {format_pose(target_tcp)}")
    print(f"target flange pose : {format_pose(flange_target)}")
    if motion_mode == "l":
        robot.move_l(flange_target)
    else:
        robot.move_p(flange_target)


def move_and_wait(robot, target_tcp: Sequence[float], motion_mode: str, timeout: float) -> list[float]:
    move_with_tcp_target(robot, target_tcp, motion_mode)
    if not wait_motion_done(robot, timeout=timeout):
        latest_tcp = None
        try:
            latest_tcp = read_current_tcp_pose(robot)
        except Exception:
            pass
        details = [f"tcp motion timeout after {timeout:.1f}s", format_status_snapshot(robot)]
        if latest_tcp is not None:
            details.append(f"latest tcp pose={format_pose(latest_tcp)}")
        raise RuntimeError("; ".join(details))
    latest_tcp = read_current_tcp_pose(robot)
    print(f"tcp pose after move: {format_pose(latest_tcp)}")
    return latest_tcp


def main() -> int:
    args = build_parser().parse_args()
    if args.loop_count <= 0:
        raise ValueError("loop_count must be > 0")
    if args.loop_pause_sec < 0.0:
        raise ValueError("loop_pause_sec must be >= 0")

    robot = None
    try:
        robot_cfg = create_demo_config(args.interface, args.channel, args.firmware_version)
        print(robot_cfg)

        robot = AgxArmFactory.create_arm(robot_cfg)
        robot.connect()

        robot.set_tcp_offset(list(args.tcp_offset))
        print(f"tcp offset         : {format_pose(args.tcp_offset)}")

        if not wait_until_enabled(robot, args.enable_timeout_sec):
            raise RuntimeError("failed to enable robot")

        robot.set_normal_mode()
        time.sleep(0.2)
        if not wait_feedback_ready(robot, args.feedback_timeout_sec):
            raise RuntimeError("failed to receive feedback after set_normal_mode()")

        robot.set_speed_percent(args.speed_percent)
        current_tcp = read_current_tcp_pose(robot)
        print(f"current tcp pose   : {format_pose(current_tcp)}")

        target_tcp = None
        if args.target_tcp is not None:
            target_tcp = [float(value) for value in args.target_tcp]
        elif args.target_offset is not None:
            target_tcp = [current_tcp[i] + float(args.target_offset[i]) for i in range(6)]

        if target_tcp is None:
            if args.loop_x_step is not None:
                for index in range(args.loop_count):
                    target_tcp = list(current_tcp)
                    target_tcp[0] += float(args.loop_x_step)
                    print(f"\nloop step {index + 1}/{args.loop_count}")
                    print(f"current tcp pose   : {format_pose(current_tcp)}")
                    print(f"x increment        : {args.loop_x_step:+.5f}")
                    current_tcp = move_and_wait(
                        robot,
                        target_tcp,
                        args.motion_mode,
                        args.wait_timeout_sec,
                    )
                    if index + 1 < args.loop_count and args.loop_pause_sec > 0.0:
                        time.sleep(args.loop_pause_sec)
                return 0
            print("no target provided, exiting after reading current tcp pose")
            return 0

        move_and_wait(robot, target_tcp, args.motion_mode, args.wait_timeout_sec)
        return 0
    finally:
        if robot is not None:
            try:
                robot.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
