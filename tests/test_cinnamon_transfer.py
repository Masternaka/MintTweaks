"""Portable profile values are additive; import/export never apply GSettings."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

from minttweaks.modules.cinnamon import backend, transfer
from tests.fakes import FakeRunner
from tests import fakegi

fakegi.install()
from minttweaks.modules.cinnamon.page import CinnamonPage
from minttweaks.ui.widgets import AppContext


def profile():
    values = {setting.id: 'Thème d’été' for setting in backend.SETTINGS}
    values[backend.SETTINGS[-1].id] = ''
    return backend.Profile(uuid.uuid4().hex, '../Bureau été', '2026-11-03T10:00:00-05:00', values)


class ProfileTransferTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.directory = self.root / 'profiles'
        self.source = self.root / 'any-name.json'
        self.profile = profile()
        self.export = transfer.preview_export(self.profile)
        self.source.write_text(self.export.text)
        self.runner = FakeRunner()

    def preview(self):
        return transfer.preview_import(self.runner, self.source, self.directory)

    def test_preview_preserves_unicode_empty_values_and_original_capture_time(self):
        plan = self.preview()
        self.assertEqual(plan.profile, self.profile)
        self.assertEqual(plan.directory, self.directory)
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.runner.calls)
        self.assertNotIn('../Bureau', self.export.filename)

    def test_import_adds_a_new_identifier_without_applying_settings(self):
        original = backend.store_snapshot(backend.Snapshot(self.profile.captured_at, self.profile.settings),
                                          self.profile.name, self.directory)
        existing = self.directory / (original.id + '.json')
        before = existing.read_bytes()
        imported = transfer.import_profile(self.runner, self.preview())
        self.assertNotIn(imported.id, (self.profile.id, original.id))
        self.assertEqual(imported.settings, self.profile.settings)
        self.assertEqual(imported.name, self.profile.name)
        self.assertEqual(imported.captured_at, self.profile.captured_at)
        self.assertEqual(existing.read_bytes(), before)
        self.assertEqual(len(backend.list_profiles(self.directory).profiles), 2)
        self.assertEqual((self.directory / (imported.id + '.json')).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertFalse(self.runner.calls)

    def test_export_writes_exact_preview_bytes_without_querying_settings(self):
        destination = self.root / 'portable.json'
        transfer.export_profile(self.runner, self.export, destination)
        self.assertEqual(destination.read_bytes(), self.export.text.encode('utf-8'))
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.runner.calls)

    def test_existing_export_files_and_symlinks_are_not_replaced(self):
        broken = self.root / 'linked.json'
        broken.symlink_to(self.root / 'missing')
        before = self.source.read_bytes()
        for destination in (self.source, broken):
            with self.assertRaises(backend.ProfileError):
                transfer.export_profile(self.runner, self.export, destination)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(broken.is_symlink())
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_failed_export_leaves_no_partial_destination(self):
        target = self.root / 'portable.json'
        with patch.object(transfer.os, 'fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                transfer.export_profile(self.runner, self.export, target)
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.iterdir()), [self.source])

    def test_export_plan_mutation_requires_a_new_preview(self):
        self.export.profile.settings[backend.SETTINGS[0].id] = 'Changed after review'
        with self.assertRaises(backend.ProfileError):
            transfer.export_profile(self.runner, self.export, self.root / 'portable.json')
        self.assertEqual(list(self.root.iterdir()), [self.source])

    def test_source_byte_changes_require_a_new_preview(self):
        plan = self.preview()
        self.source.write_text(self.export.text + '\n')
        with self.assertRaisesRegex(backend.ProfileError, 'changed after its preview'):
            transfer.import_profile(self.runner, plan)
        self.assertFalse(self.directory.exists())

    def test_mutated_import_plan_is_not_written(self):
        plan = self.preview()
        plan.profile.settings[backend.SETTINGS[0].id] = 'Unreviewed'
        with self.assertRaises(backend.ProfileError):
            transfer.import_profile(self.runner, plan)
        self.assertFalse(self.directory.exists())

    def test_invalid_incomplete_duplicate_and_future_json_are_preserved(self):
        valid = json.loads(self.export.text)
        future = dict(valid, schema_version=99)
        incomplete = dict(valid, settings={})
        injected = dict(valid, command='must never run')
        for raw in ('{broken', '[]', '{"schema_version": 1, "schema_version": 2}',
                    json.dumps(future), json.dumps(incomplete), json.dumps(injected)):
            self.source.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(backend.ProfileError):
                self.preview()
            self.assertEqual(self.source.read_text(), raw)
            self.assertFalse(self.directory.exists())
        self.assertFalse(self.runner.calls)

    def test_oversized_source_is_preserved(self):
        raw = b' ' * (backend.MAX_FILE_BYTES + 1)
        self.source.write_bytes(raw)
        with self.assertRaises(backend.ProfileError):
            self.preview()
        self.assertEqual(self.source.read_bytes(), raw)

    def test_source_symlink_and_special_file_are_refused(self):
        link = self.root / 'link.json'
        link.symlink_to(self.source)
        with self.assertRaises(OSError):
            transfer.preview_import(self.runner, link, self.directory)
        fifo = self.root / 'fifo'
        transfer.os.mkfifo(fifo)
        with self.assertRaises(backend.ProfileError):
            transfer.preview_import(self.runner, fifo, self.directory)
        self.assertFalse(self.directory.exists())

    def test_directory_replaced_with_symlink_after_preview_is_refused(self):
        plan = self.preview()
        other = self.root / 'other'
        other.mkdir()
        self.directory.symlink_to(other)
        with self.assertRaises(backend.ProfileError):
            transfer.import_profile(self.runner, plan)
        self.assertEqual(list(other.iterdir()), [])
        self.assertTrue(self.directory.is_symlink())

    def test_identifier_collision_preserves_the_existing_profile(self):
        fixed = uuid.uuid4()
        with patch.object(backend.uuid, 'uuid4', return_value=fixed):
            old = backend.store_snapshot(backend.Snapshot(self.profile.captured_at, self.profile.settings), 'Keep this', self.directory)
            existing = self.directory / (old.id + '.json')
            before = existing.read_bytes()
            with self.assertRaises(FileExistsError):
                transfer.import_profile(self.runner, self.preview())
        self.assertEqual(existing.read_bytes(), before)
        self.assertEqual(list(self.directory.iterdir()), [existing])

    def test_simulation_does_not_read_imports_or_write_any_profile(self):
        plan = self.preview()
        self.runner.dry_run = True
        with patch.object(transfer, '_read_profile') as read:
            with self.assertRaises(backend.ProfileError):
                self.preview()
            self.assertIsNone(transfer.import_profile(self.runner, plan))
            self.assertIsNone(transfer.export_profile(self.runner, self.export, self.root / 'portable.json'))
        read.assert_not_called()
        self.assertFalse(self.directory.exists())
        self.assertEqual(list(self.root.iterdir()), [self.source])

    def test_failed_readback_preserves_the_new_file_for_manual_review(self):
        plan = self.preview()
        read = transfer._read_profile
        def fail_readback(source):
            if source.parent == self.directory:
                raise OSError('read-back unavailable')
            return read(source)
        with patch.object(transfer, '_read_profile', side_effect=fail_readback):
            with self.assertRaisesRegex(backend.ProfileError, 'saved but could not be verified'):
                transfer.import_profile(self.runner, plan)
        self.assertEqual(len(list(self.directory.glob('*.json'))), 1)
        self.assertEqual(self.source.read_text(), self.export.text)
        self.assertFalse(self.runner.calls)


class ProfileTransferPageTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.context = AppContext(self.runner)
        self.page = CinnamonPage(self.context)
        self.profile = profile()
        self.page.profiles = {self.profile.id: self.profile}
        self.page.profile_combo.get_active_id = Mock(return_value=self.profile.id)

    def import_plan(self):
        return transfer.ImportPlan(Path('/source.json'), 'reviewed', self.profile, Path('/profiles'))

    def test_transfers_are_available_without_cinnamon_settings(self):
        self.assertIsNone(self.page.snapshot)
        with patch.object(self.page.export_profile_button, 'set_sensitive') as export, \
                patch.object(self.page.import_profile_button, 'set_sensitive') as import_:
            self.page._update_actions()
        export.assert_called_with(True)
        import_.assert_called_with(True)

    def test_cancelled_export_preview_never_opens_the_file_chooser_or_writes(self):
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), \
                patch.object(self.page, '_choose_profile_file') as choose, \
                patch.object(self.page, 'run_operation') as run:
            self.page._export_profile()
        choose.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.page._saving)

    def test_cancelled_export_file_chooser_never_writes(self):
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), \
                patch.object(self.page, '_choose_profile_file', return_value=None), \
                patch.object(self.page, 'run_operation') as run:
            self.page._export_profile()
        run.assert_not_called()
        self.assertFalse(self.page._saving)

    def test_import_confirmation_shows_all_values_and_never_applies(self):
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm, \
                patch.object(self.page, 'run_operation') as run, patch.object(backend, 'apply_profile') as apply:
            self.page._confirm_profile_import(self.import_plan())
        text = '\n'.join(confirm.call_args.args[2])
        for setting in backend.SETTINGS:
            self.assertIn(setting.title, text)
        self.assertIn('/profiles', text)
        run.assert_not_called()
        apply.assert_not_called()
        self.assertFalse(self.page._saving)

    def test_busy_operation_refuses_import_and_restores_controls(self):
        with patch.object(self.context, 'run_async'):
            self.context.run_operation('Another operation', lambda: None)
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), \
                patch.object(transfer, 'import_profile') as import_, patch.object(self.page, 'error') as error:
            self.page._confirm_profile_import(self.import_plan())
        import_.assert_not_called()
        error.assert_called_once()
        self.assertFalse(self.page._saving)

    def test_imported_profile_is_selected_after_catalog_refresh(self):
        imported = replace(self.profile, id=uuid.uuid4().hex)
        snapshot = backend.Snapshot(backend.timestamp(), {}, {'setting': 'unavailable'})
        with patch.object(self.page, 'refresh') as refresh:
            self.page._profile_imported(imported)
        refresh.assert_called_once()
        with patch.object(self.page.profile_combo, 'set_active_id') as select:
            self.page._apply_state((snapshot, backend.Catalog([self.profile, imported]), ''))
        select.assert_called_with(imported.id)
        self.assertIsNone(self.page._imported_profile_id)
        self.assertFalse(self.runner.calls)

    def test_simulation_does_not_open_transfer_dialogs(self):
        self.runner.dry_run = True
        with patch.object(self.page, '_choose_profile_file') as choose, \
                patch('minttweaks.ui.widgets.confirm_list') as confirm:
            self.page._export_profile()
            self.page._import_profile()
        choose.assert_not_called()
        confirm.assert_not_called()

    def test_transfer_error_preserves_the_current_appearance_snapshot(self):
        snapshot = backend.Snapshot(self.profile.captured_at, dict(self.profile.settings))
        self.page.snapshot = snapshot
        self.page._saving = True
        with patch.object(self.page, 'error'):
            self.page._transfer_failed(OSError('disk full'))
        self.assertIs(self.page.snapshot, snapshot)
        self.assertFalse(self.page._saving)
