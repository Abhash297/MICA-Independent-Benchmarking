"""
Query RCSB PDB for cryo-EM protein structures released in 2026,
then pull resolution + linked EMDB IDs from the Data API for each hit.

Docs:
  Search API: https://search.rcsb.org/#search-api
  Data API:   https://data.rcsb.org/#data-api

Two-step process, because the Search API only returns IDs + minimal
metadata; resolution, release date, and EMDB cross-references have to
be pulled separately from the Data API per entry.
"""

import requests
import csv
import time

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
DATA_URL = "https://data.rcsb.org/rest/v1/core/entry/{}"

# ---- adjust these to taste ----
DATE_FROM = "2026-01-01T00:00:00Z"
DATE_TO = "2026-09-26T23:59:59Z"
RES_MIN = 1.5
RES_MAX = 4.0
OUTPUT_CSV = "../../data/pool/rcsb_2026_cryoem_candidates.csv"
# --------------------------------


def search_pdb_ids():
    query = {
        "query": {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "exptl.method",
                        "operator": "exact_match",
                        "value": "ELECTRON MICROSCOPY",
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_accession_info.initial_release_date",
                        "operator": "range",
                        "value": {
                            "from": DATE_FROM,
                            "to": DATE_TO,
                            "include_lower": True,
                            "include_upper": True,
                        },
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entry_info.resolution_combined",
                        "operator": "range",
                        "value": {
                            "from": RES_MIN,
                            "to": RES_MAX,
                            "include_lower": True,
                            "include_upper": True,
                        },
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "entity_poly.rcsb_entity_polymer_type",
                        "operator": "exact_match",
                        "value": "Protein",
                    },
                },
            ],
        },
        "return_type": "entry",
        "request_options": {"return_all_hits": True},
    }

    resp = requests.post(SEARCH_URL, json=query, timeout=30)
    if resp.status_code == 204:
        print("No hits for this query.")
        return []
    resp.raise_for_status()
    data = resp.json()
    return [hit["identifier"] for hit in data.get("result_set", [])]


def fetch_entry_details(pdb_id):
    resp = requests.get(DATA_URL.format(pdb_id), timeout=30)
    if resp.status_code != 200:
        return None
    entry = resp.json()

    emdb_ids = entry.get("rcsb_entry_container_identifiers", {}).get("emdb_ids", [])
    resolution = entry.get("rcsb_entry_info", {}).get("resolution_combined", [None])
    release_date = entry.get("rcsb_accession_info", {}).get("initial_release_date")
    title = entry.get("struct", {}).get("title", "")

    return {
        "pdb_id": pdb_id,
        "emdb_ids": ";".join(emdb_ids) if emdb_ids else "",
        "resolution": resolution[0] if resolution else "",
        "release_date": release_date,
        "title": title,
    }


def main():
    print("Searching RCSB PDB...")
    ids = search_pdb_ids()
    print(f"Found {len(ids)} candidate entries. Fetching details...")

    rows = []
    for i, pdb_id in enumerate(ids):
        details = fetch_entry_details(pdb_id)
        if details and details["emdb_ids"]:  # only keep entries with a linked map
            rows.append(details)
        if (i + 1) % 20 == 0:
            print(f"  ...{i + 1}/{len(ids)} processed")
        time.sleep(0.1)  # be polite to the API

    print(f"{len(rows)} entries have a linked EMDB map.")

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["pdb_id", "emdb_ids", "resolution", "release_date", "title"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
