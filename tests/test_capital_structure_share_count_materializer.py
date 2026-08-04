"""End-to-end seam tests for the authenticated Company Facts materializer.

The model and publisher each have their own adversarial suites.  These tests
pin the non-negotiable bridge properties: recovery precedes upstream opening,
the raw object selection remains bound to the authenticated manifest, and a
bounded append/replay cannot silently alter the selected prefix.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from engine.capital_structure.companyfacts_authenticated_read import (
    CompanyFactsAuthenticatedSnapshot,
    CompanyFactsSelectedCoverageReceipt,
)
from engine.capital_structure.source_store import (
    ContentAddressedSourceStore,
    LocalStore,
    SourceStoreIdentityError,
)
from engine.capital_structure import share_count_materializer as share_model
from scripts import materialize_capital_structure_share_counts as materializer
from tests.test_capital_structure_share_count_materializer_model import (
    _Verifier,
    _coverage_receipt,
    _manifest,
    _raw,
)


def _snapshot(
    manifests: list[dict[str, Any]], receipt: Mapping[str, Any], receipt_bytes: bytes,
) -> CompanyFactsAuthenticatedSnapshot:
    selected = CompanyFactsSelectedCoverageReceipt(
        receipt_id=str(receipt["receipt_id"]),
        receipt_path="receipts/test.json",
        receipt_sha256="a" * 64,
        receipt_byte_length=len(receipt_bytes),
        generation_id=str(receipt["generation"]["generation_id"]),
        sequence=int(receipt["sequence"]),
        published_at=str(receipt["published_at"]),
        source_manifest_descriptor=receipt["generation"]["source_manifest"],
        coverage_descriptor=receipt["generation"]["coverage"],
        manifest_prefix=receipt["companyfacts_manifest_ledger"],
        coverage_prefix=receipt["coverage_ledger"],
    )
    return CompanyFactsAuthenticatedSnapshot(
        manifests=tuple(manifests),
        coverage_rows=(),
        selected_coverage_receipt=selected,
        selected_coverage_receipt_record=receipt,
        selected_coverage_receipt_bytes=receipt_bytes,
        observed_head={},
    )


def _local_store(tmp_path: Path, raws: list[bytes]) -> ContentAddressedSourceStore:
    store = ContentAddressedSourceStore(
        LocalStore(tmp_path / "companyfacts"), backend="local", store_id="capital_structure_local",
    )
    for raw in raws:
        receipt = store.put_verified(raw, media_type="application/json")
        assert receipt is not None
    return store


def _published(*, ledger_bytes: bytes, binding: Mapping[str, Any]) -> SimpleNamespace:
    """The production boundary returns these two fields to the bridge on recovery."""
    return SimpleNamespace(
        ledger_bytes=ledger_bytes,
        receipt={"input_binding": dict(binding)},
        published=True,
        recovered=False,
    )


def _recording_publisher(calls: list[tuple[dict[str, Any], dict[str, Any]]]):
    def publish(*, canonical_ledger_bytes: bytes, input_binding: Mapping[str, Any]):
        ledger = json.loads(canonical_ledger_bytes)
        assert input_binding == materializer._input_binding(ledger)
        calls.append((ledger, dict(input_binding)))
        return _published(ledger_bytes=canonical_ledger_bytes, binding=input_binding)

    return publish


def _variant_raw(index: int) -> bytes:
    payload = json.loads(_raw())
    payload["facts"]["dei"]["EntityPublicFloat"]["units"]["USD"][0]["val"] = index + 1
    return _raw(payload)


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_run_recovers_before_authenticated_upstream_or_raw_read_and_uses_no_sec_or_legacy_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    snapshot = _snapshot([manifest], receipt, receipt_bytes)
    source = _local_store(tmp_path, [raw])
    events: list[str] = []
    published: list[tuple[dict[str, Any], dict[str, Any]]] = []
    recovery_budgets: list[float] = []
    snapshot_budgets: list[float] = []
    publication_budgets: list[float] = []

    class RecordingSource:
        backend = source.backend
        store_id = source.store_id

        def get_verified_strict_bounded(self, *args: Any, **kwargs: Any) -> bytes | None:
            events.append("raw")
            return source.get_verified_strict_bounded(*args, **kwargs)

    def recover(*, max_operation_seconds: float):
        events.append("recover")
        recovery_budgets.append(max_operation_seconds)
        return None

    def load_snapshot(*, max_read_seconds: float):
        assert events == ["recover"]
        snapshot_budgets.append(max_read_seconds)
        events.append("upstream")
        return snapshot

    def source_stores():
        assert events == ["recover", "upstream", "trust"]
        events.append("stores")
        return {source.store_id: RecordingSource()}

    def trust():
        events.append("trust")
        return verifier, object()

    def publish(
        *,
        canonical_ledger_bytes: bytes,
        input_binding: Mapping[str, Any],
        max_operation_seconds: float,
    ):
        events.append("publish")
        publication_budgets.append(max_operation_seconds)
        ledger = json.loads(canonical_ledger_bytes)
        assert input_binding == materializer._input_binding(ledger)
        published.append((ledger, dict(input_binding)))
        return _published(ledger_bytes=canonical_ledger_bytes, binding=input_binding)

    # If this bridge grew a direct SEC request, it would fail before a test
    # accidentally makes a network call.  The selected raw bytes come only
    # from the manifest-bound source store above.
    import requests

    def forbidden_network(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("materializer must not make a network request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden_network)
    monkeypatch.setattr(materializer, "recover_share_count_materialization", recover)
    monkeypatch.setattr(materializer, "load_authenticated_companyfacts_snapshot", load_snapshot)
    monkeypatch.setattr(materializer, "_build_production_trust_context", trust)
    monkeypatch.setattr(materializer, "build_source_stores", source_stores)
    monkeypatch.setattr(
        materializer, "_publish_share_count_materialization_with_production_trust", publish,
    )

    result = materializer.run()

    assert result is not None
    assert events == ["recover", "upstream", "trust", "stores", "raw", "publish"]
    assert len(recovery_budgets) == 1
    assert 0 < recovery_budgets[0] <= materializer.MATERIALIZATION_TIMEOUT_SECONDS
    assert len(snapshot_budgets) == 1
    assert 0 < snapshot_budgets[0] <= materializer.MATERIALIZATION_TIMEOUT_SECONDS
    assert len(publication_budgets) == 1
    assert 0 < publication_budgets[0] <= materializer.MATERIALIZATION_TIMEOUT_SECONDS
    assert published[0][1]["prefixes"]["source_manifests"]["count"] == 1
    source_code = inspect.getsource(materializer)
    assert "fundamental_forensics" not in source_code
    # The explicit nonclaim in the module docstring is deliberately retained;
    # the executable bridge itself has no HTTP client or legacy-cache import.
    assert "import requests" not in source_code
    assert "import urllib" not in source_code


@pytest.mark.parametrize(
    ("slow_phase", "expected_events"),
    [
        ("recovery", ["recover"]),
        ("snapshot", ["recover", "snapshot"]),
        ("trust", ["recover", "snapshot", "trust"]),
        ("stores", ["recover", "snapshot", "trust", "stores"]),
    ],
)
def test_run_deadline_fails_closed_after_slow_pre_raw_phase(
    slow_phase: str,
    expected_events: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    events: list[str] = []
    snapshot_budgets: list[float] = []

    def recover(*, max_operation_seconds: float) -> None:
        events.append("recover")
        assert 0 < max_operation_seconds <= 10
        if slow_phase == "recovery":
            clock.advance(10)
        return None

    def load_snapshot(*, max_read_seconds: float) -> Any:
        events.append("snapshot")
        snapshot_budgets.append(max_read_seconds)
        if slow_phase == "snapshot":
            clock.advance(10)
        return object()

    def trust() -> tuple[object, object]:
        events.append("trust")
        if slow_phase == "trust":
            clock.advance(10)
        return object(), object()

    def source_stores() -> dict[str, ContentAddressedSourceStore]:
        events.append("stores")
        if slow_phase == "stores":
            clock.advance(10)
        return {}

    monkeypatch.setattr(materializer, "recover_share_count_materialization", recover)
    monkeypatch.setattr(materializer, "load_authenticated_companyfacts_snapshot", load_snapshot)
    monkeypatch.setattr(materializer, "_build_production_trust_context", trust)
    monkeypatch.setattr(materializer, "build_source_stores", source_stores)

    labels = {
        "recovery": "share-count recovery",
        "snapshot": "authenticated snapshot load",
        "trust": "production trust construction",
        "stores": "source-store construction",
    }
    with pytest.raises(
        materializer.ShareCountMaterializationRunError,
        match=f"deadline exceeded during {labels[slow_phase]}",
    ):
        materializer._run(max_run_seconds=10, monotonic=clock)

    assert events == expected_events
    if slow_phase != "recovery":
        assert snapshot_budgets == [10]


def test_strict_raw_batch_enforces_exact_store_backend_key_hash_and_length_bindings(
    tmp_path: Path,
) -> None:
    raw = _raw()
    manifest = _manifest(raw)
    source = _local_store(tmp_path, [raw])

    assert materializer._strict_raw_batch([manifest], {source.store_id: source}) == [raw]

    with pytest.raises(materializer.ShareCountMaterializationRunError, match="unavailable"):
        materializer._strict_raw_batch([manifest], {})

    class ReboundStore:
        backend = "r2"
        store_id = source.store_id

    with pytest.raises(materializer.ShareCountMaterializationRunError, match="rebound"):
        materializer._strict_raw_batch([manifest], {source.store_id: ReboundStore()})

    wrong_key = deepcopy(manifest)
    wrong_key["storage"]["object_key"] = "capital_structure/sec/sha256/00/" + "0" * 64
    with pytest.raises(SourceStoreIdentityError, match="key"):
        materializer._strict_raw_batch([wrong_key], {source.store_id: source})

    wrong_length = deepcopy(manifest)
    wrong_length["content"]["byte_length"] += 1
    with pytest.raises(Exception, match="length mismatch"):
        materializer._strict_raw_batch([wrong_length], {source.store_id: source})


def test_materialization_deadline_stops_inside_the_raw_read_loop(
    tmp_path: Path,
) -> None:
    verifier = _Verifier()
    raws = [_variant_raw(0), _variant_raw(1)]
    manifests = [_manifest(raw) for raw in raws]
    receipt, receipt_bytes = _coverage_receipt(manifests, verifier)
    snapshot = _snapshot(manifests, receipt, receipt_bytes)
    source = _local_store(tmp_path, raws)
    clock = _Clock()
    reads: list[str] = []

    class SlowFirstReadSource:
        backend = source.backend
        store_id = source.store_id

        def get_verified_strict_bounded(self, *args: Any, **kwargs: Any) -> bytes | None:
            reads.append("raw")
            result = source.get_verified_strict_bounded(*args, **kwargs)
            if len(reads) == 1:
                clock.advance(10)
            return result

    def must_not_publish(**_kwargs: Any) -> Any:
        raise AssertionError("deadline exhaustion during raw reads must halt publication")

    with pytest.raises(
        materializer.ShareCountMaterializationRunError,
        match="deadline exceeded during strict raw Company Facts reads",
    ):
        materializer._materialize_authenticated_snapshot(
            snapshot=snapshot,
            current=None,
            stores={source.store_id: SlowFirstReadSource()},
            coverage_receipt_verifier=verifier,
            now_fn=lambda: datetime(2025, 12, 1, tzinfo=timezone.utc),
            publisher=must_not_publish,
            deadline=10,
            monotonic=clock,
        )

    assert reads == ["raw"]


@pytest.mark.parametrize(
    ("slow_phase", "expected_label"),
    [
        ("compile", "share-count model compilation"),
        ("validate", "share-count ledger validation"),
        ("publish", "share-count publication"),
    ],
)
def test_materialization_deadline_fails_closed_after_slow_model_or_publication_phase(
    tmp_path: Path,
    slow_phase: str,
    expected_label: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _Verifier()
    raw = _raw()
    manifest = _manifest(raw)
    receipt, receipt_bytes = _coverage_receipt([manifest], verifier)
    snapshot = _snapshot([manifest], receipt, receipt_bytes)
    source = _local_store(tmp_path, [raw])
    clock = _Clock()
    published: list[str] = []

    if slow_phase == "compile":
        compile_prefix = materializer.compile_authenticated_companyfacts_share_count_prefix

        def slow_compile(*args: Any, **kwargs: Any) -> dict[str, Any]:
            ledger = compile_prefix(*args, **kwargs)
            clock.advance(10)
            return ledger

        monkeypatch.setattr(
            materializer,
            "compile_authenticated_companyfacts_share_count_prefix",
            slow_compile,
        )
    elif slow_phase == "validate":
        validate_ledger = materializer.validate_share_count_ledger

        def slow_validate(*args: Any, **kwargs: Any) -> None:
            validate_ledger(*args, **kwargs)
            clock.advance(10)

        monkeypatch.setattr(materializer, "validate_share_count_ledger", slow_validate)

    def publisher(**_kwargs: Any) -> Any:
        published.append("publish")
        if slow_phase == "publish":
            clock.advance(10)
        return object()

    with pytest.raises(
        materializer.ShareCountMaterializationRunError,
        match=f"deadline exceeded during {expected_label}",
    ):
        materializer._materialize_authenticated_snapshot(
            snapshot=snapshot,
            current=None,
            stores={source.store_id: source},
            coverage_receipt_verifier=verifier,
            now_fn=lambda: datetime(2025, 12, 1, tzinfo=timezone.utc),
            publisher=publisher,
            deadline=10,
            monotonic=clock,
        )

    assert published == (["publish"] if slow_phase == "publish" else [])


def test_authenticated_prefix_advances_in_hard_bounded_batches_then_replays_exactly(
    tmp_path: Path,
) -> None:
    verifier = _Verifier()
    raws = [_variant_raw(index) for index in range(share_model.MAX_SOURCE_BATCH + 1)]
    manifests = [
        _manifest(raw, retrieved_at=f"2025-11-{index + 1:02d}T00:00:00Z")
        for index, raw in enumerate(raws)
    ]
    receipt, receipt_bytes = _coverage_receipt(manifests, verifier, sequence=2)
    snapshot = _snapshot(manifests, receipt, receipt_bytes)
    source = _local_store(tmp_path, raws)
    calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
    publisher = _recording_publisher(calls)

    first = materializer._materialize_authenticated_snapshot(
        snapshot=snapshot, current=None, stores={source.store_id: source},
        coverage_receipt_verifier=verifier,
        now_fn=lambda: datetime(2025, 12, 1, tzinfo=timezone.utc), publisher=publisher,
    )
    assert first is not None
    assert len(calls) == 1
    assert len(calls[0][0]["source_snapshots"]) == share_model.MAX_SOURCE_BATCH
    assert len(calls[0][0]["ledger_receipts"]) == 1
    assert calls[0][1]["prefixes"]["source_manifests"]["count"] == share_model.MAX_SOURCE_BATCH

    second = materializer._materialize_authenticated_snapshot(
        snapshot=snapshot, current=first, stores={source.store_id: source},
        coverage_receipt_verifier=verifier,
        now_fn=lambda: datetime(2025, 12, 2, tzinfo=timezone.utc), publisher=publisher,
    )
    assert second is not None
    assert len(calls) == 2
    assert len(calls[1][0]["source_snapshots"]) == len(manifests)
    assert len(calls[1][0]["ledger_receipts"]) == 2
    assert calls[1][1]["prefixes"]["source_manifests"]["count"] == len(manifests)

    replay = materializer._materialize_authenticated_snapshot(
        snapshot=snapshot, current=second, stores={source.store_id: source},
        coverage_receipt_verifier=verifier,
        now_fn=lambda: datetime(2025, 12, 3, tzinfo=timezone.utc), publisher=publisher,
    )
    assert replay is not None
    assert len(calls) == 3
    assert calls[2][0] == calls[1][0]
    assert calls[2][1] == calls[1][1]


def test_zero_authenticated_manifests_remain_explicitly_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    verifier = _Verifier()
    receipt, receipt_bytes = _coverage_receipt([], verifier)
    snapshot = _snapshot([], receipt, receipt_bytes)

    def must_not_publish(**_kwargs: Any) -> Any:
        raise AssertionError("zero-source intake must not publish an empty share ledger")

    assert materializer._materialize_authenticated_snapshot(
        snapshot=snapshot, current=None, stores={}, coverage_receipt_verifier=verifier,
        now_fn=lambda: datetime(2025, 12, 1, tzinfo=timezone.utc), publisher=must_not_publish,
    ) is None

    monkeypatch.setattr(materializer, "run", lambda: None)
    assert materializer.main() == 0
    assert "share-count state remains unavailable" in capsys.readouterr().out


def test_share_count_publication_workspace_is_excluded_from_nightly_git_checkpoint() -> None:
    root = Path(__file__).resolve().parents[1]
    ignore_lines = {
        line.strip()
        for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "data/capital_structure/share_counts/" in ignore_lines
    daily_workflow = (root / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "git add data/" in daily_workflow
    assert (
        "if: ${{ vars.CAPITAL_STRUCTURE_SHARE_COUNT_PUBLICATION_ENABLED == 'true' }}"
        in daily_workflow
    )
    assert (
        "SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID: "
        "${{ secrets.SHARE_COUNT_HEAD_GUARD_ACCOUNT_ID }}"
    ) in daily_workflow
    assert (
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED: "
        "${{ vars.CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V3_MIGRATION_ENABLED || 'false' }}"
    ) in daily_workflow
    assert (
        "CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V4_MIGRATION_ENABLED: "
        "${{ vars.CAPITAL_STRUCTURE_SHARE_COUNT_HEAD_V4_MIGRATION_ENABLED || 'false' }}"
    ) in daily_workflow
    assert (
        "timeout --signal=TERM --kill-after=30s 15m30s "
        "python -m scripts.materialize_capital_structure_share_counts"
    ) in daily_workflow
