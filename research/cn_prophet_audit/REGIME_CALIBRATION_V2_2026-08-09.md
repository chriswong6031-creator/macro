# CN REGIME-CONDITIONAL CALIBRATION v2 — does the regime dial close the onset model's gap?

**Program:** CN LIMIT-MOVE ALPHA, Wave 2 / lane W2-A (the regime × calibration merge).
**Merges:** `onset_calibration_v1.py` (Wave 1 / L3, PR #5055) × `board_ecology_series_v1.parquet`
(Wave 1 / L2, PR #5078) ·
**Instrument:** `research/cn_prophet_audit/regime_calibration_v2.py` ·
**Frozen numbers:** `REGIME_CALIBRATION_V2_2026-08-09.json` ·
**Runtime:** ~39s · **Window:** 2011-01-04 → 2026-08-07 · **Basis:** `data/china_stocks_raw` (nominal OHLCV).

**Tier: display / audit. MEASUREMENT ONLY.** Nothing here ranks for size, gates, admits, promotes,
or reaches a live surface. No LLM is involved at any point. **No number is pooled across board
types.** The holdout was scored exactly once; nothing was refit, retuned, re-split or re-bucketed
after seeing it.

---

## DECISION SUMMARY

**1. Does regime conditioning clear the bar? PARTLY — and NOT by the route the lane was built to
test.** The pre-registered bar is a positive holdout Brier skill against the 连板 ladder B0.

| Board | B1 (L3's model) | **R0 regime ladder** | R1 +covariate | **R2 regime-conditioned calibration** | R3 both |
|---|---|---|---|---|---|
| main | −0.167% | **+0.061%** ✅ | −0.165% | **−0.173%** ❌ | −0.171% ❌ |
| chinext | −11.686% | **−0.026%** ❌ (dead heat) | −12.498% | **−13.458%** ❌ | −13.470% ❌ |
| star | THIN-SKIP | THIN-SKIP | THIN-SKIP | THIN-SKIP | THIN-SKIP |

**R2 — the causal fix this lane exists to test — FAILED on both boards, and made B1 slightly
worse.** What cleared the bar on main is **R0, the (连板 N × regime) lookup table**: the ladder,
re-quoted for today's continuation temperature. That is the second time in this program a hand-built
lookup table has beaten the parametric machinery (L3's §7, B2 over B1).

**2. WHICH MODEL SHIPS.**

| Board | **Shippable object** | Why |
|---|---|---|
| **main** | **R0 — the 15-cell regime ladder** | The only Wave-2 object that clears the bar. Keeps the ladder's calibration (ECE 0.095pp vs B0's 0.069pp; B1 is 0.214pp), adds resolution (0.4959 vs B0's 0.4850) and cross-date AUC (0.602 vs 0.592), under-quotes rather than over-quotes (P̂/realized **0.943**), and fits on one sheet of paper. |
| **chinext** | **B0 — the plain ladder, unchanged** | Nothing beats it. R0 ties it (−0.026%, and ±0.06% year to year) and buys AUC 0.563 vs 0.540, but the Brier evidence does not require replacing the ladder. B1/R1/R2/R3 over-quote by **2.58×–2.77×** and are not quotable as probabilities at all. |
| **star** | **nothing** | THIN-SKIP, printed below with its counts. |

**A caveat that must travel with the main-board verdict:** R0's +0.061% is a real win and a *small*
one. It is positive in **4 of 6** holdout years (2021 −0.294, 2025 −0.094 are the misses). Nobody
should read 0.061% of Brier as a large effect; what R0 actually buys is **honesty of level**, not
skill.

**3. R0 is not the program's best Brier object, and this receipt will not pretend otherwise.**
L3's own `P2` (f3 + N dummies) and `B2` (f3×f6×N lookup) were re-derived here **unchanged** on the
identical holdout, purely so the ranking is stated correctly:

| main, by holdout Brier skill vs B0 | skill | AUC | P̂/realized | ECE | Murphy resolution |
|---|---|---|---|---|---|
| **P2** (L3) | **+0.707%** | 0.689 | **1.189** ⚠ | **0.267pp** ⚠ | **0.5708** |
| **B2** (L3) | +0.320% | 0.743 | 0.899 | 0.130pp | 0.5479 |
| **R0** (this lane) | +0.061% | 0.602 | **0.943** | **0.095pp** | 0.4959 |
| B0 | 0.000% | 0.592 | 0.963 | 0.069pp | 0.4850 |
| B1 / R1 / R3 / R2 | −0.167 / −0.165 / −0.171 / −0.173% | 0.775 / 0.775 / 0.771 / 0.770 | 1.06–1.08 | 0.19–0.21pp | 0.479–0.502 |

P2 wins the pre-registered metric and is the **best ranker with a number attached**, but it
over-quotes by 19% and posts the worst ECE of the credible set — **rank with it, do not quote it.**
R0 is the best-calibrated object that still beats the ladder. Two different jobs; the receipt names
both rather than collapsing them.

**4. WHY R2 FAILED — measured, in one table, and it is a precondition failure, not a tuning miss.**
A per-stratum calibration map can only repair a level error if the dial orders the outcome **the
same way in the calibration slice as in the holdout**. On main it does not:

| main, base rate by regime stratum | T1_cold | T2_mid | T3_hot | direction |
|---|---|---|---|---|
| fit CORE (2011-01-04 → 2020-04-08) | 0.709% | 1.109% | 1.399% | **MONOTONE POSITIVE**, 1.975× |
| **fit CALIBRATION (2020-04-09 → 2021-11-25)** | **1.796%** | **1.529%** | **1.388%** | **MONOTONE INVERTED**, 0.773× |
| holdout (2021-11-26 →) | 1.032% | 1.217% | 1.610% | **MONOTONE POSITIVE**, 1.560× |

The dial points the right way in the fit core and in the holdout, and **backwards in exactly the
397-date window L3's isotonic map is fitted on.** R2 therefore learns "cold days are hot" and
applies it to a holdout where cold days are cold: its over-prediction on cold rows worsens from
1.111× to **1.271×** and its under-prediction on hot rows deepens from 0.915× to **0.823×**. The
Murphy RELIABILITY term nearly doubles, 0.0241 → **0.0442**. `r2_precondition.precondition_met` is
`false` on both boards, and it is computed, not asserted.

**5. Did R2 fix ChiNext's named 2.58× over-prediction? NO — it made it worse, for a different and
equally measured reason.**

| ChiNext over-prediction (P̂ ÷ realized) | B1 | R1 | **R2** | R3 | **R0** | B0 |
|---|---|---|---|---|---|---|
| whole holdout | 2.577× | 2.635× | **2.772×** | 2.651× | **1.118×** | 0.942× |
| head of book (top decile) | 5.221× | 5.536× | **5.452×** | 5.630× | **1.427×** | 1.343× |
| top reliability bin | 8.586% → 1.535% | — | 8.983% → 1.532% | — | 47.50% → 28.57% | 47.50% → 28.57% |

**The named defect is fixed by R0, not by R2.** The reason R2 could not fix it is a **coverage
degeneracy that is printed rather than papered over**: ChiNext's dial has a point mass at zero, so a
quantile cut cannot separate it. Of the board's 1,007 wide-era fit sessions, **54.6% print no
continuation rate at all** and a further **25.1% print exactly 0.0** — so the tercile's lowest edge
*lands on zero*, the bottom stratum comes out **empty**, and the collapse ladder's halves do the
same. Measured occupancy: `H1_cold 0.0%`, `H2_hot 100.0%` → `dial_is_degenerate: true`. The only
contrast ChiNext actually supplies is **printed-a-rate vs no-pairs**, and the surviving stratum's
"hot" label is a naming artifact. Worse, that surviving stratum's calibration slice runs at
**1.059%** against the pooled slice's 0.735% — *hotter still* — so conditioning enlarged the level
error by construction. The no-print stratum carried 33 calibration positives against the
pre-registered floor of 50 and fell back to the pooled map, so **R2 ≡ B1 on those rows by design**
(both 2.309×, confirmed in `by_stratum`).

**6. THE FINDING THAT MATTERS MOST — the dial is a LEVEL instrument, never a RANKER, and this is
structural.** `i5` is a board-level daily value: it is **constant across every name on a given
date**, so it cannot re-order a daily book. The measurement is the proof — R0's within-date top-K
selection is **identical to B0's at every K** (main: 16.846% / 11.154% / 5.494% at K=10/20/50, to
four decimals), while its cross-date AUC is *higher* (0.602 vs 0.592). A desk uses this dial to
decide **how much to trust today's book**, never **which names to pick**. Any Wave-3 lane that
expects a market-level regime series to improve a daily ranking is expecting something the object
cannot do.

**7. Where the regime information actually lives — the holdout ladder × regime cross-tab.** This is
descriptive (nothing is fitted from it) and it explains every result above:

| main holdout | rows | share | T1_cold | T2_mid | T3_hot | top/bottom |
|---|---|---|---|---|---|---|
| **N=0** | 1,267,878 | **98.79%** | 0.888% | 0.9997% | 1.175% | **1.323×** monotone |
| **N=1** | 12,506 | 0.97% | 13.32% | 14.68% | 22.24% | **1.670×** monotone |
| N=2 | 1,957 | 0.15% | 30.54% | 27.73% | 30.15% | 0.987× non-monotone |
| N=3+ | 1,035 | 0.08% | 43.38% | 46.08% | 46.27% | 1.067× monotone |

The dial is real on the N=0 bulk (Wilson intervals disjoint: [0.862, 0.915] vs [1.126, 1.225]) and
**strongest on the first rung**, which is exactly where L2 measured it (their M1 conditioned on
first boards and got 2.121× on quintiles; this is 1.670× on terciles — the same object, coarser
cut). It is flat-to-noise on N≥2.

**8. …and why a covariate cannot harvest it. R1's regime coefficient is +0.0007.** Standardised,
fitted on the fit core, on the main board:

| main R1 coefficient | value |
|---|---|
| `i5_ma5_z` (the regime dial) | **+0.0007** |
| `i5_is_null` (no continuation print) | −0.784 |
| `N_is_1` / `N_is_2` / `N_is_3plus` | +2.117 / +3.507 / +3.585 |

Every other coefficient moves by ≤0.001 from B1's. The dial contributes **nothing as a linear main
effect** — because in the *fit* window the N=0 relationship is non-monotone (0.766% / 1.027% /
1.001%, peak in the middle), so a straight line through it is flat. R0 escapes this because a cell
table **is an interaction**: it can encode "cold is lower" without committing to "hotter is
monotonically higher". That is the whole reason the lookup table clears the bar and the logistic
does not. The missing-print indicator, by contrast, is large and real (−0.784), which is the
coefficient-level echo of §5's coverage finding.

**9. The isotonic head-tie DOES partially unlock — and the head gets worse-calibrated for it.**
L3 §12 flagged the published book saturating at the map's last block (six live names all at 27.03%).

| main head of book | B1 | R2 | R3 |
|---|---|---|---|
| distinct P̂ values in the top decile | 94 | **176** | **228** |
| rows tied at the maximum | 2,232 | **631** | 631 |
| maximum P̂ | 27.03% | **34.93%** | 34.93% |
| realized at that maximum tie | 24.96% | 28.21% | 28.21% |

The ceiling lifts and the tie shrinks by 72% — the unlock is real. But the top tie moves from a
1.083× over-quote to a **1.238×** one, so the vocabulary was bought with accuracy. On ChiNext there
is no unlock at all (11 rows tied at 37.5% before and after).

**10. ECE and Murphy-reliability move in OPPOSITE directions for R2 on main, and Murphy is the one
to believe.** R2's ECE *improves* (0.214pp → 0.195pp) and its bins-inside-Wilson go 0/9 → 1/10,
while its Murphy RELIABILITY *worsens* 0.0241 → 0.0442. They disagree because ECE bins on ten
deciles of P̂ while Murphy groups on **distinct predicted values** — and R2's three maps roughly
double its prediction vocabulary, so miscalibration that is visible at the fine grain averages out
at the coarse one. Murphy is the term that exactly decomposes the Brier score being judged
(identity residual 0.0), so it is the one that governs. **A reliability metric whose binning
changes when the model's vocabulary changes is not a fixed yardstick.**

**11. STAR: re-split as authorised, and it is STILL a THIN-SKIP.** L3 printed STAR as a THIN-SKIP
under v0's global date split (40 fit-core positives against a floor of 150) and refused to re-split
after watching the gate fail. The re-split was authorised **before** this lane's first run and
applied to STAR alone:

| STAR | L3 global split | **v2 listing-era split** | floor |
|---|---|---|---|
| fit dates / holdout dates | 565 / 1,135 | **1,190 / 510** | — |
| fit-core positives | 40 | **137** | 150 ❌ |
| fit-calibration positives | — | **36** | 50 ❌ |
| holdout positives | 612 | 497 | 100 ✅ |

The re-split moved fit-core positives **3.4×** and still misses both fit-side floors. Printed as a
measured null; the floor was **not** lowered to admit it. Worth recording for Wave 3: STAR's
calibration slice runs at **0.223×** its holdout base rate — the same defect as main and ChiNext,
inverted, and 4.5× in magnitude.

**12. Everything composes with L3 — 6 of 6 parity checks exact, on both boards.** This lane calls
L3's own code rather than re-implementing it, and gates that the numbers did not drift: main
holdout rows **1,283,376**, base **1.204%**, B1 skill **−0.17%**, B1 AUC **0.775**, B0 AUC
**0.592**, B1 top-20 realized **12.317%** — all exact. ChiNext: rows **135,753**, base **0.357%**,
skill **−11.69%**, AUC **0.726 / 0.540**, B1 P̂/realized **2.58×** — all exact.

**13. Top-20 realized rate vs L3's 12.317% (main).** B1 12.317% (unchanged, as it must be) · R1
12.339% · R2 12.203% · R3 12.198% · **R0 11.154% (= B0 exactly, per §6)**. No Wave-2 model
meaningfully moves the head of the daily book, which is the same statement as §6 from the desk's
side.

**14. LOOKAHEAD: PASS, gated three ways.** `i5` at T is computable at T's close by construction; the
audit measures it rather than arguing it. G1 join alignment 177/177 sessions exact. G3 backward
window 600/600 sessions exact. **G4 independent recompute — 6,612 of 6,612 (board, date) keys match
the committed parquet to 0.0 absolute difference on both the rate and the pair count**, from a panel
built by L3's detector rather than L2's. G2 (does the test have power?) is disclosed **per board**:
main 98.31%, star 27.12%, chinext **8.47%** — the sparse boards repeat their own value too often for
a one-session shift to be visible to G1 *there*, which is precisely why G3 and G4 exist.

---

## COVERAGE RECEIPT (read before any number)

| Fact | Measured |
|---|---|
| Price basis | `data/china_stocks_raw` — nominal/unadjusted. The adjusted twin would fabricate limit misses. |
| **STORE VINTAGE — BINDING** | **1,842 files · 1,836 kept · 1 skipped ST · checkout HEAD `e4b075f2cc7ed048f2c4325f6a49acf7b2a6a46e` · last bar 2026-08-07.** **THIS RUN PREDATES THE UNIVERSE EXPANSION.** A sibling lane is growing the store toward ~5,400 names. Every probability, stratum edge and regime print here is calibrated ON and FOR the pre-expansion curated slice. A post-expansion re-run is **not a refinement of these numbers — it is a different universe**, and the two receipts must be compared as such. ORE LEDGER row 6. |
| Boards | main 1,243 · chinext 351 · star 242 · bse 0 |
| Panel | 4,981,168 ticker-days · 4,843,576 live after exclusions · limit-up events main 50,421 / chinext 8,999 / star 878 |
| Complete-case coverage | 4,406,515 of 4,821,371 usable rows = **91.4%**. Dominant single cause `f4_sector_heat` (305,372) — a universe property, not a random one. Complete-case, **not imputed** (L3's decision, inherited). |
| **Regime series coverage** | **main 3,775 / 3,786 sessions = 99.71%** · chinext 2,524 / 3,786 = **66.67%** · star 346 / 1,705 = **20.29%**. Taken as committed from L2's parquet; **not recomputed** — recomputing would silently fork the definition under test. |
| **ChiNext dial degeneracy** | 1,007 wide-era fit sessions: **54.6% no print · 25.1% exactly 0.0** → the quantile edge lands on the point mass → occupancy `H1_cold 0.0% / H2_hot 100.0%`, `dial_is_degenerate: true`. Every ChiNext regime result is a **coverage null**, not a measurement of the dial. |
| Curated-universe caveat | Inherited unchanged and it binds **harder** on a market-level dial than on a per-name feature: L2 measured a **median 2.748× undercount** against the vendor limit-up pool, with only 514 of 1,770 (29%) of pool names present here. `i5` is a *rate*, so it is less exposed than a count — but it is still a rate measured inside the slice we hold. |
| Survivorship | The store holds the CURRENT listed universe; delisted names are absent. Stated, not patched. |
| Clustering | Limit-ups cluster hard in time and cross-section. **Every Wilson interval printed here is UNDERSTATED.** Read `dates`, not only `n`. |
| Determinism | TZ=UTC pinned at import · ticker-sorted file walk · no sampling anywhere · ties broken by ticker ascending. **Two consecutive runs verified byte-identical** modulo `generated_utc` / `runtime_sec` / `checkout_head_sha`. |
| Runtime | ~39s (budget: ≤10 min). |

---

## PRE-REGISTRATION (written before the first holdout pass)

Reproduced from `preregistration.written_before_the_first_holdout_pass` in the JSON:

1. The regime variable is **`i5_realized_continuation_ma5` and nothing else** — L2 measured it as the
   only era-neutral dial in the family (holdout 2.121×, rho 1.0, 12/16 years), and measured that the
   raw breadth counts **invert within-year** (i1 era-neutral 0.724, 12/16 years the wrong way), so
   **no absolute 涨停家数 count is admitted here as a conditioner.**
2. The split is **L3's, frozen and unchanged**, for main and chinext (main 2011-01-04→2021-11-25 fit /
   2021-11-26→ holdout; chinext inside the ±20% era only, 2020-08-24→2024-10-24 fit / 2024-10-25→).
3. **STAR gets its own listing-era 70/30 re-split** (L3 ORE row #3, authorised); if it still misses
   the THIN gate it is printed THIN-SKIP again. Applied to STAR **alone** — main and chinext keep
   L3's boundaries, gated by asserting `make_splits` returns them identically.
4. The dial is joined on the **feature bar T**, per the board's **own** series; a four-gate lookahead
   audit runs and prints **before any model is fitted**.
5. Strata are **terciles** of the dial over the board's **own fit-window sessions** (quantiled on
   dates, L2's convention, never on rows), plus an **UNKNOWN** stratum for sessions with no
   continuation print. If any tercile carries fewer than **50** positives in the fit-calibration
   slice → **collapse to halves** and print it. A stratum still under the floor → **pooled-map
   fallback**, printed. All decisions from fit-side counts only.
6. **R0 is fitted on the WHOLE fit window, exactly as B0 is**, so the new benchmark is never
   handicapped against the models it judges.
7. **R2 reuses B1's logistic UNCHANGED** — only the calibration step differs, so any difference is
   attributable to calibration and to nothing else.
8. Rows with no regime print are kept via a **missing indicator, NOT dropped**, so the holdout row set
   stays byte-identical to L3's and the receipts compose.
9. Metrics are **L3's, imported**: Brier ×1000, Brier skill, exact Murphy decomposition, log-loss
   skill, AUC, 10-bin reliability with Wilson intervals, per-year skill, top-K realized/capture/mean P̂.
10. **ONE evaluation pass** on the holdout; no refit, no retune, no re-bucketing, no second look.

**Reported-only additions, disclosed:** `B2` and `P2` are L3's own published models, re-derived
**unchanged**. L3 measured them at +0.32% and +0.71% on this exact holdout, so a Wave-2 receipt that
omitted them would present R0's win as the program's best when it is not. **No Wave-2 model was
refitted, retuned or reselected in response to them, and nothing here was built on top of them.**
The `ladder_x_regime` cross-tab (§7) is likewise descriptive — the pre-registered ladder crossed with
the pre-registered strata on the pre-registered holdout, computed inside the same single pass.

**Frozen parameters:** `N_STRATA=3` · `MIN_STRATUM_CALIB_POS=50` (L3's `MIN_CALIB_POS`, not a new
number) · `TOP_FRACTION=0.10` · winsorisation quantiles (0.01, 0.99) and standardisation moments
from the **fit core only** · THIN floors, N bucketing, isotonic and Wilson conventions all L3's.

---

## LOOKAHEAD AUDIT (STAGE 0) — mandatory, four gates

`i5_realized_continuation` at date *d* is `k/n` over pairs whose **next usable bar is *d*** and whose
prior bar was a limit-up close. Every input bar is at or before *d*, so the value is on the tape at
*d*'s close. `_ma5` is `.rolling(5, min_periods=3).mean()` on the board's own session index —
backward-looking and inclusive of *d*. That is the argument; below is the evidence.

| Gate | What it pins | Result |
|---|---|---|
| **G1 join alignment** | the joined value equals the series value at the row's OWN feature date T | **177 / 177 sessions exact** |
| **G2 power** | i5(T) ≠ i5(T+1) often enough that a T+1 join would be visible to G1 | **main 98.31%** · star 27.12% · **chinext 8.47%** — read per board |
| **G3 backward window** | ma5(T) = mean of the series' own i5 over the ≤5 sessions **ending** at T | **600 / 600 sessions exact** |
| **G4 independent recompute** | i5(T) rebuilt from THIS lane's panel (L3's detector) matches L2's committed parquet | **6,612 / 6,612 keys, max abs diff 0.0 on rate AND pair count** |

Worked example (main, 2026-08-05): series `i5_ma5` at T = **0.209127**, at T+1 = 0.200946, value
joined onto the panel rows = **0.209127**. The joined value is T's, not T+1's.

**G2's honest reading:** the pooled 44.63% understates the test's power where it matters and
overstates it on the sparse boards. main's dial moves nearly every session, so G1 is a strong test
there. ChiNext and STAR print long runs of the same value (frequently 0.0) because their boards go
days with no continuation pairs at all, so a one-session shift would often be invisible to G1 *on
those boards*. **G3 and G4 do not share that weakness** — G3 pins the window's direction
arithmetically and G4 re-derives the series from an independent panel — which is why the alignment is
gated three ways rather than one.

---

## SPLITS (frozen)

| Board | rule | era start | fit core | fit calibration | holdout | fit / holdout dates |
|---|---|---|---|---|---|---|
| main | global 70/30 (v0's) | 2011-01-04 | 2011-01-04 → 2020-04-08 | 2020-04-09 → 2021-11-25 | 2021-11-26 → 2026-08-06 | 2,646 / 1,135 |
| chinext | ±20% band era, re-split inside it | 2020-08-24 | 2020-08-24 → 2024-03-07 | 2024-03-08 → 2024-10-24 | 2024-10-25 → 2026-08-06 | 1,007 / 433 |
| star | **listing era, re-split inside it (v2)** | 2019-07-29 | 2019-07-29 → 2023-09-24 | 2023-09-25 → 2024-06-30 | 2024-07-01 → 2026-08-06 | 1,190 / 510 |

**The defect this lane exists to fix, per board** — `calib ÷ holdout` base rate:

| Board | fit-core base | **calibration-slice base** | holdout base | **calib ÷ holdout** |
|---|---|---|---|---|
| main | 1.073% | **1.563%** | 1.204% | **1.298×** |
| chinext | 0.254% | **0.735%** | 0.357% | **2.057×** |
| star | 0.171% | 0.110% | 0.492% | **0.223×** |

---

## HOLDOUT — MAIN BOARD (1,283,376 rows · 15,455 positives · base 1.2042% · 1,135 dates)

| Model | Brier ×1000 | **skill vs B0** | **skill vs R0** | log-loss skill | AUC | mean P̂ | P̂/realized | ECE | bins in CI | Murphy reliability | Murphy resolution |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 ladder | 11.42323 | 0.000% | −0.061% | 0.000% | 0.5921 | 1.160% | 0.963 | 0.069pp | 2/4 | **0.0108** | 0.4850 |
| B1 (L3) | 11.44234 | −0.167% | −0.228% | +4.614% | **0.7753** | 1.271% | 1.056 | 0.214pp | 0/9 | 0.0241 | 0.4792 |
| B2 (L3, reported) | 11.38664 | +0.320% | +0.260% | +3.495% | 0.7426 | 1.083% | 0.899 | 0.130pp | 5/10 | 0.0371 | 0.5479 |
| P2 (L3, reported) | **11.34245** | **+0.707%** | **+0.647%** | +2.657% | 0.6886 | 1.432% | 1.189 | 0.267pp | 0/3 | 0.0158 | **0.5708** |
| **R0 regime ladder** | 11.41627 | **+0.061%** | 0.000% | +0.037% | 0.6018 | 1.135% | **0.943** | **0.095pp** | 0/3 | **0.0147** | 0.4959 |
| R1 +covariate | 11.44206 | −0.165% | −0.226% | +4.616% | 0.7754 | 1.271% | 1.055 | 0.214pp | 1/9 | 0.0249 | 0.4802 |
| **R2 regime calibration** | 11.44295 | **−0.173%** | −0.234% | +4.253% | 0.7704 | 1.305% | 1.084 | 0.195pp | 1/10 | **0.0442** | 0.4987 |
| R3 both | 11.44272 | −0.171% | −0.232% | +4.260% | 0.7706 | 1.305% | 1.084 | 0.195pp | 1/10 | 0.0470 | 0.5017 |

Murphy UNCERTAINTY = 11.8974 ×1000 for every model (it is the holdout's own base-rate variance);
identity residual 0.0 everywhere.

### R0's cells — the shippable object, in full (fit-window rates, main)

| 连板 N | T1_cold | T2_mid | T3_hot | UNKNOWN | rows (fit) |
|---|---|---|---|---|---|
| **0** | 0.766% | 1.027% | 1.001% | 0.294% | 2,217,250 (98.8%) |
| **1** | 11.21% | 12.90% | **19.57%** | 3.85% | 21,570 |
| **2** | 27.59% | 31.08% | **43.52%** | (thin, n=1) | 3,385 |
| **3+** | 48.48% | 49.38% | 43.52% | — | 2,206 |

15 realized cells (N=3+ × UNKNOWN never occurs); one is THIN (N=2 × UNKNOWN, n=1) and falls back to
that N's marginal — i.e. to B0. **R0 degrades toward the old benchmark, never toward noise.**
Fit window: 2,244,411 rows / 26,157 positives.

### Reliability — R0 (3 realized bins; its 16 distinct values collapse under quantile binning)

| bin | n | k | mean P̂ | realized | Wilson 95% | in CI |
|---|---|---|---|---|---|---|
| 1 | 657,507 | 6,361 | 0.831% | 0.967% | 0.944–0.991 | no |
| 2 | 610,371 | 6,102 | 1.027% | 1.000% | 0.975–1.025 | no |
| 3 | 15,498 | 2,992 | 18.325% | **19.306%** | 18.692–19.935 | no |

R0's misses are **under**-quotes of 0.14pp and 0.98pp — the direction a desk can live with. Compare
B1, whose nine bins run 0.302→0.205, 0.460→0.298, 0.659→0.457, 0.881→0.646, 1.101→0.898,
1.220→1.089, 1.514→1.361, 1.851→1.928, 4.560→5.224: **over**-quoting the whole bottom and
**under**-quoting the top — a slope error, 0/9 inside CI, exactly as L3 §5 measured.

### Per-year Brier skill vs B0 — main

| year | n | base | B1 | B2 | P2 | **R0** | R2 | R3 |
|---|---|---|---|---|---|---|---|---|
| 2021 | 28,530 | 1.546% | −1.036 | +0.402 | +0.258 | **−0.294** | −1.127 | −1.099 |
| 2022 | 268,910 | 1.164% | −0.792 | −0.213 | +0.136 | **+0.034** | −0.819 | −0.813 |
| 2023 | 271,381 | 0.675% | +0.241 | +0.495 | +0.489 | **+0.101** | +0.049 | +0.044 |
| 2024 | 272,674 | 1.291% | −0.390 | +0.539 | +1.060 | **+0.108** | −0.273 | −0.277 |
| 2025 | 277,913 | 1.225% | −0.077 | +0.395 | +0.681 | **−0.094** | −0.121 | −0.114 |
| 2026 | 163,968 | 1.908% | +0.477 | +0.417 | +1.112 | **+0.229** | +0.523 | +0.524 |
| **years positive** | | | **2/6** | **5/6** | **6/6** | **4/6** | **2/6** | **2/6** |

P2 is positive in **all six** years; R0 in four. R2/R3 are positive in the same two years B1 is —
further evidence that the calibration change moved nothing structural.

### Top-K daily book — main, 1,135 holdout dates

| ranker | K=10 realized | K=20 realized | K=50 realized | K=50 capture | K=20 mean P̂ | K=20 P̂/realized |
|---|---|---|---|---|---|---|
| B0 | 16.846% | 11.154% | 5.494% | 20.18% | 12.058% | 1.081 |
| B1 | 16.582% | **12.317%** | **7.403%** | **27.18%** | 10.504% | 0.853 |
| **R0** | 16.846% | 11.154% | 5.494% | 20.18% | **10.967%** | **0.983** |
| R1 | 16.599% | 12.339% | 7.396% | 27.16% | 10.508% | 0.852 |
| R2 | 16.511% | 12.203% | 7.417% | 27.23% | 10.525% | 0.863 |
| R3 | 16.555% | 12.198% | 7.412% | 27.21% | 10.531% | 0.863 |

R0's selection is B0's, to four decimals, at every K — §6's structural claim, measured. What R0
changes is the **number printed beside the pick**: 10.967% against B0's 12.058% for a realized
11.154%.

---

## HOLDOUT — CHINEXT (135,753 rows · 485 positives · base 0.3573% · 433 dates)

**Read every regime number on this board as a COVERAGE NULL** (§5): the dial is degenerate here.

| Model | Brier ×1000 | **skill vs B0** | skill vs R0 | log-loss skill | AUC | P̂/realized | ECE | Murphy reliability |
|---|---|---|---|---|---|---|---|---|
| B0 ladder | **3.54896** | 0.000% | +0.026% | 0.000% | 0.5396 | **0.942** | **0.065pp** | **0.0145** |
| B1 (L3) | 3.96368 | −11.686% | −11.657% | −11.684% | 0.7259 | **2.577** | 0.574pp | 0.4381 |
| B2 (L3, reported) | 3.55019 | −0.035% | −0.009% | +2.040% | 0.6908 | 1.004 | 0.093pp | 0.0252 |
| P2 (L3, reported) | 3.69319 | −4.064% | −4.037% | −2.120% | 0.6672 | 1.554 | 0.275pp | 0.1642 |
| **R0 regime ladder** | 3.54989 | −0.026% | 0.000% | −0.443% | **0.5633** | 1.118 | 0.115pp | 0.0177 |
| R1 +covariate | 3.99251 | −12.498% | −12.469% | −13.350% | 0.7156 | 2.635 | 0.614pp | 0.4665 |
| **R2 regime calibration** | 4.02658 | **−13.458%** | −13.428% | −13.620% | **0.7272** | **2.772** | 0.662pp | **0.5108** |
| R3 both | 4.02699 | −13.470% | −13.440% | −13.870% | 0.7190 | 2.651 | 0.634pp | 0.5032 |

### The failure, bin by bin — B1 vs R2 at the top of the book

| B1 bin | n | P̂ | realized | | R2 bin | n | P̂ | realized |
|---|---|---|---|---|---|---|---|---|
| 7 | 16,890 | 1.480% | 0.681% | | 8 | 17,440 | 1.582% | 0.608% |
| 8 | 8,731 | **8.586%** | **1.535%** | | 9 | 8,945 | **8.983%** | **1.532%** |

Both models are fine through the bottom six bins and both fail in the top two. R2's top bin quotes
**0.4pp higher** for the same realized rate. **Regime conditioning moved the failure by nothing and
made it marginally worse.**

### Holdout ladder × regime — ChiNext

| 连板 N | has a print | no pairs | rows | ratio |
|---|---|---|---|---|
| 0 | 0.354% (n=92,414) | 0.275% (n=42,845) | 135,259 | 1.285× (Wilson intervals touch) |
| 1 | 8.723% (n=321) | 3.759% (n=133) | 454 | 2.320× (28 and 5 positives — THIN) |
| 2 | 16.13% (n=31) | 0% (n=2, THIN) | 33 | — |
| 3+ | 28.57% (n=7, THIN) | — | 7 | — |

Even the degenerate print/no-print binary carries information — but on 33 and 7 rows at the rungs, it
is a hint, not a measurement.

### Per-year Brier skill vs B0 — ChiNext

| year | n | base | B1 | B2 | P2 | **R0** | R2 |
|---|---|---|---|---|---|---|---|
| 2024 | 14,471 | 0.553% | −4.216 | +0.253 | −2.139 | **−0.173** | −5.576 |
| 2025 | 75,580 | 0.327% | −11.580 | −0.047 | −4.024 | **+0.058** | −13.144 |
| 2026 | 45,702 | 0.346% | −15.569 | −0.159 | −5.085 | **−0.083** | −17.869 |

**B1's failure is worsening monotonically** (−4.2 → −11.6 → −15.6) while R0 sits within ±0.2% of the
ladder every year. A model whose miscalibration grows with time is not a model that needs one more
covariate.

---

## STAR — THIN-SKIP (printed, not silently downgraded)

Modelled window would have been 2019-07-29 → 2026-08-06, holdout from 2024-07-01 (510 dates,
101,038 rows, 497 positives, base 0.492%). **Fit-core positives 137 against the pre-registered floor
of 150; fit-calibration positives 36 against 50.** The listing-era re-split moved fit-core positives
from L3's 40 to 137 — a 3.4× improvement that still does not reach the floor. **The floor was not
lowered.** STAR's own dial is available on only **20.29%** of its sessions (346 of 1,705), so even a
board that cleared the gate would be testing the regime on one session in five.

---

## LIVE REGIME STATE (display only — nothing promoted, sized or gated)

| Board | as of | i5_ma5 | stratum | R0's row today: N=0 / 1 / 2 / 3+ |
|---|---|---|---|---|
| main | 2026-08-07 | 0.2274 | **T2_mid** | 1.03% / 12.90% / 31.08% / 49.38% |
| chinext | 2026-08-07 | 0.0000 | *(H2_hot — see §5; the label is an artifact)* | 0.44% / 15.46% / 25.30% / 47.50% |

---

## WHAT THIS DOES **NOT** ESTABLISH

- **NO significance claim.** Limit-ups cluster hard in time and in the cross-section, so every Wilson
  interval printed here is **understated**. The evidence offered is skill and calibration on a frozen
  holdout plus per-year stability — never a p-value. R0's +0.061% in particular is not defended as
  distinguishable from zero; it is defended as *the measured number, positive, in 4 of 6 years*.
- **It does NOT establish that `i5` is causal.** It establishes that conditioning on `i5` changes the
  holdout's calibration and level in measured directions. A dial that merely co-moves with the base
  rate would do the same.
- **It does NOT refute regime conditioning as an idea.** It refutes **one construction** — a frozen
  per-stratum isotonic map fitted on L3's specific 397-date calibration slice — and it names the
  precise precondition that construction violated (§4). Per the ORE LAW, a kill closes the
  construction tested, not the search space. Continuous-in-`i5` calibration, regime × feature
  interactions, and the L1 continuation-side merge are all untested and all in the ledger.
- **`i5` is not dead as a factor — it is null as a STANDALONE LEVEL COVARIATE on the onset side.**
  §7 measures it working (1.32× on the N=0 bulk, 1.67× on the first rung, Wilson-disjoint). It is
  retained as a **confluence input** by house epistemics; what failed is the specific job of
  repairing a frozen calibration map.
- **Calibration remains IN-UNIVERSE.** The probabilities are calibrated for the curated ~1,842-name
  store, not the A-share market, and the 打板 game is denser in the names the store omits. A
  market-level dial inherits that curation **more** than a per-name feature does.
- **It says nothing about FILLABILITY.** P is for a limit-up **close**; a name that gaps straight to
  the limit at the open is unfillable and still scores as a hit. That is the rider lane's question.
- **It says nothing about the CONTINUATION side as a modelled object.** N is an input here and `i5`
  is a market aggregate; `P(next board | already N boards)` is lane L1's, and §7 is the strongest
  argument in this receipt that the merge belongs **there**.
- **H=1 only.** Nothing here speaks to a board within the next 3 or 5 sessions.
- **Survivorship is unfixed** with the stores we hold, and stated rather than patched.
- **Nothing is promoted.** The gauntlet is a promotion gate; this is display tier and no key is
  escalated.

---

## ORE LEDGER / UNTESTED VARIANTS

| # | Ore | Status | Why it could matter | Next |
|---|---|---|---|---|
| 1 | **Other L2 instruments as conditioners — 炸板率 (i4), 高标 height (i3)** | UNTESTED — only `i5` was admitted | L2 measured 炸板率 as a real **inverse** dial pooled (holdout 0.724×, rho −0.6) that did **not** survive its era-neutral control (median 0.974, 9/16). Under house epistemics that makes it a **confluence candidate, not a null**. `i3` is blind in our universe (below the market on 21 of 36 clean dates, mean gap 1.81 boards). | Two-dial strata (`i5` × `i4`) on the same frozen split, pre-registered. `i3` needs the vendor pool first. |
| 2 | **Continuous-in-`i5` calibration instead of terciles** | UNTESTED | Terciles are a step function over a continuous dial: every within-stratum gradient is discarded and every edge is a discontinuity a desk must explain. §5 shows the cut can degenerate entirely on a point mass — a continuous map cannot. | 2-D isotonic or beta calibration with `i5` as the second argument; compare against R2 on the identical frozen split. |
| 3 | **Regime-conditional FEATURE coefficients (interactions, not level)** | UNTESTED — R1 admits `i5` as a **main effect only**, and §8 measures that main effect at **+0.0007** | The practitioner claim is not that a hot tape lifts every name equally — it is that run-up and gap **mean** something different in a hot tape. §7 shows the dial's strength varies 1.32× → 1.67× → 0.99× across ladder rungs; only an `i5 × N` and `i5 × f3` cross can express that. **This is the highest-value untested variant in this ledger.** | Explicit `i5 × f3`, `i5 × f4`, `i5 × N` crosses, pre-registered, same frozen split. |
| 4 | **Horizons H > 1 (a board within the next 3 / 5 sessions)** | UNTESTED — inherited from L3 | H=1 is the hardest possible framing. A regime dial should help **more** at a longer horizon, since it is a far slower variable than any per-name feature. | Same features, H ∈ {2,3,5}; overlapping windows worsen the dependence, so state it before measuring. |
| 5 | **The L1 continuation-side regime merge** | OUT OF SCOPE — lane L1 owns `P(board \| already N boards)` | `i5` **is** the realized continuation rate, so conditioning a *continuation* model on it is far more direct than conditioning an *onset* model on it. §7's 1.670× on N=1 against 1.323× on the N=0 bulk — where N=0 is 98.79% of rows — says the largest expected effect in this program is there, not here. | L1's empirics × `i5` strata as a **sibling** model, never pooled with this one. |
| 6 | **Post-expansion re-run on the ~5,400-name universe** | BLOCKED on the sibling universe lane, not on method | The omitted names are where the 打板 game is densest, and a market-level dial inherits the curation directly — the `i5` **level** measured here is a curated-slice level, and L2 measured a 2.748× median undercount. ChiNext's degeneracy (§5) may be pure coverage and could vanish outright. | Re-run this file unchanged once the store lands; compare receipts as **two universes**, never as before/after of one. |
| 7 | **Tie-aware / mass-aware strata for sparse boards** | UNTESTED — the pre-registered quantile ladder produced an empty stratum on ChiNext | §5 is a pure artifact of cutting quantiles on a point mass. A cut that treats "exactly zero" as its own state, or a minimum-occupancy constraint, would have given ChiNext a real two-state dial. **Not applied here — changing a cut after watching it degenerate is the move pre-registration exists to block.** | State the rule once, before Wave 3, and re-run both boards under it. |
| 8 | **Per-stratum feature selection / per-stratum logistic** | UNTESTED — R2 deliberately holds the logistic fixed | Holding the logistic fixed is what makes R2's effect attributable to calibration **alone**; relaxing it buys flexibility and loses the attribution. | Only after a calibration effect exists to attribute, and with the attribution loss stated up front. |
| 9 | **Platt / beta calibration in place of isotonic** | UNTESTED — inherited from L3 | Isotonic is a step function whose top block is a tie — L3's §12 head-of-book defect. §9 shows per-stratum maps only partially unlock it (2,232 → 631 rows tied) and cost head accuracy. A smooth map would order the head outright. | Beta calibration per stratum; report ECE, Murphy reliability **and** head-of-book ties for both. |
| 10 | **A calibration slice chosen by REGIME rather than by DATE** | UNTESTED — and §4 is the argument for it | The root defect is that the last 15% of fit *dates* is one contiguous era whose dial→outcome ordering happens to be inverted. A calibration slice **stratified across the fit window** (e.g. every 7th date) would inherit the fit window's ordering, not one sub-era's. This is a change to L3's design, not to this lane's, so it is not taken here. | Pre-register a stratified-by-date calibration slice; re-run B1 and R2 unchanged on it. |
| 11 | **The STAR listing-era re-split as a general policy** | APPLIED HERE TO STAR ONLY, by pre-registration | If a listing-era re-split is right for STAR it may be right for any board whose era post-dates the global split — but a split rule chosen per board is a degree of freedom and must be pre-registered, never fitted. | State the rule once, in the program masterplan, before Wave 3. |
| 12 | **Near-limit as a soft label; per-name partial pooling; gradient boosting** | UNTESTED — carried forward from L3's ledger unchanged | None of these were touched by this lane and none are closed by it. | See L3's `ONSET_CALIBRATION_V1_2026-08-08.md` ORE LEDGER. |

---

## DEVIATIONS AND CORRECTIONS

- **STAR was re-split**, as authorised in the brief and pre-registered above. It changed nothing for
  main or chinext (gated by asserting L3's `make_splits` returns their boundaries identically) and
  STAR still fails its floors.
- **`B2` and `P2` were added as reported-only benchmarks** after the first run, for the reason given
  in PRE-REGISTRATION. They are L3's models, re-derived unchanged; no Wave-2 model was altered in
  response. Without them this receipt would have implied R0 was the program's best object on main,
  which is false.
- **The `ladder_x_regime` cross-tab and the dial-shape / occupancy diagnostics** were added as
  reporting after the first run. They fit nothing and select nothing; they are descriptive tables
  over pre-registered objects, and §5 and §7 are unreadable without them.
- **No floor was lowered, no edge was moved, no stratum scheme was re-chosen** after any holdout
  number was seen. The ChiNext degeneracy was left standing and printed (ORE row 7).

---

## REPRODUCE

```bash
# Wave-1 dependencies — this lane does not vendor copies of them.
git fetch origin claude/cn-limit-w1-onset claude/cn-limit-w1-regime-salvage
git show origin/claude/cn-limit-w1-onset:research/cn_prophet_audit/onset_calibration_v1.py \
  > research/cn_prophet_audit/onset_calibration_v1.py
git show origin/claude/cn-limit-w1-regime-salvage:research/cn_prophet_audit/board_ecology_series_v1.parquet \
  > research/cn_prophet_audit/board_ecology_series_v1.parquet
# (or simply run this after both Wave-1 PRs have merged to main)

TZ=UTC python3 research/cn_prophet_audit/regime_calibration_v2.py
```

Writes `research/cn_prophet_audit/REGIME_CALIBRATION_V2_2026-08-09.json`. A missing dependency is a
loud, named error listing these commands — never a silent fallback, because a fallback would quietly
change what "regime" means.
