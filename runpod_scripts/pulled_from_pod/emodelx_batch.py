#!/usr/bin/env python3
"""Sequential EModelX(+AF) inference across all 12 real benchmark entries."""
import subprocess
import time
from pathlib import Path

INPUT_ROOT = Path("/workspace/input")
EMODELX_DIR = Path("/workspace/baselines/EModelX")
OUTPUT_ROOT = Path("/workspace/output_emodelx")
LOG_DIR = Path("/workspace/emodelx_logs")
PYTHON = "python3"

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

    if out_dir.exists() and any(out_dir.glob("*.pdb")):
        print(f"[SKIP] {emdb_num} already done")
        return

    if not map_path.exists():
        print(f"[WARN] {emdb_num}: no map, skipping")
        return

    # Use our own already-fetched AF3 structures as the template dir instead
    # of --download_afdb -- AFDB's own search API hung indefinitely when
    # tested (confirmed stuck across multiple checks, never a single retry
    # succeeded). AF3_structures/<SEQID>/ranked_0.pdb already matches
    # EModelX's manual template format exactly (confirmed working on 62164).
    template_dir = entry_dir / "AF3_structures"
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        PYTHON, "run.py",
        "--protocol=temp_flex",
        f"--EM_map={map_path}",
        f"--fasta={fasta_path}",
        f"--template_dir={template_dir}",
        f"--output_dir={out_dir}",
        "--run_pulchra", "--pulchra_path=modules/pulchra304/src/pulchra",
    ]

    start = time.time()
    with open(log_path, "w") as lf:
        proc = subprocess.run(cmd, cwd=EMODELX_DIR, stdout=lf, stderr=subprocess.STDOUT)
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
