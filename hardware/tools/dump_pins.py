"""Print pin lists of library symbols: python dump_pins.py Lib:Name [...] > out.txt"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from kilib import get_symbol, pins

for lid in sys.argv[1:]:
    s = get_symbol(lid)
    print(f"== {lid}")
    for p in sorted(pins(s), key=lambda p: (p["x"], -p["y"])):
        print(f'{p["number"]:>4} {p["name"]:<14} {p["type"]:<14} ({p["x"]:.2f},{p["y"]:.2f}) a{p["angle"]:.0f}')
