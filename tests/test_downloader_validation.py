import pytest

from ah_disclosure.pdf import downloader


class FakeResponse:
    headers = {"content-type": "text/html"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"<html>not a pdf</html>"


class FakePdfResponse:
    headers = {"content-type": "application/pdf"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"%PDF-1.7\n"
        yield b"%%EOF\n"


def test_pdf_download_rejects_html(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader.requests, "get", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(ValueError, match="not a PDF"):
        downloader.download_file("https://example.com/report.pdf", tmp_path, filename="report.pdf")

    assert not (tmp_path / "report.pdf").exists()


def test_existing_bad_pdf_cache_is_replaced(monkeypatch, tmp_path):
    target = tmp_path / "report.pdf"
    target.write_text("<html>not a pdf</html>", encoding="utf-8")
    monkeypatch.setattr(downloader.requests, "get", lambda *args, **kwargs: FakePdfResponse())

    result = downloader.download_file("https://example.com/report.pdf", tmp_path, filename="report.pdf")

    assert result["existed"] is False
    assert result["cached_invalid"] is True
    assert target.read_bytes().startswith(b"%PDF")
