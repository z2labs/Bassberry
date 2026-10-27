"""Route the Bassberry board with srouter, following srouter docs/USAGE.md (rev-B3 layer roles, 3 passes).

   "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/route.py

Input : hardware/bassberry/bassberry.kicad_pcb (placed by pcb_build.py; kept as bassberry_placed.kicad_pcb)
Output: hardware/bassberry/bassberry.kicad_pcb (routed), route/passN.{dsn,ses,json}

Layer roles (DSN layer type + -top cost), GND is never routed (In2 plane + F/B pours, stitched afterwards):
  pass 0 trunks  the wide part of every high-current net, between its big pads (net split, see trunk_pass): outer only
  pass 1 power   wide rails, battery, charger power stage, speaker outputs:  B.Cu open, In1 open, F.Cu cost 3
  pass 2 fast    I2S, I2C, USB D+/D-, HAT ID:                                In1 open, B.Cu cost 2, F.Cu cost 10
  pass 3 rest    everything else:                                           In1 + B.Cu open, F.Cu cost 4
In2.Cu (GND plane): closed in passes 0, 1a and 2 (fast signals keep an unbroken reference); open at a high cost
(IN2) in pass 1b, pass 3 and the repair - Zoltan 2026-10-27: short GND-plane crossings are fine, the plane is stitched
densely afterwards. The router style is always oct + smooth (USAGE.md: known limits).
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
        if ds and min(ds) < 0.35:      # 0.4 mm pitch QFN pins: two 0.2 mm tracks + 0.15 mm clearance must fit
            wc = 0.2
        out.append((g, wc, CLR))
    return out


# pass 1 also takes everything that escapes from between power pins (charger QFN, amp bootstrap pins), so the
# fattened power copper never walls them in
LOCAL = [f"{PW}CHG_*", "CHG_LED_*", "NTC", f"{PW}CC?", f"{A}AMP?_BST*", f"{A}AMP?_VRDIG", f"{A}AMP?_AVDD", f"{PW}BUCK_*", f"{PW}BOOST_*"]
# 1a: high-current nets that never touch a fine-pitch pin - routed alone, outer copper only, vias avoided
HEAVY = [f"{BT}CELL*", "+5V", "+5V_BUCK", f"{PW}BUCK_SW", f"{PW}BOOST_SW", f"{PW}BOOST_OUT", f"{A}SAT_*", f"{A}SUB_*"]
# 1b: the high-current nets that start on a 0.4/0.65 mm-pitch pin (charger QFN, amp PVDD/OUT) negotiate together with
# everything else that escapes from those packages; inner layer and vias expensive so the current stays outside
POWER = LOCAL + ["+BATT", "VBUS", f"{PW}CHG_VIN", f"{PW}CHG_NODE?", f"{PW}CHG_LX?", "PVDD_SUB",
                 f"{A}AMP1_AP", f"{A}AMP1_AN", f"{A}AMP1_BP", f"{A}AMP1_BN", f"{A}AMP2_P", f"{A}AMP2_N",
                 "+3V3", "+3V3_AON", "+3V3_USB"]
FAST = ["I2S_*", f"{PI}PI_BCLK", f"{PI}PI_LRCLK", f"{PI}PI_DOUT", "USB_DP", "USB_DN", "I2C_*", f"{PI}ID_S?",
        "AMP*_PDN", "PI_*",                                    # everything else that leaves the Pi header
        f"{A}AMP2_SDIN", f"{A}AMP1_SDOUT"]
# amplifier outputs: pin -> inductor -> connector on the parts side only - a via in a 2-3 A speaker path is a neck
AMP_OUT = [f"{A}AMP1_AP", f"{A}AMP1_AN", f"{A}AMP1_BP", f"{A}AMP1_BN", f"{A}AMP2_P", f"{A}AMP2_N", f"{A}SAT_*", f"{A}SUB_*"]
PASSES = [
    # 1a: high-current nets alone, outer layers only (In1 closed: 0.5 oz inner copper carries a third), vias avoided
    ("pass1a_heavy", HEAVY, ["-top", "F.Cu:6", "-via", "20000", "-it", "80"]),
    # 1b: everything that escapes from between power pins (QFN, amp bootstrap), the 3V3 rails
    ("pass1b_local", POWER, ["-top", "F.Cu:2", "-top", "In1.Cu:40"] + IN2 + ["-via", "8000", "-it", "80"]),
    ("pass2_fast", FAST, ["-top", "F.Cu:10", "-top", "B.Cu:2", "-via", "2500"]),
    ("pass3_rest", ["*"], ["-top", "F.Cu:4"] + IN2 + ["-via", "2000"]),
]


def rules(only, width):
    return {
        "ignore_nets": ["GND"],
        "nets": [{"match": m, "width_mm": w, "clearance_mm": c} for (m, w, c) in width],
        "diff_pairs": [{"p": "USB_DP", "n": "USB_DN", "gap_mm": 0.15}],
        "only": "|".join(only), "smooth": True, "style": "oct", "pad_entry": True,
    }


IN2 = ["-top", "In2.Cu:30"]   # wires on the GND plane only where nothing else fits
VIA_PAD_INSET = 0.17   # mm: via keep-out = SMD pad inset by this (srouter keeps a via centre one via diameter off it)


def pad_via_keepouts(board):
    """srouter lets a via ring overlap an SMD pad (only the hole is kept off); JLC DFM rates a via touching a pad as
    Danger. A keep-out on In2.Cu (the closed GND plane: no wires there) over every SMD pad, inset so that a 0.45/0.6 mm
    via ring ends >= 0.05 mm off the pad, stops vias only - srouter blocks vias through every keep-out layer."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            bb = p.GetBoundingBox()
            x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (bb.GetX(), bb.GetY(), bb.GetRight(), bb.GetBottom()))
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            hx, hy = max(0.01, (x1 - x0) / 2 - VIA_PAD_INSET), max(0.01, (y1 - y0) / 2 - VIA_PAD_INSET)
            pts = [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)]
            out.append('    (keepout "" (polygon In2.Cu 0 ' + " ".join(f"{x * 1000:.0f} {-y * 1000:.0f}" for x, y in pts) + "))")
    return "\n".join(out)


def closed_for(name, args):
    """layers exported as power (no wires): In2 unless the pass opens it (IN2 in its args), In1 too in pass 1a"""
    c = () if "In2.Cu:30" in args else ("In2.Cu",)
    return c + (("In1.Cu",) if name in ("pass1a_heavy", "pass1a2_amp") else ())


def export_dsn(board, path, closed=("In2.Cu",)):
    assert pcbnew.ExportSpecctraDSN(board, path), "DSN export failed"
    t = open(path, encoding="utf-8").read()
    t = t.replace("    (boundary", pad_via_keepouts(board) + "\n    (boundary", 1)      # after the layer list
    open(path, "w", encoding="utf-8").write(t)
    # In2.Cu is the GND plane: closed unless the pass opens it; pass 1a also closes In1.Cu
    t2 = t
    for l in ("In1.Cu", "In2.Cu"):
        typ = "power" if l in closed else "signal"
        t2 = re.sub(r"\(layer " + re.escape(l) + r"\s*\(type \w+\)", f"(layer {l} (type {typ})", t2)
    open(path, "w", encoding="utf-8").write(t2)
    return t2 != t


def import_ses(board, ses):
    assert pcbnew.ImportSpecctraSES(board, ses), "SES import failed: " + ses
    for t in board.GetTracks():   # the import resets every via drill to the default
        if t.GetClass() == "PCB_VIA":
            w = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))
            t.SetDrill(pcbnew.FromMM(0.2 if w < 0.5 else 0.3))


# ------------------------------------------------------------ pass 0: power trunks (neck-down by net split)
# srouter gives a net ONE width that must fit its smallest pad, so a battery rail that also touches a 0.3 mm amp pin
# would be routed 0.2 mm wide end to end. Pass 0 routes only the wide part of each high-current net: on a scratch copy
# of the board the small pads of the net are moved to a dummy net, and srouter joins the big pads (holders, fuse,
# 2512 links, inductors, MOSFET tabs, connectors) at the widest width those pads allow. The SES goes back into the real
# board on the real net, and the later passes join the small pads to that trunk at their own width: a neck-down
# that happens only at the last millimetres before a fine-pitch pin.
TRUNK_MAX = 1.6      # mm, widest trunk asked from the router (fatten.py and the pours widen further)
TRUNK_MAX_NET = {}   # (2.4 mm battery-link trunks congested pass 1b; the links get In1 copies of their pours instead)
TRUNK_MIN = 0.5      # mm, a trunk narrower than this is no trunk


def trunk_plan(board):
    import fnmatch
    from fatten import TARGET
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if n:
                s = p.GetSize(pcbnew.F_Cu)
                pads.setdefault(n, []).append((min(pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)), p))
    plan = {}
    for n, ps in pads.items():
        tg = next((w for g, w, a in TARGET if fnmatch.fnmatchcase(n, g)), None)
        if tg is None:
            continue
        want = min(next((w for g, w in TRUNK_MAX_NET.items() if fnmatch.fnmatchcase(n, g)), TRUNK_MAX), tg)
        fits = sorted((d * 0.95 for d, p in ps), reverse=True)
        if len(fits) < 2 or fits[1] < TRUNK_MIN:
            continue
        # widest width that still joins at least two pads (and every pad that is at least that wide);
        # 0805/0603 decoupling caps and fine-pitch pins become taps
        w = round(min(want, fits[1]), 2)
        # a pad joins the trunk only if the trunk fits it; everything narrower is a tap, routed later
        small = [p for d, p in ps if d * 0.95 < w]
        plan[n] = (w, small)
    return plan


def trunk_pass(b):
    plan = trunk_plan(b)
    print("trunks:", ", ".join(f"{n} {w} mm ({len(sm)} taps)" for n, (w, sm) in sorted(plan.items())))
    tmp = os.path.join(OUT, "pass0_split.kicad_pcb")
    pcbnew.SaveBoard(tmp, b)
    b2 = pcbnew.LoadBoard(tmp)
    taps = {}
    for fp in b2.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if n in plan:
                d = min(pcbnew.ToMM(p.GetSize(pcbnew.F_Cu).x), pcbnew.ToMM(p.GetSize(pcbnew.F_Cu).y))
                if d * 0.95 < plan[n][0]:
                    if n not in taps:
                        ni = pcbnew.NETINFO_ITEM(b2, "TAP~" + n.replace("/", "_")); b2.Add(ni); taps[n] = ni
                    p.SetNet(taps[n])
    name = "pass0_trunk"
    dsn, ses, rep, rj = (os.path.join(OUT, name + e) for e in (".dsn", ".ses", "_report.json", "_rules.json"))
    export_dsn(b2, dsn, ("In2.Cu", "In1.Cu"))
    r = rules(list(plan), [(n, w, CLR) for n, (w, sm) in plan.items()])
    json.dump(r, open(rj, "w"), indent=1)
    return name, dsn, ses, rep, rj


# ------------------------------------------------------------ rip-up and reroute for what the passes left
# A net that lost the negotiation (or got walled in by nets routed in a later pass) is routed again first: the
# small-signal nets that pass within RIP mm of its pads are ripped up, the stuck net is routed alone, then the ripped
# nets are routed back. Power, trunks, GND and the pre-routed USB pair are never ripped.
RIP = 1.2
NO_RIP = ["GND", "USB_DP", "USB_DN"]


def stuck_nets(logf):
    out = []
    for l in open(logf, encoding="utf-8", errors="replace").read().splitlines():
        m = re.match(r"\s*!\s*(\S+?):", l.strip())
        if m and not l.strip().startswith("! diff pair"):
            out.append(m.group(1))
    return out


def run_pass(b, name, only, args, width):
    dsn, ses, rep, rj = (os.path.join(OUT, name + e) for e in (".dsn", ".ses", "_report.json", "_rules.json"))
    export_dsn(b, dsn, closed_for(name, args))
    json.dump(rules(only, width), open(rj, "w"), indent=1)
    logf = os.path.join(OUT, name + ".log")
    with open(logf, "w", encoding="utf-8") as fh:
        p = subprocess.run([SR, "-de", dsn, "-do", ses, "-rules", rj, "-report", rep] + args, stdout=fh, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0 or not os.path.exists(ses):
        print(f"   {name}: srouter failed"); return b, None
    import_ses(b, ses)
    pcbnew.SaveBoard(BOARD, b)
    b = pcbnew.LoadBoard(BOARD)
    return b, stuck_nets(logf)


def rip_up(stuck):
    """(own process) rip the small-signal nets within RIP mm of the stuck nets' pads, and the stuck nets themselves"""
    import fnmatch
    b = pcbnew.LoadBoard(BOARD)
    protected = lambda n: (not n or n in NO_RIP or any(fnmatch.fnmatchcase(n, g) for g in HEAVY + POWER))
    segs = []
    for t in b.GetTracks():
        a = (t.GetPosition() if t.GetClass() == "PCB_VIA" else t.GetStart())
        e = (t.GetPosition() if t.GetClass() == "PCB_VIA" else t.GetEnd())
        segs.append((t.GetNetname(), pcbnew.ToMM(a.x), pcbnew.ToMM(a.y), pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)))
    rip = set()
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() not in stuck:
                continue
            cx, cy = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            reach = RIP + pcbnew.ToMM(max(p.GetSize(pcbnew.F_Cu).x, p.GetSize(pcbnew.F_Cu).y)) / 2
            for (n, ax, ay, ex, ey) in segs:
                if n in stuck or protected(n):
                    continue
                L = (ex - ax) ** 2 + (ey - ay) ** 2
                k = 0 if L == 0 else max(0, min(1, ((cx - ax) * (ex - ax) + (cy - ay) * (ey - ay)) / L))
                if ((ax + k * (ex - ax) - cx) ** 2 + (ay + k * (ey - ay) - cy) ** 2) ** 0.5 < reach:
                    rip.add(n)
    for t in list(b.GetTracks()):
        if t.GetNetname() in rip or t.GetNetname() in stuck:
            b.Remove(t)
    pcbnew.SaveBoard(BOARD, b)
    return sorted(rip)


def sub(*args):
    """run one step of the repair in a fresh pcbnew process (pcbnew's track list goes stale in a long-lived one)"""
    out = os.path.join(OUT, "repair_step.json")
    if os.path.exists(out):
        os.remove(out)
    p = subprocess.run([sys.executable, os.path.abspath(__file__)] + list(args) + [out], capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(out):
        print("   repair step failed:", args[0], p.stderr[-800:])
        return None
    return json.load(open(out))


def repair(summary):
    stuck = stuck_nets(os.path.join(OUT, "pass3_rest.log"))
    args = ["-top", "F.Cu:4"] + IN2 + ["-via", "1500", "-it", "120"]
    for rnd in range(1, 4):
        if not stuck:
            break
        print(f"   repair {rnd}: stuck {stuck}")
        rip = sub("--rip", json.dumps(stuck))
        if rip is None:
            break
        print(f"   repair {rnd}: ripped {rip}")
        s1 = sub("--pass", f"repair{rnd}a", json.dumps(stuck), json.dumps(args))
        if s1 is None:
            break
        s2 = sub("--pass", f"repair{rnd}b", json.dumps(rip), json.dumps(args)) if rip else []
        if s2 is None:
            break
        stuck = sorted(set(s1) | set(s2))
        summary.append((f"repair{rnd}", len(stuck)))
        print(f"   repair {rnd}: left {stuck}")
    if stuck:
        print("   repair: still unrouted", stuck)


def main():
    shutil.copy(PLACED, BOARD)   # always route from the placed board written by pcb_build.py
    # gate: no pad may be walled in by its neighbours (holes, pads) before the router even starts
    g = subprocess.run([sys.executable, os.path.join(HERE, "escape_probe.py"), PLACED, "ALL", "0.2"], capture_output=True, text=True)
    print("escape probe:", g.stdout.strip().splitlines()[-1] if g.stdout.strip() else g.stderr[-300:])
    if g.returncode != 0:
        print(g.stdout); sys.exit(1)
    # (fanout.py exists, but straight dog-bones on a 0.4 mm-pitch QFN wall the neighbouring pins in: not used)
    b = pcbnew.LoadBoard(BOARD)
    width = widths(b)
    print("routing widths:", ", ".join(f"{g} {w}" for g, w, c in width))
    summary = []
    for name, only, args in [("pass0_trunk", None, ["-top", "F.Cu:3", "-via", "6000", "-it", "80"])] + PASSES:
        if only is None:
            name, dsn, ses, rep, rj = trunk_pass(b)
        else:
            dsn, ses, rep, rj = (os.path.join(OUT, name + e) for e in (".dsn", ".ses", "_report.json", "_rules.json"))
            export_dsn(b, dsn, closed_for(name, args))
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
        if name in ("pass0_trunk", "pass1b_local"):    # give the power copper its width before the rest is routed around it
            subprocess.run([sys.executable, os.path.join(HERE, "fatten.py"), BOARD])
        b = pcbnew.LoadBoard(BOARD)
    pcbnew.SaveBoard(BOARD, b)
    repair(summary)
    b = pcbnew.LoadBoard(BOARD)
    n = add_thermal_vias(b, pcbnew)
    print("SoC via field restored:", n)
    if not any(z.GetZoneName().startswith("GND_") for z in b.Zones()):
        add_gnd_pours(b, pcbnew)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(BOARD, b)
    print("routed ->", BOARD, summary)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rip":
        json.dump(rip_up(json.loads(sys.argv[2])), open(sys.argv[3], "w"))
    elif len(sys.argv) > 1 and sys.argv[1] == "--pass":
        bb = pcbnew.LoadBoard(BOARD)
        _, left = run_pass(bb, sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4]), widths(bb))
        if left is not None:
            json.dump(left, open(sys.argv[5], "w"))
    else:
        main()
