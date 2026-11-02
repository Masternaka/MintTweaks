"""Repository setup never touches real system files or APT in this suite."""

import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from minttweaks.modules.software import repository
from tests.fakes import FakeRunner

ROOT = Path(__file__).resolve().parent.parent
loader = importlib.machinery.SourceFileLoader("repository_helper", str(ROOT / "data/mtk-repository"))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class RepositoryHelperTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.key = self.base / "keyrings/masternaka.asc"
        self.source = self.base / "sources/masternaka.list"
        self.source.parent.mkdir()
        for name, value in (("KEY_PATH", self.key), ("SOURCE_PATH", self.source)):
            patcher = patch.object(helper, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # The test directory is deliberately user-owned, not a root-owned /etc.
        for name, value in (("secure_directory", Mock()),
                            ("existing_content", Mock(side_effect=lambda p: p.read_bytes() if p.exists() else None))):
            patcher = patch.object(helper, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(helper.os, "fchown")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(helper.subprocess, "run", return_value=Mock(returncode=0))
        self.run = patcher.start()
        self.addCleanup(patcher.stop)

    def test_bundled_key_and_ui_fingerprint_match_pins(self):
        self.assertEqual(hashlib.sha256(helper.BUNDLED_KEY.read_bytes()).hexdigest(), helper.KEY_SHA256)
        self.assertEqual(helper.FINGERPRINT, repository.FINGERPRINT)
        self.assertEqual(helper.URL, repository.URL)
        self.assertIn("signed-by=/etc/apt/keyrings/masternaka.asc", helper.SOURCE)

    def test_setup_only_refreshes_this_signed_source_and_is_repeatable(self):
        helper.install_repository()
        self.assertEqual(self.key.read_bytes(), helper.BUNDLED_KEY.read_bytes())
        self.assertEqual(self.source.read_text(), helper.SOURCE)
        self.assertEqual(stat.S_IMODE(self.key.stat().st_mode), 0o644)
        args = self.run.call_args.args[0]
        self.assertEqual(args[-1], "update")
        self.assertIn("Dir::Etc::sourceparts=-", args)
        self.assertIn("APT::Update::Error-Mode=any", args)
        self.assertIn("APT::Get::AllowUnauthenticated=false", args)
        self.assertNotIn("install", args)
        inode = self.key.stat().st_ino
        helper.install_repository()
        self.assertEqual(self.key.stat().st_ino, inode)

    def test_conflicting_source_prevents_even_key_installation(self):
        self.source.write_text("deb https://example.invalid stable main\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            helper.install_repository()
        self.assertFalse(self.key.exists())
        self.assertIn("example.invalid", self.source.read_text())
        self.run.assert_not_called()

    def test_wrong_bundled_key_does_not_write_or_run_apt(self):
        with patch.object(helper, "KEY_SHA256", "0" * 64), self.assertRaisesRegex(ValueError, "pinned"):
            helper.install_repository()
        self.assertFalse(self.key.exists())
        self.assertFalse(self.source.exists())
        self.run.assert_not_called()

    def test_failed_refresh_rolls_back_new_files(self):
        self.run.return_value.returncode = 100
        with self.assertRaisesRegex(ValueError, "refresh failed"):
            helper.install_repository()
        self.assertFalse(self.key.exists())
        self.assertFalse(self.source.exists())

    def test_failed_refresh_preserves_preexisting_matching_key(self):
        self.key.parent.mkdir()
        self.key.write_bytes(helper.BUNDLED_KEY.read_bytes())
        self.run.side_effect = subprocess.TimeoutExpired("apt-get", 300)
        with self.assertRaises(subprocess.TimeoutExpired):
            helper.install_repository()
        self.assertTrue(self.key.exists())
        self.assertFalse(self.source.exists())

    def test_create_file_will_not_overwrite_a_racing_destination(self):
        self.source.write_text("concurrent configuration")
        with self.assertRaises(FileExistsError):
            helper.create_file(self.source, b"replacement")
        self.assertEqual(self.source.read_text(), "concurrent configuration")
        self.assertEqual(list(self.source.parent.glob(".minttweaks-*")), [])

    def test_cli_refuses_extra_paths_urls_and_non_root_callers(self):
        for args in (["install", "/tmp/key"], ["https://example.invalid"], []):
            self.assertEqual(helper.main(["mtk-repository"] + args), 1)
        with patch.object(helper.os, "geteuid", return_value=1000):
            self.assertEqual(helper.main(["mtk-repository", "install"]), 3)
        self.run.assert_not_called()


class PathSafetyTests(unittest.TestCase):
    def test_existing_content_refuses_symlinks_writable_and_non_root_files(self):
        for mode, uid in ((stat.S_IFLNK | 0o777, 0), (stat.S_IFREG | 0o666, 0),
                          (stat.S_IFREG | 0o644, 1000), (stat.S_IFIFO | 0o600, 0)):
            path = Mock()
            path.lstat.return_value = Mock(st_mode=mode, st_uid=uid, st_size=10)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                helper.existing_content(path)
            path.read_bytes.assert_not_called()

    def test_secure_directory_rejects_symlinked_or_writable_parents(self):
        for mode in (stat.S_IFLNK | 0o755, stat.S_IFDIR | 0o777):
            with patch.object(Path, "lstat", return_value=Mock(st_mode=mode, st_uid=0)):
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    helper.secure_directory(Path("/etc/apt/keyrings"))


class RepositoryBackendTests(unittest.TestCase):
    def test_simulation_never_requests_privilege_or_finds_a_helper(self):
        runner = FakeRunner()
        runner.dry_run = True
        with patch.object(repository, "find_helper", side_effect=AssertionError("must not be called")):
            self.assertIsNone(repository.install(runner))
        self.assertFalse(runner.calls)

    def test_only_fixed_install_action_reaches_privileged_runner(self):
        runner = FakeRunner().add(["/helper", "install"])
        with patch.object(repository, "find_helper", return_value=Path("/helper")):
            self.assertTrue(repository.install(runner).ok)
        self.assertEqual(runner.calls[0].argv, ("/helper", "install"))
        self.assertTrue(runner.calls[0].needs_root)
