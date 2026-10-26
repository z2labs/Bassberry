"""Layer 2: plug the Raspberry Pi in, face down - mechanics and the electrical stack.

Layer 1 asks "does the board match its own specification". This layer asks the question that bites on the bench:

    I push a Pi 4 / Pi 5 face down onto the socket. Which Pi pin lands on which pad, does the board around it
    let it sit, and does every Pi signal end up where the spec says?

How it works
  1. The Pi is placed from its mechanical drawing [RPI-MECH], not from our footprint: the four Pi mounting holes are
     found on the board (H6/H7 + the socket footprint's holes) and the Pi frame is fitted to them, mirrored
     (face down). Pin n of the Pi header is then at a known board position (pin 1 = square pad, inner row, end away
     from the ports).
  2. Each Pi pin is joined to whatever pad is physically under it, regardless of the pad's number. The electrical
     checks of layer 1 that involve the Pi are re-run on that geometric join (a mirrored or rotated socket
     footprint shows up here even if its pad numbers look right).
  3. Mechanics: port block over the open corner, SoC lids inside the thermal pad, antenna inside the keep-out,
     nothing on the top side under the Pi except its socket.

usage: kicad-python twin_plug.py board.kicad_pcb [--selftest]       exit 0 / 1 FAIL / 2 input / 3 selftest
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from twin_common import Board, Report
import spec_bassberry as S
import twin_check as T

# [RPI-MECH] Pi frame: x along the 85 mm side (ports at x = 85), y across 56 mm (header edge at y = 56)
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
HDR_CX, HDR_CY, PITCH = 32.5, 52.5, 2.54          # header centre: 29 mm from the hole, 3.5 mm from the edge


def pi_pin(n):
    """pin n in the Pi frame: pin 1 square pad, inner row (y < header centre), end away from the ports"""
    col = (n - 1) // 2
    x = HDR_CX - 9.5 * PITCH + col * PITCH
    y = HDR_CY - PITCH / 2 if n % 2 == 1 else HDR_CY + PITCH / 2
    return x, y


PORT_BLOCK = (66.0, 0.0, 88.0, 56.0)   # Pi 4/5 RJ45 + USB bodies: drawing ~66.8 mm (Pi 4), 66.9 mm (Pi 5) to the 3 mm overhang
SOCS = {"Pi 4 SoC": ((29.25, 32.5), 15.0), "Pi 5 SoC": ((33.1, 23.0), 17.0)}
ANT = (0.0, 35.0, 8.0, 56.0)                      # antenna corner (pin-1 end, header side)


def fits(holes_board, tol=0.2):
    """all rigid transforms Pi -> board putting the 4 Pi holes on 4 board holes.
    Board coordinates are y-down, the drawing is y-up: a FACE-DOWN Pi is a proper rotation in raw numbers
    (det +1), a face-up Pi is a reflection (det -1). Only face-down fits are returned (the spec)."""
    import itertools
    out = []
    for four in itertools.combinations(holes_board, 4):
        for perm in itertools.permutations(four, 4):
            cs = (sum(p[0] for p in PI_HOLES) / 4, sum(p[1] for p in PI_HOLES) / 4)
            cd = (sum(p[0] for p in perm) / 4, sum(p[1] for p in perm) / 4)
            sxx = sxy = 0.0
            for (a, b), (c, d) in zip(PI_HOLES, perm):
                a, b, c, d = a - cs[0], b - cs[1], c - cd[0], d - cd[1]
                sxx += a * c + b * d; sxy += a * d - b * c
            th = math.atan2(sxy, sxx); co, si = math.cos(th), math.sin(th)

            def f(x, y, co=co, si=si, cs=cs, cd=cd):
                x, y = x - cs[0], y - cs[1]
                return cd[0] + co * x - si * y, cd[1] + si * x + co * y
            err = max(math.hypot(f(*h)[0] - p[0], f(*h)[1] - p[1]) for h, p in zip(PI_HOLES, perm))
            if err < tol:
                out.append((err, f))
    return out


def board_geometry(path):
    import pcbnew
    from board_geom import OX, OY
    b = pcbnew.LoadBoard(path)
    mm = lambda v: pcbnew.ToMM(v)
    P = lambda p: (mm(p.x) - OX, mm(p.y) - OY)
    holes, pads, top_parts, zones = [], {}, [], {}
    for fp in b.GetFootprints():
        r = fp.GetReference()
        for p in fp.Pads():
            d = mm(p.GetDrillSize().x)
            if 2.4 < d < 3.0 and (r == "J101" or r.startswith("H")):
                holes.append(P(p.GetPosition()))
            if r == "J101" and p.GetNumber():
                pads[p.GetNumber()] = (P(p.GetPosition()), p.GetNetname())
        if not fp.IsFlipped() and r != "J101" and not r.startswith("H"):
            bb = fp.GetBoundingBox(False)
            top_parts.append((r, (mm(bb.GetX()) - OX, mm(bb.GetY()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY)))
    for z in b.Zones():
        o = z.Outline().BBox()
        zones[z.GetZoneName()] = (mm(o.GetX()) - OX, mm(o.GetY()) - OY, mm(o.GetRight()) - OX, mm(o.GetBottom()) - OY)
    outline = b.GetBoardEdgesBoundingBox()
    edge = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(edge, True)
    def on_board(x, y):
        return edge.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(x + OX), pcbnew.FromMM(y + OY)))
    return holes, pads, top_parts, zones, on_board


def check(path, pads_override=None):
    rep = Report("layer 2: Pi 4/5 plugged in face down")
    holes, pads, top_parts, zones, on_board = board_geometry(path)
    # unique hole positions
    uniq = []
    for h in holes:
        if all(math.hypot(h[0] - u[0], h[1] - u[1]) > 0.5 for u in uniq):
            uniq.append(h)
    cands = fits(uniq)
    if not cands:
        rep.add("FAIL", "holes", "Pi 58 x 49 mm hole pattern (face down) not found on the board")
        return rep, None

    def ports_on_board(F):
        return sum(on_board(*F(PORT_BLOCK[0] + i, PORT_BLOCK[1] + j)) for i in range(0, 26, 2) for j in range(0, 57, 4))
    err, F = min(cands, key=lambda c: (ports_on_board(c[1]), c[0]))
    rep.add("PASS", "holes", f"Pi hole pattern found, face down (max error {err:.3f} mm); orientation chosen by the enclosure: ports over the open corner")
    # ---- pin by pin: what pad is physically under Pi pin n
    pmap = {}
    for n in range(1, 41):
        x, y = F(*pi_pin(n))
        near = min(pads.items(), key=lambda kv: math.hypot(kv[1][0][0] - x, kv[1][0][1] - y))
        d = math.hypot(near[1][0][0] - x, near[1][0][1] - y)
        if d > 0.15:
            rep.add("FAIL", "pin", f"Pi pin {n}: no socket pad within 0.15 mm (nearest {near[0]} at {d:.2f} mm)")
        pmap[n] = near[0]
    wrong = [(n, p) for n, p in pmap.items() if str(n) != p]
    rep.add("PASS" if not wrong else "FAIL", "pin", "every Pi pin lands on the socket pad with its own number" +
            ("" if not wrong else f"  MISMATCH {wrong[:8]}"))
    # ---- mechanics
    pts = [(PORT_BLOCK[0] + i * 1.0, PORT_BLOCK[1] + j * 1.0) for i in range(int(PORT_BLOCK[2] - PORT_BLOCK[0]) + 1)
           for j in range(int(PORT_BLOCK[3] - PORT_BLOCK[1]) + 1)]
    hit = [F(*p) for p in pts if on_board(*F(*p))]
    rep.add("PASS" if not hit else "FAIL", "ports", "USB/Ethernet block hangs over the open corner (no board under it)" +
            ("" if not hit else f"  {len(hit)} sample points on the board, e.g. {tuple(round(v, 1) for v in hit[0])}"))
    th = [z for k, z in zones.items() if k.startswith("PI_THERMAL_PAD")]
    for name, ((cx, cy), s) in SOCS.items():
        corners = [F(cx + dx * s / 2, cy + dy * s / 2) for dx in (-1, 1) for dy in (-1, 1)]
        ok = bool(th) and all(th[0][0] <= x <= th[0][2] and th[0][1] <= y <= th[0][3] for x, y in corners)
        rep.add("PASS" if ok else "FAIL", "thermal", f"{name} lid ({s:g} mm) inside the exposed thermal pad")
    ko = zones.get("PI_ANTENNA_KEEPOUT")
    ac = [F(ANT[0], ANT[1]), F(ANT[2], ANT[3])]
    ab = (min(p[0] for p in ac), min(p[1] for p in ac), max(p[0] for p in ac), max(p[1] for p in ac))
    if ko:
        inter = (max(ab[0], ko[0]), max(ab[1], ko[1]), min(ab[2], ko[2]), min(ab[3], ko[3]))
        area = max(0, inter[2] - inter[0]) * max(0, inter[3] - inter[1]); full = (ab[2] - ab[0]) * (ab[3] - ab[1])
        cov = area / full if full else 0
        rep.add("PASS" if cov > 0.6 else "WARN", "antenna", f"antenna corner covered by the copper keep-out: {cov*100:.0f} % (on-board part)")
    else:
        rep.add("FAIL", "antenna", "no PI_ANTENNA_KEEPOUT rule area")
    shadow = [F(0, 0), F(85, 56)]
    sb = (min(p[0] for p in shadow), min(p[1] for p in shadow), max(p[0] for p in shadow), max(p[1] for p in shadow))
    under = [r for r, bb in top_parts if bb[0] < sb[2] - 0.5 and bb[2] > sb[0] + 0.5 and bb[1] < sb[3] - 0.5 and bb[3] > sb[1] + 0.5]
    rep.add("PASS" if not under else "FAIL", "shadow", "no top-side part under the Pi (only its socket)" + (f"  {under}" if under else ""))
    return rep, pmap


def electrical(path, pmap):
    """layer-1 assertions that touch J101, with each Pi pin joined to the pad physically under it"""
    rep = Report("layer 2b: Pi signals through the geometric join")
    B = Board(path)
    pads = dict(B.pads)
    phys = {("J101", str(n)): B.pads.get(("J101", p), "") for n, p in pmap.items()}
    pads.update(phys)
    def touches(a):
        items = []
        for x in a[1:]:
            if isinstance(x, list):
                items += x
            elif isinstance(x, tuple):
                items.append(x)
        return any(isinstance(i, tuple) and len(i) == 2 and i[0] == "J101" for i in items)
    sub = [a for a in S.A if touches(a)]
    saved = S.A
    try:
        S.A = sub
        r = T.check(pads, B.val)
    finally:
        S.A = saved
    for row in r.rows:
        if row[1] not in ("physical", "deviation"):
            rep.add(*row)
    return rep


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args or not os.path.exists(args[0]):
        print(__doc__); sys.exit(2)
    r1, pmap = check(args[0]); r1.show()
    code = 1 if r1.fails() else 0
    if pmap:
        r2 = electrical(args[0], pmap); r2.show("-q" in sys.argv)
        code = 1 if (r1.fails() or r2.fails()) else 0
    if "--selftest" in sys.argv and pmap:
        # a face-up fit must be rejected and a mirrored pin map must break the Pi signals
        st = Report("selftest")
        mirrored = {n: str(n + 1 if n % 2 else n - 1) for n in range(1, 41)}
        bad = electrical(args[0], mirrored)
        st.add("PASS" if bad.fails() else "FAIL", "inject", f"socket rows swapped: {len(bad.fails())} FAIL")
        shifted = {n: str(n + 2) if n <= 38 else str(n) for n in range(1, 41)}
        bad = electrical(args[0], shifted)
        st.add("PASS" if bad.fails() else "FAIL", "inject", f"Pi plugged one pin off: {len(bad.fails())} FAIL")
        st.show()
        if st.fails():
            code = 3
    sys.exit(code)
