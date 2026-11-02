#!/bin/bash
set -euo pipefail
if [[ $EUID == 0 ]]; then
    echo 'Run this command as your regular desktop user, without sudo.' >&2
    exit 1
fi
if ! { : </dev/tty; } 2>/dev/null; then
    echo 'Run this command in a terminal.' >&2
    exit 1
fi
for command in curl tar python3; do
    command -v "$command" >/dev/null || { echo "Missing dependency: $command" >&2; exit 1; }
done
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
curl --fail --silent --show-error --location --retry 2 \
    https://codeload.github.com/HawkingChen/Steam-Deck-Automount/tar.gz/refs/heads/main \
    --output "$stage/package.tar.gz"
mkdir "$stage/package"
tar -xzf "$stage/package.tar.gz" --strip-components=1 -C "$stage/package"
[[ -s "$stage/package/install.sh" && -s "$stage/package/manage.py" && -s "$stage/package/automount.sh" ]] || { echo 'Invalid package.' >&2; exit 1; }
destination="${XDG_DATA_HOME:-$HOME/.local/share}/steamdeck-auto-mount"
mkdir -p "$destination"
cp -R "$stage/package/." "$destination/"
bash "$destination/install.sh" </dev/tty
