"""Review portable catalog choices separately from installation actions."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from ...i18n import _
from ...ui import widgets
from . import backend, transfer


def disposition_label(state):
    return {'ready': _("Ready for the APT installation preview"),
            'installed': _("Already installed; kept without reinstallation"),
            'github': _("GitHub font route available; use its separate preview"),
            'unavailable': _("Unavailable or unverified; retained for later review")}[state]


class SelectionTransferControls:
    def _build_selection_transfer(self, container):
        self._transfer_ids = ()
        card, body = widgets.card(_("Transfer an application selection"),
            _("Transfer choices from this catalog as JSON. Versions, repositories, application settings and personal data are not copied. Importing never installs software."))
        self.export_selection_button = widgets.button(_("Choose applications to export…"), self._export_selection)
        self.import_selection_button = widgets.button(_("Import an application selection…"), self._import_selection)
        self.prepare_selection_button = widgets.button(_("Prepare the transferred selection"), self._prepare_transferred)
        for button in (self.export_selection_button, self.import_selection_button, self.prepare_selection_button):
            body.pack_start(button, False, False, 0)
        body.pack_start(widgets.label(_("The transfer list is kept for this session. Save its JSON file to reuse it after reopening MintTweaks."), wrap=True), False, False, 0)
        self.transfer_hint = widgets.label(_("No transfer list loaded."), wrap=True)
        body.pack_start(self.transfer_hint, False, False, 0)
        container.pack_start(card, False, False, 0)

    def _transfer_controls(self):
        ready = not self._loading and not self._busy and not self.ctx.runner.dry_run
        self.export_selection_button.set_sensitive(bool(ready and self.checks))
        self.import_selection_button.set_sensitive(bool(ready and self.checks))
        self.prepare_selection_button.set_sensitive(bool(ready and self._transfer_ids and self.status))

    def _choose_selection_file(self, exporting):
        dialog = Gtk.FileChooserDialog(title=_("Export application selection") if exporting else _("Import application selection"),
            transient_for=self.window, action=Gtk.FileChooserAction.SAVE if exporting else Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Save") if exporting else _("Open"), Gtk.ResponseType.OK)
        if exporting:
            dialog.set_current_name('minttweaks-applications.json')
        filter_ = Gtk.FileFilter()
        filter_.set_name(_("JSON files"))
        filter_.add_pattern('*.json')
        dialog.add_filter(filter_)
        try:
            return dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _choose_export_ids(self):
        dialog = Gtk.Dialog(title=_("Applications to transfer"), transient_for=self.window, modal=True)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Review selection"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.set_default_size(640, 520)
        body = dialog.get_content_area()
        body.set_border_width(12)
        body.set_spacing(8)
        body.pack_start(widgets.label(_("These choices are separate from the installation checkboxes. Installed applications can also be included."), wrap=True), False, False, 0)
        choices = {}
        selected = set(self._selected()) | set(self._transfer_ids)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for key, app in backend.catalog().items():
            check = Gtk.CheckButton(label=app.name + ' — ' + app.package)
            check.set_active(key in selected)
            choices[key] = check
            rows.pack_start(check, False, False, 0)
        def include_detected():
            for key, entry in self.status.items():
                if key in choices and entry.installed and not entry.error:
                    choices[key].set_active(True)
        body.pack_start(widgets.button(_("Add applications detected in the last analysis"), include_detected), False, False, 0)
        body.pack_start(widgets.scrolled(rows, min_height=300), True, True, 0)
        dialog.show_all()
        try:
            return tuple(key for key, check in choices.items() if check.get_active()) if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _cancel_selection_transfer(self):
        self._busy = False
        self._controls()

    def _export_selection(self):
        if self._loading or self._busy or self.ctx.runner.dry_run:
            return
        self._busy = True
        self._controls()
        ids = self._choose_export_ids()
        if ids is None:
            return self._cancel_selection_transfer()
        try:
            plan = transfer.preview_export(ids)
        except ValueError as exc:
            return self._selection_transfer_failed(exc)
        if not widgets.confirm_list(self.window, _("Export this application selection?"), plan.text.splitlines(),
            _("Only catalog references are saved. Packages and versions will be resolved on the destination machine. Existing files are preserved.")):
            return self._cancel_selection_transfer()
        filename = self._choose_selection_file(True)
        if not filename:
            return self._cancel_selection_transfer()
        self.run_operation(lambda: transfer.export(self.ctx.runner, plan, filename),
            on_done=lambda path: self._selection_exported(plan.ids, path),
            on_error=self._selection_transfer_failed, name=_("Export application selection"))

    def _selection_exported(self, ids, path):
        self._busy = False
        if path is not None:
            self._transfer_ids = tuple(ids)
            self.transfer_hint.set_text(_("Application choices exported: {path}. No software was installed.").format(path=path))
        else:
            self.transfer_hint.set_text(_("Simulation: no application selection was exported."))
        self._controls()

    def _import_selection(self):
        if self._loading or self._busy or self.ctx.runner.dry_run:
            return
        filename = self._choose_selection_file(False)
        if not filename:
            return
        self._busy = True
        self._controls()
        def preview():
            plan = transfer.preview_import(self.ctx.runner, filename)
            return plan, backend.collect_status(self.ctx.runner)
        self.ctx.run_async(preview, on_done=self._confirm_selection_import, on_error=self._selection_transfer_failed)

    def _confirm_selection_import(self, payload):
        plan, status = payload
        apps = backend.catalog()
        lines = [apps[key].name + ' — ' + apps[key].package + '\n' + disposition_label(transfer.disposition(status.get(key))) for key in plan.ids]
        if not widgets.confirm_list(self.window, _("Import these application choices?"), lines,
            _("Available APT choices will be added to the current selection. Installed applications are kept. Unavailable choices and GitHub fonts remain in the transfer list. Nothing is installed or downloaded.")):
            return self._cancel_selection_transfer()
        def work():
            ids = transfer.confirm_import(self.ctx.runner, plan)
            return ids, backend.collect_status(self.ctx.runner) if ids else {}
        self.run_operation(work, on_done=self._selection_imported, on_error=self._selection_transfer_failed,
                           name=_("Import application selection"))

    def _selection_imported(self, payload):
        ids, status = payload
        self._busy = False
        if not ids:
            self.transfer_hint.set_text(_("Simulation: no application choices were imported."))
            return self._controls()
        self._transfer_ids = tuple(dict.fromkeys((*self._transfer_ids, *ids)))
        self._apply_status(status)
        self._stage_choices(ids)

    def _prepare_transferred(self):
        if self._loading or self._busy or self.ctx.runner.dry_run or not self.status or not self._transfer_ids:
            return
        self._stage_choices(self._transfer_ids)

    def _stage_choices(self, ids):
        groups = {'ready': [], 'installed': [], 'github': [], 'unavailable': []}
        apps = backend.catalog()
        for key in ids:
            state = transfer.disposition(self.status.get(key))
            groups[state].append(apps[key].name)
            if state == 'ready':
                self.checks[key].set_active(True)
        lines = [_("Choices prepared without installation. Review the APT preview separately; font downloads keep their own confirmation.")]
        for state, names in groups.items():
            if names:
                lines.append(disposition_label(state) + ': ' + ', '.join(names))
        self.transfer_hint.set_text('\n'.join(lines))
        self._controls()

    def _selection_transfer_failed(self, exc):
        self._busy = False
        self._controls()
        self.transfer_hint.set_text(_("Selection transfer failed. Existing installations and the previous transfer list were preserved."))
        self.error(_("Application selection transfer failed."), str(exc))
