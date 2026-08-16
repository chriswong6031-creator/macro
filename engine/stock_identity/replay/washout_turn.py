"""The weekly washout->turn organ: the committed ledger union the earlier recompute.

Two arms again, and again not merged:

**Ledger arm** (``ledger_recorded``). ``data/washout_turn/ledger.jsonl`` is the organ's own
nightly transitions-only record. Extraction is a **pure filter** — rows are read, selected
by symbol, and never rewritten; a duplicate ``(session, symbol, state)`` keeps the FIRST
occurrence, which is the one that was actually published. The ledger is young (it begins
when the organ shipped), so it covers a handful of sessions and nothing before them. That
is ``family_first_available`` honesty, not a coverage failure.

**Recompute arm** (``replay_recomputed``). Earlier history is recovered by walking the
name's own weekly bars and calling the organ's OWN pure entry point,
:func:`engine.washout_turn.compute_symbol_washout`, on the frame **truncated at that bar**.

Truncation is not a convenience here, it is the correctness argument. The organ's depth
percentile is a WHOLE-SAMPLE statistic — ``_evaluate`` documents it as "percent of the FULL
weekly line history strictly BELOW bar j" — so evaluating it once over the complete series
would let a bar's qualification depend on bars that had not happened yet. Calling the organ
on ``close.loc[:t]`` makes every read a function of the prefix by construction, which is
exactly what truncation invariance asks for and what a single-pass re-implementation would
have quietly failed.

An event is a **transition into** ``WASHOUT_TURN`` (or ``TURN_WATCH``) from a different
state — the same convention the organ's own ledger uses. ``signal_ts`` is the weekly bar's
first actual session, ``signal_known_ts`` its last: the W-FRI label is a calendar date the
name may never have traded, so it is carried as context, never as a stamp.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from engine.washout_turn import (
    CANON_PARAMS,
    DEPTH_PCTILE_MAX,
    FAIL_HIST_BARS,
    MIN_WEEKLY_BARS,
    SCHEMA,
    STATE_TURN,
    STATE_WATCH,
    compute_symbol_washout,
)

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grid import KNOWN_BASIS_WEEKLY, weekly_completed

__all__ = ["FAMILY_KEY", "ERA", "LEDGER_PATH", "constants", "load_ledger",
           "ledger_fires", "recompute_fires"]

FAMILY_KEY = "weekly_washout_turn"
LEDGER_PATH = "data/washout_turn/ledger.jsonl"

#: The organ publishes ``washout_turn.v1``; that schema string IS its era receipt.
ERA = SCHEMA

#: A truncated-frame walk is O(n^2) in weekly bars. Bars before the organ can say anything
#: (``MIN_WEEKLY_BARS``) are skipped outright rather than called and discarded.
_WARMUP = MIN_WEEKLY_BARS


def constants() -> dict[str, Any]:
    return {
        "producer": "engine.washout_turn:compute_symbol_washout",
        "schema": SCHEMA,
        "min_weekly_bars": MIN_WEEKLY_BARS,
        "depth_pctile_max": DEPTH_PCTILE_MAX,
        "fail_hist_bars": FAIL_HIST_BARS,
        "canon_params": dict(CANON_PARAMS),
        "grain": "W-FRI completed bars only",
        "event_convention": "transition INTO a state (the organ's own ledger convention)",
        "replay_method": (
            "the organ's own pure function called on the frame truncated at each weekly "
            "bar — its depth percentile is a whole-sample statistic, so a single-pass "
            "evaluation over the full series would not be causal"
        ),
    }


def load_ledger(repo_root: str | Path, symbols: list[str] | None = None) -> pd.DataFrame:
    """The organ's committed transitions ledger — read, filtered, never rewritten."""
    p = Path(repo_root) / LEDGER_PATH
    if not p.exists():
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001 — a malformed line is skipped, never guessed at
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if symbols is not None and "symbol" in df.columns:
        df = df[df["symbol"].isin(symbols)]
    if df.empty:
        return df
    df = df.copy()
    df["session"] = pd.to_datetime(df["session"])
    return df.drop_duplicates(subset=["session", "symbol", "state"], keep="first")


def ledger_fires(
    ledger: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> list[dict[str, Any]]:
    if ledger is None or ledger.empty or "symbol" not in ledger.columns:
        return []
    sub = ledger[ledger["symbol"] == symbol]
    rows: list[dict[str, Any]] = []
    for r in sub.itertuples(index=False):
        state = str(getattr(r, "state", "") or "")
        if state not in (STATE_TURN, STATE_WATCH):
            continue
        ts = pd.Timestamp(r.session)
        rows.append(ev.make_event(
            family_key=FAMILY_KEY,
            producer="engine.washout_turn -> data/washout_turn/ledger.jsonl",
            family="weekly_washout_turn",
            subtype=state,
            stage="ORGAN",
            symbol=symbol,
            price_plane_id=price_plane_id,
            grain="W",
            signal_ts=ts,
            signal_known_ts=ts,
            known_basis=KNOWN_BASIS_WEEKLY,
            signal_era=ERA,
            detector_spec_hash=spec_hash,
            source_hash=spec_hash,
            field_origin="ledger_recorded",
            provenance_class="R",
            family_first_available=family_first_available,
            scored_authority=False,
            spec_postdates_history=False,
            context={
                "prior_state": str(getattr(r, "prior_state", "") or "") or None,
                "since": str(getattr(r, "since", "") or "") or None,
                "data_through": str(getattr(r, "data_through", "") or "") or None,
            },
        ))
    return rows


def recompute_fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
    stop_before: pd.Timestamp | None = None,
    step: int = 1,
) -> list[dict[str, Any]]:
    """Truncated-frame walk over completed weekly bars.

    ``stop_before`` bounds the recompute at the ledger's first session, so the two arms
    never both claim the same bar. ``step`` is a stride over weekly bars for a cheap smoke
    run; the shipped extraction uses ``step=1``.
    """
    close = df["close"].astype(float).dropna().sort_index()
    bars = weekly_completed(close)
    if bars.empty or len(bars) <= _WARMUP:
        return []

    rows: list[dict[str, Any]] = []
    prev_state: str | None = None
    for i in range(_WARMUP, len(bars), max(1, int(step))):
        known = pd.Timestamp(bars["known"].iloc[i])
        if stop_before is not None and known >= pd.Timestamp(stop_before):
            break
        truncated = close.loc[:known]
        receipts = compute_symbol_washout(truncated)
        state = str(receipts.get("state")) if isinstance(receipts, dict) else None
        if state not in (STATE_TURN, STATE_WATCH):
            state = None
        if state and state != prev_state:
            rows.append(ev.make_event(
                family_key=FAMILY_KEY,
                producer="engine.washout_turn:compute_symbol_washout",
                family="weekly_washout_turn",
                subtype=state,
                stage="ORGAN",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="W",
                signal_ts=pd.Timestamp(bars["open"].iloc[i]),
                signal_known_ts=known,
                known_basis=KNOWN_BASIS_WEEKLY,
                signal_era=ERA,
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="replay_recomputed",
                provenance_class="R",
                family_first_available=family_first_available,
                scored_authority=False,
                spec_postdates_history=False,
                context={
                    "prior_state": prev_state,
                    "calendar_label": str(pd.Timestamp(bars["label"].iloc[i]).date()),
                },
            ))
        prev_state = state
    return rows
