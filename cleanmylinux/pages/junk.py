"""Page « Nettoyage » : catégories de fichiers inutiles avec cases à cocher."""
from gi.repository import Adw, Gtk

from ..cleaner import clean
from ..scanners import scan_all
from ..util import human, in_thread, ui
from ..widgets import ProgressRow, confirm, content_box, page_header, scrolled_clamp

MAX_ROWS = 120  # lignes affichées par catégorie (le reste est résumé)


class JunkPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.categories = []
        box = content_box()
        box.append(page_header("Nettoyage système",
                               "Supprimez caches, journaux, fichiers temporaires et paquets inutiles."))

        # Barre d'actions
        bar = Gtk.Box(spacing=12)
        self.scan_btn = Gtk.Button(label="Analyser")
        self.scan_btn.add_css_class("suggested-action")
        self.scan_btn.add_css_class("pill")
        self.scan_btn.connect("clicked", self.on_scan)
        bar.append(self.scan_btn)
        self.total_label = Gtk.Label(label="", hexpand=True, xalign=0)
        self.total_label.add_css_class("title-3")
        bar.append(self.total_label)
        self.clean_btn = Gtk.Button(label="Nettoyer la sélection", sensitive=False)
        self.clean_btn.add_css_class("destructive-action")
        self.clean_btn.add_css_class("pill")
        self.clean_btn.connect("clicked", self.on_clean)
        bar.append(self.clean_btn)
        box.append(bar)
        self.progress = ProgressRow()
        box.append(self.progress)

        self.empty = Adw.StatusPage(icon_name="edit-clear-all-symbolic", title="Prêt à nettoyer",
                                    description="Cliquez sur « Analyser » pour rechercher les fichiers inutiles.",
                                    vexpand=True)
        box.append(self.empty)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.append(self.list_box)
        self.append(scrolled_clamp(box))

    # ------------------------------------------------------------------
    def on_scan(self, *_):
        self.scan_btn.set_sensitive(False)
        self.clean_btn.set_sensitive(False)
        self.progress.start()
        in_thread(lambda: ui(self.set_categories, scan_all(lambda m: ui(self.progress.message, m))))

    def set_categories(self, cats):
        self.progress.stop()
        self.scan_btn.set_sensitive(True)
        self.categories = cats
        self._rebuild()

    def _clear_list(self):
        child = self.list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list_box.remove(child)
            child = nxt

    def _rebuild(self):
        self._clear_list()
        self.empty.set_visible(not self.categories)
        for cat in self.categories:
            self.list_box.append(self._build_category(cat))
        self._update_total()

    def _build_category(self, cat):
        group = Adw.PreferencesGroup()
        exp = Adw.ExpanderRow(title=cat.title, subtitle=cat.subtitle)
        exp.add_prefix(Gtk.Image.new_from_icon_name(cat.icon))
        check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
        exp.add_prefix(check)
        size_label = Gtk.Label(valign=Gtk.Align.CENTER)
        size_label.add_css_class("numeric")
        exp.add_suffix(size_label)
        if cat.root:
            lock = Gtk.Image.new_from_icon_name("system-lock-screen-symbolic")
            lock.set_tooltip_text("Nécessite les droits administrateur")
            lock.add_css_class("dim-label")
            exp.add_suffix(lock)
        cat._size_label = size_label
        cat._check = check
        item_checks = []

        def sync_header():
            n = len(cat.selected_items())
            check.handler_block(check._hid)
            check.set_active(n == len(cat.items) and n > 0)
            check.set_inconsistent(0 < n < len(cat.items))
            check.handler_unblock(check._hid)
            size_label.set_text(f"{human(cat.selected_size())} / {human(cat.total_size())}")
            self._update_total()

        def on_header_toggled(btn):
            state = btn.get_active()
            for it in cat.items:
                it.selected = state
            for it, c in item_checks:
                c.handler_block(c._hid)
                c.set_active(state)
                c.handler_unblock(c._hid)
            sync_header()
        check._hid = check.connect("toggled", on_header_toggled)

        if cat.warning:
            warn = Adw.ActionRow(title=cat.warning)
            warn.add_prefix(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
            warn.add_css_class("dim-label")
            exp.add_row(warn)

        for it in cat.items[:MAX_ROWS]:
            row = Adw.ActionRow(title=it.label, subtitle=it.detail or (it.path if not it.path.startswith(
                ("docker:", "apt:", "snap:", "flatpak:", "journal")) else ""))
            row.set_title_lines(1)
            row.set_subtitle_lines(1)
            c = Gtk.CheckButton(active=it.selected, valign=Gtk.Align.CENTER)
            row.add_prefix(c)
            row.set_activatable_widget(c)
            lbl = Gtk.Label(label=human(it.size) if it.size else "—", valign=Gtk.Align.CENTER)
            lbl.add_css_class("dim-label")
            lbl.add_css_class("numeric")
            row.add_suffix(lbl)

            def on_toggle(btn, item=it):
                item.selected = btn.get_active()
                sync_header()
            c._hid = c.connect("toggled", on_toggle)
            item_checks.append((it, c))
            exp.add_row(row)
        if len(cat.items) > MAX_ROWS:
            rest = cat.items[MAX_ROWS:]
            more = Adw.ActionRow(title=f"… et {len(rest)} autres éléments ({human(sum(i.size for i in rest))})",
                                 subtitle="Sélectionnés avec la catégorie")
            exp.add_row(more)
        sync_header()
        exp.set_expanded(False)
        group.add(exp)
        return group

    def _update_total(self):
        total = sum(c.selected_size() for c in self.categories)
        n = sum(len(c.selected_items()) for c in self.categories)
        self.total_label.set_text(f"{human(total)} sélectionnés" if n else "Rien de sélectionné")
        self.clean_btn.set_sensitive(n > 0)

    # ------------------------------------------------------------------
    def on_clean(self, *_):
        total = sum(c.selected_size() for c in self.categories)
        needs_root = any(c.root and c.selected_items() for c in self.categories)
        body = f"Environ {human(total)} vont être libérés. Cette action est définitive."
        if needs_root:
            body += "\n\nLe mot de passe administrateur sera demandé pour les éléments système."
        confirm(self.window, "Nettoyer la sélection ?", body, "Nettoyer", self._do_clean)

    def _do_clean(self):
        self.scan_btn.set_sensitive(False)
        self.clean_btn.set_sensitive(False)
        self.progress.start("Nettoyage…")
        in_thread(lambda: ui(self._cleaned, *clean(self.categories, lambda m: ui(self.progress.message, m))))

    def _cleaned(self, freed, errors):
        self.progress.stop()
        self.scan_btn.set_sensitive(True)
        self._clear_list()
        self.categories = []
        self.total_label.set_text("")
        self.empty.set_icon_name("emblem-ok-symbolic")
        self.empty.set_title(f"{human(freed)} libérés")
        desc = "Le nettoyage est terminé. Relancez une analyse pour vérifier."
        if errors:
            desc += f"\n\n{len(errors)} erreur(s) :\n" + "\n".join(errors[:8])
        self.empty.set_description(desc)
        self.empty.set_visible(True)
        self.window.toast(f"{human(freed)} libérés" + (f" ({len(errors)} erreurs)" if errors else ""))
        self.window.dashboard.refresh()
