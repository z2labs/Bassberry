# Architecture

> Pre-schematic plan. Part numbers marked *(tbc)* still need a datasheet check before they go into the schematic.

## Mechanical stack

```
 ┌───────────────────────── top cover: buttons, encoder, OLED window ─┐
 │  Raspberry Pi (upside down)        3S 18650 in metal clips         │  electronics deck
 │  └ SoC → gap pad → Al pedestal → 4-layer GND via field             │
 │════════════════ motherboard (≈180 × 110 mm, 4 layers) ═════════════│
 │  bottom side: amps, charger, buck/boost, bulk caps, MCU            │
 ├────────────────── airtight divider ────────────────────────────────┤
 │ [sat L 0.2 l]        sub chamber 1.5 l             [sat R 0.2 l]   │  acoustic section
 │  PR ◄                  sub fires down                     ► PR     │
 └────────────────────────────────────────────────────────────────────┘
```

* The Pi plugs into a standard 2×20 female socket, component side down. Its SoC presses through a 1.5–2 mm gap pad onto an aluminium pedestal bolted through the board into a dense GND via field (exposed ENIG, no soldermask). The soft pad absorbs the SoC height differences between Pi models.
* A notch in the board edge leaves room for the USB/Ethernet block of B-size Pis, and those ports stay reachable from the back of the enclosure.
* The Zero / Zero W / Zero 2 W use the same header and the top two HAT mounting holes. A second, smaller pedestal position is planned for their SoC location.
* The Pi's on-board Wi-Fi/BT antenna gets a copper keep-out (all layers) or a board cut-out underneath.

## Host compatibility

| Pi | Supported | Notes |
|---|---|---|
| 1 A / B (26-pin) | No | No I2S on the 26-pin header |
| 1 A+ / B+, 2, 3, 3 B+, 4, 5 | Yes | 58 × 49 mm hole pattern, same 40-pin position |
| Zero / Zero W / Zero 2 W | Yes | Built-in BT on W / 2 W and Pi 3/4/5. Older models need a USB BT dongle. |

## Power

| Rail | Source | Load | Notes |
|---|---|---|---|
| VBUS | USB-C, PD sink 5–20 V | charger input | Prefers 15 V, then 20 V, then 9 V. 5 V also charges, just slowly. |
| VBAT / VSYS | 3S Li-ion, 9.0–12.6 V | satellite amp PVDD, buck, boost | power-bank-class PD + 3S buck-boost SoC, e.g. IP2368 *(tbc)* |
| 18 V (optional) | boost from VBAT | sub amp PVDD | +3.4 dB bass, battery-independent. Jumper to VBAT when not fitted. |
| 5.1 V / 5 A | synchronous buck | Raspberry Pi via GPIO 5 V pins | Ideal-diode output stage blocks back-feed from the Pi's own USB input. Pi 5: `usb_max_current_enable=1` |
| 3.3 V | LDO | supervisor MCU, OLED | always-on, µA standby |

* Bulk capacitance on PVDD: 2–4× 470–1000 µF low-ESR. The battery itself handles bass transients.
* Pack protection: 3-cell OV/UV/OC protection with cell balancing, a 10 A fuse, and an NTC on the middle cell (no charging above 45 °C).
* Pi 5: set `POWER_OFF_ON_HALT=1` in the EEPROM so a halted Pi does not drain the pack.

## Audio

* I2S from the Pi (BCLK GPIO18, LRCLK GPIO19, DOUT GPIO21) to two TAS5805M daisy-chained as one 2.1 sound card. An existing open-source Linux driver supports this setup.
  * #1: satellites, stereo BTL, PVDD = VBAT
  * #2: sub, PBTL mono, PVDD = 18 V boost (or VBAT)
* DSP profiles (crossover, EQ, DRC) live in the amps, so the Pi does no audio processing. This works the same on a Pi Zero and a Pi 5.

## Control and UI

| Function | Connection |
|---|---|
| OLED 1.3" 128×64 (SH1106/SSD1306) | I2C1 (GPIO2/3), 4-pin header, mounted behind the front window |
| Buttons: power, BT, play/pause, vol−, vol+ | Supervisor MCU |
| Rotary encoder EC11 with push | Supervisor MCU |
| Supervisor MCU (e.g. CH32V003) | I2C slave to the Pi plus an IRQ line. Runs the power latch, soft shutdown handshake, battery monitoring and charger status. Works while the Pi is off. |
| Serial console | USB-UART (CH340-class) on the D+/D− of the same USB-C connector, wired to the Pi UART (GPIO14/15) |
| Amp control | PDN on GPIO4 (#1) / GPIO5 (#2), shared FAULT to the MCU |

One USB-C cable both charges the speaker and gives a serial console to any Pi model.
