#!/usr/bin/env python3
"""Sequential ModelAngelo inference across all 12 real benchmark entries."""
import subprocess
import time
from pathlib import Path

INPUT_ROOT = Path("/workspace/input")
OUTPUT_ROOT = Path("/workspace/output_modelangelo")
LOG_DIR = Path("/workspace/modelangelo_logs")
BINARY = "/root/miniconda3/envs/model_angelo/bin/model_angelo"

ENTRIES = {
    "62164": "9k88", "64568": "9uwy", "75023": "10ac", "65506": "9w0j",
    "76934": "13bv", "71787": "9pqo", "71973": "9pxl", "70609": "9om7",
    "64362": "9unu", "79027": "38pa", "67233": "9xti", "73799": "9z49",
}


def run_one(emdb_num, fasta_stub):
    entry_dir = INPUT_ROOT / emdb_num
    map_path = entry_dir / f"emd_{emdb_num}.map"
    fasta_path = entry_dir / f"{fasta_stub}.fasta"
    out_dir = OUTPUT_ROOT / emdb_num
    log_path = LOG_DIR / f"{emdb_num}.log"

    if (out_dir / "output.cif").exists() or (out_dir / "model_angelo_output.pdb").exists():
        print(f"[SKIP] {emdb_num} already done")
        return

    if not map_path.exists():
        print(f"[WARN] {emdb_num}: no map, skipping")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [BINARY, "build", "-v", str(map_path), "-f", str(fasta_path), "-o", str(out_dir)]

    start = time.time()
    with open(log_path, "w") as lf:
        proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT)
    elapsed = time.time() - start
    status = "OK" if proc.returncode == 0 else f"FAILED(rc={proc.returncode})"
    print(f"[{status}] {emdb_num}: {elapsed:.1f}s")


def main():
    OUTPUT_ROOT.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    for i, (emdb_num, fasta_stub) in enumerate(ENTRIES.items(), 1):
        print(f"\n=== [{i}/12] {emdb_num} ===")
        run_one(emdb_num, fasta_stub)
    print("\n=== ALL 12 ENTRIES PROCESSED ===")


if __name__ == "__main__":
    main()
