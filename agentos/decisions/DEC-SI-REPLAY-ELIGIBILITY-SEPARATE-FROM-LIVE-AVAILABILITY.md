---
key: SI-REPLAY-ELIGIBILITY-SEPARATE-FROM-LIVE-AVAILABILITY
question: >
  After W3A Attempt-1 consumed P1 under an unlawful historical eligibility population,
  what availability architecture governs recovery without deleting W2's registered replay
  substrate or weakening the prospective-only law?
answer: >
  RATIFIED: historical research replay eligibility and live/prospective availability are
  separate epistemic clocks. Historical eligibility exists only through the exact W2-
  registered ledger, PIT recompute, locked-spec backcast, store-vintage, or frozen price-
  reference construction with required PIT inputs. Live/prospective availability remains
  the real deployment/known-at clock. Class P is prospective-only under both the old and
  recovered program. Generic spec/code existence and output fire timestamps establish
  neither historical source coverage nor a live deployment fact.
rationale: >
  W2 explicitly registered stored-ledger extraction, era-pinned recomputation and Class-B
  locked-spec backcasts while explicitly excluding Class-P backfill. Treating actual software
  deployment date as the only historical research clock would retroactively erase accepted W2
  research objects; treating all current specs as historically available would repeat Attempt-1's
  overreach. The two-clock model preserves both contracts without touching outcomes.
alternatives:
  - option: Treat actual live deployment/source availability as the sole clock for all historical research replay.
    why_not: >
      That would erase W2's explicitly registered ledger/recompute/locked-spec historical research
      substrate instead of enforcing its PIT input contract.
  - option: Treat every current W2 Class-R/B specification as historically available whenever price history exists.
    why_not: >
      That repeats Attempt-1's overreach: current code/spec existence is not date-specific source/input
      coverage, ledger-only families gain no backcast path, and Class P remains prospective-only.
  - option: Re-read or reseal the consumed P1 partition after repairing availability semantics.
    why_not: >
      P1's one-time PR-3 look was consumed before population-determining logic changed; a second look
      would contaminate the scientific record and violate the accepted seal law.
evidence:
  - "research/stock_identity/W2_EXPERT_REPLAY_REGISTRATION.md registers ledger extraction, PIT recomputation, Class-B locked-spec backcast, and Class-P prospective-only history."
  - "research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md requires stored-ledger or era-pinned leak-tested replay and prospective accrual where legitimate history does not exist."
  - "PR #6638 is CLOSED UNMERGED at f0b265f82cc7066a4e8d0b87a8fd62a64dd10177 after its P1 Attempt-1 population was rejected; P1 may not be reread for the ruler constant family."
  - "research/stock_identity/W3AR_CENSUS_P2_PREREG_CHARTER_2026-08-30.md freezes the outcome-free successor census and STOP-before-P2-draw boundary."
affects:
  - WS:STOCK-IDENTITY
  - research/stock_identity/W3AR_CENSUS_P2_PREREG_CHARTER_2026-08-30.md
  - agentos/handoffs/STOCK-IDENTITY-2026-08-30-W3AR-CENSUS-P2-PREREG.md
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-30
---

# Ratified decision

W3A recovery uses **two clocks** and never overloads `family_first_available` or another single field to mean both retrospective research reconstructibility and real live availability.

## 1. Historical replay eligibility

A family/date/name/grain is historically eligible only through its exact already-registered W2 method and the PIT inputs that method requires. The closed basis vocabulary for the bounded recovery census is:

- `LEDGER_COVERAGE`
- `PIT_RECOMPUTE`
- `LOCKED_SPEC_BACKCAST`
- `STORE_VINTAGE`
- `PRICE_REFERENCE`
- `PROSPECTIVE_ONLY`

Unknown support fails closed. This list is a derived classification of already-accepted W2 constructions; it creates no second replay/availability authority plane.

Historical eligibility is **not** established by:

- a current `spec_hash` or current code existing;
- actual software deployment date by itself;
- family fire occurrence;
- first/last fire or event min/max;
- a convenient output file whose coverage contract is not the registered source/input contract.

Ledger-only families remain ledger-only. A registered Class-B backcast remains a retrospective research object only and must retain `spec_postdates_history=true` plus its named era/deviation semantics. Class-P and structurally non-reconstructable families remain historical false.

## 2. Live/prospective availability

The actual emitter/source deployment and known-at clock governs Live Entry Radar, W7 prospective evidence and any live product use. A lawful historical research backcast does not imply that the family was available to the live system at that historical date.

The retrospective clock may never be exported into live authority. The live clock may not be misused to erase an already-registered lawful W2 research backcast.

## 3. Family-law examples that bind the successor census

Subject only to byte-current verification of W2/registry, the worker must preserve these distinctions rather than redesigning them:

- `grey_dot_macro`: registered recompute may use `PIT_RECOMPUTE` when its required inputs are reconstructable.
- `confirmed_buy`: committed buy-filter ledger rows use `LEDGER_COVERAGE`; separately named pre-filter `cb_3d_confluence` may use the W2-registered recompute path. Do not merge them.
- `rebuy`: ledger-only; no invented backcast.
- `reclaim_waiver`: only the persisted nightly-state artifact's actual source vintage; no synthetic history.
- `weekly_washout_turn`: distinguish its ledger arm from its W2-registered truncated weekly pure-function recompute.
- `sea_event_classes`: source-store/backfill coverage must be derived from store truth, never fire min/max.
- naive registered comparators: `PRICE_REFERENCE` on lawful adjusted price history.
- `tier_cascade_t1..t4`, `grey_dot_terminal`, `bottom_watch_terminal`: only their exact W2 Class-B locked-spec backcasts, with `spec_postdates_history=true`.
- STARTER state trio and all Class-P families: `PROSPECTIVE_ONLY`; `starter_signature` remains its separately named replayable construction.

## 4. Consequences for P1/P2

- PR #6638 Attempt-1 remains REJECTED/CLOSED UNMERGED; its P1 values are immutable negative evidence, never design input.
- P1 may never be reread/resealed/overwritten/relabelled for the PR-3 ruler constant family.
- Blind per-name outcomes remain untouched.
- A future P2 may be proposed only after an outcome-free family/source-input coverage census and deterministic untouched clean-pool census.
- P2 eligibility must exclude pilot/B, blind, P1 and every later design-touched/contaminated name required by the successor charter.
- The draw algorithm/seed/sample law must be frozen before membership reveal.
- `GO_P2_PREREG` is not authority to execute the draw; Sol must separately accept/freeze and commission it.

## 5. Operation-boundary ruling

Old child `SI-W3AR-REPLAY-ELIGIBILITY-P2-V1` is terminal/effect-NONE because its principal source-law question has been resolved by Sol. Reusing that stable key with a materially narrower payload would be a semantic conflict.

Successor child `SI-W3AR-CENSUS-P2-PREREG-V1` owns only:

1. family-method/source-input classification and coverage;
2. deterministic untouched clean-pool exclusions/count/hash;
3. outcome-free family × era × grain support census;
4. complete **unexecuted** P2 prereg proposal if feasible;
5. independent adversarial review;
6. return of exactly `GO_P2_PREREG`, `NO_GO_CALIBRATION_RECOVERY`, or `BLOCKED_NEW_SOURCE_LAW`.

It stops before any P2 draw/read.

## 6. Routing ruling

This successor no longer meets Fable admission. Sol owns and froze the architecture. Preferred avenue is `CTO Sol`, then `Terra`; `Opus` is an acceptable bounded fallback if Codex-backed capacity is unavailable. Fable remains parent-level escalation capacity only if a new material architecture/source-law contradiction is discovered.

`DNR:KILL-OUTCOME-AUDITION`, Class-P forward-only law, canonical owner reuse and zero Prophet authority remain total.
