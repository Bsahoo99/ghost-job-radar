"""
Feature engineering for the Ghost Signal Score classifier.

Every feature here is computed "as of" a given date (as_of_date, default
today) using ONLY information that would have been knowable at that point --
this is the leakage fix from the PRD: a posting's own removed_date IS the
outcome we'd eventually want to predict, so it is never used as an input
feature. Concretely:

  - Features are only computed for postings that are still OPEN as of
    as_of_date (removed_date is NULL, or later than as_of_date). A closed
    posting isn't a live candidate to score anyway.
  - "How long has this been open" uses as_of_date - first_seen_date, not
    a full lifespan that depends on knowing when (or whether) it closes.
  - The one feature that draws on OTHER postings' repost history --
    company_repost_rate -- deliberately excludes the posting being scored,
    so a posting is never scored using evidence of its own eventual repost.

This module produces the feature table; scraper/entity_resolution.py's
repost_links and scraper/db.py's postings table are the only inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from scraper.entity_resolution import normalize_title, usable_description

# Generic, could-be-anywhere phrases. A higher hit rate against this list is
# used as a (rough, heuristic) proxy for a boilerplate/templated description --
# not proof of anything on its own, just one signal among several.
BOILERPLATE_PHRASES = [
    "fast-paced environment",
    "fast paced environment",
    "wear many hats",
    "rockstar",
    "ninja",
    "self-starter",
    "team player",
    "competitive salary",
    "great benefits",
    "unlimited pto",
    "work hard play hard",
    "move fast and break things",
    "world-class",
    "best-in-class",
    "dynamic team",
    "passionate about",
    "we are looking for a",
    "join our team",
    "make an impact",
]

_WS_RE = re.compile(r"\s+")


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def is_open_as_of(posting: dict, as_of_date: date) -> bool:
    """True if this posting was active (not yet removed) as of as_of_date."""
    removed = _parse_date(posting.get("removed_date"))
    first_seen = _parse_date(posting.get("first_seen_date"))
    if first_seen is None or first_seen > as_of_date:
        return False  # didn't exist yet as of as_of_date
    return removed is None or removed > as_of_date


def days_open_so_far(posting: dict, as_of_date: date) -> int:
    first_seen = _parse_date(posting["first_seen_date"])
    return (as_of_date - first_seen).days


def description_vagueness_score(description: Optional[str]) -> Optional[float]:
    """Fraction of boilerplate phrases found, normalized by description length
    in (roughly) 50-word blocks. None if there's no usable description --
    distinct from 0.0 (a specific, non-boilerplate description), since
    "no description available" and "concrete description" are different
    situations that a model should be able to tell apart.
    """
    cleaned = usable_description(description)
    if cleaned is None:
        return None
    text = cleaned.lower()
    word_count = max(1, len(text.split()))
    hits = sum(text.count(phrase) for phrase in BOILERPLATE_PHRASES)
    blocks = max(1, word_count / 50)
    return min(1.0, hits / blocks)


def salary_disclosed(posting: dict) -> bool:
    return posting.get("salary_min") is not None or posting.get("salary_max") is not None


@dataclass
class CompanyContext:
    active_posting_count: int
    repost_rate: Optional[float]  # None if the company has no removed postings to compute a rate from


def compute_company_context(
    postings: list[dict], repost_links: list[dict], as_of_date: date
) -> dict[str, CompanyContext]:
    """Per-company context as of as_of_date, built from OTHER postings than
    the one being scored (that exclusion happens in build_feature_table,
    which passes each posting's own key through so it isn't double-counted
    in its own company's stats where that matters -- active_posting_count
    intentionally still includes the posting itself, since "how many reqs
    is this company running right now" is a fact about the company at that
    moment, not about this posting's own future).
    """
    by_company: dict[str, list[dict]] = {}
    for p in postings:
        by_company.setdefault(normalize_title(p.get("company", "")), []).append(p)

    # Repost pairs, keyed by company, using only pairs detected from
    # postings that were already removed as of as_of_date (so the rate
    # reflects history available at that point, not the future).
    reposts_by_company: dict[str, int] = {}
    removed_by_company: dict[str, int] = {}
    posting_by_key = {(p["source"], p["source_job_id"]): p for p in postings}

    for p in postings:
        removed = _parse_date(p.get("removed_date"))
        if removed is not None and removed <= as_of_date:
            company = normalize_title(p.get("company", ""))
            removed_by_company[company] = removed_by_company.get(company, 0) + 1

    for link in repost_links:
        old_key = (link["old_source"], link["old_source_job_id"])
        old_posting = posting_by_key.get(old_key)
        if old_posting is None:
            continue
        removed = _parse_date(old_posting.get("removed_date"))
        if removed is None or removed > as_of_date:
            continue  # this repost pair wouldn't have been knowable yet
        company = normalize_title(old_posting.get("company", ""))
        reposts_by_company[company] = reposts_by_company.get(company, 0) + 1

    context = {}
    for company, company_postings in by_company.items():
        active_count = sum(1 for p in company_postings if is_open_as_of(p, as_of_date))
        removed_count = removed_by_company.get(company, 0)
        repost_rate = (
            reposts_by_company.get(company, 0) / removed_count if removed_count > 0 else None
        )
        context[company] = CompanyContext(active_posting_count=active_count, repost_rate=repost_rate)
    return context


def compute_features(posting: dict, company_context: CompanyContext, as_of_date: date) -> dict:
    """Feature vector for one currently-open posting."""
    return {
        "source": posting["source"],
        "source_job_id": posting["source_job_id"],
        "company": posting.get("company", ""),
        "as_of_date": as_of_date.isoformat(),
        "days_open_so_far": days_open_so_far(posting, as_of_date),
        "times_seen_so_far": posting.get("times_seen", 0),
        "description_length_chars": len(usable_description(posting.get("description")) or ""),
        "description_vagueness_score": description_vagueness_score(posting.get("description")),
        "salary_disclosed": salary_disclosed(posting),
        "company_active_posting_count": company_context.active_posting_count,
        "company_repost_rate": company_context.repost_rate,
    }


def build_feature_table(postings: list[dict], repost_links: list[dict], as_of_date: date) -> list[dict]:
    """Feature rows for every posting that was open as of as_of_date."""
    company_context = compute_company_context(postings, repost_links, as_of_date)
    rows = []
    for p in postings:
        if not is_open_as_of(p, as_of_date):
            continue
        company = normalize_title(p.get("company", ""))
        context = company_context.get(company, CompanyContext(active_posting_count=1, repost_rate=None))
        rows.append(compute_features(p, context, as_of_date))
    return rows
