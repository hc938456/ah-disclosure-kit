from ah_disclosure.identity import a_symbol_resolver


def test_resolves_legacy_and_new_bse_codes(monkeypatch):
    monkeypatch.setattr(
        a_symbol_resolver,
        "canonicalize_bse_symbol",
        lambda symbol, **kwargs: {
            "symbol": "920982" if symbol == "832982" else symbol,
            "alias_resolved": symbol == "832982",
        },
    )

    legacy = a_symbol_resolver.resolve_a_symbol("832982.BJ")
    current = a_symbol_resolver.resolve_a_symbol("920982")

    assert legacy["exchange"] == "BSE"
    assert legacy["symbol"] == "920982"
    assert legacy["alias_resolved"] is True
    assert current["exchange"] == "BSE"


def test_resolves_sse_and_szse_codes():
    assert a_symbol_resolver.resolve_a_symbol("688347.SH")["exchange"] == "SSE"
    assert a_symbol_resolver.resolve_a_symbol("300750.SZ")["exchange"] == "SZSE"
