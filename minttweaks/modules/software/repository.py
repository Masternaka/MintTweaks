"""Explicit installation of the fixed Masternaka repository."""

from pathlib import Path

from ...core import paths
from ...core.runner import cmd
from ...i18n import _

URL = "https://masternaka.github.io/masternaka-repository/"
FINGERPRINT = "86A7954635E2B4A77CAC8F00E25B26CC99FBDB1C"
KEY_PATH = Path("/etc/apt/keyrings/masternaka.asc")
SOURCE_PATH = Path("/etc/apt/sources.list.d/masternaka.list")


def find_helper():
    for helper in (Path("/usr/lib/minttweaks/mtk-repository"), paths.PKG_DIR.parent / "data" / "mtk-repository"):
        if helper.is_file():
            return helper
    raise ValueError(_("The repository helper is missing. Reinstall MintTweaks."))


def install(runner, on_line=None):
    if runner.dry_run:
        # Do not read system state, request root, write files or access the network.
        return None
    return runner.stream(cmd(str(find_helper()), "install", root=True), on_line=on_line, timeout=360)
