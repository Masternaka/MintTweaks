"""Transfer repository references without cloning, activating or restoring files."""
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from ...i18n import _
from ...ui import widgets
from . import backend, transfer


class ReferenceTransferControls:
    def _build_reference_transfer(self, body):
        card, content = widgets.card(_("Transfer dotfiles references"),
            _("Save a GitHub URL, chosen Stow configurations and the dotfiles option. Local paths, configuration files, authentication and backups are excluded."))
        self.export_reference_button = widgets.button(_("Export a dotfiles reference…"), self._export_reference)
        self.import_reference_button = widgets.button(_("Import a dotfiles reference…"), self._import_reference)
        content.pack_start(self.export_reference_button, False, False, 0)
        content.pack_start(self.import_reference_button, False, False, 0)
        content.pack_start(widgets.label(_("Reference choices stay in this session. Keep the JSON file to load them again. Cloning and Stow activation keep their own confirmations."), wrap=True), False, False, 0)
        self.reference_hint = widgets.label(_("No dotfiles reference loaded. Enter the GitHub URL and analyse configurations before choosing an export."), wrap=True)
        content.pack_start(self.reference_hint, False, False, 0)
        body.pack_start(card, False, False, 0)

    def _reference_candidates(self):
        retained = self._reference.packages if self._reference is not None else ()
        found = [name for name, package in self._analysed_packages.items() if not package.error]
        return tuple(dict.fromkeys((*retained, *found)))

    def _reference_controls(self):
        ready = not self._busy and not self.ctx.runner.dry_run
        self.export_reference_button.set_sensitive(bool(ready and self._reference_candidates()))
        self.import_reference_button.set_sensitive(ready)

    def _reference_state(self, name):
        package = self._analysed_packages.get(name)
        if package is None:
            return _("Pending analysis or not found")
        if package.error:
            return _("Review the configuration error")
        if package.managed:
            return _("Managed by MintTweaks; review before reuse")
        if package.linked:
            return _("Existing links detected")
        return _("Found in the last analysis")

    def _reference_changed(self):
        if self._reference is not None and not self._updating_reference:
            try:
                url = backend.repository_url(self.url.get_text())
            except ValueError:
                url = None
            if url != self._reference.repository_url:
                self._reference = None
        self._update_reference_hint()

    def _update_reference_hint(self):
        if self._reference is None:
            self.reference_hint.set_text(_("No dotfiles reference loaded. Enter the GitHub URL and analyse configurations before choosing an export."))
        else:
            lines = [self._reference.repository_url]
            lines += [name + ' — ' + self._reference_state(name) for name in self._reference.packages]
            self.reference_hint.set_text('\n'.join(lines))

    def _choose_reference_file(self, exporting):
        dialog = Gtk.FileChooserDialog(title=_("Export dotfiles reference") if exporting else _("Import dotfiles reference"),
            transient_for=self.window, action=Gtk.FileChooserAction.SAVE if exporting else Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Save") if exporting else _("Open"), Gtk.ResponseType.OK)
        if exporting:
            dialog.set_current_name('minttweaks-dotfiles.json')
        filter_ = Gtk.FileFilter()
        filter_.set_name(_("JSON files"))
        filter_.add_pattern('*.json')
        dialog.add_filter(filter_)
        try:
            return dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _choose_reference_packages(self):
        dialog = Gtk.Dialog(title=_("Configurations to reference"), transient_for=self.window, modal=True)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Review selection"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.set_default_size(620, 480)
        body = dialog.get_content_area()
        body.set_border_width(12)
        body.set_spacing(8)
        body.pack_start(widgets.label(_("These checkboxes choose reference names only. They do not activate or undo Stow."), wrap=True), False, False, 0)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        retained = self._reference.packages if self._reference is not None else ()
        choices = {}
        for name in self._reference_candidates():
            check = Gtk.CheckButton(label=name + ' — ' + self._reference_state(name))
            check.set_active(name in retained)
            choices[name] = check
            rows.pack_start(check, False, False, 0)
        def include_managed():
            for name, package in self._analysed_packages.items():
                if name in choices and not package.error and (package.managed or package.linked):
                    choices[name].set_active(True)
        body.pack_start(widgets.button(_("Add managed configurations or detected links"), include_managed), False, False, 0)
        body.pack_start(widgets.scrolled(rows, min_height=260), True, True, 0)
        dialog.show_all()
        try:
            return tuple(name for name, check in choices.items() if check.get_active()) if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _export_reference(self):
        if self._busy or self.ctx.runner.dry_run or not self._reference_candidates():
            return
        self._busy = True
        self._controls()
        packages = self._choose_reference_packages()
        if packages is None:
            return self._release()
        try:
            plan = transfer.preview_export(self.url.get_text(), packages, self.dotfiles.get_active())
        except ValueError as exc:
            return self._reference_failed(exc)
        if not widgets.confirm_list(self.window, _("Export this dotfiles reference?"), plan.text.splitlines(),
            _("Only the displayed reference is saved. Configuration contents, local paths, Git credentials and backups remain on this machine. Existing files are preserved.")):
            return self._release()
        filename = self._choose_reference_file(True)
        if not filename:
            return self._release()
        self.run_operation(lambda: transfer.export(self.ctx.runner, plan, filename),
            on_done=lambda path: self._reference_exported(plan.reference, path),
            on_error=self._reference_failed, name=_("Export dotfiles reference"))

    def _reference_exported(self, ref, path):
        if path is not None:
            self._reference = ref
        self._release()
        self._update_reference_hint()
        self.ctx.log(_("Dotfiles reference exported: {path}").format(path=path) if path is not None else
                     _("Simulation: no dotfiles reference was exported."))

    def _import_reference(self):
        if self._busy or self.ctx.runner.dry_run:
            return
        filename = self._choose_reference_file(False)
        if not filename:
            return
        self._busy = True
        self._controls()
        self.ctx.run_async(lambda: transfer.preview_import(self.ctx.runner, filename),
                           on_done=self._prepare_reference_paths, on_error=self._reference_failed)

    def _choose_reference_paths(self, ref):
        dialog = Gtk.Dialog(title=_("Choose local paths for this reference"), transient_for=self.window, modal=True)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Review selection"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.set_default_size(680, 420)
        body = dialog.get_content_area()
        body.set_border_width(12)
        body.set_spacing(8)
        body.pack_start(widgets.label(ref.repository_url, wrap=True, selectable=True), False, False, 0)
        body.pack_start(widgets.label(_("Choose a new clone destination or an existing local configuration directory, and an existing link target. Import creates no directory and does not verify an existing folder's GitHub origin."), wrap=True), False, False, 0)
        slug = ref.repository_url.rsplit('/', 1)[-1].removesuffix('.git')
        repository, target = Gtk.Entry(), Gtk.Entry()
        repository.set_text(str(Path.home() / slug))
        target.set_text(str(Path.home()))
        body.pack_start(widgets.label(_("Local dotfiles directory")), False, False, 0)
        body.pack_start(repository, False, False, 0)
        def parent_folder():
            folder = self._folder()
            if folder:
                repository.set_text(str(Path(folder) / slug))
        def existing_folder(entry):
            folder = self._folder()
            if folder:
                entry.set_text(folder)
        body.pack_start(widgets.button(_("Choose the parent folder for cloning…"), parent_folder), False, False, 0)
        body.pack_start(widgets.button(_("Open an existing dotfiles directory…"), lambda: existing_folder(repository)), False, False, 0)
        body.pack_start(widgets.label(_("Link target directory")), False, False, 0)
        body.pack_start(target, False, False, 0)
        body.pack_start(widgets.button(_("Choose the link target…"), lambda: existing_folder(target)), False, False, 0)
        dialog.show_all()
        try:
            return (repository.get_text(), target.get_text()) if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _prepare_reference_paths(self, plan):
        paths = self._choose_reference_paths(plan.reference)
        if paths is None:
            return self._release()
        self.ctx.run_async(lambda: transfer.prepare_import(self.ctx.runner, plan, *paths),
                           on_done=self._confirm_reference_import, on_error=self._reference_failed)

    def _confirm_reference_import(self, prepared):
        if prepared is None:
            return self._release()
        ref = prepared.plan.reference
        lines = [ref.repository_url, _("Configurations: {names}").format(names=', '.join(ref.packages)),
                 _("Convert dot- names: {enabled}").format(enabled=_("Yes") if ref.dotfiles else _("No")),
                 _("Local repository: {path}").format(path=prepared.repository),
                 _("Link target: {path}").format(path=prepared.target)]
        if not widgets.confirm_list(self.window, _("Prepare this dotfiles reference?"), lines,
            _("Only the form fields and reference names are prepared. Clone, analyse and activate configurations through their separate actions. Existing links, files and backups are preserved.")):
            return self._release()
        self.run_operation(lambda: transfer.confirm_import(self.ctx.runner, prepared),
            on_done=self._reference_imported, on_error=self._reference_failed, name=_("Import dotfiles reference"))

    def _reference_imported(self, prepared):
        if prepared is None:
            return self._release()
        ref = prepared.plan.reference
        self._updating_reference = True
        try:
            self.url.set_text(ref.repository_url)
            self.repository.set_text(str(prepared.repository))
            self.target.set_text(str(prepared.target))
            self.dotfiles.set_active(ref.dotfiles)
            self._reference = ref
            self._invalidate()
        finally:
            self._updating_reference = False
            self._release()
        self._update_reference_hint()
        self.ctx.log(_("Dotfiles reference prepared. Review the local layout, then clone or analyse explicitly; no link was created."))

    def _reference_failed(self, exc):
        self._release()
        self.error(_("Dotfiles reference transfer failed."), str(exc))
