"""Explicit APT installs, current-user shell changes and backed-up user files."""

from __future__ import annotations

import difflib
import json
import os
import platform
import pwd
import re
import shlex
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ...core import paths, userfiles
from ...core.runner import cmd, read_command
from ...i18n import _
from ..software.backend import VERSION_RE, apt_command, package_state
from .catalog import CATALOG, CATEGORIES, TOOL_BY_ID, TOOLS

SHELLS = ("bash", "zsh", "fish")
TERMINALS = ("kitty", "alacritty")
PALETTES = {"dark": ("#20242b", "#e6e9ef"), "light": ("#fafafa", "#24292e")}
START = "# >>> MintTweaks Starship >>>"
END = "# <<< MintTweaks Starship <<<"


@dataclass
class ToolState:
    installed: bool = False
    binary: str = ""
    version: str = ""
    candidate: str = ""
    error: str = ""


@dataclass
class TerminalState:
    tools: dict = field(default_factory=dict)
    fonts: list = field(default_factory=lambda: ["monospace"])
    account: tuple = ()
    shells: list = field(default_factory=list)
    error: str = ""


def fonts(runner):
    result = ["monospace"]
    try:
        raw = read_command(runner, cmd("fc-list", "--format=%{family[0]}\\n"), timeout=15).stdout
        result += sorted({line.strip() for line in raw.splitlines() if 0 < len(line.strip()) <= 100
                          and not any(ord(char) < 32 for char in line.strip())})[:512]
    except Exception:
        pass
    return list(dict.fromkeys(result))


def current_account():
    if platform.system() != "Linux" or os.getuid() == 0:
        raise ValueError(_("Login shell changes require a normal Linux desktop user."))
    entry = pwd.getpwuid(os.getuid())
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*\$?", entry.pw_name):
        raise ValueError("Unsupported account name.")
    return entry.pw_name, entry.pw_shell


def allowed_shells(shells_file=Path("/etc/shells")):
    values = []
    for line in shells_file.read_text(encoding="utf-8").splitlines():
        candidate = line.split("#", 1)[0].strip()
        path = Path(candidate)
        if path.parent in (Path("/bin"), Path("/usr/bin")) and path.name in SHELLS and os.access(path, os.X_OK):
            resolved = path.resolve()
            if resolved.parent in (Path("/bin"), Path("/usr/bin")) and resolved.name in SHELLS:
                values.append(candidate)
    return sorted(set(values))


def tool_state(runner, tool):
    entry = TOOL_BY_ID[tool]
    binary = next((path for name in entry.binaries for path in [shutil.which(name)] if path), "")
    state = ToolState(binary=binary)
    try:
        package = package_state(runner, entry.package)
        state.installed = package.installed or bool(state.binary)
        state.version = package.version
        if not state.installed:
            policy = read_command(runner, cmd("apt-cache", "policy", entry.package), timeout=15).stdout
            match = re.search(r"^\s*Candidate:\s*(\S+)\s*$", policy, re.MULTILINE)
            if match and VERSION_RE.fullmatch(match[1]):
                state.candidate = match[1]
            else:
                state.error = _("No APT candidate. Use the project's official installation guide if needed.")
    except Exception as exc:
        state.error = str(exc)
    return state


def collect_state(runner):
    state = TerminalState({tool: tool_state(runner, tool) for tool in TOOLS}, fonts(runner))
    try:
        state.account = current_account()
        state.shells = allowed_shells()
    except Exception as exc:
        state.error = str(exc)
    return state


@dataclass(frozen=True)
class PackagePlan:
    tools: tuple
    specs: tuple
    operations: tuple
    output: str


def preview_install(runner, selected):
    if not selected or len(set(selected)) != len(selected) or any(tool not in TOOLS for tool in selected):
        raise ValueError("Choose tools from the terminal catalog only.")
    specs = []
    for tool in selected:
        state = tool_state(runner, tool)
        if state.installed or state.error or not state.candidate:
            raise ValueError(state.error or _("The selected tool is already installed: {tool}").format(tool=tool))
        specs.append(TOOL_BY_ID[tool].package + "=" + state.candidate)
    result = read_command(runner, apt_command(specs, simulate=True), timeout=120)
    operations = tuple(sorted(line.strip() for line in result.stdout.splitlines() if line.startswith(("Inst ", "Conf ", "Remv ", "Purg "))))
    if any(line.startswith(("Remv ", "Purg ")) for line in operations):
        raise ValueError(_("APT proposed removals. Installation was refused."))
    installed = {line.split()[1].split(":")[0] for line in operations if line.startswith("Inst ")}
    if not {TOOL_BY_ID[tool].package for tool in selected} <= installed:
        raise ValueError(_("The complete installation plan could not be read."))
    return PackagePlan(tuple(selected), tuple(specs), operations, result.output)


def install(runner, plan, on_line=None):
    if runner.dry_run:
        return _("Simulation: no terminal tools were installed.")
    checked = preview_install(runner, plan.tools)
    if (checked.specs, checked.operations) != (plan.specs, plan.operations):
        raise ValueError(_("The installation plan changed. Review a new preview before continuing."))
    result = runner.stream(apt_command(checked.specs), on_line=on_line)
    if not result.ok:
        raise ValueError(result.output or _("The tool installation failed. Check APT before retrying."))
    for tool, spec in zip(checked.tools, checked.specs):
        actual = package_state(runner, TOOL_BY_ID[tool].package)
        if not actual.installed or actual.version != spec.split("=", 1)[1]:
            raise ValueError(_("The installed tool version could not be verified: {tool}").format(tool=tool))
    return _("The terminal tools were installed and verified.")


def config_home(home=None):
    home = Path.home() if home is None else Path(home)
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")


def targets(home=None):
    home = Path.home() if home is None else Path(home)
    config = config_home(home)
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    return {
        "bashrc": home / ".bashrc", "zshrc": home / ".zshrc", "fishrc": config / "fish/config.fish",
        "starship": config / "minttweaks/terminal/starship.toml",
        "kitty": config / "minttweaks/terminal/kitty.conf",
        "alacritty-toml": config / "minttweaks/terminal/alacritty.toml",
        "alacritty-yaml": config / "minttweaks/terminal/alacritty.yml",
        "kitty-launcher": data / "applications/minttweaks-kitty.desktop",
        "alacritty-launcher": data / "applications/minttweaks-alacritty.desktop",
        "preferences": config / "minttweaks/terminal/preferences.json",
        "settings-bash": config / "minttweaks/terminal/settings.bash",
        "settings-zsh": config / "minttweaks/terminal/settings.zsh",
        "settings-fish": config / "minttweaks/terminal/settings.fish",
        "tmux": config / "minttweaks/terminal/tmux.conf",
    }


def changes_text(changes, mapping):
    lines = []
    for change in changes:
        lines.append(str(mapping[change.slot]))
        before = (change.before or b"").decode("utf-8")
        after = (change.after or b"").decode("utf-8")
        lines += list(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile="before", tofile="after", lineterm=""))
    return lines


def prompt_preview(runner, shell, enabled, home=None):
    if shell not in SHELLS:
        raise ValueError("Unknown shell.")
    if shell == "zsh" and os.environ.get("ZDOTDIR") and Path(os.environ["ZDOTDIR"]) != (Path.home() if home is None else Path(home)):
        raise ValueError(_("A custom ZDOTDIR is in use. Manage its initialization manually."))
    if enabled and not shutil.which("starship"):
        raise ValueError(_("Install Starship before enabling its prompt."))
    mapping = targets(home)
    slot = {"bash": "bashrc", "zsh": "zshrc", "fish": "fishrc"}[shell]
    before = userfiles.read_file(mapping[slot])[0] or b""
    text = before.decode("utf-8")
    placement = None
    if text.count(START) != text.count(END) or text.count(START) > 1:
        raise ValueError(_("The managed prompt block is malformed. The file was preserved."))
    if START in text:
        start, stop = text.index(START), text.index(END)
        if start > stop or (start and text[start - 1] != "\n") or (stop and text[stop - 1] != "\n"):
            raise ValueError("Invalid prompt markers.")
        end = stop + len(END)
        if text[start + len(START):start + len(START) + 1] != "\n" or (end < len(text) and text[end] != "\n"):
            raise ValueError("Invalid prompt markers.")
        tail = text[end:]
        placement = (text[:start], tail[1:] if tail.startswith("\n") else tail)
        text = text[:start] + (tail[1:] if tail.startswith("\n") else tail)
    elif not enabled:
        return []
    if enabled:
        if any(re.search(r"\bstarship\s+init\b", line) for line in text.splitlines() if not line.lstrip().startswith("#")):
            raise ValueError(_("Starship is already initialized outside the managed block. The file was preserved."))
        path = str(mapping["starship"])
        if shell == "fish":
            quoted = "'" + path.replace("\\", "\\\\").replace("'", "\\'") + "'"
            block = f"if status is-interactive; and type -q starship\n    set -gx STARSHIP_CONFIG {quoted}\n    starship init fish | source\nend"
        else:
            block = f'if command -v starship >/dev/null 2>&1; then\n    export STARSHIP_CONFIG={shlex.quote(path)}\n    eval "$(starship init {shell})"\nfi'
        managed = START + "\n" + block + "\n" + END + "\n"
        if placement is None:
            text += ("\n" if text and not text.endswith("\n") else "") + managed
        else:
            text = placement[0] + managed + placement[1]
    updates = {slot: text.encode("utf-8")}
    if enabled:
        from .configuration import current_starship
        updates["starship"] = current_starship(home)
    return userfiles.preview(mapping, updates)


def desktop_quote(value):
    if any(ord(char) < 32 for char in value):
        raise ValueError("Unsupported launcher path.")
    quoted = re.sub(r'([\\"`$])', r'\\\1', value).replace("%", "%%")
    # Desktop string unescaping happens before Exec argument unquoting.
    return '"' + quoted.replace("\\", "\\\\") + '"'


def terminal_preview(runner, terminal, palette, family, size, home=None, persist=True):
    if terminal not in TERMINALS or palette not in PALETTES or type(size) is not int or not 8 <= size <= 32:
        raise ValueError("Invalid terminal profile.")
    if family not in fonts(runner):
        raise ValueError(_("Choose an installed font from the list."))
    binary = shutil.which(terminal)
    if not binary:
        raise ValueError(_("Install the selected terminal first."))
    if "=" in binary:
        raise ValueError("Unsupported launcher executable path.")
    mapping = targets(home)
    background, foreground = PALETTES[palette]
    if terminal == "kitty":
        slot = "kitty"
        text = f"font_family {family}\nfont_size {size}\nbackground {background}\nforeground {foreground}\n"
        option = "--config"
    else:
        version = read_command(runner, cmd(binary, "--version"), timeout=10).stdout
        match = re.search(r"alacritty (\d+)\.(\d+)\.", version)
        if not match:
            raise ValueError(_("The Alacritty configuration format could not be identified."))
        toml = int(match[1]) > 0 or int(match[2]) >= 13
        slot = "alacritty-toml" if toml else "alacritty-yaml"
        text = (f'[font]\nsize = {size}.0\n[font.normal]\nfamily = {json.dumps(family, ensure_ascii=False)}\n'
                f'[colors.primary]\nbackground = "{background}"\nforeground = "{foreground}"\n') if toml else (
                f'font:\n  size: {size}.0\n  normal:\n    family: {json.dumps(family, ensure_ascii=False)}\n'
                f'colors:\n  primary:\n    background: "{background}"\n    foreground: "{foreground}"\n')
        option = "--config-file"
    launch = ("[Desktop Entry]\nType=Application\nName=" + terminal.capitalize() + " — MintTweaks\nExec=" +
              " ".join(desktop_quote(value) for value in (binary, option, str(mapping[slot]))) +
              "\nIcon=" + terminal + "\nTerminal=false\nCategories=System;TerminalEmulator;\n")
    updates = {slot: text.encode("utf-8"), terminal + "-launcher": launch.encode("utf-8")}
    if persist:
        from . import configuration
        preferences = configuration.load(home)
        preferences['terminals'][terminal] = {'palette': palette, 'family': family, 'size': size}
        updates['preferences'] = (json.dumps(preferences, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    return userfiles.preview(mapping, updates)


@dataclass(frozen=True)
class ShellPlan:
    user: str
    before: str
    after: str


def preview_shell(path):
    user, before = current_account()
    if path not in allowed_shells():
        raise ValueError(_("Choose an executable shell listed in /etc/shells."))
    return ShellPlan(user, before, path)


def change_shell(runner, plan, backup_directory=None):
    if runner.dry_run:
        return _("Simulation: the login shell was not changed.")
    checked = preview_shell(plan.after)
    if checked != plan:
        raise ValueError(_("The account shell changed. Review a new preview."))
    if plan.before == plan.after:
        return _("This is already your login shell.")
    directory = Path(backup_directory) if backup_directory else paths.TERMINAL_BACKUP_DIR / "accounts"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = directory / (uuid.uuid4().hex + ".json")
    userfiles.atomic_write(receipt, json.dumps({"user": plan.user, "before": plan.before, "after": plan.after}).encode("utf-8"))
    result = runner.stream(cmd("/usr/bin/chsh", "-s", plan.after, plan.user, root=True), timeout=120)
    if not result.ok or current_account() != (plan.user, plan.after):
        raise ValueError(result.output or _("The login shell change could not be verified. Its previous value was saved."))
    return _("Login shell updated. Start a new login session to use it.")


def restore_shell_plan(directory=None):
    directory = Path(directory) if directory else paths.TERMINAL_BACKUP_DIR / "accounts"
    files = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
    if not files:
        raise ValueError(_("No login shell backup is available."))
    raw = userfiles.read_file(files[0])[0]
    data = json.loads(raw)
    if current_account() != (data["user"], data["after"]):
        raise ValueError(_("The account no longer matches the latest shell backup. Choose the shell manually."))
    return preview_shell(data["before"])
