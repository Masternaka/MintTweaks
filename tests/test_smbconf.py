"""Tests for the smb.conf model."""

import unittest

from minttweaks.core.smbconf import (
    DEFAULT_CONF,
    SmbConf,
    default_conf,
    merge_duplicate_keys,
    validate_share_name,
    validate_share_path,
)
from tests.fakes import sample_smb_conf


class RoundTripTests(unittest.TestCase):
    def test_untouched_file_round_trips_byte_for_byte(self):
        text = sample_smb_conf()
        self.assertEqual(SmbConf.parse(text).render(), text)

    def test_empty_document(self):
        self.assertEqual(SmbConf.parse("").render(), "")

    def test_no_trailing_newline_is_preserved(self):
        text = "[global]\n   workgroup = HOME"
        self.assertEqual(SmbConf.parse(text).render(), text)

    def test_comments_and_blank_lines_survive_an_edit(self):
        text = "# top comment\n\n[global]\n   ; inner\n   workgroup = WORKGROUP\n"
        conf = SmbConf.parse(text)
        conf.set("global", "workgroup", "OFFICE")
        rendered = conf.render()
        self.assertIn("# top comment", rendered)
        self.assertIn("   ; inner", rendered)
        self.assertIn("workgroup = OFFICE", rendered)
        self.assertEqual(rendered.count("\n"), text.count("\n"))

    def test_backslash_continuation_is_read_and_preserved(self):
        text = "[global]\n   passwd chat = *Enter\\snew\\s* %n\\n .\n"
        conf = SmbConf.parse(text)
        self.assertIn("%n", conf.global_get("passwd chat"))
        self.assertEqual(conf.render(), text)

    def test_default_template_is_parseable(self):
        conf = default_conf()
        self.assertEqual(conf.render(), DEFAULT_CONF)
        self.assertEqual(conf.global_get("workgroup"), "WORKGROUP")


class ParameterTests(unittest.TestCase):
    def setUp(self):
        self.conf = SmbConf.parse(sample_smb_conf())

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(self.conf.global_get("WORKGROUP"), "WORKGROUP")
        self.assertEqual(self.conf.get("documents", "PATH"), "/srv/documents")

    def test_set_updates_in_place_and_keeps_indentation(self):
        self.conf.set("global", "workgroup", "HOME")
        rendered = self.conf.render()
        self.assertIn("   workgroup = HOME", rendered)
        self.assertNotIn("   workgroup = WORKGROUP", rendered)

    def test_set_appends_missing_key_inside_the_section(self):
        self.conf.set("global", "netbios name suffix", "0")
        lines = self.conf.render().splitlines()
        index = lines.index("   netbios name suffix = 0")
        # Still before the next section header, and inside [global].
        self.assertLess(index, lines.index("[Documents]"))
        self.assertGreater(index, lines.index("[global]"))

    def test_set_creates_missing_section(self):
        self.conf.set("Photos", "path", "/srv/photos")
        self.assertTrue(self.conf.has_section("Photos"))
        self.assertEqual(self.conf.get("photos", "path"), "/srv/photos")

    def test_unset_removes_only_that_section(self):
        self.assertTrue(self.conf.unset("global", "log file"))
        self.assertIsNone(self.conf.global_get("log file"))
        self.assertFalse(self.conf.unset("global", "does not exist"))

    def test_items_last_wins(self):
        conf = SmbConf.parse("[global]\n  workgroup = A\n  workgroup = B\n")
        self.assertEqual(conf.get("global", "workgroup"), "B")
        self.assertEqual(len(conf.items("global")), 1)

    def test_remove_section(self):
        self.assertTrue(self.conf.remove_section("Documents"))
        self.assertFalse(self.conf.has_section("Documents"))
        self.assertEqual(self.conf.shares(), [])

    def test_rename_section_keeps_content(self):
        self.conf.rename_section("Documents", "Docs")
        self.assertEqual(self.conf.get("docs", "path"), "/srv/documents")

    def test_rename_rejects_existing_target(self):
        with self.assertRaises(ValueError):
            self.conf.rename_section("Documents", "global")


class DuplicateSectionTests(unittest.TestCase):
    TEXT = "[global]\n   workgroup = WORKGROUP\n\n[Share]\n   path = /srv/one\n\n[Share]\n   path = /srv/two\n"

    def test_duplicates_are_reported(self):
        conf = SmbConf.parse(self.TEXT)
        self.assertEqual(conf.duplicate_sections(), ["Share"])
        self.assertEqual(conf.render(), self.TEXT)

    def test_last_section_wins_when_reading(self):
        conf = SmbConf.parse(self.TEXT)
        self.assertEqual(conf.get("Share", "path"), "/srv/two")

    def test_writing_targets_the_last_block(self):
        conf = SmbConf.parse(self.TEXT)
        conf.set("Share", "guest ok", "yes")
        blocks = conf.render().split("[Share]")
        self.assertNotIn("guest ok", blocks[1])
        self.assertIn("guest ok = yes", blocks[2])

    def test_unset_clears_every_block(self):
        conf = SmbConf.parse(self.TEXT)
        self.assertTrue(conf.unset("Share", "path"))
        self.assertIsNone(conf.get("Share", "path"))

    def test_merge_duplicate_keys(self):
        conf = SmbConf.parse("[global]\n   workgroup = A\n   workgroup = B\n")
        removed = merge_duplicate_keys(conf)
        self.assertEqual(removed, ["global/workgroup"])
        self.assertEqual(conf.get("global", "workgroup"), "B")


class ValidationTests(unittest.TestCase):
    def test_share_name_accepted(self):
        for name in ("Documents", "Mes documents", "backup_2024", "public$", "A1"):
            self.assertIsNone(validate_share_name(name), name)

    def test_share_name_rejected(self):
        for name in ("", "   ", "global", "homes", "printers", "print$", "-dash", "bad]name", "a/b", "x" * 90):
            self.assertIsNotNone(validate_share_name(name), name)

    def test_share_name_conflict_with_existing_section(self):
        conf = SmbConf.parse(sample_smb_conf())
        self.assertIsNotNone(validate_share_name("Documents", conf))
        self.assertIsNone(validate_share_name("Documents2", conf))

    def test_share_path_rules(self):
        self.assertIsNotNone(validate_share_path(""))
        self.assertIsNotNone(validate_share_path("relative/path"))
        self.assertIsNotNone(validate_share_path("/"))
        self.assertIsNotNone(validate_share_path("/proc/1"))
        self.assertIsNotNone(validate_share_path("/sys/kernel"))
        self.assertIsNotNone(validate_share_path("/nope/does/not/exist", must_exist=True))
        self.assertIsNone(validate_share_path("/nope/does/not/exist", must_exist=False))

    def test_share_path_rejects_control_characters(self):
        self.assertIsNotNone(validate_share_path("/srv/with\x00nul"))


if __name__ == "__main__":
    unittest.main()
