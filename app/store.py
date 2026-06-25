"""Tiny SQLite persistence for generated reports.

One table. Each report is stored as its JSON payload plus a couple of queryable columns,
so the demo can list past runs and re-open a report without re-calling the model.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .schemas import OnboardingReport, StoredReport

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _db_path() -> Path:
    raw = os.environ.get("FRICTION_RADAR_DB", "friction_radar.db")
    p = Path(raw)
    return p if p.is_absolute() else _REPO_ROOT / p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT    NOT NULL,
                product    TEXT    NOT NULL,
                payload    TEXT    NOT NULL
            )
            """
        )


def save_report(report: OnboardingReport) -> StoredReport:
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = report.model_dump_json()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO reports (created_at, product, payload) VALUES (?, ?, ?)",
            (created_at, report.product, payload),
        )
        report_id = cur.lastrowid
    return StoredReport(
        id=report_id, created_at=created_at, product=report.product, report=report
    )


def list_reports() -> List[StoredReport]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, product, payload FROM reports ORDER BY id DESC"
        ).fetchall()
    return [
        StoredReport(
            id=row["id"],
            created_at=row["created_at"],
            product=row["product"],
            report=OnboardingReport.model_validate_json(row["payload"]),
        )
        for row in rows
    ]


def get_report(report_id: int) -> StoredReport | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, created_at, product, payload FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    if row is None:
        return None
    return StoredReport(
        id=row["id"],
        created_at=row["created_at"],
        product=row["product"],
        report=OnboardingReport.model_validate_json(row["payload"]),
    )
