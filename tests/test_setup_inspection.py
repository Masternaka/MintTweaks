"""Optional observations stay read-only and separate from declared progress."""
import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from minttweaks.core.runner import Result
from minttweaks.modules.setup import backend, inspection
from minttweaks.modules.home import backend as home
from minttweaks.modules.cinnamon import backend as cinnamon
from tests.fakes import FakeRunner
from tests.test_software import BrowserRunner
from tests import fakegi

fakegi.install()
from minttweaks.modules.setup.page import SetupPage
from minttweaks.ui.widgets import AppContext


class InspectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.runner = BrowserRunner()

    def test_unknown_step_is_refused_before_any_diagnostic(self):
        with self.assertRaises(ValueError):
            inspection.collect(self.runner, 'unknown')
        self.assertFalse(self.runner.calls)

    def test_simulation_never_reads_commands_or_configuration(self):
        self.runner.dry_run = True
        with patch.object(inspection.home, 'collect_report') as health, \
                patch.object(inspection.configuration, 'load') as preferences, \
                patch.object(inspection.firefox, 'load_policy') as policy, \
                patch.object(inspection.cinnamon, 'capture') as settings, \
                patch.object(inspection.userfiles, 'read_file') as files:
            for step in backend.STEPS:
                result = inspection.collect(self.runner, step.id)
                self.assertEqual(result.items[0].state, 'unavailable')
                self.assertIn('simulation', result.items[0].detail)
        for read in (health, preferences, policy, settings, files):
            read.assert_not_called()
        self.assertFalse(self.runner.calls)

    def test_health_reports_unavailable_checks_without_success(self):
        report = home.HomeReport(home.SystemSummary(), [
            home.Finding('ok', 'Disk'), home.Finding('info', 'Journal', completed=False),
            home.Finding('warn', 'Updates'),
        ])
        with patch.object(inspection.home, 'collect_report', return_value=report):
            result = inspection.collect(self.runner, 'health')
        self.assertEqual([item.state for item in result.items], ['detected', 'unavailable', 'attention'])

    def test_browser_presence_never_completes_the_step_or_requires_every_browser(self):
        self.runner.installed['helium-bin'] = '1.2'
        result = inspection.collect(self.runner, 'software')
        self.assertEqual(result.items[0].state, 'detected')
        self.assertIn('1.2', result.items[0].detail)
        self.assertEqual(result.items[1].state, 'not_detected')
        self.assertIn('not required', result.items[1].detail)
        self.assertIn('does not verify download origin', result.limitation)
        self.assertFalse(any(command.needs_root for command in self.runner.calls))

    def test_legacy_zen_is_an_item_to_review(self):
        self.runner.installed['zen-browser'] = '1.0+legacy'
        with patch('minttweaks.modules.software.zen.os.geteuid', return_value=1000):
            result = inspection.collect(self.runner, 'software')
        self.assertEqual(result.items[-1].state, 'attention')
        self.assertIn('Legacy Debian', result.items[-1].detail)

    def test_terminal_does_not_execute_startup_files_or_hooks(self):
        self.runner.installed.update({'bash': '5.2', 'kitty': '0.30'})
        with patch.object(inspection.terminal, 'current_account', return_value=('private-user', '/bin/bash')), \
                patch.object(inspection.configuration, 'load', return_value={'shells': {'bash': {}}, 'terminals': {}}):
            result = inspection.collect(self.runner, 'terminal')
        self.assertEqual(result.items[0].detail, '/bin/bash')
        self.assertNotIn('private-user', repr(result))
        self.assertIn('effective loading was not checked', result.items[1].detail)
        self.assertTrue(all(command.argv[0] == 'dpkg-query' and not command.needs_root for command in self.runner.calls))

    def test_corrupt_terminal_preferences_do_not_hide_package_observations(self):
        with patch.object(inspection.terminal, 'current_account', side_effect=OSError('private account detail')), \
                patch.object(inspection.configuration, 'load', side_effect=ValueError('private configuration')):
            result = inspection.collect(self.runner, 'terminal')
        self.assertEqual(result.items[0].state, 'unavailable')
        self.assertEqual(result.items[1].state, 'unavailable')
        self.assertEqual(len(result.items), 7)
        self.assertNotIn('private configuration', repr(result))

    def test_firefox_policy_presence_does_not_claim_extensions_are_loaded(self):
        document = inspection.firefox.plan_policy({}, [inspection.firefox.CATALOG[0].id])
        with patch.object(inspection.shutil, 'which', return_value='/usr/bin/firefox'), \
                patch.object(inspection.firefox, 'load_policy', return_value=(document, None)):
            result = inspection.collect(self.runner, 'firefox')
        self.assertEqual(result.items[1].state, 'detected')
        self.assertIn('Browser loading was not checked', result.items[1].detail)
        self.assertIn('Restart Firefox', result.limitation)
        self.assertFalse(self.runner.calls)

    def test_unreadable_firefox_policy_is_unavailable_not_missing(self):
        with patch.object(inspection.shutil, 'which', return_value=None), \
                patch.object(inspection.firefox, 'load_policy', return_value=(None, 'private path unreadable')):
            result = inspection.collect(self.runner, 'firefox')
        self.assertEqual(result.items[1].state, 'unavailable')
        self.assertNotIn('private path', repr(result))

    def test_cinnamon_does_not_infer_that_a_saved_profile_is_applied(self):
        snapshot = cinnamon.Snapshot('now', {'one': 'a theme'}, {'two': 'read failed'})
        with patch.object(inspection.cinnamon, 'capture', return_value=snapshot), \
                patch.object(inspection.cinnamon, 'list_profiles', return_value=cinnamon.Catalog([Mock()])):
            result = inspection.collect(self.runner, 'cinnamon')
        self.assertEqual(result.items[0].state, 'unavailable')
        self.assertEqual(result.items[1].state, 'detected')
        self.assertIn('does not mean one is currently applied', result.items[1].detail)
        self.assertNotIn('a theme', repr(result))

    def test_samba_readings_never_ask_for_root_or_test_network_access(self):
        self.runner.installed['samba'] = '4.19'
        self.runner.add(['systemctl', 'show'], stdout='LoadState=loaded\nActiveState=active\n')
        configuration = self.directory / 'smb.conf'
        configuration.write_text('[global]\n[Private share]\npath = /home/private-user\n')
        with patch.object(inspection.paths, 'SMB_CONF', configuration):
            result = inspection.collect(self.runner, 'samba')
        self.assertEqual([item.state for item in result.items], ['detected', 'detected', 'detected'])
        self.assertIn('1 share definition', result.items[2].detail)
        self.assertNotIn('private-user', repr(result))
        self.assertNotIn('Private share', repr(result))
        self.assertFalse(any(command.needs_root for command in self.runner.calls))
        self.assertTrue(all(command.argv[0] in {'dpkg-query', 'systemctl'} for command in self.runner.calls))
        self.assertEqual(configuration.read_text(), '[global]\n[Private share]\npath = /home/private-user\n')

    def test_samba_permission_failure_is_unavailable_not_inactive(self):
        self.runner.add(['systemctl', 'show'], returncode=1, stderr='Access denied')
        with patch.object(inspection.userfiles, 'read_file', side_effect=PermissionError):
            result = inspection.collect(self.runner, 'samba')
        self.assertEqual(result.items[1].state, 'unavailable')
        self.assertEqual(result.items[2].state, 'unavailable')


class InspectionPageTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.context = AppContext(self.runner)
        self.page = SetupPage(self.context)
        self.page.plan = backend.Plan(selected=['firefox', 'health'])
        self.page.plan.progress['firefox'] = backend.Progress('retry', 'Keep this note')
        self.page.step_combo.get_active_id = Mock(return_value='firefox')
        self.page.note_entry.set_text = Mock()
        self.page.observation_buffer.set_text = Mock()

    def observation(self):
        return inspection.Observation('firefox', datetime.datetime.now(datetime.timezone.utc).isoformat(),
            (inspection.Item('Firefox policy', 'detected', 'One policy entry'),), 'Check Firefox manually')

    def test_observation_is_optional_and_never_saves_or_changes_progress(self):
        with patch.object(self.context, 'run_async') as run, patch.object(backend, 'save_plan') as save:
            self.page._observe_selected()
            callback = run.call_args.kwargs['on_done']
            callback(self.observation())
        save.assert_not_called()
        self.assertEqual(self.page.plan.progress['firefox'], backend.Progress('retry', 'Keep this note'))
        self.page.note_entry.set_text.assert_not_called()
        self.assertFalse(self.page._observing)
        self.assertIn('Detected', self.page.observation_buffer.set_text.call_args.args[0])

    def test_result_is_discarded_when_selection_changes_during_collection(self):
        with patch.object(self.context, 'run_async') as run:
            self.page._observe_selected()
        self.page.step_combo.get_active_id.return_value = 'health'
        self.page._invalidate_observation()
        self.page.observation_buffer.set_text.reset_mock()
        run.call_args.kwargs['on_done'](self.observation())
        self.page.observation_buffer.set_text.assert_not_called()
        self.assertFalse(self.page._observing)

    def test_operation_invalidates_a_pending_observation(self):
        with patch.object(self.context, 'run_async') as run:
            self.page._observe_selected()
        self.page._operation_changed('Another operation')
        self.page.observation_buffer.set_text.reset_mock()
        run.call_args.kwargs['on_done'](self.observation())
        self.page.observation_buffer.set_text.assert_not_called()

    def test_failed_observation_does_not_disable_manual_progress(self):
        with patch.object(self.context, 'run_async') as run:
            self.page._observe_selected()
        run.call_args.kwargs['on_error'](OSError('read failed'))
        self.assertFalse(self.page._read_failed)
        self.assertFalse(self.page._observing)
        self.assertEqual(self.page.plan.progress['firefox'].note, 'Keep this note')
        with patch.object(self.page.note_entry, 'get_text', return_value='Keep this note'), \
                patch.object(self.page, '_persist') as persist:
            self.page._save_result('verified')
        persist.assert_called_once()

    def test_dirty_selection_simulation_or_active_mutation_prevents_new_checks(self):
        for flag in ('dirty', 'simulation', 'operation'):
            self.page._dirty = flag == 'dirty'
            self.runner.dry_run = flag == 'simulation'
            self.context.operation_name = 'Installation' if flag == 'operation' else None
            with patch.object(self.context, 'run_async') as run:
                self.page._observe_selected()
            run.assert_not_called()

    def test_check_preserves_the_saved_plan_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'plan.json'
            plan = backend.save_plan(self.runner, backend.Plan(), ['firefox'], path=path,
                                     step_id='firefox', state='verified', note='Already tested under Mint')
            before = path.read_bytes()
            self.page.plan = plan
            with patch.object(self.context, 'run_async') as run:
                self.page._observe_selected()
            run.call_args.kwargs['on_done'](self.observation())
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(backend.load_plan(path), plan)
