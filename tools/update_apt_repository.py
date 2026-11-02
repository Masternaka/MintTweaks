#!/usr/bin/env python3
"""Notify the fixed APT repository after a stable release; confirm public bytes.

The cross-repository token is sent only to GitHub's workflow-dispatch endpoint.
No token, repository signing secret or arbitrary URL is accepted on the CLI.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE = "Masternaka/MintTweaks"
DESTINATION = "Masternaka/masternaka-repository"
PUBLIC_URL = "https://masternaka.github.io/masternaka-repository/"
WORKFLOW_URL = f"https://github.com/{DESTINATION}/actions/workflows/repository.yml"
DISPATCH_URL = f"https://api.github.com/repos/{DESTINATION}/actions/workflows/repository.yml/dispatches"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


class PublicationError(ValueError):
    pass


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # In particular, never forward the dispatch token to a redirected host.
        raise PublicationError("Unexpected HTTP redirect; no credentials were forwarded.")


def request(url, *, payload=None, token=None):
    if token is not None and (url != DISPATCH_URL or payload != {"ref": "main"}):
        raise PublicationError("The dispatch token is restricted to the fixed workflow endpoint.")
    headers = {"User-Agent": "MintTweaks-APT-publication", "Accept": "application/vnd.github+json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.build_opener(NoRedirects()).open(req, timeout=30) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise PublicationError("The HTTP response exceeds the size limit.")
    return content


def stable_asset(release, tag, version):
    if (not isinstance(release, dict) or release.get("tag_name") != tag
            or release.get("draft") is not False or release.get("prerelease") is not False):
        raise PublicationError("A published stable Release is required before notifying APT.")
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise PublicationError("The Release assets could not be read.")
    candidates = [asset for asset in assets if isinstance(asset, dict)
                  and re.fullmatch(r"minttweaks_[^/\\\s]+_all\.deb", str(asset.get("name", "")))]
    name = f"minttweaks_{version}_all.deb"
    if len(candidates) != 1 or candidates[0].get("name") != name:
        raise PublicationError("The stable Release must contain exactly the expected MintTweaks .deb.")
    asset = candidates[0]
    if asset.get("state") != "uploaded" or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", str(asset.get("digest", ""))):
        raise PublicationError("The uploaded .deb and its GitHub SHA-256 digest are required.")
    return name, asset["digest"].lower()


def manifest_matches(manifest, tag, version, name, digest):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("apps"), list):
        return False
    matches = [app for app in manifest["apps"] if isinstance(app, dict) and app.get("package") == "minttweaks"]
    if len(matches) != 1:
        return False
    app = matches[0]
    return (app.get("repository") == SOURCE and app.get("tag") == tag and app.get("version") == version
            and app.get("architecture") == "all" and app.get("recipe") == "deb"
            and app.get("asset") == name and app.get("digest") == digest
            and app.get("deb") == {"filename": name, "version": version, "digest": digest})


def publish(tag, version, token, *, fetch=request, clock=time.monotonic, sleep=time.sleep,
            timeout=600, interval=15):
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or tag != "v" + version:
        raise PublicationError("Only a matching vX.Y.Z stable tag and X.Y.Z version are accepted.")
    if not token or "\n" in token or "\r" in token:
        raise PublicationError("Configure the APT_REPOSITORY_DISPATCH_TOKEN secret in Masternaka/MintTweaks.")
    release_url = f"https://api.github.com/repos/{SOURCE}/releases/tags/{tag}"
    name, digest = stable_asset(json.loads(fetch(release_url)), tag, version)
    fetch(DISPATCH_URL, payload={"ref": "main"}, token=token)
    print(f"APT publication requested for {tag}. Waiting for verified public bytes: {WORKFLOW_URL}", flush=True)
    deadline = clock() + timeout
    attempt = 0
    while clock() < deadline:
        attempt += 1
        # Avoid a cached previous manifest or package from an earlier snapshot.
        query = urllib.parse.urlencode({"minttweaks_release": tag, "attempt": attempt})
        try:
            manifest = json.loads(fetch(PUBLIC_URL + "manifest.json?" + query))
            if manifest_matches(manifest, tag, version, name, digest):
                package = fetch(PUBLIC_URL + "pool/" + urllib.parse.quote(name, safe="") + "?" + query)
                if "sha256:" + hashlib.sha256(package).hexdigest() == digest:
                    print(f"APT availability confirmed: {name} ({digest}).", flush=True)
                    return name, digest
        except urllib.error.HTTPError as exc:
            if exc.code not in (404, 408, 429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            # A transient Pages response is not proof of publication or failure.
            pass
        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(interval, remaining))
    raise PublicationError(f"APT availability was not confirmed within {timeout}s. The GitHub Release remains published. Inspect {WORKFLOW_URL}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        name, digest = publish(args.tag, args.version, os.environ.get("APT_REPOSITORY_DISPATCH_TOKEN", ""))
    except urllib.error.HTTPError as exc:
        # Do not print request headers, the token, or untrusted response bodies.
        print(f"APT publication request failed (HTTP {exc.code}). The GitHub Release was not changed. Check {WORKFLOW_URL}", file=sys.stderr)
        return 1
    except (PublicationError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"### APT availability confirmed\n\n`{name}`\n\n`{digest}`\n\n[APT workflows]({WORKFLOW_URL})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
