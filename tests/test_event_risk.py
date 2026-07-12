"""Tests for engine.event_risk — the non-directional event-risk banner.

Guards the honesty invariants: never directional, never a dampener, defensive on
missing data, and the fragility overlay reads the real latest.json keys.
"""
from __future__ import annotations

from datetime import date

from engine import event_risk as er


def _ev(etype, d, **kw):
    return {"type": etype, "date": d, "label": kw.get("label", etype),
            "time_et": kw.get("time_et", "14:00"), "md": kw.get("md", ""), "dow": kw.get("dow", "")}


TODAY = date(2026, 6, 15)


def test_no_events_returns_hidden():
    out = er.snapshot({}, events=[], today=TODAY)
    assert out["show"] is False


def test_picks_nearest_event_in_window():
    events = [_ev("CPI", "2026-06-20"), _ev("FOMC", "2026-06-17"), _ev("NFP", "2026-07-02")]
    out = er.snapshot({}, events=events, today=TODAY)
    assert out["show"] is True
    assert out["type"] == "FOMC"          # nearest (17th) wins
    assert out["days_to"] == 2


def test_past_events_ignored():
    events = [_ev("FOMC", "2026-06-10")]  # already past
    assert er.snapshot({}, events=events, today=TODAY)["show"] is False


def test_non_directional_invariant():
    out = er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)
    assert out["direction"] == "two-sided"
    # up-rate must be ~coin-flip, never a directional bet
    assert 0.45 <= out["up_rate"] <= 0.6
    blob = (out["headline_en"] + out["sub_en"]).lower()
    # no directional FORECAST verbs (it may say "not a sell signal" — that's allowed)
    for phrase in ("will fall", "will rise", "expect a drop", "expect a selloff", "likely to fall", "likely to rise"):
        assert phrase not in blob
    assert "two-sided" in blob and "not a sell signal" in blob


def test_vol_tier_mapping():
    assert er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)["vol_tier"] == "high"
    assert er.snapshot({}, events=[_ev("PPI", "2026-06-17")], today=TODAY)["vol_tier"] == "elevated"


def test_fragility_reads_real_keys_and_overlays():
    latest = {
        "turning_point": {"present": True},
        "cross_asset": {"absorption_pctile_5y": 0.96},
        "fed_path": {"gap": {"gap_bp": 38}},
        "conditions": {"risk_appetite": {"stock_bond_corr": 0.67}},
    }
    frag = er.fragility(latest)
    assert frag["fragile"] is True
    assert frag["score"] == 4
    out = er.snapshot(latest, events=[_ev("FOMC", "2026-06-17")], today=TODAY)
    assert out["fragility"]["fragile"] is True
    assert "FRAGILE" in out["headline_en"]
    assert len(out["fragility"]["reasons"]) == 4


def test_not_fragile_when_calm():
    latest = {"turning_point": {"present": False}, "cross_asset": {"absorption_pctile_5y": 0.4},
              "fed_path": {"gap": {"gap_bp": 5}}}
    frag = er.fragility(latest)
    assert frag["fragile"] is False
    assert frag["score"] == 0


def test_defensive_on_missing_or_none():
    assert er.snapshot(None, events=[], today=TODAY)["show"] is False
    # malformed event dicts must not crash
    out = er.snapshot({}, events=[{"type": "FOMC"}, {"date": "not-a-date"}], today=TODAY)
    assert out["show"] is False
    # fragility on empty dict is safe
    assert er.fragility({})["fragile"] is False


def test_is_context_only_always():
    assert er.snapshot({}, events=[], today=TODAY)["is_context_only"] is True
    assert er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)["is_context_only"] is True


# ---- scorecard + alert (fast-follow) ----

def test_as_alert_shape_and_nondirectional():
    snap = er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)
    a = er.as_alert(snap)
    assert set(a) == {"rule", "severity", "message", "message_zh"}
    assert a["rule"] == "event_risk" and a["severity"] == "warn"
    assert "not a sell signal" in a["message"].lower()
    assert er.as_alert({"show": False}) is None


def test_append_log_only_on_event_day_and_idempotent(tmp_path):
    p = tmp_path / "log.jsonl"
    far = er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=TODAY)  # days_to=2
    assert er.append_log(far, path=p) is False                              # not event day
    day = er.snapshot({}, events=[_ev("FOMC", "2026-06-17")], today=date(2026, 6, 17))
    assert day["days_to"] == 0
    assert er.append_log(day, path=p) is True
    assert er.append_log(day, path=p) is False                             # idempotent
    assert er.track_record(path=p) == {"n": 0}                             # unresolved yet


def test_resolve_and_track_record(tmp_path):
    p = tmp_path / "log.jsonl"
    day = er.snapshot({"turning_point": {"present": True}, "cross_asset": {"absorption_pctile_5y": 0.96},
                       "fed_path": {"gap": {"gap_bp": 38}}},
                      events=[_ev("FOMC", "2026-06-17")], today=date(2026, 6, 17))
    er.append_log(day, path=p)
    closes = {"2026-06-16": 100.0, "2026-06-17": 101.5}   # +1.5% on the event day
    assert er.resolve(closes, path=p) == 1
    assert er.resolve(closes, path=p) == 0                # already resolved
    tr = er.track_record(path=p)
    assert tr["n"] == 1 and tr["avg_abs"] == 1.5 and tr["up_rate"] == 1.0
    assert tr["n_fragile"] == 1 and tr["avg_abs_fragile"] == 1.5


# --------------------------------------------------------------------------- #
# bilingual parity (docs/DESIGN_DOCTRINE.md) — label_zh / md_zh passthrough
# --------------------------------------------------------------------------- #
def test_label_zh_passthrough_and_zh_headline():
    ev = _ev("FOMC", "2026-06-17", label="FOMC rate decision")
    ev["label_zh"] = "美联储议息会议"
    ev["md_zh"] = "6月17日"
    out = er.snapshot({}, events=[ev], today=TODAY)
    assert out["label_zh"] == "美联储议息会议"
    assert out["md_zh"] == "6月17日"
    assert "美联储议息会议" in out["headline_zh"]
    assert "FOMC rate decision" not in out["headline_zh"]
    a = er.as_alert(out)
    assert "美联储议息会议" in a["message_zh"]
    assert "FOMC rate decision" not in a["message_zh"]


def test_label_zh_falls_back_to_en_label():
    """Old event dicts without label_zh (stale artifacts) degrade to the EN label."""
    out = er.snapshot({}, events=[_ev("FOMC", "2026-06-17", label="FOMC decision")],
                      today=TODAY)
    assert out["label_zh"] == "FOMC decision"
    assert er.as_alert(out) is not None
