# -*- coding: utf-8 -*-
"""ZPL 模板渲染器 — 支持 .zpl 纯文本模板 和 .json/.label.json 标签模板"""

import re
import os
import json

PLACEHOLDER_RE = re.compile(r"\{\{(?P<name>[A-Za-z0-9_]+)\}\}")


def render_zpl(template: str, parameters: dict) -> str:
    """渲染 ZPL 模板，替换 {{参数名}} 占位符"""
    missing = set()

    def replacer(m):
        key = m.group("name")
        if key in parameters:
            return _escape_for_zpl(str(parameters[key]))
        missing.add(key)
        return m.group(0)

    result = PLACEHOLDER_RE.sub(replacer, template)

    if missing:
        raise ValueError(f"模板缺少参数: {', '.join(sorted(missing))}")

    return result


def _escape_for_zpl(text: str) -> str:
    """转义 ZPL 特殊字符"""
    if not text:
        return ""
    return text.replace("^", " ").replace("~", " ")


def load_template(template_path: str) -> str:
    """加载 ZPL 模板文件（.zpl / .txt）"""
    if not os.path.isabs(template_path):
        base = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(os.path.dirname(base), template_path)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def is_json_template(template_path: str) -> bool:
    """判断模板文件是否为 JSON 格式（.json 或 .label.json）"""
    return template_path.endswith((".json", ".label.json"))


def load_json_template(template_path: str) -> dict:
    """加载 JSON 标签模板，返回 {"width_mm", "height_mm", "elements", "raw"}"""
    if not os.path.isabs(template_path):
        base = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(os.path.dirname(base), template_path)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "width_mm": data.get("WidthMm", 100),
        "height_mm": data.get("HeightMm", 75),
        "elements": data.get("Elements", []),
        "raw": data,
    }


def extract_placeholders(template: str) -> list:
    """提取模板中所有占位符名称"""
    return sorted(set(m.group("name") for m in PLACEHOLDER_RE.finditer(template)))


def extract_json_placeholders(template_data: dict) -> list:
    """从 JSON 标签模板中提取所有占位符名称"""
    placeholders = set()
    for elem in template_data.get("elements", []):
        content = elem.get("Content", "")
        placeholders.update(m.group("name") for m in PLACEHOLDER_RE.finditer(content))
    return sorted(placeholders)


def list_templates(template_dir: str = "templates") -> list:
    """列出模板目录下所有支持的文件（.label.json, .json, .zpl）"""
    import glob
    files = set()
    for ext in ("*.label.json", "*.json", "*.zpl"):
        pattern = os.path.join(template_dir, ext)
        for f in glob.glob(pattern):
            if f.endswith(".label.json") and ext == "*.json":
                continue
            files.add(os.path.basename(f))
    return sorted(files)


def _mm_to_dots(mm: float, dpi: int = 203) -> int:
    """毫米转打印机点数"""
    return max(1, int(round(mm * dpi / 25.4)))


def _resolve_placeholders(text: str, params: dict) -> str:
    """替换字符串中的 {{占位符}}"""
    return PLACEHOLDER_RE.sub(lambda m: str(params.get(m.group("name"), m.group(0))), text)


def elements_to_zpl(elements: list, width_mm: float, height_mm: float,
                    params: dict, dpi: int = 203) -> str:
    """将 LabelTemplate 元素列表转换为 ZPL 命令"""
    mm = lambda v: _mm_to_dots(v, dpi)

    lines = ["^XA", f"^PW{mm(width_mm)}", f"^LL{mm(height_mm)}", "^CI28"]

    for elem in elements:
        etype = elem.get("Type", "Text")
        x = mm(elem.get("XMm", 0))
        y = mm(elem.get("YMm", 0))
        w = mm(elem.get("WidthMm", 50))
        h = mm(elem.get("HeightMm", 10))
        content = _resolve_placeholders(elem.get("Content", ""), params)
        content = content.replace("^", " ").replace("~", " ")
        if not content and etype not in ("Line", "Rectangle", "RoundedRectangle", "Circle", "Ellipse", "Image"):
            continue

        try:
            if etype == "Text":
                font_size = int(elem.get("FontSizePt", 11) * 1.5)
                lines.append(f"^FO{x},{y}^A0N,{font_size},{font_size}^FD{content}^FS")

            elif etype == "Barcode":
                bc_type = elem.get("BarcodeType", "Code128")
                bc_map = {"Code128": "BC", "Code39": "B3", "Ean13": "BE", "Ean8": "B8", "Itf": "BI", "Codabar": "BK"}
                zpl_bc = bc_map.get(bc_type, "BC")
                height_dots = max(20, h)
                lines.append(f"^FO{x},{y}^BY2,2,{height_dots}")
                lines.append(f"^{zpl_bc}N,{height_dots},Y,N,N^FD{content}^FS")

            elif etype == "QrCode":
                lines.append(f"^FO{x},{y}^BQN,2,{h * 2}")
                lines.append(f"^FDQA,{content}^FS")

            elif etype == "Line":
                thickness = mm(elem.get("StrokeWidthMm", 0.3))
                if w >= h:
                    lines.append(f"^FO{x},{y + h // 2}^GB{w},{thickness},{thickness}^FS")
                else:
                    lines.append(f"^FO{x + w // 2},{y}^GB{thickness},{h},{thickness}^FS")

            elif etype in ("Rectangle", "RoundedRectangle"):
                thickness = mm(elem.get("StrokeWidthMm", 0.3))
                fill = elem.get("Fill", False)
                color = "B" if fill else ""  # B=black fill
                l = elem.get("CornerRadiusMm", 0) if etype == "RoundedRectangle" else 0
                if l > 0:
                    r = mm(l)
                    lines.append(f"^FO{x},{y}^GB{w},{h},{thickness},{r},{color}^FS")
                else:
                    lines.append(f"^FO{x},{y}^GB{w},{h},{thickness},{color}^FS")

            elif etype in ("Circle", "Ellipse"):
                thickness = mm(elem.get("StrokeWidthMm", 0.3))
                d = min(w, h)  # diameter
                lines.append(f"^FO{x + (w - d) // 2},{y + (h - d) // 2}^GC{d},{thickness}^FS")

            elif etype == "DateTime":
                from datetime import datetime
                fmt = elem.get("DateTimeFormat", "%Y-%m-%d %H:%M:%S")
                now = datetime.now().strftime(fmt)
                font_size = int(elem.get("FontSizePt", 11) * 1.5)
                lines.append(f"^FO{x},{y}^A0N,{font_size},{font_size}^FD{now}^FS")

            elif etype == "Image":
                lines.append(f"^FO{x},{y}^GFA,...^FS  // Image: {content}")

        except Exception:
            pass  # skip problematic elements

    lines.append("^XZ")
    return "\n".join(lines)
    """列出模板目录下所有支持的文件（.label.json, .json, .zpl）"""
    import glob
    files = set()
    # 优先匹配 .label.json，再匹配 .json（避免 .label.json 被重复匹配）
    for ext in ("*.label.json", "*.json", "*.zpl"):
        pattern = os.path.join(template_dir, ext)
        for f in glob.glob(pattern):
            # 跳过已被 .label.json 匹配的文件再被 .json 匹配
            if f.endswith(".label.json") and ext == "*.json":
                continue
            files.add(os.path.basename(f))
    return sorted(files)
