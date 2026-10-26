"""Board geometry shared by pcb_build.py (placement), route.py (post-route repair) and the twin (mechanics).

Board frame: x to the right, y from the REAR edge (y=0) to the FRONT edge (y=110), mm. Sheet origin (OX, OY).
Face-down Pi, mapped from the Raspberry Pi 4 / Pi 5 mechanical drawings (Pi frame: x along the 85 mm side towards the
USB/Ethernet ports, y across the 56 mm side towards the 40-pin header):

    board x = pi_y + 5,   board y = 85 - pi_x        (a mirror: the Pi is seen from its back side)
"""
import math

OX, OY = 50.0, 50.0
W, H = 180.0, 110.0
NOTCH = (61.0, 21.0)  # open rear-left corner: the Pi's USB/Ethernet block hangs past the board here
OUTLINE = [(0, NOTCH[1]), (NOTCH[0], NOTCH[1]), (NOTCH[0], 0), (W, 0), (W, H), (0, H)]


def pi_to_board(px, py):
    return py + 5.0, 85.0 - px


PI_AREA = (4.0, 19.0, 62.0, 86.5)       # Pi 85 x 56 mm body over the top side: only its socket goes there
# SoC centres: Pi 4 (29.25, 32.5) -> (37.5, 55.75), 15 mm lid; Pi 5 (33.1, 23.0) -> (28.0, 51.9), 17 mm lid. Pad = union + 1 mm.
SOC = {"Pi 4": ((29.25, 32.5), 15.0), "Pi 5": ((33.1, 23.0), 17.0)}
THERMAL = (18.5, 42.5, 46.0, 64.5)       # SoC thermal pad + via field (both sides)
# Pi 4/5 Wi-Fi/BT antenna at the pin-1 corner (pi_x 0..8, pi_y 35..56): no copper on any layer, starts past header pin 1.
ANTENNA = (40.0, 78.5, 61.5, 92.0)
# (x, y, drill): M3 board mounts, M2.5 Pi holes not in the socket footprint, M2.5 pedestal bolts (from below)
HOLES = [(66.0, 4.0, 3.2), (175.5, 9.0, 3.2), (4.5, 105.5, 3.2), (175.5, 105.5, 3.2), (135.0, 50.0, 3.2),
         (8.5, 23.5, 2.7), (8.5, 81.5, 2.7), (21.5, 62.0, 2.7), (43.0, 45.0, 2.7)]


def thermal_vias():
    """GND via field under the SoC pad, 2 mm pitch, clear of the bolt holes."""
    pts = []
    for ix in range(int((THERMAL[2] - THERMAL[0] - 1.0) / 2.0) + 1):
        for iy in range(int((THERMAL[3] - THERMAL[1] - 1.0) / 2.0) + 1):
            x, y = THERMAL[0] + 1.0 + ix * 2.0, THERMAL[1] + 1.0 + iy * 2.0
            if any(math.hypot(x - hx, y - hy) < 4 for (hx, hy, d) in HOLES):
                continue
            pts.append((x, y))
    return pts


def add_thermal_vias(board, pcbnew):
    gnd = board.FindNet("GND")
    have = {(round(pcbnew.ToMM(v.GetPosition().x) - OX, 2), round(pcbnew.ToMM(v.GetPosition().y) - OY, 2))
            for v in board.GetTracks() if v.GetClass() == "PCB_VIA"}
    n = 0
    for (x, y) in thermal_vias():
        if (round(x, 2), round(y, 2)) in have:
            continue
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y)))
        v.SetDrill(pcbnew.FromMM(0.3)); v.SetWidth(pcbnew.FromMM(0.6)); v.SetNet(gnd)
        board.Add(v); n += 1
    return n


def add_gnd_pours(board, pcbnew):
    """Solid GND on In2, GND pours on F.Cu and B.Cu (all priority 0, thermal reliefs, islands removed)."""
    gnd = board.FindNet("GND")
    for layer in (pcbnew.In2_Cu, pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer); z.SetNet(gnd); z.SetAssignedPriority(0)
        z.SetZoneName(f"GND_{board.GetLayerName(layer)}")
        z.SetLocalClearance(pcbnew.FromMM(0.3)); z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(pcbnew.FromMM(0.3)); z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.5))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ol = z.Outline(); ol.NewOutline()
        for (x, y) in OUTLINE:
            ol.Append(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))
        board.Add(z)
