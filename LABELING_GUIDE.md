# Audit-Set Labeling Guide

Rules for filling in the `label` column in `data/audit_set.csv`. The point of
this set is to be a more trustworthy signal than the lifecycle heuristics
themselves -- that only holds if the labels are applied consistently, not by
gut feel that shifts row to row.

## The three labels

**`real`** -- you'd bet this posting reflects an active, genuine hiring
intent. Evidence to look for:
- Specific, non-templated description: named team, concrete responsibilities,
  a tech stack or tools actually named, not just generic corporate language
- Posted once, not showing up as a likely repost of something recently removed
- Still reasonably fresh (posted or updated in the last ~30 days) OR removed
  within a normal hiring-cycle window (roughly 2-8 weeks from first_seen_date
  to removed_date)
- Company is at a stage/size where the role makes obvious sense (e.g. a
  Series A startup posting one specific backend role, not eleven identical
  "Software Engineer" postings across every team)

**`likely_ghost`** -- you'd bet this posting is NOT tied to an active req.
Evidence to look for:
- Open far longer than a normal hiring cycle would justify (use
  `first_seen_date` vs. today, or vs. `removed_date` if closed) -- as a
  starting reference, 60+ days open with no removal is a flag, not a rule
- Vague, boilerplate description that could be pasted onto almost any role
  at almost any company (generic "fast-paced environment," no specifics on
  team/stack/responsibilities)
- Shows up in `repost_links` (check `data/postings.db`'s `repost_links`
  table for this posting's `source`/`source_job_id`) -- a detected repost
  pair is a strong signal, though not an automatic label; use judgment on
  whether it reads like a genuinely re-opened req (team grew, first hire
  didn't work out) vs. a listing kept alive for pipeline-building
- Identical or near-identical postings open simultaneously at the same
  company for the same title (evergreen/pipeline postings)

**`unsure`** -- genuinely ambiguous, or you don't have enough to go on from
the description/lifecycle data alone (e.g. posting is still open and it's
too early to tell, or the description is too thin to judge either way).
Use this rather than guessing -- a forced real/likely_ghost label you don't
actually believe is worse than an honest `unsure` for evaluation purposes.

## Process notes

- Judge each posting independently. Don't let one company's postings bias
  your read of another's, even if you're labeling several from the same
  company in a row.
- The `description_excerpt` column is truncated to 500 characters -- if you
  need the full text or want to see the live listing, `url` is the original
  posting.
- `removed_date` blank means still active as of the last scrape -- for a
  still-open posting, judge on how long it's been open and the description
  content, not on how it eventually resolves (you won't know that yet for
  most rows early on).
- Use `notes` for anything that informed a borderline call -- useful later
  for auditing your own labels or explaining specific decisions.
- It's fine to leave rows unlabeled and come back later -- re-running
  `python -m scraper.build_audit_set` never touches rows you've already
  labeled, so there's no penalty for labeling in batches over time.
