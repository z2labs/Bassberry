"""Widen the high-current tracks after the srouter power pass and add parallel vias at their layer changes.

srouter routes every net with one width, and that width must fit the smallest pad of the net (its pre-route check
warns 'track will wall the pad in - neck down'): the battery rail touches a 0.25 mm QFN pin, so it is routed thin.
This step gives the current back: every segment of a high-current net is widened to its target width wherever the
clearance to all other copper allows (it necks down on its own next to small pads), and every via of such a net
gets parallel vias until the layer change carries the current (1.5 A per 0.6/0.3 mm via).
It runs between pass 1 and pass 2, so the later passes see the wide copper as fixed obstacles.

usage: kicad-python fatten.py board.kicad_pcb [--dry]
"""
import os, sys, math, fnmatch
import pcbnew

CLR = 0.20          # mm, widened copper to any other net (netclass is 0.15)
EDGE = 0.5          # mm to the board edge
VIA_D, VIA_HOLE = 0.6, 0.3
VIA_A = 1.5
# net glob -> (target width mm on outer copper, design current A)   [IPC-2221, 1 oz, 20 K rise]
TARGET = [
    ("/battery/CELL?", 2.4, 6.0), ("+BATT", 2.4, 6.0),
    ("+5V", 1.9, 5.0), ("+5V_BUCK", 1.9, 5.0), ("/power/BUCK_SW", 1.9, 5.0),
    ("/power/CHG_LX?", 1.2, 3.5), ("VBUS", 1.0, 3.0), ("/power/CHG_VIN", 1.0, 3.0), ("/power/CHG_NODE?", 1.0, 3.0),
    ("PVDD_SUB", 1.0, 3.0), ("/power/BOOST_SW", 1.0, 3.0), ("/power/BOOST_OUT", 0.8, 2.0),
    ("/audio/AMP2_?", 1.0, 3.0), ("/audio/SUB_?", 1.0, 3.0),
    ("/audio/AMP1_A?", 0.6, 2.0), ("/audio/AMP1_B?", 0.6, 2.0), ("/audio/SAT_*", 0.6, 2.0),
]


def target(net):
    for g, w, a in TARGET:
        if fnmatch.fnmatchcase(net, g):
            return w, a
    return None


# ---------------------------------------------------------------- 2D geometry (mm)
def d_pt_seg(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def seg_x(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)


def d_seg_seg(a, b, c, d):
    if seg_x(a, b, c, d):
        return 0.0
    return min(d_pt_seg(a, c, d), d_pt_seg(b, c, d), d_pt_seg(c, a, b), d_pt_seg(d, a, b))


def d_seg_rect(a, b, r):
    x0, y0, x1, y1 = r
    if x0 <= a[0] <= x1 and y0 <= a[1] <= y1:
        return 0.0
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    return min(d_seg_seg(a, b, c, d) for c, d in edges)


class Copper:
    """other-net copper per layer: ('seg', a, b, half_width) | ('rect', x0,y0,x1,y1) | ('circ', c, r)"""
    def __init__(self, board):
        self.b = board
        self.items = []   # (net, layerset, kind, geom, bbox)
        mm = pcbnew.ToMM
        P = lambda v: (mm(v.x), mm(v.y))
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                c = P(t.GetPosition()); r = mm(t.GetWidth(pcbnew.F_Cu)) / 2
                self.add(t.GetNetname(), "all", ("circ", c, r), t)
            else:
                a, bb = P(t.GetStart()), P(t.GetEnd()); hw = mm(t.GetWidth()) / 2
                self.add(t.GetNetname(), {t.GetLayer()}, ("seg", a, bb, hw), t)
        for fp in board.GetFootprints():
            for p in fp.Pads():
                box = p.GetBoundingBox()
                r = (mm(box.GetX()), mm(box.GetY()), mm(box.GetRight()), mm(box.GetBottom()))
                layers = {l for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)}
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    layers = "all"
                self.add(p.GetNetname() if p.GetNumber() else "", layers, ("rect",) + r, p)

    def update_seg(self, obj, hw):
        for i, (n, ls, g, bb, o) in enumerate(self.items):
            if o is obj or (hasattr(o, "m_Uuid") and hasattr(obj, "m_Uuid") and o.m_Uuid.AsString() == obj.m_Uuid.AsString()):
                g2 = ("seg", g[1], g[2], hw)
                self.items[i] = (n, ls, g2, (min(g[1][0], g[2][0]) - hw, min(g[1][1], g[2][1]) - hw, max(g[1][0], g[2][0]) + hw, max(g[1][1], g[2][1]) + hw), o)
                return

    def add(self, net, layers, g, obj):
        if g[0] == "circ":
            bb = (g[1][0] - g[2], g[1][1] - g[2], g[1][0] + g[2], g[1][1] + g[2])
        elif g[0] == "seg":
            bb = (min(g[1][0], g[2][0]) - g[3], min(g[1][1], g[2][1]) - g[3], max(g[1][0], g[2][0]) + g[3], max(g[1][1], g[2][1]) + g[3])
        else:
            bb = g[1:5]
        self.items.append((net, layers, g, bb, obj))

    def clear(self, net, layer, a, b, hw, skip=()):
        """True if a capsule a-b with half width hw on layer keeps CLR from every other-net item"""
        qb = (min(a[0], b[0]) - hw - CLR - 0.05, min(a[1], b[1]) - hw - CLR - 0.05, max(a[0], b[0]) + hw + CLR + 0.05, max(a[1], b[1]) + hw + CLR + 0.05)
        for (n, ls, g, bb, obj) in self.items:
            if n == net or obj in skip:
                continue
            if ls != "all" and layer not in ls:
                continue
            if bb[0] > qb[2] or bb[2] < qb[0] or bb[1] > qb[3] or bb[3] < qb[1]:
                continue
            if g[0] == "seg":
                d = d_seg_seg(a, b, g[1], g[2]) - g[3]
            elif g[0] == "circ":
                d = d_pt_seg(g[1], a, b) - g[2]
            else:
                d = d_seg_rect(a, b, g[1:5])
            if d < hw + CLR:
                return False
        return True


def main(path, dry=False):
    b = pcbnew.LoadBoard(path)
    mm, FM = pcbnew.ToMM, pcbnew.FromMM
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, True)

    def inside(p, margin):
        for ang in range(0, 360, 45):
            q = (p[0] + margin * math.cos(math.radians(ang)), p[1] + margin * math.sin(math.radians(ang)))
            if not outline.Contains(pcbnew.VECTOR2I(FM(q[0]), FM(q[1]))):
                return False
        return True

    cu = Copper(b)
    widened, vias_added, report = 0, 0, {}
    tracks = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA" and target(t.GetNetname())]
    tracks.sort(key=lambda t: -t.GetLength())
    for t in tracks:
        net = t.GetNetname(); wt, _ = target(net)
        a, c = (mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y))
        w0 = mm(t.GetWidth())
        best = w0
        w = wt
        while w > w0 + 0.05:
            if cu.clear(net, t.GetLayer(), a, c, w / 2) and inside(a, w / 2 + EDGE) and inside(c, w / 2 + EDGE):
                best = w; break
            w = round(w - 0.1, 2)
        if best > w0:
            if not dry:
                t.SetWidth(FM(best))
            cu.update_seg(t, best / 2)
            widened += 1
            # update our own copper model so later segments see it (other nets only care, but keep it exact)
        report.setdefault(net, []).append(best)
    # ---- parallel vias at layer changes
    for v in [x for x in b.GetTracks() if x.GetClass() == "PCB_VIA" and target(x.GetNetname())]:
        net = v.GetNetname(); wt, amps = target(net)
        need = math.ceil(amps / VIA_A)
        c = (mm(v.GetPosition().x), mm(v.GetPosition().y))
        mates = [x for x in b.GetTracks() if x.GetClass() == "PCB_VIA" and x.GetNetname() == net and
                 math.hypot(mm(x.GetPosition().x) - c[0], mm(x.GetPosition().y) - c[1]) < 2.5]
        layers = {t.GetLayer() for t in b.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetNetname() == net and
                  min(math.hypot(mm(t.GetStart().x) - c[0], mm(t.GetStart().y) - c[1]), math.hypot(mm(t.GetEnd().x) - c[0], mm(t.GetEnd().y) - c[1])) < 0.05}
        have = len(mates)
        for r in (1.1, 1.7, 2.3):
            if have >= need:
                break
            for k in range(8):
                if have >= need:
                    break
                ang = math.radians(45 * k + (22.5 if r == 1.7 else 0))
                p = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
                if not inside(p, VIA_D / 2 + EDGE):
                    continue
                ok = all(cu.clear(net, l, p, p, VIA_D / 2) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu))
                ok = ok and all(math.hypot(mm(x.GetPosition().x) - p[0], mm(x.GetPosition().y) - p[1]) > VIA_D + 0.25
                                for x in b.GetTracks() if x.GetClass() == "PCB_VIA")
                sw = min(wt, 1.0)
                ok = ok and all(cu.clear(net, l, c, p, sw / 2) for l in layers)
                if not ok:
                    continue
                if not dry:
                    nv = pcbnew.PCB_VIA(b); nv.SetPosition(pcbnew.VECTOR2I(FM(p[0]), FM(p[1])))
                    nv.SetWidth(FM(VIA_D)); nv.SetDrill(FM(VIA_HOLE)); nv.SetNet(v.GetNet()); b.Add(nv)
                    for l in layers:
                        s = pcbnew.PCB_TRACK(b); s.SetStart(v.GetPosition()); s.SetEnd(nv.GetPosition())
                        s.SetWidth(FM(sw)); s.SetLayer(l); s.SetNet(v.GetNet()); b.Add(s)
                        cu.add(net, {l}, ("seg", c, p, sw / 2), s)
                    cu.add(net, "all", ("circ", p, VIA_D / 2), nv)
                have += 1; vias_added += 1
    if not dry:
        pcbnew.SaveBoard(path, b)
    for net, ws in sorted(report.items()):
        wt = target(net)[0]
        print(f"  {net:22s} {len(ws):3d} seg, at target {sum(1 for w in ws if w >= wt - 0.01):3d}, min {min(ws):.2f} mm (target {wt})")
    print(f"fatten: {widened} segments widened, {vias_added} parallel vias added")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(args[0], "--dry" in sys.argv)
