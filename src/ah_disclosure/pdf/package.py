from __future__ import annotations

import uuid
from contextlib import ExitStack
from pathlib import Path

from ah_disclosure.core.errors import OptionalDependencyError
from ah_disclosure.core.file_utils import replace_file_with_retry


def merge_pdf_parts(part_paths: list[str | Path], output_path: str | Path) -> Path:
    """Merge ordered PDF parts into one file without rendering or OCR."""
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception as exc:  # pragma: no cover - depends on optional PDF extras
        raise OptionalDependencyError(
            "pypdf is required to merge sectional listing documents. "
            "Install ah-disclosure-kit[pdf]."
        ) from exc

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    writer = PdfWriter()
    try:
        with ExitStack() as stack:
            for part_path in part_paths:
                stream = stack.enter_context(Path(part_path).open("rb"))
                reader = PdfReader(stream)
                for page in reader.pages:
                    writer.add_page(page)
            with temporary.open("wb") as handle:
                writer.write(handle)
        replace_file_with_retry(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target
