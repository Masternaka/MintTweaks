"""Confirmations and common operation reservation using GTK doubles."""
import unittest
from unittest.mock import Mock, patch
from tests import fakegi
fakegi.install()
from minttweaks.core.userfiles import Change, FileOutcome
from minttweaks.modules.terminal import backend
from minttweaks.modules.terminal import integrations
from minttweaks.modules.terminal.page import TerminalPage
from minttweaks.ui.widgets import AppContext
from tests.fakes import FakeRunner


class TerminalPageTests(unittest.TestCase):
    def setUp(self):
        self.ctx = AppContext(FakeRunner())
        self.page = TerminalPage(self.ctx)

    def test_cancelled_configuration_preview_never_writes(self):
        self.page._busy = True
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm, patch.object(self.page, 'run_operation') as run:
            self.page._confirm_files([Change('bashrc', b'alias ll=ls\n', b'changed\n')])
        run.assert_not_called()
        self.assertIn('alias ll=ls', '\n'.join(confirm.call_args.args[2]))
        self.assertFalse(self.page._busy)

    def test_cancelled_shell_preview_never_changes_account(self):
        self.page._busy = True
        with patch.object(self.page, 'confirm', return_value=False), patch.object(self.page, 'run_operation') as run:
            self.page._confirm_shell(backend.ShellPlan('mintuser', '/bin/bash', '/usr/bin/fish'))
        run.assert_not_called()
        self.assertFalse(self.page._busy)

    def test_global_busy_reservation_refuses_configuration_and_releases_controls(self):
        with patch.object(self.ctx, 'run_async'):
            self.ctx.run_operation('Other modification', lambda: None)
        self.page.error = Mock()
        self.page._busy = True
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), patch('minttweaks.core.userfiles.apply') as apply:
            self.page._confirm_files([Change('bashrc', None, b'test')])
        apply.assert_not_called()
        self.page.error.assert_called_once()
        self.assertFalse(self.page._busy)

    def test_failed_recovery_has_visible_details_and_no_success_message(self):
        with patch.object(self.page, 'error') as error, patch.object(self.page, '_done') as done:
            self.page._files_done(FileOutcome(False, errors={'bashrc': 'external edit preserved'}))
        self.assertIn('external edit preserved', error.call_args.args[1])
        self.assertNotIn('verified', done.call_args.args[0])

    def test_starter_selection_skips_installed_unavailable_and_optional_tools(self):
        self.page.state.tools = {entry.id: backend.ToolState(candidate='1.0') for entry in backend.CATALOG}
        self.page.state.tools['bat'] = backend.ToolState(installed=True)
        self.page.state.tools['eza'] = backend.ToolState(error='No candidate')
        for entry in backend.CATALOG:
            value = [False]
            check = Mock()
            check.set_active.side_effect = lambda active, value=value: value.__setitem__(0, active)
            check.get_active.side_effect = lambda value=value: value[0]
            self.page.checks[entry.id] = check
        with patch.object(self.page, 'run_operation') as run:
            self.page._select_starter(True)
        selected = self.page._selected()
        self.assertIn('fzf', selected)
        self.assertIn('ripgrep', selected)
        self.assertNotIn('bat', selected)
        self.assertNotIn('eza', selected)
        self.assertNotIn('zsh', selected)
        self.assertNotIn('atuin', selected)
        run.assert_not_called()
        self.page._select_starter(False)
        self.assertFalse(self.page._selected())

    def test_installation_precedes_configuration_preview(self):
        plan = backend.PackagePlan(('zoxide',), ('zoxide=1.0',), (), 'APT preview')
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), patch.object(self.page, 'run_operation') as operation, patch.object(backend, 'install', return_value='Installed') as install, patch.object(self.page, '_start') as start:
            self.page._confirm_install(plan, 'fish')
            start.assert_not_called()
            message = operation.call_args.args[0]()
            install.assert_called_once()
            operation.call_args.kwargs['on_done'](message)
            with patch.object(integrations, 'preview') as preview:
                start.call_args.args[0]()
            preview.assert_called_once_with(self.ctx.runner, 'fish', ('zoxide',))

    def test_cancelling_configuration_keeps_packages_and_writes_no_files(self):
        plan = integrations.IntegrationPlan('bash', ('zoxide',), True, (Change('bashrc', None, b'config'),), ())
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), patch.object(self.page, 'run_operation') as run, patch.object(self.page, 'refresh'):
            self.page._confirm_integrations(plan)
        run.assert_not_called()
        self.assertFalse(self.page._busy)

    def test_post_install_error_distinguishes_packages_from_configuration(self):
        self.page._busy = True
        with patch.object(self.page, 'error') as error, patch.object(self.page, 'refresh'):
            self.page._post_install_failed(ValueError('manual configuration exists'))
        self.assertIn('Packages were installed', error.call_args.args[0])
        self.assertFalse(self.page._busy)


    def test_search_hides_rows_without_clearing_selection(self):
        self.page.search_entry.get_text = Mock(return_value='fd-find')
        self.page.catalog_filter.get_active_id = Mock(return_value='all')
        self.page.install_shell.get_active_id = Mock(return_value='bash')
        for tool in self.page.catalog_rows:
            self.page.catalog_rows[tool].set_visible = Mock()
            self.page.checks[tool].set_active = Mock()
        self.page._filter_catalog()
        self.page.catalog_rows['fd'].set_visible.assert_called_with(True)
        self.page.catalog_rows['jq'].set_visible.assert_called_with(False)
        for check in self.page.checks.values():
            check.set_active.assert_not_called()

    def test_cancelled_personal_settings_write_nothing(self):
        from minttweaks.modules.terminal.configuration import ConfigurationPlan
        plan = ConfigurationPlan((Change('settings-bash', None, b'alias gst=git'),), ())
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), patch.object(self.page, 'run_operation') as operation:
            self.page._confirm_customization(plan)
        operation.assert_not_called()
        self.assertFalse(self.page._busy)

    def test_export_requires_review_before_writing(self):
        document = {'format':'minttweaks-terminal','schema_version':1,'tools':[], 'integrations':{},'preferences':{'schema_version':1,'shells':{}}}
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), patch.object(self.page, 'run_operation') as operation:
            self.page._confirm_export('/tmp/not-written.json', document)
        operation.assert_not_called()

    def test_import_installs_missing_packages_before_preparing_configuration(self):
        from minttweaks.modules.terminal.transfer import Request
        plan = backend.PackagePlan(('fzf',), ('fzf=1.0',), (), 'APT plan')
        request = Request({'tools':['fzf']}, plan, ())
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), patch.object(self.page, 'run_operation') as operation, patch.object(self.page, '_prepare_import') as prepare:
            self.page._confirm_import(request)
            prepare.assert_not_called()
            operation.call_args.kwargs['on_done']('Installed')
            prepare.assert_called_once_with(request.document, 'Installed')
