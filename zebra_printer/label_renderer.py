# -*- coding: utf-8 -*-
"""标签图像渲染器 — 替代 C# LabelImageRenderer.cs (GDI+)"""

import json
import os
import math
from datetime import datetime
from enum import Enum
from typing import Dict

from PIL import Image, ImageDraw, ImageFont, ImageColor


class LabelElementType(Enum):
    TEXT = "Text"
    BARCODE = "Barcode"
    QRCODE = "QrCode"
    LINE = "Line"
    RECTANGLE = "Rectangle"
    ROUNDED_RECTANGLE = "RoundedRectangle"
    CIRCLE = "Circle"
    ELLIPSE = "Ellipse"
    IMAGE = "Image"
    DATETIME = "DateTime"


class LabelContentHorizontalAlign(Enum):
    LEFT = "Left"
    CENTER = "Center"
    RIGHT = "Right"


class LabelHorizontalAlign(Enum):
    MANUAL = "Manual"
    LEFT = "Left"
    CENTER = "Center"
    RIGHT = "Right"


class LabelBarcodeType(Enum):
    CODE128 = "Code128"
    CODE39 = "Code39"
    EAN13 = "Ean13"
    EAN8 = "Ean8"
    ITF = "Itf"
    CODABAR = "Codabar"


class QrCodeType(Enum):
    QRCODE = "QrCode"
    DATAMATRIX = "DataMatrix"
    PDF417 = "Pdf417"
    AZTEC = "Aztec"


# ── 枚举值映射表 ──
_TYPE_MAP = {0: LabelElementType.TEXT, 1: LabelElementType.BARCODE,
             2: LabelElementType.QRCODE, 3: LabelElementType.LINE,
             4: LabelElementType.RECTANGLE, 5: LabelElementType.ROUNDED_RECTANGLE,
             6: LabelElementType.CIRCLE, 7: LabelElementType.ELLIPSE,
             8: LabelElementType.IMAGE, 9: LabelElementType.DATETIME}
_BC_MAP = {0: LabelBarcodeType.CODE128, 1: LabelBarcodeType.CODE39,
           2: LabelBarcodeType.EAN13, 3: LabelBarcodeType.EAN8,
           4: LabelBarcodeType.ITF, 5: LabelBarcodeType.CODABAR}
_QR_MAP = {0: QrCodeType.QRCODE, 1: QrCodeType.DATAMATRIX,
           2: QrCodeType.PDF417, 3: QrCodeType.AZTEC}
_HA_MAP = {0: LabelHorizontalAlign.MANUAL, 1: LabelHorizontalAlign.LEFT,
           2: LabelHorizontalAlign.CENTER, 3: LabelHorizontalAlign.RIGHT}
_CHA_MAP = {0: LabelContentHorizontalAlign.LEFT, 1: LabelContentHorizontalAlign.CENTER,
            2: LabelContentHorizontalAlign.RIGHT}


def _to_enum(val, enum_cls, int_map, default):
    """将字符串或整数转换为枚举值"""
    if val is None:
        return default
    if isinstance(val, int):
        return int_map.get(val, default)
    # 字符串：按 value 或 name 匹配（大小写不敏感）
    s = str(val)
    for member in enum_cls:
        if member.value == s or member.name.upper() == s.upper():
            return member
    return default


class LabelElement:
    def __init__(self, data: dict):
        self.name = data.get("Name", "Element")
        self.x_mm = data.get("XMm", 0)
        self.y_mm = data.get("YMm", 0)
        self.width_mm = data.get("WidthMm", 50)
        self.height_mm = data.get("HeightMm", 10)
        self.center_vertically = data.get("CenterVertically", False)
        self.auto_fit_font = data.get("AutoFitFont", True)
        self.font_family = data.get("FontFamilyName", "Arial")
        self.font_style = data.get("FontStyle", 0)  # 0=Regular, 1=Bold, 2=Italic, 3=BoldItalic
        self.font_color = data.get("FontColor", "#000000")
        self.font_size_pt = data.get("FontSizePt", 11)
        self.stroke_width_mm = data.get("StrokeWidthMm", 0.3)
        self.stroke_color = data.get("StrokeColor", "#000000")
        self.fill = data.get("Fill", False)
        self.fill_color = data.get("FillColor", "#D3D3D3")
        self.corner_radius_mm = data.get("CornerRadiusMm", 1.5)
        self.keep_aspect_ratio = data.get("KeepAspectRatio", True)
        self.date_time_format = data.get("DateTimeFormat", "yyyy-MM-dd HH:mm:ss")
        self.rotation_angle = data.get("RotationAngle", 0)
        self.content = data.get("Content", "")

        # 统一解析枚举（兼容字符串和整数）
        self.type = _to_enum(data.get("Type"), LabelElementType, _TYPE_MAP, LabelElementType.TEXT)
        self.barcode_type = _to_enum(data.get("BarcodeType"), LabelBarcodeType, _BC_MAP, LabelBarcodeType.CODE128)
        self.qr_code_type = _to_enum(data.get("QrCodeType"), QrCodeType, _QR_MAP, QrCodeType.QRCODE)
        self.horizontal_align = _to_enum(data.get("HorizontalAlign"), LabelHorizontalAlign, _HA_MAP, LabelHorizontalAlign.MANUAL)
        self.content_horizontal_align = _to_enum(data.get("ContentHorizontalAlign"), LabelContentHorizontalAlign, _CHA_MAP, LabelContentHorizontalAlign.LEFT)

    def get_rect_mm(self, canvas_w_mm: float, canvas_h_mm: float) -> tuple:
        """计算实际 mm 坐标（含对齐）"""
        x = self.x_mm
        y = self.y_mm
        if self.horizontal_align == LabelHorizontalAlign.LEFT:
            x = 0
        elif self.horizontal_align == LabelHorizontalAlign.CENTER:
            x = (canvas_w_mm - self.width_mm) / 2
        elif self.horizontal_align == LabelHorizontalAlign.RIGHT:
            x = canvas_w_mm - self.width_mm
        if self.center_vertically:
            y = (canvas_h_mm - self.height_mm) / 2
        return (x, y, self.width_mm, self.height_mm)


def render_label_from_json(json_path, parameters, dpi=203, output_path=None):
    """从 .label.json 模板渲染标签为 PNG 图片

    Args:
        json_path: .label.json 模板文件路径
        parameters: 参数字典 {key: value}
        dpi: 渲染 DPI（默认 203，匹配 Zebra 打印机标准）
        output_path: 输出 PNG 路径，不指定则返回 Image 对象

    Returns:
        PIL.Image 对象
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    template_w_mm = data["WidthMm"]
    template_h_mm = data["HeightMm"]
    elements = [LabelElement(e) for e in data.get("Elements", [])]

    return render_label(template_w_mm, template_h_mm, elements, parameters, dpi, output_path)


def render_label(width_mm, height_mm, elements: list, parameters,
                 dpi=203, output_path=None):
    """渲染标签"""
    w_px = max(1, int(round(width_mm / 25.4 * dpi)))
    h_px = max(1, int(round(height_mm / 25.4 * dpi)))

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img)

    for element in elements:
        content = _resolve_content(element, parameters)

        x, y, ew, eh = element.get_rect_mm(width_mm, height_mm)
        rect = (
            _mm2px(x, dpi), _mm2px(y, dpi),
            _mm2px(ew, dpi), _mm2px(eh, dpi)
        )

        try:
            if element.type == LabelElementType.TEXT:
                _draw_text(draw, element, content, rect)
            elif element.type == LabelElementType.BARCODE:
                _draw_barcode(img, draw, element, content, rect)
            elif element.type == LabelElementType.QRCODE:
                _draw_qrcode(img, draw, element, content, rect)
            elif element.type == LabelElementType.LINE:
                _draw_line(draw, element, rect, dpi)
            elif element.type in (LabelElementType.RECTANGLE, LabelElementType.ROUNDED_RECTANGLE):
                _draw_rect(draw, element, rect, dpi)
            elif element.type in (LabelElementType.CIRCLE, LabelElementType.ELLIPSE):
                _draw_ellipse(draw, element, rect, dpi)
            elif element.type == LabelElementType.IMAGE:
                _draw_image(img, draw, element, content, rect)
            elif element.type == LabelElementType.DATETIME:
                _draw_datetime(draw, element, rect)
        except Exception as e:
            draw.rectangle(rect, outline="red", width=1)
            _draw_simple_text(draw, str(e)[:50], rect, fill="red")

    if output_path:
        img.save(output_path, "PNG")

    return img


def _resolve_content(element, parameters):
    """解析内容，替换 {{key}} 占位符"""
    content = element.content or ""
    if element.type == LabelElementType.DATETIME:
        fmt = element.date_time_format or "yyyy-MM-dd HH:mm:ss"
        return datetime.now().strftime(fmt)
    for key, val in parameters.items():
        content = content.replace("{{%s}}" % key, str(val))
    return content


def _draw_text(draw, element, text, rect):
    """绘制文本（自动缩放字体）"""
    rx, ry, rw, rh = rect

    try:
        size = element.font_size_pt * 1.5  # pt to px approx
        if element.auto_fit_font and text:
            size = 40
            while size > 4:
                try:
                    font = _get_font(element.font_family, int(size),
                                     bold=(element.font_style in (1, 3)),
                                     italic=(element.font_style in (2, 3)))
                except Exception:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                if tw <= rw + 1 and th <= rh + 1:
                    break
                size -= 1

        font = _get_font(element.font_family, int(size),
                         bold=(element.font_style in (1, 3)),
                         italic=(element.font_style in (2, 3)))

        color = _parse_color(element.font_color, (0, 0, 0))

        # 水平对齐
        if element.content_horizontal_align == LabelContentHorizontalAlign.CENTER:
            x = rx + rw // 2
            anchor = "mt"
        elif element.content_horizontal_align == LabelContentHorizontalAlign.RIGHT:
            x = rx + rw
            anchor = "rt"
        else:
            x = rx
            anchor = "lt"

        y = ry + (rh - _text_height(draw, text, font)) // 2

        draw.text((x, y), text, fill=color, font=font, anchor=anchor)
    except Exception:
        draw.rectangle(rect, outline="red", width=1)


def _draw_barcode(img, draw, element, content, rect):
    """绘制条码"""
    rx, ry, rw, rh = rect
    try:
        from .barcode_renderer import render_barcode
        bc_img = render_barcode(content, element.barcode_type.value, rw, rh)
        img.paste(bc_img, (rx, ry))
    except Exception:
        draw.rectangle(rect, outline="orange")
        _draw_simple_text(draw, content, rect, fill="black")


def _draw_qrcode(img, draw, element, content, rect):
    """绘制二维码"""
    rx, ry, rw, rh = rect
    size = min(rw, rh)
    try:
        from .barcode_renderer import render_barcode
        qr_img = render_barcode(content, element.qr_code_type.value, size, size)
        img.paste(qr_img, (rx + (rw - qr_img.width) // 2, ry + (rh - qr_img.height) // 2))
    except Exception:
        draw.rectangle(rect, outline="orange")
        _draw_simple_text(draw, content, rect, fill="black")


def _draw_line(draw, element, rect, dpi):
    rx, ry, rw, rh = rect
    y = ry + rh // 2
    color = _parse_color(element.stroke_color, (0, 0, 0))
    width = max(1, _mm2px(element.stroke_width_mm, dpi))
    draw.line([(rx, y), (rx + rw, y)], fill=color, width=width)


def _draw_rect(draw, element, rect, dpi):
    rx, ry, rw, rh = rect
    stroke_c = _parse_color(element.stroke_color, (0, 0, 0))
    stroke_w = max(1, _mm2px(element.stroke_width_mm, dpi))

    if element.fill:
        fill_c = _parse_color(element.fill_color, (211, 211, 211))
        if element.type == LabelElementType.ROUNDED_RECTANGLE:
            cr = max(1, _mm2px(element.corner_radius_mm, dpi))
            draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=cr, fill=fill_c, outline=stroke_c, width=stroke_w)
        else:
            draw.rectangle([rx, ry, rx + rw, ry + rh], fill=fill_c, outline=stroke_c, width=stroke_w)
    else:
        if element.type == LabelElementType.ROUNDED_RECTANGLE:
            cr = max(1, _mm2px(element.corner_radius_mm, dpi))
            draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=cr, outline=stroke_c, width=stroke_w)
        else:
            draw.rectangle([rx, ry, rx + rw, ry + rh], outline=stroke_c, width=stroke_w)


def _draw_ellipse(draw, element, rect, dpi):
    rx, ry, rw, rh = rect
    if element.type == LabelElementType.CIRCLE:
        size = min(rw, rh)
        rx += (rw - size) // 2
        ry += (rh - size) // 2
        rw = rh = size

    stroke_c = _parse_color(element.stroke_color, (0, 0, 0))
    stroke_w = max(1, _mm2px(element.stroke_width_mm, dpi))

    if element.fill:
        fill_c = _parse_color(element.fill_color, (211, 211, 211))
        draw.ellipse([rx, ry, rx + rw, ry + rh], fill=fill_c, outline=stroke_c, width=stroke_w)
    else:
        draw.ellipse([rx, ry, rx + rw, ry + rh], outline=stroke_c, width=stroke_w)


def _draw_image(img, draw, element, content, rect):
    rx, ry, rw, rh = rect
    path = content.strip()
    if not path or not os.path.exists(path):
        draw.rectangle(rect, outline="red")
        _draw_simple_text(draw, "IMG?", rect, fill="red")
        return

    try:
        src = Image.open(path).convert("RGB")
        if element.keep_aspect_ratio:
            ratio = min(rw / src.width, rh / src.height)
            nw = int(src.width * ratio)
            nh = int(src.height * ratio)
            src = src.resize((nw, nh), Image.LANCZOS)
            px = rx + (rw - nw) // 2
            py = ry + (rh - nh) // 2
        else:
            src = src.resize((rw, rh), Image.LANCZOS)
            px, py = rx, ry
        img.paste(src, (px, py))
    except Exception:
        draw.rectangle(rect, outline="red")


def _draw_datetime(draw, element, rect):
    fmt = element.date_time_format or "yyyy-MM-dd HH:mm:ss"
    text = datetime.now().strftime(fmt)
    _draw_text(draw, element, text, rect)


def _draw_simple_text(draw, text, rect, fill="black"):
    try:
        font = ImageFont.load_default()
        draw.text((rect[0] + 2, rect[1] + 2), text, fill=fill, font=font)
    except Exception:
        pass


def _get_font(family, size, bold=False, italic=False):
    """获取字体（多平台 fallback）"""
    font_paths = []

    # Linux
    if os.name == "posix":
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ]
    # Windows
    else:
        if bold:
            font_paths = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/Arial.ttf"]
        else:
            font_paths = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/Arial.ttf"]

    for fp in font_paths:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)

    return ImageFont.load_default()


def _text_height(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def _parse_color(hex_str, default):
    try:
        if hex_str.startswith("#"):
            r = int(hex_str[1:3], 16)
            g = int(hex_str[3:5], 16)
            b = int(hex_str[5:7], 16)
            return (r, g, b)
    except Exception:
        pass
    return default


def _mm2px(mm, dpi):
    return max(1, int(round(mm / 25.4 * dpi)))
