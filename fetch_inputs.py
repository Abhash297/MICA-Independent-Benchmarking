"""
Pull FASTA sequences (RCSB) and cryo-EM density maps (EMDB) for the 12
shortlisted benchmark entries, laid out to match the directory structure
MICA's own pipeline expects (README "Directory Structure" section):

    input/
    └── <emdb_num>/
        ├── AF3_chains/, AF3_docked_models/, AF3_domains/, AF3_JSON/,
        │   AF3_PDBs/, AF3_results/, AF3_structures/   (empty, populated later)
        ├── <pdb_id_lower>.fasta
        └── emd_<emdb_num>.map

FASTA: https://www.rcsb.org/fasta/entry/{pdb_id}
Map:   https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{num}/map/emd_{num}.map.gz
       (downloaded gzipped, decompressed in place, .gz removed after)
"""

import csv
import gzip
import shutil
import subprocess
from pathlib import Path

SHORTLIST_CSV = "shortlist_12_v3_stratified_random.csv"
INPUT_DIR = Path("input")

FASTA_URL = "https://www.rcsb.org/fasta/entry/{}"
MAP_URL = "https://ftp.ebi.ac.uk/pub/databases/emdb/structures/EMD-{}/map/emd_{}.map.gz"

SUBDIRS = ["AF3_chains", "AF3_docked_models", "AF3_domains", "AF3_JSON",
           "AF3_PDBs", "AF3_results", "AF3_structures"]


def fetch_fasta(pdb_id, dest):
    result = subprocess.run(
        ["curl", "-sL", "-f", FASTA_URL.format(pdb_id)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 or not result.stdout.startswith(">"):
        print(f"  ERROR fetching FASTA for {pdb_id}: {result.stderr.strip()}")
        return False
    dest.write_text(result.stdout)
    return True


def fetch_map(emdb_num, dest_map, entry_dir):
    gz_path = entry_dir / f"emd_{emdb_num}.map.gz"
    url = MAP_URL.format(emdb_num, emdb_num)
    result = subprocess.run(
        ["curl", "-sL", "-f", "--retry", "3", "-o", str(gz_path), url],
        capture_output=True, text=True, timeout=3600,
    )
    if result.returncode != 0 or not gz_path.exists():
        print(f"  ERROR fetching map EMD-{emdb_num}: {result.stderr.strip()}")
        return False
    with gzip.open(gz_path, "rb") as f_in, open(dest_map, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    gz_path.unlink()
    return True


def main():
    with open(SHORTLIST_CSV, newline="") as f:
        rows = list(csv.DictReader(f))

    INPUT_DIR.mkdir(exist_ok=True)
    summary = []

    for row in rows:
        pdb_id = row["pdb_id"]
        emdb_num = row["emdb_ids"].split("-")[1]
        entry_dir = INPUT_DIR / emdb_num

        existing_fasta = entry_dir / f"{pdb_id.lower()}.fasta"
        existing_map = entry_dir / f"emd_{emdb_num}.map"
        if entry_dir.exists() and existing_fasta.exists() and existing_map.exists():
            print(f"[{pdb_id} / EMD-{emdb_num}] already fetched, skipping")
            summary.append({
                "pdb_id": pdb_id, "emdb_id": f"EMD-{emdb_num}",
                "fasta_ok": True, "fasta_size_kb": round(existing_fasta.stat().st_size / 1024, 1),
                "map_ok": True, "map_size_mb": round(existing_map.stat().st_size / 1e6, 1),
            })
            continue

        entry_dir.mkdir(exist_ok=True)
        for sub in SUBDIRS:
            (entry_dir / sub).mkdir(exist_ok=True)

        print(f"[{pdb_id} / EMD-{emdb_num}] fetching FASTA...")
        fasta_path = entry_dir / f"{pdb_id.lower()}.fasta"
        fasta_ok = fetch_fasta(pdb_id, fasta_path)

        print(f"[{pdb_id} / EMD-{emdb_num}] fetching map (this can take a while)...")
        map_path = entry_dir / f"emd_{emdb_num}.map"
        map_ok = fetch_map(emdb_num, map_path, entry_dir)

        summary.append({
            "pdb_id": pdb_id,
            "emdb_id": f"EMD-{emdb_num}",
            "fasta_ok": fasta_ok,
            "fasta_size_kb": round(fasta_path.stat().st_size / 1024, 1) if fasta_ok else None,
            "map_ok": map_ok,
            "map_size_mb": round(map_path.stat().st_size / 1e6, 1) if map_ok else None,
        })

    print("\n--- Summary ---")
    for s in summary:
        status = "OK" if s["fasta_ok"] and s["map_ok"] else "INCOMPLETE"
        print(f"{s['pdb_id']:6} {s['emdb_id']:12} fasta={s['fasta_size_kb']}KB  "
              f"map={s['map_size_mb']}MB  [{status}]")

    failed = [s for s in summary if not (s["fasta_ok"] and s["map_ok"])]
    if failed:
        print(f"\n{len(failed)} entries incomplete: {[s['pdb_id'] for s in failed]}")
    else:
        print(f"\nAll {len(summary)} entries fetched successfully.")


if __name__ == "__main__":
    main()
