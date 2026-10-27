"""Install a small allowlist of native third-party browser packages.

Repositories must already be configured. No repository, key or download script
is added implicitly. All candidate versions are checked against their source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ...core.runner import BaseRunner, Result, cmd, read_command
from ...i18n import _


@dataclass(frozen=True)
class Application:
    id: str
    name: str
    package: str
    origin: str
    architectures: Tuple[str, ...]
    source_msgid: str
    guide: str
    suite: str = "stable/main"

    @property
    def source(self):
        return _(self.source_msgid)


CENTRAL = "https://masternaka.github.io/masternaka-repository/"
CATALOG = (
    Application("helium", "Helium Browser", "helium-bin", "https://pkg.helium.computer/deb/", ("amd64", "arm64"),
                _("Helium's official stable APT repository."),
                "https://github.com/imputnet/helium-linux#debianubuntu"),
    Application("brave", "Brave Browser", "brave-browser", "https://brave-browser-apt-release.s3.brave.com/", ("amd64", "arm64"),
                _("Brave's official stable APT repository."), "https://brave.com/linux/"),
    Application("zen", "Zen Browser", "zen-browser", CENTRAL, ("amd64",),
                _("Unofficial Debian package built from Zen's official archive by the Masternaka APT repository."),
                "https://github.com/Masternaka/masternaka-repository#installation-sur-linux-mint", suite="./"),
)
APP_BY_ID = {app.id: app for app in CATALOG}
VERSION_RE = re.compile(r"^[0-9][0-9A-Za-z.+:~\-]*$")


class SoftwareError(ValueError):
    pass


@dataclass
class PackageState:
    installed: bool
    version: str = ""


@dataclass
class Availability:
    installed: bool = False
    installed_version: str = ""
    candidate: str = ""
    error: str = ""

    @property
    def installable(self):
        return bool(not self.installed and self.candidate and not self.error)


def package_state(runner: BaseRunner, package: str) -> PackageState:
    if runner.dry_run:
        raise SoftwareError(_("Software availability is not checked in simulation mode."))
    result = runner.run(cmd("dpkg-query", "-W", "-f=${Status}\t${Version}\n", package), timeout=15)
    if result.returncode == 1 and not result.stdout.strip() and re.search(
        r"^dpkg-query: no packages found matching " + re.escape(package) + r"\s*$", result.stderr.strip()
    ):
        return PackageState(False)
    if not result.ok:
        raise SoftwareError(result.output or "Could not read package state.")
    fields = result.stdout.strip().split("\t")
    if len(fields) != 2:
        raise SoftwareError("Invalid package state output.")
    status, version = fields
    if status.split()[1:] == ["ok", "installed"]:
        return PackageState(True, version)
    if status.split()[-1:] in (["not-installed"], ["config-files"]):
        return PackageState(False)
    raise SoftwareError(_("This package has an incomplete state. Check it in Maintenance first."))


def parse_candidate(text: str, expected_origin: str, expected_suite: str = "stable/main") -> str:
    candidate = ""
    current = ""
    origins = set()
    for line in text.splitlines():
        match = re.match(r"\s*Candidate:\s*(\S+)\s*$", line)
        if match:
            candidate = match[1]
            continue
        version = re.match(r"\s*(?:\*\*\*\s+)?(\S+)\s+-?\d+\s*$", line)
        if version:
            current = version[1]
            continue
        source = re.match(r"\s*-?\d+\s+(\S+)\s+(\S+)\s+.*\bPackages\s*$", line)
        if not source:
            source = re.match(r"\s*-?\d+\s+(\S+)\s+(\S+)\s+Packages\s*$", line)
        if source and current == candidate:
            origins.add((source[1].rstrip("/") + "/", source[2]))
    if not VERSION_RE.fullmatch(candidate) or origins != {(expected_origin.rstrip("/") + "/", expected_suite)}:
        raise SoftwareError(_("No unambiguous candidate from the expected repository. Configure its source and refresh APT metadata first."))
    return candidate


def architecture(runner: BaseRunner) -> str:
    return read_command(runner, cmd("dpkg", "--print-architecture"), timeout=10).stdout.strip()


def check_application(runner: BaseRunner, app: Application, arch: str) -> Availability:
    status = Availability()
    try:
        package = package_state(runner, app.package)
        status.installed, status.installed_version = package.installed, package.version
        if package.installed:
            return status
        if arch not in app.architectures:
            raise SoftwareError(_("This source has no supported package for architecture {architecture}.").format(architecture=arch))
        policy = read_command(runner, cmd("apt-cache", "policy", app.package + ":" + arch), timeout=15)
        status.candidate = parse_candidate(policy.stdout, app.origin, app.suite)
    except Exception as exc:
        status.error = str(exc)
    return status


def collect_status(runner: BaseRunner) -> Dict[str, Availability]:
    try:
        arch = architecture(runner)
    except Exception as exc:
        return {app.id: Availability(error=str(exc)) for app in CATALOG}
    return {app.id: check_application(runner, app, arch) for app in CATALOG}


def selected_apps(ids) -> List[Application]:
    if not ids or any(not isinstance(key, str) or key not in APP_BY_ID for key in ids):
        raise SoftwareError("Select applications from the catalog only.")
    if len(set(ids)) != len(ids):
        raise SoftwareError("Duplicate application selection.")
    return [APP_BY_ID[key] for key in ids]


def apt_command(specs, simulate=False):
    flags = ("-s",) if simulate else ("-y",)
    return cmd("apt-get", *flags, "--no-remove", "--no-install-recommends", "install", "--", *specs, root=not simulate)


@dataclass(frozen=True)
class InstallPlan:
    ids: tuple
    specs: tuple
    arch: str
    operations: tuple
    output: str


def preview_install(runner: BaseRunner, ids) -> InstallPlan:
    apps = selected_apps(ids)
    arch = architecture(runner)
    specs = []
    for app in apps:
        status = check_application(runner, app, arch)
        if not status.installable:
            raise SoftwareError(status.error or _("This package is already installed: {name}").format(name=app.name))
        specs.append(app.package + ":" + arch + "=" + status.candidate)
    result = read_command(runner, apt_command(specs, simulate=True), timeout=120)
    operations = tuple(sorted(line.strip() for line in result.stdout.splitlines() if line.startswith(("Inst ", "Conf ", "Remv ", "Purg "))))
    if any(line.startswith(("Remv ", "Purg ")) for line in operations):
        raise SoftwareError(_("APT proposed removals. Installation was refused."))
    installed = {line.split()[1].split(":")[0] for line in operations if line.startswith("Inst ")}
    if not {app.package for app in apps} <= installed:
        raise SoftwareError(_("The complete installation plan could not be read."))
    return InstallPlan(tuple(app.id for app in apps), tuple(specs), arch, operations, result.output)


@dataclass
class InstallOutcome:
    ok: bool
    message: str
    result: Result = None
    states: Dict[str, str] = field(default_factory=dict)


def install(runner: BaseRunner, plan: InstallPlan, on_line=None) -> InstallOutcome:
    selected_apps(plan.ids)
    if runner.dry_run:
        return InstallOutcome(True, _("Simulation: no software was installed."))
    checked = preview_install(runner, plan.ids)
    if (checked.specs, checked.arch, checked.operations) != (plan.specs, plan.arch, plan.operations):
        raise SoftwareError(_("The installation plan changed. Review a new preview before continuing."))
    result = runner.stream(apt_command(checked.specs), on_line=on_line)
    states = {}
    for key, spec in zip(checked.ids, checked.specs):
        try:
            status = package_state(runner, APP_BY_ID[key].package)
            if not status.installed or status.version != spec.split("=", 1)[1]:
                raise SoftwareError(_("The requested package version was not verified after installation."))
        except Exception as exc:
            states[key] = str(exc)
    ok = result.ok and not states
    message = (_("The selected packages were installed and their versions verified.") if ok else
               _("Installation failed or could not be fully verified. Check the package state; no automatic removal was performed."))
    return InstallOutcome(ok, message, result, states)
