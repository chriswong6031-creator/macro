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


def test_rule_scorecard_wiring_three_honest_outcomes():
    # synthetic rule scorecard standing in for data/alerts/rule_scorecard.json
    rsc = {
        "ebp_widening": {"label": "EBP spike", "verdict": "earned",
                         "headline_horizon": "60", "earned_horizons": ["20", "60"],
                         "n_events": 12,
                         "horizons": {"20": {"hit": 0.67, "base_hit": 0.35},
                                      "60": {"hit": 0.50, "base_hit": 0.28}}},
        "hy_oas_widening": {"label": "HY OAS spike", "verdict": "no_edge",
                            "n_events": 168, "horizons": {}},
        "sahm_trigger": {"label": "Sahm", "verdict": "underpowered",
                         "n_events": 4, "horizons": {}},
    }
    reg = at._registry_index()
    earned = at._validation("macro", "ebp_widening", "", "", reg, rsc, "spike")
    assert earned["backtested"] is True and earned["verdict"] == "backtested"
    assert earned["hit"] == 0.50 and earned["horizon"] == "60d"   # headline horizon
    no_edge = at._validation("macro", "hy_oas_widening", "", "", reg, rsc, "widening")
    assert no_edge["verdict"] == "no_edge" and no_edge["hit"] is None
    under = at._validation("macro", "sahm_trigger", "", "", reg, rsc, "")
    assert under["verdict"] == "underpowered" and under["backtested"] is False
    # the rule's own backtest takes precedence over the signal_lab map / engine edge
    assert earned["report"] == "alert-rules-phase0"


def test_net_liquidity_rule_key_is_direction_aware():
    assert at._rule_key("macro", "net_liquidity_roc_flip", "flipped positive (expanding)") == "net_liq_expand"
    assert at._rule_key("macro", "net_liquidity_roc_flip", "negative (contracting)") == "net_liq_contract"
    assert at._rule_key("macro", "hy_oas_widening", "") == "hy_oas_widening"
    assert at._rule_key("forex", "carry_flip", "") is None


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


# --- v2 modeling: persistence, lifecycle, corroboration cap, storylines -------

def test_corroboration_cap_is_demote_only():
    # Article-2 clean: the cap may only ever LOWER a band, never raise it.  An
    # uncorroborated major drops to minor; a corroborated one is untouched.
    reg = at._registry_index()
    doc = at._validation("altdata", "convergence", "", "", reg)   # documented, not backtested
    # isolated one-off, no cross-asset confirm, not persisting → demoted
    band, why = at.corroborated_severity("major", "watch", "neutral", doc, fire_count=1, streak_days=0)
    assert band == "minor" and why == "uncorroborated"
    # a persisting flag keeps its band (persistence corroborates)
    band, why = at.corroborated_severity("major", "watch", "neutral", doc, fire_count=5, streak_days=6)
    assert band == "major" and why is None
    # cross-asset confirm corroborates → band untouched (even as a one-off)
    band, why = at.corroborated_severity("critical", "watch", "confirm", doc, 1, 0)
    assert band == "critical" and why is None
    # an uncorroborated critical steps down exactly one notch (→ major), never further
    band, why = at.corroborated_severity("critical", "watch", "neutral", doc, 1, 0)
    assert band == "major" and why == "uncorroborated"
    # a backtested family keeps its band even as a one-off
    bt = {"backtested": True}
    band, why = at.corroborated_severity("major", "watch", "neutral", bt, 1, 0)
    assert band == "major" and why is None
    # act-tier is inherently corroborated; minor is a no-op floor
    assert at.corroborated_severity("major", "act", "neutral", doc, 1, 0)[0] == "major"
    assert at.corroborated_severity("minor", "context", "neutral", doc, 1, 0) == ("minor", None)


def test_persistence_recovers_the_fire_pattern():
    inst = [{"ts": "2026-06-01T00:00:00"}, {"ts": "2026-06-05T00:00:00"},
            {"ts": "2026-06-03T00:00:00"}]
    p = at._persistence(inst)
    assert p["fire_count"] == 3
    assert p["first_ts"].startswith("2026-06-01") and p["last_ts"].startswith("2026-06-05")
    assert p["streak_days"] == 4


def test_lifecycle_stages_are_descriptive():
    # persisting = re-fired across days AND still fresh; fading = same history, gone quiet
    assert at.lifecycle_of(fire_count=5, streak_days=6, age_days=0) == "persisting"
    assert at.lifecycle_of(fire_count=5, streak_days=6, age_days=9) == "fading"
    assert at.lifecycle_of(fire_count=1, streak_days=0, age_days=0) == "new"
    assert at.lifecycle_of(fire_count=1, streak_days=0, age_days=9) == "aging"


def test_clustering_maps_related_alerts_together():
    assert at.cluster_of("bonds", "credit_band") == "stress"
    assert at.cluster_of("macro", "transition_state_change") == "regime"
    assert at.cluster_of("altdata", "convergence") == "single_name"
    assert at.cluster_of("themes", "theme_deteriorating") == "rotation"
    assert at.cluster_of("nope", "nope") == "other"


def test_board_read_is_bounded_and_descriptive():
    p = _payload()
    br = p["board_read"]
    assert 0 <= br["score"] <= 100
    assert br["stance"] in ("risk-off", "mixed", "constructive")
    assert br["one_liner"] and br["one_liner_zh"]


def test_new_payload_keys_and_alert_fields_present():
    p = _payload()
    for k in ("board_read", "volume", "storylines"):
        assert k in p
    for a in p["alerts"]:
        for k in ("cluster", "lifecycle", "fire_count", "streak_days", "first_ts", "last_ts"):
            assert k in a
        assert a["fire_count"] >= 1
        assert a["lifecycle"] in ("new", "persisting", "fading", "aging")


def test_storylines_do_not_reorder_the_feed():
    # storylines are a grouping VIEW; the alerts array stays priority-sorted, and
    # every storyline's count reconciles with the feed's cluster membership.
    p = _payload()
    from collections import Counter
    feed_by_cluster = Counter(a["cluster"] for a in p["alerts"])
    for st in p["storylines"]:
        assert st["count"] == feed_by_cluster[st["cluster"]]
    assert sum(st["count"] for st in p["storylines"]) == len(p["alerts"])


def test_severity_is_no_longer_a_monotone_wall():
    # the whole point of the v2 corroboration cap: the board must show a real triage
    # gradient, not 60 identical 'major' rows.  At least two distinct bands appear.
    p = _payload()
    bands = {a["severity"] for a in p["alerts"]}
    assert len(bands) >= 2


def test_volume_context_states_and_empty():
    import pandas as pd
    today = pd.Timestamp("2026-06-14")
    # empty input → {} (template guards on volume.state)
    assert at._volume_context([], today, 30) == {}
    # busier: last-7d fires far above the trailing weekly rate
    busy = ([{"ts": (today - pd.Timedelta(days=1)).isoformat()}] * 40
            + [{"ts": (today - pd.Timedelta(days=20)).isoformat()}] * 4)
    v = at._volume_context(busy, today, 30)
    assert v["state"] == "busier" and v["ratio"] >= 1.25 and v["last_7d"] == 40
    # quieter: last week almost silent vs a busy earlier stretch
    quiet = ([{"ts": (today - pd.Timedelta(days=25)).isoformat()}] * 60
             + [{"ts": (today - pd.Timedelta(days=2)).isoformat()}] * 2)
    q = at._volume_context(quiet, today, 30)
    assert q["state"] == "quieter" and q["ratio"] <= 0.75
    # normal: last-7d roughly equal to the weekly baseline
    norm = [{"ts": (today - pd.Timedelta(days=d)).isoformat()} for d in range(0, 28)]
    n = at._volume_context(norm, today, 28)
    assert n["state"] == "normal" and 0.75 < n["ratio"] < 1.25


def test_enum_zh_maps_closed_sets_and_falls_back():
    assert at.enum_zh("ca", "converging") == "趋同"      # the bug the review caught
    assert at.enum_zh("ca", "unknown") == "未知"
    assert at.enum_zh("band", "elevated") == "偏高"
    assert at.enum_zh("nfci", "loose") == "宽松"
    assert at.enum_zh("quad", "Goldilocks") == "金发经济"
    assert at.enum_zh("ca", "some_new_state") == "some_new_state"  # degrade, never crash
    assert at.enum_zh("band", None) is None


def test_board_read_zh_matches_en_verdict(monkeypatch):
    # regression for the ZH 'converging/unknown → 分散' mislabel: the ZH label must
    # track the true verdict, never silently collapse to 'diversified'.
    import engine.alert_triage as m
    for verdict, zh in [("converging", "趋同"), ("unknown", "未知"), ("diversified", "分散")]:
        ctx = {"cross_asset": {"verdict": verdict}, "risk_backdrop": {}}
        br = m._board_read([], ctx)
        assert zh in br["one_liner_zh"], f"{verdict} should render {zh}"
        assert verdict in br["one_liner"]


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
