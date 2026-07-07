"""Forward shadow-ledger for the Amendment-3 structural descriptors on the
bottom-sensor envelope — the "display chip + forward-ledger, no rank/bonus change"
ship-shape (mirrors engine/shadow_book.py; deployment ruling
research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md §F.3).

Two descriptors are graded live before either earns weight (CHIP-blocked until the
true eq_band lands, RUL-28):

  decline_geometry  — family E DISPLAY-CANDIDATE.  flush = trailing-63-bar loss
                      concentrated in few large down-days (forced supply that
                      empties) vs grind = loss spread evenly (distribution that
                      persists).  The program's cleanest survivor; graded here to
                      confirm the live edge before any promotion.
  underwater_state  — family F ADVERSE-CONTEXT (shadow-only, de-escalation lane).
                      long = longest under the trailing-252 peak = historically
                      higher stop-out; a caution axis, never a buy signal.

Three pure functions, append-only, leak-free by construction (verbatim shape of
engine.shadow_book):

  snapshot(date, recs)  — append (date, symbol, decline_geometry, decline_herf,
                          underwater_state, underwater_bars) frozen at the build
                          date.  Append-only + dedup by (date, symbol): a nightly
                          rebuild never overwrites or backfills history.
  mature(asof, closes)  — join only rows whose horizon has FULLY ELAPSED (the h-th
                          trading bar after `date` exists in `closes` AND its date
                          <= asof) to the realized forward return.  A horizon that
                          has not closed is NEVER graded.
  grade(matured)        — DESCRIPTIVE per-horizon forward-return gaps stratified by
                          decline_geometry (flush − grind) and underwater_state
                          (long − short).  No ranking, no weight, no allocation —
                          the output is an audit surface only.

Honest caveat shipped on every artifact: this is a survivor-only OPTIMISTIC bound
(free prices serve currently-listed names) and it is DISPLAY-ONLY — a positive
forward gap here does NOT promote either descriptor; promotion re-opens only when
the true eq_band cache lands (RUL-28) and re-runs the pre-registered study.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

BOOK_PATH = "data/shadow/bottom_sensors_geometry_book.jsonl"
HORIZONS = (21, 63)

# The state fields frozen per (date, symbol) at build time.
_STATE_FIELDS = ("decline_geometry", "decline_herf", "underwater_state", "underwater_bars")


# --------------------------------------------------------------------------- #
# snapshot (append-only, frozen at build time)
# --------------------------------------------------------------------------- #
def snapshot(date, recs, *, horizons=HORIZONS, path: str = BOOK_PATH) -> int:
    """Append frozen descriptor rows for `date`.  `recs` = iterable of dicts
    carrying at least `symbol` and the descriptor fields.  Returns rows written.
    Idempotent per (date, symbol): re-running a build does not duplicate or
    overwrite.  A row is written even when both descriptors are None (records the
    coverage gap honestly) — but a missing `symbol` is skipped."""
    d = str(pd.Timestamp(date).date())
    seen = _seen_keys(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n = 0
    with open(path, "a") as fh:
        for r in recs:
            t = r.get("symbol")
            if t is None or (d, t) in seen:
                continue
            row = {"date": d, "symbol": t}
            for f in _STATE_FIELDS:
                v = r.get(f)
                if isinstance(v, float) and not np.isfinite(v):
                    v = None
                row[f] = v
            row["horizons"] = list(horizons)
            fh.write(json.dumps(row, default=str) + "\n")
            seen.add((d, t))
            n += 1
    return n


def _seen_keys(path: str) -> set:
    out = set()
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                out.add((r.get("date"), r.get("symbol")))
            except Exception:
                continue
    return out


def load_book(path: str = BOOK_PATH) -> pd.DataFrame:
    cols = ["date", "symbol", *_STATE_FIELDS, "horizons"]
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)


# --------------------------------------------------------------------------- #
# mature (leak-free: only fully-elapsed horizons)
# --------------------------------------------------------------------------- #
def mature(asof, closes: pd.DataFrame, *, path: str = BOOK_PATH, horizons=HORIZONS) -> pd.DataFrame:
    """Join snapshot rows to realized forward returns for every horizon that has
    FULLY elapsed on or before `asof`.  `closes` = wide price panel
    (DatetimeIndex x symbol).  A (date, symbol, h) is matured ONLY if the h-th
    trading bar after `date` exists in `closes` and its date <= asof — so a
    not-yet-closed horizon is never graded (verbatim leak guard of shadow_book)."""
    book = load_book(path)
    if book.empty:
        return pd.DataFrame()
    asof = pd.Timestamp(asof)
    idx = closes.index
    out = []
    pos_of = {d: i for i, d in enumerate(idx)}
    for _, r in book.iterrows():
        t = r["symbol"]
        if t not in closes.columns:
            continue
        d0 = pd.Timestamp(r["date"])
        p0 = pos_of.get(d0)
        if p0 is None:                                  # snapshot date not a trading bar in panel
            after = idx[idx > d0]
            if len(after) == 0:
                continue
            p0 = pos_of[after[0]]
        base = closes.iloc[p0][t]
        if not np.isfinite(base) or base <= 0:
            continue
        for h in (r.get("horizons") or horizons):
            pe = p0 + int(h)
            if pe >= len(idx):                          # horizon hasn't generated enough bars yet
                continue
            d_end = idx[pe]
            if d_end > asof:                            # LEAK GUARD: horizon not fully elapsed
                continue
            px = closes.iloc[pe][t]
            if not np.isfinite(px):
                continue
            out.append({
                "date": r["date"], "symbol": t, "horizon": int(h),
                "decline_geometry": r.get("decline_geometry"),
                "underwater_state": r.get("underwater_state"),
                "fwd_ret": float(px / base - 1.0), "end_date": str(d_end.date()),
            })
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- #
# grade (DESCRIPTIVE stratified forward-return gaps — no weight)
# --------------------------------------------------------------------------- #
def _strat_gap(g: pd.DataFrame, col: str, hi: str, lo: str) -> dict:
    """Per-bucket mean forward return + (hi − lo) gap for one stratifier column.
    Descriptive only; None where a bucket is empty."""
    buckets = {}
    for label, sub in g.groupby(col):
        if label is None:
            continue
        buckets[str(label)] = {"mean_fwd_ret": float(sub["fwd_ret"].mean()), "n": int(len(sub))}
    gap = None
    if hi in buckets and lo in buckets:
        gap = buckets[hi]["mean_fwd_ret"] - buckets[lo]["mean_fwd_ret"]
    return {"buckets": buckets, f"{hi}_minus_{lo}": gap}


def grade(matured: pd.DataFrame) -> dict:
    """Per-horizon DESCRIPTIVE forward-return audit of the frozen descriptors:
    mean forward return per decline_geometry / underwater_state bucket and the
    flush−grind / long−short gaps.  Empty until horizons mature.  DISPLAY-ONLY:
    no ranking surface is touched and no gap here promotes either descriptor."""
    out = {"n_matured": int(len(matured)), "by_horizon": {}}
    if matured is None or matured.empty:
        return out
    for h, g in matured.groupby("horizon"):
        out["by_horizon"][f"h{int(h)}"] = {
            "n_obs": int(len(g)),
            "decline_geometry": _strat_gap(g, "decline_geometry", "flush", "grind"),
            "underwater_state": _strat_gap(g, "underwater_state", "long", "short"),
        }
    return out
