"""The Maintenance page: see what takes space, then reclaim it."""

from __future__ import annotations

from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ...modules.maintenance import backend as maint  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import AppContext, Page  # noqa: E402
from ...i18n import _  # noqa: E402


class MaintenancePage(Page):
    page_name = "maintenance"
    page_title = "Maintenance"
    page_icon = "user-trash-symbolic"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.selected_kernels: List[maint.Kernel] = []
        self._size_labels: Dict[str, Gtk.Label] = {}
        self._task_buttons: Dict[str, Gtk.Button] = {}
        self._busy = False
        self._autoremove_packages: List[str] = []

        scroller = widgets.scrolled(self._build(), min_height=400)
        self.pack_start(scroller, True, True, 0)

    # -- construction ------------------------------------------------------
    def _build(self) -> Gtk.Box:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_margin_start(18)
        container.set_margin_end(18)
        container.set_margin_top(12)
        container.set_margin_bottom(18)
        container.pack_start(self._build_sizes(), False, False, 0)
        container.pack_start(self._build_orphans(), False, False, 0)
        container.pack_start(self._build_tasks(), False, False, 0)
        container.pack_start(self._build_kernels(), False, False, 0)
        return container

    def _build_sizes(self) -> Gtk.Box:
        outer, body = widgets.card(
            _("Disk usage"),
            _("Sizes are measured, not estimated. Nothing is removed from this card."),
        )
        for key, heading, subtitle in (
            ("apt", _("Package cache"), _("/var/cache/apt/archives - downloaded .deb files")),
            ("journal", _("System journal"), _("journald logs, shrinkable without losing the last weeks")),
            ("thumbnails", _("Thumbnail cache"), _("rebuilt automatically by the file manager")),
            ("trash", _("Trash"), _("your user trash")),
        ):
            value = widgets.label("-", dim=True)
            value.set_xalign(1.0)
            self._size_labels[key] = value
            body.pack_start(widgets.action_row(heading, subtitle, value), False, False, 0)
        body.pack_start(
            widgets.row(
                widgets.label(""),
                widgets.button(_("Re-analyse"), self.refresh, "suggested-action"),
            ),
            False,
            False,
            0,
        )
        return outer

    def _build_orphans(self) -> Gtk.Box:
        outer, body = widgets.card(
            _("Orphaned packages"),
            _("Packages installed automatically that nothing depends on any more."),
        )
        self.autoremove_label = widgets.label(_("Not analysed yet."), wrap=True)
        body.pack_start(self.autoremove_label, False, False, 0)
        self.autoremove_button = widgets.button(
            _("Remove orphaned packages"), self._on_autoremove, "destructive-action"
        )
        self.autoremove_button.set_sensitive(False)
        body.pack_start(self.autoremove_button, False, False, 0)
        self.autoremove_detail = widgets.label("", dim=True, wrap=True)
        body.pack_start(self.autoremove_detail, False, False, 0)
        return outer

    def _build_tasks(self) -> Gtk.Box:
        outer, body = widgets.card(_("Cleanup tasks"), _("Each task shows exactly what it will run."))
        can_escalate = widgets.escalation_available(self.ctx.runner)
        for task in maint.available_tasks(self.ctx.runner):
            onclick = (lambda t=task: self._run_task(t))
            button = widgets.button(_("Run"), onclick)
            if task.danger >= 2:
                button.get_style_context().add_class("destructive-action")
            if task.needs_root and not can_escalate:
                button.set_sensitive(False)
                button.set_tooltip_text(_("Requires administrator rights, and privilege escalation is unavailable."))
            self._task_buttons[task.id] = button
            body.pack_start(widgets.action_row(task.title, task.detail, button), False, False, 0)
        return outer

    def _build_kernels(self) -> Gtk.Box:
        outer, body = widgets.card(
            _("Installed kernels"),
            _("The running kernel and the newest one are always kept. "
            "Linux Mint's Update Manager can also remove kernels; both tools are safe to use."),
        )
        self.kernel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        body.pack_start(self.kernel_box, False, False, 0)
        self.kernel_button = widgets.button(_("Purge selected kernels"), self._on_purge, "destructive-action")
        self.kernel_button.set_sensitive(False)
        body.pack_start(self.kernel_button, False, False, 0)
        return outer

    # -- data loading ------------------------------------------------------
    def refresh(self) -> None:
        self.ctx.log(_("Analysing the system, one moment…"))
        for value in self._size_labels.values():
            value.set_text("…")
        self.ctx.run_async(
            lambda: maint.collect_maintenance(self.ctx.runner),
            on_done=self._apply_refresh,
            on_error=self._on_analysis_error,
        )

    def _on_analysis_error(self, exc: BaseException) -> None:
        self._autoremove_packages = []
        self._rebuild_kernels([])
        for value in self._size_labels.values():
            value.set_text(_("unknown"))
        self._set_busy(self._busy)
        self.autoremove_label.set_text(_("The removal preview could not be read. Re-analyse before removing packages."))
        self.autoremove_detail.set_text(str(exc))
        self.ctx.log(str(exc), "error")

    def _apply_refresh(self, payload) -> None:
        probe, kernels = payload
        self._autoremove_packages = list(probe.autoremove_packages)
        self._size_labels["apt"].set_text(maint.human_bytes(probe.apt_archives_bytes))
        self._size_labels["journal"].set_text(maint.human_bytes(probe.journal_bytes))
        self._size_labels["thumbnails"].set_text(maint.human_bytes(probe.thumbnails_bytes))
        self._size_labels["trash"].set_text(maint.human_bytes(probe.trash_bytes))

        count = probe.autoremove_count
        if probe.autoremove_error:
            self.autoremove_label.set_text(_("The removal preview could not be read. Re-analyse before removing packages."))
            self.autoremove_detail.set_text(probe.autoremove_error)
            self.autoremove_button.set_sensitive(False)
        elif count:
            preview = ", ".join(probe.autoremove_packages[:8])
            if count > 8:
                preview += _(", … (+{count})").format(count=count - 8)
            self.autoremove_label.set_text(_("{count} package(s) can be removed.").format(count=count))
            self.autoremove_detail.set_text(preview)
            self.autoremove_button.set_label(_("Remove {count} package(s)").format(count=count))
            self.autoremove_button.set_sensitive(True)
        else:
            self.autoremove_label.set_text(_("Nothing to remove: every installed package is still needed."))
            self.autoremove_detail.set_text("")
            self.autoremove_button.set_label(_("Remove orphaned packages"))
            self.autoremove_button.set_sensitive(False)

        self._rebuild_kernels(kernels)
        if probe.kernel_error:
            for child in self.kernel_box.get_children():
                self.kernel_box.remove(child)
            self.kernel_box.pack_start(widgets.label(
                _("The kernel list could not be read: {error}").format(error=probe.kernel_error), wrap=True,
            ), False, False, 0)
            self.kernel_box.show_all()
        self._set_busy(self._busy)
        self.ctx.log(_("Analysis finished."), "warn" if probe.autoremove_error or probe.kernel_error else "ok")

    def _rebuild_kernels(self, kernels: List[maint.Kernel]) -> None:
        for child in self.kernel_box.get_children():
            self.kernel_box.remove(child)
        self.selected_kernels = []

        removable = {kernel.version for kernel in maint.removable_kernels(kernels, keep=1)}
        if not kernels:
            self.kernel_box.pack_start(widgets.label(_("No linux-image package found."), dim=True), False, False, 0)
        for kernel in kernels:
            state = []
            if kernel.running:
                state.append(_("running"))
            state.append(_("removable") if kernel.version in removable else _("kept"))
            check = Gtk.CheckButton(label=f"{kernel.version}  ({', '.join(state)})")
            if kernel.version not in removable:
                check.set_sensitive(False)
            check.connect("toggled", self._on_kernel_toggle, kernel)
            self.kernel_box.pack_start(check, False, False, 0)
        self.kernel_button.set_sensitive(False)

    # -- actions -----------------------------------------------------------
    def _on_kernel_toggle(self, check: Gtk.CheckButton, kernel: maint.Kernel) -> None:
        if check.get_active():
            if kernel not in self.selected_kernels:
                self.selected_kernels.append(kernel)
        else:
            self.selected_kernels = [item for item in self.selected_kernels if item.version != kernel.version]
        self.kernel_button.set_sensitive(
            not self._busy and widgets.escalation_available(self.ctx.runner) and bool(self.selected_kernels)
        )

    def _on_purge(self) -> None:
        if self._busy or not self.selected_kernels:
            return
        names = "\n".join(kernel.version for kernel in self.selected_kernels)
        detail = _("{kernels}\n\nEvery related package is removed (about 300 MB each).").format(kernels=names)
        if not self.confirm(_("Purge these kernels?"), detail, destructive=True):
            return
        selected = list(self.selected_kernels)
        self._set_busy(True)
        self.run_operation(
            lambda: maint.purge_kernels(self.ctx.runner, selected, on_line=self.ctx.log),
            on_done=self._after_purge,
            on_error=self._on_operation_error,
            name=_("Purge selected kernels"),
        )

    def _after_purge(self, result) -> None:
        self._set_busy(False)
        self._report(result, "Kernels purged.", "Purging kernels failed.")
        self.refresh()

    def _on_autoremove(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.ctx.run_async(
            lambda: maint.autoremove_preview(self.ctx.runner),
            on_done=self._confirm_autoremove,
            on_error=self._on_operation_error,
        )

    def _confirm_autoremove(self, packages: List[str]) -> None:
        if not packages:
            self._autoremove_packages = []
            self._set_busy(False)
            self.info(_("Nothing to remove: every installed package is still needed."))
            self.refresh()
            return
        accepted = widgets.confirm_list(
            self.window,
            _("Remove orphaned packages?"),
            packages,
            _("{count} package(s) are proposed for removal. The complete list is shown below. "
              "APT will be checked again before execution; if the list changes, removal will be refused.").format(count=len(packages)),
        )
        if not accepted:
            self._set_busy(False)
            return
        self._execute(maint.TASK_BY_ID["apt_autoremove"], approved_packages=packages)

    def _run_task(self, task: maint.Task) -> None:
        if self._busy:
            return
        if task.id == "apt_autoremove":
            self._on_autoremove()
            return
        if task.danger >= 1 and not self.confirm(
            task.title,
            task.detail + _("\n\nThis cannot be undone from MintTweaks."),
            destructive=task.danger >= 2,
        ):
            return
        self._execute(task)

    def _execute(self, task: maint.Task, approved_packages=None) -> None:
        self._set_busy(True)
        self.ctx.log(f"Running: {task.title}")
        self.run_operation(
            lambda: maint.run_task(self.ctx.runner, task, on_line=self.ctx.log, approved_packages=approved_packages),
            on_done=self._after_task,
            on_error=self._on_operation_error,
            name=task.title,
        )

    def _after_task(self, outcome) -> None:
        self._set_busy(False)
        level = "ok" if outcome.ok else "error"
        self.ctx.log(outcome.summary(), level)
        self.refresh()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        can_escalate = widgets.escalation_available(self.ctx.runner)
        for task_id, button in self._task_buttons.items():
            allowed = not maint.TASK_BY_ID[task_id].needs_root or can_escalate
            button.set_sensitive(not busy and allowed)
        self.autoremove_button.set_sensitive(not busy and can_escalate and bool(self._autoremove_packages))
        self.kernel_button.set_sensitive(not busy and can_escalate and bool(self.selected_kernels))

    def _on_operation_error(self, exc: BaseException) -> None:
        self._set_busy(False)
        self.ctx.log(str(exc), "error")
        self.error(_("The operation failed."), str(exc))

    def _report(self, result, success: str, failure: str) -> None:
        if result is not None and getattr(result, "ok", True):
            self.ctx.log(success, "ok")
        else:
            output: Optional[str] = getattr(result, "output", "") if result is not None else ""
            self.ctx.log(f"{failure} {output or ''}".strip(), "error")
