"""Dump the copper inside windows of a board to JSON (for net-coloured close-ups of necks).
usage: kicad-python dump_window.py board.kicad_pcb out.json x0,y0,x1,y1 [...]"""
import sys, json
import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.ToMM
L = {pcbnew.F_Cu: "F", pcbnew.In1_Cu: "In1", pcbnew.In2_Cu: "In2", pcbnew.B_Cu: "B"}
wins = [tuple(map(float, w.split(","))) for w in sys.argv[3:]]


def inwin(x0, y0, x1, y1):
    return [i for i, (a, b_, c, d) in enumerate(wins) if x1 >= a and x0 <= c and y1 >= b_ and y0 <= d]


out = {"tracks": [], "vias": [], "pads": [], "zones": [], "windows": wins}
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
        if inwin(x, y, x, y):
            out["vias"].append([x, y, mm(t.GetWidth(pcbnew.F_Cu)), t.GetNetname()])
    else:
        s, e = t.GetStart(), t.GetEnd()
        if inwin(min(mm(s.x), mm(e.x)), min(mm(s.y), mm(e.y)), max(mm(s.x), mm(e.x)), max(mm(s.y), mm(e.y))):
            out["tracks"].append([mm(s.x), mm(s.y), mm(e.x), mm(e.y), mm(t.GetWidth()), L.get(t.GetLayer(), "?"), t.GetNetname()])
for fp in b.GetFootprints():
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        if not inwin(mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())):
            continue
        ps = pcbnew.SHAPE_POLY_SET()
        for l in L:
            if p.IsOnLayer(l):
                ps2 = pcbnew.SHAPE_POLY_SET(); p.TransformShapeToPolygon(ps2, l, 0, pcbnew.FromMM(0.02), pcbnew.ERROR_INSIDE)
                ol = ps2.Outline(0)
                pts = [[mm(ol.CPoint(k).x), mm(ol.CPoint(k).y)] for k in range(ol.PointCount())]
                out["pads"].append([L[l], fp.GetReference() + "." + p.GetNumber(), p.GetNetname(), pts])
for z in b.Zones():
    if z.GetIsRuleArea():
        continue
    for l in L:
        if not z.IsOnLayer(l):
            continue
        f = z.GetFilledPolysList(l)
        if f is None:
            continue
        for k in range(f.OutlineCount()):
            ol = f.Outline(k)
            bb = ol.BBox()
            if not inwin(mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())):
                continue
            pts = [[round(mm(ol.CPoint(j).x), 3), round(mm(ol.CPoint(j).y), 3)] for j in range(ol.PointCount())]
            holes = []
            for h in range(f.HoleCount(k)):
                hl = f.Hole(k, h)
                hb = hl.BBox()
                if inwin(mm(hb.GetX()), mm(hb.GetY()), mm(hb.GetRight()), mm(hb.GetBottom())):
                    holes.append([[round(mm(hl.CPoint(j).x), 3), round(mm(hl.CPoint(j).y), 3)] for j in range(hl.PointCount())])
            out["zones"].append([L[l], z.GetNetname(), z.GetZoneName(), pts, holes])
json.dump(out, open(sys.argv[2], "w"))
print("dumped", {k: len(v) for k, v in out.items()})
