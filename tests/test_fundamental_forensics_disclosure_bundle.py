"""Contract tests for the disclosure-projection bundle the nightly render restores.

The bundle is the ONLY Filing Forensics input on the render path since 2026-08-08,
so its failure modes are the interesting half: a pointer that binds nothing, a
ticker set that quietly shrank, a bundle old enough that the producing lane is
dead, and a byte that changed in transit must each stop the engine's hard gate
rather than hand the broad build a shallow state.

Projections here are REAL ones built by ``build_disclosure_projection`` over a
local fixture cache (no network, no fixtures shared with another test module),
because the bundle's identity is a hash of their canonical bytes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from collectors.edgar_forensics import endpoint_url, persist_response
from collectors.sec_document_spine import persist_archive_document, persist_filing_manifest
from engine.fundamental_forensics.disclosure_bundle import (
    DISCLOSURE_BUNDLE_LATEST_KEY,
    DisclosureBundleError,
    build_disclosure_bundle,
    bundle_object_key,
    publish_disclosure_bundle,
    restore_disclosure_bundle,
    validate_disclosure_bundle,
)
from engine.fundamental_forensics.disclosure_projection import (
    build_disclosure_projection,
    disclosure_projection_path,
    write_disclosure_projection,
)
from engine.fundamental_forensics.models import canonical_json
from engine.fundamental_forensics.sec_document_spine import (
    build_filing_manifests,
    with_document_retrievals,
)
from engine.research_vault.r2_store import LocalStore
from scripts import fundamental_forensics_disclosure_bundle as cli


RECORDED_AT = "2026-08-01T12:00:00Z"
AS_OF = "2026-08-01T23:59:59Z"
COMPUTED_AT = "2026-08-02T00:05:00Z"
PUBLISHED_AT = "2026-08-02T02:40:00Z"
NOW = "2026-08-02T06:00:00Z"


def _submissions(cik: int) -> dict:
    accessions = [f"{cik:010d}-26-00000{index}" for index in (4, 3, 2, 1)]
    return {
        "cik": str(cik),
        "name": f"Bundle Fixture {cik}, Inc.",
        "filings": {
            "recent": {
                "accessionNumber": accessions,
                "form": ["10-Q", "10-Q", "10-K", "10-K"],
                "filingDate": ["2026-08-01", "2026-05-01", "2026-02-20", "2025-02-20"],
                "reportDate": ["2026-06-30", "2026-03-31", "2025-12-31", "2024-12-31"],
                "acceptanceDateTime": [
                    "2026-08-01T16:00:00.000Z",
                    "2026-05-01T16:00:00.000Z",
                    "2026-02-20T16:00:00.000Z",
                    "2025-02-20T16:00:00.000Z",
                ],
                "primaryDocument": ["q2.htm", "q1.htm", "fy25.htm", "fy24.htm"],
                "isXBRL": [1, 1, 1, 1],
                "isInlineXBRL": [1, 1, 1, 1],
            }
        },
    }


def _document(accession: str) -> bytes:
    changes = {
        "1": "Customer concentration may affect results.",
        "2": "Customer concentration and new supplier concentration may affect results.",
        "3": "Revenue is recognized when promised services transfer to customers.",
        "4": "Revenue is recognized when services transfer and collection is probable.",
    }
    body = changes[accession[-1]]
    return (
        "<html><body>"
        "<h1>Item 1A. Risk Factors</h1>"
        f"<p>{body}</p>"
        "<h1>Significant Accounting Policies</h1>"
        f"<p>{body}</p>"
        "</body></html>"
    ).encode("utf-8")


def _prepare_cache(cache_root: Path, *, cik: int, ticker: str) -> tuple[Path, Path]:
    raw_root = cache_root / "raw"
    archive_root = cache_root / "archive"
    payload = _submissions(cik)
    persist_response(
        raw_root,
        cik=cik,
        endpoint="submissions",
        url=endpoint_url(cik, "submissions"),
        content=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        retrieved_at=RECORDED_AT,
    )
    for manifest in build_filing_manifests(payload, cik=cik, ticker=ticker, recorded_at=RECORDED_AT):
        primary = manifest["documents"][0]
        receipt = persist_archive_document(
            archive_root,
            primary,
            _document(manifest["filing"]["accession"]),
            retrieved_at=RECORDED_AT,
        )
        stored = with_document_retrievals(manifest, {primary["document_id"]: receipt.to_dict()})
        persist_filing_manifest(archive_root, stored)
    return raw_root, archive_root


def _projection(cache_root: Path, *, cik: int, ticker: str) -> dict:
    raw_root, archive_root = _prepare_cache(cache_root, cik=cik, ticker=ticker)
    return build_disclosure_projection(
        raw_root=raw_root,
        archive_root=archive_root,
        ticker=ticker,
        cik=cik,
        as_of=AS_OF,
        computed_at=COMPUTED_AT,
    )


@pytest.fixture(scope="module")
def projections(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict]:
    """Two real projections; module-scoped because building them is the slow part."""
    base = tmp_path_factory.mktemp("bundle-projections")
    return {
        "TST": _projection(base / "tst", cik=1, ticker="TST"),
        "TSU": _projection(base / "tsu", cik=2, ticker="TSU"),
    }


def _publish(store: LocalStore, projections: dict[str, dict], *, published_at: str = PUBLISHED_AT) -> dict:
    return publish_disclosure_bundle(
        store, build_disclosure_bundle(projections, published_at=published_at)
    )


def test_publish_then_restore_round_trips_every_projection_byte_exact(
    tmp_path: Path, projections: dict[str, dict]
) -> None:
    store = LocalStore(tmp_path / "private-store")
    receipt = _publish(store, projections)

    assert receipt["schema"] == "fundamental_forensics.disclosure_projection_bundle_publish/v1"
    assert receipt["tickers"] == ["TST", "TSU"]
    assert receipt["pointer_updated"] is True
    assert receipt["bundle_key"] == bundle_object_key(receipt["bundle_id"])

    pointer = json.loads((store.get_bytes(DISCLOSURE_BUNDLE_LATEST_KEY) or b"{}").decode("utf-8"))
    assert pointer["bundle_id"] == receipt["bundle_id"]
    assert pointer["bundle_key"] == receipt["bundle_key"]

    output_root = tmp_path / "engine-checkout"
    result = restore_disclosure_bundle(
        store, output_root=output_root, expected_tickers=["TSU", "tst"], now=NOW
    )

    assert result["schema"] == "fundamental_forensics.disclosure_projection_bundle_restore/v1"
    assert result["bundle_id"] == receipt["bundle_id"]
    assert result["restored_files"] == 2
    assert result["tickers"] == ["TST", "TSU"]
    assert result["stale_warning"] is False
    for ticker, projection in projections.items():
        path = disclosure_projection_path(output_root, ticker)
        assert path.read_bytes() == canonical_json(projection).encode("utf-8")


def test_republishing_the_same_bundle_is_idempotent(tmp_path: Path, projections: dict[str, dict]) -> None:
    store = LocalStore(tmp_path / "private-store")
    first = _publish(store, projections)
    second = _publish(store, projections)

    assert second["bundle_id"] == first["bundle_id"]
    assert first["pointer_updated"] is True
    assert second["pointer_updated"] is False


def test_publish_refuses_to_rewind_the_pointer_to_an_older_bundle(
    tmp_path: Path, projections: dict[str, dict]
) -> None:
    store = LocalStore(tmp_path / "private-store")
    newer = _publish(store, projections, published_at="2026-08-03T02:40:00Z")

    with pytest.raises(DisclosureBundleError, match="rewind"):
        _publish(store, projections, published_at="2026-08-02T02:40:00Z")

    pointer = json.loads((store.get_bytes(DISCLOSURE_BUNDLE_LATEST_KEY) or b"{}").decode("utf-8"))
    assert pointer["bundle_id"] == newer["bundle_id"]


def test_bundle_refuses_a_mislabeled_or_invalid_projection(projections: dict[str, dict]) -> None:
    with pytest.raises(DisclosureBundleError, match="does not match projection issuer"):
        build_disclosure_bundle({"AAPL": projections["TST"]}, published_at=PUBLISHED_AT)

    broken = dict(projections["TST"])
    broken["projection_id"] = "ffdisclosure_projection_" + "0" * 64
    with pytest.raises(DisclosureBundleError, match="is invalid"):
        build_disclosure_bundle({"TST": broken}, published_at=PUBLISHED_AT)

    with pytest.raises(DisclosureBundleError, match="at least one projection"):
        build_disclosure_bundle({}, published_at=PUBLISHED_AT)

    with pytest.raises(DisclosureBundleError, match="published_at"):
        build_disclosure_bundle({"TST": projections["TST"]}, published_at="2026-08-02T02:40:00")


def test_restore_refuses_when_no_bundle_has_been_published(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "private-store")
    with pytest.raises(DisclosureBundleError, match="no published disclosure bundle"):
        restore_disclosure_bundle(
            store, output_root=tmp_path / "out", expected_tickers=["TST"], now=NOW
        )


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        (["TST"], "unexpected: \\['TSU'\\]"),
        (["TST", "TSU", "TSV"], "missing: \\['TSV'\\]"),
    ],
)
def test_restore_refuses_a_ticker_set_that_is_not_exactly_the_expected_one(
    tmp_path: Path, projections: dict[str, dict], expected: list[str], message: str
) -> None:
    store = LocalStore(tmp_path / "private-store")
    _publish(store, projections)
    output_root = tmp_path / "engine-checkout"

    with pytest.raises(DisclosureBundleError, match=message):
        restore_disclosure_bundle(
            store, output_root=output_root, expected_tickers=expected, now=NOW
        )
    assert not list(output_root.rglob("*.json"))


def test_restore_warns_then_refuses_as_the_producing_lane_goes_dark(
    tmp_path: Path, projections: dict[str, dict]
) -> None:
    store = LocalStore(tmp_path / "private-store")
    _publish(store, projections)
    output_root = tmp_path / "engine-checkout"

    fresh = restore_disclosure_bundle(
        store, output_root=output_root, expected_tickers=["TST", "TSU"], now="2026-08-04T02:40:00Z"
    )
    assert fresh["stale_warning"] is False

    stale = restore_disclosure_bundle(
        store, output_root=output_root, expected_tickers=["TST", "TSU"], now="2026-08-07T02:40:00Z"
    )
    assert stale["stale_warning"] is True
    assert stale["restored_files"] == 2

    with pytest.raises(DisclosureBundleError, match="days old"):
        restore_disclosure_bundle(
            store,
            output_root=output_root,
            expected_tickers=["TST", "TSU"],
            now="2026-09-02T02:40:00Z",
        )


def test_restore_refuses_a_bundle_published_in_the_future(
    tmp_path: Path, projections: dict[str, dict]
) -> None:
    store = LocalStore(tmp_path / "private-store")
    _publish(store, projections, published_at="2026-08-02T06:00:00Z")

    # Inside the tolerated one-hour skew between two hosts sampling two clocks.
    assert restore_disclosure_bundle(
        store,
        output_root=tmp_path / "engine-checkout",
        expected_tickers=["TST", "TSU"],
        now="2026-08-02T05:30:00Z",
    )["restored_files"] == 2

    with pytest.raises(DisclosureBundleError, match="future"):
        restore_disclosure_bundle(
            store,
            output_root=tmp_path / "engine-checkout",
            expected_tickers=["TST", "TSU"],
            now="2026-08-02T03:30:00Z",
        )


def test_restore_refuses_tampered_bundle_bytes(tmp_path: Path, projections: dict[str, dict]) -> None:
    local_dir = tmp_path / "private-store"
    store = LocalStore(local_dir)
    receipt = _publish(store, projections)
    object_path = local_dir / receipt["bundle_key"]

    original = object_path.read_bytes()
    body = json.loads(original.decode("utf-8"))
    body["published_at"] = "2026-08-02T02:41:00.000000Z"
    object_path.write_bytes(canonical_json(body).encode("utf-8"))
    with pytest.raises(DisclosureBundleError, match="identity or canonical body"):
        restore_disclosure_bundle(
            store, output_root=tmp_path / "out", expected_tickers=["TST", "TSU"], now=NOW
        )

    object_path.write_bytes(original + b" ")
    with pytest.raises(DisclosureBundleError, match="not strict UTF-8 JSON|canonically encoded"):
        restore_disclosure_bundle(
            store, output_root=tmp_path / "out", expected_tickers=["TST", "TSU"], now=NOW
        )


def test_restore_refuses_a_pointer_that_binds_a_different_bundle(
    tmp_path: Path, projections: dict[str, dict]
) -> None:
    local_dir = tmp_path / "private-store"
    store = LocalStore(local_dir)
    published = _publish(store, projections)
    other = build_disclosure_bundle({"TST": projections["TST"]}, published_at=PUBLISHED_AT)

    # A valid, canonical bundle parked under ANOTHER identity's key: only the
    # pointer/bundle identity cross-check can catch this substitution.
    decoy_key = bundle_object_key(other["bundle_id"])
    decoy_path = local_dir / decoy_key
    decoy_path.parent.mkdir(parents=True, exist_ok=True)
    decoy_path.write_bytes((local_dir / published["bundle_key"]).read_bytes())
    pointer = json.loads((store.get_bytes(DISCLOSURE_BUNDLE_LATEST_KEY) or b"{}").decode("utf-8"))
    pointer["bundle_id"] = other["bundle_id"]
    pointer["bundle_key"] = decoy_key
    (local_dir / DISCLOSURE_BUNDLE_LATEST_KEY).write_bytes(canonical_json(pointer).encode("utf-8"))

    with pytest.raises(DisclosureBundleError, match="pointer does not bind this bundle"):
        restore_disclosure_bundle(
            store, output_root=tmp_path / "out", expected_tickers=["TST", "TSU"], now=NOW
        )


def test_validate_rejects_a_ticker_index_that_disagrees_with_the_projections(
    projections: dict[str, dict],
) -> None:
    bundle = build_disclosure_bundle(projections, published_at=PUBLISHED_AT)
    mutated = dict(bundle)
    mutated["tickers"] = ["TST"]
    with pytest.raises(DisclosureBundleError, match="ticker index"):
        validate_disclosure_bundle(mutated)


def _targets_file(path: Path, targets: list[tuple[str, str]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "fundamental_forensics.wave2_targets/v1",
                "targets": [{"ticker": ticker, "cik": cik} for ticker, cik in targets],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_cli_publishes_and_restores_through_the_same_target_file(
    tmp_path: Path, projections: dict[str, dict], capsys: pytest.CaptureFixture[str]
) -> None:
    targets = _targets_file(tmp_path / "targets.json", [("TST", "1"), ("TSU", "2")])
    source_root = tmp_path / "lane-checkout"
    for projection in projections.values():
        write_disclosure_projection(source_root, projection)
    store_dir = tmp_path / "private-store"

    assert cli.main(
        [
            "--publish",
            "--targets-file", str(targets),
            "--root", str(source_root),
            "--published-at", PUBLISHED_AT,
            "--local-store", str(store_dir),
        ]
    ) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["tickers"] == ["TST", "TSU"]

    engine_root = tmp_path / "engine-checkout"
    assert cli.main(
        [
            "--restore",
            "--targets-file", str(targets),
            "--root", str(engine_root),
            "--now", NOW,
            "--local-store", str(store_dir),
        ]
    ) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["restored_files"] == 2
    assert restored["stale_warning"] is False
    for ticker in projections:
        assert (
            disclosure_projection_path(engine_root, ticker).read_bytes()
            == disclosure_projection_path(source_root, ticker).read_bytes()
        )


def test_cli_refuses_to_publish_a_partial_bundle(
    tmp_path: Path, projections: dict[str, dict], capsys: pytest.CaptureFixture[str]
) -> None:
    targets = _targets_file(tmp_path / "targets.json", [("TST", "1"), ("TSU", "2")])
    source_root = tmp_path / "lane-checkout"
    write_disclosure_projection(source_root, projections["TST"])  # TSU deliberately absent

    rc = cli.main(
        [
            "--publish",
            "--targets-file", str(targets),
            "--root", str(source_root),
            "--published-at", PUBLISHED_AT,
            "--local-store", str(tmp_path / "private-store"),
        ]
    )

    assert rc == 1
    annotation = [
        line for line in capsys.readouterr().out.splitlines() if line.startswith("::")
    ]
    assert len(annotation) == 1
    assert annotation[0].startswith("::warning title=fundamental_forensics_disclosure_bundle::")
    assert not (tmp_path / "private-store").exists()


def test_cli_annotates_a_stale_bundle_at_the_line_start(
    tmp_path: Path, projections: dict[str, dict], capsys: pytest.CaptureFixture[str]
) -> None:
    targets = _targets_file(tmp_path / "targets.json", [("TST", "1"), ("TSU", "2")])
    store_dir = tmp_path / "private-store"
    _publish(LocalStore(store_dir), projections)

    rc = cli.main(
        [
            "--restore",
            "--targets-file", str(targets),
            "--root", str(tmp_path / "engine-checkout"),
            "--now", "2026-08-07T02:40:00Z",
            "--local-store", str(store_dir),
        ]
    )

    assert rc == 0
    lines = capsys.readouterr().out.splitlines()
    warnings = [line for line in lines if line.startswith("::")]
    assert len(warnings) == 1
    assert warnings[0].startswith("::warning title=fundamental_forensics_disclosure_bundle::")
    assert "5.0 days old" in warnings[0]


def test_cli_requires_exactly_one_direction_and_a_targets_file(tmp_path: Path) -> None:
    targets = _targets_file(tmp_path / "targets.json", [("TST", "1")])
    with pytest.raises(SystemExit) as neither:
        cli.main(["--targets-file", str(targets)])
    assert neither.value.code == 2

    with pytest.raises(SystemExit) as both:
        cli.main(["--publish", "--restore", "--targets-file", str(targets)])
    assert both.value.code == 2

    with pytest.raises(SystemExit) as missing_file:
        cli.main(["--restore", "--now", NOW])
    assert missing_file.value.code == 2


def test_cli_requires_the_clock_that_belongs_to_its_direction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    targets = _targets_file(tmp_path / "targets.json", [("TST", "1")])

    assert cli.main(["--restore", "--targets-file", str(targets), "--local-store", str(tmp_path / "s")]) == 1
    assert "--now is required" in capsys.readouterr().out

    assert cli.main(["--publish", "--targets-file", str(targets), "--local-store", str(tmp_path / "s")]) == 1
    assert "--published-at is required" in capsys.readouterr().out
