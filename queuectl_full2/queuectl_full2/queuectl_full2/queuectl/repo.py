
from __future__ import annotations
import sqlite3
from typing import Optional, List, Dict, Any
from datetime import timedelta
from .utils import utc_now, to_iso, parse_iso, clamp_text
from .config import get_int
from .db import dict_from_row

def enqueue(conn: sqlite3.Connection, job: Dict[str, Any]) -> None:
    now = utc_now()
    job.setdefault("state", "pending")
    job.setdefault("attempts", 0)
    job.setdefault("max_retries", 3)
    job.setdefault("created_at", to_iso(now))
    job.setdefault("updated_at", to_iso(now))
    job.setdefault("run_at", to_iso(now))
    job.setdefault("priority", 0)
    with conn:
        conn.execute("""
            INSERT INTO jobs(id, command, state, attempts, max_retries, created_at, updated_at, run_at, priority, worker_id, locked_until, last_error)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            job["id"], job["command"], job["state"], job["attempts"], job["max_retries"],
            job["created_at"], job["updated_at"], job["run_at"], job["priority"],
            job.get("worker_id"), job.get("locked_until"), job.get("last_error")
        ))

def acquire_next_job(conn: sqlite3.Connection, worker_id: str) -> Optional[Dict[str, Any]]:
    now = utc_now()
    lease_seconds = get_int(conn, "lease_seconds")
    locked_until = to_iso(now + timedelta(seconds=lease_seconds))
    with conn:
        row = conn.execute("""
            SELECT id FROM jobs
            WHERE state IN ('pending','failed')
              AND run_at <= ?
              AND (locked_until IS NULL OR locked_until <= ?)
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """, (to_iso(now), to_iso(now))).fetchone()
        if not row:
            return None
        job_id = row["id"]
        conn.execute("""
            UPDATE jobs
               SET state='processing', worker_id=?, locked_until=?, updated_at=?
             WHERE id=?
        """, (worker_id, locked_until, to_iso(now), job_id))
    return get_job(conn, job_id)

def get_job(conn: sqlite3.Connection, job_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict_from_row(row) if row else None

def complete_job(conn: sqlite3.Connection, job_id: str) -> None:
    now = utc_now()
    with conn:
        conn.execute("""
            UPDATE jobs SET state='completed', worker_id=NULL, locked_until=NULL, updated_at=? WHERE id=?
        """, (to_iso(now), job_id))

def log_execution(conn: sqlite3.Connection, job_id: str, exit_code: int, stdout: str, stderr: str) -> None:
    from .utils import utc_now, to_iso
    with conn:
        conn.execute("""
            INSERT INTO job_logs(job_id, created_at, exit_code, stdout, stderr)
            VALUES(?,?,?,?,?)
        """, (job_id, to_iso(utc_now()), exit_code, clamp_text(stdout, 65535), clamp_text(stderr, 65535)))

def fail_job(conn: sqlite3.Connection, job: Dict[str, Any], last_error: str) -> None:
    now = utc_now()
    attempts = int(job["attempts"]) + 1
    max_retries = int(job["max_retries"])
    base = get_int(conn, "backoff_base")
    if attempts > max_retries:
        state = "dead"
        run_at = job["run_at"]
    else:
        delay = base ** attempts
        from datetime import timedelta
        run_at = to_iso(now + timedelta(seconds=delay))
        state = "failed"
    with conn:
        conn.execute("""
            UPDATE jobs
               SET attempts=?, state=?, run_at=?, worker_id=NULL, locked_until=NULL, updated_at=?, last_error=?
             WHERE id=?
        """, (attempts, state, run_at, to_iso(now), last_error, job["id"]))

def list_jobs(conn: sqlite3.Connection, state: Optional[str]=None, limit: int=100) -> List[Dict[str, Any]]:
    if state:
        rows = conn.execute("SELECT * FROM jobs WHERE state=? ORDER BY created_at ASC LIMIT ?", (state, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at ASC LIMIT ?", (limit,)).fetchall()
    return [dict_from_row(r) for r in rows]

def status(conn: sqlite3.Connection) -> Dict[str, Any]:
    counts = {}
    for st in ["pending","processing","completed","failed","dead"]:
        counts[st] = conn.execute("SELECT COUNT(*) AS c FROM jobs WHERE state=?", (st,)).fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]
    from .utils import to_iso, utc_now
    now_iso = to_iso(utc_now())
    active_workers = conn.execute("""
        SELECT COUNT(DISTINCT worker_id) AS c FROM jobs
        WHERE worker_id IS NOT NULL AND locked_until > ?
    """, (now_iso,)).fetchone()["c"]
    return {"total": total, "states": counts, "active_workers": active_workers}

def dlq_list(conn: sqlite3.Connection):
    rows = conn.execute("SELECT * FROM jobs WHERE state='dead' ORDER BY updated_at DESC").fetchall()
    return [dict_from_row(r) for r in rows]

def dlq_retry(conn: sqlite3.Connection, job_id: str) -> bool:
    from .utils import utc_now, to_iso
    now = to_iso(utc_now())
    with conn:
        cur = conn.execute("""
            UPDATE jobs
               SET state='pending', attempts=0, run_at=?, updated_at=?, last_error=NULL
             WHERE id=? AND state='dead'
        """, (now, now, job_id))
        return cur.rowcount > 0

def get_logs(conn: sqlite3.Connection, job_id: str, limit: int=10):
    rows = conn.execute("SELECT * FROM job_logs WHERE job_id=? ORDER BY id DESC LIMIT ?", (job_id, limit)).fetchall()
    return [dict_from_row(r) for r in rows]
