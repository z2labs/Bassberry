"""Place every part the way JLCPCB's own footprint (EasyEDA model of the LCSC part) expects it.

KiCad's footprint origin and zero orientation are not JLC's: a QFN may be 90 deg off, a 2x20 socket or an encoder has its
origin on a pin instead of the body centre. Instead of a table of guessed corrections, this fits the JLC footprint onto
the copper: for each placed part it downloads the EasyEDA footprint of its LCSC part, and finds the rotation (0/90/180/270)
and the position that put the JLC pads on the board's pads (pad numbers matched; geometry only where the numbering
differs, e.g. a socket). The residual of that fit is the check that the JLC part really fits the land pattern.

Rotation = KiCad .pos rotation + (angle of JLC's footprint - angle of KiCad's own library footprint), both fitted to the
same board pads (bottom side: both mirrored, seen from the top). So the file stays in KiCad's .pos convention, which is
the one JLC documents for KiCad, and only the footprint-to-footprint difference is added.

    kicad-python hardware/tools/jlc_rotfix.py
in : hardware/bassberry/bassberry.kicad_pcb, jlc/bassberry_bom_jlc.csv (LCSC code per designator), jlc/bassberry_pos_kicad.csv
out: jlc/bassberry_cpl_jlc*.csv (rewritten), jlc/rotfix_report.csv, jlc/easyeda_cache/*.json
needs curl (Windows 10+ has curl.exe); the EasyEDA API refuses Python's own HTTP client.
"""
import os, sys, csv, json, math, subprocess, re, time
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
# --project DIR (KiCad project folder; default: the Bassberry one) and --name NAME (file stem; default: the .kicad_pcb in DIR)
_a = sys.argv[1:]
PRJ = os.path.abspath(_a[_a.index("--project") + 1]) if "--project" in _a else os.path.normpath(os.path.join(HERE, "..", "bassberry"))
if not os.path.isdir(PRJ):
    sys.exit(f"usage: {os.path.basename(__file__)} --project <KiCad project folder> [--name <board file stem>]")
NAME = _a[_a.index("--name") + 1] if "--name" in _a else next(
    (f[:-10] for f in sorted(os.listdir(PRJ)) if f.endswith(".kicad_pcb") and not f.endswith("_placed.kicad_pcb")), "board")
J = os.path.join(PRJ, "jlc")
CACHE = os.path.join(J, "easyeda_cache")
FPDIR = os.environ.get("KICAD_FP", r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
U = 0.254          # EasyEDA unit: 10 mil
TOL = 0.25         # mm rms: a fit worse than this means the JLC part does not match the land pattern


def easyeda(code):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, code + ".json")
    for attempt in range(6):
        if os.path.exists(f) and open(f, encoding="utf-8", errors="replace").read(1) == "{":
            break
        if attempt:
            time.sleep(5 * attempt)                     # the API throttles bursts with an HTML 403 page
        subprocess.run(["curl.exe" if os.name == "nt" else "curl", "-s", "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "-H", "Accept: application/json", "-o", f,
                        f"https://easyeda.com/api/products/{code}/components?version=6.4.19.5"], check=True)
    d = json.load(open(f, encoding="utf-8"))
    ds = d["result"]["packageDetail"]["dataStr"]
    ox, oy = float(ds["head"]["x"]), float(ds["head"]["y"])
    pads = []
    for s in ds["shape"]:
        if not s.startswith("PAD~"):
            continue
        p = s.split("~")
        pads.append((p[8].strip(), (float(p[2]) - ox) * U, -(float(p[3]) - oy) * U))   # y up
    return d["result"]["packageDetail"]["title"], pads


def rot(v, a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def fit(model, target, by_number, inl=None):
    """model, target: [(number, x, y)] (y up). Returns (angle, (tx, ty), rms over inliers, inliers, compared).
    By number: the translation is the one most pin pairs agree on (an exposed pad numbered differently, or a tab whose
    anchor is not its centre, does not drag the fit), the rms is over the pins that agree. Geometry only: every model
    pad to its nearest board pad."""
    if inl is None:                       # pin-pair agreement: 0.3 mm, or 2 % of the part's size for big parts
        span = max((math.hypot(x1 - x2, y1 - y2) for _, x1, y1 in model for _, x2, y2 in model), default=0)
        inl = max(0.3, 0.02 * span)
    best = None
    for a in (0, 90, 180, 270):
        m = [(n, rot((x, y), a)) for n, x, y in model]
        if by_number:
            tn = {}
            for n, x, y in target:
                tn.setdefault(n, []).append((x, y))
            mn = {}
            for n, p in m:
                mn.setdefault(n, []).append(p)
            pairs = [(mn[n][0], tn[n][0]) for n in mn if n in tn and len(mn[n]) == 1 and len(tn[n]) == 1]
            if len(pairs) < 2:
                continue
            cands = [(q[0] - p[0], q[1] - p[1]) for p, q in pairs]
            if len(pairs) <= 2:                # two-pin part: both pins count, take the mean
                cands = [(sum(c[0] for c in cands) / len(cands), sum(c[1] for c in cands) / len(cands))]
                inl_here = max(inl, max(math.hypot(q[0] - p[0] - cands[0][0], q[1] - p[1] - cands[0][1]) for p, q in pairs) + 1e-6)
            else:
                inl_here = inl
            scored = []
            for t in cands:
                ins = [(p, q) for p, q in pairs if math.hypot(q[0] - p[0] - t[0], q[1] - p[1] - t[1]) < inl_here]
                scored.append((len(ins), t, ins))
            n_in, t, ins = max(scored, key=lambda s: s[0])
            # position: the median of all pin translations (a land pattern with a wider row spacing stays centred,
            # one tab anchored off its centre does not pull)
            med = lambda v: sorted(v)[len(v) // 2] if len(v) % 2 else (sorted(v)[len(v) // 2 - 1] + sorted(v)[len(v) // 2]) / 2
            t = (med([q[0] - p[0] for p, q in pairs]), med([q[1] - p[1] for p, q in pairs]))
            err = math.sqrt(sum((q[0] - p[0] - t[0]) ** 2 + (q[1] - p[1] - t[1]) ** 2 for p, q in ins) / len(ins))
            cand = (a, t, err, len(ins), len(pairs))
            key = (len(ins), -err)
        else:
            cm = (sum(p[0] for _, p in m) / len(m), sum(p[1] for _, p in m) / len(m))
            ct = (sum(x for _, x, _ in target) / len(target), sum(y for _, _, y in target) / len(target))
            t = (ct[0] - cm[0], ct[1] - cm[1])
            ds = [min(math.hypot(tx - p[0] - t[0], ty - p[1] - t[1]) for _, tx, ty in target) for _, p in m]
            err = math.sqrt(sum(d * d for d in ds) / len(ds))
            cand = (a, t, err, sum(1 for d in ds if d < inl), len(ds))
            key = (cand[3], -err)
        if best is None or key > best[0]:
            best = (key, cand)
    return best[1] if best else (0, (0, 0), 99.0, 0, 1)


def main():
    b = pcbnew.LoadBoard(os.path.join(PRJ, f"{NAME}.kicad_pcb"))
    mm = pcbnew.ToMM
    code = {}
    for r in csv.DictReader(open(os.path.join(J, f"{NAME}_bom_jlc.csv"), encoding="utf-8")):
        for d in r["Designator"].split(","):
            code[d] = r["LCSC Part #"]
    kpos = {r["Ref"]: r for r in csv.DictReader(open(os.path.join(J, f"{NAME}_pos_kicad.csv"), encoding="utf-8"))}
    rows, report, conv = [], [], {}
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if ref not in code:
            continue
        bottom = fp.IsFlipped()
        target = [(p.GetNumber(), mm(p.GetPosition().x), -mm(p.GetPosition().y)) for p in fp.Pads()
                  if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH and p.GetNumber()]
        title, model = easyeda(code[ref])
        model = [(n, -x if bottom else x, y) for n, x, y in model if n]
        nums_t, nums_m = {n for n, _, _ in target}, {n for n, _, _ in model}
        by_number = len(nums_m & nums_t) >= max(2, 0.6 * min(len(nums_m), len(nums_t))) and not ref.startswith("J101")
        a, t, err, nin, ncmp = fit(model, target, by_number)
        if by_number and (nin < max(2, 0.6 * ncmp) or err > TOL):   # numbering differs: geometry only
            g = fit(model, target, False)
            if (g[3] / g[4], -g[2]) > (nin / ncmp, -err):
                a, t, err, nin, ncmp = g; by_number = False
        # KiCad's own footprint through the same fit -> the angle that corresponds to KiCad's .pos rotation
        lib, name = str(fp.GetFPID().GetLibNickname()), str(fp.GetFPID().GetLibItemName())
        own = os.path.join(PRJ, lib + ".pretty")
        kfp = pcbnew.FootprintLoad(own if os.path.isdir(own) else os.path.join(FPDIR, lib + ".pretty"), name)
        kmodel = [(p.GetNumber(), mm(p.GetPosition().x), -mm(p.GetPosition().y)) for p in kfp.Pads()
                  if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH and p.GetNumber() and p.GetNumber() in nums_t]
        kmodel = [(n, -x if bottom else x, y) for n, x, y in kmodel]
        ka, _, kerr, _, _ = fit(kmodel, target, not ref.startswith("J101"))
        prot = float(kpos[ref]["Rot"]) % 360
        if not bottom and kerr < 0.05 and round(ka) % 360 != round(prot) % 360:
            print(f"  note: {ref} top-side KiCad fit {ka} vs .pos {prot:.0f}")
        if os.environ.get("ROTDBG") and bottom:
            print("DBG", ref, name, "pos", prot, "ka", ka, "kerr", round(kerr, 3), "a", a, "err", round(err, 3), fp.GetOrientationDegrees())
        if bottom and kerr < 0.05:
            conv.setdefault(round((prot - ka) % 360), 0)
            conv[round((prot - ka) % 360)] += 1
        rows.append([ref, t, a, ka, prot, bottom])
        jrot = (prot - ka + a) % 360
        # verdict: every JLC pad centre must land on copper of this footprint (any of its pads, numbered or not)
        boxes = []
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            bb = p.GetBoundingBox()
            boxes.append((mm(bb.GetX()), -mm(bb.GetBottom()), mm(bb.GetRight()), -mm(bb.GetY())))
        land = [rot((x, y), a) for _, x, y in model]
        off = [(round(px + t[0], 2), round(py + t[1], 2)) for px, py in land
               if not any(x0 - 0.05 <= px + t[0] <= x1 + 0.05 and y0 - 0.05 <= py + t[1] <= y1 + 0.05 for x0, y0, x1, y1 in boxes)]
        ok = not off
        report.append([ref, code[ref], title, "bottom" if bottom else "top", f"{prot:.0f}", f"{jrot:.0f}", f"{t[0]:.3f}", f"{t[1]:.3f}",
                       f"{err:.3f}", f"{nin}/{ncmp} " + ("pins by number" if by_number else "pads by geometry"),
                       "OK" if ok else f"LAND PATTERN MISMATCH: {len(off)} of {len(land)} JLC pads off the copper"])
    # JLC rotation = KiCad .pos rotation corrected by the angle between JLC's footprint and KiCad's own footprint, both
    # fitted to the same pads (bottom: KiCad .pos = top-view angle + 180, the offset printed below; same rule for the JLC footprint)
    print("KiCad .pos vs top-view angle of KiCad's own footprint, bottom side (pos - angle):", dict(conv))
    out = []
    for ref, t, a, ka, prot, bottom in rows:
        r = (prot - ka + a) % 360
        out.append([ref, f"{t[0]:.4f}mm", f"{t[1]:.4f}mm", "Bottom" if bottom else "Top", f"{r:.0f}"])
    nat = lambda r: (re.sub(r"\d", "", r[0]), int(re.sub(r"\D", "", r[0]) or 0))
    out.sort(key=nat)
    for name, pick in ((f"{NAME}_cpl_jlc.csv", lambda r: True), (f"{NAME}_cpl_jlc_top.csv", lambda r: r[3] == "Top"),
                       (f"{NAME}_cpl_jlc_bottom.csv", lambda r: r[3] == "Bottom")):
        with open(os.path.join(J, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            w.writerows([r for r in out if pick(r)])
    with open(os.path.join(J, "rotfix_report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "LCSC", "JLC footprint", "Side", "KiCad pos rot", "JLC rotation", "X", "Y",
                    "Fit rms mm", "Matched by", "Verdict"])
        w.writerows(report)
    bad = [r for r in report if not r[-1].startswith("OK")]
    print(f"{len(report)} parts fitted, {len(bad)} land-pattern mismatches")
    for r in bad:
        print("  MISMATCH", r[0], r[1], r[2], "rms", r[8])


if __name__ == "__main__":
    main()
