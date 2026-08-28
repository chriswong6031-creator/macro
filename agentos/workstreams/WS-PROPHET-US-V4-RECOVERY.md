---
key: PROPHET-US-V4-RECOVERY
title: Prophet US V4 — recovery, early discovery & intelligence graph OS
objective: >
  Migrate Prophet US from a late-confirmation board to an early-discovery,
  present-entry, intelligence-ranked research OS. Done means the Chairman opens
  Prophet V4 in production and sees: every owed session settled (or explicitly
  unavailable), early expert evidence before slow confirmation, deterministic
  server-authoritative entry availability where green means only ENTRY_OPEN, an
  explainable missing-aware intelligence rank inside availability lanes, a
  complete searchable All Candidates field with no producer cap, cohort-honest
  grading of every episode, and the frozen V3 algorithm accruing as
  us_prophet_v3_legacy_shadow on the same tape.
status: active
program: prophet-us
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: fable
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - research/prophet_v4/
  - engine/us_turn_watch.py
  - scripts/build_turn_watch.py
  - site/turn_watch/
  - app/prophet_lab.py
  - engine/prophet_lab/
  - tests/test_prophet_lab.py
  - tests/test_prophet_lab_api.py
  - tests/fixtures/prophet_lab/
  - engine/us_candidate_episode.py
  - engine/us_candidate_episode_intake.py
  - scripts/reconcile_us_candidate_episodes.py
  - data/us_prophet_rank/episode_inputs/turn_watch/
  - data/us_prophet_rank/episodes/
  - tests/test_us_candidate_episode.py
  - tests/test_us_candidate_episode_intake.py
  - tests/test_us_candidate_episode_reconciler.py
  - tests/test_us_candidate_episode_wiring.py
depends_on:
  - WS:PROPHET-US-AVAILABILITY
  - WS:LIVE-ENTRY-RADAR
  - WS:PROPHET-CONDITIONAL-FUSION
  - WS:GMI-THEME-GRAPH
  - WS:EARNINGS-INTELLIGENCE-OS
  - WS:STOCK-IDENTITY
  - WS:PROPHET-US-ENTRY-TIMING
  - WS:EVAL-OS-MEASUREMENT-LAW
decisions:
  - DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS
  - DEC:PROPHET-LAB-B5A-RECUT
  - DEC:PROPHET-B1-CANONICAL-EPISODE-BINDINGS
  - DEC:PROPHET-D5-PRESERVES-CONTEXT-VECTOR-AND-SEPARATES-EVIDENCE-AUTHORITY
landmines:
  - "THE OUTAGE was LIVE at 0A (2026-08-17) and still unresolved at the 0B pin
    (2026-08-18T00Z: source_asof=2026-08-13, 206 plans). That historical fact is
    preserved. A1 is now RESOLVED by adoption of A1R #6320 plus the ordinary scheduled
    run 32786919396 and private served-byte proof on 2026-08-25. Exact receipts and the
    unrelated late Marketing cancellation boundary are indexed in
    agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-25-a1-acceptance.md."
  - "Prophet index top-level asof is WALL-CLOCK (DSC:PROPHET-ASOF-IS-WALL-CLOCK);
    freshness = source_asof + per-plan cohorts. Run conclusions decouple from Prophet
    delivery in both directions (DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET)."
  - "Pages can diverge from git in BOTH directions: designed conservatism
    (daily.yml:5046-5092, Pages lags one cycle) AND the measured 08-16 violation
    (run 31913143619 — Pages served the first v3 board git never got; mechanics
    unresolved from source). Production is the VPS, not Pages."
  - "The served board and the plan book have different gates: build_stock_library.py
    writes us_standouts.json directly; prophet_bridge.select_candidates() is a
    downstream consumer that refuses buy_soon. FOUR stage derivations disagree on the
    page (CURRENT_STATE §8). One server contract is B3's job."
  - "PAID BOUNDARY (scoped, 0B): #5840 merged the ranked-board server-side split
    (free shell + premium remainder; PROVEN_LIVE at the 0B pin — VPS premiumdata 401,
    3-row anonymous shell, render receipt 5232c4c4). Per #5840's OWN scope, Act-Now,
    .topsetups, ran, and theme-tape member names REMAIN DOM-gated — residual
    commercial-boundary debt. Do not write 'all Prophet anonymous leakage fixed'."
  - "Vocabulary collisions: Radar G0/C1-C5 vs Fusion arena rungs C1-C5 vs
    prophet_arena C0-C7 execution policies vs audit C0-C4; two same-named 'arena'
    systems; _v2 paths are SCHEMA versions, not the v2 ranker era; two 'board history'
    stores. Disambiguation table: CURRENT_STATE §9 — binding on every handoff."
  - "TURN WATCH is owned by this WS and its canonical artifacts are current at
    data_session=2026-08-24 after the accepted A1 natural run. The page is still NOT
    BUILT and the engine copy still has zero template consumers; artifact freshness is
    not B5B product proof."
  - "MP-1 (research/migration_packets/MP-1-prophet-board.md) is design-ratified with
    all spawn gates satisfied and NOT executed — B5/E2 build against it; its
    population re-source must be checked against DNR:KILL-PROPHET-POP-MERGE first."
  - "QLedger's control leg has never been populated on any of 46,630 claims
    (DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG); the plan ledger has no
    benchmark column. Do not describe V4 grading as control-matched until wired."
  - "Radar W4 activation proof is structurally owed (operator arm of
    ENTRY_RADAR_LIVE_ENABLE); B-15..B-19 dispositions post-#5370-heal are UNKNOWN —
    B2 opens with the matrix, do not assume the heal closed them."
do_not_redo:
  - "D5 v1 does NOT mutate or widen engine/us_context_vector.py; Context Vector is a
    read/reference-only PIT history/research substrate for D5."
  - "An unbuilt D5 adapter emits no evidence-family envelope. Adapter readiness may accrue
    outside evidence_families[], but missing/unbuilt is never zero or neutral."
  - "Runtime D5 requires the owner-issued canonical prophet.candidate_episode/v1 from B1.
    Never alias mastermind.live_entry_episode.v1 or mint ticker/date surrogate episodes."
  - "Do not read Earnings decision-time evidence through read_event_workspace /
    read_current_event_workspace. They resolve the CURRENT generation and take no as-of
    argument, so they present post-cut corrected values as decision-time belief while passing
    the contracts stated admissibility test. Decision-time access is
    read_event_source_revisions / read_all_event_source_revisions only."
  - "Do not admit an Earnings revision on source_available_at alone. Admission is the
    CONJUNCTION source_available_at <= cut AND observed_at <= cut, because the owner enforces
    only observed_at >= source_available_at (events.py:249-252), so a filing available before
    the cut but observed after it is a legal state and admitting it is lookahead. That case is
    NOT_CAPTURED_AT_DECISION; a null or unknown admission clock is UNKNOWN, never a silent
    skip. See CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md A7."
  - "Do not spend a PR removing the bridge candidate cap: N_CANDIDATES=12 survives
    only as an OVERRIDDEN DEFAULT (prophet_bridge.py:146,1147) — production passes
    n=None (:4127; daily.yml:2270). A grep hitting the constant does not contradict
    this; observed narrow boards come from the admission gate chain, not a cap."
  - "Do not widen Conditional Fusion PR-3B (outcome-blind LOFO + member census, its
    own fresh session) into availability/Radar/lifecycle/V4-UI work — V4-E1 consumes
    the ACCEPTED registry after PR-3D."
  - "Do not build a second cross-family ranker, second theme graph, second earnings
    store, second forward grader, second publication truth, or a rival identity
    stack (masterplan §6.4 reject list; canonical owners in
    research/prophet_v4/CONTRACT_AND_OWNER_MAP.md)."
  - "Do not flatten Radar expert identities (G0/C1-C5) into one entry_signal boolean;
    entry-detector fusion is Radar's reserved F1_FUSION slot."
  - "Do not synthesize the missed Aug-14 session from later knowledge — exact
    reconstruction from Aug-14-knowable data or an explicit unrecoverable receipt."
  - "Do not replay US 2026-08-14 again. DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT
    authorized one PIT reconstruction; A1R #6320 executed it, and natural run 32786919396
    absorbed it. Reconstructed rows remain unmarked and this authority does not extend
    to data-defect windows or a second replay."
artifacts:
  - research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md
  - research/prophet_v4/PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md
  - research/prophet_v4/FABLE_HANDOFF_PROPHET_US_V4_0A_2026-08-17.md
  - research/prophet_v4/CURRENT_STATE_2026-08-17.md
  - research/prophet_v4/CAPABILITY_LEDGER.md
  - research/prophet_v4/ARCHITECTURE_FREEZE.md
  - research/prophet_v4/CONTRACT_AND_OWNER_MAP.md
  - research/prophet_v4/D1_D5_READINESS_RULING.md
  - research/prophet_v4/B1_NATURAL_ACCEPTANCE_PROBE.md
  - research/prophet_v4/flagship_cells/CELL_F_D5_EVIDENCE_TRANSLATION_AND_TRAJECTORY_CONTRACT_2026-08-22.md
  - research/prophet_v4/flagship_cells/CELL_F_D5_ADVERSARIAL_REVIEW_AMENDMENTS_2026-08-22.md
  - research/prophet_v4/flagship_cells/CELL_F_D5_CANDIDATE_REFERENCE_COMPOSITIONS_AND_E1_BASELINE_2026-08-23.md
  - research/prophet_v4/flagship_cells/CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md
  - research/prophet_v4/SOURCE_RIGHTS_AND_COVERAGE_REGISTRY.md
  - research/prophet_v4/EXPERIENCE_REFERENCE_COMPOSITIONS.md
  - research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md
  - research/prophet_v4/V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md
  - agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-25-a1-acceptance.md
  - agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-25-b1-built.md
waves:
  - id: 0a
    title: "V4-0A — estate archaeology + architecture freeze. Merged #5832
      (squash ebce73b97288, 2026-08-17T13:18:55Z)."
    status: done
    pr: 5832
  - id: 0b
    depends_on: [0a]
    title: "V4-0B — post-0A records reconciliation (records only; scope narrowed by
      the 2026-08-17 Sol 0B handoff — no sibling record edits). Evidence:
      research/prophet_v4/POST_0A_RECONCILIATION_2026-08-17.md."
    status: done
    pr: 5847
  - id: a1
    depends_on: [0a]
    title: "V4-A1 — owed-session settlement recovery. Accepted by Chairman-authorized
      adoption on 2026-08-25 from A1R #6320 plus the ordinary natural-run and private
      reader packet; this is not a claim of separate Sol review."
    status: done
    next_action: >
      DONE. Preserve the exact receipt in
      agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-25-a1-acceptance.md; never rerun
      the Aug-14 replay. B1 is dependency-ready. A2/A3/A4 remain distinct waves.
  - id: a2
    depends_on: [a1]
    title: "V4-A2 — canonical settlement manifest (prophet.settlement_manifest/v1)"
    status: todo
    next_action: >
      ADOPT FIRST: before any spawn, map the accepted Availability/outage return onto
      this capability; if the sibling durable fix already satisfies it, close by
      reference — only the unresolved delta may become a V4 wave.
  - id: a3
    depends_on: [a1]
    title: "V4-A3 — atomic publication + split-brain fence"
    status: todo
    next_action: >
      ADOPT FIRST: same rule as a2 — map the sibling return (and #5840's premium-plane
      split) before spawning; only the unresolved delta becomes a V4 wave.
  - id: a4
    depends_on: [a2, a3]
    title: "V4-A4 — availability fire-drill week"
    status: todo
  - id: b1
    depends_on: [a1]
    title: "V4-B1 — canonical candidate episode registry (prophet.candidate_episode/v1)"
    status: in_progress
    next_action: >
      BUILT_PENDING_NATURAL_ACCEPTANCE. Merge the reviewed B1 code/wiring, then wait
      for the first ordinary scheduled nightly descendant. Accept only from its exact
      HEAD-referenced immutable generation, receipt/source hashes, workflow ancestry,
      and read-only canonical-reader proof. The B1 step itself is schedule-only and is
      skipped by daily workflow_dispatch; a manual dispatch, rerun, replay, report mode,
      or CI fixture is not natural acceptance. The Radar lineage input remains
      PROPOSED/STAGED_NOT_ARMED: only WS:LIVE-ENTRY-RADAR may freeze and validate its
      forward-projection contract and require exact immutable event_id before PRODUCED.
      Do not arm or manufacture that store here. D5 remains blocked until then.
  - id: b2
    depends_on: [b1]
    title: "V4-B2 — entry-event correction hardening (B-15..B-19)"
    status: todo
  - id: b3
    depends_on: [b1]
    title: "V4-B3 — orthogonal lifecycle contract (4 independent state fields)"
    status: todo
  - id: b4
    depends_on: [b2, b3]
    title: "V4-B4 — deterministic buyability/chase firewall (prophet.entry_availability/v1)"
    status: todo
  - id: b5a
    depends_on: [0a]
    title: "V4-B5A — Prophet Operator Lab (LAB-0 recut of b5, Chairman commission
      2026-08-18, wave-graph ruling 14, DEC:PROPHET-LAB-B5A-RECUT). Operator-only
      LIVE|LAB observational surface: read-only projection of canonical Radar output
      (six Lab boards) over the Prophet page + MP-1 shell migration. ZERO Prophet
      authority — read/filter/join/decorate only; no B3/B4 dependency. Contract:
      research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md. Child lanes:
      R-LAB-1 (= Radar W4.1, executes under WS:LIVE-ENTRY-RADAR), D-LAB-R5 (fresh
      independent RIG R5 — note R4 reference is committed but carries NO approval.yml;
      R4 was a closure pass, 10 blocking findings in
      research/reference_integrity/prophet-board-5514-r4/R4_CLOSURE_LEDGER.md),
      P-LAB-API, P-MP1-SHELL, P-LAB-UI. Shipping B5A completes NEITHER b5b NOR b6.
      DAY-2 STATE (2026-08-19): R-LAB-1 DONE (Radar W4.1 #5929 squash 9ef200f +
      commissioning-prep #5995 squash 85d651bc5bbb, live-verified via /api/health
      commit match; W4 arming stays an OPERATOR act per
      research/prophet_v4/P_LAB_COMMISSIONING_NOTES.md). P-LAB-API DONE (#5928
      squash 4295c05; /api/prophet/lab/v1 live, 401 fail-closed). D-LAB-R5 DONE —
      R5.3 APPROVED: approval.yml minted at frozen dcbea7cd
      (research/reference_integrity/prophet-board-lab-r5-1/, two-pass independent
      dual-critic, author excluded). R4-composition C8 pass COMPLETE (#5990 squash
      2313bdb, verdict REVISE + rulings b1/b8/n1); repairs C8-A/C8-B MERGED
      (#5998 squash fa9ceeb, 98/98 verify_r4); MP-1 Amendment 1 MERGED (#5994
      squash a3c3b69); C8-C DS-PR #6011 in flight (independent review MERGE-SAFE,
      pre-merge repairs applied; commissioning session merges by hand — never
      armed). P-MP1-SHELL gated on: #6011 merged + G-D coverage re-measured at a
      post-#6006 nightly payload (08-19 library collapse was a #5980 partial
      build; heal #6006 squash 0de8b86 merged 2026-08-19T20:07:23Z; groundwork
      branch claude/p-mp1-shell at 3f43864e41ce, no PR). P-LAB-UI after the
      settled shell + API, per the day-2 directive §7.
      DAY-3 STATE (2026-08-20, Sol Day-3 directive): SEQUENCE CORRECTED — the
      frozen LAB-0 §6 order is P-LAB-API -> R-LAB-1 -> Radar live commissioning
      -> P-MP1-SHELL -> P-LAB-UI; the day-2 handoff's shell->UI->commissioning
      ordering is SUPERSEDED. Gate A (G-D) PASS: measured at blob 251b9351 (the
      post-#6006 publication 0b0c296f, byte-identical at tip) — frozen Reading A
      (available/(available+blocked_data), not_applicable:plan_closed excluded
      per producer law) = 237/237 = 100.0000%, blocked_data 0; gross-row Reading
      B = 237/262 = 90.46%; ALL plausible readings clear >=90%. BINDING READING
      ADJUDICATED = Reading A (uniquely reproduces MP-1's literal 225/225).
      Do NOT wait for another nightly to re-measure — measure the CURRENT
      artifact (the day-2 'tonight's nightly' wait is CLOSED). Gate B (Radar
      commissioning) BLOCKED-ON-OPERATOR: W4 was already armed 08-18 by a prior
      operator; 215 armed passes ALL refused (160 in-window 'no_pack') — the
      08-19 pack builder store-gate red self-resolved, but four config blockers
      remain: B2 writer has NO spool destination (live env lacks R2 creds AND
      spool dir), B3 same-host split-brain (API env reads R2
      mastermindx/live_flow/entry_radar_events; writer resolves to nothing),
      B4 PROPHET_LAB_OBSERVATION_BASELINE_PATH absent from the API env, B5
      ENTRY_RADAR_SLICE_DIR unset (path /opt/terminal/terminal/public/data now
      VERIFIED live: 5.7G, 44,436 entries). Repairs are STAGED (systemd drop-in
      referencing the API env file — no credential values handled — + two path
      appends); the harness permission boundary denies remote production config
      mutation from any lane, so applying them is an OPERATOR act; receipts:
      /var/lib/macro-live/state/prophet_lab/commissioning_receipt_2026-08-20.json.
      Baseline NOT minted (CLI correctly refused: zero spooled passes — never
      self-baseline). P-MP1-SHELL: bounded prep MERGED #6049 (1ccf7fe8bdba —
      §8a stance projection plumbing unwired, pv_card parameter byte-parity
      proven, count plumbing, suites wired into engine-render-guards); CENTRAL
      ACT OWED on a Sol referral — MP-1 is silent on the W-L1 collision (the
      pinned provisional-board surface repaints the same #us-standouts .nbgrid
      the packet re-sources; research/WL1_PROVISIONAL_BOARD_DESIGN_SPEC.md).
      DS-PR #6055 MERGED (d78121d6459c: .skel + .mx-error ported from the
      specimen, additive-only, drift-guarded) discharging the V-B4 primitive
      gap. Heal #6053 MERGED (zh-rebind test re-pinned to the C8-C structural
      flip — the test-pinned-retired-literal trap, third instance). The five
      test_hk_board_ui reds were NOT fixture drift — #6029 proved a sparse-CI
      checkout artifact (day-2 diagnosis STRUCK, chip dismissed). P-LAB-UI NOT
      started (directive §9).
      DAY-4 STATE (2026-08-20, Sol Day-4 directive — CLOSURE): W-L1 RULED by Sol
      (option b, MP-1 §13 row CLOSED, records #6064). GATE B COMMISSIONED under
      the Chairman's explicit admin grant: env repairs applied (drop-in
      EnvironmentFile + slice dir + baseline path + macro-api restart), a NEW
      code blocker isolated and healed same-day (#6095: live_eval._quote_ts
      only read 'ts' while the loader normalizes to 'ts_ms' — a healthy
      2,089-symbol snapshot darked the whole probe set 0/2979), two bounded
      resource rulings on the evaluator unit (MemoryHigh 768M/Max 1G;
      TimeoutStartSec 570 — first full pass is cold-I/O ~10min), first genuine
      in-window envelope 115834-entry_radar_live.json (240 usable quotes, 54
      transitions, 27 events, 237 basis audits 0 mismatch), baseline minted
      LAWFULLY 16:10:41Z (dry-run first, backend r2, after real passes),
      post-mint service cycles self-sustaining (~5min cadence) with
      observation_class live_forward=49 / retrospective_seed=150, pools
      separate, coverage_verified true. Receipt (verdict COMMISSIONED):
      /var/lib/macro-live/state/prophet_lab/commissioning_receipt_2026-08-20.json.
      P-MP1-SHELL CENTRAL ACT MERGED #6076 (squash 31ca4971ba4a) after THREE
      build rounds + THREE independent adversarial review rounds (final
      certification MERGE-SAFE; §8b three-part record: mechanism PASS /
      boundary WITHHELD pending the B1 escalation / candidate split
      conformant): plan-book grid re-source in published plans_sort_key order,
      §4b ladder verbatim, ?life= URL law, W-L1 neutralization per ruling (b)
      (data-mp1-grid marker + :not() choke point; poller+stamp byte-identical),
      §8a stance wiring, §10 states (dense clause DEFERRED — no plan-book
      table view exists yet), Candidates shelf gated at the standing 1/3/full
      idiom, fail-closed gate config, non-US byte parity proven at merge-base.
      CRITICAL ESCALATION B1 (routed to Sol + operator,
      DSC:PROPHET-INDEX-PUBLIC-R2-TWIN): the FULL plan book is anonymously
      world-readable at the public R2 dev URL (200/2.16MB/262 plans with
      entries/zones/targets/invalidations/theses) while the origin 401s the
      same path — a LIVE pre-existing leak that the shell's paid boundary now
      sits on top of. Remedy sketch in the DSC (redacted public stub for the
      rescue watchdog + credentialed server-side reads for the Terminal's
      /api/flow route + delete the public object; all consumers are
      server-side). Post-merge render pending at the merge SHA; browser matrix
      + live verification follow the bake. Follow-ups owed: cadence finding
      for the Radar owner (cold-start pass exceeds the 5-min tick), N1 dead-JS
      heal, N2 macro.html dead CSS, remote-route proof (site-full token).

      DAY-5 STATE (2026-08-21, Sol Day-5 directive — B1 CLOSURE): Day-4
      accepted with one security gate. B1 R2-PLANE PRODUCTION-CLOSED in one
      session per DEC:B1-PROPHET-PUBLIC-SPLIT — census (2 scouts), health
      contract prophet/health.json (prophet.public_health/v1, six-field
      allowlist), producer closure in daily.yml (health-only publisher +
      self-healing tombstone + guarded_put_object + boundary/mutation tests),
      consumer rebinds (rescue→health with R2_HEALTH_LAG semantics;
      marks→canonical git; Terminal prophet_idx fail-closed #439; the
      Terminal's canonical backend /api/hub/prophet CREATED in
      app/prophet_lab.py — it had never existed, the Prophet tab was served
      entirely by the anonymous R2 fallback), object DELETED (anon 404; health
      200 allowlist-verified; origin 401; edge 401; internal 200/269 plans;
      rescue dispatch run 32451390875 SUCCESS post-merge). Macro PR #6158
      (3a0d1eaf0bb3) + terminal PR #439 (b913382b778d). Same-key bridge
      SKIPPED on the record (Terminal was R2-only in production; twins still
      public on git/Pages — a bridge broke product while reducing zero
      exposure). DECISIVE CENSUS DISCOVERY
      (DSC:PROPHET-BOOK-PUBLIC-GIT-TWIN): the canonical repo is PUBLIC —
      raw git, anonymous clone, and the nightly-deployed GitHub Pages live
      mirror all still serve the full book + premiumdata anonymously, so the
      §8b BOUNDARY PASS is NOT issuable; reduced to ONE Chairman/Sol ruling
      (repo visibility + Pages premium-stripping + four dependent
      migrations). P-LAB-UI NOT commissioned (Sol's own gate requires §8b
      PASS). Also minted DSC:RADAR-SPOOL-PUBLIC-R2 (spool anonymously
      readable — Radar-owner escalation). Residual chores: tonight's
      stays-gone receipt (tombstone-enforced), M1 flow-ops-wt pin advance
      (marks stale during RTH until then), Terminal deploy of #439, site-full
      token proofs, pixel crops. CORRECTION 2026-08-25 (B1-A): the 'M1
      flow-ops-wt pin advance' chore must NOT be read as authority to advance,
      reset, clean or reconstruct that checkout. Its detached dirty pin at
      a5f79c83 is the deliberate ENGINE the merged #6363 publisher lanes consume
      via PYTHONPATH/WorkingDirectory/.env; normalizing it destroys the governed
      runtime. The marks lane was separately migrated to ~/prophet-marks-runtime
      on 2026-08-23 and no longer depends on that pin. See
      DSC:M1-PUBLISHER-RUNTIME-IS-HOST-LOCAL-AND-DELIBERATELY-PINNED and
      DEC:B1A-M1-RUNTIME-RECOVERED-NO-SUPERSESSION. Handoff:
      agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-21-lab-day5.md."
    status: in_progress
  - id: b5b
    depends_on: [b3, b4]
    title: "V4-B5B — authoritative Early Entry Desk MVP (TURN WATCH finally visible;
      retains B3/B4 deps; adopts B5A plumbing instead of rebuilding — LAB-0 recut)"
    status: todo
  - id: b6
    depends_on: [b2]
    title: "V4-B6 — Radar observation-only activation (full-RTH-session proof)"
    status: todo
  - id: b7
    depends_on: [b6]
    title: "V4-B7 — Radar production UI + Prophet integration (executes Radar W9 under
      Radar ownership). 0B note: Radar W6 code merged (#5834, research_priority.v1 —
      ACCRUING attention ordering, commissioning owed, zero Prophet authority); W8
      (#5737) still open/reference-only; W9 absent. b7 inherits Radar's W9 deps."
    status: todo
  - id: c1
    depends_on: [b1]
    title: "V4-C1 — cohort-separated all-candidate ledger"
    status: todo
  - id: c2
    depends_on: [c1]
    title: "V4-C2 — us_prophet_v3_legacy_shadow (activates at cutover)"
    status: todo
  - id: c3
    depends_on: [b5b]
    title: "V4-C3 — operator decision instrumentation (keys on the authoritative desk
      b5b per LAB-0 ruling 14)"
    status: todo
  - id: d1
    depends_on: [0a]
    title: "V4-D1 — theme-source and identity census. DONE 2026-08-18: master census
      research/prophet_v4/D1_THEME_SOURCE_AND_IDENTITY_CENSUS_2026-08-18.md + 9
      machine artifacts in research/prophet_v4/d1/. Headlines: C6 thematic gap =
      2,368/3,253 (73%); graph company plane is ticker-string-keyed (D2's repair);
      two live graph data defects (GOLD reused-ticker, IBIT ETF-as-company); Citrini
      OPERATOR_HELD_ONLY; Theia DEC stands; 5 rights decisions routed."
    status: done
    pr: 5859
  - id: d2
    depends_on: [d1]
    title: "V4-D2 — canonical ontology + probation mapping, executing INSIDE/WITH the
      GMI lane. RECUT by Sol 2026-08-18 into bounded child PRs D2A-D2E (one giant PR
      rejected); Sol AMENDED the D1-generated handoff's Gate 1: exact
      issuer/security/listing identity = the Mastermind Data OS identity spine
      (lib/dataos/identity.py + data/reference master/aliases), NOT stock_identity;
      GMI keeps its co:market:symbol#epoch topology ids (KNOWINGLY-DIFFERENT per
      config/identity_seams.yml); the bridge projection is the seam. Child D2A
      (identity authority bridge: gmi.identity_resolution/v1 sidecar + reader +
      guard, frozen contract research/prophet_v4/d2/D2A_FROZEN_CONTRACT_2026-08-18.md)
      MERGED 2026-08-18 (#5894). Child D2B1 (issuer authority hardening: economic
      issuer axis via SEC-CIK evidence — GOOG/GOOGL, FOX/FOXA, NWS/NWSA one issuer
      each; era issuer_semantic_correction_v1 with durable migration receipts; typed
      issuer_state refusals; reference.issuer_master + issuer_migrations datasets;
      receipt authority decomposition; nightly refresh seam in daily.yml collect;
      frozen contract research/prophet_v4/d2/D2B1_FROZEN_CONTRACT_2026-08-19.md)
      shipped as #5965 — live-refresh production proof gated on the first
      post-#5936 listing snapshot (>2026-08-10). Child D2B1-R1 (Sol amendment
      2026-08-20: the transition race fired on the first natural nightly —
      duplicate SEC:US-XNYS-VMRK minted for the EQR→VMRK rename; PROVEN, then
      repaired: dated RenameEvent from SEC 8-K 0001140361-26-033377, supersession
      onto the continuing EQR identity via new security_state/superseded_by axis +
      security_migrations receipts + authored SECURITY_SUPERSESSIONS registry,
      AVB typed exit, general pending-transition fence with typed refusals;
      contract research/prophet_v4/d2/D2B1_R1_FROZEN_CONTRACT_2026-08-20.md +
      AMENDMENTS §1-§3) shipped as #6082 — Sol's D2B2 gate = the next natural
      refresh proving one canonical identity survives (see the R1 handoff for
      the expected first-night provenance churn). D2B2-CN-HK AUTHORIZED
      2026-08-20 (Sol adjudication DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK,
      resolving the China Alpha pr0d owner collision): exactly one bounded
      child admitting the source-supported China/HK listing population into
      the canonical master (or typed refusals for every target) and
      re-deriving the GMI identity projection — frozen contract
      research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md; start
      pin re-censuses NOT_IN_MASTER by market (the 1,868 figure is
      observation, not contract); China wave pr0d is consumer-verifier and
      adopts the child's result by reference. The full D2B2 US/Canada
      backlog, D2B3 (GMI GOLD/B + IBIT corrections), D2C (PIT vintages), D2D
      (ontology/probation), D2E (rights/acceptance) remain NOT authorized —
      Sol reviews after each child returns. D2B2-CN-HK BUILT_NOT_PROVEN
      2026-08-20: start-pin census 1,021 cn + 147 hk (target N 1,168);
      admitted via the EXISTING canonical builder (no lib/dataos edits, no
      new evidence class, no CN/HK issuer grouping) using committed
      primary-source evidence (CN: CNInfo data/china_filings/filings.parquet,
      984/1021 = 96.4%; HK: SFC+HKEX data/hk_shorts/{positions,turnover}.parquet,
      147/147 = 100%; 37 CN refused, named in the receipt, no silent drop);
      GMI sidecar re-derived with zero code changes to
      engine/theme_graph/identity_resolution.py (already market-agnostic);
      US coverage byte-identical (702/533/2/1 unchanged); 5 hostile fixtures
      on real committed data (A/H ICBC, renamed 300223, SOE-naming-collision
      601988/601601, unresolved issuer, alias-only vendor id — CN/HK never
      resolves via rule 5, only rule 6); PR #6116, squash-merged as
      ed28d0d992a144aec5f0ef2616024e3e32d83b1a (immutable merge SHA). China
      pr0d wave adopts this result by
      reference (WS-CHINA-ALPHA-INTELLIGENCE.md). Done requires a natural
      production nightly proving source -> master -> GMI projection with a
      recorded run id and the measured CN/HK resolution delta, per Sol's
      completion law. Sol accepted the D2B2-CN-HK implementation 2026-08-20
      (BUILT_NOT_PROVEN); proof rides the first natural nightly containing
      ed28d0d992a1 per the China WS pr0d entry. D2B2-CN-HK NATURAL-PROOF
      ADJUDICATION (Sol, 2026-08-21): DONE / PROVEN_LIVE. Sol independently
      extracted the required production receipt from the completed natural
      nightly stages (the first nightly containing #6116 squash
      ed28d0d992a144aec5f0ef2616024e3e32d83b1a). Receipt: canonical
      security-master refresh verdict REGENERATED (identity inputs
      advanced); natural master receipt generated 2026-08-21T01:17:00; US
      canonical coverage 702/712 with 10 unresolved; CN canonical admission
      survives 984/1021 (96.4%) with 37 typed primary-source refusals; HK
      canonical admission survives 147/147 (100%); the regenerated master
      was published to main BEFORE the engine pulled refreshed main;
      subsequent natural GMI/theme-graph build stamped 2026-08-21T03:47:15Z
      lane=nightly; GMI state counts RESOLVED 1833 / NOT_IN_MASTER 737 /
      UNSUPPORTED_MARKET 233 / DEFERRED 1 / ENTITY_TYPE_CONFLICT 1; 1833 =
      702 US + 984 CN + 147 HK, exactly the frozen D2B2 population. The
      canonical path primary evidence -> DataOS security master -> GMI
      identity projection is proven through the natural production topology
      (nightly run 32426513915). No D2B2 repair authorized or required.
      D2B2-US BUILT_NOT_PROVEN 2026-08-21 (Sol commission; frozen contract
      research/prophet_v4/d2/D2B2_US_FROZEN_CONTRACT_2026-08-21.md +
      AMENDMENTS §1-§2 = 16 adjudicated rulings, 3-pass opus review ending
      PASS): start-pin 0c097d0f9621 re-census target_n 533 U.S. NOT_IN_MASTER
      (seed-scope gap — load_universe's 710 curated keys never wired to the
      1,238 GMI U.S. company nodes); admitted via tagged GMI-U.S. seed intake
      through the EXISTING resolution/mint path (R1 fence live; structural
      etf/test_issue/is_preferred eligibility on GMI-ONLY targets — legacy
      curated keys never gated; closed EXCHANGE_MIC untouched; CIK mandatory
      fail-closed). +508 U.S. active rows (master 1,836 → 2,344; pre-existing
      rows byte-identical); us_gmi_admission accounting target_n 1,236 =
      resolved_total 1,210 + 25 named typed refusals (21 not_listed_no_cik,
      3 not_listed_cik_present, 1 unsupported_venue CBOE) + 1 disclosed
      FISV→FI duplicate-claim exclusion, invariant fail-closed in-build;
      resolved_not_rederivable discloses WBS/SATS (active rows the current
      rail snapshot cannot re-derive — resolved, never refusals). Sidecar
      rebake: us RESOLVED 702 → 1,210, NOT_IN_MASTER 533 → 25 (strict set
      equality with receipt refusals); cn/hk/ca/intl unchanged; GMI node
      ids/memberships untouched. PR #6190, squash-merged 2026-08-21T13:13:16Z
      as 71b4813266c1f52611dc0105ff62e1670ab68f66 (immutable merge SHA;
      post-merge fences proof SUCCESS incl. contract-delta; handoff
      agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-21-D2B2-US.md). DONE
      requires the next natural production nightly showing source → master →
      fresh GMI projection with measured before/after U.S. counts. D2B2-Canada
      (167 ca nodes) remains NOT authorized — Sol reviews after this
      child returns.
      D2B3 CONTRACT-FROZEN 2026-08-21 (Sol commission; archaeology + freeze
      ONLY — the commission's precondition gates implementation on D2B2-US
      PROVEN_LIVE, and at freeze the Aug-22 Data OS generation existed
      (receipt 2026-08-22T01:07:17, us_gmi_admission 1236/1210/0 natural
      steady state) but no natural GMI generation had consumed it yet).
      Frozen contract research/prophet_v4/d2/D2B3_FROZEN_CONTRACT_2026-08-21.md:
      GOLD reuse corrected by retiring the epoch-1 fossil node (retire_date =
      ratified break_date 2025-12-02 verbatim) + truncating its stale
      gold_miners edge via the EXISTING (edge_id, belief_time) lineage; IBIT
      corrected by retiring the company-kind node + ANNULLING its crypto_rails
      company edge (empty interval) + a deterministic bake-side etf-conflict
      mint refusal with typed receipt; retirement expressed in a NEW
      node_lifecycle.parquet sibling table (KEY=(node_id,computed_at), same
      append-only/latest pattern as capability) because nodes are write-once
      keep-first with NO existing retirement path — nodes.parquet rows stay
      bit-identical forever; ABX = generality control on the prior-node-ABSENT
      shape (no co:us:ABX exists; nothing is minted); #2 nodes NEVER
      pre-minted (live epoch law routes future evidence). Pre-implementation
      Opus design review returned FAIL; all findings adopted as AMENDMENT §1
      (re-frozen): belief_time is the RUN DATE so keep-first never protects a
      correction across days — the bake must stop COMPUTING corrected rows
      (post-pass node+edge suppression with typed receipts); derive_rows runs
      over the COMPUTED generation, so co:us:GOLD is ALREADY absent from the
      natural sidecar population (next natural gen: us DEFERRED 1 = B only —
      graders must not read that as regression); the live IBIT conflict
      counter lawfully drops to 0 post-correction while history stays
      append-only; additive ratified_at field makes the backdating guard
      implementable; retired-remint check receipts, never raises. Handoff
      agentos/handoffs/PROPHET-US-V4-RECOVERY-2026-08-21-D2B3-FREEZE.md.
      D2B2-US NATURAL-PROOF ADJUDICATION (Sol, 2026-08-22): DONE /
      PROVEN_LIVE. Production receipt recorded by Sol from the natural
      chain: Data OS generated_at 2026-08-22T01:07:17; GMI natural
      generation computed_at 2026-08-22T04:50:47Z (lane/mode
      nightly/nightly) consuming that master; reconciled U.S. generation
      RESOLVED=1210 / NOT_IN_MASTER=25 / DEFERRED=1 (B only, GOLD absent
      per D2B3 AMENDMENT §1 R-A2 population mechanics — not regression) /
      ENTITY_TYPE_CONFLICT=1; the daily engine run carrying that natural
      generation ran 02:26:06Z→05:56:19Z, after the Data OS generation
      existed. D2B3 implementation gate OPEN (Sol GO, 2026-08-22):
      implementing session executes the frozen contract + AMENDMENTS
      §1-§2 verbatim (amendments win over base prose); one Sonnet builder,
      fresh Opus review, merge = BUILT_NOT_PROVEN; DONE = next natural
      GMI cycle proving no resurrection, corrected current view, refusal
      receipt live, 1,210-resolved coverage non-regressed. STOP unchanged:
      no D2C/D2D/D2E/D3/D5/Canada."
    status: in_progress
  - id: d3
    depends_on: [d2]
    title: "V4-D3 — ThemeState consumption contract. Sol ADJUDICATED 2026-08-18
      (D2A commission §19): D1's merge-order recommendation ACCEPTED — GMI is the
      sole ThemeState owner and builds theme_state/v1 as W3B after d2 completes; d3
      is the Prophet-side consumption/join wave and V4 never builds a second state
      engine; engine/neuralweb/thematic_state.py is predecessor lineage W3B must
      explicitly reconcile/consume/supersede; Finviz/THS-derived state stays
      internal-only pending the routed rights decision. Future hard gate from D2A:
      a membership may contribute to security/issuer ThemeState only when its GMI
      node resolves through the exact identity bridge, or the feature explicitly
      operates at local-theme/node grain."
    status: todo
  - id: d4
    depends_on: [d3]
    title: "V4-D4 — peer and transmission features"
    status: todo
  - id: d5
    depends_on: [b1]
    title: "V4-D5 — V4 intelligence-vector contract (prophet.intelligence_vector/v1).
      Sol ADJUDICATED 2026-08-18 (D2A commission §19): D1's readiness ruling
      ACCEPTED WITH BOUNDARY — contract work may later proceed in parallel once Sol
      authorizes execution, but until d3 the theme_graph family status = ACCRUING,
      measured fields = null, contribution = none; no provisional theme score, no
      fake zero, no rank authority. Execution NOT authorized during D2A. Original
      ruling: research/prophet_v4/D1_D5_READINESS_RULING.md (no ticker-string joins;
      SPARSE coverage band is the honest scan-tier default). ARCHITECTURE RECONCILED
      2026-08-26 (PR #6275 amended, not superseded): the 2026-08-22 Cell F contract's
      epistemic core stands; three BLOCKING defects repaired in
      research/prophet_v4/flagship_cells/CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md —
      A7 binds Earnings decision-time reads to the revision-chain reader and FORBIDS
      read_event_workspace there; A8 binds decision_cut to B1-owned opened_at/opened_session
      and sets tradable_at NOT_ASSERTED until B4; A9 requires episode_ref to pin the B1
      generation_id. Runtime D5 stays gated on B1 natural-production acceptance (B1 is
      MERGED / BUILT_NOT_PROVEN as 878930b3b2f9)."
    status: todo
  - id: d6
    depends_on: [d5]
    title: "V4-D6 — earnings adapter. Premise updated 0B: EIOS E1P is LIVE for the
      golden AAPL FY2026 Q3 event workspace (#5842) and E2 is unblocked — but ONE
      golden event is not broad issuer coverage; d6 still waits on d5 and must not
      infer coverage from it."
    status: todo
  - id: d7
    depends_on: [d5]
    title: "V4-D7 — alt-data family adapters (one per family)"
    status: todo
  - id: e1
    depends_on: [b4, c1, d5]
    title: "V4-E1 — explainable deterministic V4 priority (extends Fusion registry
      post-3D). 0B note: Fusion PR-3B AND PR-3C (#5839) are merged; PR-3D remains the
      sibling acceptance boundary; V4 does not read/tune from the W3 forward race."
    status: todo
  - id: e2
    depends_on: [e1, b7, c2, a4]
    title: "V4-E2 — Prophet V4 primary experience + cutover"
    status: todo
  - id: e3
    depends_on: [c1, e1]
    title: "V4-E3 — listwise ranker challenger (shadow only)"
    status: todo
  - id: e4
    depends_on: [e3]
    title: "V4-E4 — conditional router/multi-head challenger (shadow only)"
    status: todo
  - id: e5
    depends_on: [d4, e3]
    title: "V4-E5 — temporal heterogeneous graph challenger (shadow only)"
    status: todo
  - id: e6
    depends_on: [e3, e4, e5]
    title: "V4-E6 — promotion gauntlet + V3 retirement ruling"
    status: todo
next_action: >
  B1 is BUILT_PENDING_NATURAL_ACCEPTANCE on its single reviewed carrier. Merge it,
  then wait for the first ordinary scheduled nightly descendant and validate the exact
  HEAD-selected immutable generation, receipt/source hashes, ancestry, and canonical
  read path. The B1 workflow step is schedule-only; do not dispatch, rerun, or replay as
  a substitute. Radar forward lineage remains PROPOSED/STAGED_NOT_ARMED until its owner
  freezes and validates an exact immutable-event relationship contract. D5 remains blocked;
  PR #6275 stays a contract-only carrier to reconcile only after B1 acceptance without
  losing its frozen D5 evidence terms. A2/A3/A4 and all other V4 waves remain separate.
---

## Context

Chairman-commissioned P0 (2026-08-17): Sol's masterplan
(`research/prophet_v4/PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md`)
freezes the V4 thesis — surface by emergence, gate by the trade available now, rank by
intelligence, explain the evidence, let the Chairman decide. This workstream is the
INTEGRATION umbrella: it owns candidate-episode intake, board lifecycle, deterministic
entry availability, product projection, and operator workflow. It consumes — and never
duplicates — the sibling owners: Radar (expert events), Stock Identity (identity
epochs/routing), GMI (theme graph/state), EIOS (earnings), Conditional Fusion
(cross-family ranking machinery), Availability (rescue plane), Evaluation OS/QLedger
(outcome labels).

## Scope boundary

Wave definitions and acceptance live in masterplan §21; dependencies, merge order, and
path ownership in `research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md` (its §4 rulings
govern every path shared with a registered sibling owner — engine/prophet_*.py belongs
to WS:PROPHET-US-ENTRY-TIMING and B2/B3/B4 execute jointly under it); nine numbered
architecture decisions in `research/prophet_v4/ARCHITECTURE_FREEZE.md` with the tenth
(wave dependencies/file ownership) frozen in the wave-graph doc. As each wave starts,
its owned paths are PROMOTED into this record's owns_paths (or the partner
workstream's) so the AgentOS collision detector can see them. Sibling wave
IDs (Radar W0-W9, Fusion PR-3x, GMI W3x, EIOS E0-E2) are never renamed by this program.
Future stores (candidate episode registry, availability artifacts, V4 rank projection)
enter `owns_paths:` when their waves create them — not before.
