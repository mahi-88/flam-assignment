
from __future__ import annotations
import uuid
from datetime import datetime, timezone, timedelta

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(ISO_FMT)

def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, ISO_FMT).replace(tzinfo=timezone.utc)

def gen_id() -> str:
    return str(uuid.uuid4())

def clamp_text(s: str, max_len: int = 65535) -> str:
    if s is None:
        return ""
    if len(s) <= max_len:
        return s
    return s[:max_len]
