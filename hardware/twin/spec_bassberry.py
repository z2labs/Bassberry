"""Bassberry digital twin - SPECIFICATION written from source documents, never from our own schematic or board.
Every table carries its source. Refdes are ours (identifiers only); pin numbers and connectivity come from the sources.
The PDFs live in hardware/_datasheets (not in git: copyright); URLs below.

Sources
  [RPI-SCH]   Raspberry Pi 4 Model B reduced schematics, J8 (40-pin header): pin -> GPIO / power / ID_SD / ID_SC,
              (SDA1)(SCL1)(TXD0)(RXD0) labels.  https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-reduced-schematics.pdf
  [BCM2711]   BCM2711 ARM Peripherals, 5.3 alternative function table: GPIO18 PCM_CLK, GPIO19 PCM_FS, GPIO21 PCM_DOUT (ALT0).
              https://datasheets.raspberrypi.com/bcm2711/bcm2711-peripherals.pdf
  [RPI-MECH]  Raspberry Pi 4 / Pi 5 mechanical drawings (85 x 56 mm, holes 58 x 49 at 3.5 mm, header centre 29 mm from
              the hole, Pi 4 SoC 25.75 / 32.5 mm, Pi 5 drawing: pin 1 = square pad, inner row, end away from the ports).
  [HAT-DG]    raspberrypi/hats designguide.md + eeprom-circuit.png + zvd-circuit.png: ID_SD/ID_SC only to a 24Cxx EEPROM
              (CAT24C32: 1 A0, 2 A1, 3 A2, 4 VSS, 5 SDA, 6 SCL, 7 WP, 8 VCC) with 3.9 k pull-ups; WP 1 k pull-up, jumper to GND;
              back-powering safety diode: PFET + matched dual PNP, 10 k (diode-connected side) and 47 k (gate) to GND.
  [DS-TAS]    TI TAS5805M SLASEH5D, Table 5-1 pin functions, Table 7-5 ADR (4.7k/15k/47k/120k to DVDD -> 0x2C..0x2F),
              Fig. "MONO (PBTL) Systems" (OUT_A+ = OUT_A-, OUT_B+ = OUT_B- before the filter, BST 0.22 uF to the tied node,
              AVDD 1 uF, VR_DIG 1 uF, DVDD 4.7 uF + 0.1 uF, LC 10 uH + 0.68 uF), Table 8-5 values.
  [DS-IP2366] Injoinic IP2366 V1.10, 6.1 pin table, fig. 9 application circuit, 11.4 PSET (3.6k = 30 W), 11.5 BAT_NUM
              (6.2k = 3 cells), 11.6 VSET (9.1k = 4.2 V/cell), 11.7 NTC (10k B3380; without NTC a 10 k to GND, never floating).
  [DS-TPS]    TI TPS565208 SLVSE72B, pin functions (1 GND, 2 SW, 3 VIN, 4 VFB, 5 EN, 6 VBST), VFB 753/760/767 mV, VIN 4.5-17 V.
  [DS-MT3608] Aerosemi MT3608, pin description (1 SW, 2 GND, 3 FB, 4 EN, 5 IN, 6 NC), VFB = 0.6 V, SW max 28 V.
  [DS-DMP]    Diodes DMP3013SFV, PowerDI3333-8: pins 1-3 S, 4 G, 5-8 D (bottom view), 17 mOhm @ -4.5 V.
  [DS-DMMT]   Diodes DMMT5401 SOT26 top view: 1 C1, 2 B1, 3 B2, 4 C2, 5 E2, 6 E1.
  [DS-CH32]   WCH CH32V003 datasheet V1.1, Table 2-1 (TSSOP20 column): 1 PD4 .. 20 PD3, 7 VSS, 9 VDD; PC1 SDA, PC2 SCL, PD1 SWIO.
  [DS-CH340]  WCH CH340DS1 V3: CH340C SOP16: 1 GND, 2 TXD, 3 RXD, 4 V3, 5 UD+, 6 UD-, 15 R232, 16 VCC; V3 = VCC for 3.3 V.
  [DS-LC6]    ST USBLC6-2SC6: 1 I/O1, 2 GND, 3 I/O2, 4 I/O2, 5 VBUS, 6 I/O1 (pins 1/6 and 3/4 are the two lines).
  [DS-HT75]   Holtek HT75xx-1 rev 1.50 SOT-89: 1 GND, 2 VIN, 3 VOUT; VIN max 24 V, Pd 250 mW.
  [DS-XC6216] Torex XC6216/XE6216 ETR0321: SOT-89-5 1 VOUT, 2 VSS, 3 CE (B type: active high), 4 NC, 5 VIN; VIN 2-28 V,
              Pd 500 mW (1300 mW PCB mounted), dropout 300 mV at 20 mA.
  [USB-C]     USB Type-C receptacle pin map: VBUS A4/A9/B4/B9, GND A1/A12/B1/B12, CC1 A5, CC2 B5, D+ A6/B6, D- A7/B7.
  [KEY-1042]  Keystone 1042 18650 holder drawing ('+' marked contact = pad 1 in the KiCad footprint silk).
  [KICAD]     KiCad library conventions: diode/LED pad 1 = cathode; SolderJumper "Bridged12" = pads 1-2 shorted by copper.
  [FW]        Bassberry firmware/OS pin map (docs/architecture.md): supervisor CH32V003 PC0 BOOST_EN, PC3..PC7 buttons,
              PD0 PI_POWEROFF, PD2/PD3/PD4 encoder A/B/switch, PD5 PI_IRQ, PD6 PI_SHUTDOWN_REQ, PA1 PI_PWR_EN, PA2 VBAT_SENSE;
              Pi GPIO4 = PDN amp 1, GPIO5 = PDN amp 2, GPIO17 = PI_IRQ, GPIO22 = shutdown request, GPIO27 = power-off ack.
  [BMS]       generic 3S BMS module, wire pads in order B-, B1, B2, B+, P- (module silk; physical check).
"""

# ---------------------------------------------------------------- pin tables (function name -> pad number)
PI_J8 = {  # [RPI-SCH] J8
    "3V3_1": "1", "5V_2": "2", "GPIO2": "3", "5V_4": "4", "GPIO3": "5", "GND_6": "6", "GPIO4": "7", "GPIO14": "8",
    "GND_9": "9", "GPIO15": "10", "GPIO17": "11", "GPIO18": "12", "GPIO27": "13", "GND_14": "14", "GPIO22": "15",
    "GPIO23": "16", "3V3_17": "17", "GPIO24": "18", "GPIO10": "19", "GND_20": "20", "GPIO9": "21", "GPIO25": "22",
    "GPIO11": "23", "GPIO8": "24", "GND_25": "25", "GPIO7": "26", "ID_SD": "27", "ID_SC": "28", "GPIO5": "29",
    "GND_30": "30", "GPIO6": "31", "GPIO12": "32", "GPIO13": "33", "GND_34": "34", "GPIO19": "35", "GPIO16": "36",
    "GPIO26": "37", "GPIO20": "38", "GND_39": "39", "GPIO21": "40",
}
PI_GND = [k for k in PI_J8 if k.startswith("GND_")]
PI_ROLE = {"GPIO2": "SDA1", "GPIO3": "SCL1", "GPIO14": "TXD0", "GPIO15": "RXD0",           # [RPI-SCH] labels
           "GPIO18": "PCM_CLK", "GPIO19": "PCM_FS", "GPIO21": "PCM_DOUT", "GPIO20": "PCM_DIN"}  # [BCM2711] ALT0
TAS = {"DGND1": "1", "DVDD": "2", "ADR": "3", "VR_DIG": "4", "DGND5": "5", "LRCLK": "6", "SCLK": "7", "SDIN": "8",
       "SDOUT": "9", "SDA": "10", "SCL": "11", "PDN": "12", "AVDD": "13", "AGND": "14", "PVDD15": "15", "PVDD16": "16",
       "OUT_B+": "17", "BST_B+": "18", "PGND19": "19", "OUT_B-": "20", "BST_B-": "21", "BST_A-": "22", "OUT_A-": "23",
       "PGND24": "24", "BST_A+": "25", "OUT_A+": "26", "PVDD27": "27", "PVDD28": "28", "PAD": "29"}   # [DS-TAS] Table 5-1
IP = {"TEST2": "1", "TEST3": "2", "TEST4": "3", "TEST5": "4", "VBUS": "5", "VBUSG": "6", "VBUSI": "7", "VIO": "8",
      "CSP1": "9", "CSN1": "10", "PCIN": "11", "HG1": "12", "BST1": "13", "LX1": "14", "LG1": "15", "LG2": "16",
      "LX2": "17", "BST2": "18", "HG2": "19", "PCON": "20", "CSN2": "21", "CSP2": "22", "BAT": "23", "CC_BDO": "24",
      "VCC5V": "25", "AGND": "26", "GPIO4": "27", "VCCIO": "28", "GPIO3": "29", "GPIO2": "30", "GPIO1": "31",
      "GPIO0": "32", "EN": "33", "CC2": "34", "DPC": "35", "DMC": "36", "CC1": "37", "GPIO19": "38", "GPIO20": "39",
      "TEST1": "40", "GND": "41"}                                                       # [DS-IP2366] 6.1
TPS = {"GND": "1", "SW": "2", "VIN": "3", "VFB": "4", "EN": "5", "VBST": "6"}            # [DS-TPS]
MT = {"SW": "1", "GND": "2", "FB": "3", "EN": "4", "IN": "5", "NC": "6"}                 # [DS-MT3608]
DMP = {"S": "1", "S2": "2", "S3": "3", "G": "4", "D": "5"}                               # [DS-DMP]
DMMT = {"C1": "1", "B1": "2", "B2": "3", "C2": "4", "E2": "5", "E1": "6"}                # [DS-DMMT]
NMOS8 = {"S": "1", "S2": "2", "S3": "3", "G": "4", "D": "5"}                             # SO-8FL / TDSON-8 (JEDEC power SO-8)
EEP = {"A0": "1", "A1": "2", "A2": "3", "VSS": "4", "SDA": "5", "SCL": "6", "WP": "7", "VCC": "8"}   # [HAT-DG] eeprom-circuit
CH32 = {"PD4": "1", "PD5": "2", "PD6": "3", "PD7": "4", "PA1": "5", "PA2": "6", "VSS": "7", "PD0": "8", "VDD": "9",
        "PC0": "10", "PC1": "11", "PC2": "12", "PC3": "13", "PC4": "14", "PC5": "15", "PC6": "16", "PC7": "17",
        "PD1": "18", "PD2": "19", "PD3": "20"}                                           # [DS-CH32] Table 2-1 TSSOP20
CH340 = {"GND": "1", "TXD": "2", "RXD": "3", "V3": "4", "UD+": "5", "UD-": "6", "R232": "15", "VCC": "16"}  # [DS-CH340]
LC6 = {"IO1": "1", "GND": "2", "IO2": "3", "IO2b": "4", "VBUS": "5", "IO1b": "6"}        # [DS-LC6]
HT75 = {"GND": "1", "VIN": "2", "VOUT": "3"}                                             # [DS-HT75]
XC6216 = {"VOUT": "1", "VSS": "2", "CE": "3", "NC": "4", "VIN": "5"}                    # [DS-XC6216]
USBC = {"VBUS": ["A4", "A9", "B4", "B9"], "GND": ["A1", "A12", "B1", "B12"], "CC1": ["A5"], "CC2": ["B5"],
        "D+": ["A6", "B6"], "D-": ["A7", "B7"]}                                          # [USB-C]
CELL = {"+": "1", "-": "2"}                                                              # [KEY-1042]
DIODE = {"K": "1", "A": "2"}                                                             # [KICAD]
ENC = {"A": "A", "B": "B", "C": "C", "S1": "S1", "S2": "S2"}                             # Alps EC11E: A, B, common C, switch

PINTABLES = {"J101": PI_J8, "U201": TAS, "U202": TAS, "U302": IP, "U303": TPS, "U304": MT, "Q101": DMP, "Q102": DMMT,
             "Q301": NMOS8, "Q302": NMOS8, "Q303": NMOS8, "Q304": NMOS8, "Q305": NMOS8, "U101": EEP, "U501": CH32,
             "U502": CH340, "U301": LC6, "U305": HT75, "U306": XC6216, "BT401": CELL, "BT402": CELL, "BT403": CELL,
             "SW506": ENC}
MULTI = {"J301": USBC}
DIODES = ("D", )          # refs starting with D use DIODE names

# ---------------------------------------------------------------- design intent (by FUNCTION, not by our net names)
# ("same", [pins])  ("diff", [pins])  ("gnd", [pins])  ("only", pin, {refs})  ("thru", a, ref, b)
# ("walk", a, b, max_series_R)  ("btn", pin, ref)  ("pullup", pin, to_pin, ohms)  ("pulldown", pin, ohms)
# ("cap", a, b, farads, rel_tol)  ("ratio", fb, top, vref, lo, hi)  ("float", pin)  ("rsense", a, b, ohms)
PI = lambda f: ("J101", f)
U1 = lambda f: ("U201", f)
U2 = lambda f: ("U202", f)
IC = lambda f: ("U302", f)
MCU = lambda f: ("U501", f)
GND = "GND"

A = [
    # ================= Raspberry Pi header [RPI-SCH] [HAT-DG]
    ("gnd", [PI(g) for g in PI_GND], "all eight Pi GND pins on GND"),
    ("same", [PI("5V_2"), PI("5V_4"), ("Q101", "S")], "Pi 5 V pins = back-power diode output (PFET source)"),
    ("same", [PI("3V3_1"), PI("3V3_17"), U1("DVDD"), U2("DVDD"), ("U101", "VCC")], "Pi 3V3 feeds amp DVDD + ID EEPROM"),
    ("diff", [PI("5V_2"), PI("3V3_1"), ("U305", "VOUT")], "Pi 5 V, Pi 3V3 and the always-on 3V3 are separate rails"),
    # HAT ID EEPROM
    ("only", PI("ID_SD"), {"U101", "R104"}, "ID_SD: EEPROM SDA + its pull-up only (HAT rule)"),
    ("only", PI("ID_SC"), {"U101", "R105"}, "ID_SC: EEPROM SCL + its pull-up only (HAT rule)"),
    ("same", [PI("ID_SD"), ("U101", "SDA")], "ID_SD -> EEPROM SDA"),
    ("same", [PI("ID_SC"), ("U101", "SCL")], "ID_SC -> EEPROM SCL"),
    ("pullup", PI("ID_SD"), PI("3V3_1"), 3900, "ID_SD 3.9 k pull-up to 3V3"),
    ("pullup", PI("ID_SC"), PI("3V3_1"), 3900, "ID_SC 3.9 k pull-up to 3V3"),
    ("gnd", [("U101", "A0"), ("U101", "A1"), ("U101", "A2"), ("U101", "VSS")], "EEPROM address 0x50 (A0..A2 = 0), VSS"),
    ("pullup", ("U101", "WP"), PI("3V3_1"), 1000, "WP 1 k pull-up = write protected"),
    ("same", [("U101", "WP"), ("JP101", "1"), ("TP101", "1")], "WP to the write-enable jumper and test point"),
    ("gnd", [("JP101", "2")], "write-enable jumper other side to GND"),
    # back-power ideal diode [HAT-DG] zvd-circuit (input = PFET drain side, output = Pi 5 V)
    ("same", [("Q101", "D"), ("Q102", "E1"), ("L302", "2")], "ZVD: PFET drain + diode-connected PNP emitter on the 5.1 V buck output"),
    ("same", [("Q102", "B1"), ("Q102", "C1"), ("Q102", "B2")], "ZVD: Q2A diode-connected, bases common"),
    ("same", [("Q102", "E2"), ("Q101", "S")], "ZVD: sensing PNP emitter on the Pi 5 V side"),
    ("same", [("Q102", "C2"), ("Q101", "G")], "ZVD: sensing PNP collector drives the PFET gate"),
    ("pulldown", ("Q102", "B1"), 10000, "ZVD: 10 k bias to GND"),
    ("pulldown", ("Q101", "G"), 47000, "ZVD: 47 k gate to GND"),
    ("diff", [("Q101", "D"), ("Q101", "S"), ("Q101", "G")], "ZVD PFET pins on three different nodes"),
    # ================= I2S / I2C / control from the Pi [BCM2711] [FW]
    ("walk", PI("GPIO18"), U1("SCLK"), 1, "PCM_CLK -> amp 1 SCLK"), ("walk", PI("GPIO18"), U2("SCLK"), 1, "PCM_CLK -> amp 2 SCLK"),
    ("walk", PI("GPIO19"), U1("LRCLK"), 1, "PCM_FS -> amp 1 LRCLK"), ("walk", PI("GPIO19"), U2("LRCLK"), 1, "PCM_FS -> amp 2 LRCLK"),
    ("walk", PI("GPIO21"), U1("SDIN"), 1, "PCM_DOUT -> amp 1 SDIN"),
    ("walk", PI("GPIO21"), U2("SDIN"), 1, "PCM_DOUT -> amp 2 SDIN (JP201 default 1-2)"),
    ("same", [U1("SDOUT"), ("JP201", "3")], "amp 1 SDOUT on the JP201 alternative input of amp 2"),
    ("diff", [PI("GPIO18"), PI("GPIO19"), PI("GPIO21")], "I2S lines separate"),
    ("float", PI("GPIO20"), "PCM_DIN unused"),
    ("same", [PI("GPIO2"), U1("SDA"), U2("SDA"), MCU("PC1"), ("J502", "4")], "SDA1: amps, supervisor PC1 (I2C SDA), OLED"),
    ("same", [PI("GPIO3"), U1("SCL"), U2("SCL"), MCU("PC2"), ("J502", "3")], "SCL1: amps, supervisor PC2 (I2C SCL), OLED"),
    ("diff", [PI("GPIO2"), PI("GPIO3")], "SDA/SCL separate"),
    ("same", [PI("GPIO4"), U1("PDN")], "GPIO4 -> amp 1 PDN"),
    ("same", [PI("GPIO5"), U2("PDN")], "GPIO5 -> amp 2 PDN (one GPIO per codec for the Linux driver)"),
    ("pulldown", U1("PDN"), 10000, "amp 1 held in shutdown until the driver (deviation from TI 10 k pull-up: accepted)"),
    ("pulldown", U2("PDN"), 10000, "amp 2 held in shutdown until the driver"),
    ("walk", PI("GPIO14"), ("U502", "RXD"), 1, "TXD0 -> USB console RXD"),
    ("walk", PI("GPIO15"), ("U502", "TXD"), 1, "USB console TXD -> RXD0"),
    ("same", [PI("GPIO17"), MCU("PD5")], "PI_IRQ: supervisor PD5 -> GPIO17"),
    ("same", [PI("GPIO22"), MCU("PD6")], "shutdown request: supervisor PD6 -> GPIO22"),
    ("same", [PI("GPIO27"), MCU("PD0")], "power-off ack: GPIO27 -> supervisor PD0"),
    ("float", PI("GPIO6"), "GPIO6 unused (HAT guide: not driven at boot)"),
    ("float", PI("GPIO16"), "GPIO16 unused (HAT guide: not driven at boot)"),
    # ================= amplifiers [DS-TAS]
    *[("gnd", [U(p) for p in ("DGND1", "DGND5", "AGND", "PGND19", "PGND24", "PAD")], f"{r} grounds + PowerPAD")
      for r, U in (("U201", U1), ("U202", U2))],
    ("same", [U1("PVDD15"), U1("PVDD16"), U1("PVDD27"), U1("PVDD28"), ("F401", "2")], "amp 1 PVDD = fused battery"),
    ("same", [U2("PVDD15"), U2("PVDD16"), U2("PVDD27"), U2("PVDD28"), ("F401", "2")], "amp 2 PVDD = battery through the fitted 0R link (default)"),
    ("pullup", U1("ADR"), U1("DVDD"), 15000, "amp 1 ADR 15 k to DVDD -> I2C 0x2D"),
    ("pullup", U2("ADR"), U2("DVDD"), 47000, "amp 2 ADR 47 k to DVDD -> I2C 0x2E"),
    *[("cap", U(a), U(b), 0.22e-6, 0.1, f"{r} {a} bootstrap 0.22 uF") for r, U in (("U201", U1), ("U202", U2))
      for a, b in (("BST_A+", "OUT_A+"), ("BST_A-", "OUT_A-"), ("BST_B+", "OUT_B+"), ("BST_B-", "OUT_B-"))],
    *[("cap", U(a), ("GND", None), 1e-6, 0.1, f"{r} {a} 1 uF") for r, U in (("U201", U1), ("U202", U2)) for a in ("AVDD", "VR_DIG")],
    *[("cap", U("DVDD"), ("GND", None), v, 0.1, f"{r} DVDD {v*1e6:g} uF") for r, U in (("U201", U1), ("U202", U2)) for v in (4.7e-6, 0.1e-6)],
    ("diff", [U1("OUT_A+"), U1("OUT_A-"), U1("OUT_B+"), U1("OUT_B-")], "amp 1 stereo BTL: four separate outputs"),
    ("same", [U2("OUT_A+"), U2("OUT_A-")], "amp 2 PBTL: OUT_A+ = OUT_A- before the filter (TI fig. PBTL)"),
    ("same", [U2("OUT_B+"), U2("OUT_B-")], "amp 2 PBTL: OUT_B+ = OUT_B- before the filter"),
    ("diff", [U2("OUT_A+"), U2("OUT_B+")], "amp 2 PBTL: the two halves separate"),
    *[("thru", U1(o), l, (j, p), f"amp 1 {o} -> 10 uH -> speaker {j}.{p}")
      for o, l, j, p in (("OUT_A+", "L201", "J201", "1"), ("OUT_A-", "L202", "J201", "2"), ("OUT_B+", "L203", "J202", "1"), ("OUT_B-", "L204", "J202", "2"))],
    ("thru", U2("OUT_A+"), "L205", ("J203", "1"), "amp 2 OUT_A -> 10 uH -> sub +"),
    ("thru", U2("OUT_B+"), "L206", ("J203", "2"), "amp 2 OUT_B -> 10 uH -> sub -"),
    *[("cap", (j, p), ("GND", None), 0.68e-6, 0.1, f"filter 0.68 uF at {j}.{p}") for j in ("J201", "J202", "J203") for p in ("1", "2")],
    # ================= charger IP2366 [DS-IP2366] fig. 9
    ("same", [IC("VBUS"), ("J301", "VBUS"), ("Q305", "D")], "VBUS pin to the receptacle and the input switch"),
    ("same", [IC("VBUSG"), ("Q305", "G")], "VBUSG drives the input NMOS gate"),
    ("same", [IC("VBUSI"), IC("VIO"), IC("CSP1"), ("Q305", "S"), ("R302", "1")], "VBUSI = VIO = CSP1 = input node after the switch"),
    ("same", [("J301", "VBUS"), IC("VIO")], "R5 0R bypass across the input switch fitted (fig. 9): VBUS = input node"),
    ("rsense", IC("CSP1"), IC("PCIN"), 0.005, "input sense 5 mOhm CSP1 -> PCIN node"),
    ("thru", IC("PCIN"), "R301", IC("CSN1"), "51 Ohm PCIN node -> CSN1"),
    ("cap", IC("CSN1"), IC("CSP1"), 470e-9, 0.1, "470 nF CSN1-CSP1"),
    ("same", [IC("PCIN"), ("Q301", "D")], "high-side 1 drain on the PCIN node"),
    ("thru", IC("HG1"), "R306", ("Q301", "G"), "HG1 -> 10 Ohm -> Q1 gate"),
    ("thru", IC("LG1"), "R307", ("Q302", "G"), "LG1 -> 2 Ohm -> Q2 gate"),
    ("thru", IC("HG2"), "R308", ("Q303", "G"), "HG2 -> 2 Ohm -> Q3 gate"),
    ("thru", IC("LG2"), "R309", ("Q304", "G"), "LG2 -> 2 Ohm -> Q4 gate"),
    ("same", [IC("LX1"), ("Q301", "S"), ("Q302", "D")], "LX1 = Q1 source = Q2 drain"),
    ("same", [IC("LX2"), ("Q303", "S"), ("Q304", "D")], "LX2 = Q3 source = Q4 drain"),
    ("gnd", [("Q302", "S"), ("Q304", "S"), IC("AGND"), IC("GND")], "low-side sources, AGND, exposed pad"),
    ("thru", IC("LX1"), "L301", IC("LX2"), "22 uH between LX1 and LX2"),
    ("cap", IC("BST1"), IC("LX1"), 0.1e-6, 0.1, "BST1 0.1 uF"), ("cap", IC("BST2"), IC("LX2"), 0.1e-6, 0.1, "BST2 0.1 uF"),
    ("same", [IC("PCON"), ("Q303", "D")], "PCON on the high-side 2 drain node"),
    ("rsense", IC("PCON"), IC("BAT"), 0.005, "battery sense 5 mOhm PCON node -> BAT"),
    ("thru", IC("PCON"), "R303", IC("CSN2"), "10 Ohm PCON node -> CSN2"),
    ("cap", IC("CSN2"), IC("BAT"), 1e-6, 0.1, "1 uF CSN2-BAT"),
    ("same", [IC("BAT"), IC("CSP2"), ("F401", "2")], "BAT = CSP2 = fused pack +"),
    ("cap", IC("VCC5V"), ("GND", None), 2.2e-6, 0.1, "VCC5V 2.2 uF"), ("cap", IC("VCCIO"), ("GND", None), 2.2e-6, 0.1, "VCCIO 2.2 uF"),
    ("pulldown", IC("GPIO4"), 6200, "BAT_NUM 6.2 k = 3 cells in series"),
    ("pulldown", IC("GPIO2"), 9100, "VSET 9.1 k = 4.2 V per cell"),
    ("pulldown", IC("GPIO3"), 3600, "PSET 3.6 k = 30 W"),
    ("same", [IC("GPIO0"), ("J402", "1")], "NTC pin to the cell thermistor connector"),
    ("pulldown", IC("EN"), 10000, "EN 10 k to GND"),
    ("same", [IC("CC1"), ("J301", "CC1")], "CC1"), ("same", [IC("CC2"), ("J301", "CC2")], "CC2"),
    ("diff", [("J301", "CC1"), ("J301", "CC2")], "CC1/CC2 separate"),
    ("float", IC("DPC"), "DPC unused (USB data goes to the console)"), ("float", IC("DMC"), "DMC unused"),
    *[("float", IC(t), f"{t} NC") for t in ("TEST1", "TEST2", "TEST3", "TEST4", "TEST5")],
    # ================= battery pack [KEY-1042] [BMS]
    ("same", [("BT401", "+"), ("BT402", "-"), ("J401", "2")], "cell 1 + = cell 2 - = BMS B1"),
    ("same", [("BT402", "+"), ("BT403", "-"), ("J401", "3")], "cell 2 + = cell 3 - = BMS B2"),
    ("same", [("BT401", "-"), ("J401", "1")], "cell 1 - = BMS B-"),
    ("same", [("BT403", "+"), ("J401", "4"), ("F401", "1")], "cell 3 + = BMS B+ = fuse in"),
    ("gnd", [("J401", "5")], "BMS P- = board GND"),
    *[("same", [(f"D40{i}", "K"), (f"BT40{i}", "+")], f"reverse-cell LED {i}: cathode on the cell + contact") for i in (1, 2, 3)],
    # ================= Pi 5 V buck [DS-TPS]
    ("same", [("U303", "VIN"), ("F401", "2")], "buck VIN = fused battery (9..12.6 V, inside 4.5-17 V)"),
    ("thru", ("U303", "SW"), "L302", ("Q101", "D"), "SW -> 4.7 uH -> 5.1 V node (ZVD input)"),
    ("cap", ("U303", "VBST"), ("U303", "SW"), 0.1e-6, 0.1, "VBST 0.1 uF to SW"),
    ("gnd", [("U303", "GND")], "buck GND"),
    ("ratio", ("U303", "VFB"), ("Q101", "D"), 0.760, 5.0, 5.25, "Vout = 0.760*(1+Rtop/Rbot) for the Pi"),
    ("same", [("U303", "EN"), MCU("PA1")], "buck EN from supervisor PA1"),
    ("pulldown", ("U303", "EN"), 100000, "buck EN default off"),
    # ================= sub boost [DS-MT3608]
    ("same", [("U304", "IN"), ("F401", "2")], "boost IN = fused battery"),
    ("thru", ("U304", "IN"), "L303", ("U304", "SW"), "boost inductor IN -> SW"),
    ("same", [("U304", "SW"), ("D306", "A")], "SW -> Schottky anode"),
    ("ratio", ("U304", "FB"), ("D306", "K"), 0.6, 16.0, 18.5, "Vout = 0.6*(1+Rtop/Rbot), below TAS PVDD max"),
    ("same", [("U304", "EN"), MCU("PC0")], "boost EN from supervisor PC0"),
    ("pulldown", ("U304", "EN"), 100000, "boost EN default off"),
    ("thru", ("D306", "K"), "R345", U2("PVDD15"), "boost output -> unfitted 0R link -> amp 2 PVDD (fit instead of R344)"),
    # ================= LDOs [DS-HT75]
    ("same", [("U305", "VIN"), ("F401", "2")], "always-on LDO from the fused battery"),
    ("same", [("U305", "VOUT"), MCU("VDD")], "always-on 3V3 -> supervisor VDD"),
    ("same", [("U306", "VIN"), ("U306", "CE"), ("J301", "VBUS")], "USB-side LDO from VBUS, CE tied to VIN (XC6216B: active high)"),
    ("same", [("U306", "VOUT"), ("U502", "VCC"), ("U301", "VBUS")], "USB 3V3 -> CH340 VCC + ESD VBUS"),
    ("gnd", [("U305", "GND"), ("U306", "VSS")], "LDO grounds"),
    ("float", ("U306", "NC"), "XC6216 pin 4 NC"),
    # ================= USB console [DS-CH340] [DS-LC6] [USB-C]
    ("same", [("J301", "D+"), ("U502", "UD+")], "D+ (both receptacle rows) -> CH340 UD+"),
    ("same", [("J301", "D-"), ("U502", "UD-")], "D- (both receptacle rows) -> CH340 UD-"),
    ("diff", [("J301", "D+"), ("J301", "D-")], "D+/D- not shorted"),
    ("same", [("U301", "IO1"), ("U301", "IO1b")], "USBLC6 line 1 in/out"), ("same", [("U301", "IO2"), ("U301", "IO2b")], "USBLC6 line 2"),
    ("gnd", [("U301", "GND"), ("U502", "GND"), ("U502", "R232")], "ESD / CH340 grounds, R232 off"),
    ("same", [("U502", "V3"), ("U502", "VCC")], "CH340 V3 = VCC (3.3 V operation)"),
    # ================= supervisor [DS-CH32] [FW]
    ("gnd", [MCU("VSS")], "MCU VSS"),
    *[("btn", MCU(p), ref, f"{ref} on {p}") for p, ref in
      (("PC3", "SW501"), ("PC4", "SW502"), ("PC5", "SW503"), ("PC6", "SW504"), ("PC7", "SW505"))],
    ("same", [MCU("PD2"), ("SW506", "A")], "encoder A -> PD2"), ("same", [MCU("PD3"), ("SW506", "B")], "encoder B -> PD3"),
    ("same", [MCU("PD4"), ("SW506", "S1")], "encoder switch -> PD4"),
    ("gnd", [("SW506", "C"), ("SW506", "S2")], "encoder common + switch return"),
    ("same", [MCU("PD1"), ("J501", "2")], "SWIO header pin 2"),
    ("pullup", MCU("PD7"), MCU("VDD"), 10000, "NRST 10 k pull-up"),
    ("ratio", MCU("PA2"), ("F401", "2"), None, None, None, "VBAT_SENSE divider 100 k / 22 k (12.6 V -> 2.27 V < VDD)"),
]

PHYSICAL = [
    "OLED module pin order must be GND-VCC-SCL-SDA (1.3in SH1106 modules exist with VCC-GND): check the module before plugging",
    "3S BMS module pad order B-, B1, B2, B+, P- must match the module silk",
    "Keystone 1042 polarity: '+' marked contact = pad 1, cells must be inserted per the silk",
    "NTC on J402 must be fitted (IP2366 11.7: NTC pin never floating)",
    "Pi antenna keep-out position: confirm on a real Pi 4 / Pi 5 / Pi 3B+",
    "TDSON MOSFETs: any 30-40 V SO-8FL/TDSON part with the JEDEC pin-out (1-3 S, 4 G, 5-8 D)",
]
# accepted deviations from the source application circuits (decisions, not silent differences)
DEVIATIONS = [
    "TAS5805M PDN: 10 k pull-DOWN instead of TI's 10 k pull-up: amps stay off until the Linux driver drives PDN",
    "IP2366 DPC/DMC: not connected (fig. 9 wires them to USB D+/D- for QC/FCP/AFC); USB data goes to the CH340 console",
    "IP2366 RPSET 3.6 k (30 W) instead of fig. 9 27 k (140 W): 3S pack, cheap inductor and MOSFETs",
    "HAT ZVD PFET DMP3013SFV instead of DMG2305UX: the Pi 5 needs 5 A",
]
