#!/bin/bash
# machine index on a VM: the CPU-only Linux srouter, ONE iteration, ONE thread, bench input (same as on the Z170 / G7)
cd ~/bench
chmod +x ./srouter-cpu-linux
DIRS="-dir F.Cu:H:2.5 -dir In1.Cu:V:2.5 -dir In2.Cu:H:2.5 -dir B.Cu:V:2.5"
for k in 1 2 3; do
  /usr/bin/time -f "real %e s" ./srouter-cpu-linux -de bassberry_bench.dsn -do /tmp/idx.ses -rules bench_rules.json -it 1 -mt 1 $DIRS > /tmp/idx.log 2>&1 || true
  grep -E "iter  1|real" /tmp/idx.log | tr '\n' ' '; echo
done
nproc; lscpu | grep -E "Model name|MHz" | head -2; uptime
echo MINDEX_DONE
