from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ah_disclosure.core.file_utils import replace_file_with_retry
from ah_disclosure.pdf.downloader import file_sha256
from ah_disclosure.storage.sqlite_store import SQLiteStore


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def discard_staged_candidate(downloaded: dict[str, Any], staging_root: Path) -> bool:
    path = Path(str(downloaded.get("path") or ""))
    if not path.is_file() or not is_within(path, staging_root):
        return False
    path.unlink()
    return True


def move_staged_candidate(
    downloaded: dict[str, Any],
    destination_dir: Path,
    filename: str,
    url: str,
    staging_root: Path,
) -> dict[str, Any]:
    source = Path(str(downloaded.get("path") or "")).resolve()
    if not source.is_file() or not is_within(source, staging_root):
        return downloaded
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / filename
    source_hash = str(downloaded.get("sha256") or file_sha256(source))
    reused_existing = False
    destination_hash = file_sha256(destination) if destination.exists() else None
    if destination_hash is not None and destination_hash != source_hash:
        suffix = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        destination = destination.with_name(f"{destination.stem}_{suffix}{destination.suffix}")
        destination_hash = file_sha256(destination) if destination.exists() else None
    if destination_hash == source_hash:
        source.unlink()
        reused_existing = True
    else:
        replace_file_with_retry(source, destination)
    result = {
        **downloaded,
        "path": str(destination),
        "filename": destination.name,
        "sha256": source_hash,
        "promoted_from_staging": True,
        "reused_existing": reused_existing,
    }
    SQLiteStore().log_download(
        url,
        str(destination),
        "promoted_cached" if reused_existing else "promoted",
    )
    return result
