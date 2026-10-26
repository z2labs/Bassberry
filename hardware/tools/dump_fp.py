"""Print pad numbers of footprints: python dump_fp.py Lib:Name [...]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sexpr import parse, find
from kilib import KICAD_SHARE
for fid in sys.argv[1:]:
    lib, name = fid.split(":")
    p = os.path.join(KICAD_SHARE, "footprints", lib + ".pretty", name + ".kicad_mod")
    if not os.path.exists(p):
        print("MISSING", fid); continue
    t = parse(open(p, encoding="utf-8").read())
    pads = sorted({str(x[1]) for x in find(t, "pad")})
    print(fid, pads)
