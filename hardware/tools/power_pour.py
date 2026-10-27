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
PRIO = 5        # 5..9 by current: above the GND pours (0), below the SoC thermal pad (10)
SPLIT = 1.0     # mm a pour keeps from another high-current net's track on the same layer
# zone name -> (layer, net): a plane on an inner layer that takes all the room the signals leave there
PLANES = {"PWR_PLANE_+BATT_In1.Cu": (pcbnew.In1_Cu, "+BATT")}
TAP_A = {"big": 4.5, "small": 1.5}   # A each pad of the plane net must be able to push into the plane


def add_vias(b):
    """every layer change of a high-current net must carry its current (1.5 A per 0.3 mm of drill, the same figure as the
    layer-3 twin): first the via itself grows to 1.0/0.5 mm where it clears, then parallel vias (1.0/0.5 or 0.6/0.3 mm)
    go inside the net's own filled pour on each layer the via joins, clear of every other net on all four layers."""
    FM, mm = pcbnew.FromMM, pcbnew.ToMM
    fatten.CLR = 0.15; fatten.CLR_PAD = 0.15        # routing is done: the netclass clearance is the rule now
    cu = fatten.Copper(b)
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, True)
    keep = [z for z in b.Zones() if z.GetIsRuleArea()]
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
        allv_net.setdefault(v.GetNetname(), []).append([mm(v.GetPosition().x), mm(v.GetPosition().y), mm(v.GetDrillValue()), v])
    amps = lambda d: VIA_A * d / 0.3                  # barrel cross-section pi * d * t scales with the drill
    ALL = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)

    def hole_ok(p, d, skip=None):
        # 0.25 mm hole to hole (JLC) to every via, any net
        for vv in vias_all:
            if vv[3] is skip:
                continue
            if math.hypot(p[0] - vv[0], p[1] - vv[1]) < (d + vv[2]) / 2 + 0.25 + 0.05:
                return False
        return True
    vias_all = [x for lst in allv_net.values() for x in lst]
    for v in vias:
        net = v.GetNetname(); tg = fatten.target(net)
        if not tg:
            continue
        need = tg[1]
        c = (mm(v.GetPosition().x), mm(v.GetPosition().y))
        layers = {t.GetLayer() for t in b.GetTracks() if t.GetClass() != "PCB_VIA" and t.GetNetname() == net and
                  (t.GetStart() == v.GetPosition() or t.GetEnd() == v.GetPosition())}
        if len(layers) < 2:
            continue
        near = [x for x in allv_net.get(net, []) if math.hypot(x[0] - c[0], x[1] - c[1]) < 2.6]
        have = sum(amps(x[2]) for x in near)
        # 1) a bigger barrel in place: 1.0 / 0.5 mm (2.5 A) if it clears everything
        me = next(x for x in allv_net[net] if x[3] is v)
        if have < need and me[2] < 0.45 and hole_ok(c, 0.5, skip=v) and \
                all(cu.clear(net, l, c, c, 0.5) for l in ALL):
            v.SetWidth(FM(1.0)); v.SetDrill(FM(0.5)); have += amps(0.5) - amps(me[2]); me[2] = 0.5
            cu.add(net, "all", ("circ", c, 0.5), v); made += 1
        # 2) parallel vias inside the net's own pour on every layer this via joins
        for r in (0.7, 0.9, 1.25, 1.6, 2.0, 2.5, 3.0, 3.5, 4.0):
            if have >= need:
                break
            for k in range(24):
                if have >= need:
                    break
                ang = 2 * math.pi * k / 24
                p = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
                if not inside(outline, p, 0.8) or any(z.Outline().Contains(pcbnew.VECTOR2I(FM(p[0]), FM(p[1]))) for z in keep):
                    continue
                for dia, drill in ((1.0, 0.5), (0.6, 0.3), (0.45, 0.2)):
                    if not hole_ok(p, drill):
                        continue
                    if not all(cu.clear(net, l, p, p, dia / 2) for l in ALL):
                        continue
                    # joined through the net's own pour on every layer, or else by a stub from the via on each layer
                    stubs = [l for l in layers if not inside(own_fill(net, l), p, dia / 2 + 0.05)]
                    sw = min(tg[0], 0.8)
                    if not all(cu.clear(net, l, c, p, sw / 2) for l in stubs):
                        continue
                    nv = pcbnew.PCB_VIA(b); nv.SetPosition(pcbnew.VECTOR2I(FM(p[0]), FM(p[1])))
                    nv.SetWidth(FM(dia)); nv.SetDrill(FM(drill)); nv.SetNet(v.GetNet()); b.Add(nv)
                    for l in stubs:
                        st = pcbnew.PCB_TRACK(b); st.SetStart(v.GetPosition()); st.SetEnd(nv.GetPosition())
                        st.SetWidth(FM(sw)); st.SetLayer(l); st.SetNet(v.GetNet()); b.Add(st)
                        cu.add(net, {l}, ("seg", c, p, sw / 2), st)
                    cu.add(net, "all", ("circ", p, dia / 2), nv)
                    rec = [p[0], p[1], drill, nv]; allv_net[net].append(rec); vias_all.append(rec)
                    have += amps(drill); made += 1
                    break
    return made


def plane_taps(b):
    """vias from every pad of a plane net (on its own outer copper: pad, track or pour) down into the plane: pads
    1 mm or wider need TAP_A['big'] (they are the fuse, sense resistor, links and bulk caps), smaller ones one via."""
    FM, mm = pcbnew.FromMM, pcbnew.ToMM
    fatten.CLR = 0.2; fatten.CLR_PAD = 0.2
    cu = fatten.Copper(b)
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, True)
    keep = [z for z in b.Zones() if z.GetIsRuleArea()]
    vias = [[mm(v.GetPosition().x), mm(v.GetPosition().y), mm(v.GetDrillValue()), v.GetNetname()] for v in b.GetTracks() if v.GetClass() == "PCB_VIA"]
    ALL = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    made = 0
    for zname, (pl, net) in PLANES.items():
        plane = next(z for z in b.Zones() if z.GetZoneName() == zname)
        pf = plane.GetFilledPolysList(pl)
        own = {}
        for l in (pcbnew.F_Cu, pcbnew.B_Cu):
            ps = pcbnew.SHAPE_POLY_SET()
            for z in b.Zones():
                if z.GetNetname() == net and not z.GetIsRuleArea() and z.IsOnLayer(l):
                    f = z.GetFilledPolysList(l)
                    if f is not None and f.OutlineCount():
                        ps.Append(f)
            for t in b.GetTracks():
                if t.GetNetname() == net and t.GetClass() != "PCB_VIA" and t.GetLayer() == l:
                    t.TransformShapeToPolygon(ps, l, 0, FM(0.02), pcbnew.ERROR_INSIDE)
            for fp in b.GetFootprints():
                for p in fp.Pads():
                    if p.GetNetname() == net and p.IsOnLayer(l):
                        p.TransformShapeToPolygon(ps, l, 0, FM(0.02), pcbnew.ERROR_INSIDE)
            ps.Simplify()
            own[l] = ps

        def inside(ps, p, r):
            return all(ps.Contains(pcbnew.VECTOR2I(FM(p[0] + r * math.cos(a)), FM(p[1] + r * math.sin(a))))
                       for a in [k * math.pi / 4 for k in range(8)] + [0])
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() != net:
                    continue
                if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH,):
                    continue                                  # a plated hole already reaches the plane
                l = pcbnew.B_Cu if p.IsOnLayer(pcbnew.B_Cu) else pcbnew.F_Cu
                s = p.GetSize(pcbnew.F_Cu)
                need = TAP_A["big"] if min(mm(s.x), mm(s.y)) >= 1.0 else TAP_A["small"]
                c = (mm(p.GetPosition().x), mm(p.GetPosition().y))
                have = sum(VIA_A * v[2] / 0.3 for v in vias if v[3] == net and math.hypot(v[0] - c[0], v[1] - c[1]) < 2.5)
                for r in (0.8, 1.2, 1.6, 2.0, 2.5, 3.0):
                    if have >= need:
                        break
                    for k in range(16):
                        if have >= need:
                            break
                        q = (c[0] + r * math.cos(k * math.pi / 8), c[1] + r * math.sin(k * math.pi / 8))
                        if not inside(outline, q, 0.8) or any(z.Outline().Contains(pcbnew.VECTOR2I(FM(q[0]), FM(q[1]))) for z in keep):
                            continue
                        for dia, drill in ((1.0, 0.5), (0.6, 0.3)):
                            if any(math.hypot(q[0] - v[0], q[1] - v[1]) < (drill + v[2]) / 2 + 0.35 for v in vias):
                                continue
                            if not inside(own[l], q, dia / 2 + 0.05) or not inside(pf, q, dia / 2 + 0.05):
                                continue
                            if not all(cu.clear(net, ll, q, q, dia / 2) for ll in ALL):
                                continue
                            v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(FM(q[0]), FM(q[1])))
                            v.SetWidth(FM(dia)); v.SetDrill(FM(drill)); v.SetNet(p.GetNet()); b.Add(v)
                            cu.add(net, "all", ("circ", q, dia / 2), v)
                            vias.append([q[0], q[1], drill, net]); have += VIA_A * drill / 0.3; made += 1
                            break
    return made


def main(path):
    b = pcbnew.LoadBoard(path)
    FM = pcbnew.FromMM
    # remove pours from an earlier run
    # (near-)duplicate vias of one net (two tools dropping one on almost the same spot, hole to hole < 0.25 mm):
    # keep the first, bridge the tracks that ended on the other one
    alltr = list(b.GetTracks())
    vs = [v for v in alltr if v.GetClass() == "PCB_VIA"]
    kept, dup = [], []
    for v in vs:
        p = v.GetPosition()
        twin = next((k for k in kept if k.GetNetname() == v.GetNetname() and
                     pcbnew.ToMM((k.GetPosition() - p).EuclideanNorm()) < (pcbnew.ToMM(k.GetDrillValue()) + pcbnew.ToMM(v.GetDrillValue())) / 2 + 0.25), None)
        if twin is None:
            kept.append(v); continue
        dup.append(v)
        # the tracks that ended on the dropped via stay where they are; a short bridge on each of their layers
        # joins that spot to the kept via (it lies inside the two via pads, so no new clearance is used)
        lays = {t.GetLayer() for t in alltr if t.GetClass() != "PCB_VIA" and t.GetNetname() == v.GetNetname()
                and (t.GetStart() == p or t.GetEnd() == p)}
        for l in lays:
            br = pcbnew.PCB_TRACK(b); br.SetStart(p); br.SetEnd(twin.GetPosition()); br.SetLayer(l)
            br.SetWidth(min(v.GetWidth(pcbnew.F_Cu), twin.GetWidth(pcbnew.F_Cu))); br.SetNet(v.GetNet()); b.Add(br)
    for v in dup:
        b.Remove(v)
    if dup:
        print(f"power_pour: {len(dup)} near-duplicate vias merged")
        pcbnew.SaveBoard(path, b)                 # pcbnew's track list is stale after Remove: reload
        b = pcbnew.LoadBoard(path)
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
    power_nets = {n for n in nets if fatten.target(n)}
    for net in nets:
        if not any(fnmatch.fnmatchcase(net, g) for g, w, a in TARGET):
            continue
        ni = b.FindNet(net)
        prio = PRIO + min(4, int(fatten.target(net)[1] // 1.5))   # where two pours still meet, the bigger current wins
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
            # share the room with the other high-current nets on this layer: never closer than SPLIT to their tracks,
            # so two neighbouring pours split the gap between them instead of one eating the other's corridor
            for t in tracks:
                if t.GetClass() != "PCB_VIA" and t.GetLayer() == layer and t.GetNetname() != net and t.GetNetname() in power_nets:
                    t.TransformShapeToPolygon(moat, layer, FM(SPLIT), FM(0.05), pcbnew.ERROR_OUTSIDE)
            ps.Simplify()
            if moat.OutlineCount():
                moat.Simplify()
                ps.BooleanSubtract(moat)
            for i in range(ps.OutlineCount()):
                z = pcbnew.ZONE(b)
                z.SetLayer(layer); z.SetNet(ni); z.SetAssignedPriority(prio)
                z.SetZoneName(f"PWR_{net.split('/')[-1]}_{b.GetLayerName(layer)}_{i}")
                z.SetLocalClearance(FM(0.25)); z.SetMinThickness(FM(0.25))
                z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
                z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
                z.Outline().Append(ps.UnitSet(i))          # outline with its holes (the GND moats)
                b.Add(z); made += 1
    # In1.Cu: whatever room the signals leave becomes a +BATT plane (below every corridor pour), fed by taps
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, True)
    for pname, (pl, pnet) in PLANES.items():
        z = pcbnew.ZONE(b)
        z.SetLayer(pl); z.SetNet(b.FindNet(pnet)); z.SetAssignedPriority(4)
        z.SetZoneName(pname); z.SetLocalClearance(FM(0.25)); z.SetMinThickness(FM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL); z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.Outline().Append(outline)
        b.Add(z); made += 1
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    nt = plane_taps(b)
    if nt:
        print(f"power_pour: {nt} plane tap vias")
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    nv = add_vias(b)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    # a pour piece that touches nothing of its own net is dead copper (DRC isolated_copper): drop it
    pts = {}
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            pts.setdefault(t.GetNetname(), []).append((t.GetPosition(), None)); continue
        a, e = t.GetStart(), t.GetEnd()
        n = max(1, int(pcbnew.ToMM((e - a).EuclideanNorm()) / 0.3))      # sample along the whole segment
        for i in range(n + 1):
            q = pcbnew.VECTOR2I(int(a.x + (e.x - a.x) * i / n), int(a.y + (e.y - a.y) * i / n))
            pts.setdefault(t.GetNetname(), []).append((q, t.GetLayer()))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            pts.setdefault(p.GetNetname(), []).append((p.GetPosition(), p))
    dead = 0
    for z in list(b.Zones()):
        if not z.GetZoneName().startswith("PWR_"):
            continue
        l = z.GetLayer(); f = z.GetFilledPolysList(l)
        if f is None or not f.OutlineCount():
            b.Remove(z); dead += 1; continue
        hit = any(f.Contains(q) for q, o in pts.get(z.GetNetname(), [])
                  if o is None or (o == l if isinstance(o, int) else o.IsOnLayer(l)))
        if not hit:
            b.Remove(z); dead += 1
    if dead:
        print(f"power_pour: {dead} dead pour pieces removed")
    print(f"power_pour: {nv} vias enlarged or added in parallel")
    pcbnew.SaveBoard(path, b)
    print(f"power_pour: {made} zones on {len([n for n in nets if any(fnmatch.fnmatchcase(n, g) for g, w, a in TARGET)])} nets")


if __name__ == "__main__":
    main(sys.argv[1])
