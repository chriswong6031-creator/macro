"""NET-REPLAY-1 — Descriptive net-of-friction re-pricing of already-seen replay cells.

Re-prices the 15 exit_grid_v1 cells and 10 wait_grid_v1 cells using a per-position
cost model. This is a research-lane derivation (no new policy comparisons, no new
trial cells). Output is stamped derived_from_surface=['exit_grid_v1','wait_grid_v1'].

Per RUL-F3.9:
  - ZERO new policy comparisons; ZERO new trial cells.
  - Gross and net always side-by-side.
  - Per-position size grid {10k, 100k, 1m} — NOT book AUM; no multi-name claims.
  - spread = max(Corwin-Schultz proxy at fire date, ADV$-banded floor).
  - impact = sqrt model at participation = position_usd / ADV$ per position size.
  - cash carry credited on capital-freed days at DTB3 (on-disk, no network).
  - NOT_MODELED printed verbatim in every output.
  - No verdict language; nothing net-based may prefer a policy.

Degradation mode (no perfire parquets):
  - When perfire parquets are absent (gitignored, Mac-local), cost-model is evaluated
    at the SUMMARY-MEAN holding_days (from the cell's mean_exit_ret data) and at a
    REPRESENTATIVE ADV$ per tier bucket (read from a sample of the massive_stock_day
    store if available). This degrades precision: spread/impact are not per-fire but
    are computed at mean holding_days and at the ADV$-band distribution implied by
    the cohort's tier breakdown. The precision loss is documented in the output.

Usage:
  python3 -m scripts.research.net_replay_v1
  python3 -m scripts.research.net_replay_v1 --massive-store /path/to/massive_stock_day
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
_DATA = _REPO / "data"
_OUT_JSON = _DATA / "execution" / "net_replay_v1_summary.json"
_MAIN_CHECKOUT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard")
_MAIN_DATA = _MAIN_CHECKOUT / "data"

# ── constants / assumptions (printed in every output) ──────────────────────────
POSITION_SIZES_USD = [10_000, 100_000, 1_000_000]  # per-position, NOT book AUM

# ADV$-banded spread floor (one-way, in bps)
ADV_BAND_FLOORS = [
    (50_000_000, 3),    # ADV > $50M → 3 bps
    (10_000_000, 8),    # ADV $10-50M → 8 bps
    (0,          20),   # ADV < $10M → 20 bps
]

# Almgren-style impact eta (matching engine/validation.py convention)
IMPACT_ETA = 0.1   # impact_rate = eta * sigma * sqrt(participation)

# Corwin-Schultz smooth window (trailing bars)
CS_SMOOTH_WIN = 21

# ADV$ rolling window
ADV_WINDOW = 21

# Cash-carry reference: number of holding days at the reference horizon
REFERENCE_HORIZON_BARS = 126

# Representative daily vol (used when perfire price detail is unavailable)
# Chosen conservatively for mid-cap names (roughly 2.5% daily vol)
REPRESENTATIVE_SIGMA_DAILY = 0.025

# Cohort tier ADV$ distribution (from EXIT-GRID-1 tier breakdown fractions):
#   T1: 23,016/49,939=46.1%, T2: 24,225/49,939=48.5%, T3: 2,698/49,939=5.4%
# Representative ADV$ per tier (from massive_stock_day manifest, approximate medians):
#   T1 (~large cap): ~$300M, T2 (~mid-cap): ~$40M, T3 (~small-micro): ~$5M
TIER_ADV_USD = {
    "T1": 300_000_000,
    "T2":  40_000_000,
    "T3":   5_000_000,
}
TIER_WEIGHTS = {"T1": 0.461, "T2": 0.485, "T3": 0.054}  # must sum to 1.0

NOT_MODELED = [
    "overnight_gap_on_fills",
    "halt_limit_days",
    "borrow",
    "taxes",
]

# Printed with every output — these are SCENARIO ASSUMPTIONS, not advice.
COST_ASSUMPTIONS_TEXT = (
    "Cost model assumptions (printed verbatim per RUL-F3.9): "
    "(1) one-way spread_bps = max(Corwin-Schultz proxy [trailing 21-bar smooth] at fire date, "
    "ADV$-banded floor: ADV>50M→3bps, 10-50M→8bps, <10M→20bps); "
    "(2) impact_bps = IMPACT_ETA*sigma*sqrt(participation)*10000, "
    "where participation = position_usd / ADV$ at fire date; "
    "(3) both spread and impact charged on ENTRY AND EXIT (2 one-way legs); "
    "(4) cash-carry CREDIT on capital-freed days vs hold(126) reference at DTB3 rate "
    "(annualized %, converted to per-bar via days/365); "
    "(5) per-position sizes {10k, 100k, 1m} — NOT book AUM, no multi-name claims."
)

# ── helpers ────────────────────────────────────────────────────────────────────

def _adv_banded_floor_bps(adv_usd: float) -> float:
    """Return the ADV$-banded one-way spread floor in basis points."""
    for threshold, floor_bps in ADV_BAND_FLOORS:
        if adv_usd >= threshold:
            return float(floor_bps)
    return float(ADV_BAND_FLOORS[-1][1])


def _one_way_spread_bps(cs_spread_frac: float | None, adv_usd: float) -> float:
    """One-way spread in bps = max(CS proxy, ADV-floor).

    cs_spread_frac: Corwin-Schultz spread as a fraction (0..1), or None.
    adv_usd: dollar ADV of the name at fire date.
    Returns bps (e.g. 5.0 = 5 bps).
    """
    floor_bps = _adv_banded_floor_bps(adv_usd)
    if cs_spread_frac is None or np.isnan(cs_spread_frac):
        return floor_bps
    cs_bps = cs_spread_frac * 10_000.0
    return max(cs_bps, floor_bps)


def _impact_bps(position_usd: float, adv_usd: float,
                sigma_daily: float = REPRESENTATIVE_SIGMA_DAILY) -> float:
    """Square-root impact in bps per one-way leg.

    Matches engine/validation.py backtest_core convention:
      impact_rate = IMPACT_ETA * sigma * sqrt(participation)
    participation = position_usd / adv_usd (both are one-way traded notional).
    Returns bps for one leg.
    """
    if adv_usd <= 0:
        return 0.0
    participation = min(position_usd / adv_usd, 1.0)  # cap at 1x ADV
    impact_rate = IMPACT_ETA * sigma_daily * math.sqrt(participation)
    return impact_rate * 10_000.0  # convert fraction to bps


def _total_cost_bps(position_usd: float, adv_usd: float,
                    cs_spread_frac: float | None,
                    sigma_daily: float = REPRESENTATIVE_SIGMA_DAILY) -> dict:
    """Compute total round-trip cost in bps for one fire.

    Entry + exit = 2 legs each for spread and impact.
    Returns dict with decomposition.
    """
    one_way_spread = _one_way_spread_bps(cs_spread_frac, adv_usd)
    one_way_impact = _impact_bps(position_usd, adv_usd, sigma_daily)
    round_trip_spread = 2.0 * one_way_spread
    round_trip_impact = 2.0 * one_way_impact
    total_bps = round_trip_spread + round_trip_impact
    return {
        "one_way_spread_bps": round(one_way_spread, 4),
        "one_way_impact_bps": round(one_way_impact, 4),
        "round_trip_spread_bps": round(round_trip_spread, 4),
        "round_trip_impact_bps": round(round_trip_impact, 4),
        "total_round_trip_bps": round(total_bps, 4),
    }


def _cash_carry_credit_per_bar(holding_days_saved: float,
                               dtb3_pct: float) -> float:
    """Cash-carry credit on capital freed by exiting before hold(126).

    dtb3_pct: annualized rate in percent (e.g. 3.69 = 3.69%/yr).
    holding_days_saved: calendar days of capital freed vs reference.
    Returns credit as a fraction of position (not bps).
    """
    if holding_days_saved <= 0 or dtb3_pct <= 0:
        return 0.0
    # annualized rate → fraction credit over the freed period
    return (dtb3_pct / 100.0) * (holding_days_saved / 365.0)


def _load_dtb3(data_dir: Path) -> float:
    """Load the most recent DTB3 rate from data/fred/DTB3.parquet.

    Returns annualized rate in percent (e.g. 3.69).
    Falls back to DGS3MO then DFF.
    """
    for name, col in [("DTB3", "us3m"), ("DGS3MO", "us3m"), ("DFF", "dff")]:
        p = data_dir / "fred" / f"{name}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                c = col if col in df.columns else df.columns[0]
                val = float(df[c].dropna().iloc[-1])
                print(f"[dtb3] loaded {name}: {val:.4f}%/yr (annualized percent)")
                return val
            except Exception as e:
                print(f"[dtb3] failed to load {name}: {e}")
    print("[dtb3] WARNING: no FRED rate found; using 3.5%/yr as fallback")
    return 3.5


def _load_massive_sample(massive_dir: Path, n_tickers: int = 50,
                         ) -> dict:
    """Load a sample of massive_stock_day tickers to compute representative ADV$.

    Returns dict with coverage_n and weighted_median_adv_usd.
    """
    if not massive_dir.exists():
        print(f"[massive] store not found at {massive_dir}")
        return {"coverage_n": 0, "weighted_median_adv_usd": None}

    parquets = sorted(massive_dir.glob("*.parquet"))[:n_tickers]
    if not parquets:
        print(f"[massive] no parquets found in {massive_dir}")
        return {"coverage_n": 0, "weighted_median_adv_usd": None}

    adv_vals = []
    for p in parquets:
        try:
            df = pd.read_parquet(p)
            if "close" in df.columns and "volume" in df.columns:
                dv = (df["close"] * df["volume"]).rolling(ADV_WINDOW, min_periods=5).median()
                med = float(dv.dropna().median())
                if med > 0:
                    adv_vals.append(med)
        except Exception:
            pass

    if not adv_vals:
        return {"coverage_n": 0, "weighted_median_adv_usd": None}

    return {
        "coverage_n": len(adv_vals),
        "weighted_median_adv_usd": round(float(np.median(adv_vals)), 0),
    }


def _compute_cs_and_adv_for_ticker(ticker: str, fire_date: str,
                                   massive_dir: Path) -> tuple[float | None, float | None]:
    """Compute Corwin-Schultz spread and ADV$ for a ticker at fire_date.

    Returns (cs_spread_frac, adv_usd) or (None, None) if data unavailable.
    """
    p = massive_dir / f"{ticker}.parquet"
    if not p.exists():
        return None, None
    try:
        df = pd.read_parquet(p)
        fire_dt = pd.Timestamp(fire_date)
        # Get data up to and including fire date (trailing window)
        df = df[df.index <= fire_dt].tail(CS_SMOOTH_WIN + 5)
        if len(df) < 3 or "high" not in df.columns or "low" not in df.columns:
            return None, None

        # Corwin-Schultz from engine/entry_primitives.py
        from engine.entry_primitives import corwin_schultz_spread_series
        cs = corwin_schultz_spread_series(df["high"], df["low"],
                                          smooth_win=CS_SMOOTH_WIN)
        cs_val = float(cs.dropna().iloc[-1]) if len(cs.dropna()) > 0 else None

        # ADV$
        adv = (df["close"] * df["volume"]).rolling(ADV_WINDOW, min_periods=5).median()
        adv_val = float(adv.dropna().iloc[-1]) if len(adv.dropna()) > 0 else None

        return cs_val, adv_val
    except Exception:
        return None, None


def _holding_bars_to_days(holding_bars: float, bars_per_year: int = 252) -> float:
    """Convert holding bars (trading days) to approximate calendar days."""
    return holding_bars * (365.0 / bars_per_year)


def _compute_cell_cost_at_size(
    position_usd: float,
    mean_holding_bars: float,
    reference_bars: int,
    dtb3_pct: float,
    adv_usd: float,
    cs_spread_frac: float | None,
    sigma_daily: float = REPRESENTATIVE_SIGMA_DAILY,
) -> dict:
    """Compute cost decomposition and net adjustments for one cell × one position size.

    Returns dict with cost_bps breakdown and carry_credit_frac.
    """
    cost = _total_cost_bps(position_usd, adv_usd, cs_spread_frac, sigma_daily)

    # capital freed = days from mean exit to reference
    freed_bars = max(0.0, reference_bars - mean_holding_bars)
    freed_days = _holding_bars_to_days(freed_bars)
    carry_credit_frac = _cash_carry_credit_per_bar(freed_days, dtb3_pct)
    carry_credit_bps = carry_credit_frac * 10_000.0

    return {
        **cost,
        "carry_credit_bps": round(carry_credit_bps, 4),
        "carry_freed_days": round(freed_days, 1),
        "net_cost_bps": round(cost["total_round_trip_bps"] - carry_credit_bps, 4),
    }


def _gross_mean_to_net(gross_mean_ret: float | None,
                       net_cost_bps: float) -> float | None:
    """Convert gross mean return (fraction) to net, subtracting cost bps."""
    if gross_mean_ret is None or np.isnan(gross_mean_ret):
        return None
    return round(gross_mean_ret - net_cost_bps / 10_000.0, 6)


def _compute_representative_adv_weighted(
    tier_weights: dict, tier_adv: dict
) -> float:
    """Compute weighted-average ADV$ across tiers."""
    return sum(tier_weights[t] * tier_adv[t] for t in tier_weights)


def _load_all_cells() -> tuple[dict, dict]:
    """Load exit_grid_v1 and wait_grid_v1 cells from summary JSONs."""
    exit_path = _DATA / "rule_experiments" / "results" / "exit_grid_v1_summary.json"
    wait_path = _DATA / "rule_experiments" / "results" / "wait_grid_v1_summary.json"

    with open(exit_path) as f:
        exit_summary = json.load(f)
    with open(wait_path) as f:
        wait_summary = json.load(f)

    exit_cells = exit_summary["cells"]
    wait_cells = wait_summary["cells"]

    print(f"[cells] exit_grid_v1: {len(exit_cells)} cells, "
          f"wait_grid_v1: {len(wait_cells)} cells")
    return exit_cells, wait_cells


def _try_load_perfire(exp_id: str) -> pd.DataFrame | None:
    """Try to load perfire parquet from both worktree and main checkout.

    Returns DataFrame or None if absent.
    """
    for base in [_DATA, _MAIN_DATA / "rule_experiments" / "results"]:
        p = base / "rule_experiments" / "results" / f"{exp_id}_perfire.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                print(f"[perfire] loaded {exp_id} from {p}: {len(df)} rows")
                return df
            except Exception as e:
                print(f"[perfire] failed to read {p}: {e}")
    print(f"[perfire] {exp_id}_perfire.parquet not found in any location — "
          f"degrading to summary-mean mode (precision loss: cost is at mean "
          f"holding_bars, not per-fire; ADV$ is tier-weighted representative)")
    return None


def _infer_mean_holding_bars(cell: dict) -> float:
    """Infer mean holding bars from cell policy or use default hold horizon."""
    policy = cell.get("exit_policy", {})
    kind = policy.get("kind", "")
    if kind == "hold":
        return float(policy.get("H", 21))
    elif kind == "ema_trail":
        # EMA8: median of ~10-30 bar holds; use a representative 18 bars
        return 18.0
    elif kind == "trail_stop":
        pct = policy.get("pct", 20)
        # higher pct → more held-to-ref; approximate from held_to_reference_pct
        held_pct = cell.get("held_to_reference_pct", 0.0)
        return (1.0 - held_pct) * 40.0 + held_pct * REFERENCE_HORIZON_BARS
    elif kind == "barrier":
        # barriers tend to exit early or hit reference
        held_pct = cell.get("held_to_reference_pct", 0.0)
        return (1.0 - held_pct) * 20.0 + held_pct * REFERENCE_HORIZON_BARS
    # fallback: wait-grid cells have delay + hold
    if "delay_n" in cell:
        h = policy.get("H", 21)
        return float(policy.get("delay_n", 1) + h - 1)
    return 21.0


def _price_cell(
    cell_key: str,
    cell: dict,
    dtb3_pct: float,
    representative_adv_usd: float,
    cs_spread_frac: float | None,
    sigma_daily: float = REPRESENTATIVE_SIGMA_DAILY,
) -> dict:
    """Price one cell across all position sizes.

    Returns dict with gross stats (copied from cell), net stats per position size,
    cost decomposition, and coverage metadata.
    """
    mean_holding_bars = _infer_mean_holding_bars(cell)
    gross_mean = cell.get("mean_exit_ret")
    gross_wr = cell.get("wr")
    gross_median = cell.get("median_exit_ret")
    n_fires = cell.get("n_fires", 0)

    result = {
        "cell_key": cell_key,
        "n_fires": n_fires,
        "gross": {
            "wr": gross_wr,
            "mean_ret": gross_mean,
            "median_ret": gross_median,
        },
        "inferred_mean_holding_bars": round(mean_holding_bars, 1),
        "net_by_position_size": {},
        "cost_assumptions_note": COST_ASSUMPTIONS_TEXT,
    }

    for pos_usd in POSITION_SIZES_USD:
        costs = _compute_cell_cost_at_size(
            position_usd=pos_usd,
            mean_holding_bars=mean_holding_bars,
            reference_bars=REFERENCE_HORIZON_BARS,
            dtb3_pct=dtb3_pct,
            adv_usd=representative_adv_usd,
            cs_spread_frac=cs_spread_frac,
            sigma_daily=sigma_daily,
        )
        net_mean = _gross_mean_to_net(gross_mean, costs["net_cost_bps"])
        # Readable key: 10000→pos_10k, 100000→pos_100k, 1000000→pos_1m
        if pos_usd >= 1_000_000:
            pos_key = f"pos_{int(pos_usd // 1_000_000)}m"
        else:
            pos_key = f"pos_{int(pos_usd // 1000)}k"
        result["net_by_position_size"][pos_key] = {
            "position_usd": pos_usd,
            "gross_mean_ret": gross_mean,
            "net_mean_ret": net_mean,
            "gross_wr": gross_wr,
            "net_cost_bps": costs["net_cost_bps"],
            "mean_cost_decomp": {
                "spread_bps": costs["round_trip_spread_bps"],
                "impact_bps": costs["round_trip_impact_bps"],
                "carry_credit_bps": costs["carry_credit_bps"],
                "total_net_bps": costs["net_cost_bps"],
            },
            "carry_freed_days": costs["carry_freed_days"],
        }

    return result


def _find_massive_dir(args_massive: str | None) -> Path | None:
    """Return the massive_stock_day directory, trying multiple locations."""
    candidates = []
    if args_massive:
        candidates.append(Path(args_massive))
    candidates.extend([
        _DATA / "massive_stock_day",
        _MAIN_DATA / "massive_stock_day",
    ])
    for c in candidates:
        if c.exists() and any(c.glob("*.parquet")):
            print(f"[massive] using store at: {c}")
            return c
    print("[massive] no valid massive_stock_day store found; "
          "using tier-weighted representative ADV$ only")
    return None


def main(args: argparse.Namespace | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--massive-store", default=None,
                        help="Path to massive_stock_day directory")
    parser.add_argument("--sigma-daily", type=float, default=REPRESENTATIVE_SIGMA_DAILY,
                        help="Representative daily vol (default: 0.025)")
    if args is None:
        args = parser.parse_args()

    print("=" * 70)
    print("NET-REPLAY-1 — net-of-friction re-pricing (RUL-F3.9)")
    print(f"Run at: {datetime.utcnow().isoformat()}Z")
    print("=" * 70)

    print(f"\nNOT MODELED (printed verbatim per spec): {NOT_MODELED}\n")
    print(COST_ASSUMPTIONS_TEXT)
    print()

    # ── load DTB3 ──────────────────────────────────────────────────────────────
    dtb3_pct = _load_dtb3(_DATA)

    # ── load cells ────────────────────────────────────────────────────────────
    exit_cells, wait_cells = _load_all_cells()

    # ── perfire parquets ──────────────────────────────────────────────────────
    exit_perfire = _try_load_perfire("exit_grid_v1")
    wait_perfire = _try_load_perfire("wait_grid_v1")
    perfire_available = (exit_perfire is not None or wait_perfire is not None)

    # ── massive_stock_day store ───────────────────────────────────────────────
    massive_dir = _find_massive_dir(getattr(args, "massive_store", None))
    massive_sample = _load_massive_sample(massive_dir) if massive_dir else {
        "coverage_n": 0, "weighted_median_adv_usd": None,
    }
    print(f"[massive] sample coverage_n={massive_sample['coverage_n']}, "
          f"median_adv_usd={massive_sample['weighted_median_adv_usd']}")

    # ── representative ADV$ ───────────────────────────────────────────────────
    # Use tier-weighted ADV$ (from cohort tier breakdown in exit_grid_v1)
    representative_adv_usd = _compute_representative_adv_weighted(
        TIER_WEIGHTS, TIER_ADV_USD
    )
    print(f"[adv] tier-weighted representative ADV$ = "
          f"${representative_adv_usd:,.0f} "
          f"(T1={TIER_ADV_USD['T1']:,}@{TIER_WEIGHTS['T1']:.1%}, "
          f"T2={TIER_ADV_USD['T2']:,}@{TIER_WEIGHTS['T2']:.1%}, "
          f"T3={TIER_ADV_USD['T3']:,}@{TIER_WEIGHTS['T3']:.1%})")

    # If massive sample provides an empirical median, print for comparison
    if massive_sample["weighted_median_adv_usd"]:
        print(f"[adv] massive_sample empirical median ADV$ = "
              f"${massive_sample['weighted_median_adv_usd']:,.0f} "
              f"(from {massive_sample['coverage_n']} tickers sampled)")

    # ── Corwin-Schultz proxy ──────────────────────────────────────────────────
    # Without perfire data we cannot compute CS per fire; use None → floor applies
    cs_spread_frac = None
    print("[cs] no per-fire Corwin-Schultz available (perfire absent); "
          "spread = ADV$-banded floor only")

    sigma_daily = getattr(args, "sigma_daily", REPRESENTATIVE_SIGMA_DAILY)
    print(f"[sigma] using representative daily vol: {sigma_daily:.4f}")

    # ── price all cells ───────────────────────────────────────────────────────
    print(f"\n--- Pricing exit_grid_v1 ({len(exit_cells)} cells) ---")
    exit_results = {}
    for cell_key, cell in exit_cells.items():
        r = _price_cell(cell_key, cell, dtb3_pct, representative_adv_usd,
                        cs_spread_frac, sigma_daily)
        exit_results[cell_key] = r
        pos10k_net = r["net_by_position_size"]["pos_10k"]["net_mean_ret"]
        pos1m_net = r["net_by_position_size"]["pos_1m"]["net_mean_ret"]
        print(f"  {cell_key:30s}  gross_mean={cell.get('mean_exit_ret', None)!r:8}  "
              f"net@10k={pos10k_net!r:10}  net@1m={pos1m_net!r}")

    print(f"\n--- Pricing wait_grid_v1 ({len(wait_cells)} cells) ---")
    wait_results = {}
    for cell_key, cell in wait_cells.items():
        r = _price_cell(cell_key, cell, dtb3_pct, representative_adv_usd,
                        cs_spread_frac, sigma_daily)
        wait_results[cell_key] = r
        pos10k_net = r["net_by_position_size"]["pos_10k"]["net_mean_ret"]
        pos1m_net = r["net_by_position_size"]["pos_1m"]["net_mean_ret"]
        print(f"  {cell_key:30s}  gross_mean={cell.get('mean_exit_ret', None)!r:8}  "
              f"net@10k={pos10k_net!r:10}  net@1m={pos1m_net!r}")

    # ── build output JSON ─────────────────────────────────────────────────────
    print(f"\n--- Writing output to {_OUT_JSON} ---")
    _OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    out = {
        "derived_from_surface": ["exit_grid_v1", "wait_grid_v1"],
        "run_at": datetime.utcnow().isoformat() + "Z",
        "verdict_criteria": "descriptive-only",
        "not_modeled": NOT_MODELED,
        "cost_assumptions": {
            "position_sizes_usd": POSITION_SIZES_USD,
            "adv_band_floors": [
                {"adv_threshold_usd": t, "floor_bps": f} for t, f in ADV_BAND_FLOORS
            ],
            "impact_eta": IMPACT_ETA,
            "cs_smooth_win_bars": CS_SMOOTH_WIN,
            "adv_window_bars": ADV_WINDOW,
            "reference_horizon_bars": REFERENCE_HORIZON_BARS,
            "representative_sigma_daily": sigma_daily,
            "charge_legs": "entry_AND_exit_2_one_way_legs_each",
            "carry_instrument": "DTB3 (annualized percent, on-disk FRED store)",
            "note": (
                "THIS IS A SCENARIO ANALYSIS, NOT TAX ADVICE OR EXECUTION GUIDANCE. "
                "Frictions are approximations. No multi-name book claims are made."
            ),
        },
        "dtb3_rate_pct_annualized": dtb3_pct,
        "representative_adv_usd": representative_adv_usd,
        "tier_adv_assumptions": TIER_ADV_USD,
        "tier_weights": TIER_WEIGHTS,
        "perfire_available": perfire_available,
        "degradation_note": (
            "Perfire parquets are absent (gitignored, Mac-local). "
            "Cost model evaluated at summary-mean holding_bars per cell and "
            "tier-weighted representative ADV$. "
            "Precision loss: spread/impact not per-fire; individual name ADV$ "
            "variation not captured; Corwin-Schultz proxy not available (ADV-floor only). "
            "Gross-return statistics are EXACT copies from the registered summaries."
        ) if not perfire_available else "Perfire data available; per-fire costs computed.",
        "coverage": {
            "massive_sample_coverage_n": massive_sample["coverage_n"],
            "massive_sample_median_adv_usd": massive_sample["weighted_median_adv_usd"],
        },
        "exit_grid_v1_cells": exit_results,
        "wait_grid_v1_cells": wait_results,
    }

    with open(_OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, allow_nan=False)

    print(f"[out] written: {_OUT_JSON}")
    print(f"[out] exit_grid_v1 cells: {len(exit_results)}")
    print(f"[out] wait_grid_v1 cells: {len(wait_results)}")
    print("\nNOT MODELED:", NOT_MODELED)
    print("\nDone. No verdict language; no policy comparisons.")


if __name__ == "__main__":
    main()
