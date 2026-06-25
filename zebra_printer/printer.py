# -*- coding: utf-8 -*-
"""打印机模块 — 替代 C# RawPrinterHelper.cs (winspool.Drv)

支持两种模式:
  1. 网络直连 (socket TCP:9100) — Zebra 打印机 RAW 端口
  2. CUPS — Linux 打印系统
"""

import socket
import subprocess
import tempfile
import os
from typing import Tuple


def print_zpl(zpl_data: bytes, host: str = "192.168.1.100", port: int = 9100,
              timeout: int = 5) -> Tuple[bool, str]:
    """通过网络直连打印 ZPL 到 Zebra 打印机

    Args:
        zpl_data: ZPL 命令（bytes，UTF-8 编码）
        host: 打印机 IP 地址
        port: 打印机端口（默认 9100 = RAW）
        timeout: 连接超时（秒）

    Returns:
        (success, error_message)
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.sendall(zpl_data)
        sock.close()
        return True, ""
    except socket.timeout:
        return False, f"连接打印机超时 {host}:{port}"
    except ConnectionRefusedError:
        return False, f"打印机拒绝连接 {host}:{port}"
    except Exception as e:
        return False, str(e)


def print_image(image, printer_name: str = None, host: str = "192.168.1.100",
                port: int = 9100, dpi: int = 203) -> Tuple[bool, str]:
    """打印图片到 Zebra 打印机（通过 ZPL ^GF 命令）

    Args:
        image: PIL Image 对象
        host: 打印机 IP
        port: 打印机端口
        dpi: 打印机 DPI

    Returns:
        (success, error_message)
    """
    try:
        from PIL import Image
        import io

        # 转换为 1-bit 黑白位图
        img = image.convert("1")  # 黑白
        w, h = img.size

        # 转为 ZPL ^GF 格式（十六进制）
        raw = img.tobytes()
        hex_data = raw.hex().upper()

        # 计算每行字节数
        bytes_per_row = (w + 7) // 8

        zpl = (
            "^XA\n"
            f"^FO0,0^GFA,{len(hex_data)},{len(hex_data)},{bytes_per_row},{hex_data}^FS\n"
            "^XZ"
        )

        return print_zpl(zpl.encode("utf-8"), host, port)
    except Exception as e:
        return False, str(e)


def get_cups_printers() -> list:
    """获取 CUPS 打印机列表（Linux）"""
    try:
        result = subprocess.run(
            ["lpstat", "-p"], capture_output=True, text=True, timeout=5
        )
        printers = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("printer "):
                name = line.split()[1]
                printers.append(name)
        return printers
    except Exception:
        return []


def cups_raw_print(zpl_data: bytes, printer_name: str) -> Tuple[bool, str]:
    """通过 CUPS RAW 打印 ZPL"""
    try:
        with tempfile.NamedTemporaryFile(suffix=".zpl", delete=False) as f:
            f.write(zpl_data)
            temp_path = f.name

        result = subprocess.run(
            ["lp", "-d", printer_name, "-o", "raw", temp_path],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(temp_path)

        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def cups_print_image(image_path: str, printer_name: str) -> Tuple[bool, str]:
    """通过 CUPS 打印图片文件（PNG/BMP 等）

    Args:
        image_path: 图片文件路径
        printer_name: CUPS 打印机名称

    Returns:
        (success, error_message)
    """
    try:
        result = subprocess.run(
            ["lp", "-d", printer_name, "-o", "fit-to-page", image_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip() or "未知错误"
    except subprocess.TimeoutExpired:
        return False, "打印超时"
    except Exception as e:
        return False, str(e)
