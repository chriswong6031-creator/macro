"""Smoke + invariant tests for the China deterministic market-driver attribution leaf.

Mirrors tests/test_market_drivers.py, adapted to the China driver set and the
China audit-log path. DISPLAY-ONLY invariant is asserted structurally (the module
must not be importable into the scoring path — see test below)."""
from __future__ import annotations

import pandas as pd

from engine import china_market_drivers as md


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


def test_snapshot_has_same_shape_as_us_module():
    """The China card clones the US template, so the snapshot must carry the same
    keys (so a template clone is trivial)."""
    s = md.snapshot()
    if s["verdict"] == "unknown":
        return
    expected = {
        "asof", "window_d", "verdict", "verdict_zh", "primary", "primary_label",
        "primary_label_zh", "direction", "direction_zh", "dir_sign", "confidence",
        "confidence_zh", "strength", "dominance_ratio", "agreement", "runner_up",
        "runner_up_label", "runner_up_label_zh", "headline", "evidence",
        "evidence_legs", "invalidation", "invalidation_zh", "scores", "note",
    }
    assert expected <= set(s)


def test_fingerprints_are_well_formed():
    for name, spec in md.DRIVERS.items():
        assert spec["legs"], f"{name} has no legs"
        assert spec["label"] and spec["pos"] and spec["neg"] and spec["family"]
        for col, mtype, sign, w, lw in spec["legs"]:
            assert mtype in {"d", "p"}, (name, col)
            # China fingerprints use fractional canonical signs (e.g. +0.6) for
            # secondary-confirmation legs, unlike the US ±1-only set.
            assert sign > 0 or sign < 0, (name, col)
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
    clear["china_stimulus"] = [2.0] * 3
    vc = md.classify_day(clear, empty_raw, idx[-1])
    assert vc["verdict"] == "clear" and vc["primary"] == "china_stimulus"
    assert vc["dir_sign"] == 1


def test_gates_mixed_when_two_drivers_tie():
    """Two near-equal leaders → 'mixed' (neither clears the dominance ratio)."""
    idx = pd.bdate_range("2022-01-01", periods=3)
    empty_raw = {d: {} for d in md.DRIVERS}
    mixed = pd.DataFrame({d: [0.0] * 3 for d in md.DRIVERS}, index=idx)
    mixed["pboc_repricing"] = [2.0] * 3
    mixed["cny_shock"] = [1.9] * 3          # ratio 2.0/1.9 ≈ 1.05 < 1.3
    vm = md.classify_day(mixed, empty_raw, idx[-1])
    assert vm["verdict"] == "mixed"
    assert vm["runner_up_label"] and vm["runner_up_label_zh"]


def test_unknown_when_no_projections():
    idx = pd.bdate_range("2022-01-01", periods=2)
    empty = pd.DataFrame({d: [float("nan")] * 2 for d in md.DRIVERS}, index=idx)
    v = md.classify_day(empty, {d: {} for d in md.DRIVERS}, idx[-1])
    assert v["verdict"] == "unknown"


def test_stimulus_fingerprint_is_picked_up():
    """Inject a sharp stimulus-tape move into a mild-noise frame; engine names it."""
    import numpy as np

    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2022-01-01", periods=400)
    frame = pd.DataFrame(
        {c: 100 + np.cumsum(rng.normal(0, 0.1, len(idx))) for c in md.NAMES},
        index=idx)
    # final week: CSI300, brokers, real estate, copper & rebar all rip together
    for col in ("510300.SS", "512880.SS", "512200.SS", "copper", "rebar", "iron_ore"):
        frame.loc[idx[-5:], col] *= 1.10
    proj_df, raw_z = md.projections(frame)
    v = md.classify_day(proj_df, raw_z, proj_df.dropna(how="all").index[-1])
    assert v["primary"] == "china_stimulus"
    assert v["dir_sign"] == 1                       # canonical "stimulus-on"


def test_projections_drop_missing_legs_and_renormalize():
    """A leg whose column is missing/all-NaN is simply dropped; the projection is
    still produced over the present legs (degrade-don't-crash)."""
    import numpy as np

    idx = pd.bdate_range("2022-01-01", periods=300)
    # only CSI300 present for the stimulus driver — others absent
    frame = pd.DataFrame({"510300.SS": 100 + np.cumsum(np.full(len(idx), 0.05))},
                         index=idx)
    proj_df, raw_z = md.projections(frame)
    assert "china_stimulus" in proj_df.columns
    assert list(raw_z["china_stimulus"].keys()) == ["510300.SS"]


def test_append_log_is_keep_first(tmp_path, monkeypatch):
    """The audit log appends one row per date (keep-first) and skips unknown reads."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    base = {"asof": "2026-01-02", "verdict": "clear", "primary": "china_stimulus",
            "direction": "x", "dir_sign": 1, "confidence": "high", "strength": 2.0,
            "dominance_ratio": 1.8, "evidence": ["a", "b"]}
    md.append_log(base)
    md.append_log({**base, "verdict": "mixed"})        # same date → ignored (keep-first)
    md.append_log({**base, "asof": "2026-01-03"})      # new date → appended
    md.append_log({"verdict": "unknown", "asof": "2026-01-04"})  # not logged

    df = pd.read_parquet(tmp_path / "china_regime" / "china_market_drivers_log.parquet")
    assert set(df["asof"]) == {"2026-01-02", "2026-01-03"}
    assert df[df["asof"] == "2026-01-02"]["verdict"].iloc[0] == "clear"
    assert df[df["asof"] == "2026-01-02"]["evidence"].iloc[0] == "a; b"


def test_display_only_invariant_not_in_scoring_path():
    """DISPLAY-ONLY: china_market_drivers must NOT be imported by the scoring engines
    (china_axes / china_regime / china_playbook). Guards the never-scored invariant."""
    import inspect

    from engine import china_regime, china_playbook
    for mod in (china_regime, china_playbook):
        src = inspect.getsource(mod)
        assert "china_market_drivers" not in src, (
            f"{mod.__name__} must not import the display-only market-drivers leaf")
