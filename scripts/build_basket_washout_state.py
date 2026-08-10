"""Nightly basket-washout state -> site/factordata/basket_washout_state.json.

Display-tier support artifact for the RATIFIED blocked-entry override (construction A1b,
threshold 25%): `research/BLOCKED_ENTRY_CONDITIONAL_PREREG.md` §5 ratification log +
`research/BLOCKED_ENTRY_RATIFICATION_PACKET_2026-08-10.md` §4.

WHAT THIS IS: a nightly snapshot of how deep each US thematic basket's members sit below
their 252-session highs, plus the per-name lookup (which group a name reads through, and
whether that group clears each of the three published thresholds).  Nothing here scores,
ranks, or gates anything — the live `enter`-mask conditional stays behind its own two
standing gates (production-feed re-grade + signal-era fence).  This artifact only lets a
reader-facing surface show the same peer-washout number the study measured on.

CONSTRUCTION (mirrors `research/blocked_entry_study/r3_axes.py`, the graded instrument):
  * per-name drawdown  = close / close.rolling(252, min_periods=60).max() - 1
  * a basket's state   = the MEDIAN of that drawdown across its members that print on
                         `as_of`; a group needs >= 5 such members or it is omitted
  * a name's peer set  = its PRIMARY basket -- the smallest basket (>= 5 curated members)
                         the name belongs to, ties broken by id, i.e. the most
                         thematically specific one
  * fallback           = GICS sector peers (data/breadth/ticker_sectors.parquet) for names
                         no basket claims
  * names in NEITHER mapping are OMITTED -- never defaulted to a neutral value
  * a name PRINTS ITS GROUP'S number: the median is not recomputed leave-one-out, so a
    name and its basket always show the same figure (these are the same all-member
    medians the study's exemplar and current-membership receipts were reported on --
    UEC/uranium_miners, HL/silver_miners, NEM/gold_miners)
  * `qualifies[t]` is recomputed from the PUBLISHED (rounded) number, so a consumer that
    re-derives the flag from `peer_median_dd_252` / `peer_dd` always agrees with us

Basket membership comes from the curated store `data/baskets/membership.json` (the same
source `scripts/build_baskets.py` and the prophet candidates' `theme_membership_ids`
descend from); members carrying a `removed` date are dropped.

COST: reads only the names it needs (basket members + GICS-mapped names), one close column
each, ~2-5s wall on the full US panel.  It is a nightly display artifact and must stay off
the render-critical path.

Usage: python -m scripts.build_basket_washout_state [--data-root DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_basket_washout_state")

SCHEMA = "basket_washout_state.v1"
THRESHOLDS = (20, 25, 30)          # published menu (packet §2); 25 is the ratified default
WINDOW = 252                       # trading-day high water mark
MIN_PERIODS = 60                   # a name needs a quarter of history before it has a high
MIN_PEERS = 5                      # a group thinner than this states nothing
ROUND = 6

GICS = (
    "Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy",
    "Financials", "Health Care", "Industrials", "Information Technology", "Materials",
    "Real Estate", "Utilities",
)


# --------------------------------------------------------------------- inputs --
def load_basket_defs(data_root: Path) -> dict[str, dict]:
    """Curated basket id -> {name, name_zh, members}.  Degrades to {} when the store is
    missing or unreadable -- the sector arm still publishes."""
    p = data_root / "baskets" / "membership.json"
    try:
        raw = json.loads(p.read_text())
    except Exception as exc:                                    # noqa: BLE001
        print(f"::warning title=basket-washout-membership::membership store unreadable "
              f"({p.name}: {exc}) - publishing the GICS-sector arm only", flush=True)
        return {}
    out: dict[str, dict] = {}
    for bid, b in (raw.get("baskets") or {}).items():
        if not isinstance(b, dict):
            continue
        members = []
        for m in b.get("members") or []:
            if not isinstance(m, dict) or m.get("removed"):
                continue
            t = m.get("ticker")
            if isinstance(t, str) and t.strip():
                members.append(t.strip())
        out[str(bid)] = {
            "name": b.get("name") or str(bid),
            "name_zh": b.get("name_zh") or b.get("name") or str(bid),
            "members": sorted(dict.fromkeys(members)),
        }
    return out


def load_sector_map(data_root: Path) -> dict[str, str]:
    """ticker -> GICS sector, from the breadth store (+ the prophet candidates' own sector
    column when that lane has run, mirroring the study's union)."""
    out: dict[str, str] = {}
    p = data_root / "breadth" / "ticker_sectors.parquet"
    try:
        ts = pd.read_parquet(p, columns=["ticker", "sector"])
        for t, s in zip(ts["ticker"], ts["sector"]):
            if isinstance(t, str) and isinstance(s, str) and s in GICS:
                out.setdefault(t, s)
    except Exception as exc:                                    # noqa: BLE001
        print(f"::warning title=basket-washout-sectors::GICS sector store unreadable "
              f"({p.name}: {exc}) - publishing the basket arm only", flush=True)
    cand = data_root / "us_prophet_rank" / "candidates"
    if cand.is_dir():
        for f in sorted(cand.glob("*.parquet"))[-2:]:           # newest months only (cheap)
            try:
                c = pd.read_parquet(f, columns=["ticker", "sector"])
            except Exception:                                   # noqa: BLE001
                continue
            for t, s in zip(c["ticker"], c["sector"]):
                if isinstance(t, str) and isinstance(s, str) and s in GICS:
                    out.setdefault(t, s)
    return out


def panel_paths(data_root: Path) -> dict[str, list[Path]]:
    """symbol -> the price parquets that carry it (the deep store and the OHLCV store are
    unioned per name, exactly as the study's loader does)."""
    out: dict[str, list[Path]] = {}
    for sub in ("stocks", "baskets/ohlcv"):
        d = data_root.joinpath(*sub.split("/"))
        if not d.is_dir():
            continue
        for p in d.glob("*.parquet"):
            if p.name.startswith("_"):
                continue
            out.setdefault(p.stem, []).append(p)
    return out


# ----------------------------------------------------------------- drawdowns --
def drawdown_series(close: pd.Series) -> pd.Series:
    """close / trailing-252 max - 1, on a sorted DatetimeIndex."""
    c = pd.to_numeric(close, errors="coerce").astype("float64").dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    if c.empty:
        return c
    return c / c.rolling(WINDOW, min_periods=MIN_PERIODS).max() - 1.0


def compute_drawdowns(paths: dict[str, list[Path]], symbols: set[str]) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for sym in sorted(symbols):
        ser: pd.Series | None = None
        for p in paths.get(sym, ()):
            try:
                c = pd.read_parquet(p, columns=["close"])["close"]
            except Exception:                                   # noqa: BLE001
                continue
            if not isinstance(c.index, pd.DatetimeIndex):
                continue
            ser = c if ser is None else c.combine_first(ser)
        if ser is None:
            continue
        dd = drawdown_series(ser)
        if not dd.empty:
            out[sym] = dd
    return out


def group_median(dd: dict[str, pd.Series], members, as_of: pd.Timestamp) -> tuple[float | None, int]:
    """Median drawdown across the members that PRINT on `as_of`.  Names with no print that
    session drop out (halted / delisted / not yet collected) rather than being carried."""
    vals = []
    for m in members:
        s = dd.get(m)
        if s is None:
            continue
        try:
            v = s.get(as_of)
        except Exception:                                       # noqa: BLE001
            continue
        if v is None or not np.isfinite(v):
            continue
        vals.append(float(v))
    if len(vals) < MIN_PEERS:
        return None, len(vals)
    return float(np.median(vals)), len(vals)


def primary_basket(defs: dict[str, dict], ticker: str) -> str | None:
    """The most thematically specific basket claiming this name: fewest curated members,
    ties broken by id.  Baskets thinner than MIN_PEERS never claim a name."""
    cand = [b for b, d in defs.items()
            if ticker in d["members"] and len(d["members"]) >= MIN_PEERS]
    if not cand:
        return None
    return min(sorted(cand), key=lambda b: len(defs[b]["members"]))


def _qualifies(value: float) -> dict[str, bool]:
    return {str(t): bool(value <= -t / 100.0) for t in THRESHOLDS}


# -------------------------------------------------------------------- builder --
def build_state(defs: dict[str, dict], sectors: dict[str, str],
                dd: dict[str, pd.Series], as_of: pd.Timestamp | None = None) -> dict:
    """Assemble the frozen v1 payload.  Pure: every input is already in memory."""
    if as_of is None:
        stamps = [s.index[-1] for s in dd.values() if len(s.index)]
        as_of = max(stamps) if stamps else None
    payload: dict = {
        "schema": SCHEMA,
        "as_of": None if as_of is None else str(pd.Timestamp(as_of).date()),
        "thresholds": list(THRESHOLDS),
        "baskets": {},
        "names": {},
    }
    if as_of is None:
        return payload
    as_of = pd.Timestamp(as_of)

    basket_state: dict[str, float] = {}
    for bid in sorted(defs):
        med, n = group_median(dd, defs[bid]["members"], as_of)
        if med is None:
            continue
        med = round(med, ROUND)
        basket_state[bid] = med
        payload["baskets"][bid] = {
            "name": defs[bid]["name"],
            "name_zh": defs[bid]["name_zh"],
            "peer_median_dd_252": med,
            "n_members": n,
            "qualifies": _qualifies(med),
        }

    sector_members: dict[str, list[str]] = {}
    for t, s in sectors.items():
        sector_members.setdefault(s, []).append(t)
    sector_state: dict[str, float] = {}
    for s in sorted(sector_members):
        med, _n = group_median(dd, sector_members[s], as_of)
        if med is not None:
            sector_state[s] = round(med, ROUND)

    # A name reads through its primary basket; if that basket could not state a number
    # tonight it falls back to its GICS sector; a name with neither is OMITTED.
    universe = sorted(set(dd) | {t for d in defs.values() for t in d["members"]} | set(sectors))
    for t in universe:
        bid = primary_basket(defs, t)
        if bid is not None and bid in basket_state:
            basis, gid, val = "basket", bid, basket_state[bid]
        else:
            s = sectors.get(t)
            if s is None or s not in sector_state:
                continue
            basis, gid, val = "sector", s, sector_state[s]
        payload["names"][t] = {
            "basis": basis,
            "group_id": gid,
            "peer_dd": val,
            "qualifies": _qualifies(val),
        }
    return payload


def write_state(payload: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build site/factordata/basket_washout_state.json")
    ap.add_argument("--data-root", default=None, help="override the data/ root")
    ap.add_argument("--out", default=None, help="override the output JSON path")
    a = ap.parse_args(argv)

    data_root = Path(a.data_root) if a.data_root else config.data_dir()
    out = Path(a.out) if a.out else config.site_dir() / "factordata" / "basket_washout_state.json"

    defs = load_basket_defs(data_root)
    sectors = load_sector_map(data_root)
    paths = panel_paths(data_root)
    need = ({t for d in defs.values() for t in d["members"]} | set(sectors)) & set(paths)
    if not need:
        print("::warning title=basket-washout-empty::no basket or GICS names resolve against "
              "the price panel - leaving the previous artifact in place", flush=True)
        return 0
    dd = compute_drawdowns(paths, need)
    payload = build_state(defs, sectors, dd)
    if not payload["names"]:
        print("::warning title=basket-washout-empty::no group could state a peer median - "
              "leaving the previous artifact in place", flush=True)
        return 0
    write_state(payload, out)
    q25 = sum(1 for b in payload["baskets"].values() if b["qualifies"]["25"])
    log.info("basket_washout_state as_of=%s baskets=%d (%d qualify @25%%) names=%d -> %s",
             payload["as_of"], len(payload["baskets"]), q25, len(payload["names"]), out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
