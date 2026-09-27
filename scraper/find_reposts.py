"""
Entry point: python -m scraper.find_reposts

Reads every posting currently in data/postings.db, runs entity resolution
over it to find repost pairs (a removed posting reappearing at the same
company under a new id), and writes matches to the repost_links table.

Safe to re-run at any time -- matches are upserted by (old, new) pair, not
appended, so running this daily alongside the scraper (or ad hoc) just
re-scores existing pairs and finds any new ones as more lifecycle history
accumulates.
"""

from datetime import date

from scraper.db import fetch_all_postings, get_connection, record_repost_links
from scraper.entity_resolution import find_repost_candidates


def main():
    conn = get_connection()
    postings = fetch_all_postings(conn)
    print(f"Scanning {len(postings)} postings for repost pairs...")

    matches = find_repost_candidates(postings)
    print(f"Found {len(matches)} candidate repost pairs.")

    for m in matches:
        basis = "title+description" if m.used_description else "title only (no usable description)"
        print(
            f"  {m.company}: {m.old_source}/{m.old_source_job_id} -> "
            f"{m.new_source}/{m.new_source_job_id} "
            f"(title_sim={m.title_similarity:.2f}, "
            f"desc_sim={'n/a' if m.description_similarity is None else f'{m.description_similarity:.2f}'}, "
            f"gap={m.days_gap}d, basis={basis})"
        )

    record_repost_links(conn, matches, detected_date=date.today().isoformat())
    conn.close()
    print("Done. Matches written to the repost_links table.")


if __name__ == "__main__":
    main()
