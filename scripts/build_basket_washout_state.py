"""Nightly basket-washout state + history -> site/factordata/basket_washout_{state,history}.json.

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
  * `qualifies[t]` is recomputed from the PUBLISHED (rounded) number, so a consumer that
    re-derives the flag from `peer_median_dd_252` / `peer_dd` always agrees with us

THE TWO MAPS ANSWER DIFFERENT QUESTIONS -- read the field you actually mean:
  * `baskets[<id>].peer_median_dd_252` describes the GROUP: the plain median over every
    member that printed, no exclusions.  It is a basket-level state chip.
  * `names[<TICKER>].peer_dd` is the LEAVE-ONE-OUT median -- the name's peers with the
    name ITSELF removed.  This is the quantity r3_axes.py computed per event, so it is
    the one every published gate was measured on.  A name is usually among the deepest
    drawdowns in its own basket, so letting it vote in its own peer median would ship a
    systematically MORE PERMISSIVE rule than the one that passed the gauntlet.  The two
    numbers therefore differ, and names inside one basket differ from each other.
    The MIN_PEERS floor applies to the FULL group (as upstream), so a 5-member group
    leaves a 4-peer read.

Basket membership comes from the curated store `data/baskets/membership.json` (the same
source `scripts/build_baskets.py` and the prophet candidates' `theme_membership_ids`
descend from); members carrying a `removed` date are dropped.

SECOND ARTIFACT -- `basket_washout_history.v1` (operator directive 2026-08-10, "historical
fires must be re-markable under the as-shipped rule"): per name, the date-INTERVALS during
which it qualified, over its full available history, on the same leave-one-out read and the
same group the state artifact gives it.  `intervals` is keyed PER NOTCH ({"20": [...],
"25": [...], "30": [...]}), so moving the live dial -- 20 as of 2026-08-10 -- is a
consumer-side change that never needs this artifact rebuilt.  Interval ends are inclusive;
a null end means the run reaches `as_of`.  Crossings are printed RAW -- no smoothing, no
minimum length -- because the shipped rule is evaluated per fire date, so a one-session
qualifying window really does admit a fire that lands in it.
IT IS A RETRO-APPLIED LENS, NOT A RECORD OF CALLS MADE: today's rosters are applied to the
whole past (see HISTORY_NOTES, which ships inside the artifact).

COST: reads only the names it needs (basket members + GICS-mapped names), one close column
each, ~2-5s wall on the full US panel; the history pass adds ~4s (one argsort per group
rather than a per-date median sweep -- see loo_median_matrix).  Measured end-to-end at ~9s,
so it is a full recompute every night: no incremental store, nothing to go stale, and still
an order of magnitude inside the budget.  It is a nightly display artifact and must stay off
the render-critical path.

Usage: python -m scripts.build_basket_washout_state [--data-root DIR] [--out FILE]
                                                    [--history-out FILE] [--no-history]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_basket_washout_state")

SCHEMA = "basket_washout_state.v1"
SCHEMA_HISTORY = "basket_washout_history.v1"
THRESHOLDS = (20, 25, 30)          # published menu (packet §2); the live dial moves inside it
WINDOW = 252                       # trading-day high water mark
MIN_PERIODS = 60                   # a name needs a quarter of history before it has a high
MIN_PEERS = 5                      # a group thinner than this states nothing
ROUND = 6

HISTORY_NOTES = (
    "Qualifying date-intervals on the same leave-one-out peer read as "
    "basket_washout_state.v1's names map. KEYED PER NOTCH: `intervals` is a map "
    "{\"20\": [...], \"25\": [...], \"30\": [...]} over the whole published menu, so moving "
    "the live dial is a consumer-side change and never needs this artifact rebuilt. All "
    "three keys are always present; an empty list means the name never qualified at that "
    "notch. RETRO-APPLIED, NOT LIVE CALLS: intervals are computed with TODAY's basket "
    "rosters and TODAY's GICS map over each name's full available history, so a name is "
    "scored against peers it may not have had at the time and against members curated "
    "later. Anything a consumer derives from this artifact must be labelled retro-applied "
    "— it is a re-marking lens for historical fires, never a record of calls that were "
    "made. Interval ends are INCLUSIVE (the last date the name qualified); a null end "
    "means the run reaches as_of and is still open. Crossings are RAW: no smoothing and no "
    "minimum length, because the shipped rule is evaluated per fire date, so a one-session "
    "window really does admit a fire that lands in it. A name's domain is the dates its own "
    "252d drawdown is defined AND its group had at least 5 members printing, so a gap in "
    "either breaks a run. Names with no interval at any notch are omitted."
)

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


def group_values(dd: dict[str, pd.Series], members, as_of: pd.Timestamp) -> dict[str, float]:
    """member -> its drawdown ON `as_of`.  Names with no print that session drop out
    (halted / delisted / not yet collected) rather than being carried forward."""
    vals: dict[str, float] = {}
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
        vals[m] = float(v)
    return vals


def group_median(dd: dict[str, pd.Series], members, as_of: pd.Timestamp) -> tuple[float | None, int]:
    """The GROUP's own state: median across every member that printed, no exclusions.
    Under MIN_PEERS printing members the group states nothing."""
    vals = group_values(dd, members, as_of)
    if len(vals) < MIN_PEERS:
        return None, len(vals)
    return float(np.median(list(vals.values()))), len(vals)


def leave_one_out_median(values: dict[str, float], ticker: str) -> float | None:
    """The NAME's read: the median of its peers with the name itself removed.  This is the
    quantity the study's per-event `peer_dd` was computed on -- a name in deep drawdown must
    not be able to vote itself into its own washout evidence.  The MIN_PEERS floor is
    applied to the FULL group upstream (as in r3_axes.py), so a 5-member group leaves 4."""
    peers = [v for t, v in values.items() if t != ticker]
    if not peers:
        return None
    return float(np.median(peers))


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

    # Each group's per-member values are computed ONCE and kept: the basket map reads their
    # plain median, every name in the group reads the same values minus itself.
    basket_vals: dict[str, dict[str, float]] = {}
    for bid in sorted(defs):
        vals = group_values(dd, defs[bid]["members"], as_of)
        if len(vals) < MIN_PEERS:
            continue
        basket_vals[bid] = vals
        med = round(float(np.median(list(vals.values()))), ROUND)
        payload["baskets"][bid] = {
            "name": defs[bid]["name"],
            "name_zh": defs[bid]["name_zh"],
            "peer_median_dd_252": med,
            "n_members": len(vals),
            "qualifies": _qualifies(med),
        }

    sector_members: dict[str, list[str]] = {}
    for t, s in sectors.items():
        sector_members.setdefault(s, []).append(t)
    sector_vals: dict[str, dict[str, float]] = {}
    for s in sorted(sector_members):
        vals = group_values(dd, sector_members[s], as_of)
        if len(vals) >= MIN_PEERS:
            sector_vals[s] = vals

    # A name reads through its primary basket; if that basket could not state a number
    # tonight it falls back to its GICS sector; a name with neither is OMITTED.
    universe = sorted(set(dd) | {t for d in defs.values() for t in d["members"]} | set(sectors))
    for t in universe:
        bid = primary_basket(defs, t)
        if bid is not None and bid in basket_vals:
            basis, gid, vals = "basket", bid, basket_vals[bid]
        else:
            s = sectors.get(t)
            if s is None or s not in sector_vals:
                continue
            basis, gid, vals = "sector", s, sector_vals[s]
        loo = leave_one_out_median(vals, t)
        if loo is None:
            continue
        loo = round(loo, ROUND)
        payload["names"][t] = {
            "basis": basis,
            "group_id": gid,
            "peer_dd": loo,
            "qualifies": _qualifies(loo),
        }
    return payload


# -------------------------------------------------------------------- history --
def loo_median_matrix(V: np.ndarray) -> np.ndarray:
    """Leave-one-out median for EVERY cell of a (dates x members) drawdown matrix.

    `V[t, j]` is member j's drawdown on date t, NaN where it did not print.  Returns an
    array of the same shape whose `[t, j]` is the median of row t's finite values with
    column j removed -- the same quantity `leave_one_out_median()` computes one name at a
    time, and the identity is pinned by a test.  Cells where j did not print, and whole
    rows under MIN_PEERS, come back NaN.

    Done by ranking instead of by looping: removing ANY element equal to v leaves the same
    sorted remainder, so a member's leave-one-out median is a fixed offset into the row's
    sorted values, decided only by its rank.  With k finite values in the row and the
    member at rank r (0-based, ascending):
        k even (k=2m): one value remains at the middle -- sorted[m] if r <= m-1 else sorted[m-1]
        k odd  (k=2m+1): two do -- (m, m+1) if r < m; (m-1, m+1) if r == m; (m-1, m) if r > m
    That turns an O(T*k) median sweep into one argsort per group.
    """
    if V.ndim != 2 or V.shape[1] == 0:
        return np.full(V.shape, np.nan)
    T, k = V.shape
    finite = np.isfinite(V)
    cnt = finite.sum(axis=1)

    order = np.argsort(np.where(finite, V, np.inf), axis=1, kind="stable")
    S = np.take_along_axis(V, order, axis=1)                 # finite ascending, NaN last
    ranks = np.empty((T, k), dtype=np.int64)
    np.put_along_axis(ranks, order, np.broadcast_to(np.arange(k), (T, k)), axis=1)

    out = np.full((T, k), np.nan)
    usable = cnt >= MIN_PEERS
    if not usable.any():
        return out

    even = usable & (cnt % 2 == 0)
    odd = usable & (cnt % 2 == 1)

    if even.any():
        m = (cnt[even] // 2)[:, None]
        r = ranks[even]
        idx = np.where(r <= m - 1, m, m - 1)
        out[even] = np.take_along_axis(S[even], idx, axis=1)
    if odd.any():
        m = ((cnt[odd] - 1) // 2)[:, None]
        r = ranks[odd]
        lo = np.where(r < m, m, m - 1)
        hi = np.where(r <= m, m + 1, m)
        So = S[odd]
        out[odd] = (np.take_along_axis(So, lo, axis=1)
                    + np.take_along_axis(So, hi, axis=1)) / 2.0

    out[~finite] = np.nan          # a name that did not print has no reading that session
    return out


def _runs_to_intervals(index: np.ndarray, mask: np.ndarray, as_of: pd.Timestamp) -> list:
    """Contiguous True runs of `mask` over `index` -> [[start, end], ...], end INCLUSIVE and
    null when the run reaches `as_of`."""
    if not mask.any():
        return []
    padded = np.concatenate(([False], mask, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    out = []
    for a, b in zip(edges[0::2], edges[1::2]):
        start = pd.Timestamp(index[a])
        end = pd.Timestamp(index[b - 1])
        out.append([str(start.date()), None if end >= as_of else str(end.date())])
    return out


def build_history(dd: dict[str, pd.Series], defs: dict[str, dict], sectors: dict[str, str],
                  state: dict) -> dict:
    """Per-name qualifying intervals at the ratified notch, over full available history.

    Group membership and each name's basis/group_id are taken STRAIGHT from the state
    payload, so the two artifacts can never disagree about which peers a name reads.
    """
    as_of_str = state.get("as_of")
    payload: dict = {
        "schema": SCHEMA_HISTORY,
        "as_of": as_of_str,
        "notches": list(THRESHOLDS),
        "notes": HISTORY_NOTES,
        "names": {},
    }
    if not as_of_str or not state.get("names"):
        return payload
    as_of = pd.Timestamp(as_of_str)

    sector_members: dict[str, list[str]] = {}
    for t, s in sectors.items():
        sector_members.setdefault(s, []).append(t)

    by_group: dict[tuple[str, str], list[str]] = {}
    for t, e in state["names"].items():
        by_group.setdefault((e["basis"], e["group_id"]), []).append(t)

    for (basis, gid), names in sorted(by_group.items()):
        members = defs[gid]["members"] if basis == "basket" else sector_members.get(gid, [])
        cols = [m for m in sorted(set(members)) if m in dd]
        if len(cols) < MIN_PEERS:
            continue
        frame = pd.DataFrame({m: dd[m] for m in cols}).sort_index()
        frame = frame[frame.index <= as_of]
        if frame.empty:
            continue
        idx = frame.index.to_numpy()
        loo = np.round(loo_median_matrix(frame.to_numpy(dtype="float64")), ROUND)
        pos = {c: i for i, c in enumerate(frame.columns)}
        for t in sorted(names):
            j = pos.get(t)
            if j is None:                       # mapped to the group but never priced
                continue
            col = loo[:, j]
            live = np.isfinite(col)
            per_notch = {str(n): _runs_to_intervals(idx, live & (col <= -n / 100.0), as_of)
                         for n in THRESHOLDS}
            if any(per_notch.values()):
                payload["names"][t] = {
                    "basis": basis, "group_id": gid, "intervals": per_notch,
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
    ap.add_argument("--history-out", default=None, help="override the history JSON path")
    ap.add_argument("--no-history", action="store_true",
                    help="skip the interval pass (state artifact only)")
    a = ap.parse_args(argv)

    data_root = Path(a.data_root) if a.data_root else config.data_dir()
    out = Path(a.out) if a.out else config.site_dir() / "factordata" / "basket_washout_state.json"
    hist_out = (Path(a.history_out) if a.history_out
                else out.with_name("basket_washout_history.json"))

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

    if not a.no_history:
        t0 = time.monotonic()
        hist = build_history(dd, defs, sectors, payload)
        if hist["names"]:
            write_state(hist, hist_out)
            per = {n: (sum(len(v["intervals"][str(n)]) for v in hist["names"].values()),
                       sum(1 for v in hist["names"].values()
                           if v["intervals"][str(n)] and v["intervals"][str(n)][-1][1] is None))
                   for n in THRESHOLDS}
            log.info("basket_washout_history names=%d %s (%.1fs) -> %s",
                     len(hist["names"]),
                     " ".join(f"{n}%:{s}iv/{o}open" for n, (s, o) in per.items()),
                     time.monotonic() - t0, hist_out)
        else:
            print("::warning title=basket-washout-history-empty::no name produced a "
                  "qualifying interval - leaving the previous history artifact in place",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
