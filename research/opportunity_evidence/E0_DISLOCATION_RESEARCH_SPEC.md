# E0 Dislocation Research Spec

**Purpose:** specify how to *attribute* a name’s drawdown or outperformance without turning the attribution into an entry signal or Opportunity Score.  
**Hard split:** statistical decomposition ≠ economic-cause hypothesis. They must travel as two fields.  
**Base:** `origin/main` @ `3d12412e561e`.

---

## 1. Law this spec inherits

| Binding | Exact killed / surviving form | Consequence for this spec |
|---|---|---|
| `DNR:KILL-PSS-F3-RESIDUAL` | Idiosyncratic-residual **reset as standalone entry-timing** (beta-stripped vs sector ETF). Mechanism falsifier failed: fires concentrate in **high-R² / systemic** windows, residual MAE does not beat raw analog, earliness is early-into-systemic-drawdowns. | Residualization may be used as a **descriptor** of *where* the move lived. It may **not** be a timer, gate, or ranker. |
| `DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER` | 1–5d no-news shock-reversal classifier closed at OHLCV grade. | DRL ships measured truth as display. Do not rebuild a bounce classifier on `resid_z`. |
| `DNR:KILL-PARALLEL-SHOCK-CLASSIFIER` | Day taxonomy / shock vocabulary in the ledger | DRL ledger stores **numbers**, not named day types. This spec’s statistical layer must stay numeric. |
| `DNR:KILL-WASHOUT-TURN` | 2W/1M StochRSI washout × turn on Prophet fires | Depth is context. Radar/Opportunity research may not revive that interaction. |
| `DNR:KILL-MCO-THRUST` | Market-level breadth washout bounce as radar leg | No market-breadth-thrust detector enters via this program. |
| Residual alpha charter | Market + orthogonal sector residual momentum, **within-sector rank**, 12-1. Modest, crowded, regime-decayed. Not BH-FDR/DSR-cleared on modern era. | Lawful as a **medium-horizon residual return series**, not as “alpha score.” **CODE VERIFIED** `engine/residual_alpha.py:1-21` |
| DRL charter | `resid = ret − sector_ex_self_peer(ret)`; `resid_z = resid / rolling60σ.shift(1)`; shock `\|resid_z\|≥3 ∧ vol≥2×`. Authority all-false. | Lawful as **event harvest + resolution tracking**. **CODE VERIFIED** `engine/price_pressure/detect.py:1-10` and `data/price_pressure/latest.json` |
| Radar PR-0 | Radar is prospective washout→turn, DRL is reactive residual-shock. Zero namespace overlap. | This spec is a **research attribution layer**, not a third entry system. |

---

## 2. Two objects, never one

### 2.1 Statistical dislocation vector (required)

For name *i* at decision date *t*, over a declared window *W* (default overlapping: 5d / 21d / 63d):

```
r_i,W
  = β_mkt · r_mkt,W
  + β_fac · r_fac,W          # optional; UNAVAILABLE if factor residual absent
  + β_sec · r_sec_ex_self,W
  + β_theme · r_theme_ex_self,W   # optional; UNAVAILABLE if no basket
  + ε_i,W
```

Emit, for each window:

| Field | Meaning | Missing rule |
|---|---|---|
| `ret_raw` | Close-to-close total return | If bars missing → `unavailable` |
| `ret_mkt` | Contribution of market | SPY or region benchmark, named |
| `ret_fac` | Contribution of a **named** factor basket | If `factor__absent` → omit, never 0 |
| `ret_sec` | Contribution of GICS (or named) sector ex-self | If peer set < min_names → fall back **and label** `peer_basis=market` |
| `ret_theme` | Contribution of theme/basket ex-self | If not a member → omit |
| `ret_resid` | Leftover `ε` | Always with `peer_basis` disclosure |
| `resid_z` | `ε / σ_{ε,lagged}` | Same construction as DRL if reused; do not fork σ |
| `r2_window` | Share of variance explained by non-residual terms | Needed to read PSS-F3’s lesson (high-R² vs low-R²) |
| `peer_basis` | `sector` \| `market` \| `theme` \| `mixed` | Copy DRL’s honesty: latest DRL panel is sector-basis only **52.79%**, market **47.21%** **PRODUCTION VERIFIED** |
| `asof` / `known_at` | Information date | Confirmed close ≠ live quote |

**Reuse, do not re-derive**

- Daily residual shock path: import DRL/LSR seam (`engine/price_pressure.panel.derive`).  
- Medium-horizon residual momentum path: import `engine.residual_alpha.residuals`.  
- These two residuals are **not interchangeable**. Document which object a consumer is holding.

### 2.2 Economic-cause hypothesis (optional, separate)

A free-text or enum **hypothesis** with provenance, never computed from `ε`:

| Allowed values (research enum) | May be set only if |
|---|---|
| `sector_or_factor_washout` | Statistical layer shows large `ret_sec` or `ret_fac` and company evidence fields are not impaired |
| `company_impairment` | Filing / earnings / guidance / going-concern / dilution / fraud-forensics evidence exists **as of t** |
| `liquidity_airpocket` | Dollar-volume collapse or halt; not inferred from residual alone |
| `positioning_unwind` | Observable SI / options / 13F change **as of t** (usually 13F cannot explain a 21d move) |
| `unknown` | Default |

**Forbidden:** inferring `company_impairment` from a large residual, or `washout` from a large sector term without checking company evidence. Co-movement is not cause.

---

## 3. Existing constructions — map, do not merge

| Construction | Formula (short) | Window | Peer | What it answers | What it does not |
|---|---|---|---|---|---|
| Residual alpha | `r − βm m − βs s̃`, `s̃ ⟂ m`, 252d causal betas, shrink 0.66 | 12-1 month IR of `e` | GICS EW ex implied by sector loop | Medium-horizon residual **momentum rank within sector** | Event shock; theme; factors; timing |
| DRL / LSR | `r − sector_ex_self`; z vs 60d lagged σ | 1-day shock + t+1..t+60 resolution | Sector if covered else market | “Was today a residual shock vs peers?” | Why; whether to buy; 12-1 alpha |
| DRL theme context | Thematic-basket ex-self residual | Event | Basket membership | Extra descriptor | Independent confirmation (shares price) |
| Factor exposure | User-watchlist vs ~30 ETFs | Mixed | ETF_NAMES list | Watchlist factor decomp | Universe-wide name residual |
| US Context Vector `factor__*` | Join slot | Nightly | — | **100% absent** on 2026-08-17 stamp | There is no live factor residual on the board |
| Prophet `alpha` / `alpha_percentile` | Residual-alpha consumer | Nightly | Sector | Setups / standouts input | Dislocation attribution |

**PRODUCTION VERIFIED** DRL coverage (`data/price_pressure/latest.json`):

- panel_names 4,315 · span 2021-07-06 → 2026-08-14  
- sector_covered_share 0.3416 · edgar_covered_share 0.4594  
- ledger_rows 36,479 (backfill 35,677 / gap 754 / forward 48)  
- open_events on asof 2026-08-14: 24 listed; `open_rows` 1,795  
- authority all false · display_only true  

---

## 4. Research protocol (no promotion)

### 4.1 Episode definition

An attribution episode is `(ticker, t0, W)` where `t0` is a **decision date** taken from an existing PIT object (winner-case `t0_hypothesis`, DRL event date, Prophet `stamp_date`, Radar `observed_at`). Do not optimize `t0` after seeing forward returns.

### 4.2 Required comparison

For every episode print **both**:

1. Statistical vector at `t0` (and at `t0−21`, `t0−63` if bars exist).  
2. Company-evidence state at `t0` (filings/earnings/revisions/forensics known_at ≤ t0), each field `present | absent | stale | unlicensed`.

Then classify:

| Cell | Meaning |
|---|---|
| A | Large sector/factor/theme term, company evidence intact → *candidate washout* |
| B | Large residual, company evidence impaired → *candidate impairment* |
| C | Large residual, company evidence intact → *unexplained residual* (not a buy signal) |
| D | Large sector term **and** impaired evidence → *do not call washout* |
| E | Insufficient peer_basis / missing bars → `unavailable` |

### 4.3 Honest-N

Report **distinct episodes**, not fire-days. State whether today’s tape is in-sample of any cell that later looks good. Name who is missing from the peer panel (DRL already discloses market-basis fallback).

### 4.4 What would kill a later promotion (not requested now)

A promotion-bearing rule that uses residualization as timing or rank must re-confront `DNR:KILL-PSS-F3-RESIDUAL` by name with an NC-style high-R² kill-arm. This spec does not register that test.

---

## 5. Implementation stance (boring baseline)

Do **not** write a new residual engine.

1. For shock-scale questions: read DRL.  
2. For medium-horizon residual momentum: read residual_alpha.  
3. For a 5-layer research pack: a **view** that joins those plus a named factor series **if and when** `factor__absent` is no longer 100%.  
4. Theme term only when `data/baskets/membership.json` or theme-graph member edge exists at `t0`.

If a factor series is added later, it must have its own `known_at` and must not be backfilled into the US Context Vector’s disclosed-null nights (`data/us_prophet_rank/disclosed_gaps.json`).

---

## 6. Worked numeric example (statistical only)

Open DRL event on asof 2026-08-14, **IMXI**, side up: `ret=0.2470`, `peer_ret=0.0014` (peer_basis **market**), `resid=0.2456`, `resid_z=11.85`, `edgar_covered=false`, family `filing-coverage-unknown`. **PRODUCTION VERIFIED** `data/price_pressure/latest.json` open_events[0].

Economic cause for IMXI that day: **UNKNOWN**. The residual is large versus the market fallback, not versus a sector peer. Filing coverage is false. This row is a Cell-C or Cell-E candidate, not a washout call.

---

## 7. No-build warnings

- Do not merge residual_alpha and DRL into one “dislocation score.”  
- Do not fill missing factor/theme terms with 0.  
- Do not treat `peer_basis=market` as if it were sector-idiosyncratic.  
- Do not narrate “the thesis is false” from a residual window miss (instrument verdict ≠ market verdict).  
- Do not start W7 or emit rank weights from this spec.
