from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.research_vault.r2_store import LocalStore
from scripts import run_fundamental_forensics_wave2 as operator


ROOT = Path(__file__).resolve().parents[1]
PINNED_TARGETS = ROOT / "config" / "fundamental_forensics" / "wave2_targets.v1.json"


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
    # Per-phase wall time for the phases that actually ran: the 2026-08-08 off-render
    # move had to be diagnosed from GitHub log timestamps because this receipt had none.
    assert set(bootstrap["timings"]) == {"sync"}
    assert bootstrap["timings"]["sync"] >= 0.0

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
    assert set(warm["timings"]) == {"restore"}
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


def test_incremental_sync_requires_sync_in_the_same_invocation(tmp_path: Path):
    """The skip baseline comes from the sync path; arming it alone is a silent no-op."""
    with pytest.raises(operator.OperatorFlowError, match="--incremental-sync requires --sync"):
        operator.run_operator_flow(
            root=tmp_path,
            targets=("FXT=1",),
            as_of="2026-08-01T23:59:59Z",
            recorded_at="2026-08-02T00:05:00Z",
            computed_at="2026-08-02T00:10:00Z",
            restore=True,
            incremental_sync=True,
            store=LocalStore(tmp_path / "private-store"),
        )


def test_reuse_local_archive_requires_acquire_in_the_same_invocation(tmp_path: Path):
    """Reuse only has meaning inside the acquire leg; arming it alone is a silent no-op."""
    with pytest.raises(operator.OperatorFlowError, match="--reuse-local-archive requires --acquire"):
        operator.run_operator_flow(
            root=tmp_path,
            targets=("FXT=1",),
            as_of="2026-08-01T23:59:59Z",
            recorded_at="2026-08-02T00:05:00Z",
            computed_at="2026-08-02T00:10:00Z",
            restore=True,
            reuse_local_archive=True,
            store=LocalStore(tmp_path / "private-store"),
        )


def test_reuse_local_archive_is_disclosed_and_reaches_the_acquisition_collector(monkeypatch, tmp_path: Path):
    received: dict = {}
    monkeypatch.setattr(operator, "_user_agent", lambda root: "MastermindX research@example.com")
    monkeypatch.setattr(
        operator,
        "acquire_bounded_filings",
        lambda **kwargs: received.update(kwargs) or {"status": "complete"},
    )
    clocks = {
        "as_of": "2026-08-01T23:59:59Z",
        "recorded_at": "2026-08-02T00:05:00Z",
        "computed_at": "2026-08-02T00:10:00Z",
    }

    armed = operator.run_operator_flow(
        root=tmp_path, targets=("FXT=1",), acquire=True, reuse_local_archive=True, **clocks
    )
    assert received["reuse_local_archive"] is True
    assert armed["actions"]["reuse_local_archive"] is True

    # Default OFF, so an operator recovery run keeps proving every byte.
    default = operator.run_operator_flow(
        root=tmp_path, targets=("FXT=1",), acquire=True, **clocks
    )
    assert received["reuse_local_archive"] is False
    assert default["actions"]["reuse_local_archive"] is False


def test_cli_arms_reuse_local_archive_only_when_requested(monkeypatch, tmp_path: Path):
    received: dict = {}
    monkeypatch.setattr(operator, "run_operator_flow", lambda **kwargs: received.update(kwargs) or {})
    argv = [
        "--root", str(tmp_path),
        "--target", "FXT=1",
        "--as-of", "2026-08-01T23:59:59Z",
        "--recorded-at", "2026-08-02T00:05:00Z",
        "--computed-at", "2026-08-02T00:10:00Z",
        "--acquire",
    ]

    assert operator.main(argv) == 0
    assert received["reuse_local_archive"] is False
    assert operator.main(argv + ["--reuse-local-archive"]) == 0
    assert received["reuse_local_archive"] is True


def test_pinned_targets_file_parses_to_normalized_targets_in_file_order():
    targets = operator.load_targets_file(PINNED_TARGETS)

    assert len(targets) == 12
    assert targets[0] == "SMCI=0001375365"
    assert targets[-1] == "ORCL=0001341439"
    assert all(entry.count("=") == 1 for entry in targets)
    # File order is the contract: the lane and the engine restore must agree on the
    # universe, and normalize_targets applies dedupe/cap on top of this list.
    assert targets == [
        f"{item['ticker']}={item['cik']}"
        for item in json.loads(PINNED_TARGETS.read_text(encoding="utf-8"))["targets"]
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"targets": [{"ticker": "FXT", "cik": "1"}]}, "shape is invalid"),
        (
            {"schema": "fundamental_forensics.wave2_targets/v2", "targets": [{"ticker": "FXT", "cik": "1"}]},
            "unsupported",
        ),
        ({"schema": "fundamental_forensics.wave2_targets/v1", "targets": []}, "lists no targets"),
        (
            {"schema": "fundamental_forensics.wave2_targets/v1", "targets": [{"ticker": "FXT"}]},
            "entry shape is invalid",
        ),
        (
            {"schema": "fundamental_forensics.wave2_targets/v1", "targets": [{"ticker": "FXT", "cik": 1}]},
            "must be strings",
        ),
        (
            {"schema": "fundamental_forensics.wave2_targets/v1", "targets": [{"ticker": "not a ticker", "cik": "1"}]},
            "invalid ticker",
        ),
    ],
)
def test_targets_file_rejects_every_malformed_shape(tmp_path: Path, payload: dict, message: str):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(operator.OperatorFlowError, match=message):
        operator.load_targets_file(path)


def test_targets_file_rejects_unreadable_or_non_json_content(tmp_path: Path):
    path = tmp_path / "targets.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(operator.OperatorFlowError, match="invalid Wave-2 targets file"):
        operator.load_targets_file(path)
    with pytest.raises(operator.OperatorFlowError, match="invalid Wave-2 targets file"):
        operator.load_targets_file(tmp_path / "absent.json")


def test_cli_merges_the_targets_file_with_explicit_targets(monkeypatch, tmp_path: Path):
    received: dict = {}
    monkeypatch.setattr(operator, "run_operator_flow", lambda **kwargs: received.update(kwargs) or {})
    path = tmp_path / "targets.json"
    path.write_text(
        json.dumps(
            {
                "schema": "fundamental_forensics.wave2_targets/v1",
                "targets": [{"ticker": "FXT", "cik": "1"}, {"ticker": "FXU", "cik": "2"}],
            }
        ),
        encoding="utf-8",
    )

    rc = operator.main(
        [
            "--root", str(tmp_path),
            "--targets-file", str(path),
            "--target", "FXV=3",
            "--as-of", "2026-08-01T23:59:59Z",
            "--recorded-at", "2026-08-02T00:05:00Z",
            "--computed-at", "2026-08-02T00:10:00Z",
            "--restore", "--verify-local-restore",
        ]
    )

    assert rc == 0
    assert received["targets"] == ["FXT=0000000001", "FXU=0000000002", "FXV=3"]
    assert received["verify_local_restore"] is True
    assert received["incremental_sync"] is False


def test_cli_requires_at_least_one_target_before_any_store_is_built(monkeypatch, capsys, tmp_path: Path):
    def no_store(**kwargs):
        raise AssertionError("private source store should not be built")

    monkeypatch.setattr(operator, "build_private_source_store", no_store)
    rc = operator.main(
        [
            "--root", str(tmp_path),
            "--as-of", "2026-08-01T23:59:59Z",
            "--recorded-at", "2026-08-02T00:05:00Z",
            "--computed-at", "2026-08-02T00:10:00Z",
            "--restore",
        ]
    )

    assert rc == 1
    annotations = [line for line in capsys.readouterr().out.splitlines() if line.startswith("::")]
    assert len(annotations) == 1
    assert "at least one target is required" in annotations[0]


def test_research_ingest_bootstrap_never_expands_an_empty_array_under_nounset():
    """Regression for run 30724508043 on the macOS Bash 3.2 runner."""
    workflow = (ROOT / ".github" / "workflows" / "research-ingest.yml").read_text(
        encoding="utf-8"
    )

    assert "restore_args=()" not in workflow
    assert 'set -- "${targets[@]}"' in workflow
    assert 'set -- "$@" --restore' in workflow
    assert '"$@" --acquire --require-complete-acquisition' in workflow
