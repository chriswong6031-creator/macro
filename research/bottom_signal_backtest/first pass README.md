# Bottom/Bounce Signal Backtest

This research package implements the requested signal-quality study:

- completed 1W price MACD bullish crossover
- completed 2W StochRSI bullish crossover from a recent sub-20 oversold state
- first tradable day after completed candles
- 20 trading-day same-ticker cooldown
- forward 5D/10D/20D/30D returns, MFE/MAE, stop-outs, new lows, durable-bottom rates
- single-factor filters and curated two-to-five-factor combinations

Run:

```bash
python3 research/bottom_signal_backtest/run_backtest.py
```

The main outputs are written to `research/bottom_signal_backtest/results/` and charts to
`research/bottom_signal_backtest/charts/`.

Data caveats:

- The broad OHLCV panel starts in 2014, so static validation uses 2014-2017, 2018-2021,
  and 2022-2026 instead of a true 2010 start.
- Sector classifications are current/static when available, not point-in-time.
- Fundamentals and options/GEX are hook points in this run because no broad PIT history is
  present in the repo slice.
