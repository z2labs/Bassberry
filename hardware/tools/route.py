"""Route the Bassberry board with srouter, following srouter docs/USAGE.md (rev-B3 layer roles, 3 passes).

   "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/route.py

Input : hardware/bassberry/bassberry.kicad_pcb (placed by pcb_build.py; kept as bassberry_placed.kicad_pcb)
Output: hardware/bassberry/bassberry.kicad_pcb (routed), route/passN.{dsn,ses,json}

Layer roles (DSN layer type + -top cost), GND is never routed (In2 plane + F/B pours, stitched afterwards):
  pass 1 power   wide rails, battery, charger power stage, speaker outputs:  B.Cu open, In1 open, F.Cu cost 3
  pass 2 fast    I2S, I2C, USB D+/D-, HAT ID:                                In1 open, B.Cu cost 2, F.Cu cost 10
  pass 3 rest    everything else:                                           In1 + B.Cu open, F.Cu cost 4
In2.Cu is exported as a power layer (closed). The router style is always oct + smooth (USAGE.md: known limits).
After the passes: via drill repair, GND pours re-filled, SoC via field restored; post-processing is run by postroute.ps1.
"""
import os, sys, re, json, shutil, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from board_geom import add_thermal_vias, add_gnd_pours

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.normpath(os.path.join(HERE, "..", "bassberry"))
OUT = os.path.join(PRJ, "route")
SR = os.environ.get("SROUTER", r"C:\Users\RF\Documents\GitHub\srouter-feat\target\release\srouter.exe")
BOARD = os.path.join(PRJ, "bassberry.kicad_pcb")
PLACED = os.path.join(PRJ, "bassberry_placed.kicad_pcb")
os.makedirs(OUT, exist_ok=True)

A = "/audio/"; PW = "/power/"; BT = "/battery/"; PI = "/pi/"
CLR = 0.15   # netclass clearance (QFN40 0.4 mm pitch)
# routing width wish per net glob (mm). srouter routes a net with ONE width that must fit its smallest pad
# (check.rs: 'track will wall the pad in'), so route.py clips each wish to the smallest pad of the net and
# fatten.py widens the power copper afterwards, necking down only where it has to.
WISH = [
    (f"{BT}CELL*", 0.8), ("+BATT", 0.8), ("+5V", 0.8), ("+5V_BUCK", 0.8), (f"{PW}BUCK_SW", 0.8),
    ("VBUS", 0.6), (f"{PW}CHG_VIN", 0.6), (f"{PW}CHG_NODE?", 0.6), (f"{PW}CHG_LX?", 0.6),
    ("PVDD_SUB", 0.6), (f"{PW}BOOST_SW", 0.6), (f"{PW}BOOST_OUT", 0.6),
    (f"{A}AMP1_AP", 0.4), (f"{A}AMP1_AN", 0.4), (f"{A}AMP1_BP", 0.4), (f"{A}AMP1_BN", 0.4),
    (f"{A}AMP2_P", 0.4), (f"{A}AMP2_N", 0.4), (f"{A}SAT_*", 0.6), (f"{A}SUB_*", 0.8),
    ("+3V3", 0.4), ("+3V3_AON", 0.3), ("+3V3_USB", 0.3),
    (f"{PW}CHG_HG*", 0.3), (f"{PW}CHG_LG*", 0.3), (f"{PW}CHG_BST?", 0.3), (f"{PW}CHG_SN?", 0.3),
    (f"{A}AMP?_BST*", 0.3), (f"{PW}BUCK_BST", 0.3),
]


def widths(board):
    """clip each wish to the narrowest pad of the nets it matches"""
    import fnmatch
    small = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if not n:
                continue
            s = p.GetSize(pcbnew.F_Cu) if hasattr(p, "GetSize") else None
            d = min(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y))
            small[n] = min(small.get(n, 99), d)
    out = []
    for g, w in WISH:
        ds = [d for n, d in small.items() if fnmatch.fnmatchcase(n, g)]
        wc = max(0.2, min([w] + [round(d * 0.95, 2) for d in ds]))
        out.append((g, wc, CLR))
    return out


# pass 1 also takes everything that escapes from between power pins (charger QFN, amp bootstrap pins), so the
# fattened power copper never walls them in
LOCAL = [f"{PW}CHG_*", f"{PW}CC?", f"{A}AMP?_BST*", f"{A}AMP?_VRDIG", f"{A}AMP?_AVDD", f"{PW}BUCK_*", f"{PW}BOOST_*"]
POWER = LOCAL + [f"{BT}CELL*", "+BATT", "+5V", "+5V_BUCK", f"{PW}BUCK_SW", "VBUS", f"{PW}CHG_VIN", f"{PW}CHG_NODE?", f"{PW}CHG_LX?",
         "PVDD_SUB", f"{PW}BOOST_SW", f"{PW}BOOST_OUT", f"{A}AMP1_AP", f"{A}AMP1_AN", f"{A}AMP1_BP", f"{A}AMP1_BN",
         f"{A}AMP2_P", f"{A}AMP2_N", f"{A}SAT_*", f"{A}SUB_*", "+3V3", "+3V3_AON", "+3V3_USB"]
FAST = ["I2S_*", f"{PI}PI_BCLK", f"{PI}PI_LRCLK", f"{PI}PI_DOUT", "USB_DP", "USB_DN", "I2C_*", f"{PI}ID_S?",
        f"{A}AMP2_SDIN", f"{A}AMP1_SDOUT"]
PASSES = [
    ("pass1_power", POWER, ["-top", "F.Cu:2", "-top", "In1.Cu:15", "-via", "6000"]),   # heavy copper stays outside
    ("pass2_fast", FAST, ["-top", "F.Cu:10", "-top", "B.Cu:2", "-via", "2500"]),
    ("pass3_rest", ["*"], ["-top", "F.Cu:4", "-via", "2000"]),
]


def rules(only, width):
    return {
        "ignore_nets": ["GND"],
        "nets": [{"match": m, "width_mm": w, "clearance_mm": c} for (m, w, c) in width],
        "diff_pairs": [{"p": "USB_DP", "n": "USB_DN", "gap_mm": 0.15}],
        "only": "|".join(only), "smooth": True, "style": "oct", "pad_entry": True,
    }


def export_dsn(board, path):
    assert pcbnew.ExportSpecctraDSN(board, path), "DSN export failed"
    t = open(path, encoding="utf-8").read()
    # In2.Cu is the solid GND plane: closed for the router
    t2 = re.sub(r"\(layer In2\.Cu\s*\(type \w+\)", "(layer In2.Cu (type power)", t)
    open(path, "w", encoding="utf-8").write(t2)
    return t2 != t


def import_ses(board, ses):
    assert pcbnew.ImportSpecctraSES(board, ses), "SES import failed: " + ses
    for t in board.GetTracks():   # the import resets every via drill to the default
        if t.GetClass() == "PCB_VIA":
            w = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))
            t.SetDrill(pcbnew.FromMM(0.2 if w < 0.5 else 0.3))


def main():
    shutil.copy(PLACED, BOARD)   # always route from the placed board written by pcb_build.py
    b = pcbnew.LoadBoard(BOARD)
    width = widths(b)
    print("routing widths:", ", ".join(f"{g} {w}" for g, w, c in width))
    summary = []
    for name, only, args in PASSES:
        dsn, ses, rep, rj = (os.path.join(OUT, name + e) for e in (".dsn", ".ses", "_report.json", "_rules.json"))
        export_dsn(b, dsn)
        json.dump(rules(only, width), open(rj, "w"), indent=1)
        cmd = [SR, "-de", dsn, "-do", ses, "-rules", rj, "-report", rep] + args
        print(">>", " ".join(cmd), flush=True)
        t0 = time.time()
        logf = os.path.join(OUT, name + ".log")
        with open(logf, "w", encoding="utf-8") as fh:      # streamed, so a long pass can be watched
            p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, text=True)
        log = open(logf, encoding="utf-8", errors="replace").read()
        bad = [l.strip() for l in log.splitlines() if l.strip().startswith("!")]
        print(f"   {name}: exit {p.returncode}, {time.time() - t0:.0f} s, unrouted: {len(bad)}")
        for l in bad[:30]:
            print("   ", l)
        if p.returncode != 0 or not os.path.exists(ses):
            print(log[-3000:]); sys.exit(1)
        import_ses(b, ses)
        summary.append((name, len(bad)))
        pcbnew.SaveBoard(BOARD, b)
        if name == "pass1_power":     # give the power copper its width before the other nets are routed around it
            subprocess.run([sys.executable, os.path.join(HERE, "fatten.py"), BOARD])
        b = pcbnew.LoadBoard(BOARD)
    n = add_thermal_vias(b, pcbnew)
    print("SoC via field restored:", n)
    if not any(z.GetZoneName().startswith("GND_") for z in b.Zones()):
        add_gnd_pours(b, pcbnew)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(BOARD, b)
    print("routed ->", BOARD, summary)


if __name__ == "__main__":
    main()
