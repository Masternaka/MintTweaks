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

from tests import fakegi

fakegi.install()

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
        for page_class in (MaintenancePage, ServicesPage, SambaPage):
            page = page_class(self.ctx)
            self.assertIsInstance(page, widgets.Page)

    def test_window_can_be_built(self):
        context = widgets.AppContext(make_runner())
        window = MainWindow(None, context)
        self.assertEqual(len(window.pages), 3)
        self.assertEqual(
            [page.page_name for page in window.pages],
            ["maintenance", "services", "samba"],
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


class ServicesStateTests(unittest.TestCase):
    def setUp(self):
        self.ctx = widgets.AppContext(make_runner())
        self.page = ServicesPage(self.ctx)

    def test_units_are_loaded_into_the_store(self):
        units = svc.list_units(self.page.ctx.runner)
        self.page._apply_units(units)
        self.assertEqual(len(self.page.units), len(units))
        self.assertTrue(any(unit.failed for unit in self.page.units))

    def test_boot_analysis_renders(self):
        self.page._apply_boot(("Startup finished in 4.2s", [("5.1s", "foo.service")], "chain"))
        self.assertTrue(self.page.boot_summary)

    def test_journal_failure_shows_a_hint(self):
        self.page.selected = svc.Unit(name="smbd.service", active="active", sub="running")
        result = self.page.ctx.runner.run(["journalctl"])
        self.page._apply_logs("smbd.service", result)
        self.assertTrue(self.page.log_hint)


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
