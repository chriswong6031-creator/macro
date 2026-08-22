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
    status: in_progress
    depends_on: [AD-1]
    next_action: >
      Per the AD-1T0 directive: live ThetaData T1 census on the store-bearing
      host (runtime, coverage, lawful S/D pair, contract identity), source/PIT
      reconciliation, Fable contract-identity ruling, bounded producer-source
      adapter (engine/options_intel_brief.py unchanged; v1.2 frozen; Q_flow
      stays ABSENT; no legacy Polygon options inputs), then production proof
      against the newest lawful ThetaData S/D pair (coverage >= 90%, receipt
      closes over actual ThetaData bytes, board not STALE_SOURCE, served
      Options Workspace verified). Success => AD-1 = PROVEN_LIVE; return to
      Sol before AD-2.
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
  Execute wave AD-1T0 (ThetaData canonical source cutover): census + PIT
  reconciliation + identity ruling + bounded adapter + production proof against
  the newest lawful ThetaData S/D pair. Success => AD-1 = PROVEN_LIVE; return
  to Sol before AD-2. No Massive/Polygon restoration work belongs to this
  workstream.
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

`site/options_intel_brief.json` remains `board_state=STALE_SOURCE` from the
frozen legacy store (`as_of_session=2026-08-12`) until AD-1T0's cutover PR
lands and the producer consumes the ThetaData store.
