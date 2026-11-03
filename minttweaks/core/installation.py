"""Presentation of observed versions without inferring origin or update status."""
from ..i18n import _


def version_rows(status):
    if status is None:
        installed = candidate = _("Not analysed yet.")
    else:
        if status.installed:
            installed = status.installed_version or _("Not verified")
        else:
            installed = _("Not verified") if status.error else _("Not installed")
        if status.installed:
            candidate = _("Not checked for installed software.")
        elif status.error:
            candidate = _("Unavailable")
        else:
            candidate = status.candidate or _("Selected during the installation preview.")
    return ((_("Installed version or revision"), installed), (_("Installation candidate"), candidate))


def apt_lifecycle(package):
    return (
        (_("Updates"), _("Use Mint's Update Manager or APT with the sources configured on this machine.")),
        (_("Removal"), _("Remove {package} with Mint's package manager after reviewing its removal plan. User data may remain.").format(package=package)),
    )


def installed_apt_note(status):
    if status is not None and status.installed:
        return _("The installed Debian package was detected. Its download origin has not been verified.")
    return _("The expected source describes the installation route. It does not identify the origin of other existing copies.")
