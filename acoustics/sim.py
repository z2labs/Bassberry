"""Bassberry 2.1 - lumped-element acoustic simulation.

Satellites : 2x Dayton CE54N-4 in sealed chambers (alt: Tectonic TEBM35C10-4 BMR)
Sub        : 1x Dayton DMA70-4 + 2x Dayton DMA70-PR (opposed, side walls)
Amp        : TAS5825M (2x BTL, sats) + TAS5805M (PBTL, sub), PVDD = 3S Li-ion
DSP        : LR4 crossover, Linkwitz transform on sats, subsonic HPF + shelf on sub

Model: single-frequency linear solve of the electro-mechano-acoustic network,
far field at 1 m. Valid roughly 20 Hz - 1 kHz (piston, no cone breakup, no
diffraction detail beyond a first-order baffle-step shelf).
"""
import json
import numpy as np
import matplotlib.pyplot as plt

RHO, C = 1.18, 343.0
RC2 = RHO * C * C
P_REF = 20e-6
f = np.logspace(np.log10(20), np.log10(2000), 600)
w = 2 * np.pi * f
s = 1j * w

# ---------------------------------------------------------------- drivers
SAT = dict(name="CE54N-4", Re=3.6, Le=0.11e-3, Bl=3.82, Mms=2.4e-3,
           Cms=0.37e-3, Rms=0.37, Sd=14.5e-4, Xmax=1.4e-3, Pmax=15.0)
# alternative (wider dispersion BMR): TEBM35C10-4, see compare.py
SUB = dict(name="ND91-4", Re=4.3, Le=0.83e-3, Bl=4.59, Mms=4.8e-3,
           Cms=0.96e-3, Rms=0.53, Sd=30.4e-4, Xmax=4.6e-3, Pmax=30.0)
PR = dict(name="DMA70-PR", Mms=12.0e-3, Cms=1.77e-3, Rms=1.49, Sd=22.9e-4,
          Xmax=6.0e-3, n=2)          # Xmech 7 mm, 6 mm used as limit

# ---------------------------------------------------------------- enclosure
ENC = dict(outer_mm=(230, 120, 140), wall_mm=2.5)
VB_SAT = 0.20e-3       # net per satellite chamber (56 x 78 x 50 mm, minus driver)
VB_SUB = 1.50e-3       # net sub volume (centre column + rear wings, -15 % for parts/ribs)
QL = 7.0               # box leakage Q (well sealed printed box)
BAFFLE_W = 0.230       # m, front baffle width -> baffle step

# ---------------------------------------------------------------- amplifier
PVDD_NOM, PVDD_MIN = 11.1, 9.6        # 3S nominal / near-empty under load (satellite amp)
PVDD_SUB = 18.0                       # boosted rail for the sub amp (TAS5805M PBTL)
def v_rms_max(pvdd):                   # BTL/PBTL full-bridge, ~5 % headroom
    return 0.95 * pvdd / np.sqrt(2)


def fs_of(d):
    return 1 / (2 * np.pi * np.sqrt(d["Mms"] * d["Cms"]))


def solve(drv, Vb, pr=None, V=1.0):
    """Return dict of complex responses per 1 V(rms) drive."""
    Ze = drv["Re"] + s * drv["Le"]
    Zm = drv["Rms"] + s * drv["Mms"] + 1 / (s * drv["Cms"])
    Cab = Vb / RC2
    wb = 2 * np.pi * (fs_of(drv) if pr is None else 60.0)
    Ral = QL / (wb * Cab)
    Yab = s * Cab + 1 / Ral            # box admittance: p = -dV_dot / Yab
    out = {k: np.zeros_like(f, dtype=complex) for k in ("i", "vd", "vp", "p")}
    for k in range(len(f)):
        # unknowns: i, vd, vp, p
        n = 4 if pr else 3
        A = np.zeros((n, n), complex)
        b = np.zeros(n, complex)
        # electrical: Ze i + Bl vd = V
        A[0, 0], A[0, 1], b[0] = Ze[k], drv["Bl"], V
        # driver mech: Bl i + p Sd - Zm vd = 0
        A[1, 0], A[1, 1], A[1, n - 1] = drv["Bl"], -Zm[k], drv["Sd"]
        # box: Yab p + Sd vd + Sp_tot vp = 0
        A[n - 1, n - 1], A[n - 1, 1] = Yab[k], drv["Sd"]
        if pr:
            Sp = pr["Sd"] * pr["n"]
            Zmp = pr["Rms"] + s[k] * pr["Mms"] + 1 / (s[k] * pr["Cms"])
            A[n - 1, 2] = Sp
            # PR mech (per PR, all identical): p Sp1 - Zmp vp = 0
            A[2, 2], A[2, 3] = -Zmp, pr["Sd"]
        x = np.linalg.solve(A, b)
        out["i"][k], out["vd"][k] = x[0], x[1]
        out["p"][k] = x[-1]
        if pr:
            out["vp"][k] = x[2]
    U = drv["Sd"] * out["vd"] + (pr["Sd"] * pr["n"] * out["vp"] if pr else 0)
    out["U"] = U
    out["xd"] = out["vd"] / s
    out["xp"] = out["vp"] / s if pr else None
    out["Z"] = V / out["i"]
    return out


def p_far(U, r=1.0):
    """4pi far-field pressure + first-order baffle-step shelf (4pi -> 2pi)."""
    fbs = 115.0 / BAFFLE_W
    shelf = (1 + s / (2 * np.pi * fbs)) / (1 + s / (2 * np.pi * 2 * fbs))
    return 1j * w * RHO * U / (4 * np.pi * r) * shelf


def spl(p):
    return 20 * np.log10(np.abs(p) / P_REF + 1e-30)


# ---------------------------------------------------------------- analog filters
def hp2(f0, Q):
    w0 = 2 * np.pi * f0
    return s**2 / (s**2 + s * w0 / Q + w0**2)


def lp2(f0, Q):
    w0 = 2 * np.pi * f0
    return w0**2 / (s**2 + s * w0 / Q + w0**2)


def lt(f0, Q0, fp, Qp):            # Linkwitz transform
    w0, wp = 2 * np.pi * f0, 2 * np.pi * fp
    return (s**2 + s * w0 / Q0 + w0**2) / (s**2 + s * wp / Qp + wp**2)


def low_shelf(f0, gain_db, Q=0.707):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0
    return (s**2 + s * np.sqrt(A) * w0 / Q + A * w0**2) / \
           (s**2 + s * np.sqrt(A) * w0 / Q + w0**2) * 1 / A * A  # RBJ analog


def peq(f0, gain_db, Q):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0
    return (s**2 + s * (w0 / Q) * A + w0**2) / (s**2 + s * (w0 / Q) / A + w0**2)


# ---------------------------------------------------------------- systems
sat = solve(SAT, VB_SAT)
sub = solve(SUB, VB_SUB, PR)

# sealed-sat closed-box figures
alpha = (RC2 * SAT["Sd"] ** 2 * SAT["Cms"]) / VB_SAT
Qes = 2 * np.pi * fs_of(SAT) * SAT["Mms"] * SAT["Re"] / SAT["Bl"] ** 2
Qms = 2 * np.pi * fs_of(SAT) * SAT["Mms"] / SAT["Rms"]
Qts = Qes * Qms / (Qes + Qms)
fc_sat = fs_of(SAT) * np.sqrt(1 + alpha)
qtc_sat = Qts * np.sqrt(1 + alpha)

# PR tuning
Cab_sub = VB_SUB / RC2
Map = PR["Mms"] / PR["Sd"] ** 2 / PR["n"]
Cap = PR["Cms"] * PR["Sd"] ** 2 * PR["n"]
fb = 1 / (2 * np.pi * np.sqrt(Map * (Cab_sub * Cap / (Cab_sub + Cap))))

FX = 180.0                              # crossover
w_bs = 2 * np.pi * 115.0 / BAFFLE_W
BSC = (1 + s / (w_bs * 10 ** (4.5 / 20))) / (1 + s / w_bs)       # baffle-step compensation, -4.5 dB HF shelf
H_sat = lt(fc_sat, qtc_sat, FX, 0.707) * hp2(FX, 0.707) * BSC  # -> LR4 HP acoustically
H_sub = lp2(FX, 0.707) ** 2 * hp2(42, 0.6) * peq(62, 4.0, 1.2)  # LR4 LP + subsonic + bass lift

# Reference: 1 V rms program signal into each channel (DSP applied)
p_sub = p_far(sub["U"] * H_sub)
band_sub = (f > 80) & (f < 120)
band_sat = (f > 400) & (f < 900)
trim = np.mean(spl(p_sub)[band_sub]) - np.mean(spl(2 * p_far(sat["U"] * H_sat))[band_sat])
H_sat = H_sat * 10 ** (trim / 20)     # sat trim (negative = attenuate sats)
p_sat = p_far(sat["U"] * H_sat)
p_tot = 2 * p_sat + p_sub               # two sats coherent on axis
p_sat_raw = p_far(sat["U"] * 2.83)
p_sub_raw = p_far(sub["U"] * 2.83)

# ---------------------------------------------------------------- max output
def max_level(pvdd, pvdd_sub=None):
    vmax = v_rms_max(pvdd)
    vmax_sub = v_rms_max(pvdd if pvdd_sub is None else pvdd_sub)
    lim = {}
    # scale g = program volts (rms) at DSP input
    g_v_sat = np.minimum(vmax, np.sqrt(SAT["Pmax"] * SAT["Re"])) / np.abs(H_sat)
    g_v_sub = np.minimum(vmax_sub, np.sqrt(SUB["Pmax"] * SUB["Re"])) / np.abs(H_sub)
    g_x_sat = SAT["Xmax"] / (np.sqrt(2) * np.abs(sat["xd"] * H_sat))
    g_x_sub = SUB["Xmax"] / (np.sqrt(2) * np.abs(sub["xd"] * H_sub))
    g_x_pr = PR["Xmax"] / (np.sqrt(2) * np.abs(sub["xp"] * H_sub))
    lim = dict(sat_voltage=g_v_sat, sub_voltage=g_v_sub, sat_xmax=g_x_sat,
               sub_xmax=g_x_sub, pr_xmax=g_x_pr)
    g = np.min(np.vstack(list(lim.values())), axis=0)
    which = np.array(list(lim.keys()))[np.argmin(np.vstack(list(lim.values())), axis=0)]
    return g, which


g_nom, which_nom = max_level(PVDD_NOM, PVDD_SUB)
g_low, _ = max_level(PVDD_MIN, PVDD_SUB)
g_nob, _ = max_level(PVDD_NOM)          # no boost: sub straight on battery
spl_max_nob = spl(np.abs(p_tot) * g_nob)
spl_max_nom = spl(np.abs(p_tot) * g_nom)
spl_max_low = spl(np.abs(p_tot) * g_low)

# ---------------------------------------------------------------- figures of merit
ref = spl(p_tot)
mid = np.mean(ref[(f > 300) & (f < 1000)])
def f_at(drop):
    idx = np.where((ref < mid - drop) & (f < 300))[0]
    return float(f[idx[-1]]) if len(idx) else None

def at(arr, hz):
    return float(np.interp(np.log(hz), np.log(f), arr))

# usable "flat" max SPL = lowest max over 70 Hz - 1 kHz, shaped like the response
flat_cap = float(np.min(spl_max_nom[(f >= 70) & (f <= 1000)] - (ref[(f >= 70) & (f <= 1000)] - mid)))

summary = dict(
    enclosure_outer_mm=ENC["outer_mm"],
    sat=dict(driver=SAT["name"], fs_hz=round(fs_of(SAT), 1), Qts=round(Qts, 2),
             Vb_l=VB_SAT * 1e3, fc_hz=round(fc_sat, 1), Qtc=round(qtc_sat, 2)),
    sub=dict(driver=SUB["name"], fs_hz=round(fs_of(SUB), 1), Vb_l=VB_SUB * 1e3,
             pr=f'{PR["n"]}x {PR["name"]}', fb_hz=round(fb, 1)),
    crossover_hz=FX, sat_trim_db=round(float(trim), 1),
    system=dict(f_minus3_hz=f_at(3), f_minus6_hz=f_at(6), f_minus10_hz=f_at(10),
                ripple_100_1k_db=round(float(np.ptp(ref[(f > 100) & (f < 1000)])), 2)),
    max_spl_db_1m_nominal_pvdd=dict({str(h): round(at(spl_max_nom, h), 1) for h in (50, 60, 80, 100, 150, 300, 1000)}),
    max_spl_db_1m_low_batt=dict({str(h): round(at(spl_max_low, h), 1) for h in (60, 100, 1000)}),
    flat_max_spl_db_1m=round(flat_cap, 1),
    max_spl_db_1m_without_sub_boost=dict({str(h): round(at(spl_max_nob, h), 1) for h in (60, 100, 150)}),
    limiter_by_band={str(h): str(which_nom[np.argmin(abs(f - h))]) for h in (40, 60, 80, 120, 200, 500, 1000)},
    sub_raw_spl_2v83_100hz=round(at(spl(p_sub_raw), 100), 1),
    sat_raw_spl_2v83_1khz=round(at(spl(p_sat_raw), 1000), 1),
)
with open("summary.json", "w") as fh:
    json.dump(summary, fh, indent=2)
print(json.dumps(summary, indent=2))

# ---------------------------------------------------------------- plots
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
C_SUB, C_SAT, C_PR, C_TOT = "#2a78d6", "#eb6834", "#1baf7a", INK
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2,
                     "axes.facecolor": SURF, "figure.facecolor": SURF})


def style(ax, ylab, ylim=None):
    ax.set_xscale("log")
    ax.set_xlim(20, 2000)
    ax.grid(True, which="both", color=GRID, lw=0.6)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel(ylab)
    ax.set_xticks([20, 50, 100, 200, 500, 1000, 2000])
    ax.set_xticklabels(["20", "50", "100", "200", "500", "1k", "2k"])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    if ylim:
        ax.set_ylim(*ylim)


fig, ax = plt.subplots(figsize=(9, 4.6))
off = 85 - mid
ax.plot(f, spl(p_sub) + off, color=C_SUB, lw=2, label="Sub (ND91 + 2x PR)")
ax.plot(f, spl(2 * p_sat) + off, color=C_SAT, lw=2, label="Satellites (2x CE54N)")
ax.plot(f, ref + off, color=C_TOT, lw=2.4, label="System sum")
ax.axvline(FX, color=INK2, lw=0.8, ls=":")
ax.text(FX * 1.04, 58, f"{FX:.0f} Hz LR4", color=INK2, fontsize=9)
style(ax, "SPL @ 1 m (dB)", (55, 95))
ax.legend(frameon=False, loc="lower right")
ax.set_title("Bassberry 2.1 - system response with DSP (normalised 85 dB)", loc="left", color=INK, fontsize=11)
fig.tight_layout(); fig.savefig("01_system_response.png", dpi=160)

fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(f, spl_max_nom, color=C_TOT, lw=2.4, label=f"Sub on {PVDD_SUB:.0f} V boost, sats on 3S (design)")
ax.plot(f, spl_max_nob, color=C_SUB, lw=2, label=f"Sub straight on 3S {PVDD_NOM} V (no boost)")
style(ax, "Max SPL @ 1 m (dB)", (60, 105))
ax.legend(frameon=False, loc="lower right")
ax.set_title("Maximum output (amp voltage, driver power, Xmax and PR excursion limits)", loc="left", color=INK, fontsize=11)
fig.tight_layout(); fig.savefig("02_max_spl.png", dpi=160)

fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(f, 1e3 * np.sqrt(2) * np.abs(sub["xd"] * H_sub) * g_nom, color=C_SUB, lw=2, label="Sub cone (Xmax 4.6 mm)")
ax.plot(f, 1e3 * np.sqrt(2) * np.abs(sub["xp"] * H_sub) * g_nom, color=C_PR, lw=2, label="Each PR (limit 6 mm)")
ax.plot(f, 1e3 * np.sqrt(2) * np.abs(sat["xd"] * H_sat) * g_nom, color=C_SAT, lw=2, label="Satellite (Xmax 1.4 mm)")
style(ax, "Peak excursion (mm)", (0, 8))
ax.legend(frameon=False, loc="upper right")
ax.set_title("Excursion at maximum output", loc="left", color=INK, fontsize=11)
fig.tight_layout(); fig.savefig("03_excursion.png", dpi=160)

fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(f, np.abs(sub["Z"]), color=C_SUB, lw=2, label="Sub")
ax.plot(f, np.abs(sat["Z"]), color=C_SAT, lw=2, label="Satellite")
style(ax, "|Z| (ohm)", (0, 30))
ax.legend(frameon=False, loc="upper right")
ax.set_title(f"Impedance - PR tuning Fb = {fb:.0f} Hz, sealed sat Fc = {fc_sat:.0f} Hz", loc="left", color=INK, fontsize=11)
fig.tight_layout(); fig.savefig("04_impedance.png", dpi=160)

np.savetxt("response.csv", np.column_stack([f, ref + off, spl(p_sub) + off, spl(2 * p_sat) + off, spl_max_nom, spl_max_low]),
           delimiter=",", header="f_hz,system_db,sub_db,sats_db,max_spl_nom_db,max_spl_low_db", comments="", fmt="%.3f")
