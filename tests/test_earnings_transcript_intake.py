from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from engine import earnings_transcript_intake as eti


def _body(ticker: str = "AAPL", tx_id: str = "2026Q3", body_text: str = "Revenue rose 10%"):
    return {
        "schema": "mastermind.tx/v1",
        "ticker": ticker,
        "id": tx_id,
        "period": "Q3 FY2026",
        "date": "2026-07-30",
        "title": f"{ticker} Earnings Call Q3 FY2026",
        "segments": [
            {"speaker": "Tim Cook", "role": "CEO", "text": body_text},
            {"speaker": "Analyst", "role": "Analyst", "text": "What changed?"},
        ],
    }


def _index(*bodies: dict, with_extensions: bool = True):
    symbols: dict[str, list[str]] = {}
    revisions: dict[str, str] = {}
    dates: dict[str, str] = {}
    for body in bodies:
        pair = f"{body['ticker']}/{body['id']}"
        symbols.setdefault(body["ticker"], []).append(body["id"])
        revisions[pair] = eti.canonical_body_sha256(body)
        dates[pair] = body["date"]
    out = {
        "schema": eti.INDEX_SCHEMA,
        "generated_at": "2026-08-01T12:00:00+00:00",
        "body_count": len(bodies),
        "symbol_count": len(symbols),
        "symbols": symbols,
    }
    if with_extensions:
        out["revisions"] = revisions
        out["dates"] = dates
    return out


def test_canonical_hash_ignores_json_key_order():
    body = _body()
    reordered = {key: body[key] for key in reversed(list(body))}
    assert eti.canonical_body_sha256(body) == eti.canonical_body_sha256(reordered)


def test_legacy_index_remains_compatible():
    body = _body()
    refs, meta = eti.parse_global_index(_index(body, with_extensions=False))
    assert refs == [eti.TranscriptRef("AAPL", "2026Q3")]
    assert meta["has_revisions"] is False
    assert meta["has_dates"] is False


def test_first_run_seed_existing_is_forward_only():
    body = _body()
    refs, meta = eti.parse_global_index(_index(body))
    state, pending = eti.plan_index(
        refs,
        eti.new_state("https://app.mastermind-x.com/data/tx"),
        metadata=meta,
        seed_existing=True,
    )
    assert state["initialized"] is True
    assert state["known"]["AAPL/2026Q3"] == refs[0].body_sha256
    assert pending == []


def test_first_run_requires_explicit_seed_or_bootstrap():
    refs, meta = eti.parse_global_index(_index(_body()))
    with pytest.raises(ValueError, match="seed_existing"):
        eti.plan_index(refs, eti.new_state("source"), metadata=meta)


def test_bootstrap_since_queues_only_recent_dated_calls():
    recent = _body("AAPL", "2026Q3")
    old = _body("MSFT", "2026Q2")
    old["date"] = "2026-04-25"
    refs, meta = eti.parse_global_index(_index(recent, old))
    state, pending = eti.plan_index(
        refs,
        eti.new_state("source"),
        metadata=meta,
        bootstrap_since="2026-07-24",
    )
    assert [ref.pair for ref in pending] == ["AAPL/2026Q3"]
    assert set(state["known"]) == {"AAPL/2026Q3", "MSFT/2026Q2"}


def test_new_pair_queues_once_and_rerun_is_idempotent():
    first = _body("AAPL", "2026Q2")
    refs1, meta1 = eti.parse_global_index(_index(first))
    state, _ = eti.plan_index(
        refs1, eti.new_state("source"), metadata=meta1, seed_existing=True
    )

    second = _body("AAPL", "2026Q3")
    refs2, meta2 = eti.parse_global_index(_index(first, second))
    state, pending = eti.plan_index(refs2, state, metadata=meta2)
    assert [ref.pair for ref in pending] == ["AAPL/2026Q3"]

    state, pending_again = eti.plan_index(refs2, state, metadata=meta2)
    assert [ref.revision_key for ref in pending_again] == [pending[0].revision_key]
    state = eti.mark_completed(state, pending[0])
    state, after_completion = eti.plan_index(refs2, state, metadata=meta2)
    assert after_completion == []


def test_corrected_hash_requeues_same_stable_pair():
    first = _body()
    refs1, meta1 = eti.parse_global_index(_index(first))
    state, _ = eti.plan_index(
        refs1, eti.new_state("source"), metadata=meta1, seed_existing=True
    )

    corrected = _body(body_text="Revenue rose 12% after a source correction")
    refs2, meta2 = eti.parse_global_index(_index(corrected))
    state, pending = eti.plan_index(refs2, state, metadata=meta2)
    assert len(pending) == 1
    assert pending[0].pair == "AAPL/2026Q3"
    assert pending[0].body_sha256 != refs1[0].body_sha256


def test_hash_extension_rollout_does_not_replay_legacy_archive():
    body = _body()
    legacy_refs, legacy_meta = eti.parse_global_index(_index(body, with_extensions=False))
    state, _ = eti.plan_index(
        legacy_refs,
        eti.new_state("source"),
        metadata=legacy_meta,
        seed_existing=True,
    )
    refs, meta = eti.parse_global_index(_index(body, with_extensions=True))
    state, pending = eti.plan_index(refs, state, metadata=meta)
    assert pending == []
    assert state["known"]["AAPL/2026Q3"] == refs[0].body_sha256


def test_local_body_validation_and_score_mapping(tmp_path: Path):
    body = _body()
    ref = eti.TranscriptRef(
        ticker="AAPL",
        transcript_id="2026Q3",
        body_sha256=eti.canonical_body_sha256(body),
        call_date="2026-07-30",
    )
    body_dir = tmp_path / "AAPL"
    body_dir.mkdir()
    with gzip.open(body_dir / "2026Q3.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(body, handle)

    loaded = eti.read_local_body(tmp_path, ref)
    payload, text = eti.body_to_score_input(
        loaded, index_generated_at="2026-08-01T12:00:00+00:00"
    )
    assert payload["ticker"] == "AAPL"
    assert payload["quarter"] == "Q3"
    assert payload["year"] == 2026
    assert payload["source_record_id"] == "defeatbeta:AAPL:2026Q3"
    assert payload["terminal_url"] == (
        "https://app.mastermind-x.com/data/tx/AAPL/2026Q3.json.gz"
    )
    assert payload["source_revision_sha256"] == ref.body_sha256
    assert "Tim Cook [CEO]: Revenue rose 10%" in text
    assert "Analyst: What changed?" in text


def test_body_hash_mismatch_is_rejected(tmp_path: Path):
    body = _body()
    body_dir = tmp_path / "AAPL"
    body_dir.mkdir()
    with gzip.open(body_dir / "2026Q3.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(body, handle)
    ref = eti.TranscriptRef("AAPL", "2026Q3", "0" * 64, "2026-07-30")
    with pytest.raises(ValueError, match="hash mismatch"):
        eti.read_local_body(tmp_path, ref)


def test_state_write_is_atomic_and_round_trips(tmp_path: Path):
    path = tmp_path / "intake_state.json"
    state = eti.new_state("source")
    state["initialized"] = True
    state["known"] = {"AAPL/2026Q3": ""}
    state["pending"] = [
        {
            "ticker": "AAPL",
            "transcript_id": "2026Q3",
            "body_sha256": "",
            "call_date": "2026-07-30",
        }
    ]
    eti.save_state(path, state)
    loaded = eti.load_state(path, source="source")
    assert loaded["pending"][0]["transcript_id"] == "2026Q3"
    assert not list(tmp_path.glob("*.tmp.*"))


def test_failed_revision_rotates_to_tail_and_survives_replan():
    first = _body("AAPL", "2026Q3")
    second = _body("MSFT", "2026Q3")
    refs, meta = eti.parse_global_index(_index(first, second))
    state, pending = eti.plan_index(
        refs,
        eti.new_state("source"),
        metadata=meta,
        bootstrap_since="2026-07-24",
    )
    failed = pending[0]
    state = eti.mark_failed(state, failed, error="model:invalid_json")
    rotated = [eti.ref_from_pending(item) for item in state["pending"]]
    assert rotated[-1].revision_key == failed.revision_key
    assert state["retry"][failed.revision_key]["attempts"] == 1
    assert state["retry"][failed.revision_key]["last_error"] == "model:invalid_json"

    state, replanned = eti.plan_index(refs, state, metadata=meta)
    assert [ref.revision_key for ref in replanned] == [
        ref.revision_key for ref in rotated
    ]
    state = eti.mark_completed(state, failed)
    assert failed.revision_key not in state["retry"]
