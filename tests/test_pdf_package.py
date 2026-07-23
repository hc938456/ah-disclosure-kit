from pypdf import PdfReader, PdfWriter

from ah_disclosure.pdf.package import merge_pdf_parts


def test_merge_pdf_parts_preserves_order(tmp_path):
    parts = []
    for index, width in enumerate((100, 200), start=1):
        path = tmp_path / f"part-{index}.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=width, height=300)
        with path.open("wb") as handle:
            writer.write(handle)
        parts.append(path)

    merged = merge_pdf_parts(parts, tmp_path / "merged.pdf")
    with merged.open("rb") as handle:
        reader = PdfReader(handle)

        assert len(reader.pages) == 2
        assert float(reader.pages[0].mediabox.width) == 100
        assert float(reader.pages[1].mediabox.width) == 200

    for path in [*parts, merged]:
        path.unlink()
    assert list(tmp_path.glob("*.part")) == []
