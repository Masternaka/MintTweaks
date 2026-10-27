#!/usr/bin/env python3
"""Plan a development or stable release without publishing anything.

Only --apply updates the three version markers in the build checkout.
GitHub output is deliberately restricted to validated single-line values.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


@dataclass(frozen=True)
class ReleasePlan:
    channel: str
    version: str = ""
    tag: str = ""

    def outputs(self) -> str:
        return "\n".join((
            f"publish={'false' if self.channel == 'none' else 'true'}",
            f"channel={self.channel}", f"version={self.version}", f"tag={self.tag}",
        )) + "\n"


def plan_release(base: str, event: str, ref: str, sha: str, run_number: str, attempt: str) -> ReleasePlan:
    if not re.fullmatch(VERSION, base):
        raise ValueError("The base version must have the form X.Y.Z.")
    if event == "pull_request":
        return ReleasePlan("none")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected the full source commit SHA.")
    if event == "push" and ref.startswith("refs/tags/"):
        tag = ref[len("refs/tags/"):]
        if tag != f"v{base}":
            raise ValueError("A stable tag must match the source version exactly: v" + base)
        return ReleasePlan("stable", base, tag)
    if event in ("push", "workflow_dispatch") and ref == "refs/heads/main":
        if not all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run_number, attempt)):
            raise ValueError("Run number and attempt must be positive integers.")
        version = f"{base}~dev.{run_number}.{attempt}.{sha[:12]}"
        return ReleasePlan("development", version, f"v{base}-dev.{run_number}.{attempt}")
    raise ValueError("Development releases require main; stable releases require a matching pushed tag.")


def source_version(root: Path) -> str:
    source = (root / "minttweaks/__init__.py").read_text(encoding="utf-8")
    matches = re.findall(r'^__version__ = "([^"]+)"$', source, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError("Expected one application version marker.")
    return matches[0]


def stamp_version(root: Path, base: str, version: str) -> None:
    replacements = {
        "minttweaks/__init__.py": (f'__version__ = "{base}"', f'__version__ = "{version}"'),
        "data/minttweaks.1": (f'"minttweaks {base}"', f'"minttweaks {version}"'),
        "debian/changelog": (f"minttweaks ({base})", f"minttweaks ({version})"),
    }
    changes = []
    # Validate every marker before changing any file.
    for name, (old, new) in replacements.items():
        path = root / name
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1 or (name == "debian/changelog" and not text.startswith(old + " ")):
            raise ValueError("Expected exactly one matching version marker in " + name)
        changes.append((path, text.replace(old, new, 1)))
    if version != base:
        for path, text in changes:
            path.write_text(text, encoding="utf-8")


def main(argv=None, environment: Mapping[str, str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--apply", action="store_true", help="stamp the build checkout")
    args = parser.parse_args(argv)
    env = os.environ if environment is None else environment
    try:
        base = source_version(args.root)
        plan = plan_release(base, env.get("GITHUB_EVENT_NAME", ""), env.get("GITHUB_REF", ""),
                            env.get("GITHUB_SHA", ""), env.get("GITHUB_RUN_NUMBER", ""), env.get("GITHUB_RUN_ATTEMPT", ""))
        if args.apply and plan.channel != "none":
            stamp_version(args.root, base, plan.version)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(plan.outputs(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
