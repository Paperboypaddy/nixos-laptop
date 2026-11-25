import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango
Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
import subprocess, threading, pathlib, os, json, shlex, fcntl

repo = pathlib.Path.home() / "nixos-config"
lock = (pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / ("config-update-%d.lock" % os.getuid())).open("a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    subprocess.run(["swaymsg", '[title="^NixOS Update Manager$"] kill'], capture_output=True)
    raise SystemExit(0)

def run(*args):
    return subprocess.check_output(args, cwd=repo, text=True, stderr=subprocess.STDOUT).strip()

class Manager(Gtk.Window):
    def __init__(self):
        super().__init__(title="NixOS Update Manager")
        self.set_default_size(440, 420)
        self.set_decorated(False)
        self.set_resizable(True)
        self.connect("key-press-event", self.keypress)
        self.busy = False
        self.connect("delete-event", lambda *_: self.busy)
        self.connect("destroy", Gtk.main_quit)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        self.add(box)
        heading = Gtk.Label()
        heading.set_markup("<span size='xx-large' weight='bold'>System updates</span>")
        heading.set_xalign(0)
        header = Gtk.Box(spacing=8)
        header.pack_start(heading, True, True, 0)
        close = Gtk.Button(label="×")
        close.connect("clicked", lambda *_: self.close())
        header.pack_end(close, False, False, 0)
        box.pack_start(header, False, False, 0)
        self.status = Gtk.Label(label="Loading repository…", xalign=0)
        self.status.set_line_wrap(True)
        box.pack_start(self.status, False, False, 0)
        self.targets = Gtk.ComboBoxText()
        for renderer in self.targets.get_cells():
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            renderer.set_property("width-chars", 24)
            renderer.set_property("max-width-chars", 28)
        box.pack_start(self.targets, False, False, 0)
        buttons = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        box.pack_start(buttons, False, False, 0)
        self.controls = [self.targets]
        for index, (label, action) in enumerate([("Refresh", self.refresh), ("Update current", lambda: self.apply(False)), ("Switch & apply", lambda: self.apply(True)), ("Rebuild checkout", self.rebuild)]):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _, fn=action: fn())
            buttons.attach(button, index % 2, index // 2, 1, 1)
            self.controls.append(button)
        self.log = Gtk.TextView(editable=False, monospace=True, cursor_visible=False)
        self.log.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.log)
        box.pack_start(scroll, True, True, 0)
        self.show_all()
        self.connect("map-event", self.position)
        GLib.timeout_add(350, self.position)
        self.refresh()

    def keypress(self, widget, event):
        if event.keyval == 65307 and not self.busy:
            self.close()
            return True
        return False

    def position(self, *_):
        try:
            outputs = json.loads(run("swaymsg", "-t", "get_outputs"))
            output = next(o for o in outputs if o.get("focused"))
            rect = output["rect"]
            tree = json.loads(run("swaymsg", "-t", "get_tree"))
            def find(n):
                if n.get("name") == "NixOS Update Manager" and n.get("type") == "con":
                    return n
                for child in n.get("nodes", []) + n.get("floating_nodes", []):
                    found = find(child)
                    if found: return found
            node = find(tree)
            if not node: return False
            width = node["rect"]["width"]
            run("swaymsg", '[title="^NixOS Update Manager$"] move position %d %d' % (max(rect["x"], rect["x"] + rect["width"] - width - 10), rect["y"] + 36))
        except Exception:
            pass
        return False

    def append(self, line):
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), line + "\n")
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        return False

    def stream(self, *args):
        GLib.idle_add(self.append, "$ " + shlex.join(args))
        p = subprocess.Popen(args, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
        for line in p.stdout:
            GLib.idle_add(self.append, line.rstrip())
        if p.wait():
            raise RuntimeError("Command failed: " + shlex.join(args))

    def task(self, fn):
        if self.busy: return
        self.busy = True
        for c in self.controls: c.set_sensitive(False)
        def work():
            try: fn()
            except Exception as e:
                GLib.idle_add(self.append, str(e))
                GLib.idle_add(self.status.set_text, "Operation failed. See details below.")
            finally: GLib.idle_add(self.done)
        threading.Thread(target=work, daemon=True).start()

    def done(self):
        self.busy = False
        for c in self.controls: c.set_sensitive(True)
        return False

    def refresh(self):
        def work():
            self.stream("git", "fetch", "--prune", "origin")
            branch = run("git", "branch", "--show-current") or "(detached)"
            head = run("git", "rev-parse", "--short", "HEAD")
            refs = run("git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").splitlines()
            targets = [(x, x) for x in refs if x.startswith("origin/") and x != "origin/HEAD"]
            try:
                prs = json.loads(run("gh", "pr", "list", "--state", "open", "--limit", "100", "--json", "number,title"))
                targets += [("pr:"+str(p["number"]), "PR #"+str(p["number"])+" — "+p["title"]) for p in prs]
            except Exception as e:
                GLib.idle_add(self.append, "PR listing unavailable: "+str(e))
            try:
                pending = run("git", "log", "--oneline", "HEAD..@{u}")
            except subprocess.CalledProcessError:
                pending = ""
            GLib.idle_add(self.populate, targets, branch+" · "+head)
            GLib.idle_add(self.append, "Pending commits:\n"+(pending or "None found (or no upstream)."))
        self.task(work)

    def populate(self, targets, status):
        self.targets.remove_all()
        for ident, label in targets: self.targets.append(ident, label)
        self.targets.set_active(0)
        self.status.set_text(status)
        GLib.timeout_add(150, self.position)
        return False

    def confirm(self, message):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.OK_CANCEL, text=message)
        answer = dialog.run()
        dialog.destroy()
        return answer == Gtk.ResponseType.OK

    def clean(self):
        if run("git", "status", "--porcelain"):
            raise RuntimeError("Checkout has local changes. Commit or stash them first.")

    def build(self):
        # Authenticate through the existing graphical polkit agent, never a terminal.
        self.stream("pkexec", "/run/current-system/sw/bin/nixos-rebuild", "switch")
        GLib.idle_add(self.status.set_text, "Applied successfully. Reboot or relog if system/session components changed.")
        subprocess.run(["pkill", "-SIGUSR2", "waybar"], check=False)

    def rebuild(self):
        if self.confirm("Build and activate the current checkout?"):
            self.task(self.build)

    def apply(self, switch):
        target = self.targets.get_active_id() if switch else None
        if switch and not target: return
        if not self.confirm("Switch to "+target+" and rebuild NixOS?" if switch else "Fetch, fast-forward and rebuild the current branch?"): return
        def work():
            self.clean()
            old = run("git", "rev-parse", "HEAD")
            GLib.idle_add(self.append, "Previous checkout: "+old)
            self.stream("git", "fetch", "--prune", "origin")
            if target and target.startswith("pr:"):
                self.stream("gh", "pr", "checkout", target[3:])
            elif target:
                name = target.removeprefix("origin/")
                local = run("git", "branch", "--list", name)
                if local:
                    self.stream("git", "switch", "--", name)
                    self.stream("git", "merge", "--ff-only", target)
                else:
                    self.stream("git", "switch", "--track", target)
            else:
                self.stream("git", "merge", "--ff-only", "@{u}")
            self.build()
        self.task(work)

Manager()
Gtk.main()
