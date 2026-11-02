"""Font fallback boundaries, network fixtures and real temporary font files."""
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

from minttweaks.modules.applications import backend, fonts, _apt_probe
from minttweaks.modules.applications.catalog import Application, CATALOG
from tests.fakes import FakeRunner
from tests.test_applications import ApplicationsRunner
from tests import fakegi
fakegi.install()
from minttweaks.modules.applications.page import ApplicationsPage
from minttweaks.ui.widgets import AppContext

FONT = Application('fonts-jetbrains-mono', 'JetBrains Mono', 'fonts-jetbrains-mono', 'Fonts')


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        for patcher in (patch.object(backend, 'CATALOG', (FONT,)),
                        patch.object(fonts.paths, 'DATA_DIR', self.base / 'minttweaks')):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.runner = ApplicationsRunner()
        self.runner.versions[FONT.package] = '1.0'

    def missing(self):
        self.runner.add_callable(['/usr/bin/python3', '-I', str(backend.PROBE)],
            lambda command: backend_read(command, {'error': 'No APT candidate', 'reason': 'missing'}))

    def test_official_apt_candidate_always_has_priority(self):
        entry = backend.collect_status(self.runner)[FONT.id]
        self.assertTrue(entry.installable)
        self.assertFalse(entry.github_available)

    def test_only_a_confirmed_missing_package_enables_github(self):
        self.missing()
        # FakeRunner prefers the first equal-length rule: replace the old handler.
        self.runner.rules = [rule for rule in self.runner.rules if not (rule[0][:1] == ('/usr/bin/python3',))] + [
            (('/usr/bin/python3', '-I', str(backend.PROBE)), lambda command: backend_read(command, {'error': 'No APT candidate', 'reason': 'missing'}))]
        entry = backend.collect_status(self.runner)[FONT.id]
        self.assertTrue(entry.github_available)
        self.assertFalse(entry.installable)
        with self.assertRaises(ValueError):
            backend.preview_install(self.runner, [FONT.id])

    def test_broken_or_third_party_apt_source_never_triggers_github(self):
        self.runner.bad_sources.add(FONT.package)
        entry = backend.collect_status(self.runner)[FONT.id]
        self.assertFalse(entry.github_available)
        self.assertTrue(entry.error)
        with patch.object(backend, 'probe', side_effect=ValueError('cache unreadable')):
            entry = backend.collect_status(self.runner)[FONT.id]
        self.assertFalse(entry.github_available)
        self.assertTrue(entry.error)

    def test_official_package_alternatives_are_used_only_for_missing_candidates(self):
        app = next(item for item in CATALOG if item.package == 'qemu')
        self.runner.versions['qemu-system'] = '2.0'
        def metadata(_runner, requests):
            return {request: ({'reason': 'missing', 'error': 'virtual package'} if request == 'qemu'
                    else {'version': request.split('=')[1] if '=' in request else '2.0', 'origins': ['Ubuntu | mirror | noble | universe']}) for request in requests}
        with patch.object(backend, 'CATALOG', (app,)), patch.object(backend, 'probe', side_effect=metadata):
            status = backend.collect_status(self.runner)['qemu']
            self.assertEqual(status.package, 'qemu-system')
            plan = backend.preview_install(self.runner, ['qemu'])
            self.assertEqual(plan.specs, ('qemu-system=2.0',))
            self.assertTrue(backend.install(self.runner, plan).ok)

    def test_probe_marks_absence_differently_from_source_failure(self):
        class Cache(dict):
            pass
        cache = Cache({'absent': SimpleNamespace(candidate=None)})
        capture = io.StringIO()
        with patch.dict('sys.modules', {'apt': SimpleNamespace(Cache=lambda: cache)}), \
                patch.object(Path, 'read_text', return_value='ID=linuxmint\nID_LIKE=ubuntu'), redirect_stdout(capture):
            self.assertEqual(_apt_probe.main(['unknown', 'absent']), 0)
        results = json.loads(capture.getvalue())
        self.assertEqual(results['unknown']['reason'], 'missing')
        self.assertEqual(results['absent']['reason'], 'missing')


def backend_read(command, info):
    from minttweaks.core.runner import Result
    return Result(str(command), 0, stdout=json.dumps({key: info for key in command.argv[3:]}))


class FontInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        patcher = patch.object(fonts.paths, 'DATA_DIR', self.base / 'minttweaks')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = FakeRunner().add(['fc-cache'])
        self.font = b'\x00\x01\x00\x00' + b'font test fixture'
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('fonts/ttf/Example.ttf', self.font)
            bundle.writestr('OFL.txt', 'font license')
            bundle.writestr('install.sh', 'should never be installed')
        self.archive = archive.getvalue()
        self.url = 'https://github.com/JetBrains/JetBrainsMono/releases/download/v1/JetBrainsMono-1.zip'
        self.release = {'tag_name': 'v1', 'assets': [{'name': 'JetBrainsMono-1.zip', 'browser_download_url': self.url,
                        'size': len(self.archive), 'digest': 'sha256:' + hashlib.sha256(self.archive).hexdigest()}]}
        self.network = patch.object(fonts, '_json', return_value=self.release)
        self.network.start()
        self.addCleanup(self.network.stop)
        self.downloader = patch.object(fonts, '_download', side_effect=lambda url, target, limit: target.write_bytes(self.archive))
        self.downloader.start()
        self.addCleanup(self.downloader.stop)

    def preview(self):
        return fonts.preview(FONT.package)

    def test_preview_reads_metadata_without_installing_fonts(self):
        plan = self.preview()
        self.assertEqual(plan.size, len(self.archive))
        self.assertFalse(plan.target.exists())
        self.assertFalse(self.runner.calls)

    def test_installs_only_fonts_and_licenses_without_root_or_scripts(self):
        plan = self.preview()
        fonts.install(self.runner, plan)
        self.assertEqual((plan.target / 'fonts/ttf/Example.ttf').read_bytes(), self.font)
        self.assertTrue((plan.target / 'OFL.txt').exists())
        self.assertFalse((plan.target / 'install.sh').exists())
        self.assertTrue(fonts.installed_version(FONT.package))
        self.assertEqual(self.runner.calls[0].argv[0], 'fc-cache')
        self.assertFalse(any(call.needs_root for call in self.runner.calls))

    def test_existing_fonts_are_never_overwritten(self):
        plan = self.preview()
        plan.target.mkdir(parents=True)
        (plan.target / 'personal.ttf').write_bytes(self.font)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            fonts.install(self.runner, plan)
        self.assertEqual((plan.target / 'personal.ttf').read_bytes(), self.font)

    def test_changed_release_or_checksum_blocks_publication(self):
        plan = self.preview()
        self.release['tag_name'] = 'v2'
        with self.assertRaisesRegex(ValueError, 'source changed'):
            fonts.install(self.runner, plan)
        self.assertFalse(plan.target.exists())
        self.release['tag_name'] = 'v1'
        with patch.object(fonts, '_download', side_effect=lambda url, target, limit: target.write_bytes(b'x' * len(self.archive))):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                fonts.install(self.runner, plan)
        self.assertFalse(plan.target.exists())

    def test_archive_traversal_and_symbolic_links_are_rejected(self):
        for name, symlink in [('../outside.ttf', False), ('font.ttf', True)]:
            archive = self.base / 'invalid.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                info = zipfile.ZipInfo(name)
                if symlink:
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                bundle.writestr(info, self.font)
            staged = self.base / 'staged'
            staged.mkdir(exist_ok=True)
            with self.assertRaises(ValueError):
                fonts._extract(archive, staged)
        self.assertFalse((self.base.parent / 'outside.ttf').exists())

    def test_invalid_font_signature_is_rejected(self):
        archive = self.base / 'invalid.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('font.ttf', b'not a font')
        staged = self.base / 'staged'
        staged.mkdir()
        with self.assertRaisesRegex(ValueError, 'invalid'):
            fonts._extract(archive, staged)

    def test_corrupted_installed_font_is_not_reported_as_verified(self):
        plan = self.preview()
        fonts.install(self.runner, plan)
        (plan.target / 'fonts/ttf/Example.ttf').write_bytes(b'changed')
        self.assertFalse(fonts.installed_version(FONT.package))

    def test_fontconfig_error_reports_files_already_installed(self):
        self.runner = FakeRunner().add(['fc-cache'], returncode=1, stderr='cache failure')
        plan = self.preview()
        with self.assertRaisesRegex(ValueError, 'files were installed'):
            fonts.install(self.runner, plan)
        self.assertTrue(plan.target.exists())

    def test_dry_run_performs_no_metadata_or_font_download(self):
        plan = self.preview()
        self.runner.dry_run = True
        with patch.object(fonts, '_json') as metadata, patch.object(fonts, '_download') as download:
            fonts.install(self.runner, plan)
        metadata.assert_not_called()
        download.assert_not_called()
        self.assertFalse(plan.target.exists())
        self.assertFalse(self.runner.calls)

    def test_redirects_are_limited_to_github_https_hosts(self):
        for url in ['http://github.com/file', 'https://evil.example/file', 'https://user@github.com/file']:
            with self.assertRaises(ValueError):
                fonts._url(url)
        self.assertEqual(fonts._url(self.url), self.url)

    def test_noto_files_are_pinned_to_git_revision_and_reject_truncated_lists(self):
        commit = 'a' * 40
        blob = hashlib.sha1(b'blob ' + str(len(self.font)).encode() + b'\x00' + self.font).hexdigest()
        data = {'tree': [{'type': 'blob', 'mode': '100644', 'path': 'hinted/ttf/NotoSans/NotoSans-Regular.ttf', 'sha': blob, 'size': len(self.font)}]}
        with patch.object(fonts, '_json', side_effect=[{'sha': commit}, data]):
            revision, downloads = fonts._tree('notofonts/noto-fonts', ('hinted/ttf/',), ())
        self.assertIn(commit, downloads[0].url)
        self.assertEqual(downloads[0].digest, 'git-sha1:' + blob)
        with patch.object(fonts, '_json', side_effect=[{'sha': commit}, {'truncated': True}]):
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                fonts._tree('notofonts/noto-fonts', ('hinted/ttf/',), ())


class FontPageTests(unittest.TestCase):
    def test_cancelled_font_confirmation_never_installs(self):
        with patch.object(backend, 'CATALOG', (FONT,)):
            page = ApplicationsPage(AppContext(FakeRunner()))
        plan = fonts.FontPlan(FONT.package, Path('/fonts/example'), ('upstream@v1',), ())
        page._busy = True
        with patch('minttweaks.ui.widgets.confirm_list', return_value=False), patch.object(page, 'run_operation') as run:
            page._confirm_font(FONT.id, plan)
        run.assert_not_called()
        self.assertFalse(page._busy)
