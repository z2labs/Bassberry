"""Compare driver sets in the same Bassberry enclosure (runs sim.py per config)."""
import os, re, json, tempfile
import numpy as np
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(HERE, "sim.py")).read()

DRV = {
    "TEBM35C10-4": 'dict(name="TEBM35C10-4", Re=4.2, Le=0.05e-3, Bl=2.03, Mms=1.11e-3, Cms=1.04e-3, Rms=0.27, Sd=11.04e-4, Xmax=2.5e-3, Pmax=10.0)',
    "CE54N-4":     'dict(name="CE54N-4", Re=3.6, Le=0.11e-3, Bl=3.82, Mms=2.4e-3, Cms=0.37e-3, Rms=0.37, Sd=14.5e-4, Xmax=1.4e-3, Pmax=15.0)',
    "ND91-4":      'dict(name="ND91-4", Re=4.3, Le=0.83e-3, Bl=4.59, Mms=4.8e-3, Cms=0.96e-3, Rms=0.53, Sd=30.4e-4, Xmax=4.6e-3, Pmax=30.0)',
    "PC83-4":      'dict(name="PC83-4", Re=3.9, Le=0.38e-3, Bl=2.9, Mms=2.7e-3, Cms=1.47e-3, Rms=0.4, Sd=30.2e-4, Xmax=2.0e-3, Pmax=30.0)',
}
# rough single-unit street prices (EUR/USD mixed, Oct 2026 web listings)
PRICE = {"TEBM35C10-4": 14.9, "CE54N-4": 12.3, "ND91-4": 28.0, "PC83-4": 15.0, "DMA70-PR": 12.0}

CONFIGS = [
    ("A  reference", "TEBM35C10-4", "ND91-4"),
    ("B  budget sats", "CE54N-4", "ND91-4"),
    ("C  budget all", "CE54N-4", "PC83-4"),
]


def run(sat, sub):
    src = re.sub(r"SAT = dict\(.*?\)\n", f"SAT = {DRV[sat]}\n", SRC, count=1, flags=re.S)
    src = re.sub(r"SUB = dict\(.*?\)\n", f"SUB = {DRV[sub]}\n", src, count=1, flags=re.S)
    g = {"__name__": "sim_cfg"}
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(src, "sim.py", "exec"), g)
        os.chdir(cwd)
    plt.close("all")
    return g


res = {}
for label, sat, sub in CONFIGS:
    g = run(sat, sub)
    cost = 2 * PRICE[sat] + PRICE[sub] + 2 * PRICE["DMA70-PR"]
    res[label] = dict(g=g, sat=sat, sub=sub, cost=cost)

INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
COL = ["#2a78d6", "#eb6834", "#1baf7a"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.facecolor": SURF, "figure.facecolor": SURF})


def style(ax, ylab, ylim):
    ax.set_xscale("log"); ax.set_xlim(30, 2000); ax.set_ylim(*ylim)
    ax.grid(True, which="both", color=GRID, lw=0.6)
    ax.set_xticks([30, 50, 100, 200, 500, 1000, 2000]); ax.set_xticklabels(["30", "50", "100", "200", "500", "1k", "2k"])
    ax.set_xlabel("Frequency (Hz)"); ax.set_ylabel(ylab)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)


fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
rows = []
for (label, r), c in zip(res.items(), COL):
    g = r["g"]; f = g["f"]
    ref = g["ref"]; mid = g["mid"]
    name = f'{label}: 2x {r["sat"]} + {r["sub"]}'
    axs[0].plot(f, ref + 85 - mid, color=c, lw=2, label=name)
    axs[1].plot(f, g["spl_max_nom"], color=c, lw=2, label=name)
    s = g["summary"]
    rows.append(dict(config=label, sat=r["sat"], sub=r["sub"], drivers_cost=round(r["cost"]),
                     f3=round(s["system"]["f_minus3_hz"]), sat_trim_db=s["sat_trim_db"],
                     flat_max=s["flat_max_spl_db_1m"],
                     max60=s["max_spl_db_1m_nominal_pvdd"]["60"], max100=s["max_spl_db_1m_nominal_pvdd"]["100"],
                     max1k=s["max_spl_db_1m_nominal_pvdd"]["1000"], sat_fc=s["sat"]["fc_hz"], sat_qtc=s["sat"]["Qtc"]))
style(axs[0], "SPL @ 1 m (dB), normalised", (55, 95)); axs[0].set_title("Response with DSP", loc="left", color=INK, fontsize=11)
style(axs[1], "Max SPL @ 1 m (dB)", (60, 105)); axs[1].set_title("Maximum output (18 V sub rail)", loc="left", color=INK, fontsize=11)
axs[1].legend(frameon=False, loc="lower right", fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "05_driver_comparison.png"), dpi=160)
json.dump(rows, open(os.path.join(HERE, "comparison.json"), "w"), indent=2)
print(json.dumps(rows, indent=2))
