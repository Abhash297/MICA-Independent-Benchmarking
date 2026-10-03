# MICA Benchmark — Independent Evaluation on 2026 Cryo-EM Structures

Independent benchmark of **MICA** (Gyawali, Dhakal & Cheng, *Communications
Chemistry* 2025) against three baseline methods — **ModelAngelo**,
**EModelX(+AF)**, and **CryoAtom** — on a newly constructed, leakage-screened
set of 12 cryo-EM structures released in 2026. All 12 structures postdate
every test set used in MICA's own publication, including its newest
(`test_2025`, structures released after January 1, 2025).

## Pipeline overview

1. **Candidate pool construction** — three sequential filters, each
   dropping entries for a specific, documented reason:
   1. `rcsb_2026_cryoem_query.py` — queries RCSB for entries with
      `exptl.method = ELECTRON MICROSCOPY` and
      `rcsb_accession_info.initial_release_date` in
      `[2026-01-01, 2026-09-26]`, pulling resolution and linked EMDB IDs
      for each hit. **5,163 raw candidates.**
   2. `filter_pure_protein.py` — two sub-filters, both on structured
      RCSB fields (not title keywords, which miss protein+NA complexes
      like spliceosomes or CRISPR-Cas effectors that don't say
      "ribosome" anywhere in the name):
      - `rcsb_entry_info.polymer_composition`: keep pure protein
        (heteromeric + homomeric) and protein+glycan entries (glycans
        are sugar decorations, not a competing macromolecule); drop
        anything containing nucleic acid. **4,070 remain.**
      - `em_experiment.reconstruction_method`: keep `SINGLE PARTICLE`
        only; drop `HELICAL` and `SUBTOMOGRAM AVERAGING` (different box
        geometry/resolution regime, none of the 4 benchmarked methods
        were built or evaluated for these). **3,752 remain.**
   3. `filter_emdb_release_date.py` — a structure's own listed release
      date does **not** guarantee its linked density map is actually
      new (re-refinements and stale EMDB cross-references can leave a
      2026-dated structure pointing at a years-old map). Each linked
      map's own `map_release` date is independently verified via the
      EMDB API; any entry whose map isn't also genuinely in
      `[2026-01-01, 2026-09-26]` is dropped regardless of the
      structure's own date. **7 false positives caught and dropped.**

   Output: `data/pool/rcsb_2026_final_candidates.csv` — **3,745
   candidates**, each confirmed pure-protein, single-particle cryo-EM,
   with both the structure and its density map genuinely released in
   2026.
2. **Benchmark selection** (`scripts/dataset/build_shortlist.py`,
   `candidate_dataset_eda.ipynb`) — stratified random sampling over a 3×4
   grid (protein size × map resolution), seed 42, one entry per cell.
   Every candidate additionally screened via MMSeqs2 at 25% sequence
   identity against MICA's disclosed 550-structure training set to
   exclude any overlap. Output:
   `data/benchmark/shortlist_12_v3_stratified_random.csv` (the final
   12-entry benchmark).
3. **Input acquisition** (`scripts/dataset/fetch_inputs.py`) — pulls each
   entry's FASTA sequence, density map, and ground-truth structure.
4. **AF3 structure generation** (`scripts/dataset/utils/fasta_to_AF3_json.py`)
   — generates AlphaFold3 Server job requests per chain.
5. **Domain segmentation + docking** (`runpod_scripts/dock_batch.py`,
   `runpod_scripts/combine_docked.py`) — Merizo domain segmentation,
   `phenix.dock_in_map` rigid-body docking of each domain into its own
   density map (`min_cc=0.2`, MICA's own default), combined per-chain into
   MICA's required single-file input format. Run on a dedicated CPU pod.
   Results: `data/docking/docking_results.csv`; full per-domain accounting
   in the (locally kept, not in this repo) `FAILED_CASES.md`.
6. **MICA inference** (`runpod_scripts/mica_batch.py`) — MICA's own
   released code, default parameters, run on a dedicated GPU pod. Falls
   back to map-only prediction for entries with zero docked domains.
7. **Baseline inference** (`runpod_scripts/modelangelo_batch.py`,
   `cryoatom_batch.py`, `emodelx_batch.py`) — ModelAngelo, CryoAtom, and
   EModelX(+AF) run on identical map+sequence inputs, pretrained weights,
   no retraining.
8. **Evaluation** (`scripts/evaluation/evaluate_usalign.py`,
   `evaluate_chain_comparison.py`, `recompute_cc.py`) — reproduces 5 of
   MICA's own 6 published metrics (TM-score, aligned Cα length, sequence
   identity via US-align; Cα match, sequence match via Phenix
   `chain_comparison`) using the exact tools the source paper names. One
   supplementary metric (`CA_score`, Phenix `chain_comparison`'s internal
   fraction-matched/RMSD field) is added beyond the paper's protocol to
   probe atomic placement precision, a dimension the original six metrics
   don't measure. Results: `data/evaluation/evaluation_usalign.csv`,
   `evaluation_chain_comparison.csv`, `evaluation_merged.csv`.
9. **Statistical analysis** (`analysis/statistical_analysis.ipynb`) —
   paired non-parametric tests (Friedman omnibus + Holm-corrected Wilcoxon
   post-hoc, MICA vs. each baseline), bootstrap confidence intervals,
   stratified by docking-coverage mode. Results in `data/stats/`
   (`friedman_omnibus_results.csv`, `posthoc_wilcoxon_*.csv`,
   `descriptive_stats_bootstrap_ci.csv`, `stratified_coverage_comparison.csv`,
   `summary_per_protein_tmscore.csv`, `headline_comparison_paper_vs_added.csv`)
   and figures in `figures/` (`dataset_distribution.png`,
   `all_metrics_boxplots.png`, `tm_score_by_coverage.png`).

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
├── README.md
├── scripts/
│   ├── dataset/              # candidate pool construction -> benchmark selection -> input acquisition
│   │   ├── rcsb_2026_cryoem_query.py, filter_pure_protein.py, filter_emdb_release_date.py
│   │   ├── build_shortlist.py, candidate_dataset_eda.ipynb, fetch_inputs.py
│   │   └── utils/fasta_to_AF3_json.py
│   └── evaluation/           # evaluate_usalign.py, evaluate_chain_comparison.py, recompute_cc.py
├── runpod_scripts/           # pod batch runners
│   ├── dock_batch.py, combine_docked.py          #   docking
│   ├── mica_batch.py                             #   MICA inference
│   ├── modelangelo_batch.py, cryoatom_batch.py,  #   baselines
│   │   emodelx_batch.py
│   └── COMMANDS.md                               #   pod ops reference
├── tools/USalign/             # US-align, compiled from source
├── analysis/statistical_analysis.ipynb   # stats + figures (executable, regenerates everything below)
├── data/
│   ├── pool/                 # candidate-pool CSVs (3,745 candidates + lookup caches)
│   ├── benchmark/             # the final 12-entry shortlist, training sequences, contour levels
│   ├── docking/                # docking_results.csv, cc_recomputation_unknown_domains.csv
│   ├── evaluation/             # evaluation_usalign.csv, evaluation_chain_comparison.csv, evaluation_merged.csv
│   └── stats/                  # Friedman/Wilcoxon/descriptive/stratified results
├── figures/                  # dataset_distribution.png, all_metrics_boxplots.png, tm_score_by_coverage.png
├── reference/
│   ├── MICA_cryo-EM 6.pdf, supplementary/        # the MICA paper + its SI
│   └── sanity_check/                             # pipeline sanity-test notebook
└── archive/                   # superseded selection iterations, kept for provenance
```

## Data not included in this repository

Raw density maps, AF3 structure predictions, domain-docking outputs, and
all 4 methods' final predicted structures (`input/`, `baseline_output/`,
`mica_output/`, `AF3_out/` — roughly 3.2GB combined) are kept locally but
excluded from version control due to size. Available on request.

## Reproducing the analysis

Each stage's script can be re-run independently given its documented
inputs; scripts under `scripts/` use paths relative to their own
location, so run them from wherever they live (e.g.
`python3 scripts/dataset/fetch_inputs.py`). The statistics notebook
(`analysis/statistical_analysis.ipynb`) can be re-executed in place with
`jupyter nbconvert --to notebook --execute --inplace
analysis/statistical_analysis.ipynb` any time the underlying `data/`
CSVs change — it regenerates every figure and results CSV from scratch.
Pod-based stages (docking, MICA/baseline inference) require the compute
environments described in each `runpod_scripts/*_batch.py` script's own
configuration.
