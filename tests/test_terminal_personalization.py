"""Personal choices stay declarative, isolated, backed up and reviewable."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.core import userfiles
from minttweaks.modules.terminal import backend, configuration as c, integrations as i, status, transfer
from tests.fakes import FakeRunner
from tests.test_software import BrowserRunner


class PersonalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mtk personal ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        for mocked in (
            patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.home / '.config'), 'XDG_DATA_HOME': str(self.home / '.local/share'), 'ZDOTDIR': ''}),
            patch.object(backend.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name if name in ('bash','zsh','fish','fzf','bat','batcat','eza','tmux','starship','zoxide','kitty') else None),
            patch.object(backend, 'tool_state', return_value=backend.ToolState(installed=True, binary='/usr/bin/tool')),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)
        self.runner = FakeRunner().add(['/usr/bin/fzf', '--version'], stdout='0.48.0\n')
        self.targets = backend.targets(self.home)
        self.backups = self.home / 'backups'
        p = patch('minttweaks.core.paths.TERMINAL_BACKUP_DIR', self.backups)
        p.start()
        self.addCleanup(p.stop)

    def save(self, shell, tool=None, options=None, aliases=None):
        plan = c.preview(self.runner, shell, tool, options, aliases, self.home)
        self.assertTrue(c.apply(self.runner, plan, self.home).ok)
        return plan

    def test_every_setting_is_generated_and_reopening_is_idempotent(self):
        for tool, defaults in c.DEFAULTS.items():
            with self.subTest(tool=tool):
                self.save('bash', tool, defaults)
                self.assertEqual(c.load(self.home)['shells']['bash']['settings'][tool], defaults)
                self.assertFalse(c.preview(self.runner, 'bash', tool, defaults, home=self.home).changes)
        content = self.targets['settings-bash'].read_text()
        self.assertIn('FZF_DEFAULT_OPTS', content)
        self.assertIn('BAT_THEME', content)
        self.assertIn('mtk-eza()', content)
        self.assertIn('tmux -L minttweaks -f', content)
        self.assertLess(self.targets['bashrc'].read_text().index('integration: customization'), self.targets['bashrc'].read_text().index('fzf --bash'))

    def test_starship_settings_survive_later_reactivation(self):
        opt = dict(c.DEFAULTS['starship'], color='blue', symbol='$', git=False)
        self.save('bash', 'starship', opt)
        self.assertIn('bold blue', self.targets['starship'].read_text())
        self.assertNotIn('$git_branch', self.targets['starship'].read_text())
        plan = i.preview(self.runner, 'bash', ['starship'], home=self.home)
        self.assertFalse(plan.changes)

    def test_alias_add_edit_remove_preserves_external_settings_and_other_aliases(self):
        self.targets['bashrc'].write_text('alias ll="ls -l"\n')
        self.save('bash', aliases={'gst': 'git status', 'glog': 'git log --oneline'})
        self.save('bash', aliases={'gst': 'git status --short', 'glog': 'git log --oneline'})
        self.assertIn('git status --short', self.targets['settings-bash'].read_text())
        self.save('bash', aliases={'glog': 'git log --oneline'})
        self.assertNotIn('alias gst=', self.targets['settings-bash'].read_text())
        self.assertIn('alias ll="ls -l"', self.targets['bashrc'].read_text())

    def test_alias_values_are_quoted_and_never_executed_when_read(self):
        command = 'printf "%s" "$(touch /tmp/not-run)"; echo `whoami`'
        for shell in backend.SHELLS:
            self.save(shell, aliases={'demo': command})
            self.assertEqual(c.load(self.home)['shells'][shell]['aliases']['demo'], command)
            content = self.targets['settings-' + shell].read_text()
            self.assertIn(command, content)
            if shell in ('bash', 'zsh'):
                host = Path('/bin/' + shell)
                if host.exists():
                    result = subprocess.run([str(host), '-n', str(self.targets['settings-' + shell])], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_manual_alias_conflict_is_refused_but_binary_shadowing_is_visible(self):
        self.targets['bashrc'].write_text('alias gst="git status"\n')
        with self.assertRaises(ValueError):
            c.preview(self.runner, 'bash', aliases={'gst': 'git status -sb'}, home=self.home)
        plan = c.preview(self.runner, 'bash', aliases={'tmux': 'tmux -2'}, home=self.home)
        self.assertIn('will shadow an installed command', '\n'.join(plan.notes))
        self.assertFalse(self.backups.exists())

    def test_invalid_aliases_and_options_are_refused(self):
        for aliases in ({'z': 'echo conflict'}, {'bad name': 'ls'}, {'demo': 'a\nb'}, {'demo': 'x\x85y'}):
            with self.subTest(aliases=aliases), self.assertRaises(ValueError):
                c.validate_aliases(aliases)
        for options in (dict(c.DEFAULTS['fzf'], height=True), dict(c.DEFAULTS['fzf'], height=101), dict(c.DEFAULTS['fzf'], color='dark; touch /tmp/no')):
            with self.assertRaises(ValueError):
                c.validate_settings({'fzf': options})

    def test_stale_plans_missing_tools_and_simulation_do_not_write(self):
        plan = c.preview(self.runner, 'bash', 'fzf', c.DEFAULTS['fzf'], home=self.home)
        self.targets['bashrc'].write_text('external edit\n')
        with self.assertRaises(ValueError):
            c.apply(self.runner, plan, self.home)
        self.assertFalse(self.backups.exists())
        with patch.object(backend, 'tool_state', return_value=backend.ToolState()), self.assertRaises(ValueError):
            c.preview(self.runner, 'bash', 'tmux', c.DEFAULTS['tmux'], home=self.home)
        self.runner.dry_run = True
        self.assertTrue(c.apply(self.runner, plan, self.home).simulated)
        self.assertFalse(self.targets['preferences'].exists())

    def test_status_distinguishes_managed_manual_absent_and_modified(self):
        self.targets['bashrc'].write_text('eval "$(direnv hook bash)"\n')
        self.assertTrue(i.apply(self.runner, i.preview(self.runner, 'bash', ['zoxide'], home=self.home), self.home, self.backups).ok)
        states = {tool: backend.ToolState(installed=True, binary='/usr/bin/tool') for tool in ('zoxide', 'direnv', 'fzf', 'jq')}
        states['bat'] = backend.ToolState()
        report = status.collect(self.runner, states, self.home)['bash']
        self.assertEqual({tool: value.code for tool, value in report.items()}, {'zoxide':'configured', 'direnv':'manual', 'fzf':'unconfigured', 'jq':'default', 'bat':'absent'})
        self.assertIn('new terminal', report['zoxide'].detail)
        self.targets['bashrc'].write_text(self.targets['bashrc'].read_text().replace('zoxide init bash', 'zoxide init posix'))
        self.assertEqual(status.collect(self.runner, states, self.home)['bash']['zoxide'].code, 'review')

    def test_unreadable_or_malformed_startup_never_reports_configured(self):
        self.targets['bashrc'].write_text(i.markers('fzf')[0] + '\n')
        report = status.collect(self.runner, {'fzf': backend.ToolState(installed=True)}, self.home)
        self.assertEqual(report['bash']['fzf'].code, 'unknown')

    def test_filters_match_package_description_and_keep_shell_compatibility(self):
        entry = backend.TOOL_BY_ID['fd']
        absent = backend.ToolState(candidate='1')
        self.assertTrue(status.matches(entry, absent, None, 'fd-find', 'available'))
        self.assertFalse(status.matches(entry, absent, None, '', 'installed'))
        self.assertFalse(status.matches(backend.TOOL_BY_ID['zsh-autosuggestions'], absent, None, '', 'configurable', 'fish'))
        self.assertTrue(status.matches(backend.TOOL_BY_ID['zsh-autosuggestions'], absent, None, '', 'configurable', 'zsh'))

    def test_preferences_corruption_is_preserved_and_not_reset(self):
        path = self.targets['preferences']
        path.parent.mkdir(parents=True)
        path.write_text('{broken')
        with self.assertRaises(ValueError):
            c.preview(self.runner, 'bash', aliases={'gst':'git status'}, home=self.home)
        self.assertEqual(path.read_text(), '{broken')

    def test_export_import_round_trip_in_different_home_regenerates_paths(self):
        self.save('bash', 'starship', dict(c.DEFAULTS['starship'], color='magenta'))
        self.save('bash', 'fzf', dict(c.DEFAULTS['fzf'], height=60, preview=True))
        self.save('bash', aliases={'gst':'git status'})
        states = {tool: backend.ToolState(installed=True, binary='/usr/bin/tool') for tool in ('bash','starship','fzf')}
        report = status.collect(self.runner, states, self.home)
        document = transfer.export_document(states, report, home=self.home)
        destination = self.home / 'export.json'
        self.assertTrue(transfer.write(self.runner, destination, document).ok)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        loaded = transfer.read(destination)
        with tempfile.TemporaryDirectory(prefix='other home ') as other:
            with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(Path(other) / '.config'), 'XDG_DATA_HOME': str(Path(other) / '.local/share')}):
                plan = transfer.preview_configuration(self.runner, loaded, Path(other))
                self.assertTrue(transfer.apply_configuration(self.runner, loaded, plan, Path(other)).ok)
                mapping = backend.targets(Path(other))
                self.assertIn(other, mapping['bashrc'].read_text())
                self.assertNotIn(str(self.home), mapping['bashrc'].read_text())
                self.assertIn('alias gst=', mapping['settings-bash'].read_text())
                self.assertIn('height=60%', mapping['settings-bash'].read_text())
                self.assertIn('bold magenta', mapping['starship'].read_text())
                self.assertFalse(transfer.preview_configuration(self.runner, loaded, Path(other)).changes)

    def test_import_rejects_raw_scripts_unknown_versions_tools_and_duplicate_keys(self):
        document = {'format':'minttweaks-terminal', 'schema_version':1, 'tools':['bash'], 'integrations':{}, 'preferences':{'schema_version':1,'shells':{}}}
        for change in ({'script':'eval evil'}, {'schema_version':2}, {'tools':['arbitrary-package']}, {'preferences':{'schema_version':1,'shells':{'powershell':{}}}}):
            invalid = dict(document, **change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                transfer.validate(invalid)
        path = self.home / 'duplicates.json'
        path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            transfer.read(path)

    def test_export_never_overwrites_an_existing_file_or_follows_link(self):
        document = {'format':'minttweaks-terminal', 'schema_version':1, 'tools':[], 'integrations':{}, 'preferences':{'schema_version':1,'shells':{}}}
        path = self.home / 'existing.json'
        path.write_text('precious')
        with self.assertRaises(ValueError):
            transfer.write(self.runner, path, document)
        link = self.home / 'link.json'
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            transfer.write(self.runner, link, document)
        self.assertEqual(path.read_text(), 'precious')

    def test_import_merges_aliases_without_removing_other_local_tools(self):
        self.save('bash', aliases={'local':'echo local'})
        document = {'format':'minttweaks-terminal','schema_version':1,'tools':['bash'],'integrations':{},'preferences':{'schema_version':1,'shells':{'bash':{'settings':{},'aliases':{'remote':'echo remote'}}}}}
        plan = transfer.preview_configuration(self.runner, document, self.home)
        self.assertTrue(transfer.apply_configuration(self.runner, document, plan, self.home).ok)
        self.assertEqual(set(c.load(self.home)['shells']['bash']['aliases']), {'local','remote'})

    def test_import_prerequisites_include_full_apt_preview(self):
        runner = BrowserRunner()
        runner.versions['fzf'] = '1.0'
        runner.origins['fzf'] = ['https://example.invalid/mint']
        runner.suites['fzf'] = 'stable/main'
        document = {'format':'minttweaks-terminal','schema_version':1,'tools':['bash','fzf'],'integrations':{'bash':['fzf']},'preferences':{'schema_version':1,'shells':{}}}
        # Bypass this fixture's tool-state patch for the package simulation.
        def state(_runner, tool):
            return backend.ToolState(installed=tool == 'bash', candidate='' if tool == 'bash' else '1.0')
        with patch.object(backend, 'tool_state', side_effect=state):
            request = transfer.inspect(runner, document)
        self.assertIn('fzf=1.0', request.packages.specs)
        self.assertFalse(any(command.needs_root for command in runner.calls))

    def test_terminal_appearance_survives_export_import_with_current_paths(self):
        changes = backend.terminal_preview(self.runner, 'kitty', 'light', 'monospace', 16, self.home)
        self.assertTrue(userfiles.apply(self.runner, self.targets, changes, self.backups).ok)
        states = {'kitty': backend.ToolState(installed=True, binary='/usr/bin/kitty')}
        document = transfer.export_document(states, {}, home=self.home)
        with tempfile.TemporaryDirectory() as other, patch.dict(os.environ, {'XDG_CONFIG_HOME': str(Path('/tmp') / Path(other).name / '.config'), 'XDG_DATA_HOME': str(Path('/tmp') / Path(other).name / '.local/share')}):
            plan = transfer.preview_configuration(self.runner, document, Path(other))
            config = next(change for change in plan.changes if change.slot == 'kitty').after.decode()
            launcher = next(change for change in plan.changes if change.slot == 'kitty-launcher').after.decode()
            self.assertIn('font_size 16', config)
            self.assertIn('background #fafafa', config)
            self.assertNotIn(str(self.home), launcher)

    def test_import_preserves_zsh_highlighter_order_when_adding_settings_hooks(self):
        document = {'format':'minttweaks-terminal','schema_version':1,'tools':['zsh','fzf','zsh-syntax-highlighting'],
                    'integrations':{'zsh':['zsh-syntax-highlighting']},
                    'preferences':{'schema_version':1,'shells':{'zsh':{'settings':{'fzf':c.DEFAULTS['fzf']},'aliases':{}}}}}
        with patch.object(i, 'system_script', side_effect=lambda values: Path(values[0])):
            plan = transfer.preview_configuration(self.runner, document, self.home)
            self.assertTrue(transfer.apply_configuration(self.runner, document, plan, self.home).ok)
        text = self.targets['zshrc'].read_text()
        self.assertLess(text.index('fzf --zsh'), text.index('. /usr/share/zsh-syntax-highlighting'))

    def test_status_reports_modified_generated_settings_file(self):
        self.save('bash', 'fzf', c.DEFAULTS['fzf'])
        self.targets['settings-bash'].write_text('external modification\n')
        states = {'fzf':backend.ToolState(installed=True, binary='/usr/bin/fzf')}
        self.assertEqual(status.collect(self.runner, states, self.home)['bash']['fzf'].code, 'review')

    def test_shared_starship_settings_are_consistent_across_shells(self):
        self.save('bash', 'starship', c.DEFAULTS['starship'])
        updated = dict(c.DEFAULTS['starship'], color='blue')
        self.save('zsh', 'starship', updated)
        preferences = c.load(self.home)
        self.assertEqual(preferences['shells']['bash']['settings']['starship'], updated)
        self.assertFalse(i.preview(self.runner, 'bash', ['starship'], home=self.home).changes)

    def test_import_refuses_unavailable_tool_and_missing_font_before_installation(self):
        document = {'format':'minttweaks-terminal','schema_version':1,'tools':['kitty'], 'integrations':{},
                    'preferences':{'schema_version':1,'shells':{},'terminals':{'kitty':{'family':'Missing Font','size':12,'palette':'dark'}}}}
        with self.assertRaises(ValueError):
            transfer.inspect(self.runner, document)
        document['preferences']['terminals'] = {}
        with patch.object(backend, 'tool_state', return_value=backend.ToolState(error='no candidate')), self.assertRaises(ValueError):
            transfer.inspect(self.runner, document)
        self.assertFalse(any(command.needs_root for command in self.runner.calls))

    def test_fish_alias_command_remains_data_until_invocation(self):
        command = "end; echo 'text'; function other"
        self.save('fish', aliases={'demo':command})
        text = self.targets['settings-fish'].read_text()
        self.assertNotIn('alias demo', text)
        self.assertEqual(text.splitlines()[0], 'function demo')
        self.assertIn('    builtin eval ', text)
        self.assertEqual(len(text.splitlines()), 3)

    def test_partial_personal_write_failure_recovers_startup_and_preferences(self):
        self.targets['bashrc'].write_text('# original\n')
        plan = c.preview(self.runner, 'bash', aliases={'gst':'git status'}, home=self.home)
        original_write = userfiles.atomic_write
        def write(path, data, mode=0o600):
            if path == self.targets['settings-bash']:
                raise OSError('disk full')
            return original_write(path, data, mode)
        with patch.object(userfiles, 'atomic_write', side_effect=write):
            outcome = c.apply(self.runner, plan, self.home)
        self.assertFalse(outcome.ok)
        self.assertTrue(outcome.backup.exists())
        self.assertEqual(self.targets['bashrc'].read_text(), '# original\n')
        self.assertFalse(self.targets['preferences'].exists())

    def test_import_stale_plan_and_simulated_export_never_write(self):
        document = {'format':'minttweaks-terminal','schema_version':1,'tools':['bash'],'integrations':{},'preferences':{'schema_version':1,'shells':{'bash':{'settings':{},'aliases':{'gst':'git status'}}}}}
        plan = transfer.preview_configuration(self.runner, document, self.home)
        self.targets['bashrc'].write_text('# external\n')
        with self.assertRaises(ValueError):
            transfer.apply_configuration(self.runner, document, plan, self.home)
        self.runner.dry_run = True
        self.assertTrue(transfer.write(self.runner, self.home / 'not-created/export.json', document).simulated)
        self.assertFalse((self.home / 'not-created').exists())
