"""Validated graphical settings and personal aliases, rendered as owned files."""
import copy
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ...core import paths, userfiles
from ...i18n import _
from . import backend, integrations

DEFAULTS = {
    'starship': {'git': True, 'newline': False, 'symbol': '>', 'color': 'green'},
    'fzf': {'height': 40, 'layout': 'reverse', 'color': 'dark', 'preview': False},
    'bat': {'theme': 'TwoDark', 'style': 'numbers,changes,header'},
    'eza': {'long': True, 'git': True, 'tree': False},
    'tmux': {'prefix': 'C-b', 'mouse': False, 'position': 'bottom'},
}
CHOICES = {
    ('starship', 'symbol'): ('>', '$', '❯'), ('starship', 'color'): ('green', 'blue', 'magenta'),
    ('fzf', 'layout'): ('default', 'reverse'), ('fzf', 'color'): ('dark', 'light', '16'),
    ('bat', 'theme'): ('TwoDark', 'GitHub'), ('bat', 'style'): ('numbers,changes,header', 'plain', 'full'),
    ('tmux', 'prefix'): ('C-b', 'C-a'), ('tmux', 'position'): ('bottom', 'top'),
}
RESERVED = {'if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'do', 'done', 'case', 'esac',
            'and', 'or', 'not', 'in', 'break', 'continue', 'until', 'select', 'time', 'coproc', 'repeat', 'foreach', 'exec',
            'function', 'end', 'switch', 'begin', 'return', 'exit', 'source', 'alias', 'unalias',
            'command', 'builtin', 'eval', 'set', 'export', 'bat', 'fd', 'z', 'zi', 'mtk-eza', 'mtk-tmux'}


@dataclass(frozen=True)
class ConfigurationPlan:
    changes: tuple
    notes: tuple
    shells: tuple = ()
    preferences: bytes = b''


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field.')
        result[key] = value
    return result


def validate_settings(value):
    if not isinstance(value, dict) or not set(value) <= set(DEFAULTS):
        raise ValueError('Unknown tool settings.')
    result = {}
    for tool, options in value.items():
        if not isinstance(options, dict) or set(options) != set(DEFAULTS[tool]):
            raise ValueError('Invalid tool settings.')
        for key, item in options.items():
            expected = DEFAULTS[tool][key]
            if type(item) is not type(expected):
                raise ValueError('Invalid setting type.')
            if (tool, key) in CHOICES and item not in CHOICES[tool, key]:
                raise ValueError('Unsupported setting choice.')
            if tool == 'fzf' and key == 'height' and not 10 <= item <= 100:
                raise ValueError('Invalid fzf height.')
        result[tool] = dict(options)
    return result


def validate_aliases(value):
    if not isinstance(value, dict) or len(value) > 64:
        raise ValueError('Invalid alias list.')
    for name, command in value.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,31}', name)
                or name in RESERVED or name.startswith('mtk-')):
            raise ValueError(_("This alias name is invalid or reserved: {name}").format(name=name))
        if (not isinstance(command, str) or not command.strip() or len(command) > 1024
                or any(unicodedata.category(char) == 'Cc' for char in command)):
            raise ValueError('Alias commands must be a single nonempty line (1024 characters maximum).')
    return dict(value)


def validate_preferences(value):
    if (not isinstance(value, dict) or not {'schema_version', 'shells'} <= set(value) or not set(value) <= {'schema_version', 'shells', 'terminals'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not isinstance(value['shells'], dict) or not set(value['shells']) <= set(backend.SHELLS)):
        raise ValueError('Unsupported terminal preferences.')
    result = {'schema_version': 1, 'shells': {}, 'terminals': {}}
    terminals = value.get('terminals', {})
    if not isinstance(terminals, dict) or not set(terminals) <= set(backend.TERMINALS):
        raise ValueError('Unknown terminal appearance settings.')
    for terminal, data in terminals.items():
        if (not isinstance(data, dict) or set(data) != {'palette', 'family', 'size'}
                or data['palette'] not in backend.PALETTES or type(data['size']) is not int or not 8 <= data['size'] <= 32
                or not isinstance(data['family'], str) or not 0 < len(data['family']) <= 100
                or any(unicodedata.category(char) == 'Cc' for char in data['family'])):
            raise ValueError('Invalid terminal appearance settings.')
        result['terminals'][terminal] = dict(data)
    for shell, data in value['shells'].items():
        if not isinstance(data, dict) or set(data) != {'settings', 'aliases'}:
            raise ValueError('Invalid shell preferences.')
        result['shells'][shell] = {'settings': validate_settings(data['settings']), 'aliases': validate_aliases(data['aliases'])}
    # Starship has one shared managed file. Different shell copies must agree.
    for shared in ('starship', 'tmux'):
        choices = [data['settings'][shared] for data in result['shells'].values() if shared in data['settings']]
        if choices and any(choice != choices[0] for choice in choices):
            raise ValueError('Conflicting settings for a shared configuration file.')
    return result


def load(home=None):
    raw = userfiles.read_file(backend.targets(home)['preferences'])[0]
    return validate_preferences(json.loads(raw, object_pairs_hook=unique_object)) if raw is not None else {'schema_version': 1, 'shells': {}, 'terminals': {}}


def starship_config(options):
    opt = validate_settings({'starship': options})['starship']
    fmt = '$directory' + ('$git_branch$git_status' if opt['git'] else '') + '$character'
    return (f'add_newline = {str(opt["newline"]).lower()}\nformat = {json.dumps(fmt)}\n'
            f'[character]\nsuccess_symbol = {json.dumps("[" + opt["symbol"] + "](bold " + opt["color"] + ")", ensure_ascii=False)}\n'
            f'error_symbol = {json.dumps("[" + opt["symbol"] + "](bold red)", ensure_ascii=False)}\n'
            '[git_branch]\nsymbol = "git:"\n').encode('utf-8')


def current_starship(home=None):
    for data in load(home)['shells'].values():
        if 'starship' in data['settings']:
            return starship_config(data['settings']['starship'])
    return starship_config(DEFAULTS['starship'])


def tmux_config(options):
    opt = validate_settings({'tmux': options})['tmux']
    return (f'unbind C-b\nset -g prefix {opt["prefix"]}\nbind {opt["prefix"]} send-prefix\n'
            f'set -g mouse {"on" if opt["mouse"] else "off"}\nset -g status-position {opt["position"]}\n').encode('utf-8')


def environment(shell, settings, aliases, mapping):
    lines = []
    def variable(name, value):
        quoted = integrations.quote(value, shell)
        lines.append(('set -gx ' if shell == 'fish' else 'export ') + name + (' ' if shell == 'fish' else '=') + quoted)
    if 'fzf' in settings:
        opt = settings['fzf']
        flags = f'--height={opt["height"]}% --layout={opt["layout"]} --color={opt["color"]}'
        if opt['preview']:
            # Fixed built-in preview; never an imported or interpolated command.
            flags += " --preview='head -n 100 -- {}'"
        variable('FZF_DEFAULT_OPTS', flags)
    if 'bat' in settings:
        variable('BAT_THEME', settings['bat']['theme'])
        variable('BAT_STYLE', settings['bat']['style'])
    if 'eza' in settings:
        flags = ' '.join('--' + key for key in DEFAULTS['eza'] if settings['eza'][key])
        if shell == 'fish':
            lines.append(f'function mtk-eza\n    command eza {flags} $argv\nend')
        else:
            lines.append(f'mtk-eza() {{ command eza {flags} "$@"; }}')
    if 'tmux' in settings:
        value = integrations.quote(mapping['tmux'], shell)
        if shell == 'fish':
            lines.append(f'function mtk-tmux\n    command tmux -L minttweaks -f {value} $argv\nend')
        else:
            lines.append(f'mtk-tmux() {{ command tmux -L minttweaks -f {value} "$@"; }}')
    for name, command in sorted(aliases.items()):
        if shell == 'fish':
            # Fish's alias helper sources generated function bodies. Keep the
            # imported command a string until the user invokes this function.
            body = 'command ' + command if re.match(r'^' + re.escape(name) + r'(?:\s|$)', command) else command
            value = integrations.quote(body, shell)
            lines.append(f'function {name}\n    builtin eval {value} (string escape -- $argv)\nend')
        else:
            lines.append(f'alias {name}={integrations.quote(command, shell)}')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def check_shell(shell, home):
    if shell not in backend.SHELLS:
        raise ValueError('Unknown shell.')
    if shell == 'zsh' and os.environ.get('ZDOTDIR') and Path(os.environ['ZDOTDIR']) != (Path.home() if home is None else Path(home)):
        raise ValueError(_("A custom ZDOTDIR is in use. Manage its initialization manually."))
    if not backend.shutil.which(shell):
        raise ValueError(_("Install the target shell before configuring its integrations."))


def changes_for_preferences(runner, preferences, shells, home=None):
    preferences = validate_preferences(preferences)
    mapping = backend.targets(home)
    updates, notes = {}, []
    for shell in shells:
        check_shell(shell, home)
        data = preferences['shells'].get(shell, {'settings': {}, 'aliases': {}})
        settings, aliases = data['settings'], data['aliases']
        for tool in settings:
            if not backend.tool_state(runner, tool).binary:
                raise ValueError(_("Install this tool before configuring it: {tool}").format(tool=tool))
        slot = {'bash': 'bashrc', 'zsh': 'zshrc', 'fish': 'fishrc'}[shell]
        rc = (userfiles.read_file(mapping[slot])[0] or b'').decode('utf-8')
        clean = integrations.strip_block(rc, 'customization')
        for name in aliases:
            if re.search(r'\balias\s+' + re.escape(name) + r'(?:\s|=)|\bfunction\s+' + re.escape(name) + r'\b|\b' + re.escape(name) + r'\s*\(\s*\)', clean):
                raise ValueError(_("A manual alias or function already uses this name: {name}").format(name=name))
            if backend.shutil.which(name):
                notes.append(_("Alias {name} will shadow an installed command in {shell}.").format(name=name, shell=shell))
        # Configure the hooks which these graphical settings rely on.
        hooks = [tool for tool in settings if tool in integrations.INTEGRATIONS]
        if hooks:
            plan = integrations.preview(runner, shell, hooks, home=home)
            updates.update({change.slot: change.after for change in plan.changes})
            rc = (updates.get(slot) or rc.encode('utf-8')).decode('utf-8')
        rc = integrations.strip_block(rc, 'customization')
        env_slot = 'settings-' + shell
        content = environment(shell, settings, aliases, mapping)
        if content.strip():
            start, end = integrations.markers('customization')
            source = integrations.source_script(mapping[env_slot], shell)
            source = ('if status is-interactive\n' + source + '\nend' if shell == 'fish' else
                      ('case $- in\n*i*)\n' + source + '\n;;\nesac' if shell == 'bash' else
                       'if [[ -o interactive ]]; then\n' + source + '\nfi'))
            # Settings precede initialization: fzf reads its environment at load time.
            rc = start + '\n' + source + '\n' + end + '\n' + rc
            updates[env_slot] = content
        else:
            updates[env_slot] = None
        if settings or aliases or userfiles.read_file(mapping[slot])[0] is not None:
            updates[slot] = rc.encode('utf-8')
        if 'tmux' in settings:
            updates['tmux'] = tmux_config(settings['tmux'])
        if 'starship' in settings:
            updates['starship'] = starship_config(settings['starship'])
    updates['preferences'] = (json.dumps(preferences, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    notes.append(_("Open a new terminal. Use mtk-eza and mtk-tmux for their managed options; mtk-tmux uses a separate server."))
    return ConfigurationPlan(tuple(userfiles.preview(mapping, dict(sorted(updates.items())))), tuple(notes), tuple(shells), updates['preferences'])


def preview(runner, shell, tool=None, options=None, aliases=None, home=None):
    preferences = copy.deepcopy(load(home))
    data = preferences['shells'].setdefault(shell, {'settings': {}, 'aliases': {}})
    if tool is not None:
        data['settings'].update(validate_settings({tool: options}))
        if tool in ('starship', 'tmux'):
            for existing in preferences['shells'].values():
                if tool in existing['settings']:
                    existing['settings'][tool] = dict(options)
    if aliases is not None:
        data['aliases'] = validate_aliases(aliases)
    return changes_for_preferences(runner, preferences, [shell], home)


def apply(runner, plan, home=None):
    if not runner.dry_run and plan.preferences:
        preferences = json.loads(plan.preferences, object_pairs_hook=unique_object)
        fresh = changes_for_preferences(runner, preferences, plan.shells, home)
        if fresh.changes != plan.changes:
            raise ValueError(_("The personal configuration changed. Review a new preview."))
    return userfiles.apply(runner, backend.targets(home), plan.changes, paths.TERMINAL_BACKUP_DIR / 'files')
