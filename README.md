# CleanMyLinux

Nettoyeur et optimiseur système Linux avec interface graphique native GNOME, inspiré de CleanMyMac.  
Le projet est écrit en **Python + GTK4/libadwaita**.

## ✨ Fonctionnalités

- **Tableau de bord** : jauges disque / mémoire / CPU, partitions, analyse intelligente.
- **Nettoyage système** : caches applicatifs et navigateurs, miniatures, journaux, temporaires, Docker, APT, Snap, Flatpak, etc.
- **Gros fichiers** : détection par dossier et taille minimale, suppression via corbeille.
- **Doublons** : détection par empreinte **SHA-256** avec conservation d'un exemplaire.
- **Applications** : désinstallation APT, Flatpak, Snap et AppImage.
- **Démarrage** : gestion des apps et services utilisateur lancés à la session.
- **Maintenance** : TRIM SSD, mises à jour paquets, réparation APT, DNS, cache polices, SMART, etc.

## 🧩 UX / UI

- Interface en **NavigationSplitView** (barre latérale + pages).
- Une page par domaine (dashboard, nettoyage, fichiers, doublons, apps, démarrage, maintenance).
- Exécution des actions en arrière-plan avec **journal en direct** et notifications toast.
- Opérations sensibles confirmées par dialogue, avec indicateur explicite des tâches administrateur.

## 🔒 Sécurité et suppression

- Les actions système utilisent `pkexec` pour l'élévation de privilèges.
- Les fichiers personnels (gros fichiers, doublons, AppImages) sont envoyés à la corbeille.
- Pas de suppression directe irréversible pour les contenus utilisateurs.

## 📦 Prérequis (Ubuntu / Debian)

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-psutil
```

## ▶️ Lancer en local

```bash
./bin/cleanmylinux
```

## 🖥️ Installer le lanceur dans le menu

```bash
./install.sh
```

## 🏗️ Structure du projet

```text
cleanmylinux/
├── app.py            # fenêtre principale + navigation
├── cleaner.py        # moteur de nettoyage
├── pages/            # pages UI par fonctionnalité
├── scanners.py       # analyses (fichiers, doublons, etc.)
├── sysinfo.py        # infos système
├── util.py           # utilitaires (threads, shell, UI)
└── widgets.py        # composants UI réutilisables
```
