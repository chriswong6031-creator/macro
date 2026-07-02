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
