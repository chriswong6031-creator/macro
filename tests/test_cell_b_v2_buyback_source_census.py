from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "cell_b_v2_buyback_source_census.py"
SPEC = importlib.util.spec_from_file_location("cell_b_v2_buyback_source_census", MODULE_PATH)
assert SPEC and SPEC.loader
census = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = census
SPEC.loader.exec_module(census)


def filing(*, accession: str = "0000000001-24-000001", filed: str = "2024-08-01"):
    return census.FilingRow(
        cik="0000000001",
        company_name="Fixture Operating Company",
        form="8-K",
        filing_date=filed,
        filename=f"edgar/data/1/{accession.replace('-', '')}.txt",
        accession=accession,
    )


def identity():
    return census.IdentityRow(
        economic_issuer_id="ISS:US-XNYS-FIXT",
        security_id="SEC:US-XNYS-FIXT",
        listing_id="US-XNYS-FIXT",
        mic="XNYS",
    )


def metadata(*, items: str = "8.01", sic: str = "3571", accepted: str = "2024-08-01T20:20:00Z"):
    return {
        "items": items,
        "sic": sic,
        "entity_type": "operating",
        "acceptanceDateTime": accepted,
    }


def submission(text: str, *, doc_type: str = "EX-99.1", filename: str = "release.htm") -> bytes:
    return (
        "<SEC-DOCUMENT>fixture\n"
        "<DOCUMENT>\n"
        f"<TYPE>{doc_type}\n"
        "<SEQUENCE>2\n"
        f"<FILENAME>{filename}\n"
        "<DESCRIPTION>Issuer release\n"
        f"<TEXT><html><body>{text}</body></html></TEXT>\n"
        "</DOCUMENT>\n"
        "</SEC-DOCUMENT>"
    ).encode("latin-1")


def clean_source(*, timestamp: str = "August 1, 2024 at 4:15 p.m. EDT") -> bytes:
    return submission(
        f"{timestamp}. The board approved a new common stock repurchase program "
        "authorizing up to $500 million."
    )


def test_sec_acceptance_alone_never_certifies_publication_clock():
    body = submission(
        "The board approved a new common stock repurchase program authorizing up to $500 million."
    )
    row = census.classify_filing(filing(), metadata(accepted="2024-08-01T21:30:00Z"), [identity()], body)
    assert row["refusal_reason"] == "CLOCK_UNESTIMABLE"
    assert row["publication_bucket"] is None


def test_duplicate_filing_exhibit_release_root_counts_once():
    first = census.classify_filing(filing(), metadata(), [identity()], clean_source())
    duplicate = dict(first)
    duplicate["accession"] = "0000000001-24-000002"
    duplicate["source_document_ids"] = ["same-root:release-copy"]
    collapsed = census.collapse_dependence_roots([first, duplicate])
    assert len(collapsed) == 1
    assert collapsed[0]["duplicate_accessions"] == ["0000000001-24-000002"]
    assert len(collapsed[0]["source_document_ids"]) == 2


@pytest.mark.parametrize(
    "words",
    [
        "approved an increase to the common stock repurchase program",
        "approved an extension of the common stock repurchase program",
        "approved an additional common stock repurchase program",
        "approved the remaining common stock repurchase authorization",
    ],
)
def test_increase_extension_additional_or_remaining_is_refused(words):
    body = submission(f"August 1, 2024 at 4:15 p.m. EDT. The board {words} up to $500 million.")
    row = census.classify_filing(filing(), metadata(), [identity()], body)
    assert row["refusal_reason"] == "INCREASE_EXTENSION_RENEWAL_OR_REMAINING"


@pytest.mark.parametrize(
    ("phrase", "reason"),
    [
        ("through a tender offer", "TENDER_ASR_OR_NON_DISCRETIONARY"),
        ("under an accelerated share repurchase agreement", "TENDER_ASR_OR_NON_DISCRETIONARY"),
        ("for preferred stock", "DEBT_PREFERRED_OR_EMPLOYEE_WITHHOLDING"),
        ("through employee tax withholding", "DEBT_PREFERRED_OR_EMPLOYEE_WITHHOLDING"),
    ],
)
def test_tender_accelerated_or_non_common_mechanics_are_refused(phrase, reason):
    body = submission(
        "August 1, 2024 at 4:15 p.m. EDT. The board approved a new common stock "
        f"repurchase program authorizing up to $500 million {phrase}."
    )
    row = census.classify_filing(filing(), metadata(), [identity()], body)
    assert row["refusal_reason"] == reason


def test_bundled_earnings_item_is_refused_before_clock_admission():
    row = census.classify_filing(filing(), metadata(items="2.02,8.01"), [identity()], clean_source())
    assert row["refusal_reason"] == "BUNDLED_EARNINGS_RESULTS_OR_GUIDANCE"


def test_missing_exact_dollar_ceiling_fails_closed():
    body = submission(
        "August 1, 2024 at 4:15 p.m. EDT. The board approved a new common stock repurchase program."
    )
    row = census.classify_filing(filing(), metadata(), [identity()], body)
    assert row["refusal_reason"] == "AMOUNT_UNESTIMABLE"
    assert row["authorization_amount_usd"] is None


def test_completed_purchase_reporting_is_not_a_new_authorization():
    body = submission(
        "During the quarter the company repurchased common stock under its existing repurchase program."
    )
    row = census.classify_filing(filing(), metadata(), [identity()], body)
    assert row["refusal_reason"] == "COMPLETED_PURCHASE_ONLY"


def test_symbol_like_source_text_never_substitutes_for_identity():
    body = submission(
        "August 1, 2024 at 4:15 p.m. EDT. NYSE:FIXT. The board approved a new common "
        "stock repurchase program authorizing up to $500 million."
    )
    row = census.classify_filing(filing(), metadata(), [], body)
    assert row["refusal_reason"] == "IDENTITY_UNESTIMABLE"
    assert row["security_id"] is None


def test_unknown_rights_profile_fails_closed(monkeypatch):
    monkeypatch.setattr(census, "_source_url", lambda *_args: "https://example.invalid/release")
    row = census.classify_filing(filing(), metadata(), [identity()], clean_source())
    assert row["refusal_reason"] == "RIGHTS_UNESTIMABLE"


def test_correction_is_append_only_and_supersedes_parent():
    parent = census.classify_filing(filing(), metadata(), [identity()], clean_source())
    correction = dict(parent)
    correction["episode_id"] = "cell-b-v2:correction"
    correction["correction_of"] = parent["episode_id"]
    corrected = census.apply_correction_supersession([parent, correction])
    assert corrected[0]["superseded_by"] == "cell-b-v2:correction"
    assert corrected[1]["correction_of"] == parent["episode_id"]


def test_master_index_denominator_uses_exact_frozen_range_and_form(tmp_path):
    rows = [
        "1|Before|8-K|2022-02-28|edgar/data/1/000000000122000001.txt",
        "1|First|8-K|2022-03-01|edgar/data/1/0000000001-22-000002.txt",
        "1|Last|8-K|2026-06-30|edgar/data/1/000000000126000003.txt",
        "1|After|8-K|2026-07-01|edgar/data/1/000000000126000004.txt",
        "1|Amended|8-K/A|2024-08-01|edgar/data/1/000000000124000005.txt",
    ]
    body = (
        "Description\nCIK|Company Name|Form Type|Date Filed|Filename\n"
        "----------------------------------------------------------\n"
        + "\n".join(rows)
    )
    archive = tmp_path / "2022-QTR1-master.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("master.idx", body)
    parsed, _receipt = census.parse_master_index_archive(archive)
    assert [row.filing_date for row in parsed] == ["2022-03-01", "2026-06-30"]
    assert all(row.form == "8-K" for row in parsed)


def test_canonical_manifest_serialization_is_byte_identical():
    payload = {"z": [3, 2, 1], "a": {"unicode": "✓", "value": None}}
    first = census.canonical_json_bytes(payload)
    second = census.canonical_json_bytes(json.loads(first))
    assert first == second
    assert census.sha256_bytes(first) == census.sha256_bytes(second)


def test_static_source_and_manifest_contract_contains_no_market_store_paths():
    source = MODULE_PATH.read_text(encoding="utf-8")
    denied_paths = (
        "data/massive_stock_day/",
        "data/stocks/",
        "data/yahoo/",
        "data/baskets/ohlcv/",
        "data/edgar/dead_name_prices.parquet",
    )
    assert all(path not in source for path in denied_paths)
    row = census.classify_filing(filing(), metadata(), [identity()], clean_source())
    encoded = census.canonical_json_bytes(row).decode("utf-8")
    denied_fields = ("abnormal_" + "return", "target_" + "price", "price_" + "derived")
    assert all(field not in encoded for field in denied_fields)


def test_explicit_time_maps_on_early_close_not_hard_coded_regular_close():
    stamp = datetime(2025, 7, 3, 13, 5, tzinfo=ZoneInfo("America/New_York"))
    bucket, session = census.publication_bucket(stamp)
    assert bucket == "AFTER_CLOSE_CERTIFIED"
    assert session == "2025-07-07"


def test_clean_official_source_is_admitted_with_exact_amount_and_span():
    row = census.classify_filing(filing(), metadata(), [identity()], clean_source())
    assert row["status"] == "ADMITTED"
    assert row["authorization_amount_usd"] == 500_000_000
    assert row["publication_bucket"] == "AFTER_CLOSE_CERTIFIED"
    assert row["event_session"] == "2024-08-02"
    assert row["amount_span"]["byte_end"] > row["amount_span"]["byte_start"]
    assert row["rights_profile"]["source_system"] == "sec_edgar"


def test_financial_sic_is_refused():
    row = census.classify_filing(filing(), metadata(sic="6021"), [identity()], clean_source())
    assert row["refusal_reason"] == "FINANCIAL_ISSUER"


def test_only_declared_verdict_vocabulary_is_emitted():
    assert census.verdict_for([]) == "SOURCE_CENSUS_UNDERPOWERED"
    assert (
        census.verdict_for([], identity_or_rights_ceiling_clears_center=True)
        == "SOURCE_CENSUS_IDENTITY_OR_RIGHTS_BLOCKED"
    )
    assert census.verdict_for([]) in census.VERDICTS


def test_earlier_semantic_refusal_does_not_erase_identity_or_public_rights():
    refused = census.classify_filing(
        filing(),
        metadata(),
        [identity()],
        submission(
            "The board approved an increase to the common stock repurchase program up to $500 million."
        ),
    )
    assert refused["economic_issuer_id"] is None
    attached = census.attach_source_plane_receipts(
        [refused],
        {filing().cik: [identity()]},
        [
            {
                "accession": filing().accession,
                "url": "https://www.sec.gov/Archives/edgar/data/1/fixture.txt",
                "sha256": "a" * 64,
            }
        ],
    )[0]
    assert attached["economic_issuer_id"] == identity().economic_issuer_id
    assert attached["rights_profile"]["rights_class"] == "public_source_link"
