"""Maintenance and cleanup tasks.

Two rules shape this module:

1. **Nothing destructive happens without a preview.**  ``apt-get -s`` is free,
   so the UI can show exactly which packages would go before a single byte is
   removed.
2. **User-scoped cleanup never runs as root.**  Thumbnails and trash belong to
   the logged-in user; escalating them would leave root-owned files in $HOME.

Kernels are handled separately from the generic task list because the set of
packages depends on the machine: see :func:`installed_kernels`.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ...core.runner import BaseRunner, Command, ReadError, Result, cmd, read_command
from ...i18n import _

THUMBNAILS = Path(".cache/thumbnails")
TRASH = Path(".local/share/Trash")
APT_ARCHIVES = Path("/var/cache/apt/archives")
JOURNAL_DIR = Path("/var/log/journal")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def human_bytes(size: Optional[float]) -> str:
    if size is None:
        return _("unknown")
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def directory_size(path: Path) -> Optional[int]:
    """Bytes, 0 when absent, or None when the measurement is incomplete.

    Symlinks are measured but never followed: a symlink planted in a cache
    folder must not make us walk (or delete) something else entirely.
    """
    total = 0
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return 0
    except OSError:
        return None
    if stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        return metadata.st_size

    def unreadable(exc):
        raise exc

    try:
        for root, dirs, files in os.walk(path, followlinks=False, onerror=unreadable):
            for name in files:
                try:
                    total += os.lstat(os.path.join(root, name)).st_size
                except FileNotFoundError:
                    continue
    except OSError:
        return None
    return total


def _du_bytes(runner: BaseRunner, path: Path) -> Optional[int]:
    """Ask GNU ``du`` for a size; None when it cannot tell us."""
    result = runner.run(cmd("du", "-sb", str(path)))
    if not result.ok:
        return None
    digits = result.stdout.split("\t")[0].split()[0] if result.stdout.strip() else ""
    return int(digits) if digits.isdigit() else None


def _clear_tree(path: Path) -> Tuple[int, int]:
    """Delete the *contents* of a directory. Returns (files, bytes freed).

    Directories are only walked when they are real directories: a symlink inside
    the cache is unlinked, never descended into.
    """
    files = 0
    freed = 0
    if not path.is_dir() or path.is_symlink():
        return files, freed

    for root, dirs, names in os.walk(path, topdown=False, followlinks=False):
        for name in names:
            target = Path(root) / name
            try:
                size = target.lstat().st_size
                target.unlink()
                files += 1
                freed += size
            except OSError:
                continue
        for name in dirs:
            target = Path(root) / name
            try:
                if target.is_symlink():
                    target.unlink()
                    files += 1
                else:
                    target.rmdir()
            except OSError:
                continue
    return files, freed


# --------------------------------------------------------------------------- #
# User-scoped actions (never root)
# --------------------------------------------------------------------------- #
def clear_thumbnails(home: Optional[Path] = None) -> Result:
    base = (Path(home) if home is not None else Path.home()) / THUMBNAILS
    files, freed = _clear_tree(base)
    if not base.exists():
        return Result("clear thumbnails", 0, stdout="No thumbnail cache to clear.")
    return Result("clear thumbnails", 0, stdout=f"Removed {files} thumbnail file(s), freeing {human_bytes(freed)}.")


def empty_trash(home: Optional[Path] = None) -> Result:
    base = (Path(home) if home is not None else Path.home()) / TRASH
    files, freed = _clear_tree(base)
    if not base.exists():
        return Result("empty trash", 0, stdout="The trash is already empty.")
    return Result("empty trash", 0, stdout=f"Deleted {files} item(s) from the trash, freeing {human_bytes(freed)}.")


# --------------------------------------------------------------------------- #
# Task model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Step:
    description: str
    command: Optional[Command] = None
    action: Optional[Callable[[], Result]] = None
    required: bool = True

    def run(self, runner: BaseRunner, on_line=None) -> Result:
        if self.action is not None:
            if runner.dry_run:
                output = f"[dry-run] {self.description}"
                if on_line is not None:
                    on_line(output)
                return Result(self.description, 0, stdout=output)
            return self.action()
        assert self.command is not None
        if on_line is not None:
            return runner.stream(self.command, on_line=on_line)
        return runner.run(self.command)


@dataclass(frozen=True)
class Task:
    """A cleanup task.

    ``title`` and ``detail`` are stored as English msgids and translated on
    access: the registry below is built at import time, which is before the
    translation catalogue is loaded.
    """

    id: str
    title_msgid: str
    detail_msgid: str
    steps: Tuple[Step, ...]
    danger: int = 0  # 0 = safe, 1 = removes things, 2 = destroys data
    only_when_present: bool = True

    @property
    def title(self) -> str:
        return _(self.title_msgid)

    @property
    def detail(self) -> str:
        return _(self.detail_msgid)

    @property
    def needs_root(self) -> bool:
        return any(step.command is not None and step.command.needs_root for step in self.steps)


def _apt(*args: str) -> Command:
    return cmd("apt-get", *args, root=True)


TASKS: Tuple[Task, ...] = (
    Task(
        id="apt_autoremove",
        title_msgid=_("Remove orphaned packages"),
        detail_msgid=(
            _("Deletes packages that were installed automatically and are no longer needed "
            "by anything. The list is shown before you confirm.")
        ),
        steps=(
            Step(
                "Purge orphaned packages",
                command=_apt("autoremove", "--purge", "-y"),
            ),
        ),
        danger=1,
    ),
    Task(
        id="apt_clean",
        title_msgid=_("Delete downloaded package files"),
        detail_msgid=_("Empties /var/cache/apt/archives. Re-downloading is the only consequence."),
        steps=(Step("apt-get clean", command=_apt("clean")),),
        danger=0,
    ),
    Task(
        id="apt_autoclean",
        title_msgid=_("Delete obsolete package files"),
        detail_msgid=_("Removes cached .deb files that can no longer be downloaded."),
        steps=(Step("apt-get autoclean", command=_apt("autoclean")),),
        danger=0,
    ),
    Task(
        id="apt_fix",
        title_msgid=_("Fix broken dependencies"),
        detail_msgid=_("Runs 'apt-get -f install', the usual cure for a half-configured system."),
        steps=(Step("apt-get -f install", command=_apt("-f", "install", "-y")),),
        danger=1,
    ),
    Task(
        id="journal_vacuum_size",
        title_msgid=_("Shrink the system journal to 200 MB"),
        detail_msgid=_("Keeps the most recent entries and drops the rest. Log history is lost."),
        steps=(Step("journalctl --vacuum-size=200M", command=cmd("journalctl", "--vacuum-size=200M", root=True)),),
        danger=0,
    ),
    Task(
        id="journal_vacuum_time",
        title_msgid=_("Drop journal entries older than two weeks"),
        detail_msgid=_("Time-based vacuum, usually the better choice on a laptop."),
        steps=(Step("journalctl --vacuum-time=2weeks", command=cmd("journalctl", "--vacuum-time=2weeks", root=True)),),
        danger=0,
    ),
    Task(
        id="thumbnails",
        title_msgid=_("Clear the thumbnail cache"),
        detail_msgid=_(
            "The file manager rebuilds it as you browse. Safe, and it frees a surprising amount of space."
        ),
        steps=(Step("clear thumbnails", action=clear_thumbnails),),
        danger=0,
    ),
    Task(
        id="trash",
        title_msgid=_("Empty the trash"),
        detail_msgid=_("Permanently deletes everything currently in your user trash."),
        steps=(Step("empty trash", action=empty_trash),),
        danger=2,
    ),
    Task(
        id="flatpak_unused",
        title_msgid=_("Remove unused Flatpak runtimes"),
        detail_msgid=_("Only available when Flatpak is installed. Frees runtimes no app references any more."),
        steps=(
            Step(
                "flatpak uninstall --unused",
                command=cmd("flatpak", "uninstall", "--unused", "-y"),
            ),
        ),
        danger=1,
    ),
)

TASK_BY_ID: Dict[str, Task] = {task.id: task for task in TASKS}


def available_tasks(runner: BaseRunner) -> List[Task]:
    """Hide tasks that make no sense on this machine (e.g. no Flatpak)."""
    tasks: List[Task] = []
    for task in TASKS:
        if task.id == "flatpak_unused" and shutil.which("flatpak") is None:
            continue
        tasks.append(task)
    return tasks


# --------------------------------------------------------------------------- #
# Preview / probing
# --------------------------------------------------------------------------- #
@dataclass
class Probe:
    apt_archives_bytes: Optional[int] = None
    journal_bytes: Optional[int] = None
    thumbnails_bytes: Optional[int] = 0
    trash_bytes: Optional[int] = 0
    autoremove_packages: List[str] = field(default_factory=list)
    autoremove_error: str = ""
    kernel_error: str = ""

    @property
    def autoremove_count(self) -> int:
        return len(self.autoremove_packages)


def parse_autoremove_preview(text: str) -> List[str]:
    """Read the package list out of ``apt-get -s autoremove`` output.

    apt prints the names twice: in the "will be REMOVED" summary and again as
    ``Remv <name> [<version>]`` lines.  Depending on the version and on whether
    the list is truncated, only one of them may be present, so both are read.
    """
    packages: List[str] = []

    def remember(name: str) -> None:
        name = name.strip().rstrip("*")
        if name and not name.startswith("-") and name not in packages:
            packages.append(name)

    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        lowered = line.lower()
        if not line:
            in_block = False
            continue
        if lowered.startswith("the following packages will be removed"):
            in_block = True
            continue
        if lowered.startswith(("remv ", "purg ")):
            in_block = False
            parts = line.split()
            if len(parts) >= 2:
                remember(parts[1])
            continue
        if lowered.startswith(("the following", "0 upgraded", "need to get", "after this operation")):
            in_block = False
            continue
        if in_block:
            for token in line.split():
                remember(token)
    return packages


class PreviewError(RuntimeError):
    """APT could not provide a successful removal simulation."""


def autoremove_preview(runner: BaseRunner) -> List[str]:
    try:
        result = read_command(runner, cmd("apt-get", "-s", "autoremove", "--purge"), timeout=120)
    except ReadError as exc:
        raise PreviewError(str(exc)) from exc
    return parse_autoremove_preview(result.stdout)


def collect_probe(runner: BaseRunner, home: Optional[Path] = None) -> Probe:
    base = Path(home) if home is not None else Path.home()
    try:
        packages, preview_error = autoremove_preview(runner), ""
    except PreviewError as exc:
        packages, preview_error = [], str(exc)
    return Probe(
        apt_archives_bytes=_du_bytes(runner, APT_ARCHIVES),
        journal_bytes=_du_bytes(runner, JOURNAL_DIR),
        thumbnails_bytes=directory_size(base / THUMBNAILS),
        trash_bytes=directory_size(base / TRASH),
        autoremove_packages=packages,
        autoremove_error=preview_error,
    )


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
@dataclass
class StepOutcome:
    description: str
    result: Result


@dataclass
class TaskOutcome:
    task_id: str
    title: str
    steps: List[StepOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(step.result.ok for step in self.steps)

    def summary(self) -> str:
        if not self.steps:
            return "Nothing to do."
        failed = [step for step in self.steps if not step.result.ok]
        if not failed:
            return f"{self.title}: done."
        first = failed[0].result.output or "unknown error"
        return f"{self.title}: {len(failed)} step(s) failed — {first.splitlines()[0] if first else ''}"


def run_task(
    runner: BaseRunner,
    task: Task,
    on_line: Optional[Callable[[str], None]] = None,
    approved_packages: Optional[Sequence[str]] = None,
) -> TaskOutcome:
    outcome = TaskOutcome(task.id, task.title)
    if task.id == "apt_autoremove" and not runner.dry_run:
        error = ""
        if not approved_packages:
            error = "A complete removal preview must be confirmed before removing orphaned packages."
        else:
            try:
                current = autoremove_preview(runner)
                if set(current) != set(approved_packages):
                    error = "The removal plan changed. Review and confirm a new preview before trying again."
            except PreviewError as exc:
                error = f"Removal preview failed; no packages were removed: {exc}"
        if error:
            outcome.steps.append(StepOutcome("Check removal preview", Result("autoremove preview", 2, stderr=error)))
            return outcome
    for step in task.steps:
        result = step.run(runner, on_line=on_line)
        outcome.steps.append(StepOutcome(step.description, result))
        if not result.ok and step.required:
            break
    return outcome


# --------------------------------------------------------------------------- #
# Kernels
# --------------------------------------------------------------------------- #
KERNEL_PACKAGE_PREFIXES = ("linux-image-",)


@dataclass(frozen=True)
class Kernel:
    """A kernel version, with every installed package that belongs to it."""

    version: str  # "6.8.0-45-generic"
    packages: Tuple[str, ...]
    running: bool = False

    @property
    def label(self) -> str:
        return f"{self.version}{' (running)' if self.running else ''}"


def parse_dpkg_listing(text: str) -> List[str]:
    """Installed package names from ``dpkg-query -W`` output."""
    names: List[str] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        status = parts[2] if len(parts) > 2 else ""
        if status and "install ok installed" not in status:
            continue
        names.append(parts[0].strip())
    return names


def installed_packages(runner: BaseRunner, pattern: str = "linux-*") -> List[str]:
    result = read_command(runner,
        cmd("dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n", pattern),
        timeout=60,
    )
    if not result.stdout.strip():
        return []
    return parse_dpkg_listing(result.stdout)


def running_kernel(runner: BaseRunner) -> str:
    result = read_command(runner, cmd("uname", "-r"), timeout=10)
    version = result.stdout.strip()
    if not version:
        raise ReadError("The running kernel could not be identified.")
    return version


def collect_maintenance(runner: BaseRunner):
    """A failed kernel query must not hide successful space and APT checks."""
    probe = collect_probe(runner)
    try:
        kernels = installed_kernels(runner)
    except Exception as exc:
        kernels = []
        probe.kernel_error = str(exc)
    return probe, kernels


def installed_kernels(runner: BaseRunner) -> List[Kernel]:
    """Group installed linux-* packages into per-release kernels."""
    packages = installed_packages(runner, "linux-*")
    current = running_kernel(runner)

    images = [name for name in packages if name.startswith(KERNEL_PACKAGE_PREFIXES)]
    kernels: List[Kernel] = []
    for image in images:
        version = image[len("linux-image-") :]
        if version.startswith("unsigned-"):
            version = version[len("unsigned-") :]
        # Companions of a kernel all end with the same release+flavour string:
        # linux-headers-6.8.0-45-generic, linux-modules-6.8.0-45-generic, ...
        # The flavour-less linux-headers-6.8.0-45 is deliberately *not* matched:
        # it is shared with other flavours of the same release, so removing it
        # could break a kernel we are keeping.  apt's autoremove mops it up.
        companions = sorted(
            name
            for name in packages
            if name.startswith("linux-") and (name == image or name.endswith(version))
        )
        kernels.append(Kernel(version=version, packages=tuple(companions), running=version == current))
    return _sort_kernels(_dedupe(kernels))


def _dedupe(kernels: Sequence[Kernel]) -> List[Kernel]:
    by_version: Dict[str, Kernel] = {}
    for kernel in kernels:
        existing = by_version.get(kernel.version)
        if existing is None:
            by_version[kernel.version] = kernel
        else:
            merged = tuple(sorted(set(existing.packages) | set(kernel.packages)))
            by_version[kernel.version] = Kernel(kernel.version, merged, kernel.running)
    return list(by_version.values())


def _version_key(version: str) -> Tuple:
    """Sortable key: numbers compare numerically, flavours alphabetically."""
    parts = re.split(r"[.-]", version)
    key: List = []
    for part in parts:
        key.append((0, int(part), "") if part.isdigit() else (1, 0, part))
    return tuple(key)


def _sort_kernels(kernels: Sequence[Kernel]) -> List[Kernel]:
    return sorted(kernels, key=lambda kernel: _version_key(kernel.version))


def removable_kernels(kernels: Sequence[Kernel], keep: int = 1) -> List[Kernel]:
    """Kernels it is safe to purge: never the running one, never the newest ``keep``."""
    ordered = _sort_kernels(kernels)
    if len(ordered) <= keep:
        return []
    newest = ordered[-keep:] if keep > 0 else []
    keep_versions = {kernel.version for kernel in newest}
    return [
        kernel
        for kernel in ordered
        if not kernel.running and kernel.version not in keep_versions
    ]


def purge_kernels(runner: BaseRunner, kernels: Sequence[Kernel], on_line=None) -> Result:
    packages: List[str] = []
    for kernel in kernels:
        if kernel.running:
            return Result("purge kernels", 2, stderr=f"Refusing to purge the running kernel ({kernel.version}).")
        packages.extend(kernel.packages)
    if not packages:
        return Result("purge kernels", 0, stdout="Nothing selected.")
    return runner.stream(
        cmd("apt-get", "purge", "-y", *sorted(set(packages)), root=True),
        on_line=on_line,
    )
