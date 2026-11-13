"""Fenêtre principale et application GTK4/libadwaita."""
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__  # noqa: E402
from .pages.dashboard import DashboardPage  # noqa: E402
from .pages.duplicates import DuplicatesPage  # noqa: E402
from .pages.junk import JunkPage  # noqa: E402
from .pages.largefiles import LargeFilesPage  # noqa: E402
from .pages.maintenance import MaintenancePage  # noqa: E402
from .pages.startup import StartupPage  # noqa: E402
from .pages.uninstaller import UninstallerPage  # noqa: E402

PAGES = [
    ("dashboard", "Tableau de bord", "user-home-symbolic"),
    ("junk", "Nettoyage", "edit-clear-all-symbolic"),
    ("large", "Gros fichiers", "drive-harddisk-symbolic"),
    ("duplicates", "Doublons", "edit-copy-symbolic"),
    ("apps", "Applications", "view-app-grid-symbolic"),
    ("startup", "Démarrage", "media-playback-start-symbolic"),
    ("maintenance", "Maintenance", "emblem-system-symbolic"),
]

CSS = """
.sidebar-row { padding: 8px 10px; }
.card { border-radius: 12px; }
"""


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="CleanMyLinux", default_width=1120, default_height=760)
        self.set_size_request(760, 520)
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        split = Adw.NavigationSplitView(min_sidebar_width=200, max_sidebar_width=240)
        self.toast_overlay.set_child(split)

        # --- Barre latérale
        sidebar_box = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="CleanMyLinux"))
        menu = Gio.Menu()
        menu.append("À propos", "app.about")
        menu.append("Quitter", "app.quit")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)
        sidebar_box.add_top_bar(header)
        self.nav = Gtk.ListBox()
        self.nav.add_css_class("navigation-sidebar")
        for key, label, icon in PAGES:
            row = Gtk.ListBoxRow()
            row.key = key
            hb = Gtk.Box(spacing=12)
            hb.add_css_class("sidebar-row")
            hb.append(Gtk.Image.new_from_icon_name(icon))
            hb.append(Gtk.Label(label=label, xalign=0))
            row.set_child(hb)
            self.nav.append(row)
        self.nav.connect("row-selected", self._on_nav)
        sidebar_box.set_content(self.nav)
        split.set_sidebar(Adw.NavigationPage(title="Menu", child=sidebar_box))

        # --- Contenu
        content = Adw.ToolbarView()
        content.add_top_bar(Adw.HeaderBar(show_title=False))
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        content.set_content(self.stack)
        split.set_content(Adw.NavigationPage(title="CleanMyLinux", child=content))

        self.dashboard = DashboardPage(self)
        self.junk_page = JunkPage(self)
        self.pages = {
            "dashboard": self.dashboard, "junk": self.junk_page, "large": LargeFilesPage(self),
            "duplicates": DuplicatesPage(self), "apps": UninstallerPage(self),
            "startup": StartupPage(self), "maintenance": MaintenancePage(self),
        }
        for key, page in self.pages.items():
            self.stack.add_named(page, key)
        self.nav.select_row(self.nav.get_row_at_index(0))

    def _on_nav(self, _lb, row):
        if row:
            self.stack.set_visible_child_name(row.key)
            page = self.pages[row.key]
            if hasattr(page, "on_show"):
                page.on_show()

    def show_page(self, key):
        for i, (k, _l, _i) in enumerate(PAGES):
            if k == key:
                self.nav.select_row(self.nav.get_row_at_index(i))

    def toast(self, text, timeout=4):
        self.toast_overlay.add_toast(Adw.Toast(title=text, timeout=timeout))


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self.on_activate)
        for name, cb, accel in (("quit", lambda *_: self.quit(), "<Primary>q"), ("about", self.on_about, None)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            if accel:
                self.set_accels_for_action(f"app.{name}", [accel])

    def on_activate(self, *_):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        win = self.props.active_window or MainWindow(self)
        win.present()

    def on_about(self, *_):
        about = Adw.AboutDialog(application_name="CleanMyLinux", application_icon="edit-clear-all-symbolic",
                                version=__version__, developer_name="Sébastien",
                                comments="Nettoyeur et optimiseur système pour Linux, inspiré de CleanMyMac.",
                                license_type=Gtk.License.MIT_X11)
        about.present(self.props.active_window)


def main():
    GLib.set_prgname("cleanmylinux")
    GLib.set_application_name("CleanMyLinux")
    app = App()
    return app.run(sys.argv)
