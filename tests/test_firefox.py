"""Tests for the Firefox extension catalogue and policy writer."""

import copy
import json
import pathlib
import runpy
import tempfile
import unittest
from unittest import mock

from minttweaks.core.runner import Result
from minttweaks.modules.firefox import backend as firefox
from tests.fakes import FakeRunner

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "data" / "mtk-firefox"


def addon(identifier, kind="extension", location="app-profile"):
    return {"id": identifier, "type": kind, "location": location}


class CatalogueTests(unittest.TestCase):
    def test_catalogue_contains_every_requested_extension(self):
        self.assertEqual(len(firefox.CATALOG), 16)
        identifiers = [extension.id for extension in firefox.CATALOG]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertNotIn("support@goodlinks.app", identifiers)

    def test_install_urls_point_at_addons_mozilla_org(self):
        for extension in firefox.CATALOG:
            self.assertEqual(
                extension.install_url,
                f"https://addons.mozilla.org/firefox/downloads/latest/{extension.id}/latest.xpi",
            )

    def test_helper_allow_list_matches_the_catalogue(self):
        helper = runpy.run_path(str(HELPER))
        self.assertEqual(set(helper["ALLOWED"]), {extension.id for extension in firefox.CATALOG})
        for extension in firefox.CATALOG:
            self.assertEqual(helper["entry_for"](extension.id), extension.policy)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        self.base = self.home / ".mozilla" / "firefox"
        self.profile = self.base / "abcd.default-release"
        self.profile.mkdir(parents=True)
        (self.base / "profiles.ini").write_text(
            "[Profile0]\nName=default-release\nIsRelative=1\nPath=abcd.default-release\n"
            "Default=1\n\n[General]\nStartWithLastProfile=1\nVersion=2\n",
            encoding="utf-8",
        )

    def write_extensions(self, profile, *addons):
        (profile / "extensions.json").write_text(
            json.dumps({"addons": list(addons)}), encoding="utf-8"
        )

    def test_profiles_ini_is_read(self):
        self.assertEqual(firefox.profile_paths(self.home), [self.profile])

    def test_installed_extensions_ignores_builtins_and_themes(self):
        self.write_extensions(
            self.profile,
            addon("uBlock0@raymondhill.net"),
            addon("newtab@mozilla.org", location="app-builtin-addons"),
            addon("theme@example.com", kind="theme"),
            addon("addon@darkreader.org"),
        )
        self.assertEqual(
            firefox.installed_extension_ids(self.home),
            {"uBlock0@raymondhill.net", "addon@darkreader.org"},
        )

    def test_profiles_are_unioned(self):
        second = self.base / "efgh.default"
        second.mkdir()
        self.write_extensions(self.profile, addon("uBlock0@raymondhill.net"))
        self.write_extensions(second, addon("addon@darkreader.org"))
        (self.base / "profiles.ini").write_text(
            "[Profile0]\nPath=abcd.default-release\nIsRelative=1\n"
            "[Profile1]\nPath=efgh.default\nIsRelative=1\n",
            encoding="utf-8",
        )
        self.assertEqual(
            firefox.installed_extension_ids(self.home),
            {"uBlock0@raymondhill.net", "addon@darkreader.org"},
        )

    def test_invalid_extensions_json_is_ignored(self):
        (self.profile / "extensions.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(firefox.installed_extension_ids(self.home), set())

    def test_status_reports_installed_and_managed_extensions(self):
        self.write_extensions(self.profile, addon("uBlock0@raymondhill.net"))
        policy = self.home / "policies.json"
        policy.write_text(
            json.dumps(
                {
                    "policies": {
                        "ExtensionSettings": {
                            "addon@darkreader.org": firefox.EXTENSION_BY_ID["addon@darkreader.org"].policy
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        status = firefox.collect_status(self.home, policy)
        self.assertEqual(status.profiles, 1)
        self.assertEqual(status.installed_ids, {"uBlock0@raymondhill.net"})
        self.assertEqual(status.policy_ids, {"addon@darkreader.org"})
        self.assertEqual(status.policy_error, "")


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.ublock = firefox.EXTENSION_BY_ID["uBlock0@raymondhill.net"]
        self.darkreader = firefox.EXTENSION_BY_ID["addon@darkreader.org"]
        self.privacybadger = firefox.EXTENSION_BY_ID["jid1-MnnxcxisBPnSXQ@jetpack"]
        self.custom = {"installation_mode": "allowed"}

    def existing(self):
        return {
            "policies": {
                "Homepage": "https://example.com",
                "ExtensionSettings": {
                    "custom@example.com": self.custom,
                    self.ublock.id: self.ublock.policy,
                    self.privacybadger.id: self.privacybadger.policy,
                },
            }
        }

    def test_selection_is_merged_and_unselected_managed_entries_are_removed(self):
        merged = firefox.plan_policy(self.existing(), [self.ublock.id, self.darkreader.id])
        self.assertEqual(merged["policies"]["Homepage"], "https://example.com")
        settings = merged["policies"]["ExtensionSettings"]
        self.assertEqual(settings["custom@example.com"], self.custom)
        self.assertEqual(settings[self.ublock.id], self.ublock.policy)
        self.assertEqual(settings[self.darkreader.id], self.darkreader.policy)
        self.assertNotIn(self.privacybadger.id, settings)

    def test_empty_selection_removes_all_managed_entries(self):
        merged = firefox.plan_policy(self.existing(), [])
        settings = merged["policies"]["ExtensionSettings"]
        self.assertEqual(settings, {"custom@example.com": self.custom})
        self.assertEqual(merged["policies"]["Homepage"], "https://example.com")

    def test_foreign_entry_is_never_overwritten(self):
        existing = self.existing()
        existing["policies"]["ExtensionSettings"][self.ublock.id] = {
            "installation_mode": "force_installed",
            "install_url": self.ublock.install_url,
        }
        with self.assertRaises(firefox.PolicyError):
            firefox.plan_policy(existing, [self.ublock.id])

    def test_foreign_entry_is_preserved_when_not_selected(self):
        existing = self.existing()
        existing["policies"]["ExtensionSettings"][self.ublock.id] = {
            "installation_mode": "force_installed",
            "install_url": self.ublock.install_url,
        }
        merged = firefox.plan_policy(existing, [])
        self.assertEqual(
            merged["policies"]["ExtensionSettings"][self.ublock.id]["installation_mode"],
            "force_installed",
        )

    def test_unknown_extension_is_refused(self):
        with self.assertRaises(firefox.PolicyError):
            firefox.plan_policy({}, ["not-in-the-catalogue@example.com"])

    def test_invalid_extension_settings_is_refused(self):
        with self.assertRaises(firefox.PolicyError):
            firefox.plan_policy({"policies": {"ExtensionSettings": []}}, [])

    def test_load_policy_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "policies.json"
            path.write_text("{", encoding="utf-8")
            data, error = firefox.load_policy(path)
            self.assertIsNone(data)
            self.assertIn("not valid JSON", error)

    def test_load_policy_treats_a_missing_file_as_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, error = firefox.load_policy(pathlib.Path(tmp) / "policies.json")
            self.assertEqual(data, {})
            self.assertIsNone(error)

    def test_policy_extension_ids_only_counts_our_entries(self):
        document = self.existing()
        document["policies"]["ExtensionSettings"][self.ublock.id] = {
            "installation_mode": "force_installed",
            "install_url": self.ublock.install_url,
        }
        self.assertEqual(
            firefox.policy_extension_ids(document),
            {self.privacybadger.id},
        )


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = pathlib.Path(self.tmp.name)
        self.helper = self.directory / "mtk-firefox"
        self.helper.write_text("#!/usr/bin/python3\n", encoding="utf-8")
        self.helper.chmod(0o755)
        self.ublock = firefox.EXTENSION_BY_ID["uBlock0@raymondhill.net"]
        self.darkreader = firefox.EXTENSION_BY_ID["addon@darkreader.org"]

    def test_helper_receives_only_the_selected_entries(self):
        runner = FakeRunner()
        seen = {}

        def handler(command):
            seen["candidate"] = json.loads(pathlib.Path(command.argv[2]).read_text(encoding="utf-8"))
            return Result(str(command), 0, stdout="ok\n")

        runner.add_callable((str(self.helper), "install-policy"), handler)
        outcome = firefox.apply_policy(
            runner,
            [self.ublock.id, self.darkreader.id],
            policy_path=self.directory / "policies.json",
            helper=self.helper,
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(
            seen["candidate"],
            {self.ublock.id: self.ublock.policy, self.darkreader.id: self.darkreader.policy},
        )
        self.assertTrue(runner.calls[0].needs_root)

    def test_helper_failure_is_reported(self):
        runner = FakeRunner()
        runner.add((str(self.helper), "install-policy"), returncode=2, stderr="rejected\n")
        outcome = firefox.apply_policy(
            runner,
            [self.ublock.id],
            policy_path=self.directory / "policies.json",
            helper=self.helper,
        )
        self.assertFalse(outcome.ok)
        self.assertIn("rejected", outcome.output)

    def test_unknown_extension_is_refused_before_running_anything(self):
        runner = FakeRunner()
        outcome = firefox.apply_policy(
            runner,
            ["unknown@example.com"],
            policy_path=self.directory / "policies.json",
            helper=self.helper,
        )
        self.assertFalse(outcome.ok)
        self.assertEqual(runner.calls, [])

    def test_fallback_merges_and_installs_the_policy(self):
        policy = self.directory / "policies.json"
        policy.write_text(
            json.dumps({"policies": {"Homepage": "https://example.com"}}),
            encoding="utf-8",
        )
        runner = FakeRunner()
        seen = {}

        def handler(command):
            seen["installed"] = json.loads(pathlib.Path(command.argv[-2]).read_text(encoding="utf-8"))
            return Result(str(command), 0, stdout="ok\n")

        runner.add(("install", "-d"), stdout="ok\n")
        runner.add_callable(("install", "-o", "root"), handler)
        with mock.patch.object(firefox, "find_helper", return_value=None):
            outcome = firefox.apply_policy(
                runner,
                [self.ublock.id],
                policy_path=policy,
            )
        self.assertTrue(outcome.ok)
        self.assertEqual(seen["installed"]["policies"]["Homepage"], "https://example.com")
        self.assertIn(self.ublock.id, seen["installed"]["policies"]["ExtensionSettings"])
        self.assertEqual(
            [call.argv[0] for call in runner.calls],
            ["install", "install"],
        )


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.helper = runpy.run_path(str(HELPER))
        self.ublock = firefox.EXTENSION_BY_ID["uBlock0@raymondhill.net"]
        self.darkreader = firefox.EXTENSION_BY_ID["addon@darkreader.org"]

    def test_validate_candidate_accepts_catalogue_entries(self):
        candidate = {self.ublock.id: self.ublock.policy}
        self.assertIsNone(self.helper["validate_candidate"](candidate))

    def test_validate_candidate_rejects_foreign_entries_and_bad_urls(self):
        self.assertIsNotNone(
            self.helper["validate_candidate"]({"other@example.com": self.ublock.policy})
        )
        bad = copy.deepcopy(self.ublock.policy)
        bad["install_url"] = "https://example.com/evil.xpi"
        self.assertIsNotNone(self.helper["validate_candidate"]({self.ublock.id: bad}))

    def test_merge_preserves_foreign_policies_and_removes_unselected_entries(self):
        existing = {
            "policies": {
                "Homepage": "https://example.com",
                "ExtensionSettings": {
                    "custom@example.com": {"installation_mode": "allowed"},
                    self.ublock.id: self.ublock.policy,
                    self.darkreader.id: self.darkreader.policy,
                },
            }
        }
        merged = self.helper["merge"](existing, {self.ublock.id: self.ublock.policy})
        settings = merged["policies"]["ExtensionSettings"]
        self.assertEqual(merged["policies"]["Homepage"], "https://example.com")
        self.assertIn("custom@example.com", settings)
        self.assertIn(self.ublock.id, settings)
        self.assertNotIn(self.darkreader.id, settings)

    def test_merge_refuses_to_overwrite_a_foreign_entry(self):
        existing = {
            "policies": {
                "ExtensionSettings": {
                    self.ublock.id: {
                        "installation_mode": "force_installed",
                        "install_url": self.ublock.install_url,
                    }
                }
            }
        }
        with self.assertRaises(ValueError):
            self.helper["merge"](existing, {self.ublock.id: self.ublock.policy})

    def test_check_source_rejects_a_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = pathlib.Path(tmp) / "link.json"
            link.symlink_to(target)
            ok, _reason = self.helper["check_source"](link)
            self.assertFalse(ok)

    def test_check_source_accepts_a_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "candidate.json"
            target.write_text("{}", encoding="utf-8")
            ok, reason = self.helper["check_source"](target)
            self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
