"""Utilitaires communs : formatage, exécution de commandes, threads, suppression sûre."""
import os
import shlex
import shutil
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gio  # noqa: E402

HOME = str(Path.home())
# Chemins qu'on refuse catégoriquement de supprimer, quoi qu'il arrive.
PROTECTED = {"/", "/home", HOME, "/usr", "/etc", "/var", "/boot", "/bin", "/lib", "/opt", "/root",
             os.path.join(HOME, ".config"), os.path.join(HOME, ".local"), os.path.join(HOME, ".local", "share"),
             os.path.join(HOME, ".cache"), os.path.join(HOME, ".ssh"), os.path.join(HOME, ".gnupg")}


def human(n) -> str:
    """Formate une taille en octets de façon lisible (unités françaises)."""
    n = float(n or 0)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024 or unit == "To":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return f"{n:.1f} To"


def run(cmd, timeout=600, input_text=None, env=None, check=False):
    """Exécute une commande (liste ou chaîne) et renvoie (code, stdout, stderr)."""
    full_env = dict(os.environ, LC_ALL="C", LANG="C")
    if env:
        full_env.update(env)
    try:
        p = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True,
                           timeout=timeout, input=input_text, env=full_env)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"commande introuvable : {cmd[0] if isinstance(cmd, list) else cmd}"
    except subprocess.TimeoutExpired:
        return 124, "", "délai dépassé"


def which(name) -> bool:
    return shutil.which(name) is not None


def du(paths) -> dict:
    """Taille réelle sur disque (octets) de chaque chemin, via `du` (bien plus rapide que Python)."""
    paths = [p for p in paths if os.path.lexists(p)]
    if not paths:
        return {}
    sizes = {}
    # Par lots pour éviter une ligne de commande trop longue.
    for i in range(0, len(paths), 500):
        batch = paths[i:i + 500]
        rc, out, _ = run(["du", "-s", "--block-size=1", "--"] + batch, timeout=1800)
        for line in out.splitlines():
            if "\t" in line:
                size, path = line.split("\t", 1)
                try:
                    sizes[path] = int(size)
                except ValueError:
                    pass
    return sizes


def file_size(path) -> int:
    try:
        st = os.lstat(path)
        return st.st_blocks * 512 if st.st_blocks else st.st_size
    except OSError:
        return 0


def in_thread(fn, *args, **kwargs) -> threading.Thread:
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return t


def ui(fn, *args):
    """Planifie l'appel de fn(*args) sur le thread GTK."""
    def _call():
        fn(*args)
        return False
    GLib.idle_add(_call)


def is_safe_to_delete(path) -> bool:
    """Refuse les chemins critiques ou trop courts."""
    try:
        real = os.path.realpath(path)
    except OSError:
        return False
    if real in PROTECTED or path in PROTECTED:
        return False
    if real.count("/") < 2:  # ex. /tmp ou /home : trop haut dans l'arborescence
        return False
    return True


def delete_path(path) -> int:
    """Supprime définitivement un fichier ou un dossier. Renvoie les octets libérés (approx.)."""
    if not is_safe_to_delete(path):
        raise PermissionError(f"chemin protégé : {path}")
    size = file_size(path) if not os.path.isdir(path) or os.path.islink(path) else du([path]).get(path, 0)
    if os.path.islink(path) or not os.path.isdir(path):
        os.remove(path)
    else:
        shutil.rmtree(path)
    return size


def trash_path(path) -> bool:
    """Déplace vers la corbeille (via GIO, respecte la spec freedesktop)."""
    if not is_safe_to_delete(path):
        raise PermissionError(f"chemin protégé : {path}")
    return Gio.File.new_for_path(path).trash(None)


def shell_quote(s) -> str:
    return shlex.quote(s)


def pkexec_script(script: str, timeout=3600):
    """Exécute un script shell en root via pkexec (une seule demande de mot de passe)."""
    return run(["pkexec", "/bin/sh", "-c", script], timeout=timeout)


def open_in_file_manager(window, path):
    """Ouvre le dossier contenant `path` dans le gestionnaire de fichiers."""
    try:
        launcher = Gio.File.new_for_path(path)
        from gi.repository import Gtk
        Gtk.FileLauncher.new(launcher).open_containing_folder(window, None, None)
    except Exception:
        run(["xdg-open", os.path.dirname(path)])
