# CN bearish-divergence veto-leg audit — does the leg that blocks 湖南黄金-class reclaims earn its keep? (2026-08-04)

## DECISION-RELEVANT SUMMARY

1. **Overall: the leg FAILS its keep on this window, at both horizons.** Fires it blocks that
   every other leg would admit (n=162/161) do **not** underperform today's takes (n=1,681/1,633):
   win 48.8% vs 47.4% (H=10) and **52.2% vs 43.9% (H=21)** — the wrong direction for a protective
   leg. Catastrophic share and MAE-p10 also lean the wrong way (−0.7pp/−2.1pp; +0.6pp/+0.9pp).
2. **Strength of that verdict differs by horizon.** At H=21 the vetoed cell's Wilson CI
   [44.5, 59.8] lies entirely above the keep bar (40.9%) — protection is ruled out at 95%. At
   H=10 the CI [41.2, 56.4] straddles the bar (44.4%): the point estimate fails, the interval
   cannot exclude protection. Read H=10 as "no measurable protection", not "proven harmful".
3. **In the Recovery+/Trough+ cell: UNDECIDED — n=3.** The whole year yields three vetoed fires
   in that state. Nothing can be ruled either way there.
4. **But the "systematically blocking early-Recovery reclaims" premise does not hold.** Among
   basket-mapped fires the veto's Recovery+/Trough+ share is **11.5% (3/26) vs 17.3% (51/295)
   for admitted** — under-represented, not over. (Coverage caveat: only ~16% of fires map.)
5. **The motivating case does not survive its own receipt.** Re-running production with the
   divergence leg removed leaves 002155.SZ **still blocked** — `failed reclaim-and-hold`. It sits
   in `VETOED_BLOCKED_ANYWAY` (575 of 743 vetoed fires, 77%). The divergence string is only the
   *first* leg to fire; removing it would not surface 湖南黄金.
6. **Robustness FAILS the half-split — the sign inverts.** H1 vetoed better (+4.1pp/+10.3pp);
   H2 vetoed **worse** (−11.8pp/−6.7pp, catastrophic +5.6pp/+9.1pp). The FAILS verdict is carried
   by H1 (126 of 162 fires). This is regime oscillation, not a stable null.
7. **The one cell where the veto looks protective is the deepest-drawdown tercile** (≤ −13.6%:
   Δwin −14.6pp/−7.8pp, catastrophic +2.6pp/+8.1pp) — which is exactly where 002155 (−44%) sits.
8. **Cost of the leg is small**: 743 gross blocks, decision set 168, **+9.7% more takes** if removed.
9. **RECOMMENDATION: do NOT remove the leg. Prereg + forward shelf.** In-sample, one year, one
   market, half-split inverting, and the motivating name unaffected. Nothing here licenses a change.

---

## Status and scope

MEASUREMENT ONLY — in-sample, motivating-only, **no promotion and no gate change**. Verdict
language is "the leg earns / fails its keep on this window"; it feeds a prereg + ratification,
never a hot removal. Instrument: `research/cn_prophet_audit/cn_divergence_veto_audit.py`; frozen
numbers: `research/cn_prophet_audit/cn_divergence_veto_results.json` (rerun:
`python3 research/cn_prophet_audit/cn_divergence_veto_audit.py`, 200s).

**Trigger.** 湖南黄金 002155.SZ, −44% off its 252d high inside `cn_gold` while that basket reads
phase Recovery / osc_slope +12.9 with narrative HOT, carries
`gate_reason = "buy blocked by filter: veto: bearish divergence"` on every stamped board date in
`data/china_prophet_rank/candidates.parquet`. HK removed its 200dma-reclaim veto after
measurement (#4470) and `research/HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md` §0 G6 named this
leg as the next lever — measuring a null in HK ("blocks 1,148 signals for no measurable return
cost and no drawdown benefit"). The CN side had never been measured.

## The leg, re-derived from production (not approximated)

`engine/signal_quality.py:178` — `_buy_filter(i, sig, bear, n, *, reclaim_veto: bool = True)`
opens with the divergence test, before every other leg and unconditional on `reclaim_veto`
(lines 208-209):

```python
if bear:
    return False, "veto: bearish divergence"
```

`bear` is supplied by the caller at `engine/signal_quality.py:238` inside `analyze()`:
`_bear_div(i, sig["high"], macd, hi)`.

**Exact firing condition** — `engine/signal_quality.py:169`, over swing highs from
`engine/signal_quality.py:164` `_swing_highs(s, w=2)` (index `h` is a swing high iff
`v[h] == v[h-2:h+3].max()`):

```python
rh = [h for h in hi if i - look < h <= i]          # look = 12
return len(rh) >= 2 and pv[rh[-1]] > pv[rh[-2]] and mv[rh[-1]] < mv[rh[-2]]
```

*The last two confirmed swing highs inside the trailing 12 bars print a HIGHER price high
against a LOWER RSI-MACD high.* Everything sits on the 3-business-day resample
(`signal_frame`: `daily_close.resample("3B")`), so one bar ≈ 3 sessions and `look=12` ≈ 36
business days.

**CN call site and policy.** `scripts/build_china_library.py:1960`
`sig_verdict[ticker] = signal_gate.gate(ticker, close)` → `engine/signal_gate.py:155`
`gate(..., reclaim_veto: bool = True)` (the DEFAULT path — CN never passes `False`) →
`analyze(ticker, daily_close)` **with no `daily_high`/`daily_low`**, so `signal_frame` takes the
`h3 = l3 = s3` branch and `_bear_div`'s price leg reads the 3D **close**, not an intrabar high.
The instrument reproduces that exactly (close-only).

**Entanglement: none.** The veto is the first statement of `_buy_filter` and returns before the
reclaim/hold branches, so "remove the leg" is exactly the production call
`_buy_filter(i, sig, False, n, reclaim_veto=True)` — a counterfactual, not a reimplementation.
`tests/test_hk_reclaim_veto_policy.py:77-79` independently pins the leg's orthogonality to
`reclaim_veto`. The leg is therefore audited standalone; no entangled family was needed.

## Design (pre-registered; nothing below was chosen after seeing a result)

| | |
|---|---|
| Panel | `data/china_stocks/*.parquet`, ≥250 bars → **1,637 names** (41 skipped thin) |
| Window | anchor date in 2025-08-01 … 2026-07-31 · frozen replay at GRADE_ASOF 2026-08-04 |
| Fire | the production buy event `CB[i] or revBuy[i]` (the `is_buy` test at `signal_quality.py:236`) |
| Cells | `VETOED_ADMIT` = bear ∧ counterfactual-take · `ADMITTED` = ¬bear ∧ production-take. Both sides have passed **identical** non-divergence legs; the only difference is the divergence state |
| Anchor | last daily session of 3B bar **i+2** — the first close at which the label is knowable |
| Ruler | T+1 **HL2** fill, locked-limit (T+1 high==low==close) **excluded**; CSI300-relative (510300.SS) excess at H=10 / H=21 |
| Metrics | n · win% + Wilson 95% CI · median/mean excess · MAE-p10 · catastrophic (**absolute** ≤ −15%) |
| Dedup | within-cell, 5 sessions per name (inert here: 1,892 → 1,892) |

**Marker-date grading is forbidden** (`engine/signal_quality.py:190-201`; CN-1 §W6-CN).
`_buy_filter` reads bars i+1/i+2 and `_swing_highs(w=2)` confirms a high only at h+2, so both
look-aheads are covered by the i+2 anchor. Leak-free for the divergence leg specifically:
`_bear_div` filters `h <= i`, and every `h <= i` is confirmed by i+2, so the full-series `hi`
list yields the same `rh` a point-in-time recomputation would. `resample("3B")` labels buckets on
the **left** edge, so the anchor is resolved through an explicit bucket→last-daily-date map and
never by reading a bar label as a close date.

**KEEP RULE (pre-registered).** Mirrors `research/signal_engine/VETO_LEG_AUDIT.md`'s "a leg earns
its keep on a cell iff that cell stops out ≥ +3pp worse", and the HK removal's return-leg +
risk-leg pairing (`HK_BOARD_RESURRECTION_MASTERPLAN_BY_FABLE.md` §0 G6: mean excess with a
zero-crossing CI, 60d MAE, and P(excess<−20%) reported together):

> The veto **EARNS** its keep on a cell iff **either**
> (R) win%(VETOED_ADMIT) ≤ win%(ADMITTED) − 3pp, **or**
> (K) catastrophic%(VETOED_ADMIT) ≥ catastrophic%(ADMITTED) + 3pp, or MAE-p10 deeper by ≥ 3pp,
> on a cell with **n ≥ 100 on both sides**. Neither leg → **FAILS**. n below the floor →
> **UNDECIDED** (printed, never read as a pass).

Reported alongside (a stricter read of the same rule, **not** a rule change): whether the vetoed
cell's Wilson CI **excludes** the return-leg keep bar. A FAILS verdict whose CI straddles the bar
is "no measurable protection", not "proven harmful".

**P0 gate (passes before any cycle cell is printed).** The basket-cycle stratifier has no
historical store — `data/china_sector_cycles/forward_log.parquet` starts 2026-06-26 — so it is
reconstructed through the production path (`baskets_china.compute_china_baskets` →
`china_sector_cycles._basket_series` → `sector_cycles._record_core`, series truncated at each
stamp, `win_start` matched to `china_sector_cycles.py:250`). It reproduces the shipped 2026-08-03
`cn_gold` read **exactly — Recovery / pos 13.5 / osc_slope 12.9** — and agrees with the shipped
log on **144/154 (93.5%)** overlapping (basket, date) phase pairs with median |Δosc_slope| = 0.0.

## Funnel — what the leg actually costs

| | |
|---|---|
| Fires in window | 5,157 |
| Vetoed (gross) | **743** (14.4% of fires) |
| …that another leg blocks anyway | **575 (77.4%)** |
| …decision set (would be newly admitted) | **168 (22.6%)** |
| Takes today | 1,730 |
| Extra takes if the leg were removed | **+9.7%** |

Unlike HK's reclaim veto (68% of all rejections), this leg is **not** the CN board's primary
blocker. The reclaim-and-hold leg is: 2,684 non-vetoed fires fail it.

## Headline — VETOED_ADMIT vs ADMITTED

| H | cell | n | names | win% | Wilson 95% | med exc | mean exc | MAE-p10 | catastrophic |
|---|---|---|---|---|---|---|---|---|---|
| 10 | vetoed→admit | 162 | 156 | **48.77** | [41.19, 56.40] | −0.58 | +1.21 | −14.23 | 4.94 |
| 10 | admitted | 1,681 | 1,111 | 47.41 | [45.03, 49.80] | −0.48 | +1.22 | −14.87 | 5.65 |
| 21 | vetoed→admit | 161 | 155 | **52.17** | [44.50, 59.75] | +0.67 | +2.52 | −19.83 | 10.56 |
| 21 | admitted | 1,633 | 1,091 | 43.85 | [41.46, 46.26] | −1.87 | +1.83 | −20.71 | 12.68 |

**H=10 — FAILS** (Δwin **+1.4pp**, Δcatastrophic −0.7pp, ΔMAE-p10 +0.6pp; keep bar 44.41%,
CI does **not** exclude it). **H=21 — FAILS** (Δwin **+8.3pp**, Δcatastrophic −2.1pp, ΔMAE-p10
+0.9pp; keep bar 40.85%, CI **excludes** it). Every leg of the keep rule points away from
protection. Name concentration is a non-issue: top-5 names are 6.2% of the vetoed cell (156
names for 162 events) and 1.2% of the admitted cell.

**Fill-convention robustness.** Swapping the pinned T+1 HL2 for the production open-preferring
fill (`china_standout_track._t1_fill`) moves every headline win% by ≤ 0.6pp and every median by
≤ 0.12pp. Not fill-driven.

> **Read the absolute level with care.** Both cells are near-coin-flip because this is the raw
> `signal_gate` fire population across all 1,637 names, **not** the Prophet board (which layers
> rank, tier, liquidity, extension and featured gates on top and whose ledger reads very
> differently). The comparison here is cell-vs-cell; the level is not a board win rate.

## Stratification

### The Recovery+/Trough+ cell — the operator's question

| H | cell | n | win% | med exc | catastrophic | verdict |
|---|---|---|---|---|---|---|
| 10 | vetoed→admit, Recovery+/Trough+ | **3** | 66.67 | +6.33 | 0.0 | UNDECIDED |
| 10 | admitted, Recovery+/Trough+ | 44 | 61.36 | +1.84 | 0.0 | — |
| 21 | vetoed→admit, Recovery+/Trough+ | **3** | 66.67 | +8.31 | 0.0 | UNDECIDED |
| 21 | admitted, Recovery+/Trough+ | 38 | 42.11 | −1.93 | 7.89 | — |

**n=3. Nothing is readable here and nothing is claimed.** Two things *are* readable:

* **Composition refutes the "systematic" framing.** Among basket-mapped fires, Recovery+/Trough+
  is **11.5% (3/26)** of the veto's decision set but **17.3% (51/295)** of admitted fires. The
  veto lands *less* often on early-Recovery reclaims than the admitted population does. Coverage
  caveat: only 15.5% of vetoed and 17.1% of admitted fires map to a curated basket at all, so
  this is a weak signal — but it points against the premise, not for it.
* **Both Recovery+ cells are the best-performing cells in the study** (admitted Recovery+ wins
  61.4% at H=10 vs 47.4% pooled). The cycle state is doing real work; the veto is not what stands
  between the board and it.

### Drawdown tercile — where the leg looks protective

| tercile | H | VET n | VET win | ADM win | Δwin | Δcatastrophic | verdict |
|---|---|---|---|---|---|---|---|
| T1 deepest (≤ −13.6%) | 10 | 34 | 32.35 | 46.91 | **−14.56** | +2.63 | UNDECIDED (n) |
| T1 deepest | 21 | 34 | 32.35 | 40.14 | **−7.79** | +8.11 | UNDECIDED (n) |
| T2 mid (−13.6…−5.6%) | 10 | 61 | 59.02 | 47.90 | +11.12 | −3.30 | UNDECIDED (n) |
| T2 mid | 21 | 61 | 65.57 | 45.42 | +20.15 | −5.55 | UNDECIDED (n) |
| T3 shallowest (> −5.6%) | 10 | 67 | 47.76 | 47.46 | +0.30 | +0.17 | UNDECIDED (n) |
| T3 shallowest | 21 | 66 | 50.00 | 46.06 | +3.94 | −4.44 | UNDECIDED (n) |

Every tercile is under the n floor, so none of these is a verdict. Directionally they reproduce
the US not-topped study's shape (`VETO_LEG_AUDIT.md`): **the tradable washout lane is the MID
pullback bucket** — where the veto blocks the single best-performing cell in the study — while
the **deepest** bucket is the one place the block looks justified. **002155 (−44%) sits in T1**,
the tercile that argues *for* the block, not against it.

### Narrative level

Coverage collapses (26 of 162 vetoed fires map): HOT n=8, WARMING n=9, no tag n=9. Every cell
UNDECIDED, nothing readable. No historical narrative store exists — `narrative_level` is only
persisted incidentally in `candidates.parquet` from 2026-07-30 — so the tape is a reconstruction
through `china_narrative_tags.narrative_heat` on the closes panel truncated at each weekly stamp.

### Half-split robustness — **the sign inverts**

| half | H | VET n | VET win | ADM win | Δwin | VET cat | ADM cat | verdict |
|---|---|---|---|---|---|---|---|---|
| H1 2025-08…2026-01 | 10 | 126 | 53.17 | 49.03 | +4.14 | 1.59 | 1.83 | FAILS |
| H1 | 21 | 126 | 57.94 | 47.61 | +10.33 | 3.97 | 4.37 | FAILS |
| H2 2026-02…2026-07 | 10 | **36** | 33.33 | 45.13 | **−11.80** | 16.67 | 11.03 | UNDECIDED (n) |
| H2 | 21 | **35** | 31.43 | 38.15 | **−6.72** | 34.29 | 25.23 | UNDECIDED (n) |

**This is the most important robustness fact in the study.** The overall FAILS verdict is carried
by H1 (126 of 162 fires). In H2 the veto looks genuinely protective on *both* legs — it would
EARN at H=10 (Δwin −11.8pp, Δcatastrophic +5.6pp, ΔMAE-p10 −5.7pp) if n cleared the floor. H2 is
also a materially worse tape for everyone (admitted catastrophic 1.8% → 11.0%). Read together:
**the leg's value is regime-conditional and this window is too short to separate that from
noise** — the same decade-oscillation pattern that stopped `VETO_LEG_AUDIT.md` from deleting
`macd_bear`.

## Case receipt — 002155.SZ on 2026-08-03, from production code paths

Replayed with the series truncated at the board date (PIT), close-only, `reclaim_veto=True`:

| | |
|---|---|
| Last buy marker bar (3B label) | 2026-06-17 |
| Swing highs in the `look=12` window | 2026-05-06, 2026-05-22, **2026-06-17** |
| Price at the last two | 25.700 → **26.660** (higher high ✔) |
| RSI-MACD at the last two | −6.53230 → **−7.41674** (lower high ✔) |
| `_bear_div` | **True** |
| Production verdict | `take=False`, `reason="veto: bearish divergence"` |
| Rendered gate reason | `buy blocked by filter: veto: bearish divergence` |
| Shipped board row | identical string, `buyable=False`, `off_high=−44.3`, `narrative_level=HOT` |
| **Counterfactual, veto removed** | **`take=False`, `reason="failed reclaim-and-hold"`** |
| dd from 252d high | −44.27% |

The instrument reproduces the shipped `gate_reason` byte-for-byte
(`reproduces_shipped_gate_reason: true`), which is the trust gate for everything above.

**The finding that reframes the case: removing the bearish-divergence leg would NOT surface
湖南黄金.** Its buy fails the next-bar hold independently. It belongs to `VETOED_BLOCKED_ANYWAY`
— 77.4% of all vetoed fires — not to the decision set. `gate_reason` names the divergence veto
only because it is the **first** leg to fire; the reason string is a first-match label, not an
exhaustive account of why a name is blocked. Any future board copy that lists a single blocking
reason inherits this ambiguity.

## Verdict

**On this window the bearish-divergence veto FAILS its keep overall, and the Recovery+/Trough+
cell is UNDECIDED at n=3.** The failure is not evidence the leg is harmful: at H=10 the interval
cannot exclude protection, the half-split inverts, and the one cell where the leg looks
protective (deepest-drawdown) is exactly where the motivating name sits.

**Do not remove the leg.** Recommended next step, mirroring `VETO_LEG_AUDIT.md`'s
recommendation 3 and the G6 prereg discipline HK's own masterplan says the divergence leg still
deserves:

1. **Prereg, not a patch.** Register the keep rule above with an out-of-sample window and a
   forward cohort before any admission change. Nothing in this document is out-of-sample.
2. **Display-tier relief first** — the HK `vetoed` lane pattern. Make blocked names visible with
   the blocking reason named, and (learning from the case receipt) name **every** failing leg,
   not just the first match. That is the cheap, honest fix for the 湖南黄金 complaint, and it
   would have shown at a glance that this name is blocked twice over.
3. **The forward cohort settles it.** Accrue `VETOED_ADMIT` fires on the CN forward ledger from
   day one; revisit at ≥100 matured fires spanning ≥2 quarters, with the half-split repeated.

## Limitations

One year, one market, **in-sample**, no out-of-sample holdout — motivating only. The half-split
does not hold (§Half-split), which alone disqualifies the headline from carrying authority.
H=21 cannot mature for fires anchored after ~2026-07-02, so H=21 cells are smaller and
end-loaded. Basket membership is hindsight-curated (`engine/baskets_china.py` module docstring
says so) and today's roster is applied to past dates, so the cycle and narrative stratifiers
inherit both that and any data-vintage restatement — 93.5% phase agreement against the shipped
log measures how much. Cycle/narrative coverage is ~16% of fires; those strata are directional at
best. Name-clustered dependence is not modelled (name spread is reported instead: 156 names for
162 vetoed fires). 5 fires were dropped as T+1 locked-limit and 1 for no T+1 bar — excluded, never
fabricated. The absolute win rates are the raw `signal_gate` fire population, not the Prophet
board.
