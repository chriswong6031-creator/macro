"""Real-time Intelligence Desk: packet, persistence, daemon, and UI contracts."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.marketing.intelligence_desk import (
    DESK_SCHEMA,
    PACKET_SCHEMA,
    IntelligenceStore,
    build_story_packet,
    update_intelligence_desk,
)


ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc)


def _item(iid: str, source: str, url: str, *, salience: float = 82.0) -> dict:
    return {
        "id": iid,
        "headline": "Federal Reserve holds rates steady",
        "body_snippet": "The Federal Reserve held its policy rate steady.",
        "url": url,
        "source": source.lower().replace(" ", "_"),
        "source_name": source,
        "published_at": "2026-07-29T17:58:00Z",
        "event_class": "policy",
        "corroboration_class": "hearsay",
        "salience": salience,
        "rank_score": 99.9,
        "_components": {"features": {"novelty": 1.7}},
        "matched": {"tickers": ["SPY"]},
    }


def _packet(iid: str, source: str, url: str, *, source_count: int = 1) -> dict:
    return build_story_packet(
        _item(iid, source, url),
        story={
            "story_id": "story-fed-hold",
            "source_count": source_count,
            "sources_15m": source_count,
            "first_seen": "2026-07-29T17:57:00Z",
            "is_new": source_count == 1,
        },
        now=NOW,
        corr_sources=[f"src:{source}:{i}" for i in range(source_count)],
        draft_text="Federal Reserve holds rates steady — multiple reports",
    )


def test_packet_is_evidence_bound_and_never_exposes_internal_scores():
    packet = _packet("fed-1", "Reuters", "https://reuters.com/fed")
    assert packet["schema"] == PACKET_SCHEMA
    assert packet["stage"] == "developing"
    assert packet["stance"] == "Review the draft"
    assert packet["evidence"][0]["url"] == "https://reuters.com/fed"
    assert packet["drafts"][0]["requires_review"] is True
    rendered = json.dumps(packet)
    assert "rank_score" not in rendered
    assert "_components" not in rendered
    assert "salience" not in rendered
    assert "source_tier" not in rendered


def test_market_context_states_the_honest_session_basis():
    item = _item("fed-2", "Federal Reserve", "https://federalreserve.gov/release")
    quotes = {
        "ts": int(NOW.timestamp() * 1000),
        "quotes": {
            "SPY": {
                "ts": int(NOW.timestamp() * 1000),
                "changePct": 0.8,
            }
        },
    }
    packet = build_story_packet(
        item,
        story={"story_id": "story-fed-hold", "source_count": 1},
        now=NOW,
        draft_text="Federal Reserve holds rates steady",
        quotes_store=quotes,
        tape_cfg={"min_move_pct": 0.4, "staleness_max_s": 1800},
    )
    assert packet["market"]["label"] == "SPY +0.8%"
    assert packet["market"]["basis"] == "session vs prior close"
    assert "since the headline" not in json.dumps(packet).lower()


def test_store_merges_reports_into_one_story_and_promotes_confirmation(tmp_path):
    db = tmp_path / "intelligence.db"
    sink = tmp_path / "intelligence.json"
    first = _packet("fed-1", "Reuters", "https://reuters.com/fed")
    second = _packet(
        "fed-2", "Federal Reserve", "https://federalreserve.gov/release",
        source_count=2,
    )
    update_intelligence_desk(
        [first], root=tmp_path, now=NOW, db_path=db, snapshot_path=sink
    )
    payload = update_intelligence_desk(
        [second],
        root=tmp_path,
        now=NOW + timedelta(minutes=2),
        db_path=db,
        snapshot_path=sink,
    )
    assert payload["schema"] == DESK_SCHEMA
    assert payload["health"]["active_stories"] == 1
    assert payload["health"]["confirmed"] == 1
    story = payload["stories"][0]
    assert story["stage"] == "high_impact"
    assert story["source_count"] >= 2
    assert len(story["evidence"]) == 2
    assert all(not key.startswith("_") for key in story)
    assert json.loads(sink.read_text(encoding="utf-8")) == payload


def test_store_prunes_expired_rows(tmp_path):
    store = IntelligenceStore(tmp_path / "intelligence.db")
    try:
        store.upsert([_packet("fed-1", "Reuters", "https://reuters.com/fed")], now=NOW)
        store.prune(now=NOW + timedelta(hours=80), retention_h=72)
        payload = store.snapshot(now=NOW + timedelta(hours=80))
    finally:
        store.close()
    assert payload["stories"] == []
    assert payload["health"]["state"] == "quiet"


def test_store_never_carries_a_stale_market_stamp_into_a_quiet_update(tmp_path):
    db = tmp_path / "intelligence.db"
    store = IntelligenceStore(db)
    first = _packet("fed-1", "Reuters", "https://reuters.com/fed")
    first["market"] = {
        "label": "SPY +1.0%",
        "basis": "session vs prior close",
        "as_of": "2026-07-29T18:00:00Z",
    }
    quiet = _packet("fed-2", "Reuters", "https://reuters.com/fed-2")
    quiet["market"] = None
    try:
        store.upsert([first], now=NOW)
        store.upsert([quiet], now=NOW + timedelta(minutes=5))
        payload = store.snapshot(now=NOW + timedelta(minutes=5))
    finally:
        store.close()
    assert payload["stories"][0]["market"] is None


def test_long_copy_is_retained_but_not_claimed_as_x_ready():
    packet = build_story_packet(
        _item("fed-long", "Reuters", "https://reuters.com/fed"),
        story={"story_id": "story-long"},
        now=NOW,
        draft_text="x" * 350,
    )
    assert packet["drafts"][0]["shape"] == "long_post"
    assert packet["drafts"][0]["status"] == "needs_edit"


def test_publish_switch_no_longer_disables_intelligence_collection():
    daemon = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(
        encoding="utf-8"
    )
    assert "offline=dry_run" in daemon
    assert "offline=effective_dry" not in daemon
    assert "update_intelligence_desk" in daemon


def test_press_tick_emits_story_packets_even_in_outbound_dry_mode(tmp_path):
    from engine.marketing.press_lane import run_press_tick

    item = {
        "id": "truth:tariff-1",
        "truth_status_id": "tariff-1",
        "source": "trumpstruth",
        "source_name": "Truth Social (via mirror)",
        "source_tier": "mirror",
        "url": "https://example.com/truth/tariff-1",
        "published_at": "2026-07-29T17:58:00Z",
        "headline": "Trump orders new tariffs and export controls on $AAPL and $NVDA",
        "body_snippet": "The president announced tariffs and export controls.",
        "corroboration_class": "direct-quote",
    }
    result = run_press_tick(
        [item],
        root=tmp_path,
        now=NOW,
        cfg={"breaking": {"llm": {"enabled": False}}},
        press_cfg={
            "wire": {
                "flagship_top_k_per_day": 3,
                "flagship_salience_floor": 40,
                "rail_salience_floor": 30,
                "intelligence": {"salience_floor": 30},
                "voice": {"enabled": False},
                "tape": {"enabled": False},
            }
        },
        state={},
        seen_ids=set(),
        dry_run=True,
    )
    assert result["intelligence"]
    packet = result["intelligence"][0]
    assert packet["schema"] == PACKET_SCHEMA
    assert packet["evidence"][0]["event_id"] == "truth:tariff-1"
    assert packet["drafts"], "the rail copy should become a review candidate"


def test_news_page_consumes_story_contract_and_keeps_review_gate_visible():
    template = (ROOT / "templates" / "news.html.j2").read_text(encoding="utf-8")
    assert "'live/intelligence.json'" in template
    assert "intelligence.desk/v1" in template
    assert "Source receipts" in template and "来源依据" in template
    assert "Outbound posting is separate and remains review-gated." in template
    assert "navigator.clipboard.writeText" in template
    # Live payload fields never become HTML.
    block = template.split("// ---- INTELLIGENCE DESK")[1].split(
        "// ---- LIVE WIRE"
    )[0]
    assert ".innerHTML" not in block
    assert "textContent" in block


def test_content_studio_receives_the_live_review_queue_without_a_nightly_plan(tmp_path):
    from admin import marketing

    live_dir = tmp_path / "data" / "marketing" / "press"
    live_dir.mkdir(parents=True)
    payload = {
        "schema": DESK_SCHEMA,
        "updated_at": "2026-07-29T18:00:00Z",
        "health": {"active_stories": 1, "draft_ready": 1},
        "stories": [_packet("fed-1", "Reuters", "https://reuters.com/fed")],
    }
    (live_dir / "intelligence.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    result = marketing.content(root=tmp_path)
    assert result["ok"] is True
    assert result["note"]  # the separate nightly plan is honestly still absent
    assert result["intelligence"]["schema"] == DESK_SCHEMA
    assert result["intelligence"]["stories"][0]["drafts"][0]["status"] == "review"


def test_missing_story_asset_reaches_the_client_as_a_true_404():
    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    err_block = caddy.split("@reg_asset_err {", 1)[1].split("}", 1)[0]
    assert "/live/intelligence.json" in err_block


def test_story_asset_is_registered_news_not_public_data():
    import yaml

    access = yaml.safe_load(
        (ROOT / "config" / "site_access.yml").read_text(encoding="utf-8")
    )
    assert "/live/intelligence.json" in access["free_registered"]["exact"]
    assert "/live/intelligence.json" not in access["public"]["exact"]
