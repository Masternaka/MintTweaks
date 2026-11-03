"""Personal application selection, with explicit official-source APT previews."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from . import backend, details, fonts
from ...i18n import _
from ...ui import widgets
from ...ui.widgets import Page
from ...ui.installations import InstallationDetails
from .transfer_controls import SelectionTransferControls


class ApplicationsPage(SelectionTransferControls, Page):
    page_name = 'applications'
    page_title = _("Applications")
    page_icon = 'view-app-grid-symbolic'

    def __init__(self, ctx):
        super().__init__(ctx)
        self.status, self.checks, self.labels, self.rows = {}, {}, {}, {}
        self.font_buttons = {}
        self.details = {}
        self._loading = self._busy = False
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(18)
        box.pack_start(widgets.title(_("My applications")), False, False, 0)
        box.pack_start(widgets.label(_("Choose applications from your personal list to install through Linux Mint's official repositories. Already installed applications are kept."), wrap=True), False, False, 0)
        box.pack_start(widgets.label(_("Fonts use APT first. A separate GitHub download is offered only when their official package is missing."), wrap=True), False, False, 0)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text(_("Search by name, category or package"))
        self.search.connect('search-changed', lambda _entry: self._filter())
        box.pack_start(self.search, False, False, 0)
        self.empty = widgets.label(_("Your application list is empty for now."), wrap=True)
        box.pack_start(self.empty, False, False, 0)
        self.summary = widgets.label('', wrap=True)
        box.pack_start(self.summary, False, False, 0)
        self.install_button = widgets.button(_("Preview selected applications"), self._on_install, 'suggested-action')
        box.pack_start(self.install_button, False, False, 0)
        self.reload_button = widgets.button(_("Re-analyse"), self.refresh)
        box.pack_start(self.reload_button, False, False, 0)
        self._build_selection_transfer(box)
        if not widgets.escalation_available(ctx.runner):
            box.pack_start(widgets.info_bar(_("Administrator authorization is unavailable: package state can be read, but installation is disabled.")), False, False, 0)
        for app in backend.CATALOG:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            check = Gtk.CheckButton(label=app.name)
            check.connect('toggled', lambda _check: self._controls())
            self.checks[app.id] = check
            row.pack_start(check, False, False, 0)
            row.pack_start(widgets.label(_(app.category) + ' · ' + app.package, dim=True, wrap=True), False, False, 0)
            if app.description:
                row.pack_start(widgets.label(_(app.description), wrap=True), False, False, 0)
            label = widgets.label(_("Not analysed yet."), wrap=True)
            self.labels[app.id] = label
            row.pack_start(label, False, False, 0)
            information = InstallationDetails(details.installation_rows(app))
            self.details[app.id] = information
            row.pack_start(information, False, False, 0)
            if app.package in fonts.RECIPES:
                button = widgets.button(_("Get this font from GitHub…"), lambda key=app.id: self._on_font(key))
                self.font_buttons[app.id] = button
                row.pack_start(button, False, False, 0)
            box.pack_start(row, False, False, 0)
            row.show_all()
            row.set_no_show_all(True)
            self.rows[app.id] = row
        self.pack_start(widgets.scrolled(box), True, True, 0)
        self._controls()

    def _selected(self):
        return [key for key, check in self.checks.items() if check.get_active()
                and key in self.status and self.status[key].installable]

    def _filter(self):
        query = self.search.get_text().strip().casefold()
        for app in backend.CATALOG:
            text = ' '.join((app.name, app.package, _(app.category), _(app.description))).casefold()
            self.rows[app.id].set_visible(not query or query in text)

    def _controls(self):
        self._transfer_controls()
        ready = not self._loading and not self._busy and not self.ctx.runner.dry_run
        allowed = ready and widgets.escalation_available(self.ctx.runner)
        for key, check in self.checks.items():
            check.set_sensitive(bool(allowed and key in self.status and self.status[key].installable))
        for key, button in self.font_buttons.items():
            button.set_sensitive(bool(ready and key in self.status and self.status[key].github_available))
        self.install_button.set_sensitive(bool(allowed and self._selected()))
        self.reload_button.set_sensitive(not self._loading and not self._busy)
        self.summary.set_text(_("{total} application(s) in your list · {selected} selected.").format(total=len(self.checks), selected=len(self._selected())))
        self.empty.set_no_show_all(bool(self.checks))
        self.empty.set_visible(not self.checks)

    def refresh(self):
        if self._loading or self._busy:
            return
        self._loading = True
        self._controls()
        self.ctx.run_async(lambda: backend.collect_status(self.ctx.runner), on_done=self._apply_status, on_error=self._failed)

    def _apply_status(self, status):
        self.status = status
        self._loading = False
        for app in backend.CATALOG:
            entry = status[app.id]
            if entry.error:
                text = _("Unavailable from official repositories: {error}").format(error=entry.error)
            elif entry.github_installed:
                text = _("Font installed for your user account from GitHub: {version}").format(version=entry.installed_version)
            elif entry.github_available:
                text = _("No official APT candidate. This font can be retrieved from its upstream GitHub source.")
            elif entry.installed:
                text = _("APT package installed: {version}").format(version=entry.installed_version)
            else:
                text = _("Available from official repositories: {version}").format(version=entry.candidate)
            if entry.package != app.package:
                text += '\n' + _("APT package used: {package}").format(package=entry.package)
            self.labels[app.id].set_text(text)
            self.details[app.id].update(details.installation_rows(app, entry))
            if not entry.installable:
                self.checks[app.id].set_active(False)
        self._controls()
        self._filter()

    def _on_install(self):
        if self._loading or self._busy or self.ctx.runner.dry_run:
            return
        ids = self._selected()
        if not ids:
            return
        self._busy = True
        self._controls()
        self.ctx.run_async(lambda: backend.preview_install(self.ctx.runner, ids), on_done=self._confirm_install, on_error=self._failed)

    def _confirm_install(self, plan):
        apps = backend.catalog()
        lines = [apps[key].name + ' — ' + spec for key, spec in zip(plan.ids, plan.specs)]
        for request, origins in plan.sources:
            lines += ['', request, *origins]
        lines += ['', *plan.output.splitlines()]
        if not widgets.confirm_list(self.window, _("Install these applications?"), lines,
                                    _("Review all packages, dependencies and official sources. Removals are refused. The plan is checked again before installation; repositories are not changed.")):
            self._busy = False
            self._controls()
            return
        self.run_operation(lambda: backend.install(self.ctx.runner, plan, self.ctx.log), on_done=self._after_install,
                           on_error=self._failed, name=_("Install applications"))

    def _after_install(self, outcome):
        self._busy = False
        detail = outcome.message
        if not outcome.ok:
            if outcome.result:
                detail += '\n' + outcome.result.output
            detail += '\n' + '\n'.join(key + ': ' + error for key, error in outcome.states.items())
            self.error(_("Application installation was not fully verified."), detail)
        self.ctx.log(detail, 'ok' if outcome.ok else 'error')
        self.refresh()

    def _failed(self, exc):
        self._busy = self._loading = False
        self._controls()
        self.error(_("The application operation failed."), str(exc))

    def _on_font(self, key):
        if self._loading or self._busy or self.ctx.runner.dry_run or key not in self.status or not self.status[key].github_available:
            return
        app = backend.catalog()[key]
        self._busy = True
        self._controls()
        def work():
            if not backend.collect_status(self.ctx.runner)[key].github_available:
                raise ValueError(_("The font availability changed. Re-analyse before continuing."))
            return fonts.preview(app.package)
        self.ctx.run_async(work, on_done=lambda plan: self._confirm_font(key, plan), on_error=self._failed)

    def _confirm_font(self, key, plan):
        lines = [*plan.versions, '', str(plan.target),
                 _("Download size: {size:.1f} MiB").format(size=plan.size / fonts.MIB)]
        lines += [item.url for item in plan.downloads]
        if not widgets.confirm_list(self.window, _("Download and install this GitHub font?"), lines,
                                    _("The official APT package is unavailable. Download font files from the listed upstream repositories into your user account. No repository scripts are executed and existing fonts are preserved.")):
            self._busy = False
            self._controls()
            return
        def work():
            if not backend.collect_status(self.ctx.runner)[key].github_available:
                raise ValueError(_("The font availability changed. Re-analyse before continuing."))
            return fonts.install(self.ctx.runner, plan, self.ctx.log)
        self.run_operation(work, on_done=self._font_installed, on_error=self._failed, name=_("Install GitHub fonts"))

    def _font_installed(self, message):
        self._busy = False
        self.ctx.log(message, 'ok')
        self.refresh()
