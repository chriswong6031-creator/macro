# Pillar D4 — The Data Substrate: fix the ground everything stands on

**Author:** principal quant-systems designer (Opus) · **As of:** 2026-07-02 · **Repo:** canonical main @ `/tmp/macro-cycle-fable-main/`

> **Scope.** This pillar owns the *substrate contract* under the whole cycle platform: the price basis every
> structure-math consumer reads, the migration that flipping the basis forces, the FX decomposition for
> `country_cycles`, benchmark basis-matching in every grader, frozen basket levels with membership hashing,
> and the guard-rail audit that makes the contract enforceable. It does **not** own the ontology module
> (Pillar D2/ontology), the hazard model (D3), the grader-stats library (D5-measurement), or the flagship
> re-backing (D-schism). It *supplies the corrected inputs* those pillars stand on, and names the exact
> hand-off seams.

---

## 0. Executive thesis

The audit's finding #4/#7 is correct and load-bearing: **every "data-driven" cycle on this platform is
computed on dividend-adjusted total-return closes (`collectors/yahoo.py:100 auto_adjust=True`) while the
engines market themselves as "true price."** I verified the mechanism empirically — with
`auto_adjust=False`, yfinance 1.4.1 returns *both* a `Close` column (split-adjusted, dividend-**un**adjusted
— exactly the price series ZigZag needs) and an `Adj Close` column (split+dividend adjusted = total
return). So the dual-basis store Fable's T5 asks for is **one collector flag away** from being collectable;
the whole cost is backfill + storage + a basis-aware read API + a migration.

But the naive framing "just use raw close" is a trap the repo already documented and defended against:
`lib/store.py:upsert` has a long comment explaining that a fresh dividend-adjusted pull re-scales the entire
prior history, and `sector_cycles.py:283-288` explains the 14% ZigZag threshold is *frozen precisely so
detected turn dates never move* — because moving them orphans every `narratives.json` key. So the substrate
fix is not a one-line swap; it is **a basis contract + a re-keying migration + a freeze discipline**, and it
must land *before* D5 backfills any grades (a grade on the wrong basis is worthless — audit's own words) and
*before* D3 fits any hazard model.

The three highest-leverage moves are: (1) add `close_price` (split-adjusted, div-unadjusted) alongside the
existing `close` (now explicitly `close_tr`) as a **second column in the same parquet**, backfilled once from
yfinance `max` history, exposed via `yahoo_closes(basis=...)`; (2) a **one-time re-key migration** that
re-dates every ZigZag turn on the new basis and matches old narrative keys to new turns by nearest-turn
within tolerance, versioning the keys so a stamp always declares which basis it was computed on; (3) a
**frozen daily basket-level parquet with a membership hash per row**, killing the survivorship/look-ahead leak
in every basket grade and wiring the THS-truncation failure mode to *invalidate* affected grades instead of
silently rewriting them. A guard-rail audit (`scripts/audit_price_basis.py`) wired into the existing
`run_quality_audits` gate makes the contract non-regressable.

---

## 1. Ground truth established (what actually exists)

Verified directly against the checkout; these facts anchor every decision below.

| Fact | Evidence |
|---|---|
| Yahoo parquets are `close` + `volume` only, **dividend+split adjusted (TR)** | `collectors/yahoo.py:100` `auto_adjust=True`; `data/yahoo/SPY.parquet` 2 cols, 8412 rows 1993→2026 |
| `auto_adjust=False` returns **both** `Close` (split-adj, div-UNadj) *and* `Adj Close` (TR) | empirical: `yf.download('AAPL',auto_adjust=False)` → cols include `('Close',..)` and `('Adj Close',..)` (verified this session, yfinance 1.4.1) |
| Three collectors already use `auto_adjust=False` | `china_stock_raw.py:48`, `rate_futures.py`, `commodity_carry.py` — pattern exists |
| Shenwan L1 (China sectors) are **price-basis** custodian indices via akshare (NOT TR) | `collectors/china_sectors.py:11-16`; `801010.parquet` has OHLC, base 1000.0 |
| China A-share prices are dual-plane already: `china_stocks` (adj) + `china_stocks_raw` (raw) | `china_stock_raw.py:1-22` docstring |
| `store.upsert` already has an `overwrite_overlap` flag for adjusted-series basis-step correctness | `lib/store.py:upsert` docstring |
| `sector_cycles.compute(asof=...)` already slices `closes<=asof` before all builders (PIT-ready) | `sector_cycles.py:533-534` (S2 scout) |
| `_record_core` on 800-bar series = **56ms/call** measured; ZigZag/osc/phase all pure price functions | S2 scout |
| Basket candle is built with `pit=False` (survivorship-not-clean) hard-coded | `sector_cycles.py:409`; `basket_index.py:168-174` |
| China grader subtracts a **TR** benchmark from a **price-return** Shenwan sector | `china_sector_central_grader.py:110-135`; `china_sector_index.benchmark_close()` |
| `country_cycles` runs USD-ETF TR only, folds FX into every "equity cycle" turn | `country_cycles.py:1-14`; `cycle_dna.json` ewj ("fell 33% in dollars while local flat") |
| 14 of 24 country FX pairs already in-repo; 7 absent but Yahoo-fetchable; 8 markets HIGH-feasibility for LC decomp with zero new collection | S4 scout |
| Quality-audit gate: `run_quality_audits` in `scripts/collect.py:273` runs prices/macro/universe/fred audits, each writes `data/quality/*_audit.json`, gates `collect.py` fail_pct | `collect.py:287-311`; `scripts/audit_prices.py` |
| Experiment registry exists (20-field schema, accruing→measuring→validated) | `data/experiments/registry_seed.json` |

**Corrective note on Fable's T5 parenthetical.** Fable wrote "naive *raw* close breaks ZigZag at every
split." Precisely right — but the fix is *not* the exchange-raw unadjusted close (which has split
discontinuities). It is yfinance's `auto_adjust=False` **`Close`**, which is **split-adjusted but
dividend-unadjusted**. That is the correct structure-math basis: continuous across splits (no ZigZag break),
but not inflated by reinvested dividends (so drawdowns, failed-cycle lows, and detrended position are on
true price). I adopt T5 with this precision baked in. The name I use throughout is `close_price` for that
series and `close_tr` for the existing total-return series.

---

## 2. DUAL-BASIS STORE (T5 core)

### 2.1 The contract

Three named bases, one canonical definition each. Every downstream consumer declares which it reads.

| Basis token | Definition | yfinance source | Use |
|---|---|---|---|
| `price` | split-adjusted, dividend-**un**adjusted | `auto_adjust=False` → `Close` | **all structure math**: ZigZag turns, detrended osc, DCL/failed-cycle, invalidation levels, drawdown-from-ATH |
| `tr` | split+dividend adjusted (total return) | `auto_adjust=False` → `Adj Close` (identical to today's `auto_adjust=True Close`) | **return/momentum/RS**: `pct_change`, RS-vs-bench, forward-return grading |
| `raw` | exchange-raw, unadjusted (splits present) | n/a for yahoo group | China A-share limit bands only (already isolated in `china_stocks_raw`) — **out of scope for cycle math** |

**Rule (the contract):** structure math consumes `price`; return/momentum math consumes `tr`; the two are
never mixed within one computed quantity, and every stamp records `price_basis` + `basis_version`.

### 2.2 Storage: second column, same parquet (NOT a new file)

Add `close_price` as a **second column** in each `data/yahoo/<t>.parquet` alongside the existing `close`
(which is renamed in meaning to "TR" but keeps the column name `close` for backward-compat during
migration — see §2.6). Rationale over a separate file:

- The store is "one parquet per logical series" (`store.py` docstring). A ticker's price and TR are the
  *same series on two bases*, not two series — co-locating them keeps `store.read('yahoo', t)` a single I/O
  and keeps them index-aligned by construction (no join-on-read, no drift).
- Backward compatibility: existing readers of `df['close']` keep working (they get TR, which is what they
  read today) until each is migrated. A missing-file rename would break every reader at once.
- Storage cost: one extra float64 column per yahoo parquet. ~1,500 yahoo parquets × ~8k rows × 8 bytes ≈
  **~96 MB** incremental across the whole yahoo store — trivial in a git-LFS-free parquet repo (the store is
  already ~GB-scale).

Final per-yahoo-parquet schema after migration:
```
index: DatetimeIndex (business days)
close        float64   # TR (unchanged meaning; = old auto_adjust=True close)
close_price  float64   # NEW: split-adj, div-unadj (auto_adjust=False Close)
volume       float64
# vol group (^VIX etc.) additionally: high, low  (unchanged)
```

### 2.3 Collector change (`collectors/yahoo.py`)

Flip `_download` to `auto_adjust=False` and keep **both** Close and Adj Close:

```python
# collectors/yahoo.py  _download (was line 100)
df = yf.download(batch, period=period, auto_adjust=False,   # was True
                 progress=False, group_by="ticker", threads=True)
```
Then in `fetch()` (was lines 51-59), rename to preserve the dual basis:
```python
want = (["High","Low","Close","Adj Close","Volume"] if t in ohlc
        else ["Close","Adj Close","Volume"])
sub = sub[[c for c in want if c in sub.columns]].rename(columns={
    "Adj Close": "close",      # TR — SAME meaning as today's auto_adjust=True Close
    "Close":     "close_price",# split-adj, div-UNadj — the NEW structure-math basis
    "Volume":    "volume", "High":"high", "Low":"low",
}).dropna(subset=["close"])
```

**Why `Adj Close`→`close` is byte-safe:** `auto_adjust=True Close` ≡ `auto_adjust=False Adj Close` (both are
yfinance's dividend+split adjusted series). So the *existing* `close` column's values are **unchanged** by
this flip — no existing consumer's numbers move. `close_price` is purely additive. This is the critical
property that lets §2 ship independently of §3's migration.

**Upsert:** `close` (TR) keeps `overwrite_overlap=True` (adjusted-series re-scaling, per store docstring).
`close_price` is split-adjusted only → a split *also* re-scales its prior history, so it **also** needs
`overwrite_overlap=True`. Since both live in one frame, one `store.upsert(..., overwrite_overlap=True)` call
covers both. (Verify: A-share split events are rare in the US ETF/index universe; the overwrite span is the
1-month refresh window, so deep history is carried forward untouched — a split older than the window would
leave a basis-step in `close_price`. Guard: the `--full` monthly backfill re-pulls `max` and fully
overwrites, healing any step. See §6 audit check `split_step`.)

### 2.4 Full-history backfill (one-time)

`scripts/backfill_price_basis.py` (Sonnet). For every ticker in the yahoo group:
1. `yf.download(t, period='max', auto_adjust=False)` → Close + Adj Close.
2. Assert `Adj Close` matches stored `close` within tol (1e-6 relative) on overlapping dates — this
   **proves** the flip is basis-preserving before writing (fail loud on mismatch = a corrupt ticker).
3. `store.upsert('yahoo', t, frame_with_close_price, overwrite_overlap=True)`.

Cost: bounded by yfinance rate limits, not CPU. Batched like the collector; run once out-of-band (not in the
67-min render). Tickers where `max` history is unavailable (Stooq-recovered extras, dead names) → §2.5.

### 2.5 Tickers where price history is unavailable

- **Stooq-recovered extras** (`_fill_missing_extras`): Stooq `.us` daily is already unadjusted-ish price. Set
  `close_price = close_tr = stooq_close` and stamp `price_basis='stooq_unverified'` so the audit flags them
  as not-dual-basis-clean (they are a tiny minority, single stocks not cycle instruments).
- **Dead names** (`edgar_deadname_prices.py`): terminal-value backfill; not cycle instruments. `close_price`
  absent → readers fall back to `close` with a `basis_fallback=True` flag (§2.6 API).
- **Crypto / FX / futures in the yahoo group:** these have no dividends, so `Close`≡`Adj Close`. Set
  `close_price = close`. No structure-math distortion existed for them; the dual-basis is a no-op but the
  column is present for uniformity.

### 2.6 The read API (`engine/inputs.py`)

`yahoo_closes()` gains a `basis` parameter; the default preserves current behavior byte-identically.

```python
def _yahoo_close(name: str, basis: str = "tr") -> pd.Series | None:
    df = store.read("yahoo", name)
    if df is None: return None
    col = {"tr": "close", "price": "close_price"}[basis]
    if col in df.columns:
        return df[col]
    if basis == "price" and "close" in df.columns:
        # basis_fallback: pre-migration ticker or price-unavailable — degrade to TR, flagged
        _record_basis_fallback(name)          # feeds the audit + a build-time counter
        return df["close"]
    return df["close"] if "close" in df.columns else None

def yahoo_closes(basis: str = "tr") -> pd.DataFrame:      # default 'tr' == today's behaviour
    ...
    s = _yahoo_close(t.replace(...), basis=basis)
```

**Migration safety:** default `basis="tr"` means *nothing changes* for any caller until it explicitly opts
into `basis="price"`. Callers migrate one at a time (§4 sequencing), each in a reviewable diff.

### 2.7 China / akshare basis

- **Shenwan L1** (`china_sectors`): already **price-basis** (custodian index, not TR). So `china_sector_*`
  structure math is *already on the correct basis* — the audit's China distortion is NOT in the sector
  series, it is in the **benchmark** (§5). Action: stamp Shenwan series `price_basis='price'` (a metadata
  no-op) and record in the contract that no re-key is needed for China sector cycles. **This is a major
  scope reduction the audit's blanket "everything is TR" framing missed** (see NEW PROBLEM D4-N1).
- **China A-shares** (`china_stocks` adj / `china_stocks_raw` raw): the adjusted plane is TR-adjusted. For
  China *baskets* (which feed `sector_cycles_china` basket cards) the structure math should read a
  split-adjusted-div-unadjusted plane. yfinance `auto_adjust=False` on the `.SS/.SZ` symbols gives the same
  dual columns → add `close_price` to `china_stocks` via the same collector pattern
  (`collectors/china_prices.py:82`). HK likewise (`hk_prices.py`).
- **FRED series** (Case-Shiller, HY-OAS, ISM per N1): these are **levels, not prices** — no dividend basis
  exists. They carry `price_basis='level'` (n/a) and are exempt from the price-basis audit. The monthly
  kernel (Pillar D3-N1) reads them raw.

---

## 3. MIGRATION SEQUENCING — the re-key bomb (N2 is mine)

### 3.1 The problem, precisely

Flipping any structure-math consumer from `close` (TR) to `close_price` **re-dates every ZigZag turn** (the
detrended-linear vs true-price series pivot at different points). Two things break:

1. **`narratives.json` keys** are keyed on turn dates (a researched "why" bound to a specific dated peak/
   trough). New turn dates orphan every key.
2. **Frozen forward-log stamps** (`data/*/forward_log.parquet`, `data/*/calls.parquet`) carry a `pos`,
   `phase`, `signature`, `proj` computed on the OLD basis. Mixing old-basis and new-basis stamps in one
   grader corrupts the grade.

The 14% frozen ZigZag threshold (`sector_cycles.py:283-288`) exists *only* to keep dates stable for keys —
i.e. the repo chose to freeze a wrong-basis threshold rather than face this migration. We face it.

### 3.2 Decision: re-stamp existing logs on the new basis and DISCARD the old (argued)

**Yes — discard and re-stamp. Argument:**

- The existing forward logs are **single-date, zero-matured** (audit Part II #1: all logs began 2026-06-28,
  4 stamp dates, 21d shortest horizon → *nothing has matured*). There is **no track record to preserve** —
  discarding costs literally zero measured outcomes.
- D5's PIT backfill will regenerate the *entire* historical stamp series deterministically on the new basis
  anyway (stamps are pure price functions — S2 confirmed). So the "old" logs are about to be superseded by a
  from-scratch backfill regardless.
- Keeping old-basis stamps in the same parquet as new-basis backfilled stamps would be the *worst* outcome:
  a silent basis-mix that biases every grade (the exact failure the audit warns of). Discard is the only way
  to guarantee basis-homogeneity.

**Mechanism:** the migration script writes new logs with `basis_version` stamped on every row; the grader
(D5) hard-refuses to grade across mixed `basis_version` (raises, like `china_sector_cycles_grader` refuses
non-`bar_i+1` fills). Old parquets are moved to `data/_migration_archive/` (not deleted from git history) so
the migration is auditable but never re-read.

### 3.3 Narrative re-keying (nearest-turn match + key versioning)

`scripts/rekey_narratives.py` (Sonnet, one-time). For each engine that has a `narratives.json`
(`sector_cycles`, `country_cycles`, `china_sector_cycles`):

1. Load OLD turns (recompute on `close_tr` at the frozen 14% threshold — reproduces current keys) and NEW
   turns (compute on `close_price`).
2. **Match** each old key's turn date to the nearest new turn of the *same kind* (peak↔peak, trough↔trough)
   within a tolerance window `TOL_DAYS` (default 45 calendar days for sectors, scaled by the series' median
   half-cycle for slow instruments — a housing-scale turn tolerates a wider match than a 2-week whipsaw).
3. Emit a versioned key: `{"turn_id": "<ticker>__<kind>__<newdate>", "basis_version": 2,
   "prev_key": "<ticker>__<kind>__<olddate>", "match": "exact|shifted|orphaned|new"}`.
   - `exact` (Δ≤7d): carry the narrative verbatim.
   - `shifted` (7d<Δ≤TOL): carry the narrative, add `{rekey_shift_days: Δ}` so the UI can badge "turn
     re-dated on price basis".
   - `orphaned` (old turn has no new match within TOL): the narrative is retained but **detached** — moved to
     an `orphaned_narratives.json` for human review, never auto-plotted (a turn that vanished on the correct
     basis was probably a TR artifact — genuinely interesting signal, but not a plotted turn).
   - `new` (new turn has no old key): a fresh empty slot for research (feeds the research backlog).
4. Write `narratives.v2.json` keyed by `turn_id`; the build reads v2 and asserts every plotted turn's
   `turn_id` exists (orphans cannot be plotted).

**Key-versioning contract:** every narrative key is now `(ticker, kind, date, basis_version)`. A future basis
change (basis_version 3) re-runs the same matcher against v2. The `prev_key` chain makes every re-key
auditable back to the hand-researched original. This is the general re-keying strategy Fable's N2 asks for.

### 3.4 Ordering guarantee (no basis-mixing window)

The migration is **atomic per engine** in this order (each a squash-merged PR, same-day per house rules):

1. `close_price` column lands (§2) — additive, no reads change, no re-key. *Ship first, independently.*
2. Per engine E ∈ {sector_cycles, country_cycles, china_sector_cycles}:
   a. `rekey_narratives.py` produces `narratives.v2.json` for E (build still reads v1 — no visible change).
   b. Flip E's `_record_core` call site to `basis="price"` **and** switch the build to read v2 **and** archive
      E's old forward log **in the same commit**. This guarantees no build ever mixes v1 keys with v2 turns
      or old-basis stamps with new-basis stamps.
   c. D5 backfills E's forward log on the new basis (depends-on: this step).

A CI assertion (`audit_price_basis.py`, §6) fails the build if any engine reads `narratives.v1.json` after
its flip, or if a forward log contains >1 distinct `basis_version`.

---

## 4. Per-consumer migration ledger (which call site flips to `price`)

Every structure-math consumer, with its exact flip. Return/momentum consumers stay on `tr` (labeled).

| Consumer | File:sym | Reads today | Flip to | Notes |
|---|---|---|---|---|
| ZigZag turns | `sector_cycles._detect_swings` (via `_record_core`) | `full` (TR) | `price` | pass price series into `_detect_swings`; re-key required |
| Detrended osc | `sector_cycles._detrended_osc` | `full` (TR) | `price` | the 0-100 position — must be price |
| Phase classify | `sector_cycles._classify_phase` (uses `cycles.analyze`) | `full` (TR) | `price` | see `cycles.analyze` below |
| Ladder / DCL / failed-cycle | `cycles.analyze(full, kind='equity')` | `full` (TR) | `price` | `cycles.py:253` failed-cycle low; invalidation *price level* must be price |
| Median-half-cycle proj | `sector_cycles._project_next` | turns (derived) | `price` (inherited) | inherits corrected turns |
| RS vs SPY (63/126d) | `sector_cycles._leadership` | ratio of TR | **stay `tr`** | RS is a *return* ratio — TR/TR is correct and comparable; label it |
| `ret_win_pct` | `_record_core` | TR | **stay `tr`** | a return stat, labeled |
| `signal` BUY/SELL | `_record_core:329` | osc (price after flip) | inherits `price` | |
| Country cycle | `country_cycles._record_core` | USD-ETF TR | **`price` of LOCAL series** (§5) | biggest change — FX decomp |
| China sector cycle | `china_sector_cycles` | Shenwan (already price!) | **no flip** | already price-basis (D4-N1) |
| China basket cycle | `sector_cycles_china` baskets | member TR | `price` | add `close_price` to china_stocks |

**Key design point:** `cycles.analyze(series, kind=...)` is called with a *single* series today and internally
does both structure (troughs, DCL, failed-cycle) *and* some momentum (MACD/StochRSI on the same series). MACD
on TR vs price differs slightly. **Decision:** `cycles.analyze` gains an optional `price=None` kwarg; when
supplied, structure math (`find_troughs`, `cycle_state`, failed-cycle, invalidation level) uses `price` and
oscillators/MACD keep using the passed `series` (which callers set to `tr` for momentum fidelity, or `price`
if they want a single basis). Default `price=None` → current behavior (all on the passed series) → byte-safe.
`_record_core` passes `price=price_series, series=tr_series`. This is a Pillar-D2/ontology-adjacent change; I
specify the *substrate seam* (the `price=` kwarg contract) and hand the internal wiring to whoever owns
`cycles.py` (flag the dependency: **D4-W4 depends on the ontology pillar's `cycles.analyze` signature**).

---

## 5. FX DECOMPOSITION (country_cycles) — T5 country leg

### 5.1 Local-price series construction

For a single-country ETF with a known FX pair, the USD-ETF return decomposes multiplicatively:
```
(1 + r_usd)  =  (1 + r_local) · (1 + r_fx)          # r_fx = local-currency-per-USD return... sign matters
```
So the **local-currency price series** is:
```
P_local(t)  =  P_usd_etf_price(t) / FX_usdccy(t)     # FX quoted as CCY per USD (e.g. USDJPY)
```
where `P_usd_etf_price` is the ETF on **`price` basis** (§2, the div-unadjusted ETF price) and `FX_usdccy` is
normalized to *CCY-per-USD* (invert Yahoo pairs quoted as USD-per-CCY, e.g. EURUSD → 1/EURUSD). The forex
engine's `engine/forex_inputs.load_price()` (`:58-83`) already has this inversion logic and is directly
reusable (S4). Two construction paths, in priority order:

1. **Native local index** where available (8 HIGH-feasibility markets, S4): use the actual local index
   (`_N225`, `_KS11`, `_TWII`, `_GDAXI`, `_FCHI`, `_FTSE`, `_AXJO`, `_NSEI`) on price basis directly — this
   is the *cleanest* local-currency equity cycle (no ETF tracking error, no ETF fee drag, no synthetic
   division). The cycle is computed on **this**.
2. **Synthetic `ETF_price / FX`** for the 16 markets lacking a clean local index — computed on the fly, with a
   `lc_source='synthetic'` flag so the UI can note lower fidelity.

### 5.2 The separate FX leg record

`country_cycles` emits, per country, a **second labeled leg** alongside the equity cycle:

```json
"fx": {
  "pair": "USDJPY", "quote": "ccy_per_usd", "source": "yahoo:USDJPY_X",
  "basis": "price",
  "leg_return_63d": -4.2, "leg_return_252d": -11.8,      // FX contribution, labeled
  "cycle_pos": 71.3,                                      // FX's OWN detrended-osc position (is the CURRENCY stretched?)
  "cycle_phase": "Peak",                                  // FX cycle phase (optional, same kernel)
  "peg": null                                             // or {"band":"7.75-7.85","dist_bps":12} for EWH
}
```
The FX leg runs the *same* `_record_core` kernel on the FX price series, so "is the yen cycle stretched"
becomes a first-class, gradable read — not a hidden confound. The equity cycle card shows the **local-currency
equity cycle** (the honest "is Japanese equity cyclically cheap") and the FX leg shows the currency cycle
**separately**.

### 5.3 Per-turn equity-vs-FX attribution

At each detected **local-equity turn** (peak/trough on `P_local`), decompose the co-incident USD-ETF move into
equity vs FX contribution over the leg since the prior turn:
```python
def attribute_turn(p_local, p_usd, fx, t_prev, t_now):
    r_usd   = p_usd.loc[t_now]/p_usd.loc[t_prev] - 1
    r_local = p_local.loc[t_now]/p_local.loc[t_prev] - 1
    r_fx    = fx.loc[t_now]/fx.loc[t_prev] - 1          # ccy per usd
    return {"usd_leg_pct": r_usd*100, "equity_leg_pct": r_local*100,
            "fx_leg_pct": (r_usd - r_local)*100,        # residual = FX contribution to the USD experience
            "fx_share": abs(r_usd - r_local)/(abs(r_usd)+1e-9)}  # 0..1: how much of the USD move was currency
```
`fx_share` directly answers the audit's `cycle_dna.json` complaint ("EWJ fell 33% in dollars while local was
flat" → `fx_share ≈ 1.0`, flagged). Each turn record carries this attribution; a turn with `fx_share>0.6` is
badged "currency-driven" so the user never mistakes a yen crash for a Japanese-equity trough. This is
stamped, so D5 can **grade whether currency-driven turns behave differently** (registers as an experiment,
N4).

### 5.4 Bloc handling

Per S4: blocs (EFA/VGK/VPL/EEM/AAXJ/ILF/VXUS) have **no well-defined scalar FX** without time-varying
holdings weights. **Decision (adopt S4 recommendation):** blocs stay **USD-only** in the cycle engine; the FX
leg is `null` for blocs with a `fx: {"note": "multi-currency bloc — FX decomposition not defined"}` marker.
No synthetic bloc FX. Single-country ETFs get the full treatment; blocs get an honest "USD-basis, currency
mix not decomposed" label. VXUS (47 markets) explicitly `fx: {"note": "global — USD basis only"}`.

### 5.5 Collection gaps (per S4)

- 7 absent pairs (SEK/SGD/IDR/CLP/ZAR/TRY/PLN): add `USDXXX=X` to `config.yml yahoo.tickers.fx` — collects
  automatically. 5 have FRED DEX fallbacks (deep history); TRY/CLP are Yahoo-only.
- HKD peg (EWH): local≈USD return; ship a **peg-distance annotation** not a decomposition (S4). `hkma`
  collector already tracks peg distance.
- These are **Haiku** config-line adds + one collect run (D4-W5a).

---

## 6. BENCHMARK BASIS-MATCHING — every grader audited

The rule: **excess = instrument − benchmark on the *same* basis.** A price-return sector minus a TR benchmark
bakes in a chronic ~dividend-yield negative drift (audit #4). Every grader's benchmark load is audited below.

| Grader | Instrument basis | Benchmark today | Fix |
|---|---|---|---|
| `china_sector_central_grader.py:110-135` | Shenwan **price** | `china_sector_index.benchmark_close()` — **TR** (000001.SS via yahoo `close`=TR) | benchmark → **price basis**: `benchmark_close()` reads `close_price`. One-line data swap. **This is Phase-0-shippable NOW** (audit Part III) once `close_price` exists. |
| `sector_central_grader.py` | XLK etc. **price** (after flip) | SPY **TR** | benchmark SPY → `close_price`; instrument sectors → `close_price`; **both** price. |
| `china_sector_cycles_grader.py` | Shenwan **price** | (turn/drawdown self-relative — no bench) | audit: forward *return* leg should be labeled `tr` for the return channel; drawdown channel is price. Split the two channels' basis explicitly. |
| `sector_cycles` (no grader yet, D5 builds) | price after flip | SPY | born correct: D5 grader reads instrument+bench both `price` for excess, `tr` for absolute forward return, **labeled per column**. |
| Forward *return* horizons (all graders) | — | — | forward return is a **return** → compute on `tr` (a holder earns dividends). Forward **drawdown / MAE** → compute on `price` (a stop is hit on price, not TR). **This dual-channel labeling is the substrate contract's grader clause.** |

**Substrate contract clause for graders (hand to D5):** every forward metric column is suffixed with its
basis: `fwd_ret_21_tr`, `fwd_mdd_21_price`, `excess_63_price`. A grader that emits an unbasis-suffixed
forward column fails the audit. D5 owns the grader internals; D4 owns *this naming contract* and the
benchmark-basis table above.

---

## 7. FROZEN BASKET LEVELS + membership-hash (T5 freeze clause)

### 7.1 The leak, precisely

`sector_cycles.build_basket` calls `consolidated_candle(members, idx, mode='equal', pit=False)`
(`sector_cycles.py:409`). `pit=False` projects **today's** membership over full history — survivorship-not-
clean (engine docstring). Worse, basket levels are **null in the store**, so graders **re-run
`compute_*_baskets()` at grade time** (`china_sector_central_grader.py:117-122`) → an old stamp is silently
re-scored on a *refreshed, current-membership* series. A THS truncation event (memory:
`ths-truncated-scrape-fabricates-removals`) that fabricates mass removals would **silently rewrite every prior
basket grade**. This is the audit's most acute look-ahead/survivorship leak.

### 7.2 The frozen daily writer

New engine module `engine/basket_freeze.py` + build hook. Each build, **after** baskets are computed, freeze:

```
data/basket_levels/<domain>.parquet         # domain ∈ {us, china, china_ths, hk}
  index: date
  columns (wide, one per basket_id):
    <bid>__level_price    float64   # equal-weight index on PRICE basis (structure math reads this)
    <bid>__level_tr       float64   # equal-weight index on TR basis (return grading reads this)
    <bid>__mhash          object    # membership hash for THIS basket on THIS date (see 7.3)
    <bid>__n_members      int
```
Writer contract:
- **Append-only, immutable per (date, bid):** `store.upsert` with **no `overwrite_overlap`** — a frozen level
  for a past date is NEVER re-written. Once 2026-07-02's basket level is frozen, it is the PIT truth forever.
- Levels computed with `pit=True` where added/removed dates exist; where they don't (curated seed baskets),
  the freeze *is* the PIT record going forward (day-one membership is frozen; changes are dated from here).
- The grader reads `data/basket_levels/<domain>.parquet` **only** — it never calls `compute_*_baskets()`.
  (D5 hand-off: grader `_fwd_return` for baskets reads the frozen parquet; **the live-recompute path is
  deleted**.)

### 7.3 Membership hash

Per basket per date:
```python
def membership_hash(members: list[dict]) -> str:
    # canonical: sorted member identifiers only (not weights — equal-weight)
    ids = sorted(m["ticker"] if "ticker" in m else m["code"] for m in live_members)
    return hashlib.sha1("|".join(ids).encode()).hexdigest()[:16]
```
Stamped on every frozen row **and** on every forward-log stamp (the call). At grade time the grader asserts
the call's `mhash` matches the frozen series' `mhash` for the same basket over the forward window; a
**mismatch invalidates that grade** (drops it with reason `membership_changed`) rather than silently scoring
across a composition change. This makes a basket call gradable only over the window where its composition was
stable — the honest behavior.

### 7.4 Truncation-event invalidation (ties to THS failure mode)

The known failure (`ths-truncated-scrape-fabricates-removals`): a truncated THS scrape makes the seeder
fabricate mass removals → membership churns → `mhash` flips for many baskets on one date. Wiring:
- The freeze writer computes, per build, the **churn rate** = fraction of baskets whose `mhash` changed vs
  prior build. If churn > `CHURN_ALERT_PCT` (default 15%), the writer **refuses to freeze new levels** for
  that domain that day (keeps yesterday's frozen row, sets `freeze_skipped=true` with reason), and fires a
  `notify.send_telegram/discord` alert (the alerts infra `notify.py:113/129` is established — S5). This is
  the same guard as the existing `PruneGuardError` membership reconciler (memory:
  `membership-cache-reconciler`) — I reuse that pattern, not invent a new one.
- Any grade whose forward window straddles a `freeze_skipped` gap is dropped (`membership_uncertain`).

### 7.5 Build-cost budget

The freeze is a **write** of already-computed levels — the baskets are computed during the render anyway. The
only new cost is the parquet write (one wide frame per domain, ~4 writes/build). **Negligible** vs the 67-min
render. It does **not** add per-day recompute (that would be unbounded); it snapshots what's already computed.

---

## 8. GUARD RAILS — `scripts/audit_price_basis.py`

New audit, wired into `run_quality_audits` (`collect.py:290-296`) as a 5th audit fn, writing
`data/quality/price_basis_audit.json`, counting toward the collect gate.

### 8.1 Checks (each HARD-fail or FLAG)

| Check | Type | Rule |
|---|---|---|
| `dual_basis_present` | HARD | every cycle-instrument yahoo parquet (the sector/country/basket-member universe) has a `close_price` column with ≥99% coverage over the `close` span |
| `basis_preserving` | HARD | on a sample of tickers with dividends, `close != close_price` on a nontrivial fraction (else the flip silently didn't happen); AND `close` (TR) unchanged vs pre-migration snapshot within tol (the byte-safe invariant §2.3) |
| `split_step` | FLAG | `close_price` has no single-day jump > `SPLIT_STEP_PCT` outside a known split date (catches the out-of-window split basis-step §2.3) |
| `no_tr_in_structure` | HARD | **static AST scan** of `engine/sector_cycles.py`, `country_cycles.py`, `cycles.py`, `china_sector_cycles.py`: every call into `_detect_swings`/`_detrended_osc`/`find_troughs`/failed-cycle must trace to a `basis='price'` read. Implemented as an import-time contract: these functions assert their input series carries a `.attrs['price_basis']=='price'` tag (pandas Series `.attrs`), set by `_yahoo_close(basis='price')`. A `tr` series reaching structure math raises. |
| `bench_basis_match` | HARD | every grader's excess computation reads instrument and benchmark on the *same* basis (AST + `.attrs` tag check on the benchmark load) |
| `basis_version_homogeneous` | HARD | no forward-log parquet contains >1 distinct `basis_version` (§3.4) |
| `narratives_versioned` | HARD | every plotted `turn_id` in each engine's output exists in that engine's `narratives.v2.json` (no orphan plotted) |
| `basis_fallback_count` | FLAG | count of `_record_basis_fallback` events this build (tickers degrading price→tr); trend it |
| `frozen_levels_immutable` | HARD | `data/basket_levels/*.parquet` — no past (date,bid) `level_price` changed vs prior committed version (git diff assertion) |
| `basket_churn` | FLAG | per-domain `mhash` churn rate; ties to §7.4 alert |

### 8.2 The `.attrs` tag mechanism (enforcement primitive)

The cleanest enforcement: `_yahoo_close(basis=b)` sets `series.attrs['price_basis']=b`. Structure-math
functions guard:
```python
def _detect_swings(close, pct=_ZZ_PCT):
    if close.attrs.get('price_basis') not in ('price', None):   # None = legacy/unmigrated grace during rollout
        raise BasisContractError(f"_detect_swings requires price basis, got {close.attrs.get('price_basis')}")
```
After rollout completes, the `None` grace is removed (a follow-up wave) so the contract is total. This is a
runtime tripwire *in addition to* the static AST scan — belt and suspenders, because `.attrs` can be lost by
some pandas ops (a known caveat), so the AST scan is the authoritative gate and `.attrs` is the fast-fail dev
aid.

---

## 9. NEW PROBLEMS discovered while designing

**D4-N1 — China sector cycles are ALREADY on the correct (price) basis; the audit's blanket "everything is
TR" over-scopes the migration.** Shenwan L1 indices are custodian *price* indices via akshare
(`china_sectors.py:11-16`), not TR. So `china_sector_cycles` structure math needs **no basis flip and no
re-key** — a significant scope reduction. The China *distortion* the audit found is real but lives in the
**benchmark** (`benchmark_close()` returns TR 000001.SS, §6) and in China **baskets** (member A-shares are
TR-adjusted). *Evidence:* `china_sectors.py:11-16` docstring "real sector indices (not ETF proxies)";
`801010.parquet` base 1000.0 index levels. *Severity: MEDIUM (scope-reducing, prevents a needless destructive
re-key of the one engine that has a working grader).*

**D4-N2 — `close`≡`Adj Close` basis-invariance is UNVERIFIED for non-US yahoo symbols and could silently
corrupt the byte-safe migration.** My §2.3 byte-safety argument rests on `auto_adjust=True Close` ≡
`auto_adjust=False Adj Close`. This is documented yfinance behavior but I could only verify it empirically for
AAPL (US). For `.SS`/`.HK`/index/FX symbols the equality could differ (yfinance sometimes lacks Adj Close for
FX/indices → `Adj Close` may equal `Close`, silently making `close_tr==close_price` for a *dividend-paying*
non-US ETF, losing the TR series). *Mitigation:* the `basis_preserving` audit check (§8.1) catches this — but
the backfill (§2.4 step 2) must assert per-ticker and **quarantine** any ticker where `Adj Close` is absent or
equals `Close` on a known-dividend name, rather than writing a corrupt dual basis. *Severity: HIGH — must be a
hard gate in the backfill, not a post-hoc flag.*

**D4-N3 — The frozen basket-level parquet has a cold-start survivorship hole that freezing cannot fix.** §7
freezes levels *going forward* PIT-cleanly, but the *historical* portion of any basket level (before the
freeze starts) is still `pit=False` survivorship-projected — because there are no historical added/removed
dates for the curated/seed baskets (`membership.json` has a `seed_date` but not per-member add/remove
history). So D5's PIT backfill of *basket* cycles is survivorship-contaminated for the pre-freeze span, while
*ETF/Shenwan* backfills are clean. *Mitigation:* backfilled basket stamps carry `survivorship='projected'` for
dates < freeze_start and `survivorship='pit'` after; the grader reports basket-cycle grades **separately** for
the two spans and never pools them. Do not claim a basket track record on the projected span. *Severity: HIGH
— this bounds what D5 can honestly grade for baskets; ETFs/countries/Shenwan are unaffected.* (This reinforces
the audit's "separate scorecards for clean sectors vs hindsight baskets.")

**D4-N4 — `country_cycles` local-index history is SHORTER than the USD-ETF, silently truncating the local-
currency cycle window.** Per S4, `_NSEI` (India local) starts 2007 vs INDA/EWJ/EWY ETFs from 1996. Flipping
India's cycle to the native local index *loses 11 years of history* — the very deep history country_cycles
advertises ("single-country ETFs date to 1996"). *Mitigation:* construction priority (§5.1) must prefer the
**synthetic `ETF_price/FX`** path *when it has longer history than the native index*, not blindly prefer the
native index. Choose per-market by `max(coverage)`; stamp `lc_source` accordingly. *Severity: MEDIUM.*

**D4-N5 — `store.upsert overwrite_overlap` heals TR splits but the 1-month refresh window can leave a
`close_price` split-step for a split older than the window.** §2.3 notes this; calling it out as its own
problem because the *daily* collect (period='1mo') will not heal a split that occurred >1mo ago if the deep
history wasn't re-pulled. *Mitigation:* the `--full` monthly backfill must run on a schedule (it re-pulls
`max` and fully overwrites), and the `split_step` audit flag (§8.1) surfaces any unhealed step for a manual
`--full` trigger. *Severity: LOW (self-healing on the monthly full pull; flagged meanwhile).*

---

## 10. Verdict on Fable's theses (this pillar's touch-points)

**T5 (DUAL-BASIS DATA CONTRACT) — ADOPT, with one precision correction and two extensions.**
- *Correction:* the structure-math basis is yfinance `auto_adjust=False` **`Close`** (split-adjusted,
  dividend-unadjusted), **not** exchange-raw close. I verified empirically the flag yields both series in one
  pull — so the contract is cheap and byte-safe (§2.3). Fable's parenthetical ("naive raw close breaks
  ZigZag at every split") is exactly why we use the split-adjusted `Close`, not the raw one.
- *Extension 1:* the contract must extend to **graders** as a column-naming clause (`_price`/`_tr` suffixes,
  dual-channel: forward-return on TR, forward-drawdown on price) — §6.
- *Extension 2:* China sector cycles are **already** on the correct basis (D4-N1) — T5's migration does not
  apply uniformly; it is per-engine.
- *Refinement:* the FX "separate leg" (T5 country clause) is upgraded to a full `_record_core`-graded FX
  cycle leg + per-turn `fx_share` attribution (§5), so currency-driven turns become measurable, not just
  disclosed.

**T4 (BACKFILL-FIRST MEASUREMENT) — ADOPT (as a hard dependency, not owned here).** My migration (§3) is
sequenced *precisely so* D5's backfill runs on the corrected basis. I supply the substrate; D5 runs the
backfill. The critical inter-pillar contract: **D5 must not backfill any engine's log until that engine's
D4 basis-flip + re-key has merged** (else it backfills worthless wrong-basis grades — the audit's explicit
warning). I encode this as `basis_version_homogeneous` (§8) and the per-engine atomic flip (§3.4).

**T6 (NARRATIVE DEMOTED TO ANNOTATION) — ADOPT the re-keying half.** I do not own the annotation/staleness
layer, but the re-key migration (§3.3) is the mechanism that lets the hand-researched turning-point history
survive a basis change: nearest-turn matching + `turn_id` versioning + orphan quarantine. The curated DRAM/
uranium turn history is *preserved* (carried on `exact`/`shifted` matches; retained-but-detached on
`orphaned`), never thrown away — satisfying T6's "do NOT throw it away."

**T1 (TWO-TIER HONESTY SPLIT) — TOUCHED, not owned; I supply the FX tripwire substrate.** The FX leg's
`fx_share` and peg-distance annotations (§5) are exactly the kind of machine-evaluated tripwire T1's
falsifier DSL would consume ("this 'trough' is >60% currency"). I make them stamped and gradable; the DSL
itself is D3/D1's.

---

## 11. Waves (with tier, deps, acceptance gates)

Dependencies reference other pillars where named. House rule: each wave = a branch off main → PR →
same-day squash-merge.

### D4-W1 — Dual-basis store: collector + backfill + read API
- **Tier:** Sonnet.
- **Scope:** `collectors/yahoo.py` flip to `auto_adjust=False`, keep Close→`close_price` + Adj Close→`close`;
  same for `china_prices.py`, `hk_prices.py`. `scripts/backfill_price_basis.py` (one-time `max` backfill with
  per-ticker `Adj Close≡stored close` assertion + quarantine on absent/degenerate Adj Close — **D4-N2 hard
  gate**). `engine/inputs.py` `yahoo_closes(basis=...)` + `_record_basis_fallback`. `.attrs['price_basis']`
  tagging in `_yahoo_close`.
- **Files:** `collectors/{yahoo,china_prices,hk_prices}.py`, `scripts/backfill_price_basis.py`,
  `engine/inputs.py`, `lib/store.py` (confirm `overwrite_overlap` covers 2-col frame).
- **Depends on:** nothing (additive; default `basis='tr'` preserves all behavior).
- **Acceptance:** (1) `close` column values byte-identical to pre-flip on a 20-ticker sample (the byte-safe
  invariant); (2) `close_price` present, ≥99% coverage, differs from `close` on dividend-paying ETFs;
  (3) backfill quarantines ≥0 and writes a manifest; (4) `yahoo_closes()` with no arg returns the identical
  frame as before (regression test); (5) no ticker with a known dividend has `close_price==close` (D4-N2).

### D4-W2 — Benchmark basis-match (Phase-0 quick win) + audit skeleton
- **Tier:** Sonnet.
- **Scope:** flip `china_sector_index.benchmark_close()` and each grader's benchmark load to `close_price`;
  add the `_price`/`_tr` forward-column naming clause spec (a shared constant + assertion) that D5 will honor.
  Stand up `scripts/audit_price_basis.py` with the `dual_basis_present`, `basis_preserving`,
  `bench_basis_match` checks; wire into `run_quality_audits`.
- **Files:** `engine/china_sector_index.py`, `engine/{sector_central,china_sector_central,
  china_sector_cycles}_grader.py` (bench load only), `scripts/audit_price_basis.py`, `scripts/collect.py`
  (register 5th audit).
- **Depends on:** D4-W1 (needs `close_price`).
- **Acceptance:** every grader's excess reads instrument+bench same basis; audit runs green in
  `run_quality_audits`; `data/quality/price_basis_audit.json` written.

### D4-W3 — Re-key migration (narratives + log archive)
- **Tier:** Opus (the matcher tolerance/orphan policy is judgment) for the design of `rekey_narratives.py`;
  Sonnet to implement once the matching rules are fixed.
- **Scope:** `scripts/rekey_narratives.py` (nearest-turn match, `turn_id` versioning, orphan quarantine);
  produce `narratives.v2.json` for sector_cycles + country_cycles (NOT china_sector_cycles per D4-N1);
  archive existing forward logs to `data/_migration_archive/`.
- **Files:** `scripts/rekey_narratives.py`, `data/sector_cycles/narratives.v2.json`,
  `data/country_cycles/narratives.v2.json`, build readers gated behind a flag (not yet flipped).
- **Depends on:** D4-W1. **Coordinates with** the ontology pillar (turn primitive contract) — the `turn_id`
  format should match the ontology module's turn identity if that pillar defines one; **flag: align `turn_id`
  scheme with ontology-pillar W-turn**.
- **Acceptance:** v2 produced; every old key classified exact/shifted/orphaned; orphan file written; no key
  silently dropped; `prev_key` chain complete; build still reads v1 (no visible change yet).

### D4-W4 — Per-engine basis flip (atomic: read-flip + v2 + log-archive)
- **Tier:** Sonnet (well-specified by §4 ledger); the `cycles.analyze(price=...)` seam **depends on the
  ontology pillar** owning `cycles.py`.
- **Scope:** flip `sector_cycles._record_core` and `country_cycles._record_core` structure reads to
  `basis='price'`; switch builds to `narratives.v2.json`; archive old logs — **each engine in one commit**
  (§3.4). Add the `.attrs` runtime tripwires + AST `no_tr_in_structure` audit check.
- **Files:** `engine/sector_cycles.py`, `engine/country_cycles.py`, `engine/cycles.py` (the `price=` kwarg —
  **coordinate with ontology pillar**), `scripts/build_{sector_cycles,country_cycles}.py`,
  `scripts/audit_price_basis.py` (add `no_tr_in_structure`, `basis_version_homogeneous`,
  `narratives_versioned`).
- **Depends on:** D4-W3, **ontology-pillar `cycles.analyze` signature** (the `price=` kwarg). If ontology
  isn't ready, ship an interim: `_record_core` computes structure on price by passing the price series as the
  single `analyze` arg (loses MACD-on-TR fidelity but is basis-correct) — a documented interim.
- **Acceptance:** structure turns re-dated on price; no forward log mixes basis versions; every plotted turn
  has a v2 key; `.attrs` tripwire raises on a TR series in structure math (unit test); audit green.

### D4-W5 — FX decomposition (country_cycles)
- **D4-W5a (Haiku):** add 7 absent `USDXXX=X` pairs to `config.yml yahoo.tickers.fx` + 5 FRED DEX fallbacks
  to `fred.series`; one collect run. Acceptance: pairs present in `data/yahoo`/`data/fred`.
- **D4-W5b (Opus→Sonnet):** `engine/country_cycles.py` FX leg: local-series construction (native-index vs
  synthetic, choose by max coverage per D4-N4), separate `fx` leg record (§5.2), `_record_core` on the FX
  series, per-turn `attribute_turn` (§5.3), bloc `null`-FX marker (§5.4), HKD peg annotation. Register the
  "currency-driven turns behave differently?" study in `data/experiments/registry_seed.json` (N4).
- **Files:** `engine/country_cycles.py`, `engine/forex_inputs.py` (reuse `load_price`), `config.yml`,
  `data/experiments/registry_seed.json`, `scripts/build_country_cycles.py` (render the FX leg; i18n dual-span
  l-en/l-zh for the new labels — house rule).
- **Depends on:** D4-W4 (country cycle already on price+local basis), D4-W5a.
- **Acceptance:** each single-country card shows local-currency equity cycle + separate FX leg; each turn
  carries `fx_share`; EWJ historical currency-driven "trough" flags `fx_share>0.6`; blocs show USD-only note;
  experiment registered.

### D4-W6 — Frozen basket levels + membership hash + truncation guard
- **Tier:** Sonnet.
- **Scope:** `engine/basket_freeze.py` (daily wide-parquet writer, price+tr levels, `mhash`, `n_members`);
  build hook after basket compute for all 4 domains; churn guard + `freeze_skipped` + notify (reuse
  `notify.py`, `PruneGuardError` pattern); grader hand-off — graders read `data/basket_levels/*.parquet`,
  **delete** the live-recompute path (**coordinate with D5** which owns grader internals). Add audit checks
  `frozen_levels_immutable`, `basket_churn`.
- **Files:** `engine/basket_freeze.py`, `scripts/build_site.py` (freeze hook), `engine/*_grader.py` (basket
  `_fwd_return` reads frozen — **D5 coordination**), `scripts/audit_price_basis.py`.
- **Depends on:** D4-W1 (price+tr for level construction). **D5 depends on D4-W6** for leak-free basket
  grades.
- **Acceptance:** `data/basket_levels/{us,china,china_ths,hk}.parquet` written each build; past (date,bid)
  levels never re-written (git-diff immutability test); `mhash` stamped; a simulated 20% churn triggers
  `freeze_skipped` + alert; grader reads frozen series only (no `compute_*_baskets` in grade path).

### D4-W7 — Contract hardening (remove `.attrs None` grace, final audit)
- **Tier:** Haiku.
- **Scope:** after all engines migrated, remove the `price_basis in (..., None)` grace so any untagged series
  in structure math raises; flip audit flags to hard where appropriate; document the contract in a short
  `docs/PRICE_BASIS_CONTRACT.md`.
- **Depends on:** D4-W4, D4-W6.
- **Acceptance:** no `None`-basis series reaches structure math anywhere; contract doc committed.

---

## 12. Inter-pillar hand-off summary

| Seam | D4 provides | Consumer pillar |
|---|---|---|
| `close_price` column + `yahoo_closes(basis='price')` | corrected structure-math input | D3 hazard (fits on price turns), ontology (turn primitive on price) |
| `basis_version` on every stamp + `basis_version_homogeneous` gate | guarantees no wrong-basis grade | D5 backfill (must wait per engine) |
| `_price`/`_tr` forward-column naming + benchmark-basis table | grader basis contract | D5 grader-stats |
| frozen `data/basket_levels/*.parquet` + `mhash` | immutable PIT basket series | D5 basket grading (leak-free) |
| FX leg `fx_share` stamps + peg annotation | machine-evaluable currency tripwire inputs | D1 falsifier DSL / D3 hazard regime |
| `cycles.analyze(price=...)` kwarg **need** | structure-vs-momentum basis split | **ontology pillar owns the impl** — D4-W4 depends on it |
| `turn_id` scheme | versioned turn identity for re-keying | ontology pillar (align turn identity) |

---

## 13. Build-cost accounting (house 67-min constraint)

- W1 collector flip: **zero** added render cost (collect-time, one extra column). Backfill is out-of-band.
- W2 benchmark swap: zero (a column read).
- W3 re-key: one-time script, not in render.
- W4 basis flip: re-computes the same `_record_core` on a different series — **same cost** (56ms/call).
- W5 FX leg: adds one `_record_core` per single-country ETF (~24 extra calls × 56ms ≈ **1.3s** + FX reads).
  Negligible.
- W6 freeze: one parquet write per domain per build (~4 writes) — **negligible**; it snapshots
  already-computed levels, adds no recompute.

**Total added render cost: < 5 seconds.** No unbounded per-day recompute anywhere (the freeze explicitly
avoids it). Backfill (D5) is the heavy one and is out-of-band per S2 (~2 min sector-spine, ~27 min full) —
D4 adds nothing to it beyond ensuring it runs on the right basis.
