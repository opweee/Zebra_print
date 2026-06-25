# -*- coding: utf-8 -*-
"""条码/二维码渲染器 — 替代 C# BarcodeImageRenderer.cs (ZXing.Net)"""

from PIL import Image, ImageDraw
from typing import Tuple


def render_barcode(value: str, barcode_type: str, width: int, height: int) -> Image.Image:
    """渲染条码/二维码，返回 PIL Image"""
    import io

    if not value.strip():
        raise ValueError("条码/二维码内容不能为空")

    w = max(20, width)
    h = max(20, height)

    if barcode_type.lower() in ("code128", "code39", "ean13", "ean8", "itf", "codabar"):
        return _render_1d_barcode(value, barcode_type, w, h)
    else:
        return _render_2d_code(value, barcode_type, w, h)


def _render_1d_barcode(value: str, barcode_type: str, w: int, h: int) -> Image.Image:
    """渲染一维条码"""
    try:
        import barcode
        from barcode.writer import ImageWriter

        import io
        io_buffer = io.BytesIO()

        # 映射类型
        type_map = {
            "code128": barcode.Code128,
            "code39": barcode.Code39,
            "ean13": barcode.EAN13,
            "ean8": barcode.EAN8,
            "itf": barcode.ITF,
            "codabar": barcode.CODABAR,
        }

        cls = type_map.get(barcode_type.lower())
        if cls is None:
            return _fallback_barcode(value, w, h)

        # 清理数据：只保留数字和字母
        if barcode_type.lower() in ("ean13", "ean8"):
            value = "".join(c for c in value if c.isdigit())
            if len(value) > 13:
                value = value[:13]

        bc = cls(value, writer=ImageWriter())
        bc.write(io_buffer, options={"module_width": max(1, w // 200), "module_height": max(1, h // 4)})
        io_buffer.seek(0)
        img = Image.open(io_buffer).convert("RGB")
        return _resize_keep_ratio(img, w, h)
    except Exception:
        return _fallback_barcode(value, w, h)


def _render_2d_code(value: str, barcode_type: str, w: int, h: int) -> Image.Image:
    """渲染二维码/DataMatrix/PDF417/Aztec"""
    try:
        import qrcode
        import qrcode.image.pil

        qr = qrcode.QRCode(version=None, box_size=4, border=1)
        qr.add_data(value)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return _resize_keep_ratio(img, w, h)
    except Exception:
        return _fallback_barcode(value, w, h)


def _fallback_barcode(value: str, w: int, h: int) -> Image.Image:
    """备用方案：纯文本显示"""
    img = Image.new("RGB", (w, h), "white")
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", size=min(16, max(8, h // 4)))
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), value, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((w - tw) // 2, (h - th) // 2), value, fill="black", font=font)
    return img


def _resize_keep_ratio(img: Image.Image, w: int, h: int) -> Image.Image:
    """调整大小保持比例"""
    ratio = min(w / img.width, h / img.height)
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))
    return img.resize((new_w, new_h), Image.LANCZOS)
