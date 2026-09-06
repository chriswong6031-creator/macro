---
workstream: "WS:MARKET-OS"
session: claude/f09-premium-math-v1-20260903 (rounds 1-2 Claude4 38c55853-6e42-4cbd-8a1f-910c2f7d673b; round 3 Claude8 bb72a676-c429-4224-9479-dba3c02da269 after a Chairman runtime rebind; round 4 Claude6/Ryan6-Max 58d45b99-0a88-4722-9138-18e12805cf43 after SOL RULING / PRESTART_REBIND 1788478471.712919 — one operation, worktree, branch and PR throughout)
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
    what: >
      5 engine-level F09 integration tests (session receipts, staleness, no invented day,
      no-ledger degradation, consumer divergence), the desk-page contract guard, the
      ledger-join-key end-to-end regression, and 3 collector-lane tests.
  - path: scripts/build_special_situations.py
    what: >
      _arb_str migrated to the F09-1 contract, null-safe on the degraded rows the contract now
      attaches. Authorized by Sol as PATH_BOUNDARY_EXPANDED for exactly this one path after the
      DECISION_REQUEST; no gross_spread_pct alias restored, downside-on-break not reinvented.
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
  - claim: "ROUND 3 — 18 exploit mutants failed against head a88c12f2 before any fix; the reviews reproduce exactly."
    command: "python3 -m pytest tests/test_special_arb.py -q  (exploit block appended, source unchanged)"
    result: >
      18 failed / 55 passed. Directly measured pre-repair outcomes: forged supersession field ->
      VERIFIED, offer 250.0, spread +1150%; session=2020-01-02 + expected_session=2026-06-01 +
      sessions_behind=0 -> VERIFIED; basis="totally_made_up_basis" -> VERIFIED; a genuinely
      5-sessions-stale close declared 0 -> VERIFIED; historical $48 cash proposal under
      "Background of the Merger" beside a current all-stock merger -> VERIFIED, offer 48.0,
      spread +20.0%, consideration cash; price_input() default basis = "close_raw".
  - claim: "ROUND 3 — the owned + dependent surface is green on the repaired head."
    command: "python3 -m pytest tests/test_special_arb.py tests/test_special_situations.py tests/test_special_sits_intel.py tests/test_special_prices.py tests/test_event_priors.py tests/test_world_state_special_sits.py tests/test_price_basis_graders.py -q"
    result: "263 passed"
  - claim: "ROUND 3 — zero regressions, proven by an identical failure SET rather than an identical count."
    command: >
      `git archive origin/main tests engine collectors lib scripts contracts config app admin`
      extracted to a scratchpad tree (no new worktree/branch), non-code dirs symlinked, then the
      8 failing files run on both sides and the FAILED name sets diffed with comm
    result: >
      40 failures on the branch and 40 on the origin/main baseline, byte-identical name sets —
      `comm -13` and `comm -23` both empty. All 40 are site/data-dependent suites
      (china_heatmap_gate, us_board_gate, seo_meta_rollout, unsubscribe_page,
      asset_stamp_lane_order, china_analyst_ticker, china_intel_hub_command) that fail the same
      way in a sparse worktree on unmodified main.
  - claim: "ROUND 3 — the ONE genuinely branch-caused failure was found by an existing repo guard and repaired, not waived."
    command: "python3 -m pytest tests/test_price_basis_graders.py -q"
    result: >
      test_no_new_module_pairs_the_two_bases went RED because engine/special_situations.py now
      names both `_closes_cache` and `data/yahoo`. Dead panel helpers (`_closes_paths`,
      `_panel_sources`) were deleted, and the module was registered in KNOWN_UNMIGRATED with a
      NO-PAIRING reason (the two stores never meet in one calculation, and the reducer's closed
      vocabulary refuses a breadth artifact outright). 9 passed, including the
      registry-does-not-rot and detector-not-vacuous guards.
  - claim: "ROUND 3 — the SEC acceptance clock is DST-correct and matches the proven owner's expression."
    command: "python3 -m pytest tests/test_special_situations.py -k acceptance -q"
    result: >
      winter 20260115120000 -> 2026-01-15T17:00:00+00:00 (EST, -05:00); summer 20260715120000 ->
      2026-07-15T16:00:00+00:00 (EDT, -04:00); both DST changeover mornings correct. The prior
      implementation hard-coded -04:00 for every filing. NOTE: importing
      collectors.sec_capital_structure raises on this host ("document-term parser code contains
      unsupported constant slice", Python 3.14) on blobs IDENTICAL to origin/main — pre-existing
      and unrelated — so equivalence is asserted by re-executing the owner's exact conversion
      expression AND pinning that expression against the owner's source.
  - claim: "PR #6793 is in a lawful hold state."
    command: "gh pr view 6793 --json isDraft,autoMergeRequest,labels"
    result: "draft=true, autoMergeRequest=null, labels=[]"
  - claim: "The desk page no longer raises KeyError on the economics contract."
    command: "python3 -c \"from scripts.build_special_situations import _arb_str; _arb_str(reduce_cash_deal(compile_current_terms([]), category='Acquisitions'))\""
    result: "'' (empty string). Before the migration this raised KeyError: 'gross_spread_pct'."
  - claim: "The prior head's CI concluded with every pack green."
    command: "watcher bsxma4gmg on PR #6793 head 8e4379e24a57, 300s cadence, exit-on-all-concluded"
    result: >
      ci-gate pass; ci-pack-0..11 all pass; trusted-executor-pack-0..11 all pass; ci-authority,
      ci-authority/main, ci-plan, contract-delta, fence-pack, capability-broker, grader-manifest,
      self-mod-fence, trusted-executor-main-admission, trusted-executor-hosted-plan all pass.
      One red, ci-authority/codex/merge-queue-pilot, whose payload reads allowed:true /
      ordinary_change / authority_hit_count:0 and which is red identically on sibling heads
      #6790 and #6789 — base-side, not this branch's.
  - claim: "Round 4 — the staged repair executes: the four owned suites are green on the first run they ever received."
    command: "python3 -m pytest tests/test_special_arb.py tests/test_special_situations.py tests/test_special_sits_intel.py tests/test_price_basis_graders.py -q -p no:randomly"
    result: "198 passed (197 before the M4 guard test was added). The staged tree had never been executed by its author."
  - claim: "The ledger clock/listing bypass is closed on BOTH readers, and each defence layer is pinned separately."
    command: "15-mutant matrix; 6 hostile REDs asserting collector read_ledger_strict AND engine _load_observations reject every resealed tamper"
    result: >
      15/15 killed at 209 passed. Extending the matrix exposed that this repair had itself
      un-pinned three things: M9 (malformed-line counter) had been KILLED before and now
      survived, because a corrupt ledger reaches ok=False through the new unbound path too, so
      "census is unhealthy" assertions passed either way; M14 (meaning-bearing fields dropped
      from observation_id) and M15 (authored_terms back on the row's own currency) survived
      because the independent rebind catches those mutants first. Three tests now pin each layer
      alone: malformed counted AS malformed, an unresealed edit rejected on identity (invalid,
      not unbound), and authored_terms proved to receive the canonical currency via a row that
      omits its own.
  - claim: "Both halves of the round-5 semantic repair are themselves mutant-pinned."
    command: "matrix extended to 12: M11 restores the (anchored or admissible)[0] fallback; M12 narrows _CURRENT_TXN_ANCHOR back"
    result: >
      12/12 killed at 201 passed. M12 matters because the narrowed vocabulary is exactly the gap
      the fallback used to hide, so without it the recall repair could be reverted silently.
  - claim: "Every repaired guard is pinned by a named test — proved by mutation, not by the suite being green."
    command: >
      10-mutant matrix, each re-introducing exactly one repaired defect into the real source,
      suites run, file restored from the index and re-verified by blob digest between mutants
      (scratchpad harness; anchors asserted unique before any write).
    result: >
      10/10 killed. M4 (the receipt's declared expected_session no longer compared) SURVIVED
      197/197 on the first pass — a correct, reviewed, shipped guard that no test pinned, because
      all four sibling freshness tests also move session or sessions_behind and the recomputed
      staleness arithmetic reddens first. Closed by
      test_a_false_expected_session_field_is_invalid_even_when_the_price_is_current.
  - claim: "Zero regressions across the dependent surface, measured as a controlled A/B on one tree."
    command: >
      33 test files referencing these modules (the 4 owned suites excluded) run twice on the SAME
      sparse worktree: once against the repaired sources, once with origin/main's versions of all
      six F09 paths swapped in and nothing else changed.
    result: >
      Branch 40 failed / 1547 passed / 19 skipped; origin/main-swapped 40 failed / 1547 passed /
      19 skipped. Failing sets identical test-for-test: 0 only-on-branch, 0 only-on-main. The 40
      are pre-existing sparse-worktree artifacts in unrelated suites.
  - claim: "The Sol-pinned owner blobs still match current main, so the receipts are valid against current code."
    command: "git rev-parse origin/main:collectors/yahoo.py origin/main:lib/nyse_calendar.py (main 68f81214)"
    result: "7e41bb66d921b43bee6253f316bb1849e2c3e72b and 0ece6439ffe4b081ee7a268fe99b69e1de1216a3 — both exactly the pinned PRICE_WRITER_BLOB / CALENDAR_BLOB."
  - claim: "The one red is not attributable to this head — read from its own payload, not inherited."
    command: "gh api repos/.../commits/a88c12f2.../check-runs | jq '.check_runs[]|select(.name|test(\"merge-queue-pilot\"))'"
    result: >
      allowed:true, reason:same_repo_admin_authority_change, admin_verified:true. The failure is
      context_base_ref:codex/merge-queue-pilot with context_active:false and
      context_reason:inactive_base_context — an inactive base context, not a verdict on this
      branch's content.
  - claim: "No path collision anywhere in the repository."
    command: "blob-identity scan of all 1046 remote branch tips against origin/main on the six F09 owner paths"
    result: "0 branches differ on any of them; exactly one PR exists on this branch."
  - claim: "contract-delta is genuinely candidate-caused, NOT the known stale-base artifact — tested, not assumed."
    command: "git show origin/main:engine/special_situations.py | grep 'from collectors import'  (empty) vs HEAD line 715"
    result: >
      engine/special_situations.py gains `from collectors import special_situations as col`,
      absent on origin/main; collectors/special_situations.py already imports
      engine/qual_extraction.py on main. That one new edge widens six job closures, which is why
      five findings name jobs F09 never touches. Job 100865703147: 8 introduced, 0 inherited.
  - claim: "The bounded manifest widening clears contract-delta on the tree CI actually builds."
    command: >
      simulated merge ref — origin/main's .github/ci/legacy-jobs.yml plus the exact 8 authorized
      additions, then scripts/check_contract_delta.py --base f72d6430ccab
    result: >
      0 introduced, 0 inherited. Running it against this branch's own (stale) manifest instead
      reports 1 introduced for tests/test_top_anatomy_oot_receipt.py — a file present on BOTH
      sides that main's manifest wires in 3 places and this branch's older manifest wires in 0.
      That one is a stale-manifest artifact of the branch base, never a CI finding, and needs no
      action. The effective manifest diff is 8 added lines, 0 removed.
  - claim: "The current-transaction scope repair discriminates and does not become blanket refusal."
    command: "revert `return None` to `(anchored or admissible)[0]`, run the three new scope tests"
    result: >
      2 failed, 1 passed — exactly the two decline cases die and the anchored-positive case
      survives, which is the correct signature. Restored and re-verified byte-for-byte.
  - claim: "Removing the fallback exposed anchor-vocabulary gaps, not regressions; the negatives still decline."
    command: "corpus scope audit over all 22 cases before and after extending _CURRENT_TXN_ANCHOR"
    result: >
      dividend/redemption/exercise-price/aggregate-value still scope=None after the widening;
      contingent_value_right, cross_currency_bare_dollar, explicit_foreign_currency and
      terminated_offer resolve again because their real phrasing ("will receive", "will be
      acquired for", "previously announced merger") is now carried. 201 passed.
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
  - >
    Sol's exact-head review 5099936758 REJECTED the first head with eight defects (six real
    false-precision holes) and they are repaired at the successor head: producer wiring,
    accession-scoped deal identity, complete-byte retention with versioned projection,
    fail-closed ledger revalidation, lib/nyse_calendar as the independent freshness owner,
    explicit now_utc plus acceptance-timestamp reference sessions, transaction-scoped
    extraction, and comparator-bound stated premium. See research report section 7.
  - >
    A secretary relay on the carrier reported the consumer repair, the xfail removal and a head
    as already done BEFORE any of it existed (verified false against git at the time: the file
    was untouched, the xfail present, and that head was a records-only commit). The receiver
    corrected the record and then performed the work. Treat relayed progress about this session
    as unverified until checked against git.
  - "Production proof is gated behind macro#6783 (Mac Studio daily-runner disk-admission floor). Capability is BUILT_NOT_PROVEN / PRODUCTION_INERT."
  - "RESOLVED in round 3 — enrich_deal_terms() IS now called by build(refresh=True) before desk_payload(), under the PATH_BOUNDARY_EXPANDED Sol granted for exactly scripts/build_special_situations.py. --no-refresh stays source-inert, pinned by a build-path test. Do not re-request this ruling."
  - "RESOLVED — the exact-head independent review WAS obtained at a88c12f2 and returned NOT PASS (Claude8 2ca24e4c, carrier 1788441277.558499), adding four defects Sol had not named, three reaching VERIFIED. All are repaired in the round-3/4 head; see research report section 8. A FRESH independent review is owed on the new head and may not come from this lane."
next_actions:
  - "Obtain a fresh exact-head independent review of PR #6793 at the round-4 head; repair only on the same carrier. The reviewer may NOT be this lane: the fleet shares the chriswong6031-creator GitHub identity with the PR author, so a self-review would not be independent — which is also why the a88c12f2 NOT PASS was returned on Slack rather than as a GitHub REQUEST_CHANGES."
  - "Return RESULT / HOLD-FOR-SOL on C0BSBM78V1N/1788407688.753659 and wait for Sol acceptance. Do NOT self-merge, mark Ready, or arm merge-on-green."
  - "Do NOT re-ask for the enrich_deal_terms() path ruling — Sol granted it (carrier 1788426229.286289, repair 1) and round 3 performed the wiring."
  - "After #6783 restores the daily route, observe ONE natural cycle (never a dispatch) and check: observation counts, VERIFIED vs degraded census, every ordered row's receipts, the real LGMK disposition, and all five Neural Web consumers."
do_not_redo:
  - "Do NOT add a magnitude clamp, band, cap or ticker exception. The band already existed and ADMITTED the 42,790.2% row (DSC:ARB-PLAUSIBILITY-BAND-ADMITTED-THE-DEFECT-IT-GUARDED). A guard test now fails the build if LGMK, _PLAUS_LO, _PLAUS_HI or _DAYS_CAP reappears in the owner."
  - "Do NOT restore arb_metrics or parse_terms_text. They were deleted deliberately; every caller is migrated."
  - "Do NOT reuse contracts/capital_structure_document_term_observation.schema.json — it was read and rejected as registration-fee-table scoped; see DEC:CASH-DEAL-NUMBERS-ARE-BYTE-BOUND-OR-ABSENT."
  - "Do NOT treat falling row counts as a regression. Deterministic extraction has lower recall by design; the honest metric is VERIFIED rows plus the visible degraded census."
  - "Do NOT re-run the full suite in this sparse worktree to judge health — 45 failures are pre-existing artifacts. Compare against origin/main with the same four files swapped, as this session did."
  - "Do NOT let a model lane supply a numeric term. parse_terms is _candidate_only and provably cannot satisfy the observation contract."
  - "Do NOT re-add downside_on_break_pct to the rendered desk line or the contract. It is a downside target, explicitly outside F09-1, and Sol's boundary ruling names it."
  - "Do NOT reintroduce a panel-derived session count. lib/nyse_calendar.py is the freshness owner and must not be edited, copied, or approximated."
  - "Do NOT bind an observation to the stripped doc_cache. It is a lossy TRUNCATED projection; retain the complete object and keep the projection as a separate versioned receipt."
  - "Do NOT group observations by issuer CIK. An accession is an isolated transaction unless an explicit source-linked supersession proves otherwise."
  - "Do NOT reason about _arb_str from the pre-F09 signature. It reads live_gross_spread_pct and is null-safe; a real guard test now pins both directions."
  - "Do NOT accept a green suite as evidence that a guard works. M4 proved a correct, reviewed, shipped guard can be pinned by nothing: deleting the expected_session comparison left 197/197 passing. Mutate each guard separately and require a named killing test; when writing that test hold every other input HONEST and perturb exactly one field, or a coarser sibling check absorbs it. See DSC:A-GREEN-SUITE-CANNOT-TELL-YOU-WHICH-GUARDS-IT-PINS."
  - "Do NOT judge regressions from a raw failure count in this sparse worktree. Run the controlled A/B: the same 33 dependent test files twice on ONE tree, second pass with origin/main's six F09 sources swapped in, and compare failing sets test-for-test. Restore from the INDEX afterwards and re-verify by blob digest — a killed run leaves the swapped bytes in place."
  - "Do NOT try to bind this operation from the process table or an app-level window id. The round-3 writer was native session bb72a676-c429-4224-9479-dba3c02da269, not the local_2bfd22a6 file id the census examined, and its metadata CWD was macro-main while it wrote the worktree by absolute path. Bind from the session transcript and from what the artifact says about its own author."
danger_areas:
  - "engine/special_arb.py `_price_candidates` negative lexicon: loosening the ±160-char window or removing a term (dividend/redemption/exercise/conversion/aggregate/notes) reopens the false-price class the corpus exists to catch."
  - "`_resolve_currency`: a bare $ must stay refused on any non-USD listing. Making it default to USD would silently restore the cross-currency compare."
  - "`_calendar_index` NO LONGER EXISTS (removed 2026-09-03, round 2). Freshness comes from lib/nyse_calendar and the PURE reducer recomputes expected_session/sessions_behind itself — never trust a receipt's own count."
  - "engine/special_arb.py `validate_price_receipt` is a CLOSED vocabulary (basis/column/writer blob/calendar blob/artifact name). Adding a store to it is a basis decision, not a config change: `collectors/yahoo.py` is the only reviewed writer and `close_price` the only reviewed column."
  - "The reviewed owner blobs (PRICE_WRITER_BLOB, CALENDAR_BLOB) are PINNED. If either owner legitimately moves, `test_the_reviewed_owner_blobs_are_pinned_to_the_real_repository_blobs` fails loudly — re-review the basis/calendar semantics and re-pin; never widen the vocabulary to make the red go away."
  - "`tests/test_price_basis_graders.py` KNOWN_UNMIGRATED carries engine/special_situations.py with a NO-PAIRING reason. It is load-bearing: the module names both `_closes_cache` (passed through to activist/special_prices, no arithmetic here) and `data/yahoo` (the F09 path). Do NOT migrate this module to engine.price_ladder — the ladder is coverage-first with fallbacks and would make PRICE_BASIS_UNRESOLVED unreachable, which is the defect this capability removes."
  - "collectors/special_situations.py: `_cached_body` is the LEGACY CANDIDATE cache (stripped, 40k-truncated) and may never be promoted to a source object. The deal-term lane reads `verified_projection()` instead, which re-opens the retained object and re-checks digest+length+projection before extracting. `enrich_deal_terms(fetch_missing=True)` is the ONLY fetching path (the natural build passes it; `--no-refresh` never reaches it) — making it fetch unconditionally turns a bounded lane into an unbounded SEC crawl."
  - "`_retain_source` takes BYTES (`Response.content`), never `Response.text`. Re-encoding a decoded str with errors=\"replace\" is a lossy round trip, so the digest would describe our decoding rather than SEC's document."
  - "The observation ledger is append-only and de-duplicates on observation_id, which is a digest of (bytes, field, span, value, revision). Changing EXTRACTION_REVISION intentionally re-mints every observation — that is the correction path, not a bug."
prs: [6793]
decisions: ["DEC:CASH-DEAL-NUMBERS-ARE-BYTE-BOUND-OR-ABSENT",
             "DEC:F09-TRANSACTION-SCOPE-IS-STRUCTURAL-NOT-PRICE-ANCHORED"]
discoveries: ["DSC:ARB-PLAUSIBILITY-BAND-ADMITTED-THE-DEFECT-IT-GUARDED",
              "DSC:A-DIGEST-OF-A-DERIVED-PROJECTION-IS-NOT-BYTE-BINDING",
              "DSC:A-RESEALED-ROW-IS-SELF-CONSISTENT-NOT-EVIDENCED",
              "DSC:A-PURE-REDUCER-THAT-TRUSTS-ITS-RECEIPT-HAS-NO-GATE",
              "DSC:A-GREEN-SUITE-CANNOT-TELL-YOU-WHICH-GUARDS-IT-PINS",
              "DSC:A-FALLBACK-MAKES-ITS-PRIMARY-PATHS-COVERAGE-UNMEASURABLE"]
---

## Why this handoff says `blocked` rather than `complete`

The source lane is finished and green, but the capability is not delivered: F09-1 may only reach
`PROVEN_LIVE` through one natural authoritative pipeline cycle, and that route is under the
macro#6783 disk-admission floor. No dispatch was made to manufacture proof. Anyone continuing
this should treat "117 tests pass and the PR is green" as the beginning of the evidence, not
the end of it — the whole point of the wave is that a confident number without a live receipt
is exactly the failure being repaired.

## The consumer break, and why it is worth remembering

`scripts/build_special_situations.py:82` subscripted `a['gross_spread_pct']` directly, so the
desk page raised `KeyError` on the renamed contract — and **no CI check covers `_arb_str`**, so
the PR would have gone fully green while carrying a page-build crash. It was found by tracing
the wire from the collector to the page while writing this handoff, not by any test or check.

Two transferable lessons. First, a rename inside a contract is only half a migration; grep for
**direct subscripts** of the old key, because `.get()` degrades quietly while `[...]` crashes
loudly and neither is covered if the renderer is untested. Second, the honest response to
"no check can see this" is not to merge and hope — it was raised as a boundary request, pinned
in code by a strict xfail so it could not be forgotten, and only fixed once Sol expanded the
path. The xfail is now gone, replaced by a real two-direction guard.

## The wire that WAS missing — now present (superseded 2026-09-03)

This section previously read "nothing calls the writer yet". That is no longer true and reading
it as current would send the next session to fix something already fixed. Sol expanded the path
by exactly one file, and `scripts/build_special_situations.py:build(refresh=True)` now calls
`col.enrich_deal_terms(..., fetch_missing=True)` BEFORE `sse.desk_payload()`, pinned by
`test_the_real_build_path_calls_the_producer_and_no_refresh_stays_source_inert`. `--no-refresh`
remains network- and source-inert.

`fetch_missing=True` is the load-bearing half and was added in round 3: without it every
accession that any earlier build had already cached could never obtain a complete-source
receipt, `enrich_deal_terms()` skipped it, and coverage over the entire pre-existing corpus was
structurally **zero** — permanently, with no backfill path. "Narrow coverage" would have been
unmeasured, not narrow.

## Round 3 — the critical repair, under a runtime rebind

Rounds 1-2 ran in Claude4 session `38c55853-6e42-4cbd-8a1f-910c2f7d673b`. That account became
provider-unavailable (`Organization access is disabled`) mid-delivery; a host census proved its
worktree clean at PR #6793 head `a88c12f2`, so the failed turn created no source effect, and the
Chairman rebound the SAME operation to Claude8 session
`bb72a676-c429-4224-9479-dba3c02da269` in the SAME worktree, branch and PR. No new operation,
carrier, branch, PR, watcher or worktree was created.

Round 3 answered Sol reviews `5102199556` + `5102373399` and the reviewer-STOP addendum. Its
lesson is the one worth carrying: **every defect in this round was a gate that reviewed as real.**
`_has_calendar_receipt()` named four true fields and did no arithmetic. `observation_id` was a
closed digest — over everything except the correction relation and the status. `validate_observation()`
re-derived that digest — from the row itself, so a resealed forgery passed. `_retain_source()`
wrote a receipt about bytes it had never read back. Each one is the shape a reviewer approves,
and the only thing that found them was asking *who could produce this receipt* and *what is this
digest a digest OF*. Both new discovery records are about exactly that:
`DSC:A-RESEALED-ROW-IS-SELF-CONSISTENT-NOT-EVIDENCED` and
`DSC:A-PURE-REDUCER-THAT-TRUSTS-ITS-RECEIPT-HAS-NO-GATE`.

One finding was NOT in either review and came from a mutant written while repairing a different
class: because the repaired extractor records out-of-scope prices as `deferred` rows, `status`
being outside the digest would have let a flip from `deferred` to `observed` promote a rejected
background proposal to the live offer. The fix for one defect created the hole for another,
which is why the semantic tuple is enumerated explicitly rather than derived from "whatever the
digest happens to cover".

## Round 4 — adopting a dead session's staged effect, and proving it

Round 3 never finished. Its session died mid-tool-call at `14:57:08Z` ("tool call could not be
parsed (retry also failed)"), 2m16s after its last file write, leaving **15 paths staged and
never once executed**: no test had run against them, nothing was committed, nothing pushed. A
runtime census then returned `SESSION_LOST / EFFECT_UNKNOWN`, and Sol's
`PRESTART_REBIND` (`1788478471.712919`) bound round 4 (Claude6/Ryan6-Max,
`58d45b99-0a88-4722-9138-18e12805cf43`) to the same worktree, branch and PR with one standing
instruction: preserve the staged bytes exactly, then finish.

**Attribution, since the census could not close it.** The census examined app-level file id
`local_2bfd22a6-e7a1-410e-a9f5-af5f5f2d0122`, found its metadata CWD was `macro-main`, and
concluded it "does not bind the designated F09 worktree". The real writer is native session
`bb72a676-c429-4224-9479-dba3c02da269`: its transcript starts `13:45:59Z` — 11 seconds after the
rebind edge — ends at `14:57:08.669Z`, the exact instant the census reported as the other id's
last activity, and references this worktree 159 times. Same session, two id namespaces. The
generalizable trap is that **a CWD in session metadata is not where a session wrote**: that one
ran with cwd `macro-main` and worked the worktree by absolute path, which is also how round 4
runs. Attribution here came from the transcript and from the staged handoff naming its own
author — not from the process table.

**What adoption actually required.** The staged code was written *after* the reviewer's NOT PASS
and Sol's addendum and it does address them — but "addresses" was an inference from reading, and
an unexecuted repair is a claim, not a result. So round 4 ran the suites (197 green on the first
execution the staged tree ever received), then treated the green as worthless on its own and
mutated each repaired guard separately. Nine of ten mutants died to exactly one test. The tenth
did not, and that is the round's real finding — see
`DSC:A-GREEN-SUITE-CANNOT-TELL-YOU-WHICH-GUARDS-IT-PINS` and research report section 8. A guard
can be correct, reviewed, and pinned by nothing; the only instrument that says which is which is
deleting it and seeing whether anything notices.

Round 4 also closed a dangling forward reference the cut-off left: the staged report cites a
"section 8" that round 3 never wrote. It is written now, and the round-3/round-4 rounds are kept
as separate sections on purpose — the useful fact about this wave is that a green suite, a
CI pack sweep, and an exact-head review all held at once while three `VERIFIED`-reaching defects
were still live.

## Round 5 — the CI manifest and the last false-precision fallback

Head `bb86d760` came back red on four checks, and the round is mostly an exercise in refusing to
treat them as one thing. `contract-delta` was **candidate-caused**; `trusted-executor-pack-7` was
an `npx` eslint fetch timing out at 180 s; `ci-gate` failed downloading zero semantic fragments
the trusted packs had uploaded; `merge-queue-pilot` says `allowed:true` in its own payload and
fails only on an inactive base context. Sol classified the last three as not-ours and explicitly
forbade patching them from this carrier. They are not waived — a later natural run that
reproduces a source-correlated failure reopens them.

The contract-delta finding is the one worth remembering, because it looked exactly like the
known artifact and wasn't. Five of eight findings named `engine/qual_extraction.py` against
`biocatalyst-*`, `flow-surface` and `unrun-*` — jobs F09 never touches — which is the signature
of `contract-delta` billing a PR for a main-side closure change its base predates. Tested
instead of assumed: `engine/special_situations.py` gains `from collectors import
special_situations as col`, absent on main, and `collectors/special_situations.py` already
imports `qual_extraction` there. One new edge, six widened closures. Mine.

The inverse then showed up on the same gate. Run locally against current main, contract-delta
reports `tests/test_top_anatomy_oot_receipt.py` unwired — a file on both sides that main's
manifest wires three times and this branch's older manifest wires zero times. *That* one is the
stale-base artifact, it is invisible to CI because CI builds the merge ref, and the fix for it is
nothing. Both readings of the same gate in one round is the reason the verification was run on a
simulated merge ref (main's manifest + the 8 authorized additions → `0 introduced, 0 inherited`)
rather than on the branch tree.

The semantic half removed `(anchored or admissible)[0]`. Five tests failed instantly and the
triage — not the count — was the finding: four negative corpus cases still declined correctly,
and four *genuine* transactions had been living on the fallback because the anchor vocabulary
never carried their phrasing. See
`DSC:A-FALLBACK-MAKES-ITS-PRIMARY-PATHS-COVERAGE-UNMEASURABLE`. The distinction that governed the
repair: extending a closed vocabulary still requires the document to assert a transaction, while
the fallback required only that it have sections.

## Round 6 — the ledger clock and listing authority

The third Sol addendum is the sharpest of the wave because nothing in CI could have found it:
the JSON Schema is exercised only by tests, while the two production readers call
`validate_observation()`, which re-derives a row's id from the row's OWN fields. A row could
therefore rewrite its acceptance clock, its filing date, or its resolved listing, reseal, and
survive — changing which session a filing-reference premium is drawn from, which observation is
current, or whether a bare `$` becomes USD. `_load_observations()` even passed
`authored_terms(listing_currency=o.get("currency"))`, so the untrusted row nominated the
authority that then blessed it.

The repair is one law over both readers: the three fields inside the closed digest, and — since
resealing is not authorization — each re-bound to an owner outside the row (the retained
acquisition receipt for the clock, `canonical_event_authority()` for filing date and listing,
with the listing admitted only where the per-ticker Yahoo `close_price` owner proves it). No
event authority means fail closed.

The lesson worth carrying forward is the mutation result, not the repair. Extending the matrix
to fifteen showed this repair had **un-pinned three existing behaviours**: M9's malformed-line
counter had been killed in the previous round and now survived, because a corrupt ledger reaches
`ok is False` through the new unbound path as well, so every "the census is unhealthy" assertion
passed with or without it. M14 and M15 survived for the same structural reason — the new,
stronger gate catches those mutants first. Adding a defence-in-depth layer silently converts the
layers beneath it into decoration unless something still fails when you remove each one alone.
That is [[A-GREEN-SUITE-CANNOT-TELL-YOU-WHICH-GUARDS-IT-PINS]] arriving from the opposite
direction, and it is why the matrix is re-run in full after every layer rather than extended
once at the end.
