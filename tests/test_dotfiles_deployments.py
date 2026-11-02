"""Exercise backup/undo on real temporary files with a Stow process double."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.core.runner import Result
from minttweaks.modules.dotfiles import backend, deployments
from tests.fakes import FakeRunner


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root, self.target = self.base / 'repo', self.base / 'home'
        self.root.mkdir()
        self.target.mkdir()
        self.package = self.root / 'bash'
        self.package.mkdir()
        (self.package / '.bashrc').write_text('new configuration')
        self.original = self.target / '.bashrc'
        self.original.write_text('personal configuration')
        self.original.chmod(0o640)
        self.storage = self.base / 'backups'
        for patcher in (patch.object(deployments, 'backup_directory', return_value=self.storage),
                        patch.object(backend, '_check_resource_files')):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.runner = FakeRunner().add_callable(['stow'], self.stow)
        self.fail = False
        self.ignore = set()

    def stow(self, command):
        target = Path(next(arg[9:] for arg in command.argv if arg.startswith('--target=')))
        output = []
        for source in sorted(self.package.rglob('*')):
            if not source.is_file() or source.name in self.ignore:
                continue
            relative = str(source.relative_to(self.package))
            destination = target / relative
            if deployments._matches_link(destination, source):
                continue
            if os.path.lexists(destination):
                return Result(str(command), 1, stderr='conflict: ' + relative)
            output.append('LINK: ' + relative + ' => ' + os.path.relpath(source, destination.parent))
            if '--simulate' not in command.argv:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(os.path.relpath(source, destination.parent))
                if self.fail:
                    return Result(str(command), 1, stderr='stow failed after one link')
        return Result(str(command), 0, stdout='\n'.join(output))

    def preview(self):
        return deployments.preview_activation(self.runner, self.root, self.target, 'bash')

    def undo(self):
        plan = deployments.preview_undo(self.root, self.target, 'bash')
        return deployments.undo(self.runner, plan)

    def test_preview_lists_backup_without_writing_anything(self):
        plan = self.preview()
        self.assertEqual(plan.backups, ('.bashrc',))
        self.assertEqual(self.original.read_text(), 'personal configuration')
        self.assertFalse(self.storage.exists())
        self.assertTrue(all('--simulate' in call.argv for call in self.runner.calls))

    def test_activation_and_undo_restore_bytes_permissions_and_keep_backup(self):
        plan = self.preview()
        deployments.activate(self.runner, plan)
        self.assertTrue(self.original.is_symlink())
        self.assertEqual(self.original.read_text(), 'new configuration')
        journal = deployments.active_journal(self.root, self.target, 'bash')
        self.assertIsNotNone(journal)
        self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.storage.stat().st_mode & 0o777, 0o700)
        self.undo()
        self.assertFalse(self.original.is_symlink())
        self.assertEqual(self.original.read_text(), 'personal configuration')
        self.assertEqual(self.original.stat().st_mode & 0o777, 0o640)
        self.assertTrue(journal.exists())
        self.assertEqual(json.loads(journal.read_text())['status'], 'undone')
        self.assertIsNone(deployments.active_journal(self.root, self.target, 'bash'))
        self.assertEqual((self.package / '.bashrc').read_text(), 'new configuration')

    def test_no_previous_configuration_undo_only_removes_new_links(self):
        self.original.unlink()
        deployments.activate(self.runner, self.preview())
        self.undo()
        self.assertFalse(os.path.lexists(self.original))

    def test_existing_external_symbolic_link_is_backed_up_and_restored(self):
        self.original.unlink()
        self.original.symlink_to('../previous-config')
        deployments.activate(self.runner, self.preview())
        self.undo()
        self.assertTrue(self.original.is_symlink())
        self.assertEqual(os.readlink(self.original), '../previous-config')

    def test_failed_stow_restores_original_and_removes_partial_links(self):
        self.fail = True
        with self.assertRaisesRegex(ValueError, 'previous configuration was restored'):
            deployments.activate(self.runner, self.preview())
        self.assertFalse(self.original.is_symlink())
        self.assertEqual(self.original.read_text(), 'personal configuration')
        self.assertIsNone(deployments.active_journal(self.root, self.target, 'bash'))
        self.assertEqual(len(list(self.storage.glob('*.json'))), 1)

    def test_backup_failure_happens_before_original_is_removed(self):
        plan = self.preview()
        with patch.object(deployments, '_save', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                deployments.activate(self.runner, plan)
        self.assertEqual(self.original.read_text(), 'personal configuration')
        self.assertFalse(any('--simulate' not in call.argv for call in self.runner.calls))

    def test_target_change_after_preview_is_preserved(self):
        plan = self.preview()
        self.original.write_text('external edit')
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            deployments.activate(self.runner, plan)
        self.assertEqual(self.original.read_text(), 'external edit')
        self.assertFalse(self.storage.exists())

    def test_undo_refuses_external_changes_before_removing_other_links(self):
        (self.package / '.profile').write_text('new profile')
        deployments.activate(self.runner, self.preview())
        self.original.unlink()
        self.original.write_text('manual replacement')
        with self.assertRaisesRegex(ValueError, 'preserved'):
            self.undo()
        self.assertEqual(self.original.read_text(), 'manual replacement')
        self.assertTrue((self.target / '.profile').is_symlink())
        self.assertIsNotNone(deployments.active_journal(self.root, self.target, 'bash'))

    def test_nested_files_are_restored_and_shared_directories_kept(self):
        folder = self.package / '.config' / 'app'
        folder.mkdir(parents=True)
        (folder / 'settings').write_text('new')
        (self.target / '.config').mkdir()
        unrelated = self.target / '.config' / 'unrelated'
        unrelated.write_text('keep')
        deployments.activate(self.runner, self.preview())
        self.undo()
        self.assertEqual(unrelated.read_text(), 'keep')
        self.assertTrue((self.target / '.config').is_dir())
        self.assertFalse(os.path.lexists(self.target / '.config' / 'app' / 'settings'))

    def test_stow_ignored_conflicts_are_never_removed_or_backed_up(self):
        (self.package / 'README').write_text('docs')
        (self.target / 'README').write_text('personal docs')
        self.ignore.add('README')
        plan = self.preview()
        self.assertEqual(plan.backups, ('.bashrc',))
        deployments.activate(self.runner, plan)
        self.assertEqual((self.target / 'README').read_text(), 'personal docs')
        self.undo()
        self.assertEqual((self.target / 'README').read_text(), 'personal docs')

    def test_existing_correct_links_are_preserved_by_managed_undo(self):
        (self.package / '.profile').write_text('profile')
        existing = self.target / '.profile'
        existing.symlink_to(self.package / '.profile')
        deployments.activate(self.runner, self.preview())
        self.undo()
        self.assertTrue(existing.is_symlink())
        self.assertEqual(existing.read_text(), 'profile')

    def test_unmanaged_stow_can_be_undone_without_touching_regular_files(self):
        self.original.unlink()
        self.original.symlink_to(self.package / '.bashrc')
        (self.package / '.profile').write_text('source')
        (self.target / '.profile').write_text('manual')
        self.undo()
        self.assertFalse(os.path.lexists(self.original))
        self.assertEqual((self.target / '.profile').read_text(), 'manual')
        self.assertFalse(self.storage.exists())

    def test_dry_run_does_not_create_backups_or_remove_links(self):
        plan = self.preview()
        self.runner.dry_run = True
        calls = len(self.runner.calls)
        deployments.activate(self.runner, plan)
        self.assertEqual(len(self.runner.calls), calls)
        self.assertFalse(self.storage.exists())
        self.assertEqual(self.original.read_text(), 'personal configuration')
        self.runner.dry_run = False
        deployments.activate(self.runner, plan)
        undo = deployments.preview_undo(self.root, self.target, 'bash')
        self.runner.dry_run = True
        deployments.undo(self.runner, undo)
        self.assertTrue(self.original.is_symlink())

    def test_unsafe_target_parent_and_backup_symlinks_are_refused(self):
        folder = self.package / '.config'
        folder.mkdir()
        (folder / 'settings').write_text('new')
        (self.target / '.config').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, 'Unsafe target'):
            self.preview()
        (self.target / '.config').unlink()
        self.storage.symlink_to(self.target)
        with self.assertRaisesRegex(ValueError, 'Unsafe backup'):
            self.preview()

    def test_journal_traversal_is_refused(self):
        deployments.activate(self.runner, self.preview())
        path = deployments.active_journal(self.root, self.target, 'bash')
        data = json.loads(path.read_text())
        data['records'][0]['relative'] = '../outside'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Invalid dotfiles backup'):
            self.undo()
        self.assertTrue(self.original.is_symlink())

    def test_undo_works_when_source_package_was_removed(self):
        deployments.activate(self.runner, self.preview())
        (self.package / '.bashrc').unlink()
        self.package.rmdir()
        self.undo()
        self.assertEqual(self.original.read_text(), 'personal configuration')

    def test_repeated_activation_is_refused_until_undo(self):
        deployments.activate(self.runner, self.preview())
        with self.assertRaisesRegex(ValueError, 'already managed'):
            self.preview()
        self.undo()
        self.assertEqual(self.preview().backups, ('.bashrc',))

    def test_external_change_after_undo_preview_is_preserved(self):
        deployments.activate(self.runner, self.preview())
        plan = deployments.preview_undo(self.root, self.target, 'bash')
        self.original.unlink()
        self.original.write_text('new manual file')
        with self.assertRaisesRegex(ValueError, 'preserved'):
            deployments.undo(self.runner, plan)
        self.assertEqual(self.original.read_text(), 'new manual file')

    def test_analysis_keeps_undo_available_after_package_removal(self):
        deployments.activate(self.runner, self.preview())
        (self.package / '.bashrc').unlink()
        self.package.rmdir()
        packages = backend.analyse(self.root, self.target)
        self.assertEqual(len(packages), 1)
        self.assertTrue(packages[0].managed)
        self.assertEqual(packages[0].name, 'bash')

    def test_backup_overlap_is_rejected_before_modifying_existing_files(self):
        self.storage.mkdir()
        self.original.unlink()
        # The backup store itself may not be replaced by a configuration link.
        with patch.object(deployments, 'backup_directory', return_value=self.target / '.bashrc'):
            with self.assertRaisesRegex(ValueError, 'overlaps'):
                deployments.activate(self.runner, self.preview())
        self.assertFalse(os.path.lexists(self.original))
