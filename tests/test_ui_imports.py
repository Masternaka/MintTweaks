"""Import-level smoke tests for the GTK layer.

These run on any machine: :mod:`tests.fakegi` supplies a stub ``gi`` so the real
widget code can be imported and inspected without a display.
"""

import contextlib
import io
import threading
import unittest
from unittest import mock

from tests import fakegi

HAS_REAL_GI = not fakegi.install()

from minttweaks.modules.maintenance import page as maintenance_page  # noqa: E402
from minttweaks.modules.samba import page as samba_page  # noqa: E402
from minttweaks.modules.services import page as services_page  # noqa: E402
from minttweaks.ui import widgets, window  # noqa: E402

from tests.fakes import FakeRunner  # noqa: E402


class PageContractTests(unittest.TestCase):
    def test_every_page_declares_metadata(self):
        for page_class in (maintenance_page.MaintenancePage, services_page.ServicesPage, samba_page.SambaPage):
            self.assertTrue(page_class.page_name, page_class)
            self.assertTrue(page_class.page_title, page_class)
            self.assertTrue(page_class.page_icon, page_class)
            self.assertTrue(issubclass(page_class, widgets.Page), page_class)

    def test_page_names_are_unique(self):
        names = [page_class.page_name for page_class in window.PAGE_CLASSES]
        self.assertEqual(len(names), len(set(names)))

    def test_every_page_class_is_registered_in_the_window(self):
        self.assertEqual(
            set(window.PAGE_CLASSES),
            {maintenance_page.MaintenancePage, services_page.ServicesPage, samba_page.SambaPage},
        )

    def test_pages_use_known_context(self):
        for page_class in window.PAGE_CLASSES:
            self.assertTrue(callable(page_class.refresh), page_class)


class ContextTests(unittest.TestCase):
    def test_log_reaches_every_sink(self):
        ctx = widgets.AppContext(FakeRunner())
        seen = []
        ctx.add_sink(lambda message, level: seen.append((message, level)))
        ctx.log("hello", "warn")
        self.assertEqual(seen, [("hello", "warn")])

    def test_unknown_level_falls_back_to_info(self):
        ctx = widgets.AppContext(FakeRunner())
        seen = []
        ctx.add_sink(lambda message, level: seen.append(level))
        ctx.log("hello", "nonsense")
        self.assertEqual(seen, ["info"])

    def test_log_from_a_worker_thread_is_deferred_to_the_main_loop(self):
        ctx = widgets.AppContext(FakeRunner())
        seen = []
        ctx.add_sink(lambda message, level: seen.append(message))

        thread = threading.Thread(target=lambda: ctx.log("from thread"))
        thread.start()
        thread.join()

        # Touching GTK off the main thread would be a crash in real GTK; the
        # context must therefore *not* have called the sink directly.
        self.assertEqual(seen, [])

    def test_broken_sink_does_not_propagate(self):
        ctx = widgets.AppContext(FakeRunner())
        calls = []

        def broken(_message, _level):
            raise RuntimeError("boom")

        ctx.add_sink(broken)
        ctx.add_sink(lambda message, level: calls.append(message))
        with mock.patch("traceback.print_exc"):
            ctx.log("still delivered")
        self.assertEqual(calls, ["still delivered"])

    def test_once_helper_never_repeats(self):
        calls = []
        self.assertFalse(widgets._once(lambda: calls.append(1)))
        self.assertEqual(calls, [1])

    def test_escalation_available_with_a_plain_runner(self):
        self.assertTrue(widgets.escalation_available(FakeRunner()))


class WidgetHelperTests(unittest.TestCase):
    def test_level_tags_cover_every_level_used(self):
        for level in ("info", "ok", "warn", "error", "command"):
            self.assertIn(level, widgets.LEVEL_TAGS)

    def test_dialog_helpers_are_exported(self):
        self.assertTrue(callable(widgets.confirm))
        self.assertTrue(callable(widgets.show_error))
        self.assertTrue(callable(widgets.show_info))


class AppModuleTests(unittest.TestCase):
    def test_help_and_version_do_not_start_gtk(self):
        from minttweaks import app

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(["minttweaks", "--version"]), 0)
            self.assertEqual(app.main(["minttweaks", "--help"]), 0)

    def test_own_flags_are_stripped_before_gtk_sees_them(self):
        from minttweaks import app

        self.assertEqual(app._strip_own_flags(["minttweaks", "--dry-run"]), ["minttweaks"])

    def test_language_flag_is_extracted_before_gtk_sees_it(self):
        from minttweaks import app

        self.assertEqual(app._split_language(["minttweaks", "--lang", "fr"]), ("fr", ["minttweaks"]))
        self.assertEqual(app._split_language(["minttweaks", "--lang=de"]), ("de", ["minttweaks"]))
        self.assertEqual(app._split_language(["minttweaks"]), (None, ["minttweaks"]))


if __name__ == "__main__":
    unittest.main()
