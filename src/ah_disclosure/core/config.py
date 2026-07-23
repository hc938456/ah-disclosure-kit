from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    log_level: str = "INFO"
    cache_ttl_days: int = 7
    akshare_ttl_days: int = 7
    cninfo_ttl_days: int = 1
    hkex_ttl_days: int = 1
    historical_filing_ttl_days: int = 30
    resolver_ttl_days: int = 90
    default_ingest_mode: str = "auto"
    generate_markdown: bool = False
    generate_full_text: bool = False
    generate_pages_jsonl: bool = True
    extract_tables: str = "auto"
    ocr: str = "auto"
    enable_vector_index: bool = False
    layout_mode: str = "auto"
    default_context_max_chars: int = 12000
    default_context_max_pages: int = 8


def _package_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _source_checkout_root() -> Path | None:
    root = _package_root()
    if (root / "pyproject.toml").is_file() and (root / "src" / "ah_disclosure").is_dir():
        return root
    return None


def _user_data_root() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or Path.home())
        return base / "ah-disclosure"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ah-disclosure"
    base = Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "ah-disclosure"


def _project_root() -> Path:
    checkout_root = _source_checkout_root()
    if checkout_root is None:
        return _user_data_root()
    if checkout_root.parent.name.lower() == "tools":
        return checkout_root.parent.parent
    return checkout_root


def _default_data_dir() -> Path:
    if _source_checkout_root() is None:
        return _user_data_root() / "data"
    return _project_root() / "data" / "ah_disclosure"


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_config_file() -> dict[str, Any]:
    configured = (
        os.getenv("AH_DISCLOSURE_CONFIG")
        or os.getenv("AH_FILINGS_CONFIG")
        or "config.toml"
    )
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = _project_root() / path
    if not path.exists() and not Path(configured).is_absolute():
        package_path = _package_root() / configured
        if package_path.exists():
            path = package_path
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def get_settings() -> Settings:
    config = _read_config_file()
    paths = config.get("paths", {}) if isinstance(config, dict) else {}
    cache = config.get("cache", {}) if isinstance(config, dict) else {}
    pdf = config.get("pdf", {}) if isinstance(config, dict) else {}
    logging = config.get("logging", {}) if isinstance(config, dict) else {}
    llm = config.get("llm", {}) if isinstance(config, dict) else {}

    data_dir_value = (
        os.getenv("AH_DISCLOSURE_DATA_DIR")
        or os.getenv("AH_FILINGS_DATA_DIR")
        or paths.get("data_dir")
    )
    if data_dir_value:
        configured_data_dir = Path(str(data_dir_value)).expanduser()
        if not configured_data_dir.is_absolute():
            configured_data_dir = _project_root() / configured_data_dir
        data_dir = configured_data_dir.resolve()
    else:
        data_dir = _default_data_dir().resolve()

    return Settings(
        data_dir=data_dir,
        log_level=os.getenv("AH_DISCLOSURE_LOG_LEVEL") or os.getenv("AH_FILINGS_LOG_LEVEL") or logging.get("level", "INFO"),
        cache_ttl_days=int(os.getenv("AH_DISCLOSURE_CACHE_TTL_DAYS") or os.getenv("AH_FILINGS_CACHE_TTL_DAYS") or cache.get("ttl_days", 7)),
        akshare_ttl_days=int(cache.get("akshare_ttl_days", cache.get("ttl_days", 7))),
        cninfo_ttl_days=int(cache.get("cninfo_ttl_days", 1)),
        hkex_ttl_days=int(cache.get("hkex_ttl_days", 1)),
        historical_filing_ttl_days=int(cache.get("historical_filing_ttl_days", 30)),
        resolver_ttl_days=int(cache.get("resolver_ttl_days", 90)),
        default_ingest_mode=str(pdf.get("default_ingest_mode", "auto")),
        generate_markdown=_coerce_bool(pdf.get("generate_markdown", False), False),
        generate_full_text=_coerce_bool(pdf.get("generate_full_text", False), False),
        generate_pages_jsonl=_coerce_bool(pdf.get("generate_pages_jsonl", True), True),
        extract_tables=str(pdf.get("extract_tables", "auto")),
        ocr=str(pdf.get("ocr", "auto")),
        enable_vector_index=_coerce_bool(pdf.get("build_vector_index", pdf.get("enable_vector_index", False)), False),
        layout_mode=str(pdf.get("layout_mode", "auto")),
        default_context_max_chars=int(llm.get("default_context_max_chars", 12000)),
        default_context_max_pages=int(llm.get("default_context_max_pages", 8)),
    )

# Compatibility alias for generated modules.
def load_settings() -> Settings:
    return get_settings()
