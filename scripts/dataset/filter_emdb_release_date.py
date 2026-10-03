"""
Third filter stage: drop entries whose linked EMDB map was actually made
public before 2026, even though the PDB coordinate entry's own
initial_release_date falls in 2026 (re-refinements, revised depositions,
and stale/incorrect EMDB cross-references all produce this mismatch --
see EMD-7396 linked to 9Z9Y, map_release 2019-01-30, whose EMDB title
doesn't even match the PDB entry's title).

RCSB's Data/GraphQL API doesn't carry the EMDB map's own release date --
only EMDB itself does, via https://www.ebi.ac.uk/emdb/api/entry/{num}
(admin.key_dates.map_release). No batch endpoint, so this is per-ID REST
calls, parallelized with a thread pool to keep wall time reasonable.

A row can have >1 semicolon-separated EMDB ID (rare, ~3 cases upstream).
ALL linked maps must have map_release in the 2026 window for the row to
survive -- if any one of them is stale, the pairing is suspect enough to
drop rather than guess which map is "the real one".
"""

import csv
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

INPUT_CSV = "../../data/pool/rcsb_2026_pure_protein.csv"
OUTPUT_CSV = "../../data/pool/rcsb_2026_final_candidates.csv"
CACHE_CSV = "../../data/pool/emdb_id_map_release_date.csv"

DATE_FROM = "2026-01-01"
DATE_TO = "2026-09-26"
MAX_WORKERS = 10

EMDB_URL = "https://www.ebi.ac.uk/emdb/api/entry/{}"


def fetch_map_release(emdb_id, retries=3):
    """emdb_id like 'EMD-75023' -> (emdb_id, 'YYYY-MM-DD' or None)."""
    num = emdb_id.split("-")[1]
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(EMDB_URL.format(num), timeout=30) as resp:
                data = json.loads(resp.read())
            release = data.get("admin", {}).get("key_dates", {}).get("map_release")
            return emdb_id, release.split("T")[0] if release else None
        except Exception as e:
            last_err = e
    print(f"  ERROR fetching {emdb_id} after {retries} attempts: {last_err}")
    return emdb_id, None


def main():
    with open(INPUT_CSV, newline="") as f:
        rows = list(csv.DictReader(f))

    all_emdb_ids = sorted({
        e for r in rows for e in r["emdb_ids"].split(";") if e
    })
    print(f"Fetching map_release date for {len(all_emdb_ids)} unique EMDB entries...")

    release_date = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_map_release, e) for e in all_emdb_ids]
        for i, fut in enumerate(as_completed(futures), 1):
            emdb_id, release = fut.result()
            release_date[emdb_id] = release
            if i % 200 == 0:
                print(f"  ...{i}/{len(all_emdb_ids)}")

    with open(CACHE_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["emdb_id", "map_release"])
        for e, d in sorted(release_date.items()):
            w.writerow([e, d or ""])

    fieldnames = list(rows[0].keys()) + ["emdb_map_release_dates", "emdb_map_release_ok"]
    kept, dropped = [], []

    for row in rows:
        ids = [e for e in row["emdb_ids"].split(";") if e]
        dates = [release_date.get(e) for e in ids]
        row["emdb_map_release_dates"] = ";".join(d or "UNKNOWN" for d in dates)

        ok = all(d is not None and DATE_FROM <= d <= DATE_TO for d in dates) and len(dates) > 0
        row["emdb_map_release_ok"] = ok
        (kept if ok else dropped).append(row)

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    print(f"\n{len(kept)} kept / {len(dropped)} dropped ({len(rows)} total input rows).")
    print(f"Saved to {OUTPUT_CSV}")
    if dropped:
        print("\nSample of dropped (stale map, PDB date was a false positive):")
        for r in dropped[:10]:
            print(f"  {r['pdb_id']}  emdb={r['emdb_ids']}  map_release={r['emdb_map_release_dates']}  pdb_release={r['release_date'][:10]}")


if __name__ == "__main__":
    main()
