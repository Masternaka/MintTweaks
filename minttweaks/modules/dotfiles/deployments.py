"""Reviewed dotfiles activation, durable backups, and conservative undo.

Only leaf files/links may be backed up. Shared directories are never moved or
removed. A durable journal is written before touching any configuration.
"""
import base64
import datetime
import json
import os
import re
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import backend
from ...core import paths, userfiles
from ...core.runner import read_command
from ...i18n import _

MAX_FILE = 8 * 1024 * 1024
MAX_JOURNAL = 64 * 1024 * 1024


def _parents(path, target):
    if path == target or not path.is_relative_to(target):
        raise ValueError(_("Invalid dotfiles target path."))
    for parent in path.parents:
        if parent == target:
            return
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(_("Unsafe target directory: {path}").format(path=parent))


def _read(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return {'kind': 'link', 'value': os.readlink(path)}
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(_("Only regular files and individual links can be backed up: {path}").format(path=path))
    with path.open('rb') as handle:
        raw = handle.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        raise ValueError(_("The configuration file is too large to back up: {path}").format(path=path))
    return {'kind': 'file', 'value': base64.b64encode(raw).decode('ascii'), 'mode': stat.S_IMODE(info.st_mode)}


def _matches_link(path, source):
    return path.is_symlink() and Path(os.path.abspath(path.parent / os.readlink(path))) == source


def _mapping(root, target, name, tree, dotfiles):
    files = {}
    for relative, mode, *_rest in tree:
        if any(ord(c) < 32 for c in relative) or ' => ' in relative:
            raise ValueError(_("This configuration contains an unsupported filename."))
        parts = Path(relative).parts
        if dotfiles:
            parts = tuple('.' + part[4:] if part.startswith('dot-') else part for part in parts)
        if any(part in {'.', '..'} for part in parts):
            raise ValueError(_("Invalid dot- filename in this configuration."))
        path = target.joinpath(*parts)
        _parents(path, target)
        if path == root or path.is_relative_to(root):
            raise ValueError(_("A configuration cannot create links inside its own repository."))
        if stat.S_ISDIR(mode):
            if os.path.lexists(path) and (path.is_symlink() or not path.is_dir()):
                raise ValueError(_("Unsafe target directory: {path}").format(path=path))
        else:
            key = str(path.relative_to(target))
            if key in files:
                raise ValueError(_("Several source files map to the same target."))
            files[key] = root / name / relative
    return files


def _planned_links(output, mapping):
    names = set()
    for line in output.splitlines():
        if line.startswith('LINK: '):
            relative = line[6:].split(' => ', 1)[0]
            if relative not in mapping:
                raise ValueError(_("Stow proposed an unexpected link: {path}").format(path=relative))
            names.add(relative)
        elif line.startswith(('UNLINK:', 'MV:')):
            raise ValueError(_("Stow proposed an unexpected removal."))
    return tuple(sorted(names))


def backup_directory():
    return paths.DATA_DIR / 'dotfiles-backups'


def _store(create=False):
    directory = backup_directory().absolute()
    # Never follow a symlink in the backup storage hierarchy.
    for parent in (directory, *directory.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(_("Unsafe backup directory: {path}").format(path=parent))
    if create:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    return directory


def _save(path, data):
    raw = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
    if len(raw) > MAX_JOURNAL:
        raise ValueError(_("The dotfiles backup is too large."))
    userfiles.atomic_write(path, raw, 0o600)


def _load(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(_("Invalid dotfiles backup."))
    with path.open('rb') as handle:
        raw = handle.read(MAX_JOURNAL + 1)
    if len(raw) > MAX_JOURNAL:
        raise ValueError(_("The dotfiles backup is too large."))
    data = json.loads(raw)
    if data.get('schema') != 1 or data.get('status') not in {'prepared', 'active', 'undone'}:
        raise ValueError(_("Invalid dotfiles backup."))
    return data


def active_journal(root, target, name, dotfiles=False):
    directory = _store()
    if not directory.exists():
        return None
    matches = []
    for path in sorted(directory.glob('*.json')):
        data = _load(path)
        if (data['root'], data['target'], data['name'], data['dotfiles']) == (str(root), str(target), name, dotfiles) and data['status'] != 'undone':
            matches.append(path)
    if len(matches) > 1:
        raise ValueError(_("Several active dotfiles backups require manual review."))
    return matches[0] if matches else None


@dataclass(frozen=True)
class ActivationPlan(backend.StowPlan):
    records: tuple = ()

    @property
    def backups(self):
        return tuple(record['relative'] for record in self.records if record['before'] is not None)


def preview_activation(runner, repository, target, name, dotfiles=False):
    root, target = backend.directory(repository), backend.directory(target)
    if root == target or target.is_relative_to(root):
        raise ValueError(_("The target must be outside the dotfiles directory."))
    backend._check_resource_files()
    if active_journal(root, target, name, dotfiles):
        raise ValueError(_("This configuration is already managed. Undo its Stow before activating it again."))
    tree = backend._tree(backend._package(root, name))
    mapping = _mapping(root, target, name, tree, dotfiles)
    if not mapping:
        raise ValueError(_("This configuration is empty."))
    snapshots = {relative: _read(target / relative) for relative in mapping}
    # Simulate against an isolated target, omitting conflicting leaves. This
    # respects Stow ignore rules without moving the user's files for a preview.
    with tempfile.TemporaryDirectory(prefix='mtk-stow-preview-') as tmp:
        shadow = Path(tmp).resolve()
        for relative, source in mapping.items():
            real, staged = target / relative, shadow / relative
            # Reproduce only existing ordinary directories, preserving MKDIR plans.
            for parent in reversed(real.parents):
                if parent == target or parent.is_relative_to(target):
                    if parent.is_dir():
                        (shadow / parent.relative_to(target)).mkdir(parents=True, exist_ok=True)
            if _matches_link(real, source) and os.readlink(real) == os.path.relpath(source, real.parent):
                staged.symlink_to(os.path.relpath(source, staged.parent))
        result = read_command(runner, backend.stow_command(root, shadow, name, dotfiles))
        links = _planned_links(result.output, mapping)
        output = result.output.replace(str(shadow), str(target))
    records = tuple({'relative': relative, 'source': str(mapping[relative]), 'before': snapshots[relative]} for relative in links)
    # Bound the complete durable journal before the confirmation.
    if len(json.dumps(records).encode()) > MAX_JOURNAL - 4096:
        raise ValueError(_("The dotfiles backup is too large."))
    return ActivationPlan(root, target, name, dotfiles, tree, output, records)


def _restore(target, records):
    # First validate every leaf, so an external edit blocks the whole undo.
    for record in records:
        path, source = target / record['relative'], Path(record['source'])
        _parents(path, target)
        if not _matches_link(path, source) and _read(path) not in (None, record['before']):
            raise ValueError(_("A target changed outside MintTweaks and was preserved: {path}").format(path=path))
    for record in reversed(records):
        path, source, before = target / record['relative'], Path(record['source']), record['before']
        _parents(path, target)
        if _matches_link(path, source):
            path.unlink()
        elif _read(path) not in (None, before):
            raise ValueError(_("A target changed outside MintTweaks and was preserved: {path}").format(path=path))
        if _read(path) == before:
            continue
        if before is None:
            continue
        if os.path.lexists(path):
            raise ValueError(_("A target changed outside MintTweaks and was preserved: {path}").format(path=path))
        path.parent.mkdir(parents=True, exist_ok=True)
        if before['kind'] == 'link':
            path.symlink_to(before['value'])
        else:
            # Exclusive creation prevents replacement of a newly introduced file.
            with path.open('xb') as handle:
                handle.write(base64.b64decode(before['value'], validate=True))
                os.fchmod(handle.fileno(), before['mode'])
                handle.flush()
                os.fsync(handle.fileno())
        if _read(path) != before:
            raise ValueError(_("Restoration could not be verified: {path}").format(path=path))


def activate(runner, plan, on_line=None):
    if runner.dry_run:
        return _("Simulation: no dotfiles links or backups were created.")
    checked = preview_activation(runner, plan.root, plan.target, plan.name, plan.dotfiles)
    if checked.tree != plan.tree or checked.records != plan.records:
        raise ValueError(_("The Stow plan changed. Review a new preview before continuing."))
    if not plan.records:
        return _("No new dotfiles links are needed.")
    directory = _store()
    if directory.is_relative_to(plan.root) or any(
        directory.is_relative_to(plan.target / record['relative']) or
        (plan.target / record['relative']).is_relative_to(directory)
        for record in plan.records
    ):
        raise ValueError(_("The backup directory overlaps the configuration."))
    _store(create=True)
    journal = directory / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex + '.json')
    data = {'schema': 1, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status': 'prepared', 'root': str(plan.root), 'target': str(plan.target), 'name': plan.name,
            'dotfiles': plan.dotfiles, 'records': list(plan.records)}
    _save(journal, data)
    # Read-back proves that the original bytes are durable before unlinking.
    if _load(journal) != data:
        raise ValueError(_("The dotfiles backup could not be verified."))
    from ...core.history import record_backup
    record_backup(journal)
    try:
        for record in plan.records:
            path = plan.target / record['relative']
            _parents(path, plan.target)
            if _read(path) != record['before']:
                raise ValueError(_("The Stow plan changed. Review a new preview before continuing."))
            if record['before'] is not None:
                path.unlink()
        result = read_command(runner, backend.stow_command(plan.root, plan.target, plan.name, plan.dotfiles))
        mapping = {r['relative']: Path(r['source']) for r in plan.records}
        if _planned_links(result.output, mapping) != tuple(sorted(mapping)):
            raise ValueError(_("The Stow plan changed. Review a new preview before continuing."))
        result = runner.stream(backend.stow_command(plan.root, plan.target, plan.name, plan.dotfiles, simulate=False), on_line=on_line)
        if not result.ok:
            raise ValueError(result.output)
        if any(not _matches_link(plan.target / r['relative'], Path(r['source'])) for r in plan.records):
            raise ValueError(_("The created dotfiles links could not be verified."))
        data['status'] = 'active'
        _save(journal, data)
    except Exception as exc:
        try:
            _restore(plan.target, plan.records)
            data['status'] = 'undone'
            _save(journal, data)
        except Exception as recovery:
            raise ValueError(_("Dotfiles recovery is incomplete. Backup: {path}\n{error}").format(path=journal, error=recovery)) from exc
        raise ValueError(_("Activation failed; the previous configuration was restored. Backup: {path}\n{error}").format(path=journal, error=exc)) from exc
    return _("Stow activated. Backup and undo record: {path}").format(path=journal)


@dataclass(frozen=True)
class UndoPlan:
    root: Path
    target: Path
    name: str
    dotfiles: bool
    records: tuple
    journal: Path = None
    data: dict = None


def preview_undo(repository, target, name, dotfiles=False):
    root, target = Path(repository).expanduser().resolve(), backend.directory(target)
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", name):
        raise ValueError(_("Invalid Stow package name."))
    journal = active_journal(root, target, name, dotfiles)
    if journal:
        data = _load(journal)
        records = tuple(data['records'])
    else:
        root = backend.directory(root)
        tree = backend._tree(backend._package(root, name))
        mapping = _mapping(root, target, name, tree, dotfiles)
        records = tuple({'relative': key, 'source': str(source), 'before': None}
                        for key, source in mapping.items() if _matches_link(target / key, source))
        data = None
    if not records:
        raise ValueError(_("No dotfiles links were found to undo."))
    # Validate journal paths, payloads and the present target without writing.
    for record in records:
        relative = Path(record['relative'])
        source = Path(record['source'])
        if (relative.is_absolute() or '..' in relative.parts or not relative.parts or
                not source.is_absolute() or '..' in source.parts or not source.is_relative_to(root / name)):
            raise ValueError(_("Invalid dotfiles backup."))
        path = target / relative
        _parents(path, target)
        before = record['before']
        if before is not None:
            if before.get('kind') == 'file':
                if len(base64.b64decode(before['value'], validate=True)) > MAX_FILE or type(before['mode']) is not int or not 0 <= before['mode'] <= 0o7777:
                    raise ValueError(_("Invalid dotfiles backup."))
            elif before.get('kind') != 'link' or not isinstance(before['value'], str) or '\x00' in before['value']:
                raise ValueError(_("Invalid dotfiles backup."))
        if not _matches_link(path, source) and _read(path) not in (None, before):
            raise ValueError(_("A target changed outside MintTweaks and was preserved: {path}").format(path=path))
    return UndoPlan(root, target, name, dotfiles, records, journal, data)


def managed_packages(root, target, dotfiles=False):
    directory = _store()
    if not directory.exists():
        return {}
    result = {}
    for path in directory.glob('*.json'):
        data = _load(path)
        if (data['root'], data['target'], data['dotfiles']) == (str(root), str(target), dotfiles) and data['status'] != 'undone':
            result[data['name']] = tuple(data['records'])
    return result


def undo(runner, plan):
    if runner.dry_run:
        return _("Simulation: no dotfiles links were removed or backups restored.")
    checked = preview_undo(plan.root, plan.target, plan.name, plan.dotfiles)
    if checked != plan:
        raise ValueError(_("The undo plan changed. Review a new preview before continuing."))
    from ...core.history import record_backup
    record_backup(plan.journal)
    _restore(plan.target, plan.records)
    if plan.journal:
        data = dict(plan.data, status='undone')
        _save(plan.journal, data)
    return _("Stow undone. Previous configurations were restored; backups were kept.")
