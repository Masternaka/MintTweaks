"""Real temporary theme copies, backups and GTK confirmation contracts."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from minttweaks.modules.cinnamon import themes, backend
from tests.fakes import FakeRunner
from tests.test_cinnamon_apply import SettingsRunner
from tests import fakegi
fakegi.install()
from minttweaks.modules.cinnamon.page import CinnamonPage
from minttweaks.ui.widgets import AppContext


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / 'repository with spaces'
        self.destination = self.base / 'themes'
        self.source = self.repo / 'dist' / 'Catppuccin-Mocha'
        (self.source / 'cinnamon').mkdir(parents=True)
        (self.source / 'cinnamon' / 'cinnamon.css').write_text('stage { color: #cdd6f4; }')
        (self.source / 'index.theme').write_text('[Desktop Entry]\nName=Catppuccin Mocha\n')
        self.runner = FakeRunner()
        patcher = patch.object(themes, 'themes_directory', return_value=self.destination)
        patcher.start()
        self.addCleanup(patcher.stop)

    def preview(self):
        return themes.preview_install(self.repo, 'Mocha')

    def test_preview_never_creates_installation_directories(self):
        plan = self.preview()
        self.assertIsNone(plan.backup)
        self.assertFalse(self.destination.exists())

    def test_installs_generated_files_without_running_scripts_or_applying_settings(self):
        plan = self.preview()
        message = themes.install(self.runner, plan)
        self.assertIn('Theme installed', message)
        self.assertEqual(themes.tree_snapshot(plan.target), plan.source_tree)
        self.assertEqual(themes.tree_snapshot(plan.source), plan.source_tree)
        self.assertFalse(self.runner.calls)

    def test_existing_theme_is_preserved_in_dated_backup(self):
        target = self.destination / 'Catppuccin-Mocha'
        target.mkdir(parents=True)
        (target / 'personal.css').write_text('old personal version')
        plan = self.preview()
        themes.install(self.runner, plan)
        self.assertIn('.minttweaks-backups', str(plan.backup))
        self.assertEqual((plan.backup / 'personal.css').read_text(), 'old personal version')
        self.assertEqual(themes.tree_snapshot(target), plan.source_tree)
        self.assertFalse((target / 'personal.css').exists())

    def test_source_change_after_confirmation_blocks_installation(self):
        plan = self.preview()
        (self.source / 'index.theme').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'files changed'):
            themes.install(self.runner, plan)
        self.assertFalse(self.destination.exists())

    def test_destination_change_after_confirmation_is_preserved(self):
        plan = self.preview()
        plan.target.mkdir(parents=True)
        (plan.target / 'manual').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'files changed'):
            themes.install(self.runner, plan)
        self.assertEqual((plan.target / 'manual').read_text(), 'keep')

    def test_failed_copy_does_not_move_the_existing_theme(self):
        target = self.destination / 'Catppuccin-Mocha'
        target.mkdir(parents=True)
        (target / 'manual').write_text('keep')
        plan = self.preview()
        with patch.object(themes.shutil, 'copytree', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                themes.install(self.runner, plan)
        self.assertEqual((target / 'manual').read_text(), 'keep')
        self.assertFalse(plan.backup.exists())

    def test_failed_publish_restores_moved_previous_version(self):
        target = self.destination / 'Catppuccin-Mocha'
        target.mkdir(parents=True)
        (target / 'manual').write_text('keep')
        plan = self.preview()
        original = Path.rename
        def fail_publish(path, destination):
            if path.parent.name.startswith('.mtk-theme-'):
                raise OSError('publish failed')
            return original(path, destination)
        with patch.object(Path, 'rename', fail_publish):
            with self.assertRaisesRegex(ValueError, 'publish failed'):
                themes.install(self.runner, plan)
        self.assertEqual((target / 'manual').read_text(), 'keep')
        self.assertFalse(plan.backup.exists())

    def test_symlink_source_destination_and_backup_directories_are_refused(self):
        (self.source / 'external').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError, 'symbolic links'):
            self.preview()
        (self.source / 'external').unlink()
        self.destination.symlink_to(self.repo)
        with self.assertRaisesRegex(ValueError, 'ordinary directories'):
            self.preview()
        self.destination.unlink()
        target = self.destination / 'Catppuccin-Mocha'
        target.mkdir(parents=True)
        (self.destination / '.minttweaks-backups').symlink_to(self.repo)
        with self.assertRaisesRegex(ValueError, 'ordinary directories'):
            self.preview()

    def test_missing_distribution_and_invalid_variants_are_refused(self):
        for variant in ('../Mocha', '--adopt', 'Unknown'):
            with self.assertRaises(ValueError):
                themes.preview_install(self.repo, variant)
        (self.source / 'index.theme').unlink()
        with self.assertRaisesRegex(ValueError, 'complete generated'):
            self.preview()

    def test_clone_uses_fixed_repository_and_refuses_existing_destinations(self):
        destination = self.base / 'new clone'
        command = themes.clone_command(destination)
        self.assertIn(themes.REPOSITORY, command.argv)
        self.assertEqual(command.argv[-1], str(destination))
        self.assertIn('--no-recurse-submodules', command.argv)
        self.assertFalse(command.needs_root)
        with self.assertRaises(ValueError):
            themes.clone_command(self.repo)

    def test_clone_failure_has_a_visible_error(self):
        self.runner.add(['git'], returncode=127, stderr='Git is not installed')
        with self.assertRaisesRegex(ValueError, 'Git is not installed'):
            themes.clone(self.runner, self.base / 'new')

    def test_dry_run_changes_neither_themes_backups_nor_clone(self):
        plan = self.preview()
        self.runner.dry_run = True
        themes.install(self.runner, plan)
        themes.clone(self.runner, self.base / 'new')
        self.assertFalse(self.destination.exists())
        self.assertFalse((self.base / 'new').exists())
        self.assertFalse(self.runner.calls)

    def test_apply_changes_only_the_desktop_theme_and_uses_existing_backup_flow(self):
        themes.install(self.runner, self.preview())
        runner = SettingsRunner()
        plan = themes.preview_apply(runner, 'Mocha')
        self.assertEqual([setting.id for setting in plan.changes], ['org.cinnamon.theme/name'])
        outcome = backend.apply_profile(runner, plan, backup_directory=self.base / 'appearance-backups')
        self.assertTrue(outcome.ok)
        self.assertIsNotNone(outcome.backup)
        self.assertEqual(runner.values['org.cinnamon.theme/name'], 'Catppuccin-Mocha')
        for setting in backend.SETTINGS:
            if setting.id != 'org.cinnamon.theme/name':
                self.assertEqual(runner.values[setting.id], plan.before.values[setting.id])

    def test_uninstalled_theme_cannot_be_applied(self):
        with self.assertRaisesRegex(ValueError, 'Install this'):
            themes.preview_apply(self.runner, 'Mocha')


class ThemePageTests(unittest.TestCase):
    def setUp(self):
        self.page = CinnamonPage(AppContext(FakeRunner()))

    def test_cancelled_installation_does_not_start_mutation(self):
        plan = themes.InstallPlan(Path('/source'), Path('/themes/Catppuccin-Mocha'), (), None)
        self.page._saving = True
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), patch.object(self.page, 'run_operation') as run:
            self.page._confirm_theme_install(plan)
        run.assert_not_called()
        self.assertFalse(self.page._saving)

    def test_installation_preview_contains_backup_destination(self):
        plan = themes.InstallPlan(Path('/source'), Path('/themes/Catppuccin-Mocha'), (), (), Path('/backup/Mocha'))
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm:
            self.page._confirm_theme_install(plan)
        self.assertIn('/backup/Mocha', '\n'.join(confirm.call_args.args[2]))

    def test_busy_operation_refuses_theme_install_and_releases_controls(self):
        with patch.object(self.page.ctx, 'run_async'):
            self.page.ctx.run_operation('Other operation', lambda: None)
        self.page.error = Mock()
        self.page._theme_start(lambda: None, self.page._theme_done, mutation=True)
        self.page.error.assert_called_once()
        self.assertFalse(self.page._saving)

    def test_cancelled_clone_never_runs_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.page.theme_repository.get_text = Mock(return_value=str(Path(tmp).resolve() / 'clone'))
            with patch.object(self.page, 'confirm', return_value=False), patch.object(self.page, '_theme_start') as start:
                self.page._clone_theme()
            start.assert_not_called()
