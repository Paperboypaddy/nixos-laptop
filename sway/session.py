import os, json, subprocess, time, pathlib, sys, fcntl, shutil
os.umask(0o077)
state = pathlib.Path(os.environ.get("XDG_STATE_HOME", str(pathlib.Path.home()/".local/state"))) / "sway-session"
state.mkdir(mode=0o700, parents=True, exist_ok=True)
file = state / "session.json"
apps = {"foot":"foot", "kitty":"kitty", "librewolf":"librewolf", "bitwarden":"bitwarden", "bitwarden-desktop":"bitwarden"}
def ipc(*args):
    return json.loads(subprocess.check_output(["swaymsg", *args], text=True))
def cmd(s):
    result = ipc(s)
    if not all(x.get("success") for x in result):
        raise RuntimeError(str(result))
def windows():
    result = []
    def walk(n, ws=None, floating=False, layout="splith"):
        if n["type"] == "workspace":
            ws = n["name"]
        app = (n.get("app_id") or (n.get("window_properties") or {}).get("class") or "").lower()
        if app and ws and ws != "__i3_scratch":
            result.append(dict(id=n["id"], app=app, ws=ws, floating=floating, rect=n["rect"], layout=layout, focused=n.get("focused",False), fullscreen=n.get("fullscreen_mode",0)))
        for child in n.get("nodes",[]):
            walk(child,ws,floating,n.get("layout","splith"))
        for child in n.get("floating_nodes",[]):
            walk(child,ws,True,n.get("layout","splith"))
    walk(ipc("-t","get_tree"))
    return result
def save():
    rows = [w for w in windows() if w["app"] in apps]
    tmp = state / ("snapshot-%d.tmp" % os.getpid())
    tmp.write_text(json.dumps(rows))
    tmp.replace(file)
def restore():
    if not file.exists(): return
    rows = json.loads(file.read_text())
    used = set()
    browser_started = False
    for row in rows:
        app = row["app"]
        if app not in apps: continue
        executable = shutil.which(apps[app])
        if not executable: continue
        match = next((w for w in windows() if w["app"] == app and w["id"] not in used),None)
        if not match and (app != "librewolf" or not browser_started):
            subprocess.Popen([executable], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if app == "librewolf": browser_started = True
        for _ in range(75):
            match = next((w for w in windows() if w["app"] == app and w["id"] not in used),None)
            if match: break
            time.sleep(.2)
        if not match: continue
        ident = match["id"]
        used.add(ident)
        prefix = "[con_id=%d] " % ident
        try:
            cmd(prefix + "move container to workspace " + json.dumps(row["ws"]))
            if row["floating"]:
                rect = row["rect"]
                cmd(prefix + "floating enable")
                cmd(prefix + "resize set %d px %d px" % (rect["width"],rect["height"]))
                cmd(prefix + "move position %d px %d px" % (rect["x"],rect["y"]))
            elif row["layout"] in ("splith","splitv","tabbed","stacked"):
                cmd(prefix + "layout " + ("stacking" if row["layout"] == "stacked" else row["layout"]))
            if row.get("fullscreen"): cmd(prefix + "fullscreen enable")
        except RuntimeError as e: print(e, file=sys.stderr)
    focused = next((r for r in rows if r["focused"]),None)
    if focused: cmd("workspace " + json.dumps(focused["ws"]))
if sys.argv[1:] == ["logout"]:
    save()
    cmd("exit")
elif sys.argv[1:] == ["save"]:
    save()
else:
    lock = (state / "lock").open("a")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: sys.exit(0)
    try: restore()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e: print(e, file=sys.stderr)
    while True:
        time.sleep(15)
        try:
            if windows(): save()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError): break
