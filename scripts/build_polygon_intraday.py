"""Intraday (hourly) US price accrual via Polygon / massive.com -> data/intraday/<T>.parquet.

Powers the **4H timeframe** on US single-stock charts and the 2D/3D intraday
bar-derivation hooks (engine/bar_derive.py): the collector pulls hourly bars, ships
them as site/intraday/<T>.json (scripts/build_chart_data) for the chart, and keeps the
raw store the signal-engine / Standout-grid sessions can later resample. US-only by
entitlement — the plan covers US stocks REST aggregates; non-US markets have no
intraday source, so they keep daily-derived timeframes only.

HONEST FRESHNESS — the Polygon **STANDARD** stocks plan serves **15-MINUTE-DELAYED**
aggregates. This is NOT real-time: every bar's timestamp trails the wall clock by at
least ~15 minutes. We stamp that floor on the store (a ``_meta.json`` sidecar) so every
downstream consumer/label can say "delayed" truthfully. Upgrading to a real-time/
websocket plan later -> set DELAYED_MIN = 0 (see research/LIVE_DATA_POLYGON.md).

APPEND-ONLY / KEY-DEDUPED — each run reads the existing per-ticker parquet, re-fetches
only a small recent window (with a 2-day overlap so late bar corrections are picked up),
concatenates, and de-dupes on the bar timestamp (keep='last'). So an hourly run extends
the store cheaply instead of re-pulling 180 days every time. ``--full`` forces a clean
re-fetch; ``--lookback-days`` sets the cold-start window when no prior file exists.

Curated to the deep-history US names (data/stocks/*) + sector/factor ETFs — the most-viewed,
candle-capable set — to keep the API call count and data footprint modest. Fail-safe: no
API key -> no-op; a per-ticker error is logged and skipped, never aborts the run. Mirrors
scripts/build_polygon_gex.accrue (its own persistence path, driven from scripts/collect.py).

Cannot be exercised live locally without the key (CI secret); the append/dedup + universe
+ no-key no-op paths are unit-tested in tests/test_polygon_intraday.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.polygon_options import PolygonOptions  # noqa: E402
from engine.options_signal_episode import (  # noqa: E402
    PRICE_BASIS,
    PRICE_RECEIPT_SCHEMA,
    TIMESTAMP_BASIS,
)
from lib import config  # noqa: E402

log = logging.getLogger("polygon_intraday")
GROUP = "intraday"

# Polygon STANDARD (stocks) plan delay floor, in minutes. 15-min delayed aggregates;
# NOT real-time. Stamped onto the store's _meta.json so consumers label honestly.
# Set to 0 once a real-time/websocket entitlement is live (see LIVE_DATA_POLYGON.md).
DELAYED_MIN = 15

# Re-fetch this many days back from the last stored bar on an incremental run, so a
# late aggregate correction (Polygon revises the most recent session) is captured.
_OVERLAP_DAYS = 2
def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("receipt clock must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def _bar_seconds(multiplier: int, timespan: str) -> int:
    unit = {
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }.get(timespan.lower())
    if unit is None or type(multiplier) is not int or multiplier <= 0:
        raise ValueError(f"unsupported Polygon aggregate cadence: {multiplier}{timespan}")
    return multiplier * unit


def _write_price_receipt(
    outdir: Path,
    *,
    ticker: str,
    frame: pd.DataFrame,
    bar_seconds: int,
    now_fn=None,
) -> Path:
    """Bind a post-fsync source clock and digest to one exact parquet version."""
    source = (outdir / f"{ticker}.parquet").resolve()
    raw = source.read_bytes()
    available = (now_fn or (lambda: datetime.now(timezone.utc)))()
    if available.tzinfo is None:
        raise ValueError("price receipt clock must be timezone-aware")
    index = pd.to_datetime(frame.index, utc=True)
    if frame.empty or index.hasnans:
        raise ValueError(f"cannot receipt an empty/invalid price frame for {ticker}")
    receipt = {
        "schema": PRICE_RECEIPT_SCHEMA,
        "ticker": ticker,
        # Portable exact locator: resolved relative to this adjacent receipt.
        "source_file": source.name,
        "source_file_sha256": hashlib.sha256(raw).hexdigest(),
        "source_available_at": _iso_utc(available),
        "bar_seconds": bar_seconds,
        "vendor_delay_minutes": DELAYED_MIN,
        "adjusted": True,
        "price_basis": PRICE_BASIS,
        "timestamp_basis": TIMESTAMP_BASIS,
        "row_count": len(frame),
        "first_time": _iso_utc(index.min().to_pydatetime()),
        "last_time": _iso_utc(index.max().to_pydatetime()),
    }
    path = outdir / f"{ticker}.parquet.receipt.json"
    _atomic_write_json(path, receipt)
    return path


def _universe() -> list[str]:
    """Deep-history US single names (data/stocks/*.parquet) + sector/factor ETFs from
    config.yahoo. These are exactly the candle-capable, most-viewed US tickers the daily
    chart already draws as candlesticks — the natural set to also offer intraday on."""
    names: set[str] = set()
    d = config.data_dir() / "stocks"
    if d.exists():
        for p in d.glob("*.parquet"):
            names.add(p.stem)
    ycfg = (config.load().get("yahoo") or {}).get("tickers") or {}
    # sectors/factors = the ETF set; extras = the big index ETFs (SPY/QQQ/IWM) plus the
    # searchable off-index US roster (ADRs, recent IPOs) — all have stock-library pages.
    for grp in ("sectors", "factors", "extras"):
        for t in (ycfg.get(grp) or []):
            if not str(t).startswith("^"):
                names.add(str(t))
    return sorted(names)


def _poly_sym(ticker: str) -> str:
    """Polygon encodes US class shares with a dot (BRK.B); our store uses a dash (BRK-B)."""
    return ticker.replace("-", ".")


def _read_existing(path) -> pd.DataFrame | None:
    """Prior per-ticker store, or None. Tolerant: a corrupt/legacy file -> None (the run
    falls back to a full lookback fetch rather than aborting)."""
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        # legacy files may lack a tz-aware index name; normalise so concat/dedup is safe
        df.index = pd.to_datetime(df.index, utc=True)
        df.index.name = "ts"
        return df[~df.index.duplicated(keep="last")].sort_index()
    except Exception:  # noqa: BLE001 — never let one bad file abort the accrual
        return None


def _write_meta(outdir, *, bar: str, universe_n: int, now: datetime) -> None:
    """Sidecar that travels with the store so every consumer (and a human) sees the
    honest delay without parsing a parquet. pandas drops DataFrame.attrs on the parquet
    round-trip, so this JSON is the durable label."""
    try:
        (outdir / "_meta.json").write_text(json.dumps({
            "store": "polygon_intraday",
            "bar": bar,
            "delayed_min": DELAYED_MIN,
            "source": "polygon_standard",
            "realtime": DELAYED_MIN == 0,
            "adjusted": True,
            "price_basis": PRICE_BASIS,
            "timestamp_basis": TIMESTAMP_BASIS,
            "note": ("15-MINUTE DELAYED (Polygon Standard plan) — NOT real-time"
                     if DELAYED_MIN else "real-time feed"),
            "universe": universe_n,
            "updated": now.isoformat(),
        }, indent=2))
    except Exception as e:  # noqa: BLE001
        log.warning("polygon intraday: could not write _meta.json: %s", e)


def accrue(as_of=None, *, lookback_days: int | None = None, full: bool = False,
           only: list[str] | None = None, limit: int | None = None,
           out_dir: Path | None = None) -> dict:
    """Extend data/intraday/<T>.parquet with fresh Polygon hourly bars.

    ``lookback_days`` overrides the cold-start window (when no prior file exists); on an
    incremental run the window is computed from the last stored bar. ``full`` ignores
    existing files (clean re-fetch). When supplied, ``only`` is the explicit requested
    universe rather than an intersection with the chart-oriented default universe."""
    client = PolygonOptions()   # reuses the entitled stocks REST client (auth + http_get)
    if not client.enabled():
        log.warning("polygon intraday: no API key (POLYGON_API_KEY/MASSIVE_API_KEY) — skipped")
        return {"status": "skipped", "rows": 0}

    icfg = (config.load().get("polygon") or {}).get("intraday") or {}
    mult = int(icfg.get("multiplier", 1))
    span = str(icfg.get("timespan", "hour"))
    bar_seconds = _bar_seconds(mult, span)
    lookback = int(lookback_days if lookback_days is not None else icfg.get("lookback_days", 180))
    sleep_s = float(icfg.get("sleep", 0.06))

    now = as_of or datetime.now(timezone.utc)
    to = now.date()
    # The VPS uses an external ephemeral store so intraday accrual never mutates
    # canonical repo data. Mac/CI callers keep the historical default.
    outdir = Path(out_dir) if out_dir is not None else config.data_dir() / GROUP
    outdir.mkdir(parents=True, exist_ok=True)

    universe = _universe()
    if only:
        universe = sorted({
            str(symbol).strip().upper()
            for symbol in only
            if str(symbol).strip()
        })
    if limit:
        universe = universe[:limit]

    written = 0
    appended = 0
    for t in universe:
        path = outdir / f"{t}.parquet"
        existing = None if full else _read_existing(path)
        # incremental window: from just before the last stored bar (overlap to catch
        # corrections); cold-start: the full lookback.
        if existing is not None:
            frm = (existing.index.max() - pd.Timedelta(days=_OVERLAP_DAYS)).date()
        else:
            frm = to - timedelta(days=lookback)
        try:
            res = client._get(
                f"/v2/aggs/ticker/{_poly_sym(t)}/range/{mult}/{span}/{frm.isoformat()}/{to.isoformat()}",
                {"adjusted": "true", "sort": "asc", "limit": 50000})
            if res:                                   # empty (weekend/after-hours) -> keep file as-is
                new = pd.DataFrame({
                    "open":   [r.get("o") for r in res],
                    "high":   [r.get("h") for r in res],
                    "low":    [r.get("l") for r in res],
                    "close":  [r.get("c") for r in res],
                    "volume": [r.get("v") for r in res],
                }, index=pd.to_datetime([r["t"] for r in res], unit="ms", utc=True))
                new.index.name = "ts"
                df = pd.concat([existing, new]) if existing is not None else new
                # KEY-DEDUP on the bar timestamp, last write wins (idempotent re-run safe).
                df = df[~df.index.duplicated(keep="last")].sort_index()
                before = 0 if existing is None else len(existing)
                # atomic write: tmp + replace so a crash mid-write can't truncate the store
                # (a corrupt file would force an expensive cold re-fetch). .tmp is not matched
                # by the *.parquet glob, so a stray temp never pollutes the universe.
                tmp = outdir / f"{t}.parquet.tmp"
                df.to_parquet(tmp)
                with tmp.open("rb") as handle:
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
                _fsync_directory(outdir)
                _write_price_receipt(
                    outdir,
                    ticker=t,
                    frame=df,
                    bar_seconds=bar_seconds,
                )
                written += 1
                appended += max(0, len(df) - before)
        except Exception as e:  # noqa: BLE001 — degrade per-ticker, never abort the accrual
            log.warning("polygon intraday %s failed: %s", t, e)
        finally:
            time.sleep(sleep_s)                       # pace EVERY iteration (incl. empty/error)

    if written:
        _write_meta(outdir, bar=f"{mult}{span}", universe_n=len(universe), now=now)
    log.info("polygon intraday: wrote %d/%d US tickers (+%d bars; %d%s; delayed_min=%d)",
             written, len(universe), appended, mult, span, DELAYED_MIN)
    return {"status": "ok" if written else "stale", "rows": written,
            "appended": appended, "delayed_min": DELAYED_MIN}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(
        description="Polygon STANDARD (15-min DELAYED) hourly US bars -> "
                    "data/intraday/<T>.parquet (append-only, key-deduped).")
    ap.add_argument("--lookback-days", type=int, default=None,
                    help="cold-start window when no prior file exists (default config 180); "
                         "an existing file is extended incrementally regardless")
    ap.add_argument("--full", action="store_true",
                    help="ignore existing files — clean full re-fetch + overwrite")
    ap.add_argument("--limit", type=int, default=None, help="cap the universe (debug)")
    ap.add_argument("--symbols", default=None,
                    help="comma-separated tickers to restrict to (debug)")
    ap.add_argument(
        "--out-dir",
        default=None,
        help="override data/intraday output directory (VPS uses /var/lib/macro-live/data/intraday)",
    )
    args = ap.parse_args()
    only = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    print(
        accrue(
            lookback_days=args.lookback_days,
            full=args.full,
            only=only,
            limit=args.limit,
            out_dir=Path(args.out_dir) if args.out_dir else None,
        )
    )


if __name__ == "__main__":
    main()
