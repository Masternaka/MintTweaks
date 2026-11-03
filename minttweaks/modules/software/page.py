"""Native third-party browsers, with explicit source and APT plan review."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import backend, details, repository, zen  # noqa: E402
from ...i18n import _  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import Page  # noqa: E402
from ...ui.installations import InstallationDetails  # noqa: E402


class SoftwarePage(Page):
    page_name = "software"
    page_title = _("Native software")
    page_icon = "system-software-install-symbolic"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.status = {}
        self.checks = {}
        self.labels = {}
        self.repository_buttons = {}
        self.details = {}
        self._loading = False
        self._busy = False
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(18)
        if not widgets.escalation_available(self.ctx.runner):
            box.pack_start(widgets.info_bar(_("Administrator authorization is unavailable: APT installation is disabled. Zen can still be installed for the current user.")), False, False, 0)
        repo_card, repo_body = widgets.card(_("Masternaka APT repository"),
            _("Add the signed repository for MintTweaks updates and the packages distributed by Masternaka. No application is installed by this action."))
        repo_body.pack_start(widgets.label(repository.URL, wrap=True, selectable=True), False, False, 0)
        repo_body.pack_start(widgets.label(_("Signing key fingerprint: {fingerprint}").format(
            fingerprint=repository.FINGERPRINT), wrap=True, selectable=True), False, False, 0)
        self.repository_label = widgets.label(_("The source and its public key are added only after confirmation."), wrap=True)
        repo_body.pack_start(self.repository_label, False, False, 0)
        self.repository_button = widgets.button(_("Configure or refresh the Masternaka repository"), self._on_masternaka_repository)
        repo_body.pack_start(self.repository_button, False, False, 0)
        box.pack_start(repo_card, False, False, 0)
        catalog, body = widgets.card(_("Browsers outside Mint's official repositories"),
            _("Helium and Brave use their official APT repositories. Zen uses its official GitHub installer for the current user."))
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
            information = InstallationDetails(details.installation_rows(app))
            self.details[app.id] = information
            body.pack_start(information, False, False, 0)
            button = (widgets.button(_("Install Zen from GitHub…"), self._on_zen)
                      if app.method == "zen" else widgets.button(_("Configure repository and install…"), lambda key=app.id: self._on_repository(key)))
            button.set_sensitive(False)
            self.repository_buttons[app.id] = button
            body.pack_start(button, False, False, 0)
            body.pack_start(Gtk.LinkButton.new_with_label(app.guide, _("Installation instructions")), False, False, 0)
        self.reload_button = widgets.button(_("Re-analyse"), self.refresh)
        body.pack_start(self.reload_button, False, False, 0)
        self.install_button = widgets.button(_("Preview selected installations"), self._on_install, "suggested-action")
        self.install_button.set_sensitive(False)
        body.pack_start(self.install_button, False, False, 0)
        box.pack_start(catalog, False, False, 0)
        self.pack_start(widgets.scrolled(box), True, True, 0)
        self._update_controls()

    def _selected(self):
        return [app.id for app in backend.CATALOG if self.checks[app.id].get_active()
                and app.method == "apt" and app.id in self.status and self.status[app.id].installable]

    def _update_controls(self):
        ready = not self._loading and not self._busy and not self.ctx.runner.dry_run
        allowed = ready and widgets.escalation_available(self.ctx.runner)
        for key, check in self.checks.items():
            if backend.APP_BY_ID[key].method == "zen":
                check.set_sensitive(False)
                self.repository_buttons[key].set_sensitive(bool(ready and key in self.status and self.status[key].installable))
                continue
            check.set_sensitive(bool(allowed and key in self.status and self.status[key].installable))
            self.repository_buttons[key].set_sensitive(bool(allowed and key in backend.RECIPES and key in self.status and not self.status[key].installed and not self.status[key].installable))
        self.install_button.set_sensitive(bool(allowed and self._selected()))
        self.repository_button.set_sensitive(bool(allowed))
        self.reload_button.set_sensitive(not self._loading and not self._busy)

    def _on_masternaka_repository(self):
        if self._loading or self._busy or self.ctx.runner.dry_run:
            return
        lines = [repository.URL, _("Signing key fingerprint: {fingerprint}").format(
            fingerprint=repository.FINGERPRINT), str(repository.KEY_PATH), str(repository.SOURCE_PATH)]
        if not widgets.confirm_list(self.window, _("Add or refresh the Masternaka repository?"), lines,
            _("This third-party source can provide package updates through APT and Mint. "
              "Its bundled public key is checked and restricted to this repository with Signed-By. "
              "Existing different files are refused. If APT refresh fails, newly created files are removed. "
              "Administrator authorization is required; no package is installed or upgraded.")):
            return
        self._busy = True
        self._update_controls()
        self.run_operation(lambda: repository.install(self.ctx.runner, on_line=self.ctx.log),
                           on_done=self._after_repository, on_error=self._failed,
                           name=_("Configure Masternaka repository"))

    def _after_repository(self, result):
        self._busy = False
        if result is None:
            text = _("Simulation: no repository was changed.")
        elif not result.ok:
            self._failed(RuntimeError(result.output))
            return
        else:
            text = _("Masternaka repository configured and APT metadata refreshed. No application was installed.")
        self.repository_label.set_text(text)
        self.ctx.log(text, "ok")
        self.refresh()

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
            elif app.method == "zen":
                text = (_("Zen installed for this user: {version}").format(version=entry.installed_version)
                        if entry.installed else _("Zen is available directly from GitHub. No APT repository is required."))
            elif entry.installed:
                text = _("APT package installed: {version}").format(version=entry.installed_version)
            else:
                text = _("APT package not installed. Candidate from the expected source: {version}").format(version=entry.candidate)
            self.labels[app.id].set_text(text)
            self.details[app.id].update(details.installation_rows(app, entry))
            if not entry.installable:
                self.checks[app.id].set_active(False)
        self._update_controls()

    def _on_zen(self):
        if self._loading or self._busy or self.ctx.runner.dry_run:
            return
        self._busy = True
        self._update_controls()
        self.ctx.run_async(lambda: zen.preview(self.ctx.runner),
                           on_done=self._confirm_zen, on_error=self._failed)

    def _confirm_zen(self, plan):
        lines = [zen.INSTALLER_URL, zen.DOWNLOAD_URL, "SHA-256: " + plan.digest]
        lines.extend(str(path) for path in plan.destinations)
        if not widgets.confirm_list(self.window, _("Install Zen from GitHub?"), lines,
            _("Run Zen's official installer as the current user. It downloads the latest release, creates a launcher and a menu entry. "
              "The installer is downloaded before confirmation; the browser archive is selected when it runs. "
              "Updates are managed by Zen. No administrator authorization is required.")):
            self._busy = False
            self._update_controls()
            return
        self.run_operation(lambda: zen.install(self.ctx.runner, plan, on_line=self.ctx.log),
                           on_done=self._after_install, on_error=self._failed, name=_("Install Zen from GitHub"))

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

    def _on_repository(self, key):
        if self._loading or self._busy or self.ctx.runner.dry_run or not widgets.escalation_available(self.ctx.runner):
            return
        if key not in backend.RECIPES:
            return
        app = backend.APP_BY_ID[key]
        recipe = backend.RECIPES[key]
        detail = _("Add the signing key and APT source shown below, then refresh package metadata. Existing repository files are preserved. An installation preview will follow.")
        detail += "\n\n" + app.source + "\n" + app.origin + "\n" + recipe.key_url
        if not self.confirm(_("Configure the repository for {name}?").format(name=app.name), detail):
            return
        self._busy = True
        self._update_controls()
        self.run_operation(lambda: backend.configure_repository(self.ctx.runner, key, on_line=self.ctx.log),
                           on_done=lambda status: self._repository_ready(key, status),
                           on_error=self._failed, name=_("Configure an APT repository"))

    def _repository_ready(self, key, status):
        self._busy = False
        self._apply_status(status)
        if status[key].installable:
            self.checks[key].set_active(True)
            self._on_install()

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
