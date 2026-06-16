# IPO lock-up expiry — Phase-0 event study

As of 2026-06-16 · 77 usable names (2 missing price data) · min deal size $50M

**Verdict: DISPLAY-ONLY · no measurable edge on our sample**

| Window | n | mean % | median % | trimmed % | % neg | t (HAC) | p |
|---|--:|--:|--:|--:|--:|--:|--:|
| pre_runup[-10,-1] | 77 | -0.81 | -1.83 | -1.7 | 59.7 | -0.346 | 0.7293 |
| event[-1,+3] | 77 | 0.88 | 1.04 | 1.0 | 44.2 | 0.812 | 0.4168 |
| event[0,+3] | 77 | 1.27 | 1.67 | 1.47 | 42.9 | 1.255 | 0.2096 |
| event[0,+1] | 77 | 1.42 | 0.55 | 1.37 | 44.2 | 1.923 | 0.0545 |
| wide[-5,+5] | 77 | -0.28 | 0.0 | -0.04 | 49.4 | -0.199 | 0.8422 |

### Honest caveats
- survivorship (delisted IPOs absent → drift biased upward)
- small/time-clustered sample (cross-sectional t overstates)
- borrow scarce/expensive in lock-up → not shortable net of cost

Market-adjusted (stock − SPY) cumulative returns around the lock-up expiry (priced_date + prospectus-confirmed-or-180d). The leg ships DISPLAY-ONLY regardless: a negative drift here is long-only-avoidable, not shortable net of borrow, so it never becomes a scored signal — only an avoid/de-risk calendar.
