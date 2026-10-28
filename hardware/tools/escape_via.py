"""Escape via for a pin that the router finds walled in: a short stub straight out of the pin (away from the part body)
and a via at its end, where the via clears every other net on all layers and the stub clears its layer.

  PI_PWR_EN on U303.5 (buck EN, SOT-23-6 under the buck copper): "no path" in every repair round (run 2026-10-28 03:43);
  with a via next to the pin the router reaches it from any layer.

usage: kicad-python escape_via.py board.kicad_pcb REF.PAD [REF.PAD ...]     (also imported by pcb_build.py)
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

VIA_D, VIA_DRILL = 0.45, 0.2
STEPS = (0.8, 1.1, 1.4, 1.8, 2.3)        # mm from the pad centre, along the escape direction
ALL = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)


def escape(board, refpads, log=print):
    import fatten
    fatten.CLR = 0.15; fatten.CLR_PAD = 0.15
    cu = fatten.Copper(board)
    mm, FM = pcbnew.ToMM, pcbnew.FromMM
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    made = []
    for rp in refpads:
        ref, num = rp.split(".")
        fp = fps.get(ref)
        pad = next((p for p in fp.Pads() if p.GetNumber() == num), None) if fp else None
        if pad is None:
            log(f"escape_via: {rp} not found"); continue
        net = pad.GetNetname(); lay = pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
        c = (mm(pad.GetPosition().x), mm(pad.GetPosition().y)); o = (mm(fp.GetPosition().x), mm(fp.GetPosition().y))
        dx, dy = c[0] - o[0], c[1] - o[1]
        dirs = [(1 if dx > 0 else -1, 0), (0, 1 if dy > 0 else -1)]
        if abs(dy) > abs(dx):
            dirs.reverse()
        dirs += [(-dirs[1][0], -dirs[1][1])]           # the other side along the row as a last resort
        sz = pad.GetSize(pcbnew.F_Cu); hw = min(0.125, mm(min(sz.x, sz.y)) / 2 - 0.025)
        done = False
        for u in dirs:
            for s in STEPS:
                v = (c[0] + u[0] * s, c[1] + u[1] * s)
                if not cu.off_pads(v, VIA_D / 2, 0.15):
                    continue
                if not all(cu.clear(net, l, v, v, VIA_D / 2) for l in ALL):
                    continue
                if not cu.clear(net, lay, c, v, hw):
                    continue
                t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I(FM(c[0]), FM(c[1]))); t.SetEnd(pcbnew.VECTOR2I(FM(v[0]), FM(v[1])))
                t.SetWidth(FM(2 * hw)); t.SetLayer(lay); t.SetNet(pad.GetNet()); board.Add(t)
                via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I(FM(v[0]), FM(v[1])))
                via.SetWidth(FM(VIA_D)); via.SetDrill(FM(VIA_DRILL)); via.SetNet(pad.GetNet()); board.Add(via)
                cu.add(net, {lay}, ("seg", c, v, hw), t)
                made.append(f"{rp}->({v[0]:.2f},{v[1]:.2f})"); done = True
                break
            if done:
                break
        if not done:
            log(f"escape_via: no room next to {rp}")
    log(f"escape vias: {made}")
    return made


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    b = pcbnew.LoadBoard(sys.argv[1])
    escape(b, sys.argv[2:])
    pcbnew.SaveBoard(sys.argv[1], b)
