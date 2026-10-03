#!/usr/bin/env python3
"""
Combine each entry's AF3_docked_models/*.pdb into the single
<entry>_af3_docked.pdb file run.py actually looks for (confirmed via
reading dock_in_map.py / modeler.py -- run.py never reads the
per-domain AF3_docked_models files directly, only this combined file).

Reuses MICA's own PhenixDockingProcessor.combine_af3_docked_results(),
which is pure Biopython -- no Phenix binary needed, safe to call here
even though this GPU pod has no Phenix install.
"""
import sys
sys.path.insert(0, "/workspace/MICA")
sys.path.insert(0, "/workspace/MICA/utils")
from utils.dock_in_map import PhenixDockingProcessor

# __init__ validates a real Phenix install via test_phenix_environment() --
# not needed for combine_af3_docked_results() (pure Biopython), and this
# GPU pod deliberately has no Phenix install. Bypass the check.
PhenixDockingProcessor.test_phenix_environment = lambda self: None

ENTRIES = ["62164", "64568", "65506", "67233", "70609", "71787",
           "71973", "75023", "76934", "79027", "64362", "73799"]

for emdb_num in ENTRIES:
    af3_results_path = f"/workspace/input/{emdb_num}/AF3_results"
    processor = PhenixDockingProcessor(
        phenix_command="unused",  # unused by combine_af3_docked_results
        AF3_results_path=af3_results_path,
        log_directory=f"/workspace/input/{emdb_num}/docking_logs",
        quiet=True,
    )
    result = processor.combine_af3_docked_results()
    print(f"{emdb_num}: {result}")
