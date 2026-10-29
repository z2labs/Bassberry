#!/bin/bash
# freerouting-rs run 2: KiCad board in, routed KiCad board + DRC report out (reads bassberry_bench.kicad_pro/.kicad_dru next to it)
cd ~/bench
B=~/freerouting-rs/target/release/freerouting-rs
echo "start $(date -Is)"
( time $B -de bassberry_bench.kicad_pcb -do frs2.kicad_pcb+frs2.drc.json ) > frs2.log 2>&1
echo "end $(date -Is)"
tail -n 20 frs2.log
echo FRS2_DONE
