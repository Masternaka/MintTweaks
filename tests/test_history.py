"""Operation metadata persists without command output or configuration contents."""
import concurrent.futures
import os
from pathlib import Path
import queue
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from minttweaks.core import history, userfiles
from minttweaks.core.runner import Result
from tests import fakegi
from tests.fakes import FakeRunner

fakegi.install()
from minttweaks.ui import widgets
from minttweaks.modules.history.page import HistoryPage


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = history.HistoryStore(self.root / 'history')

    def test_read_empty_history_creates_no_files(self):
        self.assertEqual(self.store.entries(), [])
        self.assertFalse(self.store.directory.exists())

    def test_persists_dates_module_status_and_backup_references(self):
        identifier = self.store.begin('Apply settings', 'terminal')
        backup = self.root / 'backup.json'
        self.store.add_backup(identifier, backup)
        self.store.add_backup(identifier, backup)
        self.store.finish(identifier, 'completed')
        reopened = history.HistoryStore(self.store.directory)
        row = reopened.entries()[0]
        self.assertEqual((row['name'], row['module'], row['status']), ('Apply settings', 'terminal', 'completed'))
        self.assertEqual(row['backups'], (str(backup),))
        self.assertIsNotNone(row['finished'])
        self.assertEqual(os.stat(self.store.database).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.store.directory).st_mode & 0o777, 0o700)

    def test_old_unfinished_operation_is_unknown_without_rewriting_it(self):
        self.store.begin('Install', 'software')
        self.assertEqual(self.store.entries()[0]['status'], 'running')
        previous = self.store.database.read_bytes()
        restarted = history.HistoryStore(self.store.directory)
        self.assertEqual(restarted.entries(status='unknown')[0]['status'], 'unknown')
        self.assertEqual(restarted.entries(status='running'), [])
        self.assertEqual(previous, self.store.database.read_bytes())

    def test_filters_and_pages_keep_distinct_operations(self):
        for number in range(8):
            identifier = self.store.begin(str(number), 'software')
            self.store.finish(identifier, 'completed' if number % 2 else 'failed')
        first = self.store.entries(limit=3)
        second = self.store.entries(limit=3, offset=3)
        self.assertEqual(len(first), 3)
        self.assertFalse({r['id'] for r in first} & {r['id'] for r in second})
        self.assertEqual(len(self.store.entries(status='failed')), 4)
        with self.assertRaises(ValueError):
            self.store.entries(status="' OR 1=1")

    def test_writers_do_not_lose_entries(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            identifiers = list(executor.map(lambda n: self.store.begin('Action ' + str(n), 'terminal'), range(16)))
        self.assertEqual(len(set(identifiers)), 16)
        self.assertEqual(len(self.store.entries()), 16)

    def test_corrupt_and_future_databases_are_preserved(self):
        self.store.begin('Action', 'terminal')
        with sqlite3.connect(self.store.database) as connection:
            connection.execute('PRAGMA user_version = 99')
        original = self.store.database.read_bytes()
        with self.assertRaises(ValueError):
            self.store.entries()
        with self.assertRaises(ValueError):
            self.store.begin('Another', 'terminal')
        self.assertEqual(self.store.database.read_bytes(), original)
        self.store.database.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.entries()
        self.assertEqual(self.store.database.read_bytes(), b'not a database')

    def test_symlink_database_and_directory_are_refused(self):
        target = self.root / 'preserve'
        target.write_text('unchanged')
        self.store.directory.mkdir()
        self.store.database.symlink_to(target)
        with self.assertRaises(OSError):
            self.store.begin('Action', 'terminal')
        self.assertEqual(target.read_text(), 'unchanged')
        other = history.HistoryStore(self.root / 'linked')
        other.directory.symlink_to(self.store.directory)
        with self.assertRaises(OSError):
            other.entries()


class HistoryOperationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = history.HistoryStore(self.root / 'history')
        self.ctx = widgets.AppContext(FakeRunner(), history=self.store)
        self.callbacks = queue.Queue()
        idle = patch.object(widgets.GLib, 'idle_add', side_effect=lambda *args: self.callbacks.put(args))
        idle.start()
        self.addCleanup(idle.stop)

    def drain(self):
        while not self.callbacks.empty():
            callback, *args = self.callbacks.get_nowait()
            callback(*args)

    def run_work(self, work, **kwargs):
        worker = self.ctx.run_operation('Apply configuration', work, module='terminal', **kwargs)
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.drain()

    def test_failure_return_is_recorded_without_persisting_sensitive_output(self):
        secret = 'private-password-very-secret'
        self.run_work(lambda: [Result('command ' + secret, 0), Result(secret, 1, stderr=secret)])
        self.assertEqual(self.store.entries()[0]['status'], 'failed')
        self.assertNotIn(secret.encode(), self.store.database.read_bytes())

    def test_exception_is_recorded_without_its_private_message(self):
        def fail():
            raise ValueError('secret payload')
        with patch('traceback.print_exc'):
            self.run_work(fail, on_error=lambda _exc: None)
        self.assertEqual(self.store.entries()[0]['status'], 'failed')
        self.assertNotIn(b'secret payload', self.store.database.read_bytes())
        self.assertIsNone(self.ctx.operation_name)

    def test_recorded_outcome_survives_a_pending_gtk_callback(self):
        worker = self.ctx.run_operation('Install', lambda: Result('apt', 0), module='software')
        worker.join(3)
        self.assertEqual(self.store.entries()[0]['status'], 'completed')
        self.assertEqual(self.ctx.operation_name, 'Install')
        self.drain()
        self.assertIsNone(self.ctx.operation_name)

    def test_callback_failure_has_a_distinct_status(self):
        worker = self.ctx.run_operation('Install', lambda: Result('apt', 0),
            on_done=Mock(side_effect=RuntimeError('GUI error')))
        worker.join(3)
        with self.assertRaises(RuntimeError):
            self.drain()
        self.assertEqual(self.store.entries()[0]['status'], 'interface_error')
        self.assertIsNone(self.ctx.operation_name)

    def test_simulation_is_identified_and_has_no_backup(self):
        self.ctx.runner.dry_run = True
        self.run_work(lambda: userfiles.apply(self.ctx.runner, {}, [], self.root / 'backups'))
        row = self.store.entries()[0]
        self.assertEqual(row['status'], 'simulation')
        self.assertTrue(row['simulated'])
        self.assertEqual(row['backups'], ())
        self.assertFalse((self.root / 'backups').exists())

    def test_backup_is_linked_without_copying_contents(self):
        target = self.root / 'config'
        target.write_bytes(b'private configuration')
        changes = userfiles.preview({'config': target}, {'config': b'updated'})
        self.run_work(lambda: userfiles.apply(self.ctx.runner, {'config': target}, changes, self.root / 'backups'))
        row = self.store.entries()[0]
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(len(row['backups']), 1)
        self.assertTrue(Path(row['backups'][0]).is_file())
        self.assertNotIn(b'private configuration', self.store.database.read_bytes())
        self.assertIsNone(history.backup_recorder.get())

    def test_backup_reference_survives_a_failure_after_creation(self):
        backup = self.root / 'backup.json'
        def fail():
            backup.write_text('private settings')
            history.record_backup(backup)
            raise RuntimeError('failure after backup')
        with patch('traceback.print_exc'):
            self.run_work(fail, on_error=lambda _exc: None)
        self.assertEqual(self.store.entries()[0]['status'], 'failed')
        self.assertEqual(self.store.entries()[0]['backups'], (str(backup),))

    def test_failed_export_is_recorded_and_releases_the_operation_slot(self):
        from minttweaks.modules.terminal import transfer
        document = {'format': 'minttweaks-terminal', 'schema_version': 1, 'tools': [],
                    'integrations': {}, 'preferences': {'schema_version': 1, 'shells': {}}}
        target = self.root / 'export.json'
        with patch.object(transfer.os, 'fsync', side_effect=OSError('disk full')), patch('traceback.print_exc'):
            self.run_work(lambda: transfer.write(self.ctx.runner, target, document), on_error=lambda _exc: None)
        row = self.store.entries()[0]
        self.assertEqual((row['module'], row['status'], row['backups']), ('terminal', 'failed', ()))
        self.assertFalse(target.exists())
        self.assertIsNone(self.ctx.operation_name)
        self.run_work(lambda: transfer.write(self.ctx.runner, target, document))
        self.assertEqual(self.store.entries()[0]['status'], 'completed')
        self.assertEqual(transfer.read(target), document)

    def test_read_only_diagnostics_and_busy_rejection_do_not_add_history(self):
        worker = self.ctx.run_async(lambda: 1)
        worker.join(1)
        self.assertEqual(self.store.entries(), [])
        with patch.object(self.ctx, 'run_async'):
            self.ctx.run_operation('First operation', lambda: None)
        with self.assertRaises(widgets.OperationBusy):
            self.ctx.run_operation('Rejected operation', lambda: None)
        self.assertEqual(self.store.entries(), [])

    def test_history_write_failure_does_not_cancel_the_operation(self):
        messages = []
        self.ctx.add_sink(lambda text, level: messages.append((text, level)))
        with patch.object(self.store, 'begin', side_effect=OSError('disk full')):
            work = Mock(return_value=True)
            self.run_work(work)
        work.assert_called_once()
        self.assertTrue(self.ctx.history_warning)
        self.assertIsNone(self.ctx.operation_name)
        self.assertTrue(any(level == 'warn' for _, level in messages))

    def test_backup_and_final_write_failures_keep_the_result_and_release_the_slot(self):
        completed = []
        with patch.object(self.store, 'add_backup', side_effect=OSError('disk full')), \
                patch.object(self.store, 'finish', side_effect=OSError('disk full')):
            self.run_work(lambda: (history.record_backup(self.root / 'backup.json'), True)[1],
                          on_done=completed.append)
        self.assertEqual(completed, [True])
        self.assertTrue(self.ctx.history_warning)
        self.assertIsNone(self.ctx.operation_name)

    def test_history_refresh_renders_entries_and_opens_the_original_module(self):
        self.run_work(lambda: True)
        page = HistoryPage(self.ctx)
        page._request = 1
        page._apply(self.store.entries(), 1)
        self.assertEqual(page.entries[0]['module'], 'terminal')
        window = Mock()
        with patch.object(page, 'get_toplevel', return_value=window):
            page._open_module('terminal')
        window.show_page.assert_called_once_with('terminal')

    def test_read_request_keeps_its_offset_if_page_changes_before_worker_starts(self):
        page = HistoryPage(self.ctx)
        page.offset = 50
        with patch.object(self.ctx, 'run_async') as run:
            page.refresh()
        page.offset = 100
        with patch.object(self.store, 'entries', return_value=[]) as read:
            run.call_args.args[0]()
        self.assertEqual(read.call_args.kwargs['offset'], 50)

    def test_page_passes_its_module(self):
        page = widgets.Page(self.ctx)
        worker = page.run_operation(lambda: Result('action', 0))
        worker.join(3)
        self.drain()
        self.assertEqual(self.store.entries()[0]['module'], 'page')

    def test_ui_failure_clears_old_rows_and_stale_requests_are_ignored(self):
        page = HistoryPage(self.ctx)
        page._request = 2
        summary = Mock()
        page.summary = summary
        page._apply([], 1)
        summary.set_text.assert_not_called()
        page.entries = [{'stale': True}]
        page._failed(None, 2)
        self.assertEqual(page.entries, [])
        self.assertIn('could not be read', summary.set_text.call_args.args[0])
