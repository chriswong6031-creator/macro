"""Alert Command Center — the honest triage layer (engine/alert_triage.py) + the
alerts.html.j2 page render.

The page's whole value is honest triage, so these tests guard the load-bearing
properties: (1) the priority score is a transparent, bounded sum of its parts;
(2) a forex per-pair flip or a commodity intraday shock NEVER outranks credit /
recession / the BTC risk regime (true cross-asset tiering, not engine-local
severity); (3) we NEVER fabricate a hit-rate — a number appears only where
Signal Lab validated that family; and (4) the validation block always carries a
consistent key set so the template can't trip Jinja's missing-key Undefined.
"""
from __future__ import annotations

import datetime

from jinja2 import Environment, FileSystemLoader

from engine import alert_triage as at
from engine import i18n
from lib import config

TODAY = datetime.date(2026, 6, 14)


def _payload():
    return at.build_triage(today=TODAY)


# --- pure helpers -------------------------------------------------------------

def test_severity_band_is_tier_led():
    # act tier escalates; a context-tier 'high' is still minor on a macro board
    assert at.severity_band("act", "high") == "critical"
    assert at.severity_band("act", "warn") == "major"
    assert at.severity_band("watch", "high") == "major"
    assert at.severity_band("watch", "medium") == "minor"
    assert at.severity_band("context", "high") == "minor"


def test_action_reflects_conviction_and_cross_asset_disagreement():
    assert at.action_for("context", "minor", "neutral")[0] == "context"
    assert at.action_for("act", "critical", "neutral")[0] == "high-conviction"
    assert at.action_for("act", "major", "neutral")[0] == "reduce risk"
    assert at.action_for("watch", "major", "neutral")[0] == "watch"
    # cross-asset disagreement downgrades to 'confirm first' — the don't-chase rule
    assert at.action_for("act", "critical", "diverge")[0] == "confirm first"
    assert at.action_for("watch", "major", "diverge")[0] == "confirm first"


def test_cross_asset_tag_only_fires_for_unambiguous_stress():
    assert at.cross_asset_tag("hy_oas_widening", "concentrated") == "confirm"
    assert at.cross_asset_tag("hy_oas_widening", "diversified") == "diverge"
    # a non-stress family is never tagged (we refuse to guess its direction)
    assert at.cross_asset_tag("carry_flip", "concentrated") == "neutral"
    # no backdrop → neutral
    assert at.cross_asset_tag("hy_oas_widening", None) == "neutral"


def test_priority_is_a_bounded_transparent_sum():
    score, comp = at.priority("act", "critical", age_days=0, ca_tag="confirm")
    assert score == 40 + 30 + 20 + 10 == 100              # the documented ceiling
    assert comp["conviction"][0] == 40 and comp["severity"][0] == 30
    # the parts always reconstruct the score (auditable, never a black box)
    assert sum(v[0] for v in comp.values()) == score
    lo, _ = at.priority("context", "minor", age_days=99, ca_tag="diverge")
    assert 0 <= lo < score                                 # monotonic + clamped
    # diverge can subtract but never below zero
    assert at.priority("context", "minor", 99, "diverge")[0] >= 0


# --- validation honesty -------------------------------------------------------

def test_validation_always_has_a_consistent_key_set():
    # the Jinja missing-key guard: every branch returns the SAME keys
    reg = at._registry_index()
    expect = {"backtested", "verdict", "scorecard_name", "hit", "dsr", "ic", "n",
              "horizon", "extra", "report", "link", "note", "note_zh"}
    mapped = at._validation("bonds", "recession_risk", "", "", reg)
    btc = at._validation("vector", "risk_regime", "Proven edge.", "", reg)
    bare = at._validation("forex", "carry_flip", "", "", reg)
    for v in (mapped, btc, bare):
        assert expect <= set(v)


def test_only_validated_families_are_backtested_true():
    reg = at._registry_index()
    # a Signal-Lab-mapped family is backtested True with a registry verdict
    mapped = at._validation("commodity", "risk_regime", "", "", reg)
    assert mapped["backtested"] is True
    assert mapped["verdict"] in {"scored", "confirmer", "display", "killed"}
    assert mapped["scorecard_name"]
    # BTC's calibration edge is labelled 'calibrated' (a real backtest), not faked
    btc = at._validation("vector", "risk_regime", "Proven edge — both halves.", "", reg)
    assert btc["backtested"] == "engine" and btc["verdict"] == "calibrated"
    # a macro conviction NOTE is documented, NOT calibrated (honest downgrade)
    macro = at._validation("macro", "net_liquidity_roc_flip", "Medium — weakened.", "", reg)
    assert macro["backtested"] is False and macro["verdict"] == "documented"
    # an un-noted family is documented with no invented number
    bare = at._validation("forex", "carry_flip", "", "", reg)
    assert bare["backtested"] is False and bare["hit"] is None


# --- the assembled board ------------------------------------------------------

def test_payload_shape():
    p = _payload()
    for k in ("summary", "alerts", "regime", "cross_asset", "risk_backdrop",
              "events", "weights", "window_days"):
        assert k in p
    s = p["summary"]
    assert s["critical"] + s["major"] + s["minor"] == s["total"] == len(p["alerts"])


def test_alerts_are_ranked_by_priority_desc():
    al = _payload()["alerts"]
    assert al == sorted(al, key=lambda a: (a["priority"], a["ts"]), reverse=True)


def test_forex_and_commodity_never_reach_act_tier():
    # the de-flooding guarantee: a per-pair FX flip / intraday commodity shock is
    # macro context, so the loud 'act' tier stays reserved for real cross-asset stress
    for a in _payload()["alerts"]:
        if a["source"] in ("forex", "commodity"):
            assert a["tier"] in ("watch", "context")


def test_no_fabricated_hit_rate():
    # the honesty invariant: a hit-rate is shown ONLY when the family is genuinely
    # validated (backtested is True, i.e. a Signal-Lab registry row)
    for a in _payload()["alerts"]:
        v = a["validation"]
        if v["hit"] is not None:
            assert v["backtested"] is True


def test_context_tier_is_capped_per_source():
    cap = 6
    p = at.build_triage(today=TODAY, per_source_context_cap=cap)
    from collections import Counter
    c = Counter(a["source"] for a in p["alerts"] if a["tier"] == "context")
    assert all(n <= cap for n in c.values())


def test_priority_components_reconstruct_the_score():
    for a in _payload()["alerts"]:
        assert sum(v[0] for v in a["priority_components"].values()) == a["priority"]


# --- the page render ----------------------------------------------------------

def test_page_renders_without_template_errors():
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    html = env.get_template("alerts.html.j2").render(**_payload())
    assert "Alert Command Center" in html
    assert "{{" not in html and "{%" not in html          # no unrendered jinja
    assert "Undefined" not in html                        # no leaked missing keys
    # the honest framing + the transparent score must be present
    assert "documented, not" in html
    assert "Triage priority" in html
    assert "Backdrop" in html
