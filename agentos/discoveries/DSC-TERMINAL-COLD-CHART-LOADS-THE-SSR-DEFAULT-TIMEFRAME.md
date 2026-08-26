---
key: TERMINAL-COLD-CHART-LOADS-THE-SSR-DEFAULT-TIMEFRAME
claim: >
  In the Terminal, a persisted UI preference that a mount effect applies does NOT reach a
  child's data effect in time to steer its first fetch. TerminalShell resolves the startup
  timeframe (mm.startTf) inside its mount effect, but React does not COMMIT that update for
  ~1.05s (measured, dev build, with zero network or chunk activity in the gap — it is main-
  thread render cost, not suspense and not a lazy import). ChartPanel's EFFECT 2 runs at
  ~130ms. So every user whose startup timeframe differed from the server-rendered default
  paid a COMPLETE discarded load first — /data/<sym>.json, setData, buildAllIndicators,
  paint — before the real timeframe even started loading. Nothing cancelled it: EFFECT 2's
  `cancelled` flag only flips in its cleanup, which React runs on the dep change, and that
  commit lands BEHIND the in-flight discarded work. Cost, ten cold runs per arm: p50 1142ms
  / p95 1225ms of the path to the first live candle unthrottled; 2729-3091ms at 4x CPU
  throttle, where the real chart then never loaded inside 45s at all (0 of 4 runs reached a
  first live candle). `workspaceRestored` is NOT a usable readiness signal for this — it is
  `useState(!!initialSymbol)`, so it starts TRUE on any deep link.
falsifier: >
  Load /terminal?symbol=NVDA&boottrace=1 with mm.startTf set to a non-default timeframe and
  read the console: two `chart-effect2-start[SYM@tf]` marks with different tf values, the
  first being the SSR default, reproduces it. One mark, on the user's timeframe, means it is
  fixed. Equivalently, terminal/e2e/live-candle-cold-start.spec.ts going red.
so_what: >
  When a child component's effect must act on a persisted preference, do NOT wait for the
  parent's state commit and do NOT let the child act on the SSR default. Resolve the value
  ONCE synchronously on the client's first render (a ref — it cannot be RENDERED before the
  mount effect commits without a hydration mismatch) and hand it to the child out-of-band as
  a prop that affects no markup; seed the parent's state from that same ref so prop and state
  cannot diverge. Deferring the child instead (gating its effect on a "prefs ready" flag) was
  measured and is WORSE: it removes the wasted work but makes the child wait on the same
  ~1.05s commit, so first-repaint latency is unchanged at full speed and degrades to no chart
  at all under CPU load. Also: the live-candle merge itself is NOT a bottleneck — mutate ->
  series.update() -> DOM write totals 1.9-2.0ms, packet->DOM ~60ms, DOM->paint ~190ms — so do
  not go looking there. Reproduce CI-shaped timing with CDP Emulation.setCPUThrottlingRate;
  an M2 Studio is far too fast to show this class unthrottled.
kind: architecture
verified_at: 2026-08-26
verified_by: "mastermindx-market-intelligence/mastermind-terminal PR #478; terminal/components/ChartPanel.tsx EFFECT 2; terminal/components/TerminalShell.tsx startTfRef"
scope:
  - mastermind-terminal
  - terminal/components/ChartPanel.tsx
  - terminal/components/TerminalShell.tsx
confidence: verified
---

# A cold Terminal chart used to load the timeframe it was about to replace

Measured with the product's own `?boottrace=1` tracer (`cpMark`/`btMark`), which is
deliberately kept in production builds.

```
+121.9ms  chart-effect1-start[NVDA]
+133.2ms  chart-effect2-start[NVDA@3D]     <- data effect starts on the SSR default
+134.1ms  ohlc-fetch-start[NVDA]
+137.2ms  startup-tf=1s                    <- the app ALREADY KNOWS the answer here
+569.9ms  ohlc-fetch-done[NVDA]            <- 436ms fetching data it will discard
+576.7ms  chart-painted[NVDA@3D:daily]     <- full paint, discarded
+757.7ms  chart-effect2-start[NVDA@1s]     <- the real load finally starts, 625ms late
```

| cold, unthrottled (n=10) | before | after |
|---|---|---|
| first live repaint p50 | 2782ms | 1740ms |
| first live repaint p95 | 2816ms | 1771ms |
| discarded default-timeframe loads | 10 of 10 | 0 of 10 |

At 4x CPU throttle: 0 of 4 runs reached a first live candle before; 3 of 3 after
(9679 / 9866 / 10369ms).

## Hypotheses that were measured and are DEAD

- **The live merge.** 1.9-2.0ms total per tick.
- **Lazy imports / a suspended chunk blocking the commit.** Zero chunk requests between
  +130ms and the commit at +1178ms.
- **Chart invalidation.** The chart repaints the moment state changes.

## Residual, deliberately not fixed in #478

The visible-chart fast lane is a fixed 1 Hz `setInterval` in `TerminalShell.tsx`
(`pollChartQuotes`), so the first repaint still waits up to one poll boundary (~500ms mean)
after the chart is ready. That code sits inside PR #429's changed hunks (2265-2395), so #478
left it alone rather than racing it.

Note also that ~1s of any `live-candle` measurement is `expect.poll` backoff, not product
latency: its interval reaches 1000ms, and in one run the DOM carried revision 1 at 3819ms
while the test only observed it at 4772ms.
