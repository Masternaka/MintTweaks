"""Inspect, save, preview, apply and restore appearance profiles."""

from __future__ import annotations

from typing import Dict

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from . import backend  # noqa: E402
from ...i18n import _  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import Page  # noqa: E402


class CinnamonPage(Page):
    page_name = "cinnamon"
    page_title = _("Cinnamon profiles")
    page_icon = "preferences-desktop-theme-symbolic"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.snapshot = None
        self.profiles: Dict[str, backend.Profile] = {}
        self.backups: Dict[str, backend.Profile] = {}
        self._loading = False
        self._saving = False
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_border_width(18)
        self._values = {}
        current, body = widgets.card(_("Current appearance"), _("Read-only values. Missing settings are never replaced with defaults."))
        for setting in backend.SETTINGS:
            value = widgets.label(_("Not analysed yet."), wrap=True, selectable=True)
            self._values[setting.id] = value
            body.pack_start(widgets.row(widgets.label(setting.title), value), False, False, 0)
        body.pack_start(widgets.button(_("Re-analyse"), self.refresh), False, False, 0)
        container.pack_start(current, False, False, 0)

        save, body = widgets.card(_("Save a profile"), _("Only setting values are saved. Theme, icon and font files are not copied."))
        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text(_("Profile name"))
        self.name_entry.set_max_length(80)
        self.name_entry.connect("changed", lambda _entry: self._update_save())
        body.pack_start(self.name_entry, False, False, 0)
        self.save_button = widgets.button(_("Save current appearance"), self._on_save, "suggested-action")
        self.save_button.set_sensitive(False)
        body.pack_start(self.save_button, False, False, 0)
        self.capture_hint = widgets.label(_("Read all settings before saving a profile."), wrap=True)
        body.pack_start(self.capture_hint, False, False, 0)
        container.pack_start(save, False, False, 0)

        saved, body = widgets.card(_("Saved profiles"))
        self.catalog_hint = widgets.label("", wrap=True)
        body.pack_start(self.catalog_hint, False, False, 0)
        self.profile_combo = Gtk.ComboBoxText()
        self.profile_combo.connect("changed", lambda _combo: self._show_profile())
        body.pack_start(self.profile_combo, False, False, 0)
        self.apply_button = widgets.button(_("Preview and apply profile"), lambda: self._on_preview(False))
        self.apply_button.set_sensitive(False)
        body.pack_start(self.apply_button, False, False, 0)
        scroller, _view, self.profile_buffer = widgets.text_view(height=220)
        body.pack_start(scroller, True, True, 0)
        container.pack_start(saved, False, False, 0)

        recovery, body = widgets.card(_("Restore previous appearance"), _("A backup is saved before every change, including restoration."))
        self.backup_hint = widgets.label("", wrap=True)
        body.pack_start(self.backup_hint, False, False, 0)
        self.backup_combo = Gtk.ComboBoxText()
        self.backup_combo.connect("changed", lambda _combo: self._update_actions())
        body.pack_start(self.backup_combo, False, False, 0)
        self.restore_button = widgets.button(_("Preview and restore backup"), lambda: self._on_preview(True))
        self.restore_button.set_sensitive(False)
        body.pack_start(self.restore_button, False, False, 0)
        container.pack_start(recovery, False, False, 0)
        self.pack_start(widgets.scrolled(container), True, True, 0)

    def _update_save(self):
        try:
            backend.validate_name(self.name_entry.get_text())
            valid_name = True
        except backend.ProfileError:
            valid_name = False
        self.save_button.set_sensitive(bool(
            valid_name and self.snapshot is not None and self.snapshot.complete
            and not self._loading and not self._saving and not self.ctx.runner.dry_run
        ))
        self._update_actions()

    def _update_actions(self):
        allowed = bool(self.snapshot is not None and self.snapshot.complete and
                       not self._loading and not self._saving and not self.ctx.runner.dry_run)
        self.apply_button.set_sensitive(allowed and self.profile_combo.get_active_id() in self.profiles)
        self.restore_button.set_sensitive(allowed and self.backup_combo.get_active_id() in self.backups)

    def refresh(self):
        if self._loading or self._saving:
            return
        self._loading = True
        self._update_save()

        def work():
            snapshot = backend.capture(self.ctx.runner)
            def read_catalog(directory=None):
                try:
                    return backend.list_profiles(directory), ""
                except OSError as exc:
                    return None, str(exc)
            catalog, error = read_catalog()
            backups, backup_error = read_catalog(backend.paths.PROFILE_BACKUP_DIR)
            return snapshot, catalog, error, backups, backup_error

        self.ctx.run_async(work, on_done=self._apply_state, on_error=self._failed)

    def _apply_state(self, payload):
        self.snapshot, catalog, catalog_error = payload[:3]
        self._loading = False
        for setting in backend.SETTINGS:
            if setting.id in self.snapshot.values:
                text = self.snapshot.values[setting.id]
                self._values[setting.id].set_text(text if text else _("(empty value)"))
            else:
                self._values[setting.id].set_text(_("Unavailable: {error}").format(error=self.snapshot.errors.get(setting.id, "")))
        self.capture_hint.set_text(
            _("All settings were read. Saving will capture them again.") if self.snapshot.complete
            else _("The settings could not all be read. Refresh before saving a profile.")
        )
        if catalog is None:
            self.catalog_hint.set_text(_("Profiles could not be read. Previous results have not been updated.\n{error}").format(error=catalog_error))
        else:
            self.profiles = {profile.id: profile for profile in catalog.profiles}
            self.profile_combo.remove_all()
            for profile in catalog.profiles:
                self.profile_combo.append(profile.id, profile.name + " — " + profile.captured_at)
            self.catalog_hint.set_text(_("{count} saved profile(s).").format(count=len(self.profiles)))
            if catalog.errors:
                self.catalog_hint.set_text(_("Some profile files could not be read and were preserved:\n{errors}").format(
                    errors="\n".join(name + ": " + error for name, error in catalog.errors.items())
                ))
            self.profile_combo.set_active(0 if self.profiles else -1)
            self._show_profile()
        if len(payload) > 3:
            backups, backup_error = payload[3:]
            if backups is None:
                self.backup_hint.set_text(_("Backups could not be read: {error}").format(error=backup_error))
            else:
                self.backups = {profile.id: profile for profile in backups.profiles}
                self.backup_combo.remove_all()
                for profile in sorted(backups.profiles, key=lambda item: item.captured_at, reverse=True):
                    self.backup_combo.append(profile.id, profile.captured_at + " — " + profile.name)
                self.backup_combo.set_active(0 if self.backups else -1)
                self.backup_hint.set_text(_("{count} appearance backup(s).").format(count=len(self.backups)))
                if backups.errors:
                    self.backup_hint.set_text(_("Some backups could not be read and were preserved:\n{errors}").format(
                        errors="\n".join(name + ": " + error for name, error in backups.errors.items())
                    ))
        self._update_save()

    def _show_profile(self):
        profile = self.profiles.get(self.profile_combo.get_active_id())
        lines = []
        if profile is not None:
            lines = [profile.name, profile.captured_at, ""]
            for setting in backend.SETTINGS:
                value = profile.settings[setting.id]
                lines.append(setting.title + ": " + (value if value else _("(empty value)")))
        self.profile_buffer.set_text("\n".join(lines))
        self._update_actions()

    def _on_preview(self, restoring):
        if self._loading or self._saving or self.ctx.runner.dry_run:
            return
        catalog = self.backups if restoring else self.profiles
        combo = self.backup_combo if restoring else self.profile_combo
        profile = catalog.get(combo.get_active_id())
        if profile is None:
            return
        self._saving = True
        self._update_save()
        self.ctx.run_async(
            lambda: backend.preview_profile(self.ctx.runner, profile),
            on_done=lambda plan: self._confirm_apply(plan, restoring), on_error=self._failed,
        )

    def _confirm_apply(self, plan, restoring):
        if not plan.changes:
            self._saving = False
            self._update_save()
            self.info(_("The selected profile already matches the current appearance."))
            return
        lines = [setting.title + ": " + repr(plan.before.values[setting.id]) + " → " + repr(plan.profile.settings[setting.id])
                 for setting in plan.changes]
        accepted = widgets.confirm_list(
            self.window, _("Restore this appearance?") if restoring else _("Apply this appearance?"), lines,
            _("A backup will be saved before changing these values. The referenced themes and fonts must already be installed. "
              "If settings changed since this preview, the operation will be refused."),
        )
        if not accepted:
            self._saving = False
            self._update_save()
            return
        self.run_operation(
            lambda: backend.apply_profile(self.ctx.runner, plan),
            on_done=self._after_apply, on_error=self._failed,
            name=_("Restore Cinnamon appearance") if restoring else _("Apply Cinnamon profile"),
        )

    def _after_apply(self, outcome):
        self._saving = False
        detail = outcome.message
        if outcome.backup is not None:
            detail += "\n" + _("Backup: {id}").format(id=outcome.backup.id)
        if outcome.rollback_errors:
            detail += "\n" + "\n".join(key + ": " + error for key, error in outcome.rollback_errors.items())
        self.ctx.log(detail, "ok" if outcome.ok else "error")
        if not outcome.ok:
            self.error(_("The Cinnamon profile operation failed."), detail)
        self.refresh()

    def _on_save(self):
        if self._saving or self._loading or self.snapshot is None or not self.snapshot.complete:
            return
        try:
            name = backend.validate_name(self.name_entry.get_text())
        except backend.ProfileError as exc:
            self.error(_("The profile could not be saved."), str(exc))
            return
        self._saving = True
        self._update_save()
        self.run_operation(
            lambda: backend.save_profile(self.ctx.runner, name),
            on_done=self._saved, on_error=self._failed, name=_("Save Cinnamon profile"),
        )

    def _saved(self, profile):
        self._saving = False
        self.name_entry.set_text("")
        self.ctx.log(_("Profile saved: {name}").format(name=profile.name), "ok")
        self.refresh()

    def _failed(self, exc):
        self._loading = False
        self._saving = False
        self.snapshot = None
        self.capture_hint.set_text(_("Refresh before saving another profile."))
        self._update_save()
        self.error(_("The Cinnamon profile operation failed."), str(exc))
