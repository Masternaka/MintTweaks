"""Installation routes and lifecycle guidance for the browser catalog."""
from ...core.installation import apt_lifecycle, installed_apt_note, version_rows
from ...i18n import _
from . import zen


def installation_rows(app, status=None):
    legacy = status is not None and status.installation_method == 'legacy-deb'
    if app.method == 'apt' or legacy:
        rows = [(_("Method"), _("Debian package (APT)")), (_("Scope"), _("System-wide")),
                (_("Package"), app.package)]
        rows.append((_("Source of legacy package"), _("Not verified")) if legacy else (_("Expected source"), app.origin))
        rows += list(version_rows(status))
        if not legacy and status is not None and status.installable:
            rows.append((_("Verified candidate source"), app.origin + ' (' + app.suite + ')'))
        rows.append((_("Origin check"), installed_apt_note(status)))
        if legacy:
            rows.append((_("Installation note"), _("The old Zen Debian package was detected. This is separate from the official user installation offered here.")))
        rows += list(apt_lifecycle(app.package))
    else:
        rows = [(_("Method"), _("Official GitHub installer and native archive")),
                (_("Scope"), _("Current user")), (_("Expected source"), app.origin),
                (_("Installer"), zen.INSTALLER_URL)]
        rows += list(version_rows(status))
        rows += [(_("Installation locations"), '\n'.join(str(path) for path in zen.targets())),
                 (_("Updates"), _("Use Zen's built-in updater. MintTweaks does not check for newer releases here.")),
                 (_("Removal"), _("Close Zen, then review and remove only the application directory, launcher and menu entry listed here. Keep ~/.zen if you want to preserve your profiles.")),
                 (_("Detection"), _("Detection checks the user installation files and application.ini. It does not inspect Flatpak installations or copies in other locations."))]
    return tuple(rows)
