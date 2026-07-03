from ah_disclosure.clients.hkex_client import HkexClient


def test_hkex_parser_extracts_publish_date_from_document_url():
    html = """
    <html><body>
      <a href="/listedco/listconews/sehk/2018/0907/ltn20180907017.pdf">GLOBAL OFFERING</a>
    </body></html>
    """

    rows = HkexClient().parse_title_search_html(html, hk_code="03690")

    assert rows[0].publish_time == "2018-09-07"
