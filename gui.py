# -*- coding: utf-8 -*-
"""ZebraTemplatePrinter — Linux 原生桌面 GUI (PyQt5)

完整复刻原 C# WinForms 界面，复用已移植的 Python 后端模块。
模板支持 JSON 格式（.json / .label.json）和 ZPL 格式（.zpl）。
打印机默认使用系统 CUPS 打印机（lpstat 读取）。
"""

import sys, os, json, time, logging, threading, tempfile, shutil, csv
from datetime import datetime
from typing import Optional

# ── 项目根目录（解决桌面快捷方式工作目录错误的问题） ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)  # 确保所有相对路径基于项目目录

# ── PyQt5 ──
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QSpinBox, QTextEdit, QGroupBox, QFormLayout, QMessageBox,
    QFileDialog, QStatusBar, QSplitter, QCheckBox, QGridLayout, QFrame, QDialog,
    QDialogButtonBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QIcon, QColor

# ── 后端模块 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zebra_printer.db import AppDb, PrintHistoryItem, TemplateMapping
from zebra_printer.param_resolver import ParamResolver
from zebra_printer.zpl_renderer import (
    load_template, render_zpl, list_templates,
    is_json_template, load_json_template, extract_json_placeholders
)
from zebra_printer.printer import (
    print_zpl, cups_raw_print, get_cups_printers, cups_print_image
)
from zebra_printer.config import AppConfig
from zebra_printer.label_renderer import render_label
from zebra_printer.trigger_service import AutoTriggerService, TriggerSettings, TriggerMessage
from zebra_printer.statistics import StatisticsWidget
from zebra_printer.label_designer_widget import LabelDesignerWidget
from zebra_printer.statistics import StatisticsWidget
from zebra_printer.label_designer_widget import LabelDesignerWidget

# ── 日志 ──
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gui")


# ════════════════════════════════════════════════════════════════════════════
# 打印工作线程
# ════════════════════════════════════════════════════════════════════════════

class PrintWorker(QThread):
    finished = pyqtSignal(bool, str, str)  # success, message, preview
    progress = pyqtSignal(int)              # current copy

    def __init__(self, template_path, params, copies,
                 printer_name="", is_json=False):
        super().__init__()
        self.template_path = template_path
        self.params = params
        self.copies = copies
        self.printer_name = printer_name
        self.is_json = is_json       # True = JSON 标签模板, False = ZPL 模板

    def run(self):
        try:
            if self.is_json:
                self._print_json()
            else:
                self._print_zpl()
        except Exception as e:
            self.finished.emit(False, f"打印异常: {e}", "")

    def _print_zpl(self):
        template = load_template(self.template_path)
        resolver = ParamResolver()
        seq_offsets = {}
        if self.db and self.scope_key:
            seq_offsets = self.db.get_sequence_states(self.scope_key)
        per_copy_values = resolver.build_per_copy_values(self.params, self.copies, seq_offsets)

        success_count = 0
        for i in range(self.copies):
            self.progress.emit(i + 1)
            copy_params = per_copy_values[i] if i < len(per_copy_values) else self.params
            zpl = render_zpl(template, copy_params)
            zpl_bytes = zpl.encode("utf-8")

            if self.printer_name:
                ok, err = cups_raw_print(zpl_bytes, self.printer_name)
            else:
                ok, err = False, "未选择打印机"

            if ok:
                success_count += 1
            else:
                self.finished.emit(False, f"第{i+1}份失败: {err}", zpl)
                return

        if self.db and self.scope_key:
            tokens = resolver.get_sequence_tokens(self.params)
            if tokens:
                od = {}
                for item in tokens:
                    od[item[0]] = (seq_offsets.get(item[0], 0) or 0) + self.copies
                self.db.upsert_sequence_states(self.scope_key, od)

        self.finished.emit(True, f"打印完成: {success_count}/{self.copies} 成功", zpl)

    def _print_json(self):
        tmpl_data = load_json_template(self.template_path)
        from zebra_printer.label_renderer import LabelElement
        elements = [LabelElement(e) for e in tmpl_data["elements"]]
        dpi = 203
        resolver = ParamResolver()
        seq_offsets = {}
        if self.db and self.scope_key:
            seq_offsets = self.db.get_sequence_states(self.scope_key)
        per_copy_values = resolver.build_per_copy_values(self.params, self.copies, seq_offsets)

        success_count = 0
        for i in range(self.copies):
            self.progress.emit(i + 1)
            copy_params = per_copy_values[i] if i < len(per_copy_values) else self.params
            img = render_label(
                tmpl_data["width_mm"], tmpl_data["height_mm"],
                elements, copy_params, dpi=dpi
            )

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                img_path = f.name
            img.save(img_path, "PNG")

            if self.printer_name:
                ok, err = cups_print_image(img_path, self.printer_name)
            else:
                ok, err = False, "未选择打印机"

            os.unlink(img_path)

            if ok:
                success_count += 1
            else:
                self.finished.emit(False, f"第{i+1}份失败: {err}",
                                   f"[JSON 标签模板] {self.template_path}")
                return

        if self.db and self.scope_key:
            tokens = resolver.get_sequence_tokens(self.params)
            if tokens:
                od = {}
                for item in tokens:
                    od[item[0]] = (seq_offsets.get(item[0], 0) or 0) + self.copies
                self.db.upsert_sequence_states(self.scope_key, od)

        self.finished.emit(True, f"打印完成: {success_count}/{self.copies} 成功",
                           f"[JSON 标签模板] {self.template_path}")


# ════════════════════════════════════════════════════════════════════════════
# 主窗口
# ════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zebra Template Printer — Linux")
        self.resize(1100, 750)

        self.db = AppDb("data/print.db")
        self.db.initialize()
        self.trigger_running = False

        self.trigger_service = AutoTriggerService()
        self.trigger_service.on_message = self._on_trigger_received

        self._build_ui()
        self._refresh_all()

        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_status)
        self._refresh_timer.start(5000)

    def _build_ui(self):
        tabs = QTabWidget()

        tabs.addTab(self._build_print_tab(), "🖨 打印")
        tabs.addTab(self._build_template_tab(), "📋 模板管理")

        # 标签设计
        self._designer = LabelDesignerWidget(BASE_DIR)
        self._designer.template_saved.connect(self._refresh_templates)
        tabs.addTab(self._designer, "✏ 标签设计")

        tabs.addTab(self._build_history_tab(), "📜 历史记录")

        # 统计
        self._stats = StatisticsWidget(self.db)
        tabs.addTab(self._stats, "📊 统计")

        tabs.addTab(self._build_trigger_tab(), "⚡ 自动触发")
        self.setCentralWidget(tabs)

        self._lbl_printer = QLabel("打印机: -")
        self._lbl_counter = QLabel("")
        self.statusBar().addWidget(self._lbl_printer, 1)
        self.statusBar().addWidget(self._lbl_counter)

    # ── Tab 1: 打印 ─────────────────────────────────────────────────────

    def _build_print_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("型号:"))
        self._txt_model = QLineEdit()
        self._txt_model.setPlaceholderText("输入产品型号（如 KV-100）")
        self._txt_model.setMinimumWidth(200)
        row1.addWidget(self._txt_model)
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("模板文件:"))
        self._cmb_template = QComboBox()
        self._cmb_template.setMinimumWidth(220)
        self._cmb_template.currentTextChanged.connect(self._on_template_changed)
        row2.addWidget(self._cmb_template)

        row2.addWidget(QLabel("目标打印机:"))
        self._cmb_printer = QComboBox()
        self._cmb_printer.setMinimumWidth(200)
        row2.addWidget(self._cmb_printer)

        self._btn_refresh_printers = QPushButton("🔄 刷新")
        self._btn_refresh_printers.clicked.connect(self._refresh_printers)
        row2.addWidget(self._btn_refresh_printers)
        layout.addLayout(row2)

        gb_params = QGroupBox("模板参数")
        params_layout = QVBoxLayout(gb_params)
        self._tbl_params = QTableWidget(0, 3)
        self._tbl_params.setHorizontalHeaderLabels(["参数名", "参数值", "规则（FIXED/SEQ）"])
        self._tbl_params.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_params.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl_params.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tbl_params.setMinimumHeight(150)
        self._tbl_params.itemChanged.connect(self._on_param_changed)
        params_layout.addWidget(self._tbl_params)
        layout.addWidget(gb_params)

        gb_preview = QGroupBox("打印预览")
        preview_layout = QVBoxLayout(gb_preview)
        self._txt_zpl_preview = QTextEdit()
        self._txt_zpl_preview.setReadOnly(True)
        self._txt_zpl_preview.setMaximumHeight(180)
        self._txt_zpl_preview.setFont(QFont("Consolas", 10))
        preview_layout.addWidget(self._txt_zpl_preview)
        layout.addWidget(gb_preview)

        btn_row = QHBoxLayout()
        self._btn_preview = QPushButton("👁 预览")
        self._btn_preview.clicked.connect(self._do_preview)
        btn_row.addWidget(self._btn_preview)

        btn_row.addWidget(QLabel("份数:"))
        self._sp_copies = QSpinBox()
        self._sp_copies.setRange(1, 999)
        self._sp_copies.setValue(1)
        self._sp_copies.setMinimumWidth(60)
        btn_row.addWidget(self._sp_copies)

        self._btn_print = QPushButton("▶ 打印")
        self._btn_print.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; font-size: 14px; "
            "padding: 8px 30px; border-radius: 6px; }"
            "QPushButton:disabled { background-color: #cccccc; }"
        )
        self._btn_print.clicked.connect(self._do_print)
        btn_row.addWidget(self._btn_print)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return w

    # ── Tab 2: 模板管理（完善版）─────────────────────────────────────────

    def _build_template_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # ── 模板文件管理 ──
        gb_files = QGroupBox("模板文件管理（templates/ 目录）")
        files_layout = QVBoxLayout(gb_files)

        bar = QHBoxLayout()
        self._btn_import_tmpl = QPushButton("📥 导入模板")
        self._btn_import_tmpl.clicked.connect(self._do_import_template)
        bar.addWidget(self._btn_import_tmpl)

        self._btn_delete_tmpl = QPushButton("🗑 删除模板文件")
        self._btn_delete_tmpl.clicked.connect(self._do_delete_template_file)
        bar.addWidget(self._btn_delete_tmpl)

        self._btn_preview_tmpl = QPushButton("👁 预览模板")
        self._btn_preview_tmpl.clicked.connect(self._do_preview_template)
        bar.addWidget(self._btn_preview_tmpl)

        self._btn_refresh_tmpl = QPushButton("🔄 刷新列表")
        self._btn_refresh_tmpl.clicked.connect(self._refresh_templates)
        bar.addWidget(self._btn_refresh_tmpl)

        bar.addStretch()
        files_layout.addLayout(bar)

        # 模板文件列表（仅显示文件）
        self._tbl_template_files = QTableWidget(0, 4)
        self._tbl_template_files.setHorizontalHeaderLabels(["文件名", "类型", "大小", "元素/占位符"])
        self._tbl_template_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_template_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tbl_template_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tbl_template_files.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tbl_template_files.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_template_files.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_template_files.doubleClicked.connect(self._on_template_file_double_clicked)
        self._tbl_template_files.setMinimumHeight(140)
        files_layout.addWidget(self._tbl_template_files)

        layout.addWidget(gb_files)

        # ── 型号映射管理 ──
        gb_mappings = QGroupBox("型号 → 模板映射管理")
        mappings_layout = QVBoxLayout(gb_mappings)

        bar2 = QHBoxLayout()
        self._btn_add_mapping = QPushButton("➕ 添加映射")
        self._btn_add_mapping.clicked.connect(self._do_add_mapping)
        bar2.addWidget(self._btn_add_mapping)

        self._btn_edit_mapping = QPushButton("✏ 编辑映射")
        self._btn_edit_mapping.clicked.connect(self._do_edit_mapping)
        bar2.addWidget(self._btn_edit_mapping)

        self._btn_delete_mapping = QPushButton("🗑 删除映射")
        self._btn_delete_mapping.clicked.connect(self._do_delete_mapping)
        bar2.addWidget(self._btn_delete_mapping)

        bar2.addStretch()
        mappings_layout.addLayout(bar2)

        self._tbl_mappings = QTableWidget(0, 5)
        self._tbl_mappings.setHorizontalHeaderLabels(["型号", "模板文件", "参数", "类型", "更新时间"])
        self._tbl_mappings.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_mappings.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl_mappings.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl_mappings.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tbl_mappings.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._tbl_mappings.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_mappings.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_mappings.doubleClicked.connect(self._on_mapping_double_clicked)
        mappings_layout.addWidget(self._tbl_mappings)

        layout.addWidget(gb_mappings, stretch=1)
        return w

    # ── Tab 3: 历史记录 ─────────────────────────────────────────────────

    def _build_history_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        bar = QHBoxLayout()
        self._txt_search = QLineEdit()
        self._txt_search.setPlaceholderText("搜索（型号 / 模板 / 结果...）")
        self._txt_search.textChanged.connect(self._refresh_history)
        bar.addWidget(self._txt_search)

        self._cmb_mode_filter = QComboBox()
        self._cmb_mode_filter.addItems(["全部模式", "ZPL", "AutoTrigger", "Manual", "JSON"])
        self._cmb_mode_filter.currentTextChanged.connect(self._refresh_history)
        bar.addWidget(self._cmb_mode_filter)

        self._btn_clear_history = QPushButton("清空历史")
        self._btn_clear_history.clicked.connect(self._do_clear_history)
        bar.addWidget(self._btn_clear_history)
        layout.addLayout(bar)

        self._tbl_history = QTableWidget(0, 7)
        self._tbl_history.setHorizontalHeaderLabels(["时间", "型号", "模板", "打印机", "份数", "模式", "结果"])
        self._tbl_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tbl_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tbl_history.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._tbl_history.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._tbl_history.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self._tbl_history.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_history.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_history.doubleClicked.connect(self._on_history_double_clicked)
        layout.addWidget(self._tbl_history)

        return w

    # ── Tab 4: 自动触发 ─────────────────────────────────────────────────

    def _build_trigger_tab(self):
        w = QWidget()
        layout = QHBoxLayout(w)

        left = QVBoxLayout()
        gb_trigger = QGroupBox("触发设置")
        form = QFormLayout(gb_trigger)

        self._chk_trigger_enabled = QCheckBox("启用自动触发")
        self._chk_trigger_enabled.setChecked(False)
        form.addRow(self._chk_trigger_enabled)

        self._cmb_protocol = QComboBox()
        self._cmb_protocol.addItems(["Tcp", "Serial"])
        form.addRow("协议:", self._cmb_protocol)

        self._sp_tcp_port = QSpinBox()
        self._sp_tcp_port.setRange(1, 65535)
        self._sp_tcp_port.setValue(9000)
        form.addRow("TCP 端口:", self._sp_tcp_port)

        self._txt_serial_port = QLineEdit("/dev/ttyUSB0")
        form.addRow("串口:", self._txt_serial_port)

        self._sp_baud_rate = QSpinBox()
        self._sp_baud_rate.setRange(1200, 115200)
        self._sp_baud_rate.setSingleStep(1200)
        self._sp_baud_rate.setValue(9600)
        form.addRow("波特率:", self._sp_baud_rate)

        self._txt_trigger_keyword = QLineEdit("PRINT")
        form.addRow("触发关键字:", self._txt_trigger_keyword)

        left.addWidget(gb_trigger)
        btn_bar = QHBoxLayout()
        self._btn_trigger_start = QPushButton("▶ 启动监听")
        self._btn_trigger_start.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; font-size: 14px; "
            "padding: 8px 20px; border-radius: 6px; }"
        )
        self._btn_trigger_start.clicked.connect(self._do_toggle_trigger)
        btn_bar.addWidget(self._btn_trigger_start)

        self._btn_trigger_test = QPushButton("🧪 模拟触发")
        self._btn_trigger_test.clicked.connect(self._do_test_trigger)
        btn_bar.addWidget(self._btn_trigger_test)
        left.addLayout(btn_bar)
        left.addStretch()
        layout.addLayout(left, 1)

        self._txt_trigger_log = QTextEdit()
        self._txt_trigger_log.setReadOnly(True)
        self._txt_trigger_log.setFont(QFont("Consolas", 9))
        layout.addWidget(self._txt_trigger_log, 2)

        return w

    # ═══════════════════════════════════════════════════════════════════════
    # 刷新
    # ═══════════════════════════════════════════════════════════════════════

    def _refresh_all(self):
        self._refresh_printers()
        self._refresh_templates()
        self._refresh_history()
        self._refresh_status()

    def _refresh_printers(self):
        current = self._cmb_printer.currentText()
        self._cmb_printer.blockSignals(True)
        self._cmb_printer.clear()
        printers = get_cups_printers()
        self._cmb_printer.addItems(printers)
        if current and current in printers:
            self._cmb_printer.setCurrentText(current)
        self._cmb_printer.blockSignals(False)

    def _refresh_status(self):
        printer_name = self._cmb_printer.currentText() or "未选择"
        self._lbl_printer.setText(f"打印机: {printer_name}")
        self._lbl_counter.setText(
            f"模板文件: {self._tbl_template_files.rowCount()} | "
            f"映射: {self._tbl_mappings.rowCount()} | "
            f"历史: {self._tbl_history.rowCount()} | "
            f"触发: {'运行中' if self.trigger_running else '停止'}"
        )

    def _refresh_templates(self):
        """刷新模板文件列表 + 映射列表 + 打印页下拉"""
        tmpl_dir = os.path.join(BASE_DIR, "templates")
        os.makedirs(tmpl_dir, exist_ok=True)

        # ── 模板文件列表 ──
        self._tbl_template_files.setRowCount(0)
        all_files = list_templates(tmpl_dir) + [f for f in os.listdir(tmpl_dir)
                                                 if f.endswith(('.json', '.zpl'))
                                                 and f not in list_templates(tmpl_dir)]
        all_files = sorted(set(all_files))

        for fname in all_files:
            fpath = os.path.join(tmpl_dir, fname)
            if not os.path.isfile(fpath):
                continue
            row = self._tbl_template_files.rowCount()
            self._tbl_template_files.insertRow(row)

            self._tbl_template_files.setItem(row, 0, QTableWidgetItem(fname))

            is_json = fname.endswith((".json", ".label.json"))
            type_item = QTableWidgetItem("JSON" if is_json else "ZPL")
            type_item.setForeground(QColor("green" if is_json else "blue"))
            self._tbl_template_files.setItem(row, 1, type_item)

            fsize = os.path.getsize(fpath)
            self._tbl_template_files.setItem(row, 2, QTableWidgetItem(
                f"{fsize} B" if fsize < 1024 else f"{fsize / 1024:.1f} KB"
            ))

            # 解析占位符/元素数
            try:
                if is_json:
                    data = load_json_template(fpath)
                    ph = extract_json_placeholders(data)
                    info = f"{len(data['elements'])} 个元素 › {','.join(ph) if ph else '-'}"
                else:
                    tpl_str = load_template(fpath)
                    from zebra_printer.zpl_renderer import extract_placeholders
                    ph = extract_placeholders(tpl_str)
                    info = f"{','.join(ph) if ph else '-'}"
                self._tbl_template_files.setItem(row, 3, QTableWidgetItem(info))
            except Exception:
                self._tbl_template_files.setItem(row, 3, QTableWidgetItem("解析失败"))

        # ── 映射列表 ──
        self._tbl_mappings.setRowCount(0)
        mappings = self.db.get_mappings()
        for m in mappings:
            row = self._tbl_mappings.rowCount()
            self._tbl_mappings.insertRow(row)
            self._tbl_mappings.setItem(row, 0, QTableWidgetItem(m.model))
            self._tbl_mappings.setItem(row, 1, QTableWidgetItem(m.template_path))
            params = m.get_parameters()
            params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "-"
            self._tbl_mappings.setItem(row, 2, QTableWidgetItem(params_str))
            tmpl_type = "JSON" if is_json_template(m.template_path) else "ZPL"
            type_item = QTableWidgetItem(tmpl_type)
            type_item.setForeground(QColor("green" if tmpl_type == "JSON" else "blue"))
            self._tbl_mappings.setItem(row, 3, type_item)
            self._tbl_mappings.setItem(row, 4, QTableWidgetItem(m.updated_at))

        # ── 打印页下拉列表 ──
        current = self._cmb_template.currentText()
        self._cmb_template.blockSignals(True)
        self._cmb_template.clear()
        self._cmb_template.addItems(all_files)
        if current in all_files:
            self._cmb_template.setCurrentText(current)
        self._cmb_template.blockSignals(False)

    def _refresh_history(self):
        keyword = self._txt_search.text().strip() or None
        mode = self._cmb_mode_filter.currentText()
        if mode == "全部模式":
            mode = None
        items = self.db.search_history(keyword=keyword, mode=mode, limit=200)

        self._tbl_history.setRowCount(0)
        for item in items:
            row = self._tbl_history.rowCount()
            self._tbl_history.insertRow(row)
            self._tbl_history.setItem(row, 0, QTableWidgetItem(item.printed_at))
            self._tbl_history.setItem(row, 1, QTableWidgetItem(item.model or ""))
            self._tbl_history.setItem(row, 2, QTableWidgetItem(item.template_path))
            self._tbl_history.setItem(row, 3, QTableWidgetItem(item.printer_name))
            self._tbl_history.setItem(row, 4, QTableWidgetItem(str(item.copies)))
            self._tbl_history.setItem(row, 5, QTableWidgetItem(item.mode))
            result_item = QTableWidgetItem(item.result)
            if item.result == "Fail":
                result_item.setForeground(QColor("red"))
            elif item.result == "Success":
                result_item.setForeground(QColor("green"))
            self._tbl_history.setItem(row, 6, result_item)

    # ═══════════════════════════════════════════════════════════════════════
    # 模板文件操作
    # ═══════════════════════════════════════════════════════════════════════

    def _do_import_template(self):
        """从文件管理器选择模板文件导入到 templates/ 目录"""
        fpath, _ = QFileDialog.getOpenFileName(
            self, "选择模板文件",
            os.path.expanduser("~"),
            "模板文件 (*.json *.label.json *.zpl);;所有文件 (*)"
        )
        if not fpath:
            return

        dst_dir = os.path.join(BASE_DIR, "templates")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(fpath))

        if os.path.exists(dst):
            reply = QMessageBox.question(
                self, "文件已存在",
                f"{os.path.basename(fpath)} 已存在，是否覆盖?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        shutil.copy2(fpath, dst)
        self._refresh_templates()
        QMessageBox.information(self, "导入完成", f"已导入: {os.path.basename(fpath)}")

    def _do_delete_template_file(self):
        """删除选中的模板文件"""
        row = self._tbl_template_files.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先在模板文件列表中选中一行")
            return
        fname = self._tbl_template_files.item(row, 0).text()
        fpath = os.path.join(BASE_DIR, "templates", fname)
        if not os.path.exists(fpath):
            QMessageBox.warning(self, "提示", "文件不存在")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除模板文件 {fname}?\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        os.remove(fpath)
        # 同时清理数据库中引用此模板的映射
        import sqlite3
        conn = sqlite3.connect(self.db._db_path)
        conn.execute("DELETE FROM TemplateMappings WHERE TemplatePath = ?", (fname,))
        conn.commit()
        conn.close()

        self._refresh_templates()
        QMessageBox.information(self, "删除完成", f"已删除: {fname}")

    def _do_preview_template(self):
        """弹窗预览模板内容"""
        row = self._tbl_template_files.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先在模板文件列表中选中一行")
            return
        fname = self._tbl_template_files.item(row, 0).text()
        fpath = os.path.join(BASE_DIR, "templates", fname)

        try:
            if is_json_template(fpath):
                data = load_json_template(fpath)
                elements = data.get("elements", [])
                lines = [f"📄 {fname}"]
                lines.append(f"尺寸: {data['width_mm']}mm × {data['height_mm']}mm")
                lines.append(f"DPI: 203")
                lines.append(f"元素数: {len(elements)}")
                lines.append("-" * 50)
                for i, e in enumerate(elements):
                    etype = e.get("Type", "?")
                    content = e.get("Content", "")
                    name = e.get("Name", f"#{i}")
                    x = e.get("XMm", 0)
                    y = e.get("YMm", 0)
                    lines.append(f"  [{etype}] \"{name}\" @({x},{y})")
                    if content:
                        lines.append(f"    内容: {content}")
                content_text = "\n".join(lines)
            else:
                with open(fpath, "r", encoding="utf-8") as f:
                    raw = f.read()
                lines = [f"📄 {fname}"]
                lines.append("-" * 50)
                lines.append(raw)
                content_text = "\n".join(lines)

            dlg = QDialog(self)
            dlg.setWindowTitle(f"模板预览: {fname}")
            dlg.resize(600, 500)
            layout = QVBoxLayout(dlg)
            txt = QTextEdit()
            txt.setReadOnly(True)
            txt.setFont(QFont("Consolas", 10))
            txt.setPlainText(content_text)
            layout.addWidget(txt)
            btn = QDialogButtonBox(QDialogButtonBox.Ok)
            btn.accepted.connect(dlg.accept)
            layout.addWidget(btn)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "预览失败", str(e))

    def _on_template_file_double_clicked(self, idx):
        """模板文件双击 → 填充到打印页面"""
        row = idx.row()
        fname = self._tbl_template_files.item(row, 0).text()
        # 切换到打印标签页并选择该模板
        self.centralWidget().findChild(QTabWidget).setCurrentIndex(0)
        ci = self._cmb_template.findText(fname)
        if ci >= 0:
            self._cmb_template.setCurrentIndex(ci)

    # ═══════════════════════════════════════════════════════════════════════
    # 映射操作
    # ═══════════════════════════════════════════════════════════════════════

    def _do_add_mapping(self):
        dlg = _AddMappingDialog(self, BASE_DIR)
        if dlg.exec_() != QDialog.Accepted:
            return
        self.db.upsert_mapping(dlg.model, dlg.template, parameters_json=dlg.params_json)
        self._refresh_templates()
        QMessageBox.information(self, "完成", f"已添加 {dlg.model} → {dlg.template}")

    def _do_edit_mapping(self):
        row = self._tbl_mappings.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先在映射列表中选中一行")
            return
        model = self._tbl_mappings.item(row, 0).text()
        current_tmpl = self._tbl_mappings.item(row, 1).text()

        mapping = next((m for m in self.db.get_mappings() if m.model == model), None)
        params = mapping.get_parameters() if mapping else {}

        dlg = _AddMappingDialog(self, BASE_DIR, model=model, template=current_tmpl, params=params)
        if dlg.exec_() != QDialog.Accepted:
            return
        self.db.upsert_mapping(dlg.model, dlg.template, parameters_json=dlg.params_json)
        self._refresh_templates()
        QMessageBox.information(self, "完成", f"已更新 {dlg.model} → {dlg.template}")

    def _do_delete_mapping(self):
        row = self._tbl_mappings.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先在映射列表中选中一行")
            return
        model = self._tbl_mappings.item(row, 0).text()
        reply = QMessageBox.question(self, "确认", f"删除 {model} 的映射?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        import sqlite3
        conn = sqlite3.connect(self.db._db_path)
        conn.execute("DELETE FROM TemplateMappings WHERE Model = ?", (model,))
        conn.commit()
        conn.close()
        self._refresh_templates()

    def _on_mapping_double_clicked(self, idx):
        """映射双击 → 自动填充到打印页面"""
        row = idx.row()
        model = self._tbl_mappings.item(row, 0).text()
        path = self._tbl_mappings.item(row, 1).text()
        if not model or not path:
            return

        self.centralWidget().findChild(QTabWidget).setCurrentIndex(0)
        self._txt_model.setText(model)

        ci = self._cmb_template.findText(path)
        if ci >= 0:
            self._cmb_template.setCurrentIndex(ci)

        mapping = next((m for m in self.db.get_mappings() if m.model == model), None)
        if mapping:
            params = mapping.get_parameters()
            for r in range(self._tbl_params.rowCount()):
                key = self._tbl_params.item(r, 0).text()
                if key in params:
                    self._tbl_params.item(r, 1).setText(params[key])

    def _do_clear_history(self):
        reply = QMessageBox.question(self, "确认", "清空所有打印历史?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        import sqlite3
        conn = sqlite3.connect(self.db._db_path)
        conn.execute("DELETE FROM PrintHistory")
        conn.commit()
        conn.close()
        self._refresh_history()

    # ═══════════════════════════════════════════════════════════════════════
    # 模板选择 → 参数填充 & 预览
    # ═══════════════════════════════════════════════════════════════════════

    def _on_template_changed(self, tmpl_name):
        if not tmpl_name:
            return
        tmpl_path = os.path.join("templates", tmpl_name)

        try:
            if is_json_template(tmpl_path):
                tmpl_data = load_json_template(tmpl_path)
                placeholders = extract_json_placeholders(tmpl_data)
            else:
                template = load_template(tmpl_path)
                from zebra_printer.zpl_renderer import extract_placeholders
                placeholders = extract_placeholders(template)
        except Exception:
            placeholders = []

        model = self._txt_model.text().strip()
        saved_params = {}
        if model:
            mapping = next((m for m in self.db.get_mappings() if m.model == model), None)
            if mapping:
                saved_params = mapping.get_parameters()

        self._tbl_params.setRowCount(0)
        self._tbl_params.blockSignals(True)
        for ph in placeholders:
            row = self._tbl_params.rowCount()
            self._tbl_params.insertRow(row)
            self._tbl_params.setItem(row, 0, QTableWidgetItem(ph))
            val = saved_params.get(ph, "")
            self._tbl_params.setItem(row, 1, QTableWidgetItem(val))
            self._tbl_params.setItem(row, 2, QTableWidgetItem("FIXED"))
        self._tbl_params.blockSignals(False)

        self._do_preview()

    def _on_param_changed(self, item):
        model = self._txt_model.text().strip()
        if not model:
            return
        params = {}
        for r in range(self._tbl_params.rowCount()):
            key = self._tbl_params.item(r, 0).text() if self._tbl_params.item(r, 0) else ""
            val = self._tbl_params.item(r, 1).text() if self._tbl_params.item(r, 1) else ""
            if key:
                params[key] = val
        tmpl = self._cmb_template.currentText()
        self.db.upsert_mapping(model, tmpl, parameters_json=json.dumps(params, ensure_ascii=False))

    def _get_params_from_table(self) -> dict:
        params = {}
        for r in range(self._tbl_params.rowCount()):
            key = self._tbl_params.item(r, 0).text() if self._tbl_params.item(r, 0) else ""
            val = self._tbl_params.item(r, 1).text() if self._tbl_params.item(r, 1) else ""
            if key:
                params[key] = val
        return params

    # ═══════════════════════════════════════════════════════════════════════
    # 预览 & 打印
    # ═══════════════════════════════════════════════════════════════════════

    def _do_preview(self):
        tmpl = self._cmb_template.currentText()
        if not tmpl:
            return
        params = self._get_params_from_table()
        tmpl_path = os.path.join("templates", tmpl)

        try:
            if is_json_template(tmpl_path):
                tmpl_data = load_json_template(tmpl_path)
                elements = tmpl_data.get("elements", [])
                summary = f"[JSON 标签模板] {tmpl}\n"
                summary += f"尺寸: {tmpl_data['width_mm']}mm × {tmpl_data['height_mm']}mm\n"
                summary += f"元素数: {len(elements)}\n"
                summary += "-" * 40 + "\n"
                for i, e in enumerate(elements):
                    etype = e.get("Type", "?")
                    content = e.get("Content", "")
                    for k, v in params.items():
                        content = content.replace("{{%s}}" % k, str(v))
                    name = e.get("Name", f"#{i}")
                    summary += f"  [{etype}] {name}: {content}\n"
                self._txt_zpl_preview.setPlainText(summary)
            else:
                template = load_template(tmpl_path)
                zpl = render_zpl(template, params)
                self._txt_zpl_preview.setPlainText(zpl)
        except Exception as e:
            self._txt_zpl_preview.setPlainText(f"预览失败: {e}")

    def _do_print(self):
        tmpl = self._cmb_template.currentText()
        if not tmpl:
            QMessageBox.warning(self, "提示", "请先选择模板文件")
            return

        printer_name = self._cmb_printer.currentText()
        if not printer_name:
            QMessageBox.warning(self, "提示", "请先选择目标打印机（点击🔄刷新扫描系统打印机）")
            return

        params = self._get_params_from_table()
        copies = self._sp_copies.value()
        tmpl_path = os.path.join("templates", tmpl)
        is_json = is_json_template(tmpl_path)

        mode_label = "JSON 标签" if is_json else "ZPL"
        params_text = ", ".join(f"{k}={v}" for k, v in params.items())
        reply = QMessageBox.question(
            self, "确认打印",
            f"模板: {tmpl} [{mode_label}]\n"
            f"参数: {params_text}\n"
            f"份数: {copies}\n"
            f"打印机: {printer_name}\n\n确认打印?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._btn_print.setEnabled(False)
        self._btn_print.setText("打印中...")
        self._worker = PrintWorker(tmpl_path, params, copies,
                                   printer_name=printer_name,
                                   is_json=is_json)
        self._worker.finished.connect(self._on_print_done)
        self._worker.start()

    def _on_print_done(self, success, message, preview):
        self._btn_print.setEnabled(True)
        self._btn_print.setText("▶ 打印")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tmpl = self._cmb_template.currentText()
        params = self._get_params_from_table()
        printer_name = self._cmb_printer.currentText()

        self.db.insert_print_history(PrintHistoryItem(
            printed_at=now,
            model=self._txt_model.text().strip() or None,
            template_path=tmpl,
            printer_name=printer_name,
            copies=self._sp_copies.value(),
            parameters_json=json.dumps(params, ensure_ascii=False),
            mode="JSON" if is_json_template(os.path.join("templates", tmpl)) else "ZPL",
            result="Success" if success else "Fail",
            error_message=None if success else message
        ))

        self._refresh_history()

        if success:
            QMessageBox.information(self, "打印完成", message)
        else:
            QMessageBox.critical(self, "打印失败", message)

    def _on_history_double_clicked(self, idx):
        row = idx.row()
        model = self._tbl_history.item(row, 1).text() if self._tbl_history.item(row, 1) else ""
        path = self._tbl_history.item(row, 2).text() if self._tbl_history.item(row, 2) else ""
        if not model or not path:
            return

        self.centralWidget().findChild(QTabWidget).setCurrentIndex(0)
        self._txt_model.setText(model)

        ci = self._cmb_template.findText(path)
        if ci >= 0:
            self._cmb_template.setCurrentIndex(ci)

        mapping = next((m for m in self.db.get_mappings() if m.model == model), None)
        if mapping:
            params = mapping.get_parameters()
            for r in range(self._tbl_params.rowCount()):
                key = self._tbl_params.item(r, 0).text()
                if key in params:
                    self._tbl_params.item(r, 1).setText(params[key])

    # ═══════════════════════════════════════════════════════════════════════
    # 自动触发
    # ═══════════════════════════════════════════════════════════════════════

    def _on_trigger_settings_changed(self):
        pass

    def _do_toggle_trigger(self):
        if self.trigger_running:
            self.trigger_service.stop()
            self.trigger_running = False
            self._btn_trigger_start.setText("▶ 启动监听")
            self._btn_trigger_start.setStyleSheet(
                "QPushButton { background-color: #4CAF50; color: white; font-size: 14px; "
                "padding: 8px 20px; border-radius: 6px; }"
            )
            self._log_trigger("监听已停止")
        else:
            settings = TriggerSettings(
                enabled=self._chk_trigger_enabled.isChecked(),
                protocol=self._cmb_protocol.currentText(),
                tcp_port=self._sp_tcp_port.value(),
                serial_port=self._txt_serial_port.text().strip() or None,
                baud_rate=self._sp_baud_rate.value(),
                trigger_keyword=self._txt_trigger_keyword.text().strip(),
            )
            self.trigger_service.start(settings)
            self.trigger_running = True
            self._btn_trigger_start.setText("⏹ 停止监听")
            self._btn_trigger_start.setStyleSheet(
                "QPushButton { background-color: #f44336; color: white; font-size: 14px; "
                "padding: 8px 20px; border-radius: 6px; }"
            )
            self._log_trigger(f"监听已启动 [{settings.protocol}]")

        self._refresh_status()

    def _do_test_trigger(self):
        msg = TriggerMessage(
            source="TEST",
            payload=self._txt_trigger_keyword.text().strip(),
            display_payload=self._txt_trigger_keyword.text().strip()
        )
        self._on_trigger_received(msg)

    def _on_trigger_received(self, msg: TriggerMessage):
        self._log_trigger(f"[{msg.source}] {msg.display_payload}")

        tmpl = self._cmb_template.currentText()
        if not tmpl:
            mappings = self.db.get_mappings()
            if mappings:
                tmpl = mappings[0].template_path
        if not tmpl:
            self._log_trigger("⚠ 无可用模板，跳过打印")
            return

        params = self._get_params_from_table()
        printer_name = self._cmb_printer.currentText() or ""
        tmpl_path = os.path.join("templates", tmpl) if not tmpl.startswith("templates/") else tmpl

        try:
            if is_json_template(tmpl_path):
                tmpl_data = load_json_template(tmpl_path)
                from zebra_printer.label_renderer import LabelElement
                elements = [LabelElement(e) for e in tmpl_data["elements"]]
                img = render_label(
                    tmpl_data["width_mm"], tmpl_data["height_mm"],
                    elements, params, dpi=203
                )
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    img_path = f.name
                img.save(img_path, "PNG")
                if printer_name:
                    ok, err = cups_print_image(img_path, printer_name)
                else:
                    ok, err = False, "未选择打印机"
                os.unlink(img_path)
            else:
                template = load_template(tmpl_path)
                zpl = render_zpl(template, params)
                zpl_bytes = zpl.encode("utf-8")
                if printer_name:
                    ok, err = cups_raw_print(zpl_bytes, printer_name)
                else:
                    ok, err = False, "未选择打印机"

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mode = "JSON" if is_json_template(tmpl_path) else "AutoTrigger"
            self.db.insert_print_history(PrintHistoryItem(
                printed_at=now,
                model=self._txt_model.text().strip() or None,
                template_path=tmpl,
                printer_name=printer_name or "未选择",
                copies=1,
                parameters_json=json.dumps(params, ensure_ascii=False),
                mode=mode,
                result="Success" if ok else "Fail",
                error_message=None if ok else err
            ))

            status = "✅ 打印成功" if ok else f"❌ 打印失败: {err}"
            self._log_trigger(status)
        except Exception as e:
            self._log_trigger(f"❌ 异常: {e}")

    def _log_trigger(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        self._txt_trigger_log.append(f"[{now}] {text}")


# ════════════════════════════════════════════════════════════════════════════
# 自定义对话框 — 添加/编辑映射
# ════════════════════════════════════════════════════════════════════════════

class _AddMappingDialog(QDialog):
    """添加/编辑 型号→模板 映射的对话框"""
    def __init__(self, parent, base_dir, model="", template="", params=None):
        super().__init__(parent)
        self.setWindowTitle("型号映射设置")
        self.resize(450, 400)
        self.base_dir = base_dir

        self.model = model
        self.template = template
        self.params_json = None

        layout = QVBoxLayout(self)

        # 型号
        form = QFormLayout()
        self._edit_model = QLineEdit(model)
        self._edit_model.setPlaceholderText("例如 KV-100")
        form.addRow("型号名称:", self._edit_model)
        layout.addLayout(form)

        # 模板文件
        tmpl_files = list_templates(os.path.join(base_dir, "templates"))
        self._cmb_template = QComboBox()
        self._cmb_template.addItems(tmpl_files)
        if template in tmpl_files:
            self._cmb_template.setCurrentText(template)
        form2 = QFormLayout()
        form2.addRow("模板文件:", self._cmb_template)
        layout.addLayout(form2)

        # 参数表格
        gb = QGroupBox("参数设置")
        gb_layout = QVBoxLayout(gb)
        self._tbl_params = QTableWidget(0, 2)
        self._tbl_params.setHorizontalHeaderLabels(["参数名", "参数值"])
        self._tbl_params.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_params.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        gb_layout.addWidget(self._tbl_params)
        layout.addWidget(gb)

        # 占位符自动填充
        self._cmb_template.currentTextChanged.connect(self._on_tmpl_changed)
        if model:
            self._on_tmpl_changed(self._cmb_template.currentText())

        # 参数预填
        if params:
            self._tbl_params.blockSignals(True)
            for r in range(self._tbl_params.rowCount()):
                key = self._tbl_params.item(r, 0).text()
                if key in params:
                    self._tbl_params.item(r, 1).setText(params[key])
            self._tbl_params.blockSignals(False)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_tmpl_changed(self, tmpl_name):
        if not tmpl_name:
            return
        tmpl_path = os.path.join("templates", tmpl_name)
        try:
            if is_json_template(tmpl_path):
                data = load_json_template(tmpl_path)
                placeholders = extract_json_placeholders(data)
            else:
                tpl = load_template(tmpl_path)
                from zebra_printer.zpl_renderer import extract_placeholders
                placeholders = extract_placeholders(tpl)
        except Exception:
            placeholders = []

        self._tbl_params.setRowCount(0)
        for ph in placeholders:
            row = self._tbl_params.rowCount()
            self._tbl_params.insertRow(row)
            self._tbl_params.setItem(row, 0, QTableWidgetItem(ph))
            self._tbl_params.setItem(row, 1, QTableWidgetItem(""))

    def _on_accept(self):
        model = self._edit_model.text().strip()
        if not model:
            QMessageBox.warning(self, "提示", "型号名称不能为空")
            return
        tmpl = self._cmb_template.currentText()
        if not tmpl:
            QMessageBox.warning(self, "提示", "请选择模板文件")
            return

        params = {}
        for r in range(self._tbl_params.rowCount()):
            key = self._tbl_params.item(r, 0).text() if self._tbl_params.item(r, 0) else ""
            val = self._tbl_params.item(r, 1).text() if self._tbl_params.item(r, 1) else ""
            if key:
                params[key] = val

        self.model = model
        self.template = tmpl
        self.params_json = json.dumps(params, ensure_ascii=False) if params else None
        self.accept()


# ════════════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
