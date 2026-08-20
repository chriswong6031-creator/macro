---
key: ADVANCED-DATA-OPTIONS
title: Advanced Data — Options EOD + Off-Exchange Intelligence OS
objective: >
  Convert the options/off-exchange estate from an interpret-it-yourself dashboard into a
  standalone anticipation and risk intelligence lobe with bounded Prophet confluence.
  Done = ranked, falsifiable, receipt-backed EOD signals with explicit no-signal/degraded
  states, production-proven per slice (AD-0…AD-15 per the committed recovery masterplan).
status: blocked
program: options-intelligence
repos: [macro]
owner: coo-fable
class: research
blast_radius: reversible
ambiguity: scoped
blocked_by:
  - >
    Massive/Polygon option-chain snapshot entitlement is still absent on the linked
    key after a claimed restoration. Post-entitlement commissioning census
    2026-08-20T05:23:23Z: GET /v3/snapshot/options/{AAPL,SPY} returns HTTP 403
    NOT_AUTHORIZED on BOTH api.polygon.io and api.massive.com, while AAPL stock
    snapshot and news return 200 on the same key (MASSIVE_API_KEY). Production
    adapter PolygonOptions.snapshot() on the mixed probe set
    [SPY, QQQ, IWM, AG, CDE] returned 5/5 auth_or_entitlement_failure, 0 rows,
    no production write. The 2026-08-19 scheduled capture wrote a FAILED health
    receipt (coverage_pct=0.0, aborted_early). No repo change can restore this.
    AD-1 stays BUILT_NOT_PROVEN / SOURCE_BLOCKED.
needs_ceo:
  question: >
    Restore a rights-safe Massive Options Snapshot entitlement (daily OI + Greeks/IV)
    on the linked production key, and confirm a BUSINESS/ENTERPRISE license or written
    commercial grant covering Mastermind before AD-1 production commissioning?
  options:
    - "Restore Options Snapshot on the existing linked key under a business/enterprise grant, then wait for two scheduled healthy captures"
    - "Replace the linked key with an already-entitled business-licensed key, then wait for two scheduled healthy captures"
    - "Hold AD-1 dark and separately commission a Massive↔ThetaData parallel-source adjudication (not a silent swap)"
  recommendation: >
    Restore/rebind Options Snapshot on the existing account/key under a business
    license. Do not attach a personal-use plan. Do not silently route AD-1 to ThetaData.
    Do not ask a coding agent to "fix Polygon options."
  by_when: 2026-08-21
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
      Production commissioning remains SOURCE-BLOCKED / BUILT_NOT_PROVEN until
      entitlement restoration plus two consecutive healthy scheduled captures
      (S then D, coverage_pct >= 0.90), then Sol production-acceptance review.
  - id: AD-1C0
    title: Source-failure durability (auth census, health receipt, first-writer quality)
    status: done
    pr: 5974
    depends_on: [AD-1]
    next_action: >
      Merged (d5ebb5d9b3db8c12deed7c267676cb38b6b348dc, 2026-08-19T16:04:26Z).
      First post-merge scheduled capture DID run: data/polygon_gex_health/2026-08-19.json
      session 2026-08-19 capture_instant 2026-08-20T01:00:18Z health=failed
      coverage_pct=0.0 aborted_early 5/5 auth_or_entitlement_failure. That is not
      capture S. Do not hand-write a receipt. Do not --force. After a live 200
      entitlement, the next lawful scheduled run may replace this failed vintage.
  - id: AD-1C0.1
    title: Source-clock integrity + security closure + production commissioning
    status: in_progress
    depends_on: [AD-1C0]
    next_action: >
      Sol handoff 2026-08-20, three jobs. (A) Source-clock adjudication: census
      measures the nightly accrual's real execution window (a normal collect crosses
      midnight ET while the resolved session stays the prior NYSE session, so the
      same-ET-day partial-replacement rule may refuse lawful repairs); Fable rules
      Option A (earlier close-proximate capture point) vs Option B (bounded lawful
      capture lease); any timing PR is held UNMERGED for Sol, no merge-on-green.
      (B) Credential/vendor closure is OPERATOR-EXTERNAL: revoke/rotate the exposed
      key, delete run 32077948964 logs, register the replacement as a real Actions
      secret, restore the option-chain entitlement (probe 2026-08-20T08:09Z: chain
      still 403, logs still served, no POLYGON/MASSIVE key in Actions secrets).
      (C) Production commissioning BLOCKED_EXTERNAL until (B) closes; then two
      consecutive healthy scheduled captures (S, D) and AD-1 end-to-end acceptance.
  - id: AD-2
    title: Evidence Receipts, Nulls, Lifecycle, Corrections
    status: todo
    depends_on: [AD-1]
    next_action: CLOSED until AD-1 production acceptance. Do not start.
landmines:
  - >-
    The entire host-side intraday options launchd fleet (15 units incl. the sparse-selector
    canary) is NOT loaded on the Mac Studio as of 2026-08-17 (verified launchctl probes,
    AD-0 ledger §2.3). Do not treat in-repo plists under ops/launchd/ as running machinery.
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
    HTTP 403 NOT_AUTHORIZED on /v3/snapshot/options/{symbol} is an account entitlement
    failure. Do not change base URL, retries, thresholds, endpoint paths, or AD-1 scoring
    to work around it. Polygon and Massive domains currently behave identically for this key.
  - >-
    Missing chain sessions 2026-08-14 / 2026-08-17 / 2026-08-18 are permanent (point-in-time
    OI). Do not hand-write those parquet files. Do not backfill them from ThetaData without
    a separate provenance/PIT ruling.
  - >-
    Cboe delayed quote pages expressly prohibit automated extraction. Not an AD-1 fallback.
decisions:
  - "DEC:AD-SIGNAL-VOCAB-RESTORES-SHORT"
  - "DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION"
  - "DEC:AD1C0-FIRST-WRITER-QUALITY-RULE"
discoveries:
  - "DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION"
do_not_redo:
  - >-
    Do not re-audit the seven sparse-selector PRs (#5747 #5694 #5696 #5708 #5711 #5790
    #5801) — reconciled with merge SHAs in the AD-0 ledger; #5711 is a closed duplicate of
    #5708; W1A-A/B modules are test-only with zero consumers.
  - >-
    Do not re-derive the EOD source map: Polygon snapshot (POLYGON_API_KEY then
    MASSIVE_API_KEY, ~18:30 ET, session-stamped) + massive.com OPRA aggs (NOT entitled
    to trades_v1/quotes_v1) + FINRA CNMS/ATS keyless. AD-0 ledger §4.
  - >-
    Do not resurrect darkpool direction labels (v2 null walk-forward + DNR:PSS-AF1) or the
    DOI/skew-decel families (killed).
  - >-
    Do not restart Polygon-vs-Massive domain-migration diagnosis. Re-proved
    2026-08-19T19:59:29Z and again 2026-08-20T05:23:23Z: both domains 403 on option
    chains and 200 on stock/news with the same linked key.
  - >-
    Do not treat an operator/CEO "entitlement restored" claim as live evidence.
    Re-run the bounded 8-probe plus a no-write adapter snapshot this session.
    2026-08-20 commissioning did that and still got 403.
  - >-
    Do not sweep 375 underlyings while the chain endpoint is 403. AD-1C0 short-circuits
    after a mixed-class auth probe.
  - >-
    Do not silently route AD-1 to ThetaData. collectors/thetadata.py already implements
    historical + snapshot OI, EOD chains, and Greeks/IV, and is NOT wired into
    polygon_gex / options_intel_brief. That is a later Sol-commissioned parallel-source
    adjudication, not this recovery.
  - >-
    Sparse selector / W1A is RESEARCH-ONLY. Do not resurrect before the AD-9 ruling.
next_action: >
  Owner restores/rebinds Massive Options Snapshot + daily OI + Greeks/IV on the
  linked key under a business/enterprise license. Then the normal scheduled
  nightly must produce two consecutive healthy captures (S then D, coverage_pct
  >= 0.90, no --force). Only then run AD-1 production acceptance. AD-2 stays closed.
artifacts:
  - research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md
  - research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md
  - research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md
---

## Context

AD-0 and AD-1P0 are done. AD-1 runtime is merged (PR #5872,
`661ad5d291aa687bbb0c7a33e5b573c60a2b148f`, 2026-08-19T13:25:26Z). AD-1C0
source-failure durability is merged (PR #5974,
`d5ebb5d9b3db8c12deed7c267676cb38b6b348dc`, 2026-08-19T16:04:26Z).

Production commissioning is SOURCE-BLOCKED. `site/options_intel_brief.json` is
still `board_state=STALE_SOURCE`, `as_of_session=2026-08-12`,
`oi_counted_date=2026-08-13`, empty opportunity/watch/event boards. The chain
store newest vintage is `data/polygon_gex/chains/2026-08-13.parquet`. Sessions
2026-08-14/17/18 are absent and must not be filled by hand.

AD-1C0 health machinery has now observed a scheduled run:
`data/polygon_gex_health/2026-08-19.json` (`health=failed`, `coverage_pct=0.0`,
`aborted_early`, 5/5 `auth_or_entitlement_failure` at
`capture_instant` 2026-08-20T01:00:18Z). `run_status.json`
`sources.polygon_gex_accrual` matches (`status=empty`, `health=failed`,
`checked_at` 2026-08-20T01:02:45Z). That failed vintage is not capture S.

Post-entitlement commissioning census 2026-08-20T05:23:23Z on
`origin/main` `e186f9f45c1bf0f55e774d836c7ee5df2fecccc7` re-proved CASE B
after a claimed restoration: option-chain snapshot 403 NOT_AUTHORIZED on both
vendor domains; stock snapshot and news 200. Production adapter dry-run on
[SPY, QQQ, IWM, AG, CDE] also 5/5 `auth_or_entitlement_failure`, 0 rows, no
write. Local key source name `MASSIVE_API_KEY` (POLYGON_API_KEY absent from
local env). GitHub Actions has `POLYGON_API_KEY` (secret metadata still
`updated_at` 2026-08-08T08:10:36Z); no `MASSIVE_API_KEY` Actions secret. The
2026-08-08 capability manifest recorded `options_chain_snapshot` HTTP 200
entitled with Greeks/IV/OI under `POLYGON_API_KEY`.

ThetaData remains a source-redundancy *candidate* only (`collectors/thetadata.py`,
theta-ops lane, not on the AD-1 path).
