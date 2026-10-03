# RunPod command reference

Practical command cheat-sheet for this project's RunPod usage. Update
IP/port every time the pod is redeployed — they change on every fresh
deploy (confirmed multiple times this session). Current values are
tracked in `sync_from_pod.sh`'s `POD_HOST`/`POD_PORT` variables; check
there first before assuming these examples are current.

## Deploying a pod from scratch (dashboard steps)

**Do this first, before deploying anything — SSH keys only get
injected at genuine deploy time, not retroactively:**
1. Generate a dedicated key (see "SSH key" section below) if you
   haven't already.
2. Go to RunPod **Settings → SSH Public Keys → Add SSH key**, paste
   the full public key contents, give it a title, save. Confirm it
   shows up in the list with the right fingerprint before proceeding.

**Then, on the Deploy page:**
1. **Workload / template**: leave the default (`Runpod Ubuntu 20.04`)
   unless you need something else.
2. **Pod name**: rename from the random default if you want something
   identifiable (cosmetic only).
3. **Region**: click **"Specific region"**, not "Any region" — pick
   one explicitly. This matters because a Network Volume is pinned to
   whatever region it's created in, and the pod's region must match
   or the volume silently won't attach (confirmed the hard way this
   session — "Any region" once landed the pod in a different region
   than the volume, and the dashboard's size numbers looked plausible
   enough that it wasn't obvious until checked via SSH).
4. **Compute tab → CPU** (not GPU, for the docking-only pod). Pick a
   tier — **General Purpose** was chosen over Compute-Optimized here
   specifically for the higher RAM-per-core ratio (4GB/core vs
   2GB/core), given every local failure this project hit was
   memory-bound, not CPU-bound.
5. **Network volume dropdown**: either select an existing volume
   (should appear by name if the region matches) or create a new one.
   If creating new: pick a data center, checking the live
   **Type/Availability** panel next to it for what's actually in
   stock there (click a GPU type to filter by it, if relevant later
   for the GPU pod) — for this CPU pod, just confirm CPU availability
   shows "High." Set size deliberately (billed on **provisioned**
   size, hourly-prorated, not on actual bytes used — don't
   over-provision "just in case"). Toggle "High-performance storage"
   off if the region allows it (some regions lock it on).
6. Confirm the price breakdown panel shows what you expect (compute +
   container disk cost; the volume's own cost is separate/monthly,
   not folded into this hourly figure), then **Deploy Pod**.

**After deploying**, go to the pod's **Connect** tab and use the
**"SSH over exposed TCP"** command, not the top "SSH" (proxied)
option — the proxied one doesn't support SCP/SFTP, which this
workflow needs for file transfer. Substitute the custom key path
(see below) for whatever default path RunPod's own generated command
shows.

**If a fresh pod's key doesn't work** (permission denied even though
the key is correctly listed in Settings): don't bother with
Stop→Start, it recreates the container but doesn't re-inject keys.
**Terminate and deploy fresh instead** — that's the only thing that
reliably fixed it this session.

## SSH key

**This is a one-time, account-level setup — not per-pod.** Once the
public key is registered on your RunPod account, every subsequently
deployed pod (CPU, GPU, any region) gets it auto-injected into
`authorized_keys` automatically. No new keygen or re-registration
needed for new pods — confirmed this session: the GPU pod deployed
hours after the CPU pod connected immediately with the same key,
zero extra setup.

**Manual steps, from scratch:**

1. **Generate a dedicated keypair** on your local machine (separate
   name so it doesn't overwrite your Mac's existing default
   `~/.ssh/id_ed25519`, if one already exists for other purposes):
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519_runpod
   ```
   Press enter through the passphrase prompt for no passphrase (or set
   one — your choice, just remember it if so). This creates two
   files: `id_ed25519_runpod` (private, never share) and
   `id_ed25519_runpod.pub` (public, this is what gets uploaded).

2. **Copy the public key contents:**
   ```bash
   cat ~/.ssh/id_ed25519_runpod.pub
   ```
   Copy the entire single-line output (starts with `ssh-ed25519
   AAAA...`, ends with your email comment).

3. **Register it on RunPod**, *before* deploying any pod — go to
   **Settings → SSH Public Keys → Add SSH Key**. Paste the full
   public key contents, give it a title (e.g. "MacBook - MICA
   project"), save. Confirm it appears in the list with a fingerprint
   shown.

4. **Deploy normally from here on** — every pod (this session proved
   it across both a CPU pod and, much later, a completely separate
   GPU pod) will have this key pre-injected. Connect with:
   ```bash
   ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP>
   ```
   Always use `-i ~/.ssh/id_ed25519_runpod` explicitly — RunPod's own
   auto-generated SSH command in the dashboard defaults to the
   *generic* `~/.ssh/id_ed25519` path, which is wrong unless that
   happens to be the exact file you registered. Substitute manually
   every time, don't copy-paste their suggested command as-is.

**Timing matters**: keys are only injected into `authorized_keys` at
genuine pod **deploy** time, not retroactively. If you add a key to
your account *after* a pod is already running, that existing pod won't
have it — Stop/Start doesn't re-inject either (recreates the
container but skips key injection; confirmed via the pod's own boot
logs showing sshd starting cleanly while still rejecting the key).
Only a fresh Terminate + Deploy picks up a newly-added key.

## Connecting

Use the **"SSH over exposed TCP"** option from the pod's Connect tab,
not the top "SSH" (proxied via `ssh.runpod.io`) option — the proxied
one explicitly does not support SCP/SFTP, which this workflow needs.

```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod -o StrictHostKeyChecking=accept-new root@<IP>
```

Quick health check after connecting:
```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> \
  "nproc; free -h; df -h /workspace; mount | grep workspace"
```
The last two confirm the Network Volume is actually mounted at
`/workspace` (should show a `*.runpod.net:/runpodfs/networkvolumes/...`
NFS-style mount) rather than just being a directory on the ephemeral
container disk — worth checking after every redeploy, not assumed.

## Transferring files to the pod

```bash
scp -P <PORT> -i ~/.ssh/id_ed25519_runpod <local_file> root@<IP>:/workspace/<dest>
```

For directories (e.g. the `input/` folder with all 12 entries):
```bash
rsync -avz -e "ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod" \
  /Users/abhashshrestha/Downloads/MICA-Experiment/input/ \
  root@<IP>:/workspace/input/
```

Always put persistent/large data under `/workspace` (the Network
Volume), never the container's own `/` — anything outside `/workspace`
is lost if the pod is stopped/reset/terminated.

## Pulling results back

Use `sync_from_pod.sh` (in this same directory) rather than one-off
commands — it's safe to run repeatedly (rsync only moves what's new),
pulls `AF3_docked_models/`, `docking_logs/`, and the results CSV for
all 12 entries in one go. Update `POD_HOST`/`POD_PORT` in that script
first if the pod was redeployed since the last run.

```bash
./sync_from_pod.sh
```

## Installing Phenix (Linux x86-64, no Coot, no CUDA)

Download the "x86-64 [download command-line installer]" link from
Phenix's Linux downloads page (registration already active from the
original academic license request — no new wait needed). Transfer to
the pod, then run non-interactively:

Don't scp from the Mac — upload bandwidth was too slow (~150KB/s,
would've taken 5+ hours for the 3.73GB file). Instead, download
directly on the pod from phenix-online.org (datacenter-to-datacenter,
~110MB/s, took 32s). Requires HTTP Basic Auth credentials from the
original registration email (`User Name: download`, password from
that email — not the account login):

```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> \
  "cd /workspace && wget --user=download --password=<PASSWORD> \
   -O Phenix-2.2.1-6174-Linux-x86_64.sh \
   'https://www.phenix-online.org/download/phenix/release/send_octet_stream.cgi?version=2.2.1-6174&file=Phenix-2.2.1-6174-Linux-x86_64.sh'"

ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> \
  "chmod +x /workspace/Phenix-2.2.1-6174-Linux-x86_64.sh && \
   bash /workspace/Phenix-2.2.1-6174-Linux-x86_64.sh -b -p /workspace/phenix-2.2.1-6174"
```

`-b` = batch/non-interactive. **The prefix flag is `-p PREFIX`, not
`-prefix`** — this installer uses single-letter getopts-style flags
(confirmed via `-h`); `-prefix` gets misparsed as `-p` with argument
`refix` (the leftover text), silently installing to `/root/refix`
instead. Always verify with `-h` before assuming a flag name.
`-p /workspace/phenix-2.2.1-6174` installs under the persistent volume
rather than the ephemeral container disk, so a pod restart doesn't
mean reinstalling from scratch.

## Running the docking batch

```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> \
  "cd /workspace && nohup python3 dock_batch.py > dock_batch.log 2>&1 &"
```

Check progress:
```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> \
  "tail -30 /workspace/dock_batch.log; wc -l /workspace/docking_results.csv"
```

## Browsing the pod's storage directly

**Option 1 — plain SSH shell (no setup needed):**
```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP>
cd /workspace
ls
```
Real remote shell — `cd`/`ls`/`cat` etc. all work, just not "local."

**Option 2 — SSHFS, mounts it as a local-feeling folder** (not set up
yet on this Mac — `sshfs` not found, macFUSE not installed):
```bash
brew install macfuse sshfs
# then approve the kernel extension in System Settings > Privacy &
# Security (macOS blocks it by default, may need a reboot)
mkdir -p ~/runpod-workspace
sshfs -p <PORT> -o IdentityFile=~/.ssh/id_ed25519_runpod \
  root@<IP>:/workspace ~/runpod-workspace
# unmount when done: umount ~/runpod-workspace
```
Only worth the setup friction if you want Finder-style browsing or
want other local tools to treat it as a normal folder — plain SSH
already covers basic navigation with zero setup.

## After connecting — what to check once you're in a shell

```bash
ssh -p 34732 -i ~/.ssh/id_ed25519_runpod root@38.80.152.147
```
(Use `id_ed25519_runpod`, not the default `id_ed25519` RunPod's own
auto-generated command shows — that's not the key registered with
your account.)

Once connected, you're in a real remote shell. Useful things to check:

**Where everything lives:**
```bash
cd /workspace
ls
```

**Map download progress** (while `fetch_maps.sh` is running):
```bash
cat /workspace/fetch_maps.log          # DONE lines, one per finished map
ls /workspace/input/*/emd_*.map        # unzipped = finished
ls /workspace/input/*/emd_*.map.gz     # still downloading
```

**Phenix sanity check:**
```bash
source /workspace/phenix-2.2.1-6174/phenix_env.sh
phenix.dock_in_map --version
```

**Docking batch progress** (once `dock_batch.py` is running):
```bash
tail -30 /workspace/dock_batch.log           # live progress lines
wc -l /workspace/docking_results.csv         # rows = domains completed so far
tail -20 /workspace/docking_results.csv      # most recent results
```

**A specific entry's results:**
```bash
ls /workspace/input/<emdb_num>/AF3_docked_models/    # actual docked PDBs
cat /workspace/input/<emdb_num>/docking_logs/<domain_name>.log  # full Phenix log for one domain
```

**Disk/resource check:**
```bash
df -h /workspace      # persistent volume usage
nproc; free -h        # note: free -h often shows the shared HOST's totals, not just this pod's allocation — don't read too much into it
```

**Leave the shell:**
```bash
exit
```

## GPU pod (MICA inference + baselines) — current connection

**Current live values** (update every redeploy, same as the CPU pod):
```bash
ssh -p 22023 -i ~/.ssh/id_ed25519_runpod root@194.68.245.89
```
Pod: `dizzy_teal_kite`, RTX A6000, US region, volume
`A6000_elastic_quiet_blush_herring` (Global/Elastic Volume) mounted at
`/workspace`. Template: **"Runpod Pytorch 2.8.0"** (pre-installs
Python 3.12 + PyTorch 2.8.0+cu128 + CUDA — confirmed working via
`python3 -c 'import torch; print(torch.__version__, torch.cuda.is_available())'`).

## Deploying on a Global/Elastic Volume (region-independent fallback)

Used when the Network Volume's pinned datacenter has **zero GPU
capacity** (hit this hard — CA datacenter saturated for hours, every
popular GPU showed "Out of capacity"). Global Volume mounts to a pod
in *any* region, sidestepping the region-pinning problem entirely.

1. **Storage page → New volume → Global volume (BETA)**. Elastic
   (grows with data stored), `$0.09/GB stored per month + IOPS` vs.
   Network Volume's flat `$0.07/GB` — marginally pricier but no
   region lock. Name it, create — no data center selection needed.
2. On the **Deploy a Pod** screen, the Global Volume **will show in
   the storage dropdown** this time (unlike an earlier session
   attempt where it didn't appear — may have been a timing/UI issue,
   or needs the volume fully provisioned first). Select it explicitly,
   same as a Network Volume.
3. **Template trap**: whenever a volume is attached, RunPod
   **defaults the template selection to "Network storage file
   browser"** (`filebrowser/filebrowser:v2.63.5`) — a file-browsing
   utility image, not a compute environment (no Python/CUDA usable for
   real work). **Hit this twice before catching it.** Always click
   into **Select a template → "Runpod Pytorch"** explicitly and pick
   a CUDA-enabled PyTorch version — don't trust the pre-highlighted
   default.
4. Double-check the deploy summary shows the correct template
   (`runpod/pytorch:...`, not `filebrowser/filebrowser`), correct GPU,
   and correct volume name **before** clicking Deploy — confirmed via
   the pod's **Details** tab after deploy (Container → Image, and
   Volumes → should list your volume mounted at `/workspace`).

### Global Volume filesystem quirk — attribute preservation fails

Confirmed broken: any operation trying to `chmod`/`chown`/preserve
timestamps on files **inside `/workspace`** fails, even as root.
- `git clone` directly into `/workspace` fails:
  `chmod on /workspace/<repo>/.git/config.lock failed: Operation not
  permitted`. **Fix**: clone to the pod's local container disk
  instead (e.g. `/root/<repo>`) — ephemeral, but trivial to re-clone
  if the pod is ever terminated. Only point actual *data* paths at
  `/workspace`, not code.
- `rsync -a` (archive mode, the default in every example above)
  silently fails on this volume — transfers report success but
  **zero bytes actually land**, only empty directories. **Fix**: drop
  attribute preservation explicitly:
  ```bash
  rsync -rvz --no-perms --no-owner --no-group --no-times \
    -e "ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod" \
    <local_dir>/ root@<IP>:/workspace/<dest>/
  ```
- Plain writes work fine without any special flags (`echo "x" >
  /workspace/file`, `dd if=/dev/zero of=/workspace/file`) — it's
  specifically the explicit attribute-setting syscalls that fail, not
  writes in general.
- **`df -h /workspace` is not a reliable signal on this volume type**
  — it permanently reports `0 used / 1.0P avail` regardless of actual
  usage (confirmed by writing 50MB+ and re-checking). Verify real
  contents with `ls`/`find`, not `df`.

### MICA environment setup on this pod (what actually worked)

```bash
# Clone to LOCAL disk, not /workspace (see git chmod issue above)
cd /root && git clone https://github.com/jianlin-cheng/MICA

# Install deps at MODERN versions (not the 2021-era environment.yml
# pins) — validated strategy from the earlier Colab sanity check.
# --break-system-packages needed: this image's Python is PEP
# 668-protected (externally-managed-environment).
pip install --break-system-packages --ignore-installed blinker -q \
  biopython numpy pandas scipy freesasa psutil atom3d mrcfile tqdm \
  scikit-image networkx einops rotary-embedding-torch natsort open3d
# ^ --ignore-installed blinker works around a Debian-packaged blinker
#   with no RECORD file that pip can't uninstall cleanly.
# ^ wandb deliberately omitted — training-only logging dep, not
#   needed for inference, and was one trigger of the blinker conflict.

# The above silently upgrades torch to a newer version (seen: 2.14.1),
# breaking the pod's pre-installed CUDA-matched build. Reinstall the
# correct one explicitly, AFTER the other installs:
pip install --break-system-packages -q torch==2.8.0+cu128 \
  --index-url https://download.pytorch.org/whl/cu128

# Two known-required exceptions to "use modern versions" (same as the
# Colab findings, Stage 9c in CLAUDE.md):
pip install --break-system-packages -q superpose3d==1.1.1
sed -i 's/self\.optimal_batch_size = self\._calculate_optimal_batch_size()/self.optimal_batch_size = 1/' \
  /root/MICA/utils/predict.py

# open3d needs system OpenGL/EGL libs not present on this minimal image:
apt-get update -qq && apt-get install -y -qq libegl1 libgl1 libgomp1

# PULCHRA's bundled Linux binary works as-is, no compile needed
# (modules/pulchra304/src/pulchra) — confirms Stage 9c's finding that
# only macOS needed a custom build.
```

### Running the sanity check (README's sample entry, validates the
whole environment before trusting it on real data)

Data comes from `input.tar` in the local project root (MICA's
Zenodo-hosted Quick Start sample, NOT bundled in the git repo) —
extract just the `15635` subset and upload to the volume:
```bash
mkdir -p /tmp/mica_sanity_extract
tar -xf /Users/abhashshrestha/Downloads/MICA-Experiment/input.tar \
  -C /tmp/mica_sanity_extract "input/15635"

ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> "mkdir -p /workspace/input/15635"
rsync -rvz --no-perms --no-owner --no-group --no-times \
  -e "ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod" \
  /tmp/mica_sanity_extract/input/15635/ root@<IP>:/workspace/input/15635/
```

Run (background, since this takes ~20-45 min depending on GPU):
```bash
ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod root@<IP> "
cd /root/MICA
mkdir -p /workspace/output
nohup python3 run.py \
  -m /workspace/input/15635/emd_15635.map \
  -f /workspace/input/15635/8at6.fasta \
  -a /workspace/input/15635/AF3_structures \
  --run_pulchra --pulchra_path=modules/pulchra304/src/pulchra \
  --resolution=3.7 --device cuda \
  -o /workspace/output \
  > /root/sanity_test.log 2>&1 &
"
```
Check progress: `tail -40 /root/sanity_test.log`. Reference baseline
(Colab T4): 2670.67s (44.5 min) total, with the real breakdown being
~48% GPU inference, ~40% CPU-bound Cα-sequence alignment, ~11%
preprocessing, PULCHRA itself negligible (<1s) — so more vCPU plausibly
helps the alignment phase specifically, not raw GPU speed.

## Notes / gotchas hit this session

- Pod IP/port **change on every redeploy** — always re-check the
  Connect tab, never assume a previously-used value is still valid.
- The auto-generated SSH command RunPod shows uses the *default* key
  path (`~/.ssh/id_ed25519`) even when a custom-named key was added —
  substitute `id_ed25519_runpod` manually every time.
- "Any region" for pod deployment is fine for compute, but **breaks
  Network Volume attachment** if the volume was created in a specific
  pinned region — always pin the pod's region to match the volume's
  region explicitly.
- Container disk and Network Volume can coincidentally show the same
  GB number in the dashboard — don't assume a size match means the
  volume is attached; verify via `mount`/`df -h` over SSH.

## Baseline methods (ModelAngelo, CryoAtom, EModelX) — environment setup

**Install conda to LOCAL container disk, never `/workspace`.** Even on
a working Network Volume (not the broken Global Volume), bulk
small-file writes (conda env creation, pip installing thousands of
package files) are genuinely slow over the network-backed mount —
confirmed via `ps -o etime,time` showing minutes of wall-clock elapsed
against seconds of actual CPU time (i.e. waiting on I/O, not
computing). Moving conda itself to `/root/miniconda3` fixed it
immediately:
```bash
wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p /root/miniconda3
/root/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
/root/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```
The `conda tos accept` step is required on newer conda versions before
`conda create`/`conda env create` will work at all — otherwise fails
with an opaque `EnvironmentNameNotFound` error that looks like
something else went wrong.

**ModelAngelo**:
```bash
export PATH=/root/miniconda3/bin:$PATH
cd /workspace/baselines/model-angelo
export TORCH_HOME=/workspace/baselines/model-angelo/torch_cache  # weights go on the volume (persistent), env stays local
nohup bash install_script.sh -w > install.log 2>&1 &
```
`-w` also downloads both weight bundles (`nucleotides`,
`nucleotides_no_seq`, ~3.6GB combined, checksummed automatically).

**CryoAtom**: weights are a plain `wget` (simplest of the three, no
manual download needed):
```bash
export PATH=/root/miniconda3/bin:$PATH
cd /workspace/baselines/CryoAtom
nohup bash install.sh > install.log 2>&1 &
```

**EModelX**: its `.yml` pins the same 2021-era stack MICA's does
(Python 3.8.12, PyTorch 1.8.1) — skip conda entirely and reuse MICA's
"modern versions, don't fight the pins" approach instead:
```bash
pip install --break-system-packages --ignore-installed blinker -q \
  biopython pandas scipy atom3d mrcfile open3d superpose3d==1.1.1 tqdm argparse
# open3d silently upgrades torch again (same as MICA's setup) -- a
# plain reinstall may not actually take effect; force it:
pip install --break-system-packages --force-reinstall --no-deps -q \
  torch==2.8.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```
Weights are **Google Drive only** (no direct-downloadable link, unlike
the other two) — `best_AA_model.ckpt` / `best_BB_model.ckpt` /
`best_CA_model.ckpt`, ~423MB each, go in `EModelX/models/`. Needs a
manual browser download by the user, then upload:
```bash
rsync -avz --no-perms --no-owner --no-group --no-times \
  -e "ssh -p <PORT> -i ~/.ssh/id_ed25519_runpod" \
  <local_download_dir>/ root@<IP>:/workspace/baselines/EModelX/models/
```
`--run_phenix` is **optional** for EModelX(+AF) (confirmed via
README) — only needed for an extra post-processing refinement pass,
not for the core modeling. The minimal working command doesn't need
Phenix at all: `--protocol=temp_flex --download_afdb
--afdb_allow_seq_id 0.6`.

## Checking if a background process is genuinely stuck vs. just slow

`tail`-ing a log isn't reliable for tqdm-style progress bars (they use
`\r`, not newlines, so line-based `tail` can show a stale-looking
single line even while real progress is happening). Use byte-based
reads instead: `tail -c 2000 logfile`. To tell a genuine stall from
slow-but-real progress, don't trust the log at all — check the actual
process's CPU time against wall-clock elapsed:
```bash
ps -p <PID> -o etime,time
```
If `etime` (wall clock) is climbing much faster than `time` (actual
CPU time used), the process is waiting on I/O/network, not frozen —
give it more time rather than killing it. If `time` stays flat across
repeated checks with no increase at all, it's genuinely stuck.
