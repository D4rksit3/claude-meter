#!/usr/bin/env bash
# Instala el widget y la status line para el usuario actual (sin sudo).
set -euo pipefail
cd "$(dirname "$0")"

BIN="$HOME/.local/bin/claude-meter.py"
HOOK="$HOME/.claude/claude-meter-statusline.py"
APPS="$HOME/.local/share/applications"
SETTINGS="$HOME/.claude/settings.json"

install -Dm755 claude-meter.py "$BIN"
install -Dm755 statusline.py "$HOOK"
mkdir -p "$APPS"
sed "s|@BIN@|$BIN|" claude-meter.desktop > "$APPS/claude-meter.desktop"

if [[ "${1:-}" == "--autostart" ]]; then
    mkdir -p "$HOME/.config/autostart"
    cp "$APPS/claude-meter.desktop" "$HOME/.config/autostart/"
    echo "Se abrirá solo al iniciar sesión."
fi

# Activa la status line en Claude Code si no hay otra configurada
python3 - "$SETTINGS" "$HOOK" <<'PY'
import json, os, shutil, sys
path, hook = sys.argv[1], sys.argv[2]
settings = {}
if os.path.exists(path):
    with open(path) as f:
        settings = json.load(f)
if settings.get("statusLine"):
    print("Ya tienes una statusLine en", path, "- no la toqué. Para usar el medidor ponla así:")
    print('  "statusLine": {"type": "command", "command": "python3 ' + hook + '"}')
    sys.exit(0)
if os.path.exists(path):
    shutil.copy(path, path + ".bak")
os.makedirs(os.path.dirname(path), exist_ok=True)
settings["statusLine"] = {"type": "command", "command": "python3 " + hook}
with open(path, "w") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("Status line activada en", path)
PY

echo "Listo. Búscalo como \"Claude meter\" en el menú de aplicaciones."
