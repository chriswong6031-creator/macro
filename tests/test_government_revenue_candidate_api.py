"""Read-only API tests for the receipt-bound Government Revenue candidate rail."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import government_revenue as api
from engine.government_revenue.candidates import (
    build_candidate_observations,
    candidate_queue_content_id,
)
from scripts import build_government_revenue_candidates as projection
from tests.government_revenue_candidate_fixture import (
    canonical_frozen_at,
    canonical_fixture_root,
)
from tests.test_government_revenue_candidates import _award_event, _graph, _payload


# Derived from the canonical inputs `_fixture_root` copies, never hand-typed --
# see `tests/government_revenue_candidate_fixture` for why a wall-clock literal
# here is a scheduled failure rather than a constant.
FROZEN_AT = canonical_frozen_at()


def _fixture_root(tmp_path: Path) -> Path:
    """Copy only the materializer's immutable input boundary into a temp root."""
    return canonical_fixture_root(tmp_path)


def _artifact_paths(root: Path) -> dict[str, Path]:
    data_dir = root / "data" / "government_revenue"
    return {
        "ledger": data_dir / projection.LEDGER_FILENAME,
        "queue": data_dir / projection.QUEUE_FILENAME,
        "state": data_dir / projection.STATE_FILENAME,
        "status": data_dir / projection.STATUS_FILENAME,
        "public": root / projection.PUBLIC_DIRECTORY / projection.PUBLIC_QUEUE_FILENAME,
    }


def _exact_observations(*, leaked_observed_change: bool = False) -> list[dict]:
    """Make two schema-valid observations of one exact candidate identity."""
    oldest = build_candidate_observations(
        _payload(_award_event()), _graph(), generated_at=FROZEN_AT
    )[0]
    newest = deepcopy(oldest)
    newest["observation_id"] = "gro1-" + "e" * 24
    newest["known_at"] = "2026-08-02T13:00:00+00:00"
    newest["source_event"]["known_at"] = newest["known_at"]
    newest["source_receipt_refs"][0]["known_at"] = newest["known_at"]
    newest["freshness"]["event_known_at"] = newest["known_at"]
    if leaked_observed_change:
        newest["mechanism"]["observed_change"] = "Official change; token=not-for-public"
    return [oldest, newest]


def _materialize(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    exact: bool = False,
    empty: bool = False,
    leaked_observed_change: bool = False,
) -> None:
    """Publish a real temp generation, with exact rows only where a route needs them."""
    if exact and empty:
        raise ValueError("candidate API fixture cannot be both exact and empty")
    if exact:
        (root / "data/government_revenue/recipient_entity_graph.json").write_text(
            projection._canonical_json(_graph()),
            encoding="utf-8",
        )
        observations = _exact_observations(leaked_observed_change=leaked_observed_change)
        original_queue = projection.build_candidate_queue

        def exact_observations(*_args, **_kwargs):
            return deepcopy(observations)

        def exact_queue(latest, graph, *, generated_at):
            queue = original_queue(latest, graph, generated_at=generated_at)
            queue["candidates"] = deepcopy(observations)
            queue["counts"] = {
                **queue["counts"],
                "total": len(observations),
                "exact_linked": len(observations),
                "by_family": {observations[0]["candidate_family"]: len(observations)},
                "by_state": {observations[0]["candidate_state"]: len(observations)},
                "by_freshness": {"ok": len(observations)},
                "by_exact_link_status": {
                    "exact_linked": len(observations),
                    "mapping_needed": len(queue["mapping_backlog"]),
                },
            }
            queue["freshness"] = {
                **queue["freshness"],
                "exact_candidate_availability": "available",
            }
            queue["content_id"] = candidate_queue_content_id(queue)
            return queue

        monkeypatch.setattr(projection, "build_candidate_observations", exact_observations)
        monkeypatch.setattr(projection, "build_candidate_queue", exact_queue)
    elif empty:
        original_queue = projection.build_candidate_queue

        def empty_observations(*_args, **_kwargs):
            return []

        def empty_queue(latest, graph, *, generated_at):
            queue = original_queue(latest, graph, generated_at=generated_at)
            queue["candidates"] = []
            queue["counts"] = {
                **queue["counts"],
                "total": 0,
                "exact_linked": 0,
                "by_family": {},
                "by_state": {},
                "by_freshness": {},
                "by_exact_link_status": {
                    "exact_linked": 0,
                    "mapping_needed": len(queue["mapping_backlog"]),
                },
            }
            queue["freshness"] = {
                **queue["freshness"],
                "exact_candidate_availability": "not_observed",
            }
            queue["content_id"] = candidate_queue_content_id(queue)
            return queue

        monkeypatch.setattr(projection, "build_candidate_observations", empty_observations)
        monkeypatch.setattr(projection, "build_candidate_queue", empty_queue)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)


def _wire_api(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _artifact_paths(root)
    monkeypatch.setattr(api, "_CANDIDATE_QUEUE_PATHS", (paths["queue"], paths["public"]))
    monkeypatch.setattr(api, "_CANDIDATE_LEDGER_PATH", paths["ledger"])
    monkeypatch.setattr(api, "_CANDIDATE_STATE_PATH", paths["state"])
    monkeypatch.setattr(api, "_CANDIDATE_STATUS_PATH", paths["status"])
    monkeypatch.setattr(
        api,
        "_CANDIDATE_SOURCE_PATHS",
        (
            root / "data/government_revenue/latest.json",
            root / "data/government_revenue/workspace.json",
            root / "data/government_revenue/recipient_entity_graph.json",
        ),
    )
    monkeypatch.setattr(api, "_CANDIDATE_CACHE", {"state": None, "payload": None})


def _list(*, cursor: str | None = None, limit: int = 100, family: str | None = None) -> dict:
    return api.candidates(
        ticker=None,
        family=family,
        state=None,
        direction=None,
        cursor=cursor,
        limit=limit,
    )


def _assert_http_error(call, status_code: int) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == status_code
    return exc.value


def test_zero_candidate_generation_is_a_successful_empty_envelope_with_mapping_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch, empty=True)
    _wire_api(root, monkeypatch)

    listing = _list(limit=1)
    backlog = api.mapping_backlog(ticker=None, cursor=None, limit=2)

    assert listing["total"] == 0
    assert listing["items"] == []
    assert listing["next_cursor"] is None
    assert listing["mapping_backlog_total"] == 21
    assert backlog["total"] == 21
    assert len(backlog["items"]) == 2
    assert backlog["next_cursor"]
    assert all(row["issuer_attribution"] == "not_asserted" for row in backlog["items"])


def test_candidate_list_detail_history_company_and_mapping_backlog_page_against_one_exact_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch, exact=True)
    _wire_api(root, monkeypatch)

    first_list = _list(limit=1)
    second_list = _list(cursor=first_list["next_cursor"], limit=1)
    candidate_id = first_list["items"][0]["candidate_id"]
    detail = api.candidate(candidate_id)
    first_history = api.candidate_history(candidate_id, cursor=None, limit=1)
    second_history = api.candidate_history(
        candidate_id, cursor=first_history["next_cursor"], limit=1
    )
    first_company = api.company_candidates("NOC", cursor=None, limit=1)
    second_company = api.company_candidates("NOC", cursor=first_company["next_cursor"], limit=1)
    first_backlog = api.mapping_backlog(ticker=None, cursor=None, limit=1)
    second_backlog = api.mapping_backlog(
        ticker=None, cursor=first_backlog["next_cursor"], limit=1
    )

    assert first_list["total"] == 2
    assert len(first_list["items"]) == len(second_list["items"]) == 1
    assert first_list["next_cursor"] and second_list["next_cursor"] is None
    assert first_list["items"][0]["coverage"]["exact_link_status"] == "exact_linked"
    assert detail["candidate"]["candidate_id"] == candidate_id
    assert detail["history_count"] == 2
    assert first_history["total"] == 2
    assert len(first_history["items"]) == len(second_history["items"]) == 1
    assert first_history["next_cursor"] and second_history["next_cursor"] is None
    assert first_company["total"] == 2
    assert len(first_company["items"]) == len(second_company["items"]) == 1
    assert first_company["next_cursor"] and second_company["next_cursor"] is None
    assert first_backlog["total"] == 21
    assert len(first_backlog["items"]) == len(second_backlog["items"]) == 1
    assert first_backlog["next_cursor"] and second_backlog["next_cursor"]


def test_candidate_cursors_are_rejected_when_malformed_or_bound_to_other_filters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch, exact=True)
    _wire_api(root, monkeypatch)

    page = _list(limit=1)
    cursor = page["next_cursor"]
    assert cursor
    mutated = cursor[:10] + ("A" if cursor[10] != "A" else "B") + cursor[11:]
    _assert_http_error(lambda: _list(cursor="not-a-candidate-cursor", limit=1), 400)
    _assert_http_error(lambda: _list(cursor=mutated, limit=1), 400)
    _assert_http_error(
        lambda: _list(cursor=cursor, limit=1, family="new_award"), 400
    )


def test_unknown_candidate_and_ticker_are_not_discovery_fallbacks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch, exact=True)
    _wire_api(root, monkeypatch)

    unknown = "grc1-" + "0" * 24
    _assert_http_error(lambda: api.candidate(unknown), 404)
    _assert_http_error(lambda: api.candidate_history(unknown, cursor=None, limit=1), 404)
    _assert_http_error(lambda: api.company_candidates("ZZZZ", cursor=None, limit=1), 404)


def test_candidate_cache_fails_closed_when_bound_workspace_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch)
    _wire_api(root, monkeypatch)
    assert _list()["total"] > 0

    workspace_path = root / "data/government_revenue/workspace.json"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    workspace["bundle_id"] = "grw2-" + "f" * 24
    workspace_path.write_text(json.dumps(workspace), encoding="utf-8")

    _assert_http_error(lambda: _list(), 503)


def test_candidate_cache_fails_closed_when_top_level_company_coverage_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch)
    _wire_api(root, monkeypatch)
    assert _list()["mapping_backlog_total"] == 21

    latest_path = root / "data/government_revenue/latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["companies"] = latest["companies"][:-1]
    latest_path.write_text(json.dumps(latest), encoding="utf-8")

    _assert_http_error(lambda: _list(), 503)


@pytest.mark.parametrize("missing", ["queue", "public"])
def test_candidate_projection_requires_both_queue_twins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch)
    _artifact_paths(root)[missing].unlink()
    _wire_api(root, monkeypatch)

    _assert_http_error(lambda: _list(limit=1), 503)


def test_candidate_projection_rejects_nonidentical_twins_and_content_id_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch)
    paths = _artifact_paths(root)
    paths["public"].write_bytes(paths["public"].read_bytes() + b" ")
    _wire_api(root, monkeypatch)
    _assert_http_error(lambda: _list(limit=1), 503)

    root = _fixture_root(tmp_path / "content-id")
    _materialize(root, monkeypatch)
    paths = _artifact_paths(root)
    queue = json.loads(paths["queue"].read_text(encoding="utf-8"))
    queue["content_id"] = "grcq1-" + "0" * 24
    raw = json.dumps(queue, sort_keys=True, separators=(",", ":")).encode("utf-8")
    paths["queue"].write_bytes(raw)
    paths["public"].write_bytes(raw)
    _wire_api(root, monkeypatch)
    _assert_http_error(lambda: _list(limit=1), 503)


@pytest.mark.parametrize("tamper", ["truncation", "mutation", "status_binding"])
def test_candidate_projection_rejects_ledger_and_status_binding_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch, exact=True)
    paths = _artifact_paths(root)
    if tamper == "truncation":
        paths["ledger"].write_bytes(b"")
    elif tamper == "mutation":
        rows = [json.loads(line) for line in paths["ledger"].read_text(encoding="utf-8").splitlines()]
        rows[0]["mechanism"]["observed_change"] = "Valid shape, altered ledger bytes"
        paths["ledger"].write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )
    else:
        status = json.loads(paths["status"].read_text(encoding="utf-8"))
        status["ledger_sha256"] = "0" * 64
        paths["status"].write_text(json.dumps(status), encoding="utf-8")
    _wire_api(root, monkeypatch)

    _assert_http_error(lambda: _list(limit=1), 503)


def test_candidate_projection_rejects_authority_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch)
    paths = _artifact_paths(root)
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    status["authority"]["can_gate"] = True
    paths["status"].write_text(json.dumps(status), encoding="utf-8")
    _wire_api(root, monkeypatch)

    _assert_http_error(lambda: _list(limit=1), 503)


def test_candidate_projection_rejects_noncanonical_but_schema_valid_jsonl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch, exact=True)
    paths = _artifact_paths(root)
    rows = [json.loads(line) for line in paths["ledger"].read_text(encoding="utf-8").splitlines()]
    noncanonical = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=False, separators=(", ", ": ")).encode("utf-8") + b"\n"
        for row in rows
    )
    paths["ledger"].write_bytes(noncanonical)
    digest = hashlib.sha256(noncanonical).hexdigest()
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    state["ledger"]["sha256"] = digest
    state["ledger"]["byte_count"] = len(noncanonical)
    status["ledger_sha256"] = digest
    status["ledger_byte_count"] = len(noncanonical)
    paths["state"].write_text(json.dumps(state), encoding="utf-8")
    paths["status"].write_text(json.dumps(status), encoding="utf-8")
    _wire_api(root, monkeypatch)

    _assert_http_error(lambda: _list(limit=1), 503)


def test_candidate_cache_reset_isolates_temp_projection_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_root = _fixture_root(tmp_path / "empty")
    _materialize(empty_root, monkeypatch, empty=True)
    _wire_api(empty_root, monkeypatch)
    assert _list(limit=1)["total"] == 0

    exact_root = _fixture_root(tmp_path / "exact")
    _materialize(exact_root, monkeypatch, exact=True)
    _wire_api(exact_root, monkeypatch)
    assert _list(limit=1)["total"] == 2


def test_public_candidate_responses_scrub_sensitive_derived_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _materialize(root, monkeypatch, exact=True, leaked_observed_change=True)
    _wire_api(root, monkeypatch)

    listing = _list(limit=1)
    candidate_id = listing["items"][0]["candidate_id"]
    detail = api.candidate(candidate_id)
    history = api.candidate_history(candidate_id, cursor=None, limit=1)
    company = api.company_candidates("NOC", cursor=None, limit=1)

    for response in (listing, detail, history, company):
        serialized = json.dumps(response)
        assert "not-for-public" not in serialized
        assert "token=[redacted]" in serialized
