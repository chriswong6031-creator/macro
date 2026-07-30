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
                "date": "2026-07-28",
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
