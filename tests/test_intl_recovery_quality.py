"""Recovery-quality and macro-authority tests for the international turn board."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.intl_recovery_quality import apply_recovery_naming, assess_recovery, macro_backdrop


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


def _rendered(**overrides):
    """A state dict as market_states() hands it out: machine enum + raw display words."""
    value = _state(
        state_en="Repairing",
        state_zh="修复中",
        stance_en="Early recovery — no rush to buy",
        stance_zh="初步回升 — 不急于买入",
        css="state-recovery",
    )
    value.update(overrides)
    return value


class TestApplyRecoveryNaming:
    """The shared view-model step — one set of words per market per day.

    Regression (2026-07-29 audit): India read "Rebound failed — Stand aside" on
    intl.html and "Repairing — no rush to buy" on macro.html from the same engine
    on the same day, because build_intl applied the qualifier in template-land and
    build_site copied state_en/stance_en RAW. The overlay now lands on the state
    dict itself, so every raw-field consumer inherits it.
    """

    def test_broken_price_evidence_overwrites_words_in_place(self):
        states = {"IN": _rendered(above_ma20=False)}

        apply_recovery_naming(states)
        st = states["IN"]

        assert st["state_en"] == "Rebound failed"
        assert st["state_zh"] == "反弹失败"
        assert st["stance_en"] == "Stand aside — repair evidence has broken"
        assert st["stance_zh"] == "观望 — 修复证据已经破坏"
        assert st["recovery_assessment"]["phase"] == "failed_rebound"
        # The machine enum and CSS class are the heat/colour authorities — untouched.
        assert st["state"] == "recovery"
        assert st["css"] == "state-recovery"

    def test_negative_momentum_also_fails_the_rebound(self):
        states = {"IN": _rendered(mom20_pct=-1.0)}

        apply_recovery_naming(states)

        assert states["IN"]["state_en"] == "Rebound failed"
        assert states["IN"]["recovery_assessment"]["phase"] == "failed_rebound"

    def test_healthy_price_without_confirmation_is_a_qualified_repair_attempt(self):
        states = {"JP": _rendered()}

        apply_recovery_naming(states)
        st = states["JP"]

        # Never the raw "Repairing": price-only repair cannot claim recovery.
        assert st["state_en"] == "Repair attempt"
        assert st["state_zh"] == "修复尝试"
        assert st["stance_en"] == "Unconfirmed — wait for breadth and external pressure to improve"
        assert st["stance_zh"] == "尚未确认 — 等待广度与外部压力改善"
        assert st["recovery_assessment"]["phase"] == "repair_attempt"

    def test_non_recovery_state_is_left_completely_untouched(self):
        states = {"AU": _rendered(state="uptrend", state_en="Uptrend", state_zh="上升趋势",
                                  stance_en="Trend intact", stance_zh="趋势完好",
                                  css="state-uptrend")}
        before = dict(states["AU"])

        apply_recovery_naming(states)

        assert states["AU"] == before
        assert "recovery_assessment" not in states["AU"]

    def test_pre_attached_assessment_is_respected_never_recomputed(self, monkeypatch):
        """HK's richer confirmation+radar assessment must survive the sweep."""
        import engine.intl_recovery_quality as MOD

        def _boom(*_a, **_kw):  # pragma: no cover — must never be reached
            raise AssertionError("assess_recovery recomputed a pre-attached assessment")

        monkeypatch.setattr(MOD, "assess_recovery", _boom)
        states = {"HK": _rendered(recovery_assessment={
            "label_en": "Fragile rebound",
            "label_zh": "脆弱反弹",
            "stance_en": "Rollover risk — wait for breadth to re-accelerate",
            "stance_zh": "再度转弱风险 — 等待广度重新加速",
        })}

        MOD.apply_recovery_naming(states)

        assert states["HK"]["state_en"] == "Fragile rebound"
        assert states["HK"]["state_zh"] == "脆弱反弹"
        assert states["HK"]["stance_en"] == "Rollover risk — wait for breadth to re-accelerate"
        assert states["HK"]["stance_zh"] == "再度转弱风险 — 等待广度重新加速"

    def test_is_idempotent(self):
        states = {"IN": _rendered(above_ma20=False)}

        apply_recovery_naming(states)
        once = dict(states["IN"])
        apply_recovery_naming(states)

        assert states["IN"] == once

    @pytest.mark.parametrize("states", [None, {}, {"X": "not-a-dict"}, {"X": None}])
    def test_junk_input_never_raises(self, states):
        apply_recovery_naming(states)


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
    # The modelled pullback odds must still arrive WITH their base rate — the honesty
    # invariant. Both moved off the tile face into the hover receipt (they printed on
    # every tile at rest, and on most tiles the two figures are equal, i.e. "no lift"),
    # so match the receipt form rather than the old always-visible line.
    assert "'% base'" in template and "_rd_b21" in template
    assert "≥5% dip in a month" in template
    # ...and the provenance of those odds travels with them
    assert "own history only — radar record still building" in template
    # the radar is still declared non-ranking on the glance tier
    assert "Risk tags are context, never a ranking" in template
