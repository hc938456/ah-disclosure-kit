from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current_date_yyyymmdd() -> str:
    """Return the current local date for upstream filing query boundaries."""
    return datetime.now().astimezone().strftime("%Y%m%d")
