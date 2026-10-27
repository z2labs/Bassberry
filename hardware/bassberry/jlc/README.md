# JLCPCB manufacturing files (rev 0.2)

| File | Upload where | What |
|---|---|---|
| `bassberry_gerber.zip` | PCB order, "Add gerber file" | Gerber (4 copper, mask, paste, silk, outline) + Excellon (PTH and NPTH separate) |
| `bassberry_bom_jlc.csv` | SMT assembly, BOM | `Comment, Designator, Footprint, LCSC Part #` - 86 lines, 168 placed parts |
| `bassberry_cpl_jlc.csv` | SMT assembly, CPL | `Designator, Mid X, Mid Y, Layer, Rotation` (KiCad placement, mm) |
| `bassberry_bom_jlc_bottom.csv` + `bassberry_cpl_jlc_bottom.csv` | SMT assembly, **bottom side only** (recommended) | the 158 bottom parts |
| `bassberry_bom_jlc_top.csv` + `bassberry_cpl_jlc_top.csv` | top side, if JLC should do it too | the 10 top parts (holders, tact switches, encoder, 2x20 socket) |
| `bassberry_bom_full.csv` | - | the same lines with MPN, maker, Basic/Extended, SMT/THT, key spec, the page each code was checked on, notes |
| `not_assembled.csv` | - | parts JLC does not place (DNP, solder jumpers, test point, BMS wire pads, and the 3 parts below) |
| `gerber_check.png` | - | every Gerber layer rendered by an independent viewer (pygerber) |

Regenerate: `powershell -File hardware\tools\jlc_fab.ps1` (Gerber, drill, placement from the board), then
`python3 hardware/tools/jlc_bom_cpl.py` (BOM + CPL from the netlist, the placement and `lcsc_parts.csv`).

## PCB order settings

4 layers, 180 x 110 mm, 1.6 mm FR-4, outer 1 oz / inner 0.5 oz (JLC standard 4-layer stack-up; the layer-3 twin was
computed with exactly these thicknesses), green mask, HASL lead-free or ENIG. Smallest via 0.45 / 0.2 mm (JLC 4-layer
minimum 0.25 / 0.15), smallest track / gap 0.2 / 0.15 mm. No via-in-pad, no impedance control needed.
The Pi SoC thermal pad is a deliberate mask opening on both sides.

## Assembly

**JLC's BOM page shows one side at a time** ("Top Side ... 10 parts detected"): set *PCBA side* on the PCB page to
**Bottom** (or Both) and the 158 bottom parts appear. Recommended: JLC assembles the bottom only; the 10 top parts are
large hand-solder parts, and at the time of writing the Keystone 1042 and the TL3342 had no JLC stock and the EC11 a
shortfall.

* **Both sides:** top = 3 battery holders, 5 tact switches, the encoder, the 2x20 socket; bottom = everything else.
* **Through-hole (JLC THT assembly or hand soldering):** J101 2x20 socket, J201-J203 JST XH, J402 JST PH, J501 header,
  SW506 encoder; the Keystone 1042 holders are SMD-tab parts that JLC lists as "wave soldering".
* 38 lines are JLC Basic parts, 48 Extended (39 distinct Extended codes, each carries JLC's extended-part fee).
* **Rotations and centres are fitted, not guessed** (`hardware/tools/jlc_rotfix.py`, report in `rotfix_report.csv`):
  for every placed part the EasyEDA footprint of its LCSC part (the model JLC places) is downloaded and fitted onto the
  board's pads - by pin number where the numbering agrees, by geometry otherwise. The CPL rotation is KiCad's .pos
  rotation plus the angle between JLC's and KiCad's footprint; the CPL position is where JLC's footprint origin lands
  (the 2x20 socket and the encoder have their KiCad origin on a pin, not at the body centre). The same fit is the
  land-pattern check: every JLC pad centre must land on this footprint's copper.
  Results: 168 parts fitted; 167 OK (the encoder 7/7 pads, the holders and switches exact). Q101 (DMP3013SFV): JLC's PowerDI3333 model has two small exposed-pad side tabs
  that KiCad's land pattern does not have - pins 1-4 and the drain fit, no action. F401 and U502 fit with 0.6 / 0.4 mm
  pad-spacing differences (2410 fuse on 2512 pads, SOP-16 row spacing), centred.
* **Part numbers: `lcsc_parts.csv` is the source of truth**, as confirmed in stock by Zoltan on 2026-10-27
  (Keystone 1042 C5249310, TL3342F160QG C2886898, EC11E15244G1 C370970 on the top side). Substitutes tried in JLC's
  BOM tool were checked by the same fit: the 18650 holder C2988620 does **not** fit (contacts 82.6 mm apart vs 79.4 mm).
* Still look at JLC's placement preview before paying, and at the DFM check JLC sends after the order.

## Check before ordering

1. **U306 XC6216B332PR (USB-side 3.3 V LDO, 28 V):** not found at LCSC - consign it, or pick another >= 24 V / >= 300 mW
   3.3 V LDO in SOT-89-5 with the same pin-out (1 VOUT, 2 VSS, 3 CE, 4 NC, 5 VIN).
2. **L301 (charger inductor, 22 uH):** no LCSC part reaches the "≥ 10 A, < 10 mOhm" target in the MWSA1265S land pattern.
   At the 30 W PSET setting the inductor sees about 3-4 A, so FXL1360-220-M (C526028, Isat 7.5 A, 39.5 mOhm) would do
   electrically, but its terminals are not checked against the footprint - left out of the assembly until decided.
3. **J502 OLED socket:** no right-angle 1x4 female socket at LCSC for this footprint - hand-fit (or change it to vertical, C2718488).
4. **U302 IP2366:** LCSC lists the "I2C version" (C20415848). Confirm it is pin- and function-compatible with the
   resistor-programmed circuit (PSET / BAT_NUM / VSET), and that its exposed pad (3.4 mm per one listing) suits the 3.6 mm footprint pad.
5. **F401 fuse:** Littelfuse 0451010.MRL (C44479, 10 A, NANO2 2410 body) on the 2512 footprint pads; its breaking
   capacity is 50 A, so the pack short-circuit protection is the BMS module's job, the fuse is the backup.
6. **C314, C317:** Panasonic EEHZK1V331P 330 uF / 35 V hybrid polymer (the 220 uF part was out of stock) - more
   capacitance, same can.
7. **R331 57k6 1 %:** only about 400 in stock at the time of the lookup.
8. Q301-Q304: Infineon BSC050N04LS G (40 V, 5 mOhm) in place of the AER4061BE of the IP2366 reference design.

Stock figures are from the LCSC pages on 2026-10-27; re-check at ordering time.
