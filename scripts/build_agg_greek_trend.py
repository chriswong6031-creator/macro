#!/usr/bin/env python3
"""Build the aggregate greek trend — whole-book dealer exposure per session, per root.

Writes ``data/agg_trend/{ROOT}.parquet`` (the durable cache) and
``data/live_flow_out/options_hub/aggtrend/{ROOT}.json`` (the published payload),
optionally uploading to R2 under ``options_hub/aggtrend/``.

Program of record: charting-app ``docs/VOLLAND_PARITY_PLAN_2026-08-01.md`` §5 (W2).

Why a separate script from the nightly
--------------------------------------
``build_options_hub_nightly`` reads ONE session per root and is budgeted at 420s
per root. A first build here reads every year in the store — for SPY that is ten
parquets totalling ~1.4GB of greeks plus the matching open interest. Those are
different jobs with different failure modes, so they get different entry points.

After the first pass this is cheap: the cache holds every session already computed
and only ``--tail`` recent sessions are re-derived (open interest for the last few
days can still be revised upstream), so the nightly-cadence run touches one year
parquet per root.

Memory
------
Year files are read one at a time with an explicit column projection — 11 of the
26 columns the greeks store carries. Reading a full year unprojected is what turns
a 170MB parquet into several GB of resident pandas.

Usage
-----
    # first build, index anchors, full history
    python -m scripts.build_agg_greek_trend --roots SPY QQQ IWM SPX --full

    # nightly-cadence incremental over every root that already has a cache
    python -m scripts.build_agg_greek_trend --cached --tail 10 --publish
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.agg_trend import (  # noqa: E402
    _GREEK_READ_COLS,
    _OI_READ_COLS,
    build_trend_payload,
    daily_aggregates,
    merge_history,
    read_cache,
    write_cache,
)
from engine.thetadata_store import store_root  # noqa: E402

log = logging.getLogger("agg_trend_builder")

REPO = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO / "data" / "agg_trend"
OUT_DIR = REPO / "data" / "live_flow_out" / "options_hub" / "aggtrend"
R2_PREFIX = "options_hub/aggtrend/"

#: Sessions re-derived at the tail on an incremental run. Open interest for the
#: most recent sessions can be revised upstream, so the tail is never trusted from
#: cache. Ten sessions is two trading weeks — comfortably past any revision.
DEFAULT_TAIL = 10

#: Roots built by default when neither --roots nor --cached is given. The index
#: complex plus the highest-volume single names — the set where a nine-year
#: positioning history is actually informative.
DEFAULT_ROOTS = [
    "SPY", "QQQ", "IWM", "DIA", "SPX", "NDX", "RUT", "VIX",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD",
    "NFLX", "AVGO", "COIN", "SMCI", "MSTR", "PLTR",
    "XLF", "XLE", "XLK", "GLD", "TLT", "HYG", "USO", "ARKK",
]


def _years_available(tier: str, root: str, store: str | Path | None) -> list[int]:
    base = store_root(store) / tier / root.upper()
    if not base.exists():
        return []
    years: list[int] = []
    for f in sorted(base.glob("*.parquet")):
        try:
            years.append(int(f.stem))
        except ValueError:
            continue
    return years


def _read_year(tier: str, root: str, year: int, cols: list[str],
               store: str | Path | None) -> pd.DataFrame:
    """Read one year parquet with an explicit column projection.

    Deliberately bypasses ``thetadata_store._load_parquets``: that memoizes whole
    frames for the life of the process, which is right for a one-session nightly
    and ruinous for a ten-year sweep.
    """
    p = store_root(store) / tier / root.upper() / f"{year}.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p, columns=cols)
    except Exception:  # noqa: BLE001
        # A store written before a column existed (e.g. `vanna` pre-2024) rejects
        # the projection. Fall back to a full read and take what is there.
        try:
            df = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001
            log.warning("agg_trend: unreadable %s — %s", p, exc)
            return pd.DataFrame()
        return df[[c for c in cols if c in df.columns]]


def build_root(root: str, store: str | Path | None, *, full: bool,
               tail: int = DEFAULT_TAIL) -> pd.DataFrame | None:
    """Build (or extend) one root's aggregate frame. Returns None when no data."""
    root = root.upper()
    cached = None if full else read_cache(CACHE_DIR, root)

    greek_years = set(_years_available("greeks", root, store))
    oi_years = set(_years_available("oi", root, store))
    years = sorted(greek_years & oi_years)
    if not years:
        log.info("agg_trend: %s — no overlapping greeks/oi years, skipping", root)
        return None

    if cached is not None and not cached.empty:
        # Incremental: recompute only the years the uncovered tail can touch.
        have = set(pd.to_datetime(cached["date"]).dt.year.unique().tolist())
        last = str(cached["date"].max())
        cutoff = (pd.Timestamp(last) - pd.Timedelta(days=tail * 2)).date().isoformat()
        years = [y for y in years if y not in have or y >= int(cutoff[:4])]
        if not years:
            log.info("agg_trend: %s — cache current through %s", root, last)
            return cached
    else:
        cutoff = None

    frames: list[pd.DataFrame] = []
    for year in years:
        g = _read_year("greeks", root, year, _GREEK_READ_COLS, store)
        if g.empty:
            continue
        o = _read_year("oi", root, year, _OI_READ_COLS, store)
        if o.empty:
            continue
        if cutoff is not None:
            g = g[pd.to_datetime(g["date"]).dt.date.astype(str) >= cutoff]
            o = o[pd.to_datetime(o["date"]).dt.date.astype(str) >= cutoff]
            if g.empty or o.empty:
                continue
        agg = daily_aggregates(g, o)
        if not agg.empty:
            frames.append(agg)
        del g, o

    if not frames:
        return cached if cached is not None and not cached.empty else None

    fresh = pd.concat(frames, ignore_index=True)
    return merge_history(cached, fresh)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roots", nargs="+", metavar="ROOT",
                    help=f"roots to build (default: the {len(DEFAULT_ROOTS)} anchors)")
    ap.add_argument("--cached", action="store_true",
                    help="build every root that already has a cache parquet")
    ap.add_argument("--full", action="store_true",
                    help="ignore the cache and rebuild from the whole store")
    ap.add_argument("--tail", type=int, default=DEFAULT_TAIL, metavar="N",
                    help=f"sessions re-derived on an incremental run (default {DEFAULT_TAIL})")
    ap.add_argument("--theta-store", default=None, metavar="PATH")
    ap.add_argument("--out", default=None, metavar="DIR",
                    help="payload output dir (default data/live_flow_out/options_hub/aggtrend)")
    ap.add_argument("--publish", action="store_true", help="upload payloads to R2")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = args.theta_store or os.environ.get("THETADATA_STORE")
    out_dir = Path(args.out) if args.out else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.roots:
        roots = [r.upper() for r in args.roots]
    elif args.cached:
        roots = sorted(p.stem for p in CACHE_DIR.glob("*.parquet"))
    else:
        roots = list(DEFAULT_ROOTS)

    log.info("agg_trend: %d roots, store=%s, full=%s", len(roots), store, args.full)

    built: list[tuple[str, int]] = []
    failed: list[str] = []
    for root in roots:
        t0 = time.time()
        try:
            df = build_root(root, store, full=args.full, tail=args.tail)
        except Exception as exc:  # noqa: BLE001
            log.warning("agg_trend: %s FAILED — %s", root, exc)
            failed.append(root)
            continue
        if df is None or df.empty:
            log.info("agg_trend: %s — nothing to build", root)
            continue

        write_cache(CACHE_DIR, root, df)
        asof = str(df["date"].max())
        payload = build_trend_payload(df, root, asof)
        path = out_dir / f"{root}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        built.append((root, len(df)))
        log.info("agg_trend: %s — %d sessions since %s (%.1fs, %.0fKB)",
                 root, len(df), payload["since"], time.time() - t0,
                 path.stat().st_size / 1024)

    if args.publish and built:
        _publish(out_dir, [r for r, _ in built])

    log.info("agg_trend: DONE — %d built, %d failed%s",
             len(built), len(failed), f" ({', '.join(failed)})" if failed else "")
    return 0


def _publish(out_dir: Path, roots: list[str]) -> None:
    """Upload built payloads to R2, reusing the nightly's client and credentials."""
    try:
        from scripts.build_options_hub_nightly import _r2_client, _upload_r2
    except Exception as exc:  # noqa: BLE001
        log.warning("agg_trend: publish unavailable — %s", exc)
        return
    s3 = _r2_client()
    bucket = os.environ.get("R2_BUCKET")
    if s3 is None or not bucket:
        log.warning("agg_trend: R2 creds absent — payloads written locally only")
        return
    ok = 0
    for root in roots:
        p = out_dir / f"{root}.json"
        if p.exists() and _upload_r2(s3, bucket, p, f"{R2_PREFIX}{root}.json"):
            ok += 1
    log.info("agg_trend: published %d/%d to R2 %s", ok, len(roots), R2_PREFIX)


if __name__ == "__main__":
    raise SystemExit(main())
