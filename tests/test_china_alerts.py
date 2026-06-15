"""Tests for engine/china_alerts.py — the China-native fired-alerts clone.

Covers: dedup idempotency, change-detector behaviour (fires on a synthetic cross,
not on a flat level), missing-data / unknown-rule safety, the DISPLAY-ONLY
invariant (china_alerts must not be imported by the scored China engines), and
bilingual fields on every fired view.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import china_alerts as ca
from engine.china_alerts import Alert


# --------------------------------------------------------------------------- #
# dedup idempotency
# --------------------------------------------------------------------------- #
def test_log_and_dedup_is_idempotent(tmp_path, monkeypatch):
    """Running the same alerts twice on the same day must not duplicate the log,
    and must return a stable set of views."""
    log = tmp_path / "china_alerts" / "alerts_log.parquet"
    monkeypatch.setattr(ca, "_log_path", lambda: log)
    asof = pd.Timestamp("2026-06-15")
    alerts = [Alert("pboc_rrr_cut", "info", "RRR cut -0.50pp", "降准 -0.50pp"),
              Alert("qvix_spike", "warn", "QVIX jumped +20%", "QVIX 跳升 +20%")]

    first = ca.log_and_dedup(alerts, asof)
    assert len(first) == 2
    df1 = pd.read_parquet(log)
    assert len(df1) == 2

    second = ca.log_and_dedup(alerts, asof)          # same day, same alerts
    df2 = pd.read_parquet(log)
    assert len(df2) == 2, "re-running the same day must not append duplicates"
    assert len(second) == 2, "today's view set is stable across same-day runs"
    assert {v["rule"] for v in first} == {v["rule"] for v in second}


def test_log_and_dedup_appends_new_rule_same_day(tmp_path, monkeypatch):
    """A genuinely new alert later the same day is appended (and surfaced)."""
    log = tmp_path / "china_alerts" / "alerts_log.parquet"
    monkeypatch.setattr(ca, "_log_path", lambda: log)
    asof = pd.Timestamp("2026-06-15")
    ca.log_and_dedup([Alert("qvix_spike", "warn", "QVIX jumped", "QVIX 跳升")], asof)
    views = ca.log_and_dedup([Alert("margin_froth_high", "high", "Froth high", "拥挤")], asof)
    rules = {v["rule"] for v in views}
    assert rules == {"qvix_spike", "margin_froth_high"}
    assert len(pd.read_parquet(log)) == 2


# --------------------------------------------------------------------------- #
# change detector: fires on a cross, NOT on a flat (already-high) level
# --------------------------------------------------------------------------- #
def test_ppi_rule_fires_on_downcross_not_flat_level():
    """ppi_deflation_deepen must fire when PPI YoY crosses below -2.0, and must
    NOT fire when it has been sitting below -2.0 for a while (level-only)."""
    idx = pd.bdate_range("2025-01-01", periods=10)

    crossing = pd.DataFrame({"ppi_yoy": [-1.0] * 9 + [-2.5]}, index=idx)
    a = ca.ppi_deflation_deepen(crossing, None, {})
    assert a is not None and a.rule == "ppi_deflation_deepen"
    assert a.message and a.message_zh

    flat_low = pd.DataFrame({"ppi_yoy": [-3.0] * 10}, index=idx)
    assert ca.ppi_deflation_deepen(flat_low, None, {}) is None, \
        "a flat (already-deflationary) level must NOT re-fire"

    flat_ok = pd.DataFrame({"ppi_yoy": [1.0] * 10}, index=idx)
    assert ca.ppi_deflation_deepen(flat_ok, None, {}) is None


def test_regime_transition_fires_only_when_pending_builds():
    """china_regime_transition fires on a pending quad that has held >= 3 days,
    not on a flat (no-pending) state."""
    assert ca.china_regime_transition(None, None,
                                      {"pending_quad": "Q2", "pending_days": 4}) is not None
    # too fresh (< 3 days) -> no fire
    assert ca.china_regime_transition(None, None,
                                      {"pending_quad": "Q2", "pending_days": 1}) is None
    # no pending at all -> no fire
    assert ca.china_regime_transition(None, None,
                                      {"pending_quad": None, "pending_days": 0}) is None


def test_fear_euphoria_extreme_bands():
    assert ca.fear_euphoria_extreme(None, None,
        {"fear_euphoria": {"fe_score": 92, "band": "Euphoria", "band_zh": "欣喜"}}).severity == "warn"
    assert ca.fear_euphoria_extreme(None, None,
        {"fear_euphoria": {"fe_score": 8, "band": "Panic", "band_zh": "恐慌"}}).severity == "info"
    # mid-band -> no fire
    assert ca.fear_euphoria_extreme(None, None,
        {"fear_euphoria": {"fe_score": 50, "band": "Neutral", "band_zh": "中性"}}) is None


def test_market_driver_clear_requires_clear_and_high():
    fire = {"market_drivers": {"verdict": "clear", "confidence": "high",
                               "primary_label": "Yuan shock", "primary_label_zh": "人民币冲击"}}
    assert ca.market_driver_clear(None, None, fire) is not None
    # mixed verdict -> no fire
    assert ca.market_driver_clear(None, None,
        {"market_drivers": {"verdict": "mixed", "confidence": "high"}}) is None
    # clear but low confidence -> no fire
    assert ca.market_driver_clear(None, None,
        {"market_drivers": {"verdict": "clear", "confidence": "low"}}) is None


# --------------------------------------------------------------------------- #
# missing-data / unknown-rule safety: returns [] / None, never raises
# --------------------------------------------------------------------------- #
def test_rules_safe_on_empty_inputs():
    empty = pd.DataFrame()
    for rule in ca._SINGLE_RULES:
        assert rule(empty, None, {}) is None or isinstance(rule(empty, None, {}), Alert)
    for rule in ca._MULTI_RULES:
        assert isinstance(rule(empty, None, {}), list)


def test_evaluate_never_raises_on_garbage():
    """A garbage latest / None frame must degrade to a list, never raise."""
    out = ca.evaluate(f=pd.DataFrame(), regime=None, latest={"junk": True})
    assert isinstance(out, list)


def test_unknown_rule_falls_back_to_defaults():
    v = ca.alert_view("not_a_real_rule", "info", "hi", "你好")
    assert v["plain_en"] == ca._DEFAULT_META["plain_en"]
    assert v["tier"] == ca._DEFAULT_CONVICTION["tier"]
    assert v["icon"] and v["anchor"] == ""


# --------------------------------------------------------------------------- #
# alert_views output shape + bilingual fields
# --------------------------------------------------------------------------- #
def test_alert_views_shape_and_bilingual():
    views = ca.alert_views([Alert("pboc_rrr_cut", "info", "RRR cut", "降准")])
    assert len(views) == 1
    v = views[0]
    required = {"rule", "severity", "message", "message_zh", "icon", "plain_en",
                "plain_zh", "what_en", "what_zh", "anchor", "tier",
                "edge_en", "edge_zh"}
    assert required.issubset(v.keys()), f"missing keys: {required - set(v.keys())}"
    # bilingual: EN + ZH both present and non-empty for the headline + explainer
    assert v["plain_en"] and v["plain_zh"]
    assert v["what_en"] and v["what_zh"]


def test_every_meta_entry_is_bilingual():
    """Every ALERT_META + ALERT_CONVICTION entry must carry EN and ZH copy."""
    for rule, meta in ca.ALERT_META.items():
        for k in ("plain_en", "plain_zh", "what_en", "what_zh"):
            assert meta.get(k), f"{rule} META missing {k}"
    for rule, conv in ca.ALERT_CONVICTION.items():
        assert conv.get("edge_en") and conv.get("edge_zh"), f"{rule} conviction not bilingual"


def test_dataclass_messages_bilingual_on_real_rules():
    """Spot-check a few rules return both message + message_zh when they fire."""
    a = ca.china_regime_transition(None, None, {"pending_quad": "Q1", "pending_days": 5})
    assert a.message and a.message_zh
    b = ca.fear_euphoria_extreme(None, None,
        {"fear_euphoria": {"fe_score": 95, "band": "Euphoria", "band_zh": "欣喜"}})
    assert b.message and b.message_zh


# --------------------------------------------------------------------------- #
# DISPLAY-ONLY invariant: china_alerts must not feed the scored China engines
# --------------------------------------------------------------------------- #
def test_display_only_not_imported_by_scored_engines():
    """Alerts are surfaced notifications, never scored inputs — assert the scored
    China engines never import china_alerts."""
    eng = Path(__file__).resolve().parent.parent / "engine"
    for fname in ("china_axes.py", "china_regime.py", "china_playbook.py"):
        src = (eng / fname).read_text()
        assert "china_alerts" not in src, \
            f"{fname} imports china_alerts — breaks the DISPLAY-ONLY invariant"
        # belt-and-suspenders: no `import ... alerts` form either
        assert not re.search(r"import\s+.*\bchina_alerts\b", src), \
            f"{fname} imports china_alerts (regex) — DISPLAY-ONLY invariant violated"


def test_circuit_breaker_only_flags_china_sources(monkeypatch):
    """The breaker rule must mirror the US rule but scope to china_* sources only."""
    from collectors.base import CIRCUIT_BREAKER_FAILS
    fake = {"yahoo": CIRCUIT_BREAKER_FAILS,          # US source -> ignored
            "china_qvix": CIRCUIT_BREAKER_FAILS,     # china dead -> fires
            "china_macro": CIRCUIT_BREAKER_FAILS - 1}  # below threshold -> no fire
    monkeypatch.setattr(ca.store, "read_status", lambda: {"circuit_breaker": fake})
    out = ca.china_circuit_breaker(None, None, {})
    assert [a.rule for a in out] == ["china_circuit_breaker"]
    assert "china_qvix" in out[0].message and out[0].severity == "high"
