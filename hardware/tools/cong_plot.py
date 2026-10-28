"""Plot srouter's congestion map (-congmap JSON): demand / capacity per gcell, H and V pools, overflowing cells with
the nets through them. Run before detailed routing: an overflowing gcell is a placement problem.

usage: python cong_plot.py route/pass1b_local_cong.json [out.png] [--board route/x.kicad_pcb]   (plain python)"""
import sys, json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main(path, out=None):
    d = json.load(open(path, encoding="utf-8"))
    cnx, cny, cm = d["cnx"], d["cny"], d["cell_mm"]
    x0, y0 = d["x0_mm"], d["y0_mm"]
    pools = d["pools"]
    panels = [("H", "cap_h", "use_h"), ("V", "cap_v", "use_v")] if pools == ["H", "V"] else [("all", "cap_h", "use_h")]
    fig, axs = plt.subplots(1, len(panels), figsize=(8 * len(panels), 6.5), squeeze=False)
    for ax, (name, ck, uk) in zip(axs[0], panels):
        cap = np.array(d[ck]).reshape(cny, cnx); use = np.array(d[uk]).reshape(cny, cnx)
        ratio = np.where(cap > 0.05, use / np.maximum(cap, 0.05), np.where(use > 0, 9.0, np.nan))
        im = ax.imshow(ratio, origin="upper", cmap="RdYlGn_r", vmin=0, vmax=1.5,
                       extent=(x0, x0 + cnx * cm, -(y0 + cny * cm), -y0))
        ax.set_title(f"{name} pool: demand / capacity  ({cm:.1f} mm gcells, {d['iterations']} global iterations)")
        ax.set_xlabel("x (mm, DSN)"); ax.set_ylabel("y (mm, DSN; up)")
        plt.colorbar(im, ax=ax, fraction=0.03, label="demand / capacity (1 = full)")
    over = d.get("over", [])
    for o in over:
        for ax in axs[0]:
            ax.add_patch(plt.Rectangle((x0 + o["i"] * cm, -(y0 + (o["j"] + 1) * cm)), cm, cm, fill=False, ec="black", lw=1.2))
    fig.suptitle(f"{os.path.basename(path)}: {len(over)} overflowing gcells", fontsize=12)
    plt.tight_layout()
    out = out or path.replace(".json", ".png")
    plt.savefig(out, dpi=110)
    # worst cells with their nets
    over.sort(key=lambda o: -max(o["use_h"] - o["cap_h"], o["use_v"] - o["cap_v"]))
    print(f"{len(over)} overflowing gcells ({cm:.1f} mm), pools {pools}")
    for o in over[:12]:
        worst = "H" if o["use_h"] - o["cap_h"] >= o["use_v"] - o["cap_v"] else "V"
        print(f"  ({o['x_mm']:6.1f},{o['y_mm']:6.1f}) {worst}: {o['use_'+worst.lower()]:.1f} of {o['cap_'+worst.lower()]:.1f}  "
              f"{len(o['nets'])} nets: {', '.join(o['nets'][:8])}{' ...' if len(o['nets']) > 8 else ''}")
    print("wrote", out)
    return len(over)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        print(__doc__); sys.exit(2)
    main(a[0], a[1] if len(a) > 1 else None)
