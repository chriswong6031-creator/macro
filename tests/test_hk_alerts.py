"""Tests for engine/hk_alerts.py — HK change-detector alerts.

Display-only; bilingual; every rule isolated; views well-formed.
"""
from __future__ import annotations

from engine import hk_alerts as al


def test_evaluate_runs_and_isolated():
    """evaluate() builds its own f/regime/latest and never raises; severity-sorted."""
    alerts = al.evaluate()
    sev = [al._SEV_ORDER.get(a.severity, 9) for a in alerts]
    assert sev == sorted(sev)
    for a in alerts:
        assert a.rule and a.severity in ("high", "warn", "info")
        assert a.message and a.message_zh          # bilingual


def test_alert_views_well_formed():
    views = al.alert_views(al.evaluate())
    for v in views:
        assert v["plain_en"] and v["plain_zh"]
        assert v["what_en"] and v["what_zh"]
        assert v["icon"]
        assert v["tier"] in ("act", "watch", "context")


def test_every_rule_has_meta_and_conviction():
    """Every rule that can fire has plain-English copy + a conviction tier + anchor."""
    rule_names = {
        "hk_regime_transition", "hk_regime_confidence_floor", "hk_growth_confidence_floor",
        "hk_inflation_confidence_floor", "hk_risk_on", "hk_risk_off", "hk_peg_weak_side",
        "hk_peg_strong_side", "hibor_spike", "southbound_surge", "southbound_exodus",
        "hk_roro_flip_on", "hk_roro_flip_off", "vhsi_spike", "fear_euphoria_extreme",
        "fear_euphoria_capitulation", "ah_premium_wide", "ah_premium_narrow",
        "hk_drawdown_elevated", "market_driver_clear", "hk_circuit_breaker",
    }
    # hk_circuit_breaker intentionally has NO anchor (the HK page has no data-health
    # panel), so it renders as plain text rather than a dead jump link.
    anchorless = {"hk_circuit_breaker"}
    for r in rule_names:
        assert r in al.ALERT_META, f"{r} missing ALERT_META"
        assert al.ALERT_META[r]["plain_zh"]        # bilingual
        assert "anchor" in al.ALERT_META[r]
        if r not in anchorless:
            assert al.ALERT_META[r]["anchor"], f"{r} should deep-link to a panel"
        # conviction may fall back to _DEFAULT_CONVICTION; the rendered view must
        # still carry a valid tier.
        v = al.alert_view(r, "info", "x", "x")
        assert v["tier"] in ("act", "watch", "context")


def test_every_anchor_resolves_to_a_panel():
    """Each non-empty alert anchor must exist as an id= in templates/hk.html.j2 so the
    'View panel ↓' jump never scrolls to a dead anchor (caught the data-health orphan)."""
    from lib import config
    tpl = (config.ROOT / "templates" / "hk.html.j2").read_text()
    for rule, meta in al.ALERT_META.items():
        anchor = meta.get("anchor")
        if anchor:
            assert f'id="{anchor}"' in tpl, f"{rule} anchor #{anchor} has no panel in hk.html.j2"


def test_log_and_dedup_idempotent(tmp_path, monkeypatch):
    """Logging the same alert twice for one day adds it once (returns stable views)."""
    import pandas as pd
    monkeypatch.setattr(al, "_log_path", lambda: tmp_path / "alerts_log.parquet")
    a = al.Alert("vhsi_spike", "warn", "test message", "测试")
    asof = pd.Timestamp("2026-06-17")
    v1 = al.log_and_dedup([a], asof)
    v2 = al.log_and_dedup([a], asof)
    assert len(v1) == len(v2) == 1
