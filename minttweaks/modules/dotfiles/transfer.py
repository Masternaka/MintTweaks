"""Portable references only. Import prepares paths without cloning or linking."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from ...i18n import _
from . import backend

MAX_BYTES = 32 * 1024
KIND = 'minttweaks-dotfiles-reference'


@dataclass(frozen=True)
class Reference:
    repository_url: str
    packages: tuple
    dotfiles: bool


@dataclass(frozen=True)
class ExportPlan:
    reference: Reference
    text: str


@dataclass(frozen=True)
class ImportPlan:
    source: Path
    digest: str
    reference: Reference


@dataclass(frozen=True)
class LocalImport:
    plan: ImportPlan
    repository: Path
    target: Path


def reference(url, packages, dotfiles=False):
    url = backend.repository_url(url)
    if (not isinstance(packages, (tuple, list)) or not 1 <= len(packages) <= 256
            or any(not isinstance(name, str) or len(name) > 255
                   or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.+-]*', name)
                   or name in {'docs', 'scripts', 'tests', 'tools', 'node_modules'} for name in packages)
            or len(packages) != len(set(packages)) or type(dotfiles) is not bool):
        raise ValueError(_("Choose distinct supported Stow configuration names and a boolean dotfiles option."))
    return Reference(url, tuple(packages), dotfiles)


def preview_export(url, packages, dotfiles=False):
    ref = reference(url, packages, dotfiles)
    data = {'schema_version': 1, 'kind': KIND, 'repository_url': ref.repository_url,
            'packages': list(ref.packages), 'dotfiles': ref.dotfiles}
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError(_("The dotfiles reference file is too large."))
    return ExportPlan(ref, text)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate reference field')
        result[key] = value
    return result


def preview_import(runner, filename):
    if runner.dry_run:
        raise ValueError(_("Dotfiles reference import is unavailable in simulation mode."))
    source = Path(filename).expanduser().absolute()
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError(_("Choose a regular JSON dotfiles reference file."))
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(_("The dotfiles reference file is too large."))
    try:
        data = json.loads(raw, object_pairs_hook=_unique)
        if (not isinstance(data, dict) or set(data) != {'schema_version', 'kind', 'repository_url', 'packages', 'dotfiles'}
                or type(data['schema_version']) is not int or data['schema_version'] != 1 or data['kind'] != KIND):
            raise ValueError('Unsupported reference format')
        ref = reference(data['repository_url'], data['packages'], data['dotfiles'])
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ValueError(_("This file is not a supported dotfiles reference. The source file was preserved.")) from exc
    return ImportPlan(source, hashlib.sha256(raw).hexdigest(), ref)


def local_paths(repository, target):
    if not str(repository).strip() or not str(target).strip():
        raise ValueError(_("Choose the local repository directory and link target."))
    repository, target = Path(repository).expanduser(), Path(target).expanduser()
    if not repository.is_absolute() or not target.is_absolute() or '..' in repository.parts or '..' in target.parts:
        raise ValueError(_("Choose absolute local paths without parent traversal."))
    target = backend.directory(target)
    if os.path.lexists(repository):
        repository = backend.directory(repository)
    else:
        repository = backend.directory(repository.parent) / repository.name
    if target == repository or target.is_relative_to(repository):
        raise ValueError(_("The target must be outside the dotfiles directory."))
    return repository, target


def prepare_import(runner, plan, repository, target):
    if runner.dry_run:
        return None
    if preview_import(runner, plan.source) != plan:
        raise ValueError(_("The dotfiles reference changed after its preview. Review it again."))
    repository, target = local_paths(repository, target)
    return LocalImport(plan, repository, target)


def confirm_import(runner, prepared):
    if runner.dry_run:
        return None
    checked = prepare_import(runner, prepared.plan, prepared.repository, prepared.target)
    if checked != prepared:
        raise ValueError(_("The local dotfiles paths changed after the preview. Choose them again."))
    return checked


def export(runner, plan, filename):
    if runner.dry_run:
        return None
    ref = plan.reference
    if preview_export(ref.repository_url, ref.packages, ref.dotfiles) != plan:
        raise ValueError(_("The dotfiles reference changed after its preview. Review it again."))
    target = Path(filename).expanduser()
    if not target.is_absolute():
        raise ValueError(_("Choose an absolute path for the dotfiles reference export."))
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.mtk-dotfiles-reference-', delete=False) as output:
            staged = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            output.write(plan.text.encode('utf-8'))
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(staged, target)
        except FileExistsError as exc:
            raise ValueError(_("This file already exists. Choose a new filename; no existing file was replaced.")) from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return target
