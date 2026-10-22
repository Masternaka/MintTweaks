"""Validate the packaging without dpkg.

``dpkg-buildpackage`` only exists on Debian-family machines, so the packaging is
checked structurally here instead: every file debhelper expects, a parseable
control file, a changelog whose version matches the code, a desktop entry that
points at things the Makefile actually installs, and a man page that is part of
the install.
"""

import configparser
import email.utils
import os
import pathlib
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ElementTree

from minttweaks import __version__

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEBIAN = ROOT / "debian"
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")


def parse_deb822(text: str):
    """Minimal deb822 parser: returns a list of {field: value} stanzas."""
    stanzas = []
    current = {}
    key = None
    for raw in text.splitlines():
        if not raw.strip():
            if current:
                stanzas.append(current)
                current, key = {}, None
            continue
        if raw.startswith("#"):
            continue
        if raw[0] in " \t" and key:
            current[key] += "\n" + raw  # keep the indentation: deb822 continuation
            continue
        if ":" not in raw:
            raise AssertionError(f"not a deb822 line: {raw!r}")
        key, _, value = raw.partition(":")
        key = key.strip()
        current[key] = value.strip()
    if current:
        stanzas.append(current)
    return stanzas


def makefile_target(name: str) -> str:
    """The recipe of one Makefile target, as a single string."""
    pattern = re.compile(rf"^{re.escape(name)}:(?P<body>.*?)(?=^\S|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(MAKEFILE)
    assert match, f"no target {name} in the Makefile"
    return match.group("body")


class DebianFilesTests(unittest.TestCase):
    def test_expected_files_exist(self):
        for name in (
            "control",
            "rules",
            "changelog",
            "copyright",
            "minttweaks.docs",
            "source/format",
        ):
            self.assertTrue((DEBIAN / name).is_file(), f"debian/{name} is missing")

    def test_rules_is_executable_and_uses_tabs(self):
        path = DEBIAN / "rules"
        self.assertTrue(path.stat().st_mode & 0o111, "debian/rules must be executable")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "#!/usr/bin/make -f")
        for line in lines:
            if line.startswith("    "):
                self.fail(f"debian/rules recipe indented with spaces instead of a tab: {line!r}")
        body = path.read_text(encoding="utf-8")
        self.assertIn("override_dh_auto_install:", body)
        self.assertIn("debian/minttweaks", body)

    def test_control_declares_the_runtime_dependencies(self):
        stanzas = parse_deb822((DEBIAN / "control").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(stanzas), 2)
        source, binary = stanzas[0], stanzas[1]

        for field in ("Source", "Maintainer", "Build-Depends", "Standards-Version"):
            self.assertIn(field, source)
        self.assertIn("debhelper-compat", source["Build-Depends"])
        self.assertEqual(binary["Package"], "minttweaks")
        self.assertEqual(binary["Architecture"], "all")

        depends = binary["Depends"].replace("\n", " ")
        for package in ("python3-gi", "gir1.2-gtk-3.0", "policykit-1", "${misc:Depends}"):
            self.assertIn(package, depends)
        self.assertIn("${python3:Depends}", depends)

        description = binary["Description"].splitlines()
        self.assertTrue(description[0].strip(), "the synopsis line cannot be empty")
        for line in description[1:]:
            self.assertTrue(line.startswith(" "), f"description line not indented: {line!r}")

    def test_changelog_matches_the_code_version(self):
        lines = (DEBIAN / "changelog").read_text(encoding="utf-8").splitlines()
        header = re.match(
            r"^(?P<name>[a-z0-9][a-z0-9+.-]*) \((?P<version>[^)]+)\) (?P<dist>[a-z-]+); urgency=(?P<urgency>\w+)$",
            lines[0],
        )
        self.assertIsNotNone(header, f"malformed changelog header: {lines[0]!r}")
        self.assertEqual(header.group("name"), "minttweaks")
        self.assertEqual(header.group("version"), __version__)

        trailer = [line for line in lines if line.strip()][-1]
        match = re.match(r"^ -- (?P<who>.+) <(?P<email>[^>]+)>  (?P<date>.+)$", trailer)
        self.assertIsNotNone(match, f"malformed changelog trailer: {trailer!r}")
        self.assertIsNotNone(email.utils.parsedate_to_datetime(match.group("date")))

    def test_docs_file_lists_existing_files(self):
        for name in (DEBIAN / "minttweaks.docs").read_text(encoding="utf-8").split():
            self.assertTrue((ROOT / name).is_file(), f"{name} is listed in .docs but does not exist")

    def test_copyright_follows_dep5(self):
        text = (DEBIAN / "copyright").read_text(encoding="utf-8")
        for field in ("Format:", "Upstream-Name:", "Files:", "Copyright:", "License:"):
            self.assertIn(field, text)
        self.assertIn("GPL-3+", text)

    def test_source_format_is_native(self):
        self.assertEqual((DEBIAN / "source" / "format").read_text(encoding="utf-8").strip(), "3.0 (native)")


class DesktopEntryTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "data" / "minttweaks.desktop"
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str  # type: ignore[assignment]
        parser.read_string(self.path.read_text(encoding="utf-8"))
        self.entry = parser["Desktop Entry"]

    def test_required_keys(self):
        for key in ("Type", "Name", "Comment", "Exec", "Icon", "Categories"):
            self.assertIn(key, self.entry)
        self.assertEqual(self.entry["Type"], "Application")
        self.assertEqual(self.entry["Terminal"], "false")

    def test_exec_points_at_the_installed_launcher(self):
        executable = self.entry["Exec"].split()[0]
        self.assertEqual(executable, "minttweaks")
        self.assertIn("$(BINDIR)/minttweaks", makefile_target("install"))
        self.assertTrue((ROOT / "bin" / executable).is_file())

    def test_icon_exists_with_the_declared_name(self):
        self.assertEqual(self.entry["Icon"], "minttweaks")
        icon = ROOT / "data" / f"{self.entry['Icon']}.svg"
        self.assertTrue(icon.is_file())
        self.assertIn("$(ICONDIR)/minttweaks.svg", makefile_target("install"))
        ElementTree.parse(icon)  # well-formed XML or it raises

    def test_categories_are_valid(self):
        for category in self.entry["Categories"].strip(";").split(";"):
            self.assertRegex(category, r"^[A-Za-z0-9-]+$")


class MakefileTests(unittest.TestCase):
    def test_install_installs_every_shipped_asset(self):
        recipe = makefile_target("install")
        for asset in (
            "bin/minttweaks",
            "data/mtk-root",
            "data/mtk-firefox",
            "data/minttweaks.desktop",
            "data/minttweaks.svg",
            "data/minttweaks.1",
        ):
            self.assertIn(asset, recipe, f"{asset} is never installed")
        self.assertIn("cp -r $(PKG)", recipe)

    def test_uninstall_removes_what_install_adds(self):
        install = makefile_target("install")
        uninstall = makefile_target("uninstall")
        for destination in ("$(BINDIR)/minttweaks", "$(APPDIR)/minttweaks.desktop",
                            "$(ICONDIR)/minttweaks.svg", "$(MANDIR)/minttweaks.1",
                            "$(LIBDIR)/$(PKG)"):
            self.assertIn(destination, install, f"{destination} is not installed")
            self.assertIn(destination, uninstall, f"{destination} is not removed")

    def test_install_builds_the_catalogues_first(self):
        self.assertRegex(MAKEFILE, r"(?m)^install: translations$")

    def test_helper_keeps_its_executable_mode(self):
        recipe = makefile_target("install")
        for helper in ("data/mtk-root", "data/mtk-firefox"):
            self.assertIn(f"-m 0755 {helper}", recipe)


class ManPageTests(unittest.TestCase):
    def test_man_page_header_matches_the_version(self):
        text = (ROOT / "data" / "minttweaks.1").read_text(encoding="utf-8")
        first = text.splitlines()[0]
        self.assertTrue(first.startswith('.TH MINTTWEAKS 1 '), first)
        self.assertIn(f"minttweaks {__version__}", first)
        self.assertIn(".SH OPTIONS", text)
        self.assertIn(".SH FICHIERS", text)

    def test_man_page_documents_the_documented_flags(self):
        from minttweaks import app

        man = (ROOT / "data" / "minttweaks.1").read_text(encoding="utf-8")
        for flag in ("\\-\\-help", "\\-\\-version", "\\-\\-lang", "\\-\\-dry-run"):
            self.assertIn(flag, man)
        for variable in ("MTK_LOCALEDIR", "MTK_ROOT_CMD", "MTK_DRY_RUN"):
            self.assertIn(variable, man)
            self.assertIn(variable, app.USAGE)


class PrivilegedHelperTests(unittest.TestCase):
    def test_helpers_are_shipped_executable_and_start_with_python(self):
        for name in ("mtk-root", "mtk-firefox"):
            helper = ROOT / "data" / name
            self.assertTrue(helper.stat().st_mode & 0o111, f"{name} is not executable")
            self.assertEqual(
                helper.read_text(encoding="utf-8").splitlines()[0],
                "#!/usr/bin/python3",
                f"{name} does not use the expected interpreter",
            )

    def test_helpers_document_the_commands_the_backends_call(self):
        for helper_name, command, backend_name in (
            ("mtk-root", "install-smbconf", "samba"),
            ("mtk-firefox", "install-policy", "firefox"),
        ):
            helper = (ROOT / "data" / helper_name).read_text(encoding="utf-8")
            backend = (
                ROOT / "minttweaks" / "modules" / backend_name / "backend.py"
            ).read_text(encoding="utf-8")
            self.assertIn(command, helper)
            self.assertIn(command, backend)


class LauncherTests(unittest.TestCase):
    """bin/minttweaks must fail with advice, not with a traceback."""

    def _run(self, *arguments):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        return subprocess.run(
            [sys.executable, str(ROOT / "bin" / "minttweaks"), *arguments],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=environment,
        )

    @staticmethod
    def gtk_available() -> bool:
        """Ask a fresh interpreter: the test process may hold a gi stub."""
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk",
            ],
            capture_output=True,
        )
        return probe.returncode == 0

    def test_launcher_behaves_according_to_the_gtk_presence(self):
        gtk_available = self.gtk_available()
        result = self._run("--version")
        self.assertNotIn("Traceback", result.stderr)
        if gtk_available:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("MintTweaks", result.stdout)
        else:
            self.assertEqual(result.returncode, 1)
            self.assertIn("python3-gi", result.stderr)

    def test_launcher_is_executable(self):
        self.assertTrue((ROOT / "bin" / "minttweaks").stat().st_mode & 0o111)

    def test_launcher_explains_missing_gtk_namespace_when_gi_is_installed(self):
        # Reproduce a minimal Ubuntu installation: PyGObject is available,
        # but the Gtk typelib is not. Use a fresh process, independent of GTK
        # and of the UI stubs imported by the rest of the test suite.
        script = """
import runpy
import sys
import types

gi = types.ModuleType('gi')
def require_version(namespace, version):
    assert (namespace, version) == ('Gtk', '3.0')
    raise ValueError('Namespace Gtk not available')
gi.require_version = require_version
sys.modules['gi'] = gi
runpy.run_path(sys.argv[1], run_name='__main__')
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT / "bin" / "minttweaks")],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("sudo apt install python3-gi gir1.2-gtk-3.0", result.stderr)


if __name__ == "__main__":
    unittest.main()
