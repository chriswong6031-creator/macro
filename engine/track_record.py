"""Signal Track-Record Logger — append-only, key-deduped measurement log.

MEASUREMENT ONLY. Do NOT touch engine/signal_quality.py. Framing is entirely on
DRAWDOWN / entry-quality (CHARTER §2b, §3, §4). Never return-alpha.

The buy-filter cut avg max drawdown -23.7% → -15.5% across 110 held-out US names
(84% improved). This logger is the standing forward track record that proves — or
surfaces blind spots in — that claim.

Public API
----------
update_track_record(repo_root, signals_dir, mtf_path, stocks_dir, out_path, asof) -> dict
    Summary keys: new_rows, matured_rows, total_rows, skipped_pending, out_path.

NO LOOK-AHEAD rule (CHARTER §3): every entry-time feature uses ONLY daily data with
index ≤ the marker date; forward metrics use ONLY data > the marker date — in *index*
terms there is no look-ahead.

FILL CONVENTION (W1c, audit #15): a signal that fires on the close of the marker bar is
FILLED at the NEXT bar's close — the honest convention matching the VALIDATED research
harness (research/signal_engine/tuning_harness.py enters at f=i+1) and validation.py's
alloc.shift(1) "act next bar". `entry_price` is the fill bar (marker bar + 1); forward
returns/drawdowns are measured from that fill; the strictly-forward window never includes
the entry bar. The forward/fill math is centralized in engine.grading so this logger, the
sector graders, and the desk graders all use ONE convention. Same-bar fills flatter short
mean-reversion signals most (you buy the exact trough), so the pre-W1c same-bar version was
optimistic in exactly the direction that over-sizes a mechanical system; a shadow same-bar
column (fwd_mdd_60_samebar) is emitted alongside so the correction is measurable, not hidden.

Price-store caveat (honest framing, not a fatal leak): the daily store is back-adjusted
(CHARTER §5; data/stocks `close` is split- AND dividend-back-adjusted total-return,
verified empirically — AAPL has no gap across the 2020 4:1 split). Splits are a constant
multiplicative factor that CANCELS in every ratio we compute (entry_price, fwd_ret /
fwd_mdd / trade_ret, price-vs-SMA200, pct_change vol, the ER ratio are all scale-
invariant) → split adjustment is leak-neutral. The residual is DIVIDENDS: an interim
dividend rebases the entry-leg bar but not the t+H bar, so forward returns / drawdowns
are total-return-with-hindsight, injecting interim dividends unknown at entry. The bias
is bounded by interim dividend yield (typically <1% over 60d) — it nudges the drawdown
*magnitudes* slightly, not the take-vs-block *direction*. Feed an unadjusted/as-of price
series to remove it entirely.

Append-only + idempotent: identity/entry columns frozen on first write
(first-observed wins). Only NULL maturation columns get filled as data matures.
Re-running on unchanged inputs is a no-op.

Key = (ticker, date, type).

Dependencies: pandas, numpy, pyarrow ONLY. No scipy. Python 3.
"""
from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from engine import grading  # W1c: one shared next-bar/survivorship-aware grader

logger = logging.getLogger(__name__)


def _is_null(v: Any) -> bool:
    """NaN-aware null test.

    A maturation cell that was written as None round-trips back from a float64
    parquet column as ``np.nan`` (not None), so a plain ``v is None`` check would
    treat an un-matured cell as already-filled and SKIP it forever (maturation
    stall).  This handles None, np.nan, pd.NA, pd.NaT for scalars.
    """
    return v is None or (np.ndim(v) == 0 and pd.isna(v))


# ---------------------------------------------------------------------------
# Schema: ordered column list.  Types are pandas dtypes (object = str/nullable).
# ---------------------------------------------------------------------------

# Immutable identity + entry-time columns (frozen on first write, first-observed wins)
_IDENTITY_COLS = [
    "ticker",       # str
    "date",         # str YYYY-MM-DD  — the marker's 3D bar date
    "type",         # str  buy / rebuy / sell / cut
    "quality",      # str/null  take / block  (null for sell/cut)
    "reason",       # str/null  engine reason text  (null for sell/cut)
    "entry_price",  # float  close on date (snapped to prior bar if needed)
    "regime_at_entry",        # str  bull / bear / choppy / unknown
    "above200_at_entry",      # bool/null
    "sma200_rising_at_entry", # bool/null
    "vol_annual_at_entry",    # float/null  trailing-63d σ × √252
    "er_at_entry",            # float/null  Kaufman Efficiency Ratio (20-bar)
    "first_seen_asof",        # str  mtf asof when row first written
]

# Maturation columns — NULL until enough forward data, then filled once and frozen
_MATURATION_COLS = [
    "fwd_ret_20",   # float/null  close[t+20]/entry − 1
    "fwd_ret_60",
    "fwd_ret_180",
    "fwd_price_20", # float/null  close[t+20]
    "fwd_price_60",
    "fwd_price_180",
    "fwd_mdd_20",   # float/null  min(0, min(close[fill+1..fill+20])/entry − 1)  (≤0)  THE §3 METRIC
    "fwd_mdd_60",
    "fwd_mdd_180",
    "fwd_mdd_60_samebar",  # float/null  W1c shadow: the OLD same-bar-fill 60d MDD — for measuring the next-bar correction
    "fill_offset",  # int/null  bars from marker to fill (1 = honest next-bar; 0 = same-bar legacy/unfillable)
    "trade_mae",    # float/null  min(0, min(close[fill+1..exit])/entry − 1)  (≤0, trade-level §3-faithful)
    "outcome",      # str/null  win / loss / still_held
    "exit_date",    # str/null
    "exit_type",    # str/null  sell / cut
    "exit_price",   # float/null
    "trade_ret",    # float/null  exit_price/entry − 1  (secondary context, NOT the verdict)
    "last_backfill_asof",  # str/null  provenance: asof of run that last filled a mat. col
]

_ALL_COLS = _IDENTITY_COLS + _MATURATION_COLS
_KEY = ("ticker", "date", "type")

# Which marker types carry the buy-filter verdict
_ENTRY_TYPES = {"buy", "rebuy"}
_EXIT_TYPES  = {"sell", "cut"}
_FWD_HORIZONS = [20, 60, 180]


# ---------------------------------------------------------------------------
# Regime + archetype helpers  (all NO LOOK-AHEAD: use only data ≤ date)
# ---------------------------------------------------------------------------

def _snap_loc(close: pd.Series, date: str) -> int | None:
    """Integer iloc position of nearest prior bar (index ≤ date).  None if none."""
    dt = pd.Timestamp(date)
    lte = close.index <= dt
    if not lte.any():
        return None
    return int(np.searchsorted(close.index, dt, side="right") - 1)


def _regime_at(close: pd.Series, date: str) -> tuple[str, bool | None, bool | None]:
    """Compute regime using ONLY daily close data with index ≤ date.

    Returns (regime, above200, sma200_rising) where:
        regime  = 'bull' / 'bear' / 'choppy' / 'unknown'
        above200 = close > SMA200 as of date
        sma200_rising = SMA200[t] > SMA200[t-20] as of date

    bull   = above SMA200 AND SMA200 rising
    bear   = below SMA200 AND SMA200 falling
    choppy = mixed (one signal but not both)
    unknown = fewer than 200 bars of history through date
    """
    loc = _snap_loc(close, date)
    if loc is None:
        return "unknown", None, None

    # Use only data through 'date' (inclusive)
    sub = close.iloc[: loc + 1]

    if len(sub) < 200:
        return "unknown", None, None

    sma200 = sub.rolling(200).mean()
    sma200_now  = float(sma200.iloc[-1])
    sma200_prev = float(sma200.iloc[-21]) if len(sma200) >= 21 else float("nan")

    price_now = float(sub.iloc[-1])

    above200 = bool(price_now > sma200_now) if not np.isnan(sma200_now) else None
    rising   = (bool(sma200_now > sma200_prev)
                if (above200 is not None and not np.isnan(sma200_prev)) else None)

    if above200 is None or rising is None:
        return "unknown", above200, rising
    if above200 and rising:
        regime = "bull"
    elif (not above200) and (not rising):
        regime = "bear"
    else:
        regime = "choppy"

    return regime, above200, rising


def _vol_annual_at(close: pd.Series, date: str) -> float | None:
    """Trailing-63-day daily-return σ × √252 using only data ≤ date.  None if <64 bars."""
    loc = _snap_loc(close, date)
    if loc is None or loc < 63:
        return None
    sub = close.iloc[max(0, loc - 63): loc + 1]
    if len(sub) < 2:
        return None
    rets = sub.pct_change().dropna()
    if len(rets) < 2:
        return None
    return float(rets.std() * np.sqrt(252))


def _kaufman_er_at(close: pd.Series, date: str, n: int = 20) -> float | None:
    """Kaufman Efficiency Ratio (n-bar) using only data ≤ date.

    ER = |price_now - price_n_bars_ago| / sum(|daily_changes|)
    Returns None if fewer than n+1 bars available.
    """
    loc = _snap_loc(close, date)
    if loc is None or loc < n:
        return None
    sub = close.iloc[loc - n: loc + 1]  # n+1 points → n returns
    if len(sub) < n + 1:
        return None
    direction = abs(float(sub.iloc[-1]) - float(sub.iloc[0]))
    volatility = float((sub.diff().dropna().abs()).sum())
    if volatility == 0:
        return None
    return float(direction / volatility)


def _forward_metrics(
    close: pd.Series, entry_date: str, horizons: list[int]
) -> dict[str, Any]:
    """Fixed-horizon forward returns + drawdowns on the NEXT-BAR fill (W1c, audit #15).

    Routes through engine.grading.forward_metrics: entry = the bar STRICTLY AFTER the
    marker bar; the drawdown window is strictly forward of that fill. Returns the flat
    fwd_ret_{H}/fwd_price_{H}/fwd_mdd_{H} dict PLUS `fill_offset` and the shadow
    `fwd_mdd_60_samebar` (the old same-bar-fill 60d MDD) so the next-bar correction is
    measurable rather than hidden. Any horizon not yet matured is None.
    """
    m = grading.forward_metrics(close, entry_date, horizons=tuple(horizons))
    result: dict[str, Any] = {}
    for h in horizons:
        result[f"fwd_ret_{h}"]   = m.get(f"fwd_ret_{h}")
        result[f"fwd_price_{h}"] = m.get(f"fwd_price_{h}")
        result[f"fwd_mdd_{h}"]   = m.get(f"fwd_mdd_{h}")
    result["fill_offset"] = m.get("fill_offset")

    # shadow same-bar 60d MDD — the pre-W1c number, for the before/after audit only.
    if 60 in horizons:
        sb = grading.forward_metrics(close, entry_date, horizons=(60,), same_bar=True)
        result["fwd_mdd_60_samebar"] = sb.get("fwd_mdd_60")
    else:
        result["fwd_mdd_60_samebar"] = None
    return result


def _resolve_exit(
    markers: list[dict], entry_idx: int
) -> tuple[str | None, str | None]:
    """Find the first sell/cut marker after entry_idx in the marker list.

    Returns (exit_date, exit_type) or (None, None) if still open.
    """
    for m in markers[entry_idx + 1:]:
        if m.get("type") in _EXIT_TYPES:
            return m["date"], m["type"]
    return None, None


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _build_row(
    ticker: str,
    marker: dict,
    markers: list[dict],
    marker_idx: int,
    close: pd.Series,
    asof: str,
) -> dict[str, Any]:
    """Build a single track-record row dict from a marker.

    Entry-time features are computed no-look-ahead.  Maturation columns are left
    None here — they are filled separately during the maturation pass.
    """
    date = marker["date"]
    mtype = marker["type"]

    # NEXT-BAR fill (W1c): entry price = close of the bar STRICTLY AFTER the marker bar.
    # Falls back to the marker bar itself ONLY when there is no next bar yet (the fill has
    # not happened) — that row then carries entry NaN and stays un-matured, which is honest.
    fill = grading.fill_index(close, date)
    if fill is not None:
        entry_price = float(close.iloc[fill])
    else:
        loc = _snap_loc(close, date)
        entry_price = float(close.iloc[loc]) if loc is not None else float("nan")

    regime, above200, rising = _regime_at(close, date)
    vol_annual = _vol_annual_at(close, date)
    er = _kaufman_er_at(close, date)

    row: dict[str, Any] = {
        "ticker": ticker,
        "date": date,
        "type": mtype,
        "quality": marker.get("quality"),   # None for sell/cut
        "reason": marker.get("reason"),
        "entry_price": entry_price,
        "regime_at_entry": regime,
        "above200_at_entry": above200,
        "sma200_rising_at_entry": rising,
        "vol_annual_at_entry": vol_annual,
        "er_at_entry": er,
        "first_seen_asof": asof,
        # maturation — all None at birth
        "fwd_ret_20": None, "fwd_ret_60": None, "fwd_ret_180": None,
        "fwd_price_20": None, "fwd_price_60": None, "fwd_price_180": None,
        "fwd_mdd_20": None, "fwd_mdd_60": None, "fwd_mdd_180": None,
        "fwd_mdd_60_samebar": None, "fill_offset": None,
        "trade_mae": None, "outcome": None,
        "exit_date": None, "exit_type": None, "exit_price": None,
        "trade_ret": None,
        "last_backfill_asof": None,
    }
    return row


# ---------------------------------------------------------------------------
# Maturation filler — called on both new and existing rows
# ---------------------------------------------------------------------------

def _fill_maturation(
    row: dict[str, Any],
    markers: list[dict],
    marker_idx: int,
    close: pd.Series,
    asof: str,
) -> bool:
    """Fill any NULL maturation columns in-place.

    Returns True if at least one column was filled (so caller knows to set
    last_backfill_asof).

    Maturation discipline:
      * fwd_* / fixed-horizon columns are FROZEN first-observed — filled only when
        currently null, never overwritten (a horizon matures once and stays).
      * exit_* / trade_ret are frozen first-observed too.
      * `outcome` is the one provisional state: "still_held" is NOT final, so when an
        exit later appears it is resolved (overwritten) to win/loss and `trade_mae` is
        recomputed entry→exit.  win/loss are final.  This is the only post-birth
        overwrite, and it is a one-way resolution — so re-running on unchanged inputs
        is still a strict no-op (idempotent).
      * `outcome` (win/loss/still_held) is a MATURATION / EXCLUSION flag, NOT the
        verdict.  The verdict is drawdown (fwd_mdd_* / trade_mae) per CHARTER §3 — the
        audit uses outcome only to drop still_held rows and as a coverage count.

    entry-only metrics (trade_mae / outcome / exit_*) are only filled for buy/rebuy.
    sell/cut rows get all fwd_* columns too (for context) but no trade_* columns.
    """
    mtype = row["type"]
    date = row["date"]
    entry_price = row.get("entry_price")
    if _is_null(entry_price):
        return False

    entry_price_f = float(entry_price)
    filled = False

    def _freeze(key: str, value: Any) -> None:
        """Fill a frozen column only if currently null (first-observed wins)."""
        nonlocal filled
        if not _is_null(value) and _is_null(row.get(key)):
            row[key] = value
            filled = True

    # --- fixed-horizon forward metrics (frozen, NaN-aware) ---
    if any(_is_null(row.get(f"fwd_mdd_{h}")) for h in _FWD_HORIZONS):
        for k, v in _forward_metrics(close, date, _FWD_HORIZONS).items():
            _freeze(k, v)

    # --- trade-level metrics (entry markers only) ---
    if mtype in _ENTRY_TYPES:
        outcome = row.get("outcome")
        provisional = _is_null(outcome) or outcome == "still_held"
        if provisional:
            # NEXT-BAR fill (W1c): entry = the bar AFTER the marker, EXIT = the bar AFTER
            # the sell/cut marker — symmetric with the forward-metric convention. entry_price_f
            # is already the fill-bar price, so the MAE window / trade_ret are measured from it.
            loc_entry = grading.fill_index(close, date)
            exit_date, exit_type = _resolve_exit(markers, marker_idx)
            loc_exit = grading.fill_index(close, exit_date) if exit_date is not None else None

            if loc_entry is not None and loc_exit is not None and loc_exit > loc_entry:
                # Closed trade — final MAE/outcome (resolves any provisional still_held).
                # Window is strictly forward of the entry fill: [fill+1 .. exit_fill].
                window = close.iloc[loc_entry + 1: loc_exit + 1]
                exit_price = float(close.iloc[loc_exit])
                if len(window) > 0:
                    new_mae = min(0.0, float(window.min()) / entry_price_f - 1.0)
                    if _is_null(row.get("trade_mae")) or row.get("outcome") == "still_held":
                        row["trade_mae"] = new_mae
                        filled = True
                _freeze("exit_date", exit_date)
                _freeze("exit_type", exit_type)
                _freeze("exit_price", exit_price)
                _freeze("trade_ret", exit_price / entry_price_f - 1.0)
                new_outcome = "win" if exit_price >= entry_price_f else "loss"
                if row.get("outcome") != new_outcome:
                    row["outcome"] = new_outcome
                    filled = True
            elif loc_entry is not None and _is_null(row.get("outcome")):
                # Open (no priced exit yet) — provisional still_held; freeze a
                # first-window MAE (the audit excludes still_held from trade_mae, so it
                # is held frozen until an exit resolves it rather than re-extended).
                if len(close) - 1 > loc_entry:
                    fwd_open = close.iloc[loc_entry + 1:]
                    if len(fwd_open) > 0:
                        _freeze("trade_mae", min(0.0, float(fwd_open.min()) / entry_price_f - 1.0))
                    row["outcome"] = "still_held"
                    filled = True

    if filled:
        row["last_backfill_asof"] = asof

    return filled


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _empty_df() -> pd.DataFrame:
    """Return an empty DataFrame with the full schema."""
    return pd.DataFrame(columns=_ALL_COLS)


def _read_existing(out_path: Path) -> pd.DataFrame:
    """Read existing parquet or return empty DataFrame.  Safe if file absent."""
    if not out_path.exists():
        return _empty_df()
    try:
        df = pd.read_parquet(out_path)
        # Ensure all schema columns present (schema evolution guard)
        for col in _ALL_COLS:
            if col not in df.columns:
                df[col] = None
        return df[_ALL_COLS]
    except Exception as exc:
        logger.warning("Could not read existing track_record.parquet: %s — starting fresh", exc)
        return _empty_df()


def _write_parquet(df: pd.DataFrame, out_path: Path) -> None:
    """Write DataFrame to parquet via pyarrow (preserves None as null)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df[_ALL_COLS], preserve_index=False)
    pq.write_table(table, str(out_path))


def _key_tuple(row_or_dict) -> tuple:
    """Return (ticker, date, type) key."""
    if isinstance(row_or_dict, dict):
        return (row_or_dict["ticker"], row_or_dict["date"], row_or_dict["type"])
    return (row_or_dict["ticker"], row_or_dict["date"], row_or_dict["type"])


# ---------------------------------------------------------------------------
# Signal files reader
# ---------------------------------------------------------------------------

def _iter_marker_files(signals_dir: Path):
    """Yield (ticker, markers_list) for every signal JSON in signals_dir."""
    for fp in sorted(signals_dir.glob("*.json")):
        ticker = fp.stem
        try:
            doc = json.loads(fp.read_text())
        except Exception as exc:
            logger.debug("Skipping %s: %s", fp.name, exc)
            continue
        markers = doc.get("markers") or []
        if markers:
            yield ticker, markers


def _load_asof(mtf_path: Path, asof_override: str | None) -> str:
    """Load asof from mtf_signals_latest.json or use the override."""
    if asof_override:
        return asof_override
    try:
        doc = json.loads(mtf_path.read_text())
        return str(doc.get("asof", ""))
    except Exception as exc:
        logger.warning("Could not read mtf_path %s: %s — using empty asof", mtf_path, exc)
        return ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def update_track_record(
    repo_root: str | Path | None = None,
    signals_dir: str | Path | None = None,
    mtf_path: str | Path | None = None,
    stocks_dir: str | Path | None = None,
    out_path: str | Path | None = None,
    asof: str | None = None,
) -> dict:
    """Append-only, idempotent track-record logger.

    Parameters
    ----------
    repo_root : path to the repo root; default = two directories above this file.
    signals_dir : path to site/signals/*.json  (per-ticker chart markers).
    mtf_path : path to data/signal_archive/mtf_signals_latest.json.
    stocks_dir : path to data/stocks/*.parquet.
    out_path : output parquet path.
    asof : override for the run's as-of string; default = mtf leaf's 'asof'.

    Returns
    -------
    dict with keys: new_rows, matured_rows, total_rows, skipped_pending, out_path.
    """
    # --- resolve paths ---
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    repo_root = Path(repo_root)

    if signals_dir is None:
        signals_dir = repo_root / "site" / "signals"
    if mtf_path is None:
        mtf_path = repo_root / "data" / "signal_archive" / "mtf_signals_latest.json"
    if stocks_dir is None:
        stocks_dir = repo_root / "data" / "stocks"
    if out_path is None:
        out_path = repo_root / "data" / "signal_archive" / "track_record.parquet"

    signals_dir = Path(signals_dir)
    mtf_path    = Path(mtf_path)
    stocks_dir  = Path(stocks_dir)
    out_path    = Path(out_path)

    # --- resolve asof (NEVER use wall-clock) ---
    run_asof = _load_asof(mtf_path, asof)

    # --- load existing parquet ---
    existing = _read_existing(out_path)

    # Build a mutable dict keyed by (ticker, date, type) for O(1) lookup.
    # Each value is a row dict.  We preserve insertion order (first-observed wins).
    existing_keys: dict[tuple, dict] = {}
    for _, row in existing.iterrows():
        key = (str(row["ticker"]), str(row["date"]), str(row["type"]))
        existing_keys[key] = row.to_dict()

    new_rows: list[dict] = []
    skipped_pending = 0
    matured_rows = 0

    # dead-name terminal store (8-K Item 1.03 bankruptcy imputation) — a name that
    # delisted mid-horizon still grades at its loss instead of vanishing (W1c, audit #15).
    try:
        dead_prices = grading.load_dead_prices()
    except Exception:  # noqa: BLE001 — additive, never fatal
        dead_prices = {}

    # --- process each ticker's signal file ---
    for ticker, markers in _iter_marker_files(signals_dir):
        # Load daily close for this ticker (skip gracefully if absent).
        # NOTE: this `close` is split- AND dividend-back-adjusted total-return (see the
        # module docstring's price-store caveat) — leak-neutral for splits, small
        # dividend residual on forward drawdowns. Not point-in-time.
        stock_fp = stocks_dir / f"{ticker}.parquet"
        try:
            close = pd.read_parquet(stock_fp)["close"].dropna()
            close = close.sort_index()
        except Exception:
            close = None
        # extend with (or fall back to) the dead-name terminal series so a delisting is
        # graded as a loss rather than dropping the row silently.
        close = grading.resolve_series(ticker, close, dead_prices=dead_prices)
        if close is None or close.empty:
            logger.debug("No price data for %s — skipping", ticker)
            continue

        for idx, marker in enumerate(markers):
            mtype   = marker.get("type", "")
            quality = marker.get("quality")

            # --- skip rules (CHARTER) ---
            # risk_flags is a separate date list on the doc, never a marker type → ignore
            # pending quality on buy/rebuy → skip (repaint bait)
            if mtype in _ENTRY_TYPES and quality == "pending":
                skipped_pending += 1
                continue

            # Only log: buy/rebuy (quality=take/block) and sell/cut
            if mtype not in (_ENTRY_TYPES | _EXIT_TYPES):
                continue

            key = (ticker, marker["date"], mtype)

            if key in existing_keys:
                # Row already exists — fill NULL maturation columns only
                row = existing_keys[key]
                changed = _fill_maturation(row, markers, idx, close, run_asof)
                if changed:
                    matured_rows += 1
            else:
                # New row — build identity + entry-time features + attempt maturation
                row = _build_row(ticker, marker, markers, idx, close, run_asof)
                _fill_maturation(row, markers, idx, close, run_asof)
                existing_keys[key] = row
                new_rows.append(row)

    # --- assemble final DataFrame ---
    all_rows = list(existing_keys.values())
    if not all_rows:
        out_df = _empty_df()
    else:
        out_df = pd.DataFrame(all_rows, columns=_ALL_COLS)

    # --- write ---
    _write_parquet(out_df, out_path)

    return {
        "new_rows": len(new_rows),
        "matured_rows": matured_rows,
        "total_rows": len(out_df),
        "skipped_pending": skipped_pending,
        "out_path": str(out_path),
    }
