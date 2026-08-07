# Price-adjustment contamination audit — Prophet US evidence base

**Tier: RESEARCH.** Measurement only. No engine, gate, board, ranker, grader or ledger
changes. Instrument: `research/prophet_us_audit/price_adjustment_audit.py` →
`price_adjustment_audit_results.json`. Helper: `price_ladder.py` (+ `test_price_ladder.py`).

---

## §0 Verdict, in plain words

**No shipped conclusion moves.** The defect is real, its direction is exactly the one
feared — a distribution-paying name loses its own payout against an unadjusted
benchmark — and it is two orders of magnitude too small on these frames to reach any
decision boundary it was suspected of crossing.

| Conclusion | as shipped | adjusted-first | moved? |
|---|---|---|---|
| FRESH_TICKS kill (#4546), `ext − admitted` median dm | **+0.04pp** [−0.18, +0.24] | **+0.01pp** [−0.20, +0.24] | no — null either way |
| veto-label family (#4547), `max_edge_over_control` | **+0.28pp** | **+0.26pp** | no — same labels, same order |
| reclaim-veto packet, `excess_21` median / loser rate | **−4.54pp** / 56.7% | **−4.44pp** / 55.9% | no |
| W8 intersection + S-COIL H=63 (#4564) | **+0.98pp** | *not exposed* | n/a — both legs already adjusted |
| macd_bear per-leg separation (#4678) | −0.26 / −0.57 / −0.52pp | *not re-run — fenced* | see §6 |

The largest single decision statistic moved by the basis anywhere in the re-runs is
**2.5pp**, and it sits in a half-split robustness cell of the ran-lane reconstruction
(§4.2) whose stated finding — *the sign flips across halves* — is identical on both
bases. Across the two instruments with enough statistics to take a distribution over,
basis moves run **p95 0.10pp** (FRESH_TICKS, n=107) and **p95 0.30pp** (label-grading,
n=988); the largest move in any headline block reported above is **+0.34pp**
(reclaim-veto `excess_21` *mean*, against a median that moved +0.10pp).

**One finding does need its own PR** and is not repaired here: `scripts/grade_us_board.py`
pairs a cache-priced name leg with an adjusted benchmark leg in code (§5). Its shipped
artifact is nonetheless clean on this frame, so the exposure is *latent*, not realized.

---

## §1 The defect, and what it is NOT

An excess return is `name_return − benchmark_return`. The subtraction is only meaningful
when both legs share one adjustment basis. The repo carries two families:

| family | stores | behaviour |
|---|---|---|
| **ADJUSTED** | `data/baskets/ohlcv` · `data/yahoo` · `data/stocks` | back-adjusted: prior history is re-scaled when a name goes ex-distribution |
| **UNADJUSTED** | `data/{breadth,midcap_breadth,smallcap_breadth}/_closes_cache.parquet` | raw closes accrued forward; re-based only at an infrequent full rebuild |

**The receipt** (`CFG`, 2026-06-22): the cache reads `67.9900`, `data/baskets/ohlcv` reads
`67.5514` — a 0.649% gap, exactly CFG's 2026-07-01 quarterly dividend. Both stores agree
to the cent at 2026-07-07, *after* the ex-date. SPY exists only adjusted, so a cache-priced
CFG measured against SPY books its own dividend as a loss.

**The control half matters as much as the receipt.** Names with no post-rebuild ex-date —
`JPM`, `KO`, `ALB`, `CEG` — agree *exactly* across all four stores. Without that, a CFG
mismatch would be equally explained by the two stores simply being different data.

### What this is NOT: "the caches are never retro-adjusted"

That framing overstates the blast radius and is worth correcting, because it changes which
studies are at risk. Sweeping all 1,227 cache names that have an adjusted counterpart with
≥200 overlapping sessions:

| deviation from the adjusted basis | names | share |
|---|---|---|
| exact match across the whole overlap | 885 | **72.1%** |
| sub-1% (ordinary quarterly distribution) | 273 | 22.2% |
| 1–5% (REIT / high-yield / special) | 67 | 5.5% |
| 5–25% (`SPGI`, spin-off shaped) | 1 | 0.1% |
| >25% (`SEM`, split shaped) | 1 | 0.1% |

A three-year quarterly payer under a never-rebuilt cache would carry **~12** divergence
steps. The observed median is **0** and the maximum is **8**. And the *first* divergence
clusters hard:

```
first divergence date:  p05 2026-05-13 · median 2026-06-01 · max 2026-07-01
by month:  2023-09: 1 · 2024-11: 1 · 2026-05: 143 · 2026-06: 180 · 2026-07: 17
```

So the caches **are** re-based at a full rebuild and accrue raw rows after it. The last
rebuild landed around **2026-05-12**. The exposure is therefore a bounded **tail**:

- a measurement window that closes **before** the last rebuild carries **zero** bias;
- a window inside **2026-05-12 → 2026-07-31** carries all of it.

That is why a June–July frame (the board ledger, the reclaim-veto packet) is the exposed
case and a three-year frame (FRESH_TICKS: 755 sessions, ~33 of them exposed ≈ 4.4%) is
heavily diluted.

**Corollary worth its own attention:** because the caches are re-based per name over time,
a result computed off them is **not reproducible** — the underlying prices mutate. `PNC` at
2026-06-22 read `234.71` in the 2026-07-01 commit and reads `232.85` today. This is the
mechanism behind the store drift in §4.

---

## §2 Census — who prices what

`exposed` means the name leg and the benchmark leg come from **different** adjustment
families in the same subtraction. Same-family pairings are recorded as **not exposed**
rather than flagged, and the machine self-check in
`price_adjustment_audit.py::census_selfcheck()` re-greps all 16 on-disk files each run so
this table cannot rot into prose (status: **OK**).

### Research

| instrument | name source | benchmark source | exposed | reason |
|---|---|---|---|---|
| `fresh_ticks_extension_replay.py` (#4546) | closes_cache | `yahoo/SPY` | **yes** | mixed basis in every `excess_spy_pp` cell |
| `label_grading_battery.py` (#4547) | closes_cache; weekly leg spliced over yahoo with the **cache winning** | `yahoo/SPY` | **yes** | §2/§3 mix bases; §1 inherits from the ledger; the weekly splice also mixes bases *within* one name |
| `reclaim_veto_packet.py` | closes_cache | `yahoo/SPY` | **yes** | direct subtraction; 126-session window sits inside the exposed tail |
| `name_score_pk_benchmark.py` | ledger `excess_spy` | ledger `excess_spy` | **inherited** | computes no excess of its own; its cache read is a PIT tier recompute (a signal leg) |
| `superintelligence_standins.py` | ledger `excess_spy` | ledger `excess_spy` | **inherited** | same shape as above |
| `relay_position_standin.py` | closes_cache | same-day median of the **same** panel | **partial** | one basis on both legs; residual tilt is only `(name yield − universe median yield)` |
| `leader_reset_study.py` | closes_cache | cross-sectional median of the **same** panel | **partial** | same construction; family already killed |
| `ignition_standins.py` (#4564) | `baskets/ohlcv` | `yahoo/SPY` | **no** | both legs ADJUSTED — W8 intersection and S-COIL are untouched |
| `roc_extremes_battery.py` | `baskets/ohlcv` | `yahoo/SPY` | **no** | both legs ADJUSTED |
| `runner_exclusion_audit.py` | closes_cache | *none* | **no** | raw forward return only; no benchmark leg, so no basis mismatch |
| `post_board_trajectory.py` (#4692) | adjusted-first ladder | `yahoo/SPY` | **no** | the lane that found this; reference implementation |
| `cn_prophet_audit/*` | `china_stocks` | `china/510300.SS` | **no** | self-consistent CN family |
| `entry_timing/wave*.py` | `stocks` / `baskets/ohlcv` | `stocks/SPY → yahoo/SPY` | **no** | never reads a cache; both rungs ADJUSTED |
| `entry_intel/**`, `bottom_signal_backtest/`, `species/s7_rs_repair_phase0/` | `massive_stock_day` / `baskets` / `stocks` | `yahoo` | **no** | same-family. `s7` documents the rule explicitly and is the house reference |

### Production — reported, **not repaired here** (see §5)

| path | name source | benchmark source | exposed |
|---|---|---|---|
| `scripts/grade_us_board.py` | `_closes('broad')` → caches | `yahoo/{SPY,XL*}` | **latent** — mixed in code, clean in the artifact |
| `scripts/prophet_postmortem.py` | cache **rung 1**, baskets/extras only as fallback | `yahoo/SPY` | **yes** (majority case) |
| `engine/manager_trades.py` | `yahoo` **first**, cache as fallback | same ladder → yahoo | **partial** (minority; rung order already correct, fallback undisclosed) |
| `scripts/backtest_special_situations.py` | closes_cache | SPY from the cache if present, else `yahoo` | **partial** (fallback branch only) |
| `scripts/calibrate_bottom_radar.py` | `data/stocks` by default; caches under `--universe breadth\|midcap\|smallcap` | `yahoo/SPY` | **partial** — and its docstring calls the *cache* mode "the proper test" |
| `engine/desk_grader.py` | `yahoo` only | `yahoo/SPY` | **no — already correct** |

**`desk_grader.py` is the finding inside the finding.** It was hardened against this exact
cache on **2026-07-04**, and says so in its own notes: *"grade off `data/yahoo` adjusted
closes ONLY. The S&P-1500 breadth close cache is SPLIT-CORRUPTED — using it silently
poisons every RS / forward-return number."* The house already knew, a month ago. The
knowledge never reached `grade_us_board.py`. Today's residue is overwhelmingly
distribution-shaped rather than split-shaped (§1), but it is the same class of defect.

---

## §3 Magnitude, measured on the production ledger

`data/us_board_ledger/retro_grades.parquet`, 2,287 rows over 2026-06-15 → 07-27; 1,931
comparable on both bases.

**Fidelity gate first.** The cache-basis recompute reproduces the ledger's stored `ret`
with median and p95 absolute difference **0.000000pp** — so what follows measures the
basis, not a reimplementation difference.

| horizon | n | rows affected | affected-row median | **aggregate mean shift** |
|---|---|---|---|---|
| H=5 | 1,306 | 21 (1.6%) | −0.155pp | **−0.005pp** |
| H=10 | 575 | 7 (1.2%) | −0.417pp | **−0.004pp** |
| H=21 | 50 | 0 (0.0%) | — | 0.000pp |

The per-affected-row bias is meaningful. The aggregate a cohort statistic inherits is not:
**−0.005pp against decision boundaries of 0.26–0.98pp.**

### The cohort worry, tested

The brief's real concern was that a split correlating with payer status inherits a
systematic tilt. It does — the gradient is exactly the predicted one — and it is still
negligible:

| sector (H=5) | n | affected | mean shift |
|---|---|---|---|
| Energy | 47 | 12.8% | −0.041pp |
| Materials | 69 | 2.9% | −0.012pp |
| Consumer Staples | 72 | 4.2% | −0.010pp |
| Financials | 230 | 1.3% | −0.007pp |
| Consumer Discretionary | 233 | 1.3% | −0.005pp |
| Industrials | 208 | 0.5% | −0.003pp |
| Health Care | 136 | 0.7% | −0.001pp |
| Info Tech / Real Estate / Comm Svcs / Utilities | 108 / 97 / 32 / 50 | 0.0–4.0% | ≈0.000pp |
| *Communications (11), Technology (12), "history" (1)* | *thin — printed, not read* | | |

Worst sector cell: **−0.041pp**, still 6× below the tightest boundary in the table.

---

## §4 The re-runs — both numbers, side by side

Each instrument gained a `PRICE_BASIS` switch: `cache` (default, reproduces the shipped
JSON) or `adjusted` (the ladder). Frozen JSONs are **not** overwritten; corrections are
written alongside as `*_adjusted_rerun.json`.

Three runs are compared, because two of the differences have nothing to do with the basis:

1. **committed** — the shipped frozen JSON
2. **cache** — today's stores, same basis → isolates **store drift**
3. **adjusted** — today's stores, adjusted ladder → isolates the **basis**

> **A confound caught mid-audit.** The first adjusted run grew the admitted population by
> **+31%** (22,616 → 29,675). That was not the basis: the large-cap `breadth` cache starts
> 2025-03-18 while `baskets/ohlcv` carries the same names back to 2014, so an unmasked swap
> silently handed ~500 large caps two extra years of warm-up. Every re-run below holds the
> universe, the calendar **and the observed-cell mask** fixed, so only price *values*
> differ. (This is also a real finding about the caches: they are ~2 years shallower than
> the adjusted stores for the large-cap sleeve.)

### 4.1 FRESH_TICKS extension replay (#4546) — the kill row

Ladder: 1,226 baskets / 39 yahoo / 1 stocks / **274 still on the unadjusted cache**, 0 unresolved.

| statistic | committed | cache | adjusted | basis Δ |
|---|---|---|---|---|
| `delta_median_dm_pp` (ext − admitted) | +0.040 | +0.040 | **+0.010** | −0.030 |
| `delta_loser_pp` | +0.90 | +0.90 | **+0.90** | 0.00 |
| bootstrap CI95 | [−0.18, +0.24] | [−0.18, +0.24] | **[−0.20, +0.24]** | straddles zero both ways |
| admitted(0–2) median excess | −0.37 | −0.37 | −0.38 | −0.01 |
| ext(3–4) per-name median | −0.50 | −0.50 | −0.54 | −0.04 |

Across **107** decision statistics: 64 moved, median move **0.02pp**, p95 **0.10pp**, max
**0.20pp**. **Zero** moved by ≥0.26pp. Store drift moved 6 statistics and no headline.

**The kill stands.** The registry row that rests on this null is unaffected.

### 4.2 Label-grading battery (#4547) — the veto-label family

Ladder: 1,189 baskets / 38 yahoo / **266 unadjusted**, 0 unresolved.

| statistic | cache | adjusted | Δ |
|---|---|---|---|
| `max_edge_over_control_pp` | **0.28** | **0.26** | −0.02 |
| `control_admitted_per_name_median_pp` | 0.13 | 0.17 | +0.04 |
| `labels_beating_control_H10` | 4 labels | **identical list, identical order** | — |
| `of_which_sign_flip_across_halves` | 2 labels | **identical** | — |
| `leg_replication_mismatches` / `dead_legs` | 0 / [] | 0 / [] | — |

Across **988** decision statistics: 385 moved, median **0.08pp**, p95 **0.30pp**, max
**2.50pp**. The 31 moves ≥0.28pp are concentrated in the §3 ran-lane half-split
(`b_ran_array_reconstructed/H10/half_split`), where `per_name_median_gap_pp` moves
**1.87 → 1.15** and the two halves re-partition (n 1257/1057 → 1155/1154, because the
event set shifts the median split date). That is a genuinely basis-sensitive robustness
cell and it is reported as one — but its stated finding, `half_split_sign_flip: True`, is
**identical on both bases**, as is the §3 stage-ran block (n=55, loser 14.5%, Δ +0.72pp),
which is byte-identical because it is ledger-fed.

**The null holds.**

> The battery's original overlap check — *"median max relative difference 0.000000 over a
> 40-name sample"* — **could not have found this defect**. 72.1% of names are bit-identical
> across the two bases, so the median of any sample is 0.000000 whether or not the rest
> diverge. A max, or a nonzero-share over the full universe, is the statistic that can see
> it. The caveat is now stamped into the instrument's own provenance block.

### 4.3 Reclaim-veto packet — the most-exposed frame

Its 126-session window sits inside the unadjusted tail, so this was the highest-risk
instrument in the set. It reproduces its frozen numbers exactly on today's stores (the only
non-numeric change is a refusal-reason string now bound to a since-updated engine constant).

| statistic | cache | adjusted | Δ |
|---|---|---|---|
| `excess_21` median / mean | −4.542 / −3.367 | −4.441 / −3.031 | +0.10 / +0.34 |
| `excess_10` median | −0.872 | −0.966 | −0.09 |
| `excess_63` median | −5.610 | −5.643 | −0.03 |
| saved-side loser rate | 56.7% | 55.9% | −0.8pp |
| cost-side winner share | 29.8% | 30.5% | +0.7pp |
| `n_fires` / `n_names` | 353 / 315 | 358 / 318 | +5 / +3 |

The packet's decision — the veto saves more than it costs — rests on the saved-side loser
rate against the cost-side winner share. Both move under 1pp and in the directions that
*narrow* the gap slightly, nowhere near reversing it. **Conclusion unchanged.** Note the
fire count itself is mildly basis-sensitive (+5), because the signal legs are computed on
the same panel; that is a population effect, not a return effect.

---

## §5 PRODUCTION FINDING — `scripts/grade_us_board.py`

**Read the code and it is exposed. Measure the artifact and it is not.** Both halves are
receipts and both belong in the report.

`_load_prices()` returns `(names, etfs)` under the docstring *"Both dividend-adjusted TR
closes."* The ETF leg is `data/yahoo/{SPY,XL*}.parquet` — adjusted, as claimed. The name leg
is `engine.equity_factors._closes('broad')`, which reads the three `_closes_cache.parquet`
files directly. `excess_spy = nret − sret` (L887) subtracts one from the other, with no
fallback: **every** graded name is priced this way in code. `extend_prices_to_admitted()`
then splices yahoo-adjusted recovered names into the same panel, so the panel is internally
mixed as well — and its comment asserts the opposite ("uses the SAME dividend-adjusted
yahoo closes… so the price convention is unchanged").

**But the shipped ledger does not carry the bias.** Of the 1,931 comparable rows, 28 are
rows where the two bases genuinely differ. On **28 of 28**, the ledger stores the
**adjusted** value (max gap to adjusted: 1.1e-05 pp):

| ticker | entry | H | cache basis | adjusted basis | **ledger stores** |
|---|---|---|---|---|---|
| LPG | 2026-06-22 | 5 | −13.8224% | −11.8780% | **−11.8780%** |
| LKFN | 2026-06-24 | 5 | +1.6948% | +2.5674% | **+2.5674%** |
| PNC | 2026-06-18 | 5 | +4.7458% | +5.5809% | **+5.5809%** |
| CL | 2026-06-18 | 5 | +2.3080% | +2.8945% | **+2.8945%** |
| FAST | 2026-06-23 | 5 | +4.7541% | +5.3290% | **+5.3289%** |

And this is not a later repair: ledger rows are **never re-graded** — 0 of 950 rows shared
with the 2026-07-03 ledger commit changed. The adjusted value was written at grading time.

**Therefore the exposure is LATENT, not realized.** The pairing in the code is wrong; the
artifact on this frame is clean. **The path that supplies the adjusted price was not
identified in this audit**, so the protection is not understood and must not be assumed to
hold on the next frame — which is exactly why this needs its own PR rather than a
reassurance. Filed for that PR:

1. Route the name leg of `grade_us_board.py` through an adjusted-first ladder and stamp
   `price_source` per graded name.
2. Fix the two docstrings that assert an adjustment guarantee the code does not provide
   (`_load_prices`, `extend_prices_to_admitted`).
3. Determine empirically why the current ledger is adjusted — the answer decides whether
   any historical ledger rows need re-grading, and this audit could not settle it.
4. `scripts/prophet_postmortem.py` is the same defect with **no** protective ambiguity:
   the cache is rung 1 and the benchmark is always `yahoo/SPY`, so the common case is
   mixed. It has no comparable clean-artifact receipt and should be treated as the more
   likely live contamination of the two.

---

## §6 Migration backlog — named, not silently left

The helper is adopted **only** in the three instruments re-run here. The rest are listed
rather than rewritten, because changing a frozen instrument without re-running it produces
an artifact that matches neither basis.

| file | why it is on the list | priority |
|---|---|---|
| `scripts/prophet_postmortem.py` | production, cache-first ladder, no clean-artifact receipt | **P1** |
| `scripts/grade_us_board.py` | production, latent; feeds ledger + Track-record surface + 4 research instruments | **P1** (own PR, §5) |
| `scripts/calibrate_bottom_radar.py` | non-default mode is mixed *and* documented as "the proper test" | P2 |
| `scripts/backtest_special_situations.py` | mixed only on the yahoo fallback branch | P2 |
| `engine/manager_trades.py` | rung order already correct; fallback undisclosed | P3 |
| `veto_leg_isolation.py` (#4678, macd_bear) | **fenced from this PR.** Its −0.26pp separation is the tightest boundary in the set and the measured aggregate shift is ~0.005pp, but it was not re-run here and this audit does not clear it | **P1 — re-run before ratification** |
| `relay_position_standin.py`, `leader_reset_study.py` | same-basis both legs; only the second-order tilt applies | P3 |
| `name_score_pk_benchmark.py`, `superintelligence_standins.py` | inherit from the ledger; fixed when §5 is fixed | follows P1 |

---

## §7 The helper

`research/prophet_us_audit/price_ladder.py`

```python
r = resolve_close("CFG", asof="2026-07-31")
r.price_source   # "baskets_ohlcv" | "yahoo" | "data_stocks" | "closes_cache_UNADJUSTED"
r.adjusted       # True unless the ladder fell through to a cache
r.tried          # every rung attempted, in order
r.reason         # populated only when the series is None

px, prov = close_panel(tickers, asof=..., start=...)
prov["names_on_unadjusted_basis"]   # counted AND named, never hidden
prov["price_source"]["CFG"]          # per-name stamp
```

Ladder: `baskets_ohlcv → yahoo → data_stocks → closes_cache_UNADJUSTED → null-with-reason`.
Coverage still comes first — the ladder falls **through** to the cache rather than dropping
a name, because dropping an unpriced name deletes exactly the population a study exists to
measure — but the fallback is stamped and counted so it can never be silent.
`allow_unadjusted=False` refuses the cache rung for studies that would rather lose a name
than mix bases. `data_dir` is injectable on every entry point so the tests run with no repo
data.

**Tests** (`test_price_ladder.py`, 13 passing): adjusted-first ordering · each fallback rung
in turn · fallback counted *and named* · `allow_unadjusted=False` refuses with a reason ·
an ex-distribution name resolving to the adjusted series (and the cache booking the payout
as a loss) · absent-from-everything → null with reason · empty and unreadable files falling
through rather than passing as hits · a window closing before the ex-date carrying zero
bias · **the CFG regression**, both against the real stores *and* as a synthetic twin that
never skips, plus the `JPM`/`KO`/`ALB`/`CEG` control that stops the CFG assertion from
passing merely because two stores hold different data.

**Mutation-checked**, because a passing test proves nothing until it has been shown it can
fail. Re-ordering the ladder to cache-first — the exact defect the module exists to
prevent — fails **7** tests including *both* CFG regressions. Silently dropping the
unadjusted-fallback disclosure fails the disclosure test. The module was restored
byte-identical (md5 verified) after each.

**Verification of this document:** all **87** load-bearing numbers are machine-checked
against the committed JSONs rather than transcribed by hand. That check found 6 errors on
its first run — including a CI that had been copied from the *pre-mask* run — all fixed
before this doc was committed.

---

## §8 Reproduce

```bash
python3 research/prophet_us_audit/price_adjustment_audit.py          # census + magnitude
python3 -m pytest research/prophet_us_audit/test_price_ladder.py -q  # 13 tests

PRICE_BASIS=adjusted python3 research/prophet_us_audit/fresh_ticks_extension_replay.py
PRICE_BASIS=adjusted python3 research/prophet_us_audit/label_grading_battery.py
PRICE_BASIS=adjusted python3 research/prophet_us_audit/reclaim_veto_packet.py
```

Default `PRICE_BASIS=cache` reproduces the shipped JSONs. The committed frozen artifacts
predate the provenance stamp and ~5 rows of store drift; every headline figure in them is
unchanged under a same-basis re-run today (§4).
