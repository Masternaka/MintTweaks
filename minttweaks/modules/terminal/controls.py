"""Focused GTK controls for personal settings, aliases and portable exports."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from ...core import userfiles
from ...i18n import _
from ...ui import widgets
from . import backend, configuration, integrations, status, transfer


class TerminalControls:
    def _shell_picker(self, body, label):
        combo = Gtk.ComboBoxText()
        for shell in backend.SHELLS:
            combo.append(shell, shell.capitalize())
        combo.set_active(0)
        body.pack_start(widgets.row(widgets.label(label), combo), False, False, 0)
        return combo

    def _build_filters(self, body):
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_('Search by tool, package or description'))
        body.pack_start(self.search_entry, False, False, 0)
        self.catalog_filter = Gtk.ComboBoxText()
        for code, label in [('all', _('All tools')), ('installed', _('Installed tools')),
                            ('available', _('Available to install')), ('configurable', _('Integrations for the target shell'))]:
            self.catalog_filter.append(code, label)
        self.catalog_filter.set_active(0)
        body.pack_start(self.catalog_filter, False, False, 0)
        self.filter_label = widgets.label('', wrap=True)
        body.pack_start(self.filter_label, False, False, 0)

    def _filter_catalog(self, *_args):
        query = self.search_entry.get_text()
        mode = self.catalog_filter.get_active_id()
        shell = self.install_shell.get_active_id()
        query = query if isinstance(query, str) else ''
        shell = shell if shell in backend.SHELLS else 'bash'
        mode = mode if mode in ('all', 'installed', 'available', 'configurable') else 'all'
        visible_categories, count = set(), 0
        for entry in backend.CATALOG:
            inspect = self.inspection.get(shell, {}).get(entry.id)
            visible = status.matches(entry, self.state.tools.get(entry.id), inspect, query, mode, shell)
            self.catalog_rows[entry.id].set_visible(visible)
            if visible:
                visible_categories.add(entry.category)
                count += 1
            if inspect:
                self.catalog_status[entry.id].set_text(shell.capitalize() + ': ' + inspect.detail)
        for category, heading in self.category_headings.items():
            heading.set_visible(category in visible_categories)
        self.filter_label.set_text(_('{count} tool(s) shown. Hidden selections are kept.').format(count=count))

    def _update_integration_status(self, *_args):
        shell = self.prompt_shell.get_active_id()
        if shell not in backend.SHELLS:
            shell = 'bash'
        for tool, label in self.integration_status_labels.items():
            value = self.inspection.get(shell, {}).get(tool)
            label.set_text(value.detail if value else _('Not analysed yet.'))

    def _build_settings(self):
        body = self._tab(_('Tool settings'), _('Personal options only. Preview and back up changes before applying them. Open a new terminal to load them.'))
        self.options_shell = self._shell_picker(body, _('Target shell'))
        self.settings_fields = {}
        captions = {
            ('starship', 'git'): _('Show Git information'), ('starship', 'newline'): _('Blank line before the prompt'),
            ('starship', 'symbol'): _('Prompt character'), ('starship', 'color'): _('Prompt color'),
            ('fzf', 'height'): _('Height (%)'), ('fzf', 'layout'): _('Layout'), ('fzf', 'color'): _('Colors'),
            ('fzf', 'preview'): _('Preview files with head (first 100 lines)'),
            ('bat', 'theme'): _('Theme'), ('bat', 'style'): _('Displayed information'),
            ('eza', 'long'): _('Detailed listing'), ('eza', 'git'): _('Git information'), ('eza', 'tree'): _('Tree view'),
            ('tmux', 'prefix'): _('Prefix shortcut'), ('tmux', 'mouse'): _('Mouse support'), ('tmux', 'position'): _('Status bar position'),
        }
        for tool, defaults in configuration.DEFAULTS.items():
            body.pack_start(widgets.title(backend.TOOL_BY_ID[tool].name), False, False, 0)
            for key, default in defaults.items():
                if type(default) is bool:
                    control = Gtk.CheckButton(label=captions[tool, key])
                    control.set_active(default)
                    body.pack_start(control, False, False, 0)
                elif type(default) is int:
                    control = Gtk.SpinButton.new_with_range(10, 100, 5)
                    control.set_value(default)
                    body.pack_start(widgets.row(widgets.label(captions[tool, key]), control), False, False, 0)
                else:
                    control = Gtk.ComboBoxText()
                    for value in configuration.CHOICES[tool, key]:
                        control.append(value, value)
                    control.set_active_id(default)
                    body.pack_start(widgets.row(widgets.label(captions[tool, key]), control), False, False, 0)
                self.settings_fields[tool, key] = control
            self._action(body, _('Preview settings for {tool}').format(tool=backend.TOOL_BY_ID[tool].name), lambda tool=tool: self._save_settings(tool))
        body.pack_start(widgets.label(_('Eza options use mtk-eza. Tmux options use mtk-tmux on a separate server. Starship settings are shared between managed shells.'), wrap=True), False, False, 0)

    def _load_settings(self, *_args):
        shell = self.options_shell.get_active_id()
        data = self.preferences.get('shells', {}).get(shell, {}).get('settings', {})
        for tool, defaults in configuration.DEFAULTS.items():
            for key, default in defaults.items():
                value = data.get(tool, defaults).get(key, default)
                control = self.settings_fields[tool, key]
                if type(default) is bool:
                    control.set_active(value)
                elif type(default) is int:
                    control.set_value(value)
                else:
                    control.set_active_id(value)

    def _save_settings(self, tool):
        values = {}
        for key, default in configuration.DEFAULTS[tool].items():
            control = self.settings_fields[tool, key]
            values[key] = (control.get_active() if type(default) is bool else
                           control.get_value_as_int() if type(default) is int else control.get_active_id())
        shell = self.options_shell.get_active_id()
        self._start(lambda: configuration.preview(self.ctx.runner, shell, tool, values), self._confirm_customization)

    def _confirm_customization(self, plan):
        if not plan.changes:
            self.info(_('No configuration changes are needed.'))
            return self._release()
        lines = list(plan.notes) + [''] + backend.changes_text(plan.changes, backend.targets())
        if not widgets.confirm_list(self.window, _('Apply these personal settings?'), lines, _('Review all file differences. A private backup is saved before writing.')):
            return self._release()
        self.run_operation(lambda: configuration.apply(self.ctx.runner, plan), on_done=self._files_done,
                           on_error=self._failed, name=_('Update personal terminal settings'))

    def _build_aliases(self):
        body = self._tab(_('Personal aliases'), _('Add, edit or remove your own shortcuts for one shell. Commands are displayed for review and are never executed by MintTweaks.'))
        self.alias_shell = self._shell_picker(body, _('Target shell'))
        self.alias_combo = Gtk.ComboBoxText()
        body.pack_start(self.alias_combo, False, False, 0)
        self.alias_name = Gtk.Entry()
        self.alias_command = Gtk.Entry()
        body.pack_start(widgets.row(widgets.label(_('Alias name')), self.alias_name), False, False, 0)
        body.pack_start(widgets.row(widgets.label(_('Command')), self.alias_command), False, False, 0)
        self._action(body, _('Load selected alias'), self._edit_alias)
        self._action(body, _('Preview alias save'), lambda: self._save_alias(False))
        self._action(body, _('Preview alias removal'), lambda: self._save_alias(True))
        self.alias_hint = widgets.label('', wrap=True)
        body.pack_start(self.alias_hint, False, False, 0)

    def _load_aliases(self, *_args):
        shell = self.alias_shell.get_active_id()
        aliases = self.preferences.get('shells', {}).get(shell, {}).get('aliases', {})
        self.alias_combo.remove_all()
        for name, command in sorted(aliases.items()):
            self.alias_combo.append(name, name + ' = ' + command)
        self.alias_combo.set_active(0 if aliases else -1)
        self.alias_name.set_text('')
        self.alias_command.set_text('')
        self.alias_hint.set_text(_('{count} managed alias(es). External startup files are not fully inspected.').format(count=len(aliases)))

    def _edit_alias(self):
        shell, name = self.alias_shell.get_active_id(), self.alias_combo.get_active_id()
        aliases = self.preferences.get('shells', {}).get(shell, {}).get('aliases', {})
        if name in aliases:
            self.alias_name.set_text(name)
            self.alias_command.set_text(aliases[name])

    def _save_alias(self, remove):
        shell = self.alias_shell.get_active_id()
        name, command = self.alias_name.get_text(), self.alias_command.get_text()
        def work():
            aliases = dict(configuration.load()['shells'].get(shell, {}).get('aliases', {}))
            if remove:
                if name not in aliases:
                    raise ValueError(_('Choose an existing managed alias to remove.'))
                aliases.pop(name)
            else:
                aliases[name] = command
            return configuration.preview(self.ctx.runner, shell, aliases=aliases)
        self._start(work, self._confirm_customization)

    def _build_transfer(self):
        body = self._tab(_('Export and import'), _('Export your personal tool selection, managed integrations, settings and aliases. Import checks this machine and shows package and configuration previews separately.'))
        body.pack_start(widgets.label(_('Only managed choices and alias commands are exported, without startup scripts or command history. Review personal paths and sensitive values before sharing.'), wrap=True), False, False, 0)
        self._action(body, _('Export personal configuration'), self._export_personal)
        self._action(body, _('Import personal configuration'), self._import_personal)

    def _choose_file(self, save):
        dialog = Gtk.FileChooserDialog(_('Export personal configuration') if save else _('Import personal configuration'), self.window,
                                       Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN,
                                       (_('Cancel'), Gtk.ResponseType.CANCEL, _('Save') if save else _('Open'), Gtk.ResponseType.OK))
        if save:
            dialog.set_current_name('minttweaks-terminal.json')
        filter_ = Gtk.FileFilter()
        filter_.set_name(_('JSON files'))
        filter_.add_pattern('*.json')
        dialog.add_filter(filter_)
        try:
            return dialog.get_filename() if dialog.run() == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()

    def _export_personal(self):
        filename = self._choose_file(True)
        if not filename:
            return
        selected = tuple(self._selected())
        def prepare():
            current = backend.collect_state(self.ctx.runner)
            inspection = status.collect(self.ctx.runner, current.tools)
            return transfer.export_document(current.tools, inspection, selected)
        self._start(prepare, lambda document: self._confirm_export(filename, document))

    def _confirm_export(self, filename, document):
        import json
        if not widgets.confirm_list(self.window, _('Export this personal configuration?'), json.dumps(document, ensure_ascii=False, indent=2).splitlines(), str(filename)):
            return self._release()
        self.run_operation(lambda: transfer.write(self.ctx.runner, filename, document),
                           on_done=lambda outcome: self._done(_('Simulation: no configuration files changed.') if outcome.simulated else _('Personal configuration exported.')),
                           on_error=self._failed, name=_('Export terminal configuration'))

    def _import_personal(self):
        filename = self._choose_file(False)
        if filename:
            self._start(lambda: transfer.inspect(self.ctx.runner, transfer.read(filename)), self._confirm_import)

    def _confirm_import(self, request):
        if request.packages:
            lines = list(request.notes) + list(request.packages.specs) + request.packages.output.splitlines()
            if not widgets.confirm_list(self.window, _('Install missing imported tools?'), lines, _('Configuration is previewed after installation. Cancelling that later preview keeps the packages.')):
                return self._release()
            self.run_operation(lambda: backend.install(self.ctx.runner, request.packages, self.ctx.log),
                               on_done=lambda message: self._prepare_import(request.document, message),
                               on_error=self._failed, name=_('Install imported terminal tools'))
        else:
            self._prepare_import(request.document)

    def _prepare_import(self, document, message=''):
        if message:
            self.ctx.log(message)
        self._release()
        self._start(lambda: transfer.preview_configuration(self.ctx.runner, document),
                    lambda plan: self._confirm_import_configuration(document, plan), self._post_install_failed if message else self._failed)

    def _confirm_import_configuration(self, document, plan):
        import json
        lines = list(plan.notes) + [json.dumps(document['tools'], ensure_ascii=False)] + backend.changes_text(plan.changes, backend.targets())
        if not plan.changes:
            self.info(_('No configuration changes are needed.'))
            return self._release()
        if not widgets.confirm_list(self.window, _('Import these personal settings?'), lines, _('Paths and shell hooks are regenerated for this machine. Review all aliases and differences before confirming.')):
            self._release()
            return self.refresh()
        self.run_operation(lambda: transfer.apply_configuration(self.ctx.runner, document, plan),
                           on_done=self._files_done, on_error=self._failed, name=_('Import terminal configuration'))
