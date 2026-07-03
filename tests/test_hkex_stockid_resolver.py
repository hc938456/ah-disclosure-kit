from ah_disclosure.identity import hkex_stockid_resolver


def test_candidate_stock_id_reuses_cached_company_name(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    cache_path = hkex_stockid_resolver._cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"03690":{"symbol":"03690","hkex_stock_id":"198419","company_name":"MEITUAN-W","verified":true}}',
        encoding="utf-8",
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id("03690", candidate_stock_id="198419", verify=False)

    assert result["company_name"] == "MEITUAN-W"
    assert result["hkex_stock_id"] == "198419"
