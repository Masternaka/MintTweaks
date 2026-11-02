"""Dotfiles safety boundaries, plans and GTK confirmation flow."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from minttweaks.modules.dotfiles import backend
from minttweaks.modules.dotfiles import deployments
from tests.fakes import FakeRunner
from tests import fakegi
fakegi.install()
from minttweaks.modules.dotfiles.page import DotfilesPage
from minttweaks.ui.widgets import AppContext


class DotfilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root, self.target = base / 'repo', base / 'home'
        self.root.mkdir()
        self.target.mkdir()
        self.package = self.root / 'bash'
        self.package.mkdir()
        (self.package / '.bashrc').write_text('alias ll="ls -l"\n')
        self.runner = FakeRunner().add(['stow'], stdout='LINK: .bashrc => ../repo/bash/.bashrc')
        resource = patch.object(backend, '_check_resource_files')
        resource.start()
        self.addCleanup(resource.stop)

    def preview(self):
        return backend.preview_stow(self.runner, self.root, self.target, 'bash')

    def test_analysis_finds_packages_and_existing_links(self):
        (self.root / '.git').mkdir()
        (self.root / 'docs').mkdir()
        (self.target / '.bashrc').symlink_to(self.package / '.bashrc')
        packages = backend.analyse(self.root, self.target)
        self.assertEqual([(p.name, p.files, p.linked, p.error) for p in packages], [('bash', 1, 1, '')])

    def test_conflict_preserves_existing_file_and_never_calls_stow(self):
        existing = self.target / '.bashrc'
        existing.write_text('personal data')
        with self.assertRaisesRegex(ValueError, 'Existing files'):
            self.preview()
        self.assertEqual(existing.read_text(), 'personal data')
        self.assertFalse(self.runner.calls)

    def test_source_symlink_is_refused(self):
        (self.package / 'external').symlink_to(self.target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Source symbolic links'):
            self.preview()
        self.assertFalse(self.runner.calls)

    def test_target_symlink_parent_is_refused(self):
        (self.package / '.config').mkdir()
        (self.package / '.config' / 'settings').write_text('test')
        (self.target / '.config').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe directories'):
            self.preview()
        self.assertFalse(self.runner.calls)

    def test_tree_and_conflicts_are_rechecked_before_apply(self):
        plan = self.preview()
        (self.package / '.bashrc').write_text('changed content')
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            backend.apply_stow(self.runner, plan)
        self.assertTrue(all('--simulate' in call.argv for call in self.runner.calls))

    def test_new_conflict_blocks_previously_confirmed_plan(self):
        plan = self.preview()
        (self.target / '.bashrc').write_text('preserve')
        with self.assertRaises(ValueError):
            backend.apply_stow(self.runner, plan)
        self.assertEqual(len(self.runner.calls), 1)

    def test_apply_uses_user_stow_without_adopt_or_folding(self):
        backend.apply_stow(self.runner, self.preview())
        call = self.runner.calls[-1]
        self.assertFalse(call.needs_root)
        self.assertIn('--no-folding', call.argv)
        self.assertIn('--stow', call.argv)
        self.assertNotIn('--simulate', call.argv)
        self.assertNotIn('--adopt', call.argv)

    def test_simulation_performs_no_mutating_commands(self):
        plan = self.preview()
        self.runner.calls.clear()
        self.runner.dry_run = True
        backend.apply_stow(self.runner, plan)
        backend.clone(self.runner, 'https://github.com/example/dotfiles.git', self.root / 'new')
        backend.install_dependencies(self.runner, backend.DependencyPlan(('stow',), (), ''))
        self.assertFalse(self.runner.calls)
        self.assertFalse((self.target / '.bashrc').exists())
        self.assertFalse((self.root / 'new').exists())

    def test_dotfiles_option_maps_names_and_rejects_parent_traversal(self):
        (self.package / '.bashrc').rename(self.package / 'dot-bashrc')
        (self.target / '.bashrc').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'Existing files'):
            backend.preview_stow(self.runner, self.root, self.target, 'bash', True)
        (self.package / 'dot-.').write_text('invalid')
        with self.assertRaisesRegex(ValueError, 'Invalid dot-'):
            backend.preview_stow(self.runner, self.root, self.target, 'bash', True)

    def test_package_traversal_and_target_inside_repository_are_refused(self):
        for name in ['../home', '--adopt', 'bash/..']:
            with self.assertRaises(ValueError):
                backend.preview_stow(self.runner, self.root, self.target, name)
        with self.assertRaises(ValueError):
            backend.preview_stow(self.runner, self.root, self.package, 'bash')

    def test_clone_validates_url_and_never_reuses_destination(self):
        for url in ['--upload-pack=evil', 'file:///repo', 'https://token@github.com/a/b', 'https://evil.test/a/b']:
            with self.assertRaises(ValueError):
                backend.clone_command(url, self.root / 'new')
        with self.assertRaises(ValueError):
            backend.clone_command('git@github.com:example/dotfiles.git', self.root)
        command = backend.clone_command('https://github.com/example/my.dotfiles.git', self.root / 'with spaces')
        self.assertIn('--no-recurse-submodules', command.argv)
        self.assertEqual(command.argv[-1], str(self.root.resolve() / 'with spaces'))

    def test_apt_removals_and_changed_plans_are_refused(self):
        runner = FakeRunner().add(['apt-get'], stdout='Remv other [1.0]')
        with self.assertRaisesRegex(ValueError, 'removals'):
            backend.preview_dependencies(runner)
        runner = FakeRunner().add(['apt-get'], stdout='Inst stow (2.4)')
        plan = backend.DependencyPlan(('git', 'stow'), ('Inst stow (2.3)',), '')
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            backend.install_dependencies(runner, plan)
        self.assertFalse(any(call.needs_root for call in runner.calls))

    def test_failed_stow_is_reported(self):
        plan = self.preview()
        command = backend.stow_command(plan.root, plan.target, plan.name, simulate=False)
        self.runner.add(command.argv, returncode=1, stderr='conflict')
        with self.assertRaisesRegex(ValueError, 'conflict'):
            backend.apply_stow(self.runner, plan)


class DotfilesPageTests(unittest.TestCase):
    def setUp(self):
        self.page = DotfilesPage(AppContext(FakeRunner()))

    def test_cancelled_stow_does_not_mutate(self):
        plan = deployments.ActivationPlan(Path('/repo'), Path('/target'), 'bash', False, (), 'LINK .bashrc')
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm, patch.object(self.page, '_start') as start:
            self.page._confirm_stow(plan)
        start.assert_not_called()
        self.assertIn('LINK .bashrc', '\n'.join(confirm.call_args.args[2]))

    def test_confirmed_stow_uses_shared_operation_slot(self):
        plan = deployments.ActivationPlan(Path('/repo'), Path('/target'), 'bash', False, (), 'LINK .bashrc')
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), patch.object(self.page, 'run_operation') as operation:
            self.page._confirm_stow(plan)
        operation.assert_called_once()

    def test_busy_global_operation_is_visible_and_releases_controls(self):
        ctx = self.page.ctx
        with patch.object(ctx, 'run_async'):
            ctx.run_operation('Other operation', lambda: None)
        self.page.error = Mock()
        self.page._start(lambda: None, self.page._done, mutation=True)
        self.page.error.assert_called_once()
        self.assertFalse(self.page._busy)

    def test_cancelling_dependency_install_does_not_mutate(self):
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), patch.object(self.page, '_start') as start:
            self.page._confirm_install(backend.DependencyPlan(('git', 'stow'), (), 'APT preview'))
        start.assert_not_called()

    def test_cancelled_undo_never_removes_links(self):
        plan = deployments.UndoPlan(Path('/repo'), Path('/target'), 'bash', False,
                                    ({'relative': '.bashrc', 'source': '/repo/bash/.bashrc', 'before': None},))
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm, patch.object(self.page, '_start') as start:
            self.page._confirm_undo(plan)
        start.assert_not_called()
        self.assertIn('/target/.bashrc', confirm.call_args.args[2])

    def test_confirmed_undo_uses_shared_operation_slot(self):
        plan = deployments.UndoPlan(Path('/repo'), Path('/target'), 'bash', False, ())
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), patch.object(self.page, 'run_operation') as operation:
            self.page._confirm_undo(plan)
        operation.assert_called_once()


class ResourceFilesTests(unittest.TestCase):
    def test_implicit_resource_files_are_refused_without_modifying_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home, cwd = base / 'home', base / 'cwd'
            home.mkdir()
            cwd.mkdir()
            for folder in (home, cwd):
                options = folder / '.stowrc'
                options.write_text('--adopt\n')
                with patch.object(Path, 'home', return_value=home), patch.object(Path, 'cwd', return_value=cwd):
                    with self.assertRaisesRegex(ValueError, 'automatically'):
                        backend._check_resource_files()
                self.assertEqual(options.read_text(), '--adopt\n')
                options.unlink()
