"""Polygon (standing open-interest) -> the SAME daily GEX panel schema the volume-proxy
backfill emits, so scripts/gex_phase0.py runs the identical battery on REAL dealer-OI
history. This is the definitive test the volume proxy could not be: OI is persistent
standing positioning (the actual driver of dealer hedging), not one day's flow.

STATUS: awaiting the Polygon (massive.com) API key from the user. Everything except the
one network call `_fetch_chain` is wired — fill that in when creds land and run:
    POLYGON_API_KEY=... .venv/bin/python -m scripts.gex_polygon_panel --start 2022-01-01

THE CONTRACT (what `_fetch_chain` must return for one (symbol, date)):
  spot: float  — underlying close that day
  contracts: DataFrame with one row per option contract and columns
     K     strike
     T     years to expiry  (DTE/365)
     iv    implied vol, DECIMAL (0.18 not 18)
     gamma per-contract BS gamma (Polygon ships greeks; or recompute via engine.greeks)
     w     OPEN INTEREST   (the standing-OI weight — this is the whole point vs volume)
     sign  +1 for calls, -1 for puts  (long-call / short-put dealer convention)
  (optionally delta + per-contract IV if you also want the ATM-IV / 25-delta put-skew read)

Polygon endpoints that carry OI + greeks:
  - live/EOD snapshot:  GET /v3/snapshot/options/{underlying}      (open_interest, greeks, iv, day close)
  - historical by day:  accrue the daily snapshot forward, OR pull per-contract OI from the
    flat-file/aggregates product. massive.com may proxy these — confirm the exact path on receipt.

Output: data/gex_backfill/panel_<sym>.parquet  (weight_kind='oi'), identical schema to the
volume panel, so gex_phase0 just picks it up.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.gex_backfill_panel import Q, reduce_chain  # noqa: E402

SYMS = ("SPY", "QQQ", "SPX", "IWM")          # OI works at the index level (clean dealer sign)


def _fetch_chain(symbol: str, date: str, key: str) -> tuple[float, pd.DataFrame] | None:
    """TODO(creds): one network call returning (spot, contracts) per THE CONTRACT above.
    Left unimplemented until the Polygon/massive.com key + endpoint shape are confirmed."""
    raise NotImplementedError(
        "Provide the Polygon (massive.com) API key + endpoint; build the long contract frame "
        "[K,T,iv,gamma,w=open_interest,sign] and return (spot, contracts). Then reduce_chain "
        "produces a panel row identical to the volume proxy.")


def build(symbol: str, dates: list[str], key: str) -> pd.DataFrame:
    sym = symbol.lower()
    q = Q.get(sym, 0.0)
    rows = []
    for d in dates:
        got = _fetch_chain(symbol, d, key)
        if not got:
            continue
        spot, contracts = got
        contracts = contracts[(contracts["iv"] > 0) & (contracts["w"].fillna(0) >= 0)
                              & contracts["gamma"].notna() & contracts["K"].notna()]
        if len(contracts) < 20 or not (spot and spot > 0):
            continue
        row = {"date": pd.Timestamp(d), "spot": float(spot), "n_contracts": int(len(contracts)),
               **reduce_chain(contracts, float(spot), q)}
        rows.append(row)
    out = pd.DataFrame(rows).drop_duplicates("date").set_index("date").sort_index()
    out["symbol"] = sym
    out["weight_kind"] = "oi"
    return out


def main(argv: list[str]) -> int:
    key = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY")
    if not key:
        print("Set POLYGON_API_KEY (or MASSIVE_API_KEY). This extractor is a drop-in for "
              "scripts.gex_backfill_panel — it writes the same panel_<sym>.parquet with OI weights.")
        return 0
    # TODO(creds): replace with a real trading-day calendar over the requested span
    start = argv[argv.index("--start") + 1] if "--start" in argv else "2022-01-01"
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start, pd.Timestamp.today())]
    for symbol in SYMS:
        df = build(symbol, dates, key)
        if df.empty:
            print(f"{symbol}: no data")
            continue
        cache = Path(f"data/gex_backfill/panel_{symbol.lower()}.parquet")
        df.to_parquet(cache)
        print(f"{symbol}: wrote {cache} ({len(df)} days, OI-weighted)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
