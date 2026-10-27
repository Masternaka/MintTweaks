"""Native third-party browsers, with explicit source and APT plan review."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import backend  # noqa: E402
from ...i18n import _  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import Page  # noqa: E402


class SoftwarePage(Page):
    page_name = "software"
    page_title = _("Native software")
    page_icon = "system-software-install-symbolic"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.status = {}
        self.checks = {}
        self.labels = {}
        self._loading = False
        self._busy = False
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(18)
        if not widgets.escalation_available(self.ctx.runner):
            box.pack_start(widgets.info_bar(_("Administrator authorization is unavailable: package state can be read, but installation is disabled.")), False, False, 0)
        catalog, body = widgets.card(_("Browsers outside Mint's official repositories"),
            _("Native APT packages only. Configure the indicated repository first; this page does not add repositories or signing keys."))
        for app in backend.CATALOG:
            check = Gtk.CheckButton(label=app.name)
            check.set_sensitive(False)
            check.connect("toggled", lambda _check: self._update_controls())
            self.checks[app.id] = check
            body.pack_start(check, False, False, 0)
            body.pack_start(widgets.label(app.source, wrap=True), False, False, 0)
            body.pack_start(widgets.label(app.origin, dim=True, wrap=True, selectable=True), False, False, 0)
            self.labels[app.id] = widgets.label(_("Not analysed yet."), wrap=True)
            body.pack_start(self.labels[app.id], False, False, 0)
            body.pack_start(Gtk.LinkButton.new_with_label(app.guide, _("Repository setup instructions")), False, False, 0)
        self.reload_button = widgets.button(_("Re-analyse"), self.refresh)
        body.pack_start(self.reload_button, False, False, 0)
        self.install_button = widgets.button(_("Preview selected installations"), self._on_install, "suggested-action")
        self.install_button.set_sensitive(False)
        body.pack_start(self.install_button, False, False, 0)
        box.pack_start(catalog, False, False, 0)
        self.pack_start(widgets.scrolled(box), True, True, 0)

    def _selected(self):
        return [app.id for app in backend.CATALOG if self.checks[app.id].get_active()
                and app.id in self.status and self.status[app.id].installable]

    def _update_controls(self):
        ready = not self._loading and not self._busy and not self.ctx.runner.dry_run
        allowed = ready and widgets.escalation_available(self.ctx.runner)
        for key, check in self.checks.items():
            check.set_sensitive(bool(allowed and key in self.status and self.status[key].installable))
        self.install_button.set_sensitive(bool(allowed and self._selected()))
        self.reload_button.set_sensitive(not self._loading and not self._busy)

    def refresh(self):
        if self._loading or self._busy:
            return
        self._loading = True
        self._update_controls()
        self.ctx.run_async(lambda: backend.collect_status(self.ctx.runner), on_done=self._apply_status, on_error=self._failed)

    def _apply_status(self, status):
        self.status = status
        self._loading = False
        for app in backend.CATALOG:
            entry = status[app.id]
            if entry.error:
                text = _("Package check unavailable: {error}").format(error=entry.error)
            elif entry.installed:
                text = _("APT package installed: {version}").format(version=entry.installed_version)
            else:
                text = _("APT package not installed. Candidate from the expected source: {version}").format(version=entry.candidate)
            self.labels[app.id].set_text(text)
            if not entry.installable:
                self.checks[app.id].set_active(False)
        self._update_controls()

    def _on_install(self):
        if self._loading or self._busy:
            return
        selected = self._selected()
        if not selected:
            return
        self._busy = True
        self._update_controls()
        self.ctx.run_async(lambda: backend.preview_install(self.ctx.runner, selected),
                           on_done=self._confirm_install, on_error=self._failed)

    def _confirm_install(self, plan):
        lines = []
        for key, spec in zip(plan.ids, plan.specs):
            app = backend.APP_BY_ID[key]
            lines.extend([app.name + " — " + spec, app.source, app.origin, ""])
        lines.extend(plan.output.splitlines())
        if not widgets.confirm_list(self.window, _("Install these native packages?"), lines,
            _("Review the complete APT simulation, including dependencies and upgrades. Removals are refused. "
              "The plan will be checked again before installation; repository configuration is not changed.")):
            self._busy = False
            self._update_controls()
            return
        self.run_operation(lambda: backend.install(self.ctx.runner, plan, on_line=self.ctx.log),
                           on_done=self._after_install, on_error=self._failed, name=_("Install native software"))

    def _after_install(self, outcome):
        self._busy = False
        detail = outcome.message
        if not outcome.ok and outcome.result is not None:
            detail += "\n" + outcome.result.output
        if outcome.states:
            detail += "\n" + "\n".join(backend.APP_BY_ID[key].name + ": " + error for key, error in outcome.states.items())
        self.ctx.log(detail, "ok" if outcome.ok else "error")
        if not outcome.ok:
            self.error(_("The software installation was not fully verified."), detail)
        self.refresh()

    def _failed(self, exc):
        self._loading = False
        self._busy = False
        self._update_controls()
        self.error(_("The software operation failed."), str(exc))
