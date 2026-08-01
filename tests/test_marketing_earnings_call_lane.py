"""Focused contract tests for the Chronicle -> X earnings-call derivative."""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.chronicle.earnings_calls import make_call_event_id
from engine.marketing import earnings_call_lane as lane


NOW = datetime(2026, 8, 1, 18, 0, 0, tzinfo=timezone.utc)


def _event(**overrides) -> dict:
    row = {
        "schema": "earnings.call_event.v1",
        "id": "",
        "source_record_id": "defeatbeta:TST:2026Q2",
        "ticker": "TST",
        "quarter": "Q2",
        "year": 2026,
        "call_date": "2026-07-31",
        "source_type": "transcript",
        "source_url": "https://app.mastermind-x.com/data/tx/TST/2026Q2.json.gz",
        "source_sha256": "a" * 64,
        "source_updated_at": "2026-07-31T21:00:00Z",
        "scored_at": "2026-07-31T21:05:00Z",
        "model": "qwen3-14b",
        "prompt_version": "equal-v2",
        "analysis_schema_version": "earnings-qual/v2",
        "sentiment": 0.55,
        "performance": 8.0,
        "confidence": 0.91,
        "tone_word": "confident",
        "summary": "Revenue held above plan while management kept full-year guidance.",
        "positive_highlights": ["Demand accelerated across both core segments."],
        "negative_highlights": ["Freight costs remain a near-term margin pressure."],
        "tags": ["demand_acceleration", "margin_contraction"],
        "is_context_only": True,
    }
    row.update(overrides)
    if "id" not in overrides:
        row["id"] = make_call_event_id(row["source_record_id"])
    return row


def _hosted(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def fake_publish(svg, *, chart_id, as_of, root, **_kwargs):
        calls.append({"svg": svg, "chart_id": chart_id, "as_of": as_of, "root": root})
        return {
            "svg_path": f"data/marketing/outbox/media/{as_of}/{chart_id}.svg",
            "media_png_path": f"data/marketing/outbox/media/{as_of}/{chart_id}.png",
            "media_url": f"https://cards.example/{chart_id}.png",
            "media_render": "svg_raster",
        }

    from engine.marketing import media_publish

    monkeypatch.setattr(media_publish, "publish_card", fake_publish)
    return calls


def test_compose_is_deterministic_context_only_and_one_story_identity():
    event = _event()
    first = lane.compose_event(event)
    second = lane.compose_event(event)

    assert first == second
    assert first["story_key"] == "earnings-call:TST:Q2:2026"
    assert first["text"].startswith("$TST Q2 FY2026 call: confident tone.")
    assert "Demand accelerated" in first["text"]
    assert "Freight costs" in first["text"]
    assert "Research context only, not a trading recommendation." in first["text"]
    assert len(first["headline"]) + 1 + len(first["body"]) <= 275


def test_advice_shaped_source_copy_is_not_relayed_and_bad_tone_falls_back():
    event = _event(
        tone_word="validated",
        summary="Buy now and use 44 as the entry level.",
        positive_highlights=[],
        negative_highlights=[],
    )
    composed = lane.compose_event(event)
    assert "mixed tone" in composed["headline"]
    assert "Buy now" not in composed["text"]
    assert "entry level" not in composed["text"]
    assert "trading recommendation" in composed["text"]


def test_non_context_event_is_rejected_even_if_every_other_field_is_valid():
    with pytest.raises(ValueError, match="context-only"):
        lane.compose_event(_event(is_context_only=False))


def test_build_stamps_full_revision_provenance_and_keeps_urls_off_native_copy():
    article = "https://mastermind-x.com/research/tst-q2-call"
    media = [{
        "kind": "chart_svg",
        "path": "data/marketing/outbox/media/call.svg",
        "chart_id": "call",
        "media_url": "https://cards.example/call.png",
    }]
    item = lane.build_outbox_item(
        _event(), account="flagship", now=NOW, media=media, article_url=article,
    )

    assert item["schema"] == "marketing.outbox/v1"
    assert item["kind"] == "earnings"
    assert item["provenance"] == "earnings_call_lane"
    assert item["source"]["story_key"] == "earnings-call:TST:Q2:2026"
    assert item["source"]["event_id"] == _event()["id"]
    assert item["source"]["revision_sha256"] == "a" * 64
    assert item["source"]["source_url"] == _event()["source_url"]
    assert item["source"]["source_record_id"] == "defeatbeta:TST:2026Q2"
    assert item["source"]["article_url"] == article
    assert item["source"]["citation_url"] == article
    assert item["source"]["is_context_only"] is True
    assert item["source"]["value_gate"]["verdict"] == "pass"
    assert "https://" not in item["text"]  # publisher cannot send a self-reply yet


def test_enqueue_routes_through_outbox_and_rerun_dedupes_before_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls = _hosted(monkeypatch)
    first = lane.enqueue_event(_event(), root=tmp_path, now=NOW)
    assert first["status"] == "queued", first
    assert len(calls) == 1
    assert ">EARNINGS CALL</text>" in calls[0]["svg"]
    assert ">BREAKING</text>" not in calls[0]["svg"]

    queued = [
        json.loads(line)
        for line in (tmp_path / "data/marketing/outbox/items.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(queued) == 1
    assert queued[0]["account"] == "flagship"  # wire_routing earnings owner
    assert queued[0]["media"][0]["media_url"].startswith("https://cards.example/")

    second = lane.enqueue_event(_event(), root=tmp_path, now=NOW)
    assert second["status"] == "duplicate"
    assert second["reason"] == "event_revision"
    assert len(calls) == 1, "a rerun burned a card render before dedupe"


def test_story_lock_refuses_a_second_account_before_media_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from engine.marketing import outbox

    other = outbox.make_item(
        account="founder",
        kind="earnings",
        text="$TST prior coverage.",
        as_of=NOW.date().isoformat(),
        provenance="fixture",
        source={"story_key": "earnings-call:TST:Q2:2026"},
        now=NOW,
    )
    assert outbox.enqueue(other, tmp_path, max_per_account_day=-1) == "queued"

    def must_not_publish(*_args, **_kwargs):
        raise AssertionError("story lock ran after media rendering")

    from engine.marketing import media_publish

    monkeypatch.setattr(media_publish, "publish_card", must_not_publish)
    result = lane.enqueue_event(_event(), root=tmp_path, now=NOW)
    assert result["status"] == "story_locked"
    assert result["owner"] == "founder"


def test_unhosted_card_never_enters_the_queue(tmp_path: Path, monkeypatch):
    from engine.marketing import media_publish

    monkeypatch.setattr(media_publish, "publish_card", lambda *_a, **_k: {})
    result = lane.enqueue_event(_event(), root=tmp_path, now=NOW)
    assert result["status"] == "media_unhosted"
    assert not (tmp_path / "data/marketing/outbox/items.jsonl").exists()


def test_dry_run_builds_full_item_without_filesystem_writes(tmp_path: Path):
    result = lane.enqueue_event(_event(), root=tmp_path, now=NOW, dry_run=True)
    assert result["status"] == "dry_run", result
    assert result["item"]["source"]["revision_sha256"] == "a" * 64
    assert not (tmp_path / "data").exists()


def test_ledger_runner_excludes_backfill_and_future_rows_and_caps_recent_batch(tmp_path):
    ledger = tmp_path / "data/chronicle/earnings_call_events.jsonl"
    ledger.parent.mkdir(parents=True)
    rows = [
        _event(
            source_record_id="defeatbeta:OLD:2025Q4",
            ticker="OLD",
            quarter="Q4",
            year=2025,
            call_date="2026-01-15",
            source_url="https://app.mastermind-x.com/data/tx/OLD/2025Q4.json.gz",
            source_sha256="b" * 64,
        ),
        _event(),
        _event(
            source_record_id="defeatbeta:NEW:2026Q2",
            ticker="NEW",
            call_date="2026-08-01",
            source_url="https://app.mastermind-x.com/data/tx/NEW/2026Q2.json.gz",
            source_sha256="c" * 64,
            scored_at="2026-08-01T17:00:00Z",
            source_updated_at="2026-08-01T16:55:00Z",
        ),
        _event(
            source_record_id="defeatbeta:FUT:2026Q3",
            ticker="FUT",
            quarter="Q3",
            call_date="2026-08-02",
            source_url="https://app.mastermind-x.com/data/tx/FUT/2026Q3.json.gz",
            source_sha256="d" * 64,
            scored_at="2026-08-02T17:00:00Z",
            source_updated_at="2026-08-02T16:55:00Z",
        ),
    ]
    ledger.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = lane.run_ledger(root=tmp_path, now=NOW, dry_run=True, max_events=1)
    assert result["input_rows"] == 4
    assert result["eligible_rows"] == 1
    assert result["stale_rows"] == 2  # old + future; TST was eligible but capped
    assert result["capped_rows"] == 1
    assert result["results"][0]["event_id"] == make_call_event_id(
        "defeatbeta:NEW:2026Q2"
    )
    assert result["dry_run"] == 1


def test_lane_has_no_model_or_article_generation_dependency():
    tree = ast.parse(Path(lane.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(
        name.startswith(("openai", "anthropic", "engine.press", "engine.llm"))
        for name in imported
    )
