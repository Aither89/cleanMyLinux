"""Exécution du nettoyage : suppressions utilisateur, commandes, et script root via pkexec."""
import os

from .scanners import Category
from .util import HOME, delete_path, pkexec_script, run, shell_quote


def clean(categories, progress=lambda m: None):
    """Nettoie les éléments sélectionnés. Renvoie (octets libérés, liste d'erreurs)."""
    freed, errors, root_lines, user_cmds = 0, [], [], []
    for cat in categories:
        selected = cat.selected_items()
        if not selected:
            continue
        if cat.mode == "shell":
            script = cat.shell_fn(selected) if cat.shell_fn else ""
            if not script:
                continue
            if cat.root:
                root_lines.append(script)
            else:
                user_cmds.append((cat, script))
            continue
        if cat.root:
            for it in selected:
                root_lines.append(f"rm -rf -- {shell_quote(it.path)}")
            continue
        progress(f"Nettoyage : {cat.title}…")
        for it in selected:
            try:
                delete_path(it.path)
                freed += it.size
                if cat.key == "trash":
                    info = os.path.join(HOME, ".local", "share", "Trash", "info", os.path.basename(it.path) + ".trashinfo")
                    if os.path.exists(info):
                        os.remove(info)
            except Exception as e:
                errors.append(f"{it.path} : {e}")

    for cat, script in user_cmds:
        progress(f"Nettoyage : {cat.title}…")
        rc, out, err = run(script, timeout=1800)
        if rc != 0:
            errors.append(f"{cat.title} : {err.strip() or out.strip() or f'code {rc}'}")
        else:
            freed += cat.selected_size()

    if root_lines:
        progress("Nettoyage des éléments système (mot de passe requis)…")
        script = "set -e\n" + "\n".join(root_lines)
        rc, out, err = pkexec_script(script)
        if rc == 126 or rc == 127:
            errors.append("Nettoyage système annulé (authentification refusée).")
        elif rc != 0:
            errors.append(f"Nettoyage système : {err.strip() or out.strip() or f'code {rc}'}")
        else:
            freed += sum(c.selected_size() for c in categories if c.root)
    return freed, errors
