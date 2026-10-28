"""Routing metrics per flow run, so routing changes are compared on numbers, not impressions.

Reads route/<pass>.log (srouter iteration lines), route/full_flow.log, route/postroute.log, route/drc.json and the board;
appends one JSON line per run to route/metrics.jsonl and keeps the logs of the run in route/runs/<stamp>/.

  per pass   : wall time, iterations, s/iteration (median, max), conflicting nets / cells per iteration,
               iteration where conflicts stopped falling (plateau), unrouted at the end (+ which nets)
  per run    : git commit, flow knobs (route.py constants), total route time, repair rounds, DRC errors / unconnected,
               twin FAIL counts, vias by net class, track length per copper layer (In2 = wires on the GND plane)

usage: kicad-python route_metrics.py [project_dir] [--note "text"]
       python route_metrics.py --report [project_dir]        table of all runs
"""
import os, sys, re, json, glob, shutil, statistics, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, "..", "bassberry"))
IT = re.compile(r"iter\s+(\d+):\s+(\d+) nets routed in (\d+) batches,\s+(\d+) conflicting nets \((\d+) cells\),\s+(\d+) unroutable,\s+([\d.]+)s")
PASSES = ["pass0_trunk", "pass1a_heavy", "pass1b_local", "pass2_fast", "pass3_rest",
          "repair1a", "repair1b", "repair2a", "repair2b", "repair3a", "repair3b"]


def pass_metrics(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    its = [tuple(float(x) for x in m.groups()) for m in IT.finditer(txt)]
    m = re.search(r"\[([\d.]+)s total\]", txt)
    bad = [l.strip()[2:] for l in txt.splitlines() if l.strip().startswith("!") and "diff pair" not in l]
    out = dict(iters=len(its), total_s=float(m.group(1)) if m else None, done=bool(m),
               unrouted=len(bad), unrouted_nets=[b.split(":")[0] for b in bad][:20])
    if its:
        ts = [i[6] for i in its]; conf = [int(i[3]) for i in its]
        out.update(s_per_iter_med=round(statistics.median(ts), 1), s_per_iter_max=round(max(ts), 1),
                   conflicts=conf, cells=[int(i[4]) for i in its])
        best = min(conf); plateau = next(k for k, c in enumerate(conf) if c == best)
        out["plateau_iter"] = plateau + 1            # first iteration at the final minimum: the rest was spent for nothing
        out["wasted_s"] = round(sum(ts[plateau + 1:]), 1)
    return out


def board_metrics(pcb):
    try:
        import pcbnew
    except ImportError:
        return {}
    b = pcbnew.LoadBoard(pcb); mm = pcbnew.ToMM
    names = {pcbnew.F_Cu: "F", pcbnew.In1_Cu: "In1", pcbnew.In2_Cu: "In2", pcbnew.B_Cu: "B"}
    length = {n: 0.0 for n in names.values()}; vias = {}; n_tr = 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            k = "GND" if t.GetNetname() == "GND" else "signal/power"
            vias[k] = vias.get(k, 0) + 1
        else:
            n_tr += 1
            length[names.get(t.GetLayer(), "?")] = length.get(names.get(t.GetLayer(), "?"), 0) + mm(t.GetLength())
    b.BuildConnectivity()
    try:
        unc = int(b.GetConnectivity().GetUnconnectedCount(False))
    except TypeError:
        unc = int(b.GetConnectivity().GetUnconnectedCount())
    return dict(tracks=n_tr, track_mm={k: round(v) for k, v in length.items()}, vias=vias, unconnected=unc)


def knobs():
    src = open(os.path.join(HERE, "route.py"), encoding="utf-8").read()
    k = {}
    for name in ("IN2", "VIA_PAD_INSET", "KEEPOUT_PASSES", "CLR", "RIP"):
        m = re.search(rf"^{name}\s*=\s*(.+?)(\s+#.*)?$", src, re.M)
        if m:
            k[name] = m.group(1).strip()
    k["passes"] = re.findall(r'\("(pass\w+)", \w+, (\[.*?\])\)', src)
    pb = open(os.path.join(HERE, "pcb_build.py"), encoding="utf-8").read()
    m = re.search(r"^PRE_GND_VIAS\s*=\s*(\w+)", pb, re.M)
    k["PRE_GND_VIAS"] = m.group(1) if m else "True"
    return k


def collect(prj, note=""):
    rd = os.path.join(prj, "route")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        commit = subprocess.run(["git", "-C", prj, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = ""
    run = dict(stamp=stamp, commit=commit, note=note, knobs=knobs(), passes={})
    for p in PASSES:
        f = os.path.join(rd, p + ".log")
        if os.path.exists(f) and os.path.getmtime(f) > time.time() - 6 * 3600:
            run["passes"][p] = pass_metrics(f)
    run["route_s"] = round(sum(v.get("total_s") or 0 for v in run["passes"].values()))
    drc = os.path.join(rd, "drc.json")
    if os.path.exists(drc):
        d = json.load(open(drc, encoding="utf-8"))
        run["drc"] = dict(violations=len(d.get("violations", [])), unconnected=len(d.get("unconnected_items", [])),
                          parity=len(d.get("schematic_parity", [])))
    pr = os.path.join(rd, "postroute.log")
    if os.path.exists(pr):
        t = open(pr, encoding="utf-8", errors="replace").read()
        run["twins"] = {m.group(1): int(m.group(2)) for m in re.finditer(r"== layer (\d\w?):.*?-> \d+ pass, \d+ warn, (\d+) FAIL", t, re.S)}
        m = re.search(r"via_off_pad: (\d+) vias moved off SMD pads, (\d+) could not move", t)
        if m:
            run["via_off_pad"] = dict(moved=int(m.group(1)), stuck=int(m.group(2)))
        m = re.search(r"z2 stitch: .*?placed (\d+).*?unconnected (\d+) -> (\d+)", t)
        if m:
            run["z2"] = dict(placed=int(m.group(1)), unc_before=int(m.group(2)), unc_after=int(m.group(3)))
    pcb = os.path.join(prj, "bassberry.kicad_pcb")
    if os.path.exists(pcb):
        run["board"] = board_metrics(pcb)
    keep = os.path.join(rd, "runs", stamp); os.makedirs(keep, exist_ok=True)
    for f in glob.glob(os.path.join(rd, "*.log")) + [drc, os.path.join(rd, "bassberry_routed_raw.kicad_pcb")]:
        if os.path.exists(f):
            shutil.copy(f, keep)
    with open(os.path.join(rd, "metrics.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(run) + "\n")
    return run


def report(prj):
    rows = [json.loads(l) for l in open(os.path.join(prj, "route", "metrics.jsonl"), encoding="utf-8") if l.strip()]
    print(f"{'run':16} {'commit':8} {'route min':>9} {'1b min':>7} {'1b s/it':>7} {'1b plateau':>10} {'unrouted':>8} {'DRC':>5} {'unc':>4}  note")
    for r in rows:
        p1b = r["passes"].get("pass1b_local", {})
        unr = sum(v.get("unrouted", 0) for k, v in r["passes"].items() if not k.startswith("repair"))
        print(f"{r['stamp']:16} {r['commit']:8} {r['route_s'] / 60:9.0f} {(p1b.get('total_s') or 0) / 60:7.0f} "
              f"{p1b.get('s_per_iter_med', 0):7} {str(p1b.get('plateau_iter', '')) + '/' + str(p1b.get('iters', '')):>10} "
              f"{unr:8} {r.get('drc', {}).get('violations', '-'):>5} {r.get('drc', {}).get('unconnected', '-'):>4}  {r['note']}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    note = ""
    if "--note" in argv:
        i = argv.index("--note"); note = argv[i + 1]; del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    prj = args[0] if args else PRJ
    if "--report" in sys.argv:
        report(prj)
    else:
        r = collect(prj, note)
        print(json.dumps({k: v for k, v in r.items() if k != "knobs"}, indent=1)[:4000])
