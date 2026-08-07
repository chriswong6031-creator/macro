"""Wave-1.5 HAR-standardizer discriminator invariants (scripts/pick_forward_dist_phase1_har.py).

Fixture-only by construction, exactly like tests/test_pick_forward_dist.py: CI has no
massive_stock_day parquets, so every test here runs on synthetic OHLCV. What is pinned is
the part a results table cannot show —

  * CAUSALITY: the new standardizer must not move when FUTURE bars move. A multi-scale
    blend is a fresh chance to introduce a centred window or a forward fill.
  * PARITY WITH THE SHIPPED FORECASTER: the study's scale must be the house
    `engine.vol_forecast.har_vol`, lagged one bar and floored — pinned two ways, once
    against the module itself (composition: lag direction + floor) and once against an
    INDEPENDENT first-principles re-derivation of the blend (equal weight over HAR_LAGS,
    pct_change returns, ddof=0). The second is what makes the first non-vacuous: a change
    inside `har_vol` fails loudly instead of silently redefining the study's scale.
  * ROUND TRIP: a cone standardized on the HAR scale must come back to percent exactly,
    and the two routes the harness uses to build the HAR frame (direct re-standardization
    from raw percent for `ret`; exact scale-ratio conversion for `mae`/`mfe`) must agree.
  * IMPORT-SURFACE PIN: the phase-1 runner must REFUSE TO RUN when the phase-0 signatures
    or frozen constants it imports drift, so a later phase-0 refactor cannot silently
    change what this study measured. Pinned by mutation, not by assertion of the happy
    path alone.

Run: python3 -m tests.test_pick_forward_dist_phase1
     (or pytest tests/test_pick_forward_dist_phase1.py)
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from engine import pick_forward_dist as pfd  # noqa: E402
from engine import vol_forecast as vf  # noqa: E402
from scripts import pick_forward_dist_phase0 as p0  # noqa: E402
from scripts import pick_forward_dist_phase1_har as p1  # noqa: E402


# ------------------------------------------------------------------ fixtures
def _ohlcv(seed: int, n: int = 900, start: str = "2020-01-02", px0: float = 50.0) -> pd.DataFrame:
    """One synthetic name with regime-varying vol — the same generator shape as
    tests/test_pick_forward_dist.py, so the two suites exercise comparable panels."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    vol = 0.012 + 0.010 * np.abs(np.sin(np.linspace(0, 5.0 + seed % 3, n)))
    ret = rng.normal(0.0003, 1.0, n) * vol
    close = px0 * np.exp(np.cumsum(ret))
    span = np.abs(rng.normal(0.0, 1.0, n)) * vol * close
    return pd.DataFrame({
        "open": close * (1.0 + rng.normal(0, 0.002, n)),
        "high": close + span,
        "low": close - span,
        "close": close,
        "volume": rng.integers(1_500_000, 6_000_000, n).astype(float),
    }, index=idx)


def _frames(k: int = 8, **kw) -> dict:
    return {f"SYN{i:02d}": _ohlcv(seed=300 + i, **kw) for i in range(k)}


def _independent_har_blend(close: pd.Series, lags=(2, 5, 22, 66)) -> pd.Series:
    """First-principles re-derivation of the shipped blend — deliberately NOT calling
    engine.vol_forecast, so it can disagree with it. Equal-weight mean (NaN-skipping, as
    `pd.concat(...).mean(axis=1)` does) of trailing realized vol over `lags`, on simple
    pct_change returns with ddof=0 and the module's min_periods rule."""
    r = close.astype(float).pct_change(fill_method=None)
    comps = []
    for L in lags:
        w = max(2, int(L))
        comps.append(r.rolling(w, min_periods=min(w, max(2, w // 2))).std(ddof=0))
    return pd.concat(comps, axis=1).mean(axis=1)


# ------------------------------------------------------------------ (a) causality
def test_har_scale_is_causal_under_future_perturbation():
    """Perturbing every bar AFTER t must leave the HAR standardizer at and before t
    bit-identical. A centred window, a bfill, or a full-sample statistic fails here."""
    df = _ohlcv(seed=17)
    cut = df.index[600]
    base = p1.har_vol_scale(df["close"])

    poisoned = df.copy()
    fut = poisoned.index > cut
    poisoned.loc[fut, "close"] = poisoned.loc[fut, "close"] * 4.0
    after = p1.har_vol_scale(poisoned["close"])

    a, b = base.loc[:cut], after.loc[:cut]
    assert a.shape == b.shape and len(a) > 500
    diff = (a - b).abs().to_numpy()
    worst = float(np.nanmax(diff)) if diff.size else 0.0
    assert worst == 0.0, f"look-ahead: future bars moved a past HAR scale by {worst}"

    # And the lag is a LAG: the value at t must not read bar t's own return. Move bar t
    # alone and the scale at t must not budge, while the scale at t+1 must.
    j = df.index.get_loc(cut)
    nudged = df.copy()
    nudged.iloc[j, nudged.columns.get_loc("close")] *= 1.25
    n_scale = p1.har_vol_scale(nudged["close"])
    assert float(abs(n_scale.iloc[j] - base.iloc[j])) == 0.0, "the scale at t read bar t"
    assert float(abs(n_scale.iloc[j + 1] - base.iloc[j + 1])) > 0.0, \
        "the scale at t+1 ignored bar t — that is not a one-bar lag"
    print("ok test_har_scale_is_causal_under_future_perturbation")


# ------------------------------------------------------------------ (b) parity
def test_har_scale_matches_the_shipped_house_forecaster():
    """Two pins on one series. (1) COMPOSITION: the study's scale is exactly the shipped
    `vol_forecast.har_vol`, shifted one bar and clipped from below at VOL_FLOOR — the lag
    direction and the floor are what the composition can get wrong. (2) DEFINITION: an
    INDEPENDENT re-derivation of the blend must agree with the shipped function, so a
    change to `har_vol` (weights, lags, return convention, ddof) fails loudly here rather
    than silently redefining what wave-1.5 measured."""
    close = _ohlcv(seed=31, n=700)["close"]

    # (1) composition
    ref = vf.har_vol(close, vf.HAR_LAGS).shift(1).clip(lower=pfd.VOL_FLOOR)
    got = p1.har_vol_scale(close)
    j = pd.concat([ref.rename("ref"), got.rename("got")], axis=1)
    assert j["ref"].notna().sum() > 600, "fixture too short to test parity"
    worst = float((j["ref"] - j["got"]).abs().max())
    assert worst < 1e-12, f"standardizer diverged from the shipped forecaster by {worst}"

    # a wrong lag direction, or a dropped floor, must NOT pass the same check
    wrong_lag = vf.har_vol(close, vf.HAR_LAGS).shift(-1).clip(lower=pfd.VOL_FLOOR)
    assert float((wrong_lag - got).abs().max()) > 1e-9, "the composition pin is vacuous"

    # (2) definition, re-derived without touching engine.vol_forecast
    mine = _independent_har_blend(close, vf.HAR_LAGS)
    theirs = vf.har_vol(close, vf.HAR_LAGS)
    k = pd.concat([mine.rename("a"), theirs.rename("b")], axis=1).dropna()
    assert len(k) > 600
    dworst = float((k["a"] - k["b"]).abs().max())
    assert dworst < 1e-12, (
        f"engine.vol_forecast.har_vol no longer equals an equal-weight blend of realized "
        f"vol over HAR_LAGS={vf.HAR_LAGS} (max diff {dworst}). wave-1.5's standardizer is "
        "defined by that function — a change here changes what the study measured.")
    assert tuple(vf.HAR_LAGS) == (2, 5, 22, 66), vf.HAR_LAGS

    # a weighted blend is a DIFFERENT object — the definition pin must be able to see it
    weighted = pd.concat(
        [vf.realized_vol(close, L) * w for L, w in zip(vf.HAR_LAGS, (0.4, 0.3, 0.2, 0.1))],
        axis=1).sum(axis=1)
    assert float((weighted - theirs).abs().max()) > 1e-6, "the definition pin is vacuous"

    # the floor must actually bind: a flat series cannot manufacture sigma-scale outcomes
    flat = pd.Series(20.0, index=pd.bdate_range("2021-01-04", periods=400))
    assert float(p1.har_vol_scale(flat).dropna().min()) >= pfd.VOL_FLOOR
    print(f"ok test_har_scale_matches_the_shipped_house_forecaster (max diff {worst:.2e})")


# ------------------------------------------------------------------ (c) round trip
def test_har_standardization_round_trip_and_frame_arithmetic():
    """The new standardization must be an exact inverse of `rescale_cone` at a fixed
    scale, and the two routes the harness uses to build the HAR frame must agree.

    AM-H5: `z_ret` is re-standardized DIRECTLY from raw percent, while `z_mae`/`z_mfe`
    are converted by the exact scale ratio because the panel carries no raw column for
    them. If those routes ever disagree, the mae/mfe half of the HAR frame is wrong and
    nothing downstream would notice."""
    df = _ohlcv(seed=41, n=500)
    h = 21
    paths = pfd.forward_paths(df["close"], h)
    scale = 0.017
    z = pfd.standardize_paths(paths, pd.Series(scale, index=df.index), h)
    cone = pfd.empirical_cone(z["ret"].dropna().to_numpy(), z["mae"].dropna().to_numpy(),
                              z["mfe"].dropna().to_numpy())
    pct = pfd.rescale_cone(cone, scale, h)
    raw = pfd.empirical_cone(paths["ret"].dropna().to_numpy(), paths["mae"].dropna().to_numpy(),
                             paths["mfe"].dropna().to_numpy())
    for k, v in raw["ret_q"].items():
        assert abs(pct["ret_q"][k] - v) < 1e-8, (k, pct["ret_q"][k], v)
    assert pct["units"] == "pct"

    # frame arithmetic on a real panel: direct route vs ratio route
    frames = _frames(6, n=800)
    panel, cal = pfd.build_panel(frames, horizons=(h,))
    assert len(panel) > 1000, f"fixture panel too thin ({len(panel)})"
    p1.attach_scales(panel, cal, frames, horizon=h)
    keep = np.isfinite(panel["har_scale"].to_numpy()) & (panel["har_scale"].to_numpy() > 0)
    panel = panel.loc[keep].reset_index(drop=True)
    har = p1.build_har_frame(panel, h)

    direct = (panel[f"ret_{h}"].to_numpy(np.float64) / 100.0) / (
        panel["har_scale"].to_numpy(np.float64) * np.sqrt(h))
    ratio = panel[f"z_ret_{h}"].to_numpy(np.float64) * (
        panel["vol_scale"].to_numpy(np.float64) / panel["har_scale"].to_numpy(np.float64))
    ok = np.isfinite(direct) & np.isfinite(ratio)
    assert int(ok.sum()) > 800
    rel = np.abs(direct[ok] - ratio[ok]) / np.maximum(np.abs(direct[ok]), 1e-9)
    assert float(rel.max()) < 1e-4, f"direct and ratio routes disagree: {float(rel.max())}"

    # the HAR frame really IS a different frame — otherwise the whole study is a no-op
    a = har[f"z_ret_{h}"].to_numpy(np.float64)
    b = panel[f"z_ret_{h}"].to_numpy(np.float64)
    both = np.isfinite(a) & np.isfinite(b)
    assert float(np.abs(a[both] - b[both]).max()) > 1e-3, "HAR frame equals the wave-1 frame"
    # ... and it is the SAME outcome on a different scale: signs must be identical
    nz = both & (np.abs(b) > 1e-9)
    assert bool((np.sign(a[nz]) == np.sign(b[nz])).all()), \
        "re-scaling flipped an outcome's sign — the scale must be strictly positive"

    # every non-outcome column is untouched: the arms differ ONLY by the standardizer
    for col in list(pfd.FEATURE_COLS) + ["sess", "name", "vol_scale", f"ret_{h}", "har_scale"]:
        lhs, rhs = panel[col], har[col]
        if lhs.dtype.kind in "fc":
            assert np.allclose(lhs.to_numpy(np.float64), rhs.to_numpy(np.float64),
                               equal_nan=True), f"{col} moved between arms"
        else:
            assert lhs.equals(rhs), f"{col} moved between arms"
    print(f"ok test_har_standardization_round_trip_and_frame_arithmetic "
          f"({int(ok.sum()):,} paired rows)")


# ------------------------------------------------------------------ (d) import-surface pin
def test_runner_refuses_to_run_on_phase0_import_drift(monkeypatch):
    """The phase-1 study IS wave-1's machinery with one series swapped, so its meaning is
    defined by code it imports rather than owns. `verify_phase0_surface` must pass today
    AND must RAISE on drift — pinned by mutation on all three axes (a moved constant, a
    changed signature, a vanished symbol) and on the engine constants too. A guard that
    only asserts the happy path would pass on a refactor that voided the comparison."""
    passed = p1.verify_phase0_surface()
    assert len(passed) >= 20, f"suspiciously few surface checks: {len(passed)}"
    assert any("walk_forward" in c for c in passed)
    assert any("vf.HAR_LAGS" in c for c in passed)
    # every scheme is pinned, not just the two the readouts focus on: S1/S2/S4 are the
    # contrast that makes the "ordering flattens" reading mean anything
    for s in p0.SCHEMES:
        assert any(f"pfd.SCHEMES[{s}]" in c for c in passed), f"{s} not pinned"

    # THE REVIEWER'S NAMED DEFEATING MUTATION. VOL_WIN 20 -> 30 moves the trailing-20d
    # standardizer itself — the wave-1 baseline arm AND the D-2 denominator — while every
    # function signature still matches. Before the feature windows were pinned, this
    # silently redefined what the study measured and the guard stayed green.
    monkeypatch.setattr(pfd, "VOL_WIN", 30)
    with pytest.raises(RuntimeError, match="pfd.VOL_WIN"):
        p1.verify_phase0_surface()
    monkeypatch.undo()

    for const, bad in (("VOL_MINP", 10), ("REF_WIN", 126), ("REF_MINP", 60),
                       ("MAE_TAUS", (0.1, 0.5))):
        monkeypatch.setattr(pfd, const, bad)
        with pytest.raises(RuntimeError, match=f"pfd.{const}"):
            p1.verify_phase0_surface()
        monkeypatch.undo()

    # a redefined NON-vol scheme corrupts the X-3 contrast without touching S3 or S5
    bent = dict(pfd.SCHEMES)
    bent["S2_extension"] = (("ext_pct", "q", 6),)
    monkeypatch.setattr(pfd, "SCHEMES", bent)
    with pytest.raises(RuntimeError, match=r"pfd\.SCHEMES\[S2_extension\]"):
        p1.verify_phase0_surface()
    monkeypatch.undo()

    # 1. a frozen constant moves (this is how a refactor silently changes the study)
    for const, bad in (("WINDOW", 252), ("BOOT_SEED", 11), ("OOS_START", "2024-01-01"),
                       ("MIN_CELL_N", 100), ("TAUS", (0.1, 0.5, 0.9))):
        monkeypatch.setattr(p0, const, bad)
        with pytest.raises(RuntimeError, match="import surface drifted"):
            p1.verify_phase0_surface()
        monkeypatch.undo()
        assert p1.verify_phase0_surface(), "undo did not restore the surface"

    # 2. a signature changes (a new required argument, a moved default, a rename)
    def _renamed(panel, cal, horizon, *, frame="std"):
        raise AssertionError("never called")

    monkeypatch.setattr(p0, "walk_forward", _renamed)
    with pytest.raises(RuntimeError, match="signature drift"):
        p1.verify_phase0_surface()
    monkeypatch.undo()

    def _moved_default(store, max_names=500):
        raise AssertionError("never called")

    monkeypatch.setattr(p0, "load_frames", _moved_default)
    with pytest.raises(RuntimeError, match="signature drift"):
        p1.verify_phase0_surface()
    monkeypatch.undo()

    # 3. a symbol vanishes entirely
    monkeypatch.delattr(p0, "era_split")
    with pytest.raises(RuntimeError, match="missing or not callable"):
        p1.verify_phase0_surface()
    monkeypatch.undo()

    # 4. the engine side is pinned too — the standardizer's own lag set
    monkeypatch.setattr(vf, "HAR_LAGS", (1, 5, 22, 66))
    with pytest.raises(RuntimeError, match="vf.HAR_LAGS"):
        p1.verify_phase0_surface()
    monkeypatch.undo()

    monkeypatch.setattr(pfd, "VOL_FLOOR", 0.01)
    with pytest.raises(RuntimeError, match="pfd.VOL_FLOOR"):
        p1.verify_phase0_surface()
    monkeypatch.undo()

    # 5. and the REFUSAL is wired into the runner, not merely available beside it —
    #    run_study must raise before it reads a single parquet.
    src = inspect.getsource(p1.run_study)
    assert "verify_phase0_surface()" in src, "run_study does not call the import pin"
    monkeypatch.setattr(p0, "BOOT_SEED", 999)
    with pytest.raises(RuntimeError, match="import surface drifted"):
        p1.run_study(Path("/nonexistent-store-this-must-not-be-reached"))
    monkeypatch.undo()
    print("ok test_runner_refuses_to_run_on_phase0_import_drift "
          f"({len(passed)} pinned checks, 17 mutations)")


# ------------------------------------------------------------------ (e) D-2 decision table
def test_frozen_discriminator_bands_are_the_registered_ones():
    """The D-2 verdict map is pre-registered, so it is pinned as data rather than left to
    be re-read out of prose. Every branch of the frozen table is exercised, including the
    two degenerate cases (no replication; the two ratios straddling the band)."""
    assert p1.SHRINK_BAND == 0.5, p1.SHRINK_BAND

    assert p1.discriminate(True, 0.80, 0.90, True)[0] == "STATE_INFORMATION"
    assert p1.discriminate(True, 0.50, 0.55, True)[0] == "STATE_INFORMATION"   # band is >=
    assert p1.discriminate(False, 0.10, 0.12, True)[0] == "VOL_FORECAST_CORRECTION"
    assert p1.discriminate(False, 0.49, 0.30, True)[0] == "VOL_FORECAST_CORRECTION"
    assert p1.discriminate(True, 0.20, 0.24, True)[0] == "MIXED"     # survives but shrunk
    assert p1.discriminate(False, 0.70, 0.80, True)[0] == "MIXED"    # big point, no CI
    assert p1.discriminate(True, 0.60, 0.40, True)[0] == "MIXED"     # ratios straddle
    assert p1.discriminate(True, 0.90, 0.95, False)[0] == "INCONCLUSIVE_BASE"
    assert p1.discriminate(True, None, None, True)[0] == "INCONCLUSIVE_BASE"

    # An UNPRINTABLE secondary must not crash the verdict the PRIMARY already decided.
    # r_rel above the band + r_raw None/NaN takes the straddle branch (hi_raw is False),
    # which formatted r_raw unguarded and raised TypeError on None.
    for bad_raw in (None, float("nan")):
        v, why = p1.discriminate(True, 0.80, bad_raw, True)
        assert v == "MIXED", (v, bad_raw)
        assert "undefined" in why, why
        v2, why2 = p1.discriminate(False, 0.80, bad_raw, True)
        assert v2 == "MIXED" and "undefined" in why2
    # and the same pair BELOW the band agrees with hi_raw=False, so no straddle fires
    assert p1.discriminate(False, 0.20, None, True)[0] == "VOL_FORECAST_CORRECTION"
    for args in ((True, 0.8, 0.9, True), (False, 0.1, 0.1, True), (True, 0.9, 0.9, False)):
        assert len(p1.discriminate(*args)[1]) > 30, "a verdict must carry a stated reason"
    print("ok test_frozen_discriminator_bands_are_the_registered_ones")


# ------------------------------------------------------------------ (f) ratio CI honesty
def test_shrinkage_ratio_ci_prints_undefined_replicates():
    """The paired bootstrap must resample BOTH arms on the same blocks and must COUNT
    replicates whose denominator is non-positive instead of quietly dropping them into
    the percentile — a silently-dropped replicate turns an unstable ratio into a
    confident-looking interval."""
    rng = np.random.default_rng(5)
    n = 400
    base = pd.Series(0.25 + rng.normal(0, 0.01, n))
    dt = pd.Series(rng.normal(0.003, 0.002, n))        # a solid trailing-arm edge
    dh = dt * 0.4 + rng.normal(0, 0.0005, n)           # 40% retained by construction
    r = p1.shrinkage_ratio_ci(dh, base, dt, base, block=21, B=400, seed=7)
    assert r["ci"] is not None and r["undefined_frac"] == 0.0, r
    assert 0.2 < r["ci"][1] < 0.7, r["ci"]
    assert r["ci"][0] < r["ci"][1] < r["ci"][2]

    # a denominator that is noise around zero makes the ratio undefined in many draws —
    # that fraction must be reported, and a mostly-undefined ratio must refuse an interval
    dead = pd.Series(rng.normal(0.0, 0.002, n))
    r2 = p1.shrinkage_ratio_ci(dh, base, dead, base, block=21, B=400, seed=7)
    assert r2.get("undefined_frac", 0.0) > 0.2, r2
    if r2["ci"] is None:
        assert "denominator" in r2["reason"]

    # same blocks for both arms: identical inputs must return exactly 1.0 everywhere
    same = p1.shrinkage_ratio_ci(dt, base, dt, base, block=21, B=200, seed=7)
    assert same["ci"] is not None
    assert all(abs(v - 1.0) < 1e-9 for v in same["ci"]), \
        f"the two arms were not resampled on the same blocks: {same['ci']}"

    # too few dates for the block length is a null, not a fabricated interval
    short = p1.shrinkage_ratio_ci(dh[:40], base[:40], dt[:40], base[:40],
                                  block=21, B=100, seed=7)
    assert short["ci"] is None and "insufficient" in short["reason"]
    print("ok test_shrinkage_ratio_ci_prints_undefined_replicates")


# ------------------------------------------------------------------ (g) end-to-end shape
def test_forecast_quality_reads_a_forward_label_not_a_feature():
    """X-4 scores each standardizer against the REALIZED forward vol. That label is
    look-ahead by construction, so pin that it is (a) actually forward-looking and
    (b) never written into any column a cone reads."""
    close = _ohlcv(seed=53, n=600)["close"]
    h = 21
    fwd = p1.forward_rv_daily(close, h)
    assert fwd.iloc[-h:].isna().all(), "the forward label must be NaN in the last h rows"

    # it looks FORWARD: perturbing bars after t moves the label at t (the opposite of the
    # causality pin above, and the reason it can never be an input)
    poisoned = close.copy()
    poisoned.iloc[400:] = poisoned.iloc[400:] * np.exp(np.linspace(0, 0.5, len(poisoned) - 400))
    fwd2 = p1.forward_rv_daily(poisoned, h)
    assert float(abs(fwd2.iloc[380] - fwd.iloc[380])) > 0.0, \
        "the 'forward' vol label did not see the future — it is not a forward label"

    # daily units, consistent with the scales it is compared against
    ann = vf.forward_vol_ann(close, h)
    j = pd.concat([fwd.rename("d"), ann.rename("a")], axis=1).dropna()
    assert float((j["d"] * np.sqrt(252.0) - j["a"]).abs().max()) < 1e-9

    # and it is not among the columns the panel exposes to a cone
    frames = _frames(4, n=700)
    panel, cal = pfd.build_panel(frames, horizons=(h,))
    p1.attach_scales(panel, cal, frames, horizon=h)
    assert "fwd_rv" in panel.columns and "har_scale" in panel.columns
    assert "fwd_rv" not in set(pfd.FEATURE_COLS)
    fq = p1.forecast_quality(panel, cal, h)
    assert set(fq) >= {"trail20", "har"}
    print("ok test_forecast_quality_reads_a_forward_label_not_a_feature")


if __name__ == "__main__":
    import types

    class _MP:
        """Minimal monkeypatch stand-in so the file runs under `python3 -m` too."""

        def __init__(self):
            self._undo: list = []

        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def delattr(self, obj, name):
            self._undo.append((obj, name, getattr(obj, name)))
            delattr(obj, name)

        def undo(self):
            while self._undo:
                obj, name, old = self._undo.pop()
                setattr(obj, name, old)

    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for fn in fns:
        if "monkeypatch" in inspect.signature(fn).parameters:
            mp = _MP()
            try:
                fn(mp)
            finally:
                mp.undo()
        else:
            fn()
    print(f"\n{len(fns)} pick_forward_dist phase-1 tests passed.")
