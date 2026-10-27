"""Command execution.

Backends never import :mod:`subprocess` directly.  They build :class:`Command`
objects and hand them to a :class:`Runner`.  That single indirection is what
makes all the system-facing logic unit-testable off-target (see ``tests/``), and
it keeps the "build an argv list, never a shell string" rule in one place.
"""

from __future__ import annotations

import codecs
import io
import logging
import os
import selectors
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Union

from .privilege import EscalationUnavailable, Escalator

log = logging.getLogger(__name__)

#: Exit codes we synthesise ourselves, mirroring shell conventions.
RC_NOT_FOUND = 127
RC_NOT_ALLOWED = 126
RC_TIMEOUT = 124
DEFAULT_STREAM_TIMEOUT = 1800.0


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

    dry_run = False

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
        timeout: Optional[float] = DEFAULT_STREAM_TIMEOUT,
    ) -> Result:  # pragma: no cover - interface
        raise NotImplementedError


class ReadError(RuntimeError):
    """A diagnostic failed; its output must not be presented as a complete result."""


def read_command(runner: BaseRunner, command: Command, timeout: float = 120) -> Result:
    if runner.dry_run:
        raise ReadError("Diagnostic commands are unavailable in simulation mode.")
    result = runner.run(command, timeout=timeout)
    if not result.ok:
        raise ReadError(result.output or f"{result.command} failed (rc={result.returncode}).")
    return result


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
        if self.dry_run:
            log.info("[dry-run] %s", command)
            return Result(str(command), 0, stdout=f"[dry-run] {command}")

        try:
            argv = self._build(command)
        except EscalationUnavailable as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))

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
        timeout: Optional[float] = DEFAULT_STREAM_TIMEOUT,
    ) -> Result:
        command = self._argv(command)
        if self.dry_run:
            log.info("[dry-run] %s", command)
            if on_line:
                on_line(f"[dry-run] {command}")
            return Result(str(command), 0, stdout=f"[dry-run] {command}")

        try:
            argv = self._build(command)
        except EscalationUnavailable as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))

        log.info("stream: %s", command)
        lines: List[str] = []
        try:
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                env=_child_env(),
                start_new_session=True,
            )
        except FileNotFoundError:
            return Result(str(command), RC_NOT_FOUND, stderr=f"Program not found: {argv[0]}")
        except (PermissionError, OSError) as exc:
            return Result(str(command), RC_NOT_ALLOWED, stderr=str(exc))

        # Read bytes rather than readline(): a silent child, a partial line,
        # and a child which closes stdout before exiting all need a deadline.
        decoder = io.IncrementalNewlineDecoder(
            codecs.getincrementaldecoder("utf-8")(errors="replace"), translate=True
        )
        deadline = time.monotonic() + timeout if timeout is not None else None
        pending = ""
        timed_out = False
        stopped = False
        diagnostic = ""
        callback_error: Optional[BaseException] = None

        def notify(line):
            nonlocal callback_error, on_line
            if on_line is None:
                return None
            try:
                return on_line(line)
            except BaseException as exc:
                if not command.needs_root:
                    raise
                # Keep draining a privileged child's pipe if the UI callback
                # fails. Otherwise it could block on output while we wait.
                callback_error = exc
                on_line = None
                return None

        def emit(text):
            nonlocal pending, stopped
            pending += text
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                lines.append(line)
                if notify(line) is False:
                    stopped = True
                    break

        def stop_group():
            # The process owns its session: descendants inheriting the output
            # pipe must also stop, without touching the desktop process group.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        try:
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                pipe_open = True
                while pipe_open or process.poll() is None:
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        timed_out = True
                        diagnostic = f"Timed out after {timeout:g}s."
                        deadline = None
                        if command.needs_root:
                            diagnostic += " The administrative command is still monitored until it exits; it was not forcibly interrupted."
                            notify(diagnostic)
                        else:
                            stop_group()
                            break
                    if stopped:
                        if command.needs_root:
                            # A callback is not an authorization to interrupt APT.
                            on_line = None
                            stopped = False
                        else:
                            stop_group()
                            break
                    delay = 0.1 if deadline is None else max(0, min(0.1, deadline - time.monotonic()))
                    if not pipe_open:
                        time.sleep(delay)
                        continue
                    for key, _mask in selector.select(delay):
                        data = os.read(key.fd, 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            pipe_open = False
                            emit(decoder.decode(b"", final=True))
                        else:
                            emit(decoder.decode(data))
                if pending and not stopped:
                    lines.append(pending)
                    notify(pending)
        except BaseException:
            if not command.needs_root:
                stop_group()
            raise
        finally:
            process.stdout.close()
            # Administrative processes remain supervised even if the output
            # callback fails; the application must not release its action slot.
            process.wait()

        if callback_error is not None:
            raise callback_error
        returncode = RC_TIMEOUT if timed_out else process.returncode
        return Result(str(command), returncode, stdout="\n".join(lines), stderr=diagnostic)

def describe(result: Result) -> str:
    """One-line status used in logs and tooltips."""
    status = "ok" if result.ok else f"failed (rc={result.returncode})"
    return f"{result.command} -> {status}"
