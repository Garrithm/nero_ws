import ctypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class Vector3(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
    ]


class Vector4(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("z", ctypes.c_float),
        ("w", ctypes.c_float),
    ]


class WirelessControllerKeys(ctypes.Structure):
    _fields_ = [
        ("keyTrigger", ctypes.c_int),
        ("keySide", ctypes.c_int),
        ("rocker_x", ctypes.c_int),
        ("rocker_y", ctypes.c_int),
        ("key", ctypes.c_int),
    ]


class WirelessControllerDeviceInfo(ctypes.Structure):
    _fields_ = [
        ("battery", ctypes.c_int),
        ("temp", ctypes.c_int),
        ("sleep", ctypes.c_int),
        ("charging", ctypes.c_int),
        ("sn", ctypes.c_char * 10),
    ]


@dataclass
class XvisioPoseMessage:
    position: list[float]
    quaternion: list[float]
    key: int
    key_trigger: int
    key_side: int
    rocker_x: int
    rocker_y: int
    timestamp: float


@dataclass
class XvisioDeviceStatus:
    battery: int
    temp: int
    sleep: int
    charging: int
    sn: str
    timestamp: float


class XvisioWirelessController:
    LEFT = 1
    RIGHT = 2

    def __init__(
        self,
        library_path: Optional[str] = None,
        device_type: int = 2,
    ) -> None:
        default_library = (
            Path(__file__).resolve().parents[2] / "XvisioSDK" / "libwirelessController.so"
        )
        self.library_path = Path(library_path).expanduser().resolve() if library_path else default_library
        self.device_type = int(device_type)
        self._lib = self._load_library(self.library_path)
        self._configure_signatures()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        if not self._lib.xv_start_wireless_controller():
            raise RuntimeError(f"failed to start wireless controller from {self.library_path}")
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._lib.xv_stop_wireless_controller()
        self._started = False

    def get_pose(self) -> Optional[XvisioPoseMessage]:
        if not self._started:
            raise RuntimeError("wireless controller is not started")

        position = Vector3()
        quaternion = Vector4()
        keys = WirelessControllerKeys()
        ok = self._lib.xv_wireless_controller_get_6dof(
            ctypes.byref(position),
            ctypes.byref(quaternion),
            ctypes.byref(keys),
            self.device_type,
        )
        if not ok:
            return None

        return XvisioPoseMessage(
            position=[float(position.x), float(position.y), float(position.z)],
            quaternion=[
                float(quaternion.x),
                float(quaternion.y),
                float(quaternion.z),
                float(quaternion.w),
            ],
            key=int(keys.key),
            key_trigger=int(keys.keyTrigger),
            key_side=int(keys.keySide),
            rocker_x=int(keys.rocker_x),
            rocker_y=int(keys.rocker_y),
            timestamp=time.time(),
        )

    def get_device_status(self) -> XvisioDeviceStatus:
        if not self._started:
            raise RuntimeError("wireless controller is not started")

        info = WirelessControllerDeviceInfo()
        self._lib.xv_wireless_controller_get_device_info(ctypes.byref(info), self.device_type)
        return XvisioDeviceStatus(
            battery=int(info.battery),
            temp=int(info.temp),
            sleep=int(info.sleep),
            charging=int(info.charging),
            sn=bytes(info.sn).split(b"\x00", 1)[0].decode("utf-8", errors="ignore"),
            timestamp=time.time(),
        )

    def _load_library(self, library_path: Path):
        if not library_path.exists():
            raise FileNotFoundError(f"Xvisio library not found: {library_path}")
        return ctypes.CDLL(str(library_path))

    def _configure_signatures(self) -> None:
        self._lib.xv_start_wireless_controller.argtypes = []
        self._lib.xv_start_wireless_controller.restype = ctypes.c_bool

        self._lib.xv_stop_wireless_controller.argtypes = []
        self._lib.xv_stop_wireless_controller.restype = ctypes.c_bool

        self._lib.xv_wireless_controller_get_6dof.argtypes = [
            ctypes.POINTER(Vector3),
            ctypes.POINTER(Vector4),
            ctypes.POINTER(WirelessControllerKeys),
            ctypes.c_int,
        ]
        self._lib.xv_wireless_controller_get_6dof.restype = ctypes.c_bool

        self._lib.xv_wireless_controller_get_device_info.argtypes = [
            ctypes.POINTER(WirelessControllerDeviceInfo),
            ctypes.c_int,
        ]
        self._lib.xv_wireless_controller_get_device_info.restype = None
