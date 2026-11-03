"""Private operation metadata, separate from command transcripts and backups."""

from __future__ import annotations

import contextlib
import contextvars
import datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid

from . import paths

# Worker-local: a backup belongs to the operation which actually created it.
backup_recorder = contextvars.ContextVar('minttweaks_backup_recorder', default=None)
STATUSES = ('running', 'completed', 'failed', 'simulation', 'unknown', 'interface_error')


def record_backup(path):
    """Associate a created backup by path only; never read its contents."""
    recorder = backup_recorder.get()
    if recorder is not None and path is not None:
        recorder(Path(path))


def result_failed(value):
    """Recognize backend failures even when a worker returns without raising."""
    if isinstance(value, (list, tuple)):
        return any(result_failed(item) for item in value)
    if isinstance(value, bool):
        return not value
    return getattr(value, 'ok', None) is False


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class HistoryStore:
    def __init__(self, directory=None, *, session=None):
        self.directory = Path(directory if directory is not None else paths.HISTORY_DIR).absolute()
        self.database = self.directory / 'operations.sqlite3'
        self.session = session or uuid.uuid4().hex

    def _check_paths(self, create):
        for parent in (self.directory, *self.directory.parents):
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise OSError('Unsafe history directory')
        if create:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.directory.exists():
            return False
        if not create and not os.path.lexists(self.database):
            return False
        info = self.directory.stat()
        if info.st_uid != os.getuid():
            raise OSError('History directory belongs to another user')
        if create:
            self.directory.chmod(0o700)
        elif stat.S_IMODE(info.st_mode) & 0o077:
            raise OSError('History directory is not private')
        if create:
            try:
                fd = os.open(self.database, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        try:
            info = self.database.lstat()
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise OSError('Invalid history file')
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise OSError('History file is not private')
        return True

    @contextlib.contextmanager
    def _connect(self, create=False):
        if not self._check_paths(create):
            yield None
            return
        # Read-only views cannot create or change a database.
        uri = self.database.as_uri() + ('?mode=rw' if create else '?mode=ro')
        connection = sqlite3.connect(uri, uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        try:
            if create:
                connection.execute('BEGIN IMMEDIATE')
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version == 0 and create:
                if connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                    raise ValueError('Unrecognized history database')
                connection.execute('''CREATE TABLE operations (
                        id TEXT PRIMARY KEY, session TEXT NOT NULL, module TEXT NOT NULL,
                        name TEXT NOT NULL, started TEXT NOT NULL, finished TEXT,
                        status TEXT NOT NULL, simulated INTEGER NOT NULL,
                        backups TEXT NOT NULL DEFAULT '[]')''')
                connection.execute('PRAGMA user_version = 1')
            elif version != 1:
                raise ValueError('Unsupported history version')
            yield connection
            if create:
                connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin(self, name, module, simulated=False):
        if not isinstance(name, str) or not 0 < len(name) <= 512:
            raise ValueError('Invalid operation name')
        if not isinstance(module, str) or not 0 < len(module) <= 64:
            raise ValueError('Invalid module')
        identifier = uuid.uuid4().hex
        with self._connect(create=True) as connection:
            connection.execute('INSERT INTO operations (id, session, module, name, started, status, simulated) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (identifier, self.session, module, name, now(), 'running', int(simulated)))
        return identifier

    def finish(self, identifier, status):
        if status not in ('completed', 'failed', 'simulation', 'interface_error'):
            raise ValueError('Invalid final status')
        with self._connect(create=True) as connection:
            connection.execute('UPDATE operations SET finished = ?, status = ? WHERE id = ? AND session = ?',
                               (now(), status, identifier, self.session))

    def add_backup(self, identifier, path):
        path = str(path)
        if not Path(path).is_absolute() or len(path) > 4096 or any(ord(c) < 32 for c in path):
            raise ValueError('Invalid backup path')
        with self._connect(create=True) as connection:
            row = connection.execute('SELECT backups FROM operations WHERE id = ? AND session = ?',
                                     (identifier, self.session)).fetchone()
            if row is None:
                return
            backups = json.loads(row[0])
            if path not in backups:
                if len(backups) >= 100:
                    raise ValueError('Too many backup references')
                backups.append(path)
                connection.execute('UPDATE operations SET backups = ? WHERE id = ?', (json.dumps(backups), identifier))

    def entries(self, *, status=None, limit=50, offset=0):
        if status is not None and status not in STATUSES:
            raise ValueError('Invalid history filter')
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValueError('Invalid history page')
        with self._connect() as connection:
            if connection is None:
                return []
            rows = connection.execute('''SELECT * FROM (
                SELECT id, module, name, started, finished, simulated, backups,
                CASE WHEN status = 'running' AND session != ? THEN 'unknown' ELSE status END AS status
                FROM operations) WHERE (? IS NULL OR status = ?)
                ORDER BY started DESC, id DESC LIMIT ? OFFSET ?''', (self.session, status, status, limit, offset)).fetchall()
        result = []
        for row in rows:
            entry = dict(row)
            backups = json.loads(entry['backups'])
            if not isinstance(backups, list) or any(not isinstance(path, str) for path in backups):
                raise ValueError('Invalid backup references')
            entry['backups'] = tuple(backups)
            result.append(entry)
        return result
