"""Explain APT candidates and managed GitHub font copies without installing."""
from ...core import paths
from ...core.installation import apt_lifecycle, installed_apt_note, version_rows
from ...i18n import _
from . import fonts


def installation_rows(app, status=None):
    github = status is not None and (status.github_installed or status.github_available)
    package = status.package if status is not None and status.package else app.package
    if github:
        repositories = [item[0] for item in fonts.NOTO] if app.package == 'fonts-noto' else [fonts.RECIPES[app.package][0]]
        target = paths.DATA_DIR.parent / 'fonts' / 'minttweaks' / app.package
        rows = [(_("Method"), _("Font files from upstream GitHub repositories")),
                (_("Scope"), _("Current user")), (_("APT package reference"), app.package),
                (_("Expected source"), '\n'.join('https://github.com/' + repo for repo in repositories))]
        rows += list(version_rows(status))
        rows += [(_("Managed font directory"), str(target)),
                 (_("Updates"), _("This copy is not updated by APT or MintTweaks. Review a newer upstream revision before replacing it.")),
                 (_("Removal"), _("Review and remove only the managed font directory listed here, then refresh the font cache with Fontconfig. Other font directories are separate."))]
        if status.github_installed:
            note = _("The local font manifest and file checksums were checked. The displayed revision comes from that manifest.")
        else:
            note = _("The official APT package is missing. The upstream revision will be selected during the GitHub preview.")
        rows.append((_("Detection"), note))
    else:
        rows = [(_("Method"), _("Debian package (APT)")), (_("Scope"), _("System-wide")),
                (_("Package"), package),
                (_("Expected source"), _("Official repositories of Linux Mint and its Ubuntu or Debian base."))]
        rows += list(version_rows(status))
        if status is not None and status.origins and not status.error and not status.installed:
            rows.append((_("Verified candidate sources"), '\n'.join(status.origins)))
        rows.append((_("Origin check"), installed_apt_note(status)))
        rows += list(apt_lifecycle(package))
        if app.package in fonts.RECIPES:
            rows.append((_("GitHub fallback"), _("Offered only when the official APT package is confirmed missing. Repository errors do not enable this fallback.")))
    return tuple(rows)
