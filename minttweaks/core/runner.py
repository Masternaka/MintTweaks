"""Command execution.

Backends never import :mod:`subprocess` directly.  They build :class:`Command`
objects and hand them to a :class:`Runner`.  That single indirection is what
makes all the system-facing logic unit-testable off-target (see ``tests/``), and
it keeps the "build an argv list, never a shell string" rule in one place.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Union

from .privilege import EscalationUnavailable, Escalator

log = logging.getLogger(__name__)

#: Exit codes we synthesise ourselves, mirroring shell conventions.
RC_NOT_FOUND = 127
RC_NOT_ALLOWED = 126
RC_TIMEOUT = 124


@dataclass(frozen=True)
class Command:
    """A single process invocation, expressed as an argv list."""

    argv: tuple
    needs_root: bool = False

    def __post_init__(self) -> None:
        if not self.argv:
            raise ValueError("Command requires at least a program name")
        for part in self.argv:
            if not isinstance(part, str):
                raise TypeError(f"Command arguments must be str, got {type(part).__name__}: {part!r}")
            if "\x00" in part:
                raise ValueError("Command arguments must not contain NUL bytes")
        object.__setattr__(self, "argv", tuple(str(p) for p in self.argv))

    def __str__(self) -> str:
        rendered = " ".join(shlex.quote(a) for a in self.argv)
        return f"sudo {rendered}" if self.needs_root else rendered


def cmd(*argv: str, root: bool = False) -> Command:
    """Shorthand for building a :class:`Command`."""
    return Command(tuple(argv), needs_root=root)


ArgvLike = Union[Command, Sequence[str]]


def coerce(value: ArgvLike, needs_root: bool = False) -> Command:
    """Accept either a Command or a bare argv sequence."""
    if isinstance(value, Command):
        return value
    if isinstance(value, (str, bytes)):
        raise TypeError("Expected an argv sequence, not a string; refusing to guess about shell quoting")
    return Command(tuple(value), needs_root=needs_root)


@dataclass
class Result:
    """Outcome of one command."""

    command: str
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Combined output, stderr last; handy for showing to the user."""
        parts = [self.stdout.strip(), self.stderr.strip()]
        return "\n".join(p for p in parts if p)

    def failed_with_missing_program(self) -> bool:
        return self.returncode == RC_NOT_FOUND


def _child_env() -> dict:
    """Environment for child processes: stable, parseable, non-interactive."""
    env = dict(os.environ)
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "LANGUAGE": "C",
            "DEBIAN_FRONTEND": "noninteractive",
            "APT_LISTCHANGES_FRONTEND": "none",
            "SYSTEMD_PAGER": "",
            "PAGER": "cat",
        }
    )
    env.pop("GIT_PAGER", None)
    return env


class BaseRunner:
    """Interface every backend depends on."""

    def run(
        self,
        command: ArgvLike,
        timeout: float = 120.0,
        input_text: Optional[str] = None,
    ) -> Result:  # pragma: no cover - interface
        raise NotImplementedError

    def stream(
        self,
        command: ArgvLike,
        on_line: Optional[Callable[[str], Optional[bool]]] = None,
        timeout: Optional[float] = None,
    ) -> Result:  # pragma: no cover - interface
        raise NotImplementedError


class SubprocessRunner(BaseRunner):
    """Runs commands for real, escalating through polkit when asked."""

    def __init__(self, escalator: Optional[Escalator] = None, dry_run: bool = False) -> None:
        self.escalator = escalator or Escalator()
        self.dry_run = dry_run or os.environ.get("MTK_DRY_RUN", "").lower() in ("1", "true", "yes")

    # -- internals ---------------------------------------------------------
    def _argv(self, command: ArgvLike) -> Command:
        return coerce(command)

    def _build(self, command: Command) -> List[str]:
        return self.escalator.wrap(command.argv, command.needs_root)

    # -- public API --------------------------------------------------------
    def run(
        self,
        command: ArgvLike,
        timeout: float = 120.0,
        input_text: Optional[str] = None,
    ) -> Result:
        """Run a command to completion.

        ``input_text`` is piped to stdin.  It exists so that passwords can be
        handed to ``smbpasswd -s`` without ever appearing in an argv (and
        therefore in ``ps`` output or in our logs).
        """
        command = self._argv(command)
        try:
            argv = self._build(command)
        except EscalationUnavailable as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))

        if self.dry_run:
            log.info("[dry-run] %s", command)
            return Result(str(command), 0, stdout=f"[dry-run] {command}")

        log.debug("run: %s", command)
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                env=_child_env(),
                input=input_text,
                check=False,
            )
        except FileNotFoundError:
            return Result(str(command), RC_NOT_FOUND, stderr=f"Program not found: {argv[0]}")
        except PermissionError as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))
        except subprocess.TimeoutExpired:
            return Result(str(command), RC_TIMEOUT, stderr=f"Timed out after {timeout:g}s")
        except OSError as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))

        result = Result(
            command=str(command),
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
        if not result.ok:
            log.info("rc=%s %s\n%s", result.returncode, command, result.output[:2000])
        return result

    def stream(
        self,
        command: ArgvLike,
        on_line: Optional[Callable[[str], Optional[bool]]] = None,
        timeout: Optional[float] = None,
    ) -> Result:
        command = self._argv(command)
        try:
            argv = self._build(command)
        except EscalationUnavailable as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))

        if self.dry_run:
            log.info("[dry-run] %s", command)
            if on_line:
                on_line(f"[dry-run] {command}")
            return Result(str(command), 0, stdout=f"[dry-run] {command}")

        log.info("stream: %s", command)
        lines: List[str] = []
        try:
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
                env=_child_env(),
            )
        except FileNotFoundError:
            return Result(str(command), RC_NOT_FOUND, stderr=f"Program not found: {argv[0]}")
        except (PermissionError, OSError) as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))

        stopped_early = False
        returncode = -1
        try:
            assert process.stdout is not None
            for raw in process.stdout:
                line = raw.rstrip("\n")
                lines.append(line)
                if on_line is not None and on_line(line) is False:
                    stopped_early = True
                    break
        finally:
            try:
                if process.stdout is not None:
                    process.stdout.close()
            except OSError:
                pass
            if stopped_early:
                try:
                    process.terminate()
                except OSError:
                    pass
            try:
                # Only guards the final wait; the reading loop above is as long
                # as the child keeps producing output.
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                returncode = RC_TIMEOUT

        return Result(str(command), returncode, stdout="\n".join(lines))


def describe(result: Result) -> str:
    """One-line status used in logs and tooltips."""
    status = "ok" if result.ok else f"failed (rc={result.returncode})"
    return f"{result.command} -> {status}"
