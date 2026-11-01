"""Optional retirement of Casper's media check on an installed system."""

from dataclasses import dataclass
from pathlib import Path

from ...core.runner import cmd, read_command
from ...i18n import _

UNIT = "casper-md5check.service"
EXPLANATION = _(
    "This service checks the files on the Linux Mint installation USB drive or DVD. "
    "It is unnecessary once Mint is installed on disk and may report an error when "
    "the installation media is absent. Disabling it does not affect disk filesystem checks."
)


@dataclass(frozen=True)
class Status:
    available: bool
    detail: str


def inspect(runner):
    """Fail closed on Live boots, unknown roots and unavailable diagnostics."""
    if runner.dry_run:
        return Status(False, _("Live media check changes are unavailable in simulation mode."))
    boot = Path("/proc/cmdline").read_text().split()
    if any(token in ("boot=casper", "boot=live") or token.startswith("rd.live.") for token in boot) or any(
        Path(path).exists() for path in ("/run/casper", "/run/live/medium", "/rofs")
    ):
        return Status(False, _("Live session detected: keep the installation media check enabled."))
    filesystem = read_command(runner, cmd("findmnt", "--noheadings", "--output", "FSTYPE", "--target", "/")).stdout.strip()
    if filesystem not in {"ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "zfs"}:
        return Status(False, _("An installation on disk could not be confirmed. No changes are available."))
    result = read_command(runner, cmd(
        "systemctl", "show", UNIT, "--no-pager",
        "--property=LoadState,UnitFileState,ActiveState",
    ))
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if values.get("LoadState") == "not-found":
        return Status(False, _("The Live media check service is not installed."))
    if values.get("UnitFileState") in {"disabled", "masked"} and values.get("ActiveState") == "inactive":
        return Status(False, _("The Live media check is already disabled."))
    if values.get("LoadState") != "loaded" or values.get("UnitFileState") not in {"enabled", "enabled-runtime", "disabled"} or values.get("ActiveState") not in {"active", "inactive", "failed"}:
        return Status(False, _("The Live media check service state could not be confirmed. No changes are available."))
    return Status(True, _("Installation on disk detected. You can disable the Live media check and clear its failure state."))


def disable(runner):
    """Recheck eligibility immediately before issuing scoped privileged commands."""
    status = inspect(runner)
    if not status.available:
        raise RuntimeError(status.detail)
    for args in (("disable", "--now", UNIT), ("reset-failed", UNIT)):
        result = runner.run(cmd("systemctl", *args, root=True), timeout=120)
        if not result.ok:
            raise RuntimeError(result.output or _("The Live media check change failed. Reload its status before retrying."))
    return inspect(runner)
