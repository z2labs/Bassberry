"""One-off on a routed board: drop the Pi Zero outline silkscreen of the face-down socket footprint (J101),
keeping only what sits on the 2x20 header (pcb_build.py does the same for new placements).
usage: kicad-python pi_silk_fix.py board.kicad_pcb"""
import sys
import pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
fp = b.FindFootprintByReference("J101")
pins = [p for p in fp.Pads() if p.GetNumber().isdigit()]
xs = [pcbnew.ToMM(p.GetPosition().x) for p in pins]; ys = [pcbnew.ToMM(p.GetPosition().y) for p in pins]
n = 0
for g in list(fp.GraphicalItems()):
    if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS, pcbnew.F_Fab, pcbnew.B_Fab):
        bb = g.GetBoundingBox()
        if not (pcbnew.ToMM(bb.GetX()) >= min(xs) - 3 and pcbnew.ToMM(bb.GetRight()) <= max(xs) + 3 and
                pcbnew.ToMM(bb.GetY()) >= min(ys) - 3 and pcbnew.ToMM(bb.GetBottom()) <= max(ys) + 3):
            fp.Remove(g); n += 1
pcbnew.SaveBoard(sys.argv[1], b)
print("J101 graphics removed:", n)
