"""FF-1 incremental broad SEC source plane — acceptance and failure contracts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
import io
import json
import re
import zipfile
from hashlib import sha256
from pathlib import Path

import jsonschema
import pandas as pd
import pytest
import requests

from collectors.edgar_forensics import SecForensicsCollector, endpoint_url, full_master_index_url
from engine.fundamental_forensics.broad_sec_store import (
    MAX_UNIVERSE_ISSUERS,
    UNIVERSE_RELATIVE_PATH,
    BroadSecError,
    PollClocks,
    calendar_quarter,
    count_source_objects,
    index_latest_key,
    index_snapshot_key,
    issuer_latest_key,
    latest_complete_key,
    latest_observation_key,
    load_universe,
    object_key,
    quarter_id,
    recovery_continuation_pointer_key,
    run_broad_sec_poll,
    run_key,
    PREFIX,
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
POLL_2 = "2026-08-17T04:00:00Z"
POLL_3 = "2026-08-17T05:00:00Z"
RECOVERY_FROM = "2026-07-12T11:23:15Z"
ACCEPT_Q = "2026-06-15T20:11:00Z"
ACCEPT_NEW = "2026-08-12T21:04:00Z"
ACCEPT_AMEND = "2026-08-13T16:30:00Z"
ACCEPT_LATE = "2026-08-16T18:00:00Z"
ACCEPT_RECOVERY = "2026-07-20T18:00:00Z"


class SequenceClock:
    def __init__(self, start: str = "2026-08-17T03:00:01Z") -> None:
        self._current = datetime.fromisoformat(start.replace("Z", "+00:00"))
        self.stamps: list[str] = []

    def __call__(self) -> str:
        stamp = self._current.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )
        self.stamps.append(stamp)
        self._current += timedelta(seconds=1)
        return stamp


def _clocks(started: str, *, recovery_from: str | None = None, cutoff: str | None = None) -> PollClocks:
    return PollClocks(
        poll_started_at=started,
        selection_cutoff_at=cutoff or started,
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


def _layout(tmp_path: Path, rows: list[tuple[str, int]]) -> tuple[Path, Path, LocalStore]:
    repo = tmp_path / "repo"
    universe = _write_universe(repo / UNIVERSE_RELATIVE_PATH, rows)
    store = LocalStore(tmp_path / "store")
    return repo, universe, store


def _filing(
    accession: str,
    form: str,
    *,
    accepted: str | None,
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


def _submissions_bytes(
    cik: str,
    filings: list[dict[str, object]],
    *,
    extra_8k: bool = False,
    files: list | None = None,
) -> bytes:
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


def _index_filename(cik: str, accession: str) -> str:
    return f"edgar/data/{int(cik)}/{accession}.txt"


def _idx_row(cik: str, form: str, filed: str, accession: str, *, name: str = "TEST ISSUER") -> dict[str, str]:
    return {
        "cik": cik,
        "name": name,
        "form": form,
        "filed": filed,
        "filename": _index_filename(cik, accession),
    }


def _master_zip(rows: list[dict[str, str]] | None = None) -> bytes:
    payload = list(rows or [])
    if not payload:
        payload.append(_idx_row("0000999999", "8-K", "2026-08-01", "0000999999-26-000001"))
    header = (
        "Description:           Master Index of EDGAR Dissemination Feed\n"
        "Last Data Received:    August 17, 2026\n"
        "Comments:              webmaster@sec.gov\n"
        "Anonymous FTP:         ftp://ftp.sec.gov/edgar/\n"
        "Cloud HTTP:            https://www.sec.gov/Archives/\n"
        "\n"
        "CIK|Company Name|Form Type|Date Filed|Filename\n"
        "--------------------------------------------------------------------------------\n"
    )
    body = "\n".join(
        f"{int(row['cik'])}|{row['name']}|{row['form']}|{row['filed']}|{row['filename']}"
        for row in payload
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as handle:
        handle.writestr("master.idx", header + body + "\n")
    return buf.getvalue()


class FakeSec:
    def __init__(self) -> None:
        self.submissions: dict[str, bytes] = {}
        self.facts: dict[str, bytes] = {}
        self.fail_submissions: dict[str, str] = {}
        self.fail_facts: dict[str, str] = {}
        self.fail_detail: dict[str, str] = {}
        self.bad_url_submissions: set[str] = set()
        self.submissions_fetches: list[str] = []
        self.facts_fetches: list[str] = []
        self.index_zips: dict[tuple[int, int], bytes] = {}
        self.index_fetches: list[tuple[int, int]] = []
        self.index_headers: dict[str, str | None] = {}
        self.set_index([])

    def set_index(self, rows: list[dict[str, str]], *, year: int = 2026, quarter: int = 3) -> None:
        self.index_zips[(year, quarter)] = _master_zip(rows)

    def fetch_master_index(self, year: int, quarter: int) -> tuple[bytes, dict[str, str | None]]:
        self.index_fetches.append((year, quarter))
        if (year, quarter) not in self.index_zips:
            raise BroadSecError("edgar_index_unavailable", f"no fixture for {year} Q{quarter}")
        headers: dict[str, str | None] = {
            "url": full_master_index_url(year, quarter),
            **self.index_headers,
        }
        return self.index_zips[(year, quarter)], headers

    def fetch_submissions(self, cik: str) -> tuple[bytes, dict[str, str | None]]:
        self.submissions_fetches.append(cik)
        if cik in self.fail_submissions:
            raise BroadSecError(
                self.fail_submissions[cik],
                self.fail_detail.get(cik, f"forced {self.fail_submissions[cik]}"),
            )
        url = "https://example.invalid/not-sec" if cik in self.bad_url_submissions else endpoint_url(cik, "submissions")
        return self.submissions[cik], {"url": url}

    def fetch_companyfacts(self, cik: str) -> tuple[bytes, dict[str, str | None]]:
        self.facts_fetches.append(cik)
        if cik in self.fail_facts:
            raise BroadSecError(self.fail_facts[cik], f"forced {self.fail_facts[cik]}")
        return self.facts[cik], {"url": endpoint_url(cik, "companyfacts")}


def _poll(store, universe: Path, fake: FakeSec, clocks: PollClocks, *, repo_root: Path, now=None, **kwargs):
    return run_broad_sec_poll(
        store=store,
        universe_path=universe,
        fetch_submissions=fake.fetch_submissions,
        fetch_companyfacts=fake.fetch_companyfacts,
        fetch_master_index=fake.fetch_master_index,
        clocks=clocks,
        now=now or SequenceClock(),
        repo_root=repo_root,
        **kwargs,
    )


def _validate_run(receipt: dict) -> None:
    jsonschema.validate(receipt, RUN_SCHEMA)


def _load_json(store: LocalStore, key: str) -> dict:
    raw = store.get_bytes_strict(key)
    assert raw is not None, key
    return json.loads(raw)


def _load_gzip_json(store: LocalStore, key: str) -> dict:
    raw = store.get_bytes_strict(key)
    assert raw is not None, key
    with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as handle:
        return json.loads(handle.read())


def _receipt_from_head(store: LocalStore, key: str) -> tuple[dict, dict]:
    head = _load_json(store, key)
    return head, _load_json(store, head["run_key"])


def _assert_clock_order(receipt: dict, observations: list[dict]) -> None:
    started = receipt["poll_started_at"]
    recorded = receipt["recorded_at"]
    completed = receipt["poll_completed_at"]
    assert started <= recorded <= completed
    assert recorded != started
    for row in observations:
        sub_at = row.get("submissions_retrieved_at")
        facts_at = row.get("companyfacts_retrieved_at")
        if sub_at:
            assert started <= sub_at <= recorded
        if facts_at:
            assert sub_at <= facts_at <= recorded


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


def test_live_canonical_census_size_binds_under_hard_max(tmp_path: Path) -> None:
    """Reproduce production run 32097495749: 2837 issuers used to fail at 2500."""
    rows = [(f"T{i:04d}", 1_000_000 + i) for i in range(2837)]
    path = _write_universe(tmp_path / "census.parquet", rows)
    bound = load_universe(path)
    assert bound.issuer_count == 2837
    assert bound.unique_ticker_count == 2837
    assert bound.unique_cik_count == 2837
    assert bound.issuer_count <= MAX_UNIVERSE_ISSUERS


def test_universe_hard_max_still_fail_closes_above_cap(tmp_path: Path) -> None:
    rows = [(f"T{i:04d}", 1_000_000 + i) for i in range(MAX_UNIVERSE_ISSUERS + 1)]
    path = _write_universe(tmp_path / "oversize.parquet", rows)
    with pytest.raises(BroadSecError) as err:
        load_universe(path)
    assert err.value.reason_code == "universe_invalid"
    assert str(MAX_UNIVERSE_ISSUERS) in err.value.detail


@pytest.mark.needs_full_checkout("data")
def test_live_canonical_parquet_binds_under_hard_max() -> None:
    path = ROOT / UNIVERSE_RELATIVE_PATH
    bound = load_universe(path, repo_root=ROOT)
    assert bound.canonical is True
    assert bound.issuer_count > 0
    assert bound.issuer_count <= MAX_UNIVERSE_ISSUERS
    assert bound.unique_ticker_count == bound.issuer_count
    assert bound.unique_cik_count == bound.issuer_count


def test_two_run_idempotence_does_not_advance_source_identity(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    m = _filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [q])
    fake.submissions[MSFT[1]] = _submissions_bytes(MSFT[1], [m])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1])
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", q["accession"]),
            _idx_row(MSFT[1], "10-Q", "2026-06-15", m["accession"]),
        ]
    )

    first = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert first.exit_code == 0
    _validate_run(first.receipt)
    assert first.receipt["status"] == "complete"
    assert first.receipt["index"]["baseline"] is True
    assert first.receipt["index"]["source_kind"] == "sec_edgar_full_master_index"
    assert fake.facts_fetches == []
    assert fake.submissions_fetches == []
    assert len(fake.index_fetches) == 1
    objects_after_first = count_source_objects(store)
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is None
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is None
    assert first.receipt["latest_relevant_sec_accepted_at"] is None
    snapshot_id = first.receipt["index"]["snapshot_sha256"]

    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    fake.index_fetches.clear()
    second = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert second.exit_code == 0
    _validate_run(second.receipt)
    assert count_source_objects(store) == objects_after_first
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is None
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is None
    assert second.receipt["run_id"] != first.receipt["run_id"]
    assert second.receipt["poll_started_at"] == POLL_2
    assert first.receipt["poll_started_at"] == POLL_1
    assert second.receipt["index"]["baseline"] is False
    assert second.receipt["index"]["snapshot_sha256"] == snapshot_id
    assert second.receipt["index"]["new_events"] == 0
    assert fake.facts_fetches == []
    assert fake.submissions_fetches == []
    assert fake.index_fetches == [(2026, 3)]
    head, complete_receipt = _receipt_from_head(store, latest_complete_key())
    assert head["run_id"] == second.receipt["run_id"]
    observation_head, _obs_receipt = _receipt_from_head(store, latest_observation_key())
    assert observation_head["run_id"] == second.receipt["run_id"]
    assert "failures" not in observation_head
    assert complete_receipt["index"]["http_last_modified"] is None or complete_receipt[
        "latest_relevant_sec_accepted_at"
    ] != complete_receipt["index"]["http_last_modified"]


def test_one_new_10q_fetches_companyfacts_only_for_affected_issuer(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    msft_q = _filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.submissions[MSFT[1]] = _submissions_bytes(MSFT[1], [msft_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v1")
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1], "v1")
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", aapl_q["accession"]),
            _idx_row(MSFT[1], "10-Q", "2026-06-15", msft_q["accession"]),
        ]
    )
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)

    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    new_q = _filing("0000320193-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q, new_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", aapl_q["accession"]),
            _idx_row(AAPL[1], "10-Q", "2026-08-12", new_q["accession"]),
            _idx_row(MSFT[1], "10-Q", "2026-06-15", msft_q["accession"]),
        ]
    )
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 0
    assert fake.submissions_fetches == [AAPL[1]]
    assert fake.facts_fetches == [AAPL[1]]
    assert result.receipt["coverage"]["companyfacts_fetched"] == 1
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is None
    assert result.receipt["latest_relevant_sec_accepted_at"] == ACCEPT_NEW
    pointer = _load_json(store, issuer_latest_key(AAPL[1]))
    manifest = _load_json(store, pointer["manifest_key"])
    jsonschema.validate(manifest, MANIFEST_SCHEMA)
    accessions = [item["accession_number"] for item in manifest["relevant_filings"]]
    assert "0000320193-26-000044" in accessions
    assert "0000320193-26-000010" in manifest["cumulative_relevant_accessions"]
    assert manifest["sec_accepted_at"] == ACCEPT_NEW
    assert manifest["companyfacts_snapshot_kind"] == "current_observed"
    assert "as_of" not in manifest
    assert result.receipt["companyfacts_as_of_policy"] == "current_observed_snapshot"
    head, _ = _receipt_from_head(store, latest_complete_key())
    assert head["run_id"] == result.receipt["run_id"]


def test_amendment_keeps_prior_manifest_immutable_and_reachable(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v1")
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"])])
    _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    prior_pointer = _load_json(store, issuer_latest_key(AAPL[1]))
    prior_manifest_bytes = store.get_bytes_strict(prior_pointer["manifest_key"])

    amendment = _filing("0000320193-26-000011", "10-Q/A", accepted=ACCEPT_AMEND, filed="2026-08-13")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, amendment])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"]),
            _idx_row(AAPL[1], "10-Q/A", "2026-08-13", amendment["accession"]),
        ]
    )
    second = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo)
    assert second.exit_code == 0
    new_pointer = _load_json(store, issuer_latest_key(AAPL[1]))
    assert new_pointer["manifest_id"] != prior_pointer["manifest_id"]
    assert store.get_bytes_strict(prior_pointer["manifest_key"]) == prior_manifest_bytes
    new_manifest = _load_json(store, new_pointer["manifest_key"])
    assert new_manifest["previous_manifest_id"] == prior_pointer["manifest_id"]
    forms = {item["form"] for item in new_manifest["relevant_filings"]}
    assert "10-Q/A" in forms
    assert original["accession"] in new_manifest["cumulative_relevant_accessions"]
    assert amendment["accession"] in new_manifest["cumulative_relevant_accessions"]


def test_accession_after_selection_cutoff_is_not_admitted(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"])])
    first = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    objects_before = count_source_objects(store)
    prior = _load_json(store, issuer_latest_key(AAPL[1]))

    late = _filing("0000320193-26-000099", "10-Q", accepted=ACCEPT_LATE, filed="2026-08-16")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, late])
    fake.facts_fetches.clear()
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"]),
            _idx_row(AAPL[1], "10-Q", "2026-08-16", late["accession"]),
        ]
    )
    result = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_3, cutoff="2026-08-15T00:00:00Z"),
        repo_root=repo,
    )
    assert result.exit_code == 1
    assert any(
        item["reason_code"] == "edgar_index_event_not_causally_admitted"
        for item in result.receipt["failures"]
    )
    assert fake.facts_fetches == []
    assert count_source_objects(store) == objects_before + 1
    digest = sha256(fake.submissions[AAPL[1]]).hexdigest()
    packed = store.get_bytes_strict(object_key(digest))
    assert packed is not None
    with gzip.GzipFile(fileobj=io.BytesIO(packed), mode="rb") as handle:
        retained = json.loads(handle.read())
    assert late["accession"] in retained["filings"]["recent"]["accessionNumber"]
    still = _load_json(store, issuer_latest_key(AAPL[1]))
    manifest = _load_json(store, still["manifest_key"])
    accessions = [item["accession_number"] for item in manifest["relevant_filings"]]
    assert late["accession"] not in accessions
    assert any(item.get("withheld_cause") == "after_selection_cutoff" for item in manifest["withheld_filings"])
    assert original["accession"] in manifest["cumulative_relevant_accessions"]
    assert first.receipt["run_id"] != result.receipt["run_id"]
    assert prior["manifest_id"] != still["manifest_id"] or still["submissions_sha256"] == prior["submissions_sha256"]


def test_companyfacts_is_never_labelled_historical_as_of(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.facts[AAPL[1]] = json.dumps({"cik": 320193, "facts": {}, "as_of": POLL_1}).encode()
    fake.set_index([])
    first = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert first.exit_code == 0
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"])])
    first = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert first.exit_code == 1
    assert any(item["reason_code"] == "source_binding_failure" for item in first.receipt["failures"])
    complete_before = store.get_bytes_strict(latest_complete_key())
    assert complete_before is not None

    new_q = _filing("0000320193-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, new_q])
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"]),
            _idx_row(AAPL[1], "10-Q", "2026-08-12", new_q["accession"]),
        ]
    )
    result = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo)
    assert result.exit_code == 1
    assert result.receipt["status"] in {"failed", "degraded"}
    assert any(item["reason_code"] == "source_binding_failure" for item in result.receipt["failures"])
    assert store.get_bytes_strict(latest_complete_key()) == complete_before


def test_partial_issuer_failure_does_not_advance_complete_head(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    msft_q = _filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.submissions[MSFT[1]] = _submissions_bytes(MSFT[1], [msft_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1])
    fake.set_index([])
    baseline = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert baseline.exit_code == 0
    complete_before = store.get_bytes_strict(latest_complete_key())

    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", aapl_q["accession"]),
            _idx_row(MSFT[1], "10-Q", "2026-06-15", msft_q["accession"]),
        ]
    )
    fake.fail_submissions[MSFT[1]] = "sec_5xx_exhausted"
    first = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert first.exit_code == 1
    assert first.receipt["status"] == "degraded"
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is not None
    assert store.get_bytes_strict(latest_complete_key()) == complete_before
    observation = _load_json(store, latest_observation_key())
    assert observation["status"] == "degraded"
    assert observation["schema"] == "fundamental_forensics.broad_sec.head.v1"

    del fake.fail_submissions[MSFT[1]]
    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    second = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo)
    assert second.exit_code == 0
    assert second.receipt["status"] == "complete"
    assert store.get_bytes_strict(latest_complete_key()) is not None
    assert fake.submissions_fetches == [AAPL[1], MSFT[1]]
    assert fake.facts_fetches == [MSFT[1]]


def test_queue_overflow_never_truncates_silently(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    msft_q = _filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.submissions[MSFT[1]] = _submissions_bytes(MSFT[1], [msft_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1])
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)

    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [aapl_q, _filing("0000320193-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")],
    )
    fake.submissions[MSFT[1]] = _submissions_bytes(
        MSFT[1],
        [msft_q, _filing("0000789019-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")],
    )
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", aapl_q["accession"]),
            _idx_row(AAPL[1], "10-Q", "2026-08-12", "0000320193-26-000044"),
            _idx_row(MSFT[1], "10-Q", "2026-06-15", msft_q["accession"]),
            _idx_row(MSFT[1], "10-Q", "2026-08-12", "0000789019-26-000044"),
        ]
    )
    fake.facts_fetches.clear()
    result = _poll(
        store, universe, fake, _clocks(POLL_2), repo_root=repo, max_affected_issuers=1
    )
    assert result.exit_code == 1
    assert any(item["reason_code"] == "queue_overflow" for item in result.receipt["failures"])
    # SPEC item 6: incremental overflow selects first max_affected_issuers (1) sorted by
    # (ticker, cik); AAPL < MSFT so AAPL's CF is fetched; MSFT is non-committable this run.
    assert fake.facts_fetches == [AAPL[1]]
    assert result.receipt["status"] != "complete"
    assert store.get_bytes_strict(latest_complete_key()) is not None


def test_oversize_invalid_json_and_wrong_url_fail_before_durable_admission(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"])])

    fake.submissions[AAPL[1]] = b"not-json"
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 1
    assert result.receipt["failures"][0]["reason_code"] == "invalid_sec_json"
    assert count_source_objects(store) == 0

    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.bad_url_submissions.add(AAPL[1])
    result = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo)
    assert result.receipt["failures"][0]["reason_code"] == "source_binding_failure"
    assert count_source_objects(store) == 0

    fake.bad_url_submissions.clear()
    fake.fail_submissions[AAPL[1]] = "response_too_large"
    result = _poll(store, universe, fake, _clocks("2026-08-17T06:00:00Z"), repo_root=repo)
    assert result.receipt["failures"][0]["reason_code"] == "response_too_large"
    assert count_source_objects(store) == 0
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is None


def test_cas_failure_does_not_move_complete_pointer(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"])])
    first = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert first.exit_code == 0
    complete_before = store.get_bytes_strict(latest_complete_key())

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
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, amendment])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", original["accession"]),
            _idx_row(AAPL[1], "10-Q/A", "2026-08-13", amendment["accession"]),
        ]
    )
    result = _poll(LyingStore(store), universe, fake, _clocks(POLL_3), repo_root=repo)
    assert result.exit_code == 1
    assert result.receipt["reason_code"] == "store_readback_failure"
    assert store.get_bytes_strict(latest_complete_key()) == complete_before


def test_recovery_window_predating_recent_submissions_is_reason_coded(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-07-20", "0000320193-26-000010")])
    keys_before = store.list_prefix(PREFIX)
    result = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_1, recovery_from="2020-01-01T00:00:00Z"),
        repo_root=repo,
        mode="recovery",
    )
    assert result.exit_code == 1
    assert result.receipt["reason_code"] == "recovery_plan_required"
    assert fake.index_fetches == []
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []
    assert store.list_prefix(PREFIX) == keys_before
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

    fetch_submissions, _facts, _index = live_fetchers(
        user_agent="MastermindX research@example.com",
        scratch_root=tmp_path / "scratch",
        submissions_session=Session(),
    )
    with pytest.raises(BroadSecError) as err:
        fetch_submissions(AAPL[1])
    assert err.value.reason_code == "sec_5xx_exhausted"
    assert classify_fetch_error(RuntimeError("SEC fetch failed after retries for x: SEC transient HTTP 429")) == (
        "sec_429_exhausted"
    )


def test_cli_incremental_refuses_recovery_from() -> None:
    assert broad_sec_main(["--mode", "incremental", "--recovery-from", POLL_1]) == 1


def test_cli_recovery_mode_fails_closed_with_recovery_plan_required(capsys: pytest.CaptureFixture[str]) -> None:
    code = broad_sec_main(["--mode", "recovery", "--recovery-from", RECOVERY_FROM])
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert code == 1
    assert payload["reason_code"] == "recovery_plan_required"
    assert broad_sec_main(["--mode", "recovery"]) == 1


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
    assert "tests/test_fundamental_forensics_edgar_index.py" in job


def test_empty_store_recovery_bootstraps_baseline_without_mass_companyfacts(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-07-20", "0000320193-26-000040")])
    keys_before = store.list_prefix(PREFIX)
    result = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_1, recovery_from=RECOVERY_FROM),
        repo_root=repo,
        mode="recovery",
    )
    assert result.exit_code == 1
    assert result.receipt["reason_code"] == "recovery_plan_required"
    assert fake.index_fetches == []
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []
    assert store.list_prefix(PREFIX) == keys_before
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is None
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is None


def test_recent_window_removal_does_not_false_refresh_companyfacts(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    older = _filing("0000320193-26-000001", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    newer = _filing("0000320193-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [older, newer])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v1")
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", older["accession"]),
            _idx_row(AAPL[1], "10-Q", "2026-08-12", newer["accession"]),
        ]
    )
    _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo, mode="incremental")
    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [newer])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    rolled = _poll(store, universe, fake, _clocks("2026-08-17T05:00:00Z"), repo_root=repo)
    assert rolled.exit_code == 0
    assert fake.facts_fetches == []
    assert fake.submissions_fetches == []
    manifest = _load_json(store, _load_json(store, issuer_latest_key(AAPL[1]))["manifest_key"])
    assert older["accession"] in manifest["cumulative_relevant_accessions"]
    assert newer["accession"] in manifest["cumulative_relevant_accessions"]


def test_recovery_converges_across_bounded_tranches(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    fake.set_index([])
    keys_before = store.list_prefix(PREFIX)
    result = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_1, recovery_from=RECOVERY_FROM),
        repo_root=repo,
        mode="recovery",
        max_affected_issuers=64,
    )
    assert result.exit_code == 1
    assert result.receipt["reason_code"] == "recovery_plan_required"
    assert fake.index_fetches == []
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []
    assert store.list_prefix(PREFIX) == keys_before
    assert store.get_bytes_strict(recovery_continuation_pointer_key()) is None
    assert store.get_bytes_strict(latest_complete_key()) is None


def test_companyfacts_byte_budget_stops_further_network_retrieval(tmp_path: Path) -> None:
    rows = [(AAPL[0], 320193), (MSFT[0], 789019), ("IBM", 51143)]
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    ibm = ("IBM", "0000051143")
    index_rows = []
    for ticker, cik in (AAPL, MSFT, ibm):
        fake.submissions[cik] = _submissions_bytes(
            cik,
            [
                _filing(f"{cik}-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15"),
                _filing(f"{cik}-26-000040", "10-Q", accepted=ACCEPT_RECOVERY, filed="2026-07-20"),
            ],
        )
        fake.facts[cik] = _facts_bytes(cik, ticker)
        index_rows.append(_idx_row(cik, "10-Q", "2026-07-20", f"{cik}-26-000040"))
    fake.set_index([])
    baseline = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert baseline.exit_code == 0
    complete_before = store.get_bytes_strict(latest_complete_key())
    fake.set_index(index_rows)
    first_body = fake.facts[AAPL[1]]
    result = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_2),
        repo_root=repo,
        max_companyfacts_bytes_per_run=len(first_body) + 10,
    )
    assert result.exit_code == 1
    assert fake.facts_fetches[0] == AAPL[1]
    assert len(fake.facts_fetches) == 2
    assert result.receipt["coverage"]["companyfacts_fetched"] == 1
    assert result.receipt["coverage"]["recovery_backlog"] >= 1
    # SPEC item 1: latest-complete must not advance when CF budget is exceeded.
    assert store.get_bytes_strict(latest_complete_key()) == complete_before
    # SPEC item 1: index_latest_key is never written (no second mutable pointer).


def test_run_level_observation_receipt_covers_every_expected_issuer(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
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
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-06-15", "0000320193-26-000010"),
            _idx_row(MSFT[1], "10-Q", "2026-06-15", "0000789019-26-000010"),
        ]
    )
    fake.fail_submissions[MSFT[1]] = "sec_5xx_exhausted"
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    payload = _load_gzip_json(store, result.receipt["storage"]["observation_key"])
    assert payload["row_count"] == 2
    by_cik = {row["cik"]: row for row in payload["issuers"]}
    assert by_cik[AAPL[1]]["outcome"] == "observed"
    assert by_cik[AAPL[1]]["submissions_sha256"]
    assert by_cik[AAPL[1]]["submissions_retrieved_at"]
    assert by_cik[MSFT[1]]["outcome"] == "failed"
    assert by_cik[MSFT[1]]["reason_code"] == "sec_5xx_exhausted"
    head = _load_json(store, latest_observation_key())
    assert "issuers" not in head
    assert head["observation_key"] == result.receipt["storage"]["observation_key"]
    assert head["observation_sha256"] == result.receipt["storage"]["observation_sha256"]


def test_broad_failure_receipt_exceeds_pointer_limit_but_compact_observation_advances(
    tmp_path: Path,
) -> None:
    rows = [(f"Z{index:02d}", 4000000 + index) for index in range(40)]
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    index_rows = []
    for ticker, cik_int in rows:
        cik = f"{cik_int:010d}"
        fake.submissions[cik] = _submissions_bytes(
            cik,
            [_filing(f"{cik}-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
        )
        fake.fail_submissions[cik] = "sec_5xx_exhausted"
        fake.fail_detail[cik] = ("SEC upstream exhausted " + ("x" * 400))
        index_rows.append(_idx_row(cik, "10-Q", "2026-06-15", f"{cik}-26-000010"))
    fake.set_index([])
    baseline = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert baseline.exit_code == 0
    complete_before = store.get_bytes_strict(latest_complete_key())
    fake.set_index(index_rows)
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    encoded = json.dumps(result.receipt).encode()
    assert len(encoded) > 16 * 1024
    assert store.get_bytes_strict(latest_complete_key()) == complete_before
    head = _load_json(store, latest_observation_key())
    assert len(json.dumps(head).encode()) < 16 * 1024
    assert head["status"] == "failed"
    assert store.get_bytes_strict(head["run_key"]) is not None


def test_injected_pointer_failures_never_advance_complete_ahead_of_observation(
    tmp_path: Path,
) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])

    class FailKey:
        def __init__(self, wrapped: LocalStore, needle: str) -> None:
            self.wrapped = wrapped
            self.needle = needle

        def put_bytes_strict_conditional(self, key, data, *, expected_version, content_type="application/octet-stream"):
            if self.needle in key:
                raise RuntimeError(f"injected failure for {key}")
            return self.wrapped.put_bytes_strict_conditional(
                key, data, expected_version=expected_version, content_type=content_type
            )

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    for needle in (
        "issuer-observations.json.gz",
        "/receipt.json",
        "latest-observation.json",
    ):
        result = _poll(FailKey(store, needle), universe, fake, _clocks(POLL_1), repo_root=repo)
        assert result.exit_code == 1
        assert store.get_bytes_strict(latest_complete_key()) is None


def test_noncanonical_universe_never_masquerades_as_complete_census(tmp_path: Path) -> None:
    canary = _write_universe(tmp_path / "canary.parquet", [(AAPL[0], 320193)])
    repo = tmp_path / "repo"
    (repo / "data/edgar").mkdir(parents=True)
    store = LocalStore(tmp_path / "store")
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    result = _poll(store, canary, fake, _clocks(POLL_1), repo_root=repo)
    assert result.receipt["universe"]["canonical"] is False
    assert result.receipt["universe"]["path"] != UNIVERSE_RELATIVE_PATH
    assert result.receipt["universe"]["universe_id"].endswith(".noncanonical")
    assert result.exit_code == 1
    assert store.get_bytes_strict(latest_complete_key()) is None
    assert store.get_bytes_strict(latest_observation_key()) is not None


def test_malformed_relevant_accession_and_acceptance_are_not_silently_dropped(
    tmp_path: Path,
) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    good = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")
    payload = json.loads(_submissions_bytes(AAPL[1], [good]))
    recent = payload["filings"]["recent"]
    recent["accessionNumber"].extend(["not-an-accession", "0000320193-26-000011", "0000320193-26-000012"])
    recent["form"].extend(["10-Q", "10-Q", "8-K"])
    recent["filingDate"].extend(["2026-07-01", "2026-07-02", "2026-07-03"])
    recent["reportDate"].extend(["2026-07-01", "2026-07-02", "2026-07-03"])
    recent["acceptanceDateTime"].extend([ACCEPT_RECOVERY, "not-a-time", "2026-07-03T12:00:00Z"])
    recent["primaryDocument"].extend(["b.htm", "c.htm", "d.htm"])
    recent["isXBRL"].extend([1, 1, 0])
    recent["isInlineXBRL"].extend([1, 1, 0])
    fake.submissions[AAPL[1]] = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-06-15", good["accession"])])
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 0
    manifest = _load_json(store, _load_json(store, issuer_latest_key(AAPL[1]))["manifest_key"])
    causes = {item["withheld_cause"] for item in manifest["withheld_filings"]}
    assert "malformed_accession" in causes
    assert "unevaluable_acceptance" in causes
    admitted = [item["accession_number"] for item in manifest["relevant_filings"]]
    assert "not-an-accession" not in admitted
    assert "0000320193-26-000011" not in admitted
    assert good["accession"] in admitted


def test_production_cli_samples_clocks_after_issuer_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, universe, store_dir = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    fake.submissions[AAPL[1]] = _submissions_bytes(
        AAPL[1],
        [_filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-06-15")],
    )
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    monkeypatch.setattr(
        "scripts.run_fundamental_forensics_broad_sec.live_fetchers",
        lambda **_kwargs: (fake.fetch_submissions, fake.fetch_companyfacts, fake.fetch_master_index),
    )
    monkeypatch.setattr(
        "scripts.run_fundamental_forensics_broad_sec.open_store",
        lambda _path: LocalStore(tmp_path / "store"),
    )
    clock = SequenceClock("2026-08-17T03:00:01Z")
    args = [
        "--mode",
        "incremental",
        "--repo-root",
        str(repo),
        "--universe",
        str(universe),
        "--local-store",
        str(tmp_path / "store"),
        "--user-agent",
        "MastermindX research@example.com",
    ]
    assert broad_sec_main(args + ["--poll-started-at", POLL_1], now=clock) == 0
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-06-15", "0000320193-26-000010")])
    later = SequenceClock("2026-08-17T04:00:01Z")
    code = broad_sec_main(args + ["--poll-started-at", POLL_2], now=later)
    assert code == 0
    store = LocalStore(tmp_path / "store")
    head, receipt = _receipt_from_head(store, latest_complete_key())
    _validate_run(receipt)
    observations = _load_gzip_json(store, receipt["storage"]["observation_key"])["issuers"]
    _assert_clock_order(receipt, observations)
    assert receipt["poll_started_at"] == POLL_2
    assert receipt["recorded_at"] != POLL_1
    manifest = _load_json(store, _load_json(store, issuer_latest_key(AAPL[1]))["manifest_key"])
    assert manifest["submissions_retrieved_at"] != POLL_1
    assert manifest["submissions_retrieved_at"] <= receipt["recorded_at"] <= receipt["poll_completed_at"]
    assert head["run_id"] == receipt["run_id"]
    del store_dir


def test_incremental_does_not_silently_enter_recovery_on_backlog(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    fake.set_index([])
    baseline = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert baseline.exit_code == 0
    store.put_bytes_strict_conditional(
        recovery_continuation_pointer_key(),
        json.dumps(
            {
                "schema": "fundamental_forensics.broad_sec.recovery_continuation_head.v1",
                "recovery_from": RECOVERY_FROM,
                "universe_sha256": "planted",
                "pending_count": 70,
                "completed_count": 0,
            }
        ).encode(),
        expected_version=None,
    )
    fake.submissions_fetches.clear()
    fake.facts_fetches.clear()
    fake.index_fetches.clear()
    incremental = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert incremental.receipt["mode"] == "incremental"
    assert incremental.exit_code == 0
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []
    assert incremental.receipt["reason_code"] != "recovery_plan_required"


def test_incremental_never_enters_recovery(tmp_path: Path) -> None:
    test_incremental_does_not_silently_enter_recovery_on_backlog(tmp_path)


# ── SPEC item 4: calendar_quarter mandatory timestamps ──────────────────────

def test_calendar_quarter_mandatory_timestamps() -> None:
    """SPEC item 4 mandated examples plus Eastern-midnight rollover."""
    # Mandatory cases from SPEC:
    # 2026-10-01T03:15:00Z → Eastern 2026-09-30T23:15 EDT → Q3
    assert calendar_quarter("2026-10-01T03:15:00Z") == (2026, 3)
    # 2027-01-01T03:15:00Z → Eastern 2026-12-31T22:15 EST → Q4
    assert calendar_quarter("2027-01-01T03:15:00Z") == (2026, 4)
    # 2027-04-01T03:15:00Z → Eastern 2027-03-31T23:15 EDT → Q1
    assert calendar_quarter("2027-04-01T03:15:00Z") == (2027, 1)
    # 2027-07-01T03:15:00Z → Eastern 2027-06-30T20:15 EDT → Q2
    assert calendar_quarter("2027-07-01T03:15:00Z") == (2027, 2)
    # Eastern-midnight rollover: just-before midnight stays in old quarter
    # 2027-01-01T04:59:59Z → Eastern 2026-12-31T23:59:59 EST → Q4
    assert calendar_quarter("2027-01-01T04:59:59Z") == (2026, 4)
    # Just past midnight crosses into new quarter
    # 2027-01-01T05:00:01Z → Eastern 2027-01-01T00:00:01 EST → Q1
    assert calendar_quarter("2027-01-01T05:00:01Z") == (2027, 1)


# ── SPEC item 5: three-run source clock ──────────────────────────────────────

def test_three_run_source_clock_bootstrap_then_advance_then_stable(tmp_path: Path) -> None:
    """Bootstrap clock is null; new 10-Q sets clock to A; quiet rerun keeps clock A."""
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    # Run 1: bootstrap (no prior), empty index → complete, clock null.
    fake.set_index([])
    r1 = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert r1.exit_code == 0
    assert r1.receipt["latest_relevant_sec_accepted_at"] is None

    # Run 2: one new 10-Q → submissions+CF fetched → clock = ACCEPT_NEW.
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-08-12", aapl_q["accession"])])
    r2 = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert r2.exit_code == 0
    assert r2.receipt["latest_relevant_sec_accepted_at"] == ACCEPT_NEW

    # Run 3: unchanged index → zero changed-issuer fetches → clock stays ACCEPT_NEW.
    fake.submissions_fetches.clear()
    fake.facts_fetches.clear()
    r3 = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo)
    assert r3.exit_code == 0
    assert r3.receipt["latest_relevant_sec_accepted_at"] == ACCEPT_NEW
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []


# ── SPEC item 6: capacity two-run (3 issuers, cap 2) ────────────────────────

def test_capacity_overflow_commits_first_n_defers_rest_then_retries(tmp_path: Path) -> None:
    """cap=2 with 3 issuers needing CF: run1 commits 2, 3rd uncommitted;
    run2 fetches no CF for the 2 already committed; 3rd succeeds and complete advances."""
    ibm = ("IBM", "0000051143")
    rows = [(AAPL[0], 320193), (ibm[0], 51143), (MSFT[0], 789019)]
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    # Baseline run: empty index, all issuers observed with no change.
    fake.set_index([])
    baseline = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert baseline.exit_code == 0
    complete_after_baseline = store.get_bytes_strict(latest_complete_key())

    # Build index with 3 issuers each having one new 10-Q.
    index_rows = []
    for ticker, cik_int in rows:
        cik = f"{cik_int:010d}"
        acc = f"{cik}-26-000001"
        fake.submissions[cik] = _submissions_bytes(cik, [_filing(acc, "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")])
        fake.facts[cik] = _facts_bytes(cik, ticker)
        index_rows.append(_idx_row(cik, "10-Q", "2026-08-12", acc))
    fake.set_index(index_rows)

    # Run 1: cap=2, sorted (AAPL, IBM, MSFT) → AAPL+IBM selected, MSFT deferred.
    fake.facts_fetches.clear()
    r1 = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo, max_affected_issuers=2)
    assert r1.exit_code == 1
    assert any(f["reason_code"] == "queue_overflow" for f in r1.receipt["failures"])
    # AAPL and IBM committed (first 2 sorted by ticker); MSFT deferred.
    assert AAPL[1] in fake.facts_fetches
    assert ibm[1] in fake.facts_fetches
    assert MSFT[1] not in fake.facts_fetches
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is not None
    assert store.get_bytes_strict(issuer_latest_key(ibm[1])) is not None
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is None  # not committed
    # latest-complete must not advance while deferred (MSFT uncommitted).
    assert store.get_bytes_strict(latest_complete_key()) == complete_after_baseline

    # Run 2: cap=2; MSFT still new vs prior snapshot (latest-complete unchanged);
    # AAPL+IBM already committed → no re-fetch; MSFT fetched → all committed → complete advances.
    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    r2 = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo, max_affected_issuers=2)
    assert r2.exit_code == 0
    # Only MSFT needs CF this run (AAPL+IBM already in issuer_latest).
    assert MSFT[1] in fake.facts_fetches
    assert AAPL[1] not in fake.facts_fetches
    assert ibm[1] not in fake.facts_fetches
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is not None
    # All 3 now committed; complete should advance.
    assert store.get_bytes_strict(latest_complete_key()) != complete_after_baseline


def test_capacity_overflow_65_issuers_cap_64(tmp_path: Path) -> None:
    """65 issuers needing CF with max_affected_issuers=64: run1 defers 1, run2 succeeds."""
    all_rows = [(f"T{i:04d}", 4_000_000 + i) for i in range(65)]
    repo, universe, store = _layout(tmp_path, all_rows)
    fake = FakeSec()
    fake.set_index([])
    baseline = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert baseline.exit_code == 0
    complete_after_baseline = store.get_bytes_strict(latest_complete_key())

    index_rows = []
    for ticker, cik_int in all_rows:
        cik = f"{cik_int:010d}"
        acc = f"{cik}-26-000001"
        fake.submissions[cik] = _submissions_bytes(cik, [_filing(acc, "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")])
        fake.facts[cik] = _facts_bytes(cik, ticker)
        index_rows.append(_idx_row(cik, "10-Q", "2026-08-12", acc))
    fake.set_index(index_rows)

    r1 = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo, max_affected_issuers=64)
    assert r1.exit_code == 1
    assert r1.receipt["coverage"]["companyfacts_fetched"] == 64
    # 65th issuer deferred; latest-complete not advanced.
    assert store.get_bytes_strict(latest_complete_key()) == complete_after_baseline

    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    r2 = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo, max_affected_issuers=64)
    assert r2.exit_code == 0
    # Only the 65th issuer's CF fetched (the 64 already committed).
    assert r2.receipt["coverage"]["companyfacts_fetched"] == 1
    assert store.get_bytes_strict(latest_complete_key()) != complete_after_baseline


# ── SPEC item 6: CF byte-budget two-run ──────────────────────────────────────

def test_cf_byte_budget_deferred_absent_from_issuer_ledger(tmp_path: Path) -> None:
    """Byte-budget deferred issuer's new accession is absent from issuer_latest/cumulative
    until facts_satisfied on a later run."""
    rows = [(AAPL[0], 320193), (MSFT[0], 789019)]
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    # Baseline.
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)

    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    msft_q = _filing("0000789019-26-000010", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.submissions[MSFT[1]] = _submissions_bytes(MSFT[1], [msft_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.facts[MSFT[1]] = _facts_bytes(MSFT[1])
    fake.set_index([
        _idx_row(AAPL[1], "10-Q", "2026-08-12", aapl_q["accession"]),
        _idx_row(MSFT[1], "10-Q", "2026-08-12", msft_q["accession"]),
    ])
    # Run 1: AAPL CF fits; MSFT CF budget-exhausted → MSFT deferred.
    first_body = fake.facts[AAPL[1]]
    r1 = _poll(
        store, universe, fake, _clocks(POLL_2), repo_root=repo,
        max_companyfacts_bytes_per_run=len(first_body) + 10,
    )
    assert r1.exit_code == 1
    # MSFT not committed: no issuer_latest, new accession not in cumulative.
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is None
    # AAPL committed normally.
    aapl_latest_ptr = _load_json(store, issuer_latest_key(AAPL[1]))
    aapl_manifest = _load_json(store, aapl_latest_ptr["manifest_key"])
    assert aapl_q["accession"] in aapl_manifest["cumulative_relevant_accessions"]

    # Run 2: full budget → MSFT CF fetched and committed.
    fake.facts_fetches.clear()
    r2 = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo)
    assert r2.exit_code == 0
    assert MSFT[1] in fake.facts_fetches
    msft_latest_ptr = _load_json(store, issuer_latest_key(MSFT[1]))
    msft_manifest = _load_json(store, msft_latest_ptr["manifest_key"])
    assert msft_q["accession"] in msft_manifest["cumulative_relevant_accessions"]


# ── SPEC item 7: CIK validation ──────────────────────────────────────────────

def test_malformed_cik_rejects_in_parse_master_index_archive() -> None:
    """ASCII digit-only check: 32O193, CIK320193, 320193x, +320193 must all be rejected."""
    from engine.fundamental_forensics.broad_sec_store import parse_master_index_archive

    canonical = {"0000320193"}

    def _zip_with_cik(cik_str: str) -> bytes:
        header = (
            "CIK|Company Name|Form Type|Date Filed|Filename\n"
            "--------------------------------------------------------------------------------\n"
        )
        acc = "0000320193-26-000001"
        filename = f"edgar/data/320193/{acc}.txt"
        body = f"{cik_str}|AAPL|10-Q|2026-06-15|{filename}\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as h:
            h.writestr("master.idx", header + body)
        return buf.getvalue()

    bad_ciks = ["32O193", "CIK320193", "320193x", "+320193"]
    for bad in bad_ciks:
        with pytest.raises(BroadSecError, match="not ASCII digits-only"):
            parse_master_index_archive(_zip_with_cik(bad), canonical_ciks=canonical)


def test_agent_filed_accession_is_admitted_when_row_matches_path() -> None:
    """Accession prefix is the transmitting filer, not the subject issuer.

    Live Q3 canary: MSFT CIK 0000789019, 10-K 0001193125-26-323660.
    Row CIK must still match path CIK; accession shape must be valid.
    """
    from engine.fundamental_forensics.broad_sec_store import parse_master_index_archive

    canonical = {"0000789019"}
    header = (
        "CIK|Company Name|Form Type|Date Filed|Filename\n"
        "--------------------------------------------------------------------------------\n"
    )
    acc = "0001193125-26-323660"
    filename = "edgar/data/789019/0001193125-26-323660.txt"
    body = f"789019|MICROSOFT CORP|10-K|2026-07-29|{filename}\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as h:
        h.writestr("master.idx", header + body)
    parsed = parse_master_index_archive(buf.getvalue(), canonical_ciks=canonical)
    assert parsed["relevant_rows"][0]["cik"] == "0000789019"
    assert parsed["relevant_rows"][0]["accession"] == acc


def test_prior_complete_without_index_state_fails_closed(tmp_path: Path) -> None:
    """A sha-verified complete head missing index discovery state must not re-bootstrap."""
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    fake.set_index([])
    run_id = "run_corruptprior0001"
    receipt = {
        "schema": "fundamental_forensics.broad_sec.run.v1",
        "status": "complete",
        "run_id": run_id,
        "latest_relevant_sec_accepted_at": ACCEPT_Q,
    }
    raw = json.dumps(receipt).encode("utf-8")
    key = run_key(run_id)
    assert store.put_bytes_strict_conditional(key, raw, expected_version=None)
    head = {
        "schema": "fundamental_forensics.broad_sec.head.v1",
        "run_id": run_id,
        "run_key": key,
        "run_receipt_sha256": sha256(raw).hexdigest(),
        "status": "complete",
        "poll_completed_at": POLL_1,
        "universe_sha256": "ab" * 32,
        "observation_key": "x",
        "observation_sha256": "cd" * 32,
    }
    assert store.put_bytes_strict_conditional(
        latest_complete_key(),
        json.dumps(head).encode("utf-8"),
        expected_version=None,
    )
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 1
    assert result.receipt["reason_code"] == "issuer_manifest_invalid"
    assert result.receipt.get("index") in (None, {}) or result.receipt["index"].get("baseline") is not True
    assert fake.submissions_fetches == []
    assert store.get_bytes_strict(latest_complete_key()) == json.dumps(head).encode("utf-8")


def test_index_snapshot_write_failure_cannot_complete_or_publish_latest_complete(
    tmp_path: Path,
) -> None:
    """If index snapshot write fails, census_complete=False and latest-complete is not written."""
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    fake.set_index([])

    # Wrap store to fail writes to the snapshot key prefix.
    class SnapFailStore:
        def __init__(self, wrapped) -> None:
            self.wrapped = wrapped

        def put_bytes_strict_conditional(self, key, data, *, expected_version, content_type="application/octet-stream"):
            if "/indexes/quarters/" in key and "snapshot" in key:
                raise BroadSecError("store_write_failure", "simulated snapshot write failure")
            return self.wrapped.put_bytes_strict_conditional(key, data, expected_version=expected_version, content_type=content_type)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    failing_store = SnapFailStore(store)
    result = _poll(failing_store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert result.exit_code == 1
    assert store.get_bytes_strict(latest_complete_key()) is None


# ── SPEC item 10: CAS failure contracts ──────────────────────────────────────

def test_latest_observation_cas_failure_cannot_move_latest_complete(tmp_path: Path) -> None:
    """If latest-observation CAS fails, latest-complete must not advance."""
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    # Baseline run succeeds: latest_complete written.
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    complete_before = store.get_bytes_strict(latest_complete_key())
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-08-12", aapl_q["accession"])])

    class ObsFailStore:
        def __init__(self, wrapped) -> None:
            self.wrapped = wrapped
            self._fail_next_obs = False

        def put_bytes_strict_conditional(self, key, data, *, expected_version, content_type="application/octet-stream"):
            # Fail the latest_observation_key write.
            from engine.fundamental_forensics.broad_sec_store import latest_observation_key as lok
            if key == lok():
                raise BroadSecError("store_write_failure", "simulated obs CAS failure")
            return self.wrapped.put_bytes_strict_conditional(key, data, expected_version=expected_version, content_type=content_type)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    failing_store = ObsFailStore(store)
    result = _poll(failing_store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 1
    # latest-complete must not have advanced.
    assert store.get_bytes_strict(latest_complete_key()) == complete_before


def test_latest_complete_cas_failure_leaves_prior_complete_valid(tmp_path: Path) -> None:
    """If latest-complete CAS fails, the prior complete pointer survives intact."""
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    complete_before = store.get_bytes_strict(latest_complete_key())
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-08-12", aapl_q["accession"])])

    class CompleteFailStore:
        def __init__(self, wrapped) -> None:
            self.wrapped = wrapped

        def put_bytes_strict_conditional(self, key, data, *, expected_version, content_type="application/octet-stream"):
            from engine.fundamental_forensics.broad_sec_store import latest_complete_key as lck
            if key == lck():
                return False
            return self.wrapped.put_bytes_strict_conditional(key, data, expected_version=expected_version, content_type=content_type)

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

    failing_store = CompleteFailStore(store)
    result = _poll(failing_store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 1
    # Prior complete pointer survives (unchanged bytes).
    assert store.get_bytes_strict(latest_complete_key()) == complete_before


def test_compact_head_run_receipt_sha256_matches_stored_bytes(tmp_path: Path) -> None:
    """SPEC item 10: head.run_receipt_sha256 must equal sha256(exact bytes at run_key)."""
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [aapl_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-08-12", aapl_q["accession"])])
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 0

    # Verify both latest_observation and latest_complete heads have correct sha.
    for pointer_key in (latest_observation_key(), latest_complete_key()):
        head = _load_json(store, pointer_key)
        stored_receipt_bytes = store.get_bytes_strict(head["run_key"])
        assert stored_receipt_bytes is not None, f"Receipt missing at {head['run_key']}"
        actual_sha = sha256(stored_receipt_bytes).hexdigest()
        assert head["run_receipt_sha256"] == actual_sha, (
            f"head.run_receipt_sha256 mismatch for {pointer_key}: "
            f"expected {actual_sha}, got {head['run_receipt_sha256']}"
        )
