"""Contract tests for the private R6.2-A operator Issue Desk."""
from __future__ import annotations

import json
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from engine import options_issue_desk as desk
from scripts.build_options_issue_desk import build as build_private_projection

NOW = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)  # Monday, 11:00 ET
REVIEWER = "supabase-user-123"


def _repo(tmp_path: Path, n: int = 1) -> Path:
    root = tmp_path / "repo"
    (root / "site/prophet").mkdir(parents=True)
    (root / "site/options_prophet").mkdir(parents=True)
    (root / "site/vol").mkdir(parents=True)
    plans = [
        {
            "id": f"TEST{i}-BULL-20260810", "asset": f"TEST{i}", "direction": "BULL",
            "closed": False, "entry": 100.0, "trigger": 101.0,
            "invalidation": 90.0, "targets": [120.0, 140.0], "option_contract": None,
        }
        for i in range(n)
    ]
    (root / "site/prophet/index.json").write_text(json.dumps({
        "schema": "prophet.index/v1", "asof": "2026-08-10", "recorded_at": "2026-08-10T14:00:00Z", "plans": plans,
    }))
    (root / "site/options_prophet/index.json").write_text(json.dumps({
        "schema": "options.prophet_shadow/v1", "authority": "display_only", "as_of": "2026-08-10",
    }))
    (root / "site/vol/regime.json").write_text(json.dumps({"schema": "options.vol_regime/v1", "as_of": "2026-08-10"}))
    return root


def _receipt(*, symbol: str = "TEST0", sleeve: str = "core", cluster: str = "cluster_a", allocation: float = 0.02, cash_after: float | None = None) -> dict:
    return {
        "schema": "options.issue_receipt/v1",
        "underlying": {
            "reference": 100.0, "trigger": 101.0, "no_chase": 105.0, "stop": 90.0,
            "t1": 120.0, "t2": 140.0, "t1_fraction": 0.5, "t2_fraction": 0.5,
            "minimum_hold_days": 10, "horizon_days": 30, "starter_allowed": False,
            "add_rule": "no additions in v1", "invalidation": 90.0,
        },
        "option": {
            "occ_symbol": f"{symbol}260918C00200000", "right": "C", "strike": 200.0,
            "expiry": "2026-09-18", "quantity": 1, "premium": 5.1,
            "nbbo_bid": 5.0, "nbbo_ask": 5.2, "nbbo_mid": 5.1,
            "quote_at": "2026-08-10T14:55:00Z", "quote_source": "operator_attested_nbbo/v1",
            "receipt_sha256": "a" * 64, "spread": 0.2, "spread_pct": 0.2 / 5.1,
        },
        "risk": {
            "allocation_weight": allocation,
            "loss_at_stop_weight": allocation / 2,
            "cash_after_weight": 1 - allocation if cash_after is None else cash_after,
            "disclosure": "Research plan only; no brokerage order or fill is created.",
        },
        "portfolio_fit": {
            "regime_alignment": "ALIGNED", "sleeve": sleeve,
            "correlation_cluster": cluster, "cooldown_clear": True, "event_risk_clear": True,
        },
    }


def _proposals(repo: Path, state: Path) -> list[dict]:
    desk.snapshot_current_proposals(repo=repo, reviewer=REVIEWER, root=state, now=NOW)
    return desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)["proposals"]


def _contract_validator(name: str) -> Draft202012Validator:
    contract_root = Path(__file__).resolve().parents[1] / "contracts" / "options"
    names = (
        "options.issue_receipt.v1.schema.json",
        "options.issue_desk_proposal.v1.schema.json",
        "options.issue_desk_decision.v1.schema.json",
        "options.issue_desk.v1.schema.json",
    )
    registry = Registry()
    schemas: dict[str, dict] = {}
    for filename in names:
        schema = json.loads((contract_root / filename).read_text())
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        schemas[filename] = schema
    return Draft202012Validator(schemas[name], registry=registry, format_checker=FormatChecker())


def test_registered_private_runtime_path_is_gitignored() -> None:
    root = Path(__file__).resolve().parents[1]
    candidate = "runtime-private/options_issue_desk/proposals.jsonl"
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", candidate],
        cwd=root,
        check=False,
    )
    assert result.returncode == 0, f"private Issue Desk ledger is stageable: {candidate}"


def test_snapshot_is_idempotent_and_freezes_display_context(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    (repo / "site/options_prophet/index.json").write_text(json.dumps({
        "schema": "options.prophet_shadow/v1", "authority": "display_only",
        "available_at": "2026-08-10T14:05:00Z",
        "watchlist": [{"symbol": "TEST0", "available_at": "2026-08-10T14:00:00Z",
                       "source_signing_reliable": False, "direction_reliable": False,
                       "observations": {"flow_z": -3.5, "net_prem_norm_abs": 1.2}}],
    }))
    first = desk.snapshot_current_proposals(repo=repo, reviewer=REVIEWER, root=state, now=NOW)
    second = desk.snapshot_current_proposals(repo=repo, reviewer=REVIEWER, root=state, now=NOW)
    payload = desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)
    assert first["created"] == 1
    assert second["created"] == 0
    proposal = payload["proposals"][0]
    assert proposal["state"] == "PENDING_REVIEW"
    assert proposal["source"]["sha256"]
    assert proposal["authority"] == desk.AUTHORITY
    assert payload["authority"] == desk.AUTHORITY
    assert payload["available_at"] >= proposal["available_at"]
    assert payload["provenance"]["public_r2_mirror"] is False
    shadow = next(item for item in proposal["context_receipts"] if item["kind"] == "options_shadow")
    assert shadow["evidence"]["source_signing_reliable"] is False
    assert shadow["evidence"]["direction_reliable"] is False
    assert shadow["evidence"]["observations"]["flow_magnitude"] == 3.5
    assert "flow_z" not in shadow["evidence"]["observations"]
    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert stat.S_IMODE((state / "proposals.jsonl").stat().st_mode) == 0o600
    assert stat.S_IMODE((state / ".lock").stat().st_mode) == 0o600


def test_approval_requires_complete_current_nbbo_receipt(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    proposal = _proposals(repo, state)[0]
    with pytest.raises(desk.IssueDeskError, match="issue_receipt"):
        desk.review(root=state, proposal_id=proposal["proposal_id"], proposal_revision=1,
                    action="approve", reason_codes=["EXECUTION_VERIFIED"],
                    idempotency_key="approve-without-receipt", issue_receipt=None, reviewer=REVIEWER, now=NOW)
    assert desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)["proposals"][0]["state"] == "PENDING_REVIEW"


def test_issue_is_append_only_idempotent_and_never_a_trade(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    proposal = _proposals(repo, state)[0]
    args = {
        "root": state, "proposal_id": proposal["proposal_id"], "proposal_revision": 1,
        "action": "approve", "reason_codes": ["EXECUTION_VERIFIED"],
        "idempotency_key": "approve-complete-receipt",
        "issue_receipt": _receipt(symbol=proposal["macro_candidate"]["asset"]),
        "reviewer": REVIEWER, "now": NOW,
    }
    first = desk.review(**args)
    second = desk.review(**args)
    payload = desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)
    assert first["state"] == "ISSUED"
    assert second["idempotent"] is True
    assert len(payload["decisions"]) == 1
    position = payload["positions"][0]
    assert position["proposal_id"] == proposal["proposal_id"]
    assert position["lifecycle_state"] == "ISSUED"
    assert position["brokerage_trade"] is False
    assert position["issue_receipt"] == _receipt(symbol=proposal["macro_candidate"]["asset"])
    assert position["events"][0]["event_type"] == "ISSUED"
    assert position["events"][0]["reason_codes"] == ["EXECUTION_VERIFIED"]
    assert position["authority"] == desk.AUTHORITY


def test_reject_is_terminal_and_capacity_counts_only_issues(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path, n=6), tmp_path / "state"
    proposals = _proposals(repo, state)
    reject = desk.review(root=state, proposal_id=proposals[0]["proposal_id"], proposal_revision=1,
                         action="reject", reason_codes=["ABSTAIN"],
                         idempotency_key="reject-first-proposal", issue_receipt=None, reviewer=REVIEWER, now=NOW)
    assert reject["capacity"]["issued_in_window"] == 0
    for index, proposal in enumerate(proposals[1:5], 1):
        desk.review(root=state, proposal_id=proposal["proposal_id"], proposal_revision=1,
                    action="approve", reason_codes=["EXECUTION_VERIFIED"],
                    idempotency_key=f"approve-issued-{index:02d}-receipt", issue_receipt=_receipt(symbol=proposal["macro_candidate"]["asset"], sleeve=f"sleeve_{index}", cluster=f"cluster_{index}", cash_after=1 - index * 0.02), reviewer=REVIEWER, now=NOW)
    with pytest.raises(desk.ConflictError, match="capacity"):
        desk.review(root=state, proposal_id=proposals[-1]["proposal_id"], proposal_revision=1,
                    action="approve", reason_codes=["EXECUTION_VERIFIED"],
                    idempotency_key="approve-capacity-five", issue_receipt=_receipt(symbol=proposals[-1]["macro_candidate"]["asset"]), reviewer=REVIEWER, now=NOW)


def test_lmt_transport_receipt_survives_issuance_byte_for_byte(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    artifact = repo / "site/prophet/index.json"
    source = json.loads(artifact.read_text())
    source["plans"][0]["asset"] = "LMT"
    artifact.write_text(json.dumps(source))
    proposal = _proposals(repo, state)[0]
    receipt = _receipt(symbol="LMT")
    receipt["underlying"].update({
        "reference": 582.74, "trigger": 595.0, "no_chase": 610.0,
        "stop": 525.0, "invalidation": 525.0, "t1": 700.0, "t2": 750.0,
        "minimum_hold_days": 30, "horizon_days": 60,
    })
    receipt["option"].update({
        "occ_symbol": "LMT260918C00600000", "right": "C", "strike": 600.0,
        "premium": 16.5, "nbbo_bid": 16.4, "nbbo_mid": 16.5, "nbbo_ask": 16.6,
        "spread": 0.2, "spread_pct": 0.2 / 16.5,
    })
    result = desk.review(root=state, reviewer=REVIEWER, proposal_id=proposal["proposal_id"], proposal_revision=1,
                         action="approve", reason_codes=["PORTFOLIO_FIT", "REGIME_ALIGNED", "EXECUTION_VERIFIED"],
                         idempotency_key="lmt-transport-receipt-0001", issue_receipt=receipt, now=NOW)
    assert result["decision"]["issue_receipt"] == receipt
    assert result["decision"]["issue_receipt"]["underlying"]["reference"] == 582.74
    assert result["decision"]["issue_receipt"]["option"]["occ_symbol"] == "LMT260918C00600000"


def test_revision_is_stale_while_pending_and_terminal_plan_never_reopens(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    first = _proposals(repo, state)[0]
    artifact = repo / "site/prophet/index.json"
    data = json.loads(artifact.read_text())
    data["plans"][0]["targets"] = [121.0, 141.0]
    artifact.write_text(json.dumps(data))
    assert desk.snapshot_current_proposals(repo=repo, reviewer=REVIEWER, root=state, now=NOW)["created"] == 1
    current = desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)["proposals"]
    assert len(current) == 1 and current[0]["proposal_id"] == first["proposal_id"] and current[0]["proposal_revision"] == 2
    with pytest.raises(desk.ConflictError, match="superseded"):
        desk.review(root=state, reviewer=REVIEWER, proposal_id=first["proposal_id"], proposal_revision=1,
                    action="reject", reason_codes=["ABSTAIN"], idempotency_key="stale-revision-reject-001", issue_receipt=None, now=NOW)
    desk.review(root=state, reviewer=REVIEWER, proposal_id=first["proposal_id"], proposal_revision=2,
                action="reject", reason_codes=["ABSTAIN"], idempotency_key="terminal-revision-reject", issue_receipt=None, now=NOW)
    data["plans"][0]["targets"] = [122.0, 142.0]
    artifact.write_text(json.dumps(data))
    assert desk.snapshot_current_proposals(repo=repo, reviewer=REVIEWER, root=state, now=NOW)["created"] == 0


def test_effective_session_rolls_weekend_and_after_close_to_next_nyse_session() -> None:
    assert desk._session_for(datetime(2026, 8, 7, 21, 0, tzinfo=timezone.utc)) == "2026-08-10"  # Fri 17:00 ET
    assert desk._session_for(datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)) == "2026-08-10"  # Saturday


def test_private_projection_cannot_write_a_public_artifact(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    output = state / "projection.json"
    payload = build_private_projection(repo=repo, state_dir=state, output=output, reviewer=REVIEWER)
    assert json.loads(output.read_text())["schema"] == payload["schema"]
    with pytest.raises(ValueError, match="private state"):
        build_private_projection(repo=repo, state_dir=state, output=tmp_path / "site" / "issue_desk.json", reviewer=REVIEWER)


def test_private_projection_direct_cli_bootstraps_repo_imports() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "build_options_issue_desk.py"), "--help"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "private Issue Desk projection" in result.stdout


def test_occ_identity_and_negative_weights_fail_closed() -> None:
    receipt = _receipt(symbol="TEST0")
    receipt["option"]["occ_symbol"] = "AAPL260918C00200000"
    with pytest.raises(desk.IssueDeskError, match="OCC"):
        desk._validate_issue_receipt(receipt, decision_at=NOW, expected_symbol="TEST0")
    receipt = _receipt(symbol="TEST0")
    receipt["risk"]["loss_at_stop_weight"] = -0.01
    with pytest.raises(desk.IssueDeskError, match="loss_at_stop_weight"):
        desk._validate_issue_receipt(receipt, decision_at=NOW, expected_symbol="TEST0")
    receipt = _receipt(symbol="TEST0")
    receipt["option"]["nbbo_mid"] = receipt["option"]["nbbo_ask"]
    receipt["option"]["spread_pct"] = receipt["option"]["spread"] / receipt["option"]["nbbo_ask"]
    with pytest.raises(desk.IssueDeskError, match="NBBO"):
        desk._validate_issue_receipt(receipt, decision_at=NOW, expected_symbol="TEST0")
    receipt = _receipt(symbol="TEST0")
    receipt["option"]["expiry"] = "2026-08-14"
    receipt["option"]["occ_symbol"] = "TEST0260814C00200000"
    with pytest.raises(desk.IssueDeskError, match="expiry"):
        desk._validate_issue_receipt(receipt, decision_at=NOW, expected_symbol="TEST0")


def test_receipt_rejects_unregistered_fields_and_noncanonical_occ() -> None:
    receipt = _receipt(symbol="TEST0")
    receipt["option"]["may_trade"] = True
    with pytest.raises(desk.IssueDeskError, match="receipt contract"):
        desk._validate_issue_receipt(receipt, decision_at=NOW, expected_symbol="TEST0")
    receipt = _receipt(symbol="TEST0")
    receipt["option"]["occ_symbol"] = receipt["option"]["occ_symbol"].lower()
    with pytest.raises(desk.IssueDeskError, match="occ_symbol"):
        desk._validate_issue_receipt(receipt, decision_at=NOW, expected_symbol="TEST0")


def test_future_context_is_explicitly_dropped(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    (repo / "site/options_prophet/index.json").write_text(json.dumps({
        "schema": "options.prophet_shadow/v1", "authority": "display_only",
        "available_at": "2026-08-10T16:00:00Z",
        "watchlist": [{"symbol": "TEST0", "available_at": "2026-08-10T16:00:00Z"}],
    }))
    proposal = _proposals(repo, state)[0]
    shadow = next(item for item in proposal["context_receipts"] if item["kind"] == "options_shadow")
    assert shadow["source"]["available_at"] is None
    assert shadow["source"]["status"] == "future_unusable"
    assert shadow["evidence"] is None and shadow["gap"] == "options_shadow_future_or_unavailable"
    vol = next(item for item in proposal["context_receipts"] if item["kind"] == "vol_regime")
    assert vol["source"]["status"] == "availability_missing" and vol["evidence"] is None


def test_context_artifacts_are_single_read_and_exact_clock_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, state = _repo(tmp_path, n=2), tmp_path / "state"
    (repo / "site/options_prophet/index.json").write_text(json.dumps({
        "schema": "options.prophet_shadow/v1", "authority": "display_only",
        "available_at": "2026-08-10T14:10:00Z",
        "watchlist": [
            {"symbol": f"TEST{i}", "available_at": "2026-08-10T14:00:00Z",
             "source_signing_reliable": False, "direction_reliable": False}
            for i in range(2)
        ],
    }))
    (repo / "site/vol/regime.json").write_text(json.dumps({
        "schema": "options.vol_regime/v1", "available_at": "2026-08-10T14:10:00Z",
        "snapshot": {"asof": "2026-08-10", "regime": "normalizing", "scored_active": False},
    }))
    gex_dir = repo / "site/options_structure/gex_state"
    gex_dir.mkdir(parents=True)
    for i in range(2):
        (gex_dir / f"TEST{i}.json").write_text(json.dumps({
            "schema": "options_structure.gex_state/v1", "available_at": "2026-08-10T14:10:00Z",
            "root": f"TEST{i}", "spot": 100.0, "authority_tier": "display",
        }))
    original = desk._read_json
    calls: dict[str, int] = {}

    def counted(path: Path):
        key = str(path.relative_to(repo))
        calls[key] = calls.get(key, 0) + 1
        return original(path)

    monkeypatch.setattr(desk, "_read_json", counted)
    assert desk.snapshot_current_proposals(repo=repo, reviewer=REVIEWER, root=state, now=NOW)["created"] == 2
    assert calls == {
        "site/prophet/index.json": 1,
        "site/options_prophet/index.json": 1,
        "site/vol/regime.json": 1,
        "site/options_structure/gex_state/TEST0.json": 1,
        "site/options_structure/gex_state/TEST1.json": 1,
    }
    proposals = desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)["proposals"]
    assert all(all(receipt["evidence"] is not None for receipt in row["context_receipts"]) for row in proposals)


def test_context_authority_is_normalized_and_schema_rejects_objects(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    (repo / "site/options_prophet/index.json").write_text(json.dumps({
        "schema": "options.prophet_shadow/v1", "authority": {"may_trade": True},
        "available_at": "2026-08-10T14:10:00Z",
        "watchlist": [{"symbol": "TEST0", "available_at": "2026-08-10T14:00:00Z"}],
    }))
    proposal = _proposals(repo, state)[0]
    receipts = {row["kind"]: row for row in proposal["context_receipts"]}
    assert receipts["options_shadow"]["authority"] == "unknown"
    assert receipts["vol_regime"]["authority"] == "display_context"
    assert receipts["gex_state"]["authority"] == "display_context"
    forged = json.loads(json.dumps(proposal))
    forged["context_receipts"][0]["authority"] = {"may_trade": True}
    with pytest.raises(desk.IssueDeskError, match="proposal contract"):
        desk._fold([forged], [])


def test_fold_rejects_forged_persisted_context_semantics(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    proposal = _proposals(repo, state)[0]

    mismatched_kind = json.loads(json.dumps(proposal))
    mismatched_kind["context_receipts"][0]["source"]["kind"] = "gex_state"
    with pytest.raises(desk.IssueDeskError, match="proposal contract|source kind"):
        desk._fold([mismatched_kind], [])

    future_available = json.loads(json.dumps(proposal))
    source = future_available["context_receipts"][0]["source"]
    source.update({
        "status": "available", "schema": "options.prophet_shadow/v1",
        "available_at": "2026-08-10T16:00:00Z",
    })
    future_available["context_receipts"][0]["evidence"] = {
        "symbol": "TEST0", "available_at": "2026-08-10T14:00:00Z"
    }
    future_available["context_receipts"][0]["gap"] = None
    with pytest.raises(desk.IssueDeskError, match="context availability exceeds"):
        desk._fold([future_available], [])

    unavailable_with_evidence = json.loads(json.dumps(proposal))
    unavailable_with_evidence["context_receipts"][0]["evidence"] = {"may_trade": True}
    unavailable_with_evidence["context_receipts"][0]["gap"] = None
    with pytest.raises(desk.IssueDeskError, match="proposal contract|explicit gap"):
        desk._fold([unavailable_with_evidence], [])


def test_fold_binds_options_evidence_clock_and_symbol_to_source_and_proposal(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    (repo / "site/options_prophet/index.json").write_text(json.dumps({
        "schema": "options.prophet_shadow/v1", "authority": "display_only",
        "available_at": "2026-08-10T14:10:00Z",
        "watchlist": [{
            "symbol": "TEST0", "available_at": "2026-08-10T14:00:00Z",
            "source_signing_reliable": False, "direction_reliable": False,
        }],
    }))
    proposal = _proposals(repo, state)[0]

    future_evidence = json.loads(json.dumps(proposal))
    shadow = next(row for row in future_evidence["context_receipts"] if row["kind"] == "options_shadow")
    shadow["evidence"]["available_at"] = "2026-08-10T14:11:00Z"
    with pytest.raises(desk.IssueDeskError, match="evidence availability exceeds"):
        desk._fold([future_evidence], [])

    wrong_symbol = json.loads(json.dumps(proposal))
    shadow = next(row for row in wrong_symbol["context_receipts"] if row["kind"] == "options_shadow")
    shadow["evidence"]["symbol"] = "FORGED"
    with pytest.raises(desk.IssueDeskError, match="evidence symbol"):
        desk._fold([wrong_symbol], [])


def test_replay_rejects_decision_on_non_latest_revision(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    proposal = _proposals(repo, state)[0]
    desk.review(
        root=state, reviewer=REVIEWER, proposal_id=proposal["proposal_id"], proposal_revision=1,
        action="reject", reason_codes=["ABSTAIN"], idempotency_key="old-revision-decision-001",
        issue_receipt=None, now=NOW,
    )
    newer = json.loads(json.dumps(proposal))
    newer["proposal_revision"] = 2
    newer["source"]["sha256"] = "b" * 64
    with (state / "proposals.jsonl").open("ab") as handle:
        handle.write(desk._canonical(newer) + b"\n")
    with pytest.raises(desk.IssueDeskError, match="non-latest proposal revision"):
        desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)


def test_replay_enforces_action_specific_reason_codes(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    proposal = _proposals(repo, state)[0]
    desk.review(
        root=state, reviewer=REVIEWER, proposal_id=proposal["proposal_id"], proposal_revision=1,
        action="reject", reason_codes=["ABSTAIN"], idempotency_key="reason-replay-decision-001",
        issue_receipt=None, now=NOW,
    )
    decision_path = state / "decisions.jsonl"
    decision = json.loads(decision_path.read_text())
    decision["reason_codes"] = ["EXECUTION_VERIFIED"]
    decision["request_sha256"] = desk._sha256({
        "proposal_id": decision["proposal_id"], "proposal_revision": decision["proposal_revision"],
        "action": decision["action"], "reason_codes": decision["reason_codes"],
        "issue_receipt": decision["issue_receipt"], "reviewer": decision["reviewer"],
    })
    decision_path.write_bytes(desk._canonical(decision) + b"\n")
    with pytest.raises(desk.IssueDeskError, match="decision contract|reason_codes"):
        desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)


def test_contract_schemas_accept_real_pending_and_issued_documents(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    pending = desk.document(repo=repo, reviewer=REVIEWER, root=state, now=NOW)
    validator = _contract_validator("options.issue_desk.v1.schema.json")
    validator.validate(pending)

    proposal = pending["proposals"][0]
    desk.review(
        root=state,
        reviewer=REVIEWER,
        proposal_id=proposal["proposal_id"],
        proposal_revision=proposal["proposal_revision"],
        action="approve",
        reason_codes=["EXECUTION_VERIFIED"],
        idempotency_key="schema-round-trip-issue-001",
        issue_receipt=_receipt(symbol=proposal["macro_candidate"]["asset"]),
        now=NOW,
    )
    issued = desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)
    validator.validate(issued)
    assert issued["proposals"][0]["state"] == "ISSUED"


def test_decision_cannot_precede_proposal_availability(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    proposal = _proposals(repo, state)[0]
    earlier = NOW.replace(hour=14)
    receipt = _receipt(symbol=proposal["macro_candidate"]["asset"])
    receipt["option"]["quote_at"] = "2026-08-10T13:55:00Z"
    with pytest.raises(desk.ConflictError, match="proposal availability"):
        desk.review(
            root=state,
            reviewer=REVIEWER,
            proposal_id=proposal["proposal_id"],
            proposal_revision=proposal["proposal_revision"],
            action="approve",
            reason_codes=["EXECUTION_VERIFIED"],
            idempotency_key="backdated-decision-0001",
            issue_receipt=receipt,
            now=earlier,
        )


def test_append_only_replay_rejects_duplicate_and_tampered_rows(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path), tmp_path / "state"
    proposal = _proposals(repo, state)[0]
    proposal_path = state / "proposals.jsonl"
    proposal_path.write_bytes(proposal_path.read_bytes() + proposal_path.read_bytes())
    with pytest.raises(desk.IssueDeskError, match="duplicate proposal revision"):
        desk.document(repo=repo, reviewer=REVIEWER, root=state, snapshot=False, now=NOW)

    clean_state = tmp_path / "clean-state"
    proposal = _proposals(repo, clean_state)[0]
    desk.review(
        root=clean_state,
        reviewer=REVIEWER,
        proposal_id=proposal["proposal_id"],
        proposal_revision=proposal["proposal_revision"],
        action="approve",
        reason_codes=["EXECUTION_VERIFIED"],
        idempotency_key="tamper-replay-decision-001",
        issue_receipt=_receipt(symbol=proposal["macro_candidate"]["asset"]),
        now=NOW,
    )
    decision_path = clean_state / "decisions.jsonl"
    decision = json.loads(decision_path.read_text())
    decision["proposal_symbol"] = "FORGED"
    decision_path.write_text(json.dumps(decision, separators=(",", ":"), sort_keys=True) + "\n")
    with pytest.raises(desk.IssueDeskError, match="proposal_symbol"):
        desk.document(repo=repo, reviewer=REVIEWER, root=clean_state, snapshot=False, now=NOW)
