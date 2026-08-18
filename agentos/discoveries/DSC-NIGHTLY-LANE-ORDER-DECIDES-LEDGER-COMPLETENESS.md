---
key: NIGHTLY-LANE-ORDER-DECIDES-LEDGER-COMPLETENESS
claim: >
  When a forward ledger is advanced by one nightly lane and its INPUT is
  advanced by a different one, a lane-ordering race makes the ledger look
  incomplete until the next projection run — and the resulting CI red is
  transient, not a defect. Measured 2026-08-18 on
  data/government_revenue/candidate_ledger.jsonl: the govrev projection
  committed at 04:18:10Z (5214d0b20a17, candidate_projection_status
  `status: ok`, ledger_line_count 56) and `data: daily collection 2026-08-18`
  committed at 04:23:15Z (93ab221b81dd) — FIVE MINUTES LATER. The new award
  records produced 26 first-seen candidates with neither a ledger issuance nor
  a reviewed suppression, reddening
  `test_reviewed_historical_cohort_rebuilds_byte_exact_and_nothing_escapes_review`
  and, through ci-gate, every armed PR in the fleet.
falsifier: >
  `git log origin/main --format='%h|%cI|%s' -25 | grep -iE "collection|govrev"`
  — if the `data: daily collection` commit PRECEDES the govrev projection
  commit and the test still reports unaccounted first-seen candidates, the race
  is not the cause and a real ledger defect should be sought. Equally, if the
  red survives a subsequent govrev projection run that postdates the collection,
  it is not transient.
so_what: >
  Do NOT hand-issue the missing ledger rows to make CI green. `nightly is the
  sole advancer of forward ledgers` (CLAUDE.md), and the failing test's own
  docstring records that auto-covering such rows once stamped `reviewed_at`
  values no human reviewed against rows that were never suppression-eligible.
  Issuing them forward is the correct disposition AND the one the nightly takes
  by itself on its next run, so the repair for this red is to WAIT for that run
  — the opposite of the sealed-pin red it superficially resembles
  ([[ADJUSTED-PRICE-PLANES-RESTATE-HISTORY]]), which never self-heals and had to
  be fixed in code. Two reds on one main baseline can need opposite treatments;
  classify each by asking whether the next scheduled run changes the answer.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  Reproduced on a full checkout: the 19-file `award-event spine, candidates,
  entity + workspace contracts` CI step gave 1 failed / 352 passed, the single
  failure listing 26 `grc1-` candidate ids as unaccounted. Read
  data/government_revenue/candidate_projection_status.json (generated_at
  2026-08-18T04:17:31Z, known_at 02:42:13Z, source_health.status `ok`) and
  compared committer timestamps of 5214d0b20a17 and 93ab221b81dd.
scope:
  - macro
  - data/government_revenue/candidate_ledger.jsonl
  - tests/test_government_revenue_candidates.py
confidence: verified
---

Found while repairing the 2026-08-18 fleet-wide main red, which carried two
failing jobs that looked like one problem. They were not. The atlas red was a
structural defect that re-fires every night and needed a code fix; this one is a
five-minute scheduling overlap that the next govrev run clears on its own.

Deliberately NOT fixed in the accompanying repair PR. The one-PR-per-main-red
rule exists so two partial heals cannot deadlock a shared check — it does not
oblige a session to hand-edit an append-only ledger whose sole legitimate
advancer is the nightly.
