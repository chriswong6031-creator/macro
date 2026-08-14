#!/usr/bin/env python3
"""Stock Identity W1 — the §9-gated collection for the two absent pilot names.

Registration §9 established at the W1 data gate that **BABA and WPM are absent
from both allowed curated planes** (`data/stocks`, `data/baskets/ohlcv`), while
AEM/PAAS/AG are present on the baskets plane. §13's "a small permitted collection
step if absent" clause therefore fires for exactly those two names and no others.

What this writes
----------------
``data/stock_identity/ohlcv/<SYM>.parquet``   full OHLCV (incl. ``open``), Date index
``data/stock_identity/ohlcv/manifest.json``   provenance: fetch ts, source, adjustment
                                              mode, rows, first/last date, authority

The store is *program-owned* (`price_plane_id = stock_identity_ohlcv_v1`) and sits
last in the §1 plane precedence, so it is consulted only for names absent from the
curated planes. **Nothing is written into `data/stocks/` or `data/baskets/`** —
those planes belong to their own nightly machinery (registration §11).

Fetching goes through the house shared implementation
``collectors/_stock_ohlc.fetch_ohlc`` (``auto_adjust=True``, ``period='max'`` via
``full_history=True``) rather than a private ``yf.download`` call, so this program
inherits the same adjustment convention, retry/backoff, and column normalization
the curated planes were built with. If yfinance is unavailable or blocked, this
script fails loudly — it never silently substitutes a different source, because a
plane whose adjustment convention is unknown is exactly what the plane law exists
to keep out.

Usage::

    python3 scripts/stock_identity_collect_missing.py            # BABA + WPM
    python3 scripts/stock_identity_collect_missing.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity.authority import authority_block  # noqa: E402
from engine.stock_identity.plane import (  # noqa: E402
    PLANE_BASKETS,
    PLANE_PROGRAM,
    PLANE_STOCKS,
    plane_dir,
    symbols_on_plane,
)

log = logging.getLogger("stock_identity.collect")

#: The §9 gate resolved exactly these two names as absent from both curated planes.
GATED_SYMBOLS: tuple[str, ...] = ("BABA", "WPM")

SOURCE = "yfinance"
ADJUSTMENT_MODE = "auto_adjust=True (dividend/split adjusted total-return)"
FETCH_PERIOD = "max"

#: `_stock_ohlc._download` indexes `retries`/`backoff_base_s`; the rest are `.get`s.
FETCH_CFG: dict[str, float | int] = {
    "retries": 3,
    "backoff_base_s": 5.0,
    "batch_size": 2,
    "sleep_s": 2.0,
}


def _already_curated(symbol: str) -> str | None:
    """The curated plane carrying ``symbol``, or None — the gate's own precondition."""
    for plane_id in (PLANE_STOCKS, PLANE_BASKETS):
        if symbol in symbols_on_plane(plane_id, REPO_ROOT):
            return plane_id
    return None


def collect(symbols: tuple[str, ...] = GATED_SYMBOLS, *, dry_run: bool = False) -> dict:
    out_dir = plane_dir(PLANE_PROGRAM, REPO_ROOT)

    gate: dict[str, str] = {}
    for sym in symbols:
        curated = _already_curated(sym)
        gate[sym] = curated or "absent_from_both_curated_planes"
        if curated:
            raise SystemExit(
                f"REFUSING to collect {sym}: it is present on curated plane {curated}. "
                "The §13 collection clause fires only for names ABSENT from both "
                "curated planes; collecting a present name would create a second, "
                "differently-adjusted history for the same instrument."
            )
    print(f"[gate] {json.dumps(gate)}", flush=True)

    if dry_run:
        return {"dry_run": True, "gate": gate}

    try:
        from collectors._stock_ohlc import fetch_ohlc
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"cannot import collectors._stock_ohlc.fetch_ohlc ({exc}). The §9 collection "
            "uses the house fetcher only — no substitute source."
        ) from exc

    fetched_at = datetime.now(timezone.utc).isoformat()
    frames = fetch_ohlc(
        list(symbols), "stock_identity_w1", FETCH_CFG, full_history=True, auto_adjust=True
    )

    missing = [s for s in symbols if s not in frames or frames[s] is None or frames[s].empty]
    if missing:
        raise SystemExit(
            f"yfinance returned nothing for {missing}. Not substituting another source — "
            "report the block instead (registration §9/§11)."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    for sym in symbols:
        df = frames[sym].sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df.index.name = "Date"
        df.columns = pd.Index(list(df.columns))
        keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
        df = df[keep].astype("float64")
        if "open" not in df.columns:
            raise SystemExit(
                f"{sym}: response carried no `open` column — the program-owned store's "
                "whole point is a plane that has one. Not writing a degraded file."
            )
        path = out_dir / f"{sym}.parquet"
        df.to_parquet(path)
        entries[sym] = {
            "rows": int(len(df)),
            "first_date": str(df.index[0].date()),
            "last_date": str(df.index[-1].date()),
            "columns": list(df.columns),
            "path": str(path.relative_to(REPO_ROOT)),
        }
        print(
            f"[write] {sym}: {len(df)} rows {df.index[0].date()} -> {df.index[-1].date()} "
            f"cols={list(df.columns)}",
            flush=True,
        )

    manifest = {
        "schema": "stock_identity.ohlcv_manifest.v1",
        "price_plane_id": PLANE_PROGRAM,
        "source": SOURCE,
        "fetcher": "collectors._stock_ohlc.fetch_ohlc",
        "adjustment_mode": ADJUSTMENT_MODE,
        "fetch_period": FETCH_PERIOD,
        "fetched_at": fetched_at,
        "gate": (
            "registration §9: BABA and WPM are absent from both curated TR-adjusted "
            "planes; §13's collection clause fires for exactly these two names."
        ),
        "gate_check": gate,
        "symbols": entries,
        "authority": authority_block(),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[manifest] {out_dir / 'manifest.json'}", flush=True)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default=",".join(GATED_SYMBOLS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    syms = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())
    collect(syms, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
