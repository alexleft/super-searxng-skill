#!/usr/bin/env bash
# Installs (or updates) super-searxng-skill into ~/.dsh/skills/searxng.
# Existing files are backed up with a .bak-<timestamp> suffix first.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-$HOME/.dsh/skills/searxng}"

echo "Installing super-searxng-skill"
echo "  source: $SRC_DIR"
echo "  target: $TARGET"

mkdir -p "$TARGET"
mkdir -p "$TARGET/bin"

stamp="$(date +%Y%m%d-%H%M%S)"

install_one() {
    local rel="$1"
    local src="$SRC_DIR/$rel"
    local dst="$TARGET/$rel"
    if [ ! -f "$src" ]; then
        echo "  warning: source missing: $src" >&2
        return
    fi
    if [ -f "$dst" ]; then
        cp "$dst" "$dst.bak-$stamp"
        echo "  backed up $rel -> $(basename "$dst").bak-$stamp"
    fi
    cp "$src" "$dst"
    echo "  installed $rel"
}

install_one "SKILL.md"
install_one "searxng.py"
install_one "searxng.ps1"
install_one "bin/searxng"
chmod +x "$TARGET/bin/searxng" "$TARGET/searxng.py" 2>/dev/null || true

echo
echo "Done. Restart or reload the DSH session to pick up the skill."
echo "Quick test:"
echo "  $TARGET/bin/searxng 'hello' --limit 2"
