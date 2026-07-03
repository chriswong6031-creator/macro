# Wave-6 Report — donor promotion (G6a) + blocked-population discovery (W6-B) + fixtures

> Companion to `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md` (THE program spec; §2 tripwires
> and §4 constitution bind verbatim) and the binding pre-registration
> `research/entry_timing/WAVE6_PREREG.md` **v2** (2026-07-02, 4-reviewer adversarial panel; the §8
> amendment log is honored line-by-line below). Machinery reused **by import, never reimplemented**:
> `wave1.py` (`compute_outcomes`, `build_tf_grids`, sector d-matrix, capit/ATR constants), `wave2.py`
> (panel loaders, FIX-1 ISO serialization, the `Pool` pattern), `wave5.py`/`wave5b.py` (policy/ATR/
> bootstrap machinery + the #25 donor-timeline builder **verbatim**), `tuning_harness.py`
> (`rsi`/`ema`/`stoch_rsi_kd`/`xup`/`tf_bars`/`to_daily`), `engine/signal_quality.py` (`signal_frame`,
> `_buy_filter`, `_bear_div`, `_swing_highs` — **read to replicate the blocked path on the 3D grid
> exactly; never modified**). New wave-6 code: the honest blocked-population replicator, the F1–F8
> feature battery on the 3D grid, the C-SHALLOW / C-LOCKOUT state machines, the episode-clustered G6a
> bootstrap, and the fixtures.
>
> **Mandate (prereg §6):** exactly ONE statistical ship decision this wave — **G6a** (the donor
> context chip). W6-B is a **stratification DISCOVERY study** (wave-1 protocol) that produces
> **promotions to a wave-7 gate candidate ONLY** — nothing from W6-B ships to a board. W6-C (the HOLD
> tracker) is a product decision on already-measured objects, not carried in this statistical report.
> Every number below comes from the frozen parquets / gate JSONs / selftest under
> `research/entry_timing/_out/wave6_*`.

---

## 0. Verdict at a glance

| decision | binding rule (prereg) | result | **outcome** |
|---|---|---|:--:|
| **G6a** donor-unwind context chip | §1: deep gap ≥ +2pp AND baskets gap ≥ +2pp AND episode-clustered 90% LB > 0 (deep) AND per-name majority ≥ 52% AND excl-2025 + both halves same sign AND ≥ 12 cracking episodes | deep **+5.96pp**, baskets **+5.81pp**, LB90 **+2.66pp**, per-name **69.3%**, 159 episodes, all splits + | **SHIP** |
| **W6-B** feature promotions | §2: fav−unf ≥ +5pp clean15 POINT, n ≥ 300/side, stop5 not worse >2pp, sign-stable on both time & ticker halves, ≥ 25 distinct 63d blocks; composites also pass fixtures | **0 / 8 features+composites promote** on ANY panel | **NONE PROMOTE** |

**The one-sentence G6a why:** on the incumbent E_FRESH confluence entries, fires that fire while the
market's leading GICS sector (the donor) is *cracking* have a materially higher clean-15 rate than
fires into an *intact* donor (deep +5.96pp, baskets +5.81pp), the difference survives episode-level
clustering (paired-difference 90% LB **+2.66pp > 0**), it is broad across names (69.3% of ≥3-fire
names), and it holds excl-2025 and in both time halves — so the donor-unwind context chip earns its
display-only ship, the SOLE statistical ship of the wave.

**The one-sentence W6-B why:** every "favorable" leg the prereg built to admit the owner's shallow
dips runs the **wrong way at the fire bar** — F1-shallow has *lower* clean15 than F1-deep on all three
panels, and no single feature or composite reaches the +5pp promotion bar with a stop-5 that isn't
worse; the honest instrument for the knife (C-LOCKOUT) is a proper subset that reduces admitted fires
but does not carry a clean-15 edge over the population it prunes.

**HK adversarial (the sign-inversion that matters):** the donor-cracking edge **INVERTS on HK**
(gap **−3.78pp** full panel, cracking WORSE). G6a's gate is US-anchored by construction (deep=stocks,
baskets=baskets), so it still passes — but the honest read is that the donor mechanism does **not**
generalize to HK, mirroring the wave-3 HK cohort failure. This is carried as a named caveat, not
laundered into the pass.

---

## 1. Config & panels

Produced by `research/entry_timing/wave6.py` (`--stocks` / `--baskets` / `--hk` panels, `--gates`
evaluation, `--selftest` fixtures). Multiprocessing via the wave-2 `Pool` pattern; dates round-tripped
as ISO strings in worker args (wave-2 ms→ns serialization bug class avoided). Fill = the daily bar
**strictly after** the 3D fire bar's known date for the blocked population; E_FRESH fills at i+1
(wave-5 machinery).

| | **stocks** (deep US) | **baskets** (decisive OOS) | **hk** (adversarial) |
|---|---|---|---|
| panel glob | `data/stocks/*.parquet` | `data/baskets/ohlcv/*.parquet` | `data/hk_search/closes_deep.parquet` |
| index context | SPY | SPY | **HSI** (`_HSI_deep.parquet`, 1986–2026) |
| names (≥ min_bars) | **212** | **2,335** | **157** |
| min_bars | 1,500 | 1,000 | 800 |
| eval_start | 2012-01-01 | 2015-01-01 | 2012-01-01 |
| workers | 6 | 6 | 4 |
| runtime | 72.7s | 287.3s | 29.4s |
| errors | 0 | 0 | 0 |
| **E_FRESH fires (W6-A, m2d_s3d)** | **10,286** | **81,260** | **6,981** |
| donor episodes | 741 | 143 | 237 |
| **blocked pop (honest)** | **7,121** | **26,093** | **3,024** |
| blocked pop (eval, full window) | **2,457** | **24,775** | **2,158** |
| naive `close<MA200` daily bars | 673,816 | 2,568,714 | 290,176 |
| C-SHALLOW admits | 1,166 | 2,381 | 372 |
| C-LOCKOUT admits | 5,873 | 18,720 | 2,182 |

**Two populations, kept distinct throughout:** `blocked(honest)` is the full count of confluence
fires that the live `_buy_filter` below∧weekly-down path blocks (§2, honest replication on the 3D
grid); `blocked(eval)` is the fully-observed subset (a fire enters the W6-B stats only if its forward
window is complete), and it is the row count of the `_wb` parquets on which every W6-B table is
computed. The naive count is a **daily-bar** count of `close < MA200`, reported only to make the
honest-vs-naive gap visible — it is not a fire population.

---

## 2. G6a — donor-unwind promotion (the SOLE statistical ship)

**Inference unit:** the donor-unwind EPISODE (a maximal run of consecutive `cracking` days on the
donor timeline; wave-5b #25 definition verbatim). `cracking` = a fresh weekly RSI-MACD bearish cross
on the top-1 126d-EW-return GICS sector within the trailing 4 completed weeks, OR donor 20d EW return
< 0 while still top-ranked; `intact` = otherwise. The paired-difference bootstrap resamples cracking
EPISODES (each one cluster) and intact fires (each a singleton cluster) together and takes the α=0.10
quantile of `clean15(cracking) − clean15(intact)` — so both cells' sampling variability is honored.

### 2.1 E_FRESH donor cells — clean15 / stop5 / dead-money

| panel | cell | n | names | clean15 | stop5 | dead-money |
|---|---|---:|---:|---:|---:|---:|
| **stocks** | cracking | 3,921 | 212 | **38.38** | 38.08 | 13.82 |
| | intact | 6,365 | 212 | **32.43** | 41.81 | 14.97 |
| **baskets** | cracking | 30,938 | 2,334 | **34.40** | 44.73 | 6.02 |
| | intact | 50,322 | 2,334 | **28.59** | 49.59 | 7.91 |
| **hk** *(adversarial)* | cracking | 4,198 | 157 | **31.75** | 48.38 | 7.17 |
| | intact | 2,783 | 157 | **35.54** | 42.51 | 8.01 |

On both US panels `cracking` beats `intact` on clean15 by ~+6pp AND has the lower stop-5 AND the lower
dead-money — a clean directional read. On HK the sign flips on every axis (cracking clean15 31.75 <
intact 35.54).

### 2.2 G6a gate table (evaluated verbatim from `wave6_stocks_gates.json`)

The G6a block reads the deep (`stocks_wa`) + baskets (`baskets_wa`) parquets regardless of the `--panel`
argument, so the identical G6a object appears in all three gate JSONs — the HK panel does NOT feed the
gate (it is adversarial context, §2.4).

| clause (prereg §1) | decisive number | verdict |
|---|---|:--:|
| deep gap ≥ +2pp | **+5.956pp** (cracking 38.38 − intact 32.43) | ✓ |
| baskets gap ≥ +2pp | **+5.809pp** (34.40 − 28.59) | ✓ |
| episode-clustered 90% LB of paired diff > 0 (deep) | **+2.657pp** > 0 | ✓ |
| ≥ 12 distinct cracking episodes contribute (deep) | **159** episodes | ✓ |
| per-name majority ≥ 52% (deep, names ≥ 3 fires/cell) | **0.6934** (69.34%) | ✓ |
| excl-2025 gap positive | **+5.973pp** | ✓ |
| both time halves same sign (positive) | half1 **+7.606**, half2 **+3.878** | ✓ |
| **G6a PASS** | all clauses hold | **SHIP** |

Baskets robustness (not a gate clause, on record): excl-2025 +5.78pp, half1 +4.49pp, half2 +6.55pp —
all positive, so the baskets direction is also split-stable.

### 2.3 Ship shape

Per §1: a **market-wide context chip** ("rotation: leader cracking / intact") + forward-ledger fields,
**display-only** — never a rank change, never a hard gate this wave. This is the family's single
accounted statistical ship (§6 multiplicity: one).

### 2.4 HK adversarial section (binding context for G6a)

HK is the adversarial panel for every promoted object. The donor-unwind edge **does not survive** on
HK:

| HK split | cracking clean15 | intact clean15 | gap | n |
|---|---:|---:|---:|---:|
| full panel | 31.75 | 35.54 | **−3.784** | 6,981 |
| excl-2025 | 30.12 | 35.28 | **−5.170** | 6,543 |
| half1 (<2020) | 34.34 | 35.94 | **−1.594** | 3,600 |
| half2 (≥2020) | 29.28 | 35.04 | **−5.753** | 3,381 |

The inversion is sign-stable in the WRONG direction across every HK split. Mechanism read (consistent
with the wave-3 HK ledger row): HK is ~157 names across ~12 sectors in a macro-correlated market, so
"the leading sector is cracking" is near-universal during HK drawdowns and carries no discrimination —
it mostly co-fires with the market falling. **G6a ships US-only by construction; HK gets nothing**, and
the report does not treat the US pass as market-general.

---

## 3. W6-B — blocked-population discovery (stratification, wave-1 protocol)

**Population (honest replication of the live blocker):** confluence fires (`CB ∨ revBuy`) where the 3D
`_buy_filter` counter-trend branch blocks — `¬above200(3D) ∧ ¬w_bull(3D)` — AND NOT bearish-div-vetoed
(`SQ._bear_div` on 3D swing highs) AND NOT saved by the held∧reclaim escape at the next two 3D bars
(`held = close[i+1]>close[i]`, `reclaim = above200[i+1] ∨ above200[i+2]`). Replicated grid-identical
to `signal_quality`; the last two 3D bars are excluded as pending-confirmation (anti-repaint). Every
W6-B table is computed on the fully-observed `_wb` parquet (stocks n=2,457, baskets n=24,775,
hk n=2,158).

**Promotion rule (prereg §2, to a wave-7 gate candidate — NOTHING ships to a board):** favorable
stratum − unfavorable stratum ≥ **+5pp clean15 POINT**, n ≥ 300 per side, stop5 not worse by > 2pp,
sign-stable on both time AND ticker halves, ≥ 25 distinct 63d blocks. Ties resolve to the SIMPLER leg
(CHARTER §3).

### 3.1 Singles — F1, F3, F5, F6, F7, F8 (favorable vs unfavorable)

Numbers from `wave6_{panel}_gates.json.W6B_promotions.features`. `gap` = clean15(fav) − clean15(unf).
**A negative gap means the "favorable" side is WORSE — the mechanism runs backward.**

**stocks (deep, n=2,457):**

| feature (fav vs unf) | gap pp | n_fav | n_unf | n_ok | stop5 fav | stop5 unf | stop_ok | blocks | sign-stable | PROMOTE |
|---|---:|---:|---:|:--:|---:|---:|:--:|---:|:--:|:--:|
| F1 shallow vs deep | **−9.91** | 1,273 | 358 | ✓ | 43.68 | 39.66 | ✗ | 57 | ✓ | **no** |
| F3 unbroken vs broken | −2.70 | 1,470 | 987 | ✓ | 43.20 | 42.86 | ✓ | 57 | ✓ | **no** |
| F5 not-entrenched vs entrenched | −4.83 | 1,959 | 490 | ✓ | 42.52 | 45.31 | ✓ | 57 | ✗ | **no** |
| F6 rs-ok vs new-low | +0.14 | 2,419 | 38 | ✗ | 43.08 | 42.11 | ✓ | 57 | ✗ | **no** |
| F7 weekly-turn vs none | +1.47 | 933 | 1,524 | ✓ | 43.19 | 42.98 | ✓ | 57 | ✓ | **no** |
| F8 ¬bear_ctx vs bear_ctx | −14.19 | 2,263 | 194 | ✗ | 44.85 | 22.16 | ✗ | 55 | ✓ | **no** |

**baskets (OOS, n=24,775):**

| feature | gap pp | n_fav | n_unf | n_ok | stop5 fav | stop5 unf | stop_ok | blocks | sign-stable | PROMOTE |
|---|---:|---:|---:|:--:|---:|---:|:--:|---:|:--:|:--:|
| F1 shallow vs deep | **−6.29** | 7,673 | 9,190 | ✓ | 52.38 | 49.64 | ✗ | 45 | ✓ | **no** |
| F3 unbroken vs broken | −1.02 | 12,662 | 12,113 | ✓ | 50.13 | 49.26 | ✓ | 38 | ✗ | **no** |
| F5 not-entrenched vs entrenched | −1.85 | 16,169 | 7,685 | ✓ | 48.94 | 51.37 | ✓ | 44 | ✗ | **no** |
| F6 rs-ok vs new-low | −5.81 | 24,515 | 260 | ✗ | 49.75 | 45.38 | ✗ | 45 | ✓ | **no** |
| F7 weekly-turn vs none | +1.55 | 10,082 | 14,693 | ✓ | 48.71 | 50.38 | ✓ | 45 | ✓ | **no** |
| F8 ¬bear_ctx vs bear_ctx | −5.56 | 22,733 | 2,042 | ✓ | 50.59 | 39.86 | ✗ | 44 | ✗ | **no** |

**hk (adversarial, n=2,158):**

| feature | gap pp | n_fav | n_unf | n_ok | stop5 fav | stop5 unf | stop_ok | blocks | sign-stable | PROMOTE |
|---|---:|---:|---:|:--:|---:|---:|:--:|---:|:--:|:--:|
| F1 shallow vs deep | −5.88 | 734 | 639 | ✓ | 54.36 | 48.51 | ✗ | 55 | ✓ | **no** |
| F3 unbroken vs broken | −4.90 | 1,292 | 866 | ✓ | 51.16 | 48.96 | ✗ | 57 | ✓ | **no** |
| F5 not-entrenched vs entrenched | −4.06 | 1,353 | 771 | ✓ | 50.92 | 49.29 | ✓ | 57 | ✓ | **no** |
| F6 rs-ok vs new-low | −3.91 | 2,121 | 37 | ✗ | 50.45 | 40.54 | ✗ | 57 | ✓ | **no** |
| F7 weekly-turn vs none | **+2.78** | 959 | 1,199 | ✓ | 48.38 | 51.79 | ✓ | 56 | ✓ | **no** |
| F8 ¬bear_ctx vs bear_ctx | −8.42 | 1,329 | 829 | ✓ | 53.88 | 44.51 | ✗ | 46 | ✓ | **no** |

**Reading the singles.** F7 (weekly turn present) is the ONLY leg whose favorable side is the
better side on all three panels (+1.47 / +1.55 / +2.78pp) with a not-worse stop5 and full sign
stability — but it never reaches the +5pp promotion bar, so it does not promote. F1 (the owner's
shallow-dip thesis) is the loudest falsification: shallow dips have *lower* clean15 AND *higher*
stop5 than deep declines on every panel (−9.91 / −6.29 / −5.88pp), the exact inverse of the intuition
the prereg's object model warned about. F8's "favorable" (¬bear_ctx) leg is the one with the huge
apparent gap (−14.19pp deep), but its unfavorable (bear_ctx) cell has both the LOWER clean15 *and*
the far lower stop5 (22.16 vs 44.85) — a fixed-barrier vol artifact, not an entry edge, which is
exactly why bear_ctx was demoted from an admit-leg to a stratifier (§3.3).

### 3.2 F4 dwell monotone curve + F2 sigma bands (reported, not gated)

**F4** clean15 by native-ME dwell run-length (no hand bands; the smooth distribution the prereg
required in lieu of a ≤2/≥4 cut). Deep panel, low-n tail collapses:

| dwell (months) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| n | 1,671 | 170 | 137 | 101 | 69 | 80 | 48 | 53 | 35 |
| clean15 | 33.87 | 26.47 | 32.12 | 36.63 | 37.68 | 43.75 | 45.83 | 28.30 | 51.43 |
| stop5 | 42.85 | 45.29 | 41.61 | 42.57 | 40.58 | 41.25 | 37.50 | 52.83 | 34.29 |

There is a weak *rising* clean15 tendency from dwell 3→6 (the mid-dwell washouts) but it is
non-monotone and reverses at dwell 7, and the per-dwell n is tiny past ~5 — no knee survives as a
promotable cut. Baskets shows the same story with the mass at dwell 0 (n=18,967, clean15 29.97) and a
noisy, non-monotone tail. This directly closes prereg amendment #14/#18: **dwell is not a clean
knife-vs-shallow separator on a smooth distribution.**

**F2** sigma-scaled decline speed `(252d-high drawdown) ÷ (ATR63% × √126)` — fast-fall (most
negative) vs slow-drift:

| panel | fast_fall (n / clean15 / stop5) | mid | slow_drift |
|---|---|---|---|
| stocks | 811 / 36.25 / 41.06 | 810 / 32.96 / 43.70 | 836 / 33.85 / 44.38 |
| baskets | 8,176 / 31.21 / 48.64 | 8,175 / 30.95 / 48.60 | 8,424 / 29.10 / 51.80 |
| hk | 712 / 29.63 / 49.44 | 712 / 32.02 / 48.31 | 734 / 24.25 / 53.00 |

Fast-falls modestly beat slow-drifts on clean15 with a lower stop5 on stocks & baskets (a hint that
multi-sigma trend legs recover better than slow bleeds), but the gap is small (~+2–3pp), not sign-clean
on HK (mid > fast), and F2 is reported-not-gated by design. No promotion.

### 3.3 within-¬bear_ctx decomposition (§8 finding 9, REQUIRED table)

bear_ctx was demoted from a silent admit-leg to a stratifier; the decomposition below shows what each
single feature's gap is **inside the ¬bear_ctx population only** — i.e. with the bear-veto's vol
artifact stripped out. Numbers from `within_no_bearctx_decomposition`:

| feature | stocks gap pp (n_fav/n_unf) | baskets gap pp (n_fav/n_unf) | hk gap pp (n_fav/n_unf) |
|---|---|---|---|
| F1 shallow vs deep | −5.461 (1,207/308) | −5.595 (7,215/8,264) | +2.647 (537/295) |
| F3 unbroken vs broken | +0.085 (1,410/853) | −0.475 (12,114/10,619) | +2.789 (944/385) |
| F5 not-entrenched vs entrenched | −1.596 (1,824/432) | −1.350 (15,220/6,681) | +0.249 (887/426) |
| F7 weekly-turn vs none | −0.090 (835/1,428) | +1.080 (9,232/13,501) | +0.985 (571/758) |

Stripping bear_ctx does NOT rescue any leg on the decisive US panels: F1 stays strongly negative
(−5.46 / −5.60), F3/F5/F7 collapse to near-zero. The apparent F1/F5 gaps in the full-population tables
were partly the bear-context confound, and what remains inside ¬bear_ctx is either the wrong sign
(F1) or noise (F3/F5/F7). HK's small positive F1/F3 gaps here are on tiny cells and do not survive as
US-generalizable. **This is the panel's finding-9 payload: no feature has a clean, bear-context-free
selection on the blocked population.**

### 3.4 Composites — C-SHALLOW and C-LOCKOUT serial economics

- **C-SHALLOW** = F1-shallow ∧ 200MA-rising ∧ F3-unbroken (monthly D ≥ 25). The owner's-buy shape.
- **C-LOCKOUT** (the ratchet) = state machine: OPEN until (F4 dwell ≥ 4 ∨ F5 entrenched ∨ F1-deep) —
  the knife signature — then SHUT until the name's monthly D exits oversold AND it reclaims its 200MA
  (full cycle reset). Evaluated on serial per-name economics; a proper subset of the blocked population.

| panel | composite | admit n | admit clean15 | admit stop5 | admit dead-money | rest n | rest clean15 | rest stop5 | gap pp | stop_ok | PROMOTE |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|:--:|
| stocks | C-SHALLOW | 438 | 32.65 | 40.18 | 16.89 | 2,019 | 34.72 | 43.68 | −2.07 | ✓ | **no** |
| stocks | C-LOCKOUT | 2,099 | 33.35 | 43.45 | 11.15 | 358 | 40.22 | 40.78 | −6.87 | ✗ | **no** |
| baskets | C-SHALLOW | 2,288 | 28.45 | 50.04 | 8.78 | 22,487 | 30.60 | 49.67 | −2.15 | ✓ | **no** |
| baskets | C-LOCKOUT | 17,764 | 29.97 | 49.11 | 5.56 | 7,011 | 31.52 | 51.21 | −1.56 | ✓ | **no** |
| hk | C-SHALLOW | 263 | 26.62 | 53.23 | 14.07 | 1,895 | 28.87 | 49.87 | −2.25 | ✗ | **no** |
| hk | C-LOCKOUT | 1,536 | 26.82 | 51.17 | 9.05 | 622 | 32.96 | 48.07 | −6.14 | ✗ | **no** |

**Serial economics read.** C-LOCKOUT does what it was built to do *mechanically* — it is a strict
subset that admits the first fire of a knife then shuts (the Tencent fixture, §4.1, proves ≤1 admit &
≥80% shut). But the admitted population it leaves is NOT a higher-clean15 set than the fires it prunes;
on stocks & HK the admitted set is actually *worse* on clean15 (−6.87 / −6.14pp) because the ratchet
opens on the early, near-indistinguishable knife fires (dwell 0, the bulk of the mass) and shuts only
after the damage marker — so it prunes the *later* deep fires (which, per F1, are the higher-clean15
ones). C-LOCKOUT's value is capital-destruction avoidance on serial re-fires (fires 2..N of a knife),
not a per-fire clean15 lift — and per-fire clean15 is what the promotion rule measures. It does not
promote. C-SHALLOW is negative on every panel (the owner's shallow-dip shape is the *lower*-clean15
side, consistent with F1). Neither composite promotes; both pass their fixtures (§4).

---

## 4. Fixtures (`--selftest`, run BEFORE the panels; all green)

### 4.1 Tencent 0700.HK 2021-01..2022-10 — the C-LOCKOUT lockout scan

The v1 READMIT gate opened twice on Tencent during the knife (the inverted-gate error on the record).
The v2 C-LOCKOUT reframing must admit ≤ 1 fire across the window AND be SHUT for ≥ 80% of it (measured
from knife onset), including 2021-09-30 (the mid-knife date v1 admitted).

```
blocked fires in window: 3    ratchet events: 3
C-LOCKOUT admitted fires: 1   (date: 2021-08-24)
SHUT coverage, full window:      103/158 = 65.2%   (first ~7mo OPEN = pre-knife healthy period, honest)
SHUT coverage, from knife onset 2021-08-24: 100.0%   (the ≥80% 'locked-out for the knife' measurement)
2021-09-30 (mid-knife): 3D bar known=2021-09-30  state=SHUT  admitted=False   ✓
C-SHALLOW admissions in window: 0   (honesty table — no shallow-dip admit hidden)
ASSERT admit≤1: True   SHUT≥80% (from onset): True   0930 SHUT & not-admitted: True
```

The ratchet admits exactly the first knife fire (2021-08-24), prices it at the −5% stop, then locks out
for 100% of the remaining knife — reversing v1's twice-open failure. The window's first ~7 months are
legitimately OPEN (Tencent was near its Feb-2021 peak, not yet in the knife), and the report states this
rather than counting it toward the shut fraction.

### 4.2 MCD 2026 + KO 2024/2025 — per-candidate state tables (open/shut, premium/lead)

A candidate that never opens for ANY positive fixture is dead; one that opens late gets its lateness
(premium/lead) printed, not excused.

| ticker | blocked(honest) | conf. fires | naive `<MA200` bars | window | fire date | f1 | distBelow | monthlyD | dwell | entrenched | 2w_turn / lead | C-SHALLOW | C-LOCKOUT | fwd63 |
|---|---:|---:|---:|---|---|---|---:|---:|---:|:--:|---|---|---|---:|
| **MCD** | 48 | 185 | 4,399 | 2026-04-21..06-30 | 2026-06-09 | shallow | 0.067 | 49.99 | 0 | False | False / 80d | **shut** | OPEN | −4.6% |
| **KO** | 47 | 205 | 4,487 | 2024-12-01..12-31 | 2024-12-27 | shallow | 0.026 | 93.04 | 0 | False | False / 113d | **OPEN** | OPEN | +15.8% |
| **KO** | 47 | 205 | 4,487 | 2025-09-08..12-31 | *(no blocked fire)* | — | — | — | — | — | — | shut | — | — |

**Reading the fixtures honestly.** C-SHALLOW opens for KO's 2024-12 dip (unbroken shallow, monthly D
93, and it worked: +15.8% fwd63) — so the shape is non-empty and can be right. But it **does not open
for MCD's 2026-06 fire** (monthly D 49.99 ≥ 25 unbroken and shallow, but the 200MA-rising leg fails —
MCD's 200MA was not rising at the fire), and MCD's fire went −4.6% fwd63, so C-SHALLOW's non-admission
was *correct* on MCD. The **2W turn is measured catastrophically late on both names** (MCD lead 80d,
KO lead 113d — the last 2W cross-up was months stale at the fire), the named F7-2W failure mode
(amendments #16/#17): the 2W leg is a context lag, not a fire-timing instrument, which is why F7's
*weekly* (fast) leg is the one that carries the only positive single-feature sign (§3.1). KO's
2025-09 window produced NO blocked fire at all (the fire that period was not blocked) — the population
screen is honest about which owner-dates it does and does not contain.

### 4.3 Completedness / anti-repaint assertions (§2, all PASS)

```
monthly anti-repaint:    16 ME known dates checked, repaint hits=0  → PASS
                         (a daily bar ON an ME known date never sees THAT month's D; +1-bar shift honored)
2W fixed-phase:          208 event bars, known-date>fill hits=0      → PASS
                         (no 2W cross lands before its fortnight known date; GLOBAL phase, not per-name)
blocked-fill anti-leak:  47 KO fires, fill≤known hits=0              → PASS
                         (the daily fill is STRICTLY after the 3D bar's known date)
```

### 4.4 Blocked-population count sanity (honest ⊊ confluence)

```
KO:      honest_blocked=47   confluence_fires=205   naive_below_MA200_bars=4,487   honest ⊊ fires ✓
MCD:     honest_blocked=48   confluence_fires=185   naive_below_MA200_bars=4,399   honest ⊊ fires ✓
0700.HK: honest_blocked=16   confluence_fires=61    naive_below_MA200_bars=1,338   honest ⊊ fires ✓
```

The honest blocked population is a non-empty PROPER subset of confluence fires on every fixture name
(degeneracy check §5: population ≠ ∅ and ≠ all-fires), and the naive `close<MA200` bar count is ~20–90×
larger — the concrete evidence that the live gate does NOT block sub-200 wholesale (the v1 population
was factually wrong; amendment #1).

---

## 5. Naive-vs-honest population counts (the amendment-#1 correction, panel-wide)

| panel | naive `close<MA200` daily bars | confluence fires | **honest blocked (below∧wk-down, no bear-div, no held∧reclaim)** | honest / confluence |
|---|---:|---:|---:|---:|
| stocks | 673,816 | 26,373 | **7,121** | 27.0% |
| baskets | 2,568,714 | 76,485 | **26,093** | 34.1% |
| hk | 290,176 | 8,849 | **3,024** | 34.2% |

The honest blocked population is roughly a quarter-to-a-third of confluence fires — it is a specific
counter-trend branch, NOT the whole sub-200 universe the naive screen would suggest (the naive count is
two orders of magnitude larger because it counts every day below the MA, not fires). The W6-B study runs
on the fully-observed subset of the honest population (stocks 2,457 / baskets 24,775 / hk 2,158; §1).

---

## 6. Leak-audit section

| # | assertion | status |
|---|---|---|
| 1 | **Blocked population replicated grid-identical to `signal_quality`** — `signal_frame` → `_buy_filter` counter-trend branch on the 3D grid; `_bear_div` on 3D swing highs; held∧reclaim escape read at 3D bars i+1,i+2 (never modified `signal_quality`) | **OK** |
| 2 | **Completedness — monthly (F3/F4)** — D computed on the ME-native series, mapped by known-date (index.max), shifted one bar so a month completing ON bar i is not visible at i; anti-repaint assertion 16 dates, 0 hits | **OK** (§4.3) |
| 3 | **Completedness — 2W (F7)** — FIXED GLOBAL fortnight phase (weeks since 1990-01-05 grouped in pairs), never a per-name resample anchor; 208 event bars, 0 known-date>fill hits | **OK** (§4.3) |
| 4 | **Blocked-fill anti-leak** — the daily fill is STRICTLY after the 3D fire bar's known date; 47 KO fires, 0 fill≤known hits; last two 3D bars excluded as pending-confirmation | **OK** (§4.3) |
| 5 | **F1/F2/F5/F6 windows backward-bounded** — distance-below-200MA, 252d-high drawdown, ATR63, 252d-entrenchment frac, 126d RS all computed from bars ≤ the 3D fire bar | **OK** (feature battery is `≤ state_idx`) |
| 6 | **F6 RS index-aligned** — RS-vs-index uses SPY (US/baskets) / HSI (HK) aligned to the name's index, trailing 126d, bars ≤ i | **OK** |
| 7 | **Episode clustering (G6a)** — cracking EPISODES are maximal consecutive-cracking runs on the donor timeline; the paired-difference bootstrap resamples episodes + intact singletons; 159 distinct cracking episodes on deep (≥12 floor) | **OK** |
| 8 | **Fortnight phase** — global, not per-name; the 2W cross event never lands before its fortnight known date (§4.3) | **OK** |
| 9 | **Donor timeline = wave-5b #25 verbatim** — top-1 126d-EW-return GICS sector, min-members/top-rank guards; fresh weekly bearish cross within 4 completed weeks OR donor 20d EW return < 0 while top-ranked | **OK** (imported, not reimplemented) |
| 10 | **No outcome field is an input** — F1–F8 and composites condition only on price/ATR/monthly-D/donor/index features at bars ≤ fire; clean15/stop5/dead_money are outputs | **OK** |
| 11 | **Fully-observed guard** — W6-B stats use only fires with a complete forward window (blocked-eval subset); the naive/honest/eval populations are reported separately (§1/§5) | **OK** |

**Leak audit: clean.** errors=0 on all three panel runs; the selftest completedness/anti-repaint block
passes pre-panel; the population is grid-identical to the live blocker.

---

## 7. Promotions (per §2 rules; ties → simpler leg)

**Promotions to a wave-7 gate candidate: NONE.** The prereg promotion rule requires favorable − unfavorable
≥ **+5pp** clean15 with n ≥ 300/side, stop5 not worse > 2pp, sign-stable on both time & ticker halves,
≥ 25 distinct 63d blocks. Applying it verbatim to `W6B_promotions.features` on all three panels:

- Every single feature (F1, F3, F5, F6, F7, F8) has `PROMOTE=false` on stocks, baskets, and HK.
- Both composites (C-SHALLOW, C-LOCKOUT) have `PROMOTE=false` on all three panels.
- The closest-to-directionally-right leg is **F7 weekly-turn** (fav side better on all 3 panels,
  +1.47 / +1.55 / +2.78pp, stop not worse, sign-stable) — but it is **~3.5pp short of the +5pp bar**,
  so it does not promote. Under the tie-to-simpler rule it would be the leg to carry forward IF a
  future wave lowers the bar, but this wave promotes nothing.
- F1-shallow, F5, F8, C-SHALLOW, C-LOCKOUT are *negative* on the decisive US panels (favorable side
  WORSE) — falsifications, not near-misses.

**The only object that ships this wave is G6a** (the donor-unwind context chip, §2), display-only, the
family's single accounted statistical ship.

---

## 8. Honest caveats

1. **G6a is US-only; the donor mechanism INVERTS on HK.** The cracking-vs-intact clean15 gap is
   +5.96/+5.81pp on stocks/baskets but **−3.78pp on HK** (sign-stable wrong-way across every HK split).
   The chip must ship US-only and the forward ledger must not read the US pass as market-general. This
   is the same HK-cohort-non-discrimination failure recorded in the wave-3 ledger.

2. **The owner's shallow-dip thesis (F1/C-SHALLOW) is falsified at the fire bar.** Shallow dips have
   *lower* clean15 and *higher* stop5 than deep declines on every panel (F1 −9.91/−6.29/−5.88pp). The
   owner's live intuition (KO worked, +15.8%) is a real anecdote — C-SHALLOW opened for it — but as a
   population feature the shallow side is the losing side. The prereg's corrected object-model warning
   (early knife ≈ shallow dip at the fire bar) is confirmed: no bar-t feature cleanly separates them.

3. **C-LOCKOUT's value is serial capital-preservation, not per-fire clean15.** The ratchet is a strict
   subset (Tencent fixture: ≤1 admit, 100% shut from onset) that prevents fires 2..N of a knife, but
   the admitted set is not a higher-clean15 set than the fires it prunes (stocks/HK −6.87/−6.14pp) —
   because it prunes the later deep fires, which per F1 are the *higher*-clean15 ones. The promotion
   rule measures per-fire clean15, which is the wrong axis for what the ratchet does; its real payoff
   (avoided serial losses) is untested here and would need a serial-P&L gate in a future wave.

4. **F4 dwell has no promotable knee.** On a smooth run-length distribution the clean15 curve is
   non-monotone (rises dwell 3→6, reverses at 7) with tiny per-dwell n past ~5 — no cut survives.
   Amendment #14/#18 (dwell bands are arbitrary) is confirmed empirically.

5. **The bear_ctx confound is real and was correctly demoted.** F8's headline −14pp deep gap is a
   fixed-barrier vol artifact (the bear_ctx cell has stop5 22.16 vs 44.85 — it simply stops out less
   in a persistent bear because barriers are absolute). Inside ¬bear_ctx every single feature collapses
   to the wrong sign or noise (§3.3) — the finding-9 payload: no feature has a clean bear-context-free
   selection. Any wave-7 gate on these features MUST vol-match (ATR co-primary) before reading a sign.

6. **Survivorship + effective-n.** The deep panel is surviving-names (212 with ≥1,500 bars); delisted
   names absent, so absolute clean15/stop5 levels are optimistic. All W6-B comparisons are within-panel
   (fav vs unf on the same blocked fires) so survivorship shifts levels together, not the gap signs.
   Effective n ≪ printed n (overlapping 126d windows); the G6a bootstrap clusters on episodes (159 on
   deep) and the W6-B block floor (≥25 63d blocks) mitigates but does not eliminate this.

7. **W6-C (HOLD tracker) not carried in this statistical report.** Per §6 it is a product decision on
   already-measured objects (`engine/coiled.py` port + stockdata/stock.html surface + grade allowlist),
   owner-gated; it is out of scope for the numbers here and neither promoted nor shipped by this file.

---

## 9. Ledger rows (appended to `DURABLE_BOTTOM_FRAMEWORK.md` §8)

See the appended block in that file. Summary: **G6a SHIPS** (donor context chip, US-only, display-only);
**W6-B promotes NOTHING** (0/8 on every panel; F1/C-SHALLOW falsified, F7 the near-miss at +1.5–2.8pp);
donor edge **inverts on HK**; C-LOCKOUT is a valid strict subset without a per-fire clean15 lift.
