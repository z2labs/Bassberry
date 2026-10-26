"""Which pads of a net have no escape? usage: kicad-python escape_probe.py board.kicad_pcb NET [width_mm]"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import fatten

b = pcbnew.LoadBoard(sys.argv[1])
net = sys.argv[2]
w = float(sys.argv[3]) if len(sys.argv) > 3 else 0.3
fatten.CLR = 0.15; fatten.CLR_PAD = 0.15
cu = fatten.Copper(b)
mm = pcbnew.ToMM
for fp in b.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname() != net:
            continue
        c = (mm(p.GetPosition().x), mm(p.GetPosition().y))
        bb = p.GetBoundingBox(); r = max(mm(bb.GetWidth()), mm(bb.GetHeight())) / 2
        layers = [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)]
        free = []
        for k in range(16):
            a = math.radians(22.5 * k)
            q = (c[0] + (r + 1.0) * math.cos(a), c[1] + (r + 1.0) * math.sin(a))
            if any(cu.clear(net, l, c, q, w / 2) for l in layers):
                free.append(22.5 * k)
        print(f"{fp.GetReference()}.{p.GetNumber()} at ({c[0]-50:.2f},{c[1]-50:.2f}) layers {[b.GetLayerName(l) for l in layers]}: free directions {free}")
