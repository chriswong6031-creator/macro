"""Point-in-time integrity tests for the China Prophet full-universe shadow log."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import china_prophet_shadow as shadow
from lib import config


@pytest.fixture
def shadow_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        shadow.china_standout_track,
        "session_status",
        lambda asof: {"partial_session": False, "reason": "settled"},
    )
    return tmp_path


def _candidate(
    ticker: str,
    *,
    eligible: bool = True,
    tier: str | None = "T2",
    score: float = 70.0,
    definition: str = "cn_prophet_v2",
) -> dict:
    values = {
        "signal": 1.0,
        "entry": 0.9,
        "runway": 0.6,
        "bottom_quality": 0.8,
        "reversal_member": 1.0,
    }
    points = {
        "signal": 35.0,
        "entry": 22.5,
        "runway": 12.0,
        "bottom_quality": 8.0,
        "reversal_member": 10.0,
    }
    return {
        "ticker": ticker,
        "name": f"Name {ticker}",
        "sector": "Industrials",
        "board_definition": definition,
        "prophet_score": score,
        "score_rank": 1,
        "prophet": {
            "version": definition,
            "score": score,
            "components": values,
            "points": points,
        },
        "signal": {
            "eligible": eligible,
            "tier_cascade": tier,
            "reason": "test gate",
            "ticks": 1,
            "provisional": False,
            "asof": "2026-07-29",
            "input_asof": "2026-07-29",
        },
        "entry_signal": {
            "status": "buy_now",
            "urgency": "now",
            "entry_z": 1.2,
            "buy_zone": {"low": 9.8, "high": 10.2},
        },
        "extension": {"extended": False, "score": 0.1},
        "microstructure": {
            "as_of": "2026-07-29",
            "fillable": True,
            "chase_veto": {"flag": False},
        },
        "_micro_asof": "2026-07-29",
        "_board_asof": "2026-07-29",
        "liquidity": {"adv_yi": 1.25},
        "stage": "ENTRY",
        "price": 10.0,
        "alpha": -0.2,
        "setup": 0.7,
        "rev_z": 1.5,
        "rev_percentile": 0.9,
        "reversal_member": True,
        "conviction": {
            "score": 65,
            "potential": {
                "score": 65,
                "tier": "setting_up",
                "components": {"fuel": 0.6},
            },
        },
        "risk_sizing": {"size_mult": 0.8, "vol_ann_pct": 28.0},
    }


def _lane_doc(rows_by_lane):
    return {
        lane: [
            {
                **row,
                "display_rank": index,
                "lane_reasons": [f"{lane}_reason"],
            }
            for index, row in enumerate(rows, start=1)
        ]
        for lane, rows in rows_by_lane.items()
    }


def test_appends_full_universe_with_exact_lanes_and_components(shadow_store):
    featured = _candidate("600001.SS")
    more = _candidate("600002.SS")
    late = _candidate("600003.SS")
    forming = _candidate("600004.SS", tier="T4")
    rejected = _candidate("600005.SS", eligible=False, tier=None)
    rows = [featured, more, late, forming, rejected]
    lanes = _lane_doc(
        {
            "featured": [featured],
            "more_actionable": [more],
            "late_or_unfillable": [late],
            "forming": [forming],
        }
    )

    assert shadow.append_candidates(
        rows,
        "2026-07-29",
        lane="asia",
        board_lanes=lanes,
    ) == 5

    stored = pd.read_parquet(shadow._store_path()).set_index("ticker")
    assert stored["lane"].to_dict() == {
        "600001.SS": "featured",
        "600002.SS": "more_actionable",
        "600003.SS": "late_or_unfillable",
        "600004.SS": "forming",
        "600005.SS": "not_raw_eligible",
    }
    top = stored.loc["600001.SS"]
    assert top["board_definition"] == "cn_prophet_v2"
    assert top["prophet_signal"] == pytest.approx(1.0)
    assert top["prophet_signal_points"] == pytest.approx(35.0)
    assert top["prophet_entry"] == pytest.approx(0.9)
    assert top["raw_eligible"] and top["buyable"]
    assert top["entry_status"] == "buy_now"
    assert top["micro_fillable"] and not top["micro_chase_veto"]
    assert top["execution_clear"]
    assert top["level"] == pytest.approx(10.0)
    assert top["lane_reasons"] == "featured_reason"


def test_challenger_receipts_keep_actual_fields_and_unknowns(shadow_store):
    observed = _candidate("600006.SS")
    observed.update(
        ret_3m=-18.5,
        sector_turn={
            "state": "bottoming",
            "osc_slope": 0.42,
            "signature": -0.17,
            "asof": "2026-07-29",
            "approx": True,
        },
        coiled={
            "coiled": False,
            "star": False,
            "washout_ctx": False,
            "cohort": None,
        },
        washout_2w=False,
    )
    missing = _candidate("600007.SS")

    assert shadow.append_candidates(
        [observed, missing],
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"featured": [observed, missing]}),
    ) == 2

    stored = pd.read_parquet(shadow._store_path()).set_index("ticker")
    receipt = stored.loc["600006.SS"]
    assert receipt["ret_3m"] == pytest.approx(-18.5)
    assert receipt["sector_turn_state"] == "bottoming"
    assert receipt["sector_turn_osc_slope"] == pytest.approx(0.42)
    assert receipt["sector_turn_signature"] == pytest.approx(-0.17)
    assert receipt["sector_turn_asof"] == "2026-07-29"
    assert bool(receipt["sector_turn_approx"]) is True
    assert bool(receipt["coiled"]) is False
    assert bool(receipt["coiled_star"]) is False
    assert bool(receipt["washout_2w"]) is False

    unknown = stored.loc["600007.SS"]
    assert pd.isna(unknown["coiled"])
    assert pd.isna(unknown["coiled_star"])
    assert pd.isna(unknown["washout_2w"])


def test_only_asia_and_settled_session_can_persist(shadow_store, monkeypatch):
    row = _candidate("600010.SS")
    lanes = _lane_doc({"featured": [row]})

    assert shadow.append_candidates(
        [row], "2026-07-29", lane="render", board_lanes=lanes
    ) == 0
    assert not shadow._store_path().exists()

    monkeypatch.setattr(
        shadow.china_standout_track,
        "session_status",
        lambda asof: {"partial_session": True, "reason": "mid-session partial"},
    )
    assert shadow.append_candidates(
        [row], "2026-07-29", lane="asia", board_lanes=lanes
    ) == 0
    assert not shadow._store_path().exists()


def test_keep_first_is_definition_scoped(shadow_store):
    first = _candidate("600020.SS", score=88.0)
    lanes = _lane_doc({"featured": [first]})
    assert shadow.append_candidates(
        [first], "2026-07-29", lane="asia", board_lanes=lanes
    ) == 1

    rerun = _candidate("600020.SS", score=1.0)
    assert shadow.append_candidates(
        [rerun],
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"late_or_unfillable": [rerun]}),
    ) == 1

    challenger = _candidate(
        "600020.SS",
        score=55.0,
        definition="cn_prophet_v3_challenger",
    )
    assert shadow.append_candidates(
        [challenger],
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"more_actionable": [challenger]}),
    ) == 2

    stored = pd.read_parquet(shadow._store_path())
    v2 = stored[stored["board_definition"] == "cn_prophet_v2"].iloc[0]
    assert v2["prophet_score"] == pytest.approx(88.0)
    assert v2["lane"] == "featured"
    assert set(stored["board_definition"]) == {
        "cn_prophet_v2",
        "cn_prophet_v3_challenger",
    }


def test_schema_union_preserves_legacy_columns(shadow_store):
    path = shadow._store_path()
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "stamp_date": "2026-07-28",
                "ticker": "600030.SS",
                "board_definition": "cn_prophet_v1",
                "legacy_only": "keep-me",
            }
        ]
    ).to_parquet(path, index=False)

    row = _candidate("600031.SS")
    assert shadow.append_candidates(
        [row],
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"featured": [row]}),
    ) == 2

    stored = pd.read_parquet(path).set_index("ticker")
    assert stored.loc["600030.SS", "legacy_only"] == "keep-me"
    assert pd.isna(stored.loc["600030.SS", "prophet_score"])
    assert stored.loc["600031.SS", "lane"] == "featured"


def test_raw_eligible_without_exact_board_lane_is_refused(shadow_store):
    row = _candidate("600040.SS")
    assert shadow.append_candidates(
        [row],
        "2026-07-29",
        lane="asia",
    ) == 0
    assert not shadow._store_path().exists()


def test_research_rank_payload_shape_is_supported(shadow_store):
    row = _candidate("600050.SS")
    compact = row.pop("prophet")
    row.pop("prophet_score")
    row.pop("board_definition")
    row["prophet_rank"] = {
        "definition": "cn_prophet_v2",
        "score": compact["score"],
        "components": {
            name: {
                "value": value,
                "points": compact["points"][name],
            }
            for name, value in compact["components"].items()
        },
    }

    assert shadow.append_candidates(
        [row],
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"featured": [row]}),
    ) == 1
    stored = pd.read_parquet(shadow._store_path()).iloc[0]
    assert stored["board_definition"] == "cn_prophet_v2"
    assert stored["prophet_score"] == pytest.approx(70.0)
    assert stored["prophet_runway"] == pytest.approx(0.6)
    assert stored["prophet_runway_points"] == pytest.approx(12.0)


def test_micro_fresh_uses_exact_packet_date_not_batch_date(shadow_store):
    repaired = _candidate("600060.SS")
    repaired["_micro_asof"] = "2026-07-28"
    undated = _candidate("600061.SS")
    undated["microstructure"].pop("as_of")
    rows = [repaired, undated]

    assert shadow.append_candidates(
        rows,
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({
            "featured": [repaired],
            "more_actionable": [undated],
        }),
    ) == 2

    stored = pd.read_parquet(shadow._store_path()).set_index("ticker")
    assert bool(stored.loc["600060.SS", "micro_fresh"]) is True
    assert bool(stored.loc["600060.SS", "execution_clear"]) is True
    assert stored.loc["600060.SS", "micro_asof"] == "2026-07-29"
    assert stored.loc["600060.SS", "micro_batch_asof"] == "2026-07-28"
    assert bool(stored.loc["600061.SS", "micro_fresh"]) is False
    assert bool(stored.loc["600061.SS", "execution_clear"]) is False
    assert pd.isna(stored.loc["600061.SS", "micro_asof"])
    assert stored.loc["600061.SS", "micro_batch_asof"] == "2026-07-29"


def test_production_compact_signal_keeps_private_research_receipt(shadow_store):
    source = _candidate("600070.SS")
    verdict = {
        "eligible": True,
        "tier_cascade": "T2",
        "tier_sub": "fresh_cross",
        "reason": "full production reason",
        "state": "turning",
        "ticks": 1,
        "bars_to_cross": 0,
        "weight": 0.75,
        "provisional": False,
        "asof": "2026-07-28",
        "input_asof": "2026-07-29",
    }
    scored = shadow.china_board_rank.enrich_and_score_rows(
        [source],
        verdict_by={"600070.SS": verdict},
        profile_by={"600070.SS": source["conviction"]},
        entry_by={"600070.SS": source["entry_signal"]},
        micro_by={"600070.SS": source["microstructure"]},
        liquidity_by={"600070.SS": source["liquidity"]},
        board_asof="2026-07-29",
    )
    lanes = shadow.china_board_rank.partition_board_rows(scored)
    assert "_signal_research" in scored[0]
    assert all(
        "_signal_research" not in row
        for lane in shadow.BOARD_LANES
        for row in lanes[lane]
    )

    assert shadow.append_candidates(
        scored,
        "2026-07-29",
        lane="asia",
        board_lanes=lanes,
    ) == 1
    stored = pd.read_parquet(shadow._store_path()).iloc[0]
    assert stored["gate_reason"] == "full production reason"
    assert stored["gate_state"] == "turning"
    assert stored["gate_weight"] == pytest.approx(0.75)
    assert stored["signal_asof"] == "2026-07-29"
    assert stored["signal_bar_asof"] == "2026-07-28"
    # a verdict with nothing extra to say still fills gate_reasons — the column is never
    # emptier than its first-match sibling, so a reader may always split on "|".
    assert stored["gate_reasons"] == "full production reason"


def test_gate_reasons_records_every_blocking_leg_not_just_the_first(shadow_store):
    """The 002155.SZ defect, pinned at the PIT store.

    ``gate_reason`` is a FIRST-MATCH label: ``_buy_filter`` returns on the bearish-divergence
    veto before reclaim-and-hold is ever tested, so 湖南黄金 stamped ``veto: bearish divergence``
    on every board date while ALSO failing the hold — and 575 of 743 vetoed fires (77%) were
    blocked by another leg anyway (research/cn_prophet_audit/CN_DIVERGENCE_VETO_AUDIT.md).
    The store must record the whole account, or every consumer inherits the ambiguity."""
    blocked = "buy blocked by filter: veto: bearish divergence"
    also = "buy blocked by filter: failed next-bar hold"
    verdict = {
        "eligible": False,
        "tier_cascade": None,
        "reason": blocked,
        "reasons": [blocked, also],
        "state": "short-bias",
        "weight": 0.0,
        "provisional": False,
        "asof": "2026-08-03",
        "input_asof": "2026-08-03",
    }

    # 1. the private research receipt is an explicit key ALLOWLIST — a `reasons` missing from
    #    it degrades the store back to first-match silently, with every other test still green.
    carrier = _candidate("002155.SZ", eligible=False, tier=None)
    scored = shadow.china_board_rank.enrich_and_score_rows(
        [carrier],
        verdict_by={"002155.SZ": verdict},
        profile_by={"002155.SZ": carrier["conviction"]},
        entry_by={"002155.SZ": carrier["entry_signal"]},
        micro_by={"002155.SZ": carrier["microstructure"]},
        liquidity_by={"002155.SZ": carrier["liquidity"]},
        board_asof="2026-08-03",
    )
    assert scored[0]["_signal_research"]["reasons"] == [blocked, also]
    assert scored[0]["_signal_research"]["reason"] == blocked

    # 2. the store writes both columns. A blocked name holds no board lane, so it stamps
    #    not_raw_eligible — exactly where the full-universe log is supposed to keep it.
    row = _candidate("002155.SZ", eligible=False, tier=None)
    row["_signal_research"] = dict(verdict)
    assert shadow.append_candidates(
        [row], "2026-08-03", lane="asia", board_lanes=_lane_doc({}),
    ) == 1
    stored = pd.read_parquet(shadow._store_path()).iloc[0]
    assert stored["lane"] == "not_raw_eligible"
    assert stored["gate_reason"] == blocked, "the first-match label must not change"
    assert stored["gate_reasons"] == f"{blocked}|{also}"
    assert stored["gate_reasons"].split("|")[0] == stored["gate_reason"]


def test_missing_definition_is_refused_not_relabelled_v2(shadow_store):
    row = _candidate("600080.SS")
    row.pop("board_definition")
    row.pop("prophet")
    assert shadow.append_candidates(
        [row],
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"featured": [row]}),
    ) == 0
    assert not shadow._store_path().exists()


# ── PR-0B: full intel_interest anatomy persisted to the candidate plane ───────
#
# engine/china_intel_interest.py's interest_score() is the live cn_prophet_v4
# ordering authority. The candidate plane previously recorded none of its
# anatomy, so R4/L-track diagnosis of *why* the champion ordered a name the way
# it did was unrecoverable after the fact. These tests pin: (1) the full record
# — including the components china_board_rank._attach_intel does NOT hoist to
# its compact ``row["intel"]`` — round-trips through the store with correct
# null-safety for refused/absent names; (2) the persisted values are exactly
# what the board attached, proving the plane and the board share one computed
# record rather than re-scoring; (3) adding this persistence changes no
# ordering/board output; (4) appending against an old-schema fixture (no
# intel_* columns) still succeeds via the store's existing schema-union path.

def _measured_intel(
    score: float = 62.5,
    *,
    drivers: list[str] | None = None,
    falsifiers: list[str] | None = None,
) -> dict:
    return {
        "definition": "cn_intel_interest_v1",
        "basis": "measured",
        "score": score,
        "signal_core": 0.7,
        "signal_source": "altdata",
        "edge_remaining": 0.6,
        "edge_components": 2,
        "gap": 1,
        "lead_up": 1,
        "gap_mult": 1.05,
        "falsifier_penalty": 1.0 if not falsifiers else 0.85,
        "falsifiers": falsifiers or [],
        "drivers": drivers if drivers is not None else ["altdata convergence", "no board overhang"],
        "excludes": ["prophet_score", "prophet_rank", "hub_opportunity_score"],
    }


def _fallback_intel(reason: str = "no_desk_evidence") -> dict:
    return {
        "definition": "cn_intel_interest_v1",
        "basis": "fallback_v3",
        "score": None,
        "unavailable_reason": reason,
        "drivers": [],
        "excludes": ["prophet_score", "prophet_rank", "hub_opportunity_score"],
    }


def test_intel_anatomy_persists_with_null_safety_for_refused_names(shadow_store):
    measured = _candidate("600090.SS")
    fallback = _candidate("600091.SS")
    absent = _candidate("600092.SS")  # not present in intel_by at all
    rows = [measured, fallback, absent]
    intel_by = {
        "600090.SS": _measured_intel(),
        "600091.SS": _fallback_intel("no_edge_evidence"),
    }

    assert shadow.append_candidates(
        rows,
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"featured": rows}),
        intel_by=intel_by,
    ) == 3

    stored = pd.read_parquet(shadow._store_path()).set_index("ticker")

    m = stored.loc["600090.SS"]
    assert m["intel_score"] == pytest.approx(62.5)
    assert m["intel_basis"] == "measured"
    assert m["intel_definition"] == "cn_intel_interest_v1"
    assert m["intel_signal_core"] == pytest.approx(0.7)
    assert m["intel_signal_source"] == "altdata"
    assert m["intel_edge_remaining"] == pytest.approx(0.6)
    assert m["intel_edge_components"] == pytest.approx(2)
    assert m["intel_gap"] == pytest.approx(1)
    assert m["intel_lead_up"] == pytest.approx(1)
    assert m["intel_gap_mult"] == pytest.approx(1.05)
    assert m["intel_falsifier_penalty"] == pytest.approx(1.0)
    assert pd.isna(m["intel_falsifiers"]) or m["intel_falsifiers"] is None
    assert m["intel_drivers"] == "altdata convergence|no board overhang"
    assert m["intel_excludes"] == "prophet_score|prophet_rank|hub_opportunity_score"
    assert pd.isna(m["intel_unavailable_reason"]) or m["intel_unavailable_reason"] is None

    f = stored.loc["600091.SS"]
    assert pd.isna(f["intel_score"])
    assert f["intel_basis"] == "fallback_v3"
    assert f["intel_unavailable_reason"] == "no_edge_evidence"

    a = stored.loc["600092.SS"]
    assert pd.isna(a["intel_score"])
    assert pd.isna(a["intel_basis"]) or a["intel_basis"] is None
    assert a["intel_unavailable_reason"] == "no_intel_record"


def test_intel_falsifiers_pipe_joined_like_gate_reasons(shadow_store):
    row = _candidate("600093.SS")
    intel_by = {
        "600093.SS": _measured_intel(
            falsifiers=["price rolling over (20d drawdown + RS falling)", "weak altdata convergence"],
        ),
    }
    assert shadow.append_candidates(
        [row], "2026-07-29", lane="asia",
        board_lanes=_lane_doc({"featured": [row]}), intel_by=intel_by,
    ) == 1
    stored = pd.read_parquet(shadow._store_path()).iloc[0]
    assert stored["intel_falsifiers"] == (
        "price rolling over (20d drawdown + RS falling)|weak altdata convergence"
    )
    assert stored["intel_falsifier_penalty"] == pytest.approx(0.85)


def test_intel_plane_persists_the_same_record_the_board_attached(shadow_store):
    """Board-attach vs plane-persist must share values for the same input.

    ``intel_by`` is one map, computed once, fed to BOTH
    ``china_board_rank.enrich_and_score_rows`` (which stamps the compact,
    top-level ``intel_interest_score``/``intel_interest_basis`` the live board
    orders by) and ``shadow.append_candidates`` (which now persists the full
    anatomy). This structurally demonstrates the single-compute invariant: no
    second ``interest_score()`` evaluation happens for the plane write.
    """
    ticker = "600094.SS"
    source = _candidate(ticker)
    intel_by = {ticker: _measured_intel(score=41.75)}

    scored = shadow.china_board_rank.enrich_and_score_rows(
        [source],
        verdict_by={ticker: source["signal"]},
        profile_by={ticker: source["conviction"]},
        entry_by={ticker: source["entry_signal"]},
        micro_by={ticker: source["microstructure"]},
        liquidity_by={ticker: source["liquidity"]},
        board_asof="2026-07-29",
        intel_by=intel_by,
    )
    assert scored[0]["intel_interest_score"] == pytest.approx(41.75)
    assert scored[0]["intel_interest_basis"] == "measured"

    lanes = shadow.china_board_rank.partition_board_rows(scored)
    assert shadow.append_candidates(
        scored, "2026-07-29", lane="asia", board_lanes=lanes, intel_by=intel_by,
    ) == 1

    stored = pd.read_parquet(shadow._store_path()).iloc[0]
    assert stored["intel_score"] == pytest.approx(scored[0]["intel_interest_score"])
    assert stored["intel_basis"] == scored[0]["intel_interest_basis"]


def test_intel_persistence_leaves_ordering_and_board_output_untouched(shadow_store):
    """Adding intel_by persistence must not perturb enrich_and_score_rows' output.

    Snapshots the FULL scored-row population (order, scores, ranks, the compact
    board ``intel`` attach) before it is handed to the shadow writer, then
    re-snapshots after ``append_candidates`` runs (with and without intel_by).
    Byte-identical proves the new persistence path is read-only with respect to
    the board's own ranked output.
    """
    import copy
    import json

    rows = [_candidate(f"60010{i}.SS", score=float(90 - i)) for i in range(3)]
    intel_by = {r["ticker"]: _measured_intel(score=float(10 + i)) for i, r in enumerate(rows)}

    scored = shadow.china_board_rank.enrich_and_score_rows(
        [dict(r) for r in rows],
        verdict_by={r["ticker"]: r["signal"] for r in rows},
        profile_by={r["ticker"]: r["conviction"] for r in rows},
        entry_by={r["ticker"]: r["entry_signal"] for r in rows},
        micro_by={r["ticker"]: r["microstructure"] for r in rows},
        liquidity_by={r["ticker"]: r["liquidity"] for r in rows},
        board_asof="2026-07-29",
        intel_by=intel_by,
    )
    before = json.dumps(
        [{k: v for k, v in r.items() if not k.startswith("_")} for r in scored],
        sort_keys=True, default=str,
    )
    lanes = shadow.china_board_rank.partition_board_rows(copy.deepcopy(scored))

    assert shadow.append_candidates(
        scored, "2026-07-29", lane="asia", board_lanes=lanes,
    ) == 3
    after_no_intel = json.dumps(
        [{k: v for k, v in r.items() if not k.startswith("_")} for r in scored],
        sort_keys=True, default=str,
    )
    assert after_no_intel == before

    assert shadow.append_candidates(
        scored, "2026-07-30", lane="asia", board_lanes=lanes, intel_by=intel_by,
    ) == 6
    after_with_intel = json.dumps(
        [{k: v for k, v in r.items() if not k.startswith("_")} for r in scored],
        sort_keys=True, default=str,
    )
    assert after_with_intel == before


def test_intel_columns_append_onto_a_pre_pr0b_fixture_parquet(shadow_store):
    """Schema-union: an existing store without any intel_* columns must accept
    a new append that carries them, per the store's existing keep-both-columns
    contract (see test_schema_union_preserves_legacy_columns)."""
    path = shadow._store_path()
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "stamp_date": "2026-07-28",
                "ticker": "600095.SS",
                "board_definition": "cn_prophet_v2",
                "prophet_score": 50.0,
            }
        ]
    ).to_parquet(path, index=False)

    row = _candidate("600096.SS")
    intel_by = {"600096.SS": _measured_intel(score=77.0)}
    assert shadow.append_candidates(
        [row],
        "2026-07-29",
        lane="asia",
        board_lanes=_lane_doc({"featured": [row]}),
        intel_by=intel_by,
    ) == 2

    stored = pd.read_parquet(path).set_index("ticker")
    assert "intel_score" in stored.columns
    old = stored.loc["600095.SS"]
    assert pd.isna(old["intel_score"])
    assert pd.isna(old["intel_basis"]) or old["intel_basis"] is None
    new = stored.loc["600096.SS"]
    assert new["intel_score"] == pytest.approx(77.0)
    assert new["intel_basis"] == "measured"
