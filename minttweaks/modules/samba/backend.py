"""Everything MintTweaks does to Samba, minus the pixels.

Design notes:

* Only :class:`~minttweaks.core.runner.Command` objects are executed, never a
  shell string, and every user-supplied value (share name, path, username) is
  validated before it reaches a command or ``smb.conf``.
* A configuration is never written blind: it is validated with ``testparm``
  first, the previous file is copied to the user's backup folder, and the
  privileged write goes through a small root helper that repeats the
  ``testparm`` check.
* Passwords travel on stdin, never in an argv.
"""

from __future__ import annotations

import datetime
import os
import pwd
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ...core import paths
from ...core.runner import BaseRunner, Command, Result, cmd
from ...core.smbconf import SmbConf, default_conf, normalise_path, validate_share_name, validate_share_path
from ...i18n import _

#: Packages we consider "Samba is installed" and offer to add.
PACKAGES = ("samba", "smbclient", "cifs-utils")
#: Units we are willing to drive, and nothing else.
SERVICES = ("smbd", "nmbd", "winbind")

INSTALLED_HELPER = Path("/usr/lib/minttweaks/mtk-root")

USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_TRUE = {"yes", "true", "1", "on"}
_FALSE = {"no", "false", "0", "off"}


# --------------------------------------------------------------------------- #
# Small value objects
# --------------------------------------------------------------------------- #
def as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def bool_str(value: bool) -> str:
    return "yes" if value else "no"


@dataclass
class Validation:
    """Outcome of ``testparm`` on a candidate configuration."""

    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    output: str = ""

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return "Configuration is valid."
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(parts) or "Configuration is valid."


@dataclass
class SaveOutcome:
    ok: bool
    message: str
    backup_path: Optional[Path] = None
    validation: Optional[Validation] = None
    result: Optional[Result] = None


@dataclass
class SambaUser:
    name: str
    unix_uid: str = ""
    full_name: str = ""
    enabled: bool = True
    has_unix_account: bool = True


@dataclass
class ServiceState:
    name: str
    active: str = "unknown"
    enabled: str = "unknown"

    @property
    def running(self) -> bool:
        return self.active == "active"


@dataclass
class SambaStatus:
    installed: bool = False
    missing_packages: List[str] = field(default_factory=list)
    conf_exists: bool = False
    services: List[ServiceState] = field(default_factory=list)
    firewall_available: bool = False
    firewall_active: bool = False
    firewall_allows_samba: bool = False


# --------------------------------------------------------------------------- #
# Package state
# --------------------------------------------------------------------------- #
def package_installed(runner: BaseRunner, package: str) -> bool:
    result = runner.run(cmd("dpkg-query", "-W", "-f=${Status}", package))
    return result.ok and "install ok installed" in result.stdout


def missing_packages(runner: BaseRunner) -> List[str]:
    return [package for package in PACKAGES if not package_installed(runner, package)]


def samba_installed(runner: BaseRunner) -> bool:
    return package_installed(runner, "samba") or shutil.which("smbpasswd") is not None


def install_packages(runner: BaseRunner, on_line=None) -> Result:
    packages = missing_packages(runner) or list(PACKAGES)
    runner.run(cmd("apt-get", "update", "-qq", root=True), timeout=300)
    return runner.stream(
        cmd("apt-get", "install", "-y", "--no-install-recommends", *packages, root=True),
        on_line=on_line,
    )


# --------------------------------------------------------------------------- #
# Configuration document
# --------------------------------------------------------------------------- #
@dataclass
class Document:
    """A loaded ``smb.conf`` plus what we know about where it came from."""

    path: Path
    conf: SmbConf
    text: str
    existed: bool

    @property
    def duplicates(self) -> List[str]:
        return self.conf.duplicate_sections()


def conf_path(path: Optional[Path] = None) -> Path:
    return Path(path) if path is not None else paths.SMB_CONF


def load_document(runner: BaseRunner, path: Optional[Path] = None) -> Document:
    """Read ``smb.conf``, falling back to a sane template when absent."""
    target = conf_path(path)
    text: Optional[str] = None
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return Document(target, default_conf(), "", existed=False)
    except PermissionError:
        result = runner.run(cmd("cat", str(target), root=True))
        if not result.ok:
            return Document(target, default_conf(), "", existed=False)
        text = result.stdout
    except OSError:
        return Document(target, default_conf(), "", existed=False)

    return Document(target, SmbConf.parse(text), text, existed=True)


def render(doc: Document) -> str:
    return doc.conf.render()


def validate_text(runner: BaseRunner, text: str) -> Validation:
    """Run ``testparm`` on a candidate configuration held in a temp file."""
    tempdir = tempfile.mkdtemp(prefix="mtk-smb-")
    candidate = Path(tempdir) / "smb.conf"
    try:
        candidate.write_text(text, encoding="utf-8")
        candidate.chmod(0o600)
        # testparm needs the file to be reachable; it reads as the current user.
        result = runner.run(cmd("testparm", "-s", str(candidate)), timeout=60)
        return _parse_testparm(result)
    except OSError as exc:
        return Validation(False, errors=[f"Could not stage the configuration for validation: {exc}"])
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def _parse_testparm(result: Result) -> Validation:
    output = result.output
    if result.returncode == 127:
        # testparm missing: we cannot vouch for the file, so be explicit.
        return Validation(False, errors=["'testparm' is not installed (package samba-common-bin)."], output=output)

    errors: List[str] = []
    warnings: List[str] = []
    for raw in (result.stdout + "\n" + result.stderr).splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("error") or lowered.startswith("badly formed"):
            errors.append(line)
        elif "unknown parameter" in lowered or "ignoring unknown parameter" in lowered:
            errors.append(line)
        elif lowered.startswith("warning") or "invalid value" in lowered:
            warnings.append(line)

    ok = result.ok and not errors
    return Validation(ok, errors=errors, warnings=warnings, output=output)


def helper_path() -> Optional[Path]:
    """Locate the privileged helper.

    Tried in order: the system location, the sibling of the installed package
    (non-standard PREFIX), then the source checkout.  A missing helper is not
    fatal: the caller falls back to ``install(1)``.
    """
    for candidate in (
        INSTALLED_HELPER,
        paths.PKG_DIR.parent / "mtk-root",
        paths.PKG_DIR.parent / "data" / "mtk-root",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _backup_dir(backup_dir: Optional[Path]) -> Path:
    target = Path(backup_dir) if backup_dir is not None else paths.BACKUP_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def backup_conf(text: str, backup_dir: Optional[Path] = None) -> Optional[Path]:
    """Keep a timestamped copy of the current configuration in the user's data dir."""
    if not text.strip():
        return None
    directory = _backup_dir(backup_dir)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = directory / f"smb.conf.{stamp}"
    counter = 1
    while destination.exists():
        destination = directory / f"smb.conf.{stamp}.{counter}"
        counter += 1
    destination.write_text(text, encoding="utf-8")
    destination.chmod(0o600)
    return destination


def list_backups(backup_dir: Optional[Path] = None) -> List[Path]:
    directory = Path(backup_dir) if backup_dir is not None else paths.BACKUP_DIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("smb.conf.*"), key=lambda p: p.name, reverse=True)


def save_document(
    runner: BaseRunner,
    doc: Document,
    text: Optional[str] = None,
    backup_dir: Optional[Path] = None,
    reload_service: bool = True,
) -> SaveOutcome:
    """Validate, back up, then install a configuration as root.

    With the installed helper, installing and reloading smbd happen inside a
    single privileged call, so the user is asked for their password once.
    """
    candidate = doc.text if text is None else text
    validation = validate_text(runner, candidate)
    if not validation.ok:
        return SaveOutcome(
            False,
            "The configuration was rejected by testparm; nothing was written.",
            validation=validation,
        )

    backup_path: Optional[Path] = None
    try:
        backup_path = backup_conf(doc.text, backup_dir)
    except OSError as exc:
        return SaveOutcome(False, f"Could not write a backup copy: {exc}", validation=validation)

    tempdir = tempfile.mkdtemp(prefix="mtk-smb-")
    staged = Path(tempdir) / "smb.conf"
    try:
        staged.write_text(candidate, encoding="utf-8")
        staged.chmod(0o600)
        helper = helper_path()
        if helper is not None:
            argv = [str(helper), "install-smbconf", str(staged)]
            if reload_service:
                argv.append("--reload")
            command = Command(tuple(argv), needs_root=True)
        else:
            # Fallback used in a source checkout: install(1) is a plain, argv-only
            # way of putting a file in place with the right owner and mode.
            command = cmd(
                "install", "-o", "root", "-g", "root", "-m", "0644", str(staged), str(doc.path), root=True
            )
        result = runner.run(command, timeout=180)
        if result.ok and reload_service and helper is None:
            # No helper to do it for us: a second authorization is needed.
            runner.run(cmd("systemctl", "reload", "smbd", root=True), timeout=60)
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)

    if result.ok:
        return SaveOutcome(
            True,
            f"Configuration installed ({doc.path}); previous file saved to {backup_path}.",
            backup_path=backup_path,
            validation=validation,
            result=result,
        )
    return SaveOutcome(
        False,
        "Could not install the configuration. " + (result.output or "Administrator authorisation was refused."),
        backup_path=backup_path,
        validation=validation,
        result=result,
    )


def restore_backup(runner: BaseRunner, backup: Path, path: Optional[Path] = None) -> SaveOutcome:
    try:
        text = Path(backup).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return SaveOutcome(False, f"Could not read {backup}: {exc}")
    target = conf_path(path)
    doc = Document(target, SmbConf.parse(text), text, existed=target.exists())
    return save_document(runner, doc, text=text)


# --------------------------------------------------------------------------- #
# Shares
# --------------------------------------------------------------------------- #
@dataclass
class Share:
    """The share parameters we expose in the UI."""

    name: str
    path: str
    comment: str = ""
    browseable: bool = True
    read_only: bool = True
    guest_ok: bool = False
    valid_users: str = ""
    write_list: str = ""
    create_mask: str = ""
    directory_mask: str = ""
    force_group: str = ""

    # -- conversion ------------------------------------------------------
    @classmethod
    def from_conf(cls, conf: SmbConf, name: str) -> "Share":
        def getter(key: str, default: str = "") -> str:
            return conf.get(name, key, default) or ""

        return cls(
            name=name,
            path=getter("path"),
            comment=getter("comment"),
            browseable=as_bool(conf.get(name, "browseable"), True),
            read_only=as_bool(conf.get(name, "read only"), True),
            guest_ok=as_bool(conf.get(name, "guest ok", conf.get(name, "public")), False),
            valid_users=getter("valid users"),
            write_list=getter("write list"),
            create_mask=getter("create mask"),
            directory_mask=getter("directory mask"),
            force_group=getter("force group"),
        )

    def directives(self) -> List[Tuple[str, str]]:
        """The (key, value) pairs this share owns in the file."""
        pairs = [
            ("comment", self.comment.strip()),
            ("path", normalise_path(self.path)),
            ("browseable", bool_str(self.browseable)),
            ("read only", bool_str(self.read_only)),
            ("guest ok", bool_str(self.guest_ok)),
            ("valid users", self.valid_users.strip()),
            ("write list", self.write_list.strip()),
            ("create mask", self.create_mask.strip()),
            ("directory mask", self.directory_mask.strip()),
            ("force group", self.force_group.strip()),
        ]
        return [(key, value) for key, value in pairs if value != ""]

    def validate(self, conf: Optional[SmbConf] = None, renaming_from: Optional[str] = None) -> List[str]:
        """Every reason this share cannot be written, in plain language."""
        problems: List[str] = []
        target_conf = conf
        if conf is not None and renaming_from and renaming_from.lower() != self.name.strip().lower():
            # Renaming: the old section name is not a conflict.
            target_conf = conf.copy()
            if target_conf.has_section(self.name):
                target_conf.remove_section(self.name)
        name_error = validate_share_name(self.name, target_conf)
        if name_error:
            problems.append(name_error)
        path_error = validate_share_path(self.path)
        if path_error:
            problems.append(path_error)
        for label, mask in ((
            _("Create mask"), self.create_mask), (_("Directory mask"), self.directory_mask)):
            if mask and not re.match(r"^[0-7]{3,4}$", mask.strip()):
                problems.append(_("{label} must be an octal mode such as 0664 or 2775.").format(label=label))
        return problems


def list_shares(conf: SmbConf) -> List[Share]:
    shares: List[Share] = []
    for name in conf.shares():
        shares.append(Share.from_conf(conf, name))
    return shares


def apply_share(conf: SmbConf, share: Share, previous: Optional[Share] = None) -> None:
    """Write a share into the document, leaving unrelated keys alone."""
    managed = {key for key, _ in share.directives()} | {
        "comment",
        "path",
        "browseable",
        "read only",
        "guest ok",
        "public",
        "valid users",
        "write list",
        "create mask",
        "directory mask",
        "force group",
    }
    if previous is not None and previous.name.strip().lower() != share.name.strip().lower():
        conf.rename_section(previous.name, share.name.strip())
    elif not conf.has_section(share.name):
        conf.add_section(share.name.strip())

    for key, value in share.directives():
        conf.set(share.name, key, value)

    # Parameters we own but that ended up empty must disappear, otherwise a
    # cleared "valid users" would silently keep the old restriction.
    for key in managed:
        if not any(key == written for written, _ in share.directives()):
            conf.unset(share.name, key)


def create_share(conf: SmbConf, share: Share) -> List[str]:
    problems = share.validate(conf)
    if problems:
        return problems
    apply_share(conf, share)
    return []


def update_share(conf: SmbConf, share: Share, previous: Share) -> List[str]:
    problems = share.validate(conf, renaming_from=previous.name)
    if problems:
        return problems
    apply_share(conf, share, previous=previous)
    return []


def delete_share(conf: SmbConf, name: str) -> bool:
    return conf.remove_section(name)


def is_windows_safe_share_name(name: str) -> bool:
    """Windows is the usual client; flag characters it dislikes."""
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9._$ -]{0,11}$", name or ""))


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
def unix_user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
    except KeyError:
        return False
    return True


def list_users(runner: BaseRunner) -> List[SambaUser]:
    """Samba accounts from the passdb, annotated with the Unix account state."""
    result = runner.run(cmd("pdbedit", "-L", "-v", root=True), timeout=30)
    users: List[SambaUser] = []
    if result.ok and result.stdout.strip():
        for block in re.split(r"\n\s*\n", result.stdout):
            name_match = re.search(r"^Unix username:\s*(\S+)", block, re.MULTILINE)
            if not name_match:
                continue
            flags_match = re.search(r"^Account Flags:\s*\[([^\]]*)\]", block, re.MULTILINE)
            full_match = re.search(r"^Full Name:\s*(.*)$", block, re.MULTILINE)
            flags = flags_match.group(1).strip() if flags_match else "U"
            users.append(
                SambaUser(
                    name=name_match.group(1).strip(),
                    full_name=(full_match.group(1).strip() if full_match else ""),
                    enabled="D" not in flags,
                )
            )
    elif result.ok:
        return []
    else:
        # Older or trimmed builds: "name:uid:fullname" one per line.
        listing = runner.run(cmd("pdbedit", "-L", root=True), timeout=30)
        if listing.ok:
            for line in listing.stdout.splitlines():
                parts = line.split(":")
                if parts and parts[0].strip():
                    users.append(
                        SambaUser(
                            name=parts[0].strip(),
                            unix_uid=parts[1].strip() if len(parts) > 1 else "",
                            full_name=parts[2].strip() if len(parts) > 2 else "",
                        )
                    )

    for user in users:
        user.has_unix_account = unix_user_exists(user.name)
    return sorted(users, key=lambda u: u.name.lower())


def validate_username(username: str) -> Optional[str]:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        return _("Use a lowercase Unix user name (letters, digits, '_', '-').")
    if not unix_user_exists(username):
        return _("No Unix account named '{user}'. Create the system account first.").format(user=username)
    return None


def password_problem(password: str) -> Optional[str]:
    """Cheap sanity check. Samba itself accepts almost anything."""
    if not password:
        return _("The password cannot be empty.")
    if len(password) < 8:
        return _("Use at least 8 characters.")
    if password.strip() != password:
        return _("The password must not start or end with a space.")
    return None


def add_user(runner: BaseRunner, username: str, password: str) -> Result:
    """Create (or update) a Samba account; the password goes through stdin."""
    problem = validate_username(username)
    if problem:
        return Result(f"smbpasswd -a {username}", 2, stderr=problem)
    if not package_installed(runner, "samba"):
        return Result(
            f"smbpasswd -a {username}",
            2,
            stderr=_("Samba is not installed. Install it first."),
        )
    return runner.run(
        cmd("smbpasswd", "-a", "-s", username, root=True),
        input_text=f"{password}\n{password}\n",
        timeout=60,
    )


def set_user_enabled(runner: BaseRunner, username: str, enabled: bool) -> Result:
    problem = validate_username(username)
    if problem:
        return Result(f"smbpasswd {username}", 2, stderr=problem)
    flag = "-e" if enabled else "-d"
    return runner.run(cmd("smbpasswd", flag, username, root=True), timeout=30)


def delete_user(runner: BaseRunner, username: str) -> Result:
    problem = validate_username(username)
    if problem:
        return Result(f"smbpasswd -x {username}", 2, stderr=problem)
    return runner.run(cmd("smbpasswd", "-x", username, root=True), timeout=30)


# --------------------------------------------------------------------------- #
# Services & status
# --------------------------------------------------------------------------- #
def _first_line(text: str, default: str = "unknown") -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return default


def service_state(runner: BaseRunner, unit: str) -> ServiceState:
    active = runner.run(cmd("systemctl", "is-active", unit), timeout=10)
    enabled = runner.run(cmd("systemctl", "is-enabled", unit), timeout=10)
    return ServiceState(
        name=unit,
        # ``is-active`` exits non-zero when the unit is inactive, and still
        # prints the state, so read stdout rather than trusting the status.
        active=_first_line(active.stdout, "inactive"),
        enabled=_first_line(enabled.stdout, "disabled"),
    )


def control_service(runner: BaseRunner, unit: str, action: str, on_line=None) -> Result:
    if unit not in SERVICES:
        return Result(f"systemctl {action} {unit}", 2, stderr=f"Refusing to drive unit '{unit}'.")
    if action not in ("start", "stop", "restart", "reload", "enable", "disable"):
        return Result(f"systemctl {action} {unit}", 2, stderr=f"Unsupported action '{action}'.")
    return runner.stream(cmd("systemctl", action, unit, root=True), on_line=on_line, timeout=120)


def unit_exists(runner: BaseRunner, unit: str) -> bool:
    listing = runner.run(cmd("systemctl", "list-unit-files", "--no-legend", f"{unit}.service"), timeout=15)
    return bool(listing.ok and listing.stdout.strip())


def enable_and_start_sharing(runner: BaseRunner, on_line=None) -> List[Result]:
    """Enable smbd (and nmbd when it exists) and start them."""
    results: List[Result] = []
    for unit in ("smbd", "nmbd"):
        if not unit_exists(runner, unit):
            continue
        results.append(control_service(runner, unit, "enable", on_line=on_line))
        results.append(control_service(runner, unit, "restart", on_line=on_line))
    return results


def firewall_state(runner: BaseRunner) -> Tuple[bool, bool, bool]:
    """``(available, active, allows_samba)`` for ufw."""
    if shutil.which("ufw") is None:
        return False, False, False
    result = runner.run(cmd("ufw", "status", root=True), timeout=20)
    output = result.stdout or result.stderr
    active = "status: active" in output.lower()
    allows = bool(re.search(r"^Samba\b.*ALLOW", output, re.IGNORECASE | re.MULTILINE))
    return True, active, allows


def allow_samba_in_firewall(runner: BaseRunner) -> Result:
    return runner.run(cmd("ufw", "allow", "Samba", root=True), timeout=30)


def smbstatus_text(runner: BaseRunner) -> Result:
    return runner.run(cmd("smbstatus", "-b", "-L", "--numeric"), timeout=30)


def collect_status(runner: BaseRunner, path: Optional[Path] = None) -> SambaStatus:
    status = SambaStatus()
    status.installed = samba_installed(runner)
    status.missing_packages = missing_packages(runner) if status.installed else list(PACKAGES)
    status.conf_exists = conf_path(path).exists()
    if status.installed:
        for unit in SERVICES[:2]:
            status.services.append(service_state(runner, unit))
    available, active, allows = firewall_state(runner)
    status.firewall_available = available
    status.firewall_active = active
    status.firewall_allows_samba = allows
    return status


def restart_after_change(runner: BaseRunner, on_line=None) -> List[Result]:
    return [control_service(runner, "smbd", "reload", on_line=on_line)]
