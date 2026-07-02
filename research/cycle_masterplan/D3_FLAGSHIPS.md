# PILLAR D3 — THE FLAGSHIPS: engine-backing cycle.html + markets.html

**Author:** principal quant-systems designer (Fable masterplan, solution phase)
**As of:** 2026-07-02 · designed against `/tmp/macro-cycle-fable-main/` (main @ a51665054e)
**Audit basis:** `research/CYCLE_INTELLIGENCE_PROBLEM_AUDIT_FOR_FABLE.md` Parts I–III + Part IV §A (cycle.html, 8 findings), §B (markets.html, 8 findings), plus §C/§D where the kernel is shared. Scout notes S1–S5 in this directory.

---

## 0. Design thesis

cycle.html's genuine, irreplaceable value is **the curated turning-point history and causal archetypes** — nobody else has hand-verified DRAM ASP turns, uranium spot turns, and the 18-yr land-cycle chronology in one place. Its fatal flaw is that the *same hand-typed JSON also sets every plotted number* (pos 91, cosine pins, cone widths, frozen TODAY=2026.48), laundering opinion into the visual authority of the sibling engines (audit A-1/A-2/A-3).

The fix is a **surgical ownership transfer, not a rewrite**: every plotted number moves to the engine; every prose claim stays but becomes dated, TTL'd, and machine-checked. The instrument for this is a per-cycle **PROXY REGISTRY** that declares, for each of the 23 cycles and 9 markets: which live tape backs it, at which frequency, under which kernel, and — where no decent tape exists — an explicit `NONE` that demotes the cycle to a **STRUCTURAL frame** whose falsifiers become machine-evaluated **tripwires** and whose hand-dated turns become the *only* (and honestly-labeled) turn source.

Three structural insights drive everything below:

1. **The two-tier split (T1) needs a third axis: DUAL-BAND cards.** Gold, dollar, Japan, and bitcoin each genuinely carry *both* a gradeable intermediate cycle on a deep daily tape (GC=F, DXY, EWJ, BTC-USD) *and* an ungradeable secular frame (17y gold, 15y DXY, 18y Nikkei, 4y halving). Forcing each cycle into exactly one tier either throws away a measurable object or launders an unmeasurable one. So: **tier is a property of a BAND, not a CYCLE** — one card can carry a MEASURED band + a STRUCTURAL band, visually separated.
2. **Flagships mostly sidestep the TR-contamination problem (T5) if we pick the right series.** Unlike the sector pages (stuck with ETF closes), 14 of the 23 flagships have non-equity level series available — futures (GC=F, HG=F, SI=F, CL=F), FRED spreads/rates/vol (BAMLH0A0HYM2, DGS30, VIXCLS), spot crypto (BTC-USD). These have **no dividend adjustment at all**. The dual-basis contract matters only for the ~6 ETF-proxied cards (SOXX, XBI, EEM, EWJ, TLT, DBA). But this creates a *new* kernel requirement T5 doesn't cover: **inverted-semantics and non-price level series** (credit = tight spreads at cycle top; vol = calm at top; long-bonds = low yields at price top).
3. **markets.html has no reason to exist as an engine.** Its 9 markets are a strict subset of `country_cycles` + SPX. Its unique content — turn history with real levels, valuation blocks, archetypes — is 100% overlay-shaped. Fold it in; keep every byte of curation as overlay data.

---

## 1. THE PROXY REGISTRY — `engine/cycle_proxies.py`

### 1.1 File + shape

New module `engine/cycle_proxies.py` — a **Python dict, source of truth**, exported to JSON at build (`site/cycledata/proxy_registry.json`) so JS never re-declares it (T2 discipline). No YAML: the registry embeds validation lambdas and comments; Python is the house pattern.

```python
# engine/cycle_proxies.py
"""Per-flagship proxy registry: which live series backs each cycle.html cycle /
markets.html market, at which frequency, under which kernel + tier.

tier:  "measured"    — engine computes every plotted number from `series`
       "structural"  — no gradeable tape; hand turns are the plotted turns,
                       rendered as a FRAME (see §3); tripwires still live
band:  a cycle may declare BOTH a measured band and a structural (secular) band
basis: "spot" | "futures_cont" | "fred_level" | "etf_tr" | "etf_px" | "index_px"
       — etf_tr entries MUST also name the structure_series once D-data-basis
       (dual-basis contract wave) lands; until then they run on TR with an
       on-card basis label (honest interim).
invert: True  → kernel runs on 1/x so "100 = risk-on/complacent" holds
        (credit: tight spreads = top; vol: calm = top; long-bonds: low yield = price top)
"""
from __future__ import annotations

REGISTRY: dict[str, dict] = { ... }   # §1.2 table, verbatim

def load_series(entry: dict) -> "pd.Series":
    """Resolve entry['series'] refs → one pd.Series (first available wins;
    'yahoo:GC_F' → store.read('yahoo','GC=F').close; 'fred:VIXCLS' →
    data/fred/VIXCLS.parquet value col; 'intl:_N225' → data/intl parquet).
    Applies entry['invert'] (s = 1.0/s) and freq resample ('ME' last for freq='M'
    when the raw tape is daily). Raises ProxyMissing(series_ref) if absent."""

def registry_report() -> dict:
    """Build-time health: per cycle {tier, series_found, rows, first_date,
    last_date, stale_days}. Written to data/cycle_flagships/registry_health.json;
    build FAILS (raise) if a `measured` cycle's tape is > 7 trading days stale."""
```

### 1.2 The registry itself — all 23 cycle.html cycles

Grounded in what exists **today** in `data/yahoo/` and `data/fred/` (verified by listing; see S1/S5). "ADD" = one config.yml line, zero collector code (collectors/fred.py:83 and yahoo.py iterate config).

| id | tier(s) | live series (priority order) | freq | basis | invert | zz | notes / fallback |
|---|---|---|---|---|---|---|---|
| semis | **MEASURED** | `yahoo:SOXX` (2001→); ADD `yahoo:^SOX` for the index falsifier level | D | etf_tr | – | vol-scaled | SMH dup not needed. WSTS sales: no free feed → archetype prose only |
| memory | **MEASURED-proxy** + STRUCT overlay | ADD `yahoo:MU` (1980s→) | D | equity_px(TR) | – | vol-scaled | DRAM contract ASP has NO free tape. MU = *labeled* equity proxy; hand ASP turns survive as structural overlay dots. Proxy-fitness gate §1.5 |
| housing | **STRUCTURAL** | monitors: ADD `fred:CSUSHPISA` (M), `fred:PERMIT`✅, `fred:MORTGAGE30US`✅, `yahoo:XHB`✅ | M | fred_level | – | – | 18y, n≈2 graded turns → never MEASURED. Full tripwire coverage (§4) |
| business | **MEASURED-M** | `fred:INDPRO`✅ + `fred:NEWORDER`✅ composite via existing `engine/business_cycle.py` leading index | M | fred_level | – | abs 1.5σ | ISM PMI is proprietary; NAPM dead on FRED. Rewire falsifier to PAYEMS/SAHMREALTIME (§4). Kitchin ~4y → ~7 turns/30y, gradeable at monthly horizon |
| oil | **MEASURED** | ADD `fred:DCOILWTICO` (1986→, spot, no roll artifacts); fallback `yahoo:CL_F`✅ | D | spot | – | vol-scaled | Prefer FRED spot over continuous futures for ZigZag cleanliness |
| copper | **MEASURED** | `yahoo:HG_F`✅ (2000→) | D | futures_cont | – | vol-scaled | falsifier $/t thresholds convert: $/lb × 2204.62 |
| uranium | **MEASURED-proxy** + STRUCT overlay | `yahoo:CCJ`✅ (1996→) | D | equity_px(TR) | – | vol-scaled | Spot U₃O₈: no free tape (UxC/Numerco paywalled). CCJ labeled proxy; hand spot turns = structural overlay. Alt considered+rejected: URA (2010→ too short), equal-weight mini-basket (adds membership PIT problem for zero gain) |
| gold | **DUAL**: MEASURED + STRUCT(17y frame) | `yahoo:GC_F`✅ (2000→) | D | futures_cont | – | vol-scaled | Measured band = intermediate cycle; 17y secular clock renders as frame band (§3.3) |
| bitcoin | **DUAL**: MEASURED + STRUCT(halving) | `yahoo:BTC-USD`✅ (2014→) | D | spot | – | vol-scaled (~40%+) | halving clock = structural band; keeps out of the hazard pool's equity family |
| credit | **MEASURED** | `fred:BAMLH0A0HYM2`✅ (1996→, append-only past FRED's 3y window) | D | fred_level | **1/x** | vol-scaled on 1/x | risk-on semantics preserved: tights=top. Loan-default falsifier leg dropped (no feed) |
| shipping | **STRUCTURAL** | NONE. BDI is Baltic-Exchange proprietary; WCI (Drewry) paywalled. Optional weak monitor: ADD `yahoo:BDRY` (2018→, tripwire-only, never plotted) | – | – | – | – | The honest NONE case. Manual falsifier w/ TTL (§4.4) |
| lithium | **STRUCTURAL** | NONE for spot Li₂CO₃ (Fastmarkets/SMM paywalled). Monitors: ADD `yahoo:ALB`, `yahoo:SQM`; `yahoo:LAC`✅ thin | – | – | – | – | equity monitors feed tripwires only; spot-price falsifier legs stay manual |
| agriculture | **MEASURED** | ADD `yahoo:DBA` (2007→, investable GSCI-ag proxy); ADD `yahoo:ZC_F` (corn, for the falsifier leg) | D | etf_tr | – | vol-scaled | DBA *is* the tradeable object → measured is honest |
| vol | **MEASURED** | `fred:VIXCLS`✅ (1990→); `yahoo:_VIX`✅ dup | D | fred_level | **1/x** | vol-scaled on 1/x | 100 = deep calm (risk-on convention per cycle_data.js header). ~2y period → richest turn sample of all flagships |
| biotech | **MEASURED** | `yahoo:XBI`✅ (2006→); `yahoo:IBB`✅ (2001→) secondary | D | etf_tr | – | vol-scaled | IPO-window leg of the thesis stays prose |
| long-bonds | **MEASURED** | `fred:DGS30`✅ (1977→) **inverted** = price-cycle clock; `yahoo:TLT`✅ overlay for the tradeable falsifier level | D | fred_level | **1/x** | abs 35bp → via 1/x pct | Yield series sidesteps TLT's huge TR distortion entirely |
| dollar | **DUAL**: MEASURED + STRUCT(15y frame) | `yahoo:DX-Y.NYB`✅ (1971→); `fred:DTWEXBGS`✅ broad-dollar secondary | D | index_px | – | vol-scaled (~8% floor 6) | DXY is price-basis already (no dividends) — clean |
| natural-gas | **MEASURED** | ADD `fred:DHHNGSP` (Henry Hub spot, 1997→); ADD `yahoo:NG_F` secondary | D | spot | – | vol-scaled (high) | storage falsifier leg (EIA weekly) NOT collected → leg dropped, price leg survives |
| iron-ore | **STRUCTURAL** | NONE for 62% Fe (SGX/Platts paywalled). Monitor: `fred:PCU331110331110`✅ (US steel PPI, M) + ADD `yahoo:SLX` | – | – | – | – | US steel PPI ≠ seaborne iron ore; honest NONE. China-property driver belongs to the China pillar |
| silver | **MEASURED** | `yahoo:SI_F`✅ (2000→) | D | futures_cont | – | vol-scaled | gold/silver ratio = derived series for tripwires |
| em-equities | **MEASURED** | `yahoo:EEM`✅ (2003→) | D | etf_tr | – | vol-scaled | MSCI-EM-index falsifier levels rewritten as EEM levels (§4) |
| japan | **DUAL**: MEASURED + STRUCT(secular) | `intl:_N225`✅ (1965→, local-ccy!) primary; `yahoo:EWJ`✅ (USD) as FX-decomposed second leg per D-country pillar | D | index_px | – | vol-scaled | The ONE flagship where local-vs-USD legs both already exist in-repo (S4). 61y of tape |
| pgms | **MEASURED** | ADD `yahoo:PL_F` (PL=F platinum), ADD `yahoo:PA_F` (PA=F palladium) | D | futures_cont | – | vol-scaled | ⚠ `PL` already exists in data/yahoo = **Planet Labs**. Registry must use explicit `PL=F` yfinance symbols — see New Problem NP-3 |

**Tier census:** 14 MEASURED (incl. 4 DUAL measured bands), 2 MEASURED-proxy, 1 MEASURED-M, **4 STRUCTURAL-only** (housing, shipping, lithium, iron-ore), + 4 structural secular bands on DUAL cards. Every STRUCTURAL assignment is forced by a real data gap or an n≈2 turn count, never by laziness — this is the T1 split made concrete.

### 1.3 The registry — 9 markets.html markets

All nine resolve to tapes **already collected**; the engine already computes 8 of them. Registry entries exist only to bind overlay data and declare the flagship subset:

| market | series | already in country_cycles? |
|---|---|---|
| us | `yahoo:SPY`✅ (+`yahoo:_GSPC`✅ for falsifier levels) | NO → add a `FLAGSHIP_US` entry (kind="country", group="North America") to `engine/country_cycles.py` COUNTRIES |
| canada | `yahoo:EWC`✅ | yes |
| uk | `yahoo:EWU`✅ | yes |
| europe | `yahoo:VGK`✅ | yes (aggregate) |
| japan | `yahoo:EWJ`✅ / `intl:_N225`✅ | yes |
| taiwan | `yahoo:EWT`✅ | yes |
| india | `yahoo:INDA`✅ | yes |
| hk | `yahoo:EWH`✅ | yes |
| china | `yahoo:FXI`✅ | yes |

Local-index falsifier/turn levels (Nikkei 73,000; SPX 7,358…) are preserved in the overlay, keyed to the local-ccy tape where it exists (`_N225`, `_GSPC`) — the D-country FX-decomposition wave (S4: 8 HIGH-feasibility markets) upgrades the rest.

### 1.4 Config additions (one wave, Haiku-able)

`config.yml`:
- `fred.series.housing`: + `CSUSHPISA` (Case-Shiller SA, M)
- `fred.series.energy` (or new group `flagship_cycles`): + `DCOILWTICO`, `DHHNGSP`
- `yahoo.tickers` new group `flagship_cycles`: `MU, ALB, SQM, DBA, ZC=F, NG=F, PL=F, PA=F, ^SOX, BDRY, SLX`

All append into existing collector loops (fred.py:83; yahoo.py config-driven). **History caveat:** FRED serves a rolling 3y window since Apr-2026 (S5) — but CSUSHPISA/DCOILWTICO deep history must be seeded once. `collectors/fred.py` is append-only; the seeding path is the standing `intl page deploy seed` pattern: run one backfill fetch via the FRED API host (ungated, per `fred keyless ua waf` memory) with `observation_start=1970-01-01` and commit the parquet. **Acceptance for the wave includes verifying ≥30y of CSUSHPISA rows land.**

### 1.5 Proxy-fitness gate (for the two MEASURED-proxy cards)

A proxy tier claim must be *earned*, not asserted (T4 discipline). At compile, `engine/cycle_proxies.py::validate_proxy(entry, hand_turns)`:

- Run the appropriate kernel on the proxy tape; extract major turns (`mag ≥ _MAJOR_PCT`-equivalent).
- Match each hand-researched turn (memory: DRAM ASP turns; uranium: spot turns) to the nearest same-kind engine turn; compute `median_abs_offset_months` and `match_rate` (hand turns with an engine turn within 25% of the median half-cycle).
- **Gate:** `match_rate ≥ 0.7` AND `median_abs_offset_months ≤ 6` → the proxy may render as MEASURED-proxy with an on-card chip "measured on MU (equity proxy)". Fail → the cycle auto-demotes to STRUCTURAL and the build logs it. Result stored in `data/cycle_flagships/proxy_fitness.json` — the word "proxy-validated" thereby has a stored artifact (T4).

---

## 2. THE MONTHLY KERNEL (N1) — `record_series()` in `engine/sector_cycles.py`

### 2.1 Why extend, not fork

`_record_core` (sector_cycles.py:291) is already a pure function of one close series (S2: PIT-pure, all overlays absent). The flagships need three capabilities it lacks: **monthly bars**, **inverted semantics**, and **abs-threshold ZigZag** for bounded diffusion-style series. Fork-and-drift is the disease this masterplan is curing — so: ONE new public wrapper in the same module, delegating to the same primitives, with the ontology contract (D1 pillar) declaring both kernels as implementations of the same semantic.

### 2.2 Signature + exact behavior

```python
def record_series(full: pd.Series, *, win_start: pd.Timestamp, last_ts: pd.Timestamp,
                  freq: str = "D",              # "D" | "M"
                  invert: bool = False,          # s ← 1.0/s before ALL math
                  zz_pct: float | None = None,   # None → _zz_pct_for(s) (vol-scaled)
                  zz_abs: float | None = None,   # abs-units reversal (ISM-like); wins over pct
                  trend_span: int | None = None, # detrend EMA span (bars)
                  stoch_win: int | None = None,  # stochastic window (bars)
                  ladder: bool | None = None,    # None → (freq == "D")
                  ) -> dict | None:
    """Superset of _record_core for any level series at daily or monthly frequency.
    Emits the IDENTICAL record schema (price/osc/turns/proj/now{...}) so every
    downstream consumer (JS renderers, backfill, hazard pool, graders) is
    frequency-agnostic. Adds:
      now.freq            ("D"|"M")
      now.basis           (from the registry, threaded by the caller)
      now.hazard_features (§2.5)
    Monthly rules (freq="M"):
      • bars are month-end; min length 72 bars (6y) vs 60 for daily
      • detrend: trend_span=60 (5y EMA), stoch_win=60, smooth=3
        [daily: 252/252/10 — unchanged]
      • direction votes for _classify_phase: monthly MACD(6,13,5) replaces the
        weekly MACD (weight ×2); the 3-bar osc slope replaces the 3D MACD as the
        secondary vote (±1 when |slope₃ₘ| > 3); same vote arithmetic
      • cycles.analyze() is NOT called; timing_state/action/dc_phase = None
        (the ontology crosswalk must declare the ladder sub-read OPTIONAL,
        keyed on now.freq — D1 dependency)
      • osc_slope: osc[-1] − osc[-4] (3 months ≈ the daily kernel's 22-bar month)
    invert=True: s = 1.0/s BEFORE detrend/ZigZag/phase; turns[].px is reported in
      ORIGINAL units (re-invert for display); ZigZag % thresholds are ~symmetric
      in log space so 1/x preserves them.
    zz_abs: _detect_swings_abs — pivot confirmed when |p − ext| ≥ zz_abs
      (for bounded/diffusion series where % of level is meaningless, e.g. a
      z-scored business composite: zz_abs = 1.5 σ-units).
    """
```

Implementation notes:
- `_detect_swings_abs` is a 15-line clone of `_detect_swings`'s loop with the two threshold comparisons swapped (`p <= ext_px - zz_abs` etc.) — keep both in the module, both returning the same swing-dict shape (`provisional` flag included).
- `_detrended_osc` gains the `trend/win/smooth` passthrough it already has as params — zero change.
- `_classify_phase` is reused verbatim: it takes `(pos, slope, w_votes, t3_votes, above200)`; the monthly caller passes `w=monthly_macd_state, t3={}` and the slope. `above200` becomes `above_20m` (20-month ≈ 200d equivalent: `full.iloc[-1] > full.iloc[-20:].mean()` on monthly bars).
- **One ontology semantic across kernels (T2):** the compiled ontology declares `position := detrended-stochastic percentile (trend 1y-equiv, window 1y-equiv... monthly uses 5y/5y for macro cycles)` — the *parameters* differ by frequency, the *semantic* ("where the series sits in its own detrended cyclical range") does not. The registry stamps `trend_span/stoch_win` per cycle so the choice is versioned data, not code folklore.
- `_record_core` itself becomes a thin call: `record_series(full, win_start=..., last_ts=..., freq="D", zz_pct=pct)` — **zero behavior change for the three existing engine pages** (regression gate: byte-identical `sector_cycles_data.js` on rebuild).

### 2.3 Monthly ZigZag defaults per registry entry

- `CSUSHPISA` (if ever promoted): zz_pct 5.0 — CS is ultra-smooth; 5% catches 2006-07/2012-02/2022 wobble.
- business composite: `zz_abs = 1.5` on the z-scored leading index.
- Monthly `_zz_pct_for` variant: annualize from monthly returns (`vol = r_m.std()*sqrt(12)`), base threshold 8% at 22% vol, floor 5%, cap 30%.

### 2.4 Cost budget

Daily kernel ≈ 56ms/series (S2, measured). Flagships: ~20 measured series × 56ms ≈ 1.2s + parquet I/O ≈ **< 10s added to the 67-min render**. Monthly kernel on 800-bar-capped series: <5ms. Backfill (T4, wave W7): 20 series × 180 month-ends × 56ms ≈ **3.4 min one-off** (with the `_cycle_fix_backtest.py` 800-bar cap ported — mandatory per S2).

### 2.5 Hazard features (T3 hand-off)

Every `record_series` stamp emits, under `now.hazard_features`:

```python
{"age_in_phase_bars": int,      # bars since the phase label last changed
 "age_since_turn_bars": int,    # bars since last confirmed (non-provisional) pivot
 "pos": float, "osc_slope": float,
 "amp_leg_pct": float,          # % move since last confirmed pivot
 "median_half_yrs": float, "n_turns_all": int,
 "freq": "D"|"M", "family": "flagship"|"sector"|"country"|"basket"}
```

This is the exact feature row the D-hazard pillar's pooled discrete-time hazard model consumes; flagships join the cross-sectional pool with `family="flagship"` shrinkage. **Flagship cones are replaced by hazard cones only after that pillar's calibration artifact exists** — until then, MEASURED cards show the median-half-cycle IQR band (already honest: "typical rhythm, not a backtested forecast", sector_cycles.js:289-299) and STRUCTURAL cards show no cone at all (§3.3). N3 compliance: flagship grading horizons are **phase-scaled** — `H_bars = clip(round(0.25 · period_central_yrs · bars_per_year), 21, 252)` for return grading, plus hazard-calibration windows 1/3/6m for turn grading; never a flat 21d on an 18y cycle.

---

## 3. THE TWO-TIER PRODUCT (T1) — rendering spec

### 3.1 Data flow replacing cycle_data.js

`scripts/build_cycle.py` becomes a real builder (it is currently a shell-copier, audit A-1):

```
engine/cycle_flagships.py::compute(asof=None) ->
  for cid, entry in REGISTRY:
      if measured band: series = cycle_proxies.load_series(entry)
                        rec = sector_cycles.record_series(series, **entry.kernel_args)
      structural band:  rec = {"turns": overlay.turning_points, "frame": {...}}  # §3.3
      merge overlay (§5); attach tripwire states (§4)
  -> data/cycle_flagships/flagships.json      (engine artifact, committed)
  -> site/cycledata/flagships.js               (window.CYCLE_FLAGSHIPS = {...})
scripts/build_cycle.py: render cycle.html.j2 with tier-aware cards; copy assets.
site/cycle_data.js: DELETED (after W3 ships); cycle_app.js reads CYCLE_FLAGSHIPS.
```

Hand-authored content moves **out of site/** into `data/cycle_flagships/narratives.json` (§5) — site/ stops being a source directory for this page (matches `theme-assets-source-is-templates` doctrine).

### 3.2 MEASURED card (and the measured band of DUAL cards)

Rendered exactly like a sector_cycles card (the visual language users already know): rebased price (or level) line + 0-100 osc + engine ZigZag turns + IQR projection band, `now.pos/phase/signal` all engine-owned. Additions:

- **Tier chip** top-right: `⬤ MEASURED` (l-en "MEASURED · engine-computed" / l-zh "实测 · 引擎计算"). MEASURED-proxy variant: `⬤ MEASURED (MU proxy)` with a hover note citing `proxy_fitness.json` numbers.
- **Basis label** under the chart: "GC=F futures, price basis" / "SOXX ETF, total-return basis (dividend-adjusted)" — the T5 honesty label, dual-span.
- **Graded badge** (`✓ graded · n=…`) appears ONLY when the shared grader (D-measurement pillar) has a matured scorecard artifact for this cycle; until then the chip reads `accruing` — never fake it.
- Inverted series annotate the y-axis: credit card's osc axis reads "100 = tightest spreads (complacent)".

### 3.3 STRUCTURAL card (and the secular band of DUAL cards)

The honest frame rendering. What STRUCTURAL **loses**: the 0-100 oscillator, `now.pos`, BUY/SELL signal, "% to next turn", the projection cone, and any graded badge. What it **keeps/gains**:

- **Secular age-dial** — replaces the oscillator hero. A horizontal band spanning `period.low → period.high` years with a marker at `years_since_last_hand_turn` (computed from wall-clock TODAY, §7): housing renders "year 14.4 of a 15–20y upswing (central 18y)". Pure arithmetic on curated turns + real time; no fake precision.
- **Hand-turn timeline** beneath: the curated turns[] as dots with `v` levels and `e` events — **the crown-jewel content, now labeled as what it is** (chip: `▢ STRUCTURAL FRAME — curated history, not a measured cycle` / zh "结构性框架 — 人工整理的历史，非实测周期").
- **Typical turn window** — a hatched span from `last_turn + period.low` to `last_turn + period.high`, captioned "frame, not forecast" (dual-span). NO central date, NO cone: a window is what n≈2 supports.
- **Tripwire strip** (§4.5) — the machine-evaluated falsifier status; this is where STRUCTURAL cards earn their "honest middle" keep.
- **Monitor sparklines** (housing: CSUSHPISA YoY, PERMIT; iron-ore: steel PPI) — small, labeled, live; they show the *evidence*, never a position number.

DUAL cards stack: secular strip (compact, ~64px) above the measured chart. Gold reads: measured intermediate cycle (engine) + "17y secular frame: year 10 of 15–20" strip.

The overview scorecard/wheel gets a hard rule: **STRUCTURAL cycles never appear in the phase-wheel buckets or any ranked list alongside measured positions** — they render in a separate "Frames" row. Mixing them is precisely the laundering the audit called the root disease (A-1, Part I §1).

### 3.4 i18n

Every new string ships dual-span `l-en/l-zh` via the established `t()` dual-span pattern; `t()` never in attributes (title/aria get plain English per house rule); zh up/down color flip respected in the tripwire strip (FIRED = follows alert semantics, not up/down — use severity colors, sidestepping the flip).

---

## 4. FALSIFIER TRIPWIRE COMPILER (T6) — `engine/falsifier_tripwires.py`

### 4.1 The DSL

Falsifiers live in `data/cycle_flagships/falsifiers.json` — a **list of tripwires**, each a boolean expression over collected series:

```jsonc
{
  "id": "oil.trough_not_in.v1",          // {cycle}.{claim}.{version}
  "cycle": "oil",
  "direction": "refutes",                 // firing REFUTES the card's stated thesis
  "claim": "the 2025 trough is in",
  "expires": "2027-06-30",                // hand-typed horizon; ARMED→EXPIRED after
  "expr": {
    "any": [
      {"series": "fred:DCOILWTICO", "op": "lt", "value": 55, "sustain_bars": 42},
      {"series": "fred:DCOILWTICO", "op": "gt", "value": 95, "sustain_bars": 42,
       "meaning": "confirms_upcycle"}     // optional: a leg can CONFIRM instead
    ]
  }
}
```

**Leg grammar** (each leg → `bool | None`, None = data missing):

| field | semantics |
|---|---|
| `series` | `"yahoo:SOXX"` \| `"fred:VIXCLS"` \| `"intl:_N225"` — resolved by `cycle_proxies.load_series` refs |
| `op` | `gt, lt, ge, le, cross_above, cross_below` |
| `value` | scalar threshold, in the series' native units |
| `sustain_bars` | leg true only if op holds for N **consecutive** bars ending at asof (default 1) |
| `transform` | optional: `"yoy_pct"` (12m % change), `"weekly_close"` (W-FRI resample), `"ratio:<series2>"` (s/s2, e.g. Pt/gold) |
| `months` | seasonal guard, e.g. `[7,8,9]` — leg can only evaluate true inside these months (nat-gas injection season) |
| `within` | `{"of": "<leg_id>", "days": N}` — conjunction with temporal proximity (housing: CS ATH *and* permits ≥1.5M within 90d) |

**Combinators:** `all`, `any`, `not` — arbitrarily nested. No free-form eval, no code in data: the compiler whitelists ops (this is a *DSL*, deliberately small; anything inexpressible stays a manual falsifier, §4.4).

### 4.2 Evaluator

```python
# engine/falsifier_tripwires.py
@dataclass
class TripwireResult:
    id: str; cycle: str; state: str    # ARMED | FIRED | EXPIRED | DATA_MISSING
    fired_on: str | None               # date the expr first held
    legs: list[dict]                   # per-leg {desc, value_now, threshold, ok, stale_days}
    claim: str; direction: str

def evaluate_all(asof: pd.Timestamp | None = None) -> list[TripwireResult]:
    """Pure read of data/ parquets. A leg whose series is >5 trading days stale
    → leg None → tripwire DATA_MISSING (never silently ARMED on dead data)."""

def persist(results) -> list[TripwireResult]:
    """Latch semantics: FIRED is sticky in data/cycle_flagships/tripwire_state.json.
    Un-firing requires a human to publish {cycle}.{claim}.v(N+1) — a falsified
    thesis stays falsified until re-authored. Returns NEWLY-fired only."""
```

Called from `engine/cycle_flagships.compute()` at build; states embedded in `flagships.json`.

### 4.3 Alert wiring (zero new infra — S5 verified)

New rule `cycle_falsifier_fired(hist, f)` in `engine/alerts.py` reading the newly-fired delta from `persist()`; appended to the `rules` list at alerts.py:476; flows through `log_and_dedup` (alerts.py:499, idempotent) → `scripts/notify.py send_telegram/send_discord` (the experiments_registry.py:182 pattern). Severity: `high`. Message: `"Cycle falsifier FIRED — oil: WTI < $55 held 42 sessions; card thesis 'trough is in' is refuted."` + zh.

**N4:** one experiments-registry entry `flagship-tripwires` (kind: monitoring, cadence: daily, maturation: `n_fired>=1 OR 180d`, come_back_on: +90d) so the accrual is tracked in the admin Experiments tab, not floating free.

### 4.4 Compile-from-prose: the full enumeration (all 23)

Which of today's hand-written falsifiers (cycle_data.js) compile, leg by leg:

| cycle | expressible? | compiled legs | dropped/manual legs |
|---|---|---|---|
| semis | **PARTIAL** | `yahoo:^SOX gt 14655` (after ^SOX add) | "broadening breadth" (no SOX A/D feed), "Broadcom raises AI outlook" (event) |
| memory | **NONE** | – | DRAM contract QoQ, spot DDR5, supplier inventories — all paywalled feeds |
| housing | **FULL** | `fred:CSUSHPISA transform:yoy_pct gt 5 sustain 3(M)` AND `fred:PERMIT ge 1500 sustain 2(M)` within 90d | (starts→permits rewrite; HOUST not collected — see NP-6) |
| business | **PARTIAL (rewrite)** | `fred:SAHMREALTIME lt 0.5` AND `fred:PAYEMS transform:yoy_pct gt 0` sustained | ISM>54 (no ISM feed) — rewritten legs approved as v2 falsifier, prose updated to match |
| oil | **FULL** | both legs (lt 55 / gt 95, sustain 42) | – |
| copper | **FULL** | `yahoo:HG_F lt 4.082 sustain 42` (=$9,000/t), `gt 6.804` (=$15,000/t) | – |
| uranium | **NONE** (proxy optional) | optional advisory: `yahoo:CCJ lt <level>` (labeled proxy-tripwire) | spot <$63/lb (no spot feed) |
| gold | **FULL** | `yahoo:GC_F lt 3300 sustain 21` | – |
| bitcoin | **FULL** | `gt 126000 (before next trough — encode expires)`, `lt 64000` | – |
| credit | **PARTIAL** | `fred:BAMLH0A0HYM2 gt 5.0 (=500bp)`, `le 3.0 sustain 63` | loan-default rate (no feed) |
| shipping | **NONE** | – | WCI $4,000/40ft (Drewry paywalled) |
| lithium | **NONE** | – | Jianxiawo restart (news event) + spot <$15k (paywalled) |
| agriculture | **FULL (after ZC=F add)** | `yahoo:ZC_F gt 5.75 sustain 42` | stocks-to-use (WASDE — manual) |
| vol | **FULL** | `fred:VIXCLS gt 27.5 sustain 5` | – |
| biotech | **FULL** | `yahoo:XBI lt 122.5 sustain 21`, `gt 175` | IPO-pricing quality (manual) |
| long-bonds | **FULL** | `fred:DGS30 gt 5.2`, `fred:DGS10 gt 4.9`, `yahoo:TLT lt 83` (any) | "failed auction" event (the yield legs capture it) |
| dollar | **PARTIAL→FULL** | `yahoo:DX-Y.NYB transform:weekly_close lt 97`, `fred:CPIAUCSL transform:yoy_pct lt 4` | "dovish FOMC pivot" (the CPI+DXY legs proxy it; prose amended) |
| natural-gas | **PARTIAL** | `fred:DHHNGSP gt 4.0 months:[7,8,9] sustain 10` | storage vs 5-yr avg (EIA weekly not collected) |
| iron-ore | **NONE** | – | 62% Fe >$120/t, SHFE rebar YoY (both paywalled) |
| silver | **PARTIAL** | `yahoo:SI_F gt 72 sustain 5` | "Fed pivot to cuts" leg (policy event) |
| em-equities | **PARTIAL (rewrite)** | `yahoo:EEM cross_above <2026-ATH level>` AND `yahoo:DX-Y.NYB lt 99` | MSCI-EM 1,809 rewritten to the EEM-equivalent level (documented in the tripwire `meaning`) |
| japan | **FULL** | `intl:_N225 gt 73000 sustain 21` AND `yahoo:USDJPY_X ge 160` | "broadening breadth" (no TOPIX A/D) |
| pgms | **FULL (after PL=F add)** | `yahoo:PL_F gt 1900`, `transform:ratio:GC_F lt 2.2`, `lt 1300` | – |

**Tally: 10 FULL, 8 PARTIAL, 5 NONE.** The 5 NONEs are exactly the no-proxy set — coherent: no tape ⇒ no tripwire ⇒ STRUCTURAL tier + **manual falsifier** = prose + `{as_of, ttl_days: 90, review_due}`; when TTL lapses the card badge flips to "falsifier review overdue" (grey), and a weekly digest alert lists overdue manual falsifiers. PARTIAL cards show compiled legs live + remaining prose labeled "manual leg".

### 4.5 FIRED-state UX

- Card banner (red, above the chart): `⚠ Falsifier fired 2026-08-12 — WTI held < $55 for 42 sessions. The card's thesis ("trough is in") is refuted.` Dual-span; sticky until re-authored (v2).
- The projection band (measured) / turn window (structural) grays out on FIRED — a refuted thesis may not keep advertising its forecast.
- Tripwire strip states: `⬤ armed · 3 conditions live` (green) / `⚠ FIRED <date>` (red) / `◌ data missing: DHHNGSP stale 12d` (amber) / `▢ manual · review due <date>` (grey).
- alerts.html picks the FIRED event up automatically via the alerts-log pipeline (it renders `alerts_log.parquet`).

---

## 5. NARRATIVE OVERLAY — schema, staleness, tolerance, re-keying (N2)

### 5.1 Schema — `data/cycle_flagships/narratives.json`

```jsonc
{
  "version": 3,                    // bumped on any re-authoring pass
  "basis_version": "tr_v1",        // bumped when the engine price basis / zz params change (N2)
  "cycles": {
    "semis": {
      "as_of": "2026-06-25", "ttl_days": 45,
      "archetype": {"en": "...", "zh": "..."},        // durable — no TTL badge
      "read":      {"en": "...", "zh": "...",          // volatile — TTL-badged
                    "claims": [ {"text": "SOX record ~14,655 on Jun-22",
                                 "check": {"series":"yahoo:^SOX","op":"ge","value":14000},
                                 "tolerance_note": "engine ATH within 5%"} ] },
      "falsifier_refs": ["semis.top_2026.v1"],         // → falsifiers.json
      "manual_falsifier": null,                        // or {text, as_of, ttl_days}
      "turning_points": [                              // THE CURATED CROWN JEWELS
        {"t": "2018-10", "k": "peak", "v": null, "e": "Crypto/datacenter/memory super-cycle top",
         "engine_key": "peak:2018-10", "match": "exact"}   // §5.3
      ],
      "regime_note": {"en": "...", "zh": "..."}
    } } }
```

Hard rule inherited from T6: **no field in this file is ever plotted as a number on a MEASURED band.** `turning_points[].v` renders in tooltips as "curated level"; positions/turns/cones are engine-only. On STRUCTURAL cards the curated turns ARE the timeline — but under the STRUCTURAL frame chip, so the provenance is on the label.

### 5.2 Staleness + tolerance at build

`engine/cycle_flagships.compute()`:
- `stale = (build_date − as_of).days > ttl_days` → card badge "curated {n}d ago" (grey → amber at 2×TTL). The read is *never dropped* — badged, not censored.
- **Tolerance assertion (T6):** for every MEASURED cycle, each curated turning point is matched to the engine turn list (§5.3). Unmatched hand turn ⇒ build **warning** + on-card `engine disagrees` micro-badge on that dot; >30% unmatched ⇒ build **error** (the curation or the registry mapping is wrong — a human must look). Each `read.claims[].check` is evaluated like a tripwire leg; a failing claim gets a strikethrough + "engine disagrees" tooltip. Numbers in prose thereby *cannot silently rot* (kills audit A-2/C-3 class).

### 5.3 Turn re-keying (the N2 migration bomb)

Any basis/threshold change re-dates engine turns and would orphan narrative keys (the sector pages froze zz at 14% for exactly this reason, sector_cycles.py:283). The flagships adopt **fuzzy engine keys from day one**:

- Key = `"{kind}:{YYYY-MM}"` of the *hand* turn (stable, human-owned).
- At build, `match_turn(hand, engine_turns)`: nearest engine turn of the same kind within `max(3 months, 0.25 × median_half_cycle)` → `match: "exact"|"near(Δmo)"|"none"`.
- When `basis_version` bumps (e.g. the D-data-basis dual-basis wave re-dates turns), **nothing re-keys**: matching is re-run, `match` fields update, and a one-shot migration report (`data/cycle_flagships/rekey_report_{basis_version}.md`) lists every hand turn whose match distance changed by >1 month, for a single human review pass. Narrative content is never machine-rewritten.
- This pattern is exported to the sector pages' narratives in the D-ontology pillar (it unfreezes the 14% ZigZag prison).

---

## 6. markets.html DISPOSITION — fold into country_cycles.html

### 6.1 Verified ground truth (the audit is wrong on the filename)

The canonical intl page **is `site/country_cycles.html`**, built by `scripts/build_country_cycles.py` (docstring line 1: "→ site/country_cycles.html"; the file exists in site/). The audit's Part IV-B verifier note claiming output "feeds site/intl_cycles.html" is itself wrong — it was misled by a **stale docstring in `engine/country_cycles.py:26-27`** referencing `scripts/build_intl_cycles.py -> site/intl_cycles.html`, neither of which exists (verified: no build_intl_cycles.py, no site/intl_cycles.html; log strings still say "intl_cycles:"). → New Problem NP-1; fix the docstring in W6.

### 6.2 The fold

1. **US row**: add `"SPY": {"name": "United States", "group": "North America", "flagship": True}` to `COUNTRIES` in `engine/country_cycles.py` (kernel runs unchanged; SPY tape 1993→). Add `"flagship": True` to EWC/EWU/VGK/EWJ/EWT/INDA/EWH/FXI.
2. **Flagship view**: `country_cycles.html` gains a "Flagship markets" filter tab (the 9), rendered first, with the markets.html overlay content attached: `data/country_cycles/flagship_overlay.json` = per-market `{turning_points (with real levels + draw), valuation{...,"as_of"}, archetype, falsifier_refs}` — same schema as §5.1, same tolerance/TTL machinery (shared code path in `cycle_flagships.py`, parameterized by overlay path).
3. **What survives from markets_data.js** (nothing valuable dies):
   - turns[] with real levels/draws → `flagship_overlay.json.turning_points` (STRUCTURAL-style curated dots on the measured chart's tooltip layer + the per-market detail panel).
   - valuation blocks → overlay panel, **now with mandatory `as_of` + TTL badge** (fixes B-5); scatter survives on the flagship tab, x-axis labeled "curated valuation (as of …)".
   - archetype/regime prose → overlay.
   - `posFromDrawdown`, cosine, convergence bands, `now.pos` → **deleted**. Convergence is NOT replaced here: per T7, any synchronization statistic waits for the D-interaction pillar's phase-0 lead-lag measurement.
4. **Redirect**: `site/markets.html` becomes a stub for one release: `<meta http-equiv="refresh" content="0;url=country_cycles.html#flagships">` + `<link rel="canonical" href="country_cycles.html">` + a visible dual-span link (the site is indexable since #796 — a hard 404 would burn any acquired link equity). `build_markets.py` shrinks to rendering the stub. Next release: remove the nav entry (`templates/_navlinks.html.j2` — run `check_nav_mega`/`check_nav_gap.py` guards), delete markets_{data,app,i18n}.js. cycle.html's japan/em-equities cards cross-link to the country_cycles flagship rows ("same market, intl desk view").
5. **Basis honesty on the fold**: the flagship tab shows the D-country pillar's local-vs-USD toggle where it lands (S4: 8 HIGH-feasibility markets incl. all overlap markets except HK peg-trivial); until then the existing "USD ETF, total-return" basis label ships on every card (interim honesty per T5).

---

## 7. WALL-CLOCK TODAY + elapsed-turn handling (interim, ships first)

The `Math.max(central, today+0.15)` push-forward trap (cycle_app.js:63, audit A-7) means naively wiring `Date.now()` would *silently re-date elapsed hand-typed turns as fresh futures* — worse than the frozen page. The interim fix (before W3 replaces the data source entirely):

```js
// cycle_app.js + markets_app.js — shared patch
const yfNow = d => d.getFullYear() + (dayOfYear(d) - 1) / 365.25;  // matches _yf()
const TODAY = yfNow(new Date());          // META.today kept ONLY as data as-of
// build(c):
const tcRaw = yf(c.proj.central);
const elapsed = tcRaw < TODAY;            // NO Math.max push-forward. Ever.
if (elapsed) {
  //  - projection leg + cone draw to their ORIGINAL hand-typed dates, dimmed
  //    (class "proj-elapsed", 35% opacity, dashed grey)
  //  - card chip: "⏳ turn window passed — unresolved"  (dual-span)
  //  - legPct pins at 100 and renders ">100% — projected window elapsed"
} else {
  const tc = tcRaw, te = clamp(yf(low), TODAY + 0.05, tc), tl = Math.max(yf(high), tc + 0.1);
}
// history/projection split + Now dot + TODAY guide use wall-clock TODAY
```

- **Staleness banner** on both pages when `(TODAY − yf(asOf)) × 365.25 > 21` days: "Curated data as of {asOf} — {n} days old" (amber ≥ 21d, red ≥ 60d), dual-span, plain-English attribute-free.
- markets_app.js:504 `'Live read · '` label → `'Curated read · ' + asOf` immediately (the "Live" word is a lie today, B-1).
- This wave touches only the two app.js files + i18n dicts; no engine dependency; ships day 1 while the registry waves proceed.

---

## 8. NEW PROBLEMS DISCOVERED (evidence-grounded)

- **NP-1 — Stale engine docstring poisoned the audit record itself.** `engine/country_cycles.py:26-27` claims output feeds `scripts/build_intl_cycles.py -> site/intl_cycles.html`; neither exists (actual: `scripts/build_country_cycles.py -> site/country_cycles.html`, its docstring line 1). Log tags still read `intl_cycles:` (lines 124/162/182/201). The audit's own Part IV-B "correction" repeats the phantom filename — a hand-written doc contaminated a machine-verified audit. Severity: medium (trust infrastructure). Fix in W6.
- **NP-2 — build_cycle.py docstring says "15-cycle dataset"; cycle_data.js contains 23.** (build_cycle.py:4 vs 23 `id:` entries verified.) Same rot class as NP-1: hand-maintained counts drift. Severity: low. Fixed by W3 (docstring rewritten with the registry as source of truth).
- **NP-3 — Ticker-collision trap for the platinum add.** `data/yahoo/PL.parquet` already exists = **Planet Labs**, not platinum. Any naive "add PL" for PGMs would silently plot a satellite company as a metals cycle. Registry must pin explicit yfinance symbols (`PL=F` → `PL_F.parquet`); W1 acceptance includes an assert that flagship series refs never resolve to an equity when `basis="futures_cont"`. Severity: high if unguarded (wrong tape, plausible-looking chart).
- **NP-4 — markets_data.js `draw` field is semantically overloaded and undocumented.** On trough rows it is the drawdown % (−56.8 at 2009-03); on peak rows it is the *run-up* % since the prior trough (+101.5 at the 2007-10 peak) (markets_data.js:92-110). Any migration that reads `draw` as "drawdown" corrupts half the rows. W6's overlay migration renames to `move_pct` with `k`-dependent meaning documented. Severity: medium (migration-time data corruption).
- **NP-5 — Five cycles are permanently un-tripwire-able with the current collector estate** (memory, uranium, shipping, lithium, iron-ore — DRAM ASP/UxC/Baltic/Fastmarkets/Platts all paywalled). T6's "machine-evaluated tripwires" ceiling is 18/23; the design must (and does, §4.4) define a first-class *manual-falsifier* state with TTL + overdue alerts, or these five silently become the old decorative prose again. Severity: medium (honesty architecture).
- **NP-6 — The housing falsifier cites "starts/permits ≥1.5M SAAR" but only PERMIT is collected** (no HOUST in data/fred, verified). Compiled leg uses PERMIT; either add HOUST (one config line) in W1 or amend the prose. Severity: low.
- **NP-7 — FRED 3y-window truncation makes new monthly series shallow by default.** CSUSHPISA/DCOILWTICO/DHHNGSP added today would carry only ~3y unless deep-history is seeded via the API host once (S5: collector is append-only; pre-window history persists only if fetched before/seeded). An 18y-cycle monitor with 3y of data is useless. W1 must include the seed-and-commit step (§1.4). Severity: high for the housing card specifically.

---

## 9. VERDICT ON FABLE'S THESES

- **T1 ADOPT + REFINE.** The two-tier split is correct and §1.2 lands every cycle. Two refinements forced by the data: (a) **tier attaches to a BAND, not a cycle** — gold/dollar/japan/bitcoin are DUAL (a gradeable daily tape *and* an ungradeable secular frame; picking one tier per cycle either discards a measurable object or launders an unmeasurable one); (b) a **MEASURED-proxy sub-flag with an earned fitness gate** (§1.5) for memory/uranium, where the only tape is an equity standing in for the researched series — calling that plain "MEASURED" would be a new laundering.
- **T2 ADOPT (as consumer).** Both kernels emit one record schema and one phase semantic; the monthly kernel requires the ontology crosswalk to declare the ladder/DC/IC sub-reads **optional keyed on `now.freq`** (a monthly macro series has no daily ladder — the contract must permit basis-declared absence, not fake it). Registry params (`trend_span`, `zz`) are versioned data under the ontology, killing parameter folklore.
- **T3 ADOPT.** §2.5 emits the exact hazard feature row per stamp with `family="flagship"` for per-family shrinkage. Flagship-specific caveat: STRUCTURAL bands contribute **nothing** to the hazard pool (n≈2 turns is not a hazard sample; the frame band renders a window, not a probability), and flagship cones swap to hazard cones only when the calibration artifact exists.
- **T4 ADOPT.** Backfill is cheap for flagships (~3.4 min for 20 series × 180 month-ends with the 800-bar cap, S2-measured) and the registry stamps per-series start dates so effective-n is honest per cycle. N3 folded in: phase-scaled grading horizons (§2.5), never flat 21d.
- **T5 ADOPT + REFINE.** Adopted for the 6 ETF-proxied cards. Refinement: for flagships the *stronger* move is **series substitution, not dual columns** — 14 of 23 have native price/level series (futures, FRED spreads/rates/vol, spot crypto) with no dividend adjustment to fight; and T5's price/TR framing misses the **inverted + abs-threshold level-series support** (credit/vol/long-bonds/business) that §2.2 adds. Dual-basis remains necessary where only ETFs exist — that's the D-data-basis pillar; the registry's `basis` field is the join key.
- **T6 ADOPT.** §4 is the compiler T6 asked for: 10 FULL + 8 PARTIAL compile today (18/23 with at least one live leg); the 5 NONEs get first-class manual-falsifier state (NP-5) — the DSL must not pretend coverage it lacks. Curated turning-point history is preserved twice over: as the STRUCTURAL timeline (plotted, labeled) and as tolerance-checked overlay dots on MEASURED cards. Latched FIRED semantics (§4.2) make refutation sticky — a falsified thesis cannot quietly re-arm.
- **T7 ADOPT.** markets.html's fake convergence bands are deleted in W6 and NOT replaced; any synchronization/dispersion statistic waits for the interaction pillar's phase-0 lead-lag measurement. Nothing in this pillar builds on unmeasured lead-lag.
- **N1 ADDRESSED** (§2, the monthly kernel + registry is the proxy-mapping N1 demanded). **N2 ADDRESSED** (§5.3 fuzzy keys + basis_version + rekey report). **N3 ADDRESSED** (§2.5 phase-scaled horizons). **N4 ADDRESSED** (§4.3 experiments-registry entries for tripwires; the backfill/hazard accruals register in their own pillars' entries).

---

## 10. WAVES

Standing pipeline per house rules: each wave = branch off main → PR → squash-merge same-day; site pages re-render as committed artifacts; i18n dual-span everywhere; render-cost budget ≤ +60s total (actual estimate < 15s steady-state).

**D3-W0 — Stop the rot (wall-clock TODAY + elapsed turns + staleness banners).** *(sonnet)*
Scope: §7 exactly — cycle_app.js + markets_app.js wall-clock TODAY, kill the Math.max push-forward, elapsed-turn UX, staleness banners, "Live read"→"Curated read". Files: `site/cycle_app.js`, `site/markets_app.js`, `site/cycle_i18n.js`, `site/markets_i18n.js` (these four are committed site/ sources per build_cycle.py PAGE_ASSETS — no templates copy exists).
Acceptance: with system clock ≥ 2026-07-02, both pages show the Now dot at wall-clock; every proj.central < today renders dimmed + "window passed" chip and never shifts right; banner text dual-span; zero console errors.
Depends: nothing. Ships immediately.

**D3-W1 — Proxy registry + collector adds + deep-history seed.** *(sonnet; the config lines alone are haiku, the seeding + fitness gate are not)*
Scope: `engine/cycle_proxies.py` (REGISTRY §1.2-1.3, `load_series`, `registry_report`, `validate_proxy` §1.5); config.yml adds (§1.4 incl. HOUST per NP-6); FRED deep-history seed for CSUSHPISA/DCOILWTICO/DHHNGSP via API host, parquets committed (NP-7); proxy-fitness run for MU/CCJ → `proxy_fitness.json`.
Acceptance: `python -m engine.cycle_proxies` prints a health table: every `measured` entry resolves, ≥10y rows (CSUSHPISA ≥30y), zero stale; `PL_F` resolves to futures not Planet Labs (NP-3 assert); fitness gate emits pass/fail for memory+uranium with stored artifact.
Depends: nothing (registry is pure-additive).

**D3-W2 — `record_series` kernel (monthly + invert + abs-ZigZag).** *(opus for the kernel-parameter decisions + ontology negotiation; sonnet execution acceptable if D1's contract has already landed)*
Scope: §2.2 in `engine/sector_cycles.py` — `record_series`, `_detect_swings_abs`, monthly classifier votes, hazard_features emission; `_record_core` re-expressed as the daily special case.
Acceptance: (a) full-site rebuild produces **byte-identical** `sector_cycles_data.js`, `sector_cycles_china_data.js`, `country_cycles_data.js` (zero regression); (b) unit tests: invert on a synthetic V-shaped spread series yields mirrored turns; monthly kernel on CSUSHPISA detects 2006-07±2mo peak and 2012-02±3mo trough at zz_pct=5; abs-swing detector on a synthetic diffusion series; (c) `now.freq`/`hazard_features` present in every stamp.
Depends: D1 ontology contract for the optional-sub-read declaration (can proceed with a TODO-pinned crosswalk if D1-W1 hasn't merged, but must not ship user-visible before it).

**D3-W3 — Engine-backed cycle.html (the schism collapse).** *(sonnet, large)*
Scope: `engine/cycle_flagships.py::compute()` (§3.1); `scripts/build_cycle.py` becomes a real builder; two-tier + DUAL-band rendering (§3.2-3.3) in cycle_app.js + cycle.css; `data/cycle_flagships/narratives.json` seeded by mechanically splitting cycle_data.js (turns/archetype/read/falsifier → overlay; pos/cosine params → deleted); `site/cycle_data.js` retired; scorecard separates Frames row.
Acceptance: every MEASURED band's plotted position/turns/projection derives from `record_series` output (grep: no `now.pos` literal survives in data); 4 STRUCTURAL cards render age-dial + hand-turn timeline + no oscillator/signal/pos; 4 DUAL cards render both bands; tier chips + basis labels dual-span; build fails on a stale measured tape (registry_report gate); render-time delta < 30s.
Depends: W1 + W2. (Grading/backfill NOT in scope — measured cards ship with `accruing` chips.)

**D3-W4 — Falsifier tripwire compiler + alerts.** *(sonnet)*
Scope: §4 — `engine/falsifier_tripwires.py`, `data/cycle_flagships/falsifiers.json` authored from the §4.4 table (10 FULL + 8 PARTIAL, exact legs as specced; unit conversions copper $/lb→$/t documented in-file), latched state file, `cycle_falsifier_fired` alert rule + rules-list registration (alerts.py:476), FIRED/armed/missing/manual UX strip on cards, experiments-registry entry (N4), manual-falsifier TTL + weekly overdue digest.
Acceptance: synthetic-data test fires the oil tripwire on a fabricated 42-bar <$55 tape and the state latches across a second evaluate; DATA_MISSING surfaces on a deliberately-staled series; telegram/discord dispatch smoke-tested via the notify.py pattern; every card shows exactly one tripwire strip state; FIRED grays the projection band.
Depends: W1 (series resolution), W3 (card UX to attach to). The evaluator itself can merge after W1 with alerts-only output.

**D3-W5 — Narrative overlay hardening (TTL, tolerance, re-keying).** *(sonnet)*
Scope: §5.2-5.3 — claims[].check evaluation, tolerance assertion + engine-disagrees badges, TTL staleness badges, `match_turn` fuzzy matching + `basis_version` + rekey report generator; wire the same machinery into the country_cycles flagship overlay (shared code path).
Acceptance: corrupting a curated turn date by 4 months in a test fixture produces `match:"near(4mo)"` + build warning; setting >30% mismatches fails the build; an expired-TTL read renders the badge; bumping basis_version regenerates the rekey report without touching narrative text.
Depends: W3.

**D3-W6 — markets.html fold into country_cycles.** *(sonnet)*
Scope: §6.2 — SPY flagship row in `engine/country_cycles.py` (+ fix the NP-1 stale docstring/log tags); flagship tab + overlay (`flagship_overlay.json` migrated from markets_data.js with the NP-4 `draw`→`move_pct` rename); valuation panel with as_of + TTL; redirect stub + canonical link; nav update behind `check_nav_mega`/`check_nav_gap.py`; delete markets_{app,data,i18n}.js next release; convergence bands deleted, not replaced (T7).
Acceptance: /markets.html 200s and redirects; country_cycles flagship tab shows 9 markets incl. US with curated turn history in the detail panel; every valuation chip shows its as_of; nav guards pass; grep confirms `posFromDrawdown` and `convergenceBands` are gone.
Depends: W3 (overlay machinery), W5 (tolerance/TTL shared path). Can run parallel to W4.

**D3-W7 — Flagship backfill + phase-scaled grading + hazard hand-off.** *(fable to specify the joint artifact with the measurement + hazard pillars; sonnet to execute)*
Scope: monthly-cadence PIT backfill of all MEASURED flagship stamps via `record_series(asof=...)` with the 800-bar cap (≈3.4 min one-off) → `data/cycle_flagships/forward_log.parquet`; grade with the shared `engine/grading_stats.py` (D-measurement pillar) at phase-scaled horizons (§2.5, N3): turn precision/recall vs realized ZigZag extrema, IQR-band coverage rate (the missing cone-coverage function per S5 — build it there, reuse here), Wilson/bootstrapped CIs, MIN_N floors; hazard features stream into the D-hazard pool (`family="flagship"`); graded badges go live on cards only from stored scorecard artifacts; register the accrual in the experiments registry.
Acceptance: forward_log spans ≥ 15y of month-ends for every ≥15y tape; zero look-ahead (spot-check: stamp at 2020-03-31 uses no April data); scorecard JSON per cycle with n, CI, coverage; a cycle with n < MIN_N renders `accruing`, never a point estimate.
Depends: W1-W3 + D-measurement pillar's grading_stats wave + D-hazard pillar's model wave (badge/cone swap only).

**Wave order:** W0 ⟶ (W1 ∥ W2) ⟶ W3 ⟶ (W4 ∥ W5 ∥ W6) ⟶ W7.

---

## 11. Open questions (for Fable / sibling pillars)

1. **Ontology home for the STRUCTURAL frame semantics** — the age-dial ("year 14 of 15-20") is a new display primitive; D1's compiled contract should own its vocabulary so China/sector pages can reuse it for their own secular frames.
2. **Does the em-equities card survive at all**, or fold into country_cycles alongside markets.html? (EEM is literally a country-bloc aggregate the intl engine already computes.) Recommend: keep on cycle.html as the "EM as an asset-class cycle" card, cross-linked — but cheap to fold later.
3. **^SOX collection reliability** — Yahoo's index tickers occasionally gap; if ^SOX proves flaky, the semis falsifier level rewrites onto SOXX (documented conversion) rather than depending on a fragile tape.
4. **Manual-falsifier review cadence** — 90d TTL proposed; the user trades on these cards (memory: user-trades-conviction-low-n), so Fable may want 45d for the five NONE cycles.
5. **DUAL-card hazard treatment for bitcoin** — the existing BTC 1064/364 cycle work (separate program) overlaps the halving frame; the structural band should cite that program's artifacts rather than re-deriving.
