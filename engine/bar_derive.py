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

BUCKETING ERA ``display-grid-abs-session-2026-08-06`` (:data:`ANCHOR_ERA`). The 2D/3D
derivers below used to bucket with ``resample("2B"/"3B")``, whose bin edges anchor to the
SERIES' FIRST timestamp and which mis-split every bucket spanning a market holiday. They
now cut on the ABSOLUTE session calendar — ``session_anchor.session_positions(dates,
market) // n``, labelled by the bucket's OPEN date — so a bucket is a function of
``(reference calendar, date)`` alone and matches ``signal_quality._tf_grid`` bar for bar.
Ruling: ``research/DISPLAY_GRID_ALIGNMENT_ADJUDICATION_BY_FABLE.md`` (DG-R1/R2/R6/R8);
measured blast radius: ``reports/display_grid_blast_radius.md``. The same era stamps the
``anchor`` block the chart emitters ship (:func:`chart_anchor`), so a rendered payload can
place itself against the grid it was cut on.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import logging
import re
import warnings

from engine import session_anchor   # the ONE absolute session calendar (DG-R1)
from lib import config

log = logging.getLogger(__name__)

#: The bucketing era the 2D/3D DISPLAY grids (and the ``anchor`` block every StockChart
#: payload ships) are cut under — DG-R6's single source, imported by the emitters rather
#: than re-typed. SEPARATE from ``signal_quality.ANCHOR_ERA`` (the §7 marker stream) and
#: ``confluence_tiers.ANCHOR_ERA`` (the cascade): three grids, three stamps, so a payload
#: or a graded row can place itself against each one independently.
ANCHOR_ERA = "display-grid-abs-session-2026-08-06"

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


#: Rules DG-R8 refuses: ``2B``/``3B``/any ``<n>B`` with n>=2. Plain ``B`` (one business day)
#: is a relabelling, not a bucketing, and is left alone; so are '1D' and 'W-FRI'.
_MULTI_BDAY_RULE = re.compile(r"^\s*(\d+)\s*B\s*$", re.IGNORECASE)

#: The candle aggregation, in payload column order. Only PRESENT columns are used (the
#: nightly store has no 'open').
_OHLCV_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample an OHLCV frame to ``rule`` (e.g. '1D', 'W-FRI') with the standard candle
    aggregation. Tolerant of a missing 'open' column (the nightly store has none) — only
    present columns are aggregated. Empty buckets are dropped.

    REFUSES multi-business-day rules — '2B', '3B', any ``<n>B`` with n>=2 (DG-R8). Those
    bins anchor their edges to the SERIES' FIRST timestamp, so the same name cut from two
    windows disagrees bar for bar, and they mis-split every bucket spanning a market
    holiday. Closing the footgun is the point: leaving it silently callable is how the
    2D/3D derivers below drifted away from ``signal_quality._tf_grid`` in the first place.
    Use :func:`derive_2d_ohlcv` / :func:`derive_3d_ohlcv`, which cut on the absolute
    session calendar. '1D' and 'W-FRI' behaviour is unchanged.
    """
    m = _MULTI_BDAY_RULE.match(str(rule))
    if m and int(m.group(1)) >= 2:
        raise ValueError(
            f"resample_ohlcv: refusing rule {rule!r} — multi-business-day bins phase their "
            f"edges to the series' FIRST timestamp (so two windows of one name disagree) "
            f"and mis-split every bucket spanning a market holiday. Use "
            f"engine.bar_derive.derive_2d_ohlcv / derive_3d_ohlcv, which bucket on the "
            f"absolute session calendar (engine.session_anchor, era {ANCHOR_ERA}). "
            f"'1D' / 'W-FRI' are unaffected.")
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    agg = {c: how for c, how in _OHLCV_AGG.items() if c in df.columns}
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


def _anchored_ohlcv(daily_df: pd.DataFrame, n: int, market: str = "US") -> pd.DataFrame:
    """n-SESSION OHLCV candles cut on the absolute session calendar (DG-R1/R2).

    ``bucket(d) = session_anchor.session_positions(d, market) // n`` — a function of
    ``(reference calendar, date)`` alone, so any two windows of one name agree bar for bar
    and no bucket is mis-split by a market holiday. Mirrors
    ``signal_quality._tf_grid`` exactly: the same positions, the same OPEN-date labels
    (the bucket's FIRST session carrying a finite close), the same skip-NaN aggregation.

    ``resample``'s tolerance contracts are kept: an unsorted index is sorted, duplicate
    dates collapse keep-last, only PRESENT columns are aggregated, and the empty-bucket
    drop stays ``dropna(subset=['close'])`` — or ``dropna(how='all')`` when the frame
    carries no close at all.
    """
    if daily_df is None or daily_df.empty:
        return daily_df if daily_df is not None else pd.DataFrame()
    df = daily_df
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()                     # resample used to sort; keep that contract
    df = df[~df.index.duplicated(keep="last")]
    idx = df.index if isinstance(df.index, pd.DatetimeIndex) else pd.DatetimeIndex(
        pd.to_datetime(df.index))
    agg = {c: how for c, how in _OHLCV_AGG.items() if c in df.columns}
    if not agg or len(idx) == 0:
        return df.iloc[:0]
    b = session_anchor.session_positions(idx, market) // n
    out = df.groupby(b, sort=True).agg(agg)      # groupby first/last skip NaN, as resample did
    # DG-R2 labels: the bucket's first session carrying a finite close (a real traded bar of
    # THIS frame), so a label is always addressable in the daily index. A bucket with nothing
    # finite in it keeps its first row's date — it only survives the drop below in the
    # no-close-column case, where the old code labelled it with a synthetic bin edge.
    ok = (df["close"].notna() if "close" in df.columns
          else df[list(agg)].notna().any(axis=1)).to_numpy()
    first_row = pd.Series(idx.to_numpy(), index=b).groupby(level=0, sort=True).first()
    label = first_row
    if ok.any():
        traded = pd.Series(idx.to_numpy()[ok], index=b[ok]).groupby(level=0, sort=True).first()
        label = traded.reindex(first_row.index).fillna(first_row)
    if "close" in out.columns:
        out = out.dropna(subset=["close"])
    else:
        out = out.dropna(how="all")
    out.index = pd.DatetimeIndex(label.reindex(out.index).to_numpy(), name=idx.name)
    return out


def derive_2d_ohlcv(daily_df: pd.DataFrame, market: str = "US") -> pd.DataFrame:
    """2-SESSION OHLCV candles from a DAILY OHLCV frame, anchored on ``market``'s absolute
    session calendar (DG-R1; ``market`` per ``session_anchor`` — US default, CN/HK/CA read
    their reference index store). SUPPLEMENTARY (Standout grid / regime); do NOT feed to
    ``signal_frame`` (it cuts its own 2D/3D grids internally from the daily CLOSE).

    Its close matches ``signal_quality._tf_grid(daily_df['close'], 2, market).close``, the
    same equality :func:`derive_3d_ohlcv` documents and CI pins."""
    return _anchored_ohlcv(daily_df, 2, market)


def derive_3d_ohlcv(daily_df: pd.DataFrame, market: str = "US") -> pd.DataFrame:
    """3-SESSION OHLCV candles (the confluence timeframe) from a DAILY OHLCV frame,
    anchored on ``market``'s absolute session calendar (DG-R1).

    SUPPLEMENTARY — the 3D close here equals what ``signal_frame`` derives internally
    (``signal_quality._tf_grid(daily_df['close'], 3, market).close``, bit-exact, labels
    included), but pass signal_frame the daily CLOSE Series, never this frame.

    That equality claim was FALSE from era ``sq-abs-session-2026-08-06`` — when
    ``_tf_grid`` moved to the absolute session calendar and this function was still cutting
    raw ``"3B"`` bins — until era ``display-grid-abs-session-2026-08-06`` restored it. It
    is no longer prose: ``tests/test_bar_derive.py`` pins it against ``_tf_grid`` itself on
    real NYSE sessions spanning a holiday, because copy that points at another module's
    behaviour is an untested contract."""
    return _anchored_ohlcv(daily_df, 3, market)


# -------------------------------------------------- display-grid chart anchor ----
# The server-side half of DG-R3: the chart cannot re-derive session positions in the
# browser, so every StockChart payload SHIPS its bucket boundaries. Emitters (
# scripts/build_chart_data.py, scripts/build_subsector_confluence.py,
# scripts/build_hk_library.py) call these two helpers; the era string lives once, here.

def bucket_ids(dates, n: int = 3, market: str = "US") -> np.ndarray:
    """Absolute n-session bucket id per date (DG-R1) — ``session_positions // n``."""
    idx = dates if isinstance(dates, pd.DatetimeIndex) else pd.DatetimeIndex(
        pd.to_datetime(dates))
    if len(idx) == 0:
        return np.zeros(0, dtype=np.int64)
    return session_anchor.session_positions(idx, market) // n


def trim_rows_to_bucket_open(dates, prev_date, market: str = "US", n: int = 3) -> int:
    """DG-R4: how many LEADING rows to drop so the window opens on a bucket boundary.

    ``prev_date`` is the session immediately BEFORE the window in the untruncated source
    (``None`` when nothing precedes it — then row 0 opens its bucket by construction and
    the answer is 0). Any leading row sharing ``prev_date``'s bucket would render as a
    PARTIAL first candle whose membership depends on where the ``tail(MAX_BARS)`` window
    happened to land, so it is cut. At most ``n - 1`` rows are ever dropped: the bucket
    holding ``prev_date`` has at most ``n`` reference sessions and at least one is
    ``prev_date``'s own.

    Cosmetic only — ``anchor.b3`` is the correctness carrier. This just keeps the first
    candle complete and the visible grid stable night over night.
    """
    if prev_date is None:
        return 0
    idx = dates if isinstance(dates, pd.DatetimeIndex) else pd.DatetimeIndex(
        pd.to_datetime(dates))
    if len(idx) == 0:
        return 0
    b = bucket_ids(pd.DatetimeIndex([pd.Timestamp(prev_date)]).append(idx), n, market)
    cut = 0
    while cut + 1 < len(b) and b[cut + 1] == b[0]:
        cut += 1
    return cut


def chart_anchor(dates, market: str = "US", n: int = 3) -> dict:
    """The payload ``anchor`` block (DG-R3/R6): ``{"era": ANCHOR_ERA, "b3": [...]}``.

    ``b3`` is the list of ROW INDICES at which a new absolute n-session bucket opens,
    always including 0 — the exact grouping the client must reproduce. Shipping the
    BOUNDARIES rather than a phase offset is deliberate: a phase would silently drift for
    the rest of the window on any missing reference session (a halt, a suspension, a
    short-history name), and ``b3`` is exact by construction for ~2 KB against a ~50 KB
    payload. Compute it on the EMITTED rows, after NaN filtering and after the DG-R4 trim.
    """
    b = bucket_ids(dates, n, market)
    b3 = [0] + [i for i in range(1, len(b)) if b[i] != b[i - 1]] if len(b) else []
    return {"era": ANCHOR_ERA, "b3": b3}


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
