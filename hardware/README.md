# Hardware - Bassberry motherboard (KiCad 10)

<p align="center"><img src="../docs/img/pcb_iso.png" width="85%" alt="Bassberry motherboard, KiCad 3D render"></p>

**Status: rev 0.2 (branch `feat/rev02-layout`) - HAT+ EEPROM, back-power diode, 18650 holders, functional placement, srouter routing, digital twin.**

Open `bassberry/bassberry.kicad_pro` in KiCad 10. A PDF of the schematic is in [`bassberry/bassberry_sch.pdf`](bassberry/bassberry_sch.pdf).

## Sheets

| Sheet | Content |
|---|---|
| `pi.kicad_sch` | 40-pin socket for a **face-down** Raspberry Pi (B+/2/3/4/5/Zero), I2S series termination, HAT+ ID EEPROM (CAT24C32 @ 0x50, WP jumper), back-power ideal diode |
| `audio.kicad_sch` | 2x TI TAS5805M: U201 stereo BTL (satellites, PVDD = VBAT), U202 PBTL (sub, PVDD_SUB), LC output filters, speaker connectors |
| `power.kicad_sch` | USB-C, Injoinic IP2366 PD3.1 3S buck-boost charger (30 W, 4.2 V/cell), TPS565208 5.1 V / 5 A Pi buck, optional MT3608 ~17 V sub boost, HT7533 LDOs |
| `battery.kicad_sch` | 3x 18650 in Keystone 1042 snap-in holders, off-the-shelf 3S BMS module (B-, B1, B2, B+, P-), reverse-cell LEDs, 10 A fuse, NTC |
| `ui.kicad_sch` | CH32V003 supervisor (power latch, buttons, encoder, VBAT sense, I2C slave to the Pi), OLED header, CH340C USB console |

Reference designators are numbered per sheet: 1xx Pi, 2xx audio, 3xx power, 4xx battery, 5xx UI.

## Board

* 180 x 110 mm, 4 layers, 1.6 mm. Layer roles as in srouter's rev-B3 flow: **F.Cu** signals + GND pour, **In1.Cu** signals
  (power stays on the outer layers), **In2.Cu** solid GND, **B.Cu** parts + signals + GND pour. Netclass 0.15 mm / 0.2 mm, via 0.6/0.3 mm.
* Top: face-down Pi (fitted to the Pi 4/5 hole pattern, ports over the open rear-left corner), three 18650 holders front-to-back
  with alternating polarity (series links 20 mm), USB-C at the rear, buttons / EC11 encoder / OLED socket in the front strip.
* Bottom: every other part, placed by function: each passive next to the pin it serves (`pcb_build.py`).
* Pi SoC thermal pad: covers the Pi 4 **and** the Pi 5 SoC lid (from the mechanical drawings), exposed copper both sides,
  0.3 mm GND via field, two M2.5 bolts for the aluminium pedestal. Copper keep-out under the Pi 4/5 Wi-Fi antenna corner.

## Regenerating (Windows, KiCad 10)

```powershell
powershell -File hardware\tools\regen_sch.ps1                       # schematic, ERC, netlist
& $py hardware\tools\pcb_build.py                                   # outline, placement, zones -> bassberry_placed.kicad_pcb
& $py hardware\tools\route.py                                       # srouter: escape gate, 3 passes, fatten after pass 1
powershell -File hardware\tools\postroute.ps1                       # track_tidy, fill, gnd_stitch, via_rescue, stitch_audit,
                                                                     # silk_dfm, DRC --schematic-parity, digital twin 1-4
```

Routing follows `srouter/docs/USAGE.md`: GND is never routed (planes + pours, stitched afterwards); pass 1 routes power and
everything that escapes from between power pins, pass 2 the fast nets (I2S, I2C, USB, HAT ID), pass 3 the rest.
srouter routes a net with one width that has to fit its smallest pad, so `fatten.py` widens the high-current copper after
pass 1 (necking only next to small pads, keeping an escape lane around foreign pads) and adds parallel vias at their layer changes.

## Digital twin

`hardware/twin/` - four layers, spec written only from datasheets and the Raspberry Pi documents, each with injected-fault
self-tests. See [`twin/README.md`](twin/README.md).

## Known open items (rev 0.2)

- [ ] ERC: 2 expected errors - TAS5805M PBTL pre-filter output pairing (OUT_A+/OUT_A-, OUT_B+/OUT_B-), exactly as in TI's datasheet fig. "MONO (PBTL) Systems".
- [ ] Confirm the Pi antenna keep-out on a real Pi 4 / Pi 5 / Pi 3B+.
- [ ] CH340C supply current from the current WCH datasheet (the LDO dissipation check at a 20 V PD contract uses 15 mA).
- [ ] TDSON MOSFETs: pick the final cheap part (30-40 V, ~5 mOhm, JEDEC SO-8FL pin-out).
- [ ] Device tree overlay and DSP profiles (`software/overlay`, draft).
