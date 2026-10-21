"""Privilege escalation.

MintTweaks runs as the desktop user and asks for authorisation only for the
handful of actions that genuinely need root.  We use ``pkexec`` (polkit) rather
than ``sudo`` because a Cinnamon session already has a polkit agent, so the
password dialog is the native one.

Set ``MTK_ROOT_CMD`` to override the prefix (``MTK_ROOT_CMD="sudo -n"`` for
CI or containers, ``MTK_ROOT_CMD=""`` to never escalate).
"""

from __future__ import annotations

import os
import shlex
import shutil
from typing import List, Optional, Sequence
from ..i18n import _

ENV_OVERRIDE = "MTK_ROOT_CMD"
DEFAULT_PREFIX = ("pkexec",)


def is_root() -> bool:
    """True when the current process is already privileged."""
    return hasattr(os, "geteuid") and os.geteuid() == 0


class EscalationUnavailable(RuntimeError):
    """Raised when root is required but no escalation helper exists."""


class Escalator:
    """Turns a plain argv into one that runs with root privileges."""

    def __init__(self, prefix: Optional[Sequence[str]] = None) -> None:
        if prefix is None:
            raw = os.environ.get(ENV_OVERRIDE)
            prefix = shlex.split(raw) if raw is not None else list(DEFAULT_PREFIX)
        self.prefix: List[str] = list(prefix)

    @property
    def enabled(self) -> bool:
        return bool(self.prefix)

    def available(self) -> bool:
        """Can we escalate right now, on this machine?"""
        if is_root():
            return True
        if not self.prefix:
            return False
        return shutil.which(self.prefix[0]) is not None

    def wrap(self, argv: Sequence[str], needs_root: bool = False) -> List[str]:
        """Return the argv actually to execute.

        Program paths are made absolute because ``pkexec`` refuses to look up
        bare names in ``PATH``.
        """
        argv = [str(a) for a in argv]
        if not argv:
            raise ValueError("empty command")
        if not needs_root or is_root():
            return argv
        if not self.prefix:
            raise EscalationUnavailable(
                "This action needs administrator rights and privilege escalation is disabled."
            )
        program = shutil.which(argv[0]) or argv[0]
        return [*self.prefix, program, *argv[1:]]


def escalation_hint() -> str:
    """Human-readable help for the 'I cannot do this' case."""
    if is_root():
        return _("Running as root.")
    if shutil.which("pkexec") is None:
        return _(
            "Privilege escalation is unavailable: 'pkexec' (polkit) is not installed. "
            "Install the 'policykit-1' package to enable administrative actions."
        )
    return _(
        "No polkit authentication agent answered. Make sure a keyring/polkit agent "
        "is running in your desktop session."
    )
