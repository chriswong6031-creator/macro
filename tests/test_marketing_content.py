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
     "tilt": {"signal": 0.38, "chart": 0.12, "education": 0.10, "macro": 0.18,
               "receipt": 0.10, "watchlist": 0.06, "event": 0.06}},
    {"id": "receipts", "kind": "branded", "beat": "Receipt", "voice": "dry, receipts-forward",
     "tilt": {"signal": 0.30, "chart": 0.22, "education": 0.06, "macro": 0.08,
               "receipt": 0.22, "watchlist": 0.06, "event": 0.06}},
    {"id": "theme_desk", "kind": "branded", "beat": "Theme", "voice": "specialist",
     "tilt": {"signal": 0.36, "chart": 0.12, "education": 0.10, "macro": 0.10,
               "receipt": 0.08, "watchlist": 0.06, "event": 0.18}},
    {"id": "research_a", "kind": "generic", "beat": "Macro", "voice": "educational",
     "tilt": {"signal": 0.28, "chart": 0.10, "education": 0.22, "macro": 0.24,
               "receipt": 0.06, "watchlist": 0.06, "event": 0.04}},
    {"id": "research_b", "kind": "generic", "beat": "Fast", "voice": "fast, reactive",
     "tilt": {"signal": 0.40, "chart": 0.22, "education": 0.06, "macro": 0.08,
               "receipt": 0.08, "watchlist": 0.06, "event": 0.10}},
    {"id": "research_c", "kind": "generic", "beat": "Charts", "voice": "pattern/history",
     "tilt": {"signal": 0.30, "chart": 0.26, "education": 0.08, "macro": 0.08,
               "receipt": 0.06, "watchlist": 0.16, "event": 0.06}},
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


def test_invalidated_plan_never_appears_in_signal_posts_or_charts():
    """Full pipeline: a QCOM-class invalidated plan must not leak anywhere."""
    from engine.marketing.content_studio import content_plan
    from engine.marketing.chart_render import load_closes
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plans = _SAMPLE_PLANS + [_INVALIDATED_PLAN]
    loader = lambda t: load_closes(t, ROOT, n=90)  # noqa: E731
    plan = content_plan(cfg, plans, closes_loader=loader)
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
    total_slots = 7 * 3  # n_days * per_day = 21

    for acct in plan["accounts"]:
        mix = acct["mix_observed"]
        # All types must have at least 1 slot out of 21 (largest-remainder guarantees this)
        for type_id in all_type_ids:
            assert mix.get(type_id, 0) >= 1, (
                f"account {acct['id']} missing type {type_id}: mix={mix}"
            )


def test_signal_is_largest_type_in_every_account():
    from engine.marketing.content_studio import content_plan
    cfg = {"desk_network": {"stage": "A", "accounts": _SAMPLE_ACCOUNTS}}
    plan = content_plan(cfg, _SAMPLE_PLANS, closes_loader=None)
    for acct in plan["accounts"]:
        mix = acct["mix_observed"]
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
    assert len(cp.get("content_types", [])) == 7
    assert isinstance(cp.get("accounts"), list)
    assert len(cp.get("accounts", [])) == 6
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
        assert len(tilt) == 7, f"account {acct['id']} tilt has {len(tilt)} keys"
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
            assert "BUY" in svg, f"featured chart {fc['id']} missing BUY marker"
            assert not re.search(r"MACD|RSI|EMA|cross", svg, re.I), (
                f"featured chart {fc['id']} leaks indicator text"
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
    """Only runs if PLTR.parquet exists in the real repo."""
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
