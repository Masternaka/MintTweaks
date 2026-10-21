"""The Samba page: install, shares, users, raw configuration.

Every write goes through one funnel (:meth:`SambaPage._apply_conf_change`):
mutate a *copy* of the document, render it, validate with testparm, install
through the privileged helper, and only adopt the new document when all of that
succeeded. A refused save therefore leaves both memory and disk untouched.
"""

from __future__ import annotations

import pwd
from pathlib import Path
from typing import Callable, Dict, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ...core import paths as core_paths  # noqa: E402
from ...core.privilege import escalation_hint  # noqa: E402
from ...core.smbconf import SmbConf, merge_duplicate_keys  # noqa: E402
from ...modules.samba import backend  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import AppContext, Page  # noqa: E402
from ...i18n import _  # noqa: E402


class SambaPage(Page):
    page_name = "samba"
    page_title = "Samba sharing"
    page_icon = "network-server-symbolic"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.doc: Optional[backend.Document] = None
        self.status: Optional[backend.SambaStatus] = None
        self.shares: List[backend.Share] = []
        self.users: List[backend.SambaUser] = []
        self.selected_share: Optional[backend.Share] = None
        self.selected_user: Optional[backend.SambaUser] = None
        self._config_dirty = False
        self._saving = False
        self._can_escalate = widgets.escalation_available(ctx.runner)
        self._build()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        self.notebook = Gtk.Notebook()
        self.notebook.set_margin_start(6)
        self.notebook.set_margin_end(6)
        self.notebook.set_margin_top(6)
        self.notebook.set_margin_bottom(6)
        self.pack_start(self.notebook, True, True, 0)

        self.notebook.append_page(self._build_overview(), Gtk.Label(label=_("Overview")))
        self.notebook.append_page(self._build_shares(), Gtk.Label(label=_("Shares")))
        self.notebook.append_page(self._build_users(), Gtk.Label(label=_("Users")))
        self.notebook.append_page(self._build_config(), Gtk.Label(label="smb.conf"))

    # -- overview ----------------------------------------------------------
    def _build_overview(self) -> Gtk.Widget:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_margin_start(12)
        container.set_margin_end(12)
        container.set_margin_top(12)
        container.set_margin_bottom(12)

        self.install_bar = Gtk.InfoBar()
        self.install_bar.set_message_type(Gtk.MessageType.WARNING)
        self.install_bar.set_show_close_button(False)
        install_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_box.pack_start(
            widgets.label(_("Samba is not installed on this system."), wrap=True), True, True, 0
        )
        self.install_button = widgets.button(_("Install Samba"), self._on_install, "suggested-action")
        install_box.pack_start(self.install_button, False, False, 0)
        self.install_bar.get_content_area().add(install_box)
        container.pack_start(self.install_bar, False, False, 0)

        status_card, status_body = widgets.card(_("Status"))
        self.status_labels: Dict[str, Gtk.Label] = {}
        for key, heading in (
            ("packages", "Packages"),
            ("smbd", "smbd (file sharing)"),
            ("nmbd", "nmbd (NetBIOS browsing)"),
            ("config", "Configuration file"),
            ("firewall", "Firewall"),
        ):
            value = widgets.label("-", dim=True)
            value.set_xalign(1.0)
            self.status_labels[key] = value
            status_body.pack_start(widgets.action_row(heading, "", value), False, False, 0)
        container.pack_start(status_card, False, False, 0)

        actions_card, actions_body = widgets.card(
            _("Serve files on the network"), _("All of these need administrator rights.")
        )
        self.start_button = widgets.button(_("Enable and start sharing"), self._on_enable_sharing, "suggested-action")
        self.reload_button = widgets.button(_("Reload configuration"), self._on_reload)
        self.firewall_button = widgets.button(_("Allow Samba in the firewall"), self._on_firewall)
        self.connections_button = widgets.button(_("Show active connections"), self._on_connections)
        for heading, subtitle, control in (
            (_("Start sharing"), _("Enables smbd and nmbd, then starts them."), self.start_button),
            (_("Apply configuration"), _("Reloads smbd so new shares are served at once."), self.reload_button),
            (_("Firewall"), _("Adds the Samba application profile to ufw."), self.firewall_button),
            (_("Diagnostics"), _("Lists who is connected right now."), self.connections_button),
        ):
            actions_body.pack_start(widgets.action_row(heading, subtitle, control), False, False, 0)
        container.pack_start(actions_card, False, False, 0)

        for button in (self.start_button, self.reload_button, self.firewall_button, self.install_button):
            if not self._can_escalate:
                button.set_sensitive(False)
                button.set_tooltip_text(_("Administrator rights are unavailable in this session."))

        return widgets.scrolled(container, min_height=300)

    # -- shares ------------------------------------------------------------
    def _build_shares(self) -> Gtk.Widget:
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(240)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_margin_start(10)
        left.set_margin_top(10)
        left.set_margin_bottom(10)
        left.pack_start(widgets.title(_("Shares")), False, False, 0)
        self.share_list = Gtk.ListBox()
        self.share_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.share_list.connect("row-selected", self._on_share_selected)
        left.pack_start(widgets.scrolled(self.share_list, min_height=200), True, True, 0)
        left.pack_start(widgets.button(_("New share"), self._on_new_share), False, False, 0)
        paned.pack1(left, True, False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_margin_start(12)
        right.set_margin_end(12)
        right.set_margin_top(10)
        right.set_margin_bottom(10)

        form = Gtk.Grid()
        form.set_column_spacing(10)
        form.set_row_spacing(6)
        self.share_fields = self._build_share_fields(form)
        right.pack_start(form, False, False, 0)

        advanced = Gtk.Expander(label=_("Advanced parameters"))
        advanced_grid = Gtk.Grid()
        advanced_grid.set_column_spacing(10)
        advanced_grid.set_row_spacing(6)
        advanced_grid.set_margin_top(6)
        self._add_field(advanced_grid, 0, _("Valid users"), self.share_fields["valid_users"])
        self._add_field(advanced_grid, 1, _("Write list"), self.share_fields["write_list"])
        self._add_field(advanced_grid, 2, _("Create mask"), self.share_fields["create_mask"])
        self._add_field(advanced_grid, 3, _("Directory mask"), self.share_fields["directory_mask"])
        self._add_field(advanced_grid, 4, _("Force group"), self.share_fields["force_group"])
        advanced.add(advanced_grid)
        right.pack_start(advanced, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.save_share_button = widgets.button(_("Save share"), self._on_save_share, "suggested-action")
        self.delete_share_button = widgets.button(_("Delete share"), self._on_delete_share, "destructive-action")
        buttons.pack_start(self.save_share_button, False, False, 0)
        buttons.pack_start(self.delete_share_button, False, False, 0)
        right.pack_start(buttons, False, False, 0)
        self.share_hint = widgets.label("", dim=True, wrap=True)
        right.pack_start(self.share_hint, False, False, 0)

        paned.pack2(right, True, False)
        return paned

    def _build_share_fields(self, grid: Gtk.Grid) -> Dict[str, Gtk.Widget]:
        fields: Dict[str, Gtk.Widget] = {
            "name": Gtk.Entry(),
            "path": Gtk.Entry(),
            "comment": Gtk.Entry(),
            "browseable": Gtk.Switch(),
            "read_only": Gtk.Switch(),
            "guest_ok": Gtk.Switch(),
            "valid_users": Gtk.Entry(),
            "write_list": Gtk.Entry(),
            "create_mask": Gtk.Entry(),
            "directory_mask": Gtk.Entry(),
            "force_group": Gtk.Entry(),
        }
        self.share_fields = fields

        self._add_field(grid, 0, _("Name"), fields["name"])
        browse = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        browse.pack_start(fields["path"], True, True, 0)
        browse.pack_start(widgets.button(_("Browse…"), self._on_browse), False, False, 0)
        self._add_widget(grid, 1, _("Folder"), browse)
        self._add_field(grid, 2, _("Comment"), fields["comment"])
        self._add_field(grid, 3, _("Browseable"), fields["browseable"])
        self._add_field(grid, 4, _("Read only"), fields["read_only"])
        self._add_field(grid, 5, _("Guest access"), fields["guest_ok"])
        return fields

    @staticmethod
    def _add_field(grid: Gtk.Grid, row: int, text: str, widget: Gtk.Widget) -> None:
        SambaPage._add_widget(grid, row, text, widget)

    @staticmethod
    def _add_widget(grid: Gtk.Grid, row: int, text: str, widget: Gtk.Widget) -> None:
        caption = widgets.label(text)
        caption.set_xalign(0.0)
        grid.attach(caption, 0, row, 1, 1)
        if isinstance(widget, Gtk.Switch):
            widget.set_halign(Gtk.Align.START)
        else:
            widget.set_hexpand(True)
        grid.attach(widget, 1, row, 1, 1)

    # -- users -------------------------------------------------------------
    def _build_users(self) -> Gtk.Widget:
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(240)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_margin_start(10)
        left.set_margin_top(10)
        left.set_margin_bottom(10)
        left.pack_start(widgets.title(_("Samba accounts")), False, False, 0)
        self.user_list = Gtk.ListBox()
        self.user_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.user_list.connect("row-selected", self._on_user_selected)
        left.pack_start(widgets.scrolled(self.user_list, min_height=200), True, True, 0)
        paned.pack1(left, True, False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_margin_start(12)
        right.set_margin_end(12)
        right.set_margin_top(10)
        right.set_margin_bottom(10)
        right.pack_start(
            widgets.label(
                _("A Samba account needs an existing Unix account: sharing a folder does not work "
                "without one. Passwords are sent to smbpasswd on its standard input, never on a "
                "command line."),
                dim=True,
                wrap=True,
            ),
            False,
            False,
            0,
        )

        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(6)
        self.user_combo = Gtk.ComboBoxText()
        self._fill_unix_users()
        self._add_widget(grid, 0, _("Unix account"), self.user_combo)
        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.password_entry.set_placeholder_text(_("at least 8 characters"))
        show = Gtk.CheckButton(label=_("Show"))
        show.connect("toggled", lambda widget: self.password_entry.set_visibility(widget.get_active()))
        password_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        password_box.pack_start(self.password_entry, True, True, 0)
        password_box.pack_start(show, False, False, 0)
        self._add_widget(grid, 1, _("Samba password"), password_box)
        right.pack_start(grid, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.user_password_button = widgets.button(
            _("Create / change password"), self._on_set_password, "suggested-action"
        )
        self.user_enable_button = widgets.button(_("Enable"), lambda: self._on_toggle_user(True))
        self.user_disable_button = widgets.button(_("Disable"), lambda: self._on_toggle_user(False))
        self.user_delete_button = widgets.button(_("Delete account"), self._on_delete_user, "destructive-action")
        for widget in (
            self.user_password_button,
            self.user_enable_button,
            self.user_disable_button,
            self.user_delete_button,
        ):
            buttons.pack_start(widget, False, False, 0)
        right.pack_start(buttons, False, False, 0)
        self.user_hint = widgets.label("", dim=True, wrap=True)
        right.pack_start(self.user_hint, False, False, 0)

        paned.pack2(right, True, False)
        return paned

    def _fill_unix_users(self) -> None:
        self.user_combo.remove_all()
        try:
            accounts = sorted(
                (entry for entry in pwd.getpwall() if entry.pw_uid >= 1000 and entry.pw_uid < 65534),
                key=lambda entry: entry.pw_name,
            )
        except (KeyError, OSError):
            accounts = []
        for entry in accounts:
            full_name = entry.pw_gecos.split(",")[0] or _("user")
            self.user_combo.append(entry.pw_name, f"{entry.pw_name} — {full_name}")
        if accounts:
            self.user_combo.set_active(0)

    # -- configuration -----------------------------------------------------
    def _build_config(self) -> Gtk.Widget:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        container.set_margin_start(12)
        container.set_margin_end(12)
        container.set_margin_top(10)
        container.set_margin_bottom(10)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.config_path_label = widgets.title(str(backend.conf_path()))
        header.pack_start(self.config_path_label, True, True, 0)
        header.pack_start(widgets.button(_("Validate"), self._on_validate_config), False, False, 0)
        header.pack_start(widgets.button(_("Save"), self._on_save_config, "suggested-action"), False, False, 0)
        header.pack_start(widgets.button(_("Revert"), self._on_revert_config), False, False, 0)
        header.pack_start(widgets.button(_("Clean up duplicates"), self._on_remove_duplicates), False, False, 0)
        header.pack_start(widgets.button(_("Restore a backup…"), self._on_restore_backup), False, False, 0)
        container.pack_start(header, False, False, 0)

        self.config_hint = widgets.label("", dim=True, wrap=True)
        container.pack_start(self.config_hint, False, False, 0)

        window, self.config_view, self.config_buffer = widgets.text_view(editable=True, height=340)
        self.config_buffer.connect("changed", self._on_config_changed)
        container.pack_start(window, True, True, 0)
        return container

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        def work():
            status = backend.collect_status(self.ctx.runner)
            doc = backend.load_document(self.ctx.runner)
            users = backend.list_users(self.ctx.runner) if status.installed else []
            return status, doc, users

        self.ctx.run_async(work, on_done=self._apply_state)

    def _apply_state(self, payload) -> None:
        status, doc, users = payload
        self.status = status
        self.doc = doc
        self.users = users
        self.shares = backend.list_shares(doc.conf)

        self._apply_status(status)
        self._fill_share_list()
        self._fill_user_list()
        self._fill_config(doc)

        installed = status.installed
        self.install_bar.set_revealed(not installed)
        for index in (1, 2):  # Shares, Users
            self.notebook.get_nth_page(index).set_sensitive(installed)
        self._set_share_buttons_sensitive(installed and self._can_escalate and bool(self.shares))
        self.ctx.log(_("Samba status refreshed."), "ok")

    def _apply_status(self, status: backend.SambaStatus) -> None:
        if status.installed:
            missing = status.missing_packages
            self.status_labels["packages"].set_text(
                _("installed") if not missing else _("missing: {packages}").format(packages=", ".join(missing))
            )
        else:
            self.status_labels["packages"].set_text(_("not installed"))

        states = {service.name: service for service in status.services}
        for key, unit in (("smbd", "smbd"), ("nmbd", "nmbd")):
            service = states.get(unit)
            self.status_labels[key].set_text(
                f"{service.active}, {service.enabled}" if service else _("unknown")
            )
        self.status_labels["config"].set_text(
            "{} · {}".format(_("present") if status.conf_exists else _("absent"), backend.conf_path())
        )
        if not status.firewall_available:
            self.status_labels["firewall"].set_text(_("ufw not installed"))
        else:
            state = _("active") if status.firewall_active else _("inactive")
            allowed = _("Samba allowed") if status.firewall_allows_samba else _("Samba not allowed")
            self.status_labels["firewall"].set_text(f"{state} · {allowed}")
        self.firewall_button.set_sensitive(
            status.firewall_available and self._can_escalate and not status.firewall_allows_samba
        )
        self.connections_button.set_sensitive(status.installed)

    def _fill_share_list(self) -> None:
        for child in self.share_list.get_children():
            self.share_list.remove(child)
        for share in self.shares:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            box.set_margin_start(6)
            box.set_margin_end(6)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            box.pack_start(widgets.label(share.name), False, False, 0)
            box.pack_start(widgets.label(share.path, dim=True), False, False, 0)
            row.add(box)
            self.share_list.add(row)

    def _fill_user_list(self) -> None:
        for child in self.user_list.get_children():
            self.user_list.remove(child)
        for user in self.users:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            box.set_margin_start(6)
            box.set_margin_end(6)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            box.pack_start(widgets.label(user.name), False, False, 0)
            state = _("enabled") if user.enabled else _("disabled")
            if not user.has_unix_account:
                state += " · " + _("no Unix account")
            box.pack_start(widgets.label(state, dim=True), False, False, 0)
            row.add(box)
            self.user_list.add(row)

    def _fill_config(self, doc: backend.Document) -> None:
        self.config_path_label.set_text(str(doc.path))
        if self._config_dirty:
            self.config_hint.set_text(_("The editor has unsaved changes; the file on disk has changed since."))
            return
        self.config_buffer.set_text(doc.text or backend.render(doc))
        self._config_dirty = False
        duplicates = doc.duplicates
        if duplicates:
            self.config_hint.set_text(
                _("Warning: these sections are defined twice and Samba merges them: ")
                + ", ".join(duplicates)
            )
        else:
            self.config_hint.set_text(_("Validated with testparm before every save."))

    # ------------------------------------------------------------------ #
    # Shares
    # ------------------------------------------------------------------ #
    def _on_share_selected(self, listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        if row is None:
            self.selected_share = None
            self._set_share_buttons_sensitive(False)
            return
        index = listbox.get_children().index(row)
        if not 0 <= index < len(self.shares):
            return
        share = self.shares[index]
        self.selected_share = share
        self._share_to_form(share)
        self._set_share_buttons_sensitive(True)
        self.share_hint.set_text("")

    def _set_share_buttons_sensitive(self, sensitive: bool) -> None:
        self.save_share_button.set_sensitive(sensitive)
        self.delete_share_button.set_sensitive(sensitive)

    def _share_to_form(self, share: backend.Share) -> None:
        fields = self.share_fields
        fields["name"].set_text(share.name)
        fields["path"].set_text(share.path)
        fields["comment"].set_text(share.comment)
        fields["browseable"].set_active(share.browseable)
        fields["read_only"].set_active(share.read_only)
        fields["guest_ok"].set_active(share.guest_ok)
        fields["valid_users"].set_text(share.valid_users)
        fields["write_list"].set_text(share.write_list)
        fields["create_mask"].set_text(share.create_mask)
        fields["directory_mask"].set_text(share.directory_mask)
        fields["force_group"].set_text(share.force_group)

    def _form_to_share(self) -> backend.Share:
        fields = self.share_fields
        return backend.Share(
            name=fields["name"].get_text().strip(),
            path=fields["path"].get_text().strip(),
            comment=fields["comment"].get_text().strip(),
            browseable=fields["browseable"].get_active(),
            read_only=fields["read_only"].get_active(),
            guest_ok=fields["guest_ok"].get_active(),
            valid_users=fields["valid_users"].get_text().strip(),
            write_list=fields["write_list"].get_text().strip(),
            create_mask=fields["create_mask"].get_text().strip(),
            directory_mask=fields["directory_mask"].get_text().strip(),
            force_group=fields["force_group"].get_text().strip(),
        )

    def _on_new_share(self) -> None:
        self.selected_share = None
        self.share_list.unselect_all()
        self._share_to_form(backend.Share(name="", path="", read_only=False))
        self._set_share_buttons_sensitive(self._can_escalate)
        self.delete_share_button.set_sensitive(False)
        self.share_hint.set_text(_("Fill in a name and pick an existing folder, then save."))

    def _on_browse(self) -> None:
        dialog = Gtk.FileChooserDialog(
            "Choose a folder to share",
            self.window,
            Gtk.FileChooserAction.SELECT_FOLDER,
            ("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK),
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.share_fields["path"].set_text(dialog.get_filename() or "")
        dialog.destroy()

    def _on_save_share(self) -> None:
        share = self._form_to_share()
        previous = self.selected_share
        if share.name and not backend.is_windows_safe_share_name(share.name):
            # Not fatal - Samba accepts it - but Windows clients show odd names.
            self.ctx.log(
                f"Note: '{share.name}' is long or contains characters Windows clients abbreviate.",
                "warn",
            )

        def mutate(conf: SmbConf) -> Optional[str]:
            problems = (
                backend.create_share(conf, share)
                if previous is None
                else backend.update_share(conf, share, previous)
            )
            return "\n".join(problems) if problems else None

        self._apply_conf_change(mutate, _("Share '{name}' saved.").format(name=share.name))

    def _on_delete_share(self) -> None:
        if self.selected_share is None:
            return
        name = self.selected_share.name
        if not self.confirm(
            _("Delete the share '{name}'?").format(name=name),
            _("The folder and its files are kept; only the Samba share is removed."),
            destructive=True,
        ):
            return
        self._apply_conf_change(
            lambda conf: None
            if backend.delete_share(conf, name)
            else _("Share '{name}' not found.").format(name=name),
            _("Share '{name}' deleted.").format(name=name),
        )

    # ------------------------------------------------------------------ #
    # Users
    # ------------------------------------------------------------------ #
    def _on_user_selected(self, listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        if row is None:
            self.selected_user = None
            return
        index = listbox.get_children().index(row)
        if not 0 <= index < len(self.users):
            return
        user = self.users[index]
        self.selected_user = user
        current = self.user_combo.get_active_id()
        if current != user.name and user.has_unix_account:
            self.user_combo.set_active_id(user.name)
        self.user_hint.set_text("" if user.has_unix_account else _("This account has no Unix user behind it."))

    def _on_set_password(self) -> None:
        username = self.user_combo.get_active_id()
        password = self.password_entry.get_text()
        if not username:
            self.error(_("No account selected"), _("Choose the Unix account to give a Samba password to."))
            return
        problem = backend.password_problem(password)
        if problem:
            self.error(_("Password rejected"), problem)
            return
        self.ctx.run_async(
            lambda: backend.add_user(self.ctx.runner, username, password),
            on_done=lambda result: self._after_user_action(
                result, _("Samba password set for {user}.").format(user=username)
            ),
        )

    def _on_toggle_user(self, enabled: bool) -> None:
        if self.selected_user is None:
            self.error(_("No account selected"), _("Pick a Samba account in the list first."))
            return
        username = self.selected_user.name
        self.ctx.run_async(
            lambda: backend.set_user_enabled(self.ctx.runner, username, enabled),
            on_done=lambda result: self._after_user_action(
                result,
                _("Account {user} {state}.").format(
                    user=username, state=_("enabled") if enabled else _("disabled")
                ),
            ),
        )

    def _on_delete_user(self) -> None:
        if self.selected_user is None:
            self.error(_("No account selected"), _("Pick a Samba account in the list first."))
            return
        username = self.selected_user.name
        if not self.confirm(
            _("Delete the Samba account '{user}'?").format(user=username),
            _("The Unix account and its files are kept."),
            destructive=True,
        ):
            return
        self.ctx.run_async(
            lambda: backend.delete_user(self.ctx.runner, username),
            on_done=lambda result: self._after_user_action(
                result, _("Samba account {user} deleted.").format(user=username)
            ),
        )

    def _after_user_action(self, result, success_message: str) -> None:
        if result.ok:
            self.ctx.log(success_message, "ok")
            self.password_entry.set_text("")
            self.refresh()
        else:
            self.ctx.log(f"Samba account action failed: {result.output}", "error")
            self.error(_("The Samba account could not be updated"), result.output)

    # ------------------------------------------------------------------ #
    # Overview actions
    # ------------------------------------------------------------------ #
    def _on_install(self) -> None:
        if not self.confirm(
            _("Install Samba?"),
            _("The packages samba, smbclient and cifs-utils are installed with apt."),
        ):
            return
        self.install_button.set_sensitive(False)
        self.ctx.run_async(
            lambda: backend.install_packages(self.ctx.runner, on_line=self.ctx.log),
            on_done=self._after_install,
        )

    def _after_install(self, result) -> None:
        self.install_button.set_sensitive(self._can_escalate)
        if result.ok:
            self.ctx.log(_("Samba installed."), "ok")
        else:
            self.ctx.log(f"Samba installation failed: {result.output}", "error")
            self.error(_("Samba could not be installed"), result.output)
        self.refresh()

    def _on_enable_sharing(self) -> None:
        self.ctx.run_async(
            lambda: backend.enable_and_start_sharing(self.ctx.runner, on_line=self.ctx.log),
            on_done=self._after_enable_sharing,
        )

    def _after_enable_sharing(self, results) -> None:
        failures = [result for result in results if not result.ok]
        if failures:
            self.ctx.log(f"Starting Samba failed: {failures[0].output}", "error")
        else:
            self.ctx.log(_("smbd and nmbd are enabled and running."), "ok")
        self.refresh()

    def _on_reload(self) -> None:
        self.ctx.run_async(
            lambda: backend.restart_after_change(self.ctx.runner, on_line=self.ctx.log),
            on_done=lambda results: self._report_simple(results),
        )

    def _on_firewall(self) -> None:
        if not self.confirm(_("Allow Samba through the firewall?"), _("This runs 'ufw allow Samba'.")):
            return
        self.ctx.run_async(
            lambda: backend.allow_samba_in_firewall(self.ctx.runner),
            on_done=lambda result: self._report_simple([result]),
        )

    def _on_connections(self) -> None:
        self.ctx.run_async(
            lambda: backend.smbstatus_text(self.ctx.runner),
            on_done=self._show_connections,
        )

    def _show_connections(self, result) -> None:
        if result.ok:
            self.ctx.log(_("Active Samba connections:"), "info")
            for line in (result.stdout or "(none)").splitlines():
                self.ctx.log(line, "command")
        else:
            self.ctx.log(f"smbstatus failed: {result.output}", "error")

    def _report_simple(self, results) -> None:
        failures = [result for result in results if not result.ok]
        level = "error" if failures else "ok"
        message = failures[0].output if failures else _("Done.")
        self.ctx.log(message, level)
        self.refresh()

    # ------------------------------------------------------------------ #
    # Raw configuration
    # ------------------------------------------------------------------ #
    def _on_config_changed(self, _buffer: Gtk.TextBuffer) -> None:
        self._config_dirty = True

    def _config_text(self) -> str:
        start, end = self.config_buffer.get_bounds()
        return self.config_buffer.get_text(start, end, False)

    def _on_validate_config(self) -> None:
        text = self._config_text()
        self.ctx.run_async(
            lambda: backend.validate_text(self.ctx.runner, text),
            on_done=self._after_validate,
        )

    def _after_validate(self, validation: backend.Validation) -> None:
        if validation.ok:
            message = _("Configuration is valid.")
            if validation.warnings:
                message += _("\n\nWarnings:\n") + "\n".join(validation.warnings[:10])
            self.ctx.log(message.splitlines()[0], "ok")
            self.info(_("Configuration is valid"), message)
        else:
            detail = "\n".join(validation.errors[:15]) or validation.output[:1500]
            self.ctx.log(_("testparm rejected the configuration."), "error")
            self.error(_("testparm rejected this configuration"), detail)

    def _on_save_config(self) -> None:
        text = self._config_text()
        self._save_text(text, _("Configuration saved."))

    def _on_remove_duplicates(self) -> None:
        if self.doc is None:
            return
        working = self.doc.conf.copy()
        removed = merge_duplicate_keys(working)
        if not removed:
            self.info(
                _("No duplicate parameter"),
                _("No section of this configuration repeats the same key, so there is nothing to clean up."),
            )
            return
        preview = "\n".join(removed[:12])
        if len(removed) > 12:
            preview += _("\n… and {count} more").format(count=len(removed) - 12)
        if not self.confirm(
            _("Remove {count} duplicate parameter(s)?").format(count=len(removed)),
            preview + _("\n\nSamba already ignores every value but the last one."),
        ):
            return
        self._save_text(
            working.render(),
            _("Removed {count} duplicate parameter(s).").format(count=len(removed)),
            new_conf=working,
        )

    def _on_revert_config(self) -> None:
        if self.doc is None:
            return
        if self._config_dirty and not self.confirm(
            _("Discard your changes?"), _("The editor is reloaded from the file on disk.")
        ):
            return
        self._config_dirty = False
        self.config_buffer.set_text(self.doc.text or backend.render(self.doc))
        self._config_dirty = False

    def _on_restore_backup(self) -> None:
        backups = backend.list_backups()
        if not backups:
            self.error(
                _("No backup found"),
                _("MintTweaks keeps its backups in {folder}.").format(folder=core_paths.BACKUP_DIR),
            )
            return
        dialog = Gtk.Dialog(title=_("Restore a backup"), transient_for=self.window, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Restore", Gtk.ResponseType.OK)
        combo = Gtk.ComboBoxText()
        for backup in backups:
            combo.append(str(backup), backup.name)
        combo.set_active(0)
        dialog.get_content_area().add(combo)
        dialog.show_all()
        response = dialog.run()
        selected = combo.get_active_id()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not selected:
            return
        self.ctx.run_async(
            lambda: backend.restore_backup(self.ctx.runner, Path(selected)),
            on_done=self._after_restore,
        )

    def _after_restore(self, outcome: backend.SaveOutcome) -> None:
        if outcome.ok:
            self.ctx.log(outcome.message, "ok")
            self._config_dirty = False
            self.refresh()
        else:
            self.ctx.log(f"Restore failed: {outcome.message}", "error")
            self.error(_("The backup could not be restored"), outcome.message)

    # ------------------------------------------------------------------ #
    # Shared save funnel
    # ------------------------------------------------------------------ #
    def _apply_conf_change(self, mutate: Callable[[SmbConf], Optional[str]], success_message: str) -> None:
        if self.doc is None:
            self.error(_("No configuration loaded"), _("Refresh the page and try again."))
            return
        if not self._can_escalate:
            self.error(
                _("Administrator rights are required"),
                "Changing shares means writing /etc/samba/smb.conf.\n\n" + escalation_hint(),
            )
            return

        working = self.doc.conf.copy()
        problem = mutate(working)
        if problem:
            self.error(_("This share cannot be saved"), problem)
            return

        candidate = working.render()
        self._save_text(candidate, success_message, new_conf=working)

    def _save_text(
        self,
        text: str,
        success_message: str,
        new_conf: Optional[SmbConf] = None,
    ) -> None:
        if self.doc is None:
            return
        if self._saving:
            self.ctx.log(_("A save is already in progress."), "warn")
            return
        self._saving = True
        doc = self.doc
        self.ctx.log(_("Validating and installing the configuration…"))

        def work():
            return backend.save_document(self.ctx.runner, doc, text=text)

        self.ctx.run_async(
            work,
            on_done=lambda outcome: self._after_save(outcome, text, new_conf, success_message),
            on_error=self._save_failed,
        )

    def _save_failed(self, error: BaseException) -> None:
        self._saving = False
        self.ctx.log(f"Saving the configuration failed: {error}", "error")
        self.error(_("The configuration was not saved"), str(error))

    def _after_save(
        self,
        outcome: backend.SaveOutcome,
        text: str,
        new_conf: Optional[SmbConf],
        success_message: str,
    ) -> None:
        self._saving = False
        if not outcome.ok:
            detail = outcome.message
            if outcome.validation and outcome.validation.errors:
                detail += "\n\n" + "\n".join(outcome.validation.errors[:15])
            self.ctx.log(detail, "error")
            self.error(_("The configuration was not saved"), detail)
            return
        self.doc.text = text
        self.doc.conf = new_conf if new_conf is not None else SmbConf.parse(text)
        self.doc.existed = True
        self._config_dirty = False
        self.ctx.log(outcome.message, "ok")
        self.ctx.log(success_message, "ok")
        self.refresh()
