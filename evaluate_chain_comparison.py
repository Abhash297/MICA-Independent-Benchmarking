#!/usr/bin/env python3
"""
Run phenix.chain_comparison for all 4 methods against ground truth,
across all 12 real entries. Ground truth passed first (becomes
"target"), prediction second (becomes "query").
"""
import csv
import os
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path("/Users/abhashshrestha/Downloads/MICA-Experiment")
OUT_CSV = ROOT / "evaluation_chain_comparison.csv"
PHENIX_ENV = str(Path.home() / "phenix-2.2.1-6174/phenix_env.sh")

ENTRIES = {
    "62164": "9k88", "64568": "9uwy", "75023": "10ac", "65506": "9w0j",
    "76934": "13bv", "71787": "9pqo", "71973": "9pxl", "70609": "9om7",
    "64362": "9unu", "79027": "38pa", "67233": "9xti", "73799": "9z49",
}


def method_paths(emdb, stub):
    return {
        "MICA": ROOT / "mica_output" / f"{emdb}_{stub}_MICA_all_atom_model.pdb",
        "ModelAngelo": ROOT / "baseline_output/modelangelo" / emdb / f"{emdb}.cif",
        "CryoAtom": ROOT / "baseline_output/cryoatom" / emdb / f"{emdb}.cif",
        "EModelX": ROOT / "baseline_output/emodelx" / emdb / f"{stub}_EModelX(+AF)_all_atom_model.pdb",
    }


def ground_truth_path(emdb):
    matches = list((ROOT / "input" / emdb).glob("*_ground_truth.cif"))
    return matches[0] if matches else None


def parse_output(text):
    result = {"RMSD": None, "N_close": None, "N_far": None, "Forward": None,
              "Reverse": None, "Mixed": None, "Pct_found": None, "CA_score": None,
              "Seq_match_pct": None, "Seq_score": None, "Mean_length": None,
              "Fragments": None, "Bad_connections": None, "error": None}
    m = re.search(
        r"(?:Unique_target|Entire_target)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+"
        r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)",
        text)
    if m:
        (result["RMSD"], result["N_close"], result["N_far"], result["Forward"],
         result["Reverse"], result["Mixed"], result["Pct_found"], result["CA_score"],
         result["Seq_match_pct"], result["Seq_score"], result["Mean_length"],
         result["Fragments"], result["Bad_connections"]) = m.groups()
    else:
        result["error"] = "no_match_parsed"
    return result


def run_one(gt_path, pred_path):
    if not pred_path.exists():
        return {"error": f"missing_prediction: {pred_path}"}
    if not gt_path.exists():
        return {"error": f"missing_ground_truth: {gt_path}"}
    cmd = (f"source {shlex.quote(PHENIX_ENV)} && phenix.chain_comparison "
           f"pdb_in={shlex.quote(str(gt_path))} pdb_in={shlex.quote(str(pred_path))}")
    try:
        proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                               timeout=180, cwd=ROOT)
        if proc.returncode != 0:
            return {"error": f"rc{proc.returncode}: {proc.stderr[-300:]}"}
        return parse_output(proc.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def main():
    rows = []
    for emdb, stub in ENTRIES.items():
        gt_path = ground_truth_path(emdb)
        paths = method_paths(emdb, stub)
        for method, pred_path in paths.items():
            print(f"[{emdb}/{method}] ", end="", flush=True)
            result = run_one(gt_path, pred_path)
            row = {"emdb_num": emdb, "pdb_id": stub, "method": method, **result}
            rows.append(row)
            if result.get("error"):
                print(f"ERROR: {result['error']}")
            else:
                print(f"CA_score={result['CA_score']} RMSD={result['RMSD']} SeqMatch={result['Seq_match_pct']}%")

    fieldnames = ["emdb_num", "pdb_id", "method", "RMSD", "N_close", "N_far",
                  "Forward", "Reverse", "Mixed", "Pct_found", "CA_score",
                  "Seq_match_pct", "Seq_score", "Mean_length", "Fragments",
                  "Bad_connections", "error"]
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})
    print(f"\nSaved {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
