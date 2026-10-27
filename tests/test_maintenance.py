"""Tests for the maintenance backend."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.core.runner import SubprocessRunner
from minttweaks.modules.maintenance import backend
from tests.fakes import FakeRunner

AUTOREMOVE = """\
NOTE: This is only a simulation!
Reading package lists...
The following packages will be REMOVED:
  libgdal30* libproj22* linux-image-6.8.0-40-generic*
0 upgraded, 0 newly installed, 3 to remove and 0 not upgraded.
Remv libgdal30 [3.4.1]
Remv libproj22 [8.2.1]
Remv linux-image-6.8.0-40-generic [6.8.0-40.40]
"""

DPKG = (
    "linux-image-6.8.0-40-generic\t6.8.0-40.40\tinstall ok installed\n"
    "linux-headers-6.8.0-40-generic\t6.8.0-40.40\tinstall ok installed\n"
    "linux-headers-6.8.0-40\t6.8.0-40.40\tinstall ok installed\n"
    "linux-image-6.8.0-45-generic\t6.8.0-45.45\tinstall ok installed\n"
    "linux-modules-6.8.0-45-generic\t6.8.0-45.45\tinstall ok installed\n"
    "linux-image-6.8.0-47-generic\t6.8.0-47.47\tinstall ok installed\n"
    "linux-image-6.8.0-30-generic\t6.8.0-30.30\tdeinstall ok config-files\n"
)


class AutoremovePreviewTests(unittest.TestCase):
    def test_failed_preview_with_partial_output_is_rejected(self):
        runner = FakeRunner().add(["apt-get", "-s"], stdout=AUTOREMOVE, returncode=100, stderr="APT locked")
        with self.assertRaises(backend.PreviewError):
            backend.autoremove_preview(runner)

    def test_autoremove_requires_an_approved_plan(self):
        runner = FakeRunner()
        outcome = backend.run_task(runner, backend.TASK_BY_ID["apt_autoremove"])
        self.assertFalse(outcome.ok)
        self.assertEqual(runner.commands(), [])

    def test_changed_plan_does_not_remove_any_package(self):
        runner = FakeRunner().add(["apt-get", "-s"], stdout="Remv unexpected [1]\n")
        outcome = backend.run_task(runner, backend.TASK_BY_ID["apt_autoremove"], approved_packages=["approved"])
        self.assertFalse(outcome.ok)
        self.assertFalse(runner.ran(["apt-get", "autoremove"]))

    def test_failed_recheck_does_not_remove_any_package(self):
        runner = FakeRunner().add(["apt-get", "-s"], stdout="Remv approved [1]\n", returncode=100)
        outcome = backend.run_task(runner, backend.TASK_BY_ID["apt_autoremove"], approved_packages=["approved"])
        self.assertFalse(outcome.ok)
        self.assertFalse(runner.ran(["apt-get", "autoremove"]))

    def test_matching_plan_is_checked_before_removal(self):
        runner = FakeRunner().add(["apt-get", "-s"], stdout="Remv approved [1]\n")
        runner.add(["apt-get", "autoremove"], stdout="Removed")
        outcome = backend.run_task(runner, backend.TASK_BY_ID["apt_autoremove"], approved_packages=["approved"])
        self.assertTrue(outcome.ok)
        self.assertEqual(runner.commands(), [
            ("apt-get", "-s", "autoremove", "--purge"),
            ("apt-get", "autoremove", "--purge", "-y"),
        ])

    def test_reads_both_the_summary_and_the_remv_lines(self):
        self.assertEqual(
            backend.parse_autoremove_preview(AUTOREMOVE),
            ["libgdal30", "libproj22", "linux-image-6.8.0-40-generic"],
        )

    def test_nothing_to_remove(self):
        text = "0 upgraded, 0 newly installed, 0 to remove and 5 not upgraded.\n"
        self.assertEqual(backend.parse_autoremove_preview(text), [])

    def test_only_remv_lines(self):
        self.assertEqual(backend.parse_autoremove_preview("Remv foo [1.0]\n"), ["foo"])

    def test_wrapped_package_list(self):
        text = (
            "The following packages will be REMOVED:\n"
            "  aaa bbb ccc\n"
            "  ddd\n"
            "0 upgraded, 0 newly installed, 4 to remove and 0 not upgraded.\n"
        )
        self.assertEqual(backend.parse_autoremove_preview(text), ["aaa", "bbb", "ccc", "ddd"])

    def test_preview_runs_a_simulation_not_a_removal(self):
        runner = FakeRunner().add(["apt-get", "-s", "autoremove"], stdout=AUTOREMOVE)
        backend.autoremove_preview(runner)
        self.assertFalse(any(call[:1] == ("apt-get",) and "-y" in call for call in runner.commands()))


class KernelTests(unittest.TestCase):
    def runner(self, uname="6.8.0-45-generic"):
        runner = FakeRunner()
        runner.add(["dpkg-query"], stdout=DPKG)
        runner.add(["uname", "-r"], stdout=uname + "\n")
        return runner

    def test_installed_kernels_groups_companions(self):
        kernels = {kernel.version: kernel for kernel in backend.installed_kernels(self.runner())}
        self.assertEqual(sorted(kernels), ["6.8.0-40-generic", "6.8.0-45-generic", "6.8.0-47-generic"])
        entry = kernels["6.8.0-45-generic"]
        self.assertIn("linux-image-6.8.0-45-generic", entry.packages)
        self.assertIn("linux-modules-6.8.0-45-generic", entry.packages)
        self.assertTrue(entry.running)

    def test_running_and_newest_are_never_removable(self):
        kernels = backend.installed_kernels(self.runner())
        removable = [kernel.version for kernel in backend.removable_kernels(kernels, keep=1)]
        self.assertEqual(removable, ["6.8.0-40-generic"])

    def test_keep_zero_still_protects_the_running_kernel(self):
        kernels = backend.installed_kernels(self.runner())
        removable = [kernel.version for kernel in backend.removable_kernels(kernels, keep=0)]
        self.assertNotIn("6.8.0-45-generic", removable)
        self.assertEqual(removable, ["6.8.0-40-generic", "6.8.0-47-generic"])

    def test_purge_refuses_the_running_kernel(self):
        kernels = backend.installed_kernels(self.runner())
        running = [kernel for kernel in kernels if kernel.running]
        result = backend.purge_kernels(FakeRunner(), running)
        self.assertFalse(result.ok)
        self.assertIn("running kernel", result.stderr)

    def test_purge_passes_every_companion(self):
        kernels = backend.installed_kernels(self.runner())
        target = [k for k in kernels if k.version == "6.8.0-40-generic"]
        runner = FakeRunner().add(["apt-get", "purge"], returncode=0)
        backend.purge_kernels(runner, target)
        argv = runner.commands()[-1]
        self.assertIn("linux-image-6.8.0-40-generic", argv)
        self.assertIn("linux-headers-6.8.0-40-generic", argv)

    def test_version_sort_is_numeric(self):
        kernels = [
            backend.Kernel("6.8.0-9-generic", ()),
            backend.Kernel("6.8.0-45-generic", ()),
            backend.Kernel("6.8.0-10-generic", ()),
        ]
        self.assertEqual(
            [kernel.version for kernel in backend._sort_kernels(kernels)],
            ["6.8.0-9-generic", "6.8.0-10-generic", "6.8.0-45-generic"],
        )

    def test_parse_dpkg_listing_skips_removed_packages(self):
        self.assertEqual(
            backend.parse_dpkg_listing(DPKG),
            [
                "linux-image-6.8.0-40-generic",
                "linux-headers-6.8.0-40-generic",
                "linux-headers-6.8.0-40",
                "linux-image-6.8.0-45-generic",
                "linux-modules-6.8.0-45-generic",
                "linux-image-6.8.0-47-generic",
            ],
        )


class UserCleanupTests(unittest.TestCase):
    def test_dry_run_preserves_trash_and_thumbnails(self):
        for environment in (False, True):
            with self.subTest(environment=environment), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                thumbnail = home / ".cache/thumbnails/normal/a.png"
                trash = home / ".local/share/Trash/files/precious.txt"
                for path in (thumbnail, trash):
                    path.parent.mkdir(parents=True)
                    path.write_text("preserve me")
                with patch.dict("os.environ", {"MTK_DRY_RUN": "1" if environment else "0"}):
                    runner = SubprocessRunner(dry_run=not environment)
                    with patch.object(backend.Path, "home", return_value=home):
                        for task_id in ("thumbnails", "trash"):
                            lines = []
                            outcome = backend.run_task(runner, backend.TASK_BY_ID[task_id], on_line=lines.append)
                            self.assertTrue(outcome.ok)
                            self.assertIn("[dry-run]", lines[0])
                for path in (thumbnail, trash):
                    self.assertEqual(path.read_text(), "preserve me")

    def test_clear_thumbnails_and_keep_neighbours(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cache = home / ".cache/thumbnails/normal"
            cache.mkdir(parents=True)
            (cache / "a.png").write_bytes(b"x" * 512)
            (home / "keep.txt").write_text("keep me")

            self.assertGreater(backend.directory_size(home / ".cache/thumbnails"), 0)
            result = backend.clear_thumbnails(home)
            self.assertTrue(result.ok)
            self.assertIn("1 thumbnail", result.stdout)
            self.assertTrue((home / ".keep.txt").exists() or True)
            self.assertTrue((home / "keep.txt").exists())
            self.assertFalse((cache / "a.png").exists())

    def test_symlink_inside_the_cache_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cache = home / ".cache/thumbnails"
            cache.mkdir(parents=True)
            (home / "precious").mkdir()
            (home / "precious/data.txt").write_text("important")
            (cache / "trap").symlink_to(home / "precious")

            backend.clear_thumbnails(home)

            self.assertTrue((home / "precious/data.txt").exists(), "followed a symlink out of the cache")
            self.assertFalse((cache / "trap").exists())

    def test_empty_trash(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            files = home / ".local/share/Trash/files"
            info = home / ".local/share/Trash/info"
            files.mkdir(parents=True)
            info.mkdir(parents=True)
            (files / "junk.txt").write_text("junk")
            (info / "junk.txt.trashinfo").write_text("[Trash Info]")
            result = backend.empty_trash(home)
            self.assertTrue(result.ok)
            self.assertIn("2 item", result.stdout)
            self.assertFalse((files / "junk.txt").exists())

    def test_missing_trash_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(backend.empty_trash(Path(tmp)).ok)


class RegistryTests(unittest.TestCase):
    def test_task_ids_are_unique(self):
        ids = [task.id for task in backend.TASKS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_task_has_steps_and_a_title(self):
        for task in backend.TASKS:
            self.assertTrue(task.steps, task.id)
            self.assertTrue(task.title.strip(), task.id)
            self.assertTrue(task.detail.strip(), task.id)
            for step in task.steps:
                self.assertTrue(step.description.strip(), task.id)
                self.assertTrue(step.command is not None or step.action is not None, task.id)

    def test_root_tasks_are_marked_root(self):
        for task in backend.TASKS:
            if task.id.startswith(("apt_", "journal_")):
                self.assertTrue(task.needs_root, task.id)
            if task.id in ("thumbnails", "trash"):
                self.assertFalse(task.needs_root, task.id)

    def test_run_task_stops_after_a_required_failure(self):
        task = backend.Task(
            id="demo",
            title_msgid="Demo",
            detail_msgid="two mandatory steps",
            steps=(
                backend.Step("first", command=backend.cmd("false")),
                backend.Step("second", command=backend.cmd("true")),
            ),
        )
        runner = FakeRunner().add(["false"], returncode=1, stderr="boom")
        outcome = backend.run_task(runner, task)
        self.assertFalse(outcome.ok)
        self.assertEqual([step.description for step in outcome.steps], ["first"])
        self.assertIn("failed", outcome.summary())

    def test_run_task_continues_after_an_optional_failure(self):
        task = backend.Task(
            id="demo",
            title_msgid="Demo",
            detail_msgid="one optional step",
            steps=(
                backend.Step("optional", command=backend.cmd("false"), required=False),
                backend.Step("required", command=backend.cmd("true")),
            ),
        )
        runner = FakeRunner().add(["false"], returncode=1)
        outcome = backend.run_task(runner, task)
        self.assertEqual(len(outcome.steps), 2)
        self.assertFalse(outcome.ok)

    def test_human_bytes(self):
        self.assertEqual(backend.human_bytes(None), "unknown")
        self.assertEqual(backend.human_bytes(512), "512 B")
        self.assertEqual(backend.human_bytes(2048), "2.0 KB")
        self.assertEqual(backend.human_bytes(5 * 1024**3), "5.0 GB")


class ProbeTests(unittest.TestCase):
    def test_unreadable_cache_size_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(backend.os, "walk", side_effect=PermissionError("denied")):
                self.assertIsNone(backend.directory_size(Path(tmp)))
        self.assertEqual(backend.human_bytes(None), "unknown")

    def test_failed_kernel_query_does_not_hide_the_space_and_apt_probe(self):
        runner = FakeRunner().add(["apt-get", "-s"], stdout=AUTOREMOVE)
        runner.add(["du"], stdout="2048\t/cache\n")
        runner.add(["dpkg-query"], returncode=124, stderr="kernel query timeout")
        with tempfile.TemporaryDirectory() as tmp, patch.object(backend.Path, "home", return_value=Path(tmp)):
            probe, kernels = backend.collect_maintenance(runner)
        self.assertEqual(probe.apt_archives_bytes, 2048)
        self.assertEqual(probe.autoremove_count, 3)
        self.assertEqual(kernels, [])
        self.assertIn("kernel query timeout", probe.kernel_error)

    def test_failed_preview_is_distinct_from_no_orphans(self):
        runner = FakeRunner().add(["apt-get", "-s"], returncode=100, stderr="APT locked")
        with tempfile.TemporaryDirectory() as tmp:
            probe = backend.collect_probe(runner, Path(tmp))
        self.assertEqual(probe.autoremove_packages, [])
        self.assertIn("APT locked", probe.autoremove_error)

    def test_probe_collects_sizes(self):
        runner = FakeRunner()
        runner.add(["du", "-sb", "/var/cache/apt/archives"], stdout="2048\t/var/cache/apt/archives\n")
        runner.add(["du", "-sb", "/var/log/journal"], stdout="1024\t/var/log/journal\n")
        runner.add(["apt-get", "-s", "autoremove"], stdout=AUTOREMOVE)
        with tempfile.TemporaryDirectory() as tmp:
            probe = backend.collect_probe(runner, Path(tmp))
        self.assertEqual(probe.apt_archives_bytes, 2048)
        self.assertEqual(probe.journal_bytes, 1024)
        self.assertEqual(probe.autoremove_count, 3)

    def test_du_failure_is_reported_as_unknown(self):
        self.assertIsNone(backend._du_bytes(FakeRunner().add(["du"], returncode=1), Path("/var")))


if __name__ == "__main__":
    unittest.main()
