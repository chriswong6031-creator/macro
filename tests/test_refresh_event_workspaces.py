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
    AAPL_CIK,
    FLAGSHIP_EVENT_ID,
    LIVE_CIE_ALIAS,
    LIVE_NARRATIVE_ALIAS,
    LIVE_PUBLIC_SLUG,
    write_workspace_generation,
)
from engine.earnings_transcript_intake import TranscriptRef, canonical_body_sha256
from engine.neuralweb import company_intelligence_reader as reader
from scripts.publish_company_intelligence_r2 import PUBLISH_CONFLICT, publish, publish_event_workspaces
from scripts.refresh_event_workspaces import (
    PriorWorkspaceFetchFailed,
    RefreshError,
    _parse_sgml_manifest,
    _PriorWorkspaceNotPublished,
    _select_exhibit_99_1,
    load_prior_workspace,
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
        publish_generation=lambda out_dir, dry_run=False: publish_event_workspaces(
            out_dir, dry_run=dry_run, s3=fake, bucket="bucket"
        ),
        dry_run=kwargs.get("dry_run", False),
    )


def _marker(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "event_workspaces" / "manifest.json").read_text(encoding="utf-8"))


def test_same_source_revisions_are_semantic_noop(tmp_path: Path) -> None:
    fake = _FakeR2()
    assert _refresh(tmp_path, fake) == 0
    first = _marker(tmp_path)
    first_puts = list(fake.puts)
    assert first_puts[-1][0] == WS_MARKER
    assert V1_MARKER not in [key for key, _ in first_puts]
    assert _refresh(tmp_path, fake) == 0
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
    questions = next(fact for fact in workspace["facts"] if fact["fact_id"] == "fact_questions_count")
    assert "typed_absence" in questions
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
