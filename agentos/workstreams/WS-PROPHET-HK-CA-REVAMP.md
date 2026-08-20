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
    status: in_progress
    depends_on: [ca-truth]
    next_action: >
      Definition-scope the scorecard group metrics (n/n_buy/hit_rate_21d/
      by_group currently pooled all-era in engine/board_ledger.scorecard —
      only rank_ic is fenced); add an explicit historical_context block
      keeping the legacy pool queryable as labeled context; legacy-only
      ledgers (definition None) keep pooled behavior unchanged. Packet §7
      required tests + mutation kills. Consumers censused 2026-08-20:
      build_hk.py horizons table (scored-only), build_canada.py board_track +
      track_ledger.from_board_ledger_grade, prophet_governor status fields,
      build_hk_library status only.
  - id: shadow-contract
    title: Rank/discovery shadow substrate
    status: todo
    depends_on: [ledger-era]
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
  Land LEDGER-ERA (era-clean scorecard fencing in engine/board_ledger.py;
  spec in the ledger-era wave entry + packet §7). CA-TRUTH settlement receipt
  PASSED 2026-08-20 — receipt recorded in the ca-truth wave entry. No HK/CA
  challenger work before LEDGER-ERA lands.
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
