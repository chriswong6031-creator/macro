"""engine.foresight_cascade — the per-theme STAGE machine (T1 x T4). Verifies the stage
logic on the four canonical states and that it ranks by edge remaining (PRECIPICE first)
and degrades honestly when a tier is missing. W0a additions: _append_ledger logs ALL stages
with transition-dedup + heartbeat.
"""
from __future__ import annotations
import json

from engine import foresight_cascade as fc


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
