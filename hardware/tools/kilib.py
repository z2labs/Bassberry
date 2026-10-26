"""Read KiCad symbol libraries and compute absolute pin positions of placed symbols."""
import os, math
from sexpr import parse, find, find1, Sym

KICAD_SHARE = os.environ.get("KICAD_SHARE", r"C:\Program Files\KiCad\10.0\share\kicad")
_cache = {}


def load_lib(lib):
    if lib not in _cache:
        path = os.path.join(KICAD_SHARE, "symbols", lib + ".kicad_sym")
        _cache[lib] = parse(open(path, encoding="utf-8").read())
    return _cache[lib]


def get_symbol(lib_id):
    """Return the symbol s-expr (with 'extends' resolved) renamed to lib_id."""
    lib, name = lib_id.split(":")
    tree = load_lib(lib)
    syms = {s[1]: s for s in find(tree, "symbol")}
    s = syms[name]
    ext = find1(s, "extends")
    if ext:
        parent = [x for x in syms[ext[1]]]
        merged = [Sym("symbol"), lib_id]
        own_props = {p[1]: p for p in find(s, "property")}
        for item in parent[2:]:
            if isinstance(item, list) and item[0] == "property" and item[1] in own_props:
                merged.append(own_props.pop(item[1]))
            elif isinstance(item, list) and item[0] == "symbol":
                sub = list(item); sub[1] = sub[1].replace(ext[1], name, 1); merged.append(sub)
            else:
                merged.append(item)
        merged.extend(own_props.values())
        return merged
    out = list(s); out[1] = lib_id
    return out


def pins(sym, unit=1):
    """List of dicts: number, name, x, y, angle, type (symbol coords, y up)."""
    res = []
    for sub in find(sym, "symbol"):
        nm = sub[1]
        try:
            u = int(nm.split("_")[-2])
        except ValueError:
            u = 0
        if u not in (0, unit):
            continue
        for p in find(sub, "pin"):
            at = find1(p, "at")
            res.append(dict(type=str(p[1]), name=find1(p, "name")[1], number=find1(p, "number")[1],
                            x=float(at[1]), y=float(at[2]), angle=float(at[3]) if len(at) > 3 else 0.0))
    return res


def pin_abs(pin, sx, sy, rot=0, mirror_x=False):
    """Absolute schematic position (y down) of a pin's connection point."""
    x, y = pin["x"], -pin["y"]
    if mirror_x:
        x = -x
    r = math.radians(-rot)
    xr = x * math.cos(r) - y * math.sin(r)
    yr = x * math.sin(r) + y * math.cos(r)
    return round(sx + xr, 4), round(sy + yr, 4)
