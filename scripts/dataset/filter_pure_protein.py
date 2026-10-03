"""
Filter RCSB 2026 cryo-EM candidates down to pure-protein entries using the
structured rcsb_entry_info.polymer_composition field, instead of a
title-keyword heuristic (which misses spliceosomes, CRISPR-Cas effector
complexes, nucleosomes, snRNPs, etc. -- anything protein+NA that doesn't
happen to say "ribosome" in the title).

Values were live-verified this session via the RCSB GraphQL endpoint
(https://data.rcsb.org/graphql) against all 5163 candidates in
rcsb_2026_cryoem_candidates.csv. Full per-ID lookup is cached in
pdb_id_polymer_composition.csv, so this script just merges -- no network
calls needed. Breakdown found in the candidate set:

    1922  heteromeric protein         <- pure protein, keep
    1669  homomeric protein           <- pure protein, keep
    1089  protein/NA                  <- excludes ribosomes, spliceosomes,
                                          nucleosomes, CRISPR-Cas, etc.
     479  protein/oligosaccharide     <- glycoprotein; judgment call, see below
       4  protein/NA/oligosaccharide  <- has NA, drop

protein/oligosaccharide default = KEEP: glycans are branched sugar
decorations on a protein chain, not a competing macromolecule the way rRNA
is in a ribosome, and MICA/ModelAngelo/EModelX(+AF) ground-truth masks are
backbone/C-alpha/amino-acid only regardless. Flip INCLUDE_GLYCOPROTEINS to
False for a maximally strict pure-protein-only set.

Second filter: em_experiment.reconstruction_method. exptl.method ==
"ELECTRON MICROSCOPY" (used in the original RCSB query) is broader than
single-particle cryo-EM -- it also matches helical reconstruction and
subtomogram averaging, neither of which MICA/ModelAngelo/EModelX(+AF)/
CryoAtom were built or evaluated on (different box geometry / much lower
resolution). Live-verified breakdown within the 4070-entry pure-protein
pool, cached in pdb_id_reconstruction_method.csv:

    3752  SINGLE PARTICLE       <- keep
     312  HELICAL               <- drop, different box geometry
       6  SUBTOMOGRAM AVERAGING <- drop, cellular tomography, not single-particle
"""

import csv

CANDIDATES_CSV = "../../data/pool/rcsb_2026_cryoem_candidates.csv"
COMPOSITION_CSV = "../../data/pool/pdb_id_polymer_composition.csv"
RECON_METHOD_CSV = "../../data/pool/pdb_id_reconstruction_method.csv"
OUTPUT_CSV = "../../data/pool/rcsb_2026_pure_protein.csv"

INCLUDE_GLYCOPROTEINS = True

PURE_PROTEIN_VALUES = {"homomeric protein", "heteromeric protein"}
if INCLUDE_GLYCOPROTEINS:
    PURE_PROTEIN_VALUES.add("protein/oligosaccharide")

VALID_RECONSTRUCTION_METHODS = {"SINGLE PARTICLE"}


def main():
    with open(COMPOSITION_CSV, newline="") as f:
        composition = {r["pdb_id"]: r["polymer_composition"] for r in csv.DictReader(f)}

    with open(RECON_METHOD_CSV, newline="") as f:
        recon_method = {r["pdb_id"]: r["reconstruction_method"] for r in csv.DictReader(f)}

    with open(CANDIDATES_CSV, newline="") as f:
        rows = list(csv.DictReader(f))

    missing_comp = [r["pdb_id"] for r in rows if r["pdb_id"] not in composition]
    if missing_comp:
        print(f"WARNING: {len(missing_comp)} candidate IDs have no cached composition "
              f"(not in {COMPOSITION_CSV}), dropping them: {missing_comp[:10]}...")

    fieldnames = list(rows[0].keys()) + ["polymer_composition", "reconstruction_method"]
    kept, dropped = [], []

    for row in rows:
        comp = composition.get(row["pdb_id"], "UNKNOWN")
        row["polymer_composition"] = comp
        is_pure_protein = comp in PURE_PROTEIN_VALUES

        # reconstruction_method was only cached for entries already in the
        # pure-protein pool -- non-pure-protein rows never had it fetched,
        # which is fine since they're dropped by the composition filter anyway
        recon = recon_method.get(row["pdb_id"], "UNKNOWN") if is_pure_protein else "N/A"
        row["reconstruction_method"] = recon
        is_single_particle = recon in VALID_RECONSTRUCTION_METHODS

        (kept if (is_pure_protein and is_single_particle) else dropped).append(row)

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    print(f"{len(kept)} kept / {len(dropped)} dropped ({len(rows)} total candidates).")
    print(f"Saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
