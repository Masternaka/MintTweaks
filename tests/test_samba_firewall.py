"""UFW activation is confirmed, checked and completed before Samba rules."""

import runpy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

HELPER = Path(__file__).resolve().parent.parent / 'data/mtk-root'


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.helper = runpy.run_path(str(HELPER))
        self.commands = []
        self.active = False
        self.fail = None

    def reply(self, argv, **kwargs):
        self.commands.append(argv[1:])
        if argv[1:] == self.fail:
            return subprocess.CompletedProcess(argv, 1, '', 'operation failed')
        if argv[1:] == ['--force', 'enable']:
            self.active = True
        text = ''
        if argv[1:] == ['status']:
            text = 'Status: active\nSamba ALLOW Anywhere\n' if self.active else 'Status: inactive\n'
        return subprocess.CompletedProcess(argv, 0, text, '')

    def configure(self, enable):
        with patch('subprocess.run', side_effect=self.reply), patch('builtins.print'):
            return self.helper['configure_samba_firewall'](enable)

    def test_inactive_firewall_is_enabled_before_adding_rules(self):
        self.assertEqual(self.configure(True), 0)
        self.assertEqual(self.commands, [['status'], ['app', 'info', 'Samba'], ['--force', 'enable'], ['allow', 'Samba'], ['status']])

    def test_active_firewall_is_not_reenabled(self):
        self.active = True
        self.assertEqual(self.configure(False), 0)
        self.assertNotIn(['--force', 'enable'], self.commands)
        self.assertIn(['allow', 'Samba'], self.commands)

    def test_inactive_firewall_without_consent_is_left_unchanged(self):
        self.assertNotEqual(self.configure(False), 0)
        self.assertEqual(self.commands, [['status']])

    def test_failed_activation_never_adds_rules(self):
        self.fail = ['--force', 'enable']
        self.assertNotEqual(self.configure(True), 0)
        self.assertNotIn(['allow', 'Samba'], self.commands)

    def test_missing_profile_never_activates_firewall(self):
        self.fail = ['app', 'info', 'Samba']
        self.assertNotEqual(self.configure(True), 0)
        self.assertNotIn(['--force', 'enable'], self.commands)

    def test_failed_status_is_not_treated_as_inactive(self):
        self.fail = ['status']
        self.assertNotEqual(self.configure(True), 0)
        self.assertEqual(self.commands, [['status']])
