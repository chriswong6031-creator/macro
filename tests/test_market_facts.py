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

import json
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
    """An event post in the full build must contain a digit or real fact text.

    Event items are DATA-CONDITIONAL: the plan only mints them when the day's
    brief/regime artifacts carry an event, so asserting non-empty here turned
    the suite red on every quiet day (it failed for days while the 07-31 empty
    plan sat on main). Skipping on the empty case is honest, not vacuous: the
    skip names the data condition, and the substantive pin (event copy carries
    a concrete fact) still fires on every day that HAS events.
    """
    plan = _build_plan_with_root()
    event_items = _collect_items_by_type(plan, "event")
    if not event_items:
        pytest.skip("today's source artifacts minted no event items — "
                    "the fact pin below runs on event-bearing days")
    # At least one event post must carry a concrete fact (digit or the tape direction text)
    has_content = any(
        re.search(r"\d|today|regime|liquidity", item.get("body", ""), re.IGNORECASE)
        for item in event_items
    )
    assert has_content, (
        f"No event post carries concrete content. Sample bodies: "
        f"{[i['body'][:100] for i in event_items[:3]]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# THE EVENT LANE'S MINT, PINNED DETERMINISTICALLY
#
# Review-of-tests finding (2026-07-31): the integration test above is the event
# lane's ONLY coverage, and it skips whenever the build produces no event items.
# That skip is honest about the data, but it makes a CODE regression — the
# driver table stops resolving, the fact id is renamed, the allocator's `event`
# weight is dropped — indistinguishable from a quiet morning. Every green run
# that skips proves nothing, and the lane can go dark for weeks in silence.
#
# The two halves of the mint are deterministic and are pinned from fixtures
# here. The THIRD half — the writer turning an event fact into an event post —
# is LLM-gated (MARKETING_LLM_ENABLED is never set in this suite, and the
# keyless writer drops the LLM-required kinds), which is the real reason the
# integration test finds an empty plan; that one stays an honest skip.
# ─────────────────────────────────────────────────────────────────────────────

#: A `why_the_tape_moved` direction with a plain-English translation in
#: market_facts._DRIVER_PLAIN. Written out rather than imported so a silent
#: rename of the label breaks THIS test instead of passing vacuously against
#: whatever key the table happens to hold.
_EVENT_DRIVER = "credit spreads widening — stress"


def _write_event_brief(root: Path, *, available: bool = True,
                       direction: str = _EVENT_DRIVER) -> None:
    """The minimal daily_brief.json shape that mints an event fact."""
    (root / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
    (root / "site" / "neuralwebdata" / "daily_brief.json").write_text(
        json.dumps({"why_the_tape_moved": {
            "available": available,
            "primary": {"direction": direction, "coherence": "supported"}}}),
        encoding="utf-8")


def test_an_event_bearing_brief_mints_an_event_fact(tmp_path):
    """Data -> fact. Fails when the mint path breaks, on any day of the week."""
    from engine.marketing.market_facts import event_facts

    _write_event_brief(tmp_path)
    out = event_facts(tmp_path)
    assert _fact_shape_ok(out), out
    ids = [f["id"] for f in out["facts"]]
    assert "event_catalyst" in ids, ids
    text = next(f["text"] for f in out["facts"] if f["id"] == "event_catalyst")
    # The SAME substantive assertion the integration test makes — a concrete
    # fact, not desk shorthand — so this pin is a true stand-in on a quiet day.
    assert re.search(r"\d|today|regime|liquidity", text, re.IGNORECASE), text
    # And never the raw internal label.
    assert _EVENT_DRIVER not in text, text


def test_an_unknown_driver_label_refuses_rather_than_shipping_shorthand(tmp_path):
    """The lane's own rule (`_plain_driver_read` returns None => SKIP): an
    untranslated label must fall back, never reach a reader as desk jargon."""
    from engine.marketing.market_facts import event_facts

    _write_event_brief(tmp_path, direction="gamma pin unwind — dealer flip")
    out = event_facts(tmp_path)
    assert "event_catalyst" not in [f["id"] for f in out["facts"]]
    assert "gamma pin unwind" not in json.dumps(out)


def test_an_event_less_brief_falls_back_instead_of_going_dark(tmp_path):
    """`available: False` is a quiet day, and a quiet day still gets macro
    context — the fallback is the behaviour, not an accident of the data."""
    from engine.marketing.market_facts import event_facts, macro_facts

    _write_event_brief(tmp_path, available=False)
    assert event_facts(tmp_path) == macro_facts(tmp_path)


def test_the_allocator_still_mints_event_slots(tmp_path):
    """Fact -> SLOT. The other half a quiet-day skip cannot see: if `event`
    ever falls out of the tilt (or is dropped unconditionally rather than only
    under publish.publish_time_read), the lane goes dark and every run of the
    integration test above skips green."""
    from engine.marketing.content_studio import plan_account

    account = {"id": "flagship", "kind": "flagship", "voice": "authoritative desk"}
    items = plan_account(account, _SAMPLE_PLANS, tilt=_SAMPLE_ACCOUNTS[0]["tilt"])
    assert [i for i in items if i.type == "event"], \
        sorted({i.type for i in items})


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


# ─────────────────────────────────────────────────────────────────────────────
# X Growth W1g — a denominator the numerator cannot move against.
#
# THE DEFECT (2026-07-25..31 audit). Four posts opened "231 of 231 names in the
# S&P universe are showing bullish momentum setups right now" and then argued
# the opposite in the next sentence ("No triggers", "zero triggers"). `now` is
# keyed by every tracked name and `universe_n` is the size of that same list, so
# the count is a definition of the screen, not an observation about the market.
#
# WHAT THE LIVE ARTIFACT CARRIES (checked 2026-07-31): universe_n = 232,
# len(now) = 232, active = 232. `universe_n` IS the real scanned universe — the
# artifact holds no larger population — so there is no denominator repair
# available and dropping is the only honest handling.
#
# THE GATE MUST BE A BAND. `0 < n < universe` is a knife-edge that 231-of-232
# walks straight through, and 231-of-232 is the same non-fact as 231-of-231.
# ─────────────────────────────────────────────────────────────────────────────

def _write_confluence(tmp_path, *, n_active, universe_n, n_names=None):
    """A tech_confluence.json with `n_active` of `n_names` names firing."""
    n_names = n_names if n_names is not None else universe_n
    now = {}
    for i in range(n_names):
        now[f"T{i:04d}"] = [0] if i < n_active else []
    (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
    (tmp_path / "site" / "factordata" / "tech_confluence.json").write_text(
        json.dumps({"universe_n": universe_n, "now": now,
                    "combos": {"long": [{"id": "c0"}]}}),
        encoding="utf-8")


def _breadth_ids(tmp_path):
    from engine.marketing.market_facts import breadth_facts
    return [f["id"] for f in breadth_facts(tmp_path)["facts"]]


class TestVacuousDenominatorsNeverShip:
    def test_a_fully_saturated_count_is_dropped(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_confluence(p, n_active=231, universe_n=231)
            assert "breadth_active" not in _breadth_ids(p)

    def test_one_name_short_of_saturation_is_still_dropped(self):
        """The knife-edge. 231 of 232 clears `0 < n < universe` and says
        exactly as little as 231 of 231."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_confluence(p, n_active=231, universe_n=232)
            assert "breadth_active" not in _breadth_ids(p), (
                "a 99.6%-saturated count still shipped as a breadth read"
            )

    def test_an_empty_count_is_dropped_too(self):
        """0 of 232 has no members to name and is indistinguishable from a
        broken screen. This is the ONE survivor of the deleted low arm."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_confluence(p, n_active=0, universe_n=232)
            assert "breadth_active" not in _breadth_ids(p)

    def test_a_washout_ships_it_is_the_rarest_print_the_lane_has(self):
        """11 of 232 is a WASHOUT, and a washout is information.

        Adversarial-review finding (2026-07-31). The gate was symmetric —
        `ratio <= 0.05` — but the diagnosed defect was SATURATION only. The low
        arm was assumed, never measured, and it deleted the rarest and most
        newsworthy print this lane can produce: 231-of-232 says nothing because
        it cannot be otherwise, while 11-of-232 says the screen almost emptied,
        which is checkable and concrete. Fails pre-fix (11/232 = 4.7% ≤ 5%).
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_confluence(p, n_active=11, universe_n=232)
            assert "breadth_active" in _breadth_ids(p), (
                "a washout was deleted as a 'degenerate' count"
            )

    def test_the_low_arm_is_gone_across_the_whole_thin_range(self):
        """Directly on the predicate, so the pin survives a breadth_facts
        refactor. Everything from one lone name up to the saturation ceiling is
        a real fraction; only 0-of-N and no-universe are vacuous."""
        from engine.marketing.market_facts import _is_vacuous_count
        for n in (1, 2, 5, 11, 23, 116, 219):
            assert not _is_vacuous_count(n, 232), f"{n} of 232 was dropped"
        assert _is_vacuous_count(0, 232)      # nothing to name
        assert _is_vacuous_count(5, 0)        # no universe
        assert _is_vacuous_count(221, 232)    # 95.3% — saturated
        assert _is_vacuous_count(232, 232)

    def test_a_real_breadth_read_still_ships(self):
        """The gate drops non-facts; it must not silence the lane."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            _write_confluence(p, n_active=112, universe_n=232)
            ids = _breadth_ids(p)
            assert "breadth_active" in ids, ids

    def test_the_tracked_list_denominator_is_gated_on_the_RATIO_not_the_shape(self):
        """The live artifact's shape — `len(now) == universe_n` — driven from a
        FIXTURE, both ways round.

        WHY THIS IS NOT THE LIVE FILE ANY MORE (review-of-tests, 2026-07-31).
        This pin used to hard-assert `len(now) == universe` against the
        committed site/factordata/tech_confluence.json, which was true at 232/232
        the day it was written and turns red the first morning one name drops a
        leg — a data-day bomb in a suite about a code rule. Worse, its
        non-saturated arm asserted nothing at all: with `active` and `len(now)`
        identical by construction on that file, only the saturated branch could
        ever execute.

        The rule under test is a RATIO rule, so the fixture supplies both
        ratios on the shape the live data actually has.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            # Saturated: every tracked name firing, denominator = the list size.
            _write_confluence(p, n_active=232, universe_n=232)
            assert "breadth_active" not in _breadth_ids(p), (
                "232 of 232 is a definition of the screen, not a breadth read")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            # SAME shape, ordinary ratio — the arm the live-file version of this
            # test could never reach. It must ship, or the gate is a mute button.
            _write_confluence(p, n_active=140, universe_n=232)
            assert "breadth_active" in _breadth_ids(p), (
                "a 60%-active read was dropped along with the vacuous ones")

    def test_the_live_artifact_agrees_with_the_producers_own_rule(self):
        """SMOKE READ of the committed artifact — no equality assert.

        Whatever shape the data has on any given morning, the fact list must
        agree with `_is_vacuous_count` about it. That is a statement about the
        CODE (one rule, honoured at the seam that reads the file) and it holds on
        a saturated day, a washout day and an ordinary day alike, so it can never
        go red merely because the tape changed.
        """
        tc_path = ROOT / "site" / "factordata" / "tech_confluence.json"
        if not tc_path.exists():
            pytest.skip("site/factordata/tech_confluence.json not present")
        raw = json.loads(tc_path.read_text(encoding="utf-8"))
        now = raw.get("now") or {}
        active = len([t for t, v in now.items() if isinstance(v, list) and v])
        universe = int(raw.get("universe_n") or 0)
        from engine.marketing.market_facts import _is_vacuous_count, breadth_facts
        ids = [f["id"] for f in breadth_facts(ROOT)["facts"]]
        assert ("breadth_active" in ids) is not _is_vacuous_count(active, universe), (
            f"{active} of {universe}: the fact list and the drop rule disagree "
            f"about the live artifact ({ids})")

    def test_the_producer_saturation_arm_matches_the_consumer_band(self):
        """BOTH nets are saturation-only now, and this pin holds them together.

        market_facts deleted its low arm first (a washout is information — see
        the two tests above); the fix-wave then brought content_studio's
        `_DEFAULT_DEGENERATE_BAND` to the same ruling (lo=0.0, and
        `is_degenerate_count` treats a non-positive lo as NO low arm, so a
        "0 of N" no-triggers read survives the second net too). If either side
        regrows a low arm, a washout that clears the producer dies silently in
        `drop_degenerate_facts` — this test is what makes that divergence loud.
        """
        from engine.marketing.market_facts import (
            _VACUOUS_COUNT_BAND, _VACUOUS_COUNT_MAX_RATIO,
        )
        from engine.marketing.content_studio import (
            _DEFAULT_DEGENERATE_BAND, is_degenerate_count,
        )
        assert _VACUOUS_COUNT_MAX_RATIO == _DEFAULT_DEGENERATE_BAND[1]
        assert _VACUOUS_COUNT_BAND[1] == _VACUOUS_COUNT_MAX_RATIO
        # Neither net has a low arm.
        assert _VACUOUS_COUNT_BAND[0] == 0.0
        assert _DEFAULT_DEGENERATE_BAND[0] == 0.0
        # The washout and the no-triggers read both clear the consumer net.
        assert not is_degenerate_count(11, 232)
        assert not is_degenerate_count(0, 232)
        # Saturation still dies there.
        assert is_degenerate_count(232, 232)
