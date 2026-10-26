"""Layer 1: fabricated netlist (pad -> net of the .kicad_pcb) vs the source-document spec (spec_bassberry.py).

usage: twin_check.py board.kicad_pcb|netlist.net [--selftest] [-q]
exit 0 clean, 1 FAIL, 2 missing input, 3 selftest failed
"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from twin_common import Board, Netlist, Nodes, Report, parse_value, parse_cap
import spec_bassberry as S

BRIDGED = {"JP201": ("1", "2")}   # [KICAD] SolderJumper_3_Bridged12: copper bridge 1-2


def conductor(ref, val, pp):
    """DC-merged two-terminal parts: 0 Ohm links and bridged solder jumpers (fuses are NOT merged: 'thru' checks them)."""
    out = []
    v = val.split()[0] if val.split() else ""
    if ref.startswith("R") and v in ("0R", "0") and len(pp) == 2:      # 'DNP 0R ...' is not fitted, not merged
        out.append(tuple(pp.values()))
    if ref in BRIDGED:
        a, b = BRIDGED[ref]
        out.append((pp.get(a, ""), pp.get(b, "")))
    return out


def resolver(refs):
    def pads(rp):
        ref, name = rp
        if ref not in refs:
            raise KeyError(f"part {ref} not on board")
        if ref in S.PINTABLES and name in S.PINTABLES[ref]:
            return [S.PINTABLES[ref][name]]
        if ref in S.MULTI and name in S.MULTI[ref]:
            return S.MULTI[ref][name]
        if ref.startswith("D") and name in S.DIODE:
            return [S.DIODE[name]]
        return [name]
    return pads


def check(pads, vals):
    rep = Report("layer 1: netlist vs source-document spec")
    N = Nodes(pads, vals, conductor)
    P = resolver(set(vals))
    gnd = N._f("GND")

    def node(rp):
        if rp[0] == "GND":
            return gnd
        ps = P(rp)
        ns = {N.node((rp[0], p)) for p in ps}
        if len(ns) != 1:
            raise KeyError(f"{rp}: pads {ps} are on different nodes")
        return next(iter(ns))

    def parts_between(x, y, prefix):
        res = []
        for r, pp in N.two_pin():
            if not r.startswith(prefix):
                continue
            (n1, a), (n2, b) = pp
            na = N._f(a) if a else ("NC", (r, n1))
            nb = N._f(b) if b else ("NC", (r, n2))
            if {na, nb} == {x, y} and x != y:
                res.append(r)
        return res

    # resistor graph for signal walks (series resistors > 0 Ohm)
    redges = collections.defaultdict(list)
    for r, pp in N.two_pin():
        if not r.startswith("R"):
            continue
        v = parse_value(vals.get(r, ""))
        (n1, a), (n2, b) = pp
        if v and v > 0 and a and b:
            x, y = N._f(a), N._f(b)
            if x != y:
                redges[x].append((y, r, v)); redges[y].append((x, r, v))

    def walk(a, b, k):
        seen = {a: 0}; q = [a]
        while q:
            x = q.pop(0)
            if x == b:
                return seen[x]
            if seen[x] >= k:
                continue
            for y, r, v in redges[x]:
                if y not in seen and y != gnd and N.refs_on(y) - {r} != set() and len(N.refs_on(y)) <= 12:
                    seen[y] = seen[x] + 1; q.append(y)
        return None

    def rvals(x, y):
        return [(r, parse_value(vals[r])) for r in parts_between(x, y, "R")]

    for a in S.A:
        kind, why = a[0], a[-1]
        try:
            if kind == "same":
                ns = {node(p) for p in a[1]}
                rep.add("PASS" if len(ns) == 1 else "FAIL", "same", f"{why}" + ("" if len(ns) == 1 else f"  -> {len(ns)} different nodes: " + ", ".join(f"{p[0]}.{p[1]}" for p in a[1])))
            elif kind == "diff":
                ns = [node(p) for p in a[1]]
                rep.add("PASS" if len(set(ns)) == len(ns) else "FAIL", "diff", why)
            elif kind == "gnd":
                bad = [p for p in a[1] if node(p) != gnd]
                rep.add("PASS" if not bad else "FAIL", "gnd", why + (f"  NOT GND: {bad}" if bad else ""))
            elif kind == "only":
                n = node(a[1])
                on = N.refs_on(n) if not isinstance(n, tuple) else set()
                allowed = set(a[2]) | {a[1][0]}
                extra, missing = on - allowed, allowed - on
                ok = not extra and not missing
                rep.add("PASS" if ok else "FAIL", "only", why + ("" if ok else f"  extra {sorted(extra)} missing {sorted(missing)}"))
            elif kind == "thru":
                x, y, r = node(a[1]), node(a[3]), a[2]
                pp = N.parts.get(r, {})
                nn = {N._f(v) if v else ("NC", (r, k)) for k, v in pp.items()}
                ok = nn == {x, y} and x != y
                rep.add("PASS" if ok else "FAIL", "thru", f"{why}: {r} between {a[1][0]}.{a[1][1]} and {a[3][0]}.{a[3][1]}")
            elif kind == "walk":
                d = walk(node(a[1]), node(a[2]), a[3])
                rep.add("PASS" if d is not None else "FAIL", "walk", f"{why}" + (f" ({d} series R)" if d else "") + ("" if d is not None else "  NOT REACHED"))
            elif kind == "btn":
                r = a[2]; n1, n2 = N.node((r, "1")), N.node((r, "2"))
                rep.add("PASS" if {n1, n2} == {node(a[1]), gnd} else "FAIL", "button", why)
            elif kind == "pullup":
                rs = rvals(node(a[1]), node(a[2]))
                ok = any(v and abs(v - a[3]) / a[3] < 0.05 for _, v in rs)
                rep.add("PASS" if ok else "FAIL", "pull-up", f"{why}: {rs}")
            elif kind == "pulldown":
                rs = rvals(node(a[1]), gnd)
                ok = any(v and abs(v - a[2]) / a[2] < 0.05 for _, v in rs)
                rep.add("PASS" if ok else "FAIL", "pull-down", f"{why}: {rs}")
            elif kind == "rsense":
                rs = rvals(node(a[1]), node(a[2]))
                ok = any(v and abs(v - a[3]) / a[3] < 0.05 for _, v in rs)
                rep.add("PASS" if ok else "FAIL", "sense", f"{why}: {rs}")
            elif kind == "cap":
                cs = [(r, parse_cap(vals[r])) for r in parts_between(node(a[1]), node(a[2]), "C")]
                ok = any(v and abs(v - a[3]) / a[3] <= a[4] for _, v in cs)
                rep.add("PASS" if ok else "FAIL", "cap", f"{why}: {cs}")
            elif kind == "float":
                n = node(a[1])
                ok = isinstance(n, tuple) or N.refs_on(n) == {a[1][0]}
                rep.add("PASS" if ok else "FAIL", "float", why + ("" if ok else f"  connected to {sorted(N.refs_on(n))}"))
            elif kind == "ratio":
                fb, top = node(a[1]), node(a[2])
                rt, rb = rvals(fb, top), rvals(fb, gnd)
                if not (rt and rb):
                    rep.add("FAIL", "divider", f"{why}: Rtop {rt} Rbot {rb}")
                elif a[3] is None:      # sense divider: 12.6 V full pack must stay below the 3.3 V ADC rail
                    v = 12.6 * rb[0][1] / (rt[0][1] + rb[0][1])
                    rep.add("PASS" if v < 3.0 else "FAIL", "divider", f"{why}: {rt[0][0]}/{rb[0][0]} -> {v:.2f} V at 12.6 V")
                else:
                    vout = a[3] * (rt[0][1] / rb[0][1] + 1)
                    ok = a[4] <= vout <= a[5]
                    rep.add("PASS" if ok else "FAIL", "divider", f"{why}: {rt[0][0]} {rt[0][1]/1e3:g}k / {rb[0][0]} {rb[0][1]/1e3:g}k -> {vout:.3f} V")
        except KeyError as e:
            rep.add("FAIL", kind, f"{why}: {e}")
    for p in S.PHYSICAL:
        rep.add("WARN", "physical", p)
    for p in S.DEVIATIONS:
        rep.add("WARN", "deviation", p)
    return rep


def selftest(pads, vals):
    """inject typical faults; every one must create a new FAIL"""
    base = {r[2] for r in check(pads, vals).fails()}

    def sw(p, *pairs):
        q = dict(p)
        for a, b in pairs:
            q[a], q[b] = p[b], p[a]
        return q

    def mirror_pi(p):
        q = dict(p)
        for n in range(1, 41, 2):
            q[("J101", str(n))], q[("J101", str(n + 1))] = p[("J101", str(n + 1))], p[("J101", str(n))]
        return q

    def setv(ref, v):
        w = dict(vals); w[ref] = v; return w

    T = lambda r, f: (r, S.PINTABLES[r][f])
    faults = {
        "Pi socket mirrored (odd/even rows swapped: the face-down trap)": (mirror_pi(pads), vals),
        "amp 1 SCLK/LRCLK swapped": (sw(pads, (T("U201", "SCLK"), T("U201", "LRCLK"))), vals),
        "ZVD PFET drain/source swapped": (sw(pads, (("Q101", "1"), ("Q101", "5")), (("Q101", "2"), ("Q101", "5"))), vals),
        "HAT EEPROM SDA/SCL swapped": (sw(pads, (T("U101", "SDA"), T("U101", "SCL"))), vals),
        "IP2366 HG1/LG1 swapped": (sw(pads, (T("U302", "HG1"), T("U302", "LG1"))), vals),
        "TPS565208 VIN/SW swapped": (sw(pads, (T("U303", "VIN"), T("U303", "SW"))), vals),
        "MT3608 FB/EN swapped": (sw(pads, (T("U304", "FB"), T("U304", "EN"))), vals),
        "BMS B1/B2 swapped": (sw(pads, (("J401", "2"), ("J401", "3"))), vals),
        "cell 2 holder rotated (polarity)": (sw(pads, (("BT402", "1"), ("BT402", "2"))), vals),
        "USB D+/D- swapped at the CH340": (sw(pads, (T("U502", "UD+"), T("U502", "UD-"))), vals),
        "supervisor I2C SDA/SCL swapped": (sw(pads, (T("U501", "PC1"), T("U501", "PC2"))), vals),
        "both amps on the same I2C address (ADR 15k)": (pads, setv("R221", "15k")),
        "buck divider wrong (10k -> 12k: 4.4 V for the Pi)": (pads, setv("R332", "12k 1%")),
        "BAT_NUM resistor 9.1k (4 cells)": (pads, setv("R311", "9k1 1%")),
    }
    q = dict(pads); q[("U202", "23")] = "NEW_NET_X"; faults["amp 2 PBTL tie OUT_A+/OUT_A- missing"] = (q, vals)
    q = dict(pads); q[("R106", "2")] = pads[("J101", "27")]; faults["something else on ID_SD (HAT violation)"] = (q, vals)
    rep = Report("selftest: injected faults")
    ok = True
    for name, (p, v) in faults.items():
        new = {r[2] for r in check(p, v).fails()} - base
        rep.add("PASS" if new else "FAIL", "inject", f"{name}: {len(new)} new FAIL" + (f"  e.g. {sorted(new)[0][:90]}" if new else "  NOT DETECTED"))
        ok &= bool(new)
    return rep, ok


def load(path):
    return Netlist(path) if path.endswith(".net") else Board(path)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args or not os.path.exists(args[0]):
        print(__doc__); sys.exit(2)
    B = load(args[0])
    r1 = check(B.pads, B.val); r1.show("-q" in sys.argv)
    code = 1 if r1.fails() else 0
    if "--selftest" in sys.argv:
        r3, ok = selftest(B.pads, B.val); r3.show()
        if not ok:
            code = 3
    sys.exit(code)
