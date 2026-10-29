#!/bin/bash
# after the GPU bench: CPU-only srouter binary for the Linux VMs + the machine-index reference run on the Z170
# (machine index = wall time of ONE identical single-thread iteration on the bench input, same binary family everywhere)
set -e
cd ~/rb/srouter-gpu
source ~/.cargo/env 2>/dev/null || true
echo "== cpu-only build"; cargo build --release --target-dir target-cpu 2>&1 | tail -2
cp target-cpu/release/srouter /tmp/srouter-cpu && ls -la /tmp/srouter-cpu
cd ~/rb/bench
DIRS="-dir F.Cu:H:2.5 -dir In1.Cu:V:2.5 -dir In2.Cu:H:2.5 -dir B.Cu:V:2.5"
echo "== machine index: 1 iteration, 1 thread"
for k in 1 2 3; do
  /usr/bin/time -f "real %e s" /tmp/srouter-cpu -de bassberry_bench.dsn -do /tmp/idx.ses -rules bench_rules.json -it 1 -mt 1 $DIRS > /tmp/idx.log 2>&1 || true
  grep -E "iter  1|real" /tmp/idx.log | tr '\n' ' '; echo
done
nproc; lscpu | grep -E "Model name|MHz" | head -2
echo POST_DONE
