"""Firefox extension catalogue and policy management.

Firefox has no API for installing an extension silently.  The supported route is
the ``ExtensionSettings`` enterprise policy: Firefox reads it at startup and
downloads the add-ons from addons.mozilla.org itself, so signatures are checked
by the browser.  This module keeps that policy narrow:

* only extensions from :data:`CATALOG` can be requested;
* existing policies and unrelated extension entries are preserved;
* an entry that was not written by MintTweaks is never overwritten;
* the privileged write goes through the ``mtk-firefox`` helper, which repeats
  every check and keeps a root-owned backup.
"""

from __future__ import annotations

import configparser
import copy
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ...core import paths
from ...core.runner import BaseRunner, Command, Result, cmd
from ...i18n import _

POLICY_PATH = Path("/etc/firefox/policies/policies.json")
INSTALLED_HELPER = Path("/usr/lib/minttweaks/mtk-firefox")
AMO_LATEST = "https://addons.mozilla.org/firefox/downloads/latest/{addon}/latest.xpi"
INSTALLATION_MODE = "normal_installed"


@dataclass(frozen=True)
class Extension:
    """One add-on we are willing to install."""

    id: str
    name: str
    description_msgid: str

    @property
    def description(self) -> str:
        return _(self.description_msgid)

    @property
    def install_url(self) -> str:
        return AMO_LATEST.format(addon=self.id)

    @property
    def policy(self) -> Dict[str, str]:
        return {"installation_mode": INSTALLATION_MODE, "install_url": self.install_url}


CATALOG: Tuple[Extension, ...] = (
    Extension(
        id="uBlock0@raymondhill.net",
        name="uBlock Origin",
        description_msgid=_("Content blocker for ads, trackers and malware domains."),
    ),
    Extension(
        id="jid1-MnnxcxisBPnSXQ@jetpack",
        name="Privacy Badger",
        description_msgid=_("Blocks trackers that follow you across sites."),
    ),
    Extension(
        id="{74145f27-f039-47ce-a470-a662b129930a}",
        name="ClearURLs",
        description_msgid=_("Removes tracking parameters from links before pages load."),
    ),
    Extension(
        id="{446900e4-71c2-419f-a6a7-df9c091e268b}",
        name="Bitwarden Password Manager",
        description_msgid=_("Open-source password manager."),
    ),
    Extension(
        id="addon@darkreader.org",
        name="Dark Reader",
        description_msgid=_("Generates dark themes for every website."),
    ),
    Extension(
        id="FirefoxColor@mozilla.com",
        name="Firefox Color",
        description_msgid=_("Creates and applies custom Firefox colour themes."),
    ),
    Extension(
        id="jid0-adyhmvsP91nUO8pRv0Mn2VKeB84@jetpack",
        name="Raindrop.io",
        description_msgid=_("Bookmark manager for links, articles and files."),
    ),
    Extension(
        id="clipper@obsidian.md",
        name="Obsidian Web Clipper",
        description_msgid=_("Saves web pages to an Obsidian vault."),
    ),
    Extension(
        id="tab-stash@condordes.net",
        name="Tab Stash",
        description_msgid=_("Stashes tabs into a list you can restore later."),
    ),
    Extension(
        id="{531906d3-e22f-4a6c-a102-8057b88a1a63}",
        name="SingleFile",
        description_msgid=_("Saves a complete web page as a single HTML file."),
    ),
    Extension(
        id="side-view@mozilla.org",
        name="Side View",
        description_msgid=_("Opens a page in a sidebar next to the current one."),
    ),
    Extension(
        id="drag_to_privew@uxer",
        name="Peek Pop: Link Preview",
        description_msgid=_("Previews links in a popup without leaving the page."),
    ),
    Extension(
        id="sponsorBlocker@ajay.app",
        name="SponsorBlock",
        description_msgid=_("Skips sponsor segments in YouTube videos."),
    ),
    Extension(
        id="enhancerforyoutube@maximerf.addons.mozilla.org",
        name="Enhancer for YouTube",
        description_msgid=_("Adds playback and appearance controls to YouTube."),
    ),
    Extension(
        id="{b9db16a4-6edc-47ec-a1f4-b86292ed211d}",
        name="Video Download Helper",
        description_msgid=_("Downloads videos and audio from web pages."),
    ),
    Extension(
        id="amptra@keepa.com",
        name="Keepa - Amazon Price Tracker",
        description_msgid=_("Shows Amazon price history and alerts."),
    ),
)

EXTENSION_BY_ID: Dict[str, Extension] = {extension.id: extension for extension in CATALOG}


class PolicyError(ValueError):
    """The existing policy cannot be merged safely."""


@dataclass
class FirefoxStatus:
    profiles: int = 0
    installed_ids: Set[str] = field(default_factory=set)
    policy_ids: Set[str] = field(default_factory=set)
    firefox_found: bool = False
    policy_error: str = ""


@dataclass
class ApplyOutcome:
    ok: bool
    message: str
    result: Optional[Result] = None

    @property
    def output(self) -> str:
        if self.result is not None and self.result.output:
            return self.result.output
        return self.message


# --------------------------------------------------------------------------- #
# Profiles and installed extensions
# --------------------------------------------------------------------------- #
def profile_bases(home: Optional[Path] = None) -> Tuple[Path, ...]:
    base = Path(home) if home is not None else Path.home()
    return (base / ".mozilla" / "firefox",)


def _profiles_from_ini(base: Path) -> List[Path]:
    ini = base / "profiles.ini"
    if not ini.is_file():
        return []
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read(ini, encoding="utf-8")
    except (OSError, configparser.Error):
        return []

    found: List[Path] = []
    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        raw = parser.get(section, "Path", fallback="").strip()
        if not raw:
            continue
        relative = parser.get(section, "IsRelative", fallback="1").strip().lower() not in ("0", "false", "no")
        candidate = base / raw if relative else Path(raw)
        if candidate.is_dir():
            found.append(candidate)
    return found


def profile_paths(home: Optional[Path] = None) -> List[Path]:
    """Every profile directory of the native Firefox installation."""
    found: List[Path] = []
    seen: Set[Path] = set()
    for base in profile_bases(home):
        candidates = _profiles_from_ini(base)
        if not candidates and base.is_dir():
            candidates = sorted(path.parent for path in base.glob("*/extensions.json"))
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate
            if resolved not in seen:
                seen.add(resolved)
                found.append(candidate)
    return found


def _profile_extension_ids(profile: Path) -> Set[str]:
    try:
        data = json.loads((profile / "extensions.json").read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    addons = data.get("addons")
    if not isinstance(addons, list):
        return set()

    identifiers: Set[str] = set()
    for addon in addons:
        if not isinstance(addon, dict):
            continue
        if addon.get("type") != "extension":
            continue
        if addon.get("location") != "app-profile":
            continue
        addon_id = addon.get("id")
        if isinstance(addon_id, str) and addon_id:
            identifiers.add(addon_id)
    return identifiers


def installed_extension_ids(home: Optional[Path] = None) -> Set[str]:
    identifiers: Set[str] = set()
    for profile in profile_paths(home):
        identifiers |= _profile_extension_ids(profile)
    return identifiers


def firefox_installed(home: Optional[Path] = None) -> bool:
    if shutil.which("firefox") is not None:
        return True
    return any(base.is_dir() for base in profile_bases(home))


# --------------------------------------------------------------------------- #
# Policy handling
# --------------------------------------------------------------------------- #
def load_policy(path: Optional[Path] = None) -> Tuple[Optional[dict], Optional[str]]:
    """Return ``(document, error)``; a missing file is an empty document."""
    target = Path(path) if path is not None else POLICY_PATH
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, None
    except OSError as exc:
        return None, f"Could not read {target}: {exc}"
    if not text.strip():
        return {}, None
    try:
        data = json.loads(text)
    except ValueError as exc:
        return None, f"{target} is not valid JSON: {exc}"
    try:
        _settings(data)
    except PolicyError as exc:
        return None, str(exc)
    return data, None


def _policies(data: dict) -> dict:
    if not isinstance(data, dict):
        raise PolicyError("The Firefox policy file must contain a JSON object.")
    policies = data.get("policies", {})
    if not isinstance(policies, dict):
        raise PolicyError("The 'policies' entry in the Firefox policy file is not an object.")
    return policies


def _settings(data: dict) -> dict:
    settings = _policies(data).get("ExtensionSettings", {})
    if not isinstance(settings, dict):
        raise PolicyError("The 'ExtensionSettings' entry in the Firefox policy file is not an object.")
    return settings


def policy_extension_ids(data: Optional[dict]) -> Set[str]:
    if not data:
        return set()
    try:
        settings = _settings(data)
    except PolicyError:
        return set()
    return {extension.id for extension in CATALOG if settings.get(extension.id) == extension.policy}


def plan_policy(existing: Optional[dict], selected_ids: Iterable[str]) -> dict:
    """Merge the selection into an existing policy document.

    Entries MintTweaks did not write are left alone.  Selecting an extension
    whose existing entry uses another mode or URL is refused rather than
    silently weakening an administrator's policy.
    """
    selected = set(selected_ids)
    unknown = selected - set(EXTENSION_BY_ID)
    if unknown:
        raise PolicyError(f"Unknown extension(s): {', '.join(sorted(unknown))}")

    data = copy.deepcopy(existing) if existing else {}
    if not isinstance(data, dict):
        raise PolicyError("The Firefox policy file must contain a JSON object.")

    policies = data.setdefault("policies", {})
    if not isinstance(policies, dict):
        raise PolicyError("The 'policies' entry in the Firefox policy file is not an object.")
    settings = policies.setdefault("ExtensionSettings", {})
    if not isinstance(settings, dict):
        raise PolicyError("The 'ExtensionSettings' entry in the Firefox policy file is not an object.")

    for extension in CATALOG:
        current = settings.get(extension.id)
        wanted = extension.policy
        if extension.id in selected:
            if current is not None and current != wanted:
                raise PolicyError(
                    f"Extension {extension.id} already has a different Firefox policy; refusing to overwrite it."
                )
            settings[extension.id] = wanted
        elif current == wanted:
            del settings[extension.id]

    if not settings:
        policies.pop("ExtensionSettings", None)
    if not policies:
        data.pop("policies", None)
    return data


def render_policy(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def collect_status(home: Optional[Path] = None, policy_path: Optional[Path] = None) -> FirefoxStatus:
    profiles = profile_paths(home)
    installed: Set[str] = set()
    for profile in profiles:
        installed |= _profile_extension_ids(profile)

    data, error = load_policy(policy_path)
    return FirefoxStatus(
        profiles=len(profiles),
        installed_ids=installed,
        policy_ids=policy_extension_ids(data) if data is not None else set(),
        firefox_found=firefox_installed(home),
        policy_error=error or "",
    )


# --------------------------------------------------------------------------- #
# Installation
# --------------------------------------------------------------------------- #
def find_helper() -> Optional[Path]:
    """Locate ``mtk-firefox`` in the installed tree or a source checkout."""
    for candidate in (
        INSTALLED_HELPER,
        paths.PKG_DIR.parent / "mtk-firefox",
        paths.PKG_DIR.parent / "data" / "mtk-firefox",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def apply_policy(
    runner: BaseRunner,
    selected_ids: Sequence[str],
    policy_path: Optional[Path] = None,
    helper: Optional[Path] = None,
    timeout: float = 120.0,
) -> ApplyOutcome:
    """Write the selected extensions into Firefox's enterprise policy.

    The helper receives only the desired mapping.  It merges it into the live
    policy itself, which avoids sending the whole system policy through a
    user-writable temporary file.
    """
    requested = list(dict.fromkeys(selected_ids))
    unknown = [identifier for identifier in requested if identifier not in EXTENSION_BY_ID]
    if unknown:
        return ApplyOutcome(False, f"Unknown extension(s): {', '.join(unknown)}")
    selected = [EXTENSION_BY_ID[identifier] for identifier in requested]

    target = Path(policy_path) if policy_path is not None else POLICY_PATH
    helper_path = helper if helper is not None else find_helper()
    tempdir = tempfile.mkdtemp(prefix="mtk-firefox-")
    staged = Path(tempdir) / "extensions.json"
    try:
        if helper_path is not None:
            candidate = {extension.id: extension.policy for extension in selected}
            staged.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
            staged.chmod(0o600)
            command = Command((str(helper_path), "install-policy", str(staged)), needs_root=True)
            result = runner.run(command, timeout=timeout)
            if result.ok:
                return ApplyOutcome(True, "The Firefox extension policy was updated.", result)
            return ApplyOutcome(False, result.output or "The Firefox policy helper failed.", result)

        existing, error = load_policy(target)
        if error:
            return ApplyOutcome(False, error)
        try:
            data = plan_policy(existing or {}, requested)
        except PolicyError as exc:
            return ApplyOutcome(False, str(exc))

        staged.write_text(render_policy(data), encoding="utf-8")
        staged.chmod(0o600)
        runner.run(cmd("install", "-d", "-m", "0755", str(target.parent), root=True), timeout=60)
        result = runner.run(
            cmd(
                "install",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0644",
                str(staged),
                str(target),
                root=True,
            ),
            timeout=timeout,
        )
        if result.ok:
            return ApplyOutcome(True, "The Firefox extension policy was updated.", result)
        return ApplyOutcome(False, result.output or "Could not install the Firefox policy.", result)
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)
