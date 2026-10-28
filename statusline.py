#!/usr/bin/env python3
"""Status line de Claude Code: imprime el uso del plan y lo deja en un archivo para el widget claude-meter.

Variables opcionales:
  CLAUDE_METER_OUT    dónde escribir el JSON (por defecto ~/.cache/claude-meter.json)
  CLAUDE_METER_OWNER  "uid:gid" dueño del archivo, por si Claude Code corre como otro usuario (p. ej. root)
"""
import json
import os
import sys
import time

OUT = os.environ.get("CLAUDE_METER_OUT") or os.path.expanduser("~/.cache/claude-meter.json")
OWNER = os.environ.get("CLAUDE_METER_OWNER")

data = json.load(sys.stdin)
limits = data.get("rate_limits") or {}
state = {
    "updated_at": time.time(),
    "model": (data.get("model") or {}).get("display_name"),
    "context_pct": (data.get("context_window") or {}).get("used_percentage"),
    "five_hour": limits.get("five_hour"),
    "seven_day": limits.get("seven_day"),
}

tmp = OUT + ".tmp"
try:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(state, f)
    if OWNER:
        uid, gid = (int(x) for x in OWNER.split(":"))
        os.chown(tmp, uid, gid)
    os.replace(tmp, OUT)
except (OSError, ValueError):
    pass


def pct(win):
    return "—" if not win else "{:.0f}%".format(win["used_percentage"])


parts = [state["model"] or "Claude", "5h " + pct(state["five_hour"]), "semana " + pct(state["seven_day"])]
if state["context_pct"] is not None:
    parts.append("contexto {:.0f}%".format(state["context_pct"]))
print(" · ".join(parts))
