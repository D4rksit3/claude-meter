#!/usr/bin/env bash
set -euo pipefail
rm -f "$HOME/.local/bin/claude-meter.py" \
      "$HOME/.claude/claude-meter-statusline.py" \
      "$HOME/.local/share/applications/claude-meter.desktop" \
      "$HOME/.config/autostart/claude-meter.desktop"
echo "Desinstalado. Quita a mano la clave \"statusLine\" de ~/.claude/settings.json si la agregó el instalador."
