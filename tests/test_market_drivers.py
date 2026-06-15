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
