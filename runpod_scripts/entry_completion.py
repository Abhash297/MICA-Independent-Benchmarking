#!/usr/bin/env python3
"""
Entry-level docking completion tracker. Run against a fresh pull of
docking_results.csv + per-entry domain counts to see how many of the
12 entries have enough docked domains for downstream MICA inference,
rather than just the raw domain-level completion rate (which undersells
progress, since MICA's map-only fallback means an entry doesn't need
100% of its domains docked to produce a usable result).

Usage:
  ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> \
    "cat /workspace/docking_results.csv" > /tmp/current_results.csv
  ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> \
    "for d in 79027 67233 73799 64362 75023 76934 70609 71973 64568 62164 71787 65506; \
     do n=\$(ls /workspace/input/\$d/AF3_domains/*.pdb 2>/dev/null | wc -l); echo \"\$d,\$n\"; done" \
    > /tmp/entry_domain_counts.csv
  python3 entry_completion.py
"""

import csv
from collections import OrderedDict, defaultdict

RESULTS = "/tmp/current_results.csv"
COUNTS = "/tmp/entry_domain_counts.csv"

totals = {}
with open(COUNTS) as f:
    for line in f:
        eid, n = line.strip().split(",")
        totals[eid] = int(n)

rows = list(csv.DictReader(open(RESULTS)))
latest = OrderedDict()
for r in rows:
    key = (r["emdb_num"], r["domain"])
    latest[key] = r  # last occurrence wins = most recent attempt

docked = defaultdict(int)
attempted = defaultdict(int)
for (eid, dom), r in latest.items():
    attempted[eid] += 1
    if r["status"] == "docked":
        docked[eid] += 1

print(f"{'Entry':<8}{'Docked':<8}{'Attempted':<11}{'Total':<7}{'% docked':<10}")
grand_docked, grand_total = 0, 0
for eid in totals:
    d, a, t = docked[eid], attempted[eid], totals[eid]
    pct = f"{100*d/t:.0f}%" if t else "n/a"
    print(f"{eid:<8}{d:<8}{a:<11}{t:<7}{pct:<10}")
    grand_docked += d
    grand_total += t

print(f"\nOverall: {grand_docked}/{grand_total} domains docked ({100*grand_docked/grand_total:.1f}%)")
print(f"Entries with >=1 domain docked: {sum(1 for e in totals if docked[e] > 0)}/12")
print(f"Entries with 100% of domains docked: {sum(1 for e in totals if docked[e] == totals[e])}/12")
