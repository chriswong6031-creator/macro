from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from engine import earnings_transcript_intake as intake


def _body(text: str = "Café 数据 demand is durable.") -> dict:
    return {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q3",
        "period": "Q3 FY2026",
        "date": "2026-07-30",
        "title": "AAPL earnings call",
        "segments": [{"speaker": "CEO", "role": "CEO", "text": text}],
    }


def _event_id(ticker: str, transcript_id: str) -> str:
    return "cie_" + hashlib.sha256(
        f"{ticker}|{transcript_id[:4]}|Q{transcript_id[-1]}".encode("utf-8")
    ).hexdigest()[:24]


def _write_archive(tmp_path: Path, body: dict) -> tuple[Path, dict]:
    tx_root = tmp_path / "tx"
    body_dir = tx_root / body["ticker"]
    body_dir.mkdir(parents=True)
    with gzip.open(body_dir / f"{body['id']}.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(body, handle, ensure_ascii=False)
    body_sha = intake.canonical_body_sha256(body)
    index = {
        "schema": intake.INDEX_SCHEMA,
        "generated_at": "2026-08-30T12:00:00Z",
        "body_count": 1,
        "symbol_count": 1,
        "symbols": {body["ticker"]: [body["id"]]},
        "revisions": {f"{body['ticker']}/{body['id']}": body_sha},
        "dates": {f"{body['ticker']}/{body['id']}": body["date"]},
    }
    (tx_root / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return tx_root, index


def _ref(body: dict, index: dict, *, start_byte: int | None = None, end_byte: int | None = None) -> dict:
    text = body["segments"][0]["text"]
    encoded = text.encode("utf-8")
    start = 0 if start_byte is None else start_byte
    end = len(encoded) if end_byte is None else end_byte
    document_sha = intake.canonical_body_sha256(body)
    segment_sha = hashlib.sha256(encoded).hexdigest()
    locator = {
        "schema": "mastermind.tx-span-locator/v1",
        "document_key": f"{body['ticker']}/{body['id']}",
        "body_sha256": document_sha,
        "segment_index": 0,
        "start_byte": start,
        "end_byte": end,
        "segment_text_sha256": segment_sha,
    }
    span_id = "txs1_" + hashlib.sha256(
        json.dumps(locator, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "mastermind.research-context-ref/v1",
        "kind": "company_source_span",
        "authority": "context_only",
        "ticker": body["ticker"],
        "event_id": _event_id(body["ticker"], body["id"]),
        "transcript_id": body["id"],
        "revision_id": "txroot-" + intake.canonical_body_sha256(index),
        "document_sha256": document_sha,
        "segment_index": 0,
        "start_byte": start,
        "end_byte": end,
        "segment_text_sha256": segment_sha,
        "span_id": span_id,
    }


def test_resolves_verified_span_and_tolerates_unrelated_root_movement(tmp_path: Path):
    body = _body()
    tx_root, index = _write_archive(tmp_path, body)
    ref = _ref(body, index)
    # The root revision is provenance, not a per-document stale fence.  A different
    # root that still advertises the selected immutable document must resolve.
    ref["revision_id"] = "txroot-" + "0" * 64

    resolved = intake.resolve_company_source_span(ref, tx_root)

    assert resolved.receipt["state"] == "verified"
    assert resolved.receipt["document_sha256"] == ref["document_sha256"]
    assert resolved.evidence_text == body["segments"][0]["text"]
    assert "UNTRUSTED SOURCE EVIDENCE" in resolved.prompt_block


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda ref: ref.update({"excerpt": "browser text"}), "unsupported_context"),
        (lambda ref: ref.update({"event_id": "cie_" + "0" * 24}), "identity_mismatch"),
        (lambda ref: ref.update({"document_sha256": "0" * 64}), "document_hash_mismatch"),
        (lambda ref: ref.update({"segment_text_sha256": "0" * 64}), "segment_hash_mismatch"),
        (lambda ref: ref.update({"span_id": "txs1_" + "0" * 64}), "identity_mismatch"),
    ],
)
def test_refuses_tampered_closed_reference(tmp_path: Path, mutate, code: str):
    body = _body()
    tx_root, index = _write_archive(tmp_path, body)
    ref = _ref(body, index)
    mutate(ref)

    with pytest.raises(intake.CompanySourceSpanError, match=code):
        intake.resolve_company_source_span(ref, tx_root)


def test_refuses_utf8_mid_codepoint_coordinates(tmp_path: Path):
    body = _body()
    tx_root, index = _write_archive(tmp_path, body)
    # "é" occupies bytes 3..4; byte 4 is not a character boundary.
    ref = _ref(body, index, start_byte=0, end_byte=4)

    with pytest.raises(intake.CompanySourceSpanError, match="invalid_coordinates"):
        intake.resolve_company_source_span(ref, tx_root)


def test_missing_current_document_is_stale_not_a_ticker_fallback(tmp_path: Path):
    body = _body()
    tx_root, index = _write_archive(tmp_path, body)
    ref = _ref(body, index)
    index["symbols"] = {"AAPL": []}
    index["body_count"] = 0
    index["revisions"] = {}
    index["dates"] = {}
    (tx_root / "index.json").write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(intake.CompanySourceSpanError, match="stale_revision"):
        intake.resolve_company_source_span(ref, tx_root)
