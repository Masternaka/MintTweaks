"""Shared PO-file helpers for the two tools in this directory.

Keeping the parser in one place means the compiler and the extractor cannot
disagree about what a catalogue contains, and the generated files are canonical:
one entry, one block.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Dict, List, Optional, Sequence, Tuple

HEADER_MSGID = ""


class PoParseError(ValueError):
    pass


def po_escape(text: str) -> str:
    """Encode a string for a PO file."""
    out = text.replace("\\", "\\\\").replace('"', '\\"')
    return out.replace("\n", "\\n").replace("\t", "\\t")


def po_unquote(quoted: str) -> str:
    """Decode one PO string literal (escapes are close enough to Python's)."""
    try:
        return ast.literal_eval(quoted.strip())
    except (SyntaxError, ValueError) as exc:
        raise PoParseError(f"cannot decode {quoted!r}: {exc}") from exc


def format_entry(msgid: str, msgstr: str, references: Sequence[str] = ()) -> str:
    """One canonical entry block (no trailing newline)."""
    lines: List[str] = []
    for reference in references:
        lines.append(f"#: {reference}")
    lines.append(f'msgid "{po_escape(msgid)}"')
    lines.append(f'msgstr "{po_escape(msgstr)}"')
    return "\n".join(lines)


def format_header(msgstr: str) -> str:
    """The header entry, with one continuation line per field."""
    lines = ['msgid ""', 'msgstr ""']
    for field in msgstr.splitlines():
        lines.append(f'"{po_escape(field)}\\n"')
    return "\n".join(lines)


def parse_po(text: str) -> Tuple[Dict[str, str], List[str], List[str]]:
    """Return ``({msgid: msgstr}, warnings, order)``.

    ``order`` keeps the file's sequence so a rewritten catalogue stays stable.
    """
    entries: Dict[str, str] = {}
    order: List[str] = []
    warnings: List[str] = []

    msgid = ""
    msgstr = ""
    current = ""
    fuzzy = False
    seen_msgid = False

    def flush() -> None:
        nonlocal msgid, msgstr, current, fuzzy, seen_msgid
        if seen_msgid and not fuzzy:
            if msgid not in entries:
                order.append(msgid)
            elif entries[msgid] != msgstr:
                warnings.append(f"duplicate msgid, the last one wins: {msgid!r}")
            entries[msgid] = msgstr
        msgid, msgstr, current, fuzzy, seen_msgid = "", "", "", False, False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            continue
        if line.startswith("msgid_plural") or line.startswith("msgstr["):
            warnings.append("plural forms are not supported; entry skipped")
            fuzzy = True
            continue
        if line.startswith("msgid "):
            if seen_msgid:
                flush()
            msgid = po_unquote(line[6:])
            current = "msgid"
            seen_msgid = True
        elif line.startswith("msgstr "):
            msgstr = po_unquote(line[7:])
            current = "msgstr"
        elif line.startswith('"'):
            if current == "msgid":
                msgid += po_unquote(line)
            elif current == "msgstr":
                msgstr += po_unquote(line)
        else:
            raise PoParseError(f"unexpected line: {raw!r}")
    flush()
    return entries, warnings, order


def read_po(path: pathlib.Path) -> Tuple[Dict[str, str], List[str], List[str]]:
    return parse_po(path.read_text(encoding="utf-8"))


def find_msgid(text: str) -> Optional[str]:
    for line in text.splitlines():
        if line.startswith('msgid "') and line != 'msgid ""':
            return po_unquote(line[6:])
    return None
