#!/bin/bash
# Pulls newly-completed docking outputs + logs + results CSV from the
# RunPod instance back to this Mac. Safe to run repeatedly -- rsync
# only transfers what's new/changed each time, so it can be called
# every few minutes during a batch run without real cost.
#
# Fill in POD_HOST / POD_PORT / POD_KEY once the pod is deployed.
# Run from the repo root.

set -euo pipefail

POD_HOST="root@<POD_IP>"
POD_PORT="<POD_PORT>"
POD_KEY="$HOME/.ssh/id_ed25519_runpod"

LOCAL_ROOT="./input"
REMOTE_ROOT="/workspace/input"

SSH_OPTS=(-p "$POD_PORT" -i "$POD_KEY" -o StrictHostKeyChecking=accept-new)

echo "=== Syncing AF3_docked_models/ and docking_logs/ for all entries ==="
for emdb_dir in 79027 67233 73799 64362 75023 76934 70609 71973 64568 62164 71787 65506; do
  rsync -avz -e "ssh ${SSH_OPTS[*]}" \
    "${POD_HOST}:${REMOTE_ROOT}/${emdb_dir}/AF3_docked_models/" \
    "${LOCAL_ROOT}/${emdb_dir}/AF3_docked_models/" 2>&1 | grep -v "^$" || true
  rsync -avz -e "ssh ${SSH_OPTS[*]}" \
    "${POD_HOST}:${REMOTE_ROOT}/${emdb_dir}/docking_logs/" \
    "${LOCAL_ROOT}/${emdb_dir}/docking_logs/" 2>&1 | grep -v "^$" || true
done

echo "=== Syncing results CSV ==="
rsync -avz -e "ssh ${SSH_OPTS[*]}" \
  "${POD_HOST}:/workspace/docking_results.csv" \
  "./docking_results.csv" 2>&1 || true

echo "=== Done. Current tally: ==="
if [ -f "./docking_results.csv" ]; then
  tail -n +2 "./docking_results.csv" | \
    awk -F',' '{print $3}' | sort | uniq -c | sort -rn
fi
