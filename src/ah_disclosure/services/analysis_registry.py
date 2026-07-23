from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass


_MAX_RUNS = 128
_TTL_SECONDS = 3600
_MAX_CONTEXT_BYTES = 4 * 1024 * 1024
_MAX_REGISTRY_BYTES = 16 * 1024 * 1024
_MAX_EVIDENCE_TEXT_BYTES = 256 * 1024
_LOCK = threading.RLock()
EvidenceIdentity = dict[str, dict[tuple[str, int], str]]


@dataclass(frozen=True)
class _AnalysisContext:
    created_at: float
    evidence_registry: dict[str, set[str]]
    evidence_catalog: dict[str, str]
    evidence_identity: EvidenceIdentity
    context_fingerprint: str
    byte_size: int


_RUNS: OrderedDict[str, _AnalysisContext] = OrderedDict()
_TOTAL_BYTES = 0


def _utf8_prefix(value: str, max_bytes: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= max_bytes:
        return value
    return raw[:max_bytes].decode("utf-8", errors="ignore")


def _bounded_context(
    evidence_registry: dict[str, set[str]],
    evidence_catalog: dict[str, str],
    evidence_identity: EvidenceIdentity,
) -> tuple[dict[str, set[str]], dict[str, str], EvidenceIdentity, int]:
    """Copy a context while enforcing a deterministic UTF-8 storage ceiling."""
    catalog: dict[str, str] = {}
    byte_size = 0
    for evidence_id, raw_text in evidence_catalog.items():
        key = str(evidence_id)
        key_bytes = len(key.encode("utf-8"))
        remaining = _MAX_CONTEXT_BYTES - byte_size - key_bytes
        if remaining <= 0:
            break
        text = _utf8_prefix(str(raw_text or ""), min(remaining, _MAX_EVIDENCE_TEXT_BYTES))
        catalog[key] = text
        byte_size += key_bytes + len(text.encode("utf-8"))

    retained_ids = set(catalog)
    registry = {
        str(claim_id): {str(item) for item in ids if str(item) in retained_ids}
        for claim_id, ids in evidence_registry.items()
    }
    identity = {
        str(claim_id): {
            (str(document_id), int(page_no)): str(evidence_id)
            for (document_id, page_no), evidence_id in claim_identity.items()
            if str(evidence_id) in retained_ids
        }
        for claim_id, claim_identity in evidence_identity.items()
    }
    byte_size += sum(
        len(claim_id.encode("utf-8"))
        + sum(len(evidence_id.encode("utf-8")) for evidence_id in ids)
        for claim_id, ids in registry.items()
    )
    return registry, catalog, identity, min(byte_size, _MAX_CONTEXT_BYTES)


def _remove(run_id: str) -> None:
    global _TOTAL_BYTES
    item = _RUNS.pop(run_id, None)
    if item is not None:
        _TOTAL_BYTES = max(0, _TOTAL_BYTES - item.byte_size)


def _prune(now: float, *, reserve_bytes: int = 0) -> None:
    expired = [
        run_id
        for run_id, item in _RUNS.items()
        if now - item.created_at > _TTL_SECONDS
    ]
    for run_id in expired:
        _remove(run_id)
    while _RUNS and (
        len(_RUNS) >= _MAX_RUNS
        or _TOTAL_BYTES + reserve_bytes > _MAX_REGISTRY_BYTES
    ):
        _remove(next(iter(_RUNS)))


def register_analysis_context(
    evidence_registry: dict[str, set[str]],
    evidence_catalog: dict[str, str],
    evidence_identity: EvidenceIdentity | None = None,
    *,
    context_fingerprint: str = "",
) -> str:
    global _TOTAL_BYTES
    registry, catalog, identity, byte_size = _bounded_context(
        evidence_registry,
        evidence_catalog,
        evidence_identity or {},
    )
    run_id = uuid.uuid4().hex
    with _LOCK:
        now = time.monotonic()
        _prune(now, reserve_bytes=byte_size)
        _RUNS[run_id] = _AnalysisContext(
            created_at=now,
            evidence_registry=registry,
            evidence_catalog=catalog,
            evidence_identity=identity,
            context_fingerprint=str(context_fingerprint or ""),
            byte_size=byte_size,
        )
        _TOTAL_BYTES += byte_size
    return run_id


def _get(run_id: str) -> _AnalysisContext | None:
    key = str(run_id or "").strip()
    if not key:
        return None
    with _LOCK:
        _prune(time.monotonic())
        item = _RUNS.get(key)
        if item is None:
            return None
        _RUNS.move_to_end(key)
        return item


def get_analysis_context(
    run_id: str,
) -> tuple[dict[str, set[str]], dict[str, str]] | None:
    item = _get(run_id)
    if item is None:
        return None
    return (
        {claim_id: set(ids) for claim_id, ids in item.evidence_registry.items()},
        dict(item.evidence_catalog),
    )


def get_analysis_identity(run_id: str) -> EvidenceIdentity | None:
    """Return stable document/page-to-evidence-ID bindings for a prior run."""
    item = _get(run_id)
    if item is None:
        return None
    return {
        claim_id: dict(claim_identity)
        for claim_id, claim_identity in item.evidence_identity.items()
    }


def get_analysis_fingerprint(run_id: str) -> str | None:
    item = _get(run_id)
    return item.context_fingerprint if item is not None else None
