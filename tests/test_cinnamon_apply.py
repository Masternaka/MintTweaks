"""Verify state transitions with a mutable GSettings double, never the desktop."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from minttweaks.core.runner import Result
from minttweaks.modules.cinnamon import backend
from tests.fakes import FakeRunner


class SettingsRunner(FakeRunner):
    def __init__(self):
        super().__init__()
        self.values = {setting.id: "Original" for setting in backend.SETTINGS}
        self.locked = set()
        self.write_hook = None
        self.add_callable(["gsettings", "get"], self.get_value)
        self.add_callable(["gsettings", "writable"], self.writable)
        self.add_callable(["gsettings", "set"], self.set_value)

    def get_value(self, command):
        key = command.argv[2] + "/" + command.argv[3]
        return Result(str(command), 0, stdout=repr(self.values[key]))

    def writable(self, command):
        key = command.argv[2] + "/" + command.argv[3]
        return Result(str(command), 0, stdout="false" if key in self.locked else "true")

    def set_value(self, command):
        key = command.argv[2] + "/" + command.argv[3]
        value = json.loads(command.argv[4])
        if self.write_hook is not None:
            result = self.write_hook(command, key, value)
            if result is not None:
                return result
        self.values[key] = value
        return Result(str(command), 0)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backups = Path(self.tmp.name) / "backups"
        self.runner = SettingsRunner()
        self.original = dict(self.runner.values)
        self.first, self.second = (setting.id for setting in backend.SETTINGS[:2])
        values = dict(self.original)
        values[self.first] = "Target one"
        values[self.second] = "Target two"
        self.profile = backend.Profile(uuid.uuid4().hex, "Test", backend.timestamp(), values)

    def apply(self, plan=None):
        return backend.apply_profile(self.runner, plan or backend.preview_profile(self.runner, self.profile), self.backups)

    def writes(self):
        return [command for command in self.runner.calls if command.argv[:2] == ("gsettings", "set")]

    def test_preview_is_read_only_and_contains_only_differences(self):
        plan = backend.preview_profile(self.runner, self.profile)
        self.assertEqual([setting.id for setting in plan.changes], [self.first, self.second])
        self.assertFalse(self.writes())
        self.assertFalse(self.backups.exists())

    def test_complete_backup_exists_before_the_first_write(self):
        def check_backup(command, key, value):
            catalog = backend.list_profiles(self.backups)
            self.assertEqual(len(catalog.profiles), 1)
            self.assertEqual(catalog.profiles[0].settings, self.original)
        self.runner.write_hook = check_backup
        outcome = self.apply()
        self.assertTrue(outcome.ok)
        self.assertEqual(self.runner.values, self.profile.settings)
        self.assertEqual(len(self.writes()), 2)
        self.assertTrue(all(not command.needs_root for command in self.runner.calls))

    def test_stale_preview_is_refused_without_backup_or_writes(self):
        plan = backend.preview_profile(self.runner, self.profile)
        self.runner.values[self.first] = "Changed outside"
        with self.assertRaises(backend.ProfileError):
            self.apply(plan)
        self.assertFalse(self.writes())
        self.assertFalse(self.backups.exists())

    def test_locked_settings_are_checked_before_preview_and_before_application(self):
        plan = backend.preview_profile(self.runner, self.profile)
        self.runner.locked.add(self.first)
        for action in (lambda: backend.preview_profile(self.runner, self.profile), lambda: self.apply(plan)):
            with self.assertRaises(backend.ProfileError):
                action()
        self.assertFalse(self.writes())
        self.assertFalse(self.backups.exists())

    def test_simulation_never_writes_settings_or_backups(self):
        plan = backend.preview_profile(self.runner, self.profile)
        self.runner.dry_run = True
        count = len(self.runner.calls)
        outcome = self.apply(plan)
        self.assertTrue(outcome.simulated)
        self.assertEqual(len(self.runner.calls), count)
        self.assertFalse(self.backups.exists())

    def test_backup_failure_prevents_all_settings_writes(self):
        with patch.object(backend, "store_snapshot", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.apply()
        self.assertFalse(self.writes())

    def test_failed_command_that_already_wrote_a_value_is_rolled_back(self):
        def fail_once(command, key, value):
            if key == self.second and value == "Target two":
                self.runner.values[key] = value
                return Result(str(command), 1, stderr="Failed after writing")
        self.runner.write_hook = fail_once
        outcome = self.apply()
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.rollback_errors, {})
        self.assertEqual(self.runner.values, self.original)
        self.assertEqual(len(backend.list_profiles(self.backups).profiles), 1)

    def test_silent_write_failure_is_detected_by_readback(self):
        self.runner.write_hook = lambda command, key, value: Result(str(command), 0)
        outcome = self.apply()
        self.assertFalse(outcome.ok)
        self.assertEqual(self.runner.values, self.original)

    def test_failed_rollback_is_reported_and_keeps_the_backup(self):
        def fail(command, key, value):
            if (key == self.second and value == "Target two") or (key == self.first and value == "Original"):
                return Result(str(command), 1, stderr="Write refused")
        self.runner.write_hook = fail
        outcome = self.apply()
        self.assertFalse(outcome.ok)
        self.assertIn(self.first, outcome.rollback_errors)
        self.assertEqual(self.runner.values[self.first], "Target one")
        self.assertTrue((self.backups / (outcome.backup.id + ".json")).exists())

    def test_recovery_does_not_overwrite_an_external_change(self):
        def interfere(command, key, value):
            if key == self.second and value == "Target two":
                self.runner.values[self.first] = "External change"
                return Result(str(command), 1, stderr="Failure")
        self.runner.write_hook = interfere
        outcome = self.apply()
        self.assertIn(self.first, outcome.rollback_errors)
        self.assertEqual(self.runner.values[self.first], "External change")

    def test_recovery_is_verified_again_after_all_rollback_writes(self):
        def interfere(command, key, value):
            if key == self.second and value == "Target two":
                self.runner.values[key] = value
                return Result(str(command), 1, stderr="Failure after writing")
            if key == self.first and value == "Original":
                self.runner.values[self.second] = "Changed during recovery"
        self.runner.write_hook = interfere
        outcome = self.apply()
        self.assertFalse(outcome.ok)
        self.assertIn(self.second, outcome.rollback_errors)
        self.assertEqual(self.runner.values[self.second], "Changed during recovery")

    def test_restoration_has_its_own_preview_and_backup(self):
        outcome = self.apply()
        restore_plan = backend.preview_profile(self.runner, outcome.backup)
        restored = self.apply(restore_plan)
        self.assertTrue(restored.ok)
        self.assertEqual(self.runner.values, self.original)
        self.assertEqual(restored.backup.settings, self.profile.settings)
        self.assertEqual(len(backend.list_profiles(self.backups).profiles), 2)

    def test_noop_does_not_create_a_backup_or_write_values(self):
        self.runner.values = dict(self.profile.settings)
        self.assertTrue(self.apply().ok)
        self.assertFalse(self.writes())
        self.assertFalse(self.backups.exists())

    def test_quotes_and_unicode_are_passed_as_one_typed_string_argument(self):
        self.profile.settings[self.first] = 'Thème d’été "bleu" \\ 😀'
        self.assertTrue(self.apply().ok)
        command = self.writes()[0]
        self.assertEqual(len(command.argv), 5)
        self.assertEqual(json.loads(command.argv[-1]), self.profile.settings[self.first])

    def test_invalid_profile_is_rejected_before_any_command(self):
        self.profile.settings["unknown/schema"] = "anything"
        with self.assertRaises(backend.ProfileError):
            backend.preview_profile(self.runner, self.profile)
        self.assertFalse(self.runner.calls)
