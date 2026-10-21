"""Test doubles.

``FakeRunner`` is why the backends are worth testing off-target: they only ever
talk to the system through :class:`~minttweaks.core.runner.BaseRunner`, so a
handful of canned replies is enough to exercise real logic on any OS.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

from minttweaks.core.runner import BaseRunner, Command, Result, coerce


class FakeRunner(BaseRunner):
    """Replies to commands by matching their argv prefix (longest match wins)."""

    def __init__(self) -> None:
        self.rules: List[Tuple[Tuple[str, ...], Result]] = []
        self.calls: List[Command] = []
        self.inputs: List[Optional[str]] = []

    # -- configuration -----------------------------------------------------
    def add(
        self,
        argv_prefix: Sequence[str],
        stdout: str = "",
        returncode: int = 0,
        stderr: str = "",
    ) -> "FakeRunner":
        self.rules.append(
            (tuple(argv_prefix), Result(" ".join(argv_prefix), returncode, stdout, stderr))
        )
        return self

    def add_callable(self, argv_prefix: Sequence[str], handler: Callable[[Command], Result]) -> "FakeRunner":
        self.rules.append((tuple(argv_prefix), handler))  # type: ignore[arg-type]
        return self

    # -- introspection -----------------------------------------------------
    def commands(self) -> List[Tuple[str, ...]]:
        return [tuple(call.argv) for call in self.calls]

    def ran(self, argv_prefix: Sequence[str]) -> bool:
        prefix = tuple(argv_prefix)
        return any(command[: len(prefix)] == prefix for command in self.commands())

    def last_input(self) -> Optional[str]:
        return self.inputs[-1] if self.inputs else None

    # -- BaseRunner --------------------------------------------------------
    def _reply(self, command: Command) -> Result:
        best: Optional[Tuple[Tuple[str, ...], object]] = None
        for prefix, reply in self.rules:
            if command.argv[: len(prefix)] == prefix and (best is None or len(prefix) > len(best[0])):
                best = (prefix, reply)
        if best is None:
            return Result(str(command), 127, stderr=f"no fake rule for: {command}")
        reply = best[1]
        if callable(reply):
            return reply(command)
        return Result(str(command), reply.returncode, reply.stdout, reply.stderr)

    def run(self, command, timeout: float = 120.0, input_text: Optional[str] = None) -> Result:
        coerced = coerce(command)
        self.calls.append(coerced)
        self.inputs.append(input_text)
        return self._reply(coerced)

    def stream(self, command, on_line=None, timeout=None) -> Result:
        coerced = coerce(command)
        self.calls.append(coerced)
        self.inputs.append(None)
        result = self._reply(coerced)
        if on_line is not None:
            for line in (result.stdout or "").splitlines():
                on_line(line)
        return result


def sample_smb_conf() -> str:
    return """\
#======================= Global Settings =======================
[global]
## Browsing/Identification ###
   workgroup = WORKGROUP
   server string = %h server (Samba, Linux Mint)
   netbios name = mintbox
   map to guest = bad user

#### Debugging ####
   log file = /var/log/samba/log.%m
   max log size = 1000

#======================= Share Definitions =======================
[Documents]
   comment = Mes documents
   path = /srv/documents
   browseable = yes
   read only = no
   guest ok = no
   valid users = alice bob
   create mask = 0664
   directory mask = 0775
"""


def pdbedit_listv(names: Sequence[str] = ("alice", "bob")) -> str:
    blocks = []
    for index, name in enumerate(names):
        flags = "[U          ]" if index == 0 else "[DU         ]"
        blocks.append(
            f"Unix username:        {name}\n"
            f"NT username:          \n"
            f"Account Flags:        {flags}\n"
            f"User SID:             S-1-5-21-1-2-3-{1000 + index}\n"
            f"Full Name:            {name.title()} Example\n"
            f"Home Directory:       \\\\mintbox\\{name}\n"
        )
    return "\n".join(blocks) + "\n"


LIST_UNITS = """\
  accounts-daemon.service              loaded active running Accounts Service
  ssh.service                          loaded active running OpenBSD Secure Shell server
  smbd.service                         loaded active running Samba SMB Daemon
  cups.service                         loaded inactive dead  CUPS Scheduler
● weird-fail.service                   loaded failed failed  A unit that broke
  sshd.service                         loaded inactive dead  Alias for ssh.service
"""

LIST_UNIT_FILES = """\
accounts-daemon.service               enabled         enabled
cups.service                          enabled         enabled
smbd.service                          enabled         enabled
nmbd.service                          disabled        enabled
ssh.service                           enabled         enabled
weird-fail.service                    disabled        enabled
"""


DEFAULTS = dict(smb_conf=sample_smb_conf())
