"""GTK dotfiles page: prepare, review, then link one configuration."""

from pathlib import Path
import shutil

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from . import backend, deployments
from ...i18n import _
from ...ui import widgets
from ...ui.widgets import Page


class DotfilesPage(Page):
    page_name = "dotfiles"
    page_title = _("Dotfiles")
    page_icon = "folder-symbolic"

    def __init__(self, ctx):
        super().__init__(ctx)
        self._busy = False
        self.actions = []
        self.package_buttons = []
        self.inputs = []
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_border_width(18)
        self.pack_start(widgets.scrolled(body), True, True, 0)
        body.pack_start(widgets.title(_("Dotfiles")), False, False, 0)
        body.pack_start(widgets.label(_("Clone your GitHub repository, then activate each configuration. Existing files are backed up before Stow; Undo Stow restores them."), wrap=True), False, False, 0)
        self.tools_label = widgets.label("", wrap=True)
        body.pack_start(self.tools_label, False, False, 0)
        self.install_button = self._action(body, _("Install Git and Stow"), self._install)
        self.url = self._entry(body, _("GitHub repository URL"), "")
        self.url.set_placeholder_text("https://github.com/user/dotfiles.git")
        self.repository = self._entry(body, _("Local dotfiles directory"), str(Path.home() / "dotfiles"))
        self._action(body, _("Choose the parent folder for cloning…"), self._choose_clone_parent)
        self._action(body, _("Clone repository"), self._clone)
        self._action(body, _("Open an existing dotfiles directory…"), lambda: self._choose(self.repository))
        self.target = self._entry(body, _("Link target directory"), str(Path.home()))
        self._action(body, _("Choose the link target…"), lambda: self._choose(self.target))
        self.dotfiles = Gtk.CheckButton(label=_("Convert dot- names to hidden files (--dotfiles)"))
        self.dotfiles.connect("toggled", self._invalidate)
        self.inputs.append(self.dotfiles)
        body.pack_start(self.dotfiles, False, False, 0)
        body.pack_start(widgets.label(_("Expected layout: bash/.bashrc or kitty/.config/kitty/kitty.conf. If packages are in a stow/ subdirectory, open that directory. Repository scripts are never executed."), wrap=True), False, False, 0)
        self._action(body, _("Analyse configurations"), self.refresh)
        self.summary = widgets.label(_("Not analysed yet."), wrap=True)
        body.pack_start(self.summary, False, False, 0)
        self.packages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.pack_start(self.packages_box, False, False, 0)
        self._controls()

    def _entry(self, body, title, value):
        body.pack_start(widgets.label(title), False, False, 0)
        entry = Gtk.Entry()
        entry.set_text(value)
        entry.connect("changed", self._invalidate)
        body.pack_start(entry, False, False, 0)
        self.inputs.append(entry)
        return entry

    def _action(self, body, title, callback):
        button = widgets.button(title, callback)
        self.actions.append(button)
        body.pack_start(button, False, False, 0)
        return button

    def _folder(self):
        dialog = Gtk.FileChooserDialog(title=_("Choose a directory"), transient_for=self.window,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        try:
            return dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _choose(self, entry):
        path = self._folder()
        if path:
            entry.set_text(path)

    def _choose_clone_parent(self):
        parent = self._folder()
        if parent:
            name = self.url.get_text().strip().rstrip("/").split("/")[-1].removesuffix(".git") or "dotfiles"
            self.repository.set_text(str(Path(parent) / name))

    def _invalidate(self, *_args):
        if not hasattr(self, "packages_box"):
            return
        for child in self.packages_box.get_children():
            self.packages_box.remove(child)
        self.package_buttons = []
        self.summary.set_text(_("Analyse again after changing the repository or target."))

    def _controls(self):
        ready = not self._busy and not self.ctx.runner.dry_run
        for widget in self.actions + self.inputs:
            widget.set_sensitive(ready)
        for button, allowed, needs_stow in self.package_buttons:
            button.set_sensitive(ready and allowed and (not needs_stow or bool(shutil.which("stow"))))
        self.install_button.set_sensitive(ready and widgets.escalation_available(self.ctx.runner))
        self.tools_label.set_text(_("Git: {git} · Stow: {stow}").format(
            git=_("Available") if shutil.which("git") else _("Missing"),
            stow=_("Available") if shutil.which("stow") else _("Missing")))

    def _start(self, work, done, mutation=False):
        if self._busy or self.ctx.runner.dry_run:
            return
        self._busy = True
        self._controls()
        if mutation:
            self.run_operation(work, on_done=done, on_error=self._failed, name=_("Dotfiles"))
        else:
            self.ctx.run_async(work, on_done=done, on_error=self._failed)

    def _release(self):
        self._busy = False
        self._controls()

    def _failed(self, exc):
        self._release()
        self.error(_("The dotfiles operation failed."), str(exc))

    def _done(self, message):
        self._release()
        self.ctx.log(message)
        if Path(self.repository.get_text()).expanduser().is_dir():
            self.refresh()

    def refresh(self):
        repository, target, dotfiles = self.repository.get_text(), self.target.get_text(), self.dotfiles.get_active()
        self._invalidate()
        if not Path(repository).expanduser().is_dir():
            self.summary.set_text(_("Clone a repository or open an existing dotfiles directory to begin."))
            self._controls()
            return
        self._start(lambda: backend.analyse(repository, target, dotfiles), self._show_packages)

    def _show_packages(self, packages):
        self._release()
        self.summary.set_text(_("{count} configuration(s) found.").format(count=len(packages)))
        for package in packages:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            row.pack_start(widgets.title(package.name), False, False, 0)
            row.pack_start(widgets.label(_("{files} file(s), {linked} existing link(s).").format(files=package.files, linked=package.linked), wrap=True), False, False, 0)
            if package.error:
                row.pack_start(widgets.label(package.error, selectable=True, wrap=True), False, False, 0)
            if package.conflicts:
                row.pack_start(widgets.label(_("Existing configuration: {count} path(s) to review for backup.").format(count=len(package.conflicts)), wrap=True), False, False, 0)
            if package.managed:
                row.pack_start(widgets.label(_("Managed by MintTweaks. Its backup is kept for undo."), wrap=True), False, False, 0)
            button = widgets.button(_("Stow"), lambda name=package.name: self._stow(name))
            row.pack_start(button, False, False, 0)
            self.package_buttons.append((button, not package.error and not package.managed, True))
            undo = widgets.button(_("Undo Stow"), lambda name=package.name: self._undo(name))
            row.pack_start(undo, False, False, 0)
            self.package_buttons.append((undo, bool(package.managed or package.linked), False))
            self.packages_box.pack_start(row, False, False, 0)
        self.packages_box.show_all()
        self._controls()

    def _clone(self):
        url, destination = self.url.get_text(), self.repository.get_text()
        try:
            command = backend.clone_command(url, destination)
        except ValueError as exc:
            return self._failed(exc)
        if self.confirm(_("Clone this repository?"), str(command)):
            self._start(lambda: backend.clone(self.ctx.runner, url, destination, self.ctx.log), self._done, mutation=True)

    def _install(self):
        self._start(lambda: backend.preview_dependencies(self.ctx.runner), self._confirm_install)

    def _confirm_install(self, plan):
        self._release()
        if widgets.confirm_list(self.window, _("Install Git and Stow?"), plan.output.splitlines(),
                                _("Review the APT plan. Administrator authorization is required.")):
            self._start(lambda: backend.install_dependencies(self.ctx.runner, plan, self.ctx.log), self._done, mutation=True)

    def _stow(self, name):
        repository, target, dotfiles = self.repository.get_text(), self.target.get_text(), self.dotfiles.get_active()
        self._start(lambda: deployments.preview_activation(self.ctx.runner, repository, target, name, dotfiles), self._confirm_stow)

    def _confirm_stow(self, plan):
        self._release()
        lines = [str(backend.stow_command(plan.root, plan.target, plan.name, plan.dotfiles, simulate=False)), "", plan.output]
        lines += ["", _("Files to back up before activation:")]
        lines += [str(plan.target / path) for path in plan.backups] or [_("No existing files need a backup.")]
        if widgets.confirm_list(self.window, _("Activate this dotfiles configuration?"), lines,
                                _("Review the links and backups. A dated private backup is verified before replacing existing files with links. Undo Stow restores that backup.")):
            self._start(lambda: deployments.activate(self.ctx.runner, plan, self.ctx.log), self._done, mutation=True)

    def _undo(self, name):
        repository, target, dotfiles = self.repository.get_text(), self.target.get_text(), self.dotfiles.get_active()
        self._start(lambda: deployments.preview_undo(repository, target, name, dotfiles), self._confirm_undo)

    def _confirm_undo(self, plan):
        self._release()
        lines = [_("Links to remove:")]
        lines += [str(plan.target / record['relative']) for record in plan.records]
        lines += ["", _("Configurations to restore:")]
        lines += [str(plan.target / record['relative']) for record in plan.records if record['before'] is not None]
        if plan.journal:
            lines += ["", _("Backup: {path}").format(path=plan.journal)]
        if widgets.confirm_list(self.window, _("Undo this Stow configuration?"), lines,
                                _("Only this configuration's links are removed. Saved files are restored, backups and repository files are kept. External changes block restoration.")):
            self._start(lambda: deployments.undo(self.ctx.runner, plan), self._done, mutation=True)
