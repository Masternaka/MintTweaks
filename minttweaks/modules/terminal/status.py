"""Read-only integration inspection. Never claim an existing shell has reloaded."""
from dataclasses import dataclass
import re
from ...core import userfiles
from ...i18n import _
from . import backend, integrations


@dataclass(frozen=True)
class Status:
    code: str
    detail: str


def collect(runner, states, home=None):
    result = {}
    mapping = backend.targets(home)
    for shell in backend.SHELLS:
        result[shell] = {}
        try:
            slot = {'bash': 'bashrc', 'zsh': 'zshrc', 'fish': 'fishrc'}[shell]
            text = (userfiles.read_file(mapping[slot])[0] or b'').decode('utf-8')
            clean = text
            for tool in integrations.INTEGRATIONS:
                if tool != 'starship':
                    clean = integrations.strip_block(clean, tool)
            clean = integrations.strip_block(clean, 'customization')
            customization_error = ''
            personal = None
            if integrations.markers('customization')[0] in text:
                from . import configuration
                data = configuration.load(home)['shells'].get(shell)
                personal = data
                actual = userfiles.read_file(mapping['settings-' + shell])[0]
                expected = configuration.environment(shell, data['settings'], data['aliases'], mapping) if data else None
                if actual is None or actual != expected:
                    customization_error = _('The managed settings file is missing or modified; review the configuration.')
            # Remove and validate the special historic Starship block as well.
            if text.count(backend.START) != text.count(backend.END) or text.count(backend.START) > 1:
                raise ValueError('Malformed Starship markers.')
            if backend.START in clean:
                pattern = r'^' + re.escape(backend.START) + r'\n.*?^' + re.escape(backend.END) + r'(?:\n|$)'
                if not re.search(pattern, clean, re.MULTILINE | re.DOTALL):
                    raise ValueError('Malformed Starship block.')
                clean = re.sub(pattern, '', clean, flags=re.MULTILINE | re.DOTALL)
            for tool, state in states.items():
                if state.error:
                    value = Status('unknown', state.error)
                elif not state.installed:
                    value = Status('absent', _('Not installed.'))
                elif tool not in integrations.INTEGRATIONS:
                    if personal and tool in personal['settings']:
                        personal_error = customization_error
                        if not state.binary:
                            personal_error = 'The executable is unavailable in PATH.'
                        if tool == 'tmux' and userfiles.read_file(mapping['tmux'])[0] != configuration.tmux_config(personal['settings']['tmux']):
                            personal_error = _('The managed settings file is missing or modified; review the configuration.')
                        value = (Status('review', personal_error) if personal_error else
                                 Status('configured', _('Personal settings configured; verify in a new terminal.')))
                    else:
                        value = Status('default', _('Installed; works with its default configuration.'))
                elif tool in integrations.ONLY and integrations.ONLY[tool] != shell:
                    value = Status('unsupported', _('This integration does not apply to this shell.'))
                elif (backend.START if tool == 'starship' else integrations.markers(tool)[0]) in text:
                    try:
                        if customization_error:
                            raise ValueError(customization_error)
                        if backend.TOOL_BY_ID[tool].binaries and not state.binary:
                            raise ValueError('Installed executable unavailable in PATH.')
                        if tool != 'starship':
                            expected = integrations.block(tool, shell, integrations.hook(runner, tool, shell))
                            if expected not in text:
                                raise ValueError(_('The managed block differs from the expected integration. Review it before updating.'))
                        else:
                            from .configuration import current_starship
                            config = userfiles.read_file(mapping['starship'])[0]
                            if config != current_starship(home) or 'starship init ' + shell not in text or integrations.quote(mapping['starship'], shell) not in text:
                                raise ValueError('The managed Starship configuration is incomplete.')
                        value = Status('configured', _('Configured; verify in a new terminal.'))
                    except Exception as exc:
                        value = Status('review', str(exc))
                elif integrations.manual_hook(clean, tool):
                    value = Status('manual', _('Manual integration detected; not managed here.'))
                else:
                    value = Status('unconfigured', _('Installed; integration not configured for this shell.'))
                result[shell][tool] = value
        except Exception as exc:
            result[shell] = {tool: Status('unknown', str(exc)) for tool in states}
    return result


def matches(entry, state, integration, query='', mode='all', shell='bash'):
    haystack = ' '.join((entry.name, entry.package, entry.id, _(entry.description), entry.category)).casefold()
    if query and query.strip().casefold() not in haystack:
        return False
    if mode == 'installed':
        return bool(state and state.installed)
    if mode == 'available':
        return bool(state and state.candidate and not state.installed and not state.error)
    if mode == 'configurable':
        return entry.id in integrations.INTEGRATIONS and (entry.id not in integrations.ONLY or integrations.ONLY[entry.id] == shell)
    return True
