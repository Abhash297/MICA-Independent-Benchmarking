# What CryoZeta Is and How It Works

Companion to `METHODOLOGY_LAYMAN.md` / `METHODOLOGY_EXPERT.md` — those
explain the whole 12-protein benchmark; this file is scoped to just
the 5th method added at Cheng's request (see `CLAUDE.md` Stage 22).
Two versions below, same structure as the main methodology docs.

---

## For a layman

**The one-sentence version**: CryoZeta is an AI that looks at a
protein's blurry 3D microscope photo *and* its genetic "ingredient
list" (the amino acid sequence) at the same time, and guesses the
precise atom-by-atom shape directly from both — no separate guessing
step, no separate fitting step, just one AI doing both jobs at once.

**How this is different from MICA.** MICA is like a two-person relay
race. Runner 1 (AlphaFold3) is handed only the ingredient list and has
to guess the shape blind — it never sees the actual microscope photo.
Runner 2 (Phenix docking) then forces that blind guess to physically
fit into the real photo, piece by piece. Runner 3 (MICA itself) then
looks at both the forced-fit guess and the photo together and cleans
up the final answer. Three separate tools, three separate steps,
handed off in sequence.

CryoZeta skips the relay entirely — one single AI looks at the
ingredient list and the blurry photo together, from the very start,
and produces an answer already informed by both. No blind guessing
stage, no separate forced-fit stage.

**What actually happens inside, step by step, per protein:**

1. **Scan the photo.** A first pass over the blurry 3D microscope
   image makes a rough guess at roughly where atoms might be.
2. **Refine, repeatedly.** That rough guess gets tightened over and
   over — like sharpening a pencil sketch into a cleaner drawing —
   using both the photo and the ingredient list together each time.
3. **Produce 5 different finished drafts.** Rather than committing to
   one answer, it generates 5 independent attempts at the complete
   structure.
4. **Grade each draft against the real photo.** For each of the 5
   drafts, it checks how well the draft's shape actually lines up with
   the blurry photo, using two different "overlay" techniques (think
   of two people independently trying to line up a cutout shape on top
   of a stencil, using different strategies) — then keeps whichever
   overlay technique worked better for that draft.
5. **Save the winning draft(s).** The best-scoring drafts, in ranked
   order, get written out as the final answer.

**For very large proteins** (more chains/atoms than it can handle in
one pass), CryoZeta can't solve the whole jigsaw puzzle at once — so
it breaks the protein into chunks, solves one chunk's worth at a time,
and each time it finishes a chunk, it sets that part of the photo
aside so the next chunk only has to search the leftover, unclaimed
part of the image. This project calls that "large-complex mode" and
it's what two of our biggest proteins (`67233`, `73799`) needed.

**Why it needs extra information we had to provide ourselves.**
Even though CryoZeta doesn't need a separate AlphaFold3 step like
MICA does, it still needs something called an MSA (a list of
similar sequences found across many known proteins, used as a kind
of evolutionary hint) for each protein chain. We generated these
ourselves using a free tool (ColabFold) before running CryoZeta,
the same way the AlphaFold3 service would normally compute this
internally.

---

## For an expert

**Architecture summary.** CryoZeta (Kihara Lab, Purdue; bioRxiv
preprint, 2026-02-16, postdates the MICA paper — not one of its
original baselines) is a diffusion-based, AF3-architecture model that
takes sequence (+ precomputed MSA) and cryo-EM density map as two
fused input channels directly, in a single forward pass — structurally
the opposite design choice from MICA/EModelX(+AF), which treat an
externally-generated AlphaFold3 prediction as a separate, pre-docked
input rather than fusing map and sequence natively inside one network.

**Pipeline, per entry (confirmed by reading the actual source this
session, not from the paper alone):**

1. **Detection** (`cryozeta-detection`) — a sliding-window 3D CNN
   (`sliding_window_inference`) scans the preprocessed, contour-
   thresholded density map in overlapping boxes, producing a dense
   per-voxel backbone/Cα probability volume. This step is GPU-light
   but became the real bottleneck for large maps: the *post*-inference
   step that converts the dense voxel volume into a sparse point list
   is CPU/RAM-bound (not GPU-bound) and scales with raw map size, not
   residue count — this is what OOM'd on `64362` and `67233` under a
   92GB container RAM cap, resolved by moving to a pod with a 251GB
   cgroup ceiling.
2. **EMPairformer cycles** (`model.N_cycle`, default 10) — an
   AlphaFold3-style Pairformer trunk (`empairformer.py`), iteratively
   refining single (`s`) and pair (`z`) representations conditioned on
   both the MSA features and the EM-derived point features. This is
   the dominant per-sample wall-clock cost (~130-390s/cycle observed
   this session, scaling with `N_token`/`N_msa`, i.e. with protein
   size/chain count — `64362`'s 11-chain, N_msa=14477 entry ran at
   ~3x the per-cycle cost of `67233`'s single-chain, N_msa=2429 stage).
3. **Diffusion sampling** (`sample_diffusion.N_sample=5`,
   `N_step=20`) — generates 5 independent full-atom structure samples
   per cycle-refined representation, not one single committed answer.
4. **Registration** — each sample's predicted coordinates are rigid-
   body registered into the real map's coordinate frame via two
   independent methods, TEASER++ (certifiable outlier-robust point
   cloud registration) and SVD/Kabsch superposition
   (`compare_registration_methods`), with the higher-recall method
   selected per sample (e.g. `67233_stage_1`: TEASER recall=0.623 vs.
   SVD recall=0.202 → TEASER selected). A real, observed failure mode:
   TEASER++ can fail to write its `.npz` output for a given
   sample/stage, falling back to an exhaustive rotational/translational
   grid search that can degrade to `NaN` scores for genuinely
   ambiguous point clouds (`67233_stage_3`, this session).
5. **Fit scoring** — `recall`, `ccc_mask`, `ccc_box`,
   `num_dist_over_4`, `recall_ccmask_ca` computed per
   (sample × registration-method) combination, written to
   `scores.csv`. This is the only artifact `combine.py` reads for
   final selection — everything downstream of here (confidence head,
   file writing) is independent of these scores already being final.
6. **Confidence head** (`run_confidence_head` → `ConfidenceHead`, a
   separate Pairformer-stack sub-network) — computes per-atom
   `plddt`/`pae`/`pde`/`resolved` estimates for output annotation
   only; does not alter coordinates. Confirmed via direct traceback
   this session (`76934`'s crash) that this step runs *after* scoring
   is already complete and saved, and its failure has zero effect on
   which structure gets selected or how it scores on any evaluation
   metric used in this project.
7. **Combine** (`cryozeta-combine`) — sorts every (sample, method) row
   in `scores.csv` by `recall_ccmask_ca` descending, copies the top
   `num_select` (= `N_sample` by CryoZeta's own default, i.e. all 5,
   just rank-ordered) into `CryoZeta-Final/<id>_sample_{0..4}.cif` —
   `sample_0` is therefore CryoZeta's own highest-confidence pick, not
   an arbitrary first sample.

**Worked example, with deliberately tiny numbers.** Say the input is a
single 10-residue toy chain, `MKVLAADGST`, plus its density map and a
precomputed MSA with 40 homologous sequences.

1. **Detection** scans the map's voxel grid (say a modest
   64×64×64 box) and outputs a dense per-voxel Cα-probability volume,
   then converts it to a sparse point list — maybe 14 candidate atom
   positions survive thresholding (real proteins: thousands).
2. **EMPairformer cycles** build `s` (per-residue, shape
   `[10, c_s]`) and `z` (per-residue-pair, shape `[10, 10, c_z]`)
   representations from the MSA + the 14 EM points, and refine both
   10 times (`N_cycle=10`), each cycle letting sequence information
   and map information inform each other a bit more.
3. **Diffusion sampling** turns the refined `s`/`z` into 5 candidate
   full sets of 3D coordinates for all 10 residues' atoms (`N_sample=5`,
   `N_step=20` denoising steps each) — 5 independent "guesses" at the
   finished shape, not one answer.
4. **Registration** takes each of the 5 guesses and rigid-body-fits it
   onto the real 14-point map cloud via TEASER++ and SVD, keeping
   whichever gives higher recall per guess — e.g. guess #3 might get
   TEASER-recall 0.81 vs. SVD-recall 0.55, so TEASER's fit is kept for
   guess #3.
5. **Scoring** writes one row per (guess, method) to `scores.csv` —
   with 5 guesses × 3 methods (svd_0.8, svd_0.4, teaser) that's 15
   rows total, each with `recall`/`ccc_mask`/`recall_ccmask_ca` etc.,
   exactly the shape seen in every real `scores.csv` this project
   produced (`76934`'s, `64362`'s — always 15 rows for a single-stage
   entry, 5 samples × 3 methods).
6. **Confidence head** separately estimates, for whichever guess gets
   used, how sure the model is about each of the 10 residues'
   placement — purely descriptive, changes nothing above.
7. **Combine** sorts those 15 `scores.csv` rows by
   `recall_ccmask_ca`, and if guess #3/teaser has the top score, it
   gets copied in as `<id>_sample_0.cif` — CryoZeta's official answer
   — with the other 4 top-ranked rows following as `sample_1..4.cif`.

Scale this up from 10 residues/14 points/64³ voxels to a real entry
(hundreds to thousands of residues, tens of thousands of EM points,
400³+ voxel grids) and the mechanics are identical — just why
`64362` (2,395 tokens) took ~390s/cycle while `67233` (1,542 tokens)
took ~130s/cycle: the same 7 steps, scaled.

**Large-complex mode** (`large_inference_demo.sh`, triggered above
~2,800 residues on 32GB-class hardware): processes the entry as N
sequential stages (`cycle_predict.py`), one chain/copy-group per
stage, cropping already-assigned EM points out of the working point
cloud after each stage (`crop_em_points`) so later stages search only
the remaining unassigned density — a greedy, order-dependent
assignment strategy, not a joint multi-chain optimization.

**Real bugs found in the released code this session** (beyond the
paper/preprint's own disclosed specs):
- `combine.py` compares `scores.csv`'s `pdb_id` column (pandas-inferred
  `int64` for any all-numeric entry name) against a Python `str` loop
  variable — always `False`, silently producing zero `CryoZeta-Final`
  output for every purely-numeric entry name with no error raised.
- `combine.py`'s file-copy step assumed every top-scored candidate's
  `.cif` exists on disk; crashes with `FileNotFoundError` if that
  specific candidate's registration step failed to write output
  despite being scored.
- `large_inference_demo.sh` defaults to GPU index 1 (`-g`) and parses
  `--example`/`-x` as a numeric array index when the entry name is
  itself all-digits — both silently wrong for this project's EMDB-
  style entry names, requiring explicit `-g 0 -x <index>`.
- On Blackwell GPUs specifically (not Hopper/Ampere): Triton's
  `get_ptxas()` requests a binary literally named `ptxas-blackwell`
  via an env var CryoZeta's own scripts export with the wrong
  character (`_` vs `-`, which bash cannot even express as a valid
  variable name) — plus a separate, unfixable Triton MLIR codegen gap
  for Blackwell's `sm_120` matrix-multiply path, worked around by
  disabling `use_deepspeed_evo_attention`/`use_cuequivariance` to
  force a plain-PyTorch attention fallback.

**Recovery methodology used when CryoZeta's own writer failed but the
underlying computation succeeded**: `predict()`'s raw
`pred_all_coordinate` tensor is saved to `output_dict_<id>.pt`
*before* the confidence head or file-writing steps run. A standalone
script re-featurizes the entry on CPU (`InferenceDataset`, no GPU) and
calls CryoZeta's own `save_structure_cif` directly on the saved
tensor — bypassing the broken step entirely, reproducing byte-for-byte
identical coordinates to what CryoZeta's native writer would have
produced (verified against entries where both paths existed).
Large-complex mode checkpoints this per *stage* (not just per sample),
so a crash late in a multi-stage entry (e.g. `67233` reaching stage
3/4) still leaves stages 1-3's raw predictions recoverable even though
stage 4 never ran.
