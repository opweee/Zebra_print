# -*- coding: utf-8 -*-
"""标签设计器 — 支持拖拽，属性编辑器分组显示"""

import os, json
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QMessageBox,
    QSplitter, QScrollArea, QFrame, QColorDialog, QFileDialog, QTextEdit,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QCursor


# ── 元素类型 ──
ELEMENT_TYPES = [
    ("Text", "文本"), ("Barcode", "条码"), ("QrCode", "二维码"),
    ("Line", "线条"), ("Rectangle", "矩形"), ("RoundedRectangle", "圆角矩形"),
    ("Circle", "圆形"), ("Ellipse", "椭圆"), ("Image", "图片"), ("DateTime", "日期时间"),
]

DEFAULT_ELEMENT = {
    "Name": "Element", "Type": "Text",
    "XMm": 5, "YMm": 5, "WidthMm": 60, "HeightMm": 12,
    "HorizontalAlign": "Manual", "CenterVertically": False,
    "ContentHorizontalAlign": "Left", "AutoFitFont": True,
    "FontFamilyName": "Arial", "FontStyle": 0, "FontColor": "#000000", "FontSizePt": 11,
    "StrokeWidthMm": 0.3, "StrokeColor": "#000000",
    "Fill": False, "FillColor": "#D3D3D3", "CornerRadiusMm": 1.5,
    "KeepAspectRatio": True, "DateTimeFormat": "yyyy-MM-dd HH:mm:ss",
    "RotationAngle": 0, "BarcodeType": "Code128", "QrCodeType": "QrCode",
    "Content": "{{Value}}"
}

# 每个字段定义: (字段名, 标签, 类型, [参数...])
FIELD_DEFS = {
    "Name": ("名称", "line"),
    "Content": ("内容/文本", "line"),
    "FontFamilyName": ("字体", "line"),
    "FontSizePt": ("字号(pt)", "spin", 6, 200),
    "FontStyle": ("风格", "combo", {0: "常规", 1: "粗体", 2: "斜体", 3: "粗斜体"}),
    "FontColor": ("颜色", "color", "#000000"),
    "XMm": ("X(mm)", "dspin", 0, 500),
    "YMm": ("Y(mm)", "dspin", 0, 500),
    "WidthMm": ("宽(mm)", "dspin", 1, 500),
    "HeightMm": ("高(mm)", "dspin", 1, 500),
    "HorizontalAlign": ("水平对齐", "combo", {"Manual": "手动", "Left": "靠左", "Center": "居中", "Right": "靠右"}),
    "ContentHorizontalAlign": ("内容对齐", "combo", {"Left": "靠左", "Center": "居中", "Right": "靠右"}),
    "CenterVertically": ("垂直居中", "check"),
    "AutoFitFont": ("自动缩放", "check"),
    "BarcodeType": ("条码类型", "combo", {"Code128": "Code128", "Code39": "Code39",
        "Ean13": "EAN-13", "Ean8": "EAN-8", "Itf": "ITF", "Codabar": "Codabar"}),
    "QrCodeType": ("二维码类型", "combo", {"QrCode": "QR Code", "DataMatrix": "DataMatrix",
        "Pdf417": "PDF417", "Aztec": "Aztec"}),
    "StrokeWidthMm": ("线粗(mm)", "dspin", 0, 20),
    "StrokeColor": ("线颜色", "color", "#000000"),
    "Fill": ("填充", "check"),
    "FillColor": ("填充色", "color", "#D3D3D3"),
    "CornerRadiusMm": ("圆角(mm)", "dspin", 0, 50),
    "KeepAspectRatio": ("保持比例", "check"),
    "DateTimeFormat": ("日期格式", "line"),
    "RotationAngle": ("旋转(°)", "spin", 0, 360),
}

# 每种元素类型的属性分组: {组名: [字段名列表]}
ELEMENT_GROUPS = {
    "Text": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "内容":  ["Content", "FontFamilyName", "FontSizePt", "FontColor", "FontStyle",
                  "HorizontalAlign", "ContentHorizontalAlign", "CenterVertically", "AutoFitFont"],
    },
    "Barcode": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "内容":  ["Content", "BarcodeType"],
    },
    "QrCode": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "内容":  ["Content", "QrCodeType"],
    },
    "Line": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "样式":  ["StrokeWidthMm", "StrokeColor"],
    },
    "Rectangle": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "样式":  ["StrokeWidthMm", "StrokeColor", "Fill", "FillColor"],
    },
    "RoundedRectangle": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "样式":  ["CornerRadiusMm", "StrokeWidthMm", "StrokeColor", "Fill", "FillColor"],
    },
    "Circle": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "样式":  ["StrokeWidthMm", "StrokeColor", "Fill", "FillColor"],
    },
    "Ellipse": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "样式":  ["StrokeWidthMm", "StrokeColor", "Fill", "FillColor"],
    },
    "Image": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "内容":  ["Content", "KeepAspectRatio"],
    },
    "DateTime": {
        "位置":  ["XMm", "YMm", "WidthMm", "HeightMm"],
        "内容":  ["DateTimeFormat", "FontFamilyName", "FontSizePt", "FontColor",
                  "FontStyle", "HorizontalAlign", "ContentHorizontalAlign", "CenterVertically", "AutoFitFont"],
    },
}


def _get_widget_value(w):
    """通用获取控件值"""
    if hasattr(w, 'get_value'):
        return w.get_value()
    if isinstance(w, QLineEdit):
        return w.text()
    if isinstance(w, QSpinBox):
        return w.value()
    if isinstance(w, QDoubleSpinBox):
        return w.value()
    if isinstance(w, QComboBox):
        return w.currentData()
    if isinstance(w, QCheckBox):
        return w.isChecked()
    return ""


def _create_field_widget(field_key, current_val):
    """根据字段定义创建编辑控件"""
    if field_key not in FIELD_DEFS:
        w = QLineEdit(str(current_val) if current_val else "")
        return w

    fd = FIELD_DEFS[field_key]
    ftype = fd[1]

    if ftype == "line":
        w = QLineEdit(str(current_val) if current_val else "")
        return w

    elif ftype == "spin":
        w = QSpinBox()
        w.setRange(fd[2], fd[3])
        try:
            w.setValue(int(current_val) if current_val else 0)
        except ValueError:
            w.setValue(0)
        return w

    elif ftype == "dspin":
        w = QDoubleSpinBox()
        w.setRange(fd[2], fd[3])
        w.setDecimals(1)
        w.setSingleStep(1)
        try:
            w.setValue(float(current_val) if current_val else 0)
        except ValueError:
            w.setValue(0)
        return w

    elif ftype == "combo":
        w = QComboBox()
        for k, v in fd[2].items():
            w.addItem(v, k)
        if current_val is not None:
            idx = w.findData(current_val)
            if idx >= 0:
                w.setCurrentIndex(idx)
        return w

    elif ftype == "check":
        w = QCheckBox()
        w.setChecked(bool(current_val) if current_val else False)
        return w

    elif ftype == "color":
        w = QPushButton()
        hex_val = str(current_val) if current_val else "#000000"
        w.setText(hex_val)
        w.setStyleSheet(f"background-color: {hex_val}; min-width: 50px; max-width: 70px;")
        color_val = [hex_val]

        def pick_color():
            c = QColorDialog.getColor(QColor(color_val[0]), w, "选择颜色")
            if c.isValid():
                color_val[0] = c.name()
                w.setText(c.name())
                w.setStyleSheet(f"background-color: {c.name()}; min-width: 50px; max-width: 70px;")
        w.clicked.connect(pick_color)
        w.get_value = lambda: color_val[0]
        return w

    return QLineEdit(str(current_val) if current_val else "")


# ============================================================================
# 画布
# ============================================================================

class CanvasPreview(QWidget):
    selection_changed = pyqtSignal(int)
    element_moved = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.width_mm = 100
        self.height_mm = 75
        self.dpi = 203
        self.elements = []
        self.selected_index = -1
        self.dragging = False
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.setMinimumSize(200, 150)
        self.setMouseTracking(False)
        self.setCursor(QCursor(Qt.ArrowCursor))
        self.setStyleSheet("background: #e0e0e0;")

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

    def _get_canvas_rect(self):
        cw, ch = self.width(), self.height()
        m = 20
        aw, ah = cw - 2 * m, ch - 2 * m
        aspect = self.width_mm / self.height_mm if self.height_mm else 1
        if aw / ah > aspect:
            dh = ah
            dw = dh * aspect
        else:
            dw = aw
            dh = dw / aspect
        ox = m + (aw - dw) / 2
        oy = m + (ah - dh) / 2
        scale = dw / self.width_mm if self.width_mm else 1
        return ox, oy, dw, dh, scale

    def _px_to_mm(self, px_x, px_y):
        ox, oy, _, _, scale = self._get_canvas_rect()
        return (px_x - ox) / scale, (px_y - oy) / scale

    def _hit_test(self, px_x, px_y):
        ox, oy, _, _, scale = self._get_canvas_rect()
        for i in range(len(self.elements) - 1, -1, -1):
            elem = self.elements[i]
            ex = ox + elem.get("XMm", 0) * scale
            ey = oy + elem.get("YMm", 0) * scale
            ew = elem.get("WidthMm", 50) * scale
            eh = elem.get("HeightMm", 10) * scale
            if ex <= px_x <= ex + ew and ey <= px_y <= ey + eh:
                return i
        return -1

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self._hit_test(event.x(), event.y())
            if idx >= 0:
                self.selected_index = idx
                self.dragging = True
                mx, my = self._px_to_mm(event.x(), event.y())
                elem = self.elements[idx]
                self.drag_offset_x = mx - elem.get("XMm", 0)
                self.drag_offset_y = my - elem.get("YMm", 0)
                self.setCursor(QCursor(Qt.ClosedHandCursor))
                self.selection_changed.emit(idx)
            else:
                if self.selected_index >= 0:
                    self.selected_index = -1
                    self.selection_changed.emit(-1)
            self.update()

    def mouseMoveEvent(self, event):
        if self.dragging and self.selected_index >= 0:
            mx, my = self._px_to_mm(event.x(), event.y())
            elem = self.elements[self.selected_index]
            elem["XMm"] = max(0, round(mx - self.drag_offset_x, 1))
            elem["YMm"] = max(0, round(my - self.drag_offset_y, 1))
            self.update()
            self.element_moved.emit(self.selected_index)

    def mouseReleaseEvent(self, event):
        if self.dragging:
            self.dragging = False
            self.setCursor(QCursor(Qt.ArrowCursor))
            self.update()
            if self.selected_index >= 0:
                self.element_moved.emit(self.selected_index)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        ox, oy, dw, dh, scale = self._get_canvas_rect()

        p.fillRect(QRect(int(ox), int(oy), int(dw), int(dh)), QColor("white"))
        p.setPen(QPen(QColor("#999"), 1))
        p.drawRect(int(ox), int(oy), int(dw), int(dh))

        for i, elem in enumerate(self.elements):
            x = ox + elem.get("XMm", 0) * scale
            y = oy + elem.get("YMm", 0) * scale
            ew = elem.get("WidthMm", 50) * scale
            eh = elem.get("HeightMm", 10) * scale
            rect = QRect(int(x), int(y), int(ew), int(eh))
            etype = elem.get("Type", "Text")
            fill_color = QColor(elem.get("FillColor", "#D3D3D3"))
            stroke_color = QColor(elem.get("StrokeColor", "#000000"))
            is_selected = (i == self.selected_index)

            if is_selected:
                p.setPen(QPen(QColor("#2196F3"), 2, Qt.DashLine))
                p.setBrush(QBrush(QColor(33, 150, 243, 20)))
                p.drawRect(rect.adjusted(-3, -3, 3, 3))

            p.setPen(QPen(stroke_color, 1) if not is_selected else QPen(QColor("#2196F3"), 2))

            if etype == "Text":
                # 文本图标：左上角蓝色 "T" + 内容预览
                ih = max(14, int(eh))
                p.setBrush(QBrush(QColor("#E3F2FD")))
                p.drawRoundedRect(rect, 2, 2)
                p.setPen(QPen(QColor("#1565C0"), 1))
                p.setFont(QFont("Arial", max(9, int(ih * 0.45)), QFont.Bold))
                tr = QRect(int(x + 2), int(y + (eh - ih) / 2), int(ih), int(ih))
                p.drawRoundedRect(tr, 3, 3)
                p.setPen(QColor("#1565C0"))
                p.drawText(tr, Qt.AlignCenter, "T")
                # 文本预览
                text = elem.get("Content", "T")[:int(ew / max(5, fs := max(7, int(8 * scale))))]
                fs2 = max(7, int(9 * scale))
                p.setFont(QFont("Arial", fs2))
                p.setPen(QColor(elem.get("FontColor", "#333")))
                p.drawText(QRect(int(x + ih + 4), int(y), int(ew - ih - 4), int(eh)),
                           Qt.AlignLeft | Qt.AlignVCenter, text)

            elif etype == "Barcode":
                # 条码图标：灰色背景 + 垂直条纹
                p.setBrush(QBrush(QColor("#F5F5F5")))
                p.drawRect(rect)
                p.setPen(Qt.NoPen)
                bar_colors = [QColor("#222"), QColor("#444"), QColor("#000"),
                              QColor("#333"), QColor("#111"), QColor("#555"),
                              QColor("#222"), QColor("#333"), QColor("#000"), QColor("#444")]
                bar_w = max(2, int(ew / 15))
                for bi, bc in enumerate(bar_colors):
                    bx = int(x + bi * bar_w * 1.4)
                    if bx < int(x + ew):
                        p.fillRect(bx, int(y + 2), bar_w, int(eh - 4), bc)
                # 底部数字
                p.setPen(QColor("#555"))
                p.setFont(QFont("Arial", max(5, int(7 * scale))))
                bc_text = elem.get("Content", "")[:8]
                p.drawText(rect.adjusted(0, 0, 0, -2), Qt.AlignBottom | Qt.AlignHCenter, bc_text or "Code128")

            elif etype == "QrCode":
                # 二维码图标：灰色背景 + 网格
                p.setBrush(QBrush(QColor("#F5F5F5")))
                p.drawRect(rect)
                sz = min(ew, eh) - 4
                if sz > 8:
                    grid_x = int(x + (ew - sz) / 2 + 2)
                    grid_y = int(y + (eh - sz) / 2 + 2)
                    cells = 7
                    cell_sz = sz / cells
                    for ci in range(cells):
                        for cj in range(cells):
                            if (ci + cj) % 3 == 0 or (ci == 0 or cj == 0 or ci == cells - 1 or cj == cells - 1):
                                rx = int(grid_x + ci * cell_sz)
                                ry = int(grid_y + cj * cell_sz)
                                rw = int(cell_sz) + 1
                                rh = int(cell_sz) + 1
                                p.fillRect(rx, ry, rw, rh, QColor("#333"))

            elif etype in ("Rectangle", "RoundedRectangle"):
                p.setBrush(QBrush(fill_color) if elem.get("Fill") else Qt.NoBrush)
                if etype == "RoundedRectangle":
                    cr = int(elem.get("CornerRadiusMm", 1.5) * scale)
                    p.drawRoundedRect(rect, cr, cr)
                else:
                    p.drawRect(rect)

            elif etype in ("Circle", "Ellipse"):
                p.setBrush(QBrush(fill_color) if elem.get("Fill") else Qt.NoBrush)
                p.drawEllipse(rect)

            elif etype == "Line":
                cy = int(oy + dh / 2)
                lw = max(1, int(elem.get("StrokeWidthMm", 0.3) * scale))
                p.setPen(QPen(stroke_color, lw))
                p.drawLine(int(x), cy, int(x + ew), cy)

            elif etype == "Image":
                # 图片图标：山/太阳符号
                p.setBrush(QBrush(QColor("#FFF8E1")))
                p.drawRect(rect)
                p.setPen(QPen(QColor("#FF8F00"), 1))
                # 山形
                path = QPainterPath()
                path.moveTo(int(x + 4), int(y + eh - 4))
                path.lineTo(int(x + ew / 2), int(y + 4))
                path.lineTo(int(x + ew - 4), int(y + eh - 4))
                path.closeSubpath()
                p.drawPath(path)
                p.setFont(QFont("Arial", max(5, int(7 * scale))))
                p.setPen(QColor("#FF8F00"))
                p.drawText(rect, Qt.AlignBottom | Qt.AlignHCenter, "IMG")

            elif etype == "DateTime":
                # 日期时间图标：日历符号
                p.setBrush(QBrush(QColor("#E8F5E9")))
                p.drawRect(rect)
                p.setPen(QPen(QColor("#2E7D32"), 1))
                # 日历头
                head_h = max(4, int(eh * 0.3))
                p.fillRect(int(x + 2), int(y + 2), int(ew - 4), head_h, QColor("#4CAF50"))
                p.setFont(QFont("Arial", max(5, int(8 * scale))))
                p.setPen(QColor("white"))
                p.drawText(QRect(int(x + 2), int(y + 2), int(ew - 4), head_h),
                           Qt.AlignCenter, "📅")
                # 日期数字
                p.setPen(QColor("#2E7D32"))
                p.setFont(QFont("Arial", max(6, int(10 * scale))))
                p.drawText(QRect(int(x + 2), int(y + head_h + 2), int(ew - 4), int(eh - head_h - 4)),
                           Qt.AlignCenter, elem.get("DateTimeFormat", "").replace("%", "")[:6])

        p.end()


# ============================================================================
# 标签设计器
# ============================================================================

class LabelDesignerWidget(QWidget):
    template_saved = pyqtSignal(str)

    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = base_dir
        self.elements = []
        self.current_file = ""
        self.label_width = 100
        self.label_height = 75
        self.label_dpi = 203
        self.selected_idx = -1
        self._suppress_sync = False
        self._build_ui()
        self._update_title()

    def _update_title(self):
        name = os.path.basename(self.current_file) if self.current_file else "新建模板"
        self._lbl_status.setText(name)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        # 工具栏
        toolbar = QHBoxLayout()
        for btn_def in [
            ("🆕 新建", self._new_template),
            ("📂 打开", self._open_template),
            ("💾 保存", self._save_template),
            ("另存为...", self._save_template_as),
        ]:
            b = QPushButton(btn_def[0])
            b.clicked.connect(btn_def[1])
            toolbar.addWidget(b)
        toolbar.addStretch()
        self._lbl_status = QLabel("新建模板")
        toolbar.addWidget(self._lbl_status)
        main_layout.addLayout(toolbar)

        # 尺寸栏
        size_bar = QHBoxLayout()
        size_bar.addWidget(QLabel("标签:"))
        self._sp_width = QDoubleSpinBox()
        self._sp_width.setRange(10, 500); self._sp_width.setValue(100); self._sp_width.setSuffix(" mm")
        self._sp_width.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._sp_width)
        size_bar.addWidget(QLabel("×"))
        self._sp_height = QDoubleSpinBox()
        self._sp_height.setRange(10, 500); self._sp_height.setValue(75); self._sp_height.setSuffix(" mm")
        self._sp_height.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._sp_height)
        size_bar.addWidget(QLabel("DPI:"))
        self._sp_dpi = QSpinBox()
        self._sp_dpi.setRange(100, 600); self._sp_dpi.setValue(203)
        self._sp_dpi.valueChanged.connect(self._on_size_changed)
        size_bar.addWidget(self._sp_dpi)
        size_bar.addStretch()
        main_layout.addLayout(size_bar)

        # 主体
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：元素列表
        left_w = QWidget()
        left_lo = QVBoxLayout(left_w)
        left_lo.setContentsMargins(0, 0, 0, 0)
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
        left_lo.addLayout(add_bar)
        left_lo.addWidget(QLabel("元素（点击选中，拖拽移动）:"))
        self._lst_elements = QListWidget()
        self._lst_elements.currentRowChanged.connect(self._on_list_select_changed)
        left_lo.addWidget(self._lst_elements)
        sort_bar = QHBoxLayout()
        self._btn_up = QPushButton("▲ 上移")
        self._btn_up.clicked.connect(self._move_up)
        sort_bar.addWidget(self._btn_up)
        self._btn_down = QPushButton("▼ 下移")
        self._btn_down.clicked.connect(self._move_down)
        sort_bar.addWidget(self._btn_down)
        sort_bar.addStretch()
        left_lo.addLayout(sort_bar)
        splitter.addWidget(left_w)

        # 中间：画布
        self._canvas = CanvasPreview()
        self._canvas.selection_changed.connect(self._on_canvas_select_changed)
        self._canvas.element_moved.connect(self._on_element_moved)
        splitter.addWidget(self._canvas)

        # 右侧：属性编辑
        right_w = QScrollArea()
        right_w.setWidgetResizable(True)
        self._prop_widget = QWidget()
        self._prop_layout = QVBoxLayout(self._prop_widget)
        right_w.setWidget(self._prop_widget)
        splitter.addWidget(right_w)
        splitter.setSizes([180, 400, 260])
        main_layout.addWidget(splitter, stretch=1)

        # 底部
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
        self._canvas.set_label(self.label_width, self.label_height, self.label_dpi)
        self._canvas.set_selected(-1)
        self._canvas.set_elements([])
        self._clear_prop_editor()
        self._update_title()

    def _open_template(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self, "打开标签模板", os.path.join(self.base_dir, "templates"),
            "标签模板 (*.label.json *.json);;所有文件 (*)")
        if not fpath:
            return
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            self.label_width = data.get("WidthMm", 100)
            self.label_height = data.get("HeightMm", 75)
            self.elements = data.get("Elements", [])
            self.current_file = fpath
            self._canvas.set_elements(self.elements)
            self._canvas.set_label(self.label_width, self.label_height, self.label_dpi)
            self._sp_width.blockSignals(True)
            self._sp_height.blockSignals(True)
            self._sp_width.setValue(self.label_width)
            self._sp_height.setValue(self.label_height)
            self._sp_width.blockSignals(False)
            self._sp_height.blockSignals(False)
            self._rebuild_element_list()
            self._clear_prop_editor()
            self._update_title()
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
            "标签模板 (*.label.json);;JSON (*.json)")
        if fpath:
            self.current_file = fpath
            self._do_save(fpath)

    def _do_save(self, fpath):
        data = {"WidthMm": self.label_width, "HeightMm": self.label_height, "Elements": self.elements}
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._update_title()
            self.template_saved.emit(os.path.basename(fpath))
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # ── 元素管理 ──

    def _add_element(self):
        etype = self._cmb_add_type.currentData()
        elem = dict(DEFAULT_ELEMENT)
        elem["Type"] = etype
        count = sum(1 for e in self.elements if e.get("Type") == etype) + 1
        elem["Name"] = f"{etype}{count}"
        base_y = max([e.get("YMm", 0) + e.get("HeightMm", 0) for e in self.elements] or [0])
        elem["YMm"] = max(5, base_y + 3)
        self.elements.append(elem)
        self._rebuild_element_list()
        self._lst_elements.setCurrentRow(len(self.elements) - 1)
        self._canvas.set_elements(self.elements)
        self._canvas.set_selected(len(self.elements) - 1)

    def _delete_element(self):
        if self.selected_idx < 0:
            return
        reply = QMessageBox.question(self, "确认",
            f"删除: {self.elements[self.selected_idx].get('Name', '?')}?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        del self.elements[self.selected_idx]
        self.selected_idx = -1
        self._rebuild_element_list()
        self._canvas.set_elements(self.elements)
        self._canvas.set_selected(-1)
        self._clear_prop_editor()

    def _move_up(self):
        if self.selected_idx <= 0:
            return
        i = self.selected_idx
        self.elements[i], self.elements[i-1] = self.elements[i-1], self.elements[i]
        self.selected_idx = i - 1
        self._rebuild_element_list()
        self._lst_elements.setCurrentRow(self.selected_idx)
        self._canvas.set_elements(self.elements)
        self._canvas.set_selected(self.selected_idx)

    def _move_down(self):
        if self.selected_idx < 0 or self.selected_idx >= len(self.elements) - 1:
            return
        i = self.selected_idx
        self.elements[i], self.elements[i+1] = self.elements[i+1], self.elements[i]
        self.selected_idx = i + 1
        self._rebuild_element_list()
        self._lst_elements.setCurrentRow(self.selected_idx)
        self._canvas.set_elements(self.elements)
        self._canvas.set_selected(self.selected_idx)

    def _clear_all(self):
        reply = QMessageBox.question(self, "确认", "清空全部元素?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.elements = []
        self.selected_idx = -1
        self._rebuild_element_list()
        self._canvas.set_elements([])
        self._canvas.set_selected(-1)
        self._clear_prop_editor()

    def _rebuild_element_list(self):
        self._lst_elements.blockSignals(True)
        self._lst_elements.clear()
        for i, elem in enumerate(self.elements):
            etype = elem.get("Type", "?")
            name = elem.get("Name", f"#{i}")
            x = elem.get("XMm", 0)
            y = elem.get("YMm", 0)
            self._lst_elements.addItem(f"[{etype}] {name} @({x:.1f},{y:.1f})")
        self._lst_elements.blockSignals(False)

    # ── 选择同步 ──

    def _on_list_select_changed(self, idx):
        self._suppress_sync = True
        self.selected_idx = idx
        self._canvas.set_selected(idx)
        self._build_prop_editor(idx)
        self._suppress_sync = False

    def _on_canvas_select_changed(self, idx):
        if self._suppress_sync:
            return
        self.selected_idx = idx
        self._lst_elements.blockSignals(True)
        if idx >= 0:
            self._lst_elements.setCurrentRow(idx)
        else:
            self._lst_elements.clearSelection()
        self._lst_elements.blockSignals(False)
        self._build_prop_editor(idx)

    def _on_element_moved(self, idx):
        if idx >= 0:
            self._rebuild_element_list()
            self._lst_elements.blockSignals(True)
            self._lst_elements.setCurrentRow(idx)
            self._lst_elements.blockSignals(False)
            self._sync_prop_from_elem(idx)

    # ── 属性编辑器（分组）──

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
        groups = ELEMENT_GROUPS.get(etype, ELEMENT_GROUPS["Text"])
        self._prop_widgets = {}

        # 标题
        title = QLabel(f"<b>{elem.get('Name')} [{etype}]</b>")
        title.setStyleSheet("font-size: 13px; padding: 5px 0;")
        self._prop_layout.addWidget(title)

        for group_name, field_list in groups.items():
            gb = QGroupBox(group_name)
            gb.setStyleSheet("QGroupBox { font-weight: bold; font-size: 11px; margin-top: 4px; }")
            form = QFormLayout(gb)
            form.setSpacing(3)
            form.setContentsMargins(8, 12, 8, 4)

            for fname in field_list:
                if fname not in FIELD_DEFS:
                    continue
                fd = FIELD_DEFS[fname]
                label_text = fd[0]
                val = elem.get(fname, DEFAULT_ELEMENT.get(fname, ""))
                w = _create_field_widget(fname, val)
                self._prop_widgets[fname] = w
                # 连接信号
                if isinstance(w, (QLineEdit,)):
                    w.textChanged.connect(self._sync_prop)
                elif isinstance(w, (QComboBox,)):
                    w.currentIndexChanged.connect(self._sync_prop)
                elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.valueChanged.connect(self._sync_prop)
                elif isinstance(w, QCheckBox):
                    w.stateChanged.connect(self._sync_prop)
                form.addRow(f"{label_text}:", w)

            self._prop_layout.addWidget(gb)

        self._prop_layout.addStretch()

    def _sync_prop(self):
        if self.selected_idx < 0 or self._suppress_sync:
            return
        elem = self.elements[self.selected_idx]
        for fname, w in list(self._prop_widgets.items()):
            try:
                val = _get_widget_value(w)
                old = elem.get(fname)
                if isinstance(val, float) and isinstance(old, (int, float)):
                    val = round(val, 1)
                elif isinstance(val, (int, float)) and isinstance(old, bool):
                    val = bool(val)
                elem[fname] = val
            except Exception:
                pass
        self._rebuild_element_list()
        self._canvas.set_elements(self.elements)

    def _sync_prop_from_elem(self, idx):
        if idx < 0 or idx >= len(self.elements):
            return
        elem = self.elements[idx]
        for fname, w in self._prop_widgets.items():
            if fname not in ("XMm", "YMm", "WidthMm", "HeightMm"):
                continue
            val = elem.get(fname)
            try:
                if isinstance(w, QDoubleSpinBox):
                    w.blockSignals(True)
                    w.setValue(float(val) if val else 0)
                    w.blockSignals(False)
            except Exception:
                pass

    # ── 画布 ──

    def _on_size_changed(self):
        self.label_width = self._sp_width.value()
        self.label_height = self._sp_height.value()
        self.label_dpi = self._sp_dpi.value()
        self._canvas.set_label(self.label_width, self.label_height, self.label_dpi)

    def _full_preview(self):
        if not self.elements:
            QMessageBox.information(self, "提示", "没有元素可以预览")
            return
        try:
            from zebra_printer.label_renderer import render_label, LabelElement
            lelems = [LabelElement(e) for e in self.elements]
            img = render_label(self.label_width, self.label_height, lelems, {}, dpi=self.label_dpi)
            tmp = "/tmp/_designer_preview.png"
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
