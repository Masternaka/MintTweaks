"""Personal catalog and official-source enforcement with offline APT fixtures."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from minttweaks.core.runner import Result
from minttweaks.modules.applications import backend
from minttweaks.modules.applications.catalog import Application, CATALOG
from minttweaks.modules.applications import _apt_probe
from tests.fakes import FakeRunner
from tests.test_software import BrowserRunner
from tests import fakegi
fakegi.install()
from minttweaks.modules.applications.page import ApplicationsPage
from minttweaks.ui.widgets import AppContext

APP = Application('editor', 'My editor', 'editor-example', 'Editing', 'Personal editor')
OTHER = Application('player', 'My player', 'player-example', 'Multimedia')


class ApplicationsRunner(BrowserRunner):
    def __init__(self):
        super().__init__()
        self.versions.update({'editor-example': '1.2.3', 'player-example': '4.0'})
        self.bad_sources = set()
        self.add_callable(['/usr/bin/python3', '-I', str(backend.PROBE)], self.probe)

    def probe(self, command):
        payload = {}
        for request in command.argv[3:]:
            name, sep, version = request.partition('=')
            name = name.split(':')[0]
            if name in self.bad_sources:
                payload[request] = {'error': 'PPA is not an official distribution source'}
            else:
                payload[request] = {'version': version if sep else self.versions[name], 'architecture': 'amd64',
                                    'origins': ['Ubuntu | mirror.example | noble | universe']}
        return Result(str(command), 0, stdout=json.dumps(payload))


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(backend, 'CATALOG', (APP, OTHER))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = ApplicationsRunner()

    def test_user_catalog_preserves_all_requested_packages(self):
        expected = '''catfish gparted qbittorrent transmission-gtk lshw fwupd 7zip unzip stow
fontconfig font-manager flameshot btop fastfetch git curl wget ranger strawberry vlc mpv
qemu virt-manager distrobox podman kitty micro meld fonts-cascadia-code fonts-firacode
fonts-hack fonts-jetbrains-mono fonts-noto fonts-font-awesome'''.split()
        self.assertEqual([app.package for app in CATALOG], expected)

    def test_empty_catalog_queries_nothing(self):
        with patch.object(backend, 'CATALOG', ()):
            self.assertEqual(backend.collect_status(self.runner), {})
        self.assertFalse(self.runner.calls)

    def test_installed_package_does_not_become_an_installation_candidate(self):
        self.runner.installed[APP.package] = '1.0'
        status = backend.collect_status(self.runner)
        self.assertTrue(status['editor'].installed)
        self.assertFalse(status['editor'].installable)
        self.assertTrue(status['player'].installable)

    def test_unknown_duplicate_or_injected_selections_are_refused_before_query(self):
        for ids in ([], ['unknown'], ['editor', 'editor']):
            with self.assertRaises(ValueError):
                backend.preview_install(self.runner, ids)
        with patch.object(backend, 'CATALOG', (Application('bad', 'Bad', '--option', 'Other'),)):
            with self.assertRaises(ValueError):
                backend.collect_status(self.runner)
        self.assertFalse(self.runner.calls)

    def test_third_party_candidate_is_unavailable(self):
        self.runner.bad_sources.add(APP.package)
        status = backend.collect_status(self.runner)
        self.assertFalse(status['editor'].installable)
        self.assertIn('official', status['editor'].error)
        with self.assertRaises(ValueError):
            backend.preview_install(self.runner, ['editor'])
        self.assertFalse(any(command.needs_root for command in self.runner.calls))

    def test_third_party_dependency_blocks_an_otherwise_official_application(self):
        self.runner.extra_operations = ['Inst external-dependency (1.0 PPA [amd64])']
        self.runner.bad_sources.add('external-dependency')
        with self.assertRaisesRegex(ValueError, 'PPA'):
            backend.preview_install(self.runner, ['editor'])
        self.assertFalse(any(command.needs_root for command in self.runner.calls))

    def test_preview_includes_sources_versions_and_all_dependencies(self):
        self.runner.extra_operations = ['Inst dependency [0.9] (1.0 Ubuntu [amd64])']
        plan = backend.preview_install(self.runner, ['editor'])
        self.assertEqual(plan.specs, ('editor-example=1.2.3',))
        self.assertIn('dependency=1.0', [item[0] for item in plan.sources])
        self.assertIn('Inst dependency', plan.output)
        self.assertFalse(any(command.needs_root for command in self.runner.calls))

    def test_removal_and_unreadable_plans_are_refused(self):
        for operation in ['Remv important [1.0]', 'Inst unexpected-garbage']:
            self.runner.extra_operations = [operation]
            with self.assertRaises(ValueError):
                backend.preview_install(self.runner, ['editor'])
        self.assertFalse(self.runner.installed)

    def test_changed_candidate_dependency_or_origin_requires_new_preview(self):
        plan = backend.preview_install(self.runner, ['editor'])
        self.runner.versions[APP.package] = '2.0'
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            backend.install(self.runner, plan)
        self.runner.versions[APP.package] = '1.2.3'
        self.runner.extra_operations = ['Inst new-dependency (1.0 Ubuntu [amd64])']
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            backend.install(self.runner, plan)
        self.runner.extra_operations = []
        self.runner.bad_sources.add(APP.package)
        with self.assertRaises(ValueError):
            backend.install(self.runner, plan)
        self.assertFalse(self.runner.installed)

    def test_successful_installation_is_pinned_and_verified(self):
        outcome = backend.install(self.runner, backend.preview_install(self.runner, ['editor', 'player']))
        self.assertTrue(outcome.ok)
        commands = [command for command in self.runner.calls if command.needs_root]
        self.assertEqual(len(commands), 1)
        self.assertIn('--no-remove', commands[0].argv)
        self.assertIn('editor-example=1.2.3', commands[0].argv)
        self.assertFalse(self.runner.ran(['apt-get', 'update']))

    def test_command_success_without_installed_version_is_not_verified(self):
        self.runner.keep_absent = True
        outcome = backend.install(self.runner, backend.preview_install(self.runner, ['editor']))
        self.assertFalse(outcome.ok)
        self.assertIn('editor', outcome.states)

    def test_dry_run_performs_no_installs_or_queries(self):
        plan = backend.preview_install(self.runner, ['editor'])
        self.runner.calls.clear()
        self.runner.dry_run = True
        outcome = backend.install(self.runner, plan)
        self.assertTrue(outcome.ok)
        self.assertFalse(self.runner.calls)
        self.assertFalse(self.runner.installed)


class ProbeTests(unittest.TestCase):
    def origin(self, name='Ubuntu', trusted=True, site='mirror.example', archive='noble'):
        return SimpleNamespace(origin=name, trusted=trusted, site=site, archive=archive, component='universe')

    def cache(self, origins):
        version = SimpleNamespace(version='1.0', architecture='amd64', origins=origins)
        return {'example': SimpleNamespace(candidate=version, versions=[version])}

    def test_distribution_origins_distinguish_ubuntu_base_and_lmde(self):
        self.assertEqual(_apt_probe.distro_origins('ID=linuxmint\nID_LIKE="ubuntu debian"\nUBUNTU_CODENAME=noble'), {'linuxmint', 'ubuntu'})
        self.assertEqual(_apt_probe.distro_origins('ID=linuxmint\nID_LIKE=debian'), {'linuxmint', 'debian'})
        with self.assertRaises(ValueError):
            _apt_probe.distro_origins('ID=ubuntu')

    def test_trusted_official_mirrors_and_linuxmint_origin_are_accepted(self):
        for name in ['Ubuntu', 'linuxmint', 'LinuxMint']:
            info = _apt_probe.inspect(self.cache([self.origin(name)]), 'example', {'ubuntu', 'linuxmint'})
            self.assertEqual(info['version'], '1.0')
        info = _apt_probe.inspect(self.cache([self.origin('Debian', archive='stable')]), 'example=1.0', {'debian', 'linuxmint'})
        self.assertIn('Debian', info['origins'][0])

    def test_unsigned_ppa_mixed_or_unidentified_sources_are_refused(self):
        for origins in ([self.origin(trusted=False)], [self.origin('LP-PPA-owner')],
                        [self.origin(), self.origin('ThirdParty')], [self.origin(site='')], []):
            with self.assertRaises(ValueError):
                _apt_probe.inspect(self.cache(origins), 'example=1.0', {'ubuntu'})

    def test_installed_status_record_is_not_a_repository_source(self):
        local = self.origin('', False, '', 'now')
        _apt_probe.inspect(self.cache([self.origin(), local]), 'example', {'ubuntu'})
        with self.assertRaises(ValueError):
            _apt_probe.inspect(self.cache([local]), 'example', {'ubuntu'})


class ApplicationsPageTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(backend, 'CATALOG', (APP, OTHER))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = ApplicationsRunner()
        self.page = ApplicationsPage(AppContext(self.runner))

    def test_cancelled_preview_never_installs(self):
        plan = backend.preview_install(self.runner, ['editor'])
        self.page._busy = True
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm, patch.object(self.page, 'run_operation') as run:
            self.page._confirm_install(plan)
        run.assert_not_called()
        self.assertIn('mirror.example', '\n'.join(confirm.call_args.args[2]))
        self.assertFalse(self.page._busy)

    def test_busy_global_operation_is_visible_and_releases_controls(self):
        plan = backend.preview_install(self.runner, ['editor'])
        with patch.object(self.page.ctx, 'run_async'):
            self.page.ctx.run_operation('Other operation', lambda: None)
        self.page.error = Mock()
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True):
            self.page._confirm_install(plan)
        self.page.error.assert_called_once()
        self.assertFalse(self.page._busy)
        self.assertFalse(self.runner.installed)

    def test_search_filters_without_clearing_selection(self):
        self.page.search.get_text = Mock(return_value='multimedia')
        for row in self.page.rows.values():
            row.set_visible = Mock()
        for check in self.page.checks.values():
            check.set_active = Mock()
        self.page._filter()
        self.page.rows['player'].set_visible.assert_called_once_with(True)
        self.page.rows['editor'].set_visible.assert_called_once_with(False)
        for check in self.page.checks.values():
            check.set_active.assert_not_called()
