# -*- coding: utf-8 -*-
"""参数值解析器 — SEQ 序列规则，完全对应 C# ParameterValueResolver.cs"""

import re
from typing import Dict, Optional, Tuple


SEQ_PATTERN = re.compile(r"SEQ\((?P<body>[^()]*)\)", re.IGNORECASE)
SEQ_START_PATTERN = re.compile(r"SEQ\(", re.IGNORECASE)


class ParamResolver:
    """参数值解析器，支持 SEQ(start,step,width) 序列规则"""

    def __init__(self):
        pass

    def build_per_copy_values(self, parameter_rules, copies,
                              sequence_offsets=None):
        """为每份打印生成独立的参数值"""
        if copies <= 0:
            raise ValueError("打印份数必须大于0")

        compiled = {k: self._compile_rule(k, v) for k, v in parameter_rules.items()}

        result = []
        for i in range(copies):
            item = {k: self._resolve_value(compiled[k], i, sequence_offsets)
                    for k in parameter_rules}
            result.append(item)

        return result

    def get_sequence_tokens(self, parameter_rules: dict):
        """获取所有 SEQ token 信息，返回 [(token_key, param_name, start, step, width, raw_expr), ...]"""
        tokens = []
        for key, raw in parameter_rules.items():
            compiled = self._compile_rule(key, raw)
            for seg in compiled["segments"]:
                rule = seg["rule"]
                tokens.append((
                    seg["token_key"], key,
                    rule["start"], rule["step"], rule["width"],
                    seg["raw_expression"]
                ))
        return tokens

    def _compile_rule(self, key, raw):
        matches = SEQ_PATTERN.findall(raw)
        if not matches:
            if SEQ_START_PATTERN.search(raw):
                raise ValueError(f"参数[{key}]序列规则格式错误：缺少右括号或格式不正确")
            return {"raw": raw, "segments": []}

        # 验证SEQ数量一致
        starts_count = len(SEQ_START_PATTERN.findall(raw))
        if starts_count != len(matches):
            raise ValueError(f"参数[{key}]序列规则格式错误：存在未闭合的SEQ表达式")

        segments = []
        for idx, m in enumerate(SEQ_PATTERN.finditer(raw)):
            body = m.group("body")
            rule = self._parse_seq_body(key, body)
            segments.append({
                "start": m.start(), "length": len(m.group()),
                "rule": rule,
                "token_key": f"{key}#{idx}:{body}",
                "raw_expression": m.group()
            })

        return {"raw": raw, "segments": segments}

    @staticmethod
    def _parse_seq_body(key, body):
        parts = [p.strip() for p in body.split(",") if p.strip()]

        if len(parts) < 1 or len(parts) > 3:
            raise ValueError(f"参数[{key}]序列规则格式错误，应为 SEQ(start,step[,width])")

        try:
            start = int(parts[0])
        except ValueError:
            raise ValueError(f"参数[{key}]序列规则格式错误：start必须是整数")

        step = 1
        if len(parts) >= 2:
            try:
                step = int(parts[1])
            except ValueError:
                raise ValueError(f"参数[{key}]序列规则格式错误：step必须是整数")

        width = 0
        if len(parts) == 3:
            try:
                width = int(parts[2])
            except ValueError:
                raise ValueError(f"参数[{key}]序列规则格式错误：width必须是整数")
            if width < 0:
                raise ValueError(f"参数[{key}]序列规则格式错误：width不能小于0")

        return {"start": start, "step": step, "width": width}

    @staticmethod
    def _resolve_value(compiled, index, sequence_offsets):
        if not compiled["segments"]:
            return compiled["raw"]

        raw = compiled["raw"]
        parts = []
        cursor = 0
        for seg in compiled["segments"]:
            if seg["start"] > cursor:
                parts.append(raw[cursor:seg["start"]])

            offset = 0
            if sequence_offsets and seg["token_key"] in sequence_offsets:
                offset = sequence_offsets[seg["token_key"]]

            rule = seg["rule"]
            value = rule["start"] + rule["step"] * (offset + index)

            if rule["width"] > 0:
                parts.append(str(value).zfill(rule["width"]))
            else:
                parts.append(str(value))

            cursor = seg["start"] + seg["length"]

        if cursor < len(raw):
            parts.append(raw[cursor:])

        return "".join(parts)
