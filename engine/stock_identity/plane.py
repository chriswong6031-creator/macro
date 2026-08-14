"""Price-plane enumeration and the normalized per-symbol loader (registration §1).

Three planes are legal for this program, in a fixed precedence:

===========================  =============================  ==================
directory                    ``price_plane_id``             columns
===========================  =============================  ==================
``data/stocks``              ``stocks_tr_v1``               close high low volume
``data/baskets/ohlcv``       ``baskets_ohlcv_v1``           open high low close volume
``data/stock_identity/ohlcv``  ``stock_identity_ohlcv_v1``  open high low close volume
===========================  =============================  ==================

**Primary-plane rule (§1):** ``stocks`` beats ``baskets`` beats the program-owned
store — the deeper curated store wins, and the program-owned store exists only
for names absent from both curated planes (the §9-gated collection). The chosen
plane is recorded as ``price_plane_id`` on every downstream row (masterplan §4
law vi), which is what lets the census cross-tabulate feature availability by
plane, so a behavioral neighborhood can never partition by data plane before it
partitions by behavior.

**The open-column asymmetry is structural, not incidental.** ``data/stocks`` has
no ``open`` (archaeology §6.1), so the gap feature family is unavailable for the
~240 deepest-history names. Under the plane-availability law that family is
excluded from the metric block entirely rather than masked per name. This module
reports availability; ``fingerprint`` applies the law.

The raw, split-uncorrected ``massive_stock_day`` plane is prohibited for any
MA/drawdown/gap math (masterplan §9.7) and is never read here.

Reads are direct ``pandas.read_parquet`` calls. The canonical ``lib/store.py``
accessor is macro-series-oriented (keyed by series id, not by instrument), so
using it here would mean adapting an unrelated shape; direct reads keep this
package's coupling surface at "the parquet layout on disk", which is what the
plane law is about anyway.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# --- plane identities (frozen strings; they appear in committed artifacts) ----
PLANE_STOCKS = "stocks_tr_v1"
PLANE_BASKETS = "baskets_ohlcv_v1"
PLANE_PROGRAM = "stock_identity_ohlcv_v1"

#: Precedence order, best first. Registration §1.
PLANE_PRECEDENCE: tuple[str, ...] = (PLANE_STOCKS, PLANE_BASKETS, PLANE_PROGRAM)

PLANE_DIRS: dict[str, str] = {
    PLANE_STOCKS: "data/stocks",
    PLANE_BASKETS: "data/baskets/ohlcv",
    PLANE_PROGRAM: "data/stock_identity/ohlcv",
}

#: Planes that carry an ``open`` column (drives the gap-basis choice in `state`).
PLANES_WITH_OPEN: frozenset[str] = frozenset({PLANE_BASKETS, PLANE_PROGRAM})

_REQUIRED = ("close", "high", "low", "volume")


@dataclass(frozen=True)
class PlaneRow:
    """One symbol's plane assignment plus the cheap shape facts."""

    symbol: str
    price_plane_id: str
    path: str
    first_date: pd.Timestamp
    last_date: pd.Timestamp
    n_rows: int
    has_open: bool


def _root(repo_root: str | Path | None) -> Path:
    return Path(repo_root) if repo_root is not None else Path.cwd()


def plane_dir(plane_id: str, repo_root: str | Path | None = None) -> Path:
    return _root(repo_root) / PLANE_DIRS[plane_id]


def symbols_on_plane(plane_id: str, repo_root: str | Path | None = None) -> set[str]:
    """Every symbol with a parquet file on ``plane_id`` (empty if the dir is absent)."""
    d = plane_dir(plane_id, repo_root)
    if not d.is_dir():
        return set()
    return {p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_")}


def primary_planes(repo_root: str | Path | None = None) -> dict[str, str]:
    """symbol -> ``price_plane_id`` under the §1 precedence rule.

    A symbol present on several planes is assigned the FIRST plane in
    ``PLANE_PRECEDENCE`` that carries it; the others are shadowed and never read.
    """
    assigned: dict[str, str] = {}
    for plane_id in PLANE_PRECEDENCE:
        for sym in sorted(symbols_on_plane(plane_id, repo_root)):
            assigned.setdefault(sym, plane_id)
    return assigned


def symbol_path(symbol: str, plane_id: str, repo_root: str | Path | None = None) -> Path:
    return plane_dir(plane_id, repo_root) / f"{symbol}.parquet"


def load_symbol(
    symbol: str,
    plane_id: str,
    repo_root: str | Path | None = None,
    *,
    columns: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Load one symbol as a normalized OHLCV frame.

    Returns a frame indexed by an ascending, de-duplicated ``DatetimeIndex`` named
    ``Date``, with float ``close/high/low/volume`` and — only where the plane
    carries it — ``open``. Non-positive closes are dropped (bad prints break every
    log-return and drawdown downstream); the count dropped is logged, never
    silently absorbed.

    Raises ``FileNotFoundError`` if the symbol is not on that plane and
    ``ValueError`` if a required column is missing, because a silently empty frame
    would show up downstream as a coverage null and read as "young name".
    """
    path = symbol_path(symbol, plane_id, repo_root)
    if not path.exists():
        raise FileNotFoundError(f"{symbol} not present on plane {plane_id} ({path})")
    df = pd.read_parquet(path, columns=list(columns) if columns else None)
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{symbol} on {plane_id}: missing required column(s) {missing}")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"{symbol} on {plane_id}: index is not a DatetimeIndex")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.index.name = "Date"
    # `data/stocks` parquets carry a COLUMN-index name ("Price") left over from the
    # yfinance flatten; `data/baskets/ohlcv` carries none. Normalize so a concat or a
    # column-wise merge downstream cannot pick up a phantom axis name. Volume is
    # int64 on one plane and float64 on the other — the astype below settles it.
    df.columns = pd.Index(list(df.columns))

    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[keep].astype("float64")

    bad = ~(out["close"] > 0)
    if bool(bad.any()):
        log.debug("%s/%s: dropping %d non-positive close print(s)", plane_id, symbol, int(bad.sum()))
        out = out.loc[~bad]
    return out


def has_open(plane_id: str) -> bool:
    return plane_id in PLANES_WITH_OPEN


def describe_symbol(
    symbol: str, plane_id: str, repo_root: str | Path | None = None
) -> PlaneRow:
    """Cheap shape facts for the universe snapshot (loads the frame once)."""
    df = load_symbol(symbol, plane_id, repo_root)
    return PlaneRow(
        symbol=symbol,
        price_plane_id=plane_id,
        path=str(symbol_path(symbol, plane_id, repo_root)),
        first_date=df.index[0] if len(df) else pd.NaT,
        last_date=df.index[-1] if len(df) else pd.NaT,
        n_rows=int(len(df)),
        has_open="open" in df.columns,
    )
