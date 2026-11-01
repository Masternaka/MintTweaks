"""One scoped authorization covers installation and protected status reads."""

import json
import runpy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.modules.samba import backend
from tests.fakes import FakeRunner, pdbedit_listv

HELPER = Path(__file__).resolve().parent.parent / 'data/mtk-root'


def snapshot():
    return {'users': [0, pdbedit_listv(), ''],
            'firewall': [0, 'Status: active\nSamba ALLOW Anywhere\n', '']}


class SambaAuthorizationTests(unittest.TestCase):
    def test_install_and_following_diagnostics_use_one_privileged_command(self):
        runner = FakeRunner().add([str(HELPER), 'install-samba'],
                                 stdout='APT complete\nMTK_SAMBA_STATUS=' + json.dumps(snapshot()))
        with patch.object(backend, 'helper_path', return_value=HELPER), \
                patch.object(backend.shutil, 'which', return_value='/usr/sbin/ufw'):
            self.assertTrue(backend.install_packages(runner).ok)
            self.assertEqual(len(backend.list_users(runner)), 2)
            self.assertEqual(backend.firewall_state(runner), (True, True, True))
        self.assertEqual(len(runner.calls), 1)
        self.assertTrue(runner.calls[0].needs_root)

    def test_plain_firewall_refresh_never_requests_authorization(self):
        runner = FakeRunner().add(['ufw', 'status'], returncode=1, stderr='need root')
        with patch.object(backend.shutil, 'which', return_value='/usr/sbin/ufw'):
            self.assertEqual(backend.firewall_state(runner), (True, None, None))
        self.assertFalse(any(call.needs_root for call in runner.calls))

    def test_firewall_configuration_and_status_share_one_authorization(self):
        runner = FakeRunner().add([str(HELPER), 'enable-samba-firewall'],
                                 stdout='MTK_SAMBA_STATUS=' + json.dumps(snapshot()))
        with patch.object(backend, 'helper_path', return_value=HELPER):
            self.assertTrue(backend.allow_samba_in_firewall(runner, enable_if_inactive=True).ok)
        self.assertEqual(len(runner.calls), 1)
        self.assertTrue(runner.calls[0].needs_root)

    def test_refused_authorization_does_not_update_cached_status(self):
        runner = FakeRunner().add([str(HELPER)], returncode=126, stderr='not authorized')
        with patch.object(backend, 'helper_path', return_value=HELPER):
            self.assertFalse(backend.install_packages(runner).ok)
        self.assertFalse(hasattr(runner, 'samba_admin_status'))

    def test_helper_stops_after_failed_apt_update(self):
        helper = runpy.run_path(str(HELPER))
        with patch('os.geteuid', return_value=0), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 42)) as run:
            self.assertEqual(helper['main'](['mtk-root', 'install-samba']), 42)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ['/usr/bin/apt-get', 'update', '-qq'])

    def test_helper_installs_fixed_packages_and_reads_status_in_same_process(self):
        helper = runpy.run_path(str(HELPER))
        result = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        with patch('os.geteuid', return_value=0), patch('subprocess.run', return_value=result) as run, patch('builtins.print'):
            self.assertEqual(helper['main'](['mtk-root', 'install-samba']), 0)
        self.assertEqual(run.call_args_list[1].args[0], ['/usr/bin/apt-get', 'install', '-y', '--no-install-recommends', 'samba', 'smbclient', 'cifs-utils'])
        self.assertEqual(run.call_count, 4)

    def test_helper_rejects_arbitrary_package_arguments(self):
        helper = runpy.run_path(str(HELPER))
        with patch('os.geteuid', return_value=0), patch('subprocess.run') as run:
            self.assertEqual(helper['main'](['mtk-root', 'install-samba', 'other-package']), 1)
        run.assert_not_called()
