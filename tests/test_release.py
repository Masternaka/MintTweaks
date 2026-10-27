"""Exercise release decisions and the publisher with an offline GitHub double."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.release_plan import main, plan_release, source_version, stamp_version

ROOT = Path(__file__).resolve().parent.parent
SHA = "a" * 40


class ReleasePlanTests(unittest.TestCase):
    def plan(self, event="push", ref="refs/heads/main", base="1.2.3", run="12", attempt="1"):
        return plan_release(base, event, ref, SHA, run, attempt)

    def test_main_produces_a_development_version_and_tag(self):
        plan = self.plan()
        self.assertEqual(plan.channel, "development")
        self.assertEqual(plan.version, "1.2.3~dev.12.1.aaaaaaaaaaaa")
        self.assertEqual(plan.tag, "v1.2.3-dev.12.1")
        self.assertNotEqual(plan.tag, self.plan(attempt="2").tag)

    def test_manual_runs_on_main_stay_in_development(self):
        self.assertEqual(self.plan(event="workflow_dispatch").channel, "development")

    def test_pull_requests_cannot_publish(self):
        plan = self.plan(event="pull_request", ref="refs/pull/12/merge")
        self.assertEqual(plan.channel, "none")
        self.assertIn("publish=false", plan.outputs())

    def test_only_a_matching_pushed_tag_produces_a_stable_release(self):
        plan = self.plan(ref="refs/tags/v1.2.3")
        self.assertEqual((plan.channel, plan.version, plan.tag), ("stable", "1.2.3", "v1.2.3"))
        for event, ref in (
            ("push", "refs/tags/v1.2.4"),
            ("push", "refs/tags/v1.2.3-rc1"),
            ("push", "refs/tags/v1.2.3-dev.12.1"),
            ("workflow_dispatch", "refs/tags/v1.2.3"),
            ("push", "refs/heads/feature"),
            ("workflow_dispatch", "refs/heads/feature"),
        ):
            with self.subTest(event=event, ref=ref), self.assertRaises(ValueError):
                self.plan(event=event, ref=ref)

    def test_invalid_metadata_cannot_inject_github_outputs(self):
        for kwargs in ({"base": "1.2.3\nchannel=stable"}, {"run": "12\npublish=true"}, {"attempt": "0"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.plan(**kwargs)

    @unittest.skipUnless(shutil.which("dpkg"), "Debian version comparison requires dpkg")
    def test_development_versions_sort_before_the_corresponding_stable(self):
        for left, right in ((self.plan().version, "1.2.3"), ("1.2.3", self.plan(base="1.2.4").version)):
            result = subprocess.run(["dpkg", "--compare-versions", left, "lt", right])
            self.assertEqual(result.returncode, 0)


class VersionStampTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.contents = {
            "minttweaks/__init__.py": '__version__ = "1.2.3"\n',
            "debian/changelog": "minttweaks (1.2.3) unstable; urgency=medium\n\nPrevious changes.\n",
            "data/minttweaks.1": '.TH MINTTWEAKS 1 "date" "minttweaks 1.2.3"\n',
        }
        for name, text in self.contents.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def test_stamps_all_markers_with_the_same_build_version(self):
        version = "1.2.3~dev.12.1.aaaaaaaaaaaa"
        stamp_version(self.root, source_version(self.root), version)
        for name in self.contents:
            self.assertIn(version, (self.root / name).read_text())

    def test_invalid_marker_does_not_leave_a_partially_updated_checkout(self):
        (self.root / "data/minttweaks.1").write_text("wrong version")
        with self.assertRaises(ValueError):
            stamp_version(self.root, "1.2.3", "1.2.3~dev.12.1.aaaaaaaaaaaa")
        self.assertEqual((self.root / "minttweaks/__init__.py").read_text(), self.contents["minttweaks/__init__.py"])
        self.assertEqual((self.root / "debian/changelog").read_text(), self.contents["debian/changelog"])

    def test_cli_planning_is_read_only_unless_apply_is_requested(self):
        environment = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": SHA,
                       "GITHUB_RUN_NUMBER": "12", "GITHUB_RUN_ATTEMPT": "1"}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--root", str(self.root)], environment), 0)
        self.assertIn("channel=development", output.getvalue())
        self.assertEqual(source_version(self.root), "1.2.3")

    def test_stable_build_retains_the_source_version(self):
        stamp_version(self.root, "1.2.3", "1.2.3")
        for name, original in self.contents.items():
            self.assertEqual((self.root / name).read_text(), original)

    def test_pull_request_apply_does_not_stamp_or_publish(self):
        environment = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/pull/12/merge"}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--root", str(self.root), "--apply"], environment), 0)
        self.assertIn("publish=false", output.getvalue())
        self.assertEqual(source_version(self.root), "1.2.3")


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "calls.jsonl"
        fake = self.root / "gh"
        fake.write_text(f"#!{sys.executable}\n" + '''import json, os, sys
with open(os.environ['FAKE_GH_LOG'], 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1:3] == ['release', 'view']:
    sys.exit(0 if os.environ.get('FAKE_GH_EXISTS') == '1' else 1)
''')
        fake.chmod(0o755)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        for name in ("package.deb", "source.tar.gz", "SHA256SUMS"):
            (self.assets / name).write_text("fixture")

    def publish(self, channel, exists=False):
        env = dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ.get("PATH", ""),
                   FAKE_GH_LOG=str(self.log), FAKE_GH_EXISTS="1" if exists else "0")
        return subprocess.run(["bash", str(ROOT / "tools/publish-release.sh"), channel, "v1.2.3", "1.2.3", SHA,
                               str(self.assets)], env=env, capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_development_cannot_be_latest_or_standard(self):
        self.assertEqual(self.publish("development").returncode, 0)
        create = self.calls()[-1]
        self.assertEqual(create[:2], ["release", "create"])
        self.assertIn("--prerelease", create)
        self.assertIn("--latest=false", create)
        self.assertIn(str(self.assets / "SHA256SUMS"), create)
        self.assertIn(SHA, create)

    def test_stable_requires_an_existing_tag_and_does_not_set_prerelease(self):
        self.assertEqual(self.publish("stable").returncode, 0)
        create = self.calls()[-1]
        self.assertIn("--verify-tag", create)
        self.assertNotIn("--prerelease", create)
        self.assertNotIn("--clobber", create)

    def test_existing_stable_release_is_never_overwritten(self):
        result = self.publish("stable", exists=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("no assets or metadata were changed", result.stderr)

    def test_development_retry_restores_the_prerelease_flags(self):
        self.assertEqual(self.publish("development", exists=True).returncode, 0)
        calls = self.calls()
        self.assertEqual(calls[1][:2], ["release", "upload"])
        self.assertEqual(calls[2], ["release", "edit", "v1.2.3", "--prerelease", "--latest=false"])

    def test_invalid_channel_does_not_call_github(self):
        self.assertNotEqual(self.publish("unknown").returncode, 0)
        self.assertFalse(self.log.exists())
