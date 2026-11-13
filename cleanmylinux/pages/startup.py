"""Page « Démarrage » : applications lancées à l'ouverture de session et services utilisateur."""
import configparser
import glob
import os

from gi.repository import Adw, Gtk

from ..util import HOME, in_thread, run, ui
from ..widgets import ProgressRow, content_box, page_header, scrolled_clamp

USER_AUTOSTART = os.path.join(HOME, ".config", "autostart")


def _read_desktop(path):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    try:
        cp.read(path, encoding="utf-8")
        sec = cp["Desktop Entry"]
    except Exception:
        return None
    enabled = sec.get("Hidden", "false").lower() != "true" and sec.get("X-GNOME-Autostart-enabled", "true").lower() != "false"
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "GNOME").split(":")
    only = [x for x in sec.get("OnlyShowIn", "").split(";") if x]
    notin = [x for x in sec.get("NotShowIn", "").split(";") if x]
    if (only and not any(d in only for d in desktop)) or any(d in notin for d in desktop):
        return None  # ne se lance pas dans ce bureau
    return {"internal": sec.get("NoDisplay", "false").lower() == "true","name": sec.get("Name[fr]", sec.get("Name", os.path.basename(path))),
            "comment": sec.get("Comment[fr]", sec.get("Comment", sec.get("Exec", ""))),
            "icon": sec.get("Icon", "application-x-executable"), "enabled": enabled, "path": path}


def list_autostart():
    entries = {}
    for d in ("/etc/xdg/autostart", USER_AUTOSTART):
        for f in sorted(glob.glob(os.path.join(d, "*.desktop"))):
            info = _read_desktop(f)
            if info:
                info["system"] = d.startswith("/etc")
                entries[os.path.basename(f)] = info  # le fichier utilisateur remplace le système
    return sorted(entries.values(), key=lambda e: e["name"].lower())


def set_autostart(entry, enabled):
    """Active/désactive une entrée : on écrit toujours dans ~/.config/autostart."""
    os.makedirs(USER_AUTOSTART, exist_ok=True)
    target = os.path.join(USER_AUTOSTART, os.path.basename(entry["path"]))
    with open(entry["path"], encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if not l.startswith(("Hidden=", "X-GNOME-Autostart-enabled="))]
    if not enabled:
        lines.append("X-GNOME-Autostart-enabled=false")
        lines.append("Hidden=true")
    with open(target, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def list_user_services():
    rc, out, _ = run(["systemctl", "--user", "list-unit-files", "--type=service", "--no-legend", "--no-pager"], timeout=30)
    services = []
    for line in out.splitlines():
        cols = line.split()
        if len(cols) >= 2 and cols[1] in ("enabled", "disabled") and not cols[0].endswith("@.service"):
            services.append({"name": cols[0], "enabled": cols[1] == "enabled"})
    return services


class StartupPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.loaded = False
        box = content_box()
        box.append(page_header("Démarrage", "Contrôlez ce qui se lance à l'ouverture de votre session."))
        self.progress = ProgressRow()
        box.append(self.progress)
        self.auto_group = Adw.PreferencesGroup(title="Applications au démarrage",
                                               description="Entrées d'autostart (système et utilisateur)")
        box.append(self.auto_group)
        self.internal_group = Adw.PreferencesGroup(title="Composants du bureau",
                                                   description="Services internes de GNOME : à ne désactiver que si vous savez ce que vous faites")
        self.internal_exp = Adw.ExpanderRow(title="Afficher les composants système", subtitle="Avancé")
        self.internal_exp.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        self.internal_group.add(self.internal_exp)
        box.append(self.internal_group)
        self.svc_group = Adw.PreferencesGroup(title="Services utilisateur (systemd --user)",
                                              description="Services activés dans votre session")
        box.append(self.svc_group)
        self.append(scrolled_clamp(box))
        self._rows = []

    def on_show(self):
        if not self.loaded:
            self.load()

    def load(self):
        self.loaded = True
        self.progress.start("Lecture des entrées de démarrage…")
        in_thread(lambda: ui(self._show, list_autostart(), list_user_services()))

    def _show(self, entries, services):
        self.progress.stop()
        for group, rows in self._rows:
            for r in rows:
                group.remove(r)
        self._rows = []
        auto_rows, svc_rows, internal_rows = [], [], []
        for e in entries:
            row = Adw.SwitchRow(title=e["name"].replace("&", "&amp;"),
                                subtitle=(e["comment"] + (" · système" if e["system"] else "")).replace("&", "&amp;"))
            row.set_subtitle_lines(1)
            row.add_prefix(Gtk.Image.new_from_icon_name(e["icon"] if not e["icon"].startswith("/") else "application-x-executable"))
            row.set_active(e["enabled"])
            row.connect("notify::active", lambda r, _p, entry=e: self._toggle_autostart(r, entry))
            if e["internal"]:
                self.internal_exp.add_row(row)
                internal_rows.append(row)
            else:
                self.auto_group.add(row)
                auto_rows.append(row)
        if not auto_rows:
            r = Adw.ActionRow(title="Aucune application au démarrage")
            self.auto_group.add(r)
            auto_rows.append(r)
        for s in services:
            row = Adw.SwitchRow(title=s["name"])
            row.set_active(s["enabled"])
            row.connect("notify::active", lambda r, _p, svc=s: self._toggle_service(r, svc))
            self.svc_group.add(row)
            svc_rows.append(row)
        self._rows = [(self.auto_group, auto_rows), (self.svc_group, svc_rows), (self.internal_exp, internal_rows)]

    def _toggle_autostart(self, row, entry):
        try:
            set_autostart(entry, row.get_active())
            self.window.toast(f"{entry['name']} : {'activé' if row.get_active() else 'désactivé'} au démarrage")
        except Exception as e:
            self.window.toast(f"Erreur : {e}")

    def _toggle_service(self, row, svc):
        action = "enable" if row.get_active() else "disable"
        rc, out, err = run(["systemctl", "--user", action, svc["name"]], timeout=30)
        if rc == 0:
            self.window.toast(f"{svc['name']} {'activé' if row.get_active() else 'désactivé'}")
        else:
            self.window.toast(f"Erreur : {err.strip() or out.strip()}")
