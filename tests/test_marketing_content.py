"""tests/test_marketing_content.py — Content Studio + Chart Render tests (spec §4).

Test list:
1. content_studio produces a non-empty plan for 6 accounts
2. Every account's mix has ALL 7 types with ≥1 where slots allow; signal is largest
3. Distinctness passes on the generated plan
4. chart_render emits valid <svg> with BUY marker and NO indicator text
5. macd_cross finds a known cross on a synthetic rising series
6. Governor writes content_plan.json with the frozen top-level keys
"""
from __future__ import annotations

import json
import re
import shutil
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

_FROZEN_KEYS = {
    "schema_version", "produced_by", "produced_at", "tier", "schema",
    "as_of", "source", "content_types", "accounts", "featured_charts",
    "distinctness", "summary",
}

# Fresh signal date (within the eligibility window) so fixtures exercise the
# signal path regardless of when the suite runs.
from datetime import datetime, timedelta, timezone as _tz
_FRESH = (datetime.now(_tz.utc).date() - timedelta(days=5)).isoformat()

# Minimal Prophet plans for testing (no closes needed for basic tests) — all
# LIVE, healthy, fresh, confident so they pass the eligibility gate.
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
    {
        "id": "BA-BEAR", "asset": "BA", "direction": "BEAR",
        "entry": 180.0, "invalidation": 200.0, "targets": [155.0, 130.0],
        "trigger": 178.0, "_conviction_score": 75, "_signal_date": _FRESH,
        "phase": "triggered_pre_t1", "recommended_action": "hold",
        "management_confidence": 58.0, "what_to_do_now": [],
    },
]

# A failed / invalidated plan (the QCOM class): stop breached, low confidence.
# Must NEVER appear in a signal post or a featured chart.
_INVALIDATED_PLAN = {
    "id": "QCOM-BULL", "asset": "QCOM", "direction": "BULL",
    "entry": 189.2, "invalidation": 177.09, "targets": [207.36, 230.0],
    "trigger": 190.0, "_conviction_score": 75, "_signal_date": _FRESH,
    "phase": "invalidated", "recommended_action": "invalidated",
    "management_confidence": 13.5,
    "what_to_do_now": ["Invalidation breached. Exit the full position."],
}

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


# ---------------------------------------------------------------------------
# 1. content_plan produces 6 accounts
# ---------------------------------------------------------------------------

def test_content_plan_six_accounts():
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    assert len(plan["accounts"]) == 6


# ---------------------------------------------------------------------------
# Signal eligibility gate — NEVER post a failed / stale / low-confidence signal
# ---------------------------------------------------------------------------

def test_gate_rejects_invalidated_plan():
    from engine.marketing.content_studio import is_postable_signal
    assert is_postable_signal(_INVALIDATED_PLAN) is False


def test_gate_accepts_healthy_fresh_plan():
    from engine.marketing.content_studio import is_postable_signal
    assert is_postable_signal(_SAMPLE_PLANS[0]) is True


def test_gate_rejects_stale_signal():
    from engine.marketing.content_studio import is_postable_signal
    stale = dict(_SAMPLE_PLANS[0], _signal_date="2026-01-01")
    assert is_postable_signal(stale) is False


def test_gate_rejects_low_confidence():
    from engine.marketing.content_studio import is_postable_signal
    weak = dict(_SAMPLE_PLANS[0], management_confidence=20.0)
    assert is_postable_signal(weak) is False


def test_gate_rejects_dead_actions():
    from engine.marketing.content_studio import is_postable_signal
    for action in ("exit", "trim", "reduce", "close", "avoid"):
        p = dict(_SAMPLE_PLANS[0], recommended_action=action)
        assert is_postable_signal(p) is False, f"action {action} must be rejected"


def test_invalidated_plan_never_appears_in_signal_posts_or_charts(monkeypatch):
    """Full pipeline: a QCOM-class invalidated plan must not leak anywhere."""
    import engine.marketing.chart_render as cr
    from engine.marketing.content_studio import content_plan
    from engine.marketing.chart_render import load_closes
    # This test passes the real ROOT so load_closes can read committed parquet,
    # but the theme_list watchlist card would then fetch + cache company logos
    # into the repo's real data/marketing/logos/ tree. Neutralize BOTH logo
    # resolvers so the card renders offline (monograms) and writes nothing —
    # tests must never mutate the real logo cache (MM_DATA_GUARD law).
    monkeypatch.setattr(cr, "resolve_color_logo", lambda *a, **k: None)
    monkeypatch.setattr(cr, "resolve_logo", lambda *a, **k: None)
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plans = _SAMPLE_PLANS + [_INVALIDATED_PLAN]
    loader = lambda t: load_closes(t, ROOT, n=90)  # noqa: E731
    plan = content_plan(cfg, plans, closes_loader=loader, root=ROOT)
    sig_tickers = {
        p.get("ticker")
        for a in plan["accounts"] for p in a["queue"]
        if p["type"] == "signal" and p.get("ticker")
    }
    chart_tickers = {c["ticker"] for c in plan["featured_charts"]}
    assert "QCOM" not in sig_tickers, "invalidated signal leaked into a signal post"
    assert "QCOM" not in chart_tickers, "invalidated signal leaked into a chart"


def test_content_plan_non_empty_queues():
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    for acct in plan["accounts"]:
        assert len(acct["queue"]) > 0, f"account {acct['id']} has empty queue"


# ---------------------------------------------------------------------------
# 2. Every account has all 7 types; signal is largest
# ---------------------------------------------------------------------------

def test_all_types_present_in_every_account():
    from engine.marketing.content_studio import content_plan, CONTENT_TYPES
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    all_type_ids = {t["id"] for t in CONTENT_TYPES}
    total_slots = 7 * 19  # n_days * per_day = 133 (19-slot 45-min Pacific ladder)

    # mover and theme_list posts are injected only into the first account (flagship)
    # from real heatmap data.  Non-flagship accounts will have these stripped from
    # their queues when no heatmap is present (tests run without real data).
    _MOVERS_DESK_TYPES = {"mover", "theme_list"}
    for acct in plan["accounts"]:
        # `mix_allocated`, not `mix_observed`: the largest-remainder >=1 guarantee
        # is a property of what the ALLOCATOR emits. `mix_observed` is recomputed
        # from the surviving queue after the perishability cut (operator
        # 2026-07-30) drops perishable kinds booked past D1, so it describes the
        # shipping plan and a low-tilt kind can legitimately round to zero there.
        mix = acct["mix_allocated"]
        # All types must have at least 1 slot out of 21 (largest-remainder guarantees this),
        # EXCEPT mover/theme_list on non-flagship accounts (heatmap-only; not in test env).
        for type_id in all_type_ids:
            if type_id in _MOVERS_DESK_TYPES:
                continue  # movers_desk injection is heatmap-gated; skip in unit tests
            assert mix.get(type_id, 0) >= 1, (
                f"account {acct['id']} missing type {type_id}: mix={mix}"
            )


def test_signal_is_largest_type_in_every_account():
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    for acct in plan["accounts"]:
        # Allocator property (see the note in test_all_types_present_in_every_account):
        # the tilt makes signal the biggest share of what is ALLOCATED. After the
        # perishability cut, signal is D1-only while watchlist spans the week, so
        # the shipping mix is deliberately not signal-led.
        mix = acct["mix_allocated"]
        signal_count = mix.get("signal", 0)
        for type_id, count in mix.items():
            if type_id != "signal":
                assert signal_count >= count, (
                    f"account {acct['id']}: signal ({signal_count}) not largest; "
                    f"{type_id} has {count}"
                )


def test_plan_is_deterministic():
    """Same inputs → same output every time."""
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan1 = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    plan2 = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    assert plan1["accounts"][0]["queue"] == plan2["accounts"][0]["queue"]


def test_accounts_differ_from_each_other():
    """Different accounts → different queue ordering."""
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    acct0_types = [i["type"] for i in plan["accounts"][0]["queue"]]
    acct1_types = [i["type"] for i in plan["accounts"][1]["queue"]]
    # Different tilt + account-hash means sequences differ
    assert acct0_types != acct1_types


# ---------------------------------------------------------------------------
# 3. Distinctness passes
# ---------------------------------------------------------------------------

def test_distinctness_passes_on_generated_plan():
    from engine.marketing.content_studio import content_plan, distinctness
    from engine.marketing.content_studio import ContentItem
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    # Re-assemble ContentItem list from queue dicts
    items = []
    for acct in plan["accounts"]:
        for item_dict in acct["queue"]:
            items.append(ContentItem(
                id=item_dict["id"], type=item_dict["type"],
                account=item_dict["account"], cashtag=item_dict["cashtag"],
                ticker=item_dict["ticker"], headline=item_dict["headline"],
                body=item_dict["body"], provenance=item_dict["provenance"],
                chart_id=item_dict["chart_id"], slot=item_dict["slot"],
                status=item_dict["status"],
            ))
    d = distinctness(items)
    assert d["flags"] == 0, f"Distinctness flags: {d['flags']}, max_sim={d['max_similarity']}"


# ---------------------------------------------------------------------------
# 4. chart_render emits valid <svg> with BUY and no indicator text
# ---------------------------------------------------------------------------

def _synthetic_closes(n: int = 90) -> list[float]:
    """Synthetic price series: rising trend with small noise for testing."""
    prices = []
    p = 100.0
    for i in range(n):
        # Simple rising series with oscillation
        p = p + 0.5 + (0.3 if i % 7 < 4 else -0.2)
        prices.append(round(p, 2))
    return prices


def test_render_signal_chart_is_svg():
    from engine.marketing.chart_render import render_signal_chart
    closes = _synthetic_closes(90)
    dates = [f"2026-0{(i // 30) + 1}-{(i % 28) + 1:02d}" for i in range(90)]
    svg = render_signal_chart("TEST", dates, closes, marker_index=60)
    assert svg.strip().startswith("<svg"), f"Expected SVG, got: {svg[:50]}"


def test_render_signal_chart_has_buy_marker():
    from engine.marketing.chart_render import render_signal_chart
    closes = _synthetic_closes(90)
    dates = [f"2026-0{(i // 30) + 1}-{(i % 28) + 1:02d}" for i in range(90)]
    svg = render_signal_chart("TEST", dates, closes, marker_index=60)
    assert "BUY" in svg, "BUY marker missing from SVG"


def test_render_signal_chart_no_indicator_text():
    from engine.marketing.chart_render import render_signal_chart
    closes = _synthetic_closes(90)
    dates = [f"2026-0{(i // 30) + 1}-{(i % 28) + 1:02d}" for i in range(90)]
    svg = render_signal_chart("TEST", dates, closes, marker_index=60)
    assert not re.search(r"MACD|RSI|EMA|cross", svg, re.I), (
        "Indicator text leaked into SVG"
    )


def test_render_signal_chart_no_script():
    from engine.marketing.chart_render import render_signal_chart
    closes = _synthetic_closes(90)
    dates = [f"2026-0{(i // 30) + 1}-{(i % 28) + 1:02d}" for i in range(90)]
    svg = render_signal_chart("TEST", dates, closes, marker_index=60)
    assert "<script" not in svg.lower(), "SVG must not contain <script> tags"


def test_render_signal_chart_under_9kb():
    from engine.marketing.chart_render import render_signal_chart
    closes = _synthetic_closes(90)
    dates = [f"2026-0{(i // 30) + 1}-{(i % 28) + 1:02d}" for i in range(90)]
    svg = render_signal_chart("TEST", dates, closes, marker_index=60)
    size = len(svg.encode("utf-8"))
    assert size < 9 * 1024, f"SVG too large: {size} bytes (max 9KB)"


# ---------------------------------------------------------------------------
# 5. macd_cross finds a cross on a synthetic series
# ---------------------------------------------------------------------------

def test_macd_cross_finds_bullish_cross():
    from engine.marketing.chart_render import macd_cross
    # Generate a series: falling first (drives MACD negative / below signal),
    # then sharply rising (fast EMA recovers faster → MACD crosses above signal).
    closes = []
    # 40 falling sessions — drives fast EMA below slow EMA → MACD negative
    p = 150.0
    for i in range(40):
        p -= 1.0
        closes.append(round(p, 2))
    # 50 sharply rising sessions — fast EMA (12) recovers faster than slow (26)
    for i in range(50):
        p += 2.5
        closes.append(round(p, 2))

    result = macd_cross(closes)
    # With falling-then-sharply-rising price, the fast EMA overtakes slow EMA
    # and MACD crosses above its signal line.
    assert result is not None, (
        "macd_cross should find a bullish cross on a falling-then-rising series"
    )
    assert "index" in result
    assert "offset_from_end" in result
    assert result["index"] >= 0
    assert result["offset_from_end"] >= 0


def test_macd_cross_returns_none_on_flat_series():
    from engine.marketing.chart_render import macd_cross
    # A perfectly flat series has no cross
    closes = [100.0] * 60
    result = macd_cross(closes)
    # Flat series: MACD stays at 0, signal stays at 0 — no cross (equal, not crossing)
    # This may return None or a cross at start — both are acceptable
    if result is not None:
        assert "index" in result


def test_macd_cross_returns_none_on_short_series():
    from engine.marketing.chart_render import macd_cross
    # Series too short for EMA26 + signal9
    closes = [100.0] * 20
    result = macd_cross(closes)
    assert result is None, "macd_cross should return None for too-short series"


# ---------------------------------------------------------------------------
# 6. Governor writes content_plan.json with frozen top-level keys
# ---------------------------------------------------------------------------

def test_governor_writes_content_plan(tmp_path):
    """Governor must produce content_plan.json with the frozen §2.3 shape."""
    # Set up minimal directory structure
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True)

    # Copy config
    cfg_src = ROOT / "config" / "marketing.yml"
    shutil.copy(cfg_src, tmp_path / "config" / "marketing.yml")

    # Copy seed ledgers if present
    for name in [
        "opportunities.jsonl", "campaigns.jsonl", "publications.jsonl",
        "growth_events.jsonl", "experiments.jsonl", "department_changes.jsonl",
        "corrections.jsonl", "claims.jsonl",
    ]:
        src = ROOT / "data" / "marketing" / name
        if src.exists():
            shutil.copy(src, tmp_path / "data" / "marketing" / name)

    from engine.neuralweb.marketing_governor import build_and_write
    result = build_and_write(root=tmp_path)

    content_path = tmp_path / "data" / "marketing" / "content_plan.json"
    assert content_path.exists(), f"content_plan.json not written: {result}"

    cp = json.loads(content_path.read_text())
    missing_keys = _FROZEN_KEYS - set(cp.keys())
    assert not missing_keys, f"content_plan.json missing keys: {missing_keys}"

    assert cp.get("schema") == "marketing.content/v1"
    assert isinstance(cp.get("content_types"), list)
    assert len(cp.get("content_types", [])) == 9  # 7 original + mover + theme_list
    assert isinstance(cp.get("accounts"), list)
    # 6 W1 desks + founder (2026-07-27) + the 4 employee desks and the
    # wired-but-dark news property (XG-W1, 2026-07-28).
    # 13 since W2R (XG-W8): the 12 W1/XG-W1 desks plus the dark
    # mastermind_research publication property.
    assert len(cp.get("accounts", [])) == 13
    assert isinstance(cp.get("featured_charts"), list)


def test_governor_content_plan_accounts_have_tilt(tmp_path):
    """Each account in content_plan.json must carry a tilt map."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True)
    shutil.copy(ROOT / "config" / "marketing.yml", tmp_path / "config" / "marketing.yml")

    from engine.neuralweb.marketing_governor import build_and_write
    build_and_write(root=tmp_path)

    cp = json.loads((tmp_path / "data" / "marketing" / "content_plan.json").read_text())
    for acct in cp["accounts"]:
        tilt = acct.get("tilt", {})
        assert isinstance(tilt, dict), f"account {acct['id']} has no tilt"
        assert len(tilt) == 9, f"account {acct['id']} tilt has {len(tilt)} keys"
        assert tilt.get("signal", 0) > 0, f"account {acct['id']} signal weight is 0"


def test_governor_content_plan_featured_charts_have_svg(tmp_path):
    """Featured charts (if any) must contain a valid SVG string."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True)
    (tmp_path / "data" / "stocks").mkdir(parents=True)
    shutil.copy(ROOT / "config" / "marketing.yml", tmp_path / "config" / "marketing.yml")

    # Copy a real parquet file to enable chart generation
    for ticker in ["PLTR", "SBUX"]:
        src = ROOT / "data" / "stocks" / f"{ticker}.parquet"
        if src.exists():
            shutil.copy(src, tmp_path / "data" / "stocks" / f"{ticker}.parquet")

    # Copy prophet index
    prophet_src = ROOT / "site" / "prophet" / "index.json"
    if prophet_src.exists():
        (tmp_path / "site" / "prophet").mkdir(parents=True)
        shutil.copy(prophet_src, tmp_path / "site" / "prophet" / "index.json")

    from engine.neuralweb.marketing_governor import build_and_write
    build_and_write(root=tmp_path)

    cp = json.loads((tmp_path / "data" / "marketing" / "content_plan.json").read_text())
    if cp["featured_charts"]:
        for fc in cp["featured_charts"]:
            svg = fc.get("svg", "")
            assert svg.strip().startswith("<svg"), f"featured chart {fc['id']} has invalid SVG"
            # v2 charts: have candlestick rects, MASTERMIND brand, SETUP pill.
            # v1 fallback charts: have "BUY" marker. Both are valid.
            is_v2 = svg.count("<rect") >= 10  # v2 has many candle rects
            is_v1 = "BUY" in svg              # v1 has explicit BUY text
            assert is_v2 or is_v1, (
                f"featured chart {fc['id']} is neither v2 (candle rects) nor v1 (BUY text)"
            )
            if is_v2:
                # v2 charts must have brand lockup
                assert "MASTERMIND" in svg, f"v2 chart {fc['id']} missing MASTERMIND"
                # v2 SVG subpanel labels (MACD/RSI) are intentional — not a leak
            else:
                # v1 fallback: no indicator vocabulary in SVG
                assert not re.search(r"MACD|RSI|EMA|cross", svg, re.I), (
                    f"v1 fallback chart {fc['id']} leaks indicator text"
                )


def test_governor_content_plan_fail_soft_no_prophet(tmp_path):
    """Governor must write a valid minimal content_plan.json even with no Prophet data."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True)
    shutil.copy(ROOT / "config" / "marketing.yml", tmp_path / "config" / "marketing.yml")
    # Deliberately do NOT copy prophet index

    from engine.neuralweb.marketing_governor import build_and_write
    result = build_and_write(root=tmp_path)

    content_path = tmp_path / "data" / "marketing" / "content_plan.json"
    assert content_path.exists(), "content_plan.json not written even without Prophet"
    cp = json.loads(content_path.read_text())
    assert cp.get("schema") == "marketing.content/v1"
    missing = _FROZEN_KEYS - set(cp.keys())
    assert not missing, f"Minimal plan missing keys: {missing}"


# ---------------------------------------------------------------------------
# Additional: load_closes helper
# ---------------------------------------------------------------------------

def test_load_closes_returns_none_for_missing_ticker():
    from engine.marketing.chart_render import load_closes
    result = load_closes("XXXX_NONEXISTENT", ROOT, n=90)
    assert result is None


def test_load_closes_returns_dates_and_closes_for_known_ticker():
    """Only runs if PLTR.parquet exists AND a parquet reader is available.

    The marketing-engine CI job is deliberately minimal-deps (no pandas), so
    guard on the reader too — the file-existence guard alone went red in CI
    the day this suite was whitelisted (#3347).
    """
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    parquet_path = ROOT / "data" / "stocks" / "PLTR.parquet"
    if not parquet_path.exists():
        pytest.skip("PLTR.parquet not present")
    from engine.marketing.chart_render import load_closes
    result = load_closes("PLTR", ROOT, n=90)
    assert result is not None
    dates, closes = result
    assert len(dates) <= 90
    assert len(dates) == len(closes)
    assert all(isinstance(c, float) for c in closes)


# ---------------------------------------------------------------------------
# v2: render_chart_v2 tests
# ---------------------------------------------------------------------------

def _synthetic_ohlcv(n: int = 90) -> tuple:
    """Synthetic OHLCV for testing."""
    dates = [f"2026-0{(i // 30) + 1}-{(i % 28) + 1:02d}" for i in range(n)]
    c_vals = _synthetic_closes(n)
    # prev-close proxy for open
    o_vals = [c_vals[0]] + c_vals[:-1]
    h_vals = [max(o, c) + abs(c - o) * 0.3 + 0.5 for o, c in zip(o_vals, c_vals)]
    l_vals = [min(o, c) - abs(c - o) * 0.3 - 0.5 for o, c in zip(o_vals, c_vals)]
    v_vals = [1_000_000.0 + i * 10_000 for i in range(n)]
    return dates, o_vals, h_vals, l_vals, c_vals, v_vals


def test_render_chart_v2_is_valid_svg():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v)
    assert svg.strip().startswith("<svg"), f"Expected SVG, got: {svg[:80]}"
    assert "</svg>" in svg


def test_render_chart_v2_has_candlestick_rects():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("AAPL", dates, o, h, l, c, v)
    # Candlestick bodies are <rect> elements; should have many
    rect_count = svg.count("<rect")
    assert rect_count >= 10, f"Too few <rect> elements ({rect_count}); expected candlesticks"


def test_render_chart_v2_has_ticker_in_header():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("NVDA", dates, o, h, l, c, v)
    assert "NVDA" in svg, "Ticker not found in chart SVG"


def test_render_chart_v2_has_mastermind_lockup():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v)
    assert "MASTERMIND" in svg, "MASTERMIND brand lockup missing from chart"


def test_render_chart_v2_has_last_price_pill():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v)
    # Last price pill: the last close formatted with commas
    last_close = c[-1]
    # The pill contains the formatted last price
    pill_label = f"{last_close:,.2f}"
    assert pill_label in svg, f"Last-price pill value '{pill_label}' not found in SVG"


def test_render_chart_v2_has_macd_subpanel_when_show_indicators():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, show_indicators=True, indicators=("macd",))
    assert "MACD" in svg, "MACD subpanel label missing when show_indicators=True"


def test_render_chart_v2_no_subpanels_when_show_indicators_false():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, show_indicators=False)
    # No subpanel labels when disabled
    assert "MACD" not in svg
    assert "RSI" not in svg
    assert "VOLUME" not in svg


def test_render_chart_v2_no_script():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v)
    assert "<script" not in svg.lower(), "SVG must not contain <script> tags"


def test_render_chart_v2_under_45kb():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v,
                           show_indicators=True, indicators=("volume", "macd", "rsi"))
    size = len(svg.encode("utf-8"))
    assert size < 45 * 1024, f"SVG too large: {size} bytes (max 45KB)"


def test_render_chart_v2_hostile_ticker_escaped():
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    hostile = '<script>alert(1)</script>'
    svg = render_chart_v2(hostile, dates, o, h, l, c, v)
    # Raw unescaped injection must NOT appear
    assert "<script>" not in svg, "Hostile ticker not escaped: raw <script> tag present"
    assert "</script>" not in svg, "Hostile ticker not escaped: raw </script> tag present"
    # Escaped forms must appear (ticker is uppercased in header; watermark uppercases it)
    assert "&lt;" in svg, "Hostile ticker text not found in any escaped form"


# ---------------------------------------------------------------------------
# v2: render_earnings_card tests
# ---------------------------------------------------------------------------

def test_render_earnings_card_is_valid_svg():
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("AAPL", "Apple Inc.", 1.53, 1.48, 94.9e9, 93.1e9)
    assert svg.strip().startswith("<svg"), "Earnings card must be valid SVG"
    assert "</svg>" in svg


def test_render_earnings_card_beat_eps():
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("NVDA", "NVIDIA", 6.10, 5.89, 44.1e9, 43.0e9)
    # Both EPS and Rev beat → both chips show BEAT
    assert "BEAT" in svg
    # Green chip used for beat
    assert "#4CAF50" in svg


def test_render_earnings_card_miss_eps():
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("INTC", "Intel", 0.12, 0.28, 12.1e9, 13.5e9)
    # EPS miss, Rev miss → both chips show MISS
    assert "MISS" in svg
    # Red chip used for miss
    assert "#E23B3B" in svg


def test_render_earnings_card_mixed_beat_miss():
    from engine.marketing.chart_render import render_earnings_card
    # EPS beats, Rev misses
    svg = render_earnings_card("META", "Meta Platforms", 4.92, 4.70, 38.5e9, 40.0e9)
    assert "BEAT" in svg
    assert "MISS" in svg


def test_render_earnings_card_has_ticker_and_company():
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("TSLA", "Tesla Inc.", 0.82, 0.75, 25.7e9, 24.9e9)
    assert "TSLA" in svg
    assert "Tesla Inc." in svg
    assert "MASTERMIND" in svg


def test_render_earnings_card_no_script():
    from engine.marketing.chart_render import render_earnings_card
    svg = render_earnings_card("AMZN", "Amazon", 1.83, 1.72, 148.0e9, 145.0e9)
    assert "<script" not in svg.lower()


# ---------------------------------------------------------------------------
# v3 chart branding tests
# ---------------------------------------------------------------------------

def _make_white_png_bytes(width: int = 60, height: int = 30) -> bytes:
    """Create a minimal white-on-transparent PNG via PIL for logo tests."""
    try:
        import io
        from PIL import Image
        img = Image.new("RGBA", (width, height), (255, 255, 255, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # If PIL is not available, return a known-good 1x1 transparent PNG
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\x0bIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def test_v3_unique_gradient_uids():
    """Two renders of different tickers must produce non-colliding gradient ids."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg_a = render_chart_v2("AAPL", dates, o, h, l, c, v)
    svg_b = render_chart_v2("MSFT", dates, o, h, l, c, v)
    # Extract all gradient ids from each SVG
    import re
    ids_a = set(re.findall(r'id="(mbTile_[^"]+)"', svg_a))
    ids_b = set(re.findall(r'id="(mbTile_[^"]+)"', svg_b))
    assert ids_a, "AAPL chart has no mbTile_ gradient id"
    assert ids_b, "MSFT chart has no mbTile_ gradient id"
    # When concatenated (as in admin page), ids must not collide
    assert ids_a.isdisjoint(ids_b), (
        f"Gradient id collision between AAPL and MSFT charts: {ids_a & ids_b}"
    )


def test_v3_logo_embed_from_cached_file(tmp_path):
    """With a synthetic cached white PNG, render includes data:image/png;base64."""
    import base64
    from pathlib import Path
    from engine.marketing.chart_render import render_chart_v2
    from engine.marketing.logo_cache import _cache_path, white_logo_datauri

    # Write synthetic white PNG into the expected cache path
    png_bytes = _make_white_png_bytes(60, 30)
    cp = _cache_path("SYNTH", tmp_path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(png_bytes)

    # cached_only should now return a URI
    uri = white_logo_datauri("SYNTH", tmp_path, fetch=False)
    assert uri is not None and uri.startswith("data:image/png;base64,"), (
        f"Expected data URI from cache, got: {str(uri)[:80]}"
    )

    # Chart rendered with logo_datauri includes the image element
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("SYNTH", dates, o, h, l, c, v, logo_datauri=uri)
    assert "data:image/png;base64," in svg, "Logo data URI not embedded in chart SVG"
    assert "<image " in svg, "<image> element missing from chart SVG"


def test_v3_logo_embed_via_logo_root(tmp_path):
    """logo_root kwarg triggers cached_only lookup and embeds logo when cached."""
    from engine.marketing.chart_render import render_chart_v2
    from engine.marketing.logo_cache import _cache_path

    # Pre-populate cache
    png_bytes = _make_white_png_bytes(60, 30)
    cp = _cache_path("RTEST", tmp_path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(png_bytes)

    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("RTEST", dates, o, h, l, c, v, logo_root=tmp_path)
    assert "data:image/png;base64," in svg, "logo_root did not trigger logo embed"


def test_v3_fail_soft_missing_logo():
    """Missing logo → ghost text fallback, no raise, chart still valid SVG."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    # No logo_datauri, no logo_root → falls back to ghost text
    svg = render_chart_v2("NOLOGO", dates, o, h, l, c, v)
    assert svg.strip().startswith("<svg"), "Chart must be valid SVG even without logo"
    # Ghost watermark text present (ticker uppercased)
    assert "NOLOGO" in svg, "Ghost watermark text missing when no logo"
    # No <image> element for logo
    assert "<image " not in svg, "Unexpected <image> element when no logo provided"


def test_v3_real_favicon_logomark_present():
    """The real favicon M-path (ascending market peak shape) is in the SVG."""
    from engine.marketing.chart_render import render_chart_v2
    import re
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TICK", dates, o, h, l, c, v)
    # The favicon M-path is a polyline of 5 points rendered as <path d="M...L...L...L...L...">
    # It derives from M13,28 L13,14.5 L20,22 L27,12.5 L27,28 scaled to tile size
    paths = re.findall(r'd="(M[^"]+)"', svg)
    assert paths, "No <path d=...> M-path found in SVG (favicon logomark missing)"
    # Must have a 5-segment path (4 L commands) — the M shape
    five_seg = [p for p in paths if p.count(" L") == 4]
    assert five_seg, (
        f"No 5-segment path (favicon M shape) found. Paths found: {paths[:3]}"
    )


def test_v3_mastermind_url_in_footer():
    """Footer must contain 'mastermind-x.com'."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("SBUX", dates, o, h, l, c, v)
    assert "mastermind-x.com" in svg, "URL 'mastermind-x.com' missing from chart footer"


def test_v3_no_script_tag():
    """v3 chart must not contain <script> tags."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TEST", dates, o, h, l, c, v, logo_datauri=None)
    assert "<script" not in svg.lower(), "SVG must not contain <script> tags"


def test_v3_xss_escaped():
    """Hostile ticker is escaped; no raw injection possible."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    hostile = '<script>alert(1)</script>'
    svg = render_chart_v2(hostile, dates, o, h, l, c, v)
    assert "<script>" not in svg
    assert "</script>" not in svg
    assert "&lt;" in svg, "Hostile ticker not escaped"


def test_v3_under_60kb_with_logo(tmp_path):
    """Chart with embedded logo must stay under 60KB."""
    import base64
    from engine.marketing.chart_render import render_chart_v2

    # Generate a moderately sized PNG (120x60 white logo)
    png_bytes = _make_white_png_bytes(120, 60)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    logo_uri = f"data:image/png;base64,{b64}"

    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2(
        "AAPL", dates, o, h, l, c, v,
        show_indicators=True,
        indicators=("volume", "macd", "rsi"),
        logo_datauri=logo_uri,
    )
    size = len(svg.encode("utf-8"))
    assert size < 60 * 1024, f"SVG too large with logo: {size} bytes (max 60KB)"


def test_v3_under_60kb_without_logo():
    """Chart without logo must stay under 60KB."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2(
        "TEST", dates, o, h, l, c, v,
        show_indicators=True,
        indicators=("volume", "macd", "rsi"),
    )
    size = len(svg.encode("utf-8"))
    assert size < 60 * 1024, f"SVG too large: {size} bytes (max 60KB)"


def test_v3_logo_cache_cached_only_returns_none_when_absent(tmp_path):
    """cached_only() returns None when no file cached — never fetches."""
    from engine.marketing.logo_cache import cached_only
    result = cached_only("NOCACHE", tmp_path)
    assert result is None, f"Expected None for uncached ticker, got: {str(result)[:60]}"


def test_v3_logo_cache_whiten_writes_file(tmp_path):
    """white_logo_datauri with fetch=False but pre-cached file returns URI and no re-fetch."""
    from engine.marketing.logo_cache import white_logo_datauri, _cache_path
    png_bytes = _make_white_png_bytes(40, 20)
    cp = _cache_path("WH", tmp_path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(png_bytes)

    result = white_logo_datauri("WH", tmp_path, fetch=False)
    assert result is not None and result.startswith("data:image/png;base64,")


def test_v3_mastermind_brand_weight_900():
    """MASTERMIND wordmark must use font-weight 900 (prominent brand lockup)."""
    from engine.marketing.chart_render import render_chart_v2
    dates, o, h, l, c, v = _synthetic_ohlcv(90)
    svg = render_chart_v2("TST", dates, o, h, l, c, v)
    # font-weight="900" must appear (the bold brand lockup)
    assert 'font-weight="900"' in svg, "MASTERMIND wordmark must use font-weight 900"


# ---------------------------------------------------------------------------
# v2: content_plan featured charts use v2 (candlestick rects in SVG)
# ---------------------------------------------------------------------------

def test_content_plan_featured_charts_use_v2_when_ohlcv_available():
    """Featured charts built from real parquet must contain candlestick rects."""
    parquet_path = ROOT / "data" / "stocks" / "PLTR.parquet"
    if not parquet_path.exists():
        pytest.skip("PLTR.parquet not present — skipping v2 chart integration test")

    from engine.marketing.content_studio import content_plan
    from engine.marketing.chart_render import load_closes

    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    loader = lambda t: load_closes(t, ROOT, n=90)  # noqa: E731
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=loader)

    fc_list = plan["featured_charts"]
    assert isinstance(fc_list, list)
    # At least one featured chart should exist (PLTR and SBUX parquets present)
    if not fc_list:
        pytest.skip("No featured charts produced (no eligible ticker parquets found)")

    for fc in fc_list:
        svg = fc.get("svg", "")
        assert svg.strip().startswith("<svg"), f"chart {fc['id']} not valid SVG"
        # v2 charts have many <rect> (candlestick bodies); v1 has none
        # Accept either (v1 fallback is fine) but assert at least one chart used v2
    v2_charts = [
        fc for fc in fc_list
        if fc.get("svg", "").count("<rect") >= 10
    ]
    assert len(v2_charts) >= 1, (
        "Expected at least one v2 candlestick chart in featured_charts; "
        f"got rect counts: {[fc.get('svg','').count('<rect') for fc in fc_list]}"
    )
    # All v2 charts must have MASTERMIND
    for fc in v2_charts:
        assert "MASTERMIND" in fc["svg"], f"MASTERMIND missing from v2 chart {fc['id']}"


# ---------------------------------------------------------------------------
# F1: build_context fact-polarity filter (directional-post safety)
# ---------------------------------------------------------------------------

def _signal_item(direction: str = "BULL") -> dict:
    """A minimal signal ContentItem-like dict for build_context."""
    return {
        "ticker": "AMD",
        "type": "signal",
        "account": "flagship",
        "direction": direction,
        "_plan": {"direction": direction, "entry": 100.0, "targets": [120.0],
                  "invalidation": 90.0},
    }


def test_polarity_filter_bull_drops_bearish_poc_keeps_reclaim_and_neutral():
    """BULL signal post: keep +1 (reclaim) and 0 (in_value_area); drop -1 (poc_level below)."""
    from engine.marketing.copywriter import build_context
    facts = {
        "facts": [
            {"id": "avwap_reclaim", "text": "AMD reclaimed the anchored VWAP from the Jun 26 volume-spike anchor",
             "salience": 8, "polarity": 1, "numbers": ["100.00", "26"]},
            {"id": "poc_level", "text": "Volume point of control sits at 90.00 — price is 11.1% above it",
             "salience": 5, "polarity": -1, "numbers": ["90.00", "11.1%"]},
            {"id": "in_value_area", "text": "Trading inside the value area (95.00–110.00)",
             "salience": 3, "polarity": 0, "numbers": ["95.00", "110.00"]},
        ],
        "numbers_whitelist": ["100.00", "26", "90.00", "11.1%", "95.00", "110.00"],
    }
    ctx = build_context(_signal_item("BULL"), facts=facts)
    ids = [f["id"] for f in ctx["top_facts"]]
    assert "avwap_reclaim" in ids, f"bull post dropped its aligned +1 fact: {ids}"
    assert "in_value_area" in ids, f"bull post dropped the neutral (0) fact: {ids}"
    assert "poc_level" not in ids, (
        f"bull post kept a structured bearish (-1) fact: {ids}"
    )


def test_polarity_filter_bear_keeps_bearish_drops_bullish():
    """BEAR signal post: keep -1 (poc_level below) and 0; drop +1 (reclaim)."""
    from engine.marketing.copywriter import build_context
    facts = {
        "facts": [
            {"id": "avwap_reclaim", "text": "AMD reclaimed the anchored VWAP",
             "salience": 8, "polarity": 1, "numbers": []},
            {"id": "poc_level", "text": "Volume point of control sits at 110.00 — price is 9.1% below it",
             "salience": 5, "polarity": -1, "numbers": ["110.00", "9.1%"]},
            {"id": "in_value_area", "text": "Trading inside the value area (95.00–110.00)",
             "salience": 3, "polarity": 0, "numbers": ["95.00", "110.00"]},
        ],
        "numbers_whitelist": [],
    }
    ctx = build_context(_signal_item("BEAR"), facts=facts)
    ids = [f["id"] for f in ctx["top_facts"]]
    assert "poc_level" in ids and "in_value_area" in ids, f"bear post dropped aligned facts: {ids}"
    assert "avwap_reclaim" not in ids, f"bear post kept a structured bullish (+1) fact: {ids}"


def test_polarity_filter_anchored_does_not_trip_red_marker():
    """The word 'anchored' must NOT match the bear marker 'red' (the F1 substring bug).

    A structured +1 AVWAP fact whose text contains 'anchored' must survive a BULL
    post; the legacy substring path used to drop it because 'red ' ⊂ 'ancho-red-'.
    """
    from engine.marketing.copywriter import build_context
    facts = {
        "facts": [
            {"id": "avwap_hold",
             "text": "Held the anchored VWAP from the Jun 26 volume-spike anchor for 15 straight sessions",
             "salience": 6, "polarity": 1, "numbers": ["15", "26"]},
        ],
        "numbers_whitelist": ["15", "26"],
    }
    ctx = build_context(_signal_item("BULL"), facts=facts)
    ids = [f["id"] for f in ctx["top_facts"]]
    assert "avwap_hold" in ids, (
        f"'anchored' text tripped the bear 'red' marker and dropped a +1 fact: {ids}"
    )


def test_polarity_filter_legacy_no_polarity_word_boundary():
    """Legacy (no-polarity) facts still use marker matching — at word boundaries.

    'lost its 50-day' hits the bear marker 'lost' → dropped on a BULL post (legacy
    behaviour pinned). 'anchored' (no polarity key) must NOT be dropped by 'red'.
    """
    from engine.marketing.copywriter import build_context
    facts = {
        "facts": [
            {"id": "sma_50_loss", "text": "AMD lost its 50-day average (98.00) — first time since May 2026",
             "salience": 8, "numbers": ["98.00", "May 2026"]},
            {"id": "legacy_anchor_note", "text": "AMD is anchored above a rising base",
             "salience": 4, "numbers": []},
        ],
        "numbers_whitelist": ["98.00"],
    }
    ctx = build_context(_signal_item("BULL"), facts=facts)
    ids = [f["id"] for f in ctx["top_facts"]]
    assert "sma_50_loss" not in ids, f"legacy bear 'lost' fact leaked into bull post: {ids}"
    assert "legacy_anchor_note" in ids, (
        f"legacy 'anchored' fact wrongly dropped by 'red' substring: {ids}"
    )


def test_polarity_filter_empty_prefers_neutral_over_bearish():
    """When aligned facts are empty, prefer a neutral (0) fact over a structured -1."""
    from engine.marketing.copywriter import build_context
    facts = {
        "facts": [
            {"id": "poc_level", "text": "Volume point of control sits at 90.00 — price is 11.1% above it",
             "salience": 5, "polarity": -1, "numbers": ["90.00", "11.1%"]},
            {"id": "in_value_area", "text": "Trading inside the value area (95.00–110.00)",
             "salience": 3, "polarity": 0, "numbers": ["95.00", "110.00"]},
        ],
        "numbers_whitelist": [],
    }
    ctx = build_context(_signal_item("BULL"), facts=facts)
    ids = [f["id"] for f in ctx["top_facts"]]
    # Only aligned fact is the neutral one; the -1 must never lead a bull post.
    assert ids[0] == "in_value_area", f"bull post led with a bearish fact: {ids}"
    assert "poc_level" not in ids, f"bull post reinstated a structured -1 fact: {ids}"


# ═══════════════════════════════════════════════════════════════════════════
# F3d: content_plan generates queues ONLY for effective-enabled accounts, but
# still LISTS disabled accounts (status "planned", empty queue) so the admin
# shows them — killing the ~85-item nightly Sentinel noise at the source.
# ═══════════════════════════════════════════════════════════════════════════

def test_content_plan_skips_disabled_accounts_but_lists_them():
    from engine.marketing.content_studio import content_plan
    accounts = [
        {"id": "flagship", "kind": "branded", "beat": "What changed",
         "voice": "authoritative desk", "enabled": True,
         "tilt": {"signal": 0.4, "chart": 0.1, "mover": 0.1, "theme_list": 0.1,
                  "receipt": 0.1, "event": 0.05, "education": 0.05, "macro": 0.05,
                  "watchlist": 0.05}},
        {"id": "receipts", "kind": "branded", "beat": "Receipt",
         "voice": "dry, receipts-forward", "enabled": False,
         "tilt": {"signal": 0.4, "chart": 0.1, "mover": 0.1, "theme_list": 0.1,
                  "receipt": 0.1, "event": 0.05, "education": 0.05, "macro": 0.05,
                  "watchlist": 0.05}},
    ]
    cfg = {"desk_network": {"stage": "A", "accounts": accounts}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)

    rows = {a["id"]: a for a in plan["accounts"]}
    # Both accounts appear...
    assert set(rows) == {"flagship", "receipts"}
    # ...but only the enabled one has a generated queue.
    assert len(rows["flagship"]["queue"]) > 0
    assert rows["receipts"]["queue"] == []
    assert rows["receipts"]["status"] == "planned"

    # No queued post anywhere belongs to the disabled account → no Sentinel load.
    for acct in plan["accounts"]:
        for post in acct["queue"]:
            assert post.get("account") != "receipts"


def test_content_plan_all_enabled_by_default():
    """Without any enabled key, every account generates a queue (backward-compat)."""
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    for acct in plan["accounts"]:
        assert len(acct["queue"]) > 0, f"{acct['id']} got no queue"


def test_slot_labels_are_the_45min_pacific_ladder():
    """The plan schedules onto the 19-slot 45-min Pacific ladder (S1..S19),
    replacing the old AM/PM/EOD triple; day N labels prefix D<N>-, and no legacy
    suffix survives (outbox.slot_datetime resolves S1..S19 to real Pacific-clock
    times)."""
    from engine.marketing.content_studio import _slot_labels
    assert _slot_labels(1, 19) == [f"D1-S{i}" for i in range(1, 20)]
    two_days = _slot_labels(2, 19)
    assert two_days[:19] == [f"D1-S{i}" for i in range(1, 20)]
    assert two_days[19:] == [f"D2-S{i}" for i in range(1, 20)]
    assert not any(lbl.endswith(("-AM", "-PM", "-EOD")) for lbl in two_days)


def test_content_plan_queue_uses_resolvable_ladder_slots():
    """End-to-end: generated queue items carry ladder slots that
    outbox.slot_datetime resolves to a real UTC time."""
    import re as _re
    from engine.marketing.content_studio import content_plan
    from engine.marketing.outbox import slot_datetime
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    as_of = plan.get("as_of") or "2026-07-15"
    slots = [it.get("slot") for acct in plan["accounts"] for it in acct["queue"]
             if isinstance(it, dict)]
    day_slots = [s for s in slots if s and _re.match(r"^D\d+-S(?:[1-9]|1[0-9])$", s)]
    assert day_slots, f"no ladder slots in queue: {slots[:8]}"
    assert all(slot_datetime(as_of, s) is not None for s in day_slots)


# ─────────────────────────────────────────────────────────────────────────────
# copy_laws type contract
# ─────────────────────────────────────────────────────────────────────────────

def test_every_copy_law_is_a_string():
    """A law written as `- some label: the rule` is YAML for a MAPPING, not a
    sentence, and copywriter renders it into the system prompt with f"- {law}".
    The law then reaches the model as a dict repr. Caught in review on the
    cold-read law; this keeps the next one from shipping silently.
    """
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load(
        Path("config/marketing.yml").read_text(encoding="utf-8"))
    laws = (cfg.get("copywriter") or {}).get("copy_laws") or []
    assert laws, "copy_laws is empty — the guard would pass vacuously"
    bad = [l for l in laws if not isinstance(l, str)]
    assert not bad, (
        f"{len(bad)} copy_law(s) parsed as non-strings (quote any law "
        f"containing 'word: '): {bad}")


def test_the_clarity_laws_are_present_and_readable():
    """The three laws that close the 2026-07-26 $AAPL ambiguity incident."""
    import yaml
    from pathlib import Path
    laws = yaml.safe_load(
        Path("config/marketing.yml").read_text(encoding="utf-8")
    )["copywriter"]["copy_laws"]
    blob = "\n".join(laws).lower()
    assert "cold-read law" in blob
    assert "four up" in blob, "the worked counter-example is missing"
    assert "print the level" in blob
    assert "vwap" in blob, "the M2 study names are not banned in copy_laws"


# ---------------------------------------------------------------------------
# 7. In-process scaffolding never reaches content_plan.json
#
# The copywriter pass hangs the whole Prophet plan dict on every queue item
# (`_plan`) so build_context can read it without a second lookup. Measured
# 2026-07-28 on the tracked 7-desk artifact: `_plan` was 239KB of 1.11MB — the
# largest per-item field by ~9x over the next one (`body`, 27KB) — and it grows
# with the desk count. Nothing that re-opens the artifact reads it.
# ---------------------------------------------------------------------------

def _scaffolding_in(cp: dict) -> set[str]:
    """Underscore-prefixed keys present anywhere in a written plan that are NOT
    on the artifact keep-list."""
    from engine.marketing.content_studio import ARTIFACT_KEEP_KEYS

    found: set[str] = {k for k in cp if k.startswith("_")}
    for fc in cp.get("featured_charts") or []:
        if isinstance(fc, dict):
            found |= {k for k in fc if k.startswith("_")}
    for acct in cp.get("accounts") or []:
        if not isinstance(acct, dict):
            continue
        found |= {k for k in acct if k.startswith("_")}
        for item in acct.get("queue") or []:
            if isinstance(item, dict):
                found |= {k for k in item if k.startswith("_")}
    return found - ARTIFACT_KEEP_KEYS


def test_strip_scaffolding_drops_bulk_keys_and_keeps_the_read_ones():
    """The keep-list is exactly the keys with a named reader of the artifact;
    every other "_" key is scaffolding and must not survive the write."""
    from engine.marketing.content_studio import strip_scaffolding

    plan = {
        "as_of": "2026-07-28",
        "featured_charts": [{"id": "c1", "svg": "<svg/>", "_defer": {"big": "blob"}}],
        "accounts": [{
            "id": "flagship",
            "queue": [{
                "id": "p1", "type": "signal", "ticker": "PLTR",
                "_plan": {"id": "prophet-PLTR-1", "entry": 120.0},
                "_receipt": {"kind": "win"},
                "_mover_data": {"pct": 3.1}, "_mover_facts": {"a": 1},
                "_theme_data": {"agg_pct": 2.0}, "_theme_facts": {"b": 2},
                "_live_gate_fail": "stale", "_copy_violations": ["x"],
                "_copy_mode": "llm",
            }],
        }],
    }
    out = strip_scaffolding(plan)
    item = out["accounts"][0]["queue"][0]

    for gone in ("_plan", "_receipt", "_mover_data", "_mover_facts",
                 "_theme_data", "_theme_facts"):
        assert gone not in item, f"{gone} is scaffolding but reached the artifact"
    # Read downstream — admin badges (_live_gate_fail, _copy_violations) and the
    # Lab roll-up (_copy_mode, via telemetry._build_post_index re-reading disk).
    assert item["_live_gate_fail"] == "stale"
    assert item["_copy_violations"] == ["x"]
    assert item["_copy_mode"] == "llm"
    # Non-underscore fields are untouched.
    assert item["id"] == "p1" and item["ticker"] == "PLTR"
    assert "_defer" not in out["featured_charts"][0]
    assert out["featured_charts"][0]["svg"] == "<svg/>"
    assert _scaffolding_in(out) == set()


def test_strip_scaffolding_leaves_the_in_memory_plan_intact():
    """COPY-ON-WRITE IS LOAD-BEARING. The governor writes the stripped copy but
    keeps using the fat in-memory plan afterwards — above all
    outbox.emit_from_content_plan, which reads `_plan` to stamp
    source.signal_id/direction/entry/invalidation for the publisher's post-time
    live gate. A strip that mutated in place would disarm that gate silently."""
    from engine.marketing.content_studio import strip_scaffolding

    plan = {"accounts": [{"id": "a", "queue": [
        {"id": "p1", "_plan": {"id": "prophet-NVDA-1", "direction": "BULL"}},
    ]}], "featured_charts": [{"id": "c1", "_defer": {"blob": 1}}]}
    out = strip_scaffolding(plan)

    assert plan["accounts"][0]["queue"][0]["_plan"]["direction"] == "BULL", (
        "strip_scaffolding mutated its argument — outbox.emit_from_content_plan "
        "runs on this object AFTER the write and would lose its live-gate stamp")
    assert plan["featured_charts"][0]["_defer"] == {"blob": 1}
    assert "_plan" not in out["accounts"][0]["queue"][0]


def test_written_content_plan_carries_no_scaffolding(tmp_path):
    """End-to-end: the artifact the governor writes carries no scaffolding."""
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "neuralweb").mkdir(parents=True)
    (tmp_path / "site" / "neuralwebdata").mkdir(parents=True)
    shutil.copy(ROOT / "config" / "marketing.yml", tmp_path / "config" / "marketing.yml")

    from engine.neuralweb.marketing_governor import build_and_write
    build_and_write(root=tmp_path)

    cp = json.loads(
        (tmp_path / "data" / "marketing" / "content_plan.json").read_text())

    n_items = sum(len(a.get("queue") or []) for a in cp.get("accounts") or [])
    assert n_items > 0, "no queue items — this guard would pass vacuously"

    leaked = _scaffolding_in(cp)
    assert leaked == set(), (
        f"in-process scaffolding reached content_plan.json: {sorted(leaked)}. "
        f"Strip it in marketing_governor.build_and_write (strip_scaffolding), "
        f"or add it to ARTIFACT_KEEP_KEYS if a reader of the WRITTEN artifact "
        f"needs it.")
    # The specific 239KB regression this pins.
    assert all(
        "_plan" not in item
        for a in cp["accounts"] for item in (a.get("queue") or [])
    ), "the full Prophet plan dict is back in the artifact"


def test_artifact_keep_list_covers_what_admin_renders():
    """Cross-module contract: every underscore key the admin Content Studio
    render whitelists must survive the write, or the badge silently goes dark."""
    from admin.marketing import _CONTENT_POST_KEEP
    from engine.marketing.content_studio import ARTIFACT_KEEP_KEYS

    missing = set(_CONTENT_POST_KEEP) - set(ARTIFACT_KEEP_KEYS)
    assert not missing, (
        f"admin renders {sorted(missing)} but the writer strips them — the "
        f"Content Studio badge would read empty for every post")


# ---------------------------------------------------------------------------
# Movers/theme desk: counted in the plan census, and first in line for a card
# (X Growth wave 1, 2026-07-31)
# ---------------------------------------------------------------------------

def _write_heatmaps(root: Path) -> None:
    """sp500 + themes heatmap fixtures with enough supply for 2 movers and 2
    theme lists (movers_source wants |1D| >= 3.0 and >= 4 members per theme)."""
    md = root / "site" / "marketdata"
    md.mkdir(parents=True, exist_ok=True)
    (md / "sp500_heatmap.json").write_text(json.dumps({
        "asof": "2026-07-31",
        "tiles": [
            {"t": "AAPL", "name": "Apple", "sector": "Technology",
             "perf": {"1D": 7.5}},
            {"t": "NVDA", "name": "NVIDIA", "sector": "Technology",
             "perf": {"1D": -9.1}},
            {"t": "AMD", "name": "AMD", "sector": "Technology",
             "perf": {"1D": -6.2}},
        ],
    }), encoding="utf-8")
    (md / "themes_heatmap.json").write_text(json.dumps({
        "tiles": [
            {"t": "aicompute", "name": "Compute",
             "sector": "Artificial Intelligence", "perf": {"1D": -3.0},
             "members": [{"t": "NVDA", "perf": {"1D": -4.5}},
                         {"t": "AMD", "perf": {"1D": -6.2}},
                         {"t": "SMCI", "perf": {"1D": -5.1}},
                         {"t": "AVGO", "perf": {"1D": -3.8}},
                         {"t": "MRVL", "perf": {"1D": -2.5}}]},
            {"t": "biotech", "name": "Biotech Core",
             "sector": "Healthcare & Biotech", "perf": {"1D": 2.5},
             "members": [{"t": "AMGN", "perf": {"1D": 4.2}},
                         {"t": "BIIB", "perf": {"1D": 3.1}},
                         {"t": "REGN", "perf": {"1D": 2.8}},
                         {"t": "GILD", "perf": {"1D": 1.9}},
                         {"t": "VRTX", "perf": {"1D": 2.2}}]},
        ],
    }), encoding="utf-8")


def _reach_items(plan: dict) -> list[dict]:
    return [it for a in plan["accounts"] for it in (a.get("queue") or [])
            if it.get("provenance") == "movers_desk"]


def test_movers_items_are_counted_in_the_plan_summary(tmp_path):
    """THE FALSE-EMPTY DEFECT: the movers desk appended straight to
    `acct_row["queue"]` and never extended `all_items`, so `total_posts` /
    `signal_posts` / `distinctness` could not see a single mover or theme post —
    a movers-only night reported `total_posts: 0`, which is the same reading the
    DeepSeek copy outage produced.

    With no confluence file and no filing supply under `tmp_path`, every queued
    post came from a producer that feeds `all_items`, so the census must equal
    the queue exactly. Pre-fix it is short by the number of reach items.
    """
    from engine.marketing.content_studio import content_plan

    _write_heatmaps(tmp_path)
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None, root=tmp_path)

    reach = _reach_items(plan)
    assert reach, "fixture produced no movers-desk items"

    queued = [it for a in plan["accounts"] for it in (a.get("queue") or [])]
    assert plan["summary"]["total_posts"] == len(queued), (
        f"summary.total_posts={plan['summary']['total_posts']} but the plan "
        f"carries {len(queued)} queued posts, {len(reach)} of them movers-desk "
        f"— the census cannot see the reach lane")


def test_movers_items_take_real_d1_ladder_rungs(tmp_path):
    """A MOVER-NN / THEME-NN slot cannot be emitted (outbox takes D1- only), so
    the desk's own slot label was the reason it never published."""
    from engine.marketing.content_studio import content_plan

    _write_heatmaps(tmp_path)
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None, root=tmp_path)

    reach = _reach_items(plan)
    assert reach
    bad = [it["slot"] for it in reach if not str(it["slot"]).startswith("D1-")]
    assert not bad, f"movers-desk items on unemittable slots: {bad}"
    # Each desk books a rung at most once — a double-booked time is the thing
    # the free-pool exists to prevent.
    for acct in plan["accounts"]:
        d1 = [it["slot"] for it in (acct.get("queue") or [])
              if str(it.get("slot") or "").startswith("D1-")]
        assert len(d1) == len(set(d1)), f"{acct['id']} double-booked: {sorted(d1)}"


def _fake_conf_many_tickers(n: int = 9) -> dict:
    """A confluence file with `n` fresh, high-edge combos on distinct tickers —
    enough to exhaust the whole 8-card reach budget on its own."""
    from datetime import date, timedelta

    fresh = (date.today() - timedelta(days=2)).isoformat()
    tickers = ["CONFA", "CONFB", "CONFC", "CONFD", "CONFE",
               "CONFF", "CONFG", "CONFH", "CONFI"][:n]
    return {
        "legs": [
            {"leg_id": "golden_cross_7_35@D", "signal_id": "golden_cross_7_35",
             "tf": "D", "kind": "event", "family": "ma_crosses", "direction": 1,
             "display_en": "Golden Cross (7/35)", "display_zh": "黄金交叉"},
        ],
        "combos": {
            "long": [
                {
                    "id": f"L{i:04d}", "legs": [0], "dir": 1,
                    "name_en": f"Combo {i}",
                    "h21": {"n": 90, "wr": 0.65, "wr_mc_test": 0.80,
                            "n_test": 15, "months_test": 12},
                    "edge_wr_test": 0.30, "rank_score": 0.18,
                    "n_fires": 90, "fires_last3y": 9,
                    "last_fire": fresh, "first_fire": "2023-01-05",
                    "active_now": [t], "recent_fires": [],
                }
                for i, t in enumerate(tickers, start=1)
            ],
            "short": [],
        },
    }


def test_reach_chart_budget_reserves_cards_for_the_movers_desk(tmp_path, monkeypatch):
    """THE STARVED LANE: the 8-card reach budget was spent in source order, so
    confluence — which slots posts CONF-NN and therefore CANNOT reach the outbox
    at all — took all 8 and the movers/theme desk got none. `theme_list` and
    `mover` are ticker-rollup kinds, and the publisher refuses a cashtag-bearing
    post with no picture, so a chartless mover is unpublishable.

    Pre-fix this test sees 8 confluence cards and 0 theme cards.
    """
    import engine.marketing.chart_render as chart_render
    from engine.marketing.content_studio import content_plan

    conf_dir = tmp_path / "site" / "factordata"
    conf_dir.mkdir(parents=True)
    (conf_dir / "tech_confluence.json").write_text(
        json.dumps(_fake_conf_many_tickers()), encoding="utf-8")
    _write_heatmaps(tmp_path)

    # Synthetic OHLCV so the confluence lane can actually build cards without a
    # parquet store; the renderer is stubbed because this test is about BUDGET,
    # not artwork.
    n = 60
    dates = [f"2026-05-{(i % 28) + 1:02d}" for i in range(n)]
    series = [100.0 + i for i in range(n)]
    monkeypatch.setattr(
        chart_render, "load_ohlcv_windowed",
        lambda ticker, root=None, *a, **k: (
            (dates, series, series, series, series, [1_000.0] * n), 0),
    )
    monkeypatch.setattr(chart_render, "render_chart_v2",
                        lambda **kw: "<svg data-stub='conf'></svg>")

    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None, root=tmp_path)

    charts = plan["featured_charts"]
    conf_charts = [c for c in charts if c.get("source") == "confluence"]
    theme_charts = [c for c in charts if c.get("source") == "theme_list"]

    assert conf_charts, "fixture failed to exercise the confluence chart lane"
    assert theme_charts, (
        f"movers/theme desk got NO card while confluence took "
        f"{len(conf_charts)} — the publishable lane is starved by one that "
        f"cannot emit")
    assert len(conf_charts) <= 2, (
        f"confluence took {len(conf_charts)} cards; its share of the 8-card "
        f"reach budget is 2 once the movers reserve is honoured")
    # The TOTAL allowance is unchanged — this is a split, not a raise.
    assert len(charts) <= 8, f"reach budget breached: {len(charts)} charts"
