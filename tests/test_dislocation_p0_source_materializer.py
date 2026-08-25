"""The materializer uses current Submissions and owner persistence only."""
from __future__ import annotations

import json
from pathlib import Path

from collectors.sec_document_spine import SecFilingArchiveCollector
from scripts.research.dislocation_p0_source_adapter import CanonicalSpineRef
from scripts.research.dislocation_p0_source_adapter import read_source_packets
from scripts.research.dislocation_p0_source_materializer import (
    materialize_current_p0_source_refs, materialize_current_source_refs,
)


RECORDED = "2026-08-22T12:00:00Z"


class _Response:
    status_code = 200
    headers = {}
    url = ""
    def __init__(self, url: str, body: bytes) -> None: self.url, self._body = url, body
    def raise_for_status(self) -> None: return None
    def iter_content(self, chunk_size: int): yield self._body
    def close(self) -> None: return None


class _Session:
    def __init__(self, *, include_match: bool = True) -> None:
        self.include_match = include_match
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.urls.append(url)
        if url.endswith("/index.json"):
            names = ["primary.htm"] + (["matched.htm"] if self.include_match else [])
            return _Response(
                url,
                json.dumps({"directory": {"item": [{"name": name} for name in names]}}).encode(),
            )
        if url.endswith("/matched.htm"):
            return _Response(url, b"canonical matched exhibit")
        if url.endswith("/primary.htm"):
            raise AssertionError("filing cover must not replace the FTS-matched exhibit")
        raise AssertionError(f"unexpected owner URL: {url}")


def _payload(cik: str, accession: str) -> bytes:
    return json.dumps({"filings": {"recent": {
        "accessionNumber": [accession], "form": ["8-K"], "filingDate": ["2026-08-20"],
        "reportDate": ["2026-08-19"], "acceptanceDateTime": ["2026-08-20T15:30:00Z"],
        "primaryDocument": ["primary.htm"], "isXBRL": [False], "isInlineXBRL": [False],
        "items": ["2.05"], "amendsAccessionNumber": [None],
    }}}).encode()


def _selections() -> list[CanonicalSpineRef]:
    return [CanonicalSpineRef(
        slot, f"{slot:010d}", f"000000000{slot % 10}-26-{slot:06d}",
        "8-K", "2026-08-20", ("matched.htm",), None,
    ) for slot in range(1, 21)]


def test_materializes_only_current_selected_rows_to_owner_refs(tmp_path: Path) -> None:
    selections = _selections()
    sessions: list[_Session] = []
    def fetch(cik: str):
        row = next(item for item in selections if item.cik == cik)
        return _payload(cik, row.accession), {"url": "ignored"}
    def factory(root: Path, agent: str):
        session = _Session()
        sessions.append(session)
        return SecFilingArchiveCollector(root, user_agent=agent, session=session)
    result = materialize_current_p0_source_refs(archive_root=tmp_path, selections=selections, user_agent="P0 test@example.com", fetch_submissions=fetch, collector_factory=factory, recorded_at=RECORDED)
    assert result.complete and len(result.refs) == 20
    assert all(ref.manifest_storage_key and ref.expected_base_form == "8-K" for ref in result.refs)
    assert all(any(url.endswith("/matched.htm") for url in session.urls) for session in sessions)
    assert all(not any(url.endswith("/primary.htm") for url in session.urls) for session in sessions)


def test_absent_current_accession_is_gap_without_top_up(tmp_path: Path) -> None:
    selections = _selections()
    def fetch(cik: str):
        row = next(item for item in selections if item.cik == cik)
        return _payload(cik, "0000000000-26-999999"), {}
    result = materialize_current_p0_source_refs(archive_root=tmp_path, selections=selections, user_agent="P0 test@example.com", fetch_submissions=fetch, recorded_at=RECORDED)
    assert result.refs == ()
    assert all(gap.code == "OWNER_CAPABILITY_GAP" for gap in result.gaps)


def test_missing_matched_document_fails_closed_without_primary_fallback(tmp_path: Path) -> None:
    selections = _selections()
    sessions: list[_Session] = []
    def fetch(cik: str):
        row = next(item for item in selections if item.cik == cik)
        return _payload(cik, row.accession), {}
    def factory(root: Path, agent: str):
        session = _Session(include_match=False)
        sessions.append(session)
        return SecFilingArchiveCollector(root, user_agent=agent, session=session)
    result = materialize_current_p0_source_refs(
        archive_root=tmp_path,
        selections=selections,
        user_agent="P0 test@example.com",
        fetch_submissions=fetch,
        collector_factory=factory,
        recorded_at=RECORDED,
    )
    assert result.refs == ()
    assert all(gap.code == "OWNER_FTS_DOCUMENT_NOT_IN_INDEX" for gap in result.gaps)
    assert all(not any(url.endswith("/primary.htm") for url in session.urls) for session in sessions)


def test_generic_primary_context_is_additive_and_reuses_match_receipt(tmp_path: Path) -> None:
    selections = _selections()[:2]
    class PrimarySession(_Session):
        def get(self, url: str, **kwargs):
            if url.endswith("/primary.htm"):
                self.urls.append(url)
                return _Response(url, b"canonical primary context")
            return super().get(url, **kwargs)
    sessions: list[PrimarySession] = []
    def fetch(cik: str):
        row = next(item for item in selections if item.cik == cik)
        return _payload(cik, row.accession), {}
    def factory(root: Path, agent: str):
        session = PrimarySession(); sessions.append(session)
        return SecFilingArchiveCollector(root, user_agent=agent, session=session)
    materialized = materialize_current_source_refs(
        archive_root=tmp_path, selections=selections, user_agent="P0 test@example.com",
        fetch_submissions=fetch, collector_factory=factory, recorded_at=RECORDED,
        required_packet_count=2, include_primary_context=True,
        primary_context_required=True,
    )
    assert materialized.complete and len(materialized.refs) == 2
    packets = read_source_packets(
        archive_root=tmp_path, refs=materialized.refs, required_packet_count=2,
        include_primary_context=True, primary_context_required=True,
    )
    assert packets.complete
    assert all(packet.primary_context and packet.primary_context_source == b"canonical primary context" for packet in packets.packets)
    assert all(len(packet.matched_documents) == 1 for packet in packets.packets)
    assert all(any(url.endswith("/primary.htm") for url in session.urls) for session in sessions)


def test_generic_primary_equal_to_match_reuses_existing_owner_receipt(tmp_path: Path) -> None:
    selections = _selections()[:2]
    sessions: list[_Session] = []
    def fetch(cik: str):
        row = next(item for item in selections if item.cik == cik)
        payload = json.loads(_payload(cik, row.accession))
        payload["filings"]["recent"]["primaryDocument"] = ["matched.htm"]
        return json.dumps(payload).encode(), {}
    def factory(root: Path, agent: str):
        session = _Session(); sessions.append(session)
        return SecFilingArchiveCollector(root, user_agent=agent, session=session)
    materialized = materialize_current_source_refs(
        archive_root=tmp_path, selections=selections, user_agent="P0 test@example.com",
        fetch_submissions=fetch, collector_factory=factory, recorded_at=RECORDED,
        required_packet_count=2, include_primary_context=True,
        primary_context_required=True,
    )
    assert materialized.complete
    packets = read_source_packets(
        archive_root=tmp_path, refs=materialized.refs, required_packet_count=2,
        include_primary_context=True, primary_context_required=True,
    )
    assert packets.complete
    assert all(packet.primary_context_source == packet.source_documents[0] for packet in packets.packets)
    assert all(not any(url.endswith("/primary.htm") for url in session.urls) for session in sessions)


def _historical_selection() -> CanonicalSpineRef:
    return CanonicalSpineRef(
        1, "0001069533", "0001069533-18-000041", "8-K", "2018-10-01",
        ("matched.htm",), None,
    )


def _historical_current(*, name: str = "CIK0001069533-submissions-001.json", start: str = "2005-06-03", end: str = "2019-04-30", duplicate: bool = False) -> bytes:
    payload = json.loads(_payload("0001069533", "0001069533-26-000001"))
    file = {"name": name, "filingFrom": start, "filingTo": end, "filingCount": 1}
    payload["filings"]["files"] = [file, dict(file)] if duplicate else [file]
    return json.dumps(payload).encode()


def _historical_columns() -> bytes:
    return json.dumps({
        "cik": "0001069533",
        "accessionNumber": ["0001069533-18-000041"], "form": ["8-K"],
        "filingDate": ["2018-10-01"], "reportDate": ["2018-09-30"],
        "acceptanceDateTime": ["2018-10-01T15:30:00Z"],
        "primaryDocument": ["primary.htm"], "isXBRL": [False], "isInlineXBRL": [False],
        "items": ["2.05"], "amendsAccessionNumber": [None],
    }).encode()


def test_declared_covering_historical_shard_materializes_exact_frozen_accession(tmp_path: Path) -> None:
    selection = _historical_selection(); requested: list[tuple[str, str]] = []
    def fetch(_cik: str): return _historical_current(), {}
    def historical(cik: str, name: str):
        requested.append((cik, name)); return _historical_columns(), {}
    result = materialize_current_source_refs(
        archive_root=tmp_path, selections=[selection], user_agent="P0 test@example.com",
        fetch_submissions=fetch, fetch_historical_submissions=historical,
        collector_factory=lambda root, agent: SecFilingArchiveCollector(root, user_agent=agent, session=_Session()),
        recorded_at=RECORDED, required_packet_count=1,
    )
    assert result.complete and requested == [("0001069533", "CIK0001069533-submissions-001.json")]


def test_historical_inventory_wrong_cik_and_missing_coverage_are_typed_gaps(tmp_path: Path) -> None:
    selection = _historical_selection()
    for current, code in (
        (_historical_current(name="CIK0000000001-submissions-001.json"), "OWNER_HISTORICAL_FILENAME_CIK_MISMATCH"),
        (_historical_current(start="2019-05-01", end="2020-01-01"), "OWNER_HISTORICAL_COVERAGE_ABSENT"),
    ):
        result = materialize_current_source_refs(
            archive_root=tmp_path, selections=[selection], user_agent="P0 test@example.com",
            fetch_submissions=lambda _cik, value=current: (value, {}),
            fetch_historical_submissions=lambda _cik, _name: (_historical_columns(), {}),
            recorded_at=RECORDED, required_packet_count=1,
        )
        assert result.refs == () and result.gaps[0].code == code


def test_historical_duplicate_covering_target_is_refused(tmp_path: Path) -> None:
    selection = _historical_selection()
    current = json.loads(_historical_current())
    current["filings"]["files"].append({"name": "CIK0001069533-submissions-002.json", "filingFrom": "2018-01-01", "filingTo": "2018-12-31", "filingCount": 1})
    result = materialize_current_source_refs(
        archive_root=tmp_path, selections=[selection], user_agent="P0 test@example.com",
        fetch_submissions=lambda _cik: (json.dumps(current).encode(), {}),
        fetch_historical_submissions=lambda _cik, _name: (_historical_columns(), {}),
        recorded_at=RECORDED, required_packet_count=1,
    )
    assert result.refs == () and result.gaps[0].code == "OWNER_HISTORICAL_TARGET_CONFLICT"
