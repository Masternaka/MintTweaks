"""Missing Samba server must expose installation instead of working actions."""

import unittest
from unittest.mock import patch

from tests import fakegi
fakegi.install()

from minttweaks.modules.samba import backend
from minttweaks.modules.samba.page import SambaPage
from minttweaks.ui.widgets import AppContext
from tests.fakes import FakeRunner


class SambaAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.ctx = AppContext(FakeRunner())
        self.page = SambaPage(self.ctx)
        self.page._can_escalate = True

    def test_missing_server_disables_actions(self):
        status = backend.SambaStatus(installed=False, firewall_available=True)
        for button in (self.page.start_button, self.page.reload_button,
                       self.page.firewall_button, self.page.connections_button):
            with patch.object(button, 'set_sensitive') as sensitive:
                self.page._apply_status(status)
                sensitive.assert_called_with(False)

    def test_missing_server_blocks_action_handlers(self):
        self.page.status = backend.SambaStatus(installed=False)
        with patch.object(self.page, 'run_operation') as operation, patch.object(self.ctx, 'run_async') as read:
            self.page._on_enable_sharing()
            self.page._on_reload()
            self.page._on_firewall()
            self.page._on_connections()
        operation.assert_not_called()
        read.assert_not_called()

    def test_empty_start_result_is_reported_as_an_error(self):
        with patch.object(self.ctx, 'log') as log, patch.object(self.page, 'refresh'), patch.object(self.page, 'error') as error:
            self.page._after_enable_sharing([])
        self.assertEqual(log.call_args.args[1], 'error')
        error.assert_called_once()

    def test_missing_server_reveals_installation_prompt(self):
        status = backend.SambaStatus(installed=False, missing_packages=['samba'])
        doc = backend.Document(backend.conf_path(), backend.SmbConf.parse('[global]\n'), '[global]\n', existed=False)
        with patch.object(self.page.install_bar, 'set_revealed') as revealed:
            self.page._apply_state((status, doc, []))
        revealed.assert_called_once_with(True)

    def test_ordinary_refresh_does_not_request_protected_user_list(self):
        status = backend.SambaStatus(installed=True)
        with patch.object(backend, "collect_status", return_value=status), \
                patch.object(backend, "load_document") as load, \
                patch.object(backend, "list_users") as users, \
                patch.object(self.ctx, "run_async", side_effect=lambda work, **kwargs: work()):
            self.page.refresh()
        users.assert_not_called()
        load.assert_called_once_with(self.ctx.runner, allow_escalation=False)

    def test_firewall_activation_requires_confirmation(self):
        self.page.status = backend.SambaStatus(installed=True, firewall_active=False)
        with patch.object(self.page, "confirm", return_value=False), \
                patch.object(self.page, "run_operation") as operation:
            self.page._on_firewall()
        operation.assert_not_called()

    def test_firewall_confirmation_passes_conditional_activation_choice(self):
        for active in (True, False, None):
            self.page.status = backend.SambaStatus(installed=True, firewall_active=active)
            with patch.object(self.page, "confirm", return_value=True), \
                    patch.object(self.page, "run_operation") as operation, \
                    patch.object(backend, "allow_samba_in_firewall") as allow:
                self.page._on_firewall()
                operation.call_args.args[0]()
            allow.assert_called_once_with(self.ctx.runner, enable_if_inactive=active is not True)
