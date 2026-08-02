"""Deterministic story-packet projection workflow contract.

Press staging deliberately has no workflow here.  The R2 projection can only
move receipt-verified packet catalogs and must remain model-credential-free.
"""
from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/earnings-story-packets.yml"


def test_story_packet_projection_workflow_is_scheduled_and_serialized() -> None:
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "name: earnings-story-packets" in body
    assert "  schedule:" in body
    assert "  workflow_dispatch:" in body
    assert "  contents: read" in body
    assert "group: earnings-story-packets-projection" in body
    assert "cancel-in-progress: false" in body
    assert 'cron: "37 6 * * *"' in body
    assert "--audit-remote" in body


def test_story_packet_projection_accepts_no_tier_and_uses_only_deterministic_transport() -> None:
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "      promote:" in body
    assert "      tier:" not in body
    assert "--tier" not in body
    assert "scripts/refresh_earnings_story_packets.py" in body
    assert "scripts/publish_earnings_evidence_graph_r2.py" in body
    assert "scripts/publish_earnings_story_packets_r2.py" in body
    assert "scripts.refresh_earnings_story_packets" in body
    lowered = body.lower()
    assert "scripts/run_press.py" not in lowered
    assert "scripts.run_press" not in lowered
    assert "press staging" not in lowered
    assert "openai" not in lowered


def test_story_packet_projection_never_receives_model_credentials() -> None:
    body = WORKFLOW.read_text(encoding="utf-8").upper()
    assert "R2_ENDPOINT" in body
    assert "R2_ACCESS_KEY_ID" in body
    assert "R2_SECRET_ACCESS_KEY" in body
    assert "R2_BUCKET" in body
    for forbidden in ("OPENAI", "ANTHROPIC", "CLAUDE", "DEEPSEEK", "KIMI", "GEMINI", "MODEL_API"):
        assert forbidden not in body
