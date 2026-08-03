"""Adversarial B4A tests for the dark Drugs@FDA evidence transaction."""
from __future__ import annotations

from base64 import b64decode
from copy import deepcopy
import fcntl
from hashlib import sha256
from io import BytesIO
import json
import multiprocessing
import os
from pathlib import Path
from queue import Empty
import sqlite3
import stat
from tempfile import TemporaryDirectory
import zipfile

import pytest

from collectors.biocatalyst.drugs_at_fda import (
    EXPECTED_HEADERS,
    DrugsAtFdaCollectionError,
    DrugsAtFdaCollector,
    DrugsAtFdaConfig,
    _APPDOCS_EMPTY_FIELD_EXCEPTION,
    _parse_tsv,
    _typed_sqlite_semantic_digests,
    build_release_receipt,
    SQLITE_SCHEMA_SPEC_SHA256,
    SQLITE_TABLE_NAMES,
    parse_drugs_at_fda_zip,
    stream_drugs_at_fda_zip_to_sqlite,
)
from engine.biocatalyst.regulatory import RegulatoryGraphError, build_regulatory_graph
from engine.sector_intelligence import (
    ContractValidationError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
    validate_drugs_at_fda_release_receipt,
    validate_drugs_at_fda_table_manifest,
)
from scripts.biocatalyst_regulatory_worker import RegulatoryWorkerConfigError, load_environment


FIXTURE = Path("data/biocatalyst/fixtures/drugs_at_fda/synthetic_release.json")
LANDING_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files"
ARCHIVE_URL = "https://www.fda.gov/media/89850/download?attachment="


def _fixture_tables() -> dict[str, list[list[str]]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["tables"]


def _table_payloads(*, mutate=None, payload_mutate=None) -> dict[str, bytes]:
    tables = _fixture_tables()
    if mutate is not None:
        mutate(tables)
    payloads: dict[str, bytes] = {}
    for name, header in EXPECTED_HEADERS.items():
        rows = tables[name]
        body = "\r\n".join(["\t".join(header), *["\t".join(row) for row in rows]]) + "\r\n"
        payload = body.encode("cp1252")
        payloads[name] = payload_mutate(name, payload) if payload_mutate is not None else payload
    return payloads


# ``writestr`` with a bare member name stamps the member with the current local
# time at DOS two-second granularity, so two builds of the identical tables that
# straddle a bucket boundary produce different archive bytes and different
# ``archive_sha256``.  Tests cross-check archives built seconds apart, so every
# member timestamp is pinned and the synthetic release is byte-reproducible.
_PINNED_ZIP_DATE_TIME = (2026, 7, 31, 12, 54, 46)
_WRITESTR_EXTERNAL_ATTR = 0o600 << 16


def _zip_members(
    entries: list[tuple[str, bytes]], *, compression: int = zipfile.ZIP_DEFLATED,
    comment: bytes = b"", symlink_name: str | None = None,
) -> bytes:
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "synthetic.zip"
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            archive.comment = comment
            for name, payload in entries:
                info = zipfile.ZipInfo(name, date_time=_PINNED_ZIP_DATE_TIME)
                info.compress_type = compression
                info.external_attr = (
                    (stat.S_IFLNK | 0o777) << 16 if name == symlink_name else _WRITESTR_EXTERNAL_ATTR
                )
                archive.writestr(info, payload)
        return path.read_bytes()


def _zip_bytes(
    *, mutate=None, payload_mutate=None, compression: int = zipfile.ZIP_DEFLATED,
    names: list[str] | None = None, comment: bytes = b"", symlink_name: str | None = None,
) -> bytes:
    payloads = _table_payloads(mutate=mutate, payload_mutate=payload_mutate)
    selected_names = names or list(EXPECTED_HEADERS)
    return _zip_members(
        [(name, payloads.get(name, b"synthetic\r\n")) for name in selected_names],
        compression=compression,
        comment=comment,
        symlink_name=symlink_name,
    )


def _patch_first_member(raw: bytes, *, flag_bits: int | None = None, crc32: int | None = None,
                        compression: int | None = None) -> bytes:
    """Patch matching local/central fields for an intentional malformed ZIP."""
    patched = bytearray(raw)
    local = patched.find(b"PK\x03\x04")
    central = patched.find(b"PK\x01\x02")
    assert local == 0 and central > local
    if flag_bits is not None:
        patched[local + 6:local + 8] = flag_bits.to_bytes(2, "little")
        patched[central + 8:central + 10] = flag_bits.to_bytes(2, "little")
    if crc32 is not None:
        patched[local + 14:local + 18] = crc32.to_bytes(4, "little")
        patched[central + 16:central + 20] = crc32.to_bytes(4, "little")
    if compression is not None:
        patched[local + 8:local + 10] = compression.to_bytes(2, "little")
        patched[central + 10:central + 12] = compression.to_bytes(2, "little")
    return bytes(patched)


class _Response:
    """A requests-shaped, single-read response which records collector closure."""

    def __init__(self, body: bytes, *, headers: dict[str, str] | None = None,
                 status_code: int = 200, chunks: list[bytes] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.content = body
        self._chunks = list(chunks) if chunks is not None else [body]
        self.closed = False

    def iter_content(self, *, chunk_size: int):
        del chunk_size
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


def _response(body: bytes, *, headers: dict[str, str] | None = None,
              status_code: int = 200, chunks: list[bytes] | None = None) -> _Response:
    return _Response(body, headers=headers, status_code=status_code, chunks=chunks)


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls: list[tuple[str, dict]] = []
        self.trust_env = True

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if not hasattr(response, "url"):
            response.url = url
        return response


class _MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def get_bytes(self, key: str):
        return self.objects.get(key)

    def put_if_absent(self, key: str, data: bytes, *, content_type: str = "application/octet-stream"):
        if key in self.objects:
            return False
        self.objects[key] = data
        return True


def _release(raw: bytes, parsed) -> dict:
    def receipt(kind: str, url: str, body: bytes) -> dict:
        return {
            "kind": kind, "source_uri": url, "final_url": url, "status_code": 200, "response_headers": {},
            "exact_response_sha256": sha256(body).hexdigest(), "byte_count": len(body),
            "raw_object_key": f"biocatalyst/raw/drugs_at_fda/{'archive' if kind == 'archive' else 'landing'}/{sha256(body).hexdigest()}{'.zip' if kind == 'archive' else '.html'}",
            "received_at": "2026-08-01T00:00:00Z",
        }
    landing = b"x"
    value = {
        "contract_id": "drugs_at_fda_release_receipt.v1", "schema_version": "1.0.0",
        "release_id": f"drugs_at_fda_release_{parsed.archive_sha256[:24]}", "source_id": "drugs_at_fda",
        "source_url": LANDING_URL, "archive_sha256": parsed.archive_sha256, "archive_byte_count": len(raw),
        "source_release_date": "2026-07-31", "source_release_time": None, "observed_at": "2026-08-01T00:00:00Z",
        "http_receipts": [receipt("landing_before", LANDING_URL, landing), receipt("archive", ARCHIVE_URL, raw), receipt("landing_after", LANDING_URL, landing)],
        "parser_version": "drugs_at_fda_zip_parser.v1", "license_class": "us_government_source_facts",
        "hash_scope": "canonical_payload_excluding_receipt_payload_sha256",
    }
    value["receipt_payload_sha256"] = canonical_json_sha256(value)
    return value


def _parsed_graph():
    raw = _zip_bytes()
    parsed = parse_drugs_at_fda_zip(raw, config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    return raw, parsed, build_regulatory_graph(release=_release(raw, parsed), table_manifests=parsed.table_manifests, tables=parsed.tables)


def _rehash(document: dict, hash_field: str) -> dict:
    document[hash_field] = canonical_json_sha256(
        {key: value for key, value in document.items() if key != hash_field}
    )
    return document


def _archive_headers(raw: bytes) -> dict[str, str]:
    return {
        "content-type": "application/zip",
        "content-length": str(len(raw)),
        "content-disposition": "attachment; filename=dafdata20260731.zip",
    }


def _landing_bytes() -> bytes:
    return f"<html>Data Last Updated: July 31st, 2026 {ARCHIVE_URL}</html>".encode()


def _publish_synthetic(
    tmp_path: Path, *, require_private_mirror: bool = False,
    private_store: _MemoryStore | None = None,
) -> tuple[DrugsAtFdaCollector, bytes, DrugsAtFdaPublicationResult]:
    raw = _zip_bytes()
    collector = DrugsAtFdaCollector(
        private_root=tmp_path / "private",
        state_root=tmp_path / "state",
        config=DrugsAtFdaConfig(
            user_agent="test@example.invalid",
            require_private_mirror=require_private_mirror,
        ),
        private_store=private_store,
    )
    result = collector.publish_responses(
        _response(_landing_bytes()), _response(raw, headers=_archive_headers(raw)), _response(_landing_bytes())
    )
    return collector, raw, result


def _receipt_bound_to_exact_bodies(raw: bytes) -> tuple[dict, tuple[bytes, bytes]]:
    receipt, archive, landings = build_release_receipt(
        landing_before=_response(_landing_bytes()),
        archive_response=_response(raw, headers=_archive_headers(raw)),
        landing_after=_response(_landing_bytes()),
        config=DrugsAtFdaConfig(user_agent="test@example.invalid"),
        observed_at="2026-08-01T00:00:00Z",
    )
    assert archive == raw
    return receipt, landings


def _publication_lock_worker(private_root: str, state_root: str, raw: bytes, result_queue) -> None:
    """Spawn-safe witness for the actual collector publication lock boundary."""
    try:
        collector = DrugsAtFdaCollector(
            private_root=Path(private_root),
            state_root=Path(state_root),
            config=DrugsAtFdaConfig(user_agent="test@example.invalid"),
        )
        original = collector._publish_responses_locked

        def entered_locked(*args, **kwargs):
            result_queue.put(("entered_locked", None))
            return original(*args, **kwargs)

        collector._publish_responses_locked = entered_locked
        result_queue.put(("ready", None))
        result = collector.publish_responses(
            _response(_landing_bytes()),
            _response(raw, headers=_archive_headers(raw)),
            _response(_landing_bytes()),
        )
        result_queue.put(("completed", result.release_id))
    except BaseException as exc:  # Process boundary: preserve an inspectable failure.
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def test_synthetic_archive_bytes_never_depend_on_the_wall_clock() -> None:
    """One synthetic release must hash the same however far apart it is built.

    A member stamped with ``time.localtime()`` is only stable inside a DOS
    two-second bucket, so archives built moments apart get different
    ``archive_sha256`` values and any test that binds a receipt from one build to
    rows from another fails on receipt validation at a wall-clock-dependent rate.
    Two back-to-back builds usually land in the same bucket, so equality alone
    cannot see that defect -- the pinned stamp is what this asserts.
    """
    raw = _zip_bytes()
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        stamps = {member.date_time for member in archive.infolist()}
    assert stamps == {_PINNED_ZIP_DATE_TIME}
    assert raw == _zip_bytes()
    assert _zip_bytes(symlink_name="TE.txt") == _zip_bytes(symlink_name="TE.txt")


def test_synthetic_release_preserves_all_12_tables_and_blank_te_value() -> None:
    _raw, parsed, graph = _parsed_graph()
    assert set(parsed.tables) == set(EXPECTED_HEADERS)
    assert len(parsed.table_manifests) == 12
    dossier = graph.dossiers[0]
    assert dossier["products"][0]["therapeutic_equivalence"] == [{"marketing_status_id": "1", "te_code_source_text": ""}]
    assert dossier["submissions"][0]["submission_type_source_text"] == "ORIG      "
    assert dossier["authority"]["decision_authority"] is False
    assert "ticker" not in dossier and "prophet" not in dossier


def test_rejects_zip_slip_duplicate_or_unknown_members_before_graph() -> None:
    raw = _zip_bytes()
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / "bad.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../Applications.txt", b"x")
            for name in list(EXPECTED_HEADERS)[1:]:
                archive.writestr(name, b"x")
        with pytest.raises(DrugsAtFdaCollectionError) as error:
            parse_drugs_at_fda_zip(path.read_bytes(), config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    assert error.value.code in {"MEMBER_COUNT_MISMATCH", "ZIP_MEMBER_SET_MISMATCH", "ZIP_SLIP"}
    assert raw  # Pins the clean control did not fail fixture construction.


def test_unpinned_extra_application_docs_field_fails_closed() -> None:
    def mutate(tables):
        tables["ApplicationDocs.txt"][0].insert(-1, "")
    with pytest.raises(DrugsAtFdaCollectionError) as error:
        parse_drugs_at_fda_zip(_zip_bytes(mutate=mutate), config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    assert error.value.code == "ROW_SHAPE_MISMATCH"


def test_zip_envelope_member_type_compression_and_crc_fail_closed_in_both_paths(tmp_path: Path) -> None:
    config = DrugsAtFdaConfig(user_agent="test@example.invalid")
    for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        parsed = parse_drugs_at_fda_zip(_zip_bytes(compression=compression), config=config)
        assert set(parsed.tables) == set(EXPECTED_HEADERS)

    raw = _zip_bytes()
    duplicate_names = [name for name in EXPECTED_HEADERS if name != "TE.txt"] + ["Applications.txt"]
    unknown_names = [name for name in EXPECTED_HEADERS if name != "TE.txt"] + ["Unexpected.txt"]
    with pytest.warns(UserWarning, match="Duplicate name"):
        duplicate_zip = _zip_bytes(names=duplicate_names)
    malformed = [
        ("ZIP_ENVELOPE_MISMATCH", b"prefix" + raw),
        ("ZIP_ENVELOPE_MISMATCH", raw + b"trailer"),
        ("ZIP_ENVELOPE_MISMATCH", _zip_bytes(comment=b"not-a-source-archive")),
        ("DUPLICATE_ZIP_MEMBER", duplicate_zip),
        ("ZIP_MEMBER_SET_MISMATCH", _zip_bytes(names=unknown_names)),
        ("UNSAFE_ZIP_MEMBER", _zip_bytes(symlink_name="TE.txt")),
        ("ENCRYPTED_ZIP_MEMBER", _patch_first_member(raw, flag_bits=0x1)),
        ("UNEXPECTED_ZIP_COMPRESSION", _patch_first_member(raw, compression=zipfile.ZIP_BZIP2)),
    ]
    for expected_code, candidate in malformed:
        with pytest.raises(DrugsAtFdaCollectionError) as error:
            parse_drugs_at_fda_zip(candidate, config=config)
        assert error.value.code == expected_code

    bad_crc = _patch_first_member(raw, crc32=0)
    for parser in (
        lambda payload: parse_drugs_at_fda_zip(payload, config=config),
        lambda payload: stream_drugs_at_fda_zip_to_sqlite(
            payload, sqlite_path=tmp_path / "bad-crc.sqlite", config=config
        ),
    ):
        with pytest.raises(DrugsAtFdaCollectionError) as error:
            parser(bad_crc)
        assert error.value.code == "ZIP_READ_FAILURE"


def test_text_shape_contract_and_full_parser_memory_fence_are_fail_closed(tmp_path: Path) -> None:
    def replace_application(transform):
        return _zip_bytes(
            payload_mutate=lambda name, payload: transform(payload) if name == "Applications.txt" else payload
        )

    malformed = [
        ("UNEXPECTED_NUL", replace_application(lambda payload: payload.replace(b"Synthetic Sponsor", b"Synthetic\x00Sponsor"))),
        ("UNEXPECTED_LINE_ENDING", replace_application(lambda payload: payload.replace(b"\r\n", b"\n"))),
        ("UNEXPECTED_LINE_ENDING", replace_application(lambda payload: payload.replace(b"\r\n", b"\r"))),
        ("UNEXPECTED_BOM", replace_application(lambda payload: b"\xef\xbb\xbf" + payload)),
        ("UNTERMINATED_TABLE", replace_application(lambda payload: payload[:-2])),
        ("INVALID_CP1252", replace_application(lambda payload: payload.replace(b"Synthetic Sponsor", b"Synthetic \x81Sponsor"))),
    ]
    config = DrugsAtFdaConfig(user_agent="test@example.invalid")
    for expected_code, candidate in malformed:
        with pytest.raises(DrugsAtFdaCollectionError) as error:
            parse_drugs_at_fda_zip(candidate, config=config)
        assert error.value.code == expected_code

    raw = _zip_bytes()
    fenced = DrugsAtFdaConfig(user_agent="test@example.invalid", max_in_memory_parse_uncompressed_bytes=1)
    with pytest.raises(DrugsAtFdaCollectionError) as error:
        parse_drugs_at_fda_zip(raw, config=fenced)
    assert error.value.code == "FULL_RELEASE_REQUIRES_SQLITE_STREAM"
    streamed = stream_drugs_at_fda_zip_to_sqlite(raw, sqlite_path=tmp_path / "stream.sqlite", config=fenced)
    assert streamed.table_row_counts["Applications.txt"] == 1


def test_pinned_live_application_docs_raw_line_witness_is_the_only_normalized_shape() -> None:
    # This exact source row is the reviewed 2026-07-31 archive exception.  It
    # deliberately has a ninth, empty pre-date field; source bytes/digest and
    # the physical line number are all part of the narrow acceptance policy.
    raw_line = b64decode(
        "ODQ2MzAJMgkyMDY2MjcJU1VQUEwgICAgIAkxNwkwCWh0dHBzOi8vd3d3LmFjY2Vzc2RhdGEuZmRhLmdvdi9kcnVnc2F0ZmRhX2RvY3MvbGFiZWwvMjAyNS8yMDY2MjdPcmlnMXMwMTdsYmwucGRmCQkyMDI2LTAxLTA2IDAwOjAwOjAwDQo="
    )
    assert sha256(raw_line).hexdigest() == _APPDOCS_EMPTY_FIELD_EXCEPTION["raw_row_sha256"]
    fields = raw_line.decode("cp1252").removesuffix("\r\n").split("\t")
    assert len(fields) == 9
    assert fields[0] == _APPDOCS_EMPTY_FIELD_EXCEPTION["application_docs_id"]
    assert fields[-2] == "" and fields[-1] == "2026-01-06 00:00:00"

    header = ("\t".join(EXPECTED_HEADERS["ApplicationDocs.txt"]) + "\r\n").encode("cp1252")
    prefix = b"".join(
        (
            f"{line}\t1\t123456\tORIG      \t1\ttitle\thttps://example.invalid/{line}\t2026-01-01 00:00:00\r\n"
        ).encode("cp1252")
        for line in range(1, _APPDOCS_EMPTY_FIELD_EXCEPTION["row_number"] - 1)
    )
    rows, manifest = _parse_tsv(
        table_name="ApplicationDocs.txt",
        payload=header + prefix + raw_line,
        archive_sha256=_APPDOCS_EMPTY_FIELD_EXCEPTION["archive_sha256"],
        compressed_byte_count=1,
        uncompressed_byte_count=len(header) + len(prefix) + len(raw_line),
        crc32=0,
    )
    assert rows[-1]["ApplicationDocsDate"] == "2026-01-06 00:00:00"
    assert manifest["row_shape_repairs"] == [{
        "rule": "application_docs_empty_field_before_date",
        "row_number": _APPDOCS_EMPTY_FIELD_EXCEPTION["row_number"],
        "raw_row_sha256": _APPDOCS_EMPTY_FIELD_EXCEPTION["raw_row_sha256"],
        "expected_field_count": len(EXPECTED_HEADERS["ApplicationDocs.txt"]),
        "observed_field_count": len(EXPECTED_HEADERS["ApplicationDocs.txt"]) + 1,
    }]


def test_exact_member_validation_recomputes_rehashed_row_semantics_from_source_bytes() -> None:
    raw = _zip_bytes()
    parsed = parse_drugs_at_fda_zip(raw, config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    receipt, _landings = _receipt_bound_to_exact_bodies(raw)
    forged = deepcopy(next(item for item in parsed.table_manifests if item["table_name"] == "Applications.txt"))
    # Keep internal arithmetic and self-hash valid.  Only the source member
    # itself can disprove this mutually-consistent row-count/profile/digest lie.
    forged["row_count"] = 2
    forged["field_count_profile"] = {str(len(EXPECTED_HEADERS["Applications.txt"])): 2}
    forged["ordered_row_digest_sha256"] = "0" * 64
    _rehash(forged, "manifest_payload_sha256")
    validate_contract(forged)
    with pytest.raises(ContractValidationError, match="member_semantics"):
        validate_drugs_at_fda_table_manifest(
            forged,
            receipt,
            exact_member_bytes=parsed.member_bytes_by_name["Applications.txt"],
        )


def test_exact_raw_body_receipt_validation_rejects_rehashed_release_date_lie() -> None:
    raw = _zip_bytes()
    receipt, landings = _receipt_bound_to_exact_bodies(raw)
    receipt["source_release_date"] = "2026-07-30"
    _rehash(receipt, "receipt_payload_sha256")
    raw_bodies = {
        "landing_before": landings[0],
        "archive": raw,
        "landing_after": landings[1],
    }
    with pytest.raises(ContractValidationError, match="release_date_binding"):
        validate_drugs_at_fda_release_receipt(receipt, raw_bodies_by_kind=raw_bodies)


def test_member_row_ceiling_fails_before_excess_row_key_or_duplicate_retention() -> None:
    tables = _fixture_tables()
    duplicate_application = list(tables["Applications.txt"][0])
    body = "\r\n".join([
        "\t".join(EXPECTED_HEADERS["Applications.txt"]),
        "\t".join(duplicate_application),
        "\t".join(duplicate_application),
    ]) + "\r\n"
    retained_lines: list[int] = []
    with pytest.raises(DrugsAtFdaCollectionError) as error:
        _parse_tsv(
            table_name="Applications.txt",
            payload=body.encode("cp1252"),
            archive_sha256="0" * 64,
            compressed_byte_count=1,
            uncompressed_byte_count=len(body),
            crc32=0,
            max_rows=1,
            row_sink=lambda _table, line, _digest, _row: retained_lines.append(line),
        )
    # The second row is deliberately a duplicate: MEMBER_ROW_LIMIT proves the
    # cap runs before its key is formed/retained or duplicate handling begins.
    assert error.value.code == "MEMBER_ROW_LIMIT"
    assert retained_lines == [2]


def test_graph_rejects_rehashed_receipt_and_manifest_cross_release_binding() -> None:
    raw = _zip_bytes()
    parsed = parse_drugs_at_fda_zip(raw, config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    receipt = _release(raw, parsed)
    receipt["archive_byte_count"] += 1
    receipt["receipt_payload_sha256"] = canonical_json_sha256({key: value for key, value in receipt.items() if key != "receipt_payload_sha256"})
    with pytest.raises(ContractValidationError):
        build_regulatory_graph(release=receipt, table_manifests=parsed.table_manifests, tables=parsed.tables)
    receipt = _release(raw, parsed)
    manifests = deepcopy(parsed.table_manifests)
    manifests[0]["release_id"] = "drugs_at_fda_release_" + "0" * 24
    manifests[0]["manifest_payload_sha256"] = canonical_json_sha256({key: value for key, value in manifests[0].items() if key != "manifest_payload_sha256"})
    with pytest.raises(ContractValidationError):
        build_regulatory_graph(release=receipt, table_manifests=manifests, tables=parsed.tables)


def test_dossier_schema_refuses_private_or_inferred_fields_even_when_rehashed() -> None:
    _raw, _parsed, graph = _parsed_graph()
    dossier = deepcopy(graph.dossiers[0])
    dossier["products"][0]["ticker"] = "SYNTH"
    dossier["dossier_payload_sha256"] = canonical_json_sha256({key: value for key, value in dossier.items() if key != "dossier_payload_sha256"})
    with pytest.raises(ContractValidationError):
        validate_contract("fda_application_dossier.v1", dossier)


def test_generic_contract_validation_enforces_fda_self_hash_ids_and_nested_release_binding() -> None:
    _raw, _parsed, graph = _parsed_graph()
    application = graph.application_snapshots[0]
    submission = graph.submission_observations[0]
    event = graph.regulatory_events[0]
    dossier = graph.dossiers[0]
    for document in (application, submission, event, dossier):
        validate_contract(document)

    forged_application = deepcopy(application)
    forged_application["application_number"] = "999999"
    forged_application["snapshot_payload_sha256"] = canonical_json_sha256({key: value for key, value in forged_application.items() if key != "snapshot_payload_sha256"})
    with pytest.raises(ContractValidationError, match="derived_id"):
        validate_contract(forged_application)

    forged_submission = deepcopy(submission)
    forged_submission["submission_number"] = "999"
    forged_submission["observation_payload_sha256"] = canonical_json_sha256({key: value for key, value in forged_submission.items() if key != "observation_payload_sha256"})
    with pytest.raises(ContractValidationError, match="derived_id"):
        validate_contract(forged_submission)

    forged_event = deepcopy(event)
    forged_event["submission_action_join_id"] = "999"
    forged_event["event_payload_sha256"] = canonical_json_sha256({key: value for key, value in forged_event.items() if key != "event_payload_sha256"})
    with pytest.raises(ContractValidationError, match="derived_id"):
        validate_contract(forged_event)

    forged_dossier = deepcopy(dossier)
    nested = forged_dossier["application_snapshot"]
    nested["source_evidence"]["archive_sha256"] = "0" * 64
    nested["snapshot_payload_sha256"] = canonical_json_sha256({key: value for key, value in nested.items() if key != "snapshot_payload_sha256"})
    forged_dossier["dossier_payload_sha256"] = canonical_json_sha256({key: value for key, value in forged_dossier.items() if key != "dossier_payload_sha256"})
    with pytest.raises(ContractValidationError, match="evidence_release|dossier_release_binding"):
        validate_contract(forged_dossier)


def test_rehashed_fda_evidence_cannot_swap_the_reviewed_page_or_manifest_set() -> None:
    _raw, _parsed, graph = _parsed_graph()
    application = deepcopy(graph.application_snapshots[0])

    wrong_url = deepcopy(application)
    wrong_url["source_evidence"]["source_url"] = "https://www.fda.gov/drugs/not-the-reviewed-data-page"
    _rehash(wrong_url, "snapshot_payload_sha256")
    with pytest.raises(ContractValidationError, match="evidence_source"):
        validate_contract(wrong_url)

    wrong_manifest = deepcopy(application)
    wrong_manifest["source_evidence"]["table_manifest_ids"] = ["drugs_at_fda_table_" + "0" * 24]
    _rehash(wrong_manifest, "snapshot_payload_sha256")
    with pytest.raises(ContractValidationError, match="evidence_manifests"):
        validate_contract(wrong_manifest)


def test_rehashed_submission_and_event_parent_orphan_claims_are_not_trusted() -> None:
    _raw, _parsed, graph = _parsed_graph()
    submission = graph.submission_observations[0]
    event = graph.regulatory_events[0]

    forged_parent = deepcopy(submission)
    forged_parent["application_snapshot_id"] = "fda_application_" + "0" * 24
    forged_parent["source_native_orphan"] = False
    _rehash(forged_parent, "observation_payload_sha256")
    with pytest.raises(ContractValidationError, match="submission_parent"):
        validate_contract(forged_parent)

    forged_submission_orphan = deepcopy(submission)
    forged_submission_orphan["source_native_orphan"] = True
    _rehash(forged_submission_orphan, "observation_payload_sha256")
    with pytest.raises(ContractValidationError, match="submission_parent"):
        validate_contract(forged_submission_orphan)

    forged_event_orphan = deepcopy(event)
    forged_event_orphan["action_type_lookup_id"] = None
    forged_event_orphan["action_type_description_source_text"] = None
    forged_event_orphan["source_native_orphan"] = False
    _rehash(forged_event_orphan, "event_payload_sha256")
    with pytest.raises(ContractValidationError, match="event_parent|event_action"):
        validate_contract(forged_event_orphan)


def test_rehashed_dossier_rejects_nested_evidence_drift_beyond_archive_identity() -> None:
    _raw, _parsed, graph = _parsed_graph()
    dossier = deepcopy(graph.dossiers[0])
    dossier["submissions"][0]["source_evidence"]["observed_at"] = "2026-08-01T00:00:01Z"
    _rehash(dossier["submissions"][0], "observation_payload_sha256")
    _rehash(dossier, "dossier_payload_sha256")
    with pytest.raises(ContractValidationError, match="dossier_release_binding"):
        validate_contract(dossier)


def test_dossier_rejects_duplicate_event_product_and_false_document_parent_claims() -> None:
    _raw, _parsed, graph = _parsed_graph()
    dossier = graph.dossiers[0]

    duplicate_event = deepcopy(dossier)
    duplicate_event["submission_action_events"].append(
        deepcopy(duplicate_event["submission_action_events"][0])
    )
    _rehash(duplicate_event, "dossier_payload_sha256")
    with pytest.raises(ContractValidationError, match="dossier_duplicate"):
        validate_contract(duplicate_event)

    duplicate_product = deepcopy(dossier)
    duplicate_product["products"].append(deepcopy(duplicate_product["products"][0]))
    _rehash(duplicate_product, "dossier_payload_sha256")
    with pytest.raises(ContractValidationError, match="dossier_duplicate"):
        validate_contract(duplicate_product)

    false_document_parent = deepcopy(dossier)
    false_document_parent["documents"][0]["submission_number"] = "999999"
    false_document_parent["documents"][0]["source_native_orphan"] = False
    _rehash(false_document_parent, "dossier_payload_sha256")
    with pytest.raises(ContractValidationError, match="document_parent"):
        validate_contract(false_document_parent)


def test_generic_release_and_manifest_validation_reject_key_smuggling_and_rehashed_header_drift() -> None:
    raw = _zip_bytes()
    parsed = parse_drugs_at_fda_zip(raw, config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    receipt = _release(raw, parsed)
    receipt["http_receipts"][0]["raw_object_key"] = receipt["http_receipts"][0]["raw_object_key"].replace("/landing/", "/landing_before/")
    receipt["receipt_payload_sha256"] = canonical_json_sha256({key: value for key, value in receipt.items() if key != "receipt_payload_sha256"})
    with pytest.raises(ContractValidationError, match="raw_key_binding"):
        validate_contract(receipt)
    manifest = deepcopy(parsed.table_manifests[0])
    manifest["header"] = ["different"]
    manifest["manifest_payload_sha256"] = canonical_json_sha256({key: value for key, value in manifest.items() if key != "manifest_payload_sha256"})
    with pytest.raises(ContractValidationError, match="drugs_fda.header"):
        validate_contract(manifest)


def test_streamed_sqlite_replay_is_logically_deterministic_and_graph_has_small_source_ceiling(tmp_path: Path) -> None:
    raw = _zip_bytes()
    first = stream_drugs_at_fda_zip_to_sqlite(raw, sqlite_path=tmp_path / "one.sqlite", config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    second = stream_drugs_at_fda_zip_to_sqlite(raw, sqlite_path=tmp_path / "two.sqlite", config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    assert first.table_row_counts == second.table_row_counts
    assert first.table_manifests == second.table_manifests
    import sqlite3
    with sqlite3.connect(tmp_path / "one.sqlite") as one, sqlite3.connect(tmp_path / "two.sqlite") as two:
        for table in SQLITE_TABLE_NAMES.values():
            assert one.execute(f"SELECT physical_line, physical_line_sha256 FROM {table} ORDER BY physical_line").fetchall() == two.execute(f"SELECT physical_line, physical_line_sha256 FROM {table} ORDER BY physical_line").fetchall()
        plan = one.execute("EXPLAIN QUERY PLAN SELECT count(*) FROM fda_submission_action_join j WHERE NOT EXISTS (SELECT 1 FROM fda_action_types_lookup a WHERE a.ActionTypes_LookupID=j.ActionTypes_LookupID)").fetchall()
        assert any("idx_action_lookup" in str(row) for row in plan)
    assert SQLITE_SCHEMA_SPEC_SHA256
    # The receipt must bind the same ``raw`` archive the rows came from: a second
    # independently built archive fails receipt validation (a ValueError too) and
    # the row ceiling this pins would never be reached.
    parsed = parse_drugs_at_fda_zip(raw, config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    oversized = {name: list(rows) for name, rows in parsed.tables.items()}
    oversized["Applications.txt"] = oversized["Applications.txt"] * 10_001
    with pytest.raises(RegulatoryGraphError, match="full_release_requires_private_sqlite_query_index"):
        build_regulatory_graph(release=_release(raw, parsed), table_manifests=parsed.table_manifests, tables=oversized)


def test_private_derived_pointer_is_separate_and_does_not_publish_raw_coordinates(tmp_path: Path) -> None:
    raw = _zip_bytes()
    landing = f"<html>Data Last Updated: July 31st, 2026 {ARCHIVE_URL}</html>".encode()
    archive = _response(raw, headers={"content-type": "application/zip", "content-length": str(len(raw)), "content-disposition": "attachment; filename=dafdata20260731.zip", "last-modified": "Fri, 31 Jul 2026 12:54:47 GMT"})
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private", state_root=tmp_path / "regulatory-state", config=DrugsAtFdaConfig(user_agent="test@example.invalid"), now_fn=lambda: __import__("datetime").datetime(2026, 8, 1, tzinfo=__import__("datetime").timezone.utc))
    result = collector.publish_responses(_response(landing), archive, _response(landing))
    pointer = json.loads(result.pointer_path.read_text())
    assert pointer["release_id"] == result.release_id
    assert (tmp_path / "private" / "biocatalyst" / "raw" / "drugs_at_fda" / "archive" / f"{result.archive_sha256}.zip").exists()
    manifest = (result.generation_path / "manifest.json").read_text()
    assert "raw_object_key" not in manifest and "physical_line" not in manifest
    import sqlite3
    with sqlite3.connect(result.generation_path / "release.sqlite") as connection:
        assert sum(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in SQLITE_TABLE_NAMES.values()) == 12
        assert "source_rows" not in {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for source_name, sqlite_name in SQLITE_TABLE_NAMES.items():
            columns = {row[1]: (row[2], row[3]) for row in connection.execute(f"PRAGMA table_info({sqlite_name})")}
            assert columns["physical_line"] == ("INTEGER", 1)
            assert columns["physical_line_sha256"] == ("TEXT", 1)
            assert all(columns[column] == ("TEXT", 1) for column in EXPECTED_HEADERS[source_name])
            if "SubmissionType" in EXPECTED_HEADERS[source_name]:
                assert columns["SubmissionType_join"] == ("TEXT", 1)
            ddl = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (sqlite_name,)).fetchone()[0]
            assert ddl.endswith("WITHOUT ROWID")


def test_same_archive_refetch_is_a_transport_observation_not_a_mutated_release(tmp_path: Path) -> None:
    raw = _zip_bytes()
    landing = f"<html>Data Last Updated: July 31st, 2026 {ARCHIVE_URL}</html>".encode()
    archive = _response(raw, headers={"content-type": "application/zip", "content-length": str(len(raw)), "content-disposition": "attachment; filename=dafdata20260731.zip"})
    instants = iter([
        __import__("datetime").datetime(2026, 8, 1, tzinfo=__import__("datetime").timezone.utc),
        __import__("datetime").datetime(2026, 8, 2, tzinfo=__import__("datetime").timezone.utc),
    ])
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private", state_root=tmp_path / "state", config=DrugsAtFdaConfig(user_agent="test@example.invalid"), now_fn=lambda: next(instants))
    first = collector.publish_responses(_response(landing), archive, _response(landing))
    pointer_before = first.pointer_path.read_bytes()
    receipt_before = (tmp_path / "private" / "biocatalyst" / "receipts" / "drugs_at_fda" / f"{first.release_id}.json").read_bytes()
    second = collector.publish_responses(_response(landing), archive, _response(landing))
    assert second.release_id == first.release_id
    assert second.pointer_path.read_bytes() == pointer_before
    assert (tmp_path / "private" / "biocatalyst" / "receipts" / "drugs_at_fda" / f"{first.release_id}.json").read_bytes() == receipt_before
    assert len(list((tmp_path / "private" / "biocatalyst" / "attempts" / "drugs_at_fda" / first.archive_sha256).glob("*.json"))) == 2


def test_crash_retry_uses_immutable_canonical_landing_evidence_not_new_transport_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _zip_bytes()
    first_landing = _landing_bytes()
    collector = DrugsAtFdaCollector(
        private_root=tmp_path / "private",
        state_root=tmp_path / "state",
        config=DrugsAtFdaConfig(user_agent="test@example.invalid"),
    )
    original_commit = collector._commit_private_sqlite

    def crash_before_generation(*_args, **_kwargs):
        raise RuntimeError("simulated crash after canonical evidence commit")

    monkeypatch.setattr(collector, "_commit_private_sqlite", crash_before_generation)
    with pytest.raises(RuntimeError, match="simulated crash"):
        collector.publish_responses(
            _response(first_landing), _response(raw, headers=_archive_headers(raw)), _response(first_landing)
        )

    release_id = f"drugs_at_fda_release_{sha256(raw).hexdigest()[:24]}"
    receipt_path = tmp_path / "private" / "biocatalyst" / "receipts" / "drugs_at_fda" / f"{release_id}.json"
    canonical_receipt_before = receipt_path.read_bytes()
    canonical_receipt = json.loads(canonical_receipt_before)
    canonical_raw_paths = [
        tmp_path / "private" / str(item["raw_object_key"])
        for item in canonical_receipt["http_receipts"]
    ]
    canonical_raw_before = [path.read_bytes() for path in canonical_raw_paths]
    assert not (tmp_path / "state" / "generations" / release_id).exists()

    monkeypatch.setattr(collector, "_commit_private_sqlite", original_commit)
    retry_landing = (
        f"<html><body>Data Last Updated: July 31st, 2026 <p>reformatted after crash</p>{ARCHIVE_URL}</body></html>"
    ).encode()
    completed = collector.publish_responses(
        _response(retry_landing), _response(raw, headers=_archive_headers(raw)), _response(retry_landing)
    )
    assert completed.release_id == release_id and completed.pointer_path.exists()
    assert receipt_path.read_bytes() == canonical_receipt_before
    assert [path.read_bytes() for path in canonical_raw_paths] == canonical_raw_before


def test_required_private_mirror_readback_precedes_pointer_advance(tmp_path: Path) -> None:
    raw = _zip_bytes()
    landing = f"<html>Data Last Updated: July 31st, 2026 {ARCHIVE_URL}</html>".encode()
    archive = _response(raw, headers={"content-type": "application/zip", "content-length": str(len(raw)), "content-disposition": "attachment; filename=dafdata20260731.zip"})
    config = DrugsAtFdaConfig(user_agent="test@example.invalid", require_private_mirror=True)
    blocked = DrugsAtFdaCollector(private_root=tmp_path / "blocked-private", state_root=tmp_path / "blocked-state", config=config)
    with pytest.raises(DrugsAtFdaCollectionError, match="PRIVATE_MIRROR_REQUIRED"):
        blocked.publish_responses(_response(landing), archive, _response(landing))
    assert not (tmp_path / "blocked-state" / "current.json").exists()
    store = _MemoryStore()
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private", state_root=tmp_path / "state", config=config, private_store=store)
    result = collector.publish_responses(_response(landing), archive, _response(landing))
    assert result.pointer_path.exists()
    assert f"biocatalyst/raw/drugs_at_fda/archive/{result.archive_sha256}.zip" in store.objects
    assert not any(key.endswith("/release.sqlite") for key in store.objects)
    assert any(key.startswith(f"biocatalyst/commits/drugs_at_fda/{result.release_id}/") for key in store.objects)
    # Disaster rehydrate uses the exact remote source ZIP, not an oversized
    # remote SQLite sidecar, and reconstructs the same logical inventory.
    replay = stream_drugs_at_fda_zip_to_sqlite(
        store.objects[f"biocatalyst/raw/drugs_at_fda/archive/{result.archive_sha256}.zip"],
        sqlite_path=tmp_path / "rehydrated.sqlite", config=config,
    )
    assert replay.table_row_counts == json.loads((result.generation_path / "manifest.json").read_text())["table_row_counts"]


def test_dark_worker_refuses_registry_blocked_enablement() -> None:
    plan = load_environment({"BIOCATALYST_REGULATORY_ENABLED": "0"})
    assert plan.enabled is False
    with pytest.raises(RegulatoryWorkerConfigError, match="blocked by source registry"):
        load_environment({"BIOCATALYST_REGULATORY_ENABLED": "1"})


def test_network_gate_runs_before_any_request_and_fetch_rejects_unreviewed_redirect_or_oversize_body(tmp_path: Path) -> None:
    session = _Session([])
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private", state_root=tmp_path / "state", config=DrugsAtFdaConfig(user_agent="test@example.invalid"), session=session)
    with pytest.raises(DrugsAtFdaCollectionError, match="SOURCE_INGEST_BLOCKED"):
        collector.collect()
    assert session.calls == []

    redirect = _response(b"", headers={"location": "https://example.invalid/not-fda"})
    redirect.status_code = 302
    session = _Session([redirect])
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private2", state_root=tmp_path / "state2", config=DrugsAtFdaConfig(user_agent="test@example.invalid"), session=session)
    with pytest.raises(DrugsAtFdaCollectionError, match="UNAPPROVED_FDA_URL"):
        collector._get(LANDING_URL, "text/html")
    assert session.calls[0][1]["allow_redirects"] is False and session.calls[0][1]["stream"] is True

    huge = _response(b"x" * 17, headers={"content-length": "17"})
    session = _Session([huge])
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private3", state_root=tmp_path / "state3", config=DrugsAtFdaConfig(user_agent="test@example.invalid", max_landing_bytes=16), session=session)
    with pytest.raises(DrugsAtFdaCollectionError, match="HTTP_BODY_TOO_LARGE"):
        collector._get(LANDING_URL, "text/html")

    streamed = _response(b"<html>small</html>", chunks=[b"<html>", b"small</html>"])
    session = _Session([streamed])
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private4", state_root=tmp_path / "state4", config=DrugsAtFdaConfig(user_agent="test@example.invalid"), session=session)
    returned = collector._get(LANDING_URL, "text/html")
    assert returned.content == b"<html>small</html>"
    assert streamed.closed is True


@pytest.mark.skipif(os.name != "posix", reason="the collector publication lock uses POSIX flock")
def test_interprocess_publication_lock_blocks_entry_until_the_holder_releases(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    raw = _zip_bytes()
    private_root = tmp_path / "private"
    state_root = tmp_path / "state"
    state_root.mkdir()
    process = context.Process(
        target=_publication_lock_worker,
        args=(str(private_root), str(state_root), raw, results),
    )
    with (state_root / "publication.lock").open("a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        process.start()
        try:
            assert results.get(timeout=15) == ("ready", None)
            try:
                premature = results.get(timeout=0.4)
            except Empty:
                pass
            else:
                pytest.fail(f"publisher entered while a different process held the lock: {premature!r}")
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    try:
        assert results.get(timeout=20) == ("entered_locked", None)
        status, payload = results.get(timeout=35)
        assert status == "completed", payload
        assert payload == f"drugs_at_fda_release_{sha256(raw).hexdigest()[:24]}"
    finally:
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)
    assert process.exitcode == 0


def test_existing_generation_repairs_missing_pointer_without_replacing_it(tmp_path: Path) -> None:
    raw = _zip_bytes()
    landing = f"<html>Data Last Updated: July 31st, 2026 {ARCHIVE_URL}</html>".encode()
    archive_headers = {"content-type": "application/zip", "content-length": str(len(raw)), "content-disposition": "attachment; filename=dafdata20260731.zip"}
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private", state_root=tmp_path / "state", config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    first = collector.publish_responses(_response(landing), _response(raw, headers=archive_headers), _response(landing))
    first.pointer_path.unlink()
    repaired = collector.publish_responses(_response(landing), _response(raw, headers=archive_headers), _response(landing))
    assert repaired.generation_path == first.generation_path
    assert repaired.pointer_path.exists()


def test_replaying_an_older_existing_generation_cannot_roll_back_current_pointer(tmp_path: Path) -> None:
    first_raw = _zip_bytes()
    second_raw = _zip_bytes(mutate=lambda tables: tables["Applications.txt"][0].__setitem__(1, "CHANGED SPONSOR"))
    landing = f"<html>Data Last Updated: July 31st, 2026 {ARCHIVE_URL}</html>".encode()
    collector = DrugsAtFdaCollector(private_root=tmp_path / "private", state_root=tmp_path / "state", config=DrugsAtFdaConfig(user_agent="test@example.invalid"))
    def archive(raw: bytes):
        return _response(raw, headers={"content-type": "application/zip", "content-length": str(len(raw)), "content-disposition": "attachment; filename=dafdata20260731.zip"})
    old = collector.publish_responses(_response(landing), archive(first_raw), _response(landing))
    current = collector.publish_responses(_response(landing), archive(second_raw), _response(landing))
    pointer_before = current.pointer_path.read_bytes()
    replay = collector.publish_responses(_response(landing), archive(first_raw), _response(landing))
    assert replay.release_id == old.release_id
    assert current.pointer_path.read_bytes() == pointer_before


def test_recovery_refuses_semantically_tampered_sqlite_and_never_advances_pointer(tmp_path: Path) -> None:
    collector, raw, result = _publish_synthetic(tmp_path)
    result.pointer_path.unlink()
    with sqlite3.connect(result.generation_path / "release.sqlite") as connection:
        connection.execute(
            "UPDATE fda_applications SET SponsorName=? WHERE physical_line=2",
            ("tampered after release commit",),
        )
        connection.commit()
    with pytest.raises(DrugsAtFdaCollectionError) as error:
        collector.publish_responses(
            _response(_landing_bytes()), _response(raw, headers=_archive_headers(raw)), _response(_landing_bytes())
        )
    assert error.value.code == "PRIVATE_GENERATION_SEMANTIC_DIGEST_MISMATCH"
    assert not result.pointer_path.exists()


def test_recovery_refuses_rehashed_manifest_or_index_metadata_tampering(tmp_path: Path) -> None:
    for name, mutate in (
        ("manifest", lambda payload: payload.__setitem__("source_id", "forged_fda_source")),
        ("index", lambda payload: payload.__setitem__("query_backend", "forged_public_database")),
    ):
        collector, raw, result = _publish_synthetic(tmp_path / name)
        result.pointer_path.unlink()
        target = result.generation_path / f"{name}.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        mutate(payload)
        if "manifest_payload_sha256" in payload:
            payload["manifest_payload_sha256"] = canonical_json_sha256(
                {key: value for key, value in payload.items() if key != "manifest_payload_sha256"}
            )
        target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with pytest.raises(DrugsAtFdaCollectionError):
            collector.publish_responses(
                _response(_landing_bytes()), _response(raw, headers=_archive_headers(raw)), _response(_landing_bytes())
            )
        assert not result.pointer_path.exists()


def test_recovery_rebinds_a_mutually_consistent_forged_table_manifest_to_exact_zip_bytes(
    tmp_path: Path,
) -> None:
    collector, raw, result = _publish_synthetic(tmp_path)
    result.pointer_path.unlink()
    manifest_path = result.generation_path / "manifest.json"
    index_path = result.generation_path / "index.json"
    generation_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    forged_table = next(
        item for item in generation_manifest["table_manifests"]
        if item["table_name"] == "Applications.txt"
    )
    forged_table["ordered_row_digest_sha256"] = "f" * 64
    _rehash(forged_table, "manifest_payload_sha256")
    generation_manifest["manifest_payload_sha256"] = canonical_json_sha256({
        key: value for key, value in generation_manifest.items()
        if key != "manifest_payload_sha256"
    })
    manifest_path.write_bytes(canonical_json_bytes(generation_manifest) + b"\n")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["generation_manifest_payload_sha256"] = generation_manifest["manifest_payload_sha256"]
    index_path.write_bytes(canonical_json_bytes(index) + b"\n")
    with sqlite3.connect(result.generation_path / "release.sqlite") as connection:
        connection.execute(
            "UPDATE table_manifests SET manifest_json=? WHERE table_name=?",
            (canonical_json_bytes(forged_table).decode("utf-8"), "Applications.txt"),
        )
        connection.commit()

    with pytest.raises(DrugsAtFdaCollectionError) as error:
        collector.publish_responses(
            _response(_landing_bytes()), _response(raw, headers=_archive_headers(raw)), _response(_landing_bytes())
        )
    assert error.value.code == "PRIVATE_GENERATION_SOURCE_BINDING"
    assert not result.pointer_path.exists()


def test_recovery_rejects_rehashed_sqlite_semantics_that_no_longer_match_source_manifests(
    tmp_path: Path,
) -> None:
    collector, raw, result = _publish_synthetic(tmp_path)
    result.pointer_path.unlink()
    sqlite_path = result.generation_path / "release.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute(
            "UPDATE fda_applications SET SponsorName=? WHERE physical_line=2",
            ("rehashed local sqlite source-cell forgery",),
        )
        connection.commit()
    rehashed_sqlite_digests = _typed_sqlite_semantic_digests(sqlite_path)

    manifest_path = result.generation_path / "manifest.json"
    index_path = result.generation_path / "index.json"
    generation_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original_source_manifest_digests = {
        item["table_name"]: item["typed_row_semantic_digest_sha256"]
        for item in generation_manifest["table_manifests"]
    }
    assert rehashed_sqlite_digests != original_source_manifest_digests
    # Give every locally-mutable layer a coherent new self-description.  The
    # raw-source table manifests remain untouched and must veto recovery.
    generation_manifest["sqlite_table_semantic_row_digests"] = rehashed_sqlite_digests
    generation_manifest["manifest_payload_sha256"] = canonical_json_sha256({
        key: value for key, value in generation_manifest.items()
        if key != "manifest_payload_sha256"
    })
    manifest_path.write_bytes(canonical_json_bytes(generation_manifest) + b"\n")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["sqlite_table_semantic_row_digests"] = rehashed_sqlite_digests
    index["generation_manifest_payload_sha256"] = generation_manifest["manifest_payload_sha256"]
    index_path.write_bytes(canonical_json_bytes(index) + b"\n")

    with pytest.raises(DrugsAtFdaCollectionError) as error:
        collector.publish_responses(
            _response(_landing_bytes()), _response(raw, headers=_archive_headers(raw)), _response(_landing_bytes())
        )
    assert error.value.code == "PRIVATE_GENERATION_SOURCE_SEMANTIC_BINDING"
    assert not result.pointer_path.exists()


def test_same_release_corrupted_pointer_is_never_rewritten(tmp_path: Path) -> None:
    collector, raw, result = _publish_synthetic(tmp_path)
    pointer = json.loads(result.pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = "0" * 64
    # Keep valid JSON while ensuring this exact corruption is observable after
    # the failed repair attempt; it must not be silently replaced.
    result.pointer_path.write_bytes(json.dumps(pointer, sort_keys=True).encode("utf-8") + b"\n")
    before = result.pointer_path.read_bytes()
    with pytest.raises(DrugsAtFdaCollectionError) as error:
        collector.publish_responses(
            _response(_landing_bytes()), _response(raw, headers=_archive_headers(raw)), _response(_landing_bytes())
        )
    assert error.value.code == "CURRENT_POINTER_BINDING"
    assert result.pointer_path.read_bytes() == before


def test_remote_commit_recovery_rereads_every_required_object_and_commit(tmp_path: Path) -> None:
    store = _MemoryStore()
    collector, raw, result = _publish_synthetic(
        tmp_path, require_private_mirror=True, private_store=store
    )
    pointer = json.loads(result.pointer_path.read_text(encoding="utf-8"))
    archive_key = f"biocatalyst/raw/drugs_at_fda/archive/{result.archive_sha256}.zip"
    archive_before = store.objects[archive_key]
    receipt = json.loads(
        (tmp_path / "private" / "biocatalyst" / "receipts" / "drugs_at_fda" / f"{result.release_id}.json").read_text()
    )
    result.pointer_path.unlink()
    store.objects[archive_key] = b"corrupted remote archive"
    with pytest.raises(DrugsAtFdaCollectionError) as error:
        collector._repair_existing_generation_pointer(receipt, result.generation_path)
    assert error.value.code == "PRIVATE_REMOTE_OBJECT_READBACK_FAILED"
    assert not result.pointer_path.exists()

    store.objects[archive_key] = archive_before
    commit_key = pointer["private_remote_commit_object_key"]
    store.objects[commit_key] = b"corrupted remote commit"
    with pytest.raises(DrugsAtFdaCollectionError) as error:
        collector._repair_existing_generation_pointer(receipt, result.generation_path)
    assert error.value.code == "PRIVATE_REMOTE_COMMIT_READBACK_FAILED"
    assert not result.pointer_path.exists()
