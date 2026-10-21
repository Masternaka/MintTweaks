"""Translation support.

Every user-visible string is written in English in the source and wrapped in
``_()``; French translations live in ``po/fr.po`` and are compiled to
``minttweaks/locale/<lang>/LC_MESSAGES/minttweaks.mo``.

Two deliberate choices:

* ``_`` is a real function, not ``gettext.gettext`` bound at import time. Modules
  do ``from ..i18n import _``, and if that bound the C function directly the
  translation catalogue loaded by :func:`install` would never reach them.
* The output panel is a technical transcript (commands, testparm output, apt
  output) and stays in English. Only the interface is translated.
"""

from __future__ import annotations

import gettext
import os
from pathlib import Path
from typing import Iterator, Optional, Sequence

DOMAIN = "minttweaks"

_translation: gettext.NullTranslations = gettext.NullTranslations()

#: Our own French catalogue, used as the fallback test fixture and by `make test`.
PACKAGE_DIR = Path(__file__).resolve().parent


def _(message: str) -> str:
    """Translate one string; returns it unchanged when no catalogue matches."""
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, count: int) -> str:
    return _translation.ngettext(singular, plural, count)


def locale_dirs() -> Iterator[Path]:
    """Where to look for ``<lang>/LC_MESSAGES/minttweaks.mo``, best first."""
    override = os.environ.get("MTK_LOCALEDIR", "").strip()
    if override:
        yield Path(override)
    yield PACKAGE_DIR / "locale"  # in-tree build (`make translations`)
    yield Path("/usr/share/locale")


def install(languages: Optional[Sequence[str]] = None) -> str:
    """Load the best catalogue available. Returns the language actually used."""
    global _translation
    for directory in locale_dirs():
        if not directory.is_dir():
            continue
        try:
            translation = gettext.translation(
                DOMAIN,
                localedir=str(directory),
                languages=list(languages) if languages else None,
                fallback=False,
            )
        except (OSError, IOError):
            continue
        _translation = translation
        return translation.info().get("language", "") or "unknown"

    _translation = gettext.NullTranslations()
    return "C"


def reset() -> None:
    """Drop the loaded catalogue (used when switching language at runtime)."""
    global _translation
    _translation = gettext.NullTranslations()


def current() -> gettext.NullTranslations:
    """The active catalogue (mainly for tests)."""
    return _translation
