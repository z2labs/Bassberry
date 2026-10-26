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
OX, OY = 50.0, 50.0  # board origin on the sheet
W, H = 180.0, 110.0
EDGE = 1.0           # parts keep this far from the board edge
GAP = 0.35           # courtyard-to-courtyard gap


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
NOTCH = (61.0, 21.0)  # open rear-left corner for the Pi USB/Ethernet block
OUTLINE = [(0, NOTCH[1]), (NOTCH[0], NOTCH[1]), (NOTCH[0], 0), (W, 0), (W, H), (0, H)]
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
    comps[ref] = dict(value=find1(c, "value")[1], fp=(find1(c, "footprint") or [None, ""])[1])
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
PI_AREA = (3.0, 19.0, 61.5, 107.0)       # face-down Pi body over the top side: only its socket goes there
THERMAL = (16.0, 48.0, 42.0, 74.0)       # SoC thermal pad + via field (both sides)
ANTENNA = (44.0, 72.0, 61.0, 88.0)       # Pi Wi-Fi/BT antenna: no copper on any layer (verify vs Pi drawing)
BLOCK = {"F": [PI_AREA, ANTENNA], "B": [THERMAL, ANTENNA]}
HOLES = [(66.0, 4.5, 3.2), (175.5, 9.0, 3.2), (4.5, 105.5, 3.2), (175.5, 105.5, 3.2), (135.0, 50.0, 3.2),
         (8.5, 23.5, 2.7), (8.5, 81.5, 2.7), (22.0, 61.0, 2.7), (36.0, 61.0, 2.7)]
for (x, y, d) in HOLES:
    r = (3.0 if d > 3 else 2.5) + 0.3
    for s in "FB":
        BLOCK[s].append((x - r, y - r, x + r, y + r))

# ------------------------------------------------------------ placement plan
# fixed: ref -> (x, y, rot, side). Cells alternate so the series links are short:
#   BT401 '+' rear / '-' front (CELL0 -> BMS B- at the front), BT402 '-' rear, BT403 '+' rear (CELL3 -> fuse -> charger).
FIXED = {
    "J101": (57.5, 52.5, None, "F"),
    "BT401": (74.5, 50.0, 90, "F"), "BT402": (97.0, 50.0, 270, "F"), "BT403": (119.5, 50.0, 90, "F"),
    "J301": (141.0, 3.6, 180, "F"),
    # front UI strip (top), plungers through the lid
    "SW501": (72.0, 104.0, 0, "F"), "SW502": (84.0, 104.0, 0, "F"), "SW503": (96.0, 104.0, 0, "F"),
    "SW504": (108.0, 104.0, 0, "F"), "SW505": (120.0, 104.0, 0, "F"),
    "J502": (143.0, 100.5, 90, "F"), "SW506": (167.0, 97.0, 0, "F"),
    # BMS module wire pads under the front of the cells, fuse at the rear next to cell 3 '+'
    "J401": (96.0, 97.0, 0, "B"), "F401": (128.0, 8.0, 90, "B"), "J402": (136.0, 97.0, 0, "B"),
    # speaker connectors (bottom, cables to the chambers)
    "J201": (52.0, 28.0, 90, "B"), "J202": (172.0, 62.0, 90, "B"), "J203": (150.0, 62.0, 0, "B"),
    # charger power stage (bottom, rear right, next to USB-C): HS/LS pairs either side of L301
    "L301": (163.0, 24.0, 0, "B"),
    "Q301": (150.5, 16.0, 90, "B"), "Q302": (150.5, 27.0, 90, "B"),
    "Q303": (175.5, 16.0, 270, "B"), "Q304": (175.5, 27.0, 270, "B"),
    "R302": (150.5, 7.0, 0, "B"), "R304": (171.0, 6.0, 0, "B"),
    "C314": (151.0, 46.0, 0, "B"), "C317": (174.0, 46.0, 0, "B"),
    "U302": (162.5, 40.0, 0, "B"),
    "Q305": (135.0, 14.0, 90, "B"), "R305": (141.0, 14.0, 90, "B"),
    # Pi 5 V buck + back-power diode next to header pins 2/4 (bottom)
    "U303": (75.0, 80.0, 0, "B"), "L302": (75.0, 90.0, 0, "B"), "Q101": (66.0, 78.5, 90, "B"),
    # sub boost
    "U304": (110.0, 88.0, 0, "B"), "L303": (120.0, 88.0, 0, "B"),
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
    "C350": ("U305", "2"), "C351": ("U305", "3"), "C352": ("U306", "2"), "C353": ("U306", "3"),
    "C501": ("U501", "9"), "C502": ("U501", "9"), "C510": ("U502", "16"),
    "D301": ("J301", "A4"), "R106": ("J101", "11"),
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
    return fp


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
    pbox = None
    for p in fp.Pads():
        pads.setdefault(p.GetNumber(), tomm(p.GetPosition()))
        if p.GetNumber() and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pcbnew.ToMM(p.GetDrillSize().x) > 0.5:
            b = p.GetBoundingBox(); a = tomm(pcbnew.VECTOR2I(b.GetX(), b.GetY()))
            r = (a[0], a[1], a[0] + pcbnew.ToMM(b.GetWidth()), a[1] + pcbnew.ToMM(b.GetHeight()))
            pbox = r if pbox is None else (min(pbox[0], r[0]), min(pbox[1], r[1]), max(pbox[2], r[2]), max(pbox[3], r[3]))
    return box, pads, pbox


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
    box, pads, pbox = fp_geom
    occupied[side].append((box[0] + x, box[1] + y, box[2] + x, box[3] + y)); owner[side].append(ref)
    if tht and pbox:
        o = "B" if side == "F" else "F"
        occupied[o].append((pbox[0] + x - 0.3, pbox[1] + y - 0.3, pbox[2] + x + 0.3, pbox[3] + y + 0.3)); owner[o].append(ref + "(pins)")


fps, where, padpos = {}, {}, {}
for ref, c in sorted(comps.items()):
    if not c["fp"]:
        continue
    fp = load_fp(c["fp"])
    fp.SetReference(ref)
    fp.SetValue(c["value"])
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


# 1) fixed parts. The Pi socket picks its rotation: header vertical, pin 40 to the rear, Pi body to the left.
for ref, (x, y, rot, side) in FIXED.items():
    if ref not in fps:
        print("WARNING: fixed ref not on netlist:", ref); continue
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
REGION = {"raspberry pi (mounted face-down) + hat id": (64, 60, 100, 75), "battery": (100, 80, 128, 95)}
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
            if a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]:
                nover += 1
                print(f"  overlap {s}: {owner[s][i]} x {owner[s][j]}")
print("courtyard overlaps after placement:", nover)

# ------------------------------------------------------------ mounting holes (M3 board, M2.5 Pi, M2.5 pedestal)
def hole(x, y, d, ref):
    fp = load_fp("MountingHole:MountingHole_3.2mm_M3_Pad_Via" if d > 3 else "MountingHole:MountingHole_2.7mm_M2.5_Pad_Via")
    fp.SetReference(ref)
    fp.SetPosition(P(x, y))
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
for ix in range(13):
    for iy in range(13):
        x, y = THERMAL[0] + 1.0 + ix * 2.0, THERMAL[1] + 1.0 + iy * 2.0
        if math.hypot(x - 22.0, y - 61.0) < 4 or math.hypot(x - 36.0, y - 61.0) < 4:
            continue
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(P(x, y)); v.SetDrill(mm(0.3)); v.SetWidth(mm(0.6)); v.SetNet(gnd)
        board.Add(v)

# ------------------------------------------------------------ keep-out under the Pi Wi-Fi/BT antenna (all copper layers)
ko = pcbnew.ZONE(board)
ko.SetIsRuleArea(True)
ko.SetDoNotAllowTracks(True); ko.SetDoNotAllowVias(True); ko.SetDoNotAllowPads(True); ko.SetDoNotAllowZoneFills(True)
ko.SetDoNotAllowFootprints(False)
ls = pcbnew.LSET(); [ls.AddLayer(l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
ko.SetLayerSet(ls)
ko.SetZoneName("PI_ANTENNA_KEEPOUT")
ol = ko.Outline(); ol.NewOutline()
for (x, y) in [(ANTENNA[0], ANTENNA[1]), (ANTENNA[2], ANTENNA[1]), (ANTENNA[2], ANTENNA[3]), (ANTENNA[0], ANTENNA[3])]:
    ol.Append(mm(OX + x), mm(OY + y))
board.Add(ko)

# ------------------------------------------------------------ GND: solid In2 plane, pours on F.Cu and B.Cu
for layer in (pcbnew.In2_Cu, pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer); z.SetNet(gnd); z.SetAssignedPriority(0)
    z.SetZoneName(f"GND_{board.GetLayerName(layer)}")
    z.SetLocalClearance(mm(0.3)); z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.3)); z.SetThermalReliefSpokeWidth(mm(0.5))
    ol = z.Outline(); ol.NewOutline()
    for (x, y) in OUTLINE:
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(z)

# ------------------------------------------------------------ silk text
t = pcbnew.PCB_TEXT(board)
t.SetText("BASSBERRY 2.1  rev 0.2  Z2Labs  CERN-OHL-S-2.0")
t.SetPosition(P(150.0, 60.0)); t.SetLayer(pcbnew.F_SilkS)
t.SetTextSize(pcbnew.VECTOR2I(mm(1.5), mm(1.5)))
board.Add(t)

filler = pcbnew.ZONE_FILLER(board)
filler.Fill(board.Zones())
out = os.path.join(PRJ, "bassberry.kicad_pcb")
board.Save(out)
json.dump({r: list(v) for r, v in where.items()}, open(os.path.join(PRJ, "placement.json"), "w"), indent=0)
print("placed", len(where), "footprints ->", out)
