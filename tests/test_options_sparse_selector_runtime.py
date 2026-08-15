from __future__ import annotations

import copy
import hashlib
import json
import os
import resource
import shutil
import stat
import sys
import time
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft202012Validator

from engine import options_market_memory_receipt_store as context_store
from engine import options_signal_campaign as campaign_engine
from engine import options_sparse_selector as selector
from lib import nyse_calendar

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/options/options.sparse_selector_runtime.v1.schema.json"
# Frozen first-row template. Reading the live nightly store here taints every
# ``== N`` in this file as an options-episodes vintage pin (ci-pack-3).
_EPISODE_TEMPLATE = (
    ROOT / "tests/fixtures/options_sparse_selector/episode_template.json"
)


@pytest.fixture(autouse=True)
def _private_runtime_test_harness(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Inject private armed semantics only into tests that exercise transitions."""

    if request.node.name in {
        "test_schema_and_frozen_digests_are_valid",
        "test_proposal_canary_refuses_w1a_before_private_store_creation",
        "test_public_plan_and_commit_are_inert_before_private_store_creation",
        "test_core_activation_preserves_private_paper_only_boundary",
    }:
        return
    monkeypatch.setattr(selector, "SELECTOR_RUNTIME_ARMED", True)
    monkeypatch.setattr(selector, "plan_cycle", selector._plan_cycle_internal)
    monkeypatch.setattr(selector, "commit_cycle", selector._commit_cycle_internal)


def _stable_id(prefix: str, *parts: object) -> str:
    body = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(body).hexdigest()[:24]}"


def _episode(
    source_event_id: str,
    available_at: str,
    *,
    strike: float = 700.0,
) -> dict:
    base = json.loads(_EPISODE_TEMPLATE.read_text(encoding="utf-8"))
    row = copy.deepcopy(base)
    available = datetime.fromisoformat(available_at.replace("Z", "+00:00"))
    session = available.astimezone(ZoneInfo("America/New_York")).date()
    prior = nyse_calendar.session_n_back(session, 1)
    assert prior is not None
    row["source_event_id"] = source_event_id
    row["episode_id"] = _stable_id(
        "osep", row["schema"], row["source"], source_event_id
    )
    row["available_at"] = available_at
    row["event_time"] = (
        (available - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    )
    row["observed_at"] = available_at
    row["decision_at"] = available_at
    row["published_at"] = None
    row["session_date"] = session.isoformat()
    row["ticker"] = "SPY"
    row["contract"] = {
        "expiration": "2026-08-21",
        "right": "C",
        "strike": strike,
    }
    row["feature_snapshot"]["flow_side"] = "~buy"
    row["feature_snapshot"]["premium_usd"] = 1_000_000.0
    row["feature_snapshot"]["selection_floor_usd"] = 25_000
    row["feature_snapshot"]["contracts"] = 100
    row["feature_snapshot"]["avg_option_trade_price"] = 100.0
    row["feature_snapshot"]["dte"] = 9
    row["feature_snapshot"]["dte"] = (
        datetime.fromisoformat(row["contract"]["expiration"]).date() - session
    ).days
    row["provenance"]["feature_cutoff"] = available_at
    row["provenance"]["source_snapshot_asof"] = available_at
    row["provenance"]["source_artifact"] = (
        f"live_flow/events/{session.isoformat()}.jsonl"
    )
    row["provenance"]["oi_vintage"] = prior.isoformat()
    campaign_engine.validate_episode(row)
    return row


def _source(
    episode_groups: list[list[dict]],
    *,
    observed_at: str = "2026-08-12T14:00:00Z",
    commit: str = "a" * 40,
) -> selector.SourceSnapshot:
    episodes = [episode for group in episode_groups for episode in group]
    episode_raw = b"".join(
        campaign_engine.canonical_bytes(row) + b"\n" for row in episodes
    )
    snapshot = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.EPISODES_PATH),
        campaign_engine.EPISODES_PATH,
        episode_raw,
    )
    grouped = campaign_engine._validated_episode_groups(snapshot)
    campaigns = [
        campaign_engine._campaign_payload(key, members, snapshot, None)
        for key, members in sorted(grouped.items())
    ]
    campaigns_raw = b"".join(
        campaign_engine.canonical_bytes(row) + b"\n" for row in campaigns
    )
    return _snapshot_with_checkpoint(
        commit=commit,
        campaigns_raw=campaigns_raw,
        episodes_raw=episode_raw,
        observed_at=observed_at,
    )


def _snapshot_with_checkpoint(
    *,
    commit: str,
    campaigns_raw: bytes,
    episodes_raw: bytes,
    observed_at: str,
) -> selector.SourceSnapshot:
    episodes = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.EPISODES_PATH),
        campaign_engine.EPISODES_PATH,
        episodes_raw,
    )
    campaigns = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.CAMPAIGNS_PATH),
        campaign_engine.CAMPAIGNS_PATH,
        campaigns_raw,
    )
    h60 = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.H60_PATH), campaign_engine.H60_PATH, b""
    )
    sessions = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.SESSION_PATH), campaign_engine.SESSION_PATH, b""
    )
    outcomes = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.OUTCOMES_PATH), campaign_engine.OUTCOMES_PATH, b""
    )
    checkpoint = campaign_engine._build_checkpoint(
        episodes, h60, sessions, campaigns, outcomes
    )
    return selector.SourceSnapshot(
        commit=commit,
        campaigns_raw=campaigns_raw,
        episodes_raw=episodes_raw,
        observed_at=observed_at,
        checkpoint_raw=campaign_engine.canonical_bytes(checkpoint) + b"\n",
    )


def _many_candidate_source(count: int) -> selector.SourceSnapshot:
    template = _episode("bounded-template", "2026-08-12T13:31:00Z")
    groups: list[list[dict]] = []
    for ordinal in range(count):
        row = copy.deepcopy(template)
        source_event_id = f"bounded-{ordinal:05d}"
        row["source_event_id"] = source_event_id
        row["episode_id"] = _stable_id(
            "osep", row["schema"], row["source"], source_event_id
        )
        row["contract"]["strike"] = 700.0 + ordinal / 100.0
        groups.append([row])
    return _source(groups)


def _global_order_adversary_source(count: int, move_rank: int) -> selector.SourceSnapshot:
    source = _many_candidate_source(count)
    campaigns = [json.loads(line) for line in source.campaigns_raw.splitlines()]
    ranked = sorted(
        campaigns,
        key=lambda row: selector._candidate_id(row["campaign_id"]),
    )
    moved = ranked[move_rank - 1]
    reordered = [row for row in campaigns if row is not moved]
    reordered.append(moved)
    return _snapshot_with_checkpoint(
        commit=source.commit,
        campaigns_raw=b"".join(
            campaign_engine.canonical_bytes(row) + b"\n" for row in reordered
        ),
        episodes_raw=source.episodes_raw,
        observed_at=source.observed_at,
    )


def _revised_source(
    first: dict,
    second: dict,
    *,
    observed_at: str = "2026-08-12T14:00:00Z",
) -> selector.SourceSnapshot:
    first_raw = campaign_engine.canonical_bytes(first) + b"\n"
    first_snapshot = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.EPISODES_PATH),
        campaign_engine.EPISODES_PATH,
        first_raw,
    )
    group = next(iter(campaign_engine._validated_episode_groups(first_snapshot)))
    first_campaign = campaign_engine._campaign_payload(
        group,
        campaign_engine._validated_episode_groups(first_snapshot)[group],
        first_snapshot,
        None,
    )
    full_raw = first_raw + campaign_engine.canonical_bytes(second) + b"\n"
    full_snapshot = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.EPISODES_PATH),
        campaign_engine.EPISODES_PATH,
        full_raw,
    )
    full_members = campaign_engine._validated_episode_groups(full_snapshot)[group]
    second_campaign = campaign_engine._campaign_payload(
        group, full_members, full_snapshot, first_campaign
    )
    campaigns_raw = b"".join(
        campaign_engine.canonical_bytes(row) + b"\n"
        for row in (first_campaign, second_campaign)
    )
    return _snapshot_with_checkpoint(
        commit="b" * 40,
        campaigns_raw=campaigns_raw,
        episodes_raw=full_raw,
        observed_at=observed_at,
    )


def _append_group_source(
    prior: selector.SourceSnapshot,
    episode: dict,
    *,
    observed_at: str,
) -> selector.SourceSnapshot:
    episodes_raw = prior.episodes_raw + campaign_engine.canonical_bytes(episode) + b"\n"
    snapshot = campaign_engine._snapshot_from_raw(
        Path(campaign_engine.EPISODES_PATH),
        campaign_engine.EPISODES_PATH,
        episodes_raw,
    )
    groups = campaign_engine._validated_episode_groups(snapshot)
    key = campaign_engine._group_key(episode)
    campaign = campaign_engine._campaign_payload(key, groups[key], snapshot, None)
    return _snapshot_with_checkpoint(
        commit="b" * 40,
        campaigns_raw=(
            prior.campaigns_raw + campaign_engine.canonical_bytes(campaign) + b"\n"
        ),
        episodes_raw=episodes_raw,
        observed_at=observed_at,
    )


def _clock(value: str = "2026-08-12T14:00:00Z"):
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return lambda: instant


def _pinned_source(
    source: selector.SourceSnapshot,
    head: dict,
) -> selector.SourceSnapshot:
    return selector.SourceSnapshot(
        commit=head["source_commit"],
        campaigns_raw=None,
        episodes_raw=None,
        observed_at=head["source_observed_at"],
        campaigns_blob_oid=head["source_campaign_prefix"]["git_blob_oid"],
        episodes_blob_oid=head["source_episode_prefix"]["git_blob_oid"],
        checkpoint_raw=None,
        checkpoint_blob_oid=head["source_checkpoint"]["git_blob_oid"],
    )


def _commit_first(
    root: Path,
    source: selector.SourceSnapshot,
    *,
    scheduled_at: str = "2026-08-12T14:00:00Z",
    observed_plan_sizes: list[tuple[int, int]] | None = None,
) -> dict:
    head: dict | None = None
    prior = selector._load_head(root) if root.exists() else None
    initial_cycles = 0 if prior is None else prior["cycle_count"]
    active = source
    active_schedule = scheduled_at
    for _ in range(64):
        plan = selector.plan_cycle(
            root=root,
            source=active,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at=active_schedule,
            clock=_clock(active_schedule),
            runtime_armed=True,
        )
        assert len(plan.objects) <= selector.MAX_SOURCE_OBJECTS_PER_CYCLE
        assert len(selector.canonical_bytes(plan.intent)) <= selector.MAX_INTENT_BYTES
        if observed_plan_sizes is not None:
            observed_plan_sizes.append(
                (len(plan.objects), len(selector.canonical_bytes(plan.intent)))
            )
        head = selector.commit_cycle(root, plan)
        if head["source_commit"] == source.commit and head["cycle_count"] > initial_cycles:
            return head
        if head["cycle_count"] > initial_cycles and head["source_commit"] != source.commit:
            active_schedule = selector.utc_text(
                selector._utc(active_schedule, label="test schedule")
                + timedelta(minutes=5)
            )
            initial_cycles = head["cycle_count"]
        active = (
            source
            if (
                head["source_phase"] == "AUDITING"
                or head["source_commit"] != source.commit
            )
            else _pinned_source(source, head)
        )
    raise AssertionError("selector source epoch did not reach its first manifest")


def _manifest_sizes_until_drain(
    root: Path,
    source: selector.SourceSnapshot,
) -> tuple[list[int], dict, list[tuple[int, int]]]:
    observed_plan_sizes: list[tuple[int, int]] = []
    head = _commit_first(root, source, observed_plan_sizes=observed_plan_sizes)
    sizes: list[int] = []
    scheduled = selector._utc(
        "2026-08-12T14:00:00Z", label="test first schedule"
    )
    while True:
        cycle = _last_cycle(root, head)
        if cycle["next_manifest"] is not None:
            manifest = selector._load_pointer(
                root, cycle["next_manifest"], label="bounded manifest"
            )
            sizes.append(manifest["candidate_count"])
        if head["source_phase"] == "DRAINED":
            return sizes, head, observed_plan_sizes
        scheduled += timedelta(minutes=5)
        slot = selector.utc_text(scheduled)
        plan = selector.plan_cycle(
            root=root,
            source=_pinned_source(source, head),
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at=slot,
            clock=_clock(slot),
            runtime_armed=True,
        )
        assert len(plan.objects) <= selector.MAX_SOURCE_OBJECTS_PER_CYCLE
        assert len(selector.canonical_bytes(plan.intent)) <= selector.MAX_INTENT_BYTES
        observed_plan_sizes.append(
            (len(plan.objects), len(selector.canonical_bytes(plan.intent)))
        )
        head = selector.commit_cycle(root, plan)


def _last_cycle(root: Path, head: dict) -> dict:
    return selector._load_pointer(root, head["last_cycle"], label="test cycle")


def _decision_rows(
    root: Path,
    *,
    evidence_inputs: selector.EvidenceInputs | None = None,
) -> list[dict]:
    return selector.authenticate_store(
        root, evidence_inputs=evidence_inputs
    )[1]


def _cycle_rows(root: Path, head: dict) -> list[dict]:
    return [
        selector._load_pointer(root, row["selector_cycle"], label="test queued cycle")
        for row in _handoff_rows(root, head)
    ]


def _handoff_rows(root: Path, head: dict) -> list[dict]:
    return [
        record["item"]
        for record in selector.authenticated_pending_handoff_queue(
            root,
            head,
            after_ordinal=0,
            after_cycle_id=None,
            after_cycle_pointer=None,
            after_queue_item_id=None,
            after_queue_item_pointer=None,
        )
    ]


def _context_head(references: list[dict], *, published_at: str) -> dict:
    zero = "0" * 64
    one = "1" * 64
    reference_body = selector.context_bridge.canonical_reference_set_bytes(references)
    return context_store._head(
        deployed_commit="d" * 40,
        audit={"audit_id": f"omctxaudit_{zero}", "audited_at": published_at},
        audit_sha256=zero,
        audit_object_key=f"audits/00/{zero}.json",
        reference_set={
            "reference_set_sha256": hashlib.sha256(reference_body).hexdigest(),
            "reference_count": len(references),
        },
        reference_set_object_sha256=one,
        reference_set_object_key=f"reference_sets/11/{one}.json",
    )


def _publish_w1a(
    root: Path,
    references: list[dict],
    *,
    published_at: str = "2026-08-12T14:00:00Z",
    salt: str = "a",
) -> dict:
    def digest(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    sources = []
    for path in selector.context_bridge._SOURCE_PATHS:
        count = 1 if path == "config/market_memory_canary.v1.json" else 0
        if path == "data/options_signal_episode/episodes.jsonl":
            count = sum(
                item["owner"]["schema"] == "options.signal_episode/v1"
                for item in references
            )
        if path == "data/options_signal_episode/campaigns.jsonl":
            count = sum(
                item["owner"]["schema"] == "options.signal_campaign/v2"
                for item in references
            )
        sources.append(
            {
                "path": path,
                "sha256": digest(path),
                "bytes": 1,
                "record_count": count,
            }
        )
    generations = []
    for ordinal, profile in enumerate(
        selector.context_bridge._GENERATION_PROFILES, start=1
    ):
        token = digest(f"{profile}-{ordinal}-{salt}")
        generations.append(
            {
                "profile": profile,
                "store_id": f"mmstore_{token}",
                "generation_id": f"mmgeneration_{digest('generation-' + token)}",
                "generation_sha256": digest("sha-" + token),
                "capture_count": 0,
            }
        )
    audit = selector.context_bridge.build_audit_receipt(
        references=references,
        source_artifacts=sources,
        context_generations=generations,
        audited_at=published_at,
    )
    head = context_store.publish_receipt_set(
        root,
        deployed_commit=("d" if salt == "a" else "e") * 40,
        references=references,
        audit=audit,
    )
    return context_store.read_current_publication(root) | {"head": head}


def _bound_w1a_reference(
    *,
    owner_id: str,
    record_sha256: str,
    padding_items: int = 0,
) -> dict:
    identity = selector.prereg.SELECTOR_RULE["required_truth_receipts"]["konseki"][
        "subject_identity"
    ]
    token = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()
    source_ids = sorted(
        f"mmsrc_{hashlib.sha256(f'{token}-source-{index}'.encode()).hexdigest()}"
        for index in range(padding_items)
    )
    artifact_ids = sorted(
        hashlib.sha256(f"{token}-artifact-{index}".encode()).hexdigest()
        for index in range(padding_items)
    )
    return selector.context_bridge._reference(
        owner={
            "schema": "options.signal_episode/v1",
            "id": owner_id,
            "record_sha256": record_sha256,
            "ticker": "SPY",
            "event_time": "2026-08-12T13:30:59Z",
            "requested_as_of": "2026-08-12T13:31:00Z",
            "requested_as_of_basis": "durable_available_at",
            "evidence_phase": "decision_time_actual_output",
        },
        subject={
            "subject_id": identity["subject_id"],
            "instrument_id": identity["instrument_id"],
        },
        identity_config_sha256=identity["identity_config_sha256"],
        disposition="bound",
        reason=None,
        context={
            "context_id": f"mmctx_{token}",
            "packet_sha256": token,
            "capture_id": f"mmcapture_{token}",
            "capture_schema": "market_memory.capture_receipt.v1",
            "query_id": f"mmquery_{token}",
            "basis": "exact_requested_as_of_capture",
            "source_receipt_ids": source_ids,
            "source_artifact_sha256s": artifact_ids,
            "missing_feature_ids": [],
            "domain_coverage_sha256": token,
        },
    )


def _passing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: selector.SourceSnapshot,
    *,
    padding_bytes: int = 0,
) -> selector.EvidenceInputs:
    episodes = [json.loads(line) for line in source.episodes_raw.splitlines()]
    identity = selector.prereg.SELECTOR_RULE["required_truth_receipts"]["konseki"][
        "subject_identity"
    ]
    subject = {
        "subject_id": identity["subject_id"],
        "instrument_id": identity["instrument_id"],
    }
    references: list[dict] = []
    by_episode: dict[str, tuple[dict, ...]] = {}
    for line, episode in zip(source.episodes_raw.splitlines(), episodes, strict=True):
        token = hashlib.sha256(episode["episode_id"].encode("utf-8")).hexdigest()
        reference = selector.context_bridge._reference(
            owner={
                "schema": "options.signal_episode/v1",
                "id": episode["episode_id"],
                "record_sha256": hashlib.sha256(line).hexdigest(),
                "ticker": episode["ticker"],
                "event_time": episode["event_time"],
                "requested_as_of": episode["available_at"],
                "requested_as_of_basis": "durable_available_at",
                "evidence_phase": "decision_time_actual_output",
            },
            subject=subject,
            identity_config_sha256=identity["identity_config_sha256"],
            disposition="bound",
            reason=None,
            context={
                "context_id": f"mmctx_{token}",
                "packet_sha256": token,
                "capture_id": f"mmcapture_{token}",
                "capture_schema": "market_memory.capture_receipt.v1",
                "query_id": f"mmquery_{token}",
                "basis": "exact_requested_as_of_capture",
                "source_receipt_ids": [],
                "source_artifact_sha256s": [],
                "missing_feature_ids": [],
                "domain_coverage_sha256": token,
            },
        )
        references.append(reference)
        by_episode[episode["episode_id"]] = (reference,)
    references.sort(key=lambda row: (row["owner"]["schema"], row["owner"]["id"]))
    w1a_root = tmp_path / "w1a-receipts"
    publication = _publish_w1a(w1a_root, references)

    enrollments: dict[tuple[str, str, str, str], tuple[tuple, ...]] = {}
    enrollment_pointers: dict[str, dict] = {}
    latest_marks: dict[str, dict] = {}
    mark_rows: dict[tuple[str, str], tuple[dict, dict, dict]] = {}
    for campaign in (json.loads(line) for line in source.campaigns_raw.splitlines()):
        group = campaign["group"]
        token = hashlib.sha256(campaign["campaign_id"].encode("utf-8")).hexdigest()
        plan_id = f"selector-test-{campaign['campaign_id']}"
        strike = group["strike_key"]
        strike_millis = int(float(strike) * 1000)
        expiry_compact = group["expiration"].replace("-", "")[2:]
        contract = {
            "root": group["ticker"],
            "right": group["right"],
            "expiry": group["expiration"],
            "strike": strike,
            "strike_millis": strike_millis,
            "occ_symbol": (
                f"{group['ticker']:<6}{expiry_compact}{group['right']}"
                f"{strike_millis:08d}"
            ),
        }
        plan_identity = {
            "id": plan_id,
            "asset": group["ticker"],
            "plan_asof": None,
            "recorded_at": None,
            "entry_date": None,
        }
        event_id = f"posle_{token}"
        enrollment_pointer = {
            "schema": selector.lifecycle.EVENT_POINTER_SCHEMA,
            "event_id": event_id,
            "key": f"events/2026-08-12/{event_id}.json",
            "sha256": token,
            "bytes": 1,
        }
        observation_id = f"pom_obs_{token}"
        mark_pointer = {
            "schema": selector.mark_chain.EVIDENCE_POINTER_SCHEMA,
            "observation_id": observation_id,
            "key": f"observations/2026-08-12/{observation_id}.json",
            "sha256": token,
            "bytes": 1,
        }
        enrollment = {
            "payload": {"plan": plan_identity, "contract": contract},
            "authority": dict(selector.FALSE_AUTHORITY),
            "padding": "x" * padding_bytes,
        }
        observation = {
            "observed_at_utc": "2026-08-12T14:04:59Z",
            "authority": dict(selector.FALSE_AUTHORITY),
            "padding": "x" * padding_bytes,
        }
        row = {
            "plan": plan_identity,
            "contract": contract,
            "quote_status": "available",
            "quote": {"quote_ts_utc": "2026-08-12T14:04:58Z"},
        }
        contract_key = selector._campaign_contract_key(campaign)
        enrollments[contract_key] = ((plan_id, enrollment, enrollment_pointer),)
        enrollment_pointers[plan_id] = enrollment_pointer
        latest_marks[plan_id] = {
            "contract_occ_symbol": contract["occ_symbol"],
            "contract_drift": False,
            "plan_identity_drift": False,
            "sessions": {"2026-08-12": mark_pointer},
        }
        mark_rows[(plan_id, "2026-08-12")] = (mark_pointer, observation, row)
    state = {
        "enrollments": enrollment_pointers,
        "terminals": {},
        "latest_marks": latest_marks,
    }
    snapshot = selector.EvidenceSnapshot(
        w1a_head=publication["head"],
        w1a_audit=publication["audit"],
        w1a_references=tuple(publication["references"]),
        w1a_root_path_sha256=hashlib.sha256(
            os.fsencode(str(w1a_root.absolute()))
        ).hexdigest(),
        w1a_by_episode=by_episode,
        lifecycle_state=state,
        enrollments_by_contract=enrollments,
        mark_rows_by_plan_session=mark_rows,
        w1a_error=False,
        mark_error=False,
        lifecycle_error=False,
        lifecycle_publishable=True,
    )
    monkeypatch.setattr(
        selector.lifecycle,
        "_validate_state_shape",
        lambda value: copy.deepcopy(value),
    )
    monkeypatch.setattr(
        selector,
        "_build_evidence_snapshot",
        lambda inputs, **_scope: snapshot
        if inputs.w1a_receipt_root == w1a_root
        else pytest.fail(
            "passing evidence inputs changed"
        ),
    )

    def reference_for_candidate(
        candidate: dict,
        evidence_snapshot: selector.EvidenceSnapshot,
        *,
        evidence_available_at: datetime,
    ):
        assert evidence_available_at.tzinfo is not None
        matching = evidence_snapshot.w1a_by_episode[
            candidate["final_episode_row"]["episode_id"]
        ]
        assert len(matching) == 1
        reference = matching[0]
        return selector._evidence_object(
            {
                "schema": "options.sparse_selector_konseki_evidence/v1",
                "source_publication_id": publication["head"]["publication_id"],
                "reference": reference,
                "authority": dict(selector.FALSE_AUTHORITY),
            }
        ), []

    monkeypatch.setattr(
        selector, "_reference_for_candidate", reference_for_candidate
    )
    return selector.EvidenceInputs(w1a_receipt_root=w1a_root)


def test_schema_and_frozen_digests_are_valid() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert selector.SELECTOR_RUNTIME_ARMED is True
    assert selector.SELECTOR_PROPOSALS_ARMED is False
    assert selector.DIGESTS == {
        "benchmark_digest_sha256": "20e6c19f691cf9a07381288d6bdb33c6d74c8957b074ceefcdaf0ab8da1b1f42",
        "selector_rule_sha256": "a98d3b92e1ebe069c141d5f79ee9260eeb2b8eeee4f90f574ef0069c062ad20b",
        "candidate_manifest_rule_sha256": "70e1bec30bde9764a5e88dfec6aa01a654b9eece65ee3b7d20fa57e1c87444a6",
        "decision_rule_sha256": "734d742723f650a05b321131079c1329ff608e9e72bf5bcc1d1276b718fdc79c",
        "evidence_rule_sha256": "518ae9a36cf60e400933c07e46ce885955b720cc71c59a39e328800e86ac91af",
        "source_campaign_rule_sha256": "6ff5cc16a74bf27807b3c8540b31794a6d9c54aec8fc152edc02602d646ad7f6",
    }


@pytest.mark.parametrize(
    ("instance", "expected_valid"),
    (
        ([1, 1.0], False),
        ([0, -0.0], False),
        ([[1], [1.0]], False),
        ([{"x": 1}, {"x": 1.0}], False),
        ([{"a": 1, "b": [0, -0.0]}, {"b": [0.0, 0], "a": 1.0}], False),
        ([10**20, 1e20], False),
        ([10**100, 1e100], True),
        ([True, 1], True),
        ([False, 0], True),
    ),
)
def test_linear_unique_items_matches_draft_json_equality(
    instance: list[object], expected_valid: bool
) -> None:
    schema = {"type": "array", "uniqueItems": True}
    stock_valid = not list(Draft202012Validator(schema).iter_errors(instance))
    linear_valid = not list(
        selector._SelectorSchemaValidator(schema).iter_errors(instance)
    )
    assert stock_valid is expected_valid
    assert linear_valid is stock_valid


def test_linear_unique_items_rejects_numeric_equivalent_runtime_pointers() -> None:
    schema = {
        "type": "array",
        "uniqueItems": True,
        "items": {
            "type": "object",
            "required": ["id", "key", "sha256", "bytes"],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string"},
                "key": {"type": "string"},
                "sha256": {"type": "string"},
                "bytes": {"type": "integer"},
            },
        },
    }
    base = {"id": "obj_a", "key": "objects/a.json", "sha256": "a" * 64}
    pointers = [{**base, "bytes": 1}, {**base, "bytes": 1.0}]
    stock_errors = list(Draft202012Validator(schema).iter_errors(pointers))
    linear_errors = list(
        selector._SelectorSchemaValidator(schema).iter_errors(pointers)
    )
    assert any(error.validator == "uniqueItems" for error in stock_errors)
    assert any(error.validator == "uniqueItems" for error in linear_errors)


def test_proposal_canary_refuses_w1a_before_private_store_creation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "never-created"
    with pytest.raises(selector.SparseSelectorUnarmed, match="W1A receipt root"):
        selector.advance(
            private_root=root,
            source=selector.SourceSnapshot("bad", b"", b"", "bad"),
            evidence_inputs=selector.EvidenceInputs(
                w1a_receipt_root=tmp_path / "forbidden-w1a"
            ),
            scheduled_at="bad",
        )
    assert not root.exists()


@pytest.mark.parametrize(
    ("head_proposals", "value"),
    (
        (
            0,
            {
                "schema": "options.sparse_selector_decision/v1",
                "action": "propose",
            },
        ),
        (
            0,
            {
                "schema": "options.sparse_selector_cycle_receipt/v1",
                "propose_count": 1,
            },
        ),
        (1, {"schema": "options.sparse_selector_source_episode_chunk/v1"}),
    ),
)
def test_proposal_canary_rejects_planned_authority_before_wal(
    head_proposals: int,
    value: dict[str, object],
) -> None:
    plan = selector.CyclePlan(
        expected_head_id=None,
        objects=(selector.PlannedObject(key="probe.json", value=value),),
        head={"proposal_session_count": head_proposals},
        intent={},
    )
    with pytest.raises(selector.SparseSelectorUnarmed, match="code-unarmed"):
        selector._assert_proposal_boundary_closed(plan)


def test_proposal_canary_rejects_forged_planner_output_before_wal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "proposal-forgery"
    forged = selector.CyclePlan(
        expected_head_id=None,
        objects=(
            selector.PlannedObject(
                key="decisions/forged.json",
                value={
                    "schema": "options.sparse_selector_decision/v1",
                    "action": "propose",
                },
            ),
        ),
        head={"proposal_session_count": 1},
        intent={},
    )
    monkeypatch.setattr(selector, "_plan_cycle_internal", lambda **_kwargs: forged)
    monkeypatch.setattr(
        selector,
        "_commit_cycle_locked",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("proposal-bearing plan reached commit")
        ),
    )

    with pytest.raises(selector.SparseSelectorUnarmed, match="code-unarmed"):
        selector.advance(
            private_root=root,
            source=selector.SourceSnapshot("bad", b"", b"", "bad"),
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="bad",
        )
    assert not (root / selector.INTENT_FILE).exists()


def test_public_plan_and_commit_are_inert_before_private_store_creation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "public-never-created"
    source = selector.SourceSnapshot("bad", b"", b"", "bad")
    with pytest.raises(selector.SparseSelectorUnarmed, match="public planning is inert"):
        selector.plan_cycle(
            root=root,
            source=source,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="bad",
            clock=_clock(),
        )
    with pytest.raises(selector.SparseSelectorUnarmed, match="public commit is inert"):
        selector.commit_cycle(root, None)
    assert not root.exists()


def test_core_activation_preserves_private_paper_only_boundary() -> None:
    assert (ROOT / "scripts/run_options_sparse_selector.py").is_file()
    assert selector.SELECTOR_RUNTIME_ARMED is True
    assert selector.SELECTOR_PROPOSALS_ARMED is False
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8").lower()
    assert "options_sparse_selector" not in daily
    assert "sparse-selector" not in daily
    assert "make_w1a_export" not in selector.__all__
    assert "make_nbbo_handoff" not in selector.__all__
    assert not hasattr(selector, "make_nbbo_handoff")


def _empty_context_head(*, published_at: str) -> dict:
    return _context_head([], published_at=published_at)


def test_w1a_receipt_root_replaces_caller_export_and_preserves_clock_causality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "w1a-clock"
    publication = _publish_w1a(root, [])
    snapshot = selector._build_evidence_snapshot(
        selector.EvidenceInputs(w1a_receipt_root=root)
    )
    assert snapshot.w1a_head == publication["head"]
    assert snapshot.w1a_references == ()
    assert snapshot.w1a_error is False
    assert not hasattr(selector.EvidenceInputs(), "w1a_export")
    assert not hasattr(selector, "validate_w1a_export")

    episode = _episode("future-export", "2026-08-12T13:31:00Z")
    candidate = {
        "final_episode_row": episode,
        "final_episode_row_sha256": "a" * 64,
        "campaign_row": {"group": {"ticker": "SPY"}},
    }
    monkeypatch.setattr(
        selector.context_bridge,
        "validate_context_reference",
        lambda _value: pytest.fail("future publication must refuse before reference use"),
    )
    evidence, reasons = selector._reference_for_candidate(
        candidate,
        snapshot,
        evidence_available_at=datetime(2026, 8, 12, 13, 59, 59, tzinfo=timezone.utc),
    )
    assert evidence is None
    assert reasons == ["KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"]


def test_episode_owned_w1a_phase_is_authoritative_and_can_propose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([[_episode("w1a-owner-phase", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "selector"
    head = _commit_first(root, source)
    real_reference_for_candidate = selector._reference_for_candidate
    evidence_inputs = _passing_evidence(tmp_path, monkeypatch, source)
    monkeypatch.setattr(
        selector, "_reference_for_candidate", real_reference_for_candidate
    )
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    decision = next(
        item.value
        for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    assert decision["action"] == "propose", decision["reason_codes"]
    assert decision["reason_codes"] == []

    snapshot = selector._build_evidence_snapshot(evidence_inputs)
    wrong_reference = copy.deepcopy(snapshot.w1a_references[0])
    wrong_reference["owner"]["evidence_phase"] = (
        "prospective_after_rule_freeze"
    )
    with pytest.raises(
        selector.context_bridge.OptionsMarketMemoryContextError,
        match="evidence phase",
    ):
        selector.context_bridge.validate_context_reference(wrong_reference)
    episode_id = source.episodes_raw.splitlines()[0]
    owner_id = json.loads(episode_id)["episode_id"]
    wrong_snapshot = replace(
        snapshot,
        w1a_references=(wrong_reference,),
        w1a_by_episode={owner_id: (wrong_reference,)},
    )
    evidence, reasons = real_reference_for_candidate(
        selector._load_pointer(
            root, head["last_candidate"], label="W1A owner-phase candidate"
        ),
        wrong_snapshot,
        evidence_available_at=datetime(
            2026, 8, 12, 14, 5, 0, tzinfo=timezone.utc
        ),
    )
    assert evidence is None
    assert reasons == ["KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"]


def test_producer_rfc3339_offsets_preserve_mark_causality_and_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([[_episode("producer-offset", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "selector"
    head = _commit_first(root, source)
    evidence_inputs = _passing_evidence(tmp_path, monkeypatch, source)
    snapshot = selector._build_evidence_snapshot(evidence_inputs)
    for _pointer, observation, row in snapshot.mark_rows_by_plan_session.values():
        observation["observed_at_utc"] = selector.mark_chain._source_utc_iso(
            datetime(2026, 8, 12, 14, 4, 59, tzinfo=timezone.utc)
        )
        row["quote"]["quote_ts_utc"] = "2026-08-12T10:04:58-04:00"
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    decision = next(
        item.value
        for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    assert decision["action"] == "propose"
    assert selector._source_rfc3339(
        "2026-08-12T14:04:58.000000+00:00", label="producer UTC"
    ) == selector._source_rfc3339(
        "2026-08-12T10:04:58-04:00", label="producer offset"
    )
    with pytest.raises(selector.SparseSelectorError, match="RFC3339"):
        selector._source_rfc3339("nonsense", label="producer nonsense")
    with pytest.raises(selector.SparseSelectorError, match="RFC3339"):
        selector._source_rfc3339(
            "2026-08-12T14:04:58+24:00", label="producer bad offset"
        )


def test_w1a_compact_source_reauthenticates_after_current_head_advances(
    tmp_path: Path,
) -> None:
    episode = _episode("historical-w1a", "2026-08-12T13:31:00Z")
    source = _source([[episode]])
    episode_body = source.episodes_raw.splitlines()[0]
    reference = _bound_w1a_reference(
        owner_id=episode["episode_id"],
        record_sha256=hashlib.sha256(episode_body).hexdigest(),
    )
    w1a_root = tmp_path / "historical-w1a-receipts"
    publication_a = _publish_w1a(w1a_root, [reference])
    selector_root = tmp_path / "historical-selector"
    head = _commit_first(selector_root, source)
    inputs = selector.EvidenceInputs(w1a_receipt_root=w1a_root)
    plan = selector.plan_cycle(
        root=selector_root,
        source=_pinned_source(source, head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    source_receipt = next(
        item
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_w1a_source_receipt/v1"
    )
    assert source_receipt.value["head"] == publication_a["head"]
    assert "references" not in source_receipt.value
    committed = selector.commit_cycle(selector_root, plan)
    assert committed["w1a_publication_high_water"]["publication_id"] == publication_a[
        "head"
    ]["publication_id"]

    publication_b = _publish_w1a(
        w1a_root,
        [reference],
        published_at="2026-08-12T14:01:00Z",
        salt="b",
    )
    assert publication_b["head"] != publication_a["head"]
    authenticated, decisions, _body = selector.authenticate_store(
        selector_root, evidence_inputs=inputs
    )
    assert authenticated == committed
    assert len(decisions) == 1
    historical_generation = selector._load_pointer(
        selector_root,
        decisions[0]["evidence"]["generation"],
        label="historical W1A generation",
    )
    historical_source = selector._load_pointer(
        selector_root,
        historical_generation["w1a_source_receipt"],
        label="historical W1A source receipt",
    )
    assert historical_source["head"] == publication_a["head"]


def test_status_recovers_durable_w1a_intent_only_with_trusted_inputs(
    tmp_path: Path,
) -> None:
    episode = _episode("status-w1a-intent", "2026-08-12T13:31:00Z")
    source = _source([[episode]])
    reference = _bound_w1a_reference(
        owner_id=episode["episode_id"],
        record_sha256=hashlib.sha256(
            source.episodes_raw.splitlines()[0]
        ).hexdigest(),
    )
    w1a_root = tmp_path / "status-w1a-receipts"
    _publish_w1a(w1a_root, [reference])
    root = tmp_path / "status-selector"
    head = _commit_first(root, source)
    inputs = selector.EvidenceInputs(w1a_receipt_root=w1a_root)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == "after_intent":
            raise RuntimeError("status W1A intent crash")

    with pytest.raises(RuntimeError, match="status W1A intent crash"):
        selector.commit_cycle(root, plan, evidence_inputs=inputs, hook=crash)
    assert (root / selector.INTENT_FILE).is_file()
    with pytest.raises(
        selector.SparseSelectorError,
        match="trusted.*W1A|trusted source root|trusted receipt root",
    ):
        selector.status(root)
    report = selector.status(root, evidence_inputs=inputs)
    assert report == {
        "runtime_armed": True,
        "proposals_armed": False,
        "initialized": True,
        "head": head,
        "recovery_intent": True,
        "intent_next_head_id": plan.head["head_id"],
        "intent_next_head": plan.head,
    }
    assert selector.commit_cycle(root, None, evidence_inputs=inputs) == plan.head


def test_status_exposes_exact_first_intent_target_without_parent_head(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("status-first-intent", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "status-first-intent"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == "after_intent":
            raise RuntimeError("first intent crash")

    with pytest.raises(RuntimeError, match="first intent crash"):
        selector.commit_cycle(root, plan, hook=crash)
    report = selector.status(root)
    assert report["head"] is None
    assert report["recovery_intent"] is True
    assert report["intent_next_head_id"] == plan.head["head_id"]
    assert report["intent_next_head"] == plan.head
    assert selector.commit_cycle(root, None) == plan.head


def test_w1a_exact_asof_absence_is_evidence_while_missing_owner_is_not(
    tmp_path: Path,
) -> None:
    referenced_episode = _episode(
        "real-exact-asof-absence",
        "2026-08-12T13:31:00Z",
        strike=700.0,
    )
    missing_episode = _episode(
        "real-missing-owner",
        "2026-08-12T13:31:00Z",
        strike=701.0,
    )
    source = _source([[referenced_episode], [missing_episode]])
    raw_by_episode = {
        episode["episode_id"]: line
        for episode, line in zip(
            (referenced_episode, missing_episode),
            source.episodes_raw.splitlines(),
            strict=True,
        )
    }
    identity = selector.prereg.SELECTOR_RULE["required_truth_receipts"]["konseki"][
        "subject_identity"
    ]
    absent_reference = selector.context_bridge._reference(
        owner={
            "schema": "options.signal_episode/v1",
            "id": referenced_episode["episode_id"],
            "record_sha256": hashlib.sha256(
                raw_by_episode[referenced_episode["episode_id"]]
            ).hexdigest(),
            "ticker": referenced_episode["ticker"],
            "event_time": referenced_episode["event_time"],
            "requested_as_of": referenced_episode["available_at"],
            "requested_as_of_basis": "durable_available_at",
            "evidence_phase": "decision_time_actual_output",
        },
        subject={
            "subject_id": identity["subject_id"],
            "instrument_id": identity["instrument_id"],
        },
        identity_config_sha256=identity["identity_config_sha256"],
        disposition="abstained",
        reason="exact_requested_as_of_context_absent",
        context=None,
    )
    w1a_root = tmp_path / "absence-w1a-receipts"
    _publish_w1a(w1a_root, [absent_reference])
    selector_root = tmp_path / "absence-selector"
    head = _commit_first(selector_root, source)
    manifest = selector._load_pointer(
        selector_root, head["pending_manifest"], label="absence manifest"
    )
    assert manifest["candidate_count"] == 2
    inputs = selector.EvidenceInputs(w1a_receipt_root=w1a_root)
    plan = selector.plan_cycle(
        root=selector_root,
        source=_pinned_source(source, head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    source_receipt = next(
        item.value
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_w1a_source_receipt/v1"
    )
    descriptor_by_owner = {
        item["owner_id"]: item for item in source_receipt["descriptors"]
    }
    referenced_descriptor = descriptor_by_owner[referenced_episode["episode_id"]]
    missing_descriptor = descriptor_by_owner[missing_episode["episode_id"]]
    assert referenced_descriptor["reference_ordinal"] == 1
    assert referenced_descriptor["reference_id"] == absent_reference["reference_id"]
    assert referenced_descriptor["reference_sha256"] == hashlib.sha256(
        selector.canonical_bytes(absent_reference)
    ).hexdigest()
    assert missing_descriptor["reference_ordinal"] is None
    assert missing_descriptor["reference_id"] is None
    assert missing_descriptor["reference_sha256"] is None

    committed = selector.commit_cycle(selector_root, plan)
    _authenticated, decisions, _body = selector.authenticate_store(
        selector_root, evidence_inputs=inputs
    )
    assert _authenticated == committed
    decision_by_owner: dict[str, dict] = {}
    for decision in decisions:
        candidate = selector._load_pointer(
            selector_root, decision["candidate"], label="absence decided candidate"
        )
        assert candidate["campaign_row"]["evidence_phase"] == (
            "prospective_after_rule_freeze"
        )
        decision_by_owner[candidate["final_episode_row"]["episode_id"]] = decision
    referenced_decision = decision_by_owner[referenced_episode["episode_id"]]
    missing_decision = decision_by_owner[missing_episode["episode_id"]]
    assert referenced_decision["evidence"]["konseki"] is not None
    assert "KONSEKI_EXACT_ASOF_CONTEXT_ABSENT" in referenced_decision["reason_codes"]
    assert (
        "KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED"
        not in referenced_decision["reason_codes"]
    )
    compact = selector._load_pointer(
        selector_root,
        referenced_decision["evidence"]["konseki"],
        label="exact-asof compact Konseki evidence",
    )
    assert compact["reference_ordinal"] == 1
    assert compact["reference_id"] == absent_reference["reference_id"]
    assert missing_decision["evidence"]["konseki"] is None
    assert "KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED" in missing_decision[
        "reason_codes"
    ]
    assert "KONSEKI_EXACT_ASOF_CONTEXT_ABSENT" not in missing_decision[
        "reason_codes"
    ]


def test_w1a_five_megabyte_publication_projects_only_manifest_descriptors(
    tmp_path: Path,
) -> None:
    identities = sorted(
        (
            _stable_id(
                "osep",
                "options.signal_episode/v1",
                "live_flow.notable_contract",
                f"edge-{index}",
            ),
            f"edge-{index}",
        )
        for index in range(20_000)
    )
    chosen = (identities[0], identities[len(identities) // 2], identities[-1])
    episodes = [
        _episode(
            source_event_id,
            "2026-08-12T13:31:00Z",
            strike=700.0 + ordinal,
        )
        for ordinal, (_episode_id, source_event_id) in enumerate(chosen)
    ]
    source = _source([[episode] for episode in episodes])
    source_hashes = {
        episode["episode_id"]: hashlib.sha256(line).hexdigest()
        for episode, line in zip(
            episodes, source.episodes_raw.splitlines(), strict=True
        )
    }
    max_owner = (1 << 96) - 1
    dummy_ids = {
        f"osep_{(index * max_owner // 1198):024x}"
        for index in range(1, 1198)
    } - set(source_hashes)
    references = [
        _bound_w1a_reference(
            owner_id=owner_id,
            record_sha256=(
                source_hashes.get(owner_id)
                or hashlib.sha256(owner_id.encode("utf-8")).hexdigest()
            ),
            padding_items=30,
        )
        for owner_id in sorted(dummy_ids | set(source_hashes))
    ]
    reference_body = selector.context_bridge.canonical_reference_set_bytes(
        references
    )
    assert 5 * 1024 * 1024 <= len(reference_body) <= 8 * 1024 * 1024
    w1a_root = tmp_path / "large-w1a-receipts"
    _publish_w1a(w1a_root, references)
    selector_root = tmp_path / "large-w1a-selector"
    head = _commit_first(selector_root, source)
    plan = selector.plan_cycle(
        root=selector_root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(w1a_receipt_root=w1a_root),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    source_receipt = next(
        item
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_w1a_source_receipt/v1"
    )
    assert len(source_receipt.body) < 32 * 1024
    assert "references" not in source_receipt.value
    descriptors = source_receipt.value["descriptors"]
    manifest = selector._load_pointer(
        selector_root, head["pending_manifest"], label="large W1A manifest"
    )
    assert [item["candidate"] for item in descriptors] == manifest["candidates"]
    ordinal_by_owner = {
        item["owner_id"]: item["reference_ordinal"] for item in descriptors
    }
    edge_owner_ids = [item[0] for item in chosen]
    assert ordinal_by_owner[edge_owner_ids[0]] is not None
    assert ordinal_by_owner[edge_owner_ids[0]] <= 3
    assert 500 <= ordinal_by_owner[edge_owner_ids[1]] <= 700
    assert ordinal_by_owner[edge_owner_ids[2]] >= len(references) - 2


def test_first_observed_revision_is_frozen_and_settled_exactly_once(
    tmp_path: Path,
) -> None:
    first = _episode("first-revision", "2026-08-12T13:31:00Z")
    second = _episode("second-revision", "2026-08-12T13:32:00Z")
    source = _revised_source(first, second)
    root = tmp_path / "selector"
    head = _commit_first(root, source)
    assert head["candidate_count"] == 1
    candidate = selector._load_pointer(
        root, head["last_candidate"], label="test candidate"
    )
    assert (
        candidate["campaign_revision_id"]
        == json.loads(source.campaigns_raw.splitlines()[0])["campaign_revision_id"]
    )

    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    head = selector.commit_cycle(root, plan)
    decisions = _decision_rows(root)
    assert len(decisions) == 1
    assert decisions[0]["candidate"]["id"] == candidate["candidate_id"]
    assert decisions[0]["action"] == "abstain"
    assert decisions[0]["reason_codes"] == [
        "KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED",
        "MARK_RECEIPT_MISSING_OR_MISMATCHED",
        "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
    ]
    cycle = _last_cycle(root, head)
    assert cycle["exactly_one_reconciled"] is True
    assert cycle["decision_count"] == 1
    cycles = _cycle_rows(root, head)
    assert head["cycle_count"] == 2
    assert head["generation"] >= head["cycle_count"]
    assert [row["ordinal"] for row in cycles] == [1, 2]
    assert cycles[0]["previous_cycle"] is None
    handoff_rows = _handoff_rows(root, head)
    assert len(handoff_rows) == head["handoff_queue_count"] == 2
    assert cycles[1]["previous_cycle"] == handoff_rows[0]["selector_cycle"]
    assert head["last_cycle"] == handoff_rows[-1]["selector_cycle"]
    assert [row["ordinal"] for row in handoff_rows] == [1, 2]
    assert handoff_rows[0]["previous_queue_item_id"] is None
    assert handoff_rows[0]["previous_queue_item"] is None
    assert handoff_rows[0]["previous_cycle"] is None
    assert handoff_rows[1]["previous_queue_item_id"] == handoff_rows[0]["queue_item_id"]
    assert handoff_rows[1]["previous_queue_item"] == selector._pointer_for(
        selector._handoff_queue_key(1), handoff_rows[0]
    )
    assert handoff_rows[1]["previous_cycle"] == handoff_rows[0]["selector_cycle"]
    assert head["last_handoff_queue"] == selector._pointer_for(
        selector._handoff_queue_key(2), handoff_rows[-1]
    )


@pytest.mark.parametrize("publish_together", [True, False])
def test_ineligible_revision_one_then_eligible_revision_two_is_first_candidate(
    tmp_path: Path, publish_together: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercise the generic boundary mechanic with a later same-session fence;
    # the registered v1 fence itself equals the opening bell, so every valid
    # same-session producer row is naturally post-fence.
    monkeypatch.setattr(
        selector, "SELECTOR_EFFECTIVE_FREEZE_AT", "2026-08-12T13:30:30Z"
    )
    first = _episode("pre-selector-freeze", "2026-08-12T13:30:01Z")
    second = _episode("post-selector-freeze", "2026-08-12T13:31:00Z")
    full = _revised_source(
        first,
        second,
        observed_at=(
            "2026-08-12T14:00:00Z"
            if publish_together
            else "2026-08-12T14:05:00Z"
        ),
    )
    root = tmp_path / ("same-blob" if publish_together else "cross-blob")
    if publish_together:
        head = _commit_first(root, full)
    else:
        before = _source([[first]], observed_at="2026-08-12T14:00:00Z")
        initial = _commit_first(root, before)
        assert initial["candidate_count"] == 0
        head = _commit_first(root, full, scheduled_at="2026-08-12T14:05:00Z")
    candidate = selector._load_pointer(
        root, head["last_candidate"], label="eligible revision two candidate"
    )
    revisions = [json.loads(line) for line in full.campaigns_raw.splitlines()]
    assert candidate["campaign_revision_id"] == revisions[1]["campaign_revision_id"]
    assert candidate["campaign_row"]["revision_number"] == 2
    assert head["candidate_count"] == 1


def test_episode_then_campaign_split_publication_admits_exact_prior_episode(
    tmp_path: Path,
) -> None:
    episode = _episode("split-publication", "2026-08-12T13:31:00Z")
    episode_raw = campaign_engine.canonical_bytes(episode) + b"\n"
    episode_only = _snapshot_with_checkpoint(
        commit="a" * 40,
        campaigns_raw=b"",
        episodes_raw=episode_raw,
        observed_at="2026-08-12T14:00:00Z",
    )
    root = tmp_path / "split-publication"
    first_head = _commit_first(root, episode_only)
    assert first_head["candidate_count"] == 0

    full = _source([[episode]], observed_at="2026-08-12T14:05:00Z", commit="b" * 40)
    head = _commit_first(root, full, scheduled_at="2026-08-12T14:05:00Z")
    candidate = selector._load_pointer(
        root, head["last_candidate"], label="split publication candidate"
    )
    assert candidate["final_episode_row"]["episode_id"] == episode["episode_id"]
    assert candidate["final_episode_row_sha256"] == hashlib.sha256(
        campaign_engine.canonical_bytes(episode)
    ).hexdigest()


def test_manifest_segments_drain_unchanged_blob_without_stranding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(selector, "MAX_CANDIDATES_PER_MANIFEST", 2)
    source = _source(
        [
            [_episode(f"segment-{strike}", "2026-08-12T13:31:00Z", strike=strike)]
            for strike in (700.0, 701.0, 702.0)
        ]
    )
    root = tmp_path / "segmented-manifest"
    first = _commit_first(root, source)
    assert first["candidate_count"] == 2
    assert first["source_ready_cursor"] == 2
    assert first["source_campaign_prefix"]["records"] == 3

    second_plan = selector.plan_cycle(
        root=root,
        source=selector.SourceSnapshot(
            commit=source.commit,
            campaigns_raw=source.campaigns_raw,
            episodes_raw=source.episodes_raw,
            observed_at="2026-08-12T14:05:00Z",
            campaigns_blob_oid=first["source_campaign_prefix"]["git_blob_oid"],
            episodes_blob_oid=first["source_episode_prefix"]["git_blob_oid"],
        ),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    second = selector.commit_cycle(root, second_plan)
    assert second["candidate_count"] == 3
    assert second["source_campaign_cursor_records"] == 3
    assert len(_decision_rows(root)) == 2

    third_plan = selector.plan_cycle(
        root=root,
        source=selector.SourceSnapshot(
            commit=source.commit,
            campaigns_raw=None,
            episodes_raw=None,
            observed_at="2026-08-12T14:10:00Z",
            campaigns_blob_oid=second["source_campaign_prefix"]["git_blob_oid"],
            episodes_blob_oid=second["source_episode_prefix"]["git_blob_oid"],
        ),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:10:00Z",
        clock=_clock("2026-08-12T14:10:00Z"),
        runtime_armed=True,
    )
    third = selector.commit_cycle(root, third_plan)
    assert third["candidate_count"] == 3
    assert len(_decision_rows(root)) == 3


def test_manifest_segments_pin_first_blob_clock_and_drain_bodyless_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(selector, "MAX_CANDIDATES_PER_MANIFEST", 1)
    source = _source(
        [
            [_episode(f"projection-{strike}", "2026-08-12T13:31:00Z", strike=strike)]
            for strike in (710.0, 711.0, 712.0)
        ],
        observed_at="2026-08-12T14:00:00Z",
        commit="a" * 40,
    )
    root = tmp_path / "source-projection"
    first = _commit_first(root, source)
    assert first["source_projection_next"] is not None

    second_plan = selector.plan_cycle(
        root=root,
        source=selector.SourceSnapshot(
            # A later runner clock/commit cannot change first observation for
            # the already-audited immutable blob.
            commit="b" * 40,
            campaigns_raw=None,
            episodes_raw=None,
            observed_at="2026-08-12T14:05:00Z",
            campaigns_blob_oid=first["source_campaign_prefix"]["git_blob_oid"],
            episodes_blob_oid=first["source_episode_prefix"]["git_blob_oid"],
        ),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    second = selector.commit_cycle(root, second_plan)
    second_candidate = selector._load_pointer(
        root, second["last_candidate"], label="projected second candidate"
    )
    assert second_candidate["candidate_available_at"] == "2026-08-12T14:00:00Z"
    assert second_candidate["source_commit"] == "a" * 40
    assert second["source_observed_at"] == "2026-08-12T14:00:00Z"
    assert second["source_commit"] == "a" * 40

    third_plan = selector.plan_cycle(
        root=root,
        source=selector.SourceSnapshot(
            commit="c" * 40,
            campaigns_raw=None,
            episodes_raw=None,
            observed_at="2026-08-12T14:10:00Z",
            campaigns_blob_oid=second["source_campaign_prefix"]["git_blob_oid"],
            episodes_blob_oid=second["source_episode_prefix"]["git_blob_oid"],
        ),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:10:00Z",
        clock=_clock("2026-08-12T14:10:00Z"),
        runtime_armed=True,
    )
    third = selector.commit_cycle(root, third_plan)
    assert third["source_campaign_cursor_records"] == 3
    assert third["source_projection_next"] is None
    candidates = selector._walk_immutable_chain(
        root,
        tail=third["last_candidate"],
        count=third["candidate_count"],
        schema="options.sparse_selector_candidate/v1",
        previous_field="previous_candidate",
        namespace="candidates",
        label="test candidates",
    )
    assert {item["candidate_available_at"] for item in candidates} == {
        "2026-08-12T14:00:00Z"
    }
    assert {item["source_commit"] for item in candidates} == {"a" * 40}


def test_source_observation_rollback_and_duplicate_slot_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([[_episode("clock", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "clock"
    head = _commit_first(root, source)
    rolled_back = copy.copy(source)
    object.__setattr__(rolled_back, "observed_at", "2026-08-12T13:59:59Z")
    with pytest.raises(selector.SparseSelectorError, match="moved backward"):
        selector.plan_cycle(
            root=root,
            source=rolled_back,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="2026-08-12T14:05:00Z",
            clock=_clock("2026-08-12T14:05:00Z"),
            runtime_armed=True,
        )
    with pytest.raises(selector.SparseSelectorError, match="strictly"):
        selector.plan_cycle(
            root=root,
            source=source,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="2026-08-12T14:00:00Z",
            clock=_clock("2026-08-12T14:00:00Z"),
            runtime_armed=True,
        )

    before = sorted(path.relative_to(root) for path in root.rglob("*"))
    monkeypatch.setattr(selector, "SELECTOR_RUNTIME_ARMED", True)
    adopted = selector.advance(
        private_root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock("2026-08-12T14:00:00Z"),
    )
    after = sorted(path.relative_to(root) for path in root.rglob("*"))
    assert adopted == head
    assert after == before


def test_legacy_selector_ledger_without_head_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir(mode=0o700)
    legacy = root / "decisions.jsonl"
    legacy.write_bytes(b"{}\n")
    legacy.chmod(0o600)
    with pytest.raises(selector.SparseSelectorError, match="legacy evidence"):
        selector.status(root)


def test_deleted_non_tail_candidate_index_path_refuses_conflicting_readmission(
    tmp_path: Path,
) -> None:
    source = _source(
        [
            [_episode("indexed-a", "2026-08-12T13:31:00Z", strike=700.0)],
            [_episode("indexed-b", "2026-08-12T13:31:01Z", strike=701.0)],
        ]
    )
    root = tmp_path / "candidate-index-delete"
    head = _commit_first(root, source)
    first_pointer = _last_cycle(root, head)["candidate_pointers"][0]
    first = selector._load_pointer(root, first_pointer, label="first indexed candidate")
    result = selector._candidate_index_lookup(
        root, head["candidate_index"], first["campaign_id"]
    )
    assert result.found and result.terminal is not None
    leaf_path = selector._object_path(
        root, selector.private_auth_dict.pointer(result.terminal)["key"]
    )
    leaf_path.unlink()
    with pytest.raises(selector.SparseSelectorError, match="missing"):
        selector._candidate_index_lookup(
            root, head["candidate_index"], first["campaign_id"]
        )
    # A direct exact-key lookup is UNKNOWN/failure, never non-membership. The
    # next changed-source cycle will execute the same authoritative lookup;
    # unchanged sources do not need a candidate membership query.


def test_authenticate_store_rejects_rehashed_non_tail_candidate_index_misbinding(
    tmp_path: Path,
) -> None:
    source = _source(
        [
            [_episode("index-chain-a", "2026-08-12T13:31:00Z", strike=700.0)],
            [_episode("index-chain-b", "2026-08-12T13:31:01Z", strike=701.0)],
        ]
    )
    root = tmp_path / "candidate-index-chain"
    head = _commit_first(root, source)
    receipts = selector._walk_candidate_chain_receipts(
        root,
        tail=head["last_candidate"],
        count=head["candidate_count"],
    )
    first, tail = receipts[0], receipts[-1]
    forged_root, nodes = selector.private_auth_dict.sharded_insert_many(
        head["candidate_index"],
        [
            (
                selector._candidate_index_key(first["campaign_id"]),
                {
                    "campaign_id": first["campaign_id"],
                    "candidate_id": tail["candidate_id"],
                    "candidate": tail["pointer"],
                },
            )
        ],
        domain=selector.CANDIDATE_INDEX_DOMAIN,
        load_node=lambda pointer: selector._load_candidate_index_node(root, pointer),
        replace_existing=True,
    )
    for node in nodes:
        path = selector._object_path(
            root,
            f"{selector.private_auth_dict.NAMESPACE}/{node['node_id']}.json",
        )
        path.write_bytes(selector.canonical_bytes(node))
        path.chmod(0o600)
    corrupted = copy.deepcopy(head)
    corrupted["candidate_index"] = forged_root
    corrupted["head_id"] = selector._content_id(
        "ossh_", corrupted, field="head_id"
    )
    (root / selector.HEAD_FILE).write_bytes(selector.canonical_bytes(corrupted))
    with pytest.raises(selector.SparseSelectorError, match="complete chain"):
        selector.authenticate_store(root)


def test_authenticate_store_rejects_rehashed_proposal_session_counter(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("proposal-head", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "proposal-head"
    head = _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    settled = selector.commit_cycle(root, plan)
    assert settled["proposal_session_date"] == "2026-08-12"
    assert settled["proposal_session_count"] == 0
    corrupted = copy.deepcopy(settled)
    corrupted["proposal_session_date"] = None
    corrupted["head_id"] = selector._content_id(
        "ossh_", corrupted, field="head_id"
    )
    (root / selector.HEAD_FILE).write_bytes(selector.canonical_bytes(corrupted))
    with pytest.raises(selector.SparseSelectorError, match="proposal session state"):
        selector.authenticate_store(root)


@pytest.mark.parametrize("offset_delta", [-1, 1])
def test_source_recovery_rejects_rehashed_noncontiguous_episode_byte_offsets(
    tmp_path: Path, offset_delta: int
) -> None:
    source = _source([[_episode("episode-offset", "2026-08-12T13:31:00Z")]])
    root = tmp_path / f"episode-offset-{offset_delta}"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    forged = copy.deepcopy(plan.intent)
    original = next(
        item
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_episode_chunk/v1"
    )
    chunk = copy.deepcopy(original.value)
    chunk["rows"][0]["end_byte"] += offset_delta
    chunk["last_byte"] += offset_delta
    chunk["chunk_id"] = selector._episode_chunk_id(chunk)
    replacement = selector.PlannedObject(
        key=f"{selector.SOURCE_PROJECTION_NAMESPACE}/{chunk['chunk_id']}.json",
        value=chunk,
    )
    forged["objects"] = sorted(
        [
            replacement.receipt if receipt == original.receipt else receipt
            for receipt in forged["objects"]
        ],
        key=lambda receipt: receipt["key"],
    )
    forged["source_window"]["chunk"] = replacement.pointer
    forged["intent_sha256"] = selector._content_id(
        "", forged, field="intent_sha256"
    )
    with selector._store_lock(root):
        for item in (*plan.objects, replacement):
            selector._prestage_immutable(
                selector._object_path(root, item.key), item.body, root=root
            )
        with pytest.raises(selector.SparseSelectorError, match="chunk row binding"):
            selector._plan_from_intent(root, forged)


def test_advance_recovery_rejects_rehashed_shortened_and_zero_ready_prefixes(
    tmp_path: Path,
) -> None:
    source = _many_candidate_source(129)
    for admission_cap in (64, 0):
        root = tmp_path / f"shortened-ready-prefix-{admission_cap}"
        head: dict | None = None
        for _ in range(16):
            audit_plan = selector.plan_cycle(
                root=root,
                source=source,
                evidence_inputs=selector.EvidenceInputs(),
                scheduled_at="2026-08-12T14:00:00Z",
                clock=_clock(),
                runtime_armed=True,
            )
            head = selector.commit_cycle(root, audit_plan)
            if head["source_phase"] == "READY" and head["cycle_count"] == 0:
                break
        assert head is not None
        assert head["source_phase"] == "READY"
        assert head["cycle_count"] == 0
        pinned = _pinned_source(source, head)
        shortened = selector._plan_cycle_once(
            root=root,
            source=pinned,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="2026-08-12T14:00:00Z",
            clock=_clock(),
            runtime_armed=True,
            admission_cap=admission_cap,
            settlement_cache={},
        )
        cycle = next(
            item.value
            for item in shortened.objects
            if item.value.get("schema")
            == "options.sparse_selector_cycle_receipt/v1"
        )
        assert len(cycle["candidate_pointers"]) == admission_cap
        with selector._store_lock(root):
            for item in shortened.objects:
                selector._prestage_immutable(
                    selector._object_path(root, item.key), item.body, root=root
                )
            with pytest.raises(
                selector.SparseSelectorError,
                match="exact parent replay|authenticated clocks",
            ):
                selector._plan_from_intent(
                    root,
                    shortened.intent,
                    evidence_inputs=selector.EvidenceInputs(),
                )


def test_late_candidate_waits_for_the_following_cycle(
    tmp_path: Path,
) -> None:
    first = _episode("late-a", "2026-08-12T13:31:00Z", strike=700.0)
    second = _episode("late-b", "2026-08-12T13:32:00Z", strike=701.0)
    source_a = _source([[first]])
    source_ab = _append_group_source(
        source_a,
        second,
        observed_at="2026-08-12T14:05:00Z",
    )
    root = tmp_path / "selector"
    _commit_first(root, source_a)
    second_head = _commit_first(
        root, source_ab, scheduled_at="2026-08-12T14:05:00Z"
    )
    assert len(_decision_rows(root)) == 1
    assert _last_cycle(root, second_head)["next_manifest"] is not None
    assert _last_cycle(root, second_head)["settled_manifest"] is None
    third_plan = selector.plan_cycle(
        root=root,
        source=source_ab,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    selector.commit_cycle(root, third_plan)
    assert len(_decision_rows(root)) == 2


def test_changed_source_epoch_requires_new_clock_and_store_authenticates_global_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_episode = _episode(
        "epoch-first", "2026-08-12T13:31:00Z", strike=700.0
    )
    first = _source(
        [[first_episode]],
        observed_at="2026-08-12T14:00:00Z",
        commit="a" * 40,
    )
    second_episode = _episode(
        "epoch-second-3", "2026-08-12T13:32:00Z", strike=703.0
    )
    combined = _source(
        [[first_episode], [second_episode]],
        observed_at="2026-08-12T14:00:00Z",
        commit="b" * 40,
    )
    second_row = combined.campaigns_raw.splitlines()[1] + b"\n"
    equal_clock_append = _snapshot_with_checkpoint(
        commit="b" * 40,
        campaigns_raw=first.campaigns_raw + second_row,
        episodes_raw=combined.episodes_raw,
        observed_at="2026-08-12T14:00:00Z",
    )
    root = tmp_path / "source-epoch-order"
    first_head = _commit_first(root, first)
    assert first_head["candidate_count"] == 1
    settle_plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(first, first_head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    first_head = selector.commit_cycle(root, settle_plan)
    assert first_head["source_phase"] == "DRAINED"

    with pytest.raises(
        selector.SparseSelectorError,
        match="new selector source epoch did not advance its observation clock",
    ):
        selector.plan_cycle(
            root=root,
            source=equal_clock_append,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="2026-08-12T14:10:00Z",
            clock=_clock("2026-08-12T14:10:00Z"),
            runtime_armed=True,
        )
    assert selector.authenticate_store(root)[0] == first_head

    fractional_clock_append = _snapshot_with_checkpoint(
        commit="b" * 40,
        campaigns_raw=equal_clock_append.campaigns_raw,
        episodes_raw=equal_clock_append.episodes_raw,
        observed_at="2026-08-12T14:00:00.000001Z",
    )
    with pytest.raises(
        selector.SparseSelectorError,
        match="new selector source epoch does not sort after its candidate tail",
    ):
        selector.plan_cycle(
            root=root,
            source=fractional_clock_append,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="2026-08-12T14:10:00Z",
            clock=_clock("2026-08-12T14:10:00Z"),
            runtime_armed=True,
        )
    assert selector.authenticate_store(root)[0] == first_head

    later_clock_append = _snapshot_with_checkpoint(
        commit="b" * 40,
        campaigns_raw=equal_clock_append.campaigns_raw,
        episodes_raw=equal_clock_append.episodes_raw,
        observed_at="2026-08-12T14:05:00Z",
    )
    make_candidate = selector._candidate_from_seed

    def force_nonmonotone_candidate(
        seed: dict,
        *,
        ordinal: int,
        previous_candidate: dict | None,
    ) -> dict:
        candidate = make_candidate(
            seed,
            ordinal=ordinal,
            previous_candidate=previous_candidate,
        )
        if ordinal == 2:
            candidate["candidate_available_at"] = "2026-08-12T13:59:59Z"
            candidate = selector.validate_runtime_object(
                candidate, label="forced nonmonotone candidate"
            )
        return candidate

    monkeypatch.setattr(selector, "_candidate_from_seed", force_nonmonotone_candidate)
    corrupted = _commit_first(
        root,
        later_clock_append,
        scheduled_at="2026-08-12T14:10:00Z",
    )
    assert corrupted["candidate_count"] == 2
    with pytest.raises(
        selector.SparseSelectorError,
        match="selector candidate chain is not globally ordered",
    ):
        selector.authenticate_store(root)


def test_passing_order_applies_three_proposal_cap_without_ranking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = [
        [_episode(f"cap-{strike}", "2026-08-12T13:31:00Z", strike=float(strike))]
        for strike in (700, 701, 702, 703)
    ]
    source = _source(groups)
    root = tmp_path / "selector"
    runtime_head = _commit_first(root, source)
    evidence_inputs, complete_head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, complete_head),
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    selector.commit_cycle(root, plan)
    rows = _decision_rows(root, evidence_inputs=evidence_inputs)
    assert [row["action"] for row in rows] == [
        "propose",
        "propose",
        "propose",
        "abstain",
    ]
    assert [row["proposal_ordinal"] for row in rows] == [1, 2, 3, None]
    assert rows[-1]["reason_codes"] == ["SESSION_PROPOSAL_CAP_REACHED"]
    assert all(row["authority"] == selector.FALSE_AUTHORITY for row in rows)
    assert len(
        {
            selector.canonical_bytes(row["evidence"]["generation"])
            for row in rows
        }
    ) == 1


def test_authenticate_store_caches_generation_and_w1a_by_full_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(
        [
            [_episode(f"cache-{strike}", "2026-08-12T13:31:00Z", strike=strike)]
            for strike in (700.0, 701.0, 702.0, 703.0)
        ]
    )
    root = tmp_path / "generation-cache"
    runtime_head = _commit_first(root, source)
    inputs, complete_head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, complete_head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    committed = selector.commit_cycle(root, plan, evidence_inputs=inputs)
    planned_decisions = sorted(
        (
            item.value
            for item in plan.objects
            if item.value.get("schema")
            == "options.sparse_selector_decision/v1"
        ),
        key=lambda row: row["ordinal"],
    )
    assert len(planned_decisions) == 4
    unique_generations = {
        selector.canonical_bytes(row["evidence"]["generation"])
        for row in planned_decisions
    }
    unique_sources = {
        selector.canonical_bytes(
            next(
                item.value["w1a_source_receipt"]
                for item in plan.objects
                if item.value.get("schema")
                == "options.sparse_selector_evidence_generation/v1"
            )
        )
    }
    unique_manifests = {
        selector.canonical_bytes(item.value["settled_manifest"])
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_generation/v1"
    }
    real_load_pointer = selector._load_pointer
    real_validate_runtime_object = selector.validate_runtime_object
    real_w1a_auth = selector._authenticate_historical_w1a_source
    loads = {
        "generation": 0,
        "generation_validation": 0,
        "manifest": 0,
        "source": 0,
        "w1a": 0,
    }

    def counted_load_pointer(
        current_root: Path,
        pointer: dict,
        *,
        label: str,
    ) -> dict:
        if label in {
            "authenticated evidence generation",
            "decision evidence generation",
        }:
            loads["generation"] += 1
        if label in {
            "captured selector W1A source receipt",
            "decision W1A source receipt",
            "authenticated selector W1A source receipt",
        }:
            loads["source"] += 1
        if selector.canonical_bytes(pointer) in unique_manifests:
            loads["manifest"] += 1
        return real_load_pointer(current_root, pointer, label=label)

    def counted_validate_runtime_object(value: dict, *, label: str) -> dict:
        if (
            value.get("schema")
            == "options.sparse_selector_evidence_generation/v1"
        ):
            loads["generation_validation"] += 1
        return real_validate_runtime_object(value, label=label)

    def counted_w1a_auth(*args, **kwargs):
        loads["w1a"] += 1
        return real_w1a_auth(*args, **kwargs)

    monkeypatch.setattr(selector, "_load_pointer", counted_load_pointer)
    monkeypatch.setattr(
        selector, "validate_runtime_object", counted_validate_runtime_object
    )
    monkeypatch.setattr(
        selector, "_authenticate_historical_w1a_source", counted_w1a_auth
    )
    for call in (1, 2):
        authenticated, decisions, _body = selector.authenticate_store(
            root, evidence_inputs=inputs
        )
        assert authenticated == committed
        assert len(decisions) == 4
        assert loads == {
            "generation": call * len(unique_generations),
            "generation_validation": call * len(unique_generations),
            "manifest": call * len(unique_manifests),
            "source": call * len(unique_sources),
            "w1a": call * len(unique_generations),
        }

    decision = planned_decisions[0]
    candidate = real_load_pointer(
        root, decision["candidate"], label="cached-pointer candidate"
    )
    for field, forged_value in (
        ("key", f"evidence/{'0' * 64}.json"),
        ("sha256", "0" * 64),
        ("bytes", decision["evidence"]["generation"]["bytes"] + 1),
    ):
        generation_cache: selector._PointerObjectCache = {}
        source_cache: selector._PointerObjectCache = {}
        w1a_cache: selector._W1APublicationCache = {}
        selector._validate_decision_evidence_objects(
            root,
            decision,
            candidate=candidate,
            evidence_inputs=inputs,
            generation_cache=generation_cache,
            source_cache=source_cache,
            w1a_cache=w1a_cache,
        )
        forged = copy.deepcopy(decision)
        forged["evidence"]["generation"][field] = forged_value
        with pytest.raises(
            selector.SparseSelectorError,
            match="cached full pointer drifted",
        ):
            selector._validate_decision_evidence_objects(
                root,
                forged,
                candidate=candidate,
                evidence_inputs=inputs,
                generation_cache=generation_cache,
                source_cache=source_cache,
                w1a_cache=w1a_cache,
            )


def test_authenticate_store_caches_settled_manifest_by_full_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(
        [
            [_episode(f"manifest-cache-{strike}", "2026-08-12T13:31:00Z", strike=strike)]
            for strike in (700.0, 701.0, 702.0, 703.0)
        ]
    )
    root = tmp_path / "manifest-cache"
    first_head = _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, first_head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    committed = selector.commit_cycle(root, plan)
    decisions = sorted(
        (
            item.value
            for item in plan.objects
            if item.value.get("schema")
            == "options.sparse_selector_decision/v1"
        ),
        key=lambda row: row["ordinal"],
    )
    generations = [
        item
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_generation/v1"
    ]
    assert len(decisions) == 4
    assert len(generations) == 1
    manifest_pointers = {
        selector.canonical_bytes(item.value["settled_manifest"])
        for item in generations
    }
    real_load_pointer = selector._load_pointer
    manifest_loads = 0

    def counted_load_pointer(
        current_root: Path,
        pointer: dict,
        *,
        label: str,
    ) -> dict:
        nonlocal manifest_loads
        if selector.canonical_bytes(pointer) in manifest_pointers:
            manifest_loads += 1
        return real_load_pointer(current_root, pointer, label=label)

    monkeypatch.setattr(selector, "_load_pointer", counted_load_pointer)
    authenticated, authenticated_decisions, _body = selector.authenticate_store(root)
    assert authenticated == committed
    assert len(authenticated_decisions) == len(decisions)
    assert manifest_loads == len(manifest_pointers)

    decision = decisions[0]
    generation = generations[0]
    candidate = real_load_pointer(
        root, decision["candidate"], label="manifest-cache candidate"
    )
    manifest_cache: selector._PointerObjectCache = {}
    selector._validate_decision_evidence_objects(
        root,
        decision,
        candidate=candidate,
        evidence_inputs=selector.EvidenceInputs(),
        generation_cache={},
        manifest_cache=manifest_cache,
    )
    for field, forged_value in (
        ("key", f"manifests/ossm_{'0' * 64}.json"),
        ("sha256", "0" * 64),
        ("bytes", generation.value["settled_manifest"]["bytes"] + 1),
    ):
        forged_generation = copy.deepcopy(generation.value)
        forged_generation["settled_manifest"][field] = forged_value
        forged_generation["generation_id"] = selector._content_id(
            "osseg_", forged_generation, field="generation_id"
        )
        forged_generation = selector.validate_runtime_object(
            forged_generation, label="forged manifest-cache generation"
        )
        forged_generation_item = selector._evidence_object(forged_generation)
        forged_decision = copy.deepcopy(decision)
        forged_decision["evidence"]["generation"] = forged_generation_item.pointer
        with pytest.raises(
            selector.SparseSelectorError,
            match="settled manifest cached full pointer drifted",
        ):
            selector._validate_decision_evidence_objects(
                root,
                forged_decision,
                planned_by_key={
                    forged_generation_item.key: forged_generation_item,
                },
                candidate=candidate,
                evidence_inputs=selector.EvidenceInputs(),
                generation_cache={},
                manifest_cache=manifest_cache,
            )


@pytest.mark.parametrize(
    "stage",
    [
        "after_intent",
        "after_objects",
        "after_ledger",
        "after_handoff_queue",
        "after_head",
    ],
)
def test_crash_recovery_adopts_only_exact_before_or_after_state(
    tmp_path: Path,
    stage: str,
) -> None:
    source = _source([[_episode(f"crash-{stage}", "2026-08-12T13:31:00Z")]])
    root = tmp_path / stage
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == stage:
            raise RuntimeError("simulated power loss")

    with pytest.raises(RuntimeError, match="power loss"):
        selector.commit_cycle(root, plan, hook=crash)
    assert (root / selector.INTENT_FILE).exists()
    recovered = selector.commit_cycle(root, None)
    assert recovered == plan.head
    assert not (root / selector.INTENT_FILE).exists()
    assert selector.authenticate_store(root)[0] == plan.head
    if recovered["cycle_count"]:
        assert (
            _handoff_rows(root, recovered)[-1]["selector_cycle"]
            == recovered["last_cycle"]
        )
    else:
        assert recovered["source_phase"] == "AUDITING"


def test_handoff_queue_recovery_rejects_conflicting_immutable_ordinal_object(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("queue-corruption", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "queue-corruption"
    _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == "after_handoff_queue":
            raise RuntimeError("simulated power loss")

    with pytest.raises(RuntimeError, match="power loss"):
        selector.commit_cycle(root, plan, hook=crash)
    queue_path = selector._object_path(root, plan.head["last_handoff_queue"]["key"])
    queue_path.write_bytes(queue_path.read_bytes() + b"{}\n")
    with pytest.raises(
        selector.SparseSelectorError,
        match="object receipt differs from prestaged bytes",
    ):
        selector.commit_cycle(root, None)


def test_handoff_queue_tail_walk_is_pending_linear_and_never_rewrites_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([])
    root = tmp_path / "constant-work"
    head = _commit_first(root, source)
    first_queue_path = selector._object_path(root, head["last_handoff_queue"]["key"])
    first_queue_bytes = first_queue_path.read_bytes()
    first_queue_inode = first_queue_path.stat().st_ino
    cycle_pointers = [head["last_cycle"]]
    queue_pointers = [head["last_handoff_queue"]]
    base = datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc)
    for offset in range(1, 64):
        instant = base + timedelta(minutes=5 * offset)
        plan = selector.plan_cycle(
            root=root,
            source=source,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at=selector.utc_text(instant),
            clock=lambda instant=instant: instant,
            runtime_armed=True,
        )
        assert len(plan.objects) <= selector.MAX_SOURCE_OBJECTS_PER_CYCLE
        assert len(selector.canonical_bytes(plan.intent)) <= selector.MAX_INTENT_BYTES
        head = selector.commit_cycle(root, plan)
        cycle_pointers.append(head["last_cycle"])
        queue_pointers.append(head["last_handoff_queue"])

    assert "cycle_index" not in head
    assert "handoff_queue_sha256" not in head
    assert head["cycle_count"] == head["handoff_queue_count"] == 64
    assert first_queue_path.read_bytes() == first_queue_bytes
    assert first_queue_path.stat().st_ino == first_queue_inode

    reads: list[Path] = []
    original_read = selector._read_private_file

    def counted_read(path: Path, **kwargs):
        reads.append(path)
        return original_read(path, **kwargs)

    monkeypatch.setattr(selector, "_read_private_file", counted_read)
    pending = selector.authenticated_pending_handoff_queue(
        root,
        head,
        after_ordinal=32,
        after_cycle_id=cycle_pointers[31]["id"],
        after_cycle_pointer=cycle_pointers[31],
        after_queue_item_id=queue_pointers[31]["id"],
        after_queue_item_pointer=queue_pointers[31],
    )
    assert [record["item"]["ordinal"] for record in pending] == list(range(33, 65))
    assert pending[-1]["pointer"] == head["last_handoff_queue"]
    assert len(reads) == 1 + 2 * 32
    assert reads[0].name == "HEAD.json"
    assert [path.name for path in reads[1:5]] == [
        cycle_pointers[-1]["key"].split("/")[-1],
        "00000000000000000064.json",
        "00000000000000000063.json",
        cycle_pointers[-2]["key"].split("/")[-1],
    ]


def test_handoff_queue_exact_cap_reads_are_bounded_and_corruption_fails_when_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([])
    root = tmp_path / "exact-cap"
    head = _commit_first(root, source)
    queue_dir = root / selector.HANDOFF_QUEUE_NAMESPACE
    cycle_dir = root / "cycles"
    cycle_template = selector._load_pointer(
        root, head["last_cycle"], label="exact-cap cycle template"
    )
    cursors: dict[int, dict[str, dict]] = {}
    previous_cycle = None
    previous_queue = None
    last_item = None
    queue_values: dict[int, dict] = {}
    horizon = selector.QUEUE_WALK_TEST_HORIZON
    for ordinal in range(1, horizon + 1):
        cycle = copy.deepcopy(cycle_template)
        cycle.update(
            ordinal=ordinal,
            previous_head_id=(
                None
                if ordinal == 1
                else "ossh_"
                + hashlib.sha256(f"head:{ordinal - 1}".encode()).hexdigest()
            ),
            previous_cycle=previous_cycle,
        )
        cycle["cycle_id"] = selector._cycle_id(
            ordinal=ordinal,
            scheduled_at=cycle["scheduled_at"],
            started_at=cycle["started_at"],
            source_commit=cycle["source_commit"],
            previous_head_id=cycle["previous_head_id"],
        )
        cycle = selector.validate_runtime_object(cycle, label="exact-cap cycle")
        cycle_key = f"cycles/{cycle['cycle_id']}.json"
        cycle_path = cycle_dir / f"{cycle['cycle_id']}.json"
        cycle_path.write_bytes(selector.canonical_bytes(cycle))
        cycle_path.chmod(0o600)
        cycle_pointer = selector._pointer_for(cycle_key, cycle)
        skips = [] if previous_queue is None else [previous_queue]
        for level in range(1, (ordinal - 1).bit_length()):
            source_ordinal = ordinal - (1 << (level - 1))
            skips.append(
                copy.deepcopy(queue_values[source_ordinal]["skip_queue_items"][level - 1])
            )
        item = {
            "schema": "options.sparse_selector_handoff_queue_item/v1",
            "queue_item_id": "",
            "ordinal": ordinal,
            "previous_queue_item_id": (
                None if previous_queue is None else previous_queue["id"]
            ),
            "previous_queue_item": previous_queue,
            "skip_queue_items": skips,
            "previous_cycle": previous_cycle,
            "selector_cycle": cycle_pointer,
            "runtime_armed": True,
            "producer_rule_sha256": selector.SELECTOR_RULE_SHA256,
            "authority": dict(selector.FALSE_AUTHORITY),
        }
        item["queue_item_id"] = selector._handoff_queue_item_id(item)
        queue_path = queue_dir / f"{ordinal:020d}.json"
        queue_path.write_bytes(selector.canonical_bytes(item))
        queue_path.chmod(0o600)
        queue_pointer = selector._pointer_for(
            selector._handoff_queue_key(ordinal), item
        )
        if ordinal in {41, horizon // 2, horizon - 1}:
            cursors[ordinal] = {
                "cycle": copy.deepcopy(cycle_pointer),
                "queue": copy.deepcopy(queue_pointer),
            }
        previous_cycle = cycle_pointer
        previous_queue = queue_pointer
        last_item = item
        queue_values[ordinal] = item

    assert (
        last_item is not None
        and previous_cycle is not None
        and previous_queue is not None
    )
    head.update(
        generation=horizon,
        cycle_count=horizon,
        handoff_queue_count=horizon,
        last_cycle=previous_cycle,
        last_handoff_queue=previous_queue,
    )
    head["head_id"] = selector._content_id("ossh_", head, field="head_id")
    (root / selector.HEAD_FILE).write_bytes(selector.canonical_bytes(head))

    reads: list[Path] = []
    original_read = selector._read_private_file

    def counted_read(path: Path, **kwargs):
        reads.append(path)
        return original_read(path, **kwargs)

    monkeypatch.setattr(selector, "_read_private_file", counted_read)
    first = selector.read_next_handoff_queue_item(
        root,
        head,
        after_ordinal=0,
        after_cycle_id=None,
        after_cycle_pointer=None,
        after_queue_item_id=None,
        after_queue_item_pointer=None,
    )
    middle_ordinal = horizon // 2
    middle = selector.read_next_handoff_queue_item(
        root,
        head,
        after_ordinal=middle_ordinal,
        after_cycle_id=cursors[middle_ordinal]["cycle"]["id"],
        after_cycle_pointer=cursors[middle_ordinal]["cycle"],
        after_queue_item_id=cursors[middle_ordinal]["queue"]["id"],
        after_queue_item_pointer=cursors[middle_ordinal]["queue"],
    )
    terminal = selector.read_next_handoff_queue_item(
        root,
        head,
        after_ordinal=horizon,
        after_cycle_id=previous_cycle["id"],
        after_cycle_pointer=previous_cycle,
        after_queue_item_id=previous_queue["id"],
        after_queue_item_pointer=previous_queue,
    )
    assert first is not None and first["ordinal"] == 1
    assert middle is not None and middle["ordinal"] == middle_ordinal + 1
    assert terminal is None
    # Two next-item reads authenticate logarithmic skip paths from the tail;
    # the terminal check reads only HEAD/tail.  This bound is independent of
    # the 9,828-cycle outage length.
    assert len(reads) <= 2 * (horizon.bit_length() + 5) + 3
    assert [path.name for path in reads[:3]] == [
        "HEAD.json",
        previous_cycle["key"].split("/")[-1],
        f"{horizon:020d}.json",
    ]
    assert reads[-1].name == f"{horizon:020d}.json"

    reads.clear()
    first_batch = selector.authenticated_pending_handoff_queue(
        root,
        head,
        after_ordinal=0,
        after_cycle_id=None,
        after_cycle_pointer=None,
        after_queue_item_id=None,
        after_queue_item_pointer=None,
    )
    assert [record["item"]["ordinal"] for record in first_batch] == list(
        range(1, selector.MAX_HANDOFF_IMPORT_RECORDS + 1)
    )
    assert len(reads) <= (
        horizon.bit_length() + 3 + 2 * selector.MAX_HANDOFF_IMPORT_RECORDS
    )

    missing_ordinal = 42
    (queue_dir / f"{missing_ordinal:020d}.json").unlink()
    with pytest.raises(selector.SparseSelectorError, match="missing"):
        selector.read_next_handoff_queue_item(
            root,
            head,
            after_ordinal=missing_ordinal - 1,
            after_cycle_id=cursors[missing_ordinal - 1]["cycle"]["id"],
            after_cycle_pointer=cursors[missing_ordinal - 1]["cycle"],
            after_queue_item_id=cursors[missing_ordinal - 1]["queue"]["id"],
            after_queue_item_pointer=cursors[missing_ordinal - 1]["queue"],
        )

    for corrupt_ordinal, prior_ordinal in (
        (middle_ordinal + 1, middle_ordinal),
        (horizon, horizon - 1),
    ):
        path = queue_dir / f"{corrupt_ordinal:020d}.json"
        item = json.loads(path.read_bytes())
        item["previous_cycle"] = None
        path.write_bytes(selector.canonical_bytes(item))
        prior = cursors[prior_ordinal]
        with pytest.raises(selector.SparseSelectorError, match="drifted"):
            selector.read_next_handoff_queue_item(
                root,
                head,
                after_ordinal=prior_ordinal,
                after_cycle_id=prior["cycle"]["id"],
                after_cycle_pointer=prior["cycle"],
                after_queue_item_id=prior["queue"]["id"],
                after_queue_item_pointer=prior["queue"],
            )


def test_handoff_queue_next_read_rejects_wrong_settlement_cycle(
    tmp_path: Path,
) -> None:
    source = _source([])
    root = tmp_path / "wrong-cursor"
    first_head = _commit_first(root, source)
    second_plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    second_head = selector.commit_cycle(root, second_plan)
    wrong_pointer = copy.deepcopy(first_head["last_cycle"])
    wrong_pointer["sha256"] = "0" * 64
    with pytest.raises(selector.SparseSelectorError, match="exact cursor"):
        selector.read_next_handoff_queue_item(
            root,
            second_head,
            after_ordinal=1,
            after_cycle_id=wrong_pointer["id"],
            after_cycle_pointer=wrong_pointer,
            after_queue_item_id=first_head["last_handoff_queue"]["id"],
            after_queue_item_pointer=first_head["last_handoff_queue"],
        )


def test_store_rejects_mode_symlink_hardlink_and_prefix_drift(tmp_path: Path) -> None:
    source = _source([[_episode("security", "2026-08-12T13:31:00Z")]])
    unsafe_mode = tmp_path / "mode"
    unsafe_mode.mkdir(mode=0o755)
    unsafe_mode.chmod(0o755)
    with pytest.raises(selector.SparseSelectorError, match="caller-owned 0700"):
        _commit_first(unsafe_mode, source)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target, target_is_directory=True)
    with pytest.raises(selector.SparseSelectorError, match="symlink"):
        _commit_first(symlink, source)

    root = tmp_path / "hardlink"
    head = _commit_first(root, source)
    object_path = selector._object_path(
        root, head["last_candidate"]["key"]
    )
    os.link(object_path, tmp_path / "foreign-hardlink")
    with pytest.raises(selector.SparseSelectorError, match="metadata is unsafe"):
        selector.authenticate_store(root)


def test_257_row_global_order_ignores_source_segmentation(tmp_path: Path) -> None:
    source = _global_order_adversary_source(257, 3)
    root = tmp_path / "global-order"
    head = _commit_first(root, source)
    manifest = selector._load_pointer(
        root,
        _last_cycle(root, head)["next_manifest"],
        label="global-order manifest",
    )
    candidates = [
        selector._load_pointer(root, pointer, label="global-order candidate")
        for pointer in manifest["candidates"]
    ]
    assert len(candidates) == selector.MAX_CANDIDATES_PER_MANIFEST
    assert [
        (row["candidate_available_at"], row["candidate_id"]) for row in candidates
    ] == sorted(
        (row["candidate_available_at"], row["candidate_id"]) for row in candidates
    )
    assert candidates[2]["campaign_row_number"] == 257


def test_1300_row_projection_drains_exact_manifest_shape(tmp_path: Path) -> None:
    source = _many_candidate_source(1300)
    sizes, head, observed_plan_sizes = _manifest_sizes_until_drain(
        tmp_path / "bounded-1300", source
    )
    assert sizes == [128] * 10 + [20]
    assert head["candidate_count"] == 1300
    assert head["source_ready_cursor"] == head["source_ready_count"] == 1300
    assert observed_plan_sizes
    assert max(size[0] for size in observed_plan_sizes) <= 1024
    assert max(size[1] for size in observed_plan_sizes) <= 4 * 1024 * 1024
    assert selector.authenticate_store(tmp_path / "bounded-1300")[0] == head


def test_runtime_validator_rejects_nonsense_without_optional_formats(
    tmp_path: Path,
) -> None:
    root = tmp_path / "rfc3339"
    source = _source([[_episode("rfc3339", "2026-08-12T13:31:00Z")]])
    head = _commit_first(root, source)
    candidate = selector._load_pointer(
        root, head["last_candidate"], label="RFC3339 candidate"
    )
    candidate["candidate_available_at"] = "nonsense"
    with pytest.raises(selector.SparseSelectorError, match="schema validation failed"):
        selector.validate_runtime_object(candidate, label="invalid RFC3339 candidate")
    assert selector.runtime_schema_validator() is selector._SCHEMA_VALIDATOR


def test_legacy_segment_local_admission_is_unreachable() -> None:
    with pytest.raises(selector.SparseSelectorError, match="permanently deauthorized"):
        selector._build_source_projection(
            source=None,
            campaigns=(),
            episodes=(),
            campaign_prefix={},
            episode_prefix={},
        )


def test_evidence_generation_drift_aborts_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_root = tmp_path / "marks"
    lifecycle_root = tmp_path / "lifecycle"
    mark_root.mkdir(mode=0o700)
    lifecycle_root.mkdir(mode=0o700)
    state = {"enrollments": {}, "latest_marks": {}}
    states = iter((state, {"enrollments": {}, "latest_marks": {}, "changed": True}))
    monkeypatch.setattr(
        selector.lifecycle, "_validate_private_root_location", lambda *a, **k: None
    )
    monkeypatch.setattr(
        selector.mark_chain, "_require_private_directory", lambda *a, **k: None
    )
    monkeypatch.setattr(
        selector.mark_chain,
        "_private_ledger_lock",
        lambda *a, **k: nullcontext(),
    )
    monkeypatch.setattr(
        selector.mark_chain, "_load_previous_pointer", lambda *a, **k: None
    )
    monkeypatch.setattr(
        selector.lifecycle,
        "_ledger_paths",
        lambda *a, **k: (Path("l"), Path("r")),
    )
    monkeypatch.setattr(
        selector.lifecycle,
        "_read_ledger_snapshot",
        lambda *a, **k: (b"", [], {}),
    )
    monkeypatch.setattr(
        selector.lifecycle, "_load_state", lambda *a, **k: next(states)
    )
    monkeypatch.setattr(
        selector.lifecycle, "_validate_event_chain", lambda *a, **k: None
    )
    monkeypatch.setattr(
        selector.lifecycle,
        "_validate_activation_boundary_against_state",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        selector.lifecycle, "_validate_source_references", lambda *a, **k: None
    )
    with pytest.raises(selector.EvidenceGenerationDrift):
        selector._build_evidence_snapshot(
            selector.EvidenceInputs(
                mark_root=mark_root,
                lifecycle_root=lifecycle_root,
            )
        )


def test_evidence_snapshot_is_built_once_per_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _many_candidate_source(32)
    root = tmp_path / "one-evidence-snapshot"
    head = _commit_first(root, source)
    calls = 0
    original = selector._build_evidence_snapshot

    def counted(
        inputs: selector.EvidenceInputs, **scope
    ) -> selector.EvidenceSnapshot:
        nonlocal calls
        calls += 1
        return original(inputs, **scope)

    monkeypatch.setattr(selector, "_build_evidence_snapshot", counted)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    assert plan.head["decision_count"] == 32
    assert calls == 1


def test_audit_continuation_rejects_same_length_source_substitution(
    tmp_path: Path,
) -> None:
    source = _many_candidate_source(40)
    root = tmp_path / "contamination"
    first = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    selector.commit_cycle(root, first)
    contaminated = bytearray(source.episodes_raw)
    offset = contaminated.index(b"bounded-00039")
    contaminated[offset : offset + len(b"bounded-00039")] = b"bounded-X0039"
    with pytest.raises(selector.SparseSelectorError, match="changed under their pinned"):
        selector.plan_cycle(
            root=root,
            source=selector.SourceSnapshot(
                commit=source.commit,
                campaigns_raw=source.campaigns_raw,
                episodes_raw=bytes(contaminated),
                observed_at=source.observed_at,
                campaigns_blob_oid=selector._git_blob_oid(source.campaigns_raw),
                episodes_blob_oid=selector._git_blob_oid(source.episodes_raw),
                checkpoint_raw=source.checkpoint_raw,
                checkpoint_blob_oid=selector._git_blob_oid(source.checkpoint_raw),
            ),
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="2026-08-12T14:00:00Z",
            clock=_clock(),
            runtime_armed=True,
        )


def test_campaign_source_derived_drift_fails_closed(tmp_path: Path) -> None:
    source = _source([[_episode("derived-drift", "2026-08-12T13:31:00Z")]])
    campaign = json.loads(source.campaigns_raw)
    campaign["descriptive"]["premium_usd_total"] += 1
    campaign_engine.validate_campaign(campaign)
    drifted = _snapshot_with_checkpoint(
        commit=source.commit,
        campaigns_raw=campaign_engine.canonical_bytes(campaign) + b"\n",
        episodes_raw=source.episodes_raw,
        observed_at=source.observed_at,
    )
    with pytest.raises(selector.SparseSelectorError, match="source-derived field drift"):
        _commit_first(tmp_path / "derived-drift", drifted)


def test_episode_ledger_duplicate_identity_fails_closed(tmp_path: Path) -> None:
    episode = _episode("duplicate-episode", "2026-08-12T13:31:00Z")
    source = _snapshot_with_checkpoint(
        commit="a" * 40,
        campaigns_raw=b"",
        episodes_raw=(campaign_engine.canonical_bytes(episode) + b"\n") * 2,
        observed_at="2026-08-12T14:00:00Z",
    )
    with pytest.raises(selector.SparseSelectorError, match="repeats an identity"):
        _commit_first(tmp_path / "duplicate-episode", source)


def test_source_transition_object_and_intent_caps(tmp_path: Path) -> None:
    source = _many_candidate_source(40)
    root = tmp_path / "object-bound"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    assert len(plan.objects) <= selector.MAX_SOURCE_OBJECTS_PER_CYCLE
    assert len(selector.canonical_bytes(plan.intent)) <= selector.MAX_INTENT_BYTES


def test_manifest_and_cycle_admission_caps_are_schema_bound(tmp_path: Path) -> None:
    source = _source([[_episode("manifest-cap", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "manifest-cap"
    head = _commit_first(root, source)
    manifest = selector._load_pointer(
        root, head["pending_manifest"], label="manifest cap fixture"
    )
    empty = copy.deepcopy(manifest)
    empty["candidate_count"] = 0
    empty["candidates"] = []
    empty["manifest_id"] = selector._content_id(
        "ossm_", empty, field="manifest_id"
    )
    with pytest.raises(selector.SparseSelectorError, match="schema validation failed"):
        selector.validate_runtime_object(empty, label="empty manifest")

    duplicate = copy.deepcopy(manifest)
    duplicate["candidates"] = [manifest["candidates"][0]] * 2
    duplicate["candidate_count"] = 2
    duplicate["manifest_id"] = selector._content_id(
        "ossm_", duplicate, field="manifest_id"
    )
    with pytest.raises(selector.SparseSelectorError, match="non-unique"):
        selector.validate_runtime_object(duplicate, label="duplicate manifest")

    oversized = copy.deepcopy(manifest)
    oversized["candidates"] = [
        {
            "id": f"ossc_{ordinal:064x}",
            "key": f"candidates/ossc_{ordinal:064x}.json",
            "sha256": f"{ordinal:064x}",
            "bytes": 1,
        }
        for ordinal in range(129)
    ]
    oversized["candidate_count"] = len(oversized["candidates"])
    oversized["manifest_id"] = selector._content_id(
        "ossm_", oversized, field="manifest_id"
    )
    with pytest.raises(selector.SparseSelectorError, match="schema validation failed"):
        selector.validate_runtime_object(oversized, label="oversized manifest")

    cycle = _last_cycle(root, head)
    oversized_cycle = copy.deepcopy(cycle)
    oversized_cycle["candidate_pointers"] = oversized["candidates"]
    oversized_cycle["candidate_count_after"] = (
        oversized_cycle["candidate_count_before"] + 129
    )
    oversized_cycle["last_candidate"] = oversized["candidates"][-1]
    oversized_cycle["cycle_id"] = selector._cycle_id(
        ordinal=oversized_cycle["ordinal"],
        scheduled_at=oversized_cycle["scheduled_at"],
        started_at=oversized_cycle["started_at"],
        source_commit=oversized_cycle["source_commit"],
        previous_head_id=oversized_cycle["previous_head_id"],
    )
    with pytest.raises(selector.SparseSelectorError, match="schema validation failed"):
        selector.validate_runtime_object(oversized_cycle, label="oversized cycle")


def test_terminal_settlement_recovery_authenticates_one_to_one(tmp_path: Path) -> None:
    source = _source([[_episode("terminal", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "terminal"
    head = _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    assert plan.head["source_phase"] == "DRAINED"
    assert plan.head["pending_manifest"] is None

    def crash(point: str) -> None:
        if point == "after_intent":
            raise RuntimeError("terminal crash")

    with pytest.raises(RuntimeError, match="terminal crash"):
        selector.commit_cycle(root, plan, hook=crash)
    recovered = selector.commit_cycle(root, None)
    assert recovered["pending_manifest"] is None
    assert recovered["candidate_count"] == recovered["decision_count"] == 1
    authenticated, decisions, _body = selector.authenticate_store(root)
    assert authenticated == recovered
    assert [row["candidate"] for row in decisions] == [recovered["last_candidate"]]


def test_decision_semantics_fail_closed_on_missing_truth(tmp_path: Path) -> None:
    source = _source([[_episode("decision-semantics", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "decision-semantics"
    head = _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    decision = next(
        item.value
        for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    assert decision["action"] == "abstain"
    assert decision["reason_codes"]
    assert decision["contract"] is decision["plan_id"] is None

    missing_reason = copy.deepcopy(decision)
    missing_reason["reason_codes"] = []
    missing_reason["decision_id"] = selector._content_id(
        "ossd_", missing_reason, field="decision_id"
    )
    with pytest.raises(selector.SparseSelectorError, match="decision identity drifted"):
        selector.validate_runtime_object(missing_reason, label="reasonless abstention")

    forged_proposal = copy.deepcopy(decision)
    forged_proposal["action"] = "propose"
    forged_proposal["reason_codes"] = []
    forged_proposal["proposal_ordinal"] = 1
    forged_proposal["decision_nyse_session_date"] = "2026-08-12"
    forged_proposal["decision_id"] = selector._content_id(
        "ossd_", forged_proposal, field="decision_id"
    )
    with pytest.raises(
        selector.SparseSelectorError,
        match="schema validation failed|decision identity drifted",
    ):
        selector.validate_runtime_object(forged_proposal, label="truthless proposal")


def test_source_intent_window_pointer_tamper_fails_recovery(tmp_path: Path) -> None:
    source = _many_candidate_source(4)
    root = tmp_path / "source-window-tamper"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == "after_intent":
            raise RuntimeError("source crash")

    with pytest.raises(RuntimeError, match="source crash"):
        selector.commit_cycle(root, plan, hook=crash)
    forged = copy.deepcopy(plan.intent)
    assert forged["source_window"]["stage"] == "EPISODES"
    forged["source_window"]["chunk"]["sha256"] = "0" * 64
    forged["intent_sha256"] = selector._content_id(
        "", forged, field="intent_sha256"
    )
    (root / selector.INTENT_FILE).write_bytes(selector.canonical_bytes(forged))
    with pytest.raises(selector.SparseSelectorError, match="recovery seal"):
        selector.commit_cycle(root, None)


def test_recovery_seal_rejects_self_consistent_alternate_evidence_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source([[_episode("sealed-evidence", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "sealed-evidence"
    runtime_head = _commit_first(root, source)
    passing, head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    pinned = _pinned_source(source, head)
    absent_inputs = selector.EvidenceInputs(
        mark_root=passing.mark_root,
        lifecycle_root=passing.lifecycle_root,
    )
    absent_plan = selector.plan_cycle(
        root=root,
        source=pinned,
        evidence_inputs=absent_inputs,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    passing_plan = selector.plan_cycle(
        root=root,
        source=pinned,
        evidence_inputs=passing,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    passing_decision = next(
        item.value
        for item in passing_plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    absent_decision = next(
        item.value
        for item in absent_plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    assert passing_decision["action"] == "propose"
    assert absent_decision["action"] == "abstain"

    def crash(point: str) -> None:
        if point == "after_intent":
            raise RuntimeError("sealed intent crash")

    with pytest.raises(RuntimeError, match="sealed intent crash"):
        selector.commit_cycle(root, passing_plan, hook=crash)
    seal_path = selector._object_path(
        root, selector._intent_seal_key(passing_plan.intent)
    )
    original_seal = seal_path.read_bytes()
    assert not (root / selector.INTENT_ATTEMPT_FILE).exists()
    (root / selector.INTENT_FILE).write_bytes(selector.canonical_bytes(absent_plan.intent))
    with pytest.raises(selector.SparseSelectorError, match="recovery seal"):
        selector.commit_cycle(root, None, evidence_inputs=passing)
    assert seal_path.read_bytes() == original_seal
    assert selector._load_head(root) == head


def test_combined_settlement_lock_order_and_live_fences_span_intent_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source([[_episode("combined-locks", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "combined-lock-selector"
    runtime_head = _commit_first(root, source)
    inputs, complete_head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, complete_head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    assert any(
        item.value.get("schema")
        == "options.sparse_selector_w1a_source_receipt/v1"
        for item in plan.objects
    )

    held: list[str] = []
    locked: list[str] = []
    seal_points: list[str] = []
    complete_fences = 0
    real_store_lock = selector._store_lock
    real_w1a_fence = selector._w1a_commit_fence
    real_evidence_lock = selector._anchored_evidence_lock
    real_complete_fence = selector._validate_live_complete_evidence

    @contextmanager
    def traced_store_lock(path: Path):
        with real_store_lock(path):
            assert held == []
            held.append("selector")
            locked.append("selector")
            try:
                yield
            finally:
                assert held.pop() == "selector"

    @contextmanager
    def traced_w1a_fence(
        path: Path,
        current_plan: selector.CyclePlan,
        current_inputs: selector.EvidenceInputs,
    ):
        assert held == ["selector"]
        with real_w1a_fence(path, current_plan, current_inputs):
            held.append("w1a")
            locked.append("w1a")
            try:
                yield
            finally:
                assert held.pop() == "w1a"

    @contextmanager
    def traced_evidence_lock(lane, authority):
        # Receipt-only reconstruction may transiently authenticate the live
        # COMPLETE generation before the long-held publication fences begin.
        if held == ["selector"]:
            with real_evidence_lock(lane, authority) as descriptor:
                yield descriptor
            return
        label = (
            "mark"
            if lane.root == Path(inputs.mark_root).absolute()
            else "lifecycle"
        )
        expected = ["selector", "w1a"]
        if label == "lifecycle":
            expected.append("mark")
        assert held == expected
        with real_evidence_lock(lane, authority) as descriptor:
            held.append(label)
            locked.append(label)
            try:
                yield descriptor
            finally:
                assert held.pop() == label

    def traced_complete_fence(*args, **kwargs) -> None:
        nonlocal complete_fences
        if held == ["selector"]:
            real_complete_fence(*args, **kwargs)
            return
        assert held == ["selector", "w1a", "mark", "lifecycle"]
        complete_fences += 1
        real_complete_fence(*args, **kwargs)

    def observe_seal(point: str) -> None:
        if point in {"after_intent_before_seal", "after_intent_seal"}:
            assert held == ["selector", "w1a", "mark", "lifecycle"]
            seal_points.append(point)

    monkeypatch.setattr(selector, "_store_lock", traced_store_lock)
    monkeypatch.setattr(selector, "_w1a_commit_fence", traced_w1a_fence)
    monkeypatch.setattr(selector, "_anchored_evidence_lock", traced_evidence_lock)
    monkeypatch.setattr(
        selector, "_validate_live_complete_evidence", traced_complete_fence
    )
    committed = selector.commit_cycle(
        root,
        plan,
        evidence_inputs=inputs,
        hook=observe_seal,
    )
    assert committed == plan.head
    assert locked[:4] == ["selector", "w1a", "mark", "lifecycle"]
    assert seal_points == ["after_intent_before_seal", "after_intent_seal"]
    assert complete_fences >= 5
    assert held == []


def test_sealed_combined_settlement_replays_after_producer_heads_advance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _episode("sealed-producer-advance", "2026-08-12T13:31:00Z")
    source = _source([[episode]])
    root = tmp_path / "sealed-producer-advance-selector"
    runtime_head = _commit_first(root, source)
    inputs, complete_head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, complete_head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    planned_decisions = [
        item
        for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    ]
    assert len(planned_decisions) == 1
    assert planned_decisions[0].value["action"] == "propose"

    def crash_after_seal(point: str) -> None:
        if point == "after_intent_seal":
            raise RuntimeError("sealed settlement crash")

    with pytest.raises(RuntimeError, match="sealed settlement crash"):
        selector.commit_cycle(
            root,
            plan,
            evidence_inputs=inputs,
            hook=crash_after_seal,
        )
    assert selector._load_head(root) == complete_head
    assert (root / selector.INTENT_FILE).is_file()
    before_decisions = {
        path.relative_to(root): path.read_bytes()
        for path in (root / "decisions").rglob("*.json")
    }
    assert set(before_decisions) == {
        Path(item.key) for item in planned_decisions
    }

    reference = _bound_w1a_reference(
        owner_id=episode["episode_id"],
        record_sha256=hashlib.sha256(source.episodes_raw.splitlines()[0]).hexdigest(),
    )
    later_w1a = _publish_w1a(
        Path(inputs.w1a_receipt_root),
        [reference],
        published_at="2026-08-12T14:50:00Z",
        salt="b",
    )
    assert later_w1a["head"]["publication_id"] != (
        plan.head["w1a_publication_high_water"]["publication_id"]
    )

    mark_root = Path(inputs.mark_root)
    lifecycle_root = Path(inputs.lifecycle_root)
    monkeypatch.setenv("PROPHET_OPTION_EVIDENCE_STATE_ROOT", str(mark_root))
    later_index = {
        "schema": "prophet.index/v1",
        "asof": "2026-08-12",
        "recorded_at": "2026-08-12",
        "plans": [],
    }
    later_coverage = selector.mark_chain._evidence_coverage(
        index=later_index,
        rows=[],
        source_call_count=0,
    )
    later_mark = selector.mark_chain._publish_private_observation(
        index=later_index,
        payload={
            "schema": "prophet.live_marks/v1",
            "asof_utc": "2026-08-12T14:50:00Z",
            "session_date": "2026-08-12",
            "marks": {},
            "coverage": later_coverage,
        },
        evidence_rows=[],
    )
    ledger_path = lifecycle_root / "canonical_ledger/ledger.jsonl"
    advanced = selector.lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    assert advanced["status"] == "advanced"
    assert selector.lifecycle._load_state(lifecycle_root)["mark_cursor"] == later_mark

    recovered = selector.commit_cycle(root, None, evidence_inputs=inputs)
    assert recovered == plan.head
    assert recovered["evidence_high_water"] == complete_head["evidence_high_water"]
    assert recovered["decision_count"] == complete_head["decision_count"] + 1
    assert {
        path.relative_to(root): path.read_bytes()
        for path in (root / "decisions").rglob("*.json")
    } == before_decisions
    authenticated, decisions, _body = selector.authenticate_store(
        root, evidence_inputs=inputs
    )
    assert authenticated == recovered
    assert [decision["decision_id"] for decision in decisions] == [
        planned_decisions[0].value["decision_id"]
    ]


def test_source_recovery_cannot_omit_an_eligible_campaign_seed(
    tmp_path: Path,
) -> None:
    source = _many_candidate_source(1)
    root = tmp_path / "source-seed-omission"
    first = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    head = selector.commit_cycle(root, first)
    assert head["source_audit_stage"] == "CAMPAIGNS"
    campaign_plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    seed_receipts = [
        item.receipt
        for item in campaign_plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_source_seed/v1"
    ]
    assert len(seed_receipts) == 1
    forged = copy.deepcopy(campaign_plan.intent)
    forged["objects"] = [
        receipt for receipt in forged["objects"] if receipt not in seed_receipts
    ]
    forged["intent_sha256"] = selector._content_id(
        "", forged, field="intent_sha256"
    )
    with selector._store_lock(root):
        for item in campaign_plan.objects:
            selector._prestage_immutable(
                selector._object_path(root, item.key), item.body, root=root
            )
        with pytest.raises(
            selector.SparseSelectorError,
            match="omitted or changed an eligible seed",
        ):
            selector._plan_from_intent(root, forged)


def test_source_recovery_binds_the_complete_parent_cursor_state(
    tmp_path: Path,
) -> None:
    source = _many_candidate_source(1)
    root = tmp_path / "source-parent-state"
    first = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    head = selector.commit_cycle(root, first)
    assert head["source_audit_stage"] == "CAMPAIGNS"
    campaign_plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    forged = copy.deepcopy(campaign_plan.intent)
    forged["expected_source_state"]["source_campaign_cursor_bytes"] += 1
    forged["intent_sha256"] = selector._content_id(
        "", forged, field="intent_sha256"
    )
    with selector._store_lock(root):
        for item in campaign_plan.objects:
            selector._prestage_immutable(
                selector._object_path(root, item.key), item.body, root=root
            )
        with pytest.raises(
            selector.SparseSelectorError,
            match="parent source state drifted",
        ):
            selector._plan_from_intent(root, forged)


def test_settlement_only_backoff_recovers_and_resumes_global_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(selector, "MAX_CANDIDATES_PER_MANIFEST", 1)
    source = _many_candidate_source(2)
    root = tmp_path / "settlement-only"
    head = _commit_first(root, source)
    assert head["candidate_count"] == 1
    assert head["source_ready_cursor"] == 1

    snapshot_calls = 0
    original_snapshot = selector._build_evidence_snapshot

    def counted_snapshot(inputs, **scope):
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original_snapshot(inputs, **scope)

    original_once = selector._plan_cycle_once

    def force_settlement_only(**kwargs):
        plan = original_once(**kwargs)
        if kwargs["admission_cap"] > 0:
            raise selector._AdvanceBoundExceeded("forced bounded admission fallback")
        return plan

    monkeypatch.setattr(selector, "_build_evidence_snapshot", counted_snapshot)
    monkeypatch.setattr(selector, "_plan_cycle_once", force_settlement_only)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    assert snapshot_calls == 1
    assert plan.head["source_phase"] == "READY"
    assert plan.head["pending_manifest"] is None
    assert plan.head["candidate_count"] == plan.head["decision_count"] == 1
    assert plan.head["source_ready_cursor"] == 1

    def crash(point: str) -> None:
        if point == "after_intent":
            raise RuntimeError("settlement-only crash")

    with pytest.raises(RuntimeError, match="settlement-only crash"):
        selector.commit_cycle(root, plan, hook=crash)
    recovered = selector.commit_cycle(root, None)
    assert recovered == plan.head

    monkeypatch.setattr(selector, "_plan_cycle_once", original_once)
    resumed = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, recovered),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:10:00Z",
        clock=_clock("2026-08-12T14:10:00Z"),
        runtime_armed=True,
    )
    assert resumed.head["source_ready_cursor"] == 2
    assert resumed.head["candidate_count"] == 2
    assert resumed.head["pending_manifest"] is not None


def test_large_source_evidence_is_shared_and_compact_while_null_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([[_episode("large-evidence", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "large-evidence"
    head = _commit_first(root, source)
    evidence_inputs = _passing_evidence(
        tmp_path,
        monkeypatch,
        source,
        padding_bytes=6_000,
    )
    candidate = selector._load_pointer(
        root, head["last_candidate"], label="large-evidence candidate"
    )
    snapshot = selector._build_evidence_snapshot(evidence_inputs)
    mark, lifecycle_evidence, _contract, _plan_id, reasons = (
        selector._lifecycle_evidence(
            candidate,
            snapshot,
            decision_event_at=datetime(
                2026, 8, 12, 14, 5, 0, tzinfo=timezone.utc
            ),
        )
    )
    assert reasons == []
    assert mark is not None and len(mark.body) >= 5_371
    assert (
        lifecycle_evidence is not None
        and len(lifecycle_evidence.body) >= 5_704
    )

    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    decision = next(
        item.value
        for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    assert decision["action"] == "propose"
    assert decision["reason_codes"] == []
    assert all(decision["evidence"][name] is not None for name in decision["evidence"])
    evidence_objects = {
        item.value["schema"]: item
        for item in plan.objects
        if item.key.startswith("evidence/")
    }
    assert set(evidence_objects) == {
        "options.sparse_selector_evidence_generation/v1",
        "options.sparse_selector_konseki_evidence/v1",
        "options.sparse_selector_mark_evidence/v1",
        "options.sparse_selector_lifecycle_evidence/v1",
        "options.sparse_selector_w1a_source_receipt/v1",
    }
    generation = evidence_objects[
        "options.sparse_selector_evidence_generation/v1"
    ]
    assert decision["evidence"]["generation"] == generation.pointer
    source_receipt = evidence_objects[
        "options.sparse_selector_w1a_source_receipt/v1"
    ]
    assert len(source_receipt.body) <= selector.MAX_W1A_SOURCE_RECEIPT_BYTES
    assert generation.value["w1a_source_receipt"] == source_receipt.pointer
    for schema in (
        "options.sparse_selector_konseki_evidence/v1",
        "options.sparse_selector_mark_evidence/v1",
        "options.sparse_selector_lifecycle_evidence/v1",
    ):
        item = evidence_objects[schema]
        assert len(item.body) <= selector.MAX_EVIDENCE_OBJECT_BYTES
        assert item.value["generation"] == generation.pointer
        assert item.value["candidate"] == decision["candidate"]
        assert "padding" not in item.value
    assert len(selector.canonical_bytes(plan.intent)) <= selector.MAX_INTENT_BYTES

    monkeypatch.setattr(
        selector,
        "_reference_for_candidate",
        lambda *_args, **_kwargs: (None, []),
    )
    monkeypatch.setattr(
        selector,
        "_lifecycle_evidence",
        lambda *_args, **_kwargs: (None, None, None, None, []),
    )
    null_plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    null_decision = next(
        item.value
        for item in null_plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    assert {
        "KONSEKI_CONTEXT_RECEIPT_MISSING_OR_MISMATCHED",
        "MARK_RECEIPT_MISSING_OR_MISMATCHED",
        "LIFECYCLE_RECEIPT_MISSING_OR_MISMATCHED",
    }.issubset(null_decision["reason_codes"])
    assert null_decision["evidence"]["generation"] is not None
    assert all(
        null_decision["evidence"][name] is None
        for name in ("konseki", "mark", "lifecycle")
    )
    null_evidence_objects = [
        item for item in null_plan.objects if item.key.startswith("evidence/")
    ]
    assert {item.value["schema"] for item in null_evidence_objects} == {
        "options.sparse_selector_w1a_source_receipt/v1",
        "options.sparse_selector_evidence_generation/v1",
    }


def test_manifest_scoped_snapshot_skips_256_unrelated_enrollments_and_bounds_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([[_episode("scoped-evidence", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "selector-source"
    head = _commit_first(root, source)
    candidate = selector._load_pointer(
        root, head["last_candidate"], label="scoped evidence candidate"
    )
    mark_root = tmp_path / "marks"
    lifecycle_root = tmp_path / "lifecycle"
    mark_root.mkdir(mode=0o700)
    lifecycle_root.mkdir(mode=0o700)
    def event_pointer(ordinal: int) -> dict:
        event_id = f"posle_{ordinal:064x}"
        return {
            "schema": selector.lifecycle.EVENT_POINTER_SCHEMA,
            "event_id": event_id,
            "key": f"events/2026-08-12/{event_id}.json",
            "sha256": f"{ordinal:064x}",
            "bytes": 1,
        }

    activation = event_pointer(10_000)
    mark_cursor = {
        "schema": selector.mark_chain.EVIDENCE_POINTER_SCHEMA,
        "observation_id": f"pom_obs_{'a' * 64}",
        "key": f"observations/2026-08-12/pom_obs_{'a' * 64}.json",
        "sha256": "a" * 64,
        "bytes": 1,
    }
    target_occ = selector._campaign_occ_symbol(candidate["campaign_row"])
    enrollments = {}
    latest_marks = {}
    for ordinal in range(257):
        plan_id = f"plan-{ordinal}"
        enrollments[plan_id] = event_pointer(ordinal + 1)
        latest_marks[plan_id] = {
            "contract_occ_symbol": target_occ if ordinal == 256 else f"ZZZZ  260101C{ordinal + 1:08d}",
            "contract_drift": False,
            "plan_identity_drift": False,
            "sessions": {},
        }
    state = {
        "activation": activation,
        "lifecycle_head": enrollments["plan-256"],
        "mark_cursor": mark_cursor,
        "enrollments": enrollments,
        "terminals": {},
        "latest_marks": latest_marks,
    }
    enrollment = {
        "payload": {
            "plan": {"id": "plan-256"},
            "contract": {
                "root": candidate["campaign_row"]["group"]["ticker"],
                "right": candidate["campaign_row"]["group"]["right"],
                "expiry": candidate["campaign_row"]["group"]["expiration"],
                "strike": candidate["campaign_row"]["group"]["strike_key"],
                "occ_symbol": target_occ,
            }
        },
        "authority": dict(selector.FALSE_AUTHORITY),
    }
    loads: list[str] = []
    event_reads: list[str] = []
    monkeypatch.setattr(selector.lifecycle, "_validate_private_root_location", lambda *a, **k: None)
    monkeypatch.setattr(selector.mark_chain, "_require_private_directory", lambda *a, **k: None)
    monkeypatch.setattr(selector.mark_chain, "_private_ledger_lock", lambda *a, **k: nullcontext())
    monkeypatch.setattr(selector.mark_chain, "_load_previous_pointer", lambda *a, **k: mark_cursor)
    monkeypatch.setattr(selector.lifecycle, "_load_state", lambda *a, **k: copy.deepcopy(state))
    monkeypatch.setattr(selector.lifecycle, "_validate_event_chain", lambda *a, **k: None)
    monkeypatch.setattr(
        selector.lifecycle,
        "_validate_activation_boundary_against_state",
        lambda *a, **k: None,
    )
    boundary = {
        "mark_boundary": mark_cursor,
        "mark_boundary_observed_at_utc": "2026-08-12T14:00:00+00:00",
        "ledger_boundary": {"sha256": "b" * 64},
    }
    monkeypatch.setattr(
        selector.lifecycle, "_load_activation_boundary", lambda *_a, **_k: boundary
    )

    def load_event(_root, pointer):
        event_reads.append(pointer["event_id"])
        if pointer == activation:
            return {
                "event_kind": "activation_boundary",
                "previous": None,
                "payload": {
                    **boundary,
                    "prospective_after_boundary": True,
                },
            }
        return {
            "event_kind": "enrollment",
            "previous": activation,
            "payload": {"plan": {"id": "plan-256"}},
        }

    monkeypatch.setattr(selector.lifecycle, "_load_event", load_event)
    monkeypatch.setattr(selector, "_bounded_mark_chain", lambda *a, **k: ((), {}))
    monkeypatch.setattr(selector, "_validate_selected_enrollment_source", lambda **_k: None)

    def load_enrollment(_root, _pointer, plan_id):
        loads.append(plan_id)
        return copy.deepcopy(enrollment)

    monkeypatch.setattr(selector.lifecycle, "_load_enrollment", load_enrollment)
    snapshot = selector._build_evidence_snapshot(
        selector.EvidenceInputs(mark_root=mark_root, lifecycle_root=lifecycle_root),
        candidates=(candidate,),
        session_dates=frozenset({"2026-08-12"}),
    )
    assert loads == ["plan-256"]
    assert event_reads == [activation["event_id"]]
    assert len(snapshot.enrollments_by_contract) == 1

    monkeypatch.setattr(selector, "MAX_EVIDENCE_SOURCE_READS", 64)
    with pytest.raises(selector.EvidenceGenerationDrift, match="source-read budget"):
        selector._build_evidence_snapshot(
            selector.EvidenceInputs(mark_root=mark_root, lifecycle_root=lifecycle_root),
            candidates=(candidate,),
            session_dates=frozenset({"2026-08-12"}),
        )


def test_authenticate_store_rejects_rehashed_selected_row_forgery_with_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([[_episode("row-forgery", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "selector"
    runtime_head = _commit_first(root, source)
    inputs, head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    selector.commit_cycle(root, plan)
    authenticated_state = selector._authenticate_selector_state(root)
    decision_item = next(
        item for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    mark_item = next(
        item for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_mark_evidence/v1"
    )
    forged_mark_value = copy.deepcopy(mark_item.value)
    forged_mark_value["selected_row_sha256"] = "0" * 64
    forged_mark = selector._evidence_object(forged_mark_value)
    selector._write_immutable(
        selector._object_path(root, forged_mark.key),
        forged_mark.body,
        root=root,
    )
    forged_decision = copy.deepcopy(decision_item.value)
    forged_decision["evidence"]["mark"] = forged_mark.pointer
    forged_decision["decision_id"] = selector._content_id(
        "ossd_", forged_decision, field="decision_id"
    )
    monkeypatch.setattr(selector, "_authenticate_selector_state", lambda _root: authenticated_state)
    monkeypatch.setattr(selector, "_walk_immutable_chain", lambda *a, **k: [forged_decision])
    with pytest.raises(selector.SparseSelectorError, match="mark evidence source binding drifted"):
        selector.authenticate_store(root, evidence_inputs=inputs)


def test_cycle_decision_cap_and_evidence_recovery_are_fail_closed(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("evidence-recovery", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "evidence-recovery"
    head = _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    cycle = next(
        item.value
        for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_cycle_receipt/v1"
    )
    oversized = copy.deepcopy(cycle)
    oversized["decision_count"] = 129
    oversized["decision_ids"] = [f"ossd_{ordinal:064x}" for ordinal in range(129)]
    oversized["decision_pointers"] = [
        {
            "id": item,
            "key": f"decisions/{item}.json",
            "sha256": f"{ordinal:064x}",
            "bytes": 1,
        }
        for ordinal, item in enumerate(oversized["decision_ids"])
    ]
    with pytest.raises(selector.SparseSelectorError, match="schema validation failed"):
        selector.validate_runtime_object(oversized, label="129-decision cycle")

    decision_item = next(
        item
        for item in plan.objects
        if item.value.get("schema") == "options.sparse_selector_decision/v1"
    )
    generation_item = next(
        item
        for item in plan.objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_generation/v1"
    )
    forged = copy.deepcopy(decision_item.value)
    wrong = selector._evidence_object(
        {
            "schema": "options.sparse_selector_mark_evidence/v1",
            "generation": forged["evidence"]["generation"],
            "candidate": forged["candidate"],
            "plan_id": "wrong-slot-plan",
            "session_date": "2026-08-12",
            "mark_pointer": {
                "schema": selector.mark_chain.EVIDENCE_POINTER_SCHEMA,
                "observation_id": f"pom_obs_{'0' * 64}",
                "key": f"observations/2026-08-12/pom_obs_{'0' * 64}.json",
                "sha256": "0" * 64,
                "bytes": 1,
            },
            "selected_row_sha256": "0" * 64,
            "authority": dict(selector.FALSE_AUTHORITY),
        }
    )
    forged["evidence"]["konseki"] = wrong.pointer
    forged["decision_id"] = selector._content_id("ossd_", forged, field="decision_id")
    with pytest.raises(selector.SparseSelectorError, match="slot binding drifted"):
        selector._validate_decision_evidence_objects(
            root,
            forged,
            planned_by_key={
                generation_item.key: generation_item,
                wrong.key: wrong,
            },
        )


def test_stale_durable_intent_refuses_before_immutable_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([[_episode("stale-durable", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "stale-durable"
    head = _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, head),
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == "after_intent":
            raise RuntimeError("durable intent")

    with pytest.raises(RuntimeError, match="durable intent"):
        selector.commit_cycle(root, plan, hook=crash)
    writes = 0

    def no_write(*_args, **_kwargs):
        nonlocal writes
        writes += 1
        raise AssertionError("immutable write reached")

    monkeypatch.setattr(selector, "_write_immutable", no_write)
    monkeypatch.setattr(
        selector,
        "_load_head",
        lambda _root: {**head, "head_id": "ossh_" + "0" * 64},
    )
    with pytest.raises(
        selector.SparseSelectorError, match="parent drifted|stale|unavailable"
    ):
        selector.commit_cycle(root, None)
    assert writes == 0


@pytest.mark.skipif(
    os.environ.get("SPARSE_SELECTOR_PERF") != "1",
    reason="set SPARSE_SELECTOR_PERF=1 for the 4096-candidate resource gate",
)
def test_4096_candidate_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = time.monotonic()
    source = _many_candidate_source(4096)
    root = tmp_path / "bounded-4096"
    head: dict | None = None
    active: selector.SourceSnapshot = source
    transitions = 0
    observed_plan_sizes: list[tuple[int, int]] = []
    commit_locked = selector._commit_cycle_locked

    def observe_plan(root: Path, plan: selector.CyclePlan | None, **kwargs):
        if plan is not None:
            observed_plan_sizes.append(
                (len(plan.objects), len(selector.canonical_bytes(plan.intent)))
            )
        return commit_locked(root, plan, **kwargs)

    monkeypatch.setattr(selector, "_commit_cycle_locked", observe_plan)
    scheduled = selector._utc(
        "2026-08-12T14:00:00Z", label="benchmark first schedule"
    )
    while True:
        slot = selector.utc_text(scheduled)
        head = selector.advance(
            private_root=root,
            source=active,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at=slot,
            clock=_clock(slot),
        )
        transitions += 1
        if (
            head["source_phase"] == "DRAINED"
            and head["candidate_count"] == 4096
            and head["decision_count"] == 4096
            and head["pending_manifest"] is None
        ):
            break
        if head["cycle_count"]:
            scheduled += timedelta(minutes=5)
        active = (
            source
            if head["source_phase"] == "AUDITING"
            else _pinned_source(source, head)
        )
        assert transitions <= 128
    assert head is not None
    assert transitions <= 128
    assert head["source_phase"] == "DRAINED"
    assert head["candidate_count"] == 4096
    assert head["decision_count"] == 4096
    assert head["pending_manifest"] is None
    assert head["source_ready_cursor"] == head["source_ready_count"] == 4096
    assert head["source_ready_count"] == 4096
    assert max(size[0] for size in observed_plan_sizes) <= 1024
    assert max(size[1] for size in observed_plan_sizes) <= 4 * 1024 * 1024
    assert all(
        selector._load_source_run(root, pointer)["entry_count"] <= 4096
        for pointer in head["source_run_manifests"]
    )
    authenticated, decisions, _body = selector.authenticate_store(root)
    assert authenticated == head
    candidate_chain = selector._walk_candidate_chain_receipts(
        root,
        tail=head["last_candidate"],
        count=head["candidate_count"],
    )
    assert [row["ordinal"] for row in candidate_chain] == list(range(1, 4097))
    assert len({row["candidate_id"] for row in candidate_chain}) == 4096
    assert [row["candidate"] for row in decisions] == [
        row["pointer"]
        for row in candidate_chain
    ]
    assert [
        (row["candidate_available_at"], row["candidate_id"])
        for row in candidate_chain
    ] == sorted(
        (row["candidate_available_at"], row["candidate_id"])
        for row in candidate_chain
    )
    elapsed = time.monotonic() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = rss if sys.platform == "darwin" else rss * 1024
    # Wall-clock is a runaway-loop tripwire, not a laptop-speed pin.
    # Local receipt on this drain: 191.20s. GitHub-hosted ubuntu-latest
    # measured 387.9s on the same 4096-candidate loop (~2.0x) — shared
    # runners are noisier for this CPU-bound Python cycle. CI budget is
    # 2.5x the local receipt so a 2x-slow runner stays green and a
    # 10-minute hang still reds. Structural caps above (128 transitions,
    # 1024 objects, 4 MiB) are the real resource gate.
    budget_s = 480 if os.environ.get("CI") == "true" else 240
    assert elapsed <= budget_s, (
        f"{elapsed:.1f}s exceeded the {budget_s}s "
        f"{'CI' if os.environ.get('CI') == 'true' else 'local'} drain budget"
    )
    assert rss_bytes <= 512 * 1024 * 1024

def test_decision_clock_outside_rth_can_only_abstain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source([[_episode("after-hours", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "selector"
    runtime_head = _commit_first(root, source)
    evidence_inputs, complete_head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    plan = selector.plan_cycle(
        root=root,
        source=_pinned_source(source, complete_head),
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T21:00:00Z",
        clock=_clock("2026-08-12T21:00:00Z"),
        runtime_armed=True,
    )
    selector.commit_cycle(root, plan)
    decision = _decision_rows(root, evidence_inputs=evidence_inputs)[0]
    assert decision["action"] == "abstain"
    assert decision["reason_codes"] == ["DECISION_OUTSIDE_NYSE_RTH"]
    assert decision["proposal_ordinal"] is None


def test_full_campaign_source_join_rejects_owner_valid_row_with_forged_member(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("forged-owner", "2026-08-12T13:31:00Z")]])
    campaign = json.loads(source.campaigns_raw)
    campaign["members"][0]["source_row_sha256"] = "0" * 64
    forged = _snapshot_with_checkpoint(
        commit=source.commit,
        campaigns_raw=campaign_engine.canonical_bytes(campaign) + b"\n",
        episodes_raw=source.episodes_raw,
        observed_at=source.observed_at,
    )
    with pytest.raises(
        selector.SparseSelectorError,
        match="selector campaign member row digest drifted",
    ):
        _commit_first(tmp_path / "selector", forged)


@pytest.mark.parametrize(
    ("field", "nested_field"),
    [
        ("source_campaign_history_index", "entry_count"),
        ("source_episode_identity_index", "entry_count"),
        ("source_episode_group_index", "entry_count"),
        ("source_episode_group_count", None),
    ],
)
def test_head_refuses_authenticated_source_index_count_corruption(
    tmp_path: Path, field: str, nested_field: str | None
) -> None:
    source = _source([[_episode("head-count", "2026-08-12T13:31:00Z")]])
    root = tmp_path / field
    head = _commit_first(root, source)
    corrupted = copy.deepcopy(head)
    if nested_field is None:
        corrupted[field] -= 1
    else:
        corrupted[field][nested_field] -= 1
    corrupted["head_id"] = selector._content_id(
        "ossh_", corrupted, field="head_id"
    )
    (root / selector.HEAD_FILE).write_bytes(selector.canonical_bytes(corrupted))
    with pytest.raises(selector.SparseSelectorError, match="HEAD identity drifted"):
        selector.authenticate_store(root)


def test_stale_plan_cannot_publish_an_intent_or_replace_foreign_head(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("stale-plan", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "selector"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    selector.commit_cycle(root, plan)
    with pytest.raises(selector.SparseSelectorError, match="plan parent changed"):
        selector.commit_cycle(root, plan)
    assert not (root / selector.INTENT_FILE).exists()

    foreign_root = tmp_path / "foreign"
    foreign_plan = selector.plan_cycle(
        root=foreign_root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("do-not-replace", encoding="utf-8")
    (foreign_root / selector.HEAD_FILE).symlink_to(sentinel)
    with pytest.raises(selector.SparseSelectorError, match="symlink"):
        selector.commit_cycle(foreign_root, foreign_plan)
    assert sentinel.read_text(encoding="utf-8") == "do-not-replace"
    assert (foreign_root / selector.HEAD_FILE).is_symlink()
    assert not (foreign_root / selector.INTENT_FILE).exists()


def test_decision_evidence_and_cycle_clocks_remain_authenticated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source([[_episode("auth-evidence", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "selector"
    runtime_head = _commit_first(root, source)
    evidence_inputs, complete_head = _complete_passing_evidence(
        root=root,
        head=runtime_head,
        source=source,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    pinned_source = _pinned_source(source, complete_head)
    instants = iter(
        (
            datetime(2026, 8, 12, 14, 45, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 14, 45, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 14, 45, 2, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 14, 45, 1, tzinfo=timezone.utc),
        )
    )
    with pytest.raises(selector.SparseSelectorError, match="noncausal"):
        selector.plan_cycle(
            root=root,
            source=pinned_source,
            evidence_inputs=evidence_inputs,
            scheduled_at="2026-08-12T14:45:00Z",
            clock=lambda: next(instants),
            runtime_armed=True,
        )

    good_plan = selector.plan_cycle(
        root=root,
        source=pinned_source,
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:45:00Z",
        clock=_clock("2026-08-12T14:45:00Z"),
        runtime_armed=True,
    )
    selector.commit_cycle(root, good_plan)
    decision = selector.authenticate_store(
        root, evidence_inputs=evidence_inputs
    )[1][0]
    evidence_pointer = decision["evidence"]["mark"]
    assert evidence_pointer is not None
    evidence_path = selector._object_path(root, evidence_pointer["key"])
    os.link(evidence_path, tmp_path / "linked-evidence")
    with pytest.raises(selector.SparseSelectorError, match="metadata is unsafe"):
        selector.authenticate_store(root, evidence_inputs=evidence_inputs)


def _mock_evidence_capture_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[selector.EvidenceInputs, dict, dict]:
    del monkeypatch
    mark_root = tmp_path / "capture-marks"
    lifecycle_root = tmp_path / "capture-lifecycle"
    mark_root.mkdir(mode=0o700)
    lifecycle_root.mkdir(mode=0o700)
    mark_root.chmod(0o700)
    lifecycle_root.chmod(0o700)
    for root in (mark_root, lifecycle_root):
        lock_path = root / ".ledger.lock"
        lock_path.write_bytes(b"")
        lock_path.chmod(0o600)

    index = {
        "schema": "prophet.index/v1",
        "asof": "2026-08-12",
        "recorded_at": "2026-08-12T13:55:00Z",
        "plans": [],
    }
    observation = selector.mark_chain._build_observation(
        index=index,
        observed_at_utc="2026-08-12T14:00:00Z",
        session_date="2026-08-12",
        rows=[],
        coverage=selector.mark_chain._evidence_coverage(
            index=index, rows=[], source_call_count=0
        ),
        previous=None,
    )
    selector.mark_chain._validate_evidence_schema(observation)
    mark_pointer = selector.mark_chain._observation_pointer(observation)
    selector.mark_chain._write_private_immutable(
        selector.mark_chain._private_observation_path(
            mark_root, mark_pointer, create_parents=True
        ),
        selector.mark_chain._canonical_json_bytes(observation),
    )
    selector.mark_chain._write_private_head(
        mark_root,
        selector.mark_chain._canonical_json_bytes(
            {
                "schema": selector.mark_chain.EVIDENCE_HEAD_SCHEMA,
                "evidence": mark_pointer,
            }
        ),
    )

    ledger_body = b"\n"
    ledger_receipt = selector.lifecycle._ledger_receipt(
        ledger_body, [], source_commit="5" * 40
    )
    ledger_root = lifecycle_root / "canonical_ledger"
    selector.mark_chain._ensure_private_directory(ledger_root)
    selector.mark_chain._write_private_immutable(
        ledger_root / "ledger.jsonl", ledger_body
    )
    selector.mark_chain._write_private_immutable(
        ledger_root / "receipt.json",
        selector.lifecycle._canonical_json_bytes(ledger_receipt),
    )
    activation_boundary = selector.lifecycle._make_activation_boundary(
        mark_pointer=mark_pointer,
        mark_observation=observation,
        ledger_receipt=ledger_receipt,
    )
    activation_event = selector.lifecycle._activation_event(
        mark_pointer=mark_pointer,
        mark_observation=observation,
        ledger_receipt=ledger_receipt,
    )
    selector.lifecycle._write_events(lifecycle_root, [activation_event])
    event_pointer = selector.lifecycle._event_pointer(activation_event)
    selector.mark_chain._write_private_immutable(
        lifecycle_root / "activation_boundary.json",
        selector.lifecycle._canonical_json_bytes(activation_boundary),
    )
    state = selector.lifecycle._make_state(
        activation=event_pointer,
        lifecycle_head=event_pointer,
        mark_cursor=mark_pointer,
        ledger_cursor=ledger_receipt,
        enrollments={},
        terminals={},
        latest_marks={},
    )
    selector.lifecycle._write_state(lifecycle_root, state)
    return (
        selector.EvidenceInputs(mark_root=mark_root, lifecycle_root=lifecycle_root),
        state,
        mark_pointer,
    )


def _complete_passing_evidence(
    *,
    root: Path,
    head: dict,
    source: selector.SourceSnapshot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[selector.EvidenceInputs, dict]:
    """Install real anchored passing producers and audit them to COMPLETE."""

    real_build_snapshot = selector._build_evidence_snapshot
    real_reference_for_candidate = selector._reference_for_candidate
    real_validate_state = selector.lifecycle._validate_state_shape
    w1a_inputs = _passing_evidence(tmp_path, monkeypatch, source)
    monkeypatch.setattr(selector, "_build_evidence_snapshot", real_build_snapshot)
    monkeypatch.setattr(
        selector, "_reference_for_candidate", real_reference_for_candidate
    )
    monkeypatch.setattr(
        selector.lifecycle, "_validate_state_shape", real_validate_state
    )

    producer_parent = tmp_path / "passing-producers"
    producer_parent.mkdir(mode=0o700)
    producer_inputs, _activation_state, _activation_mark = (
        _mock_evidence_capture_sources(producer_parent, monkeypatch)
    )
    mark_root = Path(producer_inputs.mark_root)
    lifecycle_root = Path(producer_inputs.lifecycle_root)
    monkeypatch.setenv("PROPHET_OPTION_EVIDENCE_STATE_ROOT", str(mark_root))
    session_date = "2026-08-12"
    session = date.fromisoformat(session_date)
    observed_at = "2026-08-12T14:04:59Z"
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    quote, quote_reason = selector.mark_chain._validated_quote(
        {
            "bid": 99.5,
            "ask": 100.5,
            "last": 100.0,
            "quote_ts_utc": "2026-08-12T14:04:58Z",
            "trade_ts_utc": "2026-08-12T14:04:58.500000Z",
            "source_sequence": 7,
        },
        observed_at=observed,
        session_date=session,
    )
    assert quote is not None
    assert quote_reason is None
    plans: list[dict] = []
    rows: list[dict] = []
    for campaign in (
        json.loads(line) for line in source.campaigns_raw.splitlines()
    ):
        group = campaign["group"]
        plan = {
            "id": f"selector-test-{campaign['campaign_id']}",
            "asset": group["ticker"],
            "phase": "triggered_pre_t1",
            "closed": False,
            "plan_asof": session_date,
            "recorded_at": session_date,
            "entry_date": session_date,
            "option_contract": {
                "right": group["right"],
                "strike": float(group["strike_key"]),
                "expiry": group["expiration"],
                "entry_premium": 100.0,
                "freshness": "EOD mark",
            },
        }
        contract, contract_reason = selector.mark_chain._plan_contract(
            plan, session_date=session
        )
        assert contract is not None
        assert contract_reason is None
        plans.append(plan)
        rows.append(
            selector.mark_chain._plan_evidence_row(
                plan,
                contract=contract,
                contract_reason=None,
                quote=quote,
                quote_reason=None,
            )
        )
    index = {
        "schema": "prophet.index/v1",
        "asof": session_date,
        "recorded_at": session_date,
        "plans": plans,
    }
    coverage = selector.mark_chain._evidence_coverage(
        index=index,
        rows=rows,
        source_call_count=len(plans),
    )
    selector.mark_chain._publish_private_observation(
        index=index,
        payload={
            "schema": "prophet.live_marks/v1",
            "asof_utc": observed_at,
            "session_date": session_date,
            "marks": {},
            "coverage": coverage,
        },
        evidence_rows=rows,
    )
    ledger_path = lifecycle_root / "canonical_ledger/ledger.jsonl"
    summary = selector.lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    assert summary["status"] == "advanced"
    assert summary["enrollment_count"] == len(plans)

    inputs = selector.EvidenceInputs(
        w1a_receipt_root=w1a_inputs.w1a_receipt_root,
        mark_root=mark_root,
        lifecycle_root=lifecycle_root,
    )
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=head,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    complete = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    complete, _plans = _drain_cold_occurrence(
        root, inputs, complete, row_limit=64
    )
    high = selector._load_evidence_high_water(
        root, complete["evidence_high_water"]
    )
    assert high["phase"] == "COMPLETE"
    return inputs, complete


def _occurrence_mark_plan(
    *, plan_id: str = "SOFI-BULL-20260803", phase: str
) -> dict:
    return {
        "id": plan_id,
        "asset": "SOFI",
        "phase": phase,
        "closed": False,
        "plan_asof": "2026-08-03",
        "recorded_at": "2026-08-03",
        "entry_date": "2026-08-03",
        "option_contract": {
            "right": "C",
            "strike": 16.0,
            "expiry": "2026-10-16",
            "entry_premium": 1.8,
            "freshness": "EOD mark",
        },
    }


def _emit_occurrence_mark(
    monkeypatch: pytest.MonkeyPatch,
    mark_root: Path,
    *,
    observed_at: str,
    phase: str,
    plan_id: str = "SOFI-BULL-20260803",
    additional_plan_ids: tuple[str, ...] = (),
    mid: float = 3.0,
) -> dict:
    monkeypatch.setenv("PROPHET_OPTION_EVIDENCE_STATE_ROOT", str(mark_root))
    session_date = "2026-08-11"
    plans = [
        _occurrence_mark_plan(plan_id=item, phase=phase)
        for item in (plan_id, *additional_plan_ids)
    ]
    index = {
        "schema": "prophet.index/v1",
        "asof": session_date,
        "recorded_at": session_date,
        "plans": plans,
    }
    session = date.fromisoformat(session_date)
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    quote_clock = observed - timedelta(minutes=1)
    quote, quote_reason = selector.mark_chain._validated_quote(
        {
            "bid": mid - 0.05,
            "ask": mid + 0.05,
            "last": mid,
            "quote_ts_utc": quote_clock.isoformat(),
            "trade_ts_utc": (quote_clock + timedelta(seconds=1)).isoformat(),
            "source_sequence": 7,
        },
        observed_at=observed,
        session_date=session,
    )
    rows = []
    for plan in plans:
        contract, contract_reason = selector.mark_chain._plan_contract(
            plan, session_date=session
        )
        rows.append(
            selector.mark_chain._plan_evidence_row(
                plan,
                contract=contract,
                contract_reason=contract_reason,
                quote=quote,
                quote_reason=quote_reason,
            )
        )
    coverage = selector.mark_chain._evidence_coverage(
        index=index, rows=rows, source_call_count=len(plans)
    )
    return selector.mark_chain._publish_private_observation(
        index=index,
        payload={
            "schema": "prophet.live_marks/v1",
            "asof_utc": observed_at,
            "session_date": session_date,
            "marks": {},
            "coverage": coverage,
        },
        evidence_rows=rows,
    )


def _refresh_occurrence_ledger(
    ledger_path: Path, *, source_commit: str = "a" * 40
) -> dict:
    body = ledger_path.read_bytes()
    rows = sum(
        bool(line.strip()) and not line.lstrip().startswith(b"#")
        for line in body.splitlines()
    )
    receipt = selector.lifecycle._ledger_receipt(
        body,
        [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ],
        source_commit=source_commit,
    )
    assert receipt["row_count"] == rows
    receipt_path = ledger_path.parent / "receipt.json"
    receipt_path.write_bytes(selector.lifecycle._canonical_json_bytes(receipt))
    receipt_path.chmod(0o600)
    return receipt


def _occurrence_producer_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    activation_phase: str = "pre_trigger",
) -> tuple[selector.EvidenceInputs, Path]:
    mark_root = tmp_path / "occurrence-marks"
    lifecycle_root = tmp_path / "occurrence-lifecycle"
    lifecycle_root.mkdir(mode=0o700)
    lifecycle_root.chmod(0o700)
    lifecycle_lock = lifecycle_root / ".ledger.lock"
    lifecycle_lock.write_bytes(b"")
    lifecycle_lock.chmod(0o600)
    ledger_root = lifecycle_root / "canonical_ledger"
    ledger_root.mkdir(mode=0o700)
    ledger_root.chmod(0o700)
    ledger_path = ledger_root / "ledger.jsonl"
    ledger_path.write_text("# canonical occurrence ledger\n", encoding="utf-8")
    ledger_path.chmod(0o600)
    _refresh_occurrence_ledger(ledger_path)
    _emit_occurrence_mark(
        monkeypatch,
        mark_root,
        observed_at="2026-08-11T14:00:00+00:00",
        phase=activation_phase,
    )
    assert selector.lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=mark_root,
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_root / "receipt.json",
    )["status"] == "activated"
    return (
        selector.EvidenceInputs(
            mark_root=mark_root, lifecycle_root=lifecycle_root
        ),
        ledger_path,
    )


@pytest.mark.parametrize(
    ("stage", "recovery_needs_plan"),
    (
        ("after_intent_attempt", True),
        ("after_intent_before_seal", True),
        ("after_intent_seal", False),
    ),
)
def test_receipt_only_wal_crashes_are_abandoned_or_recovered_exactly(
    tmp_path: Path,
    stage: str,
    recovery_needs_plan: bool,
) -> None:
    root = tmp_path / stage
    source = _source([])
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == stage:
            raise RuntimeError("WAL crash")

    with pytest.raises(RuntimeError, match="WAL crash"):
        selector.commit_cycle(root, plan, hook=crash)
    assert selector._load_head(root) is None
    recovered = selector.commit_cycle(root, plan if recovery_needs_plan else None)
    assert recovered == plan.head
    assert selector.authenticate_store(root)[0] == plan.head


def test_deleted_authoritative_intent_is_detected_before_replanning(
    tmp_path: Path,
) -> None:
    root = tmp_path / "deleted-authoritative-intent"
    source = _source([])
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == "after_intent_seal":
            raise RuntimeError("sealed")

    with pytest.raises(RuntimeError, match="sealed"):
        selector.commit_cycle(root, plan, hook=crash)
    (root / selector.INTENT_FILE).unlink()
    (root / selector.INTENT_ATTEMPT_FILE).unlink()
    before = {path: path.read_bytes() for path in root.rglob("*.json")}
    with pytest.raises(selector.SparseSelectorError, match="orphan authoritative"):
        selector.commit_cycle(root, plan)
    assert {path: path.read_bytes() for path in root.rglob("*.json")} == before


def test_missing_intent_with_attempt_and_parent_seal_mutates_nothing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "missing-intent-with-attempt"
    source = _source([])
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )

    def crash(point: str) -> None:
        if point == "after_intent_seal":
            raise RuntimeError("sealed")

    with pytest.raises(RuntimeError, match="sealed"):
        selector.commit_cycle(root, plan, hook=crash)
    (root / selector.INTENT_FILE).unlink()
    prepare = root / selector.INTENT_PREPARE_FILE
    prepare.write_bytes(b"untrusted-prepare")
    prepare.chmod(0o600)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    with pytest.raises(selector.SparseSelectorError, match="orphan authoritative"):
        selector.commit_cycle(root, plan)
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_prestage_first_install_is_0600_and_repairs_link_crash(
    tmp_path: Path,
) -> None:
    root = selector.validate_private_root(tmp_path / "prestage", create=True)
    body = selector.canonical_bytes({"schema": "test.prestage/v1", "value": 1})
    path = root / "evidence" / "prestage.json"
    path.parent.mkdir(mode=0o700)
    with selector._store_lock(root):
        prior_umask = os.umask(0o777)
        try:
            selector._prestage_immutable(path, body, root=root)
        finally:
            os.umask(prior_umask)
        assert path.read_bytes() == body
        assert path.stat().st_mode & 0o777 == 0o600
        temporary = path.parent / f".{path.name}.prestage"
        os.link(path, temporary)
        assert path.stat().st_nlink == 2
        selector._prestage_immutable(path, body, root=root)
        assert not temporary.exists()
        assert path.stat().st_nlink == 1


@pytest.mark.parametrize(
    "stage",
    (
        "before_batch_file_fsync",
        "after_batch_file_fsync",
        "before_batch_object_link",
        "after_batch_object_link",
        "before_batch_parent_fsync",
        "after_batch_parent_fsync",
        "after_prestage",
    ),
)
def test_batch_immutable_crashes_remain_pre_authority_and_retry_exact(
    tmp_path: Path,
    stage: str,
) -> None:
    source = _source([[_episode(f"batch-{stage}", "2026-08-12T13:31:00Z")]])
    root = tmp_path / stage
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    crashed = False

    def crash(point: str) -> None:
        nonlocal crashed
        if point == stage and not crashed:
            crashed = True
            raise RuntimeError("batch durability crash")

    with pytest.raises(RuntimeError, match="batch durability crash"):
        selector.commit_cycle(root, plan, hook=crash)
    assert crashed is True
    assert selector._load_head(root) is None
    assert not (root / selector.INTENT_FILE).exists()
    assert not selector._object_path(
        root, selector._intent_seal_key(plan.intent)
    ).exists()

    recovered = selector.commit_cycle(root, plan)
    assert recovered == plan.head
    assert selector.authenticate_store(root)[0] == plan.head


def test_batch_immutable_fsyncs_new_files_and_each_parent_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source([[_episode("batch-fsync-count", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "batch-fsync-count"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    parent_paths = {
        selector._object_path(root, item.key).parent for item in plan.objects
    }
    with selector._store_lock(root):
        for parent_path in parent_paths:
            selector._require_private_directory(
                parent_path, root=root, create=True
            )
        parent_identities = {
            (parent_path.stat().st_dev, parent_path.stat().st_ino)
            for parent_path in parent_paths
        }
        real_fsync = selector.os.fsync

        def observe_batch() -> tuple[int, dict[tuple[int, int], int]]:
            regular_calls = 0
            directory_calls: dict[tuple[int, int], int] = {}

            def counted_fsync(descriptor: int) -> None:
                nonlocal regular_calls
                metadata = os.fstat(descriptor)
                identity = (metadata.st_dev, metadata.st_ino)
                if stat.S_ISDIR(metadata.st_mode):
                    directory_calls[identity] = directory_calls.get(identity, 0) + 1
                elif stat.S_ISREG(metadata.st_mode):
                    regular_calls += 1
                real_fsync(descriptor)

            with monkeypatch.context() as scoped:
                scoped.setattr(selector.os, "fsync", counted_fsync)
                selector._prestage_immutable_batch(root, plan.objects)
            return regular_calls, directory_calls

        new_file_calls, new_parent_calls = observe_batch()
        assert new_file_calls == len(plan.objects)
        assert new_parent_calls == {
            identity: 1 for identity in parent_identities
        }

        existing_file_calls, existing_parent_calls = observe_batch()
        assert existing_file_calls == 0
        assert existing_parent_calls == {
            identity: 1 for identity in parent_identities
        }


def test_batch_immutable_conflict_stays_pre_authority(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("batch-conflict", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "batch-conflict"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    target = selector._object_path(root, plan.objects[0].key)
    selector._write_immutable(target, b'{"conflict":true}', root=root)
    with pytest.raises(selector.SparseSelectorError, match="conflicts"):
        selector.commit_cycle(root, plan)
    assert selector._load_head(root) is None
    assert not (root / selector.INTENT_FILE).exists()

    target.unlink()
    recovered = selector.commit_cycle(root, plan)
    assert recovered == plan.head
    assert selector.authenticate_store(root)[0] == plan.head


def test_batch_immutable_parent_rebind_stays_pre_authority_and_retries(
    tmp_path: Path,
) -> None:
    source = _source([[_episode("batch-rebind", "2026-08-12T13:31:00Z")]])
    root = tmp_path / "batch-rebind"
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:00:00Z",
        clock=_clock(),
        runtime_armed=True,
    )
    parent = selector._object_path(root, plan.objects[0].key).parent
    saved = parent.with_name(f"{parent.name}.saved")

    def rebind(point: str) -> None:
        if point == "before_batch_parent_fsync":
            parent.rename(saved)
            parent.mkdir(mode=0o700)
            parent.chmod(0o700)

    with pytest.raises(selector.SparseSelectorError, match="rebound"):
        selector.commit_cycle(root, plan, hook=rebind)
    assert selector._load_head(root) is None
    assert not (root / selector.INTENT_FILE).exists()
    parent.rmdir()
    saved.rename(parent)

    recovered = selector.commit_cycle(root, plan)
    assert recovered == plan.head
    assert selector.authenticate_store(root)[0] == plan.head


def test_non_genesis_pin_is_exact_and_source_drift_stays_pre_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([])
    root = tmp_path / "pin"
    parent = _commit_first(root, source)
    inputs, state, mark_pointer = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    assert plan.intent["objects"] == [item.receipt for item in plan.objects]
    assert all("value" not in receipt for receipt in plan.intent["objects"])
    assert selector._source_expected_state(plan.head) == selector._source_expected_state(parent)
    assert {
        key: value
        for key, value in selector._runtime_expected_state(plan.head).items()
        if key != "evidence_high_water"
    } == {
        key: value
        for key, value in selector._runtime_expected_state(parent).items()
        if key != "evidence_high_water"
    }

    changed_state = selector.lifecycle._make_state(
        activation=state["activation"],
        lifecycle_head=state["lifecycle_head"],
        mark_cursor={**mark_pointer, "sha256": "6" * 64},
        ledger_cursor=state["ledger_cursor"],
        enrollments={},
        terminals={},
        latest_marks={},
    )

    def drift(point: str) -> None:
        if point == "after_prestage":
            path = Path(inputs.lifecycle_root) / "current.json"
            path.write_bytes(selector.lifecycle._canonical_json_bytes(changed_state))
            path.chmod(0o600)

    with pytest.raises(selector.EvidenceGenerationDrift, match="changed before PIN"):
        selector.commit_cycle(root, plan, evidence_inputs=inputs, hook=drift)
    assert selector._load_head(root) == parent
    assert not (root / selector.INTENT_FILE).exists()

    state_path = Path(inputs.lifecycle_root) / "current.json"
    state_path.write_bytes(selector.lifecycle._canonical_json_bytes(state))
    state_path.chmod(0o600)
    committed = selector.commit_cycle(root, plan, evidence_inputs=inputs)
    assert committed == plan.head
    assert selector._load_evidence_high_water(
        root, committed["evidence_high_water"]
    )["phase"] == "AUDIT_PINNED"


def test_pin_uses_only_anchored_producer_reads_and_persists_root_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "anchored-pin"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)

    def path_read_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("PIN escaped its anchored descriptor")

    monkeypatch.setattr(selector.mark_chain, "_read_private_file", path_read_forbidden)
    monkeypatch.setattr(selector.mark_chain, "_private_ledger_lock", path_read_forbidden)
    monkeypatch.setattr(selector.lifecycle, "_load_state", path_read_forbidden)
    monkeypatch.setattr(selector.lifecycle, "_load_activation_boundary", path_read_forbidden)
    monkeypatch.setenv("PROPHET_LEDGER_PATH", str(tmp_path / "hostile-ledger.jsonl"))
    monkeypatch.setenv(
        "PROPHET_LEDGER_RECEIPT_PATH", str(tmp_path / "hostile-receipt.json")
    )
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    snapshot = next(
        item.value
        for item in plan.objects
        if item.value["schema"]
        == "options.sparse_selector_evidence_source_snapshot/v1"
    )
    for name, configured in (
        ("mark", inputs.mark_root),
        ("lifecycle", inputs.lifecycle_root),
    ):
        receipt = snapshot["producer_roots"][name]
        normalized = selector._absolute_private_path(Path(configured))
        assert receipt["path_sha256"] == selector._sha256(
            os.fsencode(str(normalized))
        )
        assert set(receipt) == {"path_sha256"}


def test_pin_rejects_aliased_and_nested_producer_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root-overlap-pin"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    with pytest.raises(selector.SparseSelectorError, match="distinct and non-nested"):
        selector._plan_evidence_capture_transition(
            root=root,
            head=parent,
            evidence_inputs=selector.EvidenceInputs(
                mark_root=inputs.mark_root,
                lifecycle_root=inputs.mark_root,
            ),
            clock=_clock("2026-08-12T14:05:00Z"),
        )

    with pytest.raises(selector.SparseSelectorError, match="distinct and non-nested"):
        selector._plan_evidence_capture_transition(
            root=root,
            head=parent,
            evidence_inputs=selector.EvidenceInputs(
                mark_root=inputs.mark_root,
                lifecycle_root=root,
            ),
            clock=_clock("2026-08-12T14:05:00Z"),
        )

    selector_nested = root / "nested-producer"
    selector_nested.mkdir(mode=0o700)
    selector_nested.chmod(0o700)
    selector_nested_lock = selector_nested / ".ledger.lock"
    selector_nested_lock.write_bytes(b"")
    selector_nested_lock.chmod(0o600)
    with pytest.raises(selector.SparseSelectorError, match="distinct and non-nested"):
        selector._plan_evidence_capture_transition(
            root=root,
            head=parent,
            evidence_inputs=selector.EvidenceInputs(
                mark_root=inputs.mark_root,
                lifecycle_root=selector_nested,
            ),
            clock=_clock("2026-08-12T14:05:00Z"),
        )

    nested = Path(inputs.mark_root) / "nested-lifecycle"
    nested.mkdir(mode=0o700)
    nested.chmod(0o700)
    lock = nested / ".ledger.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    with pytest.raises(selector.SparseSelectorError, match="distinct and non-nested"):
        selector._plan_evidence_capture_transition(
            root=root,
            head=parent,
            evidence_inputs=selector.EvidenceInputs(
                mark_root=inputs.mark_root,
                lifecycle_root=nested,
            ),
            clock=_clock("2026-08-12T14:05:00Z"),
        )


def test_anchored_sources_reject_ancestor_rebind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = tmp_path / "producer-container"
    container.mkdir(mode=0o700)
    container.chmod(0o700)
    inputs, _state, _mark = _mock_evidence_capture_sources(container, monkeypatch)
    moved = tmp_path / "producer-container-moved"
    with pytest.raises(selector.SparseSelectorError, match="rebound"):
        with selector._anchored_evidence_sources(
            Path(inputs.mark_root), Path(inputs.lifecycle_root)
        ):
            container.rename(moved)
            container.mkdir(mode=0o700)
            container.chmod(0o700)


def test_pin_root_rebind_after_prestage_stays_pre_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root-rebind-pin"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    lifecycle_root = Path(inputs.lifecycle_root)
    moved = tmp_path / "capture-lifecycle-original"

    def rebind(point: str) -> None:
        if point == "after_prestage":
            lifecycle_root.rename(moved)
            shutil.copytree(moved, lifecycle_root, copy_function=shutil.copy2)

    with pytest.raises(selector.SparseSelectorError, match="rebound"):
        selector.commit_cycle(root, plan, evidence_inputs=inputs, hook=rebind)
    assert selector._load_head(root) == parent
    assert not (root / selector.INTENT_FILE).exists()


def test_pin_accepts_exact_root_clone_before_authoritative_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root-clone-pin"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    lifecycle_root = Path(inputs.lifecycle_root)
    moved = tmp_path / "capture-lifecycle-before-clone"
    lifecycle_root.rename(moved)
    shutil.copytree(moved, lifecycle_root, copy_function=shutil.copy2)
    committed = selector.commit_cycle(root, plan, evidence_inputs=inputs)
    assert committed == plan.head


def test_pin_lock_swap_after_prestage_stays_pre_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "lock-swap-pin"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    lock = Path(inputs.lifecycle_root) / ".ledger.lock"
    saved = Path(inputs.lifecycle_root) / ".ledger.lock.saved"

    def swap(point: str) -> None:
        if point == "after_prestage":
            lock.rename(saved)
            lock.write_bytes(b"")
            lock.chmod(0o600)

    with pytest.raises(selector.SparseSelectorError, match="lock path"):
        selector.commit_cycle(root, plan, evidence_inputs=inputs, hook=swap)
    assert selector._load_head(root) == parent
    assert not (root / selector.INTENT_FILE).exists()


def test_pin_activation_boundary_swap_after_prestage_stays_pre_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "activation-swap-pin"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    boundary_path = Path(inputs.lifecycle_root) / "activation_boundary.json"
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    boundary["mark_boundary_observed_at_utc"] = "2026-08-12T14:00:01Z"
    boundary["boundary_id"] = selector.lifecycle._activation_boundary_identity(
        boundary
    )
    selector.lifecycle._validate_activation_boundary(boundary)

    def swap(point: str) -> None:
        if point == "after_prestage":
            boundary_path.write_bytes(
                selector.lifecycle._canonical_json_bytes(boundary)
            )
            boundary_path.chmod(0o600)

    with pytest.raises(selector.SparseSelectorError, match="authentic prefixes"):
        selector.commit_cycle(root, plan, evidence_inputs=inputs, hook=swap)
    assert selector._load_head(root) == parent
    assert not (root / selector.INTENT_FILE).exists()


@pytest.mark.parametrize(
    ("stage", "authority_expected"),
    (
        ("after_intent_attempt", False),
        ("after_intent_before_seal", False),
        ("after_intent_seal", True),
    ),
)
def test_pin_root_swap_at_wal_boundaries_has_exact_authority_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    authority_expected: bool,
) -> None:
    root = tmp_path / f"root-swap-{stage}"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    lifecycle_root = Path(inputs.lifecycle_root)
    moved = tmp_path / f"capture-lifecycle-{stage}-original"

    def swap(point: str) -> None:
        if point == stage:
            lifecycle_root.rename(moved)
            shutil.copytree(moved, lifecycle_root, copy_function=shutil.copy2)

    if authority_expected:
        assert selector.commit_cycle(
            root, plan, evidence_inputs=inputs, hook=swap
        ) == plan.head
        assert selector._load_head(root) == plan.head
        assert not (root / selector.INTENT_FILE).exists()
    else:
        with pytest.raises(selector.SparseSelectorError, match="rebound"):
            selector.commit_cycle(root, plan, evidence_inputs=inputs, hook=swap)
        assert selector._load_head(root) == parent
        assert not selector._object_path(
            root, selector._intent_seal_key(plan.intent)
        ).exists()


@pytest.mark.parametrize(
    ("stage", "authority_expected"),
    (
        ("after_intent_attempt", False),
        ("after_intent_before_seal", False),
        ("after_intent_seal", True),
    ),
)
def test_pin_lock_swap_at_wal_boundaries_has_exact_authority_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    authority_expected: bool,
) -> None:
    root = tmp_path / f"lock-swap-{stage}"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    lock = Path(inputs.lifecycle_root) / ".ledger.lock"
    saved = Path(inputs.lifecycle_root) / f".ledger.lock.{stage}.saved"

    def swap(point: str) -> None:
        if point == stage:
            lock.rename(saved)
            lock.write_bytes(b"")
            lock.chmod(0o600)

    if authority_expected:
        assert selector.commit_cycle(
            root, plan, evidence_inputs=inputs, hook=swap
        ) == plan.head
        assert selector._load_head(root) == plan.head
        assert not (root / selector.INTENT_FILE).exists()
    else:
        with pytest.raises(selector.SparseSelectorError, match="lock path"):
            selector.commit_cycle(root, plan, evidence_inputs=inputs, hook=swap)
        assert selector._load_head(root) == parent
        assert not selector._object_path(
            root, selector._intent_seal_key(plan.intent)
        ).exists()


def test_previous_high_water_must_be_typed_and_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source([])
    root = tmp_path / "previous-high-water"
    parent = _commit_first(root, source)
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    plan = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    selector.commit_cycle(root, plan, evidence_inputs=inputs)
    first_incomplete_pointer = copy.deepcopy(plan.head["evidence_high_water"])
    complete, _plans = _drain_cold_occurrence(root, inputs, plan.head)
    second_pin = selector._plan_evidence_capture_transition(
        root=root,
        head=complete,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T15:00:00Z"),
    )
    second_head = selector.commit_cycle(
        root, second_pin, evidence_inputs=inputs
    )
    pinned = selector._load_evidence_high_water(
        root, second_head["evidence_high_water"]
    )
    assert pinned["phase"] == "AUDIT_PINNED"
    assert pinned["previous_complete"] == complete["evidence_high_water"]
    forged = copy.deepcopy(pinned)
    forged["previous_complete"] = first_incomplete_pointer
    forged["high_water_id"] = selector._content_id(
        "osehw_", forged, field="high_water_id"
    )
    forged_object = selector.PlannedObject(
        key=f"{selector.EVIDENCE_AUDIT_NAMESPACE}/{forged['high_water_id']}.json",
        value=selector.validate_runtime_object(forged, label="forged child high-water"),
    )
    with selector._store_lock(root):
        selector._prestage_immutable(
            selector._object_path(root, forged_object.key),
            forged_object.body,
            root=root,
        )
        with pytest.raises(selector.SparseSelectorError, match="not exact and complete"):
            selector._load_evidence_high_water(root, forged_object.pointer)


def _drain_cold_occurrence(
    root: Path,
    inputs: selector.EvidenceInputs,
    head: dict,
    *,
    row_limit: int = 64,
) -> tuple[dict, list[selector.CyclePlan]]:
    plans: list[selector.CyclePlan] = []
    for ordinal in range(32):
        high = selector._load_evidence_high_water(
            root, head["evidence_high_water"]
        )
        if high["phase"] == "COMPLETE":
            return head, plans
        plan = selector._plan_evidence_occurrence_transition(
            root=root,
            head=head,
            evidence_inputs=inputs,
            clock=_clock(f"2026-08-12T14:{6 + ordinal:02d}:00Z"),
            row_limit=row_limit,
        )
        assert len(plan.objects) + 1 <= selector.MAX_SOURCE_OBJECTS_PER_CYCLE
        assert selector._transition_footprint_bytes(plan.intent, plan.objects) <= (
            selector.MAX_SOURCE_INTENT_BYTES
        )
        head = selector.commit_cycle(
            root, plan, evidence_inputs=inputs
        )
        plans.append(plan)
    raise AssertionError("cold occurrence replay did not complete")


def test_cold_occurrence_activation_only_reaches_exact_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "cold-activation"
    parent = _commit_first(root, _source([]))
    inputs, state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    head, plans = _drain_cold_occurrence(root, inputs, head)
    high = selector._load_evidence_high_water(root, head["evidence_high_water"])
    assert high["phase"] == "COMPLETE"
    assert high["occurrence_stage"] == "DONE"
    assert high["ledger_capture_bytes"] == state["ledger_cursor"]["bytes"]
    assert high["ledger_replay_bytes"] == state["ledger_cursor"]["bytes"]
    assert high["ledger_replay_rows"] == state["ledger_cursor"]["row_count"]
    assert high["replay_state_id"] == state["state_id"]
    assert all(plan.intent["audit_window"]["row_limit"] == 64 for plan in plans)
    assert selector.authenticate_store(root, evidence_inputs=inputs)[0] == head


def _append_occurrence_close(
    ledger_path: Path, *, plan_id: str = "SOFI-BULL-20260803"
) -> None:
    row = {
        "schema": "prophet.ledger/v1",
        "id": plan_id,
        "close_date": "2026-08-11",
        "outcome": "T1_HIT",
        "asof": "2026-08-11",
        "option_result_pct": None,
    }
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
    _refresh_occurrence_ledger(ledger_path)


def _pin_and_drain_occurrence(
    root: Path,
    inputs: selector.EvidenceInputs,
) -> tuple[dict, dict, list[selector.CyclePlan]]:
    parent = _commit_first(root, _source([]))
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    head, plans = _drain_cold_occurrence(root, inputs, head, row_limit=2)
    high = selector._load_evidence_high_water(root, head["evidence_high_water"])
    return head, high, plans


def test_cold_occurrence_same_edge_mark_and_close_never_enrolls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, ledger_path = _occurrence_producer_roots(tmp_path, monkeypatch)
    _append_occurrence_close(ledger_path)
    _emit_occurrence_mark(
        monkeypatch,
        Path(inputs.mark_root),
        observed_at="2026-08-11T14:05:00+00:00",
        phase="triggered_pre_t1",
    )
    summary = selector.lifecycle.advance_lifecycle(
        lifecycle_root=Path(inputs.lifecycle_root),
        mark_root=Path(inputs.mark_root),
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    assert summary["status"] == "advanced"
    assert summary["enrollment_count"] == 0
    head, high, plans = _pin_and_drain_occurrence(
        tmp_path / "same-edge-selector", inputs
    )
    replay = selector._load_evidence_replay_state(
        tmp_path / "same-edge-selector",
        high["replay_state"],
        snapshot=high["snapshot"],
    )["state"]
    assert replay["enrollments"] == {}
    assert replay["terminals"] == {}
    assert high["phase"] == "COMPLETE"
    assert any(
        plan.intent["audit_window"]["stage"] == "OCCURRENCE_EDGE_FINALIZE"
        for plan in plans
    )
    assert selector.authenticate_store(
        tmp_path / "same-edge-selector", evidence_inputs=inputs
    )[0] == head


def test_cold_occurrence_split_edges_enroll_then_terminal_and_ignore_outgoing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, ledger_path = _occurrence_producer_roots(tmp_path, monkeypatch)
    _emit_occurrence_mark(
        monkeypatch,
        Path(inputs.mark_root),
        observed_at="2026-08-11T14:05:00+00:00",
        phase="triggered_pre_t1",
    )
    enrolled = selector.lifecycle.advance_lifecycle(
        lifecycle_root=Path(inputs.lifecycle_root),
        mark_root=Path(inputs.mark_root),
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    assert enrolled["enrollment_count"] == 1
    _append_occurrence_close(ledger_path)
    terminal = selector.lifecycle.advance_lifecycle(
        lifecycle_root=Path(inputs.lifecycle_root),
        mark_root=Path(inputs.mark_root),
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    assert terminal["terminal_count"] == 1
    lifecycle_root = Path(inputs.lifecycle_root)
    target = selector.lifecycle._load_state(lifecycle_root)
    assert target is not None

    # A producer crash may leave a valid outgoing boundary without advancing
    # current.json. The selector must stop at the exact pinned current state.
    next_mark_pointer = _emit_occurrence_mark(
        monkeypatch,
        Path(inputs.mark_root),
        observed_at="2026-08-11T14:10:00+00:00",
        phase="triggered_pre_t1",
        mid=3.2,
    )
    next_mark = selector._load_frozen_mark_observation(
        Path(inputs.mark_root), next_mark_pointer
    )
    orphan_candidate = selector.lifecycle._make_state(
        activation=target["activation"],
        lifecycle_head=target["lifecycle_head"],
        mark_cursor=next_mark_pointer,
        ledger_cursor=target["ledger_cursor"],
        enrollments=target["enrollments"],
        terminals=target["terminals"],
        latest_marks=target["latest_marks"],
    )
    orphan = selector.lifecycle._make_advance_boundary(
        state=target,
        mark_pointer=next_mark_pointer,
        mark_observation=next_mark,
        ledger_receipt=target["ledger_cursor"],
        candidate=orphan_candidate,
        events=[],
    )
    selector.lifecycle._write_advance_boundary(lifecycle_root, target, orphan)
    _append_occurrence_close(ledger_path, plan_id="UNRELATED-CLOSED-PLAN")

    root = tmp_path / "split-edge-selector"
    head, high, plans = _pin_and_drain_occurrence(root, inputs)
    replay = selector._load_evidence_replay_state(
        root, high["replay_state"], snapshot=high["snapshot"]
    )["state"]
    assert replay == target
    assert set(replay["enrollments"]) == {"SOFI-BULL-20260803"}
    assert set(replay["terminals"]) == {"SOFI-BULL-20260803"}
    assert replay["latest_marks"] == {}
    assert high["phase"] == "COMPLETE"
    assert high["ledger_capture_bytes"] > high["ledger_replay_bytes"]
    assert sum(
        plan.intent["audit_window"]["stage"] == "OCCURRENCE_EDGE_INIT"
        for plan in plans
    ) == 2
    assert selector.authenticate_store(root, evidence_inputs=inputs)[0] == head


@pytest.mark.parametrize("mutation", ("missing", "reordered"))
def test_cold_occurrence_rejects_missing_or_reordered_boundary_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    inputs, ledger_path = _occurrence_producer_roots(tmp_path, monkeypatch)
    lifecycle_root = Path(inputs.lifecycle_root)
    base = selector.lifecycle._load_state(lifecycle_root)
    assert base is not None
    _emit_occurrence_mark(
        monkeypatch,
        Path(inputs.mark_root),
        observed_at="2026-08-11T14:05:00+00:00",
        phase="triggered_pre_t1",
        additional_plan_ids=("SOFI-BULL-20260804",),
    )
    advanced = selector.lifecycle.advance_lifecycle(
        lifecycle_root=lifecycle_root,
        mark_root=Path(inputs.mark_root),
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    assert advanced["enrollment_count"] == 2
    boundary_path = (
        lifecycle_root / "advance_boundaries" / f"{base['state_id']}.json"
    )
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    assert len(boundary["event_pointers"]) == 2
    if mutation == "missing":
        boundary["event_pointers"] = []
        boundary["candidate_lifecycle_head"] = base["lifecycle_head"]
    else:
        boundary["event_pointers"].reverse()
        boundary["candidate_lifecycle_head"] = boundary["event_pointers"][-1]
    boundary["boundary_id"] = selector.lifecycle._advance_boundary_identity(
        boundary
    )
    selector.lifecycle._validate_advance_boundary(boundary)
    boundary_path.unlink()
    boundary_path.write_bytes(selector.lifecycle._canonical_json_bytes(boundary))
    boundary_path.chmod(0o600)

    root = tmp_path / f"forged-{mutation}-selector"
    parent = _commit_first(root, _source([]))
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    with pytest.raises(
        selector.SparseSelectorError,
        match="orphan lifecycle event|differs from boundary order",
    ):
        _drain_cold_occurrence(root, inputs, head, row_limit=2)


def _install_synthetic_occurrence_edge(
    lifecycle_root: Path,
    *,
    base: dict,
    mark_pointer: dict,
    mark_observation: dict,
    ledger_receipt: dict,
    candidate: dict,
    events: list[dict],
) -> None:
    boundary = selector.lifecycle._make_advance_boundary(
        state=base,
        mark_pointer=mark_pointer,
        mark_observation=mark_observation,
        ledger_receipt=ledger_receipt,
        candidate=candidate,
        events=events,
    )
    selector.lifecycle._write_advance_boundary(lifecycle_root, base, boundary)
    if events:
        selector.lifecycle._write_events(lifecycle_root, events)
    selector.lifecycle._write_state(lifecycle_root, candidate)


@pytest.mark.parametrize(
    "forgery",
    ("activation_mark_enrollment", "omitted_enrollment", "skipped_first", "missing_terminal"),
)
def test_cold_occurrence_rejects_source_derived_completeness_forgery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    forgery: str,
) -> None:
    inputs, ledger_path = _occurrence_producer_roots(
        tmp_path,
        monkeypatch,
        activation_phase=(
            "triggered_pre_t1"
            if forgery == "activation_mark_enrollment"
            else "pre_trigger"
        ),
    )
    lifecycle_root = Path(inputs.lifecycle_root)
    mark_root = Path(inputs.mark_root)
    base = selector.lifecycle._load_state(lifecycle_root)
    assert base is not None

    if forgery == "activation_mark_enrollment":
        mark_pointer = base["mark_cursor"]
        observation = selector._load_frozen_mark_observation(
            mark_root, mark_pointer
        )
        event = selector._frozen_enrollment_event(
            row=observation["rows"][0],
            mark_pointer=mark_pointer,
            observation=observation,
            previous=base["lifecycle_head"],
        )
        event_pointer = selector.lifecycle._event_pointer(event)
        plan_id = event["payload"]["plan"]["id"]
        candidate = selector.lifecycle._make_state(
            activation=base["activation"],
            lifecycle_head=event_pointer,
            mark_cursor=mark_pointer,
            ledger_cursor=base["ledger_cursor"],
            enrollments={plan_id: event_pointer},
            terminals={},
            latest_marks={
                plan_id: {
                    "contract_occ_symbol": event["payload"]["contract"]["occ_symbol"],
                    "contract_drift": False,
                    "plan_identity_drift": False,
                    "sessions": {observation["session_date"]: mark_pointer},
                }
            },
        )
        _install_synthetic_occurrence_edge(
            lifecycle_root,
            base=base,
            mark_pointer=mark_pointer,
            mark_observation=observation,
            ledger_receipt=base["ledger_cursor"],
            candidate=candidate,
            events=[event],
        )
    elif forgery in {"omitted_enrollment", "skipped_first"}:
        first = _emit_occurrence_mark(
            monkeypatch,
            mark_root,
            observed_at="2026-08-11T14:05:00+00:00",
            phase="triggered_pre_t1",
        )
        mark_pointer = first
        if forgery == "skipped_first":
            mark_pointer = _emit_occurrence_mark(
                monkeypatch,
                mark_root,
                observed_at="2026-08-11T14:10:00+00:00",
                phase="triggered_pre_t1",
                mid=3.2,
            )
        observation = selector._load_frozen_mark_observation(
            mark_root, mark_pointer
        )
        if forgery == "omitted_enrollment":
            events = []
            enrollments = {}
            latest = {}
            lifecycle_head = base["lifecycle_head"]
        else:
            event = selector._frozen_enrollment_event(
                row=observation["rows"][0],
                mark_pointer=mark_pointer,
                observation=observation,
                previous=base["lifecycle_head"],
            )
            event_pointer = selector.lifecycle._event_pointer(event)
            plan_id = event["payload"]["plan"]["id"]
            events = [event]
            enrollments = {plan_id: event_pointer}
            latest = {
                plan_id: {
                    "contract_occ_symbol": event["payload"]["contract"]["occ_symbol"],
                    "contract_drift": False,
                    "plan_identity_drift": False,
                    "sessions": {observation["session_date"]: mark_pointer},
                }
            }
            lifecycle_head = event_pointer
        candidate = selector.lifecycle._make_state(
            activation=base["activation"],
            lifecycle_head=lifecycle_head,
            mark_cursor=mark_pointer,
            ledger_cursor=base["ledger_cursor"],
            enrollments=enrollments,
            terminals={},
            latest_marks=latest,
        )
        _install_synthetic_occurrence_edge(
            lifecycle_root,
            base=base,
            mark_pointer=mark_pointer,
            mark_observation=observation,
            ledger_receipt=base["ledger_cursor"],
            candidate=candidate,
            events=events,
        )
    else:
        _emit_occurrence_mark(
            monkeypatch,
            mark_root,
            observed_at="2026-08-11T14:05:00+00:00",
            phase="triggered_pre_t1",
        )
        enrolled = selector.lifecycle.advance_lifecycle(
            lifecycle_root=lifecycle_root,
            mark_root=mark_root,
            ledger_path=ledger_path,
            ledger_receipt_path=ledger_path.parent / "receipt.json",
        )
        assert enrolled["enrollment_count"] == 1
        base = selector.lifecycle._load_state(lifecycle_root)
        assert base is not None
        _append_occurrence_close(ledger_path)
        ledger_receipt = json.loads(
            (ledger_path.parent / "receipt.json").read_text(encoding="utf-8")
        )
        observation = selector._load_frozen_mark_observation(
            mark_root, base["mark_cursor"]
        )
        candidate = selector.lifecycle._make_state(
            activation=base["activation"],
            lifecycle_head=base["lifecycle_head"],
            mark_cursor=base["mark_cursor"],
            ledger_cursor=ledger_receipt,
            enrollments=base["enrollments"],
            terminals={},
            latest_marks=base["latest_marks"],
        )
        _install_synthetic_occurrence_edge(
            lifecycle_root,
            base=base,
            mark_pointer=base["mark_cursor"],
            mark_observation=observation,
            ledger_receipt=ledger_receipt,
            candidate=candidate,
            events=[],
        )

    root = tmp_path / f"semantic-forgery-{forgery}"
    parent = _commit_first(root, _source([]))
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    with pytest.raises(selector.SparseSelectorError):
        _drain_cold_occurrence(root, inputs, head, row_limit=2)


def _rehashed_occurrence_intent(
    plan: selector.CyclePlan,
    *,
    mutate_high=None,
    extra: selector.PlannedObject | None = None,
) -> tuple[dict, tuple[selector.PlannedObject, ...]]:
    objects = list(plan.objects)
    high_index = next(
        index
        for index, item in enumerate(objects)
        if item.value.get("schema")
        == "options.sparse_selector_evidence_high_water/v1"
    )
    if mutate_high is not None:
        forged = copy.deepcopy(objects[high_index].value)
        mutate_high(forged)
        forged["high_water_id"] = selector._content_id(
            "osehw_", forged, field="high_water_id"
        )
        forged = selector.validate_runtime_object(
            forged, label="forged occurrence high-water"
        )
        objects[high_index] = selector.PlannedObject(
            key=(
                f"{selector.EVIDENCE_AUDIT_NAMESPACE}/"
                f"{forged['high_water_id']}.json"
            ),
            value=forged,
        )
    if extra is not None:
        objects.append(extra)
    ordered = tuple(sorted(objects, key=lambda item: item.key))
    next_high = objects[high_index].pointer
    next_head = copy.deepcopy(plan.head)
    next_head["evidence_high_water"] = next_high
    next_head["head_id"] = selector._content_id(
        "ossh_", next_head, field="head_id"
    )
    intent = copy.deepcopy(plan.intent)
    intent["objects"] = [item.receipt for item in ordered]
    intent["next_head"] = next_head
    intent["audit_window"]["next_high_water"] = next_high
    intent["intent_sha256"] = selector._content_id(
        "", intent, field="intent_sha256"
    )
    return intent, ordered


@pytest.mark.parametrize(
    "forgery", ("early_complete", "cursor_skip", "orphan_root", "extra_object")
)
def test_occurrence_recovery_rejects_rehashed_stage_root_and_object_set_forgery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    forgery: str,
) -> None:
    root = tmp_path / f"occurrence-recovery-{forgery}"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    plan = selector._plan_evidence_occurrence_transition(
        root=root,
        head=head,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:06:00Z"),
        row_limit=2,
    )

    mutate = None
    extra = None
    if forgery == "early_complete":
        def mutate(value: dict) -> None:
            value["phase"] = "COMPLETE"
            value["occurrence_stage"] = "DONE"
    elif forgery == "cursor_skip":
        def mutate(value: dict) -> None:
            value["ledger_replay_bytes"] = 1
    elif forgery == "orphan_root":
        def mutate(value: dict) -> None:
            value["boundary_index"] = selector.private_auth_dict.sharded_root_receipt(
                domain=selector.EVIDENCE_BOUNDARY_DOMAIN,
                root={
                    "id": f"padn_{'0' * 64}",
                    "key": f"auth_dict_nodes/padn_{'0' * 64}.json",
                    "sha256": "0" * 64,
                    "bytes": 1,
                },
                entry_count=1,
            )
    else:
        prior_value = selector._load_pointer(
            root, head["evidence_high_water"], label="prior high-water"
        )
        extra = selector.PlannedObject(
            key=head["evidence_high_water"]["key"], value=prior_value
        )
    forged_intent, forged_objects = _rehashed_occurrence_intent(
        plan, mutate_high=mutate, extra=extra
    )
    with selector._store_lock(root):
        for item in forged_objects:
            selector._prestage_immutable(
                selector._object_path(root, item.key), item.body, root=root
            )
        with pytest.raises(selector.SparseSelectorError):
            selector._plan_from_intent(
                root, forged_intent, evidence_inputs=inputs
            )
    assert selector._load_head(root) == head


def test_replay_wrapper_represents_a_valid_near_two_mib_producer_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _inputs, base, mark_pointer = _mock_evidence_capture_sources(
        tmp_path, monkeypatch
    )
    all_sessions = {
        (date(2000, 1, 1) + timedelta(days=index)).isoformat(): mark_pointer
        for index in range(9_000)
    }
    keys = list(all_sessions)
    low, high = 1, len(keys)
    selected = None
    while low <= high:
        middle = (low + high) // 2
        candidate = selector.lifecycle._make_state(
            activation=base["activation"],
            lifecycle_head=base["lifecycle_head"],
            mark_cursor=base["mark_cursor"],
            ledger_cursor=base["ledger_cursor"],
            enrollments={"P": base["activation"]},
            terminals={},
            latest_marks={
                "P": {
                    "contract_occ_symbol": "SOFI  261016C00016000",
                    "contract_drift": False,
                    "plan_identity_drift": False,
                    "sessions": {key: all_sessions[key] for key in keys[:middle]},
                }
            },
        )
        size = len(selector.canonical_bytes(candidate))
        if size < 2 * 1024 * 1024 - 1_024:
            low = middle + 1
        elif size > 2 * 1024 * 1024:
            high = middle - 1
        else:
            selected = candidate
            break
    assert selected is not None
    state_bytes = len(selector.canonical_bytes(selected))
    assert 2 * 1024 * 1024 - 1_024 <= state_bytes <= 2 * 1024 * 1024
    snapshot_pointer = {
        "id": f"osess_{'1' * 64}",
        "key": f"evidence_audit/osess_{'1' * 64}.json",
        "sha256": "2" * 64,
        "bytes": 1,
    }
    replay = selector._make_evidence_replay_state(
        snapshot=snapshot_pointer, state=selected
    )
    assert replay.pointer["bytes"] > 2 * 1024 * 1024
    assert replay.pointer["bytes"] < selector.MAX_SOURCE_INTENT_BYTES


@pytest.mark.parametrize("forgery", ("cursor_skip", "early_complete"))
def test_authenticate_store_rejects_rehashed_partial_occurrence_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    forgery: str,
) -> None:
    root = tmp_path / f"partial-auth-{forgery}"
    parent = _commit_first(root, _source([]))
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    plan = selector._plan_evidence_occurrence_transition(
        root=root,
        head=head,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:06:00Z"),
        row_limit=2,
    )
    head = selector.commit_cycle(root, plan, evidence_inputs=inputs)
    high = selector._load_evidence_high_water(root, head["evidence_high_water"])
    forged_high = copy.deepcopy(high)
    if forgery == "cursor_skip":
        forged_high["ledger_replay_bytes"] = 1
    else:
        forged_high["phase"] = "COMPLETE"
        forged_high["occurrence_stage"] = "DONE"
    forged_high["high_water_id"] = selector._content_id(
        "osehw_", forged_high, field="high_water_id"
    )
    forged_object = selector.PlannedObject(
        key=(
            f"{selector.EVIDENCE_AUDIT_NAMESPACE}/"
            f"{forged_high['high_water_id']}.json"
        ),
        value=selector.validate_runtime_object(
            forged_high, label="forged partial high-water"
        ),
    )
    forged_head = copy.deepcopy(head)
    forged_head["evidence_high_water"] = forged_object.pointer
    forged_head["head_id"] = selector._content_id(
        "ossh_", forged_head, field="head_id"
    )
    forged_head = selector.validate_runtime_object(
        forged_head, label="forged partial HEAD"
    )
    with selector._store_lock(root):
        selector._prestage_immutable(
            selector._object_path(root, forged_object.key),
            forged_object.body,
            root=root,
        )
        selector._atomic_write(
            root / selector.HEAD_FILE,
            selector.canonical_bytes(forged_head),
            root=root,
            limit=selector.MAX_HEAD_BYTES,
        )
    with pytest.raises(selector.SparseSelectorError, match="occurrence stage"):
        selector.authenticate_store(root, evidence_inputs=inputs)


def test_authenticate_store_rejects_restored_old_head_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "restored-old-head"
    parent = _commit_first(root, _source([]))
    parent_body = selector.canonical_bytes(parent)
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=parent,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    selector.commit_cycle(root, pin, evidence_inputs=inputs)
    with selector._store_lock(root):
        selector._atomic_write(
            root / selector.HEAD_FILE,
            parent_body,
            root=root,
            limit=selector.MAX_HEAD_BYTES,
        )
    before = {
        path: path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    with pytest.raises(selector.SparseSelectorError, match="surviving child"):
        selector.authenticate_store(root)
    assert {
        path: path.read_bytes() for path in root.rglob("*") if path.is_file()
    } == before


def _install_rehashed_complete_high_water(
    root: Path,
    head: dict,
    high: dict,
    *,
    supporting_objects: tuple[selector.PlannedObject, ...] = (),
) -> dict:
    forged = copy.deepcopy(high)
    forged["high_water_id"] = selector._content_id(
        "osehw_", forged, field="high_water_id"
    )
    forged_object = selector.PlannedObject(
        key=(
            f"{selector.EVIDENCE_AUDIT_NAMESPACE}/"
            f"{forged['high_water_id']}.json"
        ),
        value=selector.validate_runtime_object(
            forged, label="forged complete evidence high-water"
        ),
    )
    forged_head = copy.deepcopy(head)
    forged_head["evidence_high_water"] = forged_object.pointer
    forged_head["head_id"] = selector._content_id(
        "ossh_", forged_head, field="head_id"
    )
    forged_head = selector.validate_runtime_object(
        forged_head, label="forged complete selector HEAD"
    )
    with selector._store_lock(root):
        for item in (*supporting_objects, forged_object):
            selector._prestage_immutable(
                selector._object_path(root, item.key), item.body, root=root
            )
        selector._atomic_write(
            root / selector.HEAD_FILE,
            selector.canonical_bytes(forged_head),
            root=root,
            limit=selector.MAX_HEAD_BYTES,
        )
    return forged_head


@pytest.mark.parametrize("missing_kind", ("activation", "terminal"))
def test_complete_occurrence_authentication_requires_every_source_event_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_kind: str,
) -> None:
    root = tmp_path / f"missing-{missing_kind}-event"
    if missing_kind == "activation":
        inputs, _state, _mark = _mock_evidence_capture_sources(
            tmp_path, monkeypatch
        )
    else:
        inputs, ledger_path = _occurrence_producer_roots(tmp_path, monkeypatch)
        _emit_occurrence_mark(
            monkeypatch,
            Path(inputs.mark_root),
            observed_at="2026-08-11T14:05:00+00:00",
            phase="triggered_pre_t1",
        )
        selector.lifecycle.advance_lifecycle(
            lifecycle_root=Path(inputs.lifecycle_root),
            mark_root=Path(inputs.mark_root),
            ledger_path=ledger_path,
            ledger_receipt_path=ledger_path.parent / "receipt.json",
        )
        _append_occurrence_close(ledger_path)
        selector.lifecycle.advance_lifecycle(
            lifecycle_root=Path(inputs.lifecycle_root),
            mark_root=Path(inputs.mark_root),
            ledger_path=ledger_path,
            ledger_receipt_path=ledger_path.parent / "receipt.json",
        )
    head, high, _plans = _pin_and_drain_occurrence(root, inputs)
    replay = selector._load_evidence_replay_state(
        root, high["replay_state"], snapshot=high["snapshot"]
    )["state"]
    pointer = (
        replay["activation"]
        if missing_kind == "activation"
        else next(iter(replay["terminals"].values()))
    )
    selector.lifecycle._event_path(
        Path(inputs.lifecycle_root), pointer, create_parents=False
    ).unlink()
    with pytest.raises(selector.SparseSelectorError, match="event"):
        selector.authenticate_store(root, evidence_inputs=inputs)
    assert selector._load_head(root) == head


def test_complete_occurrence_authentication_rejects_empty_boundary_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "empty-complete-boundary-index"
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    head, high, _plans = _pin_and_drain_occurrence(root, inputs)
    high["boundary_index"] = selector._empty_evidence_audit_index(
        selector.EVIDENCE_BOUNDARY_DOMAIN
    )
    forged_head = _install_rehashed_complete_high_water(root, head, high)
    with pytest.raises(selector.SparseSelectorError, match="boundary index"):
        selector.authenticate_store(root, evidence_inputs=inputs)
    assert selector._load_head(root) == forged_head


def test_complete_occurrence_authentication_rebuilds_exact_ledger_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, ledger_path = _occurrence_producer_roots(tmp_path, monkeypatch)
    _append_occurrence_close(ledger_path)
    _emit_occurrence_mark(
        monkeypatch,
        Path(inputs.mark_root),
        observed_at="2026-08-11T14:05:00+00:00",
        phase="triggered_pre_t1",
    )
    selector.lifecycle.advance_lifecycle(
        lifecycle_root=Path(inputs.lifecycle_root),
        mark_root=Path(inputs.mark_root),
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    root = tmp_path / "forged-complete-ledger-index"
    head, high, _plans = _pin_and_drain_occurrence(root, inputs)
    binding = selector._ledger_ordinal_binding(
        root, high["ledger_row_index"], 1
    )
    forged_binding = copy.deepcopy(binding)
    forged_binding["outcome"] = "NO_ENTRY"
    forged_binding["row_semantic_sha256"] = "0" * 64
    forged_index, nodes = selector._evidence_auth_nodes(
        root,
        prior=selector._empty_evidence_audit_index(
            selector.EVIDENCE_LEDGER_ROW_DOMAIN
        ),
        domain=selector.EVIDENCE_LEDGER_ROW_DOMAIN,
        entries=(
            (["plan", forged_binding["plan_id"]], forged_binding),
            (["ordinal", 1], forged_binding),
        ),
    )
    high["ledger_row_index"] = forged_index
    forged_head = _install_rehashed_complete_high_water(
        root, head, high, supporting_objects=nodes
    )
    with pytest.raises(
        selector.SparseSelectorError,
        match="ledger index differs from captured ledger bytes",
    ):
        selector.authenticate_store(root, evidence_inputs=inputs)
    assert selector._load_head(root) == forged_head


def _repin_and_drain_incremental(
    root: Path,
    inputs: selector.EvidenceInputs,
    head: dict,
) -> tuple[dict, dict, selector.CyclePlan, list[selector.CyclePlan]]:
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=head,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T16:05:00Z"),
    )
    head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    plans: list[selector.CyclePlan] = []
    for ordinal in range(32):
        high = selector._load_evidence_high_water(
            root, head["evidence_high_water"]
        )
        if high["phase"] == "COMPLETE":
            break
        plan = selector._plan_evidence_occurrence_transition(
            root=root,
            head=head,
            evidence_inputs=inputs,
            clock=_clock(f"2026-08-12T16:{6 + ordinal:02d}:00Z"),
            row_limit=2,
        )
        assert len(plan.objects) + 1 <= selector.MAX_SOURCE_OBJECTS_PER_CYCLE
        assert selector._transition_footprint_bytes(
            plan.intent, plan.objects
        ) <= selector.MAX_SOURCE_INTENT_BYTES
        head = selector.commit_cycle(root, plan, evidence_inputs=inputs)
        plans.append(plan)
    else:
        raise AssertionError("incremental occurrence did not complete")
    high = selector._load_evidence_high_water(
        root, head["evidence_high_water"]
    )
    return head, high, pin, plans


def test_incremental_occurrence_same_target_reuses_complete_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "incremental-same-target"
    inputs, _state, _mark = _mock_evidence_capture_sources(tmp_path, monkeypatch)
    first_head, first_high, _plans = _pin_and_drain_occurrence(root, inputs)
    head, high, pin, plans = _repin_and_drain_incremental(
        root, inputs, first_head
    )
    pinned = next(
        item.value
        for item in pin.objects
        if item.value.get("schema")
        == "options.sparse_selector_evidence_high_water/v1"
    )
    assert pinned["previous_complete"] == first_head["evidence_high_water"]
    assert pinned["replay_state"] == first_high["replay_state"]
    assert pinned["boundary_index"] == first_high["boundary_index"]
    assert pinned["ledger_row_index"] == first_high["ledger_row_index"]
    assert pinned["ledger_chunks"] == first_high["ledger_chunks"]
    assert high["phase"] == "COMPLETE"
    assert high["source_state_id"] == first_high["source_state_id"]
    assert not any(
        plan.intent["audit_window"]["stage"] == "OCCURRENCE_ACTIVATION"
        for plan in plans
    )
    assert selector.authenticate_store(root, evidence_inputs=inputs)[0] == head


def test_incremental_occurrence_replays_only_one_new_suffix_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, ledger_path = _occurrence_producer_roots(tmp_path, monkeypatch)
    root = tmp_path / "incremental-one-edge"
    first_head, first_high, _plans = _pin_and_drain_occurrence(root, inputs)
    _emit_occurrence_mark(
        monkeypatch,
        Path(inputs.mark_root),
        observed_at="2026-08-11T14:05:00+00:00",
        phase="triggered_pre_t1",
    )
    selector.lifecycle.advance_lifecycle(
        lifecycle_root=Path(inputs.lifecycle_root),
        mark_root=Path(inputs.mark_root),
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    target = selector.lifecycle._load_state(Path(inputs.lifecycle_root))
    assert target is not None
    head, high, _pin, plans = _repin_and_drain_incremental(
        root, inputs, first_head
    )
    replay = selector._load_evidence_replay_state(
        root, high["replay_state"], snapshot=high["snapshot"]
    )["state"]
    assert replay == target
    assert high["boundary_index"]["entry_count"] == (
        first_high["boundary_index"]["entry_count"] + 1
    )
    assert sum(
        plan.intent["audit_window"]["stage"] == "OCCURRENCE_EDGE_INIT"
        for plan in plans
    ) == 1
    assert not any(
        plan.intent["audit_window"]["stage"] == "OCCURRENCE_ACTIVATION"
        for plan in plans
    )
    assert selector.authenticate_store(root, evidence_inputs=inputs)[0] == head


def test_stale_complete_evidence_repins_before_pending_manifest_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(
        [[_episode("freshness", "2026-08-12T13:31:00Z", strike=700.0)]]
    )
    root = tmp_path / "settlement-freshness"
    runtime_head = _commit_first(root, source)
    assert runtime_head["pending_manifest"] is not None
    inputs, ledger_path = _occurrence_producer_roots(tmp_path, monkeypatch)
    pin = selector._plan_evidence_capture_transition(
        root=root,
        head=runtime_head,
        evidence_inputs=inputs,
        clock=_clock("2026-08-12T14:05:00Z"),
    )
    complete_head = selector.commit_cycle(root, pin, evidence_inputs=inputs)
    complete_head, _plans = _drain_cold_occurrence(
        root, inputs, complete_head, row_limit=2
    )
    before_decisions = complete_head["decision_count"]
    pending = copy.deepcopy(complete_head["pending_manifest"])

    _emit_occurrence_mark(
        monkeypatch,
        Path(inputs.mark_root),
        observed_at="2026-08-11T14:05:00+00:00",
        phase="triggered_pre_t1",
    )
    selector.lifecycle.advance_lifecycle(
        lifecycle_root=Path(inputs.lifecycle_root),
        mark_root=Path(inputs.mark_root),
        ledger_path=ledger_path,
        ledger_receipt_path=ledger_path.parent / "receipt.json",
    )
    plan = selector._plan_cycle_once(
        root=root,
        source=_pinned_source(source, complete_head),
        evidence_inputs=inputs,
        scheduled_at="2026-08-12T14:30:00Z",
        clock=_clock("2026-08-12T14:30:00Z"),
        runtime_armed=True,
        admission_cap=selector.MAX_CANDIDATES_PER_MANIFEST,
        settlement_cache={},
    )
    assert plan.intent["schema"] == (
        "options.sparse_selector_evidence_audit_intent/v1"
    )
    assert plan.intent["audit_window"]["stage"] == "PIN"
    assert plan.head["pending_manifest"] == pending
    assert plan.head["decision_count"] == before_decisions
    assert not any(
        item.value.get("schema") == "options.sparse_selector_decision/v1"
        for item in plan.objects
    )
