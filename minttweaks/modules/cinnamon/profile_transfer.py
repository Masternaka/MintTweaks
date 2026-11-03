"""Previewed JSON import/export controls independent of GSettings availability."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from ...i18n import _
from ...ui import widgets
from . import backend, transfer


class ProfileTransferControls:
    def _build_profile_transfer(self, body):
        self.transfer_hint = widgets.label(_("Transfer a profile as JSON. Only its name, capture date and seven setting values are included; theme and font files stay on the source machine."), wrap=True)
        body.pack_start(self.transfer_hint, False, False, 0)
        self.export_profile_button = widgets.button(_("Export selected profile…"), self._export_profile)
        self.import_profile_button = widgets.button(_("Import profile from JSON…"), self._import_profile)
        body.pack_start(self.export_profile_button, False, False, 0)
        body.pack_start(self.import_profile_button, False, False, 0)
        self._update_transfer_controls()

    def _update_transfer_controls(self):
        ready = not self._loading and not self._saving and not self.ctx.runner.dry_run
        self.export_profile_button.set_sensitive(ready and self.profile_combo.get_active_id() in self.profiles)
        self.import_profile_button.set_sensitive(ready)

    def _choose_profile_file(self, exporting, filename=None):
        dialog = Gtk.FileChooserDialog(title=_("Export Cinnamon profile") if exporting else _("Import Cinnamon profile"),
            transient_for=self.window, action=Gtk.FileChooserAction.SAVE if exporting else Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL,
                           _("Save") if exporting else _("Open"), Gtk.ResponseType.OK)
        if exporting:
            dialog.set_current_name(filename)
        filter_ = Gtk.FileFilter()
        filter_.set_name(_("JSON files"))
        filter_.add_pattern('*.json')
        dialog.add_filter(filter_)
        try:
            return dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _transfer_cancelled(self):
        self._saving = False
        self.transfer_hint.set_text(_("Profile transfer cancelled. No profile was written or applied."))
        self._update_save()

    def _export_profile(self):
        if self._loading or self._saving or self.ctx.runner.dry_run:
            return
        profile = self.profiles.get(self.profile_combo.get_active_id())
        if profile is None:
            return
        self._saving = True
        self._update_save()
        try:
            plan = transfer.preview_export(profile)
        except (ValueError, TypeError) as exc:
            return self._transfer_failed(exc)
        if not widgets.confirm_list(self.window, _("Export this Cinnamon profile?"), plan.text.splitlines(),
            _("The JSON shown below will be saved to a new file. It contains profile values only and does not copy theme, icon or font files. Existing files are preserved.")):
            return self._transfer_cancelled()
        filename = self._choose_profile_file(True, plan.filename)
        if not filename:
            return self._transfer_cancelled()
        self.run_operation(lambda: transfer.export_profile(self.ctx.runner, plan, filename),
            on_done=self._profile_exported, on_error=self._transfer_failed, name=_("Export Cinnamon profile"))

    def _profile_exported(self, path):
        self._saving = False
        message = (_("Cinnamon profile exported: {path}").format(path=path) if path is not None else
                   _("Simulation: no profile was exported."))
        self.transfer_hint.set_text(message)
        self.ctx.log(message, 'ok')
        self._update_save()

    def _import_profile(self):
        if self._loading or self._saving or self.ctx.runner.dry_run:
            return
        filename = self._choose_profile_file(False)
        if not filename:
            return
        self._saving = True
        self._update_save()
        self.ctx.run_async(lambda: transfer.preview_import(self.ctx.runner, filename),
                           on_done=self._confirm_profile_import, on_error=self._transfer_failed)

    def _confirm_profile_import(self, plan):
        profile = plan.profile
        lines = [profile.name, profile.captured_at, str(plan.directory), '']
        lines += [setting.title + ': ' + repr(profile.settings[setting.id]) for setting in backend.SETTINGS]
        if not widgets.confirm_list(self.window, _("Import this Cinnamon profile as a new copy?"), lines,
            _("A new local identifier will be created. Existing profiles, including profiles with the same name, are preserved. Nothing is applied to the desktop. Theme, icon and font files must be installed separately before application.")):
            return self._transfer_cancelled()
        self.run_operation(lambda: transfer.import_profile(self.ctx.runner, plan),
            on_done=self._profile_imported, on_error=self._transfer_failed, name=_("Import Cinnamon profile"))

    def _profile_imported(self, profile):
        self._saving = False
        if profile is None:
            self.transfer_hint.set_text(_("Simulation: no profile was imported."))
            return self._update_save()
        self._imported_profile_id = profile.id
        message = _("Profile imported: {name}. It has not been applied to the desktop.").format(name=profile.name)
        self.transfer_hint.set_text(message)
        self.ctx.log(message, 'ok')
        self.refresh()

    def _transfer_failed(self, exc):
        self._saving = False
        self.transfer_hint.set_text(_("The profile transfer could not be completed. Existing profiles were preserved."))
        self._update_save()
        self.error(_("Cinnamon profile transfer failed."), str(exc))
