"""Wave 9E gates — Neural Web shadow cross-check packets.

Every acceptance gate in the handoff's Wave 9E section is one test here:

  * candidate set AND ordering byte-identical with the shadow layer disabled,
    unavailable, delayed, or contradictory;
  * no unnamed composite score hides the contributing legs;
  * every leg carries source time, known-at, freshness, status, provenance;
  * contradictory evidence stays visible rather than averaged away;
  * the label is ``shadow context``, never signal confirmation.

The candidate rows come from the real candidate engine via the existing
candidates suite's own fixtures, so a packet is always built against the shipped
contract shape rather than a hand-typed approximation of it.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

import pandas as pd  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

from engine.government_revenue import market_context as mctx  # noqa: E402
from engine.government_revenue import shadow_context as sc  # noqa: E402
from engine.government_revenue.candidates import (  # noqa: E402
    build_candidate_observations,
    build_candidate_queue,
)
from tests.test_government_revenue_candidates import (  # noqa: E402
    GENERATED_AT,
    _award_event,
    _graph,
    _payload,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts" / "government_revenue"

#: Vocabulary that may never reach a user-visible string on a cycle surface
#: (operator 2026-07-27): tripwires keep evaluating, but the words stay in the
#: Calibration Lab.
BANNED_FRONT_FACING = (
    "falsifier",
    "falsified",
    "refuted",
    "refutation",
    "invalidated thesis",
    "证伪",
)


def _candidate() -> dict:
    rows = build_candidate_observations(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    assert len(rows) == 1, "the candidates fixture must yield exactly one exact candidate"
    return rows[0]


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(
        _schema("government_revenue_shadow_context.v1.schema.json"),
        format_checker=FormatChecker(),
    )


# --------------------------------------------------------------------------- #
# fixture leg providers — one per Neural Web availability state
# --------------------------------------------------------------------------- #


def _leg(
    name: str,
    *,
    status: str = "present",
    readings: list[dict] | None = None,
    family: str = "market_context",
    source_time: str | None = "2026-08-01",
    age_days: float | None = 1.0,
    sla_days: float | None = 7.0,
) -> dict:
    return {
        "leg_id": f"market_{name}",
        "leg_family": family,
        "name": name,
        "status": status,
        "reason_code": None,
        "readings": readings or [{"name": "probe", "value": 1.0, "kind": "level", "units": "usd"}],
        "clocks": {
            "source_time": source_time,
            "observed_at": source_time,
            "observed_at_basis": "source_bar_date",
            "known_at": "2026-08-02T12:00:00+00:00",
        },
        "freshness": {"status": status, "age_days": age_days, "sla_days": sla_days},
        "provenance": {"lobe": "fixture", "loader": "fixture", "artifact": None},
    }


def _present_legs(*_args, **_kwargs) -> list[dict]:
    return [
        _leg("technical_trend", readings=[
            {"name": "above_50dma", "value": True, "kind": "state", "units": None},
            {"name": "above_200dma", "value": True, "kind": "state", "units": None},
        ]),
        _leg("relative_strength", readings=[
            {"name": "rs_3m_vs_bench", "value": 4.5, "kind": "percent", "units": "pct"},
        ]),
        _leg("volatility_liquidity"),
        _leg("runup_extension", readings=[
            {"name": "runup_63d_own_history_percentile", "value": 0.42, "kind": "percentile", "units": "fraction"},
        ]),
        _leg("regime_fit", readings=[
            {"name": "fused_risk", "value": "neutral", "kind": "state", "units": None},
        ]),
        _leg("prophet_confluence_state"),
        _leg("budget_theme_relevance", status="abstained"),
        _leg("filings_corroboration", status="abstained"),
    ]


def _unavailable_legs(*_args, **_kwargs) -> list[dict]:
    """Every leg missing — the Neural Web side is down or the stores are absent."""
    return [
        _leg(name, status="missing", readings=[], source_time=None, age_days=None, sla_days=None)
        for name in (
            "technical_trend", "relative_strength", "volatility_liquidity", "runup_extension",
            "regime_fit", "prophet_confluence_state", "budget_theme_relevance", "filings_corroboration",
        )
    ]


def _delayed_legs(*_args, **_kwargs) -> list[dict]:
    """Every leg stale — the sources answered, but later than their own SLA."""
    return [
        _leg(name, status="stale", source_time="2026-06-01", age_days=62.0)
        for name in (
            "technical_trend", "relative_strength", "volatility_liquidity", "runup_extension",
            "regime_fit", "prophet_confluence_state", "budget_theme_relevance", "filings_corroboration",
        )
    ]


def _contradictory_legs(*_args, **_kwargs) -> list[dict]:
    """Trend up, relative strength negative, run-up already extended, regime risk-off."""
    return [
        _leg("technical_trend", readings=[
            {"name": "above_50dma", "value": True, "kind": "state", "units": None},
            {"name": "above_200dma", "value": True, "kind": "state", "units": None},
        ]),
        _leg("relative_strength", readings=[
            {"name": "rs_3m_vs_bench", "value": -11.25, "kind": "percent", "units": "pct"},
        ]),
        _leg("volatility_liquidity"),
        _leg("runup_extension", readings=[
            {"name": "runup_63d_own_history_percentile", "value": 0.97, "kind": "percentile", "units": "fraction"},
        ]),
        _leg("regime_fit", readings=[
            {"name": "fused_risk", "value": "risk_off", "kind": "state", "units": None},
        ]),
        _leg("prophet_confluence_state"),
        _leg("budget_theme_relevance", status="abstained"),
        _leg("filings_corroboration", status="abstained"),
    ]


def _raising_legs(*_args, **_kwargs) -> list[dict]:
    raise RuntimeError("neural web unreachable")


ALL_STATES = {
    "present": _present_legs,
    "unavailable": _unavailable_legs,
    "delayed": _delayed_legs,
    "contradictory": _contradictory_legs,
}


# --------------------------------------------------------------------------- #
# GATE 1 — byte-identical candidate set and ordering, in every state
# --------------------------------------------------------------------------- #


def _candidate_bytes(queue: dict) -> str:
    """The exact wire form of the candidate set AND its order."""
    return json.dumps(queue["candidates"], sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize("state", sorted(ALL_STATES))
def test_candidate_set_and_ordering_are_byte_identical_in_every_shadow_state(
    state: str, tmp_path: Path
) -> None:
    """The gate, stated as bytes: no shadow state may move one byte of the queue.

    The queue is rebuilt AFTER packets are constructed from its own candidate
    rows, so a builder that mutated a candidate in place — the realistic way this
    breaks — is caught, not just one that returns a different list.
    """
    baseline = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    baseline_bytes = _candidate_bytes(baseline)
    baseline_order = [row["candidate_id"] for row in baseline["candidates"]]

    envelope = sc.build_shadow_context(
        baseline["candidates"],
        repo_root=tmp_path,
        generated_at=GENERATED_AT,
        legs_provider=ALL_STATES[state],
    )

    assert _candidate_bytes(baseline) == baseline_bytes
    assert [row["candidate_id"] for row in baseline["candidates"]] == baseline_order
    rebuilt = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    assert _candidate_bytes(rebuilt) == baseline_bytes
    assert rebuilt["content_id"] == baseline["content_id"]
    assert len(envelope["packets"]) == len(baseline["candidates"])
    assert [packet["candidate_id"] for packet in envelope["packets"]] == baseline_order


def test_shadow_layer_failure_cannot_reach_the_candidate_queue(tmp_path: Path) -> None:
    """A raising leg provider surfaces as an error to ITS caller, never as queue drift."""
    baseline = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    baseline_bytes = _candidate_bytes(baseline)

    with pytest.raises(RuntimeError):
        sc.build_shadow_context(
            baseline["candidates"],
            repo_root=tmp_path,
            generated_at=GENERATED_AT,
            legs_provider=_raising_legs,
        )

    assert _candidate_bytes(baseline) == baseline_bytes
    rebuilt = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    assert _candidate_bytes(rebuilt) == baseline_bytes


def test_packet_never_carries_a_candidate_row_back_out(tmp_path: Path) -> None:
    """The packet REFERENCES a candidate by id; it never embeds or restates the row.

    An embedded copy would make the packet a second source of candidate truth,
    and the next reader would not know which one won.
    """
    candidate = _candidate()
    packet = sc.build_shadow_packet(candidate, repo_root=tmp_path, legs_provider=_present_legs)

    rendered = json.dumps(packet, sort_keys=True)
    assert candidate["candidate_id"] in rendered
    for field in ("candidate_state", "crosscheck_state", "internal_watch_conditions"):
        assert field not in packet
    assert "is_neuralweb_trade_candidate" not in rendered


# --------------------------------------------------------------------------- #
# GATE 2 — no unnamed composite score
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", sorted(ALL_STATES))
def test_real_packet_passes_the_fused_score_guard(state: str, tmp_path: Path) -> None:
    envelope = sc.build_shadow_context(
        [_candidate()],
        repo_root=tmp_path,
        generated_at=GENERATED_AT,
        legs_provider=ALL_STATES[state],
    )
    sc.assert_no_fused_score(envelope)


@pytest.mark.parametrize(
    ("mutation", "description"),
    [
        (lambda p: p.update({"confluence_score": 0.82}), "named composite at packet level"),
        (lambda p: p.update({"shadow_score": None}), "null-valued score slot"),
        (lambda p: p.update({"overall_state": "constructive"}), "overall-prefixed summary"),
        (lambda p: p.update({"rank_hint": 3}), "rank field"),
        (lambda p: p.update({"leg_weighting": {"trend": 0.4}}), "weighting map"),
        (lambda p: p["legs"][0].update({"leg_value": 7.5}), "bare number on a leg"),
        (lambda p: p["legs"][0].update({"conviction": "high"}), "conviction on a leg"),
        (lambda p: p["legs"][0]["readings"].append({"value": 1.0, "kind": "level", "units": None}), "unnamed reading"),
        (
            lambda p: p["legs"][0]["readings"].append(
                {"name": "nested", "value": {"a": 1}, "kind": "level", "units": None}
            ),
            "container-valued reading",
        ),
        (lambda p: p["coverage"].update({"present_fraction": 0.5}), "bare number in coverage"),
    ],
)
def test_fused_score_guard_refuses_every_shape_a_composite_arrives_in(
    mutation, description: str, tmp_path: Path
) -> None:
    """Mutation gate: the guard must fail on each injected composite.

    Without this the guard is vacuous — a payload that happens to carry no
    composite today passes a guard that checks nothing.
    """
    packet = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_present_legs)
    mutation(packet)

    with pytest.raises(sc.ShadowContextError):
        sc.assert_no_fused_score(packet)


def test_no_leg_carries_a_summary_number_of_its_own(tmp_path: Path) -> None:
    """Structural restatement of gate 2: a leg's numbers live only in readings."""
    packet = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_present_legs)

    for leg in packet["legs"]:
        for key, value in leg.items():
            if key in {"readings", "clocks", "freshness", "provenance"}:
                continue
            assert not isinstance(value, (int, float)) or isinstance(value, bool), (
                f"{leg['leg_id']}.{key} is a leg-level number"
            )


# --------------------------------------------------------------------------- #
# GATE 3 — every leg carries its own clocks, freshness, status, provenance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", sorted(ALL_STATES))
def test_every_leg_declares_status_clocks_freshness_and_provenance(
    state: str, tmp_path: Path
) -> None:
    packet = sc.build_shadow_packet(
        _candidate(), repo_root=tmp_path, legs_provider=ALL_STATES[state]
    )

    assert packet["legs"], "a packet with no legs is not a packet"
    for leg in packet["legs"]:
        assert leg["status"] in mctx.LEG_STATUSES, leg["leg_id"]
        assert set(leg) >= {
            "leg_id", "leg_family", "name", "status", "reason_code",
            "readings", "clocks", "freshness", "provenance",
        }, leg["leg_id"]
        assert isinstance(leg["clocks"], dict), leg["leg_id"]
        assert isinstance(leg["freshness"], dict), leg["leg_id"]
        assert "status" in leg["freshness"], leg["leg_id"]
        assert isinstance(leg["provenance"], dict), leg["leg_id"]
        if leg["leg_family"] == "integrity":
            continue
        assert "known_at" in leg["clocks"], leg["leg_id"]
        assert "source_time" in leg["clocks"], leg["leg_id"]
        if leg["status"] in {"present", "stale"}:
            assert leg["clocks"]["source_time"] is not None, leg["leg_id"]


def test_unavailable_and_abstained_legs_are_named_not_omitted(tmp_path: Path) -> None:
    """A gap must be a row on the page: a shorter list reads as "we did not look"."""
    present = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_present_legs)
    missing = sc.build_shadow_packet(
        _candidate(), repo_root=tmp_path, legs_provider=_unavailable_legs
    )

    assert [leg["name"] for leg in present["legs"]] == [leg["name"] for leg in missing["legs"]]
    assert all(
        leg["status"] == "missing"
        for leg in missing["legs"]
        if leg["leg_family"] == "market_context"
    )
    assert missing["coverage"]["unavailable_leg_names"]
    integrity = next(leg for leg in missing["legs"] if leg["leg_family"] == "integrity")
    assert dict(
        (row["name"], row["value"]) for row in integrity["readings"]
    )["missing_legs"] == 8


def test_materiality_refusal_is_carried_through_as_a_named_reason(tmp_path: Path) -> None:
    """The candidate refuses a materiality ratio; the packet repeats that refusal.

    Silently omitting it would let a reader assume the ratio was computed and
    found unremarkable.
    """
    packet = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_present_legs)
    leg = next(leg for leg in packet["legs"] if leg["name"] == "procurement_event")

    assert leg["reason_code"] == "exact_issuer_attributed_denominator_not_available"
    readings = {row["name"]: row["value"] for row in leg["readings"]}
    assert readings["materiality_comparison_state"] == "not_comparable"
    assert "materiality_ratio" not in readings


# --------------------------------------------------------------------------- #
# GATE 4 — contradictions stay visible, never averaged
# --------------------------------------------------------------------------- #


def test_contradictions_are_named_and_both_legs_keep_their_own_readings(
    tmp_path: Path,
) -> None:
    packet = sc.build_shadow_packet(
        _candidate(), repo_root=tmp_path, legs_provider=_contradictory_legs
    )

    kinds = {row["kind"] for row in packet["contradictions"]}
    assert "trend_up_while_relative_strength_negative" in kinds
    assert "possible_positive_event_into_extended_runup" in kinds
    assert "risk_off_regime_while_name_trends_up" in kinds
    assert all(
        row["handling"] == "both_legs_remain_visible_not_averaged"
        for row in packet["contradictions"]
    )

    # Both sides of every contradiction still ship their ORIGINAL readings.
    fixture = {leg["name"]: leg for leg in _contradictory_legs()}
    for name in ("technical_trend", "relative_strength", "runup_extension", "regime_fit"):
        built = next(leg for leg in packet["legs"] if leg["name"] == name)
        assert built["readings"] == fixture[name]["readings"], name
        assert built["status"] == fixture[name]["status"], name


def test_a_stale_leg_is_disclosed_as_a_contradiction_rather_than_dropped(
    tmp_path: Path,
) -> None:
    packet = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_delayed_legs)

    stale = next(
        row for row in packet["contradictions"]
        if row["kind"] == "leg_older_than_its_own_service_level"
    )
    assert len(stale["legs"]) == 8
    assert all(
        leg["freshness"]["age_days"] == 62.0
        for leg in packet["legs"]
        if leg["leg_family"] == "market_context"
    )


def test_a_clean_packet_reports_no_contradiction_rather_than_a_neutral_one(
    tmp_path: Path,
) -> None:
    packet = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_present_legs)

    assert packet["contradictions"] == []


# --------------------------------------------------------------------------- #
# GATE 5 — the label is shadow context, and the copy is not refutation-shaped
# --------------------------------------------------------------------------- #


def test_label_says_shadow_context_bilingually_and_never_confirmation(
    tmp_path: Path,
) -> None:
    envelope = sc.build_shadow_context(
        [_candidate()], repo_root=tmp_path, generated_at=GENERATED_AT, legs_provider=_present_legs
    )

    for label in (envelope["label"], envelope["packets"][0]["label"]):
        assert label["en"] == "shadow context"
        assert label["zh"] == "影子背景"
        # The limit copy may MENTION confirmation only to deny it.
        assert "does not rank, size, or confirm" in label["limit_en"]
        assert "不确认任何信号" in label["limit_zh"]
    rendered = json.dumps(envelope, ensure_ascii=False).lower()
    for claim in ("signal confirmation", "confirmed signal", "confirms the", "信号确认。", "已确认信号"):
        assert claim not in rendered


def test_front_facing_copy_carries_no_refutation_vocabulary(tmp_path: Path) -> None:
    """Operator 2026-07-27: tripwires keep running, the words stay off the surface."""
    envelope = sc.build_shadow_context(
        [_candidate()],
        repo_root=tmp_path,
        generated_at=GENERATED_AT,
        legs_provider=_contradictory_legs,
    )

    surfaced = [
        row[key]
        for packet in envelope["packets"]
        for row in packet["contradictions"]
        for key in ("statement_en", "statement_zh")
    ]
    surfaced.extend(envelope["label"].values())
    surfaced.extend(envelope["limitations"])
    surfaced.extend(envelope["packets"][0]["limitations"])
    assert surfaced
    for text in surfaced:
        lowered = text.lower()
        for banned in BANNED_FRONT_FACING:
            assert banned not in lowered, f"{banned!r} reached front-facing copy: {text!r}"


# --------------------------------------------------------------------------- #
# authority, contract, determinism
# --------------------------------------------------------------------------- #


def test_packet_authority_mirrors_the_candidate_queue_fence(tmp_path: Path) -> None:
    queue = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    envelope = sc.build_shadow_context(
        queue["candidates"], repo_root=tmp_path, generated_at=GENERATED_AT, legs_provider=_present_legs
    )

    assert envelope["authority"] == queue["authority"]
    assert envelope["packets"][0]["authority"] == queue["authority"]
    assert envelope["coverage"]["packet_order"] == "candidate_input_order"


@pytest.mark.parametrize("state", sorted(ALL_STATES))
def test_envelope_satisfies_its_published_contract(state: str, tmp_path: Path) -> None:
    envelope = sc.build_shadow_context(
        [_candidate()],
        repo_root=tmp_path,
        generated_at=GENERATED_AT,
        legs_provider=ALL_STATES[state],
    )

    _validator().validate(envelope)


def test_packet_is_deterministic_and_its_id_tracks_its_readings(tmp_path: Path) -> None:
    first = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_present_legs)
    second = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_present_legs)

    assert first == second
    assert first["packet_id"] == second["packet_id"]

    def _moved(*_args, **_kwargs) -> list[dict]:
        legs = deepcopy(_present_legs())
        legs[0]["readings"][0]["value"] = False
        return legs

    moved = sc.build_shadow_packet(_candidate(), repo_root=tmp_path, legs_provider=_moved)
    assert moved["packet_id"] != first["packet_id"]


def test_packet_requires_a_traceable_candidate(tmp_path: Path) -> None:
    for field in ("candidate_id", "observation_id", "ticker", "known_at"):
        candidate = _candidate()
        candidate.pop(field)
        with pytest.raises(sc.ShadowContextError):
            sc.build_shadow_packet(candidate, repo_root=tmp_path, legs_provider=_present_legs)


# --------------------------------------------------------------------------- #
# point-in-time correctness of the real market legs
# --------------------------------------------------------------------------- #


def _write_ohlcv(root: Path, ticker: str, *, end: str, days: int = 420) -> Path:
    """A synthetic adjusted OHLCV rung with a deterministic, strictly rising close."""
    index = pd.bdate_range(end=pd.Timestamp(end), periods=days)
    close = pd.Series([100.0 + i * 0.25 for i in range(days)], index=index)
    frame = pd.DataFrame({
        "open": close * 0.995,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": pd.Series([1_000_000.0 + (i % 7) * 10_000 for i in range(days)], index=index),
    })
    frame.index.name = "Date"
    path = root / "baskets" / "ohlcv" / f"{ticker}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    return path


def test_market_legs_read_only_bars_at_or_before_known_at(tmp_path: Path) -> None:
    """The time-consciousness law: the last bar used is the last bar <= known_at."""
    data_root = tmp_path / "data"
    _write_ohlcv(data_root, "NOC", end="2026-08-07")

    early = mctx.load_pit_window("NOC", "2026-06-15T12:00:00+00:00", data_root=data_root)
    late = mctx.load_pit_window("NOC", "2026-08-06T12:00:00+00:00", data_root=data_root)

    assert early is not None and late is not None
    assert early.source_time <= pd.Timestamp("2026-06-15")
    assert late.source_time <= pd.Timestamp("2026-08-06")
    assert early.source_time < late.source_time
    assert len(early.close) < len(late.close)
    # A strictly rising synthetic close makes a lookahead loud rather than subtle.
    assert float(early.close.iloc[-1]) < float(late.close.iloc[-1])


def test_tz_aware_candidate_clock_does_not_raise_against_a_tz_naive_price_index(
    tmp_path: Path,
) -> None:
    """Measured trap: aware-vs-naive comparison is a TypeError, not a silent miss."""
    data_root = tmp_path / "data"
    _write_ohlcv(data_root, "NOC", end="2026-08-07")

    window = mctx.load_pit_window(
        "NOC", pd.Timestamp("2026-07-01T00:00:00Z"), data_root=data_root
    )

    assert window is not None
    assert window.cutoff.tzinfo is None
    assert window.source_time <= pd.Timestamp("2026-07-01")


def test_dotted_ticker_resolves_against_the_dash_normalized_store(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_ohlcv(data_root, "BRK-B", end="2026-08-07")

    window = mctx.load_pit_window("BRK.B", "2026-08-06T12:00:00+00:00", data_root=data_root)

    assert window is not None
    assert window.store_ticker == "BRK-B"


def test_absent_price_store_yields_named_missing_legs_not_zeros(tmp_path: Path) -> None:
    legs = mctx.market_context_legs(
        "NOC", "2026-08-06T12:00:00+00:00", repo_root=tmp_path, data_root=tmp_path / "data"
    )

    by_name = {leg["name"]: leg for leg in legs}
    assert len(legs) == 8
    for name in ("technical_trend", "relative_strength", "volatility_liquidity", "runup_extension"):
        assert by_name[name]["status"] == "missing", name
        assert by_name[name]["readings"] == [], name
        assert by_name[name]["reason_code"] == "no_price_bar_at_or_before_known_at_in_any_rung"
    assert by_name["budget_theme_relevance"]["status"] == "abstained"
    assert by_name["filings_corroboration"]["status"] == "abstained"


def test_stale_price_window_is_reported_stale_with_its_age(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_ohlcv(data_root, "NOC", end="2026-06-01")

    legs = mctx.market_context_legs(
        "NOC", "2026-08-06T12:00:00+00:00", repo_root=tmp_path, data_root=data_root
    )
    trend = next(leg for leg in legs if leg["name"] == "technical_trend")

    assert trend["status"] == "stale"
    assert trend["freshness"]["age_days"] > mctx.PRICE_SLA_DAYS
    assert trend["freshness"]["sla_days"] == mctx.PRICE_SLA_DAYS


def test_a_bar_after_known_at_is_abstained_not_used(tmp_path: Path) -> None:
    """A future-dated source is a leak; the leg refuses it by name."""
    naive = pd.Timestamp("2026-08-06")
    status, freshness = mctx._freshness(pd.Timestamp("2026-08-10"), naive, sla_days=7.0)

    assert status == "abstained"
    assert freshness["status"] == "future_source"


def test_percentile_readings_are_own_history_ranks_not_absolutes(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_ohlcv(data_root, "NOC", end="2026-08-07", days=600)

    legs = mctx.market_context_legs(
        "NOC", "2026-08-06T12:00:00+00:00", repo_root=tmp_path, data_root=data_root
    )
    runup = next(leg for leg in legs if leg["name"] == "runup_extension")
    readings = {row["name"]: row for row in runup["readings"]}

    for name in (
        "runup_21d_own_history_percentile",
        "runup_63d_own_history_percentile",
        "extension_vs_50dma_own_history_percentile",
    ):
        assert readings[name]["kind"] == "percentile", name
        assert readings[name]["units"] == "fraction", name
        value = readings[name]["value"]
        assert value is None or 0.0 <= value <= 1.0, name


def test_close_only_rung_abstains_from_atr_by_name(tmp_path: Path) -> None:
    """No high/low means no ATR — reported as a named gap, never as ATR zero."""
    data_root = tmp_path / "data"
    index = pd.bdate_range(end=pd.Timestamp("2026-08-07"), periods=300)
    frame = pd.DataFrame({
        "close": pd.Series([100.0 + i * 0.2 for i in range(300)], index=index),
        "volume": pd.Series([900_000.0] * 300, index=index),
    })
    frame.index.name = "Date"
    path = data_root / "stocks" / "NOC.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)

    window = mctx.load_pit_window("NOC", "2026-08-06T12:00:00+00:00", data_root=data_root)
    assert window is not None and window.coverage == "close_volume"

    leg = mctx.volatility_liquidity_leg(window)
    readings = {row["name"]: row["value"] for row in leg["readings"]}
    assert leg["reason_code"] == "atr_requires_high_low_absent_from_answering_price_rung"
    assert readings["atr_14"] is None
    assert readings["realized_vol_20d"] is not None


def test_relative_strength_abstains_without_a_benchmark(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _write_ohlcv(data_root, "NOC", end="2026-08-07")

    window = mctx.load_pit_window("NOC", "2026-08-06T12:00:00+00:00", data_root=data_root)
    assert window is not None and window.bench_close is None

    leg = mctx.relative_strength_leg(window)
    assert leg["status"] == "abstained"
    assert leg["reason_code"] == "benchmark_series_unavailable_at_known_at"
    assert leg["readings"] == []


def test_injected_reader_row_without_a_source_clock_abstains(tmp_path: Path) -> None:
    """The time-consciousness law is enforced on injected legs too."""
    clockless = mctx.filings_corroboration_leg(
        "NOC",
        "2026-08-06T12:00:00+00:00",
        filings_reader=lambda _t, _k: {"readings": [{"name": "backlog_mentioned", "value": True}]},
    )
    clocked = mctx.filings_corroboration_leg(
        "NOC",
        "2026-08-06T12:00:00+00:00",
        filings_reader=lambda _t, _k: {
            "source_time": "2026-08-04T00:00:00Z",
            "lobe": "filings",
            "readings": [{"name": "backlog_mentioned", "value": True, "kind": "state"}],
        },
    )

    assert clockless["status"] == "abstained"
    assert clockless["reason_code"] == "reader_row_carries_no_source_clock"
    assert clocked["status"] == "present"
    assert clocked["readings"][0]["name"] == "backlog_mentioned"


def test_a_failing_injected_reader_is_a_missing_leg_not_an_exception(tmp_path: Path) -> None:
    def _boom(_ticker, _known_at):
        raise RuntimeError("upstream down")

    leg = mctx.budget_theme_leg("NOC", "2026-08-06T12:00:00+00:00", theme_reader=_boom)

    assert leg["status"] == "missing"
    assert leg["reason_code"] == "budget_theme_reader_failed"


# --------------------------------------------------------------------------- #
# the reuse pin — one price basis, and it is Prophet's
# --------------------------------------------------------------------------- #


def test_price_basis_is_the_same_basis_prophet_reads() -> None:
    """The shadow legs and Prophet must price a name identically.

    ``market_context`` reads the rungs itself only because the public loader
    drops high/low.  This pins the two to ONE basis: if the ladder or its
    preference order ever moves, the two close series diverge and this fails.
    Live probe against the committed store, not a fixture.
    """
    from engine.prophet_stage_inputs import load_ticker_prices

    data_root = ROOT / "data"
    prophet_close, _volume = load_ticker_prices("NOC", data_root)
    if prophet_close is None:  # pragma: no cover - store absent in a thin checkout
        pytest.skip("no committed NOC price rung in this checkout")

    cutoff = pd.Timestamp(prophet_close.index[-1])
    window = mctx.load_pit_window("NOC", cutoff.isoformat(), data_root=data_root)

    assert window is not None
    assert window.rung == mctx.PRICE_RUNGS[0]
    expected = prophet_close.loc[prophet_close.index <= cutoff]
    pd.testing.assert_series_equal(
        window.close.astype(float), expected.astype(float), check_names=False
    )


def test_live_probe_builds_a_real_packet_from_committed_stores() -> None:
    """One end-to-end read of the committed stores, not a green fixture suite.

    A fixture cannot catch a schema drift in the regime store or Prophet's
    published candidates; this can. Legs are allowed to be missing here — what is
    asserted is that a real read produces a contract-valid packet.
    """
    candidate = _candidate()
    packet = sc.build_shadow_packet(candidate, repo_root=ROOT)

    assert packet["ticker"] == candidate["ticker"]
    assert len(packet["legs"]) == 11
    sc.assert_no_fused_score(packet)
    envelope = sc.build_shadow_context(
        [candidate], repo_root=ROOT, generated_at=GENERATED_AT
    )
    _validator().validate(envelope)
