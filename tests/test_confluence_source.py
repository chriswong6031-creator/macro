"""tests/test_confluence_source.py — Confluence source module tests.

Test list:
1.  load_confluence fail-soft on missing file
2.  load_confluence returns dict on real tech_confluence.json (if present)
3.  fired_combo_signals filters to active_now-only combos
4.  fired_combo_signals filters on min_edge
5.  fired_combo_signals filters on max_age_days (freshness gate)
6.  fired_combo_signals dedupes one combo per ticker (best score wins)
7.  fired_combo_signals ordering is deterministic (stable)
8.  win_rate_hook contains cashtag + win-rate % + disclosure
9.  win_rate_hook public copy contains NO raw indicator vocabulary
10. Full content_plan still builds with confluence posts present
11. Eligibility gate still excludes dead Prophet signals (regression)
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

# Forbidden indicator words — must not appear in public body copy
_FORBIDDEN = re.compile(
    r"\b(macd|rsi|stochastic|ema|sma|bollinger|atr|adx|dmi|obv|cmf|vwap|"
    r"ichimoku|keltner|donchian|connors|ttm|squeeze|choppiness|bbwp)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Minimal fake confluence dict for unit tests (no real file needed)
# ---------------------------------------------------------------------------

def _make_fake_conf() -> dict:
    """Minimal fake tech_confluence.json structure for unit testing."""
    legs = [
        {"leg_id": "golden_cross_7_35@D", "signal_id": "golden_cross_7_35",
         "tf": "D", "kind": "event", "family": "ma_crosses", "direction": 1,
         "display_en": "Golden Cross (7/35)", "display_zh": "黄金交叉"},
        {"leg_id": "trend_rising_long@W", "signal_id": "trend_rising_long",
         "tf": "W", "kind": "state", "family": "trend", "direction": 1,
         "display_en": "Long-term Rising Trend", "display_zh": "长期上升趋势"},
        {"leg_id": "momentum_up@D", "signal_id": "momentum_up",
         "tf": "D", "kind": "state", "family": "momentum", "direction": 1,
         "display_en": "Momentum Turning Up", "display_zh": "动量向上"},
    ]
    combos_long = [
        {
            "id": "L0001",
            "legs": [0, 1, 2],
            "dir": 1,
            "name_en": "Golden Cross + Rising Trend + Momentum",
            "h10": {"n": 80, "wr": 0.62, "wr_mc_test": 0.80, "n_test": 15, "months_test": 12},
            "h21": {"n": 80, "wr": 0.65, "wr_mc_test": 0.85, "n_test": 15, "months_test": 12},
            "h42": {"n": 79, "wr": 0.70, "wr_mc_test": 0.82, "n_test": 14, "months_test": 11},
            "h63": {"n": 79, "wr": 0.68, "wr_mc_test": 0.78, "n_test": 14, "months_test": 11},
            "edge_wr_test": 0.30,
            "rank_score": 0.18,
            "n_fires": 80,
            "n_tickers": 60,
            "fires_last3y": 8,
            "last_fire": "2026-07-15",
            "active_now": ["AAPL"],
            "recent_fires": [],
        },
        {
            "id": "L0002",
            "legs": [0, 1],
            "dir": 1,
            "name_en": "Golden Cross + Rising Trend",
            "h10": {"n": 120, "wr": 0.60, "wr_mc_test": 0.75, "n_test": 20, "months_test": 15},
            "h21": {"n": 120, "wr": 0.63, "wr_mc_test": 0.80, "n_test": 20, "months_test": 15},
            "h42": {"n": 119, "wr": 0.67, "wr_mc_test": 0.77, "n_test": 19, "months_test": 14},
            "h63": {"n": 119, "wr": 0.65, "wr_mc_test": 0.73, "n_test": 19, "months_test": 14},
            "edge_wr_test": 0.20,
            "rank_score": 0.14,
            "n_fires": 120,
            "n_tickers": 90,
            "fires_last3y": 12,
            "last_fire": "2026-07-16",
            "active_now": ["MSFT"],
            "recent_fires": [],
        },
        {
            # LOW edge — should be filtered out
            "id": "L0003",
            "legs": [0],
            "dir": 1,
            "name_en": "Weak combo",
            "h10": {"n": 50, "wr": 0.52, "wr_mc_test": 0.55, "n_test": 10, "months_test": 8},
            "h21": {"n": 50, "wr": 0.53, "wr_mc_test": 0.58, "n_test": 10, "months_test": 8},
            "h42": {"n": 49, "wr": 0.54, "wr_mc_test": 0.56, "n_test": 9, "months_test": 7},
            "h63": {"n": 49, "wr": 0.52, "wr_mc_test": 0.54, "n_test": 9, "months_test": 7},
            "edge_wr_test": 0.02,  # below min_edge=0.05
            "rank_score": 0.05,
            "n_fires": 50,
            "n_tickers": 40,
            "fires_last3y": 5,
            "last_fire": "2026-07-16",
            "active_now": ["WEAK"],
            "recent_fires": [],
        },
        {
            # STALE last_fire — should be filtered out by max_age_days
            "id": "L0004",
            "legs": [0, 1],
            "dir": 1,
            "name_en": "Stale combo",
            "h10": {"n": 90, "wr": 0.64, "wr_mc_test": 0.82, "n_test": 18, "months_test": 14},
            "h21": {"n": 90, "wr": 0.67, "wr_mc_test": 0.88, "n_test": 18, "months_test": 14},
            "h42": {"n": 89, "wr": 0.71, "wr_mc_test": 0.85, "n_test": 17, "months_test": 13},
            "h63": {"n": 89, "wr": 0.69, "wr_mc_test": 0.81, "n_test": 17, "months_test": 13},
            "edge_wr_test": 0.25,
            "rank_score": 0.16,
            "n_fires": 90,
            "n_tickers": 70,
            "fires_last3y": 9,
            "last_fire": "2026-06-01",  # stale (>10d before 2026-07-18)
            "active_now": ["STALE"],
            "recent_fires": [],
        },
        {
            # No active_now — must be excluded
            "id": "L0005",
            "legs": [0, 1],
            "dir": 1,
            "name_en": "Not firing",
            "h10": {"n": 100, "wr": 0.66, "wr_mc_test": 0.90, "n_test": 20, "months_test": 15},
            "h21": {"n": 100, "wr": 0.69, "wr_mc_test": 0.92, "n_test": 20, "months_test": 15},
            "h42": {"n": 99, "wr": 0.73, "wr_mc_test": 0.89, "n_test": 19, "months_test": 14},
            "h63": {"n": 99, "wr": 0.71, "wr_mc_test": 0.85, "n_test": 19, "months_test": 14},
            "edge_wr_test": 0.35,
            "rank_score": 0.20,
            "n_fires": 100,
            "n_tickers": 80,
            "fires_last3y": 10,
            "last_fire": "2026-07-17",
            "active_now": [],   # NOT firing
            "recent_fires": [],
        },
        {
            # Two tickers — should dedupe to the best-scoring one per ticker
            "id": "L0006",
            "legs": [0, 1, 2],
            "dir": 1,
            "name_en": "Multi-ticker combo",
            "h10": {"n": 85, "wr": 0.63, "wr_mc_test": 0.82, "n_test": 16, "months_test": 12},
            "h21": {"n": 85, "wr": 0.66, "wr_mc_test": 0.86, "n_test": 16, "months_test": 12},
            "h42": {"n": 84, "wr": 0.70, "wr_mc_test": 0.83, "n_test": 15, "months_test": 11},
            "h63": {"n": 84, "wr": 0.68, "wr_mc_test": 0.79, "n_test": 15, "months_test": 11},
            "edge_wr_test": 0.22,
            "rank_score": 0.15,
            "n_fires": 85,
            "n_tickers": 65,
            "fires_last3y": 9,
            "last_fire": "2026-07-17",
            "active_now": ["AAPL", "NVDA"],  # AAPL already in L0001 (higher score)
            "recent_fires": [],
        },
    ]
    return {
        "generated_utc": "2026-07-18T04:01:46Z",
        "legs": legs,
        "combos": {"long": combos_long, "short": []},
    }


# ---------------------------------------------------------------------------
# 1. load_confluence fail-soft on missing file
# ---------------------------------------------------------------------------

def test_load_confluence_returns_none_for_missing_file():
    from engine.marketing.confluence_source import load_confluence
    with tempfile.TemporaryDirectory() as tmp:
        result = load_confluence(tmp)
    assert result is None


def test_load_confluence_returns_none_for_empty_file():
    from engine.marketing.confluence_source import load_confluence
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "site" / "factordata"
        p.mkdir(parents=True)
        (p / "tech_confluence.json").write_text("")
        result = load_confluence(tmp)
    assert result is None


def test_load_confluence_returns_none_for_bad_json():
    from engine.marketing.confluence_source import load_confluence
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "site" / "factordata"
        p.mkdir(parents=True)
        (p / "tech_confluence.json").write_text("NOT JSON {{}")
        result = load_confluence(tmp)
    assert result is None


# ---------------------------------------------------------------------------
# 2. load_confluence returns dict on real file (if present)
# ---------------------------------------------------------------------------

def test_load_confluence_reads_real_file_if_present():
    from engine.marketing.confluence_source import load_confluence
    real_path = ROOT / "site" / "factordata" / "tech_confluence.json"
    if not real_path.exists():
        pytest.skip("tech_confluence.json not present")
    result = load_confluence(ROOT)
    assert isinstance(result, dict)
    assert "combos" in result
    assert "legs" in result


# ---------------------------------------------------------------------------
# 3. fired_combo_signals filters to active_now only
# ---------------------------------------------------------------------------

def test_fired_combos_only_active_now():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, today="2026-07-18")
    tickers = [s["ticker"] for s in fired]
    # L0005 has active_now=[] so should be absent
    assert "STALE" not in tickers  # stale date
    # L0005 ticker would be something not in active_now — just verify all returned have active_now
    # Verify all returned tickers are indeed in some combo's active_now
    all_active = set()
    for c in conf["combos"]["long"]:
        all_active.update(c.get("active_now") or [])
    for ticker in tickers:
        assert ticker in all_active, f"{ticker} is not in any combo's active_now"


# ---------------------------------------------------------------------------
# 4. fired_combo_signals filters on min_edge
# ---------------------------------------------------------------------------

def test_fired_combos_filters_low_edge():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, min_edge=0.05, today="2026-07-18")
    tickers = [s["ticker"] for s in fired]
    # L0003 has edge_wr_test=0.02 < min_edge=0.05
    assert "WEAK" not in tickers


def test_fired_combos_low_min_edge_includes_weak():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, min_edge=0.01, today="2026-07-18")
    tickers = [s["ticker"] for s in fired]
    # L0003 now passes the filter (edge=0.02 > 0.01)
    assert "WEAK" in tickers


# ---------------------------------------------------------------------------
# 5. fired_combo_signals filters on max_age_days (freshness gate)
# ---------------------------------------------------------------------------

def test_fired_combos_filters_stale_last_fire():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, max_age_days=10, today="2026-07-18")
    tickers = [s["ticker"] for s in fired]
    # L0004 has last_fire=2026-06-01, which is 47 days before 2026-07-18
    assert "STALE" not in tickers


def test_fired_combos_large_age_window_includes_stale():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, max_age_days=60, today="2026-07-18")
    tickers = [s["ticker"] for s in fired]
    # With 60-day window, STALE (47d old) should appear
    assert "STALE" in tickers


# ---------------------------------------------------------------------------
# 6. fired_combo_signals dedupes one combo per ticker (best score wins)
# ---------------------------------------------------------------------------

def test_fired_combos_dedupes_per_ticker():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, top_n=20, today="2026-07-18")
    tickers = [s["ticker"] for s in fired]
    # Each ticker must appear at most once
    assert len(tickers) == len(set(tickers)), f"Duplicate tickers in result: {tickers}"


def test_fired_combos_aapl_uses_higher_scored_combo():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, top_n=20, today="2026-07-18")
    # AAPL appears in L0001 (edge=0.30) and L0006 (edge=0.22)
    # L0001 has higher score → AAPL should map to L0001
    aapl_entries = [s for s in fired if s["ticker"] == "AAPL"]
    assert len(aapl_entries) == 1
    assert aapl_entries[0]["combo_id"] == "L0001"


# ---------------------------------------------------------------------------
# 7. fired_combo_signals ordering is deterministic (stable)
# ---------------------------------------------------------------------------

def test_fired_combos_deterministic():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired1 = fired_combo_signals(conf, today="2026-07-18")
    fired2 = fired_combo_signals(conf, today="2026-07-18")
    assert [s["ticker"] for s in fired1] == [s["ticker"] for s in fired2]
    assert [s["combo_id"] for s in fired1] == [s["combo_id"] for s in fired2]


def test_fired_combos_sorted_by_score_descending():
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, top_n=20, today="2026-07-18")
    scores = [s["_score"] for s in fired]
    assert scores == sorted(scores, reverse=True), (
        f"Results not sorted by score DESC: {list(zip([s['ticker'] for s in fired], scores))}"
    )


# ---------------------------------------------------------------------------
# 8. win_rate_hook contains cashtag + win-rate % + disclosure
# ---------------------------------------------------------------------------

def test_win_rate_hook_contains_cashtag():
    from engine.marketing.confluence_source import win_rate_hook
    sig = {
        "ticker": "AAPL", "combo_id": "L0001", "combo_name": "Test combo",
        "win_rate": 85.0, "edge": 30.0, "n_fires": 80, "fires_last3y": 8,
        "last_fire": "2026-07-15", "legs_plain": [], "side": "long",
        "n_test": 15, "months_test": 12, "_score": 0.5,
    }
    headline, body = win_rate_hook(sig)
    assert "$AAPL" in headline or "$AAPL" in body, "Cashtag $AAPL missing from hook copy"


def test_win_rate_hook_contains_win_rate_percent():
    from engine.marketing.confluence_source import win_rate_hook
    sig = {
        "ticker": "MSFT", "combo_id": "L0002", "combo_name": "Test",
        "win_rate": 80.0, "edge": 20.0, "n_fires": 120, "fires_last3y": 12,
        "last_fire": "2026-07-16", "legs_plain": [], "side": "long",
        "n_test": 20, "months_test": 15, "_score": 0.4,
    }
    headline, body = win_rate_hook(sig)
    full_copy = headline + " " + body
    assert "80%" in full_copy, f"Win rate % not found in copy: {full_copy[:200]}"


def test_win_rate_hook_contains_disclosure():
    from engine.marketing.confluence_source import win_rate_hook
    sig = {
        "ticker": "NVDA", "combo_id": "L0006", "combo_name": "Test",
        "win_rate": 86.0, "edge": 22.0, "n_fires": 85, "fires_last3y": 9,
        "last_fire": "2026-07-17", "legs_plain": [], "side": "long",
        "n_test": 16, "months_test": 12, "_score": 0.45,
    }
    headline, body = win_rate_hook(sig)
    full_copy = (headline + " " + body).lower()
    # Must contain some form of honest disclosure
    has_disclosure = (
        "historical" in full_copy
        or "not a guarantee" in full_copy
        or "past" in full_copy
    )
    assert has_disclosure, f"No disclosure found in hook copy: {headline!r} | {body!r}"


# ---------------------------------------------------------------------------
# 9. win_rate_hook public copy contains NO raw indicator vocabulary
# ---------------------------------------------------------------------------

def test_win_rate_hook_no_indicator_vocabulary():
    from engine.marketing.confluence_source import win_rate_hook
    sig = {
        "ticker": "VST", "combo_id": "L0022", "combo_name": "RSI Stack + Golden Cross",
        "win_rate": 86.5, "edge": 29.6, "n_fires": 107, "fires_last3y": 7,
        "last_fire": "2026-07-15", "legs_plain": [
            "Golden Cross (7/35)", "Long-term Rising Trend",
            "RSI Stack (7/14/21)", "Golden Star (21/100)",
        ],
        "side": "long", "n_test": 25, "months_test": 17, "_score": 0.5,
    }
    headline, body = win_rate_hook(sig)
    # The PUBLIC copy (headline + body) must not contain raw indicator names.
    # Note: the legs_plain list (for internal use) is NOT part of the public copy.
    public_copy = headline + " " + body
    match = _FORBIDDEN.search(public_copy)
    assert match is None, (
        f"Forbidden indicator word '{match.group()}' found in public copy: "
        f"headline={headline!r} body={body!r}"
    )


def test_win_rate_hook_no_macd_rsi_ema():
    from engine.marketing.confluence_source import win_rate_hook
    sig = {
        "ticker": "BKR", "combo_id": "L0084", "combo_name": "MACD + EMA + RSI",
        "win_rate": 75.3, "edge": 18.4, "n_fires": 90, "fires_last3y": 5,
        "last_fire": "2026-07-16", "legs_plain": ["MACD Cross", "EMA ribbon"],
        "side": "long", "n_test": 18, "months_test": 14, "_score": 0.37,
    }
    headline, body = win_rate_hook(sig)
    public_copy = headline + " " + body
    for word in ("MACD", "RSI", "EMA", "SMA", "Stochastic"):
        assert word.lower() not in public_copy.lower(), (
            f"'{word}' found in public copy: {public_copy[:300]}"
        )


# ---------------------------------------------------------------------------
# 10. Full content_plan builds with confluence posts present
# ---------------------------------------------------------------------------

def _sample_accounts() -> list[dict]:
    return [
        {"id": "flagship", "kind": "branded", "beat": "What changed", "voice": "authoritative desk",
         "tilt": {"signal": 0.38, "chart": 0.12, "education": 0.10, "macro": 0.18,
                  "receipt": 0.10, "watchlist": 0.06, "event": 0.06}},
    ]


def _sample_plans() -> list[dict]:
    from datetime import datetime, timedelta, timezone as _tz
    fresh = (datetime.now(_tz.utc).date() - timedelta(days=5)).isoformat()
    return [
        {
            "id": "PLTR-BULL", "asset": "PLTR", "direction": "BULL",
            "entry": 120.0, "invalidation": 100.0, "targets": [150.0],
            "_conviction_score": 90, "_signal_date": fresh,
            "phase": "triggered_pre_t1", "recommended_action": "hold",
            "management_confidence": 66.0, "what_to_do_now": [],
        },
    ]


def test_content_plan_builds_with_confluence_posts(tmp_path):
    """content_plan must succeed and include confluence posts when conf file present."""
    # Write a fake confluence file
    conf_dir = tmp_path / "site" / "factordata"
    conf_dir.mkdir(parents=True)
    fake_conf = _make_fake_conf()
    (conf_dir / "tech_confluence.json").write_text(json.dumps(fake_conf))

    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _sample_accounts()}}
    plan = content_plan(cfg, _sample_plans(), closes_loader=None, root=tmp_path)

    # Frozen keys must be present
    frozen = {
        "schema_version", "produced_by", "produced_at", "tier", "schema",
        "as_of", "source", "content_types", "accounts", "featured_charts",
        "distinctness", "summary",
    }
    assert frozen.issubset(set(plan.keys())), f"Missing keys: {frozen - set(plan.keys())}"

    # content.confluence block must be present
    assert "content" in plan, "content block missing from plan"
    assert "confluence" in plan["content"], "content.confluence missing"
    conf_block = plan["content"]["confluence"]
    assert isinstance(conf_block["fired_combos"], int)
    assert isinstance(conf_block["charts"], int)

    # Confluence signal posts must appear in the queue
    all_queue = [p for a in plan["accounts"] for p in a["queue"]]
    conf_posts = [p for p in all_queue if p.get("source") == "confluence"]
    # With the fake conf, there are active combos → expect > 0 confluence posts
    assert len(conf_posts) > 0, (
        f"Expected confluence posts but got 0. "
        f"conf_block={conf_block}"
    )

    # Verify additive fields on confluence posts
    for p in conf_posts:
        assert p.get("source") == "confluence"
        assert p.get("combo_id"), "combo_id missing on confluence post"
        assert p.get("ticker"), "ticker missing on confluence post"
        assert p.get("type") == "signal"


def test_content_plan_no_confluence_posts_when_conf_absent(tmp_path):
    """If tech_confluence.json absent, plan builds normally with no confluence posts."""
    # Do NOT write the confluence file
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _sample_accounts()}}
    plan = content_plan(cfg, _sample_plans(), closes_loader=None, root=tmp_path)

    all_queue = [p for a in plan["accounts"] for p in a["queue"]]
    conf_posts = [p for p in all_queue if p.get("source") == "confluence"]
    assert len(conf_posts) == 0, "Confluence posts should be absent when no conf file"

    # The plan still has accounts and content
    assert len(plan["accounts"]) > 0
    # conf block says 0 posts
    conf_block = plan.get("content", {}).get("confluence", {})
    assert conf_block.get("fired_combos", 0) == 0


def test_content_plan_total_charts_cap(tmp_path):
    """Total featured_charts must never exceed 8 (6 Prophet + 2 confluence)."""
    conf_dir = tmp_path / "site" / "factordata"
    conf_dir.mkdir(parents=True)
    fake_conf = _make_fake_conf()
    (conf_dir / "tech_confluence.json").write_text(json.dumps(fake_conf))

    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _sample_accounts()}}
    plan = content_plan(cfg, _sample_plans(), closes_loader=None, root=tmp_path)

    n_charts = len(plan["featured_charts"])
    assert n_charts <= 8, f"Too many featured charts: {n_charts} (cap=8)"


# ---------------------------------------------------------------------------
# 11. Eligibility gate still excludes dead Prophet signals (regression)
# ---------------------------------------------------------------------------

def test_eligibility_gate_still_excludes_invalidated_plans(tmp_path):
    """A QCOM-class invalidated plan must never appear even when confluence is wired."""
    from datetime import datetime, timedelta, timezone as _tz
    fresh = (datetime.now(_tz.utc).date() - timedelta(days=5)).isoformat()

    invalidated = {
        "id": "QCOM-BULL", "asset": "QCOM", "direction": "BULL",
        "entry": 189.2, "invalidation": 177.09, "targets": [207.36],
        "_conviction_score": 75, "_signal_date": fresh,
        "phase": "invalidated", "recommended_action": "invalidated",
        "management_confidence": 13.5, "what_to_do_now": [],
    }

    conf_dir = tmp_path / "site" / "factordata"
    conf_dir.mkdir(parents=True)
    (conf_dir / "tech_confluence.json").write_text(json.dumps(_make_fake_conf()))

    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _sample_accounts()}}
    plan = content_plan(cfg, _sample_plans() + [invalidated], closes_loader=None, root=tmp_path)

    all_tickers = {
        p.get("ticker")
        for a in plan["accounts"]
        for p in a["queue"]
        if p.get("type") == "signal" and p.get("ticker")
        and p.get("source") != "confluence"  # only check Prophet-sourced items
    }
    chart_tickers = {c["ticker"] for c in plan["featured_charts"]}

    assert "QCOM" not in all_tickers, "Invalidated QCOM plan leaked into signal posts"
    assert "QCOM" not in chart_tickers, "Invalidated QCOM plan leaked into charts"


# ---------------------------------------------------------------------------
# F2: leg_families emitted + drives M2 overlay liveness
# ---------------------------------------------------------------------------

def test_fired_combos_emit_leg_families():
    """Every fired combo carries leg_families mapped from the legs catalog."""
    from engine.marketing.confluence_source import fired_combo_signals
    conf = _make_fake_conf()
    fired = fired_combo_signals(conf, top_n=20, today="2026-07-18")
    assert fired, "expected fired combos"
    for sig in fired:
        assert "leg_families" in sig, "leg_families missing from fired combo"
        assert isinstance(sig["leg_families"], list)
    # L0001 has legs [0,1,2] → families ma_crosses, trend, momentum
    aapl = next(s for s in fired if s["combo_id"] == "L0001")
    assert aapl["leg_families"] == ["ma_crosses", "trend", "momentum"], (
        f"leg_families wrong for L0001: {aapl['leg_families']}"
    )


def _make_m2_conf(family: str, ticker: str = "ZM2T") -> dict:
    """A fake conf whose single fired combo has ONE M2 leg of the given family.

    last_fire is computed fresh (1 day ago) so the content_studio freshness gate
    (max_age_days=10, evaluated against the real 'now') always passes.
    """
    from datetime import datetime, timedelta, timezone as _tz
    fresh_fire = (datetime.now(_tz.utc).date() - timedelta(days=1)).isoformat()
    legs = [
        {"leg_id": f"{family}_leg@D", "signal_id": f"{family}_leg", "tf": "D",
         "kind": "event", "family": family, "direction": 1,
         "display_en": "Signal Stack Leg", "display_zh": "信号"},
    ]
    combo = {
        "id": "M2X1", "legs": [0], "dir": 1, "name_en": "M2 combo",
        "h10": {"n": 80, "wr": 0.62, "wr_mc_test": 0.80, "n_test": 15, "months_test": 12},
        "h21": {"n": 80, "wr": 0.65, "wr_mc_test": 0.85, "n_test": 15, "months_test": 12},
        "edge_wr_test": 0.30, "rank_score": 0.18, "n_fires": 80, "n_tickers": 60,
        "fires_last3y": 8, "last_fire": fresh_fire, "first_fire": "2022-01-01",
        "active_now": [ticker], "recent_fires": [],
    }
    return {"generated_utc": "2026-07-18T04:01:46Z", "legs": legs,
            "combos": {"long": [combo], "short": []}}


def _capture_render(monkeypatch):
    """Monkeypatch chart_render so load_ohlcv/build_m2_overlays are synthetic and
    render_chart_v2 records the overlay kwargs it receives. Returns the capture list.
    """
    import engine.marketing.chart_render as cr

    captured: list[dict] = []

    def _fake_load_ohlcv(ticker, root, n=90):
        m = 60
        dates = [f"2026-04-{(i % 27) + 1:02d}" for i in range(m)]
        c = [100.0 + i * 0.2 for i in range(m)]
        o = [c[0]] + c[:-1]
        h = [ci + 1.0 for ci in c]
        l = [ci - 1.0 for ci in c]
        v = [1_000_000.0] * m
        return dates, o, h, l, c, v

    def _fake_build(ticker, dates, o, h, l, c, v, root):
        return {
            "avwap_overlay": {"values": [None] * len(c), "label": "AVWAP · Apr 24"},
            "poc_overlay": {"poc": 105.0, "va_low": 103.0, "va_high": 108.0,
                            "label": "POC 105.00"},
        }

    def _fake_render(*args, **kwargs):
        captured.append({
            "avwap_overlay": kwargs.get("avwap_overlay"),
            "poc_overlay": kwargs.get("poc_overlay"),
            "ticker": kwargs.get("ticker"),
        })
        return "<svg></svg>"

    monkeypatch.setattr(cr, "load_ohlcv", _fake_load_ohlcv)
    monkeypatch.setattr(cr, "build_m2_overlays", _fake_build)
    monkeypatch.setattr(cr, "render_chart_v2", _fake_render)
    return captured


def _run_conf_plan(monkeypatch, tmp_path, family: str):
    captured = _capture_render(monkeypatch)
    conf_dir = tmp_path / "site" / "factordata"
    conf_dir.mkdir(parents=True)
    (conf_dir / "tech_confluence.json").write_text(json.dumps(_make_m2_conf(family)))
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _sample_accounts()}}
    content_plan(cfg, _sample_plans(), closes_loader=None, root=tmp_path)
    # Only the confluence ticker's render call matters.
    return [c for c in captured if c["ticker"] == "ZM2T"]


def test_m2_liveness_volume_profile_leg_gets_poc_only(monkeypatch, tmp_path):
    """A fired combo with a volume_profile_events leg → poc_overlay ONLY."""
    conf_renders = _run_conf_plan(monkeypatch, tmp_path, "volume_profile_events")
    assert conf_renders, "confluence chart was never rendered"
    r = conf_renders[0]
    assert r["poc_overlay"] is not None, "poc_overlay missing for volume_profile_events leg"
    assert r["avwap_overlay"] is None, (
        "avwap_overlay attached though no vwap_events leg fired"
    )


def test_m2_liveness_vwap_leg_gets_avwap_only(monkeypatch, tmp_path):
    """A fired combo with a vwap_events leg → avwap_overlay ONLY."""
    conf_renders = _run_conf_plan(monkeypatch, tmp_path, "vwap_events")
    assert conf_renders, "confluence chart was never rendered"
    r = conf_renders[0]
    assert r["avwap_overlay"] is not None, "avwap_overlay missing for vwap_events leg"
    assert r["poc_overlay"] is None, (
        "poc_overlay attached though no volume_profile_events leg fired"
    )


def test_m2_liveness_non_m2_leg_gets_no_overlays(monkeypatch, tmp_path):
    """A fired combo with only a non-M2 leg → no overlays attached (both None)."""
    conf_renders = _run_conf_plan(monkeypatch, tmp_path, "ma_crosses")
    assert conf_renders, "confluence chart was never rendered"
    r = conf_renders[0]
    assert r["avwap_overlay"] is None and r["poc_overlay"] is None, (
        f"overlays attached for a non-M2 leg: {r}"
    )


def test_win_rate_hook_on_real_fired_combos():
    """If real tech_confluence.json exists, verify hooks for actual fired combos are clean."""
    from engine.marketing.confluence_source import load_confluence, fired_combo_signals, win_rate_hook
    conf = load_confluence(ROOT)
    if conf is None:
        pytest.skip("tech_confluence.json not present")

    fired = fired_combo_signals(conf, today="2026-07-18")
    if not fired:
        pytest.skip("No fresh fired combos in real tech_confluence.json")

    for sig in fired:
        headline, body = win_rate_hook(sig)
        public_copy = headline + " " + body
        match = _FORBIDDEN.search(public_copy)
        assert match is None, (
            f"Forbidden indicator word '{match.group()}' in public copy for "
            f"{sig['ticker']}: {public_copy[:300]}"
        )
        # Cashtag present
        assert f"${sig['ticker']}" in public_copy, (
            f"Cashtag missing for {sig['ticker']}: {public_copy[:200]}"
        )
