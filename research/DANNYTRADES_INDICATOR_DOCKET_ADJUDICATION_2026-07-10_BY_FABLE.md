# DannyTrades Indicator Docket — Adjudication (DT-R17..DT-R24)

Adjudicated by Fable, 2026-07-10.

Input: `research/DANNYTRADES_INDICATOR_BUILD_DOCKET_FOR_FABLE.md` (Codex, 2026-07-09;
committed verbatim in this PR per docket Lane 0). Operator directive (2026-07-10):
add the technicals to the Mastermind Terminal indicator suite; other routing at
Fable's discretion.

Binding priors: DANNYTRADES adjudication DT-R1..R16, `research/DO_NOT_REBUILD.md`
DannyTrades rows, Signal Commons R3, ESX §9 / RUL-P8, LH-R2, EI PM0 PREREG.

## 0. State changes since the docket was written

The docket's central build blocker is gone:

- PR #1840 (StockInvest technical-indicator machine): **CLOSED**, superseded.
- PR #1891 (StockInvest Technical Lab, supersedes #1840, + composite-bound and
  screener-firing robustness fixes): **MERGED 2026-07-09T19:39Z**.

The technical lab now exists on main: `engine/lab.py` façade, `engine/tech_catalog.py`
registry (~46 signals across 8 families), `scripts/build_tech_lab_data.py` (off-render),
`site/tech_lab.html`, NW wiring as DARK context (`adapt_tech_signals`, direction=0,
ungraded). Docket Lane 1 ("no code until #1840 settles") is therefore **RELEASED**.

Also verified current: EI PM0 price-memory PREREG approved 2026-07-06 but **not yet
executed**; S-SQ (species S16 squeeze-release) cleared phase-0 → **ACCRUING**
2026-07-07 (unshipped, no-CHIP cap per RUL-P8); DT void-box def-4 variants therefore
newly *eligible* for registration.

## 1. Rulings

### DT-R17 — Docket adopted as canonical source inventory (Lane 0)

The Codex docket is ACCEPTED and committed verbatim as the canonical DannyTrades
public-indicator inventory and routing map. Its §7 reject list is re-affirmed in
full (see DT-R23). Its indicator passports are design references, not chartered
artifacts. No DannyTrades-branded engine, lobe, score, or authority family is
created by this adjudication.

### DT-R18 — Chart-grammar families route through the merged tech-lab (Lane 4 delivered repo-natively)

With #1891 merged, the docket's "route through the technical-lab / indicator-event
bus" instruction is now executable. Four **display-tier descriptive** signal
families are AUTHORIZED for `engine/tech_catalog.py`:

| Family | Signals | Docket source |
|---|---|---|
| `ichimoku` | above/below cloud (states), tenkan/kijun cross up/down, cloud breakout/breakdown (events) | §3.13 |
| `trend_ribbon` | ribbon_up/down (states), ribbon_flip_up/down (events) — math imported from `engine.dannytrades.ribbon_trend` (one-canonical-source law) | §3.1 / §3.11 |
| `rsi_stack` | curl_up/curl_down (events), stack oversold/overbought (states) — periods **frozen 7/14/21** before any measurement, per §3.5's freeze requirement | §3.5 |
| `bollinger_events` | upper rejection, lower reclaim (events), band-walk up/down (states) | §3.14 |

Constraints carried: PIT-clean (Ichimoku spans `.shift(displacement)`), bilingual
display, no authority (catalog signals enter NW as direction=0 ungraded context;
promotion only via the standing Article-3 gauntlet). A separate Danny-branded
`dt_public_panel_state` artifact is NOT built — the tech-lab screener/lab pages are
the descriptive panel surface; a branded duplicate adds nothing (docket §0 point 4).

### DT-R19 — Mastermind Terminal indicator suite AUTHORIZED (operator directive)

Eight user-toggled charting indicators are added to the Terminal's built-in
indicator registry (`charting-app/terminal/lib/indicators.ts` + `ChartPanel`),
computed client-side from the Terminal's own OHLCV bars:

Ichimoku Cloud; Trend Ribbon (EMA 20/50 band + trend-state candle coloring);
SuperTrend; Anchored VWAP; Volume Profile (POC/VAH/VAL, optional money-flow-weighted
"shelf" mode — docket §3.7–3.9 grammar); Volatility Box (compression box rails —
§3.6 grammar); RSI Stack (7/14/21 — §3.5); Accumulation % (63d close-in-range
money-flow share — §3.3 proxy, descriptive labeling, 35/50/75 rendered only as
labeled reference bands).

Auto-Fibonacci and auto-trendlines already exist in the Terminal (`lib/drawings.ts`)
— §3.12 / Panel-2 need no new build.

Ruling basis: charting indicators are user tools on a charting surface — display
tier by construction, out-of-repo (Mastermind side), no NW/signal path, no ranker
contact. The gauntlet is a promotion gate, not a build gate; nothing here promotes.
DT-R11a (display-only, no "validated") carries to the Terminal UI. No composite
score, no buy/sell markers, no threshold-as-signal semantics.

### DT-R20 — Naming law

"Whale" identity vocabulary and "Danny"/"DannyTrades" branding are excluded from
all new code identifiers, artifacts, and UI strings (docket §1: OHLCV cannot
identify who traded). Sanctioned vocabulary: accumulation / money-flow /
sponsorship-proxy. Public threshold values (35/50/75) may appear only as
clearly-labeled reference bands. Existing legacy identifiers inside
`engine/dannytrades.py` are grandfathered but must not propagate to new surfaces.

### DT-R21 — PM0 price-memory execution is the top research follow-up; not run here

Docket Priority 1 (momentum bars / POC / volume shelf / chip shelf → one governed
price-memory family) was already dispatched by DT-R7 into
`research/entry_intel/PM0_PRICE_MEMORY_BUNDLE_PREREG.md` (approved, red-teamed,
DT-R14-compliant). Execution (feature builder + QA + calibration gates + the m=20
FDR budget) belongs to the EI program as its own dispatch — it is a one-shot FDR
budget and will not be spent as a side effect of a UI build. The Terminal Volume
Profile (DT-R19) is display-tier and does not pre-empt or contaminate PM0.

### DT-R22 — Void-box def-4 unblocked for registration under S-SQ

S-SQ S16 cleared phase-0 → accruing (2026-07-07). Per DT-R5, void-box definition 4
(RV-collapse-after-drawdown conditioning) and retest/false-break state extensions
are now ELIGIBLE for registration as S-SQ variants. Not registered in this
adjudication; requires its own pre-registration with family + FDR budget declared.
The no-CHIP cap (RUL-P8) remains until eq_band NC-2 ships.

### DT-R23 — Reject list re-affirmed

Docket §7 is re-affirmed verbatim as standing law: no `danny_buy_score` /
`danny_sell_score` / whale directional signals; no 35/50/75 as buy/sell authority;
no fused sponsorship composite (Signal Commons R3); no DCA/stop/no-chase policy
objects (DT-R2/R7); no pooled multi-decade result without era split (DT-R16); no
ticker-cluster-only inference (DT-R14); no LLM-originated numbers; the descriptive
`dt_contra` state is not a prediction (DT-R15). Nothing in DT-R18/R19 creates a
promotion path for any of these.

### DT-R24 — No new NW→Mastermind bridge wiring in this build

The Terminal computes its indicators client-side from its own Polygon OHLCV; no new
`mastermind:context` tags, no `dt_contra_state` bridge export, no forwarding of
`vol_squeeze` box levels through `pull_macro_intel.py` in this wave. Candidate
follow-up (unchartered): forward the `vol_squeeze` block into `intel.json` so the
server-computed squeeze state can be compared against the Terminal's client-side
volatility box.

## 2. Build map of record (this adjudication)

| Lane | Repo | Deliverable | Status |
|---|---|---|---|
| Docs (this PR) | Macro Dashboard | docket copy + this adjudication | this PR |
| DT-R18 | Macro Dashboard | 4 catalog families, 18 signals + tests, draft PR pending review | building |
| DT-R19 | charting-app (local-only repo) | 8 Terminal indicators, branch `feat/dt-technicals-suite`, Playwright-verified | building |
| DT-R21 | Macro Dashboard | PM0 execution dispatch | EXECUTED 2026-07-10 (EI-PM0 r4; PM2 survives display-only, PM1/PM3 falsified, PM4 redundant, PM5 data_blocked) |
| DT-R22 | Macro Dashboard | void-box def-4 S-SQ registration | eligible, unregistered |
| Docket Lane 5 | — | monthly exhaustion trim review | remains DEFERRED (DT-R8) |
| Docket Lane 6 | Mastermind | concentration/held-book behavior | remains Mastermind-only (DT-R6) |

## 3. Clocks

- 2026-07-20 (existing tech-lab come-back): fold first fire-metrics read of the new
  chart-grammar families into the tech-lab review.
- 2026-08-10: PM0 execution dispatch check — if the EI lane has not run PM0, re-raise.
- Standing: S-SQ def-4 registration rides the next S-SQ wave, not a clock.
