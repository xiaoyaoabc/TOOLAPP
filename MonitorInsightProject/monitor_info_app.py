from __future__ import annotations

import argparse
from pathlib import Path

from PyQt6.QtCore import QSize, QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from monitor_info import (
    APP_NAME,
    MonitorSnapshot,
    collect_monitor_snapshots,
    ensure_application,
    input_source_label,
    save_snapshot_report,
    set_windows_app_id,
    snapshot_signature,
    snapshots_to_json,
    switch_monitor_input_source,
)

AUTO_REFRESH_INTERVAL_MS = 6000
SIGNAL_SWITCH_REFRESH_DELAY_MS = 900
SIGNAL_SWITCH_BUTTON_RESTORE_DELAY_MS = 1400

STYLE_SHEET = """
QMainWindow {
    background: #eef3f9;
}
QWidget {
    color: #132238;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 10.5pt;
}
QFrame#headerCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #17324d, stop:0.55 #1f5660, stop:1 #2f7a6b);
    border-radius: 22px;
}
QFrame#panelCard, QFrame#heroCard, QFrame#infoCard {
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid #d9e4f0;
    border-radius: 18px;
}
QLabel#heroTitle, QLabel#heroSubtitle, QLabel#heroMeta, QLabel#badgeLabel {
    color: white;
}
QLabel#heroTitle {
    font-size: 22pt;
    font-weight: 700;
}
QLabel#heroSubtitle {
    font-size: 11pt;
}
QLabel#heroMeta {
    font-size: 10pt;
}
QLabel#sectionTitle {
    font-size: 11pt;
    font-weight: 700;
}
QLabel#cardCaption {
    color: #62758c;
    font-size: 9.5pt;
}
QLabel#cardValue {
    color: #132238;
    font-size: 12.5pt;
    font-weight: 700;
}
QLabel#badgeLabel {
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 14px;
    padding: 8px 14px;
    font-weight: 700;
}
QListWidget {
    background: transparent;
    border: none;
    outline: none;
    padding: 6px;
}
QListWidget::item {
    background: white;
    border: 1px solid #d9e4f0;
    border-radius: 16px;
    margin: 6px 0;
    padding: 14px 16px;
}
QListWidget::item:selected {
    background: #183c56;
    color: white;
    border: 1px solid #183c56;
}
QPushButton, QComboBox {
    background: #f8fbff;
    border: 1px solid #d9e4f0;
    border-radius: 14px;
    padding: 10px 16px;
    font-weight: 700;
}
QPushButton:hover, QComboBox:hover {
    background: #e9f2fb;
}
QPushButton#accentButton {
    background: #1f5660;
    color: white;
    border: 1px solid #1f5660;
}
QPushButton#accentButton:hover {
    background: #18474f;
}
QComboBox#signalSelector {
    background: #183c56;
    color: white;
    border: 1px solid #183c56;
    selection-background-color: #183c56;
    selection-color: white;
}
QComboBox#signalSelector:hover {
    background: #214a68;
}
QComboBox#signalSelector QAbstractItemView {
    background: #183c56;
    color: white;
    border: 1px solid #2b6170;
    selection-background-color: #2b6170;
    selection-color: white;
}
QComboBox#signalSelector::drop-down {
    border: none;
}
QScrollArea {
    border: none;
    background: transparent;
}
QStatusBar {
    background: transparent;
    color: #4f6176;
}
"""

SWITCH_CONFIRM_DIALOG_STYLE = """
QMessageBox {
    background: #17324d;
}
QMessageBox QLabel {
    color: white;
    min-width: 360px;
    font-size: 10.5pt;
}
QMessageBox QPushButton {
    background: rgba(255, 255, 255, 0.14);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.24);
    border-radius: 12px;
    padding: 9px 18px;
    min-width: 96px;
    font-weight: 700;
}
QMessageBox QPushButton:hover {
    background: rgba(255, 255, 255, 0.22);
}
"""

CARD_FIELDS = [
    ("manufacturer", "厂商"),
    ("model", "型号"),
    ("serial_number", "序列号"),
    ("primary", "主显示器"),
    ("current_input_source", "当前信号"),
    ("supported_input_sources", "支持信号"),
    ("desktop_resolution", "桌面分辨率"),
    ("estimated_native_resolution", "估算原生分辨率"),
    ("refresh_rate_hz", "刷新率"),
    ("scale", "缩放比例"),
    ("orientation", "方向"),
    ("position", "屏幕位置"),
    ("work_area_resolution", "可用工作区"),
    ("physical_size_mm", "物理尺寸"),
    ("diagonal_inches", "屏幕对角线"),
    ("dpi", "DPI"),
    ("color_depth", "色深"),
]


class InfoCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("infoCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self.caption = QLabel(title)
        self.caption.setObjectName("cardCaption")
        self.caption.setWordWrap(True)
        self.value = QLabel("-")
        self.value.setObjectName("cardValue")
        self.value.setWordWrap(True)

        layout.addWidget(self.caption)
        layout.addWidget(self.value)
        layout.addStretch(1)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class MonitorInfoWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.snapshots: list[MonitorSnapshot] = []
        self._signature: tuple = ()
        self._selected_identity: tuple | None = None
        self.cards: dict[str, InfoCard] = {}
        self._build_ui()
        self._connect_runtime_signals()
        self.refresh_monitors(force=True)

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 840)
        self.setMinimumSize(1040, 720)
        self.setStyleSheet(STYLE_SHEET)
        self.setStatusBar(QStatusBar(self))
        self.setFont(QFont("Microsoft YaHei UI", 10))

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 12)
        root_layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 20, 22, 20)
        header_layout.setSpacing(18)

        title_column = QVBoxLayout()
        title_column.setSpacing(6)

        hero_title = QLabel("Monitor Insight")
        hero_title.setObjectName("heroTitle")
        hero_subtitle = QLabel(
            "实时识别显示器信息，并在显示器支持 DDC/CI 时显示当前信号、支持信号，以及切换输入源。"
        )
        hero_subtitle.setObjectName("heroSubtitle")
        hero_subtitle.setWordWrap(True)
        self.hero_meta = QLabel("准备检测显示器...")
        self.hero_meta.setObjectName("heroMeta")

        title_column.addWidget(hero_title)
        title_column.addWidget(hero_subtitle)
        title_column.addWidget(self.hero_meta)

        action_column = QVBoxLayout()
        action_column.setSpacing(12)
        action_column.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.count_badge = QLabel("0 台显示器")
        self.count_badge.setObjectName("badgeLabel")
        self.count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.refresh_button = QPushButton("刷新识别")
        self.refresh_button.setObjectName("accentButton")
        self.refresh_button.clicked.connect(lambda: self.refresh_monitors(force=True))
        self.export_button = QPushButton("导出 JSON")
        self.export_button.clicked.connect(self.export_snapshot)
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.export_button)

        action_column.addWidget(self.count_badge, 0, Qt.AlignmentFlag.AlignRight)
        action_column.addLayout(button_row)

        header_layout.addLayout(title_column, 1)
        header_layout.addLayout(action_column)
        root_layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_panel = QFrame()
        left_panel.setObjectName("panelCard")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        section_title = QLabel("已连接显示器")
        section_title.setObjectName("sectionTitle")
        left_layout.addWidget(section_title)

        self.monitor_list = QListWidget()
        self.monitor_list.currentRowChanged.connect(self.render_selected_monitor)
        left_layout.addWidget(self.monitor_list, 1)

        right_panel = QFrame()
        right_panel.setObjectName("panelCard")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_body = QWidget()
        scroll_layout = QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(16, 16, 16, 16)
        scroll_layout.setSpacing(14)

        hero_card = QFrame()
        hero_card.setObjectName("heroCard")
        hero_card_layout = QVBoxLayout(hero_card)
        hero_card_layout.setContentsMargins(20, 18, 20, 18)
        hero_card_layout.setSpacing(8)

        self.detail_title = QLabel("未检测到显示器")
        self.detail_title.setObjectName("sectionTitle")
        detail_title_font = self.detail_title.font()
        detail_title_font.setPointSize(16)
        detail_title_font.setBold(True)
        self.detail_title.setFont(detail_title_font)

        self.detail_subtitle = QLabel("请确认显示器已连接，或点击“刷新识别”。")
        self.detail_subtitle.setWordWrap(True)
        self.detail_position = QLabel("")
        self.detail_position.setObjectName("cardCaption")

        hero_card_layout.addWidget(self.detail_title)
        hero_card_layout.addWidget(self.detail_subtitle)
        hero_card_layout.addWidget(self.detail_position)
        scroll_layout.addWidget(hero_card)

        signal_card = QFrame()
        signal_card.setObjectName("panelCard")
        signal_layout = QVBoxLayout(signal_card)
        signal_layout.setContentsMargins(18, 16, 18, 16)
        signal_layout.setSpacing(12)

        signal_title = QLabel("信号源控制")
        signal_title.setObjectName("sectionTitle")
        signal_layout.addWidget(signal_title)

        signal_summary_row = QGridLayout()
        signal_summary_row.setHorizontalSpacing(18)
        signal_summary_row.setVerticalSpacing(10)

        current_label = QLabel("当前信号")
        current_label.setObjectName("cardCaption")
        self.current_signal_value = QLabel("未读取")
        self.current_signal_value.setObjectName("cardValue")
        self.current_signal_value.setWordWrap(True)

        supported_label = QLabel("支持的信号")
        supported_label.setObjectName("cardCaption")
        self.supported_signal_value = QLabel("未读取")
        self.supported_signal_value.setObjectName("cardValue")
        self.supported_signal_value.setWordWrap(True)

        signal_summary_row.addWidget(current_label, 0, 0)
        signal_summary_row.addWidget(self.current_signal_value, 0, 1)
        signal_summary_row.addWidget(supported_label, 1, 0)
        signal_summary_row.addWidget(self.supported_signal_value, 1, 1)
        signal_layout.addLayout(signal_summary_row)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(10)
        selector_caption = QLabel("切换到")
        selector_caption.setObjectName("cardCaption")
        self.signal_selector = QComboBox()
        self.signal_selector.setObjectName("signalSelector")
        self.signal_selector.setMinimumWidth(240)
        self.switch_signal_button = QPushButton("切换信号")
        self.switch_signal_button.setObjectName("accentButton")
        self.switch_signal_button.clicked.connect(self.switch_selected_signal)
        selector_row.addWidget(selector_caption)
        selector_row.addWidget(self.signal_selector, 1)
        selector_row.addWidget(self.switch_signal_button)
        signal_layout.addLayout(selector_row)

        self.signal_status = QLabel("提示：需要显示器开启 DDC/CI，且显示器本身支持输入源控制，才可以读取并切换信号。")
        self.signal_status.setObjectName("cardCaption")
        self.signal_status.setWordWrap(True)
        signal_layout.addWidget(self.signal_status)

        scroll_layout.addWidget(signal_card)

        self.card_grid = QGridLayout()
        self.card_grid.setHorizontalSpacing(14)
        self.card_grid.setVerticalSpacing(14)
        for index, (field_key, title) in enumerate(CARD_FIELDS):
            card = InfoCard(title)
            row = index // 2
            column = index % 2
            self.card_grid.addWidget(card, row, column)
            self.cards[field_key] = card
        scroll_layout.addLayout(self.card_grid)

        self.detail_hint = QLabel(
            "提示：桌面分辨率为 Windows 当前桌面坐标大小；估算原生分辨率会结合系统缩放进行换算；信号源信息依赖显示器 DDC/CI。"
        )
        self.detail_hint.setObjectName("cardCaption")
        self.detail_hint.setWordWrap(True)
        scroll_layout.addWidget(self.detail_hint)
        scroll_layout.addStretch(1)

        scroll.setWidget(scroll_body)
        right_layout.addWidget(scroll)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([360, 860])
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self._reset_signal_controls()

    def _connect_runtime_signals(self) -> None:
        self.app.screenAdded.connect(lambda _screen: self.refresh_monitors(force=True))
        self.app.screenRemoved.connect(lambda _screen: self.refresh_monitors(force=True))
        self.app.primaryScreenChanged.connect(lambda _screen: self.refresh_monitors(force=True))

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(AUTO_REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self.refresh_monitors)
        self.refresh_timer.start()

    def refresh_monitors(self, force: bool = False) -> None:
        snapshots = collect_monitor_snapshots(self.app)
        signature = snapshot_signature(snapshots)
        if not force and signature == self._signature:
            return

        current_item = self.monitor_list.currentItem()
        if current_item is not None:
            self._selected_identity = current_item.data(Qt.ItemDataRole.UserRole)

        self.snapshots = snapshots
        self._signature = signature
        controllable_count = sum(1 for snapshot in self.snapshots if snapshot.input_switch_supported)
        self._populate_monitor_list()
        self.count_badge.setText(f"{len(self.snapshots)} 台显示器")
        self.hero_meta.setText(
            f"最近一次识别：共检测到 {len(self.snapshots)} 台显示器，其中 {controllable_count} 台支持信号切换"
        )
        self.statusBar().showMessage("显示器信息已更新", 3000)

    def _populate_monitor_list(self) -> None:
        self.monitor_list.blockSignals(True)
        self.monitor_list.clear()

        for snapshot in self.snapshots:
            summary_bits = [
                f"{snapshot.desktop_resolution[0]} x {snapshot.desktop_resolution[1]}",
                f"{snapshot.refresh_rate_hz:.3f} Hz",
                f"{snapshot.scale_percent}%",
            ]
            if snapshot.current_input_source_code is not None:
                summary_bits.append(snapshot.current_input_source_label)
            if snapshot.is_primary:
                summary_bits.insert(0, "主显示器")
            summary = " | ".join(summary_bits)
            subtitle = snapshot.manufacturer or "未知厂商"
            item = QListWidgetItem(f"{snapshot.display_title}\n{subtitle}\n{summary}")
            item.setData(Qt.ItemDataRole.UserRole, snapshot.identity)
            item.setSizeHint(QSize(0, 92))
            self.monitor_list.addItem(item)

        target_row = 0
        if self._selected_identity is not None:
            for row, snapshot in enumerate(self.snapshots):
                if snapshot.identity == self._selected_identity:
                    target_row = row
                    break

        self.monitor_list.blockSignals(False)
        if self.snapshots:
            self.monitor_list.setCurrentRow(target_row)
            self.render_selected_monitor(target_row)
        else:
            self.render_empty_state()

    def render_selected_monitor(self, row: int) -> None:
        if row < 0 or row >= len(self.snapshots):
            self.render_empty_state()
            return

        snapshot = self.snapshots[row]
        self._selected_identity = snapshot.identity

        self.detail_title.setText(snapshot.display_title)
        self.detail_subtitle.setText(
            f"{snapshot.manufacturer or '未知厂商'}  |  序列号：{snapshot.serial_number or '未提供'}"
        )
        self.detail_position.setText(
            f"位置：({snapshot.position[0]}, {snapshot.position[1]})   |   "
            f"{'主显示器' if snapshot.is_primary else '扩展显示器'}"
        )

        self.cards["manufacturer"].set_value(snapshot.manufacturer or "未提供")
        self.cards["model"].set_value(snapshot.model or snapshot.name or "未提供")
        self.cards["serial_number"].set_value(snapshot.serial_number or "未提供")
        self.cards["primary"].set_value("是" if snapshot.is_primary else "否")
        self.cards["current_input_source"].set_value(snapshot.current_input_source_text)
        self.cards["supported_input_sources"].set_value(snapshot.supported_input_source_text)
        self.cards["desktop_resolution"].set_value(
            f"{snapshot.desktop_resolution[0]} x {snapshot.desktop_resolution[1]}"
        )
        self.cards["estimated_native_resolution"].set_value(
            f"{snapshot.estimated_native_resolution[0]} x {snapshot.estimated_native_resolution[1]}"
        )
        self.cards["refresh_rate_hz"].set_value(f"{snapshot.refresh_rate_hz:.3f} Hz")
        self.cards["scale"].set_value(f"{snapshot.scale_percent}%  ({snapshot.scale_factor:.3f}x)")
        self.cards["orientation"].set_value(snapshot.orientation)
        self.cards["position"].set_value(f"X={snapshot.position[0]}, Y={snapshot.position[1]}")
        self.cards["work_area_resolution"].set_value(
            f"{snapshot.work_area_resolution[0]} x {snapshot.work_area_resolution[1]}"
        )
        if snapshot.physical_size_mm[0] > 0 and snapshot.physical_size_mm[1] > 0:
            physical_size = f"{snapshot.physical_size_mm[0]:.1f} x {snapshot.physical_size_mm[1]:.1f} mm"
        else:
            physical_size = "未提供"
        self.cards["physical_size_mm"].set_value(physical_size)
        self.cards["diagonal_inches"].set_value(
            f"{snapshot.diagonal_inches:.2f} 英寸" if snapshot.diagonal_inches > 0 else "未提供"
        )
        self.cards["dpi"].set_value(
            f"逻辑 {snapshot.logical_dpi:.2f} / 物理 {snapshot.physical_dpi:.2f}"
        )
        self.cards["color_depth"].set_value(f"{snapshot.color_depth} bit")

        self._update_signal_controls(snapshot)

    def _update_signal_controls(self, snapshot: MonitorSnapshot) -> None:
        self.current_signal_value.setText(snapshot.current_input_source_text)
        self.supported_signal_value.setText(snapshot.supported_input_source_text)

        self.signal_selector.blockSignals(True)
        self.signal_selector.clear()
        for option in snapshot.supported_input_sources:
            self.signal_selector.addItem(option.display_text, option.code)
        if snapshot.current_input_source_code is not None:
            current_index = self.signal_selector.findData(snapshot.current_input_source_code)
            if current_index >= 0:
                self.signal_selector.setCurrentIndex(current_index)
        self.signal_selector.blockSignals(False)

        can_switch = snapshot.input_switch_supported and len(snapshot.supported_input_sources) > 1
        self.signal_selector.setEnabled(can_switch)
        self.switch_signal_button.setEnabled(can_switch)

        if can_switch:
            self.signal_status.setText(
                "当前显示器支持通过 DDC/CI 切换输入源。已减少多显示器下的刷新阻塞，切换后会做一次较快的状态同步。"
            )
        elif snapshot.current_input_source_code is not None:
            self.signal_status.setText(
                snapshot.input_control_error
                or "已读取到当前信号，但没有拿到可切换的完整输入源列表。"
            )
        else:
            self.signal_status.setText(
                snapshot.input_control_error
                or "当前显示器没有暴露 DDC/CI 输入源信息，常见原因是显示器菜单里未开启 DDC/CI。"
            )

    def _reset_signal_controls(self) -> None:
        self.current_signal_value.setText("未读取")
        self.supported_signal_value.setText("未读取")
        self.signal_selector.clear()
        self.signal_selector.setEnabled(False)
        self.switch_signal_button.setEnabled(False)
        self.signal_status.setText("提示：需要显示器开启 DDC/CI，且显示器本身支持输入源控制，才可以读取并切换信号。")

    def _confirm_signal_switch(self, snapshot: MonitorSnapshot, target_label: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("确认切换信号源")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(
            (
                f"准备将 {snapshot.display_title} 切换到 {target_label}。\n\n"
                "切换后显示器可能会暂时黑屏；如果该输入口没有有效信号，你需要手动切回原输入源。\n\n"
                "是否继续？"
            )
        )
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setStyleSheet(SWITCH_CONFIRM_DIALOG_STYLE)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def switch_selected_signal(self) -> None:
        row = self.monitor_list.currentRow()
        if row < 0 or row >= len(self.snapshots):
            return

        snapshot = self.snapshots[row]
        target_code = self.signal_selector.currentData()
        if target_code is None:
            self.statusBar().showMessage("当前没有可切换的目标信号", 4000)
            return

        target_code = int(target_code)
        target_label = input_source_label(target_code)
        if target_code == snapshot.current_input_source_code:
            self.statusBar().showMessage(f"{snapshot.display_title} 当前已经是 {target_label}", 4000)
            return

        if not self._confirm_signal_switch(snapshot, target_label):
            return

        self.refresh_timer.stop()
        self.switch_signal_button.setEnabled(False)
        self.statusBar().showMessage(f"正在切换 {snapshot.display_title} 到 {target_label}...", 5000)
        success, message = switch_monitor_input_source(snapshot, target_code)
        self.statusBar().showMessage(message, 7000)
        QTimer.singleShot(SIGNAL_SWITCH_REFRESH_DELAY_MS, lambda: self.refresh_monitors(force=True))
        QTimer.singleShot(SIGNAL_SWITCH_BUTTON_RESTORE_DELAY_MS, self._restore_switch_button_state)

        if success:
            self.signal_status.setText(
                f"切换命令已发送到 {target_label}。如果目标端口没有信号，显示器可能会保持黑屏，需在显示器菜单里手动切回。"
            )

    def _restore_switch_button_state(self) -> None:
        row = self.monitor_list.currentRow()
        if row < 0 or row >= len(self.snapshots):
            self.switch_signal_button.setEnabled(False)
        else:
            snapshot = self.snapshots[row]
            self.switch_signal_button.setEnabled(snapshot.input_switch_supported and len(snapshot.supported_input_sources) > 1)
        if not self.refresh_timer.isActive():
            self.refresh_timer.start(AUTO_REFRESH_INTERVAL_MS)

    def render_empty_state(self) -> None:
        self.detail_title.setText("未检测到显示器")
        self.detail_subtitle.setText("请确认显示器连接正常，然后点击“刷新识别”。")
        self.detail_position.setText("")
        for card in self.cards.values():
            card.set_value("-")
        self._reset_signal_controls()

    def export_snapshot(self) -> None:
        if not self.snapshots:
            self.statusBar().showMessage("当前没有可导出的显示器信息", 4000)
            return

        default_path = Path.cwd() / "monitor_snapshot.json"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出显示器信息",
            str(default_path),
            "JSON 文件 (*.json)",
        )
        if not output_path:
            return

        save_snapshot_report(output_path, self.snapshots)
        self.statusBar().showMessage(f"已导出到 {output_path}", 5000)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="识别当前电脑连接的显示器信息")
    parser.add_argument("--json", action="store_true", help="在终端输出显示器信息 JSON 并退出")
    parser.add_argument("--json-path", default="", help="将显示器信息导出到指定 JSON 文件并退出")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    set_windows_app_id()
    app = ensure_application()

    if args.json or args.json_path:
        snapshots = collect_monitor_snapshots(app)
        payload = snapshots_to_json(snapshots)
        if args.json:
            print(payload)
        if args.json_path:
            save_snapshot_report(args.json_path, snapshots)
        return 0

    window = MonitorInfoWindow(app)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

