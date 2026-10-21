#!/usr/bin/python3
"""Extract translatable strings from the source into a gettext template.

A small AST walker rather than ``xgettext``: the rule is simply "a string literal
passed to ``_()``", which is exactly what the code does, and it means the
template can be regenerated on any machine with nothing but Python installed.

    ./tools/extract_strings.py            # writes po/minttweaks.pot
    ./tools/extract_strings.py --check    # exit 1 if the template is stale
    ./tools/extract_strings.py --refresh  # also update the "#:" line references
                                          # in every po/*.po
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from po import format_entry, format_header, read_po  # noqa: E402  (local helper module)

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "minttweaks"
POT = ROOT / "po" / "minttweaks.pot"

HEADER = """\
# Translation template for MintTweaks.
# Copyright (C) 2024 MintTweaks contributors
# This file is distributed under the same licence as the MintTweaks package.
#
#, fuzzy
msgid ""
msgstr ""
"Project-Id-Version: minttweaks\\n"
"Report-Msgid-Bugs-To: \\n"
"POT-Creation-Date: \\n"
"PO-Revision-Date: \\n"
"Last-Translator: \\n"
"Language-Team: \\n"
"Language: \\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"X-Domain: minttweaks\\n"
"""


def call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def collect(paths: List[pathlib.Path]) -> Tuple[Dict[str, List[str]], List[str]]:
    """Return ``{msgid: [references]}`` and the f-strings that cannot be extracted."""
    found: Dict[str, List[str]] = {}
    untranslatable: List[str] = []

    for path in paths:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        relative = path.relative_to(ROOT)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or call_name(node) != "_":
                continue
            if len(node.args) != 1 or node.keywords:
                continue
            argument = node.args[0]
            if isinstance(argument, ast.JoinedStr):
                untranslatable.append(f"{relative}:{node.lineno}: f-string passed to _()")
                continue
            if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                continue
            if not argument.value.strip():
                continue
            found.setdefault(argument.value, []).append(f"{relative}:{node.lineno}")

    return found, untranslatable


def _references(found: Dict[str, List[str]], msgid: str) -> List[str]:
    references = found[msgid][:3]
    if len(found[msgid]) > 3:
        references = references + [f"… (+{len(found[msgid]) - 3})"]
    return references


def render_pot(found: Dict[str, List[str]]) -> str:
    blocks = [
        format_entry(msgid, "", _references(found, msgid))
        for msgid in sorted(found, key=lambda text: text.lower())
    ]
    return HEADER + "\n" + "\n\n".join(blocks) + "\n"


def po_unquote(quoted: str) -> str:
    return ast.literal_eval(quoted)


def refresh_po(path: pathlib.Path, found: Dict[str, List[str]]) -> Tuple[int, int]:
    """Rewrite a catalogue: fresh ``#:`` references, canonical layout.

    Line numbers move constantly; the translated strings must not.  Entries whose
    msgid no longer exists in the source are dropped, so the file always mirrors
    the code. Returns ``(kept, dropped)``.
    """
    entries, _warnings, order = read_po(path)
    header = entries.get("", "")
    text = path.read_text(encoding="utf-8")
    preamble = text.split('msgid ""')[0].rstrip()

    blocks = []
    dropped = 0
    for msgid in order:
        if msgid == "":
            continue
        if msgid not in found:
            dropped += 1
            continue
        blocks.append(format_entry(msgid, entries[msgid], _references(found, msgid)))

    body = format_header(header)
    path.write_text(
        preamble + "\n" + body + "\n\n" + "\n\n".join(blocks) + "\n",
        encoding="utf-8",
    )
    return len(blocks), dropped


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the template is out of date")
    parser.add_argument("--refresh", action="store_true", help="also refresh the #: references in po/*.po")
    options = parser.parse_args(argv[1:])

    paths = sorted(PACKAGE.rglob("*.py"))
    found, untranslatable = collect(paths)
    rendered = render_pot(found)

    if untranslatable:
        print("Strings that cannot be extracted:", file=sys.stderr)
        for line in untranslatable:
            print(f"  {line}", file=sys.stderr)
        return 2

    if options.check:
        current = POT.read_text(encoding="utf-8") if POT.is_file() else ""
        if current != rendered:
            print(f"{POT.relative_to(ROOT)} is out of date; run ./tools/extract_strings.py", file=sys.stderr)
            return 1
        print(f"{POT.relative_to(ROOT)} is up to date ({len(found)} strings).")
        return 0

    POT.parent.mkdir(parents=True, exist_ok=True)
    POT.write_text(rendered, encoding="utf-8")
    print(f"wrote {POT.relative_to(ROOT)} with {len(found)} strings")

    if options.refresh:
        for catalogue in sorted(POT.parent.glob("*.po")):
            kept, dropped = refresh_po(catalogue, found)
            print(
                f"refreshed {catalogue.relative_to(ROOT)}: "
                f"{kept} entries, {dropped} obsolete removed"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
