#!/usr/bin/env python3
"""GD-1C research-only truncate/recompute and GD-H1/GD-H2 test.

This program never calls leadership_crack.build(), never writes data/ or site/,
and writes only content-addressed research artifacts beside itself.  The primary
PIT-membership lane is adjudicated from membership receipts; the numerical run
is the separately labelled def_current_cf lane frozen in the GD-1C prereg.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import leadership_crack as lc


OUT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DESIGN_START = pd.Timestamp("2016-01-04")
DESIGN_END = pd.Timestamp("2026-07-31")
INCIDENT_START = pd.Timestamp("2026-08-01")
BASE_COMMIT = "cdf99c6203b6bd964d7fb5564452289ecfde90e8"
CODE_BLOB = "cb0a3f468ac1bf2267fb6d0ee57d378b293d3c0b"
PREREG_FREEZE = "fce7bfeb8c925748ed92b54a7b19901c3a9f35c1"
LANE = "def_current_cf"
MEMBERSHIP_BASIS = "current_membership_file_at_run_not_pit"
RNG_SEED = 20260819
BOOTSTRAPS = 2000
BLOCK_LEN = 4
HORIZONS = (1, 3)
ENDPOINTS = (
    "y_resid_dd_ge3_1s",
    "y_resid_dd_ge5_1s",
    "y_resid_dd_ge3_3s",
    "y_resid_dd_ge5_3s",
)
ERAS = {
    "E1_2016_2019": (pd.Timestamp("2016-01-04"), pd.Timestamp("2019-12-31")),
    "E2_2020_2022": (pd.Timestamp("2020-01-01"), pd.Timestamp("2022-12-30")),
    "E3_2023_2026H1": (pd.Timestamp("2023-01-03"), pd.Timestamp("2026-07-31")),
}
HALVES = {
    "H1_2016_2020": (pd.Timestamp("2016-01-04"), pd.Timestamp("2020-12-31")),
    "H2_2021_2026H1": (pd.Timestamp("2021-01-04"), pd.Timestamp("2026-07-31")),
}
CRISES = {
    "2018_Q4": (pd.Timestamp("2018-10-01"), pd.Timestamp("2018-12-31")),
    "2020_COVID": (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")),
    "2022_DURATION": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-10-31")),
    "2024_YEN_VOL": (pd.Timestamp("2024-07-01"), pd.Timestamp("2024-08-31")),
    "2026_MEMORY_UNWIND": (pd.Timestamp("2026-06-23"), pd.Timestamp("2026-06-23")),
    "2026_KR_PRIOR": (pd.Timestamp("2026-07-02"), pd.Timestamp("2026-07-02")),
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_dump(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-x))


@dataclass
class LogisticFit:
    intercept: float
    slope: float
    estimable: bool

    def predict(self, score: np.ndarray) -> np.ndarray:
        return sigmoid(self.intercept + self.slope * score)


def fit_logistic(score: Iterable[float], outcome: Iterable[float], *, l2: float = 1.0) -> LogisticFit:
    x = np.asarray(list(score), dtype=float)
    y = np.asarray(list(outcome), dtype=float)
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    if len(y) < 3 or len(np.unique(y)) < 2:
        prev = float(np.mean(y)) if len(y) else 0.5
        prev = float(np.clip(prev, 1e-6, 1 - 1e-6))
        return LogisticFit(float(np.log(prev / (1 - prev))), 0.0, False)
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.array([float(np.log(np.mean(y) / (1 - np.mean(y)))), 0.0])
    penalty = np.diag([0.0, l2])
    for _ in range(100):
        p = sigmoid(X @ beta)
        w = np.clip(p * (1 - p), 1e-8, None)
        grad = X.T @ (y - p) - penalty @ beta
        hess = X.T @ (w[:, None] * X) + penalty + np.eye(2) * 1e-10
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            return LogisticFit(float(beta[0]), float(beta[1]), False)
        beta += step
        if float(np.max(np.abs(step))) < 1e-10:
            break
    return LogisticFit(float(beta[0]), float(beta[1]), True)


def average_precision(y: Iterable[float], score: Iterable[float]) -> float:
    yv = np.asarray(list(y), dtype=float)
    sv = np.asarray(list(score), dtype=float)
    good = np.isfinite(yv) & np.isfinite(sv)
    yv, sv = yv[good], sv[good]
    positives = float(yv.sum())
    if len(yv) == 0 or positives <= 0:
        return float("nan")
    order = np.argsort(-sv, kind="stable")
    ys = yv[order]
    precision = np.cumsum(ys) / np.arange(1, len(ys) + 1)
    return float(np.sum(precision * ys) / positives)


def empirical_percentile(train: pd.Series, values: pd.Series) -> pd.Series:
    ref = np.sort(train.dropna().astype(float).to_numpy())
    if len(ref) == 0:
        return pd.Series(np.nan, index=values.index)
    vals = values.astype(float).to_numpy()
    out = np.searchsorted(ref, vals, side="right") / len(ref)
    out[~np.isfinite(vals)] = np.nan
    return pd.Series(out, index=values.index)


def episode_anchors(index: pd.DatetimeIndex, fire: pd.Series, mask: pd.Series) -> list[pd.Timestamp]:
    pos = {d: i for i, d in enumerate(index)}
    dates = [d for d in index if bool(mask.loc[d]) and bool(fire.loc[d])]
    anchors: list[pd.Timestamp] = []
    last_fire_pos: int | None = None
    for d in dates:
        p = pos[d]
        if last_fire_pos is None or p - last_fire_pos > 3:
            anchors.append(d)
        last_fire_pos = p
    return anchors


def brier_skill(y: pd.Series, p: pd.Series, baseline: pd.Series) -> float:
    good = y.notna() & p.notna() & baseline.notna()
    if not good.any():
        return float("nan")
    b = float(np.mean((y[good] - p[good]) ** 2))
    b0 = float(np.mean((y[good] - baseline[good]) ** 2))
    return float(1 - b / b0) if b0 > 0 else float("nan")


def calibration_fit(y: pd.Series, p: pd.Series) -> LogisticFit:
    good = y.notna() & p.notna()
    if not good.any():
        return LogisticFit(float("nan"), float("nan"), False)
    clipped = p[good].clip(1e-6, 1 - 1e-6)
    logits = np.log(clipped / (1 - clipped))
    return fit_logistic(logits, y[good], l2=1e-8)


def moving_block_bootstrap(y: pd.Series, p: pd.Series, seed: int) -> dict[str, float]:
    good = y.notna() & p.notna()
    yv, pv = y[good].to_numpy(float), p[good].to_numpy(float)
    n = len(yv)
    if n == 0 or yv.sum() == 0:
        return {"ratio": float("nan"), "lb90": float("nan"), "ci95_lo": float("nan"),
                "ci95_hi": float("nan"), "p_le_1": float("nan")}
    ap = average_precision(yv, pv)
    prev = float(yv.mean())
    ratio = ap / prev if prev > 0 else float("nan")
    rng = np.random.default_rng(seed)
    ratios: list[float] = []
    blocks = math.ceil(n / BLOCK_LEN)
    for _ in range(BOOTSTRAPS):
        starts = rng.integers(0, n, size=blocks)
        idx = np.concatenate([(s + np.arange(BLOCK_LEN)) % n for s in starts])[:n]
        yb, pb = yv[idx], pv[idx]
        if yb.sum() <= 0 or yb.mean() <= 0:
            continue
        ratios.append(average_precision(yb, pb) / float(yb.mean()))
    if not ratios:
        return {"ratio": ratio, "lb90": float("nan"), "ci95_lo": float("nan"),
                "ci95_hi": float("nan"), "p_le_1": float("nan")}
    arr = np.asarray(ratios)
    return {
        "ratio": ratio,
        "lb90": float(np.quantile(arr, 0.10)),
        "ci95_lo": float(np.quantile(arr, 0.025)),
        "ci95_hi": float(np.quantile(arr, 0.975)),
        "p_le_1": float((np.sum(arr <= 1.0) + 1) / (len(arr) + 1)),
    }


def bh_adjust(pvals: list[float]) -> list[float]:
    arr = np.asarray(pvals, dtype=float)
    out = np.full(len(arr), np.nan)
    good = np.isfinite(arr)
    vals = arr[good]
    if not len(vals):
        return out.tolist()
    order = np.argsort(vals)
    ranked = vals[order]
    m = len(vals)
    adjusted = np.minimum.accumulate((ranked * m / np.arange(1, m + 1))[::-1])[::-1]
    restored = np.empty(m)
    restored[order] = np.minimum(adjusted, 1.0)
    out[np.flatnonzero(good)] = restored
    return out.tolist()


def parquet_inventory(path: Path) -> dict[str, Any]:
    d = pd.read_parquet(path)
    idx = pd.to_datetime(d.index)
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "rows": len(d),
        "columns": list(d.columns),
        "first_index": str(idx.min()),
        "last_index": str(idx.max()),
    }


def load_series(path: Path, preferred: tuple[str, ...], index: pd.DatetimeIndex) -> pd.Series:
    d = pd.read_parquet(path)
    col = next((c for c in preferred if c in d.columns), d.columns[0])
    s = d[col].astype(float).sort_index()
    s.index = pd.to_datetime(s.index).normalize()
    return s.reindex(index).ffill(limit=3)


def build_daily() -> tuple[pd.DataFrame, list[str], list[Path]]:
    membership_path = DATA / "baskets" / "membership.json"
    raw = json.loads(membership_path.read_text(encoding="utf-8"))
    baskets = raw.get("baskets", raw)
    members: list[str] = []
    for key in lc.COHORT_KEYS:
        for member in (baskets.get(key) or {}).get("members") or []:
            ticker = member.get("ticker")
            if ticker and member.get("removed") is None and ticker not in members:
                members.append(ticker)

    mat_all = lc._load_closes(members)
    mat = lc._fresh_members(mat_all)
    spy = lc._load_spy()
    if mat.empty or spy is None:
        raise RuntimeError("required current-membership panel or SPY is empty")
    comp = lc._compute(mat, spy)
    states, sinces = lc._state_machine(comp["z_series"], comp["med_dd_series"], comp["carnage_ema"])
    idx = mat.index
    spy_a = spy.reindex(idx)
    daily = pd.DataFrame(index=idx)
    daily.index.name = "observation_session"
    daily["state"] = states
    daily["state_since"] = pd.to_datetime(sinces)
    daily["fragile"] = daily["state"].isin(["CRACKING", "BROKEN"]).astype(int)
    daily["z_vel"] = comp["z_series"]
    daily["med_dd"] = comp["med_dd_series"]
    daily["carnage_share_ema"] = comp["carnage_ema"]
    daily["share10"] = comp["share10"]
    daily["share20"] = comp["share20"]
    daily["share30"] = comp["share30"]
    daily["spy_close"] = spy_a
    daily["spy_ma50"] = spy_a.rolling(50, min_periods=50).mean()
    daily["b_ma_break"] = (daily["spy_close"] < daily["spy_ma50"]).astype(float)
    daily["member_count_current"] = len(members)
    daily["member_prices_at_t"] = mat.notna().sum(axis=1)
    daily["member_coverage_t"] = daily["member_prices_at_t"] / len(members)

    dgs10_path = DATA / "fred" / "DGS10.parquet"
    dgs30_path = DATA / "fred" / "DGS30.parquet"
    vix_path = DATA / "fred" / "VIXCLS.parquet"
    daily["dgs10"] = load_series(dgs10_path, ("us10y",), idx)
    daily["dgs30"] = load_series(dgs30_path, ("us30y",), idx)
    daily["vix_level"] = load_series(vix_path, ("vix_close",), idx)
    daily["d_dgs10_1d"] = daily["dgs10"].diff(1)
    daily["d_dgs30_1d"] = daily["dgs30"].diff(1)
    daily["d_dgs10_3d"] = daily["dgs10"].diff(3)
    daily["d_dgs30_3d"] = daily["dgs30"].diff(3)
    spy_ret = daily["spy_close"].pct_change(fill_method=None)
    daily["rv_spy_5d"] = spy_ret.rolling(5, min_periods=5).var(ddof=0)
    daily["drv_spy_5d"] = daily["rv_spy_5d"].diff(1)
    daily["rv_252_median"] = daily["rv_spy_5d"].rolling(252, min_periods=126).median()
    daily["b_rv_target"] = (daily["rv_spy_5d"] > daily["rv_252_median"]).astype(float)

    for h in HORIZONS:
        member_ret = mat.shift(-h) / mat - 1.0
        spy_h = spy_a.shift(-h) / spy_a - 1.0
        resid = member_ret.sub(spy_h, axis=0)
        median = resid.median(axis=1)
        daily[f"cohort_median_resid_{h}s"] = median
        pair_count = (mat.notna() & mat.shift(-h).notna()).sum(axis=1)
        daily[f"member_pair_count_{h}s"] = pair_count
        daily[f"member_pair_coverage_{h}s"] = pair_count / len(members)
        for severity in (3, 5):
            name = f"y_resid_dd_ge{severity}_{h}s"
            daily[name] = np.where(median.notna(), (median <= -severity / 100).astype(float), np.nan)
            lead = pd.Series(np.nan, index=idx)
            positives = daily[name] == 1
            for d in idx[positives.fillna(False)]:
                p = idx.get_loc(d)
                found = np.nan
                for k in range(1, h + 1):
                    if p + k >= len(idx):
                        break
                    r = (mat.iloc[p + k] / mat.iloc[p] - 1.0) - (spy_a.iloc[p + k] / spy_a.iloc[p] - 1.0)
                    if float(r.median(skipna=True)) <= -severity / 100:
                        found = float(k)
                        break
                lead.loc[d] = found
            daily[f"lead_ge{severity}_{h}s"] = lead

    source_paths = [membership_path, DATA / "yahoo" / "SPY.parquet", dgs10_path, dgs30_path, vix_path]
    source_paths.extend(DATA / "baskets" / "ohlcv" / f"{t}.parquet" for t in members)
    digest_material = "\n".join(f"{p.relative_to(ROOT)}:{sha256(p)}" for p in source_paths)
    vintage_id = hashlib.sha256(digest_material.encode()).hexdigest()[:16]
    daily["lane"] = LANE
    daily["membership_basis"] = MEMBERSHIP_BASIS
    daily["definition_schema"] = lc.SCHEMA
    daily["code_commit_sha"] = BASE_COMMIT
    daily["code_blob_sha"] = CODE_BLOB
    daily["input_vintage_id"] = vintage_id
    daily["rate_revision_basis"] = "latest_revised_no_available_at_secondary_only"
    daily["quality_state"] = "COUNTERFACTUAL_NOT_PIT"
    daily["out_of_design_sample"] = daily.index >= INCIDENT_START
    return daily, members, source_paths


def fold_masks(index: pd.DatetimeIndex, held: str) -> tuple[pd.Series, pd.Series]:
    design = (index >= DESIGN_START) & (index <= DESIGN_END)
    start, end = ERAS[held]
    test = pd.Series(design & (index >= start) & (index <= end), index=index)
    positions = np.flatnonzero(test.to_numpy())
    if len(positions) > 6:
        test.iloc[positions[:3]] = False
        test.iloc[positions[-3:]] = False
    train = pd.Series(design & ~((index >= start) & (index <= end)), index=index)
    if len(positions):
        lo, hi = positions[0], positions[-1]
        train.iloc[max(0, lo - 3):lo] = False
        train.iloc[hi + 1:min(len(index), hi + 4)] = False
    return train, test


def hypothesis_fold(daily: pd.DataFrame, hypothesis: str, held: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    train_mask, test_mask = fold_masks(daily.index, held)
    if hypothesis == "GD-H1":
        q10 = float(daily.loc[train_mask, "d_dgs10_3d"].quantile(0.80))
        q30 = float(daily.loc[train_mask, "d_dgs30_3d"].quantile(0.80))
        score_train = pd.concat([
            empirical_percentile(daily.loc[train_mask, "d_dgs10_3d"], daily["d_dgs10_3d"]),
            empirical_percentile(daily.loc[train_mask, "d_dgs30_3d"], daily["d_dgs30_3d"]),
        ], axis=1).max(axis=1) * daily["fragile"]
        fire = (daily["fragile"] == 1) & ((daily["d_dgs10_3d"] > q10) | (daily["d_dgs30_3d"] > q30))
        thresholds = {"d_dgs10_3d_q80": q10, "d_dgs30_3d_q80": q30}
    else:
        qvol = float(daily.loc[train_mask, "drv_spy_5d"].quantile(0.80))
        score_train = empirical_percentile(daily.loc[train_mask, "drv_spy_5d"], daily["drv_spy_5d"]) * daily["fragile"]
        fire = (daily["fragile"] == 1) & (daily["drv_spy_5d"] > qvol)
        thresholds = {"drv_spy_5d_q80": qvol}

    train_anchors = episode_anchors(daily.index, fire.fillna(False), train_mask)
    test_anchors = episode_anchors(daily.index, fire.fillna(False), test_mask)
    raw_train_fire_n = int((fire & train_mask).sum())
    raw_test_fire_n = int((fire & test_mask).sum())
    rows: list[dict[str, Any]] = []
    for endpoint in ENDPOINTS:
        y_train = daily.loc[train_anchors, endpoint].dropna()
        s_train = score_train.reindex(y_train.index)
        fit = fit_logistic(s_train, y_train, l2=1.0)
        prev = float(y_train.mean()) if len(y_train) else float("nan")
        for anchor in test_anchors:
            y = daily.at[anchor, endpoint]
            score = score_train.at[anchor]
            p = float(fit.predict(np.array([score]))[0]) if np.isfinite(score) else float("nan")
            horizon = 1 if endpoint.endswith("_1s") else 3
            severity = 3 if "ge3" in endpoint else 5
            source_fields = [daily.at[anchor, "fragile"]]
            if hypothesis == "GD-H1":
                source_fields += [daily.at[anchor, "d_dgs10_3d"], daily.at[anchor, "d_dgs30_3d"]]
            else:
                source_fields += [daily.at[anchor, "drv_spy_5d"], daily.at[anchor, "vix_level"]]
            source_cov = float(np.mean([pd.notna(v) for v in source_fields]))
            rows.append({
                "lane": LANE,
                "membership_basis": MEMBERSHIP_BASIS,
                "hypothesis": hypothesis,
                "endpoint": endpoint,
                "held_out_era": held,
                "episode_anchor": anchor,
                "raw_fire_n_held_era": raw_test_fire_n,
                "score": score,
                "probability_oos": p,
                "training_prevalence": prev,
                "outcome": y,
                "lead_sessions": daily.at[anchor, f"lead_ge{severity}_{horizon}s"],
                "member_coverage": daily.at[anchor, f"member_pair_coverage_{horizon}s"],
                "required_source_coverage": source_cov,
                "calibrator_estimable": fit.estimable,
                "calibrator_intercept": fit.intercept,
                "calibrator_slope": fit.slope,
                "input_vintage_id": daily.at[anchor, "input_vintage_id"],
                "code_commit_sha": BASE_COMMIT,
                "code_blob_sha": CODE_BLOB,
                "quality_state": "COUNTERFACTUAL_NOT_PIT",
            })
    return rows, {"hypothesis": hypothesis, "held_out_era": held,
                  "train_episode_n": len(train_anchors), "test_episode_n": len(test_anchors),
                  "train_raw_fire_n": raw_train_fire_n, "test_raw_fire_n": raw_test_fire_n,
                  "thresholds": thresholds}


def score_endpoint(episodes: pd.DataFrame, hypothesis: str, endpoint: str, seed: int) -> dict[str, Any]:
    e = episodes[(episodes.hypothesis == hypothesis) & (episodes.endpoint == endpoint)].copy()
    e = e.sort_values("episode_anchor")
    y, p = e["outcome"].astype(float), e["probability_oos"].astype(float)
    prev = float(y.mean()) if len(y) else float("nan")
    ap = average_precision(y, p)
    boot = moving_block_bootstrap(y, p, seed)
    brier_overall = brier_skill(y, p, e["training_prevalence"].astype(float))
    half_skills: dict[str, float] = {}
    half_signs: dict[str, float] = {}
    for name, (start, end) in HALVES.items():
        mask = (e.episode_anchor >= start) & (e.episode_anchor <= end)
        half_skills[name] = brier_skill(y[mask], p[mask], e.loc[mask, "training_prevalence"].astype(float))
        fit = fit_logistic(e.loc[mask, "score"], y[mask], l2=1.0)
        half_signs[name] = fit.slope if fit.estimable else float("nan")
    cal = calibration_fit(y, p)
    loco: dict[str, float] = {}
    for name, (start, end) in CRISES.items():
        keep = ~((e.episode_anchor >= start) & (e.episode_anchor <= end))
        fit = fit_logistic(e.loc[keep, "score"], y[keep], l2=1.0)
        loco[name] = fit.slope if fit.estimable else float("nan")
    lead = e.loc[y == 1, "lead_sessions"].dropna().astype(float)
    false = e.loc[y == 0].assign(quarter=lambda x: x.episode_anchor.dt.to_period("Q"))
    false_counts = false.groupby("quarter").size()
    raw_fire_n = int(e.groupby("held_out_era")["raw_fire_n_held_era"].first().sum()) if len(e) else 0
    era_n = int(e.loc[e.outcome.notna(), "held_out_era"].nunique())
    baselines: dict[str, float] = {}
    # Baseline fields are attached below after joining daily values.
    for col in ["b_leadership", "b_vix_pct", "b_rv_pct", "b_rv_target", "b_ma_break"]:
        if col in e:
            baselines[col] = average_precision(y, e[col])
    best_baseline = max((v for v in baselines.values() if np.isfinite(v)), default=float("nan"))
    return {
        "lane": LANE,
        "membership_basis": MEMBERSHIP_BASIS,
        "hypothesis": hypothesis,
        "endpoint": endpoint,
        "primary_verdict": "BLOCKED",
        "primary_blocker": "PIT cohort membership is not reconstructable for 2016-01-04..2026-07-31",
        "secondary_status": "SECONDARY_ONLY_NOT_PROMOTION_ELIGIBLE",
        "effective_N": len(e),
        "raw_fire_N": raw_fire_n,
        "adverse_N": int(y.sum()) if len(y) else 0,
        "distinct_months": int(e.episode_anchor.dt.to_period("M").nunique()) if len(e) else 0,
        "era_N": era_n,
        "post_2020_episode_N": int((e.episode_anchor >= pd.Timestamp("2021-01-01")).sum()),
        "prevalence": prev,
        "oos_average_precision": ap,
        "ap_over_prevalence": boot["ratio"],
        "ap_ratio_lb90": boot["lb90"],
        "ap_ratio_ci95_lo": boot["ci95_lo"],
        "ap_ratio_ci95_hi": boot["ci95_hi"],
        "ap_lift_p_one_sided": boot["p_le_1"],
        "brier_skill_overall": brier_overall,
        "brier_skill_half_1": half_skills["H1_2016_2020"],
        "brier_skill_half_2": half_skills["H2_2021_2026H1"],
        "calibration_intercept": cal.intercept,
        "calibration_slope": cal.slope,
        "calibration_estimable": cal.estimable,
        "sign_slope_half_1": half_signs["H1_2016_2020"],
        "sign_slope_half_2": half_signs["H2_2021_2026H1"],
        "loco_slopes_json": json.dumps(loco, sort_keys=True),
        "lead_N": len(lead),
        "lead_median": float(lead.median()) if len(lead) else float("nan"),
        "lead_p25": float(lead.quantile(0.25)) if len(lead) else float("nan"),
        "lead_p75": float(lead.quantile(0.75)) if len(lead) else float("nan"),
        "false_episode_max_per_quarter": int(false_counts.max()) if len(false_counts) else 0,
        "required_source_coverage": float(e.required_source_coverage.mean()) if len(e) else float("nan"),
        "member_coverage_mean": float(e.member_coverage.mean()) if len(e) else float("nan"),
        "best_baseline_ap": best_baseline,
        "baseline_ap_json": json.dumps(baselines, sort_keys=True),
        "temporal_integrity_gate": False,
        "sample_gate": bool(len(e) >= 30 and y.sum() >= 12 and era_n >= 3 and (e.episode_anchor >= pd.Timestamp("2021-01-01")).any()),
        "ap_gate": bool(np.isfinite(boot["ratio"]) and boot["ratio"] >= 1.25 and np.isfinite(boot["lb90"]) and boot["lb90"] > 1.0),
        "brier_gate": bool(all(np.isfinite(v) and v > 0 for v in half_skills.values())),
        "calibration_gate": bool(cal.estimable and 0.70 <= cal.slope <= 1.30),
        "sign_stability_gate": bool(all(np.isfinite(v) and v > 0 for v in half_signs.values()) and
                                    all((not np.isfinite(v)) or v >= 0 for v in loco.values())),
        "lead_gate": bool(len(lead) and lead.median() >= 1 and lead.quantile(0.25) > 0),
        "false_alarm_gate": bool((int(false_counts.max()) if len(false_counts) else 0) <= 2),
        "coverage_gate": bool(len(e) and e.required_source_coverage.mean() >= 0.80),
        "baseline_nonredundancy_gate": bool(np.isfinite(ap) and (not np.isfinite(best_baseline) or ap > best_baseline)),
    }


def attach_baselines(episodes: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    out = episodes.copy()
    out["episode_anchor"] = pd.to_datetime(out["episode_anchor"])
    values: dict[str, list[float]] = {k: [] for k in ["b_leadership", "b_vix_pct", "b_rv_pct", "b_rv_target", "b_ma_break"]}
    for row in out.itertuples():
        train_mask, _ = fold_masks(daily.index, row.held_out_era)
        d = row.episode_anchor
        values["b_leadership"].append(1.0 if daily.at[d, "state"] == "BROKEN" else 0.5)
        values["b_vix_pct"].append(float(empirical_percentile(daily.loc[train_mask, "vix_level"], daily.loc[[d], "vix_level"]).iloc[0]))
        values["b_rv_pct"].append(float(empirical_percentile(daily.loc[train_mask, "rv_spy_5d"], daily.loc[[d], "rv_spy_5d"]).iloc[0]))
        values["b_rv_target"].append(float(daily.at[d, "b_rv_target"]))
        values["b_ma_break"].append(float(daily.at[d, "b_ma_break"]))
    for key, vals in values.items():
        out[key] = vals
    return out


def main() -> None:
    if git("status", "--porcelain", "--", "data", "site"):
        raise RuntimeError("refusing: data/ or site/ is dirty before GD-1C run")

    daily, members, source_paths = build_daily()
    design = daily[(daily.index >= DESIGN_START) & (daily.index <= DESIGN_END)].copy()
    incident = daily[daily.index >= INCIDENT_START].copy()
    final_thresholds = {
        "d_dgs10_3d_q80": float(design["d_dgs10_3d"].quantile(0.80)),
        "d_dgs30_3d_q80": float(design["d_dgs30_3d"].quantile(0.80)),
        "drv_spy_5d_q80": float(design["drv_spy_5d"].quantile(0.80)),
        "vix_level_q80_baseline": float(design["vix_level"].quantile(0.80)),
        "rv_spy_5d_q80_baseline": float(design["rv_spy_5d"].quantile(0.80)),
    }
    incident["h1_fire_full_design_threshold"] = (
        (incident["fragile"] == 1)
        & ((incident["d_dgs10_3d"] > final_thresholds["d_dgs10_3d_q80"])
           | (incident["d_dgs30_3d"] > final_thresholds["d_dgs30_3d_q80"]))
    )
    incident["h2_fire_full_design_threshold"] = (
        (incident["fragile"] == 1)
        & (incident["drv_spy_5d"] > final_thresholds["drv_spy_5d_q80"])
    )

    rows: list[dict[str, Any]] = []
    fold_receipts: list[dict[str, Any]] = []
    for hypothesis in ("GD-H1", "GD-H2"):
        for held in ERAS:
            fold_rows, receipt = hypothesis_fold(daily, hypothesis, held)
            rows.extend(fold_rows)
            fold_receipts.append(receipt)
    episodes = attach_baselines(pd.DataFrame(rows), daily)

    score_rows: list[dict[str, Any]] = []
    for i, (hypothesis, endpoint) in enumerate(
        (h, e) for h in ("GD-H1", "GD-H2") for e in ENDPOINTS
    ):
        score_rows.append(score_endpoint(episodes, hypothesis, endpoint, RNG_SEED + i))
    qvals = bh_adjust([float(r["ap_lift_p_one_sided"]) for r in score_rows])
    for row, q in zip(score_rows, qvals):
        row["bh_q_value"] = q
        row["bh_gate"] = bool(np.isfinite(q) and q <= 0.10)
        row["all_secondary_numeric_gates"] = bool(all(row[k] for k in [
            "sample_gate", "ap_gate", "brier_gate", "calibration_gate",
            "sign_stability_gate", "lead_gate", "false_alarm_gate",
            "coverage_gate", "baseline_nonredundancy_gate", "bh_gate",
        ]))

    # Per-row reconstruction manifest.  The primary lane has zero guessed rows.
    columns = [
        "lane", "membership_basis", "definition_schema", "code_commit_sha", "code_blob_sha",
        "input_vintage_id", "rate_revision_basis", "quality_state", "out_of_design_sample",
        "state", "state_since", "fragile", "z_vel", "med_dd", "carnage_share_ema",
        "share10", "share20", "share30", "member_count_current", "member_prices_at_t",
        "member_coverage_t", "dgs10", "dgs30", "d_dgs10_1d", "d_dgs30_1d",
        "d_dgs10_3d", "d_dgs30_3d", "vix_level", "rv_spy_5d", "drv_spy_5d",
        "cohort_median_resid_1s", "cohort_median_resid_3s", "member_pair_count_1s",
        "member_pair_count_3s", "member_pair_coverage_1s", "member_pair_coverage_3s",
        *ENDPOINTS,
    ]
    reconstruction = daily.loc[(daily.index >= DESIGN_START), columns].copy()
    reconstruction.to_csv(OUT / "GD1C_RECONSTRUCTION_ROWS.csv", index=True, float_format="%.10g")
    episodes.to_csv(OUT / "GD1C_EPISODE_LEDGER.csv", index=False, float_format="%.10g")
    scorecard = pd.DataFrame(score_rows)
    scorecard.to_csv(OUT / "GD1C_GATE_SCORECARD.csv", index=False, float_format="%.10g")
    incident_columns = [
        "lane", "membership_basis", "quality_state", "state", "state_since", "fragile",
        "z_vel", "med_dd", "carnage_share_ema", "d_dgs10_3d", "d_dgs30_3d",
        "drv_spy_5d", "vix_level", "h1_fire_full_design_threshold",
        "h2_fire_full_design_threshold", "cohort_median_resid_1s", "cohort_median_resid_3s",
        *ENDPOINTS,
    ]
    incident.loc[:, incident_columns].to_csv(
        OUT / "GD1C_INCIDENT_COVERAGE.csv", index=True, float_format="%.10g"
    )

    membership_path = DATA / "baskets" / "membership.json"
    membership_history = git("log", "--follow", "--format=%H|%cI|%s", "--", str(membership_path.relative_to(ROOT))).splitlines()
    inventories: list[dict[str, Any]] = []
    for p in source_paths:
        if p.suffix == ".parquet":
            inventories.append(parquet_inventory(p))
        else:
            inventories.append({
                "path": str(p.relative_to(ROOT)), "sha256": sha256(p),
                "bytes": p.stat().st_size, "available_at_basis": "no first-known per-member membership receipt",
            })
    manifest = {
        "schema": "grey_deer.gd1c.reconstruction_manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workstream": "WS:GREY-DEER-RISK-INTELLIGENCE",
        "wave": "GD-1C",
        "preregistration_freeze_sha": PREREG_FREEZE,
        "analysis_head": git("rev-parse", "HEAD"),
        "base_commit_sha": BASE_COMMIT,
        "leadership_crack_blob_sha": CODE_BLOB,
        "analysis_script_sha256": sha256(Path(__file__)),
        "definition_schema": lc.SCHEMA,
        "design_window": [str(DESIGN_START.date()), str(DESIGN_END.date())],
        "primary_lane": {
            "lane": "pit_membership",
            "verdict": "BLOCKED",
            "evaluated_rows": 0,
            "gap": "No point-in-time cohort-membership lineage spans 2016-01-04..2026-07-31.",
            "evidence": [
                "data/baskets/membership.json first enters tracked history on 2026-06-14",
                "the four cohort baskets are curated in 2026",
                "retrospective member added dates are not first-known membership receipts",
                "membership rows do not carry available_at / observed_at clocks",
            ],
            "minimum_lawful_substitute": "def_current_cf current-membership truncate-and-recompute, secondary only",
        },
        "secondary_lane": {
            "lane": LANE,
            "membership_basis": MEMBERSHIP_BASIS,
            "member_n": len(members),
            "members": members,
            "design_row_n": len(design),
            "incident_row_n": len(incident),
            "rate_revision_basis": "latest_revised_no_available_at_secondary_only",
            "full_design_thresholds": final_thresholds,
        },
        "membership_git_history": membership_history,
        "membership_earliest_tracked_receipt": membership_history[-1] if membership_history else None,
        "fold_receipts": fold_receipts,
        "input_inventories": inventories,
        "output_files": [
            "GD1C_RECONSTRUCTION_ROWS.csv", "GD1C_EPISODE_LEDGER.csv",
            "GD1C_GATE_SCORECARD.csv", "GD1C_INCIDENT_COVERAGE.csv",
            "GD1C_RECONSTRUCTION_MANIFEST.json",
        ],
        "authority": "No live market, Prophet, Portfolio, alert, rank, sizing, gate, or execution authority.",
    }
    json_dump(OUT / "GD1C_RECONSTRUCTION_MANIFEST.json", manifest)
    summary = {
        "primary_verdicts": {"GD-H1": "BLOCKED", "GD-H2": "BLOCKED"},
        "primary_gap": manifest["primary_lane"]["gap"],
        "secondary_gate_scorecard": score_rows,
        "artifact_sha256": {},
        "authority": manifest["authority"],
    }
    for name in ["GD1C_RECONSTRUCTION_ROWS.csv", "GD1C_EPISODE_LEDGER.csv",
                 "GD1C_GATE_SCORECARD.csv", "GD1C_INCIDENT_COVERAGE.csv",
                 "GD1C_RECONSTRUCTION_MANIFEST.json"]:
        summary["artifact_sha256"][name] = sha256(OUT / name)
    json_dump(OUT / "GD1C_RUN_RECEIPT.json", summary)

    after = git("status", "--porcelain", "--", "data", "site")
    if after:
        raise RuntimeError(f"forbidden data/site mutation after run:\n{after}")
    print(json.dumps({
        "primary_verdicts": summary["primary_verdicts"],
        "secondary_rows": len(reconstruction),
        "secondary_episode_endpoint_rows": len(episodes),
        "scorecards": len(score_rows),
        "outputs": sorted(summary["artifact_sha256"]),
    }, indent=2))


if __name__ == "__main__":
    main()
