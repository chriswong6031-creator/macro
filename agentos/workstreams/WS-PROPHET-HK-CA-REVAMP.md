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
    status: done
    pr: 6178
    merge_sha: fc5282f438fb7a9566ff650961fc6ea0381e7019
    depends_on: [ledger-era]
    completion: >
      MERGED fc5282f438fb 2026-08-21 (PR #6178, sweeper on concluded-green;
      origin/main bytes verified over all 9 owned files). Contract frozen as
      research/PROPHET_SHADOW_CONTRACT_V1.md after TWO Opus adversarial
      rounds with EXECUTED mutation kills (round 1 failed the draft — 5
      merge-blocking incl. the false HK isolation-by-ordering claim; round 2
      MERGE-BLOCKED the build — B1 curated-scope closure red + 6 major, all
      re-killed after fixes; K-suite K1-K14 + positive-control/non-vacuity/
      static-fence clauses; 43 tests). Stores
      data/prophet_shadow/{hk,ca}_{rank_pairs,discovery}.parquet; challenger
      registry EMPTY (registry_state log lines are the liveness signal);
      zero authority proven by executed mutation (byte-identity + repo-wide
      static fence + write-surface fence); prospective collection can begin
      by registering a challenger with zero schema migration. Design DEC:
      DEC:PROPHET-HKCA-SHADOW-IS-A-SEPARATELY-KEYED-LANE. do_not_redo +
      danger_areas in agentos/handoffs/PROPHET-HK-CA-REVAMP-2026-08-21.md.
      POST-MERGE SOL CORRECTION (2026-08-22, this wave's FINAL closure —
      supersedes PR #6187's closure for the registration surface): Sol's
      post-merge review found CHALLENGER_REGISTRY was keyed by definition
      ALONE and write_shadow iterated every registration regardless of
      market — the first real registrant would have executed in BOTH lanes.
      Repaired in the market-scope PR (this record's amending PR): registry
      re-keyed (market, definition); register_challenger(market, ...) with
      fail-loud ValueError; _registrations_for(market) selection seam;
      four-state POST-GATE registry_state ladder (+no_challenger_for_market;
      reentrant_refused pre-gate); per-registration failure isolation with
      truthful written counts; market-scoped write-surface fence; kills
      K15-K20 + reentrancy/malformed-key/overwrite/cross-market-collision
      tests (52 total), incl. TWO executed mutation arms (market-blind seam;
      error-state collapse) proven to kill. Contract §4 rewritten
      trust-bounded ("structurally incapable" was falsified by a
      reentrant-challenger probe; registered challengers are trusted
      reviewed code, not a security boundary). Adversarial round: Opus
      reviewer MERGE-BLOCKED with D1-D10, all repaired and re-killed.
  - id: hk-discovery
    title: HK candidate-recall shadow
    status: done
    depends_on: [shadow-contract]
    detail: >
      HK-DISCOVERY-SHADOW (Sol commission 2026-08-22): first real challenger
      hk_discovery_v1 registered via register_challenger("HK", ...,
      discovery_fn=...) in build_hk_library, downstream of the
      hk_standouts.json persist. Seven deterministic origins (washout_reclaim,
      leadership, ripening [uncapped, cap=10**9], aged_turn [bare ran_admits],
      blocked_signal [bare veto_admits + VETOED_MAX_SESSIONS staleness bound],
      hk_native_onset(southbound), ah_dislocation [twin-only, missing≠zero]);
      A-twin lead honestly ABSENT (censused not-present; no new alpha
      machinery). First real availability read: 6-state fail-closed ladder,
      read-availability explicit (placement/knife/extension whole-read
      unavailable => never ENTRY_OPEN). Sol pre-settlement repair 2026-08-22:
      the merged #6226 code defaulted OMITTED availability flags to available
      (tests asserted the default) — repaired so ENTRY_OPEN requires all
      three flags explicitly True; omitted/None fails closed to
      UNAVAILABLE_DATA `…_unavailable(unstated)`; executed omission-mutation
      arm kills four named tests. Freshness via per-market receipt
      data/prophet_shadow/<mkt>_discovery_receipt.json written by write_shadow
      only for markets with >=1 registration (lawful-zero distinguishable from
      stale/error/absent); sole reader check_hk_discovery_freshness on the HK
      session clock, warn-only, deliberately NOT in _ARTIFACTS (zero-authority
      store must not page ops). Opus adversarial round MERGE-BLOCKED with
      F1-F13; all adjudicated + repaired (R1-R11), 120 targeted tests green,
      6 executed mutation arms. CLOSED 2026-08-23 with production receipts:
      merged 82dc19ff6bbf (#6226) + Sol fail-closed repair 882636757d24
      (#6227, both bytes-verified on origin/main, proof runs SUCCESS). First
      prospective production receipt landed EARLY — Saturday 08-22 asia-close
      (09:53Z, main commit 48ff25191c08) for HK session 2026-08-21: 139 rows,
      market=HK only, challenger_definition=hk_discovery_v1, deterministic
      "+"-joined origins in canonical order (6/7 origins fired; leadership a
      lawful zero this session), availability across 5 states incl. honest
      UNAVAILABLE_DATA missing_inputs(gate_verdict) and 6 ENTRY_OPEN,
      visible_to_user=False + published_authority=False on every row,
      first_seen_at prospective (09:53Z, pre-outcome); fresh receipt JSON
      registry_state "wrote_n_rows n=139", zero challenger_failures. That
      receipt predates the #6227 repair merge (13:04Z) — no contamination
      (production supplies all three availability flags; only the
      omitted-flag default was defective), and the repair is live before the
      next HK session (08-24). CA non-invocation proven on the first
      post-merge daily (run 32603557988, engine job 97120339605): log line
      "board_shadow(CA): registry_state=no_challenger_registered"
      (whole-registry-empty rung — the CA nightly is a separate process where
      build_hk_library's registration never executes; the per-market
      no_challenger_for_market rung is exercised in-process by K-D7), zero
      hk_discovery tokens in the CA lane, no CA file under
      data/prophet_shadow/ on main. site/factordata/hk_standouts.json
      structure unchanged (as_of=2026-08-21, no shadow tokens).
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
  - id: v37-canada
    title: "Presentation lane: Canada Stock Dashboard V3.7 functional completeness"
    status: done
    pr: 6416
    merge_sha: 41efeba82b0193dd9090c600567e0b551ad8dd98
    completion: >
      PROVEN_LIVE 2026-08-25 (entitled production matrix; record =
      research/STOCK_DASHBOARD_V37_CANADA_ACCEPTANCE_2026-08-25.md).
      Supersession law DEC:V37-SUPERSEDES-V36-ACCEPTANCE; review law = the
      three committed SOL_* V3.7 packets (composition reference is never
      semantic truth). Restored Track Record as Evidence & Record (moved
      .trk owner DOM), owner-native Act-Now lane vocabulary, group-action
      Expand Leadership, Sol-gate population law (no silent Top Picks→All).
      Residuals (mechanism/bytes-proven): exact-390 production pixel pass;
      final live-paint observation.
  - id: v37-hk
    title: "Presentation lane: HK V3.7 follower"
    status: done
    pr: 6433
    merge_sha: cbf615eaa89399ae2a1b40de9db94f583d6c37c2
    depends_on: [v37-canada]
    completion: >
      PROVEN_LIVE 2026-08-26 (entitled production matrix; record =
      research/STOCK_DASHBOARD_V37_HK_ACCEPTANCE_2026-08-26.md). Market-native
      follower under research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md: Featured
      cohort Top Picks (owner pv-featured, never positional), NO LIVE
      treatment (no HK per-ticker live plane), sector-only leadership joining
      Act-Now lanes + rotation rank/cycle-state, Southbound INTEGRATE ladder
      gated on the owner's sig-* materiality marker, Evidence & Record (moved
      HK trd), disclosure toggles for specialist desks. One residual:
      exact-390 production pixel pass (bytes + local-real-browser proven).
      Regional V3.7 rollout COMPLETE — Canada + HK both PROVEN_LIVE; US
      decoupled; China out of carrier.
next_action: >
  PRESENTATION LANE — V3.8 correction in flight on one Fable carrier
  (stock-dashboard-v38-hk-ca-fable-20260826-sol-001) under the frozen
  Action≠Leadership architecture (#6456 + DEC:V38-ACTION-IS-NOT-LEADERSHIP).
  HK V38-R1 PROVEN_LIVE 2026-08-27 (PR #6515, merge 5dad2bd41326, entitled
  production matrix in research/STOCK_DASHBOARD_V38_HK_ACCEPTANCE_2026-08-27.md;
  handoff PROPHET-HK-CA-REVAMP-2026-08-27-v38-hk). Next: V38-R2 Canada on the
  SAME carrier (restore at-rest action lanes, keep themes[].rank, remove
  traversal sector rank), then final HK+Canada V3.8 return to Sol. China is a
  separate later carrier; US stays decoupled and unauthorized (V4 B1→B2/B3→B4
  + reconciled Cell H prerequisites).
  INTELLIGENCE LANE unchanged: hk-discovery CLOSED 2026-08-23 with
  production receipts (wave entry). Next lawful waves: hk-intel
  (HK-NATIVE-INTEL, depends on hk-discovery), ca-intel, ca-pit — each needs
  its own commissioning decision. Standing follow-up: ≈2026-08-26 verify the
  CA board-ledger-era-empty warning self-cleared (ledger-era wave entry); if
  it persists once gradable current-era rows exist, investigate — never
  silence.
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
