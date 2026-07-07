"""Research study: OPEX cycle, vanna, charm, and equity pricing.

This is a research-only harness. It reads:
  * long daily prices from data/yahoo/*.parquet for calendar/OPEX tests;
  * ThetaData EOD greeks + OI from /Users/chriswong/theta-ops-wt/data/thetadata_eod
    for OI-weighted gamma/vanna/charm studies.

Outputs:
  reports/artifacts/options_opex_vanna_charm_results.json
  reports/artifacts/options_opex_vanna_charm_summary.md

Epistemic boundaries:
  * dealer sign is the repo's existing long-call / short-put convention, not observed truth;
  * OI is shifted one observation inside each contract series before use;
  * cross-sectional tests collapse to one IC or spread per date, then use HAC t-stats;
  * this script prints nulls and robustness checks; it does not wire any score path.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.opex import expiration_days, tag as opex_tag


THETA_STORE = Path("/Users/chriswong/theta-ops-wt/data/thetadata_eod")
YAHOO_DIR = Path("/Users/chriswong/theta-ops-wt/data/yahoo")
OUT_JSON = Path("reports/artifacts/options_opex_vanna_charm_results.json")
OUT_MD = Path("reports/artifacts/options_opex_vanna_charm_summary.md")

MULT = 100.0
PM = 0.01
MIN_ROOTS_PER_DATE = 20

CALENDAR_ROOTS = [
    "SPY", "QQQ", "IWM", "DIA",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SMH", "SOXX", "XBI", "KRE", "ARKK",
]

GREEK_ERAS = [
    ("Era1_2017_2019", "2017-01-01", "2019-12-31"),
    ("Era2_2020_2022", "2020-01-01", "2022-12-31"),
    ("Era3_2023_2026", "2023-01-01", "2026-12-31"),
]

CALENDAR_ERAS = [
    ("Full", "1993-01-01", "2026-12-31"),
    ("Pre_weeklies_1993_2004", "1993-01-01", "2004-12-31"),
    ("Weeklies_2005_2016", "2005-01-01", "2016-12-31"),
    ("Modern_2017_2022", "2017-01-01", "2022-12-31"),
    ("ZeroDTE_2023_2026", "2023-01-01", "2026-12-31"),
]


def _f(x: Any, nd: int = 6) -> float | None:
    try:
        y = float(x)
    except Exception:
        return None
    if not np.isfinite(y):
        return None
    return round(y, nd)


def _hac_ttest(x: np.ndarray, lag: int | None = None) -> tuple[float, float, int]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 8:
        return float("nan"), float("nan"), n
    mu = float(np.mean(x))
    if lag is None:
        lag = max(int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))), 1)
    lag = max(1, min(lag, n - 2))
    resid = x - mu
    gamma0 = float(np.dot(resid, resid) / n)
    nw_var = gamma0
    for j in range(1, lag + 1):
        gamma_j = float(np.dot(resid[j:], resid[:-j]) / n)
        nw_var += 2.0 * (1.0 - j / (lag + 1.0)) * gamma_j
    se = math.sqrt(max(nw_var, 1e-30) / n)
    t = mu / se
    p = float(2.0 * stats.t.sf(abs(t), df=max(n - 1, 1)))
    return float(t), p, n


def _overlap_lag(n: int, horizon: int) -> int:
    auto = max(int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))), 1)
    return max(1, min(max(auto, 2 * horizon), n - 2))


def _bh_fdr(rows: list[dict[str, Any]], p_key: str = "p", alpha: float = 0.10) -> None:
    valid = [(i, float(r[p_key])) for i, r in enumerate(rows)
             if r.get(p_key) is not None and np.isfinite(float(r[p_key]))]
    if not valid:
        return
    valid.sort(key=lambda t: t[1])
    m = len(valid)
    adj = [None] * len(rows)
    rejects = [False] * len(rows)
    running = 1.0
    for rank_from_end, (idx, p) in enumerate(reversed(valid), start=1):
        rank = m - rank_from_end + 1
        running = min(running, p * m / rank)
        adj[idx] = min(running, 1.0)
    for rank, (idx, p) in enumerate(valid, start=1):
        rejects[idx] = bool(p <= (rank / m) * alpha)
        rows[idx]["bh_rank"] = rank
    for i, r in enumerate(rows):
        r["bh_adj_p"] = _f(adj[i], 6) if adj[i] is not None else None
        r["bh_reject_10pct"] = bool(rejects[i])
        r["bh_family_n"] = m


def _sort_num(x: Any) -> float:
    if x is None:
        return float("inf")
    try:
        y = float(x)
    except Exception:
        return float("inf")
    return y if np.isfinite(y) else float("inf")


def _read_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(path, columns=columns)
    except Exception:
        df = pd.read_parquet(path)
        if columns is not None:
            keep = [c for c in columns if c in df.columns]
            df = df[keep]
    return df.drop_duplicates()


def _load_yahoo_close(root: str) -> pd.Series | None:
    p = YAHOO_DIR / f"{root}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if "close" in df.columns:
        s = df["close"].copy()
    elif "close_price" in df.columns:
        s = df["close_price"].copy()
    else:
        return None
    s.index = pd.to_datetime(s.index)
    s = pd.to_numeric(s, errors="coerce").dropna()
    s.name = root
    return s


def _era_slice(df: pd.DataFrame, date_col: str, start: str, end: str) -> pd.DataFrame:
    d = pd.to_datetime(df[date_col])
    return df[(d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))].copy()


def run_calendar_study() -> dict[str, Any]:
    """Long price-history OPEX calendar tests.

    Event definitions use trading-day offsets around the standard monthly expiration day
    (third Friday, or previous trading day when the Friday is absent from the series).
    """
    event_rows: list[dict[str, Any]] = []
    phase_rows: list[dict[str, Any]] = []

    for root in CALENDAR_ROOTS:
        close = _load_yahoo_close(root)
        if close is None or len(close) < 500:
            continue
        idx = pd.DatetimeIndex(close.index)
        exp = expiration_days(idx)
        pos = {d: i for i, d in enumerate(idx)}
        base5 = close.pct_change(5, fill_method=None).shift(-5).dropna().mean()

        for exp_day, is_quad in exp.items():
            i = pos.get(exp_day)
            if i is None or i < 5 or i + 6 >= len(idx):
                continue
            pre_start = idx[i - 5]
            placebo_start = idx[max(i - 10, 0)]
            placebo_end = idx[i - 5]
            post_end = idx[i + 5]
            week_ret = close.loc[exp_day] / close.loc[pre_start] - 1.0
            post_ret = close.loc[post_end] / close.loc[exp_day] - 1.0
            placebo_ret = close.loc[placebo_end] / close.loc[placebo_start] - 1.0
            event_rows.append({
                "root": root,
                "exp_date": str(exp_day.date()),
                "date": exp_day,
                "is_quad": bool(is_quad),
                "opex_week_ret": float(week_ret),
                "opex_week_excess": float(week_ret - base5),
                "post_opex_ret": float(post_ret),
                "post_opex_excess": float(post_ret - base5),
                "placebo_week_ret": float(placebo_ret),
                "placebo_week_excess": float(placebo_ret - base5),
            })

        tags = opex_tag(idx)
        fwd5 = close.pct_change(5, fill_method=None).shift(-5)
        daily = pd.DataFrame({
            "root": root,
            "date": idx,
            "phase": tags["phase"].values,
            "is_quad_cycle": tags["is_quad_cycle"].values,
            "fwd5": fwd5.reindex(idx).values,
        }).dropna(subset=["fwd5"])
        phase_rows.extend(daily.to_dict("records"))

    events = pd.DataFrame(event_rows)
    phases = pd.DataFrame(phase_rows)
    out: dict[str, Any] = {"n_events": int(len(events)), "calendar_roots": sorted(set(events.get("root", [])))}
    if events.empty:
        return out

    event_stats = []
    for era, start, end in CALENDAR_ERAS:
        edf = _era_slice(events, "date", start, end)
        if edf.empty:
            continue
        # Collapse cross-root dependence by expiration date.
        by_exp = edf.groupby("exp_date").agg(
            opex_week_excess=("opex_week_excess", "mean"),
            post_opex_excess=("post_opex_excess", "mean"),
            placebo_week_excess=("placebo_week_excess", "mean"),
            quad=("is_quad", "max"),
        ).reset_index()
        for col, label, horizon in [
            ("opex_week_excess", "expiration_week_excess", 5),
            ("post_opex_excess", "post_expiration_week_excess", 5),
            ("placebo_week_excess", "placebo_prior_week_excess", 5),
        ]:
            arr = by_exp[col].to_numpy(float)
            t, p, n = _hac_ttest(arr, lag=_overlap_lag(len(arr), horizon))
            event_stats.append({
                "era": era,
                "test": label,
                "mean_pct": _f(np.nanmean(arr) * 100, 4),
                "t": _f(t, 4),
                "p": _f(p, 6),
                "n_months": int(n),
            })
        quad = by_exp[by_exp["quad"] == 1]
        nonquad = by_exp[by_exp["quad"] == 0]
        if len(quad) >= 20 and len(nonquad) >= 20:
            arr = quad["opex_week_excess"].to_numpy(float)
            t, p, n = _hac_ttest(arr, lag=_overlap_lag(len(arr), 5))
            event_stats.append({
                "era": era,
                "test": "quad_expiration_week_excess",
                "mean_pct": _f(np.nanmean(arr) * 100, 4),
                "t": _f(t, 4),
                "p": _f(p, 6),
                "n_months": int(n),
            })

    phase_stats = []
    if not phases.empty:
        for era, start, end in CALENDAR_ERAS:
            pdf = _era_slice(phases, "date", start, end)
            if pdf.empty:
                continue
            by_date_phase = pdf.groupby(["date", "phase"])["fwd5"].mean().unstack()
            if "mid_cycle" not in by_date_phase:
                continue
            for phase in ["opex_week", "post_opex"]:
                if phase not in by_date_phase:
                    continue
                gap = (by_date_phase[phase] - by_date_phase["mid_cycle"]).dropna().to_numpy(float)
                if len(gap) < 30:
                    continue
                t, p, n = _hac_ttest(gap, lag=_overlap_lag(len(gap), 5))
                phase_stats.append({
                    "era": era,
                    "test": f"daily_phase_{phase}_minus_mid_cycle_fwd5",
                    "mean_pct": _f(np.nanmean(gap) * 100, 4),
                    "t": _f(t, 4),
                    "p": _f(p, 6),
                    "n_dates": int(n),
                })

    _bh_fdr(event_stats, "p", alpha=0.10)
    out["event_stats"] = event_stats
    out["phase_stats"] = phase_stats
    out["event_sample_tail"] = events.tail(5).assign(date=events.tail(5)["date"].astype(str)).to_dict("records")
    return out


def _manifest_roots(max_roots: int | None = None) -> list[str]:
    p = THETA_STORE / "_manifest.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    roots = sorted(data.get("per_root", {}).keys())
    # Skip duplicate/index variants that can dominate cross-sectional stats.
    roots = [r for r in roots if r not in {"SPXW"}]
    if max_roots is not None:
        roots = roots[:max_roots]
    return roots


def _aggregate_root_year(root: str, year: int) -> pd.DataFrame:
    gpath = THETA_STORE / "greeks" / root / f"{year}.parquet"
    opath = THETA_STORE / "oi" / root / f"{year}.parquet"
    if not gpath.exists() or not opath.exists():
        return pd.DataFrame()
    gcols = [
        "date", "expiration", "strike", "right", "underlying_price",
        "gamma", "vanna", "charm", "delta", "implied_vol",
    ]
    ocols = ["date", "expiration", "strike", "right", "open_interest"]
    g = _read_parquet(gpath, gcols)
    oi = _read_parquet(opath, ocols)
    if g.empty or oi.empty:
        return pd.DataFrame()

    for df in (g, oi):
        df["date"] = pd.to_datetime(df["date"])
        df["expiration"] = pd.to_datetime(df["expiration"])
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
        df["right"] = df["right"].astype(str).str.upper()

    oi = oi.sort_values(["expiration", "strike", "right", "date"])
    oi["oi_signal"] = (
        oi.groupby(["expiration", "strike", "right"], sort=False)["open_interest"].shift(1)
    )
    oi = oi[["date", "expiration", "strike", "right", "oi_signal"]]

    m = g.merge(oi, on=["date", "expiration", "strike", "right"], how="left")
    if m.empty:
        return pd.DataFrame()

    m["spot"] = pd.to_numeric(m["underlying_price"], errors="coerce")
    # Median spot by date protects against rare row-level stale quote oddities.
    spot = m.groupby("date")["spot"].median().rename("spot_day")
    m = m.join(spot, on="date", how="left")
    m["dte"] = (m["expiration"] - m["date"]).dt.days
    m["mny"] = m["strike"] / m["spot_day"] - 1.0

    num_cols = ["gamma", "vanna", "charm", "delta", "implied_vol", "oi_signal", "spot_day"]
    for c in num_cols:
        m[c] = pd.to_numeric(m[c], errors="coerce")

    m = m[
        (m["dte"] > 0)
        & (m["dte"] <= 365)
        & (m["mny"].abs() <= 0.25)
        & (m["oi_signal"] > 0)
        & (m["spot_day"] > 0)
    ].copy()
    if m.empty:
        return pd.DataFrame()

    is_call = m["right"] == "C"
    sign = np.where(is_call, 1.0, -1.0)
    oi_arr = m["oi_signal"].to_numpy(float)
    spot_arr = m["spot_day"].to_numpy(float)

    m["_net_gex"] = sign * m["gamma"].to_numpy(float) * oi_arr * MULT * spot_arr**2 * PM
    m["_net_vanna"] = sign * m["vanna"].to_numpy(float) * oi_arr * MULT * spot_arr * PM
    m["_net_charm"] = sign * (m["charm"].to_numpy(float) / 365.0) * oi_arr * MULT * spot_arr
    m["_net_delta"] = sign * m["delta"].to_numpy(float) * oi_arr * MULT * spot_arr
    m["_abs_gex"] = np.abs(m["_net_gex"])
    m["_abs_vanna"] = np.abs(m["_net_vanna"])
    m["_abs_charm"] = np.abs(m["_net_charm"])
    m["_call_oi"] = np.where(is_call, oi_arr, 0.0)
    m["_put_oi"] = np.where(~is_call, oi_arr, 0.0)

    daily = m.groupby("date").agg(
        spot=("spot_day", "median"),
        n_contracts=("oi_signal", "size"),
        total_oi=("oi_signal", "sum"),
        call_oi=("_call_oi", "sum"),
        put_oi=("_put_oi", "sum"),
        net_gex=("_net_gex", "sum"),
        abs_gex=("_abs_gex", "sum"),
        net_vanna=("_net_vanna", "sum"),
        abs_vanna=("_abs_vanna", "sum"),
        net_charm=("_net_charm", "sum"),
        abs_charm=("_abs_charm", "sum"),
        net_delta=("_net_delta", "sum"),
    ).reset_index()

    for label, mask in [
        ("front7", m["dte"] <= 7),
        ("front30", m["dte"] <= 30),
    ]:
        sub = m[mask]
        if sub.empty:
            for c in ["oi", "abs_gex", "abs_charm"]:
                daily[f"{label}_{c}_share"] = np.nan
            continue
        s = sub.groupby("date").agg(
            oi=("oi_signal", "sum"),
            abs_gex=("_abs_gex", "sum"),
            abs_charm=("_abs_charm", "sum"),
        )
        daily = daily.merge(s.add_prefix(f"{label}_"), left_on="date", right_index=True, how="left")

    for c in ["front7_oi", "front7_abs_gex", "front7_abs_charm",
              "front30_oi", "front30_abs_gex", "front30_abs_charm"]:
        if c not in daily.columns:
            daily[c] = np.nan
    daily["front7_oi_share"] = daily["front7_oi"] / daily["total_oi"]
    daily["front7_abs_gex_share"] = daily["front7_abs_gex"] / daily["abs_gex"]
    daily["front7_abs_charm_share"] = daily["front7_abs_charm"] / daily["abs_charm"]
    daily["front30_oi_share"] = daily["front30_oi"] / daily["total_oi"]
    daily["front30_abs_gex_share"] = daily["front30_abs_gex"] / daily["abs_gex"]
    daily["front30_abs_charm_share"] = daily["front30_abs_charm"] / daily["abs_charm"]

    cand = m[
        (m["dte"].between(7, 60))
        & (m["mny"].abs() <= 0.08)
        & (m["implied_vol"] > 0)
    ].copy()
    if not cand.empty:
        cand["_iv_w"] = cand["implied_vol"] * cand["oi_signal"]
        iv = cand.groupby("date").agg(iv_w=("_iv_w", "sum"), iv_oi=("oi_signal", "sum"))
        iv["iv_proxy"] = iv["iv_w"] / iv["iv_oi"]
        daily = daily.merge(iv[["iv_proxy"]], left_on="date", right_index=True, how="left")
    else:
        daily["iv_proxy"] = np.nan

    daily["root"] = root
    daily["pcr_oi"] = daily["put_oi"] / daily["call_oi"].replace(0, np.nan)
    daily["net_gex_ratio"] = daily["net_gex"] / daily["abs_gex"].replace(0, np.nan)
    daily["net_vanna_ratio"] = daily["net_vanna"] / daily["abs_vanna"].replace(0, np.nan)
    daily["net_charm_ratio"] = daily["net_charm"] / daily["abs_charm"].replace(0, np.nan)
    return daily


def aggregate_greek_panel(roots: list[str], start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    t0 = time.time()
    for i, root in enumerate(roots, start=1):
        root_frames = []
        for year in range(start_year, end_year + 1):
            ydf = _aggregate_root_year(root, year)
            if not ydf.empty:
                root_frames.append(ydf)
        if root_frames:
            rdf = pd.concat(root_frames, ignore_index=True).drop_duplicates(["root", "date"])
            frames.append(rdf)
        if i % 20 == 0 or i == len(roots):
            print(f"  aggregated {i}/{len(roots)} roots ({time.time() - t0:.1f}s)", flush=True)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.sort_values(["root", "date"]).reset_index(drop=True)

    out = []
    for root, g in panel.groupby("root", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        idx = pd.DatetimeIndex(g["date"])
        try:
            tags = opex_tag(idx)
            g = pd.concat([g, tags.reset_index(drop=True)], axis=1)
        except Exception:
            g["td_since"] = np.nan
            g["td_to"] = np.nan
            g["in_opex_week"] = False
            g["in_post_opex"] = False
            g["is_quad_cycle"] = False
            g["phase"] = "unknown"

        px = g["spot"].astype(float)
        log_ret = np.log(px / px.shift(1))
        for h in [1, 2, 5, 10, 21]:
            g[f"fwd_ret{h}"] = px.shift(-h) / px - 1.0
            g[f"fwd_abs_ret{h}"] = g[f"fwd_ret{h}"].abs()
        for h in [5, 21]:
            g[f"fwd_rv{h}"] = log_ret.rolling(h).std().shift(-h) * np.sqrt(252)
        g["iv_chg1"] = g["iv_proxy"] - g["iv_proxy"].shift(1)
        g["iv_chg5"] = g["iv_proxy"] - g["iv_proxy"].shift(5)
        g["vanna_hedge1"] = -g["net_vanna"] * g["iv_chg1"]
        g["vanna_hedge5"] = -g["net_vanna"] * g["iv_chg5"]
        # Carry expiration-day concentration into post-OPEX sessions.
        exp_marker = np.where(g["td_since"].fillna(-99).astype(float) == 0, g["front7_abs_gex_share"], np.nan)
        g["last_exp_front7_abs_gex_share"] = pd.Series(exp_marker, index=g.index).ffill()
        exp_charm = np.where(g["td_since"].fillna(-99).astype(float) == 0, g["front7_abs_charm_share"], np.nan)
        g["last_exp_front7_abs_charm_share"] = pd.Series(exp_charm, index=g.index).ffill()
        out.append(g)

    panel = pd.concat(out, ignore_index=True)
    # Attach SPY forward returns as market-relative anchor.
    spy = panel[panel["root"] == "SPY"][["date", "fwd_ret1", "fwd_ret2", "fwd_ret5", "fwd_ret10", "fwd_ret21"]]
    spy = spy.rename(columns={c: f"spy_{c}" for c in spy.columns if c != "date"})
    panel = panel.merge(spy, on="date", how="left")
    for h in [1, 2, 5, 10, 21]:
        panel[f"rel_ret{h}"] = panel[f"fwd_ret{h}"] - panel[f"spy_fwd_ret{h}"]
    return panel


def _date_rank(panel: pd.DataFrame, col: str) -> pd.Series:
    return panel.groupby("date")[col].rank(pct=True)


def run_cross_section_tests(panel: pd.DataFrame) -> list[dict[str, Any]]:
    features = [
        ("net_charm_ratio", "signed_charm_pressure"),
        ("abs_charm", "charm_intensity"),
        ("front7_abs_charm_share", "front_week_charm_concentration"),
        ("net_vanna_ratio", "signed_vanna_pressure"),
        ("abs_vanna", "vanna_intensity"),
        ("vanna_hedge1", "vanna_hedge_pressure_1d_ivmove"),
        ("vanna_hedge5", "vanna_hedge_pressure_5d_ivmove"),
        ("net_gex_ratio", "signed_gamma_pressure"),
        ("abs_gex", "gamma_intensity"),
        ("front7_abs_gex_share", "front_week_gamma_concentration"),
        ("pcr_oi", "put_call_oi_ratio"),
    ]
    targets = [
        ("rel_ret1", "rel_ret_1d", 1),
        ("rel_ret5", "rel_ret_5d", 5),
        ("rel_ret10", "rel_ret_10d", 10),
        ("fwd_abs_ret5", "abs_move_5d", 5),
        ("fwd_rv5", "realized_vol_5d", 5),
    ]
    rows: list[dict[str, Any]] = []
    work = panel.copy()
    for feature, feature_label in features:
        if feature not in work:
            continue
        for era, start, end in GREEK_ERAS:
            edf = _era_slice(work, "date", start, end)
            if edf.empty:
                continue
            for target, target_label, horizon in targets:
                if target not in edf:
                    continue
                ics = []
                for _, ddf in edf[["date", "root", feature, target]].dropna().groupby("date"):
                    if len(ddf) < MIN_ROOTS_PER_DATE:
                        continue
                    rho, _ = stats.spearmanr(ddf[feature].to_numpy(float), ddf[target].to_numpy(float))
                    if np.isfinite(rho):
                        ics.append(rho)
                if len(ics) < 30:
                    continue
                lag = _overlap_lag(len(ics), horizon)
                t, p, n = _hac_ttest(np.asarray(ics), lag=lag)
                rows.append({
                    "family": "cross_section_ic",
                    "era": era,
                    "feature": feature_label,
                    "target": target_label,
                    "mean_ic": _f(np.mean(ics), 5),
                    "t": _f(t, 4),
                    "p": _f(p, 6),
                    "n_dates": int(n),
                    "lag": int(lag),
                })
    _bh_fdr(rows, "p", alpha=0.10)
    rows.sort(key=lambda r: (_sort_num(r.get("bh_adj_p")), _sort_num(r.get("p"))))
    return rows


def run_state_tests(panel: pd.DataFrame) -> list[dict[str, Any]]:
    work = panel.copy()
    for c in ["in_opex_week", "in_post_opex", "is_quad_cycle"]:
        if c in work.columns:
            work[c] = work[c].fillna(False).astype(bool)
        else:
            work[c] = False
    for col in ["abs_charm", "abs_gex", "abs_vanna", "vanna_hedge1", "vanna_hedge5"]:
        work[f"{col}_rank"] = _date_rank(work, col)

    work["long_gamma_assumption"] = work["net_gex_ratio"] > 0
    work["short_gamma_assumption"] = work["net_gex_ratio"] < 0
    work["high_charm"] = work["abs_charm_rank"] >= 0.67
    work["high_gex"] = work["abs_gex_rank"] >= 0.67
    work["high_vanna"] = work["abs_vanna_rank"] >= 0.67
    work["vanna_buy_pressure"] = work["vanna_hedge5_rank"] >= 0.67
    work["vanna_sell_pressure"] = work["vanna_hedge5_rank"] <= 0.33
    work["iv_falling_5d"] = work["iv_chg5"] < 0
    work["iv_rising_5d"] = work["iv_chg5"] > 0
    work["front_charm_loaded"] = work["front7_abs_charm_share"] >= 0.50
    work["front_gamma_loaded"] = work["front7_abs_gex_share"] >= 0.50
    work["last_exp_gamma_loaded"] = work["last_exp_front7_abs_gex_share"] >= 0.50

    conditions = [
        ("opex_long_gamma_high_charm_pin", work["in_opex_week"] & work["long_gamma_assumption"] & work["high_charm"]),
        ("opex_short_gamma_high_charm_airpocket", work["in_opex_week"] & work["short_gamma_assumption"] & work["high_charm"]),
        ("opex_front_charm_loaded", work["in_opex_week"] & work["front_charm_loaded"]),
        ("post_opex_prior_gamma_loaded", work["in_post_opex"] & work["last_exp_gamma_loaded"]),
        ("quad_opex_high_charm", work["in_opex_week"] & work["is_quad_cycle"] & work["high_charm"]),
        ("vanna_relief_buy_pressure", work["iv_falling_5d"] & work["vanna_buy_pressure"]),
        ("vanna_drag_sell_pressure", work["iv_rising_5d"] & work["vanna_sell_pressure"]),
        ("placebo_long_gamma_high_charm_non_opex", (~work["in_opex_week"]) & work["long_gamma_assumption"] & work["high_charm"]),
    ]
    targets = [
        ("rel_ret2", "rel_ret_2d", 2),
        ("rel_ret5", "rel_ret_5d", 5),
        ("fwd_abs_ret5", "abs_move_5d", 5),
        ("fwd_rv5", "realized_vol_5d", 5),
    ]

    rows: list[dict[str, Any]] = []
    for cond_name, cond_mask in conditions:
        work[cond_name] = cond_mask.fillna(False)
        for era, start, end in GREEK_ERAS:
            edf = _era_slice(work, "date", start, end)
            if edf.empty:
                continue
            for target, target_label, horizon in targets:
                spreads = []
                n_cond_total = 0
                for _, ddf in edf[["date", cond_name, target]].dropna().groupby("date"):
                    c = ddf[ddf[cond_name]]
                    b = ddf[~ddf[cond_name]]
                    if len(c) < 2 or len(b) < 5:
                        continue
                    n_cond_total += len(c)
                    spreads.append(float(c[target].mean() - b[target].mean()))
                if len(spreads) < 20 or n_cond_total < 30:
                    continue
                lag = _overlap_lag(len(spreads), horizon)
                t, p, n = _hac_ttest(np.asarray(spreads), lag=lag)
                rows.append({
                    "family": "state_spread",
                    "era": era,
                    "condition": cond_name,
                    "target": target_label,
                    "spread_mean_pct": _f(np.mean(spreads) * 100, 4),
                    "t": _f(t, 4),
                    "p": _f(p, 6),
                    "n_dates": int(n),
                    "n_condition_obs": int(n_cond_total),
                    "lag": int(lag),
                })
    _bh_fdr(rows, "p", alpha=0.10)
    rows.sort(key=lambda r: (_sort_num(r.get("bh_adj_p")), _sort_num(r.get("p"))))
    return rows


def summarize_results(results: dict[str, Any]) -> str:
    lines = []
    lines.append("# Options Expiry, Vanna, Charm Study — Machine Summary")
    lines.append("")
    lines.append(f"Generated: {pd.Timestamp.now('UTC').isoformat()}")
    lines.append("")
    lines.append("## Coverage")
    gp = results.get("greek_panel", {})
    lines.append(f"- Greek panel rows: {gp.get('n_rows')} across {gp.get('n_roots')} roots.")
    lines.append(f"- Greek date range: {gp.get('start')} to {gp.get('end')}.")
    lines.append(f"- Calendar event rows: {results.get('calendar', {}).get('n_events')}.")
    lines.append("")

    lines.append("## Calendar Survivors")
    cal = results.get("calendar", {}).get("event_stats", [])
    survivors = [r for r in cal if r.get("bh_reject_10pct")]
    if survivors:
        for r in survivors[:12]:
            lines.append(f"- {r['era']} {r['test']}: mean {r['mean_pct']}%, t={r['t']}, adj_p={r.get('bh_adj_p')}.")
    else:
        lines.append("- No calendar event test survived BH-FDR at 10%.")
    lines.append("")

    lines.append("## Cross-Section IC Survivors")
    cs = [r for r in results.get("cross_section_tests", []) if r.get("bh_reject_10pct")]
    if cs:
        for r in cs[:20]:
            lines.append(
                f"- {r['era']} {r['feature']} -> {r['target']}: IC={r['mean_ic']}, "
                f"t={r['t']}, adj_p={r.get('bh_adj_p')}."
            )
    else:
        lines.append("- No cross-section IC test survived BH-FDR at 10%.")
    lines.append("")

    lines.append("## State Spread Survivors")
    st = [r for r in results.get("state_tests", []) if r.get("bh_reject_10pct")]
    if st:
        for r in st[:20]:
            lines.append(
                f"- {r['era']} {r['condition']} -> {r['target']}: spread "
                f"{r['spread_mean_pct']}pp, t={r['t']}, adj_p={r.get('bh_adj_p')}."
            )
    else:
        lines.append("- No state-spread test survived BH-FDR at 10%.")
    lines.append("")

    lines.append("## Strongest Non-Survivor Leads")
    for group_name, rows in [
        ("calendar", cal),
        ("cross_section", results.get("cross_section_tests", [])),
        ("state", results.get("state_tests", [])),
    ]:
        top = sorted(
            [r for r in rows if r.get("p") is not None and not r.get("bh_reject_10pct")],
            key=lambda r: r["p"],
        )[:8]
        lines.append(f"### {group_name}")
        if not top:
            lines.append("- none")
            continue
        for r in top:
            label = r.get("test") or f"{r.get('feature') or r.get('condition')} -> {r.get('target')}"
            metric = r.get("mean_pct", r.get("mean_ic", r.get("spread_mean_pct")))
            lines.append(f"- {r.get('era')} {label}: metric={metric}, p={r.get('p')}, adj_p={r.get('bh_adj_p')}.")
    lines.append("")
    lines.append("## Caveats")
    lines.append("- Dealer sign is assumption-based; signs may invert by root and era.")
    lines.append("- OI is shifted one observation per contract; missing first observations are dropped.")
    lines.append("- Survivorship exists because the local ThetaData root list is the current backfill universe.")
    lines.append("- This is research output only; no score path or gate is changed.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2017)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--max-roots", type=int, default=None)
    args = ap.parse_args()

    if not THETA_STORE.exists():
        print(f"SKIP: missing ThetaData store {THETA_STORE}")
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    print("Running calendar/OPEX study...", flush=True)
    calendar = run_calendar_study()

    roots = _manifest_roots(args.max_roots)
    print(f"Aggregating greek panel for {len(roots)} roots...", flush=True)
    panel = aggregate_greek_panel(roots, args.start_year, args.end_year)
    if panel.empty:
        print("SKIP: greek panel empty")
        return 0

    panel_summary = {
        "n_rows": int(len(panel)),
        "n_roots": int(panel["root"].nunique()),
        "start": str(panel["date"].min().date()),
        "end": str(panel["date"].max().date()),
        "roots": sorted(panel["root"].unique().tolist()),
    }
    print(f"Greek panel: {panel_summary['n_rows']} rows, {panel_summary['n_roots']} roots", flush=True)

    print("Running cross-section tests...", flush=True)
    cs = run_cross_section_tests(panel)
    print("Running state tests...", flush=True)
    state = run_state_tests(panel)

    results = {
        "schema": "options_opex_vanna_charm_study.v1",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "theta_store": str(THETA_STORE),
        "yahoo_dir": str(YAHOO_DIR),
        "calendar": calendar,
        "greek_panel": panel_summary,
        "cross_section_tests": cs,
        "state_tests": state,
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    OUT_MD.write_text(summarize_results(results))
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
