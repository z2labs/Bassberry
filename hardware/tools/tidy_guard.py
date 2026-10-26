"""Guard for srouter's track_tidy: re-join any pad the tidy step pulled a track off.

track_tidy straightens and merges segments; when it moves a segment that ran *through* a pad (srouter's pad entry),
the pad can end up next to its own track instead of on it (seen on R106 +3V3). This compares the KiCad DRC
unconnected list before and after the tidy and, for every pad that lost its track (or two pieces of a track that no
longer meet), adds the shortest straight stub from
the pad centre to that track (same layer, width = min(track width, pad narrow side)), if it clears all other copper.

usage: kicad-python tidy_guard.py before.kicad_pcb after.kicad_pcb      (after is modified in place)
"""
import sys, os, json, subprocess, tempfile, re, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import fatten

CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def unconnected(path):
    out = os.path.join(tempfile.gettempdir(), "tidy_guard_" + os.path.basename(path) + ".json")
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "--severity-error", "-o", out, path], capture_output=True)
    d = json.load(open(out, encoding="utf-8"))
    res = []
    for u in d.get("unconnected_items", []):
        res.append(tuple((i.get("uuid"), round(i["pos"]["x"], 3), round(i["pos"]["y"], 3), i["description"]) for i in u["items"]))
    return res


def main(before, after):
    pre = {tuple(sorted((x[1], x[2]) for x in u)) for u in unconnected(before)}
    post = unconnected(after)
    new = [u for u in post if tuple(sorted((x[1], x[2]) for x in u)) not in pre]
    b = pcbnew.LoadBoard(after)
    byid = {}
    for t in b.GetTracks():
        byid[t.m_Uuid.AsString()] = t
    for fp in b.GetFootprints():
        for p in fp.Pads():
            byid[p.m_Uuid.AsString()] = p
    fatten.CLR = 0.15; fatten.CLR_PAD = 0.15
    cu = fatten.Copper(b)
    mm, FM = pcbnew.ToMM, pcbnew.FromMM
    fixed, left = 0, []
    for u in new:
        objs = [byid.get(x[0]) for x in u]
        pads = [o for o in objs if isinstance(o, pcbnew.PAD)]
        trks = [o for o in objs if o is not None and o.GetClass() == "PCB_TRACK"]

        def seg(t):
            return (mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y))

        def foot(c, t):
            a, e = seg(t)
            dx, dy = e[0] - a[0], e[1] - a[1]
            L = dx * dx + dy * dy
            k = 0 if L == 0 else max(0, min(1, ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / L))
            return (a[0] + k * dx, a[1] + k * dy)
        if len(pads) == 1 and len(trks) == 1:
            p, t = pads[0], trks[0]
            c = (mm(p.GetPosition().x), mm(p.GetPosition().y))
            s = p.GetSize(pcbnew.F_Cu)
            w = min(mm(t.GetWidth()), mm(min(s.x, s.y)))
            ok_layer = p.IsOnLayer(t.GetLayer())
        elif len(trks) == 2 and trks[0].GetLayer() == trks[1].GetLayer():
            # two pieces of one track no longer meet: join the nearest end of one to the other
            t0, t1 = trks
            cands = [(c, t1) for c in seg(t0)] + [(c, t0) for c in seg(t1)]
            c, t = min(cands, key=lambda ct: math.dist(ct[0], foot(ct[0], ct[1])))
            w = min(mm(t0.GetWidth()), mm(t1.GetWidth()))
            p = t0
            ok_layer = True
        elif len(trks) == 2:
            # pieces on two layers: the layer change went missing - a via at the nearest end of one, and a stub
            # on the other layer from its nearest end to that via
            t0, t1 = trks
            e0, e1 = seg(t0), seg(t1)
            a, bpt = min(((x, y) for x in e0 for y in e1), key=lambda xy: math.dist(*xy))
            if math.dist(a, bpt) > 2.0 or not all(cu.clear(t0.GetNetname(), l, bpt, bpt, 0.3) for l in
                                                     (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)) \
                    or not cu.clear(t0.GetNetname(), t0.GetLayer(), a, bpt, mm(t0.GetWidth()) / 2):
                left.append(" | ".join(x[3] for x in u)); continue
            v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(FM(bpt[0]), FM(bpt[1])))
            v.SetWidth(FM(0.6)); v.SetDrill(FM(0.3)); v.SetNet(t0.GetNet()); b.Add(v)
            cu.add(t0.GetNetname(), "all", ("circ", bpt, 0.3), v)
            if math.dist(a, bpt) > 1e-3:
                n = pcbnew.PCB_TRACK(b); n.SetStart(pcbnew.VECTOR2I(FM(a[0]), FM(a[1]))); n.SetEnd(pcbnew.VECTOR2I(FM(bpt[0]), FM(bpt[1])))
                n.SetWidth(t0.GetWidth()); n.SetLayer(t0.GetLayer()); n.SetNet(t0.GetNet()); b.Add(n)
                cu.add(t0.GetNetname(), {t0.GetLayer()}, ("seg", a, bpt, mm(t0.GetWidth()) / 2), n)
            fixed += 1
            continue
        else:
            left.append(" | ".join(x[3] for x in u)); continue
        q = foot(c, t)
        if not ok_layer or not cu.clear(p.GetNetname(), t.GetLayer(), c, q, w / 2):
            left.append(" | ".join(x[3] for x in u)); continue
        n = pcbnew.PCB_TRACK(b); n.SetStart(pcbnew.VECTOR2I(FM(c[0]), FM(c[1]))); n.SetEnd(pcbnew.VECTOR2I(FM(q[0]), FM(q[1])))
        n.SetWidth(FM(w)); n.SetLayer(t.GetLayer()); n.SetNet(p.GetNet()); b.Add(n)
        cu.add(p.GetNetname(), {t.GetLayer()}, ("seg", c, q, w / 2), n)
        fixed += 1
    # tidy leftovers: a segment with a free end carries nothing - remove it
    out = os.path.join(tempfile.gettempdir(), "tidy_guard_dangling.json")
    if fixed:
        pcbnew.SaveBoard(after, b)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "--severity-all", "-o", out, after], capture_output=True)
    dang = [i.get("uuid") for v in json.load(open(out, encoding="utf-8")).get("violations", [])
            if v["type"] == "track_dangling" for i in v["items"]]
    b = pcbnew.LoadBoard(after)
    rm = [t for t in b.GetTracks() if t.m_Uuid.AsString() in dang and t.GetClass() == "PCB_TRACK"]
    for t in rm:
        b.Remove(t)
    if rm:
        pcbnew.SaveBoard(after, b)
        print(f"tidy_guard: {len(rm)} dangling segments removed")
    print(f"tidy_guard: {len(new)} connections lost by the tidy, {fixed} re-joined" + (f"; left: {left}" if left else ""))
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
