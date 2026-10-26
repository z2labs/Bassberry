"""Layer 4: board mechanics vs the enclosure concept (docs/architecture.md, render/render.py) and the cell holders.

  * 3 x Keystone 1042 (18 x 65 mm cells): long axis front-to-back, side by side, no overlap with the Pi shadow,
    series links short (cell n '+' and cell n+1 '-' at the same end)
  * USB-C mouth at the rear edge, buttons / encoder / OLED socket in the front strip (lid plungers)
  * speaker connectors on the bottom (acoustic side), mounting holes free of other parts

usage: kicad-python twin_mech.py board.kicad_pcb [--selftest]       exit 0 / 1 FAIL / 2 input / 3 selftest
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from twin_common import Report


def load(path):
    import pcbnew
    from board_geom import OX, OY
    b = pcbnew.LoadBoard(path)
    mm = pcbnew.ToMM
    parts = {}
    for fp in b.GetFootprints():
        bb = fp.GetBoundingBox(False)
        pads = {p.GetNumber(): (mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY) for p in fp.Pads() if p.GetNumber()}
        parts[fp.GetReference()] = dict(
            side="B" if fp.IsFlipped() else "F", pos=(mm(fp.GetPosition().x) - OX, mm(fp.GetPosition().y) - OY),
            box=(mm(bb.GetX()) - OX, mm(bb.GetY()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY), pads=pads,
            rot=fp.GetOrientationDegrees())
    return parts


def check(parts):
    from board_geom import W, H, PI_AREA
    rep = Report("layer 4: mechanics (cells, edges, lid controls)")
    cells = [parts[r] for r in ("BT401", "BT402", "BT403") if r in parts]
    if len(cells) != 3:
        rep.add("FAIL", "cells", "three cell holders BT401..BT403 expected"); return rep
    for r in ("BT401", "BT402", "BT403"):
        c = parts[r]; (x0, y0, x1, y1) = c["box"]
        along_y = (y1 - y0) > (x1 - x0)
        rep.add("PASS" if along_y else "FAIL", "cells", f"{r}: cell axis front-to-back ({x1-x0:.1f} x {y1-y0:.1f} mm)")
        l = math.dist(c["pads"]["1"], c["pads"]["2"])
        rep.add("PASS" if 75 < l < 85 else "FAIL", "cells", f"{r}: contact spacing {l:.1f} mm for a 65 mm 18650 (Keystone 1042: 79.4 mm)")
        inside = x0 >= 0 and y0 >= 0 and x1 <= W and y1 <= H
        rep.add("PASS" if inside else "FAIL", "cells", f"{r}: inside the outline")
        pi = PI_AREA
        rep.add("PASS" if (x0 >= pi[2] or x1 <= pi[0] or y0 >= pi[3] or y1 <= pi[1]) else "FAIL", "cells", f"{r}: clear of the Pi")
    xs = sorted((parts[r]["box"], r) for r in ("BT401", "BT402", "BT403"))
    for (a, ra), (b, rb) in zip(xs, xs[1:]):
        rep.add("PASS" if b[0] >= a[2] - 0.05 else "FAIL", "cells", f"{ra}/{rb} side by side, gap {b[0]-a[2]:.2f} mm")
    for (pa, pb, name) in ((("BT401", "1"), ("BT402", "2"), "CELL1 link"), (("BT402", "1"), ("BT403", "2"), "CELL2 link")):
        d = math.dist(parts[pa[0]]["pads"][pa[1]], parts[pb[0]]["pads"][pb[1]])
        rep.add("PASS" if d < 30 else "FAIL", "cells", f"{name}: '+' of one cell to '-' of the next = {d:.1f} mm (same end)")
    u = parts.get("J301")
    if u:
        rep.add("PASS" if u["box"][1] <= 1.0 else "FAIL", "usb", f"USB-C mouth at the rear edge (front of shell at y = {u['box'][1]:.2f} mm)")
    for r in ("SW501", "SW502", "SW503", "SW504", "SW505", "SW506", "J502"):
        p = parts.get(r)
        if p:
            ok = p["side"] == "F" and p["pos"][1] > H - 15
            rep.add("PASS" if ok else "FAIL", "lid", f"{r} on top in the front strip (y = {p['pos'][1]:.1f} mm)")
    for r in ("J201", "J202", "J203"):
        p = parts.get(r)
        if p:
            rep.add("PASS" if p["side"] == "B" else "FAIL", "speaker", f"{r} on the bottom (acoustic side)")
    for h, p in parts.items():
        if not h.startswith("H"):
            continue
        cx, cy = p["pos"]
        near = [r for r, q in parts.items() if r != h and not r.startswith("H") and r != "J101" and
                q["box"][0] - 0.2 < cx + 3.0 and q["box"][2] + 0.2 > cx - 3.0 and q["box"][1] - 0.2 < cy + 3.0 and q["box"][3] + 0.2 > cy - 3.0]
        rep.add("PASS" if not near else "FAIL", "holes", f"{h}: screw head area free" + (f" (touches {near})" if near else ""))
    return rep


def selftest(parts):
    import copy
    base = {r[2] for r in check(parts).fails()}
    st = Report("selftest: injected faults")
    q = copy.deepcopy(parts); b = q["BT402"]["box"]; q["BT402"]["box"] = (b[0], b[1], b[0] + (b[3] - b[1]), b[1] + (b[2] - b[0]))
    p2 = copy.deepcopy(parts); p2["BT402"]["pads"]["1"], p2["BT402"]["pads"]["2"] = parts["BT402"]["pads"]["2"], parts["BT402"]["pads"]["1"]
    p3 = copy.deepcopy(parts); p3["SW503"]["side"] = "B"
    for name, pp in (("cell holder turned 90 degrees", q), ("cell 2 holder reversed", p2), ("PLAY button on the bottom", p3)):
        new = {r[2] for r in check(pp).fails()} - base
        st.add("PASS" if new else "FAIL", "inject", f"{name}: {len(new)} new FAIL")
    return st


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args or not os.path.exists(args[0]):
        print(__doc__); sys.exit(2)
    parts = load(args[0])
    r = check(parts); r.show("-q" in sys.argv)
    code = 1 if r.fails() else 0
    if "--selftest" in sys.argv:
        st = selftest(parts); st.show()
        if st.fails():
            code = 3
    sys.exit(code)
