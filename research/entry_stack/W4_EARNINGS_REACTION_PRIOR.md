# W4 — Earnings announcement-reaction prior (M4 re-enable) + expectation-dislocation feasibility

**Date:** 2026-08-05
**Trigger:** external proposal for an "earnings expectation-dislocation engine" (PEAD successor:
numeric surprise + expectation positioning + market reaction + call-text features).
**Status:** phase-0 measurement + M4 slot closed. **Display-tier. No promotion, no gate, no rank.**

---

## §0 Verdict

| Question | Answer |
|---|---|
| Is the proposed engine buildable here as specified? | **No** — roughly half its feature list has no data path in this repo (table §2). |
| Is the *substrate* real? | **Yes.** 98,975 Item-2.02 announcements, 1,314 names, 2004-08..2026-07, each with an SEC acceptance timestamp, so day-0 is exact. |
| Does the reaction leg alone carry drift? | **A short-horizon effect exists and is earnings-specific (placebo-clean at 5d), but it does not survive the wider universe, the post-2016 era split, or multiplicity correction.** |
| Shipped | `earnings` event-prior slot re-enabled with real numbers — a **printed null**, replacing a "cannot measure this" placeholder. |
| Recommendation | Do **not** build the 10-output engine. The reaction leg is display-tier context. Any real edge would have to come from the expectation/text legs, which need data we do not have (§5). |

The proposal's own core claim — that classic EPS-surprise PEAD has decayed and that the
residual lives in text and in the reaction, not in the beat/miss number — is **consistent with
what this panel shows**. Where it overreaches is in assuming the expectation side is available.

---

## §1 What already exists (the proposal is ~60% already-built or already-answered)

| Proposal component | Status here |
|---|---|
| Earnings calendar / blackout | `engine/earnings_blackout.py` — the one earnings authority in the pick chain (S-EV, W1). |
| Announcement dates, PIT | `data/edgar/earnings_8k_dates.parquet` (`collectors/edgar_earnings_8k.py`). Built 2026-07-05, passed its coverage gate (1,143 names ≥8y). |
| Call-text extraction (LLM) | `engine/earnings_qual.py` (2,937 lines) — sentiment, tone, tags, evidence highlights, trading-verb post-filter, `is_context_only: true`. Already does what the proposal's "text" section asks, under stricter epistemics. |
| Transcript intake | `engine/earnings_transcript_intake.py` + `engine/earnings_narrative/`. |
| Guidance language | `engine/guidance_gap.py` — 8-K raise/cut phrases, theme-level, display-only. |
| Post-earnings move (display) | `engine/earnings_catalyst.py` W4. |
| Analyst revision momentum | `engine/analyst_revisions.py` — **code exists, feedstock is DARK** (§4). |
| Numeric surprise history | Thin: `data/earnings/earnings.parquet` carries a trailing-4-quarter Nasdaq snapshot for **231 of 1,958** tickers, overwritten each sweep — no accrual, unusable as history. |

The proposal reads as if none of this exists. Most of it does.

## §2 Feasibility of the proposed feature list

| Feature group | Verdict | Why |
|---|---|---|
| Announcement gap vs expected move | **NO** | `data/stocks/*` carries close/high/low/volume — **no open**. The gap is not computable. |
| Pre-earnings options expected move, skew change | **NO** | `data/options_surface/` is index/sector/industry **ETFs only**. No single-name surface. |
| Consensus revisions, breadth, acceleration, dispersion | **NO** | `collectors/finnhub_altdata.py` is **failed** (§4); no other estimates vendor. |
| Revenue / gross-margin / operating-margin / FCF / segment surprise | **NO** | We hold *actual* EPS (`eps_quarterly.parquet`, XBRL) but **no consensus for any line**, so no surprise is computable. |
| Guidance midpoint change, guidance vs consensus | **PARTIAL** | Direction only (`guidance_gap.py`, phrase-matched, theme-level). No midpoint, no consensus to compare against. |
| Prior-quarter surprise persistence | **PARTIAL** | 231 tickers × ≤4 quarters. Below any usable floor. |
| Announcement residual return, abnormal volume, close location, VWAP-hold, peer confirmation | **YES** | Fully buildable from stores we own (VWAP-hold needs intraday; close-location is the daily proxy). |
| Drift 5/20/60d | **YES** | Measured below. |
| Call-text features (confidence, evasiveness, novelty…) | **PARTIAL** | Extraction machinery exists; a *historical* transcript corpus deep enough to train on does not. |

**Consequence:** "expectation gap" — the proposal's central quantity — is the one thing we
cannot compute. What remains is a reaction-and-drift study. That is what was measured.

## §3 The measurement

Pre-registered before any result was computed (design, endpoint, kill conditions, era split,
inference all fixed in advance).

**Panel.** Item-2.02 events ∩ deep split-adjusted closes → **16,128 events / 200 tickers /
2004-09..2026-05**. Day-0 from the acceptance timestamp in ET: pre-open 8,402 · after-close
5,949 (priced by the *next* session) · intraday 1,777. Both close stores agree to 0.000000
relative error on the overlap, so the deep splice cannot manufacture a return at the seam.

**Reaction metric** `r0z` = day-0 excess return vs SPY ÷ trailing-60d daily vol ending day0−1
— the reaction in units of the name's own normal move. This is the free stand-in for the
options-implied expected move we do not have. Known at the day-0 close; the forward window
starts at that same close, so it is not inside the measured return.

**A. Decile spread, deep panel, date-clustered bootstrap (B=5,000):**

| horizon | top−bottom decile | 95% CI | |
|---|---|---|---|
| 5d | **+0.593%** | [+0.286, +0.903] | excludes 0 |
| 20d | **+0.768%** | [+0.238, +1.316] | excludes 0 |
| 60d | **+1.248%** | [+0.334, +2.249] | excludes 0 |

Spearman(decile, fwd20) = 0.62. On its own this looks like a result. It is not, for two reasons.

**B. Levels are survivor-contaminated.** All-event mean fwd60 = **+1.130%** [+0.915, +1.347] —
the 200 names are *current* index members, so the whole panel drifts up. Any statement of the
form "the strong-up bucket returns +1.6% over 60 days" is mostly this. **Only differences are
readable.**

**C. Placebo — the decisive test.** Same construction on matched non-earnings days (same
tickers, same counts, ±3 sessions around any 8-K excluded):

| horizon | placebo spread | earnings spread |
|---|---|---|
| 5d | −0.113% [−0.413, +0.150] ns | **+0.593%** [+0.286, +0.903] |
| 20d | +0.071% [−0.499, +0.585] ns | **+0.768%** [+0.238, +1.316] |
| 60d | +0.281% [−0.805, +1.204] ns | **+1.248%** [+0.334, +2.249] |

The construction produces nothing on ordinary days. **The effect is earnings-specific, not
generic short-horizon momentum.** That is a genuine pass, and it is the strongest thing in this
report.

**D. Earnings minus matched placebo, by extreme decile** — the survivor-free estimand:

| | 5d | 20d | 60d |
|---|---|---|---|
| decile 9 (strongest up) | **+0.364%** [+0.080, +0.646] | +0.190% ns | +0.429% ns |
| decile 0 (strongest down) | **−0.355%** [−0.639, −0.067] | −0.422% ns | −0.627% ns |

**The effect is ~±0.36% at five days and symmetric.** Everything at 20 and 60 days is survivor
drift. An earlier read of the *levels* suggested "the up arm works, the down arm doesn't" — that
was an artifact of measuring against zero instead of against the baseline, and it reversed once
differenced. Recorded because it is the exact trap this panel sets.

**E. Era split (pre-registered).** Top−bottom fwd20 by era:

| era | n | top−bot | 95% CI |
|---|---|---|---|
| 2004-2011 | 4,911 | +0.825% | [−0.035, +1.748] ns |
| 2012-2015 | 2,929 | **+1.564%** | [+0.544, +2.502] |
| 2016-2019 | 2,995 | +0.753% | [−0.213, +1.973] ns |
| 2020-2022 | 2,416 | −0.450% | [−2.580, +1.630] ns |
| 2023-2026 | 2,877 | +0.529% | [−0.922, +2.009] ns |

**Pooled significance is carried by one era.** Differenced against the placebo, the band spread
is positive in 2004-2015 and ~zero-to-negative from 2016 on. Per the prereg this is reported as
**DECAYED, not as a win** — and it independently reproduces the literature the proposal cites.

**F. The house harness (wide panel, date-episode aggregation, BH-FDR + DSR).** Feeding the
27,158 events through `backtest_event_priors`: only `reaction_strong_down` shows |t|>2 at all
three horizons (−0.221/−0.375/−0.736%, t = −2.28/−2.02/−2.29, split-half sign-stable). But
**BH-FDR rejects nothing (all q > 0.10) and DSR = 0.0.** The gap versus (A) is *universe and
era*, not aggregation: on the 200-name deep panel, episode-aggregation gives a *larger*
strong-up mean (+0.339% vs +0.257%), so the wide panel — which is mostly 2023-2026 for the
~2,100 breadth-only names — is simply sampling the era where the effect is gone.

**G. Tradeability, before costs.** spread/sd = 0.141 (5d), hit-rate 54.4%, ~74 events/yr per
decile. A two-legged 0.58% gross 5-day spread at that hit rate is thin before any spread or
slippage, on a panel that is survivor-biased in its favour.

## §4 Defect found while mapping (independent of the proposal)

`collectors/finnhub_altdata.py` is **failed** in `data/run_status.json`:
`"no rows from 120 tickers (errors=120)"` (probed 2026-08-02). It writes
`data/finnhub/recommendation.parquet`, which **has never existed** in git history.

Seven consumers read it and every one fails open to null:
`scripts/build_leader_radar.py`, `engine/altdata.py`, `engine/stock_fundamentals.py`,
`engine/eightk_magnitude.py`, `engine/moat_falsifiers.py`,
`engine/neuralweb/theme_asymmetry.py`, plus two `config/synapse.yml` artifacts.

So the entire analyst-revision layer is dark, silently. This is also exactly the "expectation
positioning" leg the proposal depends on. **Not fixed in this PR** (different lane, needs a key
diagnosis); filed so it is not lost.

## §5 What shipped, and what would move the needle

**Shipped (this PR).** M4 re-enabled in `scripts/backtest_event_priors.py`. The gate was correct
and named its own unblock — "re-enable once EDGAR 8-K timestamps are wired" — and that store has
existed since 2026-07-05 without anyone closing the loop. `eps_quarterly.asof_date` remains a
synthetic period_end+60d placeholder and is **still not read** (pinned by test). Day-0 from the
acceptance time; subtypes are reaction bands, because every name reports every quarter and an
unconditional earnings prior is ~a market average (`_pooled` t = 1.26, confirming it). The slot
now prints measured numbers with CIs and an honest null instead of "we cannot measure this".

**Would actually change the verdict, in order of value:**
1. **A consensus-estimate history** (EPS + revenue + guidance, point-in-time). This is the
   binding constraint — without it there is no "expectation" in expectation-dislocation.
2. **Single-name option surfaces** → a real expected move, replacing the `r0z` proxy.
3. **Intraday or open prices** → the announcement *gap*, which is the cleanest reaction metric
   and is currently uncomputable.
4. Fixing `finnhub_altdata` (§4) — cheapest of the four, and it lights up a layer already wired.

Until at least (1), an "expectation-dislocation engine" here would be a reaction-momentum model
wearing an earnings label — and §3C/§3E say that model has been decaying since 2016.
