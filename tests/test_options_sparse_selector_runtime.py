from __future__ import annotations

import copy
import hashlib
import json
import os
import resource
import sys
import time
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
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
        "test_unarmed_advance_refuses_before_private_store_creation",
        "test_public_plan_and_commit_are_inert_before_private_store_creation",
        "test_core_package_excludes_runtime_and_publication_surfaces",
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
    root: Path, evidence_inputs: selector.EvidenceInputs | None = None
) -> list[dict]:
    return selector.authenticate_store(root, evidence_inputs=evidence_inputs)[1]


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
        lambda inputs: snapshot if inputs.w1a_receipt_root == w1a_root else pytest.fail(
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
    assert selector.SELECTOR_RUNTIME_ARMED is False
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


def test_unarmed_advance_refuses_before_private_store_creation(tmp_path: Path) -> None:
    root = tmp_path / "never-created"
    with pytest.raises(selector.SparseSelectorUnarmed, match="code-unarmed"):
        selector.advance(
            private_root=root,
            source=selector.SourceSnapshot("bad", b"", b"", "bad"),
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="bad",
        )
    assert not root.exists()


def test_public_plan_and_commit_are_inert_before_private_store_creation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "public-never-created"
    source = selector.SourceSnapshot("bad", b"", b"", "bad")
    with pytest.raises(selector.SparseSelectorUnarmed, match="code-unarmed"):
        selector.plan_cycle(
            root=root,
            source=source,
            evidence_inputs=selector.EvidenceInputs(),
            scheduled_at="bad",
            clock=_clock(),
        )
    with pytest.raises(selector.SparseSelectorUnarmed, match="code-unarmed"):
        selector.commit_cycle(root, None)
    assert not root.exists()


def test_core_package_excludes_runtime_and_publication_surfaces() -> None:
    # The core payload deliberately does not contain a runner.  Existing repo
    # orchestration surfaces must not name or arm this held research lane.
    assert not (ROOT / "scripts/run_options_sparse_selector.py").is_file()
    for path in (
        ROOT / ".github/workflows/daily.yml",
        ROOT / "config/dag.yml",
        ROOT / "config/synapse.yml",
    ):
        text = path.read_text(encoding="utf-8").lower()
        assert "options_sparse_selector" not in text
        assert "sparse-selector" not in text
    assert selector.SELECTOR_RUNTIME_ARMED is False
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
        scheduled_at="2026-08-12T14:15:00Z",
        clock=_clock("2026-08-12T14:15:00Z"),
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
    evidence_inputs = _passing_evidence(tmp_path, monkeypatch, source)
    root = tmp_path / "selector"
    _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    selector.commit_cycle(root, plan)
    rows = _decision_rows(root, evidence_inputs)
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
        match="immutable object conflicts",
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

    def counted(inputs: selector.EvidenceInputs) -> selector.EvidenceSnapshot:
        nonlocal calls
        calls += 1
        return original(inputs)

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
    head = _commit_first(root, source)
    pinned = _pinned_source(source, head)
    absent_plan = selector.plan_cycle(
        root=root,
        source=pinned,
        evidence_inputs=selector.EvidenceInputs(),
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
        runtime_armed=True,
    )
    passing = _passing_evidence(tmp_path, monkeypatch, source)
    passing_plan = selector.plan_cycle(
        root=root,
        source=pinned,
        evidence_inputs=passing,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
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
        receipt
        for receipt in campaign_plan.intent["objects"]
        if receipt["value"].get("schema")
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

    def counted_snapshot(inputs):
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original_snapshot(inputs)

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
        padding_bytes=selector.MAX_EVIDENCE_OBJECT_BYTES,
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
    assert mark is not None and len(mark.body) > selector.MAX_EVIDENCE_OBJECT_BYTES
    assert (
        lifecycle_evidence is not None
        and len(lifecycle_evidence.body) > selector.MAX_EVIDENCE_OBJECT_BYTES
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
    evidence_inputs = _passing_evidence(tmp_path, monkeypatch, source)
    root = tmp_path / "selector"
    _commit_first(root, source)
    plan = selector.plan_cycle(
        root=root,
        source=source,
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T21:00:00Z",
        clock=_clock("2026-08-12T21:00:00Z"),
        runtime_armed=True,
    )
    selector.commit_cycle(root, plan)
    decision = _decision_rows(root, evidence_inputs)[0]
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
    evidence_inputs = _passing_evidence(tmp_path, monkeypatch, source)
    root = tmp_path / "selector"
    _commit_first(root, source)
    instants = iter(
        (
            datetime(2026, 8, 12, 14, 5, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 14, 5, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 14, 5, 2, tzinfo=timezone.utc),
            datetime(2026, 8, 12, 14, 5, 1, tzinfo=timezone.utc),
        )
    )
    with pytest.raises(selector.SparseSelectorError, match="noncausal"):
        selector.plan_cycle(
            root=root,
            source=selector.SourceSnapshot(
                commit=source.commit,
                campaigns_raw=source.campaigns_raw,
                episodes_raw=source.episodes_raw,
                observed_at="2026-08-12T14:05:00Z",
            ),
            evidence_inputs=evidence_inputs,
            scheduled_at="2026-08-12T14:05:00Z",
            clock=lambda: next(instants),
            runtime_armed=True,
        )

    good_plan = selector.plan_cycle(
        root=root,
        source=selector.SourceSnapshot(
            commit=source.commit,
            campaigns_raw=source.campaigns_raw,
            episodes_raw=source.episodes_raw,
            observed_at="2026-08-12T14:05:00Z",
        ),
        evidence_inputs=evidence_inputs,
        scheduled_at="2026-08-12T14:05:00Z",
        clock=_clock("2026-08-12T14:05:00Z"),
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
