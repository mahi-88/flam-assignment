
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any

DEFAULT_DB_PATH = Path.cwd() / "queue.db"

def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    migrate(conn)
    return conn

def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN;")
    try:
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','processing','completed','failed','dead')),
                attempts INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                run_at TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                worker_id TEXT,
                locked_until TEXT,
                last_error TEXT
            );'''
        )
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS job_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                exit_code INTEGER,
                stdout TEXT,
                stderr TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );'''
        )
        conn.execute(
            '''CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );'''
        )
        defaults = {
            "max_retries": "3",
            "backoff_base": "2",
            "lease_seconds": "60",
            "poll_interval_ms": "500",
            "timeout_seconds": "300"
        }
        for k,v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO config(key,value) VALUES(?,?)", (k, v))
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise

def dict_from_row(row: sqlite3.Row):
    return {k: row[k] for k in row.keys()}
