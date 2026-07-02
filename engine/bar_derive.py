"""Intraday -> multi-timeframe bar derivation hooks for the signal engine.

These are *hooks* the confluence-tuning + Standout-grid sessions can later consume to
run on intraday-derived bars instead of (or alongside) the nightly daily store. Nothing
here is wired into a production build by default — it is additive plumbing.

Two distinct outputs, do not confuse them:

  • ``derive_daily_close(intraday)`` -> a daily **close pd.Series** byte-compatible with
    ``pd.read_parquet('data/stocks/<T>.parquet')['close'].dropna()`` (index name 'Date',
    tz-naive midnight, float64, sorted, no NaN). This is the ONLY shape the confluence
    engine accepts — ``engine.signal_quality.signal_frame`` / ``analyze`` take a daily
    close Series and do the 3B / W-FRI resampling **internally** (faithful to the Pine).
    So an intraday source plugs in by swapping ONLY where the close Series comes from;
    signal_quality / build_signal_quality need no change beyond the source switch.

  • ``derive_2d_ohlcv`` / ``derive_3d_ohlcv`` -> **supplementary OHLCV frames** for the
    Standout-grid / ATR / regime reads that want true higher-timeframe candles. These are
    NOT inputs to ``signal_frame`` — never pass them to the confluence (that would
    double-resample and break faithfulness). They exist for the grid, not the signal.

HONESTY / CAVEATS (see research/LIVE_DATA_POLYGON.md):
  - The intraday store is **15-min DELAYED** (Polygon Standard) — see ``intraday_meta()``.
  - The intraday store carries **raw** prices; the nightly ``data/stocks`` close is
    dividend/total-return ADJUSTED. Confluence run on a raw intraday-derived close is NOT
    directly comparable to confluence on the adjusted daily store — keep the source
    consistent. This is why the intraday path is opt-in (off by default).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import logging
import re
import warnings

from lib import config

log = logging.getLogger(__name__)

GROUP = "intraday"
_DEFAULT_TZ = "America/New_York"   # US session day boundary for daily roll-up

# Ticker suffix patterns that indicate a non-US session; feeding these to
# derive_daily_close() WITHOUT an explicit ``tz`` will silently mis-bucket
# bars onto the NY calendar (e.g. a Shanghai 09:30 CST bar becomes a Monday
# NY midnight cross instead of a Tuesday CN trading date).
_NON_US_SUFFIX_RE = re.compile(
    r"\.(SS|SZ|HK|T|TO|AX|L|PA|DE|MI|MC|BR|BO|NS)$", re.IGNORECASE
)


# --------------------------------------------------------------------- io ----

def _intraday_dir(root: Path | None = None) -> Path:
    return (root or config.data_dir()) / GROUP


def intraday_meta(root: Path | None = None) -> dict:
    """The store's honest label sidecar ({delayed_min, source, realtime, ...}) or {}.
    Consumers should surface ``delayed_min`` so an intraday-derived view is never
    presented as real-time."""
    p = _intraday_dir(root) / "_meta.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def load_intraday(ticker: str, root: Path | None = None) -> pd.DataFrame | None:
    """Per-ticker intraday OHLCV (open/high/low/close/volume) with a UTC-aware
    DatetimeIndex named 'ts', or None when absent/unreadable."""
    p = _intraday_dir(root) / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if df.empty:
            return None
        idx = pd.to_datetime(df.index, utc=True)
        df = df.copy()
        df.index = idx
        df.index.name = "ts"
        return df[~df.index.duplicated(keep="last")].sort_index()
    except Exception:  # noqa: BLE001
        return None


# -------------------------------------------------------------- derivers ----

def derive_daily_close(intraday: pd.DataFrame, tz: str = _DEFAULT_TZ,
                       ticker: str = "") -> pd.Series:
    """Intraday bars -> a DAILY CLOSE Series shaped exactly like the nightly store's
    ``['close'].dropna()`` so it is a drop-in for ``engine.signal_quality.analyze``.

    The last bar of each session day (in market tz) is the day's close. Index is the
    tz-naive, midnight-normalised session date named 'Date'; dtype float64; sorted; no
    NaN. Weekends/holidays have no bars and simply do not appear.

    Parameters
    ----------
    intraday : pd.DataFrame
        UTC-indexed intraday OHLCV with a 'close' column.
    tz : str
        The *market* timezone used to determine which calendar day each
        intraday bar belongs to.  Defaults to ``America/New_York`` (correct
        for US equities).  **MUST be supplied explicitly for non-US markets**:
        use ``Asia/Shanghai`` for CN (A-shares on SS/SZ), ``Asia/Hong_Kong``
        for HK, ``America/Toronto`` for CA, etc.  Feeding an Asia-session
        ticker through the NY-default will mis-bucket bars onto the wrong
        calendar date — a bar that prints at 09:30 CST (01:30 UTC) will be
        rolled into the *previous* NY business day.
    ticker : str
        Optional — the ticker symbol.  When the suffix matches a known non-US
        exchange (e.g. ``.SS``, ``.HK``, ``.TO``) and ``tz`` is still the
        NY default, a loud ``UserWarning`` is raised so the mis-bucketing
        does not go unnoticed.
    """
    # ---- tz / region guard --------------------------------------------------
    if tz == _DEFAULT_TZ and ticker and _NON_US_SUFFIX_RE.search(ticker):
        warnings.warn(
            f"derive_daily_close: ticker={ticker!r} appears to be a non-US symbol "
            f"but tz defaulted to {_DEFAULT_TZ!r}.  Intraday bars will be bucketed "
            f"on the NY calendar, producing wrong session dates for this market.  "
            f"Pass the correct market tz (e.g. 'Asia/Shanghai', 'Asia/Hong_Kong', "
            f"'America/Toronto') via the ``tz`` parameter.",
            UserWarning,
            stacklevel=2,
        )
        log.warning(
            "derive_daily_close tz mismatch: ticker=%r suffix matches non-US exchange "
            "but tz=%r (NY default) — session dates will be mis-bucketed",
            ticker, tz,
        )
    # -------------------------------------------------------------------------
    if intraday is None or intraday.empty or "close" not in intraday.columns:
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([], name="Date"))
    px = intraday["close"].dropna()
    idx = px.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    px = px.copy()
    px.index = idx.tz_convert(tz)
    daily = px.resample("1D").last().dropna()
    daily.index = daily.index.tz_localize(None).normalize()
    daily.index.name = "Date"
    return daily.astype("float64")


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample an OHLCV frame to ``rule`` (e.g. '1D', '2B', '3B', 'W-FRI') with the
    standard candle aggregation. Tolerant of a missing 'open' column (the nightly store
    has none) — only present columns are aggregated. Empty buckets are dropped."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    agg = {c: how for c, how in agg.items() if c in df.columns}
    out = df.resample(rule).agg(agg)
    if "close" in out.columns:
        out = out.dropna(subset=["close"])
    else:
        out = out.dropna(how="all")
    return out


def derive_daily_ohlcv(intraday: pd.DataFrame, tz: str = _DEFAULT_TZ,
                       ticker: str = "") -> pd.DataFrame:
    """Intraday -> DAILY OHLCV candles (open/high/low/close/volume), 'Date' index
    (tz-naive midnight). Supplementary candle frame for the grid; NOT a signal input.
    Pass ``ticker`` to trigger the non-US tz guard (same contract as
    ``derive_daily_close``)."""
    if tz == _DEFAULT_TZ and ticker and _NON_US_SUFFIX_RE.search(ticker):
        warnings.warn(
            f"derive_daily_ohlcv: ticker={ticker!r} appears to be a non-US symbol "
            f"but tz defaulted to {_DEFAULT_TZ!r}.  Pass the correct market tz.",
            UserWarning,
            stacklevel=2,
        )
    if intraday is None or intraday.empty:
        return pd.DataFrame()
    df = intraday.copy()
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    df.index = idx.tz_convert(tz)
    daily = resample_ohlcv(df, "1D")
    daily.index = daily.index.tz_localize(None).normalize()
    daily.index.name = "Date"
    return daily


def derive_2d_ohlcv(daily_df: pd.DataFrame) -> pd.DataFrame:
    """2-business-day OHLCV candles from a DAILY OHLCV frame. SUPPLEMENTARY (Standout
    grid / regime); do NOT feed to ``signal_frame`` (it resamples close internally)."""
    return resample_ohlcv(daily_df, "2B")


def derive_3d_ohlcv(daily_df: pd.DataFrame) -> pd.DataFrame:
    """3-business-day OHLCV candles ('3B', matching the confluence timeframe) from a
    DAILY OHLCV frame. SUPPLEMENTARY — the 3D close here equals what ``signal_frame``
    derives internally, but pass signal_frame the daily CLOSE Series, never this frame."""
    return resample_ohlcv(daily_df, "3B")


# ------------------------------------------------------- integration hook ----

def daily_close_for(ticker: str, *, prefer_intraday: bool = False,
                    root: Path | None = None, stocks_dir: Path | None = None
                    ) -> pd.Series | None:
    """Daily close Series for a ticker for the signal engine.

    Default: the nightly adjusted store (``data/stocks/<T>.parquet``). When
    ``prefer_intraday`` and an intraday file exists, derive the daily close from it
    instead (raw prices — see module caveat). Returns None if neither source resolves.
    This is the single switch ``scripts/build_signal_quality.py --intraday`` flips."""
    if prefer_intraday:
        intr = load_intraday(ticker, root=root)
        if intr is not None:
            s = derive_daily_close(intr).dropna()
            if not s.empty:
                return s
    sd = stocks_dir or (config.data_dir() / "stocks")
    p = sd / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)["close"].dropna()
    except Exception:  # noqa: BLE001
        return None
