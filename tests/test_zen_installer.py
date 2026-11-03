"""Zen's user installer: provenance, cancellation, conflicts and verification."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from minttweaks.core.runner import Result
from minttweaks.modules.software import backend, zen
from tests.test_software import BrowserRunner


class ZenInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.patcher = patch.object(Path, 'home', return_value=self.home)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.uid = patch.object(zen.os, 'geteuid', return_value=1000)
        self.uid.start()
        self.addCleanup(self.uid.stop)
        self.runner = BrowserRunner()
        self.script = '#!/bin/bash\necho official-installer\n'
        self.runner.add_callable(['curl'], lambda c: Result(str(c), 0, stdout=self.script))

    def create_installation(self):
        directory, launcher, desktop = zen.targets()
        directory.mkdir(parents=True)
        binary = directory / 'zen'
        binary.write_bytes(b'not executed in tests')
        binary.chmod(0o755)
        (directory / 'application.ini').write_text('[App]\nVersion=1.23.4b\n')
        for path in (launcher, desktop):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('entry')

    def test_both_official_architectures_and_no_apt_zen_candidate(self):
        for arch in ('amd64', 'arm64'):
            self.assertTrue(zen.check_status(self.runner, arch).installable)
        self.assertFalse(zen.check_status(self.runner, 'i386').installable)
        self.assertFalse(any(c.argv[0] == 'apt-cache' for c in self.runner.calls))
        with self.assertRaises(backend.SoftwareError):
            backend.preview_install(self.runner, ['zen'])

    def test_preview_downloads_only_the_fixed_official_script_without_root(self):
        plan = zen.preview(self.runner)
        self.assertEqual(plan.script, self.script)
        self.assertEqual(len(plan.digest), 64)
        self.assertEqual(self.runner.calls[-1].argv[-1], zen.INSTALLER_URL)
        self.assertFalse(any(c.needs_root or c.argv[0] == 'bash' for c in self.runner.calls))
        self.assertFalse(any(p.exists() for p in zen.targets()))

    def test_download_failure_and_invalid_script_prevent_execution(self):
        self.script = '<html>error</html>'
        with self.assertRaises(backend.SoftwareError):
            zen.preview(self.runner)
        self.runner.add_callable(['curl', '--fail'], lambda c: Result(str(c), 22, stderr='HTTP error'))
        with self.assertRaises(Exception):
            zen.preview(self.runner)
        self.assertFalse(any(c.argv[0] == 'bash' for c in self.runner.calls))

    def test_legacy_debian_package_blocks_installation(self):
        self.runner.installed['zen-browser'] = '1.0+masternaka1'
        status = zen.check_status(self.runner, 'amd64')
        self.assertFalse(status.installable)
        self.assertIn('old Zen Debian package', status.error)
        with self.assertRaises(backend.SoftwareError):
            zen.preview(self.runner)

    def test_existing_files_and_broken_links_are_preserved(self):
        for target in zen.targets():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(self.home / 'absent')
            self.assertFalse(zen.check_status(self.runner, 'amd64').installable)
            self.assertTrue(target.is_symlink())
            target.unlink()

    def test_files_created_after_preview_refuse_execution(self):
        plan = zen.preview(self.runner)
        target = zen.targets()[0]
        target.mkdir(parents=True)
        with self.assertRaises(backend.SoftwareError):
            zen.install(self.runner, plan)
        self.assertFalse(any(c.argv[0] == 'bash' for c in self.runner.calls))

    def test_changed_architecture_or_script_requires_new_preview(self):
        plan = zen.preview(self.runner)
        with self.assertRaises(backend.SoftwareError):
            zen.install(self.runner, replace(plan, script=plan.script + 'echo changed'))
        self.runner.arch = 'arm64'
        with self.assertRaises(backend.SoftwareError):
            zen.install(self.runner, plan)

    def test_install_executes_reviewed_bytes_as_user_and_verifies_files(self):
        plan = zen.preview(self.runner)
        def execute(command):
            self.assertFalse(command.needs_root)
            self.assertEqual(Path(command.argv[1]).read_text(), self.script)
            self.create_installation()
            return Result(str(command), 0)
        self.runner.add_callable(['bash'], execute)
        self.assertTrue(zen.install(self.runner, plan).ok)
        self.assertEqual(zen.check_status(self.runner, 'amd64').installed_version, '1.23.4b')
        self.assertFalse(any(c.needs_root for c in self.runner.calls))

    def test_success_without_files_is_not_verified(self):
        self.runner.add_callable(['bash'], lambda c: Result(str(c), 0))
        self.assertFalse(zen.install(self.runner, zen.preview(self.runner)).ok)

    def test_simulation_does_not_download_write_or_execute(self):
        plan = zen.preview(self.runner)
        count = len(self.runner.calls)
        self.runner.dry_run = True
        self.assertTrue(zen.install(self.runner, plan).ok)
        self.assertFalse(zen.check_status(self.runner, 'amd64').installable)
        with self.assertRaises(Exception):
            zen.preview(self.runner)
        self.assertEqual(len(self.runner.calls), count)
        self.assertFalse(any(p.exists() for p in zen.targets()))

    def test_ui_cancellation_and_shared_operation_slot(self):
        from tests import fakegi
        fakegi.install()
        from minttweaks.modules.software.page import SoftwarePage
        from minttweaks.ui.widgets import AppContext
        ctx = AppContext(self.runner)
        page = SoftwarePage(ctx)
        plan = zen.preview(self.runner)
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), patch.object(zen, 'install') as install:
            page._confirm_zen(plan)
        install.assert_not_called()
        with patch.object(ctx, 'run_async'):
            ctx.run_operation('Other operation', lambda: None)
        page.error = Mock()
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), patch.object(zen, 'install') as install:
            page._confirm_zen(plan)
        install.assert_not_called()
        page.error.assert_called_once()
