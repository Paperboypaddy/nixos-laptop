import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
import sys, subprocess, pathlib, threading, os, socket
import cairo
import time, json

PROFILES = [("ultra-saver", "Ultra saver — 700 MHz · 3 W"), ("efficiency", "Efficiency — dynamic turbo · 5 W"), ("balanced", "Balanced — dynamic turbo · 12 W"), ("performance", "Performance — full turbo · 28 W")]

def read(path):
    try: return pathlib.Path(path).read_text().strip()
    except OSError: return None


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
        self.sample = None
        self.refreshing = False
        self.generation = 0
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
        self.generation += 1
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
            for name, desc in PROFILES:
                button = Gtk.Button(label=desc)
                button.connect("clicked", lambda _, p=name: self.change("sudo", "-n", os.environ["LAPTOP_POWER_HELPER"], p))
                self.box.pack_start(button, False, False, 0)
                self.buttons.append(button)
        self.error = Gtk.Label(xalign=0)
        self.error.set_line_wrap(True)
        self.box.pack_start(self.error, False, False, 0)
        self.backdrop.show_all()
        self.show_all()
        for button in self.buttons: button.set_sensitive(not self.busy)
        self.refresh()

    def refresh(self):
        if self.busy or self.refreshing or not self.get_visible(): return True
        self.refreshing = True
        target, generation = self.mode, self.generation
        threading.Thread(target=self.collect, args=(target, generation), daemon=True).start()
        return True

    def collect(self, target, generation):
        try:
            if target == "wireguard":
                result = command("systemctl", "is-active", "wg-quick-homelab.service")
                active = result.stdout.strip() == "active"
                status = "Homelab tunnel · "+("Connected (service active)" if active else result.stdout.strip() or "Unknown")
                labels = ["Disconnect" if active else "Connect"]
            else:
                profile = read("/var/lib/laptop-power/profile") or "ultra-saver"
                batteries = list(pathlib.Path("/sys/class/power_supply").glob("BAT*"))
                info = ""
                if batteries:
                    bat = batteries[0]
                    info = (bat/"capacity").read_text().strip()+"% · "+(bat/"status").read_text().strip()+"\n"
                rapl = pathlib.Path("/sys/class/powercap/intel-rapl:0")
                limit = read(rapl/"constraint_0_power_limit_uw")
                energy = read(rapl/"energy_uj")
                maximum_energy = read(rapl/"max_energy_range_uj")
                if energy is None or limit is None:
                    result = command("sudo", "-n", os.environ["LAPTOP_POWER_HELPER"], "telemetry")
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        energy = data["energy_uj"]
                        maximum_energy = data["max_energy_range_uj"]
                        limit = data["constraint_0_power_limit_uw"]
                watts = "unavailable"
                if energy is not None:
                    now = time.monotonic()
                    value = int(energy)
                    if self.sample:
                        previous, stamp = self.sample
                        delta = value - previous
                        if delta < 0:
                            delta += int(maximum_energy or 0)
                        if delta >= 0 and now > stamp:
                            watts = f"{delta / (now-stamp) / 1e6:.1f} W"
                    self.sample = (value, now)
                freqs = [read(p) for p in pathlib.Path("/sys/devices/system/cpu/cpufreq").glob("policy*/scaling_cur_freq")]
                freqs = [int(x) for x in freqs if x]
                freq = f"{max(freqs)/1e6:.2f} GHz" if freqs else "unavailable"
                temps = [read(p/"temp") for p in pathlib.Path("/sys/class/thermal").glob("thermal_zone*") if read(p/"type") == "x86_pkg_temp"]
                temp = f"{int(temps[0])/1000:.0f}°C" if temps and temps[0] else "unavailable"
                budget = f"{int(limit)/1e6:g} W" if limit else "unavailable"
                status = info+"Selected: "+profile+"\nCPU: "+freq+" · "+temp+"\nPackage: "+watts+" · PL1: "+budget
                labels = [("✓ " if profile == name else "")+desc for name, desc in PROFILES]
            GLib.idle_add(self.refresh_done, generation, status, labels, "")
        except Exception as e:
            GLib.idle_add(self.refresh_done, generation, "", [], str(e))

    def refresh_done(self, generation, status, labels, error):
        self.refreshing = False
        if generation != self.generation:
            self.refresh()
        elif not self.busy and self.get_visible():
            if error:
                self.error.set_text(error)
            else:
                self.status.set_text(status)
                for button, label in zip(self.buttons, labels):
                    if button.get_label() != label: button.set_label(label)
        return False

    def change(self, *args):
        if self.busy: return
        self.busy = True
        self.generation += 1
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
