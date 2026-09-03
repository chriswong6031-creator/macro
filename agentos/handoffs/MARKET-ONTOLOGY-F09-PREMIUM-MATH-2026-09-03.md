---
workstream: "WS:MARKET-OS"
session: claude/f09-premium-math-v1-20260903
model: opus
ended_because: blocked
mission: >
  F09-1 — eliminate ungrounded risk-arbitrage math in Special Situations, including the live
  LGMK 42,790.2% annualized regression. Add immutable EDGAR source-byte/evidence-locator term
  observations with amendment lineage, deterministic fixed-cash-only eligibility, separately
  named stated / filing-reference / live-spread / annualized numbers, currency-session-freshness
  -basis enforcement, and ONE canonical pure reducer consumed by every Special Situations and
  Neural Web consumer. Operation marketontology-f09-premium-math-v1-20260902-sol-001,
  carrier macro#6785, Slack root C0BSBM78V1N/1788407688.753659.
state_before: >
  data/special_situations/context/latest.json (special_sits_context.v1, asof=2026-09-01) led
  risk_arb_top with LGMK gross_spread_pct=64.57 / annualized_pct=42790.2 / days_to_close=30,
  carrying ticker, company and three numbers and nothing else. engine/special_arb.py resolved a
  YYYY-MM close to month end and annualized off it; engine/special_situations.py priced off
  panel[col].dropna().iloc[-1] with a fixed 30-ROW unaffected lookback; mastermind_emit filtered
  cash-only while special_sits_intel sorted `annualized_pct or 0`. A 0.6-1.8 plausibility band
  and a 1095-day cap already existed in the math owner and PASSED the LGMK row. Publication-path
  test coverage was one assertion: `assert "risk_arb_top" in result`.
changed:
  - path: engine/special_arb.py
    what: >
      Rewritten as the one pure owner: deal_term_observation.v1 factory with deterministic
      observation_id, deterministic span extraction with a negative lexicon, current-term
      compiler with accession/amendment precedence, typed price inputs, reduce_cash_deal, and
      select_ordered_context/context_row. arb_metrics and parse_terms_text DELETED; the month-end
      substitution, _PLAUS_LO/_PLAUS_HI band and _DAYS_CAP removed. parse_terms retained but
      demoted to _candidate_only.
  - path: engine/special_situations.py
    what: >
      _closes_frames/_panel_sources/_calendar_index/_price_inputs/_load_observations added;
      _enrich_arb now attaches a typed block to EVERY arb-category situation (including degraded
      ones) from ledger observations plus real session/basis/artifact receipts; _price_before
      deleted; mastermind_emit consumes the shared ordered projection and emits risk_arb_census.
  - path: engine/special_sits_intel.py
    what: >
      build_context_feed consumes the same select_ordered_context owner, emits risk_arb_census,
      and counts with_arb as VERIFIED rather than "has a block".
  - path: collectors/special_situations.py
    what: >
      New enrich_deal_terms() lane appends byte-bound observations to
      data/special_situations/observations/observations.jsonl, reading ONLY bodies the existing
      doc_cache already holds. Idempotent via observation_id.
  - path: contracts/special_situations_deal_term_observation.schema.json
    what: "The published observation contract (new; sibling shape to the capital-structure one)."
  - path: tests/fixtures/special_situations/f09/corpus.json
    what: "19-case rights-safe precision corpus + README stating its authored-not-sampled limits."
  - path: tests/test_special_arb.py
    what: "Rewritten as 39 hostile mutants incl. the precision gate and the no-clamp guard."
  - path: tests/test_special_situations.py
    what: "5 engine-level F09 integration tests (session receipts, staleness, no invented day, no-ledger degradation, consumer divergence)."
  - path: tests/test_special_sits_intel.py
    what: "4 context-feed consumer tests incl. the LGMK regression shape."
  - path: research/F09_PREMIUM_MATH_PRECISION_REPORT_2026-09-03.md
    what: "Precision/coverage report with the corpus limits stated explicitly."
verified:
  - claim: "All 39 new special_arb tests fail against origin/main's module — the capability did not exist."
    command: "git checkout origin/main -- engine/special_arb.py engine/special_situations.py engine/special_sits_intel.py && python3 -m pytest tests/test_special_arb.py -q"
    result: "37 failed (pre-contract-test count); after the two contract tests were added the file is 39 tests"
  - claim: "The pre-change math published 654.3% annualized with zero provenance keys and invented a 90-day close from a YYYY-MM window."
    command: "python3 -c \"from engine import special_arb as old; old.days_to_close('2026-11', date(2026,9,1)); old.arb_metrics(25.0, 15.19, expected_close='2026-11', asof=date(2026,9,1))\" (on origin/main files)"
    result: "days_to_close=90; {'gross_spread_pct': 64.58, 'days_to_close': 90, 'annualized_pct': 654.3}; provenance keys present: []"
  - claim: "The three owned suites are green on head d93092705fdc."
    command: "python3 -m pytest tests/test_special_arb.py tests/test_special_situations.py tests/test_special_sits_intel.py -q"
    result: "117 passed"
  - claim: "Zero false precise numeric publications over the 19-case corpus; 8 correct publications, 8 correct declines, 0 recall misses."
    command: "python3 - <<'PY' (corpus walk through extract_term_observations + compile_current_terms, see research report §2)"
    result: "true publish=8 correct-decline=8 recall-miss=0 FALSE PUBLICATIONS=0"
  - claim: "No regression in any suite that touches these modules — the failure set is identical on both sides."
    command: "python3 -m pytest $(grep -rl 'special_arb|special_situations|special_sits' tests/*.py) -q, run once with origin/main's four files checked out and once with the branch's"
    result: "45 failed / 1794 passed / 19 skipped on BOTH; all 45 need data/ or site/ and are sparse-worktree artifacts"
  - claim: "Every corpus observation validates against the committed JSON Schema, and a model-authored candidate term cannot."
    command: "python3 -m pytest tests/test_special_arb.py -k contract -q"
    result: "2 passed"
  - claim: "PR #6793 is in a lawful hold state."
    command: "gh pr view 6793 --json isDraft,autoMergeRequest,labels"
    result: "draft=true, autoMergeRequest=null, labels=[]"
unverified:
  - claim: "Real-world extraction recall against live EDGAR filings."
    what_would_verify: >
      One natural authoritative daily cycle after macro#6783 restores the macstudio route:
      compare enrich_deal_terms() observation counts against the arb-category event count and
      read the degraded census. The corpus is authored, so its 8/8 recall says nothing about EDGAR.
  - claim: "That the observation ledger writes correctly under a real build."
    what_would_verify: "Inspect data/special_situations/observations/observations.jsonl after a natural daily run; it has only ever been written in tmp dirs by tests."
  - claim: "That the five Neural Web consumers surface the richer rows correctly end to end."
    what_would_verify: >
      They slice risk_arb_top rows through unchanged (mastermind_context.py:1320, world_state.py:2254,
      ask_brain.py:1928, brief_context.py:920, cortex.py:2455 is prose only) — that is a code read,
      not a live observation. Verify on the same natural run.
  - claim: "That the real LGMK row is grounded rather than excluded."
    what_would_verify: "The natural run's typed state for LGMK. Only the SHAPE is pinned by tests today."
unresolved:
  - "Production proof is gated behind macro#6783 (Mac Studio daily-runner disk-admission floor). Capability is BUILT_NOT_PROVEN / PRODUCTION_INERT."
  - "enrich_deal_terms() is not yet called by any scheduled lane — wiring it into the build sequence touches scripts/ or workflow paths that were OUTSIDE the frozen path set and require a Sol path-boundary ruling first."
  - "Exact-head independent data/provenance/financial-method review not yet obtained."
next_actions:
  - "Obtain exact-head independent review of PR #6793 @ d93092705fdc; repair only on the same carrier."
  - "Return RESULT / HOLD-FOR-SOL on C0BSBM78V1N/1788407688.753659 and wait for Sol acceptance. Do NOT self-merge, mark Ready, or arm merge-on-green."
  - "Ask Sol for a path-boundary ruling on calling enrich_deal_terms() from the existing build sequence — it is the one wire still missing between the collector lane and _enrich_arb."
  - "After #6783 restores the daily route, observe ONE natural cycle (never a dispatch) and check: observation counts, VERIFIED vs degraded census, every ordered row's receipts, the real LGMK disposition, and all five Neural Web consumers."
do_not_redo:
  - "Do NOT add a magnitude clamp, band, cap or ticker exception. The band already existed and ADMITTED the 42,790.2% row (DSC:ARB-PLAUSIBILITY-BAND-ADMITTED-THE-DEFECT-IT-GUARDED). A guard test now fails the build if LGMK, _PLAUS_LO, _PLAUS_HI or _DAYS_CAP reappears in the owner."
  - "Do NOT restore arb_metrics or parse_terms_text. They were deleted deliberately; every caller is migrated."
  - "Do NOT reuse contracts/capital_structure_document_term_observation.schema.json — it was read and rejected as registration-fee-table scoped; see DEC:CASH-DEAL-NUMBERS-ARE-BYTE-BOUND-OR-ABSENT."
  - "Do NOT treat falling row counts as a regression. Deterministic extraction has lower recall by design; the honest metric is VERIFIED rows plus the visible degraded census."
  - "Do NOT re-run the full suite in this sparse worktree to judge health — 45 failures are pre-existing artifacts. Compare against origin/main with the same four files swapped, as this session did."
  - "Do NOT let a model lane supply a numeric term. parse_terms is _candidate_only and provably cannot satisfy the observation contract."
danger_areas:
  - "engine/special_arb.py `_price_candidates` negative lexicon: loosening the ±160-char window or removing a term (dividend/redemption/exercise/conversion/aggregate/notes) reopens the false-price class the corpus exists to catch."
  - "`_resolve_currency`: a bare $ must stay refused on any non-USD listing. Making it default to USD would silently restore the cross-currency compare."
  - "`_calendar_index` derives sessions from a suffix group's union of traded days — it is a proxy, not a real exchange calendar. A listing whose whole suffix group is dark looks current."
  - "collectors/special_situations.py `_cached_body` must keep reading ONLY doc_cache. Making it fetch by default turns a bounded lane into an unbounded SEC crawl."
  - "The observation ledger is append-only and de-duplicates on observation_id, which is a digest of (bytes, field, span, value, revision). Changing EXTRACTION_REVISION intentionally re-mints every observation — that is the correction path, not a bug."
prs: [6793]
decisions: ["DEC:CASH-DEAL-NUMBERS-ARE-BYTE-BOUND-OR-ABSENT"]
discoveries: ["DSC:ARB-PLAUSIBILITY-BAND-ADMITTED-THE-DEFECT-IT-GUARDED"]
---

## Why this handoff says `blocked` rather than `complete`

The source lane is finished and green, but the capability is not delivered: F09-1 may only reach
`PROVEN_LIVE` through one natural authoritative pipeline cycle, and that route is under the
macro#6783 disk-admission floor. No dispatch was made to manufacture proof. Anyone continuing
this should treat "117 tests pass and the PR is green" as the beginning of the evidence, not
the end of it — the whole point of the wave is that a confident number without a live receipt
is exactly the failure being repaired.

## The one wire that is deliberately missing

`collectors.special_situations.enrich_deal_terms()` writes the ledger; `engine.special_situations
._enrich_arb()` reads it. Nothing calls the writer yet. Wiring it into the daily sequence means
editing the build script or a workflow, both of which sat OUTSIDE the path set frozen at START,
so it stops for a Sol boundary ruling instead of quietly widening scope. Until that wire exists,
a production run would find an empty ledger and report every arb-category deal as
`SOURCE_UNAVAILABLE` — which is the correct degraded state, and is visible in the census rather
than silent.
