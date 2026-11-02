"""Exercise release-to-APT propagation with no network or real credentials."""

import contextlib
import copy
import hashlib
import io
import json
import urllib.error
import unittest
from unittest.mock import Mock, patch

from tools import update_apt_repository as apt

TAG, VERSION = "v1.2.3", "1.2.3"
PACKAGE = b"fixture Debian package bytes"
NAME = "minttweaks_1.2.3_all.deb"
DIGEST = "sha256:" + hashlib.sha256(PACKAGE).hexdigest()
RELEASE = {"tag_name": TAG, "draft": False, "prerelease": False,
           "assets": [{"name": NAME, "state": "uploaded", "digest": DIGEST}]}
MANIFEST = {"apps": [{"repository": apt.SOURCE, "tag": TAG, "version": VERSION,
                      "architecture": "all", "recipe": "deb", "package": "minttweaks",
                      "asset": NAME, "digest": DIGEST,
                      "deb": {"filename": NAME, "version": VERSION, "digest": DIGEST}}]}


class PropagationTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.calls = []
        self.manifest = MANIFEST
        self.package = PACKAGE
        self.release = RELEASE

    def sleep(self, seconds):
        self.now += seconds

    def fetch(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url == apt.DISPATCH_URL:
            return b""
        if url.startswith("https://api.github.com/"):
            return json.dumps(self.release).encode()
        if "manifest.json?" in url:
            return json.dumps(self.manifest).encode()
        if "/pool/" in url:
            return self.package
        raise AssertionError("Unexpected URL: " + url)

    def publish(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return apt.publish(TAG, VERSION, "fake-token", fetch=self.fetch,
                               clock=lambda: self.now, sleep=self.sleep, timeout=30, interval=15, **kwargs)

    def test_success_requires_public_manifest_and_matching_downloaded_package(self):
        self.assertEqual(self.publish(), (NAME, DIGEST))
        authenticated = [(url, args) for url, args in self.calls if "token" in args]
        self.assertEqual(authenticated, [(apt.DISPATCH_URL, {"payload": {"ref": "main"}, "token": "fake-token"})])
        self.assertTrue(any("/pool/" in url for url, _ in self.calls))

    def test_old_manifest_is_waited_for_without_dispatching_again(self):
        original = self.fetch
        def fetch(url, **kwargs):
            if "manifest.json?" in url:
                self.manifest = {"apps": []} if self.now == 0 else MANIFEST
            return original(url, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            result = apt.publish(TAG, VERSION, "fake-token", fetch=fetch,
                                 clock=lambda: self.now, sleep=self.sleep, timeout=30, interval=15)
        self.assertEqual(result, (NAME, DIGEST))
        self.assertEqual(self.now, 15)
        self.assertEqual(sum(url == apt.DISPATCH_URL for url, _ in self.calls), 1)

    def test_a_matching_manifest_with_wrong_package_bytes_is_not_success(self):
        self.package = b"different bytes"
        with self.assertRaisesRegex(apt.PublicationError, "not confirmed"):
            self.publish()
        self.assertEqual(self.now, 30)

    def test_published_github_release_is_never_modified_after_timeout(self):
        self.manifest = {"apps": []}
        with self.assertRaises(apt.PublicationError):
            self.publish()
        writes = [(url, args["payload"]) for url, args in self.calls if "payload" in args]
        self.assertEqual(writes, [(apt.DISPATCH_URL, {"ref": "main"})])

    def test_previews_drafts_bad_assets_or_missing_digests_do_not_dispatch(self):
        changes = [{"prerelease": True}, {"draft": True}, {"tag_name": "v1.2.2"},
                   {"assets": []}, {"assets": RELEASE["assets"] * 2},
                   {"assets": [{"name": NAME, "state": "uploaded"}]},
                   {"assets": [{"name": NAME, "state": "uploading", "digest": DIGEST}]}]
        for change in changes:
            with self.subTest(change=change):
                self.release = {**RELEASE, **change}
                self.calls = []
                with self.assertRaises(apt.PublicationError):
                    self.publish()
                self.assertFalse(any(url == apt.DISPATCH_URL for url, _ in self.calls))

    def test_invalid_tag_version_or_missing_secret_does_not_use_network(self):
        fetch = Mock()
        for tag, version, token in [("v1.2.3-dev", VERSION, "token"), (TAG, "1.2.4", "token"),
                                    (TAG, VERSION, ""), (TAG, VERSION, "bad\ntoken")]:
            with self.assertRaises(apt.PublicationError):
                apt.publish(tag, version, token, fetch=fetch)
        fetch.assert_not_called()

    def test_transient_public_404_can_be_retried(self):
        original = self.fetch
        def fetch(url, **kwargs):
            if "manifest.json?" in url and self.now == 0:
                raise urllib.error.HTTPError(url, 404, "Not found", {}, None)
            return original(url, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            result = apt.publish(TAG, VERSION, "fake-token", fetch=fetch,
                                 clock=lambda: self.now, sleep=self.sleep, timeout=30, interval=15)
        self.assertEqual(result, (NAME, DIGEST))

    def test_wrong_public_source_version_or_digest_is_rejected(self):
        for field, value in [("repository", "other/repository"), ("digest", "sha256:" + "0" * 64),
                             ("version", "1.2.2"), ("architecture", "amd64"), ("tag", "v1.2.2")]:
            data = copy.deepcopy(MANIFEST)
            data["apps"][0][field] = value
            self.assertFalse(apt.manifest_matches(data, TAG, VERSION, NAME, DIGEST))


class CredentialBoundaryTests(unittest.TestCase):
    def test_token_cannot_be_attached_to_public_or_other_api_requests(self):
        with patch.object(apt.urllib.request, "build_opener") as opener:
            for url, payload in [(apt.PUBLIC_URL, None), (apt.DISPATCH_URL, {"ref": "other"}),
                                 ("https://api.github.com/other", {"ref": "main"})]:
                with self.assertRaises(apt.PublicationError):
                    apt.request(url, payload=payload, token="fake-token")
        opener.assert_not_called()

    def test_authenticated_redirects_are_refused(self):
        with self.assertRaisesRegex(apt.PublicationError, "redirect"):
            apt.NoRedirects().redirect_request(None, None, 302, "redirect", {}, "https://example.invalid/")

    def test_failed_http_request_does_not_log_token_or_body(self):
        error = urllib.error.HTTPError(apt.DISPATCH_URL, 403, "Forbidden", {}, io.BytesIO(b"private-body"))
        with patch.object(apt, "publish", side_effect=error), contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(apt.main(["--tag", TAG, "--version", VERSION]), 1)
        self.assertIn("HTTP 403", stderr.getvalue())
        self.assertNotIn("private-body", stderr.getvalue())
