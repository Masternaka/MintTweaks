"""Portable catalog choices only: no versions, arbitrary packages or sources."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from ...i18n import _
from . import backend

MAX_BYTES = 32 * 1024
KIND = 'minttweaks-application-selection'


def _ids(ids):
    apps = backend.catalog()
    if (not isinstance(ids, (tuple, list)) or not ids or len(ids) > len(apps)
            or any(not isinstance(key, str) or key not in apps for key in ids)
            or len(ids) != len(set(ids))):
        raise ValueError(_("Choose distinct applications from the current catalog only."))
    return tuple(ids)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(_("Duplicate field in the application selection file."))
        result[key] = value
    return result


@dataclass(frozen=True)
class ExportPlan:
    ids: tuple
    text: str


@dataclass(frozen=True)
class ImportPlan:
    source: Path
    digest: str
    ids: tuple


def preview_export(ids):
    ids = _ids(ids)
    apps = backend.catalog()
    data = {'schema_version': 1, 'kind': KIND,
            'applications': [{'id': key, 'package': apps[key].package} for key in ids]}
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError(_("The application selection file is too large."))
    return ExportPlan(ids, text)


def _decode(raw):
    try:
        data = json.loads(raw, object_pairs_hook=_unique)
        if (not isinstance(data, dict) or set(data) != {'schema_version', 'kind', 'applications'}
                or type(data['schema_version']) is not int or data['schema_version'] != 1 or data['kind'] != KIND
                or not isinstance(data['applications'], list)):
            raise ValueError('Unsupported selection format')
        entries = data['applications']
        if any(not isinstance(entry, dict) or set(entry) != {'id', 'package'} for entry in entries):
            raise ValueError('Invalid application entry')
        ids = _ids([entry['id'] for entry in entries])
        apps = backend.catalog()
        if any(entry['package'] != apps[entry['id']].package for entry in entries):
            raise ValueError('Package does not match the catalog')
        return ids
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ValueError(_("This file is not a supported selection from the current application catalog. The source file was preserved.")) from exc


def preview_import(runner, filename):
    if runner.dry_run:
        raise ValueError(_("Application selection import is unavailable in simulation mode."))
    source = Path(filename).expanduser().absolute()
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError(_("Choose a regular JSON application selection file."))
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(_("The application selection file is too large."))
    return ImportPlan(source, hashlib.sha256(raw).hexdigest(), _decode(raw))


def confirm_import(runner, plan):
    if runner.dry_run:
        return ()
    if preview_import(runner, plan.source) != plan:
        raise ValueError(_("The application selection file changed after its preview. Review it again."))
    return plan.ids


def export(runner, plan, filename):
    if runner.dry_run:
        return None
    if preview_export(plan.ids) != plan:
        raise ValueError(_("The catalog selection changed after its preview. Review it again."))
    target = Path(filename).expanduser()
    if not target.is_absolute():
        raise ValueError(_("Choose an absolute path for the application selection export."))
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.mtk-app-selection-', delete=False) as output:
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


def disposition(entry):
    if entry is None or entry.error:
        return 'unavailable'
    if entry.installed:
        return 'installed'
    if entry.installable:
        return 'ready'
    if entry.github_available:
        return 'github'
    return 'unavailable'
