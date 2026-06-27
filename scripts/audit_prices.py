"""End-of-collection data-quality audit for PER-TICKER PRICE parquet stores.

One universe per price store (stocks / yahoo / baskets-ohlcv); each ticker parquet in the
store's directory is checked against rule-based, deterministic integrity tests. This is
READ-ONLY over the data stores — it only ever WRITES data/quality/prices_audit.json (via
audit_common.write_audit) — and idempotent: re-running on unchanged data yields the same
verdict.

HARD FAILS (counted toward the collect.py governance gate's fail_pct):
  - interior NaN in a price column (open/high/low/close) — leading/trailing NaN is a late
    start, not corruption, so it is ignored; NaN in *volume* is NOT a fail (older rows
    legitimately lack volume);
  - +/-inf anywhere in a numeric column;
  - OHLC inconsistency (high below the bar's other prices, or low above them);
  - negative volume;
  - a business-day gap larger than cfg['price_max_gap_days'] — but only within the RECENT
    window (see below).

FLAGS (logged, NEVER counted as failures):
  - a single-day |move| beyond cfg['price_move_alert_pct'] — a real but unremarkable event
    (earnings, a split feed glitch) that a human eyeballs, not something that aborts a build.

WINDOWING — the structural checks (NaN/inf/OHLC/negative-volume) run over the FULL history,
because a corrupt bar is corrupt at any age. But the GAP and big-MOVE checks are scoped to the
last cfg['price_recent_days'] calendar days: the stores are APPEND-ONLY, so a new hole can only
appear at the recent edge, and immutable deep-history exchange closures (9/11 = a 5-business-day
NYSE shutdown, Hurricane Sandy, the 1933 bank holiday) are NOT data-quality problems — flagging
them would false-abort every run forever. A recent gap, by contrast, is an actionable collection
miss. A gap that straddles the window boundary is still caught (one pre-window bar is retained).

DEFAULT STORES — the homogeneous US-equity OHLC stores the signal engine + charts consume:
data/stocks and data/baskets/ohlcv. data/yahoo is deliberately NOT a default: it is a
heterogeneous close-only grab-bag (equity ETFs + FX + futures + crypto + vol indices) with mixed
trading calendars, and its members' existence/depth are already audited by audit_universe. Add it
back via quality.price_stores if desired.

Stores with no per-ticker parquet (e.g. data/china_stocks & data/hk_stocks hold only a
latest.json) are SKIPPED — never an abort for an absent backing store.
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import audit_common as ac

log = logging.getLogger("audit.prices")

# Default per-ticker price stores. Each becomes one universe (named by `group`). cfg may
# override the whole list via quality.price_stores. Columns listed are those EXPECTED to be
# present; checks adapt to whatever columns actually exist in each parquet.
DEFAULT_STORES = [
    {"group": "stocks", "cols": ["close", "high", "low", "volume"]},                  # signal-engine source; NO 'open' column
    {"group": "baskets/ohlcv", "cols": ["open", "high", "low", "close", "volume"]},   # basket-chart source; full OHLCV
]

PRICE_COLS = ("open", "high", "low", "close")


def _store_dir(data_dir: Path, group: str) -> Path:
    """Resolve a store group (possibly nested like 'baskets/ohlcv') to a directory under the
    passed-in data_dir, so a data_dir override is honoured (no global hardcode)."""
    return data_dir.joinpath(*group.split("/"))


def _recent_slice(df: pd.DataFrame, asof: date, days: int) -> pd.DataFrame:
    """The tail of df within the last `days` calendar days of asof, PLUS the single bar
    immediately before the window so a hole straddling the boundary is still detected."""
    if df.empty or days is None:
        return df
    start = pd.Timestamp(asof) - pd.Timedelta(days=int(days))
    pos = int(df.index.searchsorted(start))   # first bar on/after the window start
    lo = max(0, pos - 1)                       # keep one pre-window bar for boundary gaps
    return df.iloc[lo:]


def _audit_ticker(u: ac.Universe, ticker: str, path: str, cfg: dict, asof: date) -> None:
    """Run every integrity check on one ticker parquet, recording fails/flags on `u`.
    Never raises for a data issue — a read failure is recorded as a fail."""
    try:
        raw = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001  — one bad file must not crash the audit
        u.fail(ticker, f"unreadable: {e}")
        return

    df = ac.clean_index(raw)
    cols = set(df.columns)
    # Gap + big-move checks see only the recent edge (the stores are append-only, so deep-history
    # exchange closures are immutable and not actionable — see the module docstring).
    recent = _recent_slice(df, asof, cfg.get("price_recent_days"))

    # --- (1) NaN / inf -------------------------------------------------------
    # Interior NaN in a PRICE column is corruption; volume NaN is allowed (documented).
    for c in PRICE_COLS:
        if c in cols:
            n = ac.interior_nan_count(df[c])
            if n > 0:
                u.fail(ticker, f"interior NaN in {c} ({n})")
    # +/-inf anywhere in a numeric column (incl. volume) is a fail.
    for c in sorted(cols):
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) and ac.has_bad_floats(s):
            u.fail(ticker, f"inf in {c}")

    # --- (2) OHLC validity (only when BOTH high & low exist) -----------------
    if "high" in cols and "low" in cols:
        _check_ohlc(u, ticker, df)

    # --- (3) volume >= 0 -----------------------------------------------------
    if "volume" in cols:
        vol = pd.to_numeric(df["volume"], errors="coerce")
        neg = vol < 0  # NaN compares False, so nulls are ignored
        nneg = int(neg.sum())
        if nneg:
            worst = vol[neg].idxmin()
            u.fail(ticker, f"negative volume on {nneg} row(s) (worst {_d(worst)})")

    # --- (4) business-day gaps (RECENT window only) -------------------------
    gaps = ac.business_gaps_over(recent.index, cfg["price_max_gap_days"])
    if gaps:
        prev, cur, bd = max(gaps, key=lambda g: g[2])
        u.fail(
            ticker,
            f"{len(gaps)} recent gap(s) > {cfg['price_max_gap_days']} business days "
            f"(largest {bd}d at {_d(prev)}->{_d(cur)})",
        )

    # --- (5) single-day move (RECENT window only) — FLAG only ---------------
    if "close" in cols:
        close = pd.to_numeric(recent["close"], errors="coerce")
        m = close.pct_change()
        if m.notna().any():
            am = m.abs()
            worst = am.idxmax()
            thr = cfg["price_move_alert_pct"] / 100.0
            if np.isfinite(am.loc[worst]) and am.loc[worst] > thr:
                nbig = int((am > thr).sum())
                u.flag(
                    ticker,
                    "move",
                    f"{m.loc[worst]:+.1%} on {_d(worst)}"
                    + (f" ({nbig} day(s) > {cfg['price_move_alert_pct']:.0f}%)" if nbig > 1 else ""),
                )


def _check_ohlc(u: ac.Universe, ticker: str, df: pd.DataFrame) -> None:
    """high must be the bar's max, low its min, vs whichever of {open,close} (+ the other
    extreme) are present. Tolerance scales with price so float noise is not a violation."""
    cols = set(df.columns)
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")

    # high must be >= each of the other present prices.
    others_for_high = ["low"] + [c for c in ("open", "close") if c in cols]
    upper = pd.concat([pd.to_numeric(df[c], errors="coerce") for c in others_for_high], axis=1).max(axis=1)
    others_for_low = ["high"] + [c for c in ("open", "close") if c in cols]
    lower = pd.concat([pd.to_numeric(df[c], errors="coerce") for c in others_for_low], axis=1).min(axis=1)

    tol_hi = np.maximum(1e-6 * upper.abs(), 1e-8)
    tol_lo = np.maximum(1e-6 * lower.abs(), 1e-8)

    bad_hi = (high.notna() & upper.notna()) & (high < upper - tol_hi)
    bad_lo = (low.notna() & lower.notna()) & (low > lower + tol_lo)

    if bad_hi.any():
        worst = (upper - high)[bad_hi].idxmax()
        u.fail(ticker, f"OHLC invalid: high<max(open,low,close) on {int(bad_hi.sum())} row(s) (worst {_d(worst)})")
    if bad_lo.any():
        worst = (low - lower)[bad_lo].idxmax()
        u.fail(ticker, f"OHLC invalid: low>min(open,high,close) on {int(bad_lo.sum())} row(s) (worst {_d(worst)})")


def _d(ts) -> str:
    """A date-only string for a Timestamp (stable, terse audit detail)."""
    try:
        return pd.Timestamp(ts).date().isoformat()
    except Exception:  # noqa: BLE001
        return str(ts)


def run(stores=None, cfg=None, asof=None, out_dir=None, data_dir=None) -> dict:
    """Audit each price store and persist data/quality/prices_audit.json. Returns the audit
    document. Never raises for a data issue — every problem is a fail or a flag."""
    cfg = cfg or ac.quality_cfg()
    if stores is None:
        stores = cfg.get("price_stores") or DEFAULT_STORES
    data_dir = Path(data_dir) if data_dir is not None else ac.ROOT / "data"
    out_dir = Path(out_dir) if out_dir is not None else None
    asof = asof or date.today()

    universes: list[ac.Universe] = []
    for spec in stores:
        group = spec["group"] if isinstance(spec, dict) else str(spec)
        u = ac.Universe(group)
        d = _store_dir(data_dir, group)
        files = sorted(glob.glob(str(d / "*.parquet")))
        if not files:
            u.skipped = True
            u.note = "no per-ticker parquet store"
            log.info("price store %s skipped (%s)", group, "missing dir" if not d.exists() else "0 parquet files")
            universes.append(u)
            continue

        u.n = len(files)
        for path in files:
            ticker = os.path.splitext(os.path.basename(path))[0]
            _audit_ticker(u, ticker, path, cfg, asof)

        log.info("price store %s: n=%d failed=%d (%.2f%%) flags=%d",
                 group, u.n, u.n_failed, u.fail_pct, len(u.flags))
        universes.append(u)

    return ac.write_audit("prices", "prices", universes, cfg, asof=asof, out_dir=out_dir)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Audit per-ticker price parquet stores.")
    p.add_argument("--data-dir", default=None, help="override data/ root (default: repo data/)")
    p.add_argument("--out-dir", default=None, help="override output dir (default: data/quality)")
    p.add_argument("--asof", default=None, help="audit asof date YYYY-MM-DD (default: today)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    asof = date.fromisoformat(args.asof) if args.asof else None
    doc = run(
        asof=asof,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        data_dir=Path(args.data_dir) if args.data_dir else None,
    )
    log.warning(
        "prices audit: n=%d n_failed=%d fail_pct=%.2f%% n_flags=%d",
        doc["n"], doc["n_failed"], doc["fail_pct"], doc["n_flags"],
    )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
