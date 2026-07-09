"""Smoke + invariant tests for the deterministic market-driver attribution leaf."""
from __future__ import annotations

import pandas as pd

from engine import market_drivers as md


def test_snapshot_smoke_returns_valid_verdict():
    s = md.snapshot()
    assert s["verdict"] in {"clear", "mixed", "quiet", "unknown"}
    if s["verdict"] == "unknown":
        return
    assert s["primary"] in md.DRIVERS
    assert s["confidence"] in {"low", "medium", "high"}
    assert s["dir_sign"] in {1, -1}
    assert isinstance(s["evidence"], list) and s["evidence"]
    assert s["headline"] and s["invalidation"]
    # bilingual + structured fields the macro card + AI brief read
    assert s["verdict_zh"] and s["primary_label_zh"] and s["direction_zh"]
    assert s["confidence_zh"] and s["invalidation_zh"]
    assert s["evidence_legs"] and all(
        e.get("en") and e.get("zh") and "z" in e for e in s["evidence_legs"])
    assert all(x.get("label_zh") for x in s["scores"])
    # scores are ranked by strength, descending
    strengths = [x["strength"] for x in s["scores"]]
    assert strengths == sorted(strengths, reverse=True)
    # repricing_coherence block is present and well-formed (W1-A)
    coh = s.get("repricing_coherence")
    assert coh is not None, "snapshot must include repricing_coherence"
    assert coh["state"] in {"QUIET", "ELEVATED", "SHOCK"}
    assert 0 <= coh["score"] <= 100
    assert coh["state_zh"] in {"平静", "偏高", "冲击"}
    comps = coh["components"]
    assert set(comps) == {"driver_flip", "strength_extreme", "absorption_spike", "repricing_breadth"}
    assert all(v in (0, 20, 25, 30) for v in comps.values())


def test_fingerprints_are_well_formed():
    for name, spec in md.DRIVERS.items():
        assert spec["legs"], f"{name} has no legs"
        assert spec["label"] and spec["pos"] and spec["neg"] and spec["family"]
        for col, mtype, sign, w, lw in spec["legs"]:
            assert mtype in {"d", "p"}, (name, col)
            assert sign in {1, -1}, (name, col)
            assert w > 0, (name, col)
            assert lw is None or lw > 0, (name, col)
            assert col in md.NAMES, f"{col} missing an English display name"
            assert col in md.NAMES_ZH, f"{col} missing a Chinese display name"
        assert name in md.DRIVERS_ZH, f"{name} missing Chinese label/pos/neg"
        assert len(md.DRIVERS_ZH[name]) == 3
        assert spec["family"] in md.FAMILY_ZH, spec["family"]


def test_history_runs_and_is_dated():
    h = md.history(5)
    assert 1 <= len(h) <= 5
    assert all("asof" in r and "verdict" in r for r in h)


def test_gates_quiet_and_clear():
    """Small projections everywhere → 'quiet'; one driver clearly ahead → 'clear'."""
    idx = pd.bdate_range("2022-01-01", periods=3)
    empty_raw = {d: {} for d in md.DRIVERS}

    quiet = pd.DataFrame({d: [0.1] * 3 for d in md.DRIVERS}, index=idx)
    vq = md.classify_day(quiet, empty_raw, idx[-1])
    assert vq["verdict"] == "quiet"

    clear = pd.DataFrame({d: [0.0] * 3 for d in md.DRIVERS}, index=idx)
    clear["real_rate_shock"] = [2.0] * 3
    vc = md.classify_day(clear, empty_raw, idx[-1])
    assert vc["verdict"] == "clear" and vc["primary"] == "real_rate_shock"
    assert vc["dir_sign"] == 1


def test_real_rate_fingerprint_is_picked_up():
    """Inject a sharp real-rate shock into a mild-noise frame; engine should name it."""
    import numpy as np

    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2022-01-01", periods=400)
    frame = pd.DataFrame(
        {c: 100 + np.cumsum(rng.normal(0, 0.1, len(idx))) for c in md.NAMES},
        index=idx)
    # final week: 10y real yield spikes, gold & long-duration equity fall
    frame.loc[idx[-5:], "us10y_real"] += 1.5
    frame.loc[idx[-5:], "gold"] *= 0.90
    frame.loc[idx[-5:], "growth_value"] *= 0.92
    frame.loc[idx[-5:], "QQQ"] *= 0.93
    proj_df, raw_z = md.projections(frame)
    v = md.classify_day(proj_df, raw_z, proj_df.dropna(how="all").index[-1])
    assert v["primary"] == "real_rate_shock"
    assert v["dir_sign"] == 1                       # canonical "real yields rising"


def test_append_log_is_keep_first(tmp_path, monkeypatch):
    """The audit log appends one row per date (keep-first) and skips unknown reads."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    base = {"asof": "2026-01-02", "verdict": "clear", "primary": "oil_shock",
            "direction": "x", "dir_sign": 1, "confidence": "high", "strength": 2.0,
            "dominance_ratio": 1.8, "absorption_pctile": 0.7, "evidence": ["a", "b"]}
    md.append_log(base)
    md.append_log({**base, "verdict": "mixed"})        # same date → ignored (keep-first)
    md.append_log({**base, "asof": "2026-01-03"})      # new date → appended
    md.append_log({"verdict": "unknown", "asof": "2026-01-04"})  # not logged

    df = pd.read_parquet(tmp_path / "regime" / "market_drivers_log.parquet")
    assert set(df["asof"]) == {"2026-01-02", "2026-01-03"}
    assert df[df["asof"] == "2026-01-02"]["verdict"].iloc[0] == "clear"
    assert df[df["asof"] == "2026-01-02"]["evidence"].iloc[0] == "a; b"


# ---------------------------------------------------------------------------
# repricing_coherence unit tests (W1-A)
# ---------------------------------------------------------------------------

def _make_snap(primary="oil_shock", strength=1.5, absorption=0.92,
               asof="2026-03-10", verdict="clear", scores=None):
    """Build a minimal classify_day-style snap dict for coherence tests."""
    if scores is None:
        scores = [{"driver": d, "projection": 0.1} for d in md.DRIVERS]
    return {
        "asof": asof, "verdict": verdict, "primary": primary,
        "strength": strength, "absorption_pctile": absorption,
        "scores": scores,
    }


def _make_log(*rows):
    """Build a minimal log DataFrame from (asof, primary, strength) tuples."""
    return pd.DataFrame([
        {"asof": r[0], "primary": r[1], "strength": float(r[2])} for r in rows
    ])


# --- component: driver_flip ---

def test_driver_flip_fires_when_primary_changes():
    log = _make_log(("2026-03-09", "fed_repricing", 1.2))
    snap = _make_snap(primary="oil_shock", strength=1.1, asof="2026-03-10")
    coh = md.repricing_coherence(snap, log_df=log)
    assert coh["components"]["driver_flip"] == 30, "flip should score 30 when primary changes"


def test_driver_flip_zero_when_primary_unchanged():
    log = _make_log(("2026-03-09", "oil_shock", 1.2))
    snap = _make_snap(primary="oil_shock", strength=1.1, asof="2026-03-10")
    coh = md.repricing_coherence(snap, log_df=log)
    assert coh["components"]["driver_flip"] == 0


def test_driver_flip_zero_when_strength_too_low():
    """min(today, prev) must both be >= 1.0 for a flip to score."""
    log = _make_log(("2026-03-09", "fed_repricing", 0.8))
    snap = _make_snap(primary="oil_shock", strength=1.5, asof="2026-03-10")
    coh = md.repricing_coherence(snap, log_df=log)
    assert coh["components"]["driver_flip"] == 0


def test_driver_flip_zero_with_empty_log():
    snap = _make_snap(primary="oil_shock", strength=1.5, asof="2026-03-10")
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["components"]["driver_flip"] == 0


# --- component: strength_extreme ---

def test_strength_extreme_fallback_fires_at_2x():
    """With < 40 log rows the fallback threshold is 2.0."""
    log = _make_log(*[("2026-0{}-01".format(i), "oil_shock", 1.0) for i in range(1, 5)])
    snap = _make_snap(strength=2.1, asof="2026-06-01")
    coh = md.repricing_coherence(snap, log_df=log)
    assert coh["components"]["strength_extreme"] == 25


def test_strength_extreme_fallback_zero_below_2x():
    log = _make_log(*[("2026-0{}-01".format(i), "oil_shock", 1.0) for i in range(1, 5)])
    snap = _make_snap(strength=1.9, asof="2026-06-01")
    coh = md.repricing_coherence(snap, log_df=log)
    assert coh["components"]["strength_extreme"] == 0


def test_strength_extreme_p95_with_40_plus_rows():
    """With >= 40 log rows use actual p95."""
    import numpy as np
    rows = [("2026-{:02d}-01".format(i % 12 + 1), "oil_shock", 1.0) for i in range(50)]
    log = pd.DataFrame([{"asof": r[0], "primary": r[1], "strength": r[2]} for r in rows])
    # p95 of 50 rows of 1.0 = 1.0; a strength of 1.01 should just pass
    snap = _make_snap(strength=1.01, asof="2026-13-01")  # asof > all log rows
    coh = md.repricing_coherence(snap, log_df=log)
    assert coh["components"]["strength_extreme"] == 25


# --- component: absorption_spike ---

def test_absorption_spike_fires_at_90pct():
    snap = _make_snap(absorption=0.90)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["components"]["absorption_spike"] == 20


def test_absorption_spike_zero_below_90pct():
    snap = _make_snap(absorption=0.89)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["components"]["absorption_spike"] == 0


def test_absorption_spike_zero_when_none():
    snap = _make_snap(absorption=None)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["components"]["absorption_spike"] == 0


# --- component: repricing_breadth ---

def test_repricing_breadth_fires_with_three_hot_families():
    """3 distinct families with |proj| >= 1.5 → 25 pts."""
    scores = [
        {"driver": "fed_repricing", "projection": 1.6},    # rates
        {"driver": "oil_shock", "projection": -1.7},        # inflation
        {"driver": "ai_semis", "projection": 1.8},          # equity-leadership
        {"driver": "usd_shock", "projection": 0.5},         # fx (below threshold)
    ]
    snap = _make_snap(scores=scores)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["components"]["repricing_breadth"] == 25


def test_repricing_breadth_zero_with_two_hot_families():
    """Only 2 families hot → 0 pts."""
    scores = [
        {"driver": "fed_repricing", "projection": 1.6},  # rates
        {"driver": "oil_shock", "projection": -1.7},      # inflation
        {"driver": "usd_shock", "projection": 0.5},       # fx (below threshold)
    ]
    snap = _make_snap(scores=scores)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["components"]["repricing_breadth"] == 0


def test_repricing_breadth_deduplicates_same_family():
    """Two rates drivers don't count as two families."""
    scores = [
        {"driver": "fed_repricing", "projection": 2.0},   # rates
        {"driver": "real_rate_shock", "projection": 2.0},  # rates (same family)
        {"driver": "oil_shock", "projection": 2.0},        # inflation
    ]
    snap = _make_snap(scores=scores)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    # only 2 distinct families → 0 pts
    assert coh["components"]["repricing_breadth"] == 0


# --- state thresholds ---

def test_state_quiet_below_40():
    """Score < 40 → QUIET."""
    # absorption only = 20 pts
    snap = _make_snap(absorption=0.95, strength=0.5)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["state"] == "QUIET"
    assert coh["score"] == 20


def test_state_elevated_40_to_69():
    """Score 40-69 → ELEVATED."""
    # absorption (20) + breadth (25) = 45
    scores = [
        {"driver": "fed_repricing", "projection": 1.6},
        {"driver": "oil_shock", "projection": -1.7},
        {"driver": "ai_semis", "projection": 1.8},
    ]
    snap = _make_snap(absorption=0.95, strength=0.5, scores=scores)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["state"] == "ELEVATED"
    assert 40 <= coh["score"] < 70


def test_state_shock_at_70_plus():
    """Score >= 70 → SHOCK."""
    # flip (30) + extreme (25) + absorption (20) = 75
    log = _make_log(("2026-03-09", "fed_repricing", 1.5))
    snap = _make_snap(primary="oil_shock", strength=2.1, absorption=0.95,
                      asof="2026-03-10")
    coh = md.repricing_coherence(snap, log_df=log)
    assert coh["state"] == "SHOCK"
    assert coh["score"] >= 70


# --- bilingual fields ---

def test_coherence_has_bilingual_fields():
    snap = _make_snap(absorption=0.95)
    coh = md.repricing_coherence(snap, log_df=pd.DataFrame())
    assert coh["state_zh"] in ("平静", "偏高", "冲击")
    assert coh["note"] and coh["note_zh"]


# --- defensive / degrade ---

def test_coherence_degrades_on_unknown_snap():
    coh = md.repricing_coherence({"verdict": "unknown"}, log_df=pd.DataFrame())
    assert coh["state"] == "QUIET"
    assert coh["score"] == 0


def test_coherence_never_raises_on_garbage_input():
    for bad in [None, {}, {"verdict": None}, {"verdict": "clear", "scores": "bad"}]:
        result = md.repricing_coherence(bad or {}, log_df=pd.DataFrame())
        assert "state" in result  # always returns a valid dict


# --- append_log PS-R7 guard ---

def test_append_log_allow_write_false_does_nothing(tmp_path, monkeypatch):
    """allow_write=False must prevent any file creation (intraday guard)."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    snap = {"asof": "2026-03-10", "verdict": "clear", "primary": "oil_shock",
            "direction": "x", "dir_sign": 1, "confidence": "high", "strength": 1.5,
            "dominance_ratio": 1.5, "absorption_pctile": 0.8, "evidence": []}
    md.append_log(snap, allow_write=False)
    p = tmp_path / "regime" / "market_drivers_log.parquet"
    assert not p.exists(), "allow_write=False must not write the parquet ledger"


def test_append_log_coherence_columns_written(tmp_path, monkeypatch):
    """append_log with a coherence block writes coherence_score + coherence_state."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    snap = {"asof": "2026-03-10", "verdict": "clear", "primary": "oil_shock",
            "direction": "x", "dir_sign": 1, "confidence": "high", "strength": 1.5,
            "dominance_ratio": 1.5, "absorption_pctile": 0.8, "evidence": [],
            "repricing_coherence": {"score": 55, "state": "ELEVATED"}}
    md.append_log(snap)
    df = pd.read_parquet(tmp_path / "regime" / "market_drivers_log.parquet")
    assert "coherence_score" in df.columns
    assert "coherence_state" in df.columns
    assert df["coherence_score"].iloc[0] == 55
    assert df["coherence_state"].iloc[0] == "ELEVATED"


def test_append_log_reads_old_log_without_coherence_columns(tmp_path, monkeypatch):
    """Existing rows without coherence columns must not break reads (None-safe)."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    # Write an old-style log (no coherence cols)
    old_p = tmp_path / "regime"
    old_p.mkdir(parents=True)
    old_df = pd.DataFrame([{
        "asof": "2026-01-10", "verdict": "clear", "primary": "oil_shock",
        "direction": "x", "dir_sign": 1, "confidence": "high", "strength": 1.5,
        "dominance_ratio": 1.4, "absorption_pctile": 0.9, "evidence": "a",
    }])
    old_df.to_parquet(old_p / "market_drivers_log.parquet", index=False)

    # Now append a new row with coherence — must not crash
    snap = {"asof": "2026-01-11", "verdict": "mixed", "primary": "fed_repricing",
            "direction": "y", "dir_sign": -1, "confidence": "low", "strength": 1.2,
            "dominance_ratio": 1.1, "absorption_pctile": 0.85, "evidence": [],
            "repricing_coherence": {"score": 30, "state": "QUIET"}}
    md.append_log(snap)
    df = pd.read_parquet(old_p / "market_drivers_log.parquet")
    assert len(df) == 2
    # coherence_score for old row will be NaN (None-safe concat)
    assert pd.isna(df[df["asof"] == "2026-01-10"]["coherence_score"].iloc[0])
    assert df[df["asof"] == "2026-01-11"]["coherence_score"].iloc[0] == 30


# --- regression against committed log fixture ---

def test_regression_committed_log_0707_or_0708_elevated_or_shock():
    """At least one of 2026-07-07 / 2026-07-08 from the committed log must score
    ELEVATED or SHOCK when repricing_coherence is computed from the log's own columns.
    This anchors the component math to real observed data."""
    import numpy as np

    df = pd.read_parquet(
        "data/regime/market_drivers_log.parquet"
    )

    results = {}
    for asof in ("2026-07-07", "2026-07-08"):
        row = df[df["asof"] == asof]
        if row.empty:
            continue
        r = row.iloc[0]
        strength = float(r["strength"])
        ar = r.get("absorption_pctile")
        absorption = float(ar) if pd.notna(ar) else None

        # build a minimal snap from log columns (no full scores dict → breadth = 0)
        snap = {
            "asof": asof,
            "verdict": r.get("verdict", "clear"),
            "primary": r.get("primary"),
            "strength": strength,
            "absorption_pctile": absorption,
            "scores": [],  # no scores in log; breadth component = 0
        }
        # log rows strictly before this asof
        log_before = df[df["asof"].astype(str) < asof]
        coh = md.repricing_coherence(snap, log_df=log_before)
        results[asof] = coh
        print(f"{asof}: score={coh['score']} state={coh['state']} "
              f"components={coh['components']}")

    states = {asof: r["state"] for asof, r in results.items()}
    assert any(s in ("ELEVATED", "SHOCK") for s in states.values()), (
        f"Expected at least one ELEVATED/SHOCK in 2026-07-07/08, got: {states}"
    )
