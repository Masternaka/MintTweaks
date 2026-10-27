"""The main window: sidebar, page stack, live output panel."""

from __future__ import annotations

from typing import List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk, Pango  # noqa: E402

from .. import APP_NAME, __version__  # noqa: E402
from ..modules.cinnamon.page import CinnamonPage  # noqa: E402
from ..modules.firefox.page import FirefoxPage  # noqa: E402
from ..modules.home.page import HomePage  # noqa: E402
from ..modules.maintenance.page import MaintenancePage  # noqa: E402
from ..modules.samba.page import SambaPage  # noqa: E402
from ..modules.services.page import ServicesPage  # noqa: E402
from ..modules.setup.page import SetupPage  # noqa: E402
from ..modules.software.page import SoftwarePage  # noqa: E402
from ..modules.terminal.page import TerminalPage  # noqa: E402
from . import widgets  # noqa: E402
from .widgets import AppContext, Page  # noqa: E402
from ..i18n import _  # noqa: E402

PAGE_CLASSES = (HomePage, MaintenancePage, ServicesPage, SambaPage, FirefoxPage, CinnamonPage, SetupPage, SoftwarePage, TerminalPage)

LOG_TAG_COLOURS = {
    "ok": "#1c7c3c",
    "warn": "#a35b00",
    "error": "#c02b2b",
    "command": "#555555",
}


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application, ctx: AppContext) -> None:
        super().__init__(application=application)
        self.ctx = ctx
        self.set_default_size(1120, 780)
        self.set_title(APP_NAME)
        self.set_size_request(880, 560)

        self.pages: List[Page] = []
        self._build()
        ctx.add_sink(self._on_log)
        ctx.add_operation_sink(self._on_operation_changed)
        self.connect("delete-event", self._on_delete_event)
        self._install_css()

        self.show_all()
        self.log_revealer.set_reveal_child(False)
        self.sidebar.select_row(self.sidebar.get_row_at_index(0))

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title(APP_NAME)
        if self.ctx.runner.dry_run:
            header.set_subtitle(_("Simulation: no commands or cleanup actions will be executed."))
        else:
            header.set_subtitle(_("Maintenance, services, Samba and Firefox for Linux Mint"))
        header.pack_end(self._build_menu_button())
        self.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.pack_start(body, True, True, 0)
        body.pack_start(self._build_sidebar(), False, False, 0)
        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hexpand(True)
        body.pack_start(self.stack, True, True, 0)

        for page_class in PAGE_CLASSES:
            page = page_class(self.ctx)
            self.pages.append(page)
            self.stack.add_named(page, page.page_name)

        outer.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        outer.pack_start(self._build_log_panel(), False, False, 0)
        outer.pack_start(self._build_status_bar(), False, False, 0)

    def _build_menu_button(self) -> Gtk.MenuButton:
        button = Gtk.MenuButton()
        button.set_tooltip_text(_("Menu"))
        image = Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        button.set_image(image)

        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_border_width(6)
        for text, callback in (
            (_("Refresh this page"), self.refresh_current),
            (_("Show / hide output"), self.toggle_log),
            (_("Clear output"), self.clear_output),
            (_("About"), self.show_about),
        ):
            item = Gtk.ModelButton(text=text)
            item.connect("clicked", lambda _w, cb=callback: (popover.popdown(), cb()))
            box.pack_start(item, False, False, 0)
        popover.add(box)
        box.show_all()
        button.set_popover(popover)
        return button

    def _build_sidebar(self) -> Gtk.Widget:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        container.get_style_context().add_class("sidebar")
        container.set_size_request(210, -1)

        self.sidebar = Gtk.ListBox()
        self.sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar.connect("row-selected", self._on_row_selected)

        for page_class in PAGE_CLASSES:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_border_width(8)
            icon = Gtk.Image.new_from_icon_name(page_class.page_icon, Gtk.IconSize.BUTTON)
            box.pack_start(icon, False, False, 0)
            box.pack_start(widgets.label(_(page_class.page_title)), False, False, 0)
            row.add(box)
            self.sidebar.add(row)

        container.pack_start(self.sidebar, True, True, 0)

        version = widgets.label(_("version {version}").format(version=__version__), dim=True)
        version.set_margin_start(12)
        version.set_margin_bottom(10)
        container.pack_start(version, False, False, 0)
        return container

    def _build_log_panel(self) -> Gtk.Widget:
        self.log_revealer = Gtk.Revealer()
        self.log_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.get_style_context().add_class("output-panel")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_margin_start(10)
        header.set_margin_end(10)
        header.set_margin_top(4)
        header.set_margin_bottom(2)
        header.pack_start(widgets.title(_("Output")), False, False, 0)
        header.pack_end(widgets.button(_("Hide"), self.toggle_log), False, False, 0)
        header.pack_end(widgets.button(_("Clear"), self.clear_output), False, False, 0)
        box.pack_start(header, False, False, 0)

        window, self.log_view, self.log_buffer = widgets.text_view(height=150)
        self.log_view.set_left_margin(8)
        for name, colour in LOG_TAG_COLOURS.items():
            self.log_buffer.create_tag(name, foreground=colour)
        box.pack_start(window, True, True, 0)

        self.log_revealer.add(box)
        return self.log_revealer

    def _build_status_bar(self) -> Gtk.Widget:
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.get_style_context().add_class("status-bar")
        self.status_label = widgets.label(_("Ready."), dim=True)
        self.status_label.set_ellipsize(Pango.EllipsizeMode.END)
        bar.pack_start(self.status_label, True, True, 0)
        self.operation_label = widgets.label("", dim=True)
        self.operation_label.set_ellipsize(Pango.EllipsizeMode.END)
        bar.pack_start(self.operation_label, False, False, 0)
        self.operation_spinner = Gtk.Spinner()
        bar.pack_start(self.operation_spinner, False, False, 0)
        bar.pack_end(widgets.button(_("Output"), self.toggle_log), False, False, 0)
        return bar

    def _install_css(self) -> None:
        from ..core import paths

        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(str(paths.STYLE_CSS))
        except Exception:  # a missing stylesheet must not stop the app
            return
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    # -- behaviour ---------------------------------------------------------
    def _on_operation_changed(self, name: Optional[str]) -> None:
        self.operation_label.set_text(_("In progress: {operation}").format(operation=name) if name else "")
        if name:
            self.operation_spinner.start()
        else:
            self.operation_spinner.stop()

    def show_operation_in_progress(self) -> None:
        widgets.show_info(
            self,
            _("An operation is still running."),
            _("Wait for {operation} to finish before closing MintTweaks.").format(operation=self.ctx.operation_name),
        )

    def _on_delete_event(self, _window, _event) -> bool:
        if self.ctx.operation_name is not None:
            self.show_operation_in_progress()
            return True
        return False

    def _on_row_selected(self, listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        if row is None:
            return
        index = listbox.get_children().index(row)
        if not 0 <= index < len(PAGE_CLASSES):
            return
        name = PAGE_CLASSES[index].page_name
        self.stack.set_visible_child_name(name)
        page = self.stack.get_child_by_name(name)
        if isinstance(page, Page):
            page.ensure_loaded()

    @property
    def current_page(self) -> Optional[Page]:
        child = self.stack.get_visible_child()
        return child if isinstance(child, Page) else None

    def refresh_current(self) -> None:
        page = self.current_page
        if page is not None:
            page.refresh()

    def show_page(self, name: str) -> None:
        for index, page_class in enumerate(PAGE_CLASSES):
            if page_class.page_name == name:
                self.sidebar.select_row(self.sidebar.get_row_at_index(index))
                return

    def toggle_log(self) -> None:
        self.log_revealer.set_reveal_child(not self.log_revealer.get_reveal_child())

    def clear_output(self) -> None:
        self.log_buffer.set_text("")

    def _on_log(self, message: str, level: str) -> None:
        prefix = {"ok": "✓ ", "warn": "! ", "error": "✗ "}.get(level, "")
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert_with_tags_by_name(end, f"{prefix}{message}\n", level)
        self.status_label.set_text(message.splitlines()[0] if message else "Ready.")
        self._scroll_output_to_end()
        if level in ("warn", "error"):
            self.log_revealer.set_reveal_child(True)

    def _scroll_output_to_end(self) -> None:
        mark = self.log_buffer.get_insert()
        self.log_view.scroll_mark_onscreen(mark)

    def show_about(self) -> None:
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_version(__version__)
        dialog.set_comments(
            _(
                "Maintenance, services, Samba and Firefox management for Linux Mint.\n"
                "Inspired by the ArchLinux Tweak Tool."
            )
        )
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.set_wrap_license(True)
        dialog.run()
        dialog.destroy()
