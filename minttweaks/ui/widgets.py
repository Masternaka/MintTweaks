"""Shared GTK3 building blocks and the context every page talks to.

MintTweaks targets Cinnamon, which is a GTK3 desktop: the widgets here stick to
plain GTK3 (no libadwaita) and take their colours from the current theme, so the
application inherits Mint-Y correctly.
"""

from __future__ import annotations

import html
import threading
import traceback
from typing import Callable, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402  (must follow require_version)

from ..core.runner import BaseRunner  # noqa: E402

def _once(callback: Callable, *args) -> bool:
    """Adapt a callback for ``GLib.idle_add`` (returning False = do not repeat)."""
    callback(*args)
    return False


LEVEL_TAGS = {
    "info": "info",
    "ok": "ok",
    "warn": "warn",
    "error": "error",
    "command": "command",
}


class AppContext:
    """The runner plus the places log lines have to go.

    Pages never touch widgets of other pages: they describe what happened and
    the window decides where to show it.  That keeps the three modules
    independent of each other.
    """

    def __init__(self, runner: BaseRunner) -> None:
        self.runner = runner
        self._sinks: List[Callable[[str, str], None]] = []

    # -- output ------------------------------------------------------------
    def add_sink(self, sink: Callable[[str, str], None]) -> None:
        self._sinks.append(sink)

    def log(self, message: str, level: str = "info") -> None:
        """Record a line. Safe to call from a worker thread."""
        level = level if level in LEVEL_TAGS else "info"
        if threading.current_thread() is not threading.main_thread():
            # GTK may only be touched from the main loop.
            GLib.idle_add(_once, self._emit, message, level)
            return
        self._emit(message, level)

    def _emit(self, message: str, level: str) -> None:
        for sink in list(self._sinks):
            try:
                sink(message, level)
            except Exception:  # a broken sink must not break the caller
                traceback.print_exc()

    def status(self, message: str) -> None:
        self.log(message, "info")

    # -- threading ---------------------------------------------------------
    def run_async(
        self,
        work: Callable[[], object],
        on_done: Optional[Callable[[object], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> threading.Thread:
        """Run ``work`` off the UI thread, then call back on the main loop."""

        def target() -> None:
            try:
                result = work()
            except BaseException as exc:  # noqa: BLE001 - surfaced to the user
                traceback.print_exc()
                if on_error is not None:
                    GLib.idle_add(_once, on_error, exc)
                else:
                    GLib.idle_add(_once, self.log, f"Unexpected error: {exc}", "error")
                return
            if on_done is not None:
                GLib.idle_add(_once, on_done, result)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return thread


# --------------------------------------------------------------------------- #
# Small constructors
# --------------------------------------------------------------------------- #
def label(text: str = "", *, dim: bool = False, wrap: bool = False, selectable: bool = False) -> Gtk.Label:
    widget = Gtk.Label(label=text)
    widget.set_xalign(0.0)
    widget.set_line_wrap(wrap)
    if selectable:
        widget.set_selectable(True)
    if dim:
        widget.get_style_context().add_class("dim-label")
    return widget


def title(text: str) -> Gtk.Label:
    widget = label(text)
    widget.set_use_markup(True)
    widget.set_markup(f"<b>{html.escape(text)}</b>")
    widget.set_margin_bottom(2)
    return widget


def card(title_text: Optional[str] = None, subtitle: Optional[str] = None) -> tuple:
    """A bordered container. Returns ``(outer, body)``; pack rows into ``body``."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    outer.get_style_context().add_class("card")
    outer.set_margin_top(4)
    outer.set_margin_bottom(4)

    if title_text:
        header = title(title_text)
        outer.pack_start(header, False, False, 0)
    if subtitle:
        outer.pack_start(label(subtitle, dim=True, wrap=True), False, False, 0)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    outer.pack_start(body, False, False, 0)
    return outer, body


def row(child_left: Gtk.Widget, child_right: Optional[Gtk.Widget] = None) -> Gtk.Box:
    """A horizontal row: description on the left, control on the right."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    box.pack_start(child_left, True, True, 0)
    if child_right is not None:
        if isinstance(child_right, Gtk.Switch):
            child_right.set_valign(Gtk.Align.CENTER)
        box.pack_start(child_right, False, False, 0)
    return box


def action_row(heading: str, subtitle: str, button: Gtk.Widget) -> Gtk.Box:
    texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    texts.pack_start(title(heading), False, False, 0)
    if subtitle:
        texts.pack_start(label(subtitle, dim=True, wrap=True), False, False, 0)
    return row(texts, button)


def button(text: str, on_click: Optional[Callable] = None, *classes: str) -> Gtk.Button:
    widget = Gtk.Button(label=text)
    if on_click is not None:
        widget.connect("clicked", lambda _b: on_click())
    for name in classes:
        widget.get_style_context().add_class(name)
    return widget


def scrolled(child: Gtk.Widget, min_height: int = -1) -> Gtk.ScrolledWindow:
    window = Gtk.ScrolledWindow()
    window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    window.add(child)
    if min_height > 0:
        window.set_min_content_height(min_height)
    return window


def text_view(monospace: bool = True, editable: bool = False, height: int = 160) -> tuple:
    """A text view in a scroller. Returns ``(scroller, view, buffer)``."""
    view = Gtk.TextView()
    view.set_editable(editable)
    view.set_cursor_visible(editable)
    view.set_monospace(monospace)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if not monospace else Gtk.WrapMode.NONE)
    buffer = view.get_buffer()
    window = scrolled(view, min_height=height)
    return window, view, buffer


def info_bar(text: str) -> Gtk.InfoBar:
    """A dismissible message strip."""
    bar = Gtk.InfoBar()
    bar.set_message_type(Gtk.MessageType.INFO)
    bar.set_show_close_button(True)
    content = bar.get_content_area()
    content.add(label(text, wrap=True))
    return bar


def confirm(parent: Optional[Gtk.Window], heading: str, detail: str = "", destructive: bool = False) -> bool:
    """Ask a yes/no question. Returns True when the user agrees."""
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.WARNING if destructive else Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.OK_CANCEL,
        text=heading,
    )
    if detail:
        dialog.format_secondary_text(detail)
    if destructive:
        dialog.get_widget_for_response(Gtk.ResponseType.OK).get_style_context().add_class("destructive-action")
    response = dialog.run()
    dialog.destroy()
    return response == Gtk.ResponseType.OK


def show_info(parent: Optional[Gtk.Window], heading: str, detail: str = "") -> None:
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.CLOSE,
        text=heading,
    )
    if detail:
        dialog.format_secondary_text(detail[:4000])
    dialog.run()
    dialog.destroy()


def show_error(parent: Optional[Gtk.Window], heading: str, detail: str = "") -> None:
    dialog = Gtk.MessageDialog(
        transient_for=parent,
        modal=True,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.CLOSE,
        text=heading,
    )
    if detail:
        dialog.format_secondary_text(detail[:2000])
    dialog.run()
    dialog.destroy()


def escalation_available(runner: BaseRunner) -> bool:
    """True when privileged actions can actually be attempted."""
    escalator = getattr(runner, "escalator", None)
    if escalator is None:
        return True  # test doubles and custom runners: assume yes
    try:
        return bool(escalator.available())
    except Exception:
        return False


class Page(Gtk.Box):
    """Base class for the three module pages."""

    page_name = "page"
    page_title = "Page"
    page_icon = "applications-system-symbolic"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.ctx = ctx
        self._loaded = False

    # -- lifecycle ---------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:  # pragma: no cover - overridden
        """Reload the page content from the system."""

    # -- helpers -----------------------------------------------------------
    @property
    def window(self) -> Optional[Gtk.Window]:
        return self.get_toplevel() if isinstance(self.get_toplevel(), Gtk.Window) else None

    def confirm(self, heading: str, detail: str = "", destructive: bool = False) -> bool:
        return confirm(self.window, heading, detail, destructive)

    def error(self, heading: str, detail: str = "") -> None:
        show_error(self.window, heading, detail)

    def info(self, heading: str, detail: str = "") -> None:
        show_info(self.window, heading, detail)
