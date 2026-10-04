# Patches to upstream MICA

Base: https://github.com/jianlin-cheng/MICA (no pinned commit — the
original checkout here was unpacked from a release tarball, not a
`git clone`, so there is no exact SHA to cite; the patches below are
small and self-contained enough to apply against current `main`).

Also required: `pip install superpose3d==1.1.1` specifically (not the
current PyPI default, `1.5.0`). `utils/modeler.py:202` calls
`Superpose3D(...)[0][0]`, which assumes a nested return shape that
changed somewhere between 1.1.1 and 1.5.0 — `1.5.0` throws
`IndexError: invalid index to scalar variable` partway through
Cα-sequence alignment. Not a file patch, just a pinned pip install.

## `dock_in_map.py`

Replaces the upstream CPU-core-only `nproc` formula
(`min(max(int(cpu_cores * 0.6), 1), 48)`) with a flat `nproc=4`, and
switches `quick=False` → `quick=True`, `min_cc=0.2` explicit.

Why: the upstream formula caused repeated OOM kills on both a 16GB
local Mac and a 128GB RunPod CPU pod — `nproc` controls
`phenix.dock_in_map`'s box-splitting (`target_boxes`), not a memory
ceiling, and `quick=False` runs an exhaustive search that grows
memory unboundedly over wall-clock time on some domains (one case ran
6+ hours before being killed). `quick=True` triggers Phenix's own
early-exit once a correlation threshold is reached.

Also note: `dock_in_map.py`'s own `except subprocess.TimeoutExpired`
branch is dead code — the `subprocess.run()` call never passes a
`timeout=` argument, despite the error message implying a 1-hour cap
exists. `runpod_scripts/dock_batch.py` enforces its own real timeout
(process-group kill) instead of relying on this.

Even with this patch, large maps (`dock_chains_individually=True`
loads the full map per domain search) can still exceed memory under
concurrent batch execution — worker-pool sizing (`MAX_WORKERS` in
`runpod_scripts/dock_batch.py`) is the real lever for that, not this
patch alone. Expect a non-trivial docking failure/timeout rate on
large maps regardless; see `data/docking/FAILED_CASES.md` for exactly
what this run's rate was and why.

## `predict.py`

Replaces `self.optimal_batch_size = self._calculate_optimal_batch_size()`
with a hardcoded `self.optimal_batch_size = 1`.

Why: `_calculate_optimal_batch_size()` estimated batch_size=8 fits a
conservative ~10GB budget; real peak usage was 13.4GB+ on a 14.6GB
Colab T4, causing an immediate CUDA OOM on the very first batch. No
CLI flag exposes this otherwise — direct patch was the only option.

## How to apply

```bash
git clone https://github.com/jianlin-cheng/MICA.git
cp patches/dock_in_map.py MICA/utils/dock_in_map.py
cp patches/predict.py MICA/utils/predict.py
pip install superpose3d==1.1.1
```
