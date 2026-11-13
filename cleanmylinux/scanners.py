"""Analyse des fichiers inutiles (« System Junk ») par catégorie."""
import glob
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .util import HOME, du, file_size, run, which, shell_quote

CACHE = os.path.join(HOME, ".cache")
BROWSER_CACHE_NAMES = {"google-chrome", "chromium", "mozilla", "BraveSoftware", "microsoft-edge",
                       "opera", "vivaldi", "epiphany", "brave"}
# Caches qu'on laisse décochés par défaut : utiles ou longs à reconstruire.
KEEP_UNSELECTED = {"tracker3", "fontconfig", "mesa_shader_cache", "mesa_shader_cache_db", "ibus",
                   "gstreamer-1.0", "ms-playwright", "nvidia", "pkg"}


@dataclass
class Item:
    path: str
    size: int
    label: str
    selected: bool = True
    detail: str = ""


@dataclass
class Category:
    key: str
    title: str
    subtitle: str
    icon: str
    items: list = field(default_factory=list)
    root: bool = False               # nécessite les droits administrateur
    mode: str = "paths"              # "paths" : suppression de chemins ; "shell" : commande(s)
    warning: str = ""
    shell_fn: Optional[Callable] = None  # pour mode "shell" : items -> script shell
    default_selected: bool = True

    def selected_items(self):
        return [i for i in self.items if i.selected]

    def selected_size(self):
        return sum(i.size for i in self.items if i.selected)

    def total_size(self):
        return sum(i.size for i in self.items)


def _dir_items(paths, labels=None, unselected=()):
    sizes = du(paths)
    items = []
    for p in paths:
        name = os.path.basename(p)
        items.append(Item(p, sizes.get(p, 0), (labels or {}).get(p, name),
                          selected=name not in unselected))
    items.sort(key=lambda i: -i.size)
    return items


def _entries(directory):
    try:
        return sorted(os.path.join(directory, e) for e in os.listdir(directory))
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Scanners individuels : chaque fonction renvoie une Category (ou None)
# ---------------------------------------------------------------------------

def scan_user_cache(progress):
    progress("Analyse des caches utilisateur…")
    paths = [p for p in _entries(CACHE)
             if os.path.basename(p) not in BROWSER_CACHE_NAMES and os.path.basename(p) != "thumbnails"]
    items = _dir_items(paths, unselected=KEEP_UNSELECTED)
    return Category("user_cache", "Caches des applications", "Données temporaires dans ~/.cache",
                    "folder-symbolic", items,
                    warning="Fermez les applications concernées (IDE, navigateurs) avant de nettoyer : "
                            "elles recréeront leur cache au prochain lancement.")


def scan_browser_cache(progress):
    progress("Analyse des caches des navigateurs…")
    paths = [p for p in _entries(CACHE) if os.path.basename(p) in BROWSER_CACHE_NAMES]
    labels = {}
    for snap_cache in glob.glob(os.path.join(HOME, "snap", "*", "common", ".cache")):
        paths.append(snap_cache)
        labels[snap_cache] = snap_cache.split("/snap/")[1].split("/")[0] + " (snap)"
    items = _dir_items(paths, labels)
    return Category("browser_cache", "Caches des navigateurs", "Chrome, Firefox, Brave, Edge…",
                    "web-browser-symbolic", items,
                    warning="Fermez vos navigateurs avant de nettoyer leurs caches.")


def scan_thumbnails(progress):
    progress("Analyse des miniatures…")
    items = _dir_items(_entries(os.path.join(CACHE, "thumbnails")))
    return Category("thumbnails", "Miniatures", "Aperçus d'images et de vidéos générés par le système",
                    "image-x-generic-symbolic", items)


def scan_trash(progress):
    progress("Analyse de la corbeille…")
    files_dir = os.path.join(HOME, ".local", "share", "Trash", "files")
    paths = _entries(files_dir)
    items = _dir_items(paths)
    return Category("trash", "Corbeille", "Fichiers supprimés en attente",
                    "user-trash-symbolic", items)


def scan_dev_caches(progress):
    progress("Analyse des caches de développement…")
    candidates = {
        os.path.join(HOME, ".npm", "_cacache"): "npm",
        os.path.join(HOME, ".gradle", "caches"): "Gradle (caches)",
        os.path.join(HOME, ".gradle", "daemon"): "Gradle (journaux des daemons)",
        os.path.join(HOME, ".cargo", "registry", "cache"): "Cargo (registre)",
        os.path.join(HOME, "miniconda3", "pkgs"): "Conda (paquets téléchargés)",
        os.path.join(HOME, "anaconda3", "pkgs"): "Conda (paquets téléchargés)",
        os.path.join(HOME, ".local", "share", "pnpm", "store"): "pnpm (store)",
        os.path.join(HOME, ".config", "Code", "Cache"): "VS Code (Cache)",
        os.path.join(HOME, ".config", "Code", "CachedData"): "VS Code (CachedData)",
        os.path.join(HOME, ".config", "Code", "CachedExtensionVSIXs"): "VS Code (extensions téléchargées)",
        os.path.join(HOME, ".config", "Code", "logs"): "VS Code (journaux)",
        os.path.join(HOME, ".android", "cache"): "Android SDK (cache)",
        os.path.join(HOME, ".cache", "pip"): None,  # déjà couvert par ~/.cache
        os.path.join(HOME, ".composer", "cache"): "Composer (cache)",
        os.path.join(HOME, ".nuget", "packages"): "NuGet (paquets)",
        os.path.join(HOME, ".m2", "repository"): "Maven (dépôt local – retéléchargé au besoin)",
    }
    paths = [p for p, label in candidates.items() if label and os.path.isdir(p)]
    labels = {p: candidates[p] for p in paths}
    items = _dir_items(paths, labels, unselected={"repository", "packages"})
    return Category("dev_cache", "Caches de développement", "npm, Gradle, Cargo, Conda, VS Code…",
                    "utilities-terminal-symbolic", items,
                    warning="Les dépendances seront retéléchargées lors de la prochaine compilation.")


def _parse_docker_size(s):
    m = re.match(r"([\d.]+)\s*([kKMGT]?)B", s or "")
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * {"": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[m.group(2)])


def scan_docker(progress):
    if not which("docker"):
        return None
    progress("Analyse de Docker…")
    rc, out, _ = run(["docker", "system", "df", "--format", "{{json .}}"], timeout=30)
    if rc != 0:
        return None
    reclaim = {}
    for line in out.splitlines():
        try:
            d = json.loads(line)
            reclaim[d["Type"]] = _parse_docker_size(d.get("Reclaimable", "0B").split(" ")[0])
        except (ValueError, KeyError):
            pass
    base = reclaim.get("Images", 0) + reclaim.get("Containers", 0) + reclaim.get("Build Cache", 0)
    items = [Item("docker:system", base, "Images, conteneurs arrêtés et cache de build inutilisés",
                  selected=base > 0),
             Item("docker:volumes", reclaim.get("Local Volumes", 0), "Volumes non utilisés par un conteneur",
                  selected=False, detail="Peut contenir des données de bases de données")]
    items = [i for i in items if i.size > 0]
    if not items:
        return None

    def shell(selected):
        cmds = []
        if any(i.path == "docker:system" for i in selected):
            cmds.append("docker system prune -af")
        if any(i.path == "docker:volumes" for i in selected):
            cmds.append("docker volume prune -af")
        return "\n".join(cmds)
    return Category("docker", "Docker", "Images, conteneurs et volumes inutilisés", "package-x-generic-symbolic",
                    items, mode="shell", shell_fn=shell)


def scan_tmp(progress):
    progress("Analyse des fichiers temporaires…")
    uid, now, paths = os.getuid(), time.time(), []
    for d in ("/tmp", "/var/tmp"):
        for p in _entries(d):
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if st.st_uid == uid and now - st.st_mtime > 86400 and not os.path.basename(p).startswith((".X", "systemd-", "snap-private")):
                paths.append(p)
    items = _dir_items(paths)
    return Category("tmp", "Fichiers temporaires", "Vos fichiers dans /tmp et /var/tmp de plus de 24 h",
                    "document-open-recent-symbolic", items)


def scan_crash(progress):
    progress("Analyse des rapports de plantage…")
    paths = [p for p in _entries("/var/crash")]
    items = [Item(p, file_size(p), os.path.basename(p)) for p in paths]
    return Category("crash", "Rapports de plantage", "/var/crash", "dialog-warning-symbolic", items, root=True)


def scan_old_logs(progress):
    progress("Analyse des anciens journaux…")
    paths = []
    for root, _dirs, files in os.walk("/var/log"):
        for f in files:
            if f.endswith(".gz") or f.endswith(".old") or f.endswith(".xz") or re.search(r"\.\d+$", f):
                paths.append(os.path.join(root, f))
    items = [Item(p, file_size(p), os.path.relpath(p, "/var/log")) for p in paths]
    items.sort(key=lambda i: -i.size)
    return Category("old_logs", "Anciens journaux système", "Fichiers de logs archivés dans /var/log",
                    "text-x-generic-symbolic", items, root=True)


def _parse_human(s):
    m = re.search(r"([\d.,]+)\s*([KMGT]?)", s or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", "."))
    return int(n * {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}[m.group(2)])


def scan_journal(progress):
    if not which("journalctl"):
        return None
    progress("Analyse du journal systemd…")
    rc, out, _ = run(["journalctl", "--disk-usage"], timeout=30)
    size = _parse_human(out.split("take up")[-1]) if "take up" in out else 0
    if size < 50 * 1024 ** 2:
        return None
    items = [Item("journal", size, "Journal systemd (ne garder que les 7 derniers jours)",
                  detail="Taille actuelle du journal, archives comprises")]

    def shell(selected):
        return "journalctl --vacuum-time=7d --vacuum-size=100M" if selected else ""
    return Category("journal", "Journal systemd", "Archives de journalctl", "x-office-document-symbolic",
                    items, root=True, mode="shell", shell_fn=shell)


def scan_apt_cache(progress):
    if not which("apt-get"):
        return None
    progress("Analyse du cache APT…")
    paths = glob.glob("/var/cache/apt/archives/*.deb") + glob.glob("/var/cache/apt/archives/partial/*")
    items = [Item(p, file_size(p), os.path.basename(p)) for p in paths]
    items.sort(key=lambda i: -i.size)

    def shell(selected):
        return "apt-get clean" if selected else ""
    return Category("apt_cache", "Cache des paquets APT", "Paquets .deb téléchargés", "system-software-install-symbolic",
                    items, root=True, mode="shell", shell_fn=shell)


def scan_apt_orphans(progress):
    if not which("apt-get"):
        return None
    progress("Recherche des paquets orphelins…")
    rc, out, _ = run(["apt-get", "autoremove", "--dry-run"], timeout=120)
    pkgs = re.findall(r"^Remv (\S+)", out, re.M)
    if not pkgs:
        return None
    m = re.search(r"([\d.,]+ [kMG]?B) disk space will be freed", out)
    total = _parse_human(m.group(1).replace("B", "")) if m else 0
    per = total // len(pkgs) if pkgs else 0
    items = [Item(f"apt:{p}", per, p) for p in pkgs]

    def shell(selected):
        return "apt-get autoremove -y --purge" if selected else ""
    return Category("apt_orphans", "Paquets orphelins", "Dépendances qui ne sont plus nécessaires",
                    "package-x-generic-symbolic", items, root=True, mode="shell", shell_fn=shell)


def scan_snap(progress):
    if not which("snap"):
        return None
    progress("Analyse des anciennes révisions snap…")
    rc, out, _ = run(["snap", "list", "--all"], timeout=60)
    items = []
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 6 and "disabled" in cols[-1]:
            name, rev = cols[0], cols[2]
            snap_file = f"/var/lib/snapd/snaps/{name}_{rev}.snap"
            items.append(Item(f"snap:{name}:{rev}", file_size(snap_file), f"{name} (révision {rev})"))
    if not items:
        return None

    def shell(selected):
        return "\n".join(f"snap remove {shell_quote(i.path.split(':')[1])} --revision={i.path.split(':')[2]}"
                         for i in selected)
    return Category("snap_old", "Anciennes révisions snap", "Versions désactivées conservées par snapd",
                    "package-x-generic-symbolic", items, root=True, mode="shell", shell_fn=shell)


def scan_flatpak(progress):
    if not which("flatpak"):
        return None
    progress("Analyse des runtimes Flatpak inutilisés…")
    rc, out, _ = run(["flatpak", "uninstall", "--unused"], timeout=60, input_text="n\n")
    items = []
    for line in out.splitlines():
        m = re.match(r"\s*\d+\.\s*\[?[-\s]*\]?\s*(\S+)\s+(\S+)", line)
        if m and "/" in m.group(1) or (m and "." in m.group(1)):
            items.append(Item(f"flatpak:{m.group(1)}", 0, f"{m.group(1)} {m.group(2)}"))
    if not items:
        return None

    def shell(selected):
        return "flatpak uninstall --unused -y --noninteractive" if selected else ""
    return Category("flatpak_unused", "Runtimes Flatpak inutilisés", "Runtimes dont aucune application ne dépend",
                    "package-x-generic-symbolic", items, mode="shell", shell_fn=shell)


SCANNERS = [scan_user_cache, scan_browser_cache, scan_thumbnails, scan_trash, scan_dev_caches, scan_docker,
            scan_tmp, scan_crash, scan_old_logs, scan_journal, scan_apt_cache, scan_apt_orphans, scan_snap,
            scan_flatpak]


def scan_all(progress=lambda msg: None):
    """Lance tous les scanners et renvoie les catégories non vides."""
    cats = []
    for fn in SCANNERS:
        try:
            cat = fn(progress)
        except Exception as e:  # un scanner qui échoue ne doit pas bloquer les autres
            progress(f"Erreur dans {fn.__name__} : {e}")
            cat = None
        if cat and cat.items:
            cats.append(cat)
    return cats


# ---------------------------------------------------------------------------
# Gros fichiers et doublons
# ---------------------------------------------------------------------------

def find_large_files(root, min_bytes, progress=lambda m: None, limit=500):
    """Fichiers de plus de min_bytes sous root (via find, rapide)."""
    progress(f"Recherche des fichiers de plus de {min_bytes // (1024**2)} Mo…")
    rc, out, _ = run(["find", root, "-xdev", "-type", "f", "-size", f"+{min_bytes // 1024}k",
                      "-printf", "%s\t%T@\t%p\n"], timeout=3600)
    results = []
    for line in out.splitlines():
        try:
            size, mtime, path = line.split("\t", 2)
            results.append((int(size), float(mtime), path))
        except ValueError:
            continue
    results.sort(reverse=True)
    return results[:limit]


def find_duplicates(root, min_bytes=1024 * 1024, progress=lambda m: None):
    """Groupes de fichiers identiques (taille puis hachage partiel puis complet)."""
    import hashlib
    from collections import defaultdict
    progress("Inventaire des fichiers…")
    rc, out, _ = run(["find", root, "-xdev", "-type", "f", "-size", f"+{max(min_bytes // 1024, 1)}k",
                      "-not", "-path", "*/.cache/*", "-not", "-path", "*/node_modules/*", "-not", "-path", "*/.git/*",
                      "-printf", "%s\t%p\n"], timeout=3600)
    by_size = defaultdict(list)
    for line in out.splitlines():
        try:
            size, path = line.split("\t", 1)
            by_size[int(size)].append(path)
        except ValueError:
            continue
    candidates = {s: ps for s, ps in by_size.items() if len(ps) > 1}
    total = sum(len(v) for v in candidates.values())
    done = 0
    groups = []

    def digest(path, partial):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            if partial:
                h.update(f.read(65536))
            else:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
        return h.hexdigest()

    for size, paths in sorted(candidates.items(), reverse=True):
        by_partial = defaultdict(list)
        for p in paths:
            done += 1
            if done % 50 == 0:
                progress(f"Comparaison des fichiers… {done}/{total}")
            try:
                by_partial[digest(p, True)].append(p)
            except OSError:
                pass
        for ps in by_partial.values():
            if len(ps) < 2:
                continue
            by_full = defaultdict(list)
            for p in ps:
                try:
                    by_full[digest(p, False)].append(p)
                except OSError:
                    pass
            for full_ps in by_full.values():
                if len(full_ps) > 1:
                    groups.append((size, sorted(full_ps)))
    groups.sort(key=lambda g: -g[0] * (len(g[1]) - 1))
    return groups
