"""A resumable guide to existing modules, with explicit user verification."""

from __future__ import annotations

import datetime
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import backend  # noqa: E402
from . import livecheck  # noqa: E402
from . import inspection  # noqa: E402
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
        self._live_busy = False
        self._live_status = None
        self._observing = False
        self._observation_generation = 0
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(18)
        live, body = widgets.card(_("Live installation media check"), _(livecheck.EXPLANATION))
        self.live_status_label = widgets.label(_("Loading service status…"), wrap=True)
        body.pack_start(self.live_status_label, False, False, 0)
        self.live_disable_button = widgets.button(_("Disable the Live media check"), self._disable_live_check)
        body.pack_start(self.live_disable_button, False, False, 0)
        self.live_reload_button = widgets.button(_("Reload service status"), self._refresh_live_check)
        body.pack_start(self.live_reload_button, False, False, 0)
        box.pack_start(live, False, False, 0)
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
        observations, body = widgets.card(_("Automatic observations for the selected step"),
            _("Optional read-only checks. They do not change your saved status or notes, and never mark a step verified by you."))
        self.observe_button = widgets.button(_("Observe the selected step"), self._observe_selected)
        body.pack_start(self.observe_button, False, False, 0)
        self.observation_label = widgets.label(_("No automatic observation for this selection."), wrap=True)
        body.pack_start(self.observation_label, False, False, 0)
        scroller, _view, self.observation_buffer = widgets.text_view(monospace=False, height=180)
        body.pack_start(scroller, True, True, 0)
        box.pack_start(observations, False, False, 0)
        self.pack_start(widgets.scrolled(box), True, True, 0)
        self._update_controls()
        self.ctx.add_operation_sink(self._operation_changed)

    def _selected(self):
        return [step.id for step in backend.STEPS if self.checks[step.id].get_active()]

    def _selection_changed(self):
        if self._updating:
            return
        self._invalidate_observation()
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
        self.live_disable_button.set_sensitive(bool(self._live_status and self._live_status.available and not self._live_busy and not self.ctx.runner.dry_run))
        self.live_reload_button.set_sensitive(not self._live_busy)
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
        self.observe_button.set_sensitive(bool(loaded and selected and not self._busy and not self._dirty
            and not self._observing and not self.ctx.runner.dry_run and self.ctx.operation_name is None))

    def refresh(self):
        self._refresh_live_check()
        if self._busy:
            return
        if self._dirty and not self.confirm(_("Discard unsaved step selection?")):
            return
        self._busy = True
        self._update_controls()
        self.ctx.run_async(backend.load_plan, on_done=self._apply_plan, on_error=self._failed)

    def _refresh_live_check(self):
        if self._live_busy:
            return
        self._live_busy = True
        self._update_controls()
        self.ctx.run_async(lambda: livecheck.inspect(self.ctx.runner),
                           on_done=self._apply_live_status, on_error=self._live_failed)

    def _apply_live_status(self, status):
        self._live_status = status
        self._live_busy = False
        self.live_status_label.set_text(status.detail)
        self._update_controls()

    def _live_failed(self, exc):
        self._apply_live_status(livecheck.Status(False, _("Service status could not be updated. Reload before continuing.\n{error}").format(error=exc)))

    def _disable_live_check(self):
        if self._live_busy or self.ctx.runner.dry_run or not self._live_status or not self._live_status.available:
            return
        if not self.confirm(_("Disable the Live media check?"), _(livecheck.EXPLANATION) + "\n\n" + _("This stops and disables casper-md5check.service and clears its failure state. Administrator authorization is required.")):
            return
        self._live_busy = True
        self._update_controls()
        self.run_operation(lambda: livecheck.disable(self.ctx.runner), on_done=self._apply_live_status,
                           on_error=self._live_failed, name=_("Disable the Live media check"))

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
        self._invalidate_observation()
        key = self.step_combo.get_active_id()
        note = self.plan.progress[key].note if self.plan is not None and key in self.plan.selected else ""
        self.note_entry.set_text(note)
        self._update_controls()

    def _invalidate_observation(self):
        self._observation_generation += 1
        self.observation_label.set_text(_("No automatic observation for this selection."))
        self.observation_buffer.set_text("")

    def _operation_changed(self, _name):
        self._invalidate_observation()
        self._update_controls()

    def _observe_selected(self):
        key = self.step_combo.get_active_id()
        if (self.plan is None or key not in self.plan.selected or self._dirty or self._busy
                or self._read_failed or self._observing or self.ctx.runner.dry_run or self.ctx.operation_name is not None):
            return
        self._invalidate_observation()
        request = self._observation_generation
        self._observing = True
        self.observation_label.set_text(_("Reading observations; your saved progress is unchanged…"))
        self._update_controls()
        self.ctx.run_async(lambda: inspection.collect(self.ctx.runner, key),
            on_done=lambda observation: self._apply_observation(request, key, observation),
            on_error=lambda exc: self._observation_failed(request, exc))

    def _apply_observation(self, request, key, observation):
        self._observing = False
        if request != self._observation_generation or key != self.step_combo.get_active_id():
            self._update_controls()
            return
        labels = {'detected': _("Detected"), 'not_detected': _("Not detected"),
                  'attention': _("Review manually"), 'unavailable': _("Unavailable")}
        lines = []
        for item in observation.items:
            lines.extend([item.title + ' — ' + labels[item.state], item.detail, ''])
        lines.append(observation.limitation)
        self.observation_buffer.set_text('\n'.join(lines))
        time = datetime.datetime.fromisoformat(observation.checked_at).astimezone().strftime('%Y-%m-%d %H:%M:%S')
        self.observation_label.set_text(_("Observed at {time}. Saved progress remains your own declaration.").format(time=time))
        self._update_controls()

    def _observation_failed(self, request, _exc):
        self._observing = False
        if request == self._observation_generation:
            self.observation_buffer.set_text("")
            self.observation_label.set_text(_("Observations could not be read. Your saved progress and notes are unchanged."))
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
        self._invalidate_observation()
        self._busy = False
        self._read_failed = True
        self.status_label.set_text(_("Progress was not updated. Reload before continuing.\n{error}").format(error=exc))
        self._update_controls()
