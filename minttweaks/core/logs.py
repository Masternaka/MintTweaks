"""Logging for MintTweaks.

The GUI shows a live transcript, but everything also lands in a rotating log
file so a user can paste it into a bug report after a crash.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from .paths import LOG_FILE, ensure_user_dirs

_configured = False


def setup(level: int = logging.INFO, to_stderr: bool = True) -> None:
    """Configure the root logger once."""
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    try:
        ensure_user_dirs()
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    except OSError:
        # A read-only home must not stop the application from starting.
        pass

    if to_stderr:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    _configured = True

