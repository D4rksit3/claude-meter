# Claude meter

![Medidor con la sesión al 67 % y la semana al 31 %](docs/captura.png)

Widget pequeño para Linux que se queda **siempre encima** de las demás ventanas y muestra cuánto llevas usado de tu plan de Claude:

- **Sesión (5 h)** y **Semana**: porcentaje usado, barra (verde → ámbar desde 60 % → rojo desde 85 %) y cuándo se reinicia
- modelo en uso y hace cuánto se actualizó (se pone ámbar si el dato tiene más de 15 min)

Hecho con Python + GTK 3. Probado en Ubuntu 26.04 con GNOME (Wayland).

> Proyecto personal, no afiliado a Anthropic.

## Cómo obtiene los datos

Los porcentajes del plan solo los conoce [Claude Code](https://docs.claude.com/en/docs/claude-code). Este repo trae una
**status line** (`statusline.py`) que Claude Code ejecuta en cada respuesta: recibe el bloque `rate_limits`,
lo imprime abajo en la terminal (`Opus · 5h 17% · semana 31% · contexto 13%`) y lo guarda en
`~/.cache/claude-meter.json`. El widget solo lee ese archivo cada 5 s; no se conecta a nada ni usa credenciales.

Requiere una suscripción de Claude (Pro/Max/Team): con API key no hay límites de plan que mostrar.
Los números se actualizan cuando usas Claude Code; si no lo usas, el pie te avisa que el dato está viejo.
Cuando una ventana pasa su hora de reinicio, el widget la muestra en 0 %.

## Requisitos

```bash
sudo apt install python3-gi gir1.2-gtk-3.0
```

## Instalar

```bash
git clone https://github.com/D4rksit3/claude-meter.git
cd claude-meter
./install.sh              # o ./install.sh --autostart para que arranque al iniciar sesión
```

El instalador agrega la `statusLine` a `~/.claude/settings.json` (con copia `.bak`). Si ya tienes una, no la toca
y te muestra la línea para ponerla a mano. Para quitarlo: `./uninstall.sh`.

### Si Claude Code corre como otro usuario

Por ejemplo, si lo usas como `root` y el widget corre con tu usuario, indica dónde escribir y de quién es el archivo:

```json
"statusLine": {
  "type": "command",
  "command": "CLAUDE_METER_OUT=/home/TU_USUARIO/.cache/claude-meter.json CLAUDE_METER_OWNER=1000:1000 python3 /root/.claude/claude-meter-statusline.py"
}
```

## Uso

- **Mover:** arrastra con clic izquierdo (recuerda la posición).
- **Cerrar:** clic derecho → *Cerrar medidor*. Se vuelve a abrir desde el menú de aplicaciones.

## Ver también

[spotify-mini-widget](https://github.com/D4rksit3/spotify-mini-widget), el mismo estilo para Spotify.

## Licencia

MIT
