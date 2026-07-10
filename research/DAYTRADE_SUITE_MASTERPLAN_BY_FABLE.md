# Day Trade Suite — masterplan & rulings (Fable program, 2026-07-10)

Operator ask: "intraday trading suite kit in Terminal … advanced intraday day-trading
technical indicators … a button that launches day-trading mode with a full suite for
low-timeframe trading." Target repo: `mastermind-terminal` (~/Documents/Cluade/charting-app),
Next.js + lightweight-charts v5 Terminal at app.mastermind-x.com. Everything display-tier
descriptive (no signals, no scores) — ships freely per the gauntlet-is-promotion-gate law.

Program artifacts: build spec `docs/DAYTRADE_SUITE_SPEC.md` (terminal repo, same PR as the
build); this masterplan (macro repo, program record). Research basis: 5 web lanes (VWAP
ecosystem, levels/ORB/pivots, LTF momentum/vol, OHLCV-only volume analytics, day-mode UX
teardowns) + 4 code-reader maps; all lane reports in session transcripts.

## Context found (why this was the right build)

The Terminal already had full intraday plumbing — 1m–4h TFs (Polygon US incl. extended
hours; Tencent CN/HK; ~6y 1h + ~400d 5m US history store on the VPS) — but **zero
session-aware indicators**: VWAP was cumulative-from-first-loaded-bar (never reset at
09:30), no opening range, no PDH/PDL/session levels, no RVOL. The day-trading gap was
real, not cosmetic.

## The suite (8 new registry indicators)

Overlays: **Session VWAP + σ-bands** (`svwap`), **Opening Range** (`orb`),
**Session Levels** (`slevels`: PDH/PDL/PDC/Open/PMH/PML + PWH/PWL toggle),
**Pivot Points** (`pivots`: Classic/Camarilla/Fibonacci).
Panes: **Relative Volume** (`rvol`, time-of-day slot method), **TTM Squeeze** (`ttmsq`,
3-tier compression + linreg momentum), **ADX** (`adx`, len 10, 20/25 refs),
**Session CVD approx** (`cvd`, default OFF).
Plus **Day Trade Mode**: reversible one-click preset (Alt+D) — snapshot/restore of the
user's swing workspace; applies 5m + ext-hours + {EMA 9/20, svwap, vol, orb, slevels,
rvol} + session background shading + day-stats strip (Gap% / RVOL / range-used% / ΔVWAP /
HOD/LOD / session badge+ET clock) + bar-close countdown + Alt+1/2/3/4 TF hotkeys +
`?dtm=1` deep link.

## Rulings (DTS-R1..R10)

- **DTS-R1 — VWAP bands school**: cumulative **volume-weighted variance**
  (σ² = Σ(v·tp²)/Σv − VWAP², clamped ≥0), NOT rolling stdev of close — matches
  thinkorswim/Sierra canon. Session-anchored at 09:30 market-local; premarket excluded
  by default (`includePm` option). Multipliers 1/2/3; σ3 default-off visual tier.
- **DTS-R2 — ORB**: default 15-min range (5/30 options), extensions ±1×/±2× of range,
  drawn per-session for every session in view; academically the strongest intraday edge
  (Zarattini/Barbon/Aziz 2024, SSRN 4729284) but shipped as *levels display*, no signals.
- **DTS-R3 — Levels rendering**: session levels + pivots via LWC `createPriceLine`
  (axis labels, no autoscale distortion); opacity/style hierarchy by level class;
  R-family colored from `var(--down)`, S-family from `var(--up)` resolved at build time
  (East-Asian flip safe).
- **DTS-R4 — RVOL honest-null law**: time-of-day slot baseline (default 10 sessions,
  computed from loaded bars); **< 3 prior sessions → no output + amber "insufficient
  history" note**, never a silently-noisy number. CN/HK 1m (~2.5 sessions of Tencent
  window) therefore shows the note by design.
- **DTS-R5 — CVD honesty**: OHLCV close-position-in-range approximation may ship ONLY
  with a permanent "Est. CVD (OHLCV approx)" label (legend + source stub disclaimer)
  and default-OFF. True CVD needs tick/bid-ask data we don't have.
- **DTS-R6 — TTM tier semantics**: tier = tightest KC containing the BB
  (3 = inside 1.0×KC = extreme). Foundation lane shipped this inverted (any squeeze →
  tier 3); caught by the builder's own concern note + fixed in main loop + two
  discriminating unit tests added (exact-arithmetic alternation fixture). Squeeze dots
  use a non-directional intensity palette (muted/amber/orange/red) — not up/down vars.
- **DTS-R7 — Mode reversibility law**: Day Trade Mode must restore the prior workspace
  EXACTLY (inds, params, tf, favTF, chartType, extHours) from `mm.dtmSnapshot`; the
  toggle touches nothing outside its preset (drawings, watchlists, symbol untouched).
- **DTS-R8 — Rejected designs** (reasons recorded; NOT registry kills — display tooling
  can be revisited): HMA(9) (marginal over EMA9 display), Williams %R / RSI(2)
  (redundant vs stochrsi / rsi7), Chandelier exit (SuperTrend covers), standalone
  Keltner (subsumed by ttmsq), round-number lines (clutter/value), 4σ band (dead pixel),
  premarket-in-session-VWAP default (contaminates fair value), MTF side pane (split
  layouts already exist — deferred), news feed / DOM / P&L / any order entry (out of
  scope by product definition).
- **DTS-R9 — Intraday-only gating**: session indicators (svwap/orb/slevels/pivots/rvol/
  cvd) render nothing on D/W/M and show an amber "Intraday timeframes only" legend note
  (mirror of the Pine intraday block); ttmsq/adx work on all TFs.
- **DTS-R10 — New math isolation**: all new math in `lib/intradayMath.ts` (numeric
  display-epoch Bar type) with its own vitest suite; `lib/indicatorMath.ts` (Python-
  parity-fixture coupled) untouched.

## Process (quality-bar law applied)

Mockups-first (static HTML on real tokens, desktop+390px screenshots) → builders received
the actual PNGs; foundation (math+tests ∥ registry/i18n/shading ∥ mockups) → chart lane
(C1 overlays → C2 panes, serialized on ChartPanel.tsx) ∥ shell lane (D) with a fixed
C↔D interface contract (`mm:set-eth` CustomEvent + `dayMode` prop) → 2 opus adversarial
reviewers → main-loop browser verification against LIVE Polygon/Tencent data (dev server,
day mode on/off, CN lunch-gap, daily-TF regression, ZH + East-Asian flip, 390px) →
PR → same-day squash-merge → VPS deploy (`terminal-build.sh`) → live verification.
Model routing: Sonnet built, Opus reviewed, Fable (main loop) adjudicated/merged.

## Ops notes / known upstream issues

- Tencent HK minute kline (`ifzq.gtimg.cn … mkline`) returns "param error" for all HK
  code formats as of 2026-07-10 — pre-existing upstream breakage; HK intraday serves
  empty → existing "Back to Daily" empty state. CN (`sh…`/`sz…`) fine. Re-check later;
  if persistent, HK minute data needs an alternate source.
- Terminal repo has NO CI — `npm test` + `npx tsc --noEmit` are the only gates
  (`next.config.ts` `ignoreBuildErrors:true` still set), run manually pre-merge.
- RVOL depth: US 5m top-500 have ~400d stores; other US ride the 10–25d live window;
  1m everywhere = live-window only.

## Clocks

- **2026-07-24** (with the tech-lab come-back): read Day Trade Mode usage friction +
  any operator feedback; consider MTF side pane + anchored-VWAP session anchors
  (PM H/L, gap bar) as v2 if the mode earns use.
- **2026-08-15**: re-check Tencent HK minute endpoint; decide alternate HK intraday
  source if still dead.
