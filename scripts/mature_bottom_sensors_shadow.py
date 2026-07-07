"""Mature + grade the Amendment-3 structural-descriptor shadow-ledger
(engine/neuralweb/bottom_sensors_shadow) — the realized forward audit of the
decline_geometry (family E) and underwater_state (family F) descriptors.

Joins every FULLY-ELAPSED horizon to its forward return and emits DESCRIPTIVE
per-horizon forward-return gaps (flush − grind; long − short) to
site/shadow/bottom_sensors_geometry_audit.json.

This grades the descriptors frozen at build time against returns that had not
happened yet.  It is EMPTY until horizons mature (~1-3 months of snapshots) — that
latency is the price of honesty.  DISPLAY-ONLY: a positive gap here does NOT
promote either descriptor; CHIP promotion re-opens only when the true eq_band
cache lands (RUL-28).  The artifact carries the survivorship caveat (free prices
serve currently-listed names → an optimistic bound).

Run on-demand / nightly (after snapshot; mirrors scripts/mature_shadow_book.py,
which is likewise NOT on the render critical path):
    .venv/bin/python -m scripts.mature_bottom_sensors_shadow
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
from engine.neuralweb import bottom_sensors_shadow as BSS  # noqa: E402


def closes_panel() -> pd.DataFrame:
    """Widest price panel available for forward returns: the broad breadth cache
    unioned with the deep survivor names — whatever covers the booked symbols
    (verbatim shape of scripts/mature_shadow_book.closes_panel)."""
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
    book = BSS.load_book()
    if book.empty:
        print(f"[bss-shadow] book {BSS.BOOK_PATH} empty — snapshot first; nothing to mature.")
        out = {"schema": "bottom_sensors_geometry_audit.v1", "n_booked": 0,
               "n_matured": 0, "by_horizon": {}}
    else:
        closes = closes_panel()
        asof = closes.index[-1] if not closes.empty else pd.Timestamp.utcnow()
        matured = BSS.mature(asof, closes)
        grade = BSS.grade(matured)
        out = {"schema": "bottom_sensors_geometry_audit.v1",
               "n_booked": int(len(book)),
               "booked_dates": [str(book["date"].min()), str(book["date"].max())],
               "asof": str(pd.Timestamp(asof).date()),
               **grade,
               "interpretation": (
                   "Realized forward-return gaps of the FROZEN structural descriptors per "
                   "horizon: decline_geometry flush−grind (family E, DISPLAY-CANDIDATE) and "
                   "underwater_state long−short (family F, ADVERSE-CONTEXT). Descriptive only; "
                   "empty/thin until horizons elapse."),
               "authority": (
                   "DISPLAY-ONLY — no ranking/gating/allocation surface is touched; a positive "
                   "gap does NOT promote either descriptor. CHIP promotion is blocked until the "
                   "true eq_band cache lands (RUL-28)."),
               "survivorship": "OPTIMISTIC bound — free prices serve currently-listed names only."}
    out["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs("site/shadow", exist_ok=True)
    with open("site/shadow/bottom_sensors_geometry_audit.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    nm = out.get("n_matured", 0)
    print(f"[bss-shadow] booked {out.get('n_booked',0)} rows; matured {nm}; "
          f"wrote site/shadow/bottom_sensors_geometry_audit.json")
    if nm and out.get("by_horizon"):
        for h, g in out["by_horizon"].items():
            dg = g.get("decline_geometry", {})
            print(f"  {h}: flush−grind fwd-ret gap {dg.get('flush_minus_grind')} "
                  f"(n_obs {g.get('n_obs')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
