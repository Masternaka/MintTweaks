"""Catppuccin installation controls alongside existing Cinnamon profiles."""
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from . import themes
from ...i18n import _
from ...ui import widgets


class ThemeControls:
    def _build_themes(self, container):
        card, body = widgets.card(_("Catppuccin for Cinnamon"),
                                  _("Clone your theme repository, install a variant, then apply it to the desktop. Git is required for cloning."))
        body.pack_start(Gtk.LinkButton.new_with_label('https://github.com/Masternaka/Cinnamon_Catppuccin',
                                                      _("View the theme repository")), False, False, 0)
        body.pack_start(widgets.label(_("Local theme repository")), False, False, 0)
        self.theme_repository = Gtk.Entry()
        self.theme_repository.set_text(str(Path.home() / 'Cinnamon_Catppuccin'))
        body.pack_start(self.theme_repository, False, False, 0)
        self.theme_buttons = []
        for title, callback in ((_("Choose the clone parent folder…"), self._choose_theme_parent),
                                (_("Open an existing theme repository…"), self._choose_theme_repository),
                                (_("Clone Catppuccin repository"), self._clone_theme)):
            button = widgets.button(title, callback)
            self.theme_buttons.append(button)
            body.pack_start(button, False, False, 0)
        self.theme_variant = Gtk.ComboBoxText()
        for variant in themes.VARIANTS:
            self.theme_variant.append(variant, 'Frappé' if variant == 'Frappe' else variant)
        self.theme_variant.set_active_id('Mocha')
        body.pack_start(widgets.row(widgets.label(_("Catppuccin variant")), self.theme_variant), False, False, 0)
        for title, callback in ((_("Preview theme installation"), self._install_theme),
                                (_("Apply variant to the desktop"), self._apply_theme)):
            button = widgets.button(title, callback)
            self.theme_buttons.append(button)
            body.pack_start(button, False, False, 0)
        body.pack_start(widgets.label(_("Themes are copied into ~/.themes. Existing versions are backed up. Applying changes only the Cinnamon desktop theme; application themes, icons and fonts are preserved."), wrap=True), False, False, 0)
        container.pack_start(card, False, False, 0)

    def _update_theme_controls(self):
        ready = not self._saving and not self._loading and not self.ctx.runner.dry_run
        for widget in self.theme_buttons + [self.theme_repository, self.theme_variant]:
            widget.set_sensitive(ready)

    def _theme_folder(self):
        dialog = Gtk.FileChooserDialog(title=_("Choose a directory"), transient_for=self.window,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        try:
            return dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _choose_theme_parent(self):
        folder = self._theme_folder()
        if folder:
            self.theme_repository.set_text(str(Path(folder) / 'Cinnamon_Catppuccin'))

    def _choose_theme_repository(self):
        folder = self._theme_folder()
        if folder:
            self.theme_repository.set_text(folder)

    def _theme_start(self, work, on_done, mutation=False):
        if self._saving or self._loading or self.ctx.runner.dry_run:
            return
        self._saving = True
        self._update_save()
        if mutation:
            self.run_operation(work, on_done=on_done, on_error=self._theme_failed, name=_("Install Catppuccin theme"))
        else:
            self.ctx.run_async(work, on_done=on_done, on_error=self._theme_failed)

    def _theme_release(self):
        self._saving = False
        self._update_save()

    def _theme_failed(self, exc):
        self._theme_release()
        self.error(_("The Catppuccin theme operation failed."), str(exc))

    def _theme_done(self, message):
        self._theme_release()
        self.ctx.log(message, 'ok')
        self.refresh()

    def _clone_theme(self):
        destination = self.theme_repository.get_text()
        try:
            command = themes.clone_command(destination)
        except ValueError as exc:
            return self._theme_failed(exc)
        if self.confirm(_("Clone the Catppuccin theme repository?"), str(command)):
            self._theme_start(lambda: themes.clone(self.ctx.runner, destination, self.ctx.log), self._theme_done, mutation=True)

    def _install_theme(self):
        repository, variant = self.theme_repository.get_text(), self.theme_variant.get_active_id()
        self._theme_start(lambda: themes.preview_install(repository, variant), self._confirm_theme_install)

    def _confirm_theme_install(self, plan):
        lines = [_("Theme source: {path}").format(path=plan.source),
                 _("Install into: {path}").format(path=plan.target)]
        if plan.backup:
            lines.append(_("Previous theme backup: {path}").format(path=plan.backup))
        accepted = widgets.confirm_list(self.window, _("Install this Catppuccin variant?"), lines,
                                        _("The generated files are copied without running repository scripts. An existing theme is preserved in a dated backup. Desktop settings are changed separately."))
        if not accepted:
            return self._theme_release()
        self.run_operation(lambda: themes.install(self.ctx.runner, plan), on_done=self._theme_done,
                           on_error=self._theme_failed, name=_("Install Catppuccin theme"))

    def _apply_theme(self):
        variant = self.theme_variant.get_active_id()
        self._theme_start(lambda: themes.preview_apply(self.ctx.runner, variant), lambda plan: self._confirm_apply(plan, False))
