"""A round-trip safe model of Samba's ``smb.conf``.

Why not :mod:`configparser`?  Because a real ``smb.conf`` is full of comments,
blank lines and `include` tricks that users care about, and ``configparser``
rewrites the file into something unrecognisable.  Here every physical line
becomes a node that remembers its original text, so:

    SmbConf.parse(text).render() == text

holds for any input.  Only the lines MintTweaks actually edits are regenerated.

Samba rules implemented here:

* ``#`` or ``;`` at the start of a line is a comment (not inline),
* ``[name]`` opens a section, ``global`` being the special one,
* ``key = value`` is a parameter, keys being case-insensitive,
* a line ending in ``\\`` continues on the next physical line.
"""

from __future__ import annotations

import copy as _copy
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union
from ..i18n import _

#: Sections that are not user shares.
RESERVED_SECTIONS = frozenset({"global", "homes", "printers", "print$"})

_SECTION_RE = re.compile(r"^\[(?P<name>.+)\]$")
_COMMENT_PREFIXES = ("#", ";")

#: Share names we accept.  Deliberately narrower than Samba: a name MintTweaks
#: writes is always safe to put in ``smb.conf`` and in a shell-free argv.
SHARE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._$ -]{0,79}$")


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
@dataclass
class Blank:
    raw: Optional[str] = None

    def render(self) -> str:
        return ""


@dataclass
class Comment:
    text: str
    raw: Optional[str] = None

    def render(self) -> str:
        return self.raw if self.raw is not None else self.text


@dataclass
class Raw:
    """A line we could not classify; preserved verbatim, never regenerated."""

    text: str
    raw: Optional[str] = None

    def render(self) -> str:
        return self.raw if self.raw is not None else self.text


@dataclass
class SectionHeader:
    name: str
    raw: Optional[str] = None

    def render(self) -> str:
        return self.raw if self.raw is not None else f"[{self.name}]"


@dataclass
class Entry:
    key: str
    value: str
    raw: Optional[str] = None
    indent: str = ""

    def render(self) -> str:
        return self.raw if self.raw is not None else f"{self.indent}{self.key} = {self.value}"


Node = Union[Blank, Comment, Raw, SectionHeader, Entry]


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _logical_lines(text: str) -> List[str]:
    """Split into physical lines, folding backslash continuations."""
    physical = text.split("\n")
    if physical and physical[-1] == "":
        physical.pop()
    physical = [line.rstrip("\r") for line in physical]

    logical: List[str] = []
    index = 0
    while index < len(physical):
        line = physical[index]
        stripped = line.lstrip()
        is_comment = stripped.startswith(_COMMENT_PREFIXES)
        chunk = [line]
        if not is_comment:
            while chunk[-1].rstrip().endswith("\\") and index + 1 < len(physical):
                index += 1
                chunk.append(physical[index])
        logical.append("\n".join(chunk))
        index += 1
    return logical


def _split_pair(line: str) -> Optional[Tuple[str, str]]:
    if "=" not in line:
        return None
    joined = line.replace("\\\n", " ")
    key, _, value = joined.partition("=")
    key = key.strip()
    if not key:
        return None
    return key, value.strip()


def parse_node(line: str) -> Node:
    """Classify one logical line into a node, keeping the original text."""
    if line.strip() == "":
        return Blank(raw=line)
    stripped = line.strip()
    if stripped.startswith(_COMMENT_PREFIXES):
        return Comment(text=line, raw=line)
    match = _SECTION_RE.match(stripped)
    if match:
        return SectionHeader(name=match.group("name").strip(), raw=line)
    pair = _split_pair(line)
    if pair is not None:
        first = line.split("\n", 1)[0]
        indent = first[: len(first) - len(first.lstrip())]
        return Entry(key=pair[0], value=pair[1], raw=line, indent=indent)
    return Raw(text=line, raw=line)


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #
class SmbConf:
    """An editable ``smb.conf`` document."""

    def __init__(self, nodes: Optional[Sequence[Node]] = None, trailing_newline: bool = True) -> None:
        self.nodes: List[Node] = list(nodes or [])
        self.trailing_newline = trailing_newline

    # -- construction ------------------------------------------------------
    @classmethod
    def parse(cls, text: str) -> "SmbConf":
        trailing = text.endswith("\n") or text == ""
        nodes = [parse_node(line) for line in _logical_lines(text)]
        return cls(nodes, trailing_newline=trailing)

    def copy(self) -> "SmbConf":
        return SmbConf(_copy.deepcopy(self.nodes), trailing_newline=self.trailing_newline)

    # -- serialisation -----------------------------------------------------
    def render(self) -> str:
        body = "\n".join(node.render() for node in self.nodes)  # type: ignore[attr-defined]
        if self.trailing_newline and body:
            return body + "\n"
        return body

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return self.render()

    # -- section inspection ------------------------------------------------
    def section_names(self) -> List[str]:
        """Unique section names, in file order, original case."""
        seen: Dict[str, str] = {}
        for node in self.nodes:
            if isinstance(node, SectionHeader):
                seen.setdefault(node.name.lower(), node.name)
        return list(seen.values())

    def has_section(self, name: str) -> bool:
        return self._find(name) is not None

    def shares(self) -> List[str]:
        """Sections that a human would call a share (not global/homes/printers)."""
        return [name for name in self.section_names() if name.lower() not in RESERVED_SECTIONS]

    def _find(self, name: str) -> Optional[int]:
        for index, node in enumerate(self.nodes):
            if isinstance(node, SectionHeader) and node.name.lower() == name.strip().lower():
                return index
        return None

    def _spans(self, name: str) -> List[Tuple[int, int]]:
        """Every ``(header_index, end_index)`` pair for a section name.

        Samba happily accepts a section defined twice and merges the two, so the
        model has to look at all of them instead of pretending only the first
        one exists.
        """
        wanted = name.strip().lower()
        spans: List[Tuple[int, int]] = []
        for index, node in enumerate(self.nodes):
            if not isinstance(node, SectionHeader) or node.name.lower() != wanted:
                continue
            end = len(self.nodes)
            for cursor in range(index + 1, len(self.nodes)):
                if isinstance(self.nodes[cursor], SectionHeader):
                    end = cursor
                    break
            spans.append((index, end))
        return spans

    def _span(self, name: str) -> Optional[Tuple[int, int]]:
        spans = self._spans(name)
        return spans[-1] if spans else None

    def _entries(self, name: str) -> List[Entry]:
        entries: List[Entry] = []
        for start, end in self._spans(name):
            entries.extend(node for node in self.nodes[start + 1 : end] if isinstance(node, Entry))
        return entries

    def duplicate_sections(self) -> List[str]:
        """Section names defined more than once (Samba merges them, users don't expect it)."""
        counts: Dict[str, int] = {}
        display: Dict[str, str] = {}
        for node in self.nodes:
            if isinstance(node, SectionHeader):
                key = node.name.lower()
                counts[key] = counts.get(key, 0) + 1
                display.setdefault(key, node.name)
        return [display[key] for key, count in counts.items() if count > 1]

    # -- parameter access --------------------------------------------------
    def get(self, section: str, key: str, default: Optional[str] = None) -> Optional[str]:
        wanted = key.strip().lower()
        found = default
        for entry in self._entries(section):
            if entry.key.strip().lower() == wanted:
                found = entry.value  # Samba: the last occurrence wins
        return found

    def items(self, section: str) -> List[Tuple[str, str]]:
        """Parameters of a section, last-wins, in file order."""
        merged: Dict[str, Tuple[str, str]] = {}
        for entry in self._entries(section):
            merged[entry.key.strip().lower()] = (entry.key, entry.value)
        return list(merged.values())

    def global_get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.get("global", key, default)

    # -- mutation ----------------------------------------------------------
    def set(self, section: str, key: str, value: str, create_section: bool = True) -> None:
        """Set a parameter, in place when it exists, else appended."""
        section = section.strip()
        key = key.strip()
        value = "" if value is None else str(value)
        if not section or not key:
            raise ValueError("section and key are required")
        if any(ch in key for ch in "\n\r="):
            raise ValueError(f"invalid parameter name: {key!r}")

        if not self.has_section(section):
            if not create_section:
                raise KeyError(f"section not found: {section}")
            self.add_section(section)

        wanted = key.lower()
        span = self._span(section)
        assert span is not None
        start, end = span
        indent = self._indent_for(section)

        last_entry = start
        replaced = False
        for index in range(start + 1, end):
            node = self.nodes[index]
            if isinstance(node, Entry):
                last_entry = index
                if node.key.strip().lower() == wanted:
                    self.nodes[index] = Entry(
                        key=node.key.strip(), value=value, indent=node.indent or indent
                    )
                    replaced = True
        if not replaced:
            self.nodes.insert(last_entry + 1, Entry(key=key, value=value, indent=indent))

    def _indent_for(self, section: str) -> str:
        """The indentation most entries of a section already use."""
        counts: Dict[str, int] = {}
        for entry in self._entries(section):
            if entry.indent:
                counts[entry.indent] = counts.get(entry.indent, 0) + 1
        if not counts:
            return "   "
        return max(counts.items(), key=lambda item: item[1])[0]

    def unset(self, section: str, key: str) -> bool:
        """Remove every occurrence of a parameter. Returns True if anything went."""
        spans = self._spans(section)
        if not spans:
            return False
        wanted = key.strip().lower()
        drop = set()
        for start, end in spans:
            for index in range(start + 1, end):
                node = self.nodes[index]
                if isinstance(node, Entry) and node.key.strip().lower() == wanted:
                    drop.add(index)
        if not drop:
            return False
        self.nodes = [node for index, node in enumerate(self.nodes) if index not in drop]
        return True

    def add_section(self, name: str) -> int:
        """Append a section, returning its header index."""
        existing = self._find(name)
        if existing is not None:
            return existing
        clean = name.strip()
        if not clean or "[" in clean or "]" in clean or clean == ".":
            raise ValueError(f"invalid section name: {name!r}")
        if self.nodes and not isinstance(self.nodes[-1], Blank):
            self.nodes.append(Blank())
        self.nodes.append(SectionHeader(name=clean))
        return len(self.nodes) - 1

    def remove_section(self, name: str) -> bool:
        spans = self._spans(name)
        if not spans:
            return False
        for start, end in reversed(spans):
            del self.nodes[start:end]
        # Tidy up the hole we just made.
        if 0 < start < len(self.nodes) and isinstance(self.nodes[start - 1], Blank) and isinstance(
            self.nodes[start], Blank
        ):
            del self.nodes[start]
        return True

    def rename_section(self, old: str, new: str) -> None:
        indices = [start for start, _end in self._spans(old)]
        if not indices:
            raise KeyError(f"section not found: {old}")
        new = new.strip()
        if not new or "]" in new or "[" in new:
            raise ValueError(f"invalid section name: {new!r}")
        if new.lower() != old.strip().lower() and self.has_section(new):
            raise ValueError(f"section already exists: {new}")
        for index in indices:
            self.nodes[index] = SectionHeader(name=new)

# --------------------------------------------------------------------------- #
# Validation helpers shared by the backend and the UI
# --------------------------------------------------------------------------- #
def validate_share_name(name: str, conf: Optional[SmbConf] = None) -> Optional[str]:
    """Return an error message, or None when the name is acceptable."""
    name = (name or "").strip()
    if not name:
        return _("The share name cannot be empty.")
    if name.lower() in RESERVED_SECTIONS:
        return _("'{name}' is a reserved Samba section name.").format(name=name)
    if not SHARE_NAME_RE.match(name):
        return _(
            "Use 1-80 characters from letters, digits, spaces, '.', '_', '-' or a trailing '$'. "
            "The name must start with a letter or a digit."
        )
    if name != name.rstrip():
        return _("The share name must not end with a space.")
    if conf is not None and conf.has_section(name):
        return _("A section named '{name}' already exists.").format(name=name)
    return None


def validate_share_path(path: str, must_exist: bool = True) -> Optional[str]:
    """Return an error message, or None when the path is safe to export."""
    path = (path or "").strip()
    if not path:
        return _("The folder path cannot be empty.")
    if any(ord(ch) < 32 for ch in path):
        return _("The folder path must not contain control characters.")
    if not path.startswith("/"):
        return _("The folder path must be absolute (start with '/').")
    normalised = os.path.normpath(path)
    if normalised in ("/", "//"):
        return _("Refusing to export the filesystem root.")
    first = normalised.lstrip("/").split("/", 1)[0]
    if first in ("proc", "sys", "dev", "run"):
        return _("Refusing to export a system path ({path}).").format(path=normalised)
    if must_exist and not os.path.isdir(normalised):
        return _("The folder does not exist: {path}").format(path=normalised)
    return None


def normalise_path(path: str) -> str:
    return os.path.normpath((path or "").strip())


# --------------------------------------------------------------------------- #
# Default document
# --------------------------------------------------------------------------- #
DEFAULT_CONF = """\
#======================= Global Settings =======================
[global]
   workgroup = WORKGROUP
   server string = %h server (Samba, Linux Mint)
   dns proxy = no
   log file = /var/log/samba/log.%m
   max log size = 1000
   syslog = 0
   panic action = /usr/share/samba/panic-action %d
   server role = standalone server
   passdb backend = tdbsam
   obey pam restrictions = yes
   unix password sync = yes
   passwd program = /usr/bin/passwd %u
   passwd chat = *Enter\\snew\\s*\\spassword:* %n\\n *Retype\\snew\\s*\\spassword:* %n\\n .
   pam password change = yes
   map to guest = bad user
   usershare allow guests = no

#======================= Share Definitions =======================
"""


def default_conf() -> SmbConf:
    return SmbConf.parse(DEFAULT_CONF)


def merge_duplicate_keys(conf: SmbConf) -> List[str]:
    """Drop repeated parameters inside a section (Samba only keeps the last).

    Returns the ``section/key`` identifiers that were removed.
    """
    removed: List[str] = []
    for section in conf.section_names():
        seen: Dict[str, int] = {}
        drop: List[int] = []
        for start, end in conf._spans(section):
            for index in range(start + 1, end):
                node = conf.nodes[index]
                if isinstance(node, Entry):
                    key = node.key.strip().lower()
                    if key in seen:
                        drop.append(seen[key])
                    seen[key] = index
        for index in reversed(drop):
            removed.append(f"{section}/{conf.nodes[index].key.strip()}")  # type: ignore[union-attr]
            del conf.nodes[index]
    return removed

