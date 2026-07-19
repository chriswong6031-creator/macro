"""tests/test_marketing_outbox.py — Outbox contract tests (D02 W0).

Covers:
1. Schema round-trip: make_item → validate_item == [] → enqueue "queued" → read_items
2. make_item raises ValueError on bad kind / empty text / empty account
3. Deterministic id: same inputs → same id; differing text → different id
4. Dedupe: enqueue same item twice → "duplicate"; items.jsonl has 1 line
5. Caps: 8 items queued; 9th → "cap_exceeded"; effective_cap config bounds
6. Status transitions: legal chain works; illegal jumps return False + no append
7. Decisions: approve leads to transition; hold leaves queued; unknown/invalid → False
8. emit_from_content_plan: counts, media, gate, day prefix, re-run dedupe
9. Actuator dry-run: subprocess + dryrun_report.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

_FIXED_NOW = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
_AS_OF = "2026-07-19"


def _make_minimal_item(
    tmp_path: Path,
    *,
    account: str = "flagship",
    kind: str = "signal",
    text: str = "Test post about $PLTR hitting breakout.",
    as_of: str = _AS_OF,
    provenance: str = "content_studio",
) -> dict:
    """Build a minimal valid item for tests."""
    from engine.marketing.outbox import make_item
    return make_item(
        account=account,
        kind=kind,
        text=text,
        as_of=as_of,
        provenance=provenance,
        now=_FIXED_NOW,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema round-trip
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_roundtrip(tmp_path):
    from engine.marketing.outbox import make_item, validate_item, enqueue, read_items, SCHEMA_ID

    item = make_item(
        account="flagship",
        kind="signal",
        text="$PLTR breakout at the 200-day.",
        as_of=_AS_OF,
        provenance="content_studio",
        now=_FIXED_NOW,
    )

    # validate_item returns no errors
    errors = validate_item(item)
    assert errors == [], f"Expected no errors, got: {errors}"

    # enqueue returns "queued"
    result = enqueue(item, root=tmp_path)
    assert result == "queued", f"Expected 'queued', got: {result!r}"

    # read_items returns exactly the item we enqueued
    items = read_items(root=tmp_path)
    assert len(items) == 1
    assert items[0]["id"] == item["id"]
    assert items[0]["schema"] == SCHEMA_ID
    assert items[0]["account"] == "flagship"
    assert items[0]["kind"] == "signal"
    assert items[0]["status"] == "queued"
    assert items[0]["text"] == "$PLTR breakout at the 200-day."


# ─────────────────────────────────────────────────────────────────────────────
# 2. make_item raises ValueError on invalid inputs
# ─────────────────────────────────────────────────────────────────────────────

def test_make_item_raises_on_bad_kind():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="kind"):
        make_item(
            account="flagship",
            kind="nonsense_kind",
            text="Some text.",
            as_of=_AS_OF,
            provenance="content_studio",
        )


def test_make_item_raises_on_empty_text():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="text"):
        make_item(
            account="flagship",
            kind="signal",
            text="",
            as_of=_AS_OF,
            provenance="content_studio",
        )


def test_make_item_raises_on_whitespace_text():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="text"):
        make_item(
            account="flagship",
            kind="signal",
            text="   ",
            as_of=_AS_OF,
            provenance="content_studio",
        )


def test_make_item_raises_on_empty_account():
    from engine.marketing.outbox import make_item
    with pytest.raises(ValueError, match="account"):
        make_item(
            account="",
            kind="signal",
            text="Some text.",
            as_of=_AS_OF,
            provenance="content_studio",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Deterministic id
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_id_same_inputs():
    from engine.marketing.outbox import make_item

    item1 = make_item(
        account="flagship", kind="signal",
        text="Price level break.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    item2 = make_item(
        account="flagship", kind="signal",
        text="Price level break.", as_of=_AS_OF,
        provenance="test_harness",  # provenance does NOT affect id
        now=datetime(2020, 1, 1, tzinfo=timezone.utc),  # nor does now
    )
    assert item1["id"] == item2["id"]


def test_deterministic_id_differing_text():
    from engine.marketing.outbox import make_item

    item1 = make_item(
        account="flagship", kind="signal",
        text="Text A.", as_of=_AS_OF,
        provenance="content_studio",
    )
    item2 = make_item(
        account="flagship", kind="signal",
        text="Text B.", as_of=_AS_OF,
        provenance="content_studio",
    )
    assert item1["id"] != item2["id"]


def test_deterministic_id_whitespace_normalized():
    """Whitespace normalization: same text with different internal spacing → same id."""
    from engine.marketing.outbox import make_item

    item1 = make_item(
        account="flagship", kind="signal",
        text="The  market  broke out.", as_of=_AS_OF,
        provenance="content_studio",
    )
    item2 = make_item(
        account="flagship", kind="signal",
        text="The market broke out.", as_of=_AS_OF,
        provenance="content_studio",
    )
    assert item1["id"] == item2["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dedupe
# ─────────────────────────────────────────────────────────────────────────────

def test_dedupe_second_enqueue_returns_duplicate(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    item = make_item(
        account="flagship", kind="signal",
        text="Dedup test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    r1 = enqueue(item, root=tmp_path)
    r2 = enqueue(item, root=tmp_path)
    assert r1 == "queued"
    assert r2 == "duplicate"


def test_dedupe_items_jsonl_has_one_line(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    item = make_item(
        account="flagship", kind="signal",
        text="Dedup test post line count.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    enqueue(item, root=tmp_path)

    items_file = tmp_path / "data" / "marketing" / "outbox" / "items.jsonl"
    lines = [l for l in items_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. Caps
# ─────────────────────────────────────────────────────────────────────────────

def test_cap_8_items_ok_9th_rejected(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    results = []
    for i in range(9):
        item = make_item(
            account="flagship", kind="signal",
            text=f"Cap test post number {i} with unique text here.",
            as_of=_AS_OF,
            provenance="content_studio", now=_FIXED_NOW,
        )
        results.append(enqueue(item, root=tmp_path))

    queued = [r for r in results if r == "queued"]
    cap_exceeded = [r for r in results if r == "cap_exceeded"]
    assert len(queued) == 8, f"Expected 8 queued, got {len(queued)}: {results}"
    assert len(cap_exceeded) == 1, f"Expected 1 cap_exceeded, got {len(cap_exceeded)}: {results}"
    assert results[8] == "cap_exceeded", "9th item must be cap_exceeded"


def test_effective_cap_config_can_lower(tmp_path):
    from engine.marketing.outbox import effective_cap
    assert effective_cap({"outbox": {"max_posts_per_account_per_day": 3}}) == 3


def test_effective_cap_config_cannot_raise_above_8(tmp_path):
    from engine.marketing.outbox import effective_cap
    assert effective_cap({"outbox": {"max_posts_per_account_per_day": 20}}) == 8


def test_effective_cap_default_is_8():
    from engine.marketing.outbox import effective_cap
    assert effective_cap({}) == 8


def test_cap_9th_item_not_written_to_file(tmp_path):
    from engine.marketing.outbox import make_item, enqueue

    for i in range(9):
        item = make_item(
            account="flagship", kind="signal",
            text=f"Cap test item {i} unique payload for file count.",
            as_of=_AS_OF,
            provenance="content_studio", now=_FIXED_NOW,
        )
        enqueue(item, root=tmp_path)

    items_file = tmp_path / "data" / "marketing" / "outbox" / "items.jsonl"
    lines = [l for l in items_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 8, f"Expected 8 lines (cap), got {len(lines)}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Status transitions
# ─────────────────────────────────────────────────────────────────────────────

def test_legal_transition_chain(tmp_path):
    """queued → approved → posted is a legal chain."""
    from engine.marketing.outbox import make_item, enqueue, transition, current_statuses

    item = make_item(
        account="flagship", kind="macro",
        text="Legal chain test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    # queued → approved
    ok1 = transition(item_id, "approved", actor="test", root=tmp_path)
    assert ok1 is True

    # approved → posted
    ok2 = transition(item_id, "posted", actor="test", root=tmp_path)
    assert ok2 is True

    # Fold gives posted
    statuses = current_statuses(root=tmp_path)
    assert statuses[item_id] == "posted"


def test_illegal_jump_queued_to_posted(tmp_path):
    """queued → posted is not a legal transition; must return False and not append."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="signal",
        text="Illegal jump test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    before_count = len(read_ledger(root=tmp_path))
    ok = transition(item_id, "posted", actor="test", root=tmp_path)
    after_count = len(read_ledger(root=tmp_path))

    assert ok is False
    assert after_count == before_count, "Illegal transition must not append to ledger"


def test_illegal_jump_posted_to_anything(tmp_path):
    """posted is a terminal state; no further transitions allowed."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="signal",
        text="Terminal posted state test.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    # Advance to posted
    transition(item_id, "approved", actor="test", root=tmp_path)
    transition(item_id, "posted", actor="test", root=tmp_path)

    before_count = len(read_ledger(root=tmp_path))
    ok = transition(item_id, "approved", actor="test", root=tmp_path)
    after_count = len(read_ledger(root=tmp_path))

    assert ok is False
    assert after_count == before_count


def test_illegal_jump_approved_to_queued(tmp_path):
    """approved → queued is not a valid transition."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="signal",
        text="Approved back to queued test.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    transition(item_id, "approved", actor="test", root=tmp_path)
    before_count = len(read_ledger(root=tmp_path))
    ok = transition(item_id, "queued", actor="test", root=tmp_path)
    after_count = len(read_ledger(root=tmp_path))

    assert ok is False
    assert after_count == before_count


def test_ledger_only_grows(tmp_path):
    """Append-only assertion: ledger line count only ever increases."""
    from engine.marketing.outbox import make_item, enqueue, transition, read_ledger

    item = make_item(
        account="flagship", kind="event",
        text="Append-only ledger test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    counts: list[int] = []
    counts.append(len(read_ledger(root=tmp_path)))  # 0 before any transition

    transition(item_id, "approved", actor="test", root=tmp_path)
    counts.append(len(read_ledger(root=tmp_path)))

    transition(item_id, "posted", actor="test", root=tmp_path)
    counts.append(len(read_ledger(root=tmp_path)))

    # Illegal transitions (terminal state)
    transition(item_id, "queued", actor="test", root=tmp_path)
    counts.append(len(read_ledger(root=tmp_path)))

    # Verify monotonically non-decreasing
    for i in range(1, len(counts)):
        assert counts[i] >= counts[i - 1], (
            f"Ledger shrank at step {i}: {counts[i - 1]} → {counts[i]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Decisions
# ─────────────────────────────────────────────────────────────────────────────

def test_approve_decision_then_transition(tmp_path):
    """record_decision('approve') → actuator can transition to approved."""
    from engine.marketing.outbox import (
        make_item, enqueue, record_decision, latest_decisions, transition, current_statuses
    )

    item = make_item(
        account="flagship", kind="signal",
        text="Operator approve test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    ok = record_decision(item_id, "approve", actor="operator", root=tmp_path)
    assert ok is True

    # Actuator reads decision and applies it
    dec = latest_decisions(root=tmp_path)
    assert dec[item_id]["decision"] == "approve"

    # Actuator transitions to approved
    ok2 = transition(item_id, "approved", actor="actuator", root=tmp_path)
    assert ok2 is True

    statuses = current_statuses(root=tmp_path)
    assert statuses[item_id] == "approved"


def test_hold_decision_leaves_queued(tmp_path):
    """record_decision('hold') must leave status as queued."""
    from engine.marketing.outbox import (
        make_item, enqueue, record_decision, current_statuses
    )

    item = make_item(
        account="flagship", kind="signal",
        text="Operator hold test post.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    record_decision(item_id, "hold", actor="operator", root=tmp_path)
    # No transition called — status remains queued
    statuses = current_statuses(root=tmp_path)
    assert statuses[item_id] == "queued"


def test_record_decision_unknown_id_returns_false(tmp_path):
    from engine.marketing.outbox import record_decision

    ok = record_decision("ob-2026-07-19-nonexistent", "approve", actor="operator", root=tmp_path)
    assert ok is False


def test_record_decision_invalid_decision_returns_false(tmp_path):
    from engine.marketing.outbox import make_item, enqueue, record_decision

    item = make_item(
        account="flagship", kind="signal",
        text="Invalid decision string test.", as_of=_AS_OF,
        provenance="content_studio", now=_FIXED_NOW,
    )
    enqueue(item, root=tmp_path)
    item_id = item["id"]

    ok = record_decision(item_id, "publish", actor="operator", root=tmp_path)
    assert ok is False


# ─────────────────────────────────────────────────────────────────────────────
# 8. emit_from_content_plan
# ─────────────────────────────────────────────────────────────────────────────

def _make_plan_fixture(as_of: str = _AS_OF) -> dict:
    """Build a minimal content plan fixture.

    D1 items:
      - item 1: clean, D1-AM, no chart → should be emitted
      - item 2: clean, D1-PM, no chart → should be emitted
      - item 3: clean, D1-EOD, chart_id "chart-001" matching a featured chart → should be emitted
    Gate item:
      - item 4: D1-AM, has _live_gate_fail → skipped_gate
    D2 item:
      - item 5: D2-AM → not in D1 prefix, not emitted
    """
    tiny_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'

    return {
        "as_of": as_of,
        "accounts": [
            {
                "id": "flagship",
                "queue": [
                    {
                        "id": "post-flagship-001",
                        "type": "signal",
                        "account": "flagship",
                        "cashtag": "$PLTR",
                        "ticker": "PLTR",
                        "headline": "PLTR reclaimed the 50-day.",
                        "body": "First session above the 50-day since April.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D1-AM",
                        "status": "drafted",
                    },
                    {
                        "id": "post-flagship-002",
                        "type": "macro",
                        "account": "flagship",
                        "cashtag": "",
                        "ticker": "",
                        "headline": "Rate path update.",
                        "body": "Fed futures pricing 2 cuts by December.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D1-PM",
                        "status": "drafted",
                    },
                    {
                        "id": "post-flagship-003",
                        "type": "chart",
                        "account": "flagship",
                        "cashtag": "$NVDA",
                        "ticker": "NVDA",
                        "headline": "NVDA weekly setup.",
                        "body": "Chart shows compression at the highs.",
                        "provenance": "neural_web",
                        "chart_id": "chart-001",
                        "slot": "D1-EOD",
                        "status": "drafted",
                    },
                    {
                        "id": "post-flagship-004",
                        "type": "signal",
                        "account": "flagship",
                        "cashtag": "$SBUX",
                        "ticker": "SBUX",
                        "headline": "SBUX stale signal.",
                        "body": "Signal is 17 days old.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D1-AM",
                        "status": "drafted",
                        "_live_gate_fail": "signal is 17d old (max 10d)",
                    },
                    {
                        "id": "post-flagship-005",
                        "type": "education",
                        "account": "flagship",
                        "cashtag": "",
                        "ticker": "",
                        "headline": "D2 explainer post.",
                        "body": "This is scheduled for tomorrow.",
                        "provenance": "neural_web",
                        "chart_id": None,
                        "slot": "D2-AM",
                        "status": "drafted",
                    },
                ],
            }
        ],
        "featured_charts": [
            {
                "id": "chart-001",
                "ticker": "NVDA",
                "account": "flagship",
                "cashtag": "$NVDA",
                "marker_source": "signal",
                "marker_date": as_of,
                "marker_price": 950.0,
                "svg": tiny_svg,
                "headline": "NVDA Setup",
                "body": "Compression at highs.",
                "source": "prophet",
                "combo_id": None,
            }
        ],
    }


def test_emit_counts(tmp_path):
    """3 clean D1 items emitted; 1 skipped_gate; D2 item not emitted."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    result = emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    assert result["emitted"] == 3, f"Expected 3 emitted, got: {result}"
    assert result["skipped_gate"] == 1, f"Expected 1 skipped_gate, got: {result}"
    assert result["skipped_dupe"] == 0
    assert result["skipped_invalid"] == 0
    # D2 item is not counted anywhere (not in D1 prefix)
    total_accounted = (
        result["emitted"] + result["skipped_gate"] +
        result["skipped_dupe"] + result["skipped_cap"] + result["skipped_invalid"]
    )
    # D1 items: 3 clean + 1 gate = 4 processed; 1 D2 = skipped silently
    assert total_accounted == 4


def test_emit_media_written(tmp_path):
    """Chart item produces an SVG media file at the expected path."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    result = emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    assert result["media_written"] == 1

    svg_path = tmp_path / "data" / "marketing" / "outbox" / "media" / _AS_OF / "chart-001.svg"
    assert svg_path.exists(), f"SVG file not written at {svg_path}"

    content = svg_path.read_text(encoding="utf-8")
    tiny_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'
    assert content == tiny_svg


def test_emit_media_path_repo_relative(tmp_path):
    """Media entry path in the queued item is repo-relative."""
    from engine.marketing.outbox import emit_from_content_plan, read_items

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    items = read_items(root=tmp_path)
    chart_items = [i for i in items if i.get("source", {}).get("chart_id") == "chart-001"]
    assert chart_items, "No item with chart_id=chart-001 found"

    media_list = chart_items[0].get("media") or []
    assert media_list, "Chart item has no media"
    path = media_list[0]["path"]
    # Must be repo-relative (not absolute)
    assert not path.startswith("/"), f"path must be repo-relative; got: {path}"
    assert "outbox/media" in path


def test_emit_rerun_gives_skipped_dupe(tmp_path):
    """Second emit call: all previously emitted items are duplicates."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    r1 = emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")
    r2 = emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    assert r1["emitted"] == 3
    assert r2["emitted"] == 0
    assert r2["skipped_dupe"] == 3, f"Expected 3 skipped_dupe on re-run, got: {r2}"


def test_emit_by_account(tmp_path):
    """by_account tracks emitted count per account."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    result = emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    assert "flagship" in result["by_account"]
    assert result["by_account"]["flagship"] == 3


def test_emit_media_not_rewritten_if_exists(tmp_path):
    """If SVG file already exists, emit does not rewrite it (idempotent)."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    # Overwrite with known content
    svg_path = tmp_path / "data" / "marketing" / "outbox" / "media" / _AS_OF / "chart-001.svg"
    svg_path.write_text("EXISTING_CONTENT", encoding="utf-8")

    # Second run with different plan (but same chart id) — gate bypassed via different items
    plan2 = dict(plan)
    plan2["accounts"] = [{"id": "flagship", "queue": [
        {
            "id": "post-flagship-new-001",
            "type": "chart",
            "account": "flagship",
            "cashtag": "$NVDA",
            "ticker": "NVDA",
            "headline": "New post with same chart.",
            "body": "Different post, same chart.",
            "provenance": "neural_web",
            "chart_id": "chart-001",
            "slot": "D1-AM",
            "status": "drafted",
        }
    ]}]
    emit_from_content_plan(plan2, root=tmp_path, day_prefix="D1")

    # File must retain the overwritten content (not rewritten)
    assert svg_path.read_text(encoding="utf-8") == "EXISTING_CONTENT"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Actuator dry-run (subprocess)
# ─────────────────────────────────────────────────────────────────────────────

def test_actuator_no_dry_run_flag_exits_2(tmp_path):
    """Without --dry-run: actuator must exit with code 2."""
    result = subprocess.run(
        [sys.executable, "scripts/marketing_actuator.py", "--root", str(tmp_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"Expected exit 2, got {result.returncode}. stderr={result.stderr!r}"
    )
    assert "dry-run" in result.stderr.lower() or "refusing" in result.stderr.lower()


def test_actuator_dry_run_exits_0_and_writes_report(tmp_path):
    """--dry-run exits 0 and produces dryrun_report.json."""
    # Seed the outbox with a few items
    from engine.marketing.outbox import emit_from_content_plan, record_decision, read_items

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    items = read_items(root=tmp_path)
    assert items, "No items seeded"

    # Approve the first item, hold the second
    first_id = items[0]["id"]
    second_id = items[1]["id"]
    record_decision(first_id, "approve", actor="operator", root=tmp_path)
    record_decision(second_id, "hold", actor="operator", root=tmp_path)

    result = subprocess.run(
        [
            sys.executable, "scripts/marketing_actuator.py",
            "--dry-run", "--root", str(tmp_path),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}. stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    report_path = tmp_path / "data" / "marketing" / "outbox" / "dryrun_report.json"
    assert report_path.exists(), "dryrun_report.json not written"

    report = json.loads(report_path.read_text())
    assert report["schema"] == "marketing.outbox.dryrun/v1"
    assert report["dry_run"] is True
    assert "kill_switch" in report
    assert "MARKETING_PUBLISH_ENABLED" in report["kill_switch"]

    # would_post contains the approved item
    would_post_ids = {e["id"] for e in report["would_post"]}
    assert first_id in would_post_ids, (
        f"Approved item {first_id} not in would_post: {would_post_ids}"
    )

    # would_post entries have expected text
    first_entry = next(e for e in report["would_post"] if e["id"] == first_id)
    assert first_entry["chars"] > 0
    assert "text" in first_entry

    # held list contains the held item
    assert second_id in report["held"], (
        f"Held item {second_id} not in report['held']: {report['held']}"
    )

    # Counts are consistent
    counts = report["counts"]
    assert counts["items_total"] == len(items)
    assert counts["approved"] >= 1
    assert counts["held"] >= 1


def test_actuator_dry_run_counts_consistent(tmp_path):
    """Counts in dryrun_report.json are internally consistent."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _make_plan_fixture()
    emit_from_content_plan(plan, root=tmp_path, day_prefix="D1")

    subprocess.run(
        [sys.executable, "scripts/marketing_actuator.py", "--dry-run", "--root", str(tmp_path)],
        cwd=str(ROOT),
        capture_output=True,
    )

    report_path = tmp_path / "data" / "marketing" / "outbox" / "dryrun_report.json"
    report = json.loads(report_path.read_text())
    counts = report["counts"]

    assert counts["items_total"] == 3  # 3 D1 items emitted
    accounted = (
        counts["queued"] + counts["approved"] + counts["posted"] +
        counts["failed"] + counts["quarantined"]
    )
    assert accounted == counts["items_total"], (
        f"Status counts don't add up to items_total: {counts}"
    )
