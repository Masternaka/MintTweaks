"""Diagnostic exports use reviewed bytes and omit private raw data by design."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from minttweaks.modules.home import backend as home, diagnostics
from tests.fakes import FakeRunner
from tests import fakegi

fakegi.install()
from minttweaks.modules.home.page import HomePage
from minttweaks.ui import widgets


def observation():
    return home.HomeReport(home.SystemSummary(
        os_name='Linux Mint 22.1', kernel='6.8.0-45-generic', hostname='PRIVATE-HOST',
        uptime='2 h 10 min', memory_used='2 GB', memory_total='8 GB', disk_percent=30,
        disk_free='50 GB'), [
        home.Finding('warn', 'Boot errors', 'Journal sample: {sample}',
                     {'sample': 'PASSWORD CONTENT 192.168.1.8 /home/alice/private'}),
        home.Finding('error', 'Failed services', '{count} failed: {names}',
                     {'count': 2, 'names': 'secret-user@private-host.service'}),
        home.Finding('info', 'Package database', 'Could not verify: {sample}',
                     {'sample': 'private database path'}, completed=False),
        home.Finding('ok', 'Disk space', '{percent}% used; {free} free',
                     {'percent': 30, 'free': '50 GB'}),
    ])


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.runner.add(['dpkg', '--print-architecture'], stdout='amd64')
        self.runner.add(['dpkg-query'], stdout='6.4.8')
        probe = patch.object(home, 'collect_report', return_value=observation())
        self.probe = probe.start()
        self.addCleanup(probe.stop)
        identity = patch.object(diagnostics.Redactor, 'local', return_value=diagnostics.Redactor(['alice', 'PRIVATE-HOST', '/home/alice']))
        identity.start()
        self.addCleanup(identity.stop)

    def test_report_keeps_versions_findings_and_unavailable_checks(self):
        report = diagnostics.collect(self.runner)
        for expected in ('Linux Mint 22.1', '6.8.0-45-generic', '6.4.8', 'amd64',
                         '2 GB / 8 GB', '30%', '2 failed', 'unavailable: 1',
                         'Package database [unavailable]'):
            self.assertIn(expected, report.text)
        self.assertTrue(report.filename.endswith('.md'))
        self.assertNotIn('PRIVATE-HOST', report.text)
        self.assertEqual(len(self.runner.calls), 2)
        self.assertFalse(any(command.needs_root for command in self.runner.calls))

    def test_raw_findings_are_excluded_before_redaction(self):
        report = diagnostics.collect(self.runner)
        for secret in ('PASSWORD CONTENT', '192.168.1.8', '/home/alice',
                       'secret-user', 'private-host', 'private database path'):
            self.assertNotIn(secret, report.text)
        self.assertIn('Details omitted', report.text)
        self.assertEqual(self.probe.call_count, 1)

    def test_history_has_only_allowlisted_metadata_and_is_bounded(self):
        history = Mock()
        history.entries.return_value = [{
            'module': 'terminal', 'status': 'failed', 'started': '2026-11-03T10:00:00+00:00',
            'simulated': False, 'name': 'PRIVATE ACTION', 'id': 'PRIVATE-ID',
            'backups': ('/home/alice/backups/private.json',),
        } for _ in range(30)]
        report = diagnostics.collect(self.runner, history)
        history.entries.assert_called_once_with(limit=20)
        self.assertEqual(report.text.count('terminal | failed | real'), 20)
        for private in ('PRIVATE ACTION', 'PRIVATE-ID', '/home/alice/backups'):
            self.assertNotIn(private, report.text)

    def test_excluding_history_does_not_open_the_database(self):
        history = Mock()
        report = diagnostics.collect(self.runner, history, include_history=False)
        history.entries.assert_not_called()
        self.assertIn('history was excluded', report.text)

    def test_history_error_or_invalid_timestamp_does_not_hide_system_findings(self):
        history = Mock()
        for entries in (OSError('private error'), [{'module': 'terminal', 'status': 'failed', 'started': 'not a timestamp'}]):
            history.entries.side_effect = entries if isinstance(entries, OSError) else None
            history.entries.return_value = entries
            report = diagnostics.collect(self.runner, history)
            self.assertIn('history could not be read', report.text)
            self.assertIn('Linux Mint 22.1', report.text)
            self.assertNotIn('private error', report.text)

    def test_missing_versions_are_unavailable_without_exporting_errors(self):
        runner = FakeRunner()
        report = diagnostics.collect(runner)
        self.assertIn('Unavailable', report.text)
        self.assertNotIn('no fake rule', report.text)

    def test_each_preview_collects_a_fresh_observation(self):
        diagnostics.collect(self.runner)
        self.probe.return_value = home.HomeReport(home.SystemSummary(os_name='A different system'), [])
        report = diagnostics.collect(self.runner)
        self.assertIn('A different system', report.text)
        self.assertEqual(self.probe.call_count, 2)

    def test_simulation_collects_nothing(self):
        self.runner.dry_run = True
        with self.assertRaises(ValueError):
            diagnostics.collect(self.runner)
        self.probe.assert_not_called()
        self.assertEqual(self.runner.calls, [])

    def test_collecting_real_history_does_not_modify_or_export_its_private_fields(self):
        from minttweaks.core.history import HistoryStore
        with tempfile.TemporaryDirectory() as temporary:
            store = HistoryStore(Path(temporary).resolve() / 'history')
            identifier = store.begin('PRIVATE ACTION NAME', 'terminal')
            store.add_backup(identifier, '/home/alice/PRIVATE-BACKUP.json')
            store.finish(identifier, 'failed')
            before = store.database.read_bytes()
            report = diagnostics.collect(self.runner, store)
            self.assertEqual(store.database.read_bytes(), before)
        self.assertIn('terminal | failed | real', report.text)
        self.assertNotIn('PRIVATE ACTION NAME', report.text)
        self.assertNotIn('PRIVATE-BACKUP', report.text)


class RedactionTests(unittest.TestCase):
    def test_common_identifiers_addresses_paths_and_credentials_are_masked(self):
        redactor = diagnostics.Redactor(['alice', 'mint-pc', '/home/alice'])
        inputs = ['alice', 'mint-pc', 'ALICE', 'build_alice-custom', 'alice@example.org',
                  '192.168.1.12', '2001:db8:1::abcd', 'fe80::1%eth0',
                  'aa:bb:cc:dd:ee:ff', '/home/alice/private/file', '/srv/private',
                  'smb://alice:secret@server/share', 'https://host/?token=secret',
                  'password=secret words', 'Authorization: Bearer secret', 'Bearer secret']
        for value in inputs:
            with self.subTest(value=value):
                result = redactor.text(value)
                self.assertNotIn(value, result)
                self.assertNotIn('secret', result)

    def test_home_directory_with_spaces_is_masked(self):
        redactor = diagnostics.Redactor(['/home/Jean Dupont', 'Jean'])
        self.assertNotIn('Dupont', redactor.text('/home/Jean Dupont/private'))

    def test_useful_versions_survive_and_markdown_is_escaped(self):
        redactor = diagnostics.Redactor([])
        self.assertEqual(redactor.text('6.8.0-45-generic'), '6.8.0-45-generic')
        self.assertEqual(redactor.text('2 GB / 8 GB'), '2 GB / 8 GB')
        output = redactor.text('![external](https://example.org/image) <script> | row\nnext')
        self.assertNotIn('https://', output)
        self.assertNotIn('\n', output)
        self.assertIn('\\<script\\>', output)
        self.assertIn('\\|', output)


class DiagnosticSaveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runner = FakeRunner()
        self.report = diagnostics.DiagnosticReport('# Reviewed report\n', '2026-11-03T10:00:00+00:00')

    def test_save_writes_exact_reviewed_bytes_with_private_permissions(self):
        target = self.root / 'report.md'
        diagnostics.save(self.runner, self.report, target)
        self.assertEqual(target.read_bytes(), self.report.text.encode())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.iterdir()), [target])
        self.assertEqual(self.runner.calls, [])

    def test_existing_files_and_broken_symlinks_are_preserved(self):
        existing = self.root / 'existing.md'
        existing.write_text('keep original')
        broken = self.root / 'broken.md'
        broken.symlink_to(self.root / 'absent')
        for target in (existing, broken):
            with self.assertRaises(ValueError):
                diagnostics.save(self.runner, self.report, target)
        self.assertEqual(existing.read_text(), 'keep original')
        self.assertTrue(broken.is_symlink())
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_failed_write_leaves_no_partial_report(self):
        target = self.root / 'report.md'
        with patch.object(diagnostics.os, 'fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                diagnostics.save(self.runner, self.report, target)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_simulation_writes_no_file(self):
        self.runner.dry_run = True
        diagnostics.save(self.runner, self.report, self.root / 'report.md')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_oversized_report_is_refused_before_any_write(self):
        report = diagnostics.DiagnosticReport('x' * (diagnostics.MAX_REPORT_BYTES + 1), self.report.created_at)
        with self.assertRaises(ValueError):
            diagnostics.save(self.runner, report, self.root / 'report.md')
        self.assertEqual(list(self.root.iterdir()), [])


class DiagnosticPageTests(unittest.TestCase):
    def setUp(self):
        self.ctx = widgets.AppContext(FakeRunner())
        self.page = HomePage(self.ctx)
        self.report = diagnostics.DiagnosticReport('# Reviewed report\n', '2026-11-03T10:00:00+00:00')

    def test_cancelled_preview_does_not_open_chooser_or_write(self):
        with patch.object(widgets.Gtk, 'Dialog') as dialog, \
                patch.object(self.page, '_choose_report_file') as choose, \
                patch.object(self.page, 'run_operation') as run:
            dialog.return_value.run.return_value = widgets.Gtk.ResponseType.CANCEL
            self.page._preview_export(self.report)
        choose.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.page._exporting)

    def test_cancelled_file_chooser_does_not_write(self):
        with patch.object(widgets.Gtk, 'Dialog') as dialog, \
                patch.object(self.page, '_choose_report_file', return_value=None), \
                patch.object(self.page, 'run_operation') as run:
            dialog.return_value.run.return_value = widgets.Gtk.ResponseType.OK
            self.page._preview_export(self.report)
        run.assert_not_called()
        self.assertFalse(self.page._exporting)

    def test_preview_and_save_use_the_same_report_without_recollection(self):
        buffer = Mock()
        with patch.object(widgets.Gtk, 'Dialog') as dialog, \
                patch.object(widgets, 'text_view', return_value=(Mock(), Mock(), buffer)), \
                patch.object(self.page, '_choose_report_file', return_value='/tmp/report.md'), \
                patch.object(self.page, 'run_operation') as run, \
                patch.object(diagnostics, 'save') as save:
            dialog.return_value.run.return_value = widgets.Gtk.ResponseType.OK
            self.page._preview_export(self.report)
            run.call_args.args[0]()
        buffer.set_text.assert_called_once_with(self.report.text)
        save.assert_called_once_with(self.ctx.runner, self.report, '/tmp/report.md')

    def test_failed_export_restores_controls(self):
        self.page._exporting = True
        with patch.object(self.page, 'error') as error:
            self.page._export_failed(OSError('permission denied'))
        self.assertFalse(self.page._exporting)
        error.assert_called_once()

    def test_simulation_does_not_start_collection(self):
        self.ctx.runner.dry_run = True
        with patch.object(self.ctx, 'run_async') as run:
            self.page._on_export()
        run.assert_not_called()

    def test_busy_operation_refuses_saving_and_restores_export_controls(self):
        with patch.object(self.ctx, 'run_async'):
            self.ctx.run_operation('Existing operation', lambda: None)
        with patch.object(widgets.Gtk, 'Dialog') as dialog, \
                patch.object(self.page, '_choose_report_file', return_value='/tmp/report.md'), \
                patch.object(diagnostics, 'save') as save, \
                patch.object(self.page, 'error') as error:
            dialog.return_value.run.return_value = widgets.Gtk.ResponseType.OK
            self.page._preview_export(self.report)
        save.assert_not_called()
        error.assert_called_once()
        self.assertFalse(self.page._exporting)
