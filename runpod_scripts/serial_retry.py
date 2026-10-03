#!/usr/bin/env python3
"""
Serial (one-at-a-time) retry pass for domains that failed via `timeout`
or `failed_rc-9` in the main parallel batch (dock_batch.py).

Rationale (CLAUDE.md Stage 13f): under 4-worker concurrency, a single
`nproc=4` job was measured running 35 actual OS threads -- 140 total
across 4 concurrent jobs, competing for 32 physical cores (~4.4x
oversubscription). Running one job at a time gives it genuinely
uncontended access to the whole pod, which should help both:
  - `timeout` cases: the job was still searching (not crashed) when
    cut off -- thread contention was plausibly the biggest drag on it
    actually finishing within 45 minutes.
  - `failed_rc-9` cases: only one job's memory footprint is active at
    a time instead of 4 competing simultaneously, reducing OOM risk.

Reuses dock_batch.py's actual tested run_one_domain() function rather
than duplicating the subprocess/timeout/logging logic -- avoids
copy-paste drift between the two scripts.

Usage (on the pod, after the main parallel pass has gone through all
12 entries at least once):
  /workspace/phenix-2.2.1-6174/bin/python3.11 serial_retry.py
"""

import csv
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, "/workspace")
from dock_batch import ENTRIES, INPUT_ROOT, RESULTS_CSV, run_one_domain  # noqa: E402

SERIAL_RESULTS_CSV = Path("/workspace/docking_results_serial.csv")
RETRY_STATUSES = {"timeout", "failed_rc-9"}


def find_retry_targets():
    """Domains that failed via timeout/rc-9 in the main CSV AND still
    have no valid output file (double-checks the filesystem, not just
    the CSV -- a domain could have been manually resolved since, e.g.
    the local-result transfer trick used for 62164 domain_02)."""
    if not RESULTS_CSV.exists():
        print(f"[WARN] {RESULTS_CSV} not found -- nothing to retry")
        return []

    rows = list(csv.DictReader(open(RESULTS_CSV)))
    latest = OrderedDict()
    for r in rows:
        key = (r["emdb_num"], r["domain"])
        latest[key] = r  # last occurrence = most recent attempt

    targets = []
    for (emdb_num, domain_name), r in latest.items():
        if r["status"] not in RETRY_STATUSES:
            continue
        if emdb_num not in ENTRIES:
            continue
        domain_pdb = INPUT_ROOT / emdb_num / "AF3_domains" / domain_name
        docked_dir = INPUT_ROOT / emdb_num / "AF3_docked_models"
        out_path = docked_dir / (domain_pdb.stem + "_docked.pdb")
        if out_path.exists():
            continue  # already resolved since the CSV row was written
        if not domain_pdb.exists():
            print(f"[WARN] {domain_pdb} missing, skipping")
            continue
        targets.append((emdb_num, domain_pdb))
    return targets


def main():
    targets = find_retry_targets()
    print(f"[INFO] {len(targets)} domains queued for serial retry "
          f"(status was timeout/failed_rc-9, no valid output yet)")
    if not targets:
        return

    write_header = not SERIAL_RESULTS_CSV.exists()
    with open(SERIAL_RESULTS_CSV, "a", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["emdb_num", "domain", "status", "final_cc", "elapsed_sec"],
        )
        if write_header:
            writer.writeheader()

        for i, job in enumerate(targets, 1):
            emdb_num, domain_pdb = job
            print(f"[{i}/{len(targets)}] retrying {emdb_num}/{domain_pdb.name} "
                  f"(isolated, no concurrent jobs)...")
            res = run_one_domain(job)
            writer.writerow(res)
            csvfile.flush()
            print(f"  -> {res['status']} (CC={res['final_cc']}, "
                  f"{res['elapsed_sec']}s)")


if __name__ == "__main__":
    main()
