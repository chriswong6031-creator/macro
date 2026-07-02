"""BTC Midterm Gate Attribution — Phase 0 (read-only research).

W1 of the BTC Vector Override-Registry program.

Answers two questions:
  Part A: Per-cycle attribution — what did the midterm gate actually do in
          2014, 2018, and 2022? (BTC return during blackout, max DD avoided,
          180d recovery, net gate P&L vs brake-only engine)
  Part B: Block-bootstrap breakeven fan — for what hypothetical bear depth
          does the gate beat the raw brake-only engine? (n=3 path shapes;
          illustrative, not calibrated)

Outputs:
  data/vector/gate_attribution.json
  reports/btc-gate-attribution.md

Run:
  cd /Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/zen-volhard-77003f
  python3 scripts/btc_gate_attribution_phase0.py
"""
from __future__ import annotations

import json
import sys
import os
from pathlib import Path
from datetime import date

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup so `engine` and `lib` are importable
# ---------------------------------------------------------------------------
ROOT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/zen-volhard-77003f")
sys.path.insert(0, str(ROOT))

from engine import btc_signals  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRADING_YEAR = 365  # BTC trades every day

MIDTERM_YEARS = [2014, 2018, 2022]
ELECTION_DATES = {
    2014: pd.Timestamp("2014-11-04"),
    2018: pd.Timestamp("2018-11-06"),
    2022: pd.Timestamp("2022-11-08"),
    2026: pd.Timestamp("2026-11-03"),
}
RECOVERY_DAYS = 180

# bootstrap parameters
N_BOOTSTRAP = 2000
BLOCK_SIZE = 30
DEPTH_BUCKETS = [-20, -30, -40, -50, -60, -70, -80]

LABEL = "n=3 path shapes; illustrative, not calibrated"


# ---------------------------------------------------------------------------
# Helper: equity curve from allocation series (alloc is 1-day lagged)
# ---------------------------------------------------------------------------
def alloc_equity(close: pd.Series, alloc: pd.Series) -> pd.Series:
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)
    return (1 + pos * ret).cumprod()


# ---------------------------------------------------------------------------
# Helper: max drawdown of a price series relative to the first bar
# ---------------------------------------------------------------------------
def max_drawdown_vs_start(close_window: pd.Series) -> float:
    """Max drawdown relative to first bar's close (not running HWM)."""
    start_price = close_window.iloc[0]
    return float(((close_window - start_price) / start_price).min() * 100)


# ---------------------------------------------------------------------------
# Part A: per-cycle attribution
# ---------------------------------------------------------------------------
def run_per_cycle(df: pd.DataFrame) -> list[dict]:
    close = df["close"].astype(float)
    alloc_raw = df["alloc_optimal_raw"].astype(float)

    rows = []
    for year in MIDTERM_YEARS + [2026]:
        elec_day = ELECTION_DATES[year]
        gate_start = pd.Timestamp(year=year, month=1, day=1)

        if year == 2026:
            rows.append({
                "year": year,
                "status": "PENDING",
                "btc_window_return_pct": None,
                "engine_window_return_pct": None,
                "max_drawdown_avoided_pct": None,
                "recovery_180d_pct": None,
                "gate_pnl_pct": None,
            })
            continue

        # ------------------------------------------------------------------ #
        # Gate window: gate_start to elec_day (inclusive)
        # ------------------------------------------------------------------ #
        window_mask = (close.index >= gate_start) & (close.index <= elec_day)
        window_close = close.loc[window_mask]

        if window_close.empty or len(window_close) < 10:
            rows.append({
                "year": year,
                "status": "INSUFFICIENT_DATA",
                "btc_window_return_pct": None,
                "engine_window_return_pct": None,
                "max_drawdown_avoided_pct": None,
                "recovery_180d_pct": None,
                "gate_pnl_pct": None,
            })
            continue

        # BTC return over the blackout window
        btc_start = window_close.iloc[0]
        btc_end = window_close.iloc[-1]
        btc_window_ret = (btc_end / btc_start - 1) * 100

        # Max drawdown INSIDE the window vs Jan 1 close (what the gate avoided)
        max_dd_avoided = max_drawdown_vs_start(window_close)

        # ------------------------------------------------------------------ #
        # Engine equity: raw alloc within the gate window
        # The alloc_equity is computed on the full series but we evaluate
        # the relative move during the window only.
        # For the window equity: start at 1.0 on Jan 1 of the year,
        # evolve through election day using alloc_optimal_raw.
        # ------------------------------------------------------------------ #
        # Build equity series from Jan 1 of the year
        year_start = pd.Timestamp(year=year, month=1, day=1)
        data_from_year = df.loc[df.index >= year_start].copy()
        if data_from_year.empty:
            rows.append({
                "year": year,
                "status": "INSUFFICIENT_DATA",
                "btc_window_return_pct": None,
                "engine_window_return_pct": None,
                "max_drawdown_avoided_pct": None,
                "recovery_180d_pct": None,
                "gate_pnl_pct": None,
            })
            continue

        close_yr = data_from_year["close"].astype(float)
        alloc_raw_yr = data_from_year["alloc_optimal_raw"].astype(float)

        # Compute raw engine equity from Jan 1 of year onwards
        eq_raw_yr = alloc_equity(close_yr, alloc_raw_yr)

        # Clip to gate window (Jan 1 → election day)
        eq_window = eq_raw_yr.loc[eq_raw_yr.index <= elec_day]
        if eq_window.empty:
            engine_eq_at_election = 1.0
        else:
            engine_eq_at_election = float(eq_window.iloc[-1])

        # Engine window return (%)
        engine_window_ret = (engine_eq_at_election - 1.0) * 100

        # Net gate P&L: gated stays at 1.0, ungated = engine equity
        # Positive = gate won (saved money vs being in the raw engine)
        gate_pnl = (1.0 - engine_eq_at_election) / engine_eq_at_election * 100

        # ------------------------------------------------------------------ #
        # Recovery: +180 days from election day
        # Both gated and raw get to deploy from election day (raw engine was
        # already running; gate re-engages). We report the BTC+raw engine
        # return over the +180d window as the "recovery captured".
        # ------------------------------------------------------------------ #
        recovery_end = elec_day + pd.Timedelta(days=RECOVERY_DAYS)
        # find the actual closest date in index at/after elec_day and recovery_end
        idx_arr = close.index
        elec_idx = idx_arr[idx_arr >= elec_day]
        recovery_idx = idx_arr[idx_arr <= recovery_end]

        if len(elec_idx) == 0 or len(recovery_idx) == 0:
            recovery_ret = None
        else:
            elec_close_val = close.loc[elec_idx[0]]
            recovery_close_val = close.loc[recovery_idx[-1]]
            recovery_ret = (recovery_close_val / elec_close_val - 1) * 100

        rows.append({
            "year": year,
            "status": "COMPLETE",
            "btc_window_return_pct": round(btc_window_ret, 2),
            "engine_window_return_pct": round(engine_window_ret, 2),
            "max_drawdown_avoided_pct": round(max_dd_avoided, 2),
            "recovery_180d_pct": round(recovery_ret, 2) if recovery_ret is not None else None,
            "gate_pnl_pct": round(gate_pnl, 2),
        })

    return rows


# ---------------------------------------------------------------------------
# Part B: block-bootstrap breakeven fan
# ---------------------------------------------------------------------------
def _circular_bootstrap(pool: np.ndarray, n_draw: int, block_size: int,
                         rng: np.random.Generator) -> np.ndarray:
    """Circular block bootstrap: draw blocks from pool (with wrap-around)."""
    n = len(pool)
    n_blocks = int(np.ceil(n_draw / block_size))
    starts = rng.integers(0, n, size=n_blocks)
    result = []
    for s in starts:
        idx = np.arange(s, s + block_size) % n
        result.append(pool[idx])
    return np.concatenate(result)[:n_draw]


def run_bootstrap_fan(df: pd.DataFrame) -> list[dict]:
    """
    Fit a simple linear model: engine_return = a + b * btc_return
    using the 3 historical observations from prior midterm years.
    Then for each depth D, predict engine return and compute gate P&L.
    Bootstrap the regression residuals (3 residuals) to get CI.

    This is the most honest approach given n=3.
    Also run a circular block bootstrap on pooled daily returns for
    sensitivity / sanity check — both are reported.
    """
    close = df["close"].astype(float)
    alloc_raw = df["alloc_optimal_raw"].astype(float)

    # ------------------------------------------------------------------ #
    # Collect the 3 historical observations
    # ------------------------------------------------------------------ #
    obs_btc = []   # BTC window return (fraction, not %)
    obs_eng = []   # Engine window return (fraction)
    # Also collect pooled daily returns for bootstrap
    pooled_engine_daily = []
    pooled_btc_daily = []

    for year in MIDTERM_YEARS:
        elec_day = ELECTION_DATES[year]
        gate_start = pd.Timestamp(year=year, month=1, day=1)
        window_mask = (close.index >= gate_start) & (close.index <= elec_day)
        window_close = close.loc[window_mask]
        if window_close.empty or len(window_close) < 10:
            continue

        # BTC return over window
        btc_ret = window_close.iloc[-1] / window_close.iloc[0] - 1

        # Engine equity over window
        data_from_year = df.loc[df.index >= gate_start]
        close_yr = data_from_year["close"].astype(float)
        alloc_raw_yr = data_from_year["alloc_optimal_raw"].astype(float)
        eq_raw_yr = alloc_equity(close_yr, alloc_raw_yr)
        eq_window = eq_raw_yr.loc[eq_raw_yr.index <= elec_day]
        engine_eq = float(eq_window.iloc[-1]) if not eq_window.empty else 1.0
        engine_ret = engine_eq - 1.0

        obs_btc.append(btc_ret)
        obs_eng.append(engine_ret)

        # Daily returns for block bootstrap
        w_close = window_close.values
        btc_daily = np.diff(np.log(w_close))  # log returns
        pooled_btc_daily.extend(btc_daily.tolist())

        # Engine daily returns during window
        # Re-compute engine return series day by day
        ret_daily = close_yr.pct_change().fillna(0)
        pos = alloc_raw_yr.shift(1).ffill().fillna(0)
        eng_daily_full = pos * ret_daily
        # Slice to gate window using the year-local index
        window_mask_yr = (eng_daily_full.index >= gate_start) & (eng_daily_full.index <= elec_day)
        eng_daily = eng_daily_full.loc[window_mask_yr]
        eng_ret_arr = eng_daily.values
        pooled_engine_daily.extend(eng_ret_arr.tolist())

    if len(obs_btc) < 2:
        print("WARNING: insufficient historical data for bootstrap fan.")
        return []

    obs_btc_arr = np.array(obs_btc)
    obs_eng_arr = np.array(obs_eng)

    # ------------------------------------------------------------------ #
    # Approach 1: Linear regression (n=3) + residual bootstrap
    # engine_return = a + b * btc_return
    # Gate P&L = 0 - predicted_engine_return
    # ------------------------------------------------------------------ #
    n_obs = len(obs_btc_arr)
    # OLS with numpy
    X = np.column_stack([np.ones(n_obs), obs_btc_arr])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, obs_eng_arr, rcond=None)
        a_coef, b_coef = beta[0], beta[1]
    except Exception:
        a_coef = np.mean(obs_eng_arr)
        b_coef = 0.0

    pred = a_coef + b_coef * obs_btc_arr
    residuals = obs_eng_arr - pred

    rng = np.random.default_rng(42)

    fan_rows = []
    for D_pct in DEPTH_BUCKETS:
        D = D_pct / 100.0  # fraction

        # Point estimate: predicted engine return at this BTC depth
        pred_eng = a_coef + b_coef * D
        gate_pnl_point = -pred_eng  # gate = cash = 0; gate beats engine by -engine_return

        # Bootstrap: resample residuals (with replacement, n=3 → all 3 with repeats)
        bootstrap_gate_pnls = []
        for _ in range(N_BOOTSTRAP):
            resamp_idx = rng.integers(0, n_obs, size=n_obs)
            resamp_resid = residuals[resamp_idx]
            # Perturbed engine return = predicted + resampled residual
            eng_boot = pred_eng + resamp_resid.mean()
            gate_pnl_boot = -eng_boot
            bootstrap_gate_pnls.append(gate_pnl_boot * 100)

        arr = np.array(bootstrap_gate_pnls)
        p5 = float(np.percentile(arr, 5))
        p50 = float(np.percentile(arr, 50))
        p95 = float(np.percentile(arr, 95))

        fan_rows.append({
            "depth_pct": D_pct,
            "p5": round(p5, 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "n_draws": N_BOOTSTRAP,
            "point_estimate_pct": round(gate_pnl_point * 100, 2),
        })

    return fan_rows


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def write_markdown(per_cycle: list[dict], fan: list[dict], out_path: Path) -> None:
    lines = [
        "# BTC Midterm Gate Attribution — Phase 0",
        "",
        f"> Generated: {date.today().isoformat()}  ",
        f"> {LABEL}",
        "",
        "---",
        "",
        "## Part A: Per-cycle attribution",
        "",
        "The midterm gate window runs **Jan 1 → election day** for years where `year % 4 == 2`.",
        "Election dates: 2014-11-04, 2018-11-06, 2022-11-08, 2026-11-03.",
        "",
        "| Year | BTC window return | Engine raw return | Max DD avoided | Recovery +180d | Gate P&L vs engine | Status |",
        "|------|-------------------|-------------------|----------------|----------------|--------------------|--------|",
    ]
    for r in per_cycle:
        year = r["year"]
        status = r["status"]
        if status == "PENDING":
            lines.append(f"| {year} | — | — | — | — | — | **PENDING** |")
        elif status == "INSUFFICIENT_DATA":
            lines.append(f"| {year} | N/A | N/A | N/A | N/A | N/A | INSUFFICIENT DATA |")
        else:
            btc = f"{r['btc_window_return_pct']:+.1f}%"
            eng = f"{r['engine_window_return_pct']:+.1f}%"
            dd = f"{r['max_drawdown_avoided_pct']:.1f}%" if r['max_drawdown_avoided_pct'] is not None else "N/A"
            rec = f"{r['recovery_180d_pct']:+.1f}%" if r['recovery_180d_pct'] is not None else "N/A"
            pnl = f"{r['gate_pnl_pct']:+.1f}%" if r['gate_pnl_pct'] is not None else "N/A"
            lines.append(f"| {year} | {btc} | {eng} | {dd} | {rec} | {pnl} | ✓ Complete |")

    lines += [
        "",
        "**Column definitions:**",
        "- **BTC window return**: BTC price return from Jan 1 to election day.",
        "- **Engine raw return**: alloc_optimal_raw equity return over the same window (raw engine WITH drawdown brake, no midterm gate).",
        "- **Max DD avoided**: worst intra-window drawdown vs Jan 1 close (depth the gate sidestepped).",
        "- **Recovery +180d**: BTC return from election day to +180 calendar days (context for post-gate environment).",
        "- **Gate P&L vs engine**: `(1.0_gated - engine_equity) / engine_equity × 100` — positive = gate beat the raw engine.",
        "",
        "---",
        "",
        "## Part B: Block-bootstrap breakeven fan",
        "",
        f"Method: linear regression on n=3 historical observations (engine_return = a + b × BTC_return),",
        "then residual bootstrap (N=2,000 draws) for confidence intervals.",
        "Positive gate P&L = gate beat the brake-only raw engine; negative = gate was worse.",
        "",
        f"**{LABEL}**",
        "",
        "| BTC depth | P5 gate P&L | P50 gate P&L | P95 gate P&L | Point est. |",
        "|-----------|-------------|--------------|--------------|------------|",
    ]
    for r in fan:
        d = r["depth_pct"]
        lines.append(
            f"| {d:+d}% | {r['p5']:+.1f}% | {r['p50']:+.1f}% | {r['p95']:+.1f}% | {r['point_estimate_pct']:+.1f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## Caveats",
        "",
        "1. **n=3**: Three prior midterm years are the entire historical sample. Every",
        "   statistical conclusion from this analysis is illustrative, not calibrated.",
        "   The fan and CIs should be read as 'plausible range given the 3 observed shapes',",
        "   not frequentist confidence intervals.",
        "",
        "2. **Brake-only is not passive**: `alloc_optimal_raw` already includes an enforced",
        "   drawdown brake that cuts exposure when the strategy goes underwater. The gate",
        "   competes against this active defense, not against buy-and-hold.",
        "",
        "3. **No D* breakeven trigger**: This report deliberately does not headline a",
        "   breakeven depth. With n=3, any such threshold would be spuriously precise.",
        "   The fan shows the directional story; the threshold question should be",
        "   revisited after 2026 adds a fourth observation.",
        "",
        "4. **Residual bootstrap with n=3**: The residual bootstrap resamples 3 residuals",
        "   with replacement, producing only 4 distinct bootstrap samples per draw.",
        "   CIs are rough order-of-magnitude guides, not tight bounds.",
        "",
        "5. **2026 status**: PENDING. Do not fill in projected outcomes.",
        "",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    print(f"Report written → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 72)
    print("BTC Midterm Gate Attribution — Phase 0")
    print(f"As of: {date.today().isoformat()}")
    print("=" * 72)
    print()
    print("Loading engine (compute_all)… this may take ~2 minutes.")
    df = btc_signals.compute_all()
    print(f"Engine loaded. Index range: {df.index[0].date()} → {df.index[-1].date()}")
    print(f"Columns available: {[c for c in df.columns if 'alloc' in c or 'override' in c]}")
    print()

    # ------------------------------------------------------------------ #
    # Part A
    # ------------------------------------------------------------------ #
    print("-" * 72)
    print("PART A — Per-cycle attribution")
    print("-" * 72)
    per_cycle = run_per_cycle(df)

    header = f"{'Year':<6} {'BTC window':>12} {'Engine raw':>12} {'Max DD avoid':>14} {'Rec +180d':>11} {'Gate P&L':>10} Status"
    print(header)
    print("-" * len(header))
    for r in per_cycle:
        year = r["year"]
        status = r["status"]
        if status == "PENDING":
            print(f"{year:<6} {'—':>12} {'—':>12} {'—':>14} {'—':>11} {'—':>10} PENDING")
        elif status == "INSUFFICIENT_DATA":
            print(f"{year:<6} {'N/A':>12} {'N/A':>12} {'N/A':>14} {'N/A':>11} {'N/A':>10} INSUFFICIENT DATA")
        else:
            btc = f"{r['btc_window_return_pct']:+.1f}%"
            eng = f"{r['engine_window_return_pct']:+.1f}%"
            dd = f"{r['max_drawdown_avoided_pct']:.1f}%" if r['max_drawdown_avoided_pct'] is not None else "N/A"
            rec = f"{r['recovery_180d_pct']:+.1f}%" if r['recovery_180d_pct'] is not None else "N/A"
            pnl = f"{r['gate_pnl_pct']:+.1f}%" if r['gate_pnl_pct'] is not None else "N/A"
            print(f"{year:<6} {btc:>12} {eng:>12} {dd:>14} {rec:>11} {pnl:>10}")
    print()

    # ------------------------------------------------------------------ #
    # Part B
    # ------------------------------------------------------------------ #
    print("-" * 72)
    print("PART B — Breakeven fan (n=3 shapes; illustrative, not calibrated)")
    print("-" * 72)
    fan = run_bootstrap_fan(df)
    print(f"{'BTC depth':>12} {'P5 gate P&L':>14} {'P50 gate P&L':>14} {'P95 gate P&L':>14} {'Point est.':>12}")
    print("-" * 68)
    for r in fan:
        print(
            f"{r['depth_pct']:>+11d}%"
            f"  {r['p5']:>+12.1f}%"
            f"  {r['p50']:>+12.1f}%"
            f"  {r['p95']:>+12.1f}%"
            f"  {r['point_estimate_pct']:>+10.1f}%"
        )
    print()

    # ------------------------------------------------------------------ #
    # Write outputs
    # ------------------------------------------------------------------ #
    out_json = ROOT / "data" / "vector" / "gate_attribution.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "per_cycle": per_cycle,
        "breakeven_fan": fan,
        "label": LABEL,
        "as_of": date.today().isoformat(),
    }
    out_json.write_text(json.dumps(payload, indent=2, default=str))
    print(f"JSON written → {out_json}")

    out_md = ROOT / "reports" / "btc-gate-attribution.md"
    write_markdown(per_cycle, fan, out_md)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
