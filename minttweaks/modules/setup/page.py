"""A resumable guide to existing modules, with explicit user verification."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import backend  # noqa: E402
from ...i18n import _  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import Page  # noqa: E402


def state_label(state):
    return {"pending": _("To do"), "verified": _("Verified by you"), "retry": _("To retry")}[state]


class SetupPage(Page):
    page_name = "setup"
    page_title = _("After installation")
    page_icon = "view-list-symbolic"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.plan = None
        self._busy = False
        self._updating = False
        self._dirty = False
        self._read_failed = False
        self.checks = {}
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(18)
        choose, body = widgets.card(_("Choose optional steps"), _("This guide opens the existing modules. It does not install software or change settings by itself."))
        for step in backend.STEPS:
            check = Gtk.CheckButton(label=step.title)
            check.connect("toggled", lambda _check: self._selection_changed())
            self.checks[step.id] = check
            body.pack_start(check, False, False, 0)
        self.save_button = widgets.button(_("Save selected steps"), self._save_selection)
        body.pack_start(self.save_button, False, False, 0)
        box.pack_start(choose, False, False, 0)

        overview, body = widgets.card(_("Your preparation plan"), _("Review the purpose and source of each step. Exact changes are chosen in its module."))
        scroller, _view, self.summary_buffer = widgets.text_view(monospace=False, height=160)
        body.pack_start(scroller, True, True, 0)
        self.status_label = widgets.label(_("Loading the saved checklist…"), wrap=True)
        body.pack_start(self.status_label, False, False, 0)
        self.next_button = widgets.button(_("Open the next unfinished step"), self._open_next, "suggested-action")
        body.pack_start(self.next_button, False, False, 0)
        self.reload_button = widgets.button(_("Reload saved progress"), self.refresh)
        body.pack_start(self.reload_button, False, False, 0)
        box.pack_start(overview, False, False, 0)

        progress, body = widgets.card(_("Record your result"), _("After checking the result in the module, mark the step as verified by you or keep it for another attempt. Opening a page never completes a step."))
        self.step_combo = Gtk.ComboBoxText()
        self.step_combo.connect("changed", lambda _combo: self._show_result())
        body.pack_start(self.step_combo, False, False, 0)
        self.open_button = widgets.button(_("Open selected step"), self._open_selected)
        body.pack_start(self.open_button, False, False, 0)
        self.note_entry = Gtk.Entry()
        self.note_entry.set_max_length(500)
        self.note_entry.set_placeholder_text(_("Result or error to remember"))
        body.pack_start(self.note_entry, False, False, 0)
        self.result_buttons = []
        for label, state in ((_("Mark verified by you"), "verified"), (_("Keep for another attempt"), "retry"), (_("Mark to do"), "pending")):
            button = widgets.button(label, lambda value=state: self._save_result(value))
            self.result_buttons.append(button)
            body.pack_start(button, False, False, 0)
        box.pack_start(progress, False, False, 0)
        self.pack_start(widgets.scrolled(box), True, True, 0)
        self._update_controls()

    def _selected(self):
        return [step.id for step in backend.STEPS if self.checks[step.id].get_active()]

    def _selection_changed(self):
        if self._updating:
            return
        self._dirty = self.plan is not None and self._selected() != self.plan.selected
        self._show_summary()
        self._update_controls()

    def _show_summary(self):
        lines = []
        for key in self._selected():
            step = backend.STEP_BY_ID[key]
            lines.extend([step.title, step.detail, ""])
        self.summary_buffer.set_text("\n".join(lines))

    def _update_controls(self):
        loaded = self.plan is not None and not self._read_failed
        editing = loaded and not self._busy and not self.ctx.runner.dry_run
        selected = loaded and self.step_combo.get_active_id() in self.plan.selected
        for check in self.checks.values():
            check.set_sensitive(editing)
        self.save_button.set_sensitive(editing and self._dirty)
        self.reload_button.set_sensitive(not self._busy)
        self.next_button.set_sensitive(bool(loaded and not self._busy and not self._dirty and self.plan.next_step is not None))
        self.step_combo.set_sensitive(bool(loaded and not self._busy and not self._dirty and self.plan.selected))
        self.open_button.set_sensitive(bool(selected and not self._busy and not self._dirty))
        self.note_entry.set_sensitive(bool(editing and selected and not self._dirty))
        for button in self.result_buttons:
            button.set_sensitive(bool(editing and selected and not self._dirty))

    def refresh(self):
        if self._busy:
            return
        if self._dirty and not self.confirm(_("Discard unsaved step selection?")):
            return
        self._busy = True
        self._update_controls()
        self.ctx.run_async(backend.load_plan, on_done=self._apply_plan, on_error=self._failed)

    def _apply_plan(self, plan):
        self.plan = plan
        self._busy = False
        self._read_failed = False
        self._dirty = False
        self._updating = True
        try:
            for key, check in self.checks.items():
                check.set_active(key in plan.selected)
            self.step_combo.remove_all()
            for key in plan.selected:
                self.step_combo.append(key, backend.STEP_BY_ID[key].title + " — " + state_label(plan.progress[key].state))
            if plan.next_step is not None:
                self.step_combo.set_active_id(plan.next_step.id)
            else:
                self.step_combo.set_active(0 if plan.selected else -1)
        finally:
            self._updating = False
        self.status_label.set_text(_("{verified} of {total} step(s) verified by you.").format(verified=plan.verified, total=len(plan.selected)))
        self._show_summary()
        self._show_result()
        self._update_controls()

    def _show_result(self):
        key = self.step_combo.get_active_id()
        note = self.plan.progress[key].note if self.plan is not None and key in self.plan.selected else ""
        self.note_entry.set_text(note)
        self._update_controls()

    def _navigate(self, step):
        if self._dirty or self._busy or self._read_failed:
            return
        window = self.get_toplevel()
        show_page = getattr(window, "show_page", None)
        if callable(show_page):
            show_page(step.page)

    def _open_next(self):
        if self.plan is not None and self.plan.next_step is not None:
            self._navigate(self.plan.next_step)

    def _open_selected(self):
        key = self.step_combo.get_active_id()
        if self.plan is not None and key in self.plan.selected:
            self._navigate(backend.STEP_BY_ID[key])

    def _save_selection(self):
        if self.plan is None or self._busy or self._read_failed:
            return
        selected = self._selected()
        self._persist(selected)

    def _save_result(self, state):
        key = self.step_combo.get_active_id()
        if self.plan is None or self._dirty or self._busy or self._read_failed or key not in self.plan.selected:
            return
        self._persist(list(self.plan.selected), step_id=key, state=state, note=self.note_entry.get_text())

    def _persist(self, selected, **changes):
        self._busy = True
        self._update_controls()
        self.run_operation(
            lambda: backend.save_plan(self.ctx.runner, self.plan, selected, **changes),
            on_done=self._apply_plan, on_error=self._failed, name=_("Save preparation progress"),
        )

    def _failed(self, exc):
        self._busy = False
        self._read_failed = True
        self.status_label.set_text(_("Progress was not updated. Reload before continuing.\n{error}").format(error=exc))
        self._update_controls()
