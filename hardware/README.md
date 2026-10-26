# Hardware - Bassberry motherboard (KiCad 10)

<p align="center"><img src="../docs/img/pcb_iso.png" width="85%" alt="Bassberry motherboard, KiCad 3D render"></p>

**Status: rev 0.1 - schematic complete, PCB placed (not routed yet).**

Open `bassberry/bassberry.kicad_pro` in KiCad 10. A PDF of the schematic is in [`bassberry/bassberry_sch.pdf`](bassberry/bassberry_sch.pdf).

## Sheets

| Sheet | Content |
|---|---|
| `pi.kicad_sch` | 40-pin socket for a **face-down** Raspberry Pi (B+/2/3/4/5/Zero), I2S series termination, HAT ID EEPROM |
| `audio.kicad_sch` | 2x TI TAS5805M: U201 stereo BTL (satellites, PVDD = VBAT), U202 PBTL (sub, PVDD_SUB), LC output filters, speaker connectors |
| `power.kicad_sch` | USB-C, Injoinic IP2366 PD3.1 3S buck-boost charger (30 W, 4.2 V/cell), TPS565208 5.1 V / 5 A Pi buck, optional MT3608 ~17 V sub boost, HT7533 LDOs |
| `battery.kicad_sch` | 3x 18650 in Keystone 54 clips, off-the-shelf 3S BMS module (B-, B1, B2, B+, P-), reverse-cell LEDs, 10 A fuse, NTC |
| `ui.kicad_sch` | CH32V003 supervisor (power latch, buttons, encoder, VBAT sense, I2C slave to the Pi), OLED header, CH340C USB console |

Reference designators are numbered per sheet: 1xx Pi, 2xx audio, 3xx power, 4xx battery, 5xx UI.

## Board

* 180 x 110 mm, 4 layers: F.Cu / In1 GND / In2 GND / B.Cu (GND pours), 1.6 mm.
* Top: face-down Pi (header on the right of its area, port end in the open rear-left corner), 3S cell clips, front UI strip (buttons with printed plungers, EC11 encoder, right-angle OLED socket).
* Bottom: amplifiers, charger power stage, regulators, MCU. Electrolytics face the acoustic divider (12 mm clearance).
* Pi SoC thermal pad: exposed copper + 0.3 mm via field to the inner GND planes, two M2.5 bolts for the aluminium pedestal.
* Copper keep-out (all layers) under the Pi's Wi-Fi/BT antenna.

## Regenerating

The KiCad files are generated from Python so the design stays reviewable as code:

```powershell
$py  = "C:\Program Files\KiCad\10.0\bin\python.exe"
$cli = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
& $py  hardware\tools\bassberry_sch.py                     # schematics + project symbol lib
cd hardware\bassberry
& $cli sch erc bassberry.kicad_sch
& $cli sch export netlist --format kicadsexpr -o bassberry.net bassberry.kicad_sch
cd ..\..
& $py  hardware\tools\pcb_build.py                          # outline, stack-up, placement, nets, zones
```

> Once routing starts in the KiCad editor, **do not re-run `pcb_build.py`** (it rebuilds the board from scratch).
> Schematic changes then go through *Update PCB from Schematic* as usual.

## Known open items (rev 0.1)

- [ ] ERC: 2 expected errors - TAS5805M PBTL pre-filter output pairing (OUT_A+/OUT_A-, OUT_B+/OUT_B-), exactly as in TI's datasheet fig. "MONO (PBTL) Systems".
- [ ] Verify the TAS5805M ADR resistor to I2C address mapping (15k / 47k pull-ups) against the datasheet table.
- [ ] Verify Pi 4/5 SoC position and Wi-Fi antenna position for the thermal pad and the keep-out.
- [ ] Verify Keystone 54 clip spacing for 18650 length and the BMS module pad pitch.
- [ ] Choose final low-cost MOSFETs for the IP2366 bridge (40 V, ~5 mOhm, DFN5x6) and confirm the QFN40 exposed-pad size.
- [ ] MT3608 boost: confirm switch current limit for the sub rail at full output, or swap for a stronger boost.
- [ ] Routing.
