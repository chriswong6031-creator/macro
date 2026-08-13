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
   graded window and the rendered ruler **for every claim that grades through
   `qledger`**. (Scope corrected after review: `engine/source_registry.py` keeps
   its own `_add_trading_days` session walker and grades `narrative_source_call`
   through its own exit, so "there is no second implementation" — the earlier
   wording — was false. It is a named exception, §2b, not a silent one.)
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
aggregation point **inside `qledger`** partitions by `grade_clock_basis` first,
and where a cell straddles bases the rule is **select-and-label, never blend**:
one basis's own honest numbers, with `clock_bases`, `clock_bases_n_grades` and
`pooling_refused: True` disclosed beside it.

Scope corrected after review: two aggregations **outside** `qledger` still pool
(`source_registry`'s family `hit_rate`, `report_importance_duel::_slice_stats`).
Both are single-basis today and are listed with their fuse in §2b.

**Authority is RESET by a basis change, not inherited across it.** Where a family
holds an explicit basis, `_authority_clock_basis` evaluates promotion inside it
and counts legacy rows for nothing — the alternative would launder 59,326 legacy
observations into a gate about a clock they were never measured on. A family that
holds **only** legacy rows is a different case and is unchanged by this PR: see
the scope note in §2(a).

## 2. Two defects found and fixed in this PR

**(a) The per-market escape hatch minted a legacy promotion verdict.**
`promotion_check_by_market` — which keeps a bi-market family promotable without
pooling — re-ran `promotion_check` once per key of `clock_prior_n_dates`. That
dict discloses *every* basis the family holds, `CLOCK_LEGACY` included. So a
family **straddling** the migration would publish a real promotion verdict
computed on the **legacy** basis into
`track_record.json → ladder_states.<fam>.<h>.by_clock_basis`, where an `eligible`
cell reads as authority earned. The disclosure is unchanged; only the **verdict**
is removed.

> **Scope, stated precisely — an earlier draft of this section and of the commit
> message overstated it.** This does *not* mean "promotion may never be granted
> on the legacy clock." `_authority_clock_basis` returns the sole basis when a
> family holds exactly one, and for **every live family today that basis is
> `CLOCK_LEGACY`** (no explicit-clock grade row exists yet). So the *default*
> path does return `eligible=True, clock_basis='legacy_calendar_unstamped'` for a
> legacy-only family — verified directly, 30 legacy dates → `GRADED`.
>
> That is the **status quo and it is deliberate**: refusing it would make every
> family on the board permanently un-promotable until it accrues 25 dates on the
> new clock. That is a fleet-wide product decision for the CEO, not a side effect
> to slip into a clock-plumbing PR. What this PR narrows is strictly the
> **straddling** case. The boundary is now pinned by
> `test_promotion_on_a_legacy_only_family_is_the_documented_status_quo`, so
> changing it later is a deliberate act with a failing test attached.

Neither case is reachable on today's corpus for the straddle (nothing can be
`STATE_MIXED_CLOCK` yet); it becomes reachable the first night a second market
accrues.

**(b) The acceptance-#6 flap test was tautological.** It called
`promotion_check` twice on an *unchanged* store and asserted the two results
matched. `promotion_check` is a pure function of the store, so that holds by
construction and would have stayed green against any flap a real night could
produce. A nightly run reads a store that **grew**. The test now runs
single-market → grows the store the way a night does (CN's first rows arrive) →
re-reads, which is the transition where the shipped defect actually fired.

## 2b. Adversarial review — what it changed, and what stays open

An opus `reviewer` ran the contract against seven claims. Three were refuted and
are fixed below; the rest are **disclosed here rather than fixed**, because
fixing them belongs in other PRs and a claim that overstates is worse than a
disclosed gap.

### Fixed in this PR

**The per-market fix was published into JSON and read by nothing.**
`promotion_check_by_market` writes `by_clock_basis` into `track_record.json` —
and `families_ready`, the first-cross operator alert, and the admin tab all read
only the **top-level** `ready`, which is `False` for exactly the
`STATE_MIXED_CLOCK` family the fix exists for. Measured: 26 US + 26 CN dates,
both markets eligible, `run_status.json` reports `n_families_ready: 0` and no
operator is told. Fixing it one layer up and leaving it broken one layer down is
not fixing it. The summary now reads the per-basis rows under their own keys
(`f@21d[explicit_unit_v1:trading_days:CN]`), pools nothing, and skips
`CLOCK_LEGACY` again rather than trusting an upstream filter it does not own.
The logic was **extracted from `main()`** — it was eight inline lines in a
500-line entry point, which is precisely why it shipped unread: nothing could
reach it to test it.

**The duel compared two independently-selected clock bases.**
`challenger_excess_mean_5d` and `placebo_covered_abs_excess_5d` are each chosen
by "most observations", so during a migration they land on different clocks — a
challenger on 5 exchange sessions against a placebo on 5 **calendar** days. That
is the pooling this contract forbids, wearing a comparison's clothes, and it is
the **D3 counterfactual** rendered verbatim into the admin tab. Neither basis was
recorded, so the mismatch was not merely unguarded — it was invisible.
`duel_context` now carries both bases and `duel_comparable`; on a mismatch the
numbers stay (each honest on its own basis) and the **comparison** is withdrawn
with a stated reason.

**The placebo tape's basis selection depended on file order.**
`_placebo_magnitude` built its blocks by iterating `grades` in append-only file
order and selected with `max`, which keeps the first maximum — so on a tie the
published control arm depended on which row was appended first. Two bases'
`n_grades` are monotone integer counts, so during a migration they pass through
equality **exactly once**, and on that night the counterfactual could flip. Now
sorted, with `_select_single_clock_block`'s tie rule. The test that covered this
asserted `mean_abs_excess in (0.01, 0.99)` — a test written to accept *either*
answer, which records an ambiguity rather than pinning behaviour; it now pins one
answer and asserts that reversing the row order does not move it.

### Open, disclosed, NOT fixed here

- **"ONE resolver" is overstated.** `engine/source_registry.py::_add_trading_days`
  is an independent NYSE session walker used at registration and resolution for
  `narrative_source_call`, and it grades that family through its own exit. Its
  `while` loop is also unbounded, where the clock's walkers are bounded and
  fail closed. The contract text should read "one resolver **for every claim
  that grades through `qledger`**"; `source_registry` is a named exception with
  its own grading path. Folding it in is its own PR.
- **Two live aggregations pool across bases** once accrual starts:
  `source_registry`'s family `hit_rate` and
  `scripts/report_importance_duel.py::_slice_stats`. Both are single-basis
  **today** (there are no explicit-clock grade rows), so neither is a wrong
  number yet — the fuse is the first night new claims mature (≥5 sessions).
- **`control_only` hit counting is direction-blind — and this is the most
  serious thing the review found.** `promotion_check` scores a control hit as
  `subject_ret - control_ret > 0` regardless of the claim's `direction`, so for a
  `direction=-1` claim every **correct** bearish call is counted a MISS and every
  wrong one a HIT. The §3 Wilson bound is therefore computed on an inverted hit
  series for bearish families. It is **pre-existing on `origin/main`**, not a
  regression from this PR — but it is the gate this PR is protecting, and it
  needs its own PR and its own pre-registration. `bench_ret` is read in the same
  branch and never used, so the branch is gated on a value it does not consume.
- **The claim-side `clock_market` stamp is write-only.** Nothing reads
  `claim["clock_market"]`; the grader re-derives the market from the claim's legs
  at grading time and never compares. The stated guarantee ("a later change to
  the suffix table is visible as a change rather than a silent re-reading") is
  not implemented — if `.BJ` is later mapped, already-registered claims keep a
  `check_by` computed under the old resolution.
- **Consumers report the numbers without the basis.** `PromotionResult`'s own
  docstring requires any consumer reporting these numbers to report the basis
  alongside; the operator alert and `engine/qledger_ui.py::chip_for_desk` both
  drop it.
- **The admin tab degenerates for a MIXED_CLOCK family**, picking the `h="5"`
  record (`n_dates=0`) over the `h="21"` one that carries the disclosure.

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

---

# P0a-2 — the market resolver, hardened

**Shipped as the follow-on PR to P0a-1.** The rule the five earlier rounds never
tried:

> **Provenance and ticker shape are two INDEPENDENT signals. Neither is
> authoritative alone. Where both speak they must AGREE, or the leg is refused
> and counted.**

## 7.1 Why every earlier round failed

Each round picked **one** source and let it win:

| round | sole source | how it failed |
|---|---|---|
| 2 | hardcoded NYSE | CN lanes ungradeable on ~26% of windows |
| 3 | shape: "single-letter suffix ⇒ US share class" | `.L` (London), `.T` (Tokyo), `.F` (Frankfurt) silently US |
| 4 | shape: "no suffix ⇒ US" | `600519`→US, `000001`→US, `0700`→US |
| 5 | **provenance**, for any no-suffix leg | a US desk's bare A-share code → US; and, sharpest, **the string `SPY` itself resolved CN under a CN desk** |

The error was never *which* source was picked. It was that **one source was
allowed to be sufficient**. A US desk claiming `600519` is not a market to
guess — it is a contradiction, and the only safe answer is refusal.

## 7.2 The four holes this closes

**(a) Index symbols let the default bench name the market.** `^HSI` fails
`ticker_shape.plausible_symbol` (the leading `^` is not in the symbol alphabet),
so round 5 read it as "contributes nothing, same as an absent leg" and skipped
it — leaving only the bench, which **defaults to SPY**. So
`{'desk':'radar','scope':{'key':'^HSI'}}` resolved **(US, '')**: the Hang Seng,
graded on NYSE sessions against SPY, silently. Index symbols are now
**enumerated** in `INDEX_MARKET` and refused by name when absent — never
inferred, because `^HSI` and `^GSPC` are shaped identically and trade on
different continents.

**(b) Provenance could name a market the shape positively excludes.**
`valid_us_ticker` rejects a digit-first root, so US is *excluded* for `600519`
however the desk table is configured. `_shape_admits_market` makes provenance a
**corroborated inference** rather than an override: a CN desk's bare `600519` is
admitted (6-digit A-share code) and still resolves CN — the forward use case
provenance exists for — while a US desk's `600519` refuses.

**(c) Shape and provenance could disagree with no one noticing.** Now a
contradiction, named and counted (`shape_provenance_contradiction`).

**(d) A claim with no subject leg resolved US off the default bench.**
`_validate_claim` already rejects such a claim, so this is unreachable through
registration — but `resolve_claim_market` is a public entry point, and this
exact fail-open is what made a malformed probe report a defect that did not
exist (§3). A resolver whose answer is "US" for an empty claim is not
fail-closed.

## 7.3 Two round-5 tests were enshrining the defect

`test_hsi_never_independently_claims_a_market_only_a_real_leg_can` asserted, as
**correct behaviour**:

```python
resolve_claim_market({"scope": {"key": "^HSI"}, "bench": "SPY"}) == (MARKET_US, "")
```

That is the defect, with a green test standing behind it. It is superseded by
`test_hsi_resolves_its_own_market_and_never_defers_to_the_bench`. `^HSI` was
also removed from the `..._never_silently_resolves_to_us` parametrize list —
a **strengthening**: acceptance bar #1 is "the true market, or fail closed", and
`^HSI` used to satisfy it the weak way (fail closed), which is exactly what let
the default bench answer. It now satisfies it the strong way (HK).

## 7.4 What this costs: nothing, measured

Replayed over the live **46,630-claim** corpus, P0a-2 changes the resolved
market of **0 claims**. Distribution is identical to P0a-1: US 40,682 / CN 5,944
/ 4 refused (`china_special_sits` on `.BJ`). Every shape refused here is one the
corpus does not yet contain — refused *before* a producer starts emitting it,
not after a quarter of silent mis-grading.

The corpus check is deliberately **not** a test assertion.
`data/qledger/claims.jsonl` is an append-only nightly store, and any assertion
counting its rows or its outcomes can be falsified by tomorrow's append (the
append-only law, P2). `test_the_hardening_refuses_only_shapes_the_live_corpus_
does_not_contain` asserts over **fixtures** representing the shape classes the
store holds.

## 7.5 Mechanical negative controls

Four mutations, each reverted byte-identically:

| mutant | result |
|---|---|
| M1 index table nulled (`^HSI` back to "absent leg") | 2 tests fail |
| M2 contradiction ignored (shape wins the tie) | 2 tests fail |
| M3 provenance may override an excluding shape (round-5 behaviour) | 2 tests fail |
| M4 absent subject resolves off the default bench again | 1 test fails |

`_corroborate`'s `shape_is_decisive` flag currently behaves identically in both
arms, so nothing would catch it rotting into a lie — every call site's value is
therefore pinned at the source level by
`test_corroborate_records_the_strength_of_every_call_site`.
