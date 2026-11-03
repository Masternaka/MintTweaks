"""Previewable diagnostic export from an explicit set of local observations."""

from __future__ import annotations

import datetime
import getpass
import ipaddress
import os
from pathlib import Path
import platform
import re
import socket
import tempfile
from dataclasses import dataclass

from ... import __version__
from ...core.runner import cmd
from ...i18n import _
from . import backend

MAX_REPORT_BYTES = 128 * 1024
HISTORY_LIMIT = 20
MODULES = {'home', 'maintenance', 'services', 'samba', 'firefox', 'cinnamon',
           'setup', 'applications', 'software', 'terminal', 'dotfiles', 'history'}
RESULTS = {'running', 'completed', 'failed', 'simulation', 'unknown', 'interface_error'}


class Redactor:
    def __init__(self, identifiers):
        self.identifiers = sorted({value for value in identifiers if value}, key=len, reverse=True)

    @classmethod
    def local(cls):
        identifiers = [str(Path.home())]
        for read in (getpass.getuser, socket.gethostname):
            try:
                identifiers.append(read())
            except (OSError, KeyError):
                pass
        return cls(identifiers)

    def text(self, value):
        text = str(value)[:2048]
        text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
        text = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
        # These fields should not contain credentials; suppress the remainder if
        # an unexpected source includes a credential assignment anyway.
        text = re.sub(r'(?i)\b(?:password|passwd|token|secret|api[_-]?key|authorization)\s*[:=].*', '[REDACTED]', text)
        text = re.sub(r'(?i)\bBearer\s+\S+', '[REDACTED]', text)
        text = re.sub(r'(?i)\b(?:https?|ftp|smb)://\S+', '[URL]', text)
        text = re.sub(r'\b[^\s@]+@[^\s@]+\.[^\s@]+', '[EMAIL]', text)
        text = re.sub(r'(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b', '[MAC]', text)
        # Validate numeric candidates: kernel/package versions such as 6.8.0-45
        # are useful and must remain intact.
        def address(match):
            try:
                ipaddress.ip_address(match[0].split('%', 1)[0])
            except ValueError:
                return match[0]
            return '[IP]'
        text = re.sub(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', address, text)
        text = re.sub(r'(?<![\w:])[0-9a-fA-F:]*:[0-9a-fA-F:]+(?:%[\w.-]+)?(?![\w:])', address, text)
        for identifier in self.identifiers:
            text = re.sub(r'(?<![^\W_])' + re.escape(identifier) + r'(?![^\W_])', '[IDENTITY]', text, flags=re.IGNORECASE)
        text = re.sub(r'(?<!\w)(?:~?/|\\\\)[^\s,;]+', '[PATH]', text)
        # Export remains safe to open in a Markdown renderer: source values
        # cannot introduce links, images, HTML or additional table rows.
        text = re.sub(r'([\\`*_{}\[\]()<>!|#])', r'\\\1', text)
        return text[:512]


@dataclass(frozen=True)
class DiagnosticReport:
    text: str
    created_at: str

    @property
    def filename(self):
        stamp = datetime.datetime.fromisoformat(self.created_at).strftime('%Y%m%d-%H%M%S')
        return 'minttweaks-diagnostic-' + stamp + '.md'


def _probe(runner, command, pattern):
    try:
        result = runner.run(command, timeout=10)
        value = result.stdout.strip()
        if result.ok and re.fullmatch(pattern, value):
            return value
    except Exception:
        pass
    return _("Unavailable")


def _finding_detail(finding, redactor):
    # Raw journal/command excerpts and names of failed services are excluded
    # before rendering, rather than relying on regex to find every secret.
    values = {key: value for key, value in finding.values.items()
              if key not in {'sample', 'names'}}
    for key in ('sample', 'names'):
        if key in finding.values:
            values[key] = _("Details omitted from the export")
    return redactor.text(_(finding.detail_msgid).format(**values))


def collect(runner, history=None, *, include_history=True):
    if runner.dry_run:
        raise ValueError(_("Diagnostic export is unavailable in simulation mode."))
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    observation = backend.collect_report(runner)
    redactor = Redactor.local()
    summary = observation.summary
    architecture = _probe(runner, cmd('dpkg', '--print-architecture'), r'[a-zA-Z0-9_-]{1,32}')
    cinnamon = _probe(runner, cmd('dpkg-query', '-W', '-f=${Version}', 'cinnamon'), r'[0-9][a-zA-Z0-9.+:~_-]{0,100}')
    session = os.environ.get('XDG_SESSION_TYPE', '')
    if session not in {'x11', 'wayland'}:
        session = _("Unavailable")
    lines = ['# ' + _("MintTweaks diagnostic report"), '',
             _("Collected at (UTC): {time}").format(time=created_at), '',
             _("Local snapshot. No application, service or configuration was changed during collection."),
             _("Host name, account name, backup paths, raw command output and journal excerpts are excluded. Review this report before sharing it."), '',
             '## ' + _("Environment"), '',
             '| ' + _("Item") + ' | ' + _("Value") + ' |', '| --- | --- |']
    fields = [(_("MintTweaks version"), __version__), (_("Python version"), platform.python_version()),
              (_("Operating system"), summary.os_name), (_("Kernel"), summary.kernel),
              (_("Architecture"), architecture), (_("Cinnamon package version"), cinnamon),
              (_("Session type"), session), (_("Uptime"), summary.uptime)]
    if summary.memory_measured:
        fields.append((_("Memory"), summary.memory_used + ' / ' + summary.memory_total))
    else:
        fields.append((_("Memory"), _("Unavailable")))
    if summary.disk_measured:
        fields.append((_("Disk usage"), str(summary.disk_percent) + '%'))
        fields.append((_("Free disk space"), summary.disk_free))
    else:
        fields.append((_("Disk usage"), _("Unavailable")))
    lines.extend('| ' + title + ' | ' + redactor.text(value) + ' |' for title, value in fields)
    lines += ['', '## ' + _("Diagnostic findings"), '',
              _("Errors: {errors}; warnings: {warnings}; passed: {passed}; unavailable: {unavailable}.").format(
                  errors=observation.errors, warnings=observation.warnings,
                  passed=observation.passed, unavailable=observation.unavailable), '']
    for finding in observation.findings:
        state = finding.severity if finding.completed else 'unavailable'
        lines.append('- ' + redactor.text(finding.title) + ' [' + state + ']: ' + _finding_detail(finding, redactor))
    lines += ['', '## ' + _("Recent operations"), '']
    if not include_history:
        lines.append(_("Operation history was excluded from this report."))
    elif history is None:
        lines.append(_("Operation history is unavailable."))
    else:
        try:
            entries = history.entries(limit=HISTORY_LIMIT)
            operation_lines = []
            for entry in entries[:HISTORY_LIMIT]:
                # Do not serialize the stored name, ID or backup paths: they can
                # contain user-defined service instances or personal locations.
                module = entry['module'] if entry['module'] in MODULES else 'other'
                status = entry['status'] if entry['status'] in RESULTS else 'unknown'
                start = datetime.datetime.fromisoformat(entry['started']).astimezone(datetime.timezone.utc).isoformat()
                simulated = 'simulation' if entry['simulated'] else 'real'
                operation_lines.append('- ' + start + ' | ' + module + ' | ' + status + ' | ' + simulated)
        except Exception:
            lines.append(_("Operation history could not be read. No history file was changed."))
        else:
            lines.extend(operation_lines or [_("No operation recorded.")])
    text = '\n'.join(lines) + '\n'
    if len(text.encode('utf-8')) > MAX_REPORT_BYTES:
        raise ValueError(_("The diagnostic report is too large."))
    return DiagnosticReport(text, created_at)


def save(runner, report, filename):
    if runner.dry_run:
        return _("Simulation: no diagnostic report was written.")
    raw = report.text.encode('utf-8')
    if not raw or len(raw) > MAX_REPORT_BYTES:
        raise ValueError(_("The diagnostic report is too large."))
    target = Path(filename).expanduser()
    if not target.is_absolute():
        raise ValueError(_("Choose an absolute path for the report."))
    # Publish complete reviewed bytes exclusively; never replace existing files
    # or follow a destination symlink, including a dangling one.
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.minttweaks-report-', delete=False) as output:
            staged = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(staged, target)
        except FileExistsError as exc:
            raise ValueError(_("This file already exists. Choose a new filename; no existing file was replaced.")) from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return _("Diagnostic report saved: {path}").format(path=target)
