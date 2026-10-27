# JLCPCB fabrication + assembly files from KiCad - how to get them right the first time

Learned on Bassberry rev 0.2 (4 layers, 168 parts, both sides). Three scripts, run in this order:

```powershell
powershell -ExecutionPolicy Bypass -File jlc_fab.ps1 -Board path\to\board.kicad_pcb     # Gerber, drill, raw placement
python3 jlc_bom_cpl.py --project path\to\project                                      # BOM + CPL from netlist + lcsc_parts.csv
& "C:\Program Files\KiCad\10.0\bin\python.exe" jlc_rotfix.py --project path\to\project # fit JLC's own footprints: rotation + centre
```

Inputs per project: `<name>.kicad_pcb`, `<name>.net` (KiCad netlist), and `jlc/lcsc_parts.csv` - the part table
(`value, footprint, refs, lcsc, mpn, manufacturer, ...`), one row per schematic value + footprint.

## 1. Gerber and drill

* `kicad-cli pcb export gerbers --subtract-soldermask --no-x2 --no-netlist` with every copper layer the board has,
  paste, silk, mask, Edge.Cuts; Protel extensions (KiCad default) are what JLC expects.
* `kicad-cli pcb export drill --format excellon --excellon-units mm --excellon-separate-th --drill-origin absolute`,
  the same (absolute) origin as the Gerbers.
* Zones must be filled in the saved board (kicad-cli plots the saved fill, it does not refill).
* Look at every layer in an independent viewer before uploading (e.g. `pygerber`, rendered to PNG): planes, mask
  openings (an exposed thermal pad is a mask opening on purpose), the outline, the silkscreen.
* Remove silkscreen that would lie: the KiCad face-down Pi socket footprint draws a whole Pi Zero outline.

## 2. LCSC part numbers

* Every code is checked on its jlcpcb.com/partdetail or lcsc.com page (MPN, package, value, voltage, dielectric,
  tolerance, Basic/Extended), never from memory. The package must match the KiCad footprint (a 1206 "Basic" part does not
  go on a 1210 footprint).
* Prefer JLC Basic parts (no extended-part fee). Stock: the JLC assembly stock is what counts, and the shortfall is
  `boards x qty per board`. Out of stock -> an in-stock alternative that passes the land-pattern fit (section 4), or
  JLC global sourcing / pre-order, or consign.
* Once the owner has confirmed a part list in JLC's tool (in stock), **that list is the source of truth**: write it back
  into `lcsc_parts.csv` and regenerate; do not re-pick parts behind it.

## 3. BOM - what JLC's importer needs

* Columns `Comment, Designator, Footprint, LCSC Part #`; designators comma-separated in one cell.
* **One line per LCSC code.** Two schematic values that resolve to the same part (`100n` and `100n 50V` -> C14663) on
  two lines come back from JLC's BOM tool as "Multiple lines in the BOM have been matched to the same part", status
  Unconfirmed, quantity 0 - a page of questions. Merge them before uploading.
* Comment = the maker part number. A bare schematic value like `BT` was left unmatched by the importer.
* Write the full BOM (all sides) and one BOM + CPL pair per side. JLC's BOM page shows **one side at a time** and only
  the side(s) chosen as "PCBA side" on the PCB page: "10 parts detected" on the top meant the 158 bottom parts were on
  the other tab.
* Parts JLC does not place (DNP, solder jumpers, test points, wire pads, parts without a code) go to `not_assembled.csv`.

## 4. CPL - rotation and centre

JLC does not place the KiCad footprint, it places **its own EasyEDA footprint** of the LCSC part. Its zero orientation
and its origin differ from KiCad's for many packages (SOT-23-6, TSSOP, HTSSOP, QFN: 90 deg; LEDs, connectors: 180 deg;
the 2x20 socket and the EC11 encoder have their KiCad origin on a pin, not at the body centre). The raw KiCad .pos file
put the 18650 holders across the board and the socket 25 mm off.

`jlc_rotfix.py` does not use a correction table. For every placed part it:

1. downloads the EasyEDA footprint of the part's LCSC code (`https://easyeda.com/api/products/<C-code>/components`;
   Python's own HTTP client gets 403 - use `curl`; the API throttles bursts with an HTML 403 page - retry with a delay;
   results are cached in `jlc/easyeda_cache/`),
2. fits it onto the board's pads, trying 0/90/180/270 deg: by pin number where most pins share numbers (the
   translation most pin pairs agree on, position = median of the pin translations, so an exposed pad numbered
   differently or a tab anchored off its centre does not drag it), by geometry otherwise (sockets, A/B/C pins),
3. does the same fit with KiCad's own library footprint,
4. writes `rotation = KiCad .pos rotation + (JLC footprint angle - KiCad footprint angle)` and the position of JLC's
   footprint origin. Bottom side: both footprints are mirrored (seen from the top); KiCad 10's .pos rotation for bottom
   parts is the top-view angle + 180 (verified on all 158 bottom parts), so the same formula holds.
5. **Land-pattern check** from the same fit: every JLC pad centre must land on copper of that footprint. It flagged
   the MYOUNG BH-18650-B1BA002 18650 holder (C2988620) on the Keystone 1042 footprint: JLC's model has its pads at
   82.6 mm, the Keystone footprint at 79.4 mm. Check every substitute picked in JLC's tool this way before accepting it.
6. **When the part changes, the footprint follows the maker's drawing, not JLC's model.** The BH-18650-B1BA002
   drawing (WD-CP-0088) gives 7.77 x 7.35 mm pads 79.26 mm apart and a D2.40 locating-peg hole; JLC's model has small
   pads at the tab tips (82.6 mm) - both land inside the drawing's pads. Number the pads like JLC's model (here
   1 = '-', 2 = '+'), so the fit by pin number cannot turn a polarised or pegged part 180 deg; the schematic follows
   the footprint numbering. Project footprints live in `<project>/<lib>.pretty` + `fp-lib-table`; `pcb_build.py` and
   `jlc_rotfix.py` look there before the KiCad library.

The report (`jlc/rotfix_report.csv`) lists per part: LCSC code, JLC footprint name, KiCad rotation, JLC rotation,
position, fit rms, how it was matched, verdict. Still look at JLC's placement preview (both sides) and at the DFM
report JLC sends after the order.

## 5. Order page

* PCB: layers, thickness, copper weights as designed (outer 1 oz / inner 0.5 oz is JLC's standard 4-layer stack-up).
* PCBA side: Top, Bottom or Both - must match the BOM/CPL uploaded. Large through-hole top parts (holders, switches,
  encoder, headers) are cheaper to hand-solder than to pay for second-side assembly.
* Re-match within 24 h of ordering (JLC's note): stock and prices move.

## 6. DFM - check what JLC checks, before uploading

KiCad's DRC can be clean (0 errors) while JLC's DFM report is red: DRC checks clearance between **different** nets,
round-hole minimums and silkscreen as a warning; JLC checks the Gerbers geometrically. Found on Bassberry rev 0.2:

| JLC DFM item (Danger) | cause | fix in the flow |
|---|---|---|
| Via to pad 0 mm, pad spacing 0.04 mm | router ends a track in a via whose ring overlaps an SMD pad of the same net | DSN keep-outs over SMD pads on a closed inner plane (srouter blocks vias in any keep-out layer); `via_off_pad.py` moves the rest; via placement in pours/stitching checks `off_pads` |
| Slot width 0.6 mm | KiCad USB-C footprint shell slots | widen plated slots to 0.7 mm (pad grows with the drill) |
| Silkscreen to hole 0 mm | silk lines/text over **via** holes (tented vias count) | `silk_dfm.py --fix` treats via holes as obstacles |
| Silkscreen to pad 0 mm | silk clipped by `--subtract-soldermask` ends right at the mask opening | `silk_dfm.py --fix`, 0.15 mm |
| THT to SMD 1.69 mm | SMD parts near through-hole pins (selective/wave solder) | warning; keep 2 mm where the THT part is machine-soldered |

The check that reproduces these on the board before any Gerber is written: `twin_dfm.py` (Bassberry twin layer 5) /
`jlc_dfm_check.py` (srouter tools) - via ring to any SMD pad (own net too) >= 0.10 mm (warn < 0.15), pads of different
parts >= 0.10 mm, plated slots >= 0.65 mm, silk >= 0.15 mm from mask openings and from every drilled hole; warnings for
via rings < 0.15 mm, short slots, THT pads < 2 mm from SMD pads. On the board JLC rejected it flagged exactly JLC's
Danger categories. Thresholds: jlcpcb.com/capabilities/pcb-capabilities and the JLCDFM report itself.
