"""JLCPCB assembly files from the netlist, the KiCad placement and the LCSC part table.

    python3 hardware/tools/jlc_bom_cpl.py

in : hardware/bassberry/bassberry.net                (refs, values, footprints, DNP flags)
     hardware/bassberry/jlc/bassberry_pos_kicad.csv  (kicad-cli pcb export pos, both sides; written by jlc_fab.ps1)
     hardware/bassberry/jlc/lcsc_parts.csv           (value + footprint -> LCSC code, MPN, maker; every code checked
                                                      on lcsc.com / jlcpcb.com/parts, URL in the table)
out: hardware/bassberry/jlc/bassberry_bom_jlc.csv    JLC upload format: Comment, Designator, Footprint, LCSC Part #
     hardware/bassberry/jlc/bassberry_cpl_jlc.csv    JLC upload format: Designator, Mid X, Mid Y, Layer, Rotation
     hardware/bassberry/jlc/bassberry_bom_full.csv   the same parts with MPN, maker, Basic/Extended, SMT/THT, notes
     hardware/bassberry/jlc/not_assembled.csv        DNP lines, solder jumpers, test point, BMS wire pads (no part)
Exit code 1 if a fitted part has no LCSC code, or the placement and the netlist disagree.
"""
import csv, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, "..", "bassberry"))
J = os.path.join(PRJ, "jlc")


def netlist():
    t = open(os.path.join(PRJ, "bassberry.net"), encoding="utf-8").read()
    out = {}
    for b in re.split(r"\(comp\s", t)[1:]:
        r = re.search(r'\(ref "([^"]+)"\)', b)
        if not r:
            continue
        v = re.search(r'\(value "([^"]*)"\)', b).group(1)
        f = re.search(r'\(footprint "([^"]*)"\)', b).group(1)
        out[r.group(1)] = dict(value=v, fp=f.split(":")[-1], dnp='(name "dnp")' in b.split("(sheetpath")[0])
    return out


def main():
    comps = netlist()
    parts = {}
    for row in csv.DictReader(open(os.path.join(J, "lcsc_parts.csv"), encoding="utf-8")):
        parts[(row["value"], row["footprint"])] = row
    pos = {r["Ref"]: r for r in csv.DictReader(open(os.path.join(J, "bassberry_pos_kicad.csv"), encoding="utf-8"))}
    errors = []
    groups = collections.defaultdict(list)
    skipped = []
    for ref, c in sorted(comps.items()):
        p = parts.get((c["value"], c["fp"]))
        if c["dnp"] or p is None and c["fp"].startswith(("SolderJumper", "TestPoint", "SolderWire")):
            skipped.append((ref, c["value"], c["fp"], "DNP" if c["dnp"] else "no part (pad / jumper / wire)"))
            continue
        if p is None or not re.fullmatch(r"C\d+", p["lcsc"].strip()):
            if p is not None and p["lcsc"].strip().upper() in ("NOPART", "DNP"):
                skipped.append((ref, c["value"], c["fp"], p.get("notes", "no part")))
                continue
            errors.append(f"{ref} {c['value']} {c['fp']}: no LCSC code")
            continue
        if ref not in pos:
            errors.append(f"{ref}: not in the placement file")
            continue
        groups[(c["value"], c["fp"])].append(ref)
    bom_rows = []
    nat = lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0))
    with open(os.path.join(J, "bassberry_bom_jlc.csv"), "w", newline="", encoding="utf-8") as fb, \
            open(os.path.join(J, "bassberry_bom_full.csv"), "w", newline="", encoding="utf-8") as ff:
        wb = csv.writer(fb); wf = csv.writer(ff)
        wb.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        wf.writerow(["Qty", "Comment", "Designator", "Footprint", "LCSC Part #", "MPN", "Manufacturer", "Basic/Extended",
                     "SMT/THT", "Key spec", "Checked at", "Notes"])
        for (v, fp), refs in sorted(groups.items(), key=lambda kv: nat(sorted(kv[1], key=nat)[0])):
            p = parts[(v, fp)]
            refs = sorted(refs, key=nat)
            # JLC matches by the LCSC code; a bare comment like "BT" is left unmatched by its importer, so non-passive
            # lines carry the maker part number in front of the schematic value
            cm = v if refs[0][0] in "RC" or not p.get("mpn") else f"{p['mpn']} ({v})"
            wb.writerow([cm, ",".join(refs), fp, p["lcsc"].strip()])
            bom_rows.append([cm, refs, fp, p["lcsc"].strip()])
            wf.writerow([len(refs), v, ",".join(refs), fp, p["lcsc"].strip(), p.get("mpn", ""), p.get("manufacturer", ""),
                         p.get("basic_or_extended", ""), p.get("smt_or_tht", ""), p.get("key_spec", ""),
                         p.get("verified_url", ""), p.get("notes", "")])
    placed = {r for refs in groups.values() for r in refs}
    with open(os.path.join(J, "bassberry_cpl_jlc.csv"), "w", newline="", encoding="utf-8") as fc:
        w = csv.writer(fc)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for ref in sorted(placed, key=nat):
            r = pos[ref]
            w.writerow([ref, f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm",
                        "Top" if r["Side"].lower().startswith("top") else "Bottom", f"{float(r['Rot']) % 360:.0f}"])
    # one file pair per side as well: JLC assembles one side or both; the top side here is only the holders, the tact
    # switches, the encoder and the 2x20 socket (hand-soldering them saves the second-side assembly)
    for side in ("Top", "Bottom"):
        on = {ref for ref in placed if ("Top" if pos[ref]["Side"].lower().startswith("top") else "Bottom") == side}
        with open(os.path.join(J, f"bassberry_bom_jlc_{side.lower()}.csv"), "w", newline="", encoding="utf-8") as fs:
            w = csv.writer(fs); w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
            for cm, refs, fp, code in bom_rows:
                d = [r for r in refs if r in on]
                if d:
                    w.writerow([cm, ",".join(d), fp, code])
        with open(os.path.join(J, f"bassberry_cpl_jlc_{side.lower()}.csv"), "w", newline="", encoding="utf-8") as fs:
            w = csv.writer(fs); w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            for ref in sorted(on, key=nat):
                r = pos[ref]
                w.writerow([ref, f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm", side, f"{float(r['Rot']) % 360:.0f}"])
        print(f"{side}: {len(on)} parts")
    with open(os.path.join(J, "not_assembled.csv"), "w", newline="", encoding="utf-8") as fn:
        w = csv.writer(fn); w.writerow(["Designator", "Value", "Footprint", "Why"])
        for s in sorted(skipped, key=lambda s: nat(s[0])):
            w.writerow(s)
    print(f"BOM lines {len(groups)}, placed parts {len(placed)}, not assembled {len(skipped)}")
    for e in errors:
        print("ERROR", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
