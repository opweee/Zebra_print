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
    # 优先匹配 .label.json，再匹配 .json（避免 .label.json 被重复匹配）
    for ext in ("*.label.json", "*.json", "*.zpl"):
        pattern = os.path.join(template_dir, ext)
        for f in glob.glob(pattern):
            # 跳过已被 .label.json 匹配的文件再被 .json 匹配
            if f.endswith(".label.json") and ext == "*.json":
                continue
            files.add(os.path.basename(f))
    return sorted(files)
