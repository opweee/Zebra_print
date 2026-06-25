# -*- coding: utf-8 -*-
"""自动触发服务 — 完全对应 C# AutoPrintTriggerService.cs"""

import socket
import threading
import time
import logging
from typing import Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("trigger_service")


@dataclass
class TriggerSettings:
    enabled: bool = False
    protocol: str = "Tcp"  # "Tcp" or "Rs232"
    tcp_port: int = 9000
    serial_port: Optional[str] = None
    baud_rate: int = 9600
    trigger_keyword: str = "PRINT"


@dataclass
class TriggerMessage:
    source: str           # "TCP" / "RS232"
    payload: str          # 原始数据
    display_payload: str  # 用于显示的数据
    received_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


class AutoTriggerService:
    """自动触发打印服务 — TCP / RS232 监听"""

    def __init__(self):
        self._tcp_server: Optional[socket.socket] = None
        self._tcp_thread: Optional[threading.Thread] = None
        self._serial_thread: Optional[threading.Thread] = None
        self._running = False
        self._callback: Optional[Callable] = None  # 触发回调

    def on_trigger(self, callback: Callable[[TriggerMessage], None]):
        """设置触发回调"""
        self._callback = callback

    def start(self, settings: TriggerSettings):
        self.stop()

        if not settings.enabled:
            logger.info("自动触发已禁用")
            return

        self._running = True

        if settings.protocol == "Tcp":
            self._start_tcp(settings)
        else:
            self._start_serial(settings)

    def stop(self):
        self._running = False

        if self._tcp_server:
            try:
                self._tcp_server.close()
            except Exception:
                pass
            self._tcp_server = None

        if self._tcp_thread and self._tcp_thread.is_alive():
            self._tcp_thread.join(timeout=2)
        self._tcp_thread = None

        if self._serial_thread and self._serial_thread.is_alive():
            self._serial_thread.join(timeout=2)
        self._serial_thread = None

    def _start_tcp(self, settings: TriggerSettings):
        self._tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._tcp_server.settimeout(1.0)

        try:
            self._tcp_server.bind(("0.0.0.0", settings.tcp_port))
            self._tcp_server.listen(5)
            logger.info(f"TCP 监听已启动: 0.0.0.0:{settings.tcp_port}")
        except Exception as e:
            logger.error(f"TCP 监听启动失败: {e}")
            self._tcp_server = None
            return

        self._tcp_thread = threading.Thread(target=self._tcp_accept_loop, args=(settings,), daemon=True)
        self._tcp_thread.start()

    def _tcp_accept_loop(self, settings: TriggerSettings):
        while self._running and self._tcp_server:
            try:
                conn, addr = self._tcp_server.accept()
                threading.Thread(target=self._handle_tcp_client, args=(conn, addr, settings), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                if not self._running:
                    break
        logger.info("TCP 监听已停止")

    def _handle_tcp_client(self, conn, addr, settings: TriggerSettings):
        try:
            conn.settimeout(3)
            data = conn.recv(4096)
            if data:
                text = data.decode("utf-8", errors="ignore").strip()
                if text:
                    logger.debug(f"TCP 收到: {text!r} from {addr}")
                    # 检查触发关键字
                    if settings.trigger_keyword.upper() in text.upper():
                        self._fire_trigger("TCP", text, text)
        except socket.timeout:
            pass
        except Exception as e:
            logger.error(f"TCP 处理异常: {e}")
        finally:
            conn.close()

    def _start_serial(self, settings: TriggerSettings):
        try:
            import serial
        except ImportError:
            logger.error("pyserial 未安装！")
            return

        self._serial_thread = threading.Thread(target=self._serial_loop, args=(settings,), daemon=True)
        self._serial_thread.start()

    def _serial_loop(self, settings: TriggerSettings):
        import serial

        port = settings.serial_port or "/dev/ttyUSB0"
        while self._running:
            try:
                ser = serial.Serial(
                    port=port, baudrate=settings.baud_rate,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE, timeout=0.5
                )
                logger.info(f"串口监听已启动: {port} {settings.baud_rate}")
                buffer = b""
                break
            except serial.SerialException as e:
                logger.error(f"串口打开失败: {e}, 5秒后重试...")
                time.sleep(5)

        while self._running:
            try:
                data = ser.read(ser.in_waiting or 128)
                if data:
                    buffer += data
                    # 每 13 字节一帧 (Modbus RTU)
                    while len(buffer) >= 13:
                        frame = buffer[:13]
                        buffer = buffer[13:]

                        hex_str = " ".join(f"{b:02X}" for b in frame)

                        # 校验 CRC-16
                        crc_valid = self._validate_modbus_crc(frame)

                        # 第5字节判定: 2=合格, 3=不合格
                        if crc_valid and len(frame) >= 5:
                            byte5 = frame[4]
                            if byte5 == 2:
                                self._fire_trigger("RS232", hex_str, hex_str)
                            elif byte5 == 3:
                                logger.info(f"RS232 不合格信号: frame[4]={byte5}")
            except serial.SerialException:
                logger.error("串口读取异常，尝试重连...")
                try:
                    ser.close()
                except Exception:
                    pass
                time.sleep(3)
                break
            except Exception as e:
                logger.error(f"串口异常: {e}")
                break

        try:
            ser.close()
        except Exception:
            pass
        logger.info("串口监听已停止")

    def _fire_trigger(self, source, payload, display_payload):
        msg = TriggerMessage(source=source, payload=payload, display_payload=display_payload)
        logger.info(f"触发信号: [{source}] {display_payload}")

        if self._callback:
            try:
                self._callback(msg)
            except Exception as e:
                logger.error(f"触发回调异常: {e}")

    @staticmethod
    def _compute_modbus_crc(data):
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF

    @staticmethod
    def _validate_modbus_crc(frame):
        if len(frame) < 3:
            return False
        crc = AutoTriggerService._compute_modbus_crc(frame[:-2])
        return (crc & 0xFF) == frame[-2] and ((crc >> 8) & 0xFF) == frame[-1]
