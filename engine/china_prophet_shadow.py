"""Point-in-time candidate ledger for China Prophet ranking research.

This store records the *entire* scored China universe at the close, including
names which did not pass the raw signal gate.  It is intentionally a feature
and admission log only: this module neither joins forward returns nor changes
the production rank.  Future challenger research can therefore evaluate a
frozen definition without reconstructing today's inputs from mutable files.

Integrity rules:

* writes are allowed only from the ``asia`` collection lane;
* a mid-session/partial China panel is refused via
  :func:`engine.china_standout_track.session_status`;
* every raw-eligible name must have an exact Prophet board lane;
* raw-ineligible names are stamped ``not_raw_eligible``;
* keep-first on ``(stamp_date, ticker, board_definition)`` prevents reruns from
  rewriting the decision users could have seen; and
* parquet appends use a schema union so definition additions do not discard
  old or out-of-band columns.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import logging
import math
from typing import Any

import pandas as pd

from engine import china_board_rank, china_standout_track, signal_gate
from lib import config

log = logging.getLogger(__name__)

STORE_DIR = "china_prophet_rank"
STORE_FILE = "candidates.parquet"

BOARD_LANES = (
    "featured",
    "more_actionable",
    "late_or_unfillable",
    "forming",
)
ALL_CANDIDATE_LANES = frozenset((*BOARD_LANES, "not_raw_eligible"))
SCORE_COMPONENTS = (
    "signal",
    "entry",
    "runway",
    "bottom_quality",
    "reversal_member",
)

_OBJECT_COLUMNS = (
    "stamp_date",
    "ticker",
    "name",
    "sector",
    "board_definition",
    "lane",
    "lane_reasons",
    "gate_tier",
    "gate_sub",
    "gate_reason",
    "gate_reasons",
    "gate_state",
    "signal_asof",
    "signal_bar_asof",
    "entry_status",
    "entry_urgency",
    "stage",
    "micro_asof",
    "micro_batch_asof",
    "board_asof",
    "sector_turn_state",
    "sector_turn_asof",
    "narrative_theme",
    "narrative_level",
    "narrative_asof",
    "quality_band",
    "potential_tier",
    "alpha_entry",
    "intel_basis",
    "intel_definition",
    "intel_signal_source",
    "intel_falsifiers",
    "intel_drivers",
    "intel_excludes",
    "intel_unavailable_reason",
)

_BOOL_COLUMNS = (
    "raw_eligible",
    "buyable",
    "gate_provisional",
    "extended",
    "micro_fillable",
    "micro_chase_veto",
    "micro_fresh",
    "execution_clear",
    "reversal_member",
    "coiled",
    "coiled_star",
    "washout_2w",
    "sector_turn_approx",
)


def _store_path():
    return config.data_dir() / STORE_DIR / STORE_FILE


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value: Any) -> str | None:
    text = _text(value)
    return text[:10] if text else None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _reasons(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, Iterable) and not isinstance(value, (bytes, Mapping)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return "|".join(parts) or None
    return None


def _potential(row: Mapping[str, Any]) -> Mapping[str, Any]:
    conviction = row.get("conviction") or {}
    potential = conviction.get("potential") if isinstance(conviction, Mapping) else None
    return potential if isinstance(potential, Mapping) else {}


def _component(
    row: Mapping[str, Any],
    name: str,
) -> tuple[float | None, float | None]:
    """Read a score component from either compact or research rank contracts."""
    prophet = row.get("prophet") or {}
    rank = row.get("prophet_rank") or {}

    compact_value = (prophet.get("components") or {}).get(name)
    if isinstance(compact_value, Mapping):
        compact_value = compact_value.get("value")
    value = _finite(compact_value)

    point_value = (prophet.get("points") or {}).get(name)
    points = _finite(point_value)

    rank_component = (rank.get("components") or {}).get(name)
    if isinstance(rank_component, Mapping):
        if value is None:
            value = _finite(rank_component.get("value"))
        if points is None:
            points = _finite(rank_component.get("points"))
    elif value is None:
        value = _finite(rank_component)

    return value, points


def _chase_flag(micro: Mapping[str, Any]) -> bool | None:
    chase = micro.get("chase_veto")
    if isinstance(chase, Mapping):
        chase = chase.get("flag")
    return _bool(chase)


def _adv_yi(row: Mapping[str, Any]) -> float | None:
    liquidity = row.get("liquidity") or {}
    value = liquidity.get("adv_yi") if isinstance(liquidity, Mapping) else None
    return _finite(value if value is not None else row.get("adv_yi"))


def _coiled_receipt(coiled: Mapping[str, Any]) -> tuple[bool | None, bool | None]:
    """Preserve observed negatives while keeping insufficient evidence unknown."""
    washout = _bool(coiled.get("washout_ctx"))
    cohort = _finite(coiled.get("cohort"))
    if washout is False:
        coiled_value: bool | None = False
    elif washout is True and cohort is not None:
        coiled_value = _bool(coiled.get("coiled"))
    else:
        coiled_value = None

    if coiled_value is False:
        star_value: bool | None = False
    elif coiled_value is True:
        star_value = _bool(coiled.get("star"))
    else:
        star_value = None
    return coiled_value, star_value


def _assignment_index(
    board_lanes: Mapping[str, Any] | None,
    lane_by_ticker: Mapping[str, str] | None,
) -> dict[str, dict[str, Any]]:
    """Build and validate one exact board-lane assignment per raw-eligible ticker."""
    assignments: dict[str, dict[str, Any]] = {}

    def add(ticker: str, candidate_lane: str, source: Mapping[str, Any] | None = None) -> None:
        if candidate_lane not in BOARD_LANES:
            raise ValueError(f"unknown China Prophet lane {candidate_lane!r}")
        prior = assignments.get(ticker)
        if prior and prior["candidate_lane"] != candidate_lane:
            raise ValueError(
                f"ticker {ticker} appears in both {prior['candidate_lane']} and {candidate_lane}"
            )
        source_reasons = None
        source_rank = None
        if isinstance(source, Mapping):
            source_rank = source.get("display_rank")
            source_reasons = source.get("lane_reasons") or source.get("reasons")
        assignments[ticker] = {
            "candidate_lane": candidate_lane,
            "lane_rank": source_rank,
            "lane_reasons": source_reasons,
        }

    if board_lanes:
        for candidate_lane in BOARD_LANES:
            lane_rows = board_lanes.get(candidate_lane) or ()
            for source in lane_rows:
                if not isinstance(source, Mapping):
                    continue
                ticker = _text(source.get("ticker"))
                if ticker:
                    add(ticker, candidate_lane, source)

    if lane_by_ticker:
        for raw_ticker, candidate_lane in lane_by_ticker.items():
            ticker = _text(raw_ticker)
            if ticker:
                add(ticker, str(candidate_lane), None)
    return assignments


def _row_record(
    row: Mapping[str, Any],
    *,
    asof: str,
    assignment: Mapping[str, Any] | None,
    intel: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ticker = _text(row.get("ticker"))
    if not ticker:
        raise ValueError("candidate row is missing ticker")

    signal = row.get("signal") or {}
    if not isinstance(signal, Mapping):
        signal = {}
    signal_research = row.get("_signal_research") or signal
    if not isinstance(signal_research, Mapping):
        signal_research = signal
    raw_eligible = bool(signal.get("eligible"))

    embedded_lane = row.get("lane")
    candidate_lane = (
        (assignment or {}).get("candidate_lane")
        or (embedded_lane if embedded_lane in BOARD_LANES else None)
    )
    if raw_eligible:
        if candidate_lane not in BOARD_LANES:
            raise ValueError(
                f"raw-eligible ticker {ticker} has no exact China Prophet board lane"
            )
    else:
        if candidate_lane in BOARD_LANES:
            raise ValueError(
                f"raw-ineligible ticker {ticker} was assigned board lane {candidate_lane}"
            )
        candidate_lane = "not_raw_eligible"

    prophet = row.get("prophet") or {}
    rank = row.get("prophet_rank") or {}
    board_definition = (
        _text(row.get("board_definition"))
        or _text(prophet.get("version") if isinstance(prophet, Mapping) else None)
        or _text(rank.get("definition") if isinstance(rank, Mapping) else None)
    )
    if not board_definition:
        raise ValueError(
            f"candidate {ticker} has no explicit board_definition"
        )

    entry = row.get("entry_signal") or {}
    if not isinstance(entry, Mapping):
        entry = {}
    buy_zone = entry.get("buy_zone") or {}
    if not isinstance(buy_zone, Mapping):
        buy_zone = {}
    extension = row.get("extension") or {}
    if not isinstance(extension, Mapping):
        extension = {}
    micro = row.get("microstructure") or {}
    if not isinstance(micro, Mapping):
        micro = {}
    risk = row.get("risk_sizing") or {}
    if not isinstance(risk, Mapping):
        risk = {}
    conviction = row.get("conviction") or {}
    if not isinstance(conviction, Mapping):
        conviction = {}
    quality = row.get("quality") or {}
    if not isinstance(quality, Mapping):
        quality = {}
    sector_turn = row.get("sector_turn") or {}
    if not isinstance(sector_turn, Mapping):
        sector_turn = {}
    narrative = row.get("narrative") or {}
    if not isinstance(narrative, Mapping):
        narrative = {}
    coiled = row.get("coiled") or {}
    if not isinstance(coiled, Mapping):
        coiled = {}
    potential = _potential(row)
    potential_components = potential.get("components") or {}
    if not isinstance(potential_components, Mapping):
        potential_components = {}

    micro_asof = _date(row.get("_micro_asof"))
    board_asof = _date(row.get("_board_asof")) or asof
    packet_asof = _date(micro.get("as_of"))
    micro_fresh = None
    if micro:
        # Match production admission exactly. The builder can repair a stale
        # batch packet per name, so the packet's own date is authoritative;
        # undated packets fail closed.
        micro_fresh = bool(board_asof and packet_asof == board_asof)
    fillable = _bool(micro.get("fillable"))
    chase_veto = _chase_flag(micro)
    adv_yi = _adv_yi(row)
    extended = _bool(extension.get("extended"))
    execution_clear = bool(
        micro_fresh is True
        and fillable is True
        and chase_veto is False
        and adv_yi is not None
        and adv_yi >= china_board_rank.ADV_FLOOR_YI
        and extended is False
    )
    score_value = row.get("prophet_score")
    if score_value is None and isinstance(prophet, Mapping):
        score_value = prophet.get("score")
    if score_value is None and isinstance(rank, Mapping):
        score_value = rank.get("score")
    coiled_value, coiled_star = _coiled_receipt(coiled)

    record: dict[str, Any] = {
        "stamp_date": asof,
        "ticker": ticker,
        "name": _text(row.get("name")),
        "sector": _text(row.get("sector")),
        "board_definition": board_definition,
        "lane": candidate_lane,
        "lane_rank": _finite(
            (assignment or {}).get("lane_rank") or row.get("display_rank")
        ),
        "lane_reasons": _reasons(
            (assignment or {}).get("lane_reasons")
            or row.get("lane_reasons")
            or row.get("reasons")
        ),
        "score_rank": _finite(row.get("score_rank")),
        "prophet_score": _finite(score_value),
        # Raw gate state.  ``buyable`` is the authoritative T1-T3 action gate;
        # ``raw_eligible`` also includes legacy early-warning/T4 candidates.
        "raw_eligible": raw_eligible,
        "buyable": bool(signal_gate.is_buyable(dict(signal))),
        "gate_tier": _text(signal_research.get("tier_cascade")),
        "gate_sub": _text(
            signal_research.get("tier_sub") or signal_research.get("sub")
        ),
        "gate_reason": _text(signal_research.get("reason")),
        # ``gate_reason`` is a FIRST-MATCH label: the buy filter returns on the first leg that
        # refuses a name, so 002155.SZ stamped "veto: bearish divergence" on every board date
        # while ALSO failing reclaim-and-hold, and 575 of 743 vetoed fires (77%) were blocked
        # by another leg anyway (research/cn_prophet_audit/CN_DIVERGENCE_VETO_AUDIT.md).
        # ``gate_reasons`` is the exhaustive account, pipe-joined per the ``lane_reasons``
        # convention, first element always identical to ``gate_reason``. It falls back to the
        # single label rather than to null so the column is never emptier than its first-match
        # sibling, and a reader may always split on "|" without a presence check.
        "gate_reasons": (
            _reasons(signal_research.get("reasons"))
            or _text(signal_research.get("reason"))
        ),
        "gate_state": _text(signal_research.get("state")),
        "gate_ticks": _finite(signal_research.get("ticks")),
        "gate_bars_to_cross": _finite(
            signal_research.get("bars_to_cross")
        ),
        "gate_weight": _finite(signal_research.get("weight")),
        "gate_provisional": bool(signal_research.get("provisional")),
        # ``asof`` is the 3B indicator-bucket label; ``input_asof`` is the
        # underlying daily data receipt that production freshness admission
        # actually consumes.
        "signal_asof": _date(signal_research.get("input_asof")),
        "signal_bar_asof": _date(signal_research.get("asof")),
        # Lifecycle and entry context.
        "entry_status": _text(entry.get("status")),
        "entry_urgency": _text(entry.get("urgency")),
        "entry_act_level": _finite(entry.get("act_level")),
        "entry_z": _finite(entry.get("entry_z")),
        "entry_confidence": _finite(entry.get("confidence")),
        "entry_spot": _finite(entry.get("spot")),
        "buy_zone_low": _finite(buy_zone.get("low")),
        "buy_zone_high": _finite(buy_zone.get("high")),
        "chase_above": _finite(entry.get("chase_above")),
        "stop": _finite(entry.get("stop")),
        "atr_pct": _finite(entry.get("atr_pct")),
        "stage": _text(row.get("stage")),
        # Execution/admission context.  These fields never add score.
        "extended": extended,
        "extension_score": _finite(extension.get("score")),
        "adv_yi": adv_yi,
        "micro_fillable": fillable,
        "micro_chase_veto": chase_veto,
        # Packet provenance and batch provenance are deliberately separate:
        # a fresh document date must never overwrite a stale/undated ticker.
        "micro_asof": packet_asof,
        "micro_batch_asof": micro_asof,
        "board_asof": board_asof,
        "micro_fresh": micro_fresh,
        "execution_clear": execution_clear,
        # Reference level and transparent challenger/context features.
        "level": _finite(row.get("price")),
        "off_high": _finite(row.get("off_high")),
        "residual_alpha": _finite(row.get("alpha")),
        "alpha_entry": _text(row.get("alpha_entry")),
        "legacy_setup": _finite(row.get("setup")),
        "rev_z": _finite(row.get("rev_z")),
        "ret_3m": _finite(row.get("ret_3m")),
        "rev_percentile": _finite(row.get("rev_percentile")),
        "reversal_member": bool(row.get("reversal_member")),
        "reversal_sector_rank": _finite(row.get("reversal_sector_rank")),
        "reversal_sector_n": _finite(row.get("reversal_sector_n")),
        "coiled": coiled_value,
        "coiled_star": coiled_star,
        "washout_2w": _bool(row.get("washout_2w")),
        "conviction_score": _finite(conviction.get("score")),
        "potential_score": _finite(potential.get("score")),
        "potential_tier": _text(potential.get("tier")),
        "potential_fuel": _finite(potential_components.get("fuel")),
        "quality_z": _finite(quality.get("z")),
        "quality_band": _text(quality.get("band")),
        "risk_size_mult": _finite(risk.get("size_mult")),
        "vol_ann_pct": _finite(risk.get("vol_ann_pct")),
        "vol_percentile": _finite(risk.get("vol_pct")),
        "inv_vol_mult": _finite(risk.get("inv_vol_mult")),
        "sector_turn_state": _text(sector_turn.get("state")),
        "sector_turn_osc_slope": _finite(sector_turn.get("osc_slope")),
        "sector_turn_signature": _finite(sector_turn.get("signature")),
        "sector_turn_asof": _date(sector_turn.get("asof")),
        "sector_turn_approx": _bool(sector_turn.get("approx")),
        "narrative_theme": _text(narrative.get("theme")),
        "narrative_level": _text(narrative.get("level")),
        "narrative_asof": _date(narrative.get("asof")),
        "narrative_rel20": _finite(narrative.get("rel20")),
        "narrative_breadth": _finite(narrative.get("breadth")),
    }
    # V4 — full board-independent intelligence-interest anatomy (engine/china_intel_interest.py
    # ``interest_score()``). ``intel`` is the SAME record the board attach
    # (china_board_rank._attach_intel) reads for this ticker — passed through by the caller
    # from one shared per-nightly compute, never re-scored here (single-compute invariant,
    # masterplan §13 PR-0B). A record absent from the map (the name was never requested, or the
    # whole V4 compute failed) is distinguished from an in-map record that fell back to v3
    # because a desk had no evidence: the former stamps ``no_intel_record``, the latter carries
    # its own ``unavailable_reason`` (``no_desk_evidence`` / ``no_edge_evidence``). Neither case
    # is ever a bare null with no explanation — a missing/refused intel read is never zero.
    intel_record = intel if isinstance(intel, Mapping) else None
    intel_reason = (
        _text(intel_record.get("unavailable_reason")) if intel_record is not None
        else "no_intel_record"
    )
    record.update({
        "intel_score": _finite((intel_record or {}).get("score")),
        "intel_basis": _text((intel_record or {}).get("basis")),
        "intel_definition": _text((intel_record or {}).get("definition")),
        "intel_signal_core": _finite((intel_record or {}).get("signal_core")),
        "intel_signal_source": _text((intel_record or {}).get("signal_source")),
        "intel_edge_remaining": _finite((intel_record or {}).get("edge_remaining")),
        "intel_edge_components": _finite((intel_record or {}).get("edge_components")),
        "intel_gap": _finite((intel_record or {}).get("gap")),
        "intel_lead_up": _finite((intel_record or {}).get("lead_up")),
        "intel_gap_mult": _finite((intel_record or {}).get("gap_mult")),
        "intel_falsifier_penalty": _finite((intel_record or {}).get("falsifier_penalty")),
        "intel_falsifiers": _reasons((intel_record or {}).get("falsifiers")),
        "intel_drivers": _reasons((intel_record or {}).get("drivers")),
        "intel_excludes": _reasons((intel_record or {}).get("excludes")),
        "intel_unavailable_reason": intel_reason,
    })
    for component in SCORE_COMPONENTS:
        value, points = _component(row, component)
        record[f"prophet_{component}"] = value
        record[f"prophet_{component}_points"] = points
    return record


def _coerce_nullable_objects(frame: pd.DataFrame) -> pd.DataFrame:
    """Avoid pandas/pyarrow dtype conflicts when an older column was all-null."""
    for column in _OBJECT_COLUMNS:
        if column in frame.columns:
            values = frame[column].astype(object)
            frame[column] = values.where(pd.notna(values), None)
    for column in _BOOL_COLUMNS:
        if column in frame.columns:
            values = frame[column].astype(object)
            frame[column] = values.where(pd.notna(values), None)
    return frame


def append_candidates(
    rows: Iterable[Mapping[str, Any]],
    asof: str | None = None,
    *,
    lane: str | None = None,
    board_lanes: Mapping[str, Any] | None = None,
    lane_by_ticker: Mapping[str, str] | None = None,
    intel_by: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
    """Append one settled full-universe China Prophet candidate snapshot.

    ``rows`` should be the complete result of
    :func:`engine.china_board_rank.enrich_and_score_rows`, not just raw-eligible
    names.  Since :func:`engine.china_board_rank.partition_board_rows` returns
    copies, pass that result as ``board_lanes`` (or an equivalent
    ``lane_by_ticker`` mapping) so every raw-eligible row receives its exact
    ``featured``/``more_actionable``/``late_or_unfillable``/``forming`` lane.
    Raw-ineligible names are stamped ``not_raw_eligible`` automatically.

    ``intel_by`` is the SAME ``{TICKER: interest record}`` map the caller already
    built once via :func:`engine.china_intel_interest.build_interest_map` and fed
    to :func:`engine.china_board_rank.enrich_and_score_rows` (as its own
    ``intel_by``) — passing it here persists the FULL board-independent
    intelligence-interest anatomy (score, basis, signal core/source, edge
    components, gap, falsifiers, drivers, excludes) alongside every row without a
    second ``interest_score()`` evaluation (single-compute invariant). Omitting it
    persists every ``intel_*`` column as null/``no_intel_record`` and changes no
    other behavior.

    Returns the total row count after the keep-first merge.  This telemetry is
    best-effort and returns ``0`` on a refused or failed append; it never changes
    ranking or trading state.
    """
    if lane != "asia":
        log.info("China Prophet shadow append gated (lane=%s, not asia)", lane)
        return 0

    board_date = _date(asof)
    source_rows = list(rows)
    if not board_date or not source_rows:
        return 0

    session = china_standout_track.session_status(board_date)
    if session.get("partial_session"):
        log.warning(
            "China Prophet shadow REFUSING append — %s",
            session.get("reason"),
        )
        return 0

    try:
        assignments = _assignment_index(board_lanes, lane_by_ticker)
        records = [
            _row_record(
                row, asof=board_date,
                assignment=assignments.get(_text(row.get("ticker"))),
                intel=(intel_by or {}).get(str(row.get("ticker") or "")),
            )
            for row in source_rows
        ]
        definitions = {record["board_definition"] for record in records}
        if len(definitions) != 1:
            raise ValueError(
                "one shadow append cannot mix board definitions: "
                f"{sorted(definitions)}"
            )
        new = _coerce_nullable_objects(pd.DataFrame(records))

        path = _store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prior = pd.read_parquet(path)
            # Preserve both legacy-only and newly introduced fields.
            columns = list(dict.fromkeys([*prior.columns, *new.columns]))
            combined = pd.concat(
                [
                    prior.reindex(columns=columns),
                    new.reindex(columns=columns),
                ],
                ignore_index=True,
            )
        else:
            combined = new

        combined = combined.drop_duplicates(
            subset=["stamp_date", "ticker", "board_definition"],
            keep="first",
        )
        combined = _coerce_nullable_objects(combined)
        combined.to_parquet(path, index=False)
        return int(len(combined))
    except Exception as exc:  # noqa: BLE001 - research telemetry must never break a build
        log.warning("China Prophet shadow append failed: %s", exc)
        return 0
