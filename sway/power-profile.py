"""Root-only, fixed Intel CPU profiles. Reconcile after TLP or firmware changes."""
import pathlib, sys, os, time, fcntl
P = pathlib.Path
state = P("/var/lib/laptop-power/profile")
cpu = P("/sys/devices/system/cpu")
rapl = P("/sys/class/powercap/intel-rapl:0")
profiles = {
    "ultra-saver": (700000, 0, "powersave", "power", 3, 3),
    "efficiency": (4400000, 1, "powersave", "balance_power", 5, 12),
    "balanced": (4400000, 1, "powersave", "balance_performance", 12, 25),
    "performance": (4400000, 1, "performance", "performance", 28, 60),
}
def put(path, value):
    value = str(value)
    for attempt in range(20):
        actual = path.read_text().strip()
        if actual == value:
            return
        if attempt % 5 == 0:
            path.write_text(value)
        time.sleep(0.05)
    actual = path.read_text().strip()
    if actual != value:
        raise RuntimeError(f"{path.name}: requested {value}, got {actual}")
def selected():
    return state.read_text().strip() if state.exists() else "ultra-saver"
def apply(name):
    maximum, turbo, governor, epp, pl1, pl2 = profiles[name]
    if rapl.joinpath("constraint_0_name").read_text().strip() != "long_term" or rapl.joinpath("constraint_1_name").read_text().strip() != "short_term":
        raise RuntimeError("Unexpected RAPL constraint layout")
    put(rapl/"constraint_0_power_limit_uw", pl1*1000000)
    put(rapl/"constraint_1_power_limit_uw", pl2*1000000)
    pstate = cpu/"intel_pstate"
    # Clear global percentage restrictions before changing per-policy limits.
    # The driver rounds zero up to the hardware minimum.
    if int((pstate/"min_perf_pct").read_text()) > 10:
        (pstate/"min_perf_pct").write_text("0")
    put(pstate/"max_perf_pct", 100)
    put(pstate/"no_turbo", 1-turbo)
    time.sleep(0.15) if name != selected() else None
    for policy in sorted((cpu/"cpufreq").glob("policy*")):
        put(policy/"scaling_governor", governor)
        put(policy/"scaling_min_freq", 400000)
        ceiling = min(maximum, int((policy/"cpuinfo_max_freq").read_text()))
        put(policy/"scaling_max_freq", ceiling)
        put(policy/"energy_performance_preference", epp)
def reconcile(name=None):
    with open("/run/laptop-power.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = selected()
        try:
            apply(name or old)
        except Exception:
            if name and name != old:
                try: apply(old)
                except Exception as e: print("Restore failed:", e, file=sys.stderr)
            raise
        if name:
            state.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            tmp = state.with_suffix(".tmp")
            tmp.write_text(name+"\n")
            tmp.chmod(0o644)
            tmp.replace(state)
if __name__ == "__main__":
    if os.geteuid() != 0: sys.exit("Root required")
    if len(sys.argv) != 2: sys.exit("Expected a profile or reconcile")
    arg = sys.argv[1]
    if arg == "telemetry":
        import json
        print(json.dumps({key: (rapl/key).read_text().strip() for key in ("energy_uj", "max_energy_range_uj", "constraint_0_power_limit_uw")}))
    elif arg == "reconcile" or arg in profiles:
        try: reconcile(None if arg == "reconcile" else arg)
        except Exception as e: sys.exit(str(e))
    else: sys.exit("Invalid profile")
