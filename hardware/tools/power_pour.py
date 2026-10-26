"""Power pours along the routed high-current paths (srouter USAGE.md: power is carried by pours, not routed width).

srouter routes every net with one width that must fit its smallest pad, and fatten.py can only widen a track where
the clearance allows. This step gives each high-current net a copper zone around its own tracks (2.0 mm each side,
per layer: F.Cu, In1.Cu, B.Cu), priority 5: above the GND pours (0), below the SoC thermal pad (10). The zone filler only takes free
space and keeps the clearance to every other net, so nothing already routed is disturbed; the result is a wide
copper path that hugs the routed track and grows into the room around it. Own pads connect solid (no reliefs).

Runs after track_tidy, before the zone fill (postroute.ps1).   usage: kicad-python power_pour.py board.kicad_pcb
"""
import sys, os, fnmatch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math
import pcbnew
import fatten
from fatten import TARGET

BUFFER = 2.0     # mm around each track of the net
GND_MOAT = 1.0   # mm kept free around a GND pad that has no via of its own yet (gnd_stitch / via_rescue reach it later)
VIA_A = 1.5      # A per 0.6/0.3 mm via (same figure as the layer-3 twin)
PRIO = 5


def add_vias(b):
    """every layer change of a high-current net gets ceil(I / 1.5 A) vias: the extra ones go inside the net's own
    filled pour on each layer the via joins, clear of every other net on all four layers."""
    FM, mm = pcbnew.FromMM, pcbnew.ToMM
    fatten.CLR = 0.2; fatten.CLR_PAD = 0.2
    cu = fatten.Copper(b)
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, True)
    keep = [z for z in b.Zones() if z.GetIsRuleArea()]
    allv = [(mm(v.GetPosition().x), mm(v.GetPosition().y)) for v in b.GetTracks() if v.GetClass() == "PCB_VIA"]
    fills = {}

    def own_fill(net, layer):
        k = (net, layer)
        if k not in fills:
            ps = pcbnew.SHAPE_POLY_SET()
            for z in b.Zones():
                if not z.GetIsRuleArea() and z.GetNetname() == net and z.IsOnLayer(layer):
                    f = z.GetFilledPolysList(layer)
                    if f is not None and f.OutlineCount():
                        ps.Append(f)
            fills[k] = ps
        return fills[k]

    def inside(ps, p, r):
        return all(ps.Contains(pcbnew.VECTOR2I(FM(p[0] + r * math.cos(a)), FM(p[1] + r * math.sin(a))))
                   for a in [k * math.pi / 4 for k in range(8)] + [0])

    made = 0
    vias = [v for v in b.GetTracks() if v.GetClass() == "PCB_VIA"]
    allv_net = {}
    for v in vias:
        allv_net.setdefault(v.GetNetname(), []).append((mm(v.GetPosition().x), mm(v.GetPosition().y)))
    for v in vias:
        net = v.GetNetname(); tg = fatten.target(net)
        if not tg:
            continue
        need = math.ceil(tg[1] / VIA_A)
        c = (mm(v.GetPosition().x), mm(v.GetPosition().y))
        layers = {t.GetLayer() for t in b.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetNetname() == net and
                  (t.GetStart() == v.GetPosition() or t.GetEnd() == v.GetPosition())}
        if len(layers) < 2:
            continue
        have = sum(1 for (x, y) in allv_net.get(net, []) if math.hypot(x - c[0], y - c[1]) < 2.6)
        for r in (0.9, 1.25, 1.6, 2.0, 2.5):
            if have >= need:
                break
            for k in range(16):
                if have >= need:
                    break
                a = 2 * math.pi * k / 16
                p = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
                if any(math.hypot(p[0] - x, p[1] - y) < 0.9 for (x, y) in allv):
                    continue
                if not inside(outline, p, 0.8) or any(z.Outline().Contains(pcbnew.VECTOR2I(FM(p[0]), FM(p[1]))) for z in keep):
                    continue
                if not all(inside(own_fill(net, l), p, 0.4) for l in layers):
                    continue
                if not all(cu.clear(net, l, p, p, 0.3) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)):
                    continue
                nv = pcbnew.PCB_VIA(b); nv.SetPosition(pcbnew.VECTOR2I(FM(p[0]), FM(p[1])))
                nv.SetWidth(FM(0.6)); nv.SetDrill(FM(0.3)); nv.SetNet(v.GetNet()); b.Add(nv)
                cu.add(net, "all", ("circ", p, 0.3), nv)
                allv.append(p); allv_net.setdefault(net, []).append(p)
                have += 1; made += 1
    return made


def main(path):
    b = pcbnew.LoadBoard(path)
    FM = pcbnew.FromMM
    # remove pours from an earlier run
    # duplicate vias (two tools dropping one on the same spot) -> keep one
    seen, dup = set(), []
    for v in list(b.GetTracks()):
        if v.GetClass() == "PCB_VIA":
            k = (v.GetNetname(), round(pcbnew.ToMM(v.GetPosition().x), 2), round(pcbnew.ToMM(v.GetPosition().y), 2))
            if k in seen:
                dup.append(v)
            seen.add(k)
    for v in dup:
        b.Remove(v)
    if dup:
        print(f"power_pour: {len(dup)} duplicate vias removed")
    tracks = list(b.GetTracks())
    nets = sorted({t.GetNetname() for t in tracks if t.GetClass() != "PCB_VIA"})
    old = [z for z in b.Zones() if z.GetZoneName().startswith("PWR_")]
    for z in old:
        b.Remove(z)
    # GND pads that already have their own way down (THT, dog-bone / tie track, IC exposed pad with its via field)
    # need no moat; only the others keep a ring free so the GND pour can still reach them
    gnd_ends = {(t.GetStart().x, t.GetStart().y) for t in tracks if t.GetNetname() == "GND" and t.GetClass() != "PCB_VIA"}
    gnd_ends |= {(t.GetEnd().x, t.GetEnd().y) for t in tracks if t.GetNetname() == "GND" and t.GetClass() != "PCB_VIA"}
    lonely = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if (p.GetPosition().x, p.GetPosition().y) in gnd_ends:
                continue
            bb = p.GetBoundingBox()
            if pcbnew.ToMM(bb.GetWidth()) > 2.5 and pcbnew.ToMM(bb.GetHeight()) > 2.5:
                continue
            lonely.append(p)
    made = 0
    for net in nets:
        if not any(fnmatch.fnmatchcase(net, g) for g, w, a in TARGET):
            continue
        ni = b.FindNet(net)
        for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.B_Cu):     # In1: power that srouter had to take inside
            ps = pcbnew.SHAPE_POLY_SET()
            n = 0
            for t in tracks:
                if t.GetClass() == "PCB_VIA" or t.GetNetname() != net or t.GetLayer() != layer:
                    continue
                t.TransformShapeToPolygon(ps, layer, FM(BUFFER), FM(0.05), pcbnew.ERROR_INSIDE)
                n += 1
            if not n:
                continue
            # keep the pour away from GND pads on this layer, so the GND pour (and a stitching via) can still reach them
            moat = pcbnew.SHAPE_POLY_SET()
            for p in lonely:
                if p.IsOnLayer(layer):
                    p.TransformShapeToPolygon(moat, layer, FM(GND_MOAT), FM(0.05), pcbnew.ERROR_OUTSIDE)
            ps.Simplify()
            if moat.OutlineCount():
                moat.Simplify()
                ps.BooleanSubtract(moat)
            for i in range(ps.OutlineCount()):
                z = pcbnew.ZONE(b)
                z.SetLayer(layer); z.SetNet(ni); z.SetAssignedPriority(PRIO)
                z.SetZoneName(f"PWR_{net.split('/')[-1]}_{b.GetLayerName(layer)}_{i}")
                z.SetLocalClearance(FM(0.25)); z.SetMinThickness(FM(0.25))
                z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
                z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
                z.Outline().Append(ps.UnitSet(i))          # outline with its holes (the GND moats)
                b.Add(z); made += 1
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    nv = add_vias(b)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    print(f"power_pour: {nv} parallel vias added")
    pcbnew.SaveBoard(path, b)
    print(f"power_pour: {made} zones on {len([n for n in nets if any(fnmatch.fnmatchcase(n, g) for g, w, a in TARGET)])} nets")


if __name__ == "__main__":
    main(sys.argv[1])
