---
workstream: WS:STOCK-IDENTITY
operation_key: SI-W3S-DEAD-CONTROL-V1
parent_operation: SI-FABLE-COO-PROGRAM-20260828
preferred_avenue: terra
status: commissioned_unclaimed
wave: W3S
repository: mastermindx-market-intelligence/macro
base_sha: 07e63c5877c1638ee533843d4f2b477c9a148176
---

# W3S Restart — Dead Instrument Control Set

## Observable mission

Produce either (a) a preregistered, identity-resolved cohort of at least five terminated U.S. instruments with lawful full adjusted OHLCV that runs through existing Stock Identity fingerprint/episode machinery, or (b) the typed terminal blocker `BLOCKED_NO_LAWFUL_DATA`. Nothing less may unblock W5/Q1 survivorship.

## Why now

W3S depends on W2, not on W3A. It was unnecessarily stalled behind the failed W3A calibration attempt. Restarting it now burns down an independent hard predecessor while W3AR resolves the calibration science.

## Authority / precedence

1. current Chairman end-to-end recovery intent;
2. current protected Skillpack at pickup;
3. original Stock Identity masterplan survivorship law;
4. W1 registration's measured dead-name impossibility on the original allowed planes;
5. W2 registration: Dead Instrument Control Set is a separately registered hard W5/Q1 predecessor;
6. accepted W3 freeze / W3 plan;
7. prior Sol ruling in parent thread: minimum preregistered delisted-ledger + existing Polygon dead-name collector OHLCV persistence extension is inside W3S authority; no second market-data platform.

## Verified starting truth

- `config/delisted_symbols.yml` was historically too sparse for W1: two rows and no compatible price files.
- W1 substitution over ceased tapes found no lawful dead cohort on its allowed planes.
- The prior W3S inventory concluded `NEEDS_BOUNDED_SOURCE_ACT` rather than pretending survivors were controls.
- Prior Sol ruling permits one minimum source act: extend the terminated-instrument ledger deterministically and reuse the existing Polygon/dead-name collection owner to persist the OHLCV fields it already receives.
- Any AVB tail/other unproven fallback is not trusted merely because it has close history.

## Exact scope

Fresh branch/carrier under operation `SI-W3S-DEAD-CONTROL-V1`.

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

Preferred avenue: **Terra / CTO Sol-class bounded engineering**; Chairman selects the concrete quota account. Fable remains parent COO and may coordinate/review but should not consume scarce principal capacity for the mechanical owner-extension/build once the contract above is clear.
