from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.storage.sqlite_store import SQLiteStore

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}


def safe_filename(name: str, fallback: str = "download.pdf") -> str:
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", str(name)).strip(" ._")
    text = re.sub(r"\s+", "_", text)
    return (text or fallback)[:180]


def infer_filename(url: str, title: str | None = None) -> str:
    if title:
        name = safe_filename(title)
        if not re.search(r"\.[A-Za-z0-9]{2,5}$", name):
            name += ".pdf"
        return name
    return safe_filename(Path(urlparse(url).path).name or "download.pdf")


def _digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_md5(path: str | Path) -> str:
    return _digest(Path(path), "md5")


def file_sha256(path: str | Path) -> str:
    return _digest(Path(path), "sha256")


def _pdf_target(url: str, path: Path) -> bool:
    return path.suffix.lower() == ".pdf" or urlparse(url).path.lower().endswith(".pdf")


def _looks_like_pdf(data: bytes | None) -> bool:
    return bool(data and data.lstrip().startswith(b"%PDF"))


def _head_preview(data: bytes | None) -> str:
    if not data:
        return ""
    return data[:80].decode("utf-8", errors="replace").replace("\r", " ").replace("\n", " ")


def download_file(
    url: str,
    output_dir: str | Path,
    filename: str | None = None,
    title: str | None = None,
    overwrite: bool = False,
    timeout: int = 60,
) -> dict:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = out / safe_filename(filename or infer_filename(url, title))
    existed = path.exists() and not overwrite
    cached_invalid = False
    if existed:
        with path.open("rb") as handle:
            cached_head = handle.read(1024)
        if _pdf_target(url, path) and not _looks_like_pdf(cached_head):
            existed = False
            cached_invalid = True
        else:
            result = {
                "url": url,
                "path": str(path),
                "filename": path.name,
                "bytes_written": path.stat().st_size,
                "md5": file_md5(path),
                "sha256": file_sha256(path),
                "existed": True,
            }
            try:
                SQLiteStore().log_download(url, str(path), "cached", now_iso())
            except Exception:
                pass
            return result
    if not existed:
        tmp = path.with_suffix(path.suffix + ".part")
        total = 0
        with requests.get(url, headers=HEADERS, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            chunks = resp.iter_content(1024 * 1024)
            first_chunk = next((chunk for chunk in chunks if chunk), b"")
            if _pdf_target(url, path) and not _looks_like_pdf(first_chunk):
                raise ValueError(
                    "Downloaded content is not a PDF "
                    f"(content_type={content_type!r}, head={_head_preview(first_chunk)!r})"
                )
            with tmp.open("wb") as handle:
                if first_chunk:
                    handle.write(first_chunk)
                    total += len(first_chunk)
                for chunk in chunks:
                    if chunk:
                        handle.write(chunk)
                        total += len(chunk)
        if cached_invalid and path.exists():
            path.unlink()
        tmp.replace(path)
        result = {
            "url": url,
            "path": str(path),
            "filename": path.name,
            "bytes_written": total,
            "md5": file_md5(path),
            "sha256": file_sha256(path),
            "existed": False,
            "content_type": content_type,
            "cached_invalid": cached_invalid,
        }
    try:
        SQLiteStore().log_download(url, str(path), "ok_after_invalid_cache" if cached_invalid else "ok", now_iso())
    except Exception:
        pass
    return result
