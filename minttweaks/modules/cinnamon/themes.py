"""Install the published Catppuccin theme files without running repo scripts."""
from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import backend
from ...core.runner import cmd
from ...i18n import _

REPOSITORY = 'https://github.com/Masternaka/Cinnamon_Catppuccin.git'
VARIANTS = ('Latte', 'Frappe', 'Macchiato', 'Mocha')
MAX_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 5000


def theme_name(variant):
    if variant not in VARIANTS:
        raise ValueError(_("Choose a Catppuccin variant from the list."))
    return 'Catppuccin-' + variant


def safe_path(value):
    if not str(value).strip():
        raise ValueError(_("Choose a directory first."))
    path = Path(os.path.abspath(Path(value).expanduser()))
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(_("The theme path must contain ordinary directories only: {path}").format(path=parent))
    return path


def clone_command(destination):
    path = safe_path(destination)
    if os.path.lexists(path) or not path.parent.is_dir():
        raise ValueError(_("Choose a new clone directory inside an existing parent folder."))
    return cmd('git', '-c', 'core.hooksPath=/dev/null', '-c', 'protocol.file.allow=never',
               '-c', 'protocol.ext.allow=never', 'clone', '--depth=1', '--no-recurse-submodules',
               '--', REPOSITORY, str(path))


def clone(runner, destination, on_line=None):
    command = clone_command(destination)
    if runner.dry_run:
        return _("Simulation: the theme repository was not cloned.")
    result = runner.stream(command, on_line=on_line)
    if not result.ok:
        raise ValueError(result.output)
    return _("Catppuccin repository cloned. Choose a variant to install.")


def tree_snapshot(directory):
    directory = safe_path(directory)
    if not directory.is_dir():
        raise ValueError(_("The theme directory is missing: {path}").format(path=directory))
    entries, total = [], 0
    def failed(exc):
        raise exc
    for parent, dirs, files in os.walk(directory, followlinks=False, onerror=failed):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            info = path.lstat()
            relative = str(path.relative_to(directory))
            if stat.S_ISDIR(info.st_mode):
                entries.append((relative, 'directory', stat.S_IMODE(info.st_mode), ''))
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                if total > MAX_BYTES:
                    raise ValueError(_("The theme exceeds the supported size limit."))
                digest = hashlib.sha256()
                with path.open('rb') as handle:
                    while True:
                        block = handle.read(65536)
                        if not block:
                            break
                        digest.update(block)
                entries.append((relative, 'file', stat.S_IMODE(info.st_mode), digest.hexdigest()))
            else:
                raise ValueError(_("Theme symbolic links and special files are not supported: {path}").format(path=path))
            if len(entries) > MAX_ENTRIES:
                raise ValueError(_("The theme contains too many files."))
    return tuple(sorted(entries))


def themes_directory():
    # ~/.themes is also the default of this repository's documented installer.
    return Path.home() / '.themes'


@dataclass(frozen=True)
class InstallPlan:
    source: Path
    target: Path
    source_tree: tuple
    previous_tree: tuple
    backup: Path = None


def preview_install(repository, variant, destination=None):
    name = theme_name(variant)
    repository = safe_path(repository)
    source = safe_path(repository / 'dist' / name)
    source_tree = tree_snapshot(source)
    for required in ('index.theme', 'cinnamon/cinnamon.css'):
        if not (source / required).is_file():
            raise ValueError(_("The repository does not contain a complete generated Cinnamon theme."))
    target = safe_path((themes_directory() if destination is None else Path(destination)) / name)
    if source == target or source in target.parents or target in source.parents:
        raise ValueError(_("The theme source and installation directory overlap."))
    previous = tree_snapshot(target) if target.exists() else None
    backup = None
    if previous is not None:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = safe_path(target.parent / '.minttweaks-backups' / (stamp + '-' + uuid.uuid4().hex) / name)
    return InstallPlan(source, target, source_tree, previous, backup)


def install(runner, plan):
    if runner.dry_run:
        return _("Simulation: no theme files or backups were written.")
    safe_path(plan.source)
    safe_path(plan.target)
    previous = tree_snapshot(plan.target) if plan.target.exists() else None
    if tree_snapshot(plan.source) != plan.source_tree or previous != plan.previous_tree:
        raise ValueError(_("The theme files changed. Review a new installation preview."))
    if plan.backup is not None:
        safe_path(plan.backup)
        if plan.backup.exists():
            raise ValueError(_("The theme backup destination already exists."))
    plan.target.parent.mkdir(parents=True, exist_ok=True)
    moved = False
    with tempfile.TemporaryDirectory(prefix='.mtk-theme-', dir=plan.target.parent) as tmp:
        staged = Path(tmp) / plan.target.name
        shutil.copytree(plan.source, staged)
        if tree_snapshot(staged) != plan.source_tree:
            raise ValueError(_("The staged theme copy could not be verified."))
        # Recheck immediately before moving any existing theme out of the way.
        safe_path(plan.target)
        previous = tree_snapshot(plan.target) if plan.target.exists() else None
        if previous != plan.previous_tree or tree_snapshot(plan.source) != plan.source_tree:
            raise ValueError(_("The theme files changed. Review a new installation preview."))
        try:
            if plan.backup is not None:
                safe_path(plan.backup)
                plan.backup.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
                plan.target.rename(plan.backup)
                moved = True
                if tree_snapshot(plan.backup) != plan.previous_tree:
                    raise ValueError(_("The previous theme backup could not be verified."))
            staged.rename(plan.target)
            if tree_snapshot(plan.target) != plan.source_tree:
                raise ValueError(_("The installed theme could not be verified."))
        except Exception as exc:
            if moved and not os.path.lexists(plan.target):
                plan.backup.rename(plan.target)
            detail = str(exc)
            if moved:
                detail += '\n' + _("Previous theme: {path}").format(path=plan.backup if plan.backup.exists() else plan.target)
            raise ValueError(detail) from exc
    message = _("Theme installed: {path}").format(path=plan.target)
    if moved:
        message += '\n' + _("Previous theme backup: {path}").format(path=plan.backup)
    return message


def preview_apply(runner, variant):
    name = theme_name(variant)
    installed = safe_path(themes_directory() / name)
    if not (installed / 'cinnamon' / 'cinnamon.css').is_file():
        raise ValueError(_("Install this Catppuccin variant before applying it."))
    snapshot = backend.capture(runner)
    if not snapshot.complete:
        raise ValueError(_("The current appearance could not all be read. Nothing was changed."))
    values = dict(snapshot.values)
    values['org.cinnamon.theme/name'] = name
    profile = backend.Profile(uuid.uuid4().hex, name, backend.timestamp(), values)
    return backend.preview_profile(runner, profile)
