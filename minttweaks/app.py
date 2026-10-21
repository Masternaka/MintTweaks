"""Application entry point."""

from __future__ import annotations

import logging
import os
import sys
from typing import List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, __version__, i18n  # noqa: E402
from .core import logs, paths  # noqa: E402
from .core.privilege import Escalator, is_root  # noqa: E402
from .core.runner import SubprocessRunner  # noqa: E402
from .ui.widgets import AppContext  # noqa: E402
from .ui.window import MainWindow  # noqa: E402

USAGE = f"""\
{APP_NAME} {__version__} - maintenance, services and Samba for Linux Mint

Usage: minttweaks [OPTION]

Options:
  -h, --help       show this message and exit
  -v, --version    show the version and exit
      --lang CODE  force the interface language (fr, en, ...)
      --dry-run    do not run any command, just print what would be run

Environment:
  MTK_LOCALEDIR    directory holding the compiled translation catalogues
  MTK_ROOT_CMD     replace the escalation command (default: pkexec)
  MTK_DRY_RUN      set to 1 to simulate every command
"""


class MintTweaksApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        runner = SubprocessRunner(escalator=Escalator())
        self.ctx = AppContext(runner)

    # -- lifecycle ---------------------------------------------------------
    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        logs.setup()
        paths.ensure_user_dirs()
        self._install_actions()

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = MainWindow(self, self.ctx)
        window.present()

    # -- actions -----------------------------------------------------------
    def _install_actions(self) -> None:
        for name, callback in (
            ("refresh", lambda *_: self._call_window("refresh_current")),
            ("clear-output", lambda *_: self._call_window("clear_output")),
            ("about", lambda *_: self._call_window("show_about")),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def _call_window(self, method: str) -> None:
        window = self.props.active_window
        if window is not None:
            getattr(window, method)()


def _strip_own_flags(argv: List[str]) -> List[str]:
    return [argument for argument in argv if argument not in ("--dry-run",)]


def _split_language(argv: List[str]) -> tuple:
    """Pull ``--lang CODE`` / ``--lang=CODE`` out of the command line."""
    remaining: List[str] = []
    language: Optional[str] = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--lang" and index + 1 < len(argv):
            language = argv[index + 1]
            index += 2
            continue
        if argument.startswith("--lang="):
            language = argument.split("=", 1)[1]
            index += 1
            continue
        remaining.append(argument)
        index += 1
    return language, remaining


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    if "-v" in argv or "--version" in argv:
        print(f"{APP_NAME} {__version__}")
        return 0

    language, argv = _split_language(argv)
    logs.setup()
    active_language = i18n.install([language] if language else None)
    logging.getLogger("minttweaks").info("interface language: %s", active_language)

    if is_root():
        sys.stderr.write(
            f"{APP_NAME} must run as your desktop user, not as root: it asks for "
            "administrator rights only when it needs them.\n"
        )
        return 1

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        sys.stderr.write(f"{APP_NAME} needs a graphical session (DISPLAY or WAYLAND_DISPLAY).\n")
        return 1

    application = MintTweaksApp()
    return application.run(_strip_own_flags(argv))


if __name__ == "__main__":
    sys.exit(main())
