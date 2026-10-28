"""GND stitching with Z2 Stitch 0.3.0 (github.com/z2labs/z2-stitch), headless - the same engine as the KiCad plugin.

  plan on the filled board: 2.54 mm grid + 2 refinement levels (P/2, P/4), stop at 99.5 % coverage, vias kept out of
  courtyards; other-net planes: the +BATT plane on In1 'grid' (coarse grid only, ~1 % copper), every other power
  pour 'forbid' (Z2 default); place with pour protection + built-in DRC (a via that fails is dropped); if the board
  then has more unconnected items than before, the minimal-via rescue joins the islands.

usage: kicad-python z2_stitch.py board.kicad_pcb [pitch=2.54]
env:   Z2STITCH_DIR (default D:\\Measurements\\via-stich, v0.3.0)
"""
import sys, os, json
os.environ["Z2STITCH_HEADLESS"] = "1"
sys.path.insert(0, os.environ.get("Z2STITCH_DIR", r"D:\Measurements\via-stich"))
try:                    # a wx debug-assert dialog would block an unattended run
    import wx
    wx.DisableAsserts()
except Exception:
    pass
import pcbnew as P
from z2stitch import actions

NET = "GND"
POLICY = {"+BATT": actions.PIERCE_GRID}


def unconnected(b):
    P.ZONE_FILLER(b).Fill(b.Zones())
    b.BuildConnectivity()
    c = b.GetConnectivity()
    try:
        return int(c.GetUnconnectedCount(False))
    except TypeError:
        return int(c.GetUnconnectedCount())


def main(path, pitch=2.54):
    b = P.LoadBoard(path)
    before = unconnected(b)
    vd, dr = actions.via_size_for(b, NET)
    m, _, plan = actions.plan(b, NET, vd, dr, pitch, levels=2, only_selected=False, refill=False,
                              pierce_policy=POLICY)
    for q in plan.proposals:
        print(f"draft {q.key}: {len(q.vias)} vias, coverage {q.coverage * 100:.2f} %, gap {q.gap_mm2:.0f} mm2")
    final = plan.proposals[-1]
    dropped = []
    placed = actions.place(b, NET, final.vias, vd, dr, protect=True, log=dropped.append)
    after = unconnected(b)
    print(f"z2 stitch: via {vd:.2f}/{dr:.2f} mm, placed {placed}, dropped by protection/DRC {len(dropped)}, "
          f"planes {getattr(m, 'policy', {})}, unconnected {before} -> {after}")
    if after > 0:       # GND pads that reach no pour (no dog-bone before routing): one via per island
        _, rv, left = actions.rescue_plan(b, NET, vd, dr, max_new=80)
        if rv:
            actions.place(b, NET, [(x, y, 9) for x, y, _ in rv], vd, dr, protect=True, log=dropped.append)
        after = unconnected(b)
        print(f"z2 rescue: {len(rv)} vias, unconnected -> {after}")
    P.SaveBoard(path, b)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 2.54)
