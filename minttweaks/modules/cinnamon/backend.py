"""Read a bounded set of Cinnamon settings and save named local snapshots.

Only allowlisted settings are changed, after preview and a durable local backup.
No theme asset is copied. The backend has no GTK dependency.
"""

from __future__ import annotations

import ast
import datetime
import io
import json
import os
import tempfile
import tokenize
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ...core import paths
from ...core.runner import BaseRunner, cmd, read_command
from ...i18n import _


@dataclass(frozen=True)
class Setting:
    schema: str
    key: str
    title_msgid: str

    @property
    def id(self) -> str:
        return self.schema + "/" + self.key

    @property
    def title(self) -> str:
        return _(self.title_msgid)


SETTINGS = (
    Setting("org.cinnamon.theme", "name", _("Cinnamon theme")),
    Setting("org.cinnamon.desktop.interface", "gtk-theme", _("Application theme")),
    Setting("org.cinnamon.desktop.wm.preferences", "theme", _("Window borders")),
    Setting("org.cinnamon.desktop.interface", "icon-theme", _("Icons")),
    Setting("org.cinnamon.desktop.interface", "cursor-theme", _("Cursor theme")),
    Setting("org.cinnamon.desktop.interface", "font-name", _("Interface font")),
    Setting("org.cinnamon.desktop.wm.preferences", "titlebar-font", _("Window title font")),
)
SETTING_IDS = {setting.id for setting in SETTINGS}
MAX_FILE_BYTES = 64 * 1024


def valid_value(value) -> bool:
    if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


def unique_object(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("Duplicate JSON key: " + key)
        document[key] = value
    return document


class ProfileError(ValueError):
    """An incomplete capture or an invalid profile cannot be saved or loaded."""


def timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class Snapshot:
    captured_at: str
    values: Dict[str, str] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return set(self.values) == SETTING_IDS and not self.errors


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    captured_at: str
    settings: Dict[str, str]


@dataclass
class Catalog:
    profiles: List[Profile] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)


def capture(runner: BaseRunner) -> Snapshot:
    snapshot = Snapshot(timestamp())
    for setting in SETTINGS:
        try:
            snapshot.values[setting.id] = read_value(runner, setting)
        except Exception as exc:
            snapshot.errors[setting.id] = str(exc)
    return snapshot


def read_value(runner: BaseRunner, setting: Setting) -> str:
    result = read_command(runner, cmd("gsettings", "get", setting.schema, setting.key), timeout=5)
    raw = result.stdout.strip()
    if len(raw) > 8192 or not raw.startswith(("'", '"')):
        raise ProfileError("Expected a GSettings string value.")
    tokens = [token.type for token in tokenize.generate_tokens(io.StringIO(raw).readline)
              if token.type not in (tokenize.NEWLINE, tokenize.ENDMARKER)]
    if tokens != [tokenize.STRING]:
        raise ProfileError("Expected one GSettings string value.")
    value = ast.literal_eval(raw)
    if not valid_value(value):
        raise ProfileError("Invalid GSettings string value.")
    return value


def validate_name(name: str) -> str:
    if not isinstance(name, str):
        raise ProfileError(_("Enter a profile name of 1 to 80 characters, without control characters."))
    try:
        name.encode("utf-8")
    except UnicodeError as exc:
        raise ProfileError(_("Enter a profile name of 1 to 80 characters, without control characters.")) from exc
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ProfileError(_("Enter a profile name of 1 to 80 characters, without control characters."))
    name = name.strip()
    if not 1 <= len(name) <= 80:
        raise ProfileError(_("Enter a profile name of 1 to 80 characters, without control characters."))
    return name


def decode_profile(data: dict, expected_id: str) -> Profile:
    if not isinstance(data, dict) or set(data) != {"schema_version", "id", "name", "captured_at", "settings"}:
        raise ProfileError("Invalid profile structure.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ProfileError("Unsupported profile format version.")
    if not isinstance(expected_id, str) or uuid.UUID(expected_id).hex != expected_id or data["id"] != expected_id:
        raise ProfileError("Profile identifier does not match its filename.")
    name = validate_name(data["name"])
    if name != data["name"]:
        raise ProfileError("Profile name is not normalized.")
    captured = datetime.datetime.fromisoformat(data["captured_at"])
    if captured.utcoffset() is None:
        raise ProfileError("Profile capture time must include a timezone.")
    settings = data["settings"]
    if not isinstance(settings, dict) or set(settings) != SETTING_IDS:
        raise ProfileError("Profile settings are incomplete or unsupported.")
    if any(not valid_value(value) for value in settings.values()):
        raise ProfileError("Invalid profile setting value.")
    return Profile(expected_id, name, data["captured_at"], dict(settings))


def list_profiles(directory: Optional[Path] = None) -> Catalog:
    directory = Path(directory) if directory is not None else paths.PROFILE_DIR
    catalog = Catalog()
    try:
        files = sorted(directory.iterdir())
    except FileNotFoundError:
        return catalog
    for path in files:
        if path.suffix != ".json":
            continue
        try:
            if path.is_symlink() or not path.is_file():
                raise ProfileError("Profile must be a regular file, not a symbolic link.")
            with path.open("rb") as source:
                raw = source.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                raise ProfileError("Profile is too large.")
            profile = decode_profile(json.loads(raw, object_pairs_hook=unique_object), path.stem)
            catalog.profiles.append(profile)
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            catalog.errors[path.name] = str(exc)
    catalog.profiles.sort(key=lambda profile: (profile.name.casefold(), profile.id))
    return catalog


def save_profile(runner: BaseRunner, name: str, directory: Optional[Path] = None) -> Profile:
    name = validate_name(name)
    if runner.dry_run:
        raise ProfileError(_("Profiles are not saved in simulation mode."))
    snapshot = capture(runner)
    if not snapshot.complete:
        raise ProfileError(_("The settings could not all be read. Refresh before saving a profile."))
    return store_snapshot(snapshot, name, directory)


def store_snapshot(snapshot: Snapshot, name: str, directory: Optional[Path] = None) -> Profile:
    name = validate_name(name)
    if not snapshot.complete:
        raise ProfileError("Cannot store an incomplete snapshot.")
    identifier = uuid.uuid4().hex
    data = {"schema_version": 1, "id": identifier, "name": name,
            "captured_at": snapshot.captured_at, "settings": snapshot.values}
    profile = decode_profile(data, identifier)
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if len(rendered.encode("utf-8")) > MAX_FILE_BYTES:
        raise ProfileError("Profile is too large.")
    directory = Path(directory) if directory is not None else paths.PROFILE_DIR
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         prefix=".profile-", suffix=".tmp", delete=False) as output:
            staged = Path(output.name)
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        # Publish a complete file atomically; even a UUID collision never
        # replaces a previously saved profile.
        os.link(staged, directory / (identifier + ".json"))
    finally:
        if staged is not None:
            staged.unlink()
    return profile


@dataclass(frozen=True)
class ApplyPlan:
    profile: Profile
    before: Snapshot

    @property
    def changes(self) -> List[Setting]:
        return [setting for setting in SETTINGS if self.before.values[setting.id] != self.profile.settings[setting.id]]


@dataclass
class ApplyOutcome:
    ok: bool
    message: str
    backup: Optional[Profile] = None
    rollback_errors: Dict[str, str] = field(default_factory=dict)
    simulated: bool = False


def validated_profile(profile: Profile) -> Profile:
    return decode_profile({"schema_version": 1, "id": profile.id, "name": profile.name,
                           "captured_at": profile.captured_at, "settings": profile.settings}, profile.id)


def check_writable(runner: BaseRunner, settings: List[Setting]) -> None:
    for setting in settings:
        result = read_command(runner, cmd("gsettings", "writable", setting.schema, setting.key), timeout=5)
        if result.stdout.strip() != "true":
            raise ProfileError(_("This setting cannot be changed: {setting}").format(setting=setting.title))


def preview_profile(runner: BaseRunner, profile: Profile) -> ApplyPlan:
    target = validated_profile(profile)
    before = capture(runner)
    if not before.complete:
        raise ProfileError(_("The current appearance could not all be read. Nothing was changed."))
    plan = ApplyPlan(target, before)
    check_writable(runner, plan.changes)
    return plan


def write_value(runner: BaseRunner, setting: Setting, value: str) -> None:
    # JSON double-quoted UTF-8 strings use escapes supported by GVariant.
    result = runner.run(cmd("gsettings", "set", setting.schema, setting.key,
                            json.dumps(value, ensure_ascii=False)), timeout=10)
    if not result.ok:
        raise ProfileError(result.output or f"gsettings set failed (rc={result.returncode}).")
    if read_value(runner, setting) != value:
        raise ProfileError(_("The setting did not keep the requested value: {setting}").format(setting=setting.title))


def apply_profile(runner: BaseRunner, plan: ApplyPlan, backup_directory: Optional[Path] = None) -> ApplyOutcome:
    target = validated_profile(plan.profile)
    if not plan.before.complete or any(not valid_value(value) for value in plan.before.values.values()):
        raise ProfileError("The preview baseline is invalid.")
    plan = ApplyPlan(target, Snapshot(plan.before.captured_at, dict(plan.before.values)))
    if runner.dry_run:
        return ApplyOutcome(True, _("Simulation: no appearance settings or backups were written."), simulated=True)
    current = capture(runner)
    if not current.complete or current.values != plan.before.values:
        raise ProfileError(_("The appearance changed or could not be checked. Review a new preview before applying."))
    if not plan.changes:
        return ApplyOutcome(True, _("The selected profile already matches the current appearance."))
    check_writable(runner, plan.changes)
    directory = Path(backup_directory) if backup_directory is not None else paths.PROFILE_BACKUP_DIR
    backup = store_snapshot(current, _("Before changing Cinnamon appearance"), directory)
    attempted = []
    try:
        for setting in plan.changes:
            if read_value(runner, setting) != plan.before.values[setting.id]:
                raise ProfileError(_("A setting changed during application: {setting}").format(setting=setting.title))
            # A command which fails or times out may already have changed its
            # value; include that key in recovery checks as well.
            attempted.append(setting)
            write_value(runner, setting, target.settings[setting.id])
        verified = capture(runner)
        if not verified.complete or verified.values != target.settings:
            raise ProfileError(_("The final appearance could not be verified."))
    except Exception as exc:
        errors = {}
        for setting in reversed(attempted):
            try:
                actual = read_value(runner, setting)
                if actual == plan.before.values[setting.id]:
                    continue
                if actual != target.settings[setting.id]:
                    raise ProfileError(_("The value changed outside this operation; it was not overwritten."))
                write_value(runner, setting, plan.before.values[setting.id])
            except Exception as recovery_error:
                errors[setting.id] = str(recovery_error)
        if attempted:
            recovered = capture(runner)
            for setting in attempted:
                if recovered.values.get(setting.id) != plan.before.values[setting.id]:
                    errors.setdefault(setting.id, recovered.errors.get(setting.id) or
                                      _("The previous value could not be verified after recovery."))
        message = (_("Application failed; recovery is incomplete. The backup was preserved.") if errors else
                   _("Application failed; the values changed by this operation were restored."))
        return ApplyOutcome(False, message + "\n" + str(exc), backup, errors)
    return ApplyOutcome(True, _("The profile was applied and its values were verified."), backup)
