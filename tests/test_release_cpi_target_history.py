from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from engine.release_cpi_official_truth import (
    FIRST_PRINT_STATUS,
    CpiSourceSpec,
    build_cpi_not_published_truth,
    build_cpi_official_truth,
    canonical_json_bytes,
)
from engine.release_cpi_target_history import (
    CANDIDATE_TARGET_EPOCH,
    OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
    PREREGISTERED_SAMPLE_SCHEMA,
    WITHHELD_OFFICIAL_TARGET_EPOCH,
    CpiTargetHistoryError,
    CpiTruthParityError,
    build_cpi_target_history,
    evaluate_preregistered_parity,
    load_official_table1_receipts,
)
from engine.release_target_truth import reconstruct_release_target
from scripts.build_release_cpi_truth_parity import (
    build_release_cpi_truth_parity,
)

SERIES = {
    "cpi_headline": "CPIAUCSL",
    "cpi_core": "CPILFESL",
}
GAP_CASE_ID = "gap_2025_02_fixture"
GAP_REASON = "Official CPI result was explicitly not published."
GAP_URL = "https://www.bls.gov/bls/news-release/cpi.htm"
GAP_SOURCE_ID = "bls_cpi_archive_index_fixture"
GAP_STATEMENT = (
    "February 2025 Consumer Price Index – Not published because the fixture "
    "represents an explicit publication gap"
)
GAP_HTML = f"<html><body><p>{GAP_STATEMENT}</p></body></html>".encode()


def _column_name(column: int) -> str:
    value = column + 1
    out = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        out = chr(ord("A") + remainder) + out
    return out


def _table1_xlsx(period: str, headline: float, core: float) -> bytes:
    target = pd.Period(period, freq="M")

    def month_label(value: pd.Period) -> str:
        return value.start_time.strftime("%B %Y")

    rows: list[list[object]] = [
        [
            None,
            "Table 1. Consumer Price Index for All Urban Consumers, "
            + month_label(target),
        ],
        [None, "[1982-84=100, unless otherwise noted]"],
        [],
        [
            "Indent Level",
            "Expenditure category",
            f"Relative importance {month_label(target - 1)}",
            "Unadjusted indexes",
            "Unadjusted indexes",
            "Unadjusted indexes",
            "Unadjusted percent change",
            "Unadjusted percent change",
            "Seasonally adjusted percent change",
            "Seasonally adjusted percent change",
            "Seasonally adjusted percent change",
        ],
        [
            None,
            None,
            None,
            month_label(target - 12),
            month_label(target - 1),
            month_label(target),
            f"{month_label(target - 12)}-{month_label(target)}",
            f"{month_label(target - 1)}-{month_label(target)}",
            f"{month_label(target - 3)}-{month_label(target - 2)}",
            f"{month_label(target - 2)}-{month_label(target - 1)}",
            f"{month_label(target - 1)}-{month_label(target)}",
        ],
        [],
        [0, "All items", 100.0, 300.0, 301.0, 302.0, 2.5, 0.1, 0.1, 0.1, headline],
        [
            1,
            "All items less food and energy",
            75.0,
            310.0,
            311.0,
            312.0,
            2.4,
            0.1,
            0.1,
            0.1,
            core,
        ],
    ]
    worksheet_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column, value in enumerate(row):
            if value is None:
                continue
            ref = f"{_column_name(column)}{row_number}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                escaped = (
                    str(value)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'
                )
        worksheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(worksheet_rows)}</sheetData></worksheet>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.worksheet+xml"/></Types>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for member_name, member_body in (
            ("[Content_Types].xml", content_types),
            ("xl/worksheets/sheet1.xml", sheet),
        ):
            member = zipfile.ZipInfo(
                member_name,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            member.compress_type = zipfile.ZIP_DEFLATED
            member.create_system = 3
            member.external_attr = 0o600 << 16
            archive.writestr(member, member_body)
    return buffer.getvalue()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256((body + "\n").encode("utf-8")).hexdigest()


def _write_stores(
    tmp_path: Path,
    *,
    missing_january_prior: bool = False,
    include_post_gap_release: bool = False,
    include_nonpublication_backfill: bool = False,
) -> tuple[dict[str, Path], Path]:
    base = tmp_path / "data" / "fred_vintage" / "release_targets"
    base.mkdir(parents=True)
    level_sets = {
        "CPIAUCSL": {
            "old": 60.0,
            "oct": 100.0,
            "nov": 100.1,
            "dec_first": 100.4,
            "dec_revised": 100.5,
            "jan": 100.7,
            "feb": 101.0,
            "sep_2025": 102.0,
            "oct_2025_first": 102.3,
            "oct_2025_revised": 102.4,
            "nov_2025": 103.0,
        },
        "CPILFESL": {
            "old": 90.0,
            "oct": 200.0,
            "nov": 200.2,
            "dec_first": 200.6,
            "dec_revised": 200.7,
            "jan": 201.3,
            "feb": 201.7,
            "sep_2025": 204.0,
            "oct_2025_first": 204.5,
            "oct_2025_revised": 204.7,
            "nov_2025": 206.0,
        },
    }
    paths: dict[str, Path] = {}
    manifest_series: dict[str, object] = {}
    for release, series_id in SERIES.items():
        levels = level_sets[series_id]
        rows = [
            # This is ALFRED's bulk-inception state, not a 1960 CPI release.
            ("1960-01-01", "1997-01-01", "9999-12-31", levels["old"]),
            # A prior level whose bulk-inception start is also not a release.
            ("2024-10-01", "1997-01-01", "9999-12-31", levels["oct"]),
            ("2024-11-01", "2024-12-12", "9999-12-31", levels["nov"]),
            ("2024-12-01", "2025-01-15", "2025-02-11", levels["dec_first"]),
            ("2025-01-01", "2025-02-12", "9999-12-31", levels["jan"]),
            ("2025-02-01", "2025-03-12", "9999-12-31", levels["feb"]),
        ]
        if not missing_january_prior:
            rows.append(
                (
                    "2024-12-01",
                    "2025-02-12",
                    "9999-12-31",
                    levels["dec_revised"],
                )
            )
        if include_post_gap_release:
            rows.append(
                (
                    "2025-11-01",
                    "2025-12-18",
                    "9999-12-31",
                    levels["nov_2025"],
                )
            )
        if include_nonpublication_backfill:
            rows.extend(
                [
                    (
                        "2025-09-01",
                        "2025-11-13",
                        "9999-12-31",
                        levels["sep_2025"],
                    ),
                    (
                        "2025-10-01",
                        "2025-11-13",
                        "2025-12-17",
                        levels["oct_2025_first"],
                    ),
                    (
                        "2025-10-01",
                        "2025-12-18",
                        "9999-12-31",
                        levels["oct_2025_revised"],
                    ),
                ]
            )
        frame = pd.DataFrame(
            rows,
            columns=["period", "realtime_start", "realtime_end", "value"],
        )
        frame["series"] = series_id
        frame["source_output_type"] = 2
        path = base / f"{series_id}_all_vintages.parquet"
        frame.to_parquet(path, index=False)
        paths[release] = path
        manifest_series[series_id] = {
            "status": "sealed",
            "path": path.relative_to(tmp_path).as_posix(),
            "rows": len(frame),
            "periods": frame["period"].nunique(),
            "release_dates": frame["realtime_start"].nunique(),
            "period_min": "1960-01-01",
            "period_max": (
                "2025-11-01"
                if include_post_gap_release
                else ("2025-10-01" if include_nonpublication_backfill else "2025-02-01")
            ),
            "artifact_sha256": _sha256(path),
            "artifact_bytes": path.stat().st_size,
        }

    manifest = {
        "schema": "release_target_vintage_collection.v1",
        "integrity_profile": "release_target_artifact_sha256_bytes.v1",
        "status": "ok",
        "mode": "seal_existing",
        "source": "FRED/ALFRED",
        "source_output_type": 2,
        "collected_at": "2025-03-12T13:00:00+00:00",
        "completed_at": "2025-03-12T13:01:00+00:00",
        "series": manifest_series,
    }
    manifest_path = base / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return paths, manifest_path


def _build_history(tmp_path: Path) -> dict[str, object]:
    paths, manifest = _write_stores(tmp_path)
    return build_cpi_target_history(
        vintage_paths=paths,
        manifest_path=manifest,
    )


def _proxy(
    history: dict[str, object],
    release: str,
    period: str,
) -> float:
    rows = history["targets"]
    assert isinstance(rows, list)
    return next(
        float(row["published_proxy_1dp"])
        for row in rows
        if row["release"] == release and row["period"] == period
    )


def _write_metric_receipts(
    path: Path,
    history: dict[str, object],
    *,
    mismatch: bool = False,
    missing_core: bool = False,
) -> None:
    rows = []
    for period, release_date in (
        ("2024-12", "2025-01-15"),
        ("2025-01", "2025-02-12"),
    ):
        headline = _proxy(history, "cpi_headline", period)
        core = _proxy(history, "cpi_core", period)
        if mismatch and period == "2024-12":
            headline += 0.1
        document = _table1_xlsx(period, headline, core)
        url = (
            "https://www.bls.gov/cpi/tables/supplemental-files/"
            f"news-release-table1-{period.replace('-', '')}.xlsx"
        )
        build = build_cpi_official_truth(
            document,
            spec=CpiSourceSpec(period, release_date, url),
        )
        receipt = build.receipt
        if missing_core and period == "2025-01":
            receipt = dict(receipt)
            receipt["targets"] = [
                target
                for target in receipt["targets"]
                if target["release"] != "cpi_core"
            ]
            receipt.pop("receipt_id")
            receipt["receipt_id"] = (
                "cpi_official_truth:" + _canonical_sha256(receipt)[:32]
            )
        rows.append(receipt)
        source = receipt["source"]
        archive_object = (
            path.parent
            / "official_table1_archive"
            / "documents"
            / "sha256"
            / (source["document_sha256"] + source["document_extension"])
        )
        archive_object.parent.mkdir(parents=True, exist_ok=True)
        archive_object.write_bytes(build.document_bytes)
    gap_build = build_cpi_not_published_truth(
        GAP_HTML,
        case_id=GAP_CASE_ID,
        source_id=GAP_SOURCE_ID,
        period="2025-02",
        reason=GAP_REASON,
        source_url=GAP_URL,
        evidence_statement=GAP_STATEMENT,
    )
    rows.append(gap_build.receipt)
    gap_source = gap_build.receipt["source"]
    archive_object = (
        path.parent
        / "official_table1_archive"
        / "documents"
        / "sha256"
        / (gap_source["document_sha256"] + gap_source["document_extension"])
    )
    archive_object.parent.mkdir(parents=True, exist_ok=True)
    archive_object.write_bytes(gap_build.document_bytes)
    path.write_bytes(b"".join(canonical_json_bytes(row) for row in rows))


def _write_preregistered_sample(
    path: Path,
    receipts_path: Path,
) -> None:
    gap_build = build_cpi_not_published_truth(
        GAP_HTML,
        case_id=GAP_CASE_ID,
        source_id=GAP_SOURCE_ID,
        period="2025-02",
        reason=GAP_REASON,
        source_url=GAP_URL,
        evidence_statement=GAP_STATEMENT,
    )
    gap_receipt = gap_build.receipt
    gap_source = gap_receipt["source"]
    published_receipts = {
        receipt["period"]: receipt
        for receipt in (
            json.loads(line)
            for line in receipts_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if receipt["status"] == "ok"
    }
    published_sources = {}
    for period, receipt in published_receipts.items():
        source = receipt["source"]
        published_sources[f"table1_{period.replace('-', '')}"] = {
            "url": source["url"],
            "container_sha256": source["transport_sha256"],
            "container_bytes": source["transport_bytes"],
        }
    payload = {
        "schema": PREREGISTERED_SAMPLE_SCHEMA,
        "frozen_at": "2025-03-12T13:30:00Z",
        "candidate_target_epoch": CANDIDATE_TARGET_EPOCH,
        "official_target_epoch": {
            "target_epoch": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
            "status": "withheld",
            "first_print_status": FIRST_PRINT_STATUS,
        },
        "sources": {
            **published_sources,
            GAP_SOURCE_ID: {
                "url": GAP_URL,
                "container_sha256": gap_source["transport_sha256"],
                "container_bytes": gap_source["transport_bytes"],
                "publisher": "U.S. Bureau of Labor Statistics",
                "host": "www.bls.gov",
                "content_type": "text/html",
            },
        },
        "gate": {
            "published_cases_required": 2,
            "explicit_gap_cases_required": 1,
            "annual_revision_cases_required": 1,
            "ordinary_cases_required": 1,
            "headline_mom_exact_tolerance_pp": 0.0,
            "core_mom_exact_tolerance_pp": 0.0,
            "source_hash_and_length_required": True,
            "manifest_bound_alfred_inputs_required": True,
            "missing_or_unadjudicated_mismatch_policy": "fail_closed",
        },
        "cases": [
            {
                "case_id": "ordinary_2024_12_fixture",
                "period": "2024-12",
                "release_date": "2025-01-15",
                "classification": "ordinary",
                "publication_status": "published",
                "source_id": "table1_202412",
                "member": None,
                "member_sha256": published_receipts["2024-12"]["source"][
                    "document_sha256"
                ],
                "member_bytes": published_receipts["2024-12"]["source"][
                    "document_bytes"
                ],
            },
            {
                "case_id": "annual_revision_2025_01_fixture",
                "period": "2025-01",
                "release_date": "2025-02-12",
                "classification": "annual_revision",
                "publication_status": "published",
                "source_id": "table1_202501",
                "member": None,
                "member_sha256": published_receipts["2025-01"]["source"][
                    "document_sha256"
                ],
                "member_bytes": published_receipts["2025-01"]["source"][
                    "document_bytes"
                ],
            },
            {
                "case_id": GAP_CASE_ID,
                "period": "2025-02",
                "release_date": None,
                # The production preregistration retains the calendar stratum
                # while publication_status supplies the explicit-gap class.
                "classification": "ordinary",
                "publication_status": "not_published",
                "source_id": GAP_SOURCE_ID,
                "reason": GAP_REASON,
                "release_page_url": GAP_URL,
                "evidence_statement": GAP_STATEMENT,
                "evidence_sha256": gap_receipt["source_sha256"],
                "evidence_bytes": gap_source["document_bytes"],
                "receipt_id": gap_receipt["receipt_id"],
                "source_sha256": gap_receipt["source_sha256"],
                "declaration_sha256": gap_source["declaration_sha256"],
                "declaration_bytes": gap_source["declaration_bytes"],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    _write_collection_manifest(
        path.parent / "official_table1_collection.json",
        prereg_path=path,
        receipts_path=receipts_path,
    )


def _write_collection_manifest(
    path: Path,
    *,
    prereg_path: Path,
    receipts_path: Path,
) -> None:
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    receipts = [
        json.loads(line)
        for line in receipts_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases = prereg["cases"]
    assert len(cases) == len(receipts)
    archive = receipts_path.parent / "official_table1_archive"
    archive.mkdir(parents=True, exist_ok=True)
    case_bindings = []
    for case, receipt in zip(cases, receipts, strict=True):
        binding = {
            "case_id": case["case_id"],
            "period": case["period"],
            "publication_status": case["publication_status"],
            "truth_status": receipt["status"],
            "receipt_id": receipt["receipt_id"],
        }
        source = receipt.get("source")
        if receipt.get("schema") == "release_cpi_official_truth.v1":
            binding["source"] = {
                "url": source["url"],
                "member": source.get("member"),
                "transport_sha256": source["transport_sha256"],
                "transport_bytes": source["transport_bytes"],
                "document_sha256": source["document_sha256"],
                "document_bytes": source["document_bytes"],
                "document_object": (
                    "documents/sha256/"
                    + source["document_sha256"]
                    + source["document_extension"]
                ),
            }
        case_bindings.append(binding)
    source_urls = {
        receipt["source"]["url"]
        for receipt in receipts
        if isinstance(receipt.get("source"), dict)
    }
    manifest = {
        "schema": "release_cpi_official_collection_manifest.v1",
        "status": "complete",
        "completed_at": "2025-03-12T14:00:00+00:00",
        "preregistered_sample": {
            "path": prereg_path.name,
            "sha256": _sha256(prereg_path),
            "bytes": prereg_path.stat().st_size,
        },
        "archive": {
            "path": archive.name,
            "transport_retention": "hash_and_length_only",
            "document_retention": "exact_content_addressed_bytes",
        },
        "receipts": {
            "path": receipts_path.name,
            "sha256": _sha256(receipts_path),
            "bytes": receipts_path.stat().st_size,
            "count": len(receipts),
        },
        "counts": {
            "published": sum(
                case["publication_status"] == "published" for case in cases
            ),
            "not_published": sum(
                case["publication_status"] == "not_published" for case in cases
            ),
            "distinct_source_urls": len(source_urls),
        },
        "cases": case_bindings,
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_history_is_sorted_coherent_and_manifest_bound(tmp_path: Path) -> None:
    history = _build_history(tmp_path)

    assert history["target_epoch"] == CANDIDATE_TARGET_EPOCH
    assert history["official_target_epoch"]["name"] == WITHHELD_OFFICIAL_TARGET_EPOCH
    assert history["official_target_epoch"]["status"] == "withheld"
    assert history["n_targets"] == 8
    assert [(row["period"], row["release"]) for row in history["targets"]] == [
        (period, release)
        for period in ("2024-11", "2024-12", "2025-01", "2025-02")
        for release in ("cpi_headline", "cpi_core")
    ]
    assert history["rejected_candidate_rows"]["n"] == 4

    january = next(
        row
        for row in history["targets"]
        if row["release"] == "cpi_headline" and row["period"] == "2025-01"
    )
    assert january["prior_level_same_vintage"] == 100.5
    assert january["latent_change"] == pytest.approx((100.7 / 100.5 - 1) * 100)
    assert january["published_proxy_1dp"] == 0.2
    assert january["provenance"]["current_vintage"]["realtime_start"] == "2025-02-12"
    assert january["provenance"]["prior_vintage"]["realtime_start"] == "2025-02-12"
    assert january["same_release_vintage"] is True
    assert january["cross_vintage_fallback_used"] is False

    artifact = history["source_artifacts"]["CPIAUCSL"]
    source_path = (
        tmp_path / "data" / "fred_vintage" / "release_targets" / artifact["path"]
    )
    assert artifact["artifact_sha256"] == _sha256(source_path)
    assert artifact["artifact_bytes"] == source_path.stat().st_size
    assert artifact["manifest_bound"] is True
    assert artifact["manifest_entry_status"] == "sealed"


def test_history_rejects_parquet_tamper_after_manifest(tmp_path: Path) -> None:
    paths, manifest = _write_stores(tmp_path)
    headline = pd.read_parquet(paths["cpi_headline"])
    headline.loc[headline["period"] == "2025-02-01", "value"] = 999.0
    headline.to_parquet(paths["cpi_headline"], index=False)

    with pytest.raises(CpiTargetHistoryError, match="byte-count|SHA-256"):
        build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)


def test_plausible_release_without_same_vintage_prior_fails_closed(
    tmp_path: Path,
) -> None:
    paths, manifest = _write_stores(tmp_path, missing_january_prior=True)

    with pytest.raises(
        CpiTargetHistoryError, match="same-vintage reconstruction failed"
    ):
        build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)


@pytest.mark.parametrize("include_nonpublication_backfill", [False, True])
def test_source_bound_nonpublication_overrides_alfred_rows_and_followup(
    tmp_path: Path,
    include_nonpublication_backfill: bool,
) -> None:
    paths, manifest = _write_stores(
        tmp_path,
        include_post_gap_release=True,
        include_nonpublication_backfill=include_nonpublication_backfill,
    )
    case_id = "gap_2025_10_source_bound_fixture"
    source_id = "bls_cpi_archive_index"
    reason = "BLS explicitly declared that the October 2025 CPI was not published."
    statement = (
        "October 2025 Consumer Price Index – Not published because of the "
        "fixture appropriations lapse"
    )
    html = f"<html><body>{statement}</body></html>".encode()
    build = build_cpi_not_published_truth(
        html,
        case_id=case_id,
        source_id=source_id,
        period="2025-10",
        reason=reason,
        source_url=GAP_URL,
        evidence_statement=statement,
    )
    receipt = build.receipt
    source = receipt["source"]
    prereg = tmp_path / "preregistered_sample.json"
    prereg.write_text(
        json.dumps(
            {
                "schema": PREREGISTERED_SAMPLE_SCHEMA,
                "frozen_at": "2025-03-12T13:30:00Z",
                "candidate_target_epoch": CANDIDATE_TARGET_EPOCH,
                "official_target_epoch": {
                    "target_epoch": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
                    "status": "withheld",
                    "first_print_status": FIRST_PRINT_STATUS,
                },
                "sources": {
                    source_id: {
                        "url": GAP_URL,
                        "container_sha256": source["transport_sha256"],
                        "container_bytes": source["transport_bytes"],
                        "publisher": "U.S. Bureau of Labor Statistics",
                        "host": "www.bls.gov",
                        "content_type": "text/html",
                    }
                },
                "cases": [
                    {
                        "case_id": case_id,
                        "period": "2025-10",
                        "release_date": None,
                        "classification": "ordinary",
                        "publication_status": "not_published",
                        "source_id": source_id,
                        "reason": reason,
                        "release_page_url": GAP_URL,
                        "evidence_statement": statement,
                        "evidence_sha256": receipt["source_sha256"],
                        "evidence_bytes": source["document_bytes"],
                        "receipt_id": receipt["receipt_id"],
                        "source_sha256": receipt["source_sha256"],
                        "declaration_sha256": source["declaration_sha256"],
                        "declaration_bytes": source["declaration_bytes"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    history = build_cpi_target_history(
        vintage_paths=paths,
        manifest_path=manifest,
        preregistered_sample_path=prereg,
    )

    assert history["known_nonpublications"]["periods"] == ["2025-10"]
    assert history["coverage"]["coherent_targets_rejected_after_nonpublication"] == [
        "2025-11"
    ]
    assert (
        history["rejected_candidate_rows"]["by_reason"][
            "prior_period_officially_not_published"
        ]
        == 2
    )
    if include_nonpublication_backfill:
        for release, series_id in SERIES.items():
            injected = pd.read_parquet(paths[release])
            for period, release_date in (
                ("2025-10", "2025-11-13"),
                ("2025-11", "2025-12-18"),
            ):
                assert (
                    reconstruct_release_target(
                        injected,
                        series_id=series_id,
                        period=period,
                        release_date=release_date,
                    )["status"]
                    == "ok"
                )
        assert (
            history["rejected_candidate_rows"]["by_reason"][
                "period_officially_not_published"
            ]
            == 2
        )
    assert not any(
        row["period"] in {"2025-10", "2025-11"} for row in history["targets"]
    )


def test_metrics_dict_parity_classifies_revision_ordinary_and_gap(
    tmp_path: Path,
) -> None:
    history = _build_history(tmp_path)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)

    parity = evaluate_preregistered_parity(
        history,
        official_receipts_path=receipts,
        preregistered_sample_path=prereg,
    )

    assert parity["status"] == "passed"
    assert parity["candidate_data_asof"] == "2025-03-12T13:01:00+00:00"
    assert parity["evidence_available_at"] == "2025-03-12T14:00:00+00:00"
    assert parity["asof"] == parity["evidence_available_at"]
    assert parity["n_metric_comparisons"] == 4
    assert parity["classifications"] == {
        "annual_revision": 1,
        "explicit_gap": 1,
        "ordinary": 1,
    }
    assert parity["official_target_epoch"] == {
        "name": WITHHELD_OFFICIAL_TARGET_EPOCH,
        "status": "withheld",
        "promotion_authorized": False,
        "reason": (
            "Parity against retrospective official BLS archive editions does "
            "not establish first-published bytes or values, create a complete "
            "official first-print history, or authorize a model/champion change"
        ),
    }
    assert parity["parity_basis"] == {
        "name": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
        "observation_kind": "official_archived_release_edition",
        "description": "official archived release-edition observations",
        "first_print_status": FIRST_PRINT_STATUS,
        "first_publication_evidence_verified": False,
        "deterministic_receipt_rebuild_required": True,
        "deterministic_receipt_rebuild_verified": True,
    }
    assert all(
        "official_archived_release_edition_observation" in comparison
        and "official_first_print" not in comparison
        for case in parity["cases"]
        for comparison in case["comparisons"]
    )
    assert parity["candidate_target_epoch"]["promotion_authorized"] is False
    assert parity["official_receipts"]["aggregate_binding_verified"] is True
    assert parity["official_receipts"]["binding_mode"] == (
        "collection_manifest_exact_ordered_corpus"
    )
    assert (
        parity["official_receipts"]["preregistered_aggregate_binding_verified"] is False
    )
    assert parity["official_receipts"]["ordered_receipt_count"] == 3
    assert (
        parity["official_receipts"]["deterministic_receipt_rebuild_verified_count"] == 3
    )


def test_parity_evidence_clock_uses_latest_normalized_source_clock(
    tmp_path: Path,
) -> None:
    history = _build_history(tmp_path)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    prereg_payload = json.loads(prereg.read_text(encoding="utf-8"))
    # 10:30 at UTC-05 is later than the 14:00Z collection completion.
    prereg_payload["frozen_at"] = "2025-03-12T10:30:00-05:00"
    prereg.write_text(json.dumps(prereg_payload), encoding="utf-8")
    _write_collection_manifest(
        tmp_path / "official_table1_collection.json",
        prereg_path=prereg,
        receipts_path=receipts,
    )

    parity = evaluate_preregistered_parity(
        history,
        official_receipts_path=receipts,
        preregistered_sample_path=prereg,
    )

    assert parity["candidate_data_asof"] == "2025-03-12T13:01:00+00:00"
    assert parity["preregistered_sample"]["frozen_at"] == ("2025-03-12T15:30:00+00:00")
    assert parity["evidence_available_at"] == "2025-03-12T15:30:00+00:00"
    assert parity["asof"] == parity["evidence_available_at"]


@pytest.mark.parametrize("clock_source", ["collector", "preregistered", "collection"])
def test_invalid_governed_evidence_clock_fails_closed(
    tmp_path: Path,
    clock_source: str,
) -> None:
    paths, manifest = _write_stores(tmp_path)
    if clock_source == "collector":
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_payload["completed_at"] = "2025-03-12T13:01:00"
        manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
        with pytest.raises(CpiTargetHistoryError, match="explicit timezone"):
            build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)
        return

    history = build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    if clock_source == "preregistered":
        prereg_payload = json.loads(prereg.read_text(encoding="utf-8"))
        prereg_payload["frozen_at"] = "not-a-clock"
        prereg.write_text(json.dumps(prereg_payload), encoding="utf-8")
    else:
        collection = tmp_path / "official_table1_collection.json"
        collection_payload = json.loads(collection.read_text(encoding="utf-8"))
        collection_payload["completed_at"] = "2025-03-12T14:00:00"
        collection.write_text(json.dumps(collection_payload), encoding="utf-8")

    with pytest.raises(CpiTruthParityError, match="timestamp|explicit timezone"):
        evaluate_preregistered_parity(
            history,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
        )


@pytest.mark.parametrize(
    ("mismatch", "missing_core", "message"),
    [
        (True, False, "parity mismatch"),
        (False, True, "deterministic receipt rebuild mismatch"),
    ],
)
def test_parity_fails_closed_on_mismatch_or_missing_metric(
    tmp_path: Path,
    mismatch: bool,
    missing_core: bool,
    message: str,
) -> None:
    history = _build_history(tmp_path)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(
        receipts,
        history,
        mismatch=mismatch,
        missing_core=missing_core,
    )
    _write_preregistered_sample(prereg, receipts)

    with pytest.raises(CpiTruthParityError, match=message):
        evaluate_preregistered_parity(
            history,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
        )


def test_parity_rejects_receipt_file_changed_after_preregistration(
    tmp_path: Path,
) -> None:
    history = _build_history(tmp_path)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    receipts.write_text(receipts.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(CpiTruthParityError, match="collection manifest"):
        evaluate_preregistered_parity(
            history,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
        )


@pytest.mark.parametrize("mutation", ["reorder", "extra"])
def test_collection_manifest_rejects_reordered_or_extra_receipts(
    tmp_path: Path,
    mutation: str,
) -> None:
    history = _build_history(tmp_path)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    lines = [line for line in receipts.read_text(encoding="utf-8").splitlines() if line]
    if mutation == "reorder":
        lines = list(reversed(lines))
    else:
        extra = json.loads(lines[0])
        extra["period"] = "2024-11"
        extra["receipt_id"] = "fixture:extra"
        lines.append(json.dumps(extra, sort_keys=True))
    receipts.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(CpiTruthParityError, match="collection manifest"):
        evaluate_preregistered_parity(
            history,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("authority", "authority must be false"),
        ("display_only", "display_only must be true"),
        ("parser_selection", "deterministic receipt rebuild mismatch"),
    ],
)
def test_resigned_receipt_tamper_fails_even_with_rebuilt_collection_manifest(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    history = _build_history(tmp_path)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    rows = [
        json.loads(line)
        for line in receipts.read_text(encoding="utf-8").splitlines()
        if line
    ]
    tampered = rows[0]
    if mutation == "authority":
        tampered["authority"] = True
    elif mutation == "display_only":
        tampered["display_only"] = False
    else:
        tampered["parser"]["selection"] = "tampered_governed_selection"
    tampered.pop("receipt_id")
    tampered["receipt_id"] = "cpi_official_truth:" + _canonical_sha256(tampered)[:32]
    receipts.write_bytes(b"".join(canonical_json_bytes(row) for row in rows))
    _write_collection_manifest(
        tmp_path / "official_table1_collection.json",
        prereg_path=prereg,
        receipts_path=receipts,
    )

    with pytest.raises(CpiTruthParityError, match=message):
        evaluate_preregistered_parity(
            history,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
        )


def test_collection_manifest_rejects_missing_retained_document(
    tmp_path: Path,
) -> None:
    history = _build_history(tmp_path)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    retained = next(
        (tmp_path / "official_table1_archive" / "documents" / "sha256").glob("*.html")
    )
    retained.unlink()

    with pytest.raises(
        CpiTruthParityError, match="retained official document is missing"
    ):
        evaluate_preregistered_parity(
            history,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
        )


def test_official_loader_accepts_targets_and_metrics_shapes(tmp_path: Path) -> None:
    path = tmp_path / "receipts.json"
    payload = [
        {
            "period": "2024-12",
            "status": "ok",
            "metrics": {"headline_mom": 0.3, "core_mom": 0.2},
        },
        {
            "period": "2025-01",
            "status": "ok",
            "targets": [
                {"release": "cpi_headline", "mom": 0.2},
                {"release": "cpi_core", "mom": {"value": 0.3}},
            ],
        },
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_official_table1_receipts(path)

    assert loaded[0]["metrics"] == {"cpi_headline": 0.3, "cpi_core": 0.2}
    assert loaded[1]["metrics"] == {"cpi_headline": 0.2, "cpi_core": 0.3}


def test_targets_receipt_is_bound_to_preregistered_source(tmp_path: Path) -> None:
    history = _build_history(tmp_path)
    period = "2024-12"
    release_date = "2025-01-15"
    document_body = _table1_xlsx(
        period,
        _proxy(history, "cpi_headline", period),
        _proxy(history, "cpi_core", period),
    )
    url = (
        "https://www.bls.gov/cpi/tables/supplemental-files/"
        "news-release-table1-202412.xlsx"
    )
    build = build_cpi_official_truth(
        document_body,
        spec=CpiSourceSpec(period, release_date, url),
    )
    receipt = build.receipt
    source = receipt["source"]
    document_sha = source["document_sha256"]
    receipts = tmp_path / "official_table1_receipts.jsonl"
    receipts.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    archive_object = (
        tmp_path
        / "official_table1_archive"
        / "documents"
        / "sha256"
        / f"{document_sha}.xlsx"
    )
    archive_object.parent.mkdir(parents=True)
    archive_object.write_bytes(document_body)
    prereg = tmp_path / "preregistered_sample.json"
    prereg.write_text(
        json.dumps(
            {
                "schema": PREREGISTERED_SAMPLE_SCHEMA,
                "frozen_at": "2025-03-12T13:30:00Z",
                "candidate_target_epoch": CANDIDATE_TARGET_EPOCH,
                "official_target_epoch": {
                    "target_epoch": OFFICIAL_ARCHIVE_OBSERVATION_EPOCH,
                    "status": "withheld",
                    "first_print_status": FIRST_PRINT_STATUS,
                },
                "gate": {
                    "published_cases_required": 1,
                    "explicit_gap_cases_required": 0,
                    "annual_revision_cases_required": 0,
                    "ordinary_cases_required": 1,
                    "headline_mom_exact_tolerance_pp": 0.0,
                    "core_mom_exact_tolerance_pp": 0.0,
                    "source_hash_and_length_required": True,
                    "manifest_bound_alfred_inputs_required": True,
                    "missing_or_unadjudicated_mismatch_policy": "fail_closed",
                },
                "sources": {
                    "direct": {
                        "url": source["url"],
                        "container_sha256": document_sha,
                        "container_bytes": len(document_body),
                    }
                },
                "cases": [
                    {
                        "case_id": "ordinary_2024_12_source_bound",
                        "period": period,
                        "release_date": release_date,
                        "classification": "ordinary",
                        "publication_status": "published",
                        "source_id": "direct",
                        "member": None,
                        "member_sha256": document_sha,
                        "member_bytes": len(document_body),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _write_collection_manifest(
        tmp_path / "official_table1_collection.json",
        prereg_path=prereg,
        receipts_path=receipts,
    )

    parity = evaluate_preregistered_parity(
        history,
        official_receipts_path=receipts,
        preregistered_sample_path=prereg,
    )

    assert parity["status"] == "passed"
    assert parity["official_receipts"]["binding_mode"] == (
        "collection_manifest_exact_ordered_corpus"
    )
    assert parity["official_receipts"]["per_case_source_evidence_verified"] is True
    assert parity["official_receipts"]["per_case_source_evidence_verified_count"] == 1


def test_builder_writes_nothing_when_parity_fails(tmp_path: Path) -> None:
    paths, manifest = _write_stores(tmp_path)
    history = build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)
    receipts = tmp_path / "official_table1_receipts.jsonl"
    prereg = tmp_path / "preregistered_sample.json"
    _write_metric_receipts(receipts, history, mismatch=True)
    _write_preregistered_sample(prereg, receipts)
    history_output = tmp_path / "target_history.json"
    parity_output = tmp_path / "parity.json"
    history_output.write_text("preserve-history", encoding="utf-8")
    parity_output.write_text("preserve-parity", encoding="utf-8")

    with pytest.raises(CpiTruthParityError, match="parity mismatch"):
        build_release_cpi_truth_parity(
            repo_root=tmp_path,
            vintage_paths=paths,
            collector_manifest_path=manifest,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
            history_output_path=history_output,
            parity_output_path=parity_output,
        )

    assert history_output.read_text(encoding="utf-8") == "preserve-history"
    assert parity_output.read_text(encoding="utf-8") == "preserve-parity"


def test_builder_publishes_completion_last_and_binds_cohort(tmp_path: Path) -> None:
    paths, manifest = _write_stores(tmp_path)
    history = build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)
    truth_dir = tmp_path / "data" / "release_forecast" / "cpi_truth"
    truth_dir.mkdir(parents=True)
    receipts = truth_dir / "official_table1_receipts.jsonl"
    prereg = truth_dir / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    history_output = truth_dir / "history.json"
    parity_output = truth_dir / "parity.json"
    completion_output = truth_dir / "completion.json"
    completion_output.write_text("old-complete-marker", encoding="utf-8")

    result = build_release_cpi_truth_parity(
        repo_root=tmp_path,
        vintage_paths=paths,
        collector_manifest_path=manifest,
        official_receipts_path=receipts,
        preregistered_sample_path=prereg,
        history_output_path=history_output,
        parity_output_path=parity_output,
        completion_output_path=completion_output,
    )

    completion = json.loads(completion_output.read_text(encoding="utf-8"))
    parity = json.loads(parity_output.read_text(encoding="utf-8"))
    assert result["status"] == "written"
    assert completion["status"] == "complete"
    assert completion["completion_boundary"] is True
    assert completion["candidate_data_asof"] == "2025-03-12T13:01:00+00:00"
    assert completion["evidence_available_at"] == "2025-03-12T14:00:00+00:00"
    assert completion["asof"] == completion["evidence_available_at"]
    assert completion["history_hash"] == parity["history_hash"]
    assert completion["artifacts"]["history"]["artifact_sha256"] == _sha256(
        history_output
    )
    assert completion["artifacts"]["parity"]["artifact_sha256"] == _sha256(
        parity_output
    )
    receipt_binding = completion["source_bindings"]["official_receipts"]
    assert receipt_binding["aggregate_binding_verified"] is True
    assert receipt_binding["binding_mode"] == (
        "collection_manifest_exact_ordered_corpus"
    )


def test_second_artifact_failure_does_not_publish_completion(tmp_path: Path) -> None:
    paths, manifest = _write_stores(tmp_path)
    history = build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)
    truth_dir = tmp_path / "data" / "release_forecast" / "cpi_truth"
    truth_dir.mkdir(parents=True)
    receipts = truth_dir / "official_table1_receipts.jsonl"
    prereg = truth_dir / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    history_output = truth_dir / "history.json"
    parity_output = truth_dir / "parity.json"
    completion_output = truth_dir / "completion.json"
    completion_output.write_text("old-complete-marker", encoding="utf-8")
    writes: list[Path] = []

    def fail_second(path: Path, body: bytes) -> None:
        writes.append(path)
        if len(writes) == 2:
            raise OSError("injected second-artifact failure")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    with pytest.raises(OSError, match="second-artifact failure"):
        build_release_cpi_truth_parity(
            repo_root=tmp_path,
            vintage_paths=paths,
            collector_manifest_path=manifest,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
            history_output_path=history_output,
            parity_output_path=parity_output,
            completion_output_path=completion_output,
            artifact_writer=fail_second,
        )

    assert writes == [history_output, parity_output]
    assert history_output.is_file()
    assert not parity_output.exists()
    assert not completion_output.exists()


def test_dry_run_preserves_existing_completion_marker(tmp_path: Path) -> None:
    paths, manifest = _write_stores(tmp_path)
    history = build_cpi_target_history(vintage_paths=paths, manifest_path=manifest)
    truth_dir = tmp_path / "data" / "release_forecast" / "cpi_truth"
    truth_dir.mkdir(parents=True)
    receipts = truth_dir / "official_table1_receipts.jsonl"
    prereg = truth_dir / "preregistered_sample.json"
    _write_metric_receipts(receipts, history)
    _write_preregistered_sample(prereg, receipts)
    completion_output = truth_dir / "completion.json"
    completion_output.write_text("old-complete-marker", encoding="utf-8")

    result = build_release_cpi_truth_parity(
        repo_root=tmp_path,
        vintage_paths=paths,
        collector_manifest_path=manifest,
        official_receipts_path=receipts,
        preregistered_sample_path=prereg,
        completion_output_path=completion_output,
        dry_run=True,
    )

    assert result["status"] == "dry_run_passed"
    assert completion_output.read_text(encoding="utf-8") == "old-complete-marker"


def test_history_and_parity_are_byte_stable_across_repo_roots(
    tmp_path: Path,
) -> None:
    results = []
    for name in ("checkout-a", "checkout-b"):
        root = tmp_path / name
        paths, manifest = _write_stores(root)
        preliminary = build_cpi_target_history(
            repo_root=root,
            vintage_paths=paths,
            manifest_path=manifest,
        )
        truth_dir = root / "data" / "release_forecast" / "cpi_truth"
        truth_dir.mkdir(parents=True)
        receipts = truth_dir / "official_table1_receipts.jsonl"
        prereg = truth_dir / "preregistered_sample.json"
        _write_metric_receipts(receipts, preliminary)
        _write_preregistered_sample(prereg, receipts)
        history = build_cpi_target_history(
            repo_root=root,
            vintage_paths=paths,
            manifest_path=manifest,
            preregistered_sample_path=prereg,
        )
        parity = evaluate_preregistered_parity(
            history,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
            repo_root=root,
        )
        cohort = build_release_cpi_truth_parity(
            repo_root=root,
            vintage_paths=paths,
            collector_manifest_path=manifest,
            official_receipts_path=receipts,
            preregistered_sample_path=prereg,
            dry_run=True,
        )
        results.append((history, parity, cohort["completion"]))

    assert results[0] == results[1]
