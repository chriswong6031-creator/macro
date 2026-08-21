---
key: PROPHET-HK-CA-REVAMP
title: HK + Canada Prophet revamp — truth repair, era-clean evaluation, shadow races
objective: >
  Copy the US/China Prophet authority architecture (not factor recipes) to Hong
  Kong and Canada. Done means: Canada has one canonical Branch-B board whose
  artifact/page/ledger projections provably share one order under a prospective
  board_definition with explicit screen authority; current-definition Canada
  selection metrics are era-clean (no legacy pooling); challenger ranking and
  discovery accrue in zero-authority shadow stores on the same outcome clock as
  the incumbents; HK candidate recall broadens upstream without touching
  hk_standouts.json or HK Brain pre-promotion; and promotion is a separate
  per-market adjudication against predeclared bars.
status: active
program: prophet
repos: [macro, mastermind]
owner: fable
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - scripts/build_canada_library.py
  - scripts/build_canada.py
  - engine/board_ledger.py
  - engine/hk_board_rank.py
  - engine/hk_stock_signals.py
  - scripts/build_hk_library.py
  - tests/test_canada_build.py
  - tests/test_board_ledger.py
  - engine/track_ledger.py
  - tests/test_track_ledger_emitters.py
  - research/PROPHET_HK_CANADA_REVAMP_EXECUTION_PACKET_2026_08_18.md
artifacts:
  - research/PROPHET_HK_CANADA_REVAMP_EXECUTION_PACKET_2026_08_18.md
landmines:
  - "CA-TRUTH (PR #5926, merged e495570eb5d8 2026-08-19, live-verified on the VPS):
    the composite re-sort defect is FIXED — one canonical Branch-B board object now
    feeds artifact, page, and ledger. Era-fence cost, DECLARED not accidental: the
    first stamped nightly makes board_ledger._latest_definition return
    ca_prophet_branch_b_v1, dropping all 382 legacy CA rows (21 dates,
    2026-06-30→08-17, definition None) out of rank_ic; the CA scorecard stays
    'accruing' ~21 more trading days (first scored read ≈ late Sept). Do NOT
    'fix' this by backfilling or deleting legacy rows — both are packet STOPs."
  - "Standalone library lanes (weekly.yml, engine-render scope=all, failure nets)
    rebuild canada_standouts.json via build_canada_library.__main__; overlay now
    resolves from data/canada_regime/latest.json (_last_rendered_overlay) so lane
    rewrites keep the page's oil stamps. Row ORDER is provably overlay-independent."
  - "bot:canada_book in the artifact manifest (scripts/export_signal_contracts.py)
    is a STALE-MANIFEST declaration: no live consumer in macro/Mastermind/terminal
    (censused 2026-08-18). Breaking schema changes still wait for a written
    consumer resolution; use additive fields."
  - "Board-ledger identity stays keep-FIRST (date,ticker) — do NOT migrate to
    (date,ticker,board_definition); challenger storage is separate (packet §8-9)."
  - "HK: never publish a challenger to hk_standouts.json pre-promotion — HK Brain
    consumes that artifact, so publishing IS an authority transition (packet §10.6)."
do_not_redo:
  - "Full do-not-redo register lives in the execution packet §21 (binding): no HK
    residual momentum as primary alpha, no Southbound-delta promotion, no H3/X1
    promotion below DSR 0.90, no C1 oil as name-level edge, no TSXV in initial
    repair, no shared US SCORE_WEIGHTS retune, no board-ledger identity migration,
    no Canada Brain before trustworthy Canada authority."
waves:
  - id: ca-truth
    title: Canada canonical board truth
    status: done
    pr: 5926
    settlement_receipt: >
      PASSED 2026-08-20 (first owed TSX session 2026-08-19; verifier = Fable
      session fable-handoff-hk-canada-prophet-c7c63d). Nightly commit
      fae690766555 (engine regime update 2026-08-20) built on merged code
      (contains e495570eb5d8); VPS checkout 5d58699cf8b contains it (api/health
      + merge-base --is-ancestor). Artifact origin/main
      site/factordata/canada_standouts.json — as_of=2026-08-19,
      board_definition=ca_prophet_branch_b_v1, authority=screen,
      official_pick_authority=false, selection_status=accruing, buy board_pos
      1..10 contiguous, top-level rank_basis=momentum_screen_accruing. Page
      parity — served https://mastermind-x.com/canada_stocks.html
      stocktable-data block byte-equal to git and row order == artifact buy
      order exactly (10/10). Ledger data/board_ledger/ca_board.parquet — 18
      rows for 2026-08-19 all stamped ca_prophet_branch_b_v1, board_pos 1..18
      (buy 1-10 in artifact order + watch 11-18); the 382 legacy rows (21
      dates 2026-06-30..08-17) preserved with null definition; PLUS 18
      legacy-by-timing rows for session 2026-08-18 (nightly ran ~02-08Z
      08-19, before the 16:04Z merge) — also null-definition, correct, total
      legacy pool now 400; zero duplicate (date,ticker) keys (keep-FIRST
      intact). Era fence — scorecard('CA') on the production parquet returns
      status=accruing under board_definition=ca_prophet_branch_b_v1 with
      21d_ic_dates=0/5 (legacy fenced out of rank statistics), as declared.
      NOTE the factordata HTTP endpoint is tier-locked
      (authentication_required); served-byte proof therefore rides the VPS
      checkout ancestry (the check_nightly_liveness.py pattern — repo paths
      ARE the served files) plus the public canada_stocks.html direct fetch.
  - id: ledger-era
    title: Era-clean HK/CA scorecard semantics
    status: done
    depends_on: [ca-truth]
    pr: 6072
    settlement_receipt: >
      PASSED 2026-08-21 (all four legs; verifier = Fable session, continuation
      of fable-handoff-hk-canada-prophet). Producing lanes: HK = asia-close
      13:05Z 08-20 (post-merge), artifact commit baf4cf7c9291; CA = daily.yml
      run 32426513915 (head 50577f18c5fb, merge-descendant) — its engine job
      96640561705 wrote artifact commit 5ba8447ca827; the run's 'cancelled'
      conclusion is attributable solely to job standout_audit_us (06:33Z,
      after publish succeeded 05:00Z) and the 23:49Z sibling run 32430224218
      is the DST-gated twin that builds nothing — settlement judged on
      produced bytes, not run color. All artifact commits + the VPS checkout
      e34f091309a verified merge-descendants of 273883182d9b. LEG 1 PASS:
      ca_track_ledger.json primary = 18 rows, all d=2026-08-19
      bd=ca_prophet_branch_b_v1, zero era mixing; summary n_calls=18
      n_matured=0 win_pct=None state=accruing; prior_record = 400 rows
      newest-first (08-18→06-30) all null-definition, meta.n_total=400
      truncated=0, own summary n_matured=163 win_pct=27.6 (Wilson 21.3–34.9)
      with bilingual never-pool notes. LEG 2 PASS on substance with a LOCUS
      CORRECTION: canada_standouts.json has NEVER carried board_track in any
      era (pre-merge 13750ecd1789 and post-merge 5ba8447 both verified
      absent) — build_canada_library.main() serializes the artifact ONCE
      (build_canada_library.py:800) and _canada_board_ledger attaches
      board_track to the returned in-memory dict afterwards
      (build_canada.py:766), so the scorecard's real production consumers are
      the rendered canada.html track chip/dialog and ca_track_ledger.json (by
      CA-TRUTH single-write design). Substance verified by running
      scorecard('CA') against the production parquet bytes:
      metrics_scope=current_definition; historical_context legacy_rows=400
      (==raw legacy count exactly), counts_source=raw_ledger, note
      "historical context only; not current-model track record"; current-era
      by_horizon honestly all-zero. LEG 3 PASS (HK, settled 08-20):
      hk_track_ledger.json 117 era rows 08-04→08-19 zero mixing; prior_record
      n_total=359 == raw parquet legacy pool; pooled 37.8% confined to the
      prior era's own summary; prior_record's existence proves
      build_hk_library board_definition propagation active in the produced
      artifact. LEG 4 PASS: HK half silent-with-positive-evidence (75 v2 rows
      spine-filled at 5d in the committed parquet; no era-empty annotation on
      the asia engine check run); CA half fired TRUTHFULLY on production
      (annotation "board-ledger-era-empty :: CA board_definition names an era
      with zero graded rows" on job 96640561705) — raw parquet proves the era
      is genuinely all-unmatured (36 current rows, zero non-null fwd_mfe at
      every horizon), and HK proves the same code path goes silent once era
      rows mature. POPULATION RECONCILIATION (no shape-only claims): raw 436
      = 400 legacy + 36 current; legacy 400 = 346 graded + 54 suspended
      (vanished names, survivorship note published); current 36 = 18 (08-19,
      next-bar-filled, unmatured → exactly the ledger's 18 primary rows) + 18
      (08-20, no next bar yet, outside the graded frame until the 08-21 bar);
      prior_record n_matured 163 == raw legacy fwd_mfe_21 non-null count.
      Every denominator difference accounted; no era pooling anywhere.
    next_action: >
      DIARIZED FOLLOW-UP (sentinel persistence test): on/after ≈2026-08-26
      (5d maturation of the 08-19 CA rows) verify the board-ledger-era-empty
      warning stopped firing on the CA engine job. If it persists once
      legitimately gradable current-era observations exist, that IS the
      defect it exists to catch — investigate; never silence or weaken it.
    scope_delta: >
      Wave scope extended during adversarial review (packet §7.3 "scorecard
      consumers only if needed"): engine/track_ledger.from_board_ledger_grade
      published a COMPETING pooled hit rate beside the era-scoped one (dialog
      invariant "eras never mix in one view" was broken for HK/CA; CN's
      prior_record pattern was never ported) — now era-fenced with a
      prior_record block, one fix covering HK+CA. Also fixed in the same PR:
      _latest_definition whitespace normalization (a trailing-space stamp
      silently blanked the whole published record — reviewer's executed A1
      attack), raw-parquet historical_context counts (graded-frame estimate
      undercounted delisted names) with counts_source marker, prior rows
      newest-first before cap, and the scored-branch card caption ("of —
      finished trades") now carries the era-scoped buy-lane denominator on
      canada.html.j2 + hk.html.j2.
  - id: shadow-contract
    title: Rank/discovery shadow substrate
    status: in_progress
    depends_on: [ledger-era]
    next_action: >
      OPENED 2026-08-21 immediately on the ledger-era pass (CEO Sol directive
      08-20: no extra permission cycle). Contract frozen as
      research/PROPHET_SHADOW_CONTRACT_V1.md after an Opus adversarial
      pre-implementation review of the K1–K10 mutation-kill suite; one Sonnet
      builder wave implements engine/board_shadow.py + stores
      data/prophet_shadow/{hk,ca}_{rank_pairs,discovery}.parquet with
      executed mutation kills. Non-negotiables: zero authority (nothing in
      production reads the stores), board_ledger stays keep-FIRST
      (date,ticker), challenger registry EMPTY at merge, prospective-only
      accrual, outcomes only by join to the governed board_ledger grading
      clock. HK-DISCOVERY / HK-INTEL / CA-INTEL / races stay CLOSED until
      this wave is merged + verified.
  - id: hk-discovery
    title: HK candidate-recall shadow
    status: todo
    depends_on: [shadow-contract]
  - id: hk-intel
    title: HK native intelligence adapters
    status: todo
    depends_on: [hk-discovery]
  - id: hk-race
    title: HK ranking and discovery races
    status: todo
    depends_on: [hk-intel]
  - id: ca-intel
    title: Canada sector/name/entry authority split
    status: todo
    depends_on: [shadow-contract]
  - id: ca-race
    title: Canada rank and sector-name accrual
    status: todo
    depends_on: [ca-intel]
  - id: ca-pit
    title: Canada PIT replay resolution
    status: todo
    depends_on: [ledger-era]
  - id: promotion
    title: Separate market promotion adjudications
    status: todo
    depends_on: [hk-race, ca-race]
next_action: >
  LEDGER-ERA settled 2026-08-21 (full receipt in the ledger-era wave entry;
  sentinel persistence follow-up diarized there for ≈2026-08-26).
  Shadow-contract wave OPEN: frozen contract
  research/PROPHET_SHADOW_CONTRACT_V1.md, one builder wave, executed K1–K10
  mutation kills, zero-authority proven by mutation before merge. No HK
  discovery / CA intel / challenger experiments before shadow-contract is
  merged + verified.
---

# HK + Canada Prophet revamp

Execution authority for this workstream is the hardened packet at
`research/PROPHET_HK_CANADA_REVAMP_EXECUTION_PACKET_2026_08_18.md` (six research
passes + hardening; research phase CLOSED). The packet carries the frozen
diagnosis (HK = candidate-recall starvation; Canada = semantic-authority
corruption), the non-negotiable laws, hard STOP conditions, the wave graph, and
the do-not-redo register. This record tracks state; the packet is not
duplicated here.

Sequencing law: repair truth → repair measurement → create shadow substrate →
accrue → compare → promote. First implementation wave is Canada truth repair
(CA-TRUTH), not a new model.
