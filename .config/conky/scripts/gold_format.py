#!/usr/bin/env python3
# gold_format.py — reads output from fetch_metals.sh and prints Conky-formatted text
# Place at: ~/scripts/gold_format.py

import json
import subprocess
import os
import sys

SCRIPT = os.path.expanduser("~/.config/conky/scripts/fetch_metals.sh")

try:
    raw = subprocess.check_output(["bash", SCRIPT], timeout=15).decode().strip()
    data = json.loads(raw)
    # handle both a single object {"sym":"AU",...} and an array [{"sym":"AU",...},...]
    if isinstance(data, list):
        gold = next(m for m in data if m["sym"] == "AU")
    else:
        gold = data
except Exception as e:
    print("Price:  --")
    print("Change: --")
    sys.exit(0)

p   = gold["price"]
d   = gold["delta_eur"]
pct = gold["delta_pct"]

sign  = "+" if d >= 0 else ""
arrow = "${color1}▲" if d > 0 else ("${color2}▼" if d < 0 else "─")
col   = "${color1}" if d > 0 else ("${color2}" if d < 0 else "${color3}")
reset = "${color}"

print(f"Price:  {p:,.2f} EUR")
print(f"Change: {arrow} {col}{sign}{d:.2f} EUR ({sign}{pct:.2f}%){reset}")
