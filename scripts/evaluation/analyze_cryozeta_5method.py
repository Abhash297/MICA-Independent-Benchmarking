#!/usr/bin/env python3
"""
5-method statistical comparison (MICA, ModelAngelo, CryoAtom, EModelX,
CryoZeta) restricted to the 10 entries where all 5 have data (67233/
73799 excluded -- CryoZeta partial, not comparable). Only the 3
metrics usable for CryoZeta (TM_score_ref, Aligned_length, Seq_ID --
all from US-align; chain_comparison-based metrics are not usable for
CryoZeta, see CRYOZETA_STATUS.md finding #9). Separate from the
existing 4-method/12-entry analysis in statistical_analysis.ipynb --
different N, different metric set, kept explicitly distinct rather
than mixed into the same table.
"""
import csv
import numpy as np
from pathlib import Path
from scipy.stats import friedmanchisquare, wilcoxon
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[2]
MERGED = ROOT / "data/evaluation/evaluation_merged.csv"
CRYOZETA = ROOT / "data/evaluation/evaluation_usalign_cryozeta.csv"
OUT_DIR = ROOT / "data/stats"

CRYOZETA_ENTRIES = {"62164", "64568", "75023", "65506", "76934",
                    "71787", "71973", "70609", "64362", "79027"}
METHODS = ["MICA", "ModelAngelo", "CryoAtom", "EModelX", "CryoZeta"]
METRICS = ["TM_score_ref", "Aligned_length", "Seq_ID"]
N_BOOT = 10000
rng = np.random.default_rng(42)


def load_data():
    data = {m: {} for m in METHODS}
    with open(MERGED) as f:
        for row in csv.DictReader(f):
            if row["emdb_num"] not in CRYOZETA_ENTRIES:
                continue
            if row["method"] not in METHODS:
                continue
            data[row["method"]][row["emdb_num"]] = row
    with open(CRYOZETA) as f:
        for row in csv.DictReader(f):
            data["CryoZeta"][row["emdb_num"]] = row
    return data


def bootstrap_median_ci(values, n_boot=N_BOOT):
    values = np.array(values, dtype=float)
    boots = rng.choice(values, size=(n_boot, len(values)), replace=True)
    medians = np.median(boots, axis=1)
    lo, hi = np.percentile(medians, [2.5, 97.5])
    return np.median(values), lo, hi


def rank_biserial(diffs):
    diffs = np.array(diffs)
    nz = diffs[diffs != 0]
    if len(nz) == 0:
        return 0.0
    pos = np.sum(nz > 0)
    neg = np.sum(nz < 0)
    return (pos - neg) / len(nz)


def main():
    data = load_data()
    entries = sorted(CRYOZETA_ENTRIES)
    print(f"N = {len(entries)} entries, {len(METHODS)} methods, metrics: {METRICS}\n")

    desc_rows = []
    friedman_rows = []
    posthoc_rows = []

    for metric in METRICS:
        print(f"=== {metric} ===")
        matrix = {m: [float(data[m][e][metric]) for e in entries] for m in METHODS}

        for m in METHODS:
            med, lo, hi = bootstrap_median_ci(matrix[m])
            desc_rows.append({"metric": metric, "method": m, "median": med,
                               "ci_lo": lo, "ci_hi": hi, "n": len(entries)})
            print(f"  {m}: median={med:.4f} [{lo:.4f}, {hi:.4f}]")

        stat, p = friedmanchisquare(*[matrix[m] for m in METHODS])
        k = len(METHODS)
        n = len(entries)
        kendalls_w = stat / (n * (k - 1))
        friedman_rows.append({"metric": metric, "chi2": stat, "p": p,
                               "kendalls_w": kendalls_w, "n": n, "k": k})
        print(f"  Friedman: chi2={stat:.3f} p={p:.4f} Kendall's W={kendalls_w:.3f}")

        pvals = []
        pair_results = []
        for baseline in ["MICA", "ModelAngelo", "CryoAtom", "EModelX"]:
            cz = np.array(matrix["CryoZeta"])
            bl = np.array(matrix[baseline])
            diffs = cz - bl
            if np.all(diffs == 0):
                w_stat, p_raw = np.nan, 1.0
            else:
                w_stat, p_raw = wilcoxon(cz, bl)
            r = rank_biserial(diffs)
            pvals.append(p_raw)
            pair_results.append({"metric": metric, "comparison": f"CryoZeta_vs_{baseline}",
                                  "w_stat": w_stat, "p_raw": p_raw, "rank_biserial_r": r})

        reject, p_holm, _, _ = multipletests(pvals, method="holm")
        for i, pr in enumerate(pair_results):
            pr["p_holm"] = p_holm[i]
            pr["significant"] = bool(reject[i])
            posthoc_rows.append(pr)
            print(f"  CryoZeta vs {pr['comparison'].split('_vs_')[1]}: "
                  f"p_raw={pr['p_raw']:.4f} p_holm={pr['p_holm']:.4f} r={pr['rank_biserial_r']:.3f}"
                  f"{' *' if pr['significant'] else ''}")
        print()

    with open(OUT_DIR / "descriptive_stats_5method_n10.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "method", "median", "ci_lo", "ci_hi", "n"])
        w.writeheader()
        w.writerows(desc_rows)

    with open(OUT_DIR / "friedman_5method_n10.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "chi2", "p", "kendalls_w", "n", "k"])
        w.writeheader()
        w.writerows(friedman_rows)

    with open(OUT_DIR / "posthoc_wilcoxon_5method_n10.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "comparison", "w_stat", "p_raw",
                                           "rank_biserial_r", "p_holm", "significant"])
        w.writeheader()
        w.writerows(posthoc_rows)

    print(f"Saved to {OUT_DIR}/{{descriptive_stats,friedman,posthoc_wilcoxon}}_5method_n10.csv")


if __name__ == "__main__":
    main()
