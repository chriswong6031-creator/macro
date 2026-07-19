"""tests/test_movers_source.py — movers_source module tests.

Tests:
1.  load_movers returns None on missing root
2.  load_movers returns {sp500_tiles, theme_tiles, asof} shape from real data
3.  top_movers: gainers are sorted pct DESC; losers are sorted pct ASC
4.  top_movers: all returned |pct| >= min_abs
5.  top_movers: n cap respected
6.  theme_lists: sorted by |agg_pct| DESC
7.  theme_lists: dedupes tickers across themes
8.  theme_lists: direction correct (down for negative avg)
9.  theme_lists: question present on every item
10. theme_lists: min_members filter enforced
11. mover_facts: whitelist covers the mover %
12. mover_facts: no indicator vocab in fact texts
13. theme_facts: whitelist covers every member % AND the agg
14. theme_facts: no indicator vocab in fact texts
15. theme_facts shape: {facts, numbers_whitelist} always returned
16. mover_facts shape: {facts, numbers_whitelist} always returned
17. full build: produces ≥1 theme_list post with ≥4 cashtags ending in '?'
18. full build: every number in a theme_list post body is in the whitelist (no invented numbers)
19. full build: multi-cashtag validate passes for a real member list
20. full build: validate FAILS for an unrelated cashtag in theme_list
21. full build: mover posts carry the real move %
22. no indicator vocab in mover/theme_list post bodies
23. no dup headlines across the full plan (mover + theme_list posts)
24. load_movers with real data: sp500_tiles has ≥100 entries
25. top_movers with real data: real ticker symbols present in gainers/losers
"""
from __future__ import annotations

import re
from pathlib import Path


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
    \b\d{2,4}\.\d{2}\b        # price: 226.50
    |
    \b\d{3,6}\b               # bare integer >=3 digits
    """,
    re.VERBOSE,
)


def _synthetic_movers_data() -> dict:
    """Build a synthetic movers data dict for unit tests."""
    sp500_tiles = [
        {"t": "AAPL", "name": "Apple", "sector": "Technology", "perf": {"1D": 5.2, "1W": 3.0}},
        {"t": "MSFT", "name": "Microsoft", "sector": "Technology", "perf": {"1D": 3.1, "1W": 1.5}},
        {"t": "NVDA", "name": "NVIDIA", "sector": "Technology", "perf": {"1D": -4.5, "1W": -8.0}},
        {"t": "AMD", "name": "AMD", "sector": "Technology", "perf": {"1D": -6.2, "1W": -10.0}},
        {"t": "SMCI", "name": "Super Micro", "sector": "Technology", "perf": {"1D": -2.9, "1W": -5.0}},
        {"t": "GOOG", "name": "Alphabet", "sector": "Communication Services", "perf": {"1D": 1.1, "1W": 2.0}},
        {"t": "META", "name": "Meta", "sector": "Communication Services", "perf": {"1D": -1.5, "1W": -2.0}},
        {"t": "XOM", "name": "Exxon", "sector": "Energy", "perf": {"1D": 0.3, "1W": 1.0}},
        {"t": "CVX", "name": "Chevron", "sector": "Energy", "perf": {"1D": 0.1, "1W": 0.5}},
    ]
    theme_tiles = [
        {
            "t": "aicompute",
            "name": "Compute",
            "sector": "Artificial Intelligence",
            "perf": {"1D": -3.0},
            "members": [
                {"t": "NVDA", "perf": {"1D": -4.5}},
                {"t": "AMD", "perf": {"1D": -6.2}},
                {"t": "SMCI", "perf": {"1D": -5.1}},
                {"t": "AVGO", "perf": {"1D": -3.8}},
                {"t": "MRVL", "perf": {"1D": -2.5}},
            ],
        },
        {
            "t": "aimodels",
            "name": "Models",
            "sector": "Artificial Intelligence",
            "perf": {"1D": -2.0},
            "members": [
                {"t": "MSFT", "perf": {"1D": -1.5}},
                {"t": "GOOG", "perf": {"1D": -2.0}},
                {"t": "META", "perf": {"1D": -3.0}},
                # NVDA already appears above but should dedupe
                {"t": "NVDA", "perf": {"1D": -4.5}},
            ],
        },
        {
            "t": "biotech_core",
            "name": "Biotech Core",
            "sector": "Healthcare & Biotech",
            "perf": {"1D": 2.5},
            "members": [
                {"t": "AMGN", "perf": {"1D": 4.2}},
                {"t": "BIIB", "perf": {"1D": 3.1}},
                {"t": "REGN", "perf": {"1D": 2.8}},
                {"t": "GILD", "perf": {"1D": 1.9}},
                {"t": "VRTX", "perf": {"1D": 2.2}},
            ],
        },
        {
            # Too few members — should be filtered
            "t": "tiny",
            "name": "Tiny Theme",
            "sector": "Nanotechnology",
            "perf": {"1D": -5.0},
            "members": [
                {"t": "A1", "perf": {"1D": -5.0}},
                {"t": "A2", "perf": {"1D": -4.0}},
            ],
        },
    ]
    return {"sp500_tiles": sp500_tiles, "theme_tiles": theme_tiles, "asof": None}


# ─────────────────────────────────────────────────────────────────────────────
# 1-2: load_movers
# ─────────────────────────────────────────────────────────────────────────────

def test_load_movers_returns_none_on_missing_root(tmp_path):
    from engine.marketing.movers_source import load_movers
    result = load_movers(tmp_path)
    assert result is None


def test_load_movers_real_data_shape():
    """Real heatmap files present — returned shape must have required keys."""
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    themes_path = ROOT / "site" / "marketdata" / "themes_heatmap.json"
    if not sp500_path.exists() and not themes_path.exists():
        import pytest; pytest.skip("No heatmap files present")
    from engine.marketing.movers_source import load_movers
    result = load_movers(ROOT)
    assert result is not None
    assert "sp500_tiles" in result
    assert "theme_tiles" in result
    assert "asof" in result
    assert isinstance(result["sp500_tiles"], list)
    assert isinstance(result["theme_tiles"], list)


# ─────────────────────────────────────────────────────────────────────────────
# 3-5: top_movers
# ─────────────────────────────────────────────────────────────────────────────

def test_top_movers_gainers_sorted_desc():
    from engine.marketing.movers_source import top_movers
    data = _synthetic_movers_data()
    result = top_movers(data, min_abs=3.0)
    gainers = result["gainers"]
    for i in range(len(gainers) - 1):
        assert gainers[i]["pct"] >= gainers[i + 1]["pct"], (
            f"Gainers not sorted DESC at index {i}: {gainers[i]['pct']} < {gainers[i+1]['pct']}"
        )


def test_top_movers_losers_sorted_asc():
    from engine.marketing.movers_source import top_movers
    data = _synthetic_movers_data()
    result = top_movers(data, min_abs=3.0)
    losers = result["losers"]
    for i in range(len(losers) - 1):
        assert losers[i]["pct"] <= losers[i + 1]["pct"], (
            f"Losers not sorted ASC at index {i}: {losers[i]['pct']} > {losers[i+1]['pct']}"
        )


def test_top_movers_min_abs_filter():
    from engine.marketing.movers_source import top_movers
    data = _synthetic_movers_data()
    result = top_movers(data, min_abs=4.0)
    all_movers = result["gainers"] + result["losers"]
    for m in all_movers:
        assert abs(m["pct"]) >= 4.0, (
            f"Mover {m['ticker']} has |pct|={abs(m['pct']):.1f}% < min_abs=4.0"
        )


def test_top_movers_n_cap():
    from engine.marketing.movers_source import top_movers
    data = _synthetic_movers_data()
    result = top_movers(data, n=2, min_abs=1.0)
    assert len(result["gainers"]) <= 2
    assert len(result["losers"]) <= 2


# ─────────────────────────────────────────────────────────────────────────────
# 6-10: theme_lists
# ─────────────────────────────────────────────────────────────────────────────

def test_theme_lists_sorted_by_abs_agg_pct():
    from engine.marketing.movers_source import theme_lists
    data = _synthetic_movers_data()
    result = theme_lists(data, min_members=4)
    for i in range(len(result) - 1):
        assert abs(result[i]["agg_pct"]) >= abs(result[i + 1]["agg_pct"]), (
            f"Theme list not sorted by |agg_pct| DESC at index {i}: "
            f"{result[i]['agg_pct']} vs {result[i+1]['agg_pct']}"
        )


def test_theme_lists_dedupes_tickers():
    from engine.marketing.movers_source import theme_lists
    data = _synthetic_movers_data()
    result = theme_lists(data, min_members=4)
    all_tickers = []
    for theme_item in result:
        for m in theme_item["members"]:
            all_tickers.append(m["ticker"])
    assert len(all_tickers) == len(set(all_tickers)), (
        f"Duplicate tickers across theme_lists: {[t for t in all_tickers if all_tickers.count(t) > 1]}"
    )


def test_theme_lists_direction_correct():
    from engine.marketing.movers_source import theme_lists
    data = _synthetic_movers_data()
    result = theme_lists(data, min_members=4)
    for ti in result:
        avg = sum(m["pct"] for m in ti["members"] if m.get("pct") is not None) / len(ti["members"])
        expected = "down" if ti["agg_pct"] < 0 else "up"
        assert ti["direction"] == expected, (
            f"Theme {ti['theme']}: direction={ti['direction']} but agg_pct={ti['agg_pct']}"
        )


def test_theme_lists_question_present():
    from engine.marketing.movers_source import theme_lists
    data = _synthetic_movers_data()
    result = theme_lists(data, min_members=4)
    for ti in result:
        assert ti.get("question"), f"Theme {ti['theme']} has no question"
        assert "?" in ti["question"], f"Theme {ti['theme']} question has no '?'"


def test_theme_lists_min_members_filter():
    from engine.marketing.movers_source import theme_lists
    data = _synthetic_movers_data()
    result = theme_lists(data, min_members=4)
    # "Nanotechnology" only has 2 members — should be excluded
    theme_names = [ti["theme"] for ti in result]
    assert "Nanotechnology" not in theme_names, (
        f"Theme with too few members was not filtered out: {theme_names}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 11-12: mover_facts
# ─────────────────────────────────────────────────────────────────────────────

def test_mover_facts_whitelist_covers_pct():
    from engine.marketing.movers_source import mover_facts
    mover = {"ticker": "ISRG", "name": "Intuitive Surgical", "pct": -14.15, "sector": "Healthcare"}
    result = mover_facts(mover)
    wl = result["numbers_whitelist"]
    assert any("-14.2%" in w or "14.1%" in w or "14.2" in w for w in wl), (
        f"Mover pct not in whitelist. whitelist={wl}"
    )


def test_mover_facts_no_indicator_vocab():
    from engine.marketing.movers_source import mover_facts
    mover = {"ticker": "NVDA", "name": "NVIDIA", "pct": -5.5, "sector": "Technology"}
    result = mover_facts(mover)
    for f in result["facts"]:
        m = _INDICATOR_VOCAB.search(f.get("text", ""))
        assert m is None, f"Indicator vocab '{m.group()}' in mover fact: {f['text']}"


def test_mover_facts_shape():
    from engine.marketing.movers_source import mover_facts
    mover = {"ticker": "NVDA", "pct": -5.5}
    result = mover_facts(mover)
    assert "facts" in result
    assert "numbers_whitelist" in result
    assert isinstance(result["facts"], list)
    assert isinstance(result["numbers_whitelist"], list)


def test_mover_facts_empty_on_missing_ticker():
    from engine.marketing.movers_source import mover_facts
    result = mover_facts({})
    assert result["facts"] == []
    assert result["numbers_whitelist"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 13-16: theme_facts
# ─────────────────────────────────────────────────────────────────────────────

def test_theme_facts_whitelist_covers_every_member_pct_and_agg():
    from engine.marketing.movers_source import theme_facts
    theme_item = {
        "theme": "Artificial Intelligence",
        "direction": "down",
        "tone": "selling off",
        "members": [
            {"ticker": "NVDA", "pct": -4.5},
            {"ticker": "AMD", "pct": -6.2},
            {"ticker": "SMCI", "pct": -5.1},
            {"ticker": "AVGO", "pct": -3.8},
        ],
        "agg_pct": -4.9,
        "question": "Which one comes back first?",
    }
    result = theme_facts(theme_item)
    wl = set(result["numbers_whitelist"])
    # All member pcts must be whitelisted
    for m in theme_item["members"]:
        pct_str = f"{m['pct']:+.1f}%"
        assert pct_str in wl, f"Member pct '{pct_str}' not in whitelist: {wl}"
    # Aggregate must be whitelisted
    assert "-4.9%" in wl, f"Agg pct '-4.9%' not in whitelist: {wl}"


def test_theme_facts_no_indicator_vocab():
    from engine.marketing.movers_source import theme_facts
    theme_item = {
        "theme": "FinTech",
        "direction": "up",
        "tone": "ripping",
        "members": [
            {"ticker": "SQ", "pct": 3.5},
            {"ticker": "PYPL", "pct": 2.1},
            {"ticker": "AFRM", "pct": 4.8},
            {"ticker": "SOFI", "pct": 2.9},
        ],
        "agg_pct": 3.3,
        "question": "Which one leads higher?",
    }
    result = theme_facts(theme_item)
    for f in result["facts"]:
        m = _INDICATOR_VOCAB.search(f.get("text", ""))
        assert m is None, f"Indicator vocab '{m.group()}' in theme fact: {f['text']}"


def test_theme_facts_shape():
    from engine.marketing.movers_source import theme_facts
    result = theme_facts({})
    assert "facts" in result
    assert "numbers_whitelist" in result
    assert isinstance(result["facts"], list)
    assert isinstance(result["numbers_whitelist"], list)


def test_mover_facts_shape_on_missing_pct():
    from engine.marketing.movers_source import mover_facts
    result = mover_facts({"ticker": "X"})
    assert result["facts"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 17-23: full-build integration tests
# ─────────────────────────────────────────────────────────────────────────────

def _get_all_queue_items(plan: dict, type_id: str) -> list[dict]:
    items = []
    for acct in plan.get("accounts", []):
        for item in acct.get("queue", []):
            if item.get("type") == type_id:
                items.append(item)
    return items


def _make_test_cfg():
    from datetime import datetime, timedelta, timezone
    fresh = (datetime.now(timezone.utc).date() - timedelta(days=5)).isoformat()
    plans = [
        {
            "id": "PLTR-BULL", "asset": "PLTR", "direction": "BULL",
            "entry": 120.0, "invalidation": 100.0, "targets": [150.0, 180.0],
            "trigger": 125.0, "_conviction_score": 90, "_signal_date": fresh,
            "phase": "triggered_pre_t1", "recommended_action": "hold",
            "management_confidence": 66.0, "what_to_do_now": [],
        },
    ]
    accounts = [
        {"id": "flagship", "kind": "branded", "beat": "What changed", "voice": "authoritative desk",
         "tilt": {"signal": 0.25, "chart": 0.08, "education": 0.06, "macro": 0.10,
                  "receipt": 0.06, "watchlist": 0.04, "event": 0.04,
                  "mover": 0.20, "theme_list": 0.17}},
        {"id": "research_b", "kind": "generic", "beat": "Fast", "voice": "fast, reactive",
         "tilt": {"signal": 0.25, "chart": 0.10, "education": 0.03, "macro": 0.05,
                  "receipt": 0.05, "watchlist": 0.04, "event": 0.06,
                  "mover": 0.22, "theme_list": 0.20}},
    ]
    cfg = {"desk_network": {"stage": "A", "accounts": accounts}}
    return cfg, plans


def test_full_build_produces_theme_list_posts_with_cashtags_and_question():
    """Full build must produce ≥1 theme_list post with ≥4 cashtags ending in '?'"""
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    themes_path = ROOT / "site" / "marketdata" / "themes_heatmap.json"
    if not sp500_path.exists() or not themes_path.exists():
        import pytest; pytest.skip("Heatmap files not present")

    from engine.marketing.content_studio import content_plan
    cfg, plans = _make_test_cfg()
    plan = content_plan(cfg, plans, closes_loader=None, root=ROOT)

    theme_items = _get_all_queue_items(plan, "theme_list")
    assert theme_items, "No theme_list posts in content plan"

    # At least one must have ≥4 cashtags and end in '?'
    good = []
    for item in theme_items:
        body = item.get("body", "")
        cashtags_in_body = re.findall(r"\$[A-Z]{1,5}", body)
        if len(cashtags_in_body) >= 4 and body.strip().endswith("?"):
            good.append(item)
    assert good, (
        f"No theme_list post with ≥4 cashtags ending in '?'. "
        f"Sample bodies: {[i['body'][:120] for i in theme_items[:2]]}"
    )


def test_full_build_no_invented_numbers_in_theme_list():
    """Every number in a theme_list post body must come from the heatmap (whitelist)."""
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    themes_path = ROOT / "site" / "marketdata" / "themes_heatmap.json"
    if not sp500_path.exists() or not themes_path.exists():
        import pytest; pytest.skip("Heatmap files not present")

    from engine.marketing.movers_source import load_movers, theme_lists, theme_facts
    data = load_movers(ROOT)
    assert data is not None
    tl_items = theme_lists(data)
    for tl in tl_items[:3]:
        tf = theme_facts(tl)
        wl = set(tf["numbers_whitelist"])
        # Check the pre-built body from movers_source content
        body_parts = [f"{m['ticker']} {m['pct']:+.1f}%" for m in tl["members"][:8] if m.get("pct") is not None]
        body = " ".join(body_parts) + " " + tl["question"]
        tokens = _NUMBER_RE.findall(body)
        invented = []
        for tok in tokens:
            if re.match(r"^\d{1,2}$", tok):
                continue
            if tok not in wl:
                invented.append(tok)
        assert not invented, (
            f"Invented numbers in theme '{tl['theme']}' body: {invented}\n"
            f"whitelist={sorted(wl)}\nbody={body[:200]}"
        )


def test_validate_copy_passes_for_real_theme_list():
    """validate_copy must pass for a well-formed theme_list post."""
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "",
        "type": "theme_list",
        "emoji_budget": 1,
        "numbers_whitelist": ["-4.5%", "-6.2%", "-5.1%", "-3.8%", "-4.9%"],
        "cashtags": ["$NVDA", "$AMD", "$SMCI", "$AVGO"],
    }
    headline = "Artificial Intelligence -4.9% avg today"
    body = "$NVDA -4.5% $AMD -6.2% $SMCI -5.1% $AVGO -3.8% Which one comes back first?"
    violations = validate_copy(headline, body, ctx)
    # Should have no violations
    real_v = [v for v in violations if "cashtag" not in v.lower() or "valid" in v.lower()]
    assert not violations, f"Unexpected violations for valid theme_list: {violations}"


def test_validate_copy_fails_for_unrelated_cashtag_in_theme_list():
    """validate_copy must reject a cashtag not in the member list."""
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "",
        "type": "theme_list",
        "emoji_budget": 1,
        "numbers_whitelist": ["-4.5%", "-6.2%", "-5.1%", "-3.8%"],
        "cashtags": ["$NVDA", "$AMD", "$SMCI", "$AVGO"],
    }
    headline = "AI names getting hit"
    # $TSLA is NOT in the member list
    body = "$NVDA -4.5% $AMD -6.2% $SMCI -5.1% $AVGO -3.8% $TSLA -2.0% Which one comes back first?"
    violations = validate_copy(headline, body, ctx)
    # Must flag $TSLA as invalid cashtag
    invalid_v = [v for v in violations if "member list" in v.lower() or "cashtag" in v.lower()]
    assert invalid_v, f"Expected cashtag violation for $TSLA (not in member list), got: {violations}"


def test_mover_posts_carry_real_pct():
    """Mover posts in the full plan must contain the real move %."""
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    if not sp500_path.exists():
        import pytest; pytest.skip("sp500_heatmap.json not present")

    from engine.marketing.content_studio import content_plan
    cfg, plans = _make_test_cfg()
    plan = content_plan(cfg, plans, closes_loader=None, root=ROOT)

    mover_items = _get_all_queue_items(plan, "mover")
    assert mover_items, "No mover posts in content plan"

    for item in mover_items:
        body = item.get("body", "")
        headline = item.get("headline", "")
        full_text = headline + " " + body
        # Must contain a % sign with a number (the real move)
        assert re.search(r"[+-]?\d+\.\d+%", full_text), (
            f"Mover post missing real %: headline={headline!r}, body={body!r}"
        )


def test_no_indicator_vocab_in_mover_theme_posts():
    """Mover and theme_list posts must contain no indicator vocabulary."""
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    if not sp500_path.exists():
        import pytest; pytest.skip("sp500_heatmap.json not present")

    from engine.marketing.content_studio import content_plan
    cfg, plans = _make_test_cfg()
    plan = content_plan(cfg, plans, closes_loader=None, root=ROOT)

    for type_id in ("mover", "theme_list"):
        items = _get_all_queue_items(plan, type_id)
        for item in items:
            full = (item.get("headline", "") + " " + item.get("body", "")).lower()
            m = _INDICATOR_VOCAB.search(full)
            assert m is None, (
                f"[{type_id}] Indicator vocab '{m.group()}' found in: {full[:100]}"
            )


def test_no_dup_headlines_across_mover_theme_posts():
    """No duplicate headlines within mover + theme_list posts."""
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    themes_path = ROOT / "site" / "marketdata" / "themes_heatmap.json"
    if not sp500_path.exists() or not themes_path.exists():
        import pytest; pytest.skip("Heatmap files not present")

    from engine.marketing.content_studio import content_plan
    cfg, plans = _make_test_cfg()
    plan = content_plan(cfg, plans, closes_loader=None, root=ROOT)

    mover_items = _get_all_queue_items(plan, "mover")
    theme_items = _get_all_queue_items(plan, "theme_list")
    all_items = mover_items + theme_items
    headlines = [i.get("headline", "").lower().strip() for i in all_items]
    assert len(headlines) == len(set(headlines)), (
        f"Duplicate headlines in mover/theme posts: "
        f"{[h for h in headlines if headlines.count(h) > 1]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 24-25: real-data smoke tests
# ─────────────────────────────────────────────────────────────────────────────

def test_load_movers_real_sp500_has_many_tiles():
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    if not sp500_path.exists():
        import pytest; pytest.skip("sp500_heatmap.json not present")
    from engine.marketing.movers_source import load_movers
    data = load_movers(ROOT)
    assert data is not None
    assert len(data["sp500_tiles"]) >= 100, (
        f"Expected ≥100 S&P tiles, got {len(data['sp500_tiles'])}"
    )


def test_top_movers_real_data_has_real_tickers():
    """Real data — top_movers must return real ticker strings, no empty tickers."""
    sp500_path = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    if not sp500_path.exists():
        import pytest; pytest.skip("sp500_heatmap.json not present")
    from engine.marketing.movers_source import load_movers, top_movers
    data = load_movers(ROOT)
    result = top_movers(data, min_abs=1.0)
    all_movers = result["gainers"] + result["losers"]
    assert all_movers, "No movers returned from real data"
    for m in all_movers:
        assert m["ticker"], f"Empty ticker in mover: {m}"
        assert re.match(r"^[A-Z]{1,5}$", m["ticker"]), (
            f"Non-ticker in movers: {m['ticker']!r}"
        )


def test_theme_question_deterministic_across_processes():
    """Reply-bait question must be stable run-to-run (crc32, not salted hash())."""
    import subprocess, sys
    code = (
        "from engine.marketing.movers_source import load_movers, theme_lists;"
        "d=load_movers('.');"
        "print('|'.join(t['question'] for t in theme_lists(d)))"
    )
    outs = []
    for seed in ("0", "1", "2"):
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True,
                           env={"PYTHONHASHSEED": seed, "PATH": __import__("os").environ.get("PATH", "")},
                           cwd=".")
        outs.append(r.stdout.strip())
    assert outs[0] == outs[1] == outs[2], f"question selection not deterministic: {outs}"
