---
workstream: WS:STOCK-IDENTITY
session: sol/stock-identity-w3ar-recovery-20260829
model: codex
mission: >
  Commission SI-W3S-DEAD-CONTROL-V1 as the independent survivorship predecessor:
  deterministically produce at least five identity-resolved terminated U.S. instruments
  with lawful full adjusted OHLCV compatible with existing Stock Identity machinery, or
  return BLOCKED_NO_LAWFUL_DATA without widening providers or criteria.
state_before: >
  W1 had proven the original allowed planes could not supply a five-name terminated
  control cohort, and W2 registered W3S as a hard predecessor to W5/Q1. The prior W3S
  inventory returned NEEDS_BOUNDED_SOURCE_ACT; Sol allowed only deterministic terminated-
  ledger extension plus reuse of the existing Polygon/dead-name owner. No lawful W3S
  receiver was bound.
changed:
  - path: agentos/handoffs/STOCK-IDENTITY-2026-08-29-W3S-DEAD-CONTROL-RESTART.md
    what: >
      Creates the bounded W3S commission packet, deterministic sampling/data law, receipt
      requirements, failure states, and STOP boundaries for a later lawful receiver.
  - path: agentos/workstreams/WS-STOCK-IDENTITY.md
    what: >
      Restores W3S as an independent W2-dependent predecessor while keeping W3B/W5 gates closed.
prs: [6672]
verified:
  - claim: W3S is independent of W3A/W3AR and remains a hard predecessor to W5/Q1.
    command: "open agentos/workstreams/WS-STOCK-IDENTITY.md and research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md"
    result: "W3S depends on W2; W5P depends on W3S and W4B."
  - claim: The accepted bounded source law does not authorize a second market-data platform.
    command: "open agentos/handoffs/STOCK-IDENTITY-2026-08-29-W3S-DEAD-CONTROL-RESTART.md"
    result: "Only deterministic terminated-ledger extension plus reuse of the existing Polygon/dead-name owner is permitted."
  - claim: An invalid-placement W3S session created PR #6678 but reversed all mainline risk after Sol's no-start reconciliation.
    command: "gh pr view 6678 --repo mastermindx-market-intelligence/macro --json state,isDraft,mergedAt,headRefOid"
    result: "CLOSED, DRAFT, unmerged at e98a6e593f9d786478d0076cb33878c6d1c2da28; no commit reached main."
  - claim: AVB's registered stocks-plane heal was followed by a later commit touching data/stocks/AVB.parquet.
    command: "gh api 'repos/mastermindx-market-intelligence/macro/commits?path=data/stocks/AVB.parquet&per_page=10'"
    result: >
      Heal commit 21f6a9867ad2165c88158c75865ae8e064a67a41 explicitly truncated AVB at 2026-08-14;
      later daily collection commit 27aebb3606cb3b2095f808de917516ae31b7ea35 modified the same parquet on 2026-08-29.
unverified:
  - claim: The current AVB parquet still contains successor bars after its registered last_session.
    what_would_verify: >
      Independently read the current main parquet and compare its maximum real-volume session and
      adjusted basis against config/delisted_symbols.yml last_session=2026-08-14 and the #6623
      healed blob. The unauthorized W3S session's value-level claim is not accepted as proof.
  - claim: A lawful currently authorized W3S rerun can obtain at least five controls.
    what_would_verify: >
      A lawfully bound receiver must commit the candidate/sampling law before tape-dependent
      inclusion, re-derive the full candidate/exclusion ledger, and prove >=5 compatible tapes or
      return the typed blocker under current owners and current identity evidence.
unresolved:
  - W3S still requires a lawful receiver-assignment edge; current state is WAITING_CAPACITY / needs_placement.
  - PR #6678 is inert audit evidence only; none of its cohort/verdict outputs are accepted as W3S scientific results.
  - AVB requires independent current-file verification because a daily collection commit touched it after the explicit successor-splice heal.
  - Existing open delisted/security-identity PRs must be reconciled before extending any terminated ledger owner.
next_actions:
  - Keep PR #6678 closed/unmerged and preserve its branch as inert evidence; do not reuse its verdict as a shortcut.
  - Bind one eligible W3S receiver through an authorized placement/commissioning edge.
  - Before any cohort build, reconcile current delisted/security-identity owners and independently verify/quarantine the AVB post-heal regression if present.
  - Commit the deterministic candidate/sampling/exclusion law before tape-dependent inclusion, then return RESULT or BLOCKED_NO_LAWFUL_DATA with exact evidence.
do_not_redo:
  - Do not infer death from index exit, vendor absence, stale tape, or OTC directory absence.
  - Do not hand-pick five names after inspecting tapes, paths, episodes, returns, expert fires, or outcomes.
  - Do not create a second market-data/identity plane or use unproven AVB/close-only substitutes.
  - Do not treat the unauthorized #6678 result as accepted evidence or reopen/merge it without fresh lawful authority.
  - Do not open W5/Q1/Prophet work from this commission.
danger_areas:
  - Delisted/rename/key-migration owners are collision-prone; current open identity PRs may touch the same ledger paths.
  - A successor splice on a registered adjusted price plane can corrupt every downstream behavioral consumer while looking fresh.
  - A finished tape must be distinguished from flat-forward vendor padding and from a different successor security's continuing tape.
  - Receiver attention/ACK without a lawful commissioning edge is not lifecycle authority.
ended_because: blocked
---

# W3S Restart — Dead Instrument Control Set

**Operation:** `SI-W3S-DEAD-CONTROL-V1`  
**Parent:** `SI-FABLE-COO-PROGRAM-20260828`  
**Current operational state:** `WAITING_CAPACITY / needs_placement`. Invalid Secretary placement produced an unauthorized branch/PR #6678; Sol contained it, the PR is closed unmerged, and its scientific verdict is not accepted. It remains inert audit evidence only.

## Observable mission

Produce either (a) a preregistered, identity-resolved cohort of at least five terminated U.S. instruments with lawful full adjusted OHLCV that runs through existing Stock Identity fingerprint/episode machinery, or (b) the typed terminal blocker `BLOCKED_NO_LAWFUL_DATA`. Nothing less may unblock W5/Q1 survivorship.

## Why now

W3S depends on W2, not on W3A. It was unnecessarily stalled behind the failed W3A calibration attempt. Restarting it now can burn down an independent hard predecessor once lawful capacity is available.

## Authority / precedence

1. current Chairman end-to-end recovery intent;
2. current protected Skillpack at pickup;
3. original Stock Identity masterplan survivorship law;
4. W1 registration's measured dead-name impossibility on the original allowed planes;
5. W2 registration: Dead Instrument Control Set is a separately registered hard W5/Q1 predecessor;
6. accepted W3 freeze / W3 plan;
7. prior Sol ruling in parent thread: minimum preregistered delisted-ledger + existing Polygon dead-name collector OHLCV persistence extension is inside W3S authority; no second market-data platform.

## Verified starting truth

- `config/delisted_symbols.yml` was historically too sparse for W1 and the original W1 planes could not produce the required dead cohort.
- W1 substitution over ceased tapes found no lawful dead cohort on its allowed planes.
- The prior W3S inventory concluded `NEEDS_BOUNDED_SOURCE_ACT` rather than pretending survivors were controls.
- Prior Sol ruling permits one minimum source act: extend the terminated-instrument ledger deterministically and reuse the existing Polygon/dead-name collection owner to persist the OHLCV fields it already receives.
- Any AVB tail/other unproven fallback is not trusted merely because it has close history.
- Current AVB durability is specifically suspect: #6623 says `data/stocks/AVB.parquet` was healed/truncated to 2026-08-14, but a later daily collection commit touched that same parquet. A lawful W3S receiver must independently verify current bytes before using AVB.

## Exact scope

Fresh branch/carrier under operation `SI-W3S-DEAD-CONTROL-V1` only after a lawful receiver assignment.

Expected ownership surfaces only after fresh archaeology confirms current paths:

- existing terminated/delisted identity ledger owner;
- existing Polygon/Massive dead-name collection path **as owner reuse**, not a new collector plane;
- `engine/stock_identity/dead_control.py` / `scripts/stock_identity_build_dead_control.py` and focused tests if still appropriate under current main;
- `data/stock_identity/control/` manifest/receipts only;
- `research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md`;
- Agent OS handoff/workstream updates.

Do not touch W3AR/W3A ruler constants, Q1, Prophet, Radar, or unrelated data platforms.

## Deterministic sampling law

Before acquiring/validating OHLCV, register the candidate population and ordering from lawful terminated-instrument identity facts only. Membership may depend on termination status/date/reason, U.S.-instrument identity, source entitlement/rights, minimum required history horizon and basic data-field availability. It may not depend on subsequent Stock Identity episodes, returns, drawdowns, expert fires, localization or any outcome.

Do not hand-pick five names after seeing tapes. Preserve every eligible candidate and every exclusion reason.

## Required instrument receipt

Each accepted control requires:

- stable instrument identity + ticker-history/reuse hygiene;
- terminal reason and terminal date with source;
- price source/owner and rights note;
- adjusted OHLCV mode and corporate-action semantics;
- first/last observation and coverage counts;
- known-at/correction behavior;
- immutable source/content hash;
- proof the tape is terminated rather than merely stale/index-exited;
- compatibility with current `engine.stock_identity.fingerprint` and `engine.stock_identity.episodes` inputs.

Missing is not zero. A candidate without lawful full adjusted OHLCV is an exclusion, not a partial control.

## Source/data law

Reuse current canonical owners first. The permitted bounded source act may persist OHLCV already returned by the existing Polygon/dead-name owner for the preregistered terminated cohort. It must not create a generalized second price-history platform, hidden cache, new identity authority or alternate corporate-action truth.

If the existing owner cannot lawfully supply at least five compatible terminated tapes, stop with `BLOCKED_NO_LAWFUL_DATA`. Do not widen providers or relax adjustment/history/identity requirements without Sol.

## Method

Deterministic identity/data validation only. No model, no expert fit, no ranking, no calibration, no outcome selection.

## Failure states

- `BLOCKED_NO_LAWFUL_DATA` — <5 lawful full-adjusted terminated tapes after preregistered population/exclusions;
- `IDENTITY_UNRESOLVED` — ticker/entity continuity insufficient;
- `ADJUSTMENT_UNPROVEN` — tape cannot satisfy current behavioral-math adjustment law;
- `RIGHTS_UNRESOLVED` — source cannot be lawfully persisted/used;
- `SOURCE_OWNER_CONFLICT` — proposed act would duplicate or bypass an existing owner;
- `WATCH_UNAVAILABLE` — worker cannot maintain return loop.

## Acceptance tests / real proof

- preregistration committed before tape-dependent inclusion decisions;
- deterministic rerun produces same cohort/exclusion ledger;
- reused-ticker hostile fixtures fail;
- live/stale-but-not-terminated ticker relabeled dead fails;
- raw/unadjusted plane fails;
- every accepted tape passes existing fingerprint/episode compatibility smoke;
- no new generic collector/data-plane owner appears in diff;
- exact-head hosted CI for the bounded W3S job;
- real build returns >=5 accepted instruments or the typed blocker;
- Agent OS truth updated without calling blocked data success.

## Stop condition

Return `RESULT SI-W3S-DEAD-CONTROL-V1` (or typed `BLOCKED_NO_LAWFUL_DATA`) with exact PR/head, candidate/exclusion counts, accepted instrument receipts, current-main collision proof, CI, and real compatibility smoke. Then wait for Sol. Do not open W5 or absorb W3B.

## Routing

Preferred avenue: **Terra / CTO Sol-class bounded engineering**. A concrete receiver must be bound by an authorized placement/commissioning principal; Secretary attention transport or an unbound ACK is not assignment. Fable remains parent COO and may coordinate/review but should not consume scarce principal capacity for the mechanical owner-extension/build once the contract above is clear.
