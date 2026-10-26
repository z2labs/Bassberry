# Battery: 3S 18650, new or harvested cells

Bassberry uses three 18650 cells in series (3S, 9.0–12.6 V), held by snap-in holders with spring metal contacts (Keystone 1042 or compatible) on the motherboard. No spot welding is needed, and cells can be swapped.
That makes it easy to reuse cells from old laptop packs. Li-ion stores a lot of energy, though, so please follow these rules.

## Choosing cells

1. **Inspect.** Skip any cell with a dented can, torn wrap, corrosion or a missing top insulator ring. Re-wrap cells with damaged wraps.
2. **Rest voltage.** Discard cells that were sitting below ~2.0 V. Charge the rest individually to 4.2 V and let them rest for a week. A cell that drops more than ~0.1 V in that time self-discharges and is out.
3. **Capacity and internal resistance.** Measure each cell with a hobby charger/analyzer. Use cells **within ±5 % capacity** of each other and with similar internal resistance (preferably below ~80 mΩ).
4. **Match voltage before inserting.** All three cells should be within **±50 mV** of each other when they go into the clips.
5. Use the same model of cell for all three positions when you can.

## What the board does for you

| Protection | How |
|---|---|
| Over-charge / over-discharge per cell | 3S protection IC, cuts the pack off |
| Cell balancing | passive balancing on each cell while charging |
| Over-current / short | protection IC current sense + 10 A fuse |
| **Reverse-inserted cell** | a small LED at each slot lights **only** when that cell is backwards, the sense inputs are clamped, and charging/discharging is blocked on fault |
| Temperature | NTC on the middle cell, no charging above 45 °C |
| Clean shutdown | the supervisor MCU warns the Pi and shuts it down before the pack is empty |

## Inserting the cells

* Follow the **+ / −** silkscreen at every slot. Check that no reverse LED is lit **before** closing the case.
* Insert or remove cells only with the speaker switched off and USB-C unplugged.
* Store the speaker at around 40–60 % charge if you are not using it for weeks.

## Shipping

If you sell or ship Bassberry with cells fitted, Li-ion transport rules apply (UN38.3 for the cells, carrier-specific packaging rules).
The simplest way is to ship it without cells.
