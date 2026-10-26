# HAT+ ID EEPROM

Bassberry identifies itself to the Raspberry Pi as a **HAT+** (Raspberry Pi HAT+ specification, `raspberrypi/hats`).
At boot the Pi firmware reads the EEPROM on ID_SD/ID_SC (header pins 27/28, GPIO0/GPIO1), and then:

* loads the device tree overlay named in `dt_blob` (`bassberry` → `/boot/firmware/overlays/bassberry.dtbo`),
* on a Pi 5, reads `current_supply` (5000 mA) and allows full USB current while the Pi is powered from the header.

| File | What |
|---|---|
| `bassberry_eeprom.txt` | source settings (vendor, product, UUID, current supply, overlay name) |
| `bassberry.eep` | ready-to-flash 104-byte image, built with `eepmake` from [raspberrypi/utils](https://github.com/raspberrypi/utils/tree/master/eeptools) |
| `../overlay/bassberry-overlay.dts` | the overlay the EEPROM points to (draft) |

## Circuit (hardware sheet `pi`, as in the HAT design guide)

* U101 **CAT24C32** (32 kbit, 16-bit addressing), address **0x50** (A0..A2 = GND).
* 3.9 kΩ pull-ups on ID_SD/ID_SC, nothing else on those two lines.
* WP pulled up with 1 kΩ → **write-protected** by default. To write: bridge solder jumper **JP101**
  (or hold test point **TP101** to GND).

## Flashing (on the Pi, once per board)

```sh
sudo apt install raspi-utils         # eepmake, eepdump, eepflash.sh
# /boot/firmware/config.txt: add  dtparam=i2c_vc=on   (exposes ID_SD/ID_SC as /dev/i2c-0), reboot
# bridge JP101
sudo eepflash.sh -w -f=bassberry.eep -t=24c32 -a=50
# remove the JP101 bridge, remove dtparam=i2c_vc=on, reboot
cat /proc/device-tree/hat/product        # -> Bassberry 2.1 speaker
```

Rebuild the image after editing the settings: `eepmake bassberry_eeprom.txt bassberry.eep`.

## Back-powering

The board powers the Pi through the 5 V header pins. As required by the HAT design guide for boards that use more than
the first 26 pins, a **back-power ideal diode** (PFET + matched dual PNP, guide's `zvd-circuit`) sits between the board's
5.1 V buck (`+5V_BUCK`) and the Pi 5 V net, so plugging in the Pi's own supply at the same time is safe.
The PFET is a DMP3013SFV (13 mΩ, PowerDI3333-8) instead of the guide's DMG2305UX, because the Pi 5 needs 5 A.
