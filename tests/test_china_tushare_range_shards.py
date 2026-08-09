from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from collectors import china_tushare_range_shards as shards


FIELDS = ("ts_code", "trade_date", "close")
SESSIONS = ("2024-01-02", "2024-01-03", "2024-01-04")


def _plan(
    store: Path,
    *,
    cap: int = 10,
    identities: tuple[dict[str, str], ...] | None = None,
) -> dict:
    return shards.ensure_campaign(
        store,
        endpoint="daily",
        fields=FIELDS,
        source_row_cap=cap,
        sessions=SESSIONS,
        query_identities=identities or ({
            "canonical_ticker": "600519.SS",
            "source_ts_code": "600519.SH",
            "alias_kind": "canonical",
        },),
        reference_generation_id="ref-synthetic",
        reference_generation_semantic_sha256="a" * 64,
        universe_witness_sha256="b" * 64,
    )


def _frame(leaf: shards.RangeLeaf, *, close: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame([
        {"ts_code": leaf.source_ts_code, "trade_date": day.replace("-", ""), "close": close}
        for day in SESSIONS
        if leaf.start_date <= day <= leaf.end_date
    ], columns=FIELDS)


def _complete(store: Path, plan: dict) -> shards.CampaignVerification:
    for leaf in shards.planned_leaves(plan):
        shards.record_attempt(
            store, plan, leaf, frame=_frame(leaf), observed_at="2026-08-09T12:00:00+00:00",
        )
    return shards.finalize_campaign(store, plan)


def test_campaign_transposes_and_zero_call_resume(tmp_path):
    plan = _plan(tmp_path)
    leaves = shards.pending_leaves(tmp_path, plan)
    assert len(leaves) == 1
    verification = _complete(tmp_path, plan)
    assert verification.complete is True
    assert len(verification.resolved_frame) == 3
    assert shards.pending_leaves(tmp_path, plan) == []
    resumed = shards.verify_campaign(tmp_path, plan["campaign_id"])
    assert resumed.day_receipts["2024-01-03"]["authoritative_row_count"] == 1


def test_cap_minus_one_split_is_deterministic_and_bounded(tmp_path):
    plan = _plan(tmp_path, cap=3)
    leaves = shards.planned_leaves(plan)
    assert [(leaf.start_date, leaf.end_date, leaf.session_count) for leaf in leaves] == [
        ("2024-01-02", "2024-01-03", 2),
        ("2024-01-04", "2024-01-04", 1),
    ]
    assert [leaf.leaf_id for leaf in shards.planned_leaves(shards.load_plan(
        tmp_path, plan["campaign_id"],
    ))] == [leaf.leaf_id for leaf in leaves]


def test_retry_attempt_receipts_are_immutable_and_unattempted_precedes_retry(tmp_path):
    plan = _plan(tmp_path, cap=3)
    first, second = shards.planned_leaves(plan)
    shards.record_attempt(
        tmp_path, plan, first, frame=None, observed_at="2026-08-09T12:00:00+00:00",
    )
    # The untouched second range comes before the retryable first range.
    assert shards.pending_leaves(tmp_path, plan) == [second, first]
    shards.record_attempt(
        tmp_path, plan, first, frame=_frame(first), observed_at="2026-08-09T12:01:00+00:00",
    )
    receipt_files = sorted((tmp_path / "receipts" / "requests" / "daily" / first.unit).glob("*.json"))
    assert len(receipt_files) == 2
    assert json.loads(receipt_files[0].read_text())["response_status"] == "unavailable"
    assert json.loads(receipt_files[1].read_text())["response_status"] == "accepted"
    progress = shards.campaign_progress(tmp_path, plan)
    assert progress["physical_attempt_count"] == 2
    assert progress["retry_attempt_count"] == 1
    assert progress["completed_leaf_count"] == 1
    assert progress["unattempted_leaf_count"] == 1


@pytest.mark.parametrize("mutation", ["ticker", "date", "columns", "duplicate"])
def test_response_binding_rejects_cross_unit_or_malformed_rows(tmp_path, mutation):
    plan = _plan(tmp_path)
    leaf = shards.planned_leaves(plan)[0]
    frame = _frame(leaf)
    if mutation == "ticker":
        frame.loc[0, "ts_code"] = "000001.SZ"
    elif mutation == "date":
        frame.loc[0, "trade_date"] = "20240106"
    elif mutation == "columns":
        frame = frame[["trade_date", "ts_code", "close"]]
    else:
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(shards.RangeShardError):
        shards.record_attempt(
            tmp_path, plan, leaf, frame=frame, observed_at="2026-08-09T12:00:00+00:00",
        )
    attempt_files = list((tmp_path / "receipts" / "requests" / "daily" / leaf.unit).glob("*.json"))
    assert len(attempt_files) == 1
    assert json.loads(attempt_files[0].read_text())["response_status"] == "rejected_contract"


def test_tampered_leaf_artifact_reopens_campaign(tmp_path):
    plan = _plan(tmp_path)
    _complete(tmp_path, plan)
    leaf = shards.planned_leaves(plan)[0]
    artifact = next((tmp_path / "source_range_shards" / "daily" / plan["campaign_id"]).rglob(
        f"{leaf.leaf_id}.parquet"
    ))
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(shards.RangeShardError, match="modified"):
        shards.verify_campaign(tmp_path, plan["campaign_id"])


def test_terminal_receipt_binds_complete_attempt_ledger(tmp_path):
    plan = _plan(tmp_path)
    leaf = shards.planned_leaves(plan)[0]
    shards.record_attempt(
        tmp_path, plan, leaf, frame=None, observed_at="2026-08-09T12:00:00+00:00",
    )
    shards.record_attempt(
        tmp_path, plan, leaf, frame=_frame(leaf),
        observed_at="2026-08-09T12:01:00+00:00",
    )
    shards.finalize_campaign(tmp_path, plan)
    state_path = next((tmp_path / "range_campaigns" / plan["campaign_id"] / "leaves").rglob(
        f"{leaf.leaf_id}.json"
    ))
    state = json.loads(state_path.read_text())
    state["attempts"] = state["attempts"][1:]
    state["attempts"][0]["attempt_number"] = 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(shards.RangeShardError, match="canonical|directory|ordinal"):
        shards.verify_campaign(tmp_path, plan["campaign_id"])


def test_bse_old_and_new_aliases_deduplicate_equal_rows(tmp_path):
    identities = (
        {"canonical_ticker": "920163.BJ", "source_ts_code": "920163.BJ", "alias_kind": "canonical"},
        {"canonical_ticker": "920163.BJ", "source_ts_code": "838163.BJ", "alias_kind": "bse_old_code"},
    )
    plan = _plan(tmp_path, identities=identities)
    for leaf in shards.planned_leaves(plan):
        shards.record_attempt(
            tmp_path, plan, leaf, frame=_frame(leaf),
            observed_at=f"2026-08-09T12:00:0{len(leaf.source_ts_code)}+00:00",
        )
    verification = shards.finalize_campaign(tmp_path, plan)
    assert verification.complete is True
    assert len(verification.resolved_frame) == 3
    assert len(verification.duplicate_alias_rows) == 3
    assert verification.receipt["source_accounting_complete"] is True


def test_bse_alias_conflict_is_retained_and_blocks(tmp_path):
    identities = (
        {"canonical_ticker": "920163.BJ", "source_ts_code": "920163.BJ", "alias_kind": "canonical"},
        {"canonical_ticker": "920163.BJ", "source_ts_code": "838163.BJ", "alias_kind": "bse_old_code"},
    )
    plan = _plan(tmp_path, identities=identities)
    for leaf in shards.planned_leaves(plan):
        close = 11.0 if leaf.alias_kind == "bse_old_code" else 10.0
        shards.record_attempt(
            tmp_path, plan, leaf, frame=_frame(leaf, close=close),
            observed_at=f"2026-08-09T12:00:0{len(leaf.source_ts_code)}+00:00",
        )
    verification = shards.finalize_campaign(tmp_path, plan)
    assert verification.complete is False
    assert verification.receipt["status"] == "alias_conflict"
    assert len(verification.conflicting_alias_rows) == 6
    conflict_path = tmp_path / "range_campaigns" / plan["campaign_id"] / "alias_conflicts.parquet"
    assert conflict_path.exists()
    conflict_path.write_bytes(conflict_path.read_bytes() + b"tampered")
    with pytest.raises(shards.RangeShardError, match="conflict.artifact"):
        shards.verify_campaign(tmp_path, plan["campaign_id"])


def test_plan_tamper_fails_hash_binding(tmp_path):
    plan = _plan(tmp_path)
    path = tmp_path / "range_campaigns" / plan["campaign_id"] / "plan.json"
    payload = json.loads(path.read_text())
    payload["source_row_cap"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(shards.RangeShardError, match="hash"):
        shards.load_plan(tmp_path, plan["campaign_id"])
