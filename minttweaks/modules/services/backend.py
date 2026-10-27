"""systemd units and their logs.

Everything here is read-mostly.  The three write actions (start/stop/restart,
enable/disable, and asking for a unit's journal) are validated against a strict
unit-name pattern before touching :mod:`subprocess`, so a unit name coming from
the UI can never smuggle in an extra argument.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ...core.runner import BaseRunner, ReadError, Result, cmd, read_command
from ...i18n import _

#: A systemd unit name we are willing to hand to ``systemctl``.
UNIT_RE = re.compile(r"^[A-Za-z0-9:_.@\\-]+\.service$")

ACTIONS = ("start", "stop", "restart", "reload", "enable", "disable")


@dataclass
class Unit:
    name: str
    active: str = "inactive"
    sub: str = "dead"
    description: str = ""
    enabled: str = "unknown"

    @property
    def failed(self) -> bool:
        return self.active == "failed"

    @property
    def running(self) -> bool:
        return self.active == "active"

    @property
    def is_enabled(self) -> bool:
        return self.enabled in ("enabled", "enabled-runtime", "static", "alias", "indirect")

    @property
    def state_label(self) -> str:
        if self.failed:
            return _("failed")
        if self.running:
            return _("running") if self.sub == "running" else _("active")
        if self.active == "inactive":
            return _("inactive")
        if self.active == "deactivating":
            return _("deactivating")
        return self.active or _("unknown")


#: systemctl marks failed units with one of these, followed by a space.
_MARKERS = "●×*✦•"


def _clean_name(token: str) -> str:
    return token.strip().lstrip(_MARKERS).strip()


def _fields(line: str) -> List[str]:
    """Split a systemctl table row, dropping any leading status marker."""
    return line.strip().lstrip(_MARKERS).strip().split(None, 4)


def parse_list_units(text: str) -> Dict[str, Unit]:
    """Parse ``systemctl list-units --type=service --all --plain --no-legend``."""
    units: Dict[str, Unit] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.endswith(":") or line.lower().startswith("loaded units listed"):
            continue
        parts = _fields(raw)
        if len(parts) < 4:
            continue
        name = _clean_name(parts[0])
        if not UNIT_RE.match(name):
            continue
        units[name] = Unit(
            name=name,
            active=parts[2].strip(),
            sub=parts[3].strip(),
            description=parts[4].strip() if len(parts) > 4 else "",
        )
    return units


def parse_unit_files(text: str) -> Dict[str, str]:
    """Parse ``systemctl list-unit-files --type=service`` into name -> state."""
    states: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.endswith(":") or line.lower().startswith("unit files listed"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        name = _clean_name(parts[0])
        if UNIT_RE.match(name):
            states[name] = parts[1].strip()
    return states


def list_units(runner: BaseRunner) -> List[Unit]:
    """All service units, merging runtime state with enablement state."""
    runtime = read_command(runner,
        cmd(
            "systemctl",
            "list-units",
            "--type=service",
            "--all",
            "--no-pager",
            "--no-legend",
            "--plain",
        ),
        timeout=45,
    )
    files = read_command(runner,
        cmd("systemctl", "list-unit-files", "--type=service", "--no-pager", "--no-legend", "--plain"),
        timeout=45,
    )

    units = parse_list_units(runtime.stdout)
    for name, state in parse_unit_files(files.stdout).items():
        if name in units:
            units[name].enabled = state
        else:
            units[name] = Unit(name=name, enabled=state)
    return sorted(units.values(), key=lambda unit: unit.name)


def failed_units(runner: BaseRunner) -> List[Unit]:
    result = read_command(runner,
        cmd("systemctl", "--failed", "--type=service", "--no-pager", "--no-legend", "--plain"),
        timeout=30,
    )
    if not result.stdout.strip():
        return []
    return [unit for unit in parse_list_units(result.stdout).values() if unit.failed]


def valid_unit(name: str) -> bool:
    """Accept only plain unit names.

    The pattern alone would allow ``..service``; a name is additionally rejected
    when it starts with ``.``/``-`` or contains ``..`` so that nothing that looks
    like a path or an option can reach ``systemctl``.
    """
    candidate = (name or "").strip()
    if not candidate or candidate.startswith((".", "-")) or ".." in candidate:
        return False
    return bool(UNIT_RE.match(candidate))


def control(
    runner: BaseRunner,
    unit: str,
    action: str,
    on_line: Optional[Callable[[str], None]] = None,
) -> Result:
    """Start/stop/restart/enable/disable one unit."""
    if not valid_unit(unit):
        return Result(f"systemctl {action} {unit}", 2, stderr=f"Refusing to drive unit '{unit}'.")
    if action not in ACTIONS:
        return Result(f"systemctl {action} {unit}", 2, stderr=f"Unsupported action '{action}'.")
    command = cmd("systemctl", action, unit, root=True)
    if on_line is not None:
        return runner.stream(command, on_line=on_line, timeout=120)
    return runner.run(command, timeout=120)


def journal(
    runner: BaseRunner,
    unit: Optional[str] = None,
    lines: int = 400,
    as_root: bool = False,
) -> Result:
    """Recent journal entries for one unit, or for the whole system."""
    if unit is not None and not valid_unit(unit):
        return Result(f"journalctl -u {unit}", 2, stderr=f"Refusing to read journal for '{unit}'.")
    argv = ["journalctl", "--no-pager", "--output=short-iso", "-n", str(max(1, min(lines, 5000)))]
    if unit is not None:
        argv += ["-u", unit]
    return runner.run(cmd(*argv, root=as_root), timeout=60)


def boot_summary(runner: BaseRunner) -> str:
    return read_command(runner, cmd("systemd-analyze"), timeout=30).stdout.strip()


def boot_blame(runner: BaseRunner, lines: int = 15) -> List[tuple]:
    """``[(duration_text, unit), ...]`` slowest first."""
    result = read_command(runner, cmd("systemd-analyze", "blame", "--no-pager"), timeout=60)
    rows: List[tuple] = []
    for raw in result.stdout.splitlines()[: max(1, lines)]:
        parts = raw.strip().split(None, 1)
        if len(parts) == 2:
            rows.append((parts[0], parts[1].strip()))
    return rows


def critical_chain(runner: BaseRunner) -> str:
    return read_command(runner, cmd("systemd-analyze", "critical-chain", "--no-pager"), timeout=60).stdout


@dataclass
class BootReport:
    summary: str = ""
    blame: List[tuple] = field(default_factory=list)
    chain: str = ""
    errors: Dict[str, str] = field(default_factory=dict)


def collect_boot_report(runner: BaseRunner) -> BootReport:
    report = BootReport()
    for key, check in (("summary", boot_summary), ("blame", boot_blame), ("chain", critical_chain)):
        try:
            setattr(report, key, check(runner))
        except Exception as exc:
            report.errors[key] = str(exc)
    return report

