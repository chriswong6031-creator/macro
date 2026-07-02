# Pillar D2 — MEASUREMENT: make "measured, not asserted" true

**Author:** Principal quant-systems designer (D2 pillar)
**As of:** 2026-07-02
**Canonical checkout:** `/tmp/macro-cycle-fable-main/` (main @ `a51665054e`)
**Scope:** PIT backfill loop, shared grading-stats library, the three new promise-graders (turn P/R, cone coverage, reliability/Brier), binding calibration, basket integrity, experiment registration.

This pillar owns the sentence in the TL;DR that is currently false: *"MEASURED, not asserted" is, today, unmeasured.* Everything here exists to produce, on **day one**, a leak-free walk-forward track record for the numbers the platform already plots — and to make the word "validated" require a stored artifact rather than a hand-tuned constant.

---

## 0. Design posture and what the audit forces

Three facts from the audit + scouts fix the shape of this pillar:

1. **The stamps are already deterministic PIT functions of price.** S2 verified every stamped field of `sector_cycles._record_core` (`osc_pos`, `phase`, `signal`, ZigZag `turns`, `proj`, RS, `timing_state`, `action`, `dc_phase`) is a pure function of `close <= t`, and `sector_cycles.compute(asof=...)` already slices the panel correctly (`engine/sector_cycles.py:523,533-534`). **Backfill is a loop, not a new engine.** This is the single most important enabler — it means we can synthesize hundreds of matured windows retroactively without inventing new signal logic.

2. **The rigor already exists in one file and simply isn't propagated.** `engine/china_sector_cycles_grader.py` already has Wilson CIs (delegated to `china_sector_pathway._wilson`, line 56), date-blocked bootstrap (`_boot_gap_ci`, 800 draws, seed 7), `MIN_EARN_N=40`, the bar-i+1 convention guard (`_entry_pos` via `searchsorted(side="right")`), and a pre-registered verdict lattice (`accruing/earning/falsified/inconclusive`). The audit's demand ("propagate the `china_sector_cycles_grader` machinery into ALL graders") is a *library extraction*, not new statistics. **We port, we do not re-derive.**

3. **Backfill must run on a corrected basis or the grades are worthless.** TL;DR §24: "the recommended retroactive PIT backfill would produce the first real evidence — and must be run on a corrected (unadjusted-price, leak-free) basis." This binds D2 to Pillar D3 (data basis / dual-basis contract). We handle it with an explicit **basis-version stamp** in every backfilled row so that when D3 lands the corrected `close_price` series, the backfill can be re-run and the old (TR-basis) artifact is *superseded, not silently mutated*.

**The honest scope, decided up front (from S2):**
- **IN scope for PIT backfill:** the 11 US SPDR sector ETFs, the 24 country ETFs, the ~30 China Shenwan L1 sectors (all fixed-index, membership-free, price-pure).
- **OUT of scope / partial-honesty:** thematic baskets (`pit=False` membership blocker, `sector_cycles.py:409`), and every `sector_central` overlay layer (regime anchor / heat table / crowding — none archived, S2 §4). Baskets get a *frozen-level* path (§5) that makes them PIT-clean **prospectively** but are explicitly excluded from *retroactive* backfill.

---

## 1. `scripts/backfill_forward_logs.py` — the PIT loop

### 1.1 Purpose and honesty contract

Produce, for every engine-backed **PIT-clean instrument**, a synthetic forward-log stamp at each historical month-end (and — for the monthly-macro kernel, N1 — at each source-series release), using only `tape <= stamp_date`. The output is byte-for-byte schema-compatible with the live `append_forward_log` writers so the graders cannot tell a backfilled stamp from a prospective one — **except** for one honesty column: `provenance ∈ {prospective, backfilled}`.

### 1.2 Storage layout — **parallel `backfill.parquet` + provenance column** (decision)

**Decision: parallel file, not extend `calls.parquet`.** Justification:

- The live `forward_log.parquet` / `calls.parquet` files carry the **keep-FIRST-per-(date,id)** PIT invariant (`china_sector_cycles.py:351`, `china_sector_cycles_grader.py:234`). If we appended backfilled rows into the same file, a backfilled stamp for `2024-03-29` would forever occupy that (date,id) slot and *block* a future prospective stamp from ever landing there — corrupting the very PIT ledger the live writer protects.
- Backfill is **re-runnable and versioned** (basis changes under D3; ZigZag threshold changes under D5). A prospective log is **append-only and immutable**. Mixing a mutable artifact into an immutable one violates the ledger contract.
- The grader must be able to report *matured-from-backfill* vs *matured-live* separately (a reviewer will trust the live cohort more). A `provenance` column on a **merged read** gives us that without polluting either file on disk.

**Layout:**
```
data/<engine>/forward_log.parquet        # LIVE, append-only, immutable (unchanged)
data/<engine>/backfill.parquet           # NEW, fully rewritten each backfill run
data/<engine>/backfill_manifest.json     # NEW, provenance of the backfill run itself
```
Where `<engine> ∈ {sector_cycles, country_cycles, china_sector_cycles}` (US sector_cycles currently has **no** forward log at all — this pillar creates its writer too; see §1.7).

Every row in `backfill.parquet` carries the **live schema** plus:
```
provenance:      "backfilled"          # constant in this file
basis_version:   "tr_v0" | "price_v1"  # which price basis produced it (D3 coupling)
zz_version:      "zz14_v0" | ...        # ZigZag threshold family (D5 coupling / N2 re-keying)
backfill_run_id: "<iso8601>_<git_sha>"  # ties every row to a manifest entry
```

`backfill_manifest.json` schema:
```json
{
  "run_id": "2026-07-05T02:14:00Z_a51665054e",
  "generated_at": "...",
  "engine": "sector_cycles",
  "basis_version": "tr_v0",
  "zz_version": "zz14_v0",
  "cadence": "month_end",
  "asof_dates": ["2011-01-31", "...", "2026-06-30"],
  "n_instruments": 11,
  "n_stamps": 1980,
  "window_cap_bars": 800,
  "leak_guards_passed": true,
  "notes": "TR-basis; supersede when price_v1 lands (D3-W2)."
}
```

### 1.3 The grader read model (how graders consume both files)

Add ONE loader to `engine/grading_stats.py` (§2) that every grader calls instead of `pd.read_parquet(forward_log)`:

```python
def load_graded_log(engine: str, *, include_backfill: bool = True) -> pd.DataFrame:
    """Merge live + backfill logs with provenance, enforcing PIT keep-FIRST.
    Live rows ALWAYS win a (date,id) collision (a real prospective stamp
    supersedes a synthetic one for the same day). Returns a DataFrame with a
    'provenance' column so graders can stratify matured-live vs matured-backfilled."""
```
Collision rule: concat `[live(provenance="prospective"), backfill(provenance="backfilled")]`, `sort` live-first, `drop_duplicates(["date","id"], keep="first")`. This means the day live catches up to a backfilled date, the live stamp is authoritative and the synthetic one drops — no double-count, no leak.

### 1.4 The loop — cadence, fields, per-engine scope

```python
# scripts/backfill_forward_logs.py
CADENCE = "month_end"        # trading-month-end asof dates (see N3 note below)
WINDOW_CAP = 800             # trailing bars per call — ported from _cycle_fix_backtest.py:47
START = "2010-12-31"         # ~15y; clip per-instrument to max(first_valid + 300 bars)

def backfill_engine(engine: str, asof_dates: list[str]) -> pd.DataFrame:
    rows = []
    for asof in asof_dates:
        data = ENGINE_COMPUTE[engine](asof=asof)      # sector_cycles.compute(asof=...)
        for rec in engine_instruments(data):          # PIT-clean instruments only
            rows.append(stamp_row(rec, asof, engine)) # SAME shape as append_forward_log
    return pd.DataFrame(rows)
```

**Cadence decision (addresses N3 up front):** monthly month-end stamps for the daily-price kernel. Rationale: the phase wheel is a multi-month slow clock; daily stamps produce 62/63-overlapping forward windows (the audit's autocorrelation-inflation finding, predictive-power). Month-end stamping gives ~non-overlapping 21-bar windows and dramatically reduces effective-n inflation *at the source*. Weekly is offered as a config knob for the DC/ladder (faster) fields but **off by default**. The grader still corrects for residual overlap via `effective_n` (§2).

**`asof_dates` generation:** last trading day of each calendar month from the instrument's `max(first_bar + 300, START)` to the last complete month. Use the **benchmark (SPY / Shenwan composite) trading calendar** as the master so all instruments in an engine share stamp dates (required for date-blocked bootstrap to have shared blocks).

**Stamped fields, per engine** — exactly the live writer's columns so the grader is basis-blind:

| Engine | `stamp_row` source | Columns (match live) |
|---|---|---|
| `sector_cycles` (US) | `sector_cycles.compute(asof)["sectors"]` → `rec["now"]`, `rec["proj"]`, `rec["turns"]` | `date,id,kind,name,phase,pos,osc_slope,signal,above200d,rs_63d,proj_next(=proj.nextTurn),proj_central(=proj.central),proj_lo,proj_hi,turn_dates(json),timing_state,action,dc_phase` |
| `country_cycles` | `country_cycles.compute(asof)` (delegates to `_record_core`) | same core set; add `fx_leg` null placeholder for D3 |
| `china_sector_cycles` | `china_sector_cycles.compute(asof)` sectors only (drop `b-*`) | the existing 17-col schema (`china_sector_cycles.py:333-341`) |

**Cone fields must be logged for §3.2 (cone coverage).** The live writers stamp `proj_central` but NOT the band edges. We extend both the live writers and the backfill `stamp_row` to also stamp `proj_lo`, `proj_hi` (the projected turn-date window) and `cone_pos_lo`, `cone_pos_hi` if the projection carries a position band. Without these logged *at stamp time*, cone coverage is unmeasurable retroactively for the prospective cohort (we CAN reconstruct them for backfill since the projection is deterministic).

### 1.5 Leak guards (hard asserts, fail-loud)

Ported from the china grader's convention guard philosophy but pushed into the **producer**:

1. **Tape-≤-t assert.** In `stamp_row`, after `compute(asof)`, assert `data["meta"]["asOf"] <= asof` and that the underlying panel's last index `<= pd.Timestamp(asof)`. Raise `LeakError` otherwise. (Guards against a future refactor that forgets the slice.)
2. **Bar-i+1 forward anchor** is enforced downstream in the grader (`_entry_pos`), never in the producer — the producer never looks forward at all.
3. **No-partial-window** invariant inherited from `_fwd` (returns None until fully matured).
4. **Window-cap determinism assert:** for a spot-check set of (instrument, asof) pairs, assert that a call with `WINDOW_CAP=800` and a call with the full untrimmed tail produce the *same* stamped `phase`/`signal` (they must — the 252d osc + weekly MACD have look-backs << 800). This catches accidental long-look-back dependencies that would make the cap non-PIT-equivalent. Run as a `tests/test_backfill_window_cap_stable.py` gate, not every build.

### 1.6 Runtime budget (measured, from S2)

| Engine | Instruments × months | Calls | Measured cost | vs 67-min render |
|---|---|---|---|---|
| US sector ETFs | 11 × 180 | 1,980 | ~112 s | 3% |
| Country ETFs | 24 × 180 | 4,320 | ~4 min | 6% |
| China Shenwan | ~30 × 180 | 5,400 | ~5 min | 7% |
| **Total (no baskets)** | | ~11,700 | **~10–11 min** | ~16% |

**Budget rule:** backfill is a **one-shot / on-demand** script (regenerates `backfill.parquet`), NOT a per-build step. It runs (a) once now, (b) on each basis-version bump (D3), (c) on each ZigZag-version bump (D5), (d) on the calibration-refresh cadence (§4, quarterly). The **per-build** cost is only the grader read (`load_graded_log` + `grade`), which is seconds. This respects the 67-min CPU budget: **we add ~0 to every build; the 10-min backfill is out-of-band.** Baskets (the +27-min tail, S2 §5) are explicitly excluded from backfill for exactly this reason.

### 1.7 US sector_cycles has no writer — create it

`china_sector_cycles.append_forward_log` exists; `sector_cycles` (US) has none (audit: "the flagships have no grader at all"; US sector cycles logs only via `sector_central`). Add `sector_cycles.append_forward_log(data)` mirroring the china writer's shape, wired into `scripts/build_sector_cycles.py` so the **prospective** log starts accruing immediately alongside the backfill. Same for `country_cycles` (new `append_forward_log` + wire into `scripts/build_country_cycles.py`).

---

## 2. `engine/grading_stats.py` — the shared library

One module, zero new deps (pure numpy/pandas — S5 confirms all primitives are dep-free). Every grader imports from it; the china grader is refactored to import from it (removing its private copies) so there is exactly **one** implementation of each statistic.

### 2.1 Exact API

```python
# engine/grading_stats.py
"""Shared falsifiability primitives. Pure numpy/pandas (no scipy/sklearn) — matches the
thin data-bot env. Extracted canonical copies from china_sector_cycles_grader +
china_sector_pathway + validation, so every grader shares ONE implementation."""

MIN_N_DEFAULT   = 40          # ported from china_sector_cycles_grader.MIN_EARN_N
BOOT_DRAWS      = 800
BOOT_SEED       = 7
CONVENTION      = "first_close_strictly_after_stamp"

# ── interval estimators ────────────────────────────────────────────────────
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval. Canonical copy of china_sector_pathway._wilson."""

def block_bootstrap_ci(dates: np.ndarray, vals: np.ndarray, mask: np.ndarray,
                       *, draws=BOOT_DRAWS, seed=BOOT_SEED) -> list[float] | None:
    """Date-blocked bootstrap 95% CI on (conditional mean − base mean). Resamples whole
    stamp DATES so same-day cross-sectionally-correlated rows move together. Canonical
    copy of china_sector_cycles_grader._boot_gap_ci."""

def block_bootstrap_scalar_ci(series: pd.Series, *, block: int, draws=BOOT_DRAWS,
                              seed=BOOT_SEED) -> tuple[float, float] | None:
    """Moving-block bootstrap CI on a scalar summary (mean/Sharpe) of an autocorrelated
    series. Wraps validation.block_bootstrap_ci (validation.py:453) for calibration use."""

# ── overlapping-window correction ──────────────────────────────────────────
def effective_n(stamp_dates: np.ndarray, horizon_bars: int,
                calendar: pd.DatetimeIndex) -> float:
    """Effective independent sample size for OVERLAPPING forward windows.
    Two stamps whose [i+1, i+1+H] windows overlap share information; naive n
    over-counts. Implements the audit's fix: n_eff ≈ n / (1 + 2·mean_overlap_frac),
    where mean_overlap_frac is the average fraction of shared forward bars across all
    stamp pairs within H bars of each other. For monthly stamps at H=21 → n_eff≈n
    (no overlap); for daily stamps at H=21 → n_eff≈n/21. Used to DEFLATE every CI and
    to gate MIN_N on n_eff, not raw n."""

# ── multiple-testing ───────────────────────────────────────────────────────
def fdr_adjust(pvals: dict[str, float], q: float = 0.10) -> dict[str, bool]:
    """Benjamini–Hochberg FDR at level q over the tier×horizon×state grid. Returns
    {cell_key: passed_bool}. Pure numpy. The audit's 'FDR correction across the
    horizon×tier grid' requirement — no cell may print 'earning' unless it survives BH."""

def perm_pvalue(vals: np.ndarray, mask: np.ndarray, dates: np.ndarray,
                *, draws=2000, seed=BOOT_SEED) -> float:
    """Date-block permutation p-value for a conditional-vs-base gap (feeds fdr_adjust)."""

# ── gates & verdicts ───────────────────────────────────────────────────────
def min_n_gate(n_eff: float, min_n: float = MIN_N_DEFAULT) -> bool: ...

def dd_verdict(n_eff, ci, *, min_n=MIN_N_DEFAULT) -> str:
    """accruing/earning/falsified/inconclusive — canonical copy of _dd_verdict,
    but gated on n_eff not raw n."""

def rate_verdict(n_eff, ci, base, *, min_edge=0.05, min_n=MIN_N_DEFAULT) -> str: ...

# ── forward-window primitives (producer-blind, grader-side) ────────────────
def entry_pos(idx, stamp) -> int | None:      # bar-i+1, searchsorted(side="right")
def fwd_window(px, stamp, h) -> dict | None:  # {entry,exit,ret,maxdd} or None if unmatured
def assert_convention(name: str) -> None:     # raises on any non-bar-i+1 convention

# ── merged log reader (§1.3) ───────────────────────────────────────────────
def load_graded_log(engine, *, include_backfill=True) -> pd.DataFrame: ...
```

### 2.2 The `effective_n` formula (the audit's single biggest statistical fix)

The audit repeatedly flags CIs "~2.4–6× too narrow" from overlapping windows. Concrete implementation:

For stamp dates `d_1..d_m` (sorted, in bar-index space `b_i`) and horizon `H`:
```
overlap(i,j) = max(0, H - |b_i - b_j|) / H      # fraction of shared forward bars
avg_overlap  = mean over all pairs with |b_i-b_j| < H of overlap(i,j)
n_eff        = m / (1 + 2 * sum_{k=1..H-1} (H-k)/H * rho_k_est)   # Newey-West-style
```
Practically we use the tractable estimator `n_eff = m / (1 + 2·avg_overlap·avg_neighbors)` clamped to `[1, m]`, where `avg_neighbors` = mean count of other stamps within `H` bars. Monthly stamps at `H=21` → `avg_neighbors≈0` → `n_eff≈m`. Daily stamps at `H=63` → `n_eff≈m/63`. This is the load-bearing reason §1.4 chose **monthly** cadence: it makes `n_eff≈n` by construction, so we don't fight autocorrelation with a deflator that itself has estimation error.

### 2.3 Adoption plan (every grader)

| Grader | Change |
|---|---|
| `china_sector_cycles_grader.py` | Delete private `_wilson/_boot_gap_ci/_entry_pos/_fwd/_dd_verdict/_rate_verdict`; `from engine import grading_stats as gs`; gate on `gs.effective_n` instead of raw `n`. Behavior identical on monthly data; CIs correctly widen on any daily cohort. |
| `sector_central_grader.py` | Adopt `gs`; **split** sectors vs baskets into separate scorecards (audit fix); count 'flat' calls out of the P/R denominator; add `wilson_ci` to every rank-IC (currently 4-decimal, no CI); FDR across grid. |
| `china_sector_central_grader.py` | Same; fix basis-match (grade price sector vs price benchmark — D3 coupling); remove live-recompute basket leak by reading frozen basket levels (§5). |
| **NEW** `sector_cycles_grader.py` (US) | New file, direct port of the china grader against `gs` + the US `backfill.parquet`. |
| **NEW** `country_cycles_grader.py` | Same, with the FX-decomposition leg from D3 as a labeled second channel. |

---

## 3. THE THREE NEW PRIMITIVES

These grade what the platform *promises* (turns, cones, phase probabilities) — the audit's "measurement surface is pointed at the wrong target" fix. All three live in `engine/grading_stats.py` (functions) + a thin per-engine driver; they render on ONE **Measurement page** (§3.4) plus compact per-page badges.

### 3.1 Turn precision / recall

**What it grades:** did a stamped/projected turn actually occur, within tolerance, and did real turns get called?

**Matching rule.** Ground truth = the *confirmed* ZigZag turns on the full (post-hoc) series for that instrument, using the canonical turn primitive from Pillar D-ontology (T2). A projected/provisional turn stamp at date `s` with projected turn date `p` and direction `k∈{peak,trough}` is a **true positive** iff there exists a confirmed ground-truth turn of the same direction within tolerance `τ` bars of `p`:
```
TP: ∃ gt_turn with gt.kind==k and |bar(gt.date) - bar(p)| <= τ
FP: projected turn with no matching gt_turn within τ
FN: confirmed gt_turn with no projection pointing at it within τ
```
**Tolerance `τ`.** Phase-appropriate (N3): `τ = round(0.25 * median_half_cycle_bars)` per instrument, clamped `[10, 63]`. Rationale: a projection is a *window* not a point; ±25% of a half-cycle is the honest band. `τ` is **stored in the artifact**, not hand-set per render.

**Timing-error distribution.** For every matched TP, record `err_bars = bar(gt.date) - bar(p)` (signed: negative = turn came early). Report the distribution: `{median, iqr, p10, p90, n}` and a histogram. A systematically negative median = projections are *late* (the `find_troughs` repaint the audit flagged, cycles-core-4). This distribution **feeds the cone recalibration** (§3.2) and is itself the falsifier for "our projections lead turns."

**Data shape** (`data/<engine>/turn_pr.json`):
```json
{"schema":"turn_pr.v1","engine":"sector_cycles","as_of":"...","tolerance_rule":"0.25*half_cycle[10,63]",
 "provenance_split":{"backfilled":{...},"prospective":{...}},
 "per_instrument":{"xlk":{"tau_bars":22,"tp":14,"fp":6,"fn":5,
    "precision":0.70,"precision_ci":[0.48,0.85],"recall":0.74,"recall_ci":[0.51,0.88],
    "timing_err":{"median":-4,"iqr":11,"p10":-19,"p90":9,"n":14},
    "n_eff":18.2,"verdict":"accruing"}},
 "pooled":{"precision":..,"recall":..,"ci":..,"n_eff":..,"verdict":".."}}
```
Precision/recall CIs use `wilson_ci(tp, tp+fp)` and `wilson_ci(tp, tp+fn)` on `n_eff`. Verdict via `rate_verdict` (turns are a *timing* claim, sizing-ineligible → never "earning," capped at "inconclusive/falsified" per the china doctrine — but here they CAN earn a *calibration* verdict since a turn either happened or didn't; we allow "earning" for turn-P/R specifically because it is a factual, not a return, claim).

### 3.2 Cone coverage (the confirmed infra gap — S5 §2)

**What it grades:** of the projected turn windows `[proj_lo, proj_hi]` (and position bands `[cone_pos_lo, cone_pos_hi]`) the platform draws, what fraction actually contained the realized turn/position? A well-calibrated 80% cone should contain the outcome 80% of the time.

**Log at stamp time** (§1.4): `proj_lo, proj_hi` (turn-date band), `cone_pct` (nominal coverage, e.g. 0.80), and if the projection bands the *position* path, `cone_pos_lo/hi` per forward horizon.

**Empirical containment** (new function):
```python
def cone_coverage(stamps: pd.DataFrame, truth: dict[str, pd.Series], *,
                  nominal: float = 0.80) -> dict:
    """For each stamp with a logged band, determine if the realized turn date (matched via
    §3.1) fell in [proj_lo, proj_hi] AND/OR the realized position path stayed in the band.
    Returns empirical coverage, its Wilson CI, and a RECALIBRATION multiplier:
        cover_hat = k_inside / n
        if cover_hat < nominal: cone too tight  -> widen  factor = err_quantile(1-nominal)/current_halfwidth
        if cover_hat > nominal: cone too wide    -> tighten
    The recalibration multiplier is derived from the §3.1 timing-error distribution:
    the (1-nominal) quantile of |err_bars| IS the empirically-correct half-width."""
```
**Recalibration binds (§4).** The magic ramp `lerp(1.5,13)` / tilt weights `1.35/0.7` (audit cycle-flagship-4) are **replaced** by `cone_halfwidth = quantile(|timing_err|, nominal)` from the realized error distribution, stored in the calibration artifact and read by the projection code at build. No hand constants survive.

**Data shape** (`data/<engine>/cone_coverage.json`): per-instrument + pooled `{nominal, empirical, ci, n_eff, recal_halfwidth_bars, verdict}`.

### 3.3 Reliability curves + Brier vs per-instrument base rate

**What it grades:** the platform's probabilistic outputs — chiefly the **hazard model's** `P(turn within 1/3/6m)` (Pillar D-hazard, T3) and any `pos→P(down)` mapping. For each, bucket predictions into deciles, plot predicted vs observed frequency (reliability curve), and score Brier **against the instrument's own base rate**, not 0.5.

Reuse `validation.brier_reliability(p, y, n_bins=10)` (S5 §2, pure numpy, min N=30) via `grading_stats` re-export. The key correction the audit demands: **skill vs base rate.** Report `skill_score = 1 - brier/base_brier` where `base_brier = base_rate*(1-base_rate)` per instrument (a sector that turns 30% of windows must beat 0.21, not 0.25). Also expose `platt_fit` / `isotonic_calibration` (S5) so a mis-calibrated hazard output can be recalibrated and the recalibration stored (§4).

**Data shape** (`data/<engine>/reliability.json`): per-output `{brier, base_brier, skill_score, reliability:[{bin,n,pred,obs}], ece, n, n_eff, verdict}` + an `isotonic_model` blob if recalibration is applied.

### 3.4 Where it renders

**Decision: ONE new Measurement page (`site/measurement.html`) + compact per-page badges.**

- **`measurement.html`** — the honest scorecard hub. Tabs per engine (US sectors / countries / China sectors). Each tab shows: the three-primitive tables (turn P/R, cone coverage, reliability), the `provenance` split (backfilled vs live cohorts side by side — a reviewer sees the synthetic track record AND the growing real one), the calibration-artifact version + refresh date, and the `return_null` first-class output (ported from the china grader's honesty doctrine). Built by `scripts/build_measurement.py` reading the JSON artifacts. **No new engine compute at build** — it just renders committed JSONs.
- **Per-page badges.** On each cycle card, a small `data-lang` badge: `MEASURED · turn P/R 0.70 (n=18) · cone 78%` when the cell has matured, or `ACCRUING · matures 2026-09` when not. Badge text is dual-span `l-en/l-zh` (house i18n constraint) and reads a tiny `data/<engine>/badge_summary.json` (one row per instrument) so the card template needs no logic. The badge **replaces** the current unqualified authority — a hand-typed cycle.html card that has no grader shows `FRAME · not graded` (the T1 two-tier split surfaced here).

i18n note: all three JSON artifacts carry `caveat_en`/`caveat_zh` (ported from the china grader) and every rendered label is dual-span. `t()` never appears in an attribute (house rule); the badge is a `<span class="badge"><span class="l-en">…</span><span class="l-zh">…</span></span>`.

---

## 4. BINDING CALIBRATION — "validated" requires a stored artifact

The audit's calibration-theater finding (#6): `LADDER_SCORE` is a static dict; its walk-forward calibration is loaded for *display only* (`build_site.py:2172,2312`) and is **inverted** on the endpoint-return lens. D2 makes calibration *bind*.

### 4.1 The metric — risk-adjusted drawdown lens (not endpoint return)

The audit is explicit: the ladder ordering is defensible only on the **drawdown** lens (DECLINE has the deepest `dd_p10`; on return it's inverted). So the calibration objective is a **risk-adjusted** score, fit on walk-forward:
```
score_metric(state) = mean_fwd_ret(state) / |dd_p10(state)|      # return per unit tail risk
```
computed per state on the `backfill.parquet` matured windows, walk-forward (train on `[t0, t_k]`, score on `(t_k, t_{k+1}]`, roll). This is the "risk-adjusted drawdown-lens metric" the pillar brief names. The DECLINE-vs-FRESH-BUY inversion (S3: DECLINE +2.37%/dd_p10 −13.41% vs FRESH BUY +1.13%/−9.98%) resolves correctly: DECLINE's *return-per-tail* is 0.177 vs FRESH BUY's 0.113 — DECLINE still ranks higher but the tail cost is now *priced*, not hidden.

### 4.2 What gets fit and how

1. **LADDER_SCORE** (`cycles.py:406`) — become fitted values, not hand constants. Fit each state's score `∝ walk-forward score_metric`, normalized to `[-100, +100]`, from `backfill.parquet`. **Bind it:** `cycles.py:1038` reads the fitted artifact `data/calibration/ladder_score.json` instead of the static dict, with the static dict as a fallback only if the artifact is missing/stale.
2. **Tier cut-points** (the conviction→BUY/HOLD/AVOID thresholds) — fit as the decision boundaries maximizing walk-forward `score_metric` separation, with the boundary CIs from block bootstrap. Stored in `data/calibration/tier_cuts.json`.
3. **Fusion weights** (`sector_central` conviction blend) — fit by constrained walk-forward regression of forward `score_metric` on the component signals (osc, ladder, RS, trend-gate), **sign-constrained** via `calibrate_baskets._fit_logistic_signed` (pure numpy, S5 §3). Critically, per audit #6, the **trend/regime gates are moved out of the directional-confluence sum** and into a *size cap* — their fitted weight on the return channel is forced to 0 (they demonstrably have "no mean-return edge") and they instead multiply position size. Stored in `data/calibration/fusion_weights.json`.

### 4.3 Versioned artifact schema + the "validated" gate

```json
// data/calibration/<name>.json
{"schema":"calibration.v1","name":"ladder_score","version":"2026Q3_a51665054e",
 "fit_window":["2011-01-31","2025-06-30"],"holdout":["2025-07-31","2026-06-30"],
 "metric":"mean_fwd_ret / |dd_p10|","cadence":"quarterly",
 "values":{"DECLINE":{"score":-62,"metric":0.177,"ci":[0.09,0.26],"n_eff":41},...},
 "holdout_check":{"rank_corr_train_vs_holdout":0.71,"passed":true},
 "fdr_passed_cells":["DECLINE@21","FRESH_BUY@21",...],
 "validated": true,   // ← set ONLY if: n_eff>=MIN_N per cell AND holdout rank-corr>0.5
                      //   AND FDR-survived AND CI excludes the null. Else false.
 "generated_at":"...","git_sha":"..."}
```

**The gate (the load-bearing rule):** the string `"validated": true` — and therefore the word "validated" anywhere in the UI — may be emitted **only** by `grading_stats.emit_calibration_artifact()`, which sets it true iff: (a) every fit cell has `n_eff >= MIN_N`, (b) the train→holdout rank-correlation of `score_metric` exceeds 0.5, (c) the cell survives `fdr_adjust`, and (d) the block-bootstrap CI excludes the null. A build-time assertion (`tests/test_no_unearned_validated.py`) greps templates/JS for the token "validated"/"已验证" and fails if it appears without a backing artifact whose `validated==true`. This is how "the word 'validated' requires a stored artifact" becomes mechanically true.

### 4.4 Refresh cadence + N3 (phase-appropriate horizons)

- **Cadence:** quarterly re-fit (walk-forward extends the fit window, re-runs backfill on current basis, re-emits artifacts). Registered in the admin Experiments registry (§6) with `come_back_on = fit_date + 1 quarter`.
- **N3 — phase-appropriate horizons:** calibration is fit per **phase-appropriate horizon**, not a blanket 21d. Concretely: the DD/ladder (fast) channels calibrate on 21d/63d; the **phase-wheel and hazard** channels calibrate on **time-to-next-turn** windows (the hazard model's native 1/3/6-month horizons, T3) — NOT fixed 21d. The artifact's `metric` field records which horizon each channel used. Grading a monthly phase call at 21d (the audit's N3 "noise by construction") is *structurally prevented*: the `sector_cycles_grader` maps each stamped field to its registered horizon via a `FIELD_HORIZON` table (`phase→time_to_turn`, `signal→21d`, `ladder→21d/63d`, `hazard→calibrated 1/3/6m`).

---

## 5. Basket integrity — freeze levels, hash membership, invalidate not rewrite

The audit's basket leak (sector-central-us-miss, china-sector-central-3): basket forward returns are computed off a **live-recomputed current-membership** series, so an old stamp is silently re-scored on refreshed, mutable history — and `sector_cycles.py:409` hard-codes `pit=False`. Baskets are excluded from *retroactive* backfill (§0) but must be PIT-clean **prospectively**.

### 5.1 Frozen daily basket-level parquet + membership hash

New per-build step in `scripts/build_baskets*.py`:
```
data/baskets/levels/<basket_id>.parquet   # append-only: date, level (equal-weight), membership_hash
```
Each build appends **one row per basket**: the day's equal-weight consolidated level and `membership_hash = sha1(sorted(members))`. This freezes the level the stamp was computed on so a later membership edit cannot re-mark it. The forward-log stamp for a basket records the **`membership_hash`** it was computed under.

### 5.2 Grade invalidation (not rewrite) on membership edits

Grader read rule for baskets:
```python
# in *_central_grader / sector_cycles_grader basket path
level_series = read_frozen_levels(basket_id)          # NOT compute_china_baskets()
for stamp in basket_stamps:
    if stamp.membership_hash not in level_series.hashes_upto(stamp.date + horizon):
        stamp.status = "invalidated"   # membership changed inside the forward window
        continue                       # excluded from n_matured — NOT re-scored
    grade(stamp, level_series)         # PIT-clean: level is frozen at stamp time
```
When membership changes mid-window, the stamp is **invalidated** (dropped from `n_matured`, counted in a visible `n_invalidated`), never silently re-scored on the new series. This kills the look-ahead/survivorship leak (`china_sector_central_grader.py:33-42,114-124`) by construction. The frozen-level file also removes the null-basket-levels re-run entirely.

### 5.3 N2 — narrative re-keying migration (basis/threshold change re-dates turns)

When D3 (price basis) or D5 (ZigZag threshold) lands, every historical turn re-dates, orphaning `narratives.json` keys (the 14% freeze at `sector_cycles.py:283-288` exists precisely to avoid this). D2 provides the **re-keying utility** since it owns turn identity:
```python
# scripts/rekey_narratives.py
def rekey(old_turns, new_turns, narratives, *, tol_bars=15):
    """Nearest-turn matching: each old narrative key (a turn date) maps to the nearest
    new turn of the same direction within tol_bars. Unmatched keys -> quarantined with a
    'orphaned_by=<basis_version>' tag (never deleted — the curated prose is preserved per
    T6). Emits narratives.<basis_version>.json; the render reads the version matching the
    live basis_version, so old and new coexist during migration."""
```
Key versioning: `narratives.json` gains a `basis_version` field; the loader (`build_sector_cycles.py:_load_narratives`) selects the file matching the engine's live `basis_version`. This makes the basis migration non-destructive to curated history (T6 constraint) and is the concrete answer to N2.

---

## 6. N4 — register accruing measurements in the admin Experiments registry

Every new accruing measurement gets a `data/experiments/registry_seed.json` entry (20-field schema, S3 §5) so it doesn't float free and gets a machine-tracked come-back date + Telegram/Discord alert on state change (`experiments_registry.py:182-183` already dispatches).

New entries (one per (engine × primitive) + the calibration refits):
```json
{"id":"sector-cycles-turn-pr","name":"US Sector Cycles — Turn Precision/Recall","kind":"track_record",
 "priority":"high","cadence":"daily","what":"Do projected turns land within tolerance of confirmed turns?",
 "source":"engine/sector_cycles_grader.py","storage":"data/sector_cycles/turn_pr.json",
 "track_json":"data/sector_cycles/turn_pr.json","hook":"track_record",
 "started":"2026-07-05","come_back_on":"2026-09-03","come_back_note":"21d cells mature ~2m post-first-live-stamp; backfill cohort matured day-one",
 "maturation":"n_eff>=40 AND wilson-lo>0.5 for precision","status":"measuring",
 "state":"backfill cohort matured (n_eff=182 pooled); live cohort accruing","next_step":"promote badge from ACCRUING to MEASURED once live n_eff>=40",
 "phase_hint":"measurement"}
```
Analogous entries: `*-cone-coverage`, `*-reliability`, and `calibration-ladder-score-refit` (cadence `quarterly`, `come_back_on` = next quarter). Because the **backfill cohort matures day-one**, these entries start at `status:"measuring"` (not `"accruing"`) — the whole point of the pillar: real numbers on day one.

---

## NEW PROBLEMS discovered while designing

**N-D2-1 — Cone edges are not logged at stamp time, so the prospective cohort's cone coverage is unmeasurable retroactively.** Evidence: `china_sector_cycles.append_forward_log` (`china_sector_cycles.py:333-341`) stamps `proj_central` but never `proj_lo/proj_hi`; the US writer doesn't exist. Cone coverage (§3.2) needs the band edges *as they were drawn*. Backfill can reconstruct them (deterministic), but the **live** cohort will have a permanent hole for every day between now and when we add the columns. **Severity: HIGH** — must extend the live writers (§1.4) *before* the first prospective stamp we intend to grade for cones. Fix is one-line-per-writer but time-critical.

**N-D2-2 — `_project_next` uses a *full-sample* median half-cycle, which is mildly non-PIT at short histories.** Evidence: S2 marks `proj` PIT-pure, and it is *anchored* at `last_ts`; but `_project_next(swings_all, last_ts)` computes the median over **all** swings in `swings_all`, and `swings_all = _detect_swings(full, pct)` where `full` is the ≤t slice — so it IS PIT. However, the provisional last swing is the *running extreme*, which repaints as new bars arrive. For backfill this is fine (each asof re-derives). But it means the **prospective** `proj_central` logged today can differ from what the same date's stamp would show tomorrow if the last leg extends. **Severity: MEDIUM** — the grader must grade the `proj_next` *as stamped* (keep-FIRST already does this), but reviewers should know provisional projections are inherently noisier; flag in the cone artifact as `provisional_last=True`.

**N-D2-3 — Date-blocked bootstrap degenerates when backfill stamps share dates across few months.** Evidence: `_boot_gap_ci` requires `len(unique(dates)) >= 2` (`china_sector_cycles_grader.py:146`). With **monthly** backfill (§1.4) an instrument has ~180 distinct stamp dates — fine. But **per-instrument** cells (e.g. one sector's turn P/R) may have only a handful of matured turns, and the block bootstrap resamples *dates*; with few turn events the CI can collapse. **Severity: MEDIUM** — mitigate by pooling per-family (the T3 shrinkage) for the CI and reporting per-instrument point estimates with the *pooled* CI when `n_eff < MIN_N` per instrument. Document that per-instrument verdicts stay "accruing" longer than pooled.

**N-D2-4 — The backfill `git_sha` provenance is only meaningful if the engine code is pinned; a mid-migration engine edit silently changes what "the same stamp" means.** Evidence: backfill re-runs on basis/threshold bumps (§1.6). If someone edits `_classify_phase` between two backfill runs without bumping a version, the manifest `git_sha` differs but nothing forces a re-key or supersede. **Severity: MEDIUM** — add an `engine_fingerprint` (hash of `sector_cycles.py` + `cycles.py` phase/turn functions) to the manifest; the grader refuses to merge a `backfill.parquet` whose `engine_fingerprint` differs from the live engine's, forcing an explicit re-run.

---

## VERDICT on Fable's theses (the ones D2 touches)

- **T3 (hazard-model projections) — ADOPT, with a scope caveat.** D2 provides the *grading substrate* (reliability curves, Brier-vs-base-rate, calibrated cones) that makes a hazard model falsifiable, and the backfill provides its training data. But S5 confirms **no survival model exists** and `statsmodels` is not a declared dep. D2 recommends the hazard model be a **pure-numpy discrete-time logistic** (`P(turn in next k months | age, amplitude, quad, breadth, vol)`) fit with `_fit_logistic_signed`-style code — *not* Cox/lifelines — so it stays in the thin-env doctrine. The pooling/shrinkage (T3's tiny-n fix) is exactly the per-family CI pooling in N-D2-3. **Refined: hazard model = pooled numpy logistic, graded by §3.3.**

- **T4 (backfill-first measurement) — ADOPT, this pillar IS T4.** The one refinement: the pillar brief says "port from china_sector_cycles_grader" — I upgrade this to *extract into a shared library and refactor the china grader to import it*, so there is one implementation, not a copy. And "calibration BINDS" is made mechanical via the `validated` artifact gate (§4.3) + a template-grep test.

- **T1 (two-tier honesty split) — ADOPT at the badge layer.** D2 surfaces the split concretely: engine-backed instruments get a `MEASURED/ACCRUING` badge from a real artifact; hand-typed cycle.html cards get `FRAME · not graded`. D2 doesn't build the falsifier DSL (that's another pillar) but the badge is where the two tiers become *visually* distinct — the audit's core "laundering" fix.

- **T5 (dual-basis contract) — ADOPT as a coupling, own the versioning.** D2 doesn't define the basis (D3 does) but owns the **`basis_version` stamp** on every backfilled row and the **supersede-not-mutate** re-run discipline (§1.2) + the N2 re-keying utility (§5.3). This is the concrete mechanism that lets D3's basis fix flow through measurement without silently invalidating history.

- **T6 (narrative demoted to annotation) — ADOPT via re-keying.** §5.3's `rekey_narratives.py` *preserves* curated prose (quarantines orphans, never deletes) exactly as T6 demands, and versions narrative files by basis so old/new coexist during migration.

- **T7 (interaction only after lead-lag measured) — ADOPT as a dependency.** The backfilled canonical turns (§1) ARE the input the T7 Phase-0 lead-lag study needs. D2 explicitly produces the leak-free turn series; the interaction engine is downstream and out of D2 scope. No refutation — D2 is a prerequisite.

- **T2 (compiled ontology) — TOUCHED, dependency.** Turn P/R (§3.1) needs the ONE canonical turn primitive T2 defines. D2 consumes it; if T2 slips, §3.1 uses `_detect_swings` confirmed turns as the interim ground truth and re-keys when the ontology lands.

---

## WAVES (with tier, dependencies, acceptance gates)

**D2-W1 — `engine/grading_stats.py` extraction + china-grader refactor.**
*Scope:* Extract all primitives (§2.1) into one module; add `effective_n`, `fdr_adjust`, `cone_coverage`, `load_graded_log`; refactor `china_sector_cycles_grader.py` to import them; unit tests proving identical output on the existing china log.
*Files:* `engine/grading_stats.py` (new), `engine/china_sector_cycles_grader.py` (refactor), `engine/china_sector_pathway.py` (keep `_wilson`, re-export), `tests/test_grading_stats.py`.
*Tier:* **sonnet** (well-specified port; formulas given).
*Depends on:* nothing.
*Acceptance:* china grader output byte-identical on current data; `effective_n` returns `≈n` for monthly, `≈n/H` for a synthetic daily fixture; `fdr_adjust` matches a hand-computed BH example; no scipy/sklearn import.

**D2-W2 — Live writers for US sector_cycles + country_cycles + cone-edge columns (fixes N-D2-1, time-critical).**
*Scope:* Add `append_forward_log` to `sector_cycles` and `country_cycles` mirroring the china writer; extend ALL THREE writers with `proj_lo/proj_hi/cone_pct` columns; wire into the three build scripts.
*Files:* `engine/sector_cycles.py`, `engine/country_cycles.py`, `engine/china_sector_cycles.py`, `scripts/build_sector_cycles.py`, `scripts/build_country_cycles.py`, `scripts/build_china_library.py`.
*Tier:* **sonnet**.
*Depends on:* nothing (parallel to W1). **Ship first** so live cohort starts logging cone edges immediately.
*Acceptance:* one prospective stamp per instrument lands with non-null `proj_lo/proj_hi`; keep-FIRST invariant preserved; build cost delta < 5s.

**D2-W3 — `scripts/backfill_forward_logs.py` + `backfill.parquet` + manifest.**
*Scope:* The PIT loop (§1); month-end asof generation; 800-bar cap; leak-guard asserts; `engine_fingerprint` (fixes N-D2-4); write `backfill.parquet` + `backfill_manifest.json` for the 3 PIT-clean engines (ETFs/countries/Shenwan, NO baskets).
*Files:* `scripts/backfill_forward_logs.py` (new), `tests/test_backfill_leak_guards.py`, `tests/test_backfill_window_cap_stable.py`.
*Tier:* **sonnet** (loop + asserts fully specified); **opus** review of the leak-guard asserts.
*Depends on:* D2-W1 (`load_graded_log` schema), D2-W2 (cone columns to reconstruct). Ideally **after D3-W1** (corrected basis) so the first backfill is `price_v1` — but can run on `tr_v0` first with `basis_version` stamped, then re-run.
*Acceptance:* ~11,700 stamps in ~10 min; every row has `provenance/basis_version/zz_version/engine_fingerprint`; leak-guard tests pass; spot-check 5 (instrument,asof) pairs reproduce identical stamps with/without 800-cap.

**D2-W4 — The three primitives as graders + artifacts.**
*Scope:* Implement `sector_cycles_grader.py` + `country_cycles_grader.py` (new) and extend the china grader with turn-P/R (§3.1), cone-coverage (§3.2), reliability (§3.3); emit the JSON artifacts + `badge_summary.json`.
*Files:* `engine/sector_cycles_grader.py`, `engine/country_cycles_grader.py` (new), `engine/china_sector_cycles_grader.py` (extend), `engine/grading_stats.py` (add primitive drivers).
*Tier:* **sonnet** for the graders; **opus** for the turn-matching tolerance rule + `n_eff` pooling decisions (N-D2-3).
*Depends on:* D2-W1, D2-W3. Turn ground-truth needs the T2 turn primitive — use interim `_detect_swings` if T2 not landed.
*Acceptance:* backfill cohort produces matured cells (n_eff>0) day-one; every rate carries a Wilson/bootstrap CI; no cell prints "earning" without FDR survival; `return_null` first-class output present.

**D2-W5 — `site/measurement.html` + per-page badges.**
*Scope:* `scripts/build_measurement.py` renders the artifacts into the Measurement page (per-engine tabs, provenance split, calibration version); add the dual-span `MEASURED/ACCRUING/FRAME` badge to cycle cards reading `badge_summary.json`.
*Files:* `templates/measurement.html.j2` (new), `scripts/build_measurement.py` (new), `templates/sector_cycles.js` + `templates/china.html.j2` + country template (badge injection), nav wiring.
*Tier:* **sonnet** (render); **haiku** for the i18n dual-span string pairs.
*Depends on:* D2-W4. i18n house rules apply (dual-span, no `t()` in attributes, zh color flip).
*Acceptance:* page renders committed JSONs with zero engine compute; badges show correct state per instrument; i18n lint passes; mobile-fit at 375px.

**D2-W6 — Binding calibration.**
*Scope:* Walk-forward fit of LADDER_SCORE / tier cuts / fusion weights on the risk-adjusted drawdown metric (§4); `emit_calibration_artifact()` with the `validated` gate; bind `cycles.py:1038` to read the artifact; N3 `FIELD_HORIZON` table; template-grep test for unearned "validated".
*Files:* `scripts/calibrate_cycles.py` (new), `data/calibration/*.json`, `engine/cycles.py` (bind read at :1038), `engine/grading_stats.py` (`emit_calibration_artifact`), `tests/test_no_unearned_validated.py`.
*Tier:* **opus** (the fit design, holdout gate, and the "validated" contract are judgment calls).
*Depends on:* D2-W3 (backfill = training data), D2-W4 (metrics). Should follow **D3** (correct basis) so the fitted scores aren't on TR-distorted returns.
*Acceptance:* `ladder_score.json` reproduces the DECLINE>FRESH-BUY ordering on the *risk-adjusted* metric with CIs; `cycles.py` reads the artifact (grep confirms the static dict is fallback-only); `test_no_unearned_validated` fails on a planted unearned "validated" token.

**D2-W7 — Basket integrity + narrative re-keying (N2).**
*Scope:* Frozen basket-level parquet + membership-hash (§5.1); grader invalidation path (§5.2); `rekey_narratives.py` (§5.3) + `basis_version` on narrative files.
*Files:* `scripts/build_baskets*.py` (freeze step), `engine/*_central_grader.py` (frozen-level read), `scripts/rekey_narratives.py` (new), `scripts/build_sector_cycles.py` (versioned narrative loader).
*Tier:* **sonnet**; **opus** for the nearest-turn re-keying tolerance.
*Depends on:* D2-W1; couples to D3/D5 (runs when basis/threshold changes). Reference **D3-W2** (basis landing) and any D5 ZigZag-threshold wave.
*Acceptance:* a simulated membership edit mid-window invalidates (not re-scores) the affected stamps; `n_invalidated` visible; re-keying preserves 100% of curated prose (orphans quarantined, zero deletions).

**D2-W8 — Register in admin Experiments registry (N4).**
*Scope:* Add the seed entries (§6) for all new measurements + calibration refits; verify state-change alert dispatch.
*Files:* `data/experiments/registry_seed.json`.
*Tier:* **haiku** (structured data entry against a known schema).
*Depends on:* D2-W4, D2-W6 (artifacts must exist to point `track_json` at).
*Acceptance:* entries validate against the 20-field schema; `come_back_on` dates set; a manual state-change fires a Telegram/Discord test.

---

### Wave dependency summary
```
W2 (writers/cone cols) ──┐
W1 (grading_stats) ──────┼──> W3 (backfill) ──> W4 (primitives) ──> W5 (measurement page)
                         │                          │
                         │                          └──> W6 (binding calibration) [after D3]
                         └──> W7 (basket/rekey) [couples D3/D5]
                                                    W4,W6 ──> W8 (registry)
```
**Critical path:** W2 ships first (stop the cone-edge data hole bleeding), then W1→W3→W4→W5 is the spine that turns "unmeasured" into a day-one track record. W6 (binding) is the payoff but should wait for D3's corrected basis so we don't fit on TR-distorted returns.
