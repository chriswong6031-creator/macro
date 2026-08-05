# LSR-P0 — Liquidity-shock reversal classifier: prereg + decision

**Date:** 2026-08-05 · **Family:** `liquidity_shock_reversal_p0`
**Study:** `scripts/research_liquidity_shock_reversal.py` · **Results:** `reports/liquidity-shock-reversal-phase0.md`
**Decision:** **NO-GO — construction-scoped kill.** Registered in `research/DO_NOT_REBUILD.md` §2.

---

## §0 Origin

External method candidate, intake 2026-08-05: build a model that distinguishes a
fall driven by *informed selling* from a fall driven by *someone urgently needing
liquidity*, since the two charts look identical. Proposed features:
`residual_return_zscore`, `abnormal_volume`, `signed_order_imbalance`,
`price_change_per_dollar_flow`, `close_location_value`, `intraday_recovery`,
`spread_proxy`, `peer_divergence`, `news_materiality`, `flow_persistence`.
Proposed labels: full reversal / partial reversal / continued information-driven
move. Proposed uses: (1) generate genuine mean-reversion candidates for Prophet,
(2) stop the momentum engine shorting the last stage of forced selling or buying
the last stage of forced covering.

The candidate is **well-posed and correctly grounded**. Savor (2012, JFE) is the
canonical result: major price shocks accompanied by information drift, shocks
without information reverse. Nagel (2012) ties short-horizon reversal profits to
compensation for liquidity provision, with a ~1-week horizon. Nothing in
`DO_NOT_REBUILD.md` forbade the topic at intake — the three nearest kills
(PSS-SR1/SR2/SR3, rows 75–77) all condition on *price and peer structure* at a
washout and never on *why the selling happened*, so the information firewall is a
genuinely new axis rather than a re-proposal.

## §1 What was frozen before any outcome was inspected

| Element | Frozen choice |
|---|---|
| Universe | `data/massive_stock_day`, ≥$5 close, ≥$2M median dollar volume; ≥$5M at event time |
| Span | 2021-07-06 → 2026-07-02 (the store's full reach), 4,281 names |
| Residual basis | own return − equal-weighted **same-sector ex-self** peer return |
| Shock trigger | residual-return z ≤ −3.0 (mirror +3.0), volume ≥ 2× trailing-60d median |
| Baseline window | 60 sessions, always `.shift(1)` |
| Information proxy | EDGAR 8-K within ±1 **calendar** day (earnings item 2.02; material items) |
| Outcomes | forward **residual** return over 1/3/5/10/21 sessions from the t0 close |
| Inference | circular block bootstrap over **trading dates**, block=5, B=4,000 |
| Era split | 2024-03-01 |
| Split repair | canonical `replay_standout_pipeline.split_adjust`; touched bars ineligible |

**Pre-registered gates.** GO required (a) the news-vs-no-news DIFF to exclude zero
at the 3–10 day horizons on the down side, *and* (b) the surviving effect to
exceed a plausible round-trip cost, *and* (c) sign-consistency across both era
halves. Any of (a)/(b)/(c) failing is a NO-GO.

**Multiple-testing budget declared up front:** 10 news contrasts (2 sides × 5
horizons) + 36 classifier tests (12 features × 3 horizons) + 6 veto gaps + 18
unconditional-reversal cells = 70 tests. At α=0.05, ~3.5 false positives are
expected; a finding must beat that budget, not merely clear 0.05.

## §2 Result

All three gates fail.

* **(a) Separation: 0 of 10 contrasts exclude zero.** Down-shocks *continue*
  (−0.33% residual at 5d for no-news, interval excluding zero) instead of
  reverting, and continue hardest when the shock is largest. Up-shocks fade more
  when there *is* news — the sign opposite to the predicted drift.
* **(b) Cost:** the one real effect (unconditional 1d-formation residual reversal,
  liquid tercile, D10−D1 +0.284%/5d) breaks even at **14.2 bp of round-trip cost
  per leg** at 50 cycles/year. Nothing survives.
* **(c) Era consistency:** the arms are consistent — consistently null (2021-09→
  2024-02 no-news −0.393% vs news −0.173%; 2024-03→2026-07 −0.258% vs −0.290%,
  all intervals spanning zero).

The classifier fires 3 of 36 (1.8 expected), with no feature consistent across
horizons and several sign-flipping between them. The veto stand-in moves 0 of 6.

**The firewall was validated before the null was believed** — 8-K windows cover
4.1% of days unconditionally but 60.0% of down-shocks (~15× enrichment), and
news shocks carry 4.1× the overnight gap of no-news shocks. The null is not an
artefact of a dead flag.

## §3 Withdrawn intermediate claim

An early cut subtracted the Corwin-Schultz spread as a trading cost and reported
net returns of −0.9% to −1.2%. **Withdrawn.** Against a known planted spread the
estimator is dominated by volatility (5 bp true → 38 bp read at 1.5%/day vol,
74 bp at 3%/day), and a shock population is selected for high range. The shipped
study reports a break-even instead and never subtracts a point estimate; the
contamination is pinned by test so the column cannot be silently reused as a cost.
No verdict depends on it — all four are measured gross.

## §4 Scope of the kill

**Closed:** the 1–5 day liquidity-shock reversal classifier as selection alpha or
as a Prophet entry veto, on the ≥$5 / ≥$5M-ADV US panel, with an EDGAR-8-K
information firewall and **OHLCV-derived** microstructure proxies. Do not
re-propose it by re-tuning the z-threshold, the volume multiple, the horizon set,
the peer basis, or the label taxonomy — those are the same construction.

**The four reopeners, after `scripts/research_lsr_reopeners.py` (report §7):**

1. **Tape-grade features — STILL OPEN, blocked on entitlement.**
   `signed_order_imbalance`, `price_change_per_dollar_flow` and a true
   `spread_proxy` require the per-trade tape and NBBO; massive.com is
   aggregates-only, `trades_v1`/`quotes_v1` both 403
   (`collectors/massive_flatfiles`). **The order-flow half of the candidate was
   never tested at its intended fidelity.** Not closeable by more analysis.
2. **Richer information firewall — OPEN, COVERAGE-BLOCKED with a clock.**
   `data/revisions/history.parquet` begins 2026-06-16; only **239 of 35,678
   events (0.67%) on 12 dates** have a revisions read. Savor's own proxy is
   unanswerable here today. Keep accruing; re-test in a few years.
3. **Illiquid tail — CLOSED.** Rebuilt at $2/$250k (7,087 names, 63,352 events):
   news contrast **0 of 5**; unconditional reversal genuinely stronger (bottom
   decile 5d **+0.392%**, rank-IC **+0.032** vs +0.013 liquid) but break-even
   **19.6 bp/leg**, which a $2 / $250k-ADV name does not trade inside. Bigger
   gross, worse net — the same place `validate_reversal_nonsurvivor` landed.
4. **Market-liquidity regime — separation CLOSED (0 of 9); one lead LOGGED.**
   By VIX 252d percentile, the news contrast fails in *every* regime. But the
   no-news down arm runs **−0.599% (calm, VIX 16) → −0.312% → +0.261% (stressed,
   VIX 24.5)** at h=5, and the direct test of that gradient gives **calm − stressed
   = −0.860% [−1.575, −0.145]**, excluding zero at **1 of 3 horizons**. Treat as a
   hypothesis, not a finding: the stressed level itself spans zero, breakpoints
   were post hoc, it is an arm mean and not a tradeable spread, and a ranker inside
   the stressed bucket is exactly what §2's classifier test found null. It is a
   **different claim from the candidate's** — *down-shock continuation weakens as
   market liquidity tightens* — and needs its own prereg with frozen breakpoints.

## §5 Relation to the existing record

This is the third independent reversal measurement in the repo and the first at
the 1–5 day horizon:

| Study | Construction | Verdict |
|---|---|---|
| `scripts/validate_reversal.py` | 21d/21d monthly, survivor large-cap | NO-GO — liquid residual IC t_HAC 0.351, net-10bp −1.34%/yr |
| `scripts/validate_reversal_nonsurvivor.py` | 21d/21d monthly, delisting-recovered | NO-GO — net-10bp −2.68%/yr, survivorship drag 0.23%/yr |
| **LSR-P0 (this)** | **1–5d event-conditioned, information firewall** | **NO-GO — separation 0/10, break-even 14 bp/leg** |

The 1–5 day result is *consistent* with the monthly ones rather than a new
finding: a real but marginal gross effect whose fate is entirely transaction cost,
and which the proposed conditioning does not improve.

## §6 Reproduce

```bash
PYTHONPATH=. python -m scripts.research_liquidity_shock_reversal
PYTHONPATH=. python -m pytest tests/test_liquidity_shock_reversal.py -q
```

First run scans ~20.5k parquets (~50s) and caches the wide panel under
`data/research/lsr_p0_panel/`; the report lands at
`data/research/lsr_p0_report.json`.
