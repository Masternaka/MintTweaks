"""Check profile state transitions without claiming real GTK validation."""

import unittest
import uuid
from unittest.mock import Mock, patch

from tests import fakegi

fakegi.install()

from minttweaks.modules.cinnamon import backend  # noqa: E402
from minttweaks.modules.cinnamon.page import CinnamonPage  # noqa: E402
from minttweaks.ui.widgets import AppContext  # noqa: E402
from tests.test_cinnamon import make_runner  # noqa: E402
from tests.test_cinnamon_apply import SettingsRunner  # noqa: E402


class CinnamonPageTests(unittest.TestCase):
    def setUp(self):
        self.ctx = AppContext(make_runner())
        self.page = CinnamonPage(self.ctx)

    def test_incomplete_capture_disables_save_without_hiding_available_values(self):
        snapshot = backend.capture(self.ctx.runner)
        missing = backend.SETTINGS[0].id
        snapshot.values.pop(missing)
        snapshot.errors[missing] = "No such schema"
        with patch.object(self.page.save_button, "set_sensitive") as sensitive:
            self.page._apply_state((snapshot, backend.Catalog(), ""))
        self.assertFalse(self.page.snapshot.complete)
        sensitive.assert_called_with(False)
        self.assertEqual(len(self.page.snapshot.values), len(backend.SETTINGS) - 1)

    def test_valid_capture_and_name_enable_save(self):
        self.page.snapshot = backend.capture(self.ctx.runner)
        with patch.object(self.page.name_entry, "get_text", return_value="My desktop"), \
                patch.object(self.page.save_button, "set_sensitive") as sensitive:
            self.page._update_save()
        sensitive.assert_called_with(True)

    def test_busy_operation_refuses_profile_creation_and_restores_the_page(self):
        self.page.snapshot = backend.capture(self.ctx.runner)
        with patch.object(self.ctx, "run_async"):
            self.ctx.run_operation("Existing operation", lambda: None)
        self.page.error = Mock()
        with patch.object(self.page.name_entry, "get_text", return_value="My desktop"), \
                patch.object(backend, "save_profile") as save:
            self.page._on_save()
        save.assert_not_called()
        self.assertFalse(self.page._saving)
        self.page.error.assert_called_once()

    def test_unreadable_catalog_preserves_previous_profiles_with_an_explicit_message(self):
        self.page.profiles = {"previous": object()}
        with patch.object(self.page.catalog_hint, "set_text") as hint:
            self.page._apply_state((backend.capture(self.ctx.runner), None, "Permission denied"))
        self.assertIn("Permission denied", hint.call_args.args[0])
        self.assertIn("previous", self.page.profiles)

    def test_refresh_uses_the_injected_runner_and_surfaces_catalog_errors(self):
        def immediate(work, on_done, **kwargs):
            on_done(work())

        with patch.object(self.ctx, "run_async", side_effect=immediate), \
                patch.object(backend, "list_profiles", return_value=backend.Catalog()):
            self.page.refresh()
        self.assertTrue(self.page.snapshot.complete)
        self.assertFalse(self.page._loading)

    def plan(self):
        runner = SettingsRunner()
        values = dict(runner.values)
        values[backend.SETTINGS[0].id] = "New theme"
        profile = backend.Profile(uuid.uuid4().hex, "Test", backend.timestamp(), values)
        return backend.preview_profile(runner, profile)

    def test_cancelled_preview_never_starts_a_modification(self):
        self.page._saving = True
        with patch("minttweaks.ui.widgets.confirm_list", return_value=False), \
                patch.object(self.page, "run_operation") as run:
            self.page._confirm_apply(self.plan(), False)
        run.assert_not_called()
        self.assertFalse(self.page._saving)

    def test_accepted_preview_shows_the_old_and_new_values_before_application(self):
        plan = self.plan()
        with patch("minttweaks.ui.widgets.confirm_list", return_value=True) as confirm, \
                patch.object(self.page, "run_operation") as run:
            self.page._confirm_apply(plan, False)
        self.assertIn("Original", confirm.call_args.args[2][0])
        self.assertIn("New theme", confirm.call_args.args[2][0])
        run.assert_called_once()
        with patch.object(backend, "apply_profile") as apply:
            run.call_args.args[0]()
        apply.assert_called_once_with(self.ctx.runner, plan)

    def test_restoration_previews_the_selected_backup(self):
        plan = self.plan()
        self.page.backups = {plan.profile.id: plan.profile}
        with patch.object(self.page.backup_combo, "get_active_id", return_value=plan.profile.id), \
                patch.object(self.ctx, "run_async") as run:
            self.page._on_preview(True)
        with patch.object(backend, "preview_profile", return_value=plan) as preview:
            run.call_args.args[0]()
        preview.assert_called_once_with(self.ctx.runner, plan.profile)

    def test_partial_recovery_is_shown_as_an_error_and_refreshes_backups(self):
        outcome = backend.ApplyOutcome(False, "Recovery incomplete", self.plan().profile, {"setting": "locked"})
        with patch.object(self.page, "error") as error, patch.object(self.page, "refresh") as refresh:
            self.page._after_apply(outcome)
        self.assertIn("locked", error.call_args.args[1])
        self.assertIn(outcome.backup.id, error.call_args.args[1])
        refresh.assert_called_once()
