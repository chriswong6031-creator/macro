# Forex Vector — design & data spec

A dollar-first currency signal board (`site/forex.html`), a structural clone of the
Commodity Vector. This doc is the spec the code and `config.yml forex:` block follow.
Honest caveats live in [LIMITATIONS.md](../LIMITATIONS.md#forex-vector-forexhtml);
engineering rationale in [DECISIONS.md](../DECISIONS.md) (`2026-06-13 — Forex Vector`).

Built from a research + adversarial-review workflow (5 codebase readers + 4 FX
research agents → synthesis → skeptical critique). Verdict: build, with the dollar
double-count, carry-data, and peg fixes folded in below.

## 1 · Why these pairs, and the macro they encode

The dollar is the master variable (~89% of FX turnover routes through USD), so the
model is "broad-dollar move + each currency's idiosyncratic story." Pairs cluster
into archetypes, and each archetype *is* a macro signal:

| Pair | Archetype | Macro it encodes |
|---|---|---|
| DXY / `DTWEXBGS` | dollar master | The dollar smile: USD strong in BOTH a US-led boom and global risk-off; weak only in calm synchronized growth |
| EUR/USD | major (anti-dollar) | Deepest pair; the cleanest Fed-vs-ECB real-rate-gap read |
| USD/JPY | haven-funder | Rate-differential + carry-funding; yen unwinds violently in risk-off; BoJ + MoF intervention (~150–162) |
| GBP/USD | major (fiscal-risk) | UK-US rate gap + twin-deficit / gilt risk (2022 LDI ⇒ quasi-EM) |
| AUD/USD | commodity-dollar | China/growth + terms-of-trade proxy (iron ore, copper); the risk-on barometer |
| USD/CAD | commodity-dollar | The oil currency (CAD ~ WTI) |
| USD/CHF | haven-funder | CHF rises in risk-off; SNB-capped (2015 gap) |
| USD/CNH | EM · managed | China proxy + EM-Asia anchor; PBoC fix sets the regime |
| USD/MXN, USD/BRL | EM carry | High-carry tails; contrarian-positioning + commodity/fiscal beta |

Currency archetypes drive everything: **funders/havens** (JPY, CHF, USD) rally in
risk-off; **carry/commodity/risk** currencies (AUD, NZD, EM) fall. **Terms-of-trade**
currencies track their export basket (CAD~oil, AUD~iron/copper). Transmission chain
the board surfaces: real-rate differentials → carry → risk sentiment (RORO) → the
dollar → EM stress + commodities (inverse) + global financial conditions.

## 2 · The factor model (per-pair, naive-bullish in [-1,1] on the BASE currency)

Each pair's price-layer factors are computed on the **dollar-orthogonalized residual**
(see §3). All free/keyless.

| Factor | Computation | Source | Phase |
|---|---|---|---|
| Trend | 12-1m TSMOM on the residual → `tanh(ret/scale)` | Yahoo spot | 1 |
| Structure | swing/breakout structure on the residual | Yahoo spot | 1 |
| Carry | foreign short/policy rate − US (`DFF`), vol-penalized | FRED rates | 1 |
| Risk appetite | global risk-off composite × archetype risk-beta (havens flip) | FRED/Yahoo | 1 |
| Risk index | per-pair realized-vol/drawdown saturating 0–100 | Yahoo spot | 1 |
| Residual shock | causal expanding-fit decoupling (intervention/geopolitics) | derived | 1 |
| Positioning | CFTC COT net-spec %OI percentile (contrarian) | CFTC COT | 1* |
| Value (REER) | −z of BIS REER gap vs 5y mean (pub-lag shifted, no look-ahead) | FRED `RB*BIS` | 3 ✅ |
| Rate diff (10y) | z of Δ(foreign 10y − US 10y) — relative monetary policy | FRED `IRLTLT01*`/`DGS10` | 3 ✅ |

\* COT depends on CFTC uptime (503 at first build → drops gracefully until collected).

The **dollar is NOT a per-pair factor** — it is handled architecturally (§3) and shown
in the master tile, so it is measured once and never double-counted across USD pairs.

## 3 · Signal methodology

Per-pair conviction reuses the commodity engine's assembly (`[-100,+100]` weighted
mean of signed factors → STRONG/weak/FLAT bands at ±60/±20 → factor-agreement
confidence), but FX-specific:

- **Dollar-first / orthogonalize.** Each pair's price layer runs on the residual after
  a rolling causal regression on the broad dollar (`DTWEXBGS`). The board is therefore
  NOT one repeated dollar bet. A **dollar-day haircut** shrinks confidence when the
  broad-dollar daily move dominates (false-consensus guard).
- **Risk-context headline.** UIP failure + carry crash skew ⇒ the headline is a
  regime/risk read; LONG/SHORT-base is the secondary chip; the crash-skew caveat is
  inline. Confidence is dampened ×0.6 while un-calibrated (Phase 1).
- **Carry honestly.** Differential of policy/short rates (step functions → ffill is
  correct); vol-penalized; EM = context-only (no free front-end rate).
- **Regime conditioning (Phase 2+).** Up/down-weight carry vs trend/value by the
  risk regime (VIX/NFCI) and the growth/inflation quad.
- **Peg / intervention override.** Managed `USD/CNH` → FLAT; `USD/JPY` MoF watch zone
  caps `|score|`; SNB history flagged. Calibration must excise peg windows.

## 4 · Architecture (mirrors the commodities section)

| File | Role | Mirrors |
|---|---|---|
| `config.yml forex:` | assets/orientation, drivers, factor params, bands, peg flags | `commodities:` |
| `engine/forex_inputs.py` | canonical base-vs-USD price (invert USD/xxx), rates, COT, drivers | `commodity_inputs` |
| `engine/forex_signals.py` | orthogonalize, carry, FX residual-shock, risk-off, dollar master; reuses the commodity price layer | `commodity_signals` |
| `engine/forex_conviction.py` | FX factor panel + risk-context verdict + peg override + dollar-day haircut | `commodity_conviction` |
| `scripts/build_forex.py` | dollar master VM + per-pair VMs → `forex.html` + `data/forex/latest.json`; returns 0 on error | `build_commodities` |
| `templates/forex.html.j2` | dollar-first hero + per-pair board + factor bars + honesty footer; bilingual | `commodities.html.j2` |
| `tests/test_forex.py` | orientation cross-check, orthogonalization invariance, carry sign, peg caps | `test_commodity_*` |

Data is config-only: `yahoo.tickers.fx`, `fred.series.{fx_rates,fx_dollar_legs,
fx_rates_short,fx_rates_long,fx_reer}`, `fred.series.credit.BAMLEMCBPIOAS`, and
`cot.markets` currency prefixes — the existing Yahoo/FRED/COT adapters need no code.

## 5 · Data sources (all free/keyless; `FRED_API_KEY` recommended at 100+ series)

- **Spot:** Yahoo `EURUSD=X … USDBRL=X`, `DX-Y.NYB`; cross-checked vs FRED `DEX*`
  (orientation map: `DEXUSEU/DEXUSUK/DEXUSAL` are USD-per-FX, the rest FX-per-USD).
- **Dollar legs:** FRED `DTWEXBGS` + `DTWEXAFEGS` (advanced) + `DTWEXEMEGS` (EM).
- **Carry rates:** FRED `DFF`/`DTB3`/`SOFR` (US) + `ECBDFR` + `IR3TIB01*`/`IRSTCI01JPM156N`.
- **Value:** BIS REER via FRED `RB{US,XM,JP,GB,AU,CA,CH,MX,BR,CN}BIS` (monthly).
- **Risk:** `VIXCLS`, `BAMLH0A0HYM2` (HY OAS), `BAMLEMCBPIOAS` (EM OAS), `NFCI`, `^MOVE`,
  copper/gold (`HG=F`/`GC=F`), `SPY`, `EEM`.
- **Positioning:** CFTC COT (legacy `6dca-aqww`) currency futures.

## 6 · Phasing

- **Phase 0 — config + collect** ✅ — forex config; collected 8 FX pairs (to 1996–2006),
  FX reference rates, dollar legs, short rates, REER, EM OAS; COT pending CFTC recovery.
- **Phase 1 — dollar master + 3-pair board** ✅ — EUR/USD, USD/JPY, AUD/USD; dollar-smile
  hero; risk-context conviction; orthogonalization; carry; peg override; bilingual page;
  10 FX tests (136 total green). Un-calibrated (prior weights, dampened confidence).
- **Phase 2 — calibration** ✅ — `calibrate_forex.py`: split-half (split 2015) Spearman-IC
  of each factor vs forward base-vs-USD returns, peg windows excised → PRIOR-ANCHORED
  signed weights (flip robustly-INVERTED, halve DIRECTIONAL, down-weight CONTEXT — NOT raw
  IC, which overfits) + per-factor verdict glyphs on the page. `score_reliable` needs ≥2
  robust factors; report in `reports/forex-calibration.md`. Findings: USD/JPY trend
  CONFIRMED, GBP riskoff CONFIRMED, carry INVERTED (forward-premium puzzle). See D-FX7.
- **Phase 3 — full board + depth** ✅ (partial) — all 9 pairs live, archetype-grouped
  (Majors / Commodity-dollars / Haven-funders / EM); REER **value** factor (pub-lag
  shifted) + **10y rate-diff** factor wired and calibrated (value CONFIRMED for EUR/AUD,
  INVERTED for JPY; rates mostly CONTEXT — monthly-lagged data); cross-pair **carry &
  valuation table**; USD/CNH backfilled from FRED onshore (`DEXCHUS`). Value tipped
  EUR/JPY/AUD to RELIABLE. **Deferred to Phase 3.5:** MTF confluence (the commodity
  equity-preset needs FX validation first) and the alerts/timeline engine (FX wants
  hourly data we don't collect); COT positioning table waits on CFTC recovery.
- **Phase 4 — integration** — cross-page nav links + hub card across all sections;
  optional catalyst annotation.

## 7 · Honesty bar

These are RISK-CONTEXT reads, not trade signals or measured alpha. FX violates UIP,
carry has fat-tailed crash risk, pegs truncate distributions, and FX history is short
and crash-dominated. Phase 1 ships before calibration deliberately — to validate the
architecture on real data before investing in the full board — and says so on the page.
