"""Tests for the read-only Home diagnostics."""

import tempfile
import unittest
from pathlib import Path

from minttweaks.modules.home import backend as home
from tests.fakes import FakeRunner


def make_runner() -> FakeRunner:
    runner = FakeRunner()
    runner.add(["uname", "-r"], stdout="6.8.0-45-generic\n")
    runner.add(["dpkg", "--audit"], stdout="")
    runner.add(["apt-get", "check"], stdout="")
    runner.add(["systemctl", "--failed"], stdout="")
    runner.add(["journalctl"], stdout="")
    runner.add(["dpkg-query"], stdout="")
    return runner


class ParsingTests(unittest.TestCase):
    def test_os_release_parser(self):
        values = home.parse_os_release(
            'NAME="Linux Mint"\nPRETTY_NAME="Linux Mint 22.1 (Xia)"\n# comment\nVERSION_ID=22.1\n'
        )
        self.assertEqual(values["NAME"], "Linux Mint")
        self.assertEqual(values["PRETTY_NAME"], "Linux Mint 22.1 (Xia)")
        self.assertEqual(values["VERSION_ID"], "22.1")

    def test_meminfo_parser(self):
        total, available = home.parse_meminfo(
            "MemTotal:        8000000 kB\nMemAvailable:    6000000 kB\n"
        )
        self.assertEqual(total, 8000000 * 1024)
        self.assertEqual(available, 6000000 * 1024)

    def test_meminfo_falls_back_to_free(self):
        _total, available = home.parse_meminfo("MemTotal: 1000 kB\nMemFree: 500 kB\n")
        self.assertEqual(available, 500 * 1024)

    def test_uptime_formatting(self):
        self.assertEqual(home.format_uptime(90061), "1 d 1 h 1 min")
        self.assertEqual(home.format_uptime(3660), "1 h 1 min")
        self.assertEqual(home.format_uptime(120), "2 min")
        self.assertEqual(home.format_uptime(None), "unknown")


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        (self.directory / "os-release").write_text(
            'PRETTY_NAME="Linux Mint 22.1"\n', encoding="utf-8"
        )
        (self.directory / "meminfo").write_text(
            "MemTotal: 8000000 kB\nMemAvailable: 6000000 kB\n", encoding="utf-8"
        )
        (self.directory / "uptime").write_text("90061.00 100.00\n", encoding="utf-8")

    def test_summary_reads_the_machine(self):
        summary = home.collect_summary(
            make_runner(),
            os_release=self.directory / "os-release",
            meminfo=self.directory / "meminfo",
            uptime_file=self.directory / "uptime",
            root=self.directory,
        )
        self.assertEqual(summary.os_name, "Linux Mint 22.1")
        self.assertEqual(summary.kernel, "6.8.0-45-generic")
        self.assertEqual(summary.uptime, "1 d 1 h 1 min")
        self.assertEqual(summary.memory_percent, 25)
        self.assertTrue(summary.memory_measured)
        self.assertTrue(summary.disk_measured)
        self.assertNotEqual(summary.disk_total, "unknown")

    def test_missing_files_do_not_crash(self):
        summary = home.collect_summary(
            make_runner(),
            os_release=self.directory / "missing-os-release",
            meminfo=self.directory / "missing-meminfo",
            uptime_file=self.directory / "missing-uptime",
            root=self.directory,
        )
        self.assertEqual(summary.os_name, "unknown")
        self.assertEqual(summary.uptime, "unknown")
        self.assertFalse(summary.memory_measured)


class CheckTests(unittest.TestCase):
    def test_disk_thresholds(self):
        self.assertEqual(home.disk_finding(95, "1.0 GB").severity, "error")
        self.assertEqual(home.disk_finding(85, "1.0 GB").severity, "warn")
        self.assertEqual(home.disk_finding(50, "1.0 GB").severity, "ok")
        self.assertEqual(home.disk_finding(-1, "unknown").severity, "info")

    def test_reboot_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reboot-required"
            self.assertEqual(home.check_reboot(path).severity, "ok")
            path.write_text("", encoding="utf-8")
            self.assertEqual(home.check_reboot(path).severity, "warn")

    def test_boot_errors_are_reported(self):
        runner = FakeRunner()
        runner.add(["journalctl"], stdout="2026-10-22T10:00:00 host kernel: boom\n")
        finding = home.check_boot_errors(runner)
        self.assertEqual(finding.severity, "warn")
        self.assertIn("1", finding.detail)

    def test_unreadable_journal_is_informational(self):
        runner = FakeRunner()
        runner.add(["journalctl"], returncode=1, stderr="permission denied\n")
        self.assertEqual(home.check_boot_errors(runner).severity, "info")

    def test_missing_systemctl_is_informational(self):
        runner = FakeRunner()
        finding = home.check_failed_services(runner)
        self.assertEqual(finding.severity, "info")


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        (self.directory / "os-release").write_text(
            'PRETTY_NAME="Linux Mint 22.1"\n', encoding="utf-8"
        )
        (self.directory / "meminfo").write_text(
            "MemTotal: 8000000 kB\nMemAvailable: 6000000 kB\n", encoding="utf-8"
        )
        (self.directory / "uptime").write_text("120.00 100.00\n", encoding="utf-8")
        self.reboot = self.directory / "reboot-required"

    def report(self, runner):
        return home.collect_report(
            runner,
            os_release=self.directory / "os-release",
            meminfo=self.directory / "meminfo",
            uptime_file=self.directory / "uptime",
            root=self.directory,
            reboot_file=self.reboot,
        )

    def by_title(self, report):
        return {finding.title: finding for finding in report.findings}

    def test_healthy_report(self):
        report = self.report(make_runner())
        self.assertEqual(report.errors, 0)
        self.assertEqual(report.warnings, 0)
        self.assertGreater(report.passed, 0)
        self.assertEqual(report.summary.os_name, "Linux Mint 22.1")

    def test_problems_are_reported_with_their_severity(self):
        runner = FakeRunner()
        runner.add(["uname", "-r"], stdout="6.8.0-45-generic\n")
        runner.add(["dpkg", "--audit"], stdout="Package foo is half configured\n")
        runner.add(["apt-get", "check"], returncode=100, stderr="E: Unmet dependencies.\n")
        runner.add(
            ["systemctl", "--failed"],
            stdout="● broken.service loaded failed failed Broken service\n",
        )
        runner.add(["journalctl"], stdout="2026-10-22T10:00:00 host kernel: boom\n")
        runner.add(["dpkg-query"], stdout="")
        self.reboot.write_text("", encoding="utf-8")

        report = self.report(runner)
        findings = self.by_title(report)
        self.assertEqual(findings["Package database"].severity, "warn")
        self.assertEqual(findings["Dependencies"].severity, "error")
        self.assertEqual(findings["Failed services"].severity, "error")
        self.assertEqual(findings["Boot errors"].severity, "warn")
        self.assertEqual(findings["Restart required"].severity, "warn")
        self.assertGreaterEqual(report.errors, 1)
        self.assertGreaterEqual(report.warnings, 3)

    def test_findings_are_sorted_errors_first(self):
        runner = FakeRunner()
        runner.add(["uname", "-r"], stdout="6.8.0-45-generic\n")
        runner.add(["dpkg", "--audit"], stdout="")
        runner.add(["apt-get", "check"], returncode=100, stderr="broken\n")
        runner.add(["systemctl", "--failed"], stdout="")
        runner.add(["journalctl"], stdout="")
        runner.add(["dpkg-query"], stdout="")
        report = self.report(runner)
        severities = [home.SEVERITY_ORDER[finding.severity] for finding in report.findings]
        self.assertEqual(severities, sorted(severities))


if __name__ == "__main__":
    unittest.main()
