# Bill of materials (draft)

Design rule: **cheap and easy to get**. Every electronic part should be stocked at LCSC / common distributors, and the mechanical parts should be printable or generic.
Prices are rough single-unit estimates (October 2026) and will change. *(tbc)* = to be confirmed in the schematic phase.

## Electronics

| Block | Part (proposal) | Qty | Why |
|---|---|---|---|
| Satellite amp | TI TAS5805M | 1 | I2S DAC + class-D + DSP in one chip, cheap, existing open Linux driver |
| Sub amp | TI TAS5805M (PBTL) | 1 | same part, so one footprint and one driver |
| PD sink + 3S charger | power-bank SoC, e.g. IP2368 *(tbc)* | 1 | one chip for PD input and 2–6S buck-boost charging, mass-market part |
| Pack protection | 3S protection IC + cell balancers *(tbc)* | 1 set | cheap, standard power-bank parts |
| 5.1 V / 5 A buck | synchronous buck, ~500 kHz | 1 | enough for a Pi 5 |
| 18 V boost (optional) | 3–4 A switch boost *(tbc)* | 1 | footprint present, can stay unfitted |
| Supervisor MCU | WCH CH32V003 | 1 | costs a few cents, handles buttons, encoder and power latch |
| USB-UART | WCH CH340 class | 1 | serial console over the same USB-C port |
| Display | 1.3" I2C OLED module, 4-pin | 1 | everywhere, ≈ 2–3 |
| Encoder | EC11 with push switch | 1 | |
| Buttons | 6 × 6 mm tact switches | 5 | |
| 2×20 socket | standard 8.5 mm female header | 1 | |
| Battery clips | Keystone 54 (or generic 18650 clips) | 6 | snap-in, through-hole |
| Thermal | aluminium block 24 × 24 × 6.7 mm + 1.5–2 mm gap pad | 1 | cut from bar stock, or a generic Pi heatsink |

## Acoustics

| Role | Reference (simulated) | Approx. price | Budget option |
|---|---|---|---|
| Satellites | 2× Dayton CE54N-4 | ≈ 12 each | generic 2" 4 Ω full-range, 52–54 mm frame |
| Sub | 1× Dayton ND91-4 | ≈ 28 | generic 3–3.5" long-throw BT-speaker woofer |
| Passive radiators | 2× Dayton DMA70-PR | ≈ 12 each | generic 2.5" rubber passive radiators (tune with added mass) |

The sub is where cheap parts hurt most. See the comparison in [acoustics.md](acoustics.md).
With generic drivers, measure their T/S parameters and re-run `acoustics/sim.py`.

## Mechanical

* Printed enclosure (PETG recommended), 2.5 mm walls, 100 % infill around the driver baffles, gasket on the acoustic divider
* Polyester fill in the satellite chambers
* 4 rubber feet, 18 mm (sub clearance)
* M2.5 hardware for the Pi, M3 for the enclosure
* Perforated metal or printed front grille
