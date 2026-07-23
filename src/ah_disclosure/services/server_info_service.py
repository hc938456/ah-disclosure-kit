from __future__ import annotations

from typing import Any

from ah_disclosure import __version__
from ah_disclosure.core.paths import get_data_dir
from ah_disclosure.providers.akshare_registry import list_supported_interfaces


def get_server_info() -> dict[str, Any]:
    """Return server metadata without importing the MCP runtime."""
    return {
        "name": "ah-disclosure",
        "version": __version__,
        "data_dir": str(get_data_dir()),
        "supported_interfaces": list_supported_interfaces(),
    }
