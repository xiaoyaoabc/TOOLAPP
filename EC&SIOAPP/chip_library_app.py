import argparse
import html
import json
import os
import sys
import tempfile
import time
import traceback
from collections import defaultdict
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QToolTip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

MODULE_DIR = Path(__file__).resolve().parent
from chip_library_builder import LIBRARY_PATH, build_library, ensure_library, module_name

APP_NAME = "Chip Library"
APP_TITLE = "Chip Library - 通用芯片信息库"
APP_ID = "xyabc.chip.library"
DEFAULT_ZOOM = 0.9
HOME_ZOOM = 0.55
MIN_ZOOM = 0.35
MAX_ZOOM = 2.4
HIDDEN_CHIPS_ENV = "CHIP_LIBRARY_HIDDEN_PATH"
DELETED_CHIPS_ENV = "CHIP_LIBRARY_DELETED_PATH"
USER_LIBRARY_ENV = "CHIP_LIBRARY_USER_LIBRARY_PATH"

MODULE_COLORS = {
    "power": QColor(198, 92, 54),
    "battery": QColor(158, 95, 49),
    "charger": QColor(186, 118, 42),
    "thermal": QColor(176, 71, 58),
    "fan": QColor(35, 117, 142),
    "keyboard": QColor(84, 76, 149),
    "espi_lpc": QColor(30, 111, 101),
    "fspi": QColor(226, 141, 54),
    "sspi": QColor(194, 124, 38),
    "smbus": QColor(25, 106, 143),
    "serial": QColor(83, 114, 45),
    "cir": QColor(97, 111, 130),
    "egpc": QColor(109, 78, 143),
    "peci": QColor(86, 132, 161),
    "pcie": QColor(129, 74, 61),
    "usb": QColor(46, 126, 95),
    "audio": QColor(153, 96, 44),
    "security": QColor(115, 73, 103),
    "parallel": QColor(129, 96, 67),
    "analog": QColor(188, 71, 73),
    "timer": QColor(70, 88, 112),
    "wake": QColor(131, 72, 91),
    "cec": QColor(30, 123, 126),
    "strap": QColor(96, 116, 54),
    "gpio": QColor(31, 89, 110),
    "other": QColor(120, 129, 142),
}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def runtime_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", "")
    return Path(bundle_root) if bundle_root else MODULE_DIR


def runtime_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        data_dir = Path(sys.executable).resolve().parent / "data"
    else:
        data_dir = MODULE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def master_library_path() -> Path:
    bundled = runtime_root() / "data" / LIBRARY_PATH.name
    if bundled.exists():
        return bundled
    return LIBRARY_PATH


def user_library_path() -> Path:
    override = os.environ.get(USER_LIBRARY_ENV, "").strip()
    if override:
        return Path(override)
    return runtime_data_dir() / "chip_library.user.json"


def runtime_library_path() -> Path:
    user_path = user_library_path()
    if user_path.exists():
        return user_path
    return master_library_path()


def deleted_chip_path() -> Path:
    override = os.environ.get(DELETED_CHIPS_ENV, "").strip() or os.environ.get(HIDDEN_CHIPS_ENV, "").strip()
    if override:
        return Path(override)
    return runtime_data_dir() / "chip_library_deleted.json"


def hidden_chip_path() -> Path:
    return deleted_chip_path()


def _normalize_library(library: dict) -> dict:
    normalized = dict(library)
    chips = list(library.get("chips", []))
    normalized["chips"] = chips
    normalized["chip_count"] = len(chips)
    return normalized


def _load_chip_id_list(path: Path, key: str) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        raw_ids = payload
    else:
        raw_ids = payload.get(key, payload.get("hidden_chip_ids", []))
    return sorted({str(chip_id).strip() for chip_id in raw_ids if str(chip_id).strip()})


def load_deleted_chip_ids() -> list[str]:
    path = deleted_chip_path()
    if path.exists():
        return _load_chip_id_list(path, "deleted_chip_ids")
    legacy_path = runtime_data_dir() / "chip_library_hidden.json"
    if legacy_path != path and legacy_path.exists():
        return _load_chip_id_list(legacy_path, "hidden_chip_ids")
    return []


def load_hidden_chip_ids() -> list[str]:
    return load_deleted_chip_ids()


def save_deleted_chip_ids(chip_ids: list[str]) -> None:
    normalized = sorted({str(chip_id).strip() for chip_id in chip_ids if str(chip_id).strip()})
    path = deleted_chip_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not normalized:
        if path.exists():
            path.unlink()
        return
    payload = {"deleted_chip_ids": normalized}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_hidden_chip_ids(chip_ids: list[str]) -> None:
    save_deleted_chip_ids(chip_ids)


def apply_hidden_chip_ids(library: dict, hidden_chip_ids: list[str] | set[str]) -> dict:
    hidden_set = {str(chip_id).strip() for chip_id in hidden_chip_ids if str(chip_id).strip()}
    all_chips = library.get("chips", [])
    visible_chips = [chip for chip in all_chips if chip.get("chip_id", "") not in hidden_set]
    filtered = dict(library)
    filtered["chips"] = visible_chips
    filtered["hidden_chip_ids"] = sorted(hidden_set)
    filtered["deleted_chip_ids"] = sorted(hidden_set)
    filtered["visible_chip_count"] = len(visible_chips)
    filtered["total_chip_count"] = len(all_chips)
    filtered["chip_count"] = len(visible_chips)
    return filtered


def persist_user_chip_library(library: dict) -> None:
    path = user_library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_normalize_library(library), ensure_ascii=False, indent=2), encoding="utf-8")


def clear_user_chip_library() -> None:
    path = user_library_path()
    if path.exists():
        path.unlink()


def load_raw_chip_library() -> dict:
    library_path = master_library_path()
    if library_path == LIBRARY_PATH:
        return _normalize_library(ensure_library())
    if library_path.exists():
        return _normalize_library(json.loads(library_path.read_text(encoding="utf-8-sig")))
    return _normalize_library(ensure_library())


def load_chip_library() -> dict:
    user_path = user_library_path()
    if user_path.exists():
        try:
            return _normalize_library(json.loads(user_path.read_text(encoding="utf-8-sig")))
        except (OSError, json.JSONDecodeError):
            user_path.unlink(missing_ok=True)
    return apply_hidden_chip_ids(load_raw_chip_library(), load_hidden_chip_ids())


def module_color(module_id: str) -> QColor:
    return MODULE_COLORS.get(module_id, MODULE_COLORS["other"])


TYPE_ORDER = {
    "EC芯片": 0,
    "SIO": 1,
    "CPU": 2,
    "PCIE转SATA": 3,
    "充电IC": 4,
    "电量计": 5,
    "温感": 6,
}


def chip_type_label(chip: dict) -> str:
    explicit = str(chip.get("type_label") or chip.get("chip_type_label") or "").strip()
    if explicit:
        return explicit

    category = str(chip.get("category", "")).strip()
    role = str(chip.get("chip_role", "")).strip()
    combined = f"{category} {role}".casefold()

    if "embedded controller" in combined or category.startswith("EC"):
        return "EC芯片"
    if "super i/o" in combined:
        return "SIO"
    if any(token in combined for token in ("cpu", "processor", "apu", "soc")):
        return "CPU"
    if "pcie to sata" in combined or "sata host controller" in combined:
        return "PCIE转SATA"

    if category:
        primary = category.split("/")[0].strip()
        return primary or category
    if role:
        return role
    return "其他"


def chip_type_sort_key(label: str) -> tuple[int, str]:
    return (TYPE_ORDER.get(label, 100), label.casefold())


def _stroke_pen(color: QColor, size: int) -> QPen:
    return QPen(color, max(1.6, size * 0.08), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def create_symbol_icon(kind: str, size: int = 20, color: QColor | None = None) -> QIcon:
    stroke = color or QColor(31, 76, 96)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(_stroke_pen(stroke, size))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    box = QRectF(2.0, 2.0, size - 4.0, size - 4.0)

    if kind == "zoom_in":
        painter.drawEllipse(QRectF(3.0, 3.0, size * 0.56, size * 0.56))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size - 4.0, size - 4.0))
        painter.drawLine(QPointF(size * 0.31, size * 0.31), QPointF(size * 0.31, size * 0.53))
        painter.drawLine(QPointF(size * 0.2, size * 0.42), QPointF(size * 0.42, size * 0.42))
    elif kind == "zoom_out":
        painter.drawEllipse(QRectF(3.0, 3.0, size * 0.56, size * 0.56))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size - 4.0, size - 4.0))
        painter.drawLine(QPointF(size * 0.2, size * 0.42), QPointF(size * 0.42, size * 0.42))
    elif kind == "fit_page":
        painter.drawRoundedRect(QRectF(5.0, 4.0, size - 10.0, size - 8.0), 2.0, 2.0)
        painter.drawLine(QPointF(2.5, 2.5), QPointF(6.5, 2.5))
        painter.drawLine(QPointF(2.5, 2.5), QPointF(2.5, 6.5))
        painter.drawLine(QPointF(size - 2.5, 2.5), QPointF(size - 6.5, 2.5))
        painter.drawLine(QPointF(size - 2.5, 2.5), QPointF(size - 2.5, 6.5))
        painter.drawLine(QPointF(2.5, size - 2.5), QPointF(6.5, size - 2.5))
        painter.drawLine(QPointF(2.5, size - 2.5), QPointF(2.5, size - 6.5))
        painter.drawLine(QPointF(size - 2.5, size - 2.5), QPointF(size - 6.5, size - 2.5))
        painter.drawLine(QPointF(size - 2.5, size - 2.5), QPointF(size - 2.5, size - 6.5))
    elif kind == "fit_width":
        painter.drawRoundedRect(QRectF(4.0, 5.0, size - 8.0, size - 10.0), 2.0, 2.0)
        painter.drawLine(QPointF(3.0, size / 2), QPointF(7.0, size / 2))
        painter.drawLine(QPointF(size - 3.0, size / 2), QPointF(size - 7.0, size / 2))
        painter.drawLine(QPointF(7.0, size / 2), QPointF(5.0, size / 2 - 2.0))
        painter.drawLine(QPointF(7.0, size / 2), QPointF(5.0, size / 2 + 2.0))
        painter.drawLine(QPointF(size - 7.0, size / 2), QPointF(size - 5.0, size / 2 - 2.0))
        painter.drawLine(QPointF(size - 7.0, size / 2), QPointF(size - 5.0, size / 2 + 2.0))
    elif kind == "check":
        painter.drawRoundedRect(box, 3.0, 3.0)
        painter.drawLine(QPointF(size * 0.28, size * 0.56), QPointF(size * 0.45, size * 0.72))
        painter.drawLine(QPointF(size * 0.45, size * 0.72), QPointF(size * 0.76, size * 0.34))
    else:
        painter.drawRoundedRect(box, 3.0, 3.0)

    painter.end()
    return QIcon(pixmap)


def _draw_app_icon_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0.0, 0.0, float(size), float(size))
    gradient.setColorAt(0.0, QColor(17, 47, 66))
    gradient.setColorAt(0.55, QColor(29, 92, 114))
    gradient.setColorAt(1.0, QColor(241, 168, 62))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(2.0, 2.0, float(size - 4), float(size - 4)), size * 0.22, size * 0.22)

    chip_rect = QRectF(size * 0.2, size * 0.2, size * 0.44, size * 0.44)
    painter.setBrush(QColor(250, 252, 253, 240))
    painter.drawRoundedRect(chip_rect, size * 0.07, size * 0.07)
    painter.setPen(QPen(QColor(241, 168, 62), max(2.0, size * 0.03)))
    for ratio in (0.22, 0.38, 0.54, 0.70):
        x = size * ratio
        painter.drawLine(QPointF(x, size * 0.08), QPointF(x, size * 0.2))
        painter.drawLine(QPointF(x, size * 0.64), QPointF(x, size * 0.8))
        painter.drawLine(QPointF(size * 0.08, x), QPointF(size * 0.2, x))
        painter.drawLine(QPointF(size * 0.64, x), QPointF(size * 0.8, x))

    painter.setPen(QPen(QColor(32, 84, 106), max(2.0, size * 0.03)))
    painter.drawEllipse(QPointF(size * 0.73, size * 0.34), size * 0.11, size * 0.11)
    painter.drawLine(QPointF(size * 0.68, size * 0.34), QPointF(size * 0.78, size * 0.34))
    painter.drawLine(QPointF(size * 0.73, size * 0.29), QPointF(size * 0.73, size * 0.39))
    painter.end()
    return pixmap


def create_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw_app_icon_pixmap(size))
    return icon


def create_chip_icon(size: int = 20, color: QColor | None = None) -> QIcon:
    stroke = color or QColor(28, 89, 108)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(stroke, max(1.6, size * 0.08), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(QColor(247, 248, 246))
    body = QRectF(size * 0.24, size * 0.24, size * 0.52, size * 0.52)
    painter.drawRoundedRect(body, size * 0.08, size * 0.08)
    for offset in (0.18, 0.38, 0.58, 0.78):
        x = size * offset
        painter.drawLine(QPointF(x, size * 0.08), QPointF(x, size * 0.24))
        painter.drawLine(QPointF(x, size * 0.76), QPointF(x, size * 0.92))
        painter.drawLine(QPointF(size * 0.08, x), QPointF(size * 0.24, x))
        painter.drawLine(QPointF(size * 0.76, x), QPointF(size * 0.92, x))
    painter.drawEllipse(QPointF(size * 0.38, size * 0.38), size * 0.04, size * 0.04)
    painter.end()
    return QIcon(pixmap)


def ensure_application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setWindowIcon(create_app_icon())
    app.setStyle("Fusion")
    set_windows_app_id()
    return app


class PackageCanvas(QWidget):
    pinActivated = pyqtSignal(int)
    pinHovered = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.chip: dict | None = None
        self.zoom = DEFAULT_ZOOM
        self.highlight_pins: set[int] = set()
        self.focus_pin: int | None = None
        self.selection_title = "芯片封装图"
        self.selection_subtitle = "从左侧选择模块、信号或单个引脚以高亮查看。"
        self._pin_hit_regions: dict[int, QRectF] = {}
        self._logical_width = 2680
        self._logical_height = 2680
        self._update_canvas_size()

    def _update_canvas_size(self) -> None:
        self.resize(int(self._logical_width * self.zoom), int(self._logical_height * self.zoom))
        self.setMinimumSize(int(self._logical_width * self.zoom), int(self._logical_height * self.zoom))
        self.updateGeometry()

    def set_chip(self, chip: dict | None) -> None:
        self.chip = chip
        self.highlight_pins.clear()
        self.focus_pin = None
        self._pin_hit_regions.clear()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        QToolTip.hideText()
        if chip and chip.get("view_type") == "document_only":
            self.selection_title = "芯片资料卡"
            self.selection_subtitle = "当前 PDF 未包含封装图或引脚表，右侧以资料卡方式展示芯片信息。"
        else:
            self.selection_title = "芯片封装图"
            self.selection_subtitle = "从左侧选择模块、信号或单个引脚以高亮查看。"
        self._update_canvas_size()
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom = clamp(zoom, MIN_ZOOM, MAX_ZOOM)
        self._update_canvas_size()
        self.update()

    def set_highlight(self, pins: list[int] | set[int], title: str, subtitle: str, focus_pin: int | None = None) -> None:
        self.highlight_pins = set(pins)
        self.focus_pin = focus_pin
        self.selection_title = title
        self.selection_subtitle = subtitle
        self.update()

    def clear_highlight(self) -> None:
        if self.chip and self.chip.get("view_type") == "document_only":
            self.set_highlight([], "芯片资料卡", "当前 PDF 未包含封装图或引脚表，右侧以资料卡方式展示芯片信息。")
            return
        self.set_highlight([], "芯片封装图", "从左侧选择模块、信号或单个引脚以高亮查看。")

    def _pin_reference(self, pin: dict) -> str:
        return pin.get("pin_ref") or f"P{pin['pin_number']}"

    def _pin_index_label(self, pin: dict) -> str:
        return str(pin.get("pin_index_label") or pin["pin_number"])

    def _side_count(self, side: str) -> int:
        if self.chip is None:
            return 1
        return max(1, sum(1 for pin in self.chip.get("pins", []) if pin.get("side") == side))

    def _body_rect(self) -> QRectF:
        return QRectF(780.0, 760.0, 1120.0, 1120.0)

    def _pin_position(self, pin: dict) -> tuple[QRectF, QRectF, QRectF, QRectF]:
        body = self._body_rect()
        side_index = pin["side_index"]
        pin_length = 64.0
        pin_thickness = 16.0

        if pin["side"] == "left":
            pitch = (body.height() - 110.0) / max(1, self._side_count("left") - 1)
            y = body.top() + 55.0 + side_index * pitch
            pin_rect = QRectF(body.left() - pin_length, y - pin_thickness * 0.5, pin_length, pin_thickness)
            number_rect = QRectF(body.left() - pin_length - 88.0, y - 14.0, 72.0, 28.0)
            label_rect = QRectF(42.0, y - 16.0, body.left() - pin_length - 142.0, 32.0)
            hit_rect = QRectF(24.0, y - 19.0, body.left() - 12.0, 38.0)
            return pin_rect, number_rect, label_rect, hit_rect
        if pin["side"] == "right":
            pitch = (body.height() - 110.0) / max(1, self._side_count("right") - 1)
            y = body.top() + 55.0 + side_index * pitch
            pin_rect = QRectF(body.right(), y - pin_thickness * 0.5, pin_length, pin_thickness)
            number_rect = QRectF(body.right() + pin_length + 18.0, y - 14.0, 72.0, 28.0)
            label_rect = QRectF(body.right() + pin_length + 106.0, y - 16.0, 580.0, 32.0)
            hit_rect = QRectF(body.right(), y - 19.0, 760.0, 38.0)
            return pin_rect, number_rect, label_rect, hit_rect
        if pin["side"] == "top":
            pitch = (body.width() - 110.0) / max(1, self._side_count("top") - 1)
            x = body.left() + 55.0 + side_index * pitch
            pin_rect = QRectF(x - pin_thickness * 0.5, body.top() - pin_length, pin_thickness, pin_length)
            number_rect = QRectF(x - 24.0, body.top() - pin_length - 36.0, 48.0, 20.0)
            label_rect = QRectF(x - 15.0, 48.0, 30.0, body.top() - pin_length - 54.0)
            hit_rect = QRectF(x - 18.0, 28.0, 36.0, body.top() - 24.0)
            return pin_rect, number_rect, label_rect, hit_rect
        pitch = (body.width() - 110.0) / max(1, self._side_count("bottom") - 1)
        x = body.left() + 55.0 + side_index * pitch
        pin_rect = QRectF(x - pin_thickness * 0.5, body.bottom(), pin_thickness, pin_length)
        number_rect = QRectF(x - 24.0, body.bottom() + pin_length + 14.0, 48.0, 20.0)
        label_rect = QRectF(x - 15.0, body.bottom() + pin_length + 44.0, 30.0, 580.0)
        hit_rect = QRectF(x - 18.0, body.bottom(), 36.0, 760.0)
        return pin_rect, number_rect, label_rect, hit_rect

    def _draw_rotated_label(self, painter: QPainter, rect: QRectF, text: str, angle: float, color: QColor, font: QFont) -> None:
        painter.save()
        painter.setFont(font)
        painter.setPen(color)
        if angle < 0:
            painter.translate(rect.left() + rect.width() * 0.5, rect.bottom())
            painter.rotate(angle)
            painter.drawText(QRectF(0.0, 0.0, rect.height(), rect.width()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        else:
            painter.translate(rect.right() - rect.width() * 0.5, rect.top())
            painter.rotate(angle)
            painter.drawText(QRectF(0.0, -rect.width(), rect.height(), rect.width()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()

    def _pin_at(self, position) -> int | None:
        if self.chip is None or not self.chip.get("pins"):
            return None
        logical = QPointF(position.x() / self.zoom, position.y() / self.zoom)
        for pin_number, region in self._pin_hit_regions.items():
            if region.contains(logical):
                return pin_number
        return None

    def mouseMoveEvent(self, event) -> None:
        pin_number = self._pin_at(event.position())
        if pin_number is None or self.chip is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            QToolTip.hideText()
            return
        pins = self.chip.get("pins", [])
        if pin_number < 1 or pin_number > len(pins):
            self.setCursor(Qt.CursorShape.ArrowCursor)
            QToolTip.hideText()
            return
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        pin = pins[pin_number - 1]
        aliases = ", ".join(pin.get("aliases", []))
        modules = ", ".join(module_name(module_id) for module_id in pin.get("modules", []))
        QToolTip.showText(event.globalPosition().toPoint(), f"{self._pin_reference(pin)}  {aliases}\n模块: {modules}", self)
        self.pinHovered.emit(pin_number)

    def mousePressEvent(self, event) -> None:
        pin_number = self._pin_at(event.position())
        if pin_number is not None and self.chip is not None and 1 <= pin_number <= len(self.chip.get("pins", [])):
            self.pinActivated.emit(pin_number)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(self.rect(), QColor(243, 245, 241))
        painter.scale(self.zoom, self.zoom)

        gradient = QLinearGradient(0.0, 0.0, 0.0, float(self._logical_height))
        gradient.setColorAt(0.0, QColor(250, 251, 248))
        gradient.setColorAt(1.0, QColor(241, 243, 239))
        painter.fillRect(QRectF(24.0, 24.0, self._logical_width - 48.0, self._logical_height - 48.0), gradient)

        header_font = QFont("Segoe UI Semibold", 18)
        subtitle_font = QFont("Segoe UI", 10)
        painter.setFont(header_font)
        painter.setPen(QColor(24, 41, 54))
        painter.drawText(QRectF(54.0, 42.0, 800.0, 36.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.selection_title)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(97, 108, 118))
        painter.drawText(QRectF(54.0, 80.0, 960.0, 24.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.selection_subtitle)

        if self.chip is None:
            painter.setPen(QColor(118, 127, 136))
            painter.setFont(QFont("Segoe UI", 16))
            painter.drawText(QRectF(0.0, 0.0, self._logical_width, self._logical_height), Qt.AlignmentFlag.AlignCenter, "尚未选择芯片")
            painter.end()
            return

        body = self._body_rect()
        shadow = QRectF(body.left() + 18.0, body.top() + 20.0, body.width(), body.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(29, 54, 71, 18))
        painter.drawRoundedRect(shadow, 42.0, 42.0)
        painter.setBrush(QColor(250, 249, 246))
        painter.setPen(QPen(QColor(33, 63, 80), 3.0))
        painter.drawRoundedRect(body, 40.0, 40.0)

        painter.setBrush(QColor(33, 63, 80))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(body.left() + 64.0, body.top() + 64.0), 16.0, 16.0)

        painter.setPen(QColor(32, 52, 67))
        painter.setFont(QFont("Segoe UI Semibold", 24))
        painter.drawText(QRectF(body.left() + 82.0, body.top() + 92.0, body.width() - 164.0, 44.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.chip["display_name"])
        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor(87, 101, 114))
        painter.drawText(
            QRectF(body.left() + 82.0, body.top() + 138.0, body.width() - 164.0, 24.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{self.chip['vendor']} · {self.chip['package']} · {self.chip['pin_count']} Pins",
        )
        painter.drawText(
            QRectF(body.left() + 82.0, body.bottom() - 80.0, body.width() - 164.0, 24.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "点击引脚可在左侧自动定位到对应记录。",
        )

        self._pin_hit_regions.clear()
        if not self.chip.get("pins"):
            painter.setPen(QColor(76, 90, 101))
            painter.setFont(QFont("Segoe UI Semibold", 18))
            painter.drawText(QRectF(body.left() + 82.0, body.top() + 260.0, body.width() - 164.0, 34.0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "该文档未包含封装 / 引脚定义")
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(
                QRectF(body.left() + 82.0, body.top() + 308.0, body.width() - 164.0, 70.0),
                Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                self.chip.get("description", "请在左侧查看芯片概览、关键寄存器和 BIOS 编程序列。"),
            )
            painter.setPen(QColor(97, 108, 118))
            painter.drawText(
                QRectF(body.left() + 82.0, body.top() + 400.0, body.width() - 164.0, 120.0),
                Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                "适用场景：查看 BIOS 初始化顺序、关键寄存器推荐值、AHCI / PCIe 兼容性说明，以及系统集成时的注意事项。",
            )
            painter.end()
            return

        name_font = QFont("Consolas", 11)
        number_font = QFont("Segoe UI", 9)
        active_font = QFont("Consolas", 11)
        active_font.setBold(True)
        for pin in self.chip["pins"]:
            pin_rect, number_rect, label_rect, hit_rect = self._pin_position(pin)
            color = module_color(pin.get("primary_module", "other"))
            highlight = pin["pin_number"] in self.highlight_pins or pin["pin_number"] == self.focus_pin
            fill_color = QColor(236, 239, 242)
            border_color = QColor(177, 185, 191)
            text_color = QColor(53, 64, 74)
            if highlight:
                fill_color = color.lighter(185)
                border_color = color.darker(110)
                text_color = color.darker(150)

            painter.setPen(QPen(border_color, 1.6))
            painter.setBrush(fill_color)
            painter.drawRoundedRect(pin_rect, 4.0, 4.0)

            marker_rect = QRectF(pin_rect)
            if pin["side"] in {"left", "right"}:
                marker_rect.setWidth(min(14.0, marker_rect.width()))
                if pin["side"] == "right":
                    marker_rect.moveLeft(pin_rect.right() - marker_rect.width())
            else:
                marker_rect.setHeight(min(14.0, marker_rect.height()))
                if pin["side"] == "bottom":
                    marker_rect.moveTop(pin_rect.bottom() - marker_rect.height())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(marker_rect, 3.0, 3.0)

            painter.setPen(QColor(73, 86, 96))
            painter.setFont(number_font)
            painter.drawText(number_rect, Qt.AlignmentFlag.AlignCenter, self._pin_index_label(pin))

            if pin["side"] == "left":
                painter.setFont(active_font if highlight else name_font)
                painter.setPen(text_color)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, pin["label"])
            elif pin["side"] == "right":
                painter.setFont(active_font if highlight else name_font)
                painter.setPen(text_color)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, pin["label"])
            elif pin["side"] == "top":
                self._draw_rotated_label(painter, label_rect, pin["label"], -90.0, text_color, active_font if highlight else name_font)
            else:
                self._draw_rotated_label(painter, label_rect, pin["label"], 90.0, text_color, active_font if highlight else name_font)

            self._pin_hit_regions[pin["pin_number"]] = hit_rect

        painter.end()


class ChipLibraryWindow(QMainWindow):
    def __init__(self, library: dict | None = None, test_mode: bool = False):
        super().__init__()
        self.raw_library: dict = {}
        self.library: dict = {}
        self.hidden_chip_ids: list[str] = []
        self.chips: list[dict] = []
        self._refresh_library_state(library)
        self.test_mode = test_mode
        self.current_chip: dict | None = None

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(create_app_icon())
        self.resize(1720, 1040)

        self._build_actions()
        self._build_menu()
        self._build_ui()
        self._connect_signals()
        self._apply_style()

        if self.chips:
            self.load_chip(self.chips[0]["chip_id"])
        else:
            self._show_empty_library_state()

    def _refresh_library_state(self, raw_library: dict | None = None) -> None:
        self.raw_library = raw_library or load_raw_chip_library()
        self.hidden_chip_ids = load_hidden_chip_ids()
        self.library = apply_hidden_chip_ids(self.raw_library, self.hidden_chip_ids)
        self.chips = self.library.get("chips", [])

    def _build_actions(self) -> None:
        self.chip_options_action = QAction(create_chip_icon(), "芯片选项", self)
        self.rebuild_library_action = QAction(create_symbol_icon("check"), "重新生成芯片库", self)
        self.exit_action = QAction("退出", self)
        self.zoom_in_action = QAction(create_symbol_icon("zoom_in"), "放大", self)
        self.zoom_out_action = QAction(create_symbol_icon("zoom_out"), "缩小", self)
        self.fit_action = QAction(create_symbol_icon("fit_page"), "适应窗口", self)
        self.reset_zoom_action = QAction(create_symbol_icon("fit_width"), "默认缩放", self)
        self.about_action = QAction("关于", self)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        file_menu.addAction(self.rebuild_library_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        chip_menu = self.menuBar().addMenu("芯片(&C)")
        chip_menu.addAction(self.chip_options_action)

        view_menu = self.menuBar().addMenu("视图(&V)")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addSeparator()
        view_menu.addAction(self.fit_action)
        view_menu.addAction(self.reset_zoom_action)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        help_menu.addAction(self.about_action)

    def _make_tool_button(self, icon: QIcon, text: str, accent: bool = False) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon)
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("accent", accent)
        return button

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        root_layout.addWidget(splitter)
        self.setCentralWidget(root)

        sidebar = QFrame()
        sidebar.setObjectName("SidebarPanel")
        sidebar.setMinimumWidth(350)
        sidebar.setMaximumWidth(420)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 18, 18, 18)
        side_layout.setSpacing(12)

        brand = QLabel("Chip Library")
        brand.setObjectName("BrandTitle")
        intro = QLabel("通用芯片资料界面。通过“芯片选项”切换型号，在右侧查看封装视图，在左侧查看芯片概览、模块、信号和引脚详情。")
        intro.setObjectName("MutedLabel")
        intro.setWordWrap(True)

        self.current_chip_label = QLabel("未选择芯片")
        self.current_chip_label.setObjectName("CardTitle")
        self.current_chip_meta = QLabel("等待加载芯片库")
        self.current_chip_meta.setObjectName("MutedLabel")
        self.current_chip_meta.setWordWrap(True)
        self.current_chip_stats = QLabel("0 Chips")
        self.current_chip_stats.setObjectName("StatBadge")

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("筛选模块 / 信号 / 引脚 / 功能")

        self.clear_filter_button = QPushButton("清空筛选")
        self.clear_filter_button.setCursor(Qt.CursorShape.PointingHandCursor)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(self.filter_edit, 1)
        filter_row.addWidget(self.clear_filter_button)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.module_list = QListWidget()
        self.signal_list = QListWidget()
        self.pin_list = QListWidget()
        self.tabs.addTab(self.module_list, "模块")
        self.tabs.addTab(self.signal_list, "信号")
        self.tabs.addTab(self.pin_list, "引脚")

        self.selection_title_label = QLabel("芯片概览")
        self.selection_title_label.setObjectName("CardTitle")
        self.selection_body_label = QLabel("默认显示当前芯片概览；点击左侧模块、信号或引脚后，右侧会高亮对应封装位置。")
        self.selection_body_label.setObjectName("MutedLabel")
        self.selection_body_label.setWordWrap(True)
        self.pin_detail_title_label = QLabel("引脚详情")
        self.pin_detail_title_label.setObjectName("CardTitle")
        self.pin_detail_browser = QTextBrowser()
        self.pin_detail_browser.setObjectName("DetailBrowser")
        self.pin_detail_browser.setOpenExternalLinks(False)
        self.pin_detail_browser.setReadOnly(True)
        self.pin_detail_browser.setMinimumHeight(280)
        self.pin_detail_browser.setHtml(self._default_detail_html())

        side_layout.addWidget(brand)
        side_layout.addWidget(intro)
        side_layout.addWidget(self.current_chip_label)
        side_layout.addWidget(self.current_chip_meta)
        side_layout.addWidget(self.current_chip_stats)
        side_layout.addLayout(filter_row)
        side_layout.addWidget(self.tabs, 1)
        side_layout.addWidget(self.selection_title_label)
        side_layout.addWidget(self.selection_body_label)
        side_layout.addWidget(self.pin_detail_title_label)
        side_layout.addWidget(self.pin_detail_browser)
        splitter.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("ContentPanel")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(12)

        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(8)
        self.toolbar_chip_label = QLabel("封装视图")
        self.toolbar_chip_label.setObjectName("CanvasTitle")
        self.toolbar_hint_label = QLabel("支持芯片概览、模块高亮、单引脚定位和自由缩放。")
        self.toolbar_hint_label.setObjectName("MutedLabel")

        toolbar_row.addWidget(self.toolbar_chip_label, 1)
        toolbar_row.addWidget(self.toolbar_hint_label)

        control_row = QHBoxLayout()
        control_row.setSpacing(8)
        self.chip_button = self._make_tool_button(create_chip_icon(), "芯片选项", accent=True)
        self.zoom_out_button = self._make_tool_button(create_symbol_icon("zoom_out"), "缩小")
        self.zoom_in_button = self._make_tool_button(create_symbol_icon("zoom_in"), "放大")
        self.fit_button = self._make_tool_button(create_symbol_icon("fit_page"), "适应")
        self.reset_zoom_button = self._make_tool_button(create_symbol_icon("fit_width"), "默认")
        self.zoom_label = QLabel("90%")
        self.zoom_label.setObjectName("ZoomBadge")
        for widget in (self.chip_button, self.zoom_out_button, self.zoom_in_button, self.fit_button, self.reset_zoom_button, self.zoom_label):
            control_row.addWidget(widget)
        control_row.addStretch(1)

        self.canvas = PackageCanvas()
        self.canvas_area = QScrollArea()
        self.canvas_area.setWidget(self.canvas)
        self.canvas_area.setWidgetResizable(False)
        self.canvas_area.setFrameShape(QFrame.Shape.NoFrame)

        self.canvas_footer = QLabel("主视图展示芯片封装与每个引脚的复用名称，颜色对应主要模块类别。")
        self.canvas_footer.setObjectName("MutedLabel")
        self.canvas_footer.setWordWrap(True)

        content_layout.addLayout(toolbar_row)
        content_layout.addLayout(control_row)
        content_layout.addWidget(self.canvas_area, 1)
        content_layout.addWidget(self.canvas_footer)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = QLabel("就绪")
        self.status_zoom_label = QLabel("缩放 90%")
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.status_zoom_label)

    def _connect_signals(self) -> None:
        self.exit_action.triggered.connect(self.close)
        self.chip_options_action.triggered.connect(self.open_chip_dialog)
        self.rebuild_library_action.triggered.connect(self.rebuild_library)
        self.zoom_in_action.triggered.connect(self.zoom_in)
        self.zoom_out_action.triggered.connect(self.zoom_out)
        self.fit_action.triggered.connect(self.fit_view)
        self.reset_zoom_action.triggered.connect(self.reset_zoom)
        self.about_action.triggered.connect(self.show_about)

        self.chip_button.clicked.connect(self.open_chip_dialog)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.fit_button.clicked.connect(self.fit_view)
        self.reset_zoom_button.clicked.connect(self.reset_zoom)
        self.clear_filter_button.clicked.connect(lambda: self.filter_edit.setText(""))
        self.filter_edit.textChanged.connect(self.refresh_lists)

        self.module_list.itemSelectionChanged.connect(self._on_module_selected)
        self.signal_list.itemSelectionChanged.connect(self._on_signal_selected)
        self.pin_list.itemSelectionChanged.connect(self._on_pin_selected)
        self.canvas.pinActivated.connect(self.activate_pin_from_canvas)
        self.canvas.pinHovered.connect(self._update_hover_status)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#Root {
                background: #eef1ec;
                color: #21313f;
            }
            QFrame#SidebarPanel, QFrame#ContentPanel {
                background: #f8faf7;
                border: 1px solid #d7ddd8;
                border-radius: 24px;
            }
            QLabel#BrandTitle {
                font: 700 24px "Georgia";
                color: #172735;
            }
            QLabel#CardTitle {
                font: 700 18px "Segoe UI";
                color: #1c2d39;
            }
            QLabel#CanvasTitle {
                font: 700 21px "Segoe UI";
                color: #1c2d39;
            }
            QLabel#MutedLabel, QLabel#DialogSubtitle {
                color: #687582;
                font: 10pt "Segoe UI";
            }
            QLabel#StatBadge, QLabel#ZoomBadge {
                background: #dce7e0;
                border: 1px solid #bfd0c7;
                border-radius: 12px;
                padding: 6px 12px;
                font: 700 10pt "Segoe UI";
                color: #1f566b;
            }
            QLabel#DialogTitle {
                font: 700 18px "Segoe UI";
                color: #1c2d39;
            }
            QLabel#DialogPreview {
                background: #eef3ef;
                border: 1px solid #d0dbd3;
                border-radius: 16px;
                padding: 12px;
                color: #284055;
            }
            QLineEdit, QListWidget, QTabWidget::pane, QTextBrowser#DetailBrowser {
                background: #fbfcfa;
                border: 1px solid #d4ddd7;
                border-radius: 16px;
            }
            QLineEdit {
                padding: 10px 12px;
            }
            QTextBrowser#DetailBrowser {
                padding: 8px;
                color: #21313f;
            }
            QListWidget {
                padding: 8px;
                outline: 0;
            }
            QListWidget::item {
                border: 1px solid #d4ddd7;
                border-radius: 14px;
                margin: 4px 0;
                padding: 10px 12px;
                background: #f7faf7;
            }
            QListWidget::item:selected {
                background: #dbe9e3;
                border-color: #8db4a4;
                color: #173343;
            }
            QTabBar::tab {
                background: transparent;
                padding: 8px 14px;
                margin-right: 4px;
                color: #5d6b78;
            }
            QTabBar::tab:selected {
                background: #dfeae4;
                border-radius: 12px;
                color: #1f566b;
                font: 700 10pt "Segoe UI";
            }
            QPushButton, QToolButton {
                background: #edf3ef;
                border: 1px solid #d1dbd4;
                border-radius: 14px;
                padding: 8px 12px;
                color: #203644;
            }
            QPushButton:hover, QToolButton:hover {
                background: #e4eee9;
            }
            QToolButton[accent="true"] {
                background: #1f566b;
                border-color: #1f566b;
                color: white;
            }
            QStatusBar {
                background: #f3f6f2;
                border-top: 1px solid #d4ddd7;
            }
            """
        )

    def refresh_lists(self) -> None:
        self._refresh_module_list()
        self._refresh_signal_list()
        self._refresh_pin_list()

    def _pin_reference(self, pin: dict) -> str:
        return pin.get("pin_ref") or f"P{pin['pin_number']}"

    def _format_pin_refs(self, pin_numbers: list[int]) -> str:
        if self.current_chip is None:
            return ", ".join(f"P{pin}" for pin in pin_numbers)
        lookup = {pin["pin_number"]: self._pin_reference(pin) for pin in self.current_chip.get("pins", [])}
        return ", ".join(lookup.get(pin_number, f"P{pin_number}") for pin_number in pin_numbers)

    def _current_filter(self) -> str:
        return self.filter_edit.text().strip().casefold()

    def _refresh_module_list(self) -> None:
        self.module_list.clear()
        if self.current_chip is None:
            return
        query = self._current_filter()
        modules = sorted(self.current_chip.get("modules", []), key=lambda item: (-item["count"], item["name"].casefold()))
        for module in modules:
            haystack = f"{module['id']} {module['name']}".casefold()
            if query and query not in haystack:
                continue
            item = QListWidgetItem(f"{module['name']}\n{module['count']} Pins")
            item.setData(Qt.ItemDataRole.UserRole, module)
            item.setToolTip(self._format_pin_refs(module["pins"][:24]))
            self.module_list.addItem(item)

    def _refresh_signal_list(self) -> None:
        self.signal_list.clear()
        if self.current_chip is None:
            return
        query = self._current_filter()
        for signal in self.current_chip.get("signals", []):
            haystack = signal["signal"].casefold()
            if query and query not in haystack:
                continue
            pins_text = self._format_pin_refs(signal["pins"][:8])
            item = QListWidgetItem(f"{signal['signal']}\n{pins_text}")
            item.setData(Qt.ItemDataRole.UserRole, signal)
            self.signal_list.addItem(item)

    def _refresh_pin_list(self) -> None:
        self.pin_list.clear()
        if self.current_chip is None:
            return
        query = self._current_filter()
        for pin in self.current_chip.get("pins", []):
            haystack = f"{pin['pin_number']} {pin['label']} {' '.join(pin.get('aliases', []))}".casefold()
            if query and query not in haystack:
                continue
            item = QListWidgetItem(f"{self._pin_reference(pin)}  {pin['label']}")
            item.setData(Qt.ItemDataRole.UserRole, pin)
            item.setToolTip(", ".join(pin.get("aliases", [])))
            self.pin_list.addItem(item)

    def _clear_other_lists(self, active: QListWidget) -> None:
        for widget in (self.module_list, self.signal_list, self.pin_list):
            if widget is not active:
                widget.blockSignals(True)
                widget.clearSelection()
                widget.blockSignals(False)

    def _badge_html(self, text: str, foreground: str, background: str) -> str:
        return (
            f"<span style='display:inline-block; margin:0 8px 8px 0; padding:4px 10px; "
            f"border-radius:11px; background:{background}; color:{foreground}; font-weight:700;'>"
            f"{html.escape(text)}</span>"
        )

    def _detail_table_html(self, rows: list[tuple[str, str]]) -> str:
        cells = []
        for title, value in rows:
            if value is None:
                continue
            rendered = html.escape(value if value else "-")
            cells.append(
                "<tr>"
                f"<td style='padding:5px 10px 5px 0; color:#6a7783; vertical-align:top; white-space:nowrap;'>{html.escape(title)}</td>"
                f"<td style='padding:5px 0; color:#21313f;'>{rendered}</td>"
                "</tr>"
            )
        return "<table style='width:100%; border-collapse:collapse;'>" + "".join(cells) + "</table>"

    def _selection_detail_html(self, title: str, lines: list[str]) -> str:
        items = "".join(f"<li style='margin-bottom:6px;'>{html.escape(line)}</li>" for line in lines)
        return (
            "<div style='font-family:Segoe UI; color:#21313f;'>"
            f"<div style='font-size:15px; font-weight:700; margin-bottom:10px;'>{html.escape(title)}</div>"
            "<ul style='margin:0; padding-left:18px; color:#50606d;'>"
            f"{items}"
            "</ul>"
            "</div>"
        )

    def _value_or_dash(self, value) -> str:
        if value is None:
            return "-"
        text = str(value).strip()
        return text if text else "-"

    def _join_values(self, values: list[str], separator: str = ", ") -> str:
        cleaned = [str(value).strip() for value in values if str(value).strip()]
        return separator.join(cleaned) if cleaned else "-"

    def _view_type_label(self, view_type: str) -> str:
        mapping = {
            "package_top": "顶视封装图",
            "functional_package": "功能封装视图",
            "document_only": "文档资料卡",
        }
        return mapping.get(view_type, self._value_or_dash(view_type))

    def _programming_item_card_html(self, item: dict) -> str:
        registers = self._join_values(item.get("registers", []))
        recommended = item.get("recommended", [])
        recommended_html = ""
        if recommended:
            recommended_html = (
                "<div style='margin-top:8px;'>"
                "<div style='font-weight:700; color:#1f3948; margin-bottom:4px;'>推荐设置</div>"
                "<ul style='margin:0; padding-left:18px; color:#50606d;'>"
                + "".join(f"<li style='margin-bottom:4px;'>{html.escape(value)}</li>" for value in recommended)
                + "</ul>"
                "</div>"
            )
        register_html = ""
        if registers != "-":
            register_html = (
                "<div style='margin-top:8px;'>"
                f"{self._badge_html('寄存器: ' + registers, '#1d4e64', '#e4f0f4')}"
                "</div>"
            )
        return (
            "<div style='margin-top:10px; padding:12px 14px; border:1px solid #d4ddd7; border-radius:14px; background:#f8faf7;'>"
            f"<div style='font-weight:700; color:#1c2d39; margin-bottom:4px;'>{html.escape(item.get('title', '编程项目'))}</div>"
            f"<div style='font-size:12px; color:#6a7783; margin-bottom:6px;'>第 {html.escape(str(item.get('page', '-')))} 页</div>"
            f"<div style='color:#21313f; line-height:1.6;'>{html.escape(item.get('summary', ''))}</div>"
            + register_html
            + recommended_html
            + "</div>"
        )

    def _chip_overview_html(self, chip: dict) -> str:
        summary_rows = [
            ("分类", chip.get("category")),
            ("角色", chip.get("chip_role")),
            ("厂商", chip.get("vendor")),
            ("系列", self._join_values([chip.get("family", ""), chip.get("series", "")], " / ")),
            ("封装", chip.get("package")),
            ("封装类型", chip.get("package_type")),
            ("视图类型", self._view_type_label(chip.get("view_type", ""))),
            ("文档类型", chip.get("document_type")),
            ("来源文件", chip.get("source_pdf_name")),
            ("型号别名", self._join_values(chip.get("variants", []))),
        ]
        stats_rows = [
            ("引脚数", str(chip.get("pin_count", 0))),
            ("模块数", str(len(chip.get("modules", [])))),
            ("信号数", str(len(chip.get("signals", [])))),
            ("章节数", str(len(chip.get("sections", [])))),
        ]
        programming_items = chip.get("programming_items", [])
        if programming_items:
            stats_rows.append(("编程条目", str(len(programming_items))))
        top_modules = ", ".join(module["name"] for module in sorted(chip.get("modules", []), key=lambda item: (-item["count"], item["name"].casefold()))[:5])
        section_preview = "、".join(section["title"] for section in chip.get("sections", [])[:6])
        feature_items = "".join(
            f"<li style='margin-bottom:4px;'>{html.escape(feature)}</li>" for feature in chip.get("features", [])
        )
        note_items = "".join(
            f"<li style='margin-bottom:4px;'>{html.escape(note)}</li>" for note in chip.get("notes", [])
        )
        description = html.escape(chip.get("description", "当前芯片尚未提供摘要说明。"))
        feature_section = ""
        if feature_items:
            feature_section = (
                "<div style='margin-top:14px;'>"
                "<div style='font-weight:700; margin-bottom:6px;'>已入库能力</div>"
                f"<ul style='margin:0; padding-left:18px; color:#50606d;'>{feature_items}</ul>"
                "</div>"
            )
        note_section = ""
        if note_items:
            note_section = (
                "<div style='margin-top:14px;'>"
                "<div style='font-weight:700; margin-bottom:6px;'>解析说明</div>"
                f"<ul style='margin:0; padding-left:18px; color:#50606d;'>{note_items}</ul>"
                "</div>"
            )
        module_section = ""
        if top_modules:
            module_section = (
                "<div style='margin-top:14px;'>"
                "<div style='font-weight:700; margin-bottom:6px;'>重点模块</div>"
                f"<div style='color:#50606d;'>{html.escape(top_modules)}</div>"
                "</div>"
            )
        section_section = ""
        if section_preview:
            section_section = (
                "<div style='margin-top:14px;'>"
                "<div style='font-weight:700; margin-bottom:6px;'>章节索引</div>"
                f"<div style='color:#50606d; line-height:1.6;'>{html.escape(section_preview)}</div>"
                "</div>"
            )
        programming_section = ""
        if programming_items:
            programming_cards = "".join(self._programming_item_card_html(item) for item in programming_items[:8])
            hidden_count = len(programming_items) - 8
            more_hint = ""
            if hidden_count > 0:
                more_hint = f"<div style='margin-top:8px; color:#6a7783;'>其余 {hidden_count} 个条目已入库，可继续扩展到专门的寄存器检索视图。</div>"
            programming_section = (
                "<div style='margin-top:14px;'>"
                "<div style='font-weight:700; margin-bottom:6px;'>关键编程条目</div>"
                + programming_cards
                + more_hint
                + "</div>"
            )
        return (
            "<div style='font-family:Segoe UI; color:#21313f;'>"
            f"<div style='font-size:18px; font-weight:700; margin-bottom:6px;'>{html.escape(chip.get('display_name', '芯片概览'))}</div>"
            f"<div style='margin-bottom:12px; color:#50606d;'>{description}</div>"
            + self._detail_table_html(summary_rows)
            + "<div style='margin-top:14px; font-weight:700;'>规模统计</div>"
            + self._detail_table_html(stats_rows)
            + module_section
            + section_section
            + feature_section
            + programming_section
            + note_section
            + "</div>"
        )

    def _default_detail_html(self) -> str:
        return self._selection_detail_html(
            "芯片信息",
            [
                "加载芯片后，这里默认显示芯片概览，包括分类、角色、封装、来源文档和已入库能力。",
                "选择左侧引脚或点击右侧封装图中的 pin 后，这里会切换为引脚详情。",
            ],
        )

    def _set_detail_html(self, markup: str) -> None:
        self.pin_detail_browser.setHtml(markup)
        self.pin_detail_browser.verticalScrollBar().setValue(0)

    def _voltage_badge_html(self, title: str, value, supported_fg: str, supported_bg: str) -> str:
        if value is None:
            return self._badge_html(f"{title}: 未注明", "#6a7783", "#edf1ee")
        return self._badge_html(
            f"{title}: {'支持' if value else '不支持'}",
            supported_fg if value else "#6a7783",
            supported_bg if value else "#e9eeea",
        )

    def _pin_detail_html(self, pin: dict) -> str:
        module_labels = ", ".join(module_name(module_id) for module_id in pin.get("modules", [])) or "其他"
        aliases = ", ".join(pin.get("aliases", [])) or pin.get("label", "")
        profile = pin.get("voltage_profile", {})
        gpio_alt = pin.get("gpio_alt_info") or {}
        generic_rows = pin.get("generic_info_rows") or []
        detail_entries = pin.get("detail_entries", [])

        badges = [
            self._voltage_badge_html("1.8V", profile.get("supports_1_8v"), "#17495b", "#d7edf0"),
            self._voltage_badge_html("3.3V", profile.get("supports_3_3v"), "#1f5d35", "#ddeedf"),
        ]
        if profile.get("supports_1_8v_input_only"):
            badges.append(self._badge_html("1.8V 仅输入", "#754d17", "#f6e8c9"))
        if profile.get("supports_5v_tolerant"):
            badges.append(self._badge_html("5V 容限", "#7c2130", "#f7dde2"))

        overview_rows = [
            ("引脚", self._pin_reference(pin)),
            ("名称", aliases),
            ("模块", module_labels),
            ("主模块", module_name(pin.get("primary_module", "other"))),
            ("电压能力", profile.get("summary", "")),
        ]

        gpio_rows: list[tuple[str, str]] = []
        if generic_rows:
            gpio_rows = generic_rows
        elif gpio_alt:
            gpio_rows = [
                ("GPIO 组", gpio_alt.get("group", "")),
                ("寄存器", gpio_alt.get("addr", "")),
                ("索引", gpio_alt.get("index", "")),
                ("默认模式", gpio_alt.get("mode", "")),
                ("输出能力", gpio_alt.get("output", "")),
                ("施密特", gpio_alt.get("schmitt", "")),
                ("上下拉能力", gpio_alt.get("pull_cap", "")),
                ("默认上下拉", gpio_alt.get("default_pull", "")),
                ("5VT", gpio_alt.get("vt5", "")),
                ("1.8V 输入", gpio_alt.get("v18", "")),
                ("功能1", gpio_alt.get("func1", "")),
                ("功能2", gpio_alt.get("func2", "")),
                ("功能3", gpio_alt.get("func3", "")),
            ]

        notes_html = ""
        if profile.get("notes"):
            notes_html = (
                "<div style='margin-top:12px;'>"
                "<div style='font-weight:700; margin-bottom:6px;'>电压说明</div>"
                "<ul style='margin:0; padding-left:18px; color:#50606d;'>"
                + "".join(f"<li style='margin-bottom:4px;'>{html.escape(note)}</li>" for note in profile["notes"])
                + "</ul></div>"
            )

        detail_cards = []
        for entry in detail_entries:
            entry_lines = []
            if entry.get("interface_cn") or entry.get("interface"):
                entry_lines.append(entry.get("interface_cn") or entry.get("interface"))
            if entry.get("attribute"):
                attr_line = f"属性: {entry['attribute']}"
                if entry.get("attribute_description"):
                    attr_line += f" - {entry['attribute_description']}"
                entry_lines.append(attr_line)
            if entry.get("description_cn") or entry.get("description"):
                entry_lines.append(entry.get("description_cn") or entry.get("description"))
            detail_cards.append(
                "<div style='margin-top:10px; padding:10px 12px; border:1px solid #d4ddd7; border-radius:14px; background:#f8faf7;'>"
                f"<div style='font-weight:700; color:#1c2d39; margin-bottom:4px;'>{html.escape(entry.get('summary_cn') or entry.get('signal_text') or entry.get('table_cn') or entry.get('table') or '引脚详情')}</div>"
                f"<div style='font-size:12px; color:#6a7783; margin-bottom:6px;'>{html.escape(entry.get('table_cn') or entry.get('table', ''))} · 第 {entry.get('page', '')} 页</div>"
                + "".join(f"<div style='margin-bottom:4px; color:#21313f;'>{html.escape(line)}</div>" for line in entry_lines)
                + "</div>"
            )

        if not detail_cards:
            detail_cards.append(
                "<div style='margin-top:10px; padding:10px 12px; border:1px dashed #d4ddd7; border-radius:14px; color:#687582;'>"
                "当前 pin 在已解析章节中没有额外说明，但封装别名和 GPIO 电气信息仍可直接使用。"
                "</div>"
            )

        gpio_section = ""
        if gpio_rows:
            gpio_section = (
                "<div style='margin-top:14px;'>"
                "<div style='font-weight:700; margin-bottom:6px;'>GPIO 电气信息</div>"
                + self._detail_table_html(gpio_rows)
                + "</div>"
            )

        return (
            "<div style='font-family:Segoe UI; color:#21313f;'>"
            f"<div style='font-size:18px; font-weight:700; margin-bottom:6px;'>{html.escape(self._pin_reference(pin))} · {html.escape(pin.get('display_name', pin.get('label', '')))}</div>"
            f"<div style='margin-bottom:10px;'>{''.join(badges)}</div>"
            + self._detail_table_html(overview_rows)
            + notes_html
            + gpio_section
            + "<div style='margin-top:14px; font-weight:700;'>规格书说明</div>"
            + "".join(detail_cards)
            + "</div>"
        )

    def _set_selection_state(self, title: str, body: str, pins: list[int] | set[int], focus_pin: int | None = None) -> None:
        pin_count = len(pins)
        self.selection_title_label.setText(title)
        self.selection_body_label.setText(body)
        self.canvas.set_highlight(pins, title, body, focus_pin)
        self.status_label.setText(f"{title} · {pin_count} Pins")
        self.canvas_footer.setText(body)

    def _on_module_selected(self) -> None:
        item = self.module_list.currentItem()
        if item is None:
            return
        self._clear_other_lists(self.module_list)
        module = item.data(Qt.ItemDataRole.UserRole)
        pins_text = self._format_pin_refs(module["pins"][:18])
        self._set_selection_state(module["name"], f"{module['name']} 共 {module['count']} 个引脚。示例: {pins_text}", module["pins"])
        self._set_detail_html(
            self._selection_detail_html(
                f"{module['name']} 模块",
                [
                    f"模块内共有 {module['count']} 个引脚。",
                    f"示例引脚: {pins_text}" if pins_text else "当前筛选结果为空。",
                    "继续点击单个引脚，可查看 1.8V / 3.3V、电气属性和章节说明。",
                ],
            )
        )

    def _on_signal_selected(self) -> None:
        item = self.signal_list.currentItem()
        if item is None:
            return
        self._clear_other_lists(self.signal_list)
        signal = item.data(Qt.ItemDataRole.UserRole)
        pins_text = self._format_pin_refs(signal["pins"])
        self._set_selection_state(signal["signal"], f"信号 {signal['signal']} 出现在 {pins_text}", signal["pins"])
        self._set_detail_html(
            self._selection_detail_html(
                signal["signal"],
                [
                    f"该信号当前映射到: {pins_text}" if pins_text else "当前信号没有解析到引脚。",
                    "继续点击具体引脚，可查看章节说明和 GPIO 电气能力。",
                ],
            )
        )

    def _on_pin_selected(self) -> None:
        item = self.pin_list.currentItem()
        if item is None:
            return
        self._clear_other_lists(self.pin_list)
        pin = item.data(Qt.ItemDataRole.UserRole)
        modules = ", ".join(module_name(module_id) for module_id in pin.get("modules", []))
        aliases = ", ".join(pin.get("aliases", []))
        self._set_selection_state(self._pin_reference(pin), f"{aliases}\n主要模块: {modules}", [pin["pin_number"]], pin["pin_number"])
        self._set_detail_html(self._pin_detail_html(pin))

    def _update_zoom_labels(self) -> None:
        zoom_text = f"{self.canvas.zoom * 100:.0f}%"
        self.zoom_label.setText(zoom_text)
        self.status_zoom_label.setText(f"缩放 {zoom_text}")

    def zoom_in(self) -> None:
        self.canvas.set_zoom(self.canvas.zoom + 0.1)
        self._update_zoom_labels()

    def zoom_out(self) -> None:
        self.canvas.set_zoom(self.canvas.zoom - 0.1)
        self._update_zoom_labels()

    def _apply_home_view(self) -> None:
        self.canvas.set_zoom(HOME_ZOOM)
        self._update_zoom_labels()

        viewport = self.canvas_area.viewport().size()
        target_x = int(max(0.0, self.canvas.width() * 0.5 - viewport.width() * 0.5))
        target_y = int(max(0.0, self.canvas.height() * 0.5 - viewport.height() * 0.5))
        self.canvas_area.horizontalScrollBar().setValue(target_x)
        self.canvas_area.verticalScrollBar().setValue(target_y)

    def reset_zoom(self) -> None:
        self._apply_home_view()

    def fit_view(self) -> None:
        viewport = self.canvas_area.viewport().size()
        zoom_x = (viewport.width() - 24.0) / self.canvas._logical_width
        zoom_y = (viewport.height() - 24.0) / self.canvas._logical_height
        self.canvas.set_zoom(min(zoom_x, zoom_y))
        self._update_zoom_labels()

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            APP_NAME,
            "Chip Library - 通用芯片信息库\n\n"
            "菜单栏包含“芯片 -> 芯片选项”，可选择已记录的芯片型号。\n"
            "左侧默认显示芯片概览，支持查看分类、角色、封装、来源文档和已入库能力。\n"
            "主视图以矢量方式绘制封装图，并展示每个引脚的复用名称。",
        )

    def open_chip_dialog(self, auto_accept_chip_id: str = "") -> None:
        if not self.raw_library.get("chips", []):
            QMessageBox.warning(self, APP_NAME, "芯片库为空。")
            return
        current_id = self.current_chip.get("chip_id", "") if self.current_chip else ""
        dialog = ChipSelectionDialog(self.raw_library.get("chips", []), self.hidden_chip_ids, current_id, self)
        if auto_accept_chip_id:
            dialog._select_chip(auto_accept_chip_id)
            dialog.accept()
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted and dialog.visibility_changed():
            deleted_chip_ids = dialog.hidden_chip_ids_list()
            save_hidden_chip_ids(deleted_chip_ids)
            if deleted_chip_ids:
                persist_user_chip_library(apply_hidden_chip_ids(self.raw_library, deleted_chip_ids))
            else:
                clear_user_chip_library()
            selected_chip = dialog.current_chip()
            selected_chip_id = selected_chip["chip_id"] if selected_chip else ""
            self._refresh_library_state()
            if selected_chip_id and any(chip["chip_id"] == selected_chip_id for chip in self.chips):
                self.load_chip(selected_chip_id)
            elif current_id and any(chip["chip_id"] == current_id for chip in self.chips):
                self.load_chip(current_id)
            elif self.chips:
                self.load_chip(self.chips[0]["chip_id"])
            else:
                self._show_empty_library_state()
            return
        if result != QDialog.DialogCode.Accepted:
            return
        chip = dialog.current_chip()
        if chip is not None:
            self.load_chip(chip["chip_id"])

    def rebuild_library(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            rebuilt_library = build_library()
            if self.hidden_chip_ids:
                persist_user_chip_library(apply_hidden_chip_ids(rebuilt_library, self.hidden_chip_ids))
            else:
                clear_user_chip_library()
            self._refresh_library_state(rebuilt_library)
        finally:
            QApplication.restoreOverrideCursor()
        current_id = self.current_chip.get("chip_id", "") if self.current_chip else ""
        if current_id and any(chip["chip_id"] == current_id for chip in self.chips):
            self.load_chip(current_id)
        elif self.chips:
            self.load_chip(self.chips[0]["chip_id"])
        else:
            self._show_empty_library_state()
        QMessageBox.information(self, APP_NAME, f"芯片库已重新生成，共 {len(self.chips)} 个芯片。")

    def _show_empty_library_state(self) -> None:
        hidden_count = len(self.hidden_chip_ids)
        self.current_chip = None
        self.current_chip_label.setText("没有可见芯片")
        if hidden_count:
            self.current_chip_meta.setText(f"当前已删除 {hidden_count} 颗芯片。可在“芯片选项”里恢复全部。")
            self.current_chip_stats.setText(f"0 Visible · {hidden_count} Deleted")
        else:
            self.current_chip_meta.setText("当前芯片库没有可显示的芯片。")
            self.current_chip_stats.setText("0 Chips")
        self.toolbar_chip_label.setText("芯片视图")
        self.selection_title_label.setText("芯片概览")
        self.selection_body_label.setText("当前没有可见芯片。可打开“芯片选项”查看列表、删除或恢复芯片。")
        self._set_detail_html(
            self._selection_detail_html(
                "芯片列表",
                [
                    "通过“芯片选项”查看当前芯片选型列表。",
                    "可删除不常用芯片，删除后会从当前芯片库移除。",
                    "恢复全部后，已删除芯片会重新回到当前芯片库。",
                ],
            )
        )
        self.module_list.clear()
        self.signal_list.clear()
        self.pin_list.clear()
        self.canvas.set_chip(None)
        self.canvas_footer.setText("当前没有可见芯片。")
        self.status_label.setText("芯片库为空")

    def load_chip(self, chip_id: str) -> None:
        for chip in self.chips:
            if chip["chip_id"] != chip_id:
                continue
            self.current_chip = chip
            break
        else:
            return
        category = self.current_chip.get("category", "芯片资料")
        chip_role = self.current_chip.get("chip_role", "")
        self.current_chip_label.setText(self.current_chip["display_name"])
        self.current_chip_meta.setText(
            f"{category} · {self.current_chip['vendor']} · {chip_role}\n"
            f"{self.current_chip['package']} · {self.current_chip.get('source_pdf_name', '')}"
        )
        if self.current_chip.get("view_type") == "document_only":
            self.current_chip_stats.setText(
                f"{len(self.current_chip.get('programming_items', []))} Items · {len(self.current_chip.get('sections', []))} Sections · {self.current_chip.get('document_type', 'Document')}"
            )
        else:
            self.current_chip_stats.setText(
                f"{self.current_chip['pin_count']} Pins · {len(self.current_chip.get('modules', []))} Modules · {len(self.current_chip.get('signals', []))} Signals"
            )
        self.toolbar_chip_label.setText(f"{self.current_chip['display_name']} · {category}")
        self.canvas.set_chip(self.current_chip)
        self.refresh_lists()
        self.selection_title_label.setText("芯片概览")
        if self.current_chip.get("view_type") == "document_only":
            self.selection_body_label.setText(self.current_chip.get("description", "当前芯片以资料卡方式展示关键初始化、寄存器与兼容性说明。"))
        else:
            self.selection_body_label.setText(self.current_chip.get("description", "点击左侧模块、信号或引脚，可查看更细的芯片数据。"))
        self._set_detail_html(self._chip_overview_html(self.current_chip))
        self.status_label.setText(f"已加载 {self.current_chip['display_name']}")
        QTimer.singleShot(0, self._apply_home_view)

    def _update_hover_status(self, pin_number: int) -> None:
        if self.current_chip is None:
            return
        pins = self.current_chip.get("pins", [])
        if pin_number < 1 or pin_number > len(pins):
            return
        pin = pins[pin_number - 1]
        self.status_label.setText(f"{self._pin_reference(pin)} · {pin['label']}")

    def activate_pin_from_canvas(self, pin_number: int) -> None:
        if self.current_chip is None or pin_number < 1 or pin_number > len(self.current_chip.get("pins", [])):
            return
        self.tabs.setCurrentWidget(self.pin_list)
        for index in range(self.pin_list.count()):
            item = self.pin_list.item(index)
            pin = item.data(Qt.ItemDataRole.UserRole)
            if pin["pin_number"] == pin_number:
                self.pin_list.setCurrentItem(item)
                self.pin_list.scrollToItem(item)
                return

    def select_module_by_id(self, module_id: str) -> bool:
        self.tabs.setCurrentWidget(self.module_list)
        for index in range(self.module_list.count()):
            item = self.module_list.item(index)
            module = item.data(Qt.ItemDataRole.UserRole)
            if module["id"] == module_id:
                self.module_list.setCurrentItem(item)
                self.module_list.scrollToItem(item)
                return True
        return False

    def select_pin_by_number(self, pin_number: int) -> bool:
        self.tabs.setCurrentWidget(self.pin_list)
        for index in range(self.pin_list.count()):
            item = self.pin_list.item(index)
            pin = item.data(Qt.ItemDataRole.UserRole)
            if pin["pin_number"] == pin_number:
                self.pin_list.setCurrentItem(item)
                self.pin_list.scrollToItem(item)
                return True
        return False


class ChipSelectionDialog(QDialog):
    def __init__(
        self,
        all_chips: list[dict],
        deleted_chip_ids: list[str] | None = None,
        current_chip_id: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("芯片选项")
        self.setWindowIcon(create_chip_icon())
        self.setModal(True)
        self.resize(620, 500)
        self.all_chips = list(all_chips)
        self.initial_deleted_chip_ids = set(deleted_chip_ids or [])
        self.deleted_chip_ids = set(deleted_chip_ids or [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("管理芯片库")
        title.setObjectName("DialogTitle")
        subtitle = QLabel("可以切换芯片型号，也可以把不需要的芯片从当前芯片库中删除。删除后会从程序库中移除，直到点击“恢复全部”。")
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setWordWrap(True)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("筛选型号 / 厂商 / 类型 / 封装")
        self.search_edit.textChanged.connect(self._populate_list)

        self.type_list_widget = QListWidget()
        self.type_list_widget.setMinimumWidth(170)
        self.type_list_widget.setMaximumWidth(220)
        self.type_list_widget.currentItemChanged.connect(self._on_type_changed)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        self.list_widget.currentItemChanged.connect(self._update_preview)

        self.preview_label = QLabel("未选择芯片")
        self.preview_label.setObjectName("DialogPreview")
        self.preview_label.setWordWrap(True)

        self.count_label = QLabel("")
        self.count_label.setObjectName("MutedLabel")

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.delete_button = QPushButton("删除出库")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restore_button = QPushButton("恢复全部")
        self.restore_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self._delete_current_chip)
        self.restore_button.clicked.connect(self._restore_all_chips)
        action_row.addWidget(self.delete_button)
        action_row.addWidget(self.restore_button)
        action_row.addStretch(1)

        self.manage_hint_label = QLabel("删除或恢复会在点击“确定”后写入当前芯片库。")
        self.manage_hint_label.setObjectName("MutedLabel")
        self.manage_hint_label.setWordWrap(True)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.count_label)
        selector_row = QHBoxLayout()
        selector_row.setSpacing(10)
        selector_row.addWidget(self.type_list_widget, 0)
        selector_row.addWidget(self.list_widget, 1)
        layout.addLayout(selector_row, 1)
        layout.addWidget(self.preview_label)
        layout.addLayout(action_row)
        layout.addWidget(self.manage_hint_label)
        layout.addWidget(button_box)

        self._populate_list()
        self._select_chip(current_chip_id)

    def _visible_chips(self, query: str = "") -> list[dict]:
        visible = [chip for chip in self.all_chips if chip.get("chip_id", "") not in self.deleted_chip_ids]
        if not query:
            return visible
        filtered = []
        for chip in visible:
            haystack = " ".join(
                [
                    chip.get("display_name", ""),
                    chip.get("vendor", ""),
                    chip.get("package", ""),
                    chip.get("model", ""),
                    " ".join(chip.get("variants", [])),
                    chip.get("category", ""),
                    chip.get("family", ""),
                    chip.get("series", ""),
                    chip.get("chip_role", ""),
                    chip.get("description", ""),
                    " ".join(chip.get("features", [])),
                ]
            ).casefold()
            if query in haystack:
                filtered.append(chip)
        return filtered

    def _grouped_visible_chips(self, query: str = "") -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = defaultdict(list)
        for chip in self._visible_chips(query):
            groups[chip_type_label(chip)].append(chip)
        return dict(sorted(groups.items(), key=lambda item: chip_type_sort_key(item[0])))

    def _current_type_label(self) -> str:
        item = self.type_list_widget.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _select_type(self, type_label: str) -> None:
        if not type_label:
            return
        for index in range(self.type_list_widget.count()):
            item = self.type_list_widget.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == type_label:
                self.type_list_widget.setCurrentItem(item)
                self._on_type_changed()
                return

    def _populate_type_list(self, groups: dict[str, list[dict]], preferred_type: str = "") -> None:
        self.type_list_widget.blockSignals(True)
        self.type_list_widget.clear()
        for type_label, chips in groups.items():
            item = QListWidgetItem(f"{type_label}\n{len(chips)} 款芯片")
            item.setData(Qt.ItemDataRole.UserRole, type_label)
            self.type_list_widget.addItem(item)
        self.type_list_widget.blockSignals(False)
        if preferred_type:
            self._select_type(preferred_type)
        if self.type_list_widget.count() > 0 and self.type_list_widget.currentItem() is None:
            self.type_list_widget.setCurrentRow(0)

    def _populate_chip_list(self, groups: dict[str, list[dict]], preferred_chip_id: str = "") -> None:
        selected_type = self._current_type_label()
        chips = groups.get(selected_type, [])
        self.list_widget.clear()
        for chip in chips:
            type_label = chip_type_label(chip)
            text = f"{chip['display_name']}\n{type_label} · {chip['vendor']} · {chip['package']}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, chip)
            item.setToolTip(chip.get("source_pdf_name", ""))
            self.list_widget.addItem(item)
        if preferred_chip_id and any(chip.get("chip_id") == preferred_chip_id for chip in chips):
            self._select_chip(preferred_chip_id)
        if self.list_widget.count() > 0 and self.list_widget.currentItem() is None:
            self.list_widget.setCurrentRow(0)

    def _populate_list(self) -> None:
        query = self.search_edit.text().strip().casefold()
        current_chip = self.current_chip()
        preferred_chip_id = current_chip.get("chip_id", "") if current_chip else ""
        preferred_type = chip_type_label(current_chip) if current_chip else self._current_type_label()
        groups = self._grouped_visible_chips(query)
        self._populate_type_list(groups, preferred_type)
        self._populate_chip_list(groups, preferred_chip_id)
        self.count_label.setText(
            f"类型 {len(groups)} · 可见 {len([chip for chip in self.all_chips if chip.get('chip_id', '') not in self.deleted_chip_ids])} · "
            f"已删除 {len(self.deleted_chip_ids)} · 总计 {len(self.all_chips)}"
        )
        self.restore_button.setEnabled(bool(self.deleted_chip_ids))
        self.delete_button.setEnabled(self.list_widget.count() > 0)
        self.ok_button.setEnabled(self.list_widget.count() > 0)
        if self.list_widget.count() == 0:
            self.preview_label.setText("当前类型下没有可见芯片。可以切换类型，或点击“恢复全部”把已删除芯片重新加入当前芯片库。")

    def _on_type_changed(self, *_args) -> None:
        query = self.search_edit.text().strip().casefold()
        groups = self._grouped_visible_chips(query)
        self._populate_chip_list(groups)

    def _select_chip(self, chip_id: str) -> None:
        if not chip_id:
            return
        chip_record = next(
            (
                chip
                for chip in self.all_chips
                if chip.get("chip_id") == chip_id and chip.get("chip_id", "") not in self.deleted_chip_ids
            ),
            None,
        )
        if chip_record is not None:
            self._select_type(chip_type_label(chip_record))
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            chip = item.data(Qt.ItemDataRole.UserRole)
            if chip.get("chip_id") == chip_id:
                self.list_widget.setCurrentItem(item)
                return

    def _update_preview(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            self.preview_label.setText("未选择芯片")
            self.delete_button.setEnabled(False)
            self.ok_button.setEnabled(False)
            return
        chip = item.data(Qt.ItemDataRole.UserRole)
        module_count = len(chip.get("modules", []))
        signal_count = len(chip.get("signals", []))
        category = chip_type_label(chip)
        role = chip.get("chip_role", "")
        self.delete_button.setEnabled(True)
        self.ok_button.setEnabled(True)
        self.preview_label.setText(
            f"{chip['display_name']} · {category}\n"
            f"{chip['vendor']} · {role} · {chip['package']}\n"
            f"引脚数 {chip['pin_count']} · 模块 {module_count} · 信号 {signal_count}\n"
            f"来源: {chip.get('source_pdf_name', '')}\n"
            f"{chip.get('description', '')}"
        )

    def _delete_current_chip(self) -> None:
        chip = self.current_chip()
        if chip is None:
            return
        button = QMessageBox.question(
            self,
            APP_NAME,
            f"删除后，这颗芯片会从当前芯片库中移除。\n\n确认删除 {chip['display_name']} 吗？",
        )
        if button != QMessageBox.StandardButton.Yes:
            return
        self.deleted_chip_ids.add(chip["chip_id"])
        self._populate_list()

    def _restore_all_chips(self) -> None:
        if not self.deleted_chip_ids:
            return
        button = QMessageBox.question(
            self,
            APP_NAME,
            "这会把已删除的芯片重新加入当前芯片库。\n\n确认恢复全部芯片吗？",
        )
        if button != QMessageBox.StandardButton.Yes:
            return
        self.deleted_chip_ids.clear()
        self._populate_list()

    def current_chip(self) -> dict | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def deleted_chip_ids_list(self) -> list[str]:
        return sorted(self.deleted_chip_ids)

    def hidden_chip_ids_list(self) -> list[str]:
        return self.deleted_chip_ids_list()

    def visibility_changed(self) -> bool:
        return self.deleted_chip_ids != self.initial_deleted_chip_ids


def _pump_events(app: QApplication, duration_ms: int = 120) -> None:
    deadline = time.perf_counter() + duration_ms / 1000.0
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def perform_self_test(report_path: str | None = None, screenshot_path: str | None = None, chip_id: str = "") -> dict:
    app = ensure_application()
    app.setQuitOnLastWindowClosed(False)

    library = load_raw_chip_library()
    with tempfile.TemporaryDirectory() as temp_dir:
        window = ChipLibraryWindow(library=library, test_mode=True)
        window.show()
        _pump_events(app, 180)

        chips = window.chips
        initial_chip_id = chip_id or (chips[0]["chip_id"] if chips else "")
        dialog = ChipSelectionDialog(window.raw_library.get("chips", []), window.hidden_chip_ids, initial_chip_id, window)
        dialog_count = dialog.list_widget.count()
        if chips:
            dialog._select_chip(initial_chip_id)
            selected_chip = dialog.current_chip()
            if selected_chip is not None:
                window.load_chip(selected_chip["chip_id"])
        _pump_events(app, 120)

        gpio_selected = False
        detail_pin_selected = False
        if window.current_chip and window.current_chip.get("pins"):
            module_ids = [module.get("id", "") for module in window.current_chip.get("modules", [])]
            preferred_module = "gpio" if "gpio" in module_ids else (module_ids[0] if module_ids else "")
            target_pin_number = 30 if any(pin.get("pin_number") == 30 for pin in window.current_chip.get("pins", [])) else window.current_chip["pins"][0]["pin_number"]
            gpio_selected = window.select_module_by_id(preferred_module) if preferred_module else False
            _pump_events(app, 120)
            detail_pin_selected = window.select_pin_by_number(target_pin_number)
            _pump_events(app, 120)
            if not detail_pin_selected:
                window.activate_pin_from_canvas(target_pin_number)
                _pump_events(app, 120)
        window.zoom_in()
        _pump_events(app, 120)
        detail_html = window.pin_detail_browser.toPlainText()
        if not detail_pin_selected and window.current_chip and window.current_chip.get("pins"):
            pin_ref = window.current_chip["pins"][0].get("pin_ref", f"P{window.current_chip['pins'][0]['pin_number']}")
            detail_pin_selected = f"P{target_pin_number}" in detail_html or pin_ref in detail_html or "SMCLK5" in detail_html

        screenshot_file = Path(screenshot_path or (Path(temp_dir) / "ec_chip_library.png"))
        screenshot_ok = window.grab().save(str(screenshot_file), "PNG")

        report = {
            "chip_count": len(chips),
            "dialog_chip_count": dialog_count,
            "selected_chip": window.current_chip["chip_id"] if window.current_chip else "",
            "view_type": window.current_chip.get("view_type", "") if window.current_chip else "",
            "pin_count": window.current_chip["pin_count"] if window.current_chip else 0,
            "module_count": len(window.current_chip.get("modules", [])) if window.current_chip else 0,
            "signal_count": len(window.current_chip.get("signals", [])) if window.current_chip else 0,
            "menu_has_chip_option": window.chip_options_action.text() == "芯片选项",
            "gpio_selected": gpio_selected,
            "detail_pin_selected": detail_pin_selected,
            "detail_has_1_8v": "1.8V" in detail_html,
            "detail_has_3_3v": "3.3V" in detail_html,
            "detail_has_rxec": "RXEC[2]" in detail_html,
            "detail_has_chinese": any("\u4e00" <= character <= "\u9fff" for character in detail_html),
            "highlight_count": len(window.canvas.highlight_pins),
            "zoom": round(window.canvas.zoom, 2),
            "screenshot_created": screenshot_ok and screenshot_file.exists(),
        }

        if report_path:
            Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        app.processEvents()
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--self-test", action="store_true", help="执行界面自检并退出")
    parser.add_argument("--report", default="", help="自检报告输出路径")
    parser.add_argument("--screenshot", default="", help="自检截图输出路径")
    parser.add_argument("--chip-id", default="", help="自检时指定要加载的芯片 ID")
    args = parser.parse_args(argv)

    app = ensure_application()
    if args.self_test:
        try:
            perform_self_test(args.report or None, args.screenshot or None, args.chip_id)
        except Exception:
            error_path = Path(args.report).with_suffix(".error.txt") if args.report else Path.cwd() / "ec_chip_library_self_test.error.txt"
            error_path.write_text(traceback.format_exc(), encoding="utf-8")
            raise
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    window = ChipLibraryWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
