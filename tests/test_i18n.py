"""Tests for the translation layer and its tooling.

The interesting failure modes here are not typos: they are a catalogue that is
out of sync with the source, and the classic gettext trap where a module binds
``gettext.gettext`` at import time and never sees the catalogue loaded later.
Both are covered below.
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from minttweaks import i18n

ROOT = pathlib.Path(__file__).resolve().parent.parent
PO = ROOT / "po" / "fr.po"
POT = ROOT / "po" / "minttweaks.pot"
COMPILE = ROOT / "tools" / "compile_mo.py"
EXTRACT = ROOT / "tools" / "extract_strings.py"


def run_tool(script: pathlib.Path, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self._restore)

        target = pathlib.Path(self.directory.name) / "fr" / "LC_MESSAGES" / "minttweaks.mo"
        result = run_tool(COMPILE, str(PO), str(target))
        self.assertEqual(result.returncode, 0, result.stderr)

        self._previous = os.environ.get("MTK_LOCALEDIR")
        os.environ["MTK_LOCALEDIR"] = self.directory.name

    def _restore(self):
        if self._previous is None:
            os.environ.pop("MTK_LOCALEDIR", None)
        else:
            os.environ["MTK_LOCALEDIR"] = self._previous
        i18n.reset()

    def test_french_catalogue_loads(self):
        self.assertEqual(i18n.install(["fr"]), "fr")
        self.assertEqual(i18n._("Shares"), "Partages")
        self.assertEqual(i18n._("Overview"), "Vue d'ensemble")

    def test_placeholders_survive_translation(self):
        i18n.install(["fr"])
        self.assertEqual(i18n._("Remove {count} package(s)").format(count=3), "Supprimer 3 paquet(s)")
        self.assertEqual(
            i18n._("Share '{name}' deleted.").format(name="Docs"), "Partage « Docs » supprimé."
        )

    def test_unknown_string_is_returned_unchanged(self):
        i18n.install(["fr"])
        self.assertEqual(i18n._("this string is not translated"), "this string is not translated")

    def test_missing_language_falls_back_to_source_strings(self):
        self.assertEqual(i18n.install(["tlh"]), "C")
        self.assertEqual(i18n._("Shares"), "Shares")

    def test_reset_returns_to_source_strings(self):
        i18n.install(["fr"])
        i18n.reset()
        self.assertEqual(i18n._("Shares"), "Shares")


class LateBindingTests(unittest.TestCase):
    """The `from ...i18n import _` pattern must not freeze the language."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(i18n.reset)
        self.addCleanup(lambda: os.environ.pop("MTK_LOCALEDIR", None))

        target = pathlib.Path(self.directory.name) / "fr" / "LC_MESSAGES" / "minttweaks.mo"
        run_tool(COMPILE, str(PO), str(target))
        os.environ["MTK_LOCALEDIR"] = self.directory.name

    def test_a_module_imported_before_install_still_translates(self):
        from minttweaks.modules.maintenance import backend as maintenance

        english_title = maintenance.TASKS[0].title
        i18n.install(["fr"])
        french_title = maintenance.TASKS[0].title

        self.assertNotEqual(english_title, french_title)
        self.assertIn("orphelins", french_title)

    def test_task_details_are_translated_lazily(self):
        from minttweaks.modules.maintenance import backend as maintenance

        i18n.install(["fr"])
        detail = maintenance.TASKS[0].detail
        self.assertTrue(detail)
        self.assertNotEqual(detail, maintenance.TASKS[0].detail_msgid)


class CatalogueHygieneTests(unittest.TestCase):
    def test_translation_template_is_up_to_date(self):
        result = run_tool(EXTRACT, "--check")
        self.assertEqual(
            result.returncode,
            0,
            "po/minttweaks.pot is stale, run ./tools/extract_strings.py:\n" + result.stdout + result.stderr,
        )

    def test_every_string_is_translated(self):
        result = run_tool(COMPILE, "--check", str(PO))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_fstring_is_handed_to_gettext(self):
        """f-strings cannot be extracted, so the extractor refuses them."""
        result = run_tool(EXTRACT, "--check")
        self.assertNotIn("f-string", result.stderr + result.stdout)

    def test_template_and_po_cover_the_same_strings(self):
        template = set()
        for line in POT.read_text(encoding="utf-8").splitlines():
            if line.startswith('msgid "') and line != 'msgid ""':
                template.add(line[len('msgid "'):-1])
        translated = set()
        for line in PO.read_text(encoding="utf-8").splitlines():
            if line.startswith('msgid "') and line != 'msgid ""':
                translated.add(line[len('msgid "'):-1])

        self.assertEqual(template - translated, set(), "strings missing from po/fr.po")
        self.assertEqual(translated - template, set(), "obsolete entries in po/fr.po")


class LocaleDirectoryTests(unittest.TestCase):
    def test_override_comes_first(self):
        previous = os.environ.get("MTK_LOCALEDIR")
        os.environ["MTK_LOCALEDIR"] = "/tmp/somewhere"
        try:
            self.assertEqual(str(next(i18n.locale_dirs())), "/tmp/somewhere")
        finally:
            if previous is None:
                os.environ.pop("MTK_LOCALEDIR", None)
            else:
                os.environ["MTK_LOCALEDIR"] = previous

    def test_system_locale_is_the_last_resort(self):
        self.assertIn(pathlib.Path("/usr/share/locale"), list(i18n.locale_dirs()))


if __name__ == "__main__":
    unittest.main()
