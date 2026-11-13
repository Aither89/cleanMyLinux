"""Page « Maintenance » : tâches d'entretien ponctuelles avec journal de sortie."""
import os
import subprocess

from gi.repository import Adw, Gtk

from ..util import in_thread, ui, which
from ..widgets import confirm, content_box, page_header, scrolled_clamp

TASKS = [
    ("Libérer la mémoire cache", "Vide les caches du noyau (page cache, dentries, inodes). Sans danger.",
     "drive-harddisk-symbolic", "sync && echo 3 > /proc/sys/vm/drop_caches && free -h", True, False),
    ("Optimiser les SSD (TRIM)", "Exécute fstrim sur tous les systèmes de fichiers qui le supportent.",
     "media-flash-symbolic", "fstrim -av", True, False),
    ("Mettre à jour la liste des paquets", "apt-get update", "view-refresh-symbolic",
     "apt-get update", True, False),
    ("Installer les mises à jour", "apt-get upgrade : met à jour tous les paquets installés.",
     "software-update-available-symbolic", "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y", True, True),
    ("Réparer les paquets cassés", "dpkg --configure -a puis apt-get --fix-broken install.",
     "emblem-system-symbolic", "dpkg --configure -a && DEBIAN_FRONTEND=noninteractive apt-get --fix-broken install -y", True, False),
    ("Supprimer les anciens noyaux", "Désinstalle les noyaux qui ne sont plus utilisés (apt autoremove).",
     "package-x-generic-symbolic", "DEBIAN_FRONTEND=noninteractive apt-get autoremove --purge -y", True, True),
    ("Vider le cache DNS", "resolvectl flush-caches", "network-workgroup-symbolic",
     "resolvectl flush-caches && echo 'Cache DNS vidé.'", True, False),
    ("Reconstruire le cache des polices", "fc-cache -f : utile si des polices n'apparaissent pas.",
     "font-x-generic-symbolic", "fc-cache -f -v | tail -n 3", False, False),
    ("Mettre à jour la base des applications", "update-desktop-database sur vos lanceurs personnels.",
     "view-app-grid-symbolic", "update-desktop-database ~/.local/share/applications && echo 'Base mise à jour.'", False, False),
    ("Réindexer les fichiers (Tracker)", "Réinitialise l'index de recherche GNOME ; la réindexation se fait en arrière-plan.",
     "edit-find-symbolic", "tracker3 reset -s -r 2>/dev/null || localsearch3 reset -s -r; echo 'Index réinitialisé.'", False, True),
    ("Vérifier la santé des disques (SMART)", "Résumé SMART de chaque disque (nécessite smartmontools).",
     "dialog-information-symbolic",
     "for d in /dev/sd? /dev/nvme?n1; do [ -e \"$d\" ] && { echo \"== $d\"; smartctl -H \"$d\" | tail -n +5; }; done", True, False),
]


class MaintenancePage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.running = False
        box = content_box()
        box.append(page_header("Maintenance", "Tâches d'entretien pour garder un système rapide et sain."))
        group = Adw.PreferencesGroup()
        self.buttons = []
        for title, desc, icon, cmd, root, ask in TASKS:
            row = Adw.ActionRow(title=title, subtitle=desc)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            if root:
                lock = Gtk.Image.new_from_icon_name("system-lock-screen-symbolic")
                lock.set_tooltip_text("Nécessite les droits administrateur")
                lock.add_css_class("dim-label")
                row.add_suffix(lock)
            btn = Gtk.Button(label="Exécuter", valign=Gtk.Align.CENTER)
            btn.add_css_class("flat")
            btn.connect("clicked", lambda _b, t=title, c=cmd, r=root, a=ask: self.run_task(t, c, r, a))
            row.add_suffix(btn)
            self.buttons.append(btn)
            group.add(row)
        box.append(group)

        out_group = Adw.PreferencesGroup(title="Journal")
        self.view = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        for side in ("top", "bottom", "left", "right"):
            getattr(self.view, f"set_{side}_margin")(10)
        sw = Gtk.ScrolledWindow(min_content_height=220)
        sw.add_css_class("card")
        sw.set_child(self.view)
        out_group.add(sw)
        box.append(out_group)
        self.append(scrolled_clamp(box))

    def log(self, text):
        buf = self.view.get_buffer()
        buf.insert(buf.get_end_iter(), text)
        self.view.scroll_to_mark(buf.get_insert(), 0, False, 0, 0)

    def run_task(self, title, cmd, root, ask):
        if self.running:
            return
        if ask:
            confirm(self.window, f"{title} ?", "Cette opération modifie le système. Continuer ?", "Exécuter",
                    lambda: self._start(title, cmd, root), destructive=False)
        else:
            self._start(title, cmd, root)

    def _start(self, title, cmd, root):
        self.running = True
        for b in self.buttons:
            b.set_sensitive(False)
        self.log(f"\n▶ {title}\n")
        argv = ["pkexec", "/bin/sh", "-c", cmd] if root else ["/bin/sh", "-c", cmd]

        def work():
            env = dict(os.environ, LC_ALL="C.UTF-8")
            try:
                p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
                for line in p.stdout:
                    ui(self.log, line)
                rc = p.wait()
            except Exception as e:
                ui(self.log, f"Erreur : {e}\n")
                rc = 1
            ui(self._finished, title, rc)
        in_thread(work)

    def _finished(self, title, rc):
        self.running = False
        for b in self.buttons:
            b.set_sensitive(True)
        if rc == 0:
            self.log("✔ Terminé.\n")
            self.window.toast(f"{title} : terminé")
        elif rc in (126, 127):
            self.log("✖ Authentification annulée.\n")
        else:
            self.log(f"✖ Échec (code {rc}).\n")
            self.window.toast(f"{title} : échec (code {rc})")
        self.window.dashboard.refresh()
