"""Build the Bassberry motherboard (rev 0.2) with KiCad's pcbnew API: outline, stack-up, functional placement, zones.

   powershell -File hardware\\tools\\regen_sch.ps1          (schematic -> bassberry.net)
   "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/pcb_build.py

Coordinates: x to the right, y from the REAR edge (y=0: USB-C, Pi ports) to the FRONT edge (y=110: buttons, OLED).
Stack-up (srouter rev-B3 layer roles): F.Cu GND pour + top parts, In1.Cu signal/power, In2.Cu solid GND, B.Cu parts + GND pour.
Top (F): face-down Pi on its socket, 3x 18650 holders, USB-C, buttons, encoder, OLED socket.
Bottom (B): every other SMD part (amps, charger, buck, MCU), placed by function next to the pin it serves.

Placement = fixed anchors (mechanics, ICs, power stage) + a deterministic spiral placer for the passives:
each passive goes as close as possible to the pad of its partner (the most specific shared net), courtyard-free.
"""
import os, sys, math, json
sys.path.insert(0, os.path.dirname(__file__))
import pcbnew
from sexpr import parse, find, find1

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.join(HERE, "..", "bassberry")
FPDIR = os.environ.get("KICAD_FP", r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
from board_geom import OX, OY, W, H, NOTCH, OUTLINE, PI_AREA, THERMAL, ANTENNA, HOLES, add_thermal_vias, add_gnd_pours
EDGE = 1.0           # parts keep this far from the board edge
GAP = 0.6            # courtyard-to-courtyard gap (room for a 0.2 mm escape track + 2 x 0.15 mm clearance)


def mm(v):
    return pcbnew.FromMM(v)


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def tomm(p):
    return pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY


board = pcbnew.BOARD()
board.SetCopperLayerCount(4)
ds = board.GetDesignSettings()
ds.SetBoardThickness(mm(1.6))
board.SetLayerName(pcbnew.In1_Cu, "In1.Cu")
board.SetLayerName(pcbnew.In2_Cu, "In2.Cu")
board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_SIGNAL)
board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)

# ------------------------------------------------------------ outline with Pi port notch (rear-left)
for i in range(len(OUTLINE)):
    a, b = OUTLINE[i], OUTLINE[(i + 1) % len(OUTLINE)]
    seg = pcbnew.PCB_SHAPE(board)
    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    seg.SetStart(P(*a)); seg.SetEnd(P(*b))
    seg.SetLayer(pcbnew.Edge_Cuts); seg.SetWidth(mm(0.1))
    board.Add(seg)

# ------------------------------------------------------------ netlist
net = parse(open(os.path.join(PRJ, "bassberry.net"), encoding="utf-8").read())
comps = {}
for c in find(find1(net, "components"), "comp"):
    ref = find1(c, "ref")[1]
    props = {find1(p, "name")[1] for p in find(c, "property") if find1(p, "name")}
    comps[ref] = dict(value=find1(c, "value")[1], fp=(find1(c, "footprint") or [None, ""])[1],
                      dnp="dnp" in props, nobom="exclude_from_bom" in props)
pinnet, netobjs, netpins = {}, {}, {}
for n in find(find1(net, "nets"), "net"):
    name = find1(n, "name")[1]
    ni = pcbnew.NETINFO_ITEM(board, name)
    board.Add(ni)
    netobjs[name] = ni
    for node in find(n, "node"):
        k = (find1(node, "ref")[1], find1(node, "pin")[1])
        pinnet[k] = name
        netpins.setdefault(name, []).append(k)


def short(name):
    return name.split("/")[-1]


RAILS = {"GND", "+3V3", "+5V", "+5V_BUCK", "+BATT", "VBUS", "+3V3_AON", "+3V3_USB", "PVDD_SUB", "CHG_VIN"}

# ------------------------------------------------------------ mechanical keep-outs for placement (x0, y0, x1, y1)
BLOCK = {"F": [PI_AREA, ANTENNA], "B": [THERMAL, ANTENNA]}
for (x, y, d) in HOLES:
    r = (3.0 if d > 3 else 2.5) + 0.3
    for s in "FB":
        BLOCK[s].append((x - r, y - r, x + r, y + r))

# ------------------------------------------------------------ placement plan
# fixed: ref -> (x, y, rot, side). Cells alternate so the series links are short:
#   (Keystone 1042 pad 1 = '+'; rot 270 puts pad 1 at the rear)
#   BT401 '+' rear / '-' front (CELL0 -> BMS B- at the front), BT402 '-' rear, BT403 '+' rear (CELL3 -> fuse -> charger).
FIXED = {
    "J101": (57.5, 52.5, None, "F"),
    "BT401": (74.5, 51.5, 270, "F"), "BT402": (97.0, 51.5, 90, "F"), "BT403": (119.5, 51.5, 270, "F"),
    "J301": (141.0, None, 0, "B"),           # USB-C on the bottom, mouth to the rear edge (y from EDGE_ALIGN)
    # front UI strip (top), plungers through the lid
    "SW501": (72.0, 104.0, 0, "F"), "SW502": (84.0, 104.0, 0, "F"), "SW503": (96.0, 104.0, 0, "F"),
    "SW504": (108.0, 104.0, 0, "F"), "SW505": (120.0, 104.0, 0, "F"),
    "J502": (134.0, 100.5, 90, "F"), "SW506": (147.0, 96.0, 0, "F"),
    # BMS module wire pads under the front of the cells, fuse at the rear next to cell 3 '+'
    "J401": (96.0, 98.0, 0, "B"), "F401": (128.0, 8.0, 90, "B"), "J402": (136.0, 97.0, 0, "B"),
    # speaker connectors (bottom, cables to the chambers)
    "J201": (46.0, 28.0, 90, "B"), "J202": (172.0, 62.0, 90, "B"), "J203": (150.0, 62.0, 0, "B"),
    # charger power stage (bottom, rear right, next to USB-C): HS/LS pairs either side of L301
    "L301": (163.0, 24.0, 0, "B"),
    "Q301": (150.5, 16.0, 90, "B"), "Q302": (150.5, 27.0, 90, "B"),
    "Q303": (175.5, 16.0, 270, "B"), "Q304": (175.5, 27.0, 270, "B"),
    "R302": (150.5, 7.0, 0, "B"), "R304": (168.0, 5.0, 0, "B"),
    "C314": (151.0, 46.0, 0, "B"), "C317": (174.0, 46.0, 0, "B"),
    "U302": (162.5, 40.0, 180, "B"),          # QFN pins 11-20 (gate drive, LX, BST) face the power stage
    "Q305": (135.0, 14.0, 90, "B"), "R305": (141.0, 14.0, 90, "B"),
    # Pi 5 V buck + back-power diode next to header pins 2/4 (bottom)
    "U303": (75.0, 80.0, "face:2:+y", "B"), "L302": (75.0, 88.0, "face:1:-y", "B"), "Q101": (66.0, 78.5, "face:1:-x", "B"),
    # sub boost
    "U304": (100.0, 50.0, 0, "B"), "L303": (100.0, 60.0, 0, "B"),   # next to amp 2
    # amplifiers (bottom, under the cells), output filters towards their connectors
    "U201": (82.0, 30.0, 0, "B"), "U202": (112.0, 30.0, 0, "B"),
    "C234": (82.0, 10.0, 0, "B"), "C244": (112.0, 10.0, 0, "B"),
    # supervisor + console + LDOs
    "U501": (146.0, 84.0, 0, "B"), "U502": (140.0, 30.0, 90, "B"),
    "U305": (156.0, 76.0, 0, "B"), "U306": (134.0, 22.0, 0, "B"),
    "J501": (160.0, 88.0, 90, "B"),
}
# passives whose only non-rail net is a rail: say who they decouple (ref, pad)
PARTNER = {
    "C101": ("Q101", "1"), "C102": ("J101", "2"), "C103": ("J101", "1"), "C104": ("U101", "8"),
    "C211": ("U201", "2"), "C212": ("U201", "2"), "C219": ("U201", "15"), "C231": ("U201", "28"),
    "C232": ("U201", "16"), "C233": ("U201", "27"),
    "C221": ("U202", "2"), "C222": ("U202", "2"), "C229": ("U202", "15"), "C241": ("U202", "28"),
    "C242": ("U202", "16"), "C243": ("U202", "27"),
    "C302": ("U302", "8"), "C304": ("U302", "23"), "C312": ("Q301", "5"), "C313": ("Q301", "5"),
    "C315": ("R304", "2"), "C316": ("R304", "2"),
    "C332": ("U303", "3"), "C333": ("U303", "3"), "C334": ("U303", "3"),
    "C335": ("L302", "2"), "C336": ("L302", "2"), "C337": ("L302", "2"),
    "C340": ("D306", "1"), "C341": ("D306", "1"),
    "C350": ("U305", "2"), "C351": ("U305", "3"), "C352": ("U306", "5"), "C353": ("U306", "1"),
    "C501": ("U501", "9"), "C502": ("U501", "9"), "C510": ("U502", "16"),
    "D301": ("J301", "A4"), "R106": ("J101", "11"),
    "R344": ("U202", "16"), "R345": ("U202", "27"),        # PVDD_SUB select links next to amp 2
    # gate resistors and snubbers at the MOSFETs, so the QFN pins only fan out
    "R306": ("Q301", "4"), "R307": ("Q302", "4"), "R308": ("Q303", "4"), "R309": ("Q304", "4"),
    "R320": ("Q302", "5"), "R321": ("Q304", "5"),
}
SIDE_TOP = set()  # everything not FIXED goes to the bottom (JP101/TP101 too: flashing is a one-off, from below)

# which sheet each ref belongs to
sheet_of = {}
for c in find(find1(net, "components"), "comp"):
    ref = find1(c, "ref")[1]
    sp = find1(c, "sheetpath")
    sheet_of[ref] = (find1(sp, "names")[1] if sp else "/").strip("/").split("/")[-1].lower()


def load_fp(fpid):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
    if fp is None:
        raise RuntimeError("footprint not found: " + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))       # keep the library nickname (DRC schematic parity compares it)
    nums = [p.GetNumber() for p in fp.Pads() if p.GetNumber()]
    if len(nums) != len(set(nums)):
        fp.SetDuplicatePadNumbersAreJumpers(True)   # tact switch / shell pads with one number are joined inside the part
    return fp


def pi_socket_cleanup(fp):
    """The KiCad face-down socket is drawn on a Pi Zero: its courtyard is the whole Zero and it carries the Zero's two
    far mounting holes. Only the 2 x 20 header is ours: the courtyard becomes the header outline + 0.5 mm, and only the
    two holes on the header line stay (shared by every 40-pin Pi; the far pair of the Pi 4/5 are H6/H7)."""
    pins = [p for p in fp.Pads() if p.GetNumber().isdigit() and 1 <= int(p.GetNumber()) <= 40]
    xs = [pcbnew.ToMM(p.GetPosition().x) for p in pins]; ys = [pcbnew.ToMM(p.GetPosition().y) for p in pins]
    long_x = (max(xs) - min(xs)) > (max(ys) - min(ys))
    axis = sum(ys) / len(ys) if long_x else sum(xs) / len(xs)
    for p in list(fp.Pads()):
        if p in pins:
            continue
        c = pcbnew.ToMM(p.GetPosition().y if long_x else p.GetPosition().x)
        if abs(c - axis) > 10:
            fp.Remove(p)
    for g in list(fp.GraphicalItems()):
        if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            fp.Remove(g)
        elif g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS, pcbnew.F_Fab, pcbnew.B_Fab):
            # the Pi Zero outline would be printed on the board under a Pi 4/5: keep only what sits on the header
            bb = g.GetBoundingBox()
            if not (pcbnew.ToMM(bb.GetX()) >= min(xs) - 3 and pcbnew.ToMM(bb.GetRight()) <= max(xs) + 3 and
                    pcbnew.ToMM(bb.GetY()) >= min(ys) - 3 and pcbnew.ToMM(bb.GetBottom()) <= max(ys) + 3):
                fp.Remove(g)
    r = pcbnew.PCB_SHAPE(fp); r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(pcbnew.VECTOR2I(mm(min(xs) - 1.27 - 0.5), mm(min(ys) - 1.27 - 0.5)))
    r.SetEnd(pcbnew.VECTOR2I(mm(max(xs) + 1.27 + 0.5), mm(max(ys) + 1.27 + 0.5)))
    r.SetLayer(pcbnew.F_CrtYd); r.SetWidth(mm(0.05)); fp.Add(r)


def is_tht(fp):
    return any(p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) for p in fp.Pads())


def geom(fp, rot, side):
    """bbox (relative to position) and pad offsets for a rotation/side, measured on the real footprint."""
    if fp.IsFlipped() != (side == "B"):
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(P(0, 0))
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
    x0, y0 = tomm(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
    box = (x0, y0, x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight()))
    pads = {}
    holes = []        # every drilled hole (PTH pins, NPTH pegs) blocks the other side too
    for p in fp.Pads():
        pads.setdefault(p.GetNumber(), tomm(p.GetPosition()))
        drilled = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) and pcbnew.ToMM(p.GetDrillSize().x) > 0.5
        if drilled:
            b = p.GetBoundingBox(); a = tomm(pcbnew.VECTOR2I(b.GetX(), b.GetY()))
            holes.append((a[0], a[1], a[0] + pcbnew.ToMM(b.GetWidth()), a[1] + pcbnew.ToMM(b.GetHeight())))
    return box, pads, holes


occupied = {"F": [], "B": []}
owner = {"F": [], "B": []}


def free(rect, side):
    x0, y0, x1, y1 = rect
    if x0 < EDGE or y0 < EDGE or x1 > W - EDGE or y1 > H - EDGE:
        return False
    if x0 < NOTCH[0] + EDGE and y0 < NOTCH[1] + EDGE:  # inside the open rear-left corner
        return False
    for (a, b, c, d) in occupied[side] + BLOCK[side]:
        if x0 < c + GAP and x1 > a - GAP and y0 < d + GAP and y1 > b - GAP:
            return False
    return True


def occupy(fp_geom, x, y, side, tht, ref=""):
    box, pads, holes = fp_geom
    occupied[side].append((box[0] + x, box[1] + y, box[2] + x, box[3] + y)); owner[side].append(ref)
    o = "B" if side == "F" else "F"
    for h in holes:
        occupied[o].append((h[0] + x - 0.3, h[1] + y - 0.3, h[2] + x + 0.3, h[3] + y + 0.3)); owner[o].append(ref + "(hole)")


fps, where, padpos = {}, {}, {}
for ref, c in sorted(comps.items()):
    if not c["fp"]:
        continue
    fp = load_fp(c["fp"])
    fp.SetReference(ref)
    fp.SetValue(c["value"])
    fp.SetDNP(c["dnp"])                     # board attributes follow the schematic (DRC parity)
    fp.SetExcludedFromBOM(c["nobom"])       # (library jumpers / test points carry their own flag)
    if ref == "J101":
        pi_socket_cleanup(fp)
    for pad in fp.Pads():
        n = pinnet.get((ref, pad.GetNumber()))
        if n:
            pad.SetNet(netobjs[n])
    board.Add(fp)
    fps[ref] = fp


def put(ref, x, y, rot, side):
    fp = fps[ref]
    g = geom(fp, rot, side)
    fp.SetPosition(P(x, y))
    where[ref] = (x, y, rot, side)
    occupy(g, x, y, side, is_tht(fp), ref)
    for n, (px, py) in g[1].items():
        padpos[(ref, n)] = (px + x, py + y)


def place_near(ref, tgt, side, rots):
    """spiral search from tgt for a courtyard-free spot; returns True if placed"""
    fp = fps[ref]
    geoms = {r: geom(fp, r, side) for r in rots}
    for ring in range(0, 160):
        rad = ring * 0.5
        k = 1 if ring == 0 else max(8, int(2 * math.pi * rad / 0.5))
        for i in range(k):
            cx = round((tgt[0] + rad * math.cos(2 * math.pi * i / k)) * 4) / 4
            cy = round((tgt[1] + rad * math.sin(2 * math.pi * i / k)) * 4) / 4
            for r, g in geoms.items():
                bx = g[0]
                if free((bx[0] + cx, bx[1] + cy, bx[2] + cx, bx[3] + cy), side):
                    put(ref, cx, cy, r, side)
                    if rad > 0:
                        print(f"  {ref}: moved {rad:.1f} mm from its anchor to stay courtyard-free")
                    return True
    return False


# mechanically fixed (enclosure, Pi, cells, lid controls): exactly where FIXED says. Everything else in FIXED is an
# anchor: the part goes to the nearest courtyard-free spot around it (holder pegs, holes and neighbours respected).
EDGE_ALIGN = {"J301": -0.6}   # courtyard front this far over the rear edge (receptacle lip), pads stay inside
HARD = {"J101", "BT401", "BT402", "BT403", "J301", "SW501", "SW502", "SW503", "SW504", "SW505", "J502", "SW506", "J401"}

# 1) fixed parts. The Pi socket picks its rotation: header vertical, pin 40 to the rear, Pi body to the left.
for ref, (x, y, rot, side) in sorted(FIXED.items(), key=lambda kv: kv[0] not in HARD):
    if ref not in fps:
        print("WARNING: fixed ref not on netlist:", ref); continue
    if isinstance(rot, str) and rot.startswith("face"):
        # turn the part so the named pin points the given way (the buck SW pin toward its inductor and back)
        pin, d = rot.split(":")[1], rot.split(":")[2]
        want = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}[d]
        rot = max((0, 90, 180, 270), key=lambda r: (lambda g: g[1][pin][0] * want[0] + g[1][pin][1] * want[1])(geom(fps[ref], r, side)))
        print(f"  {ref}: rotation {rot} (pin {pin} toward {d})")
    if ref not in HARD:
        if not place_near(ref, (x, y), side, (rot,)):
            print("WARNING: no room for anchored", ref)
        continue
    if ref in EDGE_ALIGN:
        g0 = geom(fps[ref], rot, side)
        y = EDGE_ALIGN[ref] - g0[0][1]
        print(f"  {ref}: y = {y:.2f} mm (courtyard front at {EDGE_ALIGN[ref]} mm)")
    if rot is None:
        fp = fps[ref]; best = None
        for r in (0, 90, 180, 270):
            fp.SetOrientationDegrees(r); fp.SetPosition(P(0, 0))
            pads = {pd.GetNumber(): tomm(pd.GetPosition()) for pd in fp.Pads()}
            p1, p40 = pads["1"], pads["40"]
            vertical = abs(p1[0] - p40[0]) < abs(p1[1] - p40[1])
            score = vertical * 4 + (p40[1] < p1[1]) * 2 + (pads["2"][0] > p1[0])
            if best is None or score > best[0]:
                best = (score, r, (p1[0] + p40[0]) / 2, (p1[1] + p40[1]) / 2)
        put(ref, x - best[2], y - best[3], best[1], side)
        # the socket itself: only the header strip blocks the top
        occupied["F"][-1] = (x - 4.5, y - 26.5, x + 2.0, y + 26.5)
        print("Pi socket rotation", best[1], "score", best[0])
    else:
        put(ref, x, y, rot, side)


# fine-pitch ICs get a fan-out ring: no other part within this margin of their courtyard (the 0.4 mm-pitch QFN
# needs room for 30 escapes; srouter cannot shove)
CLEAR_AROUND = {"U302": 2.0}
for ref, m in CLEAR_AROUND.items():
    if ref in where:
        i = owner[where[ref][3]].index(ref)
        bx = occupied[where[ref][3]][i]
        BLOCK[where[ref][3]].append((bx[0] - m, bx[1] - m, bx[2] + m, bx[3] + m))

# 2) everything else: spiral search next to its partner pad
def partner_target(ref):
    if ref in PARTNER:
        pr, pn = PARTNER[ref]
        if (pr, pn) in padpos:
            return padpos[(pr, pn)], [n for (r, n2), n in pinnet.items() if r == ref and n not in ("GND",)][:1]
        return None, []
    nets = sorted({n for (r, _), n in pinnet.items() if r == ref and n not in RAILS},
                  key=lambda n: len(netpins.get(n, [])))
    for n in nets:
        pts = [padpos[k] for k in netpins[n] if k[0] != ref and k in padpos]
        if pts:
            # pad of the biggest placed part on the most specific net (the IC it belongs to)
            ks = [k for k in netpins[n] if k[0] != ref and k in padpos]
            k = max(ks, key=lambda k: (len(fps[k[0]].Pads()) if k[0] in fps else 0, k))
            return padpos[k], [n]
    return None, []


def side_for(ref):
    if ref in SIDE_TOP:
        return "F"
    return "B"


todo = [r for r in sorted(fps) if r not in where]
for _round in range(6):
    left = []
    for ref in todo:
        tgt, nets = partner_target(ref)
        if tgt is None:
            left.append(ref); continue
        fp, side = fps[ref], side_for(ref)
        geoms = {r: geom(fp, r, side) for r in (0, 90, 180, 270)}
        # the IC whose pin is the target: a part goes on the outward side of that pin (TI/Injoinic layouts: the
        # inductor and caps sit off the pin end, never across the package, where the copper would have to squeeze
        # between the other pins)
        own = next((r for (r, n), xy in padpos.items() if xy == tgt and r != ref), None)
        outward = None
        if own and len(fps[own].Pads()) >= 6:
            ox_, oy_ = where[own][0], where[own][1]
            outward = (tgt[0] - ox_, tgt[1] - oy_)
        best = None
        for ring in range(0, 120):
            rad = ring * 0.5
            cands = []
            if ring == 0:
                cands = [(tgt[0], tgt[1])]
            else:
                k = max(8, int(2 * math.pi * rad / 0.5))
                cands = [(tgt[0] + rad * math.cos(2 * math.pi * i / k), tgt[1] + rad * math.sin(2 * math.pi * i / k)) for i in range(k)]
            for (cx, cy) in cands:
                cx, cy = round(cx * 4) / 4, round(cy * 4) / 4
                for r, g in geoms.items():
                    box = g[0]
                    if not free((box[0] + cx, box[1] + cy, box[2] + cx, box[3] + cy), side):
                        continue
                    # cost: distance from the partner to the pad on the shared net (orients caps correctly)
                    mine = [g[1][pn] for (rr, pn), n in pinnet.items() if rr == ref and (n in nets or not nets) and pn in g[1]]
                    d = min((math.hypot(px + cx - tgt[0], py + cy - tgt[1]) for px, py in mine), default=rad)
                    if outward and (cx - tgt[0]) * outward[0] + (cy - tgt[1]) * outward[1] < 0:
                        d += 2.0
                    if best is None or d < best[0]:
                        best = (d, cx, cy, r)
            if best is not None and ring > 2 and rad > best[0] + 1.5:
                break
        if best is None:
            print("WARNING: no room for", ref); left.append(ref); continue
        put(ref, best[1], best[2], best[3], side)
    if not left or left == todo:
        todo = left
        break
    todo = left

# 3) leftovers (no partner placed): sheet regions
REGION = {}
for ref in todo:
    print("NOTE: free placement for", ref)
    fp, side = fps[ref], side_for(ref)
    g = geom(fp, 0, side)
    done = False
    for yy in [y * 0.5 for y in range(4, 216)]:
        for xx in [x * 0.5 for x in range(130, 356)]:
            b = g[0]
            if free((b[0] + xx, b[1] + yy, b[2] + xx, b[3] + yy), side):
                put(ref, xx, yy, 0, side); done = True; break
        if done:
            break

# overlap report (fixed parts are not checked while placing)
nover = 0
for s in "FB":
    rs = occupied[s]
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            a, b = rs[i], rs[j]
            if owner[s][i].split("(")[0] == owner[s][j].split("(")[0]:
                continue
            if a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]:
                nover += 1
                print(f"  overlap {s}: {owner[s][i]} x {owner[s][j]}")
print("courtyard overlaps after placement:", nover)

# ------------------------------------------------------------ USB-C D+/D- crossover (pre-routed, as USAGE.md asks for
# critical pairs). Receptacle row order: B6(D+) A7(D-) A6(D+) B7(D-): the D- pads are bridged behind the row on the
# pad layer, the middle D+ pad drops through a 0.45/0.2 mm via right behind it; srouter does the rest.
def usb_crossover():
    if ("J301", "A6") not in padpos:
        return
    lay = pcbnew.B_Cu if where["J301"][3] == "B" else pcbnew.F_Cu
    a6, a7, b7 = padpos[("J301", "A6")], padpos[("J301", "A7")], padpos[("J301", "B7")]
    sgn = 1 if a6[1] > where["J301"][1] else -1           # into the board
    half = 1.45 / 2
    def trk(p1, p2, net, w=0.2):
        t = pcbnew.PCB_TRACK(board); t.SetStart(P(*p1)); t.SetEnd(P(*p2)); t.SetWidth(mm(w)); t.SetLayer(lay)
        t.SetNet(netobjs[net]); board.Add(t)
    yb = a7[1] + sgn * (half + 0.9)
    trk(a7, (a7[0], yb), "USB_DN"); trk(b7, (b7[0], yb), "USB_DN"); trk((a7[0], yb), (b7[0], yb), "USB_DN")
    yv = a6[1] + sgn * (half + 0.3)
    trk(a6, (a6[0], yv), "USB_DP")
    v = pcbnew.PCB_VIA(board); v.SetPosition(P(a6[0], yv)); v.SetWidth(mm(0.45)); v.SetDrill(mm(0.2))
    v.SetNet(netobjs["USB_DP"]); board.Add(v)
    print("USB-C crossover pre-routed")


usb_crossover()


# ------------------------------------------------------------ GND pins tied to the exposed pad (TI / Injoinic layouts):
# a short stub from every GND pin straight to the IC's own GND exposed pad, so no GND pin depends on the pour finding it
def gnd_ties(refs):
    import fatten
    fatten.CLR = 0.15; fatten.CLR_PAD = 0.15
    cu = fatten.Copper(board)
    n = 0
    for ref in refs:
        if ref not in where:
            continue
        fp = fps[ref]
        lay = pcbnew.B_Cu if where[ref][3] == "B" else pcbnew.F_Cu
        pads = [p for p in fp.Pads() if p.GetNetname() == "GND"]
        if not pads:
            continue
        ep = max(pads, key=lambda p: p.GetBoundingBox().GetWidth() * p.GetBoundingBox().GetHeight())
        eb = ep.GetBoundingBox()
        for p in pads:
            if p is ep or p.GetBoundingBox().Intersects(eb):
                continue
            q = p.GetPosition()
            # nearest point of the EP box
            tx = min(max(q.x, eb.GetX()), eb.GetRight()); ty = min(max(q.y, eb.GetY()), eb.GetBottom())
            if abs(pcbnew.ToMM(tx - q.x)) > 1.6 or abs(pcbnew.ToMM(ty - q.y)) > 1.6:
                continue       # far from the pad: leave it to the pour
            ps = p.GetSize(pcbnew.F_Cu); hw = min(0.125, pcbnew.ToMM(min(ps.x, ps.y)) / 2 - 0.025)   # a bit narrower than the pin
            a = (pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)); e = (pcbnew.ToMM(tx), pcbnew.ToMM(ty))
            if abs(e[0] - a[0]) < 0.05 or abs(e[1] - a[1]) < 0.05:
                path = [a, e]                              # pin faces the pad: straight in
            else:
                # pin beyond the pad's end (row-end GND pins of the HTSSOP): along its own axis to the pad's edge
                # line, then along that edge to the pad corner - never diagonal across the neighbouring pins
                bbp = p.GetBoundingBox(); along_x = bbp.GetWidth() > bbp.GetHeight()
                path = [a, (e[0], a[1]) if along_x else (a[0], e[1]), e]
            if not all(cu.clear("GND", lay, path[i], path[i + 1], hw) for i in range(len(path) - 1)):
                continue       # would pass a foreign pad closer than the 0.15 mm clearance
            for i in range(len(path) - 1):
                t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I(mm(path[i][0]), mm(path[i][1])))
                t.SetEnd(pcbnew.VECTOR2I(mm(path[i + 1][0]), mm(path[i + 1][1]))); t.SetWidth(mm(2 * hw))
                t.SetLayer(lay); t.SetNet(netobjs["GND"]); board.Add(t)
                cu.add("GND", {lay}, ("seg", path[i], path[i + 1], hw), t)
            n += 1
    print(f"GND pins tied to their exposed pad: {n}")


gnd_ties(["U201", "U202", "U302"])


# ------------------------------------------------------------ GND dog-bones (USAGE.md: fan-out vias may be placed before
# routing). Every SMD GND pad gets its own 0.6/0.3 mm via to the In2 plane right next to it, so no GND pad depends on a
# pour finding a way in between the routed tracks later. The via keeps 0.5 mm from foreign pads (their escape lane).
def gnd_dogbones(clr_pad=0.5, gaps=(0.35, 0.6, 0.9), only=None, vd=0.6, vh=0.3):
    import fatten
    fatten.CLR = 0.2; fatten.CLR_PAD = clr_pad
    cu = fatten.Copper(board)
    vias_xy = [(pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y)) for v in board.GetTracks() if v.GetClass() == "PCB_VIA"]
    made, skipped = 0, []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith("H") or ref in ("J101",):
            continue
        lay = pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
        gpads = [p for p in fp.Pads() if p.GetNetname() == "GND" and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
        if not gpads:
            continue
        big = max(fp.Pads(), key=lambda p: p.GetBoundingBox().GetWidth() * p.GetBoundingBox().GetHeight())
        cx, cy = pcbnew.ToMM(fp.GetPosition().x), pcbnew.ToMM(fp.GetPosition().y)
        for p in gpads:
            if p is big and fp.GetPadCount() > 8:
                continue                       # IC exposed pads have their own thermal vias
            if only is not None and f"{ref}.{p.GetNumber()}" not in only:
                continue
            if any(t.GetNetname() == "GND" and t.GetClass() != "PCB_VIA" and
                   (t.GetStart() == p.GetPosition()) for t in board.GetTracks()):
                continue                       # already has a dog-bone / tie
            q = (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
            bb = p.GetBoundingBox(); hw, hh = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
            # prefer pointing away from the part body
            out = (q[0] - cx, q[1] - cy)
            dirs = sorted([(1, 0), (-1, 0), (0, 1), (0, -1), (0.707, 0.707), (-0.707, 0.707), (0.707, -0.707), (-0.707, -0.707)],
                          key=lambda d: -(d[0] * out[0] + d[1] * out[1]))
            done = False
            for gap in gaps:
                for d in dirs:
                    r = (abs(d[0]) * hw + abs(d[1]) * hh) + gap + vd / 2
                    v = (q[0] + d[0] * r, q[1] + d[1] * r)
                    if any(math.hypot(v[0] - a, v[1] - b_) < vd / 2 + 0.3 + 0.3 for a, b_ in vias_xy):
                        continue
                    if not all(cu.clear("GND", l, v, v, vd / 2) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.B_Cu)):
                        continue
                    if not cu.clear("GND", lay, q, v, min(0.15, hw - 0.025, hh - 0.025)):
                        continue
                    ox, oy = OX, OY
                    t = pcbnew.PCB_TRACK(board); t.SetStart(p.GetPosition()); t.SetEnd(pcbnew.VECTOR2I(mm(v[0]), mm(v[1])))
                    t.SetWidth(mm(2 * min(0.15, hw - 0.025, hh - 0.025))); t.SetLayer(lay); t.SetNet(netobjs["GND"]); board.Add(t)
                    via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I(mm(v[0]), mm(v[1])))
                    via.SetWidth(mm(vd)); via.SetDrill(mm(vh)); via.SetNet(netobjs["GND"]); board.Add(via)
                    cu.add("GND", {lay}, ("seg", q, v, 0.15), t); cu.add("GND", "all", ("circ", v, vd / 2), via)
                    vias_xy.append(v); made += 1; done = True
                    break
                if done:
                    break
            if not done:
                skipped.append(f"{ref}.{p.GetNumber()}")
    print(f"GND dog-bones: {made}, no room: {' '.join(skipped) if skipped else 'none'}")
    return skipped

def gnd_links(only):
    """last resort for a GND pin with no room for its own via: a short straight or L-shaped track to the nearest GND
    copper on its layer (another part's GND pad, a dog-bone via, an exposed pad) within 6 mm, clearance-checked"""
    import fatten
    fatten.CLR = 0.15; fatten.CLR_PAD = 0.5          # 0.5 mm escape lane round every foreign pad: a link never walls one in
    cu = fatten.Copper(board)
    targets = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND":
                targets.append((fp.GetReference(), p, (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))))
    gv = [(pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y)) for v in board.GetTracks()
          if v.GetClass() == "PCB_VIA" and v.GetNetname() == "GND"]
    done, fail = [], []
    for fp in board.GetFootprints():
        lay = pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
        for p in fp.Pads():
            key = f"{fp.GetReference()}.{p.GetNumber()}"
            if key not in only:
                continue
            q = (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
            s = p.GetSize(pcbnew.F_Cu); hw = min(0.125, pcbnew.ToMM(min(s.x, s.y)) / 2 - 0.025)
            cands = [(t[2], t[1]) for t in targets if t[0] != fp.GetReference() and t[1].IsOnLayer(lay)] + [(v, None) for v in gv]
            cands = sorted((c for c in cands if math.dist(c[0], q) < 6.0), key=lambda c: math.dist(c[0], q))
            ok = False
            for (e, _) in cands:
                for path in ([q, e], [q, (e[0], q[1]), e], [q, (q[0], e[1]), e]):
                    if all(cu.clear("GND", lay, path[i], path[i + 1], hw) for i in range(len(path) - 1)):
                        for i in range(len(path) - 1):
                            if math.dist(path[i], path[i + 1]) < 1e-3:
                                continue
                            t = pcbnew.PCB_TRACK(board); t.SetStart(pcbnew.VECTOR2I(mm(path[i][0]), mm(path[i][1])))
                            t.SetEnd(pcbnew.VECTOR2I(mm(path[i + 1][0]), mm(path[i + 1][1]))); t.SetWidth(mm(2 * hw))
                            t.SetLayer(lay); t.SetNet(netobjs["GND"]); board.Add(t)
                            cu.add("GND", {lay}, ("seg", path[i], path[i + 1], hw), t)
                        ok = True
                        break
                if ok:
                    break
            (done if ok else fail).append(key)
    print(f"GND links: {' '.join(done) or 'none'}; still alone (pour / stitching): {' '.join(fail) or 'none'}")


# ------------------------------------------------------------ mounting holes (M3 board, M2.5 Pi, M2.5 pedestal)
def hole(x, y, d, ref):
    # M3 board screws: plated ring to GND (no via ring: it collides with neighbouring holes and the edge);
    # M2.5 Pi / pedestal holes: plain NPTH, the Pi has its own GND through the header
    fp = load_fp("MountingHole:MountingHole_3.2mm_M3_Pad" if d > 3 else "MountingHole:MountingHole_2.7mm_M2.5")
    fp.SetReference(ref)
    fp.SetPosition(P(x, y))
    fp.SetBoardOnly(True)             # mechanical: not in the schematic (DRC schematic parity)
    for p in fp.Pads():
        p.SetNet(netobjs.get("GND"))
    board.Add(fp)


for i, (x, y, d) in enumerate(HOLES):
    hole(x, y, d, f"H{i+1}")

# ------------------------------------------------------------ Pi SoC thermal pad: exposed copper + via field (GND)
gnd = netobjs.get("GND")
for layer in (pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.B_Cu, pcbnew.B_Mask):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    ol = z.Outline(); ol.NewOutline()
    for (x, y) in [(THERMAL[0], THERMAL[1]), (THERMAL[2], THERMAL[1]), (THERMAL[2], THERMAL[3]), (THERMAL[0], THERMAL[3])]:
        ol.Append(mm(OX + x), mm(OY + y))
    if layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z.SetNet(gnd); z.SetZoneName("PI_THERMAL_PAD_" + ("F" if layer == pcbnew.F_Cu else "B")); z.SetAssignedPriority(10)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    board.Add(z)
add_thermal_vias(board, pcbnew)
left = gnd_dogbones()              # after the holes and the SoC via field exist, so it sees them
if left:                           # second chance for the tight ones: farther out, 0.3 mm escape lane
    left = gnd_dogbones(clr_pad=0.3, gaps=(0.35, 0.6, 0.9, 1.2, 1.6), only=set(left))
def has_gnd_ep(ref):
    fp = fps.get(ref)
    return fp is not None and any(p.GetNetname() == "GND" and pcbnew.ToMM(p.GetBoundingBox().GetWidth()) > 2.0 and
                                  pcbnew.ToMM(p.GetBoundingBox().GetHeight()) > 2.0 for p in fp.Pads())


if left:                           # third: a 0.45/0.2 mm via (JLC minimum) tucked in, e.g. between the pin rows - only
    # for parts without a GND exposed pad (an EP part's GND pins reach the pour through the EP; a via squeezed in at
    # the end of an amp pin row costs the bootstrap / output escapes their room)
    left = gnd_dogbones(clr_pad=0.15, gaps=(0.1, 0.2, 0.35, 0.6), only={k for k in left if not has_gnd_ep(k.split(".")[0])},
                        vd=0.45, vh=0.2) + [k for k in left if has_gnd_ep(k.split(".")[0])]
if left:
    gnd_links(set(left))

# ------------------------------------------------------------ keep-out under the Pi Wi-Fi/BT antenna (all copper layers)
ko = pcbnew.ZONE(board)
ko.SetIsRuleArea(True)
ko.SetDoNotAllowTracks(True); ko.SetDoNotAllowVias(True); ko.SetDoNotAllowPads(False); ko.SetDoNotAllowZoneFills(True)
ko.SetDoNotAllowFootprints(False)
ls = pcbnew.LSET(); [ls.AddLayer(l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
ko.SetLayerSet(ls)
ko.SetZoneName("PI_ANTENNA_KEEPOUT")
ol = ko.Outline(); ol.NewOutline()
for (x, y) in [(ANTENNA[0], ANTENNA[1]), (ANTENNA[2], ANTENNA[1]), (ANTENNA[2], ANTENNA[3]), (ANTENNA[0], ANTENNA[3])]:
    ol.Append(mm(OX + x), mm(OY + y))
board.Add(ko)

# ------------------------------------------------------------ GND: solid In2 plane, pours on F.Cu and B.Cu
add_gnd_pours(board, pcbnew)

# ------------------------------------------------------------ silk text
for txt, yy, sz in (("BASSBERRY 2.1  rev 0.2", 70.0, 1.5), ("Z2Labs - CERN-OHL-S-2.0", 73.0, 1.0)):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt); t.SetPosition(P(156.0, yy)); t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(mm(sz), mm(sz))); t.SetTextThickness(mm(0.15 if sz < 1.2 else 0.2))
    board.Add(t)

filler = pcbnew.ZONE_FILLER(board)
filler.Fill(board.Zones())
out = os.path.join(PRJ, "bassberry.kicad_pcb")
board.Save(out)
import shutil
# netclass: 0.15 mm clearance (the IP2366 QFN40 0.4 mm pitch leaves 0.15 mm between its own pads), 0.2 mm track,
# 0.6/0.3 mm via (JLC 4-layer standard). Written into the project file, which the DSN export reads.
pro = os.path.join(PRJ, "bassberry.kicad_pro")
pj = json.load(open(pro, encoding="utf-8"))
for c in pj["net_settings"]["classes"]:
    if c["name"] == "Default":
        c.update(clearance=0.15, track_width=0.2, via_diameter=0.6, via_drill=0.3)
pj["board"]["design_settings"]["rules"]["min_through_hole_diameter"] = 0.2   # 0.45/0.2 mm via at the USB-C row (JLC ok)
pj["board"]["design_settings"]["rules"]["min_via_diameter"] = 0.45
pj["board"]["design_settings"]["rules"]["min_via_annular_width"] = 0.075     # JLC 4-layer: 0.25/0.15 mm vias allowed
pj["board"]["design_settings"]["rules"]["min_copper_edge_clearance"] = 0.3   # JLC: 0.3 mm copper to routed edge
json.dump(pj, open(pro, "w", encoding="utf-8"), indent=2)
shutil.copy(out, os.path.join(PRJ, "bassberry_placed.kicad_pcb"))   # route.py always starts from this
json.dump({r: list(v) for r, v in where.items()}, open(os.path.join(PRJ, "placement.json"), "w"), indent=0)
print("placed", len(where), "footprints ->", out)
