"""Fixed APT repository recipes, shared by the UI and privileged helper.

Only catalog IDs are accepted; callers cannot supply paths, URLs or source text.
"""

import os
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Repository:
    origin: str
    key_url: str
    architectures: tuple
    suite: str = 'stable'
    components: str = 'main'

    def source(self, key_path):
        return f"deb [arch={','.join(self.architectures)} signed-by={key_path}] {self.origin} {self.suite} {self.components}\n"


RECIPES = {
    'helium': Repository('https://pkg.helium.computer/deb/',
                         'https://raw.githubusercontent.com/imputnet/helium-linux/main/pubkey.asc', ('amd64', 'arm64')),
    'brave': Repository('https://brave-browser-apt-release.s3.brave.com/',
                        'https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg', ('amd64', 'arm64')),
}
MAX_KEY_BYTES = 1024 * 1024
SOURCES_DIR = Path('/etc/apt/sources.list.d')
KEYRINGS_DIR = Path('/usr/share/keyrings')
MAIN_SOURCE = Path('/etc/apt/sources.list')


class HTTPSOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Refusing a non-HTTPS key redirect.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_key(url):
    opener = urllib.request.build_opener(HTTPSOnly())
    with opener.open(url, timeout=30) as response:
        data = response.read(MAX_KEY_BYTES + 1)
    if not data or len(data) > MAX_KEY_BYTES:
        raise ValueError('Invalid signing key size.')
    return data


def run(argv, **kwargs):
    result = subprocess.run(argv, check=False, timeout=300,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C', 'LANG': 'C'}, **kwargs)
    if result.returncode:
        raise RuntimeError((getattr(result, 'stderr', None) or b'').decode(errors='replace') or f'{argv[0]} failed ({result.returncode}).')
    return result


def atomic_write(path, data):
    if path.is_symlink() or path.exists():
        raise ValueError(f'Refusing to replace existing file: {path}')
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.minttweaks-', delete=False) as output:
            staged = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(staged, 0o644)
        # Do not replace a file created by another package manager meanwhile.
        os.link(staged, path)
    finally:
        if staged is not None:
            staged.unlink()


def configure(app_id):
    """Run as root, download a public key, add its scoped source and update APT."""
    if app_id not in RECIPES:
        raise ValueError('Unknown or unsupported repository.')
    recipe = RECIPES[app_id]
    arch = run(['/usr/bin/dpkg', '--print-architecture'], capture_output=True).stdout.decode().strip()
    if arch not in recipe.architectures:
        raise ValueError(f'Unsupported repository architecture: {arch}')
    key_path = KEYRINGS_DIR / f'minttweaks-{app_id}.gpg'
    source_path = SOURCES_DIR / f'minttweaks-{app_id}.list'
    source = recipe.source(key_path).encode()
    # Existing user/package configuration belongs to its owner. Only refresh it.
    sources = [MAIN_SOURCE]
    sources += list(source_path.parent.glob('*.list')) + list(source_path.parent.glob('*.sources'))
    existing = any(path.is_file() and any(recipe.origin.rstrip('/') in line and not line.lstrip().startswith('#')
                   for line in path.read_text().splitlines()) for path in sources)
    created = []
    try:
        if not existing:
            data = download_key(recipe.key_url)
            with tempfile.TemporaryDirectory(prefix='mtk-key-') as directory:
                home = Path(directory)
                candidate = home / 'download'
                candidate.write_bytes(data)
                run(['/usr/bin/gpg', '--homedir', directory, '--batch', '--show-keys', str(candidate)], capture_output=True)
                if data.startswith(b'-----BEGIN PGP PUBLIC KEY BLOCK-----'):
                    data = run(['/usr/bin/gpg', '--homedir', directory, '--batch', '--output', '-', '--dearmor', str(candidate)], capture_output=True).stdout
                if not data:
                    raise ValueError('The signing key is empty.')
            key_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(key_path, data)
            created.append(key_path)
            atomic_write(source_path, source)
            created.append(source_path)
        run(['/usr/bin/apt-get', '-o', 'APT::Update::Error-Mode=any', 'update'])
    except Exception:
        for path in reversed(created):
            path.unlink()
        raise
