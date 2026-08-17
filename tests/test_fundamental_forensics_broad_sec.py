"""FF-1 incremental broad SEC source plane — acceptance and failure contracts."""
from __future__ import annotations

import gzip
import json
import re
from hashlib import sha256
from pathlib import Path

import jsonschema
import pandas as pd
import pytest
import requests

from collectors.edgar_forensics import SecForensicsCollector, endpoint_url
from engine.fundamental_forensics.broad_sec_store import (
    PREFIX,
    BroadSecError,
    PollClocks,
    count_source_objects,
    issuer_latest_key,
    issuer_manifest_key,
    latest_complete_key,
    latest_observation_key,
    load_universe,
    object_key,
    run_broad_sec_poll,
)
from engine.research_vault.r2_store import LocalStore
from scripts.run_fundamental_forensics_broad_sec import main as broad_sec_main


ROOT = Path(__file__).resolve().parents[1]
RUN_SCHEMA = json.loads(
    (ROOT / "contracts/fundamental_forensics_broad_sec_run.schema.json").read_text()
)
MANIFEST_SCHEMA = json.loads(
    (ROOT / "contracts/fundamental_forensics_broad_sec_issuer_manifest.schema.json").read_text()
)

AAPL = ("AAPL", "0000320193")
MSFT = ("MSFT", "0000789019")
POLL_1 = "2026-08-17T03:00:00Z"
POLL_1_DONE = "2026-08-17T03:05:00Z"
POLL_2 = "2026-08-17T04:00:00Z"
POLL_2_DONE = "2026-08-17T04:05:00Z"
RECORDED = "2026-08-17T03:00:01Z"
RETRIEVED = "2026-08-17T03:00:02Z"
ACCEPT_Q = "2026-06-15T20:11:00Z"
ACCEPT_NEW = "2026-08-12T21:04:00Z"
ACCEPT_AMEND = "2026-08-13T16:30:00Z"
ACCEPT_LATE = "2026-08-16T18:00:00Z"


def _clocks(started: str, completed: str, *, recovery_from: str | None = None) -> PollClocks:
    return PollClocks(
        poll_started_at=started,
        poll_completed_at=completed,
        recorded_at=RECORDED,
        selection_cutoff_at=started,
        recovery_from=recovery_from,
    )


def _write_universe(path: Path, rows: list[tuple[str, int]]) -> Path:
    frame = pd.DataFrame(
        {"cik": [cik for _, cik in rows]},
        index=pd.Index([ticker for ticker, _ in rows], name="ticker"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    return path


def _filing(
    accession: str,
    form: str,
    *,
    accepted: str,
    filed: str,
    document: str = "a.htm",
) -> dict[str, object]:
    return {
        "accession": accession,
        "form": form,
        "accepted": accepted,
        "filed": filed,
        "document": document,
    }


def _submissions_bytes(cik: str, filings: list[dict[str, object]], *, extra_8k: bool = False, files: list | None = None) -> bytes:
    rows = list(filings)
    if extra_8k:
        rows.append(
            _filing("0000000000-26-000099", "8-K", accepted="2026-08-14T12:00:00Z", filed="2026-08-14")
        )
    payload = {
        "cik": str(int(cik)),
        "name": "TEST ISSUER",
        "filings": {
            "recent": {
                "accessionNumber": [row["accession"] for row in rows],
                "form": [row["form"] for row in rows],
                "filingDate": [row["filed"] for row in rows],
                "reportDate": [row["filed"] for row in rows],
                "acceptanceDateTime": [row["accepted"] for row in rows],
                "primaryDocument": [row["document"] for row in rows],
                "isXBRL": [1 for _ in rows],
                "isInlineXBRL": [1 for _ in rows],
            },
            "files": files or [],
        },
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _facts_bytes(cik: str, marker: str = "v1") -> bytes:
    return json.dumps(
        {"cik": int(cik), "entityName": "TEST", "facts": {}, "marker": marker},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


class FakeSec:
    def __init__(self) -> None:
        self.submissions: dict[str, bytes] = {}
        self.facts: dict[str, bytes] = {}
        self.fail_submissions: dict[str, str] = {}
        self.fail_facts: dict[str, str] = {}
        self.bad_url_submissions: set[str] = set()
        self.submissions_fetches: list[str] = []
        self.facts_fetches: list[str] = []

    def fetch_submissions(self, cik: str) -> tuple[bytes, dict[str, str | None]]:
        self.submissions_fetches.append(cik)
        if cik in self.fail_submissions:
            raise BroadSecError(self.fail_submissions[cik], f"forced {self.fail_submissions[cik]}")
        url = "https://example.invalid/not-sec" if cik in self.bad_url_submissions else endpoint_url(cik, "submissions")
        return self.submissions[cik], {
            "url": url,
            "retrieved_at": RETRIEVED,
        }

    def fetch_companyfacts(self, cik: str) -> tuple[bytes, dict[str, str | None]]:
        self.facts_fetches.append(cik)
        if cik in self.fail_facts:
            raise BroadSecError(self.fail_facts[cik], f"forced {self.fail_facts[cik]}")
        return self.facts[cik], {
            "url": endpoint_url(cik, "companyfacts"),
            "retrieved_at": RETRIEVED,
        }


def _poll(store, universe: Path, fake: FakeSec, clocks: PollClocks, **kwargs):
    return run_broad_sec_poll(
        store=store,
        universe_path=universe,
        fetch_submissions=fake.fetch_submissions,
        fetch_companyfacts=fake.fetch_companyfacts,
        clocks=clocks,
        **kwargs,
    )


def _validate_run(receipt: dict) -> None:
    jsonschema.validate(receipt, RUN_SCHEMA)


def _load_json(store: LocalStore, key: str) -> dict:
    raw = store.get_bytes_strict(key)
    assert raw is not None, key
    return json.loads(raw)


def test_universe_binding_fails_closed_on_duplicate_ticker_and_cik(tmp_path: Path) -> None:
    path = tmp_path / "dup.parquet"
    frame = pd.DataFrame(
        {"cik": [320193, 789019]},
        index=pd.Index(["AAPL", "AAPL"], name="ticker"),
    )
    frame.to_parquet(path)
    with pytest.raises(BroadSecError) as err:
        load_universe(path)
    assert err.value.reason_code == "universe_invalid"

    path2 = tmp_path / "dupcik.parquet"
    frame2 = pd.DataFrame(
        {"cik": [320193, 320193]},
        index=pd.Index(["AAPL", "MSFT"], name="ticker"),
    )
    frame2.to_parquet(path2)
    with pytest.raises(BroadSecError) as err:
        load_universe(path2)
    assert err.value.reason_code == "universe_invalid"


def test_two_run_idempotence_does_not_advance_source_identity(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193), (MSFT[0], 789019)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    m = _filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [q])
    fake.submissions[MSFT[1]] = _submissions_bytes(MSFT[1], [m])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1])

    first = _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    assert first.exit_code == 0
    _validate_run(first.receipt)
    assert first.receipt["status"] == "complete"
    objects_after_first = count_source_objects(store)
    aapl_pointer = store.get_bytes_strict(issuer_latest_key(AAPL[1]))
    msft_pointer = store.get_bytes_strict(issuer_latest_key(MSFT[1]))
    source_clock = first.receipt["latest_relevant_sec_accepted_at"]
    assert source_clock == ACCEPT_Q
    assert source_clock != POLL_1
    assert source_clock != POLL_1_DONE
    assert source_clock != RETRIEVED

    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    second = _poll(store, universe, fake, _clocks(POLL_2, POLL_2_DONE))
    assert second.exit_code == 0
    _validate_run(second.receipt)
    assert count_source_objects(store) == objects_after_first
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) == aapl_pointer
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) == msft_pointer
    assert second.receipt["run_id"] != first.receipt["run_id"]
    assert second.receipt["poll_started_at"] == POLL_2
    assert first.receipt["poll_started_at"] == POLL_1
    assert second.receipt["latest_relevant_sec_accepted_at"] == source_clock
    assert fake.facts_fetches == []
    assert set(fake.submissions_fetches) == {AAPL[1], MSFT[1]}
    complete = _load_json(store, latest_complete_key())
    assert complete["run_id"] == second.receipt["run_id"]
    assert complete["latest_relevant_sec_accepted_at"] == source_clock
    observation = _load_json(store, latest_observation_key())
    assert observation["run_id"] == second.receipt["run_id"]


def test_one_new_10q_fetches_companyfacts_only_for_affected_issuer(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193), (MSFT[0], 789019)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    msft_q = _filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.submissions[MSFT[1]] = _submissions_bytes(MSFT[1], [msft_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v1")
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1], "v1")
    _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))

    fake.facts_fetches.clear()
    new_q = _filing("0000320193-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q, new_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    result = _poll(store, universe, fake, _clocks(POLL_2, POLL_2_DONE))
    assert result.exit_code == 0
    assert fake.facts_fetches == [AAPL[1]]
    assert result.receipt["coverage"]["companyfacts_fetched"] == 1
    assert result.receipt["coverage"]["companyfacts_skipped_unchanged"] == 1
    assert result.receipt["latest_relevant_sec_accepted_at"] == ACCEPT_NEW
    pointer = _load_json(store, issuer_latest_key(AAPL[1]))
    manifest = _load_json(store, pointer["manifest_key"])
    jsonschema.validate(manifest, MANIFEST_SCHEMA)
    accessions = [item["accession_number"] for item in manifest["relevant_filings"]]
    assert "0000320193-26-000044" in accessions
    assert manifest["sec_accepted_at"] == ACCEPT_NEW
    assert manifest["companyfacts_snapshot_kind"] == "current_observed"
    assert "as_of" not in manifest
    assert result.receipt["companyfacts_as_of_policy"] == "current_observed_snapshot"
    complete = _load_json(store, latest_complete_key())
    assert complete["run_id"] == result.receipt["run_id"]


def test_amendment_keeps_prior_manifest_immutable_and_reachable(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v1")
    first = _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    prior_pointer = _load_json(store, issuer_latest_key(AAPL[1]))
    prior_manifest_bytes = store.get_bytes_strict(prior_pointer["manifest_key"])

    amendment = _filing("0000320193-26-000011", "10-Q/A", accepted=ACCEPT_AMEND, filed="2026-08-13")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, amendment])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    second = _poll(store, universe, fake, _clocks(POLL_2, POLL_2_DONE))
    assert second.exit_code == 0
    new_pointer = _load_json(store, issuer_latest_key(AAPL[1]))
    assert new_pointer["manifest_id"] != prior_pointer["manifest_id"]
    assert store.get_bytes_strict(prior_pointer["manifest_key"]) == prior_manifest_bytes
    new_manifest = _load_json(store, new_pointer["manifest_key"])
    assert new_manifest["previous_manifest_id"] == prior_pointer["manifest_id"]
    forms = {item["form"] for item in new_manifest["relevant_filings"]}
    assert "10-Q/A" in forms


def test_accession_after_selection_cutoff_is_not_admitted(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    objects_before = count_source_objects(store)
    prior = _load_json(store, issuer_latest_key(AAPL[1]))

    late = _filing("0000320193-26-000099", "10-Q", accepted=ACCEPT_LATE, filed="2026-08-16")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, late])
    fake.facts_fetches.clear()
    clocks = _clocks(POLL_2, POLL_2_DONE)
    clocks.selection_cutoff_at = "2026-08-15T00:00:00Z"
    result = _poll(store, universe, fake, clocks)
    assert result.exit_code == 0
    assert fake.facts_fetches == []
    assert count_source_objects(store) == objects_before + 1
    digest = sha256(fake.submissions[AAPL[1]]).hexdigest()
    packed = store.get_bytes_strict(object_key(digest))
    assert packed is not None
    with gzip.GzipFile(fileobj=__import__("io").BytesIO(packed), mode="rb") as handle:
        retained = json.loads(handle.read())
    assert late["accession"] in retained["filings"]["recent"]["accessionNumber"]
    still = _load_json(store, issuer_latest_key(AAPL[1]))
    assert still["manifest_id"] == prior["manifest_id"]
    manifest = _load_json(store, still["manifest_key"])
    accessions = [item["accession_number"] for item in manifest["relevant_filings"]]
    assert late["accession"] not in accessions


def test_companyfacts_is_never_labelled_historical_as_of(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.facts[AAPL[1]] = json.dumps({"cik": 320193, "facts": {}, "as_of": POLL_1}).encode()
    result = _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    assert result.exit_code == 1
    assert result.receipt["status"] == "failed"
    assert any(item["reason_code"] == "source_binding_failure" for item in result.receipt["failures"])
    assert store.get_bytes_strict(latest_complete_key()) is None


def test_partial_issuer_failure_does_not_advance_complete_head(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193), (MSFT[0], 789019)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.submissions[MSFT[1]] = _submissions_bytes(
        MSFT[1],
        [_filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1])
    fake.fail_submissions[MSFT[1]] = "sec_5xx_exhausted"

    first = _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    assert first.exit_code == 1
    assert first.receipt["status"] == "degraded"
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is not None
    assert store.get_bytes_strict(latest_complete_key()) is None
    observation = _load_json(store, latest_observation_key())
    assert observation["status"] == "degraded"

    del fake.fail_submissions[MSFT[1]]
    fake.facts_fetches.clear()
    second = _poll(store, universe, fake, _clocks(POLL_2, POLL_2_DONE))
    assert second.exit_code == 0
    assert second.receipt["status"] == "complete"
    assert store.get_bytes_strict(latest_complete_key()) is not None
    assert fake.facts_fetches == [MSFT[1]]


def test_queue_overflow_never_truncates_silently(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193), (MSFT[0], 789019)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.submissions[MSFT[1]] = _submissions_bytes(
        MSFT[1],
        [_filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1])
    result = _poll(
        store, universe, fake, _clocks(POLL_1, POLL_1_DONE), max_affected_issuers=1
    )
    assert result.exit_code == 1
    assert any(item["reason_code"] == "queue_overflow" for item in result.receipt["failures"])
    assert fake.facts_fetches == []
    assert result.receipt["status"] != "complete"
    assert store.get_bytes_strict(latest_complete_key()) is None


def test_oversize_invalid_json_and_wrong_url_fail_before_durable_admission(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    fake.submissions[AAPL[1]] = b"not-json"
    result = _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    assert result.exit_code == 1
    assert result.receipt["failures"][0]["reason_code"] == "invalid_sec_json"
    assert count_source_objects(store) == 0

    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.bad_url_submissions.add(AAPL[1])
    result = _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    assert result.receipt["failures"][0]["reason_code"] == "source_binding_failure"
    assert count_source_objects(store) == 0

    fake.bad_url_submissions.clear()
    fake.fail_submissions[AAPL[1]] = "response_too_large"
    result = _poll(store, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    assert result.receipt["failures"][0]["reason_code"] == "response_too_large"
    assert count_source_objects(store) == 0
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is None


def test_cas_failure_does_not_move_complete_pointer(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193)])
    inner = LocalStore(tmp_path / "store")
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    first = _poll(inner, universe, fake, _clocks(POLL_1, POLL_1_DONE))
    assert first.exit_code == 0
    complete_before = inner.get_bytes_strict(latest_complete_key())

    class LyingStore:
        def __init__(self, wrapped: LocalStore) -> None:
            self.wrapped = wrapped

        def put_bytes_strict_conditional(self, key, data, *, expected_version, content_type="application/octet-stream"):
            if key == latest_complete_key():
                return True
            return self.wrapped.put_bytes_strict_conditional(
                key, data, expected_version=expected_version, content_type=content_type
            )

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    amendment = _filing("0000320193-26-000011", "10-Q/A", accepted=ACCEPT_AMEND, filed="2026-08-13")
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, amendment])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    result = _poll(LyingStore(inner), universe, fake, _clocks(POLL_2, POLL_2_DONE))
    assert result.exit_code == 1
    assert result.receipt["reason_code"] == "store_readback_failure"
    assert inner.get_bytes_strict(latest_complete_key()) == complete_before


def test_recovery_window_predating_recent_submissions_is_reason_coded(tmp_path: Path) -> None:
    universe = _write_universe(tmp_path / "universe.parquet", [(AAPL[0], 320193)])
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
        files=[{"name": "CIK0000320193-submissions-001.json", "filingCount": 40}],
    )
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    result = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_1, POLL_1_DONE, recovery_from="2020-01-01T00:00:00Z"),
        mode="recovery",
    )
    assert result.exit_code == 1
    assert any(
        item["reason_code"] == "historical_submissions_required"
        for item in result.receipt["failures"]
    )
    assert store.get_bytes_strict(latest_complete_key()) is None


def test_retrieve_current_reuses_collector_retry_and_does_not_write_wave2_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("collectors.edgar_forensics.time.sleep", lambda _seconds: None)
    calls = {"n": 0}
    body = b'{"cik":"0000320193","filings":{"recent":{"accessionNumber":[]}}}'

    class Response:
        def __init__(self, url: str, status_code: int) -> None:
            self.url = url
            self.status_code = status_code
            self.headers = {"ETag": '"abc"'}
            self.closed = False

        @property
        def content(self) -> bytes:
            raise AssertionError("bounded collector must not read response.content")

        def iter_content(self, *, chunk_size: int):
            yield body

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}")

        def close(self) -> None:
            self.closed = True

    class Session:
        def get(self, url, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                return Response(url, 429)
            return Response(url, 200)

    collector = SecForensicsCollector(
        tmp_path / "wave2-raw",
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=Session(),
    )
    content, headers = collector.retrieve_current(AAPL[1], "submissions")
    assert content == body
    assert headers["url"] == endpoint_url(AAPL[1], "submissions")
    assert calls["n"] == 3
    assert not list((tmp_path / "wave2-raw").rglob("latest.json"))

    exhausted = {"n": 0}

    class Always429:
        def get(self, url, **kwargs):
            exhausted["n"] += 1
            return Response(url, 429)

    collector = SecForensicsCollector(
        tmp_path / "wave2-raw-2",
        user_agent="MastermindX research@example.com",
        min_interval_seconds=0.1,
        session=Always429(),
    )
    with pytest.raises(RuntimeError, match="after retries"):
        collector.retrieve_current(AAPL[1], "submissions")
    assert exhausted["n"] == 4


def test_five_xx_exhaustion_is_reason_coded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("collectors.edgar_forensics.time.sleep", lambda _seconds: None)

    class Response:
        def __init__(self, url: str) -> None:
            self.url = url
            self.status_code = 503
            self.headers = {}
            self.closed = False

        @property
        def content(self) -> bytes:
            raise AssertionError("bounded collector must not read response.content")

        def iter_content(self, *, chunk_size: int):
            yield b"{}"

        def raise_for_status(self) -> None:
            raise requests.HTTPError("HTTP 503")

        def close(self) -> None:
            self.closed = True

    class Session:
        def get(self, url, **kwargs):
            return Response(url)

    from engine.fundamental_forensics.broad_sec_store import classify_fetch_error, live_fetchers

    fetch_submissions, _facts = live_fetchers(
        user_agent="MastermindX research@example.com",
        scratch_root=tmp_path / "scratch",
        submissions_session=Session(),
        retrieved_at=RETRIEVED,
    )
    with pytest.raises(BroadSecError) as err:
        fetch_submissions(AAPL[1])
    assert err.value.reason_code == "sec_5xx_exhausted"
    assert classify_fetch_error(RuntimeError("SEC fetch failed after retries for x: SEC transient HTTP 429")) == (
        "sec_429_exhausted"
    )


def test_cli_incremental_refuses_recovery_from() -> None:
    assert broad_sec_main(["--mode", "incremental", "--recovery-from", POLL_1]) == 1


def test_broad_sec_suite_is_named_in_engine_render_guards() -> None:
    text = (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^  engine-render-guards:\n.*?(?=^  [A-Za-z0-9_-]+:)",
        text,
    )
    assert match is not None
    job = match.group(0)
    assert "tests/test_fundamental_forensics_broad_sec.py" in job
    assert "tests/test_filing_forensics_broad_sec_lane.py" in job
