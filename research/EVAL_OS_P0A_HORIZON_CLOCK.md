# P0a — the explicit horizon-clock contract

**Date** 2026-08-13 · **Status** P0a-1 shipped in this PR; P0a-2 (market-resolver
hardening) is a separate PR that stacks on it. · **Ruling** CEO exceptional
checkpoint 2026-08-13 ("do not implement P0 as specified"; split approved).

---

## 0. The defect this repairs

`horizon_d` was a bare integer with **no declared unit**, and `qledger` itself read
it two different ways:

```
make_claim()  ->  check_by = asof + pd.offsets.BusinessDay(horizon_d)
_fwd_ret()    ->  exit     = fill + pd.Timedelta(days=horizon_d)     # CALENDAR
```

From a Friday `asof=2026-08-07` those diverge by **+2 days at `horizon_d=5`, +4 at
7, and +10 at 21** — the falsifier deadline a human reads and the window actually
graded were ten days apart at the 21d rung. This affects **every claim in the
corpus**, including the 5/21/63 rungs.

The emitters disagreed about what the number even meant: `policy_intent_desk`,
`stock_desk`, `thematic_desk` and `altdata_brain` document "integer TRADING
days"; `build_whitehouse` passes CALENDAR `banner_days`; and
`engine/source_registry.py` bypassed `_fwd_ret` entirely to compute an exact
trading-session exit **precisely because an approximated calendar horizon is
unsafe**.

## 1. The contract

1. A new claim declares `horizon_unit ∈ {trading_days, calendar_days}`.
2. `horizon_d` stays the numeric **declared ruler** and is **never converted** — a
   `policy` claim stays `126/trading_days`, a `whitehouse` claim stays
   `7/calendar_days`. (The ruling forbids the "convert every emitter to calendar
   days" workaround; this is why.)
3. The clock interprets the number **according to its unit**.
4. **ONE resolver** — `resolve_horizon_window` — answers `check_by`, maturity, the
   graded window and the rendered ruler. There is no second implementation.
5. The window is resolved **once** per (claim, horizon) and **shared** by subject,
   bench and control, so no leg can silently receive a different horizon length.

`trading_days` is resolved by **canonical exchange session arithmetic** on the
calendar of the market the claim is priced in — not `pd.Timedelta`, not a 1.4×
fudge, and not `pd.offsets.BusinessDay` (which counts Mon–Fri and so walks
*through* market holidays).

### Legacy is immutable

Rows written before this contract carry no clock stamp and are read as
`CLOCK_LEGACY = "legacy_calendar_unstamped"`. They are **never rewritten and never
re-labelled** — the same house pattern as the `fill_convention` discontinuity.
`git diff --stat data/qledger` is empty on this branch.

### Nothing pools across a basis change

Two rows both saying `horizon_d=21` are not comparable when one was graded on the
legacy calendar approximation and the other on 21 exchange sessions. Every
aggregation point partitions by `grade_clock_basis` first, and where a cell
straddles bases the rule is **select-and-label, never blend**: one basis's own
honest numbers, with `clock_bases`, `clock_bases_n_grades` and
`pooling_refused: True` disclosed beside it.

**Authority is RESET by a basis change, not inherited across it.**
`_authority_clock_basis` evaluates promotion inside the explicit-clock basis and
counts legacy rows for nothing. The alternative would launder 59,326 legacy
observations into a gate about a clock they were never measured on.

## 2. Two defects found and fixed in this PR

**(a) Promotion could be granted on the legacy clock.**
`promotion_check_by_market` — the per-market escape hatch that keeps a bi-market
family promotable without pooling — re-ran `promotion_check` once per key of
`clock_prior_n_dates`. That dict discloses *every* basis the family holds,
`CLOCK_LEGACY` included. So a family straddling the migration would publish a
real promotion verdict computed on the **legacy** basis into
`track_record.json → ladder_states.<fam>.<h>.by_clock_basis`, where an `eligible`
cell reads as authority earned — directly contradicting `_authority_clock_basis`
on the default path.

Not reachable on today's corpus (no explicit-clock grade row exists yet, so
nothing can be `STATE_MIXED_CLOCK`), but reachable the first night a second
market accrues — precisely when a legacy `GRADED` cell would appear beside the
real ones. The disclosure is unchanged; only the **verdict** is removed.

**(b) The acceptance-#6 flap test was tautological.** It called
`promotion_check` twice on an *unchanged* store and asserted the two results
matched. `promotion_check` is a pure function of the store, so that holds by
construction and would have stayed green against any flap a real night could
produce. A nightly run reads a store that **grew**. The test now runs
single-market → grows the store the way a night does (CN's first rows arrive) →
re-reads, which is the transition where the shipped defect actually fired.

## 3. A correction to the previous handoff

The parked handoff (`EVAL_OS_P0A_CONTINUATION_HANDOFF_2026-08-13.md`, not merged)
reported a round-5 blocker: *"`600519.SS` under a US desk resolves US — a hard
Shanghai suffix overridden by provenance."*

**That finding was wrong, and it was my own test that was broken.** The repro
passed `scope_key` at the top level of the claim dict, but `resolve_claim_market`
reads `claim["scope"]["key"]` — the shape every row in the live store actually
has. So the subject leg was simply *absent*, and the default `SPY` bench named
US. On a correctly-shaped claim the suffix wins, as designed:

```
{'desk': 'us_importance_v0', 'scope': {'type':'entity','key':'600519.SS'}}
  ->  (None, 'mixed_markets — CN=600519.SS, US=SPY')
```

Measured on the live 46,630-claim corpus, the resolver names a market for
**46,626** claims (US 40,682 / CN 5,944) and refuses **4** — all
`china_special_sits` on Beijing Stock Exchange (`.BJ`) tickers, which is the
correct, intended refusal. Shape and provenance **disagree on zero legs**.

Two things follow, and both are honest rather than flattering:

- The contract was **not** blocked on a five-times-failed classifier. It was
  blocked on a bad test. Four of the five rounds fixed real defects; the fifth
  chased an artifact.
- `DESK_MARKET` (the round-5 "provenance" table) is **inert on the live corpus**:
  nulling it changes **0 of 46,630** resolutions. Every CN claim resolves by its
  own `.SS`/`.SZ` suffix. It is prospective insurance, not load-bearing, and this
  document says so rather than letting its size imply otherwise.

## 4. The split, and what it actually costs

The handoff proposed splitting at **calendar-only vs trading-day**, on the
premise that `calendar_days` "needs no market at all". **That premise is also
false**: a `calendar_days` window still needs session arithmetic for its `fill`
(first session strictly after the anchor) and its `coverage_date` (last session
on or before the calendar exit), so it dispatches on the same market. Splitting
there would have removed no dependency.

The seam that actually separates is **contract vs resolver hardening**:

- **P0a-1 (this PR)** — the whole contract, both units, on the round-5 resolver,
  which is measurably correct on 46,626/46,630 live claims and refuses the other
  4 correctly.
- **P0a-2 (next PR)** — hardening the resolver against inputs the live corpus
  does not yet contain: agree-or-refuse when shape and provenance both speak,
  index symbols (`^HSI`), and the absent-subject-leg fail-open.

**This is better than the approved split, and the difference matters for
planning: P0a-1 keeps `trading_days` working, so it unblocks P3.** The approved
calendar-only variant would not have — `stock_desk`, `thematic_desk` and
`demand_chain` all declare trading days.

## 5. Out of scope, deliberately

`in_scope_horizons` and `GRADE_HORIZONS = (5, 21, 63)` are **untouched** — that is
P0b, and the ruling keeps them fixed. So for an off-rung `horizon_d` (7, 126, …)
the `check_by` a human reads is a real resolved exchange exit under the declared
unit, but it is not a date any grade row is measured to.
`check_by_is_a_graded_exit(horizon_d)` exports that question so a caller can ask
it instead of trusting prose.

## 6. Disclosed residuals

- **CN makeup workdays** (`CLOCK_CN_RESIDUAL`). `lib/cn_calendar.py` encodes only
  closures recurring every year, so a State-Council makeup Saturday reads as a
  closure and puts the exit **one session late** under the declared label —
  bounded to +1 session and invisible to the endpoint assertion, because the bar
  does exist. The fix is a makeup-workday table in that module, which is its
  scope, not this one's. The opposite error (a real closure called a session)
  fails closed and is counted.
- **Calendar support ranges.** US has a floor only (2012-10-31, the first day
  after the earliest modelled one-off closure); CN and HK carry a floor **and a
  2030 ceiling**, checked against the resolved exit as well as the anchor,
  because their lunar tables stop there and the modules return a holiday set with
  no lunar closures past it rather than raising.
- **The legacy basis will win most straddled display cells for a long time.**
  Display-tier selection is by sample size, and 59,326 legacy grade rows are
  already on file. Correctly-clocked observations are therefore not the headline
  for those cells — but they are never invisible: every basis's own count is
  published beside the selected one.
