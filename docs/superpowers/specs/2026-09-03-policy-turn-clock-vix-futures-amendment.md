# Policy Turn Clock — Monthly VIX Futures Settlement Amendment

Date: 2026-09-03  
Status: **BINDING PRE-IMPLEMENTATION ARCHITECTURE REPAIR / RECORDS ONLY**  
Parent carrier: Macro PR #6788  
Implementation carrier: Macro issue #6787  
Operation: `policy-preturn-actor-liquidity-calendar-clock-20260903-sol-001`  
Current protected procedure at repair: `mastermindx-market-intelligence/Mastermind@c7fa5b43de6ca702f942fbf20cbe3ac45a02b0f6`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1 compatible.  
Current Macro observation at repair: `16aac3be6a7e8790af0aee75ab1d44ac43eecfab`.

## 1. Why this amendment exists

The frozen W1 design correctly distinguishes standard monthly equity-option expiration from the **quarterly** roll cycle of major U.S. equity-index and Treasury futures. It omitted one material monthly futures mechanism: **standard VIX futures expiration and rank roll**.

That omission would leave the user’s explicit futures-dynamics question only partially answered. Standard VX futures expire every month, weekly VX futures can sit in front of them, and the canonical Macro estate already carries both a nearest-expiry VIX-futures settlement and the standard monthly M1–M6 VX curve. A policy/monthly transition clock that says futures are `not_applicable` outside March, June, September and December would therefore be false unless the claim is explicitly limited to equity-index and Treasury futures.

This repair does not assert that VIX expiration causes equity direction. It adds the missing settlement/term-structure clock needed to distinguish:

```text
ordinary equity/Treasury month with no quarterly roll
from
an every-month VX settlement/rank-roll boundary
from
a weekly VX expiry
from
an actual volatility-regime change
```

## 2. Precedence and exact amendment surface

This file amends only the VIX-futures portions of:

- `docs/superpowers/specs/2026-09-03-policy-transmission-preturn-command-design.md`;
- `docs/superpowers/specs/2026-09-03-actor-liquidity-monthly-transition-clock-design.md`;
- `docs/superpowers/plans/2026-09-03-actor-liquidity-monthly-transition-clock-implementation.md`;
- `agentos/decisions/DEC-POLICY-PRETURN-CALENDAR-FLOW-COMPOSITION.md`;
- `agentos/handoffs/RATES-INFLATION-COMMAND-2026-09-03-actor-liquidity-monthly-transition-clock.md`.

Where an earlier statement says an ordinary month makes the whole `futures_roll` axis `not_applicable`, this amendment controls:

- `equity_index.status=not_applicable` and `treasury.status=not_applicable` are lawful outside quarterly roll months;
- `volatility.status` is evaluated separately because standard VX futures settle monthly;
- no futures family may be averaged into one status or one score.

No executable path is added to the W1 ceiling. The already-authorized `engine/futures_roll_calendar.py`, `engine/policy_turn_clock.py`, builder, tests and Policy Watch consumer implement this amendment.

## 3. Canonical ownership and no-rebuild boundary

W1 must consume, not replace, the existing volatility-futures plane:

| Fact | Canonical owner | W1 use |
|---|---|---|
| Cboe daily VX settlement source and standard-monthly filtering | `collectors/cboe_vix_futures.py` | read existing outputs only |
| Nearest non-expired VX settlement, weekly or monthly | `data/cboe/vix_futures.parquet` | front-contract context and DTE |
| Standard monthly VX M1–M6 settlements and DTE | `data/cboe/vix_curve.parquet` | term structure and rank-roll context |
| Existing curve slope / vol context | `scripts/build_market_structure.py` → `data/market_structure/latest.json` | consume when fresh; do not recompute a rival state |
| Existing machine projection | `engine/neuralweb/world_state.py` | optional downstream context; no new owner |
| Contract calendar and settlement rules | Cboe official VIX futures/FAQ/calendar surfaces | deterministic schedule validation |

W1 must not:

- modify `collectors/cboe_vix_futures.py`;
- create another VX collector or `data/` store;
- call a second Cboe settlement endpoint for the same facts;
- treat `vix_futures.parquet` as necessarily standard monthly—the front contract can be weekly;
- treat the rank-based `m1_settle` series as one continuous same-contract price across expiration;
- create a VIX directional signal, volatility-target instruction, hedge recommendation or trade authority.

If current source proves the canonical stores unavailable or structurally different, return `DECISION_REQUEST / CANONICAL_VX_INPUT_GAP`; do not widen into collector repair under W1.

## 4. Source truth to preserve

Cboe’s public contract rules establish:

1. Standard and weekly VIX futures coexist.
2. Volatility derivatives generally expire Wednesday mornings.
3. Standard settlement uses the VIX Special Opening Quotation derived from standard A.M.-settled SPX options expiring 30 days later.
4. If the Wednesday or the Friday 30 days later is a Cboe Options holiday, expiration moves to the immediately preceding business day.
5. Expiring VIX futures trade for part of expiration morning and then settle through the SOQ.
6. Weekly VX futures generally expire Wednesdays and must remain distinguishable from the standard monthly contract.

Official reference surfaces:

```text
https://www.cboe.com/tradable-products/vix/vix-futures/
https://www.cboe.com/tradable_products/vix/faqs
https://www.cboe.com/about/hours/us-futures
```

The current official 2026 listing demonstrates the distinction: standard `VX/U6` expires `2026-09-16`, while weekly contracts expire `2026-09-02`, `2026-09-09`, `2026-09-23` and `2026-09-30`. The same month’s major CME equity-index roll is a separate quarterly event: customary roll `2026-09-14`, expiration `2026-09-18`.

These dates are acceptance fixtures, not hard-coded eternal source truth. Future dates derive from the contract rule and are checked against current canonical observations when available.

## 5. Revised futures helper contract

`engine/futures_roll_calendar.py` retains the existing interfaces and adds a volatility-family seam:

```python
from collections.abc import Mapping
from datetime import date


def vix_settlement_window(
    d: date,
    *,
    front: Mapping[str, object] | None = None,
    curve: Mapping[str, object] | None = None,
    source_asof: date | None = None,
) -> dict[str, object]: ...


def snapshot(
    asof: date,
    *,
    live_progress: Mapping[str, object] | None = None,
    vix_front: Mapping[str, object] | None = None,
    vix_curve: Mapping[str, object] | None = None,
    vix_source_asof: date | None = None,
) -> dict[str, object]: ...
```

The top-level `futures_roll_calendar.v1` output becomes:

```json
{
  "schema": "futures_roll_calendar.v1",
  "as_of": "YYYY-MM-DD",
  "equity_index": {},
  "treasury": {},
  "volatility": {},
  "gaps": [],
  "authority": {
    "can_rank": false,
    "can_gate": false,
    "can_size": false,
    "can_trade": false
  }
}
```

### 5.1 Volatility-family output

```json
{
  "status": "scheduled|approaching|settlement_day|post_settlement|stale|unknown",
  "standard_expiry": "YYYY-MM-DD|null",
  "trading_days_to_standard_expiry": null,
  "source_asof": "YYYY-MM-DD|null",
  "stale_days": null,
  "front_settle": null,
  "front_dte": null,
  "standard_m1_settle": null,
  "standard_m1_dte": null,
  "standard_m2_settle": null,
  "standard_m2_dte": null,
  "front_is_weekly": null,
  "m1_m2_spread": null,
  "m1_m2_pct": null,
  "curve_state": "contango|flat|backwardation|unknown",
  "rank_roll_boundary": false,
  "same_contract_change_available": false,
  "settlement_basis": "cboe_rule|canonical_dte|both|unknown",
  "is_context_only": true,
  "authority": {
    "can_rank": false,
    "can_gate": false,
    "can_size": false,
    "can_trade": false
  },
  "gaps": []
}
```

### 5.2 Status law

- `scheduled`: a standard monthly expiry is deterministically known but more than five NYSE sessions away, or current curve evidence is unavailable without being provably stale.
- `approaching`: zero to five NYSE sessions before the standard expiry **and** source evidence is fresh enough for its owner’s accepted SLA.
- `settlement_day`: `asof` equals the standard expiry. This is a settlement-clock fact, not a volatility-direction claim.
- `post_settlement`: the first two NYSE sessions after standard expiry, identifying the period in which former M2 becomes rank M1.
- `stale`: a canonical source observation exists but exceeds the accepted freshness budget.
- `unknown`: neither the schedule nor input state can be established safely.

No status is called `active` merely because settlement is near. `active roll` would require a source-owned migration measure such as contract volume/open interest; W1 does not invent one.

## 6. Deterministic schedule and weekly/monthly distinction

### 6.1 Standard monthly expiry

The pure schedule helper:

1. finds the standard SPX A.M.-settled third-Friday expiration for the following month;
2. subtracts 30 calendar days;
3. applies the Cboe holiday rule: if that Wednesday or the corresponding Friday is a Cboe Options holiday, move to the immediately preceding Cboe business day;
4. labels the calendar basis and any fallback.

When a fresh canonical `standard_m1_dte` is available, `asof + m1_dte` must agree with the computed standard expiry. Disagreement emits `VX_EXPIRY_SOURCE_CONFLICT`, retains both values and sets status `unknown`; it does not silently prefer the prettier date.

### 6.2 Weekly front detection

The existing front store includes the nearest non-expired weekly **or** monthly contract, while the curve store includes only standard monthlies. Therefore:

```text
front_is_weekly = front_dte < standard_m1_dte
front_is_weekly = false when front_dte == standard_m1_dte
front_is_weekly = unknown when either DTE is unavailable or contradictory
```

A weekly front must never replace the standard monthly expiry field.

## 7. Rank-roll and false-change prevention

The canonical M1–M6 curve is rank-based. At standard settlement, former M2 becomes the new M1. That mechanical relabeling can look like a large daily change even when no contract repriced by that amount.

W1 therefore enforces:

- `rank_roll_boundary=true` when the standard expiry lies between the prior and current source observations, or when M1 DTE resets upward consistently with a monthly rank roll;
- raw `m1_settle[t] - m1_settle[t-1]` is not described as same-contract movement across that boundary;
- `same_contract_change_available=false` unless an existing owner supplies contract identity on both observations;
- the transition clock may use the **same-day** M1–M2 shape and source-owned curve state, but cannot infer a volatility shock from a rank-label jump;
- a stale or ragged M2 input produces `curve_state=unknown`, not `flat`.

This is a correction-safety requirement, not optional display polish.

## 8. Curve-state semantics

For fresh positive observations:

```text
m1_m2_spread = standard_m2_settle - standard_m1_settle
m1_m2_pct    = m1_m2_spread / standard_m1_settle
```

Frozen descriptive classes:

```text
contango      when m1_m2_pct > +0.005
flat          when -0.005 <= m1_m2_pct <= +0.005
backwardation when m1_m2_pct < -0.005
unknown       when either leg is missing, stale, non-positive or roll-conflicted
```

These are state descriptions. The 0.5% deadband prevents noise from flipping the label and carries no forecast authority. Historical calibration remains separate because the existing curve accrues forward and has shallow history.

## 9. `policy_turn_clock.v1` integration

The `futures_roll` axis inside `policy_turn_clock.v1` must preserve three independent families:

```json
{
  "equity_index": {},
  "treasury": {},
  "volatility": {}
}
```

State composition law:

1. A VX settlement window alone cannot select `VOLATILITY_WINDOW_OPEN`.
2. `approaching` or `settlement_day` may add a transparent `state_basis` item such as `vx_standard_settlement_near`.
3. `VOLATILITY_WINDOW_OPEN` still requires independent realized confirmation from existing owners, such as expanding realized volatility, deteriorating breadth/credit, a short-gamma transition, or another frozen confirming predicate.
4. Fresh backwardation may strengthen a volatility-fragility explanation but carries no direction and no standalone top-level state authority.
5. Fresh contango may describe carry-calm but cannot suppress a catalyst-dominant or independently confirmed volatility state.
6. Rank-roll boundaries are displayed as mechanical context and excluded from change detection.
7. Weekly VX expiry is shown when it is the front contract but cannot be mislabeled as the standard monthly OPEX or standard monthly VX settlement.

The user-facing copy should say, for example:

> Standard VIX futures settle Wednesday; the nearest contract is a weekly expiry, while the monthly curve remains in contango. This is a volatility-carry transition, not an equity-direction signal.

## 10. Required plan patch

The existing implementation plan remains controlling except for these additive requirements.

### Task 2 additions

Add failing tests before implementation:

```python
def test_august_is_not_applicable_for_equity_treasury_but_vx_is_monthly(): ...
def test_september_2026_standard_vx_expiry_is_2026_09_16(): ...
def test_weekly_front_does_not_replace_standard_monthly_expiry(): ...
def test_vx_holiday_rule_moves_to_prior_business_day(): ...
def test_fresh_curve_classifies_contango_flat_and_backwardation(): ...
def test_stale_curve_is_not_current_or_flat(): ...
def test_rank_roll_boundary_blocks_same_contract_change_claim(): ...
def test_vx_settlement_alone_has_zero_directional_authority(): ...
```

Implement `vix_settlement_window` inside the same `engine/futures_roll_calendar.py`. Do not add another module.

### Task 4 additions

Add hostile composer tests:

- VX settlement near + no realized confirmation does not produce `VOLATILITY_WINDOW_OPEN`;
- weekly front + standard monthly M1 remain separate fields;
- backwardation + independently expanding volatility may contribute basis but not rank/gate/size/trade authority;
- M1 rank reset at expiry is excluded from `changed_axes` unless another same-contract/source-owned change exists;
- missing M2 or stale curve remains `unknown`.

### Task 5 builder additions

The builder reads existing canonical stores or the existing `market_structure/latest.json` projection. It does not call Cboe or write a new volatility store. It records the source observation, owner and stale age in `policy_turn_clock.v1`.

### Task 6 UI additions

Policy Watch renders a compact volatility-futures row only when applicable:

- standard monthly settlement date and distance;
- weekly-versus-monthly front distinction;
- curve state and data as-of;
- rank-roll disclosure;
- exact stale/unknown state.

Bilingual copy must preserve “settlement/term structure,” not imply “volatility will rise/fall.”

### Task 8 proof additions

Real proof must show:

1. current `data/cboe/vix_futures.parquet` and `data/cboe/vix_curve.parquet` or their canonical existing projection;
2. correct weekly/monthly distinction;
3. current standard expiry derived independently and reconciled with M1 DTE;
4. a synthetic settlement-boundary replay proving rank-roll false changes are suppressed;
5. the same JSON consumed by Policy Watch and the machine consumer;
6. all authority fields false.

## 11. Acceptance fixtures

Minimum discriminating fixtures:

| As-of | Expected |
|---|---|
| `2026-08-10` | equity/Treasury `not_applicable`; standard monthly VX expiry still scheduled for `2026-08-19` |
| `2026-09-01` | weekly front `2026-09-02` can be detected separately; standard monthly VX expiry `2026-09-16` |
| `2026-09-14` | equity quarterly roll scheduled/active only with supplied progress; standard VX settlement approaching independently |
| `2026-09-16` | VX `settlement_day`; equity-index futures have not yet reached `2026-09-18` expiry |
| first session after `2026-09-16` | VX `post_settlement`; rank roll disclosed; no false same-contract M1 jump |

Every fixture asserts context-only authority and zero directional field.

## 12. Capability and completion effect

Merging this amendment would make only a corrected design durable. It would not:

- run the existing VX collector;
- prove the canonical stores fresh;
- create `futures_roll_calendar.v1` or `policy_turn_clock.v1`;
- change Policy Watch;
- establish a calendar edge;
- rank, gate, size, hedge or trade;
- start issue #6787;
- accept or merge PR #6788.

The architecture carrier remains `SPEC_ONLY` until exact-head validation and independent review. W1 remains `NOT_BUILT` until a separately assigned, acknowledged and STARTed worker implements the complete official-source → deterministic artifact → Policy Watch → machine-consumer → prospective-evaluation journey.