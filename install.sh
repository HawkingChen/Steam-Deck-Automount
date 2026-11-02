#!/bin/bash
# Based on scawp/Steam-Deck.Mount-External-Drive; see LICENSE.md.
set -euo pipefail
base="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
choice=${1:-}
if [[ -z "$choice" ]]; then
    python3 "$base/manage.py" status
    echo
    echo '1) Install'
    echo '2) Uninstall'
    read -r -p '> ' choice
fi
case "$choice" in
    1|--install) exec python3 "$base/manage.py" install ;;
    2|--remove) exec python3 "$base/manage.py" remove ;;
    *) echo 'Invalid selection. No changes made.'; exit 1 ;;
esac
