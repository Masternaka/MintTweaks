"""The Home page: system summary, read-only diagnostics and module shortcuts."""

from __future__ import annotations

from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from ...modules.home import backend as home  # noqa: E402
from ...ui import widgets  # noqa: E402
from ...ui.widgets import AppContext, Page  # noqa: E402
from ...i18n import _  # noqa: E402

SEVERITY_ICONS = {
    "error": "dialog-error-symbolic",
    "warn": "dialog-warning-symbolic",
    "info": "dialog-information-symbolic",
    "ok": "emblem-ok-symbolic",
}


class HomePage(Page):
    page_name = "home"
    page_title = _("Home")
    page_icon = "go-home-symbolic"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        self.report: Optional[home.HomeReport] = None
        self._summary_labels: Dict[str, Gtk.Label] = {}

        scroller = widgets.scrolled(self._build(), min_height=400)
        self.pack_start(scroller, True, True, 0)

    # -- construction ------------------------------------------------------
    def _build(self) -> Gtk.Box:
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        container.set_margin_start(18)
        container.set_margin_end(18)
        container.set_margin_top(12)
        container.set_margin_bottom(18)
        container.pack_start(self._build_summary(), False, False, 0)
        container.pack_start(self._build_diagnostics(), False, False, 0)
        container.pack_start(self._build_modules(), False, False, 0)
        return container

    def _build_summary(self) -> Gtk.Box:
        outer, body = widgets.card(_("System"), _("Read-only snapshot of this machine."))
        for key, heading in (
            ("os", _("Operating system")),
            ("kernel", _("Kernel")),
            ("host", _("Host name")),
            ("uptime", _("Uptime")),
            ("memory", _("Memory")),
            ("disk", _("Disk (/)")),
        ):
            value = widgets.label("-", dim=True)
            value.set_xalign(1.0)
            self._summary_labels[key] = value
            body.pack_start(widgets.row(widgets.label(heading), value), False, False, 0)
        return outer

    def _build_diagnostics(self) -> Gtk.Box:
        outer, body = widgets.card(
            _("Diagnostics"),
            _("Read-only checks. Nothing is changed."),
        )
        self.checks_label = widgets.label(_("Analysing the system, one moment…"), dim=True, wrap=True)
        body.pack_start(self.checks_label, False, False, 0)

        self.findings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        body.pack_start(self.findings_box, False, False, 0)

        body.pack_start(widgets.button(_("Re-analyse"), self.refresh), False, False, 0)
        return outer

    def _build_modules(self) -> Gtk.Box:
        outer, body = widgets.card(_("Modules"), _("Jump to a section."))
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, page_name in (
            (_("Maintenance"), "maintenance"),
            (_("Services"), "services"),
            (_("Samba sharing"), "samba"),
            (_("Firefox"), "firefox"),
        ):
            buttons.pack_start(
                widgets.button(label, lambda name=page_name: self._open_page(name)),
                False,
                False,
                0,
            )
        body.pack_start(buttons, False, False, 0)
        return outer

    # -- data loading ------------------------------------------------------
    def refresh(self) -> None:
        self.checks_label.set_text(_("Analysing the system, one moment…"))
        self.ctx.run_async(home.collect_report, on_done=self._apply_report)

    def _apply_report(self, report: home.HomeReport) -> None:
        self.report = report
        summary = report.summary
        self._summary_labels["os"].set_text(summary.os_name)
        self._summary_labels["kernel"].set_text(summary.kernel)
        self._summary_labels["host"].set_text(summary.hostname)
        self._summary_labels["uptime"].set_text(summary.uptime)
        if summary.memory_measured:
            self._summary_labels["memory"].set_text(
                _("{used} / {total} ({percent}% used)").format(
                    used=summary.memory_used,
                    total=summary.memory_total,
                    percent=summary.memory_percent,
                )
            )
        else:
            self._summary_labels["memory"].set_text(_("unknown"))
        if summary.disk_measured:
            self._summary_labels["disk"].set_text(
                _("{used} / {total} ({percent}% used, {free} free)").format(
                    used=summary.disk_used,
                    total=summary.disk_total,
                    percent=summary.disk_percent,
                    free=summary.disk_free,
                )
            )
        else:
            self._summary_labels["disk"].set_text(_("unknown"))

        self._rebuild_findings(report.findings)
        if report.errors or report.warnings:
            self.checks_label.set_text(
                _("{errors} error(s), {warnings} warning(s), {ok} check(s) passed.").format(
                    errors=report.errors,
                    warnings=report.warnings,
                    ok=report.passed,
                )
            )
        else:
            self.checks_label.set_text(_("All {count} checks passed.").format(count=report.passed))

        level = "error" if report.errors else "warn" if report.warnings else "ok"
        self.ctx.log(_("Analysis finished."), level)

    def _rebuild_findings(self, findings: List[home.Finding]) -> None:
        for child in self.findings_box.get_children():
            self.findings_box.remove(child)

        if not findings:
            self.findings_box.pack_start(widgets.label(_("No check was run."), dim=True), False, False, 0)
            return

        for finding in findings:
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            heading.pack_start(
                Gtk.Image.new_from_icon_name(
                    SEVERITY_ICONS.get(finding.severity, "dialog-information-symbolic"),
                    Gtk.IconSize.BUTTON,
                ),
                False,
                False,
                0,
            )
            heading.pack_start(widgets.title(finding.title), False, False, 0)
            texts.pack_start(heading, False, False, 0)
            if finding.detail:
                texts.pack_start(widgets.label(finding.detail, dim=True, wrap=True), False, False, 0)

            action = None
            if finding.page:
                action = widgets.button(
                    _("Open"), lambda name=finding.page: self._open_page(name)
                )
            self.findings_box.pack_start(widgets.row(texts, action), False, False, 0)

    # -- navigation --------------------------------------------------------
    def _open_page(self, name: str) -> None:
        window = self.get_toplevel()
        show_page = getattr(window, "show_page", None)
        if callable(show_page):
            show_page(name)
