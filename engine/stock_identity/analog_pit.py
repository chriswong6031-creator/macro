"""Point-in-time (PIT) admission wall for the stock-identity episode catalog.

The episode catalog built by ``engine.stock_identity.episodes`` labels
episodes with **future data by design** (``episodes.py`` docstring: "first
date on which each label was knowable, so a PIT consumer can honor it"). This
module is that PIT consumer: it sits between the research-time catalog and
any analog consumer and enforces two gates before a row may be used:

1. **As-of admission** — a row is admitted only when it had *started* by the
   as-of date, and any outcome/resolution field is exposed only when it was
   *knowable* by the as-of date. Anything not yet knowable comes back as a
   typed missing value, never a number.
2. **Overlap dedup** — overlapping/duplicate episodes for the same
   ``(symbol, price_plane_id[, episode_type])`` are collapsed by a documented,
   deterministic rule, with every dropped row counted in the receipt.

Authority ceiling (verbatim, ledger row MO-PAID-045):
    research_navigation_until_promoted; explicitly not decision-grade

This module carries no rank, size, gate, signal-origination, or escalation
authority (Neural Web A7). No LLM appears anywhere in this path — every
number here comes from a deterministic transform of the input frame.

Determinism contract: pure and stateless over an in-memory episode-catalog
frame. No network access, no ``data/`` writes, no wall-clock reads. Calling
any public function twice on identical inputs returns byte-identical output
and an identical receipt (aside from fields that are themselves inputs, such
as ``asof``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from engine.stock_identity.authority import authority_block

GATE_NAME: str = "analog_pit_admission_v1"
MODULE_VERSION: str = "1.0.0"
AUTHORITY_CEILING: str = "research_navigation_until_promoted; explicitly not decision-grade"

# Frozen mirror of engine/stock_identity/episodes.py:610 episode_columns().
# Duplicated (not imported at runtime) so this gate never couples to the
# READ-ONLY catalog owner; test_frozen_episode_columns_match_the_catalog_owner
# asserts the two stay in sync.
EPISODE_COLUMNS: tuple[str, ...] = (
    "symbol", "price_plane_id", "episode_type", "tier", "start_date", "anchor_date",
    "end_date", "resolution", "censored", "depth_pct", "depth_atr",
    "duration_sessions", "a0_leg", "a0_anchor", "atr_basis",
    "resolution_known_date", "terminated_reason", "reference_price", "anchor_price",
)

# Knowable at (or before) start_date -- never masked.
ASOF_KNOWABLE_COLUMNS: tuple[str, ...] = (
    "symbol", "price_plane_id", "episode_type", "start_date",
    "reference_price", "a0_leg", "atr_basis",
)

# Computed from post-start data -- masked unless resolution_known_date <= asof.
OUTCOME_COLUMNS: tuple[str, ...] = (
    "tier", "anchor_date", "end_date", "resolution", "depth_pct", "depth_atr",
    "duration_sessions", "a0_anchor", "terminated_reason", "anchor_price",
    "post_trough_63d_atr", "sessions_to_50pct_retrace", "breakdown_low",
)

OUTCOME_STATES: tuple[str, ...] = (
    "known", "pending_resolution", "censored", "unknowable",
)
EPISODE_TYPE_PRECEDENCE: tuple[str, ...] = (
    "reset_decline", "reclaim", "failed_breakdown",
)
DEDUP_RULE: str = "earliest_start_wins_over_pit_visible_interval_v1"
DEDUP_SCOPES: tuple[str, ...] = ("symbol_plane", "symbol_plane_type")

_FLOAT_OUTCOME = ("depth_pct", "depth_atr", "anchor_price",
                   "post_trough_63d_atr", "sessions_to_50pct_retrace", "breakdown_low")
_DATETIME_OUTCOME = ("anchor_date", "end_date")
_OBJECT_OUTCOME = ("resolution", "terminated_reason")
_INT_OUTCOME = ("tier", "duration_sessions")

_EXTRA_ORDER = ("post_trough_63d_atr", "sessions_to_50pct_retrace", "breakdown_low")
_AUTHORITY_CAN_COLUMNS = (
    "authority_can_rank", "authority_can_size", "authority_can_gate",
    "authority_can_originate_signal", "authority_can_escalate",
)
_TAIL_COLUMNS = ("outcome_state", "outcome_missing_reason", "pit_asof", "pit_visible_end")

_NULL_TOKEN = " NULL"


@dataclass(frozen=True)
class PitResult:
    frame: pd.DataFrame
    receipt: dict[str, Any]


def _to_asof(asof: Any) -> pd.Timestamp:
    ts = pd.Timestamp(asof)
    if pd.isna(ts):
        raise ValueError(f"asof does not parse to a valid timestamp: {asof!r}")
    return ts.normalize()


def normalize_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``catalog`` with date columns coerced to datetime.

    Does not drop or reorder any column; only coerces dtypes so downstream
    comparisons against ``asof`` are well-typed.
    """
    frame = catalog.copy()
    for col in ("start_date", "end_date", "anchor_date", "resolution_known_date"):
        if col in frame.columns:
            frame[col] = pd.to_datetime(frame[col], errors="coerce")
    return frame


def outcome_state(catalog: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
    """Per-row PIT outcome-knowability state, one of OUTCOME_STATES."""
    asof = _to_asof(asof)
    rkd = pd.to_datetime(catalog["resolution_known_date"], errors="coerce")
    censored_src = catalog["censored"].astype("boolean") if "censored" in catalog.columns else pd.Series(False, index=catalog.index)

    known_mask = rkd.notna() & (rkd <= asof)
    pending_mask = rkd.notna() & (rkd > asof)
    censored_mask = rkd.isna() & (censored_src == True)  # noqa: E712
    unknowable_mask = rkd.isna() & ~censored_mask

    state = pd.Series("unknowable", index=catalog.index, dtype=object)
    state[known_mask] = "known"
    state[pending_mask] = "pending_resolution"
    state[censored_mask] = "censored"
    state[unknowable_mask] = "unknowable"
    return state


def _mask_outcomes(frame: pd.DataFrame, mask_rows: pd.Series) -> pd.DataFrame:
    """Mask OUTCOME_COLUMNS on rows where mask_rows is True, dtype-correctly."""
    frame = frame.copy()
    for col in OUTCOME_COLUMNS:
        if col not in frame.columns:
            continue
        if col in _INT_OUTCOME:
            frame[col] = frame[col].astype("Int64")
            frame.loc[mask_rows, col] = pd.NA
        elif col in _DATETIME_OUTCOME:
            frame[col] = pd.to_datetime(frame[col], errors="coerce")
            frame.loc[mask_rows, col] = pd.NaT
        elif col in _OBJECT_OUTCOME:
            frame[col] = frame[col].astype(object)
            frame.loc[mask_rows, col] = pd.NA
        else:  # float-like outcome column
            frame[col] = frame[col].astype(float)
            frame.loc[mask_rows, col] = np.nan
    return frame


def admit_as_of(catalog: pd.DataFrame, *, asof, mask_outcomes: bool = True
                 ) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Admit rows whose start_date <= asof; mask non-knowable outcomes."""
    asof_ts = _to_asof(asof)
    frame = normalize_catalog(catalog)

    missing_start = frame["start_date"].isna()
    rejected_missing_start = int(missing_start.sum())

    candidate = frame.loc[~missing_start].copy()
    not_started = candidate["start_date"] > asof_ts
    rejected_not_started = int(not_started.sum())

    admitted = candidate.loc[~not_started].copy()

    if admitted.empty:
        states = pd.Series([], dtype=object)
    else:
        states = outcome_state(admitted, asof_ts)

    admitted["outcome_state"] = states.reindex(admitted.index)
    reason_map = {
        "known": None,
        "pending_resolution": "not_yet_knowable_as_of_date",
        "censored": "still_running_at_end_of_history",
        "unknowable": "resolution_known_date_missing_source_contract_violation",
    }
    admitted["outcome_missing_reason"] = admitted["outcome_state"].map(reason_map)
    admitted["pit_asof"] = asof_ts

    known_mask = admitted["outcome_state"] == "known"
    admitted["pit_visible_end"] = pd.NaT
    if known_mask.any():
        admitted.loc[known_mask, "pit_visible_end"] = admitted.loc[known_mask, "end_date"]
    admitted.loc[~known_mask, "pit_visible_end"] = asof_ts
    admitted["pit_visible_end"] = pd.to_datetime(admitted["pit_visible_end"], errors="coerce")

    # censored flag on the returned frame reflects PIT-visible knowledge, not
    # only the source flag: any non-"known" row is reported censored=True.
    if "censored" in admitted.columns:
        admitted["censored"] = admitted["censored"].astype("boolean")
    else:
        admitted["censored"] = pd.array([pd.NA] * len(admitted), dtype="boolean")
    admitted.loc[~known_mask, "censored"] = True

    contract_violations = int((admitted["outcome_state"] == "unknowable").sum())

    if mask_outcomes:
        admitted = _mask_outcomes(admitted, ~known_mask)

    outcome_states_counts = {
        s: int((admitted["outcome_state"] == s).sum()) for s in OUTCOME_STATES
    } if not admitted.empty else {s: 0 for s in OUTCOME_STATES}

    by_type = (
        admitted["episode_type"].value_counts().to_dict() if not admitted.empty and "episode_type" in admitted.columns else {}
    )
    by_type = {str(k): int(v) for k, v in by_type.items()}

    masked_columns = [c for c in OUTCOME_COLUMNS if c in admitted.columns]

    info: dict[str, Any] = {
        "admitted": {"total": int(len(admitted)), "by_episode_type": by_type},
        "rejected_not_started": rejected_not_started,
        "rejected_missing_start": rejected_missing_start,
        "outcome_states": outcome_states_counts,
        "outcome_masked_rows": int((~known_mask).sum()) if not admitted.empty else 0,
        "masked_columns": masked_columns,
        "contract_violations": contract_violations,
        "existence_knowability_caveat": {
            "admitted_without_known_existence": int(len(admitted)),
            "note": (
                "admission uses start_date per MO-PAID-045 slice 1; an "
                "episode's EXISTENCE is generally not knowable at its start_date"
            ),
        },
    }
    return admitted, info


def _row_key(symbol: Any, plane: Any, etype: Any, start_date: pd.Timestamp) -> str:
    sd = start_date.isoformat() if pd.notna(start_date) else "NaT"
    raw = f"{symbol}|{plane}|{etype}|{sd}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def dedup_episodes(frame: pd.DataFrame, *, asof, scope: str = "symbol_plane",
                    precedence: tuple[str, ...] = EPISODE_TYPE_PRECEDENCE
                    ) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Drop overlapping/duplicate episodes within (symbol, plane[, type])."""
    if scope not in DEDUP_SCOPES:
        raise ValueError(f"unknown dedup scope: {scope!r}")
    asof_ts = _to_asof(asof)
    precedence_index = {name: i for i, name in enumerate(precedence)}

    if frame.empty:
        info = {
            "applied": True, "rule": DEDUP_RULE, "scope": scope,
            "precedence": list(precedence), "kept": 0, "dropped_total": 0,
            "dropped_exact_duplicate": 0, "dropped_overlap": 0,
            "dropped_by_episode_type": {},
        }
        return frame.copy(), info

    work = frame.copy()
    work["pindex"] = work["episode_type"].map(precedence_index).fillna(len(precedence))
    work["rowkey"] = [
        _row_key(r.symbol, r.price_plane_id, r.episode_type, r.start_date)
        for r in work.itertuples(index=False)
    ]
    if scope == "symbol_plane_type":
        work["scopekey"] = list(zip(work["symbol"], work["price_plane_id"], work["episode_type"]))
    else:
        work["scopekey"] = list(zip(work["symbol"], work["price_plane_id"]))

    order = work.sort_values(
        by=["start_date", "pindex", "symbol", "price_plane_id", "episode_type", "rowkey"],
        kind="mergesort",
    )

    seen_exact: set[tuple] = set()
    kept_end_by_scope: dict[tuple, pd.Timestamp] = {}
    keep_index: list[int] = []
    dropped_exact = 0
    dropped_overlap = 0
    dropped_by_type: dict[str, int] = {}

    for row in order.itertuples():
        exact_key = (row.symbol, row.price_plane_id, row.episode_type, row.start_date)
        if exact_key in seen_exact:
            dropped_exact += 1
            dropped_by_type[row.episode_type] = dropped_by_type.get(row.episode_type, 0) + 1
            continue
        seen_exact.add(exact_key)

        scope_key = row.scopekey
        prior_end = kept_end_by_scope.get(scope_key)
        if prior_end is not None and pd.notna(row.start_date) and row.start_date <= prior_end:
            dropped_overlap += 1
            dropped_by_type[row.episode_type] = dropped_by_type.get(row.episode_type, 0) + 1
            continue

        keep_index.append(row.Index)
        visible_end = row.pit_visible_end if pd.notna(row.pit_visible_end) else asof_ts
        if prior_end is None or (pd.notna(visible_end) and visible_end > prior_end):
            kept_end_by_scope[scope_key] = visible_end

    # Keep the canonical total-order sequence (not the original row order) so
    # the output is invariant to how the input rows were shuffled.
    kept_frame = order.loc[keep_index].drop(columns=["pindex", "rowkey", "scopekey"])

    by_type_out = (
        kept_frame["episode_type"].value_counts().to_dict() if not kept_frame.empty else {}
    )
    dropped_total = dropped_exact + dropped_overlap
    info = {
        "applied": True,
        "rule": DEDUP_RULE,
        "scope": scope,
        "precedence": list(precedence),
        "kept": int(len(kept_frame)),
        "dropped_total": int(dropped_total),
        "dropped_exact_duplicate": int(dropped_exact),
        "dropped_overlap": int(dropped_overlap),
        "dropped_by_episode_type": {str(k): int(v) for k, v in dropped_by_type.items()},
    }
    return kept_frame, info


def _authority_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    block = authority_block()
    for col, key in zip(_AUTHORITY_CAN_COLUMNS,
                         ("can_rank", "can_size", "can_gate", "can_originate_signal", "can_escalate")):
        if col not in frame.columns:
            frame[col] = block[key]
    return frame


def _output_columns(frame: pd.DataFrame) -> list[str]:
    cols = list(EPISODE_COLUMNS)
    for extra in _EXTRA_ORDER:
        if extra in frame.columns:
            cols.append(extra)
    cols.extend(_AUTHORITY_CAN_COLUMNS)
    cols.extend(_TAIL_COLUMNS)
    return cols


def empty_state(asof) -> dict[str, str]:
    asof_ts = _to_asof(asof)
    asof_str = asof_ts.date().isoformat()
    return {
        "state": "no_qualifying_episodes_at_asof",
        "plain_en": f"No qualifying episodes on {asof_str} — nothing had started yet on this date.",
        "plain_zh": f"{asof_str} 无符合条件的行情段 — 该日期之前尚无行情段开始。",
    }


def frame_hash(frame: pd.DataFrame) -> str:
    """Deterministic sha256 over a frame's contents (column-sorted, row order preserved)."""
    if frame is None or len(frame.columns) == 0:
        cols: list[str] = []
    else:
        cols = sorted(frame.columns)
    parts: list[str] = []
    for col in cols:
        series = frame[col]
        rendered: list[str] = []
        for value in series.tolist():
            if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NaT or value is pd.NA:
                rendered.append(_NULL_TOKEN)
            elif isinstance(value, pd.Timestamp):
                rendered.append(value.isoformat())
            else:
                rendered.append(str(value))
        parts.append(col + "=" + "|".join(rendered))
    blob = "\n".join(parts).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def params_hash(**params: Any) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def plain_null_lines(receipt: dict[str, Any]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    states = receipt.get("outcome_states", {})
    total = receipt.get("admitted", {}).get("total", 0)
    pending = states.get("pending_resolution", 0)
    if pending:
        lines.append({
            "what": "pending_outcomes",
            "plain_en": f"{pending} of {total} episodes had not finished yet on this date — their outcome is not available yet.",
            "plain_zh": f"截至该日期，{total} 段行情中有 {pending} 段尚未走完，结果暂不可得。",
            "why": "the outcome was only knowable after the as-of date",
        })
    censored = states.get("censored", 0)
    if censored:
        lines.append({
            "what": "censored_episodes",
            "plain_en": f"{censored} episodes were still running at the end of the available price history — no outcome was ever recorded.",
            "plain_zh": f"{censored} 段行情在可用价格历史结束时仍在进行中，从未记录结果。",
            "why": "price history ends before the episode resolved",
        })
    dropped = receipt.get("dedup", {}).get("dropped_total", 0)
    if dropped:
        lines.append({
            "what": "dedup_drops",
            "plain_en": f"{dropped} overlapping episodes were set aside so the same stretch of price history is not counted twice.",
            "plain_zh": f"已剔除 {dropped} 段重叠行情，避免同一段行情被重复计入。",
            "why": "the episodes shared the same knowable price-history window",
        })
    return lines


def pit_universe(catalog: pd.DataFrame, *, asof, dedup: bool = True,
                  scope: str = "symbol_plane",
                  precedence: tuple[str, ...] = EPISODE_TYPE_PRECEDENCE,
                  source_path: str | None = None) -> PitResult:
    """Full PIT gate: as-of admission, then (optionally) overlap dedup."""
    asof_ts = _to_asof(asof)
    input_rows = int(len(catalog))
    input_hash = frame_hash(normalize_catalog(catalog))

    admitted, admit_info = admit_as_of(catalog, asof=asof_ts, mask_outcomes=True)

    if dedup:
        deduped, dedup_info = dedup_episodes(admitted, asof=asof_ts, scope=scope, precedence=precedence)
    else:
        deduped = admitted
        dedup_info = {
            "applied": False, "rule": DEDUP_RULE, "scope": scope,
            "precedence": list(precedence), "kept": int(len(admitted)),
            "dropped_total": 0, "dropped_exact_duplicate": 0, "dropped_overlap": 0,
            "dropped_by_episode_type": {},
        }

    out = _authority_columns(deduped)
    ordered_cols = _output_columns(out)
    for col in ordered_cols:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[ordered_cols].reset_index(drop=True)

    output_hash = frame_hash(out)
    empty_reason = "no_qualifying_episodes_at_asof" if len(out) == 0 else None

    ph = params_hash(
        gate=GATE_NAME, version=MODULE_VERSION, asof=asof_ts.date().isoformat(),
        dedup=dedup, scope=scope, precedence=list(precedence),
        episode_columns=list(EPISODE_COLUMNS), outcome_columns=list(OUTCOME_COLUMNS),
    )

    receipt: dict[str, Any] = {
        "gate": GATE_NAME,
        "module": "engine.stock_identity.analog_pit",
        "version": MODULE_VERSION,
        "asof": asof_ts.date().isoformat(),
        "source": {
            "kind": "artifact" if source_path else "frame",
            "path": source_path,
            "rows": input_rows,
        },
        "input_rows": input_rows,
        "input_hash": input_hash,
        "output_rows": int(len(out)),
        "output_hash": output_hash,
        "params_hash": ph,
        "admitted": admit_info["admitted"],
        "rejected_not_started": admit_info["rejected_not_started"],
        "rejected_missing_start": admit_info["rejected_missing_start"],
        "outcome_states": admit_info["outcome_states"],
        "outcome_masked_rows": admit_info["outcome_masked_rows"],
        "masked_columns": admit_info["masked_columns"],
        "contract_violations": admit_info["contract_violations"],
        "existence_knowability_caveat": admit_info["existence_knowability_caveat"],
        "dedup": dedup_info,
        "authority": authority_block(),
        "authority_ceiling": AUTHORITY_CEILING,
        "llm_involved": False,
        "empty_reason": empty_reason,
    }
    receipt["nulls"] = plain_null_lines(receipt)
    return PitResult(frame=out, receipt=receipt)
