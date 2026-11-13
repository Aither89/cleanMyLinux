"""Page « Applications » : désinstallation des applications APT, Flatpak, Snap et AppImage."""
import configparser
import glob
import os
import re

from gi.repository import Adw, Gtk

from ..util import HOME, human, in_thread, pkexec_script, run, shell_quote, trash_path, ui, which
from ..widgets import ProgressRow, confirm, content_box, page_header, scrolled_clamp


def _desktop_info(path):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    try:
        cp.read(path, encoding="utf-8")
        sec = cp["Desktop Entry"]
        if sec.get("NoDisplay", "false").lower() == "true" or sec.get("Type", "Application") != "Application":
            return None
        return {"name": sec.get("Name[fr]", sec.get("Name", os.path.basename(path))),
                "icon": sec.get("Icon", "application-x-executable"),
                "comment": sec.get("Comment[fr]", sec.get("Comment", ""))}
    except Exception:
        return None


def list_apps(progress):
    apps = []
    # --- APT : paquets qui fournissent un .desktop visible
    if which("dpkg"):
        progress("Inventaire des applications APT…")
        desktops = glob.glob("/usr/share/applications/*.desktop")
        rc, out, _ = run(["dpkg", "-S"] + desktops, timeout=120)
        owner = {}
        for line in out.splitlines():
            if ": " in line:
                pkg, path = line.split(": ", 1)
                owner.setdefault(path, pkg.split(":")[0].split(",")[0].strip())
        rc, out, _ = run(["dpkg-query", "-W", "-f=${Package}\t${Installed-Size}\t${Version}\n"], timeout=60)
        sizes, versions = {}, {}
        for line in out.splitlines():
            p = line.split("\t")
            if len(p) == 3:
                sizes[p[0]] = int(p[1] or 0) * 1024
                versions[p[0]] = p[2]
        seen = set()
        for d in desktops:
            pkg = owner.get(d)
            if not pkg or pkg in seen:
                continue
            info = _desktop_info(d)
            if not info:
                continue
            seen.add(pkg)
            apps.append({"kind": "apt", "id": pkg, "name": info["name"], "icon": info["icon"],
                         "size": sizes.get(pkg, 0), "detail": f"APT · {pkg} {versions.get(pkg, '')}"})
    # --- Flatpak
    if which("flatpak"):
        progress("Inventaire des applications Flatpak…")
        rc, out, _ = run(["flatpak", "list", "--app", "--columns=application,name,size,installation"], timeout=60)
        for line in out.splitlines():
            cols = line.split("\t")
            if len(cols) >= 4:
                apps.append({"kind": "flatpak", "id": cols[0], "name": cols[1], "icon": cols[0],
                             "size": _parse_size(cols[2]), "detail": f"Flatpak ({cols[3]}) · {cols[0]}"})
    # --- Snap
    if which("snap"):
        progress("Inventaire des snaps…")
        rc, out, _ = run(["snap", "list"], timeout=60)
        for line in out.splitlines()[1:]:
            cols = line.split()
            if len(cols) >= 6 and not any(x in cols[-1] for x in ("base", "core", "snapd")) \
                    and not re.match(r"^(core\d*|bare|snapd|gnome-\d|gtk-common-themes|kf[56]|mesa-|cups$|kde-frameworks)", cols[0]):
                snap_file = f"/var/lib/snapd/snaps/{cols[0]}_{cols[2]}.snap"
                size = os.path.getsize(snap_file) if os.path.exists(snap_file) else 0
                apps.append({"kind": "snap", "id": cols[0], "name": cols[0], "icon": f"snap.{cols[0]}",
                             "size": size, "detail": f"Snap · {cols[0]} {cols[1]}"})
    # --- AppImage
    progress("Recherche des AppImages…")
    for d in (os.path.join(HOME, "Applications"), os.path.join(HOME, "Downloads"), os.path.join(HOME, "Téléchargements"),
              os.path.join(HOME, ".local", "bin"), os.path.join(HOME, "bin")):
        for f in glob.glob(os.path.join(d, "*.[Aa]pp[Ii]mage")):
            apps.append({"kind": "appimage", "id": f, "name": os.path.basename(f), "icon": "application-x-executable",
                         "size": os.path.getsize(f), "detail": "AppImage · " + f.replace(HOME, "~")})
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def _parse_size(s):
    m = re.match(r"([\d.,]+)\s*([kMGT]?)", s or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", "."))
    return int(n * {"": 1, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[m.group(2)])


class UninstallerPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.apps = []
        self.loaded = False
        box = content_box()
        box.append(page_header("Applications", "Désinstallez proprement les applications APT, Flatpak, Snap et AppImage."))
        bar = Gtk.Box(spacing=12)
        self.search = Gtk.SearchEntry(placeholder_text="Rechercher une application…", hexpand=True)
        self.search.connect("search-changed", lambda *_: self.list.invalidate_filter())
        bar.append(self.search)
        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Actualiser")
        self.refresh_btn.connect("clicked", self.load)
        bar.append(self.refresh_btn)
        box.append(bar)
        self.count_label = Gtk.Label(xalign=0)
        self.count_label.add_css_class("dim-label")
        box.append(self.count_label)
        self.progress = ProgressRow()
        box.append(self.progress)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.list.set_filter_func(self._filter)
        box.append(self.list)
        self.append(scrolled_clamp(box, 1000))

    def on_show(self):
        if not self.loaded:
            self.load()

    def _filter(self, row):
        q = self.search.get_text().lower().strip()
        return not q or q in row.app["name"].lower() or q in row.app["detail"].lower()

    def load(self, *_):
        self.loaded = True
        self.refresh_btn.set_sensitive(False)
        self.progress.start("Inventaire des applications…")
        in_thread(lambda: ui(self._show, list_apps(lambda m: ui(self.progress.message, m))))

    def _show(self, apps):
        self.progress.stop()
        self.refresh_btn.set_sensitive(True)
        self.apps = apps
        child = self.list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        for app in apps:
            row = Adw.ActionRow(title=app["name"].replace("&", "&amp;"), subtitle=app["detail"])
            row.app = app
            row.set_title_lines(1)
            row.set_subtitle_lines(1)
            icon = Gtk.Image.new_from_icon_name(app["icon"] if not app["icon"].startswith("/") else "application-x-executable")
            if app["icon"].startswith("/") and os.path.exists(app["icon"]):
                icon = Gtk.Image.new_from_file(app["icon"])
            icon.set_pixel_size(32)
            row.add_prefix(icon)
            lbl = Gtk.Label(label=human(app["size"]) if app["size"] else "", valign=Gtk.Align.CENTER)
            lbl.add_css_class("dim-label")
            lbl.add_css_class("numeric")
            row.add_suffix(lbl)
            btn = Gtk.Button(label="Désinstaller", valign=Gtk.Align.CENTER)
            btn.add_css_class("destructive-action")
            btn.add_css_class("flat")
            btn.connect("clicked", lambda _b, a=app, r=row: self.ask_remove(a, r))
            row.add_suffix(btn)
            self.list.append(row)
        total = sum(a["size"] for a in apps)
        self.count_label.set_text(f"{len(apps)} applications · {human(total)}")

    def ask_remove(self, app, row):
        body = {"apt": "Le paquet et sa configuration seront supprimés (mot de passe administrateur requis).",
                "flatpak": "L'application Flatpak et ses données seront supprimées.",
                "snap": "Le snap sera supprimé (mot de passe administrateur requis).",
                "appimage": "Le fichier AppImage sera déplacé vers la corbeille."}[app["kind"]]
        confirm(self.window, f"Désinstaller {app['name']} ?", body, "Désinstaller", lambda: self._remove(app, row))

    def _remove(self, app, row):
        row.set_sensitive(False)
        self.progress.start(f"Désinstallation de {app['name']}…")

        def work():
            if app["kind"] == "apt":
                rc, out, err = pkexec_script(f"apt-get remove --purge -y {shell_quote(app['id'])}")
            elif app["kind"] == "flatpak":
                rc, out, err = run(["flatpak", "uninstall", "-y", "--noninteractive", "--delete-data", app["id"]], timeout=600)
            elif app["kind"] == "snap":
                rc, out, err = pkexec_script(f"snap remove {shell_quote(app['id'])}")
            else:
                try:
                    trash_path(app["id"])
                    rc, err = 0, ""
                except Exception as e:
                    rc, err = 1, str(e)
            ui(self._removed, app, row, rc, err)
        in_thread(work)

    def _removed(self, app, row, rc, err):
        self.progress.stop()
        if rc == 0:
            self.list.remove(row)
            self.apps = [a for a in self.apps if a is not app]
            self.count_label.set_text(f"{len(self.apps)} applications · {human(sum(a['size'] for a in self.apps))}")
            self.window.toast(f"{app['name']} désinstallé ({human(app['size'])} libérés)")
        else:
            row.set_sensitive(True)
            self.window.toast(f"Échec : {err.strip().splitlines()[-1] if err.strip() else 'annulé'}")
