from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from engine.neuralweb import market_memory_identity_observation as OBSERVATION
from engine.neuralweb import market_memory_identity_store as STORE
from lib import symbol_directory_receipts as RECEIPTS
from scripts import ingest_market_memory_identity as INGEST

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "data" / "symbol_directory" / "snapshots"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _temporary_repository(tmp_path: Path, *, tracked_count: int = 1) -> Path:
    repository = tmp_path / "repository"
    target = repository / "data" / "symbol_directory" / "snapshots"
    target.mkdir(parents=True)
    sources = sorted(SNAPSHOTS.glob("*.parquet"))
    assert len(sources) >= tracked_count + 1
    for source in sources[: tracked_count + 1]:
        shutil.copyfile(source, target / source.name)
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "Market Memory Tests")
    for source in sources[:tracked_count]:
        _git(repository, "add", f"data/symbol_directory/snapshots/{source.name}")
    _git(repository, "commit", "-qm", "fixture")
    return repository


def _operational_repository(tmp_path: Path) -> tuple[Path, dict]:
    repository = tmp_path / "operational-repository"
    partition = "2026-08-11"
    snapshot = (
        repository / "data" / "symbol_directory" / "snapshots" / f"{partition}.parquet"
    )
    frame = pd.read_parquet(min(SNAPSHOTS.glob("*.parquet")))
    frame["date"] = partition
    RECEIPTS.durable_atomic_write_parquet(frame, snapshot)
    sources = (
        (
            RECEIPTS.NASDAQ_LISTED_SOURCE_ID,
            RECEIPTS.SourceFetch(
                value="decoded Nasdaq response",
                content=b"exact Nasdaq response bytes\r\n",
                requested_url=(
                    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
                ),
                started_at=f"{partition}T00:00:01.000000Z",
                completed_at=f"{partition}T00:00:01.100000Z",
            ),
        ),
        (
            RECEIPTS.OTHER_LISTED_SOURCE_ID,
            RECEIPTS.SourceFetch(
                value="decoded other response",
                content=b"exact other response bytes\r\n",
                requested_url=(
                    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
                ),
                started_at=f"{partition}T00:00:02.000000Z",
                completed_at=f"{partition}T00:00:02.100000Z",
            ),
        ),
    )
    source_counts = frame["source"].value_counts().to_dict()
    spy = frame.loc[frame["symbol"] == "SPY"].iloc[0]
    receipt = RECEIPTS.build_symbol_directory_completion_receipt(
        kind="listing_snapshot",
        observation_date=partition,
        artifact_path=snapshot,
        source_fetches=sources,
        collector_started_at=f"{partition}T00:00:00.000000Z",
        collector_completed_at=f"{partition}T00:00:04.000000Z",
        pre_dedupe_rows=len(frame),
        duplicate_occurrences=0,
        duplicate_key_count=0,
        source_row_counts=(
            (
                RECEIPTS.NASDAQ_LISTED_SOURCE_ID,
                int(source_counts.get("nasdaqlisted", 0)),
            ),
            (
                RECEIPTS.OTHER_LISTED_SOURCE_ID,
                int(source_counts.get("otherlisted", 0)),
            ),
        ),
        pre_dedupe_spy_occurrences=(
            {
                "source_id": RECEIPTS.OTHER_LISTED_SOURCE_ID,
                "symbol": "SPY",
                "security_name": spy["security_name"],
                "exchange": spy["exchange"],
                "etf": bool(spy["etf"]),
                "test_issue": bool(spy["test_issue"]),
                "is_preferred": bool(spy["is_preferred"]),
            },
        ),
        non_authoritative_footers=(
            RECEIPTS.footer_diagnostic(
                source_id=RECEIPTS.NASDAQ_LISTED_SOURCE_ID,
                text=f"File Creation Time: {partition} 00:00:01",
            ),
            RECEIPTS.footer_diagnostic(
                source_id=RECEIPTS.OTHER_LISTED_SOURCE_ID,
                text=f"File Creation Time: {partition} 00:00:02",
            ),
        ),
    )
    sidecar = RECEIPTS.completion_receipt_path(
        snapshot.parent.parent,
        kind="listing_snapshot",
        observation_date=partition,
    )
    RECEIPTS.write_symbol_directory_completion_receipt(
        sidecar,
        receipt,
        snapshot,
        expected_kind="listing_snapshot",
    )
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "Market Memory Tests")
    _git(repository, "add", "data/symbol_directory")
    _git(repository, "commit", "-qm", "operational fixture")
    return repository, receipt


def test_ingest_captures_only_git_owned_snapshots_and_retries_idempotently(
    tmp_path: Path,
) -> None:
    repository = _temporary_repository(tmp_path)
    store = tmp_path / "identity-store"

    first = INGEST.ingest_identity_observations(repository, store_root=store)
    second = INGEST.ingest_identity_observations(repository, store_root=store)

    assert first["tracked_snapshot_count"] == 1
    assert first["published_count"] == 1
    assert first["idempotent_count"] == 0
    assert first["reconstruction_count"] == 1
    assert first["operational_count"] == 0
    assert second["tracked_snapshot_count"] == 1
    assert second["published_count"] == 0
    assert second["idempotent_count"] == 1
    assert second["generation_id"] == first["generation_id"]
    assert first["authority"] == {
        "context_only": True,
        "training_eligible": False,
        "promotion_eligible": False,
    }


def test_ingest_admits_an_exact_tracked_post_cutoff_receipt_operationally(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, receipt = _operational_repository(tmp_path)
    store = tmp_path / "identity-store"
    monkeypatch.setattr(
        OBSERVATION,
        "_utc_now",
        lambda: datetime(2026, 8, 11, 0, 5, tzinfo=timezone.utc),
    )

    result = INGEST.ingest_identity_observations(repository, store_root=store)
    snapshot = STORE.load_identity_observation_store(
        store,
        repository_root=repository,
    )
    assert result["tracked_snapshot_count"] == 1
    assert result["published_count"] == 1
    assert result["operational_count"] == 1
    assert result["reconstruction_count"] == 0
    assert snapshot.head["capture_count"] == 1
    assert snapshot.captures[0].observation["pit_basis"] == "live_captured"
    assert snapshot.captures[0].completion_receipt == receipt


def test_ingest_rejects_a_worktree_snapshot_that_differs_from_the_pinned_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _temporary_repository(tmp_path)
    real_tracked_bytes = INGEST._tracked_bytes

    def changed_bytes(root: Path, commit: str, key: str) -> bytes:
        return real_tracked_bytes(root, commit, key) + b"changed"

    monkeypatch.setattr(INGEST, "_tracked_bytes", changed_bytes)
    with pytest.raises(INGEST.IdentityIngestError, match="not owned"):
        INGEST.ingest_identity_observations(
            repository,
            store_root=tmp_path / "identity-store",
        )


def test_ingest_never_downgrades_a_tracked_but_missing_receipt_to_reconstruction(
    tmp_path: Path,
) -> None:
    repository = _temporary_repository(tmp_path)
    snapshot_key = _git(
        repository,
        "ls-tree",
        "-r",
        "--name-only",
        "HEAD",
        "--",
        "data/symbol_directory/snapshots",
    )
    partition = Path(snapshot_key).stem
    receipt = (
        repository
        / "data"
        / "symbol_directory"
        / "receipts"
        / "snapshots"
        / f"{partition}.json"
    )
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}\n", encoding="utf-8")
    _git(repository, "add", receipt.relative_to(repository).as_posix())
    _git(repository, "commit", "-qm", "track completion receipt")
    receipt.unlink()
    store = tmp_path / "identity-store"

    with pytest.raises(INGEST.IdentityIngestError, match="presence differs"):
        INGEST.ingest_identity_observations(repository, store_root=store)

    assert not list((store / "captures").rglob("*.json"))


def test_ingest_rejects_a_tracked_receipt_without_its_snapshot(tmp_path: Path) -> None:
    repository = _temporary_repository(tmp_path)
    orphan = (
        repository
        / "data"
        / "symbol_directory"
        / "receipts"
        / "snapshots"
        / "2099-01-01.json"
    )
    orphan.parent.mkdir(parents=True)
    orphan.write_text("{}\n", encoding="utf-8")
    _git(repository, "add", orphan.relative_to(repository).as_posix())
    _git(repository, "commit", "-qm", "track orphan receipt")

    with pytest.raises(INGEST.IdentityIngestError, match="no matching snapshot"):
        INGEST.ingest_identity_observations(
            repository,
            store_root=tmp_path / "identity-store",
        )


def test_ingest_fails_closed_when_checkout_head_changes_during_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _temporary_repository(tmp_path)
    original = INGEST._repository_commit(repository)
    calls = 0

    def moving_head(root: Path) -> str:
        nonlocal calls
        calls += 1
        return original if calls == 1 else "f" * 40

    monkeypatch.setattr(INGEST, "_repository_commit", moving_head)
    with pytest.raises(INGEST.IdentityIngestError, match="changed during"):
        INGEST.ingest_identity_observations(
            repository,
            store_root=tmp_path / "identity-store",
        )


def test_entry_script_pins_the_repository_before_importing_engine_modules() -> None:
    source = (ROOT / "scripts" / "ingest_market_memory_identity.py").read_text(
        encoding="utf-8"
    )
    function = source.index("def ingest_identity_observations(")
    pin = source.index("deployed_commit = _repository_commit(root)", function)
    engine_import = source.index("from engine.neuralweb import", function)
    post_import_check = source.index(
        "if _repository_commit(root) != deployed_commit:", engine_import
    )
    assert "from engine.neuralweb import" not in source[:function]
    assert pin < engine_import < post_import_check
