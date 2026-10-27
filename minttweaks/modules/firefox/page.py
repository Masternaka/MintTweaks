"""The Firefox page: a checklist of add-ons and a policy writer."""

from __future__ import annotations

from typing import Dict, List

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ...modules.firefox import backend as firefox  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import AppContext, Page  # noqa: E402
from ...i18n import _  # noqa: E402


class FirefoxPage(Page):
    page_name = "firefox"
    page_title = "Firefox"
    page_icon = "web-browser-symbolic"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.status = firefox.FirefoxStatus()
        self._checks: Dict[str, Gtk.CheckButton] = {}
        self._status_labels: Dict[str, Gtk.Label] = {}
        self._can_escalate = widgets.escalation_available(ctx.runner)
        self._busy = False
        self._last_selection = True

        scroller = widgets.scrolled(self._build(), min_height=420)
        self.pack_start(scroller, True, True, 0)

    # -- construction ------------------------------------------------------
    def _build(self) -> Gtk.Box:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_margin_start(18)
        container.set_margin_end(18)
        container.set_margin_top(12)
        container.set_margin_bottom(18)

        if not self._can_escalate:
            warning = widgets.info_bar(
                _("Administrator rights are unavailable in this session: extensions can be inspected but not installed.")
            )
            warning.set_message_type(Gtk.MessageType.WARNING)
            container.pack_start(warning, False, False, 0)

        container.pack_start(self._build_extensions(), False, False, 0)
        return container

    def _build_extensions(self) -> Gtk.Box:
        outer, body = widgets.card(
            _("Extensions"),
            _(
                "Selected add-ons are downloaded from addons.mozilla.org and installed the next time "
                "Firefox starts. Installing an extension grants it the permissions listed on its "
                "addons.mozilla.org page."
            ),
        )

        self.profile_label = widgets.label(_("Detecting Firefox profiles…"), dim=True, wrap=True)
        body.pack_start(self.profile_label, False, False, 0)
        self.firefox_label = widgets.label("", dim=True, wrap=True)
        body.pack_start(self.firefox_label, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.select_all = Gtk.CheckButton(label=_("Select all missing extensions"))
        self.select_all.connect("toggled", self._on_select_all)
        controls.pack_start(self.select_all, True, True, 0)
        controls.pack_end(widgets.button(_("Re-analyse"), self.refresh), False, False, 0)
        body.pack_start(controls, False, False, 0)

        for extension in firefox.CATALOG:
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            texts.pack_start(widgets.title(extension.name), False, False, 0)
            texts.pack_start(widgets.label(extension.description, dim=True, wrap=True), False, False, 0)
            status = widgets.label("", dim=True, wrap=True)
            self._status_labels[extension.id] = status
            texts.pack_start(status, False, False, 0)

            check = Gtk.CheckButton()
            check.connect("toggled", lambda _check: self._update_apply())
            self._checks[extension.id] = check
            body.pack_start(widgets.row(texts, check), False, False, 0)

        self.selection_label = widgets.label("", dim=True, wrap=True)
        body.pack_start(self.selection_label, False, False, 0)

        self.apply_button = widgets.button(
            _("Install selected extensions"), self._on_apply, "suggested-action"
        )
        self.apply_button.set_sensitive(False)
        body.pack_start(self.apply_button, False, False, 0)

        self.clear_button = widgets.button(_("Remove MintTweaks policy"), self._on_clear_policy)
        self.clear_button.set_sensitive(False)
        body.pack_start(self.clear_button, False, False, 0)

        self.policy_label = widgets.label("", dim=True, wrap=True)
        body.pack_start(self.policy_label, False, False, 0)
        return outer

    # -- data loading ------------------------------------------------------
    def refresh(self) -> None:
        self.profile_label.set_text(_("Detecting Firefox profiles…"))
        self.ctx.run_async(firefox.collect_status, on_done=self._apply_status)

    def _apply_status(self, status: firefox.FirefoxStatus) -> None:
        self.status = status
        self._busy = False

        if status.profiles:
            self.profile_label.set_text(
                _("{count} Firefox profile(s) detected.").format(count=status.profiles)
            )
        else:
            self.profile_label.set_text(
                _("No Firefox profile was found. Start Firefox once so MintTweaks can detect installed extensions.")
            )
        self.firefox_label.set_text(
            "" if status.firefox_found else _("Firefox does not appear to be installed.")
        )

        if status.policy_error:
            self.policy_label.set_text(
                _("The existing Firefox policy could not be read: {error}").format(error=status.policy_error)
            )
        elif status.policy_ids:
            self.policy_label.set_text(
                _("MintTweaks currently manages {count} extension(s) in the Firefox policy.").format(
                    count=len(status.policy_ids)
                )
            )
        else:
            self.policy_label.set_text("")

        for extension in firefox.CATALOG:
            check = self._checks[extension.id]
            label = self._status_labels[extension.id]
            installed = extension.id in status.installed_ids
            managed = extension.id in status.policy_ids

            if installed:
                check.set_active(True)
                check.set_sensitive(False)
                label.set_text(_("Installed."))
            elif managed:
                check.set_active(True)
                check.set_sensitive(not status.policy_error)
                label.set_text(_("Will be installed the next time Firefox starts."))
            else:
                check.set_active(False)
                check.set_sensitive(not status.policy_error)
                label.set_text(_("Not installed."))

        missing = [
            extension
            for extension in firefox.CATALOG
            if extension.id not in status.installed_ids
        ]
        self.select_all.set_sensitive(bool(missing) and not status.policy_error)
        if not missing:
            self.select_all.set_active(False)
        self._update_apply()
    # -- actions -----------------------------------------------------------
    def _selected_ids(self) -> List[str]:
        return [
            extension.id
            for extension in firefox.CATALOG
            if self._checks[extension.id].get_active()
            and extension.id not in self.status.installed_ids
        ]

    def _on_select_all(self, _check: Gtk.CheckButton) -> None:
        wanted = self.select_all.get_active()
        for extension in firefox.CATALOG:
            check = self._checks[extension.id]
            if check.get_sensitive():
                check.set_active(wanted)
        self._update_apply()

    def _update_apply(self) -> None:
        selected = self._selected_ids()
        self.selection_label.set_text(
            _("{count} extension(s) selected.").format(count=len(selected)) if selected else ""
        )
        allowed = (
            bool(selected)
            and self._can_escalate
            and not self._busy
            and not self.status.policy_error
        )
        self.apply_button.set_sensitive(allowed)
        self.clear_button.set_sensitive(
            bool(self.status.policy_ids)
            and self._can_escalate
            and not self._busy
            and not self.status.policy_error
        )

    def _on_apply(self) -> None:
        selected = self._selected_ids()
        if not selected:
            return
        names = "\n".join(firefox.EXTENSION_BY_ID[identifier].name for identifier in selected)
        detail = _(
            "{names}\n\nFirefox must be restarted after this. The add-ons are downloaded from "
            "addons.mozilla.org."
        ).format(names=names)
        if not self.confirm(_("Install these Firefox extensions?"), detail):
            return

        self._busy = True
        self._last_selection = True
        self._update_apply()
        self.ctx.log(_("Writing the Firefox extension policy…"))
        self.run_operation(
            lambda: firefox.apply_policy(self.ctx.runner, selected),
            on_done=self._after_apply,
            on_error=self._operation_failed,
        )

    def _on_clear_policy(self) -> None:
        if not self.confirm(
            _("Remove the MintTweaks Firefox policy?"),
            _("Extensions already installed in Firefox are kept. Only the policy entries written by MintTweaks are removed."),
            destructive=True,
        ):
            return
        self._busy = True
        self._last_selection = False
        self._update_apply()
        self.ctx.log(_("Removing the MintTweaks Firefox policy…"))
        self.run_operation(
            lambda: firefox.apply_policy(self.ctx.runner, []),
            on_done=self._after_apply,
            on_error=self._operation_failed,
        )

    def _operation_failed(self, exc: BaseException) -> None:
        self._busy = False
        self._update_apply()
        self.error(_("Could not update the Firefox policy."), str(exc))

    def _after_apply(self, outcome: firefox.ApplyOutcome) -> None:
        self._busy = False
        if outcome.ok:
            if self._last_selection:
                self.ctx.log(
                    _("Policy updated. Restart Firefox to install the selected extensions."), "ok"
                )
            else:
                self.ctx.log(_("The MintTweaks Firefox policy entries were removed."), "ok")
        else:
            self.ctx.log(outcome.output, "error")
            self.error(_("Could not update the Firefox policy."), outcome.output)
        self.refresh()
