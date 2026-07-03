from ah_disclosure import cli


def test_global_prospectus_cli_passes_h_options(monkeypatch):
    calls = {}

    def fake_search_prospectus(market, symbol=None, company_keyword="", max_rows=20, **kwargs):
        calls.update(
            {
                "market": market,
                "symbol": symbol,
                "company_keyword": company_keyword,
                "max_rows": max_rows,
                **kwargs,
            }
        )
        return []

    monkeypatch.setattr(cli, "search_prospectus", fake_search_prospectus)
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "prospectus",
            "--market",
            "H",
            "--symbol",
            "03690",
            "--hkex-stock-id",
            "198419",
            "--lang",
            "EN",
            "--max-rows",
            "3",
        ]
    )

    args.func(args)

    assert calls["market"] == "H"
    assert calls["symbol"] == "03690"
    assert calls["hkex_stock_id"] == "198419"
    assert calls["lang"] == "EN"
    assert calls["max_rows"] == 3


def test_h_prospectus_cli_exists(monkeypatch):
    calls = {}

    def fake_search_prospectus(market, symbol=None, company_keyword="", max_rows=20, **kwargs):
        calls.update({"market": market, "symbol": symbol, "company_keyword": company_keyword, **kwargs})
        return []

    monkeypatch.setattr(cli, "search_prospectus", fake_search_prospectus)
    parser = cli.build_parser()
    args = parser.parse_args(["h", "prospectus", "--symbol", "03690", "--keyword", "Global Offering"])

    args.func(args)

    assert calls["market"] == "H"
    assert calls["symbol"] == "03690"
    assert calls["company_keyword"] == "Global Offering"
