
from __future__ import annotations

def compute_backoff_seconds(base: int, attempts_after_increment: int) -> int:
    return int(base ** attempts_after_increment)
