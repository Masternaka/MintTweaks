"""Configuration transactions run only against temporary directories."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.core import userfiles as files
from tests.fakes import FakeRunner


class UserFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.targets = {key: self.root / key for key in ('a', 'b')}
        self.backups = self.root / 'backups'
        self.runner = FakeRunner()
        self.targets['a'].write_bytes(b'aliases\n')
        self.targets['a'].chmod(0o640)

    def plan(self):
        return files.preview(self.targets, {'a': b'new\n', 'b': b'created\n'})

    def test_backup_round_trip_preserves_bytes_modes_and_absence(self):
        result = files.apply(self.runner, self.targets, self.plan(), self.backups)
        self.assertTrue(result.ok)
        self.assertEqual(result.backup.stat().st_mode & 0o777, 0o600)
        self.targets['a'].chmod(0o600)
        restore = files.restore_preview(self.targets, result.backup)
        restored = files.apply(self.runner, self.targets, restore, self.backups)
        self.assertTrue(restored.ok)
        self.assertNotEqual(result.backup, restored.backup)
        self.assertEqual(files.read_file(self.targets['a']), (b'aliases\n', 0o640))
        self.assertFalse(self.targets['b'].exists())

    def test_simulation_writes_neither_files_nor_backups(self):
        self.runner.dry_run = True
        result = files.apply(self.runner, self.targets, self.plan(), self.backups)
        self.assertTrue(result.simulated)
        self.assertEqual(self.targets['a'].read_bytes(), b'aliases\n')
        self.assertFalse(self.backups.exists())
        self.assertFalse(self.targets['b'].exists())

    def test_stale_preview_and_symlinks_are_refused(self):
        plan = self.plan()
        self.targets['a'].write_bytes(b'external')
        with self.assertRaises(ValueError):
            files.apply(self.runner, self.targets, plan, self.backups)
        self.assertFalse(self.backups.exists())
        self.targets['b'].symlink_to(self.targets['a'])
        with self.assertRaises(ValueError):
            self.plan()

    def test_backup_failure_prevents_every_write(self):
        with patch.object(files, 'save_backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                files.apply(self.runner, self.targets, self.plan(), self.backups)
        self.assertEqual(self.targets['a'].read_bytes(), b'aliases\n')
        self.assertFalse(self.targets['b'].exists())

    def test_partial_failure_rolls_back_prior_write(self):
        original = files.atomic_write
        def write(path, data, mode=0o600):
            self.assertEqual(len(list(self.backups.glob('*.json'))), 1)
            if path == self.targets['b']:
                raise OSError('disk full')
            original(path, data, mode)
        with patch.object(files, 'atomic_write', side_effect=write):
            result = files.apply(self.runner, self.targets, self.plan(), self.backups)
        self.assertFalse(result.ok)
        self.assertEqual(files.read_file(self.targets['a']), (b'aliases\n', 0o640))
        self.assertTrue(result.backup.exists())

    def test_external_change_during_failure_is_preserved_and_reported(self):
        original = files.atomic_write
        def write(path, data, mode=0o600):
            if path == self.targets['b']:
                self.targets['a'].write_bytes(b'external edit')
                raise OSError('disk full')
            original(path, data, mode)
        with patch.object(files, 'atomic_write', side_effect=write):
            result = files.apply(self.runner, self.targets, self.plan(), self.backups)
        self.assertFalse(result.ok)
        self.assertIn('a', result.errors)
        self.assertEqual(self.targets['a'].read_bytes(), b'external edit')

    def test_foreign_paths_corrupt_contents_and_unknown_slots_are_refused(self):
        result = files.apply(self.runner, self.targets, self.plan(), self.backups)
        original = json.loads(result.backup.read_text())
        for key, value in [('path', '/etc/passwd'), ('before', '!!'), ('slot', 'unknown'), ('mode', -1)]:
            payload = json.loads(json.dumps(original))
            payload['files'][0][key] = value
            result.backup.write_text(json.dumps(payload))
            with self.subTest(key=key), self.assertRaises((ValueError, KeyError)):
                files.restore_preview(self.targets, result.backup)

    def test_permission_only_restoration_is_not_discarded(self):
        result = files.apply(self.runner, self.targets, self.plan(), self.backups)
        self.targets['a'].write_bytes(b'aliases\n')
        self.targets['a'].chmod(0o600)
        plan = files.restore_preview(self.targets, result.backup)
        self.assertIn('a', [change.slot for change in plan])
        self.assertTrue(files.apply(self.runner, self.targets, plan, self.backups).ok)
        self.assertEqual(self.targets['a'].stat().st_mode & 0o777, 0o640)
