# MICA Benchmark — Independent Evaluation on 2026 Cryo-EM Structures

Independent benchmark of **MICA** (Gyawali, Dhakal & Cheng, *Communications
Chemistry* 2025) against four baseline methods — **ModelAngelo**,
**EModelX(+AF)**, **CryoAtom**, and **CryoZeta** — on a newly constructed,
leakage-screened set of 12 cryo-EM structures released in 2026. All 12
structures postdate every test set used in MICA's own publication, including
its newest (`test_2025`, structures released after January 1, 2025).
CryoZeta was added after the main 4-method comparison was complete and is
reported as a separate, clearly-scoped extension — see
[Headline results](#headline-results) and
[step 10](#10-cryozeta-5th-method-extended-comparison) below.

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
   (including the search-failure vs. infrastructure-failure distinction
   behind the 14.3% figure) in `data/docking/FAILED_CASES.md`.
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

**CryoZeta (5th method, added separately)**: of its 12 entries, 10
produced complete structures and 2 (`EMD-67233`, `EMD-73799`) are
disclosed partial results (3/4 and 9/12 chains — a registration-algorithm
failure in CryoZeta's own released pipeline, no resume capability),
excluded from the comparison below as not comparable to a complete
prediction. Only 3 of the paper's 5 reproduced metrics (TM-score, aligned
Cα length, sequence identity — all US-align-derived) are usable for
CryoZeta: its written coordinates carry a residual rotation/translation
offset from the true map frame (confirmed by direct inspection — see
`data/cryozeta/CRYOZETA_FINDINGS.md` for full per-entry provenance and every
bug found in CryoZeta's released code) that `chain_comparison`'s
un-superposed scoring can't handle, though US-align is unaffected. On
those 3 metrics, at n=10: **CryoZeta loses significantly to no baseline**,
and wins significantly against MICA and EModelX(+AF) on TM-score, and
against MICA, ModelAngelo, and EModelX(+AF) on aligned Cα length (all
Holm-corrected p<0.05).

## Repository structure

```
.
├── README.md
├── patches/                  # required fixes to upstream MICA before running anything (see patches/README.md)
│   ├── dock_in_map.py, predict.py
│   └── README.md
├── scripts/
│   ├── dataset/              # candidate pool construction -> benchmark selection -> input acquisition
│   │   ├── rcsb_2026_cryoem_query.py, filter_pure_protein.py, filter_emdb_release_date.py
│   │   ├── build_shortlist.py, candidate_dataset_eda.ipynb, fetch_inputs.py
│   │   └── utils/fasta_to_AF3_json.py
│   └── evaluation/           # evaluate_usalign.py, evaluate_chain_comparison.py, recompute_cc.py
│       # + evaluate_cryozeta_usalign.py, evaluate_cryozeta_chain_comparison.py,
│       #   select_cryozeta_top_pick.py, analyze_cryozeta_5method.py
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
│   │                            #   + evaluation_*_cryozeta.csv, evaluation_cryozeta_5method_merged.csv
│   ├── stats/                  # Friedman/Wilcoxon/descriptive/stratified results (+ *_5method_n10.csv for CryoZeta)
│   └── cryozeta/                # CRYOZETA_FINDINGS.md (per-entry provenance, bugs), CRYOZETA_EXPLAINED.md (methodology)
├── figures/                  # dataset_distribution.png, all_metrics_boxplots.png, tm_score_by_coverage.png,
│                                #   cryozeta_5method_boxplots.png
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

### 0. Environment

```bash
git clone https://github.com/jianlin-cheng/MICA.git
cp patches/dock_in_map.py MICA/utils/dock_in_map.py
cp patches/predict.py MICA/utils/predict.py
conda env create -f MICA/environment.yml   # or install modern-version equivalents; see patches/README.md
pip install superpose3d==1.1.1             # exact pin required, not the current PyPI default
```

Apply the patches **before** running anything in `runpod_scripts/` —
without them, docking OOM-kills itself and MICA inference crashes
partway through Cα-sequence alignment. Rationale for each patch is in
`patches/README.md`.

Also required, not bundled here (all have their own licenses/install
steps):
- **Phenix** (academic license, phenix-online.org) — needed for
  `phenix.dock_in_map`, `phenix.real_space_refine`,
  `phenix.chain_comparison`.
- **MMseqs2** (`brew install mmseqs2` or equivalent) — only needed to
  re-run the leakage screen in step 2, not for steps 3 onward.
- **ModelAngelo**, **CryoAtom**, **EModelX(+AF)** — each baseline's own
  repo/weights (see `runpod_scripts/{modelangelo,cryoatom,emodelx}_batch.py`
  for the exact setup each one needs; `runpod_scripts/COMMANDS.md` has
  the full walkthrough including conda-env gotchas hit during this run).

### 1. Rebuild the candidate pool and benchmark selection (optional)

Already-final output is `data/benchmark/shortlist_12_v3_stratified_random.csv`
— only needed to verify the selection/screening itself (e.g. with a
different seed or a later RCSB/EMDB snapshot), not for reproducing
the benchmark results.

```bash
python3 scripts/dataset/rcsb_2026_cryoem_query.py
python3 scripts/dataset/filter_pure_protein.py
python3 scripts/dataset/filter_emdb_release_date.py
python3 scripts/dataset/build_shortlist.py
```

### 2. Fetch inputs for the 12 benchmark entries

```bash
python3 scripts/dataset/fetch_inputs.py
```

Pulls, per entry: FASTA (RCSB), density map (EMDB), ground-truth
structure (`https://files.rcsb.org/download/<PDB_ID>.cif`).

### 3. Generate and submit AF3 jobs

```bash
python3 scripts/dataset/utils/fasta_to_AF3_json.py -f input/<emdb_num>/<pdb_id>.fasta -n <emdb_num>
```

Submission to the AlphaFold Server is manual (no public submission
API) — batch-upload the combined per-entry JSON, run each job, place
`*_model_0.cif` results into `input/<emdb_num>/AF3_results/<chain>/`.

### 4. Domain segmentation

Run upstream MICA's own `utils/process_AF3_results.py` per entry
(`-d cpu`, no GPU needed) — splits chains into Merizo-detected domains.

### 5. Domain docking (CPU pod)

```bash
python3 runpod_scripts/dock_batch.py
```

Worker pool across all entries' domains, CPU/RAM-bound only. Expect a
non-trivial failure/timeout rate on large maps — this run's was
21/147 (14.3%) genuine CC≥0.2 successes; see
`data/docking/FAILED_CASES.md` for the full per-domain breakdown and
why (infrastructure constraints — memory ceiling + enforced 45-min
timeout — not Phenix or MICA search failures; that distinction is the
key thing to check before concluding anything about MICA itself from
this number).

### 6. MICA inference (GPU pod)

```bash
python3 runpod_scripts/combine_docked.py   # builds each entry's combined docked-domain file
python3 runpod_scripts/mica_batch.py       # MICA's own released code, default params
```

Falls back to map-only prediction automatically for entries with zero
docked domains (3/12 in this run).

### 7. Baseline inference (same GPU pod, same 12 inputs)

```bash
python3 runpod_scripts/modelangelo_batch.py
python3 runpod_scripts/cryoatom_batch.py
python3 runpod_scripts/emodelx_batch.py
```

Pretrained weights, no retraining, identical map+sequence inputs to
MICA's run.

### 8. Evaluation

```bash
python3 scripts/evaluation/evaluate_usalign.py
python3 scripts/evaluation/evaluate_chain_comparison.py
python3 scripts/evaluation/recompute_cc.py   # independent CC cross-check for low-confidence docks
```

Writes `data/evaluation/evaluation_usalign.csv`,
`evaluation_chain_comparison.csv`, `evaluation_merged.csv`.

### 9. Statistics

```bash
jupyter nbconvert --to notebook --execute --inplace analysis/statistical_analysis.ipynb
```

Regenerates every results CSV in `data/stats/` and every figure in
`figures/` from the `data/evaluation/` CSVs — Friedman omnibus +
Holm-corrected Wilcoxon post-hoc (MICA vs. each baseline) + bootstrap
confidence intervals, stratified by docking-coverage mode.

### 10. CryoZeta (5th method, extended comparison)

CryoZeta's raw per-entry output isn't included in this repository
(`baseline_output/` is git-excluded, same as the other 4 methods — see
[Data not included](#data-not-included-in-this-repository)). Given that raw
output, reproduce the comparison with:

```bash
python3 scripts/evaluation/select_cryozeta_top_pick.py      # picks each entry's true top-ranked structure
python3 scripts/evaluation/evaluate_cryozeta_usalign.py
python3 scripts/evaluation/evaluate_cryozeta_chain_comparison.py
python3 scripts/evaluation/analyze_cryozeta_5method.py       # Friedman + Wilcoxon, n=10, standalone script
jupyter nbconvert --to notebook --execute --inplace analysis/statistical_analysis.ipynb  # also regenerates the CryoZeta section + figure
```

`select_cryozeta_top_pick.py`'s docstring explains why this isn't a trivial
"take `sample_0`" operation — which file is actually the top-ranked
structure depends on whether CryoZeta's own `combine.py` ran successfully
for that entry (see `data/cryozeta/CRYOZETA_FINDINGS.md` for the full
per-entry breakdown, every bug found in CryoZeta's released code, and the
root-caused explanation for why 2 entries are partial and 7 of 10 score
zero on `chain_comparison`'s metrics specifically).

### Variance across reruns

**Docking yield (step 5)** is the most infrastructure-sensitive number
in the pipeline — it depends on worker-pool size, per-job timeout, and
available RAM, none of which are part of MICA's own method. A
different yield on different hardware reflects that, not a
correctness issue.

**Steps 6–9** should be exactly reproducible given the same
docked-domain inputs — every intermediate and final CSV from this run
is in `data/` to diff against.

Pod-based stages (5–7) require the compute environments described in
each `runpod_scripts/*_batch.py` script's own configuration; none of
them are GPU-architecture-specific beyond what each tool itself
requires.
