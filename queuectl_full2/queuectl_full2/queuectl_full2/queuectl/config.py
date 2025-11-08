
from __future__ import annotations
import sqlite3

def get_config(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    if not row:
        raise KeyError(key)
    return row["value"]

def set_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute("INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

def get_int(conn: sqlite3.Connection, key: str) -> int:
    return int(get_config(conn, key))
