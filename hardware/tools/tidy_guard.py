"""Guard for srouter's track_tidy: re-join any pad the tidy step pulled a track off.

track_tidy straightens and merges segments; when it moves a segment that ran *through* a pad (srouter's pad entry),
the pad can end up next to its own track instead of on it (seen on R106 +3V3). This compares the KiCad DRC
unconnected list before and after the tidy and, for every pad that lost its track, adds the shortest straight stub from
the pad centre to that track (same layer, width = min(track width, pad narrow side)), if it clears all other copper.

usage: kicad-python tidy_guard.py before.kicad_pcb after.kicad_pcb      (after is modified in place)
"""
import sys, os, json, subprocess, tempfile, re
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
        if len(pads) != 1 or len(trks) != 1:
            left.append(" | ".join(x[3] for x in u)); continue
        p, t = pads[0], trks[0]
        c = (mm(p.GetPosition().x), mm(p.GetPosition().y))
        a, e = (mm(t.GetStart().x), mm(t.GetStart().y)), (mm(t.GetEnd().x), mm(t.GetEnd().y))
        dx, dy = e[0] - a[0], e[1] - a[1]
        L = dx * dx + dy * dy
        k = 0 if L == 0 else max(0, min(1, ((c[0] - a[0]) * dx + (c[1] - a[1]) * dy) / L))
        q = (a[0] + k * dx, a[1] + k * dy)
        s = p.GetSize(pcbnew.F_Cu)
        w = min(mm(t.GetWidth()), mm(min(s.x, s.y)))
        if not p.IsOnLayer(t.GetLayer()) or not cu.clear(p.GetNetname(), t.GetLayer(), c, q, w / 2):
            left.append(" | ".join(x[3] for x in u)); continue
        n = pcbnew.PCB_TRACK(b); n.SetStart(pcbnew.VECTOR2I(FM(c[0]), FM(c[1]))); n.SetEnd(pcbnew.VECTOR2I(FM(q[0]), FM(q[1])))
        n.SetWidth(FM(w)); n.SetLayer(t.GetLayer()); n.SetNet(p.GetNet()); b.Add(n)
        cu.add(p.GetNetname(), {t.GetLayer()}, ("seg", c, q, w / 2), n)
        fixed += 1
    if fixed:
        pcbnew.SaveBoard(after, b)
    print(f"tidy_guard: {len(new)} connections lost by the tidy, {fixed} re-joined" + (f"; left: {left}" if left else ""))
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
