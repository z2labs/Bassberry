"""Project-local symbols that are not in the KiCad library (written to bassberry.kicad_sym)."""
import os
from sexpr import Sym, dump


def _eff(hide=False):
    e = [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]
    if hide:
        e.append([Sym("hide"), Sym("yes")])
    return e


def _pin(typ, x, y, ang, name, num):
    return [Sym("pin"), Sym(typ), Sym("line"), [Sym("at"), x, y, ang], [Sym("length"), 5.08],
            [Sym("name"), name, _eff()], [Sym("number"), str(num), _eff()]]


def ic_symbol(name, ref, fp, datasheet, desc, left, right, bottom, w=20.32, nc=()):
    """left/right: list of (num, name, type) top->bottom; bottom: list left->right."""
    h = max(len(left), len(right)) * 2.54 + 5.08
    top = round(h / 2 / 2.54) * 2.54
    pins = []
    for i, (n, nm, t) in enumerate(left):
        pins.append(_pin(t, -w / 2 - 5.08, top - 2.54 * (i + 1), 0, nm, n))
    for i, (n, nm, t) in enumerate(right):
        pins.append(_pin(t, w / 2 + 5.08, top - 2.54 * (i + 1), 180, nm, n))
    bot = -top
    for i, (n, nm, t) in enumerate(bottom):
        x = -((len(bottom) - 1) * 2.54) / 2 + i * 2.54
        pins.append(_pin(t, round(x / 2.54) * 2.54, bot - 5.08, 90, nm, n))
    for i, n in enumerate(nc):
        pins.append(_pin("no_connect", -w / 2 + 2.54 * (i + 1), top + 5.08, 270, "NC", n))
    return [Sym("symbol"), name, [Sym("pin_names"), [Sym("offset"), 1.016]],
            [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            [Sym("property"), "Reference", ref, [Sym("at"), 0, top + 2.54, 0], _eff()],
            [Sym("property"), "Value", name, [Sym("at"), 0, bot - 7.62, 0], _eff()],
            [Sym("property"), "Footprint", fp, [Sym("at"), 0, 0, 0], _eff(True)],
            [Sym("property"), "Datasheet", datasheet, [Sym("at"), 0, 0, 0], _eff(True)],
            [Sym("property"), "Description", desc, [Sym("at"), 0, 0, 0], _eff(True)],
            [Sym("symbol"), f"{name}_0_1", [Sym("rectangle"), [Sym("start"), -w / 2, top], [Sym("end"), w / 2, bot],
                                            [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]],
                                            [Sym("fill"), [Sym("type"), Sym("background")]]]],
            [Sym("symbol"), f"{name}_1_1"] + pins]


PI, PO, IN, BI, PA, OU = "power_in", "power_out", "input", "bidirectional", "passive", "output"

IP2366 = ic_symbol(
    "IP2366", "U", "Package_DFN_QFN:QFN-40-1EP_5x5mm_P0.4mm_EP3.6x3.6mm",
    "http://www.injoinic.com/", "Injoinic IP2366: USB-C PD3.1 2-6S buck-boost charger/discharger, 140 W, QFN40 5x5",
    left=[(5, "VBUS", IN), (6, "VBUSG", OU), (7, "VBUSI", IN), (8, "VIO", PI), (9, "CSP1", IN), (10, "CSN1", IN),
          (11, "PCIN", IN), (37, "CC1", BI), (34, "CC2", BI), (35, "DPC", BI), (36, "DMC", BI), (33, "EN", IN),
          (39, "GPIO20", BI), (38, "GPIO19", BI), (31, "GPIO1", BI)],
    right=[(12, "HG1", OU), (13, "BST1", PA), (14, "LX1", PA), (15, "LG1", OU), (16, "LG2", OU), (17, "LX2", PA),
           (18, "BST2", PA), (19, "HG2", OU), (20, "PCON", IN), (21, "CSN2", IN), (22, "CSP2", IN), (23, "BAT", PI),
           (24, "CC_BDO", PA), (25, "VCC5V", PO), (28, "VCCIO", PO), (27, "GPIO4/BAT_NUM", PA),
           (29, "GPIO3/PSET", PA), (30, "GPIO2/VSET", PA), (32, "GPIO0/NTC", PA)],
    bottom=[(26, "AGND", PI), (41, "EPAD", PI)],
    w=25.4, nc=(40, 1, 2, 3, 4))


def write_lib(path):
    lib = [Sym("kicad_symbol_lib"), [Sym("version"), 20241209], [Sym("generator"), "bassberry_projlib"],
           [Sym("generator_version"), "1.0"], IP2366]
    open(path, "w", encoding="utf-8").write(dump(lib) + "\n")
    d = os.path.dirname(path)
    open(os.path.join(d, "sym-lib-table"), "w", encoding="utf-8").write(
        '(sym_lib_table\n\t(version 7)\n\t(lib (name "bassberry") (type "KiCad") (uri "${KIPRJMOD}/bassberry.kicad_sym") (options "") (descr "Bassberry project symbols"))\n)\n')
