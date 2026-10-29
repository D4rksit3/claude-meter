#!/usr/bin/env python3
"""Medidor de uso de Claude siempre encima: ventana de 5 horas y semanal del plan.

Los datos los escribe la status line de Claude Code en ~/.cache/claude-meter.json
cada vez que Claude responde; este widget solo los lee.

- La mascota cambia de ánimo según el uso: feliz con poco, cansada y triste al acercarse al límite.
- En reposo solo se ve el muñeco y un globito con su ánimo; al pasar el mouse aparecen los porcentajes.
- Arrastrar con clic izquierdo para moverlo (recuerda la posición).
- Clic derecho: cerrar.
"""
import json
import math
import os
import random
import time

# En Wayland solo las ventanas X11 pueden pedir "siempre encima"
os.environ.setdefault("GDK_BACKEND", "x11")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

DATA = os.path.expanduser("~/.cache/claude-meter.json")
ACTIVITY = os.path.expanduser("~/.cache/claude-meter-activity.json")  # lo escribe activity.py (hooks)
WORK_STALE = 10 * 60    # "trabajando" sin eventos nuevos por más de esto: probablemente se cortó
ASK_STALE = 2 * 3600    # una pregunta sin responder deja de mostrarse pasado esto
ACTIVITY_TEXT = {"ask": "Tengo una duda…"}  # trabajando ya se ve: teclea

# el muñeco "ve" lo que haces y comenta (se puede apagar con clic derecho)
CHAT_EVERY = (150, 300)       # charla espontánea mientras estás: cada 2,5–5 min (al azar)
CHAT_SHOW = 30                # segundos que se ve cada mensaje (se pausa con el mouse encima)
MIN_GAP = 25                  # nunca dos mensajes seguidos con menos de esto (salvo toque y festejo)
AWAY_AFTER = 5 * 60           # sin teclado ni mouse por esto: te fuiste
STREAK_BREAK = 50 * 60        # tiempo seguido frente a la pantalla antes de sugerir una pausa
CLAUDE_LONG = 3 * 60          # si Claude lleva esto trabajando, lo comenta
CLAUDE_UNUSED = 15 * 60       # sin usar Claude por esto: puede invitarte a usarlo
EXT_BUS = ("org.gnome.Shell", "/pe/d4rksit3/ClaudeMeter", "pe.d4rksit3.ClaudeMeter")  # gnome-extension/

# tipo de programa según la clase de su ventana (nunca se leen títulos)
APP_KINDS = [
    ("code", ("code", "vscodium", "jetbrains", "pycharm", "idea", "sublime", "text-editor", "gedit", "zed")),
    ("terminal", ("terminal", "ptyxis", "kitty", "alacritty", "konsole", "tilix", "wezterm", "ghostty")),
    ("meet", ("zoom", "meet", "webex")),
    ("chat", ("slack", "discord", "telegram", "whatsapp", "teams", "signal", "thunderbird", "evolution", "geary")),
    ("browser", ("firefox", "chrome", "chromium", "brave", "edge", "epiphany", "vivaldi", "opera")),
    ("music", ("spotify", "rhythmbox")),
    ("notes", ("obsidian",)),
    ("office", ("libreoffice", "soffice", "onlyoffice", "wps")),
    ("files", ("nautilus", "files")),
]
APP_LINES = {
    "code": ["¡A programar! 💻", "Ese código te va a quedar bonito", "¿Y los tests? Yo no digo nada 👀",
             "Nombres claros, futuro tú feliz", "Commit chiquito, commit feliz"],
    "terminal": ["Modo hacker activado 😎", "Ojo con ese sudo 👀", "La terminal es tu casa", "Cuidado con el rm -rf 😅"],
    "browser": ["¿Investigando algo? 🔎", "No te pierdas en las pestañas 😅", "¿Documentación o redes? 👀"],
    "music": ["¿Qué ponemos? 🎵", "¡Música para concentrarse!"],
    "chat": ["¡Saluda de mi parte! 👋", "Responde y volvemos a lo nuestro 😉"],
    "meet": ["¡Suerte en la reunión! 🎤", "Cámara lista, sonrisa lista 😄"],
    "notes": ["Anotar es pensar dos veces 📝", "Tu segundo cerebro crece 🧠"],
    "office": ["Documentos… ¡ánimo! 📄", "Ese informe va a quedar 👌"],
    "files": ["Ordenando cositas 📁"],
}
QUESTION_LINES = [
    "¿Cuál es la meta de hoy?",
    "¿Qué es lo más importante ahora?",
    "¿Ya tachaste algo de tu lista?",
    "¿En qué te ayudo? Claude está libre",
]
BACK_LINES = ["¡Volviste! 👋", "¡Hola de nuevo! ¿Seguimos?", "Te extrañé 😄"]
SONG_LINES = ["🎵 Buen tema: {}", "¡Esa me gusta! 🎶", "🎶 {}, buena elección"]
IDLE_LINES = [
    "¿Hacemos algo?",
    "Psst… ¿seguimos?",
    "Estoy aburrido…",
    "¿Le damos a algún pendiente?",
    "¿Revisamos algo juntos?",
    "Aquí sigo, por si acaso",
]
MOTIVATION_LINES = [
    "Paso a paso se llega lejos 🚶",
    "Lo difícil hoy es fácil mañana",
    "Hecho es mejor que perfecto",
    "Un commit a la vez 💪",
    "Tú puedes con esto",
    "Cada bug arreglado cuenta",
    "La constancia gana a la prisa",
    "Hoy es buen día para avanzar",
    "Empieza por lo pequeño",
    "Lo que no se mide no mejora 📈",
    "Respira: un problema a la vez",
    "Los errores también enseñan",
    "Vas mejor de lo que crees ✨",
    "Primero que funcione, luego que brille",
    "Si te trabas, explícamelo a mí 🦆",
    "Disciplina > motivación",
]
CARE_LINES = [
    "¿Tomaste agua? 💧",
    "Estira la espalda un ratito",
    "Mira lejos 20 segundos 👀",
    "¿Ya comiste algo?",
    "Una pausa también es avanzar ☕",
    "Hombros abajo, respira hondo",
]
DONE_LINES = ["¡Listo! Buen trabajo 💪", "¡Terminamos! 🎉", "¡Hecho! ¿Qué sigue?", "¡Eso quedó! ✨", "¡Misión cumplida!"]
POKE_LINES = ["¡Ey!", "¡Jaja, cosquillas!", "¿Me necesitas?", "¡Aquí estoy!", "¡Hola! 👋", "¿Trabajamos?"]
CONF_DIR = os.path.expanduser("~/.config/claude-meter")
CONF = os.path.join(CONF_DIR, "config.json")
STALE_AFTER = 60 * 60  # pasado esto, el uso desde otros lados (web, móvil) puede no estar reflejado

DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MASCOT = 64
FRAME_MS = 80
LOOP = 6.6  # segundos; todo movimiento de la mascota se repite en este ciclo y así se dibuja una sola vez

# ánimo según el mayor de los dos porcentajes: (hasta %, ánimo)
MOODS = [(20, "great"), (40, "happy"), (60, "ok"), (75, "meh"), (90, "tired"), (100, "sad")]
# carita del globito según el consumo (el mayor de sesión y semana): (hasta %, carita)

CSS = b"""
window { background-color: transparent; }
.card { background-color: rgba(22, 22, 22, 0.95); border-radius: 12px; }
.head { color: #d97757; font-weight: bold; }
.bubble { color: #ffffff; font-size: 11pt; font-weight: bold; background-color: rgba(28, 28, 28, 0.97);
          border: 2px solid #d97757; border-radius: 10px; padding: 5px 10px; }
.lastmsg { color: #e8e8e8; font-size: 9pt; }
.model { color: #a7a7a7; font-size: 9pt; }
.name { color: #ffffff; font-size: 9pt; }
.pct { color: #ffffff; font-weight: bold; font-size: 9pt; }
.reset, .foot { color: #8a8a8a; font-size: 8pt; }
.foot.stale { color: #e0a43a; }
progressbar trough { min-height: 6px; border-radius: 3px; background-color: rgba(255, 255, 255, 0.12); border: none; }
progressbar progress { min-height: 6px; border-radius: 3px; border: none; background-color: #4caf7a; }
progressbar.warn progress { background-color: #e0a43a; }
progressbar.crit progress { background-color: #e5534b; }
"""


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def until(epoch):
    secs = max(0, int(epoch - time.time()))
    h, m = divmod(secs // 60, 60)
    if h >= 24:
        t = time.localtime(epoch)
        return "{} {:02d}:{:02d}".format(DAYS[t.tm_wday], t.tm_hour, t.tm_min)
    return "{}h {:02d}m".format(h, m) if h else "{} min".format(m)


# cara de cada ánimo: ojos, boca, cejas y extras (como un emoji, pero en el muñeco)
FACE = {
    "great": dict(eyes="arc", mouth="grin", blush=True),            # 😄
    "happy": dict(eyes="round", mouth="smile", blush=True),         # 😊
    "ok":    dict(eyes="round", mouth="small"),                     # 🙂
    "meh":   dict(eyes="round", mouth="flat"),                      # 😐
    "tired": dict(eyes="half", mouth="wavy", sweat=True),           # 😓
    "sad":   dict(eyes="round", mouth="frown", brows="sad", tear=True),  # 😫
    "empty": dict(eyes="x", mouth="wavy"),                          # 😵
    "sleep": dict(eyes="closed", mouth="o"),                        # 😴
    "work":  dict(eyes="down", mouth="small"),                      # concentrado
    "ask":   dict(eyes="up", mouth="o", brows="raised"),            # pensando
    "wave":  dict(eyes="arc", mouth="talk", blush=True),            # hablando
}
COLORS = {"great": "#ef7d52", "happy": "#e8774f", "ok": "#d97757", "meh": "#d08062", "tired": "#c98463",
          "sad": "#b58c79", "empty": "#978a84", "sleep": "#b58c79"}


def mascot_svg(mood, t, px=MASCOT, crop=True, tint="ok"):
    """Un cuadro del muñequito pixelado de Claude Code, en una caja de 56x56.

    Rejilla de 18x5 celdas: cuerpo, dos ojitos, bracitos a los lados y cuatro patitas, más una cara
    (cejas, boca, rubor, sudor, lágrima) que cambia con el ánimo.
    mood "work" (teclea), "ask" (duda) y "wave" (habla) toman el color del ánimo de uso que indica tint.
    """
    ux, uy = 3, 6               # cada pixel es el doble de alto que de ancho, como las celdas de la terminal
    w = 2 * math.pi / LOOP      # frecuencias enteras de w: el ciclo cierra sin saltos
    lively = mood in ("great", "happy", "wave")
    droopy = mood in ("tired", "sad", "empty")
    hop = -abs(math.sin(w * 3 * t)) * (5 if mood != "happy" else 3) if lively else 0
    sway = round(math.sin(w * 2 * t)) * 0.5 if mood in ("ok", "meh") else 0
    sink = {"tired": 2, "sad": 3, "empty": 5, "sleep": 3}.get(mood, 0)
    breathe = math.sin(w * t * (1 if droopy or mood == "sleep" else 2)) * 0.4
    x0 = 1 + sway * ux
    y0 = 14 + hop + sink
    color = COLORS.get(mood) or COLORS.get(tint, COLORS["ok"])
    tap = math.sin(w * 22 * t) > 0  # alterna manos al teclear
    if mood == "work":
        y0 += 0.5 if tap else 0
    ink = "#161616"
    face = FACE[mood]

    def px_rect(cx, cy, cw=1, ch=1, fill=None, extra=""):
        return '<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" fill="{}"{}/>'.format(
            x0 + cx * ux, y0 + cy * uy, cw * ux, ch * uy, fill or color, extra)

    def stroke(d, width=1.2, fill="none"):
        return ('<path d="{}" stroke="{}" stroke-width="{}" stroke-linecap="round" stroke-linejoin="round" '
                'fill="{}" shape-rendering="geometricPrecision"/>').format(d, ink, width, fill)

    parts = [
        px_rect(3, 0 - breathe / uy, 12, 2 + breathe / uy),  # cabeza (respira estirándose un poco)
        px_rect(3, 2, 12, 2),                               # cuerpo
    ]
    # bracitos: arriba saludando si está contento, abajo si está decaído
    if lively:
        up = math.sin(w * (12 if mood == "wave" else 6) * t) > 0
        parts += [px_rect(1, 1 if up else 2, 2), px_rect(15, 2 if up else 1, 2)]
    elif mood == "work":   # manos sobre el teclado, una y otra
        parts += [px_rect(1.5, 2.7 if tap else 3.1, 1.5), px_rect(15, 3.1 if tap else 2.7, 1.5)]
    elif mood == "ask":    # una mano rascándose la cabeza
        scratch = math.sin(w * 8 * t) * 0.12
        parts += [px_rect(1, 2, 2), px_rect(16, 0.9, 1, 1.6), px_rect(14.6, 0.35 + scratch, 2.4, 0.55)]
    elif droopy:
        parts += [px_rect(1.5, 3, 1.5), px_rect(15, 3, 1.5)]
    else:
        parts += [px_rect(1, 2, 2), px_rect(15, 2, 2)]
    # patitas: caminan cuando está contento, quietas si no
    step = lively and math.sin(w * 6 * t) > 0
    for i, cx in enumerate((4, 6, 11, 13)):
        lift = 0.3 if step and i % 2 == 0 else 0
        parts.append(px_rect(cx, 4 - lift, 1, 1))

    # ---- cara ----
    cx = x0 + 9 * ux                 # centro horizontal de la cara
    ey = y0 + 1.3 * uy               # altura de los ojos
    my = y0 + 2.25 * uy              # altura de la boca
    blink = (t % (LOOP / 2)) < 0.15
    eyes = "closed" if blink and face["eyes"] in ("round", "half", "down", "up") else face["eyes"]
    for ex in (5, 12):
        ecx = x0 + (ex + 0.5) * ux
        if eyes == "round":
            parts.append(px_rect(ex, 0.85, 1, 0.9, ink))
        elif eyes == "arc":          # ^ ^
            parts.append(stroke("M{:.2f} {:.2f} Q{:.2f} {:.2f} {:.2f} {:.2f}".format(
                ecx - 2, ey + 1.2, ecx, ey - 2.4, ecx + 2, ey + 1.2), 1.3))
        elif eyes == "half":         # párpados caídos
            parts.append(px_rect(ex, 1.2, 1, 0.5, ink))
            parts.append(stroke("M{:.2f} {:.2f} L{:.2f} {:.2f}".format(ecx - 2.2, ey - 1.2, ecx + 2.2, ey - 1.2), 1))
        elif eyes == "closed":
            parts.append(stroke("M{:.2f} {:.2f} Q{:.2f} {:.2f} {:.2f} {:.2f}".format(
                ecx - 1.8, ey, ecx, ey + 1.4, ecx + 1.8, ey), 1.1))
        elif eyes == "x":
            parts.append(stroke("M{0:.2f} {1:.2f} l3.2 3.2 M{2:.2f} {1:.2f} l-3.2 3.2".format(
                ecx - 1.6, ey - 1.6, ecx + 1.6), 1))
        elif eyes == "down":         # mirando el teclado
            parts.append(px_rect(ex, 1.25, 1, 0.55, ink))
        elif eyes == "up":           # mirando hacia arriba, pensando
            parts.append(px_rect(ex + 0.3, 0.55, 1, 0.6, ink))

    brows = face.get("brows")
    if brows == "sad":               # cejas que suben hacia el centro
        parts.append(stroke("M{:.2f} {:.2f} L{:.2f} {:.2f} M{:.2f} {:.2f} L{:.2f} {:.2f}".format(
            x0 + 4.6 * ux, y0 + 0.55 * uy, x0 + 6.6 * ux, y0 + 0.25 * uy,
            x0 + 11.4 * ux, y0 + 0.25 * uy, x0 + 13.4 * ux, y0 + 0.55 * uy), 1))
    elif brows == "raised":
        parts.append(stroke("M{:.2f} {:.2f} Q{:.2f} {:.2f} {:.2f} {:.2f}".format(
            x0 + 11.6 * ux, y0 + 0.3 * uy, x0 + 12.8 * ux, y0 + 0.05 * uy, x0 + 14 * ux, y0 + 0.3 * uy), 1))

    mouth = face["mouth"]
    if mouth == "talk":              # abre y cierra la boca mientras habla
        mouth = "grin" if math.sin(w * 30 * t) > 0 else "small"
    if mouth == "grin":              # sonrisa grande, abierta
        parts.append(stroke("M{:.2f} {:.2f} Q{:.2f} {:.2f} {:.2f} {:.2f} Z".format(
            cx - 4, my - 1, cx, my + 4.5, cx + 4, my - 1), 1, ink))
    elif mouth == "smile":
        parts.append(stroke("M{:.2f} {:.2f} Q{:.2f} {:.2f} {:.2f} {:.2f}".format(cx - 3.6, my - 0.6, cx, my + 3, cx + 3.6, my - 0.6)))
    elif mouth == "small":
        parts.append(stroke("M{:.2f} {:.2f} Q{:.2f} {:.2f} {:.2f} {:.2f}".format(cx - 2.2, my, cx, my + 1.8, cx + 2.2, my)))
    elif mouth == "flat":
        parts.append(stroke("M{:.2f} {:.2f} L{:.2f} {:.2f}".format(cx - 2.6, my + 0.6, cx + 2.6, my + 0.6)))
    elif mouth == "wavy":
        parts.append(stroke("M{:.2f} {:.2f} q1.3 -1.2 2.6 0 t2.6 0".format(cx - 2.6, my + 0.8), 1.1))
    elif mouth == "frown":
        parts.append(stroke("M{:.2f} {:.2f} Q{:.2f} {:.2f} {:.2f} {:.2f}".format(cx - 3.4, my + 2, cx, my - 1, cx + 3.4, my + 2)))
    elif mouth == "o":
        parts.append('<ellipse cx="{:.2f}" cy="{:.2f}" rx="1.3" ry="1.5" fill="{}" '
                     'shape-rendering="geometricPrecision"/>'.format(cx, my + 0.8, ink))

    if face.get("blush"):
        parts += ['<ellipse cx="{:.2f}" cy="{:.2f}" rx="2" ry="1.1" fill="#f6b3a6" opacity="0.9" '
                  'shape-rendering="geometricPrecision"/>'.format(x0 + bx * ux, y0 + 2.05 * uy) for bx in (4.2, 13.8)]
    if face.get("sweat"):            # gotita de sudor en la frente
        sx, sy = x0 + 14.2 * ux, y0 + 0.3 * uy + (t / LOOP * 2 % 1) * 3
        parts.append('<path d="M{0:.2f} {1:.2f} q-1.6 2.6 0 3.4 q1.6 -0.8 0 -3.4 Z" fill="#7cc4f0" '
                     'shape-rendering="geometricPrecision"/>'.format(sx, sy))
    if face.get("tear"):             # lagrimita que cae
        drop = t / LOOP * 4 % 1
        parts.append('<ellipse cx="{:.2f}" cy="{:.2f}" rx="0.9" ry="1.3" fill="#6db3e8" opacity="{:.2f}" '
                     'shape-rendering="geometricPrecision"/>'.format(x0 + 5.5 * ux, ey + 3 + drop * 10, 1 - drop))

    if mood == "work":   # teclado delante, tapando las patitas, con teclas que se iluminan
        parts.append(px_rect(2, 3.35, 14, 0.95, "#3a3a3a"))
        lit = {(int(t * 10) * 7) % 22, (int(t * 10) * 13 + 5) % 22}
        for k in range(22):
            row, col = divmod(k, 11)
            parts.append(px_rect(2.5 + col * 1.2, 3.5 + row * 0.35, 0.8, 0.22,
                                 "#f2f2f2" if k in lit else "#666666"))
    if mood == "ask":    # signo de pregunta que flota
        bob = math.sin(w * 4 * t) * 1.5
        parts.append('<text x="47" y="{:.1f}" font-family="sans-serif" font-weight="bold" font-size="14" '
                     'fill="#ffd166" stroke="#161616" stroke-width="0.8" paint-order="stroke">?</text>'.format(19 + bob))
    if mood in ("sleep", "empty"):
        for k in range(2):
            ph = (t / LOOP * 4 + k * 0.5) % 1
            parts.append('<text x="{:.1f}" y="{:.1f}" font-family="monospace" font-weight="bold" '
                         'font-size="{:.1f}" fill="#a7a7a7" opacity="{:.2f}">z</text>'.format(
                             42 + ph * 6, max(8, y0 - 1 - ph * 8), 6 + ph * 4, 1 - ph))

    # recortado: sin el aire de arriba/abajo, para poder pegarlo a los bordes de la pantalla
    vb = (6, 44) if crop else (0, 56)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" viewBox="0 {2} 56 {3}" '
            'shape-rendering="crispEdges">{4}</svg>').format(px, round(px * vb[1] / 56), vb[0], vb[1], "".join(parts))


def span(seconds):
    mins = int(seconds // 60)
    return "{} h {:02d} min".format(mins // 60, mins % 60) if mins >= 60 else "{} min".format(mins)


def ago(epoch):
    mins = int((time.time() - epoch) // 60)
    if mins < 1:
        return "ahora"
    if mins < 60:
        return "hace {} min".format(mins)
    return "hace {} h".format(mins // 60)


class Meter(Gtk.Window):
    """Ventana del muñeco. Solo se mueve cuando el usuario la arrastra; el detalle va en otra ventana."""

    def __init__(self):
        super().__init__(title="Claude meter")
        self.config = load_json(CONF, {})
        self.save_pos_id = 0
        self.mood = "sleep"
        self.mood_text = ""
        self.last_msg = None    # (texto, cuándo): queda en la tarjeta por si no lo viste
        self.hovering = False
        self.activity = None  # "work", "ask" o None
        self.data = None
        self.last_seen = 0      # último momento en que se usó Claude Code
        self.chat_text = None   # mensaje espontáneo o reacción a un clic
        self.chat_until = 0
        self.last_said = 0
        self.next_chat = time.time() + random.randint(30, 90)
        # lo que el muñeco "ve"
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.ticks = 0
        self.away = False
        self.away_since = 0
        self.streak_start = time.time()
        self.last_break_tip = 0
        self.app_kind = None
        self.kind_said = {}
        self.ext_retry = 0      # la extensión de GNOME es opcional: si no está, se reintenta cada minuto
        self.song = None
        self.work_since = 0
        self.long_said = False
        self.prev_used = None
        self.press = None       # clic izquierdo pendiente: arrastre o "toque"
        self.dragging = False
        self.drag_end_id = 0
        self.hide_id = 0
        self.t0 = time.time()
        self.frames = {}  # ánimo -> lista de pixbufs del ciclo
        self._setup_css()
        self._setup_window()
        self._build_buddy()
        self._build_details()
        anchor = self.config.get("anchor")
        if anchor:
            self.move(*anchor)
        else:
            self._to_corner()
        self.refresh()
        GLib.timeout_add_seconds(5, self.refresh)
        GLib.timeout_add(FRAME_MS, self._animate)
        GLib.timeout_add(1000, self._poll_activity)

    # ---------- ventana del muñeco ----------
    def _setup_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    @staticmethod
    def _transparent(win):
        visual = win.get_screen().get_rgba_visual()
        if visual:
            win.set_visual(visual)
            win.set_app_paintable(True)

    def _setup_window(self):
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_icon_name("claude-meter")
        self.stick()
        self._transparent(self)
        # al cambiar de tamaño (texto del globito) se conserva la esquina inferior derecha: el muñeco no se corre
        self.set_gravity(Gdk.Gravity.SOUTH_EAST)
        self.connect("configure-event", self._on_configure)
        self.connect("destroy", Gtk.main_quit)

    def _end_drag_later(self):
        # el gestor de ventanas no avisa al soltar: se da por terminado tras un rato sin movimiento
        if self.drag_end_id:
            GLib.source_remove(self.drag_end_id)
        self.drag_end_id = GLib.timeout_add(700, self._drag_done)

    def _drag_done(self):
        self.drag_end_id = 0
        self.dragging = False
        return False

    def _on_configure(self, *_):
        if self.dragging:
            self._end_drag_later()
        if self.save_pos_id:
            GLib.source_remove(self.save_pos_id)
        self.save_pos_id = GLib.timeout_add(600, self._save_pos)

    def _save_pos(self):
        self.save_pos_id = 0
        self.config.pop("pos", None)  # formato viejo (esquina superior izquierda)
        self.config["anchor"] = list(self.get_position())
        os.makedirs(CONF_DIR, exist_ok=True)
        with open(CONF, "w") as f:
            json.dump(self.config, f)
        return False

    def _to_corner(self):
        """Pega el muñeco a la esquina inferior derecha del área útil (sin tapar barras del sistema)."""
        mon = Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)
        area = mon.get_workarea()
        size = self.get_preferred_size()[1]
        self.move(area.x + area.width - size.width - 8, area.y + area.height - size.height - 8)

    # ---------- interfaz ----------
    def _label(self, css, xalign=0):
        lbl = Gtk.Label(xalign=xalign)
        lbl.get_style_context().add_class(css)
        return lbl

    def _limit_row(self, box, name):
        top = Gtk.Box(spacing=6)
        top.pack_start(self._label("name"), False, False, 0)
        top.get_children()[0].set_text(name)
        pct = self._label("pct", xalign=1)
        top.pack_end(pct, False, False, 0)
        bar = Gtk.ProgressBar()
        reset = self._label("reset")
        box.pack_start(top, False, False, 0)
        box.pack_start(bar, False, False, 0)
        box.pack_start(reset, False, False, 0)
        return pct, bar, reset

    def _hover_box(self, win):
        root = Gtk.EventBox()
        root.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        root.connect("enter-notify-event", self._on_enter)
        root.connect("leave-notify-event", self._on_leave)
        win.add(root)
        return root

    def _build_buddy(self):
        root = self._hover_box(self)
        root.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
        root.connect("button-press-event", self._on_press)
        root.connect("motion-notify-event", self._on_motion)
        root.connect("button-release-event", self._on_release)
        buddy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        root.add(buddy)
        # globito con el ánimo y el muñeco, sin fondo
        self.mood_lbl = self._label("bubble")
        self.mood_lbl.set_halign(Gtk.Align.END)
        self.mood_lbl.set_line_wrap(True)       # frases largas en dos líneas, no un globito eterno
        self.mood_lbl.set_max_width_chars(26)
        self.mood_lbl.set_justify(Gtk.Justification.RIGHT)
        self.mascot = Gtk.Image()
        self.mascot.set_size_request(MASCOT, round(MASCOT * 44 / 56))
        self.mascot.set_halign(Gtk.Align.END)
        buddy.pack_start(self.mood_lbl, False, False, 0)
        buddy.pack_start(self.mascot, False, False, 0)
        self.show_all()

    def _build_details(self):
        """Tarjeta con los porcentajes: ventana emergente aparte que se abre a la izquierda del muñeco."""
        self.popup = Gtk.Window(type=Gtk.WindowType.POPUP)
        self._transparent(self.popup)
        root = self._hover_box(self.popup)
        card = Gtk.EventBox()
        card.get_style_context().add_class("card")
        root.add(card)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(210, -1)
        # el padding de CSS no aplica a un EventBox; el margen va en la caja
        box.set_margin_top(10)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        card.add(box)

        top = Gtk.Box(spacing=6)
        title = self._label("head")
        title.set_text("Claude")
        self.model = self._label("model", xalign=1)
        top.pack_start(title, False, False, 0)
        top.pack_end(self.model, False, False, 0)
        box.pack_start(top, False, False, 0)
        self.five = self._limit_row(box, "Sesión (5 h)")
        box.pack_start(Gtk.Box(), False, False, 2)
        self.week = self._limit_row(box, "Semana")
        self.foot = self._label("foot")
        box.pack_start(self.foot, False, False, 2)
        self.last_lbl = self._label("lastmsg")
        self.last_lbl.set_line_wrap(True)
        self.last_lbl.set_max_width_chars(30)
        box.pack_start(self.last_lbl, False, False, 2)
        root.show_all()

    # ---------- detalle al pasar el mouse ----------
    def _on_enter(self, widget, event):
        self.hovering = True
        if self.dragging:
            return False
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = 0
        if not self.popup.get_visible():
            self._show_details()
        return False

    def _on_leave(self, widget, event):
        # al entrar a un hijo también llega un "leave": ese no cuenta
        if event.detail != Gdk.NotifyType.INFERIOR and not self.hide_id:
            self.hovering = False
            self.hide_id = GLib.timeout_add(300, self._hide_details)
        return False

    def _show_details(self):
        """A la izquierda del muñeco y alineada abajo con él; a la derecha si no cabe."""
        ox, oy = self.get_window().get_origin()[1:]
        w, h = self.get_size()
        pw, ph = (lambda n: (n.width, n.height))(self.popup.get_preferred_size()[1])
        area = Gdk.Display.get_default().get_monitor_at_window(self.get_window()).get_workarea()
        x = ox - pw - 6
        if x < area.x:
            x = ox + w + 6
        y = max(area.y, min(oy + h - ph, area.y + area.height - ph))
        self.popup.move(x, y)
        self.popup.show()

    def _hide_details(self):
        self.hide_id = 0
        self.popup.hide()
        return False

    def _on_press(self, widget, event):
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            # todavía no se sabe si es arrastre o un toque: lo decide el movimiento
            self.press = (event.x_root, event.y_root)
        elif event.button == 3:
            self.popup.hide()
            menu = Gtk.Menu()
            item = Gtk.CheckMenuItem(label="Que me hable cuando no lo uso")
            item.set_active(self.config.get("chatty", True))
            item.connect("toggled", self._toggle_chatty)
            menu.append(item)
            item = Gtk.MenuItem(label="Llevar a la esquina")
            item.connect("activate", lambda *_: self._to_corner())
            menu.append(item)
            item = Gtk.MenuItem(label="Cerrar medidor")
            item.connect("activate", lambda *_: self.destroy())
            menu.append(item)
            menu.show_all()
            menu.popup_at_pointer(event)
        return True

    def _on_motion(self, widget, event):
        if self.press and math.hypot(event.x_root - self.press[0], event.y_root - self.press[1]) > 4:
            self.press = None
            # mientras se arrastra no se abre el detalle
            self.dragging = True
            if self.hide_id:
                GLib.source_remove(self.hide_id)
                self.hide_id = 0
            self.popup.hide()
            self.begin_move_drag(1, int(event.x_root), int(event.y_root), event.time)
            self._end_drag_later()
        return False

    def _on_release(self, widget, event):
        if event.button == 1 and self.press:
            self.press = None
            self._say(random.choice(POKE_LINES), 5, force=True)
        return False

    def _toggle_chatty(self, item):
        self.config["chatty"] = item.get_active()
        if not item.get_active():
            self.chat_until = 0
            self._update_bubble()
        self._save_pos()

    # ---------- conversación ----------
    def _say(self, text, seconds=CHAT_SHOW, force=False):
        now = time.time()
        if not force and (now - self.last_said < MIN_GAP or not self.config.get("chatty", True)):
            return False
        self.chat_text = text
        self.chat_until = now + seconds
        self.last_said = now
        self.last_msg = (text, now)
        self.next_chat = max(self.next_chat, now + random.randint(*CHAT_EVERY))
        self._update_bubble()
        return True

    def _dbus(self, name, path, iface, method, args=None):
        return self.bus.call_sync(name, path, iface, method, args, None,
                                  Gio.DBusCallFlags.NONE, 500, None).unpack()

    def _idle_seconds(self):
        try:
            return self._dbus("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core",
                              "org.gnome.Mutter.IdleMonitor", "GetIdletime")[0] / 1000
        except GLib.Error:
            return 0

    def _focused_kind(self, now):
        if now < self.ext_retry:
            return None
        try:
            app = self._dbus(*EXT_BUS, "FocusedApp")[0].lower()
        except GLib.Error:
            self.ext_retry = now + 60
            return None
        return next((kind for kind, keys in APP_KINDS if any(k in app for k in keys)), None)

    def _spotify(self):
        try:
            props = self._dbus("org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2",
                               "org.freedesktop.DBus.Properties", "GetAll",
                               GLib.Variant("(s)", ("org.mpris.MediaPlayer2.Player",)))[0]
        except GLib.Error:
            return None, False
        return (props.get("Metadata") or {}).get("xesam:title"), props.get("PlaybackStatus") == "Playing"

    def _idle_line(self, now):
        """Charla espontánea: motivación, cuidado, preguntas y lo que se sabe del contexto."""
        hour = time.localtime().tm_hour
        lines = MOTIVATION_LINES * 2 + CARE_LINES + QUESTION_LINES
        if now - self.last_seen > CLAUDE_UNUSED:
            lines += IDLE_LINES
        if self.app_kind:  # lo que estás usando ahora pesa bastante
            lines += APP_LINES[self.app_kind] * 3
        if 6 <= hour < 12:
            lines.append("¡Buenos días! ¿Empezamos?")
        elif 12 <= hour < 15:
            lines.append("¿Ya almorzaste? 🍽️")
        elif hour >= 22 or hour < 5:
            lines.append("Ya es tarde… ¿descansamos?")
        five = (self.data or {}).get("five_hour")
        if five and five.get("resets_at", 0) > now and five.get("used_percentage", 0) < 50:
            lines.append("Te queda {:.0f}% de esta sesión, ¡aprovechémoslo!".format(100 - five["used_percentage"]))
        return random.choice(lines)

    def _brain(self, now):
        """Cada segundo: mira si estás, qué usas, qué suena y qué hace Claude, y decide si comentar."""
        self.ticks += 1
        if self.chat_text and self.hovering:  # con el mouse encima no se va: da tiempo a leer
            self.chat_until = max(self.chat_until, now + 3)
        if self.chat_text and now >= self.chat_until:
            self.chat_text = None
            self._update_bubble()

        # ¿estás frente a la pantalla? (cada 2 s)
        if self.ticks % 2 == 0:
            idle = self._idle_seconds()
            if idle >= AWAY_AFTER and not self.away:
                self.away = True
                self.away_since = now - idle
                self._update_bubble()
            elif idle < AWAY_AFTER and self.away:
                self.away = False
                gone = now - self.away_since
                self.streak_start = now
                self._update_bubble()
                self._say(random.choice(BACK_LINES) if gone < 3600 else
                          "¡Volviste! Estuviste fuera {}".format(span(gone)), force=True)
            if (not self.away and now - self.streak_start >= STREAK_BREAK
                    and now - self.last_break_tip >= STREAK_BREAK):
                if self._say("Llevas {} seguido, ¿una pausa? ☕".format(span(now - self.streak_start)), 15):
                    self.last_break_tip = now
        if self.away:
            return

        # ¿qué programa usas? (cada 3 s; solo con la extensión de GNOME)
        if self.ticks % 3 == 0:
            kind = self._focused_kind(now)
            if kind != self.app_kind:
                self.app_kind = kind
                if kind and now - self.kind_said.get(kind, 0) > 600:
                    if self._say(random.choice(APP_LINES[kind])):
                        self.kind_said[kind] = now

        # ¿qué suena? (cada 5 s)
        if self.ticks % 5 == 0:
            title, playing = self._spotify()
            if playing and title and title != self.song:
                if self.song is not None and random.random() < 0.5:
                    self._say(random.choice(SONG_LINES).format(title))
                self.song = title

        # Claude lleva rato trabajando
        if self.activity == "work" and not self.long_said and now - self.work_since > CLAUDE_LONG:
            self.long_said = self._say("Claude sigue en eso… ¿un café mientras? ☕")

        if now >= self.next_chat:
            if not self._say(self._idle_line(now)):
                self.next_chat = now + MIN_GAP

    def _check_usage(self, data):
        """Avisa al cruzar 50, 75 y 90 % de la sesión de 5 h."""
        five = (data or {}).get("five_hour") or {}
        used = five.get("used_percentage", 0) if five.get("resets_at", 0) > time.time() else 0
        if self.prev_used is not None:
            for mark in (50, 75, 90):
                if self.prev_used < mark <= used:
                    self._say("¡Ojo! Ya vas en {:.0f}% de la sesión".format(used), 15, force=True)
        self.prev_used = used

    # ---------- mascota ----------
    def _frame(self, mood, i):
        key = (mood, self.mood)  # trabajar/dudar se pintan con el color del ánimo de uso
        frames = self.frames.setdefault(key, [None] * int(LOOP * 1000 / FRAME_MS))
        if frames[i] is None:  # se dibuja la primera vez que se necesita y queda en caché
            loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
            loader.write(mascot_svg(mood, i * FRAME_MS / 1000, tint=self.mood).encode())
            loader.close()
            frames[i] = loader.get_pixbuf()
        return frames[i]

    def _animate(self):
        if self.get_mapped():
            n = int(LOOP * 1000 / FRAME_MS)
            i = int((time.time() - self.t0) * 1000 / FRAME_MS) % n
            chatting = time.time() < self.chat_until
            idle_look = "wave" if chatting else "sleep" if self.away else self.mood
            self.mascot.set_from_pixbuf(self._frame(self.activity or idle_look, i))
        return True

    def _poll_activity(self):
        sessions = load_json(ACTIVITY, {})
        now = time.time()
        states = {v.get("state") for v in sessions.values()
                  if now - v.get("at", 0) < (ASK_STALE if v.get("state") == "asking" else WORK_STALE)}
        # una pregunta pendiente en cualquier sesión gana: es lo que requiere tu atención
        activity = "ask" if "asking" in states else "work" if "working" in states else None
        seen = [v.get("at", 0) for v in sessions.values()] + [(self.data or {}).get("updated_at", 0)]
        self.last_seen = max(seen)
        if activity:
            self.last_seen = now
        if activity != self.activity:
            finished = self.activity == "work" and activity is None
            if activity == "work" and self.activity != "work":
                self.work_since = now
                self.long_said = False
            self.activity = activity
            if finished:  # Claude terminó una tarea: festejo corto
                self._say(random.choice(DONE_LINES), 12, force=True)
            self._update_bubble()
        self._brain(now)
        return True

    def _update_bubble(self):
        chat = self.chat_text if time.time() < self.chat_until else None
        # una pregunta de Claude manda; luego lo que el muñeco dice; luego qué hace
        # el ánimo ya se ve en la cara del muñeco: el globito solo aparece cuando hay algo que decir
        if self.activity == "ask":
            text = ACTIVITY_TEXT["ask"]
        else:
            text = chat or ("" if self.away else self.mood_text)
        self.mood_lbl.set_text(text)
        self.mood_lbl.set_visible(bool(text))
        if self.last_msg:
            self.last_lbl.set_text("💬 {} · {}".format(self.last_msg[0], ago(self.last_msg[1])))

    def _set_mood(self, data):
        if not data:
            self.mood = "sleep"
            self.mood_text = ""
            self._update_bubble()
            return
        now = time.time()
        live = [w for w in (data.get("five_hour"), data.get("seven_day"))
                if w and w.get("resets_at", 0) > now]
        used = max([float(w.get("used_percentage") or 0) for w in live] or [0])
        self.mood = next((m for limit, m in MOODS if used < limit), "empty")
        text = ""  # sin nada que decir: solo la cara
        if self.mood == "empty":  # agotado: esto sí conviene tenerlo a la vista
            full = min(w["resets_at"] for w in live if float(w.get("used_percentage") or 0) >= 100)
            text = ("Agotado · vuelvo en " if full - now < 86400 else "Agotado · vuelvo el ") + until(full)
        self.mood_text = text
        self._update_bubble()

    # ---------- datos ----------
    def _set_limit(self, row, win):
        pct, bar, reset = row
        ctx = bar.get_style_context()
        ctx.remove_class("warn")
        ctx.remove_class("crit")
        # una ventana vencida o ausente significa que se reinició: arranca de cero
        if not win or win.get("resets_at", 0) <= time.time():
            pct.set_text("0%")
            bar.set_fraction(0)
            reset.set_text("sin uso en esta ventana")
            return
        used = float(win.get("used_percentage") or 0)
        pct.set_text("{:.0f}%".format(used))
        bar.set_fraction(min(used, 100) / 100)
        if used >= 85:
            ctx.add_class("crit")
        elif used >= 60:
            ctx.add_class("warn")
        reset.set_text("se reinicia en " + until(win["resets_at"]) if win["resets_at"] - time.time() < 86400
                       else "se reinicia el " + until(win["resets_at"]))

    def refresh(self):
        data = load_json(DATA, None)
        if not data:
            self.model.set_text("")
            for row in (self.five, self.week):
                row[0].set_text("—")
                row[1].set_fraction(0)
                row[2].set_text("")
            self.foot.set_text("Sin datos: usa Claude Code una vez")
            self._set_mood(None)
            return True

        self.model.set_text(data.get("model") or "")
        self._set_limit(self.five, data.get("five_hour"))
        self._set_limit(self.week, data.get("seven_day"))
        self.data = data
        self._set_mood(data)
        self._check_usage(data)
        updated = data.get("updated_at", 0)
        ctx = self.foot.get_style_context()
        if time.time() - updated > STALE_AFTER:
            ctx.add_class("stale")
        else:
            ctx.remove_class("stale")
        self.foot.set_text("Último uso de Claude " + ago(updated))
        return True


if __name__ == "__main__":
    Meter()
    Gtk.main()
