"""Bassberry 2.1 - Blender (bpy) Cycles product renders.

Usage: python3 render.py [outdir] [samples] [view ...]
Views: hero, rear, top, interior, exploded, board
Geometry in mm, (x right, y up, z toward listener), mapped to Blender Z-up.
"""
import sys, os, math
import bpy
from mathutils import Vector

OUT = sys.argv[1] if len(sys.argv) > 1 else "renders"
SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 96
VIEWS = sys.argv[3:] or ["hero", "rear", "top", "interior", "exploded", "board"]
os.makedirs(OUT, exist_ok=True)
S = 0.01  # 1 mm = 0.01 BU


def P(x, y, z):
    return Vector((x * S, -z * S, y * S))


bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene

# ------------------------------------------------------------ materials
def mat(name, col, rough=0.5, metal=0.0, alpha=1.0, emit=None, emit_img=None, coat=0.0, trans=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Alpha"].default_value = alpha
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    if trans:
        b.inputs["Transmission Weight"].default_value = trans
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = 3.0
    if emit_img:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(emit_img)
        nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
        nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Emission Strength"].default_value = 2.5
    if alpha < 1:
        m.surface_render_method = "BLENDED" if hasattr(m, "surface_render_method") else None
    return m


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


M = dict(
    shell=mat("shell", srgb("#2b2c30"), 0.62),
    shell_glass=mat("shell_smoke", srgb("#2b2c30"), 0.3, alpha=0.10),
    pcb=mat("pcb", srgb("#0f4a31"), 0.32, coat=0.4),
    enig=mat("enig", srgb("#d4af6a"), 0.25, 1.0),
    alu=mat("alu", srgb("#c9ccd1"), 0.28, 1.0),
    pad=mat("gappad", srgb("#7f93a8"), 0.85),
    pi=mat("pi", srgb("#2c7a3a"), 0.35, coat=0.4),
    blk=mat("black", srgb("#161618"), 0.5),
    chip=mat("chip", srgb("#1c1c1e"), 0.4),
    sil=mat("silver", srgb("#d8dadd"), 0.2, 1.0),
    brass=mat("brass", srgb("#c9a548"), 0.3, 1.0),
    cell=mat("cell", srgb("#1f5fbf"), 0.25, 0.0, coat=0.6),
    ni=mat("nickel", srgb("#cfd2d6"), 0.25, 1.0),
    ind=mat("inductor", srgb("#3a3a3e"), 0.55, 0.2),
    cone=mat("alu_cone", srgb("#a8acb2"), 0.3, 0.9),
    rub=mat("rubber", srgb("#0e0e10"), 0.9),
    bmr=mat("bmr", srgb("#d9d6cf"), 0.5),
    berry=mat("berry", srgb("#c2185b"), 0.38, 0.1, coat=0.5),
    btn=mat("button", srgb("#3a3b40"), 0.45),
    mag=mat("magnet", srgb("#55575c"), 0.35, 0.9),
    icon=mat("icon", srgb("#9a998f"), 0.5),
    wall=mat("petg_wall", srgb("#45464b"), 0.75),
    satv=mat("sat_volume", srgb("#EF9F27"), 0.4, alpha=0.20),
    subv=mat("sub_volume", srgb("#5DCAA5"), 0.4, alpha=0.22),
    floor=mat("floor", srgb("#141416"), 0.32),
    cap=mat("cap_sleeve", srgb("#1b1b1d"), 0.4),
)

# grille: dark metal with procedural round perforations
g = bpy.data.materials.new("grille"); g.use_nodes = True
nt = g.node_tree; bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Metallic"].default_value = 0.7; bsdf.inputs["Roughness"].default_value = 0.45
tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
mp.inputs["Scale"].default_value = (32, 32, 32)
vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.inputs["Randomness"].default_value = 0.0
cr = nt.nodes.new("ShaderNodeValToRGB")
cr.color_ramp.elements[0].position = 0.33; cr.color_ramp.elements[0].color = (0.003, 0.003, 0.004, 1)
cr.color_ramp.elements[1].position = 0.345; cr.color_ramp.elements[1].color = (*srgb("#46474c"), 1)
cr.color_ramp.interpolation = "CONSTANT"
nt.links.new(tc.outputs["Object"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], vor.inputs["Vector"])
nt.links.new(vor.outputs["Distance"], cr.inputs["Fac"]); nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
M["grille"] = g

# OLED screen image
try:
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (512, 256), "black"); d = ImageDraw.Draw(im)
    fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
    fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    d.text((70, 18), "BASSBERRY", font=fb, fill=(232, 246, 255))
    d.text((110, 84), "Radio  Kossuth", font=fr, fill=(232, 246, 255))
    for i in range(30):
        hh = 10 + abs(math.sin(i * 0.62)) * 70 * (1.25 if i < 9 else 0.8)
        d.rectangle([28 + i * 15.5, 248 - hh, 38 + i * 15.5, 248], fill=(232, 246, 255))
    oled_png = os.path.abspath(os.path.join(OUT, "_oled.png")); im.save(oled_png)
    M["oled"] = mat("oled", (0, 0, 0), 0.1, emit_img=oled_png)
except Exception as e:  # pragma: no cover
    print("OLED texture skipped:", e)
    M["oled"] = mat("oled", (0.02, 0.02, 0.02), 0.1, emit=(0.8, 0.9, 1.0))

# ------------------------------------------------------------ geometry helpers
GROUPS = {}


def reg(obj, grp):
    GROUPS.setdefault(grp, []).append(obj)
    obj["base"] = list(obj.location)
    obj["grp"] = grp
    return obj


def box(grp, x0, x1, y0, y1, z0, z1, m, bevel=0.0, segs=4):
    bpy.ops.mesh.primitive_cube_add(size=1, location=P((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object
    o.scale = ((x1 - x0) * S, (z1 - z0) * S, (y1 - y0) * S)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bv = o.modifiers.new("bevel", "BEVEL"); bv.width = bevel * S; bv.segments = segs; bv.limit_method = "ANGLE"
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth_by_angle() if hasattr(bpy.ops.object, "shade_smooth_by_angle") else None
    return reg(o, grp)


def rot_for(ax):
    return {"y": (0, 0, 0), "-y": (math.pi, 0, 0), "z": (math.pi / 2, 0, 0), "x": (0, math.pi / 2, 0)}[ax]


def cyl(grp, r_bot, r_top, h, x, y, z, ax, m, verts=64, cap=True):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r_bot * S, radius2=r_top * S, depth=h * S,
                                    location=P(x, y, z), rotation=rot_for(ax),
                                    end_fill_type="NGON" if cap else "NOTHING")
    o = bpy.context.object; o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return reg(o, grp)


def torus(grp, R, r, x, y, z, ax, m):
    bpy.ops.mesh.primitive_torus_add(major_radius=R * S, minor_radius=r * S, major_segments=72, minor_segments=16,
                                     location=P(x, y, z), rotation=rot_for(ax))
    o = bpy.context.object; o.data.materials.append(m); bpy.ops.object.shade_smooth()
    return reg(o, grp)


def plane(grp, w, h, x, y, z, m, ax="z"):
    bpy.ops.mesh.primitive_plane_add(size=1, location=P(x, y, z), rotation=rot_for(ax))
    o = bpy.context.object; o.scale = (w * S, h * S, 1); bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(m)
    return reg(o, grp)


# ------------------------------------------------------------ model
BY0, BY1 = -5.0, -3.4
PY, CY = BY1 + 8.4, BY1 + 11.0
# motherboard (notch for Pi USB/ETH)
box("board", -90, 90, BY0, BY1, -34, 55, M["pcb"])
box("board", -90, -85, BY0, BY1, -55, -34, M["pcb"])
box("board", -29, 90, BY0, BY1, -55, -34, M["pcb"])
box("board", -68, -42, BY1, BY1 + 0.06, -19, 7, M["enig"])
for i in range(28):  # thermal via field hint
    pass
# supervisor / OLED / button headers on board top
box("board", 40, 60, BY1, BY1 + 2.5, 40, 45, M["blk"])
box("board", 62, 74, BY1, BY1 + 1.0, 36, 48, M["chip"])
# Raspberry Pi upside down
box("upper", -84, -79, BY1, PY, -22, 29, M["blk"])
box("upper", -67, -43, BY1 + 0.06, PY - 1.7, -18, 6, M["alu"], bevel=0.6)
box("upper", -66, -44, PY - 1.7, PY, -17, 5, M["pad"])
box("upper", -85, -29, PY, PY + 1.6, -55, 30, M["pi"], bevel=1.0, segs=3)
box("upper", -62, -50, PY + 1.6, PY + 2.9, 21, 30.5, M["sil"])
box("upper", -70, -58, PY + 1.6, PY + 2.6, -10, 2, M["chip"])
box("upper", -50, -40, PY + 1.6, PY + 2.4, -30, -20, M["chip"])
box("upper", -83, -67, PY - 16, PY, -58, -37, M["sil"], bevel=0.5)
box("upper", -64, -50, PY - 16, PY, -58, -40, M["sil"], bevel=0.5)
box("upper", -47, -33, PY - 16, PY, -58, -40, M["sil"], bevel=0.5)
for px_, pz_ in [(-81.5, -51.5), (-32.5, -51.5), (-81.5, 6.5), (-32.5, 6.5)]:
    cyl("upper", 2.5, 2.5, PY - BY1, px_, (PY + BY1) / 2, pz_, "y", M["brass"], 6)
    cyl("upper", 2.6, 2.6, 1.4, px_, PY + 2.3, pz_, "y", M["sil"], 24)
# 3S 18650 pack with snap-in metal clips
for cx in (-9, 10, 29):
    cyl("upper", 9, 9, 64, cx, CY, -5, "z", M["cell"])
    cyl("upper", 8.4, 8.4, 65.6, cx, CY, -5, "z", M["ni"])
    for zc in (-38.6, 28.6):
        box("upper", cx - 7, cx + 7, BY1, CY + 4, zc - 0.4, zc + 0.4, M["ni"])
        box("upper", cx - 7, cx + 7, BY1, BY1 + 1.2, zc - 3, zc + 3, M["ni"])
# bottom-side electronics
for p in [(44, -44, 7), (16, -50, 6), (-12, -8, 7), (10, -8, 7), (60, 20, 5)]:
    box("under", p[0], p[0] + p[2], BY0 - 1.2, BY0, p[1], p[1] + p[2], M["chip"])
for p in [(42, -32), (16, -38), (-24, 14), (-10, 14), (4, 14), (18, 14), (34, -4), (56, -30)]:
    box("under", p[0], p[0] + 8, BY0 - 5.5, BY0, p[1], p[1] + 8, M["ind"], bevel=0.6)
for cx in (-30, -18, 30, 42):
    cyl("under", 5, 5, 10, cx, BY0 - 5, 30, "y", M["sil"])
    cyl("under", 5.05, 5.05, 6, cx, BY0 - 3, 30, "y", M["cap"])
box("under", 52, 63, BY0 - 3.4, BY0, -57, -48, M["sil"], bevel=0.8)

# acoustic section
AY0, AY1, AYM = -97.5, -19.5, -58.0
box("volumes", -112.5, -56.5, AY0, AY1, 17.5, 67.5, M["satv"])
box("volumes", 56.5, 112.5, AY0, AY1, 17.5, 67.5, M["satv"])
box("volumes", -54, 54, AY0, AY1, -67.5, 67.5, M["subv"])
box("volumes", -112.5, -56.5, AY0, AY1, -67.5, 15, M["subv"])
box("volumes", 56.5, 112.5, AY0, AY1, -67.5, 15, M["subv"])
box("acoustic", -112.5, 112.5, AY1, AY1 + 2.5, -67.5, 67.5, M["wall"])
for sg in (-1, 1):
    box("acoustic", min(sg * 54, sg * 56.5), max(sg * 54, sg * 56.5), AY0, AY1, 15, 67.5, M["wall"])
    box("acoustic", min(sg * 56.5, sg * 112.5), max(sg * 56.5, sg * 112.5), AY0, AY1, 15, 17.5, M["wall"])
for cx in (-84.5, 84.5):  # BMR satellites
    cyl("acoustic", 27, 27, 3, cx, AYM, 68.5, "z", M["blk"])
    torus("acoustic", 21.5, 1.6, cx, AYM, 70, "z", M["rub"])
    cyl("acoustic", 20, 20, 0.8, cx, AYM, 70.2, "z", M["bmr"])
    cyl("acoustic", 12, 12, 14, cx, AYM, 60, "z", M["mag"])
# down-firing 3.5" sub
cyl("acoustic", 52, 52, 3, 0, AY0 - 1, 0, "y", M["blk"])
torus("acoustic", 43, 2.6, 0, AY0 - 2.2, 0, "y", M["rub"])
cyl("acoustic", 40, 22, 16, 0, AY0 + 7, 0, "y", M["cone"], cap=False)
cyl("acoustic", 13, 13, 2, 0, AY0 + 0.5, 0, "y", M["cone"])
cyl("acoustic", 30, 30, 26, 0, AY0 + 30, 0, "y", M["mag"])
# opposed passive radiators on side walls
for sg in (-1, 1):
    cyl("acoustic", 35, 35, 3, sg * 113.8, AYM, -26, "x", M["berry"])
    torus("acoustic", 29, 2.2, sg * 115.3, AYM, -26, "x", M["rub"])
    cyl("acoustic", 27, 27, 0.8, sg * 115.6, AYM, -26, "x", M["cone"])

# shell: printed lower tub + top cover (seam at the acoustic divider)
tub = box("tub", -115, 115, -100, -20.0, -70, 70, M["shell"], bevel=10, segs=8)
cover = box("cover", -115, 115, -19.5, 20, -70, 70, M["shell"], bevel=10, segs=8)
box("grille", -106, 106, -94, -24, 71.6, 72.4, M["grille"], bevel=1.5)                       # front grille
box("cover", -24, 24, -13, 9, 70.0, 70.5, M["blk"], bevel=1.5)         # OLED bezel
plane("cover", 40, 20, 0, -2, 70.55, M["oled"])
for cx in (-62, -44, -26):
    cyl("cover", 5, 5, 2, cx, 20.6, -12, "y", M["btn"])
box("cover", -13, 21, 19.6, 21.6, -17, -7, M["btn"], bevel=4.5, segs=6)
box("cover", -2, 2, 21.6, 21.8, -12.5, -11.5, M["icon"])
box("cover", 8, 12, 21.6, 21.8, -12.5, -11.5, M["icon"])
box("cover", 9.5, 10.5, 21.6, 21.8, -14, -10, M["icon"])
cyl("cover", 10, 10, 9, 66, 24.5, -8, "y", M["alu"], 96)
cyl("cover", 10.4, 10.4, 6, 66, 23, -8, "y", M["blk"])
cyl("cover", 1.8, 1.8, 0.4, 66, 29.1, -14, "y", M["berry"])
cyl("cover", 1.6, 1.6, 0.6, -62, 21.7, -12, "y", M["berry"])
box("cover", -86, -26, -11, 7, -70.5, -70.05, M["blk"], bevel=1)       # Pi port window
box("cover", 54, 66, -8, -3, -70.5, -70.05, M["blk"], bevel=1.5)       # USB-C
for sg in (-1, 1):
    cyl("tub", 34.5, 34.5, 1.6, sg * 115.4, AYM, -26, "x", M["berry"])
    torus("tub", 29, 2.2, sg * 116.6, AYM, -26, "x", M["rub"])
    cyl("tub", 27, 27, 0.8, sg * 117.2, AYM, -26, "x", M["cone"])
for fx, fz in [(-92, -55), (92, -55), (-92, 55), (92, 55)]:
    cyl("tub", 8, 7, 18, fx, -109, fz, "y", M["rub"])

# studio floor
bpy.ops.mesh.primitive_plane_add(size=60, location=P(0, -118, 0))
fl = bpy.context.object; fl.data.materials.append(M["floor"])

# ------------------------------------------------------------ lights / world / render
w = bpy.data.worlds.new("w"); scn.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.012, 0.012, 0.014, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0


def area(name, loc, size, power, col=(1, 1, 1), target=(0, 0, -0.45)):
    d = bpy.data.lights.new(name, "AREA"); d.size = size; d.energy = power; d.color = col
    o = bpy.data.objects.new(name, d); scn.collection.objects.link(o); o.location = loc
    direction = Vector(target) - Vector(loc); o.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return o


area("key", (-3.5, -4.5, 4.0), 3.0, 900)
area("fill", (4.5, -3.0, 1.5), 3.0, 260, (0.86, 0.9, 1.0))
area("rim", (1.0, 5.0, 3.0), 2.0, 450, (1.0, 0.5, 0.66))
area("top", (0, 0, 6.0), 4.0, 300)

tgt = bpy.data.objects.new("target", None); scn.collection.objects.link(tgt)
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 60
cam = bpy.data.objects.new("cam", cam_d); scn.collection.objects.link(cam); scn.camera = cam
tc = cam.constraints.new("TRACK_TO"); tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
cam_d.dof.use_dof = True; cam_d.dof.focus_object = tgt; cam_d.dof.aperture_fstop = 11

scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.cycles.samples = SAMPLES
scn.cycles.use_adaptive_sampling = True
scn.cycles.max_bounces = 8
try:
    scn.cycles.use_denoising = True
    scn.cycles.denoiser = "OPENIMAGEDENOISE"
except Exception:
    pass
scn.render.resolution_x, scn.render.resolution_y = (640, 400) if os.environ.get("BB_PREVIEW") else (1600, 1000)
scn.render.film_transparent = False
scn.view_settings.view_transform = "AgX"
scn.view_settings.look = "AgX - Punchy" if "AgX - Punchy" in [i.identifier for i in scn.view_settings.bl_rna.properties["look"].enum_items] else "None"


def show(groups):
    for grp, objs in GROUPS.items():
        for o in objs:
            o.hide_render = grp not in groups


def explode(off):
    for grp, objs in GROUPS.items():
        for o in objs:
            b = Vector(o["base"]); o.location = b + Vector((0, 0, off.get(grp, 0) * S))


ALL = ["board", "upper", "under", "acoustic", "tub", "cover", "grille"]
VIEWDEF = {
    "hero":     dict(groups=ALL, cam=(-3.6, -6.2, 2.0), tgt=(0.1, 0, -0.42)),
    "rear":     dict(groups=ALL, cam=(4.6, 5.0, 1.6), tgt=(0, 0, -0.42)),
    "top":      dict(groups=ALL, cam=(-1.2, -3.0, 6.2), tgt=(0, 0, -0.3)),
    "interior": dict(groups=["board", "upper", "under", "acoustic", "volumes"], cam=(-4.4, -5.8, 3.4), tgt=(0, 0, -0.42)),
    "exploded": dict(groups=["board", "upper", "under", "acoustic", "cover", "volumes"], cam=(-5.6, -8.4, 3.4), tgt=(0, 0, 0.05),
                     off={"cover": 150, "upper": 95, "board": 55, "under": 45, "acoustic": -20, "volumes": -20, "tub": -20},
                     smoke=True),
    "board":    dict(groups=["board", "upper", "under"], cam=(-1.6, -2.4, 2.6), tgt=(-0.15, 0, 0.0)),
}

for v in VIEWS:
    d = VIEWDEF[v]
    show(d["groups"]); explode(d.get("off", {}))
    tub.data.materials[0] = M["shell_glass"] if d.get("smoke") else M["shell"]
    cam.location = d["cam"]; tgt.location = d["tgt"]
    fl.location = P(0, -118 + d.get("off", {}).get("tub", 0), 0)
    scn.render.filepath = os.path.abspath(os.path.join(OUT, f"bassberry_{v}.png"))
    print("rendering", v, flush=True)
    bpy.ops.render.render(write_still=True)
print("done")
