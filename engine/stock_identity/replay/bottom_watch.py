"""Terminal Bottom Watch — the Class B locked-spec C5 port (Radar contract §3.4).

The Terminal computes this per request and persists nothing, and G-8 forbids running
Terminal internals, so the lawful route is the Radar contract's declared fallback: a
Macro-side locked-spec reproduction with a declared parity fixture, stamped Class B on
every row.

Spec, verbatim from Live Entry Radar contract §3.4::

    washout context = W1 ∧ (W2a ∨ W2b) ∧ W3
    candidates      = (early_dot | blocked CB/revBuy trigger) & washed
    kind ∈ {early_dot, blocked_trigger}, blocked_trigger taking precedence
                                          and DE-DUPLICATING the dot

The washout legs live in :func:`..grey_dot.washout_context` (they are shared with the amber
carve-out predicate and must not be implemented twice). What this module adds is the
candidate union and the precedence rule.

**The de-duplication is expressed as a typed edge, never as a deleted row.** When a
``blocked_trigger`` and an ``early_dot`` land on the same bar, both are emitted and a
``dedup_suppressed_by`` edge records that the emitter would have shown one. Deleting the
dot would destroy the honest count of how often the two coincide — and the Radar contract
already records that this de-dup is "known-lossy from the artifact" (§3.2 F3).

The ``promoted_by`` edge from a ``grey_dot_macro`` fire to its bottom-watch event is minted
by the pilot CLI, which is the only place both event tables exist at once.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from engine.signal_quality import signal_frame

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grey_dot import washout_context
from engine.stock_identity.replay.grid import KNOWN_BASIS_BUCKET, macro_grid

__all__ = ["FAMILY_KEY", "ERA", "KIND_DOT", "KIND_BLOCKED", "constants", "fires"]

FAMILY_KEY = "bottom_watch_terminal"

#: The Terminal's own signal era, per Radar contract §3.1.
ERA = "gc_v2_wo2"

KIND_DOT = "early_dot"
KIND_BLOCKED = "blocked_trigger"


def constants() -> dict[str, Any]:
    return {
        "producer": "charting-app confluence_v2 bottom_watch (locked-spec port)",
        "spec_source": "research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md §3.4",
        "signal_era": ERA,
        "washout_context": "W1 ∧ (W2a ∨ W2b) ∧ W3",
        "w1": "monthly RSI-MACD bear ∧ below 200DMA ∧ 2W RSI-MACD not bull",
        "w2a": "252-session drawdown <= -35%",
        "w2b": "prior-closed monthly StochRSI-D < 20 for >= 3 consecutive months",
        "w3": "3D StochRSI-D oversold visit within 8 bars (min_periods=1)",
        "candidates": "(early_dot | blocked CB/revBuy trigger) & washed",
        "precedence": "blocked_trigger over early_dot; de-dup recorded as a typed edge",
        "port_deviation": (
            "the 'blocked' half is taken as the CB/revBuy trigger firing while the name is "
            "below its 200-session average — the Terminal's own block verdict is produced "
            "by machinery this program may not import, and inventing a verdict would be "
            "worse than declaring the approximation"
        ),
    }


def fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bottom-watch candidates on completed 3D buckets.

    Returns ``(event rows, dedup edge rows)``.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else None
    low = df["low"].astype(float) if "low" in df.columns else None
    frame = signal_frame(close, high, low, market="US")
    if frame is None or frame.empty:
        return [], []
    grid = macro_grid(close, 3)
    if len(grid) != len(frame):
        return [], []

    completed = grid.completed_mask()
    ctx = washout_context(
        close,
        bar_known=pd.DatetimeIndex(grid.known.to_numpy()),
        d3=frame["d"],
        below_200=(~frame["above200"].fillna(False).astype(bool)).to_numpy(),
    )
    washed = ctx["washed"].to_numpy()
    below200 = (~frame["above200"].fillna(False).astype(bool)).to_numpy()

    dot = frame["early"].fillna(False).to_numpy().astype(bool)
    trigger = (
        frame["CB"].fillna(False).to_numpy().astype(bool)
        | frame["revBuy"].fillna(False).to_numpy().astype(bool)
    )
    blocked = trigger & below200

    cand_dot = dot & washed & completed
    cand_blocked = blocked & washed & completed

    rows: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for i in np.flatnonzero(cand_dot | cand_blocked):
        signal_ts = pd.Timestamp(grid.label[i])
        known_ts = pd.Timestamp(grid.known.iloc[i])
        kinds = []
        if cand_blocked[i]:
            kinds.append(KIND_BLOCKED)
        if cand_dot[i]:
            kinds.append(KIND_DOT)
        for kind in kinds:
            rows.append(ev.make_event(
                family_key=FAMILY_KEY,
                producer="charting-app confluence_v2 bottom_watch (locked-spec port)",
                family="bottom_watch",
                subtype=kind,
                stage="WATCH",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="3D",
                signal_ts=signal_ts,
                signal_known_ts=known_ts,
                known_basis=KNOWN_BASIS_BUCKET,
                signal_era=ERA,
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="replay_recomputed",
                provenance_class="B",
                family_first_available=family_first_available,
                scored_authority=False,
                spec_postdates_history=True,
                in_washout_context=True,
                context={
                    "w1": bool(ctx["w1"].iloc[i]),
                    "w2a": bool(ctx["w2a"].iloc[i]),
                    "w2b": bool(ctx["w2b"].iloc[i]),
                    "w3": bool(ctx["w3"].iloc[i]),
                    "kind": kind,
                },
            ))
        if len(kinds) == 2:
            # Precedence: blocked_trigger de-duplicates the dot. Both rows survive; the
            # edge is what records that the emitter would have shown one.
            edges.append(ev.make_edge(
                relation="dedup_suppressed_by",
                source_event_id=ev.event_id(FAMILY_KEY, symbol, signal_ts, KIND_DOT),
                target_event_id=ev.event_id(FAMILY_KEY, symbol, signal_ts, KIND_BLOCKED),
                symbol=symbol,
                source_family_key=FAMILY_KEY,
                target_family_key=FAMILY_KEY,
                note="blocked_trigger takes precedence over early_dot (Radar §3.4)",
            ))
    return rows, edges
