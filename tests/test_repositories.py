"""Repository recipes write only into temporary directories in these tests."""

import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from minttweaks.modules.software import repositories as repo
from minttweaks.modules.software import backend
from tests.test_software import BrowserRunner


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.sources = self.root / 'sources'
        self.keys = self.root / 'keys'
        self.sources.mkdir()
        self.keys.mkdir()
        for attr, path in [('SOURCES_DIR', self.sources), ('KEYRINGS_DIR', self.keys), ('MAIN_SOURCE', self.root / 'sources.list')]:
            patcher = patch.object(repo, attr, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.download = patch.object(repo, 'download_key', return_value=b'binary key').start()
        self.run = patch.object(repo, 'run', side_effect=self.reply).start()
        self.addCleanup(patch.stopall)

    def reply(self, argv, **kwargs):
        return CompletedProcess(argv, 0, stdout=b'amd64\n' if argv[0].endswith('dpkg') else b'dearmored', stderr=b'')

    def test_adds_scoped_source_and_key_before_refreshing_apt(self):
        repo.configure('brave')
        key = self.keys / 'minttweaks-brave.gpg'
        source = self.sources / 'minttweaks-brave.list'
        self.assertEqual(key.read_bytes(), b'binary key')
        self.assertIn(f'signed-by={key}', source.read_text())
        self.assertNotIn('trusted=yes', source.read_text())
        self.assertEqual(key.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.run.call_args.args[0][-1], 'update')

    def test_existing_repository_is_preserved_and_only_refreshed(self):
        existing = self.sources / 'user.sources'
        content = 'Types: deb\nURIs: ' + repo.RECIPES['helium'].origin + '\nSuites: stable\n'
        existing.write_text(content)
        repo.configure('helium')
        self.download.assert_not_called()
        self.assertEqual(existing.read_text(), content)
        self.assertEqual(list(self.keys.iterdir()), [])

    def test_failed_update_removes_only_newly_created_files(self):
        unrelated = self.sources / 'keep.list'
        unrelated.write_text('untouched')
        def fail_update(argv, **kwargs):
            if argv[0].endswith('apt-get'):
                raise RuntimeError('APT failed')
            return self.reply(argv, **kwargs)
        self.run.side_effect = fail_update
        with self.assertRaisesRegex(RuntimeError, 'APT failed'):
            repo.configure('brave')
        self.assertEqual(list(self.sources.iterdir()), [unrelated])
        self.assertEqual(list(self.keys.iterdir()), [])

    def test_invalid_key_never_writes_a_source(self):
        def fail_key(argv, **kwargs):
            if argv[0].endswith('gpg'):
                raise RuntimeError('Invalid key')
            return self.reply(argv, **kwargs)
        self.run.side_effect = fail_key
        with self.assertRaises(RuntimeError):
            repo.configure('helium')
        self.assertEqual(list(self.sources.iterdir()), [])
        self.assertEqual(list(self.keys.iterdir()), [])

    def test_existing_key_is_never_replaced(self):
        key = self.keys / 'minttweaks-brave.gpg'
        key.write_bytes(b'preserved')
        with self.assertRaises(ValueError):
            repo.configure('brave')
        self.assertEqual(key.read_bytes(), b'preserved')
        self.assertEqual(list(self.sources.iterdir()), [])

    def test_unknown_id_and_unready_zen_do_not_run_commands(self):
        for key in ('zen', '../brave', '--help'):
            with self.assertRaises(ValueError):
                repo.configure(key)
        self.run.assert_not_called()

    def test_backend_uses_scoped_privileged_helper_then_rechecks_candidate(self):
        runner = BrowserRunner()
        from minttweaks.core.runner import Result
        original = runner.stream
        def stream(command, **kwargs):
            if 'configure-browser-repository' in command.argv:
                runner.calls.append(command)
                return Result(str(command), 0)
            return original(command, **kwargs)
        with patch.object(runner, 'stream', side_effect=stream):
            status = backend.configure_repository(runner, 'brave')
        privileged = [call for call in runner.calls if call.needs_root]
        self.assertEqual(len(privileged), 1)
        self.assertEqual(privileged[0].argv[-2:], ('configure-browser-repository', 'brave'))
        self.assertTrue(status['brave'].installable)

    def test_backend_simulation_does_not_run_commands(self):
        runner = BrowserRunner()
        runner.dry_run = True
        with self.assertRaises(backend.SoftwareError):
            backend.configure_repository(runner, 'helium')
        self.assertFalse(runner.calls)
