"""
Builds the final 12-entry benchmark shortlist end-to-end:

  rcsb_2026_final_candidates.csv (3,745 vetted candidates)
    -> stratify into 4 resolution bins x 3 size tertiles (12 cells)
    -> per cell: fixed-seed random draw, chain_count <=15 feasibility
       cap only (no other filtering -- see CLAUDE.md Stage 4b for why
       the earlier chain-count-2-6 + median tie-break approach was
       dropped as selection bias)
    -> MMSeqs2 leakage screen against MICA's 549-entry training set
       (25% identity, 50% coverage -- the paper's own threshold),
       walk the randomized order, first clean candidate per cell wins
    -> enrich with protein_entity_count, best-hit diagnostics
    -> shortlist_12_v3_stratified_random.csv

Consolidates what was originally run as a sequence of one-off interactive
commands (see CLAUDE.md Stage 4b/5) into one reproducible script.

One manual override is hardcoded below, not derived from a rule:
small/low-res drew 10XW first, which cleared the screen (25.3% identity,
but only 27.4% coverage / 66 residues, E=36.5 -- statistically
insignificant, see CLAUDE.md). User's call was to avoid defending a
nominally-over-25%-identity number in the report even though it wasn't
real homology, so 10XW was swapped for 9K88 (rank 5 in the same cell's
draw order). That's a documented judgment call, not something the
threshold would produce automatically -- encoded explicitly here, not
hidden inside "the algorithm picked it."

Requires: mmseqs2 installed, training_sequences.fasta present (built by
the Stage 5 leakage-screen work), network access for RCSB FASTA fetches.
"""

import subprocess
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
FEASIBILITY_CAP_CHAINS = 15
MIN_IDENTITY = 0.25
MIN_COVERAGE = 0.5
BATCH_SIZE = 8

FINAL_CANDIDATES_CSV = "../../data/pool/rcsb_2026_final_candidates.csv"
SIZE_CSV = "../../data/pool/pdb_id_entry_size.csv"
TRAINING_FASTA = "../../data/benchmark/training_sequences.fasta"
OUTPUT_CSV = "../../data/benchmark/shortlist_12_v3_stratified_random.csv"
WORKDIR = Path("mmseqs_tmp_build")

RES_EDGES = [1.5, 2.2, 2.8, 3.4, 4.0]
RES_LABELS = ["near-atomic (<2.2)", "high (2.2-2.8)", "mid (2.8-3.4)", "low (3.4-4.0)"]
SIZE_LABELS = ["small", "medium", "large"]

# Documented judgment call, not a rule -- see module docstring / CLAUDE.md
MANUAL_OVERRIDES = {("small", "low (3.4-4.0)"): "9K88"}


def fetch_fasta(pdb_id, retries=3):
    for attempt in range(retries):
        try:
            r = subprocess.run(
                ["curl", "-sL", "-f", f"https://www.rcsb.org/fasta/entry/{pdb_id}"],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0 and r.stdout.startswith(">"):
                return r.stdout
        except subprocess.TimeoutExpired:
            continue
    return None


def mmseqs_leaked_ids(query_fasta_path):
    """Returns the set of pdb_ids in the query fasta that hit the training
    set at >= MIN_IDENTITY over >= MIN_COVERAGE (paper's own threshold)."""
    out_tsv = WORKDIR / "hits.tsv"
    tmp = WORKDIR / "tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    subprocess.run(
        ["mmseqs", "easy-search", str(query_fasta_path), TRAINING_FASTA, str(out_tsv), str(tmp),
         "--min-seq-id", str(MIN_IDENTITY), "-c", str(MIN_COVERAGE), "--cov-mode", "0",
         "--format-output", "query,target,pident,alnlen,evalue,bits"],
        capture_output=True, text=True,
    )
    leaked = set()
    if out_tsv.exists():
        with open(out_tsv) as f:
            for line in f:
                q = line.split("\t")[0]
                leaked.add(q.split("_")[0].split("|")[0])
    return leaked


def best_hit_stats(pdb_id, query_fasta_path):
    """Relaxed no-floor search for the real best-hit identity/coverage,
    for transparency (see CLAUDE.md's '0.0 artifact' verification note --
    the search-time --min-seq-id floor suppresses sub-threshold hits from
    being reported at all, which must not be conflated with 'no similarity')."""
    out_tsv = WORKDIR / f"verify_{pdb_id}.tsv"
    tmp = WORKDIR / f"tmp_verify_{pdb_id}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    subprocess.run(
        ["mmseqs", "easy-search", str(query_fasta_path), TRAINING_FASTA, str(out_tsv), str(tmp),
         "-s", "7.5", "-c", "0.0", "--cov-mode", "0", "-e", "100",
         "--format-output", "query,target,pident,alnlen,qlen,tlen,evalue,bits"],
        capture_output=True, text=True,
    )
    best = (0.0, 0.0, 0)
    if out_tsv.exists():
        with open(out_tsv) as f:
            for line in f:
                q, t, pident, alnlen, qlen, tlen, ev, bits = line.strip().split("\t")
                if q.split("_")[0].split("|")[0] != pdb_id:
                    continue
                pident = float(pident)
                if pident > best[0]:
                    cov = int(alnlen) / int(qlen) * 100 if int(qlen) else 0
                    best = (pident, cov, int(alnlen))
    return best


def main():
    final = pd.read_csv(FINAL_CANDIDATES_CSV)
    size = pd.read_csv(SIZE_CSV)
    df = final.merge(size, on="pdb_id", how="left")

    df["size_bin"] = pd.qcut(df["residue_count"], 3, labels=SIZE_LABELS)
    df["res_bin"] = pd.cut(df["resolution"], bins=RES_EDGES, labels=RES_LABELS, include_lowest=True)
    df_feasible = df[df["chain_count"] <= FEASIBILITY_CAP_CHAINS]

    WORKDIR.mkdir(exist_ok=True)
    rng = np.random.RandomState(SEED)
    picks = []

    for sb in SIZE_LABELS:
        for rb in RES_LABELS:
            key = (sb, rb)

            # Always draw the permutation for every cell, even when a manual
            # override exists -- the original interactive run generated the
            # full shuffled order for ALL 12 cells before any override was
            # applied, so skipping this call here would desync the RNG
            # stream for every cell that follows. Using the same fixed seed
            # only reproduces the same draws if every cell consumes the RNG
            # in the same sequence as the original run did.
            cell = df_feasible[(df_feasible["size_bin"] == sb) & (df_feasible["res_bin"] == rb)]
            ids = cell["pdb_id"].tolist()
            shuffled = [ids[i] for i in rng.permutation(len(ids))]

            if key in MANUAL_OVERRIDES:
                chosen = MANUAL_OVERRIDES[key]
                print(f"{sb:7} {rb:20} -> {chosen}  (manual override, see CLAUDE.md)")
            else:
                chosen = None
                for i in range(0, len(shuffled), BATCH_SIZE):
                    batch = shuffled[i:i + BATCH_SIZE]
                    fasta_path = WORKDIR / "batch.fasta"
                    with open(fasta_path, "w") as f:
                        for pid in batch:
                            seq = fetch_fasta(pid)
                            if seq:
                                f.write(seq)
                    leaked = mmseqs_leaked_ids(fasta_path)
                    for pid in batch:
                        if pid not in leaked:
                            chosen = pid
                            break
                    if chosen:
                        break
                print(f"{sb:7} {rb:20} -> {chosen}")

            row = df[df["pdb_id"] == chosen].iloc[0].to_dict()
            row["rank"] = None
            picks.append(row)

    out = pd.DataFrame(picks)

    # best-hit diagnostics, for transparency (not just pass/fail)
    ids_pct, cov_pct, alnlens = [], [], []
    for _, row in out.iterrows():
        pid = row["pdb_id"]
        seq = fetch_fasta(pid)
        fasta_path = WORKDIR / f"{pid}.fasta"
        with open(fasta_path, "w") as f:
            f.write(seq)
        pident, cov, alnlen = best_hit_stats(pid, fasta_path)
        ids_pct.append(round(pident, 1))
        cov_pct.append(round(cov, 1))
        alnlens.append(alnlen)

    out["best_hit_identity_pct"] = ids_pct
    out["best_hit_coverage_pct"] = cov_pct
    out["best_hit_alnlen"] = alnlens
    out["max_identity"] = 0.0  # legacy column name, kept for continuity; see best_hit_* for real values
    out["leakage_verdict"] = "CLEAN (below 25%/50%cov threshold; see best_hit_* columns for actual best match)"
    for key, pid in MANUAL_OVERRIDES.items():
        out.loc[out["pdb_id"] == pid, "leakage_verdict"] = (
            "CLEAN -- manually reviewed override, see CLAUDE.md Stage 4b/5 for full E-value writeup"
        )

    cols = ["pdb_id", "size_bin", "res_bin", "rank", "resolution", "residue_count",
            "chain_count", "protein_entity_count", "emdb_ids", "max_identity", "title",
            "best_hit_identity_pct", "best_hit_coverage_pct", "best_hit_alnlen", "leakage_verdict"]
    out = out[cols]
    out.to_csv(OUTPUT_CSV, index=False)

    print(f"\nSaved {len(out)} entries to {OUTPUT_CSV}")
    print(f"total protein_entity_count (= AF3 job count): {out['protein_entity_count'].sum()}")


if __name__ == "__main__":
    main()
