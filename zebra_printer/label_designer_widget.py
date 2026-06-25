# -*- coding: utf-8 -*-
"""标签设计器 — 可视化编辑标签模板 (JSON .label.json)"""

import os, json, shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QMessageBox,
    QSplitter, QScrollArea, QFrame, QColorDialog, QFileDialog, QTextEdit,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPixmap, QImage,
    QPainterPath, QFontMetrics
)

# ── 元素类型 ──
ELEMENT_TYPES = [
    ("Text", "文本"),
    ("Barcode", "条码"),
    ("QrCode", "二维码"),
    ("Line", "线条"),
    ("Rectangle", "矩形"),
    ("RoundedRectangle", "圆角矩形"),
    ("Circle", "圆形"),
    ("Ellipse", "椭圆"),
    ("Image", "图片"),
    ("DateTime", "日期时间"),
]

# 默认值
DEFAULT_ELEMENT = {
    "Name": "Element",
    "Type": "Text",
    "XMm": 5, "YMm": 5, "WidthMm": 60, "HeightMm": 12,
    "HorizontalAlign": "Manual",
    "CenterVertically": False,
    "ContentHorizontalAlign": "Left",
    "AutoFitFont": True,
    "FontFamilyName": "Arial",
    "FontStyle": 0,
    "FontColor": "#000000",
    "FontSizePt": 11,
    "StrokeWidthMm": 0.3,
    "StrokeColor": "#000000",
    "Fill": False,
    "FillColor": "#D3D3D3",
    "CornerRadiusMm": 1.5,
    "KeepAspectRatio": True,
    "DateTimeFormat": "yyyy-MM-dd HH:mm:ss",
    "RotationAngle": 0,
    "BarcodeType": "Code128",
    "QrCodeType": "QrCode",
    "Content": "{{Value}}"
}

FIELD_ORDER = [
    ("Name", "名称", "line"),
    ("Content", "内容/文本", "line"),
    ("FontFamilyName", "字体", "line"),
    ("FontSizePt", "字号(pt)", "spin", 6, 200),
    ("FontStyle", "字体样式", "combo", {0: "常规", 1: "粗体", 2: "斜体", 3: "粗斜体"}),
    ("FontColor", "字体颜色", "color", "#000000"),
    ("XMm", "X坐标(mm)", "dspin", 0, 500),
    ("YMm", "Y坐标(mm)", "dspin", 0, 500),
    ("WidthMm", "宽度(mm)", "dspin", 1, 500),
    ("HeightMm", "高度(mm)", "dspin", 1, 500),
    ("HorizontalAlign", "水平对齐", "combo", {"Manual": "手动", "Left": "靠左", "Center": "居中", "Right": "靠右"}),
    ("ContentHorizontalAlign", "内容对齐", "combo", {"Left": "靠左", "Center": "居中", "Right": "靠右"}),
    ("CenterVertically", "垂直居中", "check"),
    ("AutoFitFont", "自动缩放字体", "check"),
    ("BarcodeType", "条码类型", "combo", {"Code128": "Code128", "Code39": "Code39",
                                        "Ean13": "EAN-13", "Ean8": "EAN-8",
                                        "Itf": "ITF", "Codabar": "Codabar"}),
    ("QrCodeType", "二维码类型", "combo", {"QrCode": "QR Code", "DataMatrix": "DataMatrix",
                                        "Pdf417": "PDF417", "Aztec": "Aztec"}),
    ("StrokeWidthMm", "线条粗细(mm)", "dspin", 0, 20),
    ("StrokeColor", "线条颜色", "color", "#000000"),
    ("Fill", "填充", "check"),
    ("FillColor", "填充颜色", "color", "#D3D3D3"),
    ("CornerRadiusMm", "圆角半径(mm)", "dspin", 0, 50),
    ("KeepAspectRatio", "保持宽高比", "check"),
    ("DateTimeFormat", "日期格式", "line"),
    ("RotationAngle", "旋转角度", "spin", 0, 360),
]

# 每种元素类型显示的字段
ELEMENT_FIELDS = {
    "Text": ["Name", "Content", "FontFamilyName", "FontSizePt", "FontStyle",
             "FontColor", "XMm", "YMm", "WidthMm", "HeightMm",
             "HorizontalAlign", "ContentHorizontalAlign", "CenterVertically",
             "AutoFitFont", "RotationAngle"],
    "Barcode": ["Name", "Content", "BarcodeType", "XMm", "YMm", "WidthMm",
                "HeightMm", "RotationAngle"],
    "QrCode": ["Name", "Content", "QrCodeType", "XMm", "YMm", "WidthMm",
               "HeightMm", "RotationAngle"],
    "Line": ["Name", "XMm", "YMm", "WidthMm", "HeightMm",
             "StrokeWidthMm", "StrokeColor"],
    "Rectangle": ["Name", "XMm", "YMm", "WidthMm", "HeightMm",
                  "StrokeWidthMm", "StrokeColor", "Fill", "FillColor"],
    "RoundedRectangle": ["Name", "XMm", "YMm", "WidthMm", "HeightMm",
                         "CornerRadiusMm", "StrokeWidthMm", "StrokeColor",
                         "Fill", "FillColor"],
    "Circle": ["Name", "XMm", "YMm", "WidthMm", "HeightMm",
               "StrokeWidthMm", "StrokeColor", "Fill", "FillColor"],
    "Ellipse": ["Name", "XMm", "YMm", "WidthMm", "HeightMm",
                "StrokeWidthMm", "StrokeColor", "Fill", "FillColor"],
    "Image": ["Name", "Content", "XMm", "YMm", "WidthMm", "HeightMm",
              "KeepAspectRatio"],
    "DateTime": ["Name", "DateTimeFormat", "FontFamilyName", "FontSizePt",
                 "FontStyle", "FontColor", "XMm", "YMm", "WidthMm", "HeightMm",
                 "HorizontalAlign", "ContentHorizontalAlign", "CenterVertically",
                 "AutoFitFont"],
}


# ============================================================================
# 标签设计器主控件
# ============================================================================

class CanvasPreview(QWidget):
    """标签画布预览"""
    def __init__(self):
        super().__init__()
        self.width_mm = 100
        self.height_mm = 75
        self.dpi = 203
        self.elements = []
        self.selected_index = -1
        self.setMinimumSize(200, 150)
        self.setStyleSheet("CanvasPreview { background: #e0e0e0; }")

    def set_label(self, w_mm, h_mm, dpi=203):
        self.width_mm = w_mm
        self.height_mm = h_mm
        self.dpi = dpi
        self.update()

    def set_elements(self, elements):
        self.elements = elements
        self.update()

    def set_selected(self, idx):
        self.selected_index = idx
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 计算缩放
        canvas_w = self.width()
        canvas_h = self.height()
        margin = 20
        avail_w = canvas_w - 2 * margin
        avail_h = canvas_h - 2 * margin

        aspect = self.width_mm / self.height_mm if self.height_mm else 1
        if avail_w / avail_h > aspect:
            draw_h = avail_h
            draw_w = draw_h * aspect
        else:
            draw_w = avail_w
            draw_h = draw_w / aspect

        ox, oy = margin + (avail_w - draw_w) / 2, margin + (avail_h - draw_h) / 2
        scale = draw_w / self.width_mm if self.width_mm else 1

        # 白色画布
        p.fillRect(QRect(int(ox), int(oy), int(draw_w), int(draw_h)), QColor("white"))
        p.setPen(QPen(QColor("#999"), 1))
        p.drawRect(int(ox), int(oy), int(draw_w), int(draw_h))

        # 绘制每个元素
        for i, elem in enumerate(self.elements):
            x = ox + elem.get("XMm", 0) * scale
            y = oy + elem.get("YMm", 0) * scale
            ew = elem.get("WidthMm", 50) * scale
            eh = elem.get("HeightMm", 10) * scale
            rect = QRect(int(x), int(y), int(ew), int(eh))

            etype = elem.get("Type", "Text")
            fill_color = QColor(elem.get("FillColor", "#D3D3D3"))
            stroke_color = QColor(elem.get("StrokeColor", "#000000"))

            if i == self.selected_index:
                p.setPen(QPen(QColor("#2196F3"), 2))
                p.setBrush(QBrush(QColor(33, 150, 243, 30)))
                p.drawRect(rect)
                # 选中高亮边框
                p.setPen(QPen(QColor("#2196F3"), 2, Qt.DashLine))
                p.drawRect(rect.adjusted(-2, -2, 2, 2))
                continue

            # 根据类型绘制
            p.setPen(QPen(stroke_color, 1))
            if etype == "Text":
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect)
                text = elem.get("Content", "Text")[:20]
                p.setFont(QFont("Arial", max(8, int(10 * scale))))
                p.setPen(QColor(elem.get("FontColor", "#000")))
                p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)
            elif etype == "Barcode":
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect)
                p.setPen(QColor("#333"))
                p.setFont(QFont("Arial", 8))
                p.drawText(rect, Qt.AlignCenter, "≡≡ Barcode ≡≡")
            elif etype == "QrCode":
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect)
                sz = min(ew, eh)
                p.fillRect(int(x + (ew - sz) / 2), int(y + (eh - sz) / 2),
                           int(sz), int(sz), QColor("#333"))
            elif etype in ("Rectangle", "RoundedRectangle"):
                if elem.get("Fill", False):
                    p.setBrush(QBrush(fill_color))
                else:
                    p.setBrush(Qt.NoBrush)
                if etype == "RoundedRectangle":
                    cr = int(elem.get("CornerRadiusMm", 1.5) * scale)
                    p.drawRoundedRect(rect, cr, cr)
                else:
                    p.drawRect(rect)
            elif etype in ("Circle", "Ellipse"):
                if elem.get("Fill", False):
                    p.setBrush(QBrush(fill_color))
                else:
                    p.setBrush(Qt.NoBrush)
                p.drawEllipse(rect)
            elif etype == "Line":
                cx = x + ew / 2
                p.drawLine(int(x), int(oy + draw_h / 2), int(x + ew), int(oy + draw_h / 2))
            elif etype in ("Image", "DateTime"):
                p.setBrush(Qt.NoBrush)
                p.drawRect(rect)
                p.setFont(QFont("Arial", 8))
                label = "IMG" if etype == "Image" else "Date"
                p.drawText(rect, Qt.AlignCenter, label)

        p.end()


class _FieldWidget:
    """属性字段控件工厂"""
    @staticmethod
    def create(field_def, initial_val):
        ftype = field_def[2]
        if ftype == "line":
            w = QLineEdit(str(initial_val) if initial_val else "")
            return w
        elif ftype == "spin":
            w = QSpinBox()
            w.setRange(field_def[3], field_def[4])
            try:
                w.setValue(int(initial_val) if initial_val else 0)
            except ValueError:
                w.setValue(0)
            return w
        elif ftype == "dspin":
            w = QDoubleSpinBox()
            w.setRange(field_def[3], field_def[4])
            w.setDecimals(1)
            w.setSingleStep(1)
            try:
                w.setValue(float(initial_val) if initial_val else 0)
            except ValueError:
                w.setValue(0)
            return w
        elif ftype == "combo":
            w = QComboBox()
            opt_map = field_def[3]
            for k, v in opt_map.items():
                w.addItem(v, k)
            if initial_val:
                idx = w.findData(initial_val)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            return w
        elif ftype == "check":
            w = QCheckBox()
            w.setChecked(bool(initial_val) if initial_val else False)
            return w
        elif ftype == "color":
            w = QPushButton()
            w.setText(str(initial_val) if initial_val else "#000000")
            w.setStyleSheet(f"background-color: {initial_val or '#000'}; "
                            f"min-width: 60px; max-width: 80px;")
            color_val = [initial_val or "#000000"]

            def pick_color():
                c = QColorDialog.getColor(QColor(color_val[0]), w, "选择颜色")
                if c.isValid():
                    color_val[0] = c.name()
                    w.setText(c.name())
                    w.setStyleSheet(f"background-color: {c.name()}; min-width: 60px; max-width: 80px;")
            w.clicked.connect(pick_color)
            w.get_value = lambda: color_val[0]
            return w
        return QLineEdit(str(initial_val) if initial_val else "")


class LabelDesignerWidget(QWidget):
    """标签设计器"""
    template_saved = pyqtSignal()  # 保存后触发

    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = base_dir
        self.elements = []          # list of dict
        self.current_file = ""
        self.label_width = 100
        self.label_height = 75
        self.label_dpi = 203
        self.selected_idx = -1

        self._build_ui()
        self._new_template()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # ── 顶部工具栏 ──
        toolbar = QHBoxLayout()

        self._btn_new = QPushButton("🆕 新建")
        self._btn_new.clicked.connect(self._new_template)
        toolbar.addWidget(self._btn_new)

        self._btn_open = QPushButton("📂 打开")
        self._btn_open.clicked.connect(self._open_template)
        toolbar.addWidget(self._btn_open)

        self._btn_save = QPushButton("💾 保存")
        self._btn_save.clicked.connect(self._save_template)
        toolbar.addWidget(self._btn_save)

        self._btn_save_as = QPushButton("另存为...")
        self._btn_save_as.clicked.connect(self._save_template_as)
        toolbar.addWidget(self._btn_save_as)

        toolbar.addStretch()
        self._lbl_status = QLabel("新建模板")
        toolbar.addWidget(self._lbl_status)
        main_layout.addLayout(toolbar)

        # ── 标签尺寸设置 ──
        size_bar = QHBoxLayout()
        size_bar.addWidget(QLabel("标签尺寸:"))
        self._sp_width = QDoubleSpinBox()
        self._sp_width.setRange(10, 500)
        self._sp_width.setValue(100)
        self._sp_width.setSuffix(" mm")
        self._sp_width.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._sp_width)

        size_bar.addWidget(QLabel("×"))
        self._sp_height = QDoubleSpinBox()
        self._sp_height.setRange(10, 500)
        self._sp_height.setValue(75)
        self._sp_height.setSuffix(" mm")
        self._sp_height.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._sp_height)

        size_bar.addWidget(QLabel("DPI:"))
        self._sp_dpi = QSpinBox()
        self._sp_dpi.setRange(100, 600)
        self._sp_dpi.setValue(203)
        self._sp_dpi.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._sp_dpi)
        size_bar.addStretch()
        main_layout.addLayout(size_bar)

        # ── 主体：元素列表 + 画布 + 属性编辑 ──
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：元素列表
        left_w = QWidget()
        left_layout = QVBoxLayout(left_w)
        left_layout.setContentsMargins(0, 0, 0, 0)

        add_bar = QHBoxLayout()
        self._cmb_add_type = QComboBox()
        for eng, cn in ELEMENT_TYPES:
            self._cmb_add_type.addItem(f"{cn} ({eng})", eng)
        add_bar.addWidget(self._cmb_add_type)

        self._btn_add_elem = QPushButton("➕ 添加")
        self._btn_add_elem.clicked.connect(self._add_element)
        add_bar.addWidget(self._btn_add_elem)

        self._btn_del_elem = QPushButton("🗑 删除")
        self._btn_del_elem.clicked.connect(self._delete_element)
        add_bar.addWidget(self._btn_del_elem)

        left_layout.addLayout(add_bar)

        self._lst_elements = QListWidget()
        self._lst_elements.currentRowChanged.connect(self._on_select_changed)
        left_layout.addWidget(QLabel("元素列表:"))
        left_layout.addWidget(self._lst_elements)

        # 元素排序
        sort_bar = QHBoxLayout()
        self._btn_up = QPushButton("▲ 上移")
        self._btn_up.clicked.connect(self._move_up)
        sort_bar.addWidget(self._btn_up)
        self._btn_down = QPushButton("▼ 下移")
        self._btn_down.clicked.connect(self._move_down)
        sort_bar.addWidget(self._btn_down)
        sort_bar.addStretch()
        left_layout.addLayout(sort_bar)

        splitter.addWidget(left_w)

        # 中间：画布
        self._canvas = CanvasPreview()
        splitter.addWidget(self._canvas)

        # 右侧：属性编辑
        right_w = QScrollArea()
        right_w.setWidgetResizable(True)
        self._prop_widget = QWidget()
        self._prop_layout = QVBoxLayout(self._prop_widget)
        right_w.setWidget(self._prop_widget)
        self._prop_container = right_w
        splitter.addWidget(right_w)

        splitter.setSizes([220, 400, 280])
        main_layout.addWidget(splitter, stretch=1)

        # ── 底部按钮 ──
        bottom_bar = QHBoxLayout()
        self._btn_render_preview = QPushButton("👁 完整预览")
        self._btn_render_preview.clicked.connect(self._full_preview)
        bottom_bar.addWidget(self._btn_render_preview)

        self._btn_clear_all = QPushButton("清空全部")
        self._btn_clear_all.clicked.connect(self._clear_all)
        bottom_bar.addWidget(self._btn_clear_all)
        bottom_bar.addStretch()
        main_layout.addLayout(bottom_bar)

    # ── 新建/打开/保存 ──

    def _new_template(self):
        self.elements = []
        self.current_file = ""
        self.selected_idx = -1
        self._lst_elements.blockSignals(True)
        self._lst_elements.clear()
        self._lst_elements.blockSignals(False)
        self._refresh_canvas()
        self._clear_prop_editor()
        self._lbl_status.setText("新建模板 (未保存)")

    def _open_template(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self, "打开标签模板", os.path.join(self.base_dir, "templates"),
            "标签模板 (*.label.json *.json);;所有文件 (*)"
        )
        if not fpath:
            return
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.label_width = data.get("WidthMm", 100)
            self.label_height = data.get("HeightMm", 75)
            self.elements = data.get("Elements", [])
            self.current_file = fpath

            self._sp_width.setValue(self.label_width)
            self._sp_height.setValue(self.label_height)

            self._rebuild_element_list()
            self._refresh_canvas()
            self._clear_prop_editor()
            self._lbl_status.setText(f"已打开: {os.path.basename(fpath)}")
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))

    def _save_template(self):
        if self.current_file:
            self._do_save(self.current_file)
        else:
            self._save_template_as()

    def _save_template_as(self):
        default_name = f"template_{datetime.now().strftime('%Y%m%d_%H%M%S')}.label.json"
        default_path = os.path.join(self.base_dir, "templates", default_name)
        fpath, _ = QFileDialog.getSaveFileName(
            self, "保存标签模板", default_path,
            "标签模板 (*.label.json);;JSON (*.json)"
        )
        if fpath:
            self.current_file = fpath
            self._do_save(fpath)

    def _do_save(self, fpath):
        if not fpath:
            return
        data = {
            "WidthMm": self.label_width,
            "HeightMm": self.label_height,
            "Elements": self.elements,
        }
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._lbl_status.setText(f"已保存: {os.path.basename(fpath)}")
            self.template_saved.emit()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # ── 元素管理 ──

    def _add_element(self):
        etype = self._cmb_add_type.currentData()
        elem = dict(DEFAULT_ELEMENT)
        elem["Type"] = etype
        # 自动命名
        count = sum(1 for e in self.elements if e.get("Type") == etype) + 1
        elem["Name"] = f"{etype}{count}"
        # 自动偏移位置
        base_y = max([e.get("YMm", 0) + e.get("HeightMm", 0) for e in self.elements] or [0])
        elem["YMm"] = max(5, base_y + 3)

        self.elements.append(elem)
        self._rebuild_element_list()
        self._lst_elements.setCurrentRow(len(self.elements) - 1)
        self._refresh_canvas()

    def _delete_element(self):
        if self.selected_idx < 0:
            return
        reply = QMessageBox.question(self, "确认", f"删除元素: {self.elements[self.selected_idx].get('Name', '?')}?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        del self.elements[self.selected_idx]
        self.selected_idx = -1
        self._rebuild_element_list()
        self._refresh_canvas()
        self._clear_prop_editor()

    def _move_up(self):
        if self.selected_idx <= 0:
            return
        i = self.selected_idx
        self.elements[i], self.elements[i - 1] = self.elements[i - 1], self.elements[i]
        self.selected_idx = i - 1
        self._rebuild_element_list()
        self._lst_elements.setCurrentRow(self.selected_idx)
        self._refresh_canvas()

    def _move_down(self):
        if self.selected_idx < 0 or self.selected_idx >= len(self.elements) - 1:
            return
        i = self.selected_idx
        self.elements[i], self.elements[i + 1] = self.elements[i + 1], self.elements[i]
        self.selected_idx = i + 1
        self._rebuild_element_list()
        self._lst_elements.setCurrentRow(self.selected_idx)
        self._refresh_canvas()

    def _clear_all(self):
        reply = QMessageBox.question(self, "确认", "清空全部元素?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.elements = []
        self.selected_idx = -1
        self._rebuild_element_list()
        self._refresh_canvas()
        self._clear_prop_editor()

    def _rebuild_element_list(self):
        self._lst_elements.blockSignals(True)
        self._lst_elements.clear()
        for i, elem in enumerate(self.elements):
            etype = elem.get("Type", "?")
            name = elem.get("Name", f"#{i}")
            pos = f"({elem.get('XMm', 0):.1f},{elem.get('YMm', 0):.1f})"
            self._lst_elements.addItem(f"[{etype}] {name} @{pos}")
        self._lst_elements.blockSignals(False)

    def _on_select_changed(self, idx):
        self.selected_idx = idx
        self._refresh_canvas()
        self._build_prop_editor(idx)

    # ── 属性编辑器 ──

    def _clear_prop_editor(self):
        for i in reversed(range(self._prop_layout.count())):
            w = self._prop_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._prop_widgets = {}

    def _build_prop_editor(self, idx):
        self._clear_prop_editor()
        if idx < 0 or idx >= len(self.elements):
            return

        elem = self.elements[idx]
        etype = elem.get("Type", "Text")
        fields = ELEMENT_FIELDS.get(etype, ELEMENT_FIELDS["Text"])

        title = QLabel(f"<b>属性编辑: {elem.get('Name', '')} [{etype}]</b>")
        title.setStyleSheet("font-size: 13px; padding: 5px;")
        self._prop_layout.addWidget(title)

        self._prop_widgets = {}
        form = QFormLayout()
        for fname in fields:
            fd = None
            for fd_candidate in FIELD_ORDER:
                if fd_candidate[0] == fname:
                    fd = fd_candidate
                    break
            if not fd:
                continue

            label_text = fd[1]
            val = elem.get(fname, DEFAULT_ELEMENT.get(fname, ""))
            w = _FieldWidget.create(fd, val)

            # 存储getter
            if hasattr(w, 'get_value'):
                self._prop_widgets[fname] = w.get_value
            elif isinstance(w, QLineEdit):
                self._prop_widgets[fname] = w.text
            elif isinstance(w, QSpinBox):
                self._prop_widgets[fname] = w.value
            elif isinstance(w, QDoubleSpinBox):
                self._prop_widgets[fname] = w.value
            elif isinstance(w, QComboBox):
                self._prop_widgets[fname] = lambda ww=w: ww.currentData()
            elif isinstance(w, QCheckBox):
                self._prop_widgets[fname] = w.isChecked

            w._field_name = fname
            if isinstance(w, (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox)):
                if isinstance(w, QLineEdit):
                    w.textChanged.connect(self._sync_prop)
                elif isinstance(w, QComboBox):
                    w.currentIndexChanged.connect(self._sync_prop)
                elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.valueChanged.connect(self._sync_prop)
                elif isinstance(w, QCheckBox):
                    w.stateChanged.connect(self._sync_prop)

            form.addRow(f"{label_text}:", w)

        self._prop_layout.addLayout(form)
        self._prop_layout.addStretch()

    def _sync_prop(self):
        if self.selected_idx < 0:
            return
        elem = self.elements[self.selected_idx]
        for fname, getter in self._prop_widgets.items():
            try:
                val = getter()
                old = elem.get(fname)
                if type(val) != type(old):
                    if isinstance(val, float) and isinstance(old, (int, float)):
                        val = round(val, 1)
                    elif isinstance(val, (int, float)) and isinstance(old, bool):
                        val = bool(val)
                elem[fname] = val
            except Exception:
                pass
        self._rebuild_element_list()
        self._refresh_canvas()

    # ── 画布 ──

    def _on_size_changed(self):
        self.label_width = self._sp_width.value()
        self.label_height = self._sp_height.value()
        self.label_dpi = self._sp_dpi.value()
        self._refresh_canvas()

    def _refresh_canvas(self):
        self._canvas.set_label(self.label_width, self.label_height, self.label_dpi)
        self._canvas.set_elements(self.elements)
        self._canvas.set_selected(self.selected_idx)

    def _full_preview(self):
        """完整渲染预览（使用 label_renderer）"""
        if not self.elements:
            QMessageBox.information(self, "提示", "没有元素可以预览")
            return
        try:
            from zebra_printer.label_renderer import render_label, LabelElement

            params = {}
            lelems = [LabelElement(e) for e in self.elements]
            img = render_label(self.label_width, self.label_height,
                               lelems, params, dpi=self.label_dpi)

            # 保存到临时文件并弹窗
            tmp = os.path.join("/tmp", "_designer_preview.png")
            img.save(tmp, "PNG")

            dlg = QDialog(self)
            dlg.setWindowTitle("标签预览")
            dlg.resize(600, 500)
            layout = QVBoxLayout(dlg)

            from PyQt5.QtGui import QPixmap
            from PyQt5.QtWidgets import QLabel as QL
            lbl = QL()
            pix = QPixmap(tmp)
            lbl.setPixmap(pix.scaled(550, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)

            btn = QDialogButtonBox(QDialogButtonBox.Ok)
            btn.accepted.connect(dlg.accept)
            layout.addWidget(btn)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "预览失败", str(e))
