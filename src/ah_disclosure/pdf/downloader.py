from __future__ import annotations

import hashlib
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

import requests

from ah_disclosure.core.file_utils import normalized_path_key, replace_file_with_retry
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.storage.sqlite_store import SQLiteStore

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
DOWNLOAD_CONNECT_TIMEOUT_SECONDS = 10
DOWNLOAD_MAX_ATTEMPTS = 2
RETRYABLE_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_DOWNLOAD_LOCKS: dict[str, tuple[threading.Lock, int]] = {}
_DOWNLOAD_LOCKS_GUARD = threading.Lock()


@contextmanager
def _download_target_lock(path: Path) -> Iterator[None]:
    key = normalized_path_key(path)
    with _DOWNLOAD_LOCKS_GUARD:
        lock, users = _DOWNLOAD_LOCKS.get(key, (threading.Lock(), 0))
        _DOWNLOAD_LOCKS[key] = (lock, users + 1)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _DOWNLOAD_LOCKS_GUARD:
            current_lock, current_users = _DOWNLOAD_LOCKS.get(key, (lock, 1))
            if current_lock is lock and current_users <= 1:
                _DOWNLOAD_LOCKS.pop(key, None)
            elif current_lock is lock:
                _DOWNLOAD_LOCKS[key] = (lock, current_users - 1)


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    retry_after = str(getattr(response, "headers", {}).get("retry-after", "")).strip()
    try:
        return min(max(float(retry_after), 0.0), 30.0) if retry_after else 0.5 * (2**attempt)
    except ValueError:
        return 0.5 * (2**attempt)


def safe_filename(name: str, fallback: str = "download.pdf") -> str:
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", str(name)).strip(" ._")
    text = re.sub(r"\s+", "_", text)
    text = text or fallback
    if len(text) <= 180:
        return text
    suffix = Path(text).suffix
    if suffix and len(suffix) < 32:
        return f"{text[: 180 - len(suffix)]}{suffix}"
    return text[:180]


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


def file_hashes(path: str | Path) -> tuple[str, str]:
    """Calculate MD5 and SHA256 in one file read."""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


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
    with _download_target_lock(path):
        return _download_file_locked(url, path, overwrite=overwrite, timeout=timeout)


def _download_file_locked(
    url: str,
    path: Path,
    *,
    overwrite: bool,
    timeout: int,
) -> dict:
    source_collision = False
    if path.exists() and not overwrite:
        try:
            previous = SQLiteStore().get_latest_download_for_path(str(path))
        except Exception:
            previous = {}
        previous_url = str(previous.get("url") or "")
        with path.open("rb") as handle:
            existing_head = handle.read(1024)
        visibly_invalid_pdf = _pdf_target(url, path) and not _looks_like_pdf(existing_head)
        if previous_url != url and not (not previous_url and visibly_invalid_pdf):
            source_suffix = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
            candidate = path.with_name(f"{path.stem}_{source_suffix}{path.suffix}")
            collision_index = 2
            while candidate.exists():
                try:
                    candidate_log = SQLiteStore().get_latest_download_for_path(str(candidate))
                except Exception:
                    candidate_log = {}
                if str(candidate_log.get("url") or "") == url:
                    break
                candidate = path.with_name(
                    f"{path.stem}_{source_suffix}_{collision_index}{path.suffix}"
                )
                collision_index += 1
            path = candidate
            source_collision = True
    existed = path.exists() and not overwrite
    cached_invalid = False
    if existed:
        with path.open("rb") as handle:
            cached_head = handle.read(1024)
        if _pdf_target(url, path) and not _looks_like_pdf(cached_head):
            existed = False
            cached_invalid = True
        else:
            md5, sha256 = file_hashes(path)
            result = {
                "url": url,
                "path": str(path),
                "filename": path.name,
                "bytes_written": path.stat().st_size,
                "md5": md5,
                "sha256": sha256,
                "existed": True,
                "source_collision": source_collision,
            }
            try:
                SQLiteStore().log_download(url, str(path), "cached", now_iso())
            except Exception:
                pass
            return result
    if not existed:
        last_error: Exception | None = None
        request_timeout = (min(DOWNLOAD_CONNECT_TIMEOUT_SECONDS, timeout), timeout)
        for attempt in range(DOWNLOAD_MAX_ATTEMPTS):
            tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
            response = None
            try:
                response = requests.get(
                    url,
                    headers=HEADERS,
                    stream=True,
                    timeout=request_timeout,
                )
                status_code = int(getattr(response, "status_code", 200) or 200)
                if status_code in RETRYABLE_HTTP_STATUS_CODES:
                    response.close()
                    raise requests.HTTPError(
                        f"Retryable HTTP status {status_code} for {url}",
                        response=response,
                    )
                total = 0
                md5_digest = hashlib.md5()
                sha256_digest = hashlib.sha256()
                with response as resp:
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")
                    final_url = str(getattr(resp, "url", None) or url)
                    redirect_chain = [str(item.url) for item in getattr(resp, "history", [])]
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
                            md5_digest.update(first_chunk)
                            sha256_digest.update(first_chunk)
                            total += len(first_chunk)
                        for chunk in chunks:
                            if chunk:
                                handle.write(chunk)
                                md5_digest.update(chunk)
                                sha256_digest.update(chunk)
                                total += len(chunk)
                if cached_invalid and path.exists():
                    path.unlink()
                replace_file_with_retry(tmp, path)
                md5 = md5_digest.hexdigest()
                sha256 = sha256_digest.hexdigest()
                break
            except (requests.RequestException, OSError) as exc:
                tmp.unlink(missing_ok=True)
                last_error = exc
                if attempt < DOWNLOAD_MAX_ATTEMPTS - 1:
                    time.sleep(_retry_delay(response, attempt))
                    continue
                raise
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
        else:
            raise last_error or RuntimeError(f"Download failed: {url}")
        result = {
            "url": url,
            "path": str(path),
            "filename": path.name,
            "bytes_written": total,
            "md5": md5,
            "sha256": sha256,
            "existed": False,
            "content_type": content_type,
            "final_url": final_url,
            "redirect_chain": redirect_chain,
            "cached_invalid": cached_invalid,
            "source_collision": source_collision,
        }
    try:
        SQLiteStore().log_download(url, str(path), "ok_after_invalid_cache" if cached_invalid else "ok", now_iso())
    except Exception:
        pass
    return result
