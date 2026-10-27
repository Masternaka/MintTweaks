"""Offline terminal integration; no user startup file or account is touched."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.core import userfiles
from minttweaks.core.runner import Result
from minttweaks.modules.terminal import backend as b
from tests.fakes import FakeRunner
from tests.test_software import BrowserRunner


class TerminalPackageTests(unittest.TestCase):
    def setUp(self):
        self.runner = BrowserRunner()
        self.runner.versions = {entry.package: '1.2.3' for entry in b.CATALOG}
        self.runner.origins = {entry.package: ['https://example.invalid/mint'] for entry in b.CATALOG}
        self.runner.suites = {entry.package: 'stable/main' for entry in b.CATALOG}
        p = patch.object(b.shutil, 'which', return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_selected_tools_are_version_pinned_and_verified(self):
        plan = b.preview_install(self.runner, ['kitty', 'fish'])
        self.assertTrue(all(not call.needs_root for call in self.runner.calls))
        b.install(self.runner, plan)
        self.assertEqual(self.runner.installed, {'kitty': '1.2.3', 'fish': '1.2.3'})
        command = next(call for call in self.runner.calls if call.needs_root)
        self.assertIn('--no-remove', command.argv)
        self.assertIn('kitty=1.2.3', command.argv)

    def test_removals_missing_candidates_and_unknown_tools_are_refused(self):
        for selected in ([], ['arbitrary-package'], ['kitty', 'kitty']):
            with self.assertRaises(ValueError):
                b.preview_install(self.runner, selected)
        self.assertFalse(self.runner.calls)
        self.runner.extra_operations = ['Remv mint-meta [1]']
        with self.assertRaises(ValueError):
            b.preview_install(self.runner, ['kitty'])
        self.runner.extra_operations = []
        self.runner.versions['starship'] = '(none)'
        self.assertTrue(b.tool_state(self.runner, 'starship').error)

    def test_changed_candidate_or_dependencies_require_new_preview(self):
        plan = b.preview_install(self.runner, ['kitty'])
        self.runner.versions['kitty'] = '2.0'
        with self.assertRaises(ValueError):
            b.install(self.runner, plan)
        self.assertFalse(self.runner.installed)
        self.runner.versions['kitty'] = '1.2.3'
        self.runner.extra_operations = ['Inst dependency (1 source [amd64])']
        with self.assertRaises(ValueError):
            b.install(self.runner, plan)

    def test_command_success_without_package_is_not_success(self):
        self.runner.keep_absent = True
        plan = b.preview_install(self.runner, ['kitty'])
        with self.assertRaises(ValueError):
            b.install(self.runner, plan)

    def test_simulation_runs_no_privileged_command(self):
        plan = b.preview_install(self.runner, ['kitty'])
        self.runner.dry_run = True
        before = len(self.runner.calls)
        b.install(self.runner, plan)
        self.assertEqual(len(self.runner.calls), before)

    def test_catalog_maps_display_names_to_real_packages_and_verifies_them(self):
        plan = b.preview_install(self.runner, ['fd', 'delta', 'ripgrep', 'neovim'])
        self.assertIn('fd-find=1.2.3', plan.specs)
        self.assertIn('git-delta=1.2.3', plan.specs)
        b.install(self.runner, plan)
        self.assertEqual(set(self.runner.installed), {'fd-find', 'git-delta', 'ripgrep', 'neovim'})

    def test_alternative_executable_names_are_detected_without_reinstallation(self):
        for tool, binary in [('bat', 'batcat'), ('fd', 'fdfind'), ('ripgrep', 'rg'), ('neovim', 'nvim')]:
            with self.subTest(tool=tool), patch.object(b.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name if name == binary else None):
                state = b.tool_state(self.runner, tool)
                self.assertTrue(state.installed)
                self.assertEqual(state.binary, '/usr/bin/' + binary)
                self.assertFalse(state.candidate)

    def test_plugins_are_detected_by_package_without_fictitious_executables(self):
        self.runner.installed['zsh-autosuggestions'] = '1.0'
        with patch.object(b.shutil, 'which') as which:
            state = b.tool_state(self.runner, 'zsh-autosuggestions')
        which.assert_not_called()
        self.assertTrue(state.installed)
        self.assertFalse(state.binary)
        self.assertIn('Managed activation', b.TOOL_BY_ID['zsh-autosuggestions'].description)

    def test_unknown_tool_state_is_refused_without_commands(self):
        with self.assertRaises(KeyError):
            b.tool_state(self.runner, 'unknown')
        self.assertFalse(self.runner.calls)


class TerminalFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mint terminal ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        p = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.home / '.config'), 'XDG_DATA_HOME': str(self.home / '.local/share'), 'ZDOTDIR': ''})
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(b.shutil, 'which', side_effect=lambda tool: '/usr/bin/' + tool)
        p.start()
        self.addCleanup(p.stop)
        self.runner = FakeRunner().add(['fc-list'], stdout='DejaVu Sans Mono\n')
        self.mapping = b.targets(self.home)

    def apply(self, changes):
        return userfiles.apply(self.runner, self.mapping, changes, self.home / 'backups')

    def test_prompt_preserves_aliases_is_idempotent_and_can_be_removed(self):
        for shell, slot in [('bash', 'bashrc'), ('zsh', 'zshrc'), ('fish', 'fishrc')]:
            with self.subTest(shell=shell):
                original = b'# aliases\nalias ll="ls -l"\n'
                self.mapping[slot].parent.mkdir(parents=True, exist_ok=True)
                self.mapping[slot].write_bytes(original)
                self.assertTrue(self.apply(b.prompt_preview(self.runner, shell, True, self.home)).ok)
                text = self.mapping[slot].read_text()
                self.assertIn('starship init ' + shell, text)
                self.assertEqual(text.count(b.START), 1)
                self.assertFalse(b.prompt_preview(self.runner, shell, True, self.home))
                self.assertTrue(self.apply(b.prompt_preview(self.runner, shell, False, self.home)).ok)
                self.assertEqual(self.mapping[slot].read_bytes(), original)
        self.assertTrue(self.mapping['starship'].exists())

    def test_manual_initialization_malformed_markers_and_custom_zdotdir_preserved(self):
        for text in ['eval "$(starship init bash)"\n', b.START + '\n', b.END + '\n' + b.START]:
            self.mapping['bashrc'].write_text(text)
            with self.assertRaises(ValueError):
                b.prompt_preview(self.runner, 'bash', True, self.home)
            self.assertEqual(self.mapping['bashrc'].read_text(), text)
        with patch.dict(os.environ, {'ZDOTDIR': '/different'}), self.assertRaises(ValueError):
            b.prompt_preview(self.runner, 'zsh', True, self.home)

    def test_missing_starship_refuses_activation(self):
        with patch.object(b.shutil, 'which', return_value=None), self.assertRaises(ValueError):
            b.prompt_preview(self.runner, 'bash', True, self.home)
        self.assertFalse(self.mapping['bashrc'].exists())

    def test_profiles_have_own_launcher_and_preserve_normal_configuration(self):
        normal = self.home / '.config/kitty/kitty.conf'
        normal.parent.mkdir(parents=True)
        normal.write_text('user settings')
        changes = b.terminal_preview(self.runner, 'kitty', 'dark', 'DejaVu Sans Mono', 14, self.home)
        self.assertTrue(self.apply(changes).ok)
        self.assertEqual(normal.read_text(), 'user settings')
        self.assertIn('font_size 14', self.mapping['kitty'].read_text())
        launcher = self.mapping['kitty-launcher'].read_text()
        self.assertIn('"--config"', launcher)
        self.assertIn(str(self.mapping['kitty']), launcher)
        self.assertFalse(self.mapping['alacritty-toml'].exists())

    def test_alacritty_selects_format_by_installed_version(self):
        for version, slot, fragment in [('0.12.3', 'alacritty-yaml', 'font:\n'), ('0.13.0', 'alacritty-toml', '[font]\n'), ('1.0.0', 'alacritty-toml', '[font]\n')]:
            runner = FakeRunner().add(['fc-list'], stdout='Mono\n').add(['/usr/bin/alacritty', '--version'], stdout='alacritty ' + version)
            changes = b.terminal_preview(runner, 'alacritty', 'light', 'Mono', 12, self.home)
            config = next(change for change in changes if change.slot == slot)
            self.assertIn(fragment, config.after.decode())
            self.assertIn('"--config-file"', next(c for c in changes if c.slot.endswith('launcher')).after.decode())

    def test_arbitrary_font_and_bad_sizes_cannot_inject_configuration(self):
        for family, size in [('Fake\ninclude /tmp/evil', 12), ('monospace', 33), ('monospace', True)]:
            with self.assertRaises(ValueError):
                b.terminal_preview(self.runner, 'kitty', 'dark', family, size, self.home)
        self.assertFalse(self.mapping['kitty'].exists())

    def test_launcher_escapes_desktop_values_before_exec_arguments(self):
        self.assertEqual(b.desktop_quote('/home/user name/$data'), '"/home/user name/\\\\$data"')
        self.assertEqual(b.desktop_quote('/home/a\\b'), '"/home/a\\\\\\\\b"')
        self.assertEqual(b.desktop_quote('/home/100%'), '"/home/100%%"')
        with self.assertRaises(ValueError):
            b.desktop_quote('/home/new\nExec=evil')


class TerminalShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'accounts'
        self.account = ('mintuser', '/bin/bash')
        p = patch.object(b, 'current_account', side_effect=lambda: self.account)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(b, 'allowed_shells', return_value=['/bin/bash', '/usr/bin/fish'])
        p.start()
        self.addCleanup(p.stop)
        self.runner = FakeRunner()
        def chsh(command):
            self.assertTrue(list(self.directory.glob('*.json')))
            self.assertTrue(command.needs_root)
            self.account = (command.argv[-1], command.argv[-2])
            return Result(str(command), 0)
        self.runner.add_callable(['/usr/bin/chsh'], chsh)

    def test_current_user_shell_saved_changed_verified_and_restorable(self):
        plan = b.preview_shell('/usr/bin/fish')
        b.change_shell(self.runner, plan, self.directory)
        self.assertEqual(self.account, ('mintuser', '/usr/bin/fish'))
        restore = b.restore_shell_plan(self.directory)
        self.assertEqual(restore.after, '/bin/bash')
        b.change_shell(self.runner, restore, self.directory)
        self.assertEqual(self.account, ('mintuser', '/bin/bash'))

    def test_stale_account_and_unlisted_shell_refused(self):
        with self.assertRaises(ValueError):
            b.preview_shell('/tmp/custom-shell')
        plan = b.preview_shell('/usr/bin/fish')
        self.account = ('different', '/bin/bash')
        with self.assertRaises(ValueError):
            b.change_shell(self.runner, plan, self.directory)
        self.assertFalse(self.runner.calls)

    def test_simulation_creates_no_receipt_or_command(self):
        plan = b.preview_shell('/usr/bin/fish')
        self.runner.dry_run = True
        b.change_shell(self.runner, plan, self.directory)
        self.assertFalse(self.directory.exists())
        self.assertFalse(self.runner.calls)

    def test_success_exit_without_account_change_is_refused(self):
        runner = FakeRunner().add(['/usr/bin/chsh'])
        with self.assertRaises(ValueError):
            b.change_shell(runner, b.preview_shell('/usr/bin/fish'), self.directory)
        self.assertTrue(list(self.directory.glob('*.json')))

    def test_missing_configuration_is_not_created_by_prompt_removal(self):
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {'XDG_CONFIG_HOME': home}):
            self.assertEqual(b.prompt_preview(self.runner, 'bash', False, Path(home)), [])
            self.assertFalse((Path(home) / '.bashrc').exists())
