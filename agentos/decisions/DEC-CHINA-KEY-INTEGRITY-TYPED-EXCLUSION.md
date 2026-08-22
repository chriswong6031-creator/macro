---
key: CHINA-KEY-INTEGRITY-TYPED-EXCLUSION
question: >
  How should collectors/china_filings.py and collectors/china_visits.py treat
  a malformed announcementId (missing/None, NaN-like, empty string, or a
  string that strips to empty) at their respective write boundaries, given
  that the two boundaries independently discovered the same silent-drop
  shape (DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP): china_filings'
  drop_duplicates(subset=["announcementId"]) collapses N rows sharing a
  falsy key into ONE with no counter, and china_visits' bare comprehension
  `[... for f in candidates if f.get("announcementId")]` drops a candidate
  with no typed exclusion, no counter, no health note?
answer: >
  Add a single, shared, PURE predicate — key_anomaly() — owned by
  collectors/china_filings.py (the natural-key owner) and imported by
  collectors/china_visits.py, never re-derived there. Both write boundaries
  partition rows on this predicate BEFORE any dedup/derivation and exclude
  malformed rows as a TYPED, COUNTED exclusion (never silently deduplicated,
  never appended keyless). china_filings additionally protects its ACCRUED
  store: a pre-existing malformed row already on disk is split off and
  written back VERBATIM, never subjected to the keyed dedup. china_visits
  additionally performs a mechanical identity check
  (`represented + typed_exclusions == eligible`) as an explicit `if` branch
  (not a bare `assert`, which `python -O` strips) and refuses to trust a
  derivation whose own arithmetic does not add up — writing nothing and
  degrading to `source_failure` instead. Both malformed-exclusion states
  reuse the EXISTING `upstream_degraded` health value; no fifth
  `_HEALTH_STATES` value is added.
rationale: >
  The natural key belongs to china_filings — it is the module that owns
  `_COLUMNS` and the CNInfo response shape, so the anomaly predicate lives
  there and china_visits imports it, guaranteeing the two boundaries can
  never silently diverge on what counts as malformed (a second, independently
  maintained predicate is exactly the kind of drift that produced the
  original hole: two call sites that LOOKED equivalent — `if
  f.get("announcementId")` vs `drop_duplicates(subset=[...])` — behaving
  differently on "" and NaN). A typed exclusion (not a silent drop, not a
  keyless append) preserves both product invariants this plane exists to
  serve: "no filing" must be a MEASURED null (so a real filing can never
  quietly become one), and the store must never grow unbounded from repeat
  malformed re-pulls of the same bad row (an appended-keyless row has no
  natural key to dedup against and would re-append every 3-day re-pull
  forever). Reusing `upstream_degraded` rather than minting a fifth health
  state is required by a single hard downstream fact:
  engine/china_intel_hub.py's `_visit_block()` diverts a no-rows read away
  from `measured_no_event` on the LITERAL status string `"upstream_degraded"`
  only — a new state would fall through that check and render as a clean
  measured absence, which is the exact silent conversion this whole repair
  exists to prevent, and the hub is explicitly out of scope for this repair
  (Sol's commission: "The repair is designed to need zero hub changes").
  The mechanical identity check as an explicit branch (not `assert`) matters
  because this repo runs collectors under conditions where `assert` can be
  stripped (`python -O`) and the branch would otherwise be silently swallowed
  by refresh()'s own outer `except Exception` — an assert failing inside a
  broad except is invisible, while an explicit branch with its own typed
  health write is not.
alternatives:
  - option: Mint a fallback/composite key from sec_code + title + date (or
      similar) for a malformed row, so it can still be tracked and deduped.
    why_not: >
      Forbidden by the commission as a new identity system. announcementId is
      the plane's ONLY natural key; a synthetic composite key is a second,
      unauditable identity plane layered under the first, and a later
      genuine CNInfo announcementId could collide with or duplicate a
      synthetic key's coverage with no way to reconcile the two.
  - option: Append the malformed row keyless (no dedup subset match) so it
      is at least visible in the store.
    why_not: >
      A keyless row cannot be deduplicated against itself on the next 3-day
      re-pull (the same malformed source row reappears in every subsequent
      fetch window until the upstream anomaly clears), so the store would
      grow by one new row per re-pull for the SAME underlying malformed
      filing — unbounded growth from a single upstream defect, silently.
  - option: Add a fifth `_HEALTH_STATES` value (e.g. "key_integrity_degraded")
      distinct from `upstream_degraded`.
    why_not: >
      engine/china_intel_hub.py's `_visit_block()` checks the LITERAL string
      `"upstream_degraded"` to divert a no-rows read away from
      `measured_no_event`. A new, unrecognized state falls through that
      check straight to the `measured_no_event` branch — rendering a
      degraded run as a clean, honest-looking absence, which is precisely
      the silent-conversion failure mode DSC:CHINA-VISITS-UNTYPED-
      ANNOUNCEMENT-ID-DROP records and this repair exists to close. The hub
      is explicitly out of scope for this commission, so the fix must work
      within the hub's existing vocabulary, not extend it.
  - option: Use a bare `assert represented + typed_exclusions == eligible`
      in china_visits' refresh() instead of an explicit `if` branch.
    why_not: >
      This repo's collectors run under conditions where `assert` can be
      stripped (`python -O`), and even when not stripped, an `AssertionError`
      raised inside refresh()'s own broad `except Exception` handler is
      caught and silently degraded to a generic `source_failure` with no
      distinguishing detail — indistinguishable from any other unexpected
      bug. An explicit `if` branch with its own named detail string is both
      un-strippable and self-documenting, and is the branch the mutation
      test in tests/test_china_visits_collector.py is written to kill.
evidence:
  - "collectors/china_filings.py: key_anomaly(), normalize_announcement_id(),
    partition_by_key_integrity(), write_filings() (P1-R2 rewrite)"
  - "collectors/china_visits.py: account_candidates(), refresh()'s mechanical
    identity check and fail-closed china_filings import (P1-R2 rewrite)"
  - "engine/china_intel_hub.py:372 `if status == \"upstream_degraded\":` —
    read, not edited, confirming the literal-string dependency"
  - "tests/test_china_filings_collector.py::TestKeyIntegrityMutationGuard,
    tests/test_china_visits_collector.py::TestAccountingMutationGuard —
    mutation guards proving the exclusion depends on the real predicate"
  - "agentos/discoveries/DSC-CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP.md —
    the originating finding, REPAIRED BY P1-R2 paragraph appended in this PR"
  - "Measured 2026-08-22 on origin/main:data/china_filings/filings.parquet:
    54,078 rows, 0 NaN/None, 0 empty-or-whitespace, 54,078 distinct keys —
    the path has fired ZERO times in production; this is a rare-branch
    repair proven by hostile fixtures, not by a naturally occurring
    malformed row"
affects: ["WS:CHINA-ALPHA-INTELLIGENCE", "collectors/china_filings.py",
          "collectors/china_visits.py"]
confidence: high
reversibility: easy
decided_by: session
decided_at: 2026-08-22
---

## Grounds

Commissioned by Sol (AI CEO) 2026-08-22 as P1-R2, a bounded repair scoped to
exactly the two files that own the write boundaries; `engine/china_intel_hub.py`
was read for its literal `"upstream_degraded"` string dependency but not
edited, and no new store, quarantine file, or identity system was created.

## What would reopen this

A future plane that needs to RECOVER a malformed row (rather than merely
exclude and count it) — e.g. an operator wants to see the raw excluded rows
to manually repair the source data — would need a genuinely new decision:
today `excluded_identities` (up to 5 per run, log/annotation only) is the
only trace of what was excluded; nothing persists a full excluded-row
ledger. If CNInfo ever starts producing a non-trivial rate of malformed
announcementIds in practice (this record was written when the path had
fired zero times ever), the zero-valued "rare-branch repair" framing above
would need re-examination, though the mechanism itself would not need to
change.
