from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine.capital_structure.legacy import (
    LEGACY_COLUMNS,
    project_legacy_events,
    project_legacy_rows,
    write_legacy_projection,
)
from engine.capital_structure.event_spine import build_event_version, make_stable_span


FIXTURES = Path(__file__).parent / "fixtures" / "capital_structure" / "legacy"


def _seed_rows():
    return [{
        "accession": "seed-1", "cik": "100", "ticker": "SEED", "form": "S-3",
        "filing_date": "2026-07-20", "_first_seen": "2026-07-20T12:00:00Z",
    }]


def _canonical(accession: str, *, seen: str = "2026-08-02T12:00:00Z") -> dict:
    observation = {
        "source_system": "sec_edgar",
        "source_id": accession,
        "manifest_id": f"manifest:{accession}",
        "accession": accession,
        "issuer_id": "issuer:0000000300",
        "cik": "300",
        "ticker": None,
        "aliases": [],
        "form": "S-3ASR",
        "file_number": "333-123",
        "filing_date": "2026-08-02",
        "accepted_at": "2026-08-02T11:00:00Z",
        "first_seen_at": seen,
        "primary_document_url": "https://www.sec.gov/Archives/example.htm",
        "exhibit_urls": [],
        "content_hashes": ["a" * 64],
    }
    span = make_stable_span(
        observation["manifest_id"], b"strict event", locator="bytes:0-12"
    )
    return build_event_version(observation, [span])


def test_projector_preserves_seed_and_only_appends_post_cutover_eligible_events():
    events = json.loads((FIXTURES / "events.json").read_text())
    rows = project_legacy_rows(_seed_rows(), events, cutover_at="2026-08-01")

    assert rows == _seed_rows() + [{
        "accession": "new-shelf", "cik": "300", "ticker": None, "form": "S-3ASR",
        "filing_date": "2026-08-02", "_first_seen": "2026-08-01T00:00:00Z",
    }]


def test_projector_has_exact_legacy_schema_order_and_never_zero_fills_nulls():
    events = json.loads((FIXTURES / "events.json").read_text())
    projected = project_legacy_events(_seed_rows(), events, cutover_at="2026-08-01")

    assert tuple(projected.columns) == LEGACY_COLUMNS
    assert projected.loc[1, "ticker"] is None
    assert projected.loc[1, "ticker"] != 0


def test_unchanged_seed_is_copied_byte_for_byte_to_a_separate_output(tmp_path):
    source = tmp_path / "seed.parquet"
    target = tmp_path / "projected.parquet"
    pd.DataFrame(_seed_rows(), columns=LEGACY_COLUMNS).to_parquet(source, index=False)
    original = source.read_bytes()

    projected = write_legacy_projection(
        source,
        [{"accession": "too-old", "form": "S-3", "_first_seen": "2026-07-31T23:59:59Z"}],
        cutover_at="2026-08-01",
        output_path=target,
    )

    assert len(projected) == 1
    assert target.read_bytes() == original


def test_projector_accepts_strict_canonical_events_and_serialized_ledger_rows():
    canonical = _canonical("canonical-1")
    serialized = _canonical("serialized-1", seen="2026-08-03T12:00:00Z")
    ledger = pd.DataFrame([{
        "event_id": serialized["event_id"],
        "event_json": json.dumps(serialized, sort_keys=True, separators=(",", ":")),
    }])

    rows = project_legacy_rows(
        _seed_rows(), [canonical], cutover_at="2026-08-01"
    )
    rows = project_legacy_rows(rows, ledger, cutover_at="2026-08-01")

    assert rows[-2:] == [
        {
            "accession": "canonical-1", "cik": "300", "ticker": None,
            "form": "S-3ASR", "filing_date": "2026-08-02",
            "_first_seen": "2026-08-02T12:00:00Z",
        },
        {
            "accession": "serialized-1", "cik": "300", "ticker": None,
            "form": "S-3ASR", "filing_date": "2026-08-02",
            "_first_seen": "2026-08-03T12:00:00Z",
        },
    ]


def test_projector_accepts_json_encoded_nested_event_columns():
    canonical = _canonical("nested-json-1")
    nested_row = {
        "filing": json.dumps(canonical["filing"]),
        "issuer": json.dumps(canonical["issuer"]),
        "point_in_time": json.dumps(canonical["point_in_time"]),
    }
    rows = project_legacy_rows(_seed_rows(), [nested_row], cutover_at="2026-08-01")
    assert rows[-1]["accession"] == "nested-json-1"
    assert rows[-1]["_first_seen"] == "2026-08-02T12:00:00Z"


def test_malformed_serialized_event_is_rejected_not_silently_dropped():
    with pytest.raises(ValueError, match="event_json is not valid JSON"):
        project_legacy_rows(
            _seed_rows(), [{"event_json": "{not-json"}], cutover_at="2026-08-01"
        )
    with pytest.raises(ValueError, match="event_json must contain a JSON object"):
        project_legacy_rows(
            _seed_rows(),
            [{"event_json": None, "accession": "must-not-fall-back"}],
            cutover_at="2026-08-01",
        )
