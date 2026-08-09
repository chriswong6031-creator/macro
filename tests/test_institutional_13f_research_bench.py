"""Private durability and privacy fences for the institutional 13F bench."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.institutional_census.research_bench import (
    PRIVATE_RESEARCH_POINTER_KEY,
    PRIVATE_RESEARCH_PREFIX,
    RESEARCH_BENCH_SCHEMA,
    RESEARCH_TEMPORAL_POLICY,
    Institutional13FResearchBenchError,
    Institutional13FResearchR2Store,
    build_institutional_13f_research_store,
    load_private_research_bench,
    publish_private_research_bench,
)
from engine.research_vault.r2_store import LocalStore


def _bench(*, generated_at: str, period: str = "2026-03-31", name: str = "Alpha"):
    return {
        "schema": RESEARCH_BENCH_SCHEMA,
        "status": "screened_not_promoted",
        "generated_at": generated_at,
        "as_of_period": period,
        "point_in_time": False,
        "temporal_policy": RESEARCH_TEMPORAL_POLICY,
        "minimum_quarters_for_scoring": 8,
        "candidate_count": 1,
        "eligible_count": 0,
        "authority": "research_only",
        "candidates": [
            {
                "cik": "0000000001",
                "manager_name": name,
                "research_eligible": False,
            }
        ],
    }


class _RecordingStore:
    def __init__(self, inner: LocalStore, *, lose_pointer_ack: bool = False) -> None:
        self.inner = inner
        self.lose_pointer_ack = lose_pointer_ack
        self.writes: list[str] = []

    def get_bytes_strict_bounded(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded(key, maximum_bytes)

    def get_bytes(self, key):
        return self.inner.get_bytes(key)

    def get_bytes_strict(self, key):
        return self.inner.get_bytes_strict(key)

    def get_bytes_strict_bounded_versioned(self, key, maximum_bytes):
        return self.inner.get_bytes_strict_bounded_versioned(key, maximum_bytes)

    def validate_strict_conditional_write_capability(self):
        return self.inner.validate_strict_conditional_write_capability()

    def put_bytes_strict_conditional(
        self, key, data, *, expected_version, content_type="application/octet-stream"
    ):
        self.writes.append(key)
        written = self.inner.put_bytes_strict_conditional(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )
        if key == PRIVATE_RESEARCH_POINTER_KEY and self.lose_pointer_ack:
            self.lose_pointer_ack = False
            raise TimeoutError("simulated lost pointer acknowledgement")
        return written

    def put_bytes(self, *_args, **_kwargs):
        raise AssertionError("private bench publication must not write unconditionally")

    def list_prefix(self, *_args, **_kwargs):
        raise AssertionError("private bench publication must not use list authority")

    def exists(self, key):
        return self.inner.exists(key)

    def upload_time(self, key):
        return self.inner.upload_time(key)


def _publish(
    store,
    *,
    cutoff: str = "2026-06-01T12:00:00Z",
    period: str = "2026-03-31",
    baseline: str = "2025-12-31",
    name: str = "Alpha",
    published_at: str | None = None,
):
    return publish_private_research_bench(
        store,
        bench=_bench(generated_at=cutoff, period=period, name=name),
        current_period=period,
        baseline_period=baseline,
        source_cutoff_at=cutoff,
        published_at=published_at or cutoff,
        producer_version="test/1",
    )


def test_private_bench_is_content_addressed_read_back_and_idempotent(
    tmp_path: Path,
) -> None:
    store = _RecordingStore(LocalStore(tmp_path / "private-store"))
    first = _publish(store)

    assert first.pointer_updated is True
    assert first.pointer.bench_object_key.startswith(
        f"{PRIVATE_RESEARCH_PREFIX}/objects/sha256/"
    )
    assert first.pointer.bench_byte_length == len(first.payload)
    assert PRIVATE_RESEARCH_POINTER_KEY in store.writes
    assert all(key.startswith(PRIVATE_RESEARCH_PREFIX + "/") for key in store.writes)
    assert "evidence/v1" not in first.pointer.bench_object_key

    writes_before = list(store.writes)
    replay = _publish(
        store,
        published_at="2026-06-05T12:00:00Z",
    )
    assert replay.pointer_updated is False
    assert replay.pointer == first.pointer
    assert replay.payload == first.payload
    assert store.writes == writes_before
    assert load_private_research_bench(store).pointer == first.pointer


def test_private_pointer_advances_without_period_or_cutoff_rewind(
    tmp_path: Path,
) -> None:
    store = _RecordingStore(LocalStore(tmp_path / "private-store"))
    first = _publish(store)
    later_cutoff = "2026-06-02T12:00:00Z"
    second = _publish(store, cutoff=later_cutoff, name="Beta")
    assert second.pointer_updated is True
    assert second.pointer.source_cutoff_at == later_cutoff
    assert second.pointer.bench_sha256 != first.pointer.bench_sha256

    with pytest.raises(Institutional13FResearchBenchError, match="cannot rewind"):
        _publish(store)
    with pytest.raises(
        Institutional13FResearchBenchError, match="current_period cannot rewind"
    ):
        _publish(
            store,
            cutoff="2026-06-03T12:00:00Z",
            period="2025-12-31",
            baseline="2025-09-30",
        )


def test_private_pointer_rejects_a_fork_at_the_same_source_cutoff(
    tmp_path: Path,
) -> None:
    store = _RecordingStore(LocalStore(tmp_path / "private-store"))
    _publish(store)
    with pytest.raises(Institutional13FResearchBenchError, match="forks"):
        _publish(store, name="Different")


def test_private_pointer_rejects_publication_clock_rewind(tmp_path: Path) -> None:
    store = _RecordingStore(LocalStore(tmp_path / "private-store"))
    _publish(store, published_at="2026-06-05T12:00:00Z")
    with pytest.raises(
        Institutional13FResearchBenchError, match="published_at cannot rewind"
    ):
        _publish(
            store,
            cutoff="2026-06-02T12:00:00Z",
            published_at="2026-06-03T12:00:00Z",
        )


def test_private_pointer_reconciles_a_lost_cas_acknowledgement(
    tmp_path: Path,
) -> None:
    store = _RecordingStore(
        LocalStore(tmp_path / "private-store"), lose_pointer_ack=True
    )
    published = _publish(store)
    assert published.pointer_updated is True
    assert load_private_research_bench(store).payload == published.payload


def test_private_bench_rejects_false_point_in_time_claim(tmp_path: Path) -> None:
    store = _RecordingStore(LocalStore(tmp_path / "private-store"))
    bench = _bench(generated_at="2026-06-01T12:00:00Z")
    bench["point_in_time"] = True
    with pytest.raises(Institutional13FResearchBenchError, match="point_in_time false"):
        publish_private_research_bench(
            store,
            bench=bench,
            current_period="2026-03-31",
            baseline_period="2025-12-31",
            source_cutoff_at="2026-06-01T12:00:00Z",
            published_at="2026-06-01T12:00:00Z",
            producer_version="test/1",
        )
    assert store.writes == []


def test_research_store_has_no_generic_or_public_credential_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    generic_only = {
        "R2_ENDPOINT": "https://public.invalid",
        "R2_ACCESS_KEY_ID": "public-key",
        "R2_SECRET_ACCESS_KEY": "public-secret",
        "R2_BUCKET": "public-bucket",
        "R2_RESEARCH_ENDPOINT": "https://legacy-private.invalid",
        "R2_RESEARCH_ACCESS_KEY_ID": "legacy-key",
        "R2_RESEARCH_SECRET_ACCESS_KEY": "legacy-secret",
        "R2_RESEARCH_BUCKET": "legacy-bucket",
        "INSTITUTIONAL_13F_R2_ENDPOINT": "https://evidence.invalid",
        "INSTITUTIONAL_13F_R2_ACCESS_KEY_ID": "evidence-key",
        "INSTITUTIONAL_13F_R2_SECRET_ACCESS_KEY": "evidence-secret",
        "INSTITUTIONAL_13F_R2_BUCKET": "evidence-bucket",
    }
    with pytest.raises(
        Institutional13FResearchBenchError, match="configuration is incomplete"
    ):
        build_institutional_13f_research_store(environment=generic_only)

    client = object()
    captured = {}

    def fake_client(*, endpoint, access_key, secret_key):
        captured.update(endpoint=endpoint, access_key=access_key, secret_key=secret_key)
        return client

    monkeypatch.setattr(
        "engine.institutional_census.research_bench._research_r2_client", fake_client
    )
    dedicated = {
        "INSTITUTIONAL_13F_RESEARCH_R2_ENDPOINT": "https://private.invalid",
        "INSTITUTIONAL_13F_RESEARCH_R2_ACCESS_KEY_ID": "private-key",
        "INSTITUTIONAL_13F_RESEARCH_R2_SECRET_ACCESS_KEY": "private-secret",
        "INSTITUTIONAL_13F_RESEARCH_R2_BUCKET": "private-bucket",
        **generic_only,
    }
    built = build_institutional_13f_research_store(environment=dedicated)
    assert isinstance(built, Institutional13FResearchR2Store)
    assert built.bucket == "private-bucket"
    assert captured == {
        "endpoint": "https://private.invalid",
        "access_key": "private-key",
        "secret_key": "private-secret",
    }

    local = build_institutional_13f_research_store(
        local_dir=tmp_path / "explicit-local", environment={}
    )
    assert isinstance(local, LocalStore)
