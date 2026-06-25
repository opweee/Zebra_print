# -*- coding: utf-8 -*-
"""数据库模块 — SQLite 操作，完全对应 C# AppDb.cs"""

import sqlite3
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TemplateMapping:
    model: str
    template_path: str
    preferred_printer: Optional[str] = None
    parameters_json: Optional[str] = None
    updated_at: str = ""

    def get_parameters(self) -> dict:
        import json
        if self.parameters_json:
            try:
                return json.loads(self.parameters_json)
            except json.JSONDecodeError:
                pass
        return {}


@dataclass
class PrintHistoryItem:
    printed_at: str = ""
    model: Optional[str] = None
    template_path: str = ""
    printer_name: str = ""
    copies: int = 1
    parameters_json: Optional[str] = None
    mode: str = "Unknown"        # ZPL / Image / AutoTrigger
    result: str = "Success"      # Success / Fail / Matched / Ignored / Skipped
    error_message: Optional[str] = None


class AppDb:
    """SQLite 数据库操作，完全对应 C# AppDb"""

    def __init__(self, db_path="data/print.db"):
        self._db_path = db_path

    def initialize(self):
        dir_name = os.path.dirname(self._db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS TemplateMappings (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Model TEXT NOT NULL UNIQUE,
                    TemplatePath TEXT NOT NULL,
                    PreferredPrinter TEXT,
                    ParametersJson TEXT,
                    UpdatedAt TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS PrintHistory (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    PrintedAt TEXT NOT NULL,
                    Model TEXT,
                    TemplatePath TEXT NOT NULL,
                    PrinterName TEXT NOT NULL,
                    Copies INTEGER NOT NULL,
                    ParametersJson TEXT,
                    Mode TEXT NOT NULL,
                    Result TEXT NOT NULL,
                    ErrorMessage TEXT
                );

                CREATE TABLE IF NOT EXISTS SequenceStates (
                    ScopeKey TEXT NOT NULL,
                    SequenceKey TEXT NOT NULL,
                    CurrentIndex INTEGER NOT NULL DEFAULT 0,
                    UpdatedAt TEXT NOT NULL,
                    PRIMARY KEY (ScopeKey, SequenceKey)
                );

                CREATE TABLE IF NOT EXISTS AppSettings (
                    SettingKey TEXT PRIMARY KEY,
                    SettingValue TEXT,
                    UpdatedAt TEXT NOT NULL
                );
            """)

    # ── TemplateMappings ──

    def get_mappings(self):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT Model, TemplatePath, PreferredPrinter, ParametersJson, UpdatedAt "
                "FROM TemplateMappings ORDER BY Model"
            ).fetchall()

        return [
            TemplateMapping(
                model=r[0], template_path=r[1], preferred_printer=r[2],
                parameters_json=r[3], updated_at=r[4]
            )
            for r in rows
        ]

    def upsert_mapping(self, model, template_path, preferred_printer=None, parameters_json=None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO TemplateMappings(Model, TemplatePath, PreferredPrinter, ParametersJson, UpdatedAt)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(Model) DO UPDATE SET
                       TemplatePath = excluded.TemplatePath,
                       PreferredPrinter = excluded.PreferredPrinter,
                       ParametersJson = excluded.ParametersJson,
                       UpdatedAt = excluded.UpdatedAt""",
                (model, template_path, preferred_printer, parameters_json, now)
            )

    def replace_mappings(self, mappings):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute("DELETE FROM TemplateMappings")
            conn.executemany(
                "INSERT INTO TemplateMappings(Model, TemplatePath, PreferredPrinter, ParametersJson, UpdatedAt) "
                "VALUES (?, ?, ?, ?, ?)",
                [(m.model, m.template_path, m.preferred_printer, m.parameters_json, now) for m in mappings]
            )

    # ── PrintHistory ──

    def insert_print_history(self, item: PrintHistoryItem):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO PrintHistory(PrintedAt, Model, TemplatePath, PrinterName, Copies,
                   ParametersJson, Mode, Result, ErrorMessage)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item.printed_at, item.model, item.template_path, item.printer_name,
                 item.copies, item.parameters_json, item.mode, item.result, item.error_message)
            )

    def get_history(self, limit=300):
        return self.search_history(limit=limit)

    def search_history(self, keyword=None, mode=None, result=None,
                       from_printed_at=None, to_printed_at=None, limit=300):
        where = []
        params = []

        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            where.append(
                "(IFNULL(PrintedAt,'') LIKE ? OR IFNULL(Model,'') LIKE ? OR "
                "IFNULL(TemplatePath,'') LIKE ? OR IFNULL(PrinterName,'') LIKE ? OR "
                "IFNULL(ParametersJson,'') LIKE ? OR IFNULL(Mode,'') LIKE ? OR "
                "IFNULL(Result,'') LIKE ? OR IFNULL(ErrorMessage,'') LIKE ?)"
            )
            params.extend([kw] * 8)

        if mode and mode.strip():
            where.append("Mode = ?")
            params.append(mode.strip())

        if result and result.strip():
            where.append("Result = ?")
            params.append(result.strip())

        if from_printed_at and from_printed_at.strip():
            where.append("PrintedAt >= ?")
            params.append(from_printed_at.strip())

        if to_printed_at and to_printed_at.strip():
            where.append("PrintedAt <= ?")
            params.append(to_printed_at.strip())

        sql = "SELECT PrintedAt, Model, TemplatePath, PrinterName, Copies, ParametersJson, Mode, Result, ErrorMessage FROM PrintHistory"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY Id DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            PrintHistoryItem(
                printed_at=r[0], model=r[1], template_path=r[2], printer_name=r[3],
                copies=r[4], parameters_json=r[5], mode=r[6], result=r[7], error_message=r[8]
            )
            for r in rows
        ]

    # ── SequenceStates ──

    def get_sequence_states(self, scope_key):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT SequenceKey, CurrentIndex FROM SequenceStates WHERE ScopeKey = ?",
                (scope_key,)
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def upsert_sequence_states(self, scope_key, states: dict):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            for key, val in states.items():
                conn.execute(
                    """INSERT INTO SequenceStates(ScopeKey, SequenceKey, CurrentIndex, UpdatedAt)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(ScopeKey, SequenceKey) DO UPDATE SET
                           CurrentIndex = excluded.CurrentIndex,
                           UpdatedAt = excluded.UpdatedAt""",
                    (scope_key, key, val, now)
                )

    def reset_sequence_states(self, scope_key):
        with self._conn() as conn:
            conn.execute("DELETE FROM SequenceStates WHERE ScopeKey = ?", (scope_key,))

    # ── AppSettings ──

    def get_setting(self, key):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT SettingValue FROM AppSettings WHERE SettingKey = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def set_setting(self, key, value):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO AppSettings(SettingKey, SettingValue, UpdatedAt)
                   VALUES (?, ?, ?)
                   ON CONFLICT(SettingKey) DO UPDATE SET
                       SettingValue = excluded.SettingValue,
                       UpdatedAt = excluded.UpdatedAt""",
                (key, value, now)
            )

    # ── 内部 ──

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
