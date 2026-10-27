"""Read-only system overview and diagnostics.

Everything in this module is observational: it reads files and runs only
read-only commands.  Findings are independent, so a check that cannot run on a
given machine (missing dpkg, unreadable journal, ...) degrades to an informative
result instead of hiding the rest of the report.
"""

from __future__ import annotations

import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...core.runner import BaseRunner, ReadError, cmd
from ...i18n import _
from ..maintenance import backend as maintenance
from ..services import backend as services

OS_RELEASE = Path("/etc/os-release")
MEMINFO = Path("/proc/meminfo")
UPTIME = Path("/proc/uptime")
REBOOT_REQUIRED = Path("/var/run/reboot-required")

SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2, "ok": 3}


@dataclass(frozen=True)
class Finding:
    severity: str
    title_msgid: str
    detail_msgid: str = ""
    values: Dict[str, object] = field(default_factory=dict)
    page: Optional[str] = None
    completed: bool = True

    @property
    def title(self) -> str:
        return _(self.title_msgid).format(**self.values)

    @property
    def detail(self) -> str:
        if not self.detail_msgid:
            return ""
        return _(self.detail_msgid).format(**self.values)


@dataclass
class SystemSummary:
    os_name: str = ""
    kernel: str = ""
    hostname: str = ""
    uptime: str = ""
    memory_used: str = ""
    memory_total: str = ""
    memory_percent: int = 0
    memory_measured: bool = True
    disk_used: str = ""
    disk_total: str = ""
    disk_free: str = ""
    disk_percent: int = 0
    disk_measured: bool = True


@dataclass
class HomeReport:
    summary: SystemSummary
    findings: List[Finding]

    @property
    def errors(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "warn")

    @property
    def passed(self) -> int:
        return sum(1 for finding in self.findings if finding.severity == "ok" and finding.completed)

    @property
    def unavailable(self) -> int:
        return sum(1 for finding in self.findings if not finding.completed)


# --------------------------------------------------------------------------- #
# Files and formatting
# --------------------------------------------------------------------------- #
def parse_os_release(text: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def parse_meminfo(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Return ``(total_bytes, available_bytes)`` from /proc/meminfo."""
    values: Dict[str, int] = {}
    for raw in text.splitlines():
        key, _, rest = raw.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[key.strip()] = int(parts[0]) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable", values.get("MemFree"))
    return total, available


def read_uptime(path: Path = UPTIME) -> Optional[float]:
    try:
        first = path.read_text(encoding="utf-8", errors="replace").split()[0]
        return float(first)
    except (OSError, ValueError, IndexError):
        return None


def format_uptime(seconds: Optional[float]) -> str:
    if seconds is None:
        return _("unknown")
    minutes = max(0, int(seconds // 60))
    days, remainder = divmod(minutes, 1440)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"{days} d {hours} h {minutes} min"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def collect_summary(
    runner: BaseRunner,
    os_release: Path = OS_RELEASE,
    meminfo: Path = MEMINFO,
    uptime_file: Path = UPTIME,
    root: Path = Path("/"),
) -> SystemSummary:
    summary = SystemSummary()

    try:
        release = parse_os_release(os_release.read_text(encoding="utf-8", errors="replace"))
        summary.os_name = release.get("PRETTY_NAME") or release.get("NAME") or _("unknown")
    except OSError:
        summary.os_name = _("unknown")

    try:
        kernel = runner.run(cmd("uname", "-r"), timeout=10) if not runner.dry_run else None
        summary.kernel = kernel.stdout.strip() if kernel is not None and kernel.ok and kernel.stdout.strip() else _("unknown")
    except Exception:
        summary.kernel = _("unknown")
    try:
        summary.hostname = socket.gethostname() or _("unknown")
    except OSError:
        summary.hostname = _("unknown")
    summary.uptime = format_uptime(read_uptime(uptime_file))

    try:
        total, available = parse_meminfo(meminfo.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        total, available = None, None
    if total:
        if available is None or not 0 <= available <= total:
            summary.memory_used = _("unknown")
            summary.memory_total = maintenance.human_bytes(total)
            summary.memory_measured = False
        else:
            used = total - available
            summary.memory_used = maintenance.human_bytes(used)
            summary.memory_total = maintenance.human_bytes(total)
            summary.memory_percent = round(used * 100 / total)
    else:
        summary.memory_used = _("unknown")
        summary.memory_total = _("unknown")
        summary.memory_measured = False

    try:
        usage = shutil.disk_usage(str(root))
    except OSError:
        summary.disk_used = _("unknown")
        summary.disk_total = _("unknown")
        summary.disk_free = _("unknown")
        summary.disk_percent = -1
        summary.disk_measured = False
    else:
        summary.disk_used = maintenance.human_bytes(usage.used)
        summary.disk_total = maintenance.human_bytes(usage.total)
        summary.disk_free = maintenance.human_bytes(usage.free)
        if usage.total:
            summary.disk_percent = round(usage.used * 100 / usage.total)
        else:
            summary.disk_percent = -1
            summary.disk_measured = False

    return summary


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
def _sample(text: str, limit: int = 180) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sample = " | ".join(lines[:3])
    return sample[:limit]


def check_package_database(runner: BaseRunner) -> Finding:
    result = runner.run(cmd("dpkg", "--audit"), timeout=60)
    if result.returncode == 127:
        return Finding("info", _("Package database"), _("dpkg is not available on this system."), completed=False)
    if not result.ok:
        return unavailable(_("Package database"), result.output or result.command, "maintenance")
    output = result.output.strip()
    if output:
        return Finding(
            "warn",
            _("Package database"),
            _("dpkg --audit reported: {sample}"),
            {"sample": _sample(output)},
            page="maintenance",
        )
    return Finding("ok", _("Package database"), _("No half-configured package was found."))


def check_dependencies(runner: BaseRunner) -> Finding:
    result = runner.run(cmd("apt-get", "check"), timeout=120)
    if result.returncode == 127:
        return Finding("info", _("Dependencies"), _("apt-get is not available on this system."), completed=False)
    if result.ok:
        return Finding("ok", _("Dependencies"), _("apt-get check found no broken dependency."))
    if result.returncode != 100 or not any(marker in result.output.lower() for marker in ("unmet dependencies", "broken dependencies")):
        return unavailable(_("Dependencies"), result.output or result.command, "maintenance")
    return Finding(
        "error",
        _("Dependencies"),
        _("apt-get check reported a problem: {sample}"),
        {"sample": _sample(result.output) or result.command},
        page="maintenance",
    )


def check_failed_services(runner: BaseRunner) -> Finding:
    result = runner.run(
        cmd(
            "systemctl",
            "--failed",
            "--type=service",
            "--no-pager",
            "--no-legend",
            "--plain",
        ),
        timeout=30,
    )
    if result.returncode == 127:
        return Finding("info", _("Failed services"), _("systemctl is not available on this system."), completed=False)
    if not result.ok:
        return unavailable(_("Failed services"), result.output or result.command, "services")
    units = [unit for unit in services.parse_list_units(result.stdout).values() if unit.failed]
    if units:
        names = ", ".join(unit.name for unit in units[:6])
        return Finding(
            "error",
            _("Failed services"),
            _("{count} service(s) failed: {names}"),
            {"count": len(units), "names": names},
            page="services",
        )
    return Finding("ok", _("Failed services"), _("No service has failed."))


def check_boot_errors(runner: BaseRunner) -> Finding:
    result = runner.run(
        cmd("journalctl", "-p", "err", "-b", "--no-pager", "-n", "20", "--output=short-iso"),
        timeout=60,
    )
    if result.returncode == 127:
        return Finding("info", _("Boot errors"), _("journalctl is not available on this system."), completed=False)
    if not result.ok:
        return unavailable(_("Boot errors"), result.output or result.command, "services")
    # journalctl may succeed while warning that only the user's journal is
    # visible. An empty restricted view does not prove the system is healthy.
    if result.stderr.strip():
        return unavailable(_("Boot errors"), result.output, "services")
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("-- ")
    ]
    if lines:
        return Finding(
            "warn",
            _("Boot errors"),
            _("{count} error line(s) in the latest 20 entries since boot. First entry: {sample}"),
            {"count": len(lines), "sample": lines[0][:180]},
            page="services",
        )
    return Finding("ok", _("Boot errors"), _("No error was logged since the last boot."))


def disk_finding(percent: int, free: str) -> Finding:
    if percent < 0:
        return Finding("info", _("Disk space"), _("Disk usage could not be measured."), page="maintenance", completed=False)
    values = {"percent": percent, "free": free}
    if percent >= 95:
        return Finding(
            "error",
            _("Disk space"),
            _("The root filesystem is almost full: {percent}% used, {free} free."),
            values,
            page="maintenance",
        )
    if percent >= 85:
        return Finding(
            "warn",
            _("Disk space"),
            _("The root filesystem is filling up: {percent}% used, {free} free."),
            values,
            page="maintenance",
        )
    return Finding(
        "ok",
        _("Disk space"),
        _("The root filesystem is {percent}% used, {free} free."),
        values,
        page="maintenance",
    )


def check_reboot(path: Path = REBOOT_REQUIRED) -> Finding:
    try:
        path.stat()
    except FileNotFoundError:
        return Finding("ok", _("Restart required"), _("No restart is pending."))
    except OSError as exc:
        return unavailable(_("Restart required"), str(exc))
    else:
        return Finding(
            "warn",
            _("Restart required"),
            _("The system must restart to finish applying updates."),
        )


def check_kernels(runner: BaseRunner) -> Finding:
    try:
        kernels = maintenance.installed_kernels(runner)
    except ReadError as exc:
        return unavailable(_("Old kernels"), str(exc), "maintenance")
    if not kernels:
        return Finding("info", _("Old kernels"), _("No installed kernel package was found."), page="maintenance")
    removable = maintenance.removable_kernels(kernels, keep=1)
    if removable:
        versions = ", ".join(kernel.version for kernel in removable[:4])
        return Finding(
            "info",
            _("Old kernels"),
            _("{count} old kernel(s) can be removed: {versions}"),
            {"count": len(removable), "versions": versions},
            page="maintenance",
        )
    return Finding("ok", _("Old kernels"), _("No old kernel is waiting for removal."))


def collect_report(
    runner: BaseRunner,
    os_release: Path = OS_RELEASE,
    meminfo: Path = MEMINFO,
    uptime_file: Path = UPTIME,
    root: Path = Path("/"),
    reboot_file: Path = REBOOT_REQUIRED,
) -> HomeReport:
    summary = collect_summary(runner, os_release, meminfo, uptime_file, root)
    findings = []
    checks = (
        (_("Package database"), "maintenance", lambda: check_package_database(runner), True),
        (_("Dependencies"), "maintenance", lambda: check_dependencies(runner), True),
        (_("Failed services"), "services", lambda: check_failed_services(runner), True),
        (_("Boot errors"), "services", lambda: check_boot_errors(runner), True),
        (_("Disk space"), "maintenance", lambda: disk_finding(summary.disk_percent, summary.disk_free), False),
        (_("Restart required"), None, lambda: check_reboot(reboot_file), False),
        (_("Old kernels"), "maintenance", lambda: check_kernels(runner), True),
    )
    for title, page, check, needs_command in checks:
        try:
            if runner.dry_run and needs_command:
                finding = Finding("info", title, _("Not checked in simulation mode."), page=page, completed=False)
            else:
                finding = check()
        except Exception as exc:
            finding = unavailable(title, str(exc), page)
        findings.append(finding)
    findings.sort(key=lambda finding: SEVERITY_ORDER.get(finding.severity, 99))
    return HomeReport(summary, findings)


def unavailable(title: str, detail: str, page: Optional[str] = None) -> Finding:
    return Finding("info", title, _("Could not verify: {sample}"), {"sample": _sample(detail)}, page=page, completed=False)
