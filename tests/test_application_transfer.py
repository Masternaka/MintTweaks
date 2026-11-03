"""Application selection transfer never installs or trusts source-file packages."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from minttweaks.modules.applications import backend, transfer
from minttweaks.modules.applications.catalog import Application
from tests.test_applications import APP, OTHER
from tests.fakes import FakeRunner
from tests import fakegi

fakegi.install()
from minttweaks.modules.applications.page import ApplicationsPage
from minttweaks.ui.widgets import AppContext

FONT = Application('fonts-firacode', 'Fira Code', 'fonts-firacode', 'Fonts')
MISSING = Application('missing-app', 'Unavailable application', 'missing-package', 'Utilities')
PENDING = Application('existing-choice', 'Already selected', 'existing-choice-package', 'Utilities')
CATALOG = (APP, OTHER, FONT, MISSING, PENDING)


class ApplicationTransferTests(unittest.TestCase):
    def setUp(self):
        catalog = patch.object(backend, 'CATALOG', CATALOG)
        catalog.start()
        self.addCleanup(catalog.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / 'choices.json'
        self.runner = FakeRunner()
        self.plan = transfer.preview_export((APP.id, FONT.id))
        self.source.write_text(self.plan.text)

    def test_round_trip_preserves_choices_and_does_not_query_or_install(self):
        imported = transfer.preview_import(self.runner, self.source)
        self.assertEqual(transfer.confirm_import(self.runner, imported), (APP.id, FONT.id))
        exported = self.root / 'export.json'
        transfer.export(self.runner, self.plan, exported)
        self.assertEqual(exported.read_bytes(), self.plan.text.encode())
        self.assertEqual(exported.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.source.read_text(), self.plan.text)
        self.assertFalse(self.runner.calls)

    def test_only_references_are_exported_without_versions_paths_or_sources(self):
        data = json.loads(self.plan.text)
        self.assertEqual(set(data), {'schema_version', 'kind', 'applications'})
        self.assertEqual(data['applications'][0], {'id': APP.id, 'package': APP.package})
        self.assertEqual(data['kind'], transfer.KIND)

    def test_alternatives_stay_portable_as_primary_catalog_references(self):
        entry = Application('7zip', '7-Zip', '7zip', 'Utilities', alternatives=('p7zip-full',))
        with patch.object(backend, 'CATALOG', (entry,)):
            plan = transfer.preview_export(('7zip',))
        self.assertIn('"package": "7zip"', plan.text)
        self.assertNotIn('p7zip-full', plan.text)

    def test_invalid_unknown_and_duplicate_choices_are_refused(self):
        for ids in ((), ('unknown',), (APP.id, APP.id), ([APP.id],), (1,), 'editor'):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                transfer.preview_export(ids)
        self.assertFalse(self.runner.calls)

    def test_unknown_fields_commands_repositories_and_package_substitution_are_rejected(self):
        original = json.loads(self.plan.text)
        payloads = [dict(original, schema_version=99), dict(original, kind='another-export'),
                    dict(original, command='touch /must-not-run'), dict(original, repository='https://example.invalid')]
        for field, value in (('package', '--install-anything'), ('id', 'unknown')):
            changed = json.loads(self.plan.text)
            changed['applications'][0][field] = value
            payloads.append(changed)
        duplicate = json.loads(self.plan.text)
        duplicate['applications'].append(dict(duplicate['applications'][0]))
        payloads.append(duplicate)
        for data in payloads:
            raw = json.dumps(data)
            self.source.write_text(raw)
            with self.subTest(data=data), self.assertRaises(ValueError):
                transfer.preview_import(self.runner, self.source)
            self.assertEqual(self.source.read_text(), raw)
        self.assertFalse(self.runner.calls)

    def test_duplicate_json_keys_and_incomplete_or_oversized_files_are_preserved(self):
        for raw in (b'{broken', b'[]', b'{"kind": "first", "kind": "second"}', b'\xff', b'x' * (transfer.MAX_BYTES + 1)):
            self.source.write_bytes(raw)
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                transfer.preview_import(self.runner, self.source)
            self.assertEqual(self.source.read_bytes(), raw)

    def test_file_change_after_preview_requires_another_confirmation(self):
        imported = transfer.preview_import(self.runner, self.source)
        self.source.write_text(self.plan.text + '\n')
        with self.assertRaisesRegex(ValueError, 'changed after its preview'):
            transfer.confirm_import(self.runner, imported)
        self.assertFalse(self.runner.calls)

    def test_source_symlinks_and_special_files_are_refused(self):
        source_link = self.root / 'source-link.json'
        source_link.symlink_to(self.source)
        with self.assertRaises(OSError):
            transfer.preview_import(self.runner, source_link)
        fifo = self.root / 'fifo'
        transfer.os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            transfer.preview_import(self.runner, fifo)

    def test_existing_export_files_and_links_are_not_overwritten(self):
        link = self.root / 'broken.json'
        link.symlink_to(self.root / 'absent')
        for target in (self.source, link):
            with self.assertRaises(ValueError):
                transfer.export(self.runner, self.plan, target)
        self.assertEqual(self.source.read_text(), self.plan.text)
        self.assertTrue(link.is_symlink())

    def test_changed_export_plan_is_refused_before_file_creation(self):
        changed = replace(self.plan, text=self.plan.text + 'unreviewed')
        with self.assertRaises(ValueError):
            transfer.export(self.runner, changed, self.root / 'export.json')
        self.assertFalse((self.root / 'export.json').exists())

    def test_failed_export_leaves_no_partial_file(self):
        with patch.object(transfer.os, 'fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                transfer.export(self.runner, self.plan, self.root / 'export.json')
        self.assertEqual(list(self.root.iterdir()), [self.source])

    def test_simulation_never_reads_imports_or_writes_exports(self):
        imported = transfer.preview_import(self.runner, self.source)
        self.runner.dry_run = True
        with patch.object(transfer.os, 'open') as open_:
            with self.assertRaises(ValueError):
                transfer.preview_import(self.runner, self.source)
            self.assertEqual(transfer.confirm_import(self.runner, imported), ())
            self.assertIsNone(transfer.export(self.runner, self.plan, self.root / 'export.json'))
        open_.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [self.source])


class ApplicationTransferPageTests(unittest.TestCase):
    def setUp(self):
        catalog = patch.object(backend, 'CATALOG', CATALOG)
        catalog.start()
        self.addCleanup(catalog.stop)
        self.runner = FakeRunner()
        self.context = AppContext(self.runner)
        self.page = ApplicationsPage(self.context)
        self.page.search.get_text = Mock(return_value='')
        self.status = {
            APP.id: backend.ApplicationStatus(package=APP.package, candidate='1.2'),
            OTHER.id: backend.ApplicationStatus(package=OTHER.package, installed=True, installed_version='1.0'),
            FONT.id: backend.ApplicationStatus(package=FONT.package, github_available=True),
            MISSING.id: backend.ApplicationStatus(package=MISSING.package, error='No trusted source'),
            PENDING.id: backend.ApplicationStatus(package=PENDING.package, candidate='1.0'),
        }
        self.active = {key: key == PENDING.id for key in self.page.checks}
        for key, check in self.page.checks.items():
            check.get_active = Mock(side_effect=lambda key=key: self.active[key])
            check.set_active = Mock(side_effect=lambda value, key=key: self.active.__setitem__(key, value))
        self.page.status = self.status
        self.plan = transfer.ImportPlan(Path('/selection.json'), 'digest', (APP.id, OTHER.id, FONT.id, MISSING.id))

    def test_import_keeps_existing_choices_and_installs_nothing(self):
        with patch.object(backend, 'install') as install, patch.object(backend, 'preview_install') as preview:
            self.page._selection_imported((self.plan.ids, self.status))
        self.assertTrue(self.active[APP.id])
        self.assertTrue(self.active[PENDING.id])
        self.assertFalse(self.active[OTHER.id])
        self.assertFalse(self.active[FONT.id])
        self.assertFalse(self.active[MISSING.id])
        self.assertEqual(self.page._transfer_ids, self.plan.ids)
        install.assert_not_called()
        preview.assert_not_called()
        self.assertFalse(self.runner.calls)

    def test_import_confirmation_lists_all_dispositions_and_cancel_preserves_choices(self):
        self.page._transfer_ids = (PENDING.id,)
        before = dict(self.active)
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm, \
                patch.object(self.page, 'run_operation') as run:
            self.page._confirm_selection_import((self.plan, self.status))
        text = '\n'.join(confirm.call_args.args[2])
        for expected in ('Ready for', 'Already installed', 'separate preview', 'retained for later'):
            self.assertIn(expected, text)
        self.assertEqual(self.active, before)
        self.assertEqual(self.page._transfer_ids, (PENDING.id,))
        run.assert_not_called()

    def test_confirmed_import_uses_fresh_availability_and_skips_newly_installed_apps(self):
        fresh = dict(self.status)
        fresh[APP.id] = backend.ApplicationStatus(package=APP.package, installed=True, installed_version='2.0')
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), \
                patch.object(self.page, 'run_operation') as run, \
                patch.object(transfer, 'confirm_import', return_value=self.plan.ids), \
                patch.object(backend, 'collect_status', return_value=fresh):
            self.page._confirm_selection_import((self.plan, self.status))
            result = run.call_args.args[0]()
        self.page._selection_imported(result)
        self.assertFalse(self.active[APP.id])
        self.assertIn(APP.id, self.page._transfer_ids)

    def test_unavailable_choices_can_be_prepared_after_a_later_analysis(self):
        self.page._selection_imported((self.plan.ids, self.status))
        self.page.status[MISSING.id] = backend.ApplicationStatus(package=MISSING.package, candidate='1.0')
        with patch.object(self.page, 'run_operation') as run:
            self.page._prepare_transferred()
        self.assertTrue(self.active[MISSING.id])
        run.assert_not_called()

    def test_busy_reservation_preserves_previous_transfer_list(self):
        self.page._transfer_ids = (PENDING.id,)
        with patch.object(self.context, 'run_async'):
            self.context.run_operation('Another operation', lambda: None)
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), \
                patch.object(self.page, 'error') as error, patch.object(transfer, 'confirm_import') as read:
            self.page._confirm_selection_import((self.plan, self.status))
        read.assert_not_called()
        error.assert_called_once()
        self.assertEqual(self.page._transfer_ids, (PENDING.id,))
        self.assertFalse(self.page._busy)

    def test_export_chooser_cancel_does_not_modify_installation_choices(self):
        before = dict(self.active)
        with patch.object(self.page, '_choose_export_ids', return_value=None), \
                patch.object(self.page, '_choose_selection_file') as choose, \
                patch.object(self.page, 'run_operation') as run:
            self.page._export_selection()
        choose.assert_not_called()
        run.assert_not_called()
        self.assertEqual(self.active, before)
        self.assertFalse(self.page._busy)

    def test_cancelled_export_preview_never_writes(self):
        with patch.object(self.page, '_choose_export_ids', return_value=(APP.id,)), \
                patch('minttweaks.ui.widgets.confirm_list', return_value=False), \
                patch.object(self.page, '_choose_selection_file') as choose, \
                patch.object(self.page, 'run_operation') as run:
            self.page._export_selection()
        choose.assert_not_called()
        run.assert_not_called()

    def test_detected_apps_are_added_only_by_the_explicit_export_dialog_action(self):
        for add_detected in (False, True):
            state, actions = {}, {}
            def checkbox(label):
                check = Mock()
                state[label] = False
                check.set_active.side_effect = lambda value: state.__setitem__(label, value)
                check.get_active.side_effect = lambda: state[label]
                return check
            def button(title, action):
                actions[title] = action
                return Mock()
            def accept():
                if add_detected:
                    actions['Add applications detected in the last analysis']()
                return widgets.Gtk.ResponseType.OK
            from minttweaks.ui import widgets
            with patch.object(widgets.Gtk, 'CheckButton', side_effect=checkbox), \
                    patch.object(widgets.Gtk, 'Dialog') as dialog, \
                    patch.object(widgets, 'button', side_effect=button):
                dialog.return_value.run.side_effect = accept
                ids = self.page._choose_export_ids()
            self.assertIn(PENDING.id, ids)
            self.assertEqual(OTHER.id in ids, add_detected)
            self.assertNotIn(MISSING.id, ids)

    def test_cancelled_export_file_chooser_does_not_start_an_operation(self):
        with patch.object(self.page, '_choose_export_ids', return_value=(APP.id,)), \
                patch('minttweaks.ui.widgets.confirm_list', return_value=True), \
                patch.object(self.page, '_choose_selection_file', return_value=None), \
                patch.object(self.page, 'run_operation') as run:
            self.page._export_selection()
        run.assert_not_called()
        self.assertFalse(self.page._busy)

    def test_simulation_never_opens_transfer_choosers(self):
        self.runner.dry_run = True
        with patch.object(self.page, '_choose_selection_file') as choose, \
                patch.object(self.page, '_choose_export_ids') as choices:
            self.page._export_selection()
            self.page._import_selection()
        choose.assert_not_called()
        choices.assert_not_called()
