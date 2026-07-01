# GEX validation — gamma regime vs forward realized vol

Falsifiable claim: short-gamma days precede HIGHER forward realized vol than long-gamma days.
Forward-accumulating (no free options history). This verdict GATES any ladder weight; until it PASSES, GEX is display-only and never touches the score.

- gex h=5d: building history (long n=10, short n=5; need 30/bucket)
- gex h=10d: building history (long n=8, short n=2; need 30/bucket)
- gex_AAPL h=5d: building history (long n=12, short n=0; need 30/bucket)
- gex_AAPL h=10d: building history (long n=7, short n=0; need 30/bucket)
- gex_AMD h=5d: building history (long n=12, short n=0; need 30/bucket)
- gex_AMD h=10d: building history (long n=7, short n=0; need 30/bucket)
- gex_IWM h=5d: building history (long n=0, short n=12; need 30/bucket)
- gex_IWM h=10d: building history (long n=0, short n=7; need 30/bucket)
- gex_META h=5d: building history (long n=5, short n=7; need 30/bucket)
- gex_META h=10d: building history (long n=4, short n=3; need 30/bucket)
- gex_MSFT h=5d: building history (long n=5, short n=7; need 30/bucket)
- gex_MSFT h=10d: building history (long n=4, short n=3; need 30/bucket)
- gex_NVDA h=5d: building history (long n=12, short n=0; need 30/bucket)
- gex_NVDA h=10d: building history (long n=7, short n=0; need 30/bucket)
- gex_QQQ h=5d: building history (long n=8, short n=4; need 30/bucket)
- gex_QQQ h=10d: building history (long n=5, short n=2; need 30/bucket)
- gex_SPX h=5d: building history (long n=9, short n=3; need 30/bucket)
- gex_SPX h=10d: building history (long n=6, short n=1; need 30/bucket)
- gex_SPY h=5d: building history (long n=2, short n=10; need 30/bucket)
- gex_SPY h=10d: building history (long n=2, short n=5; need 30/bucket)
- gex_TSLA h=5d: building history (long n=10, short n=2; need 30/bucket)
- gex_TSLA h=10d: building history (long n=7, short n=0; need 30/bucket)
