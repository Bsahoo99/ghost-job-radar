"""
Entity resolution for repost detection.

The labeling heuristic "high repost frequency" needs an actual matching
algorithm, not a "looks similar" judgment call. A repost is: a posting
disappears (removed_date set), and a new posting shows up at the SAME
company shortly after with a near-identical title and (when available)
a near-identical description.

Four checks, all required for a match:
  1. Same company (case-insensitive, whitespace-normalized)
  2. Title similarity above TITLE_SIM_THRESHOLD -- via token-sort ratio,
     not a raw string diff, so "Senior Software Engineer" and "Software
     Engineer, Senior" still match despite reordered words.
  3. Description similarity above DESC_SIM_THRESHOLD -- via TF-IDF cosine
     similarity on the two descriptions, when both are available. The
     Greenhouse list endpoint often returns an empty description (see
     sources.py), so when either side has no usable description text,
     matching falls back to title similarity alone at a STRICTER
     threshold (MIN_TITLE_SIM_NO_DESC), since we're missing a signal.
  4. Reappearance within MAX_REPOST_GAP_DAYS of the removal -- a
     "repost" six months later is really just a new req.

No external fuzzy-matching library (e.g. rapidfuzz) is added as a
dependency for this -- difflib (stdlib) is enough for token-sort ratio,
and scikit-learn is already a planned dependency for the classifier
stage, so TfidfVectorizer + cosine_similarity don't add anything new.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

TITLE_SIM_THRESHOLD = 0.85
DESC_SIM_THRESHOLD = 0.75
MIN_TITLE_SIM_NO_DESC = 0.92
MAX_REPOST_GAP_DAYS = 45

# Descriptions shorter than this (after stripping HTML) are treated as
# "no usable description" rather than fed into TF-IDF, since a couple of
# boilerplate words produce a meaningless cosine similarity.
MIN_DESCRIPTION_CHARS = 40

_TAG_RE = re.compile(r"<[^>]+>")
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


@dataclass
class RepostMatch:
    old_source: str
    old_source_job_id: str
    new_source: str
    new_source_job_id: str
    company: str
    title_similarity: float
    description_similarity: Optional[float]
    days_gap: int
    used_description: bool


def _strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text or "")


def normalize_title(title: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    title = _strip_html(title).lower()
    title = _PUNCT_RE.sub(" ", title)
    title = _WS_RE.sub(" ", title).strip()
    return title


def _token_sort(text: str) -> str:
    return " ".join(sorted(text.split()))


def title_similarity(title_a: str, title_b: str) -> float:
    """Token-sort ratio: order-independent similarity in [0, 1].

    Sorting tokens before comparing means "Senior Backend Engineer" and
    "Backend Engineer, Senior" score identically to two titles that were
    already in the same order -- reworded/reordered reposts are common
    and a naive string diff would miss them.
    """
    a = _token_sort(normalize_title(title_a))
    b = _token_sort(normalize_title(title_b))
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def usable_description(text: Optional[str]) -> Optional[str]:
    """Return cleaned description text, or None if too short to trust."""
    if not text:
        return None
    cleaned = _WS_RE.sub(" ", _strip_html(text)).strip()
    if len(cleaned) < MIN_DESCRIPTION_CHARS:
        return None
    return cleaned


def description_similarity(desc_a: str, desc_b: str) -> float:
    """TF-IDF cosine similarity between two descriptions, in [0, 1].

    Fit per-pair rather than on a shared corpus vocabulary: this runs
    over many small candidate pairs, not one global comparison, so a
    per-pair vectorizer keeps each score self-contained and reproducible
    independent of what else has been scored so far.
    """
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform([desc_a, desc_b])
    return float(cosine_similarity(matrix[0], matrix[1])[0][0])


def _parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def is_probable_repost(old: dict, new: dict) -> Optional[RepostMatch]:
    """Check one (removed posting, later posting) pair.

    `old` and `new` are posting rows (dicts) with at least: company,
    title, description, source, source_job_id, removed_date (on old),
    first_seen_date (on new). Returns a RepostMatch if it clears every
    threshold, else None.
    """
    if not old.get("removed_date") or not new.get("first_seen_date"):
        return None

    old_company = normalize_title(old.get("company", ""))
    new_company = normalize_title(new.get("company", ""))
    if not old_company or old_company != new_company:
        return None

    days_gap = (_parse_date(new["first_seen_date"]) - _parse_date(old["removed_date"])).days
    if days_gap < 0 or days_gap > MAX_REPOST_GAP_DAYS:
        return None

    t_sim = title_similarity(old.get("title", ""), new.get("title", ""))

    old_desc = usable_description(old.get("description"))
    new_desc = usable_description(new.get("description"))

    if old_desc and new_desc:
        d_sim = description_similarity(old_desc, new_desc)
        if t_sim >= TITLE_SIM_THRESHOLD and d_sim >= DESC_SIM_THRESHOLD:
            return RepostMatch(
                old_source=old["source"],
                old_source_job_id=old["source_job_id"],
                new_source=new["source"],
                new_source_job_id=new["source_job_id"],
                company=old.get("company", ""),
                title_similarity=t_sim,
                description_similarity=d_sim,
                days_gap=days_gap,
                used_description=True,
            )
        return None

    # No usable description on one or both sides -- fall back to a
    # stricter title-only bar rather than silently skipping the pair.
    if t_sim >= MIN_TITLE_SIM_NO_DESC:
        return RepostMatch(
            old_source=old["source"],
            old_source_job_id=old["source_job_id"],
            new_source=new["source"],
            new_source_job_id=new["source_job_id"],
            company=old.get("company", ""),
            title_similarity=t_sim,
            description_similarity=None,
            days_gap=days_gap,
            used_description=False,
        )
    return None


def find_repost_candidates(postings: list[dict]) -> list[RepostMatch]:
    """Scan a full posting set for repost pairs.

    O(n^2) within each company's postings, which is fine at watchlist
    scale (dozens to low hundreds per company); if the watchlist grows
    substantially this should bucket by a cheap prefilter (e.g. first
    title token) before the pairwise check.
    """
    by_company: dict[str, list[dict]] = {}
    for p in postings:
        by_company.setdefault(normalize_title(p.get("company", "")), []).append(p)

    matches: list[RepostMatch] = []
    for company_postings in by_company.values():
        removed = [p for p in company_postings if p.get("removed_date")]
        for old in removed:
            for new in company_postings:
                if new is old:
                    continue
                if (new["source"], new["source_job_id"]) == (old["source"], old["source_job_id"]):
                    continue
                match = is_probable_repost(old, new)
                if match:
                    matches.append(match)
    return matches
