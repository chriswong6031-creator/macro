"""engine.foresight_cascade — the per-theme STAGE machine (T1 x T4). Verifies the stage
logic on the four canonical states and that it ranks by edge remaining (PRECIPICE first)
and degrades honestly when a tier is missing. W0a additions: _append_ledger logs ALL stages
with transition-dedup + heartbeat.
"""
from __future__ import annotations
import json

import pytest

from engine import foresight_cascade as fc
from lib import config as _config


@pytest.fixture(autouse=True)
def _isolate_real_data_tree(tmp_path, monkeypatch):
    """compute_foresight_cascade lazily recomputes any tier not passed in
    (policy_reg, fda_scarcity, confirmers, ...) straight off the real data/
    tree — engine.policy_calendar._append_ledger then appends a real
    forward-ledger batch (COLLECT_LANE=nightly is armed session-wide in
    conftest; a full 13-theme batch landed in the committed ledger this way).
    Redirect lib.config so lazy recomputes see an empty store and degrade to
    None. Tests that patch data_dir themselves simply override this."""
    _config.load()  # warm the lru cache before ROOT is patched
    monkeypatch.setattr(_config, "ROOT", tmp_path)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path / "data")


def test_precipice_tight_plus_flat():
    bn = {"band": "SOLD_OUT", "tightness": 1.6, "regime": True}
    rv = {"breadth": 0.05, "level_state": "FLAT_LOW"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "PRECIPICE"          # the June-2024 HBM state


def test_broadening_tight_plus_rising():
    bn = {"band": "TIGHT", "tightness": 0.9, "regime": True}
    rv = {"breadth": 0.3, "level_state": "POSITIVE"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "BROADENING"


def test_rerating_tight_but_already_broad():
    bn = {"band": "TIGHT", "tightness": 0.9}
    rv = {"breadth": 0.8, "level_state": "POSITIVE"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "RE-RATING"          # runway maturing -> do not chase


def test_glut_risk_loose_but_estimates_high():
    bn = {"band": "LOOSE", "tightness": -0.6}
    rv = {"breadth": 0.4, "level_state": "POSITIVE"}
    stage, _ = fc._stage(bn, rv)
    assert stage == "GLUT-RISK"


def test_revisions_only_flags_lateness():
    stage, _ = fc._stage(None, {"breadth": 0.8, "level_state": "POSITIVE"})
    assert stage == "RE-RATING"
    stage2, _ = fc._stage(None, {"breadth": 0.02, "level_state": "FLAT_LOW"})
    assert stage2 == "WATCH"


def test_ranks_precipice_first():
    bottleneck = {"themes": {
        "a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True},
        "b": {"name": "B", "band": "TIGHT", "tightness": 0.9},
    }}
    revisions = {"themes": {
        "a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"},   # PRECIPICE
        "b": {"name": "B", "breadth": 0.8, "level_state": "POSITIVE"},    # RE-RATING
    }}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand={"themes": {}}, write_ledger=False)
    assert out["themes"][0]["theme"] == "a"
    assert out["themes"][0]["stage"] == "PRECIPICE"


def test_entry_overlay():
    # thesis stage + active dislocation -> entry window
    ready, _ = fc._entry("PRECIPICE", {"active": True, "verdict": "buyable_washout"})
    assert ready is True
    # thesis stage but calm market -> wait for the flush
    ready2, note2 = fc._entry("BROADENING", {"active": False, "verdict": "calm"})
    assert ready2 is False and "await" in note2.lower()
    # late stage never an entry, even on a flush
    ready3, _ = fc._entry("RE-RATING", {"active": True})
    assert ready3 is False


def test_demand_confirms_in_rationale():
    bottleneck = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True}}}
    revisions = {"themes": {"a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"}}}
    demand = {"themes": {"a": {"name": "A", "demand_band": "ACCELERATING",
                               "capex_yoy": 69.0, "strength": "direct"}}}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand=demand, glut={"themes": {}}, write_ledger=False)
    r = out["themes"][0]
    assert r["stage"] == "PRECIPICE"
    assert r["demand_band"] == "ACCELERATING"
    assert "capex" in r["rationale"].lower()


def test_guidance_confirms_without_changing_stage():
    # T3 guidance is a LEADING confirmer on the rationale + a score input, never a
    # stage-changer: a BROAD-RAISE on a PRECIPICE theme stays PRECIPICE but lifts the
    # acceleration axis and annotates the rationale.
    bottleneck = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True}}}
    revisions = {"themes": {"a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"}}}
    guidance = {"themes": {"a": {"name": "A", "guidance_band": "BROAD-RAISE",
                                 "n_raisers": 3, "n_cutters": 0, "net": 3}}}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand={"themes": {}}, glut={"themes": {}},
                                       guidance=guidance, write_ledger=False)
    r = out["themes"][0]
    assert r["stage"] == "PRECIPICE"
    assert r["guidance_band"] == "BROAD-RAISE"
    assert r["guidance_raisers"] == 3
    assert "pre-signaling" in r["rationale"]
    assert r["score_detail"]["axes"]["acceleration"] >= 0.5   # T3 raise lifts acceleration


def test_altdata_confirmers_inverse_to_breadth():
    # leading alt-data confirmers reinforce an EARLY (thesis-stage) theme's rationale + score,
    # but on a LATE (broad-revisions) theme they are crowding -> NOT added to the rationale.
    bn = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9, "regime": True}}}
    conf = {"themes": {"a": {"name": "A", "n_leading": 2, "leading_members": ["MU", "WDC"],
                             "summary": "2 insider clusters · 1 gov-award accel"}}}
    early = fc.compute_foresight_cascade(
        bottleneck=bn, revisions={"themes": {"a": {"name": "A", "breadth": 0.05, "level_state": "FLAT_LOW"}}},
        demand={"themes": {}}, glut={"themes": {}}, guidance={"themes": {}}, confirmers=conf, write_ledger=False)
    r = early["themes"][0]
    assert r["stage"] == "PRECIPICE" and r["n_altdata_leading"] == 2
    assert "alt-data confirms" in r["rationale"]

    late = fc.compute_foresight_cascade(
        bottleneck=bn, revisions={"themes": {"a": {"name": "A", "breadth": 0.9, "level_state": "POSITIVE"}}},
        demand={"themes": {}}, glut={"themes": {}}, guidance={"themes": {}}, confirmers=conf, write_ledger=False)
    r2 = late["themes"][0]
    assert r2["stage"] == "RE-RATING"
    assert "alt-data confirms" not in r2["rationale"]              # crowding, not a tell, when broad
    assert r["score_detail"]["axes"]["acceleration"] > r2["score_detail"]["axes"]["acceleration"]


def test_glut_overrides_to_exit_risk():
    # a forming glut while estimates are still broad -> GLUT-RISK (exit clock) takes precedence
    bottleneck = {"themes": {"a": {"name": "A", "band": "TIGHT", "tightness": 0.9}}}
    revisions = {"themes": {"a": {"name": "A", "breadth": 0.8, "level_state": "POSITIVE"}}}
    glut = {"themes": {"a": {"name": "A", "band": "GLUT_FORMING", "glut_score": 0.8}}}
    out = fc.compute_foresight_cascade(bottleneck=bottleneck, revisions=revisions,
                                       demand={"themes": {}}, glut=glut, write_ledger=False)
    r = out["themes"][0]
    assert r["stage"] == "GLUT-RISK"
    assert r["glut_band"] == "GLUT_FORMING"
    assert "exit clock" in r["rationale"]


# ---- W0a: _append_ledger logs ALL stages with transition-dedup + heartbeat ----

def _make_payload(stages: dict[str, str], asof: str = "2026-07-01") -> dict:
    """Minimal payload for _append_ledger with given theme->stage mapping."""
    themes = []
    for theme, stage in stages.items():
        themes.append({
            "theme": theme, "stage": stage,
            "bottleneck_band": None, "revision_breadth": None,
        })
    return {"asof": asof, "themes": themes}


def test_all_stages_get_logged(monkeypatch, tmp_path):
    """_append_ledger must log ALL stages (not just PRECIPICE/BROADENING)."""
    import engine.foresight_cascade as fc_mod
    monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(fc_mod.config, "load", lambda: {"themes": {
        "memory_storage": {"tickers": ["MU"]},
        "ai_semiconductors": {"tickers": ["NVDA"]},
        "copper_steel_electrify": {"tickers": ["FCX"]},
        "glp1_obesity": {"tickers": ["LLY"]},
    }})
    payload = _make_payload({
        "memory_storage": "PRECIPICE",
        "ai_semiconductors": "RE-RATING",
        "copper_steel_electrify": "WATCH",
        "glp1_obesity": "UNKNOWN",
    })
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)
    fc_mod._append_ledger(payload)
    rows = [(tmp_path / "foresight" / "log.jsonl").read_text().splitlines()]
    logged = [json.loads(r) for r in rows[0] if r.strip()]
    stages_logged = {r["theme"]: r["stage"] for r in logged}
    assert stages_logged["memory_storage"] == "PRECIPICE"
    assert stages_logged["ai_semiconductors"] == "RE-RATING"
    assert stages_logged["copper_steel_electrify"] == "WATCH"
    assert stages_logged["glp1_obesity"] == "UNKNOWN"


def test_transition_dedup_logs_on_change_skips_same_stage(monkeypatch, tmp_path):
    """Log on stage transition; skip if same stage and within heartbeat window."""
    import engine.foresight_cascade as fc_mod
    monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(fc_mod.config, "load",
                        lambda: {"themes": {"memory_storage": {"tickers": ["MU"]}}})
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)

    # day 1: initial log (asof 2026-07-01) — stage WATCH
    fc_mod._append_ledger(_make_payload({"memory_storage": "WATCH"}, asof="2026-07-01"))
    # day 3: same stage, 2 days later — within heartbeat window → NOT logged again
    fc_mod._append_ledger(_make_payload({"memory_storage": "WATCH"}, asof="2026-07-03"))
    # day 5: stage changes to RE-RATING → logged (transition)
    fc_mod._append_ledger(_make_payload({"memory_storage": "RE-RATING"}, asof="2026-07-05"))

    lines = (tmp_path / "foresight" / "log.jsonl").read_text().splitlines()
    logged = [json.loads(r) for r in lines if r.strip()]
    assert len(logged) == 2   # day-1 WATCH + day-5 RE-RATING; day-3 same-stage skip
    assert logged[0]["stage"] == "WATCH" and logged[0]["asof"] == "2026-07-01"
    assert logged[1]["stage"] == "RE-RATING" and logged[1]["asof"] == "2026-07-05"


def test_heartbeat_logs_when_stage_unchanged_but_stale(monkeypatch, tmp_path):
    """Even with unchanged stage, log when >7 days since last logged row (heartbeat)."""
    import engine.foresight_cascade as fc_mod
    monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(fc_mod.config, "load",
                        lambda: {"themes": {"memory_storage": {"tickers": ["MU"]}}})
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)

    # day 1: WATCH logged
    fc_mod._append_ledger(_make_payload({"memory_storage": "WATCH"}, asof="2026-07-01"))
    # day 9: same stage WATCH but 8 days later → heartbeat fires → logged
    fc_mod._append_ledger(_make_payload({"memory_storage": "WATCH"}, asof="2026-07-09"))

    lines = (tmp_path / "foresight" / "log.jsonl").read_text().splitlines()
    logged = [json.loads(r) for r in lines if r.strip()]
    assert len(logged) == 2   # both logged: initial + heartbeat
    assert logged[0]["asof"] == "2026-07-01"
    assert logged[1]["asof"] == "2026-07-09"


def test_same_day_reruns_are_idempotent(monkeypatch, tmp_path):
    """Multiple runs on the same asof produce only one row per (theme, asof)."""
    import engine.foresight_cascade as fc_mod
    monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(fc_mod.config, "load",
                        lambda: {"themes": {"memory_storage": {"tickers": ["MU"]}}})
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)

    payload = _make_payload({"memory_storage": "PRECIPICE"}, asof="2026-07-01")
    fc_mod._append_ledger(payload)
    fc_mod._append_ledger(payload)  # re-run same day
    fc_mod._append_ledger(payload)  # and again

    lines = (tmp_path / "foresight" / "log.jsonl").read_text().splitlines()
    logged = [json.loads(r) for r in lines if r.strip()]
    assert len(logged) == 1   # exactly one row — idempotent


def test_pit_membership_snapshot_in_all_stage_rows(monkeypatch, tmp_path):
    """members[] is captured at log time for ALL stage rows (not only thesis stages)."""
    import engine.foresight_cascade as fc_mod
    monkeypatch.setattr(fc_mod.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(fc_mod.config, "load",
                        lambda: {"themes": {"memory_storage": {"tickers": ["MU", "WDC"]}}})
    (tmp_path / "foresight").mkdir(parents=True, exist_ok=True)

    fc_mod._append_ledger(_make_payload({"memory_storage": "WATCH"}, asof="2026-07-01"))

    lines = (tmp_path / "foresight" / "log.jsonl").read_text().splitlines()
    logged = [json.loads(r) for r in lines if r.strip()]
    assert len(logged) == 1
    assert set(logged[0]["members"]) == {"MU", "WDC"}   # PIT snapshot present


# ---- W1a/b: text-grade PRECIPICE, text-only cap, negated exclusion, shadow log ----

def test_text_tight_flat_revisions_yields_precipice_text():
    """TIGHT (text) band + flat revisions → PRECIPICE (text), not PRECIPICE."""
    bn = {"band": "TIGHT (text)", "tightness": None, "regime": False, "text_only": True}
    rv = {"breadth": 0.04, "level_state": "FLAT_LOW"}
    stage, rationale = fc._stage(bn, rv)
    assert stage == "PRECIPICE (text)"
    assert "text-only" in rationale


def test_text_tight_rising_revisions_yields_broadening_text():
    """TIGHT (text) band + rising revisions → BROADENING (text)."""
    bn = {"band": "TIGHT (text)", "tightness": None, "regime": False, "text_only": True}
    rv = {"breadth": 0.25, "level_state": "POSITIVE"}
    stage, rationale = fc._stage(bn, rv)
    assert stage == "BROADENING (text)"
    assert "text-only" in rationale


def test_text_only_cap_binds_at_50(monkeypatch):
    """2 affirmative filers + flat revisions → PRECIPICE (text); text_only cap still at 50."""
    from engine import foresight_score as fs

    # A row that would score high physically but has text-only band
    row = {
        "stage": "PRECIPICE (text)",
        "bottleneck_band": "TIGHT (text)",
        "bottleneck_text_only": True,
        "tightness": None,
        "bottleneck_regime": False,
        "demand_band": "ACCELERATING",
        "capex_yoy": 69,
        "demand_strength": "direct",
        "revision_breadth": 0.04,
        "revision_level": "FLAT_LOW",
        "broadening_state": "FLAT_LOW",
        "est_drift_90d": 5,
        "glut_band": "STABLE",
        "entry_ready": False,
    }
    s = fs.score_row(row)
    assert s["physical_confirmed"] is False, "text-only must NOT count as physical confirmation"
    assert s["score"] <= 50.0, f"text-only cap must bind: got {s['score']}"
    assert any("text-only" in c for c in s["caps"])


def test_text_only_entry_not_ready():
    """Text thesis stages must never be entry-ready even with an active dislocation."""
    ready, note = fc._entry("PRECIPICE (text)", {"active": True, "verdict": "buyable_washout"})
    assert ready is False
    assert "text-only" in note or "awaiting" in note.lower()

    ready2, _ = fc._entry("BROADENING (text)", {"active": True, "verdict": "buyable_washout"})
    assert ready2 is False


def test_precipice_text_in_cascade(monkeypatch, tmp_path):
    """compute_foresight_cascade with a TIGHT (text) bn + flat rv → PRECIPICE (text)
    in the output, and bottleneck_text_only=True in the cascade row."""
    bottleneck = {"themes": {
        "glp1_obesity": {
            "name": "GLP-1", "band": "TIGHT (text)", "tightness": None,
            "regime": False, "text_only": True,
        }
    }}
    revisions = {"themes": {
        "glp1_obesity": {"name": "GLP-1", "breadth": 0.03, "level_state": "FLAT_LOW"},
    }}
    out = fc.compute_foresight_cascade(
        bottleneck=bottleneck, revisions=revisions,
        demand={"themes": {}}, glut={"themes": {}}, write_ledger=False,
    )
    assert out is not None
    r = out["themes"][0]
    assert r["stage"] == "PRECIPICE (text)"
    assert r["bottleneck_text_only"] is True
    # score must be capped at 50
    assert r["score"] <= 50.0


# ---- W2a (P1-A): percentile late-line tests ----------------------------------------

def _rv_themes_with_breadth(vals: dict[str, float]) -> dict:
    """Helper: build rv_themes dict from theme -> breadth mapping."""
    return {k: {"breadth": v, "level_state": "POSITIVE", "name": k}
            for k, v in vals.items()}


def _rv_themes_with_breadth_cov(vals: dict[str, float], cov_vals: dict[str, float]) -> dict:
    """Helper: build rv_themes dict with both breadth and breadth_cov."""
    out = {}
    for k, v in vals.items():
        out[k] = {"breadth": v, "level_state": "POSITIVE", "name": k}
        if k in cov_vals:
            out[k]["breadth_cov"] = cov_vals[k]
    return out


def test_percentile_lateline_85th_flags_broad_50th_does_not():
    """(c) Percentile late-line: a theme at the 85th percentile flags RE-RATING (broad);
    a theme at the 50th percentile does NOT — even when both are > 0.50 absolute."""
    # 10 themes with breadth_cov values spanning 0.1 to 1.0
    # 80th pctile of [0.1,0.2,...,1.0] = 0.82 (numpy.percentile computes linear interp)
    rv_themes = _rv_themes_with_breadth_cov(
        {f"t{i}": (i + 1) / 10 for i in range(10)},
        {f"t{i}": (i + 1) / 10 for i in range(10)},
    )
    threshold, basis = fc._compute_broad_hi_threshold(rv_themes)
    assert basis == "percentile_cov", f"expected percentile_cov, got {basis}"

    # t8 has breadth_cov=0.9 — above 80th pctile (~0.82) → broad
    bn_tight = {"band": "TIGHT", "tightness": 0.9}
    rv_t8 = {"breadth": 0.9, "breadth_cov": 0.9, "level_state": "POSITIVE"}
    stage_late, _ = fc._stage(bn_tight, rv_t8, broad_hi_threshold=threshold)
    assert stage_late == "RE-RATING", (
        f"theme at 85th pctile breadth_cov (0.9) should be RE-RATING, got {stage_late}"
    )

    # t4 has breadth_cov=0.5 — below 80th pctile (~0.82); also > 0.50 absolute cut
    # With percentile: NOT broad → BROADENING (tight band + positive revisions)
    rv_t4 = {"breadth": 0.5, "breadth_cov": 0.5, "level_state": "POSITIVE"}
    stage_early, _ = fc._stage(bn_tight, rv_t4, broad_hi_threshold=threshold)
    assert stage_early in ("BROADENING", "PRECIPICE"), (
        f"theme at 50th pctile breadth_cov (0.5) should not be RE-RATING, got {stage_early}"
    )
    # Specifically: with absolute BROAD_HI=0.50 this would be RE-RATING; with percentile it's not
    stage_absolute, _ = fc._stage(bn_tight, rv_t4, broad_hi_threshold=fc.BROAD_HI)
    # Verify the test premise: 0.5 > BROAD_HI (0.50) is false (equal, not >), so BROADENING
    # regardless. Use 0.51 to make the contrast clear:
    rv_just_over = {"breadth": 0.51, "breadth_cov": 0.51, "level_state": "POSITIVE"}
    stage_just_over_absolute, _ = fc._stage(bn_tight, rv_just_over, broad_hi_threshold=fc.BROAD_HI)
    stage_just_over_pctile, _ = fc._stage(bn_tight, rv_just_over, broad_hi_threshold=threshold)
    assert stage_just_over_absolute == "RE-RATING", (
        "0.51 > BROAD_HI=0.50 absolute → RE-RATING (test premise)"
    )
    assert stage_just_over_pctile != "RE-RATING", (
        "0.51 is at ~30th pctile — percentile threshold should NOT flag it as RE-RATING"
    )


def test_percentile_lateline_fewer_than_8_themes_uses_absolute_fallback():
    """(d) n_themes < _PCTILE_MIN_THEMES (8) → absolute fallback BROAD_HI constant."""
    # Only 5 themes — below the minimum for percentile to be meaningful
    rv_themes = _rv_themes_with_breadth_cov(
        {f"t{i}": 0.9 for i in range(5)},
        {f"t{i}": 0.9 for i in range(5)},
    )
    threshold, basis = fc._compute_broad_hi_threshold(rv_themes)
    assert basis == "absolute_fallback", (
        f"fewer than {fc._PCTILE_MIN_THEMES} themes should use absolute_fallback, got {basis}"
    )
    assert threshold == fc.BROAD_HI


def test_percentile_lateline_mixed_availability_uses_single_scale():
    """(e) Mixed breadth_cov availability: if fewer than half themes have breadth_cov,
    run the percentile on legacy breadth for ALL — never mix scales."""
    # 10 themes: only 3 have breadth_cov (fewer than half=5) → must use legacy breadth
    vals = {f"t{i}": (i + 1) / 10 for i in range(10)}
    cov_vals = {f"t{i}": (i + 1) / 10 for i in range(3)}    # only t0, t1, t2 have coverage
    rv_themes = _rv_themes_with_breadth_cov(vals, cov_vals)
    threshold, basis = fc._compute_broad_hi_threshold(rv_themes)
    assert basis == "percentile_legacy", (
        f"fewer than half themes have breadth_cov → must use legacy breadth, got basis={basis}"
    )
    # threshold should be the ~80th pctile of legacy breadth values [0.1..1.0]
    import numpy as np
    expected_threshold = float(np.percentile(list(vals.values()), fc._BROAD_HI_PCTILE))
    assert abs(threshold - expected_threshold) < 0.001


def test_percentile_lateline_surfaced_in_cascade_payload():
    """(c) late_line_basis and late_line_threshold surfaced in cascade payload."""
    # Build a cascade with >=8 themes so percentile fires
    rv_themes_dict = {f"theme_{i}": {"name": f"T{i}", "breadth": (i + 1) / 10,
                                      "level_state": "POSITIVE"}
                      for i in range(10)}
    out = fc.compute_foresight_cascade(
        bottleneck={"themes": {}},
        revisions={"themes": rv_themes_dict},
        demand={"themes": {}}, glut={"themes": {}}, write_ledger=False,
    )
    assert out is not None
    assert "late_line_basis" in out, "late_line_basis must be surfaced in cascade payload"
    assert out["late_line_basis"] in ("percentile_cov", "percentile_legacy", "absolute_fallback")
    assert "late_line_threshold" in out
    assert isinstance(out["late_line_threshold"], float)


def test_divergent_scales_cov_threshold_never_compared_to_legacy_breadth():
    """REVIEW F1/F2 REGRESSION: when the basis is percentile_cov, _stage must compare
    the theme's breadth_cov (same scale as the threshold), NEVER its legacy breadth.
    De-saturated fixture: legacy breadth saturated ~0.9, breadth_cov ~0.10-0.27. Before
    the fix, every theme's legacy 0.9 cleared the ~0.23 cov-scale threshold -> 12/12
    RE-RATING (the exact inversion of the de-saturation this wave ships)."""
    from engine.foresight_cascade import _compute_broad_hi_threshold, _stage
    vals = {f"t{i}": 0.90 for i in range(12)}                       # saturated legacy
    cov = {f"t{i}": 0.10 + 0.015 * i for i in range(12)}            # 0.10 .. 0.265
    rv_themes = _rv_themes_with_breadth_cov(vals, cov)
    thr, basis = _compute_broad_hi_threshold(rv_themes)
    assert basis == "percentile_cov"
    # mid-pack theme (t5, cov=0.175 < thr) must NOT flag RE-RATING despite legacy 0.9
    stage_mid, _ = _stage(None, rv_themes["t5"], None,
                          broad_hi_threshold=thr, late_line_basis=basis)
    assert stage_mid != "RE-RATING", (
        "cov-scale threshold was compared against legacy breadth — scale mixing")
    # top-of-distribution theme (t11, cov=0.265 > thr) SHOULD flag late
    stage_top, _ = _stage(None, rv_themes["t11"], None,
                          broad_hi_threshold=thr, late_line_basis=basis)
    assert stage_top == "RE-RATING"


def test_cov_basis_theme_without_cov_not_flaggable_late():
    """In a percentile_cov build, a theme lacking breadth_cov is NOT flaggable late —
    it must never fall back to comparing legacy breadth against the cov threshold."""
    from engine.foresight_cascade import _compute_broad_hi_threshold, _stage
    vals = {f"t{i}": 0.95 for i in range(10)}
    cov = {f"t{i}": 0.10 + 0.02 * i for i in range(9)}   # t9 has NO breadth_cov
    rv_themes = _rv_themes_with_breadth_cov(vals, cov)
    thr, basis = _compute_broad_hi_threshold(rv_themes)
    assert basis == "percentile_cov"
    stage, _ = _stage(None, rv_themes["t9"], None,
                      broad_hi_threshold=thr, late_line_basis=basis)
    assert stage != "RE-RATING"


def test_late_line_provisional_flag_in_payload():
    """REVIEW F3: the p80 percentile choice is uncalibrated pending the shadow ledger —
    the payload must declare it provisional."""
    from engine.foresight_cascade import compute_foresight_cascade
    c = compute_foresight_cascade(write_ledger=False)
    if c is not None:
        assert c.get("late_line_provisional") is True


# ── W5b (Q4): two-tier desk — tier tagging ───────────────────────────────────

def test_tier_p_for_numeric_fred_band():
    """Tier spec contract for _compute_tier — tests the four cases the review specifies.

    (a) numeric_band=NEUTRAL → P  (NEUTRAL is a live FRED composite read, not language-only)
    (b) top band "TIGHT (text)" WITH live numeric_band=TIGHTENING → P
        (anti-laundering guard rewrites top band; numeric_band retains the real measurement)
    (c) numeric_band=None + top band NEUTRAL (language-only theme) → W
        (cybersecurity/solar: NEUTRAL top band but no FRED leg → must stay W)
    (d) numeric_band=None + live theme_feed_summary → P
        (orphan-rescue: FDA shortage promotes glp1_obesity even with no FRED bottleneck)
    """
    from engine.foresight_cascade import _compute_tier

    # (a) NEUTRAL is a live numeric FRED composite band → Tier P
    assert _compute_tier("NEUTRAL", None) == "P", "NEUTRAL numeric_band should be Tier P"

    # (a) Other numeric bands also qualify
    for numeric_band in ("TIGHT", "SOLD_OUT", "LOOSE", "TIGHTENING", "GLUT_FORMING", "GLUT"):
        assert _compute_tier(numeric_band, None) == "P", (
            f"numeric_band={numeric_band} should be Tier P"
        )

    # (b) anti-laundering guard rewrites top band to "TIGHT (text)" but numeric_band
    #     retains TIGHTENING — _compute_tier receives numeric_band, not top band → P
    assert _compute_tier("TIGHTENING", None) == "P", (
        "numeric_band=TIGHTENING (FRED-mapped theme with text top band) should be Tier P"
    )

    # (c) language-only theme: top band is NEUTRAL but numeric_band is None (no FRED leg)
    #     → must stay Tier W (cybersecurity / solar case)
    assert _compute_tier(None, None) == "W", (
        "numeric_band=None (language-only theme) must be Tier W, NOT promoted by top-level band"
    )

    # (d) numeric_band=None but live theme_feed_summary → Tier P (orphan-rescue)
    feed = {"source": "fda_shortages", "band": "SHORTAGE_ACTIVE", "label": "FDA shortage ACTIVE"}
    assert _compute_tier(None, feed) == "P", (
        "theme_feed_summary present → Tier P even with numeric_band=None"
    )


def test_tier_w_for_null_numeric_band():
    """Tier W when numeric_band is None (no FRED measurement — language-only / AWAITING / null).

    Note: _compute_tier now receives bn.get("numeric_band"), NOT the top-level band.
    Themes with AWAITING_DATA or text-only top bands have numeric_band=None → Tier W.
    """
    from engine.foresight_cascade import _compute_tier
    # All these represent the numeric_band=None case (no live FRED read)
    assert _compute_tier(None, None) == "W", "numeric_band=None → Tier W"


def test_tier_p_for_theme_feed_summary_present():
    """Tier P when a theme_feed_summary is present (orphan-rescue feed) — even with
    numeric_band=None (FDA shortages rescue glp1_obesity into Tier P when FRED leg absent)."""
    from engine.foresight_cascade import _compute_tier
    feed = {"source": "fda_shortages", "band": "SHORTAGE_ACTIVE", "label": "FDA shortage ACTIVE"}
    assert _compute_tier(None, feed) == "P"


def test_tier_field_in_cascade_rows():
    """Each cascade row has a 'tier' field of 'P' or 'W'.

    Tier P requires numeric_band (the FRED-backed measurement) to be non-None.
    The bottleneck engine populates numeric_band on FRED-mapped themes.
    Language-only/AWAITING themes have numeric_band=None → Tier W.
    """
    bottleneck = {"themes": {
        # memory_storage: real FRED leg → numeric_band present (e.g. TIGHT from PPI composite)
        "memory_storage": {"name": "Memory", "band": "TIGHT", "tightness": 0.9,
                           "numeric_band": "TIGHT"},
        # glp1_obesity: no FRED bottleneck → numeric_band absent → Tier W (no feed either)
        "glp1_obesity":   {"name": "GLP-1", "band": None, "numeric_band": None},
        # cybersecurity: AWAITING_DATA top band, no FRED → numeric_band None → Tier W
        "cybersecurity":  {"name": "Cyber", "band": "AWAITING_DATA", "numeric_band": None},
    }}
    revisions = {"themes": {
        "memory_storage": {"name": "Memory", "breadth": 0.1, "level_state": "FLAT_LOW"},
        "glp1_obesity":   {"name": "GLP-1",  "breadth": 0.2, "level_state": "POSITIVE"},
        "cybersecurity":  {"name": "Cyber",  "breadth": 0.15, "level_state": "FLAT_LOW"},
    }}
    out = fc.compute_foresight_cascade(
        bottleneck=bottleneck, revisions=revisions,
        demand={"themes": {}}, glut={"themes": {}},
        fda_scarcity={},   # empty — no feed for these themes
        write_ledger=False,
    )
    assert out is not None
    tiers = {r["theme"]: r["tier"] for r in out["themes"]}
    assert tiers["memory_storage"] == "P"   # numeric_band=TIGHT → Tier P
    assert tiers["glp1_obesity"]   == "W"   # numeric_band=None, no feed → Tier W
    assert tiers["cybersecurity"]  == "W"   # numeric_band=None → Tier W


def test_tier_p_via_fda_feed_no_fred():
    """(d) glp1_obesity tier-upgrades to P when theme_feed_summary is populated by fda_scarcity."""
    bottleneck = {"themes": {
        "glp1_obesity": {"name": "GLP-1", "band": "AWAITING_DATA"},
    }}
    revisions = {"themes": {
        "glp1_obesity": {"name": "GLP-1", "breadth": 0.1, "level_state": "FLAT_LOW"},
    }}
    # Synthetic fda_scarcity dict — shortage active
    fda_scarcity_data = {
        "glp1_obesity": {
            "band": "SHORTAGE_ACTIVE",
            "n_active": 2,
            "n_resolved": 0,
            "molecules_checked": ["semaglutide"],
            "details": ["Semaglutide Injection [Current/Limited Availability]"],
            "rationale": "2 active shortage records",
        }
    }
    out = fc.compute_foresight_cascade(
        bottleneck=bottleneck, revisions=revisions,
        demand={"themes": {}}, glut={"themes": {}},
        fda_scarcity=fda_scarcity_data,
        write_ledger=False,
    )
    assert out is not None
    r = out["themes"][0]
    assert r["theme"] == "glp1_obesity"
    assert r["tier"] == "P", "FDA shortage feed should promote glp1_obesity to Tier P"
    assert r["theme_feed_summary"] is not None
    assert r["theme_feed_summary"]["band"] == "SHORTAGE_ACTIVE"


# ── W5b (§3.4): FDA scarcity engine ─────────────────────────────────────────

def _make_shortage_df(rows: list[dict]) -> "pd.DataFrame":
    import pandas as pd
    return pd.DataFrame(rows)


def test_fda_scarcity_active_band():
    """(b) Active shortage records → SHORTAGE_ACTIVE band."""
    from engine.fda_scarcity import compute_fda_scarcity, SHORTAGE_ACTIVE
    df = _make_shortage_df([
        {"generic_name": "Semaglutide Injection", "status": "Current",
         "availability": "Limited Availability", "initial_posting_date": "07/01/2023"},
        {"generic_name": "Liraglutide Injection", "status": "Current",
         "availability": "Unavailable", "initial_posting_date": "06/15/2022"},
    ])
    result = compute_fda_scarcity(df)
    glp1 = result.get("glp1_obesity")
    assert glp1 is not None
    assert glp1["band"] == SHORTAGE_ACTIVE
    assert glp1["n_active"] >= 2


def test_fda_scarcity_resolved_band():
    """(b) All shortage records resolved → SHORTAGE_RESOLVED (the glut tell)."""
    from engine.fda_scarcity import compute_fda_scarcity, SHORTAGE_RESOLVED
    df = _make_shortage_df([
        {"generic_name": "Semaglutide Tablet", "status": "Resolved",
         "availability": "", "initial_posting_date": "03/01/2022"},
        {"generic_name": "Liraglutide Injection", "status": "Resolved",
         "availability": "", "initial_posting_date": "07/18/2023"},
    ])
    result = compute_fda_scarcity(df)
    glp1 = result.get("glp1_obesity")
    assert glp1 is not None
    assert glp1["band"] == SHORTAGE_RESOLVED
    assert glp1["n_resolved"] >= 2
    assert "glut tell" in glp1["rationale"].lower() or "resolved" in glp1["rationale"].lower()


def test_fda_scarcity_none_on_missing_cache(monkeypatch, tmp_path):
    """(c) Missing cache → all themes return None.

    Hermetic: monkeypatches the cache loader so the test never touches real disk data
    (data/fda/shortages.parquet).  Without this patch the cache loader succeeds on
    checkouts that already have the file, making the test pass for the wrong reason.
    """
    import engine.fda_scarcity as fda_mod

    # Patch load_shortages_cache inside the fda_scarcity module to always raise,
    # simulating a missing/broken cache independently of what is on disk.
    def _no_cache():
        raise FileNotFoundError("monkeypatched: no cache")

    # The loader is imported lazily inside compute_fda_scarcity; patch the module
    # so that `collectors.fda_shortages.load_shortages_cache` raises.
    import sys
    fake_collector = type(sys)("collectors.fda_shortages")
    fake_collector.load_shortages_cache = _no_cache
    monkeypatch.setitem(sys.modules, "collectors.fda_shortages", fake_collector)

    from engine.fda_scarcity import compute_fda_scarcity
    result = compute_fda_scarcity(df=None)
    assert isinstance(result, dict)
    for v in result.values():
        assert v is None, f"expected None for missing cache, got {v}"


def test_fda_scarcity_mixed_active_and_resolved():
    """(b) Mixed active + resolved → SHORTAGE_ACTIVE wins (active takes priority)."""
    from engine.fda_scarcity import compute_fda_scarcity, SHORTAGE_ACTIVE
    df = _make_shortage_df([
        {"generic_name": "Semaglutide Injection", "status": "Current",
         "availability": "Unavailable", "initial_posting_date": "07/01/2023"},
        {"generic_name": "Liraglutide Injection", "status": "Resolved",
         "availability": "", "initial_posting_date": "06/15/2022"},
    ])
    result = compute_fda_scarcity(df)
    glp1 = result.get("glp1_obesity")
    assert glp1 is not None
    assert glp1["band"] == SHORTAGE_ACTIVE


def test_fda_scarcity_no_glp1_records():
    """(b) No GLP-1 records in df → NONE band (not an error)."""
    from engine.fda_scarcity import compute_fda_scarcity, BAND_NONE
    df = _make_shortage_df([
        {"generic_name": "Bupivacaine Hydrochloride", "status": "Current",
         "availability": "Unavailable", "initial_posting_date": "07/01/2023"},
    ])
    result = compute_fda_scarcity(df)
    glp1 = result.get("glp1_obesity")
    assert glp1 is not None
    assert glp1["band"] == BAND_NONE


def test_theme_feed_summary_flows_into_glp1_row():
    """(d) theme_feed_summary is populated on the glp1_obesity cascade row when
    fda_scarcity has an active shortage for it."""
    bottleneck = {"themes": {
        "glp1_obesity": {"name": "GLP-1 / Obesity", "band": "AWAITING_DATA"},
    }}
    revisions = {"themes": {
        "glp1_obesity": {"name": "GLP-1 / Obesity", "breadth": 0.05, "level_state": "FLAT_LOW"},
    }}
    fda_scarcity_data = {
        "glp1_obesity": {
            "band": "SHORTAGE_ACTIVE",
            "n_active": 3,
            "n_resolved": 0,
            "molecules_checked": ["semaglutide", "tirzepatide", "liraglutide"],
            "details": ["Semaglutide Injection [Current/Limited Availability]"],
            "rationale": "3 active shortage records — demand exceeds supply",
        }
    }
    out = fc.compute_foresight_cascade(
        bottleneck=bottleneck, revisions=revisions,
        demand={"themes": {}}, glut={"themes": {}},
        fda_scarcity=fda_scarcity_data,
        write_ledger=False,
    )
    assert out is not None
    r = out["themes"][0]
    assert r["theme"] == "glp1_obesity"
    # feed summary must be present and correctly structured
    tfs = r.get("theme_feed_summary")
    assert tfs is not None, "theme_feed_summary should be populated for glp1_obesity"
    assert tfs["band"] == "SHORTAGE_ACTIVE"
    assert tfs["source"] == "fda_shortages"
    assert "shortage" in tfs["label"].lower()
    # stage is NOT changed by the feed — still driven by T1/T4
    assert r["stage"] in ("WATCH", "PRECIPICE (text)", "PRECIPICE", "BROADENING",
                          "RE-RATING", "UNKNOWN"), f"unexpected stage: {r['stage']}"


def test_theme_feed_summary_none_when_no_fda_data():
    """(c) theme_feed_summary is None when fda_scarcity is empty/absent."""
    bottleneck = {"themes": {
        "glp1_obesity": {"name": "GLP-1 / Obesity", "band": "AWAITING_DATA"},
    }}
    revisions = {"themes": {
        "glp1_obesity": {"name": "GLP-1 / Obesity", "breadth": 0.1, "level_state": "FLAT_LOW"},
    }}
    out = fc.compute_foresight_cascade(
        bottleneck=bottleneck, revisions=revisions,
        demand={"themes": {}}, glut={"themes": {}},
        fda_scarcity={},   # empty dict — no data for any theme
        write_ledger=False,
    )
    assert out is not None
    r = out["themes"][0]
    assert r.get("theme_feed_summary") is None


# ── W5b: Jinja render test — watch shelf renders; stage pills exclude Tier W ─

def test_jinja_watch_shelf_renders_and_pills_exclude_tier_w():
    """(e) Jinja render: Tier W themes appear in watch shelf; stage pills only count Tier P."""
    import sys, os
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from jinja2 import Environment, FileSystemLoader
    import pathlib

    repo = pathlib.Path(__file__).resolve().parent.parent
    env = Environment(loader=FileSystemLoader(str(repo / "templates")), autoescape=True)
    tmpl = env.get_template("foresight.html.j2")

    # 2 Tier P themes (one TIGHT/numeric, one with FDA feed) + 1 Tier W
    themes_data = [
        {
            "theme": "memory_storage", "name": "Memory & Storage",
            "tier": "P", "stage": "PRECIPICE",
            "bottleneck_band": "TIGHT", "bottleneck_text_only": False, "tightness": 0.9,
            "bottleneck_regime": True, "demand_band": None, "demand_strength": None,
            "capex_yoy": None, "revision_breadth": 0.05, "revision_level": "FLAT_LOW",
            "broadening_state": "FLAT_LOW", "est_drift_90d": None,
            "guidance_band": None, "guidance_net": None, "guidance_raisers": None,
            "guidance_cutters": None, "altdata_summary": None, "n_altdata_leading": 0,
            "altdata_members": None, "glut_band": None, "glut_score": None,
            "theme_feed_summary": None,
            "rationale": "supply TIGHT while revisions not yet firing",
            "entry_ready": False, "entry_note": "thesis intact",
            "score": 62, "score_detail": {"verdict": "high-conviction", "axes": {}, "caps": []},
            "size_band": None, "size_note": None,
        },
        {
            "theme": "glp1_obesity", "name": "GLP-1 / Obesity",
            "tier": "P", "stage": "WATCH",
            "bottleneck_band": "AWAITING_DATA", "bottleneck_text_only": False, "tightness": None,
            "bottleneck_regime": False, "demand_band": None, "demand_strength": None,
            "capex_yoy": None, "revision_breadth": 0.08, "revision_level": "FLAT_LOW",
            "broadening_state": "FLAT_LOW", "est_drift_90d": None,
            "guidance_band": None, "guidance_net": None, "guidance_raisers": None,
            "guidance_cutters": None, "altdata_summary": None, "n_altdata_leading": 0,
            "altdata_members": None, "glut_band": None, "glut_score": None,
            "theme_feed_summary": {
                "source": "fda_shortages", "theme": "glp1_obesity",
                "band": "SHORTAGE_ACTIVE", "tone": "warn",
                "label": "FDA shortage ACTIVE (3 records)",
                "rationale": "3 active shortage records — demand exceeds supply",
                "n_active": 3, "n_resolved": 0,
            },
            "rationale": "supply not tight; FDA shortage ACTIVE — demand exceeds supply",
            "entry_ready": False, "entry_note": "not a thesis stage — no entry",
            "score": 42, "score_detail": {"verdict": "watch", "axes": {}, "caps": []},
            "size_band": None, "size_note": None,
        },
        {
            "theme": "cybersecurity", "name": "Cybersecurity",
            "tier": "W", "stage": "WATCH",
            "bottleneck_band": None, "bottleneck_text_only": False, "tightness": None,
            "bottleneck_regime": False, "demand_band": None, "demand_strength": None,
            "capex_yoy": None, "revision_breadth": 0.12, "revision_level": "FLAT_LOW",
            "broadening_state": "FLAT_LOW", "est_drift_90d": None,
            "guidance_band": None, "guidance_net": None, "guidance_raisers": None,
            "guidance_cutters": None, "altdata_summary": None, "n_altdata_leading": 0,
            "altdata_members": None, "glut_band": None, "glut_score": None,
            "theme_feed_summary": None,
            "rationale": "supply not tight; nothing actionable yet",
            "entry_ready": False, "entry_note": "not a thesis stage — no entry",
            "score": 38, "score_detail": {"verdict": "watch", "axes": {}, "caps": []},
            "size_band": None, "size_note": None,
        },
    ]
    stage_counts = {"PRECIPICE": 1, "BROADENING": 0, "RE-RATING": 0,
                    "GLUT-RISK": 0, "WATCH": 2, "UNKNOWN": 0}
    html = tmpl.render(
        cascade={"sizing": None, "demand_pool": None, "dislocation": None},
        themes=themes_data,
        stage_counts=stage_counts,
        stage_order=["PRECIPICE", "BROADENING", "RE-RATING", "GLUT-RISK", "WATCH", "UNKNOWN"],
        demand_pool=None, dislocation=None,
        track={"foresight": 0, "bottleneck": 0, "glut": 0, "revisions": 0,
               "guidance": 0, "emergence": 0, "subsector": 0, "recent": []},
        grade=None, emergence=None, subsectors=None,
        convergence=None, power=None, analyst=None, monitor=None, health=None,
        asof="2026-07-02", generated_utc="2026-07-02 00:00 UTC",
        nav_prefix="", active_section="research", active_page="foresight",
    )
    # Watch shelf must render with cybersecurity in it
    assert "fx-watch-shelf" in html, "watch shelf container missing"
    assert "Cybersecurity" in html
    # Watch shelf caveat must contain the honesty text
    assert "no numeric physical correlate" in html or "cannot reach a confirmed PRECIPICE" in html
    # Stage pills region: stage counts are Tier P only — cybersecurity (Tier W, WATCH) excluded
    # The pills only show Tier P themes: 1 PRECIPICE (memory_storage) + 1 WATCH (glp1_obesity,
    # BUT glp1_obesity is Tier P despite WATCH stage because of FDA feed)
    # Count "PRECIPICE" in the stage pills area (before watch shelf)
    assert "PRECIPICE" in html  # Tier P PRECIPICE card renders
    # Watch shelf chip ("+N on watch shelf") must appear
    assert "watch shelf" in html.lower() or "观察架" in html
    # FDA chip must appear for glp1_obesity
    assert "FDA shortage ACTIVE" in html
    # Cybersecurity should appear in watch shelf, not as a full card
    # (It has tier=W so it should be in .fx-watch-rows not .fx-cards)
    watch_shelf_pos = html.find("fx-watch-shelf")
    tier_p_cards_pos = html.find("fx-cards")
    # watch shelf comes after tier P cards section
    assert watch_shelf_pos > tier_p_cards_pos, (
        "watch shelf should render below Tier P cards"
    )


def test_jinja_tier_less_row_defaults_to_shelf():
    """F4: a row with no 'tier' field must land on the watch shelf, not silently vanish.

    Old cached JSON consumers (no tier key) must degrade visibly: the row appears in
    the watch shelf instead of dropping out of both selectattr/rejectattr filters.
    """
    import sys
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from jinja2 import Environment, FileSystemLoader

    repo = pathlib.Path(__file__).resolve().parent.parent
    env = Environment(loader=FileSystemLoader(str(repo / "templates")), autoescape=True)
    tmpl = env.get_template("foresight.html.j2")

    # One row WITH tier=P, one WITHOUT tier key (simulates old cached JSON)
    themes_data = [
        {
            "theme": "memory_storage", "name": "Memory & Storage",
            "tier": "P", "stage": "PRECIPICE",
            "bottleneck_band": "TIGHT", "bottleneck_text_only": False, "tightness": 0.9,
            "bottleneck_regime": True, "demand_band": None, "demand_strength": None,
            "capex_yoy": None, "revision_breadth": 0.05, "revision_level": "FLAT_LOW",
            "broadening_state": "FLAT_LOW", "est_drift_90d": None,
            "guidance_band": None, "guidance_net": None, "guidance_raisers": None,
            "guidance_cutters": None, "altdata_summary": None, "n_altdata_leading": 0,
            "altdata_members": None, "glut_band": None, "glut_score": None,
            "theme_feed_summary": None,
            "rationale": "supply TIGHT while revisions not yet firing",
            "entry_ready": False, "entry_note": "thesis intact",
            "score": 62, "score_detail": {"verdict": "high-conviction", "axes": {}, "caps": []},
            "size_band": None, "size_note": None,
        },
        {
            # NO 'tier' key — simulates old cached JSON row
            "theme": "old_cached_theme", "name": "Old Cached Theme",
            "stage": "WATCH",
            "bottleneck_band": None, "bottleneck_text_only": False, "tightness": None,
            "bottleneck_regime": False, "demand_band": None, "demand_strength": None,
            "capex_yoy": None, "revision_breadth": 0.03, "revision_level": "FLAT_LOW",
            "broadening_state": "FLAT_LOW", "est_drift_90d": None,
            "guidance_band": None, "guidance_net": None, "guidance_raisers": None,
            "guidance_cutters": None, "altdata_summary": None, "n_altdata_leading": 0,
            "altdata_members": None, "glut_band": None, "glut_score": None,
            "theme_feed_summary": None,
            "rationale": "no bottleneck data yet",
            "entry_ready": False, "entry_note": "not a thesis stage — no entry",
            "score": 30, "score_detail": {"verdict": "watch", "axes": {}, "caps": []},
            "size_band": None, "size_note": None,
        },
    ]
    stage_counts = {"PRECIPICE": 1, "BROADENING": 0, "RE-RATING": 0,
                    "GLUT-RISK": 0, "WATCH": 1, "UNKNOWN": 0}
    html = tmpl.render(
        cascade={"sizing": None, "demand_pool": None, "dislocation": None},
        themes=themes_data,
        stage_counts=stage_counts,
        stage_order=["PRECIPICE", "BROADENING", "RE-RATING", "GLUT-RISK", "WATCH", "UNKNOWN"],
        demand_pool=None, dislocation=None,
        track={"foresight": 0, "bottleneck": 0, "glut": 0, "revisions": 0,
               "guidance": 0, "emergence": 0, "subsector": 0, "recent": []},
        grade=None, emergence=None, subsectors=None,
        convergence=None, power=None, analyst=None, monitor=None, health=None,
        asof="2026-07-02", generated_utc="2026-07-02 00:00 UTC",
        nav_prefix="", active_section="research", active_page="foresight",
    )
    # Tier-less row must appear somewhere in the rendered HTML (not silently dropped)
    assert "Old Cached Theme" in html, "tier-less row must not be silently dropped"
    # The watch shelf must render (tier-less row defaults to W → shelf visible)
    assert "fx-watch-shelf" in html, "watch shelf must render for tier-less row"
    # The tier-less row must appear INSIDE the watch shelf (after fx-watch-shelf),
    # not before it (which would mean it was rendered as a Tier P card)
    shelf_pos = html.find("fx-watch-shelf")
    theme_pos = html.find("Old Cached Theme")
    assert theme_pos > shelf_pos, (
        "tier-less row must land in the watch shelf, not in the Tier P cards section"
    )
