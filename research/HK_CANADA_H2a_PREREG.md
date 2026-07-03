# H2a — SFC Reportable Short Positions — PRE-REGISTRATION

**Battery:** H2a (HK & Canada masterplan §3, trial ledger §6.1 row H2a).
**Grade:** EDGE-STACK candidate (ranks names, per tier). DSR ≥ 0.90 is the door.
**Pre-registered by:** quant research agent. **Committed BEFORE any analysis run** —
the commit timestamp is the audit trail. Nothing below is wired into any live engine,
board, or card (masterplan W3 acceptance: reports only). **NO WIRING.**

---

## 0. One-sentence thesis

Names carrying **high reportable-short pressure** (a large short book relative to their
own recent liquidity) **underperform** the HSI over the following month, and names whose
short pressure is **rising** (positive 4-week change) underperform names whose short
pressure is **falling** (short covering) — consistent with the short-constraint /
short-interest literature (Chang, Cheng & Yu 2007, on the HK/China short-sale
regime: shortable names with heavy or rising short demand earn lower subsequent
returns; covering after a washout precedes bounces).

This is a **name-ranking (alpha) claim** measured as a cross-sectional signal, with the
forward window starting **T+7 calendar days after the SFC position date** — the real
SFC publication lag — so the test only credits edge that survives being 7 days stale
(red-team §3.1a: a 4w-forward test on a signal already 7 days old overstates tradable
edge; this pre-registration removes that overstatement by construction).

---

## 1. Data reality (exact sources, ranges verified pre-reg)

| Series | Store / path | Range / shape verified | Role |
|---|---|---|---|
| SFC reportable short positions | `data/hk_shorts/positions.parquet` | 499,791 rows · 721 weekly dates 2012-08-31 → 2026-06-26 · cols `date, stock_code, ticker, stock_name, shorted_shares, value_hkd` | signal source |
| SFC coverage stamp | `data/hk_shorts/coverage.json` | `our_universe=157, covered=153, coverage_pct=97.5, h2a_eligible=true` | coverage gate input |
| HK price panel (core) | `data/hk_stocks/<ticker>.parquet` (157 files, idx `Date`, cols `close,high,low,volume,open`) | 2000→2026-07-03 | forward returns + ADV normalization |
| HK price panel (ext) | `data/hk_stocks_ext/<ticker>.parquet` (388 files) | present-local, deeper universe | universe expansion where present |
| HSI index close | `data/hk/_HSI.parquet` (idx `Date`, col `close`) | 1986-12-31 → 2026-07-03 | excess-return benchmark |

**SFC publishes shares + value ONLY — no `pct_issued` (slice-F deviation, stated).**
The SFC weekly file carries `shorted_shares` and `value_hkd`; it does **not** carry
short-interest-as-percent-of-issued. The normalization must therefore be **derived**
(§2). Two candidate normalizations were considered; exactly one is PRIMARY (§2).

**Coverage, quantified against our panel (verified pre-reg, not asserted):**
- All **157/157** core `hk_stocks` names appear in the SFC weekly file (a direct
  join of the SFC `ticker` set against the 157 core price files returns 157). The
  `coverage.json` figure of 153 reflects a stricter as-of-latest-date intersection;
  the *union over all 721 weeks* is the backtest-relevant number and it is 157.
- Union of SFC tickers present in *either* core or ext price panel: **536 names**.
- Per covered core name, **median 484 weekly observations** (min 13, max 721) — deep
  own-history, ample for the own-history-percentile construction in §2.
- **Coverage gate (masterplan §3 H2a): ≥ 60 names required or it is a context chip
  only.** Realized coverage is 157 core (536 union) ≫ 60 → **H2a runs as a
  decision-grade ranker, not a context chip.** Gate PASSES pre-reg.

**Large-cap-skew quantification (masterplan-required; SFC ≥0.02%-of-issued threshold
biases toward large names).** Proxy for size = trailing-21d ADV in HKD on the covered
core panel (verified pre-reg): median 21d ADV = **HKD 263M**; ADV terciles at
**HKD 139M / 504M**. The covered panel is genuinely liquid/large-cap-tilted (a
263M-HKD-median-ADV name is not a microcap). This is a **stated survivorship + size
bound**, not a hidden confound: the H2a verdict is a claim about the **large/liquid
end** of HK, where the ≥0.02% reporting threshold actually observes shorts. Any GO is
labeled "large/liquid-cap universe only." The small-cap short-crowding mechanism is
H4's territory, not H2a's, and this is pre-registered so the skew is a decision, not an
omission.

---

## 2. Normalization (the slice-F deviation resolved — PRIMARY pre-registered)

SFC gives shares + value but not percent-of-issued. Two normalizations were on the
table; **exactly one is PRIMARY**, chosen before any return is looked at:

- **PRIMARY — days-to-cover (short-turnover):**
  `dtc_{i,t} = shorted_shares_{i,t} / ADV_shares_{i,t}`, where
  `ADV_shares_{i,t}` = trailing **63-trading-day** mean of the price-panel `volume`
  for name *i* as of the last trading day **≤ position date t**.
  **One-line justification:** both legs come from data we hold *completely and cleanly*
  for all 157 names (SFC `shorted_shares` + price-panel `volume`); it requires **no
  shares-outstanding series** (HK fundamentals has only 75 names and no
  shares-outstanding column — the market-cap normalization is *not* cleanly available,
  verified pre-reg), and days-to-cover is the canonical short-crowding / short-squeeze
  pressure metric (short book measured in days of normal liquidity needed to unwind).

- **SECONDARY (labeled) — short-value share of dollar-liquidity:**
  `svl_{i,t} = value_hkd_{i,t} / (ADV_hkd_{i,t} × 63)`, where
  `ADV_hkd_{i,t}` = trailing-63d mean of `close × volume`. This is the dollar-analog
  of days-to-cover using the SFC `value_hkd` leg directly. Reported as a robustness
  cross-check; it is the *other* normalization the prompt named, kept explicitly so the
  choice of PRIMARY is auditable. It is **not** a separately-FDR-counted decision
  trial beyond the two trials in §4 — it is the same two trials recomputed on `svl`
  and reported as a fragility check (a PRIMARY trial flipping sign under `svl`
  downgrades the verdict one notch).

**Why not market-cap normalization:** `value_hkd / (close × shares_outstanding)` is the
textbook short-interest ratio, but `shares_outstanding` is unavailable for our panel
(fundamentals: 75 names, no shares column). Deriving it from `value_hkd / shorted_shares`
only recovers the *price* (≈ close), not shares outstanding. Rather than impute a noisy
shares-outstanding series, the PRIMARY uses the liquidity-normalized form, which is
both cleaner and the more standard short-*pressure* construct. Stated, not hidden.

**Non-stationarity control:** raw `dtc` levels drift with structural changes in HK
turnover over 14 years, so the ranking signal is the **own-history percentile** of
`dtc` within a trailing **104-week (≈2y) window ending at t** (no look-ahead; the
window closes at t). This mirrors the H5 own-history-percentile discipline and removes
the obvious "turnover regime drift" confound the red-team would raise. A name needs
≥ 52 prior weekly obs in the window to receive a percentile (else NaN that week).

---

## 3. Universe, panel, and fills

- **Universe (PIT-honest bound):** covered names ∩ price panel =
  `hk_stocks` (157 core) ∪ `hk_stocks_ext` (present-local) that also appear in the SFC
  file for the week in question. The signal percentile requires ≥52 prior weekly obs,
  so a name enters the cross-section only once it has ≥1y of SFC history — this is a
  natural PIT filter (no name is ranked before it has been observed long enough).
- **Weekly cross-sections:** one per SFC date, 2013→ (the first ~1y of dates is
  consumed building each name's percentile window). Expect **~660–700** usable weekly
  cross-sections (721 dates − ~52 warm-up weeks).
- **Forward target — excess vs _HSI, T+7-lag-honest:** for each position date `t`,
  the forward window **starts at the first HK trading day ≥ t + 7 calendar days**
  (the SFC publication lag) and runs **4 weeks (21 trading days)** to a
  window-end trading day. Forward *excess* return =
  `name total return over window − HSI price return over the same window`.
  The HK price-panel `close` is dividend-adjusted total return (per house note
  `yahoo close is total return`); HSI `close` is index price return — so
  name−HSI slightly over-credits dividends. This is a **known, stated** small
  positive bias on the *level* of excess returns; it is common to every name each
  week and so does **not** bias the *cross-sectional* long−short spread that the
  verdict rests on (it cancels in the LS difference). Noted, not hidden.
- **Suspension / halt rule (mandatory per masterplan §2):** forward returns are built
  on **actual traded closes only**. A name is dropped from a week's cross-section if
  (a) it has no traded close within ±3 trading days of the window-start date (halted
  at entry), or (b) fewer than 15 of the 21 forward trading days have a real traded
  close (halted mid-window) — **no forward-fill through halts**. Dropped names are
  counted and reported per week; a week with < 20 valid names is dropped entirely.
- **ADV / volume staleness:** the trailing-63d volume mean uses only real traded bars;
  a name with < 21 real volume bars in the trailing 63d window gets NaN ADV that week
  (no normalization possible → dropped that week).

**Survivorship bound (stamped, not stickered).** The price panel is a
current-constituent panel (delisted HK names are absent), so a raw backtest is
survivorship-optimistic. Bound: recompute the PRIMARY LS spread with a **worst-case
delisted-name imputation** — any name that *exits* the SFC file for ≥ 8 consecutive
weeks after appearing in the top short-pressure quintile is assigned a **−40% forward
excess** at its last-observed short-pressure rank (a stylized "shorted-into-delisting"
outcome). Report both the raw and worst-case-imputed LS spreads. If the sign holds
under the worst-case imputation, the survivorship exposure is bounded and stated; if it
flips, the raw GO is downgraded to ACCRUE. (The imputation deliberately *helps* the
short thesis, so it is a conservative test of whether survivorship is *masking* rather
than *manufacturing* the edge — stated.)

---

## 4. Pre-registered trials (exactly 2 decision trials) + expected sign PER trial

Within-family multiple testing controlled by **BH-FDR at α = 0.10** across the 2
trials. Program-level DSR uses **`n_trials = 30`** (masterplan §6 program budget,
registered in the trial-budget ledger #1071).

**TRIAL 1 — LEVEL (own-history percentile of days-to-cover).**
Signal `s1_{i,t}` = 104-week own-history percentile of `dtc_{i,t}` (§2), range [0,1].
Cross-sectional rank-IC of `s1` vs the T+7-lagged 4w forward excess return, per week;
and a top-quintile-minus-bottom-quintile (Q5−Q1) forward-excess **long−short spread**
where **Q5 = highest short pressure**.
- **Pre-registered expected sign:** **NEGATIVE.** High own-history short pressure →
  *lower* forward excess return ⇒ rank-IC < 0 and (Q5−Q1) < 0. The tradable construct
  is the **short leg** (a −signal long-book: buy Q1 / low-short-pressure, avoid/short
  Q5). A **positive** significant IC is a WRONG-SIGN result ⇒ **NO-GO**, not a flipped
  GO (masterplan direction discipline).

**TRIAL 2 — Δ4w (4-week change in short pressure).**
Signal `s2_{i,t}` = `dtc_pctile_{i,t} − dtc_pctile_{i,t−4w}` (change in the own-history
percentile over 4 weeks; percentile-space so it is comparable across names). Same
rank-IC and Q5−Q1 machinery, **Q5 = most-rising short pressure**.
- **Pre-registered expected sign:** **NEGATIVE.** *Rising* short pressure (short
  sellers piling in) → lower forward excess; *falling* short pressure (covering /
  washout) → higher forward excess (the covering-precedes-bounce leg). ⇒ rank-IC < 0,
  (Q5−Q1) < 0. A **positive** significant result ⇒ **NO-GO** (wrong sign), not a GO.

**Robustness variants (reported, NOT decision trials, NOT FDR-counted):**
R1 — both trials recomputed on the SECONDARY `svl` (dollar-liquidity) normalization
(fragility of the normalization choice). R2 — forward horizon 8w (42 td) instead of 4w
(is the decay faster/slower than the disclosure lag). R3 — window-percentile lookback
52w vs 156w (fragility of the 104w choice). A decision trial flipping sign under
R1–R3 downgrades its verdict one notch.

---

## 5. Pre-registered GO / NO-GO / KILL / ACCRUE gates

Evaluated **per trial** (Trial 1 and Trial 2 each get their own verdict), on the
PRIMARY `dtc` normalization. All statistics are on the **short-leg-consistent** sign:
the pre-registered direction is NEGATIVE, so a GO requires the *negative* sign to be
significant.

| Verdict | Condition (ALL sub-conditions must hold) |
|---|---|
| **GO** | (1) **Sign correct**: mean rank-IC < 0 AND (Q5−Q1) forward-excess < 0 (the pre-registered short-side direction). (2) **HAC-t**: Newey-West t-stat on the per-week (Q5−Q1) spread series ≥ **2.0** in magnitude (lags = 3, the 4-week overlap) — i.e. the *negative* spread is significant. (3) **BH-FDR**: the trial's two-sided p survives BH at α=0.10 within the 2-trial family. (4) **DSR ≥ 0.90**: `deflated_sharpe` on the daily (Q5−Q1) or −IC long-short return series, `n_trials = 30`, `t_eff` from `bootstrap_effective_t`, clears 0.90. (5) **split-half sign stability**: the (Q5−Q1) sign agrees (both negative) in BOTH halves of 2013→2026 split at the median week. (6) **effective-N**: `bootstrap_effective_t` t_eff ≥ 60 independent-equivalent obs on the LS daily series. (7) **survivorship bound holds**: the worst-case-imputed LS spread (§3) keeps the negative sign. |
| **ACCRUE** | Sign correct (1) AND HAC-t ≥ 1.5 but < 2.0, OR DSR in [0.80,0.90), OR split-half sign flips in one half, OR the survivorship-imputed sign weakens toward zero without flipping. i.e. right sign, right shape, power or robustness just short of the decision bar → re-run with a longer window / after H4's expanded-universe collector lands. |
| **NO-GO** | Sign is FLAT (|mean IC| < 0.01 and Q5−Q1 not distinguishable from 0 at HAC-t < 1.5), OR the correct-sign result fails FDR AND DSR < 0.80. The signal has no usable edge on this panel. |
| **WRONG-SIGN NO-GO** | The result is **significant with the OPPOSITE (positive) sign** (HAC-t ≥ 2.0 that high short pressure / rising short pressure *out*performs). Per masterplan direction discipline this is **NO-GO, explicitly NOT a flipped GO** — the literature thesis is not confirmed and we do not resurrect it by relabeling. |
| **KILL** | Wrong-sign result that is *also* DSR ≥ 0.90 (a robust reverse edge) — recorded as KILL so the thesis is not re-tested, but still **not wired** (a reverse-sign result is not a tradable long of high-short names without its own pre-registration). |

**Program DSR gate is the only door into a scored seam.** A trial that clears gates
1–3 + 5–7 but has DSR < 0.90 is **ACCRUE**, never GO (masterplan §6: "DSR ≥ 0.90 the
only door into scored seams"). Expected honest prior (§8) says at least the LEVEL trial
has a real shot at GO given the decision-grade n; Δ4w is the more fragile of the two.

---

## 6. Fill / lookahead discipline (restated, binding)

- Signal on week `t` uses SFC data disclosed *at or before* `t` and price/volume
  through the last trading day ≤ `t`. Own-history percentile window closes at `t`.
- Forward window **starts at the first HK trading day ≥ t + 7 calendar days** (SFC
  publication lag) and ends 21 trading days later. **No entry before T+7** — this is
  the load-bearing lag-honesty; a version with T+0 fills is computed ONLY as a
  labeled "lag cost" diagnostic (how much edge the 7-day lag eats), never as a
  decision trial.
- HAC (Newey-West, lags = 3) on the weekly (Q5−Q1) spread series for the
  4w-overlap serial correlation; `bootstrap_effective_t` on the daily LS series for
  the independent-N cross-check; the binding effective-N is the smaller.

---

## 7. Deliverable beyond the report

A JSON/py constants block in the report defining the frozen signal spec a future W4
ranker *would* consume IF a trial goes GO: normalization formula (days-to-cover),
percentile lookback (104w), the T+7 lag, quintile construction, suspension rule, and
the realized per-trial IC / spread / HAC-t / DSR. **NO WIRING** — the block is a spec,
not an import. If both trials are NO-GO/ACCRUE the block records that outcome as the
finding (a planned branch, not a failure).

---

## 8. Honest prior (pre-committed, before running)

Decision-grade n: ~660–700 weekly cross-sections, ~13.5 years, multiple HK regimes
(2015 A-share bubble/crash, 2018 trade war, 2019 unrest, 2020 COVID, 2021 IPO boom,
2022 hiking drawdown, 2024–25 re-liquefication). This is one of HK's **best-powered**
batteries (with H-INCL). The short-interest underperformance effect is one of the more
replicated cross-sectional anomalies internationally. **Pre-stated expectation:** the
LEVEL trial has a genuine shot at GO (correct-sign, decision-grade power); the Δ4w
trial is more fragile (change-of-percentile is noisier) and ACCRUE-lean. A NO-GO on
both is a fully respectable, non-embarrassing outcome and is reported as such. The one
result that would be surprising and is pre-registered as NON-confirming is a **wrong
(positive) sign** — that is NO-GO, not a pivot.

---

## 9. "What this does NOT show" (pre-committed)

- Does NOT show a small-cap short-crowding edge — the SFC ≥0.02% threshold observes
  shorts mostly on **large/liquid** names (median covered-name ADV HKD 263M); any GO is
  labeled large/liquid-cap-only and does **not** generalize to the microcap universe
  (that is H4's domain).
- Does NOT show tradable edge net of the SFC publication lag beyond the pre-registered
  T+7; a shorter real-world data latency (if SFC ever tightened it) is untested.
- Does NOT establish a *long* strategy in high-short names even under a KILL — a
  reverse-sign result is recorded, not traded, and would need its own pre-registration.
- Does NOT establish causality (short pressure → returns); short interest is a
  coincident sentiment/constraint proxy and reverse causality (falling prices *attract*
  shorts) and common-driver confounds are NOT ruled out and are stated.
- Does NOT survivorship-clean the panel — it *bounds* survivorship via a worst-case
  delisted-name imputation (§3); the bound is reported, the panel is not reconstructed.
- Does NOT conflate with **H2b (sstoday short-sell TURNOVER)** — that is a different
  quantity (daily flow, not a position), accrue-forward only, and is **not** in this
  battery (red-team §3.1b: non-substitutable).

---

## 10. Trial accounting (for the DSR n_trials audit trail)

Decision trials in THIS battery: **2** (LEVEL, Δ4w). Robustness variants R1–R3: 3
(reported, not decision, not FDR-counted). SECONDARY `svl` normalization: a fragility
recompute of the same 2 trials, not a new decision trial. T+0 "lag-cost" diagnostic:
labeled, non-decision. Program-level DSR `n_trials = 30` (masterplan §6 — every config
across both markets, registered #1071). BH-FDR applied within the 2-trial H2a family at
α = 0.10.

---

## 11. Store-commit decision (masterplan PART 1)

`data/hk_shorts/positions.parquet` is **5.8 MB** (verified `du -h`), well under the
20 MB house R2 threshold. Per house rules the R2 data-plane pattern is for *heavy*
per-ticker append-only stores; a single 5.8 MB weekly panel is small and slow-growing
(one ~4k-row slice per week). **Decision: commit the full store to git** (positions
parquet + coverage.json). No `.gitignore` / `publish_r2 --dirs` / `audit_r2` anchor is
required at this size. Stated as a decision, not an omission (red-team §148 flagged R2
as an *option* for append-only backfills "only small, slow-changing artifacts stay in
git" — a 5.8 MB weekly panel is exactly that small, slow-changing artifact).
