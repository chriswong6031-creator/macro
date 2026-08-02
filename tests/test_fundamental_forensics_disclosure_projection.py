"""Offline contract tests for the cached disclosure-to-workbench projection lane."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from collectors.edgar_forensics import endpoint_url, persist_response
from collectors.sec_document_spine import persist_archive_document, persist_filing_manifest
from engine.fundamental_forensics.disclosure_projection import (
    DisclosureProjectionError,
    _balanced_finding_receipts,
    _bounded_redline,
    _bounded_receipt,
    build_disclosure_projection,
    disclosure_projection_path,
    read_disclosure_projection,
    write_disclosure_projection,
)
from engine.fundamental_forensics.sec_document_spine import (
    build_filing_manifests,
    with_document_retrievals,
)
from scripts.build_fundamental_forensics import (
    MAX_DISCLOSURE_PROJECTION_BYTES,
    _disclosure_budgeted,
    compose_state,
)


RECORDED_AT = "2026-08-01T12:00:00Z"
AS_OF = "2026-08-01T23:59:59Z"
COMPUTED_AT = "2026-08-02T00:05:00Z"


def test_receipt_keeps_exact_fragment_but_adds_clean_display_excerpt() -> None:
    receipt = _bounded_receipt(
        {
            "accession": "0000000001-26-000001",
            "form": "10-K",
            "source_excerpt": (
                '<div style="text-align:justify"><span class="ix">'
                "Revenue is recognized when control transfers &#8212; not before."
                "</span></div>"
            ),
        }
    )

    assert receipt is not None
    assert receipt["source_excerpt"].startswith('<div style="text-align:justify">')
    assert receipt["display_excerpt"] == (
        "Revenue is recognized when control transfers — not before."
    )


def test_finding_receipt_cap_balances_current_and_prior_accessions() -> None:
    prior = "0000000001-25-000001"
    current = "0000000001-26-000001"

    def receipt(accession: str, offset: int) -> dict[str, object]:
        return {
            "accession": accession,
            "form": "10-K",
            "source_sha256": "a" * 64,
            "source_span": {"char_start": offset, "char_end": offset + 5},
            "source_excerpt": f"Evidence {offset}",
            "block_id": f"block-{offset}",
        }

    raw = {
        "prior_accession": prior,
        "current_accession": current,
        # Structural diffs can group many removals before their additions.
        "evidence_receipts": [
            *(receipt(prior, index) for index in range(12)),
            *(receipt(current, index + 100) for index in range(12)),
        ],
    }

    selected = _balanced_finding_receipts(raw)

    assert len(selected) == 6
    assert [item["filing_role"] for item in selected] == [
        "current", "prior", "current", "prior", "current", "prior"
    ]
    assert {item["accession"] for item in selected} == {prior, current}


def test_projection_preserves_coarse_redline_marker() -> None:
    redline = _bounded_redline(
        {
            "inline_edits": [
                {
                    "operation": "replace",
                    "prior_text": "prior excerpt",
                    "current_text": "current excerpt",
                    "contains_numeric": False,
                    "truncated": True,
                }
            ]
        }
    )

    assert redline["inline_edits"] == [
        {
            "operation": "replace",
            "prior_text": "prior excerpt",
            "current_text": "current excerpt",
            "contains_numeric": False,
            "truncated": True,
        }
    ]


def _submissions() -> dict:
    return {
        "cik": "1",
        "name": "Projection Fixture, Inc.",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000000001-26-000004",
                    "0000000001-26-000003",
                    "0000000001-26-000002",
                    "0000000001-26-000001",
                ],
                "form": ["10-Q", "10-Q", "10-K", "10-K"],
                "filingDate": ["2026-08-01", "2026-05-01", "2026-02-20", "2025-02-20"],
                "reportDate": ["2026-06-30", "2026-03-31", "2025-12-31", "2024-12-31"],
                "acceptanceDateTime": [
                    "2026-08-01T16:00:00.000Z",
                    "2026-05-01T16:00:00.000Z",
                    "2026-02-20T16:00:00.000Z",
                    "2025-02-20T16:00:00.000Z",
                ],
                "primaryDocument": ["q2.htm", "q1.htm", "fy25.htm", "fy24.htm"],
                "isXBRL": [1, 1, 1, 1],
                "isInlineXBRL": [1, 1, 1, 1],
            }
        },
    }


def _document(accession: str) -> bytes:
    changes = {
        "0000000001-26-000001": "Customer concentration may affect results.",
        "0000000001-26-000002": "Customer concentration and new supplier concentration may affect results.",
        "0000000001-26-000003": "Revenue is recognized when promised services transfer to customers.",
        "0000000001-26-000004": "Revenue is recognized when services transfer and collection is probable.",
    }
    return (
        "<html><body>"
        "<h1>Item 1A. Risk Factors</h1>"
        f"<p>{changes[accession]}</p>"
        "<h1>Significant Accounting Policies</h1>"
        f"<p>{changes[accession]}</p>"
        "</body></html>"
    ).encode("utf-8")


def _prepare_cache(tmp_path: Path) -> tuple[Path, Path]:
    raw_root = tmp_path / "raw"
    archive_root = tmp_path / "archive"
    payload = _submissions()
    persist_response(
        raw_root,
        cik=1,
        endpoint="submissions",
        url=endpoint_url(1, "submissions"),
        content=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        retrieved_at=RECORDED_AT,
    )
    for manifest in build_filing_manifests(payload, cik=1, ticker="TST", recorded_at=RECORDED_AT):
        primary = manifest["documents"][0]
        receipt = persist_archive_document(
            archive_root,
            primary,
            _document(manifest["filing"]["accession"]),
            retrieved_at=RECORDED_AT,
        )
        stored = with_document_retrievals(manifest, {primary["document_id"]: receipt.to_dict()})
        persist_filing_manifest(archive_root, stored)
    return raw_root, archive_root


def _projection(tmp_path: Path) -> dict:
    raw_root, archive_root = _prepare_cache(tmp_path)
    return build_disclosure_projection(
        raw_root=raw_root,
        archive_root=archive_root,
        ticker="TST",
        cik=1,
        as_of=AS_OF,
        computed_at=COMPUTED_AT,
    )


def test_cached_projection_selects_verified_latest_periods_and_is_byte_stable(tmp_path: Path) -> None:
    first = _projection(tmp_path)
    second = _projection(tmp_path)

    assert first == second
    assert first["schema"] == "fundamental_forensics.disclosure_projection/v1"
    assert first["clocks"] == {
        "as_of": "2026-08-01T23:59:59.000000Z",
        "recorded_at": "2026-08-01T12:00:00.000000Z",
        "computed_at": "2026-08-02T00:05:00.000000Z",
    }
    tracks = {item["form"]: item for item in first["tracks"]}
    assert tracks["10-K"]["status"] == tracks["10-Q"]["status"] == "ready"
    assert tracks["10-K"]["prior_filing"]["accession"] == "0000000001-26-000001"
    assert tracks["10-K"]["current_filing"]["accession"] == "0000000001-26-000002"
    assert tracks["10-Q"]["prior_filing"]["accession"] == "0000000001-26-000003"
    assert tracks["10-Q"]["current_filing"]["accession"] == "0000000001-26-000004"
    assert tracks["10-K"]["current_filing"]["primary_document"]["retrieval"]["status"] == "retrieved"
    assert tracks["10-Q"]["comparison"]["coverage"]["redlines_total"] >= 1
    assert all(item["display_only"] for item in tracks["10-Q"]["comparison"]["findings"])
    triggered = next(
        item for item in tracks["10-Q"]["comparison"]["findings"] if item["state"] == "triggered"
    )
    evidence_blocks = {
        receipt["block_id"]
        for receipt in triggered["evidence_receipts"]
        if receipt.get("block_id")
    }
    embedded_redline_blocks = {
        receipt["block_id"]
        for redline in tracks["10-Q"]["comparison"]["redlines"]
        for receipt in (redline.get("prior_receipt"), redline.get("current_receipt"))
        if receipt and receipt.get("block_id")
    }
    assert evidence_blocks & embedded_redline_blocks


def test_projection_build_has_no_network_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_root, archive_root = _prepare_cache(tmp_path)

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("projection generation must not open the network")

    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests.sessions.Session, "get", blocked)
    projection = build_disclosure_projection(
        raw_root=raw_root,
        archive_root=archive_root,
        ticker="TST",
        cik=1,
        as_of=AS_OF,
        computed_at=COMPUTED_AT,
    )
    assert projection["coverage"]["tracks_ready"] == 2


def test_projection_is_canonical_atomic_private_file(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    path = write_disclosure_projection(tmp_path, projection)

    assert path == disclosure_projection_path(tmp_path, "TST")
    assert read_disclosure_projection(path) == projection
    assert path.read_bytes().endswith(b"\n")
    assert not list(tmp_path.rglob("*.tmp"))


def test_corrupt_submissions_source_fails_closed_instead_of_emitting_projection(tmp_path: Path) -> None:
    raw_root, archive_root = _prepare_cache(tmp_path)
    latest = json.loads((raw_root / "0000000001" / "submissions" / "latest.json").read_text())
    (raw_root / latest["object_path"]).write_bytes(b"not-a-gzip-stream")

    with pytest.raises(DisclosureProjectionError, match="submissions source"):
        build_disclosure_projection(
            raw_root=raw_root,
            archive_root=archive_root,
            ticker="TST",
            cik=1,
            as_of=AS_OF,
            computed_at=COMPUTED_AT,
        )


def _quarter(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": "TST",
        "fiscal_year": 2025,
        "fiscal_quarter": 2,
        "period_end": "2025-06-30",
        "filed": "2025-08-01",
        "revenue": 100.0,
        "gross_profit": 40.0,
        "receivables": 20.0,
        "inventory": 20.0,
        "cfo": 15.0,
        "capex": 10.0,
        "op_income": 15.0,
        "ni": 12.0,
        "contract_liabilities": 5.0,
    }
    row.update(overrides)
    return row


def test_compose_state_adds_optional_projection_without_changing_v1_envelope(tmp_path: Path) -> None:
    projection = _projection(tmp_path)
    write_disclosure_projection(tmp_path, projection)
    q_dir = tmp_path / "data" / "edgar"
    q_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            _quarter(fiscal_year=2024, period_end="2024-06-30", filed="2024-08-01"),
            _quarter(fiscal_year=2025, period_end="2025-06-30", filed="2025-08-01"),
        ]
    ).to_parquet(q_dir / "statements_quarterly.parquet", index=False)

    state = compose_state(tmp_path, generated_at="2026-08-02T00:05:00Z")

    assert state["schema"] == "fundamental_forensics_state.v1"
    assert state["companies"]["TST"]["disclosures"]["projection_id"] == projection["projection_id"]
    assert state["companies"]["TST"]["disclosures"]["authority"] == "review_priority_only"
    assert state["summary"]["disclosure_coverage"]["attached_to_companies"] == 1
    assert state["summary"]["disclosure_coverage"]["tracks_ready"] == 2
    assert state["source"]["basis"] == "repository quarterly and annual EDGAR panels"


def test_compose_state_ignores_invalid_optional_projection_without_breaking_v1(tmp_path: Path) -> None:
    q_dir = tmp_path / "data" / "edgar"
    q_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            _quarter(fiscal_year=2024, period_end="2024-06-30", filed="2024-08-01"),
            _quarter(fiscal_year=2025, period_end="2025-06-30", filed="2025-08-01"),
        ]
    ).to_parquet(q_dir / "statements_quarterly.parquet", index=False)
    bad = tmp_path / "data" / "fundamental_forensics" / "private" / "disclosures" / "TST.json"
    bad.parent.mkdir(parents=True)
    bad.write_text('{"schema":"wrong"}\n', encoding="utf-8")

    state = compose_state(tmp_path, generated_at="2026-08-02T00:05:00Z")

    assert state["schema"] == "fundamental_forensics_state.v1"
    assert "disclosures" not in state["companies"]["TST"]
    assert state["summary"]["disclosure_coverage"]["load_issues"] == ["DisclosureProjectionError"]


def test_disclosure_state_budget_keeps_evidence_heavy_real_filing_scale() -> None:
    # A real AAPL annual + quarterly Inline XBRL pair produced a ~550 KiB
    # bounded projection. That is normal evidence density, not an outlier.
    projection = {"bounded_projection": "x" * (550 * 1024)}

    selected, coverage = _disclosure_budgeted({"SMCI": projection})

    assert MAX_DISCLOSURE_PROJECTION_BYTES == 768 * 1024
    assert selected == {"SMCI": projection}
    assert coverage["too_large"] == 0
