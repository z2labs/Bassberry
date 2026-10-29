cd ~/rb/bench
export LD_LIBRARY_PATH=$HOME/rb/ortho-venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib:$HOME/rb/ortho-venv/lib/python3.12/site-packages/nvidia/cuda_runtime/lib:$LD_LIBRARY_PATH
SR=~/rb/srouter-gpu/target/release/srouter
DIRS="-dir F.Cu:H:2.5 -dir In1.Cu:V:2.5 -dir In2.Cu:H:2.5 -dir B.Cu:V:2.5"
pkill -f "srouter -de" 2>/dev/null; sleep 1
echo "== A: pass1b DSN (flow rules, big power windows), CPU only, 4 threads"
( time nice -n 10 $SR -de pass1b_local.dsn -do p1b_cpu.ses -rules pass1b_local_rules.json -it 30 -stall 10 $DIRS ) > p1b_cpu.log 2>&1
grep -E "iter|stall|profile|routed" p1b_cpu.log | tail -8; grep real p1b_cpu.log
echo "== B: same, GPU for windows >= 1.5M nodes"
( time nice -n 10 $SR -de pass1b_local.dsn -do p1b_gpu.ses -rules pass1b_local_rules.json -it 30 -stall 10 -gpu 1500000 $DIRS ) > p1b_gpu.log 2>&1
grep -E "^gpu|iter|stall|profile|routed" p1b_gpu.log | tail -10; grep real p1b_gpu.log
echo "== C: GPU check mode on the bench DSN, 2 iterations (cost parity + per-connection times)"
( time nice -n 10 $SR -de bassberry_bench.dsn -do chk.ses -rules bench_rules.json -it 2 -gpu 1 -gpu-check $DIRS ) > chk.log 2>&1
python3 - <<'EOF'
import re
rows=[]
for l in open("chk.log"):
    m=re.search(r"gpucmp net=(\S+) nodes=(\d+) cpu_cost=(\S+) cpu_exp=(\d+) cpu_us=(\d+) gpu_cost=(\S+) gpu_us=(\S+)",l)
    if m: rows.append(m.groups())
ok=sum(1 for r in rows if r[2]!="none" and r[5]!="none" and abs(float(r[2])-float(r[5]))<=0.02*float(r[2])+0.6)
both_none=sum(1 for r in rows if r[2]=="none" and r[5]=="none")
worse=[r for r in rows if r[2]!="none" and r[5]!="none" and float(r[5])>float(r[2])*1.02+0.6]
better=[r for r in rows if r[2]!="none" and r[5]!="none" and float(r[5])<float(r[2])*0.98-0.6]
miss=[r for r in rows if (r[2]=="none")!=(r[5]=="none")]
cu=sum(int(r[4]) for r in rows); gu=sum(int(r[6]) for r in rows if r[6]!="-")
print(f"connections {len(rows)}: same optimum {ok}, both none {both_none}, gpu worse {len(worse)}, gpu better {len(better)}, mismatch none {len(miss)}")
print(f"cpu total {cu/1e6:.2f} s, gpu total {gu/1e6:.2f} s (small windows, median nodes {sorted(int(r[1]) for r in rows)[len(rows)//2] if rows else 0})")
for r in worse[:5]: print("  worse", r)
for r in miss[:5]: print("  miss", r)
EOF
echo BENCH_DONE
