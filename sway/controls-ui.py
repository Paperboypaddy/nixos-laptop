import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
import sys, subprocess, pathlib, threading, os, socket
import cairo

mode = sys.argv[1] if len(sys.argv) > 1 else "power"
if mode not in ("power", "wireguard"): sys.exit(2)
# One shared socket: opening either control replaces the other.
address = str(pathlib.Path(os.environ["XDG_RUNTIME_DIR"]) / "waybar-controls.sock")
client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    client.connect(address)
except OSError:
    client.close()
else:
    client.sendall(mode.encode())
    client.close()
    sys.exit(0)
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try: os.unlink(address)
except FileNotFoundError: pass
server.bind(address)
server.listen(4)
Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)

def command(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=30)

class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.mode = mode
        self.busy = False
        self.set_decorated(False)
        self.set_default_size(340, 180)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.RIGHT, True)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, 8)
        GtkLayerShell.set_margin(self, GtkLayerShell.Edge.RIGHT, 10)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        self.backdrop = Gtk.Window()
        self.backdrop.set_decorated(False)
        self.backdrop.set_app_paintable(True)
        self.backdrop.set_visual(self.backdrop.get_screen().get_rgba_visual())
        GtkLayerShell.init_for_window(self.backdrop)
        GtkLayerShell.set_layer(self.backdrop, GtkLayerShell.Layer.TOP)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self.backdrop, edge, True)
        self.backdrop.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.backdrop.connect("draw", self.clear)
        self.backdrop.connect("button-press-event", lambda *_: self.dismiss())
        self.connect("key-press-event", lambda _, e: self.dismiss() if e.keyval == Gdk.KEY_Escape else False)
        self.connect("delete-event", lambda *_: self.dismiss())
        self.connect("hide", lambda *_: self.backdrop.hide())
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
        self.add(self.box)
        self.render()
        GLib.timeout_add_seconds(3, self.refresh)

    def clear(self, _, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0,0,0,0)
        cr.paint()
        return True

    def dismiss(self):
        self.hide()
        return True

    def toggle(self, target):
        if self.get_visible() and target == self.mode:
            self.hide()
        else:
            self.mode = target
            self.render()
        return False

    def render(self):
        for child in self.box.get_children(): self.box.remove(child)
        header = Gtk.Box(spacing=8)
        title = Gtk.Label(xalign=0)
        title.set_markup("<span size='large' weight='bold'>"+("WireGuard" if self.mode=="wireguard" else "Battery &amp; power")+"</span>")
        header.pack_start(title, True, True, 0)
        close = Gtk.Button(label="×")
        close.connect("clicked", lambda *_: self.dismiss())
        header.pack_end(close, False, False, 0)
        self.box.pack_start(header, False, False, 0)
        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)
        self.box.pack_start(self.status, False, False, 0)
        self.buttons = []
        if self.mode == "wireguard":
            self.button = Gtk.Button(label="Connect")
            self.button.connect("clicked", lambda *_: self.change("wg-toggle"))
            self.box.pack_start(self.button, False, False, 0)
            self.buttons.append(self.button)
        else:
            for name, desc in [("power-saver","Power saver — maximum battery life"),("balanced","Balanced — everyday use"),("performance","Performance — heavy workloads")]:
                button = Gtk.Button(label=desc)
                button.connect("clicked", lambda _, p=name: self.change("powerprofilesctl", "set", p))
                self.box.pack_start(button, False, False, 0)
                self.buttons.append(button)
        self.error = Gtk.Label(xalign=0)
        self.error.set_line_wrap(True)
        self.box.pack_start(self.error, False, False, 0)
        self.backdrop.show_all()
        self.show_all()
        self.refresh()

    def refresh(self):
        if self.busy or not self.get_visible(): return True
        try:
            if self.mode == "wireguard":
                result = command("systemctl", "is-active", "wg-quick-homelab.service")
                active = result.stdout.strip() == "active"
                self.status.set_text("Homelab tunnel · "+("Connected (service active)" if active else result.stdout.strip() or "Unknown"))
                self.button.set_label("Disconnect" if active else "Connect")
            else:
                result = command("powerprofilesctl", "get")
                profile = result.stdout.strip()
                batteries = list(pathlib.Path("/sys/class/power_supply").glob("BAT*"))
                info = ""
                if batteries:
                    bat = batteries[0]
                    info = (bat/"capacity").read_text().strip()+"% · "+(bat/"status").read_text().strip()+"\n"
                self.status.set_text(info+"Current profile: "+(profile or "Unavailable"))
                for button, name in zip(self.buttons, ("power-saver","balanced","performance")):
                    button.set_sensitive(profile != name)
        except Exception as e: self.error.set_text(str(e))
        return True

    def change(self, *args):
        if self.busy: return
        self.busy = True
        self.error.set_text("Applying…")
        for button in self.buttons: button.set_sensitive(False)
        def worker():
            try:
                result = command(*args)
                error = "" if result.returncode == 0 else result.stderr.strip() or result.stdout.strip() or "Operation failed"
            except Exception as e: error = str(e)
            GLib.idle_add(self.finished, error)
        threading.Thread(target=worker, daemon=True).start()

    def finished(self, error):
        self.busy = False
        self.error.set_text(error)
        for button in self.buttons: button.set_sensitive(True)
        self.refresh()
        return False

panel = Panel()
def listen():
    while True:
        conn, _ = server.accept()
        with conn: target = conn.recv(64).decode()
        if target in ("power","wireguard"): GLib.idle_add(panel.toggle, target)
threading.Thread(target=listen, daemon=True).start()
Gtk.main()
