"""engine.marketing.hot_tape_pack — Nightly context pack for the Hot Tape radar.

Implements research/MARKETING_HOT_TAPE_MASTERPLAN.md §3.1: "heavy compute
nightly, light joins intraday". For every liquid name in the daily-bar stores
this precomputes the stat kit the §2.D devices need (streak rarity, ATH/52w
distance, biggest 1d/5d moves with dates, MA stack, Wilder RSI plus the last
date at each extreme, adjacent round numbers, correction/bear thresholds,
mcap/shares for the dollar translation, earnings date) into ONE compact JSON
that the radar reads with the json module alone - no pandas on the intraday
path, which is what keeps the 5-minute loop inside a shallow ubuntu checkout.

FRESHEST SOURCE PER TICKER (:data:`PRICE_STORES`). The scan is a union over
``data/baskets/ohlcv`` (2,758 curated names, real opens), ``data/stocks`` (232
large caps) and ``data/massive_stock_day`` (~20k, the wide tail), and for each
ticker it keeps the store whose LAST BAR IS NEWEST - ties broken in that same
priority order. This is not a nicety: on 2026-07-28 the massive store was 18
sessions stale while both curated trees were current, so scanning massive alone
stamped the whole pack trade_date 2026-07-02, ``bridge_ok`` came back False, and
the entire §2.D device library was suppressed for exactly the attention names
the program exists to post about.

Three honesty guards are baked into the scan, all learned from these stores:

* **Dead records.** A ticker whose freshest bar still lags the pack's own tip by
  more than ``universe.max_lag_weekdays`` weekdays is dropped from the universe
  rather than carried as a laggard. That is also what removes Polygon's
  ZAZZT-class test symbols - one of which ranked adv_rank 1 in the shipped pack
  on a $615B fake ADV - belt-and-braces with a name filter in the scan itself.

* **Dense window.** Early history (2021-2024) has multi-month holes. Every
  history-scan fact is computed only from ``history_start``, the earliest date
  after which no gap exceeds 7 consecutive missing weekdays, and every record
  carries ``window_start`` so the copy layer can say "since at least <month>"
  instead of implying a longer memory than we have.
* **Split suspicion.** ``data/massive_stock_day`` is NOT split-adjusted. Any
  adjacent close-to-close move beyond +/-60% inside the dense window sets
  ``suspect``; the detectors then skip that ticker's history facts entirely
  rather than reporting a 3-for-1 split as a 66% crash, and the radar refuses
  to draw a card off that store for a suspect name (a split-cliff candle is a
  lie-shaped picture).

Run: ``python -m engine.marketing.hot_tape_pack``. Never raises, always exits
0, and reports failure as a GitHub annotation (bare print, never a logger).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_ID = "marketing.hot_tape_pack/v1"

STORE_REL = "data/massive_stock_day"
#: Daily-bar stores scanned, in TIE-BREAK priority order (a curated tree's bars
#: are the ones the rest of the pipeline reasons about, and the baskets tree is
#: the only one with a real `open` column). Recency wins over priority: the
#: freshest last bar takes the ticker, and priority only settles a tie.
PRICE_STORES: tuple[str, ...] = ("data/baskets/ohlcv", "data/stocks", STORE_REL)
REFERENCE_REL = "data/polygon_universe/reference.parquet"
EARNINGS_REL = "data/earnings/earnings.parquet"
HEATMAP_REL = "site/marketdata/sp500_heatmap.json"
OUT_REL = "data/marketing/hot_tape_pack.json"

#: A gap longer than this many consecutive missing weekdays ends the dense window.
MAX_GAP_WEEKDAYS = 7
#: An adjacent close-to-close move beyond this is a split, not a price move.
SPLIT_SUSPECT_PCT = 60.0
#: Hard wall-clock budget; a partial pack beats a missed nightly step. 240s, not
#: 480: a full three-store scan measures well under a minute at 4 workers, so
#: this is ~6x head-room and still far inside the nightly step's own timeout.
DEFAULT_BUDGET_S = 4 * 60
DEFAULT_WORKERS = 4
#: A record this many weekdays behind the pack tip is dead, not lagging.
DEFAULT_MAX_LAG_WEEKDAYS = 10
RSI_PERIOD = 14

#: Polygon ships synthetic test tickers shaped Z?ZZT (ZAZZT, ZVZZT, ZWZZT, ...)
#: with fabricated prices and volume. ZAZZT ranked adv_rank 1 in the shipped
#: pack on a $615B "ADV" off 30 bars that ended 2025-06-30. They are excluded by
#: NAME as well as by the staleness prune, because a fresh one would rank first.
_TEST_SYMBOL_RE = re.compile(r"^Z[A-Z]ZZT$")


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers (no pandas)
# ─────────────────────────────────────────────────────────────────────────────

def _r(v: Any, places: int) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f or abs(f) == float("inf"):
            return None
        return round(f, places)
    except Exception:  # noqa: BLE001
        return None


def _i(v: Any) -> int | None:
    try:
        if v is None:
            return None
        f = float(v)
        if f != f or abs(f) == float("inf"):
            return None
        return int(round(f))
    except Exception:  # noqa: BLE001
        return None


def round_levels(price: float) -> tuple[float | None, float | None]:
    """Nearest round levels below and above `price` (step scales with price)."""
    try:
        p = float(price)
        if p <= 0:
            return (None, None)
        if p < 50:
            step = 5.0
        elif p < 200:
            step = 10.0
        elif p < 500:
            step = 25.0
        elif p < 1000:
            step = 50.0
        elif p < 5000:
            step = 100.0
        else:
            step = 500.0
        below = (int(p / step)) * step
        if below >= p:
            below -= step
        above = below + step
        if above <= p:
            above += step
        return (round(below, 4) if below > 0 else None, round(above, 4))
    except Exception:  # noqa: BLE001
        return (None, None)


def _weekday_lag(older: Any, newer: Any) -> int | None:
    """Weekdays strictly after `older` up to and including `newer`. None on junk.

    Mirrors hot_tape._weekdays_between; kept local so this module stays free of
    an engine-sibling import at scan time.
    """
    try:
        a, b = date.fromisoformat(str(older)[:10]), date.fromisoformat(str(newer)[:10])
    except Exception:  # noqa: BLE001
        return None
    if b <= a:
        return 0
    n, cursor = 0, a + timedelta(days=1)
    while cursor <= b:
        if cursor.weekday() < 5:
            n += 1
        cursor += timedelta(days=1)
        if n > 500:                     # runaway guard on a nonsense date
            break
    return n


def _load_json(path: Path) -> dict | None:
    try:
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_pack: unreadable %s (%s)", path, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Per-ticker scan (runs in a worker process; pandas imported here, not at top)
# ─────────────────────────────────────────────────────────────────────────────

def _wilder_rsi(closes):
    """Classic Wilder RSI: SMA seed then the recursive average. Returns arrays.

    (rsi, avg_gain, avg_loss) each aligned to closes[1:], NaN before the seed.
    """
    import numpy as np  # noqa: PLC0415

    delta = np.diff(closes)
    n = len(delta)
    if n < RSI_PERIOD:
        return None, None, None
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_g = np.full(n, np.nan)
    avg_l = np.full(n, np.nan)
    avg_g[RSI_PERIOD - 1] = gains[:RSI_PERIOD].mean()
    avg_l[RSI_PERIOD - 1] = losses[:RSI_PERIOD].mean()
    for i in range(RSI_PERIOD, n):
        avg_g[i] = (avg_g[i - 1] * (RSI_PERIOD - 1) + gains[i]) / RSI_PERIOD
        avg_l[i] = (avg_l[i - 1] * (RSI_PERIOD - 1) + losses[i]) / RSI_PERIOD
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_g / avg_l
        rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = np.where((avg_l == 0) & (avg_g > 0), 100.0, rsi)
    return rsi, avg_g, avg_l


def _last_true_before_tail(mask) -> int | None:
    """Index of the last True, skipping the trailing contiguous True run.

    "RSI is back under 30 for the first time since X" is only true if X is the
    previous EPISODE, not yesterday of the episode we are already in.
    """
    import numpy as np  # noqa: PLC0415

    idx = len(mask) - 1
    while idx >= 0 and bool(mask[idx]):
        idx -= 1
    if idx < 0:
        return None
    hits = np.nonzero(mask[: idx + 1])[0]
    return int(hits[-1]) if len(hits) else None


def _normalize_frame(df) -> Any:
    """A sorted, de-duplicated DatetimeIndex frame carrying `close`, or None.

    The three stores disagree on shape: ``data/massive_stock_day`` names its
    index "date" and carries open+transactions, the curated trees name it "Date"
    and ``data/stocks`` has no ``open`` at all. Only ``close`` (every stat) and
    ``volume`` (the ADV floor) are actually read here, so those are the only
    columns normalized; a missing ``volume`` degrades to an ADV of 0 rather than
    losing the record.
    """
    import pandas as pd  # noqa: PLC0415

    if df is None or len(df) < 2:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        for col in ("date", "Date", "timestamp", "index"):
            if col in df.columns:
                df = df.set_index(col)
                break
    try:
        df.index = pd.to_datetime(df.index)
    except Exception:  # noqa: BLE001
        return None
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if "close" not in df.columns or len(df) < 2:
        return None
    return df


def scan_ticker(args: tuple) -> dict | None:
    """Read one ticker's FRESHEST daily-bar parquet and compute its record.

    args = (ticker, [candidate paths in PRICE_STORES priority order],
    min_adv_dollars, always_keep). Every candidate is read and the one whose
    LAST BAR IS NEWEST wins (ties settle on the given order) - the store that
    is current for this name, not the store that happens to be listed first.
    Returns a record dict, a light {"ticker", "adv20_dollars", "skip": True}
    below the liquidity floor, or {"ticker", "error": ...} when no candidate is
    readable. Worker entry point; never raises.
    """
    ticker_s, paths_in, min_adv, always_keep = args
    paths = [Path(p) for p in ([paths_in] if isinstance(paths_in, (str, Path))
                               else list(paths_in))]
    ticker = str(ticker_s or (paths[0].stem if paths else "")).upper()
    try:
        import numpy as np  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415

        df = None
        best_tip: str | None = None
        errors = 0
        for candidate in paths:
            try:
                frame = _normalize_frame(pd.read_parquet(candidate))
            except Exception:  # noqa: BLE001
                errors += 1
                continue
            if frame is None:
                continue
            tip = str(frame.index[-1].date())
            if best_tip is None or tip > best_tip:
                df, best_tip = frame, tip
        if df is None:
            if errors and errors == len(paths):
                return {"ticker": ticker, "error": "no readable parquet"}
            return {"ticker": ticker, "skip": True, "adv20_dollars": None}

        close_all = df["close"].astype(float)
        volume_all = (df["volume"].astype(float) if "volume" in df.columns
                      else pd.Series(0.0, index=df.index))
        adv20 = float((close_all * volume_all).tail(20).mean())
        if adv20 != adv20:
            adv20 = 0.0
        if adv20 < float(min_adv) and not always_keep:
            return {"ticker": ticker, "skip": True, "adv20_dollars": round(adv20, 2)}

        # Dense window: cut at the last gap longer than MAX_GAP_WEEKDAYS.
        days = df.index.to_numpy().astype("datetime64[D]")
        start_pos = 0
        if len(days) > 1:
            gaps = np.busday_count(days[:-1] + np.timedelta64(1, "D"), days[1:])
            bad = np.nonzero(gaps > MAX_GAP_WEEKDAYS)[0]
            if len(bad):
                start_pos = int(bad[-1]) + 1
        dense = df.iloc[start_pos:]
        if len(dense) < 2:
            dense = df.iloc[-2:]
        close = dense["close"].astype(float)
        arr = close.to_numpy(dtype=float)
        dates = list(dense.index.strftime("%Y-%m-%d"))
        window_start = dates[0]

        pct_change = np.diff(arr) / arr[:-1] * 100.0
        suspect = bool(np.any(np.abs(pct_change) > SPLIT_SUSPECT_PCT))

        last_close = float(arr[-1])
        prev_close = float(arr[-2])

        # Streak + rarity ------------------------------------------------
        signs = np.sign(np.diff(arr)).astype(int)
        streak: dict[str, Any] = {"dir": "flat", "len": 0, "last_run_ge": {}}
        if len(signs):
            boundaries = np.nonzero(np.diff(signs) != 0)[0] + 1
            starts = np.concatenate(([0], boundaries))
            ends = np.concatenate((boundaries, [len(signs)]))
            lengths = (ends - starts).astype(int)
            run_signs = signs[starts]
            cur_sign = int(run_signs[-1])
            cur_len = int(lengths[-1])
            direction = "up" if cur_sign > 0 else ("down" if cur_sign < 0 else "flat")
            last_run_ge: dict[str, Any] = {}
            if direction != "flat":
                for k in range(cur_len + 1, cur_len + 5):
                    hit = None
                    for j in range(len(lengths) - 2, -1, -1):
                        if int(run_signs[j]) == cur_sign and int(lengths[j]) >= k:
                            hit = dates[int(ends[j])]
                            break
                    last_run_ge[str(k)] = hit
            streak = {"dir": direction, "len": cur_len if direction != "flat" else 0,
                      "last_run_ge": last_run_ge}

        # Extremes -------------------------------------------------------
        ath_pos = int(np.argmax(arr))
        ath = float(arr[ath_pos])
        year_mask = np.array(dates) >= (dense.index[-1] - pd.Timedelta(days=365)).date().isoformat()
        y_idx = np.nonzero(year_mask)[0]
        if len(y_idx) < 2:
            y_idx = np.arange(len(arr))
        y_arr = arr[y_idx]
        hi_pos, lo_pos = int(np.argmax(y_arr)), int(np.argmin(y_arr))

        # Moving averages ------------------------------------------------
        def _ma(n: int) -> float | None:
            return float(close.tail(n).mean()) if len(close) >= n else None

        # Wilder RSI -----------------------------------------------------
        rsi, avg_g, avg_l = _wilder_rsi(arr)
        rsi14 = rsi_ag = rsi_al = None
        rsi_low = rsi_low_date = rsi_high = rsi_high_date = None
        last_le_30 = last_ge_70 = None
        if rsi is not None:
            rsi_dates = dates[1:]
            valid = np.nonzero(~np.isnan(rsi))[0]
            if len(valid):
                rsi14 = float(rsi[valid[-1]])
                rsi_ag, rsi_al = float(avg_g[valid[-1]]), float(avg_l[valid[-1]])
                cutoff = (dense.index[-1] - pd.Timedelta(days=365)).date().isoformat()
                win = [i for i in valid if rsi_dates[i] >= cutoff] or list(valid)
                w_vals = np.array([rsi[i] for i in win])
                rsi_low = float(w_vals.min())
                rsi_low_date = rsi_dates[win[int(np.argmin(w_vals))]]
                rsi_high = float(w_vals.max())
                rsi_high_date = rsi_dates[win[int(np.argmax(w_vals))]]
                filled = np.nan_to_num(rsi, nan=50.0)
                p = _last_true_before_tail(filled <= 30.0)
                last_le_30 = rsi_dates[p] if p is not None else None
                p = _last_true_before_tail(filled >= 70.0)
                last_ge_70 = rsi_dates[p] if p is not None else None

        # Biggest 1d / 5d moves inside the last year ---------------------
        def _extreme(step: int, biggest_up: bool) -> dict[str, Any] | None:
            if len(y_idx) <= step:
                return None
            sub = arr[y_idx]
            sub_dates = [dates[i] for i in y_idx]
            moves = (sub[step:] - sub[:-step]) / sub[:-step] * 100.0
            if not len(moves):
                return None
            pos = int(np.argmax(moves)) if biggest_up else int(np.argmin(moves))
            return {"pct": _r(moves[pos], 2), "date": sub_dates[pos + step]}

        below, above = round_levels(last_close)

        return {
            "ticker": ticker,
            "last_date": dates[-1],
            "last_close": _r(last_close, 4),
            "prev_close": _r(prev_close, 4),
            "streak": streak,
            "ath": _r(ath, 4),
            "ath_date": dates[ath_pos],
            "high_52w": _r(y_arr[hi_pos], 4),
            "high_52w_date": dates[int(y_idx[hi_pos])],
            "low_52w": _r(y_arr[lo_pos], 4),
            "low_52w_date": dates[int(y_idx[lo_pos])],
            "pct_from_ath": _r((last_close - ath) / ath * 100.0, 2) if ath else None,
            "ma20": _r(_ma(20), 4),
            "ma50": _r(_ma(50), 4),
            "ma200": _r(_ma(200), 4),
            "rsi14": _r(rsi14, 2),
            "rsi_avg_gain": _r(rsi_ag, 6),
            "rsi_avg_loss": _r(rsi_al, 6),
            "rsi_low_1y": _r(rsi_low, 2),
            "rsi_low_1y_date": rsi_low_date,
            "rsi_high_1y": _r(rsi_high, 2),
            "rsi_high_1y_date": rsi_high_date,
            "last_rsi_le_30": last_le_30,
            "last_rsi_ge_70": last_ge_70,
            "max_up_1d": _extreme(1, True),
            "max_dn_1d": _extreme(1, False),
            "max_up_5d": _extreme(5, True),
            "max_dn_5d": _extreme(5, False),
            "round_above": _r(above, 4),
            "round_below": _r(below, 4),
            "px_correction": _r(ath * 0.9, 4) if ath else None,
            "px_bear": _r(ath * 0.8, 4) if ath else None,
            "adv20_dollars": _r(adv20, 2),
            "adv_rank": None,
            "mcap_usd": None,
            "shares_est": None,
            "sector": None,
            "sp500": False,
            "earn_next_date": None,
            "earn_next_time": None,
            "window_start": window_start,
            "suspect": suspect,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ticker": ticker, "error": str(exc)[:160]}


# ─────────────────────────────────────────────────────────────────────────────
# Joins
# ─────────────────────────────────────────────────────────────────────────────

def _heatmap_view(root: Path) -> tuple[dict[str, dict], str | None]:
    """{TICKER: {sector, name}} plus the heatmap's asof."""
    obj = _load_json(root / HEATMAP_REL) or {}
    out: dict[str, dict] = {}
    for tile in (obj.get("tiles") or []):
        if not isinstance(tile, dict):
            continue
        sym = str(tile.get("t") or "").upper()
        if sym:
            out[sym] = {"sector": tile.get("sector"), "name": tile.get("name")}
    return out, obj.get("asof")


def _reference_view(root: Path) -> tuple[dict[str, float], str | None]:
    """{TICKER: market_cap_usd} plus the reference asof. Empty on any failure."""
    try:
        import pandas as pd  # noqa: PLC0415

        path = root / REFERENCE_REL
        if not path.exists():
            return {}, None
        df = pd.read_parquet(path)
        asof = None
        if "asof" in df.columns and len(df):
            asof = str(df["asof"].astype(str).max())
        if "market_cap_usd" not in df.columns:
            return {}, asof
        out = {}
        for tkr, val in df["market_cap_usd"].items():
            try:
                f = float(val)
            except Exception:  # noqa: BLE001
                continue
            if f == f and f > 0:
                out[str(tkr).upper()] = f
        return out, asof
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_pack: reference join failed: %s", exc)
        return {}, None


def _earnings_view(root: Path) -> tuple[dict[str, dict], str | None]:
    """{TICKER: {next_date, next_time}} plus the earnings asof."""
    try:
        import pandas as pd  # noqa: PLC0415

        path = root / EARNINGS_REL
        if not path.exists():
            return {}, None
        df = pd.read_parquet(path)
        asof = None
        if "as_of" in df.columns and len(df):
            asof = str(df["as_of"].astype(str).max())
        if "next_date" not in df.columns:
            return {}, asof
        has_time = "next_time" in df.columns
        out: dict[str, dict] = {}
        for i, tkr in enumerate(df.index.astype(str)):
            nd = df["next_date"].iloc[i]
            out[str(tkr).upper()] = {
                "next_date": None if nd is None or str(nd) == "nan" else str(nd)[:10],
                "next_time": str(df["next_time"].iloc[i]) if has_time else None,
            }
        return out, asof
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_pack: earnings join failed: %s", exc)
        return {}, None


# ─────────────────────────────────────────────────────────────────────────────
# Pack build
# ─────────────────────────────────────────────────────────────────────────────

def store_universe(root: Path | str) -> dict[str, list[Path]]:
    """{TICKER: [candidate parquets, PRICE_STORES priority order]} across stores.

    The UNION, not the first store that has the name: a ticker in two trees gets
    both paths and :func:`scan_ticker` picks whichever is actually current.
    Manifest/state files (``_*.parquet``) and Polygon's Z?ZZT test symbols are
    excluded here so they never reach a worker.
    """
    out: dict[str, list[Path]] = {}
    for sub in PRICE_STORES:
        d = Path(root) / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.parquet")):
            if p.name.startswith("_"):
                continue
            ticker = p.stem.upper()
            if _TEST_SYMBOL_RE.match(ticker):
                continue
            out.setdefault(ticker, []).append(p)
    return out


def build_pack(
    root: Path | str,
    *,
    cfg: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Scan the daily stores and return the context pack. Never raises."""
    started = time.time()
    r = Path(root)
    universe = ((cfg or {}).get("universe") or {}) if isinstance(cfg, dict) else {}
    min_adv = float(universe.get("min_adv_dollars", 25_000_000))
    max_tickers = int(universe.get("max_tickers", 3000))
    workers = int(universe.get("workers", DEFAULT_WORKERS))
    budget_s = float(universe.get("budget_s", DEFAULT_BUDGET_S))
    max_lag = int(universe.get("max_lag_weekdays", DEFAULT_MAX_LAG_WEEKDAYS))
    ts = (now or datetime.now(timezone.utc))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    candidates = store_universe(r)
    files = [p for paths in candidates.values() for p in paths]
    if not files:
        # Fresh checkout / CI: the stores are nightly-host artifacts, not tracked.
        return {"error": "store absent", "schema": SCHEMA_ID,
                "built_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "tickers": {}}

    heat, heat_asof = _heatmap_view(r)
    always = set(heat)
    tasks = [(ticker, [str(p) for p in paths], min_adv, ticker in always)
             for ticker, paths in sorted(candidates.items())]

    records: dict[str, dict] = {}
    n_errors = 0
    truncated = False
    try:
        if workers and workers > 1:
            from concurrent.futures import ProcessPoolExecutor, as_completed  # noqa: PLC0415

            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(scan_ticker, t): t[0] for t in tasks}
                for fut in as_completed(futures):
                    rec = fut.result()
                    if rec is None:
                        continue
                    if rec.get("error"):
                        n_errors += 1
                    elif not rec.get("skip"):
                        records[rec["ticker"]] = rec
                    if time.time() - started > budget_s:
                        truncated = True
                        for pending in futures:
                            pending.cancel()
                        break
        else:
            for task in tasks:
                rec = scan_ticker(task)
                if rec is None:
                    continue
                if rec.get("error"):
                    n_errors += 1
                elif not rec.get("skip"):
                    records[rec["ticker"]] = rec
                if time.time() - started > budget_s:
                    truncated = True
                    break
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_pack: scan failed: %s", exc)

    # A store with thousands of files that yielded ZERO records is a broken
    # scan (e.g. the process pool died), not an empty market. Writing a hollow
    # pack here would silently disable every pack-dependent detector for a
    # day while looking perfectly healthy — the degraded-ships-confident
    # class. Fail loudly instead; the previous night's pack stays in place.
    if files and not records:
        print("::warning title=hot_tape_pack::scan yielded 0 records from "
              f"{len(files)} parquet files — refusing to write a hollow pack",
              flush=True)
        return {"error": f"scan yielded 0 records from {len(files)} files",
                "schema": SCHEMA_ID, "tickers": {}}

    # PRUNE DEAD RECORDS BEFORE RANKING. A name whose freshest bar still lags
    # the pack tip by more than max_lag weekdays cannot produce an honest
    # history fact, and leaving it in poisons the rank: ZAZZT held adv_rank 1 in
    # the shipped pack on a $615B "ADV" computed off 30 fabricated bars that
    # stopped in June 2025. Ranking after the prune also keeps adv_rank dense.
    trade_date = max((rec.get("last_date") or "" for rec in records.values()),
                     default=None) or None
    n_stale = 0
    if trade_date and max_lag >= 0:
        for sym in [s for s in records
                    if (_weekday_lag(records[s].get("last_date"), trade_date) or 0) > max_lag]:
            records.pop(sym, None)
            n_stale += 1

    # Liquidity rank, then the max_tickers cut (heatmap names are never cut).
    ranked = sorted(records.values(),
                    key=lambda x: (-(x.get("adv20_dollars") or 0.0), x["ticker"]))
    kept: dict[str, dict] = {}
    for pos, rec in enumerate(ranked, start=1):
        rec["adv_rank"] = pos
        if pos <= max_tickers or rec["ticker"] in always:
            kept[rec["ticker"]] = rec

    mcaps, mcap_asof = _reference_view(r)
    earnings, earn_asof = _earnings_view(r)
    for sym, rec in kept.items():
        tile = heat.get(sym)
        if tile:
            rec["sector"] = tile.get("sector")
            rec["sp500"] = True
        mcap = mcaps.get(sym)
        if mcap is not None:
            # mcap_usd is honest on its own asof and always carried.
            rec["mcap_usd"] = _i(mcap)
            last = rec.get("last_close")
            # SHARES ONLY WHEN THE TWO DATES AGREE (reviewer C1). shares =
            # mcap / close is a valid identity only if the market cap and the
            # close are from the SAME session. Dividing a 2026-07-27 reference
            # cap by a 2026-07-02 close inflated JPM's share count 6.5% and the
            # mcap-milestone detector then manufactured a "$JPM just crossed $1
            # trillion" post at an actual $942B. No alignment, no share count -
            # and the milestone branch dies with it, by design.
            if last and mcap_asof and rec.get("last_date") == str(mcap_asof)[:10]:
                rec["shares_est"] = _i(mcap / float(last))
        earn = earnings.get(sym)
        if earn:
            rec["earn_next_date"] = earn.get("next_date")
            rec["earn_next_time"] = earn.get("next_time")

    trade_date = max((rec.get("last_date") or "" for rec in kept.values()), default=None)
    pack = {
        "schema": SCHEMA_ID,
        "built_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trade_date": trade_date or None,
        "n_tickers": len(kept),
        "sources": {
            "store_last_date": trade_date or None,
            "mcap_asof": mcap_asof,
            "earnings_asof": earn_asof,
            "heatmap_asof": heat_asof,
        },
        "tickers": kept,
    }
    if truncated:
        pack["truncated"] = True
        print("::warning title=hot-tape-pack::scan hit the "
              f"{int(budget_s)}s budget - wrote a partial pack "
              f"({len(kept)} tickers)", flush=True)
    if n_errors:
        log.warning("hot_tape_pack: %d unreadable parquet file(s) skipped", n_errors)
    if n_stale:
        log.info("hot_tape_pack: dropped %d record(s) lagging the %s tip by "
                 "more than %d weekdays", n_stale, trade_date, max_lag)
    log.info("hot_tape_pack: %d tickers from %d candidate file(s) in %.1fs (tip %s)",
             len(kept), len(files), time.time() - started, trade_date)
    return pack


def write_pack(
    root: Path | str,
    *,
    cfg: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Build and atomically write the pack. {path, n_tickers, elapsed_s} or {error}."""
    started = time.time()
    try:
        pack = build_pack(root, cfg=cfg, now=now)
        if pack.get("error"):
            return {"error": str(pack["error"])}
        out = Path(root) / OUT_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_text(
            json.dumps(pack, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(out)
        return {"path": str(out), "n_tickers": pack.get("n_tickers", 0),
                "elapsed_s": round(time.time() - started, 2)}
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape_pack.write_pack failed: %s", exc)
        return {"error": str(exc)[:200]}


def main() -> int:
    """Nightly entry point. Never raises, always exits 0."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        from engine.marketing.hot_tape import load_config  # noqa: PLC0415

        root = Path(__file__).resolve().parents[2]
        result = write_pack(root, cfg=load_config(root))
        if result.get("error"):
            print(f"::warning title=hot-tape-pack::{result['error']}", flush=True)
        else:
            log.info("hot_tape_pack: wrote %s (%s tickers, %ss)",
                     result.get("path"), result.get("n_tickers"), result.get("elapsed_s"))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=hot-tape-pack::unexpected failure: {exc}", flush=True)
        log.warning("hot_tape_pack.main failed", exc_info=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
