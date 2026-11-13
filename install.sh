#!/bin/sh
# Installe le lanceur dans le menu des applications (utilisateur courant uniquement).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"
sed "s|@EXEC@|$DIR/bin/cleanmylinux|" "$DIR/data/cleanmylinux.desktop" > "$APPS/cleanmylinux.desktop"
update-desktop-database "$APPS" 2>/dev/null || true
echo "CleanMyLinux installé : cherchez « CleanMyLinux » dans le menu des applications."
