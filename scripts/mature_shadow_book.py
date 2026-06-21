"""Mature + grade the forward shadow book (engine/shadow_book) — the realized forward
audit of the live stock score. Joins every FULLY-ELAPSED horizon to its forward return and
emits rolling forward rank-IC + IC-IR + HAC-t per horizon to site/shadow/audit.json.

This is the only honest test of the traded score: it grades a score frozen at build time
against returns that had not happened yet. It is EMPTY until horizons mature (~1-6 months of
snapshots) — that latency is the price of honesty. The artifact carries the survivorship
caveat (free prices serve listed names → an optimistic bound).

Run nightly (after snapshot): .venv/bin/python -m scripts.mature_shadow_book
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from lib import store  # noqa: E402
from engine import shadow_book as SB  # noqa: E402


def closes_panel() -> pd.DataFrame:
    """Widest price panel available for forward returns: the broad breadth cache (505 names)
    unioned with the deep survivor names — whatever covers the booked tickers."""
    frames = {}
    cache = "data/breadth/_closes_cache.parquet"
    if os.path.exists(cache):
        c = pd.read_parquet(cache)
        for col in c.columns:
            frames[col] = c[col]
    for f in glob.glob("data/stocks/*.parquet"):
        t = os.path.splitext(os.path.basename(f))[0]
        if t not in frames:
            df = store.read("stocks", t)
            if df is not None and "close" in df:
                frames[t] = df["close"]
    return pd.DataFrame(frames).sort_index() if frames else pd.DataFrame()


def main() -> int:
    book = SB.load_book()
    if book.empty:
        print(f"[shadow] book {SB.BOOK_PATH} empty — snapshot first; nothing to mature.")
        out = {"schema": "shadow_audit.v1", "n_booked": 0, "n_matured": 0, "by_horizon": {}}
    else:
        closes = closes_panel()
        asof = closes.index[-1] if not closes.empty else pd.Timestamp.utcnow()
        matured = SB.mature(asof, closes)
        grade = SB.grade(matured, key="percentile")
        out = {"schema": "shadow_audit.v1",
               "n_booked": int(len(book)),
               "booked_dates": [str(book["date"].min()), str(book["date"].max())],
               "asof": str(pd.Timestamp(asof).date()),
               **grade,
               "interpretation": (
                   "Realized forward cross-sectional IC of the FROZEN stock score per horizon. "
                   "Empty/thin until horizons elapse. Honest prior: likely ≈0 — and knowing that "
                   "is the institutional win."),
               "survivorship": "OPTIMISTIC bound — free prices serve listed names only."}
    out["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs("site/shadow", exist_ok=True)
    with open("site/shadow/audit.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    nm = out.get("n_matured", 0)
    print(f"[shadow] booked {out.get('n_booked',0)} rows; matured {nm}; "
          f"wrote site/shadow/audit.json")
    if nm and out.get("by_horizon"):
        for h, g in out["by_horizon"].items():
            print(f"  {h}: forward IC {g['ic'].get('mean_ic')} (t {g['ic'].get('t_hac')}, "
                  f"{g['n_dates']} dates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
