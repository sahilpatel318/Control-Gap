"""Local SQLite persistence. Single-user PoC — no auth, one database file.

Stores each analysis run and its gap-register rows. Reviewer actions
(Accept / Edit / Reject) update the stored row so the human-reviewed state
survives restarts and is what exports read from.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from .models import GapRow

DB_PATH = Path(__file__).resolve().parent.parent / "controlgap.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                standard_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                assessor TEXT,
                embedder_backend TEXT,
                is_stub INTEGER,
                is_fallback_embedder INTEGER,
                top_k INTEGER,
                meta_json TEXT
            );
            CREATE TABLE IF NOT EXISTS gap_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                requirement_id TEXT NOT NULL,
                review_status TEXT NOT NULL,
                updated_at REAL NOT NULL,
                row_json TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            """
        )


def save_run(run_id: str, standard_id: str, info: dict, top_k: int, rows: List[GapRow]) -> None:
    now = time.time()
    with _conn() as conn:
        conn.execute("DELETE FROM gap_rows WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        conn.execute(
            "INSERT INTO runs (run_id, standard_id, created_at, assessor, embedder_backend, "
            "is_stub, is_fallback_embedder, top_k, meta_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id, standard_id, now,
                info["assessor"]["assessor"], info["embedder"]["backend"],
                1 if info["assessor"]["is_stub"] else 0,
                1 if info["embedder"]["is_fallback"] else 0,
                top_k, json.dumps(info),
            ),
        )
        for row in rows:
            conn.execute(
                "INSERT INTO gap_rows (run_id, requirement_id, review_status, updated_at, row_json) "
                "VALUES (?,?,?,?,?)",
                (run_id, row.requirement_id, row.review_status.value, now, row.model_dump_json()),
            )


def latest_run_id(standard_id: Optional[str] = None) -> Optional[str]:
    with _conn() as conn:
        if standard_id:
            r = conn.execute(
                "SELECT run_id FROM runs WHERE standard_id=? ORDER BY created_at DESC LIMIT 1",
                (standard_id,),
            ).fetchone()
        else:
            r = conn.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
        return r["run_id"] if r else None


def get_run(run_id: str) -> Optional[dict]:
    with _conn() as conn:
        r = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None


def get_rows(run_id: str) -> List[GapRow]:
    with _conn() as conn:
        rs = conn.execute(
            "SELECT row_json FROM gap_rows WHERE run_id=? ORDER BY id ASC", (run_id,)
        ).fetchall()
        return [GapRow.model_validate_json(r["row_json"]) for r in rs]


def get_row(run_id: str, requirement_id: str) -> Optional[GapRow]:
    with _conn() as conn:
        r = conn.execute(
            "SELECT row_json FROM gap_rows WHERE run_id=? AND requirement_id=?",
            (run_id, requirement_id),
        ).fetchone()
        return GapRow.model_validate_json(r["row_json"]) if r else None


def update_row(run_id: str, row: GapRow) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE gap_rows SET review_status=?, updated_at=?, row_json=? "
            "WHERE run_id=? AND requirement_id=?",
            (row.review_status.value, time.time(), row.model_dump_json(),
             run_id, row.requirement_id),
        )
