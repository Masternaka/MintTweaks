"""Read-only python-apt probe, run by the distribution Python in isolated mode.

This file deliberately imports no MintTweaks modules or GTK, so the system
interpreter can read its native apt bindings even when the UI uses a venv.
It never updates the cache, marks packages, commits or changes APT configuration.
"""
import json
from pathlib import Path
import re
import shlex
import sys

PACKAGE = re.compile(r'^[a-z0-9][a-z0-9+.-]+(?::[a-z0-9][a-z0-9-]*)?$')
VERSION = re.compile(r'^[0-9][0-9A-Za-z.+:~\-]*$')


class MissingPackage(ValueError):
    pass


def distro_origins(text):
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            parsed = shlex.split(value)
            fields[key] = parsed[0] if len(parsed) == 1 else ''
    if fields.get('ID') != 'linuxmint':
        raise ValueError('Official application installation requires Linux Mint or LMDE.')
    if fields.get('UBUNTU_CODENAME') or 'ubuntu' in fields.get('ID_LIKE', '').split():
        return {'linuxmint', 'ubuntu'}
    if 'debian' in fields.get('ID_LIKE', '').split():
        return {'linuxmint', 'debian'}
    raise ValueError('The Linux Mint distribution base could not be determined.')


def inspect(cache, request, allowed):
    name, sep, version = request.partition('=')
    if not PACKAGE.fullmatch(name) or (sep and not VERSION.fullmatch(version)):
        raise ValueError('Invalid APT package request.')
    package = cache[name]
    selected = next((item for item in package.versions if item.version == version), None) if sep else package.candidate
    if selected is None:
        raise MissingPackage('No requested version is available in the configured package cache.')
    # The local dpkg status entry is not a downloadable source. Keep every
    # repository origin so that a mixed official/third-party version is refused.
    origins = [origin for origin in selected.origins if origin.archive != 'now']
    if not origins or any(not origin.trusted or origin.origin.casefold() not in allowed or not origin.site for origin in origins):
        raise ValueError('This version is not exclusively available from trusted official distribution repositories.')
    return {'version': selected.version, 'architecture': selected.architecture,
            'origins': sorted({origin.origin + ' | ' + origin.site + ' | ' + origin.archive + ' | ' + origin.component for origin in origins})}


def main(arguments):
    try:
        import apt
        allowed = distro_origins(Path('/etc/os-release').read_text())
        cache = apt.Cache()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        return 2
    results = {}
    for request in arguments:
        try:
            results[request] = inspect(cache, request, allowed)
        except (KeyError, MissingPackage) as exc:
            results[request] = {'error': str(exc), 'reason': 'missing'}
        except Exception as exc:
            results[request] = {'error': str(exc), 'reason': 'source'}
    print(json.dumps(results))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
