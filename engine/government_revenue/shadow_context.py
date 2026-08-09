"""Wave 9E — Neural Web shadow cross-check packets for Government Revenue.

A packet enriches an ALREADY-SELECTED candidate.  It is a strictly separate
artifact from the candidate queue, and that separation is not stylistic:
``government_revenue_candidate.v1`` and ``…_queue.v1`` both declare
``additionalProperties: false``, so a packet cannot be nested inside a candidate
or its queue without breaking their contracts.  The byte-identity gate is
therefore structural rather than promised — this module reads candidates and
never returns them.

WHAT A PACKET IS
================
Named legs, and nothing above them.

  * the procurement legs restate what the candidate already proves — event
    family, receipts, direction, and the reviewed issuer path — so a reader can
    see the whole why in one place without the packet becoming the source of it;
  * the market-context legs come from `market_context`, each cut point-in-time at
    the candidate's own ``known_at``;
  * an integrity leg names every gap, staleness, and disagreement found while
    building the rest.

There is deliberately NO packet-level number.  ``assert_no_fused_score`` walks a
finished packet and refuses any numeric that is not inside a named leg reading,
plus any key whose NAME advertises a composite (``score``, ``rank``, ``weight``,
``composite``, ``fused``, ``conviction``, …).  A fused figure hides which leg did
the work and would be an origination event under constitution A7, so the guard
is a hard failure, not a warning.

CONTRADICTIONS STAY VISIBLE
---------------------------
When two legs disagree the packet records a named contradiction and BOTH legs
keep shipping their own readings unchanged.  Nothing is averaged, netted, or
resolved: "run-up already in the 96th percentile of its own history while the
event reads possible-positive" is the useful sentence, and collapsing it into a
single adjusted figure destroys it.

Front-facing copy is plain-word and never refutation-shaped (operator 2026-07-27):
the label is "shadow context", the disagreement copy says the two readings
disagree, and no user-visible string says falsifier, refuted, or 证伪.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .market_context import (
    LEG_STATUSES,
    market_context_legs,
)


CONTRACT = "government_revenue_shadow_context.v1"
SCHEMA_VERSION = "1.0.0"

#: The label every surface must use for this payload.  Not "confirmation", not
#: "confluence", not "signal" — the packet has no authority and the label says so.
LABEL_EN = "shadow context"
LABEL_ZH = "影子背景"
LABEL_LIMIT_EN = "Shadow context runs beside the record — it does not rank, size, or confirm anything."
LABEL_LIMIT_ZH = "影子背景与记录并行——不排序、不定仓位、也不确认任何信号。"

#: Keys that may never appear anywhere in a packet: each one names a fused or
#: ranked figure.  Matched as a substring of a lower-cased key.
_FORBIDDEN_KEY_FRAGMENTS = (
    "composite",
    "fused",
    "conviction",
    "score",
    "rank",
    "weight",
    "grade",
    "total",
    "overall",
    "aggregate",
    "verdict",
    "recommendation",
)

#: Keys that legitimately carry a number OUTSIDE a reading, because they describe
#: the packet's own shape or clocks rather than the market.
_NUMERIC_METADATA_KEYS = frozenset({
    "age_days",
    "sla_days",
    "bars_at_known_at",
    "leg_count",
    "present_leg_count",
    "contradiction_count",
    "candidate_count",
    "packet_count",
    "staleness_hours",
})


class ShadowContextError(ValueError):
    """A packet that cannot be built honestly is an error, never a partial packet."""


def _authority() -> dict[str, Any]:
    """The same typed authority fence the candidate queue publishes.

    Mirrored rather than imported so a future change to one is a visible diff in
    the other — `federation._display_only_authority` requires the COMPLETE fence,
    so a silently dropped key here would fail its consumer closed.
    """

    return {
        "tier": "display",
        "context_only": True,
        "can_rank": False,
        "can_size": False,
        "can_gate": False,
        "can_originate_signal": False,
        "can_add_candidates": False,
        "can_escalate": False,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prefix: str, value: Any) -> str:
    return f"{prefix}-{sha256(_canonical_json(value).encode('utf-8')).hexdigest()[:24]}"


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _reading_value(leg: Mapping[str, Any], name: str) -> Any:
    for row in leg.get("readings") or []:
        if isinstance(row, Mapping) and row.get("name") == name:
            return row.get("value")
    return None


def _leg_by_name(legs: Sequence[Mapping[str, Any]], name: str) -> Mapping[str, Any] | None:
    return next((leg for leg in legs if isinstance(leg, Mapping) and leg.get("name") == name), None)


# --------------------------------------------------------------------------- #
# the fused-score guard
# --------------------------------------------------------------------------- #


def assert_no_fused_score(packet: Any, *, path: str = "packet") -> None:
    """Raise unless every number in ``packet`` lives inside a named leg reading.

    Two independent refusals, because either alone is escapable:

    1. **by name** — any key advertising a composite or a rank fails, even when
       its value is null today.  A ``"confluence_score": None`` field is a slot
       waiting to be filled by the next author.
    2. **by position** — a bare number outside a ``readings`` entry or the small
       metadata allowlist fails.  This is the one that catches the composite
       nobody named, which is the way this defect actually arrives.
    """

    if isinstance(packet, Mapping):
        for key, value in packet.items():
            child_path = f"{path}.{key}"
            if key == "authority":
                # The authority fence DENIES ranking, so its own keys read as
                # composite names ("can_rank").  Pin it to the exact fence and
                # skip the name walk rather than special-casing the fragment —
                # a fence that drifted would then fail here, not slip through.
                if value != _authority():
                    raise ShadowContextError(
                        f"{child_path} is not the complete display-only authority fence"
                    )
                continue
            lowered = str(key).lower()
            for fragment in _FORBIDDEN_KEY_FRAGMENTS:
                if fragment in lowered:
                    raise ShadowContextError(
                        f"{path}.{key} names a fused or ranked figure ({fragment!r}); "
                        "a shadow packet carries named legs only"
                    )
            if key == "readings" and isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                for index, row in enumerate(value):
                    _assert_reading(row, path=f"{child_path}[{index}]")
                continue
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                if str(key) not in _NUMERIC_METADATA_KEYS:
                    raise ShadowContextError(
                        f"{child_path} carries a bare number outside a named leg reading; "
                        "every measurement must be a named reading"
                    )
                continue
            assert_no_fused_score(value, path=child_path)
        return
    if isinstance(packet, Sequence) and not isinstance(packet, (str, bytes)):
        for index, row in enumerate(packet):
            assert_no_fused_score(row, path=f"{path}[{index}]")
        return
    if isinstance(packet, (int, float)) and not isinstance(packet, bool):
        raise ShadowContextError(f"{path} carries a bare number outside a named leg reading")


def _assert_reading(row: Any, *, path: str) -> None:
    if not isinstance(row, Mapping):
        raise ShadowContextError(f"{path} is not a reading mapping")
    if _text(row.get("name")) is None:
        raise ShadowContextError(f"{path} has no reading name; an unnamed reading is a fused figure")
    for key in row:
        lowered = str(key).lower()
        if key == "name":
            continue
        for fragment in _FORBIDDEN_KEY_FRAGMENTS:
            if fragment in lowered:
                raise ShadowContextError(f"{path}.{key} names a fused or ranked figure ({fragment!r})")
    value = row.get("value")
    if isinstance(value, (Mapping, list, tuple)):
        raise ShadowContextError(
            f"{path}.value is a container; a reading holds one scalar so it stays separately inspectable"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise ShadowContextError(f"{path}.value is not finite")


# --------------------------------------------------------------------------- #
# procurement legs — a restatement of what the candidate already proves
# --------------------------------------------------------------------------- #


def _procurement_event_leg(candidate: Mapping[str, Any]) -> dict[str, Any]:
    event = candidate.get("source_event") if isinstance(candidate.get("source_event"), Mapping) else {}
    amount = event.get("amount") if isinstance(event.get("amount"), Mapping) else {}
    receipts = [
        row for row in (candidate.get("source_receipt_refs") or []) if isinstance(row, Mapping)
    ]
    materiality = candidate.get("materiality") if isinstance(candidate.get("materiality"), Mapping) else {}
    freshness = candidate.get("freshness") if isinstance(candidate.get("freshness"), Mapping) else {}
    readings = [
        {"name": "candidate_family", "value": _text(candidate.get("candidate_family")), "kind": "state", "units": None},
        {"name": "event_type", "value": _text(event.get("event_type")), "kind": "state", "units": None},
        {"name": "source_rail", "value": _text(event.get("source_rail")), "kind": "state", "units": None},
        {"name": "transmission_direction", "value": _text(candidate.get("transmission_direction")), "kind": "state", "units": None},
        {"name": "observed_event_amount", "value": _finite(amount.get("value")), "kind": "level", "units": _text(amount.get("units")) or "usd"},
        {"name": "attributable_amount", "value": _finite(materiality.get("attributable_amount")), "kind": "level", "units": "usd"},
        {"name": "economic_share", "value": _finite(materiality.get("economic_share")), "kind": "ratio", "units": None},
        {"name": "materiality_comparison_state", "value": _text(materiality.get("comparison_state")), "kind": "state", "units": None},
        {"name": "receipt_count", "value": len(receipts), "kind": "count", "units": None},
        {"name": "is_late_discovery", "value": bool(event.get("is_late_discovery")) if event.get("is_late_discovery") is not None else None, "kind": "state", "units": None},
    ]
    return {
        "leg_id": "procurement_event",
        "leg_family": "procurement",
        "name": "procurement_event",
        "status": "present" if _text(event.get("event_id")) else "missing",
        # The candidate refuses to publish a materiality ratio without an exact
        # issuer-attributed denominator; the packet repeats that refusal by name
        # rather than quietly shipping a leg with a hole in it.
        "reason_code": _text(materiality.get("reason_code")),
        "readings": readings,
        "clocks": {
            "source_time": _iso(event.get("effective_at")),
            "observed_at": _iso(event.get("known_at")),
            "observed_at_basis": "award_event_known_at",
            "known_at": _iso(candidate.get("known_at")),
        },
        "freshness": {
            "status": _text(freshness.get("award_events_status")) or "unknown",
            "age_days": None,
            "sla_days": None,
        },
        "provenance": {
            "lobe": "government_revenue",
            "loader": "engine.government_revenue.candidates.build_candidate_observations",
            "artifact": "data/government_revenue/candidate_queue.json",
            "source_content_id": _text(event.get("source_content_id")),
            "receipt_refs": sorted({_text(row.get("ref_id")) or "" for row in receipts} - {""})[:8],
        },
    }


def _issuer_attribution_leg(candidate: Mapping[str, Any]) -> dict[str, Any]:
    resolution = (
        candidate.get("issuer_resolution_ref")
        if isinstance(candidate.get("issuer_resolution_ref"), Mapping)
        else {}
    )
    issuer = candidate.get("issuer") if isinstance(candidate.get("issuer"), Mapping) else {}
    freshness = candidate.get("freshness") if isinstance(candidate.get("freshness"), Mapping) else {}
    path_refs = [ref for ref in (candidate.get("ownership_path_refs") or []) if _text(ref)]
    evidence_refs = [ref for ref in (resolution.get("evidence_refs") or []) if _text(ref)]
    readings = [
        {"name": "ticker", "value": _text(issuer.get("ticker")) or _text(candidate.get("ticker")), "kind": "state", "units": None},
        {"name": "company_name", "value": _text(issuer.get("company_name")), "kind": "state", "units": None},
        {"name": "relation_semantic", "value": _text(resolution.get("relation_semantic")), "kind": "state", "units": None},
        {"name": "resolution_state", "value": _text(resolution.get("resolution_state")), "kind": "state", "units": None},
        {"name": "ownership_path_edge_count", "value": len(path_refs), "kind": "count", "units": None},
        {"name": "evidence_ref_count", "value": len(evidence_refs), "kind": "count", "units": None},
    ]
    return {
        "leg_id": "issuer_attribution",
        "leg_family": "procurement",
        "name": "issuer_attribution",
        "status": "present" if _text(resolution.get("relation_semantic")) == "reviewed" else "abstained",
        "reason_code": None if _text(resolution.get("relation_semantic")) == "reviewed" else "issuer_path_not_reviewed",
        "readings": readings,
        "clocks": {
            "source_time": _iso(freshness.get("graph_known_at")),
            "observed_at": _iso(freshness.get("graph_known_at")),
            "observed_at_basis": "recipient_graph_known_at",
            "known_at": _iso(candidate.get("known_at")),
        },
        "freshness": {
            "status": _text(freshness.get("recipient_graph_status")) or "unknown",
            "age_days": None,
            "sla_days": None,
        },
        "provenance": {
            "lobe": "government_revenue",
            "loader": "engine.government_revenue.entity_resolution.load_recipient_entity_graph",
            "artifact": "data/government_revenue/recipient_entity_graph.json",
            "graph_id": _text(resolution.get("graph_id")),
            "graph_digest": _text(resolution.get("graph_digest")),
            "ownership_path_refs": sorted(_text(ref) or "" for ref in path_refs)[:8],
            "evidence_refs": sorted(_text(ref) or "" for ref in evidence_refs)[:8],
        },
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# --------------------------------------------------------------------------- #
# contradictions
# --------------------------------------------------------------------------- #


def _contradiction(
    kind: str,
    *,
    legs: Sequence[str],
    statement_en: str,
    statement_zh: str,
    reading_names: Sequence[str] = (),
) -> dict[str, Any]:
    # ``reading_names``, never ``readings``: this is a list of reading NAMES that
    # point back into the legs, not a list of reading objects.  The two are walked
    # differently by ``assert_no_fused_score``, so the distinction is load-bearing.
    return {
        "contradiction_id": _digest("grsx1", {"kind": kind, "legs": sorted(legs)}),
        "kind": kind,
        "legs": sorted(legs),
        "reading_names": sorted(reading_names),
        # The handling field is the promise the gate checks: both legs keep their
        # own readings, and nothing downstream may net them against each other.
        "handling": "both_legs_remain_visible_not_averaged",
        "statement_en": statement_en,
        "statement_zh": statement_zh,
    }


def find_contradictions(
    candidate: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Name every disagreement between legs, in a fixed order.

    Deliberately narrow: only pairs whose disagreement a reader can act on.  A
    long list of weak tensions trains people to ignore the block, which is worse
    than an empty list.
    """

    found: list[dict[str, Any]] = []
    trend = _leg_by_name(legs, "technical_trend")
    strength = _leg_by_name(legs, "relative_strength")
    runup = _leg_by_name(legs, "runup_extension")
    regime = _leg_by_name(legs, "regime_fit")
    direction = _text(candidate.get("transmission_direction"))

    if trend is not None and strength is not None and trend["status"] == "present" and strength["status"] == "present":
        above_200 = _reading_value(trend, "above_200dma")
        rs_3m = _reading_value(strength, "rs_3m_vs_bench")
        if above_200 is True and isinstance(rs_3m, (int, float)) and rs_3m < 0:
            found.append(_contradiction(
                "trend_up_while_relative_strength_negative",
                legs=[trend["leg_id"], strength["leg_id"]],
                reading_names=["above_200dma", "rs_3m_vs_bench"],
                statement_en="The name is above its 200-day line but has lagged the benchmark over three months — the two readings disagree.",
                statement_zh="该名称位于 200 日均线之上，但近三个月落后于基准——两项读数彼此不一致。",
            ))

    if runup is not None and runup["status"] == "present" and direction == "possible_positive":
        percentile = _reading_value(runup, "runup_63d_own_history_percentile")
        if isinstance(percentile, (int, float)) and percentile >= 0.9:
            found.append(_contradiction(
                "possible_positive_event_into_extended_runup",
                legs=[runup["leg_id"], "procurement_event"],
                reading_names=["runup_63d_own_history_percentile", "transmission_direction"],
                statement_en="The award change reads possible-positive, but the three-month move is already in the top tenth of this name's own history.",
                statement_zh="该授标变化偏正面，但近三个月涨幅已处于该名称自身历史的前十分之一。",
            ))

    if regime is not None and trend is not None and regime["status"] == "present" and trend["status"] == "present":
        risk = _text(_reading_value(regime, "fused_risk"))
        above_50 = _reading_value(trend, "above_50dma")
        if risk in {"risk_off", "off"} and above_50 is True:
            found.append(_contradiction(
                "risk_off_regime_while_name_trends_up",
                legs=[regime["leg_id"], trend["leg_id"]],
                reading_names=["fused_risk", "above_50dma"],
                statement_en="The name trends above its 50-day line while the market regime reads risk-off — the two readings disagree.",
                statement_zh="该名称位于 50 日均线之上，而市场状态读数偏避险——两项读数彼此不一致。",
            ))

    stale = sorted(leg["leg_id"] for leg in legs if isinstance(leg, Mapping) and leg.get("status") == "stale")
    if stale:
        found.append(_contradiction(
            "leg_older_than_its_own_service_level",
            legs=stale,
            statement_en="One or more readings are older than their own freshness limit; they are shown with their age rather than dropped.",
            statement_zh="部分读数已超过各自的时效上限；这些读数附带时效一并展示，而非被剔除。",
        ))
    return found


def _integrity_leg(legs: Sequence[Mapping[str, Any]], contradictions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Gaps and disagreements as a leg of their own, so absence is a fact on the page."""

    by_status = {status: [] for status in LEG_STATUSES}
    for leg in legs:
        if isinstance(leg, Mapping) and leg.get("status") in by_status:
            by_status[leg["status"]].append(str(leg.get("leg_id")))
    readings = [
        {"name": "leg_count", "value": len(legs), "kind": "count", "units": None},
        {"name": "present_legs", "value": len(by_status["present"]), "kind": "count", "units": None},
        {"name": "stale_legs", "value": len(by_status["stale"]), "kind": "count", "units": None},
        {"name": "missing_legs", "value": len(by_status["missing"]), "kind": "count", "units": None},
        {"name": "abstained_legs", "value": len(by_status["abstained"]), "kind": "count", "units": None},
        {"name": "disagreements", "value": len(contradictions), "kind": "count", "units": None},
    ]
    return {
        "leg_id": "packet_integrity",
        "leg_family": "integrity",
        "name": "packet_integrity",
        "status": "present",
        "reason_code": None,
        "readings": readings,
        "clocks": {},
        "freshness": {"status": "present", "age_days": None, "sla_days": None},
        "provenance": {
            "lobe": "government_revenue",
            "loader": "engine.government_revenue.shadow_context.build_shadow_packet",
            "artifact": None,
            "stale_leg_ids": by_status["stale"],
            "missing_leg_ids": by_status["missing"],
            "abstained_leg_ids": by_status["abstained"],
        },
    }


# --------------------------------------------------------------------------- #
# packets
# --------------------------------------------------------------------------- #


def build_shadow_packet(
    candidate: Mapping[str, Any],
    *,
    repo_root: Path | str,
    data_root: Path | str | None = None,
    legs_provider: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
    theme_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
    filings_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Return one candidate's shadow packet.  Reads the candidate; never returns it.

    ``legs_provider`` exists so a test can hand in fixture legs without a price
    store, and so a caller that already computed the market legs for one name at
    one clock can reuse them.  Its absence is the production path.
    """

    if not isinstance(candidate, Mapping):
        raise ShadowContextError("candidate must be a mapping")
    candidate_id = _text(candidate.get("candidate_id"))
    observation_id = _text(candidate.get("observation_id"))
    known_at = _iso(candidate.get("known_at"))
    ticker = _text(candidate.get("ticker"))
    if candidate_id is None or observation_id is None or known_at is None or ticker is None:
        raise ShadowContextError(
            "candidate must carry candidate_id, observation_id, ticker, and a parseable known_at"
        )

    provider = legs_provider if legs_provider is not None else market_context_legs
    market_legs = list(provider(
        ticker,
        known_at,
        repo_root=repo_root,
        data_root=data_root,
        theme_reader=theme_reader,
        filings_reader=filings_reader,
    ))
    legs: list[dict[str, Any]] = [
        _procurement_event_leg(candidate),
        _issuer_attribution_leg(candidate),
        *[dict(leg) for leg in market_legs],
    ]
    contradictions = find_contradictions(candidate, legs)
    legs.append(_integrity_leg(legs, contradictions))

    packet = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "packet_id": _digest("grsp1", {
            "candidate_id": candidate_id,
            "observation_id": observation_id,
            "legs": [
                {
                    "leg_id": leg["leg_id"],
                    "status": leg["status"],
                    "readings": leg["readings"],
                    "clocks": leg["clocks"],
                }
                for leg in legs
            ],
        }),
        "candidate_id": candidate_id,
        "observation_id": observation_id,
        "ticker": ticker,
        "issuer_company_id": _text(candidate.get("issuer_company_id")),
        "known_at": known_at,
        "candidate_artifact_content_ids": sorted(
            _text(row) or "" for row in (candidate.get("artifact_content_ids") or [])
        ),
        "label": {
            "en": LABEL_EN,
            "zh": LABEL_ZH,
            "limit_en": LABEL_LIMIT_EN,
            "limit_zh": LABEL_LIMIT_ZH,
        },
        "legs": legs,
        "contradictions": contradictions,
        "coverage": {
            "leg_names": [leg["name"] for leg in legs],
            "present_leg_names": [leg["name"] for leg in legs if leg["status"] == "present"],
            "unavailable_leg_names": [
                leg["name"] for leg in legs if leg["status"] in {"missing", "abstained"}
            ],
            "is_complete": False,
        },
        "authority": _authority(),
        "limitations": [
            "Shadow context is display-tier cross-check evidence; it cannot rank, size, gate, or originate a signal.",
            "Every market reading is cut at the candidate's own known_at; a reading with no usable source is reported missing or abstained, never as a zero.",
            "Legs that disagree are both shown with their own readings; nothing here is averaged into one figure.",
        ],
    }
    assert_no_fused_score(packet)
    return packet


def build_shadow_context(
    candidates: Iterable[Mapping[str, Any]],
    *,
    repo_root: Path | str,
    generated_at: str,
    data_root: Path | str | None = None,
    legs_provider: Callable[..., Sequence[Mapping[str, Any]]] | None = None,
    theme_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
    filings_reader: Callable[[str, Any], Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Build the shadow-context envelope for an already-ordered candidate list.

    Packets follow the order the candidates arrived in, so the queue's display
    sort stays the single owner of ordering — this envelope never re-sorts and
    never drops a candidate, because either would be a selection act.
    """

    generated = _iso(generated_at)
    if generated is None:
        raise ShadowContextError("generated_at must be parseable")
    rows = [row for row in candidates if isinstance(row, Mapping)]
    packets = [
        build_shadow_packet(
            row,
            repo_root=repo_root,
            data_root=data_root,
            legs_provider=legs_provider,
            theme_reader=theme_reader,
            filings_reader=filings_reader,
        )
        for row in rows
    ]
    envelope = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "label": {
            "en": LABEL_EN,
            "zh": LABEL_ZH,
            "limit_en": LABEL_LIMIT_EN,
            "limit_zh": LABEL_LIMIT_ZH,
        },
        "packets": packets,
        "coverage": {
            "candidate_count": len(rows),
            "packet_count": len(packets),
            "packet_order": "candidate_input_order",
            "is_complete": False,
        },
        "authority": _authority(),
        "limitations": [
            "Shadow context annotates candidates another engine already admitted; it cannot add, remove, or reorder one.",
            "Packet order mirrors the candidate queue's own display sort and is never an investment rank.",
        ],
    }
    assert_no_fused_score(envelope)
    return envelope


__all__ = [
    "CONTRACT",
    "LABEL_EN",
    "LABEL_LIMIT_EN",
    "LABEL_LIMIT_ZH",
    "LABEL_ZH",
    "SCHEMA_VERSION",
    "ShadowContextError",
    "assert_no_fused_score",
    "build_shadow_context",
    "build_shadow_packet",
    "find_contradictions",
]
