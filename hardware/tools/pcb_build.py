"""Build the Bassberry motherboard skeleton with KiCad's pcbnew API.

   kicad-cli sch export netlist --format kicadsexpr -o bassberry.net bassberry.kicad_sch
   "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/pcb_build.py

Board: 180 x 110 mm, 4 layers (F.Cu signal/power, In1 GND, In2 GND, B.Cu signal/power).
Coordinates below: x to the right, y from the REAR edge (y=0, USB-C/Pi ports) to the FRONT edge (y=110, OLED/UI).
Top side (F): Pi socket (face-down Pi), 3S cell clips, UI. Bottom side (B): amps, charger, regulators.
"""
import os, sys, re, math
sys.path.insert(0, os.path.dirname(__file__))
import pcbnew
from sexpr import parse, find, find1

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.join(HERE, "..", "bassberry")
FPDIR = os.environ.get("KICAD_FP", r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
OX, OY = 50.0, 50.0  # board origin on the sheet
W, H = 180.0, 110.0


def mm(v):
    return pcbnew.FromMM(v)


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


board = pcbnew.BOARD()
board.SetCopperLayerCount(4)
ds = board.GetDesignSettings()
ds.SetBoardThickness(mm(1.6))

# ------------------------------------------------------------ outline with Pi port notch (rear-left)
NOTCH = (5.0, 61.0, 21.0)  # x0, x1, depth from rear edge
pts = [(0, 0), (NOTCH[0], 0), (NOTCH[0], NOTCH[2]), (NOTCH[1], NOTCH[2]), (NOTCH[1], 0), (W, 0), (W, H), (0, H)]
for i in range(len(pts)):
    a, b = pts[i], pts[(i + 1) % len(pts)]
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
pinnet = {}
netobjs = {}
for n in find(find1(net, "nets"), "net"):
    name = find1(n, "name")[1]
    ni = pcbnew.NETINFO_ITEM(board, name)
    board.Add(ni)
    netobjs[name] = ni
    for node in find(n, "node"):
        pinnet[(find1(node, "ref")[1], find1(node, "pin")[1])] = ni


def short(name):
    return name.split("/")[-1]


# ------------------------------------------------------------ placement plan
# (x, y, rot, side) for mechanically fixed parts; everything else is grid-placed by sheet below.
FIXED = {
    # Raspberry Pi face-down socket: header along the left edge, matching the 3D model
    "J101": (8.5, 58.0, 90, "F"),
    # 3S cells (clips), cells run front-to-back
    "BT401": (81.0, 18.0, 0, "F"), "BT402": (81.0, 82.0, 0, "F"),
    "BT403": (100.0, 82.0, 0, "F"), "BT404": (100.0, 18.0, 0, "F"),
    "BT405": (119.0, 18.0, 0, "F"), "BT406": (119.0, 82.0, 0, "F"),
    # rear edge: USB-C (power sheet J1)
    "J301": (150.0, 3.5, 180, "F"),
    # front strip UI
    "SW501": (20.0, 100.0, 0, "F"), "SW502": (32.0, 100.0, 0, "F"), "SW503": (44.0, 100.0, 0, "F"),
    "SW504": (56.0, 100.0, 0, "F"), "SW505": (68.0, 100.0, 0, "F"),
    "SW506": (160.0, 98.0, 0, "F"),
    "J502": (90.0, 104.0, 0, "F"),
    # speaker connectors (bottom, towards the acoustic chambers)
    "J201": (12.0, 102.0, 0, "B"), "J202": (168.0, 102.0, 0, "B"), "J203": (90.0, 70.0, 0, "B"),
    # BMS module pads + NTC + fuse near the cells (bottom)
    "J401": (100.0, 95.0, 90, "B"), "J402": (130.0, 92.0, 0, "B"), "F401": (140.0, 85.0, 0, "B"),
}
REGIONS = {  # sheet -> (x0, y0, x1, y1, side) for automatic placement
    "pi": (8.0, 24.0, 66.0, 36.0, "B"),
    "audio": (6.0, 38.0, 72.0, 96.0, "B"),
    "power": (128.0, 9.0, 177.0, 84.0, "B"),
    "battery": (72.0, 98.0, 126.0, 109.0, "B"),
    "ui": (128.0, 86.0, 178.0, 109.0, "B"),
}

# which sheet each ref belongs to: read from the netlist (sheetpath)
sheet_of = {}
for c in find(find1(net, "components"), "comp"):
    ref = find1(c, "ref")[1]
    sp = find1(c, "sheetpath")
    names = find1(sp, "names")[1] if sp else "/"
    low = names.lower()
    key = ("pi" if "raspberry" in low else "audio" if "audio" in low else "power" if "power" in low
           else "battery" if "battery" in low else "ui" if "ui" in low else "root")
    sheet_of[ref] = key

cursor = {k: [v[0], v[1], 0.0] for k, v in REGIONS.items()}


def load_fp(fpid):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FPDIR, lib + ".pretty"), name)
    if fp is None:
        raise RuntimeError("footprint not found: " + fpid)
    return fp


placed = []
for ref, c in sorted(comps.items()):
    if not c["fp"]:
        continue
    fp = load_fp(c["fp"])
    fp.SetReference(ref)
    fp.SetValue(c["value"])
    sh = sheet_of.get(ref, "root")
    key = ref
    for pad in fp.Pads():
        ni = pinnet.get((ref, pad.GetNumber()))
        if ni:
            pad.SetNet(ni)
    board.Add(fp)
    if key in FIXED:
        x, y, rot, side = FIXED[key]
    else:
        x0, y0, x1, y1, side = REGIONS.get(sh, REGIONS["power"])
        cx, cy, rowh = cursor[sh]
        bb = fp.GetBoundingBox(False, False)
        w, h = pcbnew.ToMM(bb.GetWidth()) + 1.0, pcbnew.ToMM(bb.GetHeight()) + 1.0
        if cx + w > x1:
            cx, cy, rowh = x0, cy + rowh, 0.0
        x, y, rot = cx + w / 2, cy + h / 2, 0
        cursor[sh] = [cx + w, cy, max(rowh, h)]
    fp.SetPosition(P(x, y))
    fp.SetOrientationDegrees(rot)
    if side == "B":
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT if hasattr(pcbnew, "FLIP_DIRECTION_LEFT_RIGHT") else False)
    placed.append(ref)

# ------------------------------------------------------------ mounting holes (M3) and Pi pedestal bolts (M2.5)
def hole(x, y, d=3.2, pad=6.0, ref="H"):
    fp = load_fp("MountingHole:MountingHole_3.2mm_M3_Pad_Via" if d > 3 else "MountingHole:MountingHole_2.7mm_M2.5_Pad_Via")
    fp.SetReference(ref)
    fp.SetPosition(P(x, y))
    for p in fp.Pads():
        p.SetNet(netobjs.get("GND"))
    board.Add(fp)


for i, (x, y) in enumerate([(66, 4.5), (175.5, 9), (4.5, 105.5), (175.5, 105.5), (4.5, 26)]):
    hole(x, y, ref=f"H{i+1}")
hole(26.0, 49.0, d=2.7, ref="H6")
hole(44.0, 49.0, d=2.7, ref="H7")

# ------------------------------------------------------------ Pi SoC thermal pad: exposed copper + via field (GND)
gnd = netobjs.get("GND")
PAD = (22.0, 36.0, 48.0, 62.0)
for layer in (pcbnew.F_Cu, pcbnew.F_Mask):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    ol = z.Outline(); ol.NewOutline()
    for (x, y) in [(PAD[0], PAD[1]), (PAD[2], PAD[1]), (PAD[2], PAD[3]), (PAD[0], PAD[3])]:
        ol.Append(mm(OX + x), mm(OY + y))
    if layer == pcbnew.F_Cu:
        z.SetNet(gnd); z.SetZoneName("PI_THERMAL_PAD"); z.SetAssignedPriority(10)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(z)
for ix in range(13):
    for iy in range(13):
        x, y = PAD[0] + 1.0 + ix * 2.0, PAD[1] + 1.0 + iy * 2.0
        if math.hypot(x - 26.0, y - 49.0) < 4 or math.hypot(x - 44.0, y - 49.0) < 4:
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
for (x, y) in [(4.0, 72.0), (22.0, 72.0), (22.0, 88.0), (4.0, 88.0)]:
    ol.Append(mm(OX + x), mm(OY + y))
board.Add(ko)

# ------------------------------------------------------------ GND planes on In1/In2 + B.Cu pour
for layer, prio in ((pcbnew.In1_Cu, 0), (pcbnew.In2_Cu, 0), (pcbnew.B_Cu, 0)):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer); z.SetNet(gnd); z.SetAssignedPriority(prio)
    z.SetZoneName(f"GND_{board.GetLayerName(layer)}")
    ol = z.Outline(); ol.NewOutline()
    for (x, y) in pts:
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(z)

# ------------------------------------------------------------ silk text
t = pcbnew.PCB_TEXT(board)
t.SetText("BASSBERRY 2.1  rev 0.1  Z2Labs  CERN-OHL-S-2.0")
t.SetPosition(P(140.0, 104.0)); t.SetLayer(pcbnew.F_SilkS)
t.SetTextSize(pcbnew.VECTOR2I(mm(1.5), mm(1.5)))
board.Add(t)

filler = pcbnew.ZONE_FILLER(board)
filler.Fill(board.Zones())
out = os.path.join(PRJ, "bassberry.kicad_pcb")
board.Save(out)
print("placed", len(placed), "footprints ->", out)
