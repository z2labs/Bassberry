"""Label-based KiCad schematic generator (KiCad 9/10 file format).

Every symbol pin gets a net label (local or global) or a power symbol at its
connection point, so no wires are needed and the netlist is exact by construction.
"""
import os, uuid
from sexpr import Sym, dump
from kilib import get_symbol, pins, pin_abs

NS = uuid.UUID("6c1f5b9e-2b1e-4c55-9b7a-b455b3e77a21")
PROJECT = "bassberry"
POWER_SYMS = {"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V", "+BATT": "power:+BATT", "VBUS": "power:VBUS"}
FLAGS = []


def U(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


def font(size=1.27):
    return [Sym("font"), [Sym("size"), size, size]]


def snap(v, g=1.27):
    return round(round(v / g) * g, 4)


class Sheet:
    def __init__(self, name, filename, title, page, globals_=(), paper="A3"):
        self.name, self.filename, self.title, self.page, self.paper = name, filename, title, page, paper
        self.uuid = U("sheetfile", filename)
        self.items, self.lib_ids = [], []
        self.globals = set(globals_)
        self.pwr = 0
        self.path = None  # set by Project

    # ---------------------------------------------------------- symbols
    def part(self, lib_id, ref, value, x, y, rot=0, fp="", nets=None, props=None, mirror=False, dnp=False):
        x, y = snap(x, 2.54), snap(y, 2.54)
        sym = get_symbol(lib_id)
        if lib_id not in self.lib_ids:
            self.lib_ids.append(lib_id)
        nets = nets or {}
        uid = U(self.filename, ref)
        node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), x, y, rot]]
        if mirror:
            node.append([Sym("mirror"), Sym("y")])
        node += [[Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")],
                 [Sym("on_board"), Sym("yes")], [Sym("dnp"), Sym("yes" if dnp else "no")],
                 [Sym("uuid"), uid]]
        hidden_ref = ref.startswith("#")
        node.append(self._prop("Reference", ref, x + 3.81, y - 1.27, hide=hidden_ref))
        node.append(self._prop("Value", value, x + 3.81, y + 1.27))
        node.append(self._prop("Footprint", fp, x, y, hide=True))
        node.append(self._prop("Datasheet", "~", x, y, hide=True))
        for k, v in (props or {}).items():
            node.append(self._prop(k, v, x, y, hide=True))
        plist = pins(sym)
        seen = set()
        for p in plist:
            if p["number"] in seen:
                continue
            seen.add(p["number"])
            node.append([Sym("pin"), p["number"], [Sym("uuid"), U(self.filename, ref, "pin", p["number"])]])
        node.append([Sym("instances"), [Sym("project"), PROJECT,
                     [Sym("path"), self.path, [Sym("reference"), ref], [Sym("unit"), 1]]]])
        self.items.append(node)
        # connections
        done = set()
        for p in plist:
            key = (p["x"], p["y"])
            net = nets.get(p["number"], nets.get(p["name"], "__unset__"))
            if key in done:
                continue
            done.add(key)
            px, py = pin_abs(p, x, y, rot, mirror)
            out = self._outward(p["angle"], rot, mirror)
            if net == "__unset__":
                if p["type"] == "no_connect":
                    continue
                raise ValueError(f"{ref}: pin {p['number']} ({p['name']}) has no net")
            if net is None or net == "NC":
                self.items.append([Sym("no_connect"), [Sym("at"), px, py], [Sym("uuid"), U(self.filename, ref, "nc", p["number"])]])
            elif net in POWER_SYMS:
                self.power(net, px, py, out)
            else:
                self.label(net, px, py, out)
        return uid

    def _outward(self, pin_angle, rot, mirror):
        a = pin_angle
        if mirror:
            a = (180 - a) % 360
        a = (a + rot) % 360
        return (a + 180) % 360  # direction away from body

    def _prop(self, k, v, x, y, hide=False):
        eff = [Sym("effects"), font()]
        if hide:
            eff.append([Sym("hide"), Sym("yes")])
        return [Sym("property"), k, v, [Sym("at"), x, y, 0], eff]

    # ---------------------------------------------------------- nets
    def label(self, net, x, y, out_angle):
        glob = net in self.globals
        ang = {0: 0, 90: 90, 180: 180, 270: 270}[int(out_angle) % 360]
        just = {0: "left", 180: "right", 90: "left", 270: "right"}[ang]
        if glob:
            node = [Sym("global_label"), net, [Sym("shape"), Sym("bidirectional")], [Sym("at"), x, y, ang],
                    [Sym("fields_autoplaced"), Sym("yes")],
                    [Sym("effects"), font(), [Sym("justify"), Sym(just)]],
                    [Sym("uuid"), U(self.filename, "gl", net, x, y)]]
        else:
            node = [Sym("label"), net, [Sym("at"), x, y, ang], [Sym("fields_autoplaced"), Sym("yes")],
                    [Sym("effects"), font(), [Sym("justify"), Sym(just), Sym("bottom")]],
                    [Sym("uuid"), U(self.filename, "l", net, x, y)]]
        self.items.append(node)

    def power(self, net, x, y, out_angle):
        lib_id = POWER_SYMS[net]
        if lib_id not in self.lib_ids:
            self.lib_ids.append(lib_id)
        self.pwr += 1
        ref = f"#PWR{self.page:02d}{self.pwr:03d}"
        # GND graphic points down by default, rail symbols point up
        if net == "GND":
            rot = {270: 0, 0: 90, 90: 180, 180: 270}[int(out_angle) % 360]
        else:
            rot = {90: 0, 180: 90, 270: 180, 0: 270}[int(out_angle) % 360]
        uid = U(self.filename, ref)
        node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), x, y, rot], [Sym("unit"), 1],
                [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
                [Sym("dnp"), Sym("no")], [Sym("uuid"), uid],
                self._prop("Reference", ref, x, y, hide=True), self._prop("Value", net, x, y + (2.54 if net == "GND" else -2.54)),
                self._prop("Footprint", "", x, y, hide=True), self._prop("Datasheet", "", x, y, hide=True),
                [Sym("pin"), "1", [Sym("uuid"), U(self.filename, ref, "p1")]],
                [Sym("instances"), [Sym("project"), PROJECT, [Sym("path"), self.path, [Sym("reference"), ref], [Sym("unit"), 1]]]]]
        self.items.append(node)

    def flag(self, net, x, y):
        self.pwr += 1
        return self.part("power:PWR_FLAG", f"#FLG{self.page:02d}{self.pwr:03d}", "PWR_FLAG", x, y, nets={"1": net})

    def text(self, s, x, y, size=2.0):
        self.items.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), x, y, 0],
                           [Sym("effects"), font(size), [Sym("justify"), Sym("left")]], [Sym("uuid"), U(self.filename, "t", s)]])

    # ---------------------------------------------------------- passives
    def R(self, ref, val, x, y, n1, n2, fp="Resistor_SMD:R_0603_1608Metric", rot=0, **kw):
        return self.part("Device:R", ref, val, x, y, rot, fp, {"1": n1, "2": n2}, **kw)

    def C(self, ref, val, x, y, n1, n2, fp="Capacitor_SMD:C_0603_1608Metric", rot=0, **kw):
        return self.part("Device:C", ref, val, x, y, rot, fp, {"1": n1, "2": n2}, **kw)

    def CP(self, ref, val, x, y, npos, nneg, fp, rot=0, **kw):
        return self.part("Device:C_Polarized", ref, val, x, y, rot, fp, {"1": npos, "2": nneg}, **kw)

    def L(self, ref, val, x, y, n1, n2, fp, rot=0, **kw):
        return self.part("Device:L", ref, val, x, y, rot, fp, {"1": n1, "2": n2}, **kw)

    # ---------------------------------------------------------- output
    def render(self, root=False, sheets=()):
        lib = [Sym("lib_symbols")] + [get_symbol(l) for l in self.lib_ids]
        out = [Sym("kicad_sch"), [Sym("version"), 20250114], [Sym("generator"), "eeschema"],
               [Sym("generator_version"), "9.0"], [Sym("uuid"), self.uuid], [Sym("paper"), self.paper],
               [Sym("title_block"), [Sym("title"), self.title], [Sym("date"), "2026-10-26"], [Sym("rev"), "0.1"],
                [Sym("company"), "Z2Labs - Bassberry (open hardware, CERN-OHL-S-2.0)"]],
               lib] + self.items
        for sh in sheets:
            out.append(sh)
        if root:
            out.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
        return dump(out) + "\n"


class Project:
    def __init__(self, outdir):
        self.outdir = outdir
        self.root = Sheet("root", "bassberry.kicad_sch", "Bassberry 2.1 - top level", 1)
        self.root.path = "/" + self.root.uuid
        self.children = []

    def child(self, name, filename, title, globals_=(), paper="A3"):
        sh = Sheet(name, filename, title, len(self.children) + 2, globals_, paper)
        sh.sheet_uuid = U("sheetsym", filename)
        sh.path = f"/{self.root.uuid}/{sh.sheet_uuid}"
        self.children.append(sh)
        return sh

    def write(self):
        os.makedirs(self.outdir, exist_ok=True)
        sheet_nodes = []
        for i, sh in enumerate(self.children):
            x, y = 30 + (i % 3) * 70, 40 + (i // 3) * 45
            sheet_nodes.append([Sym("sheet"), [Sym("at"), x, y], [Sym("size"), 55, 30],
                                [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
                                [Sym("dnp"), Sym("no")], [Sym("fields_autoplaced"), Sym("yes")],
                                [Sym("stroke"), [Sym("width"), 0.1524], [Sym("type"), Sym("solid")]],
                                [Sym("fill"), [Sym("color"), 0, 0, 0, 0.0]],
                                [Sym("uuid"), sh.sheet_uuid],
                                [Sym("property"), "Sheetname", sh.title, [Sym("at"), x, y - 0.7, 0],
                                 [Sym("effects"), font(), [Sym("justify"), Sym("left"), Sym("bottom")]]],
                                [Sym("property"), "Sheetfile", sh.filename, [Sym("at"), x, y + 30.6, 0],
                                 [Sym("effects"), font(), [Sym("justify"), Sym("left"), Sym("top")]]],
                                [Sym("instances"), [Sym("project"), PROJECT, [Sym("path"), self.root.path, [Sym("page"), str(sh.page)]]]]])
        open(os.path.join(self.outdir, self.root.filename), "w", encoding="utf-8").write(self.root.render(root=True, sheets=sheet_nodes))
        for sh in self.children:
            open(os.path.join(self.outdir, sh.filename), "w", encoding="utf-8").write(sh.render())
