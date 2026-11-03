"""Official-repository application checks, reviewed APT plans and installation."""
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .catalog import CATALOG
from . import fonts
from ...core.runner import cmd, read_command
from ...i18n import _
from ..software.backend import Availability, InstallOutcome, VERSION_RE, apt_command, package_state

PACKAGE_RE = re.compile(r'^[a-z0-9][a-z0-9+.-]+$')
SPEC_RE = re.compile(r'^[a-z0-9][a-z0-9+.-]+(?::[a-z0-9][a-z0-9-]*)?(?:=[0-9][0-9A-Za-z.+:~\-]*)?$')
PROBE = Path(__file__).with_name('_apt_probe.py')


def catalog():
    result = {}
    packages = set()
    for app in CATALOG:
        if (not PACKAGE_RE.fullmatch(app.id) or not PACKAGE_RE.fullmatch(app.package) or
                any(not PACKAGE_RE.fullmatch(item) for item in app.alternatives) or
                app.id in result or app.package in packages or not app.name.strip() or not app.category.strip()):
            raise ValueError(_("Invalid or duplicate application catalog entry."))
        result[app.id] = app
        packages.add(app.package)
    return result


def selected_apps(ids):
    apps = catalog()
    if not ids or len(set(ids)) != len(ids) or any(key not in apps for key in ids):
        raise ValueError(_("Select applications from your catalog only."))
    return [apps[key] for key in ids]


def probe(runner, requests):
    if not requests or any(not SPEC_RE.fullmatch(request) for request in requests):
        raise ValueError(_("Invalid application package request."))
    result = read_command(runner, cmd('/usr/bin/python3', '-I', str(PROBE), *requests), timeout=120)
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict) or set(payload) != set(requests):
        raise ValueError(_("Official repository information could not be verified."))
    return payload


def checked_version(info):
    if info.get('error'):
        raise ValueError(_("Official source unavailable: {error}").format(error=info['error']))
    if not VERSION_RE.fullmatch(info.get('version', '')) or not info.get('origins'):
        raise ValueError(_("Official repository information could not be verified."))
    return info['version']


@dataclass
class ApplicationStatus(Availability):
    package: str = ''
    github_available: bool = False
    github_installed: bool = False
    origins: tuple = ()


def collect_status(runner):
    apps = catalog()
    if not apps:
        return {}
    result, missing = {}, []
    for key, app in apps.items():
        status = ApplicationStatus(package=app.package)
        try:
            for package in (app.package, *app.alternatives):
                state = package_state(runner, package)
                if state.installed:
                    status.installed, status.installed_version, status.package = True, state.version, package
                    break
            if not status.installed and app.package in fonts.RECIPES and not runner.dry_run:
                version = fonts.installed_version(app.package)
                if version:
                    status.installed, status.github_installed, status.installed_version = True, True, version
            if not status.installed:
                missing.extend((app.package, *app.alternatives))
        except Exception as exc:
            status.error = str(exc)
        result[key] = status
    if missing:
        try:
            metadata = probe(runner, missing)
        except Exception as exc:
            metadata = {package: {'error': str(exc)} for package in missing}
        for key, app in apps.items():
            if not result[key].installed and not result[key].error:
                try:
                    candidates = (app.package, *app.alternatives)
                    for package in candidates:
                        info = metadata[package]
                        if info.get('reason') == 'missing':
                            continue
                        result[key].candidate = checked_version(info)
                        result[key].origins = tuple(info['origins'])
                        result[key].package = package
                        break
                    else:
                        if app.package in fonts.RECIPES:
                            result[key].github_available = True
                        else:
                            checked_version(metadata[app.package])
                except Exception as exc:
                    result[key].error = str(exc)
    return result


@dataclass(frozen=True)
class InstallPlan:
    ids: tuple
    specs: tuple
    operations: tuple
    sources: tuple
    output: str


def preview_install(runner, ids):
    apps = selected_apps(ids)
    status = collect_status(runner)
    for app in apps:
        if not status[app.id].installable:
            raise ValueError(status[app.id].error or _("This package is already installed: {name}").format(name=app.name))
    specs = tuple(status[app.id].package + '=' + status[app.id].candidate for app in apps)
    result = read_command(runner, apt_command(specs, simulate=True), timeout=120)
    operations = tuple(sorted(line.strip() for line in result.stdout.splitlines() if line.startswith(('Inst ', 'Conf ', 'Remv ', 'Purg '))))
    if any(line.startswith(('Remv ', 'Purg ')) for line in operations):
        raise ValueError(_("APT proposed removals. Installation was refused."))
    requests = []
    for line in operations:
        if not line.startswith('Inst '):
            continue
        match = re.fullmatch(r'Inst (\S+)(?: \[[^\]]+\])? \(([^\s()]+)(?:\s.*)?\)', line)
        if not match:
            raise ValueError(_("The complete installation plan could not be read."))
        requests.append(match[1] + '=' + match[2])
    installed = {request.split('=', 1)[0].split(':', 1)[0] for request in requests}
    if not {status[app.id].package for app in apps} <= installed:
        raise ValueError(_("The complete installation plan could not be read."))
    metadata = probe(runner, list(dict.fromkeys(requests)))
    sources = []
    for request in sorted(metadata):
        checked_version(metadata[request])
        sources.append((request, tuple(metadata[request]['origins'])))
    return InstallPlan(tuple(ids), specs, operations, tuple(sources), result.output)


def install(runner, plan, on_line=None):
    apps = selected_apps(plan.ids)
    if runner.dry_run:
        return InstallOutcome(True, _("Simulation: no applications were installed."))
    checked = preview_install(runner, plan.ids)
    if (checked.specs, checked.operations, checked.sources) != (plan.specs, plan.operations, plan.sources):
        raise ValueError(_("The installation plan changed. Review a new preview before continuing."))
    result = runner.stream(apt_command(checked.specs), on_line=on_line)
    errors = {}
    for app, spec in zip(apps, checked.specs):
        try:
            state = package_state(runner, spec.split('=', 1)[0])
            if not state.installed or state.version != spec.split('=', 1)[1]:
                raise ValueError(_("The requested package version was not verified after installation."))
        except Exception as exc:
            errors[app.id] = str(exc)
    ok = result.ok and not errors
    message = (_("The selected applications were installed and their versions verified.") if ok else
               _("Application installation failed or could not be fully verified. Check the package state before retrying."))
    return InstallOutcome(ok, message, result, errors)
