"""Where MintTweaks keeps things on disk.

Every default path lives here so the rest of the code never hard-codes one, and
so tests can point at a temporary directory instead of the real system.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "minttweaks"

# --- System paths -----------------------------------------------------------
SMB_CONF = Path("/etc/samba/smb.conf")

# --- Per-user paths ---------------------------------------------------------
def _xdg(env_var: str, fallback: str) -> Path:
    raw = os.environ.get(env_var, "").strip()
    base = Path(raw) if raw else Path(fallback).expanduser()
    return base / APP_DIR_NAME


DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share")
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", "~/.config")

BACKUP_DIR = DATA_DIR / "backups"
PROFILE_DIR = DATA_DIR / "cinnamon-profiles"
PROFILE_BACKUP_DIR = DATA_DIR / "cinnamon-backups"
SETUP_PLAN = DATA_DIR / "setup-plan.json"
TERMINAL_BACKUP_DIR = DATA_DIR / "terminal-backups"
LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "minttweaks.log"

# --- Bundled resources ------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent.parent
UI_DIR = PKG_DIR / "ui"
STYLE_CSS = UI_DIR / "style.css"


def ensure_user_dirs() -> None:
    """Create the per-user directories MintTweaks writes to."""
    for directory in (DATA_DIR, BACKUP_DIR, LOG_DIR, CONFIG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
