#!/usr/bin/env bash
# Instala el widget y la status line para el usuario actual (sin sudo).
set -euo pipefail
cd "$(dirname "$0")"

BIN="$HOME/.local/bin/claude-meter.py"
HOOK="$HOME/.claude/claude-meter-statusline.py"
ACT="$HOME/.claude/claude-meter-activity.py"
APPS="$HOME/.local/share/applications"
SETTINGS="$HOME/.claude/settings.json"

install -Dm755 claude-meter.py "$BIN"
install -Dm755 statusline.py "$HOOK"
install -Dm755 activity.py "$ACT"
install -Dm644 claude-meter.svg "$HOME/.local/share/icons/hicolor/scalable/apps/claude-meter.svg"
mkdir -p "$APPS"
sed "s|@BIN@|$BIN|" claude-meter.desktop > "$APPS/claude-meter.desktop"

if [[ "${1:-}" == "--autostart" ]]; then
    mkdir -p "$HOME/.config/autostart"
    cp "$APPS/claude-meter.desktop" "$HOME/.config/autostart/"
    echo "Se abrirá solo al iniciar sesión."
fi

# Activa la status line en Claude Code si no hay otra configurada
python3 - "$SETTINGS" "$HOOK" "$ACT" <<'PY'
import json, os, shutil, sys
path, hook, act = sys.argv[1], sys.argv[2], sys.argv[3]
settings = {}
if os.path.exists(path):
    with open(path) as f:
        settings = json.load(f)
if os.path.exists(path):
    shutil.copy(path, path + ".bak")
if settings.get("statusLine"):
    print("Ya tienes una statusLine en", path, "- no la toqué. Para usar el medidor ponla así:")
    print('  "statusLine": {"type": "command", "command": "python3 ' + hook + '"}')
else:
    settings["statusLine"] = {"type": "command", "command": "python3 " + hook}
    print("Status line activada en", path)

# hooks de actividad: el muñeco teclea mientras Claude trabaja y duda cuando te pregunta algo
cmd = "python3 " + act
hooks = settings.setdefault("hooks", {})
for ev in ["UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Notification", "Stop", "SessionEnd"]:
    groups = hooks.setdefault(ev, [])
    if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
        continue
    entry = {"hooks": [{"type": "command", "command": cmd, "timeout": 5}]}
    if ev in ("PreToolUse", "PostToolUse", "PermissionRequest"):
        entry["matcher"] = "*"
    groups.append(entry)
print("Hooks de actividad agregados (sin tocar los que ya tenías)")

os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

echo "Listo. Búscalo como \"Claude meter\" en el menú de aplicaciones."
