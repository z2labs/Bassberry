"""Place every part the way JLCPCB's own footprint (EasyEDA model of the LCSC part) expects it.

KiCad's footprint origin and zero orientation are not JLC's: a QFN may be 90 deg off, a 2x20 socket or an encoder has its
origin on a pin instead of the body centre. Instead of a table of guessed corrections, this fits the JLC footprint onto
the copper: for each placed part it downloads the EasyEDA footprint of its LCSC part, and finds the rotation (0/90/180/270)
and the position that put the JLC pads on the board's pads (pad numbers matched; geometry only where the numbering
differs, e.g. a socket). The residual of that fit is the check that the JLC part really fits the land pattern.

Bottom side: the JLC model is mirrored (seen from the top), fitted the same way, and the rotation is written in KiCad's
.pos convention for the bottom side, which is the one JLC documents for KiCad files: the convention is derived per run
from KiCad's own footprints (the same fit done with the KiCad library footprint must reproduce KiCad's .pos rotation).

    kicad-python hardware/tools/jlc_rotfix.py
in : hardware/bassberry/bassberry.kicad_pcb, jlc/bassberry_bom_jlc.csv (LCSC code per designator), jlc/bassberry_pos_kicad.csv
out: jlc/bassberry_cpl_jlc*.csv (rewritten), jlc/rotfix_report.csv, jlc/easyeda_cache/*.json
needs curl (Windows 10+ has curl.exe); the EasyEDA API refuses Python's own HTTP client.
"""
import os, sys, csv, json, math, subprocess, re
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, "..", "bassberry"))
J = os.path.join(PRJ, "jlc")
CACHE = os.path.join(J, "easyeda_cache")
FPDIR = os.environ.get("KICAD_FP", r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
U = 0.254          # EasyEDA unit: 10 mil
TOL = 0.25         # mm rms: a fit worse than this means the JLC part does not match the land pattern


def easyeda(code):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, code + ".json")
    if not os.path.exists(f):
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


def fit(model, target, by_number):
    """model, target: [(number, x, y)] (y up). Returns (angle, (tx, ty), rms) of target ~ R(angle) model + t."""
    best = None
    for a in (0, 90, 180, 270):
        m = [(n, rot((x, y), a)) for n, x, y in model]
        if by_number:
            pairs = []
            for n, (x, y) in m:
                cand = [(tx, ty) for tn, tx, ty in target if tn == n]
                if cand:
                    pairs.append(((x, y), cand))
            if len(pairs) < max(2, len(m) // 2):
                continue
            # translation from the matched pad centroids, then nearest same-number pad
            t = (sum(min(c, key=lambda q: 0)[0] for _, c in pairs) / len(pairs) - sum(p[0] for p, _ in pairs) / len(pairs),
                 sum(min(c, key=lambda q: 0)[1] for _, c in pairs) / len(pairs) - sum(p[1] for p, _ in pairs) / len(pairs))
            for _ in range(3):
                ds = [min(c, key=lambda q: (q[0] - p[0] - t[0]) ** 2 + (q[1] - p[1] - t[1]) ** 2) for p, c in pairs]
                t = (sum(q[0] - p[0] for (p, _), q in zip(pairs, ds)) / len(pairs),
                     sum(q[1] - p[1] for (p, _), q in zip(pairs, ds)) / len(pairs))
            err = math.sqrt(sum((q[0] - p[0] - t[0]) ** 2 + (q[1] - p[1] - t[1]) ** 2 for (p, _), q in zip(pairs, ds)) / len(pairs))
        else:
            cm = (sum(p[0] for _, p in m) / len(m), sum(p[1] for _, p in m) / len(m))
            ct = (sum(x for _, x, _ in target) / len(target), sum(y for _, _, y in target) / len(target))
            t = (ct[0] - cm[0], ct[1] - cm[1])
            err = math.sqrt(sum(min((tx - p[0] - t[0]) ** 2 + (ty - p[1] - t[1]) ** 2 for _, tx, ty in target)
                                for _, p in m) / len(m))
        if best is None or err < best[2] - 1e-6:
            best = (a, t, err)
    return best


def main():
    b = pcbnew.LoadBoard(os.path.join(PRJ, "bassberry.kicad_pcb"))
    mm = pcbnew.ToMM
    code = {}
    for r in csv.DictReader(open(os.path.join(J, "bassberry_bom_jlc.csv"), encoding="utf-8")):
        for d in r["Designator"].split(","):
            code[d] = r["LCSC Part #"]
    kpos = {r["Ref"]: r for r in csv.DictReader(open(os.path.join(J, "bassberry_pos_kicad.csv"), encoding="utf-8"))}
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
        by_number = len(nums_m & nums_t) >= 0.8 * len(nums_m) and not ref.startswith("J101")
        a, t, err = fit(model, target, by_number)
        if by_number and err > TOL:                       # numbering differs (e.g. A/B/C vs 1/2/3): geometry only
            a2, t2, err2 = fit(model, target, False)
            if err2 < err:
                a, t, err, by_number = a2, t2, err2, False
        # KiCad's own footprint through the same fit -> the angle that corresponds to KiCad's .pos rotation
        lib, name = str(fp.GetFPID().GetLibNickname()), str(fp.GetFPID().GetLibItemName())
        kfp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
        kmodel = [(p.GetNumber(), mm(p.GetPosition().x), -mm(p.GetPosition().y)) for p in kfp.Pads()
                  if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH and p.GetNumber() and p.GetNumber() in nums_t]
        kmodel = [(n, -x if bottom else x, y) for n, x, y in kmodel]
        ka, _, kerr = fit(kmodel, target, not ref.startswith("J101"))
        prot = float(kpos[ref]["Rot"]) % 360
        if not bottom and kerr < 0.05 and round(ka) % 360 != round(prot) % 360:
            print(f"  note: {ref} top-side KiCad fit {ka} vs .pos {prot:.0f}")
        if bottom and kerr < 0.05:
            conv.setdefault(round((prot + ka) % 360), 0)
            conv[round((prot + ka) % 360)] += 1
        rows.append([ref, t, a, ka, prot, bottom])
        report.append([ref, code[ref], title, "bottom" if bottom else "top", f"{prot:.0f}", a, f"{t[0]:.3f}", f"{t[1]:.3f}",
                       f"{err:.3f}", "pad numbers" if by_number else "geometry only",
                       "OK" if err <= TOL else "LAND PATTERN MISMATCH - check this part"])
    # bottom convention: KiCad .pos rotation = (k - fitted angle) for KiCad's own footprints; k is the same for all
    k = max(conv, key=conv.get) if conv else 0
    print("bottom-side convention: pos rotation = (%d - top-view angle), from %d parts" % (k, conv.get(k, 0)), dict(conv))
    out = []
    for ref, t, a, ka, prot, bottom in rows:
        r = ((k - a) % 360) if bottom else a % 360
        out.append([ref, f"{t[0]:.4f}mm", f"{t[1]:.4f}mm", "Bottom" if bottom else "Top", f"{r:.0f}"])
    nat = lambda r: (re.sub(r"\d", "", r[0]), int(re.sub(r"\D", "", r[0]) or 0))
    out.sort(key=nat)
    for name, pick in (("bassberry_cpl_jlc.csv", lambda r: True), ("bassberry_cpl_jlc_top.csv", lambda r: r[3] == "Top"),
                       ("bassberry_cpl_jlc_bottom.csv", lambda r: r[3] == "Bottom")):
        with open(os.path.join(J, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            w.writerows([r for r in out if pick(r)])
    with open(os.path.join(J, "rotfix_report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "LCSC", "JLC footprint", "Side", "KiCad pos rot", "Fitted top-view angle", "X", "Y",
                    "Fit rms mm", "Matched by", "Verdict"])
        w.writerows(report)
    bad = [r for r in report if not r[-1].startswith("OK")]
    print(f"{len(report)} parts fitted, {len(bad)} land-pattern mismatches")
    for r in bad:
        print("  MISMATCH", r[0], r[1], r[2], "rms", r[8])


if __name__ == "__main__":
    main()
