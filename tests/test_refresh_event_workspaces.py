"""E1P: publish the flagship event_workspace nest without touching v1."""
from __future__ import annotations

import gzip
import io
import json
from hashlib import sha256
from pathlib import Path

import pytest

from engine.company_intelligence.event_workspace import (
    AAPL_ACCESSION,
    AAPL_CALL_DATE,
    AAPL_CIK,
    FLAGSHIP_EVENT_ID,
    LIVE_CIE_ALIAS,
    LIVE_NARRATIVE_ALIAS,
    LIVE_PUBLIC_SLUG,
    apple_registry,
    flagship_fiscal_period,
    write_workspace_generation,
)
from engine.company_intelligence.event_workspace_build import build_event_workspace
from engine.earnings_transcript_intake import TranscriptRef, canonical_body_sha256
from engine.neuralweb import company_intelligence_reader as reader
from scripts.publish_company_intelligence_r2 import PUBLISH_CONFLICT, publish, publish_event_workspaces
from scripts.refresh_event_workspaces import (
    PriorWorkspaceFetchFailed,
    RefreshError,
    _parse_sgml_manifest,
    _PriorWorkspaceNotPublished,
    _select_exhibit_99_1,
    discover_new_homebuilder_revisions,
    load_prior_workspace,
    load_prior_workspace_for_ticker,
    refresh,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "company_intelligence"
EXHIBIT = FIXTURES / "aapl_fy2026_q3_ex99_1.htm"
TRANSCRIPT = FIXTURES / "aapl_fy2026_q3.json.gz"
ACCEPTANCE = "2026-07-30T16:30:00Z"
ARCHIVE_BASE = (
    f"https://www.sec.gov/Archives/edgar/data/{int(AAPL_CIK)}/{AAPL_ACCESSION.replace('-', '')}"
)
HEADERS_URL = f"{ARCHIVE_BASE}/{AAPL_ACCESSION}-index-headers.html"
EXHIBIT_NAME = "a8-kex991q3202606272026.htm"
EXHIBIT_URL = f"{ARCHIVE_BASE}/{EXHIBIT_NAME}"
SUBMISSIONS_URL = f"https://data.sec.gov/submissions/CIK{AAPL_CIK}.json"
WS_MARKER = "company_intelligence/event_workspaces/manifest.json"
V1_MARKER = "company_intelligence/manifest.json"


class _PreconditionFailed(RuntimeError):
    response = {"Error": {"Code": "PreconditionFailed"}, "ResponseMetadata": {"HTTPStatusCode": 412}}


class _FakeR2:
    def __init__(
        self,
        remote_manifest: dict | None = None,
        objects: dict[str, tuple[bytes, dict]] | None = None,
        *,
        marker_key: str = WS_MARKER,
        conflict_on_cas: bool = False,
    ) -> None:
        self.marker_key = marker_key
        self.remote_manifest = remote_manifest
        self.objects = dict(objects or {})
        self.puts: list[tuple[str, dict]] = []
        self.conflict_on_cas = conflict_on_cas

    def get_object(self, *, Bucket, Key):
        if Key == self.marker_key and self.remote_manifest is not None:
            return {
                "Body": io.BytesIO(json.dumps(self.remote_manifest).encode()),
                "ETag": "prior-etag",
            }
        if Key in self.objects:
            body, _metadata = self.objects[Key]
            return {"Body": io.BytesIO(body)}
        raise RuntimeError("missing")

    def head_object(self, *, Bucket, Key):
        if Key in self.objects:
            body, metadata = self.objects[Key]
            return {"Metadata": metadata, "ContentLength": len(body)}
        raise RuntimeError("missing")

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if kwargs.get("IfMatch") and self.conflict_on_cas:
            raise _PreconditionFailed()
        if kwargs.get("IfNoneMatch") == "*" and (key in self.objects or (
            key == self.marker_key and self.remote_manifest is not None
        )):
            raise _PreconditionFailed()
        self.puts.append((key, kwargs))
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.objects[key] = (body, dict(kwargs.get("Metadata") or {}))
        if key == self.marker_key:
            self.remote_manifest = json.loads(body.decode("utf-8"))


def _transcript() -> tuple[dict, str]:
    raw = gzip.decompress(TRANSCRIPT.read_bytes())
    payload = json.loads(raw.decode("utf-8"))
    return payload, canonical_body_sha256(payload)


def _index_payload(tx_sha: str) -> dict:
    return {
        "schema": "mastermind.tx-index/v1",
        "symbols": {"AAPL": ["2026Q3"]},
        "revisions": {LIVE_NARRATIVE_ALIAS: tx_sha},
        "dates": {LIVE_NARRATIVE_ALIAS: "2026-07-30"},
        "body_count": 1,
        "symbol_count": 1,
        "generated_at": "2026-08-16T23:51:18Z",
    }


def _submissions() -> dict:
    return {
        "cik": AAPL_CIK,
        "filings": {
            "recent": {
                "accessionNumber": [AAPL_ACCESSION],
                "filingDate": ["2026-07-30"],
                "acceptanceDateTime": ["2026-07-30T16:30:00.000Z"],
                "reportDate": ["2026-06-27"],
                "form": ["8-K"],
                "primaryDocument": ["aapl-20260730.htm"],
                "items": ["2.02,9.01"],
            }
        },
    }


def _headers_html() -> str:
    """Production EDGAR shape: HTML-escaped SGML inside index-headers.html."""
    return (
        "<HTML><HEAD><TITLE>SEC EDGAR Submission</TITLE></HEAD><BODY><PRE>"
        "&lt;DOCUMENT&gt;\n&lt;TYPE&gt;8-K\n"
        "&lt;FILENAME&gt;aapl-20260730.htm\n&lt;/DOCUMENT&gt;\n"
        f"&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n&lt;FILENAME&gt;{EXHIBIT_NAME}\n"
        "&lt;/DOCUMENT&gt;\n"
        "</PRE></BODY></HTML>"
    )


def test_html_escaped_index_headers_select_ex99_1() -> None:
    manifest = _parse_sgml_manifest(_headers_html())
    assert ("EX-99.1", EXHIBIT_NAME) in manifest
    assert _select_exhibit_99_1(manifest) == EXHIBIT_NAME
    # Literal split without unescape is the production miss from run 32039517591.
    raw = _headers_html()
    assert "<DOCUMENT>" not in raw
    assert "&lt;DOCUMENT&gt;" in raw


def _http_get_factory(exhibit_body: str | None = None):
    exhibit = (exhibit_body if exhibit_body is not None else EXHIBIT.read_text(encoding="utf-8")).encode("utf-8")
    submissions = json.dumps(_submissions()).encode("utf-8")
    headers = _headers_html().encode("utf-8")

    def http_get(url: str) -> tuple[int, bytes]:
        if url == SUBMISSIONS_URL:
            return 200, submissions
        if url == HEADERS_URL:
            return 200, headers
        if url == EXHIBIT_URL:
            return 200, exhibit
        return 404, b""

    return http_get


def _tx_fetchers():
    payload, tx_sha = _transcript()
    index = _index_payload(tx_sha)

    def fetch_index(_base: str) -> dict:
        return index

    def fetch_body(_base: str, ref: TranscriptRef) -> dict:
        if ref.pair != LIVE_NARRATIVE_ALIAS:
            raise ValueError(f"unexpected pair {ref.pair}")
        if ref.body_sha256 != tx_sha:
            raise ValueError(f"transcript body hash mismatch: {ref.body_sha256}")
        return payload

    return fetch_index, fetch_body, tx_sha


def _refresh(tmp_path: Path, fake: _FakeR2, **kwargs):
    fetch_index, fetch_body, _tx_sha = _tx_fetchers()
    return refresh(
        tmp_path,
        out_dir=tmp_path,
        http_get=kwargs.get("http_get", _http_get_factory()),
        fetch_index=fetch_index,
        fetch_body_fn=fetch_body,
        prior_workspace=kwargs.get("prior_workspace"),
        # NEW-4 fix (Opus red-team verification round 3, 2026-08-23),
        # BLOCKER-2 architecture (2026-08-23): these tests are AAPL-
        # flagship-focused and never stub homebuilder SEC responses at all,
        # so every homebuilder discovery fails here by construction —
        # refresh() now looks up a carry-forward prior on every such
        # failure, and the REAL default (load_prior_workspace_for_ticker)
        # makes a genuine network call against production R2 ("No
        # network." is this file's own law). The carry-forward loader
        # defaults here to an explicit offline stub returning None (no
        # prior — the pre-existing implicit behavior every test in this
        # file already relies on); a test that wants to exercise carry-
        # forward passes its own stub explicitly.
        homebuilder_carry_forward_loader=kwargs.get("homebuilder_carry_forward_loader", lambda ticker: None),
        publish_generation=lambda out_dir, dry_run=False: publish_event_workspaces(
            out_dir, dry_run=dry_run, s3=fake, bucket="bucket"
        ),
        dry_run=kwargs.get("dry_run", False),
        # IMCE A5C: this file's universe is a fresh sandboxed nest with no
        # real predecessor to fetch (and "No network." is this file's own
        # law — see the homebuilder loaders above) — default to "no
        # predecessor, no additional discovered revisions" unless a test
        # explicitly wants to exercise the chain/discovery machinery.
        current_marker_loader=kwargs.get("current_marker_loader", lambda: None),
        homebuilder_discovery=kwargs.get("homebuilder_discovery", lambda ticker, **_kw: []),
    )


def _marker(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "event_workspaces" / "manifest.json").read_text(encoding="utf-8"))


def test_same_source_revisions_are_semantic_noop(tmp_path: Path) -> None:
    """IMCE A5C two-clock law (C3, first-observation persistence): the
    second refresh passes the FIRST cycle's own published AAPL workspace as
    ``prior_workspace`` (mirroring test_source_sha_correction_advances_
    generation_and_lifecycle below) so observed_at is correctly carried
    forward rather than re-stamped at the second call's wall-clock 'now' —
    an unchanged source revision must reproduce the IDENTICAL generation,
    never a merely-content-equal one with a drifted first-observation clock.
    """
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    first = _marker(tmp_path)
    first_puts = list(fake.puts)
    assert first_puts[-1][0] == WS_MARKER
    assert V1_MARKER not in [key for key, _ in first_puts]
    first_aapl_prior = json.loads(
        (tmp_path / "event_workspaces" / "generations" / first["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert _refresh(tmp_path, fake, prior_workspace=first_aapl_prior) == 0
    second = _marker(tmp_path)
    assert first["generation_id"] == second["generation_id"]
    assert first["generated_at"] == ACCEPTANCE
    assert second["generated_at"] == ACCEPTANCE
    assert [key for key, _ in fake.puts[len(first_puts):]] == []


def test_source_sha_correction_advances_generation_and_lifecycle(tmp_path: Path) -> None:
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    first = _marker(tmp_path)
    prior = json.loads(
        (tmp_path / "event_workspaces" / "generations" / first["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    mutated = EXHIBIT.read_text(encoding="utf-8") + "\n<!-- source correction -->\n"
    assert _refresh(tmp_path, fake, http_get=_http_get_factory(mutated), prior_workspace=prior) == 0
    second = _marker(tmp_path)
    assert second["generation_id"] != first["generation_id"]
    workspace = json.loads(
        (tmp_path / "event_workspaces" / "generations" / second["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert workspace["event_id"] == FLAGSHIP_EVENT_ID
    assert workspace["lifecycle"]["state"] == "corrected"
    assert fake.puts[-1][0] == WS_MARKER


def test_corrected_lifecycle_state_is_sticky_across_an_unchanged_source_rebuild(tmp_path: Path) -> None:
    """A5C BLOCKER-1 (Opus red-team, 2026-08-23): a corrected event must STAY
    corrected in every later generation whose source hash is unchanged.
    Before the fix, an unchanged-source rebuild after a correction silently
    walked lifecycle.state back to "complete" (started -> complete only,
    since prior_source_sha256 == the new sha) — a byte-different, spuriously
    new generation that IMCE A5C's fail-closed gate would then read as
    safe-original within one 3-hour republish cycle. After the fix, the
    THIRD refresh (same mutated source as the correction, prior = the
    corrected workspace) reproduces the corrected generation byte-for-byte:
    same generation_id, lifecycle.state stays "corrected", zero new writes."""
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    first = _marker(tmp_path)
    prior = json.loads(
        (tmp_path / "event_workspaces" / "generations" / first["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    mutated = EXHIBIT.read_text(encoding="utf-8") + "\n<!-- source correction -->\n"
    assert _refresh(tmp_path, fake, http_get=_http_get_factory(mutated), prior_workspace=prior) == 0
    second = _marker(tmp_path)
    assert second["generation_id"] != first["generation_id"]
    second_workspace = json.loads(
        (tmp_path / "event_workspaces" / "generations" / second["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert second_workspace["lifecycle"]["state"] == "corrected"
    puts_after_second = list(fake.puts)

    # THIRD refresh: same (still-mutated) source, prior = the just-published
    # corrected workspace. Before the fix this would re-derive "complete".
    assert _refresh(tmp_path, fake, http_get=_http_get_factory(mutated), prior_workspace=second_workspace) == 0
    third = _marker(tmp_path)
    assert third["generation_id"] == second["generation_id"], "sticky-corrected rebuild must be byte-stable"
    third_workspace = json.loads(
        (tmp_path / "event_workspaces" / "generations" / third["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert third_workspace["lifecycle"]["state"] == "corrected"
    assert [key for key, _ in fake.puts[len(puts_after_second):]] == []


# ---------------------------------------------------------------------------
# NEW-1 (Opus red-team verification round 2, 2026-08-23): load_prior_workspace
# was fail-soft on EVERY error — a clean 404 and a timeout/5xx/malformed-JSON
# both returned None, so one transient HTTP failure on the prior read made
# prior_lifecycle_state=None AND prior_source_sha256=None, walking the
# rebuild started->complete and silently, PERMANENTLY erasing a sticky
# "corrected" state (the de-corrected workspace becomes the new prior on the
# next cycle). Fixed: load_prior_workspace now RAISES
# PriorWorkspaceFetchFailed on a genuine fetch failure; only a clean
# not-published 404 (_PriorWorkspaceNotPublished, internal) returns None.
# ---------------------------------------------------------------------------

def test_load_prior_workspace_raises_on_genuine_fetch_failure(capsys) -> None:
    """Unit-level: any failure OTHER than a clean not-published 404 raises
    PriorWorkspaceFetchFailed, never returns None, and emits a line-start
    ::warning naming the event and the error class."""

    def boom(event_id: str) -> dict:
        raise TimeoutError("connection timed out")

    with pytest.raises(PriorWorkspaceFetchFailed):
        load_prior_workspace("evt_boom", fetch=boom)

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert any(line.startswith("::warning title=event-workspace-prior-fetch-failed::") for line in lines), out
    warning_line = next(line for line in lines if line.startswith("::warning title=event-workspace-prior-fetch-failed::"))
    assert "evt_boom" in warning_line
    assert "TimeoutError" in warning_line


def test_load_prior_workspace_returns_none_on_clean_not_published(capsys) -> None:
    """Unit-level: a clean not-published disposition still returns None
    (first-generation behavior unchanged) and emits NO fetch-failed warning."""

    def not_found(event_id: str) -> dict:
        raise _PriorWorkspaceNotPublished("manifest 404")

    assert load_prior_workspace("evt_absent", fetch=not_found) is None
    out = capsys.readouterr().out
    assert "event-workspace-prior-fetch-failed" not in out


def test_load_prior_workspace_returns_the_workspace_on_a_hit() -> None:
    payload = {"event_id": "evt_x", "lifecycle": {"state": "complete"}}
    assert load_prior_workspace("evt_x", fetch=lambda eid: payload) == payload


class _FakeRequestsResponse:
    def __init__(self, *, status_code: int, payload: object = None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400 and self.status_code != 404:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self._payload


def _as_fetch_bytes(url_handler):
    """MAJOR-7: the shared reader's producer-facing primitives now route
    through the ONE hardened ``reader._fetch_bytes`` helper (context-
    manager/streaming/allow_404 contract), not a plain ``requests.get``.
    This adapts an existing (pre-MAJOR-7) ``url_handler(url) ->
    _FakeRequestsResponse``-shaped test stub into ``_fetch_bytes``'s own
    ``(url, *, limit, allow_404=False) -> bytes | None`` contract, so every
    existing test below keeps its OWN url-routing logic byte-for-byte —
    only the monkeypatch target and the response-to-bytes translation move.
    """
    def fake_fetch_bytes(url: str, *, limit: int, allow_404: bool = False) -> bytes | None:
        response = url_handler(url)
        if response.status_code == 404:
            if allow_404:
                return None
            raise reader.CompanyIntelligenceReadError(f"404: {url}")
        response.raise_for_status()
        return json.dumps(response.json()).encode("utf-8")

    return fake_fetch_bytes


def test_load_prior_workspace_for_ticker_matches_by_company_id_scan(monkeypatch) -> None:
    """NEW-4 (Opus red-team verification round 3, 2026-08-23): direct
    unit-level proof that load_prior_workspace_for_ticker's own
    generation-manifest scan works — it must find DHI's event via
    parse_canonical_event_id's company_id, WITHOUT knowing this cycle's
    fresh event_id at all, fetching only the ONE matching workspace body
    (never the AAPL one), and return None for a ticker with no entry in
    the current generation."""
    base = "https://example.test/company_intelligence"
    dhi_event_id = "evt_cik0000882184_2026q3_results"
    aapl_event_id = FLAGSHIP_EVENT_ID
    dhi_payload = {"event_id": dhi_event_id, "lifecycle": {"state": "corrected"}}
    aapl_payload = {"event_id": aapl_event_id, "lifecycle": {"state": "complete"}}
    gen_manifest = {
        "files": {
            f"workspaces/{aapl_event_id}.json": {"bytes": 10, "sha256": "a" * 64},
            f"workspaces/{dhi_event_id}.json": {"bytes": 10, "sha256": "b" * 64},
        },
    }
    fetched_workspace_urls: list[str] = []

    def fake_get(url: str, *, headers=None, timeout=None):
        if url == f"{base}/event_workspaces/manifest.json":
            return _FakeRequestsResponse(status_code=200, payload={"generation_id": "GEN1"})
        if url == f"{base}/event_workspaces/generations/GEN1/manifest.json":
            return _FakeRequestsResponse(status_code=200, payload=gen_manifest)
        if url == f"{base}/event_workspaces/generations/GEN1/workspaces/{dhi_event_id}.json":
            fetched_workspace_urls.append(url)
            return _FakeRequestsResponse(status_code=200, payload=dhi_payload)
        if url == f"{base}/event_workspaces/generations/GEN1/workspaces/{aapl_event_id}.json":
            fetched_workspace_urls.append(url)
            return _FakeRequestsResponse(status_code=200, payload=aapl_payload)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(reader, "_fetch_bytes", _as_fetch_bytes(fake_get))
    result = load_prior_workspace_for_ticker("DHI", base_url=base)
    assert result == dhi_payload
    # Only DHI's own workspace body was ever fetched — never AAPL's, proving
    # the scan reads the generation manifest's event_id list (cheap) and
    # fetches ONLY the matched body (not every workspace in the generation).
    assert fetched_workspace_urls == [f"{base}/event_workspaces/generations/GEN1/workspaces/{dhi_event_id}.json"]

    # A ticker with no entry in the current generation returns None (never
    # published yet, not a failure).
    assert load_prior_workspace_for_ticker("PHM", base_url=base) is None


def test_load_prior_workspace_for_ticker_raises_on_genuine_fetch_failure(monkeypatch, capsys) -> None:
    def fake_get(url: str, *, headers=None, timeout=None):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(reader, "_fetch_bytes", _as_fetch_bytes(fake_get))
    with pytest.raises(PriorWorkspaceFetchFailed):
        load_prior_workspace_for_ticker("DHI", base_url="https://example.test/company_intelligence")
    out = capsys.readouterr().out
    assert any(line.startswith("::warning title=event-workspace-prior-fetch-failed::") for line in out.splitlines())


def test_load_prior_workspace_for_ticker_returns_none_when_no_generation_exists(monkeypatch) -> None:
    def fake_get(url: str, *, headers=None, timeout=None):
        return _FakeRequestsResponse(status_code=404)

    monkeypatch.setattr(reader, "_fetch_bytes", _as_fetch_bytes(fake_get))
    assert load_prior_workspace_for_ticker("DHI", base_url="https://example.test/company_intelligence") is None


# ---------------------------------------------------------------------------
# NEW-6 (Opus red-team verification round 4, 2026-08-23): 8-case probe
# table. write_workspace_generation uploads every workspace object, THEN
# the generation's own manifest.json, and only THEN promotes the top-level
# marker to point at it — so once the top-level marker names a
# generation_id, that generation's manifest existing, being an object, and
# carrying a "files" key are all GUARANTEED by the publish protocol unless
# something is genuinely broken. None is correct ONLY for a clean
# top-level marker 404 (no nest yet) and a well-formed files map with no
# entry for this issuer; every other outcome below is an ANOMALY and must
# raise PriorWorkspaceFetchFailed, never be read as "nothing to carry".
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marker_behavior,gen_behavior,expected", [
    ("404", None, "none"),                    # (i) clean top-level 404: no nest yet
    ("error", None, "raise"),                  # marker read: genuine network failure
    ("no_generation_id", None, "raise"),        # marker parses but carries no generation_id
    ("ok", "404", "raise"),                     # (a) generation's own manifest 404s
    ("ok", "error", "raise"),                   # generation manifest read: genuine network failure
    ("ok", "not_mapping", "raise"),              # (b) generation manifest payload is not an object
    ("ok", "no_files", "raise"),                 # (c) generation manifest carries no "files" key
    ("ok", "no_match", "none"),                  # (ii) well-formed, no entry for this issuer
], ids=[
    "marker_404_no_nest_yet",
    "marker_network_error",
    "marker_missing_generation_id",
    "gen_manifest_404",
    "gen_manifest_network_error",
    "gen_manifest_not_an_object",
    "gen_manifest_missing_files_key",
    "well_formed_no_entry_for_issuer",
])
def test_load_prior_workspace_for_ticker_probe_table(monkeypatch, capsys, marker_behavior, gen_behavior, expected):
    base = "https://example.test/company_intelligence"

    def fake_get(url: str, *, headers=None, timeout=None):
        if url == f"{base}/event_workspaces/manifest.json":
            if marker_behavior == "404":
                return _FakeRequestsResponse(status_code=404)
            if marker_behavior == "error":
                raise TimeoutError("connection timed out")
            if marker_behavior == "no_generation_id":
                return _FakeRequestsResponse(status_code=200, payload={})
            return _FakeRequestsResponse(status_code=200, payload={"generation_id": "GEN1"})
        if url == f"{base}/event_workspaces/generations/GEN1/manifest.json":
            if gen_behavior == "404":
                return _FakeRequestsResponse(status_code=404)
            if gen_behavior == "error":
                raise TimeoutError("connection timed out")
            if gen_behavior == "not_mapping":
                return _FakeRequestsResponse(status_code=200, payload=["not", "a", "dict"])
            if gen_behavior == "no_files":
                return _FakeRequestsResponse(status_code=200, payload={"schema": "event_workspace_manifest.v1"})
            if gen_behavior == "no_match":
                return _FakeRequestsResponse(status_code=200, payload={
                    "files": {f"workspaces/{FLAGSHIP_EVENT_ID}.json": {"bytes": 1, "sha256": "a" * 64}},
                })
            raise AssertionError(f"unhandled gen_behavior {gen_behavior!r}")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(reader, "_fetch_bytes", _as_fetch_bytes(fake_get))
    if expected == "none":
        assert load_prior_workspace_for_ticker("DHI", base_url=base) is None
    else:
        with pytest.raises(PriorWorkspaceFetchFailed):
            load_prior_workspace_for_ticker("DHI", base_url=base)
        out = capsys.readouterr().out
        assert any(line.startswith("::warning title=event-workspace-prior-fetch-failed::") for line in out.splitlines())


def test_load_prior_workspace_for_ticker_selects_the_newest_fiscal_period_on_a_double_match(monkeypatch) -> None:
    """NEW-7 (Opus red-team verification round 4, 2026-08-23): files
    iterates in the manifest's own sorted-string key order, so a plain
    first-match would pick the LEXICOGRAPHICALLY SMALLEST (= OLDEST fiscal
    period) if the one-event-per-issuer invariant ever breaks. Two DHI
    events (Q2 and Q3) coexist in one generation here — the newer (Q3)
    must win, never the older (Q2) despite sorting first as a string."""
    base = "https://example.test/company_intelligence"
    dhi_q2_event_id = "evt_cik0000882184_2026q2_results"
    dhi_q3_event_id = "evt_cik0000882184_2026q3_results"
    dhi_q2_payload = {"event_id": dhi_q2_event_id, "lifecycle": {"state": "complete"}}
    dhi_q3_payload = {"event_id": dhi_q3_event_id, "lifecycle": {"state": "corrected"}}
    assert dhi_q2_event_id < dhi_q3_event_id, "fixture must sort Q2 first lexicographically"

    def fake_get(url: str, *, headers=None, timeout=None):
        if url == f"{base}/event_workspaces/manifest.json":
            return _FakeRequestsResponse(status_code=200, payload={"generation_id": "GEN1"})
        if url == f"{base}/event_workspaces/generations/GEN1/manifest.json":
            return _FakeRequestsResponse(status_code=200, payload={"files": {
                f"workspaces/{dhi_q2_event_id}.json": {"bytes": 1, "sha256": "a" * 64},
                f"workspaces/{dhi_q3_event_id}.json": {"bytes": 1, "sha256": "b" * 64},
            }})
        if url == f"{base}/event_workspaces/generations/GEN1/workspaces/{dhi_q3_event_id}.json":
            return _FakeRequestsResponse(status_code=200, payload=dhi_q3_payload)
        if url == f"{base}/event_workspaces/generations/GEN1/workspaces/{dhi_q2_event_id}.json":
            raise AssertionError("must never fetch the OLDER event's body")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(reader, "_fetch_bytes", _as_fetch_bytes(fake_get))
    assert load_prior_workspace_for_ticker("DHI", base_url=base) == dhi_q3_payload


def test_prior_fetch_failure_never_erases_a_corrected_lifecycle_state(tmp_path: Path, capsys) -> None:
    """(a) THE NAMED FALSIFIER (verifier's own words): prior loader RAISES
    against an already-corrected event -> no publication for that event
    this cycle, warning emitted, marker not advanced with a de-corrected
    workspace. Exercised at the refresh() level via a callable prior_workspace
    that raises PriorWorkspaceFetchFailed (simulating what load_prior_workspace
    itself would raise after classifying a real network failure — the HTTP
    disposition classification itself is unit-tested above)."""
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    first = _marker(tmp_path)
    prior = json.loads(
        (tmp_path / "event_workspaces" / "generations" / first["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    mutated = EXHIBIT.read_text(encoding="utf-8") + "\n<!-- source correction -->\n"
    assert _refresh(tmp_path, fake, http_get=_http_get_factory(mutated), prior_workspace=prior) == 0
    second = _marker(tmp_path)
    assert second["generation_id"] != first["generation_id"]
    second_workspace = json.loads(
        (tmp_path / "event_workspaces" / "generations" / second["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert second_workspace["lifecycle"]["state"] == "corrected"
    puts_after_second = list(fake.puts)

    # THIRD refresh: the prior loader RAISES (simulating a transient outage
    # on the prior-workspace GET) instead of returning the corrected dict.
    def failing_prior_loader() -> dict:
        raise PriorWorkspaceFetchFailed("evt: simulated network timeout")

    with pytest.raises(RefreshError):
        _refresh(tmp_path, fake, http_get=_http_get_factory(mutated), prior_workspace=failing_prior_loader)

    third = _marker(tmp_path)
    assert third["generation_id"] == second["generation_id"], "marker must NOT advance with a de-corrected workspace"
    assert [key for key, _ in fake.puts[len(puts_after_second):]] == [], "nothing new published this cycle"
    third_workspace = json.loads(
        (tmp_path / "event_workspaces" / "generations" / third["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert third_workspace["lifecycle"]["state"] == "corrected", "the on-disk generation is unchanged, still corrected"


def test_prior_loader_absent_proceeds_as_first_generation_exactly_as_today(tmp_path: Path) -> None:
    """(b): a genuinely absent prior (not_published / None) still proceeds
    as first-generation build — unchanged regression, exercised both via
    load_prior_workspace's own disposition classification (unit-level,
    above) and here at the refresh() level with no prior at all."""
    fake = _FakeR2()
    assert _refresh(tmp_path, fake, prior_workspace=None) == 0
    marker = _marker(tmp_path)
    assert marker["generation_id"]
    workspace = json.loads(
        (tmp_path / "event_workspaces" / "generations" / marker["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert workspace["lifecycle"]["state"] == "complete"


def test_flagship_prior_loader_raising_a_bare_exception_also_aborts(tmp_path: Path) -> None:
    """NEW-5-PIN (Opus red-team verification round 4, 2026-08-23): the
    uniform flagship handler (NEW-5, round 3) merged two except branches
    into one so that NO exception of any type may mean first-generation —
    but that merge was UNPINNED: reverting to the round-3 two-handler
    shape (PriorWorkspaceFetchFailed -> abort, everything else -> fail-soft
    None) left the full suite green, because nothing exercised a NON-
    PriorWorkspaceFetchFailed exception from prior_workspace(). This pins
    it: a bare RuntimeError (deliberately NOT PriorWorkspaceFetchFailed)
    from the loader must still raise RefreshError and publish nothing."""
    fake = _FakeR2()

    def raising_prior_loader():
        raise RuntimeError("simulated non-PriorWorkspaceFetchFailed failure")

    with pytest.raises(RefreshError):
        _refresh(tmp_path, fake, prior_workspace=raising_prior_loader)
    assert not (tmp_path / "event_workspaces" / "manifest.json").exists()
    assert fake.puts == []


def test_missing_transcript_hash_does_not_move_marker(tmp_path: Path) -> None:
    fake = _FakeR2()
    payload, tx_sha = _transcript()

    def fetch_index(_base: str) -> dict:
        return _index_payload(tx_sha)

    def fetch_body(_base: str, ref: TranscriptRef) -> dict:
        raise ValueError(f"transcript body hash mismatch for {ref.pair}")

    with pytest.raises(RefreshError, match="unavailable"):
        refresh(
            tmp_path,
            out_dir=tmp_path,
            http_get=_http_get_factory(),
            fetch_index=fetch_index,
            fetch_body_fn=fetch_body,
            publish_generation=lambda *args, **kwargs: 0,
        )
    assert not (tmp_path / "event_workspaces" / "manifest.json").exists()
    assert fake.puts == []


def test_sec_unavailable_does_not_move_marker(tmp_path: Path) -> None:
    fake = _FakeR2()
    fetch_index, fetch_body, _tx_sha = _tx_fetchers()

    def http_get(_url: str) -> tuple[int, bytes]:
        return 503, b"unavailable"

    with pytest.raises(RefreshError, match="submissions unavailable"):
        refresh(
            tmp_path,
            out_dir=tmp_path,
            http_get=http_get,
            fetch_index=fetch_index,
            fetch_body_fn=fetch_body,
            publish_generation=lambda *args, **kwargs: fake.puts.append(("called", {})) or 0,
        )
    assert fake.puts == []
    assert not (tmp_path / "event_workspaces" / "manifest.json").exists()


def test_workspace_publisher_is_marker_last_and_never_touches_v1(tmp_path: Path) -> None:
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    keys = [key for key, _ in fake.puts]
    assert keys[-1] == WS_MARKER
    assert keys[0].endswith(f"/workspaces/{FLAGSHIP_EVENT_ID}.json")
    assert keys[-2].endswith("/manifest.json")
    assert V1_MARKER not in keys
    workspace = json.loads(
        (tmp_path / "event_workspaces" / "generations" / _marker(tmp_path)["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text(encoding="utf-8")
    )
    assert workspace["issuer"]["company_id"].endswith(AAPL_CIK)
    assert workspace["completeness"]["filing"]["filing_key"]["accession"] == AAPL_ACCESSION
    assert workspace["completeness"]["release"]["status"] == "present"
    assert workspace["completeness"]["transcript"]["status"] == "present"
    assert workspace["completeness"]["consensus"]["status"] == "unlicensed"
    assert workspace["completeness"]["slides"]["status"] == "absent"
    assert workspace["completeness"]["reaction"]["status"] == "not_joined"
    assert all(fact.get("fact_id") != "fact_questions_count" for fact in workspace["facts"])
    assert len(workspace.get("qa_exchanges") or []) == 7
    assert all(item.get("topics") == ["unavailable"] for item in workspace["qa_exchanges"])
    assert workspace["authority"] == "context_only"
    assert workspace["prophet_flags"] == {
        "may_rank": False,
        "may_size": False,
        "may_gate": False,
        "prophet_authority": False,
    }
    assert all("beat" not in delta and "miss" not in delta for delta in workspace["deltas"])
    assert all(delta.get("basis_match") is False for delta in workspace["deltas"])


def test_workspace_cas_loss_returns_conflict_without_claiming_win(tmp_path: Path) -> None:
    built = _FakeR2()
    assert _refresh(tmp_path, built) == 0
    local = _marker(tmp_path)
    fake = _FakeR2(remote_manifest={"schema": "event_workspace_manifest.v1", "generation_id": "0" * 24}, conflict_on_cas=True)
    assert publish_event_workspaces(tmp_path, s3=fake, bucket="bucket") == PUBLISH_CONFLICT
    assert WS_MARKER not in [key for key, _ in fake.puts]
    assert local["generation_id"] != "0" * 24


def test_immutable_collision_fails_closed(tmp_path: Path) -> None:
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    marker = _marker(tmp_path)
    key = (
        f"company_intelligence/event_workspaces/generations/{marker['generation_id']}"
        f"/workspaces/{FLAGSHIP_EVENT_ID}.json"
    )
    colliding = _FakeR2(objects={key: (b"not-the-workspace", {"sha256": sha256(b"not-the-workspace").hexdigest()})})
    assert publish_event_workspaces(tmp_path, s3=colliding, bucket="bucket") == 1
    assert WS_MARKER not in [written for written, _ in colliding.puts]


def test_v1_publish_ignores_the_sibling_nest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeR2(marker_key=V1_MARKER)
    assert _refresh(tmp_path, _FakeR2()) == 0
    (tmp_path / "manifest.json").write_text(json.dumps({
        "schema": "company_intelligence_manifest.v1",
        "status": "ready",
        "generation_id": "a" * 24,
        "company_count": 1,
        "event_count": 1,
        "files": {},
        "warnings": [],
    }), encoding="utf-8")
    monkeypatch.setattr(
        "scripts.publish_company_intelligence_r2.validate_generation",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "generation_id": "a" * 24,
            "company_count": 1,
            "event_count": 1,
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "scripts.publish_company_intelligence_r2.enforce_shrink_floor",
        lambda *_args, **_kwargs: (True, ""),
    )
    (tmp_path / "generations" / ("a" * 24) / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "generations" / ("a" * 24) / "manifest.json").write_bytes((tmp_path / "manifest.json").read_bytes())
    assert publish(tmp_path, s3=fake, bucket="bucket") == 0
    keys = [key for key, _ in fake.puts]
    assert keys[-1] == V1_MARKER
    assert WS_MARKER not in keys
    assert all("/event_workspaces/" not in key for key in keys)


def test_production_reader_observes_the_published_flagship(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    nest = tmp_path / "event_workspaces"
    origin = "https://company-intelligence.example/company_intelligence"

    def fetch(url: str, *, limit: int) -> bytes:
        del limit
        relative = url.split("/company_intelligence/", 1)[1]
        return (Path(tmp_path) / relative).read_bytes()

    monkeypatch.setattr(reader, "_public_base_url", lambda: origin)
    monkeypatch.setattr(reader, "_fetch_bytes", fetch)
    reader.clear_company_intelligence_cache()
    generation = json.loads((nest / "manifest.json").read_text(encoding="utf-8"))["generation_id"]
    for alias in (FLAGSHIP_EVENT_ID, LIVE_CIE_ALIAS, LIVE_NARRATIVE_ALIAS, LIVE_PUBLIC_SLUG):
        result = reader.read_event_workspace({"event_id": alias})
        assert result["available"] is True
        assert result["event_id"] == FLAGSHIP_EVENT_ID
        assert result["authority"] == "context_only"
        assert result["receipt"]["generation_id"] == generation


# ---------------------------------------------------------------------------
# IMCE A5C discovery (frozen spec B) — ALL not-yet-represented qualifying
# revisions, ascending SEC acceptance order, never only the newest.
# ---------------------------------------------------------------------------

_DHI_CIK = "0000882184"
_DHI_EXHIBIT = FIXTURES / "dhi_fy2026q3_ex99_1.htm"
_DHI_ORIGINAL_ACCESSION = "0000882184-26-000092"
_DHI_AMENDMENT_ACCESSION = "0000882184-26-000093"
_DHI_REPORT_DATE = "2026-07-21"


def _dhi_archive_base(accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(_DHI_CIK)}/{accession.replace('-', '')}"


def test_discover_new_homebuilder_revisions_publishes_original_and_amendment_in_order() -> None:
    """Mutation-kill (2): an original 8-K and its own 8-K/A amendment
    discovered in ONE poll are BOTH resolved, ASCENDING by SEC acceptance
    order — never only the newest (Sol item 3, "FORBIDDEN"). The amendment
    chains onto the freshly-built original (B3): its own prior_source_sha256
    is the original's sha, so it walks to lifecycle.state == "corrected"."""
    original_exhibit = _DHI_EXHIBIT.read_text(encoding="utf-8")
    amendment_exhibit = original_exhibit + "\n<!-- amendment restates a figure -->\n"
    exhibit_name = "dhi-ex991.htm"

    def http_get(url: str) -> tuple[int, bytes]:
        if url == f"https://data.sec.gov/submissions/CIK{_DHI_CIK}.json":
            return 200, json.dumps({
                "cik": _DHI_CIK,
                "filings": {"recent": {
                    # Deliberately listed NEWEST FIRST (as EDGAR's own feed
                    # order is not acceptance order) — discovery must still
                    # process them ascending.
                    "accessionNumber": [_DHI_AMENDMENT_ACCESSION, _DHI_ORIGINAL_ACCESSION],
                    "filingDate": ["2026-07-22", "2026-07-21"],
                    "acceptanceDateTime": ["2026-07-22T12:00:00.000Z", "2026-07-21T16:30:00.000Z"],
                    "reportDate": [_DHI_REPORT_DATE, _DHI_REPORT_DATE],
                    "form": ["8-K/A", "8-K"],
                    "primaryDocument": ["a.htm", "b.htm"],
                    "items": ["2.02", "2.02"],
                }},
            }).encode("utf-8")
        for accession, body in (
            (_DHI_ORIGINAL_ACCESSION, original_exhibit),
            (_DHI_AMENDMENT_ACCESSION, amendment_exhibit),
        ):
            base = _dhi_archive_base(accession)
            if url == f"{base}/{accession}-index-headers.html":
                return 200, (
                    "<HTML><BODY><PRE>&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n"
                    f"&lt;FILENAME&gt;{exhibit_name}\n&lt;/DOCUMENT&gt;\n</PRE></BODY></HTML>"
                ).encode("utf-8")
            if url == f"{base}/{exhibit_name}":
                return 200, body.encode("utf-8")
        return 404, b""

    def fetch_index(_base: str) -> dict:
        return {
            "schema": "mastermind.tx-index/v1", "symbols": {}, "revisions": {}, "dates": {},
            "body_count": 0, "symbol_count": 0, "generated_at": "2026-01-01T00:00:00Z",
        }

    def fetch_body(_base: str, _ref) -> dict:  # pragma: no cover — never called (no transcript)
        raise AssertionError("no transcript should be fetched in this test")

    revisions = discover_new_homebuilder_revisions(
        "DHI",
        http_get=http_get,
        fetch_index=fetch_index,
        fetch_body_fn=fetch_body,
        # B2: nothing represented yet in the chain -- both accessions are new.
        # MINOR-9 (Opus red-team verification round 2, 2026-08-23): the real
        # chain_state_loader contract is the FULL ordered timeline (a
        # list[dict], per _event_known_revisions) — never the pre-MINOR-9
        # "(represented_accessions, latest_workspace)" 2-tuple this stub
        # used to return.
        chain_state_loader=lambda event_id: [],
    )
    assert len(revisions) == 2
    (event_id_1, payload_1), (event_id_2, payload_2) = revisions
    assert event_id_1 == event_id_2  # same event, two revisions
    # Ascending acceptance order: the ORIGINAL comes first.
    accession_1 = payload_1["sources"][0]["filing_key"]["accession"]
    accession_2 = payload_2["sources"][0]["filing_key"]["accession"]
    assert accession_1 == _DHI_ORIGINAL_ACCESSION
    assert accession_2 == _DHI_AMENDMENT_ACCESSION
    # B3: the amendment chains onto the freshly-built original -- its
    # source_sha256 differs (the exhibit bytes differ), so it correctly
    # walks to "corrected".
    assert payload_1["lifecycle"]["state"] == "complete"
    assert payload_2["lifecycle"]["state"] == "corrected"
    # BLOCKER-3/MAJOR-4 (homebuilder-path clock separation): a genuinely
    # NEW revision's observed_at is the REAL wall-clock at discovery time —
    # not silently equal to the SEC acceptance clock, for EITHER revision.
    for payload, fixture_acceptance in (
        (payload_1, "2026-07-21T16:30:00Z"), (payload_2, "2026-07-22T12:00:00Z"),
    ):
        assert payload["lifecycle"]["source_available_at"] == fixture_acceptance
        assert payload["lifecycle"]["observed_at"] != fixture_acceptance
        assert payload["lifecycle"]["observed_at"] > fixture_acceptance  # C4: never precedes it


def test_discover_new_homebuilder_revisions_skips_already_represented_accessions() -> None:
    """B2: an accession already present in the chain history is never
    reprocessed — only the amendment (genuinely new) is returned."""
    original_exhibit = _DHI_EXHIBIT.read_text(encoding="utf-8")
    amendment_exhibit = original_exhibit + "\n<!-- amendment restates a figure -->\n"
    exhibit_name = "dhi-ex991.htm"

    def http_get(url: str) -> tuple[int, bytes]:
        if url == f"https://data.sec.gov/submissions/CIK{_DHI_CIK}.json":
            return 200, json.dumps({
                "cik": _DHI_CIK,
                "filings": {"recent": {
                    "accessionNumber": [_DHI_AMENDMENT_ACCESSION, _DHI_ORIGINAL_ACCESSION],
                    "filingDate": ["2026-07-22", "2026-07-21"],
                    "acceptanceDateTime": ["2026-07-22T12:00:00.000Z", "2026-07-21T16:30:00.000Z"],
                    "reportDate": [_DHI_REPORT_DATE, _DHI_REPORT_DATE],
                    "form": ["8-K/A", "8-K"],
                    "primaryDocument": ["a.htm", "b.htm"],
                    "items": ["2.02", "2.02"],
                }},
            }).encode("utf-8")
        for accession, body in (
            (_DHI_ORIGINAL_ACCESSION, original_exhibit),
            (_DHI_AMENDMENT_ACCESSION, amendment_exhibit),
        ):
            base = _dhi_archive_base(accession)
            if url == f"{base}/{accession}-index-headers.html":
                return 200, (
                    "<HTML><BODY><PRE>&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n"
                    f"&lt;FILENAME&gt;{exhibit_name}\n&lt;/DOCUMENT&gt;\n</PRE></BODY></HTML>"
                ).encode("utf-8")
            if url == f"{base}/{exhibit_name}":
                return 200, body.encode("utf-8")
        return 404, b""

    def fetch_index(_base: str) -> dict:
        return {
            "schema": "mastermind.tx-index/v1", "symbols": {}, "revisions": {}, "dates": {},
            "body_count": 0, "symbol_count": 0, "generated_at": "2026-01-01T00:00:00Z",
        }

    def fetch_body(_base: str, _ref) -> dict:  # pragma: no cover
        raise AssertionError("no transcript should be fetched in this test")

    revisions = discover_new_homebuilder_revisions(
        "DHI",
        http_get=http_get,
        fetch_index=fetch_index,
        fetch_body_fn=fetch_body,
        # The ORIGINAL accession is already represented; only the amendment
        # is genuinely new. MINOR-9: chain_state_loader returns the FULL
        # ordered timeline (list[dict]) — see the sibling test above.
        chain_state_loader=lambda event_id: [{
            "source_available_at": "2026-07-21T16:30:00Z",
            "workspace": _stub_dhi_revision(
                source_available_at="2026-07-21T16:30:00Z", source_sha256="a" * 64,
                accession=_DHI_ORIGINAL_ACCESSION,
            ),
        }],
    )
    assert len(revisions) == 1
    _event_id, payload = revisions[0]
    assert payload["sources"][0]["filing_key"]["accession"] == _DHI_AMENDMENT_ACCESSION


# ---------------------------------------------------------------------------
# PRODUCTION INCIDENT FIX (verification round 4, 2026-08-23): production
# run 32652474368 (workflow_dispatch) crawled each homebuilder's ENTIRE SEC
# "recent" submissions block back to 2010 — "not yet represented in the
# chain" alone admits all of history on first deploy. Sol's law is "all
# newly observed qualifying accessions SINCE THE CANONICAL PRIOR
# GENERATION" — discovery_boundary implements that temporal boundary,
# filtered on the raw submissions row BEFORE any per-accession HTTP fetch.
# ---------------------------------------------------------------------------

def test_discovery_boundary_excludes_at_or_older_rows_with_zero_per_accession_fetches() -> None:
    """A row AT OR OLDER than discovery_boundary is outside the discovery
    window BY LAW — filtered before ANY per-accession fetch (index-headers
    + exhibit) and without ever consulting chain_state_loader. This is the
    exact fetch pattern that timed out production run 32652474368 (~0.5s x
    hundreds of accessions back to 2010) — proven here to never happen for
    anything at-or-older than the boundary."""
    fetch_log: list[str] = []

    def http_get(url: str) -> tuple[int, bytes]:
        fetch_log.append(url)
        if url == f"https://data.sec.gov/submissions/CIK{_DHI_CIK}.json":
            return 200, json.dumps({
                "cik": _DHI_CIK,
                "filings": {"recent": {
                    "accessionNumber": [_DHI_ORIGINAL_ACCESSION],
                    "filingDate": [_DHI_REPORT_DATE],
                    "acceptanceDateTime": ["2026-07-21T16:30:00.000Z"],
                    "reportDate": [_DHI_REPORT_DATE],
                    "form": ["8-K"],
                    "primaryDocument": ["a.htm"],
                    "items": ["2.02"],
                }},
            }).encode("utf-8")
        return 404, b""  # any per-accession fetch here is a TEST FAILURE by construction

    def fetch_index(_base: str) -> dict:
        return {
            "schema": "mastermind.tx-index/v1", "symbols": {}, "revisions": {}, "dates": {},
            "body_count": 0, "symbol_count": 0, "generated_at": "2026-01-01T00:00:00Z",
        }

    def fetch_body(_base: str, _ref) -> dict:  # pragma: no cover
        raise AssertionError("no transcript should be fetched in this test")

    def raising_chain_state_loader(event_id: str):  # pragma: no cover
        raise AssertionError("chain_state_loader must never be consulted for an excluded row")

    revisions = discover_new_homebuilder_revisions(
        "DHI", http_get=http_get, fetch_index=fetch_index, fetch_body_fn=fetch_body,
        chain_state_loader=raising_chain_state_loader,
        # Exactly at the row's own acceptance — AT-OR-OLDER, excluded
        # (the law is STRICTLY newer, never "newer-or-equal").
        discovery_boundary="2026-07-21T16:30:00Z",
    )
    assert revisions == []
    assert len(fetch_log) == 1  # only the ONE submissions call — nothing else


def test_discovery_boundary_still_admits_a_genuinely_newer_amendment() -> None:
    """Forward corrections are unaffected by the boundary: an 8-K/A whose
    OWN acceptance_datetime is NEWER than discovery_boundary still
    qualifies and correctly chains onto the boundary-setting original via
    chain_state_loader — only the already-represented, at-the-boundary
    original itself is excluded, with zero fetches for its own accession."""
    amendment_exhibit = _DHI_EXHIBIT.read_text(encoding="utf-8") + "\n<!-- amendment restates a figure -->\n"
    exhibit_name = "dhi-ex991.htm"
    fetch_log: list[str] = []

    def http_get(url: str) -> tuple[int, bytes]:
        fetch_log.append(url)
        if url == f"https://data.sec.gov/submissions/CIK{_DHI_CIK}.json":
            return 200, json.dumps({
                "cik": _DHI_CIK,
                "filings": {"recent": {
                    "accessionNumber": [_DHI_AMENDMENT_ACCESSION, _DHI_ORIGINAL_ACCESSION],
                    "filingDate": ["2026-07-22", _DHI_REPORT_DATE],
                    "acceptanceDateTime": ["2026-07-22T12:00:00.000Z", "2026-07-21T16:30:00.000Z"],
                    "reportDate": [_DHI_REPORT_DATE, _DHI_REPORT_DATE],
                    "form": ["8-K/A", "8-K"],
                    "primaryDocument": ["a.htm", "b.htm"],
                    "items": ["2.02", "2.02"],
                }},
            }).encode("utf-8")
        base = _dhi_archive_base(_DHI_AMENDMENT_ACCESSION)
        if url == f"{base}/{_DHI_AMENDMENT_ACCESSION}-index-headers.html":
            return 200, (
                "<HTML><BODY><PRE>&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n"
                f"&lt;FILENAME&gt;{exhibit_name}\n&lt;/DOCUMENT&gt;\n</PRE></BODY></HTML>"
            ).encode("utf-8")
        if url == f"{base}/{exhibit_name}":
            return 200, amendment_exhibit.encode("utf-8")
        return 404, b""  # the excluded original's own accession must never be fetched

    def fetch_index(_base: str) -> dict:
        return {
            "schema": "mastermind.tx-index/v1", "symbols": {}, "revisions": {}, "dates": {},
            "body_count": 0, "symbol_count": 0, "generated_at": "2026-01-01T00:00:00Z",
        }

    def fetch_body(_base: str, _ref) -> dict:  # pragma: no cover
        raise AssertionError("no transcript should be fetched in this test")

    original_ws = _stub_dhi_revision(
        source_available_at="2026-07-21T16:30:00Z", source_sha256="a" * 64, accession=_DHI_ORIGINAL_ACCESSION,
    )
    revisions = discover_new_homebuilder_revisions(
        "DHI", http_get=http_get, fetch_index=fetch_index, fetch_body_fn=fetch_body,
        chain_state_loader=lambda event_id: [
            {"source_available_at": "2026-07-21T16:30:00Z", "workspace": original_ws},
        ],
        discovery_boundary="2026-07-21T16:30:00Z",
    )
    assert len(revisions) == 1
    _event_id, payload = revisions[0]
    assert payload["sources"][0]["filing_key"]["accession"] == _DHI_AMENDMENT_ACCESSION
    assert payload["lifecycle"]["state"] == "corrected"
    original_nodash = _DHI_ORIGINAL_ACCESSION.replace("-", "")
    original_fetches = [u for u in fetch_log if original_nodash in u]
    assert original_fetches == [], f"the excluded original must never be per-accession-fetched, saw: {original_fetches}"


def test_discovery_boundary_none_bounds_first_publish_to_current_and_prior_fiscal_year() -> None:
    """No represented event yet for this issuer (discovery_boundary=None,
    genuine first-ever discovery) — bounded to the current + immediately
    prior fiscal year (mirrors scripts/build_cycle_pattern_imce_
    prospective.py's own bounded candidate lookback convention), never the
    whole recent block — the exact incident this fix closes. A row from
    2010 must produce ZERO per-accession fetches; only the in-window 2026
    row is resolved."""
    from datetime import date as _date

    old_accession = "0000882184-10-000005"
    exhibit_name = "dhi-ex991.htm"
    fetch_log: list[str] = []

    def http_get(url: str) -> tuple[int, bytes]:
        fetch_log.append(url)
        if url == f"https://data.sec.gov/submissions/CIK{_DHI_CIK}.json":
            return 200, json.dumps({
                "cik": _DHI_CIK,
                "filings": {"recent": {
                    "accessionNumber": [_DHI_ORIGINAL_ACCESSION, old_accession],
                    "filingDate": [_DHI_REPORT_DATE, "2010-07-21"],
                    "acceptanceDateTime": ["2026-07-21T16:30:00.000Z", "2010-07-21T16:05:00.000Z"],
                    "reportDate": [_DHI_REPORT_DATE, "2010-07-21"],
                    "form": ["8-K", "8-K"],
                    "primaryDocument": ["a.htm", "b.htm"],
                    "items": ["2.02", "2.02"],
                }},
            }).encode("utf-8")
        base = _dhi_archive_base(_DHI_ORIGINAL_ACCESSION)
        if url == f"{base}/{_DHI_ORIGINAL_ACCESSION}-index-headers.html":
            return 200, (
                "<HTML><BODY><PRE>&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n"
                f"&lt;FILENAME&gt;{exhibit_name}\n&lt;/DOCUMENT&gt;\n</PRE></BODY></HTML>"
            ).encode("utf-8")
        if url == f"{base}/{exhibit_name}":
            return 200, _DHI_EXHIBIT.read_text(encoding="utf-8").encode("utf-8")
        return 404, b""  # the 2010 row must never be per-accession-fetched here

    def fetch_index(_base: str) -> dict:
        return {
            "schema": "mastermind.tx-index/v1", "symbols": {}, "revisions": {}, "dates": {},
            "body_count": 0, "symbol_count": 0, "generated_at": "2026-01-01T00:00:00Z",
        }

    def fetch_body(_base: str, _ref) -> dict:  # pragma: no cover
        raise AssertionError("no transcript should be fetched in this test")

    revisions = discover_new_homebuilder_revisions(
        "DHI", http_get=http_get, fetch_index=fetch_index, fetch_body_fn=fetch_body,
        chain_state_loader=lambda event_id: [],
        discovery_boundary=None,
        today=_date(2026, 8, 23),
    )
    assert len(revisions) == 1
    _event_id, payload = revisions[0]
    assert payload["sources"][0]["filing_key"]["accession"] == _DHI_ORIGINAL_ACCESSION
    old_nodash = old_accession.replace("-", "")
    old_fetches = [u for u in fetch_log if old_nodash in u]
    assert old_fetches == [], f"a first-publish row outside current+prior fiscal year must never be fetched, saw: {old_fetches}"


def test_refresh_wires_the_carry_forward_boundary_into_real_discovery_convergence(tmp_path: Path) -> None:
    """Integration-level proof that refresh() ITSELF (not merely the unit-
    level discover_new_homebuilder_revisions) threads discovery_boundary
    from the SAME carry-forward read that seeds Phase 1's base snapshot —
    the exact wiring production run 32652474368 lacked. Uses the REAL
    discover_new_homebuilder_revisions (homebuilder_discovery is NOT
    stubbed off) against a DHI carry-forward whose own source_available_at
    is T and a submissions fixture whose only candidate row predates T:
    the cycle converges to ZERO new DHI revisions and ZERO per-accession
    fetches for that row — a normal quiet cycle, not a backfill."""
    fake = _FakeR2()
    current_dhi = _stub_dhi_revision(
        source_available_at="2026-07-21T16:30:00Z", source_sha256="a" * 64,
    )
    fetch_log: list[str] = []
    aapl_http_get = _http_get_factory()

    def combined_http_get(url: str) -> tuple[int, bytes]:
        fetch_log.append(url)
        if url == f"https://data.sec.gov/submissions/CIK{_DHI_CIK}.json":
            return 200, json.dumps({
                "cik": _DHI_CIK,
                "filings": {"recent": {
                    "accessionNumber": [_DHI_ORIGINAL_ACCESSION],
                    "filingDate": [_DHI_REPORT_DATE],
                    # AT the boundary — must be excluded (already the
                    # source of the boundary itself), never re-fetched.
                    "acceptanceDateTime": ["2026-07-21T16:30:00.000Z"],
                    "reportDate": [_DHI_REPORT_DATE],
                    "form": ["8-K"],
                    "primaryDocument": ["a.htm"],
                    "items": ["2.02"],
                }},
            }).encode("utf-8")
        return aapl_http_get(url)

    assert _refresh(
        tmp_path, fake,
        http_get=combined_http_get,
        homebuilder_carry_forward_loader=lambda ticker: current_dhi if ticker == "DHI" else None,
        # The REAL production default -- not a stub -- proving the actual
        # refresh()-to-discover() wiring, not just the unit-level function.
        homebuilder_discovery=discover_new_homebuilder_revisions,
    ) == 0

    marker = _marker(tmp_path)
    assert marker["event_count"] == 2  # AAPL flagship + DHI's carried-forward current state only
    dhi_event_id = current_dhi["event_id"]
    assert f"workspaces/{dhi_event_id}.json" in marker["files"]
    dhi_nodash = _DHI_ORIGINAL_ACCESSION.replace("-", "")
    dhi_fetches = [u for u in fetch_log if dhi_nodash in u]
    assert dhi_fetches == [], f"the boundary-setting DHI accession must never be re-fetched, saw: {dhi_fetches}"
    # Exactly ONE marker promotion this cycle (the closing write) — no
    # per-ticker chained write happened, because DHI produced zero new
    # revisions and PHM/KBH/TOL's submissions calls 404 (fail-soft, no
    # prior to carry).
    marker_puts = [key for key, _ in fake.puts if key == WS_MARKER]
    assert len(marker_puts) == 1


# ---------------------------------------------------------------------------
# MAJOR-5 (Opus red-team, 2026-08-23): refresh()-level multi-generation
# chaining was previously untested — every test above hard-stubs discovery
# off. These tests inject a real ``homebuilder_discovery`` stub returning
# MULTIPLE new revisions and verify refresh() itself publishes them as
# separate, correctly-chained, marker-last generations.
# ---------------------------------------------------------------------------

def _stub_dhi_revision(
    *, event_id: str = "evt_cik0000882184_2026q3_results",
    source_available_at: str, source_sha256: str, state: str = "complete",
    accession: str = "0000882184-26-000092",
) -> dict:
    """A minimal, contract-valid event_workspace.v1 body for DHI — mirrors
    tests/test_company_intelligence_workspace_chain.py's own ``_raw_workspace``
    shape (only the keys validate_event_workspace/this module's own reads
    care about are populated meaningfully)."""
    return {
        "schema": "event_workspace.v1",
        "event_id": event_id,
        "aliases": [],
        "issuer": {"company_id": "cik:0000882184", "display_name": "D.R. Horton, Inc.", "listings": []},
        "fiscal_period": {"year": 2026, "quarter": 3, "calendar_end": "2026-06-30"},
        "lifecycle": {"state": state, "observed_at": source_available_at, "source_available_at": source_available_at},
        "completeness": {},
        "facts": [], "deltas": [], "guidance": [], "claims": [],
        "sources": [{
            "kind": "issuer_release", "document_id": "doc:1",
            "filing_key": {"cik": "0000882184", "accession": accession},
            "source_sha256": source_sha256, "form": "8-K", "url": None,
            "receipt_state": "byte_replayed",
        }],
        "warnings": [],
        "generation_id": "",
        "generated_at": source_available_at,
        "authority": "context_only",
        "prophet_flags": {"may_rank": False, "may_size": False, "may_gate": False, "prophet_authority": False},
        "claim_citations_pending": False,
        "qa_exchanges": [],
    }


def test_refresh_publishes_original_and_amendment_as_two_chained_generations(tmp_path: Path) -> None:
    fake = _FakeR2()
    dhi_event_id = "evt_cik0000882184_2026q3_results"
    original = _stub_dhi_revision(
        source_available_at="2026-07-21T16:30:00Z", source_sha256="a" * 64,
        accession="0000882184-26-000092",
    )
    amendment = _stub_dhi_revision(
        source_available_at="2026-07-22T12:00:00Z", source_sha256="b" * 64, state="corrected",
        accession="0000882184-26-000093",
    )

    def stub_discovery(ticker: str, **_kwargs) -> list[tuple[str, dict]]:
        if ticker == "DHI":
            return [(dhi_event_id, original), (dhi_event_id, amendment)]
        return []

    assert _refresh(tmp_path, fake, homebuilder_discovery=stub_discovery) == 0

    marker_puts = [key for key, _ in fake.puts if key == WS_MARKER]
    # marker-last across BOTH chained generations: one promotion per
    # generation (B3's marker-promotion choice), never batched to one.
    assert len(marker_puts) == 2

    final_marker = _marker(tmp_path)
    dhi_final = json.loads(
        (tmp_path / "event_workspaces" / "generations" / final_marker["generation_id"]
         / "workspaces" / f"{dhi_event_id}.json").read_text(encoding="utf-8")
    )
    # MAJOR-6: the final published generation leaves DHI at its NEWEST
    # (amendment) revision — never regressed to the original.
    assert dhi_final["lifecycle"]["state"] == "corrected"
    assert dhi_final["sources"][0]["filing_key"]["accession"] == "0000882184-26-000093"

    # BOTH immutable generations remain independently addressable (the
    # original's own generation was never overwritten or skipped).
    all_generation_dirs = sorted((tmp_path / "event_workspaces" / "generations").iterdir())
    assert len(all_generation_dirs) == 2
    original_generation_id = next(
        gd.name for gd in all_generation_dirs if gd.name != final_marker["generation_id"]
    )
    dhi_original_recovered = json.loads(
        (tmp_path / "event_workspaces" / "generations" / original_generation_id
         / "workspaces" / f"{dhi_event_id}.json").read_text(encoding="utf-8")
    )
    assert dhi_original_recovered["lifecycle"]["state"] == "complete"
    assert dhi_original_recovered["sources"][0]["filing_key"]["accession"] == "0000882184-26-000092"

    # Chain bookkeeping: the amendment's own generation names the
    # original's generation_id as its predecessor.
    amendment_manifest = json.loads((tmp_path / "event_workspaces" / "generations" / final_marker["generation_id"] / "manifest.json").read_text(encoding="utf-8"))
    assert amendment_manifest["previous_generation_id"] == original_generation_id


def test_refresh_every_write_contains_every_resolved_ticker_before_any_write(tmp_path: Path) -> None:
    """NEW-BLOCKER-16 (Opus red-team verification round 2, 2026-08-23 —
    FROZEN FIX): a live verifier probe caught the single-pass per-ticker
    loop publishing a triggering ticker's own first chained write BEFORE a
    LATER-ordered ticker (PHM comes after DHI in HOMEBUILDER_TICKERS) had
    been carried forward into the running snapshot at all — marker
    generation 0 had a lower event_count with PHM silently ABSENT, only
    reaching the full count once PHM was later visited in the SAME cycle.
    refresh() must now resolve EVERY ticker (Phase 1) before writing
    ANYTHING (Phase 2), so DHI's own FIRST (and only) write this cycle
    already contains PHM's carried-forward state — never a transiently-
    incomplete nest, even for the very first generation minted."""
    fake = _FakeR2()
    dhi_event_id = "evt_cik0000882184_2026q3_results"
    phm_event_id = "evt_cik0000822416_2026q2_results"
    dhi_revision = _stub_dhi_revision(
        source_available_at="2026-07-21T16:30:00Z", source_sha256="a" * 64,
    )
    phm_current = _stub_dhi_revision(
        event_id=phm_event_id, source_available_at="2026-07-01T00:00:00Z", source_sha256="b" * 64,
        accession="0000822416-26-000030",
    )

    def stub_discovery(ticker: str, **_kwargs) -> list[tuple[str, dict]]:
        # DHI (first in HOMEBUILDER_TICKERS) is the ONLY triggering ticker
        # this cycle — the exact shape the original probe caught.
        if ticker == "DHI":
            return [(dhi_event_id, dhi_revision)]
        return []

    def carry_forward(ticker: str):
        return phm_current if ticker == "PHM" else None

    assert _refresh(
        tmp_path, fake, homebuilder_discovery=stub_discovery,
        homebuilder_carry_forward_loader=carry_forward,
    ) == 0

    # Exactly ONE generation is written this cycle (DHI is the only ticker
    # with a genuinely new revision) — assert its OWN manifest, at the
    # moment of that single write, already names every resolved ticker.
    all_generation_dirs = list((tmp_path / "event_workspaces" / "generations").iterdir())
    assert len(all_generation_dirs) == 1
    manifest = json.loads((all_generation_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {
        f"workspaces/{FLAGSHIP_EVENT_ID}.json",
        f"workspaces/{dhi_event_id}.json",
        f"workspaces/{phm_event_id}.json",
    }


def test_refresh_chains_onto_the_marker_raw_bytes_hash_not_a_reserialization(tmp_path: Path) -> None:
    """MINOR-23 (Opus red-team verification round 3, 2026-08-23): pins the
    NEW-MINOR-18 raw-bytes producer hash at the refresh()-level seam, not
    merely inside the reader primitive. current_marker_loader injects a
    (raw_bytes, parsed) pair whose raw_bytes is deliberately NOT
    canonical_json_bytes(parsed) — different whitespace/key order, exactly
    the kind of byte-for-byte divergence a real R2 object can carry
    relative to any local re-serialization of its own parsed contents.
    refresh()'s minted generation must chain onto sha256(raw_bytes) — never
    sha256(canonical_json_bytes(parsed))."""
    from engine.company_intelligence.contracts import canonical_json_bytes
    from engine.company_intelligence.event_workspace import MANIFEST_SCHEMA_V2

    fake = _FakeR2()
    parsed_marker = {
        "schema": MANIFEST_SCHEMA_V2,
        # An arbitrary, non-content-derived id: guarantees this cycle's
        # freshly-built AAPL payload can never coincidentally reproduce it
        # as a semantic no-op, so the closing write's no-op branch never
        # fires and chain_previous_sha (this test's actual target) is what
        # ends up in the minted manifest.
        "generation_id": "f" * 24,
        "generated_at": "2026-07-01T00:00:00Z",
        "authority": "context_only", "status": "ready", "event_count": 0, "files": {},
        "previous_generation_id": None, "previous_manifest_sha256": None,
    }
    non_canonical_raw_bytes = (
        b'{\n  "generation_id": "' + b"f" * 24 + b'",\n  "schema": "' + MANIFEST_SCHEMA_V2.encode() + b'",\n'
        b'  "generated_at": "2026-07-01T00:00:00Z", "authority": "context_only", "status": "ready",\n'
        b'  "event_count": 0, "files": {}, "previous_generation_id": null, "previous_manifest_sha256": null\n}\n'
    )
    canonical_bytes_of_parsed = canonical_json_bytes(parsed_marker)
    assert non_canonical_raw_bytes != canonical_bytes_of_parsed, "fixture must actually diverge from the canonical form"

    assert _refresh(
        tmp_path, fake,
        current_marker_loader=lambda: (non_canonical_raw_bytes, parsed_marker),
    ) == 0
    marker = _marker(tmp_path)
    minted_manifest = json.loads(
        (tmp_path / "event_workspaces" / "generations" / marker["generation_id"] / "manifest.json")
        .read_text(encoding="utf-8")
    )
    assert minted_manifest["previous_generation_id"] == "f" * 24
    assert minted_manifest["previous_manifest_sha256"] == sha256(non_canonical_raw_bytes).hexdigest()
    assert minted_manifest["previous_manifest_sha256"] != sha256(canonical_bytes_of_parsed).hexdigest()


def test_refresh_newest_already_represented_restores_current_state_without_a_new_write(tmp_path: Path) -> None:
    """B2 at the refresh() level: when discovery finds nothing new for a
    ticker, its CURRENT published state is still carried into the running
    snapshot (via the carry-forward loader) — no NEW generation is written
    for that ticker alone, but its slot is never dropped."""
    fake = _FakeR2()
    dhi_event_id = "evt_cik0000882184_2026q3_results"
    current_dhi = _stub_dhi_revision(
        source_available_at="2026-07-21T16:30:00Z", source_sha256="a" * 64,
    )

    def no_new_revisions(ticker: str, **_kwargs) -> list[tuple[str, dict]]:
        return []

    assert _refresh(
        tmp_path, fake, homebuilder_discovery=no_new_revisions,
        homebuilder_carry_forward_loader=lambda ticker: current_dhi if ticker == "DHI" else None,
    ) == 0
    marker = _marker(tmp_path)
    assert marker["event_count"] == 2
    assert f"workspaces/{dhi_event_id}.json" in marker["files"]


def test_refresh_mid_sequence_publish_failure_stops_before_any_out_of_order_write(tmp_path: Path) -> None:
    """MAJOR-5: if the SECOND of three chained generations fails to
    publish, refresh() must abort immediately — nothing after the failure
    point publishes, and the marker stays at whatever the FIRST successful
    write left it at (never skipping ahead to a later revision out of
    order)."""
    fake = _FakeR2()
    dhi_event_id = "evt_cik0000882184_2026q3_results"
    rev1 = _stub_dhi_revision(source_available_at="2026-05-01T00:00:00Z", source_sha256="a" * 64, accession="0000882184-26-000090")
    rev2 = _stub_dhi_revision(source_available_at="2026-06-01T00:00:00Z", source_sha256="b" * 64, accession="0000882184-26-000091")
    rev3 = _stub_dhi_revision(source_available_at="2026-07-01T00:00:00Z", source_sha256="c" * 64, accession="0000882184-26-000092")

    def three_revisions(ticker: str, **_kwargs) -> list[tuple[str, dict]]:
        if ticker == "DHI":
            return [(dhi_event_id, rev1), (dhi_event_id, rev2), (dhi_event_id, rev3)]
        return []

    fetch_index, fetch_body, _tx_sha = _tx_fetchers()
    publish_calls = {"n": 0}

    def flaky_publish(out_dir, dry_run=False):
        publish_calls["n"] += 1
        if publish_calls["n"] == 2:
            return 1  # a hard publish failure on the SECOND write
        return publish_event_workspaces(out_dir, dry_run=dry_run, s3=fake, bucket="bucket")

    with pytest.raises(RefreshError):
        refresh(
            tmp_path, out_dir=tmp_path, http_get=_http_get_factory(),
            fetch_index=fetch_index, fetch_body_fn=fetch_body,
            homebuilder_carry_forward_loader=lambda ticker: None,
            publish_generation=flaky_publish,
            current_marker_loader=lambda: None,
            homebuilder_discovery=three_revisions,
        )
    # Exactly two publish attempts were made (the first succeeded, the
    # second failed) — the third revision's write never happened.
    assert publish_calls["n"] == 2
    # The REMOTE marker (fake.remote_manifest — what is actually PUBLISHED;
    # write_workspace_generation's own local scratch file is unconditionally
    # overwritten by every attempt regardless of whether ITS publish
    # succeeds, so it is not the right artifact to assert "what's live"
    # against) still names the FIRST (successfully-published) revision —
    # never rev2 (whose publish failed) or rev3 (never attempted).
    assert fake.remote_manifest is not None
    published_generation_id = fake.remote_manifest["generation_id"]
    dhi_published = json.loads(
        (tmp_path / "event_workspaces" / "generations" / published_generation_id
         / "workspaces" / f"{dhi_event_id}.json").read_text(encoding="utf-8")
    )
    assert dhi_published["sources"][0]["filing_key"]["accession"] == "0000882184-26-000090"


# ---------------------------------------------------------------------------
# MINOR-11: a clock-injected no-prior semantic-no-op test — proves the
# no-op is deterministic by CONSTRUCTION (an explicitly injected,
# non-wall-clock observed_at carried forward via prior_observed_at), never
# by two real refresh() calls happening to land in the same wall-clock
# second. This is deliberately a DIRECT unit-level proof at
# build_event_workspace's own seam (the mechanism refresh() relies on),
# rather than a second full refresh() round-trip.
# ---------------------------------------------------------------------------

def test_semantic_noop_is_deterministic_by_injected_clock_not_same_second_luck() -> None:
    exhibit_body = EXHIBIT.read_text(encoding="utf-8")
    filing = {
        "cik": AAPL_CIK, "accession": AAPL_ACCESSION, "form": "8-K",
        "filing_date": "2026-07-30", "acceptance_datetime": ACCEPTANCE,
        "report_date": "2026-06-27", "exhibit_url": EXHIBIT_URL,
    }
    tx, tx_sha = _transcript()
    # Both deliberately fixed, non-"now" values, AFTER source_available_at
    # (C4 requires observed_at >= source_available_at) but otherwise
    # arbitrary — proving the no-op is clock-injection-driven, never
    # "two wall-clock calls happened to land in the same second".
    injected_observed_at = "2026-08-01T00:00:00Z"

    first = build_event_workspace(
        registry=apple_registry(), ticker="AAPL", asof=AAPL_CALL_DATE,
        fiscal_period=flagship_fiscal_period(), exhibit_body=exhibit_body,
        filing=filing, transcript=tx, transcript_sha256=tx_sha,
        observed_at=injected_observed_at, source_available_at=ACCEPTANCE,
        prior_source_sha256=None, prior_lifecycle_state=None, prior_observed_at=None,
    )
    # A SECOND build, requesting a DIFFERENT (also non-"now") observed_at,
    # but with prior_source_sha256/prior_observed_at correctly carried
    # forward from the first — C3 must ignore the freshly-REQUESTED clock
    # entirely and reproduce the FIRST build's observed_at exactly.
    second = build_event_workspace(
        registry=apple_registry(), ticker="AAPL", asof=AAPL_CALL_DATE,
        fiscal_period=flagship_fiscal_period(), exhibit_body=exhibit_body,
        filing=filing, transcript=tx, transcript_sha256=tx_sha,
        observed_at="2026-09-01T00:00:00Z", source_available_at=ACCEPTANCE,
        prior_source_sha256=first["_source_sha256"],
        prior_lifecycle_state=first["lifecycle"]["state"],
        prior_observed_at=first["lifecycle"]["observed_at"],
    )
    assert second["lifecycle"]["observed_at"] == injected_observed_at == first["lifecycle"]["observed_at"]
    # Content-address stability follows directly: byte-identical bodies
    # (module content, excluding the generation_id/generated_at
    # write_workspace_generation always re-stamps) prove the no-op holds.
    def _content(payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k not in ("generation_id", "generated_at")}
    assert _content(first) == _content(second)
