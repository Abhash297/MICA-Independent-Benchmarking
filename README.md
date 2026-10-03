# MICA Benchmark — Independent Evaluation on 2026 Cryo-EM Structures

Independent benchmark of **MICA** (Gyawali, Dhakal & Cheng, *Communications
Chemistry* 2025) against three baseline methods — **ModelAngelo**,
**EModelX(+AF)**, and **CryoAtom** — on a newly constructed, leakage-screened
set of 12 cryo-EM structures released in 2026. All 12 structures postdate
every test set used in MICA's own publication, including its newest
(`test_2025`, structures released after January 1, 2025).

## Pipeline overview

1. **Candidate pool construction** (`rcsb_2026_cryoem_query.py`,
   `filter_pure_protein.py`, `filter_emdb_release_date.py`) — query RCSB/EMDB
   for 2026 single-particle cryo-EM depositions, filter to pure-protein
   entries, verify the density map itself (not just the structure) was
   released in 2026. Output: `rcsb_2026_final_candidates.csv` (3,745
   candidates).
2. **Benchmark selection** (`build_shortlist.py`, `candidate_dataset_eda.ipynb`)
   — stratified random sampling over a 3×4 grid (protein size ×
   map resolution), seed 42, one entry per cell. Every candidate
   additionally screened via MMSeqs2 at 25% sequence identity against
   MICA's disclosed 550-structure training set to exclude any overlap.
   Output: `shortlist_12_v3_stratified_random.csv` (the final 12-entry
   benchmark).
3. **Input acquisition** (`fetch_inputs.py`) — pulls each entry's FASTA
   sequence, density map, and ground-truth structure.
4. **AF3 structure generation** (`utils/fasta_to_AF3_json.py`) — generates
   AlphaFold3 Server job requests per chain.
5. **Domain segmentation + docking** (`runpod_scripts/dock_batch.py`,
   `runpod_scripts/combine_docked.py`) — Merizo domain segmentation,
   `phenix.dock_in_map` rigid-body docking of each domain into its own
   density map (`min_cc=0.2`, MICA's own default), combined per-chain into
   MICA's required single-file input format. Run on a dedicated CPU pod.
   Results: `docking_results.csv`; full per-domain accounting in the
   (locally kept, not in this repo) `FAILED_CASES.md`.
6. **MICA inference** (`runpod_scripts/mica_batch.py`) — MICA's own
   released code, default parameters, run on a dedicated GPU pod. Falls
   back to map-only prediction for entries with zero docked domains.
7. **Baseline inference** (`runpod_scripts/modelangelo_batch.py`,
   `cryoatom_batch.py`, `emodelx_batch.py`) — ModelAngelo, CryoAtom, and
   EModelX(+AF) run on identical map+sequence inputs, pretrained weights,
   no retraining.
8. **Evaluation** (`evaluate_usalign.py`, `evaluate_chain_comparison.py`,
   `recompute_cc.py`) — reproduces 5 of MICA's own 6 published metrics
   (TM-score, aligned Cα length, sequence identity via US-align; Cα match,
   sequence match via Phenix `chain_comparison`) using the exact tools the
   source paper names. One supplementary metric (`CA_score`, Phenix
   `chain_comparison`'s internal fraction-matched/RMSD field) is added
   beyond the paper's protocol to probe atomic placement precision, a
   dimension the original six metrics don't measure. Results:
   `evaluation_usalign.csv`, `evaluation_chain_comparison.csv`,
   `evaluation_merged.csv`.
9. **Statistical analysis** (`statistical_analysis.ipynb`) — paired
   non-parametric tests (Friedman omnibus + Holm-corrected Wilcoxon
   post-hoc, MICA vs. each baseline), bootstrap confidence intervals,
   stratified by docking-coverage mode. Results: `friedman_omnibus_results.csv`,
   `posthoc_wilcoxon_*.csv`, `descriptive_stats_bootstrap_ci.csv`,
   `stratified_coverage_comparison.csv`, `summary_per_protein_tmscore.csv`,
   `headline_comparison_paper_vs_added.csv`, and the figures
   `dataset_distribution.png` / `all_metrics_boxplots.png` /
   `tm_score_by_coverage.png`.

## Headline results

- On 4 of the 5 exactly-reproduced paper metrics, MICA shows no
  statistically significant difference from ModelAngelo or EModelX(+AF).
- A modest, significant Cα-match deficit exists specifically against
  CryoAtom — a method published after MICA, so this is a new comparison,
  not a reproduction discrepancy.
- The supplementary `CA_score` metric reveals a large, consistent gap
  against ModelAngelo and CryoAtom, traced to a verified cause: MICA's
  density-refinement step (`phenix.real_space_refine`) is gated behind an
  off-by-default flag in its own released code, and this reproduction ran
  MICA's default configuration.
- Domain-docking yield (21/147 = 14.3% genuine CC≥0.2 successes) was well
  below the 93.75% rate disclosed in MICA's paper — plausibly reflecting
  this benchmark's deliberate novelty (harder for AF3's templates) and
  documented compute-budget constraints not present in the original study.

## Repository structure

```
.
├── rcsb_2026_cryoem_query.py, filter_pure_protein.py,      # candidate pool
│   filter_emdb_release_date.py                             # construction
├── build_shortlist.py, candidate_dataset_eda.ipynb         # benchmark selection
├── fetch_inputs.py                                         # input acquisition
├── utils/fasta_to_AF3_json.py                              # AF3 job generation
├── runpod_scripts/                                         # pod batch runners
│   ├── dock_batch.py, combine_docked.py                    #   docking
│   ├── mica_batch.py                                       #   MICA inference
│   ├── modelangelo_batch.py, cryoatom_batch.py,             #   baselines
│   │   emodelx_batch.py
│   └── COMMANDS.md                                         #   pod ops reference
├── evaluate_usalign.py, evaluate_chain_comparison.py,      # evaluation
│   recompute_cc.py
├── tools/USalign/                                          # US-align, compiled from source
├── statistical_analysis.ipynb                              # stats + figures
├── *.csv                                                   # intermediate + final results data
├── *.png                                                   # figures
├── MICA_cryo-EM 6.pdf, supplementary/                      # the MICA paper + its SI
├── sanity_check/                                           # pipeline sanity-test notebook
└── archive/                                                # superseded selection
                                                              # iterations, kept for provenance
```

## Data not included in this repository

Raw density maps, AF3 structure predictions, domain-docking outputs, and
all 4 methods' final predicted structures (`input/`, `baseline_output/`,
`mica_output/`, `AF3_out/` — roughly 3.2GB combined) are kept locally but
excluded from version control due to size. Available on request.

## Reproducing the analysis

Each stage's script can be re-run independently given its documented
inputs. The statistics notebook is generated programmatically and can be
rebuilt from the evaluation CSVs with standard `jupyter nbconvert
--execute`. Pod-based stages (docking, MICA/baseline inference) require
the compute environments described in each `runpod_scripts/*_batch.py`
script's own configuration.
