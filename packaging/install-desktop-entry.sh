#!/bin/sh
# Installs the desktop entry of the configurator for the current user, pointing at this repository.
set -eu
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
target="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$target"
sed "s|@REPO@|$repo|g" "$repo/packaging/aula-f108.desktop" > "$target/aula-f108.desktop"
echo "Installed: $target/aula-f108.desktop"
