"""Tests for the systemd services backend."""

import unittest

from minttweaks.modules.services import backend
from tests.fakes import LIST_UNIT_FILES, LIST_UNITS, FakeRunner


class ParseTests(unittest.TestCase):
    def test_parse_list_units_skips_the_failure_bullet(self):
        units = backend.parse_list_units(LIST_UNITS)
        self.assertIn("weird-fail.service", units)
        self.assertTrue(units["weird-fail.service"].failed)
        self.assertEqual(units["smbd.service"].description, "Samba SMB Daemon")

    def test_parse_unit_files_handles_two_and_three_columns(self):
        modern = backend.parse_unit_files(LIST_UNIT_FILES)
        self.assertEqual(modern["nmbd.service"], "disabled")
        legacy = backend.parse_unit_files("smbd.service enabled\nnmbd.service disabled\n")
        self.assertEqual(legacy, {"smbd.service": "enabled", "nmbd.service": "disabled"})

    def test_parse_ignores_junk_lines(self):
        text = "UNIT LOAD ACTIVE SUB DESCRIPTION\nloaded units listed.\nnot a unit\n"
        self.assertEqual(backend.parse_list_units(text), {})

    def test_list_units_merges_runtime_and_enablement(self):
        runner = FakeRunner()
        runner.add(["systemctl", "list-units"], stdout=LIST_UNITS)
        runner.add(["systemctl", "list-unit-files"], stdout=LIST_UNIT_FILES)
        units = {unit.name: unit for unit in backend.list_units(runner)}
        self.assertEqual(units["smbd.service"].active, "active")
        self.assertEqual(units["smbd.service"].enabled, "enabled")
        # Known only through list-unit-files.
        self.assertIn("nmbd.service", units)
        self.assertEqual(units["nmbd.service"].active, "inactive")
        self.assertEqual(list(units), sorted(units))

    def test_failed_units(self):
        runner = FakeRunner().add(["systemctl", "--failed"], stdout=LIST_UNITS)
        self.assertEqual([unit.name for unit in backend.failed_units(runner)], ["weird-fail.service"])

    def test_failed_units_empty(self):
        self.assertEqual(backend.failed_units(FakeRunner().add(["systemctl", "--failed"], stdout="")), [])


class ActionTests(unittest.TestCase):
    def test_valid_unit_names(self):
        for name in ("smbd.service", "getty@tty1.service", "systemd-fsck@dev-disk.service"):
            self.assertTrue(backend.valid_unit(name), name)

    def test_invalid_unit_names(self):
        for name in ("", "smbd", "smbd.service; rm -rf /", "smbd.socket", "..service", "a b.service"):
            self.assertFalse(backend.valid_unit(name), name)

    def test_control_builds_an_argv_not_a_string(self):
        runner = FakeRunner().add(["systemctl"], returncode=0)
        result = backend.control(runner, "smbd.service", "restart")
        self.assertTrue(result.ok)
        self.assertEqual(runner.commands()[-1], ("systemctl", "restart", "smbd.service"))
        self.assertTrue(runner.calls[-1].needs_root)

    def test_control_rejects_bad_input(self):
        runner = FakeRunner()
        self.assertFalse(backend.control(runner, "smbd.service", "explode").ok)
        self.assertFalse(backend.control(runner, "nope", "start").ok)
        self.assertFalse(runner.ran(["systemctl"]))

    def test_journal_refuses_bad_unit(self):
        self.assertFalse(backend.journal(FakeRunner(), "smbd.service -u evil").ok)

    def test_journal_clamps_line_count(self):
        runner = FakeRunner().add(["journalctl"], stdout="line\n")
        backend.journal(runner, "smbd.service", lines=999999)
        argv = runner.commands()[-1]
        index = argv.index("-n")
        self.assertEqual(argv[index + 1], "5000")

    def test_journal_without_unit_watches_the_system(self):
        runner = FakeRunner().add(["journalctl"], stdout="line\n")
        backend.journal(runner)
        self.assertNotIn("-u", runner.commands()[-1])


class AnalysisTests(unittest.TestCase):
    def test_boot_blame(self):
        runner = FakeRunner().add(
            ["systemd-analyze", "blame"],
            stdout="5.123s NetworkManager-wait-online.service\n1.001s apt-daily.service\n",
        )
        self.assertEqual(
            backend.boot_blame(runner),
            [("5.123s", "NetworkManager-wait-online.service"), ("1.001s", "apt-daily.service")],
        )

    def test_boot_blame_returns_nothing_when_unavailable(self):
        self.assertEqual(backend.boot_blame(FakeRunner()), [])


if __name__ == "__main__":
    unittest.main()
