"""scripts/build_rr_banner.py tests — the Risk-Radar EXTREME alert tape.

Covers the trigger discipline (only the GATED risk-off state fires; an ungated
risk-off that the context gate capped at caution must stay silent), the payload
shape (headline / projected fall / odds / plain-English reasons / co-firing
amplifiers), and degrade-silent writes.

Run: python -m pytest tests/test_rr_banner.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_rr_banner as rb  # noqa: E402


def _radar(state, *, ungated=None, top_score=92.0, extra_hot=0):
    """A minimal risk_radar.v2-shaped snapshot with a growth-scare dominant leg."""
    scares = [
        {"scare": "growth", "tier": "A", "band": "risk-off", "score": top_score,
         "label_en": "Growth scare / defensive rotation",
         "label_zh": "增长恐慌/防御轮动",
         "firing_legs": [
             {"leg": "growth_defensives", "pctile": 0.90, "confirmed": True},
             {"leg": "growth_cyc_def", "pctile": 0.78, "confirmed": False},
         ]},
        {"scare": "global", "tier": "B", "band": "caution", "score": 69.0,
         "label_en": "Global breadth breakdown", "label_zh": "全球广度破位",
         "firing_legs": []},
        {"scare": "credit", "tier": "A", "band": "watch", "score": 55.0,
         "label_en": "Credit stress", "label_zh": "信用压力", "firing_legs": []},
    ]
    # optionally promote co-firing scares into the elevated/risk-off band
    for i in range(1, 1 + extra_hot):
        scares[i]["band"] = "elevated"
        scares[i]["score"] = 80.0 - i
    return {
        "schema": "risk_radar.v2", "asof": "2026-07-02",
        "state": state, "state_ungated": ungated or state,
        "top_score": top_score,
        "dominant_scare": "growth",
        "dominant_label_en": "Growth scare / defensive rotation",
        "dominant_label_zh": "增长恐慌/防御轮动",
        "scares": scares,
        "drawdown_prob": {"h5": 0.18, "h10": 0.27, "h21": 0.41,
                          "base_h21": 0.178, "lift_h21": 2.3, "conjunction_n": 3},
    }


def test_below_threshold_returns_none() -> None:
    for state in ("calm", "watch", "caution", "elevated"):
        assert rb.build_alert(_radar(state)) is None, state


def test_ungated_riskoff_does_not_fire() -> None:
    """The get-out banner keys off the GATED state. A raw risk-off score that the
    context gate capped at caution (SPY not yet < 200-day) must stay silent —
    exactly the live 2026-07-02 reading the user described as 'not at that point'."""
    assert rb.build_alert(_radar("caution", ungated="risk-off")) is None


def test_riskoff_builds_full_payload() -> None:
    a = rb.build_alert(_radar("risk-off", top_score=92.0, extra_hot=2))
    assert a is not None
    # get-out framing + score
    assert a["headline_en"].startswith("EXTREME RISK-OFF")
    assert a["score"] == 92
    assert a["href"] == "macro.html"
    # odds mirror the card (>=5% pullback within 21d, lift vs normal, escalating ramp)
    assert a["odds_pct"] == 41
    assert a["lift"] == 2.3
    assert a["base_pct"] == 18
    assert [r["pct"] for r in a["ramp"]] == [18, 27, 41]
    # reasons = dominant firing legs, mapped to plain English (not raw codes)
    names = [r["en"] for r in a["reasons"]]
    assert "Defensives outperforming" in names
    assert a["reasons"][0]["pctile"] == 90 and a["reasons"][0]["confirmed"] is True
    # amplifiers = OTHER scares now firing hot (co-firing), not the dominant one
    amp_names = [m["en"] for m in a["amplifiers"]]
    assert "Growth scare / defensive rotation" not in amp_names
    assert "Global breadth breakdown" in amp_names
    assert a["conjunction_n"] == 3
    # dismissal signature ties to state + day so it re-opens on change
    assert a["id"] == "rr-2026-07-02-risk-off"


def test_unknown_leg_code_falls_back_to_raw() -> None:
    r = _radar("risk-off")
    r["scares"][0]["firing_legs"] = [{"leg": "made_up_leg", "pctile": 0.5}]
    a = rb.build_alert(r)
    assert a["reasons"][0]["en"] == "made_up_leg"  # no crash, echoes the code


def test_build_writes_inert_and_never_raises() -> None:
    """build() degrades silent: with no readable snapshot it still writes a valid
    inert payload (alert:null) so a stale extreme banner can never linger."""
    with tempfile.TemporaryDirectory() as d:
        # point at a data dir with no regime/latest.json → inert, no exception
        import lib.config as cfg
        orig = cfg.data_dir
        cfg.data_dir = lambda: Path(d)  # type: ignore
        try:
            out = rb.build(Path(d) / "site")
        finally:
            cfg.data_dir = orig  # type: ignore
        payload = json.loads(out.read_text())
        assert payload["schema"] == "rr_banner.v1"
        assert payload["alert"] is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
