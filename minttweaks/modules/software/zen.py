"""Run Zen's documented user installer, with review and no privilege escalation."""

from __future__ import annotations

import configparser
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import tempfile

from ...core.runner import cmd, read_command
from ...i18n import _
from .backend import Availability, InstallOutcome, SoftwareError, architecture, package_state

INSTALLER_URL = "https://raw.githubusercontent.com/zen-browser/updates-server/refs/heads/main/install.sh"
DOWNLOAD_URL = "https://github.com/zen-browser/desktop/releases/latest"


def targets():
    home = Path.home()
    return (home / ".tarball-installations/zen", home / ".local/bin/zen",
            home / ".local/share/applications/zen.desktop")


def installed_version():
    directory, launcher, desktop = targets()
    binary = directory / "zen"
    if not (binary.is_file() and os.access(binary, os.X_OK)
            and launcher.is_file() and desktop.is_file()):
        return ""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(directory / "application.ini", encoding="utf-8")
    return parser.get("App", "Version", fallback="").strip()


def check_status(runner, arch):
    try:
        if runner.dry_run:
            raise SoftwareError(_("Software availability is not checked in simulation mode."))
        if os.geteuid() == 0:
            raise SoftwareError(_("Run MintTweaks as your regular user to install Zen."))
        if arch not in ("amd64", "arm64"):
            raise SoftwareError(_("This source has no supported package for architecture {architecture}.").format(architecture=arch))
        legacy = package_state(runner, "zen-browser")
        if legacy.installed:
            return Availability(installed=True, installed_version=legacy.version, installation_method='legacy-deb',
                error=_("The old Zen Debian package is installed. Remove zen-browser with Mint's package manager before installing the official version. Keep your browser profile."))
        version = installed_version()
        if version:
            return Availability(installed=True, installed_version=version)
        if any(path.exists() or path.is_symlink() for path in targets()):
            raise SoftwareError(_("Existing Zen installation files were found. Check them manually; MintTweaks will not overwrite them."))
        return Availability(candidate=_("Latest official release from GitHub"))
    except Exception as exc:
        return Availability(error=str(exc))


@dataclass(frozen=True)
class ZenPlan:
    script: str
    digest: str
    destinations: tuple
    arch: str


def preview(runner):
    arch = architecture(runner)
    status = check_status(runner, arch)
    if not status.installable:
        raise SoftwareError(status.error or _("Zen is already installed."))
    script = read_command(runner, cmd("curl", "--fail", "--silent", "--show-error",
        "--proto", "=https", "--max-time", "30", INSTALLER_URL), timeout=40).stdout
    if not script.startswith("#!/bin/bash\n") or len(script.encode("utf-8")) > 256 * 1024:
        raise SoftwareError(_("The official Zen installer could not be read."))
    return ZenPlan(script, hashlib.sha256(script.encode("utf-8")).hexdigest(), targets(), arch)


def install(runner, plan, on_line=None):
    if runner.dry_run:
        return InstallOutcome(True, _("Simulation: no software was installed."))
    arch = architecture(runner)
    status = check_status(runner, arch)
    if (not status.installable or plan.arch != arch or plan.destinations != targets()
            or hashlib.sha256(plan.script.encode("utf-8")).hexdigest() != plan.digest):
        raise SoftwareError(status.error or _("The installation plan changed. Review a new preview before continuing."))
    # Execute exactly the bytes presented for approval, never a pipe to a shell.
    with tempfile.TemporaryDirectory(prefix="minttweaks-zen-") as temporary:
        script = Path(temporary) / "install.sh"
        script.write_text(plan.script, encoding="utf-8")
        result = runner.stream(cmd("bash", str(script)), on_line=on_line)
    try:
        version = installed_version()
    except (OSError, configparser.Error):
        version = ""
    ok = result.ok and bool(version)
    message = (_("Zen was installed for the current user. Updates are managed by Zen.") if ok else
               _("Zen installation failed or could not be verified. Check the log and installation files before trying again."))
    return InstallOutcome(ok, message, result)
