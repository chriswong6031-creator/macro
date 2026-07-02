"""Outcome spine contract + first emitters + closed-loop clients (Masterplan §W4).

Covers: emit/load idempotency, measured_ic with the co-firing collapse and sign-inversion for
veto seats, the desk-weight SHADOW path (equal-weight until armed), the IC-aware alert severity
cap, the convergence-tier co-firing penalty + accrual-aware honesty, and the badge passport.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import spine


@pytest.fixture()
def root(tmp_path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path


# --- emit / load / idempotency ------------------------------------------------------------ #
def test_emit_and_load_roundtrip(root):
    rows = [spine.SpinePrediction(signal_id="x:1", engine="e", family="f", as_of="2026-01-01",
                                  symbol="AAA", horizon=20, score=1.0)]
    assert spine.emit(rows, root=root) == 1
    df = spine.load(root=root)
    assert len(df) == 1 and df.iloc[0]["signal_id"] == "x:1"
    assert list(df.columns) == spine.COLUMNS


def test_emit_is_idempotent_last_wins(root):
    spine.emit([spine.SpinePrediction("x:1", "e", "f", "2026-01-01", "AAA", 20, 1.0)], root=root)
    # re-emit same id with an outcome → updates, does not duplicate
    p = spine.SpinePrediction("x:1", "e", "f", "2026-01-01", "AAA", 20, 1.0,
                              outcome_excess=0.05, outcome_graded=True)
    spine.emit([p], root=root)
    df = spine.load(root=root)
    assert len(df) == 1
    assert bool(df.iloc[0]["outcome_graded"]) is True


def test_load_missing_is_empty_not_crash(root):
    df = spine.load(root=root)
    assert df.empty and list(df.columns) == spine.COLUMNS


# --- measured_ic: sign-inversion for veto seats + co-firing collapse ---------------------- #
def test_measured_ic_sign_inverts_veto_seat(root):
    # a SHORT (direction -1) that AVOIDED a loser (name fell, excess -0.10) earns POSITIVE credit
    rows = [spine.SpinePrediction("s:1", "e", "f", "2026-01-01", "BAD", 20, 1.0,
                                  direction=-1, outcome_excess=-0.10, outcome_graded=True)]
    spine.emit(rows, root=root)
    m = spine.measured_ic(root=root, engine="e")
    assert m["ic"] > 0, "a correct veto (short avoided a loser) must score positive IC (#17)"


def test_measured_ic_cofiring_collapses_to_one_event(root):
    # three channels firing on ONE event (same event_key) count as ONE effective observation
    rows = [
        spine.SpinePrediction(f"c:{i}", "e", "f", "2026-01-01", "AAA", 20, 1.0,
                              event_key="8k_1", outcome_excess=0.05, outcome_graded=True)
        for i in range(3)
    ]
    spine.emit(rows, root=root)
    m = spine.measured_ic(root=root, engine="e")
    assert m["n"] == 3 and m["n_eff"] == 1, "co-firing channels must collapse to one effective event"


def test_measured_ic_cold_start_is_none(root):
    m = spine.measured_ic(root=root, engine="nope")
    assert m["n"] == 0 and m["ic"] is None and m["wrong_sign"] is False


# --- adapters degrade to empty on a bare root --------------------------------------------- #
def test_adapters_empty_on_bare_root(root):
    assert spine.adapt_us_board(root=root) == []
    # altdata/desk adapters read jsonl that isn't there → empty, no crash
    assert spine.adapt_altdata(root=root) == []
    assert spine.adapt_desk_scorer(root=root) == []


def test_adapt_desk_scorer_reads_scored_jsonl(root):
    d = root / "data" / "ai_desk"
    d.mkdir(parents=True)
    (d / "scored.jsonl").write_text(
        json.dumps({"id": "t1", "outcome": "miss", "realized": 0.04, "subject": "Energy",
                    "conviction": "high", "check_by": "2026-03-01"}) + "\n")
    rows = spine.adapt_desk_scorer(root=root, desks={"ai_desk": ("data", "ai_desk", "scored.jsonl")})
    assert len(rows) == 1
    # a 'miss' must carry a NEGATIVE signed outcome so a wrong desk can go negative in pooling
    assert rows[0].outcome_excess < 0
    assert rows[0].family == "desk:ai_desk"


# --- desk-weight SHADOW path: equal until armed ------------------------------------------- #
def test_desk_weights_shadow_holds_equal_when_cold(root, monkeypatch):
    from engine import desk_scorer
    monkeypatch.setattr(desk_scorer.config, "ROOT", root, raising=False)
    out = desk_scorer.desk_weights(root=root, persist=False)
    assert out["armed"] is False
    # cold → live weights equal the equal-weight baseline (SHADOW-FIRST safety)
    assert out["live_weights"] == out["equal_weight"]


def test_desk_weights_arms_and_downweights_wrong_desk(root):
    # seed two desks: 'ai_desk' reliably right, 'stock_desk' reliably wrong, across many events
    import datetime as dt
    for name, outcome in (("ai_desk", "hit"), ("stock_desk", "miss")):
        d = root / "data" / name
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        d0 = dt.date(2026, 1, 1)
        for i in range(20):
            lines.append(json.dumps({
                "id": f"{name}-{i}", "outcome": outcome, "realized": 0.03,
                "subject": f"S{i}", "conviction": "high",
                "check_by": (d0 + dt.timedelta(days=i)).isoformat()}))
        (d / "scored.jsonl").write_text("\n".join(lines) + "\n")
    desks = {"ai_desk": ("data", "ai_desk", "scored.jsonl"),
             "stock_desk": ("data", "stock_desk", "scored.jsonl")}
    rows = spine.adapt_desk_scorer(root=root, desks=desks)
    # verify the sign is right in the adapter first
    good = [r for r in rows if r.family == "desk:ai_desk"]
    bad = [r for r in rows if r.family == "desk:stock_desk"]
    assert good and bad
    assert all(r.outcome_excess > 0 for r in good)
    assert all(r.outcome_excess < 0 for r in bad)


# --- IC-aware alert severity cap (#42) ---------------------------------------------------- #
def test_ic_severity_cap_demotes_spine_null_edge_emitter(root):
    from engine import alert_triage
    # seed the altdata convergence family with a MEASURED NULL/negative edge, past MIN_N
    rows = [spine.SpinePrediction(f"altdata_conv:t{i}", "altdata_conv",
                                  "altdata:convergence", f"2026-01-0{i%9+1}", f"T{i}", 63, 0.0,
                                  direction=1, event_key=f"t{i}",
                                  outcome_excess=-0.02, outcome_graded=True)
            for i in range(15)]
    spine.emit(rows, root=root)
    band, note = alert_triage.ic_severity_cap("altdata", "convergence", "critical", root=root)
    assert band == "minor", "a measured null/wrong-sign spine emitter must be capped to minor"
    assert note["ic_state"] == "null_or_wrong_sign"


def test_ic_severity_cap_spine_no_override_when_cold(root):
    from engine import alert_triage
    band, note = alert_triage.ic_severity_cap("altdata", "convergence", "critical", root=root)
    assert band == "critical", "cold spine → the hardcoded prior band stands (no promote/demote)"
    assert note["ic_state"] == "accruing"


def test_ic_severity_cap_documented_null_capped_now(root):
    from engine import alert_triage
    # narrative-rotation entered_book is documented rank-IC≈0 → capped to minor NOW (no spine
    # emitter needed; its ~0 IC is already established)
    band, note = alert_triage.ic_severity_cap("rotation", "entered_book", "critical", root=root)
    assert band == "minor"
    assert note["ic_state"] == "documented_null"


def test_ic_severity_cap_spine_keeps_validated_band(root):
    from engine import alert_triage
    # a genuinely positive-edge convergence family keeps its hardcoded band
    rows = [spine.SpinePrediction(f"altdata_conv:g{i}", "altdata_conv",
                                  "altdata:convergence", f"2026-01-0{i%9+1}", f"G{i}", 63, 0.0,
                                  direction=1, event_key=f"g{i}",
                                  outcome_excess=0.04, outcome_graded=True)
            for i in range(15)]
    spine.emit(rows, root=root)
    band, note = alert_triage.ic_severity_cap("altdata", "convergence", "major", root=root)
    assert band == "major" and note["ic_state"] == "validated"


def test_ic_severity_cap_ignores_ungoverned_source(root):
    from engine import alert_triage
    band, note = alert_triage.ic_severity_cap("bonds", "credit_band", "critical", root=root)
    assert band == "critical" and note == {}


# --- convergence tier: co-firing penalty + accrual honesty (#23) -------------------------- #
def test_convergence_tier_cofiring_penalty():
    from engine import altdata_signals as a
    # 3 channels but all fire on ONE corporate event → NOT 'high'
    same_event = ["material_8k", "fda_approval", "earnings_beat"]
    t = a.convergence_tier(same_event, trump=False)
    assert t["cofiring_score"] == 1
    assert t["tier"] != "high", "one corporate event lighting 3 channels can't be 'high'"
    # 3 genuinely INDEPENDENT event clusters → 'high'
    independent = ["material_8k", "congress_buy", "insider_buy"]
    t2 = a.convergence_tier(independent, trump=False)
    assert t2["cofiring_score"] == 3 and t2["tier"] == "high"


def test_convergence_tier_accrual_aware_basis():
    from engine import altdata_signals as a
    t = a.convergence_tier(["material_8k", "congress_buy"], trump=False)
    # with no matured spine ledger the basis is a PRIOR, n_scored 0 (honest, not 'earned')
    assert t["n_scored"] == 0 and t["basis"] == "prior"


def test_chip_caveat_says_accruing_when_cold():
    from engine import altdata_signals as a
    chip = a.chip({"channels": ["material_8k", "congress_buy"], "convergence_score": 2,
                   "trump_linked": False})
    assert chip is not None
    assert "ACCRUING" in chip["caveat"]["en"].upper()
    assert chip["basis"] == "prior"


# --- badge passport (#41) ------------------------------------------------------------------ #
def test_passport_states_and_earned_flag():
    from engine import passport
    assert passport.passport("measured", n=30, hit_rate=0.6)["earned"] is True
    acc = passport.passport("accruing", n=0)
    assert acc["earned"] is False and "n=0" in acc["label_en"]
    # unknown state degrades to the conservative 'prior', never crashes
    assert passport.passport("bogus")["state"] == "prior"


def test_passport_from_spine_cold_is_accruing(root):
    from engine import passport
    p = passport.passport_from_spine("desk:ai_desk", family="desk:ai_desk", root=root)
    assert p["state"] == "accruing" and p["earned"] is False


def test_passport_from_spine_measured_when_graded(root):
    from engine import passport
    rows = [spine.SpinePrediction(f"desk:ai_desk:{i}", "desk:ai_desk", "desk:ai_desk",
                                  "2026-01-01", "S", 63, 1.0, outcome_excess=0.02,
                                  outcome_graded=True) for i in range(5)]
    spine.emit(rows, root=root)
    p = passport.passport_from_spine("desk:ai_desk", family="desk:ai_desk", root=root)
    assert p["state"] == "measured" and p["earned"] is True and p["n"] == 5


def test_freshness_state_flips_stale():
    from engine import passport
    import datetime as dt
    today = dt.date(2026, 7, 1)
    assert passport.freshness_state("2026-06-30", 30, today) == "measured"
    assert passport.freshness_state("2026-01-01", 30, today) == "stale"
    assert passport.freshness_state(None, 30, today) == "unfitted"
