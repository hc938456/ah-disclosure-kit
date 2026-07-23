from __future__ import annotations

import json
from pathlib import Path

from ah_disclosure.models import PdfPage


def build_vector_index(document_id: str, pages: list[PdfPage], output_dir: str | Path) -> dict:
    # 这里只创建轻量清单，供外部向量后端按稳定契约接管；Kit 本身不声称已生成 embeddings。
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{document_id}_vector_manifest.json"
    payload = {
        "document_id": document_id,
        "engine": "manifest-only",
        "page_count": len(pages),
        "status": "created",
        "note": "This is a manifest for an external vector backend; no embeddings were generated.",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"vector_index_path": str(path), **payload}
