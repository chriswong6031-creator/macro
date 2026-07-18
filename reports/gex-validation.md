# GEX validation — gamma regime vs forward realized vol

Falsifiable claim: short-gamma days precede HIGHER forward realized vol than long-gamma days.
Forward-accumulating (no free options history). This verdict GATES any ladder weight; until it PASSES, GEX is display-only and never touches the score.

Stores evaluated:
  * data/cboe/gex*.parquet — 10 named equities + SPX (corroboration)
  * data/polygon_gex/summary_*.parquet — 384-name per-name summaries (primary gate store)
Evidence lines are prefixed [cboe] or [polygon_gex] to identify the source.

### cboe store
- [cboe] gex h=5d: building history (long n=16, short n=8; need 30/bucket)
- [cboe] gex h=10d: building history (long n=11, short n=8; need 30/bucket)
- [cboe] gex_AAPL h=5d: building history (long n=22, short n=0; need 30/bucket)
- [cboe] gex_AAPL h=10d: building history (long n=17, short n=0; need 30/bucket)
- [cboe] gex_AMD h=5d: building history (long n=22, short n=0; need 30/bucket)
- [cboe] gex_AMD h=10d: building history (long n=17, short n=0; need 30/bucket)
- [cboe] gex_IWM h=5d: building history (long n=0, short n=22; need 30/bucket)
- [cboe] gex_IWM h=10d: building history (long n=0, short n=17; need 30/bucket)
- [cboe] gex_META h=5d: building history (long n=12, short n=10; need 30/bucket)
- [cboe] gex_META h=10d: building history (long n=7, short n=10; need 30/bucket)
- [cboe] gex_MSFT h=5d: building history (long n=14, short n=8; need 30/bucket)
- [cboe] gex_MSFT h=10d: building history (long n=9, short n=8; need 30/bucket)
- [cboe] gex_NVDA h=5d: building history (long n=20, short n=2; need 30/bucket)
- [cboe] gex_NVDA h=10d: building history (long n=15, short n=2; need 30/bucket)
- [cboe] gex_QQQ h=5d: building history (long n=10, short n=12; need 30/bucket)
- [cboe] gex_QQQ h=10d: building history (long n=9, short n=8; need 30/bucket)
- [cboe] gex_SPX h=5d: building history (long n=15, short n=6; need 30/bucket)
- [cboe] gex_SPX h=10d: building history (long n=10, short n=6; need 30/bucket)
- [cboe] gex_SPY h=5d: building history (long n=4, short n=17; need 30/bucket)
- [cboe] gex_SPY h=10d: building history (long n=2, short n=14; need 30/bucket)
- [cboe] gex_TSLA h=5d: building history (long n=19, short n=3; need 30/bucket)
- [cboe] gex_TSLA h=10d: building history (long n=14, short n=3; need 30/bucket)

### polygon_gex store
- polygon_gex: 0 pass, 778 building, 0 no-edge, 0 errors (out of 778 total evidence lines)
