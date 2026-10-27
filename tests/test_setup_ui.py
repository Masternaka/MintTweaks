"""The guide navigates without pretending to execute or verify module actions."""

import unittest
from unittest.mock import Mock, patch

from tests import fakegi

fakegi.install()

from minttweaks.modules.setup import backend  # noqa: E402
from minttweaks.modules.setup.page import SetupPage  # noqa: E402
from minttweaks.ui.widgets import AppContext  # noqa: E402
from minttweaks.ui.window import PAGE_CLASSES  # noqa: E402
from tests.fakes import FakeRunner  # noqa: E402


class SetupPageTests(unittest.TestCase):
    def setUp(self):
        self.ctx = AppContext(FakeRunner())
        self.page = SetupPage(self.ctx)

    def test_every_step_targets_an_existing_page(self):
        pages = {page.page_name for page in PAGE_CLASSES}
        self.assertTrue(all(step.page in pages for step in backend.STEPS))

    def test_opening_next_step_skips_verified_steps_without_modifying_progress(self):
        self.page.plan = backend.Plan(selected=["health", "firefox"])
        self.page.plan.progress["health"].state = "verified"
        window = Mock()
        with patch.object(self.page, "get_toplevel", return_value=window), patch.object(backend, "save_plan") as save:
            self.page._open_next()
        window.show_page.assert_called_once_with("firefox")
        save.assert_not_called()
        self.assertEqual(self.page.plan.progress["firefox"].state, "pending")
        self.assertFalse(self.ctx.runner.calls)

    def test_unsaved_selection_cannot_launch_an_outdated_plan(self):
        self.page.plan = backend.Plan(selected=["health"])
        self.page._dirty = True
        with patch.object(self.page, "get_toplevel") as window:
            self.page._open_next()
        window.assert_not_called()

    def test_verification_is_an_explicit_user_action_and_carries_its_note(self):
        self.page.plan = backend.Plan(selected=["health"])
        with patch.object(self.page.step_combo, "get_active_id", return_value="health"), \
                patch.object(self.page.note_entry, "get_text", return_value="Checked in the module"), \
                patch.object(self.page, "_persist") as persist:
            self.page._save_result("verified")
        persist.assert_called_once_with(["health"], step_id="health", state="verified", note="Checked in the module")

    def test_read_error_disables_writes_without_resetting_existing_progress(self):
        self.page.plan = backend.Plan(selected=["health"])
        with patch.object(self.page.status_label, "set_text") as message:
            self.page._failed(backend.PlanError("Invalid saved checklist"))
        self.assertIn("Invalid saved checklist", message.call_args.args[0])
        self.assertTrue(self.page._read_failed)
        self.assertEqual(self.page.plan.selected, ["health"])
        with patch.object(self.page, "_persist") as save:
            self.page._save_selection()
        save.assert_not_called()

    def test_global_busy_reservation_refuses_progress_write(self):
        self.page.plan = backend.Plan(selected=["health"])
        with patch.object(self.ctx, "run_async"):
            self.ctx.run_operation("Another operation", lambda: None)
        with patch.object(backend, "save_plan") as save:
            self.page._persist(["health"])
        save.assert_not_called()
        self.assertFalse(self.page._busy)
        self.assertTrue(self.page._read_failed)
