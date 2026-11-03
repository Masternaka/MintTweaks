"""Installation information preserves provenance boundaries and actual packages."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from minttweaks.core import paths
from minttweaks.core.installation import version_rows
from minttweaks.modules.applications import backend as applications, details as app_details
from minttweaks.modules.applications.catalog import Application
from minttweaks.modules.software import backend as software, details as browser_details, zen
from tests.test_applications import APP, OTHER, ApplicationsRunner
from tests.test_software import BrowserRunner
from tests import fakegi

fakegi.install()
from minttweaks.modules.applications.page import ApplicationsPage
from minttweaks.modules.software.page import SoftwarePage
from minttweaks.ui.installations import InstallationDetails
from minttweaks.ui.widgets import AppContext


class VersionInformationTests(unittest.TestCase):
    def test_unknown_state_never_becomes_not_installed_or_up_to_date(self):
        initial = dict(version_rows(None))
        self.assertEqual(set(initial.values()), {'Not analysed yet.'})
        failed = dict(version_rows(software.Availability(error='read failed')))
        self.assertEqual(failed['Installed version or revision'], 'Not verified')
        self.assertEqual(failed['Installation candidate'], 'Unavailable')

    def test_installed_version_does_not_imply_no_updates_exist(self):
        rows = dict(version_rows(software.Availability(installed=True, installed_version='1.0')))
        self.assertEqual(rows['Installed version or revision'], '1.0')
        self.assertEqual(rows['Installation candidate'], 'Not checked for installed software.')


class OfficialApplicationDetailsTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(applications, 'CATALOG', (APP, OTHER))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner = ApplicationsRunner()

    def test_official_candidate_keeps_its_verified_origins(self):
        status = applications.collect_status(self.runner)['editor']
        rows = dict(app_details.installation_rows(APP, status))
        self.assertIn('Ubuntu | mirror.example', rows['Verified candidate sources'])
        self.assertEqual(rows['Installation candidate'], '1.2.3')
        self.assertEqual(rows['Scope'], 'System-wide')
        self.assertIn(APP.package, rows['Removal'])

    def test_installed_package_origin_is_not_inferred_from_catalog_or_candidate(self):
        self.runner.installed[APP.package] = '1.0'
        self.runner.bad_sources.add(APP.package)
        status = applications.collect_status(self.runner)['editor']
        self.assertEqual(status.origins, ())
        rows = dict(app_details.installation_rows(APP, status))
        self.assertIn('not been verified', rows['Origin check'])
        self.assertNotIn('Verified candidate sources', rows)
        self.assertEqual(rows['Installed version or revision'], '1.0')

    def test_source_error_does_not_display_stale_origins_as_verified(self):
        status = applications.ApplicationStatus(package=APP.package, candidate='1.2',
            origins=('Old source',), error='source failed')
        rows = dict(app_details.installation_rows(APP, status))
        self.assertNotIn('Verified candidate sources', rows)
        self.assertEqual(rows['Installation candidate'], 'Unavailable')

    def test_alternative_package_is_used_in_removal_guidance(self):
        app = Application('7zip', '7-Zip', '7zip', 'Utilities', alternatives=('p7zip-full',))
        status = applications.ApplicationStatus(package='p7zip-full', installed=True, installed_version='16.02')
        rows = dict(app_details.installation_rows(app, status))
        self.assertEqual(rows['Package'], 'p7zip-full')
        self.assertIn('p7zip-full', rows['Removal'])
        self.assertNotIn('Remove 7zip ', rows['Removal'])

    def test_details_use_collected_state_without_running_any_command(self):
        status = applications.collect_status(self.runner)['editor']
        calls = list(self.runner.calls)
        app_details.installation_rows(APP, status)
        self.assertEqual(self.runner.calls, calls)
        self.assertFalse(any(command.needs_root for command in calls))

    def test_application_page_refreshes_the_shared_details_without_installing(self):
        page = ApplicationsPage(AppContext(self.runner))
        status = applications.collect_status(self.runner)
        page.search.get_text = Mock(return_value='')
        with patch.object(page, 'run_operation') as operation:
            page._apply_status(status)
        rows = dict(page.details['editor'].rows)
        self.assertEqual(rows['Installation candidate'], '1.2.3')
        operation.assert_not_called()


class FontInstallationDetailsTests(unittest.TestCase):
    def setUp(self):
        self.app = Application('fonts-firacode', 'Fira Code', 'fonts-firacode', 'Fonts')

    def test_github_copy_has_its_own_scope_revision_and_lifecycle(self):
        status = applications.ApplicationStatus(package=self.app.package, installed=True,
            github_installed=True, installed_version='tonsky/FiraCode@6.2')
        with patch.object(paths, 'DATA_DIR', Path('/home/example/.local/share/minttweaks')):
            rows = dict(app_details.installation_rows(self.app, status))
        self.assertEqual(rows['Scope'], 'Current user')
        self.assertEqual(rows['Installed version or revision'], 'tonsky/FiraCode@6.2')
        self.assertIn('https://github.com/tonsky/FiraCode', rows['Expected source'])
        self.assertEqual(rows['Managed font directory'], '/home/example/.local/share/fonts/minttweaks/fonts-firacode')
        self.assertIn('not updated by APT', rows['Updates'])
        self.assertNotIn('package manager', rows['Removal'])
        self.assertIn('local font manifest', rows['Detection'])

    def test_github_offer_does_not_invent_an_available_version(self):
        status = applications.ApplicationStatus(package=self.app.package, github_available=True)
        rows = dict(app_details.installation_rows(self.app, status))
        self.assertEqual(rows['Installation candidate'], 'Selected during the installation preview.')
        self.assertEqual(rows['Installed version or revision'], 'Not installed')

    def test_apt_error_never_becomes_a_github_installation_route(self):
        status = applications.ApplicationStatus(package=self.app.package, error='APT failed')
        rows = dict(app_details.installation_rows(self.app, status))
        self.assertEqual(rows['Method'], 'Debian package (APT)')
        self.assertIn('Repository errors do not enable', rows['GitHub fallback'])
        self.assertNotIn('Managed font directory', rows)

    def test_noto_lists_all_three_upstream_repositories(self):
        app = Application('fonts-noto', 'Noto', 'fonts-noto', 'Fonts')
        status = applications.ApplicationStatus(package=app.package, github_available=True)
        rows = dict(app_details.installation_rows(app, status))
        for repository in ('notofonts/noto-fonts', 'notofonts/noto-cjk', 'googlefonts/noto-emoji'):
            self.assertIn(repository, rows['Expected source'])


class BrowserInstallationDetailsTests(unittest.TestCase):
    def setUp(self):
        self.runner = BrowserRunner()

    def test_helium_candidate_shows_the_source_verified_by_the_backend(self):
        app = software.APP_BY_ID['helium']
        status = software.check_application(self.runner, app, 'amd64')
        rows = dict(browser_details.installation_rows(app, status))
        self.assertIn('https://pkg.helium.computer/deb/', rows['Verified candidate source'])
        self.assertIn('stable/main', rows['Verified candidate source'])
        self.assertIn('helium-bin', rows['Removal'])

    def test_installed_browser_does_not_claim_verified_download_origin(self):
        self.runner.installed['brave-browser'] = '1.0'
        app = software.APP_BY_ID['brave']
        status = software.check_application(self.runner, app, 'amd64')
        rows = dict(browser_details.installation_rows(app, status))
        self.assertNotIn('Verified candidate source', rows)
        self.assertIn('not been verified', rows['Origin check'])

    def test_zen_user_installation_lists_locations_and_preserves_profiles(self):
        app = software.APP_BY_ID['zen']
        status = software.Availability(installed=True, installed_version='1.2b')
        with patch.object(Path, 'home', return_value=Path('/home/example')):
            rows = dict(browser_details.installation_rows(app, status))
        self.assertEqual(rows['Scope'], 'Current user')
        self.assertIn('/home/example/.tarball-installations/zen', rows['Installation locations'])
        self.assertIn('/home/example/.local/bin/zen', rows['Installation locations'])
        self.assertIn('/home/example/.local/share/applications/zen.desktop', rows['Installation locations'])
        self.assertIn('Keep ~/.zen', rows['Removal'])
        self.assertIn("Zen's built-in updater", rows['Updates'])
        self.assertNotIn('Package', rows)

    def test_legacy_zen_is_detected_with_its_version_and_blocked_from_reinstallation(self):
        self.runner.installed['zen-browser'] = '1.0+masternaka1'
        with patch.object(zen.os, 'geteuid', return_value=1000):
            status = zen.check_status(self.runner, 'amd64')
        self.assertTrue(status.installed)
        self.assertFalse(status.installable)
        self.assertEqual(status.installation_method, 'legacy-deb')
        rows = dict(browser_details.installation_rows(software.APP_BY_ID['zen'], status))
        self.assertEqual(rows['Installed version or revision'], '1.0+masternaka1')
        self.assertEqual(rows['Method'], 'Debian package (APT)')
        self.assertEqual(rows['Scope'], 'System-wide')
        self.assertEqual(rows['Source of legacy package'], 'Not verified')
        self.assertIn('zen-browser', rows['Removal'])
        self.assertNotIn('Installation locations', rows)

    def test_browser_page_refreshes_details_without_starting_operations(self):
        page = SoftwarePage(AppContext(self.runner))
        status = software.collect_status(self.runner)
        with patch.object(page, 'run_operation') as operation:
            page._apply_status(status)
        self.assertEqual(dict(page.details['helium'].rows)['Installation candidate'], '1.2.3')
        operation.assert_not_called()


class SharedDetailsWidgetTests(unittest.TestCase):
    def test_refresh_preserves_the_users_expansion_state(self):
        details = InstallationDetails((('Method', 'APT'),))
        with patch.object(details, 'set_expanded') as expanded:
            details.update((('Method', 'GitHub'), ('Scope', 'Current user')))
        expanded.assert_not_called()
        self.assertEqual(details.rows, (('Method', 'GitHub'), ('Scope', 'Current user')))
