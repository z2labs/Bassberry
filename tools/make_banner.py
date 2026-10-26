"""Generate docs/img/banner.svg - animated 2.1 spectrum banner for the README."""
import math, random, os

random.seed(21)
W, H = 1200, 340
N = 56
x0, x1, base = 70, 1130, 300
bw = (x1 - x0) / N
out = []
out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Bassberry - open-source hi-fi 2.1 Raspberry Pi speaker">')
out.append('''<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#121216"/><stop offset="1" stop-color="#1d1218"/></linearGradient>
<linearGradient id="sub" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#7a0f39"/><stop offset="1" stop-color="#ff3d7f"/></linearGradient>
<linearGradient id="mid" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#b0234a"/><stop offset="1" stop-color="#ffb3cc"/></linearGradient>
<linearGradient id="hi" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#5d6470"/><stop offset="1" stop-color="#e8f6ff"/></linearGradient>
<radialGradient id="glow" cx="0.18" cy="0.95" r="0.6"><stop offset="0" stop-color="#ff3d7f" stop-opacity="0.28"/><stop offset="1" stop-color="#ff3d7f" stop-opacity="0"/></radialGradient>
</defs>''')
out.append(f'<rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/><rect width="{W}" height="{H}" rx="18" fill="url(#glow)"/>')
# grid lines
for i in range(1, 5):
    y = base - i * 50
    out.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="#ffffff" stroke-opacity="0.05"/>')
# bars
for i in range(N):
    t = i / (N - 1)
    if t < 0.22:
        grad, hmax = "sub", 165
    elif t < 0.62:
        grad, hmax = "mid", 135
    else:
        grad, hmax = "hi", 100 - 45 * (t - 0.62)
    shape = hmax * (0.55 + 0.45 * math.sin(i * 0.33) ** 2)
    vals = [max(8, shape * random.uniform(0.25, 1.0)) for _ in range(6)]
    vals.append(vals[0])
    dur = (0.9 if grad == "sub" else 0.6 if grad == "mid" else 0.42) + random.uniform(0, 0.25)
    hs = ";".join(f"{v:.0f}" for v in vals)
    ys = ";".join(f"{base - v:.0f}" for v in vals)
    x = x0 + i * bw + 2
    out.append(f'<rect x="{x:.1f}" y="{base - vals[0]:.0f}" width="{bw - 5:.1f}" height="{vals[0]:.0f}" rx="3" fill="url(#{grad})">'
               f'<animate attributeName="height" values="{hs}" dur="{dur:.2f}s" repeatCount="indefinite" calcMode="spline" keySplines="{";".join(["0.4 0 0.2 1"]*6)}"/>'
               f'<animate attributeName="y" values="{ys}" dur="{dur:.2f}s" repeatCount="indefinite" calcMode="spline" keySplines="{";".join(["0.4 0 0.2 1"]*6)}"/></rect>')
# band labels + baseline
out.append(f'<line x1="{x0}" y1="{base + 2}" x2="{x1}" y2="{base + 2}" stroke="#ffffff" stroke-opacity="0.25"/>')
F = 'font-family="Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif"'
for label, frac in (("SUB  57 Hz - 180 Hz", 0.0), ("MID  180 Hz - 2 kHz", 0.22), ("HIGH  2 - 20 kHz", 0.62)):
    out.append(f'<text x="{x0 + frac * (x1 - x0) + 2:.0f}" y="{base + 26}" {F} font-size="13" letter-spacing="2" fill="#ffffff" fill-opacity="0.45">{label}</text>')
out.append(f'<text x="{x0}" y="78" {F} font-size="64" font-weight="700" letter-spacing="6" fill="#ffffff">BASSBERRY</text>')
out.append(f'<text x="{x0 + 3}" y="112" {F} font-size="20" fill="#ffffff" fill-opacity="0.72">Open-source hi-fi 2.1 speaker for every Raspberry Pi  ·  by Z2Labs</text>')
out.append(f'<text x="{x1}" y="70" text-anchor="end" {F} font-size="44" font-weight="700" fill="#ff3d7f">2.1</text>')
out.append('</svg>')
os.makedirs("docs/img", exist_ok=True)
open("docs/img/banner.svg", "w").write("\n".join(out))
print("docs/img/banner.svg written")
