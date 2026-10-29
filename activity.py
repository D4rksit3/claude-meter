#!/usr/bin/env python3
"""Hook de Claude Code: anota si Claude está trabajando, esperando una respuesta tuya o libre.

Se registra para varios eventos (UserPromptSubmit, PreToolUse, PostToolUse, PermissionRequest,
Notification, Stop, SessionEnd). No imprime nada: en UserPromptSubmit lo impreso iría al contexto.

Variables opcionales (igual que statusline.py):
  CLAUDE_METER_ACTIVITY  dónde escribir el JSON (por defecto ~/.cache/claude-meter-activity.json)
  CLAUDE_METER_OWNER     "uid:gid" dueño del archivo, por si Claude Code corre como otro usuario
"""
import json
import os
import sys
import time

OUT = os.environ.get("CLAUDE_METER_ACTIVITY") or os.path.expanduser("~/.cache/claude-meter-activity.json")
OWNER = os.environ.get("CLAUDE_METER_OWNER")
ASK_TOOLS = {"AskUserQuestion", "ExitPlanMode"}


def state_for(event):
    name = event.get("hook_event_name")
    if name in ("UserPromptSubmit", "PostToolUse"):
        return "working"
    if name == "PreToolUse":
        return "asking" if event.get("tool_name") in ASK_TOOLS else "working"
    if name == "PermissionRequest":
        return "asking"
    if name == "Notification":
        kind = event.get("notification_type") or ""
        if kind in ("permission_prompt", "elicitation_dialog") or "permission" in (event.get("message") or "").lower():
            return "asking"
        return "idle"
    if name == "Stop":
        return "idle"
    if name == "SessionEnd":
        return None  # la sesión se borra
    return "working"


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    session = event.get("session_id") or "?"
    try:
        with open(OUT) as f:
            sessions = json.load(f)
    except (OSError, ValueError):
        sessions = {}

    state = state_for(event)
    if state is None:
        sessions.pop(session, None)
    else:
        sessions[session] = {"state": state, "at": time.time()}
    # limpia sesiones olvidadas (más de un día sin eventos)
    sessions = {k: v for k, v in sessions.items() if time.time() - v.get("at", 0) < 86400}

    tmp = OUT + ".tmp"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(sessions, f)
    if OWNER:
        uid, gid = (int(x) for x in OWNER.split(":"))
        os.chown(tmp, uid, gid)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # un hook roto nunca debe molestar a Claude Code
