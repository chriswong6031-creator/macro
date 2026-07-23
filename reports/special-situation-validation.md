# Special-situation (deal-event) convergence channel — event study

_Generated 2026-07-22 13:57 UTC. Event class: non-activist actionable US deal-events (first per ticker)._

- Events: **250** first-per-ticker actionable US deal-events (219 priceable) · 2026-02-02 → 2026-07-21
- Method: daily calendar-time portfolio · SPY-relative · leak-free entry (first close strictly after the EDGAR filing date) · Newey-West HAC lag=horizon · validity bar n_days>=max(6,horizon)
- **Verdict: context-tier confirmer (measuring)**
- **Weight ruling: DE-ESCALATE to 0.20 (context tier) — mirror activist_13d in #3216**

## Post-filing SPY-relative abnormal returns (vs pre-event placebo)

_Entry is STRICTLY AFTER the filing date, so the announcement pop is already gone — this is post-filing DRIFT, not the event jump. The placebo enters the same names one quarter earlier to net out each name's normal drift._

| Horizon | n | n_days | mean_abn | median | hit | HAC-t | p | valid | placebo mean | placebo HAC-t |
|--:|--:|--:|--:|--:|--:|--:|--:|:--:|--:|--:|
| 5d | 204 | 81 | -0.0037 | -0.0076 | 0.436 | -0.92 | 0.3583 | ✓ | 0.0077 | 3.5 |
| 10d | 196 | 77 | -0.0053 | -0.0098 | 0.469 | -1.2 | 0.2286 | ✓ | 0.0017 | 1.13 |
| 21d | 162 | 66 | -0.0146 | -0.0169 | 0.407 | -2.37 | 0.0178 | ✓ | -0.0069 | -0.03 |
| 63d | 34 | 26 | -0.0802 | -0.1001 | 0.176 | -3.81 | 0.0001 | — | -0.0279 | -0.53 |

_post-filing special-situation drift is NOT robustly positive/significant vs the pre-event placebo on the covered panel → context-tier confirmer ('measuring')._

_Caveat: the special-situations pipeline is ~6 months old, so even a SCORED reading is provisional and rests on a daily-HAC (not the activist gate's 2-year monthly cluster). Re-run as the panel deepens._
