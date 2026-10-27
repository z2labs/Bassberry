# Bassberry digital twin (layers 1–4)

Pre-fabrication verifier, built the same way as the fg23-cw-trainer and ionos-sdr-mini twins.
It does not draw anything and does not replace DRC. It proves that **the copper is what we think it is**.

The specification (`spec_bassberry.py`) is written **only from source documents** (datasheets, application circuits,
Raspberry Pi drawings, HAT design guide). Every table names its source. It is never derived from our own schematic.

| Layer | File | Reads | Checks |
|---|---|---|---|
| 1 | `twin_check.py` | `.kicad_pcb` pad→net map (or the `.net` before layout) + `spec_bassberry.py` | every function lands where its datasheet says: Pi header roles, HAT ID rules, the back-power diode topology, TAS5805M PBTL ties / BST caps / ADR addresses, the IP2366 fig. 9 circuit, BAT_NUM/VSET/PSET values, buck/boost dividers, cells and BMS order, USB, supervisor pins |
| 2 | `twin_plug.py` | board geometry + Pi drawings | the Pi is fitted **face down** to the 58 × 49 mm hole pattern, then each Pi pin is joined to whatever pad is physically under it and the Pi signals of layer 1 are re-checked through that join; port block over the open corner, Pi 4 and Pi 5 SoC lids on the thermal pad, antenna in the keep-out, nothing under the Pi |
| 3 | `twin_analog.py` | the routed copper incl. zone fills | rasterised (0.2 mm) max-flow ampacity of each high-current path through tracks, pads and power pours on all layers, between the pads where the current really enters and leaves (IPC-2221, 20 K rise, vias 1.5 A each); Pi 5 V set-point and IR drop at 5 A, boost set-point, TAS5805M PVDD window, LDO dissipation (USB side at a 20 V PD contract) |
| 4 | `twin_mech.py` | board geometry | 18650 holders (axis, contact spacing, side by side, series links at the same end, clear of the Pi), USB-C at the rear edge, lid controls in the front strip, speaker connectors on the acoustic side, screw heads free |
| 5 | `twin_dfm.py` | board geometry vs JLC DFM | what JLC's DFM check flags on the Gerbers and KiCad's DRC does not: via ring on an SMD pad (own net too), pads of different parts < 0.1 mm, plated slot < 0.65 mm, silk < 0.15 mm from a mask opening or a drilled hole (vias included); warnings: via ring < 0.15 mm, short slots, THT pad < 2 mm from an SMD pad |

## Run

```powershell
$py = "C:\Program Files\KiCad\10.0\bin\python.exe"
& $py hardware\twin\twin_check.py  hardware\bassberry\bassberry.kicad_pcb --selftest
& $py hardware\twin\twin_plug.py   hardware\bassberry\bassberry.kicad_pcb --selftest
& $py hardware\twin\twin_analog.py hardware\bassberry\bassberry.kicad_pcb --selftest
& $py hardware\twin\twin_mech.py   hardware\bassberry\bassberry.kicad_pcb --selftest
& $py hardware\twin\twin_dfm.py    hardware\bassberry\bassberry.kicad_pcb --selftest
```

Layer 1 also runs without KiCad on the netlist: `python3 hardware/twin/twin_check.py hardware/bassberry/bassberry.net --selftest`.
`hardware\tools\postroute.ps1` runs all four after the routing post-processing and the DRC.

Exit code: `0` clean, `1` FAIL, `2` missing input, `3` self-test failed.

## Self-tests (injected faults, each must produce a new FAIL)

* Layer 1, 16 faults: Pi socket mirrored (the face-down trap), I2S clock swap, back-power PFET D/S swap, HAT EEPROM SDA/SCL swap,
  charger gate drive swap, buck VIN/SW swap, boost FB/EN swap, BMS B1/B2 swap, a cell holder reversed, USB D+/D- swap,
  supervisor I2C swap, both amps on one I2C address, wrong buck divider, BAT_NUM for 4 cells, missing PBTL tie, an extra load on ID_SD.
* Layer 2: socket rows swapped, Pi plugged one pin off.
* Layer 3: a battery link necked to 0.25 mm without its pour, a buck divider giving 6.1 V.
  (Max-flow runs in a window around the source and sink pads that grows only if needed: ignoring copper can only lower
  the result, so a PASS is never optimistic. Via capacity is 1.5 A per 0.3 mm of drill.)
* Layer 4: a cell holder turned 90°, a holder reversed, a lid button on the bottom, the USB-C turned round.

## What it found (rev 0.2)

* **USB-C turned 180°** (contact pads over the board edge) - layer 4 now checks the pad row position.
* **USB LDO overload at a 20 V PD contract:** HT7533-1 (24 V / 250 mW) at 20 V x 15 mA = 250 mW → replaced by a
  Torex XC6216B332PR (28 V / 500 mW).
* **Power copper too thin** where srouter had to route a power net at the width of its smallest pad → `fatten.py`
  and `power_pour.py` (see the hardware README), checked by the layer-3 max-flow.
* The Pi socket footprint and the face-down mapping are correct pin by pin (layer 2); both Pi 4 and Pi 5 SoC lids sit on the thermal pad.
* **14 under-rated current paths** on the first routed board (the +BATT rail, the 5 V path, the buck SW node, single vias in
  2-3 A speaker paths, a battery link): layer 3 now prints where the min cut is, which led to the trunk pass, the In1 +BATT
  plane, the parallel / larger vias, and two part rotations. Final board: 0 FAIL.
* **srouter's track_tidy disconnects things** (a track moved off a pad, two track pieces no longer meeting, a lost layer
  change): caught by DRC, repaired by `tidy_guard.py`.

## Physical list (not provable from copper)

OLED module pin order (GND-VCC-SCL-SDA), BMS module pad order, cell polarity at insertion, the NTC fitted on J402
(the IP2366 NTC pin must never float), the Pi antenna position on a real Pi, the TDSON MOSFET pin-out of the chosen part.

## Accepted deviations from the source circuits

TAS5805M PDN pulled down (amps off until the driver), IP2366 DPC/DMC unused (USB data goes to the console), PSET 30 W,
ZVD PFET DMP3013SFV (5 A) instead of DMG2305UX. Each one is printed as a WARN on every run.
