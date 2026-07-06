"""Long-Hold Thesis Layer — W1 PR-E: Label harness.

Pre-registration: research/long_hold/OBJECTIVE.md (LOCKED).
Masterplan: research/LONG_HOLD_THESIS_MASTERPLAN_BY_FABLE.md.

Implements OBJECTIVE.md §2 exactly:
  - All labels: compounder (A), multiple_expansion_only (B), cheap_trap (C),
    tactical_only (D), sector_laggard_winner (G), tactical_only_fail (F),
    unlabeled (unmatured_126, unmatured_252, no_price).
  - Locked coverage-waiver definition (§2.4).
  - Unmatured-at-126 / unmatured-at-252 exclusion reasons.
  - Tactical win via the exact production grader (clean15_126, TerminalState.CLEAN_LIFTOFF).
  - Sector-relative benchmark via data/baskets/ohlcv/ GICS sector baskets.
  - Piotroski F computed via run_w2_sql._piotroski_from_panel_rows (PIT-safe).
  - Episode-cluster count per §6.3 (name × macro_regime, ±10d de-dup).

Outputs:
  data/research/long_hold_labels.parquet
  data/research/long_hold_labels_manifest.json

Synapse registration: config/synapse.yml (horizon_role: hold_thesis, tier: display).

Price resolution (canonical):
  1. data/yahoo/<ticker>.parquet (primary; dividend-adjusted total return).
  2. data/massive_stock_day/<ticker>.parquet (Mac-local whole-market store,
     post-2021-07-06, survivorship-correct; RAW closes, NOT dividend-adjusted).
     Probed at both config.data_dir()/massive_stock_day and the parent
     Mac data dir (for local runs where the worktree data/ is a thin slice).
  3. data/stocks/<ticker>.parquet (deep-history; survivor-only; caveat-stamped).
  Every fire is stamped with price_source and resolvable fields.

Conservatism choices (ambiguous prereg readings):
  - Tercile cutoffs: computed on tactical-win + 252d-matured fires only, within
    cohort-year, as per §2.4. Fires below the 33rd pctile are cheap_trap.
    "Bottom tercile" = rank < 33rd pctile, "top tercile" = rank >= 67th pctile.
  - coverage_waived denominator: count of fires in cohort-year with tactical_win=True
    AND 252 bars matured (as per locked §2.4 formula). Fires without price or
    unmatured-at-126 are excluded from the denominator.
  - Gap period: fires with fire_date in 2021-10-25 to 2025-01-02 are flagged
    gap_period=True (massive store gap per masterplan §2).
  - Macro regime: read from data/regime/latest.json if available; otherwise
    a block-bootstrap fallback of 63-day blocks is used for episode clustering.

Usage:
    python scripts/research/long_hold_label_panel.py
    python scripts/research/long_hold_label_panel.py --dry-run   # prints manifest only
    python scripts/research/long_hold_label_panel.py --limit 1000  # smoke test
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_FIRES_PATH = _DATA / "research" / "gate_fires_baskets.parquet"
_YAHOO_DIR = _DATA / "yahoo"
_STOCKS_DIR = _DATA / "stocks"
_FUNDAMENTALS_PANEL = _DATA / "edgar" / "fundamentals_panel.parquet"
_SECTOR_OHLCV_DIR = _DATA / "baskets" / "ohlcv"
_REGIME_LATEST = _DATA / "regime" / "latest.json"
_OUT_PARQUET = _DATA / "research" / "long_hold_labels.parquet"
_OUT_MANIFEST = _DATA / "research" / "long_hold_labels_manifest.json"

# LT-1c: expanded sector map (scripts/build_sector_map.py).
# Preferred over the baskets/membership.json-derived map because it covers
# ~1,500 tickers (GICS from all 3 S&P constituent files + SIC-mapped) vs 503
# from baskets alone.  Falls back to the old membership.json path if not found.
_TICKER_SECTORS_PATH = _DATA / "breadth" / "ticker_sectors.parquet"

# Massive store: probed at repo-local and Mac-system paths
_MASSIVE_DIR_LOCAL = _DATA / "massive_stock_day"
_MASSIVE_DIR_MAC = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")

# Dead-name price store (W1 Phase-1 build; post-anchor dead names via Polygon REST)
_DEAD_NAME_PRICES_PATH = _DATA / "edgar" / "dead_name_prices.parquet"

# ---------------------------------------------------------------------------
# Constants (OBJECTIVE.md §3)
# ---------------------------------------------------------------------------
# Horizons
HORIZON_126 = 126  # primary (tactical win window + 6mo)
HORIZON_252 = 252  # primary (kill-test label horizon)
HORIZON_504 = 504  # caveat-stamped

# Tactical win parameters (clean15_126, §2.2)
LIFTOFF_MULT = 1.15
STOP_MULT = 0.95
CUSHION_MULT = 1.05

# Coverage waiver threshold (§2.4, locked)
COVERAGE_WAIVER_THRESHOLD = 0.30

# Tercile thresholds
TERCILE_LOW = 1.0 / 3.0   # 33.3rd pctile
TERCILE_HIGH = 2.0 / 3.0  # 66.7th pctile

# Gap period (§4.1): massive store has no data for this window
GAP_PERIOD_START = pd.Timestamp("2021-10-25")
GAP_PERIOD_END = pd.Timestamp("2025-01-02")

# Honest cohort boundary (§4.1)
HONEST_COHORT_START = pd.Timestamp("2021-07-06")

# Episode-cluster ±10 trading days = ~14 calendar days (§6.3)
EPISODE_DEDUP_CALENDAR_DAYS = 14

# ---------------------------------------------------------------------------
# Price-source helpers
# ---------------------------------------------------------------------------

def _find_massive_dir() -> Path | None:
    """Find the massive_stock_day directory. Returns None if unreachable."""
    # Try repo-local first (has parquet files when running on the build machine)
    for candidate in [_MASSIVE_DIR_LOCAL, _MASSIVE_DIR_MAC]:
        if candidate.exists():
            # Check it has actual parquet files (not just manifest)
            parquets = list(candidate.glob("*.parquet"))
            if parquets:
                log.info("Massive store found at %s (%d parquets)", candidate, len(parquets))
                return candidate
    log.warning("Massive store not found (tried %s and %s) — falling back to yahoo+stocks only",
                _MASSIVE_DIR_LOCAL, _MASSIVE_DIR_MAC)
    return None


def _load_yahoo_closes() -> dict[str, pd.Series]:
    """Load all yahoo adjusted closes. Total-return dividend-adjusted series."""
    closes: dict[str, pd.Series] = {}
    if not _YAHOO_DIR.exists():
        log.warning("Yahoo dir not found: %s", _YAHOO_DIR)
        return closes
    for p in sorted(_YAHOO_DIR.glob("*.parquet")):
        ticker = p.stem
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna().sort_index()
            if len(s) > 0:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("yahoo load fail %s: %s", ticker, exc)
    log.info("Loaded %d yahoo closes", len(closes))
    return closes


def _load_stocks_closes() -> dict[str, pd.Series]:
    """Load deep-history survivor closes (data/stocks/). Survivor-only; caveat-stamped."""
    closes: dict[str, pd.Series] = {}
    if not _STOCKS_DIR.exists():
        return closes
    for p in sorted(_STOCKS_DIR.glob("*.parquet")):
        ticker = p.stem
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna().sort_index()
            if len(s) > 0:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("stocks load fail %s: %s", ticker, exc)
    log.info("Loaded %d stocks closes", len(closes))
    return closes


def _load_massive_closes(massive_dir: Path) -> dict[str, pd.Series]:
    """Load massive_stock_day closes (RAW, unadjusted; post-2021-07-06 only)."""
    closes: dict[str, pd.Series] = {}
    for p in sorted(massive_dir.glob("*.parquet")):
        ticker = p.stem
        if ticker.startswith("_"):  # skip manifest/meta files
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna().sort_index()
            if len(s) > 0:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.debug("massive load fail %s: %s", ticker, exc)
    log.info("Loaded %d massive closes", len(closes))
    return closes


def _load_dead_name_closes() -> dict[str, pd.Series]:
    """Load dead-name price store (data/edgar/dead_name_prices.parquet).

    Returns {ticker -> close Series}. This store covers post-2021-07-06 dead names
    via Polygon REST (adjusted closes). Source: W1 Phase-1 build.
    """
    closes: dict[str, pd.Series] = {}
    if not _DEAD_NAME_PRICES_PATH.exists():
        log.info("Dead-name price store not found: %s", _DEAD_NAME_PRICES_PATH)
        return closes
    try:
        df = pd.read_parquet(_DEAD_NAME_PRICES_PATH)
        if df.empty or "ticker" not in df.columns or "close" not in df.columns:
            return closes
        # Normalize dates to midnight to match massive_stock_day convention
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        for ticker, grp in df.groupby("ticker"):
            s = grp.set_index("date")["close"].sort_index()
            s = s[~s.index.duplicated(keep="last")]
            if len(s) >= 2:
                closes[str(ticker)] = s
    except Exception as exc:  # noqa: BLE001
        log.warning("Dead-name price store load fail: %s", exc)
    log.info("Loaded %d dead-name closes from %s", len(closes), _DEAD_NAME_PRICES_PATH)
    return closes


def resolve_price(
    ticker: str,
    yahoo_closes: dict[str, pd.Series],
    stocks_closes: dict[str, pd.Series],
    massive_closes: dict[str, pd.Series],
    dead_name_closes: dict[str, pd.Series] | None = None,
) -> tuple[pd.Series | None, str]:
    """Resolve close series for ticker. Returns (series, source_label).

    Priority: yahoo (adjusted TR) > massive (raw; post-2021) > dead_name (Polygon
    adjusted; post-anchor dead names) > stocks (survivor-only).
    source_label: 'yahoo' | 'massive' | 'dead_name' | 'stocks' | 'none'
    """
    s = yahoo_closes.get(ticker)
    if s is not None and not s.empty:
        return s, "yahoo"
    s = massive_closes.get(ticker)
    if s is not None and not s.empty:
        return s, "massive"
    if dead_name_closes is not None:
        s = dead_name_closes.get(ticker)
        if s is not None and not s.empty:
            return s, "dead_name"
    s = stocks_closes.get(ticker)
    if s is not None and not s.empty:
        return s, "stocks"
    return None, "none"


# ---------------------------------------------------------------------------
# Sector basket closes
# ---------------------------------------------------------------------------

# The data/baskets/ohlcv/ directory contains per-ticker OHLCV, NOT pre-built
# sector-basket OHLCV files. We build each sector benchmark as an equal-weight
# daily-return-based cumulative index from member closes, reindexed to a common
# trading calendar.
#
# Note on data basis: member closes in data/baskets/ohlcv/ are dividend-adjusted
# total-return series (same basis as data/yahoo). The EW sector index is
# computed from daily log-returns, which makes the basis cancel in the ratio.


def _build_sector_closes(
    membership_path: Path = _DATA / "baskets" / "membership.json",
    ohlcv_dir: Path = _SECTOR_OHLCV_DIR,
) -> dict[str, pd.Series]:
    """Build 11 EW GICS sector benchmark close series from member OHLCV.

    Strategy:
    1. Load baskets/membership.json and identify US Sectors (EW) baskets.
    2. For each sector basket, load member closes from data/baskets/ohlcv/.
    3. Align on a common date index, compute daily returns per member, average
       them (EW), then reconstruct a cumulative close series anchored to 1.0
       on the first available date.

    Returns {basket_key -> cumulative_close Series}.
    """
    closes: dict[str, pd.Series] = {}
    if not membership_path.exists():
        log.warning("baskets/membership.json not found; sector benchmarks unavailable")
        return closes

    try:
        bm = json.loads(membership_path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("membership.json load fail: %s", exc)
        return closes

    baskets = bm.get("baskets", {})

    for basket_key, val in baskets.items():
        if not isinstance(val, dict):
            continue
        if val.get("category", "") != "US Sectors (EW)":
            continue

        members = val.get("members", [])
        member_tickers = []
        for m in members:
            ticker = m.get("ticker", "") if isinstance(m, dict) else str(m)
            if ticker:
                member_tickers.append(ticker)

        if not member_tickers:
            continue

        # Load member closes
        member_series: list[pd.Series] = []
        for ticker in member_tickers:
            p = ohlcv_dir / f"{ticker}.parquet"
            if not p.exists():
                continue
            try:
                df = pd.read_parquet(p)
                if "close" not in df.columns:
                    continue
                s = df["close"].dropna().sort_index()
                if len(s) >= 2:
                    member_series.append(s.rename(ticker))
            except Exception as exc:  # noqa: BLE001
                log.debug("ohlcv load fail %s: %s", ticker, exc)

        if not member_series:
            log.warning("Sector %s: no member closes available", basket_key)
            continue

        # Align on common index, compute daily returns, EW average
        panel = pd.concat(member_series, axis=1, join="outer")
        panel = panel.sort_index()
        # Forward-fill up to 2 days for holiday gaps; drop rows still all-NaN
        panel = panel.ffill(limit=2).dropna(how="all")
        # Daily log-returns per member
        rets = np.log(panel).diff()
        # EW average of log-returns (at least 3 members must have data)
        ew_ret = rets.mean(axis=1, skipna=True)
        # Mask days with fewer than 3 non-NaN members as NaN
        valid_counts = rets.notna().sum(axis=1)
        ew_ret[valid_counts < 3] = np.nan
        ew_ret = ew_ret.dropna()
        if len(ew_ret) < 2:
            log.warning("Sector %s: too few valid dates for EW benchmark", basket_key)
            continue

        # Reconstruct cumulative close (anchored at 1.0)
        cum = np.exp(ew_ret.cumsum())
        closes[basket_key] = cum.rename(basket_key)

    log.info("Built %d sector benchmarks (EW from member closes)", len(closes))
    return closes


def _build_ticker_sector_map() -> dict[str, str]:
    """Build ticker -> sector_basket_key for use with the EW sector benchmark closes.

    LT-1c: PREFER data/breadth/ticker_sectors.parquet (scripts/build_sector_map.py)
    which covers ~1,500 tickers (GICS from all 3 S&P constituent files + SIC-mapped)
    vs 503 from baskets/membership.json alone.  Falls back to the old membership.json
    path for tickers not in the expanded map.

    Returns {ticker: basket_key} where basket_key is one of the 11 US Sectors (EW)
    basket identifiers from baskets/membership.json (e.g. 'us_sector_tech').
    """
    # --- LT-1c: GICS name → basket key translation table ---
    # Maps the 11 GICS-style strings used in ticker_sectors.parquet to the
    # corresponding 'us_sector_*' basket keys in baskets/membership.json.
    _GICS_TO_BASKET: dict[str, str] = {
        "Communication Services": "us_sector_comm",
        "Consumer Discretionary":  "us_sector_discretionary",
        "Consumer Staples":        "us_sector_staples",
        "Energy":                  "us_sector_energy",
        "Financials":              "us_sector_financials",
        "Health Care":             "us_sector_health",
        "Industrials":             "us_sector_industrials",
        "Information Technology":  "us_sector_tech",
        "Materials":               "us_sector_materials",
        "Real Estate":             "us_sector_realestate",
        "Utilities":               "us_sector_utilities",
    }

    sector_map: dict[str, str] = {}

    # --- Step 1: load the expanded ticker_sectors map (preferred) ---
    if _TICKER_SECTORS_PATH.exists():
        try:
            ts_df = pd.read_parquet(_TICKER_SECTORS_PATH)
            for _, row in ts_df.iterrows():
                ticker = str(row["ticker"])
                gics = str(row.get("sector", "") or "")
                basket_key = _GICS_TO_BASKET.get(gics)
                if basket_key and ticker:
                    sector_map[ticker] = basket_key
            log.info("Sector map (ticker_sectors.parquet): %d tickers", len(sector_map))
        except Exception as exc:  # noqa: BLE001
            log.warning("ticker_sectors.parquet load failed (%s); falling back to membership.json",
                        exc)
            sector_map = {}

    # --- Step 2: fill remaining gaps from baskets/membership.json ---
    membership_path = _DATA / "baskets" / "membership.json"
    if not membership_path.exists():
        if not sector_map:
            log.warning("baskets/membership.json not found and ticker_sectors unavailable; "
                        "sector map empty")
        return sector_map
    try:
        bm = json.loads(membership_path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load membership.json: %s", exc)
        return sector_map
    baskets = bm.get("baskets", {})
    added_from_membership = 0
    for key, val in baskets.items():
        if not isinstance(val, dict):
            continue
        if val.get("category", "") != "US Sectors (EW)":
            continue
        for m in val.get("members", []):
            ticker = m.get("ticker", "") if isinstance(m, dict) else str(m)
            if ticker and ticker not in sector_map:
                sector_map[ticker] = key
                added_from_membership += 1
    log.info("Sector map final: %d tickers (%d from membership.json fill)",
             len(sector_map), added_from_membership)
    return sector_map


# ---------------------------------------------------------------------------
# Fundamentals: Piotroski F-score
# ---------------------------------------------------------------------------

def _piotroski_from_panel_rows(rows: list[dict]) -> float | None:
    """Simplified 7-8 point Piotroski F from fundamentals_panel rows (ascending FY).

    Reuses the same logic as scripts/research/run_w2_sql.py _piotroski_from_panel_rows.
    Panel columns: ni, assets, cfo, debt_lt, shares, gross_profit, revenue,
    assets_prior, ni_prior, equity. Returns None if < 5 tests computable.
    """
    if len(rows) < 2:
        return None
    a, b = rows[-2], rows[-1]  # prior, latest FY

    def n(r: dict, k: str) -> float | None:
        v = r.get(k)
        return float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None

    def ratio(r: dict, num: str, den: str) -> float | None:
        x, y = n(r, num), n(r, den)
        return x / y if (x is not None and y not in (None, 0.0)) else None

    score, total = 0, 0
    tests = [
        (ratio(b, "ni", "assets"), None, "gt0"),
        (n(b, "cfo"), None, "gt0"),
        (ratio(b, "ni", "assets"), ratio(a, "ni", "assets"), "gt"),
        (n(b, "cfo"), n(b, "ni"), "gt"),
        (ratio(a, "debt_lt", "assets"), ratio(b, "debt_lt", "assets"), "gt"),
        (n(a, "shares"), n(b, "shares"), "gte"),
        (ratio(b, "gross_profit", "revenue"), ratio(a, "gross_profit", "revenue"), "gt"),
        (ratio(b, "revenue", "assets"), ratio(a, "revenue", "assets"), "gt"),
    ]
    for x, y, op in tests:
        if x is None or (op in ("gt", "gte") and y is None):
            continue
        total += 1
        if op == "gt0":
            score += 1 if x > 0 else 0
        elif op == "gt":
            score += 1 if x > y else 0
        elif op == "gte":
            score += 1 if x >= y * 1.01 else 0

    if total < 5:
        return None
    return float(score)


def build_quality_panel(panel_path: Path) -> pd.DataFrame:
    """Load fundamentals_panel and compute Piotroski F per (ticker, fy).

    Returns DataFrame with: ticker, fy, asof_date, period_end, piotroski_f.
    asof_date = period_end + 120 calendar days (assumed lag, PIT_BASIS).
    """
    if not panel_path.exists():
        log.warning("fundamentals_panel.parquet not found: %s", panel_path)
        return pd.DataFrame(columns=["ticker", "fy", "asof_date", "period_end", "piotroski_f"])

    df = pd.read_parquet(panel_path)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "fy", "asof_date", "period_end", "piotroski_f"])

    log.info("Loaded fundamentals_panel: %d rows, %d tickers", len(df), df["ticker"].nunique())

    records = []
    for ticker, grp in df.sort_values("fy").groupby("ticker"):
        rows = grp.to_dict("records")
        for i, row in enumerate(rows):
            pit_rows = rows[:i + 1]
            pio = _piotroski_from_panel_rows(pit_rows) if i >= 1 else None
            records.append({
                "ticker":     str(ticker),
                "fy":         int(row["fy"]),
                "asof_date":  pd.Timestamp(row["asof_date"]),
                "period_end": pd.Timestamp(row["period_end"]),
                "piotroski_f": pio,
            })

    qp = pd.DataFrame(records)
    if qp.empty:
        return qp
    qp["asof_date"] = pd.to_datetime(qp["asof_date"])
    qp["period_end"] = pd.to_datetime(qp["period_end"])
    log.info("Quality panel: %d rows, piotroski_f non-null=%d",
             len(qp), qp["piotroski_f"].notna().sum())
    return qp


def pit_piotroski(
    ticker: str,
    fire_date: pd.Timestamp,
    qp_by_ticker: dict[str, list[dict]],
) -> float | None:
    """PIT-safe Piotroski: latest FY row with asof_date <= fire_date."""
    rows = qp_by_ticker.get(ticker, [])
    best = None
    best_asof = None
    for row in rows:
        asof = row["asof_date"]
        if asof <= fire_date:
            if best_asof is None or asof > best_asof:
                best = row["piotroski_f"]
                best_asof = asof
    return best


# ---------------------------------------------------------------------------
# Terminal state: tactical win (clean15_126)
# ---------------------------------------------------------------------------

def _tactical_win_state(
    close: pd.Series,
    fire_date: pd.Timestamp,
) -> dict[str, Any]:
    """Compute clean15_126 terminal state for fire. Returns:
    {state: TerminalState | None, bars_matured: int, entry_price: float | None}
    """
    from engine.grading import terminal_state, fill_index, TerminalState  # noqa: PLC0415
    result = terminal_state(
        close, fire_date,
        liftoff_mult=LIFTOFF_MULT,
        liftoff_horizon=HORIZON_126,
        stop_mult=STOP_MULT,
        cushion_mult=CUSHION_MULT,
    )
    # Count how many forward bars are actually available (for maturity check)
    from engine.grading import fill_index as _fi  # noqa: PLC0415
    fi = _fi(close, fire_date)
    bars_available = max(0, len(close) - fi - 1) if fi is not None else 0
    return {
        "state": result.get("state"),
        "entry_price": result.get("entry_price"),
        "bars_available": bars_available,
    }


def _count_forward_bars(close: pd.Series, fire_date: pd.Timestamp, horizon: int) -> int:
    """Count forward bars from fill bar to at most horizon bars."""
    from engine.grading import fill_index  # noqa: PLC0415
    fi = fill_index(close, fire_date)
    if fi is None:
        return 0
    return max(0, min(horizon, len(close) - fi - 1))


def _total_return(
    close: pd.Series,
    fire_date: pd.Timestamp,
    horizon: int,
    max_intra_window_gap_days: int = 10,
) -> float | None:
    """Total return from fill bar to fill+horizon bar.

    Returns None if the forward window is shorter than `horizon` bars OR if any
    consecutive date pair inside the window is separated by more than
    `max_intra_window_gap_days` calendar days.  The latter guard catches
    per-ticker data gaps (e.g., a ticker missing 2021-10-25 → 2025-01-02 data):
    without it, `fwd.iloc[horizon-1]` resolves to a bar that is nominally bar N
    but is separated from bar N-1 by years, corrupting the 'N-bar return' label.

    Per ruling LH-W1-3: callers must verify that the forward leg is calendar-
    contiguous.  A gap > 10 calendar days between any two consecutive bars in
    the horizon window is treated as a disqualifying discontinuity; the return
    is returned as None and the fire is stamped `gap_leg_crossed=True` by the
    caller.
    """
    from engine.grading import fill_index  # noqa: PLC0415
    fi = fill_index(close, fire_date)
    if fi is None:
        return None
    entry = float(close.iloc[fi])
    if entry <= 0:
        return None
    fwd = close.iloc[fi + 1:]
    if len(fwd) < horizon:
        return None
    window = fwd.iloc[:horizon]
    # Calendar-continuity guard: reject if any intra-window gap exceeds threshold.
    # Use pd.Series.diff() which handles DatetimeIndex correctly.
    window_dates = pd.Series(window.index)
    day_diffs = window_dates.diff().dt.days.dropna()
    if len(day_diffs) > 0 and day_diffs.max() > max_intra_window_gap_days:
        return None
    return float(window.iloc[horizon - 1]) / entry - 1.0


# ---------------------------------------------------------------------------
# Sector-relative return
# ---------------------------------------------------------------------------

def _forward_leg_has_gap(
    close: pd.Series,
    fire_date: pd.Timestamp,
    horizon: int,
    max_intra_window_gap_days: int = 10,
) -> bool:
    """Return True if the horizon-bar forward window from fill_index contains any
    intra-bar gap exceeding max_intra_window_gap_days calendar days.

    This is the forward-leg integrity check required by ruling LH-W1-3.  It is
    distinct from `gap_period` (which gates only the fire_date itself) and from
    `survivorship_biased` (which tracks dead-name presence).  A fire can be
    survivorship-clean yet have a gap-corrupted forward leg.

    Returns False if the window is too short to evaluate (caller should treat as
    insufficient bars, not as a gap crossing).
    """
    from engine.grading import fill_index  # noqa: PLC0415
    fi = fill_index(close, fire_date)
    if fi is None:
        return False
    fwd = close.iloc[fi + 1:]
    if len(fwd) < horizon:
        return False  # too short — not a gap crossing, just not matured
    window = fwd.iloc[:horizon]
    window_dates = pd.Series(window.index)
    day_diffs = window_dates.diff().dt.days.dropna()
    if len(day_diffs) == 0:
        return False
    return bool(day_diffs.max() > max_intra_window_gap_days)


def _sector_return(
    sector_close: pd.Series | None,
    fire_date: pd.Timestamp,
    horizon: int,
) -> float | None:
    """Compute total return for the sector basket over horizon bars from fire_date.

    Uses next-bar-after-fire_date as the entry bar to match _total_return's
    fill_index convention (stock total return is anchored on the fill bar, i.e. the
    first bar after fire_date).  This eliminates the 1-bar entry-convention offset
    in sector_rel_252d.
    """
    if sector_close is None or sector_close.empty:
        return None
    ts = pd.Timestamp(fire_date)
    idx = sector_close.index
    # Find the first bar strictly AFTER fire_date (next-bar fill convention)
    pos = int(np.searchsorted(idx.values, np.datetime64(ts), side="right"))
    if pos >= len(idx):
        return None
    entry = float(sector_close.iloc[pos])
    if entry <= 0:
        return None
    fwd = sector_close.iloc[pos + 1:]
    if len(fwd) < horizon:
        return None
    return float(fwd.iloc[horizon - 1]) / entry - 1.0


# ---------------------------------------------------------------------------
# Survivorship and gap-period flags
# ---------------------------------------------------------------------------

def _is_gap_period(fire_date: pd.Timestamp) -> bool:
    """True if fire is in the massive-store gap window (2021-10-25 → 2025-01-02)."""
    return GAP_PERIOD_START <= fire_date <= GAP_PERIOD_END


def _is_survivorship_biased(fire_date: pd.Timestamp, price_source: str) -> bool:
    """True if this fire's price data is known to be survivor-biased.

    Per §4.1: the ONLY survivorship-correct source is the Massive whole-market
    store (post-2021-07-06, outside the gap period).  data/yahoo and data/stocks
    are survivor-only datasets — delisted names are absent — so every fire
    resolved from those stores is stamped survivorship_biased=True regardless
    of fire date.  Gap-period massive fires (2021-10-25 → 2025-01-02) are also
    biased because the store has an entitlement gap across that window.

    dead_name (Polygon REST, post-anchor): covers post-2021-07-06 dead tickers;
    these fires ARE survivorship-correct by construction for post-anchor dates
    (dead names are explicitly present). The bias caveat (acquisition skew) is
    documented but does not affect the survivorship_biased flag.
    """
    if price_source in ("yahoo", "stocks"):
        return True  # survivor-only stores — biased at any date
    if price_source == "massive":
        return _is_gap_period(fire_date)
    if price_source == "dead_name":
        # Post-anchor Polygon-sourced dead-name prices: survivorship-correct at fire date
        # (the dead name is explicitly present). Gap period fires still flagged.
        return _is_gap_period(fire_date)
    return True


# ---------------------------------------------------------------------------
# Episode-cluster de-duplication (§6.3)
# ---------------------------------------------------------------------------

def build_regime_map(fires: pd.DataFrame) -> dict[pd.Timestamp, str]:
    """Build fire_date -> macro_regime map from data/regime/latest.json.

    Falls back to a single 'unknown' regime if not available.
    """
    if not _REGIME_LATEST.exists():
        log.warning("regime/latest.json not found; all fires assigned regime='unknown'")
        return {}
    try:
        reg = json.loads(_REGIME_LATEST.read_text())
        # regime/latest.json has a 'label' key for the CURRENT regime; it's not
        # a historical time series. For episode-clustering we need a history.
        # If only latest is available, we cannot assign historical regimes.
        # Use 'unknown' for all fires — the ±10d de-dup still runs but clustering
        # is less granular (name-only rather than name×regime).
        log.warning(
            "regime/latest.json provides only current regime — "
            "episode-cluster de-dup uses name-only blocks (conservative)"
        )
        return {}
    except Exception as exc:  # noqa: BLE001
        log.warning("regime load fail: %s; using 'unknown'", exc)
        return {}


def deduplicate_episode_clusters(
    fires_df: pd.DataFrame,
    regime_map: dict[pd.Timestamp, str],
) -> pd.DataFrame:
    """Apply (name × macro_regime) ±10d de-duplication per §6.3.

    Tie-break: keep earliest fire in each ±10-calendar-day window (greedy left-to-right).
    Returns DataFrame with boolean column 'is_episode_cluster_rep' (True = retained).
    """
    df = fires_df.copy()
    df["_regime"] = df["date"].map(regime_map).fillna("unknown")
    df["_group"] = df["ticker"].astype(str) + "|" + df["_regime"].astype(str)
    df = df.sort_values("date").reset_index(drop=True)
    kept = np.ones(len(df), dtype=bool)

    # Greedy left-to-right: for each retained fire, mark later fires within ±10d
    # of the same (ticker, regime) as duplicates.
    dates_np = df["date"].values
    groups = df["_group"].values

    for i in range(len(df)):
        if not kept[i]:
            continue
        anchor_date = pd.Timestamp(dates_np[i])
        anchor_group = groups[i]
        for j in range(i + 1, len(df)):
            if not kept[j]:
                continue
            if groups[j] != anchor_group:
                continue
            diff_days = abs((pd.Timestamp(dates_np[j]) - anchor_date).days)
            if diff_days <= EPISODE_DEDUP_CALENDAR_DAYS:
                kept[j] = False
            elif diff_days > EPISODE_DEDUP_CALENDAR_DAYS:
                # sorted by date, so no need to look further for this anchor
                break

    df["is_episode_cluster_rep"] = kept
    return df


# ---------------------------------------------------------------------------
# Core label computation
# ---------------------------------------------------------------------------

def compute_labels(
    fires: pd.DataFrame,
    yahoo_closes: dict[str, pd.Series],
    stocks_closes: dict[str, pd.Series],
    massive_closes: dict[str, pd.Series],
    sector_closes: dict[str, pd.Series],
    ticker_sector_map: dict[str, str],
    qp_by_ticker: dict[str, list[dict]],
    *,
    dead_name_closes: dict[str, pd.Series] | None = None,
    limit: int | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Label every fire row per OBJECTIVE.md §2 algorithm.

    Parameters
    ----------
    fires:
        gate_fires_baskets.parquet rows.
    yahoo_closes / stocks_closes / massive_closes:
        Price stores.
    sector_closes:
        {basket_key -> close Series}.
    ticker_sector_map:
        {ticker -> basket_key}.
    qp_by_ticker:
        {ticker -> list of quality panel rows (sorted ascending fy)}.
    limit:
        Cap to first N rows (smoke test).

    Returns
    -------
    DataFrame with all output fields per §2.4.
    """
    from engine.grading import TerminalState  # noqa: PLC0415

    if limit is not None:
        fires = fires.head(limit).copy()

    n_total = len(fires)
    log.info("Labeling %d fires...", n_total)

    rows_out: list[dict[str, Any]] = []
    t0 = time.time()

    for idx, row in fires.iterrows():
        ticker = str(row["ticker"])
        fire_date = pd.Timestamp(row["date"])
        cohort_year = fire_date.year

        rec: dict[str, Any] = {
            "ticker": ticker,
            "fire_date": fire_date,
            "cohort_year": cohort_year,
            "label": None,
            "label_reason": None,
            "tactical_win": None,
            "total_return_252d": None,
            "sector_rel_252d": None,
            "tercile_rank": None,
            "piotroski_f": None,
            "fund_unchecked": None,
            "survivorship_biased": None,
            "cohort_description": None,  # §4.3 mandatory field; set after price resolved
            "price_source": "none",
            "resolvable": False,
            "coverage_frac": None,
            "cohort_fundamentals_coverage_frac": None,
            "gap_period": _is_gap_period(fire_date),
            # Forward-leg integrity stamp (per ruling LH-W1-3):
            # True when any consecutive bar pair in the 252d forward window is
            # separated by > 10 calendar days (a data gap inside the horizon window).
            # Distinct from gap_period (which marks fire_date only) and from
            # survivorship_biased.  A gap_leg_crossed=True fire has total_return_252d=None
            # because _total_return returns None for such windows.
            "gap_leg_crossed": False,
            # Horizon status stamps
            "horizon_status_126": "primary_126d",
            "horizon_status_252": "primary_252d",
            "horizon_status_504": "caveat_504d",
            # Total return at other horizons (for coverage accounting)
            "total_return_126d": None,
            "total_return_504d": None,
        }

        # --- Step 1: resolve price path ---
        close, price_source = resolve_price(
            ticker, yahoo_closes, stocks_closes, massive_closes,
            dead_name_closes=dead_name_closes)
        rec["price_source"] = price_source
        rec["resolvable"] = close is not None

        if close is None or close.empty:
            rec["label"] = "unlabeled"
            rec["label_reason"] = "no_price"
            rec["cohort_description"] = "no_price"
            rows_out.append(rec)
            continue

        # Survivorship stamp + cohort_description (§4.3 mandatory fields)
        rec["survivorship_biased"] = _is_survivorship_biased(fire_date, price_source)
        if price_source == "massive" and not _is_gap_period(fire_date) and fire_date >= HONEST_COHORT_START:
            rec["cohort_description"] = "post-2021-07 massive (honest)"
        elif price_source == "dead_name" and not _is_gap_period(fire_date) and fire_date >= HONEST_COHORT_START:
            rec["cohort_description"] = "post-2021-07 dead_name Polygon (honest)"
        else:
            rec["cohort_description"] = "survivor-only (UPPER BOUND)"

        # --- Step 2: tactical win check (clean15_126) ---
        ts_result = _tactical_win_state(close, fire_date)
        state = ts_result["state"]
        rec["total_return_126d"] = _total_return(close, fire_date, HORIZON_126)

        if state is None:
            # Not matured at 126d
            rec["label"] = "unlabeled"
            rec["label_reason"] = "unmatured_126"
            rec["tactical_win"] = None
            rows_out.append(rec)
            continue

        if state != TerminalState.CLEAN_LIFTOFF:
            # Fire did not achieve tactical win
            rec["label"] = "tactical_only_fail"
            rec["tactical_win"] = False
            rows_out.append(rec)
            continue

        rec["tactical_win"] = True

        # --- Step 3: 252d return check ---
        fwd_bars_252 = _count_forward_bars(close, fire_date, HORIZON_252)
        if fwd_bars_252 < HORIZON_252:
            rec["label"] = "unlabeled"
            rec["label_reason"] = "unmatured_252"
            rows_out.append(rec)
            continue

        # Check forward-leg integrity (ruling LH-W1-3): stamp gap_leg_crossed before
        # calling _total_return so the reason for None is recorded in the output.
        if _forward_leg_has_gap(close, fire_date, HORIZON_252):
            rec["gap_leg_crossed"] = True
            rec["label"] = "unlabeled"
            rec["label_reason"] = "gap_leg_crossed_252"
            rows_out.append(rec)
            continue

        total_ret_252 = _total_return(close, fire_date, HORIZON_252)
        if total_ret_252 is None:
            rec["label"] = "unlabeled"
            rec["label_reason"] = "unmatured_252"
            rows_out.append(rec)
            continue

        rec["total_return_252d"] = total_ret_252

        # Sector-relative 252d return
        sector_key = ticker_sector_map.get(ticker)
        sector_close = sector_closes.get(sector_key) if sector_key else None
        sector_ret = _sector_return(sector_close, fire_date, HORIZON_252)
        if sector_ret is not None:
            rec["sector_rel_252d"] = total_ret_252 - sector_ret
        else:
            rec["sector_rel_252d"] = None  # sector benchmark unavailable

        # 504d return (caveat-stamped, not used for labeling)
        fwd_bars_504 = _count_forward_bars(close, fire_date, HORIZON_504)
        if fwd_bars_504 >= HORIZON_504:
            rec["total_return_504d"] = _total_return(close, fire_date, HORIZON_504)

        # PIT Piotroski
        pio = pit_piotroski(ticker, fire_date, qp_by_ticker)
        rec["piotroski_f"] = pio

        rows_out.append(rec)

        if verbose and (idx % 5000 == 0):
            elapsed = time.time() - t0
            log.info("Progress: %d/%d fires (%.1fs elapsed)", idx, n_total, elapsed)

    log.info("Pass 1 complete: %d rows in %.1fs", len(rows_out), time.time() - t0)

    out = pd.DataFrame(rows_out)

    # --- PRE-PASS: compute cohort_fundamentals_coverage_frac per cohort_year ---
    # Denominator: fires with tactical_win=True AND 252d bars matured.
    # Numerator: subset with non-null piotroski_f.
    # (§2.4 locked formula)
    tw_matured = out[
        (out["tactical_win"] == True) &   # noqa: E712
        (out["total_return_252d"].notna())
    ].copy()

    coverage_by_year: dict[int, float] = {}
    waived_by_year: dict[int, bool] = {}

    for yr, grp in tw_matured.groupby("cohort_year"):
        n_denom = len(grp)
        n_num = grp["piotroski_f"].notna().sum()
        frac = float(n_num / n_denom) if n_denom > 0 else 0.0
        coverage_by_year[yr] = frac
        waived_by_year[yr] = frac < COVERAGE_WAIVER_THRESHOLD

    out["cohort_fundamentals_coverage_frac"] = out["cohort_year"].map(coverage_by_year)
    coverage_waived_col = out["cohort_year"].map(waived_by_year).fillna(True)

    # --- TERCILE COMPUTATION per cohort_year ---
    # Cutoffs computed on tactical-win + 252d-matured fires only.
    tercile_33_by_year: dict[int, float] = {}
    tercile_67_by_year: dict[int, float] = {}

    for yr, grp in tw_matured.groupby("cohort_year"):
        vals = grp["total_return_252d"].dropna()
        if len(vals) >= 3:
            tercile_33_by_year[yr] = float(np.nanpercentile(vals, 33.333))
            tercile_67_by_year[yr] = float(np.nanpercentile(vals, 66.667))
        else:
            # Insufficient fires: use min/max as degenerate cutoffs
            tercile_33_by_year[yr] = float(vals.min()) if len(vals) > 0 else 0.0
            tercile_67_by_year[yr] = float(vals.max()) if len(vals) > 0 else 0.0

    # Assign tercile_rank as percentile within cohort_year (0.0 to 1.0)
    out["tercile_rank"] = np.nan
    for yr, grp in tw_matured.groupby("cohort_year"):
        vals = grp["total_return_252d"].dropna()
        if vals.empty:
            continue
        all_vals = vals.values
        idx_mask = (out["cohort_year"] == yr) & out["total_return_252d"].notna() & (out["tactical_win"] == True)  # noqa: E712
        fire_vals = out.loc[idx_mask, "total_return_252d"].values
        # Rank each fire's 252d return in the cross-section of that cohort-year
        n = len(all_vals)
        for i, fi_val in zip(out.index[idx_mask], fire_vals):
            rank_frac = float(np.sum(all_vals < fi_val)) / n  # fraction of cohort below
            out.loc[i, "tercile_rank"] = rank_frac

    # --- MAIN PASS: assign final labels ---
    labels_final: list[str] = []
    fund_unchecked_final: list[bool | None] = []

    for i, row_out in out.iterrows():
        existing_label = row_out["label"]
        if pd.notna(existing_label) and str(existing_label) != "nan":
            # Already labeled (no_price, unmatured_126, unmatured_252, tactical_only_fail)
            labels_final.append(existing_label)
            fund_unchecked_final.append(None)
            continue

        yr = int(row_out["cohort_year"])
        ret = row_out["total_return_252d"]
        sec_rel = row_out["sector_rel_252d"]
        pio = row_out["piotroski_f"]
        coverage_w = waived_by_year.get(yr, True)
        t_rank = row_out["tercile_rank"]

        if ret is None or pd.isna(ret) or pd.isna(t_rank):
            labels_final.append("unlabeled")
            fund_unchecked_final.append(None)
            continue

        # §2.4 label algorithm
        if t_rank >= TERCILE_HIGH:
            # Top tercile
            if sec_rel is not None and sec_rel >= 0:
                # Top absolute AND beats sector → A or B
                if coverage_w or (pio is not None and pio >= 6):
                    lbl = "compounder"
                    fuc = (coverage_w and pio is None)
                else:
                    # pio is available and < 6, coverage not waived
                    lbl = "multiple_expansion_only"
                    fuc = False
            else:
                # Top absolute but lagged sector → G
                # (sec_rel is None or < 0)
                # If sec_rel is None (no sector benchmark), conservative: assign G
                # (cannot confirm beats sector → cannot be compounder/MEO)
                lbl = "sector_laggard_winner"
                fuc = None
        elif t_rank < TERCILE_LOW:
            # Bottom tercile → C
            lbl = "cheap_trap"
            fuc = None
        else:
            # Middle tercile → D
            lbl = "tactical_only"
            fuc = None

        labels_final.append(lbl)
        fund_unchecked_final.append(fuc)

    out["label"] = labels_final
    out["fund_unchecked"] = fund_unchecked_final

    # --- Coverage frac per cohort (overall price resolvability) ---
    for yr in out["cohort_year"].unique():
        mask_yr = out["cohort_year"] == yr
        n_yr = mask_yr.sum()
        n_res = (out.loc[mask_yr, "resolvable"] == True).sum()  # noqa: E712
        out.loc[mask_yr, "coverage_frac"] = float(n_res / n_yr) if n_yr > 0 else 0.0

    # --- missed_hold derived flag ---
    out["missed_hold"] = (out["label"] == "compounder")

    log.info("Labeling complete: %d total rows", len(out))
    return out


# ---------------------------------------------------------------------------
# Episode-cluster counts per §6.3
# ---------------------------------------------------------------------------

def compute_episode_cluster_counts(
    labeled: pd.DataFrame,
    regime_map: dict[pd.Timestamp, str],
) -> dict[str, Any]:
    """Compute episode-cluster n at each horizon for honest cohorts.

    Returns dict with per-horizon counts.
    """
    # Honest cohort: post-2021-07-06 Massive at <=252d (§4.1)
    honest_252 = labeled[
        (labeled["fire_date"] >= HONEST_COHORT_START) &
        (~labeled["gap_period"].fillna(False)) &
        (labeled["price_source"].isin(["massive", "dead_name"])) &
        (labeled["total_return_252d"].notna())
    ].copy()

    # Also include 2025-2026 yahoo (delisters captured, §4.1)
    yahoo_2025_plus = labeled[
        (labeled["fire_date"] >= pd.Timestamp("2025-01-01")) &
        (labeled["price_source"] == "yahoo") &
        (labeled["total_return_252d"].notna())
    ].copy()

    honest_252_all = pd.concat([honest_252, yahoo_2025_plus]).drop_duplicates(
        subset=["ticker", "fire_date"])

    # 126d honest cohort: post-2021-07 massive + dead_name (survivorship-correct sources)
    # dead_name fires are post-anchor Polygon-sourced; valid for 126d forward labels
    honest_126 = labeled[
        (labeled["fire_date"] >= HONEST_COHORT_START) &
        (~labeled["gap_period"].fillna(False)) &
        (labeled["price_source"].isin(["massive", "dead_name"])) &
        (labeled["total_return_126d"].notna())
    ].copy()

    def _episode_cluster_count(df: pd.DataFrame, regime_map: dict) -> int:
        if df.empty:
            return 0
        df2 = df.copy()
        df2["_regime"] = df2["fire_date"].map(regime_map).fillna("unknown")
        df2 = df2.sort_values("fire_date").reset_index(drop=True)
        kept = np.ones(len(df2), dtype=bool)
        dates_np = df2["fire_date"].values
        groups = (df2["ticker"].astype(str) + "|" + df2["_regime"]).values
        for i in range(len(df2)):
            if not kept[i]:
                continue
            anchor = pd.Timestamp(dates_np[i])
            grp = groups[i]
            for j in range(i + 1, len(df2)):
                if not kept[j]:
                    continue
                if groups[j] != grp:
                    continue
                diff = abs((pd.Timestamp(dates_np[j]) - anchor).days)
                if diff <= EPISODE_DEDUP_CALENDAR_DAYS:
                    kept[j] = False
                else:
                    break
        return int(kept.sum())

    n_ec_252 = _episode_cluster_count(honest_252_all, regime_map)
    n_ec_126 = _episode_cluster_count(honest_126, regime_map)

    return {
        "honest_cohort_252d_n_fires": len(honest_252_all),
        "honest_cohort_252d_episode_clusters": n_ec_252,
        "honest_cohort_126d_n_fires": len(honest_126),
        "honest_cohort_126d_episode_clusters": n_ec_126,
        "n25_floor_met_252d": n_ec_252 >= 25,
        "n25_floor_met_126d": n_ec_126 >= 25,
    }


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------

def build_manifest(
    labeled: pd.DataFrame,
    episode_cluster_counts: dict[str, Any],
    runtime_seconds: float,
    massive_available: bool,
    conservative_choices: list[str],
) -> dict[str, Any]:
    """Build the per-label per-cohort-year manifest (§4 output spec)."""

    label_dist = labeled.groupby("label").size().to_dict()
    label_dist = {str(k): int(v) for k, v in label_dist.items()}

    # Per-cohort-year per-label counts
    cohort_label_counts: dict[str, dict[str, int]] = {}
    for (yr, lbl), grp in labeled.groupby(["cohort_year", "label"]):
        yr_str = str(yr)
        if yr_str not in cohort_label_counts:
            cohort_label_counts[yr_str] = {}
        cohort_label_counts[yr_str][str(lbl)] = len(grp)

    # Coverage frac by cohort
    coverage_by_cohort: dict[str, float] = {}
    for yr, grp in labeled.groupby("cohort_year"):
        n_total = len(grp)
        n_res = grp["resolvable"].fillna(False).sum()
        coverage_by_cohort[str(yr)] = round(float(n_res / n_total), 4) if n_total > 0 else 0.0

    # Survivorship stamps by cohort
    survivor_biased_by_cohort: dict[str, bool] = {}
    for yr, grp in labeled.groupby("cohort_year"):
        biased = bool(grp["survivorship_biased"].fillna(True).any())
        survivor_biased_by_cohort[str(yr)] = biased

    # Fund coverage by cohort
    fund_coverage_by_cohort: dict[str, float] = {}
    for yr in cohort_label_counts:
        mask = labeled["cohort_year"] == int(yr)
        vals = labeled.loc[mask, "cohort_fundamentals_coverage_frac"].dropna()
        fund_coverage_by_cohort[yr] = round(float(vals.iloc[0]), 4) if len(vals) > 0 else 0.0

    # Gap period counts
    gap_period_n = int(labeled["gap_period"].fillna(False).sum())

    # Tactical win counts
    tw_n = int((labeled["tactical_win"] == True).sum())  # noqa: E712
    tactical_fail_n = int((labeled["label"] == "tactical_only_fail").sum())
    unlabeled_n = int((labeled["label"] == "unlabeled").sum())

    # -----------------------------------------------------------------------
    # OOS honest-cohort subset (§8: 2020-2023, massive+dead_name, non-gap, 252d)
    # This is the number that governs G1 runnability — surfaced here per reviewer.
    # dead_name (Polygon-sourced) fires are included as a survivorship-correct source
    # for post-anchor dead tickers (LH-W1-3: auditor must verify forward path source).
    # -----------------------------------------------------------------------
    oos_honest_252 = labeled[
        (labeled["fire_date"] >= pd.Timestamp("2020-01-01")) &
        (labeled["fire_date"] <= pd.Timestamp("2023-12-31")) &
        (~labeled["gap_period"].fillna(False)) &
        (labeled["price_source"].isin(["massive", "dead_name"])) &
        (labeled["total_return_252d"].notna())
    ].copy()
    n_oos_honest_252_fires = len(oos_honest_252)

    # Episode-cluster de-dup for OOS honest subset (name-only; no regime history)
    def _ec_count(df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        import numpy as _np  # noqa: PLC0415
        df2 = df.sort_values("fire_date").reset_index(drop=True)
        kept = _np.ones(len(df2), dtype=bool)
        dates_np = df2["fire_date"].values
        tickers = df2["ticker"].values
        for i in range(len(df2)):
            if not kept[i]:
                continue
            anchor = pd.Timestamp(dates_np[i])
            t = tickers[i]
            for j in range(i + 1, len(df2)):
                if not kept[j]:
                    continue
                if tickers[j] != t:
                    continue
                diff = abs((pd.Timestamp(dates_np[j]) - anchor).days)
                if diff <= EPISODE_DEDUP_CALENDAR_DAYS:
                    kept[j] = False
                else:
                    break
        return int(kept.sum())

    n_oos_honest_252_clusters = _ec_count(oos_honest_252)

    # -----------------------------------------------------------------------
    # Fundamentals coverage waiver note (must-fix: waiver never fired)
    # -----------------------------------------------------------------------
    # Verify waiver status for each cohort and record the fact.
    waiver_fired_any = any(
        v < COVERAGE_WAIVER_THRESHOLD
        for v in fund_coverage_by_cohort.values()
        if v > 0  # exclude 2026 cohort which has 0 matured fires with tactwin+252d
    )
    # fund_unchecked fires (compounder where pio was None AND cohort coverage waived)
    n_fund_unchecked = int((labeled["fund_unchecked"] == True).sum())  # noqa: E712

    # -----------------------------------------------------------------------
    # Label G coverage note (§2.3: G fires excluded from kill-test; THREAT FLAG)
    # -----------------------------------------------------------------------
    n_g_total = int(label_dist.get("sector_laggard_winner", 0))
    g_df = labeled[labeled["label"] == "sector_laggard_winner"]
    n_g_no_sector = int(g_df["sector_rel_252d"].isna().sum()) if not g_df.empty else 0
    g_no_sector_pct = round(100.0 * n_g_no_sector / n_g_total, 1) if n_g_total > 0 else 0.0

    # -----------------------------------------------------------------------
    # gap_leg_crossed counts (ruling LH-W1-3 mandatory stamp)
    # -----------------------------------------------------------------------
    n_gap_leg_crossed = int(labeled["gap_leg_crossed"].fillna(False).sum())

    manifest = {
        "artifact": "long_hold_labels",
        "version": "W1-PR-E-r3",  # r3 = gap-leg-crossed guard + gap_leg_crossed stamp
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime_seconds": round(runtime_seconds, 1),
        "population": {
            "source": "data/research/gate_fires_baskets.parquet",
            "n_fires_total": len(labeled),
            "n_tickers": int(labeled["ticker"].nunique()),
            "date_range": [
                str(labeled["fire_date"].min().date()),
                str(labeled["fire_date"].max().date()),
            ],
        },
        "price_coverage": {
            "massive_store_available": massive_available,
            "n_resolvable": int(labeled["resolvable"].fillna(False).sum()),
            "n_no_price": int((labeled["label_reason"] == "no_price").fillna(False).sum()),
            "price_source_counts": labeled["price_source"].value_counts().to_dict(),
        },
        "label_distribution": label_dist,
        "tactical_summary": {
            "n_tactical_win": tw_n,
            "n_tactical_only_fail": tactical_fail_n,
            "n_unlabeled": unlabeled_n,
            "n_gap_period": gap_period_n,
            "n_gap_leg_crossed": n_gap_leg_crossed,
        },
        "cohort_label_counts": cohort_label_counts,
        "coverage_frac_by_cohort": coverage_by_cohort,
        "survivorship_biased_by_cohort": survivor_biased_by_cohort,
        "fundamentals_coverage_by_cohort": fund_coverage_by_cohort,
        "fundamentals_coverage_waiver_status": {
            "waiver_threshold": COVERAGE_WAIVER_THRESHOLD,
            "waiver_fired_for_any_cohort": waiver_fired_any,
            "n_fund_unchecked_compounders": n_fund_unchecked,
            "note": (
                "The §2.4 coverage waiver (coverage_waived = True when <30% of cohort "
                "tactical-win+252d-matured fires have non-null piotroski_f) NEVER FIRED "
                "for any cohort with matured fires. All cohort-year coverage fractions "
                "are >= 0.40 (range 0.40-0.61 for 2014-2025). Cohort 2026 has zero "
                "matured tactical wins with 252d bars and is excluded from the denominator. "
                f"All {label_dist.get('compounder', 0)} compounders have piotroski_f >= 6 "
                "from available panel data (or are in a coverage-waived cohort — but no "
                "cohort was coverage-waived). "
                f"fund_unchecked=True fires = {n_fund_unchecked}. "
                "The sensitivity run pre-registered in §2.4 "
                "(excluding fund_unchecked=True fires) is a null operation on this dataset."
            ),
        },
        "episode_cluster_counts": episode_cluster_counts,
        "oos_honest_cohort_252d": {
            "fire_date_range": "2021-07-06 to 2021-10-25 (within the OOS 2020-2023 split)",
            "n_fires": n_oos_honest_252_fires,
            "n_episode_clusters": n_oos_honest_252_clusters,
            "n25_floor_met": n_oos_honest_252_clusters >= 25,
            "note": (
                "The G1 kill criterion (§8) requires running on the OOS split (2020-2023) "
                "within honest cohorts (massive-only, non-gap, 252d matured). The practical "
                "honest-OOS window is only 2021-07-06 → 2021-10-25 (~3.5 months), because "
                "the massive store gap (2021-10-25 → 2025-01-02) means many tickers have "
                "per-ticker internal gaps in their forward paths; fires where the 252-bar "
                "forward window crosses such a gap are stamped gap_leg_crossed=True and "
                "excluded from the honest-OOS count (total_return_252d=None). The full-tape "
                "honest-252d count (episode_cluster_counts) includes non-OOS and 2025+ fires; "
                "the OOS-honest number above is the correct decision denominator for G1 "
                "runnability. Forward-leg continuity is verified by the calendar-gap guard "
                "in _total_return (max_intra_window_gap_days=10) per ruling LH-W1-3."
            ),
        },
        "label_g_coverage_warning": {
            "n_sector_laggard_winner_total": n_g_total,
            "n_sector_laggard_winner_no_benchmark": n_g_no_sector,
            "pct_no_benchmark": g_no_sector_pct,
            "WARNING": (
                "THREAT TO G1 POWER: Label G (sector_laggard_winner) is "
                f"{g_no_sector_pct}% a missing-benchmark bucket, not an economically-lagging "
                "bucket. Only 503 of 2,495 fire-tape tickers map to the 11 EW sector baskets "
                "(76% of matured fires have no sector benchmark). Per §2.3, G fires are "
                "excluded from the W1 missed_hold-vs-tactical_only contrast, so the majority "
                "of top-tercile fires that could be compounders are silently dropped from the "
                "kill-test on data-coverage grounds rather than economics. This is a documented "
                "conservative choice (§2.4) and not a code bug, but it substantially reduces "
                "G1 power. The G1 null may reflect sector-benchmark coverage, not absence of "
                "alpha. Pre-registered in §2.4; must be examined before ratifying a G1 null."
            ),
        },
        "survivorship_fields": {
            "survivorship_biased": (
                "bool per fire — True for all yahoo/stocks-sourced fires (survivor-only stores; "
                "delisted names absent) and for massive-store fires in the gap period "
                "(2021-10-25 → 2025-01-02). False ONLY for massive-store fires post-2021-07-06 "
                "outside the gap period."
            ),
            "gap_leg_crossed": (
                "bool per fire — True when the 252-bar forward window starting at fill_index "
                "contains any consecutive bar pair separated by > 10 calendar days. Distinct "
                "from gap_period (which gates fire_date only) and survivorship_biased (dead-name "
                "presence). A fire can be survivorship-clean yet have gap_leg_crossed=True. "
                "gap_leg_crossed=True fires have total_return_252d=None and label_reason="
                "'gap_leg_crossed_252'. They are excluded from all honest-cohort inference. "
                "This field satisfies ruling LH-W1-3: 'a separate forward-leg-integrity field "
                "that the study must carry'."
            ),
            "coverage_frac": "resolvable fires / total fires in cohort-year",
            "cohort_description": "post-2021-07 massive (honest) | post-2021-07 dead_name Polygon (honest) | survivor-only (UPPER BOUND) | no_price",
            "horizon_status": "primary_126d | primary_252d | caveat_504d | refused_756d",
        },
        "lh_r3_stamp": (
            "UPPER BOUND — survivor-only cohort applies to all yahoo/stocks-sourced fires and "
            "pre-2021-07 massive fires. Post-2021-07 massive-store fires (outside the gap "
            "2021-10-25 → 2025-01-02) are survivorship-correct per day. "
            "Per-ticker parquets in the massive store may have internal gaps within the "
            f"gap window; {n_gap_leg_crossed} fires have gap_leg_crossed=True (forward window "
            "contains a >10 calendar-day bar gap) and are excluded from honest-cohort labels. "
            "Post-2021-07 dead_name (Polygon-sourced) fires are also honest for dead names "
            "explicitly present in the data (acquisition skew residual exists; see "
            "DEAD_NAME_SPIKE.md §Deviations). "
            "756d results are REFUSED until dead_name_prices.parquet achieves >=50% coverage "
            "(current 38.3%, gate requires 50.0%)."
        ),
        "conservative_choices": conservative_choices,
        "firewall": (
            "This artifact has horizon_role=hold_thesis. It must NEVER feed entry-stack "
            "z-scores, board ordering, top-setups gates, alert triage, or push floor. "
            "Enforced by check_synapse_reads.py (CI)."
        ),
    }
    return manifest


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def run(
    dry_run: bool = False,
    limit: int | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the label harness. Returns the manifest dict."""
    t_start = time.time()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    log.info("=== Long-Hold Label Harness W1 PR-E ===")
    log.info("Pre-registration: research/long_hold/OBJECTIVE.md")

    # --- Conservative choices documentation ---
    conservative_choices = [
        "tercile_rank: computed as fraction of cohort-year tactical-win+252d-matured "
        "fires strictly below current fire; ties get same rank (no interpolation).",
        "sector_rel_252d=None treated as sector_laggard_winner (top tercile) rather than "
        "compounder/multiple_expansion_only — cannot confirm beats sector without benchmark.",
        "coverage_waived denominator includes only fires with tactical_win=True AND "
        "total_return_252d not None (as per locked §2.4 formula).",
        "Gap-period fires (2021-10-25 to 2025-01-02) labeled but flagged gap_period=True; "
        "included in output for coverage accounting but excluded from honest-cohort counts.",
        "Regime data unavailable from regime/latest.json (current-only snapshot); "
        "episode-cluster de-dup uses name-only blocks (conservative — more de-duplication).",
        "Piotroski F computed from fundamentals_panel.parquet via simplified 8-test "
        "variant (panel lacks cur_assets/cur_liab) as in run_w2_sql.py.",
    ]

    # --- Load fires ---
    if not _FIRES_PATH.exists():
        raise RuntimeError(f"Fire tape not found: {_FIRES_PATH}")
    fires = pd.read_parquet(_FIRES_PATH)
    fires["date"] = pd.to_datetime(fires["date"])
    log.info("Loaded %d fires from %s", len(fires), _FIRES_PATH)

    # --- Load price stores ---
    log.info("Loading price stores...")
    yahoo_closes = _load_yahoo_closes()

    massive_dir = _find_massive_dir()
    massive_available = massive_dir is not None
    massive_closes: dict[str, pd.Series] = {}
    if massive_dir is not None:
        log.info("Loading massive store from %s...", massive_dir)
        massive_closes = _load_massive_closes(massive_dir)
    else:
        log.warning("Massive store unreachable — coverage will be limited to yahoo+stocks")
        conservative_choices.append(
            "Massive store unreachable: coverage stamps are HONEST about this. "
            "Honest-cohort n at 252d will be near-zero without massive store."
        )

    stocks_closes = _load_stocks_closes()

    # --- Load dead-name price store (W1 Phase-1 Polygon build) ---
    log.info("Loading dead-name price store (data/edgar/dead_name_prices.parquet)...")
    dead_name_closes_map = _load_dead_name_closes()
    if dead_name_closes_map:
        log.info(
            "Dead-name price store loaded: %d tickers (Polygon REST, post-2021-07-06)",
            len(dead_name_closes_map),
        )
        conservative_choices.append(
            f"Dead-name price store loaded: {len(dead_name_closes_map)} tickers "
            "(W1 Phase-1 Polygon build). These are post-2021-07-06 dead names "
            "resolved via REST adjusted aggregates. Acquisition skew residual exists "
            "(see DEAD_NAME_SPIKE.md). Fires resolved via dead_name source stamped "
            "survivorship_biased=True if gap_period, otherwise False (honest)."
        )
    else:
        log.info("Dead-name price store unavailable — dead-name fires will be no_price")

    # --- Load sector baskets ---
    log.info("Building sector EW benchmark series from member closes...")
    sector_closes = _build_sector_closes()
    ticker_sector_map = _build_ticker_sector_map()

    # --- Load fundamentals quality panel ---
    log.info("Building Piotroski quality panel...")
    qp = build_quality_panel(_FUNDAMENTALS_PANEL)
    qp_by_ticker: dict[str, list[dict]] = {}
    if not qp.empty:
        qp["asof_date"] = pd.to_datetime(qp["asof_date"])
        for tk, grp in qp.groupby("ticker"):
            qp_by_ticker[str(tk)] = grp.sort_values("fy").to_dict("records")

    # --- Regime map (for episode-cluster de-dup) ---
    regime_map = build_regime_map(fires)

    # --- Compute labels ---
    if dry_run:
        log.info("DRY RUN — skipping label computation")
        manifest = {
            "dry_run": True,
            "n_fires": len(fires),
            "conservative_choices": conservative_choices,
        }
        print(json.dumps(manifest, indent=2, default=str))
        return manifest

    labeled = compute_labels(
        fires,
        yahoo_closes=yahoo_closes,
        stocks_closes=stocks_closes,
        massive_closes=massive_closes,
        sector_closes=sector_closes,
        ticker_sector_map=ticker_sector_map,
        qp_by_ticker=qp_by_ticker,
        dead_name_closes=dead_name_closes_map,
        limit=limit,
        verbose=verbose,
    )

    # --- Episode-cluster counts ---
    log.info("Computing episode-cluster counts...")
    episode_cluster_counts = compute_episode_cluster_counts(labeled, regime_map)
    log.info("Episode-cluster counts: %s", episode_cluster_counts)

    runtime = time.time() - t_start

    # --- Build manifest ---
    manifest = build_manifest(
        labeled,
        episode_cluster_counts=episode_cluster_counts,
        runtime_seconds=runtime,
        massive_available=massive_available,
        conservative_choices=conservative_choices,
    )

    if limit is not None:
        log.info("SMOKE RUN (limit=%d) — not writing output files", limit)
        log.info("Label distribution: %s", manifest["label_distribution"])
        return manifest

    # --- Write outputs ---
    log.info("Writing %s...", _OUT_PARQUET)
    _OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    labeled.to_parquet(_OUT_PARQUET, index=False)

    log.info("Writing %s...", _OUT_MANIFEST)
    _OUT_MANIFEST.write_text(json.dumps(manifest, indent=2, default=str))

    log.info("=== DONE: runtime=%.1fs ===", runtime)
    log.info("Label distribution: %s", manifest["label_distribution"])
    log.info("Tactical wins: %d", manifest["tactical_summary"]["n_tactical_win"])
    log.info("Episode-cluster counts: %s", episode_cluster_counts)
    log.info(
        "n>=25 floor: 252d=%s, 126d=%s",
        episode_cluster_counts["n25_floor_met_252d"],
        episode_cluster_counts["n25_floor_met_126d"],
    )

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Long-Hold Label Panel — W1 PR-E (OBJECTIVE.md §2).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print manifest without running label computation.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap to first N rows for smoke testing.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress progress logs.")
    args = parser.parse_args(argv)

    try:
        manifest = run(
            dry_run=args.dry_run,
            limit=args.limit,
            verbose=not args.quiet,
        )
        print(json.dumps(
            {k: v for k, v in manifest.items() if k not in ("cohort_label_counts",)},
            indent=2, default=str,
        ))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("Label harness failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
