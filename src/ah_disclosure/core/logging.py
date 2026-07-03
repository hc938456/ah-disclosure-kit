from __future__ import annotations

import logging

from .config import get_settings


_CONFIGURED = False


def get_logger(name: str = "ah_disclosure") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        settings = get_settings()
        logging.basicConfig(
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _CONFIGURED = True
    return logging.getLogger(name)
