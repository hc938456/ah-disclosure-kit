from ah_disclosure.clients.hkex_client import (
    HkexClient,
    get_thread_hkex_client,
    paired_chinese_pdf_url,
)


def test_hkex_parser_extracts_publish_date_from_document_url():
    html = """
    <html><body>
      <a href="/listedco/listconews/sehk/2018/0907/ltn20180907017.pdf">GLOBAL OFFERING</a>
    </body></html>
    """

    rows = HkexClient().parse_title_search_html(html, hk_code="03690")

    assert rows[0].publish_time == "2018-09-07"
    assert rows[0].raw_id == "ltn20180907017"


def test_hkex_parser_preserves_document_category_and_size():
    html = """
    <table><tr>
      <td><div class="headline">Listing Documents - [Offer for Subscription]</div>
      <div class="doc-link">
        <a href="/listedco/listconews/sehk/2020/1201/2020120100099.pdf">GLOBAL OFFERING</a>
        (<span class="attachment_filesize">10MB</span>)
      </div></td>
    </tr></table>
    """

    row = HkexClient().parse_title_search_html(html, hk_code="09992")[0]

    assert row.category == "Listing Documents - [Offer for Subscription]"
    assert row.document_type == row.category
    assert row.file_size_label == "10MB"


def test_paired_chinese_pdf_url_increments_document_sequence():
    url = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0423/2026042300752.pdf"

    assert paired_chinese_pdf_url(url) == (
        "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0423/2026042300753_c.pdf"
    )


def test_listing_package_pdf_urls_preserves_order_and_deduplicates(monkeypatch):
    class Response:
        content = b"""
        <a href="parts/001.pdf">Cover</a>
        <a href="parts/002.pdf">Business</a>
        <a href="parts/001.pdf">Cover duplicate</a>
        <a href="https://example.com/external.pdf">External</a>
        """

        def raise_for_status(self):
            return None

    client = HkexClient()
    monkeypatch.setattr(client.session, "get", lambda *args, **kwargs: Response())

    urls = client.listing_package_pdf_urls(
        "https://www1.hkexnews.hk/listedco/listconews/sehk/2022/0228/package.htm"
    )

    assert urls == [
        "https://www1.hkexnews.hk/listedco/listconews/sehk/2022/0228/parts/001.pdf",
        "https://www1.hkexnews.hk/listedco/listconews/sehk/2022/0228/parts/002.pdf",
    ]


def test_thread_hkex_client_reuses_session_within_same_thread():
    class IsolatedClient:
        pass

    first = get_thread_hkex_client(IsolatedClient)
    second = get_thread_hkex_client(IsolatedClient)

    assert first is second


def test_pdf_exists_falls_back_to_range_get_when_head_is_rejected(monkeypatch):
    class HeadResponse:
        ok = False
        headers = {"content-type": "text/html"}

        def close(self):
            return None

    class GetResponse:
        headers = {"content-type": "application/octet-stream"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"%PDF-1.7"

        def close(self):
            return None

    client = HkexClient()
    monkeypatch.setattr(client.session, "head", lambda *args, **kwargs: HeadResponse())
    monkeypatch.setattr(client.session, "get", lambda *args, **kwargs: GetResponse())

    assert client.pdf_exists("https://www1.hkexnews.hk/report.pdf") is True
