#!/usr/bin/env python3
"""
Select each CryoZeta entry's genuine top-ranked structure from the raw
per-entry output and copy it into baseline_output/cryozeta/<entry>/<entry>.cif
for scoring.

Reconstructs combine.py's own selection logic directly from first
principles (scores.csv + the method-specific predictions_<method>/
subfolders) rather than depending on a cached CryoZeta-Final/ folder,
which may not exist for every entry (e.g. it never ran at all for
entries where the process crashed/timed out before reaching combine.py
-- see CRYOZETA_STATUS.md's COMBINE_RAN/RAW_RECOVERY distinction. That
folder may also simply no longer be present locally even for entries
where it once existed, if local disk space was reclaimed).

Logic (matches combine.py's fixed version, documented in
CRYOZETA_STATUS.md's Appendix): read scores.csv from both the
standard (CryoZeta/) and Interpolate (CryoZeta-Interpolate/) passes
where present, merge, sort all rows by recall_ccmask_ca descending,
and the top row's (sample_idx, method, pass) selects the file at
{pass_dir}/seed_101/predictions_{method}/{entry}_sample_{sample_idx}.cif
"""
import csv
import glob
import os
import shutil

RAW_BASE = (
    "/Users/abhashshrestha/Downloads/MICA-Experiment-Backup/MICA-Experiment/"
    "baseline_output/cryozeta/output_standard"
)
DEST_BASE = "/Users/abhashshrestha/Downloads/MICA-Experiment/baseline_output/cryozeta"

ENTRIES = ["62164", "64568", "75023", "65506", "76934",
           "71787", "71973", "70609", "64362", "79027"]


def load_scores(entry):
    # scores.csv location isn't uniform across entries -- some still have
    # it nested under CryoZeta/saved_data/ or CryoZeta-Interpolate/saved_data/,
    # others only have a flat copy under provenance/ (from the A100-sync).
    # Search broadly rather than assume one layout.
    paths = glob.glob(f"{RAW_BASE}/{entry}/**/scores.csv", recursive=True)
    if not paths:
        raise FileNotFoundError(f"{entry}: no scores.csv found anywhere")
    rows = []
    for path in paths:
        rows.extend(csv.DictReader(open(path)))
    return rows


def top_pick_path(entry):
    rows = load_scores(entry)
    rows.sort(key=lambda r: float(r["recall_ccmask_ca"]), reverse=True)
    top = rows[0]
    sample_idx, method = top["sample_idx"], top["method"]

    # Native/combine.py-produced entries have per-method subfolders
    # (predictions_svd_0.8/, predictions_teaser/, etc.) -- try that first.
    matches = glob.glob(
        f"{RAW_BASE}/{entry}/**/predictions_{method}/{entry}_sample_{sample_idx}.cif",
        recursive=True,
    )
    if matches:
        return matches[0], top

    # Raw-tensor recovery (recover_from_output_dict.py) doesn't re-run
    # registration per method -- it dumps one file per sample index into
    # a flat predictions/ folder regardless of which method scores.csv
    # says was best for that sample. Fall back to that.
    matches = glob.glob(
        f"{RAW_BASE}/{entry}/**/predictions/{entry}_sample_{sample_idx}.cif",
        recursive=True,
    )
    if matches:
        return matches[0], top

    raise FileNotFoundError(
        f"{entry}: expected top pick not found "
        f"(sample_idx={sample_idx}, method={method}, recall_ccmask_ca={top['recall_ccmask_ca']})"
    )


def main():
    for entry in ENTRIES:
        src, top = top_pick_path(entry)
        dest_dir = f"{DEST_BASE}/{entry}"
        os.makedirs(dest_dir, exist_ok=True)
        dest = f"{dest_dir}/{entry}.cif"
        shutil.copy(src, dest)
        print(f"{entry}: sample_idx={top['sample_idx']} method={top['method']} "
              f"recall_ccmask_ca={float(top['recall_ccmask_ca']):.4f} -> {dest}")


if __name__ == "__main__":
    main()
