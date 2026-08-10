# CN WEAKNESS-ENTRY BATTERY v1 — 回封 + 龙回头, fillable by construction

**Program** CN LIMIT-MOVE ALPHA, Wave 2, lane W2-B
**Tier** display / audit — MEASUREMENT ONLY. Nothing here ranks, sizes, gates or admits. No LLM is involved.
**Instrument** `research/cn_prophet_audit/weakness_entry_battery_v1.py` (deterministic, 20.1 s)
**Data** `research/cn_prophet_audit/WEAKNESS_ENTRY_BATTERY_V1_2026-08-09.json`
**Builds on** v0 footprint (PR #4999) · L1 continuation rider (PR #5061) · L2 board-ecology dial · blinded map C3 / C10

Wave 1's rider proved the continuation ladder is real and era-stable, and then proved that
every naive next-open gap-chasing book loses money — anti-monotone in its own conditioner,
because the 09:25 auction prices public strength. Its ORE LEDGER named the family that
survives that null by construction: **weakness entries**. Buy the name on a day it is *not*
sealed. The fill is guaranteed, and the adverse selection is supposed to invert — you are not
paying the crowd's gap, you are being paid to absorb it.

This instrument tests the two weakness families the daily basis can see. Both fail.

---

## DECISION SUMMARY

**1. THE ANSWER TO THE LANE'S QUESTION IS NO — and the statistic that carries that verdict is
the t-census, not the survivor count.** Across all 210 pre-registered cohorts (n ≥ 100 in both
windows), the **largest holdout date-clustered t is 1.86, and the number reaching t ≥ 2 is
zero.** That needs no multiplicity correction to be damning, and it is the sentence to quote.

The survivor count cannot carry the verdict, because it is only interpretable against a
**per-family** chance benchmark — and pooling the families manufactures a false result:

| Family | Cohorts | Clearing net, both | Family drift (net/trade) | Coin-flip benchmark |
|---|---|---|---|---|
| HF **T+1 open** (L1's anchor, control) | 84 | 23 | **+0.124%** | applies — expectation **21.0**; observed 23 is **at its own null** |
| HF **T close** (break day, 低吸) | 84 | **1** | **−0.959%** | does not apply — a family this far from zero throws essentially no chance survivors |
| **龙回头** q close (pullback day) | 42 | **0** | **−1.104%** | does not apply, same reason |

An earlier draft pooled all three and read 23 survivors against "~52 expected", concluding the
population was *below* chance. **That was an artifact of pooling.** All 23 survivors sit in the
one family whose drift is near zero, where the honest expectation is 21 — so that family is
*at* its benchmark, not under it — while the 126 close-anchored cohorts contribute a chance
expectation of ~0 rather than ~31, which is what dragged the pooled comparison down. The
corrected reading is narrower and less flattering to the null: the weakness anchors fail on
their own numbers, and the control family is indistinguishable from chance.

**2. Both weakness anchors fail; one close cohort survives the raw bar and not the inspection.**

| Family | Anchor | Tested | Clearing net, both | Best holdout net (excl. missing-data slices) |
|---|---|---|---|---|
| B-回封 | **T close** (break day, 低吸) | 84 | **1** | +0.345% |
| B-龙回头 | **q close** (pullback day) | 42 | **0** | +0.677% (fails fit) |
| B-回封 | T+1 open (control) | 84 | 23 | +0.868% |

The lone close-anchored survivor is `HF|tolerant|chinext|T_close|E3|volz=vz1_mid`: holdout net
**+0.345%** on n = 222, against a fit mean of **+0.023%** — indistinguishable from zero in the
window that selected it. It fails date-equal weighting (fit date-eq **−0.009%**), fails the
n ≥ 500 floor, and its holdout date-clustered t is **1.17**. A marginal cell on the smallest
board, not a finding. **125 of 126 close-anchored cohorts print negative and the 126th is zero
in fit.**

**3. THE CENTRAL FINDING — the break-day close is not a discount, it is a premium.** On
*identical* break days with *identical* exit bars, buying the T close instead of the T+1 open
costs **−1.229 pp per trade in fit and −1.069 pp in holdout** (E3; win rate −6.8 / −5.1 pp).
The cause is not a residual — it is an identity, and it closes to under a basis point once the
gap is measured on the right population. The **paired-population** mean overnight gap (main,
strict, fillable opens only) is **−1.2217% in fit and −1.0745% in holdout**, leaving
unexplained residuals of **−0.0073 pp and +0.0055 pp**. The market re-prices a broken board
downward overnight, so the "guaranteed fill" is bought about one percent above where you could
have bought it the next morning. Date-clustered t on the close book is **−3.92** (E3) and
**−8.13** (E1) — structural, not marginal.

*(The gap must be measured on the paired population. Averaged over all usable break days it
reads −1.2077% / −0.9525%, because that pool includes the unfillable opens — whose mean gap is
**+9.98%** by construction — and those are exactly the rows the paired comparison excludes. An
earlier draft quoted the all-rows holdout figure and left ~0.12 pp of the delta unexplained.)*

**4. The access the weakness entry was supposed to buy does not exist.** The premise was that
a close entry owns the names that gap away to an unbuyable open. On the 回封 cohort the T+1
open is unfillable **0.48%** of the time (n = 55 holdout, 11 fit) — because a name that just
*failed* to hold its board almost never gaps to a locked open. On the **same exit rule** as the
−1.069 pp figure above (E3), those rare trades return **+0.181% net** on the holdout — at 1%
frequency, nowhere near enough to offset −1.069 pp on the other 99%. **The fillability tax that
made L1's ladder unbuyable is simply absent here, and with it the whole reason to prefer the
close.**

*(An earlier draft advertised **+5.9%** here. That is the E1 figure, set against an E3 delta —
mixing two exit rules in one comparison. E1's holdout remainder is indeed +5.906% on the same
55 trades, but the honest same-rule number is E3's +0.181%, and the two differ by enough to
change how the sentence reads.)*

**5. 回封 rates are real but small, and breaking the seal destroys most of the ladder's edge.**
Main board, next-day limit-up close: **3.27% strict** (n = 13,810) / **5.74% tolerant**
(n = 30,071). Against v0's unconditional next-bar rate of **1.27%** that is a 2.6× lift — but
against a board that *held* at N = 1 (**16.50%**) it is roughly **five times lower**. A
touched-and-lost board is far closer to a random day than to a sealed one.

**6. Break depth is NOT a stable conditioner — and the trapdoor asymmetry is the real result.**
Re-seal by depth flips shape between windows (fit monotone 1.56 → 2.99 → 3.67%; holdout
flat-to-humped 2.98 → 3.92 → 3.71%, Wilson intervals overlapping). What *is* stable is the
risk side: the deep band (> 3% off the limit) roughly **doubles** the next-day limit-down
rate, and buys its extra re-seal probability at nearly 1:1 in downside.

| Depth band (main, strict) | Re-seal | Trapdoor (LD) | Re-seal ÷ trapdoor |
|---|---|---|---|
| shallow ≤ 1% — fit / holdout | 1.56% / 2.98% | 1.44% / 1.49% | 1.08 / **2.00** |
| mid 1–3% — fit / holdout | 2.99% / 3.92% | 1.44% / 1.40% | **2.08 / 2.81** |
| deep > 3% — fit / holdout | 3.67% / 3.71% | **3.49% / 2.73%** | 1.05 / 1.36 |

The mid band carries the best asymmetry in both windows; the deep band the worst. Every
limit-down figure here is **survivors-only and therefore a lower bound** on the true hazard.

**7. 龙回头 is the study's cleanest null: strong probability structure that converts to nothing.**
Two different rates are reported here and they must not be confused — an earlier draft printed
the row rate next to an episode count, which reads as an episode probability and is not one.

| Question | Denominator | Main, fit | Main, holdout | All |
|---|---|---|---|---|
| P(a pullback DAY is followed by a board ≤5 sessions) | rows (window-days) | 24.47% (n=11,127) | 24.85% (n=4,206) | 24.57% (n=15,333) |
| **P(the EPISODE re-boards ≤5 sessions of day 1)** | **episodes** | **32.37%** (n=1,560) | **40.31%** (n=645) | **34.69%** (n=2,205) |

The episode rate is the one that answers "how often does an ended ladder come back", and its
Wilson interval is **~2.6× wider** than the row interval because one episode contributes up to
ten window-days. The row rate is *not wrong* — it is the correct denominator for "should I
enter on this particular day" — but it is not a statement about episodes.

The structure is sharply conditioned (days-elapsed **33.96% → 21.84% → 16.32%** holdout,
monotone in *both* windows; close ≥ half-retrace **31.66% vs 16.16%**; no limit-down since the
run ended **32.01% vs 17.38%**). And the book that trades it loses **−1.37% (E3) / −1.45% (E1)
net per trade** on the holdout, date-clustered t **−6.87 / −9.51**. This is L1's central null
reproduced in a family that was supposed to escape it: *the information is real and the price
already contains it.*

**8. One piece of practitioner lore is contradicted; a second apparent contradiction was my
own confound and is withdrawn.** (a) **Stands** — the "3–6 day sweet spot" for 龙回头 does not
exist: the re-board hazard declines **monotonically from day 1** in both windows, so day 1–3 is
strictly the best window and day 7–10 the worst. (b) **Withdrawn.** I reported that *declining*
pullback volume is worse (holdout **22.64% vs 29.88%**). That contrast is confounded by
position in the window: the declining arm averages **5.31 rows per episode** against **2.18**
for the non-declining arm, so it is loaded with late-window days — and the hazard falls with
day. Controlling for days-band shrinks the gap, and the residual does not reproduce:

| Days band (main) | Holdout: not-declining / declining | Fit: not-declining / declining |
|---|---|---|
| 1–3 | 41.40% / 30.17% | 32.10% / 27.60% |
| 4–6 | 27.50% / 20.13% | 24.45% / 22.84% |
| 7–10 | 16.89% / 16.04% | 19.38% / 19.79% |
| **mean absolute within-band spread** | **6.48 pp** | **2.17 pp** |

A conditioner whose controlled effect is 3× larger in holdout than in fit fails this receipt's
own stability standard — the same standard that demoted break depth in §6. **Volume decline is
recorded as unstable/confounded, not as a finding.**

**9. DATE CLUSTERING IS LOAD-BEARING, AND IT IS WHAT KILLS THE LAST SURVIVOR.** These books
trade in same-day clumps: a regime cell is a market-wide daily state, and one 龙回头 episode
emits up to ten rows. Collapsing each session to its own mean before computing a standard
error — counting *sessions*, not trades — changes the verdict on every candidate:

| Cohort (main, T+1 open, E3) | n fit / holdout | dates | net fit / holdout | per-trade t | **date-clustered t** |
|---|---|---|---|---|---|
| regime = mid tercile, **tolerant** | 7,207 / 5,033 | 543 | +0.52% / +0.55% | **4.36** | **0.46** |
| regime = mid tercile, strict | 3,368 / 2,265 | 512 | +0.60% / +0.66% | 3.45 | **1.02** |
| volume-z = low tercile, strict | 2,888 / 1,323 | 652 | +0.66% / +0.61% | 2.27 | **0.73** |
| depth = shallow, strict | 1,599 / 630 | 374 | +0.23% / +0.34% | 0.92 | **1.36** |

Nine cohorts clear the net bar with n ≥ 500 in both windows *and* under date-equal weighting.
**Not one reaches a date-clustered holdout t of 1.4**, and across all 210 cohorts the maximum
is **1.86** with **zero** at t ≥ 2. The most impressive per-trade statistic in the study —
**t = 4.36**, the tolerant mid-regime cell in the first row — collapses to **0.46** once the
denominator counts sessions instead of same-day trades.

*(An earlier draft quoted "t = 3.45" as the study's largest per-trade t two lines under a table
whose first row printed 4.36. 3.45 is the strict cell's; 4.36 is the maximum.)*

The sharpest illustration is a 龙回头 cell: deep retrace × days 1–3 × hot regime, fit,
n = 1,247. Trade-weighted it returns **+4.83% net**. Date-weighted it returns **−1.22%**
(t = −2.06) — the headline was a handful of explosive sessions, not an edge. In the holdout
that same cell prints **−3.38% / −3.08%** (t = −3.60).

**10. One genuinely positive side finding, stated as ore and not as a result.** The broken-board
cohort is a *less adversely selected* place to buy the T+1 open than L1's sealed-board cohort.
L1's book is **tolerant**-basis, so the like-for-like comparison is against this study's
tolerant column — main board, T+1 open, same exits, holdout, gross:

| | E1 | E3 |
|---|---|---|
| L1 rider — sealed-board cohort (tolerant) | −0.384% | −0.209% |
| **here — broken-board cohort (tolerant)** | **−0.230%** | **−0.050%** |
| here — broken-board cohort (strict, for reference only) | −0.176% | +0.047% |

A gain of **+0.15 pp on both exits** on the matching basis. Still not clearing net, and it is a
*control* rather than this lane's construction — but it points at where the next lane should
look, and it is the one number in this receipt that improves on Wave 1. The strict row is
printed for reference and is **not** the comparison: L1 never ran a strict book, so pairing it
against L1 would be the basis-mixing this receipt otherwise refuses.

**11. What the nulls close, precisely.** They close the *break-day close entry* and the
*pullback-day close entry*, as constructed here, on daily bars, on this universe, with these
two exit rules. They do not close the weakness-entry hypothesis. The single largest untested
variable is named first in the ORE LEDGER and is about to become measurable: **intraday
re-seal timing.** A 09:40 break that re-seals at 10:05 and a 14:52 break that never recovers
are the same OHLC row, the same `close_off_limit_pct`, and the same `failed_up_seal` event in
everything above.

---

## COVERAGE RECEIPT (read before any number)

| Fact | Measured |
|---|---|
| Base SHA (this branch's point off main) | `ec81107b3167e35db497accddfc617a1e5c9361d` |
| Input-store SHA (last commit touching the data dirs) | `035914cd3dafe1c0c7fd25bbc5f51d8a0290d64e` |
| Build-time HEAD (provenance only; moves after commit) | see `meta.vintage.build_head_sha` |
| Raw OHLCV store | `data/china_stocks_raw`, **1,842** names; **1,836** kept after ST exclusion |
| Universe vintage | **PRE-EXPANSION.** A sibling Codex lane is expanding toward ~5,400 names; that is not in this checkout |
| Limit-event tape | **71,463 rows — HEALED vintage confirmed** (pre-heal is 60,428; 314 names' history would be missing) |
| Tape source | extracted from branch `claude/cn-limit-w1-dataheal` (PR #5059, unmerged). **This lane's PR carries only `research/` files** — #5059 owns that store |
| Regime dial | `board_ecology_series_v1.parquet` from `claude/cn-limit-w1-regime-salvage`, likewise not committed here |
| Window | 2011-01-01 → 2026-08-07 |
| Fit / holdout split | 2021-11-26 (v0's frozen 70/30 date). **One holdout pass.** |
| Runtime | 20.1 s |

**Collectors, engine data wiring and every Tushare surface were untouched** — a sibling lane
owns those.

### Basis labelling — the thing this receipt refuses to blur

The house tape is **STRICT**: `sealed_up` is `close >= round(prev_close*(1+w), 2)` with no
tolerance, and `failed_up_seal` is `high >= lim_up AND NOT sealed_up`. v0 adjudicated a
**TOLERANT** primary (`close >= lim_up * (1 - 0.002)`) against an independent vendor scrape
and adopted it; L1 inherited it. Both are carried here and **every table names its basis**. A
strict-population row is scored with strict outcomes and a strict 连板; a tolerant row with
tolerant outcomes. They are never averaged into one cell.

Two consequences worth stating before the tables, because both bite:

- **The tape's `lianban_count` is hardcoded to 0 on every `failed_up_seal` row.** It carries no
  information. Conditioning on it would have silently collapsed the entire prior-连板 axis
  into one cell and looked like a null. Prior N here is **panel-derived** (the streak ending
  at T−1, on the population's own basis).
- **4.48% of strict failed seals are tolerant SEALS** — they closed within 0.2% of the limit.
  The strict tape calls them breaks; v0's adjudicated rule calls them boards. They sit
  entirely inside the shallow depth band, and the concentration is what matters: they are
  **27.49% of that band**. More than a quarter of the strict shallow cohort — one of the cells
  the census surfaces in §9 — is *not a weakness cohort at all*, but boards v0's primary rule
  counts as held. Read that cell accordingly.

### Population receipt — both definitions, counted

| | Strict | Tolerant |
|---|---|---|
| `failed_up_seal` rows in the healed tape | 16,366 | — |
| Rows the panel could place | 16,355 (11 unplaceable) | — |
| Panel-detected failed seals | 16,361 | 35,901 |
| Rows unique to this basis | 732 | 20,272 |
| Overlap of the two panel populations | **15,629** | **15,629** |
| Jaccard of the two populations | **42.66%** | **42.66%** |

The two definitions agree on well under half their union. `strict_only` rows are the tolerant
basis's *seals*; `tolerant_only` rows touched the tolerant limit price but not the strict one —
a near-touch the strict tape does not record as a break at all.

**Tape ↔ panel parity.** The strict population is taken *from the tape*, but the panel detects
it independently from the same bars. Agreement is **99.963%**: 16,355 in both, **zero
tape-only**, 6 panel-only. The instrument is standing on the store it says it is.

### Lookahead check on the regime dial — two legs, only one of them mechanical

The claim is that the dial at T is known at T's close. It rests on two separate facts, and an
earlier draft called the mechanical check "decisive" when it only establishes the second:

1. **`i5[D]` is indexed by the TARGET date** — the session the continuation printed on — so it
   counts pairs whose *second* leg is D. Verified by reading the producer
   (`board_ecology_regime_v1.py` groups the pair frame by `next_bar_date` and renames that
   level to `date`), and independently confirmed in adversarial review. **This leg is a source
   read, not something this instrument can test.**
2. **`ma5` is a TRAILING mean** of that column. This one *is* mechanical: re-deriving it, max
   |Δ| vs a trailing window is **0.0** on all three boards, vs a forward window **0.47–0.80**.

The distinction matters because leg 2 cannot rescue leg 1 — if `i5` were source-indexed by the
*origin* date, a trailing `ma5` of it would still reproduce trailingly and the mechanical check
would still pass. **PASS on both legs**, for different reasons.

Terciles use **fit-window cut points only** (main 0.1648 / 0.2883; chinext 0.1667 / 0.3671), so
the bucketing carries no holdout information. STAR has too few fit rows to cut and is `reg_na`
throughout — `reg_na` is a **data-availability slice, not a regime level**, and is excluded
from best-cell reporting (see §2). The dial is a **tolerant-basis** conditioner applied to both
populations and is labelled as such wherever it appears.

**Volume-z terciles are fit per (basis, board), not pooled.** An earlier build fit them on the
two bases pooled, which double-counted the 15,629 rows they share and let the tolerant
population set the strict population's band edges — the same basis mixing this section forbids.
Correcting it moved the strict/main edges ~5% and shifted 36 volz cohorts; no other cohort,
rate or book cell changed. `vz_na` is likewise a data-availability slice (no trailing 20-session
volume window), not a tercile.

---

## PRE-REGISTRATION

Fixed by the lane brief before the first run: both populations, all conditioners and band
edges, both exit rules, the 15 bp cost bar, the n ≥ 100 census floor, and the split date.

**The decision bar.** A cohort clears only if its mean per-trade return is positive **after** a
15 bp round trip in **both** windows with n ≥ 100 in each. Anything else is a null for that
construction. *(The date-clustered standard error was added after the first run, when the
per-trade t on the leading cohort was found to be counting 4.4 same-day trades as 4.4
independent observations. It is a stricter reading of the same pre-registered bar, applied
uniformly to every cohort, and it is reported alongside the per-trade figure rather than in
place of it.)*

**Exits — L1's, copied unchanged so the two studies' return columns mean the same thing.**
E1 sells at the next open after the first held session that fails to close limit-up; E3 sells
at the open three usable sessions after the first held bar. For **both** anchors the exit walk
starts at T+1, so an open entry and a close entry differ *only* in entry price and population.

**Locked-exit honesty.** A scheduled exit bar opening at or below its limit-down price cannot
be sold; the exit rolls up to 10 sessions, then closes at the last available close and is
flagged. Roll rates and the extra loss they cost are reported per cell.

**One convention differs from L1 and it is not a return.** `hold_sessions` here is
`exit_bar − first_held + 1` — an *inclusive* count of bars held. L1 reports
`exit_bar − entry_bar`, one lower for the same trade. Exit bars and both prices are identical,
so every return, win rate and expectancy column is unaffected; but a hold-length figure from
this file needs +1 before it is compared with L1's.

### DEVIATIONS from the pre-registration

Four changes were made after the first run. Two are defect fixes that moved numbers; all are
listed here rather than folded silently into the tables.

| Change | Why | Moved a number? |
|---|---|---|
| Date-clustered SEs added beside every per-trade figure | the per-trade t was counting same-day trades as independent | No — added beside, never instead of |
| **Volume-z terciles fit per (basis, board)** instead of pooled across bases | the pooled fit double-counted the 15,629 shared rows and let the tolerant population set the strict population's edges | **Yes** — 36 volz cohorts; pre-registered invariance held (every non-volz cohort byte-identical) |
| **Paired-population gap** computed and published | the gap had been averaged over all usable rows including unfillable opens (mean +9.98%) | **Yes** — §3's causal number; the delta itself never moved |
| **Three-way collapse emits a disjoint partition**; `reg_na`/`vz_na` relabelled as data-availability slices; census inference restated per family | duplicate/non-disjoint cells inflated the cell count; a missing-data slice was being advertised as the best cell; pooled families manufactured a "below chance" artifact | **Yes** — §2, §8, §9 and the three-way counts; no cohort statistic recomputed |

**Buy-side fillability is not the mirror of sell-side fillability**, and this lane depends on
the difference. A close entry is unfillable only when the bar closes *at the limit-up*. A
limit-**down** close is trivially fillable to buy — the book is all sellers. That is why the
weakness families have entries where the rider had none.

---

## B-回封 — the failed-seal battery

### Re-seal and trapdoor, by depth (main board)

| Basis / window | Shallow ≤1% | Mid 1–3% | Deep >3% |
|---|---|---|---|
| **strict, fit** — n | 1,602 | 3,274 | 3,951 |
| re-seal | 1.56% | 2.99% | 3.67% |
| trapdoor | 1.44% | 1.44% | 3.49% |
| **strict, holdout** — n | 672 | 1,861 | 2,450 |
| re-seal | 2.98% [1.93, 4.55] | 3.92% [3.13, 4.90] | 3.71% [3.03, 4.54] |
| trapdoor | 1.49% | 1.40% | 2.73% |
| **tolerant, holdout** — n | 1,161 | 4,179 | 5,592 |
| re-seal | 6.12% | 5.93% | 7.33% |
| trapdoor | 3.70% | 3.37% | 6.35% |

Depth is not stable as a *return* or *probability* conditioner; it is stable as a **risk**
conditioner. Reference points: v0's unconditional next-bar limit-up rate is **1.27%** on main;
a held first board is **16.50%**.

### Re-seal by prior 连板 — the one probability conditioner that looks monotone

Main, strict, holdout: **N0 3.34%** (n = 4,486) · **N1 5.32%** (432) · **N2 15.56%** (45) ·
**N3+ 20.0%** (20). A broken board on a name that already owned a ladder re-seals far more
often — and its trapdoor rises with it (N1 4.86%, N2 8.89%). The two right-hand cells are
**THIN** (n = 45 and 20) and must not be read as a result; they are flagged as ore.

### The two entry books — main board

| Basis / window | Anchor · rule | n | dates | net/trade | date-eq net | date-clustered t |
|---|---|---|---|---|---|---|
| strict, fit | T+1 open · E3 | 8,816 | 2,251 | +0.596% | +0.178% | 1.56 |
| | **T close · E3** | 8,827 | 2,252 | **−0.617%** | −1.037% | **−8.74** |
| strict, holdout | T+1 open · E3 | 4,928 | 1,054 | −0.103% | +0.231% | 1.17 |
| | **T close · E3** | 4,983 | 1,054 | **−1.155%** | −0.796% | **−3.92** |
| tolerant, holdout | T+1 open · E3 | 10,798 | 1,125 | −0.200% | −0.003% | −0.02 |
| | **T close · E3** | 10,932 | 1,125 | **−1.174%** | −0.993% | **−6.52** |

### Break-day close vs next open — paired, identical trades

| Window | Rule | Δ mean (close − open) | Δ net | Δ win rate |
|---|---|---|---|---|
| fit (n = 8,816 each) | E1 | −1.217 pp | −1.216 pp | −10.44 pp |
| | E3 | −1.229 pp | −1.227 pp | −6.76 pp |
| holdout (n = 4,928 each) | E1 | −1.066 pp | −1.065 pp | −7.43 pp |
| | E3 | −1.069 pp | −1.067 pp | −5.07 pp |

**The unpaired remainder** — break days whose T+1 open was unbuyable, the only trades the close
entry can take and the open entry cannot — is **11 trades in fit and 55 in holdout**.

| Rule | Fit (n=11) | Holdout (n=55) |
|---|---|---|
| E1 | +11.209% net | +5.906% net |
| **E3** (the rule the −1.069 pp delta above uses) | +10.960% net | **+0.181% net** |

Read the **E3** row against an E3 delta. The two rules differ by 5.7 pp on the same 55 holdout
trades, so quoting E1's +5.9% beside an E3 comparison — as an earlier draft did — makes the
remainder look far more like a counterweight than it is. Either way it is ~1% of the population
and cannot offset −1.069 pp on the other 99%.

### Rolls

Main, strict, holdout: roll rate **0.61% (E1) / 0.20% (E3)**; mean extra loss when it rolls
**−1.36% / −0.20%**, worst **−11.35%**; forced-close 0.95% / 2.80%; mean hold 2.04 / 3.94
sessions. Locked exits are a smaller factor here than in L1's ladder book — a name that just
broke its board is much less likely to be limit-down-locked two days later than a name that
was riding a ladder.

---

## B-龙回头 — the proven-ladder pullback battery

**Basis: TOLERANT throughout.** The strict tape plays no part in this battery.

**Population.** 2,731 qualifying runs of N ≥ 3; 104 whose ladder-end bar was unusable; **1,227
windows (45%) truncated by a re-board** before session 10; 58 broken by a chain gap; 255 rows
with an unresolved 5-day forward window (counted as *no board*, never dropped — dropping them
would delete exactly the losers). Main: 15,333 window rows from **2,205 episodes** across 947
names. One episode emits up to ten rows, so **read the episode count, not the row count.**

### P(new limit-up close within 5 sessions) — main

**All rates in this table use ROW denominators** (window-days). They answer "should I enter on
*this day*", not "does *this episode* come back" — the episode-denominator companions are in §7
and are materially higher (34.69% overall vs 24.57%). Do not read a row rate as an episode
probability.

| Conditioner | Fit | Holdout |
|---|---|---|
| overall | 24.47% (n=11,127 rows / 1,560 ep) | 24.85% (n=4,206 rows / 645 ep) |
| days 1–3 / 4–6 / 7–10 | 29.38 / 23.53 / **19.59%** | 33.96 / 21.84 / **16.32%** |
| retrace <15 / 15–30 / >30% | 25.75 / 25.21 / 23.57% | 41.83 / 34.69 / 19.88% |
| close ≥ half-retrace: yes / no | — | **31.66% / 16.16%** |
| no limit-down since run end: yes / no | — | **32.01% / 17.38%** |
| volume declining: yes / no *(confounded — see §8)* | 23.84% / 25.30% | 22.64% / 29.88% |
| regime cold / mid / hot | 25.53 / 27.17 / 22.97% | 25.72 / 25.02 / 23.47% |

Days-elapsed is monotone in both windows. Retrace depth is **not** — flat in fit, strong in
holdout — so its holdout spread is an era effect, not a stable conditioner. Run length does
nothing (holdout N=3 25.33% → N=6 22.52%). The volume-declining row is retained for the record
but is confounded by position in the window and is **withdrawn as a finding** (§8).

### The book — every cell negative

Main, holdout: **E1 −1.454% net** (date-clustered t −9.51) · **E3 −1.367% net** (t −6.87), over
4,195 trades from 639 episodes. Fit is the same story (−1.155% / −0.787%). No retrace band, no
days band, no regime tercile rescues it. Rolls are ~3× the 回封 book's — **1.76% (E1) / 0.79%
(E3)**, mean extra loss −1.39% / −2.14%, worst **−16.24% / −23.16%** — exactly what a book that
holds falling names should look like.

### The best cell, honestly framed

The fit's strongest three-way cell is **deep retrace × days 1–3 × hot regime**, n = 1,247,
trade-weighted **+4.833% net**. Date-weighted it is **−1.22%** (t = −2.06) across 273 sessions:
the headline came from a few explosive days, not from an edge. In the holdout the same cell
prints **−3.384% trade-weighted / −3.077% date-weighted** (t = −3.60). The holdout's own top
cells are n = 26 and n = 29.

**Counting the three-way table.** The holdout partition holds **24 disjoint cells, of which 5
are positive** (fit: 27 cells, 6 positive). Three thin holdout cells were absorbed by **2**
parents. An earlier build reported "27 cells, 5 positive" for the holdout by printing each thin
cell under its own label *carrying its parent's numbers* — which emitted byte-identical rows for
two different regime cells and listed a parent alongside siblings it contained. The partition is
now disjoint and is the only thing counted; absorbed cells appear as pointers, and their
carrying parents once each, in `collapsed_into_parents`. Cells and parents must never be summed
together — a parent's rows overlap its printed siblings'.

---

## THE DECISION CENSUS

| | Count |
|---|---|
| Cohorts tested (n ≥ 100 in both windows) | 210 |
| Positive **gross** in both windows | 30 |
| Positive **net** in both windows | **24** |
| …excluding missing-data slices (`reg_na` / `vz_na`) | **23** |
| Positive net in both under **date-equal weighting** | 42 |
| …of the 24, with n ≥ 500 in both | 15 |
| …also clearing date-equal weighting, excl. missing-data slices | **9** |
| **…reaching a date-clustered holdout t ≥ 2** | **0** |
| **Max date-clustered holdout t, all 210 cohorts** | **1.86** |
| 回封 **T-close** cohorts clearing | **1 of 84** (fit mean +0.023%) |
| 龙回头 cohorts clearing | **0 of 42** |

**Read this per family, never pooled** (§1). The three families have drifts of +0.124%,
−0.959% and −1.104% per trade, so a single coin-flip benchmark does not describe them: only the
T+1-open family is near enough to zero for the ~25% two-window sign-test expectation to mean
anything, and there it predicts 21 against 23 observed — *at* the null, not below it. The
close-anchored families are far enough from zero that they throw essentially no chance
survivors, so their counts read at face value. The cohorts are also heavily overlapping slices
of the same trades and are not independent tests.

**The verdict rests on the last two rows, not on the counts above them.** Zero cohorts of 210
reach a date-clustered holdout t of 2, and the maximum anywhere is 1.86.

---

## WHAT THIS DOES NOT ESTABLISH

- **It does not establish that weakness entries do not work.** It establishes that *these two
  constructions*, on daily bars, on this universe, with these two exit rules and this cost
  bar, do not. The ORE LEDGER below is the list of what remains.
- **It does not establish that the 回封 probability structure is absent.** It is present and it
  is measurable — prior 连板 in particular looks monotone. It does not convert to expectancy at
  the entry points daily data offers.
- **It does not establish a market-wide statistic.** The universe is a curated 1,842 names and
  the 打板 game lives disproportionately in the small-cap and ST names it omits.
- **It does not establish the true downside.** The store is survivors-only. Every limit-down
  rate is a lower bound, and 龙回头 is biased harder than 回封: a ladder that ended in the
  name's terminal decline and delisting is absent from the population *entirely*, not merely
  under-counted in a tail. Every pullback-recovery rate above is an **upper bound**.
- **It does not price capacity, portfolio construction or the correlated-exit tail.** Every
  number is a per-trade or per-session mean over overlapping episodes.
- **It does not settle the strict-vs-tolerant question.** It reports both and refuses to mix
  them. Where they disagree — and they disagree on more than half their union — that is a
  measurement, not a resolution.

---

## ORE LEDGER — untested variants

**THE ORE LAW: a null closes the construction tested, never the hypothesis. "Not found yet" is
not "does not exist."**

| Variant | Blocked by | Why it matters |
|---|---|---|
| **Intraday re-seal timing** — a 09:40 break that re-seals at 10:05 vs a 14:52 break that never recovers | daily bars: both print the same OHLC row, the same `close_off_limit_pct`, the same event | **The single largest unmodelled variable in this receipt**, and the conditioner practitioners actually use. The operator has just purchased 历史分钟; when it lands, the first re-run should split every break-day cell by first-touch time, break count and time-to-re-seal. Nothing here constrains what that will show. |
| **Seal-wall size** (封单量 / `seal_fund_yi`) | 36-date window (2026-06-15 forward), no history | §2.3's deliberate-washout hypothesis predicts a *non-monotone* relation between break quality and next-day strength. Depth and volume-z are lossy shadows of the wall. Untested, not refuted. |
| **Theme / 题材 relay context** — leader vs follower vs last laggard | not run; `members.parquet` is current industry membership, and industry ≠ 题材 | A leader's break and a follower's break are different events wearing one label in every table above. |
| **N-specific and band-specific exit tuning** | deliberately not run — identical rules per cohort keeps the comparison like-for-like | A weakness entry's natural exit is not a ladder-rider's exit. Obvious improvement, obvious overfit; needs its own holdout. |
| **Stop-loss families** (fixed %, ATR, trailing, close-based, intraday) | intraday stops unmeasurable on daily bars; none pre-registered | The p10 and worst columns show where a stop would bind and the trapdoor table shows the hazard it would cut. Two rules is not the exit space. |
| **Half-retrace alternatives** — retrace of the last board only, MA-anchored pullbacks, close-vs-first-board-open | one measure pre-registered; testing several and reporting the best is the overfit this instrument avoids | The run-height denominator is one choice among many and the 15%/30% edges are lore, not measurement. |
| **Post-expansion re-run** on the ~5,400-name universe | expansion in flight in a sibling Codex lane | The omission points at exactly the small-caps most likely to carry the effect. |
| **ST (5% band) and delisted universes** | ST dropped wholesale (one asof, no membership history); delisted names absent | Biases the trapdoor and the 龙回头 recovery rate in the same direction: the tape cannot show a pullback that never recovered because the name stopped existing. |
| **The near-miss cohort as matched control** (closed high, never touched the limit) | blinded map C12; not this lane's population | Without it the 回封 rate has no counterfactual — the right question is whether a *broken* board predicts better than a matched name that simply closed strong. |
| **Position sizing and the correlated-exit tail** | no portfolio formed, no capacity estimated | §2.10: these books are structurally short a liquidity option, and per-trade expectancy does not price it. |

---

## REPRODUCE

```bash
TZ=UTC python3 research/cn_prophet_audit/weakness_entry_battery_v1.py
```

Requires the **healed** `data/china_microstructure/limit_events.parquet` (71,463 rows, PR
#5059). While #5059 is unmerged the instrument falls back to `.w2scratch/` copies extracted
from `claude/cn-limit-w1-dataheal` and `claude/cn-limit-w1-regime-salvage`; it prints the
vintage it actually loaded into `meta.tape.vintage`. **Check that field reads
`HEALED (PR #5059)` before reading any number** — on the pre-heal store 314 names' history is
missing.

**Determinism.** Verified by running twice and comparing payloads: byte-identical apart from
`generated_utc` and `runtime_sec`. The vintage block deliberately records `base_sha` (the
branch point) and `data_store_sha` (the last commit touching the input stores) rather than
build-time HEAD alone — an artifact that pins its own build HEAD can never reproduce by
equality once it is committed, because committing moves HEAD. `build_head_sha` is carried for
provenance and *is* expected to differ on any re-run after commit.
