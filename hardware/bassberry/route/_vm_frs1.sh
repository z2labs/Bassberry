#!/bin/bash
# freerouting-rs run 1 (restart): corrected bench DSN (0.15 mm clearance like the flow) -> SES + DRC report
cd ~/bench
pkill -f "freerouting-rs -de bassberry_bench.dsn" && echo "stopped frs1 on the 0.2 mm DSN"; sleep 1
md5sum bassberry_bench.dsn; grep -m2 "(clearance" bassberry_bench.dsn
B=~/freerouting-rs/target/release/freerouting-rs
echo "start $(date -Is)"
( time $B -de bassberry_bench.dsn -do frs1.ses+frs1.drc.json ) > frs1.log 2>&1
echo "end $(date -Is)"
tail -n 20 frs1.log
echo FRS1_DONE
