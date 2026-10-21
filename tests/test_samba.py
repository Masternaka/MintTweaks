"""Tests for the Samba backend."""

import tempfile
import unittest
from pathlib import Path

from minttweaks.core.smbconf import SmbConf
from minttweaks.modules.samba import backend
from tests.fakes import FakeRunner, pdbedit_listv, sample_smb_conf


def document(runner, text=None):
    text = sample_smb_conf() if text is None else text
    return backend.Document(Path("/etc/samba/smb.conf"), SmbConf.parse(text), text, existed=True)


class ShareTests(unittest.TestCase):
    def setUp(self):
        self.conf = SmbConf.parse(sample_smb_conf())
        self.share = backend.Share.from_conf(self.conf, "Documents")

    def test_read_existing_share(self):
        self.assertEqual(self.share.path, "/srv/documents")
        self.assertEqual(self.share.comment, "Mes documents")
        self.assertFalse(self.share.read_only)
        self.assertTrue(self.share.browseable)
        self.assertFalse(self.share.guest_ok)
        self.assertEqual(self.share.valid_users, "alice bob")

    def test_directives_skip_empty_values(self):
        keys = dict(self.share.directives())
        self.assertNotIn("force group", keys)
        self.assertEqual(keys["read only"], "no")
        self.assertEqual(keys["guest ok"], "no")

    def test_update_writes_changes(self):
        self.share.read_only = True
        self.share.comment = "Archive"
        backend.apply_share(self.conf, self.share, previous=backend.Share.from_conf(self.conf, "Documents"))
        self.assertEqual(self.conf.get("Documents", "read only"), "yes")
        self.assertEqual(self.conf.get("Documents", "comment"), "Archive")

    def test_cleared_optional_parameter_disappears(self):
        self.share.valid_users = ""
        backend.apply_share(self.conf, self.share, previous=backend.Share.from_conf(self.conf, "Documents"))
        self.assertIsNone(self.conf.get("Documents", "valid users"))

    def test_create_new_share(self):
        with tempfile.TemporaryDirectory() as tmp:
            new = backend.Share(name="Photos", path=tmp, read_only=True)
            self.assertEqual(backend.create_share(self.conf, new), [])
            self.assertTrue(self.conf.has_section("Photos"))
            self.assertIn("Photos", self.conf.shares())
            self.assertEqual(self.conf.get("Photos", "path"), tmp)

    def test_create_rejects_duplicate_and_bad_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(backend.create_share(self.conf, backend.Share(name="Documents", path=tmp)))
            self.assertTrue(backend.create_share(self.conf, backend.Share(name="Nope", path="relative")))
            self.assertTrue(backend.create_share(self.conf, backend.Share(name="global", path=tmp)))
            self.assertTrue(backend.create_share(self.conf, backend.Share(name="Ghost", path=tmp + "/absent")))

    def test_masks_must_be_octal(self):
        share = backend.Share(name="Bad", path="/srv", create_mask="0668")  # path is never checked here
        self.assertTrue(any("octal" in problem for problem in share.validate(self.conf)))

    def test_rename_share(self):
        previous = backend.Share.from_conf(self.conf, "Documents")
        renamed = backend.Share.from_conf(self.conf, "Documents")
        renamed.name = "Archives"
        with tempfile.TemporaryDirectory() as tmp:
            previous.path = tmp
            renamed.path = tmp
            self.assertEqual(backend.update_share(self.conf, renamed, previous), [])
        self.assertFalse(self.conf.has_section("Documents"))
        self.assertEqual(self.conf.get("Archives", "path"), previous.path)

    def test_delete_share(self):
        self.assertTrue(backend.delete_share(self.conf, "Documents"))
        self.assertFalse(backend.delete_share(self.conf, "Documents"))


class ValidationTests(unittest.TestCase):
    def test_testparm_errors_are_collected(self):
        runner = FakeRunner().add(
            ["testparm"],
            stdout="Loaded services file OK.\n",
            stderr='Unknown parameter encountered: "bogus"\n',
            returncode=1,
        )
        validation = backend.validate_text(runner, "[global]\n  bogus = 1\n")
        self.assertFalse(validation.ok)
        self.assertTrue(any("Unknown parameter" in error for error in validation.errors))

    def test_testparm_warnings_do_not_block(self):
        runner = FakeRunner().add(
            ["testparm"],
            stdout="WARNING: The option 'syslog' is deprecated.\n",
            returncode=0,
        )
        validation = backend.validate_text(runner, "[global]\n")
        self.assertTrue(validation.ok)
        self.assertEqual(len(validation.warnings), 1)

    def test_missing_testparm_is_an_error_not_a_pass(self):
        validation = backend.validate_text(FakeRunner(), "[global]\n")
        self.assertFalse(validation.ok)
        self.assertIn("testparm", validation.errors[0])

    def test_badly_formed_share_is_an_error(self):
        runner = FakeRunner().add(["testparm"], stdout="ERROR: Badly formed share name\n", returncode=1)
        self.assertFalse(backend.validate_text(runner, "[global]\n").ok)


class SaveTests(unittest.TestCase):
    def setUp(self):
        # Force the source-checkout fallback so the argv is predictable.
        self._original_helper = backend.helper_path
        backend.helper_path = lambda: None

    def tearDown(self):
        backend.helper_path = self._original_helper

    def test_invalid_config_is_never_written(self):
        runner = FakeRunner().add(["testparm"], stdout="ERROR: nope\n", returncode=1)
        with tempfile.TemporaryDirectory() as tmp:
            outcome = backend.save_document(runner, document(runner), backup_dir=Path(tmp))
            self.assertFalse(outcome.ok)
            self.assertFalse(runner.ran(["install"]))
            self.assertEqual(list(Path(tmp).glob("smb.conf.*")), [])

    def test_helper_is_preferred_when_installed(self):
        helper = Path("/usr/lib/minttweaks/mtk-root")
        backend.helper_path = lambda: helper
        runner = FakeRunner().add(["testparm"])
        runner.add([str(helper)], returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            outcome = backend.save_document(runner, document(runner), backup_dir=Path(tmp))
        self.assertTrue(outcome.ok, outcome.message)
        call = runner.commands()[-1]
        self.assertEqual(call[0], str(helper))
        self.assertEqual(call[1], "install-smbconf")
        self.assertIn("--reload", call)

    def test_successful_save_backs_up_then_installs(self):
        runner = FakeRunner().add(["testparm"], stdout="Loaded services file OK.\n")
        runner.add(["install"], returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            outcome = backend.save_document(runner, document(runner), backup_dir=Path(tmp))
            self.assertTrue(outcome.ok, outcome.message)
            self.assertTrue(outcome.backup_path and outcome.backup_path.exists())
            self.assertIn("workgroup = WORKGROUP", outcome.backup_path.read_text())
            install_call = [call for call in runner.commands() if call[0] == "install"][0]
            self.assertEqual(install_call[1:3], ("-o", "root"))
            self.assertEqual(install_call[-1], "/etc/samba/smb.conf")

    def test_failure_to_install_is_reported(self):
        runner = FakeRunner().add(["testparm"])
        runner.add(["install"], returncode=126, stderr="Not authorized")
        with tempfile.TemporaryDirectory() as tmp:
            outcome = backend.save_document(runner, document(runner), backup_dir=Path(tmp))
            self.assertFalse(outcome.ok)
            self.assertIn("Not authorized", outcome.message)

    def test_backups_are_unique_and_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = backend.backup_conf("[global]\n", Path(tmp))
            second = backend.backup_conf("[global]\n", Path(tmp))
            self.assertNotEqual(first, second)
            self.assertEqual(len(backend.list_backups(Path(tmp))), 2)
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)

    def test_restore_backup_validates_first(self):
        runner = FakeRunner().add(["testparm"], stdout="ERROR: broken\n", returncode=1)
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "smb.conf.20240101-000000"
            backup.write_text("[global]\n")
            outcome = backend.restore_backup(runner, backup)
            self.assertFalse(outcome.ok)
            self.assertFalse(runner.ran(["install"]))


class UserTests(unittest.TestCase):
    def test_list_users_parses_pdbedit_verbose(self):
        runner = FakeRunner().add(["pdbedit", "-L", "-v"], stdout=pdbedit_listv())
        users = backend.list_users(runner)
        self.assertEqual([user.name for user in users], ["alice", "bob"])
        self.assertTrue(users[0].enabled)
        self.assertFalse(users[1].enabled)
        self.assertEqual(users[0].full_name, "Alice Example")

    def test_add_user_rejects_unknown_unix_account(self):
        runner = FakeRunner()
        result = backend.add_user(runner, "definitely-not-a-user", "password123")
        self.assertFalse(result.ok)
        self.assertIn("No Unix account", result.stderr)
        self.assertFalse(runner.ran(["smbpasswd"]))

    def test_add_user_rejects_bad_name(self):
        runner = FakeRunner()
        result = backend.add_user(runner, "../../etc/passwd", "password123")
        self.assertFalse(result.ok)
        self.assertIn("lowercase Unix user", result.stderr)
        self.assertFalse(runner.ran(["smbpasswd"]))

    def test_password_checks(self):
        self.assertIsNotNone(backend.password_problem(""))
        self.assertIsNotNone(backend.password_problem("short"))
        self.assertIsNotNone(backend.password_problem(" leading-space"))
        self.assertIsNone(backend.password_problem("longenough"))

    def test_set_user_enabled_uses_the_right_flag(self):
        runner = FakeRunner().add(["smbpasswd"], returncode=0)
        # Works only for a real Unix account; skip when the sandbox has none.
        if not backend.unix_user_exists("root"):
            self.skipTest("no root account in this environment")
        backend.set_user_enabled(runner, "root", False)
        self.assertIn(("-d", "root"), [call[1:] for call in runner.commands()])


class ServiceTests(unittest.TestCase):
    def test_control_refuses_unknown_unit(self):
        runner = FakeRunner()
        result = backend.control_service(runner, "evil; rm -rf /", "stop")
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(runner.ran(["systemctl"]))

    def test_control_refuses_unknown_action(self):
        self.assertFalse(backend.control_service(FakeRunner(), "smbd", "disable-and-mask").ok)

    def test_control_marks_the_command_as_root(self):
        runner = FakeRunner().add(["systemctl"], returncode=0)
        backend.control_service(runner, "smbd", "restart")
        self.assertTrue(runner.calls[-1].needs_root)

    def test_service_state_reads_stdout_even_on_failure(self):
        runner = FakeRunner().add(["systemctl", "is-active"], stdout="inactive\n", returncode=3)
        runner.add(["systemctl", "is-enabled"], stdout="enabled\n")
        state = backend.service_state(runner, "smbd")
        self.assertEqual(state.active, "inactive")
        self.assertEqual(state.enabled, "enabled")
        self.assertFalse(state.running)

    def test_firewall_state_detection(self):
        runner = FakeRunner().add(["ufw", "status"], stdout="Status: active\n\nSamba    ALLOW    Anywhere\n")
        original = backend.shutil.which
        backend.shutil.which = lambda name: "/usr/sbin/ufw" if name == "ufw" else original(name)
        try:
            available, active, allows = backend.firewall_state(runner)
        finally:
            backend.shutil.which = original
        self.assertTrue(available)
        self.assertTrue(active)
        self.assertTrue(allows)

    def test_unit_exists_uses_the_listing(self):
        runner = FakeRunner().add(["systemctl", "list-unit-files"], stdout="smbd.service enabled enabled\n")
        self.assertTrue(backend.unit_exists(runner, "smbd"))
        runner2 = FakeRunner().add(["systemctl", "list-unit-files"], stdout="\n")
        self.assertFalse(backend.unit_exists(runner2, "nmbd"))


class PackageTests(unittest.TestCase):
    def test_package_installed(self):
        runner = FakeRunner().add(["dpkg-query"], stdout="install ok installed")
        self.assertTrue(backend.package_installed(runner, "samba"))
        runner2 = FakeRunner().add(["dpkg-query"], stdout="deinstall ok config-files")
        self.assertFalse(backend.package_installed(runner2, "samba"))

    def test_missing_packages(self):
        runner = FakeRunner().add(["dpkg-query"], stdout="install ok installed")
        self.assertEqual(backend.missing_packages(runner), [])


class LoadDocumentTests(unittest.TestCase):
    def test_missing_file_falls_back_to_the_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = backend.load_document(FakeRunner(), Path(tmp) / "absent.conf")
            self.assertFalse(doc.existed)
            self.assertEqual(doc.conf.global_get("workgroup"), "WORKGROUP")

    def test_existing_file_is_loaded_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "smb.conf"
            target.write_text(sample_smb_conf())
            doc = backend.load_document(FakeRunner(), target)
            self.assertTrue(doc.existed)
            self.assertEqual(backend.render(doc), sample_smb_conf())


if __name__ == "__main__":
    unittest.main()
