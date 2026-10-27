"""Cinnamon captures are read-only; local profiles never replace prior files."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from minttweaks.modules.cinnamon import backend
from tests.fakes import FakeRunner


def make_runner(value="Mint-Y"):
    runner = FakeRunner()
    for setting in backend.SETTINGS:
        runner.add(["gsettings", "get", setting.schema, setting.key], stdout=repr(value) + "\n")
    return runner


class CaptureTests(unittest.TestCase):
    def test_all_reads_use_get_without_administrator_rights(self):
        runner = make_runner("Thème d’été")
        snapshot = backend.capture(runner)
        self.assertTrue(snapshot.complete)
        self.assertEqual(set(snapshot.values), backend.SETTING_IDS)
        self.assertTrue(all(value == "Thème d’été" for value in snapshot.values.values()))
        self.assertTrue(all(command.argv[:2] == ("gsettings", "get") and not command.needs_root for command in runner.calls))

    def test_empty_value_is_preserved_instead_of_inventing_a_default(self):
        snapshot = backend.capture(make_runner(""))
        self.assertTrue(snapshot.complete)
        self.assertEqual(set(snapshot.values.values()), {""})

    def test_missing_schema_does_not_hide_the_other_settings(self):
        runner = make_runner()
        runner.rules.pop(0)
        setting = backend.SETTINGS[0]
        runner.add(["gsettings", "get", setting.schema, setting.key], returncode=1, stderr="No such schema")
        snapshot = backend.capture(runner)
        self.assertFalse(snapshot.complete)
        self.assertNotIn(setting.id, snapshot.values)
        self.assertEqual(len(snapshot.values), len(backend.SETTINGS) - 1)
        self.assertIn("No such schema", snapshot.errors[setting.id])

    def test_invalid_or_non_string_values_are_unavailable(self):
        for raw in ("true", "['theme']", "'unterminated", '"a" "b"', "__import__('os').getcwd()"):
            with self.subTest(raw=raw):
                runner = FakeRunner().add(["gsettings"], stdout=raw)
                snapshot = backend.capture(runner)
                self.assertFalse(snapshot.complete)
                self.assertEqual(snapshot.values, {})

    def test_simulation_does_not_claim_settings_have_been_read(self):
        runner = make_runner()
        runner.dry_run = True
        snapshot = backend.capture(runner)
        self.assertFalse(snapshot.complete)
        self.assertFalse(runner.calls)


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "profiles"

    def test_unicode_round_trip_and_private_file_permissions(self):
        profile = backend.save_profile(make_runner(), "Bureau été", self.directory)
        catalog = backend.list_profiles(self.directory)
        self.assertEqual(catalog.profiles, [profile])
        self.assertEqual(catalog.errors, {})
        path = self.directory / (profile.id + ".json")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)

    def test_identical_names_and_path_like_names_do_not_overwrite_or_escape_the_store(self):
        first = backend.save_profile(make_runner("Original"), "../bureau", self.directory)
        second = backend.save_profile(make_runner("Updated"), "../bureau", self.directory)
        self.assertNotEqual(first.id, second.id)
        catalog = backend.list_profiles(self.directory)
        self.assertEqual(len(catalog.profiles), 2)
        self.assertEqual({profile.settings[backend.SETTINGS[0].id] for profile in catalog.profiles}, {"Original", "Updated"})
        self.assertFalse((self.directory.parent / "bureau").exists())

    def test_incomplete_capture_and_simulation_do_not_create_the_store(self):
        for simulated in (False, True):
            runner = FakeRunner()
            runner.dry_run = simulated
            with self.subTest(simulated=simulated), self.assertRaises(backend.ProfileError):
                backend.save_profile(runner, "Test", self.directory)
            self.assertFalse(self.directory.exists())

    def test_invalid_names_are_rejected_before_reading_any_settings(self):
        runner = make_runner()
        for name in ("", "   ", "x" * 81, "bad\nname", "bad\n", "bad\x00"):
            with self.subTest(name=name), self.assertRaises(backend.ProfileError):
                backend.save_profile(runner, name, self.directory)
        self.assertFalse(runner.calls)
        self.assertFalse(self.directory.exists())

    def test_corrupted_unsupported_and_symlink_profiles_are_preserved(self):
        profile = backend.save_profile(make_runner(), "Valid", self.directory)
        corrupted = self.directory / "broken.json"
        corrupted.write_text("{broken")
        linked = self.directory / "linked.json"
        linked.symlink_to(self.directory / (profile.id + ".json"))
        future = self.directory / (uuid.uuid4().hex + ".json")
        document = json.loads((self.directory / (profile.id + ".json")).read_text())
        document["schema_version"] = 99
        future.write_text(json.dumps(document))
        catalog = backend.list_profiles(self.directory)
        self.assertEqual(catalog.profiles, [profile])
        self.assertEqual(set(catalog.errors), {"broken.json", "linked.json", future.name})
        self.assertEqual(corrupted.read_text(), "{broken")
        self.assertTrue(linked.is_symlink())

    def test_uuid_collision_preserves_existing_bytes(self):
        identifier = uuid.uuid4()
        with patch.object(backend.uuid, "uuid4", return_value=identifier):
            first = backend.save_profile(make_runner("Original"), "First", self.directory)
            original = (self.directory / (first.id + ".json")).read_bytes()
            with self.assertRaises(FileExistsError):
                backend.save_profile(make_runner("New"), "Second", self.directory)
        self.assertEqual((self.directory / (first.id + ".json")).read_bytes(), original)
        self.assertEqual(len(list(self.directory.iterdir())), 1)

    def test_failed_publication_leaves_no_partial_profile(self):
        with patch.object(backend.os, "link", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                backend.save_profile(make_runner(), "Test", self.directory)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_missing_directory_is_a_valid_empty_catalog(self):
        self.assertEqual(backend.list_profiles(self.directory).profiles, [])
        self.assertFalse(self.directory.exists())

    def test_invalid_profile_strings_are_preserved_without_reaching_gtk(self):
        profile = backend.save_profile(make_runner(), "Valid", self.directory)
        path = self.directory / (profile.id + ".json")
        data = json.loads(path.read_text())
        data["settings"][backend.SETTINGS[0].id] = "\ud800"
        path.write_text(json.dumps(data))
        catalog = backend.list_profiles(self.directory)
        self.assertFalse(catalog.profiles)
        self.assertIn(path.name, catalog.errors)
        self.assertTrue(path.exists())

    def test_duplicate_json_keys_are_reported_without_hiding_other_profiles(self):
        profile = backend.save_profile(make_runner(), "Valid", self.directory)
        duplicate = self.directory / (uuid.uuid4().hex + ".json")
        duplicate.write_text('{"schema_version": 99, "schema_version": 1}')
        catalog = backend.list_profiles(self.directory)
        self.assertEqual(catalog.profiles, [profile])
        self.assertIn(duplicate.name, catalog.errors)

    def test_oversized_profile_is_reported_without_modification(self):
        self.directory.mkdir()
        path = self.directory / (uuid.uuid4().hex + ".json")
        contents = b" " * (backend.MAX_FILE_BYTES + 1)
        path.write_bytes(contents)
        catalog = backend.list_profiles(self.directory)
        self.assertFalse(catalog.profiles)
        self.assertIn(path.name, catalog.errors)
        self.assertEqual(path.read_bytes(), contents)
