"""Preview and back up an explicit allowlist of user configuration files."""

from __future__ import annotations

import base64
import datetime
import json
import os
import stat
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

MAX_FILE = 128 * 1024
MAX_BACKUP = 2 * 1024 * 1024


@dataclass(frozen=True)
class Change:
    slot: str
    before: Optional[bytes]
    after: Optional[bytes]
    mode: int = 0o600
    after_mode: Optional[int] = None


@dataclass
class FileOutcome:
    ok: bool
    backup: Optional[Path] = None
    errors: Dict[str, str] = field(default_factory=dict)
    simulated: bool = False


def read_file(path: Path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None, 0o600
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise ValueError("Configuration must be a regular file, not a link: " + str(path))
    with path.open("rb") as source:
        data = source.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError("Configuration is too large: " + str(path))
    return data, stat.S_IMODE(info.st_mode) & 0o777


def atomic_write(path: Path, data: Optional[bytes], mode=0o600):
    if data is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".mtk-", delete=False) as output:
            staged = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        staged.chmod(mode)
        os.replace(staged, path)
    finally:
        if staged is not None and staged.exists():
            staged.unlink()


def preview(targets: Dict[str, Path], updates: Dict[str, Optional[bytes]]):
    if not updates or not set(updates) <= set(targets):
        raise ValueError("Unknown configuration target.")
    changes = []
    for slot, after in updates.items():
        if after is not None and (not isinstance(after, bytes) or len(after) > MAX_FILE):
            raise ValueError("Invalid configuration content.")
        before, mode = read_file(targets[slot])
        if before != after:
            changes.append(Change(slot, before, after, mode))
    return changes


def save_backup(directory: Path, targets, changes):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "schema_version": 1, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files": [{"slot": change.slot, "path": str(targets[change.slot]), "mode": change.mode,
                   "before": None if change.before is None else base64.b64encode(change.before).decode("ascii")}
                  for change in changes],
    }
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(data) > MAX_BACKUP:
        raise ValueError("Backup is too large.")
    path = directory / (uuid.uuid4().hex + ".json")
    with path.open("xb") as output:
        os.chmod(path, 0o600)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return path


def apply(runner, targets, changes, backup_directory: Path):
    if runner.dry_run:
        return FileOutcome(True, simulated=True)
    if not changes:
        return FileOutcome(True)
    if len({change.slot for change in changes}) != len(changes):
        raise ValueError("Duplicate configuration target.")
    for change in changes:
        if change.after is not None and (not isinstance(change.after, bytes) or len(change.after) > MAX_FILE):
            raise ValueError("Invalid configuration content.")
        if change.after_mode is not None and (type(change.after_mode) is not int or not 0 <= change.after_mode <= 0o777):
            raise ValueError("Invalid configuration permissions.")
        if change.slot not in targets or read_file(targets[change.slot]) != (change.before, change.mode):
            raise ValueError("Configuration changed; review a new preview.")
    backup = save_backup(backup_directory, targets, changes)
    attempted = []
    try:
        for change in changes:
            if read_file(targets[change.slot]) != (change.before, change.mode):
                raise ValueError("Configuration changed during application.")
            attempted.append(change)
            atomic_write(targets[change.slot], change.after, change.mode if change.after_mode is None else change.after_mode)
        for change in changes:
            expected_mode = change.mode if change.after_mode is None else change.after_mode
            actual = read_file(targets[change.slot])
            if actual[0] != change.after or (change.after is not None and actual[1] != expected_mode):
                raise ValueError("Configuration write could not be verified.")
    except Exception as exc:
        errors = {"operation": str(exc)}
        for change in reversed(attempted):
            try:
                actual, mode = read_file(targets[change.slot])
                if actual == change.before and (actual is None or mode == change.mode):
                    continue
                if actual != change.after:
                    raise ValueError("An external change was preserved; recovery is incomplete.")
                atomic_write(targets[change.slot], change.before, change.mode)
                if read_file(targets[change.slot])[0] != change.before:
                    raise ValueError("Recovery could not be verified.")
            except Exception as recovery:
                errors[change.slot] = str(recovery)
        for change in attempted:
            try:
                if read_file(targets[change.slot])[0] != change.before:
                    errors.setdefault(change.slot, "The previous file contents could not be verified after recovery.")
            except Exception as recovery:
                errors[change.slot] = str(recovery)
        return FileOutcome(False, backup, errors)
    return FileOutcome(True, backup)


def restore_preview(targets, backup: Path):
    if backup.is_symlink() or not backup.is_file():
        raise ValueError("Invalid backup file.")
    with backup.open("rb") as source:
        raw = source.read(MAX_BACKUP + 1)
    if len(raw) > MAX_BACKUP:
        raise ValueError("Backup is too large.")
    data = json.loads(raw)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported backup format.")
    entries = data.get("files")
    if not isinstance(entries, list) or not entries or len(entries) > len(targets):
        raise ValueError("Invalid backup targets.")
    updates, modes = {}, {}
    for item in entries:
        slot = item["slot"]
        if slot not in targets or slot in updates or item["path"] != str(targets[slot]):
            raise ValueError("Backup does not match the current configuration targets.")
        content = item["before"]
        updates[slot] = None if content is None else base64.b64decode(content, validate=True)
        mode = item["mode"]
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise ValueError("Invalid backup permissions.")
        modes[slot] = mode
    preview(targets, updates)  # validate sizes and target types before returning
    changes = []
    for slot, after in updates.items():
        before, mode = read_file(targets[slot])
        if before != after or (after is not None and mode != modes[slot]):
            changes.append(Change(slot, before, after, mode, modes[slot]))
    return changes
