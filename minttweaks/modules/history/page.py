"""Read-only history; restoration stays in the module which owns the backup."""
from __future__ import annotations

import datetime

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from ...core.history import STATUSES
from ...i18n import _
from ...ui import widgets
from ...ui.widgets import Page


def status_label(status):
    return {
        'running': _("In progress"),
        'completed': _("Completed"),
        'failed': _("Failed"),
        'simulation': _("Simulation"),
        'unknown': _("Result unknown after interruption"),
        'interface_error': _("Interface error after the operation"),
    }.get(status, _("Unknown"))


def local_time(value):
    return datetime.datetime.fromisoformat(value).astimezone().strftime('%Y-%m-%d %H:%M:%S')


class HistoryPage(Page):
    page_name = 'history'
    page_title = _("History")
    page_icon = 'document-open-recent-symbolic'
    page_size = 50

    def __init__(self, ctx):
        super().__init__(ctx)
        self.offset = 0
        self._loading = False
        self.entries = []
        self._request = 0
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(18)
        card, body = widgets.card(_("Operation history"),
            _("Actions performed by MintTweaks on this account. Command output and passwords are not copied here. Dates use your local time zone."))
        self.summary = widgets.label("", wrap=True)
        body.pack_start(self.summary, False, False, 0)
        self.filter = Gtk.ComboBoxText()
        self.filter.append('all', _("All results"))
        for status in STATUSES:
            self.filter.append(status, status_label(status))
        self.filter.set_active_id('all')
        self.filter.connect('changed', lambda _combo: self._filter_changed())
        body.pack_start(widgets.row(widgets.label(_("Result")), self.filter), False, False, 0)
        body.pack_start(widgets.label(_("Completed means the operation returned without a reported failure. It does not prove that the application or service works correctly. Restore configurations from their original module after reviewing its preview."), wrap=True), False, False, 0)
        box.pack_start(card, False, False, 0)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(self.rows, False, False, 0)
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.previous = widgets.button(_("Newer operations"), lambda: self._move(-self.page_size))
        self.next = widgets.button(_("Older operations"), lambda: self._move(self.page_size))
        self.reload = widgets.button(_("Refresh history"), self.refresh)
        for button in (self.previous, self.next, self.reload):
            controls.pack_start(button, False, False, 0)
        box.pack_start(controls, False, False, 0)
        self.pack_start(widgets.scrolled(box), True, True, 0)
        self._controls()
        self.ctx.add_operation_sink(self._operation_changed)

    def _controls(self):
        self.previous.set_sensitive(not self._loading and self.offset > 0)
        self.next.set_sensitive(not self._loading and len(self.entries) > self.page_size)
        self.reload.set_sensitive(not self._loading)

    def _operation_changed(self, _name):
        if self._loaded:
            self.refresh()

    def _filter_changed(self):
        self.offset = 0
        self.refresh()

    def _move(self, step):
        if not self._loading:
            self.offset = max(0, self.offset + step)
            self.refresh()

    def refresh(self):
        # Generation avoids stale async results when the filter changes.
        self._request += 1
        request = self._request
        self._loading = True
        self._controls()
        status = self.filter.get_active_id()
        status = status if status in STATUSES else None
        store = self.ctx.history
        offset = self.offset
        self.ctx.run_async(
            lambda: store.entries(status=status, limit=self.page_size + 1, offset=offset) if store else [],
            on_done=lambda entries: self._apply(entries, request),
            on_error=lambda exc: self._failed(exc, request))

    def _apply(self, entries, request):
        if request != self._request:
            return
        self._loading = False
        self.entries = entries
        for child in self.rows.get_children():
            self.rows.remove(child)
        warning = self.ctx.history_warning
        text = (_("No operation recorded for this filter.") if not entries else
                _("Operations {first}–{last}, newest first.").format(first=self.offset + 1, last=self.offset + min(len(entries), self.page_size)))
        if self.ctx.runner.dry_run:
            text += '\n' + _("Simulation history is separate from real operations.")
        if warning:
            text += '\n' + warning
        self.summary.set_text(text)
        try:
            for entry in entries[:self.page_size]:
                heading = local_time(entry['started']) + ' · ' + entry['name'] + ' · ' + status_label(entry['status'])
                expander = Gtk.Expander(label=heading)
                body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                body.set_border_width(8)
                body.pack_start(widgets.label(_("Module: {module}").format(module=entry['module']), selectable=True), False, False, 0)
                if entry['finished']:
                    body.pack_start(widgets.label(_("Finished: {time}").format(time=local_time(entry['finished']))), False, False, 0)
                if entry['simulated']:
                    body.pack_start(widgets.label(_("Simulation: no real system operation.")), False, False, 0)
                body.pack_start(widgets.title(_("Associated backups")), False, False, 0)
                for path in entry['backups']:
                    body.pack_start(widgets.label(path, wrap=True, selectable=True), False, False, 0)
                if not entry['backups']:
                    body.pack_start(widgets.label(_("No backup reference recorded. This does not indicate whether a backup exists elsewhere."), wrap=True), False, False, 0)
                body.pack_start(widgets.button(_("Open the original module"), lambda key=entry['module']: self._open_module(key)), False, False, 0)
                expander.add(body)
                self.rows.pack_start(expander, False, False, 0)
        except (ValueError, TypeError, KeyError):
            self._failed(None, request)
            return
        self.rows.show_all()
        self._controls()

    def _failed(self, _exc, request):
        if request != self._request:
            return
        self._loading = False
        self.entries = []
        for child in self.rows.get_children():
            self.rows.remove(child)
        self.summary.set_text(_("History could not be read. No history file was replaced. Previously displayed results have been cleared."))
        self._controls()

    def _open_module(self, name):
        window = self.get_toplevel()
        show_page = getattr(window, 'show_page', None)
        if callable(show_page):
            show_page(name)
