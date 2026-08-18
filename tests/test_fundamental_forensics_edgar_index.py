"""FF-1P2R EDGAR full-index discovery plane — acceptance A–K and ZIP safety."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from engine.fundamental_forensics.broad_sec_store import (
    MAX_MASTER_INDEX_MEMBER_BYTES,
    MAX_MASTER_INDEX_ZIP_BYTES,
    PREFIX,
    BroadSecError,
    issuer_latest_key,
    latest_complete_key,
    object_key,
    parse_master_index_archive,
    previous_quarter_reconciliation_due,
)
from engine.research_vault.r2_store import LocalStore
from tests.test_fundamental_forensics_broad_sec import (
    AAPL,
    ACCEPT_NEW,
    ACCEPT_Q,
    MSFT,
    POLL_1,
    POLL_2,
    POLL_3,
    RECOVERY_FROM,
    FakeSec,
    _clocks,
    _facts_bytes,
    _filing,
    _idx_row,
    _layout,
    _load_gzip_json,
    _load_json,
    _master_zip,
    _poll,
    _submissions_bytes,
    _validate_run,
)


CENSUS = 2837
Q4_POLL = "2026-10-02T03:15:00Z"


class CountingStore:
    """Count issuer-level R2 reads/writes without intercepting index/run keys."""

    def __init__(self, wrapped: LocalStore) -> None:
        self.wrapped = wrapped
        self.issuer_reads: list[str] = []
        self.issuer_writes: list[str] = []

    def _note(self, key: str, *, write: bool = False) -> None:
        if "/issuers/" in key:
            (self.issuer_writes if write else self.issuer_reads).append(key)

    def get_bytes_strict(self, key: str):
        self._note(key)
        return self.wrapped.get_bytes_strict(key)

    def get_bytes_strict_bounded(self, key: str, maximum_bytes: int):
        self._note(key)
        return self.wrapped.get_bytes_strict_bounded(key, maximum_bytes)

    def get_bytes_strict_bounded_versioned(self, key: str, maximum_bytes: int):
        self._note(key)
        return self.wrapped.get_bytes_strict_bounded_versioned(key, maximum_bytes)

    def put_bytes_strict_conditional(self, key, data, *, expected_version, content_type="application/octet-stream"):
        self._note(key, write=True)
        return self.wrapped.put_bytes_strict_conditional(
            key, data, expected_version=expected_version, content_type=content_type
        )

    def __getattr__(self, name):
        return getattr(self.wrapped, name)


def _census_rows() -> list[tuple[str, int]]:
    rows = [(f"T{index:04d}", 1_000_000 + index) for index in range(CENSUS)]
    rows[0] = (AAPL[0], 320193)
    rows[1] = (MSFT[0], 789019)
    return rows


def _zip_with(name: str, payload: bytes, extra: list[tuple[str, bytes]] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as handle:
        handle.writestr(name, payload)
        for extra_name, extra_payload in extra or []:
            handle.writestr(extra_name, extra_payload)
    return buf.getvalue()


def test_previous_quarter_reconciliation_seam_is_frozen() -> None:
    assert previous_quarter_reconciliation_due(poll_started_at=POLL_1) is False
    assert previous_quarter_reconciliation_due(
        poll_started_at=POLL_1, last_reconciled_at="2026-08-01T00:00:00Z"
    ) is False


def test_empty_index_baseline_scales_with_2837_issuers_and_zero_issuer_fetches(tmp_path: Path) -> None:
    rows = _census_rows()
    repo, universe, store = _layout(tmp_path, rows)
    counted = CountingStore(store)
    fake = FakeSec()
    fake.set_index([])
    result = _poll(counted, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert result.exit_code == 0
    _validate_run(result.receipt)
    assert result.receipt["status"] == "complete"
    assert result.receipt["coverage"]["expected_issuers"] == CENSUS
    assert result.receipt["coverage"]["observed_issuers"] == CENSUS
    assert result.receipt["index"]["baseline"] is True
    assert fake.index_fetches == [(2026, 3)]
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []
    assert counted.issuer_reads == []
    assert counted.issuer_writes == []
    assert store.get_bytes_strict(latest_complete_key()) is not None
    payload = _load_gzip_json(store, result.receipt["storage"]["observation_key"])
    assert payload["row_count"] == CENSUS
    assert {row["outcome"] for row in payload["issuers"]} == {"observed_no_relevant_change"}
    assert {row["discovery_source"] for row in payload["issuers"]} == {
        "sec_edgar_full_master_index"
    }
    assert all(row["submissions_fetched"] is False for row in payload["issuers"])
    assert all(row["companyfacts_fetched"] is False for row in payload["issuers"])
    assert all(row["new_event_count"] == 0 for row in payload["issuers"])


def test_unchanged_next_run_fetches_only_the_index(tmp_path: Path) -> None:
    rows = _census_rows()
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    aapl_q = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-07-31")
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-07-31", aapl_q["accession"])])
    first = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert first.receipt["index"]["baseline"] is True
    counted = CountingStore(store)
    fake.submissions_fetches.clear()
    fake.facts_fetches.clear()
    fake.index_fetches.clear()
    second = _poll(counted, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert second.exit_code == 0
    assert second.receipt["index"]["baseline"] is False
    assert second.receipt["index"]["new_events"] == 0
    assert fake.index_fetches == [(2026, 3)]
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []
    assert counted.issuer_reads == []
    assert counted.issuer_writes == []
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is None


def test_one_new_10q_touches_exactly_one_issuer(tmp_path: Path) -> None:
    rows = _census_rows()
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    prior = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-07-15")
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-07-15", prior["accession"])])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    new_q = _filing("0000320193-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [prior, new_q])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1], "v2")
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-07-15", prior["accession"]),
            _idx_row(AAPL[1], "10-Q", "2026-08-12", new_q["accession"]),
        ]
    )
    counted = CountingStore(store)
    fake.submissions_fetches.clear()
    fake.facts_fetches.clear()
    fake.index_fetches.clear()
    result = _poll(counted, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 0
    assert fake.index_fetches == [(2026, 3)]
    assert fake.submissions_fetches == [AAPL[1]]
    assert fake.facts_fetches == [AAPL[1]]
    touched = {key.split("/issuers/")[1].split("/")[0] for key in counted.issuer_reads + counted.issuer_writes}
    assert touched == {AAPL[1]}
    assert store.get_bytes_strict(issuer_latest_key(MSFT[1])) is None
    payload = _load_gzip_json(store, result.receipt["storage"]["observation_key"])
    by_cik = {row["cik"]: row for row in payload["issuers"]}
    assert by_cik[AAPL[1]]["submissions_fetched"] is True
    assert by_cik[MSFT[1]]["submissions_fetched"] is False
    assert payload["row_count"] == CENSUS


def test_non_relevant_index_noise_fetches_zero_issuers(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index(
        [
            _idx_row(AAPL[1], "8-K", "2026-08-12", "0000320193-26-000088"),
            _idx_row(AAPL[1], "4", "2026-08-12", "0000320193-26-000089"),
            _idx_row(MSFT[1], "13F-HR", "2026-08-12", "0000789019-26-000090"),
            _idx_row(MSFT[1], "S-1", "2026-08-12", "0000789019-26-000091"),
        ]
    )
    fake.submissions_fetches.clear()
    fake.facts_fetches.clear()
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.exit_code == 0
    assert fake.submissions_fetches == []
    assert fake.facts_fetches == []
    assert result.receipt["index"]["new_events"] == 0
    assert store.get_bytes_strict(issuer_latest_key(AAPL[1])) is None


def test_removed_index_row_is_a_correction_candidate_and_preserves_lineage(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-07-15")
    later = _filing("0000320193-26-000044", "10-Q", accepted=ACCEPT_NEW, filed="2026-08-12")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original, later])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    fake.set_index(
        [
            _idx_row(AAPL[1], "10-Q", "2026-07-15", original["accession"]),
            _idx_row(AAPL[1], "10-Q", "2026-08-12", later["accession"]),
        ]
    )
    first = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert first.exit_code == 0
    prior = _load_json(store, issuer_latest_key(AAPL[1]))
    prior_manifest = _load_json(store, prior["manifest_key"])
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-08-12", later["accession"])])
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [later])
    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    result = _poll(store, universe, fake, _clocks(POLL_3), repo_root=repo)
    assert result.exit_code == 0
    assert fake.submissions_fetches == [AAPL[1]]
    assert result.receipt["index"]["correction_events"] == 1
    payload = _load_gzip_json(store, result.receipt["storage"]["observation_key"])
    row = payload["issuers"][0]
    assert row["correction_event_count"] == 1
    assert row["reason_code"] == "edgar_index_correction_requires_reconciliation"
    manifest = _load_json(store, _load_json(store, issuer_latest_key(AAPL[1]))["manifest_key"])
    assert original["accession"] in manifest["cumulative_relevant_accessions"]
    assert later["accession"] in manifest["cumulative_relevant_accessions"]
    assert store.get_bytes_strict(prior["manifest_key"]) is not None
    assert prior_manifest["cumulative_relevant_accessions"] == manifest["cumulative_relevant_accessions"] or original[
        "accession"
    ] in manifest["cumulative_relevant_accessions"]


def test_index_source_validation_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    canonical = {AAPL[1]}

    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(b"x" * (MAX_MASTER_INDEX_ZIP_BYTES + 1), canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_too_large"

    monkeypatch.setattr(
        "engine.fundamental_forensics.broad_sec_store.MAX_MASTER_INDEX_MEMBER_BYTES", 32
    )
    huge = _zip_with("master.idx", b"CIK|Company Name|Form Type|Date Filed|Filename\n" + (b"a" * 64))
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(huge, canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_too_large"
    monkeypatch.undo()

    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(b"not-a-zip", canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_invalid"

    missing = _zip_with("other.idx", b"nope")
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(missing, canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_member_missing"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as handle:
        handle.writestr("master.idx", "CIK|Company Name|Form Type|Date Filed|Filename\n")
        handle.writestr("master.idx", "CIK|Company Name|Form Type|Date Filed|Filename\n")
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(buf.getvalue(), canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_invalid"

    encrypted_info = zipfile.ZipInfo("master.idx")
    encrypted_info.flag_bits |= 0x1
    enc_buf = io.BytesIO()
    with zipfile.ZipFile(enc_buf, "w") as handle:
        handle.writestr(encrypted_info, "CIK|Company Name|Form Type|Date Filed|Filename\n320193|Apple|10-Q|2026-07-15|edgar/data/320193/0000320193-26-000010.txt\n")
    real_infolist = zipfile.ZipFile.infolist

    def encrypted_infolist(self):
        infos = real_infolist(self)
        for info in infos:
            info.flag_bits |= 0x1
        return infos

    monkeypatch.setattr(zipfile.ZipFile, "infolist", encrypted_infolist)
    try:
        with pytest.raises(BroadSecError) as err:
            parse_master_index_archive(enc_buf.getvalue(), canonical_ciks=canonical)
        assert err.value.reason_code == "edgar_index_invalid"
    finally:
        monkeypatch.setattr(zipfile.ZipFile, "infolist", real_infolist)

    traversal = _zip_with("../master.idx", b"nope")
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(traversal, canonical_ciks=canonical)
    assert err.value.reason_code in {"edgar_index_invalid", "edgar_index_member_missing"}

    absolute = _zip_with("/tmp/master.idx", b"nope")
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(absolute, canonical_ciks=canonical)
    assert err.value.reason_code in {"edgar_index_invalid", "edgar_index_member_missing"}

    bad_header = _master_zip([_idx_row(AAPL[1], "10-Q", "2026-07-15", "0000320193-26-000010")])
    bad_header = bad_header.replace(
        b"CIK|Company Name|Form Type|Date Filed|Filename",
        b"Not|A|Header",
    )
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(bad_header, canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_invalid"

    header = (
        "Description: Master\n\n"
        "CIK|Company Name|Form Type|Date Filed|Filename\n"
        "--------------------------------------------------------------------------------\n"
        "320193|Apple|10-Q|2026-07-15|not-enough-fields\n"
    )
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(_zip_with("master.idx", header.encode()), canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_invalid"

    mismatch = _idx_row(AAPL[1], "10-Q", "2026-07-15", "0000320193-26-000010")
    mismatch["filename"] = "edgar/data/789019/0000320193-26-000010.txt"
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(_master_zip([mismatch]), canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_cik_mismatch"

    bad_acc = _idx_row(AAPL[1], "10-Q", "2026-07-15", "0000320193-26-000010")
    bad_acc["filename"] = "edgar/data/320193/not-an-accession.txt"
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(_master_zip([bad_acc]), canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_invalid"

    bad_date = _idx_row(AAPL[1], "10-Q", "2026-13-40", "0000320193-26-000010")
    with pytest.raises(BroadSecError) as err:
        parse_master_index_archive(_master_zip([bad_date]), canonical_ciks=canonical)
    assert err.value.reason_code == "edgar_index_invalid"


def test_index_clocks_never_become_sec_accepted_at(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    fake = FakeSec()
    last_modified = "Tue, 18 Aug 2026 02:02:26 GMT"
    fake.index_headers = {
        "http_etag": '"abc"',
        "http_last_modified": last_modified,
    }
    original = _filing("0000320193-26-000010", "10-Q", accepted=ACCEPT_Q, filed="2026-07-15")
    fake.submissions[AAPL[1]] = _submissions_bytes(AAPL[1], [original])
    fake.facts[AAPL[1]] = _facts_bytes(AAPL[1])
    fake.set_index([])
    baseline = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert baseline.receipt["latest_relevant_sec_accepted_at"] is None
    assert baseline.receipt["index"]["http_last_modified"] == last_modified
    assert baseline.receipt["index"]["archive_retrieved_at"] != ACCEPT_Q
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-07-15", original["accession"])])
    result = _poll(store, universe, fake, _clocks(POLL_2), repo_root=repo)
    assert result.receipt["latest_relevant_sec_accepted_at"] == ACCEPT_Q
    assert result.receipt["index"]["http_last_modified"] == last_modified
    assert result.receipt["latest_relevant_sec_accepted_at"] != last_modified
    assert result.receipt["index"]["archive_retrieved_at"] != ACCEPT_Q
    manifest = _load_json(store, _load_json(store, issuer_latest_key(AAPL[1]))["manifest_key"])
    assert manifest["sec_accepted_at"] == ACCEPT_Q
    assert manifest["sec_accepted_at"] != last_modified
    assert manifest["sec_accepted_at"] != manifest["submissions_retrieved_at"]


def test_july_recovery_derives_only_canonical_relevant_ciks(tmp_path: Path) -> None:
    rows = [(f"T{index:02d}", 3200000 + index) for index in range(12)]
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    index_rows = []
    for index, (ticker, cik_int) in enumerate(rows):
        cik = f"{cik_int:010d}"
        filed = "2026-07-20" if index < 3 else "2026-07-01"
        accession = f"{cik}-26-000040" if index < 3 else f"{cik}-26-000010"
        fake.submissions[cik] = _submissions_bytes(
            cik,
            [_filing(accession, "10-Q", accepted=ACCEPT_Q if index >= 3 else "2026-07-20T18:00:00Z", filed=filed)],
        )
        fake.facts[cik] = _facts_bytes(cik, ticker)
        index_rows.append(_idx_row(cik, "10-Q", filed, accession))
        index_rows.append(_idx_row(cik, "8-K", "2026-08-01", f"{cik}-26-000088"))
    fake.set_index(index_rows)
    result = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_1, recovery_from=RECOVERY_FROM),
        repo_root=repo,
        mode="recovery",
    )
    assert result.exit_code == 0
    assert len(fake.submissions_fetches) == 3
    assert set(fake.submissions_fetches) == {f"{3200000 + index:010d}" for index in range(3)}
    assert set(fake.facts_fetches) == set(fake.submissions_fetches)
    for index in range(3, 12):
        assert store.get_bytes_strict(issuer_latest_key(f"{3200000 + index:010d}")) is None


def test_recovery_continuation_does_not_repoll_the_universe(tmp_path: Path) -> None:
    rows = [(f"T{index:02d}", 3200000 + index) for index in range(8)]
    repo, universe, store = _layout(tmp_path, rows)
    fake = FakeSec()
    index_rows = []
    for ticker, cik_int in rows:
        cik = f"{cik_int:010d}"
        fake.submissions[cik] = _submissions_bytes(
            cik,
            [_filing(f"{cik}-26-000040", "10-Q", accepted="2026-07-20T18:00:00Z", filed="2026-07-20")],
        )
        fake.facts[cik] = _facts_bytes(cik, ticker)
        index_rows.append(_idx_row(cik, "10-Q", "2026-07-20", f"{cik}-26-000040"))
    fake.set_index(index_rows)
    first = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_1, recovery_from=RECOVERY_FROM),
        repo_root=repo,
        mode="recovery",
        max_affected_issuers=3,
    )
    assert first.exit_code == 1
    assert first.receipt["coverage"]["companyfacts_fetched"] == 3
    assert len(fake.submissions_fetches) == 8
    first_facts = list(fake.facts_fetches)
    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    second = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_2, recovery_from=RECOVERY_FROM),
        repo_root=repo,
        mode="recovery",
        max_affected_issuers=3,
    )
    assert second.exit_code == 1
    assert len(fake.submissions_fetches) == 5
    assert len(fake.facts_fetches) == 3
    assert set(first_facts).isdisjoint(set(fake.facts_fetches))
    fake.facts_fetches.clear()
    fake.submissions_fetches.clear()
    third = _poll(
        store,
        universe,
        fake,
        _clocks(POLL_3, recovery_from=RECOVERY_FROM),
        repo_root=repo,
        mode="recovery",
        max_affected_issuers=3,
    )
    assert third.exit_code == 0
    assert len(fake.submissions_fetches) == 2
    assert len(fake.facts_fetches) == 2


def test_quarter_rollover_does_not_treat_prior_quarter_rows_as_mass_corrections(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193), (MSFT[0], 789019)])
    fake = FakeSec()
    fake.set_index([_idx_row(AAPL[1], "10-Q", "2026-07-31", "0000320193-26-000020")])
    q3 = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert q3.receipt["index"]["baseline"] is True
    fake.set_index([], year=2026, quarter=4)
    fake.submissions_fetches.clear()
    q4 = _poll(store, universe, fake, _clocks(Q4_POLL), repo_root=repo)
    assert q4.exit_code == 0
    assert q4.receipt["index"]["baseline"] is True
    assert q4.receipt["index"]["quarter"] == 4
    assert q4.receipt["index"]["correction_events"] == 0
    assert fake.submissions_fetches == []
    assert fake.index_fetches[-1] == (2026, 4)
    assert store.get_bytes_strict(f"{PREFIX}/indexes/quarters/2026-Q3/latest.json") is not None
    assert store.get_bytes_strict(f"{PREFIX}/indexes/quarters/2026-Q4/latest.json") is not None


def test_partial_timed_out_issuer_state_is_not_purged_by_index_baseline(tmp_path: Path) -> None:
    repo, universe, store = _layout(tmp_path, [(AAPL[0], 320193)])
    leftover_key = object_key("ab" * 32)
    store.put_bytes_strict_conditional(
        leftover_key,
        b'{"cik":"0000320193","leftover":true}',
        expected_version=None,
        content_type="application/gzip",
    )
    leftover_latest = issuer_latest_key(AAPL[1])
    store.put_bytes_strict_conditional(
        leftover_latest,
        json.dumps({"schema": "leftover", "cik": AAPL[1], "manifest_id": "prior"}).encode(),
        expected_version=None,
    )
    fake = FakeSec()
    fake.set_index([])
    result = _poll(store, universe, fake, _clocks(POLL_1), repo_root=repo)
    assert result.exit_code == 0
    assert result.receipt["index"]["baseline"] is True
    assert store.get_bytes_strict(leftover_key) is not None
    assert store.get_bytes_strict(leftover_latest) is not None
    assert fake.submissions_fetches == []
