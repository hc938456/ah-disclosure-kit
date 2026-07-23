from ah_disclosure.services.local_search_service import LocalSearchService


def test_zero_page_or_character_budget_performs_no_search(monkeypatch):
    service = LocalSearchService()
    calls: list[tuple[str, int]] = []

    def fail_if_called(query, document_id=None, limit=8, reconcile=True):
        calls.append((query, limit))
        return []

    monkeypatch.setattr(service, "search", fail_if_called)

    zero_pages = service.planned_evidence_packet(
        "query",
        queries=[("term", "user_query")],
        resolved_strategy="llm_dynamic_plan",
        document_id="doc",
        max_pages=0,
        max_chars=100,
        reconcile=False,
    )
    zero_chars = service.planned_evidence_packet(
        "query",
        queries=[("term", "user_query")],
        resolved_strategy="llm_dynamic_plan",
        document_id="doc",
        max_pages=1,
        max_chars=0,
        reconcile=False,
    )

    assert calls == []
    assert zero_pages["evidence_items"] == []
    assert zero_chars["evidence_items"] == []


def test_no_hit_quality_check_reads_only_a_bounded_page_sample(monkeypatch):
    service = LocalSearchService()
    requested_limits: list[int] = []
    monkeypatch.setattr(service, "search", lambda *args, **kwargs: [])

    def bounded_pages(document_id, pages=None, limit=20, reconcile=True):
        requested_limits.append(limit)
        return []

    monkeypatch.setattr(service, "get_pages", bounded_pages)
    result = service.planned_evidence_packet(
        "query",
        queries=[("term", "user_query")],
        resolved_strategy="llm_dynamic_plan",
        document_id="doc",
        max_pages=8,
        max_chars=12000,
        reconcile=False,
    )

    assert result["evidence_items"] == []
    assert requested_limits == [64]
