"""Move routed vias off the SMD pads they touch (JLC DFM "via to pad": a via touching a pad of its own net wicks
solder from the joint; JLC rates it Danger).

srouter's pad entry may end a track in a via whose ring overlaps the pad edge. For every via closer than GAP to an SMD
pad, this slides the via straight away from the pad by the smallest step that frees it (up to MAXSHIFT), if the via and
the re-drawn tracks that end on it keep the netclass clearance on every layer; the moved tracks keep their widths.
Vias that cannot move are listed.

usage: kicad-python via_off_pad.py board.kicad_pcb
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import fatten

GAP = 0.15        # mm via ring to pad edge
MAXSHIFT = 0.8    # mm


def main(path):
    b = pcbnew.LoadBoard(path)
    mm, FM = pcbnew.ToMM, pcbnew.FromMM
    fatten.CLR = 0.15; fatten.CLR_PAD = 0.15
    cu = fatten.Copper(b)
    tracks = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
    ALL = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
    smd = [(fp.GetReference(), p) for fp in b.GetFootprints() for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    moved, stuck = 0, []
    for v in [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]:
        c = (mm(v.GetPosition().x), mm(v.GetPosition().y)); r = mm(v.GetWidth(pcbnew.F_Cu)) / 2
        if cu.off_pads(c, r, 0.0):        # not touching: leave it (moving costs room); touching: move
            continue
        # the pad(s) it touches: push away from the nearest point of the nearest one
        best = None
        for ref, p in smd:
            bb = p.GetBoundingBox()
            box = (mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom()))
            q = (min(max(c[0], box[0]), box[2]), min(max(c[1], box[1]), box[3]))
            d = math.dist(c, q)
            if d < r + GAP and (best is None or d < best[0]):
                inside = box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]
                best = (d, q, box, inside, ref, p.GetNumber())
        if best is None:
            continue
        d, q, box, inside, ref, num = best
        if inside:      # centre on the pad: leave by the nearest edge
            cands = [((box[0] - c[0]), 0), ((box[2] - c[0]), 0), (0, (box[1] - c[1])), (0, (box[3] - c[1]))]
            dx, dy = min(cands, key=lambda t: abs(t[0]) + abs(t[1]))
            n = math.hypot(dx, dy) or 1; u = (dx / n, dy / n); base = n
        else:
            n = math.hypot(c[0] - q[0], c[1] - q[1]) or 1; u = ((c[0] - q[0]) / n, (c[1] - q[1]) / n); base = -d
        ends = [t for t in tracks if t.GetNetname() == v.GetNetname() and (t.GetStart() == v.GetPosition() or t.GetEnd() == v.GetPosition())]
        done = False
        for gap in (GAP, 0.05):                # 0.15 mm if there is room, else at least not touching
            s = base + r + gap + 0.01
            while s <= base + r + gap + MAXSHIFT and not done:
                np_ = (c[0] + u[0] * s, c[1] + u[1] * s)
                ok = cu.off_pads(np_, r, gap) and all(cu.clear(v.GetNetname(), l, np_, np_, r, skip=(v,)) for l in ALL)
                for t in ends if ok else []:
                    other = t.GetEnd() if t.GetStart() == v.GetPosition() else t.GetStart()
                    o = (mm(other.x), mm(other.y))
                    if not cu.clear(t.GetNetname(), t.GetLayer(), o, np_, mm(t.GetWidth()) / 2, skip=(t,)):
                        ok = False; break
                if ok:
                    old = v.GetPosition(); new = pcbnew.VECTOR2I(FM(np_[0]), FM(np_[1]))
                    for t in ends:
                        if t.GetStart() == old:
                            t.SetStart(new)
                        else:
                            t.SetEnd(new)
                    v.SetPosition(new)
                    cu = fatten.Copper(b)          # the moved tracks change the picture for the next via
                    moved += 1; done = True
                s += 0.05
            if done:
                break
        if not done:
            stuck.append(f"{v.GetNetname()} at ({c[0]:.2f},{c[1]:.2f}) on {ref}.{num}")
    pcbnew.SaveBoard(path, b)
    print(f"via_off_pad: {moved} vias moved off SMD pads, {len(stuck)} could not move")
    for s_ in stuck:
        print("  stuck:", s_)


if __name__ == "__main__":
    main(sys.argv[1])
