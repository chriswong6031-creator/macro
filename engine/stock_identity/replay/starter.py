"""STARTER — the Class C resolution the registration's consequence matrix requires.

STARTER fires when a **signature** meets a **licensing context**:

* signature = ``union_admission``'s two legs (leg A ``early_dot`` = the engine's own grey-dot
  column; leg B ``relaxed_cross`` = a 3D StochRSI cross with both lines under 20, confirmed
  by the 1D MACD-RSI in force within 5 sessions or arriving within the next 10);
* licensing context = the name's basket state ∈ {WASHED_OUT, BASING, TURNING} **OR** its
  leader-pullback state ∈ {PULLBACK, RESET_TURN}.

The signature is replayable. The **context** is the open question the registration binds
this wave to answer, with the consequence fixed in advance:

    context PIT-reconstructable  -> starter_pending/failed/converted replay as Class R over
                                    the reconstructable era
    NOT reconstructable          -> the trio reclassifies to Class P (no synthetic context,
                                    no backfill) AND the admission SIGNATURE alone ships as
                                    its own honestly-named family ``starter_signature``

:func:`investigate_licensing_context` runs that investigation against committed artifacts
and returns the verdict with its evidence attached. It reads what the producer itself
reads — ``engine.us_early_turn.load_basket_turn_membership`` names
``site/basketdata/us_basket_turn.json`` plus ``data/baskets/membership.json``, and
``load_leader_pullback_states`` names ``site/anticipationdata/us_leader_pullback.json`` —
and asks one question of each: *does a point-in-time history of this state exist, or only
tonight's value?*

The distinction that decides it is **membership vs state**. PIT membership does exist
(``data/baskets/membership_history.parquet`` carries per-ticker ``added``/``removed``
dates). What is licensed is not membership but the basket's *washout state on a past date*,
and that is computed nightly and overwritten. Reconstructing it would mean re-running the
basket organ over history — a different construction with its own gates, not a read of a
committed artifact — and the registration forbids inventing it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from engine.us_early_turn import (
    UNION_ADMISSION_ERA,
    UNION_LEG_CROSS,
    UNION_LEG_DOT,
    WASHOUT_MATURE_STATES,
    LEADER_PULLBACK_CONTEXT_STATES,
    _union_early_dot_fires,
    _union_relaxed_cross_fires,
)

from engine.stock_identity.replay import events as ev
from engine.stock_identity.replay.grid import KNOWN_BASIS_BUCKET, KNOWN_BASIS_DAILY, macro_grid

__all__ = [
    "SIGNATURE_FAMILY_KEY",
    "TRIO_FAMILY_KEYS",
    "ERA",
    "constants",
    "investigate_licensing_context",
    "signature_fires",
]

SIGNATURE_FAMILY_KEY = "starter_signature"
TRIO_FAMILY_KEYS: tuple[str, ...] = ("starter_pending", "starter_failed", "starter_converted")
ERA = UNION_ADMISSION_ERA

#: The artifacts the producer itself reads for its licensing context.
_CONTEXT_ARTIFACTS: tuple[tuple[str, str, str], ...] = (
    ("basket_state", "site/basketdata/us_basket_turn.json",
     "us_early_turn.load_basket_turn_membership"),
    ("leader_pullback_state", "site/anticipationdata/us_leader_pullback.json",
     "us_early_turn.load_leader_pullback_states"),
)
#: The membership map, which DOES have a point-in-time form — and is not what is licensed.
_MEMBERSHIP_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("membership_current", "data/baskets/membership.json"),
    ("membership_history", "data/baskets/membership_history.parquet"),
)


def constants() -> dict[str, Any]:
    return {
        "producer": "engine.us_early_turn:union_admission (legs) + assess_early_turn (licence)",
        "era": UNION_ADMISSION_ERA,
        "legs": [UNION_LEG_CROSS, UNION_LEG_DOT],
        "leg_a": "early_dot — the engine's own signal_frame.early column",
        "leg_b": (
            "relaxed_cross — 3D StochRSI %K x %D bull cross with BOTH lines under 20, "
            "confirmed by the 1D MACD-RSI in force within 5 sessions or arriving within 10"
        ),
        "completed_buckets_only": True,
        "licensing_context": {
            "basket_states": sorted(WASHOUT_MATURE_STATES),
            "leader_states": sorted(LEADER_PULLBACK_CONTEXT_STATES),
        },
    }


# ---------------------------------------------------------------------------
# The consequence-matrix investigation
# ---------------------------------------------------------------------------
def investigate_licensing_context(
    repo_root: str | Path,
    *,
    artifact_overrides: dict[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Is the STARTER licensing context PIT-reconstructable from committed artifacts?

    Returns a verdict dict with every piece of evidence it looked at, so the answer can be
    re-derived by a reader who does not trust the conclusion.

    ``artifact_overrides`` maps a canonical repo-relative path to a materialized copy of
    the same committed content. Some checkouts are sparse and do not carry ``site/``; the
    honest move is to read the committed bytes from wherever they are rather than let a
    sparse cone masquerade as "the artifact does not exist". The canonical path is what is
    reported either way, and ``read_from`` records the substitution.
    """
    root = Path(repo_root)
    over = {str(k): Path(v) for k, v in (artifact_overrides or {}).items()}
    evidence: list[dict[str, Any]] = []

    for key, rel, reader in _CONTEXT_ARTIFACTS:
        p = over.get(rel, root / rel)
        row: dict[str, Any] = {
            "artifact": rel, "role": key, "read_by": reader,
            "read_from": str(p) if rel in over else rel,
            "present_in_checkout": p.exists(),
            "carries_history": False, "n_dated_vintages": 0, "as_of": None, "note": None,
        }
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                row["note"] = f"unreadable: {exc}"
                evidence.append(row)
                continue
            asof = payload.get("as_of") or payload.get("asof") or payload.get("data_session")
            row["as_of"] = str(asof) if asof is not None else None
            row["n_dated_vintages"] = 1 if asof is not None else 0
            # A history-carrying artifact would key its states by DATE. These key by
            # basket/ticker and carry exactly one as_of.
            row["carries_history"] = any(
                isinstance(v, dict) and any(
                    str(k2)[:4].isdigit() and len(str(k2)) >= 8 for k2 in v
                )
                for v in payload.values() if isinstance(v, dict)
            )
            row["note"] = (
                "single nightly vintage keyed by basket/ticker; no per-date state series"
                if not row["carries_history"] else "date-keyed structure found"
            )
        else:
            row["note"] = (
                "absent from this checkout (sparse cone); it is a committed nightly "
                "artifact whose content is overwritten each night"
            )
        evidence.append(row)

    membership: list[dict[str, Any]] = []
    for key, rel in _MEMBERSHIP_ARTIFACTS:
        p = root / rel
        row = {"artifact": rel, "role": key, "present_in_checkout": p.exists(),
               "n_snapshot_dates": None, "has_added_removed": None, "note": None}
        if p.exists() and rel.endswith(".parquet"):
            df = pd.read_parquet(p)
            row["n_snapshot_dates"] = int(df["snapshot_date"].nunique()) \
                if "snapshot_date" in df.columns else 0
            row["has_added_removed"] = bool(
                {"added", "removed"}.issubset(set(df.columns))
            )
            row["note"] = (
                "per-ticker [added, removed) intervals — PIT MEMBERSHIP exists. Membership "
                "is not the licensed object; the licensed object is the basket's washout "
                "STATE on a past date."
            )
        membership.append(row)

    # A state history would have to exist as a dated store somewhere under data/.
    state_stores = sorted(
        str(p.relative_to(root)) for p in (root / "data").glob("**/*basket_turn*")
    ) if (root / "data").is_dir() else []

    reconstructable = any(e["carries_history"] for e in evidence) or bool(state_stores)
    verdict = {
        "question": (
            "is the STARTER licensing context (basket washout state OR leader-pullback "
            "state, as of a past date) reconstructable point-in-time from committed "
            "artifacts?"
        ),
        "verdict": "PIT_RECONSTRUCTABLE" if reconstructable else "NOT_PIT_RECONSTRUCTABLE",
        "consequence": (
            "starter_pending/starter_failed/starter_converted replay as Class R over the "
            "reconstructable era"
            if reconstructable else
            "starter_pending/starter_failed/starter_converted RECLASSIFY to Class P (zero "
            "rows, no synthetic context, no backfill); the admission SIGNATURE ships "
            "separately as starter_signature (Class R)"
        ),
        "context_state_evidence": evidence,
        "membership_evidence": membership,
        "basket_state_history_stores_found": state_stores,
        "reasoning": (
            "Both context artifacts are nightly-overwritten single-vintage JSON keyed by "
            "basket/ticker with one as_of; neither is a dated series and no dated basket-"
            "state store exists under data/. PIT membership DOES exist "
            "(membership_history.parquet's added/removed intervals) but membership is not "
            "what licenses a STARTER — the basket's washout STATE on the fire date is, and "
            "recomputing that over history would be a new construction with its own gates, "
            "not a read of a committed artifact."
        ),
    }
    return verdict


# ---------------------------------------------------------------------------
# starter_signature — the replayable half
# ---------------------------------------------------------------------------
def signature_fires(
    df: pd.DataFrame,
    *,
    symbol: str,
    price_plane_id: str,
    spec_hash: str,
    family_first_available: str | None,
) -> list[dict[str, Any]]:
    """Every union-admission SIGNATURE fire — the legs only, no licence claimed.

    The two leg computations come from ``engine.us_early_turn``'s own helpers. They are
    module-private because the module's public entry point answers "is a fire LIVE now" and
    returns only the most recent one; a history needs the leg lists, and re-implementing the
    legs to avoid an underscore would be the silent fork the whole firewall exists to
    prevent. Both helpers already apply the module's completed-bucket mask, so every fire
    here is knowable at the daily session the helper returns.
    """
    close = df["close"].astype(float)
    try:
        cross_fires = _union_relaxed_cross_fires(close, None)
        dot_fires = _union_early_dot_fires(close, None)
    except Exception:  # noqa: BLE001 — one unreadable name never kills a run
        return []
    if not cross_fires and not dot_fires:
        return []

    grid = macro_grid(close, 3)
    di = pd.DatetimeIndex(close.index)

    def _signal_ts(row: int, fallback: pd.Timestamp) -> pd.Timestamp:
        return pd.Timestamp(grid.label[row]) if 0 <= row < len(grid) else fallback

    rows: list[dict[str, Any]] = []
    for leg, fires_ in ((UNION_LEG_CROSS, cross_fires), (UNION_LEG_DOT, dot_fires)):
        for pos, row, meta in fires_:
            if pos >= len(di):
                continue
            known = pd.Timestamp(di[pos])
            signal_ts = _signal_ts(int(row), known)
            if signal_ts > known:
                signal_ts = known
            ctx = {k: v for k, v in dict(meta or {}).items() if v is not None}
            ctx["leg"] = leg
            rows.append(ev.make_event(
                family_key=SIGNATURE_FAMILY_KEY,
                producer="engine.us_early_turn:union_admission legs",
                family="starter_signature",
                subtype=leg,
                stage="EARLY",
                symbol=symbol,
                price_plane_id=price_plane_id,
                grain="3D",
                signal_ts=signal_ts,
                signal_known_ts=known,
                known_basis=KNOWN_BASIS_BUCKET if leg == UNION_LEG_DOT else KNOWN_BASIS_DAILY,
                signal_era=ERA,
                detector_spec_hash=spec_hash,
                source_hash=spec_hash,
                field_origin="replay_recomputed",
                provenance_class="R",
                family_first_available=family_first_available,
                # The signature alone admits nothing: the licence is the other half, and
                # this family deliberately does not claim it.
                scored_authority=False,
                spec_postdates_history=True,
                context=ctx,
            ))
    return rows
