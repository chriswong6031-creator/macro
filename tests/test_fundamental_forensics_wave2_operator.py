from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.research_vault.r2_store import LocalStore
from scripts import run_fundamental_forensics_wave2 as operator


ROOT = Path(__file__).resolve().parents[1]


def test_operator_flow_uses_fixed_restore_acquire_project_sync_order(monkeypatch, tmp_path: Path):
    events: list[str] = []
    local_store = tmp_path / "private-store"

    def restore(**kwargs):
        events.append("restore")
        assert kwargs["snapshot_id"] == "ffsecsrc_" + "a" * 64
        return SimpleNamespace(to_dict=lambda: {"restored_files": 2})

    def acquire(**kwargs):
        events.append("acquire")
        assert [item.ticker for item in kwargs["targets"]] == ["FXT"]
        return {"status": "complete"}

    def projections(*args, **kwargs):
        events.append("build_projections")
        assert kwargs["cik_overrides"] == {"FXT": 1}
        return [{"ticker": "FXT", "tracks_ready": 2}]

    def sync(**kwargs):
        events.append("sync")
        assert kwargs["snapshot_at"] == "2026-08-02T00:05:00.000000Z"
        return SimpleNamespace(to_dict=lambda: {"snapshot_id": "ffsecsrc_" + "b" * 64})

    monkeypatch.setattr(operator, "restore_source_roots", restore)
    monkeypatch.setattr(operator, "acquire_bounded_filings", acquire)
    monkeypatch.setattr(operator, "build_cached_disclosures", projections)
    monkeypatch.setattr(operator, "sync_source_roots", sync)
    monkeypatch.setattr(operator, "_user_agent", lambda root: "MastermindX research@example.com")

    outcome = operator.run_operator_flow(
        root=tmp_path,
        targets=("FXT=1",),
        as_of="2026-08-01T23:59:59Z",
        recorded_at="2026-08-02T00:05:00Z",
        computed_at="2026-08-02T00:10:00Z",
        restore=True,
        acquire=True,
        build_projections=True,
        sync=True,
        snapshot_id="ffsecsrc_" + "a" * 64,
        local_store=local_store,
    )

    assert events == ["restore", "acquire", "build_projections", "sync"]
    assert outcome["results"]["acquire"] == {"status": "complete"}
    assert "render" not in outcome["actions"]


def test_operator_rejects_no_action_and_does_not_build_private_store(tmp_path: Path, monkeypatch):
    called = False

    def no_store(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("private source store should not be built")

    monkeypatch.setattr(operator, "build_private_source_store", no_store)
    with pytest.raises(operator.OperatorFlowError, match="select at least one action"):
        operator.run_operator_flow(
            root=tmp_path,
            targets=("FXT=1",),
            as_of="2026-08-01T23:59:59Z",
            recorded_at="2026-08-02T00:05:00Z",
            computed_at="2026-08-02T00:10:00Z",
        )
    assert called is False


def test_cli_passes_explicit_action_flags_without_render(monkeypatch, capsys, tmp_path: Path):
    received: dict = {}

    def flow(**kwargs):
        received.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(operator, "run_operator_flow", flow)
    rc = operator.main(
        [
            "--root", str(tmp_path),
            "--target", "FXT=1",
            "--as-of", "2026-08-01T23:59:59Z",
            "--recorded-at", "2026-08-02T00:05:00Z",
            "--computed-at", "2026-08-02T00:10:00Z",
            "--restore", "--acquire", "--build-projections", "--sync", "--require-complete-acquisition",
        ]
    )

    assert rc == 0
    assert received["restore"] is True
    assert received["acquire"] is True
    assert received["build_projections"] is True
    assert received["sync"] is True
    assert received["require_complete_acquisition"] is True
    assert '"status": "ok"' in capsys.readouterr().out


def test_operator_localstore_bootstrap_sync_then_warm_restore_never_calls_broad_render(monkeypatch, tmp_path: Path):
    raw = tmp_path / "raw"
    archive = tmp_path / "archive"
    (raw / "0000000001" / "submissions").mkdir(parents=True)
    (raw / "0000000001" / "submissions" / "latest.json").write_bytes(b"raw-pointer")
    (archive / "manifests" / "0000000001").mkdir(parents=True)
    (archive / "manifests" / "0000000001" / "fixture.json").write_bytes(b"archive-manifest")
    local_store = tmp_path / "private-store"

    # The broad state/page builder is loaded elsewhere in the package but this
    # operator action must never call it; if it does, this test turns it into a
    # visible failure rather than an accidental render-lane dependency.
    from scripts import build_fundamental_forensics as broad_builder

    monkeypatch.setattr(
        broad_builder,
        "main",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("broad render invoked")),
    )
    bootstrap = operator.run_operator_flow(
        root=tmp_path,
        targets=("FXT=1",),
        as_of="2026-08-01T23:59:59Z",
        recorded_at="2026-08-02T00:05:00Z",
        computed_at="2026-08-02T00:10:00Z",
        sync=True,
        raw_root=raw,
        archive_root=archive,
        local_store=local_store,
    )
    assert bootstrap["results"]["sync"]["file_count"] == 2

    for path in (raw, archive):
        for item in sorted(path.rglob("*"), reverse=True):
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                item.rmdir()
        path.rmdir()
    warm = operator.run_operator_flow(
        root=tmp_path,
        targets=("FXT=1",),
        as_of="2026-08-01T23:59:59Z",
        recorded_at="2026-08-02T00:05:00Z",
        computed_at="2026-08-02T00:10:00Z",
        restore=True,
        raw_root=raw,
        archive_root=archive,
        local_store=local_store,
    )
    assert warm["results"]["restore"]["restored_files"] == 2
    assert (raw / "0000000001" / "submissions" / "latest.json").read_bytes() == b"raw-pointer"
    assert (archive / "manifests" / "0000000001" / "fixture.json").read_bytes() == b"archive-manifest"


def test_operator_requires_private_store_for_restore_or_sync(tmp_path: Path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise operator.SourceSyncError("private source store unavailable")

    monkeypatch.setattr(operator, "build_private_source_store", unavailable)
    with pytest.raises(operator.SourceSyncError, match="unavailable"):
        operator.run_operator_flow(
            root=tmp_path,
            targets=("FXT=1",),
            as_of="2026-08-01T23:59:59Z",
            recorded_at="2026-08-02T00:05:00Z",
            computed_at="2026-08-02T00:10:00Z",
            sync=True,
        )


def test_require_complete_acquisition_stops_before_projection_or_sync(tmp_path: Path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(operator, "_user_agent", lambda root: "MastermindX research@example.com")
    monkeypatch.setattr(operator, "acquire_bounded_filings", lambda **kwargs: {"status": "partial"})
    monkeypatch.setattr(operator, "build_cached_disclosures", lambda *args, **kwargs: calls.append("projection"))
    monkeypatch.setattr(operator, "sync_source_roots", lambda **kwargs: calls.append("sync"))

    with pytest.raises(operator.OperatorFlowError, match="partial coverage"):
        operator.run_operator_flow(
            root=tmp_path,
            targets=("FXT=1",),
            as_of="2026-08-01T23:59:59Z",
            recorded_at="2026-08-02T00:05:00Z",
            computed_at="2026-08-02T00:10:00Z",
            acquire=True,
            build_projections=True,
            sync=True,
            require_complete_acquisition=True,
            store=LocalStore(tmp_path / "private-store"),
        )
    assert calls == []


def test_operator_validates_every_explicit_clock_even_for_sync_only(tmp_path: Path):
    with pytest.raises(operator.OperatorFlowError, match="as_of must include a timezone"):
        operator.run_operator_flow(
            root=tmp_path,
            targets=("FXT=1",),
            as_of="2026-08-01T23:59:59",
            recorded_at="2026-08-02T00:05:00Z",
            computed_at="2026-08-02T00:10:00Z",
            sync=True,
            store=LocalStore(tmp_path / "private-store"),
        )


def test_research_ingest_bootstrap_never_expands_an_empty_array_under_nounset():
    """Regression for run 30724508043 on the macOS Bash 3.2 runner."""
    workflow = (ROOT / ".github" / "workflows" / "research-ingest.yml").read_text(
        encoding="utf-8"
    )

    assert "restore_args=()" not in workflow
    assert 'set -- "${targets[@]}"' in workflow
    assert 'set -- "$@" --restore' in workflow
    assert '"$@" --acquire --require-complete-acquisition' in workflow
