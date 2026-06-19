# Capitulation bounce risk-ON overlay (Fed-put gated) — Phase-0

**Question.** Promote the FDR-validated capitulation *alert* (`capitulation_signal`, 91 firings / 54 clusters, 60d P(up) 84% vs 72%, q=0.0) from an alert to a SIZED leg: a timed risk-ON SPY-overweight overlay (+0.5 for 63td after capitulation_score>=2, re-armed per cluster), GATED by the dislocation Fed-put master switch. Does the TIMED allocation clear SCORED, or only confirm the Fed-put gate it enriches?

**Method (no look-ahead).** SPY 1993-01-29..2026-06-17. Gauge reconstructed faithfully from config (VRP %ile>0.90 + VIX>30 + COT ES net-spec 3y-washout<10%); gate = `dislocation.master_switch_frame.put_absent` (Sahm>=0.50 OR smoothed 10y breakeven>=2.5%). Overlay financed at bill+1% (`active_alloc.backtest_lev`), cost 3.0bps; position acts next bar. Marginal = book minus base-only (1.0x SPY). 6 variants tried (DSR N=6).

## Headline

- Candidate book (base 1.0x + gated overlay): CAGR **11.96%** vs base 1.0x **10.80%**; MaxDD -56.6% vs -55.2%; avg leverage 1.08.
- Overlay MARGINAL Sharpe **0.335** (boot 95% CI [0.06, 0.34, 0.62]); mean 0.658 bps/day over 21 fires / **21 independent clusters**.
- **DSR = 0.7372** (FAILS multiple-testing haircut (DSR<0.90)); sr_ann 0.34 vs haircut sr0_ann 0.23, T=8403, N=6.
- Event-study (forward 63d): gated fires P(up) **75%** vs base 72%, mean +5.31% vs +2.86%, NW t=2.937.

## Gate results

| gate | bar | result | pass |
|---|---|---|---|
| DSR | >=0.90 | 0.7372 | NO |
| split-half OOS | beats B&H both halves | first=True second=True | YES |
| leave-one-crisis-out | marg Sharpe>0 ex each bear | full=0.335 | YES |
| beat dumb VIX>30 (gated) | marg Sharpe higher | 0.335 vs 0.377 | NO |
| beat dumb -10%wk (gated) | marg Sharpe higher | 0.335 vs 0.338 | NO |
| honest-N | >=8 independent clusters | 21 | YES |

## Leave-one-crisis-out (overlay marginal Sharpe)

| excised | marg Sharpe | mean bps | n |
|---|---|---|---|
| 2000-02_dotcom | +0.366 | +0.727 | 7691 |
| 2008_gfc | +0.361 | +0.700 | 7962 |
| 2020_covid | +0.371 | +0.627 | 8299 |
| 2022_hike | +0.353 | +0.671 | 8152 |
| FULL | +0.335 | +0.658 | 8403 |

## Gate vs ungate — does the Fed put add anything?

| variant | fires | clusters | book CAGR | marg Sharpe | es P(up) | es mean% |
|---|---|---|---|---|---|---|
| GATED_cap>=2 (CANDIDATE) | 21 | 21 | 11.96% | 0.335 | 0.750 | 5.31 |
| ungated_cap>=2 | 36 | 36 | 12.54% | 0.399 | 0.714 | 5.05 |
| GATED_VIX>30 | 21 | 21 | 12.22% | 0.377 | 0.800 | 6.21 |
| ungated_VIX>30 | 34 | 34 | 12.57% | 0.401 | 0.818 | 5.69 |
| GATED_-10%wk | 6 | 6 | 11.79% | 0.338 | 1.000 | 14.15 |
| ungated_-10%wk | 10 | 10 | 11.88% | 0.317 | 0.900 | 10.85 |

Fed-put gate moves event-study P(up) by +0.036 vs ungated cap>=2 — but it LOWERS the timed-allocation CAGR (12.54%→11.96%) and marginal Sharpe (0.399→0.335): the gate excises 2008/2022 fires that partly recovered within 63d, so as a P&L lever it costs return. The gate is a DRAWDOWN-RISK filter (its shipped evidence), not a return enhancer.

## Decisive cross-checks

- **Book-level DSR is a red herring.** The candidate BOOK (1.0x + overlay) scores DSR=0.9902, but the BASE (1.0x SPY, NO overlay) scores DSR=0.9921 — the high book DSR is the SPY equity premium, not the overlay. The honest test is the overlay's MARGINAL stream (DSR=0.7372, fails).
- The overlay DOES add return: book-minus-base +0.658 bps/day, NW t=2.437, p=0.0148 — consistent with the FDR-validated alert. But that edge is reactive/coincident, not a deflation-surviving timed allocation.
- **No edge over the dumb VIX>30 leg.** Candidate-marginal minus dumb-VIX>30-marginal = -0.1184 bps/day, NW t=-0.639, p=0.5229 — statistically zero. The 3-leg VRP+VIX+COT stack adds nothing over a one-line 'buy when VIX>30, Fed-put-gated'; in fact dumb-VIX scores a HIGHER marginal Sharpe (0.377>0.335) and stronger event-study t (5.87>2.94).

## Verdict

**CONFIRMER (not scored).** Fails: DSR 0.7372 < 0.90 (marginal), does NOT beat dumb VIX>30, does NOT beat dumb -10%wk.

The capitulation alert's forward-return edge is genuine and FDR-validated, and the overlay does add positive return to the book (book-minus-base NW t=2.437). But as a TIMED, financed, leverage-aware ALLOCATION it (1) fails the multiple-testing haircut on its marginal stream (DSR=0.7372), and (2) is statistically indistinguishable from a one-line dumb 'buy VIX>30' leg (head-to-head p=0.5229), which itself scores a higher marginal Sharpe. The Fed-put gate it enriches is the validated DRAWDOWN filter, and the candidate adds no independent sized edge on top of it. Keep capitulation as a confirmer / display-only attention signal feeding the existing dislocation gate — do NOT promote it to an independently scored allocation leg.
