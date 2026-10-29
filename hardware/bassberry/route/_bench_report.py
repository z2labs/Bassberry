"""Router benchmark table with machine normalisation.

Quality columns are hardware-independent (same board, same KiCad DRC). Time is normalised two ways:
  * machine index  = seconds of ONE identical single-thread srouter iteration on the bench input on that machine
                     (G7 = 1.0); normalised time = wall time / (index / index_G7) -> "G7-equivalent seconds"
  * CPU-vs-GPU speed-up is only ever taken on the SAME machine (Z170 test A vs B), so it needs no index.
Fill MACHINE_INDEX from _bench_mindex.ps1 (G7), _z_gpubench2.sh (Z170), _vm_mindex.sh (VMs).

usage: python _bench_report.py            (reads bench/results.jsonl)
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
MACHINE_INDEX = {   # seconds, 1 iteration, 1 thread, bench DSN (median of 3)
    "G7": 25.6,          # i7-10510U, Windows, another router running concurrently
    "Z170": None,        # filled from z_gpubench2.out
    "rb-frs-VM": None,   # Hyper-V VM on the T610 (2x Xeon E5649), 2 vCPU
    "rb-pcbworld-VM": None,
}


def main():
    rows = [json.loads(l) for l in open(os.path.join(HERE, "bench", "results.jsonl"), encoding="utf-8") if l.strip()]
    g7 = MACHINE_INDEX["G7"]
    print(f"{'router / run':28} {'machine':14} {'wall s':>7} {'G7-eq s':>8} {'nets ok':>8} {'unconn':>6} {'vias':>5} {'mm':>6} {'DRC(route)':>10} {'iters':>5}")
    for r in rows:
        idx = MACHINE_INDEX.get(r.get("machine", ""), None)
        eq = (r["time_s"] / (idx / g7)) if (idx and r.get("time_s")) else None
        nets_ok = r["nets_total"] - 1 - r["drc"]["unconnected"]   # rough: items not nets; GND excluded
        print(f"{r['name']:28} {r.get('machine',''):14} {r['time_s'] or 0:7.0f} {eq if eq else 0:8.0f} "
              f"{str(r['nets_total']) + '-' + str(r['drc']['unconnected']):>8} {r['unconnected']:6} {r['vias']:5} {r['track_mm_total']:6} "
              f"{r['drc']['routing']:10} {r.get('iters') or '':>5}")
    print("\nnote:", {k: v for k, v in MACHINE_INDEX.items()})


if __name__ == "__main__":
    main()
