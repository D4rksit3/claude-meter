// Expone por D-Bus la clase de la ventana enfocada ("code", "firefox"…) para el widget claude-meter.
// En Wayland ninguna app puede saberlo por su cuenta; solo el propio GNOME Shell.
// Nunca entrega títulos de ventana ni contenido.
import Gio from 'gi://Gio';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const IFACE = `
<node>
  <interface name="pe.d4rksit3.ClaudeMeter">
    <method name="FocusedApp">
      <arg type="s" direction="out" name="app"/>
    </method>
  </interface>
</node>`;

export default class ClaudeMeterExtension extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, '/pe/d4rksit3/ClaudeMeter');
    }

    disable() {
        this._dbus?.unexport();
        this._dbus = null;
    }

    FocusedApp() {
        const win = global.display.focus_window;
        return win ? (win.get_wm_class() ?? '') : '';
    }
}
