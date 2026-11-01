"""Casper changes are restricted to confirmed installed systems."""

import unittest
from unittest.mock import patch

from minttweaks.modules.setup import livecheck
from tests.fakes import FakeRunner


class LiveCheckTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.runner.add(['findmnt'], stdout='ext4\n')
        self.runner.add(['systemctl', 'show'], stdout='LoadState=loaded\nUnitFileState=enabled\nActiveState=failed\n')
        self.boot = patch.object(livecheck.Path, 'read_text', return_value='root=UUID=test ro quiet').start()
        patch.object(livecheck.Path, 'exists', return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_live_boots_and_unknown_roots_cannot_be_changed(self):
        for boot in ('boot=casper', 'boot=live', 'rd.live.image'):
            self.boot.return_value = boot
            with self.subTest(boot=boot), self.assertRaises(RuntimeError):
                livecheck.disable(self.runner)
        self.assertEqual(self.runner.calls, [])
        self.boot.return_value = 'root=UUID=test'
        self.runner.rules.clear()
        self.runner.add(['findmnt'], stdout='overlay\n')
        with self.assertRaises(RuntimeError):
            livecheck.disable(self.runner)
        self.assertFalse(any(call.needs_root for call in self.runner.calls))

    def test_live_marker_overrides_disk_filesystem(self):
        with patch.object(livecheck.Path, 'exists', return_value=True):
            self.assertFalse(livecheck.inspect(self.runner).available)
        self.assertEqual(self.runner.calls, [])

    def test_failed_diagnostic_never_allows_mutation(self):
        self.runner.rules.clear()
        self.runner.add(['findmnt'], returncode=1, stderr='permission denied')
        with self.assertRaises(RuntimeError):
            livecheck.disable(self.runner)
        self.assertFalse(any(call.needs_root for call in self.runner.calls))

    def test_disable_and_reset_are_scoped_and_privileged(self):
        self.runner.add(['systemctl', 'disable'], stdout='disabled')
        self.runner.add(['systemctl', 'reset-failed'])
        livecheck.disable(self.runner)
        writes = [call for call in self.runner.calls if call.needs_root]
        self.assertEqual([call.argv for call in writes], [
            ('systemctl', 'disable', '--now', livecheck.UNIT),
            ('systemctl', 'reset-failed', livecheck.UNIT),
        ])

    def test_disable_failure_does_not_clear_failed_state(self):
        self.runner.add(['systemctl', 'disable'], returncode=1, stderr='authorization denied')
        with self.assertRaisesRegex(RuntimeError, 'authorization denied'):
            livecheck.disable(self.runner)
        self.assertFalse(self.runner.ran(['systemctl', 'reset-failed']))

    def test_missing_disabled_and_unknown_service_states_are_unavailable(self):
        for state in ('LoadState=not-found', 'LoadState=loaded\nUnitFileState=disabled\nActiveState=inactive', ''):
            self.runner.rules = [rule for rule in self.runner.rules if rule[0][0] != 'systemctl']
            self.runner.add(['systemctl', 'show'], stdout=state)
            with self.subTest(state=state):
                self.assertFalse(livecheck.inspect(self.runner).available)

    def test_simulation_never_runs_commands(self):
        self.runner.dry_run = True
        with self.assertRaises(RuntimeError):
            livecheck.disable(self.runner)
        self.assertEqual(self.runner.calls, [])
