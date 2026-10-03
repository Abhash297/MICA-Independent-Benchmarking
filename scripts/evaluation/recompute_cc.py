#!/usr/bin/env python3
"""Independent CC_mask recomputation for the 6 'unknown' domains flagged in
FAILED_CASES.md's FINAL tally (log-vs-disk mismatch, CC unverified), plus
every other docked file in the same 3 entries for a complete, authoritative
re-check (method validated against 2 already-known values first — see
CLAUDE.md Stage 20)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHENIX_ENV = str(Path.home() / "phenix-2.2.1-6174/phenix_env.sh")

ENTRIES = {
    "70609": ("9om7", 5.3),
    "71787": ("9pqo", 5.1),
    "79027": ("38pa", 4.7),
}


def run_one(model_path, map_path, resolution):
    cmd = (f"source {PHENIX_ENV} && phenix.map_correlations "
           f"'{model_path}' '{map_path}' resolution={resolution}")
    proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return {"error": f"rc{proc.returncode}: {proc.stderr[-300:]}"}
    m = re.search(
        r"CC_mask\s*:\s*([\-\d.]+)\s*\n\s*CC_volume:\s*([\-\d.]+)\s*\n\s*CC_peaks\s*:\s*([\-\d.]+)",
        proc.stdout)
    if not m:
        return {"error": "no_cc_parsed"}
    return {"cc_mask": float(m.group(1)), "cc_volume": float(m.group(2)),
            "cc_peaks": float(m.group(3)), "error": None}


def main():
    rows = []
    for emdb, (stub, resolution) in ENTRIES.items():
        docked_dir = ROOT / "input" / emdb / "AF3_docked_models"
        map_path = ROOT / "input" / emdb / f"emd_{emdb}.map"
        for model_path in sorted(docked_dir.glob("*_docked.pdb")):
            print(f"[{emdb}/{model_path.name}] ", end="", flush=True)
            result = run_one(model_path, map_path, resolution)
            domain = model_path.stem.replace("_docked", "")
            row = {"emdb_num": emdb, "domain": domain, **result}
            rows.append(row)
            if result.get("error"):
                print(f"ERROR: {result['error']}")
            else:
                genuine = "GENUINE" if result["cc_mask"] >= 0.2 else "low-CC"
                print(f"CC_mask={result['cc_mask']:.4f} ({genuine})")

    print("\n=== Summary per entry ===")
    for emdb in ENTRIES:
        entry_rows = [r for r in rows if r["emdb_num"] == emdb and not r.get("error")]
        genuine = [r for r in entry_rows if r["cc_mask"] >= 0.2]
        print(f"{emdb}: {len(genuine)}/{len(entry_rows)} genuine (CC_mask>=0.2)")
        for r in entry_rows:
            flag = "GENUINE" if r["cc_mask"] >= 0.2 else "low"
            print(f"    {r['domain']}: {r['cc_mask']:.4f} [{flag}]")

    import csv
    out_csv = ROOT / "data/docking/cc_recomputation_unknown_domains.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["emdb_num", "domain", "cc_mask", "cc_volume", "cc_peaks", "error"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"\nSaved {len(rows)} rows to {out_csv}")


if __name__ == "__main__":
    main()
