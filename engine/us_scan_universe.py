"""Liquidity-floored US SCAN universe over the whole-market daily store.

PROPHET US roadmap §4.5, operator-ratified 2026-08-05 ("Yes we should do the full
universe then").  Doctrine: **see everything, admit selectively.**  This module
resolves the widened set that gets *seen* — context-vector stamped and miss-audit
counted.  It changes **no** board admission, gate, score, rank or plan intake: the
curated universe remains the graded population, exactly as before.

WHERE THE PRICES COME FROM (census 2026-08-04, this Mac Studio)
--------------------------------------------------------------
The roadmap sentence "``build_polygon_universe`` already maintains ~8.7k names
with sector + cap" does **not** describe this repo.  That script writes
``data/polygon_universe/reference.parquet`` = **504 rows** (S&P 500 GICS labels +
``us_sector_*`` basket names, market cap fetched per ticker); the ~8.7k figure in
its own docstring is the *charting app's* cross-market search manifest
(US + China A + HK + Canada + Intl), whose US leg is built FROM this repo.  There
is no 8.7k US sector+cap table here to widen onto.

The store that actually carries a whole-market US tape is
``data/massive_stock_day/`` — **20,476 per-ticker parquets, 617 MB**, OHLCV +
``transactions``, history from 2021-07-06.  It is R2-canonical (a checkout holds
only two JSON sidecars) and is restored by the collect job, so the scan tier runs
in a lane that has restored it.  Volume is present, so a dollar-volume floor is
computable from the same read — no new collection, no API key, no rate limit.

THE FLOOR (stated, not tuned)
-----------------------------
Four plain conditions, each with an obvious reason.  They are displayed with the
artifact, and every name they drop is counted by reason — a floor whose effect is
not printed is a hidden universe change.

* ``last bar == the store's own last bar`` — still trading.  ~8k of the 20.5k
  parquets are delisted/halted tape that ends years ago; scanning them would
  manufacture "runners" out of stale last prices.
* ``bars >= confluence_tiers.MIN_HISTORY`` (159 since 2026-08-05; imported, never restated).  Below it the cascade
  returns nothing, so a shorter name could only ever be stamped as a null.  This
  module does not own that constant and never redefines it: it imports it.
* ``close >= MIN_PRICE_USD`` ($3) — sub-$3 tape is where percentage "runners" are
  tick artifacts.
* ``median(close x volume) over the last 20 bars >= MIN_MDV20_USD`` ($5M) — the
  liquidity floor proper.  MEDIAN, not mean, so one halt-and-dump session cannot
  buy a name into the universe.

Measured effect of that rule on the 2026-07-02 store (printed in the disclosure
and in the PR body):

    20,476 tickers in store
    12,434 still trading            (-8,042 delisted/stale tape)
    10,422 with >= 200 bars         (-2,012 too young to gate)
     3,980 pass price + MDV20       (-6,442 below the liquidity floor)
     2,515 of those are NEW vs the curated universe

Sensitivity is disclosed rather than optimized — at $1/$1M the set is 5,721
(4,249 new), at $5/$20M it is 2,684 (1,387 new).  We publish the rule and its
cost, and let the counts move with the tape.

WHAT THIS MODULE DOES NOT DO
----------------------------
No scoring, no ranking, no admission, no writes.  It is a pure resolver: it
returns tickers, close series and a disclosure dict.  Every failure path returns
an EMPTY universe plus a named reason — a scan tier that silently resolves to
nothing must be visible as a null, never as "no runners tonight" (#4485
null-is-not-false).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from engine.confluence_tiers import MIN_HISTORY

log = logging.getLogger(__name__)

#: Whole-market daily store, relative to the repo root.  R2-canonical.
STORE_REL = "data/massive_stock_day"
MANIFEST_NAME = "_manifest.json"

#: The floor, as displayed.  Module constants so the artifact can print the rule
#: it actually ran, and a test can pin that the printed rule IS the applied one.
MIN_PRICE_USD = 3.0
MIN_MDV20_USD = 5_000_000.0
MDV_WINDOW = 20

#: Exclusion reasons, in evaluation order.  Stable strings — the disclosure
#: histogram keys a reader plots.
EXC_NOT_TRADING = "not_trading"          # last bar older than the store's last bar
EXC_THIN_HISTORY = "thin_history"        # fewer than MIN_HISTORY bars
EXC_PRICE_FLOOR = "below_price_floor"
EXC_LIQUIDITY_FLOOR = "below_liquidity_floor"


def floor_rule_text() -> str:
    """The floor as one displayable sentence, built FROM the constants.

    Built from the constants rather than transcribed beside them, so the rule the
    artifact prints can never drift from the rule the code applies.
    """
    return (
        f"still trading (last bar = store's last bar) AND >= {MIN_HISTORY} bars "
        f"AND close >= ${MIN_PRICE_USD:,.0f} AND median(close x volume) over the "
        f"last {MDV_WINDOW} bars >= ${MIN_MDV20_USD/1e6:,.0f}M"
    )


def store_dir(root: Path) -> Path:
    return Path(root) / STORE_REL


def store_available(root: Path) -> bool:
    """True when the whole-market store is restored in THIS lane.

    A checkout holds only the JSON sidecars, so "the directory exists" is not the
    question — the question is whether any per-ticker parquet is present.
    """
    d = store_dir(root)
    if not d.is_dir():
        return False
    return next(d.glob("*.parquet"), None) is not None


def store_manifest(root: Path) -> dict[str, Any]:
    p = store_dir(root) / MANIFEST_NAME
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception as exc:  # noqa: BLE001 — a sidecar must never be fatal
        log.debug("us_scan_universe: manifest unreadable (%s)", exc)
        return {}


# --------------------------------------------------------------------------- #
# census pass — ONE read of the store, everything the floor needs
# --------------------------------------------------------------------------- #

def census(root: Path, *, limit: int | None = None) -> pd.DataFrame:
    """Per-ticker liquidity/depth summary over the whole store.

    Reads only ``close`` and ``volume`` from each parquet — measured **1.46
    ms/file, 30 s for all 20,476 files** on this Mac Studio, so the census is
    never the expensive part of the night (the per-name gate is).

    Returns columns ``ticker, bars, last, last_close, mdv20``.  A ticker whose
    parquet is unreadable is skipped, not guessed at.
    """
    d = store_dir(root)
    if not d.is_dir():
        return pd.DataFrame(columns=["ticker", "bars", "last", "last_close", "mdv20"])
    rows: list[dict[str, Any]] = []
    files = sorted(d.glob("*.parquet"))
    if limit is not None:
        files = files[:limit]
    for p in files:
        try:
            frame = pd.read_parquet(p, columns=["close", "volume"])
        except Exception:  # noqa: BLE001 — one bad parquet must not blind the store
            continue
        if frame.empty:
            continue
        close = frame["close"]
        last_close = close.iloc[-1]
        # ``bars`` counts USABLE closes, not rows. A file padded with NaN closes
        # would otherwise read as deeper than it is and slip past the >= 200 floor
        # with nothing to gate on. Same definition the shallow-cache heal uses, so
        # the two never disagree about how deep a name is.
        bars = int(close.notna().sum())
        # MDV over the last MDV_WINDOW BARS — the window the printed rule names —
        # then the median of whatever is observed inside it. Taking the last 20
        # NON-NULL observations instead would silently reach back across volume
        # gaps and median a non-contiguous stretch while still claiming "20 bars".
        #
        # Fewer than MDV_WINDOW bars in the file => NULL, never a partial-window
        # number dressed up as a 20-session median (#4485 null-not-false).
        mdv20 = None
        if len(frame) >= MDV_WINDOW:
            window = (close * frame["volume"]).iloc[-MDV_WINDOW:].dropna()
            if not window.empty:
                mdv20 = float(window.median())
        rows.append({
            "ticker": p.stem,
            "bars": bars,
            "last": str(frame.index[-1])[:10],
            "last_close": (float(last_close) if pd.notna(last_close) else None),
            "mdv20": mdv20,
        })
    return pd.DataFrame(rows, columns=["ticker", "bars", "last", "last_close", "mdv20"])


def apply_floor(frame: pd.DataFrame) -> tuple[list[str], dict[str, Any]]:
    """Apply the liquidity floor to a census frame.  Pure — no I/O.

    Returns ``(kept_tickers, disclosure)``.  The disclosure counts every name the
    floor removed, BY REASON, in evaluation order: a name is attributed to the
    FIRST condition it fails, so the counts sum to the store total exactly and no
    name is double-counted.  ``price_through`` is the store's own last bar — this
    module never consults a wall clock.
    """
    total = int(len(frame))
    disclosure: dict[str, Any] = {
        "rule": floor_rule_text(),
        "min_price_usd": MIN_PRICE_USD,
        "min_mdv20_usd": MIN_MDV20_USD,
        "mdv_window": MDV_WINDOW,
        "min_history_bars": MIN_HISTORY,
        "store_n": total,
        "kept_n": 0,
        "excluded_n": total,
        "excluded_by_reason": {},
        "price_through": None,
    }
    if frame.empty:
        disclosure["null_reason"] = (
            f"{STORE_REL} held no readable per-ticker parquet in this lane — "
            "scan tier not measured (this is a null, not an empty market)")
        return [], disclosure

    # The store's own last bar. Mode, not max: a handful of files can carry a
    # stray future-dated row, and the tape's real tip is where the mass is.
    price_through = str(frame["last"].value_counts().idxmax())
    disclosure["price_through"] = price_through

    reasons: dict[str, int] = {}
    kept: list[str] = []
    for row in frame.itertuples(index=False):
        if row.last != price_through:
            reasons[EXC_NOT_TRADING] = reasons.get(EXC_NOT_TRADING, 0) + 1
            continue
        if row.bars < MIN_HISTORY:
            reasons[EXC_THIN_HISTORY] = reasons.get(EXC_THIN_HISTORY, 0) + 1
            continue
        if row.last_close is None or not (row.last_close >= MIN_PRICE_USD):
            reasons[EXC_PRICE_FLOOR] = reasons.get(EXC_PRICE_FLOOR, 0) + 1
            continue
        if row.mdv20 is None or not (row.mdv20 >= MIN_MDV20_USD):
            reasons[EXC_LIQUIDITY_FLOOR] = reasons.get(EXC_LIQUIDITY_FLOOR, 0) + 1
            continue
        kept.append(str(row.ticker))

    kept.sort()
    disclosure["kept_n"] = len(kept)
    disclosure["excluded_n"] = total - len(kept)
    disclosure["excluded_by_reason"] = dict(sorted(reasons.items()))
    return kept, disclosure


def resolve_from_census(
    frame: pd.DataFrame, root: Path, *, curated: set[str] | None = None,
) -> tuple[list[str], dict[str, Any], dict[str, dict[str, Any]]]:
    """Floor + curated removal over an ALREADY-READ census frame.

    Split out from :func:`resolve` so a caller that needs the census for
    something else (the runner also stamps per-name ``mdv20_usd``) resolves
    through the SAME code rather than re-deriving the bookkeeping inline — two
    copies of "kept minus curated" would drift the moment either changed.

    Returns ``(scan_tickers, disclosure, liquidity)`` where ``liquidity`` maps
    each scan ticker to its measured ``mdv20_usd``.
    """
    kept, disclosure = apply_floor(frame)
    curated = set(curated or ())
    scan = [t for t in kept if t not in curated]
    disclosure["curated_n"] = len(curated)
    disclosure["curated_overlap_n"] = len(kept) - len(scan)
    disclosure["scan_n"] = len(scan)
    disclosure["store_manifest"] = {
        k: v for k, v in store_manifest(root).items()
        if k in ("n_tickers", "latest_date", "updated_at")
    }
    wanted = set(scan)
    liquidity = {
        str(row.ticker): {"mdv20_usd": row.mdv20}
        for row in frame.itertuples(index=False) if str(row.ticker) in wanted
    }
    return scan, disclosure, liquidity


def resolve(root: Path, *, curated: set[str] | None = None,
            limit: int | None = None) -> tuple[list[str], dict[str, Any]]:
    """The scan tier for tonight: floored names MINUS the curated universe.

    Curated names are removed rather than re-stamped.  They already carry a
    ``tier="curated"`` row written by the builder with the full board context
    (legs, lane, near-miss) that this lane cannot see; a second row would either
    lose to keep-first silently or double-count the name in a cohort.  Excluding
    them makes the two tiers **disjoint by construction**, which is what lets a
    study group by ``tier`` without checking for overlap.

    The disclosure carries ``curated_overlap_n`` so the removal is a printed
    number, never an invisible subtraction.
    """
    frame = census(root, limit=limit)
    scan, disclosure, _liquidity = resolve_from_census(frame, root, curated=curated)
    return scan, disclosure


# --------------------------------------------------------------------------- #
# price reads
# --------------------------------------------------------------------------- #

def close_series(root: Path, ticker: str) -> pd.Series | None:
    """One name's close series from the store, or None when unreadable."""
    p = store_dir(root) / f"{ticker}.parquet"
    try:
        series = pd.read_parquet(p, columns=["close"])["close"].dropna()
    except Exception:  # noqa: BLE001
        return None
    if series.empty:
        return None
    if not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index)
    return series.sort_index()


def close_panel(root: Path, tickers: list[str]) -> pd.DataFrame:
    """Wide close frame over the given names.  Missing names are simply absent.

    Built column-wise from per-ticker files (the store has no wide cache), then
    aligned on the union index — so a name that started trading mid-window keeps
    its leading NaNs rather than being dropped or forward-filled into existence.
    """
    cols: dict[str, pd.Series] = {}
    for ticker in tickers:
        series = close_series(root, ticker)
        if series is not None:
            cols[ticker] = series
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).sort_index()
