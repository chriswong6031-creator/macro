"""Hermetic contract tests for the bounded official USAspending subaward rail."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

import collectors.usaspending_subawards as subawards
from collectors.usaspending_subawards import (
    MAX_DETAIL_ROWS_PER_PARENT,
    MAX_DETAIL_ROWS_PER_RUN,
    MAX_PARENTS,
    PAGE_SIZE,
    SUBAWARD_COLLECTION_RECEIPTS_FILENAME,
    SUBAWARD_COUNT_URL,
    SUBAWARD_COLLECTOR_HEARTBEAT_FILENAME,
    SUBAWARD_INGEST_STATUS_FILENAME,
    SUBAWARD_PROJECTION_STATE_FILENAME,
    SUBAWARD_SNAPSHOT_COLUMNS,
    SUBAWARD_SNAPSHOTS_FILENAME,
    SUBAWARDS_URL,
    UsaspendingSubawardsAdapter,
    UsaspendingSubawardsCollector,
    append_subaward_snapshot_versions,
    heartbeat_frame,
    normalize_subaward_snapshot,
    select_parent_awards,
    subaward_projection_generation,
    subaward_projection_generation_matches,
    write_heartbeat,
)


OBSERVED = "2026-08-02T12:34:56+00:00"
PARENT = "CONT_AWD_W31P4Q24F0165_9700_-NONE-_-NONE-"
FIXTURES = Path(__file__).parent / "fixtures"


class _Response:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


class _FixtureSession:
    def __init__(self, counts: dict[str, int], *, fail_parent: str | None = None):
        self.counts = counts
        self.fail_parent = fail_parent
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict, dict]] = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        parent = url.removeprefix(SUBAWARD_COUNT_URL.split("{award_id}")[0]).removesuffix("/")
        if parent == self.fail_parent:
            raise requests.ConnectionError("upstream unavailable token=do-not-persist")
        return _Response({"subawards": self.counts[parent]})

    def post(self, url, *, json, **kwargs):
        self.post_calls.append((url, dict(json), kwargs))
        parent = json["award_id"]
        count = self.counts[parent]
        start = (json["page"] - 1) * json["limit"]
        stop = min(start + json["limit"], count)
        rows = [
            {
                "id": int(hashlib.sha256(parent.encode()).hexdigest()[:8], 16) * 10_000 + idx,
                "subaward_number": "DISPLAY-CAN-REPEAT",
                "action_date": "2026-07-30",
                "amount": float(idx + 1),
                "description": "official row",
                "recipient_name": f"SUBRECIPIENT {idx}",
            }
            for idx in range(start, stop)
        ]
        pages = (count + PAGE_SIZE - 1) // PAGE_SIZE
        return _Response({
            "page_metadata": {
                "page": json["page"],
                "hasNext": json["page"] < pages,
                "hasPrevious": json["page"] > 1,
                "next": json["page"] + 1 if json["page"] < pages else None,
                "previous": json["page"] - 1 if json["page"] > 1 else None,
            },
            "results": rows,
        })


def _write_awards(root: Path, rows: list[dict]) -> None:
    path = root / "data" / "government_revenue" / "awards.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["generated_award_id", "total_obligated"]).to_parquet(
        path, index=False
    )


def _receipt(
    parent: str = PARENT,
    response: dict | None = None,
    page: int = 1,
    observed_at: str = OBSERVED,
) -> dict:
    payload = response or json.loads((FIXTURES / "usaspending_subaward_page.json").read_text())
    return UsaspendingSubawardsCollector._receipt(
        rail="subaward_detail",
        endpoint=SUBAWARDS_URL,
        request_payload={
            "award_id": parent,
            "page": page,
            "limit": 100,
            "sort": "action_date",
            "order": "desc",
        },
        response_payload=payload,
        parent_generated_award_id=parent,
        observed_at=observed_at,
        page=page,
        record_count=len(payload["results"]),
    )


def _one_row(
    amount: float = 10.0,
    *,
    row_id: int = 101,
    number: str = "DISPLAY",
    observed_at: str = OBSERVED,
) -> dict:
    return normalize_subaward_snapshot({
        "id": row_id,
        "subaward_number": number,
        "action_date": "2026-07-30",
        "amount": amount,
        "description": "subrecipient context",
        "recipient_name": "SUBRECIPIENT",
    }, PARENT, _receipt(observed_at=observed_at), observed_at)


def test_official_endpoint_semantics_and_exact_identity_page_body():
    count_payload = json.loads((FIXTURES / "usaspending_subaward_count.json").read_text())
    page_payload = json.loads((FIXTURES / "usaspending_subaward_page.json").read_text())

    class Session:
        def __init__(self):
            self.get_url = None
            self.post_call = None

        def get(self, url, **kwargs):
            self.get_url = url
            return _Response(count_payload)

        def post(self, url, *, json, **kwargs):
            self.post_call = (url, dict(json))
            return _Response(page_payload)

    session = Session()
    collector = UsaspendingSubawardsCollector(session=session, request_pacing_seconds=0)
    count, count_receipt = collector.fetch_count(PARENT, observed_at=OBSERVED)
    rows, detail_receipt = collector.fetch_detail_page(PARENT, 1, observed_at=OBSERVED)

    assert count == 2
    assert session.get_url == SUBAWARD_COUNT_URL.format(award_id=PARENT)
    assert session.post_call == (SUBAWARDS_URL, {
        "award_id": PARENT,
        "page": 1,
        "limit": 100,
        "sort": "action_date",
        "order": "desc",
    })
    assert len(rows) == 2
    assert count_receipt["rail"] == "subaward_count"
    assert detail_receipt["rail"] == "subaward_detail"
    assert "spending_by_subaward_grouped" not in session.get_url
    assert "spending_by_subaward_grouped" not in session.post_call[0]


def test_parent_selection_is_exact_deterministic_and_hard_capped():
    awards = pd.DataFrame([
        {"generated_award_id": f"PARENT-{idx:03d}", "total_obligated": idx}
        for idx in range(200)
    ] + [{"generated_award_id": None, "total_obligated": 1e20}])
    selected = select_parent_awards(awards, max_parents=999)
    assert len(selected) == MAX_PARENTS
    assert selected.iloc[0]["generated_award_id"] == "PARENT-199"
    assert selected["generated_award_id"].is_unique
    assert selected["generated_award_id"].notna().all()


def test_identity_uses_parent_and_broker_id_not_repeated_display_number():
    fixture = json.loads((FIXTURES / "usaspending_subaward_page.json").read_text())
    receipt = _receipt(response=fixture)
    rows = [normalize_subaward_snapshot(raw, PARENT, receipt, OBSERVED) for raw in fixture["results"]]
    frame = append_subaward_snapshot_versions(
        pd.DataFrame(columns=SUBAWARD_SNAPSHOT_COLUMNS),
        pd.DataFrame(rows, columns=SUBAWARD_SNAPSHOT_COLUMNS),
    )
    assert len(frame) == 2
    assert frame["subaward_number"].nunique() == 1
    assert frame["subaward_id"].nunique() == 2
    assert set(frame["subaward_id"]) == {"101", "102"}


def test_normalization_clocks_amount_semantics_and_utf8_description_cap():
    raw = {
        "id": 101,
        "subaward_number": "VISIBLE",
        "action_date": "2026-07-30",
        "amount": 123.45,
        "description": "界" * 1000,
        "recipient_name": "SUBRECIPIENT",
    }
    row = normalize_subaward_snapshot(raw, PARENT, _receipt(), OBSERVED)
    assert row["reported_subaward_amount"] == 123.45
    assert "obligation" not in row
    assert "outlay" not in row
    assert "revenue" not in row
    assert row["effective_at"] == row["action_date"] == "2026-07-30"
    assert row["known_at"] == row["first_seen_at"] == OBSERVED
    assert len(row["description"].encode("utf-8")) <= 2000
    with pytest.raises(ValueError, match="native broker row id"):
        normalize_subaward_snapshot({**raw, "id": 101.9}, PARENT, _receipt(), OBSERVED)


def test_receipts_are_canonical_hash_only_and_normalization_checks_binding(tmp_path):
    response = json.loads((FIXTURES / "usaspending_subaward_page.json").read_text())
    first = _receipt(response=response)
    second = _receipt(response=dict(reversed(list(response.items()))))
    assert first["request_sha256"] == second["request_sha256"]
    assert first["response_sha256"] == second["response_sha256"]
    assert first["receipt_id"] == second["receipt_id"]
    assert not ({"request", "response", "body", "headers", "credentials"} & set(first))

    later = UsaspendingSubawardsCollector._receipt(
        rail="subaward_detail",
        endpoint=SUBAWARDS_URL,
        request_payload={
            "award_id": PARENT,
            "page": 1,
            "limit": 100,
            "sort": "action_date",
            "order": "desc",
        },
        response_payload=response,
        parent_generated_award_id=PARENT,
        observed_at="2026-08-03T12:34:56+00:00",
        page=1,
        record_count=len(response["results"]),
    )
    assert later["request_sha256"] == first["request_sha256"]
    assert later["response_sha256"] == first["response_sha256"]
    assert later["receipt_id"] != first["receipt_id"]

    bad = dict(first, parent_generated_award_id="OTHER")
    with pytest.raises(ValueError, match="receipt binding"):
        normalize_subaward_snapshot(response["results"][0], PARENT, bad, OBSERVED)
    with pytest.raises(ValueError, match="receipt binding"):
        normalize_subaward_snapshot(
            response["results"][0], PARENT, first, "2026-08-03T12:34:56+00:00"
        )

    path = tmp_path / SUBAWARD_COLLECTION_RECEIPTS_FILENAME
    assert subawards._append_receipts([first, second], path) == 1
    stored = path.read_text()
    assert "Official fixture row" not in stored
    assert "User-Agent" not in stored
    assert "authorization" not in stored.lower()

    conflict = dict(first, observed_at="2026-08-04T12:34:56+00:00")
    with pytest.raises(ValueError, match="conflicting evidence"):
        subawards._append_receipts([conflict], path)


def test_version_ledger_retains_reversion_and_generation_is_semantic():
    ledger = pd.DataFrame(columns=SUBAWARD_SNAPSHOT_COLUMNS)
    for amount, observed_at in zip(
        (10.0, 20.0, 10.0),
        (
            "2026-08-01T12:34:56+00:00",
            "2026-08-02T12:34:56+00:00",
            "2026-08-03T12:34:56+00:00",
        ),
    ):
        ledger = append_subaward_snapshot_versions(
            ledger,
            pd.DataFrame(
                [_one_row(amount, observed_at=observed_at)],
                columns=SUBAWARD_SNAPSHOT_COLUMNS,
            ),
        )
    assert len(ledger) == 3
    assert ledger["first_seen_at"].nunique() == 1

    generation = subaward_projection_generation(ledger)
    state = {
        "schema_version": subawards.SCHEMA_VERSION,
        "contract": subawards.SUBAWARD_PROJECTION_STATE_SCHEMA,
        "activation_state": "live",
        "projection_eligible": True,
        "selected_parent_count": 0,
        "parents": [],
        "parent_coverage_semantic_sha256": (
            subawards.subaward_parent_coverage_semantic_sha256([])
        ),
        **generation,
    }
    assert subaward_projection_generation_matches(
        state, ledger.sample(frac=1, random_state=2)
    )
    changed = ledger.copy()
    changed.loc[0, "reported_subaward_amount"] = 999.0
    assert not subaward_projection_generation_matches(state, changed)

    same_clock_conflict = _one_row(
        999.0, observed_at="2026-08-03T12:34:56+00:00"
    )
    with pytest.raises(ValueError, match="strictly increasing evidence clock"):
        append_subaward_snapshot_versions(
            ledger,
            pd.DataFrame([same_clock_conflict], columns=SUBAWARD_SNAPSHOT_COLUMNS),
        )


def test_high_count_parent_persists_exact_count_receipt_state_and_zero_details(tmp_path):
    _write_awards(tmp_path, [{"generated_award_id": PARENT, "total_obligated": 1.0}])
    session = _FixtureSession({PARENT: MAX_DETAIL_ROWS_PER_PARENT + 1})
    status = UsaspendingSubawardsCollector(
        root=tmp_path,
        session=session,
        request_pacing_seconds=0,
    ).collect(observed_at=OBSERVED)

    data_dir = tmp_path / "data" / "government_revenue"
    frame = pd.read_parquet(data_dir / SUBAWARD_SNAPSHOTS_FILENAME)
    state = json.loads((data_dir / SUBAWARD_PROJECTION_STATE_FILENAME).read_text())
    receipts = [json.loads(line) for line in (
        data_dir / SUBAWARD_COLLECTION_RECEIPTS_FILENAME
    ).read_text().splitlines()]
    assert status["status"] == "ok" and status["partial"] is False
    assert len(frame) == 0
    assert len(session.get_calls) == 1 and session.post_calls == []
    assert state["parents"] == [{
        "parent_generated_award_id": PARENT,
        "subaward_count": 501,
        "count_verified": True,
        "high_count_parent": True,
        "collection_state": "high_count_count_only",
        "detail_rows": 0,
        "pages_fetched": 0,
        "source_exhausted": False,
        "count_receipt_id": receipts[0]["receipt_id"],
        "count_receipt_binding": {
            "receipt_id": receipts[0]["receipt_id"],
            "rail": "subaward_count",
            "parent_generated_award_id": PARENT,
            "reported_subaward_count": 501,
        },
        "detail_receipt_ids": [],
    }]
    assert receipts[0]["rail"] == "subaward_count"
    assert receipts[0]["reported_subaward_count"] == 501
    assert subaward_projection_generation_matches(state, frame)


def test_count_only_coverage_digest_fails_closed_on_tamper(tmp_path):
    _write_awards(tmp_path, [{"generated_award_id": PARENT, "total_obligated": 1.0}])
    UsaspendingSubawardsCollector(
        root=tmp_path,
        session=_FixtureSession({PARENT: 501}),
        request_pacing_seconds=0,
    ).collect(observed_at=OBSERVED)
    data_dir = tmp_path / "data" / "government_revenue"
    frame = pd.read_parquet(data_dir / SUBAWARD_SNAPSHOTS_FILENAME)
    state = json.loads((data_dir / SUBAWARD_PROJECTION_STATE_FILENAME).read_text())
    state["parents"][0]["subaward_count"] = 500
    assert not subaward_projection_generation_matches(state, frame)


def test_recursive_sensitive_receipt_keys_are_rejected(tmp_path):
    receipt = _receipt()
    receipt["safe_wrapper"] = {"request_headers": {"Authorization_Token": "secret"}}
    with pytest.raises(ValueError, match="sensitive"):
        subawards._append_receipts([receipt], tmp_path / "receipts.jsonl")


def test_successful_zero_parent_run_materializes_complete_empty_bundle(tmp_path):
    _write_awards(tmp_path, [])
    status = UsaspendingSubawardsCollector(
        root=tmp_path,
        session=_FixtureSession({}),
        request_pacing_seconds=0,
    ).collect(observed_at=OBSERVED)
    data_dir = tmp_path / "data" / "government_revenue"
    receipt_path = data_dir / SUBAWARD_COLLECTION_RECEIPTS_FILENAME
    assert status["status"] == "ok" and status["parents_selected"] == 0
    assert receipt_path.exists() and receipt_path.read_bytes() == b""
    frame = pd.read_parquet(data_dir / SUBAWARD_SNAPSHOTS_FILENAME)
    state = json.loads((data_dir / SUBAWARD_PROJECTION_STATE_FILENAME).read_text())
    assert frame.empty and subaward_projection_generation_matches(state, frame)


def test_per_parent_and_run_caps_never_overfetch(tmp_path):
    parents = [f"PARENT-{idx}" for idx in range(6)]
    _write_awards(tmp_path, [
        {"generated_award_id": parent, "total_obligated": 100 - idx}
        for idx, parent in enumerate(parents)
    ])
    counts = {parent: 500 for parent in parents}
    session = _FixtureSession(counts)
    status = UsaspendingSubawardsCollector(
        root=tmp_path,
        session=session,
        request_pacing_seconds=0,
    ).collect(observed_at=OBSERVED)

    assert status["detail_rows_seen"] == MAX_DETAIL_ROWS_PER_RUN
    assert status["run_cap_count_only_parents"] == 2
    assert len(session.post_calls) == 20
    assert all(call[1]["limit"] == 100 and call[1]["page"] <= 5 for call in session.post_calls)
    by_parent: dict[str, int] = {}
    for _, body, _ in session.post_calls:
        by_parent[body["award_id"]] = by_parent.get(body["award_id"], 0) + 1
    assert max(by_parent.values()) == 5
    assert len(pd.read_parquet(
        tmp_path / "data" / "government_revenue" / SUBAWARD_SNAPSHOTS_FILENAME
    )) == 2000


def test_network_failure_preserves_prior_complete_bundle(tmp_path):
    _write_awards(tmp_path, [{"generated_award_id": PARENT, "total_obligated": 1.0}])
    healthy = _FixtureSession({PARENT: 1})
    collector = UsaspendingSubawardsCollector(
        root=tmp_path,
        session=healthy,
        request_pacing_seconds=0,
    )
    collector.collect(observed_at=OBSERVED)
    data_dir = tmp_path / "data" / "government_revenue"
    protected = [
        data_dir / SUBAWARD_SNAPSHOTS_FILENAME,
        data_dir / SUBAWARD_PROJECTION_STATE_FILENAME,
        data_dir / SUBAWARD_INGEST_STATUS_FILENAME,
    ]
    before = {path: path.read_bytes() for path in protected}

    failing = _FixtureSession({PARENT: 1}, fail_parent=PARENT)
    collector.session = failing
    with pytest.raises(requests.ConnectionError):
        collector.collect(observed_at="2026-08-03T12:34:56+00:00")
    assert {path: path.read_bytes() for path in protected} == before


def test_activation_write_failure_rolls_back_prior_complete_bundle(tmp_path, monkeypatch):
    _write_awards(tmp_path, [{"generated_award_id": PARENT, "total_obligated": 1.0}])
    session = _FixtureSession({PARENT: 1})
    collector = UsaspendingSubawardsCollector(
        root=tmp_path,
        session=session,
        request_pacing_seconds=0,
    )
    collector.collect(observed_at=OBSERVED)
    data_dir = tmp_path / "data" / "government_revenue"
    protected = [
        data_dir / SUBAWARD_SNAPSHOTS_FILENAME,
        data_dir / SUBAWARD_PROJECTION_STATE_FILENAME,
        data_dir / SUBAWARD_INGEST_STATUS_FILENAME,
    ]
    before = {path: path.read_bytes() for path in protected}

    real_atomic_json = subawards._atomic_json

    def fail_state(payload, path):
        if path.name == SUBAWARD_PROJECTION_STATE_FILENAME:
            raise OSError("injected activation failure")
        return real_atomic_json(payload, path)

    monkeypatch.setattr(subawards, "_atomic_json", fail_state)
    with pytest.raises(OSError, match="injected activation"):
        collector.collect(observed_at="2026-08-03T12:34:56+00:00")
    assert {path: path.read_bytes() for path in protected} == before


def test_adapter_returns_dated_heartbeat_only_after_success(monkeypatch, tmp_path):
    ok = {
        "status": "ok",
        "partial": False,
        "observed_at": OBSERVED,
        "parents_selected": 1,
        "parents_counted": 1,
        "detail_parents_collected": 1,
        "high_count_parents": 0,
        "run_cap_count_only_parents": 0,
        "detail_rows_seen": 2,
        "snapshot_versions_total": 2,
        "errors": [],
    }
    monkeypatch.setattr(UsaspendingSubawardsCollector, "collect", lambda self: ok)
    frames = UsaspendingSubawardsAdapter().fetch()
    assert list(frames) == ["subaward_collector_heartbeat"]
    assert frames["subaward_collector_heartbeat"].index[0] == pd.Timestamp("2026-08-02")
    heartbeat_path = write_heartbeat(ok, tmp_path)
    assert heartbeat_path.name == SUBAWARD_COLLECTOR_HEARTBEAT_FILENAME
    assert heartbeat_path.exists()
    with pytest.raises(ValueError, match="successful"):
        heartbeat_frame({**ok, "status": "failed"})


def test_collect_registration_and_slow_lane():
    from scripts.collect import _SLOW, all_adapters

    assert "usaspending_subawards" in _SLOW
    assert all_adapters()["usaspending_subawards"] is UsaspendingSubawardsAdapter
