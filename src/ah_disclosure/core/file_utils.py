from __future__ import annotations

import os
import time
from pathlib import Path


def normalized_path_key(path: str | Path) -> str:
    """Normalize path identity without collapsing case-distinct POSIX files."""
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def replace_file_with_retry(
    source: str | Path,
    target: str | Path,
    *,
    attempts: int = 6,
    delay_seconds: float = 0.05,
) -> Path:
    """Atomically replace a file, tolerating short-lived Windows file locks."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    source_path = Path(source)
    target_path = Path(target)
    for attempt in range(attempts):
        try:
            return source_path.replace(target_path)
        except PermissionError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(delay_seconds * (2**attempt))
    raise AssertionError("unreachable")
