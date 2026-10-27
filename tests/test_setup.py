"""Persist only user-declared checklist progress in temporary test files."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minttweaks.modules.setup import backend
from tests.fakes import FakeRunner


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "data" / "setup-plan.json"
        self.runner = FakeRunner()

    def save(self, plan, selected=None, **kwargs):
        return backend.save_plan(self.runner, plan, plan.selected if selected is None else selected, path=self.path, **kwargs)

    def test_missing_progress_does_not_create_any_file(self):
        plan = backend.load_plan(self.path)
        self.assertEqual(plan.selected, [])
        self.assertIsNone(plan.next_step)
        self.assertFalse(self.path.parent.exists())

    def test_selection_and_verification_survive_reopening(self):
        plan = self.save(backend.Plan(), ["health", "firefox", "cinnamon"])
        self.assertEqual(plan.next_step.id, "health")
        plan = self.save(plan, step_id="health", state="verified", note="Checked manually")
        reopened = backend.load_plan(self.path)
        self.assertEqual(reopened.verified, 1)
        self.assertEqual(reopened.next_step.id, "firefox")
        self.assertEqual(reopened.progress["health"].note, "Checked manually")
        self.assertFalse(self.runner.calls)

    def test_retry_keeps_completed_steps_and_the_error_note(self):
        plan = self.save(backend.Plan(), ["health", "firefox"])
        plan = self.save(plan, step_id="health", state="verified")
        plan = self.save(plan, step_id="firefox", state="retry", note="Firefox restart still required")
        reopened = backend.load_plan(self.path)
        self.assertEqual(reopened.next_step.id, "firefox")
        self.assertEqual(reopened.progress["health"].state, "verified")
        self.assertEqual(reopened.progress["firefox"].note, "Firefox restart still required")

    def test_deselecting_and_reselecting_a_step_keeps_its_previous_progress(self):
        plan = self.save(backend.Plan(), ["health", "firefox"])
        plan = self.save(plan, step_id="health", state="verified")
        plan = self.save(plan, ["firefox"])
        plan = self.save(plan, ["health", "firefox"])
        self.assertEqual(plan.progress["health"].state, "verified")
        self.assertEqual(plan.next_step.id, "firefox")

    def test_no_next_step_remains_after_all_selected_steps_are_verified(self):
        plan = self.save(backend.Plan(), ["health"])
        plan = self.save(plan, step_id="health", state="verified")
        self.assertIsNone(plan.next_step)
        plan = self.save(plan, step_id="health", state="pending")
        self.assertEqual(plan.next_step.id, "health")

    def test_unknown_duplicate_and_unselected_steps_cannot_be_saved(self):
        for selected in (["unknown"], ["health", "health"]):
            with self.subTest(selected=selected), self.assertRaises(backend.PlanError):
                self.save(backend.Plan(), selected)
        with self.assertRaises(backend.PlanError):
            self.save(backend.Plan(), ["health"], step_id="firefox", state="verified")
        self.assertFalse(self.path.exists())

    def test_private_file_permissions_and_unicode_notes(self):
        plan = self.save(backend.Plan(), ["cinnamon"])
        self.save(plan, step_id="cinnamon", state="verified", note="Thème d’été vérifié")
        self.assertEqual(backend.load_plan(self.path).progress["cinnamon"].note, "Thème d’été vérifié")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_stale_revision_does_not_overwrite_newer_progress(self):
        original = self.save(backend.Plan(), ["health"])
        updated = self.save(original, step_id="health", state="verified")
        with self.assertRaises(backend.PlanError):
            self.save(original, step_id="health", state="retry")
        self.assertEqual(backend.load_plan(self.path), updated)

    def test_failed_atomic_replacement_preserves_previous_bytes(self):
        plan = self.save(backend.Plan(), ["health"])
        original = self.path.read_bytes()
        with patch.object(backend.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.save(plan, step_id="health", state="verified")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_corrupted_and_future_files_are_preserved(self):
        self.save(backend.Plan(), ["health"])
        future = json.loads(self.path.read_text())
        future["schema_version"] = 99
        for raw in ('{broken', json.dumps(future), '{"revision": 1, "revision": 2}'):
            self.path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(backend.PlanError):
                self.save(backend.Plan(), ["health"])
            self.assertEqual(self.path.read_text(), raw)

    def test_symbolic_progress_file_is_never_followed_or_replaced(self):
        target = Path(self.tmp.name) / "precious.json"
        target.write_text("precious")
        self.path.parent.mkdir()
        self.path.symlink_to(target)
        with self.assertRaises(backend.PlanError):
            self.save(backend.Plan(), ["health"])
        self.assertEqual(target.read_text(), "precious")
        self.assertTrue(self.path.is_symlink())

    def test_simulation_cannot_persist_selection_or_progress(self):
        self.runner.dry_run = True
        with self.assertRaises(backend.PlanError):
            self.save(backend.Plan(), ["health"])
        self.assertFalse(self.path.parent.exists())

    def test_invalid_note_does_not_change_saved_progress(self):
        plan = self.save(backend.Plan(), ["health"])
        original = self.path.read_bytes()
        for note in ("x" * 501, "bad\nline", "bad\x00", "bad\u0085"):
            with self.subTest(note=note), self.assertRaises(backend.PlanError):
                self.save(plan, step_id="health", state="verified", note=note)
        self.assertEqual(self.path.read_bytes(), original)

    def test_oversized_checklist_is_preserved(self):
        self.path.parent.mkdir()
        original = b" " * (backend.MAX_BYTES + 1)
        self.path.write_bytes(original)
        with self.assertRaises(backend.PlanError):
            self.save(backend.Plan(), ["health"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_legacy_progress_is_preserved_without_selecting_new_steps_or_rewriting_on_read(self):
        plan = self.save(backend.Plan(), ["health", "firefox"])
        plan = self.save(plan, step_id="health", state="verified", note="Already checked")
        legacy = json.loads(self.path.read_text())
        legacy["schema_version"] = 1
        legacy["progress"].pop("software")
        legacy["progress"].pop("terminal")
        self.path.write_text(json.dumps(legacy))
        original = self.path.read_bytes()
        loaded = backend.load_plan(self.path)
        self.assertEqual(loaded.selected, ["health", "firefox"])
        self.assertEqual(loaded.progress["health"].state, "verified")
        self.assertEqual(loaded.progress["health"].note, "Already checked")
        self.assertEqual(loaded.progress["software"].state, "pending")
        self.assertEqual(self.path.read_bytes(), original)
        self.save(loaded, ["health", "software", "firefox"])
        self.assertEqual(json.loads(self.path.read_text())["schema_version"], 3)

    def test_version_two_adds_terminal_unselected_and_preserves_existing_progress(self):
        plan = self.save(backend.Plan(), ['software'])
        self.save(plan, step_id='software', state='verified', note='Browsers checked')
        old = json.loads(self.path.read_text())
        old['schema_version'] = 2
        old['progress'].pop('terminal')
        self.path.write_text(json.dumps(old))
        original = self.path.read_bytes()
        loaded = backend.load_plan(self.path)
        self.assertEqual(loaded.selected, ['software'])
        self.assertEqual(loaded.progress['software'].state, 'verified')
        self.assertEqual(loaded.progress['terminal'].state, 'pending')
        self.assertEqual(self.path.read_bytes(), original)
        self.save(loaded, ['software', 'terminal'])
        self.assertEqual(json.loads(self.path.read_text())['schema_version'], 3)
