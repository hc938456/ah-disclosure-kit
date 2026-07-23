import os
import time

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


def test_verified_cached_candidate_skips_duplicate_verification(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    cache_path = hkex_stockid_resolver._cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"06862":{"symbol":"06862","hkex_stock_id":"123","verified":true}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "verify_stock_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("verified cache match should skip HKEX verification")
        ),
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id(
        "06862", candidate_stock_id="123", verify=True
    )

    assert result["cache_hit"] is True
    assert result["verification_skipped"] == "verified_cache_match"


def test_inactive_security_uses_verified_historical_mapping(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "lookup_stock",
        lambda self, code: None,
    )
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "verify_stock_id",
        lambda self, stock_id, **kwargs: {
            "hkex_stock_id": stock_id,
            "verified": True,
            "records_sample": [],
        },
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id("07836")

    assert result["hkex_stock_id"] == "1000145057"
    assert result["verified"] is True
    assert result["discovered_by"] == "verified historical HKEX mapping"


def test_delisted_hang_seng_bank_uses_historical_mapping(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "lookup_stock",
        lambda self, code: None,
    )
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "verify_stock_id",
        lambda self, stock_id, **kwargs: {
            "hkex_stock_id": stock_id,
            "verified": True,
            "records_sample": [],
        },
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id("00011")

    assert result["hkex_stock_id"] == "18"
    assert result["verified"] is True


def test_historical_mapping_does_not_depend_on_live_prefix_search(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "lookup_stock",
        lambda self, code: (_ for _ in ()).throw(TimeoutError("offline")),
    )
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "verify_stock_id",
        lambda self, stock_id, **kwargs: {
            "hkex_stock_id": stock_id,
            "verified": True,
            "records_sample": [],
        },
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id("07836")

    assert result["hkex_stock_id"] == "1000145057"
    assert result["verified"] is True


def test_old_mapping_does_not_expire_or_query_hkex(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    cache_path = hkex_stockid_resolver._cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"00700":{"symbol":"00700","hkex_stock_id":"198419","verified":true}}',
        encoding="utf-8",
    )
    old = time.time() - 3650 * 86400
    os.utime(cache_path, (old, old))
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "lookup_stock",
        lambda self, code: (_ for _ in ()).throw(
            AssertionError("permanent cache should prevent a live HKEX query")
        ),
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id("00700", verify=False)

    assert result["hkex_stock_id"] == "198419"
    assert result["cache_hit"] is True


def test_explicit_refresh_rechecks_mapping_and_updates_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    cache_path = hkex_stockid_resolver._cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"00700":{"symbol":"00700","hkex_stock_id":"old","verified":true}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "lookup_stock",
        lambda self, code: {
            "symbol": code,
            "hkex_stock_id": "new",
            "company_name": "TENCENT",
            "source": "HKEXnews prefix.do",
        },
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id(
        "00700", verify=False, refresh=True
    )

    assert result["hkex_stock_id"] == "new"
    assert result["cache_hit"] is False


def test_explicit_refresh_failure_keeps_permanent_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    cache_path = hkex_stockid_resolver._cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"00700":{"symbol":"00700","hkex_stock_id":"198419","verified":true}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        hkex_stockid_resolver.HkexClient,
        "lookup_stock",
        lambda self, code: (_ for _ in ()).throw(TimeoutError("offline")),
    )

    result = hkex_stockid_resolver.resolve_hkex_stock_id(
        "00700", refresh=True
    )

    assert result["hkex_stock_id"] == "198419"
    assert result["refresh_failed"] is True
