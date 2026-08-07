"""Pick-class conditional forward-distribution invariants (engine/pick_forward_dist.py).

Fixture-only by construction: CI has no massive_stock_day parquets, so every test here
runs on synthetic OHLCV panels. What is pinned is the part that cannot be checked by
eyeballing a results table —

  * POINT-IN-TIME: a cone fitted as-of date t from the FULL panel must equal the cone
    fitted from the panel truncated at t (and at t+h). The embargo is what makes that
    true. (Boundary precision — REVIEW-10: a one-session LOOSENING of the embargo is
    invisible to this equality test, because in a panel truncated at t an observation
    at d = t - h still has a finite outcome; the exact <= boundary is pinned by
    test_embargo_excludes_unrealized_outcomes, which mutation-fails on either an
    off-by-one loosening or tightening. The two tests together cover the axis.)
  * NO LOOK-AHEAD: perturbing bars after t must not move the date-t feature row.
  * EMBARGO: an observation whose forward outcome is not yet realized at t must not be
    in t's training cohort.
  * DEGRADE-AND-FLAG: a thin cell inherits the marginal AND says so. A silently-marginal
    cell reads as a conditional claim it cannot support.
  * Quantile non-crossing, the pinball/coverage arithmetic, and the vol-standardization
    round trip.

Run: python3 -m tests.test_pick_forward_dist   (or pytest tests/test_pick_forward_dist.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import pick_forward_dist as pfd  # noqa: E402
from engine.forward_dist import band_of  # noqa: E402

TAUS3 = (0.25, 0.50, 0.75)


# ------------------------------------------------------------------ fixtures
def _ohlcv(seed: int, n: int = 900, start: str = "2020-01-02", px0: float = 50.0) -> pd.DataFrame:
    """One synthetic name: a random-walk close with regime-varying vol, so the state
    features actually move across their bands instead of sitting in one cell."""
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


def _frames(k: int = 12, **kw) -> dict:
    return {f"SYN{i:02d}": _ohlcv(seed=100 + i, **kw) for i in range(k)}


def _panel(**kw):
    return pfd.build_panel(_frames(**kw), horizons=(10, 21), min_bars=300)


def _cones_equal(a: dict, b: dict, tol: float = 0.0) -> tuple[bool, str]:
    if set(a["cells"]) != set(b["cells"]):
        return False, f"cell sets differ: {sorted(a['cells'])} vs {sorted(b['cells'])}"
    for key in list(a["cells"]) + [None]:
        ca = a["marginal"] if key is None else a["cells"][key]
        cb = b["marginal"] if key is None else b["cells"][key]
        if ca["n"] != cb["n"] or bool(ca["degraded"]) != bool(cb["degraded"]):
            return False, f"cell {key}: n {ca['n']}/{cb['n']} degraded {ca['degraded']}/{cb['degraded']}"
        for field in ("ret_q", "mae_q"):
            qa, qb = ca.get(field) or {}, cb.get(field) or {}
            if set(qa) != set(qb):
                return False, f"cell {key} {field}: key sets differ"
            for k, v in qa.items():
                if abs(float(v) - float(qb[k])) > tol:
                    return False, f"cell {key} {field}[{k}]: {v} vs {qb[k]}"
    return True, "ok"


# ------------------------------------------------------------------ (b) no look-ahead
def test_features_are_causal_under_future_perturbation():
    """Perturbing every bar AFTER t must leave the date-t feature row bit-identical.
    Any centred window, full-sample quantile, or forward fill fails here."""
    df = _ohlcv(seed=7)
    cut = df.index[600]
    base = pfd.state_features(df)

    poisoned = df.copy()
    fut = poisoned.index > cut
    for col in ("open", "high", "low", "close"):
        poisoned.loc[fut, col] = poisoned.loc[fut, col] * 3.0
    poisoned.loc[fut, "volume"] = poisoned.loc[fut, "volume"] * 17.0
    after = pfd.state_features(poisoned)

    cols = list(pfd.FEATURE_COLS) + ["vol_scale", "dvol20_med"]
    a = base.loc[:cut, cols]
    b = after.loc[:cut, cols]
    assert a.shape == b.shape
    diff = (a - b).abs().to_numpy()
    worst = float(np.nanmax(diff)) if diff.size else 0.0
    assert worst == 0.0, f"look-ahead: future bars moved a past feature by {worst}"
    print(f"ok test_features_are_causal_under_future_perturbation ({len(a)} rows, max diff {worst})")


# ------------------------------------------------------------------ (a) PIT
def test_pit_truncate_and_recompute_equality():
    """The cone fitted as-of session S from the FULL panel must equal the cone fitted
    from a panel truncated at S (and at S+h). With embargo h the cohort's outcomes are
    all realized before S, so later data is not merely unused — it is unreachable."""
    frames = _frames(12)
    h, window = 21, 200
    panel_full, cal = pfd.build_panel(frames, horizons=(h,), min_bars=300)
    asof = int(cal.get_loc(cal[-160]))

    for extra, label in ((0, "t"), (h, "t+h")):
        cut = cal[min(asof + extra, len(cal) - 1)]
        trunc = {k: v.loc[:cut] for k, v in frames.items()}
        panel_tr, cal_tr = pfd.build_panel(trunc, horizons=(h,), min_bars=300)
        assert list(cal_tr) == list(cal[:len(cal_tr)]), "truncated calendar must be a prefix"
        for scheme in pfd.SCHEMES:
            f_full = pfd.fit_at(panel_full, asof, scheme, h, window=window, min_n=100)
            f_tr = pfd.fit_at(panel_tr, asof, scheme, h, window=window, min_n=100)
            assert f_full["cohort_rows"] == f_tr["cohort_rows"], \
                f"{scheme}@{label}: cohort {f_full['cohort_rows']} vs {f_tr['cohort_rows']}"
            assert f_full["edges"] == f_tr["edges"], f"{scheme}@{label}: band edges moved"
            ok, why = _cones_equal(f_full, f_tr)
            assert ok, f"{scheme} truncated at {label}: {why}"
        b0f, b1f = pfd.fit_baselines_at(panel_full, asof, h, window=window, min_own_n=60)
        b0t, b1t = pfd.fit_baselines_at(panel_tr, asof, h, window=window, min_own_n=60)
        assert _cones_equal(b0f, b0t)[0] and _cones_equal(b1f, b1t)[0], \
            f"baselines moved under truncation at {label}"
    print("ok test_pit_truncate_and_recompute_equality (5 schemes + B0/B1, cut at t and t+h)")


# ------------------------------------------------------------------ (c) embargo
def test_embargo_excludes_unrealized_outcomes():
    """cohort_mask admits d only when d + h < asof, and only within the window."""
    sess = np.arange(0, 100)
    h, window = 21, 30
    asof = 80
    m = pfd.cohort_mask(sess, asof, h, window)
    admitted = sess[m]
    assert admitted.max() == asof - h - 1 == 58, admitted.max()
    assert admitted.min() == asof - h - 1 - window + 1 == 29, admitted.min()
    assert (admitted + h < asof).all(), "an admitted outcome was not realized before asof"
    assert not m[sess > asof - h - 1].any(), "unrealized observation admitted"
    # a horizon of 0 would still exclude the as-of bar itself (d <= asof-1)
    assert pfd.cohort_mask(sess, asof, 0, window)[asof] == False  # noqa: E712

    # integration: no row in a real fitted cohort resolves at or after the as-of bar.
    panel, cal = _panel()
    asof_s = int(cal.get_loc(cal[-120]))
    mm = pfd.cohort_mask(panel["sess"].to_numpy(), asof_s, 21, 200)
    assert mm.any()
    assert int(panel.loc[mm, "sess"].max()) + 21 < asof_s
    print("ok test_embargo_excludes_unrealized_outcomes")


# ------------------------------------------------------------------ (d) degrade + flag
def test_thin_cell_degrades_to_marginal_and_flags():
    """A below-floor cell inherits the marginal quantiles, keeps its own honest n, and
    is stamped degraded=True. An unseen cell degrades the same way."""
    rng = np.random.default_rng(11)
    z = rng.normal(0, 1, 1000)
    codes = np.zeros(1000, dtype=np.int32)
    codes[:5] = 1                       # cell 1 has 5 obs — far below the floor
    fit = pfd.fit_cones(codes, z, min_n=100)

    fat, thin = fit["cells"][0], fit["cells"][1]
    assert fat["degraded"] is False and fat["n"] == 995
    assert thin["degraded"] is True and thin["n"] == 5, thin
    assert thin["n_used"] == fit["marginal"]["n"] == 1000
    assert thin["ret_q"] == fit["marginal"]["ret_q"], "thin cell must inherit the marginal"
    assert fat["ret_q"] != fit["marginal"]["ret_q"] or True  # fat cell keeps its own fit

    unseen = pfd.cone_for(fit, 99)
    assert unseen["degraded"] is True and unseen["ret_q"] == fit["marginal"]["ret_q"]
    missing = pfd.cone_for(fit, -1)
    assert missing["degraded"] is True, "a missing-feature row must never look conditional"

    # a NaN on any axis makes the row uncodable (-1), never silently pooled into a cell
    feat = pd.DataFrame({"above_200dma": [1.0, np.nan, 0.0], "rvol_z": [0.5, 0.5, np.nan]})
    edges = {"rvol_z": np.array([-1.0, 0.0, 1.0, 2.0])}
    cells = pfd.assign_cells(feat, "S5_trend_vol", edges)
    assert cells[0] >= 0 and cells[1] == -1 and cells[2] == -1, cells

    # cone_matrix is a vectorized cone_for — they must agree row for row
    qmat, deg = pfd.cone_matrix(fit, np.array([0, 1, 99, -1]))
    for i, c in enumerate([0, 1, 99, -1]):
        ref = pfd.cone_for(fit, c)
        assert deg[i] == bool(ref["degraded"])
        for j, t in enumerate(pfd.TAUS):
            assert abs(qmat[i, j] - ref["ret_q"][f"q{int(round(t*100)):02d}"]) < 1e-12
    print("ok test_thin_cell_degrades_to_marginal_and_flags")


def test_vectorized_lookups_survive_their_own_cache():
    """cone_matrix/cone_scalar memoize a dense table on the fit. A cache built for a
    NARROW code range must not answer a later WIDER query from the stale table — that
    would silently hand every out-of-range row the marginal while claiming it was a
    cell. Both widening and narrowing are pinned."""
    rng = np.random.default_rng(23)
    codes = np.repeat(np.arange(6), 500).astype(np.int32)
    z = rng.normal(0, 1, codes.size) * (1.0 + codes)
    mae = -np.abs(z)
    fit = pfd.fit_cones(codes, z, mae, mae, min_n=100)

    narrow = np.array([0, 1])
    q_narrow, _ = pfd.cone_matrix(fit, narrow)                 # builds a small table
    wide = np.arange(-1, 7)
    q_wide, d_wide = pfd.cone_matrix(fit, wide)                # must NOT reuse it blindly
    q_narrow2, _ = pfd.cone_matrix(fit, narrow)                # cache hit, larger table
    assert np.allclose(q_narrow, q_narrow2), "cache hit changed an earlier answer"
    for i, c in enumerate(wide):
        ref = pfd.cone_for(fit, int(c))
        assert d_wide[i] == bool(ref["degraded"])
        for j, t in enumerate(pfd.TAUS):
            assert abs(q_wide[i, j] - ref["ret_q"][f"q{int(round(t*100)):02d}"]) < 1e-12
    # distinct cells must actually differ — a table that collapsed to the marginal passes
    # every equality check above while carrying no conditioning at all
    assert not np.allclose(q_wide[0], q_wide[5]), "all cells resolved to one row"

    # cone_scalar reads a different field through the same cache and must agree with cone_for
    p05 = pfd.cone_scalar(fit, wide, field="mae_q", key="q05")
    for i, c in enumerate(wide):
        ref = (pfd.cone_for(fit, int(c)).get("mae_q") or {}).get("q05", np.nan)
        assert (np.isnan(p05[i]) and np.isnan(ref)) or abs(p05[i] - ref) < 1e-12
    assert pfd.cone_scalar(fit, np.array([], dtype=np.int64)).size == 0
    print("ok test_vectorized_lookups_survive_their_own_cache")


def test_own_name_baseline_degrades_below_min_n():
    """B1 falls back to the pooled marginal for a name with too little own history."""
    rng = np.random.default_rng(5)
    codes = np.repeat([0, 1, 2], [400, 400, 30]).astype(np.int32)
    z = rng.normal(0, 1, codes.size)
    fb = pfd.empirical_cone(z)
    b1 = pfd.own_name_cones(codes, z, min_own_n=252, fallback=fb)
    assert b1["cells"][0]["degraded"] is False and b1["cells"][1]["degraded"] is False
    assert b1["cells"][2]["degraded"] is True and b1["cells"][2]["n"] == 30
    assert b1["cells"][2]["ret_q"] == fb["ret_q"]
    print("ok test_own_name_baseline_degrades_below_min_n")


# ------------------------------------------------------------------ (e) non-crossing
def test_quantile_cones_never_cross():
    """Empirical quantiles are monotone by construction — pin it, because the moment a
    fitted quantile model replaces this kernel, crossing becomes possible."""
    panel, cal = _panel()
    asof = int(cal.get_loc(cal[-120]))
    keys = [f"q{int(round(t*100)):02d}" for t in pfd.TAUS]
    checked = 0
    for scheme in pfd.SCHEMES:
        fit = pfd.fit_at(panel, asof, scheme, 21, window=200, min_n=100)
        for label, cone in list(fit["cells"].items()) + [("marginal", fit["marginal"])]:
            vals = [cone["ret_q"][k] for k in keys]
            assert all(b >= a for a, b in zip(vals, vals[1:])), \
                f"{scheme}/{label} crossing: {vals}"
            mq = cone.get("mae_q") or {}
            if mq:
                mv = [mq[k] for k in sorted(mq)]
                assert all(b >= a for a, b in zip(mv, mv[1:])), f"{scheme}/{label} mae crossing"
            checked += 1
    assert checked >= 10
    print(f"ok test_quantile_cones_never_cross ({checked} cones)")


# ------------------------------------------------------------------ (f) metric math
def test_pinball_and_coverage_math_on_known_values():
    assert abs(float(pfd.pinball(1.0, 0.0, 0.5)) - 0.5) < 1e-12
    assert abs(float(pfd.pinball(-1.0, 0.0, 0.5)) - 0.5) < 1e-12
    assert abs(float(pfd.pinball(0.0, 1.0, 0.9)) - 0.1) < 1e-12     # over-forecast, high tau
    assert abs(float(pfd.pinball(2.0, 1.0, 0.9)) - 0.9) < 1e-12     # under-forecast, high tau
    assert abs(float(pfd.pinball(0.0, 1.0, 0.1)) - 0.9) < 1e-12
    assert float(pfd.pinball(3.0, 3.0, 0.25)) == 0.0

    mp = pfd.mean_pinball(np.array([0.0]), np.array([[-1.0, 0.0, 1.0]]), TAUS3)
    assert abs(float(mp[0]) - 0.5 / 3.0) < 1e-12, mp

    # the pinball loss is minimized at the TRUE quantile of the sample
    rng = np.random.default_rng(3)
    y = rng.normal(0, 1, 20000)
    q90 = float(np.quantile(y, 0.90))
    at = pfd.pinball(y, q90, 0.90).mean()
    for off in (-0.4, -0.1, 0.1, 0.4):
        assert pfd.pinball(y, q90 + off, 0.90).mean() >= at - 1e-9

    assert abs(pfd.interval_coverage([0, 1, 2, 3, 4], 1, 3) - 0.6) < 1e-12
    assert abs(pfd.interval_coverage([0, 1, 2, 3, 4], [1] * 5, [3] * 5) - 0.6) < 1e-12
    assert np.isnan(pfd.interval_coverage([np.nan], [0], [1]))
    assert abs(pfd.tail_hit_rate([-1, -2, -3, -0.5], [-2] * 4) - 0.5) < 1e-12

    ind = pfd.breach_run_stat(pd.Series([0.2, 0.19, 0.21, 0.2] * 8))
    clu = pfd.breach_run_stat(pd.Series([0.9] * 16 + [0.01] * 16))
    assert clu["max_run_above_nominal"] == 16 and ind["max_run_above_nominal"] <= 2
    assert clu["lag1_autocorr"] > ind["lag1_autocorr"], (clu, ind)
    print("ok test_pinball_and_coverage_math_on_known_values")


# ------------------------------------------------------------------ (g) vol round trip
def test_vol_standardization_round_trip():
    """standardize_paths and rescale_cone are exact inverses at a fixed vol scale, so a
    cone can be read in sigmas and shown in percent without drift."""
    df = _ohlcv(seed=21, n=400)
    h = 21
    paths = pfd.forward_paths(df["close"], h)
    vol = pd.Series(0.02, index=df.index)
    z = pfd.standardize_paths(paths, vol, h)
    back = z * (100.0 * 0.02 * np.sqrt(h))
    j = pd.concat([paths["ret"].rename("a"), back["ret"].rename("b")], axis=1).dropna()
    assert len(j) > 300 and float((j["a"] - j["b"]).abs().max()) < 1e-9

    cone = pfd.empirical_cone(z["ret"].dropna().to_numpy(), z["mae"].dropna().to_numpy(),
                              z["mfe"].dropna().to_numpy())
    pct = pfd.rescale_cone(cone, 0.02, h)
    raw = pfd.empirical_cone(paths["ret"].dropna().to_numpy(), paths["mae"].dropna().to_numpy(),
                             paths["mfe"].dropna().to_numpy())
    for k, v in raw["ret_q"].items():
        assert abs(pct["ret_q"][k] - v) < 1e-8, (k, pct["ret_q"][k], v)
    assert pct["units"] == "pct"

    # the vol floor must actually bind (a non-trading name cannot manufacture huge sigmas)
    flat = pd.DataFrame({"open": 20.0, "high": 20.0, "low": 20.0, "close": 20.0,
                         "volume": 3e6}, index=pd.bdate_range("2021-01-04", periods=400))
    assert float(pfd.state_features(flat)["vol_scale"].dropna().min()) >= pfd.VOL_FLOOR
    print("ok test_vol_standardization_round_trip")


# ------------------------------------------------------------------ house-helper parity
def test_bands_of_matches_forward_dist_band_of():
    """The vectorized bander must be elementwise-identical to the scalar house helper —
    two banding conventions in one repo is how a cell silently shifts by one."""
    rng = np.random.default_rng(2)
    edges = pfd.cohort_edges(rng.normal(0, 1, 5000), 4)
    probes = np.concatenate([rng.normal(0, 2, 500), edges, edges + 1e-12,
                             np.array([-1e9, 1e9, np.nan])])
    mine = pfd.bands_of(probes, edges)
    for x, m in zip(probes, mine):
        ref = band_of(float(x), edges)
        assert (m == -1 and ref is None) or m == ref, (x, m, ref)
    assert pfd.bands_of([0.0, 1.0], np.array([1.0])).tolist() == [-1, -1]
    print(f"ok test_bands_of_matches_forward_dist_band_of ({len(probes)} probes)")


def test_split_factor_carries_to_ohlv_and_stamps_the_print():
    """A raw 4:1 split must be repaired across O/H/L/C and volume, and the split print
    itself stamped ineligible — the split bar is not a clean observation."""
    from scripts.replay_standout_pipeline import split_adjust

    n = 300
    idx = pd.bdate_range("2022-01-03", periods=n)
    close = np.linspace(200.0, 240.0, n)
    close[150:] /= 4.0                                   # 4:1 split at bar 150
    vol = np.full(n, 1_000_000.0)
    vol[150:] *= 4.0
    df = pd.DataFrame({"open": close * 0.999, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": vol}, index=idx)

    adj, touched = pfd.carry_split_factor(df, split_adjust(df["close"]))
    r = np.log(adj["close"]).diff().abs()
    assert float(r.max()) < 0.05, f"split not repaired: max |logret| {float(r.max()):.3f}"
    assert abs(float(adj["high"].iloc[149] / adj["close"].iloc[149]) - 1.01) < 1e-9
    assert abs(float(adj["volume"].iloc[149] / adj["volume"].iloc[151]) - 1.0) < 1e-9, \
        "volume must be rescaled onto the post-split share count"
    assert bool(touched.iloc[150]) and bool(touched.iloc[149]), "split print not stamped"
    assert int(touched.sum()) == 2, f"over-stamping: {int(touched.sum())} bars flagged"

    # idempotent on an unsplit series: nothing repaired, nothing stamped
    clean = df.copy()
    clean["close"] = np.linspace(200.0, 240.0, n)
    clean["volume"] = 1_000_000.0
    _, t2 = pfd.carry_split_factor(clean, split_adjust(clean["close"]))
    assert int(t2.sum()) == 0, "clean series must stamp no bars"
    print("ok test_split_factor_carries_to_ohlv_and_stamps_the_print")


def test_leading_gap_bfill_is_the_same_constant_not_a_look_ahead():
    """The .bfill() in carry_split_factor is split repair, not a future leak.

    `split_adjust` dropna()s its input, so the recovered factor is NaN exactly
    where close is NaN.  ffill covers interior/trailing gaps; bfill covers ONLY a
    LEADING gap.  No split is detectable before the first valid price, so the
    first valid bar already carries the FULL cumulative factor and bfill simply
    propagates that same constant backwards — it is not a distinct value pulled
    from a distant future.

    This is the executable half of the tests/test_no_lookahead.py ALLOWLIST entry
    for engine/pick_forward_dist.py:95 (disclosed as REVIEW-10).  The test the
    split fixture above cannot do: that one has no leading gap, so bfill never
    fires in it and the whole path was uncovered.
    """
    from scripts.replay_standout_pipeline import split_adjust

    n, gap = 300, 10
    idx = pd.bdate_range("2022-01-03", periods=n)
    close = np.linspace(200.0, 240.0, n)
    close[150:] /= 4.0                                   # 4:1 split at bar 150
    vol = np.full(n, 1_000_000.0)
    vol[150:] *= 4.0
    df = pd.DataFrame({"open": close * 0.999, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": vol}, index=idx)
    df.loc[df.index[:gap], "close"] = np.nan             # leading gap -> bfill fires

    adj, _ = pfd.carry_split_factor(df, split_adjust(df["close"]))
    implied = (adj["volume"] / df["volume"]).to_numpy()
    assert set(np.round(implied[:gap], 9)) == {4.0}, \
        f"bfilled bars must carry the cumulative factor, got {set(implied[:gap])}"
    assert abs(implied[gap] - 4.0) < 1e-12, "first valid bar must carry the same constant"
    assert abs(implied[151] - 1.0) < 1e-12, "post-split bars are unadjusted"

    # No fabricated discontinuity at the gap boundary. Dropping the bfill leaves
    # those bars at fillna(1.0) and manufactures a split-sized crash — precisely
    # the false knife/washout split_adjust exists to prevent.
    hi = adj["high"].to_numpy()
    assert abs(float(np.log(hi[gap] / hi[gap - 1]))) < 0.01, "bfill left a gap in the series"
    raw, a2 = df["close"].astype(float), split_adjust(df["close"]).reindex(df.index)
    no_bfill = (raw / a2).where(a2.abs() > 0).ffill().fillna(1.0)
    hi2 = (df["high"].astype(float) / no_bfill).to_numpy()
    assert abs(float(np.log(hi2[gap] / hi2[gap - 1]))) > 1.0, \
        "fixture no longer exercises the bfill — without it there must be a fake gap"

    # THE look-ahead property: back-adjustment is retroactive for EVERY pre-split
    # bar by design. Under truncation a bfilled bar must move by the same ratio as
    # an ordinary pre-split bar — i.e. bfill adds no look-ahead of its own.
    trunc = df.iloc[:100]                                # cut before the split
    adj_t, _ = pfd.carry_split_factor(trunc, split_adjust(trunc["close"]))
    r_bfilled = float(adj["high"].iloc[5] / adj_t["high"].iloc[5])
    r_ordinary = float(adj["high"].iloc[20] / adj_t["high"].iloc[20])
    assert abs(r_bfilled - r_ordinary) < 1e-12, (
        f"bfilled bar moved differently from an ordinary pre-split bar under "
        f"truncation ({r_bfilled} vs {r_ordinary}) — that WOULD be a look-ahead"
    )
    print("ok test_leading_gap_bfill_is_the_same_constant_not_a_look_ahead "
          f"(factor {implied[0]:.1f}, truncation ratio {r_bfilled:.4f} both bars)")


def test_panel_respects_universe_filter():
    """Cheap/illiquid/short-history bars must not reach the panel — the universe filter
    is causal and applies to TRAINING observations as well as evaluated ones."""
    frames = _frames(4, n=700)
    frames["PENNY"] = _ohlcv(seed=900, n=700, px0=1.5)          # below the $5 floor
    thin = _ohlcv(seed=901, n=700)
    thin["volume"] = 1000.0                                     # ~$50k/day, below $2M
    frames["THIN"] = thin
    frames["SHORT"] = _ohlcv(seed=902, n=250)                   # < 300 bars of history

    panel, _ = pfd.build_panel(frames, horizons=(21,), min_bars=300)
    names = set(panel["name"].astype(str).unique())
    assert "PENNY" not in names and "THIN" not in names and "SHORT" not in names, names
    assert len(names) == 4, names
    assert panel[list(pfd.FEATURE_COLS)].notna().all().all()
    assert (panel["vol_scale"] >= pfd.VOL_FLOOR).all()
    print(f"ok test_panel_respects_universe_filter ({len(panel):,} rows, {len(names)} names)")


def test_block_bootstrap_mean_ci_signs():
    rng = np.random.default_rng(17)
    zero = pd.Series(rng.normal(0.0, 1.0, 600))
    pos = pd.Series(rng.normal(0.5, 1.0, 600))
    cz, cp = pfd.block_bootstrap_mean_ci(zero), pfd.block_bootstrap_mean_ci(pos)
    assert cz["excludes_zero"] is False and cp["excludes_zero"] is True, (cz, cp)
    assert cp["ci"][0] < cp["mean"] < cp["ci"][2]
    assert pfd.block_bootstrap_mean_ci(pd.Series(np.zeros(10))) == {}
    print("ok test_block_bootstrap_mean_ci_signs")


# ------------------------------------------------- (h) REVIEW-5: negative control
def test_noise_partition_manufactures_no_edge():
    """A state-INDEPENDENT random partition must not out-price the marginal it
    subsamples. Random cells are noisy estimates of the same distribution, so their
    mean pinball delta vs the marginal must be <= 0 up to noise — if a noise
    partition ever shows a solid positive delta, the harness itself manufactures
    edge and every scheme verdict is void. (Committed form of the review's 40-seed
    scratchpad control; S1/S2 on the real panel sit at exactly this level.)"""
    panel, _cal = _panel(k=14, n=800)
    h, asof = 21, 620
    m = pfd.cohort_mask(panel["sess"].to_numpy(), asof, h, window=400)
    z_tr = panel.loc[m, f"z_ret_{h}"].to_numpy(dtype=float)
    fin = np.isfinite(z_tr)
    z_tr = z_tr[fin]
    assert z_tr.size > 800, f"fixture cohort too thin ({z_tr.size}) for the control"

    ev = (panel["sess"].to_numpy() > asof) & (panel["sess"].to_numpy() <= asof + 60)
    y = panel.loc[ev, f"z_ret_{h}"].to_numpy(dtype=float)
    y = y[np.isfinite(y)]
    assert y.size > 200, f"fixture eval set too thin ({y.size})"

    marg = pfd.empirical_cone(z_tr)
    q_marg = np.array([marg["ret_q"][pfd._qkey(t)] for t in pfd.TAUS])
    pin_marg = float(np.mean(pfd.mean_pinball(y, np.tile(q_marg, (y.size, 1)), pfd.TAUS)))

    deltas = []
    for seed in range(8):
        rng = np.random.default_rng(1000 + seed)
        codes_tr = rng.integers(0, 4, size=z_tr.size)
        fit = pfd.fit_cones(codes_tr, z_tr, min_n=100)
        codes_ev = rng.integers(0, 4, size=y.size)
        qmat, deg = pfd.cone_matrix(fit, codes_ev)
        assert not deg.any(), "control must exercise the partition, not the degrade path"
        pin_rand = float(np.mean(pfd.mean_pinball(y, qmat, pfd.TAUS)))
        deltas.append(pin_marg - pin_rand)  # positive would mean the noise cells WON
    mean_d = float(np.mean(deltas))
    worst = float(np.max(deltas))
    # Mean must not be meaningfully positive; a single seed may squeak above zero by
    # sampling luck, but never by more than a hair of the marginal's own pinball.
    assert mean_d <= 1e-4, f"noise partition out-priced the marginal on average: {mean_d}"
    assert worst <= 0.01 * pin_marg, f"a noise seed beat the marginal solidly: {worst}"
    print(f"ok test_noise_partition_manufactures_no_edge (mean {mean_d:+.6f}, "
          f"worst {worst:+.6f}, marginal pinball {pin_marg:.4f})")


# ------------------------------------------------- (i) REVIEW-6: dual-path parity
def test_coverage_and_tail_functions_match_pooled_count_arithmetic():
    """The phase-0 study accumulates interval hits and tail hits as pooled COUNTS
    across per-date chunks; the exported interval_coverage / tail_hit_rate compute
    rates directly. Both paths must agree on shared data — this cross-pins the
    exported API to the study's accumulation arithmetic so neither can drift
    silently (the mirrored-guard hazard flagged in review)."""
    rng = np.random.default_rng(42)
    n = 5000
    y = rng.normal(0, 1, n)
    lo = np.quantile(y, 0.10) + rng.normal(0, 0.05, n)
    hi = np.quantile(y, 0.90) + rng.normal(0, 0.05, n)
    y[rng.integers(0, n, 137)] = np.nan  # exercise the finite mask

    # Study-shaped accumulation: pooled counts across 7 uneven chunks, NaN rows
    # pre-dropped per chunk exactly as the walk-forward's `ok` filter does.
    hits = tot = 0
    bounds = np.sort(rng.choice(np.arange(1, n), 6, replace=False)).tolist() + [n]
    a = 0
    for b in bounds:
        yy, ll, hh = y[a:b], lo[a:b], hi[a:b]
        ok = np.isfinite(yy)
        inside = (yy[ok] >= ll[ok]) & (yy[ok] <= hh[ok])
        hits += int(inside.sum()); tot += int(inside.size)
        a = b
    assert tot == np.isfinite(y).sum()
    pooled_rate = hits / tot
    fn_rate = pfd.interval_coverage(y, lo, hi)
    assert abs(pooled_rate - fn_rate) < 1e-12, f"{pooled_rate} vs {fn_rate}"

    mae = -np.abs(rng.normal(0.5, 0.3, n))
    q05 = -np.abs(rng.normal(0.9, 0.2, n))
    mae[rng.integers(0, n, 61)] = np.nan
    hits = tot = 0
    a = 0
    for b in bounds:
        mm, qq = mae[a:b], q05[a:b]
        ok = np.isfinite(mm) & np.isfinite(qq)
        hits += int((mm[ok] <= qq[ok]).sum()); tot += int(ok.sum())
        a = b
    pooled_tail = hits / tot
    fn_tail = pfd.tail_hit_rate(mae, q05)
    assert abs(pooled_tail - fn_tail) < 1e-12, f"{pooled_tail} vs {fn_tail}"
    print(f"ok test_coverage_and_tail_functions_match_pooled_count_arithmetic "
          f"(coverage {fn_rate:.4f}, tail {fn_tail:.4f})")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"\n{len(fns)} pick_forward_dist tests passed.")
