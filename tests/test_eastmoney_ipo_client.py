import os
import time

from ah_disclosure.identity import bse_symbol_resolver


def test_bse_code_mapping_reads_official_old_and_new_codes(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    class Response:
        text = """
        <table><tr><td>34</td><td>宏裕包材</td><td>2023/8/18</td>
        <td>837174</td><td>920274</td></tr></table>
        """
        encoding = None

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        bse_symbol_resolver.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )

    mapping, cache_hit = bse_symbol_resolver.get_bse_code_mapping(refresh=True)

    assert mapping["837174"] == "920274"
    assert cache_hit is False
    cached, cache_hit = bse_symbol_resolver.get_bse_code_mapping()
    assert cached == mapping
    assert cache_hit is True


def test_old_bse_mapping_does_not_expire(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    cache_path = bse_symbol_resolver._cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        '{"legacy_to_current":{"837174":"920274"}}',
        encoding="utf-8",
    )
    old = time.time() - 3650 * 86400
    os.utime(cache_path, (old, old))
    monkeypatch.setattr(
        bse_symbol_resolver.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("permanent cache should prevent a live BSE query")
        ),
    )

    mapping, cache_hit = bse_symbol_resolver.get_bse_code_mapping()

    assert mapping["837174"] == "920274"
    assert cache_hit is True
