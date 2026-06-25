#!/bin/bash
cd /home/ubuntu/zebra_printer_linux

echo "=== Zebra模板打印机 Linux版 ==="
echo "1. GUI桌面版: python3 gui.py"
echo "2. Web版:     python3 app.py"
echo "3. 命令行:     python3 app.py --cli --template ... --data ..."
echo ""

# 检查DISPLAY，有桌面环境则启动GUI，否则启动Web
if [ -n "" ] || [ -e /tmp/.X11-unix/X0 ]; then
    echo "检测到图形桌面，启动GUI..."
    python3 gui.py
else
    echo "无图形桌面，启动Web界面..."
    python3 app.py --host 0.0.0.0 --port 5050
fi
