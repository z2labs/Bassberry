"""Layer 3: the drawn copper against the currents and voltages it has to carry.

  * track ampacity (IPC-2221: I = k * dT^0.44 * A^0.725, A in mil^2, k = 0.048 outer / 0.024 inner,
    1 oz outer = 35 um, 0.5 oz inner = 17.5 um (JLC 4-layer 1.6 mm), dT = 20 K)
  * vias at every layer change of a high-current net (a 0.3 mm drill, 25 um barrel ~ 1.5 A at 20 K, conservative)
  * IR drop of the Pi 5 V path (buck inductor -> ideal diode -> header pins 2/4) at 5 A
  * set-points from the divider values (buck, boost), PVDD window of the TAS5805M, LDO dissipation at 20 V VBUS

usage: kicad-python twin_analog.py board.kicad_pcb [--selftest]       exit 0 / 1 FAIL / 2 input / 3 selftest
"""
import os, sys, math, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from twin_common import Report, parse_value

DT = 20.0
CU = {"outer": 0.035, "inner": 0.0175}            # mm
RHO = 1.72e-5                                     # Ohm*mm (copper, 20 C)
VIA_A = 1.5                                       # A per 0.3 mm via
# design currents (A): sources: Pi 5 = 5 A at 5.1 V [RPI 27 W PSU]; TAS5805M 2 x ~2.5 A peak at 12 V;
# charger 30 W; the pack must deliver all of it: 5.1*5/0.9/10 + 2*2.5 = ~8 A at the lowest pack voltage
HEAVY = {
    "/battery/CELL0": 8.0, "/battery/CELL1": 8.0, "/battery/CELL2": 8.0, "/battery/CELL3": 8.0, "+BATT": 8.0,
    "+5V": 5.0, "+5V_BUCK": 5.0, "/power/BUCK_SW": 5.0,
    "VBUS": 3.0, "/power/CHG_VIN": 3.0, "/power/CHG_NODEB": 3.0, "/power/CHG_NODEC": 3.0,
    "/power/CHG_LX1": 3.5, "/power/CHG_LX2": 3.5,
    "PVDD_SUB": 3.0, "/audio/AMP2_P": 3.0, "/audio/AMP2_N": 3.0, "/audio/SUB_P": 3.0, "/audio/SUB_N": 3.0,
    "/audio/AMP1_AP": 2.0, "/audio/AMP1_AN": 2.0, "/audio/AMP1_BP": 2.0, "/audio/AMP1_BN": 2.0,
    "/audio/SAT_L_P": 2.0, "/audio/SAT_L_N": 2.0, "/audio/SAT_R_P": 2.0, "/audio/SAT_R_N": 2.0,
}


def ipc_amps(width_mm, layer_outer):
    t = CU["outer" if layer_outer else "inner"]
    a_mil2 = (width_mm / 0.0254) * (t / 0.0254)
    return (0.048 if layer_outer else 0.024) * DT ** 0.44 * a_mil2 ** 0.725


def load(path):
    import pcbnew
    from board_geom import OX, OY
    b = pcbnew.LoadBoard(path)
    mm = pcbnew.ToMM
    tracks, vias = [], []
    for t in b.GetTracks():
        n = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            vias.append((n, mm(t.GetPosition().x) - OX, mm(t.GetPosition().y) - OY, mm(t.GetDrill())))
        else:
            ly = t.GetLayer()
            tracks.append((n, b.GetLayerName(ly), ly in (pcbnew.F_Cu, pcbnew.B_Cu), mm(t.GetWidth()),
                           (mm(t.GetStart().x) - OX, mm(t.GetStart().y) - OY), (mm(t.GetEnd().x) - OX, mm(t.GetEnd().y) - OY)))
    pads = {}
    vals = {}
    for fp in b.GetFootprints():
        vals[fp.GetReference()] = fp.GetValue()
        for p in fp.Pads():
            pads[(fp.GetReference(), p.GetNumber())] = (p.GetNetname(), mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY)
    zones = [(z.GetNetname(), b.GetLayerName(z.GetLayer())) for z in b.Zones() if not z.GetIsRuleArea()]
    return tracks, vias, pads, vals, zones


def check(tracks, vias, pads, vals, zones):
    rep = Report("layer 3: copper vs current, set-points")
    # ---- ampacity
    for net, amps in HEAVY.items():
        ts = [t for t in tracks if t[0] == net]
        if not ts:
            if any(z[0] == net for z in zones):
                rep.add("PASS", "ampacity", f"{net}: carried by a pour"); continue
            rep.add("WARN", "ampacity", f"{net}: no tracks (unrouted or pad-to-pad)"); continue
        worst = min(ts, key=lambda t: ipc_amps(t[3], t[2]))
        cap = ipc_amps(worst[3], worst[2])
        rep.add("PASS" if cap >= amps else "FAIL", "ampacity",
                f"{net}: {amps:g} A needs; narrowest {worst[3]:.2f} mm on {worst[1]} carries {cap:.1f} A at {DT:g} K")
        # vias: cluster within 2.5 mm = one layer change
        vs = [v for v in vias if v[0] == net]
        groups = []
        for v in vs:
            for g in groups:
                if any(math.hypot(v[1] - w[1], v[2] - w[2]) < 2.5 for w in g):
                    g.append(v); break
            else:
                groups.append([v])
        need = math.ceil(amps / VIA_A)
        thin = [g for g in groups if len(g) < need]
        if groups:
            rep.add("PASS" if not thin else "FAIL", "vias", f"{net}: {len(groups)} layer change(s), need >= {need} vias each" +
                    ("" if not thin else f"; {len(thin)} with fewer, e.g. {len(thin[0])} at ({thin[0][0][1]:.1f}, {thin[0][0][2]:.1f})"))
    # ---- Pi 5 V path resistance (sum over the +5V and +5V_BUCK copper, conservative: series)
    r5 = 0.0
    for t in tracks:
        if t[0] in ("+5V", "+5V_BUCK"):
            L = math.hypot(t[5][0] - t[4][0], t[5][1] - t[4][1])
            r5 += RHO * L / (t[3] * CU["outer" if t[2] else "inner"])
    r5 += 0.017                                           # DMP3013SFV Rds(on) at -4.5 V [DS-DMP]
    drop = 5.0 * r5
    vout = 0.760 * (1 + parse_value(vals.get("R331", "0")) / parse_value(vals.get("R332", "1")))
    rep.add("PASS" if vout - drop >= 4.90 else "FAIL", "IR drop",
            f"Pi 5 V: buck {vout:.3f} V - {drop*1000:.0f} mV (copper + ZVD FET, 5 A) = {vout-drop:.3f} V at the header (>= 4.90 V: USB 4.75 V minimum + margin)")
    # ---- set-points
    vb = 0.6 * (1 + parse_value(vals.get("R341", "0")) / parse_value(vals.get("R342", "1")))
    rep.add("PASS" if 4.5 <= vb <= 26.4 else "FAIL", "PVDD", f"sub boost {vb:.1f} V inside TAS5805M PVDD 4.5-26.4 V; pack 9.0-12.6 V also inside")
    rep.add("PASS" if vb <= 28 * 0.85 else "FAIL", "boost", f"MT3608 SW max 28 V: {vb:.1f} V + Schottky drop leaves margin")
    # ---- LDO from VBUS at the 20 V PD contract (HT75xx-1 SOT-89: 250 mW, VIN max 24 V)
    i_ch340 = 0.015                                      # CH340C supply current, typ. (CH340DS1); confirm
    pd = (20.0 - 3.3) * i_ch340
    rep.add("PASS" if pd <= 0.8 * 0.25 else "FAIL", "LDO", f"U306 HT7533-1 at VBUS 20 V: {pd*1000:.0f} mW vs 250 mW rating (80 % = 200 mW)")
    return rep


def selftest(tracks, vias, pads, vals, zones):
    base = {r[2] for r in check(tracks, vias, pads, vals, zones).fails()}
    st = Report("selftest: injected faults")
    narrow = [(t[0], t[1], t[2], 0.25 if t[0] == "+BATT" else t[3], t[4], t[5]) for t in tracks]
    one_via = [v for v in vias if v[0] != "+5V_BUCK"] + [("+5V_BUCK", 100.0, 100.0, 0.3)]
    w = dict(vals); w["R332"] = "8k2 1%"
    for name, args in (("+BATT necked to 0.25 mm", (narrow, vias, pads, vals, zones)),
                       ("single via on +5V_BUCK", (tracks, one_via, pads, vals, zones)),
                       ("buck divider -> 6.0 V", (tracks, vias, pads, w, zones))):
        new = {r[2] for r in check(*args).fails()} - base
        st.add("PASS" if new else "FAIL", "inject", f"{name}: {len(new)} new FAIL")
    return st


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args or not os.path.exists(args[0]):
        print(__doc__); sys.exit(2)
    data = load(args[0])
    r = check(*data); r.show("-q" in sys.argv)
    code = 1 if r.fails() else 0
    if "--selftest" in sys.argv:
        st = selftest(*data); st.show()
        if st.fails():
            code = 3
    sys.exit(code)
