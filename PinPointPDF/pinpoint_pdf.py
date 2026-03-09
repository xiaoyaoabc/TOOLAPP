import argparse
import ctypes
import json
import os
import re
import struct
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import fitz
from PyQt6.QtCore import (
    QByteArray,
    QBuffer,
    QEvent,
    QIODevice,
    QMargins,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    QStringListModel,
    QThread,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStyledItemDelegate,
    QStyle,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "PinPoint PDF"
APP_TITLE = "PinPoint PDF - 硬件引脚极速定位器"
APP_ID = "xyabc.pinpointpdf"
DEFAULT_QUERY = "SYS_RST#"
DEFAULT_ZOOM = 1.35
MIN_ZOOM = 0.35
MAX_ZOOM = 5.5
CACHE_LIMIT = 16
SEARCH_HISTORY_LIMIT = 20
RECENT_FILES_LIMIT = 8
SUGGESTION_LIMIT = 1200
RESULT_LIMIT = 2000

SIGNAL_STOPWORDS = {
    "AND", "AUDIO", "BGA", "BI", "CHANNEL", "CHIP", "CPU", "DATE", "DDR", "DIMM",
    "FAN", "FLASH", "GEN", "HEADER", "HDMI", "IC", "IN", "IT", "LANE", "LINE",
    "NAME", "OF", "OUT", "PAGE", "PIN", "PORT", "PROJECT", "REV", "SATA", "SHEET",
    "SIZE", "SPI", "SYSTEM", "TITLE", "TYPE", "USB", "WITH",
}

RectTuple = tuple[float, float, float, float]


@dataclass
class SearchOptions:
    case_sensitive: bool = False
    whole_word: bool = False


@dataclass
class WordEntry:
    text: str
    rect: RectTuple
    folded: str
    compact: str
    raw_alnum: str
    line_key: tuple[int, int]
    context: str = ""


@dataclass
class SearchHit:
    page_number: int
    text: str
    rect: RectTuple
    context: str
    match_type: str
    score: int


@dataclass
class PageIndex:
    page_number: int
    size: tuple[float, float]
    words: list[WordEntry] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


@dataclass
class DocumentIndex:
    pdf_path: str
    page_count: int
    pages: list[PageIndex] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def truncate(text: str, limit: int = 96) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def rect_to_tuple(rect: fitz.Rect | QRectF | RectTuple) -> RectTuple:
    if isinstance(rect, tuple):
        return tuple(float(value) for value in rect)
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def tuple_to_rect(rect: RectTuple) -> fitz.Rect:
    return fitz.Rect(rect[0], rect[1], rect[2], rect[3])


def compact_token(text: str, case_sensitive: bool = False) -> str:
    compact = re.sub(r"[^A-Za-z0-9]+", "", text)
    return compact if case_sensitive else compact.casefold()


def signal_priority(token: str, count: int = 1) -> int:
    score = 0
    if "#" in token:
        score += 5
    if "_" in token:
        score += 4
    if "/" in token:
        score += 2
    if any(char.isdigit() for char in token):
        score += 2
    if re.search(r"[A-Z]{3,}", token):
        score += 2
    if len(token) <= 20:
        score += 1
    score += min(6, count)
    return score


def is_signal_candidate(token: str) -> bool:
    text = token.strip()
    if len(text) < 3 or len(text) > 64:
        return False
    if text.upper() in SIGNAL_STOPWORDS:
        return False
    if re.fullmatch(r"[RCLDQUJPFBT]\d+[A-Z]?", text.upper()):
        return False
    if re.fullmatch(r"[A-Z]\d{4}", text.upper()):
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?(?:V|K|M|A|MA|UA|UF|NF|PF|MB|GB|MHZ|KHZ|HZ)", text.upper()):
        return False

    alpha_chars = [char for char in text if char.isalpha()]
    upper_ratio = (sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)) if alpha_chars else 0.0
    has_signal_delimiter = any(char in text for char in "_#/+-")
    has_mix = bool(re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", text))
    has_upper_block = bool(re.search(r"[A-Z]{2,}", text))
    if not (has_signal_delimiter or has_mix or has_upper_block):
        return False
    if upper_ratio < 0.55 and not has_signal_delimiter:
        return False
    return True


def classify_match(entry: WordEntry, query: str, options: SearchOptions) -> tuple[int, str]:
    raw_query = query if options.case_sensitive else query.casefold()
    raw_text = entry.text if options.case_sensitive else entry.folded
    compact_query = compact_token(query, case_sensitive=options.case_sensitive)
    compact_text = entry.raw_alnum if options.case_sensitive else entry.compact

    if options.whole_word:
        if raw_text == raw_query:
            return 500, "精确"
        if compact_query and compact_text == compact_query:
            return 460, "归一化"
        return 0, ""

    if raw_text == raw_query:
        return 450, "精确"
    if compact_query and compact_text == compact_query:
        return 420, "归一化"
    if raw_query and raw_query in raw_text:
        return 320, "包含"
    if compact_query and compact_query in compact_text:
        return 280, "模糊"
    return 0, ""


def sort_hits(hits: list[SearchHit]) -> list[SearchHit]:
    return sorted(hits, key=lambda hit: (-hit.score, hit.page_number, hit.rect[1], hit.rect[0], hit.text.casefold()))


def group_hits_by_page(hits: list[SearchHit]) -> dict[int, list[SearchHit]]:
    grouped: dict[int, list[SearchHit]] = defaultdict(list)
    for hit in hits:
        grouped[hit.page_number].append(hit)
    for page_hits in grouped.values():
        page_hits.sort(key=lambda hit: (hit.rect[1], hit.rect[0], -hit.score, hit.text.casefold()))
    return dict(grouped)


def extract_context_for_rect(words: list[WordEntry], rect: RectTuple) -> str:
    target = tuple_to_rect(rect)
    overlaps = [entry.context for entry in words if tuple_to_rect(entry.rect).intersects(target)]
    if overlaps:
        return overlaps[0]

    target_center = ((target.x0 + target.x1) * 0.5, (target.y0 + target.y1) * 0.5)
    best_context = ""
    best_distance = float("inf")
    for entry in words:
        word_rect = tuple_to_rect(entry.rect)
        word_center = ((word_rect.x0 + word_rect.x1) * 0.5, (word_rect.y0 + word_rect.y1) * 0.5)
        distance = abs(word_center[0] - target_center[0]) + abs(word_center[1] - target_center[1])
        if distance < best_distance:
            best_distance = distance
            best_context = entry.context
    return best_context


def build_page_index(page_number: int, page: fitz.Page) -> tuple[PageIndex, Counter]:
    raw_words = sorted(
        page.get_text("words"),
        key=lambda item: (
            int(item[5]) if len(item) > 5 else 0,
            int(item[6]) if len(item) > 6 else 0,
            int(item[7]) if len(item) > 7 else 0,
            float(item[1]),
            float(item[0]),
        ),
    )

    line_tokens: dict[tuple[int, int], list[tuple[int, str]]] = defaultdict(list)
    entries: list[WordEntry] = []

    for index, raw in enumerate(raw_words):
        if len(raw) < 5:
            continue
        text = str(raw[4]).strip()
        if not text:
            continue

        block_no = int(raw[5]) if len(raw) > 5 else 0
        line_no = int(raw[6]) if len(raw) > 6 else 0
        word_no = int(raw[7]) if len(raw) > 7 else index
        line_key = (block_no, line_no)

        entries.append(
            WordEntry(
                text=text,
                rect=(float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])),
                folded=text.casefold(),
                compact=compact_token(text),
                raw_alnum=compact_token(text, case_sensitive=True),
                line_key=line_key,
            )
        )
        line_tokens[line_key].append((word_no, text))

    line_texts = {key: " ".join(text for _, text in sorted(values)).strip() for key, values in line_tokens.items()}
    for entry in entries:
        entry.context = line_texts.get(entry.line_key, entry.text)

    signal_counter: Counter = Counter()
    for entry in entries:
        if is_signal_candidate(entry.text):
            signal_counter[entry.text] += 1

    signals = [
        term
        for term, _count in sorted(signal_counter.items(), key=lambda item: (-signal_priority(item[0], item[1]), -item[1], item[0]))[:80]
    ]

    return PageIndex(page_number=page_number, size=(float(page.rect.width), float(page.rect.height)), words=entries, signals=signals), signal_counter


def build_document_index(pdf_path: str, progress_cb: Callable[[int, int], None] | None = None, cancel_cb: Callable[[], bool] | None = None) -> DocumentIndex | None:
    pages: list[PageIndex] = []
    global_counter: Counter = Counter()
    doc = fitz.open(pdf_path)
    try:
        total = len(doc)
        for page_number in range(total):
            if cancel_cb and cancel_cb():
                return None
            page = doc.load_page(page_number)
            page_index, signal_counter = build_page_index(page_number, page)
            pages.append(page_index)
            global_counter.update(signal_counter)
            if progress_cb:
                progress_cb(page_number + 1, total)
    finally:
        doc.close()

    suggestions = [
        term
        for term, _count in sorted(global_counter.items(), key=lambda item: (-signal_priority(item[0], item[1]), -item[1], item[0]))[:SUGGESTION_LIMIT]
    ]
    return DocumentIndex(pdf_path=os.path.abspath(pdf_path), page_count=len(pages), pages=pages, suggestions=suggestions)


def search_page_index(page_index: PageIndex, query: str, options: SearchOptions) -> list[SearchHit]:
    hits: list[SearchHit] = []
    seen: set[RectTuple] = set()
    for entry in page_index.words:
        score, match_type = classify_match(entry, query, options)
        if not score or entry.rect in seen:
            continue
        seen.add(entry.rect)
        hits.append(SearchHit(page_number=page_index.page_number, text=entry.text, rect=entry.rect, context=entry.context, match_type=match_type, score=score))
    return hits


def search_index(document_index: DocumentIndex, query: str, options: SearchOptions) -> list[SearchHit]:
    query = query.strip()
    if not query:
        return []
    hits: list[SearchHit] = []
    for page_index in document_index.pages:
        hits.extend(search_page_index(page_index, query, options))
    return sort_hits(hits)[:RESULT_LIMIT]


def search_pdf_direct(pdf_path: str, query: str, options: SearchOptions, cancel_cb: Callable[[], bool] | None = None) -> list[SearchHit]:
    query = query.strip()
    if not query:
        return []

    hits: list[SearchHit] = []
    doc = fitz.open(pdf_path)
    try:
        for page_number in range(len(doc)):
            if cancel_cb and cancel_cb():
                return []
            page = doc.load_page(page_number)
            page_index, _signal_counter = build_page_index(page_number, page)
            page_hits = search_page_index(page_index, query, options)
            if not page_hits and " " in query:
                for rect in page.search_for(query):
                    rect_tuple = rect_to_tuple(rect)
                    page_hits.append(SearchHit(page_number=page_number, text=query, rect=rect_tuple, context=extract_context_for_rect(page_index.words, rect_tuple) or query, match_type="短语", score=400))
            hits.extend(page_hits)
            if len(hits) >= RESULT_LIMIT * 2:
                break
    finally:
        doc.close()
    return sort_hits(hits)[:RESULT_LIMIT]


def set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def _stroke_pen(color: QColor, size: int, width_scale: float = 8.5) -> QPen:
    pen = QPen(color)
    pen.setWidthF(max(1.4, size / width_scale))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def create_symbol_icon(kind: str, size: int = 20, color: QColor | None = None) -> QIcon:
    color = color or QColor(31, 76, 96)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = _stroke_pen(color, size)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    box = QRectF(2.0, 2.0, size - 4.0, size - 4.0)

    if kind == "open":
        painter.drawRoundedRect(QRectF(2.0, 7.0, size - 4.0, size - 8.0), 3.0, 3.0)
        painter.drawLine(QPointF(5.0, 7.0), QPointF(size * 0.38, 3.5))
        painter.drawLine(QPointF(size * 0.38, 3.5), QPointF(size - 5.0, 3.5))
    elif kind == "history":
        painter.drawEllipse(QRectF(3.5, 3.5, size - 7.0, size - 7.0))
        painter.drawLine(QPointF(size / 2, size / 2), QPointF(size / 2, 6.0))
        painter.drawLine(QPointF(size / 2, size / 2), QPointF(size * 0.72, size * 0.62))
    elif kind == "close":
        painter.drawRoundedRect(box, 3.0, 3.0)
        painter.drawLine(QPointF(6.0, 6.0), QPointF(size - 6.0, size - 6.0))
        painter.drawLine(QPointF(size - 6.0, 6.0), QPointF(6.0, size - 6.0))
    elif kind == "search":
        painter.drawEllipse(QRectF(3.0, 3.0, size * 0.56, size * 0.56))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size - 4.0, size - 4.0))
    elif kind == "prev":
        painter.drawLine(QPointF(size * 0.68, 4.5), QPointF(size * 0.34, size / 2))
        painter.drawLine(QPointF(size * 0.34, size / 2), QPointF(size * 0.68, size - 4.5))
    elif kind == "next":
        painter.drawLine(QPointF(size * 0.32, 4.5), QPointF(size * 0.66, size / 2))
        painter.drawLine(QPointF(size * 0.66, size / 2), QPointF(size * 0.32, size - 4.5))
    elif kind == "fit_width":
        painter.drawRoundedRect(QRectF(4.0, 5.0, size - 8.0, size - 10.0), 2.0, 2.0)
        painter.drawLine(QPointF(3.0, size / 2), QPointF(7.0, size / 2))
        painter.drawLine(QPointF(size - 3.0, size / 2), QPointF(size - 7.0, size / 2))
        painter.drawLine(QPointF(7.0, size / 2), QPointF(5.0, size / 2 - 2.0))
        painter.drawLine(QPointF(7.0, size / 2), QPointF(5.0, size / 2 + 2.0))
        painter.drawLine(QPointF(size - 7.0, size / 2), QPointF(size - 5.0, size / 2 - 2.0))
        painter.drawLine(QPointF(size - 7.0, size / 2), QPointF(size - 5.0, size / 2 + 2.0))
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
    elif kind == "zoom_in":
        painter.drawEllipse(QRectF(3.0, 3.0, size * 0.56, size * 0.56))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size - 4.0, size - 4.0))
        painter.drawLine(QPointF(size * 0.31, size * 0.31), QPointF(size * 0.31, size * 0.53))
        painter.drawLine(QPointF(size * 0.2, size * 0.42), QPointF(size * 0.42, size * 0.42))
    elif kind == "zoom_out":
        painter.drawEllipse(QRectF(3.0, 3.0, size * 0.56, size * 0.56))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size - 4.0, size - 4.0))
        painter.drawLine(QPointF(size * 0.2, size * 0.42), QPointF(size * 0.42, size * 0.42))
    elif kind == "favorite":
        points = [QPointF(size * 0.5, 3.0), QPointF(size * 0.62, size * 0.36), QPointF(size - 3.0, size * 0.36), QPointF(size * 0.7, size * 0.58), QPointF(size * 0.8, size - 3.0), QPointF(size * 0.5, size * 0.74), QPointF(size * 0.2, size - 3.0), QPointF(size * 0.3, size * 0.58), QPointF(3.0, size * 0.36), QPointF(size * 0.38, size * 0.36)]
        painter.drawPolygon(QPolygonF(points))
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

    sheet = QRectF(size * 0.2, size * 0.14, size * 0.42, size * 0.64)
    fold = QRectF(sheet.right() - size * 0.11, sheet.top(), size * 0.11, size * 0.11)
    painter.setBrush(QColor(250, 252, 253, 238))
    painter.drawRoundedRect(sheet, size * 0.06, size * 0.06)
    painter.setBrush(QColor(223, 233, 238, 220))
    painter.drawPolygon(QPolygonF([QPointF(fold.left(), fold.top()), QPointF(fold.right(), fold.top()), QPointF(fold.right(), fold.bottom())]))

    painter.setPen(QPen(QColor(41, 98, 117), max(2.0, size * 0.03), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    for y_factor in (0.28, 0.42, 0.56):
        y_pos = size * y_factor
        painter.drawLine(QPointF(size * 0.26, y_pos), QPointF(size * 0.54, y_pos))
        painter.drawEllipse(QPointF(size * 0.31, y_pos), size * 0.012, size * 0.012)
        painter.drawEllipse(QPointF(size * 0.54, y_pos), size * 0.012, size * 0.012)

    pin_center = QPointF(size * 0.74, size * 0.56)
    painter.setBrush(QColor(255, 244, 232))
    painter.setPen(QPen(QColor(255, 244, 232), max(2.0, size * 0.03)))
    painter.drawEllipse(pin_center, size * 0.12, size * 0.12)
    painter.setBrush(QColor(241, 168, 62))
    painter.setPen(QPen(QColor(241, 168, 62), max(2.0, size * 0.03)))
    painter.drawEllipse(pin_center, size * 0.055, size * 0.055)

    pin_path = QPainterPath()
    pin_path.moveTo(pin_center.x(), size * 0.92)
    pin_path.lineTo(size * 0.66, size * 0.69)
    pin_path.lineTo(size * 0.82, size * 0.69)
    pin_path.closeSubpath()
    painter.drawPath(pin_path)
    painter.end()
    return pixmap


def create_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw_app_icon_pixmap(size))
    return icon


def pixmap_to_png_bytes(pixmap: QPixmap) -> bytes:
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(byte_array)


def write_ico_from_icon(icon: QIcon, path: Path) -> None:
    sizes = (16, 24, 32, 48, 64, 128, 256)
    png_blobs: list[bytes] = []
    entries: list[bytes] = []
    offset = 6 + len(sizes) * 16
    for size in sizes:
        png = pixmap_to_png_bytes(icon.pixmap(QSize(size, size)))
        png_blobs.append(png)
        width_byte = 0 if size >= 256 else size
        height_byte = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", width_byte, height_byte, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    with open(path, "wb") as fp:
        fp.write(struct.pack("<HHH", 0, 1, len(sizes)))
        fp.write(b"".join(entries))
        fp.write(b"".join(png_blobs))


def export_icon_assets(output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    icon = create_app_icon()
    png_path = output_path / "app_icon.png"
    ico_path = output_path / "app_icon.ico"
    icon.pixmap(QSize(256, 256)).save(str(png_path), "PNG")
    write_ico_from_icon(icon, ico_path)
    return {"png": str(png_path), "ico": str(ico_path)}

class IndexWorker(QThread):
    progressChanged = pyqtSignal(int, int)
    completed = pyqtSignal(object, float)
    failed = pyqtSignal(str)

    def __init__(self, pdf_path: str):
        super().__init__()
        self.pdf_path = pdf_path

    def run(self) -> None:
        started = time.perf_counter()
        try:
            index = build_document_index(
                self.pdf_path,
                progress_cb=lambda current, total: self.progressChanged.emit(current, total),
                cancel_cb=self.isInterruptionRequested,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        if self.isInterruptionRequested() or index is None:
            return
        self.completed.emit(index, (time.perf_counter() - started) * 1000.0)


class SearchWorker(QThread):
    completed = pyqtSignal(object, float)
    failed = pyqtSignal(str)

    def __init__(self, pdf_path: str, query: str, options: SearchOptions):
        super().__init__()
        self.pdf_path = pdf_path
        self.query = query
        self.options = options

    def run(self) -> None:
        started = time.perf_counter()
        try:
            hits = search_pdf_direct(self.pdf_path, self.query, self.options, cancel_cb=self.isInterruptionRequested)
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        if self.isInterruptionRequested():
            return
        self.completed.emit(hits, (time.perf_counter() - started) * 1000.0)


class HistoryComboDelegate(QStyledItemDelegate):
    def __init__(self, kind_role: int, history_kind: str, clear_kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind_role = kind_role
        self.history_kind = history_kind
        self.clear_kind = clear_kind

    @staticmethod
    def trash_rect(option_rect: QRect) -> QRect:
        size = 14
        margin = 8
        x = option_rect.right() - margin - size + 1
        y = option_rect.top() + (option_rect.height() - size) // 2
        return QRect(x, y, size, size)

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        kind = index.data(self.kind_role)
        if kind != self.history_kind:
            return
        icon_rect = self.trash_rect(option.rect)
        icon = option.widget.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        icon.paint(painter, icon_rect)


class PdfCanvas(QPdfView):
    selectionFinished = pyqtSignal(object)
    zoomRequested = pyqtSignal(float)
    resized = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pdf_document = QPdfDocument(self)
        self.setDocument(self._pdf_document)
        self._page_sizes: list[tuple[float, float]] = []
        self._highlight_hits: list[SearchHit] = []
        self._selected_hit: SearchHit | None = None
        self.current_page = 0
        self.render_zoom = 0.0
        self.target_zoom = 0.0
        self.pdf_size = (0.0, 0.0)

        self._selection_origin: QPoint | None = None
        self._selection_rect = QRect()
        self._panning = False
        self._pan_origin = QPoint()

        self.setObjectName("PdfCanvas")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setPageMode(QPdfView.PageMode.SinglePage)
        self.setZoomMode(QPdfView.ZoomMode.Custom)
        self.setZoomFactor(DEFAULT_ZOOM)
        self.setPageSpacing(0)
        self.setDocumentMargins(QMargins(12, 12, 12, 12))
        self.viewport().setMouseTracking(True)
        self.horizontalScrollBar().valueChanged.connect(lambda _value: self.viewport().update())
        self.verticalScrollBar().valueChanged.connect(lambda _value: self.viewport().update())

    def load_document(self, pdf_path: str, page_sizes: list[tuple[float, float]]) -> str | None:
        self.clear_document()
        error = self._pdf_document.load(pdf_path)
        if error != QPdfDocument.Error.None_:
            return error.name
        self._page_sizes = list(page_sizes)
        self.current_page = 0
        self.pdf_size = self._page_sizes[0] if self._page_sizes else (0.0, 0.0)
        self.render_zoom = DEFAULT_ZOOM
        self.target_zoom = DEFAULT_ZOOM
        self.setZoomMode(QPdfView.ZoomMode.Custom)
        self.setZoomFactor(DEFAULT_ZOOM)
        self.pageNavigator().clear()
        self.pageNavigator().jump(0, QPointF(0.0, 0.0), 0.0)
        self.viewport().update()
        return None

    def clear_document(self) -> None:
        self.pageNavigator().clear()
        self._pdf_document.close()
        self._page_sizes.clear()
        self._highlight_hits.clear()
        self._selected_hit = None
        self.current_page = 0
        self.render_zoom = 0.0
        self.target_zoom = 0.0
        self.pdf_size = (0.0, 0.0)
        self.viewport().update()

    def has_page(self) -> bool:
        return self._pdf_document.pageCount() > 0 and self.render_zoom > 0.0

    def set_highlights(self, hits: list[SearchHit], selected_hit: SearchHit | None) -> None:
        self._highlight_hits = list(hits)
        self._selected_hit = selected_hit
        self.viewport().update()

    def set_view_state(
        self,
        page_number: int,
        pdf_size: tuple[float, float],
        zoom: float,
        hits: list[SearchHit],
        selected_hit: SearchHit | None,
        focus_rect: RectTuple | None = None,
        center_point: tuple[float, float] | None = None,
    ) -> None:
        if self._pdf_document.pageCount() <= 0:
            return

        page_number = int(clamp(page_number, 0, self._pdf_document.pageCount() - 1))
        previous_page = self.pageNavigator().currentPage()
        previous_location = self._current_location_pdf() if previous_page == page_number else QPointF(0.0, 0.0)

        self.current_page = page_number
        self.pdf_size = pdf_size
        self.render_zoom = clamp(zoom, MIN_ZOOM, MAX_ZOOM)
        self.target_zoom = self.render_zoom
        self._highlight_hits = list(hits)
        self._selected_hit = selected_hit

        self.setZoomMode(QPdfView.ZoomMode.Custom)
        self.setZoomFactor(self.render_zoom)

        if focus_rect is not None:
            location = self._location_for_center(self._rect_center(focus_rect), self.render_zoom)
        elif center_point is not None:
            location = self._location_for_center(center_point, self.render_zoom)
        else:
            location = self._clamp_location(previous_location, self.render_zoom)

        if previous_page == page_number:
            self.pageNavigator().update(page_number, location, 0.0)
        else:
            self.pageNavigator().jump(page_number, location, 0.0)
        self.viewport().update()

    def fit_width_zoom(self, pdf_size: tuple[float, float]) -> float:
        margins = self.documentMargins()
        width = max(1.0, pdf_size[0])
        available = max(1.0, self.viewport().width() - float(margins.left() + margins.right()) - 8.0)
        return clamp(available / width, MIN_ZOOM, MAX_ZOOM)

    def fit_page_zoom(self, pdf_size: tuple[float, float]) -> float:
        margins = self.documentMargins()
        width = max(1.0, pdf_size[0])
        height = max(1.0, pdf_size[1])
        available_width = max(1.0, self.viewport().width() - float(margins.left() + margins.right()) - 8.0)
        available_height = max(1.0, self.viewport().height() - float(margins.top() + margins.bottom()) - 8.0)
        zoom = min(available_width / width, available_height / height)
        return clamp(zoom, MIN_ZOOM, MAX_ZOOM)

    def apply_preview_zoom(self, target_zoom: float, anchor_pos: QPoint | None = None) -> None:
        if not self.has_page():
            return
        self.target_zoom = clamp(target_zoom, MIN_ZOOM, MAX_ZOOM)
        anchor_point = self._pdf_point_from_view(anchor_pos) if anchor_pos is not None else self.current_center_pdf()
        self.render_zoom = self.target_zoom
        self.setZoomMode(QPdfView.ZoomMode.Custom)
        self.setZoomFactor(self.render_zoom)
        if anchor_point is not None:
            if anchor_pos is not None:
                location = self._location_for_anchor(anchor_point, anchor_pos, self.render_zoom)
            else:
                location = self._location_for_center(anchor_point, self.render_zoom)
            self.pageNavigator().update(self.current_page, location, 0.0)
        self.viewport().update()

    def current_center_pdf(self) -> tuple[float, float] | None:
        if not self.has_page():
            return None
        return self._pdf_point_from_view(self.viewport().rect().center())

    def center_on_pdf_point(self, point: tuple[float, float] | None) -> None:
        if point and self.has_page():
            self.pageNavigator().update(self.current_page, self._location_for_center(point, self.render_zoom), 0.0)
            self.viewport().update()

    def center_on_pdf_rect(self, rect: RectTuple | None) -> None:
        if not rect or not self.has_page():
            return
        self.center_on_pdf_point(self._rect_center(rect))

    def wheelEvent(self, event) -> None:
        if not self.has_page():
            super().wheelEvent(event)
            return
        factor = 1.16 if event.angleDelta().y() > 0 else 1.0 / 1.16
        base = self.target_zoom or self.render_zoom or DEFAULT_ZOOM
        new_zoom = clamp(base * factor, MIN_ZOOM, MAX_ZOOM)
        if abs(new_zoom - base) < 0.001:
            event.accept()
            return
        self.apply_preview_zoom(new_zoom, event.position().toPoint())
        self.zoomRequested.emit(new_zoom)
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self.has_page():
            self._panning = True
            self._pan_origin = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.has_page() and QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
            self._selection_origin = event.pos()
            self._selection_rect = QRect(self._selection_origin, self._selection_origin)
            self.viewport().update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning:
            delta = event.pos() - self._pan_origin
            self._pan_origin = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self._selection_origin is not None:
            self._selection_rect = QRect(self._selection_origin, event.pos()).normalized()
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._selection_origin is not None:
            selection = QRect(self._selection_rect)
            self._selection_origin = None
            self._selection_rect = QRect()
            self.viewport().update()
            if selection.width() >= 4 and selection.height() >= 4 and self.has_page():
                self.selectionFinished.emit(self._viewport_rect_to_pdf(selection))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        viewport_rect = QRectF(self.viewport().rect())

        for index, hit in enumerate(self._highlight_hits, start=1):
            hit_rect = self._pdf_rect_to_viewport(tuple_to_rect(hit.rect))
            if hit_rect.isEmpty() or not hit_rect.intersects(viewport_rect):
                continue
            is_selected = bool(
                self._selected_hit
                and self._selected_hit.page_number == hit.page_number
                and self._selected_hit.rect == hit.rect
                and self._selected_hit.text == hit.text
            )
            line_color = QColor(24, 133, 69) if is_selected else QColor(205, 64, 51)
            fill_color = QColor(24, 133, 69, 40) if is_selected else QColor(205, 64, 51, 34)

            rect_pen = QPen(line_color)
            rect_pen.setWidth(2)
            painter.setPen(rect_pen)
            painter.fillRect(hit_rect, fill_color)
            painter.drawRect(hit_rect)

            label_rect = QRectF(hit_rect.left(), max(0.0, hit_rect.top() - 22.0), 30.0, 18.0)
            painter.fillRect(label_rect, line_color)
            painter.setPen(Qt.GlobalColor.white)
            label_font = QFont("Microsoft YaHei UI", 9)
            label_font.setBold(True)
            painter.setFont(label_font)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, f"#{index}")

        if not self._selection_rect.isNull():
            pen = QPen(QColor(21, 114, 160))
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.fillRect(self._selection_rect, QColor(21, 114, 160, 32))
            painter.drawRect(self._selection_rect)
        painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()

    @staticmethod
    def _rect_center(rect: RectTuple) -> tuple[float, float]:
        target = tuple_to_rect(rect)
        return ((target.x0 + target.x1) * 0.5, (target.y0 + target.y1) * 0.5)

    def _viewport_offsets(self, zoom: float) -> tuple[float, float]:
        margins = self.documentMargins()
        usable_width = max(0.0, self.viewport().width() - float(margins.left() + margins.right()))
        usable_height = max(0.0, self.viewport().height() - float(margins.top() + margins.bottom()))
        page_width = self.pdf_size[0] * zoom
        page_height = self.pdf_size[1] * zoom
        offset_x = max(float(margins.left()), float(margins.left()) + (usable_width - page_width) * 0.5)
        offset_y = max(float(margins.top()), float(margins.top()) + (usable_height - page_height) * 0.5)
        return offset_x, offset_y

    def _clamp_location(self, location: QPointF, zoom: float) -> QPointF:
        visible_width = max(1.0, self.viewport().width() / max(zoom, 0.01))
        visible_height = max(1.0, self.viewport().height() / max(zoom, 0.01))
        max_x = max(0.0, self.pdf_size[0] - visible_width)
        max_y = max(0.0, self.pdf_size[1] - visible_height)
        return QPointF(clamp(location.x(), 0.0, max_x), clamp(location.y(), 0.0, max_y))

    def _location_for_center(self, center_point: tuple[float, float], zoom: float) -> QPointF:
        visible_width = max(1.0, self.viewport().width() / max(zoom, 0.01))
        visible_height = max(1.0, self.viewport().height() / max(zoom, 0.01))
        desired = QPointF(center_point[0] - visible_width * 0.5, center_point[1] - visible_height * 0.5)
        return self._clamp_location(desired, zoom)

    def _location_for_anchor(self, pdf_point: tuple[float, float], anchor_pos: QPoint, zoom: float) -> QPointF:
        offset_x, offset_y = self._viewport_offsets(zoom)
        desired = QPointF(
            pdf_point[0] - (anchor_pos.x() - offset_x) / max(zoom, 0.01),
            pdf_point[1] - (anchor_pos.y() - offset_y) / max(zoom, 0.01),
        )
        return self._clamp_location(desired, zoom)

    def _raw_location_pdf(self, zoom: float | None = None) -> QPointF:
        zoom = max(zoom or self.render_zoom, 0.01)
        offset_x, offset_y = self._viewport_offsets(zoom)
        return QPointF(
            (self.horizontalScrollBar().value() - offset_x) / zoom,
            (self.verticalScrollBar().value() - offset_y) / zoom,
        )

    def _current_location_pdf(self, zoom: float | None = None) -> QPointF:
        zoom = max(zoom or self.render_zoom, 0.01)
        return self._clamp_location(self._raw_location_pdf(zoom), zoom)

    def _pdf_point_from_view(self, view_point: QPoint | None) -> tuple[float, float] | None:
        if view_point is None or not self.has_page():
            return None
        zoom = max(self.render_zoom, 0.01)
        location = self._raw_location_pdf(zoom)
        return (
            clamp(view_point.x() / zoom + location.x(), 0.0, self.pdf_size[0]),
            clamp(view_point.y() / zoom + location.y(), 0.0, self.pdf_size[1]),
        )

    def _viewport_rect_to_pdf(self, rect: QRect) -> RectTuple:
        zoom = max(self.render_zoom, 0.01)
        location = self._raw_location_pdf(zoom)
        left = clamp(rect.left() / zoom + location.x(), 0.0, self.pdf_size[0])
        top = clamp(rect.top() / zoom + location.y(), 0.0, self.pdf_size[1])
        right = clamp(rect.right() / zoom + location.x(), 0.0, self.pdf_size[0])
        bottom = clamp(rect.bottom() / zoom + location.y(), 0.0, self.pdf_size[1])
        return (min(left, right), min(top, bottom), max(left, right), max(top, bottom))

    def _pdf_rect_to_viewport(self, rect: fitz.Rect) -> QRectF:
        zoom = max(self.render_zoom, 0.01)
        location = self._raw_location_pdf(zoom)
        return QRectF(
            (rect.x0 - location.x()) * zoom,
            (rect.y0 - location.y()) * zoom,
            max(2.0, rect.width * zoom),
            max(2.0, rect.height * zoom),
        )

class PdfApp(QMainWindow):
    def __init__(self, history_store_path: str | Path | None = None, state_store_path: str | Path | None = None, asset_dir: str | Path | None = None, test_mode: bool = False):
        super().__init__()
        self.test_mode = test_mode
        self.base_dir = Path(__file__).resolve().parent
        self.history_store_path = Path(history_store_path or self.base_dir / "pdf_search_history.json")
        self.state_store_path = Path(state_store_path or self.base_dir / "pdf_app_state.json")
        self.asset_dir = Path(asset_dir or self.base_dir / "assets")

        self.doc: fitz.Document | None = None
        self.pdf_path: str | None = None
        self.page_sizes: list[tuple[float, float]] = []
        self.current_page = 0
        self.zoom = DEFAULT_ZOOM
        self.zoom_mode = "fit_width"
        self.index_data: DocumentIndex | None = None
        self.index_ready = False
        self.search_busy = False
        self.render_busy = False
        self.current_results: list[SearchHit] = []
        self.page_hits: dict[int, list[SearchHit]] = {}
        self.selected_hit: SearchHit | None = None

        self._focus_after_render: RectTuple | None = None
        self._center_after_render: tuple[float, float] | None = None
        self.index_worker: IndexWorker | None = None
        self.search_worker: SearchWorker | None = None
        self.search_history_limit = SEARCH_HISTORY_LIMIT
        self.history_kind_role = int(Qt.ItemDataRole.UserRole) + 10
        self.history_kind_item = "history_item"
        self.history_kind_clear = "clear_all"
        self.history_clear_text = "全部删除记录"

        self.pdf_histories = self._load_history_store()
        self.state_data = self._load_state_store()
        self.last_opened_pdf = self.state_data.get("last_opened_pdf") or None

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(create_app_icon())
        self.resize(1520, 940)

        self._build_actions()
        self._build_menu()
        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self._refresh_recent_files_menu()
        self._update_file_actions()
        self._update_zoom_label()
        self._refresh_favorites_list()
        self._refresh_page_signals()

    def _build_actions(self) -> None:
        self.open_action = QAction(create_symbol_icon("open"), "打开文件...", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_last_action = QAction(create_symbol_icon("history"), "打开上次文件", self)
        self.close_action = QAction(create_symbol_icon("close"), "关闭文件", self)
        self.close_action.setShortcut(QKeySequence.StandardKey.Close)
        self.exit_action = QAction("退出", self)
        self.exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.prev_page_action = QAction(create_symbol_icon("prev"), "上一页", self)
        self.prev_page_action.setShortcut(QKeySequence("Alt+Left"))
        self.next_page_action = QAction(create_symbol_icon("next"), "下一页", self)
        self.next_page_action.setShortcut(QKeySequence("Alt+Right"))
        self.fit_width_action = QAction(create_symbol_icon("fit_width"), "适应宽度", self)
        self.fit_width_action.setShortcut(QKeySequence("Ctrl+0"))
        self.fit_page_action = QAction(create_symbol_icon("fit_page"), "整页显示", self)
        self.zoom_in_action = QAction(create_symbol_icon("zoom_in"), "放大", self)
        self.zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        self.zoom_out_action = QAction(create_symbol_icon("zoom_out"), "缩小", self)
        self.zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self.favorite_action = QAction(create_symbol_icon("favorite"), "收藏当前命中", self)
        self.favorite_action.setShortcut(QKeySequence("Ctrl+D"))
        self.self_check_action = QAction(create_symbol_icon("check"), "运行内建自检", self)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_last_action)
        self.recent_menu = file_menu.addMenu(create_symbol_icon("history"), "最近文件")
        file_menu.addSeparator()
        file_menu.addAction(self.close_action)
        file_menu.addAction(self.exit_action)

        view_menu = self.menuBar().addMenu("视图(&V)")
        view_menu.addAction(self.prev_page_action)
        view_menu.addAction(self.next_page_action)
        view_menu.addSeparator()
        view_menu.addAction(self.fit_width_action)
        view_menu.addAction(self.fit_page_action)
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)

        tools_menu = self.menuBar().addMenu("工具(&T)")
        tools_menu.addAction(self.favorite_action)
        tools_menu.addAction(self.self_check_action)

    def _make_tool_button(self, icon_kind: str, tooltip: str, text: str = "", accent: bool = False) -> QToolButton:
        button = QToolButton()
        button.setIcon(create_symbol_icon(icon_kind))
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setProperty("accent", accent)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tooltip)
        return button

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("RootWidget")
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
        sidebar.setMinimumWidth(340)
        sidebar.setMaximumWidth(420)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 18, 18, 18)
        side_layout.setSpacing(12)

        brand_title = QLabel("Pin Search")
        brand_title.setObjectName("BrandTitle")
        brand_subtitle = QLabel("针对原理图 / 引脚 / Net 信号优化的极速 PDF 定位器")
        brand_subtitle.setObjectName("MutedLabel")
        brand_subtitle.setWordWrap(True)

        self.search_box = QComboBox()
        self.search_box.setEditable(True)
        self.search_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.search_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.search_box.setMinimumContentsLength(18)
        self.search_box.lineEdit().setPlaceholderText("输入信号名，例如 SYS_RST#")
        self.search_box_delegate = HistoryComboDelegate(self.history_kind_role, self.history_kind_item, self.history_kind_clear, self.search_box.view())
        self.search_box.view().setItemDelegate(self.search_box_delegate)
        self.search_box.view().viewport().installEventFilter(self)

        self.suggestion_model = QStringListModel(self)
        self.search_completer = QCompleter(self.suggestion_model, self)
        self.search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_box.lineEdit().setCompleter(self.search_completer)

        self.search_button = QPushButton("搜索")
        self.search_button.setProperty("accent", True)
        self.search_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.case_button = QPushButton("区分大小写")
        self.case_button.setCheckable(True)
        self.case_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.word_button = QPushButton("精确匹配")
        self.word_button.setCheckable(True)
        self.word_button.setCursor(Qt.CursorShape.PointingHandCursor)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.search_button)
        option_row = QHBoxLayout()
        option_row.setSpacing(8)
        option_row.addWidget(self.case_button)
        option_row.addWidget(self.word_button)
        option_row.addStretch(1)

        self.search_stats_label = QLabel("等待打开 PDF")
        self.search_stats_label.setObjectName("BadgeLabel")
        self.index_status_label = QLabel("索引未开始")
        self.index_status_label.setObjectName("MutedLabel")
        self.index_progress = QProgressBar()
        self.index_progress.setRange(0, 1)
        self.index_progress.setValue(0)
        self.index_progress.setTextVisible(True)
        self.index_progress.setFormat("%v / %m")

        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.page_signal_list = QListWidget()
        self.page_signal_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favorite_list = QListWidget()
        self.favorite_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.result_list, "命中")
        self.tabs.addTab(self.page_signal_list, "本页信号")
        self.tabs.addTab(self.favorite_list, "收藏")

        side_layout.addWidget(brand_title)
        side_layout.addWidget(brand_subtitle)
        side_layout.addLayout(search_row)
        side_layout.addLayout(option_row)
        side_layout.addWidget(self.search_stats_label)
        side_layout.addWidget(self.index_status_label)
        side_layout.addWidget(self.index_progress)
        side_layout.addWidget(self.tabs, 1)

        viewer_panel = QFrame()
        viewer_panel.setObjectName("ViewerPanel")
        viewer_layout = QVBoxLayout(viewer_panel)
        viewer_layout.setContentsMargins(18, 18, 18, 18)
        viewer_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.document_label = QLabel("未打开文档")
        self.document_label.setObjectName("DocTitle")
        self.document_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.prev_button = self._make_tool_button("prev", "上一页")
        self.next_button = self._make_tool_button("next", "下一页")
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_total_label = QLabel("/ 0")
        self.page_total_label.setObjectName("MutedLabel")
        self.fit_width_button = self._make_tool_button("fit_width", "适应宽度")
        self.fit_page_button = self._make_tool_button("fit_page", "整页显示")
        self.zoom_out_button = self._make_tool_button("zoom_out", "缩小")
        self.zoom_in_button = self._make_tool_button("zoom_in", "放大")
        self.favorite_button = self._make_tool_button("favorite", "收藏当前命中")
        self.favorite_button.setProperty("accent", True)
        self.favorite_button.setCheckable(True)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("BadgeLabel")

        for widget in (self.document_label, self.prev_button, self.next_button, self.page_spin, self.page_total_label, self.fit_width_button, self.fit_page_button, self.zoom_out_button, self.zoom_label, self.zoom_in_button, self.favorite_button):
            header_row.addWidget(widget)
        header_row.setStretch(0, 1)

        self.canvas = PdfCanvas()
        self.hint_label = QLabel("滚轮缩放 · 中键拖拽平移 · Alt + 左键框选复制文字 · 双击命中自动放大定位")
        self.hint_label.setObjectName("MutedLabel")
        viewer_layout.addLayout(header_row)
        viewer_layout.addWidget(self.canvas, 1)
        viewer_layout.addWidget(self.hint_label)

        splitter.addWidget(sidebar)
        splitter.addWidget(viewer_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 1120])

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_detail_label = QLabel("就绪")
        self.status_detail_label.setObjectName("MutedLabel")
        status_bar.addPermanentWidget(self.status_detail_label)

    def _connect_signals(self) -> None:
        self.open_action.triggered.connect(self.open_pdf_dialog)
        self.open_last_action.triggered.connect(self.open_last_pdf)
        self.close_action.triggered.connect(self.close_current_pdf)
        self.exit_action.triggered.connect(self.close)
        self.prev_page_action.triggered.connect(self.prev_page)
        self.next_page_action.triggered.connect(self.next_page)
        self.fit_width_action.triggered.connect(self.fit_width)
        self.fit_page_action.triggered.connect(self.fit_page)
        self.zoom_in_action.triggered.connect(self.zoom_in)
        self.zoom_out_action.triggered.connect(self.zoom_out)
        self.favorite_action.triggered.connect(self.toggle_current_favorite)
        self.self_check_action.triggered.connect(self.run_in_app_self_check)
        self.search_button.clicked.connect(self.search)
        self.search_box.lineEdit().returnPressed.connect(self.search)
        self.search_box.activated.connect(self._on_history_selected)
        self.case_button.toggled.connect(self._on_search_option_changed)
        self.word_button.toggled.connect(self._on_search_option_changed)
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button.clicked.connect(self.next_page)
        self.fit_width_button.clicked.connect(self.fit_width)
        self.fit_page_button.clicked.connect(self.fit_page)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.favorite_button.clicked.connect(self.toggle_current_favorite)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        self.result_list.currentItemChanged.connect(self._on_result_current_changed)
        self.result_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        self.result_list.customContextMenuRequested.connect(self._show_result_context_menu)
        self.page_signal_list.itemClicked.connect(self._search_from_signal_item)
        self.page_signal_list.customContextMenuRequested.connect(self._show_signal_context_menu)
        self.favorite_list.itemClicked.connect(self._open_favorite_item)
        self.favorite_list.customContextMenuRequested.connect(self._show_favorite_context_menu)
        self.canvas.selectionFinished.connect(self._copy_text_from_pdf_rect)
        self.canvas.zoomRequested.connect(self._on_canvas_zoom_requested)
        self.canvas.resized.connect(self._on_canvas_resized)
        QShortcut(QKeySequence.StandardKey.Find, self).activated.connect(self._focus_search_box)
        QShortcut(QKeySequence.StandardKey.Copy, self.result_list).activated.connect(self.copy_selected_results)
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self.fit_width)

    def _apply_style(self) -> None:
        self.setStyleSheet("QMainWindow { background: #e7ecef; } #RootWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #eef2f5, stop:0.55 #e5ebef, stop:1 #d8e1e6); } #SidebarPanel, #ViewerPanel { background: rgba(255, 255, 255, 0.94); border: 1px solid #d3dde3; border-radius: 18px; } QLabel#BrandTitle { color: #1d2a33; font-size: 20px; font-weight: 700; } QLabel#DocTitle { color: #1d2a33; font-size: 16px; font-weight: 700; } QLabel#MutedLabel { color: #5f6d76; } QLabel#BadgeLabel { color: #18313d; background: #e6edf2; border: 1px solid #ccd8df; border-radius: 11px; padding: 5px 10px; font-weight: 600; } QComboBox, QSpinBox { background: #f8fafb; border: 1px solid #d6e0e5; border-radius: 12px; padding: 8px 10px; color: #15212a; } QComboBox::drop-down { border: none; width: 22px; } QPushButton, QToolButton { background: #f4f7f9; border: 1px solid #d3dde3; border-radius: 12px; padding: 8px 12px; color: #14303b; font-weight: 600; } QPushButton:hover, QToolButton:hover { background: #ebf1f5; border-color: #b8c9d3; } QPushButton:checked, QToolButton:checked { background: #173f52; color: white; border-color: #173f52; } QPushButton[accent=\"true\"], QToolButton[accent=\"true\"] { background: #173f52; color: white; border-color: #173f52; } QPushButton[accent=\"true\"]:hover, QToolButton[accent=\"true\"]:hover { background: #214f65; border-color: #214f65; } QProgressBar { background: #f1f5f8; border: 1px solid #d4dee4; border-radius: 10px; text-align: center; color: #274252; min-height: 18px; } QProgressBar::chunk { background: #2f7c93; border-radius: 9px; } QTabWidget::pane { border: none; top: -1px; } QTabBar::tab { background: #edf2f5; color: #50626d; border: 1px solid #d2dde3; padding: 8px 14px; border-top-left-radius: 12px; border-top-right-radius: 12px; margin-right: 4px; font-weight: 600; } QTabBar::tab:selected { background: #173f52; color: white; border-color: #173f52; } QListWidget { background: transparent; border: none; outline: none; } QListWidget::item { background: #f6f9fb; border: 1px solid #dde6eb; border-radius: 14px; padding: 10px; margin: 4px 0; color: #18252e; } QListWidget::item:selected { background: #e4eef3; border-color: #7f9ba9; color: #10202a; } #PdfCanvas { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f4f6f7, stop:1 #ebf0f3); border: 1px solid #d6dfe4; border-radius: 16px; } QStatusBar { background: rgba(255, 255, 255, 0.75); border-top: 1px solid #d5dfe4; }")
        self.setFont(QFont("Microsoft YaHei UI", 10))

    def eventFilter(self, obj, event) -> bool:
        if obj is self.search_box.view().viewport() and event.type() == QEvent.Type.MouseButtonPress:
            if self._handle_history_popup_click(event):
                return True
        return super().eventFilter(obj, event)

    def _load_history_store(self) -> dict[str, list[str]]:
        if not self.history_store_path.exists():
            return {}
        try:
            raw = json.loads(self.history_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        histories: dict[str, list[str]] = {}
        for key, values in raw.items():
            if not isinstance(values, list):
                continue
            seen: set[str] = set()
            cleaned: list[str] = []
            for value in values:
                if not isinstance(value, str):
                    continue
                text = value.strip()
                if not text:
                    continue
                folded = text.casefold()
                if folded in seen:
                    continue
                seen.add(folded)
                cleaned.append(text)
                if len(cleaned) >= self.search_history_limit:
                    break
            histories[str(key)] = cleaned
        return histories

    def _save_history_store(self) -> None:
        try:
            self.history_store_path.write_text(json.dumps(self.pdf_histories, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _load_state_store(self) -> dict:
        default = {"last_opened_pdf": "", "recent_files": [], "favorites": {}}
        if not self.state_store_path.exists():
            return default
        try:
            raw = json.loads(self.state_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default
        if not isinstance(raw, dict):
            return default

        recent_files = []
        seen_files: set[str] = set()
        for value in raw.get("recent_files", []):
            if not isinstance(value, str):
                continue
            path = os.path.abspath(value)
            key = os.path.normcase(path)
            if key in seen_files:
                continue
            seen_files.add(key)
            recent_files.append(path)
            if len(recent_files) >= RECENT_FILES_LIMIT:
                break

        favorites: dict[str, list[dict]] = {}
        raw_favorites = raw.get("favorites", {})
        if isinstance(raw_favorites, dict):
            for key, items in raw_favorites.items():
                if not isinstance(items, list):
                    continue
                clean_items: list[dict] = []
                seen_items: set[tuple[int, str]] = set()
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get("text", "")).strip()
                    if not text:
                        continue
                    try:
                        page = int(item.get("page", 0))
                    except (TypeError, ValueError):
                        continue
                    item_key = (page, text.casefold())
                    if item_key in seen_items:
                        continue
                    seen_items.add(item_key)
                    favorite = {"text": text, "page": page, "context": str(item.get("context", "")).strip()}
                    rect = item.get("rect")
                    if isinstance(rect, (list, tuple)) and len(rect) == 4:
                        try:
                            favorite["rect"] = [float(value) for value in rect]
                        except (TypeError, ValueError):
                            pass
                    clean_items.append(favorite)
                favorites[str(key)] = clean_items

        return {
            "last_opened_pdf": os.path.abspath(raw.get("last_opened_pdf", "")) if raw.get("last_opened_pdf") else "",
            "recent_files": recent_files,
            "favorites": favorites,
        }

    def _save_state_store(self) -> None:
        payload = {"last_opened_pdf": self.last_opened_pdf or "", "recent_files": self.state_data.get("recent_files", []), "favorites": self.state_data.get("favorites", {})}
        try:
            self.state_store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _pdf_key(self, path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def _current_pdf_key(self) -> str | None:
        return self._pdf_key(self.pdf_path) if self.pdf_path else None

    def _get_current_pdf_history_terms(self) -> list[str]:
        key = self._current_pdf_key()
        return list(self.pdf_histories.get(key, [])) if key else []

    def _set_current_pdf_history_terms(self, terms: list[str]) -> None:
        key = self._current_pdf_key()
        if not key:
            return
        clean_items: list[str] = []
        seen: set[str] = set()
        for value in terms:
            text = str(value).strip()
            if not text:
                continue
            folded = text.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            clean_items.append(text)
            if len(clean_items) >= self.search_history_limit:
                break
        if clean_items:
            self.pdf_histories[key] = clean_items
        else:
            self.pdf_histories.pop(key, None)
        self._save_history_store()

    def _refresh_search_history_combo(self, keep_text: str = "") -> None:
        terms = self._get_current_pdf_history_terms()
        self.search_box.blockSignals(True)
        self.search_box.clear()
        for term in terms:
            self.search_box.addItem(term)
            row = self.search_box.count() - 1
            self.search_box.setItemData(row, self.history_kind_item, self.history_kind_role)
        if terms:
            self.search_box.addItem(self.history_clear_text)
            row = self.search_box.count() - 1
            self.search_box.setItemData(row, self.history_kind_clear, self.history_kind_role)
        self.search_box.setCurrentText(keep_text)
        self.search_box.blockSignals(False)

    def _remove_single_history_term(self, term: str) -> None:
        filtered = [item for item in self._get_current_pdf_history_terms() if item.casefold() != term.casefold()]
        self._set_current_pdf_history_terms(filtered)
        current_text = self._get_search_text()
        if current_text.casefold() == term.casefold():
            current_text = ""
        self._refresh_search_history_combo(current_text)

    def _clear_all_history_terms(self) -> None:
        self._set_current_pdf_history_terms([])
        self._refresh_search_history_combo("")

    def _history_icon_rect_for_index(self, index) -> QRect:
        return HistoryComboDelegate.trash_rect(self.search_box.view().visualRect(index))

    def _handle_history_popup_click(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        view = self.search_box.view()
        index = view.indexAt(event.pos())
        if not index.isValid():
            return False
        row = index.row()
        kind = self.search_box.itemData(row, self.history_kind_role)
        if kind == self.history_kind_item:
            if self._history_icon_rect_for_index(index).contains(event.pos()):
                self._remove_single_history_term(self.search_box.itemText(row))
                if self.search_box.count() > 0:
                    QTimer.singleShot(0, self.search_box.showPopup)
                else:
                    self.search_box.hidePopup()
                return True
            return False
        if kind == self.history_kind_clear:
            self._clear_all_history_terms()
            self.search_box.hidePopup()
            return True
        return False

    def _refresh_recent_files_menu(self) -> None:
        self.recent_menu.clear()
        recent_files = self.state_data.get("recent_files", [])
        if not recent_files:
            empty_action = self.recent_menu.addAction("暂无最近文件")
            empty_action.setEnabled(False)
            return
        for path in recent_files:
            action = self.recent_menu.addAction(create_symbol_icon("history"), os.path.basename(path) or path)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, chosen=path: self.load_pdf(chosen))

    def _remember_recent_file(self, path: str) -> None:
        normalized = os.path.abspath(path)
        recent_files = [item for item in self.state_data.get("recent_files", []) if os.path.normcase(item) != os.path.normcase(normalized)]
        recent_files.insert(0, normalized)
        self.state_data["recent_files"] = recent_files[:RECENT_FILES_LIMIT]
        self._save_state_store()
        self._refresh_recent_files_menu()

    def _get_current_favorites(self) -> list[dict]:
        key = self._current_pdf_key()
        return list(self.state_data.setdefault("favorites", {}).get(key, [])) if key else []

    def _set_current_favorites(self, favorites: list[dict]) -> None:
        key = self._current_pdf_key()
        if not key:
            return
        if favorites:
            self.state_data.setdefault("favorites", {})[key] = favorites
        else:
            self.state_data.setdefault("favorites", {}).pop(key, None)
        self._save_state_store()
        self._refresh_favorites_list()
        self._update_favorite_state()

    def _favorite_from_hit(self, hit: SearchHit) -> dict:
        return {"text": hit.text, "page": hit.page_number, "context": hit.context, "rect": list(hit.rect)}

    def _is_hit_favorite(self, hit: SearchHit | None) -> bool:
        if hit is None:
            return False
        return any(int(favorite.get("page", -1)) == hit.page_number and str(favorite.get("text", "")).casefold() == hit.text.casefold() for favorite in self._get_current_favorites())

    def _refresh_favorites_list(self) -> None:
        self.favorite_list.clear()
        for favorite in self._get_current_favorites():
            text = str(favorite.get("text", "")).strip()
            if not text:
                continue
            page = int(favorite.get("page", 0)) + 1
            context = truncate(str(favorite.get("context", "")), 72)
            item = QListWidgetItem(f"{text}\nP{page} · {context}")
            item.setSizeHint(QSize(0, 56))
            item.setData(Qt.ItemDataRole.UserRole, favorite)
            item.setIcon(create_symbol_icon("favorite"))
            self.favorite_list.addItem(item)

    def _refresh_page_signals(self) -> None:
        self.page_signal_list.clear()
        if not self.index_data or self.current_page >= len(self.index_data.pages):
            return
        for term in self.index_data.pages[self.current_page].signals:
            item = QListWidgetItem(term)
            item.setSizeHint(QSize(0, 40))
            item.setIcon(create_symbol_icon("search"))
            self.page_signal_list.addItem(item)

    def _focus_search_box(self) -> None:
        self.search_box.setFocus()
        self.search_box.lineEdit().selectAll()

    def _set_status_message(self, message: str, detail: str | None = None, timeout: int = 3000) -> None:
        self.statusBar().showMessage(message, timeout)
        if detail is not None:
            self.status_detail_label.setText(detail)

    def _get_search_text(self) -> str:
        return self.search_box.currentText().strip()

    def _update_file_actions(self) -> None:
        has_doc = self.doc is not None
        has_last = bool(self.last_opened_pdf and os.path.exists(self.last_opened_pdf))
        self.open_last_action.setEnabled(has_last)
        self.close_action.setEnabled(has_doc)
        for widget in (self.prev_button, self.next_button, self.page_spin, self.search_button, self.fit_width_button, self.fit_page_button, self.zoom_in_button, self.zoom_out_button, self.favorite_button):
            widget.setEnabled(has_doc)

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText(f"{self.zoom * 100:.0f}%")

    def _update_document_label(self) -> None:
        if not self.pdf_path or not self.doc:
            self.document_label.setText("未打开文档")
            self.page_total_label.setText("/ 0")
            return
        self.document_label.setText(f"{os.path.basename(self.pdf_path)} · {len(self.doc)} 页")
        self.page_total_label.setText(f"/ {len(self.doc)}")

    def _update_page_controls(self) -> None:
        if not self.doc:
            self.page_spin.blockSignals(True)
            self.page_spin.setRange(1, 1)
            self.page_spin.setValue(1)
            self.page_spin.blockSignals(False)
            return
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, len(self.doc))
        self.page_spin.setValue(self.current_page + 1)
        self.page_spin.blockSignals(False)

    def _update_favorite_state(self) -> None:
        is_favorite = self._is_hit_favorite(self.selected_hit)
        self.favorite_button.setChecked(is_favorite)
        self.favorite_action.setText("取消收藏当前命中" if is_favorite else "收藏当前命中")

    def _stop_worker(self, worker: QThread | None) -> None:
        if worker and worker.isRunning():
            worker.requestInterruption()
            worker.wait(1200)

    def _shutdown_workers(self) -> None:
        self._stop_worker(self.index_worker)
        self._stop_worker(self.search_worker)

    def open_pdf_dialog(self) -> None:
        start_dir = os.path.dirname(self.pdf_path) if self.pdf_path else (os.path.dirname(self.last_opened_pdf) if self.last_opened_pdf else "")
        file_path, _selected = QFileDialog.getOpenFileName(self, "选择 PDF 文件", start_dir, "PDF Files (*.pdf);;All Files (*)")
        if file_path:
            self.load_pdf(file_path)

    def open_last_pdf(self) -> None:
        if self.last_opened_pdf and os.path.exists(self.last_opened_pdf):
            self.load_pdf(self.last_opened_pdf)

    def close_current_pdf(self) -> None:
        self._shutdown_workers()
        self.index_worker = None
        self.search_worker = None
        if self.doc is not None:
            self.doc.close()
        self.doc = None
        self.pdf_path = None
        self.page_sizes = []
        self.current_page = 0
        self.zoom = DEFAULT_ZOOM
        self.zoom_mode = "fit_width"
        self.index_data = None
        self.index_ready = False
        self.search_busy = False
        self.render_busy = False
        self.current_results.clear()
        self.page_hits.clear()
        self.selected_hit = None
        self.canvas.clear_document()
        self.search_box.blockSignals(True)
        self.search_box.clear()
        self.search_box.setCurrentText("")
        self.search_box.blockSignals(False)
        self.suggestion_model.setStringList([])
        self.result_list.clear()
        self.favorite_list.clear()
        self.page_signal_list.clear()
        self.document_label.setText("未打开文档")
        self.search_stats_label.setText("等待打开 PDF")
        self.index_status_label.setText("索引未开始")
        self.index_progress.setRange(0, 1)
        self.index_progress.setValue(0)
        self._update_page_controls()
        self._update_zoom_label()
        self._update_document_label()
        self._update_file_actions()
        self._set_status_message("文档已关闭", "就绪", 2000)

    def load_pdf(self, path: str) -> None:
        normalized_path = os.path.abspath(path)
        if not os.path.exists(normalized_path):
            QMessageBox.warning(self, APP_NAME, f"文件不存在:\n{normalized_path}")
            return
        try:
            doc = fitz.open(normalized_path)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"打开 PDF 失败:\n{exc}")
            return

        self.close_current_pdf()
        self.doc = doc
        self.pdf_path = normalized_path
        self.page_sizes = [(float(self.doc.load_page(page_number).rect.width), float(self.doc.load_page(page_number).rect.height)) for page_number in range(len(self.doc))]
        canvas_error = self.canvas.load_document(normalized_path, self.page_sizes)
        if canvas_error is not None:
            self.doc.close()
            self.doc = None
            self.pdf_path = None
            self.page_sizes = []
            QMessageBox.critical(self, APP_NAME, f"加载高清查看器失败:\n{canvas_error}")
            return
        self.current_page = 0
        self.zoom_mode = "fit_width"
        self.last_opened_pdf = normalized_path
        self.state_data["last_opened_pdf"] = normalized_path
        self._save_state_store()
        self._remember_recent_file(normalized_path)
        self._refresh_search_history_combo("")
        self._refresh_favorites_list()
        self._update_document_label()
        self._update_page_controls()
        self._update_file_actions()
        self._start_index_build()
        self.fit_width(immediate=True)
        self._set_status_message(f"已打开 {os.path.basename(normalized_path)}", "正在建立索引...", 3000)

    def _start_index_build(self) -> None:
        if not self.pdf_path:
            return
        self._stop_worker(self.index_worker)
        self.index_ready = False
        self.index_data = None
        self.suggestion_model.setStringList([])
        self.index_progress.setRange(0, max(1, len(self.doc) if self.doc else 1))
        self.index_progress.setValue(0)
        self.index_status_label.setText("正在扫描全文并建立信号索引...")
        self.index_worker = IndexWorker(self.pdf_path)
        self.index_worker.progressChanged.connect(self._on_index_progress)
        self.index_worker.completed.connect(self._on_index_completed)
        self.index_worker.failed.connect(self._on_index_failed)
        self.index_worker.finished.connect(self.index_worker.deleteLater)
        self.index_worker.start()

    def _on_index_progress(self, current: int, total: int) -> None:
        self.index_progress.setRange(0, max(1, total))
        self.index_progress.setValue(current)
        self.index_status_label.setText(f"正在建立索引... {current}/{total}")

    def _on_index_completed(self, index: DocumentIndex, elapsed_ms: float) -> None:
        self.index_data = index
        self.index_ready = True
        self.suggestion_model.setStringList(index.suggestions)
        self.index_progress.setValue(self.index_progress.maximum())
        self.index_status_label.setText(f"索引完成 · {index.page_count} 页 · {len(index.suggestions)} 个信号建议 · {elapsed_ms:.0f} ms")
        self._refresh_page_signals()
        self._set_status_message("索引已完成", f"索引耗时 {elapsed_ms:.0f} ms", 2500)

    def _on_index_failed(self, message: str) -> None:
        self.index_status_label.setText(f"索引失败: {message}")
        self._set_status_message("索引失败", message, 4500)

    def _on_canvas_zoom_requested(self, zoom: float) -> None:
        self.zoom_mode = "manual"
        self.zoom = clamp(zoom, MIN_ZOOM, MAX_ZOOM)
        self._focus_after_render = None
        self._center_after_render = None
        self._update_zoom_label()
        self.status_detail_label.setText(f"P{self.current_page + 1} · {self.zoom * 100:.0f}%")

    def _on_canvas_resized(self) -> None:
        if not self.doc:
            return
        if self.zoom_mode == "fit_width":
            self.fit_width(immediate=True)
        elif self.zoom_mode == "fit_page":
            self.fit_page(immediate=True)

    def _desired_zoom_for_mode(self, mode: str) -> float:
        if not self.doc or not self.page_sizes:
            return DEFAULT_ZOOM
        pdf_size = self.page_sizes[self.current_page]
        if mode == "fit_width":
            return self.canvas.fit_width_zoom(pdf_size)
        if mode == "fit_page":
            return self.canvas.fit_page_zoom(pdf_size)
        return clamp(self.zoom, MIN_ZOOM, MAX_ZOOM)

    def fit_width(self, immediate: bool = True) -> None:
        if not self.doc:
            return
        self.zoom_mode = "fit_width"
        self.zoom = self._desired_zoom_for_mode("fit_width")
        self._update_zoom_label()
        self._focus_after_render = self.selected_hit.rect if self.selected_hit and self.selected_hit.page_number == self.current_page else None
        self._center_after_render = None if self._focus_after_render else self.canvas.current_center_pdf()
        self._dispatch_render()

    def fit_page(self, immediate: bool = True) -> None:
        if not self.doc:
            return
        self.zoom_mode = "fit_page"
        self.zoom = self._desired_zoom_for_mode("fit_page")
        self._update_zoom_label()
        self._focus_after_render = self.selected_hit.rect if self.selected_hit and self.selected_hit.page_number == self.current_page else None
        self._center_after_render = None if self._focus_after_render else self.canvas.current_center_pdf()
        self._dispatch_render()

    def zoom_in(self) -> None:
        if not self.doc:
            return
        self.zoom_mode = "manual"
        self.zoom = clamp(self.zoom * 1.16, MIN_ZOOM, MAX_ZOOM)
        self._update_zoom_label()
        self._focus_after_render = self.selected_hit.rect if self.selected_hit and self.selected_hit.page_number == self.current_page else None
        self._center_after_render = None if self._focus_after_render else self.canvas.current_center_pdf()
        self._dispatch_render()

    def zoom_out(self) -> None:
        if not self.doc:
            return
        self.zoom_mode = "manual"
        self.zoom = clamp(self.zoom / 1.16, MIN_ZOOM, MAX_ZOOM)
        self._update_zoom_label()
        self._focus_after_render = self.selected_hit.rect if self.selected_hit and self.selected_hit.page_number == self.current_page else None
        self._center_after_render = None if self._focus_after_render else self.canvas.current_center_pdf()
        self._dispatch_render()

    def _dispatch_render(self) -> None:
        if not self.doc or not self.pdf_path:
            return
        page_number = self.current_page
        zoom = clamp(self.zoom, MIN_ZOOM, MAX_ZOOM)
        self.render_busy = True
        started = time.perf_counter()
        try:
            self.canvas.set_view_state(
                page_number,
                self.page_sizes[page_number],
                zoom,
                self.page_hits.get(page_number, []),
                self.selected_hit,
                focus_rect=self._focus_after_render,
                center_point=self._center_after_render,
            )
        except Exception as exc:
            self.render_busy = False
            self._set_status_message("渲染失败", str(exc), 4500)
            return

        self.render_busy = False
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._focus_after_render = None
        self._center_after_render = None
        detail = f"P{page_number + 1} · {zoom * 100:.0f}%"
        if elapsed_ms > 0:
            detail += f" · {elapsed_ms:.0f} ms"
        self.status_detail_label.setText(detail)

    def _open_hit(self, hit: SearchHit, focus_zoom: float | None = None) -> None:
        self.selected_hit = hit
        self.current_page = hit.page_number
        self._update_page_controls()
        self._refresh_page_signals()
        self._update_favorite_state()
        if focus_zoom is not None and self.zoom < focus_zoom:
            self.zoom_mode = "manual"
            self.zoom = clamp(focus_zoom, MIN_ZOOM, MAX_ZOOM)
            self._update_zoom_label()
        self._focus_after_render = hit.rect
        self._center_after_render = None
        self._dispatch_render()

    def prev_page(self) -> None:
        if not self.doc or self.current_page <= 0:
            return
        self.current_page -= 1
        page_hits = self.page_hits.get(self.current_page, [])
        self.selected_hit = page_hits[0] if page_hits else None
        self._update_page_controls()
        self._refresh_page_signals()
        self._update_favorite_state()
        self._focus_after_render = self.selected_hit.rect if self.selected_hit else None
        self._center_after_render = None
        if self.zoom_mode in {"fit_width", "fit_page"}:
            self.zoom = self._desired_zoom_for_mode(self.zoom_mode)
            self._update_zoom_label()
        self._dispatch_render()

    def next_page(self) -> None:
        if not self.doc or self.current_page >= len(self.doc) - 1:
            return
        self.current_page += 1
        page_hits = self.page_hits.get(self.current_page, [])
        self.selected_hit = page_hits[0] if page_hits else None
        self._update_page_controls()
        self._refresh_page_signals()
        self._update_favorite_state()
        self._focus_after_render = self.selected_hit.rect if self.selected_hit else None
        self._center_after_render = None
        if self.zoom_mode in {"fit_width", "fit_page"}:
            self.zoom = self._desired_zoom_for_mode(self.zoom_mode)
            self._update_zoom_label()
        self._dispatch_render()

    def _on_page_spin_changed(self, value: int) -> None:
        if not self.doc:
            return
        page_number = value - 1
        if page_number == self.current_page:
            return
        self.current_page = clamp(page_number, 0, len(self.doc) - 1)
        page_hits = self.page_hits.get(self.current_page, [])
        self.selected_hit = page_hits[0] if page_hits else None
        self._refresh_page_signals()
        self._update_favorite_state()
        self._focus_after_render = self.selected_hit.rect if self.selected_hit else None
        self._center_after_render = None
        if self.zoom_mode in {"fit_width", "fit_page"}:
            self.zoom = self._desired_zoom_for_mode(self.zoom_mode)
            self._update_zoom_label()
        self._dispatch_render()

    def _add_search_history(self, keyword: str) -> None:
        terms = self._get_current_pdf_history_terms()
        terms = [item for item in terms if item.casefold() != keyword.casefold()]
        terms.insert(0, keyword)
        self._set_current_pdf_history_terms(terms)
        self._refresh_search_history_combo(keyword)

    def _build_result_item(self, hit: SearchHit) -> QListWidgetItem:
        content = f"{hit.text}\nP{hit.page_number + 1} · {hit.match_type}\n{truncate(hit.context, 88)}"
        item = QListWidgetItem(content)
        item.setData(Qt.ItemDataRole.UserRole, hit)
        item.setSizeHint(QSize(0, 70))
        item.setIcon(create_symbol_icon("search" if not self._is_hit_favorite(hit) else "favorite"))
        item.setToolTip(f"{hit.text}\nPage {hit.page_number + 1}\n{hit.context}")
        return item

    def _apply_search_results(self, hits: list[SearchHit], elapsed_ms: float, source_label: str) -> None:
        self.search_busy = False
        self.current_results = hits
        self.page_hits = group_hits_by_page(hits)
        self.result_list.clear()
        for hit in hits:
            self.result_list.addItem(self._build_result_item(hit))
        self.search_stats_label.setText(f"{len(hits)} 命中 · {source_label} · {elapsed_ms:.0f} ms")
        self.canvas.set_highlights(self.page_hits.get(self.current_page, []), self.selected_hit)
        if hits:
            self.tabs.setCurrentWidget(self.result_list)
            self.result_list.setCurrentRow(0)
        else:
            self.selected_hit = None
            self._update_favorite_state()
            self.canvas.set_highlights(self.page_hits.get(self.current_page, []), None)
            self._dispatch_render()
            self._set_status_message("未找到匹配信号", self.status_detail_label.text(), 2500)

    def search(self) -> None:
        query = self._get_search_text()
        self.current_results = []
        self.page_hits = {}
        self.selected_hit = None
        self.result_list.clear()
        self.canvas.set_highlights([], None)
        self._update_favorite_state()
        if not self.doc:
            return
        if not query:
            self.search_stats_label.setText("请输入要搜索的信号")
            self._dispatch_render()
            return

        self._add_search_history(query)
        options = SearchOptions(case_sensitive=self.case_button.isChecked(), whole_word=self.word_button.isChecked())
        if self.search_worker and self.search_worker.isRunning():
            self.search_worker.requestInterruption()
            self.search_worker.wait(1200)

        started = time.perf_counter()
        if self.index_ready and self.index_data and " " not in query:
            hits = search_index(self.index_data, query, options)
            self._apply_search_results(hits, (time.perf_counter() - started) * 1000.0, "索引")
            return

        self.search_busy = True
        self.search_stats_label.setText("正在即时扫描全文...")
        self.search_worker = SearchWorker(self.pdf_path, query, options)
        self.search_worker.completed.connect(lambda hits, elapsed_ms: self._apply_search_results(hits, elapsed_ms, "即时扫描"))
        self.search_worker.failed.connect(lambda message: self._set_status_message("搜索失败", message, 4500))
        self.search_worker.finished.connect(self.search_worker.deleteLater)
        self.search_worker.start()

    def _on_search_option_changed(self, _checked: bool) -> None:
        if self._get_search_text() and self.doc:
            self.search()

    def _on_history_selected(self, index: int) -> None:
        if index < 0:
            return
        kind = self.search_box.itemData(index, self.history_kind_role)
        if kind == self.history_kind_clear:
            self._clear_all_history_terms()
            return
        if kind == self.history_kind_item and self._get_search_text():
            self.search()

    def _on_result_current_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        hit = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(hit, SearchHit):
            self._open_hit(hit)

    def _on_result_double_clicked(self, item: QListWidgetItem) -> None:
        hit = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(hit, SearchHit):
            self._open_hit(hit, focus_zoom=max(self.zoom, 2.3))

    def copy_selected_results(self) -> None:
        selected_items = self.result_list.selectedItems()
        if not selected_items:
            return
        lines = []
        for item in selected_items:
            hit = item.data(Qt.ItemDataRole.UserRole)
            lines.append(hit.text if isinstance(hit, SearchHit) else item.text())
        QApplication.clipboard().setText("\n".join(lines))
        self._set_status_message("已复制所选命中", self.status_detail_label.text(), 1800)

    def _show_result_context_menu(self, pos) -> None:
        item = self.result_list.itemAt(pos)
        menu = QMenu(self)
        copy_action = menu.addAction("复制选中内容")
        favorite_action = None
        if item is not None:
            hit = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(hit, SearchHit):
                favorite_action = menu.addAction("取消收藏" if self._is_hit_favorite(hit) else "加入收藏")
        chosen = menu.exec(self.result_list.mapToGlobal(pos))
        if chosen == copy_action:
            self.copy_selected_results()
        elif favorite_action is not None and item is not None:
            hit = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(hit, SearchHit):
                self._toggle_favorite(hit)

    def _show_signal_context_menu(self, pos) -> None:
        item = self.page_signal_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        favorite_action = menu.addAction("加入收藏")
        search_action = menu.addAction("立即搜索")
        chosen = menu.exec(self.page_signal_list.mapToGlobal(pos))
        term = item.text().strip()
        if chosen == favorite_action:
            favorite = {"text": term, "page": self.current_page, "context": term}
            favorites = self._get_current_favorites()
            if not any(int(entry.get("page", -1)) == self.current_page and str(entry.get("text", "")).casefold() == term.casefold() for entry in favorites):
                favorites.insert(0, favorite)
                self._set_current_favorites(favorites)
        elif chosen == search_action:
            self.search_box.setCurrentText(term)
            self.search()

    def _show_favorite_context_menu(self, pos) -> None:
        item = self.favorite_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        open_action = menu.addAction("打开收藏")
        remove_action = menu.addAction("移除收藏")
        chosen = menu.exec(self.favorite_list.mapToGlobal(pos))
        if chosen == open_action:
            self._open_favorite_item(item)
        elif chosen == remove_action:
            favorite = item.data(Qt.ItemDataRole.UserRole)
            self._remove_favorite(favorite)

    def _search_from_signal_item(self, item: QListWidgetItem) -> None:
        term = item.text().strip()
        if term:
            self.search_box.setCurrentText(term)
            self.search()

    def _open_favorite_item(self, item: QListWidgetItem) -> None:
        favorite = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(favorite, dict):
            return
        term = str(favorite.get("text", "")).strip()
        page = int(favorite.get("page", 0))
        if not term:
            return
        self.search_box.setCurrentText(term)
        self.search()
        if self.current_results:
            preferred = next((hit for hit in self.current_results if hit.page_number == page), self.current_results[0])
            self._open_hit(preferred)

    def _toggle_favorite(self, hit: SearchHit) -> None:
        favorites = self._get_current_favorites()
        new_favorites = [favorite for favorite in favorites if not (int(favorite.get("page", -1)) == hit.page_number and str(favorite.get("text", "")).casefold() == hit.text.casefold())]
        if len(new_favorites) == len(favorites):
            new_favorites.insert(0, self._favorite_from_hit(hit))
            self._set_status_message(f"已收藏 {hit.text}", self.status_detail_label.text(), 1800)
        else:
            self._set_status_message(f"已取消收藏 {hit.text}", self.status_detail_label.text(), 1800)
        self._set_current_favorites(new_favorites)
        self._refresh_result_icons()

    def _remove_favorite(self, favorite: dict) -> None:
        favorites = [entry for entry in self._get_current_favorites() if not (int(entry.get("page", -1)) == int(favorite.get("page", -2)) and str(entry.get("text", "")).casefold() == str(favorite.get("text", "")).casefold())]
        self._set_current_favorites(favorites)

    def _refresh_result_icons(self) -> None:
        for row in range(self.result_list.count()):
            item = self.result_list.item(row)
            hit = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(hit, SearchHit):
                item.setIcon(create_symbol_icon("favorite" if self._is_hit_favorite(hit) else "search"))
        self._update_favorite_state()

    def toggle_current_favorite(self) -> None:
        if self.selected_hit is not None:
            self._toggle_favorite(self.selected_hit)

    def _extract_text_from_pdf_rect(self, page: fitz.Page, pdf_rect: RectTuple) -> str:
        target = tuple_to_rect(pdf_rect)
        picked = []
        for word in page.get_text("words"):
            if len(word) < 5:
                continue
            rect = fitz.Rect(word[0], word[1], word[2], word[3])
            if not rect.intersects(target):
                continue
            block_no = int(word[5]) if len(word) > 5 else 0
            line_no = int(word[6]) if len(word) > 6 else 0
            word_no = int(word[7]) if len(word) > 7 else 0
            text = str(word[4]).strip()
            if text:
                picked.append((block_no, line_no, word_no, text))
        if picked:
            picked.sort(key=lambda item: (item[0], item[1], item[2]))
            lines: list[str] = []
            current_key = None
            current_words: list[str] = []
            for block_no, line_no, _word_no, text in picked:
                key = (block_no, line_no)
                if current_key is None:
                    current_key = key
                if key != current_key:
                    lines.append(" ".join(current_words))
                    current_words = [text]
                    current_key = key
                else:
                    current_words.append(text)
            if current_words:
                lines.append(" ".join(current_words))
            return "\n".join(line for line in lines if line).strip()
        return page.get_textbox(target).strip()

    def _copy_text_from_pdf_rect(self, pdf_rect: RectTuple) -> None:
        if not self.doc:
            return
        text = self._extract_text_from_pdf_rect(self.doc.load_page(self.current_page), pdf_rect)
        if text:
            QApplication.clipboard().setText(text)
            self._set_status_message(f"复制完成: {truncate(text, 100)}", self.status_detail_label.text(), 2800)
        else:
            self._set_status_message("框选区域未识别到文字", self.status_detail_label.text(), 2000)

    def run_in_app_self_check(self) -> None:
        pdf_path = self.pdf_path or str(self.base_dir / "test.pdf")
        if not os.path.exists(pdf_path):
            QMessageBox.warning(self, APP_NAME, "未找到可用于自检的 PDF 文件。")
            return
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = str(Path(temp_dir) / "self_check_report.json")
            report = perform_app_self_test(pdf_path, DEFAULT_QUERY, report_path)
        QMessageBox.information(self, APP_NAME, f"自检完成\n\n打开文档: {'通过' if report['open_pdf'] else '失败'}\n建立索引: {'通过' if report['index_ready'] else '失败'}\n搜索命中: {report['result_count']}\n本页信号: {report['page_signal_count']}\n收藏功能: {'通过' if report['favorite_count'] > 0 else '失败'}\n图标导出: {'通过' if report['icon_assets'] else '失败'}")

    def closeEvent(self, event) -> None:
        self.close_current_pdf()
        super().closeEvent(event)


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


def _wait_until(app: QApplication, predicate: Callable[[], bool], timeout_ms: int) -> bool:
    deadline = time.perf_counter() + timeout_ms / 1000.0
    while time.perf_counter() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def perform_app_self_test(pdf_path: str, query: str = DEFAULT_QUERY, report_path: str | None = None) -> dict:

    app = ensure_application()
    app.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory() as temp_dir:
        window = PdfApp(history_store_path=Path(temp_dir) / "history.json", state_store_path=Path(temp_dir) / "state.json", asset_dir=Path(temp_dir) / "assets", test_mode=True)
        window.show()
        app.processEvents()
        window.load_pdf(pdf_path)
        open_pdf = window.doc is not None and window.pdf_path is not None
        index_ready = _wait_until(app, lambda: window.index_ready, 15000)
        window.search_box.setCurrentText(query)
        window.search()
        if window.search_busy:
            _wait_until(app, lambda: not window.search_busy, 15000)
        result_count = window.result_list.count()
        if result_count > 0:
            first_item = window.result_list.item(0)
            window._on_result_double_clicked(first_item)
            _wait_until(app, lambda: not window.render_busy, 12000)
        else:
            _wait_until(app, lambda: not window.render_busy, 12000)
        window.fit_width(immediate=True)
        _wait_until(app, lambda: not window.render_busy, 12000)
        fit_width_zoom = window.zoom
        window.zoom_in()
        _wait_until(app, lambda: not window.render_busy, 12000)
        zoom_after_plus = window.zoom
        page_signal_count = window.page_signal_list.count()
        favorite_count = 0
        if result_count > 0:
            window.toggle_current_favorite()
            favorite_count = window.favorite_list.count()
        assets = export_icon_assets(window.asset_dir)
        icon_assets = Path(assets["png"]).exists() and Path(assets["ico"]).exists()
        report = {
            "open_pdf": open_pdf,
            "index_ready": index_ready,
            "result_count": result_count,
            "page_signal_count": page_signal_count,
            "favorite_count": favorite_count,
            "fit_width_zoom": fit_width_zoom,
            "zoom_after_plus": zoom_after_plus,
            "icon_assets": icon_assets,
            "document_title": window.document_label.text(),
        }
        if report_path:
            Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        app.processEvents()
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("pdf", nargs="?", help="启动后打开的 PDF 文件")
    parser.add_argument("--self-test", action="store_true", help="执行离线自检并退出")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="自检时使用的查询信号")
    parser.add_argument("--report", default="", help="自检报告输出路径")
    parser.add_argument("--generate-assets", action="store_true", help="生成程序图标资源")
    parser.add_argument("--assets-dir", default="assets", help="图标输出目录")
    args = parser.parse_args(argv)
    app = ensure_application()
    if args.generate_assets:
        export_icon_assets(Path(args.assets_dir))
        return 0
    if args.self_test:
        pdf_path = args.pdf or str(Path(__file__).resolve().parent / "test.pdf")
        if not os.path.exists(pdf_path):
            raise SystemExit(f"PDF not found: {pdf_path}")
        perform_app_self_test(pdf_path, args.query, args.report or None)
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)
    window = PdfApp()
    window.show()
    if args.pdf:
        QTimer.singleShot(0, lambda: window.load_pdf(args.pdf))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())





