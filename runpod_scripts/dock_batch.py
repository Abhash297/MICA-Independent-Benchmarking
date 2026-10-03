#!/usr/bin/env python3
"""
Worker-pool batch docking across all 12 MICA benchmark entries.

Runs on the RunPod instance. Pulls every (entry, domain) pair from
input/<emdb_num>/AF3_domains/*.pdb across all entries, and processes
them through a bounded worker pool calling phenix.dock_in_map directly
(not through MICA's own wrapper, which processes domains serially per
entry and has no real timeout enforcement).

Config validated locally on 2026-09-29: nproc=4, quick=True, min_cc=0.2,
resolution=native+~2. Kept here as per-job defaults; nproc lowered
slightly per job since we're now running many jobs concurrently on
shared hardware (32 vCPU / 128GB RAM) rather than one job alone.
"""

import csv
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import mrcfile
import numpy as np

# ---- config ----------------------------------------------------------

INPUT_ROOT = Path("/workspace/input")
PHENIX_ENV = "/workspace/phenix-2.2.1-6174/phenix_env.sh"
MAX_WORKERS = 4            # lowered from 7 after hitting 121/128GB cgroup limit on large-map
                            # entries (67233/73799): individual jobs measured at 8-20GB RSS on
                            # those maps (vs ~1.7-5GB on the small maps used for local validation)
                            # -- dock_chains_individually=True loads the FULL map for every domain
                            # regardless of that domain's own size, so large-map entries are
                            # expensive for every job, not just some. Cores were never the real
                            # constraint; memory is, and 7 concurrent large-map jobs (~140GB
                            # worst case) blew past the 128GB cap causing cascading SIGKILLs.
NPROC_PER_JOB = 4
QUICK = True
MIN_CC = 0.2
JOB_TIMEOUT_SEC = 45 * 60  # real enforced timeout (the local wrapper's was dead code)
RESULTS_CSV = Path("/workspace/docking_results.csv")

# emdb_num -> (fasta_stub, contour_level, resolution_for_docking)
#
# contour_level fetched fresh from EMDB's own API per entry via
# utils/emdb_extractor.py on 2026-09-29 -- NOT a universal constant.
# Earlier assumption of 0.02 for every entry was wrong (only correct
# for 62164 by coincidence); 64568/9UWY's live test tonight actually
# ran with the wrong value (0.02 instead of 0.2), which is a more
# likely explanation for that domain's long non-completion than the
# pseudo-symmetry theory logged in CLAUDE.md Stage 12b -- correct there
# once this is confirmed. 71787/9PQO's contour (4.8) is a real outlier
# vs the rest (0.02-0.32 range) -- worth a sanity check once docked.
#
# resolution = native + ~2 A per Phenix's own docs guidance, EXCEPT 76934
# which uses EMDB's own resolution (3.26) instead of RCSB's (3.77) --
# see CLAUDE.md Stage 11 cross-database discrepancy note.
# Ordered by domain count ascending, untouched entries first -- 67233
# and 73799 pushed to the end despite being defined "naturally" earlier,
# since both have already eaten significant budget for ~0% success and
# have the most domains left (12 and 17-24 respectively). Given finite
# remaining budget, prioritizing broad entry-level coverage (at least
# 1-2 docked domains per entry, so every entry gets SOME AF3-fusion
# signal rather than falling back to pure map-only mode) over finishing
# the two hardest entries first. See CLAUDE.md Stage 13d/13e reasoning.
ENTRIES = {
    "62164": ("9k88", 0.02,  6.0),    # 2 domains, untouched
    "64568": ("9uwy", 0.2,   4.5),    # 6 domains, untouched -- was 0.02 in tonight's live test, wrong
    "75023": ("10ac", 0.1,   4.5),    # 8 domains, untouched
    "65506": ("9w0j", 0.04,  4.1),    # 8 domains, untouched
    "76934": ("13bv", 0.2,   5.3),    # 10 domains, untouched -- native 3.26 (EMDB) + 2, not RCSB's 3.77
    "71787": ("9pqo", 4.8,   5.1),    # 12 domains, untouched -- outlier contour scale, sanity-check once docked
    "71973": ("9pxl", 0.233, 4.1),    # 13 domains, untouched
    "70609": ("9om7", 0.2,   5.3),    # 18 domains, untouched
    "64362": ("9unu", 0.11,  4.2),    # 22 domains, untouched
    "79027": ("38pa", 0.145, 4.7),    # 12 domains, 8/12 already docked -- good coverage already
    "67233": ("9xti", 0.1,   5.7),    # 12 domains, 0/12 success so far -- poor ROI, deprioritized
    "73799": ("9z49", 0.32,  5.1),    # 24 domains, 0/7 success so far -- poor ROI, deprioritized, largest remaining
}


def preprocess_maps():
    """
    Apply contour-level thresholding to each entry's raw map, once,
    before any domain jobs run -- replicates MICA's own wrapper
    (utils/dock_in_map.py:initial_map_processing), which this
    worker-pool script bypasses for the actual docking calls but still
    needs for this one shared preprocessing step.
    """
    for emdb_num, (fasta_stub, contour, _resolution) in ENTRIES.items():
        entry_dir = INPUT_ROOT / emdb_num
        raw_map = entry_dir / f"emd_{emdb_num}.map"
        temp_dir = entry_dir / "temp_maps"
        temp_dir.mkdir(exist_ok=True)
        out_path = temp_dir / "initial_processed.mrc"
        if out_path.exists():
            continue  # resumable
        if not raw_map.exists():
            print(f"[WARN] no raw map for {emdb_num} at {raw_map}, skipping preprocessing")
            continue
        print(f"[INFO] preprocessing {emdb_num} (contour={contour})")
        with mrcfile.open(raw_map, mode="r") as mrc:
            data = mrc.data.copy()
            voxel_size = mrc.voxel_size
            origin = mrc.header.origin
        clipped = np.where(data < contour, 0, data)
        with mrcfile.new(out_path, overwrite=True) as mrc:
            mrc.set_data(clipped.astype(np.float32))
            mrc.voxel_size = voxel_size
            mrc.header.origin = origin
        print(f"[INFO] wrote {out_path}")


def discover_jobs():
    """Find every (emdb_num, domain_pdb_path) not yet docked."""
    jobs = []
    for emdb_num in ENTRIES:
        entry_dir = INPUT_ROOT / emdb_num
        domains_dir = entry_dir / "AF3_domains"
        docked_dir = entry_dir / "AF3_docked_models"
        docked_dir.mkdir(exist_ok=True)
        if not domains_dir.exists():
            print(f"[WARN] no AF3_domains dir for {emdb_num}, skipping")
            continue
        for domain_pdb in sorted(domains_dir.glob("*.pdb")):
            out_name = domain_pdb.stem + "_docked.pdb"
            out_path = docked_dir / out_name
            if out_path.exists():
                continue  # resumable: skip already-docked domains
            jobs.append((emdb_num, domain_pdb))
    return jobs


def run_one_domain(job):
    emdb_num, domain_pdb = job
    fasta_stub, contour, resolution = ENTRIES[emdb_num]
    entry_dir = INPUT_ROOT / emdb_num
    map_path = entry_dir / "temp_maps" / "initial_processed.mrc"
    fasta_path = entry_dir / f"{fasta_stub}.fasta"
    docked_dir = entry_dir / "AF3_docked_models"
    out_path = docked_dir / (domain_pdb.stem + "_docked.pdb")
    log_dir = entry_dir / "docking_logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{domain_pdb.stem}.log"

    cmd = (
        f"source {PHENIX_ENV} && phenix.dock_in_map "
        f"search_model={domain_pdb} map_file={map_path} "
        f"nproc={NPROC_PER_JOB} quick={QUICK} min_cc={MIN_CC} "
        f"resolution={resolution} pdb_out={out_path} "
        f"dock_chains_individually=True sequence={fasta_path}"
    )

    start = time.time()
    status = "unknown"
    final_cc = None
    proc = None
    try:
        with open(log_path, "w") as lf:
            # start_new_session=True puts bash -c (and everything it
            # spawns, including the actual phenix.dock_in_map process)
            # in its own process group, so a timeout kill can take out
            # the whole tree -- not just the top-level bash wrapper.
            # subprocess.run's own timeout=... only signals the direct
            # child, which left orphaned phenix processes running
            # locally tonight; this avoids repeating that on the pod.
            proc = subprocess.Popen(
                ["bash", "-c", cmd],
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                returncode = proc.wait(timeout=JOB_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait()  # reap the zombie after killing the group
                raise

        elapsed = time.time() - start
        if returncode == 0 and out_path.exists():
            status = "docked"
            log_text = log_path.read_text(errors="ignore")
            # actual observed success line (verified against tonight's
            # real log, not guessed): "Wrote placed model with CC_mask
            # (local CC) = 0.28 to ..."
            m = re.search(r"Wrote placed model with CC_mask[^=]*=\s*([\d.]+)", log_text)
            if not m:
                m = re.search(r"Final map-model cc \(CC_mask\):\s*([\d.]+)", log_text)
            if m:
                final_cc = float(m.group(1))
        elif returncode == 0:
            status = "completed_no_output"  # likely dropped, low CC
        else:
            status = f"failed_rc{returncode}"
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        status = "timeout"
    except Exception as e:
        elapsed = time.time() - start
        status = f"error_{type(e).__name__}"

    return {
        "emdb_num": emdb_num,
        "domain": domain_pdb.name,
        "status": status,
        "final_cc": final_cc,
        "elapsed_sec": round(elapsed, 1),
    }


def main():
    preprocess_maps()
    jobs = discover_jobs()
    print(f"[INFO] {len(jobs)} domains queued across {len(ENTRIES)} entries")
    if not jobs:
        print("[INFO] nothing to do")
        return

    write_header = not RESULTS_CSV.exists()
    with open(RESULTS_CSV, "a", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["emdb_num", "domain", "status", "final_cc", "elapsed_sec"],
        )
        if write_header:
            writer.writeheader()

        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(run_one_domain, job): job for job in jobs}
            for i, future in enumerate(as_completed(futures), 1):
                res = future.result()
                writer.writerow(res)
                csvfile.flush()
                print(
                    f"[{i}/{len(jobs)}] {res['emdb_num']}/{res['domain']}: "
                    f"{res['status']} (CC={res['final_cc']}, "
                    f"{res['elapsed_sec']}s)"
                )


if __name__ == "__main__":
    main()
