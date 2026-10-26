"""Bassberry schematic source. Run with KiCad's python:
   "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" hardware/tools/bassberry_sch.py
Writes hardware/bassberry/*.kicad_sch
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from schgen import Project
from kilib import PROJECT_LIBS
from projlib import write_lib

OUT = os.path.join(os.path.dirname(__file__), "..", "bassberry")
os.makedirs(OUT, exist_ok=True)
write_lib(os.path.join(OUT, "bassberry.kicad_sym"))
PROJECT_LIBS["bassberry"] = os.path.join(OUT, "bassberry.kicad_sym")
P = Project(OUT)

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
CP_10x10 = "Capacitor_SMD:CP_Elec_10x10.5"
JST2 = "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical"
IND_PWR = "Inductor_SMD:L_Changjiang_FXL1050"

GLOBAL = {"I2C_SDA", "I2C_SCL", "I2S_BCLK", "I2S_LRCLK", "I2S_DOUT", "AMP_PDN", "PI_IRQ",
          "PI_SHUTDOWN_REQ", "PI_POWEROFF", "PI_TXD", "PI_RXD", "PVDD_SUB", "+3V3_AON",
          "USB_DP", "USB_DN", "+3V3_USB", "PI_PWR_EN", "BOOST_EN", "CHG_LED_A", "CHG_LED_B", "CHG_LED_COM", "NTC"}


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
    r.C(f"C{b+1}", "4u7", "+3V3", "GND", C0603)
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
    r.L(ref, "10u 3A shielded", a, b, "Inductor_SMD:L_Changjiang_FXL1040")
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

# =====================================================================  Power: USB-C, charger, rails
pw = P.child("power", "power.kicad_sch", "Power: USB-C PD charger (IP2366), 5V/5A Pi buck, sub boost, 3V3 LDOs", GLOBAL, paper="A2")
pw.text("IP2366 application per Injoinic datasheet V1.10 fig. 9. Settings: 3S (6.2k), 4.2V/cell (9.1k), 30W (3.6k).", 30, 22)
pw.text("DPC/DMC (QC/FCP/AFC) left unconnected: USB D+/D- go to the CH340 console. PD on CC still negotiates 5-20V.", 30, 28)
pw.text("Q1-Q4 any 30-40V N-MOSFET, ~5 mOhm, TDSON/DFN5x6 (IP2366 ref: AER4061BE). Q5 optional input switch (R5 bypass).", 30, 34)

pw.part("Connector:USB_C_Receptacle_USB2.0_16P", "J1", "USB-C (charge + console)", 45, 90,
        fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        nets={"A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS", "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
              "SH": "GND", "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN", "B7": "USB_DN",
              "A8": "NC", "B8": "NC"})
pw.part("Power_Protection:USBLC6-2SC6", "U1", "USBLC6-2SC6", 45, 140, fp="Package_TO_SOT_SMD:SOT-23-6",
        nets={"1": "USB_DP", "6": "USB_DP", "3": "USB_DN", "4": "USB_DN", "5": "+3V3_USB", "2": "GND"})
pw.part("Device:D_TVS", "D1", "SMAJ24A", 75, 140, fp="Diode_SMD:D_SMA", nets={"1": "VBUS", "2": "GND"})
pw.flag("VBUS", 20, 60)
pw.flag("CHG_VIN", 30, 60)

# IP2366 core
pw.part("bassberry:IP2366", "U2", "IP2366", 170, 120, fp="Package_DFN_QFN:QFN-40-1EP_5x5mm_P0.4mm_EP3.6x3.6mm",
        nets={"VBUS": "VBUS", "VBUSG": "CHG_VBUSG", "VBUSI": "CHG_VIN", "VIO": "CHG_VIN", "CSP1": "CHG_VIN",
              "CSN1": "CHG_CSN1", "PCIN": "CHG_NODEB", "CC1": "CC1", "CC2": "CC2", "DPC": "NC", "DMC": "NC",
              "EN": "CHG_EN", "GPIO20": "CHG_LED_A_R", "GPIO19": "CHG_LED_B_R", "GPIO1": "CHG_LED_COM",
              "HG1": "CHG_HG1_R", "BST1": "CHG_BST1", "LX1": "CHG_LX1", "LG1": "CHG_LG1_R", "LG2": "CHG_LG2_R",
              "LX2": "CHG_LX2", "BST2": "CHG_BST2", "HG2": "CHG_HG2_R", "PCON": "CHG_NODEC", "CSN2": "CHG_CSN2",
              "CSP2": "+BATT", "BAT": "+BATT", "CC_BDO": "CHG_CCBDO", "VCC5V": "CHG_VCC5V", "VCCIO": "CHG_VCCIO",
              "GPIO4/BAT_NUM": "CHG_BATNUM", "GPIO3/PSET": "CHG_PSET", "GPIO2/VSET": "CHG_VSET", "GPIO0/NTC": "NTC",
              "AGND": "GND", "EPAD": "GND"})
r = Row(pw, 115, 200, 10.16)
r.R("R1", "51", "CHG_NODEB", "CHG_CSN1", R0603)
r.C("C1", "470n", "CHG_VIN", "CHG_CSN1", C0603)
r.C("C2", "2u2 35V", "CHG_VIN", "GND", C0603)
r.R("R3", "10", "CHG_NODEC", "CHG_CSN2", R0603)
r.C("C3", "1u", "CHG_CSN2", "+BATT", C0603)
r.C("C4", "2u2 35V", "+BATT", "GND", C0603)
r.C("C5", "2u2", "CHG_VCC5V", "GND", C0603)
r.C("C6", "2u2", "CHG_VCCIO", "GND", C0603)
r.R("R10", "NC", "CHG_CCBDO", "GND", R0603, dnp=True)
r.R("R11", "6k2 1%", "CHG_BATNUM", "GND", R0603)
r.R("R12", "3k6 1%", "CHG_PSET", "GND", R0603)
r.R("R13", "9k1 1%", "CHG_VSET", "GND", R0603)
r.C("C7", "100n", "NTC", "GND", C0603)
r = Row(pw, 115, 225, 10.16)
r.R("R14", "43k", "CHG_KEY", "CHG_EN", R0603)
r.R("R15", "10k", "CHG_EN", "GND", R0603)
pw.part("Switch:SW_Push", "SW1", "PWRBANK (optional)", 150, 235, fp="Button_Switch_SMD:SW_SPST_TL3342", nets={"1": "+BATT", "2": "CHG_KEY"}, dnp=True)
# charge LEDs (charlieplexed by IP2366)
r = Row(pw, 175, 225, 10.16)
r.R("R16", "100", "CHG_LED_A_R", "CHG_LED_A", R0603)
r.R("R17", "100", "CHG_LED_B_R", "CHG_LED_B", R0603)
for i, (a, k) in enumerate((("CHG_LED_A", "CHG_LED_COM"), ("CHG_LED_COM", "CHG_LED_A"), ("CHG_LED_B", "CHG_LED_COM"), ("CHG_LED_COM", "CHG_LED_B"))):
    pw.part("Device:LED", f"D{2+i}", "LED white 0603", 205 + i * 12.7, 235, rot=90, fp="LED_SMD:LED_0603_1608Metric", nets={"1": k, "2": a})

# power stage
MOS = "Package_TO_SOT_SMD:TDSON-8-1"
FET = "Transistor_FET:BSC028N06LS3"
NMOS_V = "40V N-MOS 5mR (AER4061BE equiv)"
pw.part(FET, "Q5", "30V N-MOS (RU3030M2) opt.", 80, 70, fp=MOS, nets={"G": "CHG_VBUSG", "D": "VBUS", "S": "CHG_VIN"}, dnp=True)
pw.R("R5", "0R (bypass Q5)", 95, 70, "VBUS", "CHG_VIN", "Resistor_SMD:R_1206_3216Metric")
pw.R("R2", "5m 1% 1206", 110, 70, "CHG_VIN", "CHG_NODEB", "Resistor_SMD:R_1206_3216Metric")
pw.part(FET, "Q1", NMOS_V, 240, 60, fp=MOS, nets={"G": "CHG_HG1", "D": "CHG_NODEB", "S": "CHG_LX1"})
pw.part(FET, "Q2", NMOS_V, 240, 85, fp=MOS, nets={"G": "CHG_LG1", "D": "CHG_LX1", "S": "GND"})
pw.part(FET, "Q3", NMOS_V, 300, 60, fp=MOS, nets={"G": "CHG_HG2", "D": "CHG_NODEC", "S": "CHG_LX2"})
pw.part(FET, "Q4", NMOS_V, 300, 85, fp=MOS, nets={"G": "CHG_LG2", "D": "CHG_LX2", "S": "GND"})
pw.L("L1", "22u >=10A Rdc<10m", 270, 40, "CHG_LX1", "CHG_LX2", "Inductor_SMD:L_Sunlord_MWSA1265S")
r = Row(pw, 230, 110, 10.16)
r.R("R6", "10", "CHG_HG1_R", "CHG_HG1", R0603)
r.R("R7", "2", "CHG_LG1_R", "CHG_LG1", R0603)
r.R("R8", "2", "CHG_HG2_R", "CHG_HG2", R0603)
r.R("R9", "2", "CHG_LG2_R", "CHG_LG2", R0603)
r.C("C8", "100n 50V", "CHG_BST1", "CHG_LX1", C0603)
r.C("C9", "100n 50V", "CHG_BST2", "CHG_LX2", C0603)
r.R("R20", "2", "CHG_LX1", "CHG_SN1", R0603)
r.C("C10", "3n3 50V", "CHG_SN1", "GND", C0603)
r.R("R21", "2", "CHG_LX2", "CHG_SN2", R0603)
r.C("C11", "3n3 50V", "CHG_SN2", "GND", C0603)
r = Row(pw, 230, 140, 10.16)
r.C("C12", "22u 35V", "CHG_VIN", "GND", C1210)
r.C("C13", "22u 35V", "CHG_VIN", "GND", C1210)
r.CP("C14", "220u 35V polymer", "CHG_VIN", "GND", CP_10x10)
r.R("R4", "5m 1% 1206", "CHG_NODEC", "+BATT", "Resistor_SMD:R_1206_3216Metric")
r.C("C15", "22u 35V", "+BATT", "GND", C1210)
r.C("C16", "22u 35V", "+BATT", "GND", C1210)
r.CP("C17", "220u 35V polymer", "+BATT", "GND", CP_10x10)

# 5.1 V / 5 A buck for the Pi (TPS565208, VIN 4.5-17 V)
pw.text("Pi 5V buck: Vout = 0.76*(1+R31/R32) = 5.14 V. EN driven by supervisor (PI_PWR_EN).", 30, 290)
pw.part("Regulator_Switching:TPS565208", "U3", "TPS565208", 80, 330, fp="Package_TO_SOT_SMD:SOT-23-6",
        nets={"VIN": "+BATT", "EN": "PI_PWR_EN", "GND": "GND", "SW": "BUCK_SW", "VBST": "BUCK_BST", "VFB": "BUCK_FB"})
r = Row(pw, 110, 320, 10.16)
r.C("C30", "100n", "BUCK_BST", "BUCK_SW", C0603)
r.L("L2", "4u7 7A", "BUCK_SW", "+5V", "Inductor_SMD:L_Changjiang_FXL1040")
r.R("R31", "57k6 1%", "+5V", "BUCK_FB", R0603)
r.R("R32", "10k 1%", "BUCK_FB", "GND", R0603)
r.C("C31", "47p", "+5V", "BUCK_FB", C0603)
r.R("R33", "100k", "PI_PWR_EN", "GND", R0603)
r = Row(pw, 110, 350, 10.16)
r.C("C32", "10u 25V", "+BATT", "GND", C1206)
r.C("C33", "10u 25V", "+BATT", "GND", C1206)
r.C("C34", "100n 50V", "+BATT", "GND", C0603)
r.C("C35", "22u 10V", "+5V", "GND", C1206)
r.C("C36", "22u 10V", "+5V", "GND", C1206)
r.C("C37", "22u 10V", "+5V", "GND", C1206)

# sub boost (optional) MT3608, ~17 V
pw.text("Sub PVDD boost (optional): Vout = 0.6*(1+R41/R42) = 17.1 V. JP1 selects PVDD_SUB = +BATT (default) or boost.", 200, 290)
pw.part("Regulator_Switching:MT3608", "U4", "MT3608", 230, 330, fp="Package_TO_SOT_SMD:SOT-23-6",
        nets={"IN": "+BATT", "EN": "BOOST_EN", "GND": "GND", "SW": "BOOST_SW", "FB": "BOOST_FB"})
r = Row(pw, 255, 320, 10.16)
r.L("L3", "10u 4A", "+BATT", "BOOST_SW", "Inductor_SMD:L_Changjiang_FXL1040")
pw.part("Device:D_Schottky", "D6", "SS34", 285, 310, fp="Diode_SMD:D_SMA", nets={"A": "BOOST_SW", "K": "BOOST_OUT"})
r = Row(pw, 295, 320, 10.16)
r.R("R41", "60k4 1%", "BOOST_OUT", "BOOST_FB", R0603)
r.R("R42", "2k2 1%", "BOOST_FB", "GND", R0603)
r.C("C40", "22u 25V", "BOOST_OUT", "GND", C1210)
r.C("C41", "22u 25V", "BOOST_OUT", "GND", C1210)
r.R("R43", "100k", "BOOST_EN", "GND", R0603)
pw.part("Jumper:SolderJumper_3_Bridged12", "JP1", "PVDD_SUB select", 360, 330,
        fp="Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm",
        nets={"1": "+BATT", "2": "PVDD_SUB", "3": "BOOST_OUT"})
pw.flag("PVDD_SUB", 375, 330)

# always-on 3V3 (supervisor) and USB-side 3V3 (CH340, ESD)
pw.part("Regulator_Linear:HT75xx-1-SOT89", "U5", "HT7533-1", 80, 400, fp="Package_TO_SOT_SMD:SOT-89-3",
        nets={"VIN": "+BATT", "VOUT": "+3V3_AON", "GND": "GND"})
pw.part("Regulator_Linear:HT75xx-1-SOT89", "U6", "HT7533-1", 160, 400, fp="Package_TO_SOT_SMD:SOT-89-3",
        nets={"VIN": "VBUS", "VOUT": "+3V3_USB", "GND": "GND"})
r = Row(pw, 100, 420, 10.16)
r.C("C50", "1u 25V", "+BATT", "GND", C0603)
r.C("C51", "1u", "+3V3_AON", "GND", C0603)
r = Row(pw, 180, 420, 10.16)
r.C("C52", "1u 35V", "VBUS", "GND", C0603)
r.C("C53", "1u", "+3V3_USB", "GND", C0603)

# =====================================================================  Battery
bt = P.child("battery", "battery.kicad_sch", "Battery: 3S 18650 clips, BMS module, protection", GLOBAL)
bt.text("3x 18650 in Keystone 54 clips. Balancing + protection by an off-the-shelf 3S BMS module (B-, B1, B2, B+, P-).", 25, 22)
bt.text("Reverse-cell LED lights only when a cell is inserted backwards. P- of the BMS = board GND.", 25, 28)
cells = [("CELL0", "CELL1"), ("CELL1", "CELL2"), ("CELL2", "CELL3")]
for i, (neg, pos) in enumerate(cells):
    x = 50 + i * 60
    bt.part("Connector_Generic:Conn_01x01", f"BT{i+1}A", f"cell {i+1} +", x, 70, fp="Battery:BatteryClip_Keystone_54_D16-19mm", nets={"1": pos})
    bt.part("Connector_Generic:Conn_01x01", f"BT{i+1}B", f"cell {i+1} -", x, 90, fp="Battery:BatteryClip_Keystone_54_D16-19mm", nets={"1": neg})
    bt.part("Device:LED", f"D{i+1}", "LED red 0603 (reverse cell)", x + 25, 80, rot=90, fp="LED_SMD:LED_0603_1608Metric",
            nets={"1": pos, "2": f"REV{i+1}"})
    bt.R(f"R{i+1}", "2k2", x + 35, 80, f"REV{i+1}", neg, R0603)
bt.part("Connector_Generic:Conn_01x05", "J1", "3S BMS module (B-,B1,B2,B+,P-)", 80, 150,
        fp="Connector_Wire:SolderWire-1sqmm_1x05_P5.4mm_D1.4mm_OD2.7mm",
        nets={"1": "CELL0", "2": "CELL1", "3": "CELL2", "4": "CELL3", "5": "GND"})
bt.part("Device:Fuse", "F1", "10A fast 2512", 150, 150, fp="Fuse:Fuse_2512_6332Metric", nets={"1": "CELL3", "2": "+BATT"})
bt.part("Connector_Generic:Conn_01x02", "J2", "NTC 10k B3380 on cell", 200, 150, fp="Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
        nets={"1": "NTC", "2": "GND"})
bt.flag("+BATT", 165, 140)

# =====================================================================  UI / supervisor / console
ui = P.child("ui", "ui.kicad_sch", "UI + supervisor MCU (CH32V003), OLED, buttons, encoder, USB console", GLOBAL)
ui.text("Supervisor runs from +3V3_AON. I2C slave to the Pi on PC1/PC2; PI_IRQ and PI_SHUTDOWN_REQ are open-drain.", 25, 22)
ui.text("Buttons active-low with MCU internal pull-ups. VBAT_SENSE = VBAT * 22/122.", 25, 28)
ui.part("MCU_WCH_RiscV:CH32V003FxPx", "U1", "CH32V003F4P6", 110, 100, fp="Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
        nets={"VDD": "+3V3_AON", "VSS": "GND", "PC0": "BOOST_EN", "PC1": "I2C_SDA", "PC2": "I2C_SCL",
              "PC3": "BTN_PWR", "PC4": "BTN_BT", "PC5": "BTN_PLAY", "PC6": "BTN_VOLDN", "PC7": "BTN_VOLUP",
              "PD0": "PI_POWEROFF", "PD1": "SWIO", "PD2": "ENC_A", "PD3": "ENC_B", "PD4": "ENC_SW",
              "PD5": "PI_IRQ", "PD6": "PI_SHUTDOWN_REQ", "PD7": "MCU_NRST", "PA1": "PI_PWR_EN", "PA2": "VBAT_SENSE"})
r = Row(ui, 60, 150, 10.16)
r.C("C1", "100n", "+3V3_AON", "GND", C0603)
r.C("C2", "1u", "+3V3_AON", "GND", C0603)
r.R("R1", "10k", "+3V3_AON", "MCU_NRST", R0603)
r.R("R2", "100k 1%", "+BATT", "VBAT_SENSE", R0603)
r.R("R3", "22k 1%", "VBAT_SENSE", "GND", R0603)
r.C("C3", "100n", "VBAT_SENSE", "GND", C0603)
ui.part("Connector_Generic:Conn_01x03", "J1", "SWIO (WCH-LinkE)", 200, 150, fp="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        nets={"1": "+3V3_AON", "2": "SWIO", "3": "GND"})
for i, (net, name) in enumerate((("BTN_PWR", "POWER"), ("BTN_BT", "BT"), ("BTN_PLAY", "PLAY/PAUSE"), ("BTN_VOLDN", "VOL-"), ("BTN_VOLUP", "VOL+"))):
    ui.part("Switch:SW_Push", f"SW{i+1}", name, 210, 60 + i * 12.7, fp="Button_Switch_SMD:SW_SPST_TL3342", nets={"1": net, "2": "GND"})
ui.part("Device:RotaryEncoder_Switch", "SW6", "EC11 encoder + push", 280, 70, fp="Rotary_Encoder:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm",
        nets={"A": "ENC_A", "B": "ENC_B", "C": "GND", "S1": "ENC_SW", "S2": "GND"})
ui.part("Connector_Generic:Conn_01x04", "J2", "OLED 1.3in I2C (GND VCC SCL SDA)", 280, 120, fp="Connector_PinSocket_2.54mm:PinSocket_1x04_P2.54mm_Vertical",
        nets={"1": "GND", "2": "+3V3", "3": "I2C_SCL", "4": "I2C_SDA"})
# USB serial console
ui.part("Interface_USB:CH340C", "U2", "CH340C", 110, 210, fp="Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
        nets={"VCC": "+3V3_USB", "V3": "CH340_V3", "GND": "GND", "UD+": "USB_DP", "UD-": "USB_DN", "R232": "GND",
              "TXD": "CON_TXD", "RXD": "CON_RXD", "~{CTS}": "NC", "~{DSR}": "NC", "~{RI}": "NC", "~{DCD}": "NC",
              "~{DTR}": "NC", "~{RTS}": "NC"})
r = Row(ui, 160, 210, 10.16)
r.R("R10", "1k", "CON_TXD", "PI_RXD", R0603)
r.R("R11", "1k", "PI_TXD", "CON_RXD", R0603)
r.C("C10", "100n", "+3V3_USB", "GND", C0603)
r.R("R12", "0R (V3=VCC for 3V3 op.)", "CH340_V3", "+3V3_USB", R0603)

P.write()
print("schematics written to", os.path.abspath(OUT))
