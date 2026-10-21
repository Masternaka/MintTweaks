#!/usr/bin/python3
"""Compile a gettext ``.po`` file into a binary ``.mo`` catalogue.

Pure Python on purpose: ``msgfmt`` lives in the ``gettext`` package, which is not
always installed on a build machine, and pulling a build dependency for 80 lines
of binary format is a poor trade.

    ./tools/compile_mo.py po/fr.po minttweaks/locale/fr/LC_MESSAGES/minttweaks.mo
    ./tools/compile_mo.py --check po/fr.po    # every entry translated?
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from po import parse_po  # noqa: E402  (local helper module)

MAGIC = 0x950412DE


def build_mo(entries: Dict[str, str]) -> bytes:
    """Serialise a catalogue in the GNU MO binary format."""
    pairs = sorted((msgid.encode("utf-8"), msgstr.encode("utf-8")) for msgid, msgstr in entries.items())
    count = len(pairs)

    offset = 7 * 4 + count * 8 * 2  # header + both index tables
    ids_blob = b""
    ids_index: List[Tuple[int, int]] = []
    for msgid, _msgstr in pairs:
        ids_index.append((len(msgid), offset + len(ids_blob)))
        ids_blob += msgid + b"\x00"

    strings_blob = b""
    strings_index: List[Tuple[int, int]] = []
    base = offset + len(ids_blob)
    for _msgid, msgstr in pairs:
        strings_index.append((len(msgstr), base + len(strings_blob)))
        strings_blob += msgstr + b"\x00"

    header = struct.pack(
        "<7I",
        MAGIC,
        0,  # revision
        count,
        7 * 4,  # offset of the msgid table
        7 * 4 + count * 8,  # offset of the msgstr table
        0,  # hash table size
        0,  # hash table offset
    )
    table = b"".join(struct.pack("<2I", length, position) for length, position in ids_index)
    table += b"".join(struct.pack("<2I", length, position) for length, position in strings_index)
    return header + table + ids_blob + strings_blob


def compile_po(source: pathlib.Path, destination: pathlib.Path) -> int:
    entries, warnings, _order = parse_po(source.read_text(encoding="utf-8"))
    for warning in warnings:
        print(f"{source}: {warning}", file=sys.stderr)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build_mo(entries))
    return len(entries)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("po", type=pathlib.Path, help="source .po file")
    parser.add_argument("mo", type=pathlib.Path, nargs="?", help="destination .mo file")
    parser.add_argument("--check", action="store_true", help="only verify that nothing is untranslated")
    options = parser.parse_args(argv[1:])

    if not options.po.is_file():
        print(f"no such file: {options.po}", file=sys.stderr)
        return 1

    entries, warnings, _order = parse_po(options.po.read_text(encoding="utf-8"))
    for warning in warnings:
        print(f"{options.po}: {warning}", file=sys.stderr)
    empty = [msgid for msgid, msgstr in entries.items() if not msgstr]

    if options.check:
        if not entries:
            print(f"{options.po}: no translated entry found", file=sys.stderr)
            return 1
        if empty:
            print(f"{options.po}: {len(empty)} untranslated string(s):", file=sys.stderr)
            for msgid in empty[:10]:
                print(f"  {msgid!r}", file=sys.stderr)
            return 1
        print(f"{options.po}: {len(entries)} strings, all translated.")
        return 0

    if options.mo is None:
        print("a destination .mo file is required (or use --check)", file=sys.stderr)
        return 2
    if empty:
        print(f"{options.po}: {len(empty)} untranslated string(s), they fall back to English.", file=sys.stderr)

    count = compile_po(options.po, options.mo)
    print(f"wrote {options.mo} ({count} strings)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
