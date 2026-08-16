"""The event store schema, deterministic ids, typed edges, and the R1 vintage stamp.

``mastermind.entry_event.v1``-compatible and **program-owned** (registration §4). The
Radar store is never written and never pre-empted: Radar PR-0 is a contract, its store
lands at Radar PR-2, and it remains Radar's. This is a parallel store under
``data/stock_identity/**`` that adopts Radar's A1 field vocabulary verbatim so PR-7's
prospective ingestion unions cleanly.

Field vocabulary
----------------
Radar's ``source_identity{source_hash, signal_era, detector_spec_hash}`` is carried as
three top-level columns under **its own inner field names** — a flat parquet column beats
a nested struct for every reader we have, and keeping the inner names verbatim is what
makes the union trivial later. The mapping is recorded in the family registry.

``field_origin`` is **extended** past Radar's ``{emitter_verbatim, radar_derived}`` for
historical provenance::

    emitter_verbatim   the producer itself emitted this row (not reachable in W2 —
                       no Macro producer wrote a per-fire event store historically)
    radar_derived      derived by Radar (reserved; W2 writes none)
    ledger_recorded    extracted from a committed house ledger, unmodified
    replay_recomputed  recomputed by the producer's own function over history

``scored_authority`` records what the emitter's authority actually was — a fact about the
past, never a grant. Nothing in this program grants authority to anything: every artifact
also carries the five-key all-false authority block.

Hard schema law: **no ruler or fit column may ever exist here.** ``lead_lag``,
``price_dist``, ``mae``, ``capture``, ``recall``, ``precision``, ``composite``, ``fit``,
``rank``, ``best`` are banned as column names and as context keys, test-enforced. W2's
terminal artifact is events plus attribution edges; the metrics are PR-3's object.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

import pandas as pd

from engine.stock_identity.authority import AUTHORITY_KEYS, authority_block

__all__ = [
    "EVENT_SCHEMA",
    "EDGE_SCHEMA",
    "EVENT_COLUMNS",
    "EDGE_COLUMNS",
    "FIELD_ORIGINS",
    "RELATIONS",
    "BANNED_RULER_TOKENS",
    "event_id",
    "make_event",
    "empty_events",
    "finalize_events",
    "make_edge",
    "finalize_edges",
    "vintage_stamp",
    "spec_hash",
    "assert_no_ruler_columns",
]

EVENT_SCHEMA = "stock_identity.expert_event.v0"
EDGE_SCHEMA = "stock_identity.event_edge.v0"

#: Radar A1 vocabulary, extended for historical provenance (registration §4).
FIELD_ORIGINS: tuple[str, ...] = (
    "emitter_verbatim",
    "radar_derived",
    "ledger_recorded",
    "replay_recomputed",
)

#: Typed edges. The grey-dot as-restated view is expressed as edges, NEVER as row
#: deletion — a suppressed row stays in the store carrying an edge that says so.
RELATIONS: tuple[str, ...] = ("promoted_by", "dedup_suppressed_by")

#: Ruler/fit vocabulary that may not appear as a column name or a context key anywhere
#: in W2. Matched on snake_case token boundaries, so "profit" does not trip "fit".
BANNED_RULER_TOKENS: tuple[str, ...] = (
    "lead_lag", "price_dist", "mae", "capture", "recall", "precision",
    "composite", "fit", "rank", "best",
)

_AUTHORITY_COLUMNS: tuple[str, ...] = tuple(f"authority_{k}" for k in AUTHORITY_KEYS)

EVENT_COLUMNS: tuple[str, ...] = (
    "event_id",
    "family_key",
    "producer",
    "detector_id",
    "family",
    "subtype",
    "stage",
    "quality",
    "context",
    "symbol",
    "price_plane_id",
    "grain",
    "signal_ts",
    "signal_known_ts",
    "known_basis",
    "source_hash",
    "signal_era",
    "detector_spec_hash",
    "scored_authority",
    "family_first_available",
    "family_era",
    "field_origin",
    "provenance_class",
    "spec_postdates_history",
    "in_washout_context",
) + _AUTHORITY_COLUMNS

EDGE_COLUMNS: tuple[str, ...] = (
    "relation",
    "source_event_id",
    "target_event_id",
    "symbol",
    "source_family_key",
    "target_family_key",
    "note",
) + _AUTHORITY_COLUMNS


def _tokens(name: str) -> set[str]:
    """snake_case / camelCase segments of an identifier, lowercased."""
    out: list[str] = []
    cur = ""
    for ch in str(name):
        if ch.isalnum():
            cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return {t.lower() for t in out}


#: The five authority columns are REFUSALS, not metrics — ``authority_can_rank`` is the
#: field that says this store may never rank anything. Exempting exactly these five names
#: (and nothing else) keeps the ban meaningful instead of forcing the refusal to be renamed.
_RULER_EXEMPT: frozenset[str] = frozenset(_AUTHORITY_COLUMNS) | {"can_rank"}


def assert_no_ruler_columns(names: Iterable[str], where: str = "") -> None:
    """Raise if any name carries ruler/fit vocabulary. Fail-closed, at write time."""
    for name in names:
        if str(name) in _RULER_EXEMPT:
            continue
        low = str(name).lower()
        toks = _tokens(name)
        for banned in BANNED_RULER_TOKENS:
            hit = banned in low if "_" in banned else banned in toks
            if hit:
                raise ValueError(
                    f"{where or 'schema'}: {name!r} carries ruler vocabulary {banned!r}. "
                    "W2 publishes no ruler metric — that is PR-3's object (registration §0.1)."
                )


def event_id(family_key: str, ticker: str, signal_ts: Any, subtype: str | None) -> str:
    """``sha256(family_key|ticker|signal_ts|subtype)[:16]`` — registration §4, verbatim.

    ``signal_ts`` is normalized to an ISO date so a Timestamp and its string form mint the
    same id; a null subtype normalizes to the empty string.
    """
    ts = pd.Timestamp(signal_ts)
    key = f"{family_key}|{str(ticker).upper()}|{ts.date().isoformat()}|{subtype or ''}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def spec_hash(constants: Mapping[str, Any]) -> str:
    """sha256 over a producer's formula constants **as extracted from the module**.

    The registry never invents a constant: every value hashed here is read off the
    producer at import time, so a producer edit changes the hash and the family's identity
    with it.
    """
    payload = json.dumps(constants, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_event(
    *,
    family_key: str,
    producer: str,
    family: str,
    subtype: str | None,
    stage: str,
    symbol: str,
    price_plane_id: str,
    grain: str,
    signal_ts: Any,
    signal_known_ts: Any,
    known_basis: str,
    signal_era: str,
    detector_spec_hash: str,
    source_hash: str,
    field_origin: str,
    provenance_class: str,
    family_first_available: str | None,
    family_era: str | None = None,
    scored_authority: bool = False,
    spec_postdates_history: bool = False,
    in_washout_context: bool | None = None,
    quality: str | None = None,
    context: Mapping[str, Any] | None = None,
    detector_id: str | None = None,
) -> dict[str, Any]:
    """One event row. Every provenance field is required — there is no silent default."""
    if field_origin not in FIELD_ORIGINS:
        raise ValueError(f"unknown field_origin {field_origin!r}")
    ctx = dict(context or {})
    assert_no_ruler_columns(ctx.keys(), where=f"{family_key} context")
    row: dict[str, Any] = {
        "event_id": event_id(family_key, symbol, signal_ts, subtype),
        "family_key": family_key,
        "producer": producer,
        "detector_id": detector_id,
        "family": family,
        "subtype": subtype,
        "stage": stage,
        "quality": quality,
        "context": json.dumps(ctx, sort_keys=True, default=str) if ctx else None,
        "symbol": str(symbol).upper(),
        "price_plane_id": price_plane_id,
        "grain": grain,
        "signal_ts": pd.Timestamp(signal_ts),
        "signal_known_ts": pd.Timestamp(signal_known_ts),
        "known_basis": known_basis,
        "source_hash": source_hash,
        "signal_era": signal_era,
        "detector_spec_hash": detector_spec_hash,
        "scored_authority": bool(scored_authority),
        "family_first_available": family_first_available,
        "family_era": family_era if family_era is not None else signal_era,
        "field_origin": field_origin,
        "provenance_class": provenance_class,
        "spec_postdates_history": bool(spec_postdates_history),
        "in_washout_context": in_washout_context,
    }
    for k, v in authority_block().items():
        row[f"authority_{k}"] = v
    return row


def empty_events() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in EVENT_COLUMNS})


def finalize_events(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Assemble, order, type and validate the event table."""
    rows = list(rows)
    if not rows:
        return empty_events()
    df = pd.DataFrame(rows)
    missing = [c for c in EVENT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"event rows missing column(s) {missing}")
    extra = [c for c in df.columns if c not in EVENT_COLUMNS]
    if extra:
        raise ValueError(f"event rows carry unknown column(s) {extra}")
    assert_no_ruler_columns(df.columns, where="pilot_events_v0")
    df = df[list(EVENT_COLUMNS)].copy()
    df["signal_ts"] = pd.to_datetime(df["signal_ts"])
    df["signal_known_ts"] = pd.to_datetime(df["signal_known_ts"])
    for c in ("scored_authority", "spec_postdates_history"):
        df[c] = df[c].astype(bool)
    df["in_washout_context"] = df["in_washout_context"].astype("object")
    for c in _AUTHORITY_COLUMNS:
        df[c] = df[c].astype(bool)
    # known_ts law: an event is never knowable before it fires.
    bad = df["signal_known_ts"] < df["signal_ts"]
    if bool(bad.any()):
        raise ValueError(
            f"{int(bad.sum())} row(s) carry signal_known_ts before signal_ts — the "
            "known-ts law (registration §4) is violated"
        )
    return df.sort_values(
        ["family_key", "symbol", "signal_known_ts", "signal_ts"]
    ).reset_index(drop=True)


def make_edge(
    *,
    relation: str,
    source_event_id: str,
    target_event_id: str,
    symbol: str,
    source_family_key: str,
    target_family_key: str,
    note: str | None = None,
) -> dict[str, Any]:
    if relation not in RELATIONS:
        raise ValueError(f"unknown relation {relation!r}; allowed {RELATIONS}")
    row: dict[str, Any] = {
        "relation": relation,
        "source_event_id": source_event_id,
        "target_event_id": target_event_id,
        "symbol": str(symbol).upper(),
        "source_family_key": source_family_key,
        "target_family_key": target_family_key,
        "note": note,
    }
    for k, v in authority_block().items():
        row[f"authority_{k}"] = v
    return row


def finalize_edges(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    rows = list(rows)
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in EDGE_COLUMNS})
    df = pd.DataFrame(rows)
    missing = [c for c in EDGE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"edge rows missing column(s) {missing}")
    assert_no_ruler_columns(df.columns, where="event_edges_v0")
    df = df[list(EDGE_COLUMNS)].copy()
    for c in _AUTHORITY_COLUMNS:
        df[c] = df[c].astype(bool)
    return df.sort_values(["relation", "symbol", "source_event_id"]).reset_index(drop=True)


def vintage_stamp(
    *,
    price_plane_ids: Iterable[str],
    universe_as_of: str,
    coverage_frac: float | None,
    era_law_cohort: str,
) -> dict[str, Any]:
    """The R1 vintage-stamp schema, adopted verbatim (registration §1).

    Carried once per table in the family registry rather than repeated on every row: the
    values are table-level facts and 100k copies of the same string is not honesty, it is
    a bigger file.
    """
    return {
        "price_plane_id": sorted(set(price_plane_ids)),
        "adjustment_mode": "auto_adjust=True (dividend/split adjusted total-return)",
        "universe_as_of": universe_as_of,
        "frame": "per-name full replayable depth (no fire-tape cohort filter)",
        "survivorship_biased": True,
        "survivorship_note": (
            "the allowed price planes retain no ceased tapes, so every event here belongs "
            "to a surviving instrument. The Dead Instrument Control Set is a separately "
            "registered future act that BLOCKS PR-5/Q1 (registration §0.2); W2 does not "
            "build it and no cohort claim may be made over this store without it."
        ),
        "coverage_frac": coverage_frac,
        "dead_name_coverage_pct": 0.0,
        "era_law_cohort": era_law_cohort,
    }
