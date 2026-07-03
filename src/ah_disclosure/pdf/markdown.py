from __future__ import annotations

from pathlib import Path

from ah_disclosure.models import PdfPage


def pdf_to_markdown(pdf_path: str | Path, pages: list[PdfPage], title: str | None = None) -> str:
    try:
        import pymupdf4llm

        markdown = pymupdf4llm.to_markdown(str(pdf_path))
        header = f"# {title}\n\n" if title else ""
        return header + markdown
    except Exception:
        header = f"# {title or Path(pdf_path).name}\n\n"
        body = []
        for page in pages:
            body.append(f"\n\n<!-- page: {page.page_no} -->\n\n{page.text}")
        return header + "".join(body).strip() + "\n"
