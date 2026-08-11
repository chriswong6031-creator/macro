"""No-network contracts for the one-shot AAPL B4 seed runner."""
from __future__ import annotations

import importlib.util
import json
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from engine.fundamental_forensics.companyfacts_ledger import (
    CompanyFactsLedgerConversionConfig,
    PinnedSubmissionsSource,
)
from engine.fundamental_forensics.filing_attestation import CompanyFactsSourcePaths
from engine.fundamental_forensics.sec_document_spine import build_filing_manifests
from engine.research_vault.r2_store import LocalStore

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "seed_fundamental_forensics_attested_history.py"
VERIFIER_PATH = ROOT / "scripts" / "verify_fundamental_forensics_attested_history_seed_bundle.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "attested-history-aapl-seed.yml"
LOCK_PATH = ROOT / "requirements" / "attested-history-macos-arm64-py312.lock"


def _seed_module():
    spec = importlib.util.spec_from_file_location("_attested_history_seed_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _verifier_module():
    spec = importlib.util.spec_from_file_location("_attested_history_seed_verifier_test", VERIFIER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _submissions() -> dict:
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-25-000079", "0000320193-24-000123"],
                "form": ["10-K", "10-K"],
                "filingDate": ["2025-10-31", "2024-11-01"],
                "reportDate": ["2025-09-27", "2024-09-28"],
                "acceptanceDateTime": ["2025-10-31T10:00:00Z", "2024-11-01T10:00:00Z"],
                "primaryDocument": ["aapl-20250927.htm", "aapl-20240928.htm"],
                "isXBRL": [1, 1],
                "isInlineXBRL": [1, 1],
            },
            "files": [{"name": "CIK0000320193-submissions-001.json", "filingCount": 1238}],
        },
    }


def _packet(seed):
    manifest = build_filing_manifests(
        _submissions(),
        cik=seed.AAPL_CIK,
        ticker=seed.AAPL_TICKER,
        recorded_at="2026-08-03T18:00:00Z",
    )[0]
    recent = PinnedSubmissionsSource(
        source_name="recent",
        receipt_path="0000320193/submissions/recent.receipt.json",
        object_path="0000320193/submissions/recent.json.gz",
        is_older=False,
    )
    older = PinnedSubmissionsSource(
        source_name="CIK0000320193-submissions-001.json",
        receipt_path="0000320193/submissions/older.receipt.json",
        object_path="0000320193/submissions/older.json.gz",
        is_older=True,
    )
    return seed.build_operator_packet(
        base_query_snapshot_id="ffqs_" + ("a" * 64),
        source_snapshot_id="ffsecsrc_" + ("b" * 64),
        manifest=manifest,
        archive_index_document_value={"document_id": "index"},
        member_states={
            "aapl-20250927.htm": {"state": "stored"},
            "aapl-20250927_cal.xml": "not_requested",
        },
        ixbrl_document_name="aapl-20250927.htm",
        companyfacts_paths=CompanyFactsSourcePaths(
            manifest_path="wave3_companyfacts/manifests/0000320193/manifest.json",
            capture_path="0000320193/companyfacts_v3/captures/capture.json",
            response_path="0000320193/companyfacts_v3/objects/aa/response.json.gz",
        ),
        submissions_recorded_at="2026-08-03T18:00:00Z",
        recent_submissions=recent,
        older_submissions=(older,),
        conversion_config=CompanyFactsLedgerConversionConfig(),
    )


def _review_artifact(path: Path) -> dict:
    content = path.read_bytes()
    return {
        "filename": path.name,
        "sha256": sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _preflight_bytes(receipt: dict) -> bytes:
    return json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _production_review_bundle(tmp_path):
    seed = _seed_module()
    verifier = _verifier_module()
    output = tmp_path / "artifact"
    output.mkdir(parents=True)
    expected = verifier.ExpectedRun(
        repository=verifier.EXPECTED_REPOSITORY,
        sha="c" * 40,
        ref=verifier.EXPECTED_REF,
        run_id=31534160304,
        run_attempt=1,
        environment=verifier.EXPECTED_ENVIRONMENT,
        workflow=verifier.EXPECTED_WORKFLOW,
        dependency_lock_sha256="d" * 64,
    )
    packet = _packet(seed)
    packet_path = output / verifier.PACKET_FILENAME
    packet_path.write_bytes(seed.canonical_json(packet).encode("utf-8"))
    preflight = {
        "schema": "fundamental_forensics.attested_history_preflight_receipt/v1",
        "status": "prepared",
        "operator_verification_observed_at": "2026-08-11T20:41:57.100000Z",
        "publication": {
            "publication_performed": False,
            "pointer_advanced": False,
            "immutable_objects_written": False,
            "storage_write_attempts": 0,
        },
        "redaction": {
            "raw_source_payloads_included": False,
            "storage_paths_included": False,
            "storage_endpoints_included": False,
            "storage_credentials_included": False,
            "error_messages_included": False,
        },
        "nonclaims": [
            "not_published",
            "not_a_freshness_claim",
            "not_a_filing_completeness_claim",
            "not_investment_or_trading_authority",
        ],
        "inputs": {
            "base_query_snapshot_id": packet["base_query_snapshot_id"],
            "source_snapshot_id": packet["source_snapshot_id"],
            "cik": packet["packet"]["cik"],
            "accession": packet["packet"]["filing"]["accession"],
            "filing_manifest_id": packet["packet"]["filing"]["manifest_id"],
        },
        "materialization": {
            "filing_package_id": "ffpkg_" + "1" * 64,
            "ixbrl_extraction_id": "ffxbrl_" + "2" * 64,
            "filing_attestation_id": "ffatt_" + "3" * 64,
            "companyfacts_conversion_receipt_id": "cffledger_" + "4" * 64,
        },
        "binding_plan": {
            "binding_count": 1,
            "candidate_leaf_count": 1,
            "rejected_leaf_count": 0,
            "rejection_reason_counts": {},
            "coverage": [],
        },
        "candidate": {
            "prepared_in_memory": True,
            "candidate_snapshot_id": "ffqsv2_" + "5" * 64,
            "candidate_published_at_is_not_an_actual_publication": True,
        },
    }
    preflight_path = output / verifier.PREFLIGHT_FILENAME
    preflight_path.write_bytes(_preflight_bytes(preflight))
    seed_receipt = {
        "schema": "fundamental_forensics.attested_history_aapl_seed/v1",
        "status": "prepared",
        "ticker": "AAPL",
        "cik": "0000320193",
        "source_snapshot_id": packet["source_snapshot_id"],
        "base_query_snapshot_id": packet["base_query_snapshot_id"],
        "clocks": {
            "source_snapshot_at": "2026-08-11T20:41:56.000000Z",
            "operator_verification_observed_at": "2026-08-11T20:41:57.100000Z",
            "preflight_completed_at": "2026-08-11T20:41:58.200000Z",
        },
        "dependency_lock": {
            "path": verifier.DEPENDENCY_LOCK_PATH,
            "sha256": expected.dependency_lock_sha256,
            "target": "CPython 3.12 macOS arm64",
        },
        "run_provenance": expected.as_provenance(),
        "selected_occurrence_id": "rawfact_" + "6" * 64,
        "selected_match_id": "ffatt_match_" + "7" * 64,
        "declared_older_submissions_count": 1,
        "archive_inventory_member_count": 2,
        "archive_stored_member_count": 1,
        "archive_not_requested_member_count": 1,
        "storage_control_probe": {
            "key": "fundamental_forensics/attested-history-seed-control/v1/" + "a" * 32,
            "final_sha256": verifier._FINAL_CONTROL_SHA256,
            "outcomes": {
                "absent_before_create": True,
                "absent_create_succeeded": True,
                "conflicting_absent_create_rejected": True,
                "exact_version_advance_succeeded": True,
                "stale_version_advance_rejected": True,
                "readonly_final_readback_verified": True,
            },
        },
        "preflight": {"status": "prepared", "storage_write_attempts": 0},
        "review_artifacts": {
            "operator_packet": _review_artifact(packet_path),
            "preflight_receipt": _review_artifact(preflight_path),
        },
        "nonclaims": [
            "not_a_complete_filing_archive",
            "not_a_dimensions_identity_claim",
            "not_a_freshness_claim_after_preflight",
            "not_investment_or_trading_authority",
        ],
    }
    seed_path = output / verifier.SEED_FILENAME
    seed_path.write_bytes(seed.canonical_json(seed_receipt).encode("utf-8"))
    bundle = {
        "schema": "fundamental_forensics.attested_history_aapl_seed_bundle/v1",
        "status": "prepared",
        "run_provenance": expected.as_provenance(),
        "dependency_lock": {
            "path": verifier.DEPENDENCY_LOCK_PATH,
            "sha256": expected.dependency_lock_sha256,
        },
        "files": {
            verifier.PACKET_FILENAME: _review_artifact(packet_path),
            verifier.PREFLIGHT_FILENAME: _review_artifact(preflight_path),
            verifier.SEED_FILENAME: _review_artifact(seed_path),
        },
        "assembled_at": "2026-08-11T20:41:59.300000Z",
        "nonclaims": [
            "review_artifact_not_canonical_publication",
            "credential_separation_not_parent_iam_proof",
        ],
    }
    (output / verifier.BUNDLE_FILENAME).write_bytes(seed.canonical_json(bundle).encode("utf-8"))
    return seed, verifier, output, expected


def _exercise_full_seed(monkeypatch, tmp_path, *, fail_stage: str | None = None):
    """Run the orchestration graph with deterministic no-network components."""
    seed = _seed_module()
    shared = tmp_path / "store"
    writer = LocalStore(shared)
    readonly = LocalStore(shared)
    source_latest = "fundamental_forensics/sec-source/v1/latest.json"
    query_latest = "fundamental_forensics/query-snapshots/v1/latest.json"
    writer.put_bytes(source_latest, b"source-before")
    writer.put_bytes(query_latest, b"query-before")
    calls: dict[str, object] = {
        "sync": [],
        "publish": [],
        "retrieval_kwargs": [],
        "conversion_clocks": [],
        "packet_clocks": [],
        "stages": [],
    }

    class FakeSubmissionsCollector:
        def __init__(self, *_args, **_kwargs):
            pass

        def fetch(self, cik, endpoint, **kwargs):
            assert cik == seed.AAPL_CIK and endpoint == "submissions"
            assert "retrieved_at" not in kwargs
            calls["retrieval_kwargs"].append(dict(kwargs))
            return seed.RetrievalReceipt(
                schema="sec.raw.receipt/v1",
                cik=seed.AAPL_CIK,
                endpoint="submissions",
                url="https://data.sec.gov/submissions/CIK0000320193.json",
                retrieved_at="2026-08-03T18:00:01.100000Z",
                sha256="1" * 64,
                bytes=10,
                object_path="0000320193/submissions/recent.json.gz",
                http_etag=None,
                http_last_modified=None,
            )

        def fetch_historical_submissions_file(self, cik, name, **kwargs):
            assert cik == seed.AAPL_CIK
            assert name == "CIK0000320193-submissions-001.json"
            assert "retrieved_at" not in kwargs
            calls["retrieval_kwargs"].append(dict(kwargs))
            return seed.RetrievalReceipt(
                schema="sec.raw.receipt/v1",
                cik=seed.AAPL_CIK,
                endpoint="submissions",
                url=f"https://data.sec.gov/submissions/{name}",
                retrieved_at="2026-08-03T18:00:02.200000Z",
                sha256="2" * 64,
                bytes=10,
                object_path="0000320193/submissions/older.json.gz",
                http_etag=None,
                http_last_modified=None,
            )

    monkeypatch.setattr(seed, "SecForensicsCollector", FakeSubmissionsCollector)
    monkeypatch.setattr(
        seed,
        "read_current_submissions_receipt",
        lambda *_args, **_kwargs: _submissions(),
    )

    def fake_retain(**kwargs):
        assert "retrieved_at" not in kwargs
        calls["retrieval_kwargs"].append(dict(kwargs))
        manifest = seed.select_latest_aapl_10k(
            _submissions(),
            recorded_at="2026-08-03T18:00:02.200000Z",
            as_of="2026-08-03T18:00:02.200000Z",
        )
        retrieval = {
            "retrieved_at": "2026-08-03T18:00:04.400000Z",
            "storage_key": "objects/primary",
            "content_sha256": "3" * 64,
            "byte_length": 1,
        }
        return (
            manifest,
            "manifest-key",
            {"document_id": "index", "retrieval": {"retrieved_at": "2026-08-03T18:00:03.300000Z"}},
            {
                "aapl-20250927.htm": {
                    "state": "stored",
                    "retrieval": retrieval,
                    "storage_key": "objects/primary",
                    "content_sha256": "3" * 64,
                    "byte_length": 1,
                },
                "aapl-20250927_cal.xml": "not_requested",
            },
            "aapl-20250927.htm",
        )

    monkeypatch.setattr(seed, "retain_selected_filing", fake_retain)
    monkeypatch.setattr(
        seed,
        "acquire_companyfacts",
        lambda **_kwargs: {
            "run": {
                "ticker_receipts": [
                    {
                        "status": "complete",
                        "manifest_key": "wave3_companyfacts/manifests/0000320193/manifest.json",
                        "clocks": {"recorded_at": "2026-08-03T18:00:06.500000Z"},
                    }
                ]
            }
        },
    )
    monkeypatch.setattr(
        seed,
        "read_companyfacts_manifest",
        lambda *_args, **_kwargs: {
            "source": {
                "capture_receipt_key": "0000320193/companyfacts_v3/captures/capture.json",
                "response_object_path": "0000320193/companyfacts_v3/objects/aa/response.json.gz",
            }
        },
    )

    def fake_sync(**kwargs):
        calls["sync"].append(kwargs["publish_latest"])
        writer.put_bytes_strict_conditional(
            "fundamental_forensics/sec-source/v1/snapshots/source-id.json",
            b"source-immutable",
            expected_version=None,
        )
        if fail_stage == "after_source":
            raise RuntimeError("injected after source immutable stage")
        return SimpleNamespace(snapshot_id="ffsecsrc_" + "a" * 64)

    monkeypatch.setattr(seed, "sync_source_roots", fake_sync)

    class FakeAuthority:
        def __init__(self, *, store, snapshot_id):
            self.store = store
            self.snapshot_id = snapshot_id

        def read_archive_document(self, **_kwargs):
            return SimpleNamespace(content=b"x")

    monkeypatch.setattr(seed, "PinnedSourceAuthority", FakeAuthority)
    def fake_conversion(**kwargs):
        calls["conversion_clocks"].append(kwargs["submissions_recorded_at"])
        return object()

    monkeypatch.setattr(seed, "load_companyfacts_ledger_from_pinned_source", fake_conversion)

    class FakePackage:
        def to_dict(self):
            return {
                "inventory": [
                    {
                        "document_name": "aapl-20250927.htm",
                        "storage_key": "objects/primary",
                        "retrieval": {"retrieved_at": "2026-08-03T18:00:04.400000Z"},
                        "byte_length": 1,
                    }
                ]
            }

    monkeypatch.setattr(seed, "materialize_filing_package_from_pinned_source", lambda *_args, **_kwargs: FakePackage())
    monkeypatch.setattr(seed, "build_ixbrl_extraction", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(seed, "build_filing_attestation", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        seed,
        "prepare_attested_history_base_candidate",
        lambda **_kwargs: SimpleNamespace(
            prepared=object(),
            selected_occurrence_id="occurrence-id",
            selected_match_id="match-id",
        ),
    )

    def fake_publish(_store, _prepared, *, publish_latest):
        calls["publish"].append(publish_latest)
        writer.put_bytes_strict_conditional(
            "fundamental_forensics/query-snapshots/v1/manifests/base-id.json",
            b"base-immutable",
            expected_version=None,
        )
        if fail_stage == "after_base":
            raise RuntimeError("injected after base immutable stage")
        return SimpleNamespace(snapshot_id="ffqs_" + "b" * 64)

    monkeypatch.setattr(seed, "publish_query_snapshot", fake_publish)
    def fake_packet(**kwargs):
        calls["packet_clocks"].append(kwargs["submissions_recorded_at"])
        return {"packet": "review"}

    monkeypatch.setattr(seed, "build_operator_packet", fake_packet)
    monkeypatch.setattr(
        seed,
        "run_seed_preflight",
        lambda **_kwargs: {"status": "prepared", "publication": {"storage_write_attempts": 0}},
    )
    monkeypatch.setattr(
        seed,
        "write_private_receipt",
        lambda output, receipt: seed._private_json(
            Path(output) / "attested_history_preflight_receipt.json", receipt
        ),
    )
    clocks = iter(
        [
            "2026-08-03T18:00:05.000000Z",
            "2026-08-03T18:00:06.600000Z",
            "2026-08-03T18:00:07.700000Z",
            "2026-08-03T18:00:08.800000Z",
            "2026-08-03T18:00:09.900000Z",
        ]
    )
    work = tmp_path / "work"
    output = tmp_path / "output"
    error = None
    receipt = None
    try:
        receipt = seed.run_aapl_seed(
            work_dir=work,
            output_dir=output,
            user_agent="MastermindX data@mastermind-x.com",
            writer_store=writer,
            readonly_store=readonly,
            now=lambda: next(clocks),
            dependency_lock_digest="d" * 64,
            on_stage=calls["stages"].append,
        )
    except Exception as exc:  # returned so failure assertions remain precise
        error = exc
    assert writer.get_bytes(source_latest) == b"source-before"
    assert writer.get_bytes(query_latest) == b"query-before"
    return seed, calls, receipt, error, output


def test_seed_is_closed_to_aapl_and_all_declared_historical_submissions():
    seed = _seed_module()
    assert seed.declared_older_submissions_names(_submissions()) == (
        "CIK0000320193-submissions-001.json",
    )
    wrong = _submissions()
    wrong["filings"]["files"] = [{"name": "CIK0000000001-submissions-001.json"}]
    with pytest.raises(seed.AttestedHistorySeedError, match="does not bind AAPL"):
        seed.declared_older_submissions_names(wrong)
    duplicate = _submissions()
    duplicate["filings"]["files"] *= 2
    with pytest.raises(seed.AttestedHistorySeedError, match="duplicate"):
        seed.declared_older_submissions_names(duplicate)


def test_current_submissions_reads_returned_receipt_not_hostile_latest(tmp_path):
    seed = _seed_module()
    content = json.dumps(_submissions(), sort_keys=True, separators=(",", ":")).encode()
    digest = seed.sha256(content).hexdigest()
    object_path = f"{seed.AAPL_CIK}/submissions/{digest}.json.gz"
    target = tmp_path / object_path
    target.parent.mkdir(parents=True)
    target.write_bytes(seed.gzip.compress(content, mtime=0))
    # A hostile concurrent process advances the mutable pointer to unrelated
    # bytes. Exact-receipt loading must never inspect or follow this file.
    (target.parent / "latest.json").write_text('{"object_path":"attacker"}', encoding="utf-8")
    receipt = seed.RetrievalReceipt(
        schema="fundamental_forensics_retrieval.v1",
        cik=seed.AAPL_CIK,
        endpoint="submissions",
        url="https://data.sec.gov/submissions/CIK0000320193.json",
        retrieved_at="2026-08-03T18:00:00Z",
        sha256=digest,
        bytes=len(content),
        object_path=object_path,
        http_etag=None,
        http_last_modified=None,
    )
    assert seed.read_current_submissions_receipt(tmp_path, receipt) == _submissions()
    target.write_bytes(seed.gzip.compress(b"{}", mtime=0))
    with pytest.raises(seed.AttestedHistorySeedError, match="identity mismatch"):
        seed.read_current_submissions_receipt(tmp_path, receipt)


def test_seed_enforces_exact_historical_and_archive_inventory_caps():
    seed = _seed_module()
    bounded = _submissions()
    bounded["filings"]["files"] = [
        {"name": f"CIK0000320193-submissions-{index:03d}.json"}
        for index in range(1, seed.MAX_OLDER_SUBMISSIONS_FILES + 1)
    ]
    assert len(seed.declared_older_submissions_names(bounded)) == 128
    bounded["filings"]["files"].append(
        {"name": "CIK0000320193-submissions-129.json"}
    )
    with pytest.raises(seed.AttestedHistorySeedError, match="exact file cap"):
        seed.declared_older_submissions_names(bounded)

    archive = {
        "directory": {
            "item": [
                {"name": f"member-{index:04d}.xml"}
                for index in range(seed.MAX_ARCHIVE_INVENTORY_MEMBERS)
            ]
        }
    }
    assert len(seed._archive_inventory_names(archive)) == 4_096
    archive["directory"]["item"].append({"name": "member-overflow.xml"})
    with pytest.raises(seed.AttestedHistorySeedError, match="exact member cap"):
        seed._archive_inventory_names(archive)


def test_selects_exactly_one_latest_aapl_10k_from_retained_submissions():
    seed = _seed_module()
    selected = seed.select_latest_aapl_10k(
        _submissions(),
        recorded_at="2026-08-03T18:00:00Z",
        as_of="2026-08-03T18:00:00Z",
    )
    assert selected["filing"]["accession"] == "0000320193-25-000079"
    assert selected["documents"][0]["document_name"] == "aapl-20250927.htm"


def test_packet_compiler_carries_complete_inventory_and_exact_pinned_sources():
    seed = _seed_module()
    packet = _packet(seed)
    parsed = seed.operator_spec_from_bytes(seed.canonical_json(packet).encode("utf-8"))
    assert parsed.packet.member_states["aapl-20250927_cal.xml"] == "not_requested"
    assert parsed.packet.recent_submissions.source_name == "recent"
    assert parsed.packet.older_submissions[0].source_name == "CIK0000320193-submissions-001.json"


def test_preflight_is_given_the_readonly_client_not_the_seed_writer(monkeypatch, tmp_path):
    seed = _seed_module()
    writer = LocalStore(tmp_path / "writer")
    readonly = LocalStore(tmp_path / "readonly")
    seen: list[object] = []

    def fake_preflight(*, spec, store, operator_verification_observed_at):
        del spec, operator_verification_observed_at
        seen.append(store)
        return {
            "status": "prepared",
            "publication": {"storage_write_attempts": 0},
        }

    monkeypatch.setattr(seed, "run_readonly_preflight", fake_preflight)
    receipt = seed.run_seed_preflight(
        packet_bytes=seed.canonical_json(_packet(seed)).encode("utf-8"),
        readonly_store=readonly,
        observed_at="2026-08-03T18:00:00Z",
    )
    assert receipt["status"] == "prepared"
    assert seen == [readonly]
    assert writer not in seen


def test_seed_behaviorally_preserves_latest_pointers_and_binds_review_bundle(monkeypatch, tmp_path):
    seed, calls, receipt, error, output = _exercise_full_seed(monkeypatch, tmp_path)
    assert error is None
    assert calls["sync"] == [False]
    assert calls["publish"] == [False]
    assert receipt["clocks"] == {
        "source_snapshot_at": "2026-08-03T18:00:06.600000Z",
        "operator_verification_observed_at": "2026-08-03T18:00:07.700000Z",
        "preflight_completed_at": "2026-08-03T18:00:08.800000Z",
    }
    assert receipt["dependency_lock"]["sha256"] == "d" * 64
    assert receipt["run_provenance"] == {"mode": "hermetic_local"}
    assert calls["conversion_clocks"] == ["2026-08-03T18:00:02.200000Z"]
    assert calls["packet_clocks"] == ["2026-08-03T18:00:02.200000Z"]
    bundle = json.loads(
        (output / seed.SEED_BUNDLE_RECEIPT_FILENAME).read_text(encoding="utf-8")
    )
    assert bundle["assembled_at"] == "2026-08-03T18:00:09.900000Z"
    assert set(bundle["files"]) == {
        seed.SEED_PACKET_FILENAME,
        "attested_history_preflight_receipt.json",
        seed.SEED_RECEIPT_FILENAME,
    }
    for filename, artifact in bundle["files"].items():
        content = (output / filename).read_bytes()
        assert artifact["filename"] == filename
        assert artifact["bytes"] == len(content)
        assert artifact["sha256"] == seed.sha256(content).hexdigest()
    assert all("retrieved_at" not in kwargs for kwargs in calls["retrieval_kwargs"])


def test_independent_seed_bundle_verifier_recomputes_and_cross_binds_all_four_artifacts(tmp_path):
    _seed, verifier, output, expected = _production_review_bundle(tmp_path)
    result = verifier.verify_seed_bundle(output, expected=expected)
    assert result["status"] == "verified"
    assert result["run_id"] == expected.run_id
    assert result["issuer"] == {"ticker": "AAPL", "cik": "0000320193"}
    assert result["zero_write_preflight"] is True
    assert result["all_nonclaims_exact"] is True
    assert set(result["artifacts"]) == verifier.EXPECTED_FILES
    for filename, artifact in result["artifacts"].items():
        content = (output / filename).read_bytes()
        assert artifact == {
            "bytes": len(content),
            "sha256": sha256(content).hexdigest(),
        }


def test_independent_seed_bundle_verifier_requires_the_exact_successful_actions_run(tmp_path):
    _seed, verifier, _output, expected = _production_review_bundle(tmp_path)
    metadata = {
        "id": expected.run_id,
        "status": "completed",
        "conclusion": "success",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": expected.sha,
        "run_attempt": expected.run_attempt,
        "path": ".github/workflows/attested-history-aapl-seed.yml",
        "head_repository": {"full_name": expected.repository},
    }
    verifier._verified_github_run_identity(
        metadata,
        expected_run_id=expected.run_id,
        expected_sha=expected.sha,
        expected_run_attempt=expected.run_attempt,
    )
    metadata["conclusion"] = "failure"
    with pytest.raises(verifier.SeedBundleVerificationError, match="conclusion"):
        verifier._verified_github_run_identity(
            metadata,
            expected_run_id=expected.run_id,
            expected_sha=expected.sha,
            expected_run_attempt=expected.run_attempt,
        )


def test_independent_seed_bundle_verifier_rejects_byte_tampering_and_file_smuggling(tmp_path):
    _seed, verifier, output, expected = _production_review_bundle(tmp_path)
    packet = output / verifier.PACKET_FILENAME
    packet.write_bytes(packet.read_bytes() + b" ")
    with pytest.raises(verifier.SeedBundleVerificationError, match="canonical|sha256"):
        verifier.verify_seed_bundle(output, expected=expected)

    _seed, verifier, output, expected = _production_review_bundle(tmp_path / "second")
    (output / "unreviewed.txt").write_text("smuggled", encoding="utf-8")
    with pytest.raises(verifier.SeedBundleVerificationError, match="exactly the four"):
        verifier.verify_seed_bundle(output, expected=expected)


def test_independent_seed_bundle_verifier_rejects_rehashed_write_and_provenance_tampering(tmp_path):
    seed, verifier, output, expected = _production_review_bundle(tmp_path)
    preflight_path = output / verifier.PREFLIGHT_FILENAME
    seed_path = output / verifier.SEED_FILENAME
    bundle_path = output / verifier.BUNDLE_FILENAME

    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["publication"]["storage_write_attempts"] = 1
    preflight_path.write_bytes(_preflight_bytes(preflight))
    seed_receipt = json.loads(seed_path.read_text(encoding="utf-8"))
    seed_receipt["review_artifacts"]["preflight_receipt"] = _review_artifact(preflight_path)
    seed_path.write_bytes(seed.canonical_json(seed_receipt).encode("utf-8"))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["files"][verifier.PREFLIGHT_FILENAME] = _review_artifact(preflight_path)
    bundle["files"][verifier.SEED_FILENAME] = _review_artifact(seed_path)
    bundle_path.write_bytes(seed.canonical_json(bundle).encode("utf-8"))
    with pytest.raises(verifier.SeedBundleVerificationError, match="zero-write"):
        verifier.verify_seed_bundle(output, expected=expected)

    seed, verifier, output, expected = _production_review_bundle(tmp_path / "second")
    seed_path = output / verifier.SEED_FILENAME
    bundle_path = output / verifier.BUNDLE_FILENAME
    seed_receipt = json.loads(seed_path.read_text(encoding="utf-8"))
    seed_receipt["run_provenance"]["run_id"] += 1
    seed_path.write_bytes(seed.canonical_json(seed_receipt).encode("utf-8"))
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["files"][verifier.SEED_FILENAME] = _review_artifact(seed_path)
    bundle_path.write_bytes(seed.canonical_json(bundle).encode("utf-8"))
    with pytest.raises(verifier.SeedBundleVerificationError, match="reviewed GitHub run"):
        verifier.verify_seed_bundle(output, expected=expected)


@pytest.mark.parametrize("fail_stage", ["after_source", "after_base"])
def test_seed_preserves_latest_pointers_after_partial_immutable_writes(
    monkeypatch, tmp_path, fail_stage
):
    _seed, calls, receipt, error, output = _exercise_full_seed(
        monkeypatch, tmp_path, fail_stage=fail_stage
    )
    assert receipt is None
    assert isinstance(error, RuntimeError)
    assert fail_stage.replace("_", " ") in str(error)
    assert calls["sync"] == [False]
    assert calls["publish"] == ([] if fail_stage == "after_source" else [False])
    assert not (output / "attested_history_seed_receipt.json").exists()


def test_writer_requires_dedicated_seed_credentials_and_never_uses_shared_fallback(monkeypatch, tmp_path):
    seed = _seed_module()
    for name in (
        "FF_ATTESTED_R2_SEED_ENDPOINT",
        "FF_ATTESTED_R2_SEED_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_SEED_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("R2_RESEARCH_BUCKET", "shared-must-not-be-used")
    monkeypatch.setenv("FF_ATTESTED_R2_READONLY_BUCKET", "read-only-must-not-be-used")
    with pytest.raises(seed.AttestedHistorySeedError, match="dedicated"):
        seed.build_seed_store()
    assert isinstance(seed.build_seed_store(local_dir=tmp_path / "private"), LocalStore)


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        (
            "FF_ATTESTED_R2_SEED_ENDPOINT",
            "0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
            "R2 endpoint is invalid",
        ),
        (
            "FF_ATTESTED_R2_SEED_ACCESS_KEY_ID",
            "not-an-access-key",
            "R2 parent access key ID is invalid",
        ),
        (
            "FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY",
            "x" * 513,
            "R2 parent secret access key is invalid",
        ),
        ("FF_ATTESTED_R2_SEED_BUCKET", "Not_A_Bucket", "R2 bucket is invalid"),
    ],
)
def test_writer_reports_the_rejected_credential_field_without_its_value(
    monkeypatch, name, value, reason
):
    seed = _seed_module()
    _production_environment(monkeypatch, seed)
    monkeypatch.setenv(name, value)

    with pytest.raises(seed.AttestedHistorySeedError, match=reason) as caught:
        seed.build_seed_store()

    assert value not in str(caught.value)


def test_writer_collapses_an_unreviewed_credential_error_message(monkeypatch):
    seed = _seed_module()
    _production_environment(monkeypatch, seed)
    private_detail = "private-endpoint/private-bucket/private-key"

    def reject(**_kwargs):
        raise seed.R2TemporaryCredentialError(private_detail)

    monkeypatch.setattr(seed, "mint_r2_temporary_credentials", reject)

    with pytest.raises(
        seed.AttestedHistorySeedError, match="R2 parent credential is invalid"
    ) as caught:
        seed.build_seed_store()

    assert private_detail not in str(caught.value)


def _production_environment(monkeypatch, seed):
    endpoint = "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
    values = {
        "FF_ATTESTED_R2_SEED_ENDPOINT": endpoint,
        "FF_ATTESTED_R2_SEED_ACCESS_KEY_ID": "A" * 32,
        "FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY": "writer-parent-secret",
        "FF_ATTESTED_R2_SEED_BUCKET": "attested-history",
        "FF_ATTESTED_R2_READONLY_ENDPOINT": endpoint,
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID": "B" * 32,
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY": "reader-parent-secret",
        "FF_ATTESTED_R2_READONLY_BUCKET": "attested-history",
        "FF_ATTESTED_GITHUB_REPOSITORY": seed.EXPECTED_GITHUB_REPOSITORY,
        "FF_ATTESTED_GITHUB_SHA": "c" * 40,
        "FF_ATTESTED_GITHUB_REF": seed.EXPECTED_GITHUB_REF,
        "FF_ATTESTED_GITHUB_RUN_ID": "12345",
        "FF_ATTESTED_GITHUB_RUN_ATTEMPT": "2",
        "FF_ATTESTED_GITHUB_ENVIRONMENT": seed.EXPECTED_GITHUB_ENVIRONMENT,
        "FF_ATTESTED_GITHUB_WORKFLOW": seed.EXPECTED_GITHUB_WORKFLOW,
        "FF_ATTESTED_DEPENDENCY_LOCK_SHA256": "d" * 64,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_production_boundary_rejects_equal_parent_keys_and_store_mismatch_before_io(
    monkeypatch
):
    seed = _seed_module()
    values = _production_environment(monkeypatch, seed)
    seed.validate_production_environment_boundary()
    expected = seed.production_run_provenance()
    assert expected == {
        "repository": seed.EXPECTED_GITHUB_REPOSITORY,
        "sha": "c" * 40,
        "ref": "refs/heads/main",
        "run_id": 12345,
        "run_attempt": 2,
        "environment": "attested-history-seed",
        "workflow": "attested-history-aapl-seed",
    }
    assert seed.production_dependency_lock_sha256() == "d" * 64
    monkeypatch.setenv(
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        values["FF_ATTESTED_R2_SEED_ACCESS_KEY_ID"],
    )
    with pytest.raises(seed.AttestedHistorySeedError, match="distinct"):
        seed.validate_production_environment_boundary()
    monkeypatch.setenv("FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID", "B" * 32)
    monkeypatch.setenv("FF_ATTESTED_R2_READONLY_BUCKET", "different-bucket")
    with pytest.raises(seed.AttestedHistorySeedError, match="same endpoint and bucket"):
        seed.validate_production_environment_boundary()


def test_run_provenance_rejects_untrusted_ref_repository_and_extra_receipt_fields(monkeypatch):
    seed = _seed_module()
    _production_environment(monkeypatch, seed)
    monkeypatch.setenv("FF_ATTESTED_GITHUB_REF", "refs/heads/feature")
    with pytest.raises(seed.AttestedHistorySeedError, match="provenance"):
        seed.production_run_provenance()
    monkeypatch.setenv("FF_ATTESTED_GITHUB_REF", seed.EXPECTED_GITHUB_REF)
    monkeypatch.setenv("FF_ATTESTED_GITHUB_REPOSITORY", "attacker/fork")
    with pytest.raises(seed.AttestedHistorySeedError, match="provenance"):
        seed.production_run_provenance()


def test_main_rejects_equal_parent_keys_before_lock_or_store_io(monkeypatch, tmp_path):
    seed = _seed_module()
    values = _production_environment(monkeypatch, seed)
    monkeypatch.setenv(
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        values["FF_ATTESTED_R2_SEED_ACCESS_KEY_ID"],
    )
    monkeypatch.setattr(
        seed,
        "dependency_lock_sha256",
        lambda: pytest.fail("dependency lock read happened before credential boundary"),
    )
    monkeypatch.setattr(
        seed,
        "build_seed_store",
        lambda **_kwargs: pytest.fail("store initialization happened after rejected boundary"),
    )
    assert seed.main(
        [
            "--enable-aapl-seed",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "output"),
            "--sec-user-agent",
            "MastermindX data@mastermind-x.com",
        ]
    ) == 1
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "output").exists()


def test_seed_stage_markers_reach_every_phase_of_the_graph(monkeypatch, tmp_path):
    """A stage marker that never fires localises nothing.

    ``on_stage`` is diagnostics-only, so nothing else in the suite would notice
    if the deep markers went dead or drifted out of graph order. This pins that
    each one is actually reached on the success path — including the acquire
    and preflight phases the operator most needs distinguished.
    """
    _seed, calls, receipt, error, _output = _exercise_full_seed(monkeypatch, tmp_path)
    assert error is None and receipt is not None
    assert calls["stages"] == [
        "storage-control-probe",
        "acquire-submissions",
        "acquire-filing",
        "acquire-companyfacts",
        "source-snapshot",
        "base-candidate",
        "preflight",
        "review-artifacts",
    ]


@pytest.mark.parametrize(
    ("fail_stage", "expected_last"),
    [("after_source", "source-snapshot"), ("after_base", "base-candidate")],
)
def test_seed_stage_markers_stop_at_the_phase_that_failed(
    monkeypatch, tmp_path, fail_stage, expected_last
):
    """The last marker names the phase to look at — that is the whole point."""
    _seed, calls, receipt, error, _output = _exercise_full_seed(
        monkeypatch, tmp_path, fail_stage=fail_stage
    )
    assert receipt is None and error is not None
    assert calls["stages"][-1] == expected_last
    assert "preflight" not in calls["stages"]
    assert "review-artifacts" not in calls["stages"]


def _seed_argv(tmp_path) -> list[str]:
    return [
        "--enable-aapl-seed",
        "--work-dir",
        str(tmp_path / "work"),
        "--output-dir",
        str(tmp_path / "output"),
        "--sec-user-agent",
        "MastermindX data@mastermind-x.com",
    ]


def _sole_annotation(captured_stdout: str) -> str:
    """The one workflow command in the output — proving it can start a line.

    ``capsys``, never ``caplog``: an annotation routed through a logger is
    prefixed by the formatter and GitHub silently drops it, so the defect this
    pins is a line that does not START with ``::``.
    """
    lines = [line for line in captured_stdout.splitlines() if line.startswith("::")]
    assert len(lines) == 1, f"expected exactly one annotation, got {lines!r}"
    return lines[0]


def test_main_surfaces_the_value_free_boundary_message_and_its_stage(
    monkeypatch, tmp_path, capsys
):
    """The 2026-08-09 production failure must now describe itself.

    The seed's ``::error`` is the ONLY operator-facing artifact a failing run
    produces — RUNNER_TEMP is wiped between jobs and no artifact is emitted
    before full success. It used to say "inspect the protected runner
    diagnostics", which have never existed, while discarding an already-safe
    sentence. Here the four absent GitHub secrets are reproduced by clearing the
    six env vars they feed (R2_ATTESTED_HISTORY_{ENDPOINT,BUCKET} each feed a
    seed AND a read-only name), so ``validate_production_environment_boundary``
    fails on its very first check exactly as it did in CI.
    """
    seed = _seed_module()
    _production_environment(monkeypatch, seed)
    for name in (
        "FF_ATTESTED_R2_SEED_ENDPOINT",
        "FF_ATTESTED_R2_SEED_BUCKET",
        "FF_ATTESTED_R2_READONLY_ENDPOINT",
        "FF_ATTESTED_R2_READONLY_BUCKET",
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        seed,
        "build_seed_store",
        lambda **_kwargs: pytest.fail("store initialization happened after rejected boundary"),
    )

    assert seed.main(_seed_argv(tmp_path)) == 1

    out = capsys.readouterr().out
    line = _sole_annotation(out)
    assert line.startswith("::")
    assert line.startswith("::error title=fundamental_forensics_attested_history_seed::")
    assert "dedicated attested-history parent credentials are unavailable" in line
    assert "environment-boundary" in line
    assert "protected runner diagnostics" not in out
    assert "Traceback" not in out
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "output").exists()


def test_main_suppresses_every_detail_of_a_non_seed_exception(monkeypatch, tmp_path, capsys):
    """The half of the fix that keeps it from becoming a leak.

    A store/credential path can raise a botocore ``ClientError`` (or any other
    type) whose message carries the R2 endpoint, the bucket, or a local source
    path. Only the CLASS name and the static stage may cross the boundary.
    ``RuntimeError`` is deliberate: it is the PARENT of
    ``AttestedHistorySeedError``, so a handler matching too loosely would print
    this message verbatim.
    """
    seed = _seed_module()
    _production_environment(monkeypatch, seed)
    endpoint_host = "deadbeefdeadbeefdeadbeefdeadbeef.r2.cloudflarestorage.com"
    bucket = "private-bucket"
    payload = f"https://{endpoint_host}/{bucket}"

    def _explode(**_kwargs):
        raise RuntimeError(payload)

    monkeypatch.setattr(seed, "build_seed_store", _explode)

    assert seed.main(_seed_argv(tmp_path)) == 1

    out = capsys.readouterr().out
    line = _sole_annotation(out)
    assert line.startswith("::")
    assert line.startswith("::error title=fundamental_forensics_attested_history_seed::")
    assert "RuntimeError" in line
    assert "writer-store" in line
    assert endpoint_host not in out
    assert bucket not in out
    assert payload not in out
    assert "Traceback" not in out
    # No fragment of the secret-shaped message survives anywhere in the output.
    leaked = sorted(
        {
            payload[start:stop]
            for start in range(len(payload))
            for stop in range(start + 8, len(payload) + 1)
            if payload[start:stop] in out
        }
    )
    assert leaked == [], f"annotation leaked message fragments: {leaked!r}"


def test_provenance_clocks_preserve_subseconds_and_fail_on_backdating():
    seed = _seed_module()
    assert seed._clock_not_before(
        "2026-08-03T18:00:06.600000Z",
        "2026-08-03T18:00:06.500000Z",
        field="source_snapshot_at",
    ) == "2026-08-03T18:00:06.600000Z"
    with pytest.raises(seed.AttestedHistorySeedError, match="predates"):
        seed._clock_not_before(
            "2026-08-03T18:00:06.499999Z",
            "2026-08-03T18:00:06.500000Z",
            field="source_snapshot_at",
        )


def test_dependency_lock_is_exact_hashed_and_matches_recorded_digest():
    seed = _seed_module()
    lock = LOCK_PATH.read_text(encoding="utf-8")
    requirement_lines = [line for line in lock.splitlines() if line and not line.startswith(("#", " "))]
    assert requirement_lines
    assert all("==" in line and line.endswith("\\") for line in requirement_lines)
    assert lock.count("--hash=sha256:") == len(requirement_lines)
    assert seed.dependency_lock_sha256() == seed.sha256(LOCK_PATH.read_bytes()).hexdigest()


def test_storage_control_probe_proves_cross_role_cas_without_discovery_or_delete(monkeypatch, tmp_path):
    seed = _seed_module()
    # These are separate clients over the same backing store, matching the
    # writer/GET-only R2 role split.  Any accidental legacy or discovery call
    # turns this contract into an immediate failure.
    writer = LocalStore(tmp_path / "shared")
    readonly = LocalStore(tmp_path / "shared")

    def forbidden(*_args, **_kwargs):
        pytest.fail("storage control probe used a forbidden store primitive")

    for store in (writer, readonly):
        for method in ("get_bytes", "put_bytes", "list_prefix", "exists", "upload_time", "delete"):
            monkeypatch.setattr(store, method, forbidden, raising=False)

    receipt = seed.run_storage_control_probe(
        writer_store=writer,
        readonly_store=readonly,
        token="a" * 32,
    )

    assert receipt == {
        "key": f"{seed.STORAGE_CONTROL_PREFIX}/{'a' * 32}",
        "final_sha256": "81175a607c7fc0cb3e2d17843e6c7160f6180686128d450dda0bb208ffc8eb4b",
        "outcomes": {
            "absent_before_create": True,
            "absent_create_succeeded": True,
            "conflicting_absent_create_rejected": True,
            "exact_version_advance_succeeded": True,
            "stale_version_advance_rejected": True,
            "readonly_final_readback_verified": True,
        },
    }


def test_storage_control_probe_rejects_a_backend_that_accepts_conflicting_absent_create(monkeypatch, tmp_path):
    seed = _seed_module()
    writer = LocalStore(tmp_path / "shared")
    readonly = LocalStore(tmp_path / "shared")
    original_put = writer.put_bytes_strict_conditional
    absent_creates = 0

    def broken_put(key, data, *, expected_version, content_type="application/octet-stream"):
        nonlocal absent_creates
        if expected_version is None:
            absent_creates += 1
            if absent_creates == 2:
                return True
        return original_put(
            key,
            data,
            expected_version=expected_version,
            content_type=content_type,
        )

    monkeypatch.setattr(writer, "put_bytes_strict_conditional", broken_put)
    with pytest.raises(seed.AttestedHistorySeedError, match="conflicting create was accepted"):
        seed.run_storage_control_probe(
            writer_store=writer,
            readonly_store=readonly,
            token="b" * 32,
        )


def test_storage_control_probe_requires_a_separate_reader_against_the_same_final_bytes(tmp_path):
    seed = _seed_module()
    writer = LocalStore(tmp_path / "writer")
    readonly = LocalStore(tmp_path / "different-reader-bucket")

    with pytest.raises(seed.AttestedHistorySeedError, match="read-only final readback"):
        seed.run_storage_control_probe(
            writer_store=writer,
            readonly_store=readonly,
            token="c" * 32,
        )
    with pytest.raises(seed.AttestedHistorySeedError, match="separately supplied"):
        seed.run_storage_control_probe(
            writer_store=writer,
            readonly_store=writer,
            token="d" * 32,
        )


def test_storage_control_failure_stops_before_sec_acquisition(monkeypatch, tmp_path):
    seed = _seed_module()
    writer = LocalStore(tmp_path / "writer")
    readonly = LocalStore(tmp_path / "different-reader-bucket")

    def sec_must_not_start(*_args, **_kwargs):
        pytest.fail("SEC acquisition began after storage control failure")

    monkeypatch.setattr(seed, "SecForensicsCollector", sec_must_not_start)
    work = tmp_path / "work"
    output = tmp_path / "output"
    with pytest.raises(seed.AttestedHistorySeedError, match="read-only final readback"):
        seed.run_aapl_seed(
            work_dir=work,
            output_dir=output,
            user_agent="MastermindX data@mastermind-x.com",
            writer_store=writer,
            readonly_store=readonly,
        )
    assert not (work / "raw").exists()
    assert not (work / "archive").exists()


def test_manual_seed_workflow_has_no_schedule_and_keeps_writer_and_reader_credentials_separate():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    job = parsed["jobs"]["seed"]
    steps = job["steps"]
    assert "\n  schedule:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "enable_aapl_seed" in workflow
    assert "environment: attested-history-seed" in workflow
    assert "required-reviewer protection" in workflow
    assert "FF_ATTESTED_R2_SEED_ENDPOINT" in workflow
    assert "FF_ATTESTED_R2_SEED_ENDPOINT: ${{ secrets.R2_ATTESTED_HISTORY_ENDPOINT }}" in workflow
    assert "R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID" in workflow
    assert "R2_ATTESTED_HISTORY_SEED_SECRET_ACCESS_KEY" in workflow
    assert "FF_ATTESTED_R2_READONLY_ENDPOINT" in workflow
    assert "R2_ATTESTED_HISTORY_READONLY_ACCESS_KEY_ID" in workflow
    assert "R2_ATTESTED_HISTORY_READONLY_SECRET_ACCESS_KEY" in workflow
    assert "FF_ATTESTED_R2_SEED_BUCKET: ${{ secrets.R2_ATTESTED_HISTORY_BUCKET }}" in workflow
    assert "FF_ATTESTED_R2_READONLY_BUCKET: ${{ secrets.R2_ATTESTED_HISTORY_BUCKET }}" in workflow
    assert "R2_RESEARCH_" not in workflow
    assert "fundamental_forensics/" in workflow
    assert "Distinct parents do not" in workflow
    assert "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" in workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "$HOME/.cache/mm-venv" not in workflow
    assert "requirements.txt" not in workflow
    assert "--require-hashes" in workflow
    assert "attested-history-macos-arm64-py312.lock" in workflow
    assert 'git show "$GITHUB_SHA:requirements/attested-history-macos-arm64-py312.lock"' in workflow
    assert "persist-credentials: false" in workflow
    assert "verify exact reviewed execution tree" in workflow
    assert 'git diff --quiet "$GITHUB_SHA" -- .' in workflow
    assert "git ls-files --others --ignored --exclude-standard -- ." in workflow
    assert "git archive --format=tar" in workflow
    assert '"$GITHUB_SHA" -- "${execution_paths[@]}"' in workflow
    assert "engine/fundamental_forensics" in workflow
    assert "config/fundamental_forensics" in workflow
    assert 'tar -xf "$SOURCE_ARCHIVE" -C "$EXEC_ROOT"' in workflow
    assert 'cd "$EXEC_ROOT"' in workflow
    assert "${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" in workflow
    assert "if: always()" not in workflow
    assert "if-no-files-found: error" in workflow
    assert "review-only" in workflow
    assert "private seed" not in workflow
    assert "env" not in job
    secret_steps = [step for step in steps if "env" in step]
    assert len(secret_steps) == 1
    assert secret_steps[0]["name"] == "acquire bounded AAPL seed and run zero-write preflight"
    assert set(secret_steps[0]["env"]) == {
        "FF_ATTESTED_R2_SEED_ENDPOINT",
        "FF_ATTESTED_R2_SEED_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_SEED_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_SEED_BUCKET",
        "FF_ATTESTED_R2_READONLY_ENDPOINT",
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_READONLY_BUCKET",
        "FF_ATTESTED_GITHUB_REPOSITORY",
        "FF_ATTESTED_GITHUB_SHA",
        "FF_ATTESTED_GITHUB_REF",
        "FF_ATTESTED_GITHUB_RUN_ID",
        "FF_ATTESTED_GITHUB_RUN_ATTEMPT",
        "FF_ATTESTED_GITHUB_ENVIRONMENT",
        "FF_ATTESTED_GITHUB_WORKFLOW",
        "FF_ATTESTED_DEPENDENCY_LOCK_SHA256",
        "SEC_USER_AGENT",
    }
    assert (seed_steps_run := secret_steps[0]["run"])
    assert "test ! -e \"$WORK\"" in seed_steps_run
    assert "test ! -e \"$OUTPUT\"" in seed_steps_run
