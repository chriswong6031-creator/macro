from __future__ import annotations

import json
from pathlib import Path

from engine.release_actuals import (
    canonical_actual,
    normalize_publication,
    receipts_from_payload,
    reconcile_receipts,
)
from scripts.reconcile_release_actuals import reconcile


def _publication(event_type: str = "CPI") -> dict:
    values = {
        "CPI": {"headline_mom": -0.4, "core_mom": 0.0, "reference_period": "June 2026"},
        "NFP": {"payroll_change": 57_000, "reference_period": "The"},
    }
    return {
        "event_id": f"{event_type.lower()}:2026-07-14",
        "type": event_type,
        "date": "2026-07-14" if event_type == "CPI" else "2026-08-07",
        "data_ready": True,
        "publisher": "U.S. Bureau of Labor Statistics",
        "source_id": "bls_cpi" if event_type == "CPI" else "bls_employment",
        "source_url": "https://www.bls.gov/news.release/archives/example.htm",
        "source_sha256": "a" * 64,
        "first_seen_at": "2026-07-14T12:30:01+00:00",
        "source_released_at": "2026-07-14T12:30:00+00:00",
        "parser": {"name": event_type.lower(), "version": 1},
        "actual": values[event_type],
    }


def test_cpi_normalizes_two_exact_print_targets() -> None:
    rows = normalize_publication(_publication("CPI"))
    assert [(row["release"], row["period"], row["actual"]) for row in rows] == [
        ("cpi_headline", "2026-06", -0.4),
        ("cpi_core", "2026-06", 0.0),
    ]
    assert all(row["actual_basis"] == "official_published_metric" for row in rows)


def test_nfp_uses_event_period_and_converts_persons_to_thousands() -> None:
    rows = normalize_publication(_publication("NFP"))
    assert len(rows) == 1
    assert rows[0]["period"] == "2026-07"
    assert rows[0]["actual"] == 57.0
    assert rows[0]["official_reference_period"] == "The"


def test_unofficial_domain_or_missing_hash_fails_closed() -> None:
    bad = _publication("CPI")
    bad["source_url"] = "https://example.com/cpi"
    assert normalize_publication(bad) == []
    bad = _publication("CPI")
    bad["source_sha256"] = None
    assert normalize_publication(bad) == []


def test_keep_first_and_correction_candidate() -> None:
    payload = {"schema": "release_publications.v2", "publications": [_publication("CPI")]}
    first = receipts_from_payload(payload)
    assert len(reconcile_receipts(payload, [])) == 2
    changed = _publication("CPI")
    changed["source_sha256"] = "b" * 64
    changed["actual"]["headline_mom"] = -0.3
    novel = reconcile_receipts(
        {"schema": "release_publications.v2", "publications": [changed]}, first
    )
    assert all(row["row_type"] == "correction_candidate" for row in novel)
    assert canonical_actual(first + novel, "cpi_headline", "2026-06")["actual"] == -0.4


def test_file_reconciliation_is_idempotent(tmp_path: Path) -> None:
    payload_path = tmp_path / "live.json"
    out = tmp_path / "actuals.jsonl"
    payload_path.write_text(
        json.dumps({"schema": "release_publications.v2", "publications": [_publication("CPI")]}),
        encoding="utf-8",
    )
    assert len(reconcile(str(payload_path), out)) == 2
    assert reconcile(str(payload_path), out) == []
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2
