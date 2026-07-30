"""Recovery-quality and macro-authority tests for the international turn board."""
from __future__ import annotations

from pathlib import Path

from engine.intl_recovery_quality import assess_recovery, macro_backdrop


def _state(**overrides):
    value = {
        "state": "recovery",
        "above_ma20": True,
        "macd_state": "bull",
        "mom20_pct": 8.2,
    }
    value.update(overrides)
    return value


def _confirmation(*, direction="broad_rebound_fading", positive=2, median=-1.1):
    return {
        "direction": direction,
        "windows": {
            "5d": {
                "available": 4,
                "positive": positive,
                "breadth_pct": positive / 4 * 100,
                "median_return_pct": median,
            }
        },
    }


def _radar(*, state="risk-off", phase="rising"):
    return {
        "state": state,
        "dominant_label_en": "US rate shock",
        "dominant_label_zh": "美国利率冲击",
        "trajectory": {"phase": phase},
    }


def test_fading_breadth_plus_hot_external_risk_is_rollover_not_recovery():
    out = assess_recovery(_state(), _confirmation(), _radar())

    assert out["phase"] == "rollover_risk"
    assert out["label_en"] == "Fragile rebound"
    assert "possible failed breakout" in out["read_en"]
    assert out["evidence"]["breadth_fading"] is True
    assert out["evidence"]["external_hot"] is True


def test_recovery_confirmation_requires_broad_followthrough_and_calm_external_risk():
    out = assess_recovery(
        _state(),
        _confirmation(direction="broad_rebound", positive=4, median=2.4),
        _radar(state="watch", phase="falling"),
    )

    assert out["phase"] == "recovery_confirmed"
    assert out["label_en"] == "Recovery gaining traction"


def test_price_repair_without_confirmation_stays_a_repair_attempt():
    out = assess_recovery(_state(), {}, _radar())

    assert out["phase"] == "repair_attempt"
    assert out["label_en"] == "Repair attempt"


def test_broken_price_evidence_marks_failed_rebound():
    out = assess_recovery(
        _state(above_ma20=False),
        _confirmation(direction="broad_rebound", positive=4, median=2.4),
        _radar(state="watch", phase="falling"),
    )

    assert out["phase"] == "failed_rebound"
    assert out["label_en"] == "Rebound failed"


def test_non_recovery_state_is_not_relabelled():
    assert assess_recovery(_state(state="uptrend"), _confirmation(), _radar()) == {}


def test_macro_backdrop_is_visible_but_never_scores_geopolitics_or_midterm():
    payload = {
        "asof": "2026-07-24",
        "board": {
            "rate_path_row": {
                "policy_rate": 3.63,
                "implied_bp_12m": 57,
                "headline_en": "Market prices about two hikes.",
                "headline_zh": "市场定价约两次加息。",
            },
            "policy_row": {
                "intel_staleness_days": 13,
                "iran_context": {"unsigned_display": True},
            },
        },
    }

    out = macro_backdrop(payload, as_of="2026-07-24")

    assert out["display_only"] is True
    assert [item["key"] for item in out["items"]] == ["rates", "iran_oil", "midterm"]
    assert all(item["scored"] is False for item in out["items"])
    assert "not scored for HK" in out["summary_en"]
    assert out["items"][1]["stale_days"] == 13


def test_macro_backdrop_read_makes_no_unearned_validated_claim():
    """The backdrop read must not call the HK rate/FX leg 'validated' (BC-2).

    Regression: the shipped copy said "Validated HK rate/FX pressure lives in the pullback
    radar". It reached site/intl.html on the 2026-07-27 nightly render and red-lined
    check_validated_claims on main, i.e. ci-pack-0 on every open PR. The claim is not
    earned: engine.risk_radar_intl.HK_PROFILE deliberately makes a WEAKER claim than the CN
    profile — CN's caveat says "Validated but modest", HK's says "Lighter than the China
    read and recent-era only ... Context, not a forecast" — HK leans on the external
    rateshock/usd legs with no deep breadth history, and no artifact carries
    validated:true for it. So there is nothing for an allowlist entry to cite.

    Asserted through the real gate, not a substring match, so negation/allowlist semantics
    stay in one place — and asserted on the ENGINE's own strings so a re-escalation fails
    here, at the source, rather than a render later on a page far from the edit.
    """
    from scripts import check_validated_claims as GATE

    payload = {
        "asof": "2026-07-24",
        "board": {
            "rate_path_row": {"policy_rate": 3.63, "implied_bp_12m": 57},
            "policy_row": {"intel_staleness_days": 13,
                           "iran_context": {"unsigned_display": True}},
        },
    }
    out = macro_backdrop(payload, as_of="2026-07-24")
    allow = GATE._load_allowlist()

    surfs = GATE._surfaces_of("engine/intl_recovery_quality.py")
    for field in ("read_en", "read_zh", "summary_en", "summary_zh"):
        for line in str(out.get(field) or "").splitlines():
            _, hits = GATE._scan_line(line, allow, surfs)
            assert not [h for h in hits if not h[0]], (
                f"{field} makes an unearned 'validated' claim: {line!r}. "
                "The HK rate/FX leg is measured context, not a validated edge — "
                "de-escalate the wording; do not add an allowlist entry (it takes "
                "citations, and there is no HK rate/FX study to cite)."
            )

    # EN and zh must de-escalate together. This assertion predates the gate covering 经验证:
    # when #3790 de-escalated the EN, the zh said 经验证, which TOKEN did not match, so the
    # zh could over-claim invisibly. TOKEN covers it since 2026-07-29 (so the loop above
    # would now catch a re-escalation too) — the explicit check stays as the cheaper,
    # closer-to-the-copy sentinel.
    assert "实测" in out["read_zh"] and "经验证" not in out["read_zh"]


def test_builder_and_template_wire_hk_radar_and_quality_without_ranking_it():
    root = Path(__file__).resolve().parents[1]
    builder = (root / "scripts" / "build_intl.py").read_text(encoding="utf-8")
    template = (root / "templates" / "intl.html.j2").read_text(encoding="utf-8")

    assert "_wr_rri.snapshot(_wr_rri.HK_PROFILE)" in builder
    assert '_st.get("risk_radar") or _radar_by_cc.get(_cc3)' in builder
    assert "recovery_assessment" in builder
    assert "recovery_assessment" in template
    assert "vs ~{{ (_rd_b21*100)|round|int }}% base" in template
    assert "never rank or exclude markets" in template
