"""Page « Gros fichiers » : recherche des fichiers volumineux, envoi à la corbeille."""
import os
import time

from gi.repository import Adw, Gio, Gtk

from ..scanners import find_large_files
from ..util import HOME, human, in_thread, open_in_file_manager, trash_path, ui
from ..widgets import ProgressRow, confirm, content_box, icon_button, page_header, scrolled_clamp

SIZES = [("50 Mo", 50), ("100 Mo", 100), ("250 Mo", 250), ("500 Mo", 500), ("1 Go", 1024), ("5 Go", 5120)]


class LargeFilesPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.folder = HOME
        self.results = []   # (size, mtime, path)
        self.checks = []    # (path, size, CheckButton)
        box = content_box()
        box.append(page_header("Gros fichiers", "Retrouvez les fichiers qui occupent le plus de place."))

        bar = Gtk.Box(spacing=12)
        self.folder_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        self._folder_content = Adw.ButtonContent(icon_name="folder-symbolic", label=self._short(self.folder))
        self.folder_btn.set_child(self._folder_content)
        self.folder_btn.connect("clicked", self.choose_folder)
        bar.append(self.folder_btn)
        self.size_dd = Gtk.DropDown.new_from_strings([s[0] for s in SIZES])
        self.size_dd.set_selected(1)
        self.size_dd.set_valign(Gtk.Align.CENTER)
        bar.append(Gtk.Label(label="Plus de"))
        bar.append(self.size_dd)
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

        self.empty = Adw.StatusPage(icon_name="drive-harddisk-symbolic", title="Aucune analyse",
                                    description="Choisissez un dossier et une taille minimale, puis analysez.",
                                    vexpand=True)
        box.append(self.empty)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.list.set_visible(False)
        box.append(self.list)
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
        min_mb = SIZES[self.size_dd.get_selected()][1]
        self.scan_btn.set_sensitive(False)
        self.progress.start()
        in_thread(lambda: ui(self._show, find_large_files(self.folder, min_mb * 1024 ** 2,
                                                          lambda m: ui(self.progress.message, m))))

    def _clear(self):
        child = self.list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        self.checks = []

    def _show(self, results):
        self.progress.stop()
        self.scan_btn.set_sensitive(True)
        self.results = results
        self._clear()
        self.empty.set_visible(not results)
        self.list.set_visible(bool(results))
        if not results:
            self.empty.set_title("Aucun fichier trouvé")
            self.empty.set_description("Aucun fichier ne dépasse la taille choisie dans ce dossier.")
        for size, mtime, path in results:
            row = Adw.ActionRow(title=os.path.basename(path).replace("&", "&amp;"),
                                subtitle=f"{self._short(os.path.dirname(path))} · "
                                         f"modifié le {time.strftime('%d/%m/%Y', time.localtime(mtime))}")
            row.set_title_lines(1)
            row.set_subtitle_lines(1)
            c = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            c.connect("toggled", lambda *_: self._update_total())
            row.add_prefix(c)
            row.set_activatable_widget(c)
            lbl = Gtk.Label(label=human(size), valign=Gtk.Align.CENTER)
            lbl.add_css_class("numeric")
            row.add_suffix(lbl)
            b = icon_button("folder-open-symbolic", "Afficher dans le dossier", "flat")
            b.connect("clicked", lambda _b, p=path: open_in_file_manager(self.window, p))
            row.add_suffix(b)
            self.list.append(row)
            self.checks.append((path, size, c))
        self._update_total()

    def _update_total(self):
        sel = [(p, s) for p, s, c in self.checks if c.get_active()]
        total_all = sum(s for s, _, _ in self.results)
        self.total_label.set_text(f"{len(self.results)} fichiers · {human(total_all)}"
                                  + (f" · {len(sel)} sélectionnés ({human(sum(s for _, s in sel))})" if sel else ""))
        self.trash_btn.set_sensitive(bool(sel))

    def on_trash(self, *_):
        sel = [(p, s, c) for p, s, c in self.checks if c.get_active()]
        confirm(self.window, "Mettre à la corbeille ?",
                f"{len(sel)} fichier(s) ({human(sum(s for _, s, _ in sel))}) seront déplacés vers la corbeille. "
                "Vous pourrez les restaurer depuis la corbeille.",
                "Mettre à la corbeille", lambda: self._do_trash(sel))

    def _do_trash(self, sel):
        errors, freed = 0, 0
        for path, size, c in sel:
            try:
                trash_path(path)
                freed += size
                row = c.get_parent()
                while row and not isinstance(row, Gtk.ListBoxRow):
                    row = row.get_parent()
                if row:
                    self.list.remove(row)
                self.checks = [x for x in self.checks if x[0] != path]
                self.results = [r for r in self.results if r[2] != path]
            except Exception:
                errors += 1
        self._update_total()
        self.window.toast(f"{human(freed)} déplacés vers la corbeille" + (f" ({errors} erreurs)" if errors else ""))
