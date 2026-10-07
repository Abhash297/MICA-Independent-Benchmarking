# CryoZeta (5th method) — results and findings

Technical summary for the benchmark report and repository. Same
purpose as `data/docking/FAILED_CASES.md` served for the docking
stage: back up cited numbers with the actual evidence. This file is
a cleaned-up technical summary; it omits session/infrastructure
narrative (pod IPs, hour-by-hour timing, budget tracking) that isn't
relevant to reproducing or verifying the results.

## Summary

**10 full passes, 2 disclosed partials, 0 complete failures**, out of
12 entries attempted.

| Entry | Result | Notes |
|---|---|---|
| `62164`, `65506`, `71787`, `75023`, `64568`, `71973`, `70609`, `76934`, `64362`, `79027` | PASS | Complete structures, all usable for the main comparison |
| `67233` | PARTIAL — 3 of 4 chains | Stage 3's registration step failed (see Finding 4 below); stage 4 never ran. Excluded from the main quantitative comparison. |
| `73799` | PARTIAL — 9 of 12 chains | Stage 10's registration step failed, same root cause as `67233`. Excluded from the main quantitative comparison. |

All 10 complete entries were scored with US-align (TM-score, aligned
Cα length, sequence identity) and Phenix `chain_comparison` (Cα
match, sequence match, `CA_score`). Only the US-align metrics are
usable for CryoZeta — see Finding 9.

## Bugs and limitations found in CryoZeta's released code

1. **`combine.py`'s entry-selection logic silently fails for
   purely-numeric entry names.** `scores.csv`'s `pdb_id` column is
   pandas-inferred as `int64` whenever every entry name in a run is
   all-digits (true for all 12 entries in this benchmark — standard
   EMDB-style numeric naming). The code compares this against a
   Python `str`, which is always `False` with no error raised —
   `combine.py` silently produces zero output. Fix: cast both sides
   to `str` before comparing.
2. **`combine.py` crashes instead of degrading gracefully on a
   missing file.** If a top-scored candidate's registration output
   was never written despite being scored, the original code crashes
   with `FileNotFoundError` rather than falling through to the
   next-best candidate.
3. **The confidence-head step (a non-essential, metadata-only
   network that annotates per-atom confidence) has no isolation from
   the rest of the pipeline.** Its failure (observed: a CUDA OOM)
   kills the entire run, discarding the ability to write any output
   file even though the actual structure prediction and scoring had
   already succeeded and been saved to disk moments earlier.
4. **TEASER++ registration can fail silently and degrade to
   degenerate output** instead of reporting "no fit found" cleanly.
   Observed on `67233` (stage 3) and `73799` (stage 10): TEASER++
   produced no output file, and the fallback exhaustive search
   returned `NaN` scores for every candidate. SVD and VESPER
   registration still produced valid output for the identical input,
   confirming this is specific to TEASER++'s own failure mode.
5. **Large-complex mode (multi-chain entries split into sequential
   stages) has no resume capability.** The checkpoint a later stage
   needs is only written after the *previous* stage's registration
   succeeds — so a failure on stage N (as in Finding 4) leaves no way
   to resume from stage N+1; a full restart from stage 1 is the only
   option, with a real risk of reproducing the identical
   seed-deterministic failure.
6. **`large_inference_demo.sh` defaults to GPU index 1**, which fails
   immediately on any single-GPU host — should default to 0.
7. **The entry-selector flag misparses purely-numeric entry names as
   array indices** instead of matching by name, raising an
   `IndexError` — same numeric-name blind spot as Finding 1, in a
   different part of the codebase.
8. **(Blackwell GPUs only)** A naming mismatch between Triton's
   expected binary name and the environment variable CryoZeta's own
   scripts export (the required hyphen can't even be expressed as a
   shell variable name), plus a separate Triton codegen gap with no
   available workaround beyond disabling the accelerated-attention
   code path entirely.
9. **Written `.cif` coordinates can carry a residual global
   rotation/translation offset from the true map frame, not
   corrected by the internal registration step.** All 10 complete
   entries score well on US-align (TM-score 0.97–0.999, always
   superposes before scoring), but 7 of 10 score exactly zero on
   Phenix `chain_comparison` (which assumes a shared frame and does
   not superpose). Confirmed by direct coordinate inspection
   (`65506`): the predicted structure's X/Y axes are effectively
   swapped relative to ground truth — a genuine ~90° rotational
   offset. CryoZeta's TEASER++/SVD registration transform is computed
   and used internally to *rank* candidates, but is not applied to
   the coordinates actually written to disk. **Consequence**:
   US-align metrics (TM-score, aligned Cα length, sequence identity)
   are valid and usable for CryoZeta; `chain_comparison`-based
   metrics (Cα match, sequence match, `CA_score`) are not, for this
   benchmark as currently run.
10. **Output `.cif` files omit the `_atom_site.occupancy` and
    `_atom_site.B_iso_or_equiv` columns** whenever run with
    `need_atom_confidence=False` (CryoZeta's own hardcoded default —
    no CLI flag exposes an override). Both Phenix and Biopython's
    mmCIF parsers hard-require these columns and crash without them.
    A constant dummy column was patched in before scoring could
    proceed with Phenix tooling. Unrelated to Finding 9, but another
    real interoperability gap with standard structural-biology
    tooling.

## Recovery methodology

Several entries hit a crash or timeout *after* the actual prediction
and scoring had already completed and been saved to disk (Findings 2,
3, 5). In those cases, the raw predicted coordinates
(`pred_all_coordinate`, saved to `output_dict_<id>.pt` as a normal
part of the pipeline, independent of whether later steps succeed)
were re-featurized on CPU and written directly to `.cif` via
CryoZeta's own `save_structure_cif` function — bypassing the failed
step entirely. Verified safe: for entries where both a native and a
recovered file existed, the coordinates were confirmed identical.

## Selecting each entry's top-ranked structure

CryoZeta produces 5 candidate structures per entry, scored by 3
registration methods each (15 scored candidates total). The true
top-ranked candidate (by `recall_ccmask_ca` in `scores.csv`) is not
always the file literally named `sample_0` — see
`scripts/evaluation/select_cryozeta_top_pick.py` for the exact
selection logic and why it depends on whether `combine.py` (Finding 1)
ran successfully for that entry.

## Hardware

Three GPU tiers were used across this work, driven by one recurring
constraint: CryoZeta's detection-stage post-processing is CPU/RAM-bound
(not GPU-bound), and a 92GB-RAM host proved insufficient regardless of
GPU tier.

| Tier | VRAM | RAM | Entries covered |
|---|---|---|---|
| RTX PRO 4500 Blackwell | 32GB | 62GB | `62164`, `65506`, `71787`, `75023` |
| A100 PCIe | 80GB | 92GB | `64568`, `70609`, `71973`, `76934`, `79027` |
| H100 PCIe | 80GB | 251GB | `64362` (resolved), `67233`/`73799` (partial results) |

The RAM ceiling, not VRAM, was the actual constraint that forced the
move to larger-RAM hosts — confirmed by checking the container's
cgroup memory limit directly against the OOM failures observed on the
92GB tier.
