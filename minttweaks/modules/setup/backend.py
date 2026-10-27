"""Persist an optional checklist, without performing system modifications.

Progress is explicitly user-reported; opening a module never verifies a step.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ...core import paths
from ...core.runner import BaseRunner
from ...i18n import _


@dataclass(frozen=True)
class Step:
    id: str
    page: str
    title_msgid: str
    detail_msgid: str

    @property
    def title(self):
        return _(self.title_msgid)

    @property
    def detail(self):
        return _(self.detail_msgid)


STEPS = (
    Step("health", "home", _("Check the system"), _("Read the system summary and diagnostics. This step does not change any settings.")),
    Step("software", "software", _("Install native third-party software"), _("Choose Helium, Brave or Zen from their indicated APT sources. Review the package and dependency plan before administrator approval.")),
    Step("terminal", "terminal", _("Prepare shells and terminals"), _("Install shell tools, choose your login shell and customize Kitty or Alacritty with previewed, backed-up changes.")),
    Step("firefox", "firefox", _("Prepare Firefox"), _("Choose extensions from addons.mozilla.org in the Firefox module. Its system policy requires administrator approval and a Firefox restart.")),
    Step("cinnamon", "cinnamon", _("Choose your appearance"), _("Save or apply a Cinnamon profile. Applying changes user settings after a preview and backup; themes and fonts must already be installed.")),
    Step("samba", "samba", _("Set up sharing, if needed"), _("Configure Samba shares and accounts only if you need network sharing. Package installation, firewall and service changes are performed in the Samba module.")),
)
STEP_BY_ID = {step.id: step for step in STEPS}
LEGACY_STEP_IDS = {"health", "firefox", "cinnamon", "samba"}
STATES = {"pending", "verified", "retry"}
MAX_BYTES = 32 * 1024


class PlanError(ValueError):
    pass


@dataclass
class Progress:
    state: str = "pending"
    note: str = ""


@dataclass
class Plan:
    revision: str = ""
    selected: List[str] = field(default_factory=list)
    progress: Dict[str, Progress] = field(default_factory=lambda: {step.id: Progress() for step in STEPS})
    updated_at: str = ""

    @property
    def next_step(self) -> Optional[Step]:
        return next((STEP_BY_ID[key] for key in self.selected if self.progress[key].state != "verified"), None)

    @property
    def verified(self) -> int:
        return sum(self.progress[key].state == "verified" for key in self.selected)


def valid_note(note):
    if not isinstance(note, str) or len(note) > 500 or any(unicodedata.category(char) == "Cc" for char in note):
        raise PlanError(_("Use a note of up to 500 characters without control characters."))
    note.encode("utf-8")
    return note


def decode(data) -> Plan:
    if not isinstance(data, dict) or set(data) != {"schema_version", "revision", "selected", "progress", "updated_at"}:
        raise PlanError("Invalid checklist structure.")
    if type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2, 3):
        raise PlanError("Unsupported checklist version.")
    known_ids = (LEGACY_STEP_IDS if data["schema_version"] == 1 else
                 LEGACY_STEP_IDS | {"software"} if data["schema_version"] == 2 else set(STEP_BY_ID))
    revision = data["revision"]
    if not isinstance(revision, str) or uuid.UUID(revision).hex != revision:
        raise PlanError("Invalid checklist revision.")
    updated = datetime.datetime.fromisoformat(data["updated_at"])
    if updated.utcoffset() is None:
        raise PlanError("Checklist date must include a timezone.")
    selected = data["selected"]
    if not isinstance(selected, list) or any(not isinstance(key, str) or key not in known_ids for key in selected):
        raise PlanError("Invalid checklist steps.")
    if len(selected) != len(set(selected)):
        raise PlanError("Duplicate checklist steps.")
    progress = data["progress"]
    if not isinstance(progress, dict) or set(progress) != known_ids:
        raise PlanError("Invalid checklist progress.")
    result = {step.id: Progress() for step in STEPS}
    for key, value in progress.items():
        if not isinstance(value, dict) or set(value) != {"state", "note"} or not isinstance(value["state"], str) or value["state"] not in STATES:
            raise PlanError("Invalid step state.")
        result[key] = Progress(value["state"], valid_note(value["note"]))
    return Plan(revision, list(selected), result, data["updated_at"])


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PlanError("Duplicate checklist field.")
        value[key] = item
    return value


def load_plan(path: Optional[Path] = None) -> Plan:
    path = Path(path) if path is not None else paths.SETUP_PLAN
    if path.is_symlink():
        raise PlanError(_("The checklist file is a symbolic link and was left unchanged."))
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return Plan()
    if len(raw) > MAX_BYTES:
        raise PlanError("Checklist file is too large.")
    try:
        return decode(json.loads(raw, object_pairs_hook=unique_object))
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise PlanError(_("The saved checklist could not be read and was preserved: {error}").format(error=exc)) from exc


def save_plan(runner: BaseRunner, plan: Plan, selected: List[str], step_id: Optional[str] = None,
              state: Optional[str] = None, note: str = "", path: Optional[Path] = None) -> Plan:
    if runner.dry_run:
        raise PlanError(_("Checklist progress is not saved in simulation mode."))
    target = Path(path) if path is not None else paths.SETUP_PLAN
    current = load_plan(target)
    if current.revision != plan.revision:
        raise PlanError(_("The checklist changed. Reload it before saving."))
    data = {
        "schema_version": 3, "revision": uuid.uuid4().hex,
        "selected": selected,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "progress": {key: {"state": value.state, "note": value.note} for key, value in current.progress.items()},
    }
    if step_id is not None:
        if step_id not in selected or step_id not in STEP_BY_ID or state not in STATES:
            raise PlanError("Cannot update an unselected or unknown step.")
        data["progress"][step_id] = {"state": state, "note": valid_note(note)}
    result = decode(data)
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".setup-", delete=False) as output:
            staged = Path(output.name)
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        os.replace(staged, target)
    finally:
        if staged is not None and staged.exists():
            staged.unlink()
    return result
