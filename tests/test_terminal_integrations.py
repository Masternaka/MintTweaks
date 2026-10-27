"""Backed-up integration plans use temporary user files and fake commands."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.core import userfiles
from minttweaks.modules.terminal import backend, integrations as i
from tests.fakes import FakeRunner


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mtk integration ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.runner = FakeRunner().add(['/usr/bin/fzf', '--version'], stdout='0.48.0\n')
        for change in (
            patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.home / '.config'), 'XDG_DATA_HOME': str(self.home / '.local/share'), 'ZDOTDIR': ''}),
            patch.object(backend.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name),
            patch.object(backend, 'tool_state', return_value=backend.ToolState(installed=True, binary='/usr/bin/tool')),
        ):
            change.start()
            self.addCleanup(change.stop)
        self.mapping = backend.targets(self.home)
        self.backups = self.home / 'backups'

    def preview(self, shell, tools, enabled=True):
        return i.preview(self.runner, shell, tools, enabled, self.home)

    def apply(self, plan):
        return i.apply(self.runner, plan, self.home, self.backups)

    def test_each_shell_has_working_init_syntax_and_keeps_aliases(self):
        for shell, slot in [('bash', 'bashrc'), ('zsh', 'zshrc'), ('fish', 'fishrc')]:
            self.mapping[slot].parent.mkdir(parents=True, exist_ok=True)
            self.mapping[slot].write_text('# my settings\n')
            plan = self.preview(shell, ['zoxide', 'direnv', 'atuin', 'fzf', 'bat', 'fd', 'delta', 'starship'])
            self.assertTrue(self.apply(plan).ok)
            text = self.mapping[slot].read_text()
            self.assertTrue(text.startswith('# my settings\n'))
            self.assertIn('zoxide init ' + shell, text)
            self.assertIn('direnv hook ' + shell, text)
            self.assertIn('atuin init ' + shell, text)
            self.assertIn('fzf --' + shell, text)
            self.assertIn('GIT_PAGER', text)
            self.assertIn('alias bat', text)
            self.assertIn('alias fd', text)
            self.assertIn('starship init ' + shell, text)
            self.assertFalse(self.preview(shell, list(plan.tools)).changes)
            # Paths above are mocked for preview. Only real host syntax checkers
            # are used here with -n (no script execution).
            host = {'bash': '/bin/bash', 'zsh': '/bin/zsh', 'fish': '/usr/bin/fish'}[shell]
            if Path(host).is_file():
                result = subprocess.run([host, '-n', str(self.mapping[slot])], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_old_fzf_uses_installed_scripts_instead_of_new_flags(self):
        self.runner = FakeRunner().add(['/usr/bin/fzf', '--version'], stdout='0.44.1\n')
        with patch.object(i, 'system_script', side_effect=lambda paths: Path(paths[0])):
            plan = self.preview('bash', ['fzf'])
        text = plan.changes[0].after.decode()
        self.assertIn('/usr/share/doc/fzf/examples/completion.bash', text)
        self.assertIn('/usr/share/doc/fzf/examples/key-bindings.bash', text)
        self.assertNotIn('fzf --bash', text)

    def test_missing_old_fzf_scripts_refuse_changes(self):
        self.runner = FakeRunner().add(['/usr/bin/fzf', '--version'], stdout='0.44.1\n')
        with patch.object(Path, 'is_file', return_value=False), self.assertRaises(ValueError):
            self.preview('bash', ['fzf'])
        self.assertFalse(self.mapping['bashrc'].exists())

    def test_wrong_shell_plugins_and_autonomous_tools_have_explicit_notes(self):
        plan = self.preview('fish', ['zsh-autosuggestions', 'bash-completion', 'ripgrep', 'jq'])
        self.assertFalse(plan.changes)
        self.assertIn('applies to zsh only', '\n'.join(plan.notes))
        self.assertIn('no shell hook is needed', '\n'.join(plan.notes))
        self.assertFalse(self.mapping['fishrc'].exists())

    def test_partial_removal_preserves_other_integrations_and_user_settings(self):
        self.mapping['bashrc'].write_text('alias ll="ls -l"\n')
        self.assertTrue(self.apply(self.preview('bash', ['zoxide', 'direnv'])).ok)
        remove = self.preview('bash', ['zoxide'], False)
        self.assertTrue(self.apply(remove).ok)
        text = self.mapping['bashrc'].read_text()
        self.assertNotIn('zoxide init', text)
        self.assertIn('direnv hook bash', text)
        self.assertIn('alias ll="ls -l"', text)
        self.assertFalse(self.preview('bash', ['zoxide'], False).changes)

    def test_new_integrations_keep_existing_zsh_highlighter_last(self):
        with patch.object(i, 'system_script', side_effect=lambda paths: Path(paths[0])):
            self.assertTrue(self.apply(self.preview('zsh', ['zsh-syntax-highlighting'])).ok)
            self.assertTrue(self.apply(self.preview('zsh', ['fzf', 'zoxide'])).ok)
        text = self.mapping['zshrc'].read_text()
        self.assertLess(text.index('compinit'), text.index('zoxide init'))
        self.assertLess(text.index('zoxide init'), text.index('. /usr/share/zsh-syntax-highlighting'))
        self.assertTrue(text.endswith(i.markers('zsh-syntax-highlighting')[1] + '\n'))

    def test_user_compinit_is_preserved_and_not_initialized_again(self):
        self.mapping['zshrc'].write_text('autoload -Uz compinit\ncompinit\n')
        plan = self.preview('zsh', ['zoxide'])
        text = plan.changes[0].after.decode()
        self.assertEqual(text.count('autoload -Uz compinit'), 1)
        self.assertNotIn('integration: completion-system', text)

    def test_manual_initializations_or_malformed_blocks_are_preserved(self):
        for content in ['eval "$(zoxide init bash)"\n', i.markers('zoxide')[0] + '\n']:
            self.mapping['bashrc'].write_text(content)
            with self.assertRaises(ValueError):
                self.preview('bash', ['zoxide'])
            self.assertEqual(self.mapping['bashrc'].read_text(), content)

    def test_existing_framework_plugin_is_not_activated_twice(self):
        self.mapping['zshrc'].write_text('plugins=(git zsh-autosuggestions)\nsource "$ZSH/oh-my-zsh.sh"\n')
        with self.assertRaises(ValueError):
            self.preview('zsh', ['zsh-autosuggestions'])

    def test_integration_script_disappearing_before_apply_refuses_write(self):
        with patch.object(i, 'system_script', return_value=Path('/usr/share/bash-completion/bash_completion')):
            plan = self.preview('bash', ['bash-completion'])
        with patch.object(i, 'system_script', side_effect=ValueError('missing script')), self.assertRaises(ValueError):
            self.apply(plan)
        self.assertFalse(self.mapping['bashrc'].exists())

    def test_absent_tool_refuses_activation_but_allows_removal(self):
        self.assertTrue(self.apply(self.preview('bash', ['zoxide'])).ok)
        with patch.object(backend, 'tool_state', return_value=backend.ToolState()):
            with self.assertRaises(ValueError):
                self.preview('bash', ['zoxide'])
            self.assertTrue(self.apply(self.preview('bash', ['zoxide'], False)).ok)

    def test_stale_configuration_refused_after_confirmation(self):
        plan = self.preview('bash', ['zoxide'])
        self.mapping['bashrc'].write_text('external edit\n')
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertEqual(self.mapping['bashrc'].read_text(), 'external edit\n')
        self.assertFalse(self.backups.exists())

    def test_simulation_never_creates_files_or_backups(self):
        plan = self.preview('bash', ['zoxide'])
        self.runner.dry_run = True
        self.assertTrue(self.apply(plan).simulated)
        self.assertFalse(self.mapping['bashrc'].exists())
        self.assertFalse(self.backups.exists())

    def test_restoration_uses_shared_backups(self):
        plan = self.preview('bash', ['starship', 'zoxide'])
        result = self.apply(plan)
        self.assertTrue(result.ok)
        restore = userfiles.restore_preview(self.mapping, result.backup)
        self.assertTrue(userfiles.apply(self.runner, self.mapping, restore, self.backups).ok)
        self.assertFalse(self.mapping['bashrc'].exists())
        self.assertFalse(self.mapping['starship'].exists())

    def test_history_and_git_configuration_choices_are_visible(self):
        plan = self.preview('bash', ['atuin', 'delta', 'direnv'])
        self.assertIn('records new command history locally', '\n'.join(plan.notes))
        self.assertIn('No account, sync or history import', '\n'.join(plan.notes))
        self.assertIn('Git configuration files are preserved', '\n'.join(plan.notes))
        text = plan.changes[0].after.decode()
        self.assertNotIn('direnv allow', text)
        self.assertNotIn('atuin sync', text)
        self.assertFalse((self.home / '.gitconfig').exists())
