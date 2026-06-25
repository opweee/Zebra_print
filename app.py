#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZebraTemplatePrinter Linux 版 — Web 界面
========================================
完全基于原始 C# ZebraTemplatePrinter 移植

启动:
  python3 app.py                # Web 界面模式
  python3 app.py --no-web       # 仅后台服务模式
  python3 app.py --cli <args>   # 命令行模式

访问:
  http://localhost:5050
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path
from functools import wraps

# 设置项目根目录
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from zebra_printer.db import AppDb, PrintHistoryItem, TemplateMapping
from zebra_printer.param_resolver import ParamResolver
from zebra_printer.zpl_renderer import render_zpl, load_template, extract_placeholders
from zebra_printer.printer import print_zpl, print_image, get_cups_printers
from zebra_printer.label_renderer import render_label_from_json
from zebra_printer.trigger_service import AutoTriggerService, TriggerSettings, TriggerMessage
from zebra_printer.config import AppConfig, load_config as load_app_config, save_config

# ──── 初始化 ────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("zebra_printer")

db = AppDb(str(BASE_DIR / "data" / "print.db"))
db.initialize()

param_resolver = ParamResolver()
trigger_service = AutoTriggerService()
app_config = load_app_config(str(BASE_DIR / "config.json"))

# 全局统计（自动触发）
trigger_stats = {"total": 0, "ok": 0, "ng": 0}

# ──── Flask ────
try:
    from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file, send_from_directory
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

if HAS_FLASK:
    flask_app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))

    # ──── 首页 ────
    @flask_app.route("/")
    def index():
        mappings = db.get_mappings()
        printers = _get_printer_list()

        # 自动触发状态
        trig_cfg = app_config.auto_trigger
        return render_template(
            "main.html",
            mappings=mappings,
            printers=printers,
            printer_config=app_config.printer,
            trigger_config=trig_cfg,
            trigger_stats=trigger_stats,
        )

    # ──── API: 获取模板占位符 ────
    @flask_app.route("/api/template-placeholders", methods=["POST"])
    def api_template_placeholders():
        data = request.get_json()
        path = data.get("path", "")
        try:
            tpl = load_template(path)
            placeholders = extract_placeholders(tpl)
            return jsonify({"ok": True, "placeholders": placeholders})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    # ──── API: 打印 ────
    @flask_app.route("/api/print", methods=["POST"])
    def api_print():
        data = request.get_json()
        mode = data.get("mode", "ZPL")  # ZPL / Image / AutoTrigger
        copies = max(1, int(data.get("copies", 1)))

        model_name = data.get("model", "")
        template_path = data.get("template_path", "")
        printer_name = data.get("printer", "")
        parameters = data.get("parameters", {})

        # 获取打印机配置
        host = app_config.printer.host
        port = app_config.printer.port

        # 获取序列偏移
        scope_key = f"MODEL:{model_name}" if model_name else "GLOBAL"
        sequence_offsets = db.get_sequence_states(scope_key)

        success_count = 0
        fail_count = 0
        errors = []

        try:
            for copy_idx in range(copies):
                # 解析 SEQ 参数
                per_copy = param_resolver.build_per_copy_values(
                    parameters, 1,
                    {k: sequence_offsets.get(k, 0) + copy_idx for k in sequence_offsets}
                    if sequence_offsets else None
                )
                params = per_copy[0] if per_copy else parameters

                # 更新序列偏移
                for token in param_resolver.get_sequence_tokens(parameters):
                    key = token[0]  # token_key
                    old = sequence_offsets.get(key, 0)
                    sequence_offsets[key] = old + 1

                # 按模板类型打印
                if template_path.lower().endswith((".zpl", ".txt")):
                    tpl = load_template(template_path)
                    zpl = render_zpl(tpl, params)
                    ok, err = print_zpl(zpl.encode("utf-8"), host, port)
                    print_mode = "ZPL"
                elif template_path.lower().endswith(".json"):
                    # label.json 渲染为图片再打印
                    img = render_label_from_json(template_path, params, dpi=app_config.default_dpi)
                    ok, err = print_image(img, host=host, port=port, dpi=app_config.default_dpi)
                    print_mode = "Image"
                    # 保存预览图
                    preview_dir = BASE_DIR / "data" / "printed-images"
                    preview_dir.mkdir(parents=True, exist_ok=True)
                    preview_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{copy_idx}.png"
                    img.save(str(preview_dir / preview_name))
                else:
                    ok, err = False, f"不支持的模板格式: {template_path}"

                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                    if err:
                        errors.append(err)

                # 记录历史
                db.insert_print_history(PrintHistoryItem(
                    printed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    model=model_name if model_name else None,
                    template_path=template_path,
                    printer_name=printer_name or f"{host}:{port}",
                    copies=1,
                    parameters_json=json.dumps(params, ensure_ascii=False),
                    mode=print_mode if mode != "AutoTrigger" else "AutoTrigger",
                    result="Success" if ok else "Fail",
                    error_message=err if err else None,
                ))

            # 保存序列状态
            if sequence_offsets:
                db.upsert_sequence_states(scope_key, sequence_offsets)

        except Exception as e:
            logger.exception("打印异常")
            return jsonify({"ok": False, "error": str(e)})

        return jsonify({
            "ok": fail_count == 0,
            "success_count": success_count,
            "fail_count": fail_count,
            "errors": errors[:5],
        })

    # ──── API: 获取型号映射 ────
    @flask_app.route("/api/mappings")
    def api_mappings():
        mappings = db.get_mappings()
        return jsonify([{
            "model": m.model,
            "template_path": m.template_path,
            "preferred_printer": m.preferred_printer,
            "parameters_json": m.parameters_json,
        } for m in mappings])

    # ──── API: 保存型号映射 ────
    @flask_app.route("/api/mappings", methods=["POST"])
    def api_save_mappings():
        data = request.get_json()
        mappings = []
        for item in data:
            mappings.append(TemplateMapping(
                model=item["model"],
                template_path=item["template_path"],
                preferred_printer=item.get("preferred_printer"),
                parameters_json=item.get("parameters_json"),
            ))
        db.replace_mappings(mappings)
        return jsonify({"ok": True})

    # ──── API: 打印历史 ────
    @flask_app.route("/api/history")
    def api_history():
        keyword = request.args.get("keyword", "")
        mode = request.args.get("mode", "")
        result = request.args.get("result", "")
        limit = int(request.args.get("limit", 300))

        items = db.search_history(
            keyword=keyword, mode=mode, result=result, limit=limit
        )
        return jsonify([{
            "printed_at": i.printed_at,
            "model": i.model,
            "template_path": i.template_path,
            "printer_name": i.printer_name,
            "copies": i.copies,
            "parameters_json": i.parameters_json,
            "mode": i.mode,
            "result": i.result,
            "error_message": i.error_message,
        } for i in items])

    # ──── API: 导出CSV ────
    @flask_app.route("/api/history/export")
    def api_export_csv():
        items = db.search_history(limit=99999)
        import io, csv
        output = io.StringIO()
        output.write('\ufeff')  # UTF-8 BOM
        writer = csv.writer(output)
        writer.writerow(["打印时间", "型号", "模板", "打印机", "份数", "模式", "结果", "参数", "错误信息"])
        for i in items:
            writer.writerow([
                i.printed_at, i.model or "", i.template_path, i.printer_name,
                i.copies, i.mode, i.result, i.parameters_json or "", i.error_message or ""
            ])
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=print_history_{datetime.now().strftime('%Y%m%d')}.csv"}
        )

    # ──── API: 获取序列状态 ────
    @flask_app.route("/api/sequences")
    def api_sequences():
        scope_key = request.args.get("scope", "GLOBAL")
        seqs = db.get_sequence_states(scope_key)
        return jsonify(seqs)

    # ──── API: 重置序列 ────
    @flask_app.route("/api/sequences/reset", methods=["POST"])
    def api_reset_sequences():
        data = request.get_json() or {}
        scope_key = data.get("scope", "GLOBAL")
        db.reset_sequence_states(scope_key)
        return jsonify({"ok": True})

    # ──── API: 获取打印机列表 ────
    @flask_app.route("/api/printers")
    def api_printers():
        return jsonify(_get_printer_list())

    # ──── API: 触发统计 ────
    @flask_app.route("/api/trigger-stats")
    def api_trigger_stats():
        return jsonify(trigger_stats)

    # ──── API: 重置触发统计 ────
    @flask_app.route("/api/trigger-stats/reset", methods=["POST"])
    def api_reset_trigger_stats():
        global trigger_stats
        trigger_stats = {"total": 0, "ok": 0, "ng": 0}
        return jsonify({"ok": True})

    # ──── API: 切换自动触发 ────
    @flask_app.route("/api/auto-trigger", methods=["POST"])
    def api_auto_trigger():
        data = request.get_json() or {}
        enabled = data.get("enabled", False)
        if enabled:
            _start_trigger_service()
        else:
            trigger_service.stop()
        return jsonify({"ok": True, "enabled": enabled})

    # ──── API: 保存打印预览 ────
    @flask_app.route("/api/preview", methods=["POST"])
    def api_preview():
        """预览标签渲染结果（返回 base64 图片）"""
        data = request.get_json()
        template_path = data.get("template_path", "")
        parameters = data.get("parameters", {})
        try:
            if template_path.lower().endswith((".zpl", ".txt")):
                tpl = load_template(template_path)
                zpl = render_zpl(tpl, parameters)
                return jsonify({"ok": True, "type": "zpl", "data": zpl})
            elif template_path.lower().endswith(".json"):
                img = render_label_from_json(template_path, parameters, dpi=app_config.default_dpi)
                import io, base64
                buf = io.BytesIO()
                img.save(buf, "PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                return jsonify({"ok": True, "type": "image", "data": b64})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    # ──── 静态文件 ────
    @flask_app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(str(BASE_DIR / "static"), filename)


# ──── 辅助函数 ────

def _get_printer_list():
    """获取打印机列表"""
    printers = []
    # CUPS 打印机
    cups = get_cups_printers()
    for p in cups:
        printers.append({"name": p, "type": "cups"})
    # 网络打印机
    cfg = app_config.printer
    printers.append({
        "name": f"{cfg.host}:{cfg.port}",
        "type": "network",
        "host": cfg.host,
        "port": cfg.port,
    })
    return printers


# ──── 自动触发逻辑 ────

def _start_trigger_service():
    """启动自动触发服务"""
    cfg = app_config.auto_trigger
    settings = TriggerSettings(
        enabled=True,
        protocol=cfg.protocol,
        tcp_port=cfg.tcp_port,
        serial_port=cfg.serial_port,
        baud_rate=cfg.baud_rate,
        trigger_keyword=cfg.trigger_keyword,
    )

    def on_trigger(msg: TriggerMessage):
        global trigger_stats
        trigger_stats["total"] += 1

        if msg.source == "TCP":
            # TCP 模式：收到包含 PRINT 关键字的消息就打印
            trigger_stats["ok"] += 1
            _do_auto_trigger_print()
        elif msg.source == "RS232":
            # RS232 模式：第5字节=2 → 合格打印
            trigger_stats["ok"] += 1
            _do_auto_trigger_print()

    trigger_service.on_trigger(on_trigger)
    trigger_service.start(settings)


def _do_auto_trigger_print():
    """自动触发：获取当前选中的模板和参数并打印"""
    try:
        # 使用第一个型号映射（默认）
        mappings = db.get_mappings()
        if not mappings:
            logger.warning("自动触发：未配置型号映射，无法打印")
            return

        m = mappings[0]
        template_path = m.template_path
        parameters = m.get_parameters()

        scope_key = f"MODEL:{m.model}"
        offsets = db.get_sequence_states(scope_key)

        per_copy = param_resolver.build_per_copy_values(parameters, 1, offsets)
        params = per_copy[0]

        # 更新序列
        for token in param_resolver.get_sequence_tokens(parameters):
            key = token[0]
            offsets[key] = offsets.get(key, 0) + 1
        db.upsert_sequence_states(scope_key, offsets)

        host = app_config.printer.host
        port = app_config.printer.port

        if template_path.lower().endswith((".zpl", ".txt")):
            tpl = load_template(template_path)
            zpl = render_zpl(tpl, params)
            ok, err = print_zpl(zpl.encode("utf-8"), host, port)
        else:
            ok, err = False, "自动触发仅支持 ZPL 模板"

        db.insert_print_history(PrintHistoryItem(
            printed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            model=m.model,
            template_path=template_path,
            printer_name=f"{host}:{port}",
            copies=1,
            parameters_json=json.dumps(params, ensure_ascii=False),
            mode="AutoTrigger",
            result="Success" if ok else "Fail",
            error_message=err if err else None,
        ))

        if ok:
            logger.info("自动触发打印成功")
        else:
            logger.error(f"自动触发打印失败: {err}")
    except Exception as e:
        logger.exception("自动触发打印异常")


# ──── 命令行模式 ────

def run_cli(args):
    """命令行打印模式"""
    template_path = args.template
    printer_host = args.printer_host or app_config.printer.host
    printer_port = args.printer_port or app_config.printer.port
    copies = max(1, args.copies or 1)

    # 参数
    parameters = {}
    if args.data:
        for pair in args.data.split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                parameters[k.strip()] = v.strip()
    if args.json_params:
        with open(args.json_params, "r", encoding="utf-8") as f:
            parameters.update(json.load(f))

    # 序列
    scope_key = f"TEMPLATE:{template_path}"
    offsets = db.get_sequence_states(scope_key)
    per_copy = param_resolver.build_per_copy_values(parameters, copies, offsets)

    results = []
    for i, params in enumerate(per_copy):
        tpl = load_template(template_path)
        zpl = render_zpl(tpl, params)
        ok, err = print_zpl(zpl.encode("utf-8"), printer_host, printer_port)
        status = "OK" if ok else "FAIL"
        logger.info(f"[{i+1}/{copies}] {status} {printer_host}:{printer_port}")
        results.append({"copy": i+1, "ok": ok, "error": err})

    # 更新序列
    for token in param_resolver.get_sequence_tokens(parameters):
        key = token[0]
        offsets[key] = offsets.get(key, 0) + copies
    db.upsert_sequence_states(scope_key, offsets)

    # 保存历史
    for r in results:
        db.insert_print_history(PrintHistoryItem(
            printed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            template_path=template_path,
            printer_name=f"{printer_host}:{printer_port}",
            copies=1,
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            mode="ZPL",
            result="Success" if r["ok"] else "Fail",
            error_message=r.get("error"),
        ))

    ok_count = sum(1 for r in results if r["ok"])
    logger.info(f"完成: {ok_count}/{copies} 成功")
    return ok_count == copies


# ──── 入口 ────

def main():
    parser = argparse.ArgumentParser(description="ZebraTemplatePrinter Linux 版")
    parser.add_argument("--no-web", action="store_true", help="不启动 Web 界面")
    parser.add_argument("--port", type=int, default=5050, help="Web 服务端口 (默认 5050)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Web 绑定地址")

    # CLI 模式参数
    parser.add_argument("--cli", action="store_true", help="命令行模式")
    parser.add_argument("--template", type=str, help="模板文件路径")
    parser.add_argument("--printer-host", type=str, help="打印机 IP")
    parser.add_argument("--printer-port", type=int, help="打印机端口")
    parser.add_argument("--copies", type=int, default=1, help="打印份数")
    parser.add_argument("--data", type=str, help="参数: k1=v1;k2=v2")
    parser.add_argument("--json-params", type=str, help="参数 JSON 文件")
    parser.add_argument("--test-print", action="store_true", help="测试打印")

    args = parser.parse_args()

    # CLI 模式
    if args.cli:
        success = run_cli(args)
        sys.exit(0 if success else 1)

    if args.test_print:
        zpl = "^XA^PW400^LL80^FO20,20^A0N,30,30^FDTest Print^FS^XZ"
        ok, err = print_zpl(zpl.encode("utf-8"), app_config.printer.host, app_config.printer.port)
        print(f"测试打印: {'OK' if ok else 'FAIL'} - {err or '成功'}")
        return

    # Web 模式
    if not HAS_FLASK:
        logger.error("Flask 未安装！请执行: pip install flask")
        sys.exit(1)

    if not args.no_web:
        logger.info(f"启动 Web 界面: http://{args.host}:{args.port}")
        logger.info(f"打印机: {app_config.printer.host}:{app_config.printer.port}")
        flask_app.run(host=args.host, port=args.port, debug=False)
    else:
        # 纯后台服务模式
        logger.info("启动后台服务模式 (无 Web 界面)")
        _start_trigger_service()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            trigger_service.stop()
            logger.info("已停止")


if __name__ == "__main__":
    main()
