"""Router benchmark: one result -> board -> hardware-independent quality numbers.

Every router under test gets the same input (bench/bassberry_bench.dsn = bench/bassberry_bench.kicad_pcb, 0.15 mm
clearance, In2 = GND plane) and its result is judged on the SAME KiCad board with the SAME DRC, so the numbers
compare algorithms, not machines:
  routed nets / unconnected items (KiCad connectivity), vias, wire length per layer, DRC violations (kicad-cli),
  plus the wall time and the iterations the router reported (time is normalised separately by the machine index).

usage: kicad-python _bench_eval.py <name> <result.ses | result.kicad_pcb> [--time SECONDS] [--iters N] [--machine M]
       appends one JSON line to bench/results.jsonl and writes bench/<name>.kicad_pcb + bench/<name>_drc.json
"""
import sys, os, json, subprocess, time
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(HERE, "bench")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def board_metrics(b):
    mm = pcbnew.ToMM
    names = {pcbnew.F_Cu: "F", pcbnew.In1_Cu: "In1", pcbnew.In2_Cu: "In2", pcbnew.B_Cu: "B"}
    length = {n: 0.0 for n in names.values()}; vias = 0; n_tr = 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias += 1
        else:
            n_tr += 1
            length[names.get(t.GetLayer(), "?")] = length.get(names.get(t.GetLayer(), "?"), 0) + mm(t.GetLength())
    b.BuildConnectivity()
    try:
        unc = int(b.GetConnectivity().GetUnconnectedCount(False))
    except TypeError:
        unc = int(b.GetConnectivity().GetUnconnectedCount())
    return dict(tracks=n_tr, track_mm={k: round(v) for k, v in length.items()}, track_mm_total=round(sum(length.values())),
                vias=vias, unconnected=unc)


def main():
    a = sys.argv[1:]
    opt = {}
    for k in ("--time", "--iters", "--machine", "--note"):
        if k in a:
            i = a.index(k); opt[k[2:]] = a[i + 1]; del a[i:i + 2]
    name, res = a[0], a[1]
    src = os.path.join(BENCH, "bassberry_bench.kicad_pcb")
    out = os.path.join(BENCH, name + ".kicad_pcb")
    if res.lower().endswith(".ses"):
        b = pcbnew.LoadBoard(src)
        before = sum(1 for t in b.GetTracks())
        assert pcbnew.ImportSpecctraSES(b, res), "SES import failed: " + res
        for t in b.GetTracks():   # the import resets every via drill to the default
            if t.GetClass() == "PCB_VIA":
                w = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))
                t.SetDrill(pcbnew.FromMM(0.2 if w < 0.5 else 0.3))
        pcbnew.SaveBoard(out, b)
    else:
        import shutil
        shutil.copy(res, out)
        b = pcbnew.LoadBoard(out)
    # project files next to the result board so DRC uses the same rules as the flow
    for e in (".kicad_pro", ".kicad_dru"):
        p = os.path.join(BENCH, "bassberry_bench" + e)
        if os.path.exists(p):
            import shutil
            shutil.copy(p, os.path.join(BENCH, name + e))
    # refill the GND zones: the placed board carries a stale fill, which DRC would report as hundreds of false
    # 'copper pour' clearance violations (first eval 2026-10-29: 499 clearance + 199 hole clearance, all vs GND zones)
    filler = pcbnew.ZONE_FILLER(b)
    filler.Fill(b.Zones())
    pcbnew.SaveBoard(out, b)
    b = pcbnew.LoadBoard(out)
    m = board_metrics(b)
    drc = os.path.join(BENCH, name + "_drc.json")
    r = subprocess.run([CLI, "pcb", "drc", "--format", "json", "--all-track-errors", "--schematic-parity", "-o", drc, out],
                       capture_output=True, text=True)
    d = json.load(open(drc, encoding="utf-8")) if os.path.exists(drc) else {}
    kinds = {}
    for v in d.get("violations", []):
        kinds[v.get("type", "?")] = kinds.get(v.get("type", "?"), 0) + 1
    ROUTE_KINDS = ("clearance", "hole_clearance", "track_dangling", "via_dangling", "shorting_items", "tracks_crossing",
                   "hole_to_hole", "holes_co_located", "track_width", "via_diameter", "copper_edge_clearance")
    m["drc"] = dict(violations=len(d.get("violations", [])), unconnected=len(d.get("unconnected_items", [])),
                    routing=sum(v for k, v in kinds.items() if k in ROUTE_KINDS), kinds=kinds)
    nets_total = sum(1 for n in b.GetNetsByName().items() if n[0] and n[0] != "GND")
    row = dict(name=name, stamp=time.strftime("%Y-%m-%d %H:%M"), result=os.path.basename(res), nets_total=nets_total,
               time_s=float(opt["time"]) if "time" in opt else None, iters=int(opt["iters"]) if "iters" in opt else None,
               machine=opt.get("machine", ""), note=opt.get("note", ""), **m)
    with open(os.path.join(BENCH, "results.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(json.dumps(row, indent=1))


if __name__ == "__main__":
    main()
