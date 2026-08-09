from __future__ import annotations

import json
from pathlib import Path

import pytest

from collectors.edgar_forensics import (
    SecForensicsCollector,
    SecResponseTooLarge,
    endpoint_url,
    persist_response,
)
from collectors import fundamental_forensics_acquisition as acquisition
from collectors.fundamental_forensics_acquisition import (
    SEC_OBSERVATION_LOG_SCHEMA,
    AcquisitionError,
    acquire_bounded_filings,
    normalize_targets,
    observation_log_path,
    read_verified_submissions,
)
from collectors.sec_document_spine import (
    ArchiveResponseTooLarge,
    SecFilingArchiveCollector,
    persist_archive_document,
    read_filing_manifest,
)
from engine.fundamental_forensics.sec_document_spine import (
    build_filing_manifests,
    with_document_retrievals,
)


RECORDED_AT = "2026-08-02T00:05:00Z"
AS_OF = "2026-08-01T23:59:59Z"
# A second nightly run over the SAME as_of universe: new recorded_at, therefore
# new manifest ids, but the identical four already-retained primary documents.
SECOND_NIGHT = "2026-08-03T00:05:00Z"


def _submissions(cik: int) -> dict:
    return {
        "cik": str(cik),
        "name": "Fixture Holdings, Inc.",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000000001-26-000001",  # Q2 2026
                    "0000000001-26-000002",  # Q1 2026
                    "0000000001-25-000003",  # prior Q (excluded by cap)
                    "0000000001-26-000004",  # FY25 K
                    "0000000001-25-000005",  # FY24 K
                    "0000000001-24-000006",  # FY23 K (excluded by cap)
                ],
                "form": ["10-Q", "10-Q", "10-Q", "10-K", "10-K", "10-K"],
                "filingDate": [
                    "2026-08-01", "2026-05-01", "2025-11-01", "2026-02-20", "2025-02-20", "2024-02-20"
                ],
                "reportDate": [
                    "2026-06-30", "2026-03-31", "2025-09-30", "2025-12-31", "2024-12-31", "2023-12-31"
                ],
                "acceptanceDateTime": [
                    "2026-08-01T16:00:00.000Z", "2026-05-01T16:00:00.000Z", "2025-11-01T16:00:00.000Z",
                    "2026-02-20T16:00:00.000Z", "2025-02-20T16:00:00.000Z", "2024-02-20T16:00:00.000Z",
                ],
                "primaryDocument": ["q2.htm", "q1.htm", "q0.htm", "k25.htm", "k24.htm", "k23.htm"],
                "isXBRL": [1, 1, 1, 1, 1, 1],
                "isInlineXBRL": [1, 1, 1, 1, 1, 1],
            }
        },
    }


class _SubmissionsCollector:
    calls: list[tuple[str, str, int | None]] = []
    fail_ciks: set[str] = set()

    def __init__(self, raw_root: Path, **kwargs) -> None:
        self.raw_root = raw_root

    def fetch(self, cik, endpoint, *, retrieved_at, max_response_bytes=None):
        cik10 = f"{int(cik):010d}"
        self.calls.append((cik10, endpoint, max_response_bytes))
        if cik10 in self.fail_ciks:
            raise RuntimeError("fixture submissions outage")
        content = json.dumps(_submissions(int(cik))).encode("utf-8")
        return persist_response(
            self.raw_root,
            cik=cik,
            endpoint=endpoint,
            url=endpoint_url(cik, endpoint),
            content=content,
            retrieved_at=retrieved_at,
        )


class _ArchiveCollector:
    calls: list[tuple[str, int | None]] = []
    oversized: bool = False

    def __init__(self, archive_root: Path, **kwargs) -> None:
        self.archive_root = archive_root

    def fetch_primary_document(self, manifest, *, retrieved_at, max_document_bytes=None):
        accession = str(manifest["filing"]["accession"])
        self.calls.append((accession, max_document_bytes))
        primary = manifest["documents"][0]
        content = b"x" * ((max_document_bytes or 0) + 1) if self.oversized else accession.encode("utf-8")
        receipt = persist_archive_document(
            self.archive_root,
            primary,
            content,
            retrieved_at=retrieved_at,
        )
        return with_document_retrievals(manifest, {primary["document_id"]: receipt.to_dict()})


def _run(tmp_path: Path, *, targets=("FXT=1",), recorded_at: str = RECORDED_AT, **kwargs):
    _SubmissionsCollector.calls = []
    _SubmissionsCollector.fail_ciks = set()
    _ArchiveCollector.calls = []
    _ArchiveCollector.oversized = False
    return acquire_bounded_filings(
        targets=targets,
        raw_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        as_of=AS_OF,
        recorded_at=recorded_at,
        min_interval_seconds=0.1,
        submissions_collector_factory=_SubmissionsCollector,
        archive_collector_factory=_ArchiveCollector,
        **kwargs,
    )


def _stored_names(archive_root: Path, subdirectory: str, suffix: str) -> list[str]:
    return sorted(item.name for item in (archive_root / subdirectory).rglob(f"*{suffix}"))


def _primary(manifest) -> dict:
    return next(item for item in manifest["documents"] if item["role"] == "primary")


def test_acquisition_only_fetches_submissions_and_latest_two_10k_and_10q(tmp_path: Path):
    run = _run(tmp_path)

    assert run["status"] == "complete"
    assert [(cik, endpoint) for cik, endpoint, _ in _SubmissionsCollector.calls] == [
        ("0000000001", "submissions")
    ]
    assert [accession for accession, _ in _ArchiveCollector.calls] == [
        "0000000001-26-000004", "0000000001-25-000005",  # 10-K
        "0000000001-26-000001", "0000000001-26-000002",  # 10-Q
    ]
    ticker = run["ticker_receipts"][0]
    assert ticker["status"] == "complete"
    assert ticker["forms"][0]["selected_accessions"] == [
        "0000000001-26-000004", "0000000001-25-000005"
    ]
    assert ticker["forms"][1]["selected_accessions"] == [
        "0000000001-26-000001", "0000000001-26-000002"
    ]
    assert all((tmp_path / "archive" / key).is_file() for form in ticker["forms"] for key in form["manifest_keys"])
    # The 2026-08-08 mint adjudication (DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY)
    # R6 retired the per-ticker receipt file
    # `archive/runs/acquisition/<run_id>/<TICKER>.json`: it wrote one file per
    # ticker per night into the RESTORABLE tree while no production code ever
    # read it back. The same evidence is folded into the one per-run
    # observation object, which lives outside raw/archive entirely.
    assert run["schema"] == SEC_OBSERVATION_LOG_SCHEMA
    assert not (tmp_path / "archive" / "runs").exists()
    log_path = observation_log_path(tmp_path / "observations", run["run_id"])
    assert log_path.is_file()
    assert json.loads(log_path.read_text(encoding="utf-8")) == run

    # Nothing was stored for these accessions before this run.
    assert [
        (row["ticker"], row["accession"], row["outcome"]) for row in run["observations"]
    ] == [
        ("FXT", "0000000001-26-000004", "new_filing"),
        ("FXT", "0000000001-25-000005", "new_filing"),
        ("FXT", "0000000001-26-000001", "new_filing"),
        ("FXT", "0000000001-26-000002", "new_filing"),
    ]
    assert all(row["observed_at"] == RECORDED_AT.replace("Z", ".000000Z") for row in run["observations"])
    assert all(
        row["content_key"].startswith("ffsec_content_")
        and row["manifest_id"].startswith("ffsec_manifest_")
        and (tmp_path / "archive" / row["manifest_storage_key"]).is_file()
        for row in run["observations"]
    )


def test_acquisition_continues_after_one_ticker_submission_failure_with_receipt(tmp_path: Path):
    _SubmissionsCollector.fail_ciks = {"0000000002"}
    # `_run` resets the fixture, so call the public function explicitly here.
    _SubmissionsCollector.calls = []
    _ArchiveCollector.calls = []
    run = acquire_bounded_filings(
        targets=("FXT=1", "BAD=2"),
        raw_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        submissions_collector_factory=_SubmissionsCollector,
        archive_collector_factory=_ArchiveCollector,
    )

    by_ticker = {item["ticker"]: item for item in run["ticker_receipts"]}
    assert by_ticker["FXT"]["status"] == "complete"
    assert by_ticker["BAD"]["status"] == "failed"
    assert by_ticker["BAD"]["failures"][0]["stage"] == "submissions"
    # R6 (DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY, 2026-08-08) retired
    # `archive/runs/acquisition/<run_id>/BAD.json`. The failed ticker's durable
    # receipt is preserved inside the per-run observation object instead, so a
    # single failed SEC issuer still never erases the other targets' evidence.
    assert not (tmp_path / "archive" / "runs").exists()
    log_path = observation_log_path(tmp_path / "observations", run["run_id"])
    assert log_path.is_file()
    assert json.loads(log_path.read_text(encoding="utf-8"))["ticker_receipts"] == run["ticker_receipts"]
    # A ticker whose submissions fetch failed observed no accession at all, so
    # it contributes no observation rows — only the failure receipt above.
    assert {row["ticker"] for row in run["observations"]} == {"FXT"}
    assert run["status"] == "partial"


def test_second_run_with_a_later_clock_mints_no_manifest_and_appends_one_observation(tmp_path: Path):
    """The store must stop measuring our cron instead of the issuer.

    Two runs, same universe, different ``recorded_at``: every manifest id in
    the tree used to move because ``_manifest_id`` hashes ``clocks.recorded_at``
    and ``manifest_storage_key`` puts the id in the path. After
    DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY the manifest tree is byte-identical
    and the second night is recorded as four ``unchanged`` observations.
    """
    first = _run(tmp_path)
    manifests_root = tmp_path / "archive" / "manifests"
    observations_root = tmp_path / "observations"

    def manifest_tree() -> dict[str, bytes]:
        return {
            path.relative_to(manifests_root).as_posix(): path.read_bytes()
            for path in sorted(manifests_root.rglob("*.json"))
        }

    before = manifest_tree()
    assert before
    assert len(list(observations_root.rglob("*.json"))) == 1

    later_recorded_at = "2026-08-03T00:05:00Z"
    _ArchiveCollector.calls = []
    second = acquire_bounded_filings(
        targets=("FXT=1",),
        raw_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        as_of=AS_OF,
        recorded_at=later_recorded_at,
        min_interval_seconds=0.1,
        submissions_collector_factory=_SubmissionsCollector,
        archive_collector_factory=_ArchiveCollector,
    )

    # Same file set, same bytes: not one manifest object was minted.
    assert manifest_tree() == before
    assert second["run_id"] != first["run_id"]
    assert second["status"] == "complete"
    assert [row["outcome"] for row in second["observations"]] == ["unchanged"] * 4
    assert [row["manifest_id"] for row in second["observations"]] == [
        row["manifest_id"] for row in first["observations"]
    ]
    assert [row["content_key"] for row in second["observations"]] == [
        row["content_key"] for row in first["observations"]
    ]
    # Reuse carries the FIRST retention clock forward; only the observation moves.
    assert all(row["observed_at"] == "2026-08-03T00:05:00.000000Z" for row in second["observations"])
    assert len(list(observations_root.rglob("*.json"))) == 2

    # The nightly SEC re-fetch is never skipped: dedupe is a persist decision.
    assert [accession for accession, _ in _ArchiveCollector.calls] == [
        "0000000001-26-000004", "0000000001-25-000005",
        "0000000001-26-000001", "0000000001-26-000002",
    ]


def test_warm_archive_reuse_still_dedupes_and_still_observes(tmp_path: Path):
    """The reuse leg must obey R1 and still record P3 — it is the lane's path.

    Regression for a defect that survived a clean textual merge of this ruling
    with the warm-archive reuse work (#5022): the reuse branch kept minting a
    manifest per run and emitted NO observation row at all.  Because
    ``filing-forensics-sec.yml`` arms ``--reuse-local-archive``, that combination
    left the store re-minting nightly AND the observation log empty on the only
    path production runs — while every other test stayed green, since they all
    exercise the fetch leg.

    It also pins the honesty requirement of §8: a warm run proves the primary
    from local bytes, never from a fresh SEC response, so the row must say
    ``local_reuse`` and an ``unchanged`` outcome must not be readable as a
    byte-level re-download that did not happen.
    """
    first = _run(tmp_path)
    manifests_root = tmp_path / "archive" / "manifests"

    def manifest_tree() -> dict[str, bytes]:
        return {
            path.relative_to(manifests_root).as_posix(): path.read_bytes()
            for path in sorted(manifests_root.rglob("*.json"))
        }

    before = manifest_tree()
    assert before
    assert [row["primary_verification"] for row in first["observations"]] == [
        "network_refetch"
    ] * 4

    _ArchiveCollector.calls = []
    second = _run(tmp_path, recorded_at=SECOND_NIGHT, reuse_local_archive=True)

    # R1 on the reuse leg: not one manifest object minted.
    assert manifest_tree() == before
    # The warm leg asked SEC for no document bytes at all...
    assert _ArchiveCollector.calls == []
    # ...so the log must say so, rather than implying a fresh re-derivation.
    assert [row["outcome"] for row in second["observations"]] == ["unchanged"] * 4
    assert [row["primary_verification"] for row in second["observations"]] == [
        "local_reuse"
    ] * 4
    # Reuse is proved by identity, not by count: same manifests, new observation.
    assert [row["manifest_id"] for row in second["observations"]] == [
        row["manifest_id"] for row in first["observations"]
    ]
    assert len(list((tmp_path / "observations").rglob("*.json"))) == 2


def test_observation_log_refuses_to_overwrite_a_different_object_for_the_same_run(tmp_path: Path):
    run = _run(tmp_path)
    log_path = observation_log_path(tmp_path / "observations", run["run_id"])
    log_path.write_text('{"schema":"tampered"}', encoding="utf-8")
    with pytest.raises(AcquisitionError, match="already exists with different bytes"):
        _run(tmp_path)


def test_acquisition_caps_oversized_primary_before_manifest_is_marked_stored(tmp_path: Path):
    _SubmissionsCollector.calls = []
    _SubmissionsCollector.fail_ciks = set()
    _ArchiveCollector.calls = []
    _ArchiveCollector.oversized = True
    run = acquire_bounded_filings(
        targets=("FXT=1",),
        raw_root=tmp_path / "raw",
        archive_root=tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        max_submissions_bytes=4 * 1024,
        max_document_bytes=1024,
        max_ticker_bytes=8 * 1024,
        max_total_bytes=8 * 1024,
        submissions_collector_factory=_SubmissionsCollector,
        archive_collector_factory=_ArchiveCollector,
    )

    ticker = run["ticker_receipts"][0]
    assert ticker["status"] == "partial"
    assert all(form["stored_documents"] == 0 for form in ticker["forms"])
    assert all(form["manifest_keys"] for form in ticker["forms"])


def test_target_and_cached_submissions_contracts_are_strict(tmp_path: Path):
    with pytest.raises(AcquisitionError, match="multiple CIKs"):
        normalize_targets(("FXT=1", "FXT=2"))
    with pytest.raises(AcquisitionError, match="exceeds cap"):
        normalize_targets(tuple(f"T{i}=1{i}" for i in range(13)), max_tickers=12)

    _SubmissionsCollector.calls = []
    _SubmissionsCollector.fail_ciks = set()
    collector = _SubmissionsCollector(tmp_path / "raw")
    collector.fetch(1, "submissions", retrieved_at=RECORDED_AT)
    body, receipt = read_verified_submissions(tmp_path / "raw", 1)
    assert body["cik"] == "1"
    assert receipt["endpoint"] == "submissions"
    pointer = tmp_path / "raw" / "0000000001" / "submissions" / "latest.json"
    text = pointer.read_text(encoding="utf-8")
    pointer.write_text(text.replace('"object_path":"0000000001/submissions/', '"object_path":"../'), encoding="utf-8")
    with pytest.raises(AcquisitionError, match="not in the CIK namespace"):
        read_verified_submissions(tmp_path / "raw", 1)


class _NetworkResponse:
    def __init__(self, content: bytes, *, content_length: str) -> None:
        self.status_code = 200
        self.content = content
        self.headers = {"Content-Length": content_length}

    def raise_for_status(self) -> None:
        return None


class _NetworkSession:
    def __init__(self, response: _NetworkResponse) -> None:
        self.response = response
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        if args:
            self.response.url = args[0]
        return self.response


def test_network_collectors_refuse_declared_oversize_before_any_source_persistence(tmp_path: Path):
    submissions_session = _NetworkSession(_NetworkResponse(b'{"cik":"1"}', content_length="999"))
    submissions = SecForensicsCollector(
        tmp_path / "raw",
        user_agent="MastermindX research@example.com",
        session=submissions_session,
        max_response_bytes=16,
    )
    with pytest.raises(SecResponseTooLarge):
        submissions.fetch(1, "submissions", retrieved_at=RECORDED_AT)
    assert submissions_session.calls == 1
    assert not list((tmp_path / "raw").rglob("*.gz"))

    manifest = build_filing_manifests(_submissions(1), recorded_at=RECORDED_AT)[0]
    archive_session = _NetworkSession(_NetworkResponse(b"small", content_length="999"))
    archive = SecFilingArchiveCollector(
        tmp_path / "archive",
        user_agent="MastermindX research@example.com",
        session=archive_session,
        max_document_bytes=16,
    )
    with pytest.raises(ArchiveResponseTooLarge):
        archive.fetch_primary_document(manifest, retrieved_at=RECORDED_AT)
    assert archive_session.calls == 1
    assert not list((tmp_path / "archive").rglob("*.gz"))


# --- warm-archive reuse ---------------------------------------------------------
# The nightly lane re-downloaded a flat ~128MB of already-retained 10-K/10-Q
# primary documents (127.96MB -> 127.93MB across 08-05..08-08, zero new filings).
# Reuse is opt-in, and a hit must carry the ORIGINAL receipt: a cache hit that
# minted a fresh retrieved_at would be a retrieval no server ever served.


def test_reuse_flag_defaults_off_and_receipts_carry_zeroed_reuse_accounting(tmp_path: Path):
    run = _run(tmp_path)

    # Flag off: every accession is still fetched, in the same order as before.
    assert [accession for accession, _ in _ArchiveCollector.calls] == [
        "0000000001-26-000004", "0000000001-25-000005",
        "0000000001-26-000001", "0000000001-26-000002",
    ]
    assert run["reuse_local_archive"] is False
    assert run["bytes_reused"] == 0
    ticker = run["ticker_receipts"][0]
    assert ticker["bytes_reused"] == 0
    assert ticker["bytes_retained"] > 0
    assert [form["reused_documents"] for form in ticker["forms"]] == [0, 0]


def test_reuse_serves_warm_primary_documents_without_any_archive_fetch(tmp_path: Path):
    archive = tmp_path / "archive"
    first = _run(tmp_path)
    assert first["status"] == "complete"
    receipts_before = _stored_names(archive, "receipts", ".json")
    objects_before = _stored_names(archive, "objects", ".gz")
    assert receipts_before and objects_before

    second = _run(tmp_path, recorded_at=SECOND_NIGHT, reuse_local_archive=True)

    assert _ArchiveCollector.calls == []
    assert second["status"] == "complete"
    assert second["reuse_local_archive"] is True
    # Submissions are ALWAYS fetched fresh; that is how a new filing is found.
    assert [(cik, endpoint) for cik, endpoint, _ in _SubmissionsCollector.calls] == [
        ("0000000001", "submissions")
    ]

    warm, cold = second["ticker_receipts"][0], first["ticker_receipts"][0]
    document_bytes = cold["bytes_retained"] - warm["bytes_retained"]
    assert document_bytes > 0
    # bytes_retained keeps meaning bytes pulled over the network THIS run, so the
    # documents leave it and are accounted in bytes_reused instead.
    assert warm["bytes_retained"] == int(warm["submissions"]["bytes"])
    assert warm["bytes_reused"] == document_bytes == second["bytes_reused"]
    assert cold["bytes_reused"] == 0
    assert [form["reused_documents"] for form in warm["forms"]] == [2, 2]
    assert [form["stored_documents"] for form in warm["forms"]] == [
        form["stored_documents"] for form in cold["forms"]
    ]

    # No object and no receipt is minted: the evidence is the same stored bytes.
    assert _stored_names(archive, "receipts", ".json") == receipts_before
    assert _stored_names(archive, "objects", ".gz") == objects_before

    # Last night's manifest, reused verbatim — updated for the mint adjudication
    # (DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY, R1/R2).  This originally asserted
    # tonight's 2026-08-03 clock, because the reuse leg minted a fresh manifest
    # per run.  Under R2 ``recorded_at`` means FIRST retention of that exact
    # content, so an unchanged filing keeps the 2026-08-02 clock and no second
    # object is written.  A tonight-stamped clock here would mean the nightly
    # re-mint is back on the very path the lane runs.
    manifest = read_filing_manifest(archive, warm["forms"][0]["manifest_keys"][0])
    assert manifest["clocks"]["recorded_at"] == "2026-08-02T00:05:00.000000Z"
    primary = _primary(manifest)
    assert primary["availability"] == "stored"
    assert primary["retrieval"]["retrieved_at"] == "2026-08-02T00:05:00.000000Z"
    prior = read_filing_manifest(archive, cold["forms"][0]["manifest_keys"][0])
    assert primary["retrieval"] == _primary(prior)["retrieval"]


def test_reuse_on_a_cold_archive_is_byte_identical_to_the_fetch_path(tmp_path: Path):
    off = _run(tmp_path / "off")
    off_calls = list(_ArchiveCollector.calls)

    on = _run(tmp_path / "on", reuse_local_archive=True)

    assert list(_ArchiveCollector.calls) == off_calls
    assert on["bytes_reused"] == 0
    # Apart from the disclosed flag itself, an armed-but-cold run is the run the
    # lane does today, receipt for receipt.
    assert on.pop("reuse_local_archive") is True
    assert off.pop("reuse_local_archive") is False
    assert on == off


def test_reuse_falls_back_to_fetch_for_a_corrupted_local_object(tmp_path: Path):
    archive = tmp_path / "archive"
    first = _run(tmp_path)
    annual = read_filing_manifest(archive, first["ticker_receipts"][0]["forms"][0]["manifest_keys"][0])
    (archive / _primary(annual)["storage_key"]).write_bytes(b"truncated")

    run = _run(tmp_path, recorded_at=SECOND_NIGHT, reuse_local_archive=True)

    # Only the unverifiable document goes back to SEC, and the fetch repairs it.
    assert [accession for accession, _ in _ArchiveCollector.calls] == ["0000000001-26-000004"]
    assert run["status"] == "complete"
    ticker = run["ticker_receipts"][0]
    assert [form["reused_documents"] for form in ticker["forms"]] == [1, 2]
    assert [form["stored_documents"] for form in ticker["forms"]] == [2, 2]


def test_reuse_persist_failure_is_recorded_and_keeps_the_hard_gate_closed(monkeypatch, tmp_path: Path):
    _run(tmp_path)
    # Retargeted from ``persist_filing_manifest`` to ``retain_filing_manifest``
    # by the mint adjudication (DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY, R1): the
    # reuse leg now goes through the idempotent retain helper, so patching the
    # old symbol would no-op and this guard would stop seeing the failure it
    # exists to catch.
    real = acquisition.retain_filing_manifest

    def flaky(cache_root, manifest):
        # Fail only the MATERIALIZED write; the declared-selection record still
        # lands exactly as it does on the fetch leg.
        if _primary(manifest)["availability"] == "stored":
            raise OSError("fixture materialized manifest persist failure")
        return real(cache_root, manifest)

    monkeypatch.setattr(acquisition, "retain_filing_manifest", flaky)
    run = _run(tmp_path, recorded_at=SECOND_NIGHT, reuse_local_archive=True)

    # A committed hit never silently falls back to the network: a persist-side
    # failure would kill the fetch leg identically, so the gate must see it.
    assert _ArchiveCollector.calls == []
    ticker = run["ticker_receipts"][0]
    assert ticker["status"] == "partial"
    assert run["status"] == "partial"  # --require-complete-acquisition refuses this
    assert [failure["stage"] for form in ticker["forms"] for failure in form["failures"]] == [
        "reuse_10-K", "reuse_10-K", "reuse_10-Q", "reuse_10-Q"
    ]
    assert [form["reused_documents"] for form in ticker["forms"]] == [0, 0]
    assert ticker["bytes_reused"] == 0
