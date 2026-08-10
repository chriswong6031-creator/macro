"""Sole-writer wrapper guards for W1B.3B technical actual outputs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import capture_market_memory_technicals as cli


def _bundle() -> SimpleNamespace:
    return SimpleNamespace(
        source_observation={"source_observation_id": "mmtechsrc_" + "a" * 64},
        feature_object={
            "snapshot_id": "mmtechsnap_" + "b" * 64,
            "session": "2026-08-07",
            "state": {
                "feature": "price.raw_close_ratio_20_sessions",
                "value": 1.0242532618054174,
            },
            "price_basis": {
                "raw_unadjusted": True,
                "split_adjusted": False,
                "dividend_adjusted": False,
                "economic_return": False,
            },
        },
    )


def _stored(bundle: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        generation_id="mmactualgeneration_" + "c" * 64,
        capture_receipt={
            "capture_id": "mmactualcapture_" + "d" * 64,
            "clocks": {
                "first_observed_at": "2026-08-10T16:00:00.000000Z",
                "available_at": "2026-08-10T16:00:00.000000Z",
            },
            "authority": {"context_only": True},
            "evidence_policy": {
                "training_eligible": False,
                "promotion_eligible": False,
            },
        },
        bundle=bundle,
    )


def test_capture_wrapper_pins_git_builds_once_and_validates_unresolved_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    store = tmp_path / "operator-store"
    commit = "1" * 40
    bundle = _bundle()
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(cli, "_repository_commit", lambda root: commit)

    def build(root: Path, *, pinned_commit: str) -> SimpleNamespace:
        calls.append(("build", root, pinned_commit))
        return bundle

    def validate(root: Path, *, repository_root: Path) -> Path:
        calls.append(("validate", root, repository_root))
        assert root == store
        return store.resolve()

    def capture(root: Path, *, bundle: SimpleNamespace) -> SimpleNamespace:
        calls.append(("capture", root, bundle))
        return _stored(bundle)

    monkeypatch.setattr(cli.technical, "build_current_spy_raw_close_ratio", build)
    monkeypatch.setattr(
        cli.technical_store,
        "validate_technical_actual_output_store_root",
        validate,
    )
    monkeypatch.setattr(cli.technical_store, "capture_technical_actual_output", capture)

    result = cli.capture_current_technical(repository, store_root=store)

    assert calls == [
        ("build", repository.resolve(), commit),
        ("validate", store, repository.resolve()),
        ("capture", store.resolve(), bundle),
    ]
    assert result == {
        "schema": "market_memory.technical_capture_result.v1",
        "deployed_commit": commit,
        "store_profile": cli.technical_store.STORE_PROFILE,
        "generation_id": "mmactualgeneration_" + "c" * 64,
        "capture_id": "mmactualcapture_" + "d" * 64,
        "source_observation_id": "mmtechsrc_" + "a" * 64,
        "snapshot_id": "mmtechsnap_" + "b" * 64,
        "session": "2026-08-07",
        "first_observed_at": "2026-08-10T16:00:00.000000Z",
        "available_at": "2026-08-10T16:00:00.000000Z",
        "feature": "price.raw_close_ratio_20_sessions",
        "value": 1.0242532618054174,
        "price_basis": {
            "raw_unadjusted": True,
            "split_adjusted": False,
            "dividend_adjusted": False,
            "economic_return": False,
        },
        "authority": {
            "context_only": True,
            "training_eligible": False,
            "promotion_eligible": False,
        },
    }


def test_cli_prints_one_finite_canonical_private_receipt(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {
        "schema": "market_memory.technical_capture_result.v1",
        "value": 1.25,
    }
    monkeypatch.setattr(
        cli, "capture_current_technical", lambda *args, **kwargs: expected
    )

    assert cli.main(["--repository-root", "/tmp/reviewed"]) == 0
    body = capsys.readouterr().out
    assert (
        body == '{"schema":"market_memory.technical_capture_result.v1","value":1.25}\n'
    )
    assert json.loads(body) == expected


def test_repository_commit_rejects_noncanonical_git_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="HEAD\n"),
    )
    with pytest.raises(
        cli.MarketMemoryTechnicalCaptureCliError,
        match="commit is malformed",
    ):
        cli._repository_commit(tmp_path)


def test_production_cli_exposes_no_source_clock_or_authority_override() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "--url",
        "--manifest-url",
        "--spy-url",
        "--fetcher",
        "--pinned-commit",
        "--first-observed-at",
        "--available-at",
        "--session",
        "--symbol",
        "--feature",
        "--snapshot-id",
        "--authority",
        "--entitlement-record",
    ):
        assert forbidden not in source
