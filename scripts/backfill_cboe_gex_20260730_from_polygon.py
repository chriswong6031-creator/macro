"""One-shot honest cross-fill of the 2026-07-30 CBOE gex hole from the polygon archive.

WHAT WAS LOST
    On 2026-07-30 the CBOE CDN held a continuous HTTP 429 on the delayed_quotes chain
    endpoint for ≥3 minutes (23:42:32Z→23:45:33Z+, run 30590845976), outlasting both
    the 3/6/12s per-request ladder and that night's single 60s cooldown. Six series
    lost the session: putcall, gex, gex_SPX, gex_SPY, gex_QQQ, gex_IWM.

WHY THIS IS A HEAL AND NOT A FABRICATION
    data/polygon_gex/summary_{SPY,QQQ,IWM}.parquet are produced by the SAME engine
    (engine.gex_engine.compute_gex, via scripts/build_polygon_gex.py) with the SAME
    16-column summary schema and dtypes as data/cboe/gex_{SPY,QQQ,IWM}.parquet. This
    is a like-for-like observation of the same session from a second vendor's chain —
    not an interpolation, not a carry-forward, not a model output. Nothing is invented:
    the row is COPIED and re-dated, and the script refuses to run unless it can prove
    the row is the session it claims to be.

    Only gex_SPY/QQQ/IWM are recoverable. putcall + gex + gex_SPX stay permanently
    lost: no archive here carries SPX options (polygon's universe is equities/ETFs),
    and putcall is all-or-nothing on its _SPX leg. See collectors/cboe.py
    KNOWN_PERMANENT_GAPS[2026-07-30].

THE DATE MAPPING — THE WHOLE REASON THIS SCRIPT HAS HARD PRECONDITIONS
    build_polygon_gex stamps its accrual with `datetime.now(timezone.utc).date()`
    (scripts/build_polygon_gex._as_date), and the evening collect crosses 00:00Z before
    the polygon band runs. So a polygon row is stamped SESSION + 1 DAY:

        session 2026-07-30  →  polygon summary row stamped 2026-07-31

    Verified systematic across 2026-07-20 → 07-31: every stamp's `spot` equals the
    PRIOR session's yahoo close to 0.000%. Copying the row that merely *looks* right
    by its stamp would silently land the WRONG SESSION's gamma into the store, which
    is worse than the hole it heals — an undetectable off-by-one in a series that feeds
    the regime panel. Hence the preconditions below: the copy is refused unless the
    source row's spot both (a) matches the target session's yahoo close within
    SPOT_TOL_PCT and (b) matches that session CLOSER than any neighbouring session.
    (b) is load-bearing, not belt-and-braces: for IWM the 07-31 stamp sits within
    0.5% of BOTH the 07-30 close (0.000%) and the 07-31 close (0.477%), so the
    tolerance gate ALONE does not uniquely pin the session for that symbol.

IDEMPOTENT: a symbol whose target store already carries 2026-07-30 is skipped.

Usage:
    python -m scripts.backfill_cboe_gex_20260730_from_polygon [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store  # noqa: E402

log = logging.getLogger(__name__)

SESSION = date(2026, 7, 30)
# +1 calendar day: the polygon accrual stamps UTC now() after the evening collect
# has already crossed 00:00Z. Proven per-symbol at runtime, never assumed.
POLYGON_STAMP = date(2026, 7, 31)
SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "IWM")

# Session-identity gate. The exact observed error is 0.000% on all three symbols
# (the polygon spot IS the session close), so 0.5% is a generous ceiling that still
# rejects the off-by-one: the neighbouring session's close sits 1.3-3.2% away.
SPOT_TOL_PCT = 0.5
# Neighbourhood searched for the "is SESSION the closest session?" uniqueness check.
NEIGHBOUR_DAYS = 5


class BackfillPreconditionError(RuntimeError):
    """A hard precondition failed — nothing was written."""


def _spot_vs_close(sym: str, spot: float) -> tuple[float, str, float]:
    """(err_pct_at_SESSION, nearest_session_name, err_pct_at_nearest).

    Reads the independent yahoo daily close panel — a third source, so agreement
    pins the session identity rather than merely restating the polygon store.
    """
    y = store.read("yahoo", sym)
    if y is None:
        raise BackfillPreconditionError(
            f"{sym}: yahoo/{sym} not in store — cannot verify session identity")
    if "close" not in y.columns:
        raise BackfillPreconditionError(
            f"{sym}: yahoo/{sym} has no 'close' column (got {list(y.columns)}) "
            f"— cannot verify session identity")
    target = pd.Timestamp(SESSION)
    if target not in y.index:
        raise BackfillPreconditionError(
            f"{sym}: yahoo panel has no {SESSION} close — cannot verify session "
            f"identity, refusing to copy")
    err_at_session = abs(spot / float(y.loc[target, "close"]) - 1) * 100

    span = pd.Timedelta(days=NEIGHBOUR_DAYS)
    lo, hi = target - span, target + span
    near = y.loc[(y.index >= lo) & (y.index <= hi)]
    errs = sorted((abs(spot / float(near.loc[t, "close"]) - 1) * 100, str(t.date()))
                  for t in near.index)
    return err_at_session, errs[0][1], errs[0][0]


def _check_one(sym: str) -> tuple[pd.DataFrame, dict]:
    """Validate every precondition for one symbol; return (row_to_write, receipt)."""
    src = store.read("polygon_gex", f"summary_{sym}")
    tgt = store.read("cboe", f"gex_{sym}")
    if src is None:
        raise BackfillPreconditionError(f"{sym}: polygon_gex/summary_{sym} not in store")
    if tgt is None:
        raise BackfillPreconditionError(f"{sym}: cboe/gex_{sym} not in store")

    stamp = pd.Timestamp(POLYGON_STAMP)
    if stamp not in src.index:
        raise BackfillPreconditionError(
            f"{sym}: polygon archive has no row stamped {POLYGON_STAMP} — the "
            f"{SESSION} session was never captured there either")

    # 1. schema equality — same columns in the same order, same dtypes.
    if list(src.columns) != list(tgt.columns):
        raise BackfillPreconditionError(
            f"{sym}: column mismatch\n  polygon: {list(src.columns)}\n  cboe:    "
            f"{list(tgt.columns)}")
    if list(src.dtypes) != list(tgt.dtypes):
        raise BackfillPreconditionError(
            f"{sym}: dtype mismatch\n  polygon: {list(src.dtypes.astype(str))}\n"
            f"  cboe:    {list(tgt.dtypes.astype(str))}")

    # 2. session identity — the source row must BE the session we are re-dating it to.
    row = src.loc[[stamp]].copy()
    spot = float(row["spot"].iloc[0])
    err, nearest, nearest_err = _spot_vs_close(sym, spot)
    if err > SPOT_TOL_PCT:
        raise BackfillPreconditionError(
            f"{sym}: polygon row stamped {POLYGON_STAMP} has spot {spot:.4f}, which is "
            f"{err:.3f}% from the {SESSION} yahoo close (tolerance {SPOT_TOL_PCT}%). "
            f"It is closest to the {nearest} session ({nearest_err:.3f}%) — this row is "
            f"NOT the {SESSION} session; refusing to write the wrong session's gamma")
    if nearest != str(SESSION):
        raise BackfillPreconditionError(
            f"{sym}: polygon row stamped {POLYGON_STAMP} (spot {spot:.4f}) is within "
            f"tolerance of {SESSION} ({err:.3f}%) but sits CLOSER to the {nearest} "
            f"session ({nearest_err:.3f}%) — session identity is ambiguous; refusing")

    row.index = pd.DatetimeIndex([pd.Timestamp(SESSION)])
    return row, {"symbol": sym, "spot": spot, "spot_err_pct": err,
                 "net_gex_bn": float(row["net_gex_bn"].iloc[0]),
                 "gamma_flip": float(row["gamma_flip"].iloc[0]),
                 "gamma_regime": str(row["gamma_regime"].iloc[0]),
                 "n_strikes": int(row["n_strikes"].iloc[0]),
                 "rows_before": len(tgt)}


def backfill(symbols: tuple[str, ...] = SYMBOLS, dry_run: bool = False) -> dict:
    """Copy the 2026-07-30 session from the polygon archive into the cboe gex stores.

    Idempotent: a symbol already carrying SESSION is skipped untouched.
    """
    written, skipped = [], []
    for sym in symbols:
        tgt = store.read("cboe", f"gex_{sym}")
        if tgt is not None and pd.Timestamp(SESSION) in tgt.index:
            print(f"  SKIP  gex_{sym}: {SESSION} already present ({len(tgt)} rows) "
                  f"— nothing to do")
            skipped.append(sym)
            continue

        row, receipt = _check_one(sym)
        print(f"  CHECK gex_{sym}: schema OK (16 cols, dtypes match) | polygon row "
              f"{POLYGON_STAMP} spot={receipt['spot']:.4f} == yahoo {SESSION} close "
              f"to {receipt['spot_err_pct']:.3f}% (nearest session = {SESSION}) -> "
              f"session identity confirmed")
        if dry_run:
            print(f"  DRY   gex_{sym}: would insert {SESSION} "
                  f"net_gex_bn={receipt['net_gex_bn']:.4f} "
                  f"flip={receipt['gamma_flip']:.2f} "
                  f"regime={receipt['gamma_regime']} n_strikes={receipt['n_strikes']}")
            continue

        before_dtypes = list(tgt.dtypes)
        merged = store.upsert("cboe", f"gex_{sym}", row)

        # Postconditions: the row landed, in sorted position, and nothing was upcast.
        if pd.Timestamp(SESSION) not in merged.index:
            raise BackfillPreconditionError(f"{sym}: write did not land {SESSION}")
        if list(merged.dtypes) != before_dtypes:
            raise BackfillPreconditionError(
                f"{sym}: dtypes changed on write\n  before: "
                f"{[str(d) for d in before_dtypes]}\n  after:  "
                f"{[str(d) for d in merged.dtypes]}")
        if not merged.index.is_monotonic_increasing:
            raise BackfillPreconditionError(f"{sym}: index is not sorted after write")

        pos = list(merged.index).index(pd.Timestamp(SESSION))
        neighbours = [str(d.date()) for d in merged.index[max(0, pos - 1):pos + 2]]
        print(f"  WROTE gex_{sym}: +1 row {SESSION} at index position {pos} "
              f"({' < '.join(neighbours)}) | {receipt['rows_before']} -> "
              f"{len(merged)} rows | spot={receipt['spot']:.4f} "
              f"net_gex_bn={receipt['net_gex_bn']:.4f} "
              f"flip={receipt['gamma_flip']:.2f} regime={receipt['gamma_regime']} "
              f"n_strikes={receipt['n_strikes']}")
        written.append(receipt)

    return {"written": written, "skipped": skipped}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="verify every precondition and print the plan, write nothing")
    args = ap.parse_args()

    print(f"backfill cboe gex {SESSION} from the polygon archive "
          f"(source rows stamped {POLYGON_STAMP} — UTC now() shift)")
    try:
        res = backfill(dry_run=args.dry_run)
    except BackfillPreconditionError as e:
        print(f"ABORT: {e}")
        return 1
    print(f"done: {len(res['written'])} written, {len(res['skipped'])} already present. "
          f"putcall / gex / gex_SPX remain permanently lost for {SESSION} "
          f"(no SPX options in any archive) — see collectors/cboe.py "
          f"KNOWN_PERMANENT_GAPS[{SESSION}].")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
