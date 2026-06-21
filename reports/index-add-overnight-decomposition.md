# S&P pure-add run-up — overnight vs intraday decomposition

_Pure/net-new additions, 897 events, [-5,0] window, **GROSS** SPY-relative log-returns summed over the 5 held days. Tests WHERE the run-up accrues (not net of cost)._

| Component | mean logsum (GROSS) | share of total | HAC-t |
|--|--:|--:|--:|
| overnight (open/prev-close) | 0.0141 | 1.04 | 5.22 |
| intraday (close/open) | -0.0006 | -0.04 | 0.11 |

_the pure-add run-up is OVERNIGHT-dominated (GROSS) — it accrues in the close→open gaps, not intraday. Capturing it would need a close-buy/open-sell execution on the live announcement feed (forward accrual); the open-auction spread + impact on these small-cap names is UNMODELED, so this overnight figure is a GROSS UPPER BOUND, not a net edge._
