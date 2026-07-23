from __future__ import annotations

import os
import subprocess
import sys

from ah_disclosure import cli


class _FakeStream:
    encoding = "cp936"

    def __init__(self) -> None:
        self.calls = []

    def reconfigure(self, **kwargs) -> None:
        self.calls.append(kwargs)
        self.encoding = kwargs["encoding"]


def test_configure_utf8_stream_reconfigures_cp936():
    stream = _FakeStream()

    cli._configure_utf8_stream(stream)

    assert stream.calls == [{"encoding": "utf-8", "errors": "backslashreplace"}]


def test_cli_dump_outputs_utf8_when_pythonioencoding_is_cp936():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp936"
    command = [
        sys.executable,
        "-c",
        "from ah_disclosure.cli import dump; dump({'text': '中文 • “quote”'})",
    ]

    result = subprocess.run(command, env=env, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    output = result.stdout.decode("utf-8")
    assert "中文 • “quote”" in output
