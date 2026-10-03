#!/usr/bin/env python3
"""
Run US-align for all 4 methods (MICA, ModelAngelo, CryoAtom, EModelX)
against ground truth, across all 12 real entries. Multi-chain complex
alignment (-mm 1 -ter 1), TM-score normalized by the reference
structure (ground truth) per US-align's own recommendation.
"""
import csv
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USALIGN = ROOT / "tools/USalign/USalign"
OUT_CSV = ROOT / "data/evaluation/evaluation_usalign.csv"

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


def run_one(method, pred_path, gt_path):
    if not pred_path.exists():
        return {"error": f"missing_prediction: {pred_path}"}
    if not gt_path.exists():
        return {"error": f"missing_ground_truth: {gt_path}"}
    cmd = [str(USALIGN), str(pred_path), str(gt_path), "-mm", "1", "-ter", "1"]
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
        paths = method_paths(emdb, stub)
        for method, pred_path in paths.items():
            print(f"[{emdb}/{method}] ", end="", flush=True)
            result = run_one(method, pred_path, gt_path)
            row = {"emdb_num": emdb, "pdb_id": stub, "method": method, **result}
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
