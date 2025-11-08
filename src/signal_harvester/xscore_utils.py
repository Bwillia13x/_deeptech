from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

__all__ = ["parse_datetime", "urljoin"]


def parse_datetime(s: Optional[str]) -> datetime:
    """
    Parse an ISO-8601-like datetime string.
    - If None: returns now in UTC.
    - If 'YYYY-MM-DD': returns that day at 00:00:00 UTC.
    - Accepts 'Z' suffix or '+HH:MM' offsets.
    - Naive inputs are treated as UTC.
    """
    if s is None:
        return datetime.now(timezone.utc)

    s = s.strip()
    if _DATE_ONLY.match(s):
        y, m, d = map(int, s.split("-"))
        return datetime(y, m, d, tzinfo=timezone.utc)

    # Normalize 'Z' to '+00:00' for fromisoformat
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def urljoin(base: str, path: str) -> str:
    """Simple URL join that handles trailing slashes properly."""
    if not base.endswith("/"):
        base += "/"
    if path.startswith("/"):
        path = path[1:]
    return base + path
