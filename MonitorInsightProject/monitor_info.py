from __future__ import annotations

import ctypes
import json
import math
import os
import re
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtWidgets import QApplication

APP_NAME = "Monitor Insight"
APP_ID = "xyabc.monitor.insight"
VCP_CODE_INPUT_SELECT = 0x60
CCHDEVICENAME = 32
PHYSICAL_MONITOR_DESCRIPTION_SIZE = 128
CAPABILITIES_CACHE_TTL_SECONDS = 45.0

INPUT_SOURCE_LABELS = {
    0x01: "VGA 1",
    0x02: "VGA 2",
    0x03: "DVI 1",
    0x04: "DVI 2",
    0x05: "Composite 1",
    0x06: "Composite 2",
    0x07: "S-Video 1",
    0x08: "S-Video 2",
    0x09: "Tuner 1",
    0x0A: "Tuner 2",
    0x0B: "Tuner 3",
    0x0C: "Component 1",
    0x0D: "Component 2",
    0x0E: "Component 3",
    0x0F: "DisplayPort 1",
    0x10: "DisplayPort 2",
    0x11: "HDMI 1",
    0x12: "HDMI 2",
}

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * CCHDEVICENAME),
        ]

    class PHYSICAL_MONITOR(ctypes.Structure):
        _fields_ = [
            ("hPhysicalMonitor", wintypes.HANDLE),
            ("szPhysicalMonitorDescription", wintypes.WCHAR * PHYSICAL_MONITOR_DESCRIPTION_SIZE),
        ]

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), MONITORENUMPROC, wintypes.LPARAM]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(wintypes.DWORD)]
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
    dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.DestroyPhysicalMonitors.argtypes = [wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
    dxva2.DestroyPhysicalMonitors.restype = wintypes.BOOL
    dxva2.GetCapabilitiesStringLength.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    dxva2.GetCapabilitiesStringLength.restype = wintypes.BOOL
    dxva2.CapabilitiesRequestAndCapabilitiesReply.argtypes = [wintypes.HANDLE, ctypes.c_char_p, wintypes.DWORD]
    dxva2.CapabilitiesRequestAndCapabilitiesReply.restype = wintypes.BOOL
    dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
        wintypes.HANDLE,
        ctypes.c_ubyte,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
    dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, wintypes.DWORD]
    dxva2.SetVCPFeature.restype = wintypes.BOOL


@dataclass(slots=True, frozen=True)
class InputSourceOption:
    code: int
    label: str

    @property
    def display_text(self) -> str:
        return f"{self.label} (0x{self.code:02X})"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "label": self.label,
            "display_text": self.display_text,
        }


@dataclass(slots=True)
class CachedMonitorCapabilities:
    physical_monitor_description: str
    ddc_ci_supported: bool
    supported_input_source_codes: tuple[int, ...]
    input_switch_supported: bool
    input_control_error: str
    expires_at: float


@dataclass(slots=True)
class MonitorControlInfo:
    rect: tuple[int, int, int, int]
    gdi_device_name: str
    physical_monitor_description: str
    ddc_ci_supported: bool
    current_input_source_code: int | None
    supported_input_source_codes: tuple[int, ...]
    input_switch_supported: bool
    input_control_error: str


@dataclass(slots=True)
class MonitorSnapshot:
    index: int
    name: str
    manufacturer: str
    model: str
    serial_number: str
    is_primary: bool
    desktop_resolution: tuple[int, int]
    estimated_native_resolution: tuple[int, int]
    work_area_resolution: tuple[int, int]
    position: tuple[int, int]
    refresh_rate_hz: float
    scale_factor: float
    scale_percent: int
    logical_dpi: float
    physical_dpi: float
    physical_size_mm: tuple[float, float]
    diagonal_inches: float
    color_depth: int
    orientation: str
    gdi_device_name: str
    physical_monitor_description: str
    ddc_ci_supported: bool
    current_input_source_code: int | None
    current_input_source_label: str
    supported_input_sources: tuple[InputSourceOption, ...]
    input_switch_supported: bool
    input_control_error: str

    @property
    def identity(self) -> tuple[str, str, str, str, tuple[int, int]]:
        return (
            self.gdi_device_name,
            self.serial_number,
            self.model,
            self.name,
            self.desktop_resolution,
        )

    @property
    def display_title(self) -> str:
        return self.model or self.name or f"显示器 {self.index}"

    @property
    def monitor_rect(self) -> tuple[int, int, int, int]:
        return (
            self.position[0],
            self.position[1],
            self.position[0] + self.desktop_resolution[0],
            self.position[1] + self.desktop_resolution[1],
        )

    @property
    def native_monitor_rect(self) -> tuple[int, int, int, int]:
        return (
            int(round(self.position[0] * self.scale_factor)),
            int(round(self.position[1] * self.scale_factor)),
            int(round((self.position[0] + self.desktop_resolution[0]) * self.scale_factor)),
            int(round((self.position[1] + self.desktop_resolution[1]) * self.scale_factor)),
        )

    @property
    def current_input_source_text(self) -> str:
        if self.current_input_source_code is None:
            return self.current_input_source_label or "未读取"
        return f"{self.current_input_source_label} (0x{self.current_input_source_code:02X})"

    @property
    def supported_input_source_text(self) -> str:
        if not self.supported_input_sources:
            return "未提供"
        return " / ".join(option.display_text for option in self.supported_input_sources)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "is_primary": self.is_primary,
            "desktop_resolution": {
                "width": self.desktop_resolution[0],
                "height": self.desktop_resolution[1],
            },
            "estimated_native_resolution": {
                "width": self.estimated_native_resolution[0],
                "height": self.estimated_native_resolution[1],
            },
            "work_area_resolution": {
                "width": self.work_area_resolution[0],
                "height": self.work_area_resolution[1],
            },
            "position": {
                "x": self.position[0],
                "y": self.position[1],
            },
            "refresh_rate_hz": self.refresh_rate_hz,
            "scale_factor": self.scale_factor,
            "scale_percent": self.scale_percent,
            "logical_dpi": self.logical_dpi,
            "physical_dpi": self.physical_dpi,
            "physical_size_mm": {
                "width": self.physical_size_mm[0],
                "height": self.physical_size_mm[1],
            },
            "diagonal_inches": self.diagonal_inches,
            "color_depth": self.color_depth,
            "orientation": self.orientation,
            "gdi_device_name": self.gdi_device_name,
            "physical_monitor_description": self.physical_monitor_description,
            "ddc_ci_supported": self.ddc_ci_supported,
            "current_input_source": {
                "code": self.current_input_source_code,
                "label": self.current_input_source_label,
                "display_text": self.current_input_source_text,
            },
            "supported_input_sources": [option.to_dict() for option in self.supported_input_sources],
            "input_switch_supported": self.input_switch_supported,
            "input_control_error": self.input_control_error,
        }


_CAPABILITIES_CACHE: dict[str, CachedMonitorCapabilities] = {}


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def ensure_application() -> QApplication:
    app = QApplication.instance()
    if app is not None:
        return app
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("xyabc")
    app.setQuitOnLastWindowClosed(True)
    return app


def orientation_from_size(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "未知"
    if width == height:
        return "方形"
    if width > height:
        return "横向"
    return "纵向"


def diagonal_inches_from_mm(width_mm: float, height_mm: float) -> float:
    if width_mm <= 0 or height_mm <= 0:
        return 0.0
    return round(math.hypot(width_mm, height_mm) / 25.4, 2)


def input_source_label(code: int | None) -> str:
    if code is None:
        return "未读取"
    return INPUT_SOURCE_LABELS.get(code, f"输入源 0x{code:02X}")


def parse_supported_input_source_codes(capabilities_string: str) -> tuple[int, ...]:
    if not capabilities_string:
        return ()
    match = re.search(r"60\(([^)]*)\)", capabilities_string, flags=re.IGNORECASE)
    if not match:
        return ()
    values = []
    for token in re.findall(r"[0-9A-Fa-f]{2}", match.group(1)):
        code = int(token, 16)
        if code not in values:
            values.append(code)
    return tuple(values)


def _monitor_rect_from_geometry(x: int, y: int, width: int, height: int) -> tuple[int, int, int, int]:
    return (x, y, x + width, y + height)


def _format_windows_error(prefix: str) -> str:
    error = ctypes.get_last_error()
    if not error:
        return prefix
    return f"{prefix} ({error}: {ctypes.FormatError(error).strip()})"


def _monitor_cache_key(gdi_device_name: str, rect: tuple[int, int, int, int]) -> str:
    device_name = gdi_device_name.strip() or "UNKNOWN"
    return f"{device_name}:{rect[0]},{rect[1]},{rect[2]},{rect[3]}"


def _get_cached_capabilities(cache_key: str) -> CachedMonitorCapabilities | None:
    cached = _CAPABILITIES_CACHE.get(cache_key)
    if cached is None:
        return None
    if cached.expires_at < time.monotonic():
        _CAPABILITIES_CACHE.pop(cache_key, None)
        return None
    return cached


def _store_cached_capabilities(
    cache_key: str,
    physical_monitor_description: str,
    ddc_ci_supported: bool,
    supported_input_source_codes: tuple[int, ...],
    input_switch_supported: bool,
    input_control_error: str,
) -> None:
    _CAPABILITIES_CACHE[cache_key] = CachedMonitorCapabilities(
        physical_monitor_description=physical_monitor_description,
        ddc_ci_supported=ddc_ci_supported,
        supported_input_source_codes=supported_input_source_codes,
        input_switch_supported=input_switch_supported,
        input_control_error=input_control_error,
        expires_at=time.monotonic() + CAPABILITIES_CACHE_TTL_SECONDS,
    )


def _read_capabilities_string(handle: wintypes.HANDLE) -> tuple[str, str]:
    length = wintypes.DWORD()
    if not dxva2.GetCapabilitiesStringLength(handle, ctypes.byref(length)):
        return "", _format_windows_error("读取能力字符串长度失败")
    if length.value == 0:
        return "", "显示器未返回能力字符串"
    buffer = ctypes.create_string_buffer(length.value)
    if not dxva2.CapabilitiesRequestAndCapabilitiesReply(handle, buffer, length.value):
        return "", _format_windows_error("读取能力字符串失败")
    return buffer.value.decode("ascii", errors="ignore").strip(), ""


def _read_current_input_source_code(handle: wintypes.HANDLE) -> tuple[int | None, str]:
    code_type = wintypes.DWORD()
    current = wintypes.DWORD()
    maximum = wintypes.DWORD()
    if not dxva2.GetVCPFeatureAndVCPFeatureReply(
        handle,
        VCP_CODE_INPUT_SELECT,
        ctypes.byref(code_type),
        ctypes.byref(current),
        ctypes.byref(maximum),
    ):
        return None, _format_windows_error("读取当前输入源失败")
    return int(current.value), ""


def enumerate_monitor_control_infos() -> dict[tuple[int, int, int, int], MonitorControlInfo]:
    if sys.platform != "win32":
        return {}

    control_infos: dict[tuple[int, int, int, int], MonitorControlInfo] = {}

    def callback(hmonitor, hdc, lprc, lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return True

        rect = (
            int(info.rcMonitor.left),
            int(info.rcMonitor.top),
            int(info.rcMonitor.right),
            int(info.rcMonitor.bottom),
        )
        gdi_device_name = info.szDevice.strip()
        cache_key = _monitor_cache_key(gdi_device_name, rect)

        count = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)):
            control_infos[rect] = MonitorControlInfo(
                rect=rect,
                gdi_device_name=gdi_device_name,
                physical_monitor_description="",
                ddc_ci_supported=False,
                current_input_source_code=None,
                supported_input_source_codes=(),
                input_switch_supported=False,
                input_control_error=_format_windows_error("无法获取物理显示器数量"),
            )
            return True

        if count.value == 0:
            control_infos[rect] = MonitorControlInfo(
                rect=rect,
                gdi_device_name=gdi_device_name,
                physical_monitor_description="",
                ddc_ci_supported=False,
                current_input_source_code=None,
                supported_input_source_codes=(),
                input_switch_supported=False,
                input_control_error="未发现可控制的物理显示器",
            )
            return True

        monitors = (PHYSICAL_MONITOR * count.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, monitors):
            control_infos[rect] = MonitorControlInfo(
                rect=rect,
                gdi_device_name=gdi_device_name,
                physical_monitor_description="",
                ddc_ci_supported=False,
                current_input_source_code=None,
                supported_input_source_codes=(),
                input_switch_supported=False,
                input_control_error=_format_windows_error("无法获取物理显示器句柄"),
            )
            return True

        try:
            primary_monitor = monitors[0]
            current_code, current_error = _read_current_input_source_code(primary_monitor.hPhysicalMonitor)
            cached = _get_cached_capabilities(cache_key)

            if cached is not None:
                supported_codes = list(cached.supported_input_source_codes)
                if current_code is not None and current_code not in supported_codes:
                    supported_codes.insert(0, current_code)
                control_infos[rect] = MonitorControlInfo(
                    rect=rect,
                    gdi_device_name=gdi_device_name,
                    physical_monitor_description=cached.physical_monitor_description,
                    ddc_ci_supported=bool(cached.ddc_ci_supported or current_code is not None),
                    current_input_source_code=current_code,
                    supported_input_source_codes=tuple(supported_codes),
                    input_switch_supported=cached.input_switch_supported,
                    input_control_error=current_error or cached.input_control_error,
                )
                return True

            capabilities_string, caps_error = _read_capabilities_string(primary_monitor.hPhysicalMonitor)
            supported_codes = list(parse_supported_input_source_codes(capabilities_string))
            if current_code is not None and current_code not in supported_codes:
                supported_codes.insert(0, current_code)
            error_message = current_error or caps_error
            ddc_ci_supported = bool(capabilities_string or current_code is not None)
            input_switch_supported = ddc_ci_supported and len(supported_codes) > 1
            physical_monitor_description = primary_monitor.szPhysicalMonitorDescription.strip()
            _store_cached_capabilities(
                cache_key=cache_key,
                physical_monitor_description=physical_monitor_description,
                ddc_ci_supported=ddc_ci_supported,
                supported_input_source_codes=tuple(supported_codes),
                input_switch_supported=input_switch_supported,
                input_control_error=caps_error,
            )
            control_infos[rect] = MonitorControlInfo(
                rect=rect,
                gdi_device_name=gdi_device_name,
                physical_monitor_description=physical_monitor_description,
                ddc_ci_supported=ddc_ci_supported,
                current_input_source_code=current_code,
                supported_input_source_codes=tuple(supported_codes),
                input_switch_supported=input_switch_supported,
                input_control_error=error_message,
            )
        finally:
            dxva2.DestroyPhysicalMonitors(count.value, monitors)
        return True

    enum_callback = MONITORENUMPROC(callback)
    user32.EnumDisplayMonitors(None, None, enum_callback, 0)
    return control_infos


def collect_monitor_snapshots(app: QApplication | None = None) -> list[MonitorSnapshot]:
    app = app or ensure_application()
    primary_screen = app.primaryScreen()
    control_infos = enumerate_monitor_control_infos()
    remaining_control_infos = dict(control_infos)
    screen_records: list[dict] = []

    for index, screen in enumerate(app.screens(), start=1):
        geometry = screen.geometry()
        work_area = screen.availableGeometry()
        physical_size = screen.physicalSize()
        scale_factor = max(float(screen.devicePixelRatio()), 1.0)
        desktop_width = int(geometry.width())
        desktop_height = int(geometry.height())
        estimated_native_width = max(int(round(desktop_width * scale_factor)), desktop_width)
        estimated_native_height = max(int(round(desktop_height * scale_factor)), desktop_height)
        logical_rect = _monitor_rect_from_geometry(int(geometry.x()), int(geometry.y()), desktop_width, desktop_height)
        native_rect = (
            int(round(geometry.x() * scale_factor)),
            int(round(geometry.y() * scale_factor)),
            int(round((geometry.x() + desktop_width) * scale_factor)),
            int(round((geometry.y() + desktop_height) * scale_factor)),
        )
        control_info = None
        for candidate in (logical_rect, native_rect):
            if candidate in remaining_control_infos:
                control_info = remaining_control_infos.pop(candidate)
                break

        screen_records.append(
            {
                "index": index,
                "screen": screen,
                "work_area": work_area,
                "physical_size": physical_size,
                "scale_factor": scale_factor,
                "desktop_width": desktop_width,
                "desktop_height": desktop_height,
                "estimated_native_width": estimated_native_width,
                "estimated_native_height": estimated_native_height,
                "logical_rect": logical_rect,
                "native_rect": native_rect,
                "control_info": control_info,
            }
        )

    unmatched_records = [record for record in screen_records if record["control_info"] is None]
    if unmatched_records and remaining_control_infos:
        unmatched_records.sort(key=lambda record: (record["logical_rect"][1], record["logical_rect"][0]))
        fallback_controls = sorted(
            remaining_control_infos.values(),
            key=lambda info: (info.rect[1], info.rect[0], info.rect[3] - info.rect[1], info.rect[2] - info.rect[0]),
        )
        for record, control_info in zip(unmatched_records, fallback_controls):
            record["control_info"] = control_info

    snapshots: list[MonitorSnapshot] = []
    for record in screen_records:
        screen = record["screen"]
        work_area = record["work_area"]
        physical_size = record["physical_size"]
        scale_factor = record["scale_factor"]
        desktop_width = record["desktop_width"]
        desktop_height = record["desktop_height"]
        estimated_native_width = record["estimated_native_width"]
        estimated_native_height = record["estimated_native_height"]
        control_info = record["control_info"]
        width_mm = round(max(float(physical_size.width()), 0.0), 1)
        height_mm = round(max(float(physical_size.height()), 0.0), 1)
        supported_input_sources = tuple(
            InputSourceOption(code=code, label=input_source_label(code))
            for code in (control_info.supported_input_source_codes if control_info else ())
        )

        snapshots.append(
            MonitorSnapshot(
                index=record["index"],
                name=screen.name().strip(),
                manufacturer=screen.manufacturer().strip(),
                model=screen.model().strip(),
                serial_number=screen.serialNumber().strip(),
                is_primary=screen is primary_screen,
                desktop_resolution=(desktop_width, desktop_height),
                estimated_native_resolution=(estimated_native_width, estimated_native_height),
                work_area_resolution=(int(work_area.width()), int(work_area.height())),
                position=(int(screen.geometry().x()), int(screen.geometry().y())),
                refresh_rate_hz=round(float(screen.refreshRate()), 3),
                scale_factor=round(scale_factor, 3),
                scale_percent=int(round(scale_factor * 100)),
                logical_dpi=round(float(screen.logicalDotsPerInch()), 2),
                physical_dpi=round(float(screen.physicalDotsPerInch()), 2),
                physical_size_mm=(width_mm, height_mm),
                diagonal_inches=diagonal_inches_from_mm(width_mm, height_mm),
                color_depth=int(screen.depth()),
                orientation=orientation_from_size(desktop_width, desktop_height),
                gdi_device_name=control_info.gdi_device_name if control_info else "",
                physical_monitor_description=control_info.physical_monitor_description if control_info else "",
                ddc_ci_supported=control_info.ddc_ci_supported if control_info else False,
                current_input_source_code=control_info.current_input_source_code if control_info else None,
                current_input_source_label=input_source_label(
                    control_info.current_input_source_code if control_info else None
                ),
                supported_input_sources=supported_input_sources,
                input_switch_supported=control_info.input_switch_supported if control_info else False,
                input_control_error=(
                    control_info.input_control_error
                    if control_info
                    else "当前显示器未返回 DDC/CI 输入源信息"
                ),
            )
        )
    return snapshots


def switch_monitor_input_source(snapshot: MonitorSnapshot, input_source_code: int) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "当前仅支持在 Windows 上切换显示器输入源"

    if snapshot.supported_input_sources:
        supported_codes = {option.code for option in snapshot.supported_input_sources}
        if input_source_code not in supported_codes:
            return False, f"当前显示器未声明支持 {input_source_label(input_source_code)}"

    state = {
        "matched": False,
        "success": False,
        "message": "未找到对应的物理显示器",
    }
    target_rect = snapshot.monitor_rect
    target_native_rect = snapshot.native_monitor_rect
    target_device = snapshot.gdi_device_name.strip()

    def callback(hmonitor, hdc, lprc, lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return True

        rect = (
            int(info.rcMonitor.left),
            int(info.rcMonitor.top),
            int(info.rcMonitor.right),
            int(info.rcMonitor.bottom),
        )
        device_name = info.szDevice.strip()
        if target_device:
            if device_name != target_device:
                return True
        elif rect not in (target_rect, target_native_rect):
            return True

        state["matched"] = True
        count = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)):
            state["message"] = _format_windows_error("无法获取物理显示器数量")
            return True
        if count.value == 0:
            state["message"] = "未发现可控制的物理显示器"
            return True

        monitors = (PHYSICAL_MONITOR * count.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, monitors):
            state["message"] = _format_windows_error("无法获取物理显示器句柄")
            return True

        try:
            primary_monitor = monitors[0]
            if not dxva2.SetVCPFeature(primary_monitor.hPhysicalMonitor, VCP_CODE_INPUT_SELECT, int(input_source_code)):
                state["message"] = _format_windows_error("发送输入源切换命令失败")
                return True
            state["success"] = True
            state["message"] = (
                f"已发送切换命令：{snapshot.display_title} -> {input_source_label(input_source_code)}"
            )
        finally:
            dxva2.DestroyPhysicalMonitors(count.value, monitors)
        return True

    enum_callback = MONITORENUMPROC(callback)
    if not user32.EnumDisplayMonitors(None, None, enum_callback, 0) and not state["matched"]:
        return False, _format_windows_error("枚举显示器失败")
    if not state["matched"]:
        return False, state["message"]
    return bool(state["success"]), str(state["message"])


def snapshot_signature(snapshots: list[MonitorSnapshot]) -> tuple:
    return tuple(
        (
            snapshot.identity,
            snapshot.position,
            snapshot.refresh_rate_hz,
            snapshot.scale_percent,
            snapshot.is_primary,
            snapshot.current_input_source_code,
            tuple(option.code for option in snapshot.supported_input_sources),
        )
        for snapshot in snapshots
    )


def snapshots_payload(snapshots: list[MonitorSnapshot]) -> dict:
    return {
        "app": APP_NAME,
        "monitor_count": len(snapshots),
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "monitors": [snapshot.to_dict() for snapshot in snapshots],
    }


def snapshots_to_json(snapshots: list[MonitorSnapshot]) -> str:
    return json.dumps(snapshots_payload(snapshots), ensure_ascii=False, indent=2)


def save_snapshot_report(path: str | Path, snapshots: list[MonitorSnapshot]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(snapshots_to_json(snapshots), encoding="utf-8")
    return output_path
