"""Optional read-only evidence. Never complete a checklist step automatically."""
from __future__ import annotations

import datetime
import shutil
from dataclasses import dataclass

from ...core import paths, userfiles
from ...core.runner import cmd, read_command
from ...i18n import _
from ..cinnamon import backend as cinnamon
from ..firefox import backend as firefox
from ..home import backend as home
from ..samba import backend as samba
from ..software import backend as software
from ..terminal import backend as terminal, configuration
from . import backend


@dataclass(frozen=True)
class Item:
    title: str
    state: str
    detail: str


@dataclass(frozen=True)
class Observation:
    step_id: str
    checked_at: str
    items: tuple
    limitation: str


def _attempt(title, work):
    try:
        return work()
    except Exception:
        # Exception strings can include configuration contents or private paths.
        # The original module remains the place for full local diagnostics.
        return Item(title, 'unavailable', _("This observation could not be read. Open the original module for diagnostics."))


def _package(runner, name):
    state = software.package_state(runner, name)
    return Item(name, 'detected' if state.installed else 'not_detected',
                _("Installed Debian version: {version}").format(version=state.version) if state.installed else
                _("This Debian package was not detected. It may be optional or installed in another format."))


def _health(runner):
    report = home.collect_report(runner)
    return tuple(Item(finding.title,
                      'unavailable' if not finding.completed else 'detected' if finding.severity == 'ok' else 'attention',
                      _("The check returned without a reported problem.") if finding.completed and finding.severity == 'ok' else
                      _("Review this check in the Home module; no automatic correction was performed."))
                 for finding in report.findings)


def _software(runner):
    status = software.collect_status(runner)
    items = []
    for app in software.CATALOG:
        entry = status[app.id]
        if entry.installation_method == 'legacy-deb':
            items.append(Item(app.name, 'attention', _("Legacy Debian package detected: {version}. Review the transition in Native software.").format(version=entry.installed_version)))
        elif entry.error:
            items.append(Item(app.name, 'unavailable', _("The browser state could not be verified. Re-analyse it in Native software.")))
        else:
            items.append(Item(app.name, 'detected' if entry.installed else 'not_detected',
                _("Detected version: {version}").format(version=entry.installed_version) if entry.installed else
                _("No installation was detected by this catalog. Installing every listed browser is not required.")))
    return tuple(items)


def _terminal(runner):
    def account():
        _username, shell = terminal.current_account()
        return Item(_("Login shell"), 'detected', shell)
    def preferences():
        data = configuration.load()
        count = len(data['shells']) + len(data['terminals'])
        return Item(_("Saved terminal preferences"), 'detected' if count else 'not_detected',
                    _("{count} saved shell or terminal configuration(s). Their effective loading was not checked.").format(count=count))
    items = [_attempt(_("Login shell"), account), _attempt(_("Saved terminal preferences"), preferences)]
    for name in ('bash', 'zsh', 'fish', 'kitty', 'alacritty'):
        items.append(_attempt(name, lambda name=name: _package(runner, name)))
    return tuple(items)


def _firefox(_runner):
    def policy():
        document, error = firefox.load_policy()
        if error:
            raise ValueError('Policy unavailable')
        count = len(firefox.policy_extension_ids(document))
        return Item(_("Firefox extension policy"), 'detected' if count else 'not_detected',
                    _("{count} catalog extension(s) configured in the system policy. Browser loading was not checked.").format(count=count))
    binary = bool(shutil.which('firefox'))
    return (Item(_("Firefox executable in PATH"), 'detected' if binary else 'not_detected',
                 _("This only checks for a native executable; it does not launch Firefox or inspect Flatpak.")),
            _attempt(_("Firefox extension policy"), policy))


def _cinnamon(runner):
    def settings():
        snapshot = cinnamon.capture(runner)
        return Item(_("Current appearance settings"), 'detected' if snapshot.complete else 'unavailable',
                    _("{read} of {total} appearance setting(s) read. No profile was applied or compared.").format(
                        read=len(snapshot.values), total=len(cinnamon.SETTINGS)))
    def profiles():
        catalog = cinnamon.list_profiles()
        if catalog.errors:
            return Item(_("Saved Cinnamon profiles"), 'unavailable', _("Some saved profiles could not be read. Existing files were preserved."))
        return Item(_("Saved Cinnamon profiles"), 'detected' if catalog.profiles else 'not_detected',
                    _("{count} saved profile(s). Their presence does not mean one is currently applied.").format(count=len(catalog.profiles)))
    return (_attempt(_("Current appearance settings"), settings), _attempt(_("Saved Cinnamon profiles"), profiles))


def _samba(runner):
    def service():
        text = read_command(runner, cmd('systemctl', 'show', 'smbd.service', '--no-pager',
                            '--property=LoadState,ActiveState'), timeout=15).stdout
        values = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        if values.get('LoadState') == 'not-found':
            return Item('smbd.service', 'not_detected', _("The Samba service was not found."))
        if values.get('LoadState') != 'loaded' or values.get('ActiveState') not in {'active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading'}:
            raise ValueError('Service state unavailable')
        active = values['ActiveState']
        return Item('smbd.service', 'detected' if active == 'active' else 'attention',
                    _("Reported service state: {state}. Network access was not tested.").format(state=active))
    def shares():
        raw, _mode = userfiles.read_file(paths.SMB_CONF)
        if raw is None:
            return Item(_("Samba configuration"), 'not_detected', _("No Samba configuration file was found."))
        configuration = samba.SmbConf.parse(raw.decode('utf-8'))
        count = len(samba.list_shares(configuration))
        return Item(_("Samba configuration"), 'detected' if count else 'not_detected',
                    _("{count} share definition(s) read. Permissions and testparm validation were not checked.").format(count=count))
    return (_attempt('samba', lambda: _package(runner, 'samba')),
            _attempt('smbd.service', service), _attempt(_("Samba configuration"), shares))


LIMITATIONS = {
    'health': _("These are current diagnostics, not a guarantee that the system has no other problems."),
    'software': _("Package or user-installation detection does not verify download origin, browser startup or updates. Confirm the browsers you chose manually."),
    'terminal': _("Saved preferences and package presence do not prove that integrations are loaded. Verify them in a new shell or terminal."),
    'firefox': _("A configured policy does not prove extensions are installed, enabled or loaded in Firefox. Restart Firefox and check there."),
    'cinnamon': _("Readable settings and saved profiles do not verify the visual result. Confirm the appearance in your Cinnamon session."),
    'samba': _("This check does not request administrator authorization. Verify accounts, firewall, permissions and client access separately in Samba."),
}


def collect(runner, step_id):
    if step_id not in backend.STEP_BY_ID:
        raise ValueError('Unknown preparation step')
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if runner.dry_run:
        return Observation(step_id, checked_at,
            (Item(backend.STEP_BY_ID[step_id].title, 'unavailable', _("Automatic observations are unavailable in simulation mode.")),),
            _(LIMITATIONS[step_id]))
    inspectors = {'health': _health, 'software': _software, 'terminal': _terminal,
                  'firefox': _firefox, 'cinnamon': _cinnamon, 'samba': _samba}
    try:
        items = inspectors[step_id](runner)
    except Exception:
        items = (Item(backend.STEP_BY_ID[step_id].title, 'unavailable',
                      _("This observation could not be read. Open the original module for diagnostics.")),)
    return Observation(step_id, checked_at, tuple(items), _(LIMITATIONS[step_id]))
