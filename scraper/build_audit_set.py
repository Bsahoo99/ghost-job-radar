"""
Builds/updates the manually-audited ground-truth set: python -m scraper.build_audit_set

Samples postings from data/postings.db into data/audit_set.csv, with empty
label/notes columns for Biswajeet to fill in by hand (real / likely_ghost /
unsure). This CSV -- not the heuristic labels -- is what precision/recall
gets reported against later (see the PRD's Success Criteria and Labeling &
Modeling sections), so it needs an actual person's judgment, not a
description word count.

Re-running this tool is safe and additive:
  - Postings already in audit_set.csv, and whatever label they've been
    given, are left untouched.
  - Only enough NEW postings are sampled to bring the total up to --target,
    so labeling work already done is never lost or redone.

Sampling is stratified by source and capped per company (--max-per-company)
so one heavily-populated company/source doesn't dominate the sample --
without this, day-one data (527 Greenhouse rows spread across 7 companies
vs 99 scattered RemoteOK rows) would produce an audit set that's mostly
two or three companies, which isn't a useful cross-section to evaluate against.
"""

import argparse
import csv
from datetime import date
from pathlib import Path
import random

from scraper.db import fetch_all_postings, get_connection
from scraper.entity_resolution import usable_description

AUDIT_SET_PATH = Path(__file__).parent.parent / "data" / "audit_set.csv"

FIELDNAMES = [
    "source", "source_job_id", "company", "title", "location", "url",
    "first_seen_date", "last_seen_date", "removed_date", "times_seen",
    "description_excerpt", "label", "notes", "sampled_date",
]

DESCRIPTION_EXCERPT_CHARS = 500


def _excerpt(description):
    cleaned = usable_description(description)
    if not cleaned:
        return ""
    return cleaned[:DESCRIPTION_EXCERPT_CHARS]


def load_existing(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def stratified_sample(candidates, target_count, max_per_company, seed):
    """Up to target_count postings, capped at max_per_company per
    (source, company), drawn proportionally across sources.
    """
    if target_count <= 0 or not candidates:
        return []

    rng = random.Random(seed)
    by_source = {}
    for p in candidates:
        by_source.setdefault(p["source"], []).append(p)
    for postings in by_source.values():
        rng.shuffle(postings)

    sources = list(by_source.keys())
    per_source_target = max(1, target_count // len(sources))

    selected = []
    company_counts = {}

    def take_from(postings, limit):
        taken = []
        for p in postings:
            if len(taken) >= limit:
                break
            key = (p["source"], (p.get("company") or "").lower())
            if company_counts.get(key, 0) >= max_per_company:
                continue
            taken.append(p)
            company_counts[key] = company_counts.get(key, 0) + 1
        return taken

    # First pass: each source gets its proportional share.
    for source, postings in by_source.items():
        selected.extend(take_from(postings, per_source_target))

    # Second pass: top up from whatever's left (any source), for cases
    # where a source couldn't hit its share alone (e.g. too few distinct
    # companies to satisfy the per-company cap).
    if len(selected) < target_count:
        selected_keys = {(p["source"], p["source_job_id"]) for p in selected}
        leftovers = [
            p for postings in by_source.values() for p in postings
            if (p["source"], p["source_job_id"]) not in selected_keys
        ]
        rng.shuffle(leftovers)
        selected.extend(take_from(leftovers, target_count - len(selected)))

    return selected[:target_count]


def build_new_rows(sampled_postings, sampled_date):
    rows = []
    for p in sampled_postings:
        rows.append({
            "source": p["source"],
            "source_job_id": p["source_job_id"],
            "company": p.get("company", ""),
            "title": p.get("title", ""),
            "location": p.get("location", ""),
            "url": p.get("url", ""),
            "first_seen_date": p.get("first_seen_date", ""),
            "last_seen_date": p.get("last_seen_date", ""),
            "removed_date": p.get("removed_date") or "",
            "times_seen": p.get("times_seen", ""),
            "description_excerpt": _excerpt(p.get("description")),
            "label": "",
            "notes": "",
            "sampled_date": sampled_date,
        })
    return rows


def write_audit_set(path, existing_rows, new_rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(new_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", type=int, default=180,
        help="Total audit-set size to build up to (default 180, within the PRD's 150-200 range)",
    )
    parser.add_argument(
        "--max-per-company", type=int, default=25,
        help="Cap per (source, company) so one company doesn't dominate the sample",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed, for a reproducible sample given the same underlying data",
    )
    args = parser.parse_args()

    existing_rows = load_existing(AUDIT_SET_PATH)
    existing_keys = {(r["source"], r["source_job_id"]) for r in existing_rows}
    print(f"{len(existing_rows)} postings already in the audit set (labels preserved).")

    remaining_target = max(0, args.target - len(existing_rows))
    if remaining_target == 0:
        print(f"Audit set already has {len(existing_rows)} >= target {args.target}. Nothing to add.")
        return

    conn = get_connection()
    all_postings = fetch_all_postings(conn)
    conn.close()

    candidates = [p for p in all_postings if (p["source"], p["source_job_id"]) not in existing_keys]
    print(f"{len(candidates)} candidate postings not yet in the audit set.")

    sample = stratified_sample(candidates, remaining_target, args.max_per_company, args.seed)
    print(f"Sampling {len(sample)} new postings (target was {remaining_target}).")

    new_rows = build_new_rows(sample, date.today().isoformat())
    write_audit_set(AUDIT_SET_PATH, existing_rows, new_rows)

    print(f"Wrote {len(existing_rows) + len(new_rows)} total rows to {AUDIT_SET_PATH}")
    print("Open it in Excel/Sheets/Numbers and fill in the 'label' column: real / likely_ghost / unsure.")


if __name__ == "__main__":
    main()
