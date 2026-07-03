from __future__ import annotations

import json
from pathlib import Path

from ah_disclosure.models import PdfPage


def build_vector_index(document_id: str, pages: list[PdfPage], output_dir: str | Path) -> dict:
    # Lightweight placeholder index. If a user installs vector dependencies, this can be swapped
    # for ChromaDB / sentence-transformers without changing the service contract.
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{document_id}_vector_manifest.json"
    payload = {
        "document_id": document_id,
        "engine": "manifest-only",
        "page_count": len(pages),
        "status": "created",
        "note": "Install [vector] extras and replace vector_index.py to build embeddings.",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"vector_index_path": str(path), **payload}
