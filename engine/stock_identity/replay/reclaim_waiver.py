"""RE-ENTRY sense 2 — the reclaim waiver ("block repair"), over its own era ONLY.

The waiver admits a buy whose sole failing leg is the 200-day reclaim when the name's peer
group is washed out at the ratified notch. Its PIT input is a **single nightly artifact**,
``site/factordata/basket_washout_state.json``, which is overwritten every night and carries
exactly ONE ``as_of``. No historical vintage of it exists anywhere in the repo.

That is the whole story of this family, and the registration wrote the consequence in
advance: the waiver is re-derived **only over the committed artifact's own era**, with zero
synthesized context. Concretely the replayable window is
``[as_of, as_of + WASHOUT_MAX_STALE_SESSIONS]`` in the name's own sessions —
:func:`engine.signal_quality.reclaim_waiver_for` refuses anything outside it, in both
directions, and this module does not work around that refusal:

* ``as_of > known_date`` is future information and may never relieve an older label. This
  is precisely what stops a re-scan of history from silently waiving every past block.
* ``known_date - as_of > 5`` sessions means the state no longer describes the tape the fire
  is firing into.

So the honest event count for this family is *whatever fires inside one artifact vintage*,
which on a single committed vintage is usually zero. A zero here is a **structural absence**
(the state history was never kept), never evidence that the waiver does nothing — and the
registry records it as such. Manufacturing pre-``as_of`` waiver rows would require inventing
peer-group state, which the registration forbids by name.

Both halves of the decision come from the producer's own functions
(:func:`engine.signal_quality.washout_qualifier` and
:func:`engine.signal_quality.reclaim_waiver_for`); nothing about the notch, the staleness
ceiling, or the qualification flag is re-derived here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from engine.signal_quality import (
    ANCHOR_ERA as SQ_ANCHOR_ERA,
    WASHOUT_MAX_STALE_SESSIONS,
    WASHOUT_NOTCH,
    WASHOUT_STATE_PATH,
    WASHOUT_STATE_SCHEMA,
    confirmation_date,
    marker_last_session,
    reclaim_waiver_for,
    signal_frame,
    washout_qualifier,
)

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grid import KNOWN_BASIS_BUCKET, macro_grid

__all__ = ["FAMILY_KEY", "ERA", "constants", "load_state", "state_era", "fires"]

FAMILY_KEY = "reclaim_waiver"

#: The admission-change era the waiver shipped under (archaeology §4.1).
ERA = "us_prophet_v2"


def constants() -> dict[str, Any]:
    return {
        "producer": "engine.signal_quality:washout_qualifier + reclaim_waiver_for",
        "era": ERA,
        "anchor_era": SQ_ANCHOR_ERA,
        "state_artifact": WASHOUT_STATE_PATH,
        "state_schema": WASHOUT_STATE_SCHEMA,
        "notch": WASHOUT_NOTCH,
        "max_stale_sessions": WASHOUT_MAX_STALE_SESSIONS,
        "replay_scope": (
            "the committed state artifact's own as_of era only; the artifact is nightly "
            "overwritten and no historical vintage exists, so there is nothing earlier to "
            "replay and nothing is synthesized to fill it"
        ),
    }


def load_state(repo_root: str | Path, override: str | Path | None = None) -> dict | None:
    """Parse the committed nightly state artifact, or ``None`` on any doubt.

    ``override`` lets a caller point at a materialized copy of the committed artifact — the
    file lives outside some sparse checkouts, and reading it from an explicit path beats
    silently degrading to "no waiver exists".
    """
    p = Path(override) if override else Path(repo_root) / WASHOUT_STATE_PATH
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict) or raw.get("schema") != WASHOUT_STATE_SCHEMA:
        return None
    if not isinstance(raw.get("names"), dict) or not isinstance(raw.get("as_of"), str):
        return None
    return raw


def state_era(state: dict | None) -> str | None:
    """``family_first_available`` for this family: the artifact's own ``as_of``."""
    return str(state.get("as_of")) if isinstance(state, dict) else None


def fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    state: dict | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Waiver-relieved markers inside the artifact's own era.

    Returns ``(rows, receipt)``; the receipt records why the count is what it is, because
    for this family a zero needs its reason attached.
    """
    receipt: dict[str, Any] = {
        "symbol": symbol,
        "state_available": state is not None,
        "as_of": state_era(state),
        "qualifies_at_notch": False,
        "markers_in_window": 0,
        "waived": 0,
        "reason": None,
    }
    if state is None:
        receipt["reason"] = (
            "the committed nightly state artifact is not present in this checkout; the "
            "family ships zero rows rather than a synthesized context"
        )
        return [], receipt

    qualifier = washout_qualifier(symbol, state=state)
    if qualifier is None:
        receipt["reason"] = (
            f"the name does not qualify at notch {WASHOUT_NOTCH} in the committed vintage, "
            "so no marker of its could have been relieved in that era"
        )
        return [], receipt
    receipt["qualifies_at_notch"] = True

    close = df["close"].astype(float)
    frame = signal_frame(close, market="US")
    if frame is None or frame.empty or "CB" not in frame:
        receipt["reason"] = "signal_frame produced no bars for this name"
        return [], receipt
    grid = macro_grid(close, 3)
    if len(grid) != len(frame):
        receipt["reason"] = "grid/frame length mismatch — skipped rather than aligned by guess"
        return [], receipt

    as_of = pd.Timestamp(str(state.get("as_of")))
    sessions = pd.DatetimeIndex(close.index)
    rows: list[dict[str, Any]] = []
    cb = frame["CB"].fillna(False).to_numpy().astype(bool) & grid.completed_mask()
    for i in range(len(grid) - 1, -1, -1):
        if not cb[i]:
            continue
        label = pd.Timestamp(grid.label[i])
        known = marker_last_session(close, label, market="US")
        if known is None or pd.Timestamp(known) < as_of:
            # Walking backwards: once the markers are older than the artifact there is
            # nothing left inside its era.
            break
        confirmed = confirmation_date(close, label, market="US")
        if confirmed is None:
            continue
        receipt["markers_in_window"] += 1
        waiver = reclaim_waiver_for(qualifier, str(pd.Timestamp(confirmed).date()), sessions)
        if waiver is None:
            continue
        receipt["waived"] += 1
        rows.append(ev.make_event(
            family_key=FAMILY_KEY,
            producer="engine.signal_quality:reclaim_waiver_for",
            family="reentry_block_repair",
            subtype="reclaim_waived",
            stage="ADMISSION",
            symbol=symbol,
            price_plane_id=price_plane_id,
            grain="3D",
            signal_ts=label,
            signal_known_ts=pd.Timestamp(confirmed),
            known_basis=KNOWN_BASIS_BUCKET,
            signal_era=ERA,
            detector_spec_hash=spec_hash,
            source_hash=spec_hash,
            field_origin="replay_recomputed",
            provenance_class="R",
            family_first_available=str(as_of.date()),
            # The waiver converts a block into a take, so its surface DID carry scored
            # authority. Recorded as a fact; nothing here is granted anything.
            scored_authority=True,
            spec_postdates_history=False,
            context={
                "group_id": waiver.group_id,
                "basis": waiver.basis,
                "notch": waiver.notch,
                "state_as_of": waiver.as_of,
                "stale_sessions": waiver.stale_sessions,
            },
        ))
    if not rows and receipt["reason"] is None:
        receipt["reason"] = (
            f"no marker of this name became knowable inside the artifact's own era "
            f"({as_of.date()} + {WASHOUT_MAX_STALE_SESSIONS} sessions)"
        )
    return rows, receipt
