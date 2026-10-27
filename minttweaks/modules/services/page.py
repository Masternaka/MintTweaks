"""The Services page: browse systemd units, drive them, read their logs."""

from __future__ import annotations

from typing import List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from ...modules.services import backend as svc  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import AppContext, Page  # noqa: E402
from ...i18n import _  # noqa: E402

COL_NAME, COL_STATE, COL_ENABLED, COL_DESCRIPTION, COL_UNIT = range(5)
FOLLOW_INTERVAL_MS = 3000


class ServicesPage(Page):
    page_name = "services"
    page_title = "Services"
    page_icon = "system-run-symbolic"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.units: List[svc.Unit] = []
        self.selected: Optional[svc.Unit] = None
        self._follow_source: Optional[int] = None
        self._log_busy = False
        self._want_root_logs = False
        self._can_escalate = widgets.escalation_available(ctx.runner)
        self._units_current = True

        self.store = Gtk.ListStore(str, str, str, str, object)
        self.filter = self.store.filter_new()
        self.filter.set_visible_func(self._visible)

        self._build()

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        toolbar.set_margin_top(10)
        toolbar.set_margin_bottom(6)
        self.pack_start(toolbar, False, False, 0)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text(_("Filter by name or description"))
        self.search.connect("search-changed", lambda _e: self._refilter())
        toolbar.pack_start(self.search, True, True, 0)

        self.running_only = Gtk.CheckButton(label=_("Running only"))
        self.running_only.connect("toggled", lambda _c: self._refilter())
        toolbar.pack_start(self.running_only, False, False, 0)

        self.failed_only = Gtk.CheckButton(label=_("Failed only"))
        self.failed_only.connect("toggled", lambda _c: self._refilter())
        toolbar.pack_start(self.failed_only, False, False, 0)

        toolbar.pack_start(widgets.button(_("Reload"), self.refresh), False, False, 0)

        self.units_hint = widgets.label("", wrap=True)
        self.units_hint.set_no_show_all(True)
        self.pack_start(self.units_hint, False, False, 0)

        if not self._can_escalate:
            warning = widgets.info_bar(
                _("Administrator rights are unavailable in this session: services can be inspected but not changed.")
            )
            warning.set_message_type(Gtk.MessageType.WARNING)
            self.pack_start(warning, False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_position(320)
        self.pack_start(paned, True, True, 0)

        paned.pack1(self._build_tree(), True, False)
        paned.pack2(self._build_details(), True, False)

    def _build_tree(self) -> Gtk.Widget:
        view = Gtk.TreeView(model=self.filter)
        view.set_headers_visible(True)
        for index, heading, expand in (
            (COL_NAME, "Service", False),
            (COL_STATE, "State", False),
            (COL_ENABLED, "Startup", False),
            (COL_DESCRIPTION, "Description", True),
        ):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(heading, renderer, text=index)
            column.set_resizable(True)
            column.set_expand(expand)
            view.append_column(column)
        view.get_selection().connect("changed", self._on_selection_changed)
        self.tree = view
        return widgets.scrolled(view, min_height=180)

    def _build_details(self) -> Gtk.Widget:
        notebook = Gtk.Notebook()
        notebook.set_margin_top(6)

        # --- actions tab ---
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_margin_start(12)
        page.set_margin_end(12)
        page.set_margin_top(8)
        page.set_margin_bottom(8)

        self.unit_heading = widgets.title(_("Select a service"))
        self.unit_subtitle = widgets.label("", dim=True, wrap=True)
        page.pack_start(self.unit_heading, False, False, 0)
        page.pack_start(self.unit_subtitle, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.action_buttons = {}
        for label, action in (
            (_("Start"), "start"),
            (_("Stop"), "stop"),
            (_("Restart"), "restart"),
            (_("Enable"), "enable"),
            (_("Disable"), "disable"),
        ):
            widget = widgets.button(label, lambda a=action: self._control(a))
            if not self._can_escalate:
                widget.set_sensitive(False)
            self.action_buttons[action] = widget
            buttons.pack_start(widget, False, False, 0)
        page.pack_start(buttons, False, False, 0)

        log_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        log_header.pack_start(widgets.title(_("Journal")), False, False, 0)
        self.follow_toggle = Gtk.CheckButton(label=_("Follow"))
        self.follow_toggle.connect("toggled", self._on_follow_toggled)
        log_header.pack_end(self.follow_toggle, False, False, 0)
        log_header.pack_end(widgets.button(_("Reload"), self._reload_logs), False, False, 0)
        self.root_logs_button = widgets.button(_("Read as administrator"), self._reload_logs_as_root)
        log_header.pack_end(self.root_logs_button, False, False, 0)
        page.pack_start(log_header, False, False, 0)

        log_window, self.log_view, self.log_buffer = widgets.text_view(height=140)
        page.pack_start(log_window, True, True, 0)

        self.log_hint = widgets.label("", dim=True, wrap=True)
        page.pack_start(self.log_hint, False, False, 0)

        notebook.append_page(page, Gtk.Label(label=_("Service")))

        # --- boot tab ---
        boot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        boot.set_margin_start(12)
        boot.set_margin_end(12)
        boot.set_margin_top(8)
        boot.set_margin_bottom(8)
        boot.pack_start(widgets.title(_("Boot time")), False, False, 0)
        self.boot_summary = widgets.label("", dim=True, wrap=True)
        boot.pack_start(self.boot_summary, False, False, 0)
        boot.pack_start(widgets.button(_("Analyse boot"), self._analyse_boot), False, False, 0)
        boot_window, _view, self.boot_buffer = widgets.text_view(height=160)
        boot.pack_start(boot_window, True, True, 0)
        notebook.append_page(boot, Gtk.Label(label=_("Boot")))

        return notebook

    # -- filtering ---------------------------------------------------------
    def _visible(self, model: Gtk.TreeModel, tree_iter: Gtk.TreeIter, _data=None) -> bool:
        unit = model[tree_iter][COL_UNIT]
        if unit is None:
            return False
        if self.running_only.get_active() and not unit.running:
            return False
        if self.failed_only.get_active() and not unit.failed:
            return False
        needle = self.search.get_text().strip().lower()
        if needle and needle not in unit.name.lower() and needle not in unit.description.lower():
            return False
        return True

    def _refilter(self) -> None:
        self.filter.refilter()

    def _refill(self) -> None:
        self.store.clear()
        for unit in self.units:
            self.store.append(
                [unit.name, unit.state_label, unit.enabled, unit.description, unit]
            )
        self._refilter()
        failed = [unit for unit in self.units if unit.failed]
        if failed:
            self.ctx.log(f"{len(failed)} failed service(s): {', '.join(u.name for u in failed[:5])}", "warn")

    # -- data loading ------------------------------------------------------
    def refresh(self) -> None:
        self.ctx.run_async(lambda: svc.list_units(self.ctx.runner), on_done=self._apply_units, on_error=self._units_failed)

    def _units_failed(self, exc: BaseException) -> None:
        self._units_current = False
        self.units_hint.set_text(_("Service state unavailable. Previous results, if any, have not been updated.\n{error}").format(error=exc))
        self.units_hint.show()
        self.selected = None
        self._restore_action_buttons()
        self.ctx.log(str(exc), "warn")

    def _apply_units(self, units: List[svc.Unit]) -> None:
        self._units_current = True
        self.units_hint.hide()
        self.units = units
        self._refill()
        self.ctx.log(f"{len(units)} service units loaded.", "ok")

    def _on_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            self.selected = None
            self.unit_heading.set_text(_("Select a service"))
            self.unit_subtitle.set_text("")
            return
        unit = model[tree_iter][COL_UNIT]
        self.selected = unit
        self.unit_heading.set_text(unit.name)
        subtitle = _("{state} · startup: {enabled}").format(state=unit.state_label, enabled=unit.enabled)
        if unit.description:
            subtitle += f" · {unit.description}"
        self.unit_subtitle.set_text(subtitle)
        for action_button in self.action_buttons.values():
            action_button.set_sensitive(self._can_escalate and self._units_current)
        self._reload_logs()

    # -- actions -----------------------------------------------------------
    def _control(self, action: str) -> None:
        if self.selected is None or not self._units_current:
            return
        unit = self.selected.name
        if action in ("stop", "disable") and not self.confirm(
            f"{action.capitalize()} {unit}?", _("This changes the running system immediately.")
        ):
            return
        self.ctx.log(f"systemctl {action} {unit}")
        for widget in self.action_buttons.values():
            widget.set_sensitive(False)
        self.run_operation(
            lambda: svc.control(self.ctx.runner, unit, action, on_line=self.ctx.log),
            on_done=lambda result: self._after_control(unit, action, result),
            on_error=self._control_failed,
            name=f"{action} {unit}",
        )

    def _restore_action_buttons(self) -> None:
        for widget in self.action_buttons.values():
            widget.set_sensitive(self._can_escalate and self._units_current and self.selected is not None)

    def _control_failed(self, exc: BaseException) -> None:
        self._restore_action_buttons()
        self.error(_("The operation failed."), str(exc))

    def _after_control(self, unit: str, action: str, result) -> None:
        self._restore_action_buttons()
        if result.ok:
            self.ctx.log(f"{action} {unit}: done.", "ok")
        else:
            self.ctx.log(f"{action} {unit} failed: {result.output}", "error")
        self.refresh()
        if self.selected is not None and self.selected.name == unit:
            self._reload_logs()

    def _reload_logs(self) -> None:
        if self.selected is None or self._log_busy:
            return
        unit = self.selected.name
        as_root = self._want_root_logs
        self._want_root_logs = False
        self._log_busy = True
        self.ctx.run_async(
            lambda: svc.journal(self.ctx.runner, unit, as_root=as_root),
            on_done=lambda result: self._apply_logs(unit, result),
            on_error=self._logs_failed,
        )

    def _logs_failed(self, exc: BaseException) -> None:
        self._log_busy = False
        self.log_hint.set_text(_("The journal could not be read: {error}").format(error=exc))
        self.ctx.log(str(exc), "warn")

    def _reload_logs_as_root(self) -> None:
        self._want_root_logs = True
        self._reload_logs()

    def _apply_logs(self, unit: str, result) -> None:
        self._log_busy = False
        if self.selected is None or self.selected.name != unit:
            return
        text = (result.stdout or "").strip()
        self.log_buffer.set_text("")
        if not result.ok or result.stderr.strip():
            self.log_buffer.insert_at_cursor(text or _("No journal entries could be verified."))
            detail = result.stderr.strip() or result.output or f"rc={result.returncode}"
            self.log_hint.set_text(_("The journal may be incomplete: {error}").format(error=detail))
        elif text:
            self.log_buffer.insert_at_cursor(text)
            self.log_hint.set_text("")
        elif result.ok:
            self.log_buffer.insert_at_cursor(_("No journal entry for this service."))
            self.log_hint.set_text("")

    def _on_follow_toggled(self, toggle: Gtk.CheckButton) -> None:
        if toggle.get_active():
            self._follow_source = GLib.timeout_add(FOLLOW_INTERVAL_MS, self._follow_tick)
        elif self._follow_source is not None:
            GLib.source_remove(self._follow_source)
            self._follow_source = None

    def _follow_tick(self) -> bool:
        if not self.get_mapped():
            return True
        self._reload_logs()
        return True

    def _analyse_boot(self) -> None:
        self.ctx.run_async(lambda: svc.collect_boot_report(self.ctx.runner), on_done=self._apply_boot)

    def _apply_boot(self, report: svc.BootReport) -> None:
        summary, blame, chain = report.summary, report.blame, report.chain
        self.boot_summary.set_text(
            _("Could not verify {part}: {error}").format(part="summary", error=report.errors["summary"])
            if "summary" in report.errors else summary or _("systemd-analyze returned nothing.")
        )
        lines = [_("Slowest units:"), ""]
        for duration, unit in blame:
            lines.append(f"  {duration:>10}  {unit}")
        lines += ["", _("Critical chain:"), "", chain.strip() or "  " + _("(not available)")]
        for part, error in report.errors.items():
            lines += ["", _("Could not verify {part}: {error}").format(part=part, error=error)]
        self.boot_buffer.set_text("\n".join(lines))
        self.ctx.log(_("Boot analysis updated."), "warn" if report.errors else "ok")
