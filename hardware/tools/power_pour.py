"""Power pours along the routed high-current paths (srouter USAGE.md: power is carried by pours, not routed width).

srouter routes every net with one width that must fit its smallest pad, and fatten.py can only widen a track where
the clearance allows. This step gives each high-current net a copper zone around its own tracks (2.5 mm each side,
per layer), priority 5: above the GND pours (0), below the SoC thermal pad (10). The zone filler only takes free
space and keeps the clearance to every other net, so nothing already routed is disturbed; the result is a wide
copper path that hugs the routed track and grows into the room around it. Own pads connect solid (no reliefs).

Runs after track_tidy, before the zone fill (postroute.ps1).   usage: kicad-python power_pour.py board.kicad_pcb
"""
import sys, os, fnmatch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from fatten import TARGET

BUFFER = 2.0     # mm around each track of the net
GND_MOAT = 1.6   # mm kept free around every GND pad on the layer (pour + a 0.6 mm stitching via fit in)
PRIO = 5


def main(path):
    b = pcbnew.LoadBoard(path)
    FM = pcbnew.FromMM
    # remove pours from an earlier run
    for z in list(b.Zones()):
        if z.GetZoneName().startswith("PWR_"):
            b.Remove(z)
    nets = sorted({t.GetNetname() for t in b.GetTracks() if t.GetClass() != "PCB_VIA"})
    made = 0
    for net in nets:
        if not any(fnmatch.fnmatchcase(net, g) for g, w, a in TARGET):
            continue
        ni = b.FindNet(net)
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            ps = pcbnew.SHAPE_POLY_SET()
            n = 0
            for t in b.GetTracks():
                if t.GetClass() == "PCB_VIA" or t.GetNetname() != net or t.GetLayer() != layer:
                    continue
                t.TransformShapeToPolygon(ps, layer, FM(BUFFER), FM(0.05), pcbnew.ERROR_INSIDE)
                n += 1
            if not n:
                continue
            # keep the pour away from GND pads on this layer, so the GND pour (and a stitching via) can still reach them
            moat = pcbnew.SHAPE_POLY_SET()
            for fp in b.GetFootprints():
                for p in fp.Pads():
                    if p.GetNetname() == "GND" and p.IsOnLayer(layer):
                        p.TransformShapeToPolygon(moat, layer, FM(GND_MOAT), FM(0.05), pcbnew.ERROR_OUTSIDE)
            ps.Simplify()
            if moat.OutlineCount():
                moat.Simplify()
                ps.BooleanSubtract(moat)
            for i in range(ps.OutlineCount()):
                outline = ps.Outline(i)
                z = pcbnew.ZONE(b)
                z.SetLayer(layer); z.SetNet(ni); z.SetAssignedPriority(PRIO)
                z.SetZoneName(f"PWR_{net.split('/')[-1]}_{b.GetLayerName(layer)}_{i}")
                z.SetLocalClearance(FM(0.25)); z.SetMinThickness(FM(0.25))
                z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
                z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
                zo = z.Outline(); zo.NewOutline()
                for k in range(outline.PointCount()):
                    p = outline.CPoint(k)
                    zo.Append(p.x, p.y)
                b.Add(z); made += 1
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(path, b)
    print(f"power_pour: {made} zones on {len([n for n in nets if any(fnmatch.fnmatchcase(n, g) for g, w, a in TARGET)])} nets")


if __name__ == "__main__":
    main(sys.argv[1])
