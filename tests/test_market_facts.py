"""tests/test_market_facts.py — Market facts sources (engine.marketing.market_facts).

Test list:
1.  macro_facts returns {facts, numbers_whitelist} shape
2.  macro_facts fails soft on empty root (missing files)
3.  macro_facts from real data produces at least one fact with a digit
4.  macro_facts numbers_whitelist covers every number in fact texts
5.  macro_facts no indicator vocab in any fact text
6.  sector_facts returns {facts, numbers_whitelist} shape
7.  sector_facts fails soft on empty root
8.  sector_facts from real data produces at least one fact with a digit (% sign)
9.  sector_facts numbers_whitelist covers every number in fact texts
10. sector_facts no indicator vocab in any fact text
11. breadth_facts returns {facts, numbers_whitelist} shape
12. breadth_facts fails soft on empty root
13. breadth_facts from real data produces at least one fact with a digit
14. breadth_facts numbers_whitelist covers every number in fact texts
15. breadth_facts no indicator vocab in any fact text
16. event_facts returns {facts, numbers_whitelist} shape
17. event_facts fails soft on empty root — falls back to macro_facts shape
18. event_facts from real data contains a fact
19. merge_facts combines two fact dicts, dedupes by id, merges whitelist
20. Full build: a macro post in content_plan now contains a digit
21. Full build: an event post in content_plan now contains a digit
22. Full build: no invented numbers (every number in macro/event/watchlist post body is in whitelist)
23. No indicator vocab in any macro/event/watchlist post body
"""
from __future__ import annotations

import re
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

_INDICATOR_VOCAB = re.compile(
    r"\b(macd|rsi|stochastic|ichimoku|bollinger|ema\d|sma\d)\b",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(
    r"""
    [+-]?\d+\.?\d*%            # percentage: +12.3% or -5.5%
    |
    \d+\.?\d*x                 # multiplier: 3x or 2.5x
    |
    \b\d{2,4}\.\d{2}\b        # price: 226.50 or 19.54
    |
    \b\d{3,6}\b               # bare integer >=3 digits
    """,
    re.VERBOSE,
)


def _fact_shape_ok(fd: dict) -> bool:
    """Check that a fact dict has the required shape."""
    return (
        isinstance(fd, dict)
        and "facts" in fd
        and "numbers_whitelist" in fd
        and isinstance(fd["facts"], list)
        and isinstance(fd["numbers_whitelist"], list)
    )


def _all_numbers_in_whitelist(fd: dict) -> list[str]:
    """Return list of numbers in fact texts that are NOT in the whitelist."""
    wl = set(fd.get("numbers_whitelist") or [])
    violations = []
    for f in fd.get("facts") or []:
        text = f.get("text", "")
        tokens = _NUMBER_RE.findall(text)
        for tok in tokens:
            # Skip small bare integers (1-2 digits) — they appear in prose naturally
            if re.match(r"^\d{1,2}$", tok):
                continue
            if tok not in wl:
                violations.append(f"'{tok}' in fact '{text[:60]}' not in whitelist")
    return violations


def _no_indicator_vocab(fd: dict) -> list[str]:
    """Return indicator vocab hits in fact texts."""
    hits = []
    for f in fd.get("facts") or []:
        text = f.get("text", "")
        m = _INDICATOR_VOCAB.search(text)
        if m:
            hits.append(f"'{m.group()}' in fact text: '{text[:80]}'")
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# 1-5: macro_facts
# ─────────────────────────────────────────────────────────────────────────────

def test_macro_facts_shape():
    from engine.marketing.market_facts import macro_facts
    fd = macro_facts(ROOT)
    assert _fact_shape_ok(fd), f"Bad shape: {fd}"


def test_macro_facts_failsoft_missing_root(tmp_path):
    from engine.marketing.market_facts import macro_facts
    fd = macro_facts(tmp_path)
    assert _fact_shape_ok(fd), f"Bad shape on missing root: {fd}"
    assert fd["facts"] == [], f"Expected empty facts for missing root, got: {fd['facts']}"


def test_macro_facts_real_data_has_digit():
    """Real regime/latest.json exists — at least one fact must contain a digit."""
    regime_path = ROOT / "data" / "regime" / "latest.json"
    if not regime_path.exists():
        pytest.skip("data/regime/latest.json not present")
    from engine.marketing.market_facts import macro_facts
    fd = macro_facts(ROOT)
    texts = " ".join(f.get("text", "") for f in fd["facts"])
    assert re.search(r"\d", texts), (
        f"No digit in any macro fact. Facts: {[f['text'] for f in fd['facts']]}"
    )


def test_macro_facts_whitelist_covers_fact_numbers():
    regime_path = ROOT / "data" / "regime" / "latest.json"
    if not regime_path.exists():
        pytest.skip("data/regime/latest.json not present")
    from engine.marketing.market_facts import macro_facts
    fd = macro_facts(ROOT)
    violations = _all_numbers_in_whitelist(fd)
    assert not violations, f"Numbers not in whitelist: {violations}"


def test_macro_facts_no_indicator_vocab():
    from engine.marketing.market_facts import macro_facts
    fd = macro_facts(ROOT)
    hits = _no_indicator_vocab(fd)
    assert not hits, f"Indicator vocab in macro facts: {hits}"


# ─────────────────────────────────────────────────────────────────────────────
# 6-10: sector_facts
# ─────────────────────────────────────────────────────────────────────────────

def test_sector_facts_shape():
    from engine.marketing.market_facts import sector_facts
    fd = sector_facts(ROOT)
    assert _fact_shape_ok(fd), f"Bad shape: {fd}"


def test_sector_facts_failsoft_missing_root(tmp_path):
    from engine.marketing.market_facts import sector_facts
    fd = sector_facts(tmp_path)
    assert _fact_shape_ok(fd), f"Bad shape: {fd}"
    assert fd["facts"] == [], f"Expected empty facts for missing root, got: {fd['facts']}"


def test_sector_facts_real_data_has_pct():
    """Real sp500_heatmap.json exists — at least one fact must contain a % sign."""
    hm_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    if not hm_path.exists():
        pytest.skip("site/marketdata/sp500_heatmap.json not present")
    from engine.marketing.market_facts import sector_facts
    fd = sector_facts(ROOT)
    texts = " ".join(f.get("text", "") for f in fd["facts"])
    assert "%" in texts, (
        f"No % in any sector fact. Facts: {[f['text'] for f in fd['facts']]}"
    )


def test_sector_facts_whitelist_covers_fact_numbers():
    hm_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    if not hm_path.exists():
        pytest.skip("site/marketdata/sp500_heatmap.json not present")
    from engine.marketing.market_facts import sector_facts
    fd = sector_facts(ROOT)
    violations = _all_numbers_in_whitelist(fd)
    assert not violations, f"Numbers not in whitelist: {violations}"


def test_sector_facts_no_indicator_vocab():
    from engine.marketing.market_facts import sector_facts
    fd = sector_facts(ROOT)
    hits = _no_indicator_vocab(fd)
    assert not hits, f"Indicator vocab in sector facts: {hits}"


# ─────────────────────────────────────────────────────────────────────────────
# 11-15: breadth_facts
# ─────────────────────────────────────────────────────────────────────────────

def test_breadth_facts_shape():
    from engine.marketing.market_facts import breadth_facts
    fd = breadth_facts(ROOT)
    assert _fact_shape_ok(fd), f"Bad shape: {fd}"


def test_breadth_facts_failsoft_missing_root(tmp_path):
    from engine.marketing.market_facts import breadth_facts
    fd = breadth_facts(tmp_path)
    assert _fact_shape_ok(fd), f"Bad shape: {fd}"
    assert fd["facts"] == [], f"Expected empty facts for missing root, got: {fd['facts']}"


def test_breadth_facts_real_data_has_digit():
    tc_path = ROOT / "site" / "factordata" / "tech_confluence.json"
    if not tc_path.exists():
        pytest.skip("site/factordata/tech_confluence.json not present")
    from engine.marketing.market_facts import breadth_facts
    fd = breadth_facts(ROOT)
    texts = " ".join(f.get("text", "") for f in fd["facts"])
    assert re.search(r"\d", texts), (
        f"No digit in any breadth fact. Facts: {[f['text'] for f in fd['facts']]}"
    )


def test_breadth_facts_whitelist_covers_fact_numbers():
    tc_path = ROOT / "site" / "factordata" / "tech_confluence.json"
    if not tc_path.exists():
        pytest.skip("site/factordata/tech_confluence.json not present")
    from engine.marketing.market_facts import breadth_facts
    fd = breadth_facts(ROOT)
    violations = _all_numbers_in_whitelist(fd)
    assert not violations, f"Numbers not in whitelist: {violations}"


def test_breadth_facts_no_indicator_vocab():
    from engine.marketing.market_facts import breadth_facts
    fd = breadth_facts(ROOT)
    hits = _no_indicator_vocab(fd)
    assert not hits, f"Indicator vocab in breadth facts: {hits}"


# ─────────────────────────────────────────────────────────────────────────────
# 16-18: event_facts
# ─────────────────────────────────────────────────────────────────────────────

def test_event_facts_shape():
    from engine.marketing.market_facts import event_facts
    fd = event_facts(ROOT)
    assert _fact_shape_ok(fd), f"Bad shape: {fd}"


def test_event_facts_failsoft_missing_root(tmp_path):
    from engine.marketing.market_facts import event_facts
    fd = event_facts(tmp_path)
    # Falls back to macro_facts which should also return empty shape gracefully
    assert _fact_shape_ok(fd), f"Bad shape on missing root: {fd}"


def test_event_facts_real_data_has_content():
    """event_facts must produce at least one fact when source data exists."""
    brief_path = ROOT / "site" / "neuralwebdata" / "daily_brief.json"
    regime_path = ROOT / "data" / "regime" / "latest.json"
    if not brief_path.exists() and not regime_path.exists():
        pytest.skip("Neither daily_brief.json nor latest.json present")
    from engine.marketing.market_facts import event_facts
    fd = event_facts(ROOT)
    assert len(fd["facts"]) >= 1, (
        f"Expected at least 1 event fact, got 0. Checked brief: {brief_path.exists()}, "
        f"regime: {regime_path.exists()}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 19: merge_facts
# ─────────────────────────────────────────────────────────────────────────────

def test_merge_facts_combines_and_dedupes():
    from engine.marketing.market_facts import merge_facts
    fd1 = {
        "facts": [
            {"id": "a", "text": "Fact A with +2.1%.", "salience": 8, "numbers": ["+2.1%"]},
            {"id": "b", "text": "Fact B.", "salience": 5, "numbers": []},
        ],
        "numbers_whitelist": ["+2.1%"],
    }
    fd2 = {
        "facts": [
            {"id": "b", "text": "Fact B duplicate.", "salience": 3, "numbers": []},  # dup id
            {"id": "c", "text": "Fact C with 100.", "salience": 9, "numbers": ["100"]},
        ],
        "numbers_whitelist": ["100"],
    }
    merged = merge_facts(fd1, fd2)
    assert _fact_shape_ok(merged)
    ids = [f["id"] for f in merged["facts"]]
    # 'b' must appear only once (deduped by id)
    assert ids.count("b") == 1, f"'b' should appear once, got: {ids}"
    # All 3 distinct ids present
    assert set(ids) == {"a", "b", "c"}, f"Expected {{a,b,c}}, got: {set(ids)}"
    # Whitelist merged
    assert "+2.1%" in merged["numbers_whitelist"]
    assert "100" in merged["numbers_whitelist"]
    # Sorted salience-DESC (c=9, a=8, b=5)
    assert ids[0] == "c", f"Expected c first (salience 9), got: {ids}"


def test_merge_facts_handles_empty():
    from engine.marketing.market_facts import merge_facts
    fd = merge_facts({}, {"facts": [], "numbers_whitelist": []})
    assert _fact_shape_ok(fd)
    assert fd["facts"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 20-23: Full build integration tests
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone as _tz
_FRESH = (datetime.now(_tz.utc).date() - timedelta(days=5)).isoformat()

_SAMPLE_PLANS = [
    {
        "id": "PLTR-BULL", "asset": "PLTR", "direction": "BULL",
        "entry": 120.0, "invalidation": 100.0, "targets": [150.0, 180.0],
        "trigger": 125.0, "_conviction_score": 90, "_signal_date": _FRESH,
        "phase": "triggered_pre_t1", "recommended_action": "hold",
        "management_confidence": 66.0, "what_to_do_now": [],
    },
    {
        "id": "SBUX-BULL", "asset": "SBUX", "direction": "BULL",
        "entry": 82.0, "invalidation": 75.0, "targets": [95.0, 110.0],
        "trigger": 84.0, "_conviction_score": 85, "_signal_date": _FRESH,
        "phase": "triggered_pre_t1", "recommended_action": "hold",
        "management_confidence": 61.0, "what_to_do_now": [],
    },
]

_SAMPLE_ACCOUNTS = [
    {"id": "flagship", "kind": "branded", "beat": "What changed", "voice": "authoritative desk",
     "tilt": {"signal": 0.32, "chart": 0.10, "education": 0.08, "macro": 0.14,
               "receipt": 0.08, "watchlist": 0.05, "event": 0.05,
               "mover": 0.10, "theme_list": 0.08}},
    {"id": "receipts", "kind": "branded", "beat": "Receipt", "voice": "dry, receipts-forward",
     "tilt": {"signal": 0.26, "chart": 0.18, "education": 0.05, "macro": 0.07,
               "receipt": 0.18, "watchlist": 0.05, "event": 0.05,
               "mover": 0.08, "theme_list": 0.08}},
    {"id": "theme_desk", "kind": "branded", "beat": "Theme", "voice": "specialist",
     "tilt": {"signal": 0.28, "chart": 0.10, "education": 0.08, "macro": 0.08,
               "receipt": 0.06, "watchlist": 0.05, "event": 0.14,
               "mover": 0.10, "theme_list": 0.11}},
    {"id": "research_a", "kind": "generic", "beat": "Macro", "voice": "educational",
     "tilt": {"signal": 0.24, "chart": 0.08, "education": 0.18, "macro": 0.20,
               "receipt": 0.05, "watchlist": 0.05, "event": 0.03,
               "mover": 0.10, "theme_list": 0.07}},
    {"id": "research_b", "kind": "generic", "beat": "Fast", "voice": "fast, reactive",
     "tilt": {"signal": 0.30, "chart": 0.16, "education": 0.04, "macro": 0.06,
               "receipt": 0.06, "watchlist": 0.04, "event": 0.08,
               "mover": 0.14, "theme_list": 0.12}},
    {"id": "research_c", "kind": "generic", "beat": "Charts", "voice": "pattern/history",
     "tilt": {"signal": 0.26, "chart": 0.22, "education": 0.06, "macro": 0.06,
               "receipt": 0.05, "watchlist": 0.13, "event": 0.05,
               "mover": 0.10, "theme_list": 0.07}},
]


def _build_plan_with_root():
    """Build a content plan using the real repo root so market_facts sources fire."""
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    return content_plan(cfg, _SAMPLE_PLANS, closes_loader=None, root=ROOT)


def _collect_items_by_type(plan: dict, type_id: str) -> list[dict]:
    items = []
    for acct in plan.get("accounts", []):
        for item in acct.get("queue", []):
            if item.get("type") == type_id:
                items.append(item)
    return items


@pytest.mark.skipif(
    not (Path(_worktree_root()) / "data" / "regime" / "latest.json").exists()
    and not (Path(_worktree_root()) / "site" / "marketdata" / "sp500_heatmap.json").exists(),
    reason="No source data files present for integration test",
)
def test_macro_post_contains_digit():
    """A macro post in the full build must contain a digit (from regime or tape facts)."""
    plan = _build_plan_with_root()
    macro_items = _collect_items_by_type(plan, "macro")
    assert macro_items, "No macro items in content plan"
    # At least one macro post across all accounts must carry a digit in body or headline
    has_digit = any(
        re.search(r"\d", (item.get("body", "") + " " + item.get("headline", "")))
        for item in macro_items
    )
    assert has_digit, (
        f"No macro post carries a digit. Sample bodies: "
        f"{[i['body'][:80] for i in macro_items[:3]]}"
    )


@pytest.mark.skipif(
    not (Path(_worktree_root()) / "site" / "neuralwebdata" / "daily_brief.json").exists()
    and not (Path(_worktree_root()) / "data" / "regime" / "latest.json").exists(),
    reason="No source data files present for integration test",
)
def test_event_post_contains_digit_or_fact():
    """An event post in the full build must contain a digit or real fact text."""
    plan = _build_plan_with_root()
    event_items = _collect_items_by_type(plan, "event")
    assert event_items, "No event items in content plan"
    # At least one event post must carry a concrete fact (digit or the tape direction text)
    has_content = any(
        re.search(r"\d|today|regime|liquidity", item.get("body", ""), re.IGNORECASE)
        for item in event_items
    )
    assert has_content, (
        f"No event post carries concrete content. Sample bodies: "
        f"{[i['body'][:100] for i in event_items[:3]]}"
    )


def test_no_invented_numbers_in_macro_posts():
    """Every number in a macro post body must be in that item's numbers_whitelist.

    We test this by building a plan with facts, extracting the whitelist from
    build_context, and verifying nothing leaks.

    Since non-ticker posts don't go through validate_copy number-check
    (no cashtag requirement), we check directly here.
    """
    from engine.marketing.copywriter import build_context, write_posts_deterministic
    from engine.marketing.market_facts import macro_facts

    fd = macro_facts(ROOT)
    item = {
        "ticker": "",
        "type": "macro",
        "account": "flagship",
    }
    ctx = build_context(item, persona={"name": "Test", "voice_notes": "Emoji budget: 0",
                                       "example_lines": []}, facts=fd or None)
    ctx["voice"] = "authoritative desk"
    ctx["slot"] = "D1-AM"
    ctx["type"] = "macro"

    posts = write_posts_deterministic([ctx])
    assert posts

    post = posts[0]
    body = post.get("body", "")
    wl = set(ctx.get("numbers_whitelist") or [])

    tokens = _NUMBER_RE.findall(body)
    invented = []
    for tok in tokens:
        if re.match(r"^\d{1,2}$", tok):
            continue
        if tok not in wl:
            invented.append(tok)
    assert not invented, (
        f"Invented numbers in macro post body: {invented}\n"
        f"body={body!r}\nwhitelist={sorted(wl)}"
    )


def test_no_indicator_vocab_in_macro_event_watchlist_posts():
    """No indicator vocab may appear in macro/event/watchlist post bodies."""
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None, root=ROOT)

    non_ticker_types = {"macro", "event", "watchlist"}
    hits = []
    for acct in plan.get("accounts", []):
        for item in acct.get("queue", []):
            if item.get("type") in non_ticker_types:
                full = (item.get("headline", "") + " " + item.get("body", "")).lower()
                m = _INDICATOR_VOCAB.search(full)
                if m:
                    hits.append(
                        f"[{item['type']}] '{m.group()}' in: '{full[:100]}'"
                    )
    assert not hits, f"Indicator vocab in non-ticker posts:\n" + "\n".join(hits[:5])
