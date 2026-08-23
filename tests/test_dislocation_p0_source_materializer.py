"""The materializer uses current Submissions and owner persistence only."""
from __future__ import annotations

import json
from pathlib import Path

from collectors.sec_document_spine import SecFilingArchiveCollector
from scripts.research.dislocation_p0_source_adapter import CanonicalSpineRef
from scripts.research.dislocation_p0_source_materializer import materialize_current_p0_source_refs


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
