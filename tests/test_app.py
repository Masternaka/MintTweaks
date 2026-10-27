"""Application options must configure the runner before GTK starts."""

import unittest
from unittest.mock import patch

from tests import fakegi

fakegi.install()

from minttweaks import app  # noqa: E402


class SimulationOptionTests(unittest.TestCase):
    def test_cli_flag_reaches_the_application_and_is_removed_from_gtk_arguments(self):
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), \
                    patch.object(app, "is_root", return_value=False), \
                    patch.object(app.logs, "setup"), \
                    patch.object(app.i18n, "install", return_value="en"), \
                    patch.dict("os.environ", {"DISPLAY": ":audit"}), \
                    patch.object(app, "MintTweaksApp") as factory:
                factory.return_value.run.return_value = 0
                argv = ["minttweaks"] + (["--dry-run"] if dry_run else [])
                self.assertEqual(app.main(argv), 0)
                factory.assert_called_once_with(dry_run=dry_run)
                factory.return_value.run.assert_called_once_with(["minttweaks"])

    def test_application_configures_its_runner(self):
        with patch.object(app, "SubprocessRunner") as runner:
            app.MintTweaksApp(dry_run=True)
        self.assertTrue(runner.call_args.kwargs["dry_run"])

    def test_simulation_cannot_activate_an_existing_live_instance(self):
        for cli, environment in ((False, "0"), (True, "0"), (False, "1")):
            with self.subTest(cli=cli, environment=environment), \
                    patch.dict("os.environ", {"MTK_DRY_RUN": environment}), \
                    patch.object(app.Gtk.Application, "__init__", return_value=None) as initialize:
                application = app.MintTweaksApp(dry_run=cli)
                simulated = cli or environment == "1"
                expected = app.APP_ID + ".Simulation" if simulated else app.APP_ID
                self.assertEqual(initialize.call_args.kwargs["application_id"], expected)
                self.assertEqual(application.ctx.runner.dry_run, simulated)
