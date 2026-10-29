#!/usr/bin/env bash
set -euo pipefail
rm -f "$HOME/.local/bin/claude-meter.py" \
      "$HOME/.claude/claude-meter-statusline.py" \
      "$HOME/.claude/claude-meter-activity.py" \
      "$HOME/.local/share/applications/claude-meter.desktop" \
      "$HOME/.config/autostart/claude-meter.desktop" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/claude-meter.svg"
rm -rf "$HOME/.local/share/gnome-shell/extensions/claude-meter@d4rksit3"
echo "Desinstalado. Quita a mano la clave \"statusLine\" y los hooks de claude-meter-activity.py de ~/.claude/settings.json."
