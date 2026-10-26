"""Layer 3: the drawn copper against the currents and voltages it has to carry.

  * track ampacity (IPC-2221: I = k * dT^0.44 * A^0.725, A in mil^2, k = 0.048 outer / 0.024 inner,
    1 oz outer = 35 um, 0.5 oz inner = 17.5 um (JLC 4-layer 1.6 mm), dT = 20 K)
  * max-flow through the drawn copper of each high-current net between the pads the current really enters and
    leaves (FLOWS), tracks at their IPC ampacity, vias 1.5 A each (0.3 mm drill, 25 um barrel, conservative);
    a short run into a pad that is itself narrower than the run would need counts as a pad-entry neck
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
            bb = p.GetBoundingBox()
            box = (mm(bb.GetX()) - OX, mm(bb.GetY()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY)
            s = p.GetSize(pcbnew.F_Cu)
            layers = {b.GetLayerName(l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)}
            pads.setdefault((fp.GetReference(), p.GetNumber()), []).append(
                (p.GetNetname(), mm(p.GetPosition().x) - OX, mm(p.GetPosition().y) - OY, box, min(mm(s.x), mm(s.y)), layers))
    zones = [(z.GetNetname(), b.GetLayerName(z.GetLayer())) for z in b.Zones() if not z.GetIsRuleArea()]
    return tracks, vias, pads, vals, zones


T = lambda r, *p: [(r, x) for x in p]
FLOWS = [   # (net, source pads, sink pads, A): where the current enters and leaves the copper of that net
    ("/battery/CELL3", T("BT403", "1"), T("F401", "1"), 6.0),
    ("/battery/CELL0", T("BT401", "2"), T("J401", "1"), 6.0),
    ("/battery/CELL1", T("BT401", "1"), T("BT402", "2"), 6.0),
    ("/battery/CELL2", T("BT402", "1"), T("BT403", "2"), 6.0),
    ("+BATT", T("F401", "2"), T("U303", "3"), 2.8),                       # Pi buck input at 9 V, 5.1 V / 5 A
    ("+BATT", T("F401", "2"), T("U201", "15", "16", "27", "28"), 2.5),    # amp 1 PVDD
    ("+BATT", T("F401", "2"), T("JP301", "1"), 2.5),                      # amp 2 PVDD via the select jumper
    ("+BATT", T("R304", "2"), T("F401", "2"), 3.5),                       # charging current into the pack
    ("+5V_BUCK", T("L302", "2"), T("Q101", "5"), 5.0),
    ("+5V", T("Q101", "1", "2", "3"), T("J101", "2", "4"), 5.0),
    ("/power/BUCK_SW", T("U303", "2"), T("L302", "1"), 5.0),
    ("VBUS", T("J301", "A4", "A9", "B4", "B9"), T("R305", "1"), 3.0),
    ("/power/CHG_VIN", T("R305", "2"), T("R302", "1"), 3.0),
    ("/power/CHG_NODEB", T("R302", "2"), T("Q301", "5"), 3.0),
    ("/power/CHG_LX1", T("Q301", "1", "2", "3"), T("L301", "1"), 3.5),
    ("/power/CHG_LX2", T("L301", "2"), T("Q303", "1", "2", "3"), 3.5),
    ("/power/CHG_NODEC", T("Q303", "5"), T("R304", "1"), 3.5),
    ("PVDD_SUB", T("JP301", "2"), T("U202", "15", "16", "27", "28"), 2.5),
    ("/audio/AMP2_P", T("U202", "26", "23"), T("L205", "1"), 3.0),
    ("/audio/AMP2_N", T("U202", "17", "20"), T("L206", "1"), 3.0),
    ("/audio/SUB_P", T("L205", "2"), T("J203", "1"), 3.0), ("/audio/SUB_N", T("L206", "2"), T("J203", "2"), 3.0),
    ("/audio/AMP1_AP", T("U201", "26"), T("L201", "1"), 2.0), ("/audio/AMP1_AN", T("U201", "23"), T("L202", "1"), 2.0),
    ("/audio/AMP1_BP", T("U201", "17"), T("L203", "1"), 2.0), ("/audio/AMP1_BN", T("U201", "20"), T("L204", "1"), 2.0),
    ("/audio/SAT_L_P", T("L201", "2"), T("J201", "1"), 2.0), ("/audio/SAT_L_N", T("L202", "2"), T("J201", "2"), 2.0),
    ("/audio/SAT_R_P", T("L203", "2"), T("J202", "1"), 2.0), ("/audio/SAT_R_N", T("L204", "2"), T("J202", "2"), 2.0),
]
NECK = 2.5   # mm: a narrower run this close to a pad that is itself narrower than the run's need is a pad-entry neck


def fmt(ps):
    return ps[0][0] + "." + "/".join(p for _, p in ps)


def maxflow(net, src, dst, amps, tracks, vias, pads):
    """Edmonds-Karp on the copper graph of one net: nodes = track ends / vias / pads, capacities = IPC ampacity."""
    import collections as C
    key = lambda l, x, y: (l, round(x, 2), round(y, 2))
    cap = C.defaultdict(float)
    adj = C.defaultdict(set)

    def edge(a, b, c):
        cap[(a, b)] += c; cap[(b, a)] += c; adj[a].add(b); adj[b].add(a)
    INF = 1e9
    padnodes = {}
    netpads = [(rp, g) for rp, gs in pads.items() for g in gs if g[0] == net]
    small = [(g[3], g[4]) for rp, g in netpads]
    for rp, g in netpads:
        padnodes.setdefault(rp, []).append(("PAD",) + rp)
    ts = [t for t in tracks if t[0] == net]
    for t in ts:
        a, b = key(t[1], *t[4]), key(t[1], *t[5])
        c = ipc_amps(t[3], t[2])
        L = math.hypot(t[5][0] - t[4][0], t[5][1] - t[4][1])
        # pad-entry neck: short run touching a pad narrower than the track would need
        for (box, dmin) in small:
            near = any(box[0] - 0.05 <= p[0] <= box[2] + 0.05 and box[1] - 0.05 <= p[1] <= box[3] + 0.05 for p in (t[4], t[5]))
            if near and L <= NECK and dmin < 1.0:
                c = INF
        edge(a, b, c)
    # vias join all layers at one point
    for v in vias:
        if v[0] != net:
            continue
        hub = ("VIA", round(v[1], 2), round(v[2], 2))
        for t in ts:
            for p in (t[4], t[5]):
                if math.hypot(p[0] - v[1], p[1] - v[2]) < 0.05:
                    edge(hub, key(t[1], *p), VIA_A)
    # pads: every track end inside the pad's copper on one of its layers
    for rp, g in netpads:
        node = ("PAD",) + rp
        for t in ts:
            for p in (t[4], t[5]):
                box = g[3]
                if t[1] in g[5] and box[0] - 0.02 <= p[0] <= box[2] + 0.02 and box[1] - 0.02 <= p[1] <= box[3] + 0.02:
                    edge(node, key(t[1], *p), INF)
    S, Tn = ("SRC",), ("SNK",)
    for rp in src:
        if rp not in padnodes:
            return None, f"source pad {rp} not on this net"
        edge(S, ("PAD",) + rp, INF)
    for rp in dst:
        if rp not in padnodes:
            return None, f"sink pad {rp} not on this net"
        edge(("PAD",) + rp, Tn, INF)
    flow = 0.0
    while True:
        par = {S: None}; q = C.deque([S])
        while q and Tn not in par:
            u = q.popleft()
            for w in adj[u]:
                if w not in par and cap[(u, w)] > 1e-9:
                    par[w] = u; q.append(w)
        if Tn not in par:
            break
        f, w = INF, Tn
        while par[w] is not None:
            f = min(f, cap[(par[w], w)]); w = par[w]
        if f >= INF / 2:
            return INF, "pad to pad"
        w = Tn
        while par[w] is not None:
            cap[(par[w], w)] -= f; cap[(w, par[w])] += f; w = par[w]
        flow += f
        if flow > 100:
            break
    if flow == 0:
        return None, f"{fmt(src)} and {fmt(dst)} not connected by tracks"
    return flow, ""


def check(tracks, vias, pads, vals, zones):
    rep = Report("layer 3: copper vs current, set-points")
    # ---- ampacity: max-flow through the drawn copper between the terminals the current really flows between
    for (net, src, dst, amps) in FLOWS:
        cap, why = maxflow(net, src, dst, amps, tracks, vias, pads)
        if cap is None:
            rep.add("FAIL", "ampacity", f"{net}: {why}")
            continue
        rep.add("PASS" if cap >= amps else "FAIL", "ampacity",
                f"{net} {fmt(src)} -> {fmt(dst)}: needs {amps:g} A, copper carries {cap:.1f} A ({DT:g} K rise, vias 1.5 A each)")
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
    narrow = [(t[0], t[1], t[2], 0.25 if t[0] == "/battery/CELL3" else t[3], t[4], t[5]) for t in tracks]
    keep = {}
    one_via = []
    for v in vias:                      # keep only the first via of every +5V/+5V_BUCK layer change
        if v[0] in ("+5V_BUCK", "+5V"):
            k = (v[0], round(v[1] / 3), round(v[2] / 3))
            if k in keep:
                continue
            keep[k] = 1
        one_via.append(v)
    w = dict(vals); w["R332"] = "8k2 1%"
    for name, args in (("CELL3 necked to 0.25 mm", (narrow, vias, pads, vals, zones)),
                       ("parallel vias removed on the Pi 5 V path", (tracks, one_via, pads, vals, zones)),
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
