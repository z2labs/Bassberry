"""Dog-bone fan-out for fine-pitch ICs before routing (srouter USAGE.md: 'Fan-out viak (dog-bone) mehetnek elore').

Every signal pin of the given parts gets a short 0.2 mm stub straight out of its side and a 0.6/0.3 mm via at the
first distance where the via and the stub keep 0.15 mm from everything already there (staggered automatically).
GND pins are left to the pours. The router then only has to connect vias, which it does on any layer.

usage: kicad-python fanout.py board.kicad_pcb REF [REF ...]
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import fatten

VIA_D, VIA_HOLE, STUB = 0.6, 0.3, 0.2


def main(path, refs):
    b = pcbnew.LoadBoard(path)
    fatten.CLR = 0.15; fatten.CLR_PAD = 0.15
    cu = fatten.Copper(b)
    mm, FM = pcbnew.ToMM, pcbnew.FromMM
    added = 0
    for ref in refs:
        fp = b.FindFootprintByReference(ref)
        if fp is None:
            print("no", ref); continue
        layer = pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
        c = (mm(fp.GetPosition().x), mm(fp.GetPosition().y))
        pads = [p for p in fp.Pads() if p.GetNetname() and p.GetNetname() != "GND" and not p.GetNetname().startswith("unconnected")]
        big = max(fp.Pads(), key=lambda p: p.GetBoundingBox().GetWidth() * p.GetBoundingBox().GetHeight())
        for p in pads:
            if p is big:
                continue
            q = (mm(p.GetPosition().x), mm(p.GetPosition().y))
            dx, dy = q[0] - c[0], q[1] - c[1]
            n = (1 if dx > 0 else -1, 0) if abs(dx) > abs(dy) else (0, 1 if dy > 0 else -1)
            bb = p.GetBoundingBox(); half = (mm(bb.GetWidth()) if n[0] else mm(bb.GetHeight())) / 2
            net = p.GetNetname()
            for d in (0.75, 1.1, 1.45, 1.8, 2.15, 2.5):
                v = (q[0] + n[0] * (half + d), q[1] + n[1] * (half + d))
                ok = all(cu.clear(net, l, v, v, VIA_D / 2) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu))
                ok = ok and cu.clear(net, layer, q, v, STUB / 2)
                ok = ok and all(math.hypot(mm(x.GetPosition().x) - v[0], mm(x.GetPosition().y) - v[1]) > VIA_D + 0.2
                                for x in b.GetTracks() if x.GetClass() == "PCB_VIA")
                if not ok:
                    continue
                t = pcbnew.PCB_TRACK(b); t.SetStart(p.GetPosition()); t.SetEnd(pcbnew.VECTOR2I(FM(v[0]), FM(v[1])))
                t.SetWidth(FM(STUB)); t.SetLayer(layer); t.SetNet(p.GetNet()); b.Add(t)
                via = pcbnew.PCB_VIA(b); via.SetPosition(pcbnew.VECTOR2I(FM(v[0]), FM(v[1])))
                via.SetWidth(FM(VIA_D)); via.SetDrill(FM(VIA_HOLE)); via.SetNet(p.GetNet()); b.Add(via)
                cu.add(net, {layer}, ("seg", q, v, STUB / 2), t); cu.add(net, "all", ("circ", v, VIA_D / 2), via)
                added += 1
                break
            else:
                print(f"  {ref}.{p.GetNumber()} ({net}): no room for a fan-out via, left to the router")
    pcbnew.SaveBoard(path, b)
    print(f"fanout: {added} dog-bones on {', '.join(refs)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
