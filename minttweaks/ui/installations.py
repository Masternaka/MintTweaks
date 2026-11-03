"""Compact, selectable installation information shared by software catalogs."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from ..i18n import _
from . import widgets


class InstallationDetails(Gtk.Expander):
    def __init__(self, rows):
        super().__init__(label=_("Installation details"))
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.body.set_border_width(8)
        self.add(self.body)
        self.update(rows)

    def update(self, rows):
        self.rows = tuple(rows)
        for child in self.body.get_children():
            self.body.remove(child)
        for title, value in self.rows:
            self.body.pack_start(widgets.label(title + ': ' + value, wrap=True, selectable=True), False, False, 0)
        self.body.show_all()
