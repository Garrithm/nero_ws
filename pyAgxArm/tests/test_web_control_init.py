import importlib.util
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "web_control" / "app.py"
SPEC = importlib.util.spec_from_file_location("web_control_app", APP_PATH)
web_control_app = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(web_control_app)


class _FakeJointAngles:
    def __init__(self, values, hz):
        self.msg = values
        self.hz = hz


class _FeedbackRecoveryRobot:
    def __init__(self):
        self.enable_calls = 0
        self.normal_mode_calls = 0
        self.speed_percent = None

    def is_connected(self):
        return True

    def get_joint_angles(self):
        if self.normal_mode_calls >= 1:
            return _FakeJointAngles([0.0] * 7, 100.0)
        return None

    def set_normal_mode(self):
        self.normal_mode_calls += 1

    def set_speed_percent(self, speed_percent):
        self.speed_percent = speed_percent

    def enable(self):
        self.enable_calls += 1
        raise AssertionError("initialize_arm() should recover feedback before calling enable()")


def test_initialize_arm_recovers_feedback_before_reenable():
    robot = _FeedbackRecoveryRobot()
    controller = web_control_app.NeroController(
        {
            "can_port": "nero_can",
            "firmware_version": "default",
            "speed_percent": 10,
            "feedback_timeout": 10.0,
            "enable_timeout": 10.0,
            "reach_timeout": 20.0,
            "tolerance_deg": 1.0,
        }
    )
    controller._ensure_robot_connected = lambda: robot

    result = controller.initialize_arm()

    assert result["message"] == "机械臂初始化成功，已恢复稳定反馈"
    assert result["current_deg"] == [0.0] * 7
    assert robot.normal_mode_calls >= 1
    assert robot.enable_calls == 0
    assert robot.speed_percent == 10
