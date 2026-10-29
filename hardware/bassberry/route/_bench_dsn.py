"""Benchmark input: the placed, unrouted Bassberry board as one plain DSN (all nets, no net split, no keep-outs,
In2 closed as GND plane) + the raw kicad_pcb. usage: kicad-python _bench_dsn.py out_dir"""
import sys, os, re, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import pcbnew
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bassberry_placed.kicad_pcb")
b = pcbnew.LoadBoard(src)
dsn = os.path.join(out, "bassberry_bench.dsn")
assert pcbnew.ExportSpecctraDSN(b, dsn)
t = open(dsn, encoding="utf-8").read()
t = re.sub(r"\(layer In2\.Cu\s*\(type \w+\)", "(layer In2.Cu (type power)", t)
# bassberry_placed.kicad_pcb has no project file next to it, so the DSN export writes KiCad's stock 0.2 mm netclass
# clearance; the flow (and bassberry.kicad_pro) use 0.15 mm, which the 0.4 mm-pitch charger QFN needs - with 0.2 mm
# 13 charger nets have no path at all (bench run 2026-10-28 22:xx). Same rules for every router under test.
t = t.replace("(clearance 200)", "(clearance 150)").replace("(clearance 50 (type smd_smd))", "(clearance 37.5 (type smd_smd))")
open(dsn, "w", encoding="utf-8").write(t)
shutil.copy(src, os.path.join(out, "bassberry_bench.kicad_pcb"))
for e in (".kicad_pro", ".kicad_dru"):
    p = src.replace("bassberry_placed.kicad_pcb", "bassberry" + e)
    if os.path.exists(p):
        shutil.copy(p, os.path.join(out, "bassberry_bench" + e))
n = sum(1 for f in b.GetFootprints() for p in f.Pads() if p.GetNetname())
print("dsn", os.path.getsize(dsn), "bytes; nets", b.GetNetCount(), "pads with nets", n,
      "tracks", sum(1 for t in b.GetTracks() if t.GetClass() != "PCB_VIA"), "vias", sum(1 for t in b.GetTracks() if t.GetClass() == "PCB_VIA"))
