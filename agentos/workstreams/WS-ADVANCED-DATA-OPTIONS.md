---
key: ADVANCED-DATA-OPTIONS
title: Advanced Data — Options EOD + Off-Exchange Intelligence OS
objective: >
  Convert the options/off-exchange estate from an interpret-it-yourself dashboard into a
  standalone anticipation and risk intelligence lobe with bounded Prophet confluence.
  Done = ranked, falsifiable, receipt-backed EOD signals with explicit no-signal/degraded
  states, production-proven per slice (AD-0…AD-15 per the committed recovery masterplan).
status: active
program: options-intelligence
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: scoped
waves:
  - id: AD-0
    title: Recovery archaeology + production truth + AD-1 freeze
    status: done
    pr: [5830, 5838, 5849]
  - id: AD-1P0
    title: Semantic-authority freeze (v1.2) before implementation
    status: done
    pr: 5860
    depends_on: [AD-0]
  - id: AD-1
    title: Daily EOD Options Intelligence Brief (runtime implementation)
    status: done
    pr: 5872
    depends_on: [AD-1P0]
    next_action: >
      Runtime MERGED (661ad5d291aa687bbb0c7a33e5b573c60a2b148f, 2026-08-19T13:25:26Z).
      State = BUILT_NOT_PROVEN. Production proof now runs on the canonical
      ThetaData source under wave AD-1T0 (DEC:AD-OPTIONS-CANONICAL-SOURCE-
      THETADATA) — the prior Massive/Polygon entitlement condition is retired
      and is not an AD dependency.
  - id: AD-1C0
    title: Source-failure durability (auth census, health receipt, first-writer quality)
    status: done
    pr: 5974
    depends_on: [AD-1]
    next_action: >
      Merged (d5ebb5d9b3db8c12deed7c267676cb38b6b348dc, 2026-08-19T16:04:26Z).
      Legacy source-hardening on the polygon_gex estate: remains merged
      evidence/hardening but no longer gates AD-1 (Chairman source ruling
      2026-08-22, DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA).
  - id: AD-1C0.1
    title: Source-clock integrity (capture lease) on the legacy estate
    status: done
    pr: 6080
    depends_on: [AD-1C0]
    next_action: >
      Merged (12467e2d5e9d333c13340a4fa216eb3924cd45fd, 2026-08-22T05:32:55Z,
      Sol PASS 4991922630). Legacy source-clock hardening on the polygon_gex
      estate: remains merged evidence/hardening but no longer gates AD-1.
      Any Massive/Polygon credential-security cleanup is outside this Options
      workstream and must not block AD-1.
  - id: AD-1T0
    title: ThetaData canonical options source cutover (Chairman ruling 2026-08-22)
    status: done
    depends_on: [AD-1]
    next_action: >
      Cutover DELIVERED 2026-08-22: producer consumes the canonical ThetaData
      store via resolve_thetadata_store(); engine byte-unchanged; v1.2 frozen;
      identity ruled on the source tuple (spec research/AD1T0_THETADATA_
      CUTOVER_SPEC_2026-08-22.md); three adversarial review rounds, all
      findings closed; committed artifact built on the m1 store (S=2026-08-19,
      D=2026-08-20, receipt 637d0c60..., zero Polygon inputs). AD-1 stays
      BUILT_NOT_PROVEN: the 0.90 coverage proof is structurally unreachable —
      DSC:THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS (39/375 = 0.104 daily-
      current). Diagnostic on the covered 39: 39/39 eligible, real boards —
      the scoring pipeline is production-capable; the spine is the blocker.
      Next: Sol decision on a spine-cadence wave (incremental refresh) +
      store-host runner topology (RE-PIN RULE) / r2sync heal. Do not start
      AD-2; do not shrink the universe.
  - id: AD-1T1
    title: Full-universe incremental ThetaData T1 cadence (Sol handoff 2026-08-22)
    status: done
    pr: 6267
    depends_on: [AD-1T0]
    next_action: >
      PROVEN_LIVE 2026-08-25 (production packet = PR 6267
      issuecomment-5419508761; merge SHA 787787f93c8e, merged 2026-08-23,
      m1 transitioned same night per runbook section 3a, Terminal never
      restarted). Proof: two consecutive normal scheduled sessions — D1
      2026-08-24 (S 2026-08-21) healthy 98.1->98.4%, D2 2026-08-25
      (S 2026-08-24) healthy 0.984, all 8 rungs deadline_exceeded=False,
      forced=false, both 18:30 PT sentinel anchor evaluations PASSED K4,
      oi_D_source=snapshot_open_interest direct in D2 receipts, OI[D]
      rows verified lawful at the parquet level both dates; bounded
      production acceptance review 9/10 PASS with the one finding (F1
      second-writer flock gap: com.mastermind.levelsseal ran pre-AD-1T1
      topup from stale hub-ops-wt without flock) REPAIRED same day
      (4-file closure refreshed to origin/main bytes, sha256-verified,
      live validation = next 04:30 PT fire); read-only AD diagnostic on
      the store host: source_coverage_pct 0.9467 >= 0.90, board_state OK,
      receipt closure intact, zero Polygon inputs, Q_flow ABSENT — the
      AD-1T0 source blocker (0.104) is SOLVED. Open findings for their
      own waves (never a lane redesign): F2 six dead AD-universe roots
      masked as vendor_empty (WBS/BLD/URG/RHHBY/NVR/FI, stale since
      <=2026-07-02); F3 sentinel structural evening greeks-WARN
      (pre-existing); F4 timestamp-less daily_refresh.log + single-slot
      receipt makes first-run receipts unrecoverable per day. AD-1
      remains BUILT_NOT_PROVEN (consumer path is AD-1T2's to prove).
      Next: Sol commissioning of AD-1T2. AD-2 stays CLOSED.
  - id: AD-1T2
    title: Restore store-bearing M1 to the theta-m1 product workflow; commission AD-1 end to end
    status: todo
    depends_on: [AD-1T1]
    next_action: >
      NOT STARTED. Opens only after AD-1T1 is Sol-accepted and the T1 cadence
      is production-proven (two consecutive normal scheduled sessions). Broken
      R2 sync is not a prerequisite unless new evidence proves it necessary.
  - id: AD-2
    title: Evidence Receipts, Nulls, Lifecycle, Corrections
    status: todo
    depends_on: [AD-1]
    next_action: CLOSED until AD-1 production acceptance. Do not start.
landmines:
  - >-
    The ThetaData Terminal license allows ONE terminal instance
    (com.macro.theta-terminal on the M1 host). Never launch a second Terminal,
    never copy the ~60GB T1 store between runners, and never mint a second
    store path — engine/thetadata_store.resolve_thetadata_store() is THE
    resolver, and it deliberately refuses the empty repo stub
    (data/thetadata_eod/_manifest.json n_roots=0). An M2/GH runner must never
    silently resolve the stub and publish NO_SIGNAL.
  - >-
    The entire host-side intraday options launchd fleet (15 units incl. the sparse-selector
    canary) is NOT loaded on the Mac Studio as of 2026-08-17 (verified launchctl probes,
    AD-0 ledger §2.3). Do not treat in-repo plists under ops/launchd/ as running machinery.
    Intraday options production/classification authority stays with Terminal — AD
    authorizes no duplicate intraday collector.
  - >-
    Exactly one options-derived input reaches live Prophet rank: gex_confirm_verdict in C1
    fusion, lawful solely via DNR:KILL-POSITIONING-FUSION Amendment 1. Any wider fusion of
    positioning keys outside that arena remains ILLEGAL.
  - >-
    The Macro host intraday options fleet is DISARMED BY DEFAULT pending the AD-9 ruling
    (Sol review on #5830) — do not load, install, or re-arm any ops/launchd options unit.
  - >-
    Historical/preregistered campaign and episode evidence is preserved append-only even
    where its runtime is retired (Sol review on #5830) — retirement never deletes evidence.
  - >-
    LEGACY (Massive/Polygon estate, no longer on the AD-1 path): HTTP 403
    NOT_AUTHORIZED on /v3/snapshot/options/{symbol} is an account entitlement failure
    on the legacy source; missing polygon_gex chain sessions 2026-08-14/17/18 are
    permanent (point-in-time OI) — do not hand-write those parquet files, and do not
    backfill the polygon_gex store from ThetaData (the stores keep separate identities).
  - >-
    Cboe delayed quote pages expressly prohibit automated extraction. Not an AD-1 fallback.
decisions:
  - "DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT"
  - "DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION"
  - "DEC:AD1C0-FIRST-WRITER-QUALITY-RULE"
  - "DEC:AD1C01-CAPTURE-LEASE-REPLACES-SAME-DAY"
  - "DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA"
discoveries:
  - "DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION"
do_not_redo:
  - >-
    Do not re-audit the seven sparse-selector PRs (#5747 #5694 #5696 #5708 #5711 #5790
    #5801) — reconciled with merge SHAs in the AD-0 ledger; #5711 is a closed duplicate of
    #5708; W1A-A/B modules are test-only with zero consumers.
  - >-
    Do not re-derive the legacy EOD source map: Polygon snapshot (POLYGON_API_KEY then
    MASSIVE_API_KEY, ~18:30 ET, session-stamped) + massive.com OPRA aggs (NOT entitled
    to trades_v1/quotes_v1) + FINRA CNMS/ATS keyless. AD-0 ledger §4. That estate is
    now legacy context (DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA).
  - >-
    Do not resurrect darkpool direction labels (v2 null walk-forward + DNR:PSS-AF1) or the
    DOI/skew-decel families (killed).
  - >-
    Do not restart Polygon-vs-Massive domain-migration diagnosis. Re-proved
    2026-08-19T19:59:29Z and again 2026-08-20T05:23:23Z: both domains 403 on option
    chains and 200 on stock/news with the same linked key. Legacy context only —
    restoration of that entitlement is no longer an AD objective.
  - >-
    SUPERSEDED 2026-08-22 (DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA): the former
    "do not silently route AD-1 to ThetaData" row guarded against a silent source
    swap pending a Sol-commissioned adjudication. That adjudication is now the
    Chairman source ruling: ThetaData IS the canonical options source and wave
    AD-1T0 executes the cutover explicitly. What remains prohibited: a parallel
    Massive-vs-ThetaData dual-truth store, and any second intraday collector.
  - >-
    Sparse selector / W1A is RESEARCH-ONLY. Do not resurrect before the AD-9 ruling.
next_action: >
  Execute wave AD-1T1 (full-universe incremental T1 cadence, Sol handoff
  2026-08-22): benchmark one-day vendor throughput; extend the existing
  one-session writer into the daily incremental maintainer; retire whole-year
  DAILY refresh; return the bounded PR to Sol UNMERGED. AD-1 stays
  BUILT_NOT_PROVEN until AD-1T2 restores the product workflow. Do not start
  AD-1T2 or AD-2.
artifacts:
  - research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md
  - research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md
  - research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
---

## Context

AD-0, AD-1P0, AD-1, AD-1C0, and AD-1C0.1 are done (merge SHAs in the wave rows).
AD-1 state = BUILT_NOT_PROVEN.

**Source authority (Chairman ruling 2026-08-22,
DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA): ThetaData is the canonical
Mastermind options-data source** — EOD chains, open interest, Greeks/IV,
trade + NBBO, and Terminal intraday. Massive/Polygon is a stock-data source,
not an options source authority. The prior entitlement blocker and needs_ceo
gate are retired; credential-security cleanup on the legacy key lives outside
this workstream.

The canonical T1 store lives on the M1 host
(`/Users/chriswong/theta-ops-wt/data/thetadata_eod`, resolved ONLY via
`engine.thetadata_store.resolve_thetadata_store()`), fed by the theta launchd
lanes (`com.macro.theta-terminal`, `com.macro.thetadata-backfill`,
`com.macro.thetadata-r2sync`, `com.macro.theta-staleness`). daily.yml pins
ThetaData-consuming jobs to the theta-m1 runner labels.

The repo-local `data/thetadata_eod/` is an EMPTY STUB (`n_roots=0`) and must
never be treated as production truth — the resolver refuses it by design.

`site/options_intel_brief.json` is built from the canonical ThetaData store
since AD-1T0 (PR #6253, merge a45ac6f58e63): honest
`board_state=INSUFFICIENT_COVERAGE` at 39/375 = 0.104 source coverage. The
coverage blocker is the T1 spine's 48-root daily refresh
(DSC:THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS); AD-1T1 replaces that
whole-year refresh with a full-universe one-session incremental maintainer —
the ~19h full-universe estimate was a property of the whole-year re-pull
design, not of one-day vendor throughput (Sol ruling, AD-1T1 handoff §0).
