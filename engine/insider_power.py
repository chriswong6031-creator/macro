"""engine/insider_power.py — Insider Power: quality-weighted Form-4 insider signal.

Inspired by StockInvest's "Insider Power" metric: "Based on the 100 latest insider trades
… the score focuses on the QUALITY of the trades" (weighted by size, time, transaction
type, and the person).

DATA SOURCES
------------
Primary  : data/sec_insider/panel/<quarter>.parquet
           Per-transaction panel with columns:
             ticker, filing_date, trans_date, rptownercik, code ('P'=buy, 'S'=sell),
             is_officer, is_director, is_tenpct, title, shares, price, usd, quarter
           PIT-clean: gate by filing_date (public availability), not trans_date.

Fallback  : site/factordata/insider_signals.json
           Cross-sectional snapshot: {ticker: {bps, buyers, sellers, net_mn}}
           Used when panel files are unavailable.

SCORE CONSTRUCTION (0-100 scale, 50 = neutral)
-----------------------------------------------
For a trailing window of the N most-recent-filing open-market transactions per ticker:

  1. TRANSACTION TYPE WEIGHT  (w_type)
     P (open-market purchase)   : +1.0
     S (open-market sale)       : -1.0
     (only code P/S is used; awards/grants have code A/F/other and are excluded)

  2. ROLE WEIGHT  (w_role)  — mirrors engine/insider_factor.py role_weights()
     top officer (CEO/CFO/COO/CHAIR/FOUNDER/…)  : 1.5
     line officer                                : 1.0
     director                                   : 0.6
     10%-holder                                 : 0.3
     other/unknown                              : 0.2

  3. RECENCY DECAY  (w_time)
     Exponential decay on calendar days since filing_date.
     w_time = exp(-decay_rate * days_since_filing)
     Default decay_rate = ln(2) / HALF_LIFE_DAYS (half-life = 90 days).
     Trades filed more than LOOKBACK_DAYS ago receive near-zero weight.

  4. SIZE WEIGHT  (w_size)
     |usd| / mean(|usd|) across all N trades (winsorised at 5x).
     Normalised so that the raw $ amount doesn't dominate but larger trades
     still receive higher weight within the window.

  Weighted score per trade  = w_type * w_role * w_time * w_size
  Raw score = sum of per-trade weighted scores
  Bounded score = 50 + 50 * tanh(raw / TANH_SCALE)  → [0, 100]

  Where no open-market P/S transactions exist in the window: NaN.

LIMITATIONS (honest)
--------------------
- The panel only contains open-market codes P and S. Awards (A), in-kind
  dispositions (F), and other codes are excluded from the quality score —
  this is by design (quality filter).
- The aggregate fallback (insider_signals.json) exposes only net_mn/bps/
  buyers/sellers — no per-trade type/role/recency breakdown. The fallback
  score is necessarily simpler: sign(net_mn) * normalized(|bps|), mapped 0-100.
- Panel data starts 2006q1; tickers with no filings in the trailing window
  receive NaN, not 0.
- Cross-sectional percentile used in catalog signals is computed at call time
  across all tickers with panel data — not stored pre-computed.

DISPLAY CONTRACT
----------------
Display-only / research. No 'validated' claim in any user-facing string.
No LLM-originated signals, scores, or escalations.
"""
from __future__ import annotations

import glob
import json
import logging
import math
import os
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Title keywords marking a top-of-house officer (mirrors insider_factor.py).
_TOP_TITLE: tuple[str, ...] = (
    "CHIEF EXEC", "CEO", "CHIEF FIN", "CFO", "PRESIDENT", "CHAIR",
    "FOUNDER", "CHIEF OPER", "COO", "PRINCIPAL EXEC", "PRINCIPAL FIN",
)

#: Trailing window for "latest N trades" scoring.
N_TRADES: int = 100

#: Only include trades filed within this many calendar days.
LOOKBACK_DAYS: int = 365

#: Recency decay half-life in calendar days.
HALF_LIFE_DAYS: float = 90.0

#: tanh normalisation scale — raw score below which tanh compresses near-linearly.
TANH_SCALE: float = 5.0

#: Insider-buy event threshold: score must exceed this to fire buy signal (0-100).
BUY_THRESHOLD: float = 60.0

#: Insider-sell event threshold: score must be below this to fire sell signal.
SELL_THRESHOLD: float = 40.0

# Derived decay rate
_DECAY_RATE: float = math.log(2.0) / HALF_LIFE_DAYS

# Canonical paths (relative to repo root, resolved at import time via __file__)
_REPO_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PANEL_DIR: str = os.path.join(_REPO_ROOT, "data", "sec_insider", "panel")
_JSON_PATH: str = os.path.join(_REPO_ROOT, "site", "factordata", "insider_signals.json")


# ---------------------------------------------------------------------------
# Panel data loading
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def _load_recent_panel(n_quarters: int = 4, as_of: str | None = None) -> pd.DataFrame:
    """Load the most recent ``n_quarters`` panel quarters into one DataFrame.

    Parameters
    ----------
    n_quarters : int
        How many of the most-recent quarterly panel files to load and concatenate.
    as_of : str or None
        If given (ISO date string), only include panel files whose quarter
        start-date <= as_of.  Used for PIT-clean scoring in signal fns.
        Pass as a stable string so LRU caching is effective per call-site.

    Returns
    -------
    pd.DataFrame  with columns matching the per-quarter panel schema.
    Empty DataFrame if no panel files are found.
    """
    files = sorted(glob.glob(os.path.join(_PANEL_DIR, "*.parquet")))
    if not files:
        log.warning("insider_power: no panel files found in %s", _PANEL_DIR)
        return pd.DataFrame()

    # Filter by as_of PIT gate
    if as_of is not None:
        as_of_ts = pd.Timestamp(as_of)
        def _quarter_start(fname: str) -> pd.Timestamp:
            stem = os.path.basename(fname).replace(".parquet", "")  # e.g. '2025q4'
            try:
                yr, q = int(stem[:4]), int(stem[5])
                month = (q - 1) * 3 + 1
                return pd.Timestamp(yr, month, 1)
            except Exception:
                return pd.Timestamp("2099-01-01")
        files = [f for f in files if _quarter_start(f) <= as_of_ts]

    files = files[-n_quarters:]
    if not files:
        return pd.DataFrame()

    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_parquet(f))
        except Exception as exc:
            log.warning("insider_power: failed to read %s: %s", f, exc)

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    return df


# ---------------------------------------------------------------------------
# Role-weight helper (mirrors insider_factor.py for consistency)
# ---------------------------------------------------------------------------

def _role_weight(row: pd.Series) -> float:
    """Return the conviction weight for a single transaction row."""
    title = str(row.get("title", "") or "").upper()
    is_top = any(k in title for k in _TOP_TITLE)
    if bool(row.get("is_officer", False)) and is_top:
        return 1.5
    if bool(row.get("is_officer", False)):
        return 1.0
    if bool(row.get("is_director", False)):
        return 0.6
    if bool(row.get("is_tenpct", False)):
        return 0.3
    return 0.2


def _role_weights_series(panel: pd.DataFrame) -> pd.Series:
    """Vectorised role-weight computation for a panel DataFrame."""
    title = panel["title"].fillna("").str.upper()
    is_top = title.apply(lambda t: any(k in t for k in _TOP_TITLE))

    w = pd.Series(0.2, index=panel.index, dtype=float)
    w = w.mask(panel["is_tenpct"].fillna(False).astype(bool), 0.3)
    w = w.mask(panel["is_director"].fillna(False).astype(bool), 0.6)
    w = w.mask(panel["is_officer"].fillna(False).astype(bool), 1.0)
    w = w.mask(panel["is_officer"].fillna(False).astype(bool) & is_top, 1.5)
    return w


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------

def insider_power(
    ticker_or_df: "str | pd.DataFrame",
    *,
    as_of_date: "str | pd.Timestamp | None" = None,
    n_trades: int = N_TRADES,
    lookback_days: int = LOOKBACK_DAYS,
    half_life_days: float = HALF_LIFE_DAYS,
    tanh_scale: float = TANH_SCALE,
    _panel: "pd.DataFrame | None" = None,
) -> float:
    """Quality-weighted insider power score for one ticker.

    Parameters
    ----------
    ticker_or_df : str or pd.DataFrame
        Ticker symbol string, or a single-ticker panel DataFrame (for testing).
    as_of_date : str, Timestamp, or None
        If given, only consider transactions with filing_date <= as_of_date.
        This is the PIT gate: filing_date is when the Form-4 became public.
    n_trades : int
        Maximum number of most-recent-filing open-market trades to include.
    lookback_days : int
        Discard trades older than this many calendar days from as_of_date
        (or from today if as_of_date is None).
    half_life_days : float
        Recency decay half-life in calendar days.
    tanh_scale : float
        Scale factor for tanh compression: output = 50 + 50*tanh(raw/tanh_scale).
    _panel : pd.DataFrame or None
        Optional override for the full panel — used in tests to avoid disk I/O.

    Returns
    -------
    float
        Score in [0, 100], 50 = neutral.
        NaN if no eligible open-market P/S transactions found.
    """
    if as_of_date is None:
        cutoff = pd.Timestamp.utcnow().tz_localize(None).normalize()
    else:
        cutoff = pd.Timestamp(as_of_date)

    # Obtain panel
    if isinstance(ticker_or_df, pd.DataFrame):
        panel = ticker_or_df
        ticker = None
    else:
        ticker = str(ticker_or_df).upper()
        if _panel is not None:
            panel = _panel
        else:
            # Load enough quarters to cover lookback_days
            n_q = max(4, math.ceil(lookback_days / 90) + 1)
            panel = _load_recent_panel(n_quarters=n_q, as_of=cutoff.strftime("%Y-%m-%d"))
        if panel.empty:
            return float("nan")
        panel = panel[panel["ticker"] == ticker]

    if panel.empty:
        return float("nan")

    # Ensure filing_date is datetime
    panel = panel.copy()
    panel["filing_date"] = pd.to_datetime(panel["filing_date"])

    # PIT gate: only trades with filing_date <= cutoff
    panel = panel[panel["filing_date"] <= cutoff]
    if panel.empty:
        return float("nan")

    # Open-market only: code P (purchase) or S (sale)
    panel = panel[panel["code"].isin(["P", "S"])]
    if panel.empty:
        return float("nan")

    # Lookback window
    earliest = cutoff - pd.Timedelta(days=lookback_days)
    panel = panel[panel["filing_date"] >= earliest]
    if panel.empty:
        return float("nan")

    # Take the N most recent by filing_date
    panel = panel.sort_values("filing_date", ascending=False).head(n_trades)

    # --- Component weights ---

    # 1. Transaction-type direction: buy = +1, sell = -1
    w_type = panel["code"].map({"P": 1.0, "S": -1.0}).fillna(0.0)

    # 2. Role weight (vectorised)
    w_role = _role_weights_series(panel)

    # 3. Recency decay: days since filing_date
    days_ago = (cutoff - panel["filing_date"]).dt.days.clip(lower=0).astype(float)
    decay_rate = math.log(2.0) / half_life_days
    w_time = np.exp(-decay_rate * days_ago.to_numpy())

    # 4. Size weight: |usd| normalised, winsorised at 5x mean
    usd_abs = panel["usd"].abs().fillna(0.0)
    mean_usd = usd_abs.mean()
    if mean_usd > 0:
        w_size = (usd_abs / mean_usd).clip(upper=5.0)
    else:
        w_size = pd.Series(1.0, index=panel.index)

    # Composite weight per trade
    per_trade = w_type.to_numpy() * w_role.to_numpy() * w_time * w_size.to_numpy()

    raw = float(np.sum(per_trade))

    # Bounded score: 0-100, 50 = neutral
    score = 50.0 + 50.0 * math.tanh(raw / tanh_scale)
    return round(score, 4)


# ---------------------------------------------------------------------------
# Cross-sectional universe score table
# ---------------------------------------------------------------------------

def insider_power_universe(
    tickers: "list[str] | None" = None,
    *,
    as_of_date: "str | pd.Timestamp | None" = None,
    n_trades: int = N_TRADES,
    lookback_days: int = LOOKBACK_DAYS,
    half_life_days: float = HALF_LIFE_DAYS,
    tanh_scale: float = TANH_SCALE,
    _panel: "pd.DataFrame | None" = None,
) -> pd.Series:
    """Compute insider_power scores for all tickers in the panel (or a given list).

    Returns
    -------
    pd.Series  index=ticker, values=score (float NaN where absent).
    """
    if as_of_date is None:
        cutoff = pd.Timestamp.utcnow().tz_localize(None).normalize()
    else:
        cutoff = pd.Timestamp(as_of_date)

    # Load panel
    if _panel is not None:
        panel = _panel.copy()
    else:
        n_q = max(4, math.ceil(lookback_days / 90) + 1)
        panel = _load_recent_panel(n_quarters=n_q, as_of=cutoff.strftime("%Y-%m-%d"))

    if panel.empty:
        return pd.Series(dtype=float)

    panel = panel.copy()
    panel["filing_date"] = pd.to_datetime(panel["filing_date"])

    # PIT gate
    panel = panel[panel["filing_date"] <= cutoff]
    # Open-market only
    panel = panel[panel["code"].isin(["P", "S"])]
    # Lookback
    earliest = cutoff - pd.Timedelta(days=lookback_days)
    panel = panel[panel["filing_date"] >= earliest]

    if tickers is not None:
        panel = panel[panel["ticker"].isin(tickers)]

    if panel.empty:
        return pd.Series(dtype=float)

    all_tickers = panel["ticker"].unique().tolist()
    scores = {}
    for tkr in all_tickers:
        sub = panel[panel["ticker"] == tkr]
        scores[tkr] = insider_power(
            sub,
            as_of_date=cutoff,
            n_trades=n_trades,
            lookback_days=lookback_days,
            half_life_days=half_life_days,
            tanh_scale=tanh_scale,
        )
    return pd.Series(scores, dtype=float)


# ---------------------------------------------------------------------------
# Fallback: aggregate-only score from insider_signals.json
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_json_snapshot() -> dict:
    """Load site/factordata/insider_signals.json, cached."""
    try:
        with open(_JSON_PATH) as f:
            return json.load(f)
    except Exception as exc:
        log.warning("insider_power: cannot load JSON snapshot %s: %s", _JSON_PATH, exc)
        return {}


def insider_power_from_snapshot(ticker: str) -> float:
    """Quality-constrained score from the aggregate JSON snapshot.

    LIMITATION: the snapshot only provides net_mn (net $ bought in millions),
    bps (net buy bps of mcap), buyers, sellers — no per-trade breakdown.
    The fallback score is sign(net_mn) * normalised(|bps|), mapped to 0-100.
    If bps is None (mcap unavailable), falls back to net_mn normalisation.
    Treat this as a coarser approximation.

    Returns NaN if the ticker is absent or all fields are None.
    """
    snap = _load_json_snapshot()
    rec = snap.get(ticker.upper())
    if rec is None:
        return float("nan")

    bps = rec.get("bps")
    net_mn = rec.get("net_mn")

    # Use bps (size-normalised) when available, else net_mn clipped
    if bps is not None and not math.isnan(float(bps)):
        # bps centred at 0; clip at ±30 bps (empirical 99th pct), map to [-1,+1]
        raw = float(np.clip(float(bps) / 30.0, -1.0, 1.0))
    elif net_mn is not None and not math.isnan(float(net_mn)):
        # net_mn: clip at ±100 M
        raw = float(np.clip(float(net_mn) / 100.0, -1.0, 1.0))
    else:
        return float("nan")

    return 50.0 + 50.0 * raw


# ---------------------------------------------------------------------------
# Catalog signal functions  (fn(df, **params) -> pd.Series aligned to df.index)
# ---------------------------------------------------------------------------
# All three signals are state signals (cross-sectional snapshot, constant per ticker
# like fundamental_valuation) — the score does not change bar-by-bar within a day;
# it is updated daily when the nightly pipeline regenerates the panel.
#
# PIT guarantee: the score is computed using only transactions with
# filing_date <= the last bar date in df.  This is enforced via the
# as_of_date parameter passed as the last bar of the OHLCV frame.
# ---------------------------------------------------------------------------


def _infer_ticker(df: pd.DataFrame) -> "str | None":
    """Infer ticker from df.attrs or df.index.name (mirrors fundamental_screens)."""
    t = df.attrs.get("ticker")
    if t:
        return str(t)
    if (
        isinstance(df.index.name, str)
        and len(df.index.name) <= 8
        and df.index.name.upper() == df.index.name
    ):
        return df.index.name
    return None


def _constant_series(df: pd.DataFrame, value: float, name: str) -> pd.Series:
    """Series of constant ``value`` aligned to df.index."""
    return pd.Series(value, index=df.index, dtype=float, name=name)


def insider_power_state(
    df: pd.DataFrame,
    *,
    n_trades: int = N_TRADES,
    lookback_days: int = LOOKBACK_DAYS,
    half_life_days: float = HALF_LIFE_DAYS,
    tanh_scale: float = TANH_SCALE,
    _panel: "pd.DataFrame | None" = None,
) -> pd.Series:
    """State signal: quality-weighted insider score (0-100, 50=neutral).

    Returns a constant Series aligned to df.index.  The as_of gate is set
    to the last date in df.index, so no future filings contaminate the score.
    NaN where the ticker has no eligible panel data.

    Parameters
    ----------
    df : OHLCV DataFrame.  df.attrs['ticker'] or df.index.name used for lookup.
    """
    ticker = _infer_ticker(df)
    if not ticker:
        return _constant_series(df, float("nan"), name="insider_power_state")

    # PIT: gate by the last bar date visible in the OHLCV frame
    if len(df.index) > 0:
        as_of = df.index[-1]
    else:
        as_of = None

    score = insider_power(
        ticker,
        as_of_date=as_of,
        n_trades=n_trades,
        lookback_days=lookback_days,
        half_life_days=half_life_days,
        tanh_scale=tanh_scale,
        _panel=_panel,
    )
    return _constant_series(df, score, name="insider_power_state")


def insider_buy(
    df: pd.DataFrame,
    *,
    threshold: float = BUY_THRESHOLD,
    n_trades: int = N_TRADES,
    lookback_days: int = LOOKBACK_DAYS,
    half_life_days: float = HALF_LIFE_DAYS,
    tanh_scale: float = TANH_SCALE,
    _panel: "pd.DataFrame | None" = None,
) -> pd.Series:
    """Event signal: 1.0 when insider_power_state >= threshold, else 0.0.

    NaN where no panel data exists for the ticker.

    Parameters
    ----------
    df : OHLCV DataFrame.
    threshold : float
        Minimum score to fire.  Default = BUY_THRESHOLD (60.0).
    """
    ticker = _infer_ticker(df)
    if not ticker:
        return _constant_series(df, float("nan"), name="insider_buy")

    if len(df.index) > 0:
        as_of = df.index[-1]
    else:
        as_of = None

    score = insider_power(
        ticker,
        as_of_date=as_of,
        n_trades=n_trades,
        lookback_days=lookback_days,
        half_life_days=half_life_days,
        tanh_scale=tanh_scale,
        _panel=_panel,
    )
    if math.isnan(score):
        value = float("nan")
    else:
        value = 1.0 if score >= threshold else 0.0
    return _constant_series(df, value, name="insider_buy")


def insider_sell(
    df: pd.DataFrame,
    *,
    threshold: float = SELL_THRESHOLD,
    n_trades: int = N_TRADES,
    lookback_days: int = LOOKBACK_DAYS,
    half_life_days: float = HALF_LIFE_DAYS,
    tanh_scale: float = TANH_SCALE,
    _panel: "pd.DataFrame | None" = None,
) -> pd.Series:
    """Event signal: 1.0 when insider_power_state <= threshold (net selling), else 0.0.

    NaN where no panel data exists for the ticker.

    Parameters
    ----------
    df : OHLCV DataFrame.
    threshold : float
        Maximum score to fire (below = net selling).  Default = SELL_THRESHOLD (40.0).
    """
    ticker = _infer_ticker(df)
    if not ticker:
        return _constant_series(df, float("nan"), name="insider_sell")

    if len(df.index) > 0:
        as_of = df.index[-1]
    else:
        as_of = None

    score = insider_power(
        ticker,
        as_of_date=as_of,
        n_trades=n_trades,
        lookback_days=lookback_days,
        half_life_days=half_life_days,
        tanh_scale=tanh_scale,
        _panel=_panel,
    )
    if math.isnan(score):
        value = float("nan")
    else:
        value = 1.0 if score <= threshold else 0.0
    return _constant_series(df, value, name="insider_sell")


# ---------------------------------------------------------------------------
# SIGNALS catalog  (consumed by engine/tech_catalog.py)
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict[str, Any]] = {
    "insider_power_state": {
        "fn": insider_power_state,
        "kind": "state",
        "family": "insider",
        "direction": 0,   # 0-100 DISPLAY score only — direction carried by insider_buy/insider_sell; +1 would dominate the -10..+10 composite
        "default_params": {
            "n_trades": N_TRADES,
            "lookback_days": LOOKBACK_DAYS,
            "half_life_days": HALF_LIFE_DAYS,
            "tanh_scale": TANH_SCALE,
        },
        "display": {
            "en": (
                "Insider Power (0–100) — quality-weighted Form-4 open-market "
                "trades (role × size × recency); 50 = neutral"
            ),
            "zh": (
                "内部人力量（0–100）—— "
                "加权Form-4公开市场交易"
                "（职务×规模×时效）；50=中性"
            ),
        },
        "glyph": "line",
    },
    "insider_buy": {
        "fn": insider_buy,
        "kind": "state",
        "family": "insider",
        "direction": +1,
        "default_params": {
            "threshold": BUY_THRESHOLD,
            "n_trades": N_TRADES,
            "lookback_days": LOOKBACK_DAYS,
            "half_life_days": HALF_LIFE_DAYS,
            "tanh_scale": TANH_SCALE,
        },
        "display": {
            "en": (
                f"Insider Buy signal — fires when Insider Power ≥ {BUY_THRESHOLD:.0f} "
                "(net buying on quality-weighted basis)"
            ),
            "zh": (
                f"内部人买入信号——"
                f"力量得分≥{BUY_THRESHOLD:.0f}时触发"
            ),
        },
        "glyph": "arrow_up",
    },
    "insider_sell": {
        "fn": insider_sell,
        "kind": "state",
        "family": "insider",
        "direction": -1,
        "default_params": {
            "threshold": SELL_THRESHOLD,
            "n_trades": N_TRADES,
            "lookback_days": LOOKBACK_DAYS,
            "half_life_days": HALF_LIFE_DAYS,
            "tanh_scale": TANH_SCALE,
        },
        "display": {
            "en": (
                f"Insider Sell signal — fires when Insider Power ≤ {SELL_THRESHOLD:.0f} "
                "(net selling on quality-weighted basis)"
            ),
            "zh": (
                f"内部人卖出信号——"
                f"力量得分≤{SELL_THRESHOLD:.0f}时触发"
            ),
        },
        "glyph": "arrow_down",
    },
}
