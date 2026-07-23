import pytest
from concurrent.futures import ThreadPoolExecutor

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


def test_same_filename_with_different_source_url_does_not_reuse_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(downloader.requests, "get", lambda *args, **kwargs: FakePdfResponse())

    first = downloader.download_file(
        "https://example.com/announcement.pdf",
        tmp_path,
        filename="annual-report.pdf",
    )
    second = downloader.download_file(
        "https://example.com/full-report.pdf",
        tmp_path,
        filename="annual-report.pdf",
    )

    assert first["path"] != second["path"]
    assert second["source_collision"] is True
    assert second["existed"] is False


def test_untracked_existing_file_is_not_treated_as_url_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    original = tmp_path / "annual-report.pdf"
    original.write_bytes(b"%PDF-1.7\nunmanaged\n%%EOF\n")
    monkeypatch.setattr(downloader.requests, "get", lambda *args, **kwargs: FakePdfResponse())

    result = downloader.download_file(
        "https://example.com/current.pdf",
        tmp_path,
        filename="annual-report.pdf",
    )

    assert result["existed"] is False
    assert result["source_collision"] is True
    assert result["path"] != str(original)
    assert original.read_bytes() == b"%PDF-1.7\nunmanaged\n%%EOF\n"


def test_safe_filename_preserves_extension_when_truncated():
    name = f"{'a' * 220}.pdf"

    result = downloader.safe_filename(name)

    assert len(result) == 180
    assert result.endswith(".pdf")


def test_file_hashes_matches_individual_digests(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc" * 1024)

    md5, sha256 = downloader.file_hashes(path)

    assert md5 == downloader.file_md5(path)
    assert sha256 == downloader.file_sha256(path)


def test_download_uses_bounded_connect_timeout_and_attempts(monkeypatch, tmp_path):
    calls = []

    def fail(*args, **kwargs):
        calls.append(kwargs)
        raise downloader.requests.ConnectionError("offline")

    monkeypatch.setattr(downloader.requests, "get", fail)
    monkeypatch.setattr(downloader.time, "sleep", lambda seconds: None)

    with pytest.raises(downloader.requests.ConnectionError, match="offline"):
        downloader.download_file(
            "https://example.com/report.pdf",
            tmp_path,
            filename="report.pdf",
        )

    assert len(calls) == downloader.DOWNLOAD_MAX_ATTEMPTS
    assert calls[0]["timeout"] == (
        downloader.DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
        60,
    )


def test_download_retries_retryable_http_status(monkeypatch, tmp_path):
    calls = []

    class RetryableResponse(FakePdfResponse):
        status_code = 503
        headers = {"content-type": "text/plain", "retry-after": "0"}

        def close(self):
            return None

    def get(*args, **kwargs):
        calls.append(kwargs)
        return RetryableResponse() if len(calls) == 1 else FakePdfResponse()

    monkeypatch.setattr(downloader.requests, "get", get)
    monkeypatch.setattr(downloader.time, "sleep", lambda seconds: None)

    result = downloader.download_file(
        "https://example.com/report.pdf",
        tmp_path,
        filename="report.pdf",
    )

    assert len(calls) == 2
    assert result["sha256"] == downloader.file_sha256(result["path"])


def test_download_retries_stream_interruption(monkeypatch, tmp_path):
    calls = []

    class InterruptedResponse(FakePdfResponse):
        def iter_content(self, chunk_size):
            yield b"%PDF-1.7\n"
            raise downloader.requests.ConnectionError("stream interrupted")

    def get(*args, **kwargs):
        calls.append(kwargs)
        return InterruptedResponse() if len(calls) == 1 else FakePdfResponse()

    monkeypatch.setattr(downloader.requests, "get", get)
    monkeypatch.setattr(downloader.time, "sleep", lambda seconds: None)

    result = downloader.download_file(
        "https://example.com/report.pdf",
        tmp_path,
        filename="report.pdf",
    )

    assert len(calls) == 2
    assert result["bytes_written"] > 0
    assert list(tmp_path.glob("*.part")) == []


def test_concurrent_same_filename_different_urls_are_separated(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        downloader.requests,
        "get",
        lambda *args, **kwargs: FakePdfResponse(),
    )

    def download(url):
        return downloader.download_file(url, tmp_path, filename="annual-report.pdf")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(
            executor.map(
                download,
                [
                    "https://example.com/first.pdf",
                    "https://example.com/second.pdf",
                ],
            )
        )

    assert first["path"] != second["path"]
    assert {first["source_collision"], second["source_collision"]} == {False, True}
