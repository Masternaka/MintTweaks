"""Dotfiles transfer carries references, never source-machine paths or actions."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from minttweaks.modules.dotfiles import backend, transfer
from tests.fakes import FakeRunner
from tests import fakegi

fakegi.install()
from minttweaks.modules.dotfiles.page import DotfilesPage
from minttweaks.ui.widgets import AppContext

URL = 'https://github.com/example/dotfiles.git'


class ReferenceTransferTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.target = self.root / 'target'
        self.target.mkdir()
        self.precious = self.target / '.bashrc'
        self.precious.write_text('personal data kept')
        self.repository = self.root / 'new-clone'
        self.source = self.root / 'reference.json'
        self.runner = FakeRunner()
        self.export = transfer.preview_export(URL, ('bash', 'kitty'), True)
        self.source.write_text(self.export.text)

    def preview(self):
        return transfer.preview_import(self.runner, self.source)

    def test_portable_file_contains_only_the_approved_reference_fields(self):
        document = json.loads(self.export.text)
        self.assertEqual(set(document), {'schema_version', 'kind', 'repository_url', 'packages', 'dotfiles'})
        self.assertEqual(document['repository_url'], URL)
        self.assertEqual(document['packages'], ['bash', 'kitty'])
        self.assertIs(document['dotfiles'], True)
        self.assertNotIn(str(self.root), self.export.text)

    def test_import_prepares_local_paths_without_cloning_or_changing_files(self):
        plan = self.preview()
        prepared = transfer.prepare_import(self.runner, plan, self.repository, self.target)
        result = transfer.confirm_import(self.runner, prepared)
        self.assertEqual(result.repository, self.repository)
        self.assertEqual(result.target, self.target)
        self.assertEqual(result.plan.reference, self.export.reference)
        self.assertFalse(self.repository.exists())
        self.assertEqual(self.precious.read_text(), 'personal data kept')
        self.assertFalse(self.runner.calls)

    def test_existing_repository_is_accepted_without_editing_or_inspecting_git(self):
        self.repository.mkdir()
        marker = self.repository / 'keep.txt'
        marker.write_text('existing repository content')
        prepared = transfer.prepare_import(self.runner, self.preview(), self.repository, self.target)
        transfer.confirm_import(self.runner, prepared)
        self.assertEqual(marker.read_text(), 'existing repository content')
        self.assertFalse((self.repository / '.git').exists())
        self.assertFalse(self.runner.calls)

    def test_false_option_and_ssh_url_are_preserved(self):
        plan = transfer.preview_export('git@github.com:example/dotfiles.git', ('bash',), False)
        self.source.write_text(plan.text)
        ref = self.preview().reference
        self.assertIs(ref.dotfiles, False)
        self.assertEqual(ref.repository_url, 'git@github.com:example/dotfiles.git')

    def test_urls_with_credentials_queries_fragments_or_traversal_are_rejected(self):
        for url in ('https://secret@github.com/a/b', 'https://github.com/a/b?token=secret',
                    'https://github.com/a/b#main', 'file:///private/repo', 'https://evil.example/a/b',
                    'https://github.com/../b', 'https://github.com/a/..', 'git@github.com:a/..git',
                    '--upload-pack=evil', 'https://github.com/a/.git'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                transfer.preview_export(url, ('bash',), False)
        self.assertFalse(self.runner.calls)

    def test_package_traversal_options_duplicates_reserved_names_and_non_bool_are_rejected(self):
        for packages in ((), ('../bash',), ('--adopt',), ('bash/child',), ('bash', 'bash'), ('scripts',), (1,)):
            with self.subTest(packages=packages), self.assertRaises(ValueError):
                transfer.preview_export(URL, packages, False)
        for value in (0, 1, 'true', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                transfer.preview_export(URL, ('bash',), value)

    def test_import_rejects_machine_paths_commands_options_and_future_formats(self):
        document = json.loads(self.export.text)
        values = [dict(document, repository='/source-machine/dotfiles'),
                  dict(document, target='/source-machine/home'), dict(document, command='run script'),
                  dict(document, options=['--adopt']), dict(document, schema_version=99),
                  dict(document, kind='other-kind'), dict(document, dotfiles=1)]
        for value in values:
            raw = json.dumps(value)
            self.source.write_text(raw)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.preview()
            self.assertEqual(self.source.read_text(), raw)
        self.assertFalse(self.repository.exists())
        self.assertFalse(self.runner.calls)

    def test_corrupt_duplicate_and_oversized_sources_are_preserved(self):
        for raw in (b'{broken', b'[]', b'{"schema_version":1,"schema_version":2}', b'x' * (transfer.MAX_BYTES + 1)):
            self.source.write_bytes(raw)
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                self.preview()
            self.assertEqual(self.source.read_bytes(), raw)

    def test_symbolic_source_and_special_files_are_refused(self):
        link = self.root / 'link.json'
        link.symlink_to(self.source)
        with self.assertRaises(OSError):
            transfer.preview_import(self.runner, link)
        fifo = self.root / 'fifo'
        transfer.os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            transfer.preview_import(self.runner, fifo)

    def test_source_changes_after_path_preview_require_another_confirmation(self):
        prepared = transfer.prepare_import(self.runner, self.preview(), self.repository, self.target)
        self.source.write_text(self.export.text + '\n')
        with self.assertRaisesRegex(ValueError, 'changed after its preview'):
            transfer.confirm_import(self.runner, prepared)
        self.assertEqual(self.precious.read_text(), 'personal data kept')

    def test_target_inside_repository_and_invalid_local_paths_are_refused(self):
        self.repository.mkdir()
        inside = self.repository / 'inside'
        inside.mkdir()
        bad = ((self.repository, self.repository), (self.repository, inside),
               ('relative-path', self.target), (self.repository, self.root / 'missing-target'),
               (self.root / 'missing-parent' / 'new-clone', self.target),
               (self.repository / '..' / 'new', self.target))
        for repository, target in bad:
            with self.subTest(repository=repository, target=target), self.assertRaises(ValueError):
                transfer.prepare_import(self.runner, self.preview(), repository, target)

    def test_local_directory_replaced_with_symlink_is_refused_before_form_update(self):
        prepared = transfer.prepare_import(self.runner, self.preview(), self.repository, self.target)
        other = self.root / 'other'
        other.mkdir()
        self.repository.symlink_to(other)
        with self.assertRaises(ValueError):
            transfer.confirm_import(self.runner, prepared)
        self.assertEqual(list(other.iterdir()), [])
        self.assertEqual(self.precious.read_text(), 'personal data kept')

    def test_export_publishes_reviewed_bytes_privately_without_overwriting(self):
        destination = self.root / 'export.json'
        transfer.export(self.runner, self.export, destination)
        self.assertEqual(destination.read_bytes(), self.export.text.encode())
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            transfer.export(self.runner, self.export, destination)
        link = self.root / 'broken.json'
        link.symlink_to(self.root / 'absent')
        with self.assertRaises(ValueError):
            transfer.export(self.runner, self.export, link)
        self.assertTrue(link.is_symlink())
        self.assertFalse(self.runner.calls)

    def test_failed_export_and_changed_plan_leave_no_partial_file(self):
        destination = self.root / 'export.json'
        with patch.object(transfer.os, 'fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                transfer.export(self.runner, self.export, destination)
        with self.assertRaises(ValueError):
            transfer.export(self.runner, replace(self.export, text='unreviewed'), destination)
        self.assertFalse(destination.exists())
        self.assertFalse(any(path.name.startswith('.mtk-') for path in self.root.iterdir()))

    def test_simulation_does_not_read_import_sources_paths_or_write_exports(self):
        plan = self.preview()
        self.runner.dry_run = True
        with patch.object(transfer.os, 'open') as open_, patch.object(backend, 'directory') as directory:
            with self.assertRaises(ValueError):
                self.preview()
            self.assertIsNone(transfer.prepare_import(self.runner, plan, self.repository, self.target))
            self.assertIsNone(transfer.confirm_import(self.runner, None))
            self.assertIsNone(transfer.export(self.runner, self.export, self.root / 'export.json'))
        open_.assert_not_called()
        directory.assert_not_called()
        self.assertFalse(self.repository.exists())


class ReferenceTransferPageTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.context = AppContext(self.runner)
        self.page = DotfilesPage(self.context)
        self.page.url.get_text = Mock(return_value=URL)
        self.page.repository.get_text = Mock(return_value='/local/repo')
        self.page.target.get_text = Mock(return_value='/local/home')
        self.page.dotfiles.get_active = Mock(return_value=True)
        self.ref = transfer.reference(URL, ('bash', 'kitty'), True)
        self.plan = transfer.ImportPlan(Path('/reference.json'), 'digest', self.ref)
        self.prepared = transfer.LocalImport(self.plan, Path('/local/repo'), Path('/local/home'))

    def test_export_picker_keeps_pending_reference_choices_after_local_path_changes(self):
        self.page._reference = self.ref
        self.page._analysed_packages = {'bash': backend.Package('bash', files=1)}
        self.page._invalidate()
        self.assertEqual(self.page._reference_candidates(), ('bash', 'kitty'))
        self.assertEqual(self.page._analysed_packages, {})

    def test_changing_repository_url_clears_the_previous_reference(self):
        self.page._reference = self.ref
        self.page.url.get_text.return_value = 'https://github.com/other/dotfiles'
        self.page._invalidate()
        self.assertIsNone(self.page._reference)

    def test_cancelled_export_never_opens_save_dialog_or_runs_an_operation(self):
        self.page._analysed_packages = {'bash': backend.Package('bash', files=1)}
        with patch.object(self.page, '_choose_reference_packages', return_value=None), \
                patch.object(self.page, '_choose_reference_file') as choose, \
                patch.object(self.page, 'run_operation') as run:
            self.page._export_reference()
        choose.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.page._busy)

    def test_cancelled_import_path_choice_does_not_change_existing_form(self):
        with patch.object(self.page, '_choose_reference_paths', return_value=None), \
                patch.object(self.page.url, 'set_text') as url, \
                patch.object(self.context, 'run_async') as work:
            self.page._prepare_reference_paths(self.plan)
        url.assert_not_called()
        work.assert_not_called()
        self.assertFalse(self.page._busy)

    def test_import_confirmation_shows_paths_options_and_names_without_applying(self):
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False) as confirm, \
                patch.object(self.page, 'run_operation') as run:
            self.page._confirm_reference_import(self.prepared)
        text = '\n'.join(confirm.call_args.args[2])
        for expected in (URL, 'bash', 'kitty', '/local/repo', '/local/home', 'Yes'):
            self.assertIn(expected, text)
        run.assert_not_called()

    def test_confirmed_import_only_fills_fields_and_keeps_old_links_untouched(self):
        with patch.object(self.page.url, 'set_text') as url, \
                patch.object(self.page.repository, 'set_text') as repository, \
                patch.object(self.page.target, 'set_text') as target, \
                patch.object(self.page.dotfiles, 'set_active') as dotfiles, \
                patch.object(self.page, 'refresh') as analyse, \
                patch.object(backend, 'clone') as clone, \
                patch('minttweaks.modules.dotfiles.deployments.activate') as activate, \
                patch('minttweaks.modules.dotfiles.deployments.undo') as undo:
            self.page._reference_imported(self.prepared)
        url.assert_called_once_with(URL)
        repository.assert_called_once_with('/local/repo')
        target.assert_called_once_with('/local/home')
        dotfiles.assert_called_once_with(True)
        for action in (analyse, clone, activate, undo):
            action.assert_not_called()
        self.assertEqual(self.page._reference, self.ref)
        self.assertFalse(self.runner.calls)
        self.assertFalse(self.page._busy)
        self.assertFalse(self.page._updating_reference)

    def test_busy_reservation_keeps_existing_reference_and_form(self):
        self.page._reference = self.ref
        with patch.object(self.context, 'run_async'):
            self.context.run_operation('Another operation', lambda: None)
        with patch('minttweaks.ui.widgets.confirm_list', return_value=True), \
                patch.object(transfer, 'confirm_import') as import_, \
                patch.object(self.page.url, 'set_text') as url, \
                patch.object(self.page, 'error') as error:
            self.page._confirm_reference_import(self.prepared)
        import_.assert_not_called()
        url.assert_not_called()
        error.assert_called_once()
        self.assertEqual(self.page._reference, self.ref)
        self.assertFalse(self.page._busy)

    def test_analysis_marks_reference_choices_and_retains_missing_names(self):
        self.page._reference = self.ref
        self.page._show_packages((backend.Package('bash', files=1),))
        self.assertIn('Found in the last analysis', self.page._reference_state('bash'))
        self.assertIn('Pending analysis', self.page._reference_state('kitty'))
        self.assertEqual(self.page._reference.packages, ('bash', 'kitty'))

    def test_simulation_never_opens_reference_dialogs(self):
        self.page._reference = self.ref
        self.runner.dry_run = True
        with patch.object(self.page, '_choose_reference_file') as file_, \
                patch.object(self.page, '_choose_reference_packages') as choices:
            self.page._export_reference()
            self.page._import_reference()
        file_.assert_not_called()
        choices.assert_not_called()
