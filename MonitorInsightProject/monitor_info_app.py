from __future__ import annotations

import argparse
import html

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from monitor_info import (
    APP_NAME,
    MonitorSnapshot,
    close_monitor_input_session,
    collect_monitor_snapshots,
    ensure_application,
    input_source_label,
    open_monitor_input_session,
    read_monitor_input_source,
    save_snapshot_report,
    set_monitor_input_session_source,
    set_windows_app_id,
    snapshot_signature,
    snapshots_to_json,
)

AUTO_REFRESH_INTERVAL_MS = 6000
SWITCH_VERIFY_DELAY_MS = 5000
SWITCH_RECOVERY_REFRESH_DELAY_MS = 1300

STYLE_SHEET = """
QMainWindow {
    background: #eef2f5;
}
QWidget {
    color: #172b3a;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 10pt;
}
QFrame#card {
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid #d7dfe7;
    border-radius: 16px;
}
QLabel#windowTitle {
    color: #183447;
    font-size: 16pt;
    font-weight: 700;
}
QLabel#summaryLabel {
    color: #5e7182;
    font-size: 9.4pt;
}
QLabel#sectionTitle {
    color: #183447;
    font-size: 10.2pt;
    font-weight: 700;
}
QLabel#monitorTitle {
    color: #183447;
    font-size: 11.8pt;
    font-weight: 700;
}
QLabel#captionLabel {
    color: #718395;
    font-size: 9.2pt;
}
QLabel#signalValue {
    color: #183447;
    font-size: 10.6pt;
    font-weight: 700;
}
QLabel#statusLabel {
    color: #506273;
    font-size: 9.1pt;
}
QPushButton, QComboBox {
    background: #f8fafc;
    border: 1px solid #d7dfe7;
    border-radius: 11px;
    padding: 8px 12px;
    font-weight: 700;
}
QPushButton:hover, QComboBox:hover {
    background: #edf3f8;
}
QPushButton#accentButton {
    background: #183447;
    color: white;
    border: 1px solid #183447;
}
QPushButton#accentButton:hover {
    background: #244960;
}
QPushButton#monitorSelectButton {
    background: #f8fafc;
    border: 1px solid #dfe6ee;
    border-radius: 12px;
    color: #183447;
    min-height: 54px;
    padding: 10px 12px;
    text-align: left;
}
QPushButton#monitorSelectButton:hover {
    background: #edf3f8;
}
QPushButton#monitorSelectButton:checked {
    background: #183447;
    color: white;
    border: 1px solid #183447;
}
QPushButton:disabled, QComboBox:disabled {
    color: #94a2af;
    background: #f3f6f8;
    border: 1px solid #dfe6ec;
}
QComboBox#signalSelector {
    background: #183447;
    color: white;
    border: 1px solid #183447;
    selection-background-color: #183447;
    selection-color: white;
}
QComboBox#signalSelector:hover {
    background: #244960;
}
QComboBox#signalSelector QAbstractItemView {
    background: #183447;
    color: white;
    border: 1px solid #244960;
    selection-background-color: #2c5874;
    selection-color: white;
}
QComboBox#signalSelector::drop-down {
    border: none;
}
QStatusBar {
    background: transparent;
    color: #5e7182;
}
"""

DETAIL_DIALOG_STYLE = """
QDialog {
    background: #f4f8fb;
}
QTextBrowser {
    background: white;
    border: 1px solid #dbe5ef;
    border-radius: 12px;
    padding: 8px;
    color: #182838;
}
QPushButton {
    background: #183447;
    color: white;
    border: 1px solid #183447;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 700;
}
QPushButton:hover {
    background: #244960;
}
"""

SWITCH_CONFIRM_DIALOG_STYLE = """
QMessageBox {
    background: #17324d;
}
QMessageBox QLabel {
    color: white;
    min-width: 320px;
    font-size: 10.1pt;
}
QMessageBox QPushButton {
    background: rgba(255, 255, 255, 0.14);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.24);
    border-radius: 11px;
    padding: 8px 16px;
    min-width: 90px;
    font-weight: 700;
}
QMessageBox QPushButton:hover {
    background: rgba(255, 255, 255, 0.22);
}
"""


class MonitorDetailDialog(QDialog):
    def __init__(self, snapshot: MonitorSnapshot, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{snapshot.display_title} - 显示器信息")
        self.resize(500, 560)
        self.setMinimumSize(430, 460)
        self.setStyleSheet(DETAIL_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._build_html(snapshot))
        layout.addWidget(browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _build_html(self, snapshot: MonitorSnapshot) -> str:
        rows = [
            ("显示器", snapshot.display_title),
            ("厂商", snapshot.manufacturer or "未提供"),
            ("型号", snapshot.model or snapshot.name or "未提供"),
            ("序列号", snapshot.serial_number or "未提供"),
            ("主显示器", "是" if snapshot.is_primary else "否"),
            ("当前信号", snapshot.current_input_source_text),
            ("支持信号", snapshot.supported_input_source_text),
            ("桌面分辨率", f"{snapshot.desktop_resolution[0]} x {snapshot.desktop_resolution[1]}"),
            (
                "估算原生分辨率",
                f"{snapshot.estimated_native_resolution[0]} x {snapshot.estimated_native_resolution[1]}",
            ),
            ("刷新率", f"{snapshot.refresh_rate_hz:.3f} Hz"),
            ("缩放比例", f"{snapshot.scale_percent}% ({snapshot.scale_factor:.3f}x)"),
            ("方向", snapshot.orientation),
            ("屏幕位置", f"X={snapshot.position[0]}, Y={snapshot.position[1]}"),
            ("可用工作区", f"{snapshot.work_area_resolution[0]} x {snapshot.work_area_resolution[1]}"),
            (
                "物理尺寸",
                (
                    f"{snapshot.physical_size_mm[0]:.1f} x {snapshot.physical_size_mm[1]:.1f} mm"
                    if snapshot.physical_size_mm[0] > 0 and snapshot.physical_size_mm[1] > 0
                    else "未提供"
                ),
            ),
            (
                "屏幕对角线",
                f"{snapshot.diagonal_inches:.2f} 英寸" if snapshot.diagonal_inches > 0 else "未提供",
            ),
            ("DPI", f"逻辑 {snapshot.logical_dpi:.2f} / 物理 {snapshot.physical_dpi:.2f}"),
            ("色深", f"{snapshot.color_depth} bit"),
            ("DDC/CI", "支持" if snapshot.ddc_ci_supported else "未检测到"),
            ("系统显示设备名", snapshot.gdi_device_name or "未提供"),
            ("物理显示器描述", snapshot.physical_monitor_description or "未提供"),
            ("输入源状态", snapshot.input_control_error or "正常"),
        ]
        table_rows = "".join(
            "<tr>"
            f"<td style='padding:8px 10px;color:#6a7f95;font-weight:700;width:148px'>{html.escape(label)}</td>"
            f"<td style='padding:8px 10px;color:#182838'>{html.escape(value)}</td>"
            "</tr>"
            for label, value in rows
        )
        return (
            "<html><body style='font-family:Microsoft YaHei UI, Segoe UI; background:#ffffff;'>"
            "<h2 style='color:#183447;margin:4px 0 12px 0'>显示器详细信息</h2>"
            "<table style='width:100%; border-collapse:collapse;'>"
            f"{table_rows}"
            "</table></body></html>"
        )


class MonitorInfoWindow(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.snapshots: list[MonitorSnapshot] = []
        self._signature: tuple = ()
        self._selected_identity: tuple | None = None
        self._pending_switch: dict | None = None
        self._monitor_buttons: list[QPushButton] = []
        self._build_ui()
        self._connect_runtime_signals()
        self.refresh_monitors(force=True)

    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.resize(520, 560)
        self.setMinimumSize(520, 560)
        self.setStyleSheet(STYLE_SHEET)
        self.setStatusBar(QStatusBar(self))
        self.setFont(QFont("Microsoft YaHei UI", 10))

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("card")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 14)
        header_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("Monitor Insight")
        title.setObjectName("windowTitle")
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("accentButton")
        self.refresh_button.clicked.connect(lambda: self.refresh_monitors(force=True))
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.refresh_button)

        self.summary_label = QLabel("正在检测显示器...")
        self.summary_label.setObjectName("summaryLabel")
        self.summary_label.setWordWrap(True)

        header_layout.addLayout(title_row)
        header_layout.addWidget(self.summary_label)
        layout.addWidget(header)

        monitors_panel = QFrame()
        monitors_panel.setObjectName("card")
        monitors_layout = QVBoxLayout(monitors_panel)
        monitors_layout.setContentsMargins(14, 14, 14, 14)
        monitors_layout.setSpacing(8)

        monitors_title = QLabel("按键选择显示器")
        monitors_title.setObjectName("sectionTitle")
        self.monitor_count_label = QLabel("0 台显示器")
        self.monitor_count_label.setObjectName("captionLabel")
        self.monitor_empty_label = QLabel("当前没有检测到显示器")
        self.monitor_empty_label.setObjectName("captionLabel")
        self.monitor_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.monitor_button_group = QButtonGroup(self)
        self.monitor_button_group.setExclusive(True)
        self.monitor_button_container = QWidget()
        self.monitor_button_layout = QVBoxLayout(self.monitor_button_container)
        self.monitor_button_layout.setContentsMargins(0, 0, 0, 0)
        self.monitor_button_layout.setSpacing(8)

        monitors_layout.addWidget(monitors_title)
        monitors_layout.addWidget(self.monitor_count_label)
        monitors_layout.addWidget(self.monitor_empty_label)
        monitors_layout.addWidget(self.monitor_button_container, 1)
        layout.addWidget(monitors_panel, 1)

        switch_panel = QFrame()
        switch_panel.setObjectName("card")
        switch_layout = QVBoxLayout(switch_panel)
        switch_layout.setContentsMargins(14, 14, 14, 14)
        switch_layout.setSpacing(8)

        switch_title = QLabel("切换显示信号")
        switch_title.setObjectName("sectionTitle")
        self.selected_monitor_label = QLabel("未检测到显示器")
        self.selected_monitor_label.setObjectName("monitorTitle")
        self.selected_monitor_summary = QLabel("请先连接显示器")
        self.selected_monitor_summary.setObjectName("captionLabel")
        self.current_signal_label = QLabel("当前信号：未读取")
        self.current_signal_label.setObjectName("signalValue")
        self.supported_signal_label = QLabel("支持信号：未提供")
        self.supported_signal_label.setObjectName("captionLabel")
        self.supported_signal_label.setWordWrap(True)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        self.signal_selector = QComboBox()
        self.signal_selector.setObjectName("signalSelector")
        self.signal_selector.setMinimumWidth(250)
        self.switch_signal_button = QPushButton("切换")
        self.switch_signal_button.setObjectName("accentButton")
        self.switch_signal_button.clicked.connect(self.switch_selected_signal)
        selector_row.addWidget(self.signal_selector, 1)
        selector_row.addWidget(self.switch_signal_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.details_button = QPushButton("显示器信息")
        self.details_button.clicked.connect(self.open_monitor_details)
        action_row.addWidget(self.details_button)
        action_row.addStretch(1)

        self.signal_status = QLabel("切换后 5 秒会尽量校验；只有明确检测到切换未生效时才自动切回。")
        self.signal_status.setObjectName("statusLabel")
        self.signal_status.setWordWrap(True)

        switch_layout.addWidget(switch_title)
        switch_layout.addWidget(self.selected_monitor_label)
        switch_layout.addWidget(self.selected_monitor_summary)
        switch_layout.addWidget(self.current_signal_label)
        switch_layout.addWidget(self.supported_signal_label)
        switch_layout.addLayout(selector_row)
        switch_layout.addLayout(action_row)
        switch_layout.addWidget(self.signal_status)
        layout.addWidget(switch_panel)

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

        self.switch_verify_timer = QTimer(self)
        self.switch_verify_timer.setSingleShot(True)
        self.switch_verify_timer.timeout.connect(self._verify_pending_switch)

    def _current_snapshot(self) -> MonitorSnapshot | None:
        snapshot = self._find_snapshot_by_identity(self._selected_identity)
        if snapshot is not None:
            return snapshot
        if self.snapshots:
            return self.snapshots[0]
        return None

    def _find_snapshot_by_identity(self, identity: tuple | None) -> MonitorSnapshot | None:
        if identity is None:
            return None
        for snapshot in self.snapshots:
            if snapshot.identity == identity:
                return snapshot
        return None

    def refresh_monitors(self, force: bool = False) -> None:
        snapshots = collect_monitor_snapshots(self.app)
        signature = snapshot_signature(snapshots)
        if not force and signature == self._signature:
            return

        self.snapshots = snapshots
        self._signature = signature
        self._populate_monitor_buttons()
        count = len(self.snapshots)
        self.monitor_count_label.setText(f"{count} 台显示器")
        self.summary_label.setText(
            f"当前识别到 {count} 台显示器。点击按键选择显示器，窗口也支持放大和全屏。"
        )
        self.statusBar().showMessage("显示器信息已更新", 2200)

    def _clear_monitor_buttons(self) -> None:
        while self.monitor_button_layout.count():
            item = self.monitor_button_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self.monitor_button_group.removeButton(widget)
                widget.deleteLater()
        self._monitor_buttons = []

    def _populate_monitor_buttons(self) -> None:
        self._clear_monitor_buttons()

        if not self.snapshots:
            self.monitor_empty_label.show()
            self.monitor_button_container.hide()
            self.render_empty_state()
            return

        self.monitor_empty_label.hide()
        self.monitor_button_container.show()

        target_identity = self._selected_identity
        if self._find_snapshot_by_identity(target_identity) is None:
            target_identity = self.snapshots[0].identity

        for snapshot in self.snapshots:
            top_line = snapshot.display_title
            if snapshot.is_primary:
                top_line += "  ·  主显示器"
            signal_text = snapshot.current_input_source_label if snapshot.current_input_source_code is not None else "未读取"
            button = QPushButton(
                f"{top_line}\n{snapshot.desktop_resolution[0]} x {snapshot.desktop_resolution[1]}  ·  {signal_text}"
            )
            button.setObjectName("monitorSelectButton")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, identity=snapshot.identity: self.select_monitor(identity)
            )
            self.monitor_button_group.addButton(button)
            self.monitor_button_layout.addWidget(button)
            self._monitor_buttons.append(button)

        self.monitor_button_layout.addStretch(1)
        self._selected_identity = target_identity
        self._sync_monitor_button_states()
        self.render_selected_monitor(self._current_snapshot())

    def _sync_monitor_button_states(self) -> None:
        for button, snapshot in zip(self._monitor_buttons, self.snapshots):
            button.blockSignals(True)
            button.setChecked(snapshot.identity == self._selected_identity)
            button.blockSignals(False)

    def select_monitor(self, identity: tuple) -> None:
        if self._selected_identity == identity:
            self._sync_monitor_button_states()
            self.render_selected_monitor(self._current_snapshot())
            return
        self._selected_identity = identity
        self._sync_monitor_button_states()
        self.render_selected_monitor(self._current_snapshot())

    def render_selected_monitor(self, snapshot: MonitorSnapshot | None) -> None:
        if snapshot is None:
            self.render_empty_state()
            return

        self._selected_identity = snapshot.identity
        self.selected_monitor_label.setText(snapshot.display_title)
        self.selected_monitor_summary.setText(
            f"{snapshot.manufacturer or '未知厂商'}  ·  {snapshot.refresh_rate_hz:.3f} Hz  ·  缩放 {snapshot.scale_percent}%"
        )
        self._update_signal_controls(snapshot)
        self._sync_monitor_button_states()

    def _update_signal_controls(self, snapshot: MonitorSnapshot) -> None:
        self.details_button.setEnabled(True)
        self.current_signal_label.setText(f"当前信号：{snapshot.current_input_source_text}")
        self.supported_signal_label.setText(f"支持信号：{snapshot.supported_input_source_text}")

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
        busy = self._pending_switch is not None
        self.signal_selector.setEnabled(can_switch and not busy)
        self.switch_signal_button.setEnabled(can_switch and not busy)
        self.refresh_button.setEnabled(not busy)

        for button in self._monitor_buttons:
            button.setEnabled(not busy)

        if busy:
            self.signal_status.setText("切换命令已发送，正在等待 5 秒校验；只有明确检测到未生效时才会自动切回。")
        elif can_switch:
            self.signal_status.setText("先点上方按键选择显示器，再选择目标信号。程序只会在明确检测到切换未生效时才自动切回。")
        elif snapshot.current_input_source_code is not None:
            self.signal_status.setText(snapshot.input_control_error or "已读取当前信号，但当前无法执行切换。")
        else:
            self.signal_status.setText(snapshot.input_control_error or "当前显示器未返回可用的 DDC/CI 输入源信息。")

    def _reset_signal_controls(self) -> None:
        self.details_button.setEnabled(False)
        self.selected_monitor_label.setText("未检测到显示器")
        self.selected_monitor_summary.setText("请连接显示器后点击刷新")
        self.current_signal_label.setText("当前信号：未读取")
        self.supported_signal_label.setText("支持信号：未提供")
        self.signal_selector.clear()
        self.signal_selector.setEnabled(False)
        self.switch_signal_button.setEnabled(False)
        self.refresh_button.setEnabled(True)
        for button in self._monitor_buttons:
            button.setEnabled(True)
        self.signal_status.setText("切换后 5 秒会尽量校验；只有明确检测到切换未生效时才自动切回。")

    def render_empty_state(self) -> None:
        self._selected_identity = None
        self._reset_signal_controls()

    def open_monitor_details(self) -> None:
        snapshot = self._current_snapshot()
        if snapshot is None:
            return
        dialog = MonitorDetailDialog(snapshot, self)
        dialog.exec()

    def _confirm_signal_switch(self, snapshot: MonitorSnapshot, target_label: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("确认切换信号源")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(
            (
                f"准备将 {snapshot.display_title} 切换到 {target_label}。\n\n"
                "5 秒后会尽量检查切换结果；只有在明确检测到切换未生效时才会自动切回，避免正常切换被误判。\n\n"
                "是否继续？"
            )
        )
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        dialog.setStyleSheet(SWITCH_CONFIRM_DIALOG_STYLE)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def switch_selected_signal(self) -> None:
        snapshot = self._current_snapshot()
        if snapshot is None:
            return

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

        self._clear_pending_switch()
        self.refresh_timer.stop()
        self.switch_verify_timer.stop()
        self.refresh_button.setEnabled(False)
        self.signal_selector.setEnabled(False)
        self.switch_signal_button.setEnabled(False)
        for button in self._monitor_buttons:
            button.setEnabled(False)

        session, message = open_monitor_input_session(snapshot)
        if session is None:
            self.signal_status.setText(f"切换失败：{message}")
            self.refresh_button.setEnabled(True)
            self._update_signal_controls(snapshot)
            self.statusBar().showMessage(message, 6000)
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(AUTO_REFRESH_INTERVAL_MS)
            return

        success, message = set_monitor_input_session_source(session, target_code, snapshot.display_title)
        if not success:
            close_monitor_input_session(session)
            self.signal_status.setText(f"切换失败：{message}")
            self.refresh_button.setEnabled(True)
            self._update_signal_controls(snapshot)
            self.statusBar().showMessage(message, 6000)
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(AUTO_REFRESH_INTERVAL_MS)
            return

        self._pending_switch = {
            "identity": snapshot.identity,
            "display_title": snapshot.display_title,
            "original_code": snapshot.current_input_source_code,
            "target_code": target_code,
            "target_label": target_label,
            "session": session,
        }
        self.signal_status.setText(
            f"已发送切换命令到 {target_label}。5 秒后会校验；只有明确检测到未生效时才会自动切回。"
        )
        self.statusBar().showMessage(message, 5000)
        self.switch_verify_timer.start(SWITCH_VERIFY_DELAY_MS)

    def _verify_pending_switch(self) -> None:
        pending = self._pending_switch
        if pending is None:
            self._restore_after_switch_flow()
            return

        self.refresh_monitors(force=True)
        latest_snapshot = self._find_snapshot_by_identity(pending["identity"])
        session = pending.get("session")
        target_code = int(pending["target_code"])
        original_code = pending["original_code"]
        target_label = str(pending["target_label"])

        current_code, current_error = read_monitor_input_source(session)
        latest_code = latest_snapshot.current_input_source_code if latest_snapshot is not None else None
        current_confirms_target = current_code == target_code
        latest_confirms_target = latest_code == target_code
        target_confirmed = current_confirms_target or latest_confirms_target

        if target_confirmed:
            self.signal_status.setText(f"已确认目标信号有效：{target_label}。")
            self.statusBar().showMessage(f"切换成功：{pending['display_title']} -> {target_label}", 6000)
            self._restore_after_switch_flow(schedule_refresh_ms=SWITCH_RECOVERY_REFRESH_DELAY_MS)
            return

        target_clearly_invalid = latest_snapshot is not None and (
            (latest_code is not None and latest_code != target_code)
            or (current_code is not None and current_code != target_code)
        )

        if not target_clearly_invalid:
            self.signal_status.setText(
                f"5 秒后暂时无法明确确认 {target_label} 的状态，已保留当前切换结果，不自动切回。"
            )
            self.statusBar().showMessage(
                current_error or "未能明确确认目标信号状态，已保留当前切换结果",
                7000,
            )
            self._restore_after_switch_flow(schedule_refresh_ms=SWITCH_RECOVERY_REFRESH_DELAY_MS)
            return

        if original_code is None:
            self.signal_status.setText(f"已明确检测到 {target_label} 未生效，但原始信号未知，无法自动切回。")
            self.statusBar().showMessage("已明确检测到目标信号无效，但自动切回不可用", 7000)
            self._restore_after_switch_flow(schedule_refresh_ms=SWITCH_RECOVERY_REFRESH_DELAY_MS)
            return

        revert_label = input_source_label(int(original_code))
        success, message = set_monitor_input_session_source(session, int(original_code), pending["display_title"])
        if success:
            self.signal_status.setText(f"已明确检测到目标信号未生效，已尝试自动切回 {revert_label}。")
            self.statusBar().showMessage(f"目标信号未生效，已尝试切回 {revert_label}", 8000)
        else:
            self.signal_status.setText(f"已明确检测到目标信号未生效，但自动切回失败：{message}")
            self.statusBar().showMessage(f"自动切回失败：{message}", 8000)
        self._restore_after_switch_flow(schedule_refresh_ms=SWITCH_RECOVERY_REFRESH_DELAY_MS)

    def _clear_pending_switch(self) -> None:
        if self._pending_switch is None:
            return
        session = self._pending_switch.get("session")
        if session is not None:
            close_monitor_input_session(session)
        self._pending_switch = None

    def _restore_after_switch_flow(self, schedule_refresh_ms: int | None = None) -> None:
        self._clear_pending_switch()
        if not self.refresh_timer.isActive():
            self.refresh_timer.start(AUTO_REFRESH_INTERVAL_MS)
        self.refresh_button.setEnabled(True)
        current_snapshot = self._current_snapshot()
        if current_snapshot is not None:
            self._update_signal_controls(current_snapshot)
        else:
            self._reset_signal_controls()
        if schedule_refresh_ms is not None:
            QTimer.singleShot(schedule_refresh_ms, lambda: self.refresh_monitors(force=True))

    def closeEvent(self, event) -> None:
        self.switch_verify_timer.stop()
        self._clear_pending_switch()
        super().closeEvent(event)



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
