"""Current-code ticker hygiene after the acknowledged ABX/GOLD identity repairs."""
from __future__ import annotations

from pathlib import Path

import yaml

from engine.stock_identity.hygiene import COMPUTE_BLOCKLIST, check_symbol

ROOT = Path(__file__).resolve().parent.parent


def test_gold_is_acked_readable_dealer_tape_not_a_compute_block() -> None:
    verdict = check_symbol("GOLD", repo_root=ROOT)
    assert "GOLD" not in COMPUTE_BLOCKLIST
    assert verdict["compute_eligible"] is True
    assert verdict["blind_eligible"] is False
    assert set(verdict["flags"]) == {"reused_ticker_acked", "symbol_history_note"}
    note = verdict["notes"]["symbol_history_note"]
    for needle in ("Gold.com", "dealer", "1591588", "Barrick", "756894", "B.parquet", "PR #5632"):
        assert needle.lower() in note.lower()


def test_abx_block_is_acked_and_only_preserves_the_sealed_w1_population() -> None:
    verdict = check_symbol("ABX", repo_root=ROOT)
    assert "ABX" in COMPUTE_BLOCKLIST
    assert verdict["compute_eligible"] is False
    assert verdict["blind_eligible"] is False
    assert set(verdict["flags"]) == {"reused_ticker_acked", "compute_blocklisted"}
    reason = verdict["notes"]["compute_blocklisted"]
    for needle in ("acknowledged", "sealed W1", "registered amendment", "Abacus"):
        assert needle in reason
    assert "unacknowledged" not in reason.lower()
    assert "absent from reused_ticker_acks" not in reason


def test_gold_ack_records_the_repaired_consumer_without_quarantining_the_store() -> None:
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    text = cfg["quality"]["reused_ticker_acks"]["GOLD"]
    for needle in ("CONSUMER DEFECT REPAIRED", "PR #5632", "B.parquet", "valid Gold.com instrument"):
        assert needle in text
    for stale in ("KNOWN CONSUMER DEFECT", "NO store file under 'B'", "separate curated act"):
        assert stale not in text
