"""flip_distance — the display-only distance-to-label-change meter (engine.theme_scoring).

The meter is pure arithmetic over the SAME literals _label() reads, so the core contract is
RECONSTRUCTION: for synthetic inputs where delta_5d sweeps across the rollover-guard threshold
(-0.015) with every other guard leg true, the label flips to "fading" EXACTLY when route_a_bps
crosses 0 — the meter can never disagree with the validated label logic. Also covers the
blocked-leg (None) behaviour, route B arithmetic, the descriptive note wording, and — when the
price caches are present — the act_now clean-entry split (split visibly, never hidden).
No network; everything below the integration smoke is driven by tiny in-memory fixtures.
"""
from __future__ import annotations

from engine import theme_scoring as ts


def _fp(accel=0.0, rs=0.5):
    return {"accel_z": accel, "rs_pctile": rs}


# all other rollover-guard legs TRUE: net_nh<=0 (nh==nl==0), score>=62, mom_pos (r20>0),
# breadth_ok (pct50>=.5 and net_nh>=0), not long_dn (no mtf / long_sign)
_PERF = {"5d": {"rel": None}, "20d": {"rel": 0.05}, "60d": {"rel": 0.08}}
_BREADTH = {"pct50": 0.7, "nh": 0, "nl": 0}


def _label_and_meter(d5):
    perf = {**_PERF, "5d": {"rel": d5}}
    label = ts._label(70, _fp(), perf, _BREADTH, d5)
    fd = ts._flip_distance(70, _fp(), perf, _BREADTH, d5)
    return label, fd


# ------------------------------------------------ the reconstruction contract
def test_meter_reconstructs_the_rollover_guard_exactly():
    # sweep the 5d relative across the -1.5% guard: label=="fading" <=> route_a_bps<=0
    for d5 in (-0.001, -0.005, -0.010, -0.0149, -0.015, -0.0151, -0.020, -0.030):
        label, fd = _label_and_meter(d5)
        assert fd["route_a_bps"] is not None            # other guard legs are all true
        fired = fd["route_a_bps"] <= 0
        assert (label == "fading") == fired, f"meter disagrees with _label at d5={d5}"


def test_route_a_is_pure_distance_arithmetic():
    _, fd = _label_and_meter(-0.010)
    assert fd["route_a_bps"] == 50.0                    # (-0.010 + 0.015) * 10000
    _, fd = _label_and_meter(0.002)                     # not falling yet: distance through 0
    assert fd["route_a_bps"] == 170.0                   # (0.002 + 0.015) * 10000
    # sessions estimate comes only from the trailing realized daily relative move (|5d|/5)
    _, fd = _label_and_meter(-0.010)
    assert fd["route_a_sessions_est"] == 2              # 50 bps at ~20 bps/day -> ~2 sessions


def test_route_a_none_when_other_guard_legs_block():
    # net new highs positive -> the guard cannot fire regardless of delta_5d -> None,
    # and _label agrees (stays dominant even beyond the -1.5% threshold)
    breadth = {"pct50": 0.7, "nh": 5, "nl": 0}
    label = ts._label(70, _fp(), {**_PERF, "5d": {"rel": -0.02}}, breadth, -0.02)
    fd = ts._flip_distance(70, _fp(), {**_PERF, "5d": {"rel": -0.02}}, breadth, -0.02)
    assert label == "dominant"
    assert fd["route_a_bps"] is None
    # score below the guard's 62 floor also blocks route A
    fd = ts._flip_distance(55, _fp(), {**_PERF, "5d": {"rel": -0.02}}, _BREADTH, -0.02)
    assert fd["route_a_bps"] is None


def test_route_b_is_r20_in_pp_and_nearest_route():
    _, fd = _label_and_meter(-0.010)
    assert fd["route_b_pp"] == 5.0                      # 0.05 * 100
    # 50 bps (route A) < 500 bps (route B) -> A is the nearest gap
    assert fd["nearest_route"] == "a"
    # with route A blocked, the only positive gap left is B
    fd = ts._flip_distance(55, _fp(), _PERF, _BREADTH, -0.001)
    assert fd["nearest_route"] == "b"


def test_notes_are_bilingual_and_descriptive_never_forward():
    for d5 in (-0.010, -0.020):
        _, fd = _label_and_meter(d5)
        assert fd["note_en"] and fd["note_zh"]
        assert "not a forecast" in fd["note_en"]        # the standing honesty tag
        assert "非预测" in fd["note_zh"]
        for verb in ("will ", "about to", "is going to"):
            assert verb not in fd["note_en"].lower()    # no forward verbs


def test_flip_distance_none_delta_matches_label_coalescing():
    # _label coalesces a None delta_5d to 0.0; the meter must use the same literal
    label = ts._label(70, _fp(), {**_PERF, "5d": {"rel": None}}, _BREADTH, None)
    fd = ts._flip_distance(70, _fp(), {**_PERF, "5d": {"rel": None}}, _BREADTH, None)
    assert label == "dominant"
    assert fd["route_a_bps"] == 150.0                   # (0.0 + 0.015) * 10000
    assert fd["route_a_sessions_est"] is None           # flat pace -> no session estimate


# --------------------------------------------------------------- integration smoke
def test_payload_carries_flip_distance_and_honest_act_now_split(tmp_path, monkeypatch):
    from engine import basket_breadth_divergence as bd

    # compute_theme_intel stamps elevated/high breadth-divergence textures into
    # the forward accountability log as a side effect — redirect the stamp to
    # tmp so real caches are read but data/breadth_divergence/ is never written.
    monkeypatch.setattr(bd, "_log_path", lambda: tmp_path / "forward_log.parquet")
    ti = ts.compute_theme_intel()
    if ti is None:                                      # caches absent in CI shard
        return
    for th in ti["themes"]:
        fd = th.get("flip_distance")
        assert fd is not None
        assert set(fd) >= {"route_a_bps", "route_b_pp", "nearest_route", "note_en", "note_zh"}
    an = ti["act_now"]
    assert set(an) >= {"buy", "add_on_pullback", "reduce"}
    # SPLIT, NEVER HIDDEN: buy ∪ add_on_pullback == every constructive-reco theme
    constructive = {t["id"] for t in ti["themes"] if t["reco"] in ("enter", "accumulate")}
    assert {x["id"] for x in an["buy"]} | {x["id"] for x in an["add_on_pullback"]} == constructive
    for x in an["buy"]:
        assert x["clean_entry"] is True                 # the section copy's promise, now true
    for x in an["add_on_pullback"]:
        assert x["clean_entry"] is False
        assert x["reason_en"] and x["reason_zh"]        # carries the honest bilingual reason
