"""Transfer one validated profile; never apply settings or replace user files."""
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


@dataclass(frozen=True)
class ExportPlan:
    profile: backend.Profile
    text: str

    @property
    def filename(self):
        return 'minttweaks-cinnamon-' + self.profile.id + '.json'


@dataclass(frozen=True)
class ImportPlan:
    source: Path
    digest: str
    profile: backend.Profile
    directory: Path


def preview_export(profile):
    profile = backend.validated_profile(profile)
    document = {'schema_version': 1, 'id': profile.id, 'name': profile.name,
                'captured_at': profile.captured_at, 'settings': dict(profile.settings)}
    text = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    if len(text.encode('utf-8')) > backend.MAX_FILE_BYTES:
        raise backend.ProfileError(_("The profile is too large to transfer."))
    return ExportPlan(profile, text)


def export_profile(runner, plan, filename):
    if runner.dry_run:
        return None
    if preview_export(plan.profile) != plan:
        raise backend.ProfileError(_("The profile changed after its preview. Review a new preview."))
    target = Path(filename).expanduser()
    if not target.is_absolute():
        raise backend.ProfileError(_("Choose an absolute path for the profile export."))
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.mtk-profile-export-', delete=False) as output:
            staged = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            output.write(plan.text.encode('utf-8'))
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(staged, target)
        except FileExistsError as exc:
            raise backend.ProfileError(_("This file already exists. Choose a new filename; no existing file was replaced.")) from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return target


def _read_profile(source):
    # Nonblocking + fstat prevents a file replaced with a FIFO from blocking the
    # reader. NoFollow rejects source symlinks even after an earlier check.
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise backend.ProfileError(_("Choose a regular JSON profile file."))
        raw = handle.read(backend.MAX_FILE_BYTES + 1)
    if len(raw) > backend.MAX_FILE_BYTES:
        raise backend.ProfileError(_("The profile is too large to transfer."))
    try:
        document = json.loads(raw, object_pairs_hook=backend.unique_object)
        profile = backend.decode_profile(document, document.get('id') if isinstance(document, dict) else '')
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise backend.ProfileError(_("The imported file is not a supported complete Cinnamon profile.")) from exc
    return raw, profile


def _directory(directory=None):
    target = Path(directory if directory is not None else backend.paths.PROFILE_DIR).absolute()
    for parent in (target, *target.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise backend.ProfileError(_("The profile storage directory is unsafe. No profile was imported."))
    return target


def preview_import(runner, filename, directory=None):
    if runner.dry_run:
        raise backend.ProfileError(_("Profile import previews are unavailable in simulation mode."))
    source = Path(filename).expanduser().absolute()
    raw, profile = _read_profile(source)
    return ImportPlan(source, hashlib.sha256(raw).hexdigest(), profile, _directory(directory))


def import_profile(runner, plan):
    if runner.dry_run:
        return None
    checked = preview_import(runner, plan.source, plan.directory)
    if checked != plan:
        raise backend.ProfileError(_("The import file changed after its preview. Review a new preview."))
    profile = checked.profile
    imported = backend.store_snapshot(backend.Snapshot(profile.captured_at, dict(profile.settings)),
                                      profile.name, checked.directory)
    try:
        _raw, verified = _read_profile(checked.directory / (imported.id + '.json'))
        if verified != imported:
            raise ValueError('Profile read-back mismatch')
    except (OSError, ValueError) as exc:
        raise backend.ProfileError(_("A new profile was saved but could not be verified. Reload the profile catalog before retrying.")) from exc
    return imported
