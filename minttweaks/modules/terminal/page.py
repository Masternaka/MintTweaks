"""Install tools, change the login shell, and manage isolated terminal profiles."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import backend, integrations  # noqa: E402
from . import configuration, status  # noqa: E402
from .controls import TerminalControls  # noqa: E402
from ...core import paths, userfiles  # noqa: E402
from ...i18n import _  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import Page  # noqa: E402


class TerminalPage(TerminalControls, Page):
    page_name = "terminal"
    page_title = _("Shells and terminals")
    page_icon = "utilities-terminal-symbolic"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.state = backend.TerminalState()
        self.inspection = {}
        self.preferences = {'schema_version': 1, 'shells': {}}
        self._busy = False
        self.checks, self.labels, self.actions = {}, {}, []
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.pack_start(self.notebook, True, True, 0)
        self._build_install()
        self._build_shell()
        self._build_prompt()
        self._build_profiles()
        self._build_settings()
        self._build_aliases()
        self._build_transfer()
        self._build_recovery()
        self.search_entry.connect('search-changed', self._filter_catalog)
        self.catalog_filter.connect('changed', self._filter_catalog)
        self.install_shell.connect('changed', self._filter_catalog)
        self.prompt_shell.connect('changed', self._update_integration_status)
        self.options_shell.connect('changed', self._load_settings)
        self.alias_shell.connect('changed', self._load_aliases)
        self._controls()

    def _tab(self, title, detail):
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_border_width(18)
        body.pack_start(widgets.label(detail, wrap=True), False, False, 0)
        self.notebook.append_page(widgets.scrolled(body), Gtk.Label(label=title))
        return body

    def _action(self, body, label, callback):
        button = widgets.button(label, callback)
        self.actions.append(button)
        body.pack_start(button, False, False, 0)
        return button

    def _build_install(self):
        body = self._tab(_("Utilities and installation"), _("Choose tools and a target shell. After package installation, review and confirm their supported integrations and configuration backups."))
        self.configure_after_install = Gtk.CheckButton(label=_("Configure supported integrations after installation"))
        self.configure_after_install.set_active(True)
        body.pack_start(self.configure_after_install, False, False, 0)
        self.install_shell = Gtk.ComboBoxText()
        for shell in backend.SHELLS:
            self.install_shell.append(shell, shell.capitalize())
        self.install_shell.set_active(0)
        body.pack_start(widgets.row(widgets.label(_("Target shell")), self.install_shell), False, False, 0)
        self._action(body, _("Select starter tools"), lambda: self._select_starter(True))
        self._action(body, _("Clear selection"), lambda: self._select_starter(False))
        self.install_button = self._action(body, _("Preview tool installation"), self._install)
        self.selection_label = widgets.label(_("No tools selected."), wrap=True)
        body.pack_start(self.selection_label, False, False, 0)
        self._action(body, _("Re-analyse"), self.refresh)
        self._build_filters(body)
        self.catalog_rows, self.catalog_status, self.category_headings = {}, {}, {}
        for category, title in backend.CATEGORIES:
            heading = widgets.title(title)
            body.pack_start(heading, False, False, 0)
            self.category_headings[category] = heading
            for entry in backend.CATALOG:
                if entry.category != category:
                    continue
                check = Gtk.CheckButton(label=entry.name)
                check.connect("toggled", lambda _check: self._controls())
                self.checks[entry.id] = check
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
                body.pack_start(row, False, False, 0)
                self.catalog_rows[entry.id] = row
                row.pack_start(check, False, False, 0)
                row.pack_start(widgets.label(_(entry.description), wrap=True), False, False, 0)
                detail = _("APT package: {package}").format(package=entry.package)
                if entry.example:
                    detail += " · " + _("Example: {command}").format(command=entry.example)
                row.pack_start(widgets.label(detail, selectable=True, wrap=True), False, False, 0)
                self.labels[entry.id] = widgets.label(_("Not analysed yet."), wrap=True)
                row.pack_start(self.labels[entry.id], False, False, 0)
                self.catalog_status[entry.id] = widgets.label('', wrap=True)
                row.pack_start(self.catalog_status[entry.id], False, False, 0)
                row.pack_start(Gtk.LinkButton.new_with_label(entry.website, _("Project documentation")), False, False, 0)
                row.show_all()
                row.set_no_show_all(True)

    def _select_starter(self, enabled):
        if self._busy or self.ctx.runner.dry_run:
            return
        for entry in backend.CATALOG:
            state = self.state.tools.get(entry.id)
            selectable = bool(state and state.candidate and not state.installed and not state.error)
            self.checks[entry.id].set_active(bool(enabled and entry.starter and selectable))
        self._controls()

    def _build_shell(self):
        body = self._tab(_("Login shell"), _("The login shell is separate from the terminal application. A change affects future login sessions; your current terminals stay open."))
        self.account_label = widgets.label(_("Not analysed yet."), wrap=True)
        body.pack_start(self.account_label, False, False, 0)
        self.shell_combo = Gtk.ComboBoxText()
        body.pack_start(self.shell_combo, False, False, 0)
        self.shell_button = self._action(body, _("Preview login shell change"), self._shell)
        self.restore_shell_button = self._action(body, _("Restore the previous login shell"), self._restore_shell)

    def _build_prompt(self):
        body = self._tab(_("Shell integrations"), _("Enable or remove managed integrations for installed tools. Startup files are backed up; aliases and settings outside managed blocks are preserved. No shell file is executed by MintTweaks."))
        self.prompt_shell = Gtk.ComboBoxText()
        for shell in backend.SHELLS:
            self.prompt_shell.append(shell, shell.capitalize())
        self.prompt_shell.set_active(0)
        body.pack_start(self.prompt_shell, False, False, 0)
        self._action(body, _("Preview Starship activation"), lambda: self._prompt(True))
        self._action(body, _("Preview managed prompt removal"), lambda: self._prompt(False))
        self.integration_checks = {}
        self.integration_status_labels = {}
        for tool in integrations.INTEGRATIONS:
            check = Gtk.CheckButton(label=backend.TOOL_BY_ID[tool].name)
            self.integration_checks[tool] = check
            body.pack_start(check, False, False, 0)
            label = widgets.label(_('Not analysed yet.'), wrap=True)
            self.integration_status_labels[tool] = label
            body.pack_start(label, False, False, 0)
        self._action(body, _("Preview selected integrations"), lambda: self._integrate(True))
        self._action(body, _("Preview integration removal"), lambda: self._integrate(False))

    def _build_profiles(self):
        body = self._tab(_("Terminal appearance"), _("Create a separate Kitty or Alacritty profile and a MintTweaks menu entry. Your normal terminal configuration and system default terminal are not replaced."))
        self.terminal_combo = Gtk.ComboBoxText()
        for terminal in backend.TERMINALS:
            self.terminal_combo.append(terminal, terminal.capitalize())
        self.terminal_combo.set_active(0)
        body.pack_start(self.terminal_combo, False, False, 0)
        self.palette_combo = Gtk.ComboBoxText()
        self.palette_combo.append("dark", _("Dark"))
        self.palette_combo.append("light", _("Light"))
        self.palette_combo.set_active(0)
        body.pack_start(self.palette_combo, False, False, 0)
        self.font_combo = Gtk.ComboBoxText()
        self.font_combo.append("monospace", "monospace")
        self.font_combo.set_active(0)
        body.pack_start(self.font_combo, False, False, 0)
        self.font_size = Gtk.SpinButton.new_with_range(8, 32, 1)
        self.font_size.set_value(12)
        body.pack_start(widgets.row(widgets.label(_("Font size")), self.font_size), False, False, 0)
        self._action(body, _("Preview terminal profile"), self._profile)
        body.pack_start(widgets.label(_("Launch the generated Kitty — MintTweaks or Alacritty — MintTweaks entry from the Mint menu to use this profile."), wrap=True), False, False, 0)

    def _build_recovery(self):
        body = self._tab(_("Configuration backups"), _("File changes are backed up before writing. Restoring a backup has its own preview and backup. No backup is removed automatically."))
        self.backup_combo = Gtk.ComboBoxText()
        body.pack_start(self.backup_combo, False, False, 0)
        self.backup_label = widgets.label("", wrap=True)
        body.pack_start(self.backup_label, False, False, 0)
        self._action(body, _("Preview configuration restoration"), self._restore_files)

    def _controls(self):
        ready = not self._busy and not self.ctx.runner.dry_run
        for action in self.actions:
            action.set_sensitive(ready)
        for tool, check in self.checks.items():
            value = self.state.tools.get(tool)
            check.set_sensitive(bool(ready and value and value.candidate and not value.installed and not value.error
                                     and widgets.escalation_available(self.ctx.runner)))
        selected = self._selected()
        self.selection_label.set_text(_("{count} tool(s) selected. Preview before installing.").format(count=len(selected)))
        self.install_button.set_sensitive(bool(ready and selected and widgets.escalation_available(self.ctx.runner)))
        self.shell_button.set_sensitive(bool(ready and self.state.shells and self.state.account and widgets.escalation_available(self.ctx.runner)))
        self.restore_shell_button.set_sensitive(bool(ready and self.state.account and widgets.escalation_available(self.ctx.runner)))

    def _selected(self):
        return [tool for tool in backend.TOOLS if self.checks[tool].get_active() and tool in self.state.tools
                and self.state.tools[tool].candidate and not self.state.tools[tool].installed and not self.state.tools[tool].error]

    def _start(self, work, on_done, on_error=None):
        if self._busy:
            return
        self._busy = True
        self._controls()
        self.ctx.run_async(work, on_done=on_done, on_error=on_error or self._failed)

    def refresh(self):
        self._start(backend_work(self.ctx.runner), self._apply_state)

    def _apply_state(self, payload):
        self.state, backups, self.inspection, self.preferences, preference_error = payload
        self._busy = False
        for tool, state in self.state.tools.items():
            text = state.error or (_("Detected: {version}").format(version=state.version or state.binary) if state.installed
                                   else _("APT candidate: {version}").format(version=state.candidate))
            self.labels[tool].set_text(text)
            if state.installed or state.error:
                self.checks[tool].set_active(False)
        self.account_label.set_text(self.state.error or " → ".join(self.state.account))
        self.shell_combo.remove_all()
        for value in self.state.shells:
            self.shell_combo.append(value, value)
        if self.state.account:
            self.shell_combo.set_active_id(self.state.account[1])
        self.font_combo.remove_all()
        for font in self.state.fonts:
            self.font_combo.append(font, font)
        self.font_combo.set_active_id("monospace")
        self.backup_combo.remove_all()
        for backup in backups:
            self.backup_combo.append(str(backup), backup.name)
        self.backup_combo.set_active(0 if backups else -1)
        self.backup_label.set_text(_("{count} configuration backup(s).").format(count=len(backups)))
        if preference_error:
            self.backup_label.set_text(preference_error)
        self._filter_catalog()
        self._update_integration_status()
        self._load_settings()
        self._load_aliases()
        self._controls()

    def _install(self):
        selected = self._selected()
        shell = self.install_shell.get_active_id() if self.configure_after_install.get_active() else None
        if selected:
            self._start(lambda: backend.preview_install(self.ctx.runner, selected), lambda plan: self._confirm_install(plan, shell))

    def _confirm_install(self, plan, shell=None):
        detail = list(plan.specs) + [""] + plan.output.splitlines()
        if shell:
            detail += ["", _("After installation: a separate configuration preview for {shell}. Cancelling it keeps the installed packages.").format(shell=shell)]
        if not widgets.confirm_list(self.window, _("Install these terminal tools?"), detail,
                                    _("Review all dependencies and upgrades. Removals are refused and the plan is checked again before execution.")):
            return self._release()
        self.run_operation(lambda: backend.install(self.ctx.runner, plan, self.ctx.log),
                           on_done=lambda message: self._installed(message, plan.tools, shell),
                           on_error=self._failed, name=_("Install terminal tools"))

    def _installed(self, message, selected, shell):
        self.ctx.log(message)
        self._release()
        if shell and not self.ctx.runner.dry_run:
            self._start(lambda: integrations.preview(self.ctx.runner, shell, selected), self._confirm_integrations,
                        self._post_install_failed)
        else:
            self.refresh()

    def _post_install_failed(self, exc):
        self._release()
        self.error(_("Packages were installed, but their configuration could not be prepared."), str(exc))
        self.refresh()

    def _integrate(self, enabled):
        selected = [tool for tool, check in self.integration_checks.items() if check.get_active()]
        shell = self.prompt_shell.get_active_id()
        if selected:
            self._start(lambda: integrations.preview(self.ctx.runner, shell, selected, enabled), self._confirm_integrations)

    def _confirm_integrations(self, plan):
        lines = list(plan.notes) + [""] + backend.changes_text(plan.changes, backend.targets())
        if not plan.changes:
            self.info(_("No configuration changes are needed."), "\n".join(plan.notes))
            self._release()
            return self.refresh()
        if not widgets.confirm_list(self.window, _("Apply these shell integrations?"), lines,
                                    _("Packages are already installed. Confirm the startup file changes and private backup, then open a new terminal.")):
            self._release()
            return self.refresh()
        self.run_operation(lambda: integrations.apply(self.ctx.runner, plan), on_done=self._files_done,
                           on_error=self._failed, name=_("Configure shell integrations"))

    def _shell(self):
        path = self.shell_combo.get_active_id()
        if path:
            self._start(lambda: backend.preview_shell(path), self._confirm_shell)

    def _restore_shell(self):
        self._start(backend.restore_shell_plan, self._confirm_shell)

    def _confirm_shell(self, plan):
        if not self.confirm(_("Change your login shell?"), plan.user + ": " + plan.before + " → " + plan.after + "\n" +
                            _("The previous value will be saved. Administrator authorization is required. Start a new login session afterwards.")):
            return self._release()
        self.run_operation(lambda: backend.change_shell(self.ctx.runner, plan), on_done=self._done,
                           on_error=self._failed, name=_("Change login shell"))

    def _prompt(self, enabled):
        shell = self.prompt_shell.get_active_id()
        self._start(lambda: backend.prompt_preview(self.ctx.runner, shell, enabled), self._confirm_files)

    def _profile(self):
        terminal, palette = self.terminal_combo.get_active_id(), self.palette_combo.get_active_id()
        font, size = self.font_combo.get_active_id(), self.font_size.get_value_as_int()
        self._start(lambda: backend.terminal_preview(self.ctx.runner, terminal, palette, font, size), self._confirm_files)

    def _restore_files(self):
        path = self.backup_combo.get_active_id()
        if path:
            self._start(lambda: userfiles.restore_preview(backend.targets(), backend.Path(path)), self._confirm_files)

    def _confirm_files(self, changes):
        if not changes:
            self.info(_("No configuration changes are needed."))
            return self._release()
        if not widgets.confirm_list(self.window, _("Apply these configuration changes?"), backend.changes_text(changes, backend.targets()),
                                    _("Review the full file differences. A private backup is saved before writing; close and reopen your terminal after the change.")):
            return self._release()
        self.run_operation(lambda: userfiles.apply(self.ctx.runner, backend.targets(), changes, paths.TERMINAL_BACKUP_DIR / "files"),
                           on_done=self._files_done, on_error=self._failed, name=_("Update terminal configuration"))

    def _files_done(self, outcome):
        if not outcome.ok:
            detail = "\n".join(key + ": " + value for key, value in outcome.errors.items())
            if outcome.backup:
                detail += "\n" + str(outcome.backup)
            self.error(_("Configuration changes failed. Check recovery details and the saved backup."), detail)
        self._done(_("Simulation: no configuration files changed.") if outcome.simulated else
                   _("Configuration files updated and verified.") if outcome.ok else _("The configuration operation failed."))

    def _release(self):
        self._busy = False
        self._controls()

    def _done(self, message):
        self._release()
        self.ctx.log(message)
        self.refresh()

    def _failed(self, exc):
        self._release()
        self.error(_("The shell or terminal operation failed."), str(exc))


def backend_work(runner):
    def work():
        state = backend.collect_state(runner)
        directory = paths.TERMINAL_BACKUP_DIR / "files"
        try:
            backups = sorted((path for path in directory.iterdir() if path.suffix == ".json"),
                             key=lambda path: path.stat().st_mtime_ns, reverse=True)
        except FileNotFoundError:
            backups = []
        inspection = status.collect(runner, state.tools)
        try:
            preferences, preference_error = configuration.load(), ''
        except Exception as exc:
            preferences, preference_error = {'schema_version': 1, 'shells': {}}, str(exc)
        return state, backups, inspection, preferences, preference_error
    return work
