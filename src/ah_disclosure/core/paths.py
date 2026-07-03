from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

from .config import get_settings


@dataclass(slots=True)
class DataPaths:
    root: Path
    raw: Path
    raw_cninfo: Path
    raw_hkex: Path
    raw_eastmoney: Path
    raw_manual: Path
    staging: Path
    staging_downloads: Path
    staging_extraction: Path
    staging_ocr: Path
    parsed: Path
    normalized: Path
    index: Path
    cache: Path
    cache_akshare: Path
    cache_cninfo: Path
    cache_hkex: Path
    cache_resolver: Path
    logs: Path
    manifests: Path

    @property
    def sqlite_path(self) -> Path:
        return self.index / "ah_disclosure.sqlite"

    def parsed_document_dir(self, document_id: str) -> Path:
        path = self.parsed / document_id
        (path / "tables").mkdir(parents=True, exist_ok=True)
        (path / "images").mkdir(parents=True, exist_ok=True)
        (path / "ocr").mkdir(parents=True, exist_ok=True)
        return path


def get_data_dir() -> Path:
    path = get_settings().data_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_paths() -> DataPaths:
    root = get_data_dir()
    paths = DataPaths(
        root=root,
        raw=root / "raw",
        raw_cninfo=root / "raw" / "cninfo",
        raw_hkex=root / "raw" / "hkex",
        raw_eastmoney=root / "raw" / "eastmoney",
        raw_manual=root / "raw" / "manual",
        staging=root / "staging",
        staging_downloads=root / "staging" / "downloads",
        staging_extraction=root / "staging" / "extraction",
        staging_ocr=root / "staging" / "ocr",
        parsed=root / "parsed",
        normalized=root / "normalized",
        index=root / "index",
        cache=root / "cache",
        cache_akshare=root / "cache" / "akshare",
        cache_cninfo=root / "cache" / "cninfo",
        cache_hkex=root / "cache" / "hkex",
        cache_resolver=root / "cache" / "resolver",
        logs=root / "logs",
        manifests=root / "manifests",
    )
    for f in fields(paths):
        value = getattr(paths, f.name)
        if isinstance(value, Path):
            value.mkdir(parents=True, exist_ok=True)
    return paths


def get_index_path() -> Path:
    return get_data_paths().sqlite_path


def sqlite_path() -> Path:
    return get_index_path()


def get_parsed_dir(document_id: str) -> Path:
    return get_data_paths().parsed_document_dir(document_id)

# Backward-compatible alias used by earlier drafts.
def get_path_manager() -> DataPaths:
    return get_data_paths()
