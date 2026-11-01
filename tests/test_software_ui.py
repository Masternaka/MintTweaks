"""Offline UI contracts for software selection and confirmation."""

import unittest
from unittest.mock import Mock, patch

from tests import fakegi

fakegi.install()

from minttweaks.modules.software import backend  # noqa: E402
from minttweaks.modules.software.page import SoftwarePage  # noqa: E402
from minttweaks.ui.widgets import AppContext  # noqa: E402
from tests.test_software import BrowserRunner  # noqa: E402


class SoftwarePageTests(unittest.TestCase):
    def setUp(self):
        self.runner = BrowserRunner()
        self.ctx = AppContext(self.runner)
        self.page = SoftwarePage(self.ctx)

    def test_cancelled_preview_does_not_start_installation(self):
        self.page._busy = True
        plan = backend.preview_install(self.runner, ["brave"])
        with patch("minttweaks.ui.widgets.confirm_list", return_value=False), patch.object(self.page, "run_operation") as run:
            self.page._confirm_install(plan)
        run.assert_not_called()
        self.assertFalse(self.page._busy)

    def test_confirmation_includes_sources_versions_and_all_dependency_lines(self):
        self.runner.extra_operations = [f"Inst dependency-{number} (1 source [amd64])" for number in range(50)]
        plan = backend.preview_install(self.runner, ["brave"])
        with patch("minttweaks.ui.widgets.confirm_list", return_value=False) as confirm:
            self.page._confirm_install(plan)
        text = "\n".join(confirm.call_args.args[2])
        self.assertIn(backend.APP_BY_ID["brave"].origin, text)
        self.assertIn(plan.specs[0], text)
        self.assertIn("dependency-49", text)

    def test_busy_reservation_refuses_installation_and_restores_controls(self):
        plan = backend.preview_install(self.runner, ["brave"])
        with patch.object(self.ctx, "run_async"):
            self.ctx.run_operation("Another operation", lambda: None)
        self.page.error = Mock()
        with patch("minttweaks.ui.widgets.confirm_list", return_value=True), patch.object(backend, "install") as install:
            self.page._confirm_install(plan)
        install.assert_not_called()
        self.page.error.assert_called_once()
        self.assertFalse(self.page._busy)

    def test_failed_verification_is_visible_and_does_not_report_success(self):
        outcome = backend.InstallOutcome(False, "Not verified", states={"brave": "Missing package"})
        with patch.object(self.page, "error") as error, patch.object(self.page, "refresh") as refresh:
            self.page._after_install(outcome)
        self.assertIn("Missing package", error.call_args.args[1])
        refresh.assert_called_once()

    def test_repository_confirmation_can_be_cancelled(self):
        with patch("minttweaks.ui.widgets.escalation_available", return_value=True), \
                patch.object(self.page, "confirm", return_value=False) as confirm, \
                patch.object(self.page, "run_operation") as operation:
            self.page._on_repository("brave")
        operation.assert_not_called()
        self.assertIn(backend.RECIPES["brave"].key_url, confirm.call_args.args[1])

    def test_unfinished_zen_repository_has_no_automatic_action(self):
        with patch.object(self.page, "run_operation") as operation:
            self.page._on_repository("zen")
        operation.assert_not_called()

    def test_repository_setup_is_followed_by_installation_preview(self):
        status = backend.collect_status(self.runner)
        with patch.object(self.page.checks["brave"], "set_active") as select, \
                patch.object(self.page, "_on_install") as preview:
            self.page._repository_ready("brave", status)
        select.assert_called_with(True)
        preview.assert_called_once()

    def test_repository_uses_shared_mutation_slot(self):
        with patch("minttweaks.ui.widgets.escalation_available", return_value=True), \
                patch.object(self.page, "confirm", return_value=True), \
                patch.object(self.page, "run_operation") as operation, \
                patch.object(backend, "configure_repository") as setup:
            self.page._on_repository("helium")
            self.assertTrue(self.page._busy)
            operation.call_args.args[0]()
        setup.assert_called_once_with(self.runner, "helium", on_line=self.ctx.log)
