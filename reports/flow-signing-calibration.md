# Flow-signing calibration (tick rule vs NBBO quote rule)

_generated 2026-06-21T10:41:41.598333+00:00 · 101,934 trades · ['SPY', 'QQQ', 'IWM', 'DIA', 'NVDA', 'AAPL', 'TSLA', 'AMD', 'META', 'MSFT']_

Our flow engine signs minute volume with the TICK RULE (no NBBO on the massive.com plan). This measures how close that is to the gold-standard quote rule using a Databento tcbbo (trade + consolidated NBBO) sample.

- **Per-trade agreement (tick vs quote rule):** 0.7774 (size-weighted 0.8083), n=97946 — in line with the literature (~0.77–0.84).
- **Minute net-sign recovery (what the engine actually uses):** 0.4108 across 1222 contracts.
- **DIRECTION gate:** BELOW BAR — DIRECTION IS SOFT (bar 0.7).
- **MAGNITUDE / positioning** (volume, premium size, Vol>OI, 0DTE, gamma EXPOSURE): reliable regardless — needs no signing.


_Key finding: an option's minute-to-minute price ticks are dominated by the underlying's delta-driven move, not by buy/sell pressure, so the tick rule mis-signs net DIRECTION on bar data. Net buy/sell is therefore presented as SOFT context; the magnitude/positioning reads carry the weight. To trust direction, sign at the trade level against the NBBO (a paid trades+quotes tape) or delta-adjust the bar price change. Never a stand-alone buy/sell._
