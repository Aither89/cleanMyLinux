"""Page « Doublons » : fichiers identiques (contenu) regroupés."""
import os

from gi.repository import Adw, Gio, Gtk

from ..scanners import find_duplicates
from ..util import HOME, human, in_thread, open_in_file_manager, trash_path, ui
from ..widgets import ProgressRow, confirm, content_box, icon_button, page_header, scrolled_clamp


class DuplicatesPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.folder = HOME
        self.checks = []  # (path, size, check)
        box = content_box()
        box.append(page_header("Doublons", "Fichiers strictement identiques (contenu comparé par empreinte SHA-256)."))

        bar = Gtk.Box(spacing=12)
        self.folder_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        self._folder_content = Adw.ButtonContent(icon_name="folder-symbolic", label=self._short(self.folder))
        self.folder_btn.set_child(self._folder_content)
        self.folder_btn.connect("clicked", self.choose_folder)
        bar.append(self.folder_btn)
        self.scan_btn = Gtk.Button(label="Analyser")
        self.scan_btn.add_css_class("suggested-action")
        self.scan_btn.add_css_class("pill")
        self.scan_btn.connect("clicked", self.on_scan)
        bar.append(self.scan_btn)
        self.total_label = Gtk.Label(hexpand=True, xalign=1)
        self.total_label.add_css_class("dim-label")
        bar.append(self.total_label)
        self.trash_btn = Gtk.Button(label="Mettre à la corbeille", sensitive=False)
        self.trash_btn.add_css_class("destructive-action")
        self.trash_btn.add_css_class("pill")
        self.trash_btn.connect("clicked", self.on_trash)
        bar.append(self.trash_btn)
        box.append(bar)
        self.progress = ProgressRow()
        box.append(self.progress)

        self.empty = Adw.StatusPage(icon_name="edit-copy-symbolic", title="Aucune analyse",
                                    description="Les fichiers de plus de 1 Mo sont comparés. "
                                                "Dans chaque groupe, le premier fichier est conservé par défaut.",
                                    vexpand=True)
        box.append(self.empty)
        self.groups_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.append(self.groups_box)
        self.append(scrolled_clamp(box, 1000))

    @staticmethod
    def _short(path):
        return path.replace(HOME, "~") if path.startswith(HOME) else path

    def choose_folder(self, *_):
        dlg = Gtk.FileDialog(title="Dossier à analyser", modal=True)
        dlg.set_initial_folder(Gio.File.new_for_path(self.folder))

        def done(d, res):
            try:
                f = d.select_folder_finish(res)
            except Exception:
                return
            if f:
                self.folder = f.get_path()
                self._folder_content.set_label(self._short(self.folder))
        dlg.select_folder(self.window, None, done)

    def on_scan(self, *_):
        self.scan_btn.set_sensitive(False)
        self.progress.start()
        in_thread(lambda: ui(self._show, find_duplicates(self.folder, progress=lambda m: ui(self.progress.message, m))))

    def _clear(self):
        child = self.groups_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.groups_box.remove(child)
            child = nxt
        self.checks = []

    def _show(self, groups):
        self.progress.stop()
        self.scan_btn.set_sensitive(True)
        self._clear()
        groups = groups[:200]
        self.empty.set_visible(not groups)
        if not groups:
            self.empty.set_title("Aucun doublon")
            self.empty.set_description("Aucun fichier en double de plus de 1 Mo dans ce dossier.")
        for size, paths in groups:
            group = Adw.PreferencesGroup(title=os.path.basename(paths[0]),
                                         description=f"{len(paths)} copies · {human(size)} chacune · "
                                                     f"{human(size * (len(paths) - 1))} récupérables")
            for i, p in enumerate(paths):
                row = Adw.ActionRow(title=self._short(p))
                row.set_title_lines(1)
                c = Gtk.CheckButton(active=i > 0, valign=Gtk.Align.CENTER)
                c.connect("toggled", lambda *_: self._update_total())
                row.add_prefix(c)
                row.set_activatable_widget(c)
                b = icon_button("folder-open-symbolic", "Afficher dans le dossier", "flat")
                b.connect("clicked", lambda _b, path=p: open_in_file_manager(self.window, path))
                row.add_suffix(b)
                group.add(row)
                self.checks.append((p, size, c))
            self.groups_box.append(group)
        self._update_total()

    def _update_total(self):
        sel = [(p, s) for p, s, c in self.checks if c.get_active()]
        self.total_label.set_text(f"{len(sel)} fichiers sélectionnés · {human(sum(s for _, s in sel))}" if sel else "")
        self.trash_btn.set_sensitive(bool(sel))

    def on_trash(self, *_):
        sel = [(p, s, c) for p, s, c in self.checks if c.get_active()]
        confirm(self.window, "Mettre les doublons à la corbeille ?",
                f"{len(sel)} fichier(s) ({human(sum(s for _, s, _ in sel))}) seront déplacés vers la corbeille.",
                "Mettre à la corbeille", lambda: self._do_trash(sel))

    def _do_trash(self, sel):
        freed, errors = 0, 0
        for path, size, c in sel:
            try:
                trash_path(path)
                freed += size
                c.set_sensitive(False)
                c.set_active(False)
                c.get_parent().get_parent().set_sensitive(False) if c.get_parent() else None
            except Exception:
                errors += 1
        self.checks = [x for x in self.checks if x[2].get_sensitive()]
        self._update_total()
        self.window.toast(f"{human(freed)} déplacés vers la corbeille" + (f" ({errors} erreurs)" if errors else ""))
