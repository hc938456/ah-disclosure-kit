import os
from pathlib import Path

from ah_disclosure.core.file_utils import normalized_path_key, replace_file_with_retry


def test_replace_file_retries_transient_permission_error(monkeypatch, tmp_path):
    source = tmp_path / "source.tmp"
    target = tmp_path / "target.json"
    source.write_text("new", encoding="utf-8")
    calls = {"count": 0}

    def flaky_replace(self, destination):
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError("temporary lock")
        return Path(destination)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    replaced = replace_file_with_retry(source, target, attempts=3, delay_seconds=0)

    assert replaced == target
    assert calls["count"] == 3


def test_normalized_path_key_uses_platform_case_rules(tmp_path):
    path = tmp_path / "CaseSensitiveName.txt"

    assert normalized_path_key(path) == os.path.normcase(str(path.resolve()))
