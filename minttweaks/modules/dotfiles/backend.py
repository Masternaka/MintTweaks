"""Dotfiles operations. Never run repository scripts or adopt existing files."""

from dataclasses import dataclass
from pathlib import Path
import os
import re
import stat

from ...core.runner import cmd, read_command
from ...i18n import _
from ..software.backend import apt_command


def directory(value):
    if not str(value).strip():
        raise ValueError(_("Choose a directory first."))
    path = Path(value).expanduser().absolute()
    if path.is_symlink() or not path.is_dir():
        raise ValueError(_("Choose an existing directory, not a symbolic link."))
    return path.resolve()


def repository_url(url):
    if not isinstance(url, str) or len(url) > 512:
        raise ValueError(_("Use a GitHub HTTPS or SSH repository URL without a token."))
    url = url.strip()
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", url)
    if not match:
        raise ValueError(_("Use a GitHub HTTPS or SSH repository URL without a token."))
    name = match[2][:-4] if match[2].endswith('.git') else match[2]
    if match[1] in {'.', '..'} or name in {'', '.', '..'}:
        raise ValueError(_("Use a GitHub HTTPS or SSH repository URL without a token."))
    return url


def clone_command(url, destination):
    url = repository_url(url)
    path = Path(destination).expanduser().absolute()
    if not str(destination).strip() or os.path.lexists(path):
        raise ValueError(_("The clone destination must be a new directory."))
    parent = directory(path.parent)
    path = parent / path.name
    return cmd("git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never",
               "-c", "protocol.ext.allow=never", "clone", "--no-recurse-submodules", "--", url, str(path))


def clone(runner, url, destination, on_line=None):
    command = clone_command(url, destination)
    if runner.dry_run:
        return _("Simulation: no repository was cloned.")
    result = runner.stream(command, on_line=on_line)
    if not result.ok:
        raise ValueError(result.output)
    return _("Repository cloned. You can now analyse its configurations.")


@dataclass(frozen=True)
class Package:
    name: str
    files: int = 0
    linked: int = 0
    error: str = ""
    conflicts: tuple = ()
    managed: bool = False


def _tree(package):
    """Snapshot without following source symlinks or reading file contents."""
    entries = []
    def failed(exc):
        raise exc
    for parent, dirs, files in os.walk(package, followlinks=False, onerror=failed):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError(_("Source symbolic links and special files are not supported: {path}").format(path=path))
            entries.append((str(path.relative_to(package)), info.st_mode, info.st_size, info.st_mtime_ns, info.st_ino))
            if len(entries) > 20000:
                raise ValueError(_("This configuration contains too many files."))
    return tuple(sorted(entries))


def _package(root, name):
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", name):
        raise ValueError(_("Invalid Stow package name."))
    package = root / name
    if package.is_symlink() or not package.is_dir():
        raise ValueError(_("The selected configuration is no longer available."))
    return package


def _targets(root, target, name, tree, dotfiles):
    package = root / name
    linked = 0
    conflicts = []
    for relative, mode, *_rest in tree:
        parts = Path(relative).parts
        if dotfiles:
            parts = tuple("." + part[4:] if part.startswith("dot-") else part for part in parts)
        if any(part in {".", ".."} for part in parts):
            raise ValueError(_("Invalid dot- filename in this configuration."))
        path = target.joinpath(*parts)
        if path == root or path.is_relative_to(root):
            raise ValueError(_("A configuration cannot create links inside its own repository."))
        # Check every existing parent before resolving a leaf.
        for parent in path.parents:
            if parent == target:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                conflicts.append(str(parent))
                break
        else:
            raise ValueError(_("The target escapes the selected directory."))
        if stat.S_ISDIR(mode):
            if os.path.lexists(path) and (path.is_symlink() or not path.is_dir()):
                conflicts.append(str(path))
        elif path.is_symlink() and path.resolve() == (package / relative).resolve():
            linked += 1
        elif os.path.lexists(path):
            conflicts.append(str(path))
    return linked, tuple(sorted(set(conflicts)))


def analyse(repository, target, dotfiles=False):
    from . import deployments
    root, target = directory(repository), directory(target)
    if root == target or target.is_relative_to(root):
        raise ValueError(_("The target must be outside the dotfiles directory."))
    packages = []
    managed_packages = deployments.managed_packages(root, target, dotfiles)
    for path in sorted(root.iterdir()):
        if path.name.startswith(".") or not path.is_dir() or path.name in {"docs", "scripts", "tests", "tools", "node_modules"}:
            continue
        try:
            tree = _tree(_package(root, path.name))
            count = sum(stat.S_ISREG(item[1]) for item in tree)
            linked, conflicts = _targets(root, target, path.name, tree, dotfiles)
            # Ordinary leaf conflicts can be backed up. Unsafe directories are
            # still rejected by the activation planner.
            deployments._mapping(root, target, path.name, tree, dotfiles)
            managed = path.name in managed_packages
            if count:
                packages.append(Package(path.name, count, linked, "", conflicts, managed))
        except (ValueError, OSError) as exc:
            packages.append(Package(path.name, error=str(exc), managed=path.name in managed_packages))
    found = {package.name for package in packages}
    for name, records in managed_packages.items():
        if name not in found:
            linked = sum(deployments._matches_link(target / record['relative'], Path(record['source'])) for record in records)
            packages.append(Package(name, linked=linked, managed=True))
    return tuple(packages)


def _check_resource_files():
    # Stow reads these implicitly; an --adopt/--delete there could change the
    # meaning of our explicit operation. Do not silently execute such options.
    for path in {Path.home() / ".stowrc", Path.cwd() / ".stowrc"}:
        if os.path.lexists(path):
            raise ValueError(_("Stow reads {path} automatically. Move this options file aside before using MintTweaks.").format(path=path))


def stow_command(root, target, name, dotfiles=False, simulate=True):
    return cmd("stow", "--dir=" + str(root), "--target=" + str(target), "--stow", "--no-folding",
               *(("--dotfiles",) if dotfiles else ()), *(("--simulate",) if simulate else ()),
               "--verbose=2", "--", name)


@dataclass(frozen=True)
class StowPlan:
    root: Path
    target: Path
    name: str
    dotfiles: bool
    tree: tuple
    output: str


def preview_stow(runner, repository, target, name, dotfiles=False):
    root, target = directory(repository), directory(target)
    if root == target or target.is_relative_to(root):
        raise ValueError(_("The target must be outside the dotfiles directory."))
    _check_resource_files()
    tree = _tree(_package(root, name))
    if not any(stat.S_ISREG(item[1]) for item in tree):
        raise ValueError(_("This configuration is empty."))
    _linked, conflicts = _targets(root, target, name, tree, dotfiles)
    if conflicts:
        raise ValueError(_("Existing files or unsafe directories: {paths}").format(paths="\n".join(conflicts)))
    result = read_command(runner, stow_command(root, target, name, dotfiles))
    return StowPlan(root, target, name, dotfiles, tree, result.output)


def apply_stow(runner, plan, on_line=None):
    if runner.dry_run:
        return _("Simulation: no dotfiles links were created.")
    checked = preview_stow(runner, plan.root, plan.target, plan.name, plan.dotfiles)
    if checked.tree != plan.tree or checked.output != plan.output:
        raise ValueError(_("The Stow plan changed. Review a new preview before continuing."))
    result = runner.stream(stow_command(plan.root, plan.target, plan.name, plan.dotfiles, simulate=False), on_line=on_line)
    if not result.ok:
        raise ValueError(result.output)
    return _("Stow finished. Existing files were not adopted or overwritten.")


@dataclass(frozen=True)
class DependencyPlan:
    packages: tuple
    operations: tuple
    output: str


def preview_dependencies(runner, packages=("git", "stow")):
    if not packages or any(package not in {"git", "stow"} for package in packages):
        raise ValueError("Invalid dotfiles dependency selection")
    result = read_command(runner, apt_command(packages, simulate=True))
    operations = tuple(sorted(line.strip() for line in result.stdout.splitlines() if line.startswith(("Inst ", "Conf ", "Remv ", "Purg "))))
    if any(line.startswith(("Remv ", "Purg ")) for line in operations):
        raise ValueError(_("APT proposed removals. Installation was refused."))
    return DependencyPlan(tuple(packages), operations, result.output)


def install_dependencies(runner, plan, on_line=None):
    if runner.dry_run:
        return _("Simulation: no dotfiles tools were installed.")
    checked = preview_dependencies(runner, plan.packages)
    if checked.operations != plan.operations:
        raise ValueError(_("The installation plan changed. Review a new preview before continuing."))
    result = runner.stream(apt_command(plan.packages), on_line=on_line)
    if not result.ok:
        raise ValueError(result.output)
    for binary in plan.packages:
        read_command(runner, cmd(binary, "--version"))
    return _("Git and Stow are available.")
