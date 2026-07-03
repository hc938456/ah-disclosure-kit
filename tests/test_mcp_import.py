def test_mcp_import():
    import ah_disclosure.mcp_server as m
    assert m.server_info()["name"] == "ah-disclosure"
