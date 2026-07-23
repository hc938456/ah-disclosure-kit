from __future__ import annotations

try:
    from importlib.metadata import version
    __version__ = version("ah-disclosure-kit")
except Exception:
    __version__ = "1.1.2"

from .models import (
    CompanyDataResult,
    CompanyIdentity,
    EvidenceItem,
    EvidencePacket,
    FilingRecord,
    PdfIngestResult,
    PdfPage,
    ProspectusRecord,
)

__all__ = [
    "__version__",
    "CompanyIdentity",
    "FilingRecord",
    "ProspectusRecord",
    "CompanyDataResult",
    "PdfPage",
    "PdfIngestResult",
    "EvidenceItem",
    "EvidencePacket",
]
