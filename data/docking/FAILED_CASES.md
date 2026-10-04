# Docking failures — tracking file

Separate from `CLAUDE.md` (narrative project log) — this file tracks
individual domain-level docking failures for the report, kept
up to date as the batch runs. See `CLAUDE.md` Stage 13c/13d for the
full root-cause analysis (code bug vs. Phenix tool design vs. resource
constraint) and the reasoning behind not chasing 100% success.

## Total batch runtime (for the report's Methods/compute-budget section)

- **Batch start**: Tue Sep 29 16:49:25 2026 UTC (`dock_batch.py`
  orchestrator PID 21022 launch, confirmed via `ps -o lstart` —
  process has run continuously and unbroken since, no restarts).
- **Batch end**: Wed Sep 30 12:17:26 2026 UTC (last log write,
  `73799/fold_9z49_3_model_0_chain_D_domain_01.log` — orchestrator
  process confirmed exited by the next check at 13:27 UTC, no
  `dock_in_map` processes running, cgroup memory dropped to idle).
  **Batch is complete — all 147 domains attempted.**
- **Total wall-clock time**: 19h 28m 1s (19.47 hours).
- **Worker-hours**: 19.47h × `MAX_WORKERS=4` = **77.87 worker-hours** —
  the honest compute-cost figure, since real work happened in parallel
  across 4 concurrent CPU workers the whole time.
- Note: this is Run 2 only (post-OOM-crisis, `MAX_WORKERS=4`) — doesn't
  include the earlier Run 1 (7-worker, pre-crisis) time, which should
  be accounted separately if the report wants total RunPod spend
  rather than just this run's duration.

## Entry-level completion (the metric that actually matters)

Raw domain-count completion undersells progress — MICA's map-only
fallback means an entry doesn't need 100% of its domains docked to
produce a usable downstream result. Tracked via
`runpod_scripts/entry_completion.py` (rerun anytime against a fresh
pull of `docking_results.csv` + domain counts). Snapshot below is
**early** — most entries haven't been reached by the worker queue yet.

**Queue reordered** (see `CLAUDE.md` Stage 13e) to prioritize breadth
of entry coverage over finishing the two hardest entries — untouched
entries now queued by ascending domain count first, `67233`/`73799`
(poor ROI so far) pushed to the end.

**STALE — mid-batch snapshot from pod time 23:37, while the batch was
still running. Superseded by the "FINAL tally" section further down
this file (post-completion, log-cross-referenced against disk).** Kept
here only for the narrative progression; don't read the "so far" /
"still running" notes below as current — they're the mid-run state,
not the end state. See the FINAL tally table for authoritative numbers.

| Entry | Genuine docked (CC≥0.2) | Attempted | Total domains | % genuine |
|---|---|---|---|---|
| 79027 | 6 | 12 | 12 | 50% (fully attempted) |
| 67233 | 0 | 12 | 12 | 0% (fully attempted) |
| 73799 | 0 | 18 | 24 | 0% so far (4 running, 2 not started — last entry in queue) |
| 62164 | 1 | 2 | 2 | 50% (fully attempted; disk survives a later CSV-logged failure) |
| 64568 | 0 | 6 | 6 | 0% (fully attempted; 2 "docked" but CC<0.2) |
| 75023 | 3 | 8 | 8 | 37.5% (fully attempted) |
| 65506 | 2 | 8 | 8 | 25% (fully attempted) |
| 76934 | 0 | 10 | 10 | 0% (fully attempted — every domain timed out) |
| 71787 | 0 | 12 | 12 | 0% (fully attempted; 1 "docked" but CC=0.09<0.2) |
| 71973 | 2 | 13 | 13 | 15% (fully attempted) |
| 70609 | 6 | 18 | 18 | 33% (fully attempted, best hit rate of any entry) |
| 64362 | 0 | 18 | 22 | 0% so far (4 still running; trending toward another 0% entry) |

**Overall: 18 genuine (CC≥0.2) successes across 142 domains attempted
so far (12.7%), out of 147 total.** 10 of 12 entries now fully
attempted: 79027(6), 67233(0), 64568(0), 75023(3), 62164(1), 76934(0),
71787(0), 71973(2), 70609(6 — best hit rate, 33%). `64362` at 18/22
attempted with **0 genuine so far**, trending toward a 4th 0%-entry.
`73799` still partial (7/24). **4 of the fully/mostly-attempted entries
sit at 0% genuine success** (67233, 76934, 71787, and likely 64362) —
this is now a real pattern worth its own line in the report, not
scattered early failures: roughly a third of the 12-protein set may
end up contributing zero AF3-fusion signal and rely entirely on MICA's
map-only fallback.

## Category definitions

- **`docked`** — process exited rc=0 and wrote an output file. **Does
  NOT guarantee CC ≥ our configured `min_cc=0.2`** (see caveat below) —
  the name is about process outcome, not fit quality.

  **Important caveat found while inspecting `64568/chain_C_domain_02`'s
  log** (CC=0.08, below our 0.2 bar, yet status=`docked`): Phenix's
  `dock_in_map` runs multiple internal search stages, each reporting
  its own CC, and only filters out candidates below **half** of
  `min_cc` (i.e. 0.1, logged as `"Skipping as CC_mask is < 1/2
  min_cc"`) — not below the full `min_cc=0.2` we configured. Whatever
  survives that looser internal filter gets written to disk and
  returns rc=0, regardless of whether it clears our actual 0.2 bar.
  `dock_batch.py`'s `run_one_domain()` only checks `returncode==0 and
  out_path.exists()` for `status="docked"` — it never re-checks the
  parsed `final_cc` against `MIN_CC`. Confirmed same pattern likely
  applies to `75023/chain_B_domain_02` (CC=0.1, also below 0.2).
  **Action for the report**: don't trust `status=="docked"` alone as
  "good fit" — post-filter the final CSV by `final_cc >= 0.2` to get
  the true count of domains that actually met our quality bar.
- **`completed_no_output`** — Phenix's search finished cleanly but found
  no fit above threshold; a genuine *search failure*, not infrastructure.
  None observed yet as of this snapshot — every failure below is
  infrastructure-related, not a case where Phenix actually finished
  searching and came up empty.
- **`failed_rc-9`** — killed via `SIGKILL`. Almost always the Linux
  kernel's cgroup OOM killer intervening because total container memory
  hit the 128GB cap — an *infrastructure failure*, not a search outcome.
  We never learn whether a good fit existed.
- **`timeout`** — killed by our own enforced 45-minute cutoff
  (`dock_batch.py`), separate from Phenix's own dead timeout code.
  Usually an *infrastructure failure* — the job was still searching
  when killed. **But not always**: confirmed instance
  (`67233/fold_9xti_1_model_0_chain_A_domain_02.pdb`, CSV says
  `timeout` at 2701.8s) where the log shows a genuine fit found
  (`Best fit in density search with CC = 0.43`) and a valid 131KB
  output file exists on disk, written ~4 min after the log's last
  visible line. Mechanism: `proc.wait(timeout=JOB_TIMEOUT_SEC)` in
  `run_one_domain()` raises `TimeoutExpired` and jumps straight to
  `status="timeout"` **without checking if `out_path` already exists**
  — if Phenix's own process is slow to exit after finishing its actual
  work (cleanup/post-processing after the write), our watchdog can
  kill a job that already succeeded and mislabel it. **Action for the
  report**: don't trust `status=="timeout"` as "no fit found" either —
  every `timeout` row needs the same disk-file check as `docked` rows
  needed for the CC post-filter. True success count across the batch
  is likely higher than the CSV shows. Best done as part of the
  planned final independent CC-verification pass (check every file in
  every `AF3_docked_models/`, regardless of what its CSV row says).
- **`failed_rc1`** — Phenix's Python process exited with an *uncaught
  exception* (rc=1), not a signal kill. Confirmed instance:
  `65506/fold_9w0j_3_model_0_chain_A_domain_01.pdb` (13.0s, near-instant
  — fails before any real search work). Traceback bottoms out at
  `phenix/autosol/run_phaser_mr.py:620` →
  `RuntimeError: INPUT: No scattering in coordinate file`. Root cause
  confirmed by inspecting the actual PDB: **every atom's occupancy
  column reads `0.00`**, vs. `1.00` in a working domain file from the
  same entry (`fold_9w0j_5_model_0_...`) — zero occupancy means zero
  scattering contribution, so Phaser has nothing to search with. This
  is a **data-quality defect in that specific AF3-predicted model**
  (model 3 of 9w0j's 5 predicted seeds), not a Phenix bug, not a
  resource/infra issue. Worth spot-checking whether other AF3 models
  across entries share this zero-occupancy defect (would explain
  otherwise-unexplained fast failures elsewhere) — not yet checked
  beyond this one instance. **Second instance observed**:
  `64362/fold_9unu_7_model_0_chain_A_domain_01.pdb` (124.4s, same
  near-instant failure profile). Log not yet inspected to confirm same
  zero-occupancy cause, but timing signature matches — likely the same
  defect, pending confirmation. **Third instance, now confirming the
  pattern is per-AF3-model-seed, not per-domain**:
  `73799/fold_9z49_3_model_0_*` — **all 4 of model_3's domains**
  (`chain_A/B/C/D_domain_01`) failed identically via `failed_rc1`,
  97-133s each. An entire AF3 model prediction failing uniformly
  across every domain strongly suggests the defect (likely the same
  zero-occupancy issue) originates at the AF3 model level — probably
  every atom in that specific predicted structure (not just one
  domain's worth) has occupancy=0.00. Log not individually inspected
  per domain here (pattern inference from timing + uniformity), but
  consistent enough with the confirmed mechanism to report as the
  same defect class.
- **`failed_rc-11`** — killed via `SIGSEGV` (genuine segfault), a new
  category. One confirmed instance:
  `64362/fold_9unu_10_model_0_chain_A_domain_01.pdb` (170.6s, fast).
  Not yet root-caused (log not inspected) — distinct from every other
  category here (not OOM, not our timeout, not a Phaser exception, not
  an uncaught Python exception). Likely a memory-corruption bug in
  Phenix's underlying C/C++ layer triggered by something specific to
  this domain's input, but unconfirmed pending a log check.
- **`failed_rc-6`** — killed via `SIGABRT`. **Root cause confirmed**
  (`64568/chain_C_domain_01`, 178.0s, log inspected in full): a genuine
  **Phaser internal crash**, not a memory-pressure abort —
  `terminate called after throwing an instance of 'phaser::error'`,
  `what(): Program internal error in source file DataMR.cc (line 502)`,
  `*** Consistency check (V > 0) failed. ***`. This is a real bug/limit
  in Phenix's bundled Phaser molecular-replacement engine triggered by
  this specific search_model/map pair — a genuine *tool-level failure*,
  distinct from the OOM/timeout infrastructure failures above.
  **Recurring, not a one-off**: 2 more instances since
  (`75023/chain_B_domain_01` 153.6s, `75023/chain_C_domain_01` 185.9s) —
  3 total so far, all fast (153-186s), all well under the timeout.
  Worth reporting as its own failure category with a real frequency,
  not an isolated anomaly, and not a resource-exhaustion symptom.

## Snapshot as of second check (31 unique domains attempted, 8 docked)

`67233` is now **fully attempted (12/12) with a 0% success rate** —
every domain in this entry has failed at least once. Checked whether
this is a config bug (same pattern as the earlier `9UWY` contour-level
discovery) before assuming it's just the general resource constraint:
`contour=0.1, resolution=5.7` both confirmed correct against the
EMDB-fetched values used everywhere else. No config bug found — this
entry's 0% rate looks consistent with the general large/domain-heavy
map pattern, not a separate issue. (Failure logs themselves are empty
past the header for `SIGKILL`'d jobs — known stdout-buffering
limitation, not new evidence either way.)

| Entry | Domain | Status | Elapsed (s) | Notes |
|---|---|---|---|---|
| 79027 | chain_D_domain_02 | failed_rc-9 | 1362.6 | |
| 79027 | chain_D_domain_03 | failed_rc-9 | 785.2 | |
| 79027 | chain_D_domain_01 | failed_rc-6 | 970.5 | see rc-6 caveat above |
| 79027 | chain_C_domain_03 | timeout | 2700.4 | |
| 67233 | chain_A_domain_01 | failed_rc-9 | 1450.3 | |
| 67233 | chain_A_domain_03 | failed_rc-9 | 1964.0 | |
| 67233 | chain_A_domain_02 | failed_rc-9 | 1251.2 | |
| 67233 | chain_A_domain_04 | failed_rc-9 | 1473.2 | |
| 67233 | chain_B_domain_03 | timeout | 2702.2 | Run 2's actual attempt (Run 1 had this as rc-9) |
| 67233 | chain_B_domain_02 | failed_rc-9 | 1213.6 | |
| 67233 | chain_A(2)_domain_02 | failed_rc-9 | 949.7 | model 2 |
| 67233 | chain_B_domain_04 | failed_rc-9 | 1627.9 | |
| 67233 | chain_B_domain_01 | timeout | 2703.4 | |
| 67233 | chain_B(2)_domain_02 | failed_rc-9 | 1666.0 | model 2 |
| 67233 | chain_A(2)_domain_01 | timeout | 2703.2 | model 2 |
| 67233 | chain_B(2)_domain_01 | timeout | 2703.8 | model 2 |
| 73799 | chain_A_domain_03 | failed_rc-9 | 1397.7 | |
| 73799 | chain_A_domain_02 | failed_rc-9 | 1441.6 | |
| 73799 | chain_B_domain_02 | failed_rc-9 | 1043.7 | |
| 73799 | chain_A_domain_01 | failed_rc-9 | 2458.3 | |
| 73799 | chain_C_domain_01 | failed_rc-9 | 1027.1 | |
| 73799 | chain_B_domain_01 | failed_rc-9 | 1613.6 | |
| 73799 | chain_B_domain_03 | failed_rc-9 | 1083.2 | |
| 73799 | model_2/chain_B_domain_02 | failed_rc-9 | 1289.3 | |
| 73799 | model_2/chain_B_domain_01 | timeout | 2703.0 | |
| 73799 | model_2/chain_D_domain_02 | failed_rc-9 | 547.7 | |
| 73799 | model_2/chain_C_domain_01 | failed_rc-9 | 2419.2 | |

**23 currently failed** (17 `rc-9`, 5 `timeout`, 1 `rc-6`), **8 docked**,
out of 31 unique domains attempted so far. 116 domains not yet attempted.
Note: within a single continuous `dock_batch.py` run, a failed domain
is *not* automatically retried — it only gets re-queued on a fresh
relaunch (the resumable `discover_jobs()` scan only runs once at
start).

## Snapshot as of third check (45 unique domains attempted, 14 docked)

Queue-reorder is paying off — every newly-reached entry (`62164`,
`64568`, `75023`) has landed at least one `docked` result, unlike
`67233`/`73799`'s 0% runs. Two of these `docked` results (`64568`
chain_C_domain_02 CC=0.08, chain_B_domain_02 CC=0.1) are **below our
own `min_cc=0.2` bar** — see the `docked` category caveat above; don't
count these as good fits without the CC post-filter.

| Entry | Domain | Status | Elapsed (s) | Notes |
|---|---|---|---|---|
| 62164 | chain_A_domain_01 | timeout | 2701.7 | |
| 64568 | chain_A_domain_02 | timeout | 2701.7 | |
| 64568 | chain_A_domain_01 | timeout | 2709.4 | |
| 64568 | chain_C_domain_01 | failed_rc-6 | 178.0 | see rc-6 root cause above |
| 64568 | chain_B_domain_01 | failed_rc-9 | 1466.7 | |
| 64568 | chain_C_domain_02 | docked | 2037.6 | CC=0.08 — below min_cc=0.2, see caveat |
| 64568 | chain_B_domain_02 | docked | 2111.5 | CC=0.1 — below min_cc=0.2, see caveat |
| 75023 | chain_A_domain_01 | failed_rc-9 | 904.4 | |
| 75023 | chain_B_domain_01 | failed_rc-6 | 153.6 | |
| 75023 | chain_A_domain_02 | docked | 1269.7 | CC=0.45 — genuinely above threshold |
| 75023 | chain_C_domain_01 | failed_rc-6 | 185.9 | |
| 75023 | chain_B_domain_02 | failed_rc-9 | 778.1 | |
| 75023 | chain_A_domain_03 | docked | 2552.2 | CC=0.44 — genuinely above threshold, cut close to 45-min timeout |

**Overall so far: CC values checked per-entry, not assumed** — pulled
actual final_cc for every `docked` row before writing this up:
- `79027`: 8 `docked` rows in CSV (CC 0.62, 0.56, 0.62, 0.56, 0.49, 0.49,
  0.1, 0.1) → **6 genuinely ≥0.2, 2 below** (both 0.1).
- `62164`: 1 docked (chain_A_domain_02, CC=0.28, local-transfer result,
  not in pod CSV — checked its own log directly) → **genuinely ≥0.2**.
- `64568`: 2 docked (CC 0.08, 0.1) → **both below 0.2**, per the caveat
  above.
- `75023`: 2 docked (CC 0.45, 0.44) → **both genuinely ≥0.2**.

**True CC≥0.2 success count: 9 of 14 `docked`-status domains** (64%).
`status=="docked"` alone overstates success by ~36% right now — the
CC post-filter is not optional for the final report.

**Resolved** (was open question 6): `79027`'s docked-file/CSV
discrepancy has the same root cause confirmed via `62164`. `62164`'s
CSV shows `chain_A_domain_02` as `failed_rc-9` (2317.5s), but the file
on disk is byte-identical (same md5, same 17:27 timestamp) to the
original local-transfer success (CC=0.28) — **untouched**. Mechanism:
`discover_jobs()` scans and fixes the job list once at run start; a
domain queued before its file existed can still get attempted later by
a worker, and if that later attempt gets killed (OOM/timeout) *before*
it reaches the write step, the pre-existing good file survives
untouched while the CSV still records the later attempt's failure as
that domain's status. **General methodology implication: the CSV's
per-domain status is not reliable ground truth on its own — the actual
file in `AF3_docked_models/` is.** Final analysis must cross-reference
disk state, not just filter the CSV. `79027`'s 9th file is almost
certainly the same pattern (a domain succeeded once, was re-attempted
and failed later in the same continuous run, CSV shows the failure,
file shows the earlier success).

`75023` and `65506` still have domains in flight (2 each) not yet in
this snapshot.

**Update**: `65506/chain_A_domain_02` → **docked, CC=0.54** (genuinely
≥0.2, 732.3s). Running total genuine CC≥0.2 successes: **10**.

## FINAL tally (batch complete, all 147 domains attempted, log-cross-referenced against disk)

Batch finished Wed Sep 30 12:17:26 UTC (19h28m wall-clock, 77.87
worker-hours). Ran a log-cross-reference pass against every file
actually on disk (34 total) instead of trusting CSV `status` alone —
for each docked file, checked whether its *own* log still matches it
(not overwritten by a later failed re-attempt) before trusting the
CC therein. Full independent recomputation (real map-model
correlation) still needs the raw maps, which aren't local yet — this
is the best available ground truth until then.

| Entry | Files on disk | Total domains | Confirmed genuine (CC≥0.2) | Confirmed low-CC (<0.2) | Unknown (log mismatch) |
|---|---|---|---|---|---|
| 62164 | 1 | 2 | 1 (CC=0.28, resolved via pre-transfer local log) | 0 | 0 |
| 64568 | 2 | 6 | 0 | 2 (0.08, 0.1) | 0 |
| 65506 | 2 | 8 | 2 (0.54, 0.59) | 0 | 0 |
| 67233 | 1 | 12 | 1 (CC≈0.43, resolved via log tail — see Stage re: buffering cutoff) | 0 | 0 |
| 70609 | 12 | 18 | 6 (0.31, 0.3, 0.29, 0.31, 0.31, 0.32) | 6 (0.1, 0.1, + 4 resolved via independent recomputation) | 0 |
| 71787 | 2 | 12 | 0 | 2 (0.09, + 1 resolved via independent recomputation) | 0 |
| 71973 | 2 | 13 | 2 (0.55, 0.55) | 0 | 0 |
| 75023 | 3 | 8 | 3 (0.45, 0.44, 0.47) | 0 | 0 |
| 76934 | 0 | 10 | 0 | 0 | 0 |
| 79027 | 9 | 12 | 6 (0.56, 0.49, 0.56, 0.62, 0.62, 0.49) | 3 (0.1, 0.1, + 1 resolved via independent recomputation) | 0 |
| 64362 | 0 | 22 | 0 | 0 | 0 |
| 73799 | 0 | 24 | 0 | 0 | 0 |
| **Total** | **34** | **147** | **21** | **13** | **0** |

**21/147 confirmed genuine successes (14.3%), fully resolved — zero
domains remaining unknown** across **7 of 12 proteins**: `62164`,
`65506`, `67233`, `70609`, `71973`, `75023`, `79027` each have ≥1
genuine (CC≥0.2) success. `64568` has 2 files but both are low-CC, so
0 genuine there despite having output. **4 proteins at true 0/N
genuine success**: `71787` (2 files, both low-CC, confirmed via
independent recomputation), `76934`, `64362`, `73799` (these last 3
have zero output files at all).

**RESOLVED — independent CC recomputation complete** (see `CLAUDE.md`
Stage 20, `recompute_cc.py` / `cc_recomputation_unknown_domains.csv`).
Method: `phenix.map_correlations` (CC_mask) run directly against the
real map for every docked file in the 3 affected entries, using the
exact resolution values `dock_in_map` itself used
(`70609`=5.3 Å, `71787`=5.1 Å, `79027`=4.7 Å). Validated first against
2 already-known values from other entries (log CC=0.45 → recomputed
0.486; log CC=0.08 → recomputed 0.058 — same pass/fail classification,
small systematic offset from dock_in_map's own internal CC, expected
given different default mask-construction parameters between the two
tools).

**All 6 previously-unknown domains resolved as low-CC (not genuine) —
none pan out.** Per-entry, all docked files on disk independently
recomputed:
- `70609` (12/12 domains recomputed): 6 genuine (CC_mask 0.287-0.319,
  matches the already-known ~0.29-0.32 cluster) + 6 low-CC (CC_mask
  0.004-0.074, includes the 4 previously-unknown ones). **6/18
  unchanged.**
- `71787` (2/2 domains recomputed — the only 2 that ever produced
  output): both low (-0.010, 0.066), including the 1 previously-unknown
  one. **0/12 unchanged.**
- `79027` (9/9 domains recomputed): 6 genuine (CC_mask 0.526-0.653) +
  3 low-CC (CC_mask 0.081-0.109, includes the 1 previously-unknown
  one). **6/12 unchanged.**

**Final, fully-resolved total: 21/147 confirmed genuine (14.3%), zero
domains remaining unknown.** The earlier "could shift up to 27/147
(18.4%) best case" range does not materialize — resolve to the lower,
already-reported figure.

## Manual interventions (not automatic kills)

- **2 `79027` jobs manually killed** — PIDs 17936/18575, at 40.8GB and
  31GB RSS and climbing (~2-3GB/min growth rate), killed preemptively
  before they could trigger a cascading OOM affecting the other 2
  healthy concurrent workers. Important finding: **this contradicts
  the earlier assumption that risk was concentrated on the largest
  maps** — `79027` is one of the smallest maps in the set (64MB). The
  real driver appears to be domain-specific search difficulty, not map
  size — any domain can trigger unbounded growth if genuinely hard to
  place. `67233`/`73799` showing more failures so far may simply
  reflect that they have more domains overall (12 and 24 respectively,
  vs. 79027's much smaller AF3_domains set), not a real size-driven
  hazard difference. Memory usage was also observed to *oscillate*,
  not just climb monotonically — one job dropped from 38.9GB back to
  15GB unprompted, so not every high-memory reading is a guaranteed
  runaway; only intervene when total container memory genuinely
  approaches the cap.

## Open questions for the report

1. ~~What actually causes `failed_rc-6` (SIGABRT)?~~ **Resolved**: genuine
   Phaser internal crash (`phaser::error`, `DataMR.cc:502`, "Consistency
   check (V > 0) failed"), confirmed via full log inspection of
   `64568/chain_C_domain_01`. See category definitions above.
2. Is domain-specific search difficulty predictable in advance (e.g.
   correlated with domain size, symmetry, or AF3 prediction confidence)
   or genuinely unpredictable? Would need to inspect a few of these
   specific domains' AF3 confidence scores / structures to say.
3. Final failure rate once the full 147-domain batch completes — this
   snapshot is early (45/147 attempted so far).
6. ~~`79027` shows 9 files on disk but 8 `docked` CSV rows~~ **Resolved**:
   same disk-survives-a-later-failed-retry mechanism confirmed via
   `62164` — see the CSV-vs-disk methodology note above.
7. Is the `65506` model-3 zero-occupancy defect (`failed_rc1`) isolated
   to that one file, or does it affect other AF3 models across entries?
   Only checked the one instance so far.
8. ~~6 unresolved-CC domains (4 in `70609`, 1 in `71787`, 1 in `79027`)~~
   **Resolved**: independent `phenix.map_correlations` (CC_mask)
   recomputation against the real maps, method validated against 2
   already-known values first. All 6 are low-CC, none genuine. Final
   total locked at 21/147 (14.3%), zero domains remain unknown.
4. Why does `67233` have a 0% success rate despite a confirmed-correct
   config? Ruled out contour-level/resolution bugs; remaining
   hypotheses are purely resource/search-difficulty related, not yet
   distinguished from `73799`'s similar pattern.
5. ~~Unresolved anomaly~~ **Resolved**: `67233` domains
   (`chain_B_domain_03/04`, `chain_A(model2)_domain_01/02`) appeared to
   show up both as already-logged failures and as actively running.
   Traced the exact PIDs across repeated checks and confirmed they were
   the *same* processes throughout (still running, not resubmitted) —
   the apparent duplication was because `docking_results.csv` merges
   data from **both** runs (the original 7-worker attempt and this
   4-worker relaunch, never reset between them, by design for
   resumability). The "failed" row for these domains was from Run 1;
   the long-running processes I was seeing were Run 2's first-ever
   attempt at those same domains. Not a script bug — just my own
   misread comparing across the two runs' merged data without
   accounting for which run each row came from.
