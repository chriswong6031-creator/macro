---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session: claude/ad1t0-thetadata-source-cutover
model: fable
ended_because: done
mission: >
  Sol/Chairman AD-1T0 directive: record the Chairman source ruling (ThetaData
  = canonical options source), correct the workstream's durable state, census
  the live T1 estate, rule contract identity, cut the AD-1 producer over to
  the ThetaData store with engine byte-unchanged, and prove against the newest
  lawful real S/D pair. Return to Sol before AD-2.
state_before: >
  WS blocked on the retired Massive/Polygon entitlement (needs_ceo gate);
  AD-1 BUILT_NOT_PROVEN with the producer reading the frozen polygon_gex
  estate (chains end 2026-08-13); site/options_intel_brief.json committed as
  STALE_SOURCE (as_of 2026-08-12); ThetaData "candidate only" with a standing
  do-not-route prohibition; T1 store health/coverage unmeasured.
changed:
  - path: agentos/decisions/DEC-AD-OPTIONS-CANONICAL-SOURCE-THETADATA.md
    what: Chairman ruling minted — ThetaData canonical for options truth; blocker/needs_ceo retired; Terminal keeps intraday authority; v1.2 frozen; Q_flow absent; no duplicate collector.
  - path: agentos/workstreams/WS-ADVANCED-DATA-OPTIONS.md
    what: blocked→active; Massive blocked_by + needs_ceo removed; ThetaData prohibition row superseded in place; wave AD-1T0 added (done); AD-1C0/AD-1C0.1 reclassified legacy hardening.
  - path: research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md
    what: contract-identity ruling (source tuple → engine's existing strike_ticker serialization, fail-closed assertions) + frozen adapter spec (PIT mapping, pair predicate with capped S-role demotion, spot ladder, receipts, off-host self-skip), amended across three review rounds.
  - path: scripts/build_options_intel_brief.py
    what: full I/O-layer cutover to resolve_thetadata_store() — chain frames from eod/oi/greeks with per-contract identity, chain_next from the OI tier only, price_ladder rung-2 spot, greeks-history summary_spot, gex_confirm hard-disabled, per-(session,tier) receipt digests + spot_authority/session_presence/store_resolution receipts, ::warning+exit-0 self-skip off-host.
  - path: tests/test_options_intel_brief.py
    what: fixture family refit to a synthetic ThetaData store; ~25 new ad1t0 tests incl. flip-verifications of every review finding; seed-stable (hash-salt fix).
  - path: contracts/options/OPTIONS_INTEL_BRIEF_V1.md
    what: §2 input table + B1 receipt-closure prose re-pointed to ThetaData logical sources with the dated cutover note; v1.2 semantics text untouched.
  - path: site/options_intel_brief.json
    what: production artifact built ON the m1 store-bearing host from the real T1 store — S=2026-08-19, D=2026-08-20, receipt 637d0c60..., honestly INSUFFICIENT_COVERAGE (0.104), zero Polygon references.
  - path: research/ADVANCED_DATA_OPTIONS_EOD_AD0_CURRENT_STATE_AND_CAPABILITY_LEDGER_2026-08-17.md
    what: stale "Canonical EOD options source = Polygon" answer superseded in place.
  - path: agentos/discoveries/DSC-THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS.md
    what: the coverage blocker minted as a discovery (48-root nightly refresh vs 375-universe; r2sync broken; store host not a runner).
verified:
  - claim: the live T1 store is healthy, identity-clean, and 39/375 daily-current
    command: "ssh m1 read-only census (store tiers/roots, Terminal :25503 v3 probe, launchd lanes, backfill.log) + per-session coverage and identity python probes on the plane conda env"
    result: eod/oi/greeks 381 roots; Terminal HTTP 200; tuple (root,expiration,strike,right) unique per tier/session across 9 sessions 2013→2026 with 0 conflicting duplicates; strikes integral in thousandths; coverage uniform 39/372 over the last 20 sessions; store tip 2026-08-20
  - claim: the cutover preserves the frozen engine and v1.2 semantics
    command: "git diff 449b8f1d0a2a HEAD -- engine/ | wc -l; PYTHONHASHSEED={1,2,3} python3 -m pytest tests/test_options_intel_brief.py tests/test_gh_annotation_line_start.py -q"
    result: engine diff 0 across every commit; 143 passed + 1 deliberate skip on every seed
  - claim: three adversarial opus review rounds concluded SHIP with every finding closed
    command: "review round 1 (BLOCK: B1/B2/B3 + M1-M4 + minors) -> repair bd771a9e084c; verify round (FIX-THEN-SHIP: N3/N4/N2/N5) -> repair 5d7d4e81c3d7; round 3 (SHIP) after b51f90b58c6c (capped demotion + legible diagnostics), incl. an exhaustive 3,964-shape proof that a capped-adoption S cannot pass the coverage gate"
    result: every finding re-verified against its original reproduction; final verdict SHIP
  - claim: the producer runs against the real store and produces the honest board
    command: "rsync branch tree to m1:/tmp/ad1t0-proof; plane python -m scripts.build_options_intel_brief"
    result: S=2026-08-19 D=2026-08-20 pending=08-20 OI_NOT_YET_SETTLED; INSUFFICIENT_COVERAGE cov=0.104 universe=375 present=39; receipt 637d0c60...; no polygon refs; _run diagnostics present
  - claim: the scoring pipeline is production-capable on real ThetaData bytes (contract §8 feasibility debt discharged)
    command: "DIAGNOSTIC-ONLY m1 run: universe monkeypatched to the 39 covered names + ignore_staleness=True (never production semantics)"
    result: 39/39 eligible, board OK, real top-six (AMZN/AVGO/PLTR/MSFT/SPY/GOOGL VOLATILITY), event=4, risk=4, no_signal_exemplar=QQQ, 0 identity exclusions
unverified:
  - claim: the served production Options Workspace renders the new artifact (desktop light/dark, mobile, EN/ZH)
    what_would_verify: post-merge covering render + VPS pull, then browser evidence on www.mastermind-x.com/options.html — owned by this session's ship chain (in flight at handoff-write time)
  - claim: AD-1 PROVEN_LIVE
    what_would_verify: Sol-authorized spine-cadence wave brings daily coverage >= 0.90, then the full §12 proof (real top-six from production semantics, board not degraded) on a future lawful pair
unresolved:
  - "T1 spine daily refresh = 48 roots vs 375-universe (DSC:THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS) — Sol decision on an incremental-refresh wave."
  - "Store-bearing M1 is not a GH runner (daily.yml RE-PIN RULE) and thetadata-r2sync is broken (publish_r2 symlink rglob; chipped as task_c138ddbd) — until one lands, the nightly engine-job producer self-skips and the committed artifact serves as the honest board."
next_actions:
  - Return the AD-1T0 verdict to Sol (AD-1 = BUILT_NOT_PROVEN; exact blocker = the spine DSC). Do not start AD-2.
  - On Sol's spine authorization - a bounded wave for incremental T1 refresh + the topology choice (M1 runner re-pin vs r2sync heal + runner pull).
do_not_redo:
  - The contract-identity census and ruling (spec §A; measured clean; no better first-party identifier exists — the v3 API echoes the request root).
  - The S/D pair law and committed-session predicate (spec §C: plaus + capped S-role demotion + OI-only frontier X; reviewed, property-tested, exhaustively bounded).
  - The oi/eod match-rate floor basis (organic min 0.825 over 144 recent root-sessions; floor 0.60 — spec §A #7).
  - Reaching for coverage via universe shrinkage, store-derived universes, store copies, or a second Terminal/collector (all prohibited; see the DSC so_what).
danger_areas:
  - engine/options_intel_brief.py is FROZEN v1.2 — the entire wave was built around zero engine edits; any engine change reopens Sol review.
  - OI timING law - oi[t] = positions at EOD t-1; the ΔOI baseline is oi[S], the next print oi[D]; same-day OI in an S feature is a lookahead bug (three review rounds defended this seam).
  - site/gex/*.json is legacy-Polygon provenance and is HARD-disabled in the producer (not date-gated); re-enabling requires a ThetaData-backed mechanics wave.
  - Q_flow stays structurally ABSENT; ThetaData trade+NBBO activation is a future model-version decision (directive §10).
  - The m1 flow-ops-wt checkout is detached on a FORK remote (chriswong6031-creator/macro) — never treat it as a canonical pusher; proof runs rsync the branch tree to /tmp/ad1t0-proof and use the plane conda python.
  - The repo data/thetadata_eod is an empty stub the resolver refuses BY DESIGN; never special-case it, never weaken the off-host self-skip (::warning + exit 0 + bytes untouched).
---

# AD-1T0 — ThetaData canonical source cutover (2026-08-22)

Chairman ruling executed end-to-end in one session: durable-state correction,
live census, PIT reconciliation, identity ruling, bounded cutover build, three
adversarial review rounds (verdict SHIP), and a real-store production artifact.
AD-1 remains BUILT_NOT_PROVEN solely on the spine-coverage blocker recorded in
`DSC:THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS`. Full technical law lives in
`research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md`.
