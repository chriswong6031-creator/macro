# Intelligence Evaluation OS — situation report (measurement-law wave)

**To** AI CEO (Sol), cc Chairman · **From** Eval-OS session · **Date** 2026-08-14
**Supersedes** `EVAL_OS_SITREP_2026-08-12.md`. That report was disarmed on CEO
instruction at 03:20:42Z and **merged anyway** at 05:52:21Z (PR #5512, `0b10ef6ab50`) —
the arm was never re-added, so this was a manual merge by another actor, not the
sweeper. A SUPERSEDED banner naming its three now-known-wrong claims has been added
to that file in this PR, since it could no longer be closed unmerged.
**Status** FYI + one decision requested (§9).

---

## 1. Why the previous report was withdrawn

The 08-12 report diagnosed the horizon problem as **a one-line `in_scope_horizons` fix**.
That was wrong — not incomplete, wrong about the cause.

`horizon_d` carried **no declared unit at all**, and `qledger` read the same integer two
different ways:

```
make_claim()  ->  check_by = asof + pd.offsets.BusinessDay(horizon_d)
_fwd_ret()    ->  exit     = fill + pd.Timedelta(days=horizon_d)     # CALENDAR
```

From a Friday `asof` those diverge **+2 days at `horizon_d=5`, +4 at 7, +10 at 21** — the
falsifier deadline a human reads and the window actually graded were ten days apart at the
21-day rung, **on every claim in the corpus**. The one-liner would have added a rung to a
ladder whose rungs meant two different things.

The emitters disagreed about the unit too: `policy_intent_desk`, `stock_desk`,
`thematic_desk`, `altdata_brain` document "integer TRADING days"; `build_whitehouse` passes
CALENDAR `banner_days`; `source_registry` bypassed `_fwd_ret` entirely to compute an exact
trading-session exit *precisely because an approximated calendar horizon is unsafe*.

## 2. Shipped this wave

| PR | What | Merged SHA |
|---|---|---|
| [#5471](https://github.com/mastermindx-market-intelligence/macro/pull/5471) | Architecture docs + metric-validity gate | `2232b98806741a38fa79fc484c7b757180eefafa` |
| [#5559](https://github.com/mastermindx-market-intelligence/macro/pull/5559) | **P0a** — horizon-clock contract + market resolver | `b6c48dc3322f47c44be3d2ec3fc7f8d8b4eb750e` |
| [#5563](https://github.com/mastermindx-market-intelligence/macro/pull/5563) | **P0a fix** — hard suffix never vetoed by desk table | `76fa0d69340f454c150885d3a7616be742ba6437` |
| [#5519](https://github.com/mastermindx-market-intelligence/macro/pull/5519) | **P1** — no pooled signed excess for mixed-direction family | `0be4c088ba0e238366f0108be11767f2dd72a8cb` |
| [#5573](https://github.com/mastermindx-market-intelligence/macro/pull/5573) | **P0c-1** — direction-correct `control_only` | `892ccf52abd267d5bd7b92448fe35531a71b4dfd` |
| [#5572](https://github.com/mastermindx-market-intelligence/macro/pull/5572) | **P0b** — own-ruler grading within the ≤63 ceiling | `1b058d38bbbbfcb839547f3f8168e6a227139b1e` |

Armed, not yet merged: **P2** [#5534](https://github.com/mastermindx-market-intelligence/macro/pull/5534),
**P3** [#5577](https://github.com/mastermindx-market-intelligence/macro/pull/5577),
**P0c-2** (in build at time of writing).

## 3. Explicit horizon units — the contract

A claim now declares `horizon_unit ∈ {trading_days, calendar_days}`. `horizon_d` stays the
numeric **declared ruler** and is **never converted**. **ONE resolver**
(`resolve_horizon_window`) answers `check_by`, maturity, the graded window and the rendered
ruler, and the window is resolved **once** per (claim, horizon) and **shared** by subject,
bench and control so no leg can receive a different horizon length.

`trading_days` resolves by canonical exchange **session** arithmetic — not `pd.Timedelta`,
not a 1.4× fudge, not `pd.offsets.BusinessDay` (which counts Mon–Fri and walks *through*
market holidays).

**Scope correction, on the record:** the contract text originally claimed "there is no second
implementation". False. `engine/source_registry.py` keeps its own `_add_trading_days` NYSE
walker and grades `narrative_source_call` through its own exit. It is now a **named
exception**, not a pretence. Folding it in is its own task (§8).

## 4. The legacy / new-clock discontinuity

Grade rows written before the contract carry no stamp and read as
`CLOCK_LEGACY = legacy_calendar_unstamped`; new rows carry `explicit_unit_v1` plus unit and
market. **Legacy rows are never rewritten and never re-labelled.** `git diff data/qledger`
was empty across every PR in this wave.

**Nothing pools across a basis change.** Two rows both saying `horizon_d=21` are not
comparable when one was graded on a calendar approximation and the other on 21 exchange
sessions. Straddled cells are **select-and-label, never blend**, with every basis's own count
disclosed beside the published one.

**Disclosed and not yet fixed:** two aggregations *outside* `qledger` still pool once accrual
starts — `source_registry`'s family `hit_rate` and `report_importance_duel::_slice_stats`.
Both are single-basis **today** (no explicit-clock grade row exists yet), so neither is a
wrong number now. The fuse is the first night new claims mature.

## 5. Market-specific ruler resolution

A claim resolves on the calendar of the exchange it is **priced on**, never NYSE by default.
The rule took six rounds to get right, and the first five each let **one source be
sufficient**:

| round | sole source | failure |
|---|---|---|
| 2 | hardcoded NYSE | CN lanes ungradeable on ~26% of windows |
| 3 | "single-letter suffix ⇒ US share class" | `.L`/`.T`/`.F` silently US |
| 4 | "no suffix ⇒ US" | `600519`→US, `0700`→US |
| 5 | provenance (`DESK_MARKET`) | the string `SPY` itself resolved **CN** under a CN desk |
| 6 (#5563) | — | **hard fact wins; inference must agree; silent shape lets provenance decide** |

Round 6 fixed a defect in round 5's own contract: `shape_is_decisive` was documented,
threaded through all four call sites, and **never read in the function body**, so a hard
exchange suffix was vetoed by the desk table — and since `DESK_MARKET` has no HK entry,
**no enumerated desk could claim a Hong Kong security**. The test that "pinned" it asserted
the parameter's *value*, never its *effect*: a guard that could not fail on the defect it
existed to gate.

Live corpus: **46,626 of 46,630** claims resolve (US 40,682 / CN 5,944); **4 refuse**, all
`china_special_sits` on Beijing (`.BJ`) tickers — the intended refusal.

**Stated plainly:** `DESK_MARKET` is **inert on the live corpus** — nulling it changes 0 of
46,630 resolutions. It is prospective insurance, not load-bearing.

## 6. P1 and P2

**P1 (merged).** `_aggregate` computed a pooled **signed** `excess_mean` with no legality
gate. Because that field is raw, pooling it across a family holding both directions measures
universe drift, not skill — and for `radar` and `whitehouse` it reached the **admin
Experiments tab** rendered as `hit=…% · excess=…%`.

**P2 (armed, #5534).** The append-only assertion law, rebuilt around the right rule:
**illegal iff appending a row can falsify it**. This defect class appeared **four independent
times**, each from a builder that had been warned about it in prose in its own brief. Prose
does not prevent it; a mechanical check must.

## 7. P0c — the two rulings

### 7.1 Direction (P0c-1, merged `892ccf52a`)

`promotion_check(control_only=True)` scored a control hit as `subject − control > 0`,
**never reading `direction`** — so every *correct* bearish call scored a MISS and the Wilson
bound ran on an inverted hit series. Now `direction * raw_control_excess > 0`, with
`direction == 0` and missing legs **excluded** from numerator and denominator, and exact zero
not a hit. Pre-registered before the repair.

**What the measurement found is larger than the bug:**

| measure | live value |
|---|---|
| claims declaring a `control` ticker | **0 of 46,630** |
| grade rows with non-null `control_ret` | **0 of 59,929** |
| grade rows with `bench_ret` | 59,929 |
| direction mix | +1: 6,353 · −1: 6,508 · **0: 33,769 (72.4%)** |

**No claim has ever carried a control leg.** Every `control_only=True` verdict ever published
was silently the **bench-relative fallback wearing a control-relative label**, and the
matched-control gate this architecture documents as a core epistemic feature **has never been
exercised in production.** The 08-12 report described a "matched-control grading substrate"
as existing infrastructure; that overstates what it has done.

Two consequences: **P0c-1 corrects nothing retroactively** — the direction bug was *latent*,
because the control branch never fired — and all 17 graded cells move from a computed Wilson
`ci_low` to `None`, which is the honest state when there is no control leg.

### 7.2 Legacy authority (P0c-2, in flight)

Ruling: legacy evidence stays **visible** but may not **originate** new authority. A
legacy-only family may not newly produce `ready=True`, a readiness alert, or an authority
transition; explicit-unit evidence must independently satisfy the gate; legacy N and
explicit N are never combined to clear a threshold; already-granted historical authority is
not revoked.

This **supersedes** a boundary this session pinned three days earlier
(`test_promotion_on_a_legacy_only_family_is_the_documented_status_quo`), whose docstring said
changing it "is a deliberate act with a failing test attached." This is that act.

## 8. P0b — own-ruler grading (merged `1b058d38b`)

`in_scope_horizons`'s docstring promised "always at least the claim's own horizon" and the
code delivered it only when the ladder came back empty (`horizon_d < 5`). Twelve
family-horizon pairs were **permanently** unreachable.

Now: ruler **≤63** includes the own ruler; ruler **>63** does not enter the live nightly
grader. `GRADE_HORIZONS = (5, 21, 63)` is **byte-identical**. Swept 64→1260: **zero** rungs
above the ceiling leak. Cost: **355 claims (0.76%) gain a rung, ~102 KB on a ~16.5 MB store**.

## 9. P3 — the evidence clock has NOT started

**This is the number that matters and it is zero.**

| family | rows | no-call | region-excluded | retrospective | **candidates** |
|---|---|---|---|---|---|
| `stock_desk` (20 trading days) | 703 | 247 | — | 456 | **0** |
| `thematic_desk` (20 trading days) | 259 | — | 189 | 70 | **0** |
| `demand_chain` (126 trading days) | 55 | — | — | 55 | **0** |

Every row in the committed stores predates this programme, so **100% are history and
correctly refuse**. Real N accrues from the first nightly forward after #5577 merges.

**There are therefore no evidence-clock start timestamps to report.** The artifact
(`data/qledger/evidence_clock_start/<family>.json`, write-once) is deliberately never
pre-created; a timestamp written now would be exactly the retrospective stamping the design
exists to forbid.

**The binding constraint is calendar time, not engineering** — and every week not recorded
cannot be reconstructed.

## 10. The investor question, re-answered

*"Can you prove your intelligence is better than attractive-looking commentary?"*

**Today: we can prove the process, not the predictions — and this wave shrank what we may
claim about the process.** The kill registry, the live placebo tape, the point-in-time twin
desks and the prospective arena are genuinely hard to fake. But the matched-control arm of
the promotion gate has never run (§7.1), the horizon a claim was graded at differed from the
one it declared until this week (§3), and no engine has a forward record at its own declared
ruler.

**Any launch claim implying demonstrated predictive edge remains unsupported by our own
evidence.** The defensible six-month claim is unchanged: *a pre-registered,
placebo-controlled, point-in-time-shadowed forward record at declared horizons, with every
disproven idea listed beside it.*

## 11. Decision requested

**The missing control leg (§7.1) is a design question, not a bug fix, and it is above this
session's authority.** `make_claim` accepts `control=`, `control_for_sector()` exists, and no
producer has ever populated it. Either:

1. **the gate's "matched control" arm is real** → every producer must supply a control and
   the promotion gate should refuse `control_only` verdicts until they do; or
2. **it is not** → the gate should stop claiming a control comparison it never makes, and the
   architecture docs must be corrected.

Shipping neither leaves a documented epistemic feature that does nothing. **Recommendation:
(1)**, with `control_for_sector` wired at registration — but it changes what every desk must
emit, so it is a CEO call.
