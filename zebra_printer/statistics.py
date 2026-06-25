# -*- coding: utf-8 -*-
"""统计模块 — 打印统计、图表、报表"""

import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QGroupBox,
    QGridLayout, QSizePolicy, QDateEdit
)
from PyQt5.QtCore import Qt, QDate, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath

from zebra_printer.db import AppDb

import sqlite3


# ── 颜色方案 ──
CLR_SUCCESS = QColor(76, 175, 80)    # 绿色
CLR_FAIL = QColor(244, 67, 54)        # 红色
CLR_PRIMARY = QColor(33, 150, 243)    # 蓝色
CLR_ORANGE = QColor(255, 152, 0)      # 橙色
CLR_PURPLE = QColor(156, 39, 176)     # 紫色
CLR_CYAN = QColor(0, 188, 212)        # 青色
CLR_CHART_COLORS = [
    QColor(33, 150, 243), QColor(76, 175, 80), QColor(255, 152, 0),
    QColor(156, 39, 176), QColor(0, 188, 212), QColor(244, 67, 54),
    QColor(121, 85, 72), QColor(96, 125, 139),
]
CLR_BG = QColor(245, 245, 245)


class SummaryCard(QFrame):
    """统计卡片：标题 + 大号数值 + 颜色条"""
    def __init__(self, title, value, color=CLR_PRIMARY, suffix=""):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"SummaryCard {{ background: white; border-radius: 8px; "
            f"border-left: 4px solid {color.name()}; }}"
        )
        self.setMinimumHeight(90)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {color.name()}; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl_title)

        self._lbl_value = QLabel(str(value))
        self._lbl_value.setStyleSheet(f"color: #333; font-size: 28px; font-weight: bold;")
        layout.addWidget(self._lbl_value)

        self._suffix = suffix

    def set_value(self, val):
        self._lbl_value.setText(f"{val}{self._suffix}")


class BarChartWidget(QWidget):
    """简单柱状图 (QPainter)"""
    def __init__(self, title=""):
        super().__init__()
        self.title = title
        self.labels = []
        self.values = []
        self.bar_color = CLR_PRIMARY
        self.setMinimumHeight(200)

    def set_data(self, labels, values, color=None):
        self.labels = labels
        self.values = values
        if color:
            self.bar_color = color
        self.update()

    def paintEvent(self, event):
        if not self.labels:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin_left, margin_bottom, margin_top, margin_right = 50, 40, 30, 20
        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        # 标题
        if self.title:
            p.setFont(QFont("Arial", 11, QFont.Bold))
            p.setPen(QColor("#333"))
            p.drawText(QRect(margin_left, 5, chart_w, 25), Qt.AlignLeft, self.title)

        if not chart_w > 20 or not chart_h > 20:
            p.end()
            return

        max_val = max(self.values) if self.values else 1
        bar_count = len(self.values)
        bar_width = max(8, int(chart_w / bar_count * 0.6))
        gap = max(4, int(chart_w / bar_count * 0.4))

        # Y轴基线
        p.setPen(QPen(QColor("#ccc"), 1))
        p.drawLine(margin_left, margin_top, margin_left, margin_top + chart_h)

        # X轴基线
        p.drawLine(margin_left, margin_top + chart_h,
                   margin_left + chart_w, margin_top + chart_h)

        # 柱状图
        for i, (label, val) in enumerate(zip(self.labels, self.values)):
            x = margin_left + gap // 2 + i * (bar_width + gap)
            bar_h = int((val / max_val) * chart_h * 0.95) if max_val else 0
            y = margin_top + chart_h - bar_h

            color = self.bar_color if not isinstance(self.bar_color, list) else \
                CLR_CHART_COLORS[i % len(CLR_CHART_COLORS)]
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(x, y, bar_width, bar_h, 3, 3)

            # 数值标签
            p.setFont(QFont("Arial", 8))
            p.setPen(QColor("#555"))
            p.drawText(QRect(x, y - 16, bar_width, 14),
                       Qt.AlignCenter, str(val))

            # X轴标签
            p.setPen(QColor("#555"))
            p.drawText(QRect(x - 10, margin_top + chart_h + 5,
                             bar_width + 20, 20),
                       Qt.AlignCenter, label)

        p.end()


class PieChartWidget(QWidget):
    """简单饼图 (QPainter)"""
    def __init__(self, title=""):
        super().__init__()
        self.title = title
        self.labels = []
        self.values = []
        self.setMinimumHeight(200)

    def set_data(self, labels, values):
        self.labels = labels
        self.values = values
        self.update()

    def paintEvent(self, event):
        if not self.labels:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        size = min(w - 160, h - 40)
        if size < 40:
            p.end()
            return

        total = sum(self.values) if self.values else 1
        cx, cy = 10 + size // 2, 20 + size // 2
        r = size // 2 - 4

        # 标题
        if self.title:
            p.setFont(QFont("Arial", 11, QFont.Bold))
            p.setPen(QColor("#333"))
            p.drawText(QRect(10, 2, w - 20, 20), Qt.AlignLeft, self.title)

        start_angle = 90 * 16  # 从12点方向起
        legend_x = cx + r + 20
        legend_y = cy - r

        for i, (label, val) in enumerate(zip(self.labels, self.values)):
            span = int(val / total * 360 * 16) if total else 0
            color = CLR_CHART_COLORS[i % len(CLR_CHART_COLORS)]

            p.setBrush(QBrush(color))
            p.setPen(QPen(Qt.white, 2))
            p.drawPie(QRect(cx - r, cy - r, 2 * r, 2 * r), start_angle, span)

            # 图例
            ly = legend_y + i * 22
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawRect(legend_x, ly, 14, 14)

            p.setFont(QFont("Arial", 9))
            p.setPen(QColor("#333"))
            pct = val / total * 100
            p.drawText(QRect(legend_x + 20, ly, 120, 14),
                       Qt.AlignLeft, f"{label} ({pct:.1f}%)")

            start_angle += span

        p.end()


class StatisticsWidget(QWidget):
    """统计面板 — 卡片 + 图表 + 明细表"""
    def __init__(self, db: AppDb):
        super().__init__()
        self.db = db
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── 筛选栏 ──
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("统计范围:"))
        self._cmb_range = QComboBox()
        self._cmb_range.addItems(["全部", "最近7天", "最近30天", "今天", "自定义"])
        self._cmb_range.currentTextChanged.connect(self._on_range_changed)
        filter_bar.addWidget(self._cmb_range)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-7))
        self._date_from.setVisible(False)
        filter_bar.addWidget(self._date_from)

        filter_bar.addWidget(QLabel("至"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setVisible(False)
        filter_bar.addWidget(self._date_to)

        self._btn_refresh = QPushButton("🔄 刷新")
        self._btn_refresh.clicked.connect(self._refresh)
        filter_bar.addWidget(self._btn_refresh)

        self._btn_clear = QPushButton("🗑 清除历史")
        self._btn_clear.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; "
            "padding: 4px 12px; border-radius: 4px; }"
        )
        self._btn_clear.clicked.connect(self._do_clear_history)
        filter_bar.addWidget(self._btn_clear)

        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        # ── 摘要卡片 ──
        card_grid = QGridLayout()
        self._card_total = SummaryCard("总打印次数", 0, CLR_PRIMARY)
        card_grid.addWidget(self._card_total, 0, 0)

        self._card_success = SummaryCard("成功次数", 0, CLR_SUCCESS)
        card_grid.addWidget(self._card_success, 0, 1)

        self._card_fail = SummaryCard("失败次数", 0, CLR_FAIL)
        card_grid.addWidget(self._card_fail, 0, 2)

        self._card_rate = SummaryCard("成功率", "0%", CLR_ORANGE)
        card_grid.addWidget(self._card_rate, 0, 3)

        self._card_today = SummaryCard("今日打印", 0, CLR_CYAN)
        card_grid.addWidget(self._card_today, 0, 4)
        layout.addLayout(card_grid)

        # ── 图表 ──
        chart_row = QHBoxLayout()

        self._daily_chart = BarChartWidget("每日打印趋势")
        self._daily_chart.setMinimumHeight(200)
        chart_row.addWidget(self._daily_chart, 2)

        self._result_chart = PieChartWidget("成功率分布")
        self._result_chart.setMinimumHeight(200)
        chart_row.addWidget(self._result_chart, 1)

        layout.addLayout(chart_row)

        # ── 模板使用排行 ──
        gb = QGroupBox("模板使用排行")
        gb_layout = QVBoxLayout(gb)
        self._tbl_rank = QTableWidget(0, 4)
        self._tbl_rank.setHorizontalHeaderLabels(["排名", "模板文件", "打印次数", "成功率"])
        self._tbl_rank.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_rank.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl_rank.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tbl_rank.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tbl_rank.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl_rank.setSelectionBehavior(QTableWidget.SelectRows)
        gb_layout.addWidget(self._tbl_rank)
        layout.addWidget(gb, stretch=1)

    def _on_range_changed(self, rng):
        is_custom = (rng == "自定义")
        self._date_from.setVisible(is_custom)
        self._date_to.setVisible(is_custom)
        if not is_custom:
            self._refresh()

    def _get_date_filter(self):
        rng = self._cmb_range.currentText()
        now = datetime.now()
        if rng == "全部":
            return None, None
        if rng == "今天":
            today = now.strftime("%Y-%m-%d")
            return today, today + " 23:59:59"
        if rng == "最近7天":
            d = (now - timedelta(days=7)).strftime("%Y-%m-%d")
            return d, now.strftime("%Y-%m-%d") + " 23:59:59"
        if rng == "最近30天":
            d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            return d, now.strftime("%Y-%m-%d") + " 23:59:59"
        if rng == "自定义":
            d1 = self._date_from.date().toString("yyyy-MM-dd")
            d2 = self._date_to.date().toString("yyyy-MM-dd")
            return d1, d2 + " 23:59:59"
        return None, None

    def _do_clear_history(self):
        """清空打印历史以便重新统计"""
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认清除",
            "确定清空所有打印历史记录?\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        conn = sqlite3.connect(self.db._db_path)
        conn.execute("DELETE FROM PrintHistory")
        conn.commit()
        conn.close()
        self._refresh()

    def _refresh(self):
        frm, to = self._get_date_filter()
        items = self.db.search_history(from_printed_at=frm, to_printed_at=to, limit=9999)

        total = len(items)
        success = sum(1 for i in items if i.result == "Success")
        fail = sum(1 for i in items if i.result == "Fail")
        rate = (success / total * 100) if total else 0

        self._card_total.set_value(total)
        self._card_success.set_value(success)
        self._card_fail.set_value(fail)
        self._card_rate.set_value(f"{rate:.1f}%")

        # 今日统计
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for i in items if i.printed_at and i.printed_at.startswith(today_str))
        self._card_today.set_value(today_count)

        # 每日趋势
        daily = Counter()
        for i in items:
            if i.printed_at and len(i.printed_at) >= 10:
                daily[i.printed_at[:10]] += 1
        if daily:
            dates = sorted(daily.keys())[-14:]  # 最近14天
            vals = [daily[d] for d in dates]
            self._daily_chart.set_data(dates, vals)

        # 成功率
        if total:
            self._result_chart.set_data(
                ["成功", "失败"],
                [success, fail]
            )

        # 模板排行
        tmpl_stats = defaultdict(lambda: {"total": 0, "success": 0})
        for i in items:
            key = i.template_path or "未知"
            tmpl_stats[key]["total"] += 1
            if i.result == "Success":
                tmpl_stats[key]["success"] += 1

        ranked = sorted(tmpl_stats.items(), key=lambda x: -x[1]["total"])
        self._tbl_rank.setRowCount(0)
        for rank, (tmpl, st) in enumerate(ranked, 1):
            row = self._tbl_rank.rowCount()
            self._tbl_rank.insertRow(row)
            self._tbl_rank.setItem(row, 0, QTableWidgetItem(str(rank)))
            self._tbl_rank.setItem(row, 1, QTableWidgetItem(tmpl))
            self._tbl_rank.setItem(row, 2, QTableWidgetItem(str(st["total"])))
            r = (st["success"] / st["total"] * 100) if st["total"] else 0
            self._tbl_rank.setItem(row, 3, QTableWidgetItem(f"{r:.1f}%"))
