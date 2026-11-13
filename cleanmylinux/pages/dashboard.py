"""Tableau de bord : vue d'ensemble disque / mémoire / CPU et analyse intelligente."""
import getpass
import os

from gi.repository import Adw, GLib, Gtk

from .. import sysinfo
from ..scanners import scan_all
from ..util import human, in_thread, ui
from ..widgets import Gauge, ProgressRow, content_box, scrolled_clamp


class DashboardPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        box = content_box()

        # En-tête de bienvenue
        try:
            import pwd
            name = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0].strip() or getpass.getuser().capitalize()
        except Exception:
            name = getpass.getuser().capitalize()
        title = Gtk.Label(label=f"Bonjour {name}", xalign=0)
        title.add_css_class("title-1")
        box.append(title)
        self.sub = Gtk.Label(label=sysinfo.pretty_name(), xalign=0)
        self.sub.add_css_class("dim-label")
        box.append(self.sub)

        # Jauges
        gauges = Gtk.Box(spacing=24, halign=Gtk.Align.CENTER)
        gauges.add_css_class("card")
        gauges.set_margin_top(6)
        for side in ("top", "bottom", "start", "end"):
            getattr(gauges, f"set_margin_{side}")(0)
        self.gauge_disk = Gauge("Disque")
        self.gauge_mem = Gauge("Mémoire")
        self.gauge_cpu = Gauge("Processeur")
        for g in (self.gauge_disk, self.gauge_mem, self.gauge_cpu):
            g.set_margin_top(18)
            g.set_margin_bottom(18)
            gauges.append(g)
        self.gauge_disk.set_margin_start(24)
        self.gauge_cpu.set_margin_end(24)
        box.append(gauges)

        # Carte « Analyse intelligente »
        smart = Adw.PreferencesGroup(title="Analyse intelligente")
        self.smart_row = Adw.ActionRow(title="Rechercher les fichiers inutiles",
                                       subtitle="Caches, journaux, corbeille, paquets orphelins…")
        self.smart_row.add_prefix(Gtk.Image.new_from_icon_name("edit-find-symbolic"))
        self.smart_btn = Gtk.Button(label="Analyser", valign=Gtk.Align.CENTER)
        self.smart_btn.add_css_class("suggested-action")
        self.smart_btn.add_css_class("pill")
        self.smart_btn.connect("clicked", self.on_smart_scan)
        self.smart_row.add_suffix(self.smart_btn)
        smart.add(self.smart_row)
        self.result_row = Adw.ActionRow(title="", visible=False)
        self.result_row.add_prefix(Gtk.Image.new_from_icon_name("emblem-ok-symbolic"))
        self.clean_btn = Gtk.Button(label="Voir et nettoyer", valign=Gtk.Align.CENTER)
        self.clean_btn.add_css_class("destructive-action")
        self.clean_btn.add_css_class("pill")
        self.clean_btn.connect("clicked", lambda *_: self.window.show_page("junk"))
        self.result_row.add_suffix(self.clean_btn)
        smart.add(self.result_row)
        box.append(smart)
        self.progress = ProgressRow()
        box.append(self.progress)

        # Détails disques
        self.disk_group = Adw.PreferencesGroup(title="Stockage")
        box.append(self.disk_group)
        self.disk_rows = []

        # Système
        self.sys_group = Adw.PreferencesGroup(title="Système")
        self.row_mem = Adw.ActionRow(title="Mémoire vive")
        self.row_swap = Adw.ActionRow(title="Espace d'échange (swap)")
        self.row_cpu = Adw.ActionRow(title="Charge CPU")
        self.row_uptime = Adw.ActionRow(title="Allumé depuis")
        self.row_top = Adw.ActionRow(title="Processus les plus gourmands")
        for r in (self.row_mem, self.row_swap, self.row_cpu, self.row_uptime, self.row_top):
            r.add_css_class("property")
            self.sys_group.add(r)
        box.append(self.sys_group)

        self.append(scrolled_clamp(box))
        self.refresh()
        GLib.timeout_add_seconds(3, self._tick)

    # ------------------------------------------------------------------
    def _tick(self):
        self.refresh()
        return True

    def refresh(self):
        disks = sysinfo.disks()
        if disks:
            d = disks[0]
            self.gauge_disk.update(d["percent"], f"{human(d['free'])} libres")
        mem = sysinfo.memory()
        self.gauge_mem.update(mem["percent"], f"{human(mem['available'])} dispo")
        c = sysinfo.cpu()
        self.gauge_cpu.update(c["percent"], f"{c['count']} cœurs", color=(0.21, 0.52, 0.89))

        # Lignes disques (recréées si le nombre change)
        if len(self.disk_rows) != len(disks):
            for r in self.disk_rows:
                self.disk_group.remove(r)
            self.disk_rows = []
            for d in disks:
                row = Adw.ActionRow(title=d["mount"])
                row.add_prefix(Gtk.Image.new_from_icon_name("drive-harddisk-symbolic"))
                bar = Gtk.LevelBar(min_value=0, max_value=100, valign=Gtk.Align.CENTER)
                bar.set_size_request(160, -1)
                bar.add_offset_value("low", 70)
                bar.add_offset_value("high", 90)
                bar.add_offset_value("full", 100)
                row.add_suffix(bar)
                row.bar = bar
                self.disk_group.add(row)
                self.disk_rows.append(row)
        for row, d in zip(self.disk_rows, disks):
            row.set_subtitle(f"{d['device']} · {d['fstype']} · {human(d['used'])} utilisés sur {human(d['total'])}")
            row.bar.set_value(d["percent"])

        self.row_mem.set_subtitle(f"{human(mem['used'])} utilisés sur {human(mem['total'])} "
                                  f"(dont {human(mem['cached'])} de cache)")
        self.row_swap.set_subtitle(f"{human(mem['swap_used'])} sur {human(mem['swap_total'])}"
                                   if mem["swap_total"] else "Aucun")
        self.row_cpu.set_subtitle("Charge moyenne : " + " / ".join(f"{x:.2f}" for x in c["load"]))
        self.row_uptime.set_subtitle(sysinfo.uptime())
        self.row_top.set_subtitle(", ".join(f"{n} ({human(s)})" for s, n in sysinfo.top_processes(4)))

    # ------------------------------------------------------------------
    def on_smart_scan(self, *_):
        self.smart_btn.set_sensitive(False)
        self.result_row.set_visible(False)
        self.progress.start("Analyse en cours…")
        in_thread(self._scan)

    def _scan(self):
        cats = scan_all(lambda m: ui(self.progress.message, m))
        ui(self._done, cats)

    def _done(self, cats):
        self.progress.stop()
        self.smart_btn.set_sensitive(True)
        self.window.junk_page.set_categories(cats)
        total = sum(c.selected_size() for c in cats)
        count = sum(len(c.items) for c in cats)
        self.result_row.set_title(f"{human(total)} récupérables")
        self.result_row.set_subtitle(f"{count} éléments dans {len(cats)} catégories "
                                     f"({human(sum(c.total_size() for c in cats))} au total)")
        self.result_row.set_visible(True)
