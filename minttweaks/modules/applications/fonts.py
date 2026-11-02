"""GitHub fallback for the six requested font families, installed per-user.

Only known upstreams are queried. No installer or build script is executed.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from ...core import paths
from ...core.runner import cmd
from ...i18n import _

MIB = 1024 * 1024
MAX_ARCHIVE = 256 * MIB
MAX_FILE = 64 * MIB
MAX_TOTAL = 2048 * MIB
MAX_FILES = 6000
MAX_JSON = 16 * MIB
FONT_SUFFIXES = {'.ttf', '.otf', '.ttc'}
RECIPES = {
    'fonts-cascadia-code': ('microsoft/cascadia-code', r'CascadiaCode-.*\.zip'),
    'fonts-firacode': ('tonsky/FiraCode', r'Fira_Code.*\.zip'),
    'fonts-hack': ('source-foundry/Hack', r'Hack-.*-ttf\.zip'),
    'fonts-jetbrains-mono': ('JetBrains/JetBrainsMono', r'JetBrainsMono-.*\.zip'),
    'fonts-font-awesome': ('FortAwesome/Font-Awesome', r'fontawesome-free-.*-desktop\.zip'),
    'fonts-noto': ('notofonts/noto-fonts', None),
}
NOTO = (
    ('notofonts/noto-fonts', ('hinted/ttf/',), ()),
    ('notofonts/noto-cjk', ('Sans/OTC/', 'Serif/OTC/'), ('-Regular.ttc', '-Bold.ttc')),
    ('googlefonts/noto-emoji', ('fonts/NotoColorEmoji.ttf',), ()),
)
HOSTS = {'api.github.com', 'github.com', 'raw.githubusercontent.com',
         'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
         'github-releases.githubusercontent.com'}


def _url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError(_("The font download URL is not an approved GitHub URL."))
    return url


class _Redirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, _url(newurl))


def _open(url):
    request = Request(_url(url), headers={'User-Agent': 'MintTweaks', 'Accept': 'application/vnd.github+json' if url.startswith('https://api.github.com/') else 'application/octet-stream'})
    return build_opener(_Redirect()).open(request, timeout=60)


def _json(url):
    with _open(url) as response:
        raw = response.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError(_("GitHub font metadata exceeds the size limit."))
    return json.loads(raw)


def _download(url, destination, limit):
    with _open(url) as response, destination.open('xb') as output:
        total = 0
        while True:
            block = response.read(256 * 1024)
            if not block:
                break
            total += len(block)
            if total > limit:
                raise ValueError(_("The font download exceeds the size limit."))
            output.write(block)


def _safe(path):
    path = Path(os.path.abspath(path))
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(_("Unsafe font installation directory: {path}").format(path=parent))
    return path


def destination(package):
    if package not in RECIPES:
        raise ValueError(_("No GitHub font source is configured for this package."))
    # DATA_DIR includes the application name; fonts belong in the XDG fonts tree.
    return _safe(paths.DATA_DIR.parent / 'fonts' / 'minttweaks' / package)


def _relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in value or any(ord(c) < 32 for c in value):
        raise ValueError(_("Invalid path in the downloaded font files."))
    return path


@dataclass(frozen=True)
class Download:
    url: str
    size: int
    digest: str
    path: str
    archive: bool = False


@dataclass(frozen=True)
class FontPlan:
    package: str
    target: Path
    versions: tuple
    downloads: tuple

    @property
    def size(self):
        return sum(item.size for item in self.downloads)


def _tree(repo, prefixes, suffixes):
    commit = _json('https://api.github.com/repos/' + repo + '/commits/HEAD')['sha']
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError(_("The GitHub font revision could not be verified."))
    data = _json('https://api.github.com/repos/' + repo + '/git/trees/' + commit + '?recursive=1')
    if data.get('truncated'):
        raise ValueError(_("The GitHub font file list is incomplete."))
    downloads = []
    for item in data.get('tree', []):
        name = item['path']
        font = (any(name.startswith(prefix) for prefix in prefixes) and
                (not suffixes or name.endswith(suffixes)) and PurePosixPath(name).suffix.lower() in FONT_SUFFIXES)
        license_file = PurePosixPath(name).name.upper() in {'LICENSE', 'LICENSE.TXT', 'OFL.TXT', 'COPYING'}
        if item['type'] != 'blob' or not (font or license_file):
            continue
        _relative(name)
        if item.get('mode') != '100644' or not re.fullmatch('[0-9a-f]{40}', item['sha']) or not 0 < item['size'] <= MAX_FILE:
            raise ValueError(_("Unsupported file in the upstream font repository."))
        url = 'https://raw.githubusercontent.com/' + repo + '/' + commit + '/' + quote(name, safe='/')
        downloads.append(Download(url, item['size'], 'git-sha1:' + item['sha'], repo.replace('/', '-') + '/' + name))
    if not any(PurePosixPath(item.path).suffix.lower() in FONT_SUFFIXES for item in downloads):
        raise ValueError(_("No installable fonts were found in the GitHub source."))
    return repo + '@' + commit, tuple(downloads)


def preview(package):
    target = destination(package)
    if target.exists():
        raise ValueError(_("The managed font directory already exists. Its files were preserved."))
    repo, pattern = RECIPES[package]
    if pattern is None:
        groups = [_tree(*source) for source in NOTO]
        versions = tuple(group[0] for group in groups)
        downloads = tuple(item for group in groups for item in group[1])
    else:
        release = _json('https://api.github.com/repos/' + repo + '/releases/latest')
        if release.get('draft') or release.get('prerelease') or not release.get('tag_name'):
            raise ValueError(_("No stable GitHub font release is available."))
        assets = [asset for asset in release.get('assets', []) if re.fullmatch(pattern, asset['name'], re.IGNORECASE)]
        if len(assets) != 1:
            raise ValueError(_("A unique GitHub font archive could not be identified."))
        asset = assets[0]
        url = asset['browser_download_url']
        if not url.startswith('https://github.com/' + repo + '/releases/download/') or not 0 < asset['size'] <= MAX_ARCHIVE:
            raise ValueError(_("Unsupported GitHub font release asset."))
        _url(url)
        digest = asset.get('digest') or ''
        if digest and not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
            raise ValueError(_("The GitHub font digest is invalid."))
        versions = (repo + '@' + release['tag_name'],)
        downloads = (Download(url, asset['size'], digest, asset['name'], True),)
    if len(downloads) > MAX_FILES or sum(item.size for item in downloads) > MAX_TOTAL:
        raise ValueError(_("The selected font collection is too large."))
    return FontPlan(package, target, versions, downloads)


def _font_file(path):
    with path.open('rb') as source:
        return source.read(4) in (b'\x00\x01\x00\x00', b'OTTO', b'ttcf', b'true')


def _extract(archive, folder):
    with zipfile.ZipFile(archive) as bundle:
        if len(bundle.infolist()) > MAX_FILES:
            raise ValueError(_("The selected font collection is too large."))
        seen, total = set(), 0
        for item in bundle.infolist():
            relative = _relative(item.filename)
            if item.is_dir():
                continue
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(_("Symbolic links are not accepted in font archives."))
            font = relative.suffix.lower() in FONT_SUFFIXES
            license_file = relative.name.upper() in {'LICENSE', 'LICENSE.TXT', 'OFL.TXT', 'COPYING'}
            if not (font or license_file):
                continue
            total += item.file_size
            if item.file_size > MAX_FILE or total > MAX_TOTAL or str(relative) in seen:
                raise ValueError(_("The selected font collection is too large or contains duplicate paths."))
            seen.add(str(relative))
            output = folder.joinpath(*relative.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, output.open('xb') as target:
                shutil.copyfileobj(source, target)
            if output.stat().st_size != item.file_size or (font and not _font_file(output)):
                raise ValueError(_("The downloaded font file is invalid."))


def installed_version(package):
    target = destination(package)
    if not target.exists():
        return ''
    manifest = target / 'minttweaks-fonts.json'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > MAX_JSON:
        return ''
    data = json.loads(manifest.read_text())
    if data.get('package') != package or not data.get('files') or len(data['files']) > MAX_FILES:
        return ''
    for relative, digest in data['files'].items():
        path = target.joinpath(*_relative(relative).parts)
        _safe(path.parent)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return ''
    return ', '.join(data['versions'])


def install(runner, plan, on_line=None):
    if runner.dry_run:
        return _("Simulation: no GitHub fonts were downloaded or installed.")
    if preview(plan.package) != plan:
        raise ValueError(_("The GitHub font source changed. Review a new preview."))
    target = destination(plan.package)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mtk-font-', dir=target.parent) as tmp:
        work = Path(tmp)
        staged = work / 'installed'
        staged.mkdir()
        for number, download in enumerate(plan.downloads):
            if on_line:
                on_line(_("Downloading font file {current}/{total}.").format(current=number + 1, total=len(plan.downloads)))
            downloaded = work / ('download-' + str(number))
            _download(download.url, downloaded, min(MAX_ARCHIVE if download.archive else MAX_FILE, download.size))
            if downloaded.stat().st_size != download.size:
                raise ValueError(_("The font download size does not match the preview."))
            if download.digest:
                raw = downloaded.read_bytes()
                if download.digest.startswith('git-sha1:'):
                    digest = 'git-sha1:' + hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\x00' + raw).hexdigest()
                else:
                    digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
                if digest != download.digest:
                    raise ValueError(_("The downloaded font checksum does not match."))
            if download.archive:
                _extract(downloaded, staged)
            else:
                path = staged.joinpath(*_relative(download.path).parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                downloaded.rename(path)
                if path.suffix.lower() in FONT_SUFFIXES and not _font_file(path):
                    raise ValueError(_("The downloaded font file is invalid."))
        files = {}
        for path in sorted(staged.rglob('*')):
            if path.is_file():
                path.chmod(0o644)
                files[str(path.relative_to(staged))] = hashlib.sha256(path.read_bytes()).hexdigest()
        if not any(PurePosixPath(name).suffix.lower() in FONT_SUFFIXES for name in files):
            raise ValueError(_("No installable fonts were found in the GitHub source."))
        (staged / 'minttweaks-fonts.json').write_text(json.dumps({'package': plan.package, 'versions': plan.versions, 'files': files}, indent=2))
        _safe(target)
        if target.exists():
            raise ValueError(_("The managed font directory already exists. Its files were preserved."))
        staged.rename(target)
    result = runner.stream(cmd('fc-cache', '-f', str(target)), on_line=on_line)
    if not result.ok:
        raise ValueError(_("The font files were installed, but the Fontconfig cache could not be refreshed: {error}").format(error=result.output))
    if not installed_version(plan.package):
        raise ValueError(_("The installed GitHub font files could not be verified."))
    return _("GitHub fonts installed for your user account: {path}").format(path=target)
