from __future__ import annotations

import json

from engine.company_intelligence.health import enforce_shrink_floor, validate_generation
from engine.company_intelligence.views import build_bundle, write_generation


def _ready_bundle():
    history = [{
        "document_ticker": "AAPL", "fiscal_year": 2026, "fiscal_quarter": 1,
        "call_date": "2026-01-29", "earnings_call_sent": 0.2,
        "raw_source_url": "https://example.test/source",
    }]
    tx = {"schema": "mastermind.tx-index/v1", "documents": [{"ticker": "AAPL", "fiscal_year": 2026, "fiscal_quarter": 1, "present": True}]}
    return build_bundle(history, tx_index=tx, as_of="2026-02-02")


def test_health_checks_manifest_counts_hashes_and_context_schema(tmp_path) -> None:
    contexts, manifest = _ready_bundle()
    generation = write_generation(tmp_path, contexts, manifest)
    healthy = validate_generation(tmp_path)
    assert healthy["status"] == "ready"
    assert healthy["company_count"] == 1 and healthy["event_count"] == 1
    target = generation / "companies" / "AAPL.json"
    target.write_text(json.dumps({"bad": True}), encoding="utf-8")
    degraded = validate_generation(tmp_path)
    assert degraded["status"] == "degraded"
    assert any("file_" in warning for warning in degraded["warnings"])


def test_empty_tree_has_honest_empty_health() -> None:
    health = validate_generation(__import__("pathlib").Path("/definitely/not/company-intelligence"))
    assert health["status"] == "empty"


def test_last_good_shrink_floor_blocks_partial_replacement() -> None:
    prior = {"status": "ready", "company_count": 10, "event_count": 40}
    candidate = {"company_count": 4, "event_count": 39}
    allowed, reason = enforce_shrink_floor(candidate, prior)
    assert not allowed and "company_count" in str(reason)
    assert enforce_shrink_floor({"company_count": 5, "event_count": 20}, prior)[0]
    degraded_prior = {"status": "degraded", "company_count": 10, "event_count": 40}
    assert not enforce_shrink_floor(candidate, degraded_prior)[0]


def test_source_manifest_cardinality_reconciliation_blocks_impossible_projection() -> None:
    candidate = {
        "status": "ready",
        "company_count": 2,
        "event_count": 4,
        "operational": {"history_rows_rejected": 0},
        "source": {
            "earnings_manifest": {
                "observed_counts": {"history_rows": 10, "history_tickers": 5, "score_rows": 5, "score_tickers": 5},
            },
        },
    }
    allowed, reason = enforce_shrink_floor(candidate, None)
    assert not allowed and "ticker reconciliation" in str(reason)
    candidate["company_count"] = 5
    candidate["event_count"] = 11
    allowed, reason = enforce_shrink_floor(candidate, None)
    assert not allowed and "history reconciliation" in str(reason)
    candidate["event_count"] = 4
    assert enforce_shrink_floor(candidate, None)[0]
