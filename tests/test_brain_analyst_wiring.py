"""Gateway wiring for the Market Analyst doctrine (Analyst OS P0).

What this suite pins (mirrors tests/test_brain_doctrine.py's wiring half):
  1. _analyst_block_for rides on EVERY page (message-routed, page-free) — the
     protocol reaches dashboard chat, not just the Terminal.
  2. The lane dial: fast → tight-sequence paragraph, pro/research → deeper-pass
     paragraph, unknown → block without a dial. The dial never replaces the block.
  3. Leak screen: the analyst banner + module openers are in _LEAK_SENTINELS.
  4. Source order in BOTH loops: technician doctrine → analyst block → language
     directive (the LANGUAGE line must stay last; recency is load-bearing).
  5. Never raises: a broken analyst library degrades to "" — the turn survives.
"""
from __future__ import annotations

import inspect

from engine.neuralweb import analyst_doctrine
from engine.neuralweb import brain_gateway as gw


# ── 1. Every page: block is message-routed, not page-gated ──────────────────

def test_analyst_block_rides_off_terminal():
    block = gw._analyst_block_for("why is TLT down while yields rise today", "fast")
    assert "MARKET ANALYST DOCTRINE" in block
    assert "THE ANALYST PROTOCOL" in block


def test_analyst_block_present_even_for_stable_questions():
    # The protocol is always-on (its freshness law TELLS the model educational
    # questions need no live retrieval — that guidance must be present to act).
    block = gw._analyst_block_for("what is duration?", "fast")
    assert "THE ANALYST PROTOCOL" in block
    # ...but a calm question must not drag in the stress-day playbook.
    assert "STRESS-DAY PLAYBOOK" not in block


# ── 2. Lane dial ─────────────────────────────────────────────────────────────

def test_fast_lane_gets_the_discipline_dial():
    block = gw._analyst_block_for("why is the market down today", "fast")
    assert "DISCIPLINE FOR THIS TURN" in block
    assert "DEPTH FOR THIS TURN" not in block


def test_pro_lane_gets_the_depth_dial():
    block = gw._analyst_block_for("why is the market down today", "pro")
    assert "DEPTH FOR THIS TURN" in block
    assert "DISCIPLINE FOR THIS TURN" not in block


def test_unknown_lane_keeps_the_block_drops_the_dial():
    block = gw._analyst_block_for("why is the market down today", "")
    assert "THE ANALYST PROTOCOL" in block
    assert "FOR THIS TURN" not in block


# ── 3. Leak screen carries the analyst sentinels ─────────────────────────────

def test_leak_sentinels_include_analyst_doctrine():
    for s in analyst_doctrine.LEAK_SENTINELS:
        assert s in gw._LEAK_SENTINELS, f"analyst sentinel missing from leak screen: {s!r}"


# ── 4. Source order in both loops: doctrine → analyst → language ────────────

def _assert_order(src: str) -> None:
    i_doc = src.index("_doctrine_block_for(safe_page, message)")
    i_ana = src.index("_analyst_block_for(message, lane)")
    i_lang = src.index("_language_directive(turn_lang)")
    assert i_doc < i_ana < i_lang


def test_loop_order_nonstream():
    _assert_order(inspect.getsource(gw._run_brain_loop))


def test_loop_order_stream():
    _assert_order(inspect.getsource(gw._run_brain_loop_stream))


# ── 5. Never raises ──────────────────────────────────────────────────────────

def test_analyst_block_degrades_to_empty_on_library_error(monkeypatch):
    def _boom(_msg):
        raise RuntimeError("library on fire")

    monkeypatch.setattr(analyst_doctrine, "route", _boom)
    assert gw._analyst_block_for("why is the market down", "fast") == ""


# ── 6. Market-intel tools: allowlist, schemas, dispatch, tier gate ───────────

def _dispatch(tool_name, params, tmp_path, user_id=""):
    return gw._dispatch_brain_tool(
        tool_name, params, tmp_path, tmp_path, "", user_id=user_id)


def test_intel_tools_in_allowlist_and_schemas(tmp_path):
    assert "get_market_events" in gw._BRAIN_TOOLS
    assert "search_research" in gw._BRAIN_TOOLS
    names = {s["name"] for s in gw._all_brain_tool_schemas(tmp_path)}
    assert {"get_market_events", "search_research"} <= names


def test_get_market_events_dispatches_for_everyone(tmp_path):
    # No user_id (guest turn): events are open — an empty world degrades honestly.
    out = _dispatch("get_market_events", {"window_h": 6, "limit": 3}, tmp_path)
    assert isinstance(out, dict) and "events" in out


def test_get_market_events_survives_junk_model_arguments(tmp_path):
    # The model sometimes emits junk argument types; the module's clamps must see
    # them (dispatch passes raw values through instead of raising on float()).
    out = _dispatch("get_market_events",
                    {"window_h": "soon", "limit": "a few"}, tmp_path)
    assert isinstance(out, dict) and "events" in out
    assert "error" not in out


def test_search_research_gate_guest(tmp_path):
    out = _dispatch("search_research", {"query": "oil shock"}, tmp_path, user_id="")
    assert out.get("error") == "essential_required"


def test_search_research_gate_free_tier(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "_resolve_tier",
                        lambda uid, root=None: {"tier": "free", "status": "active"})
    out = _dispatch("search_research", {"query": "oil shock"}, tmp_path, user_id="u1")
    assert out.get("error") == "essential_required"
    assert out.get("tier") == "free"


def test_search_research_serves_essential_and_pro(tmp_path, monkeypatch):
    import json
    cat_dir = tmp_path / "data" / "research_vault"
    cat_dir.mkdir(parents=True)
    (cat_dir / "catalog.json").write_text(json.dumps({
        "schema": "research_vault.catalog.v1", "count": 1,
        "items": [{"id": "x1", "title": "Oil shock playbook", "institution": "GS",
                   "side": "sell", "published_at": "2026-07-29T00:00:00Z",
                   "summary_points": ["Supply risk repricing"], "tags": [],
                   "tickers": [], "top_pick": False, "pages": 3, "language": "en"}],
    }))
    # 'insider' is the PRE-RENAME spelling a grandfathered entitlement row still carries;
    # the gate normalises it, so both must open the door.
    for tier in ("essential", "insider", "pro"):
        monkeypatch.setattr(gw, "_resolve_tier",
                            lambda uid, root=None, _t=tier: {"tier": _t, "status": "active"})
        out = _dispatch("search_research", {"query": "oil shock"}, tmp_path, user_id="u1")
        assert out.get("results"), f"tier {tier} should get results"
        assert out["results"][0]["title"] == "Oil shock playbook"


# ── 7. Grounding digest threads the turn language into the packet ───────────

def test_grounding_digest_threads_lang(tmp_path, monkeypatch):
    from engine.neuralweb import market_packet as mp
    seen = {}

    def _capture(root, char_budget=4200, lang="en"):
        seen["lang"] = lang
        return "[CURRENT DASHBOARD STATE] stub"

    monkeypatch.setattr(mp, "digest", _capture)
    out = gw._grounding_digest(tmp_path, lang="zh")
    assert seen["lang"] == "zh"
    assert out.startswith("[CURRENT DASHBOARD STATE]")


# ── 8. Analyst OS W2 — depth tools: analogues (gated) + curve detail (open) ──

def test_w2_tools_in_allowlists():
    assert "get_historical_analogues" in gw._BRAIN_TOOLS
    assert "get_curve_detail" in gw._BRAIN_TOOLS
    assert "get_historical_analogues" in gw._BRAIN_ONLY_TOOLS
    assert "get_curve_detail" in gw._BRAIN_ONLY_TOOLS


def test_w2_tools_in_schemas(tmp_path):
    names = {s["name"] for s in gw._all_brain_tool_schemas(tmp_path)}
    assert {"get_historical_analogues", "get_curve_detail"} <= names


def test_w2_tool_labels_bilingual():
    for name in ("get_historical_analogues", "get_curve_detail"):
        en, zh = gw._TOOL_LABELS[name]
        assert en and zh and en != zh


def test_analogues_gate_guest(tmp_path):
    out = _dispatch("get_historical_analogues", {}, tmp_path, user_id="")
    assert out.get("error") == "essential_required"


def test_analogues_gate_free_tier(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "_resolve_tier",
                        lambda uid, root=None: {"tier": "free", "status": "active"})
    out = _dispatch("get_historical_analogues", {}, tmp_path, user_id="u1")
    assert out.get("error") == "essential_required"
    assert out.get("tier") == "free"


def test_analogues_essential_reaches_module_and_degrades_honestly(tmp_path, monkeypatch):
    # tmp_path has no parquet estate: the gate passes, the module answers with its
    # own honest unavailable error instead of raising or fabricating episodes.
    monkeypatch.setattr(gw, "_resolve_tier",
                        lambda uid, root=None: {"tier": "insider", "status": "active"})
    out = _dispatch("get_historical_analogues", {"limit": 3}, tmp_path, user_id="u1")
    assert isinstance(out, dict)
    assert out.get("error") == "analogues_unavailable"


def test_curve_detail_open_to_guests_and_degrades_honestly(tmp_path):
    out = _dispatch("get_curve_detail", {}, tmp_path, user_id="")
    assert isinstance(out, dict)
    assert out.get("error") == "curve_detail_unavailable"


def test_seed_plan_curve_and_analogue_nudges():
    plan = gw._seed_tool_plan("why is the yield curve steepening today")
    assert "get_curve_detail" in plan
    plan = gw._seed_tool_plan("when did something similar to this happen before")
    assert "get_historical_analogues" in plan
    # zh triggers ride the same tuples
    plan = gw._seed_tool_plan("历史上有类似的情况吗")
    assert "get_historical_analogues" in plan


# ── 9. Analyst OS W3 — per-user memory tools + preference setter ─────────────

def test_w3_tools_in_allowlists():
    for name in ("recall_sessions", "get_trade_episodes", "set_chat_preference"):
        assert name in gw._BRAIN_TOOLS, name
        assert name in gw._BRAIN_ONLY_TOOLS, name
        en, zh = gw._TOOL_LABELS[name]
        assert en and zh and en != zh


def test_w3_tools_in_schemas(tmp_path):
    names = {s["name"] for s in gw._all_brain_tool_schemas(tmp_path)}
    assert {"recall_sessions", "get_trade_episodes", "set_chat_preference"} <= names


def test_recall_sessions_guest_gets_signin_note(tmp_path):
    out = _dispatch("recall_sessions", {}, tmp_path, user_id="")
    assert out.get("available") is False
    assert "sign in" in (out.get("note") or "")


def test_trade_episodes_guest_gets_signin_note(tmp_path):
    out = _dispatch("get_trade_episodes", {}, tmp_path, user_id="")
    assert out.get("available") is False


def test_set_chat_preference_guest_refused(tmp_path):
    out = _dispatch("set_chat_preference", {"depth": "concise"}, tmp_path, user_id="")
    assert out.get("error") == "signin_required"


def test_recall_sessions_signed_in_reaches_module(tmp_path, monkeypatch):
    from engine.neuralweb import brain_user_memory as bum
    monkeypatch.setattr(bum, "_sb_get", lambda path: [])
    bum.clear_cache()
    out = _dispatch("recall_sessions", {"days": 7, "limit": 3}, tmp_path, user_id="u1")
    assert out.get("schema") == "brain.session_recall.v1"
    bum.clear_cache()


# ── 10. Analyst OS W4 — vault full-report escalation gate (operator ruling) ──

def test_report_mode_essential_gets_pro_required(tmp_path, monkeypatch):
    """Operator ruling 2026-07-31: full reports are PRO-only; Essential keeps summaries.

    The resolver is mocked with the PRE-RENAME spelling on purpose — the reported tier
    must come back canonical, proving the gate normalises rather than echoing a raw row.
    """
    monkeypatch.setattr(gw, "_resolve_tier",
                        lambda uid, root=None: {"tier": "insider", "status": "active"})
    out = _dispatch("search_research",
                    {"mode": "report", "report_id": "x1"}, tmp_path, user_id="u1")
    assert out.get("error") == "pro_required"
    assert out.get("tier") == "essential"


def test_report_mode_pro_reaches_module_with_user_ctx(tmp_path, monkeypatch):
    from engine.neuralweb import brain_market_intel as bmi
    seen = {}

    def _capture(root, query="", limit=5, *, mode="search", report_id="",
                 user_ctx=None, now=None):
        seen.update(mode=mode, report_id=report_id, user_ctx=user_ctx)
        return {"schema": "brain.research_report.v1"}

    monkeypatch.setattr(gw, "_resolve_tier",
                        lambda uid, root=None: {"tier": "pro", "status": "active"})
    monkeypatch.setattr(bmi, "search_research", _capture)
    out = _dispatch("search_research",
                    {"mode": "report", "report_id": "gs-1"}, tmp_path, user_id="u7")
    assert out.get("schema") == "brain.research_report.v1"
    assert seen["mode"] == "report" and seen["report_id"] == "gs-1"
    assert seen["user_ctx"] == {"user_id": "u7"}


def test_search_mode_still_serves_essential_with_no_user_ctx(tmp_path, monkeypatch):
    from engine.neuralweb import brain_market_intel as bmi
    seen = {}

    def _capture(root, query="", limit=5, *, mode="search", report_id="",
                 user_ctx=None, now=None):
        seen.update(mode=mode, user_ctx=user_ctx)
        return {"results": []}

    monkeypatch.setattr(gw, "_resolve_tier",
                        lambda uid, root=None: {"tier": "insider", "status": "active"})
    monkeypatch.setattr(bmi, "search_research", _capture)
    out = _dispatch("search_research", {"query": "oil"}, tmp_path, user_id="u1")
    assert "results" in out
    assert seen["mode"] == "search" and seen["user_ctx"] is None
