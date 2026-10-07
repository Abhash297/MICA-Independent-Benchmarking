#!/usr/bin/env python3
"""
Run US-align for CryoZeta (5th method) against ground truth, across
the 10 complete entries (67233/73799 excluded -- partial, 3/4 and
9/12 chains respectively, not comparable to a complete structure).
Same tool/flags as evaluate_usalign.py's other 4 methods.
"""
import csv
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USALIGN = ROOT / "tools/USalign/USalign"
OUT_CSV = ROOT / "data/evaluation/evaluation_usalign_cryozeta.csv"

ENTRIES = {
    "62164": "9k88", "64568": "9uwy", "75023": "10ac", "65506": "9w0j",
    "76934": "13bv", "71787": "9pqo", "71973": "9pxl", "70609": "9om7",
    "64362": "9unu", "79027": "38pa",
}


def pred_path(emdb):
    return ROOT / "baseline_output/cryozeta" / emdb / f"{emdb}.cif"


def ground_truth_path(emdb, stub):
    matches = list((ROOT / "input" / emdb).glob("*_ground_truth.cif"))
    return matches[0] if matches else None


def parse_usalign_output(text):
    result = {"TM_score_ref": None, "TM_score_query": None, "RMSD": None,
              "Seq_ID": None, "Aligned_length": None, "error": None}
    m = re.search(r"Aligned length=\s*(\d+),\s*RMSD=\s*([\d.]+),\s*Seq_ID=\S+=\s*([\d.]+)", text)
    if m:
        result["Aligned_length"] = int(m.group(1))
        result["RMSD"] = float(m.group(2))
        result["Seq_ID"] = float(m.group(3))
    tm_lines = re.findall(r"TM-score=\s*([\d.]+)\s*\(normalized by length of Structure_([12])", text)
    for score, struct_num in tm_lines:
        if struct_num == "1":
            result["TM_score_query"] = float(score)
        else:
            result["TM_score_ref"] = float(score)
    if result["TM_score_ref"] is None and "error" not in text.lower():
        result["error"] = "no_tmscore_parsed"
    return result


def run_one(pred, gt_path):
    if not pred.exists():
        return {"error": f"missing_prediction: {pred}"}
    if not gt_path.exists():
        return {"error": f"missing_ground_truth: {gt_path}"}
    cmd = [str(USALIGN), str(pred), str(gt_path), "-mm", "1", "-ter", "1"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return {"error": f"usalign_rc{proc.returncode}: {proc.stderr[:300]}"}
        return parse_usalign_output(proc.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def main():
    rows = []
    for emdb, stub in ENTRIES.items():
        gt_path = ground_truth_path(emdb, stub)
        pred = pred_path(emdb)
        print(f"[{emdb}/CryoZeta] ", end="", flush=True)
        result = run_one(pred, gt_path)
        row = {"emdb_num": emdb, "pdb_id": stub, "method": "CryoZeta", **result}
        rows.append(row)
        if result.get("error"):
            print(f"ERROR: {result['error']}")
        else:
            print(f"TM-score(ref)={result['TM_score_ref']} RMSD={result['RMSD']}")

    fieldnames = ["emdb_num", "pdb_id", "method", "TM_score_ref", "TM_score_query",
                  "RMSD", "Seq_ID", "Aligned_length", "error"]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})
    print(f"\nSaved {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
