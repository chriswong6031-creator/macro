# C-BANK Phase-0 Pre-Registration — Bank-Earnings-Season Clustering + PEAD

**Battery:** C-BANK (masterplan §4.1, ledger row §6.1). Branch `hkca-w2-cbank`.
**Status:** PRE-REGISTERED. Committed BEFORE any test was run (commit timestamp is the audit trail).
**Author:** quant research agent, 2026-07-03.

> This file is written and committed as a SEPARATE git commit before `scripts/cbank_phase0.py` is
> executed. No result in this document. Gates, constructions, and trial count are fixed here.

---

## 0. Mechanism (why this is board-relevant)

Red-team finding (research/HK_CANADA_REDTEAM_FINDINGS.md §"missing CA-native mechanism", lines 114-116):
Financials = 22 names ≈ 29% of the Canada board weight, and the big-6 banks report on a tightly
CLUSTERED off-cycle calendar — late Feb / late May / late Aug / early Dec, each cluster spanning
~1 week. The red-team asked for exactly two tests: (a) a bank-earnings-**season window** event study
on the Financials sleeve, and (b) **PEAD** drift on bank beats. This battery runs both. No wiring
(masterplan W2 acceptance = reports only).

**Verified data facts (this session, before any test):**
- `data/canada_earnings/earnings.parquet`: 5 of the big-6 banks present (RY, TD, BMO, BNS, CM);
  **NA.TO is ABSENT** from both the earnings store and the 5y close panel. PEAD leg = **5 banks × 4Q = 20 events max**, thinner than the ledger's "~40-48". Pre-stated: this leg is under-powered; let the gate speak.
- Observed report dates (all 5 banks, 4Q): Feb 24-26, May 27-28, Aug 26-28, Dec 02-04. Fixed-calendar,
  PIT-safe: a ±2w window around a fixed seasonal anchor needs no per-event dates for the DEEP leg.
- `data/canada/XFN.TO.parquet` 2001-03-29→ (6342 rows); `ZEB.TO.parquet` 2010-04-20→ (4063);
  `_GSPTSE.parquet` 1979→ (11802). Cols = close, volume.
- `data/canada_search/closes.parquet` 2021-06-14→2026-06-30 — the 5y name panel for PEAD.

**Dividend-drift confounder (STATED, PHYSICS):** Yahoo `^GSPTSE` close is a **price** index (no
dividends); XFN/ZEB closes are **total-return** (dividend-adjusted, per memory `yahoo-close-is-total-return`).
Financials yield ~3-4%/yr, so RAW XFN−GSPTSE excess is biased +3-4%/yr by dividends alone, independent
of any season effect. The season test is INSIDE-window mean excess vs OUTSIDE-window mean excess — the
constant dividend drift is common to both and **cancels in the difference**. Trial (a) is therefore
specified as a *contrast* (in−out), never raw excess vs zero. Any raw in-window excess vs zero is
reported as descriptive-only and explicitly discounted for this bias.

---

## 1. Hypotheses

- **H-C-BANK-1 (season window):** Inside the ±2w Canadian-bank-earnings-season windows, the Financials
  sleeve (XFN.TO / ZEB.TO) earns MORE excess return over the TSX (_GSPTSE) than outside those windows.
  Directional prior: pre-announcement drift + season risk premium ⇒ in > out. Two-sided test.
- **H-C-BANK-2 (PEAD on beats):** After a bank's quarterly report, the 1-4w forward return of that bank
  (over XFN sleeve, sector-neutral) is HIGHER for beats than for misses. Directional prior: post-
  earnings-announcement drift ⇒ beat−miss > 0. Two-sided test.

---

## 2. Exact constructions

### 2.1 Season windows (fixed seasonal calendar — PIT-safe)
Anchors (fixed, from the observed tight clusters): **Feb-25, May-28, Aug-27, Dec-03** of each year.
A "season window" = anchor ± 14 calendar days (≈ ±10 trading days). Windows are **non-overlapping by
construction** (anchors ~13 weeks apart, windows ~4 weeks wide) — good for effective-N.
- XFN daily excess: `r_xfn − r_gsptse` (log returns of total-return / price closes, next-bar aligned).
- Aggregate to **season-quarter episodes**: for each (year, season) an episode return = the sum of
  daily in-window excess (compounded). "Outside" = all trading days NOT in any window, aggregated to a
  matched set of non-window inter-season blocks (one "off" episode between each pair of anchors).
- **Episode-level test (primary):** in-window episode excess vs off-window episode excess, unpaired
  Welch-style via HAC on the pooled per-episode series (episodes are the independent unit).
- **Daily-level HAC (secondary robustness):** newey_west_tstat on (in-window daily excess) with a dummy
  contrast against out-window daily excess; lags=10 (window length). Reported but episode-level is the gate.
- Effective-N basis = **independent season-quarter episodes**, NOT daily rows. XFN: 2001Q2→2026Q2 ≈
  **101 in-window episodes**. ZEB: 2010Q2→ ≈ **65**. (bootstrap_effective_t on the daily excess series
  reported for autocorrelation honesty; the gate uses episode count.)

### 2.2 PEAD (per-bank event drift)
- Universe: 5 banks in the 5y panel. Events: the 4 observed report dates per bank present in the panel
  window (2021-06→2026-06) ⇒ ~16-20 usable events (some Aug-2025..May-2026 dates are all in-panel; the
  4th quarter Aug-2025 is in-panel). Count reported honestly at run.
- Beat = surprise_pct > 0; miss = surprise_pct ≤ 0 (from the earnings payload). Fill on the **next bar**
  after the report date (T+1 open proxied by next close; report is after-close for TSX banks).
- Drift = bank forward log-return over horizons {1w=5td, 2w=10td, 4w=20td}, **sector-neutralized** by
  subtracting the XFN.TO return over the same window (removes the season/sector move so we isolate the
  idiosyncratic surprise response).
- Statistic: mean(beat drift) − mean(miss drift) per horizon, HAC t (events near-non-overlapping within
  a bank across quarters; pooled across banks). Effective-N = **independent bank-quarter events** (~16-20).

### 2.3 Fills / suspension / survivorship
- **NEXT-BAR fills** everywhere. Report dates are after-market for TSX banks ⇒ first tradable bar = next
  session; drift measured from next-bar close.
- **Suspension/halt rule:** if a bank's close is missing/stale on a fill bar, roll forward to the next
  available bar (carry, no synthetic price); an event with no tradable bar within +3 sessions is dropped
  and counted. (Canadian big-6 do not halt for weeks — this rule is mostly inert here but stated.)
- **Survivorship:** the 5y name panel is CURRENT-CONSTITUENT (data/canada_search). The big-6 banks are
  the survivors by construction — NO delisted big-6 bank exists in the sample period, so PEAD survivorship
  bound ≈ nil for the bank set specifically. The ETF legs (XFN/ZEB) are index products (survivorship
  handled by the index provider); stamp: "ETF-level, index-methodology survivorship." Bound stated, not
  a sticker.

---

## 3. Pre-registered trial list (every variant counts)

| # | Trial | Family | Effective-N |
|---|-------|--------|-------------|
| 1 | H-C-BANK-1 season window, **XFN.TO** (2001→) | season | ~101 episodes |
| 2 | H-C-BANK-1 season window, **ZEB.TO** (2010→) | season | ~65 episodes |
| 3 | H-C-BANK-2 PEAD beat−miss, **1w** | pead | ~16-20 events |
| 4 | H-C-BANK-2 PEAD beat−miss, **2w** | pead | ~16-20 events |
| 5 | H-C-BANK-2 PEAD beat−miss, **4w** | pead | ~16-20 events |

**Exploratory (LABELED, NON-GATED, non-evidential — cannot promote):**
- E1: does the season-window effect extend to the rate-sensitive sleeve **XUT.TO** (utilities, 2012→)?
- E2: same for **XRE.TO** (REITs, 2002→)? Informs the BoC-window conditioner design only.

**Program-level DSR `n_trials = 30`** (masterplan §6 program level, NOT the 5-trial family count).
BH-FDR applied WITHIN each family (season: 2 trials; pead: 3 trials) at α=0.10.

---

## 4. Gates (pre-registered — GO / NO-GO / KILL / ACCRUE)

A trial reaches **GO** only if ALL of:
1. HAC |t| ≥ **2.5** (episode-level for season; event-level for PEAD) — the constitution bar for a thin,
   multiple-tested seasonal (stricter than 2.0 because of the small effective-N and known dividend/
   selection hazards).
2. **BH-FDR reject** within its family at α=0.10.
3. **DSR ≥ 0.90** via `engine.validation.deflated_sharpe` with **n_trials=30** (program level),
   `t_eff` from `bootstrap_effective_t` on the underlying daily series.
4. **Split-half sign-stability:** split the episode set by calendar median date; the sign of the effect
   must agree in BOTH halves (season). For PEAD, split banks into two groups (by ticker sort) — sign must
   agree. A sign flip across halves ⇒ cannot GO.

Verdict mapping:
- **GO** — all four met. (Then: report only; NO wiring, per W2.)
- **ACCRUE** — direction correct + |t| in [1.5, 2.5) OR DSR in [0.80, 0.90) OR split-half agrees in sign
  but one half is weak. A marginal result is ACCRUE, not GO (constitution: do not torture into GO).
- **NO-GO** — |t| < 1.5 or wrong sign or BH-reject fails and not salvageable as ACCRUE.
- **KILL** — effect has the WRONG sign at |t| ≥ 2.0 (an actively contrary result → drop the mechanism
  from the edge stack).

**Honest priors (pre-stated):**
- Trial 1 (XFN, 101 episodes) is the ONLY decision-grade leg. Expect GO-or-ACCRUE.
- Trial 2 (ZEB, 65 episodes) is a robustness echo of Trial 1 (overlapping sleeve) — corroboration, not
  independent evidence; if it disagrees with Trial 1 that is a red flag on Trial 1.
- Trials 3-5 (PEAD, ≤20 events) are **structurally under-powered**; the ledger says decision-grade at
  ~100 bank-quarters (25y). On 20 events, ACCRUE is the ceiling absent a huge effect. Pre-stated so the
  gate, not the narrative, decides.

---

## 5. What this pre-reg fixes (anti-p-hacking)

- Windows, anchors, horizons, beat/miss cut, sector-neutralization, fill rule, and all 5 trials are
  frozen here. No post-hoc window widening, no horizon fishing beyond {1,2,4}w, no dropping ZEB if it
  disfavors.
- The dividend-drift confounder is handled by the in−out contrast design, stated before running.
- Program DSR n_trials=30 (not 5) is pre-committed — the honest multiple-testing count for the whole
  HK/Canada program per masterplan §6.
- Reports (reports/cbank-phase0.md) will open with the verdict in bold and include the gates-vs-results
  table, split-half, effective-N honesty, survivorship stamp, and an explicit "what this does NOT show".
