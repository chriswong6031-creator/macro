"""Focused fail-closed tests for the isolated share-count v2 retention lane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from engine.capital_structure import share_count_retention as retention
from scripts import retain_capital_structure_share_counts as cli


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


def _digest(char: str) -> str:
    return char * 64


def _receipt(char: str, *, sequence: int, previous: dict | None = None) -> dict:
    digest = _digest(char)
    record = {
        "schema": retention.V2_RECEIPT_SCHEMA,
        "receipt_id": "",
        "sequence": sequence,
        "previous_receipt": previous,
        "ancestor_refs": [] if previous is None else [previous],
        "published_at": "2026-08-03T00:00:00Z",
        "generation": {
            "generation_id": retention.V2_GENERATION_ID_PREFIX + digest,
            "ledger_sha256": digest,
            "ledger_byte_length": 1,
        },
        "input_binding": {
            "schema": "capital_structure.share_count_materialization_input_binding/v1",
            "ledger_head_receipt_id": "share-count-ledger-receipt-v2:cs:" + "a" * 24,
            "ledger_sequence": 1, "compiler_version": "test", "materialized_at": "2026-08-03T00:00:00Z",
            "prefixes": {name: {"count": 0, "rolling_sha256": "a" * 64} for name in ("observations", "source_snapshots", "bridges", "source_manifests")},
        },
        "output_authority": retention._output_authority(),
        "auth": {"scheme": "hmac-sha256/v1", "key_id": "test", "signature": "f" * 64},
    }
    record["receipt_id"] = retention._publication_receipt_id(record)
    return record


def _receipt_ref(receipt: dict) -> dict:
    return {"sequence": receipt["sequence"], "receipt_id": receipt["receipt_id"], "receipt_sha256": "f" * 64, "receipt_byte_length": 100}


def _selection(current: dict, *, token: str = "head-token") -> retention.AuthenticatedCurrentSelection:
    prior = current["previous_receipt"]
    generation_id = current["generation"]["generation_id"]
    return retention.AuthenticatedCurrentSelection(
        head={
            "schema": retention.V2_HEAD_SCHEMA,
            "key_id": "test",
            "sequence": current["sequence"],
            "receipt_id": current["receipt_id"],
            "receipt_sha256": "f" * 64,
            "receipt_byte_length": 100,
            "receipt_object_key": retention.receipt_object_key(current["receipt_id"]),
            "generation_id": generation_id,
            "ledger_sha256": current["generation"]["ledger_sha256"],
            "ledger_byte_length": 1,
            "ledger_object_key": retention.generation_ledger_key(generation_id),
            "published_at": "2026-08-03T00:00:00Z",
            "previous_receipt": prior,
            "signature": "f" * 64,
        },
        head_token=token,
        receipt=current,
    )


def _object(char: str, *, age_hours: int = 100) -> retention.RetentionObject:
    return retention.RetentionObject(
        key=retention.generation_ledger_key(retention.V2_GENERATION_ID_PREFIX + _digest(char)),
        last_modified=NOW - timedelta(hours=age_hours), etag=f"etag-{char}",
    )


class _Reader:
    def __init__(self, current: retention.AuthenticatedCurrentSelection, prior: dict | None, *, changed: retention.AuthenticatedCurrentSelection | None = None, change_after: int = 10_000) -> None:
        self.current, self.prior = current, prior
        self.changed, self.change_after, self.calls = changed, change_after, 0

    def read_authenticated_current(self) -> retention.AuthenticatedCurrentSelection:
        self.calls += 1
        if self.changed is not None and self.calls > self.change_after:
            return self.changed
        return self.current

    def read_authenticated_predecessor(self, current: retention.AuthenticatedCurrentSelection) -> retention.AuthenticatedReceipt:
        assert current.receipt["receipt_id"] == self.current.receipt["receipt_id"]
        if self.prior is None:
            raise AssertionError("genesis must not request a predecessor")
        prior_ref = current.receipt["previous_receipt"]
        return retention.AuthenticatedReceipt(
            self.prior, receipt_sha256=prior_ref["receipt_sha256"],
            receipt_byte_length=prior_ref["receipt_byte_length"],
        )


class _Store:
    def __init__(self, pages: list[retention.RetentionListPage]) -> None:
        self.pages, self.deleted = pages, []
        self.objects = {item.key: item for page in pages for item in page.objects}
        self._page = 0

    def list_generation_ledgers(self, *, prefix: str, continuation_token: str | None, max_keys: int) -> retention.RetentionListPage:
        assert prefix == retention.V2_GENERATION_OBJECT_PREFIX
        page = self.pages[self._page]
        self._page += 1
        return page

    def head_generation_ledger(self, *, key: str) -> retention.RetentionObject:
        return self.objects[key]

    def delete_generation_ledger_if_unchanged(self, *, key: str, expected_etag: str, expected_last_modified: datetime) -> retention.ConditionalDeleteResult:
        observed = self.objects[key]
        if observed.etag != expected_etag or observed.last_modified != expected_last_modified:
            return retention.ConditionalDeleteResult(deleted=False, condition_matched=False)
        self.deleted.append(key)
        return retention.ConditionalDeleteResult(deleted=True, condition_matched=True)


class _R2Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_objects_v2(self, **kwargs):
        self.calls.append(("list", kwargs))
        return {
            "ResponseMetadata": {"HTTPStatusCode": 200}, "IsTruncated": False,
            "KeyCount": 1, "Contents": [{"Key": _object("c").key, "LastModified": _object("c").last_modified, "ETag": "etag-c"}],
        }

    def head_object(self, **kwargs):
        self.calls.append(("head", kwargs))
        return {"ResponseMetadata": {"HTTPStatusCode": 200}, "LastModified": _object("c").last_modified, "ETag": "etag-c"}

    def delete_object(self, **kwargs):
        self.calls.append(("delete", kwargs))
        return {"ResponseMetadata": {"HTTPStatusCode": 204}}


def _lane(*, objects: tuple[retention.RetentionObject, ...]) -> tuple[_Reader, _Store, retention.HmacRetentionReceiptSigner]:
    first = _receipt("a", sequence=1)
    previous = _receipt_ref(first)
    current = _receipt("b", sequence=2, previous=previous)
    return (
        _Reader(_selection(current), first),
        _Store([retention.RetentionListPage(objects=objects, next_token=None)]),
        retention.HmacRetentionReceiptSigner(b"r" * 32, key_id="retention-test"),
    )


def test_current_and_authenticated_immediate_predecessor_are_never_candidates() -> None:
    reader, store, _signer = _lane(objects=(_object("a"), _object("b"), _object("c")))
    plan = retention.build_retention_plan(reader=reader, store=store, now=NOW)
    assert {item.key for item in plan.candidate_objects} == {_object("c").key}
    assert retention.generation_ledger_key(retention.V2_GENERATION_ID_PREFIX + _digest("a")) in plan.protected_generation_keys
    assert retention.generation_ledger_key(retention.V2_GENERATION_ID_PREFIX + _digest("b")) in plan.protected_generation_keys


def test_orphans_are_bounded_by_quarantine_and_young_objects_are_kept() -> None:
    reader, store, _signer = _lane(objects=(_object("c", age_hours=100), _object("d", age_hours=2)))
    plan = retention.build_retention_plan(reader=reader, store=store, now=NOW)
    assert [item.key for item in plan.candidate_objects] == [_object("c").key]
    assert [item.key for item in plan.grace_objects] == [_object("d", age_hours=2).key]
    with pytest.raises(retention.ShareCountRetentionError, match="at least 48 hours"):
        retention.build_retention_plan(reader=reader, store=store, now=NOW, quarantine_seconds=47 * 60 * 60)


def test_head_race_stops_before_the_next_deletion() -> None:
    reader, store, signer = _lane(objects=(_object("c"), _object("d")))
    changed = _selection(_receipt("e", sequence=1), token="new-head-token")
    reader.changed, reader.change_after = changed, 2  # plan, first guard, then second guard
    with pytest.raises(retention.ShareCountRetentionHeadChanged, match="must replan"):
        retention.run_retention(reader=reader, store=store, signer=signer, now=NOW, apply=True)
    assert store.deleted == [_object("c").key]


def test_pagination_and_unknown_objects_fail_closed_without_delete() -> None:
    reader, _store, _signer = _lane(objects=(_object("c"),))
    overflow = _Store([
        retention.RetentionListPage(objects=(_object("c"),), next_token="next"),
        retention.RetentionListPage(objects=(_object("d"),), next_token=None),
    ])
    with pytest.raises(retention.ShareCountRetentionError, match="page cap"):
        retention.build_retention_plan(reader=reader, store=overflow, now=NOW, max_pages=1)

    reader, _store, _signer = _lane(objects=(_object("c"),))
    hostile = retention.RetentionObject(
        key="capital_structure/share_counts/v2/receipts/" + _digest("f") + ".json",
        last_modified=NOW - timedelta(days=4), etag="hostile",
    )
    with pytest.raises(retention.ShareCountRetentionError, match="unknown object key"):
        retention.build_retention_plan(
            reader=reader, store=_Store([retention.RetentionListPage(objects=(hostile,), next_token=None)]), now=NOW,
        )


def test_default_dry_run_never_deletes_and_emits_signed_canonical_no_authority_receipt(tmp_path: Path) -> None:
    reader, store, signer = _lane(objects=(_object("c"),))
    result = retention.run_retention(reader=reader, store=store, signer=signer, now=NOW)
    assert store.deleted == [] and result.deleted_keys == () and result.receipt["mode"] == "dry_run"
    assert result.receipt["candidate_generation_keys"] == [_object("c").key]
    assert all(value is False for key, value in result.receipt["output_authority"].items() if key != "is_context_only")
    target = tmp_path / "retention-receipt.json"
    retention.write_retention_receipt(path=target, receipt=result.receipt, signer=signer)
    assert target.read_bytes().endswith(b"\n")
    assert json.loads(target.read_text()) == result.receipt
    tampered = dict(result.receipt)
    tampered["auth"] = dict(result.receipt["auth"])
    tampered["auth"]["signature"] = "0" * 64
    with pytest.raises(retention.ShareCountRetentionError, match="authentication"):
        retention.write_retention_receipt(
            path=tmp_path / "tampered.json",
            receipt=tampered,
            signer=signer,
        )


def test_no_credential_fallback_and_apply_has_two_explicit_gates() -> None:
    shared_only = {
        "R2_ENDPOINT": "shared-endpoint", "R2_ACCESS_KEY_ID": "shared-id",
        "R2_SECRET_ACCESS_KEY": "shared-secret", "R2_BUCKET": "shared-bucket",
    }
    with pytest.raises(retention.ShareCountRetentionError, match="dedicated"):
        cli._dedicated_delete_config(shared_only)
    dedicated = {name: f"value-{index}" for index, name in enumerate(cli.DEDICATED_DELETE_ENV_NAMES)}
    assert cli._dedicated_delete_config(dedicated).bucket == "value-3"
    with pytest.raises(retention.ShareCountRetentionError, match="both explicit"):
        cli._require_apply_enabled({cli.RETENTION_ENABLE_ENV: "true"})
    cli._require_apply_enabled({cli.RETENTION_ENABLE_ENV: "true", cli.APPLY_ENABLE_ENV: "true"})
    assert cli.build_parser().parse_args([]).apply is False
    with pytest.raises(retention.ShareCountRetentionError, match="hard-disabled"):
        cli._require_released_retention_protocol()
    assert cli.main([], environ=dedicated) == 2


def test_dedicated_r2_adapter_pins_namespace_and_refuses_unproven_conditional_delete() -> None:
    client = _R2Client()
    env = {name: f"value-{index}" for index, name in enumerate(retention.RETENTION_R2_ENV_NAMES)}
    store = retention.build_dedicated_r2_retention_store(environ=env, client_factory=lambda *args, **kwargs: client)
    listed = store.list_generation_ledgers(prefix=retention.V2_GENERATION_OBJECT_PREFIX, continuation_token=None, max_keys=7)
    assert listed.objects == (_object("c"),)
    fresh = store.head_generation_ledger(key=_object("c").key)
    with pytest.raises(retention.ShareCountRetentionDeleteAmbiguity, match="not release-proven"):
        store.delete_generation_ledger_if_unchanged(
            key=fresh.key,
            expected_etag=fresh.etag,
            expected_last_modified=fresh.last_modified,
        )
    assert not any(call == "delete" for call, _arguments in client.calls)
    with pytest.raises(retention.ShareCountRetentionError, match="exact v2"):
        store.head_generation_ledger(key="capital_structure/share_counts/v2/receipts/" + _digest("a") + ".json")


def test_daily_keeps_both_publisher_and_retention_default_off() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/daily.yml").read_text()
    assert "if: ${{ vars.CAPITAL_STRUCTURE_SHARE_COUNT_PUBLICATION_ENABLED == 'true' }}" in workflow
    assert "if: ${{ vars.CAPITAL_STRUCTURE_SHARE_COUNT_PUBLICATION_ENABLED == 'true' && vars.CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_ENABLED == 'true' }}" in workflow
    assert "CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_APPLY_ENABLED: ${{ vars.CAPITAL_STRUCTURE_SHARE_COUNT_RETENTION_APPLY_ENABLED }}" in workflow
    retention_step = workflow.split(
        "- name: retain unselected share-count v2 generations (pre-production)", 1,
    )[1].split("- name: compile capital-structure event spine", 1)[0]
    assert "${{ secrets." not in retention_step
    assert 'retention_args+=(--apply)' in retention_step
    assert "15m30s" in retention_step
