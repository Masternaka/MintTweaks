"""No real packages or repositories are changed by these tests."""

import unittest

from minttweaks.core.runner import Result
from minttweaks.modules.software import backend
from tests.fakes import FakeRunner


class BrowserRunner(FakeRunner):
    def __init__(self):
        super().__init__()
        self.arch = "amd64"
        self.installed = {}
        self.versions = {app.package: "1.2.3" for app in backend.CATALOG}
        self.origins = {app.package: [app.origin] for app in backend.CATALOG}
        self.suites = {app.package: app.suite for app in backend.CATALOG}
        self.extra_operations = []
        self.install_rc = 0
        self.keep_absent = False
        self.add_callable(["dpkg", "--print-architecture"], lambda command: Result(str(command), 0, stdout=self.arch))
        self.add_callable(["dpkg-query"], self.query)
        self.add_callable(["apt-cache", "policy"], self.policy)
        self.add_callable(["apt-get", "-s"], self.simulate)
        self.add_callable(["apt-get", "-y"], self.execute)

    def query(self, command):
        package = command.argv[-1]
        if package in self.installed:
            return Result(str(command), 0, stdout="install ok installed\t" + self.installed[package] + "\n")
        return Result(str(command), 1, stderr="dpkg-query: no packages found matching " + package)

    def policy(self, command):
        package = command.argv[-1].split(":")[0]
        version = self.versions[package]
        sources = "\n".join("        500 " + origin + " " + self.suites[package] + " amd64 Packages" for origin in self.origins[package])
        return Result(str(command), 0, stdout=f"{package}:\n  Installed: (none)\n  Candidate: {version}\n  Version table:\n     {version} 500\n{sources}\n")

    def simulate(self, command):
        specs = command.argv[command.argv.index("--") + 1:]
        lines = []
        for spec in specs:
            package, version = spec.split("=", 1)
            lines += [f"Inst {package} ({version} source [amd64])", f"Conf {package} ({version} source [amd64])"]
        return Result(str(command), 0, stdout="\n".join(lines + self.extra_operations))

    def execute(self, command):
        if self.install_rc == 0 and not self.keep_absent:
            for spec in command.argv[command.argv.index("--") + 1:]:
                package, version = spec.split("=", 1)
                self.installed[package.split(":")[0]] = version
        return Result(str(command), self.install_rc, stderr="Installation refused" if self.install_rc else "")


class SoftwareTests(unittest.TestCase):
    def setUp(self):
        self.runner = BrowserRunner()

    def test_native_catalog_has_only_the_three_requested_browsers(self):
        self.assertEqual(set(backend.APP_BY_ID), {"helium", "brave", "zen"})
        self.assertIn("Unofficial", backend.APP_BY_ID["zen"].source_msgid)
        self.assertNotEqual(backend.APP_BY_ID["brave"].origin, backend.CENTRAL)

    def test_package_state_distinguishes_absence_from_query_failure(self):
        self.assertFalse(backend.package_state(self.runner, "brave-browser").installed)
        broken = FakeRunner().add(["dpkg-query"], returncode=1, stderr="Permission denied")
        with self.assertRaises(backend.SoftwareError):
            backend.package_state(broken, "brave-browser")

    def test_installed_versions_are_displayed_without_becoming_reinstall_candidates(self):
        self.runner.installed["brave-browser"] = "1.0"
        status = backend.collect_status(self.runner)["brave"]
        self.assertTrue(status.installed)
        self.assertEqual(status.installed_version, "1.0")
        self.assertFalse(status.installable)

    def test_wrong_or_ambiguous_origins_disable_installation(self):
        for origins in (["https://example.invalid/"], [backend.APP_BY_ID["brave"].origin, "https://example.invalid/"]):
            self.runner.origins["brave-browser"] = origins
            status = backend.collect_status(self.runner)["brave"]
            self.assertFalse(status.installable)
            self.assertTrue(status.error)

    def test_missing_candidates_and_insecure_sources_are_refused(self):
        for origin in ("http://brave-browser-apt-release.s3.brave.com/", "file:/tmp/packages"):
            self.runner.origins["brave-browser"] = [origin]
            with self.assertRaises(backend.SoftwareError):
                backend.preview_install(self.runner, ["brave"])
        with self.assertRaises(backend.SoftwareError):
            backend.parse_candidate("Candidate: (none)", backend.CENTRAL)

    def test_architecture_is_checked_per_source(self):
        self.runner.arch = "arm64"
        status = backend.collect_status(self.runner)
        self.assertTrue(status["brave"].installable)
        self.assertTrue(status["helium"].installable)
        self.assertFalse(status["zen"].installable)

    def test_prerelease_suite_at_the_same_official_helium_url_is_not_accepted(self):
        self.runner.suites["helium-bin"] = "prerelease/main"
        self.assertFalse(backend.collect_status(self.runner)["helium"].installable)

    def test_unknown_packages_cannot_reach_the_runner(self):
        for selection in (["vlc"], ["--anything"], ["brave", "brave"], []):
            with self.subTest(selection=selection), self.assertRaises(backend.SoftwareError):
                backend.preview_install(self.runner, selection)
        self.assertFalse(self.runner.calls)

    def test_preview_retains_dependencies_and_does_not_need_root(self):
        self.runner.extra_operations = ["Inst dependency [1.0] (2.0 source [amd64])"]
        plan = backend.preview_install(self.runner, ["brave"])
        self.assertIn(self.runner.extra_operations[0], plan.output)
        self.assertTrue(all(not command.needs_root for command in self.runner.calls))
        self.assertFalse(self.runner.installed)

    def test_removal_proposals_are_refused(self):
        self.runner.extra_operations = ["Remv unrelated-package [1.0]"]
        with self.assertRaises(backend.SoftwareError):
            backend.preview_install(self.runner, ["brave"])
        self.assertFalse(any(command.needs_root for command in self.runner.calls))

    def test_candidate_change_requires_a_new_preview(self):
        plan = backend.preview_install(self.runner, ["brave"])
        self.runner.versions["brave-browser"] = "2.0"
        with self.assertRaises(backend.SoftwareError):
            backend.install(self.runner, plan)
        self.assertFalse(self.runner.installed)

    def test_flat_zen_policy_without_an_architecture_column_is_supported(self):
        text = f"zen-browser:\n  Candidate: 1.2\n  Version table:\n     1.2 500\n        500 {backend.CENTRAL} ./ Packages\n"
        self.assertEqual(backend.parse_candidate(text, backend.CENTRAL, "./"), "1.2")

    def test_dependency_change_requires_a_new_preview(self):
        plan = backend.preview_install(self.runner, ["brave"])
        self.runner.extra_operations = ["Inst new-dependency (1 source [amd64])"]
        with self.assertRaises(backend.SoftwareError):
            backend.install(self.runner, plan)
        self.assertFalse(self.runner.installed)

    def test_install_pins_versions_refuses_removals_and_verifies_the_result(self):
        plan = backend.preview_install(self.runner, ["helium", "brave", "zen"])
        outcome = backend.install(self.runner, plan)
        self.assertTrue(outcome.ok)
        commands = [command for command in self.runner.calls if command.needs_root]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].argv[:2], ("apt-get", "-y"))
        self.assertIn("--no-remove", commands[0].argv)
        self.assertTrue(all(spec in commands[0].argv for spec in plan.specs))
        self.assertTrue(all(":amd64=" in spec for spec in plan.specs))
        self.assertEqual(len(self.runner.installed), 3)

    def test_command_success_without_installed_packages_is_not_a_verified_installation(self):
        self.runner.keep_absent = True
        outcome = backend.install(self.runner, backend.preview_install(self.runner, ["brave"]))
        self.assertFalse(outcome.ok)
        self.assertIn("brave", outcome.states)

    def test_authentication_or_apt_failure_does_not_trigger_uninstall(self):
        self.runner.install_rc = 126
        outcome = backend.install(self.runner, backend.preview_install(self.runner, ["brave"]))
        self.assertFalse(outcome.ok)
        self.assertFalse(self.runner.ran(["apt-get", "remove"]))
        self.assertFalse(self.runner.ran(["apt-get", "purge"]))

    def test_simulation_performs_no_query_or_installation(self):
        plan = backend.preview_install(self.runner, ["brave"])
        count = len(self.runner.calls)
        self.runner.dry_run = True
        outcome = backend.install(self.runner, plan)
        self.assertTrue(outcome.ok)
        self.assertEqual(len(self.runner.calls), count)
        self.assertFalse(self.runner.installed)
