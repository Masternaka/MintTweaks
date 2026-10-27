"""Generate, preview and restore shell hooks without executing startup files."""
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shlex

from ...core import paths, userfiles
from ...core.runner import cmd, read_command
from ...i18n import _
from . import backend

# Order matters: completion first, Atuin after fzf, Zsh highlighting last.
INTEGRATIONS = ('bash-completion', 'bat', 'fd', 'fzf', 'zoxide', 'starship',
                'delta', 'atuin', 'direnv', 'zsh-autosuggestions', 'zsh-syntax-highlighting')
ONLY = {'bash-completion': 'bash', 'zsh-autosuggestions': 'zsh', 'zsh-syntax-highlighting': 'zsh'}


@dataclass(frozen=True)
class IntegrationPlan:
    shell: str
    tools: tuple
    enabled: bool
    changes: tuple
    notes: tuple


def markers(tool):
    return '# >>> MintTweaks integration: ' + tool + ' >>>', '# <<< MintTweaks integration: ' + tool + ' <<<'


def block(tool, shell, content):
    start, end = markers(tool)
    if shell == 'fish':
        content = 'if status is-interactive\n' + content + '\nend'
    else:
        content = ('case $- in\n    *i*)\n' if shell == 'bash' else 'if [[ -o interactive ]]; then\n') + content + ('\n;;\nesac' if shell == 'bash' else '\nfi')
    return start + '\n' + content + '\n' + end + '\n'


def strip_block(text, tool):
    start, end = markers(tool)
    if text.count(start) != text.count(end) or text.count(start) > 1:
        raise ValueError(_("An integration block is malformed. The startup file was preserved."))
    if start not in text:
        return text
    pattern = re.compile(r'^' + re.escape(start) + r'\n.*?^' + re.escape(end) + r'(?:\n|$)', re.MULTILINE | re.DOTALL)
    if not pattern.search(text):
        raise ValueError(_("An integration block is malformed. The startup file was preserved."))
    return pattern.sub('', text, count=1)


def quote(value, shell):
    if shell == 'fish':
        return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"
    return shlex.quote(str(value))


def system_script(candidates):
    for path in candidates:
        candidate = Path(path)
        if candidate.is_file() and os.access(candidate, os.R_OK):
            return candidate
    raise ValueError(_("A required shell integration script is unavailable: {path}").format(path=candidates[0]))


def source_script(path, shell):
    value = quote(path, shell)
    if shell == 'fish':
        return f'if test -r {value}\n    source {value}\nend'
    return f'if [ -r {value} ]; then\n    . {value}\nfi'


def init_hook(tool, shell, verb='init'):
    if shell == 'fish':
        return f'if type -q {tool}\n    {tool} {verb} fish | source\nend'
    return f'if command -v {tool} >/dev/null 2>&1; then\n    eval "$({tool} {verb} {shell})"\nfi'


def hook(runner, tool, shell):
    if tool in ('zoxide', 'atuin', 'direnv'):
        return init_hook(tool, shell, 'hook' if tool == 'direnv' else 'init')
    if tool in ('bat', 'fd'):
        fallback = 'batcat' if tool == 'bat' else 'fdfind'
        if shell == 'fish':
            return f'if not type -q {tool}; and type -q {fallback}\n    alias {tool} {fallback}\nend'
        return f'if ! command -v {tool} >/dev/null 2>&1 && command -v {fallback} >/dev/null 2>&1; then\n    alias {tool}={fallback}\nfi'
    if tool == 'delta':
        if shell == 'fish':
            return 'if type -q delta; and not set -q GIT_PAGER\n    set -gx GIT_PAGER delta\nend'
        return 'if command -v delta >/dev/null 2>&1 && [ -z "${GIT_PAGER+x}" ]; then\n    export GIT_PAGER=delta\nfi'
    if tool == 'bash-completion':
        path = system_script(['/usr/share/bash-completion/bash_completion'])
        return 'if ! declare -F _init_completion >/dev/null; then\n' + source_script(path, shell) + '\nfi'
    if tool.startswith('zsh-'):
        path = system_script(['/usr/share/' + tool + '/' + tool + '.zsh'])
        return source_script(path, shell)
    if tool == 'fzf':
        binary = backend.shutil.which('fzf')
        output = read_command(runner, cmd(binary, '--version'), timeout=10).stdout
        match = re.match(r'(\d+)\.(\d+)', output.strip())
        if not match:
            raise ValueError(_("The installed fzf version could not be identified."))
        if (int(match[1]), int(match[2])) >= (0, 48):
            if shell == 'fish':
                return 'if type -q fzf\n    fzf --fish | source\nend'
            if shell == 'zsh':
                return 'if command -v fzf >/dev/null 2>&1; then\n    source <(fzf --zsh)\nfi'
            return f'if command -v fzf >/dev/null 2>&1; then\n    eval "$(fzf --{shell})"\nfi'
        if shell == 'fish':
            path = system_script(['/usr/share/fish/vendor_functions.d/fzf_key_bindings.fish',
                                  '/usr/share/doc/fzf/examples/key-bindings.fish'])
            return source_script(path, shell) + '\nif functions -q fzf_key_bindings\n    fzf_key_bindings\nend'
        scripts = [system_script(['/usr/share/doc/fzf/examples/' + kind + '.' + shell,
                                  '/usr/share/fzf/shell/' + kind + '.' + shell])
                   for kind in ('completion', 'key-bindings')]
        return '\n'.join(source_script(path, shell) for path in scripts)
    raise ValueError('Unknown shell integration.')


def manual_hook(text, tool):
    active = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))
    if re.search(r'\bplugins\s*=\s*\([^)]*\b' + re.escape(tool) + r'\b', active):
        return True
    if tool == 'zoxide' and re.search(r'\balias\s+(?:z|zi)\s*=|\bfunction\s+(?:z|zi)\b|\b(?:z|zi)\s*\(\s*\)', active):
        return True
    if tool in ('zoxide', 'atuin', 'direnv', 'starship'):
        verb = 'hook' if tool == 'direnv' else 'init'
        return bool(re.search(r'\b' + tool + r'\s+' + verb + r'\b', active))
    if tool in ('fzf', 'bash-completion') or tool.startswith('zsh-'):
        return bool(re.search(r'(?:source|\.)\s+[^\n;]*' + re.escape(tool), active) or
                    (tool == 'fzf' and re.search(r'\bfzf\s+--(?:bash|zsh|fish)\b|\bfzf_key_bindings\b', active)))
    return False


def preview(runner, shell, selected, enabled=True, home=None):
    if shell not in backend.SHELLS or not selected or len(set(selected)) != len(selected) or not set(selected) <= set(backend.TOOLS):
        raise ValueError('Choose known tools and a supported shell.')
    mapping = backend.targets(home)
    if shell == 'zsh' and os.environ.get('ZDOTDIR') and Path(os.environ['ZDOTDIR']) != (Path.home() if home is None else Path(home)):
        raise ValueError(_("A custom ZDOTDIR is in use. Manage its initialization manually."))
    if enabled and not backend.shutil.which(shell):
        raise ValueError(_("Install the target shell before configuring its integrations."))
    slot = {'bash': 'bashrc', 'zsh': 'zshrc', 'fish': 'fishrc'}[shell]
    raw = userfiles.read_file(mapping[slot])[0]
    text = (raw or b'').decode('utf-8')
    notes, applicable = [], []
    for tool in selected:
        name = backend.TOOL_BY_ID[tool].name
        if tool not in INTEGRATIONS:
            notes.append(_("{tool}: ready with its default configuration; no shell hook is needed.").format(tool=name))
        elif tool in ONLY and ONLY[tool] != shell:
            notes.append(_("{tool}: applies to {shell} only; not changed here.").format(tool=name, shell=ONLY[tool]))
        else:
            if enabled:
                state = backend.tool_state(runner, tool)
                if not state.installed or (backend.TOOL_BY_ID[tool].binaries and not state.binary):
                    raise ValueError(_("Install this tool before configuring it: {tool}").format(tool=name))
            applicable.append(tool)
    # Reject duplicate manual initialization before changing any file.
    clean = text
    for tool in INTEGRATIONS:
        if tool != 'starship':
            clean = strip_block(clean, tool)
    if enabled:
        for tool in applicable:
            if tool != 'starship' and manual_hook(clean, tool):
                raise ValueError(_("A manual integration already exists for {tool}. The startup file was preserved.").format(tool=tool))
    updates = {}
    if 'starship' in applicable:
        changes = backend.prompt_preview(runner, shell, enabled, home)
        for change in changes:
            updates[change.slot] = change.after
        text = (updates.get(slot, raw) or b'').decode('utf-8')
    if shell == 'zsh' and enabled and applicable and not re.search(r'\bcompinit\b', clean):
        init_start, init_end = markers('completion-system')
        text = strip_block(text, 'completion-system')
        text += ('\n' if text and not text.endswith('\n') else '') + init_start + '\nif [[ -o interactive ]] && (( ! $+functions[compdef] )); then\n    autoload -Uz compinit\n    compinit\nfi\n' + init_end + '\n'
    for tool in INTEGRATIONS:
        if tool not in applicable or tool == 'starship':
            continue
        text = strip_block(text, tool)
        if enabled:
            content = hook(runner, tool, shell)
            text += ('\n' if text and not text.endswith('\n') else '') + block(tool, shell, content)
    if shell == 'zsh' and enabled and applicable:
        # Initialize completion before hooks and load highlighting after widgets.
        # Keep an existing managed highlighter at the end on later additions.
        start, end = markers('zsh-syntax-highlighting')
        pattern = re.compile(r'^' + re.escape(start) + r'\n.*?^' + re.escape(end) + r'(?:\n|$)', re.MULTILINE | re.DOTALL)
        match = pattern.search(text)
        if match:
            owned_block = match.group()
            text = pattern.sub('', text, count=1) + owned_block
    if shell == 'zsh' and not enabled and not any(markers(tool)[0] in text for tool in INTEGRATIONS):
        text = strip_block(text, 'completion-system')
    if text != (raw or b'').decode('utf-8'):
        updates[slot] = text.encode('utf-8')
    elif slot in updates and updates[slot] == raw:
        updates.pop(slot)
    notes.append(_("Open a new interactive {shell} terminal after applying. Existing terminals are not reloaded.").format(shell=shell))
    if enabled and 'atuin' in applicable:
        notes.append(_("Atuin records new command history locally and takes Ctrl+R after fzf. No account, sync or history import is configured."))
    if enabled and 'delta' in applicable:
        notes.append(_("Delta becomes the Git pager in this shell when GIT_PAGER is unset; Git configuration files are preserved."))
    changes = userfiles.preview(mapping, updates) if updates else []
    return IntegrationPlan(shell, tuple(selected), enabled, tuple(changes), tuple(notes))


def apply(runner, plan, home=None, backup_directory=None):
    if runner.dry_run:
        return userfiles.FileOutcome(True, simulated=True)
    fresh = preview(runner, plan.shell, plan.tools, plan.enabled, home)
    if fresh.changes != plan.changes:
        raise ValueError(_("The integration plan changed. Review a new preview."))
    return userfiles.apply(runner, backend.targets(home), plan.changes,
                           backup_directory or paths.TERMINAL_BACKUP_DIR / 'files')
