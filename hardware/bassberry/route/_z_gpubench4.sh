#!/bin/bash
# test B again after the lazy-sync fix (gpu.rs / router.rs), then the machine index. Output: ~/rb/z_gpubench4.out
cd ~/rb/srouter-gpu
source ~/.cargo/env 2>/dev/null || true
tar xzf /tmp/gpu_fix_0129c.tgz -C src && md5sum src/router.rs src/gpu.rs
echo "== build (cuda)"; cargo build --release --features cuda 2>&1 | grep -E "^error|warning: unused|Finished" | tail -3
cd ~/rb/bench
export LD_LIBRARY_PATH=$HOME/rb/ortho-venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib:$HOME/rb/ortho-venv/lib/python3.12/site-packages/nvidia/cuda_runtime/lib:$LD_LIBRARY_PATH
SR=~/rb/srouter-gpu/target/release/srouter
DIRS="-dir F.Cu:H:2.5 -dir In1.Cu:V:2.5 -dir In2.Cu:H:2.5 -dir B.Cu:V:2.5"
echo "== B: pass1b DSN, GPU only on fallback searches (corridor-less / whole-board), windows >= 1.5M nodes"
( time nice -n 10 $SR -de pass1b_local.dsn -do p1b_gpu4.ses -rules pass1b_local_rules.json -it 30 -stall 10 -gpu 1500000 $DIRS ) > p1b_gpu4.log 2>&1
grep -E "^gpu|stall|profile|routed .* nets|^  !|real" p1b_gpu4.log | tail -10
echo "== machine index (CPU-only build, 1 iteration, 1 thread, bench DSN) x3"
cd ~/rb/srouter-gpu && cargo build --release --target-dir target-cpu 2>&1 | grep -E "^error|Finished" | tail -1
cp target-cpu/release/srouter /tmp/srouter-cpu
cd ~/rb/bench
for k in 1 2 3; do
  /usr/bin/time -f "real %e s" /tmp/srouter-cpu -de bassberry_bench.dsn -do /tmp/idx.ses -rules bench_rules.json -it 1 -mt 1 $DIRS > /tmp/idx.log 2>&1 || true
  grep -E "iter  1|real" /tmp/idx.log | tr '\n' ' '; echo
done
nproc; lscpu | grep -E "Model name" | head -1
echo BENCH2_DONE
