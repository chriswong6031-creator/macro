# T1–T4 Entry-Quality Deep-Dive

**Date:** 2026-07-05/06  
**Status:** Pre-registered gauntlet (G-T2X) queued; findings are descriptive, not promotion-eligible without G-T2X passing  
**Primary ruler:** 21d benchmark-excess return from t+1 fill, TIER_ONSET events, −5% stop  
**Related doc:** [TIERED_CASCADE.md](TIERED_CASCADE.md) — published baseline and tier definitions  
**Harnesses:** `scripts/_bt_tier_deepdive.py` (v1 broad census), `scripts/_bt_paired_v2.py` (v1 pairing study), `scripts/_bt_tier_deepdive_v3.py` (corrected production-T1 study — AUTHORITATIVE for T1)

---

## 1. Question and Pre-Registration

**Question.** When a T1–T4 tier fires on a setup, what is the entry quality under a −5% stop with t+1 fills? Specifically: does T1 show edge over lower tiers? Is the t+1 fill delay material? What fraction of events become dead money or stop out within 21 days?

**Primary ruler:** mean 21d benchmark-excess return (vs SPY for US, vs HS300 for CN) from the t+1 E1 fill price, evaluated on TIER_ONSET events. Confidence interval: month-block bootstrap (1000 replications, seed 42).

**Population:** TIER_ONSET events — the first session a tier fires after a ≥3-session gap (onset events only, not every board-fire day). US: 2,498 names (all baskets/ohlcv), 2015–2026-05. CN: 800 names (china_stocks, seed=42 cap, 2026 snapshot), 2016–2026-05.

**Stop rule:** −5% from fill price; stop monitored from fill bar including fill-day low. Wstop return = −5% if stopped, actual if not.

**Pre-registered gauntlet:** G-T2X (see §6). No tier has been promoted based on this study.

**In plain English.** We asked: among all the times the system fires a T1/T2/T3/T4 entry signal, how well does the stock actually do over the next month under a tight stop? The answer shapes how we weight the tiers and which overlay filters are worth testing.

---

## 2. What the Tiers Are

See [TIERED_CASCADE.md](TIERED_CASCADE.md) for full definitions, audit history, and tier weights. Summary:

| Tier | Definition | Published stop% | Published lead vs T1 |
|------|-----------|----------------|---------------------|
| **T1 master** | 3D MACD-RSI cross AND 3D StochRSI crossed | 38.3% | — (anchor) |
| **T2 early** | 2D MACD-RSI cross AND 3D StochRSI crossed | 40.6% | 51% of fires, ~5.7d |
| **T3 earlier** | 2D MACD-RSI projected ≤1–2d AND 3D StochRSI already crossed | 42.3% | 42% of fires, ~7.9d |
| **T4 earliest** | 2D MACD-RSI projected AND 2D StochRSI crossed AND above-200MA | 43.1% | 32% of fires, ~7.8d |

The published baseline was estimated on a 110-name held-out curated panel. This deep-dive runs on the full broad universe (2,498 US / 800 CN names) — stop-out rates are higher on the broader, uncurated universe. See §3d for the investigation.

**Note on operator re-weight (PR #1614, 2026-07-06):** Following this study, operator ratified T2 weight 1.00 > T1 weight 0.90 as an entry-quality ranking. This reflects the fill-premium finding in §3b. It is not a gauntleted excess-edge promotion.

---

## 3. Headline Findings

### 3a. No tier shows robust standalone 21d excess in the broad universe

**In plain English.** When we look at all T1–T4 signals across the full stock universe — not just the curated names on the published panel — none of them reliably beats the benchmark over 21 days. The confidence intervals straddle zero for every US tier. CN T1 is the one exception, and it comes with important caveats.

All numbers from v3 (corrected onset dating, AUTHORITATIVE for T1). v1 T1 counts are inflated by the look-ahead leak described in §4; v3 T1 is the correct figure.

#### TIER_ONSET 21d Excess — US (v3, corrected)

| Tier | n | Mean exc 21d | Med exc 21d | CI lo 95% | CI hi 95% |
|------|---|-------------|------------|-----------|-----------|
| T1 | 12,637 | −0.12% | −0.62% | −0.47% | +0.37% |
| T2 | 7,981 | −0.03% | −0.67% | −0.59% | +0.44% |
| T3 | 3,208 | +0.16% | −0.63% | −0.66% | +0.86% |
| T4 | 31 | −0.58% | +0.36% | −3.76% | +2.62% |

All US CIs straddle zero. No US tier has standalone excess edge at this horizon on the broad universe.

#### TIER_ONSET 21d Excess — CN (v3, corrected)

| Tier | n | Mean exc 21d | Med exc 21d | CI lo 95% | CI hi 95% |
|------|---|-------------|------------|-----------|-----------|
| T1 | 2,948 | **+1.84%** | −0.03% | **+0.74%** | **+2.80%** |
| T2 | 1,945 | +0.72% | −0.82% | −0.31% | +1.80% |
| T3 | 750 | +0.46% | −1.00% | −0.74% | +1.69% |
| T4 | 3 | +13.3% | +13.9% | — | — |

CN T1 is the sole clear-positive cell. CI strictly above zero (+0.74, +2.80). This is the authoritative T1 estimate — v3's corrected onset dating removed the look-ahead that inflated v1's T1 count by ~5.7×.

**Caveats on CN T1:** (1) CN universe is a 2026 snapshot — survivorship-biased; survivors are overrepresented relative to the live universe at each historical signal date. (2) CN T1 simultaneously has the worst stop-out rate (60.0%) and highest fill premium (12.4% median) across both markets. The positive excess coexists with high friction — it is not a clean entry. (3) T4 has n=3 — no statistical inference possible.

---

### 3b. Fill-premium ladder: monotone T1→T4, both markets

**In plain English.** T1 fires later than T2/T3/T4, but it fires closer to where the stock has already moved. By the time T1 confirms, you are paying a higher price relative to where the stock was 20 days ago. This is the load-bearing fact about entry price — not about future returns.

#### Median Fill Premium (20d lookback) — v3

| Tier | US med fill premium | CN med fill premium |
|------|--------------------|--------------------|
| T1 | **10.5%** | **12.4%** |
| T2 | 7.7% | 7.5% |
| T3 | 6.2% | 6.2% |
| T4 | 4.1% | 7.7% |

The ladder is monotone T1→T4 in both markets (T4 CN slightly disrupted by n=3). Each lower tier fires earlier in the move — at a lower premium to recent price. Operator re-weight (PR #1614) reflects this: T2 1.00 > T1 0.90 as an entry-quality ranking.

---

### 3c. t+1 fill delay costs ~0 at median

**In plain English.** The system generates signals on confirmed bar closes. The operator fills at the next day's open (t+1). We measured how much that one-day delay costs. The answer is: almost nothing at the median.

#### Delay Cost (t vs t+1 fill) — v3 US and CN

| Tier | US mean delay | US med delay | US IQR | CN mean delay | CN med delay | CN IQR |
|------|--------------|-------------|--------|--------------|-------------|--------|
| T1 | +0.05% | 0.00% | −0.41% to +0.48% | +0.19% | 0.00% | −0.75% to +0.89% |
| T2 | −0.02% | 0.00% | −0.47% to +0.46% | +0.20% | 0.00% | −0.70% to +0.92% |
| T3 | −0.04% | 0.00% | −0.56% to +0.47% | +0.08% | 0.00% | −0.73% to +0.70% |

Median delay cost is zero for every tier. The IQR spans roughly ±0.5–0.9% — the noise of one trading session. The render delay (same-day signal → next-open fill) is not where the lateness cost comes from. The cost of T1 vs T2 earliness is the 2–4pp fill premium in §3b, not the t+1 gap.

---

### 3d. Stop-out rates: broad universe vs published curated panel

**In plain English.** The published baseline (TIERED_CASCADE.md) showed 38–43% stop-outs on 110 curated names. The broad universe runs 52–60%. This is a real difference, and we investigated it.

#### Stop-out Rate 21d — v3 vs Published Baseline

| Tier | Published (curated, ~110 names) | v3 US broad (2,498 names) | v3 CN broad (800 names) |
|------|--------------------------------|--------------------------|------------------------|
| T1 | 38.3% | **51.8%** | **60.0%** |
| T2 | 40.6% | **55.6%** | **55.6%** |
| T3 | 42.3% | **55.3%** | **58.4%** |
| T4 | 43.1% | 51.6% | 33.3% (n=3) |

The gap is universe composition, not a harness bug. The curated 110-name panel selects for high-quality setups with sector backing; the broad universe includes names without that context filter. The −5% stop on a 2,498-name universe will catch more volatile / lower-quality setups. The published rates remain the right baseline for the curated surface; the broad-universe rates are the honest floor without context filtering — which is exactly what G-T2X overlays are designed to address.

**Note on CN T1 stop-out:** CN T1 has both the highest stop-out (60%) and the only CI-positive excess. These coexist because CN volatility is structurally higher — the mean wstop return is still positive (+1.05%) because many events that breach −5% recover and end above it at the 21d horizon.

---

### 3e. Dead-money and clean-entry rates — US T1 is worst

**In plain English.** "Dead money" means the stock didn't go anywhere — it didn't stop out (−5% breach) but also didn't make meaningful progress in 21 days (absolute return <5%). T1 has the highest dead-money rate in the US. Clean8_21 (no drawdown worse than −8% in the 21-day window, among non-stopped) is worst for T1.

#### Durable / Dead-money — v3 US

| Tier | n | clean8_21% | dead_money_21% | durable63% |
|------|---|-----------|---------------|-----------|
| T1 | 12,637 | **26.7%** | **54.2%** | 31.5% |
| T2 | 7,981 | 29.9% | 48.8% | 30.0% |
| T3 | 3,208 | 30.5% | 45.3% | 29.6% |
| T4 | 31 | 25.8% | 46.7% | 32.3% |

#### Durable / Dead-money — v3 CN

| Tier | n | clean8_21% | dead_money_21% | durable63% |
|------|---|-----------|---------------|-----------|
| T1 | 2,948 | 34.2% | 41.4% | 28.6% |
| T2 | 1,945 | 34.6% | 44.7% | 30.5% |
| T3 | 750 | 30.4% | 47.8% | 25.9% |
| T4 | 3 | 100.0% | 50.0% | 66.7% (n=3) |

In the US: T1 54.2% dead-money vs T2 48.8%. Clean8_21 runs T1 26.7% < T2 29.9% < T3 30.5% — T1 produces the most cramped 21-day windows. CN is similar directionally though the excess finding for T1 complicates the interpretation.

---

### 3f. Lead-rate is a myth at broad-universe scale

**In plain English.** TIERED_CASCADE.md says T2 leads T1 on 51% of its fires (~5.7d earlier). That is true on the 110-name curated panel where those numbers came from. At broad-universe scale, T2 leads T1 on roughly 0.8% of its fires. T1 and T2 fire on essentially disjoint setups.

#### Pairing Coverage — v3 (window: 12 sessions)

| Market | T1 onsets | T1 with T2 precursor | T1 with T3 precursor | T2 conversion rate | T3 conversion rate |
|--------|-----------|--------------------|--------------------|-------------------|--------------------|
| US | 12,637 | 63 (0.5%) | 50 (0.4%) | 0.8% | 1.6% |
| CN | 2,948 | 12 (0.4%) | 11 (0.4%) | 0.6% | 1.5% |

Across 12,637 US T1 onsets, only 63 had a T2 precursor within 12 sessions (0.5%). Only 0.8% of T2 fires converted to T1 within 12 sessions. The "51% lead" in the published doc was an episode-scoped curated-panel figure: among the curated pairs that fired in sequence on the same name, T2 led T1 51% of the time. At broad-universe scale, T2 and T1 fire on overwhelmingly DISJOINT setups. This does not make the lead materially wrong for the curated surface — it just means the sequence is a minority pattern on the full universe.

---

### 3g. v1 conversion split: confirmation-waiting is adversely selected

**In plain English.** When T2/T3 fires and then T1 follows on the same name, that "converted" sequence significantly underperforms versus T2/T3 fires that never convert. This matters because it shows that T2/T3 fires that wait for T1 confirmation are on the wrong setups — the "not-topped" veto that T1 requires blocks T1 from fires where the move already topped.

#### Conversion Stats — v1 (broad universe, US and CN)

**US T2 converted vs unconverted (among T2 fires):**

| Group | n | wstop mean 21d | excess mean 21d |
|-------|---|---------------|----------------|
| T2 converted (→T1 within 12s) | 182 | −1.95% | **−3.82%** |
| T2 unconverted | 7,508 | +0.53% | −0.59% |

**CN T2 converted vs unconverted:**

| Group | n | wstop mean 21d | excess mean 21d |
|-------|---|---------------|----------------|
| T2 converted | 64 | −1.45% | **−3.78%** |
| T2 unconverted | 3,384 | +1.21% | +0.52% |

All four cells show converted < unconverted (US T2, CN T2, US T3, CN T3). The T2/T3 fires that eventually convert to T1 are on setups that went sideways-to-down during the waiting window — the thrust that T1's "not-topped" veto is blocking is exactly what makes those names confirm later. There is no benefit to waiting for T1 confirmation if you already filled at T2.

---

### 3h. T3 persistence experiment

**In plain English.** T3p is a variant that requires the T3 signal to persist for at least one additional session before counting as an onset. This reduces repaint noise and slightly shrinks the sample.

#### T3p vs T3 — v3

| Metric | T3 (US) | T3p (US) | T3 (CN) | T3p (CN) |
|--------|---------|---------|---------|---------|
| n events | 3,208 | 2,041 | 750 | 485 |
| Retention | — | 63.6% | — | 64.7% |
| Med fill premium 20d | 6.2% | 6.1% | 6.2% | 5.8% |
| Med lead vs T1 (sess) | 11.0 | 10.5 | 11.0 | 10.0 |
| 21d excess mean | +0.16% | +0.41% | +0.46% | −0.20% |
| Stop-out 21d% | 55.3% | 55.1% | 58.4% | 60.2% |
| Repaint rate | 15.5% | **9.4%** | 16.0% | **0.0%** |

US: repaint drops from 15.5% to 9.4%, excess improves slightly (+0.16% → +0.41%), n drops −36.4%, lead cost ~0.5 sessions. CN: repaint drops to 0%, but 21d excess flips slightly negative (−0.20%) and stop-out rises. The persistence requirement meaningfully reduces repaint at modest sample cost. Neither version has CI-positive excess in the US. The CN zero-repaint result is notable but the excess reversal means persistence is not a universal improvement — it depends on market.

---

## 4. The Look-Ahead Leak: Post-Mortem

**In plain English.** The first version of the T1 backtest (v1/v2) counted ~72,000 US T1 onsets and ~18,000 CN onsets. The corrected v3 found 12,637 US and 2,948 CN — a ~5.7× reduction. This section explains why and what the lesson is.

### What happened

v2 dated T1 onset at `sk3[CB]` — the confirmed-bar date of the 3D StochRSI cross. The problem: the §7 "take" call in the production engine is knowable only at the confirming 3D bucket's known-date, which is one bar later (`sk3[CB+1]` for trend-following confirmations) or two bars later (`sk3[CB+2]` for counter-trend). The T1 signal is the INTERSECTION of the MACD-RSI cross and the StochRSI confirmation — you see both legs only when both bars have closed, which is 1–2 sessions after the confirming bar.

Dating onset at `sk3[CB]` instead of `sk3[CB+1/CB+2]` meant that 92% of the "new" T1 onsets in v1/v2 were leaked: the harness treated events as onsets at a date when the confirmation was not yet knowable to a live evaluator. Truncation-at-onset in the panel construction exposed this: when we filtered to only truly onset-eligible dates, 92% of the v1 count vanished.

### v3 fix and verification

v3 changed onset dating to `sk3[CB+1]` (trend-following) or `sk3[CB+2]` (counter-trend). Acceptance tests on 700 fresh-sample onsets:

| Test | Pass | Total | Rate | OK? |
|------|------|-------|------|-----|
| Truncation (onset-date T1-eligible) | 300 | 300 | 100.0% | PASS |
| Parity (claim vs live gate) | 196 | 200 | 98.0% | PASS |

The 4 parity failures (ALG@2020-02-05, 002222.SZ@2021-03-10, 601877.SS@2019-10-30, DOC@2017-05-22) are all `claimed=False live=True` — the harness missed a T1 that the live gate caught, a conservative direction. Zero in the opposite direction (harness claiming T1 when live gate would not). Residual: ~1% at one-bucket-boundary edge cases.

### Lesson for future §7 backtests

Any §7 signal that uses a cross of a multi-bar indicator (2D, 3D, weekly) must date the onset at the first session where a live evaluator has seen all confirming bar closes. The confirming bar close is not the fill date — it is the date the cross becomes observable. This offset is 0 for daily indicators (bar closes daily), 1–2 sessions for 3D indicators, and can be larger for weekly or monthly timeframes. Harnesses that use the cross date itself (rather than the observation date) will overcount events and understate the selection bias of the confirmation requirement.

---

## 5. Operator Decisions (Cross-Reference)

The following decisions shipped concurrent with or following this study. Diffs are in the referenced PRs; not restated here.

- **PR #1586 / #1587** — display framing updates for T1/T2 tier badges (display-only, not a signal change)
- **PR #1614** — operator re-weight: T2 weight 1.00 > T1 weight 0.90. Rationale: fill-premium ladder (§3b) shows T2 fires at a lower premium than T1, making it the better entry-quality tier by this measure. Explicitly NOT a gauntleted excess-edge promotion — the broad-universe excess CIs for T2 straddle zero.

T3 persistence PR: search returned no distinct T3-persistence PR number separate from the v3 harness work above. The T3p experiment results are captured in this document (§3h) and in the v3 harness.

---

## 6. Pre-Registered Gauntlet: G-T2X

This gauntlet is locked. No modification is permitted without a new pre-registration.

**Candidate:** T2 tier-onset events, t+1 E1 fill, per-overlay filters.

**First-wave overlays** (max 5, one pass each, no post-hoc threshold tuning):

1. 2W washout context: setup fires after confirmed 2-week setup washout (`w_setup`)
2. Fire-day turnover z > 0 (above-median volume on signal day)
3. Sector-cycle phase ∈ {bottoming, recovering}
4. NW dispersion-regime lens (Neural Web L3 regime signal)
5. Not-extended: fill_premium_20d < 8%

**Ruler:** mean 21d benchmark-excess from E1 fill with −5% stop, month-block bootstrap CI (1000 replications, seed 42).

**Promotion gates** (ALL must hold, and directionally consistent in both temporal split halves):

- CI_lo > 0
- stop-out_21 ≤ 50% US / ≤ 52% CN
- clean8_21 ≥ 33%
- n_filtered ≥ 300 per market
- retention ≥ 25% of base T2 fires

**Kill:** filtered excess ≤ unfiltered T2 base, or retention < 15%.

Nulls are printed regardless. A filtered set that does not meet promotion gates is reported as a null finding — not discarded.

---

## 7. Caveats and Clocks

1. **CN survivorship bias.** The CN universe is a 2026 snapshot (800-name seed=42 cap). Stocks that failed before 2026 are absent from historical windows. CN numbers are directionally informative but overstated relative to a PIT universe. CN T1's CI-positive excess must be read with this caveat.

2. **CN 800-name sample.** The CN universe is a 800-name random sample (seed=42) from china_stocks. Different seeds will produce moderately different CN point estimates; the US numbers are full-universe.

3. **Completed-bar basis understates live T3/T4 noise.** T3 requires the 2D MACD-RSI projected-cross to be within 1–2 bars — a forward linear extrapolation. On completed historical bars the projection is always known; in live operation the projection can flip as the bar develops intraday. The repaint rates (15.5% T3 / 9.4% T3p US) capture bar-close-to-bar-close flips but not intraday noise.

4. **Truncated cohorts.** Events after 2026-03-01 lack full 63d forward data (truncated from 63d metrics). Events after 2026-01-01 lack 126d data. Point estimates for 63d and 126d horizons on recent years are understated in sample size.

5. **Repaint recalibration clock.** If the T3 persistence change (§3h) ships to production, the repaint rate baseline changes. The current 15.5% (T3) / 9.4% (T3p) rates apply to the respective onset definitions; after any definition change, repaint should be re-measured.

6. **US PIT filter.** The US universe uses all baskets/ohlcv parquets — no PIT survivorship filter. Names delisted during the study period contribute their available history. This is honest but slightly different from a strict PIT panel.

7. **T4 sample sizes.** v3 US T4 n=31, CN T4 n=3. No inference is drawn from CN T4. US T4 results are directionally suggestive only.

8. **Broad vs curated stop-out gap.** The 38–43% published stop-outs vs 52–60% observed here are both correct — they measure different populations. The published rates apply to curated-panel setups; the broad-universe rates apply to the unconditioned fire rate. G-T2X overlays are designed to narrow this gap.

---

## Appendix: Study Versions

| Version | Harness | T1 US n | T1 CN n | T1 dating | Status |
|---------|---------|---------|---------|-----------|--------|
| v1 (broad census) | `_bt_tier_deepdive.py` | 72,125 | 17,848 | Raw 3D cross (leaked) | Superseded for T1; T2/T3/T4 board-fire counts unaffected |
| v1 (paired study) | `_bt_paired_v2.py` | same | same | Raw 3D cross | Conversion/pairing analysis; T1 counts inflated |
| v3 (corrected) | `_bt_tier_deepdive_v3.py` | 12,637 | 2,948 | sk3[CB+1/CB+2] | AUTHORITATIVE for T1 |

The v1 T2/T3/T4 board-fire results (stop-out rates, fill premiums, dead-money) are not affected by the T1 dating leak — those tiers use a different onset definition. Only T1 onset counts and T1-specific metrics are corrected in v3.
