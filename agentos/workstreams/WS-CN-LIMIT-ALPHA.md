---
key: CN-LIMIT-ALPHA
title: China limit-up alpha research
objective: >
  Establish whether mainland limit-up mechanics carry tradeable, gauntlet-survivable
  signal. Done = a promotion-grade verdict, or a recorded kill.
status: active
program: china-system
repos: [macro]
owner: fable
class: research
blast_radius: reversible
owns_paths:
  - research/cn_prophet_audit/
  - research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md
  - research/cn_limit/
ambiguity: scoped
waves:
  - id: W-P0
    title: Washout-onset charter + first lawful measurement (#5364)
    status: done
  - id: P-A1
    title: Descriptive Prophet-panel read (#5438, merged 2026-08-12)
    status: done
  - id: P-B
    title: Winners-only case decomposition, no comparison arm (#5521, merged 2026-08-14)
    status: done
  - id: P-B2
    title: Matched precursor discrimination (the preregistered comparison arm)
    status: done
    next_action: >-
      SHIPPED (PR #5615): prereg frozen before outcomes; 17/17 checks + probes;
      byte-identical runs. Verdict = NO DISCRIMINATOR at the preregistered bar:
      11 of 31 gated cells cleared every gate but the placebo calibration failed
      3/4 families — a calibration-governed null, mechanism = persistent-state
      placebo reproducibility (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT);
      MA200/QB/VZ placebo-clean with strong holdout-consistent structure;
      nothing rescued, frozen consequence applied unchanged. Do not rerun.
      Do not move its gates. Reopen path is P-B3, not a P-B2 rewrite.
  - id: P-B2-ACCRUAL
    title: Prospective PIT accrual for remaining class-C China Intelligence feeds
    status: done
    next_action: >-
      SHIPPED: separate keep-first hist stores for broker 金股, per-name margin,
      block trades, buybacks. report_rc already fixed by #5614 (not redone).
      Display snapshots unchanged. Zero scoring/Prophet authority.
      DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE. Evidence-start = first live
      asia-close refresh after merge (floor 2026-08-15); hist files do not
      exist until that run.
  - id: P-B3
    title: Persistence-robust certification
    status: done
    depends_on: [P-B2]
    next_action: >-
      SHIPPED (PR #5729): prereg sha256 prefix 75fb38e1e6b5aefe; freeze
      commit 6419ca5ed5744d562b7c22093b52065502f802f3; run head
      b473cad20da08a274a3c7914b2edec1827433783; receipts
      PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.{md,json}. Verify 19/19
      checks + 19/19 probes. Verdict = NULL=12, UNINFORMATIVE=8; zero
      CERTIFIED TIMING; zero CERTIFIED OCCUPANCY
      (DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE). P-B2 remains NO
      DISCRIMINATOR AT THE PREREGISTERED BAR. P-D is not opened and
      has no input from this construction. Do not re-run. Do not shop
      gates, floors, strata, cells, or headlines.
  - id: P-A2
    title: Prophet-panel inference battery
    status: todo
    depends_on: [P-A1]
    next_action: >-
      Accrual-gated by its own preregistration: >=120 distinct sessions AND >=2
      own_market_regime segments per stream before any inference row (earliest ~2027-02
      via v3). Partial peeks forbidden. R6 note (2026-08-19): runs under the R6
      freeze's authority precedence; a standout-panel research battery, never a
      substitute for the exact-plane R4 battery (wave M2-R4-BATTERY).
  - id: P-C
    title: Intraday / chip / auction footprints
    status: todo
    next_action: >-
      Reconciled under R6 (2026-08-19): intraday families
      (AUCTION_DEMAND_QUALITY, SEAL_CONTINUATION_STATE) live in the D-INTRADAY
      dormant branch of the R6 freeze §13.3 and unlock only on licensed
      auction/minute/order data plus a fresh P-C charter of its own era, behind
      DEP-EXACT. Seal anatomy never predicts the same first-board target
      (continuation/access only). Do not charter from this row alone.
  - id: P-D
    title: Conjunction stacking + scorer preregistration
    status: dropped
    next_action: >-
      SUPERSEDED 2026-08-19 by the R6 measurement architecture: conjunction and
      stacking evaluation happens only inside M2-R4-BATTERY → I1C-G6 under the
      frozen R4 preregistration (DEC:CNLI-MEASUREMENT-BEFORE-ORDERING,
      DEC:CNLI-NO-OUTCOME-AUDITION). No separate P-D scorer prereg may be
      chartered. P-B3 gave it no input; R6 closes the row.
  - id: R6-0
    title: Durable R6 final-freeze landing (records only)
    status: done
    next_action: >-
      SHIPPED with this record's PR: R6 canonical package landed byte-faithfully
      under research/cn_limit/ (architecture freeze, machine registry, Fable
      command packet, Grok bounded commissions, executive handoff index,
      artifact manifest — SHA-256s match the manifest); 13 DEC:CNLI-* rulings
      and 3 discoveries minted. Per the R6 proof matrix the required proof is
      merged-records discoverability on origin/main; no runtime diff shipped,
      no runtime proof claimed. R1-R5 source artifacts were not delivered as
      bytes to the landing session; they remain pinned by SHA-256 in the freeze
      Appendix C and the manifest.
  - id: P0-ST
    title: 2026 main-board risk-warning rule parity and replay (program P0)
    status: done
    depends_on: [R6-0]
    next_action: >-
      PROVEN_LIVE 2026-08-20. Repair merged as #6047 (squash 609d883506b3):
      era-dated main-board risk-warning band ±5%→±10% effective 2026-07-06 in
      engine/china_microstructure.py (MAIN_ST_BAND_WIDE_DATE) +
      config/cn_limit_rules.yml interval split, official-source receipts (SSE
      c_20260424_10816474; SZSE 深证上〔2026〕551号 arts. 3.3.13/10.9),
      boundary tests both venues, definition hash
      e0c70f39f62e7639355128644f872c4e992699524bbdca775f24f1e1ad45e4a4. Real
      asia-close production proof: workflow run 32348780228 (asia job SUCCESS
      2026-08-20T15:20Z on head e2ba19c17d73, a descendant of the merge)
      committed baf4cf7c9291 — microstructure.json as_of 2026-08-20 carries
      metadata.st_band_regime main_st_width_pct 10.0, packet widths {10,20}
      only, and the post-run store holds 60,610 event rows with ZERO at
      limit_width==5.0. Post-run replay: zero corrections required to any
      produced store; the refreshed ST snapshot (207 names, asof 08-20) grew
      the affected universe to {600079.SS, 600745.SS}, where the superseded 5%
      law would have written 17 phantom events on 600745.SS alone — the
      store's single real row (2026-07-20 failed_down_seal @10.0) matches the
      lawful arm exactly, and the non-vacuity guard flipped on the real
      divergence. Receipts: P0_ST_BAND_REPAIR_RECEIPT_2026-08-19.{md,json}
      (frozen build-time) + P0_ST_PRODUCTION_PROOF_2026-08-20.{md,json} (this
      proof) + P0_ST_PRODUCTION_CONCLUSION_2026-08-20.json (machine-readable
      store conclusion: the replay artifact's `zero_corrections_required:
      false` is the frozen arms-identity predicate, NOT a store defect — the
      produced store matches the lawful arm and needs zero corrections).
      DSC:CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06 resolved. SCOPE:
      the quarantine lift covers ONLY this rule defect — no exact-plane
      authorization, no full-A gate change, no tolerant-label promotion, and
      DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT binds unchanged.
  - id: DEP-CAI
    title: China Alpha Intelligence PR-0B telemetry + rights/identity closure
    status: done
    depends_on: [R6-0]
    next_action: >-
      CLOSED 2026-08-21 (reconciliation + natural-run identity proof; Sol
      R6-continuation ruling). All three constituent gates are satisfied
      inside WS:CHINA-ALPHA-INTELLIGENCE and its owner route. (1) PR-0B
      candidate-plane telemetry DONE + PROVEN_LIVE: real asia-close run
      32348780228 / candidate commit baf4cf7c9291 wrote candidates.parquet
      with full intel_* anatomy (24,070 rows; 1,636-1,640 non-null covered +
      4 typed intel_unavailable_reason refusals) — the
      DSC:CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE block on the candidate
      plane is released. (2) RIGHTS-0 entitlement audit DONE (PR #6046,
      merge 458ad2e18052; CNInfo primary route rights-clear; no Tushare
      stk_surv; ¥0 outlay). (3) China identity: PR-0D was OWNER-ROUTED
      (DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK) to child D2B2-CN-HK under
      WS:PROPHET-US-V4-RECOVERY (PR #6116, squash
      ed28d0d992a144aec5f0ef2616024e3e32d83b1a: 984/1021 CN + 147/147 HK
      admitted to the canonical Data OS master), then PROVEN_LIVE on natural
      production nightly run 32426513915 and adjudicated done by the owner
      (Sol natural-proof adjudication 2026-08-21, records PR #6165 squash
      26365f63029b — both owner D2B2 and pr0d flipped there; that record
      holds the full accounting). This session independently re-measured the
      same run and corroborates every number: canonical
      build_security_master re-ran in-run (data/reference/_receipt.json
      generated_at 2026-08-21T01:17:00, row_counts security_master=1836;
      commit 65070e623f1c) with the master parquet byte-stable vs the #6116
      merge (blob d774ea76ab59); the fresh GMI identity_resolution/v1 batch
      (computed_at 2026-08-21T03:47:13Z, commit 5ba8447ca827) is pinned to
      exactly that master generation — CN 984/1021 RESOLVED (96.4%, 37
      typed refusals), HK 147/147 (100%), US resolved-set identical (702=702
      as sets; the sole US delta is co:us:GOLD leaving the GMI graph — graph
      composition, reserved D2B3 topic, not identity semantics). The
      run-level `cancelled` conclusion is solely the unrelated
      standout_audit_us job, which started 05:52Z after engine+publish
      concluded 04:59Z. CN-Limit may now consume the candidate plane's
      intel_* telemetry and canonical CN identity under the R6 contracts.
      DEP-ID-ELIG remains gated on DEP-EXACT.
  - id: DEP-EXACT
    title: Exact-plane technical readiness, live canary, range campaign, completeness
    status: todo
    depends_on: [R6-0]
    next_action: >-
      TECHNICAL_CANARY_REQUIRED (reclassified 2026-08-21 under the Chairman
      override DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE).
      TuShare licensing/compliance is CHAIRMAN_VERIFIED_PRIVATE / SATISFIED:
      the controlling agreement and its evidence are confidential and outside
      coding/agent scope under NDA/privacy constraints, and no coding session
      or runtime gate may request, upload, inspect, persist, hash, quote, or
      re-verify them. Compliance is therefore NOT a blocker and this row is no
      longer WAITING_FOR_WRITTEN_VENDOR_GRANT; the superseded
      DEC:CNLI-EXACT-PLANE-REQUIRES-WRITTEN-COMMERCIAL-GRANT and the cancelled
      vendor-letter packet are historical tombstones only. The license-document
      authorization subsystem (receipt schema, AuthorizationGrant, trust
      allowlist, grant-document hashes/chains, the empty code-reviewed trust
      root, and the --authorization-receipt / --authorization-trust-allowlist
      CLI requirements) has been REMOVED from collectors/china_tushare_spine.py
      and is held out by anti-resurrection tests in
      tests/test_china_tushare_spine.py. WHAT ACTUALLY REMAINS, all technical:
      BULK_HISTORICAL_BACKFILL_READY = False in
      collectors/china_tushare_spine.py is a TECHNICAL readiness gate (live
      canary parity, sustained throughput, range/completeness correctness) and
      must never be re-read as a licensing gate; bounded live canary windows HAVE
      now run (2026-08-26: 84 request receipts, 32,932 source rows, ~1.3 s/request,
      the full 1992..2023 reference calendar landed) but NO canary has yet reached
      stage=complete — pit_universe, name_history and all five daily endpoints have
      still never executed against the vendor; no sanitized
      completeness manifest exists because the private store has never been
      built; the dispatch-only lane .github/workflows/tushare-spine-backfill.yml
      is wired (modes plan | canary | backfill) and TUSHARE_TOKEN is alive; a red
      mode=backfill run while the technical gate is shut is the gate working.
      The canary is runnable BEFORE the gate opens by design: the gate waits on canary evidence, so gating the canary on the gate would be circular. The bounded envelope (<=12 requests, <=5 calendar days, never allow_bulk, documented row cap refusing rather than starting the unproven ticker-range campaign) has held on every run. EXACT NEXT TECHNICAL ACTION (2026-08-26, executing Sol's calendar-epoch ruling): the mainland session axis is now frozen at the definition-versioned epoch mainland-joint-complete-v1 / 1992-01-01, established by outcome-blind census (scripts/research/cn_limit_calendar_epoch_census.py) and superseding the 1991-01-01 anchor that had blocked collect_calendars; pre-epoch history is typed PRE_EPOCH_SOURCE_UNSUPPORTED and never imputed. The CLEAN REBUILD IS DONE (2026-08-26): the trade_cal plane was deleted and re-collected under the frozen epoch rather than repaired in place, reaching 66/66 terminal units with zero 1991 units, and compile_market_sessions yields 7,807 sessions from 1992-01-02. The identity generation was preserved, so no identity call was re-bought. SOL RULED return-gate 10 on 2026-08-26 (DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION): historical PIT construction is source-UNION, never current-snapshot intersection. The current stock_basic snapshot is a lifecycle/reference WITNESS, not exhaustive historical membership authority -- intersecting a CURRENT snapshot against HISTORICAL sessions is a survivorship filter whose error points one way, so a security the vendor later stops publishing became unclassifiable on every past date it actually traded (measured: 300114.SZ, demonstrably trading 2024-01-02, absent from the current snapshot). A well-formed A-share bak_basic PIT observation now LANDS carrying current_stock_basic_witness_missing=true; it grants NO trading/event and NO canonical-identity authority. Positive volume PLUS exact legal-band evidence is what proves historical trading; without it a PIT row is source-accounted but non-event-eligible, and 'never listed' may not be inferred without an explicit lifecycle source. PIT-only keys propagate into downstream acquisition including name_history. Data OS/GMI stays canonical identity owner -- no historical CN-Limit identity master. Omission rate is TELEMETRY, never an exclusion threshold. Fail-closed is unchanged for malformed/conflicting keys, incomplete responses, unresolved source contradictions, positive-volume rows lacking exact legal-band evidence, and any unknown disposition. EXECUTION FINDING: the filter was encoded at THREE layers, not one -- the row classifier (normalise_bak_basic), the PIT/lifecycle reconciliation (_pit_lifecycle_reconciliation, whose complete flag required pit subset-of lifecycle and is a term in the completeness manifest's own complete conjunction), and the daily coverage expectation (build_daily_security_coverage, where a landed PIT row that never traded becomes eligible with no daily row and lands in unexplained_missing_n, also a manifest term). Fixing only the first would have moved the failure two stages later. Two further conjunction terms (_lifecycle_edge_reconciliation, canonical_event_substrate) were traced and need no change. The rest of the plane was already union-shaped: _eligible_tickers_with_pit already returns lifecycle|pit, _instrument_scope_maps already folds landed PIT tickers into known_a, and event_eligible = positive_volume & source_limits_present already IS the graded authority test. Next after the ruling: implement it, then ONE acceptance window (pit 1 + name <=5 + daily 5 = <=11 vs the cap of 12) reaching stage=complete. Only on that complete canary's request/schema/source-row/accounting/cap/refusal/throughput receipts may a SEPARATE reviewed change flip BULK_HISTORICAL_BACKFILL_READY; mode=backfill (the full range campaign) stays refused until then. After the flip the
      range-shard campaign runs and the sanitized completeness manifest closes
      this row. The identity half of the eligibility substrate exists
      (984 CN + 147 HK canonical, see DEP-CAI); the PIT
      membership/suspension/ST-history substrate remains NOT_BUILT and is
      DEP-ID-ELIG's remainder. Standing prohibitions: no request for or
      inspection of the private agreement; no reintroduced
      authorization-receipt/trust-allowlist/license-document gate under any
      name; no gate-constant edit without reviewed technical evidence; no
      public redistribution of raw vendor data.
      DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT untouched.
      RETURN-GATE 10 SHIPPED 2026-08-27 (PR #6486, squash a636c7bcefdb): the
      source-union ruling is merged and PROVEN on the live vendor -- bak_basic
      20240102 went from failed to status=complete at 5344 = 5344 + 0 + 0,
      quarantine 0 where it was 2, witness_missing_row_count 2, with 300114.SZ
      and 603361.SS landing flagged. pit_universe, name_history, daily and
      daily_basic all executed against TuShare for the first time. Follow-up PR
      #6494 (squash fab40e11940c) fixed DSC:CNLI-STK-LIMIT-ZERO-PRE-CLOSE-SENTINEL,
      the vendor's second zero-as-null spelling: stk_limit publishes rows for
      non-trading instruments with pre_close 0, which raised and destroyed a
      whole unit's accounting (3,466 source rows, 0 landed). Sentinel is scoped to
      stk_limit only, and its load-bearing half is a fail-open GUARD -- the
      daily/stk_limit previous-close cross-check compares only rows where both
      values are non-null, so nulling a zero would have silently dropped that
      ticker from the audit; every positive-volume daily row must now have a
      non-null stk_limit.pre_close or the substrate raises.
      SOL RULED return-gate 10B on 2026-08-27
      (DEC:CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY): a valid namechange row
      is ITSELF sufficient source evidence and needs no external witness to exist
      in the name-history plane. External-witness-as-completeness is replaced by
      deterministic row disposition -- externally corroborated, NAMECHANGE_ONLY,
      or explicit conflict/quarantine. NAMECHANGE_ONLY is TERMINAL SOURCE
      COMPLETENESS with ZERO PIT membership, trading, exact-event,
      canonical-identity, rank or score authority. No pre-2016 special case and
      the witness-missing percentage is NOT an admission threshold; row by row
      across the frozen epoch, rate is telemetry. Manifest complete now requires
      all source rows deterministically reconciled with zero unresolved
      conflicts, NOT 100% external corroboration. EXECUTION FINDINGS: (1)
      name_history is a LEAF -- nothing reads store/name_history but its own
      receipt builder, so unlike the PIT case there is no second-stage filter to
      repair; the zero-authority clause is pinned by a negative proof that a
      namechange-only ticker never enters _all_known_a_tickers, which is the
      inversion that would otherwise let a name assertion bootstrap universe
      membership. (2) TWO of the four fail-closed conditions Sol required to be
      PRESERVED did not exist and had to be BUILT: normalise_name_history carried
      no lifecycle-interval validation at all, and because KEY_COLUMNS
      ['name_history'] includes `name`, two rows asserting different names
      effective the same day did not trip the duplicate check. The single
      compound witness condition had been masking both, so removing it without
      building them would have turned a fail-closed plane fail-open while
      appearing to preserve fail-closed behaviour. (3) known_a membership was
      also doing double duty as the only A-share scope filter, so an explicit
      _is_a_share_identity gate replaces that half. BULK READINESS (Sol 10B): a
      clean canary is NOT required to exercise the ticker-range campaign, since
      that capability is deliberately held behind BULK_HISTORICAL_BACKFILL_READY;
      exact-head canary plus range-shard ADVERSARIAL TESTS may justify the
      separate technical readiness PR, and the first post-promotion bounded range
      execution is its production proof. DEP-EXACT stays OPEN until the complete
      range campaign and the sanitized completeness manifest. Note the row cap is
      already binding on recent sessions: stk_limit returned >=5,800 rows for a
      2024 session against a 6,000 cap that daily/daily_basic cleared only
      narrowly, so the range campaign is REQUIRED for recent dates, not an
      optimisation.
  - id: DEP-ID-ELIG
    title: Canonical China identity, PIT membership, eligibility overlay
    status: todo
    depends_on: [DEP-EXACT, DEP-CAI]
    next_action: >-
      Point-in-time eligible security-session population + time-valid
      sector/theme edges via Data OS/GMI/eligibility owners; no CN-Limit
      identity or membership plane; no ticker-only keys; no current-membership
      backfill (packet §DEP-ID-ELIG).
  - id: I1A-T1
    title: "First candidate-anatomy vertical: CNLI.TRANS.DOWN_IMPACT_ASYMMETRY"
    status: todo
    depends_on: [P0-ST, DEP-CAI, DEP-ID-ELIG]
    next_action: >-
      One frozen deterministic feature projected prospectively onto canonical
      candidate rows + real audit consumer; no probability/rank/gate fields
      (packet §I1A-T1; freeze Appendix A contract).
  - id: I1A-T2
    title: Bad-day resilience vertical
    status: todo
    depends_on: [I1A-T1]
  - id: I1A-T3
    title: Constructive-volume asymmetry vertical
    status: todo
    depends_on: [I1A-T1]
  - id: I1A-T4
    title: Reclaim-and-hold quality vertical
    status: todo
    depends_on: [I1A-T1]
  - id: I1B-MEASURE
    title: Exact target + first immutable prediction/grade sidecar vertical
    status: todo
    depends_on: [DEP-ID-ELIG, I1A-T1]
    next_action: >-
      Referential sidecar china_prophet_rank.cn_limit_research.v1 with one real
      feature + R4 H10 exact target + access dispositions; never an empty
      generic foundation (packet §I1B-MEASURE).
  - id: M2-R4-BATTERY
    title: Frozen historical/rolling-origin R4 active-family battery
    status: todo
    depends_on: [I1B-MEASURE, I1A-T2, I1A-T3, I1A-T4]
    next_action: >-
      Freeze formulas/populations/baselines/controls/nulls/folds/metrics
      before opening exact outcomes; run once; advance/kill/accrue verdicts.
      A NULL or kill verdict is complete (packet §M2-R4-BATTERY).
  - id: I1C-G6
    title: Prospective G6 measurement shadow
    status: todo
    depends_on: [M2-R4-BATTERY]
    next_action: >-
      One preregistered challenger accrued prospectively to the G6 floors
      (>=120 candidate sessions, >=2 regimes, >=60 exact first-board events,
      no retuning). Highest verdict = ELIGIBLE_FOR_SHADOW_IMPLEMENTATION_COMMISSION,
      which is not live authority.
  - id: I2A-ORDER
    title: Fixed-candidate off-path ordering shadow
    status: todo
    depends_on: [I1C-G6]
    next_action: >-
      Coverage-atomic challenger order on frozen U3 with same-rule/same-cap
      shelf replay; production bytes must remain identical
      (DEC:CNLI-COVERAGE-ATOMIC-CHALLENGER, DEC:CNLI-ERA-IS-EFFECTIVE-AUTHORITY).
  - id: A5-DECISION
    title: Potential bounded live ordering decision (Sol/Chairman)
    status: todo
    depends_on: [I2A-ORDER]
    next_action: >-
      NOT_AUTHORIZED. A decision record, not a build wave; R6 grants no A5
      authority and no automatic promotion
      (DEC:CNLI-AUTHORITY-DOES-NOT-CASCADE).
landmines:
  - >-
    The STOP-SHIP (operator, 2026-08-10; DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT) covers
    the PRE-CHARTER research waves the program called W1-W3. They are NOT waves of this
    record — this record starts at W-P0 (charter + P0 scope), and no wave here carries
    those ids. That is deliberate: the ids are unresolvable inside this store on
    purpose, because the results behind them must never be cited as evidence, including
    in passing. If you found this landmine while hunting for a wave called W1, stop
    hunting — there is nothing here to read.
  - >-
    P-B is WINNERS-ONLY anatomy: its presence/order/lead numbers carry no comparison
    arm and must never be quoted as selection skill or conditional probability. The
    preregistered comparison arm is P-B2. P-B3 certifies what P-B2 left unresolved;
    it does not rewrite P-B2.
  - >-
    Long-horizon feature shifting (P-B2 §6.3, S in {250, 500, 1000}) is not a
    valid certification null for persistent states
    (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT). P-B3's corroborative null
    is a duration/prevalence-preserving within-split spell permutation.
  - >-
    QUARANTINE LIFTED at merge (PR #6047, P0-ST wave): the main-board
    risk-warning band repair (era-dated ±5%→±10% effective 2026-07-06;
    MAIN_ST_BAND_WIDE_DATE in engine/china_microstructure.py) plus the matching
    config/cn_limit_rules.yml interval split landed there. The census in that
    PR's replay (research/cn_limit/P0_ST_BAND_REPAIR_RECEIPT_2026-08-19.md)
    confirmed ZERO persisted rows at limit_width==5.0 in
    data/china_microstructure/limit_events.parquet even under the pre-fix code
    — the sole affected main-board ST name (600079.SS) never actually printed
    a post-07-06 event at either width — so there were no pre-fix rule-stale
    era labels to quarantine in the first place; this constraint recorded a
    risk that the census then measured as not materialized
    (DSC:CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06, now resolved — see that
    record for the repaired claim). CLOSED 2026-08-20: the real asia-close
    production proof landed (run 32348780228, commit baf4cf7c9291;
    research/cn_limit/P0_ST_PRODUCTION_PROOF_2026-08-20.md) — it also measured
    the repair's first real consequence: the superseded 5% law would have
    written 17 phantom events on the newly risk-warning 600745.SS in that very
    session. The lift is SCOPED to this rule defect only — it grants no
    exact-plane authorization and leaves
    DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT fully binding. Note
    engine/china_microstructure.py's ST_STORE_COVERAGE_DATE remains
    coincidentally also 2026-07-06 — that constant is store coverage, not the
    rule-era switch (which is the separate MAIN_ST_BAND_WIDE_DATE constant).
  - >-
    The R6 packet statuses (DORMANT_*/BLOCKED_*) are encoded here as todo +
    gates in next_action because the wave schema has no blocked status. The
    packet and freeze under research/cn_limit/ are the authority on gate
    wording; this record is the authority on current state.
do_not_redo:
  - >-
    Do not restore, re-grade, or cite any adjusted-plane W1-W3 artifact, ledger, model
    or picks page (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT). The reopen path is the
    exact-plane chain in research/CN_LIMIT_EXACT_PLANE_LEDGER_PREREG_REQUIREMENTS_2026-08-11.md
    §5 — full-A spine backfill, eligibility overlay, F3 exact re-measurement, fresh
    preregistration — and nothing short of it. R6 restates this as
    DEC:CNLI-EXACT-CENT-PRIMARY.
  - >-
    Do not build a per-ticker best-expert/outcome-audition selector in this workstream
    (DNR:KILL-OUTCOME-AUDITION; Stock Identity owns per-security routing; Live Entry
    Radar owns the entry-event store). R6 extends this to the challenger lane:
    exactly one preregistered challenger per prospective race
    (DEC:CNLI-NO-OUTCOME-AUDITION).
  - >-
    Do not import the RAW China Intelligence Hub composite (china_intel_hub
    opportunity_score / conviction) or any Hub board-derived term (board_row direction,
    board label edge, board-absent bonus, board's leading-vs-lagging gap contribution)
    into a Prophet-facing construction — those carry the board's own output back into
    itself. AMENDED 2026-08-15 (operator, "Handoff B"): the rule is PROVENANCE, not the
    word "composite". Any displayed CN Prophet score/rank must trace to
    engine/china_board_rank.py; that scorer may consume registered board-INDEPENDENT
    evidence, including the board-independent intelligence-interest composite
    engine/china_intel_interest.py (intel_interest_score), which is live in
    cn_prophet_v4 as ORDERING authority. Nothing under research/cn_prophet_audit/ may
    own Prophet rank. Any FURTHER authority (gate/size/score) still re-earns its value
    under its own preregistration.
  - >-
    Do not reconstruct evidence history from current snapshots (broker.parquet,
    margin.parquet, china_block_trades/detail.parquet, china_buyback/buyback.parquet).
    Studies read the hist/events stores. Do not stamp historical broker months as
    PIT-known (DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE). Do not redo the
    report_rc overwrite fix (#5614).
  - >-
    Do not reuse P-B2's long-horizon feature-shift placebo as a certification null
    (DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT). Do not re-run P-B3 or shop
    its gates, floors, strata, cells, or headlines
    (DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE). Do not open P-D from this
    construction. Do not flip MA200 to onset or DD to exit after seeing the
    A_B_CONTRADICT rows.
  - >-
    Do not create a second candidate population, grader, identity plane,
    company-event store, intelligence composite, or lifecycle for CN-Limit
    (DEC:CNLI-ONE-CANONICAL-PROPHET-CHAIN). Do not edit the candidate writer
    for CN-Limit before PR-0B is PROVEN_LIVE
    (DSC:CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE). Do not use the Prophet
    Operator Lab as a CN-Limit store, grader, or ontology
    (DEC:CNLI-PROPHET-LAB-FENCED-ADJACENCY).
  - >-
    Do not implement any live rank, score, gate, size, or public probability
    from R6 records — authority does not cascade
    (DEC:CNLI-AUTHORITY-DOES-NOT-CASCADE); A5 is a Sol/Chairman decision wave,
    never a build default. Do not label tape features with actor/intent claims
    (DEC:CNLI-ACTOR-NEUTRAL-TAPE-LANGUAGE).
decisions:
  - "DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE"
  - "DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE"
  - "DEC:CNLI-HAZARD-NOT-MAGIC-INDICATOR"
  - "DEC:CNLI-CARRIER-CONTEXT-NOT-SELECTOR"
  - "DEC:CNLI-SEQUENCE-OVER-COUNT"
  - "DEC:CNLI-ACTOR-NEUTRAL-TAPE-LANGUAGE"
  - "DEC:CNLI-OUTCOME-VECTOR"
  - "DEC:CNLI-EXACT-CENT-PRIMARY"
  - "DEC:CNLI-ONE-CANONICAL-PROPHET-CHAIN"
  - "DEC:CNLI-MEASUREMENT-BEFORE-ORDERING"
  - "DEC:CNLI-COVERAGE-ATOMIC-CHALLENGER"
  - "DEC:CNLI-ERA-IS-EFFECTIVE-AUTHORITY"
  - "DEC:CNLI-NO-OUTCOME-AUDITION"
  - "DEC:CNLI-AUTHORITY-DOES-NOT-CASCADE"
  - "DEC:CNLI-PROPHET-LAB-FENCED-ADJACENCY"
discoveries:
  - "DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT"
  - "DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE"
  - "DSC:CN-MAIN-ST-BAND-STILL-5PCT-AFTER-2026-07-06"
  - "DSC:PROPHET-LAB-OWNS-NO-CN-LIMIT-PATHS"
  - "DSC:CN-PR0B-NOT-LIVE-BLOCKS-CANDIDATE-PLANE"
artifacts:
  - research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md
  - research/cn_prophet_audit/PB3_PREREG_ADVERSARIAL_REVIEW_2026-08-15.md
  - research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.md
  - research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.json
  - research/cn_prophet_audit/pb3_persistence_robust_cert.py
  - research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md
  - research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_REGISTRY_V1_2026-08-19.json
  - research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_GROK_BOUNDED_COMMISSIONS_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_EXECUTIVE_HANDOFF_INDEX_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_ARTIFACT_MANIFEST_2026-08-19.json
next_action: >-
  Execution owner is Fable COO under DEC:CNLI-FABLE-COO-AUTONOMOUS-EXECUTION
  (Chairman delegation 2026-08-25; Sol retains product thesis, architecture,
  evaluation law and final milestone acceptance; A5 stays Sol/Chairman).
  R6-0, P0-ST and DEP-CAI are done with production receipts. This PR (#6207)
  lands the Chairman TuShare compliance override reconciled onto current main.
  Next: execute DEP-EXACT per its row — dispatch tushare-spine-backfill
  mode=plan, then ONE bounded mode=canary, then a separate reviewed technical
  flip of BULK_HISTORICAL_BACKFILL_READY on canary evidence, then the resumable
  full-A range campaign and the sanitized completeness manifest. After
  DEP-EXACT: DEP-ID-ELIG, then I1A-T1..T4 / I1B / M2-R4-BATTERY / I1C-G6 / I2A
  per the frozen R6 wave graph. Milestone bundles return to Sol per
  agentos/handoffs/CN-LIMIT-ALPHA-2026-08-25-fable-coo-program.md. No live
  rank, score, gate, size, or public probability is authorized by any R6
  record.
---

## Context

The 2026-08-10 STOP-SHIP ruling stands in full force as a citation/restoration ban on
the withdrawn adjusted-plane artifacts (see landmines) — but the RESEARCH workstream is
ACTIVE on lawful substrate, not blocked: the v2 program home
(`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md`) re-homed the thesis on the
pattern-tier washout-onset lane, and W-P0 (#5364), P-A1 (#5438), P-B (#5521) and
P-B2 (#5615) have all merged under it. P-B2's verdict — NO DISCRIMINATOR at the
preregistered bar — closes that construction only. P-B3 (PR #5729) ran the
persistence-robust reopen and closed it: NULL=12, UNINFORMATIVE=8; no timing
or occupancy input for P-D. P-B2-ACCRUAL (#5730) shipped the prospective
keep-first PIT hist stores; that wave is done and is not a P-B3 input.

**R6 (2026-08-19):** Sol's final research and integration architecture freeze
landed under `research/cn_limit/` — read order and precedence in
`CN_LIMIT_R6_EXECUTIVE_HANDOFF_INDEX_2026-08-19.md`. CN-Limit is now chartered
as a mechanism-aware rerating-hazard system: structural washout is the carrier,
lawful professional/corporate/sector/supply evidence supplies mechanism context,
transition features identify release, Prophet owns actionability, and access is
modeled separately from event probability. The program reuses the canonical
candidate and grade planes, adds prospective anatomy only after China Alpha
PR-0B is proven live, and writes immutable predictions/grades/corrections to a
referential sidecar. No live rank, score, gate, size, or public probability is
authorized. The R6 wave graph above (R6-0 → P0-ST + DEP-* → I1A → I1B → M2 →
I1C → I2A → A5) is the frozen execution plan; the 2026-08-19 handoff records
the landing session's reconciliations, including the post-packet merge of the
China Alpha architecture chain.
