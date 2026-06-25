# ZebraTemplatePrinter — Linux 版

一套完整的标签模板管理系统，**纯 Python 重写**（原为 C# .NET WinForms），支持可视化标签设计、ZPL 直发打印、CUPS 系统打印机、自动触发（TCP/RS232）、标签设计器、打印统计等功能。

---

## 目录

1. [功能概览](#1-功能概览)
2. [环境要求](#2-环境要求)
3. [安装部署](#3-安装部署)
4. [快速使用](#4-快速使用)
5. [功能详解](#5-功能详解)
   - [5.1 打印](#51-打印)
   - [5.2 模板管理](#52-模板管理)
   - [5.3 标签设计](#53-标签设计)
   - [5.4 型号模板设置](#54-型号模板设置)
   - [5.5 自动触发](#55-自动触发)
   - [5.6 统计](#56-统计)
   - [5.7 打印历史](#57-打印历史)
6. [模板格式说明](#6-模板格式说明)
7. [SEQ 序列规则](#7-seq-序列规则)
8. [系统服务管理](#8-系统服务管理)
9. [常见问题](#9-常见问题)

---

## 1. 功能概览

| 功能 | 说明 |
|------|------|
| 🖨 打印 | 选择 CUPS 系统打印机，支持 JSON/ZPL 两种模板 |
| 📋 模板管理 | 管理 `templates/` 目录下的模板文件 + 型号映射 |
| ✏ 标签设计 | WYSIWYG 可视化编辑器，10 种元素类型 |
| ⚡ 自动触发 | TCP / RS232 监听，收到信号自动打印 |
| 📊 统计 | 每日趋势图、成功率饼图、模板排行、一键清零 |
| 📜 打印历史 | 按关键字/模式筛选，支持 CSV 导出 |
| 🔢 SEQ 序列 | `SEQ(start,step,width)` 规则，随打印份数自动递增 |
| 🖨 打印机 | CUPS 系统打印机（lpstat），支持标签打印机和复合机 |

### 工作模式

- **JSON 模式**（`.label.json` / `.json`）：可视化设计的标签模板 → Pillow 渲染为 PNG → CUPS 图片打印
- **ZPL 模式**（`.zpl` / `.txt`）：ZPL 命令模板 → 替换占位符 → CUPS RAW 直发打印机

---

## 2. 环境要求

- **操作系统**：Ubuntu 18.04+ / 任何 Linux 发行版
- **Python**：3.8+
- **CUPS**：已安装并配置好打印机
- **显示器**：使用 GUI 模式需要 X11 图形环境

### 依赖清单

| 依赖 | 用途 |
|------|------|
| PyQt5 | 桌面 GUI |
| Pillow | 标签渲染（文本、条码、图形） |
| python-barcode | Code128 / Code39 / EAN 等条码生成 |
| qrcode | QR Code 生成 |
| pyserial | RS232 串口通信（可选，仅自动触发需要） |

---

## 3. 安装部署

### 3.1 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-pyqt5 python3-pil
```

### 3.2 克隆项目

```bash
# 项目已部署在 /home/ubuntu/zebra_printer_linux/
cd /home/ubuntu/zebra_printer_linux
```

### 3.3 安装 Python 依赖

```bash
pip3 install python-barcode qrcode pyserial
```

### 3.4 验证打印机

```bash
lpstat -a
# 应该看到类似输出：
# ARGOX-CP-2140EX-PPLB accepting requests
# Canon_iR_C3326 accepting requests
```

### 3.5 启动

**图形界面（桌面环境）：**
```bash
cd /home/ubuntu/zebra_printer_linux
python3 gui.py
```

**网页界面（无桌面环境）：**
```bash
cd /home/ubuntu/zebra_printer_linux
python3 app.py
# 访问 http://<IP>:5050
```

**开机自启（systemd 用户服务）：**
```bash
systemctl --user enable zebra-gui.service
systemctl --user start zebra-gui.service
```

---

## 4. 快速使用

### 手动打印

1. 启动 GUI：`python3 gui.py`
2. **🖨 打印** 标签页：
   - 选择 **目标打印机**（点击 🔄 刷新）
   - 选择 **模板文件**（下拉或点击 📂 选择模板）
   - 填写 **型号**（可选，配置后自动填充）
   - 在参数表填写参数值
   - 设置 **份数**
   - 点击 **▶ 打印**

### 自动触发打印

1. 切换到 **⚡ 自动触发** 标签页
2. 选择协议（TCP / RS232）
3. 配置端口/串口参数
4. 点击 **▶ 启动监听**
5. 发送包含触发关键字的 TCP 消息即可自动打印

---

## 5. 功能详解

### 5.1 打印

打印页面主要功能区：

- **型号**：输入产品型号，已配置映射的会自动填充模板和参数
- **⚙ 型号设置**：打开型号映射配置窗口
- **模板文件**：下拉选择 `templates/` 目录下的模板，或 📂 浏览选择外部文件
- **目标打印机**：显示所有 CUPS 系统打印机
- **模板参数**：参数名/参数值表格，支持 FIXED 和 SEQ 规则
- **预览**：ZPL 模式显示 ZPL 源码，JSON 模式显示元素摘要
- **🔢 当前序列**：查看当前型号/模板范围的 SEQ 序列状态
- **♻️ 序列清零**：重置流水号（会弹出确认）
- **份数**：1-999 份，SEQ 参数随份数自动递增

### 5.2 模板管理

- **上半部分：模板文件列表**
  - 显示 `templates/` 目录下所有 `.json` / `.label.json` / `.zpl` 文件
  - 列：文件名、类型（JSON/ZPL）、大小、元素/占位符
  - 操作：📥 导入模板、🗑 删除、👁 预览、🔄 刷新
  - 双击文件 → 自动填充到打印页面

- **下半部分：型号映射管理**
  - 型号 → 模板文件的映射关系
  - 列：型号、模板文件、参数、类型、更新时间
  - 操作：➕ 添加映射、✏ 编辑、🗑 删除
  - 双击映射 → 自动填充到打印页面

### 5.3 标签设计

可视化标签编辑器，所见即所得：

- **标签尺寸**：宽(mm) / 高(mm) / DPI 设置
- **10 种元素类型**：
  - Text（文本，支持字体/大小/颜色/对齐）
  - Barcode（条码：Code128 / Code39 / EAN13 等）
  - QrCode（二维码：QR / DataMatrix / PDF417 / Aztec）
  - Line / Rectangle / RoundedRectangle / Circle / Ellipse（图形）
  - Image（图片）
  - DateTime（日期时间，自动填充当前时间）
- **元素操作**：添加、删除、上移、下移
- **属性编辑**：右侧面板根据元素类型动态显示不同属性
- **实时画布**：左侧选中元素后，中间画布实时更新
- **保存**：保存为 `.label.json` 文件，自动刷新模板列表
- **完整预览**：使用 Pillow 渲染完整标签并弹窗显示

### 5.4 型号模板设置

为每个产品型号配置独立的打印规则：

- 型号名称 → 模板文件映射
- 首选打印机（可选）
- 参数默认值（支持 FIXED 和 SEQ 表达式）
- 保存后在打印页选择型号即可自动填充所有设置

### 5.5 自动触发

支持 TCP 和 RS232 两种协议：

**TCP 模式：**
- 监听指定端口（默认 9000）
- 消息包含触发关键字（默认 PRINT）时自动打印

**RS232 模式：**
- 串口通信，默认波特率 9600
- Modbus RTU 协议，第 5 字节 = 2（合格）触发打印
- 第 5 字节 = 3（不合格）不打印

**触发统计：**
- 实时显示：总数 / 合格 / 不合格 / 合格率
- 🧹 清零统计按钮重置计数器

### 5.6 统计

打印数据的可视化分析面板：

- **时间范围筛选**：全部 / 最近7天 / 最近30天 / 今天 / 自定义
- **5 张摘要卡片**：总打印数 / 成功 / 失败 / 成功率 / 今日打印
- **每日趋势柱状图**：最近 14 天的打印次数
- **成功率饼图**：成功 vs 失败占比
- **模板使用排行表**：按打印次数排序，包含成功率
- **🗑 清除历史**：一键清空所有打印历史，重新统计

### 5.7 打印历史

完整的打印记录追踪：

- 关键字搜索（型号 / 模板 / 结果）
- 按模式筛选（ZPL / AutoTrigger / Manual / JSON）
- 双击记录自动填充到打印页面
- **📥 导出 CSV**：导出全部历史到 UTF-8 BOM 编码的 CSV 文件

---

## 6. 模板格式说明

### JSON 标签模板（`.label.json`）

结构化 JSON，描述标签尺寸和所有元素：

```json
{
  "WidthMm": 100,
  "HeightMm": 75,
  "Elements": [
    {
      "Name": "Title",
      "Type": "Text",
      "XMm": 5, "YMm": 5,
      "WidthMm": 70, "HeightMm": 12,
      "FontFamilyName": "Arial",
      "FontSizePt": 11,
      "FontColor": "#000000",
      "Content": "Work Order: {{OrderNo}}"
    },
    {
      "Name": "BarcodeMain",
      "Type": "Barcode",
      "XMm": 5, "YMm": 50,
      "WidthMm": 90, "HeightMm": 20,
      "BarcodeType": "Code128",
      "Content": "{{Barcode}}"
    }
  ]
}
```

### ZPL 模板（`.zpl`）

纯文本 ZPL 命令，`{{占位符}}` 在打印时替换：

```
^XA
^CI28
^PW800
^LL600
^FO40,40^A0N,42,42^FDWork Order: {{OrderNo}}^FS
^FO40,100^A0N,42,42^FDPart: {{PartNo}}^FS
^FO40,160^A0N,42,42^FDQty: {{Qty}}^FS
^BY3,2,120
^FO40,230^BCN,120,Y,N,N^FD{{Barcode}}^FS
^XZ
```

---

## 7. SEQ 序列规则

参数值支持序列号自动生成：

### 格式

```
SEQ(start, step[, width])
```

| 参数 | 说明 | 示例 |
|------|------|------|
| start | 起始值 | `1001` |
| step | 每次递增步长 | `1` |
| width | 补零宽度（可选） | `4` → 1001, 1002... |

### 示例

| 参数值 | 第1份 | 第2份 | 第3份 |
|--------|-------|-------|-------|
| `SEQ(1001,1,4)` | 1001 | 1002 | 1003 |
| `SN-SEQ(1,1,3)` | SN-001 | SN-002 | SN-003 |
| `SEQ(100,5)` | 100 | 105 | 110 |

### 序列管理

- 序列按**型号或模板**范围独立维护
- 打印完成后自动保存偏移到数据库
- 跨批次连续递增
- 🔢 当前序列 — 查看当前值
- ♻️ 序列清零 — 重置（弹出确认）

---

## 8. 系统服务管理

使用 systemd 用户服务管理 GUI 进程：

```bash
# 查看状态
systemctl --user status zebra-gui.service

# 启动
systemctl --user start zebra-gui.service

# 停止
systemctl --user stop zebra-gui.service

# 重启
systemctl --user restart zebra-gui.service

# 查看日志
journalctl --user -u zebra-gui.service -n 50

# 开机自启
systemctl --user enable zebra-gui.service
```

### 桌面快捷方式

`~/Desktop/zebra-printer.desktop`：
```
[Desktop Entry]
Name=Zebra Template Printer
Exec=/usr/bin/python3 /home/ubuntu/zebra_printer_linux/gui.py
Path=/home/ubuntu/zebra_printer_linux
Type=Application
Terminal=false
```

---

## 9. 常见问题

### 9.1 看不到打印机

- 确认 CUPS 打印机已安装：`lpstat -a`
- 确认打印机处于 online 状态
- 点击 🔄 刷新按钮重新加载

### 9.2 GUI 启动后闪退

```bash
# 查看日志
journalctl --user -u zebra-gui.service -n 50
```

常见原因：
- DISPLAY 环境变量错误（检查 X11 display 号）
- 缺少 PyQt5 依赖

### 9.3 打印内容变量未替换

- 检查模板中占位符是否使用 `{{参数名}}` 格式
- 检查参数表是否存在同名参数
- 参数名大小写敏感

### 9.4 自动触发已监听但不打印

- TCP：检查消息是否包含触发关键字（默认 PRINT）
- RS232：检查串口设备路径和权限
- 检查是否已选择模板和打印机
- 检查触发统计是否显示收到消息

### 9.5 序列号不递增

- 确认参数值格式正确：`SEQ(start,step,width)`
- 使用 🔢 当前序列检查当前序列状态
- 如果序列已重置，使用 ♻️ 序列清零后重新开始

---

## 项目结构

```
/home/ubuntu/zebra_printer_linux/
├── gui.py                          # 主程序入口（PyQt5 GUI）
├── app.py                          # Web 界面入口（Flask，备用）
├── config.json                     # 配置文件
├── requirements.txt                # Python 依赖
├── start.sh                        # 启动脚本
├── templates/                      # 模板文件目录
│   ├── sample.label.json           # JSON 标签模板示例
│   ├── sample.zpl                  # ZPL 模板示例
│   └── main.html                   # Web 界面模板
├── data/
│   └── print.db                    # SQLite 数据库
└── zebra_printer/                  # 后端模块
    ├── __init__.py
    ├── db.py                       # SQLite 数据库操作
    ├── zpl_renderer.py             # ZPL 模板渲染
    ├── label_renderer.py           # 标签图像渲染（Pillow）
    ├── barcode_renderer.py         # 条码/二维码生成
    ├── printer.py                  # 打印机通信（CUPS + Socket）
    ├── param_resolver.py           # 参数解析（SEQ 规则）
    ├── trigger_service.py          # 自动触发（TCP/RS232）
    ├── config.py                   # JSON 配置加载
    ├── statistics.py               # 统计面板
    └── label_designer_widget.py    # 标签设计器
```
