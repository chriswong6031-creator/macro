# C6 — Asia-Semi Aggregate Read-Through: Phase-0 Report

**Date:** 2026-07-02
**Wave:** W4-C6 (INTL Fix Masterplan §5)
**Claim:** `c6_asia_semi_readthrough` — one pre-registered equal-weight Asia-semi sensor
basket (TSM + ASML, US-listed ADRs) leads `SMH` at the pre-registered 5d horizon,
earnings-print windows excised.
**Verdict: CONTEXT** — do NOT wire. Contemporaneous co-membership, **not** a tradeable lead
and **not** even a timezone-transmission read.

---

## Verdict summary

The one pre-registered equal-weight Asia-semi basket — **TSM + ASML**, the two US-listed
ADR sensors the C6 claim declares (`source_series`), chosen **on purpose** per §4.4 so the
sensors trade in the US session and the raw-screen lag-1 timezone ambiguity is removed —
graded through the **lead-lag kernel** (HAC-t + BH-FDR + split-half same-sign, the gate ADJ-4
demands for any cross-market claim) with a **±2 trading-day earnings-print excision** (838
rows, 12.8% of the panel — the `calibrate_forex` peg-excision pattern, closing INTL-49).

The kernel result is decisive and clean:

- **lag-0 is huge** (HAC-t **+15.9**, mean corr **+0.82**, FDR-reject, split-half stable) — but
  that is **mechanical co-membership**: TSM and ASML are two of `SMH`'s largest holdings, so
  same-day co-movement is the basket partly *being* the target, not leading it. The kernel's
  `pass` **excludes lag-0 by construction** for exactly this reason.
- **No lag ≥ 1 link survives.** lag-1 HAC-t **−1.67** (q_FDR 0.16, does not reject; split-half
  FALSE) — and it is **negative**, mirroring `SMH`'s *own* lag-1 mean-reversion (−0.05); lag-2/3/5
  are all |t| < 2.1 and non-surviving.

So there is no forecastable lead. And because the ADRs trade in the US session, there is not
even the **timezone-transmission lag-1** that the raw local-index cross-asset screen
(`cross-asset-leadlag-phase0.md`) surfaced as a de-risk confirmer — the ADR design deliberately
removed the overnight carry-in, leaving **only same-day co-membership**. This is a cleaner
negative than the raw screen: there is no honest "transmission read" escape hatch here.

**The surviving structure is neither a tradeable lead nor a timezone-transmission read — it is
contemporaneous index co-membership.** Weight cap **0**, `kill=True`. `stock_score._axis_tailwind`
(the would-be DOWNGRADE-only seam) is **UNCHANGED** — the harness wires nothing this wave
regardless of verdict, and CONTEXT means there is nothing to wire ever.

---

## Gate-by-gate table

| Gate | Result | Key number | Threshold |
|------|--------|-----------|-----------|
| Freshness (§4.2 g6) | PASS | yahoo/TSM, yahoo/ASML through 2026-07-01/02 | SLA 5d |
| **Lead-lag kernel (§4.2 g5)** — *binding* | **FAIL** | **0 of 4 lag≥1 links survive FDR + split-half** (lag-1 t −1.67, q 0.16, negative) | ≥1 lag≥1 lead surviving |
| Orthogonality vs SMH own momentum (§4.2 g2) | FAIL (wrong-signed) | raw Spearman +0.11; residual **+0.07** (wrong sign for a de-risk leg) | \|resid\| ≥ 0.03 with correct sign |
| DSR / promotion (§4.2 g1) | fail | **0.4463** (N=17 intl_bridge budget) | ≥ 0.90 |
| Split-half same-sign (§4.2 g1) | fail | strategy H1/H2 Sharpe sign-flip | same sign |
| Drawdown-reduction (§4.2 g «f») | fail | MaxDD cut +10.1pp **but** Calmar 0.153 < 0.216 B&H | cut ≥1pp AND Calmar ≥ B&H |
| Crisis-count effective-N (§4.2 g3) | pass | 5/6 crises contained | ≥ 3 |
| Crisis-independent ES (§4.2 g4) | pass | ES reduction ex top-3 = +0.0061 | > 0 |

The **lead-lag kernel is the binding gate.** A cross-market read-through claim whose kernel finds
no surviving lag ≥ 1 lead is a transmission/co-membership read, not a tradeable lead, and is
CONTEXT by construction (decided up front, before any other gate can promote it). Even setting the
kernel aside, the claim independently fails the promotion door (DSR 0.45), split-half, the
cost-justified drawdown-reduction gate (the overlay cuts SMH MaxDD by 10.1pp but *halves* the
return — Calmar 0.153 < 0.216 B&H, so it destroys value rather than de-risking), and its
orthogonality residual against `SMH`'s own 5d/21d momentum is **wrong-signed** (+0.07) — the basket
adds nothing beyond "semis lead semis."

---

## The lead-lag kernel, in full

Basket (leader) → `SMH` (follower), `prod_t = z_SMH(t) · z_basket(t−k)`, print-excised, full
sample 2000-06 → 2026-07 (6,556 aligned days; the two-sensor basket requires both TSM and ASML
present, so it begins when ASML's ADR history overlaps 2000-06). HAC(10) t-stat; BH-FDR across the
lag grid; split-half at 2013-06-19.

| lag | HAC-t (full) | mean corr | q_FDR | FDR reject | split-half stable | reading |
|----:|-------------:|----------:|------:|:----------:|:-----------------:|---------|
| **0** | **+15.92** | **+0.823** | 0.00 | yes | yes | mechanical co-membership (TSM+ASML *are* in SMH) — **not a lead** |
| 1 | −1.67 | −0.036 | 0.159 | no | no | negative, ≈ SMH's own lag-1 mean-reversion (−0.05); no read-through |
| 2 | −0.45 | −0.010 | 0.654 | no | — | null |
| 3 | −2.02 | −0.040 | 0.108 | no | — | \|t\|<2.1, does not survive FDR |
| 5 | +0.97 | +0.020 | 0.413 | no | — | null |

**lag ≥ 1 survivors: 0.** The only survivor is the contemporaneous lag-0 co-membership term, which
the kernel excludes from the lead determination by construction.

---

## Earnings-print excision (INTL-49)

Read-through spikes around quarterly prints would be miscoded as a lead if left in, so a ±2
trading-day window around **every** constituent print is excised from the forward target and from
every lag's kernel product (the `calibrate_forex.peg_mask` pattern: set the masked rows out of the
grade, keep everything else). **Method, stated honestly:**

- **Causal source:** yfinance `get_earnings_dates` **realized** prints — 98 TSM + 99 ASML dates,
  2000-01 → 2026-04, a near-complete quarterly record (the realized cadence is a clean Jan/Apr/Jul/Oct
  four-per-year). Cached committed to `data/intl_bridge/c6_earnings_dates.json` so the grade is
  reproducible with no network call.
- **Pre-2000 approximation:** ASML's ADR history starts 1995 and TSM's 1997, before yfinance's
  earnings coverage begins (2000). Those ~10 (TSM) + ~22 (ASML) pre-2000 quarters are approximated
  at the *same* stable Jan/Apr/Jul/Oct cadence the realized history shows, mid-month — flagged as
  approximate in the cache. This tail is a small fraction of the panel and pre-dates the 2000-06
  first date where the two-sensor basket exists, so it affects only the ~2000 edge.

Total excised: **838 of 6,556 rows (12.8%)**. The verdict is unchanged with or without the excision
(the excised lag-1 corr is −0.036 vs −0.034 un-excised) — this read-through is not a print-spike
artifact; it simply has no lead to find.

---

## Honest-N statement

The `intl_bridge` trial-ledger family was declared at **N=17** (the full C1–C8 claim×horizon×target
grid) before any scan ran; C6 spends its declared 5d horizon × `SMH` target inside that budget (no
undeclared trials — verified against `data/trial_ledger.jsonl`). The strategy DSR of 0.4463 is
haircut against this honest N=17.

**Crisis-count N = 5** of the 6 pre-declared windows (the basket's 2000-06 start post-dates the
Asian-97 window):

| Crisis | Window | Contained? |
|--------|--------|-----------|
| Asian Financial Crisis | 1997-07 → 1998-10 | No (basket starts 2000-06) |
| Dot-com bust | 2000-03 → 2002-10 | Yes |
| GFC | 2007-10 → 2009-03 | Yes |
| Eurozone sovereign debt | 2011-05 → 2011-12 | Yes |
| COVID crash | 2020-02 → 2020-04 | Yes |
| Rate-shock bear | 2022-01 → 2022-10 | Yes |

Leave-one-crisis-out shows the whole apparent MaxDD improvement comes from the **dot-com** window
(dropping it takes the full-history MaxDD from −0.61 to −0.59, i.e. the overlay barely helped there,
while dropping GFC/Euro/COVID/rate-22 blows the MaxDD out to −0.76…−0.81 — the de-risk overlay was
mostly *long* through those and inherited SMH's crash). This is a single-window artifact, not a
distributed edge. Even read as tail insurance, it is not cost-justified (Calmar below buy-and-hold).

---

## What would change the verdict

- **A surviving positive lag ≥ 1 kernel link** — i.e. the basket's *prior-session* move predicting
  `SMH`'s present move — that clears BH-FDR *and* holds split-half same-sign with |t| ≥ 2. Nothing
  in the current data comes close (best lag ≥ 1 is lag-1 at t = −1.67, and it is the wrong sign).
- **An orthogonality residual with the correct de-risk sign** after partialing `SMH`'s own 5d/21d
  momentum. The residual is currently +0.07 (wrong sign) — the basket carries no incremental
  forward-drawdown content beyond "semis lead semis."
- **Adding the declared local Asia-semi constituents (Samsung / SK Hynix / Tokyo Electron)** would
  re-introduce the timezone lag and *might* resurrect a lag-1 transmission read — but those locals
  are **not** in the C6 declared grid (ADJ-4: exactly the declared `source_series`, no name grids),
  so testing them is a **separate pre-registered claim**, not a post-hoc widening of this one. If a
  future wave declares it, the honest expectation from the raw cross-asset screen is a lag-1
  *transmission* read (CONTEXT with that note), not a tradeable lead.

The wire target if it ever cleared would be `stock_score._axis_tailwind` (DOWNGRADE-capable only).
It has not cleared; nothing is wired.

---

*Run: `python -m scripts.intl_phase0 --c6` (grades `c6_asia_semi_readthrough` through the declared
builder `scripts.c6_asia_semi_readthrough.builder` + merges the ledger). Ledger row:
`data/intl_bridge/ledger.json` (`c6_asia_semi_readthrough`). Graveyard mirror:
`engine/signal_lab.py` (display tier). Print-excision source: `data/intl_bridge/c6_earnings_dates.json`.*
