"""Build every widget tree under the stub and feed it real backend payloads.

Widget construction is where typos live: a misspelled attribute, a wrong
`pack_start` arity, a helper called with the wrong arguments. Those failures only
appear when the page is instantiated, which normally needs a display. The stub in
:mod:`tests.fakegi` lets us instantiate the pages here and assert that they react
to genuine backend output (computed with ``FakeRunner``) without raising.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests import fakegi

fakegi.install()

from minttweaks.modules.firefox import backend as firefox  # noqa: E402
from minttweaks.modules.firefox.page import FirefoxPage  # noqa: E402
from minttweaks.modules.cinnamon.page import CinnamonPage  # noqa: E402
from minttweaks.modules.setup.page import SetupPage  # noqa: E402
from minttweaks.modules.software.page import SoftwarePage  # noqa: E402
from minttweaks.modules.terminal.page import TerminalPage  # noqa: E402
from minttweaks.modules.home import backend as home  # noqa: E402
from minttweaks.modules.home.page import HomePage  # noqa: E402
from minttweaks.modules.maintenance import backend as maint  # noqa: E402
from minttweaks.modules.maintenance.page import MaintenancePage  # noqa: E402
from minttweaks.modules.samba import backend as samba  # noqa: E402
from minttweaks.modules.samba.page import SambaPage  # noqa: E402
from minttweaks.modules.services import backend as svc  # noqa: E402
from minttweaks.modules.services.page import ServicesPage  # noqa: E402
from minttweaks.ui import widgets  # noqa: E402
from minttweaks.ui.window import MainWindow  # noqa: E402

from tests.fakes import LIST_UNIT_FILES, LIST_UNITS, FakeRunner, pdbedit_listv  # noqa: E402


def make_runner() -> FakeRunner:
    runner = FakeRunner()
    runner.add(["du"], stdout="1024\t/somewhere\n")
    runner.add(["apt-get", "-s", "autoremove"], stdout="0 upgraded, 0 newly installed, 0 to remove.\n")
    runner.add(["dpkg-query"], stdout="")
    runner.add(["uname", "-r"], stdout="6.8.0-45-generic\n")
    runner.add(["systemctl", "list-units"], stdout=LIST_UNITS)
    runner.add(["systemctl", "list-unit-files"], stdout=LIST_UNIT_FILES)
    runner.add(["systemctl", "is-active"], stdout="active\n")
    runner.add(["systemctl", "is-enabled"], stdout="enabled\n")
    runner.add(["pdbedit", "-L", "-v"], stdout=pdbedit_listv())
    runner.add(["testparm"], stdout="Loaded services file OK.\n")
    return runner


class ConstructionTests(unittest.TestCase):
    def setUp(self):
        self.ctx = widgets.AppContext(make_runner())

    def test_pages_can_be_built(self):
        for page_class in (HomePage, MaintenancePage, ServicesPage, SambaPage, FirefoxPage, CinnamonPage, SetupPage, SoftwarePage, TerminalPage):
            page = page_class(self.ctx)
            self.assertIsInstance(page, widgets.Page)

    def test_window_can_be_built(self):
        context = widgets.AppContext(make_runner())
        window = MainWindow(None, context)
        self.assertEqual(len(window.pages), 9)
        self.assertEqual(
            [page.page_name for page in window.pages],
            ["home", "maintenance", "services", "samba", "firefox", "cinnamon", "setup", "software", "terminal"],
        )

    def test_pages_start_empty_and_load_lazily(self):
        page = MaintenancePage(self.ctx)
        self.assertFalse(page._loaded)
        page.ensure_loaded()
        self.assertTrue(page._loaded)


class MaintenanceStateTests(unittest.TestCase):
    def setUp(self):
        self.runner = make_runner()
        self.ctx = widgets.AppContext(self.runner)
        self.page = MaintenancePage(self.ctx)

    def test_refresh_handles_an_empty_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = maint.collect_probe(self.runner, Path(tmp))
            kernels = maint.installed_kernels(self.runner)
        # Must not raise, and must leave the kernel selection empty.
        self.page._apply_refresh((probe, kernels))
        self.assertEqual(self.page.selected_kernels, [])

    def test_kernel_toggles_drive_the_purge_button(self):
        kernels = [
            maint.Kernel("6.8.0-40-generic", ("linux-image-6.8.0-40-generic",)),
            maint.Kernel("6.8.0-45-generic", ("linux-image-6.8.0-45-generic",), running=True),
        ]
        self.page._rebuild_kernels(kernels)
        removable = [k for k in kernels if k.version == "6.8.0-40-generic"]
        self.page._on_kernel_toggle(_Toggle(True), removable[0])
        self.assertEqual(self.page.selected_kernels, removable)
        self.page._on_kernel_toggle(_Toggle(False), removable[0])
        self.assertEqual(self.page.selected_kernels, [])

    def test_generic_autoremove_button_uses_the_preview_flow(self):
        with patch.object(self.page, "_on_autoremove") as preview, patch.object(self.page, "_execute") as execute:
            self.page._run_task(maint.TASK_BY_ID["apt_autoremove"])
        preview.assert_called_once_with()
        execute.assert_not_called()

    def test_confirmation_keeps_all_packages_and_passes_the_approved_plan(self):
        packages = [f"package-{number}" for number in range(40)]
        with patch.object(widgets, "confirm_list", return_value=True) as confirm, \
                patch.object(self.page, "_execute") as execute:
            self.page._confirm_autoremove(packages)
        self.assertEqual(confirm.call_args.args[2], packages)
        execute.assert_called_once_with(maint.TASK_BY_ID["apt_autoremove"], approved_packages=packages)

    def test_cancelled_preview_does_not_execute(self):
        self.page._busy = True
        with patch.object(widgets, "confirm_list", return_value=False), patch.object(self.page, "_execute") as execute:
            self.page._confirm_autoremove(["keep-me"])
        self.assertFalse(self.page._busy)
        execute.assert_not_called()

    def test_empty_preview_does_not_execute(self):
        self.page._busy = True
        with patch.object(self.page, "info"), patch.object(self.page, "refresh"), \
                patch.object(self.page, "_execute") as execute:
            self.page._confirm_autoremove([])
        self.assertFalse(self.page._busy)
        execute.assert_not_called()

    def test_confirmation_widget_preserves_the_complete_list(self):
        packages = [f"long-package-name-{number}" for number in range(500)]
        buffer = Mock()
        with patch.object(widgets, "text_view", return_value=(Mock(), Mock(), buffer)):
            widgets.confirm_list(None, "Preview", packages, "All packages")
        buffer.set_text.assert_called_once_with("\n".join(packages))

    def test_failed_preview_restores_controls(self):
        self.page._busy = True
        with patch.object(self.page, "error") as error:
            self.page._on_operation_error(maint.PreviewError("APT locked"))
        self.assertFalse(self.page._busy)
        error.assert_called_once()

    def test_busy_state_does_not_enable_root_actions_without_escalation(self):
        with patch.object(widgets, "escalation_available", return_value=False), \
                patch.object(self.page._task_buttons["apt_clean"], "set_sensitive") as sensitive:
            self.page._set_busy(False)
        sensitive.assert_called_once_with(False)


class ServicesStateTests(unittest.TestCase):
    def test_failed_refresh_marks_previous_units_as_stale_and_prevents_actions(self):
        units = [svc.Unit("smbd.service", active="active")]
        self.page._apply_units(units)
        self.page._units_failed(svc.ReadError("D-Bus unavailable"))
        self.assertEqual(self.page.units, units)
        self.assertFalse(self.page._units_current)
        self.page.selected = units[0]
        with patch.object(self.page, "run_operation") as run:
            self.page._control("restart")
        run.assert_not_called()

    def test_partial_journal_retains_its_failure_hint(self):
        self.page.selected = svc.Unit("smbd.service")
        with patch.object(self.page.log_hint, "set_text") as hint:
            self.page._apply_logs("smbd.service", svc.Result("journalctl", 124, stdout="partial logs", stderr="Timeout"))
        self.assertIn("Timeout", hint.call_args.args[0])

    def setUp(self):
        self.ctx = widgets.AppContext(make_runner())
        self.page = ServicesPage(self.ctx)

    def test_units_are_loaded_into_the_store(self):
        units = svc.list_units(self.page.ctx.runner)
        self.page._apply_units(units)
        self.assertEqual(len(self.page.units), len(units))
        self.assertTrue(any(unit.failed for unit in self.page.units))

    def test_boot_analysis_renders(self):
        self.page._apply_boot(svc.BootReport("Startup finished in 4.2s", [("5.1s", "foo.service")], "chain"))
        self.assertTrue(self.page.boot_summary)

    def test_journal_failure_shows_a_hint(self):
        self.page.selected = svc.Unit(name="smbd.service", active="active", sub="running")
        result = self.page.ctx.runner.run(["journalctl"])
        self.page._apply_logs("smbd.service", result)
        self.assertTrue(self.page.log_hint)


class HomeStateTests(unittest.TestCase):
    def test_refresh_passes_the_context_runner_to_the_diagnostic(self):
        report = home.HomeReport(home.SystemSummary(), [])

        def immediate(work, on_done, **kwargs):
            on_done(work())

        with patch.object(home, "collect_report", return_value=report) as collect, \
                patch.object(self.ctx, "run_async", side_effect=immediate):
            self.page.refresh()
        collect.assert_called_once_with(self.ctx.runner)
        self.assertIs(self.page.report, report)

    def test_unavailable_checks_do_not_produce_an_all_passed_message(self):
        report = home.HomeReport(home.SystemSummary(), [home.Finding("info", "Unavailable", completed=False)])
        with patch.object(self.page.checks_label, "set_text") as text:
            self.page._apply_report(report)
        self.assertIn("1 check(s) unavailable", text.call_args.args[0])
        self.assertNotIn("All", text.call_args.args[0])

    def setUp(self):
        self.ctx = widgets.AppContext(make_runner())
        self.page = HomePage(self.ctx)

    def test_report_updates_the_summary_and_findings(self):
        report = home.HomeReport(
            summary=home.SystemSummary(
                os_name="Linux Mint 22.1",
                kernel="6.8.0-45-generic",
                hostname="mintbox",
                uptime="1 h 2 min",
                memory_used="1.0 GB",
                memory_total="8.0 GB",
                memory_percent=12,
                disk_used="10.0 GB",
                disk_total="100.0 GB",
                disk_free="90.0 GB",
                disk_percent=10,
            ),
            findings=[
                home.Finding("ok", "Package database", "No half-configured package was found."),
                home.Finding("warn", "Old kernels", "2 old kernel(s) can be removed: 6.8.0-40"),
            ],
        )
        self.page._apply_report(report)
        self.assertEqual(self.page.report, report)

    def test_empty_report_is_handled(self):
        report = home.HomeReport(summary=home.SystemSummary(), findings=[])
        self.page._apply_report(report)
        self.assertIs(self.page.report, report)


class FirefoxStateTests(unittest.TestCase):
    def setUp(self):
        self.ctx = widgets.AppContext(make_runner())
        self.page = FirefoxPage(self.ctx)

    def test_status_with_installed_and_managed_extensions_renders(self):
        status = firefox.FirefoxStatus(
            profiles=1,
            installed_ids={"uBlock0@raymondhill.net"},
            policy_ids={"addon@darkreader.org"},
            firefox_found=True,
        )
        self.page._apply_status(status)
        self.assertEqual(self.page.status, status)

    def test_a_policy_read_error_disables_the_apply_button(self):
        status = firefox.FirefoxStatus(
            profiles=1,
            firefox_found=True,
            policy_error="permission denied",
        )
        self.page._apply_status(status)
        self.assertEqual(self.page.status.policy_error, "permission denied")


class SambaStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conf_path = Path(self.tmp.name) / "smb.conf"
        self.conf_path.write_text("[global]\n   workgroup = WORKGROUP\n\n[Docs]\n   path = /tmp\n")
        self.runner = make_runner()
        self.ctx = widgets.AppContext(self.runner)
        self.page = SambaPage(self.ctx)

    def tearDown(self):
        self.tmp.cleanup()

    def test_state_is_applied(self):
        status = samba.collect_status(self.runner, self.conf_path)
        doc = samba.load_document(self.runner, self.conf_path)
        self.page._apply_state((status, doc, samba.list_users(self.runner)))
        self.assertEqual([share.name for share in self.page.shares], ["Docs"])
        self.assertIsNotNone(self.page.doc)

    def test_missing_samba_is_reported(self):
        status = samba.SambaStatus(installed=False, missing_packages=list(samba.PACKAGES))
        doc = samba.load_document(self.runner, self.conf_path)
        self.page._apply_state((status, doc, []))
        self.assertTrue(self.page.status_labels["packages"])

    def test_share_form_is_filled_from_a_share(self):
        share = samba.Share(name="Docs", path="/tmp", read_only=True)
        self.page._share_to_form(share)
        self.assertIn("name", self.page.share_fields)

    def test_save_is_refused_without_escalation(self):
        self.page._can_escalate = False
        self.page.doc = samba.Document(self.conf_path, None, "", existed=True)
        errors = []
        self.page.error = lambda heading, detail="": errors.append((heading, detail))
        self.page._apply_conf_change(lambda conf: None, "unused")
        self.assertEqual(len(errors), 1)
        self.assertIn("Administrator", errors[0][0])

    def test_invalid_share_is_reported_without_running_anything(self):
        doc = samba.load_document(self.runner, self.conf_path)
        self.page.doc = doc
        self.page._can_escalate = True
        errors = []
        self.page.error = lambda heading, detail="": errors.append((heading, detail))
        before = len(self.runner.calls)
        self.page._apply_conf_change(
            lambda conf: " | ".join(samba.create_share(conf, samba.Share(name="ok", path="/nope"))),
            "unused",
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(self.runner.calls), before)


class _Toggle:
    """Stands in for a Gtk.CheckButton passed to a handler."""

    def __init__(self, active: bool) -> None:
        self._active = active

    def get_active(self) -> bool:
        return self._active


if __name__ == "__main__":
    unittest.main()
