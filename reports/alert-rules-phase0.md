# Alert-rule Phase-0 — event study on the condition-based macro alerts

**Question.** The Alert Command Center (`/alerts.html`) shows a measured hit-rate
only where a signal family is validated. The condition-based macro alert rules
carried documented conviction but no backtest. This harness
(`scripts/alert_rules_phase0.py`) earns — or refuses — those numbers.

**Method.** Each rule's historical firings are reconstructed over the full
features frame (faithful to the `engine/alerts.py` thresholds), then an event
study measures forward **SPY** returns at 1 / 5 / 20 / 60 trading days
(1993-01-29 … 2026-06-12):

- hit-rate in the thesis direction (risk-off → `P(fwd<0)`; the contrarian
  capitulation rule → `P(fwd>0)`), versus the unconditional base rate;
- a **Newey-West (HAC)** t-stat of (conditional − base mean), lags = horizon, so
  overlapping windows and event clustering don't overstate significance;
- `n_events` and **`n_clusters`** (firings > horizon apart = independent windows)
  — the honest power, since risk-off events bunch in crises;
- **Benjamini-Hochberg FDR** across the whole rule × horizon panel.

A rule **EARNS** a hit-rate only if it is thesis-significant, survives FDR at
10%, and has ≥ 8 independent clusters. Three honest outcomes: `earned` /
`no_edge` (powered but failed) / `underpowered` (too few firings to test).

## Verdicts

| rule | thesis | events / clusters | verdict | headline |
|---|---|---|---|---|
| **ebp_widening** | risk-off | 12 / 12 | **EARNED @60d** | 5d `P(down)` **83%** vs 41% base; 20d 67%; q<0.01 |
| **drawdown_risk_high** | risk-off | 13 / 10 | **EARNED @60d** | 20d `P(down)` **85%** (+50pp); 60d 62%; q=0.0 — confirms the in-code "~36% drawdown" claim |
| **capitulation_signal** | contrarian | 91 / 54 | **EARNED @60d** | 60d `P(up)` **84%** vs 72% base; q=0.0 — confirms the in-code "+9.3% / 86%" claim |
| **net_liq_expand** | bullish | 137 / 89 | **EARNED @60d** | 60d `P(up)` 77% vs 72% base (+5pp, modest but FDR-significant) |
| hy_oas_widening | risk-off | 168 / 77 | **NO EDGE** | the 1-day OAS spike is coincident / already-priced — no forward SPY edge (q≈0.93), contradicting its "best smoke detector" conviction |
| net_liq_contract | risk-off | 103 / 69 | **NO EDGE** | contracting liquidity does **not** precede downside — an asymmetry vs the expansion leg |
| nfci_tightening | risk-off | 2 / — | UNDERPOWERED | only 2 upward crosses of the threshold |
| sahm_trigger | risk-off | 4 / 4 | UNDERPOWERED | recessions only; n too small to test |
| recession_high | risk-off | 4 / 2 | UNDERPOWERED | too few crossings into the high band |

**4 of 9 earn a per-horizon hit-rate**; two are honest negatives, three are
untestable on the available history. The earned numbers and the verdicts are
written to `data/alerts/rule_scorecard.json` and read live by
`engine.alert_triage` — so the alert board shows `BACKTESTED ✓ hit X% vs Y% base`
on the four, `TESTED · NO EDGE` on hy_oas / net-liq-contract, and `UNTESTABLE`
on the rest, instead of a fabricated number.

**Caveats.** SPY (1993+) is the tradeable target, so pre-1993 firings of the
slow macro rules drop out — which is why sahm / nfci / recession are
underpowered. Risk-off events cluster; the HAC t-stat on the event-ordered
series plus the `n_clusters` floor are the guardrails, but the earned rules with
few clusters (ebp 12, drawdown 10) should be read as "real but modest n".
Re-run the harness to refresh: `python -m scripts.alert_rules_phase0`.
