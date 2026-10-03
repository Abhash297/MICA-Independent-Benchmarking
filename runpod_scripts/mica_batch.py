#!/usr/bin/env python3
"""
Sequential MICA inference across all 12 real benchmark entries.

Runs on the GPU pod. One GPU, so sequential not parallel (unlike the
CPU docking worker-pool). Each entry gets its own run.py invocation,
pointed at that entry's real map + fasta + docked models (AF3_docked_models,
whatever subset Phenix actually produced -- MICA's own map-only
fallback handles entries with sparse/zero docking coverage).

Resumable: skips any entry whose final output file already exists.
"""

import subprocess
import sys
import time
from pathlib import Path

INPUT_ROOT = Path("/workspace/input")
MICA_DIR = Path("/workspace/MICA")
OUTPUT_ROOT = Path("/workspace/output")
LOG_DIR = Path("/workspace/mica_logs")

# emdb_num -> (fasta_stub, resolution) -- same resolution values used for
# Phenix docking (native + ~2A), reused here for MICA's own map-model fit.
ENTRIES = {
    "62164": ("9k88", 6.0),
    "64568": ("9uwy", 4.5),
    "75023": ("10ac", 4.5),
    "65506": ("9w0j", 4.1),
    "76934": ("13bv", 5.3),
    "71787": ("9pqo", 5.1),
    "71973": ("9pxl", 4.1),
    "70609": ("9om7", 5.3),
    "64362": ("9unu", 4.2),
    "79027": ("38pa", 4.7),
    "67233": ("9xti", 5.7),
    "73799": ("9z49", 5.1),
}


def run_one(emdb_num, fasta_stub, resolution):
    entry_dir = INPUT_ROOT / emdb_num
    map_path = entry_dir / f"emd_{emdb_num}.map"
    fasta_path = entry_dir / f"{fasta_stub}.fasta"
    af3_dir = entry_dir / "AF3_results"
    out_path = OUTPUT_ROOT / f"{emdb_num}_{fasta_stub}_MICA_all_atom_model.pdb"
    log_path = LOG_DIR / f"{emdb_num}.log"

    if out_path.exists():
        print(f"[SKIP] {emdb_num} already done: {out_path}")
        return

    if not map_path.exists():
        print(f"[WARN] {emdb_num}: no map at {map_path}, skipping")
        return

    combined_docked = entry_dir / f"{emdb_num}_af3_docked.pdb"
    mode = "domain-fusion" if combined_docked.exists() else "map-only"
    print(f"[INFO] {emdb_num} ({fasta_stub}): mode={mode}, resolution={resolution}")

    cmd = [
        "python3", "run.py",
        "-m", str(map_path),
        "-f", str(fasta_path),
        "-a", str(af3_dir),
        "--run_pulchra", "--pulchra_path=modules/pulchra304/src/pulchra",
        "--resolution", str(resolution),
        "--device", "cuda",
        "-o", str(OUTPUT_ROOT),
    ]

    start = time.time()
    with open(log_path, "w") as lf:
        proc = subprocess.run(cmd, cwd=MICA_DIR, stdout=lf, stderr=subprocess.STDOUT)
    elapsed = time.time() - start

    status = "OK" if proc.returncode == 0 and out_path.exists() else f"FAILED(rc={proc.returncode})"
    print(f"[{status}] {emdb_num}: {elapsed:.1f}s")
    return status, elapsed


def main():
    OUTPUT_ROOT.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    for i, (emdb_num, (fasta_stub, resolution)) in enumerate(ENTRIES.items(), 1):
        print(f"\n=== [{i}/12] {emdb_num} ===")
        run_one(emdb_num, fasta_stub, resolution)
    print("\n=== ALL 12 ENTRIES PROCESSED ===")


if __name__ == "__main__":
    main()
