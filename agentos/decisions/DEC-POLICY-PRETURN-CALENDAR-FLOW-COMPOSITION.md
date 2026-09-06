---
key: POLICY-PRETURN-CALENDAR-FLOW-COMPOSITION
question: >
  How should Mastermind model recurring OPEX/month-end turns, official policy events,
  Treasury liquidity and futures mechanics without creating a second market owner,
  an unexecutable test plan, a stale cross-lane publisher, a false machine consumer,
  or a calendar-driven trade signal?
answer: >
  Build one deterministic policy_turn_clock.v1 composition over existing event, release,
  OPEX, options, broad-flow, rebalance, Treasury/TGA, volatility, market-state and futures
  owners. Hourly is the sole official-event/current-artifact writer; the existing nightly
  regional-desk lane runs the same builder in ledger-only mode and appends only on explicit
  first-seen triggers. Reconcile publication per source so one regressing source preserves
  last-good truth without discarding another source's legitimate advance. Keep options and
  broad-market flow as separate axes; place cross-axis K-of-N only in support_composition.
  Preserve event venue apart from explicitly supported physical actor presence, preserve
  Treasury operation mechanism, purpose and separate amount fields, make silent source
  revisions correction-safe, and expose method/input/source identity. Standard VX
  settlement is monthly and separate from weekly fronts and quarterly equity/Treasury rolls.
  Policy Watch must carry deliberate dark command-center and light research-workspace art
  directions, and the existing Neural Web world-state producer is the durable direct machine
  consumer of site/policy_turn_clock.json. Calendar proximity and every W1 state remain
  context-only with can_rank/can_gate/can_size/can_trade=false.
rationale: >
  The Chairman's observed sequence is plausible only as a compound inventory, liquidity,
  flow and catalyst clock. Expiration can remove stabilizing long-gamma inventory or
  destabilizing short-gamma inventory; replacement may rebuild or fail; month-end may
  combine broad ETF flow, observed rebalancing, asset-specific bond-index extension and
  Treasury cash movement; standard VIX futures settle monthly while major equity-index and
  Treasury futures roll quarterly; macro events can dominate every mechanical clock.
  Existing repository organs already own each underlying truth and Neural Web already owns
  the durable machine-context projection. Independent review of the first repaired candidate
  then found six additional implementation-contract blockers: the plan prescribed a
  forbidden sibling/codex worktree shape, the promised direct machine consumer was unnamed,
  the material Policy Watch UI had no binding dual-theme art packet, prospective evidence
  could still be implemented as unconditional nightly append, whole-payload no-regress could
  regress one source or discard another source's advance, and a cross-axis K-of-N assertion
  lived inside option_support. The forward repair closes these without widening product or
  authority: harness-native session roots plus explicit sparse opt-in, existing Neural Web
  direct consumption, binding dark/light evidence, trigger-gated append tests, per-source
  monotonic reconciliation, and a separate support_composition block. This creates useful
  anticipatory context without laundering calendar folklore, source ambiguity, presentation
  styling or model narrative into capital authority.
alternatives:
  - option: "Create a universal buy-at-month-start and de-risk-after-OPEX signal."
    why_not: >
      The unconditional effect is era-dependent; options expiration can remove either
      stabilizing or destabilizing inventory; current in-repo evidence withholds a robust
      universal post-OPEX direction. A calendar trade would be empirically fragile and
      violate existing authority law.
  - option: "Create a standalone policy calendar, futures database, transition score or machine API."
    why_not: >
      Event Calendar, Macro Release Intelligence, OPEX, ThetaData options, Rebalance Pulse,
      ETF flows, Treasury Watch, Cboe VX, current market-state/volatility and Neural Web
      already own those truth/projection planes. New stores, weighted scores or a sibling
      machine endpoint would fork truth, correction clocks and authority.
  - option: "Run collection, current publication and prospective evidence from both hourly and nightly lanes."
    why_not: >
      Two writers with independent concurrency/rebase behavior can regress evidence and
      create duplicate receipts. Hourly single-writer plus trigger-gated nightly ledger-only
      is the smallest composition over existing workflows.
  - option: "Reject an entire current payload whenever any individual source watermark regresses."
    why_not: >
      A mixed candidate can contain a legitimate source-A advance and a source-B regression.
      Whole-payload rejection loses current truth; wholesale acceptance regresses B. Per-source
      reconciliation keeps A's advance while preserving B's last-good evidence and exposes the
      regression.
  - option: "Store options, broad ETF flow and the two-mechanism count together in option_support."
    why_not: >
      Broad ETF flow has a different owner, availability lag, coverage history and meaning.
      Combining it into the options axis makes provenance and null behavior ambiguous. The
      K-of-N result belongs to a separate composition block.
  - option: "Use an LLM to infer private actor location, coordination or intervention timing."
    why_not: >
      Private timing and physical presence are not identifiable from public calendars or
      aligned interests. Model text may later narrate grounded receipts but cannot create
      source facts or W1 state.
  - option: "Let the implementation worker invent worktree placement, UI art direction, CI ownership or consumer proof."
    why_not: >
      Those are architecture and authority decisions. Delegating them recreates the exact
      ambiguity independent review surfaced and risks duplicate systems or false proof.
evidence:
  - "Chairman Chris explicitly approved initiation and instructed Sol to continue at full throttle in the active session on 2026-09-03."
  - "Protected modifying procedure was fresh-repinned during the six-finding forward repair to mastermindx-market-intelligence/Mastermind@da6af515c95301377fb5fd8748e374a8948a3540; Skillpack v1.0.1 remains bootstrap-major-1 compatible."
  - "The prior architecture review on exact head f1edb549... returned six accepted forward blockers on Slack review root C0BSBM78V1N/1788428719.687049 through HOLD 1788431377.783489: worktree law, unnamed durable machine consumer, absent dark/light packet, unconditional-nightly ledger risk, insufficient per-source no-regress, and option/broad-flow cross-axis K-of-N."
  - "Macro AGENTS.md on current main requires harness/session-root worktrees, forbids codex/ branches, and requires scripts/worktree_sparse.py add/full before writes into omitted data/site/mockups trees."
  - "engine/neuralweb/world_state.py is the existing canonical Neural Web N1 machine projection; docs/SIGNAL_BUS.md names data/neuralweb/world_state.json as its output and scripts/build_world_state.py as the thin call path. Fresh open-PR search found no current owner of engine/neuralweb/world_state.py or tests/test_world_state.py at repair time."
  - "Current open-PR census during repair still found .github/ci/legacy-jobs.yml owners #6721, #6706, #6651, #6625, #6514, #6389 and #6296; .github/workflows/ci.yml remained owned by #6628; #6791 had merged. W1 therefore retains a fresh START-time all-owner census gate."
  - "collectors/cboe_vix_futures.py and its existing stores distinguish nearest weekly-or-monthly front from standard monthly M1-M6; W1 consumes those owners and suppresses rank-roll false changes."
  - "engine/etf_flows.py documents the SPY/QQQ/IWM/RSP/DIA broad-flow proxy as forward-accruing, T+1 and display-only; W1 preserves that lag and limitation as a separate axis."
  - "reports/artifacts/options_surface_coverage.md proves canonical options coverage for 20 roots, mostly 2017 onward; issue #6794 separately freezes historical versus prospective study cohorts."
  - "reports/d2-rates-calendar-flows-phase0.md finds asset-specific TLT/IEF month-end extension while generic auction/pension variants fail, requiring separate duration context rather than a generic equity flow claim."
affects:
  - "WS:RATES-INFLATION-COMMAND"
  - "Policy Transmission & Pre-Turn Command"
  - "policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001"
  - "policy_turn_clock.v1"
  - "collectors/policy_event_clock.py"
  - "engine/futures_roll_calendar.py"
  - "engine/policy_turn_clock.py"
  - "scripts/build_policy_turn_clock.py"
  - "engine/neuralweb/world_state.py"
  - "tests/test_world_state.py"
  - ".github/workflows/whitehouse-sentinel.yml"
  - "scripts/ci/daily_engine_regional_desk_builders.sh"
  - ".github/workflows/ci.yml"
  - ".github/ci/legacy-jobs.yml"
  - "site/policy_turn_clock.json"
  - "data/neuralweb/world_state.json"
  - "site/policy_watch.html"
  - "mockups/refs/policy-turn-clock/**"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-09-03
---

# Binding ruling

## One canonical composition

`policy_turn_clock.v1` is a pure deterministic composition and projection. It does not own underlying event, release, options, OPEX, flow, Treasury, market-state, futures, Neural Web or portfolio truth. Every axis carries owner, as-of/available-at, freshness, assumption, correction and null evidence.

The closed glance vocabulary is:

```text
SUPPORT_BUILDING
SUPPORT_STABLE
PINNED
SUPPORT_ROLLOFF_IMMINENT
VOLATILITY_WINDOW_OPEN
MONTH_END_REBALANCE_DOMINANT
CATALYST_DOMINANT
MIXED
UNKNOWN
```

No state is a score or position instruction.

## Evidence ruling

Official evidence preserves stable event identity, explicit/fallback revision identity, canonical semantic digest and keep-FIRST receipts. A reused revision token with changed semantic content is a visible collision. Formatting-only page changes do not create vintages.

Event location, attendance mode and actor physical presence are distinct. Current physical location requires explicit official live-presence support; scheduled, virtual, prerecorded, ambiguous, cancelled and ended appearances leave it unknown.

Treasury operation mechanism and purpose are distinct. A cash-management or liquidity-support case remains `operation_kind=buyback` when it is a buyback, with an explicit purpose. Maximum, offered, submitted and accepted amounts remain separate nullable fields.

## Monthly mechanism and axis ruling

1. OPEX proximity never establishes dealer sign or direction.
2. Stabilizing and destabilizing expiration configurations remain opposite cases.
3. Replacement evidence requires comparable canonical observations; missing is unknown.
4. `option_support` contains options/OPEX-owner evidence only. It cannot contain broad-market flow, Treasury support, breadth/credit confirmation or any cross-axis K-of-N count.
5. `broad_market_flow` remains a distinct canonical owner projection with its true T+1/short-history limitations.
6. `support_composition` is the only block that counts independent support families. `SUPPORT_BUILDING` requires at least two independent applicable supporting mechanisms there, not option replacement alone.
7. Month-end scheduled eligibility, pressure estimate and observed mechanical pulse are distinct; dominance requires observed pulse.
8. Bond-index extension is an asset-specific duration context, not a current equity flow claim.
9. Standard VX settlement is monthly; weekly fronts and quarterly equity/Treasury rolls remain separate.
10. `VOLATILITY_WINDOW_OPEN` requires fresh independent market/volatility/breadth/credit confirmation.
11. High-impact official catalysts may override mechanical windows without gaining capital authority.

## Runtime ruling

Hourly White House Sentinel is the sole official-event and current `site/policy_turn_clock.json` writer. Healthy semantic no-op reruns remain byte-stable.

Publication is reconciled **per source**. An older incoming source cannot lower its published watermark or erase last-good evidence. A mixed candidate with source A advancing and source B regressing accepts A, preserves B's last-good block/watermark, exposes B's regression and recomputes state from the accepted evidence set. Failure/stale transitions preserve last-good evidence. Valid corrections preserve original lineage. Whole-payload cutoff comparison never substitutes for this law.

The existing nightly regional-desk owner invokes `scripts.build_policy_turn_clock --mode ledger-only` immediately before Policy Watch. It does not collect evidence or publish current JSON/UI. It may append at most one keep-FIRST receipt only through `engine.ledger_lane.nightly_advance_enabled()` **and only when one explicit eligible first-seen trigger is present**. Nightly with no eligible trigger appends zero rows. The append seam itself enforces the lane. Corrections append linked rows and never rewrite originals.

`config/dag.yml` mirrors real execution; it is not an executor.

## Session/worktree ruling

The W1 plan may not prescribe a manual `../` sibling worktree or `codex/` branch. The implementation receiver uses the current repository's harness-native/session-root worktree procedure. Because session worktrees are sparse, any planned `data/`, `site/` or `mockups/` read/write/build must first opt in with `python3 scripts/worktree_sparse.py add <tree>` or `full`. Sparse omission is never evidence of absence, and omitted-tree writes may not be staged.

## Durable machine-consumer ruling

The direct machine consumer is the existing Neural Web N1 world-state plane:

```text
owner:       engine/neuralweb/world_state.py
input:       site/policy_turn_clock.json
output:      data/neuralweb/world_state.json -> policy_turn_clock lobe
call site:   build_world_state()/build_and_write(), invoked by scripts/build_world_state.py
proof:       tests/test_world_state.py
```

It reads the JSON directly, preserves method/input/state/independent axes/gaps/all-false authority, and follows existing fail-open behavior on missing/corrupt/invalid input. It does not parse Policy Watch HTML or recompute a second turn state. No new machine API/store/bus is authorized.

## Policy Watch design ruling

Policy Watch is a material UI packet and must implement two deliberate art directions over one semantic system:

- **Dark:** command center — luminance depth, calm instrument wells and restrained glow only for fresh/current emphasis. Degraded removes glow and uses a precise segmented/dashed warning mechanism; unknown is neutral graphite with explicit missing evidence.
- **Light:** research workspace — cool canvas, white material, graphite type, hairline discipline and modest shadow instead of glow. Degraded uses a mechanically distinct caution rail/hatch while retaining readable white material; unknown is an explicit neutral research sheet without pale-green “fine” implication.

Token substitution alone is not proof. The evidence matrix is binding:

```text
dark/light × EN/ZH × 1440/390
```

covering fresh/support, rolloff, catalyst, degraded, unknown and conflict, plus 768 geometry/function checks. Canonical design tokens/components remain authoritative; no parallel token root or opaque runtime stylesheet is allowed.

## CI ruling

Every new suite must be executed by one canonical logical job in `.github/ci/legacy-jobs.yml` and triggered through `.github/workflows/ci.yml`. The policy-turn additions to `tests/test_world_state.py` execute through the existing Neural Web owner. W1 waits until all current owners of the shared manifest/workflow paths are released. It may not bypass the hold with another workflow, job, planner or unrun-test exemption.

Required executable contract coverage includes:

```text
nightly ineligible-trigger no-op
all eligible trigger families
receipt identity / keep-FIRST
correction link + immutable original
direct off-lane append refusal
mixed-source advance/regression
last-good preservation on failure/regression
valid correction no-regress
options/broad-flow axis separation
Neural Web direct JSON consumer
Policy Watch dark/light evidence receipt completeness
```

## Authority ceiling

Every W1 artifact remains:

```json
{"can_rank": false, "can_gate": false, "can_size": false, "can_trade": false}
```

A later request for ranking, gating, sizing or trading is a new Chairman/Sol decision after issue #6794 evidence and the existing promotion gauntlet.