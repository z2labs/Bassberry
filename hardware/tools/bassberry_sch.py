"""Bassberry schematic source. Run with KiCad's python:
   "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/bassberry_sch.py
Writes hardware/bassberry/*.kicad_sch
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from schgen import Project

OUT = os.path.join(os.path.dirname(__file__), "..", "bassberry")
P = Project(OUT)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
CP_10x10 = "Capacitor_SMD:CP_Elec_10x10.5"
JST2 = "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"
IND_PWR = "Inductor_SMD:L_Bourns_SRR1260"

GLOBAL = {"I2C_SDA", "I2C_SCL", "I2S_BCLK", "I2S_LRCLK", "I2S_DOUT", "AMP_PDN", "PI_IRQ",
          "PI_SHUTDOWN_REQ", "PI_POWEROFF", "PI_TXD", "PI_RXD", "PVDD_SUB", "+3V3_AON"}


class Row:
    """Place vertical 2-pin parts left-to-right."""
    def __init__(self, sheet, x, y, pitch=10.16):
        self.s, self.x, self.y, self.p = sheet, x, y, pitch

    def _next(self):
        x = self.x; self.x += self.p; return x

    def R(self, *a, **k): return self.s.R(a[0], a[1], self._next(), self.y, *a[2:], **k)
    def C(self, *a, **k): return self.s.C(a[0], a[1], self._next(), self.y, *a[2:], **k)
    def CP(self, *a, **k): return self.s.CP(a[0], a[1], self._next(), self.y, *a[2:], **k)
    def L(self, *a, **k): return self.s.L(a[0], a[1], self._next(), self.y, *a[2:], **k)


# =====================================================================  Raspberry Pi
pi = P.child("pi", "pi.kicad_sch", "Raspberry Pi (mounted face-down) + HAT ID", GLOBAL)
pi.text("Raspberry Pi plugs in FACE-DOWN: footprint is the mirrored face-down socket.", 40, 30)
pi.text("I2C1 has 1k8 pull-ups on the Pi itself. Series resistors = source termination for I2S.", 40, 36)
pi_nets = {
    "2": "+5V", "4": "+5V", "1": "+3V3", "17": "+3V3",
    "6": "GND", "9": "GND", "14": "GND", "20": "GND", "25": "GND", "30": "GND", "34": "GND", "39": "GND",
    "3": "I2C_SDA", "5": "I2C_SCL", "27": "ID_SD", "28": "ID_SC",
    "12": "PI_BCLK", "35": "PI_LRCLK", "40": "PI_DOUT", "38": "NC",
    "7": "AMP_PDN", "11": "PI_IRQ", "15": "PI_SHUTDOWN_REQ", "13": "PI_POWEROFF",
    "8": "PI_TXD", "10": "PI_RXD",
}
for n in ("32", "33", "36", "16", "18", "22", "37", "29", "31", "26", "24", "21", "19", "23"):
    pi_nets[n] = "NC"
pi.part("Connector:Raspberry_Pi_4", "J1", "RPi 40-pin (face-down socket)", 160, 120,
        fp="Module:Raspberry_Pi_Zero_Socketed_THT_FaceDown_MountingHoles", nets=pi_nets)
r = Row(pi, 60, 190, 12.7)
r.R("R1", "33", "PI_BCLK", "I2S_BCLK", R0603)
r.R("R2", "33", "PI_LRCLK", "I2S_LRCLK", R0603)
r.R("R3", "33", "PI_DOUT", "I2S_DOUT", R0603)
r.R("R4", "3k9", "+3V3", "ID_SD", R0603)
r.R("R5", "3k9", "+3V3", "ID_SC", R0603)
r.R("R6", "10k", "+3V3", "PI_IRQ", R0603)
r = Row(pi, 60, 225, 12.7)
r.C("C1", "100u 6.3V", "+5V", "GND", C1210)
r.C("C2", "10u", "+5V", "GND", C0805)
r.C("C3", "100n", "+3V3", "GND", C0603)
pi.part("Memory_EEPROM:24LC32", "U1", "24C32 (HAT ID)", 250, 200, fp="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        nets={"VCC": "+3V3", "GND": "GND", "SDA": "ID_SD", "SCL": "ID_SC", "A0": "GND", "A1": "GND", "A2": "GND", "WP": "ID_WP"})
pi.part("Jumper:SolderJumper_2_Open", "JP1", "EEPROM write enable", 290, 200, fp="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
        nets={"1": "ID_WP", "2": "GND"})
pi.R("R7", "10k", 290, 225, "+3V3", "ID_WP", R0603)

# =====================================================================  Audio
au = P.child("audio", "audio.kicad_sch", "Audio: 2x TAS5805M (stereo BTL + sub PBTL)", GLOBAL)
au.text("U2 sub amp: PBTL. OUT_A+/OUT_A- and OUT_B+/OUT_B- paralleled pre-filter (verify vs TI datasheet PBTL section).", 30, 22)
au.text("ADR resistor sets each amp's I2C address (different values for U1/U2, verify table in datasheet).", 30, 28)


def tas(sheet, ref, n, x, y, pvdd, adr_val, sdin, sdout, outs):
    nets = {
        "1": "GND", "5": "GND", "14": "GND", "19": "GND", "24": "GND", "29": "GND",
        "2": "+3V3", "15": pvdd, "16": pvdd, "27": pvdd, "28": pvdd,
        "12": "AMP_PDN", "3": f"AMP{n}_ADR", "11": "I2C_SCL", "10": "I2C_SDA",
        "6": "I2S_LRCLK", "7": "I2S_BCLK", "8": sdin, "9": sdout,
        "4": f"AMP{n}_VRDIG", "13": f"AMP{n}_AVDD",
        "25": f"AMP{n}_BSTAP", "22": f"AMP{n}_BSTAN", "18": f"AMP{n}_BSTBP", "21": f"AMP{n}_BSTBN",
    }
    nets.update(outs)
    sheet.part("Amplifier_Audio:TAS5805MPWP", ref, "TAS5805M", x, y, fp="Package_SO:HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP2.85x5.4mm_ThermalVias", nets=nets)
    b = 10 * n
    r = Row(sheet, x - 45, y - 50, 10.16)
    r.C(f"C{b+1}", "1u", "+3V3", "GND", C0603)
    r.C(f"C{b+2}", "100n", "+3V3", "GND", C0603)
    r.C(f"C{b+3}", "1u", f"AMP{n}_VRDIG", "GND", C0603)
    r.C(f"C{b+4}", "1u", f"AMP{n}_AVDD", "GND", C0603)
    r.R(f"R{b+1}", adr_val, "+3V3", f"AMP{n}_ADR", R0603)
    r = Row(sheet, x + 45, y - 50, 10.16)
    r.C(f"C{b+5}", "220n", f"AMP{n}_BSTAP", outs["26"], C0603)
    r.C(f"C{b+6}", "220n", f"AMP{n}_BSTAN", outs["23"], C0603)
    r.C(f"C{b+7}", "220n", f"AMP{n}_BSTBP", outs["17"], C0603)
    r.C(f"C{b+8}", "220n", f"AMP{n}_BSTBN", outs["20"], C0603)
    r = Row(sheet, x - 45, y + 48, 10.16)
    r.C(f"C{b+9}", "100n 50V", pvdd, "GND", C0603)
    r.C(f"C{b+21}", "100n 50V", pvdd, "GND", C0603)
    r.C(f"C{b+22}", "22u 25V", pvdd, "GND", C1206)
    r.C(f"C{b+23}", "22u 25V", pvdd, "GND", C1206)
    r.CP(f"C{b+24}", "470u 25V low-ESR", pvdd, "GND", CP_10x10)


tas(au, "U1", 1, 110, 95, "+BATT", "15k", "I2S_DOUT", "AMP1_SDOUT",
    {"26": "AMP1_AP", "23": "AMP1_AN", "17": "AMP1_BP", "20": "AMP1_BN"})
tas(au, "U2", 2, 110, 215, "PVDD_SUB", "47k", "AMP2_SDIN", "NC",
    {"26": "AMP2_P", "23": "AMP2_P", "17": "AMP2_N", "20": "AMP2_N"})
au.R("R1", "10k", 60, 150, "+3V3", "AMP_PDN", R0603)
au.part("Jumper:SolderJumper_3_Bridged12", "JP1", "U2 SDIN: Pi / U1 SDOUT", 60, 175,
        fp="Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
        nets={"1": "I2S_DOUT", "2": "AMP2_SDIN", "3": "AMP1_SDOUT"})

# output LC filters
filt = [("L1", "AMP1_AP", "SAT_L_P"), ("L2", "AMP1_AN", "SAT_L_N"), ("L3", "AMP1_BP", "SAT_R_P"), ("L4", "AMP1_BN", "SAT_R_N")]
r = Row(au, 200, 60, 12.7)
for ref, a, b in filt:
    r.L(ref, "10u 3A shielded", a, b, "Inductor_SMD:L_Bourns_SRR1005")
r = Row(au, 200, 80, 12.7)
for i, (_, _, b) in enumerate(filt):
    r.C(f"C{40+i}", "680n 50V", b, "GND", C0805)
r = Row(au, 200, 185, 12.7)
r.L("L5", "10u 5A shielded", "AMP2_P", "SUB_P", IND_PWR)
r.L("L6", "10u 5A shielded", "AMP2_N", "SUB_N", IND_PWR)
r = Row(au, 200, 205, 12.7)
r.C("C44", "680n 50V", "SUB_P", "GND", C0805)
r.C("C45", "680n 50V", "SUB_N", "GND", C0805)

for ref, name, p, nn, y in (("J1", "SAT LEFT", "SAT_L_P", "SAT_L_N", 60), ("J2", "SAT RIGHT", "SAT_R_P", "SAT_R_N", 90),
                            ("J3", "SUB", "SUB_P", "SUB_N", 190)):
    au.part("Connector_Generic:Conn_01x02", ref, name, 300, y, fp=JST2, nets={"1": p, "2": nn})

P.write()
print("schematics written to", os.path.abspath(OUT))
