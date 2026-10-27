"""Portable declarations only: no exported startup scripts, paths or history."""
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from ...core import userfiles
from ...i18n import _
from . import backend, configuration, integrations


@dataclass(frozen=True)
class Request:
    document: dict
    packages: object
    notes: tuple


def validate(value):
    keys = {'format', 'schema_version', 'tools', 'integrations', 'preferences'}
    if (not isinstance(value, dict) or set(value) != keys or value['format'] != 'minttweaks-terminal'
            or type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise ValueError('Unsupported terminal export format.')
    tools, hooks = value['tools'], value['integrations']
    if (not isinstance(tools, list) or any(not isinstance(tool, str) or tool not in backend.TOOLS for tool in tools)
            or len(tools) != len(set(tools))):
        raise ValueError('Unknown or duplicate exported tools.')
    if not isinstance(hooks, dict) or not set(hooks) <= set(backend.SHELLS):
        raise ValueError('Unknown exported shell.')
    for shell, selected in hooks.items():
        if (not isinstance(selected, list) or any(not isinstance(tool, str) or tool not in integrations.INTEGRATIONS for tool in selected)
                or len(selected) != len(set(selected)) or not set(selected) <= set(tools)
                or (selected and shell not in tools)
                or any(tool in integrations.ONLY and integrations.ONLY[tool] != shell for tool in selected)):
            raise ValueError('Invalid exported integrations.')
    preferences = configuration.validate_preferences(value['preferences'])
    if not set(preferences['terminals']) <= set(tools):
        raise ValueError('Exported terminal dependencies are missing.')
    for shell, data in preferences['shells'].items():
        if shell not in tools or not set(data['settings']) <= set(tools):
            raise ValueError('Exported configuration dependencies are missing.')
    return copy.deepcopy(value)


def read(path):
    raw = userfiles.read_file(Path(path))[0]
    if raw is None:
        raise ValueError('Export file not found.')
    return validate(json.loads(raw, object_pairs_hook=configuration.unique_object))


def export_document(states, inspection, selected=(), home=None):
    preferences = configuration.load(home)
    tools = {tool for tool, state in states.items() if state.installed} | set(selected)
    if not tools <= set(backend.TOOLS):
        raise ValueError('Unknown exported tool.')
    hooks = {}
    for shell, values in inspection.items():
        managed = [tool for tool, value in values.items() if value.code == 'configured' and tool in integrations.INTEGRATIONS]
        if managed:
            hooks[shell] = managed
            tools.add(shell)
            tools.update(managed)
    for shell, data in preferences['shells'].items():
        tools.add(shell)
        tools.update(data['settings'])
    tools.update(preferences['terminals'])
    return validate({'format': 'minttweaks-terminal', 'schema_version': 1, 'tools': sorted(tools),
                     'integrations': hooks, 'preferences': preferences})


def write(runner, path, document):
    if runner.dry_run:
        return userfiles.FileOutcome(True, simulated=True)
    validate(document)
    path = Path(path)
    # Never silently overwrite an existing file or link selected from a chooser.
    path.parent.mkdir(parents=True, exist_ok=True)
    import os
    data = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    if len(data) > userfiles.MAX_FILE:
        raise ValueError('Export is too large.')
    try:
        with path.open('xb') as output:
            os.chmod(path, 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        raise ValueError(_('Choose a new export filename; existing files are preserved.'))
    return userfiles.FileOutcome(True)


def inspect(runner, document):
    document = validate(document)
    missing, notes = [], []
    terminals = configuration.validate_preferences(document['preferences'])['terminals']
    available_fonts = backend.fonts(runner) if terminals else []
    for data in terminals.values():
        if data['family'] not in available_fonts:
            raise ValueError(_('Install this imported font before retrying: {font}').format(font=data['family']))
    for tool in document['tools']:
        state = backend.tool_state(runner, tool)
        if not state.installed:
            if not state.candidate or state.error:
                raise ValueError(_('This imported tool is unavailable in the configured APT sources: {tool}').format(tool=tool))
            missing.append(tool)
    if missing:
        notes.append(_('Install the missing tools first; configuration gets a separate preview afterwards.'))
    notes.append(_('Import merges your managed choices. It does not change the login shell or remove other tools.'))
    return Request(document, backend.preview_install(runner, missing) if missing else None, tuple(notes))


def preview_configuration(runner, document, home=None):
    document = validate(document)
    # Build plans using this machine's binaries and package scripts.
    updates, notes = {}, []
    for shell, tools in document['integrations'].items():
        if tools:
            plan = integrations.preview(runner, shell, tools, home=home)
            for change in plan.changes:
                updates[change.slot] = change.after
            notes.extend(plan.notes)
    prefs = copy.deepcopy(configuration.load(home))
    imported = document['preferences']['shells']
    terminals = configuration.validate_preferences(document['preferences'])['terminals']
    prefs['terminals'].update(terminals)
    for shell, data in imported.items():
        current = prefs['shells'].setdefault(shell, {'settings': {}, 'aliases': {}})
        current['settings'].update(data['settings'])
        current['aliases'].update(data['aliases'])
        for shared in ('starship', 'tmux'):
            if shared in data['settings']:
                for other in prefs['shells'].values():
                    if shared in other['settings']:
                        other['settings'][shared] = dict(data['settings'][shared])
    if imported or terminals:
        plan = configuration.changes_for_preferences(runner, prefs, list(imported), home)
        # Both plans started from the same source files. Merge owned blocks only,
        # preserving the hooks imported above and putting settings first.
        for change in plan.changes:
            if change.slot in ('bashrc', 'zshrc', 'fishrc') and change.slot in updates:
                settings_rc = change.after.decode('utf-8')
                combined = updates[change.slot].decode('utf-8')
                start, end = integrations.markers('customization')
                combined = integrations.strip_block(combined, 'customization')
                if start in settings_rc:
                    block = settings_rc[:settings_rc.index(end) + len(end)] + '\n'
                    combined = block + combined
                # Add any newly requested setting hooks not in imported hooks.
                import re
                for tool in integrations.INTEGRATIONS:
                    if tool == 'starship':
                        a, b = backend.START, backend.END
                    else:
                        a, b = integrations.markers(tool)
                    pattern = re.compile(r'^' + re.escape(a) + r'\n.*?^' + re.escape(b) + r'(?:\n|$)', re.MULTILINE | re.DOTALL)
                    match = pattern.search(settings_rc)
                    if match and a not in combined:
                        combined += match.group()
                updates[change.slot] = combined.encode('utf-8')
            else:
                updates[change.slot] = change.after
        notes.extend(plan.notes)
    for terminal, data in terminals.items():
        changes = backend.terminal_preview(runner, terminal, data['palette'], data['family'], data['size'], home, persist=False)
        updates.update({change.slot: change.after for change in changes})
    # Highlighting must remain after all imported widgets in Zsh.
    if 'zshrc' in updates:
        import re
        a, b = integrations.markers('zsh-syntax-highlighting')
        pattern = re.compile(r'^' + re.escape(a) + r'\n.*?^' + re.escape(b) + r'(?:\n|$)', re.MULTILINE | re.DOTALL)
        text = updates['zshrc'].decode('utf-8')
        match = pattern.search(text)
        if match:
            text = pattern.sub('', text, count=1) + match.group()
            updates['zshrc'] = text.encode('utf-8')
    changes = userfiles.preview(backend.targets(home), updates) if updates else []
    return configuration.ConfigurationPlan(tuple(changes), tuple(dict.fromkeys(notes)))


def apply_configuration(runner, document, plan, home=None):
    if runner.dry_run:
        return userfiles.FileOutcome(True, simulated=True)
    fresh = preview_configuration(runner, document, home)
    if fresh.changes != plan.changes:
        raise ValueError(_('The imported configuration plan changed. Review a new preview.'))
    from ...core import paths
    return userfiles.apply(runner, backend.targets(home), plan.changes, paths.TERMINAL_BACKUP_DIR / 'files')
