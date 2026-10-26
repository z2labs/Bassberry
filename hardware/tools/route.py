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
# ---------------------------------------------------------------- net widths (mm), IPC-2152-ish for 1 oz outer / 0.5 oz inner
WIDTH = [
    (f"{BT}CELL*", 2.5, 0.3),                                   # up to 10 A pack current
    ("+BATT", 2.0, 0.3),
    ("+5V", 2.0, 0.3), ("+5V_BUCK", 2.0, 0.3), (f"{PW}BUCK_SW", 1.5, 0.3),   # Pi 5 V / 5 A
    ("VBUS", 1.5, 0.3), (f"{PW}CHG_VIN", 1.5, 0.3), (f"{PW}CHG_NODE?", 1.5, 0.3),
    (f"{PW}CHG_LX?", 1.5, 0.3),
    ("PVDD_SUB", 1.2, 0.3), (f"{PW}BOOST_SW", 1.0, 0.3), (f"{PW}BOOST_OUT", 1.0, 0.3),
    (f"{A}AMP1_AP", 1.0, 0.25), (f"{A}AMP1_AN", 1.0, 0.25), (f"{A}AMP1_BP", 1.0, 0.25), (f"{A}AMP1_BN", 1.0, 0.25),
    (f"{A}AMP2_P", 1.2, 0.25), (f"{A}AMP2_N", 1.2, 0.25), (f"{A}SAT_*", 1.0, 0.25), (f"{A}SUB_*", 1.2, 0.25),
    ("+3V3", 0.5, 0.2), ("+3V3_AON", 0.4, 0.2), ("+3V3_USB", 0.4, 0.2),
    (f"{PW}CHG_HG*", 0.5, 0.2), (f"{PW}CHG_LG*", 0.5, 0.2), (f"{PW}CHG_BST?", 0.5, 0.2), (f"{PW}CHG_SN?", 0.5, 0.2),
    (f"{PW}CHG_CSN?", 0.3, 0.2), (f"{A}AMP?_BST*", 0.5, 0.2), (f"{PW}BUCK_BST", 0.4, 0.2),
]
POWER = [f"{BT}CELL*", "+BATT", "+5V", "+5V_BUCK", f"{PW}BUCK_SW", "VBUS", f"{PW}CHG_VIN", f"{PW}CHG_NODE?", f"{PW}CHG_LX?",
         "PVDD_SUB", f"{PW}BOOST_SW", f"{PW}BOOST_OUT", f"{A}AMP1_AP", f"{A}AMP1_AN", f"{A}AMP1_BP", f"{A}AMP1_BN",
         f"{A}AMP2_P", f"{A}AMP2_N", f"{A}SAT_*", f"{A}SUB_*", "+3V3", "+3V3_AON", "+3V3_USB"]
FAST = ["I2S_*", f"{PI}PI_BCLK", f"{PI}PI_LRCLK", f"{PI}PI_DOUT", "USB_DP", "USB_DN", "I2C_*", f"{PI}ID_S?",
        f"{A}AMP2_SDIN", f"{A}AMP1_SDOUT"]
PASSES = [
    ("pass1_power", POWER, ["-top", "F.Cu:3", "-via", "6000"]),
    ("pass2_fast", FAST, ["-top", "F.Cu:10", "-top", "B.Cu:2", "-via", "2500"]),
    ("pass3_rest", ["*"], ["-top", "F.Cu:4", "-via", "2000"]),
]


def rules(only):
    return {
        "ignore_nets": ["GND"],
        "nets": [{"match": m, "width_mm": w, "clearance_mm": c} for (m, w, c) in WIDTH],
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
    summary = []
    for name, only, args in PASSES:
        dsn, ses, rep, rj = (os.path.join(OUT, name + e) for e in (".dsn", ".ses", "_report.json", "_rules.json"))
        export_dsn(b, dsn)
        json.dump(rules(only), open(rj, "w"), indent=1)
        cmd = [SR, "-de", dsn, "-do", ses, "-rules", rj, "-report", rep] + args
        print(">>", " ".join(cmd), flush=True)
        t0 = time.time()
        logf = os.path.join(OUT, name + ".log")
        with open(logf, "w", encoding="utf-8") as fh:      # streamed, so a long pass can be watched
            p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, text=True)
        log = open(logf, encoding="utf-8", errors="replace").read()
        bad = [l for l in log.splitlines() if l.startswith("!")]
        print(f"   {name}: exit {p.returncode}, {time.time() - t0:.0f} s, unrouted: {len(bad)}")
        for l in bad[:30]:
            print("   ", l)
        if p.returncode != 0 or not os.path.exists(ses):
            print(log[-3000:]); sys.exit(1)
        import_ses(b, ses)
        summary.append((name, len(bad)))
        pcbnew.SaveBoard(BOARD, b)
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
