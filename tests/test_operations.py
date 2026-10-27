"""Application-wide reservations survive worker and GTK callback failures."""

import queue
import threading
import unittest
from unittest.mock import Mock, patch

from tests import fakegi

fakegi.install()

from minttweaks import app  # noqa: E402
from minttweaks.ui import widgets  # noqa: E402
from minttweaks.ui.window import MainWindow  # noqa: E402
from minttweaks.modules.firefox.page import FirefoxPage  # noqa: E402
from minttweaks.modules.maintenance.page import MaintenancePage  # noqa: E402
from minttweaks.modules.samba.page import SambaPage  # noqa: E402
from minttweaks.modules.services.page import ServicesPage  # noqa: E402
from minttweaks.modules.services.backend import Unit  # noqa: E402
from tests.fakes import FakeRunner  # noqa: E402


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = widgets.AppContext(FakeRunner())
        self.callbacks = queue.Queue()
        self.patcher = patch.object(widgets.GLib, "idle_add", side_effect=lambda *args: self.callbacks.put(args))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def drain(self):
        while not self.callbacks.empty():
            callback, *args = self.callbacks.get_nowait()
            callback(*args)

    def test_reservation_blocks_other_pages_until_the_completion_callback(self):
        entered, release = threading.Event(), threading.Event()
        done = []

        def work():
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test worker was not released")
            return 42

        worker = self.ctx.run_operation("Samba", work, on_done=done.append)
        try:
            self.assertTrue(entered.wait(1))
            for name in ("Maintenance", "Services", "Firefox"):
                with self.assertRaises(widgets.OperationBusy):
                    self.ctx.run_operation(name, Mock())
        finally:
            release.set()
            worker.join(2)
        self.assertEqual(self.ctx.operation_name, "Samba")
        self.drain()
        self.assertEqual(done, [42])
        self.assertIsNone(self.ctx.operation_name)

    def test_read_only_work_can_run_during_a_modification(self):
        with patch.object(self.ctx, "run_async"):
            self.ctx.run_operation("Samba", lambda: None)
        seen = []
        worker = self.ctx.run_async(lambda: "diagnostic", on_done=seen.append)
        worker.join(1)
        self.drain()
        self.assertEqual(seen, ["diagnostic"])
        self.assertEqual(self.ctx.operation_name, "Samba")

    def test_worker_error_releases_reservation_and_reaches_error_handler(self):
        errors = []

        def fail():
            raise ValueError("failed")

        with patch("traceback.print_exc"):
            worker = self.ctx.run_operation("Samba", fail, on_error=errors.append)
            worker.join(1)
        self.drain()
        self.assertIsInstance(errors[0], ValueError)
        self.assertIsNone(self.ctx.operation_name)

    def test_callback_error_also_releases_reservation(self):
        callback = Mock(side_effect=ValueError("callback failed"))
        worker = self.ctx.run_operation("Samba", lambda: 1, on_done=callback)
        worker.join(1)
        with self.assertRaises(ValueError):
            self.drain()
        self.assertIsNone(self.ctx.operation_name)

    def test_error_callback_failure_also_releases_reservation(self):
        def fail():
            raise ValueError("worker failed")

        with patch("traceback.print_exc"):
            worker = self.ctx.run_operation("Samba", fail, on_error=Mock(side_effect=RuntimeError("dialog failed")))
            worker.join(1)
        with self.assertRaisesRegex(RuntimeError, "dialog failed"):
            self.drain()
        self.assertIsNone(self.ctx.operation_name)

    def test_thread_start_failure_does_not_leave_a_reservation(self):
        with patch.object(self.ctx, "run_async", side_effect=RuntimeError("no thread")):
            with self.assertRaises(RuntimeError):
                self.ctx.run_operation("Samba", lambda: None)
        self.assertIsNone(self.ctx.operation_name)

    def test_every_module_refuses_mutations_while_another_module_is_busy(self):
        with patch.object(self.ctx, "run_async"):
            self.ctx.run_operation("Existing operation", lambda: None)
        pages = [MaintenancePage(self.ctx), ServicesPage(self.ctx), SambaPage(self.ctx), FirefoxPage(self.ctx)]
        for page in pages:
            page.error = Mock()
            page.confirm = Mock(return_value=True)
        maintenance, services, samba, firefox = pages
        services.selected = Unit("example.service")
        firefox._selected_ids = lambda: ["uBlock0@raymondhill.net"]
        with patch("minttweaks.modules.maintenance.backend.run_task") as clean, \
                patch("minttweaks.modules.services.backend.control") as control, \
                patch("minttweaks.modules.samba.backend.install_packages") as install, \
                patch("minttweaks.modules.firefox.backend.apply_policy") as policy:
            from minttweaks.modules.maintenance.backend import TASK_BY_ID
            maintenance._execute(TASK_BY_ID["apt_clean"])
            services._control("restart")
            samba._on_install()
            firefox._on_apply()
        for action in (clean, control, install, policy):
            action.assert_not_called()
        for page in pages:
            page.error.assert_called_once()
        self.assertFalse(maintenance._busy)
        self.assertFalse(firefox._busy)

    def test_close_button_and_keyboard_quit_preserve_an_active_operation(self):
        window = MainWindow(None, self.ctx)
        with patch.object(self.ctx, "run_async"):
            self.ctx.run_operation("Package installation", lambda: None)
        with patch.object(window, "show_operation_in_progress") as message:
            self.assertTrue(window._on_delete_event(None, None))
        message.assert_called_once()
        application = app.MintTweaksApp()
        application.ctx = self.ctx
        with patch.object(application, "quit") as quit_app, patch.object(application, "_call_window") as message:
            application._request_quit()
        quit_app.assert_not_called()
        message.assert_called_once_with("show_operation_in_progress")

    def test_status_notification_is_cleared_after_completion(self):
        seen = []
        self.ctx.add_operation_sink(seen.append)
        worker = self.ctx.run_operation("Samba", lambda: None)
        worker.join(1)
        self.drain()
        self.assertEqual(seen, ["Samba", None])
