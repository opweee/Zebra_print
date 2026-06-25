# -*- coding: utf-8 -*-
"""配置管理模块"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class PrinterConfig:
    host: str = "192.168.1.100"
    port: int = 9100
    mode: str = "network"  # "network" / "cups"
    cups_printer: str = ""


@dataclass
class AutoTriggerConfig:
    enabled: bool = False
    protocol: str = "Tcp"  # "Tcp" / "Rs232"
    tcp_port: int = 9000
    serial_port: str = "/dev/ttyUSB0"
    baud_rate: int = 9600
    trigger_keyword: str = "PRINT"


@dataclass
class AppConfig:
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    auto_trigger: AutoTriggerConfig = field(default_factory=AutoTriggerConfig)
    data_dir: str = "data"
    template_dir: str = "templates"
    db_path: str = "data/print.db"
    default_dpi: int = 203


def load_config(path="config.json") -> AppConfig:
    """加载配置文件"""
    if not os.path.exists(path):
        return AppConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    config = AppConfig()

    if "printer" in data:
        p = data["printer"]
        config.printer = PrinterConfig(
            host=p.get("host", "192.168.1.100"),
            port=p.get("port", 9100),
            mode=p.get("mode", "network"),
            cups_printer=p.get("cups_printer", ""),
        )

    if "auto_trigger" in data:
        a = data["auto_trigger"]
        config.auto_trigger = AutoTriggerConfig(
            enabled=a.get("enabled", False),
            protocol=a.get("protocol", "Tcp"),
            tcp_port=a.get("tcp_port", 9000),
            serial_port=a.get("serial_port", "/dev/ttyUSB0"),
            baud_rate=a.get("baud_rate", 9600),
            trigger_keyword=a.get("trigger_keyword", "PRINT"),
        )

    config.data_dir = data.get("data_dir", "data")
    config.template_dir = data.get("template_dir", "templates")
    config.db_path = data.get("db_path", "data/print.db")
    config.default_dpi = data.get("default_dpi", 203)

    return config


def save_config(config: AppConfig, path="config.json"):
    """保存配置文件"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2, ensure_ascii=False)
