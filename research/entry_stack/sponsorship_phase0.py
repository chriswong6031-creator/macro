"""Phase 0 — Subsector Rotation Sponsorship Sensor (SRSS) research harness.

READ-ONLY join. No production artifact, no UI change, no signal, no gate.
Answers one question: when a stock-level gate fires, what does the (very
young) subsector-rotation PIT ledger say about the sponsorship environment
around it — and how often can we even answer that question at all?

Inputs (read-only):
  - data/subsector_rotation/snapshots.jsonl — PIT-frozen daily subsector
    rotation snapshots (engine/subsector_track_record.py is the producer).
    Fields actually on disk (confirmed by inspection, not assumed):
    date, key, name, theme, score (== emerging_score), rs_mom, accel,
    quadrant, stage, lean, members (frozen ticker list as of that date).
    NOTE: there is no `rs_ratio` field on this ledger — only `rs_mom`,
    `accel`, `score`. Substitutions per the research doc are used and
    logged (see _classify docstring).
  - data/research/gate_fires_deep.parquet — stock-level entry-gate fire
    events. Confirmed schema: ticker, date, tier, sub, ticks, not_topped,
    eligible, panel. `ticks` (ticks-since-fire) is reused directly as the
    freshness proxy the brief asked for — it is already exactly that.
    (data/neuralweb/spine_index.parquet was inspected too — it carries
    stock-level *outcome* fields (fwd_mfe_*, outcome_excess) keyed by
    engine/as_of/symbol/horizon, not a plain fire ledger, and none of the
    required output columns need those outcome fields in Phase 0, so it
    is left unused here — a deliberate scope call, not an oversight.)

Leak-prevention rule (research doc §8.5, followed exactly): a stock event
on date D may only join to a rotation snapshot row with date <= D, for a
subsector whose FROZEN member list (as recorded on that snapshot date)
contains the event's ticker. Never join to a rotation row dated after D.
If no such snapshot exists for that ticker as of D, the event is a
no-match (match_found=False) — not silently dropped, not back-filled.

distance-from-low proxy: no `dist_21d_low` (or similar) computation exists
anywhere in engine/ or scripts/ today (checked) — the field is only
mentioned as a *planned* future column in
research/ENTRY_STACK_EXPANSION_AMENDMENT1_BY_FABLE.md. Rather than invent
new OHLC math, this reuses the already-vetted price accessor
`engine.ai_desk._close_series` (same helper subsector_track_record.py
itself uses for forward returns) to build `close / rolling_21d_low(shifted
1) - 1` per ticker, sampled as-of the event date. This is a *proxy*,
explicitly named `derived_dist_proxy`, not a claim of the future
`dist_21d_low_pct` field's exact definition.

Everything here is read-only / display-only in spirit: it emits a research
parquet under `_out/` for follow-on study, not a production feed.

PHASE 2 NOTE: the nearest-prior-date join (``RotationIndex``) and the
sponsorship-state classification (``classify_sponsorship``) have been
factored out to ``engine.subsector_sponsorship`` so the production
shadow-tier pipeline (``engine.spine.adapt_subsector_sponsorship`` +
``engine.neuralweb.confluence``) reuses the exact same rules instead of a
second, subtly-different implementation. This module re-exports them under
their original private names (``_load_snapshots``, ``RotationIndex``,
``classify_sponsorship``, ``_confidence_tier``, ``_is_stale``,
``_STATES``) for source-compat with anything already importing this file.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from engine.ai_desk import _close_series  # reuse — do NOT reinvent price plumbing
from engine.subsector_sponsorship import (
    RotationIndex,
    STATES as _STATES,
    classify_sponsorship,
    confidence_tier as _confidence_tier,
    is_stale as _is_stale,
    load_snapshots as _load_snapshots,
)
from lib import config

log = logging.getLogger(__name__)

_SNAPSHOTS = ("data", "subsector_rotation", "snapshots.jsonl")
_FIRES = ("data", "research", "gate_fires_deep.parquet")
_OUT = ("research", "entry_stack", "_out", "sponsorship_phase0.parquet")

_STALE_TRADING_DAYS = 5
_DIST_WINDOW = 21


def _load_fires(root: Path) -> pd.DataFrame:
    p = Path(root, *_FIRES)
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"])
    return df


# --------------------------------------------------------------------------- #
# distance-from-low proxy (reuses engine.ai_desk._close_series)
# --------------------------------------------------------------------------- #
class DistProxyCache:
    def __init__(self, root: Path, window: int = _DIST_WINDOW):
        self._root = root
        self._window = window
        self._cache: dict[str, pd.Series | None] = {}

    def _series(self, ticker: str) -> pd.Series | None:
        if ticker in self._cache:
            return self._cache[ticker]
        s = None
        try:
            close = _close_series(ticker, self._root)
            if close is not None and len(close) > self._window:
                roll_low = close.rolling(self._window, min_periods=max(3, self._window // 3)).min().shift(1)
                s = (close / roll_low - 1.0).dropna()
        except Exception:  # noqa: BLE001
            s = None
        self._cache[ticker] = s
        return s

    def asof(self, ticker: str, event_date: pd.Timestamp) -> float | None:
        s = self._series(ticker)
        if s is None or s.empty:
            return None
        s2 = s[s.index <= event_date]
        if s2.empty:
            return None
        return round(float(s2.iloc[-1]), 4)


# --------------------------------------------------------------------------- #
# main join
# --------------------------------------------------------------------------- #
def build(root: Path | None = None) -> pd.DataFrame:
    root = Path(root) if root else config.ROOT
    snapshots = _load_snapshots(root)
    fires = _load_fires(root)
    ridx = RotationIndex(snapshots)
    dist_cache = DistProxyCache(root)

    rows = []
    for r in fires.itertuples(index=False):
        ticker = r.ticker
        event_date = r.date
        match = ridx.lookup(ticker, event_date)
        if match is None:
            rows.append({
                "ticker": ticker, "event_date": event_date, "tier": r.tier,
                "rotation_asof": None, "rotation_quadrant": None,
                "rotation_rs_mom": None, "rotation_accel": None,
                "rotation_score": None, "n_members": None,
                "confidence_tier": "none", "sponsorship_state": "NEUTRAL",
                "derived_freshness": r.ticks, "derived_dist_proxy": dist_cache.asof(ticker, event_date),
                "match_found": False, "_stale": False, "_rotation_key": None,
            })
            continue

        rotation_date = pd.Timestamp(match.get("date"))
        n_members = len(match.get("members") or [])
        stale = _is_stale(rotation_date, event_date)
        state = classify_sponsorship(
            match.get("quadrant"), match.get("rs_mom"), match.get("accel"),
            match.get("score"), n_members, stale,
        )
        rows.append({
            "ticker": ticker, "event_date": event_date, "tier": r.tier,
            "rotation_asof": rotation_date, "rotation_quadrant": match.get("quadrant"),
            "rotation_rs_mom": match.get("rs_mom"), "rotation_accel": match.get("accel"),
            "rotation_score": match.get("score"), "n_members": n_members,
            "confidence_tier": _confidence_tier(n_members), "sponsorship_state": state,
            "derived_freshness": r.ticks, "derived_dist_proxy": dist_cache.asof(ticker, event_date),
            "match_found": True, "_stale": stale, "_rotation_key": match.get("key"),
        })

    cols = [
        "ticker", "event_date", "tier", "rotation_asof", "rotation_quadrant",
        "rotation_rs_mom", "rotation_accel", "rotation_score", "n_members",
        "confidence_tier", "sponsorship_state", "derived_freshness",
        "derived_dist_proxy", "match_found", "_stale", "_rotation_key",
    ]
    out = pd.DataFrame(rows, columns=cols)
    return out


# columns emitted to the on-disk parquet — the two "_"-prefixed helper columns
# above (_stale, _rotation_key) are report-only scaffolding, dropped before write.
_OUTPUT_COLS = [
    "ticker", "event_date", "tier", "rotation_asof", "rotation_quadrant",
    "rotation_rs_mom", "rotation_accel", "rotation_score", "n_members",
    "confidence_tier", "sponsorship_state", "derived_freshness",
    "derived_dist_proxy", "match_found",
]


def coverage_report(df: pd.DataFrame) -> dict:
    total = len(df)
    if total == 0:
        return {
            "total_events": 0, "matched_pct": 0.0, "distinct_subsectors_matched": 0,
            "thin_pct": 0.0, "stale_pct": 0.0, "missing_pct": 0.0,
        }
    matched = df["match_found"]
    n_matched = int(matched.sum())
    missing = total - n_matched
    thin = int(((df["n_members"].notna()) & (df["n_members"] < 3)).sum())
    stale_col = df["_stale"] if "_stale" in df.columns else pd.Series(False, index=df.index)
    n_stale = int(stale_col.sum())
    key_col = df["_rotation_key"] if "_rotation_key" in df.columns else pd.Series(None, index=df.index)
    distinct_subsectors = int(key_col[matched].dropna().nunique())
    return {
        "total_events": total,
        "matched_pct": round(100.0 * n_matched / total, 2),
        "distinct_subsectors_matched": distinct_subsectors,
        "thin_pct": round(100.0 * thin / total, 2),
        "stale_pct": round(100.0 * n_stale / total, 2),
        "missing_pct": round(100.0 * missing / total, 2),
    }


def main() -> None:
    root = config.ROOT
    df = build(root)
    rep = coverage_report(df)

    print("=== SRSS Phase 0 coverage report ===")
    print(f"total events:               {rep['total_events']}")
    print(f"events with rotation match: {int(df['match_found'].sum())} ({rep['matched_pct']}%)")
    print(f"distinct subsectors matched: {rep['distinct_subsectors_matched']}")
    print(f"thin-share (n_members<3):   {rep['thin_pct']}%")
    print(f"stale-share (>{_STALE_TRADING_DAYS}bd old, of ALL events): {rep['stale_pct']}%")
    print(f"missing-share (no match):   {rep['missing_pct']}%")
    print("sponsorship_state distribution:")
    print(df["sponsorship_state"].value_counts().to_string())
    print("confidence_tier distribution:")
    print(df["confidence_tier"].value_counts().to_string())

    out_df = df[_OUTPUT_COLS]
    out_path = Path(root, *_OUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    print(f"wrote {out_path} ({len(out_df)} rows)")


if __name__ == "__main__":
    main()
