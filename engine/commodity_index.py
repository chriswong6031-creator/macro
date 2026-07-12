"""Commodity Sector Index + Breadth Engine.

Display-tier only — equal-weight composite of the complex members.  No scored
authority, no promotion gauntlet.  Breadth / velocity are the sector-diversity
read: how many members are trending, how fast the index is moving, and whether
the composite is washing out or blowing off.

Three public functions:
  price_shock()        — return-based washout/blow-off z-score for any close series.
  build_index()        — composite + breadth + velocity from pre-computed member frames.
  build_and_snapshot() — convenience: load_members → compute_asset → build_index.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# confirmed enum values (introspected 2026-07-12)
_BULL_MOMENTUM_STATES = {"bull"}          # momentum_state ∈ {bull, neutral, bear}
_LOW_RISK_REGIME = "low_risk"             # risk_regime ∈ {low_risk, high_risk}
_UP_TREND = "up"                          # ts_trend ∈ {up, down, flat}


# --------------------------------------------------------------------------- #
# public: price_shock
# --------------------------------------------------------------------------- #
def price_shock(close: pd.Series, cfg_ps: dict) -> pd.DataFrame:
    """Return-based washout/blow-off z-score for a close price series.

    Uses only standard rolling windows — no look-ahead beyond the rolling
    calculation itself.

    Parameters
    ----------
    close   : daily close price series (DatetimeIndex).
    cfg_ps  : price_shock sub-config with keys return_window_d, z_lookback_d,
              shock_z.

    Returns
    -------
    DataFrame with columns:
      shock_z_price    — rolling z-score of the n-day return.
      shock_state_price — "washout" | "blowoff" | "normal" (NaN where z is NaN).
    """
    rw = int(cfg_ps["return_window_d"])
    zl = int(cfg_ps["z_lookback_d"])
    sz = float(cfg_ps["shock_z"])

    r = close.pct_change(rw)
    mu = r.rolling(zl, min_periods=max(20, zl // 4)).mean()
    sd = r.rolling(zl, min_periods=max(20, zl // 4)).std()
    z = (r - mu) / sd.replace(0, np.nan)

    state = pd.Series(np.nan, index=close.index, dtype=object)
    valid = z.notna()
    state[valid & (z > sz)] = "blowoff"
    state[valid & (z < -sz)] = "washout"
    state[valid & (z >= -sz) & (z <= sz)] = "normal"

    return pd.DataFrame({"shock_z_price": z, "shock_state_price": state})


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _safe_float(v: Any, ndigits: int = 4) -> float | None:
    """Convert to a JSON-safe rounded float, or None for NaN/inf/non-numeric."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, ndigits)


def _safe_str(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v)
    return None if s in ("nan", "None", "") else s


def _last(s: pd.Series) -> Any:
    """Last non-NaN value from a Series, or None."""
    clean = s.dropna()
    return clean.iloc[-1] if len(clean) > 0 else None


def _chg_1m(close: pd.Series) -> float | None:
    """22-day percent change from the last available close."""
    c = close.dropna()
    if len(c) < 23:
        return None
    return _safe_float((c.iloc[-1] / c.iloc[-23] - 1) * 100, 1)


# --------------------------------------------------------------------------- #
# public: build_index
# --------------------------------------------------------------------------- #
def build_index(
    member_results: dict[str, pd.DataFrame],
    benchmarks: dict[str, pd.Series],
    cfg: dict,
) -> dict:
    """Build the commodity sector index + breadth + velocity snapshot.

    Parameters
    ----------
    member_results : {name: compute_asset_frame} — one frame per complex member.
    benchmarks     : {"DBC": close_series, "GSG": close_series} — may be empty.
    cfg            : full commodities config section (uses cfg["index"]).

    Returns
    -------
    JSON-safe snapshot dict.  Returns {} (never raises) on any failure.
    """
    try:
        return _build_index_inner(member_results, benchmarks, cfg)
    except Exception as e:  # noqa: BLE001 — display engine must never break the build
        log.warning("commodity_index.build_index failed: %s", e)
        return {}


def composite_series(
    member_results: dict[str, pd.DataFrame],
    cfg: dict,
) -> dict:
    """Extract the composite index series from member frames.

    Returns a dict with keys:
        "idx_ew"       : equal-weight chain-linked composite (pd.Series, rebased to 100).
        "idx_vw"       : vol-weight chain-linked composite (pd.Series, rebased to 100).
        "first_mature" : pd.Timestamp — first date where >= rebase_min_members present.

    Returns {} if member data is insufficient (fewer than rebase_min_members).
    Never raises.
    """
    try:
        return _composite_series_inner(member_results, cfg)
    except Exception:  # noqa: BLE001
        log.warning("commodity_index.composite_series failed", exc_info=True)
        return {}


def _composite_series_inner(
    member_results: dict[str, pd.DataFrame],
    cfg: dict,
) -> dict:
    icfg = cfg["index"]
    min_members: int = int(icfg["rebase_min_members"])

    all_closes: dict[str, pd.Series] = {}
    for name, df in member_results.items():
        if "close" in df.columns and df["close"].notna().any():
            all_closes[name] = df["close"].dropna()

    if len(all_closes) < min_members:
        return {}

    union_idx = pd.DatetimeIndex(
        sorted(set().union(*[c.index for c in all_closes.values()]))
    )
    ret_df = pd.DataFrame({name: c.reindex(union_idx).pct_change()
                           for name, c in all_closes.items()})
    present_df = pd.DataFrame({name: c.reindex(union_idx).notna()
                                for name, c in all_closes.items()})
    present_count = present_df.sum(axis=1)
    mask_ok = present_count >= min_members
    first_mature = mask_ok.idxmax() if bool(mask_ok.any()) else union_idx[0]

    def _chain(ret: pd.Series) -> pd.Series:
        lvl = (1.0 + ret.fillna(0.0)).cumprod()
        lvl = lvl.where(lvl.index >= first_mature)
        base = lvl.loc[first_mature] if first_mature in lvl.index else np.nan
        return (lvl / base * 100.0) if (pd.notna(base) and base != 0) else lvl

    idx_ew = _chain(ret_df.mean(axis=1, skipna=True))

    vol_df = pd.DataFrame({name: ret_df[name].rolling(60, min_periods=20).std()
                           for name in ret_df.columns})
    inv_vol = (1.0 / vol_df.replace(0, np.nan)).where(present_df)
    weights_vw = inv_vol.div(inv_vol.sum(axis=1, min_count=1), axis=0)
    idx_vw = _chain((ret_df * weights_vw).sum(axis=1, min_count=1))

    return {"idx_ew": idx_ew, "idx_vw": idx_vw, "first_mature": first_mature}


def _build_index_inner(
    member_results: dict[str, pd.DataFrame],
    benchmarks: dict[str, pd.Series],
    cfg: dict,
) -> dict:
    from engine.commodity_mtf import mtf_ladder, confluence_verdict
    from engine.commodity_signals import ts_momentum as ts_mom_fn

    icfg = cfg["index"]
    min_members: int = int(icfg["rebase_min_members"])
    breadth_lookback: int = int(icfg["breadth_pctile_lookback_d"])
    vel_windows: list[int] = [int(w) for w in icfg["velocity_windows_d"]]
    impulse_w: int = int(icfg["impulse_window_d"])
    accel_w: int = int(icfg["accel_window_d"])
    ps_cfg: dict = icfg["price_shock"]

    if not member_results:
        log.warning("commodity_index: no member results, returning empty snapshot")
        return {}

    # ------------------------------------------------------------------ #
    # 1. Union daily index + per-member rebased close
    #    (uses composite_series to avoid duplicating the chain-link logic)
    # ------------------------------------------------------------------ #
    cs = _composite_series_inner(member_results, cfg)
    if not cs:
        log.warning("commodity_index: composite_series returned empty (too few members)")
        return {}

    idx_ew      = cs["idx_ew"]
    idx_vw      = cs["idx_vw"]
    first_mature = cs["first_mature"]

    # re-derive helpers needed for breadth (present_masks, ret_df, union_idx)
    all_closes: dict[str, pd.Series] = {}
    for name, df in member_results.items():
        if "close" in df.columns and df["close"].notna().any():
            all_closes[name] = df["close"].dropna()

    if len(all_closes) < min_members:
        log.warning("commodity_index: only %d members have close data, need %d",
                    len(all_closes), min_members)
        return {}

    union_idx = pd.DatetimeIndex(
        sorted(set().union(*[c.index for c in all_closes.values()]))
    )
    ret_df = pd.DataFrame({name: c.reindex(union_idx).pct_change()
                           for name, c in all_closes.items()})
    present_masks = {name: c.reindex(union_idx).notna()
                     for name, c in all_closes.items()}
    present_df = pd.DataFrame(present_masks)

    # ------------------------------------------------------------------ #
    # 2. Index technical read (MTF + ts_momentum + price_shock)
    # ------------------------------------------------------------------ #
    idx_ew_clean = idx_ew.dropna()
    mtf_a = mtf_ladder(idx_ew_clean)
    cv = confluence_verdict(mtf_a, "commodity_index", sig_last=None, calib_asset=None)

    # ts_momentum on a minimal DataFrame with "close" column
    ts_df = pd.DataFrame({"close": idx_ew_clean})
    ts_out = ts_mom_fn(ts_df, cfg["trend"])

    ps_out = price_shock(idx_ew_clean, ps_cfg)

    # ------------------------------------------------------------------ #
    # 3. Breadth time-series
    # ------------------------------------------------------------------ #
    def _reindex_member(df: pd.DataFrame) -> pd.DataFrame:
        return df.reindex(union_idx).ffill()

    breadth_rows: dict[str, pd.Series] = {
        "n_members": pd.Series(dtype=float, index=union_idx),
        "n_up_trend": pd.Series(dtype=float, index=union_idx),
        "n_bull_momentum": pd.Series(dtype=float, index=union_idx),
        "n_low_risk": pd.Series(dtype=float, index=union_idx),
        "trend_diversity": pd.Series(dtype=float, index=union_idx),
    }

    # Collect per-member time-series on the union index
    ts_trend_cols: list[pd.Series] = []
    mom_state_cols: list[pd.Series] = []
    risk_regime_cols: list[pd.Series] = []
    ts_mom_cols: list[pd.Series] = []

    for name, df in member_results.items():
        if name not in all_closes:
            continue
        dfr = _reindex_member(df)
        present = present_masks[name]

        if "ts_trend" in dfr.columns:
            s = dfr["ts_trend"].where(present)
            ts_trend_cols.append(s)
        if "momentum_state" in dfr.columns:
            s = dfr["momentum_state"].where(present)
            mom_state_cols.append(s)
        if "risk_regime" in dfr.columns:
            s = dfr["risk_regime"].where(present)
            risk_regime_cols.append(s)
        if "ts_momentum" in dfr.columns:
            s = dfr["ts_momentum"].where(present)
            ts_mom_cols.append(s)

    if ts_trend_cols:
        ttdf = pd.concat(ts_trend_cols, axis=1)
        breadth_rows["n_members"] = ttdf.notna().sum(axis=1).astype(float)
        breadth_rows["n_up_trend"] = (ttdf == _UP_TREND).sum(axis=1).astype(float)
    else:
        breadth_rows["n_members"] = pd.Series(0.0, index=union_idx)
        breadth_rows["n_up_trend"] = pd.Series(0.0, index=union_idx)

    if mom_state_cols:
        msdf = pd.concat(mom_state_cols, axis=1)
        n_bull = pd.Series(0.0, index=union_idx)
        for s in _BULL_MOMENTUM_STATES:
            n_bull = n_bull + (msdf == s).sum(axis=1).astype(float)
        breadth_rows["n_bull_momentum"] = n_bull

    if risk_regime_cols:
        rrdf = pd.concat(risk_regime_cols, axis=1)
        breadth_rows["n_low_risk"] = (rrdf == _LOW_RISK_REGIME).sum(axis=1).astype(float)

    if ts_mom_cols:
        tmdf = pd.concat(ts_mom_cols, axis=1)
        breadth_rows["trend_diversity"] = tmdf.std(axis=1, skipna=True)

    breadth_df = pd.DataFrame(breadth_rows, index=union_idx)

    # pct_up_trend
    n_mem = breadth_df["n_members"].replace(0, np.nan)
    breadth_df["pct_up_trend"] = breadth_df["n_up_trend"] / n_mem

    # breadth_pctile: trailing rolling rank (what fraction of past readings is today <= today)
    pct_up = breadth_df["pct_up_trend"]
    breadth_df["breadth_pctile"] = pct_up.rolling(
        breadth_lookback, min_periods=60
    ).apply(lambda x: float((x.iloc[-1] >= x[:-1]).mean()), raw=False)

    # ------------------------------------------------------------------ #
    # 4. Velocity / impulse (index + per-member)
    # ------------------------------------------------------------------ #
    def _velocity_cols(close: pd.Series, prefix: str = "") -> dict[str, pd.Series]:
        cols: dict[str, pd.Series] = {}
        for w in vel_windows:
            cols[f"{prefix}r{w}"] = close.pct_change(w) * 100
        # ts_momentum acceleration (diff of ts_momentum over accel_w)
        ts_tmp = ts_mom_fn(pd.DataFrame({"close": close.dropna()}), cfg["trend"])
        if "ts_momentum" in ts_tmp.columns:
            cols[f"{prefix}accel"] = ts_tmp["ts_momentum"].reindex(close.index).diff(accel_w)
        # vol-normalized impulse
        ret = close.pct_change(impulse_w)
        rolling_vol = close.pct_change().rolling(impulse_w, min_periods=max(5, impulse_w // 4)).std()
        denom = rolling_vol * math.sqrt(impulse_w)
        cols[f"{prefix}impulse"] = ret / denom.replace(0, np.nan)
        return cols

    idx_vel = _velocity_cols(idx_ew_clean)

    # ------------------------------------------------------------------ #
    # 5. Persist to parquet
    # ------------------------------------------------------------------ #
    persist_cols: dict[str, pd.Series] = {
        "idx_ew": idx_ew,
        "idx_vw": idx_vw,
    }
    for col in breadth_df.columns:
        persist_cols[col] = breadth_df[col]
    for k, v in idx_vel.items():
        persist_cols[f"idx_{k}"] = v
    # index shock
    ps_reindexed = ps_out.reindex(union_idx)
    persist_cols["idx_shock_z_price"] = ps_reindexed["shock_z_price"] if "shock_z_price" in ps_reindexed.columns else pd.Series(np.nan, index=union_idx)

    persist_df = pd.DataFrame(persist_cols, index=union_idx)

    try:
        out_dir = config.data_dir() / "commodity"
        out_dir.mkdir(parents=True, exist_ok=True)
        persist_df.to_parquet(out_dir / "signals_index.parquet")
    except Exception as e:  # noqa: BLE001
        log.warning("commodity_index: could not persist signals_index.parquet: %s", e)

    # ------------------------------------------------------------------ #
    # 6. Build JSON-safe snapshot
    # ------------------------------------------------------------------ #
    last_date = idx_ew_clean.index[-1] if len(idx_ew_clean) > 0 else union_idx[-1]
    asof = str(last_date.date())

    # index tech read — latest values
    ts_last = ts_out.reindex([last_date]).iloc[0] if last_date in ts_out.index else ts_out.iloc[-1] if len(ts_out) > 0 else pd.Series(dtype=float)
    ps_last = ps_out.reindex([last_date]).iloc[0] if last_date in ps_out.index else ps_out.iloc[-1] if len(ps_out) > 0 else pd.Series(dtype=float)

    def _vel_dict(vel_cols: dict[str, pd.Series], prefix: str = "") -> dict:
        d: dict[str, Any] = {}
        for w in vel_windows:
            k = f"{prefix}r{w}"
            d[f"r{w}"] = _safe_float(vel_cols[k].dropna().iloc[-1] if k in vel_cols and len(vel_cols[k].dropna()) > 0 else None, 1)
        for k2 in ("accel", "impulse"):
            fk = f"{prefix}{k2}"
            d[k2] = _safe_float(vel_cols[fk].dropna().iloc[-1] if fk in vel_cols and len(vel_cols[fk].dropna()) > 0 else None, 3)
        return d

    # benchmark closes
    bench_snap: dict[str, Any] = {}
    for bname, bseries in benchmarks.items():
        bs = bseries.dropna()
        if len(bs) == 0:
            bench_snap[bname] = {"last": None, "chg_1m_pct": None}
        else:
            bench_snap[bname] = {
                "last": _safe_float(bs.iloc[-1], 2),
                "chg_1m_pct": _chg_1m(bs),
            }

    # breadth snapshot (latest row of breadth_df)
    bl = breadth_df.reindex([last_date])
    if last_date not in breadth_df.index:
        bl = breadth_df.iloc[[-1]]

    def _blv(col: str) -> Any:
        v = bl[col].iloc[0] if col in bl.columns else None
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(f):
            return None
        # integer columns
        if col in ("n_members", "n_up_trend", "n_bull_momentum", "n_low_risk"):
            return int(round(f))
        return round(f, 3)

    breadth_snap = {
        "n_members": _blv("n_members"),
        "n_up_trend": _blv("n_up_trend"),
        "pct_up_trend": _blv("pct_up_trend"),
        "n_bull_momentum": _blv("n_bull_momentum"),
        "n_low_risk": _blv("n_low_risk"),
        "trend_diversity": _blv("trend_diversity"),
        "breadth_pctile": _blv("breadth_pctile"),
    }

    # members list — sorted by class then name
    class_order = {"precious": 0, "industrial": 1, "energy": 2, "grain": 3, "soft": 4, "livestock": 5}
    members_snap: list[dict] = []
    try:
        _member_classes = {n: spec[2] for n, spec in
                           config.load()["commodities"]["complex_members"].items()}
    except Exception:  # noqa: BLE001
        _member_classes = {}

    for name in member_results:  # final order set by the class/name sort below
        df = member_results[name]
        if not isinstance(df, pd.DataFrame):
            continue
        klass = _member_classes.get(name, "")

        cl = df["close"].dropna() if "close" in df.columns else pd.Series(dtype=float)
        last_close = _safe_float(cl.iloc[-1] if len(cl) > 0 else None, 2)
        chg_1m = _chg_1m(cl) if len(cl) >= 23 else None

        def _col_last(col: str) -> Any:
            if col not in df.columns:
                return None
            s = df[col].dropna()
            return s.iloc[-1] if len(s) > 0 else None

        ts_trend_v = _safe_str(_col_last("ts_trend"))
        ts_mom_v = _safe_float(_col_last("ts_momentum"), 3)
        mom_state_v = _safe_str(_col_last("momentum_state"))
        risk_idx_v = _safe_float(_col_last("risk_index"), 1)
        risk_regime_v = _safe_str(_col_last("risk_regime"))
        risk_word = "Calm" if risk_regime_v == "low_risk" else ("Elevated" if risk_regime_v == "high_risk" else None)
        cycle_pos_v = _safe_float(_col_last("cycle_position"), 3)

        # shock: prefer macro shock_state/shock_z if present, else price-based
        if "shock_state" in df.columns:
            shock_state_v = _safe_str(_col_last("shock_state"))
            shock_z_v = _safe_float(_col_last("shock_z"), 3)
        else:
            ps_m = price_shock(cl, ps_cfg) if len(cl) >= 25 else pd.DataFrame()
            shock_state_v = _safe_str(ps_m["shock_state_price"].dropna().iloc[-1] if len(ps_m) > 0 and "shock_state_price" in ps_m.columns and ps_m["shock_state_price"].notna().any() else None)
            shock_z_v = _safe_float(ps_m["shock_z_price"].dropna().iloc[-1] if len(ps_m) > 0 and "shock_z_price" in ps_m.columns and ps_m["shock_z_price"].notna().any() else None, 3)

        # per-member velocity
        m_vel = _velocity_cols(cl)
        m_vel_snap = _vel_dict(m_vel)

        members_snap.append({
            "name": name,
            "label": name.replace("_", " ").title(),
            "class": klass,
            "close": last_close,
            "chg_1m_pct": chg_1m,
            "ts_trend": ts_trend_v,
            "ts_momentum": ts_mom_v,
            "momentum_state": mom_state_v,
            "risk_index": risk_idx_v,
            "risk_word": risk_word,
            "shock_state": shock_state_v,
            "shock_z": shock_z_v,
            "cycle_position": cycle_pos_v,
            "velocity": m_vel_snap,
        })

    # sort members by class then name (re-sort using class from populated snap)
    members_snap.sort(key=lambda m: (class_order.get(m.get("class", ""), 99), m.get("name", "")))

    snapshot: dict[str, Any] = {
        "asof": asof,
        "index": {
            "ew": _safe_float(idx_ew_clean.iloc[-1] if len(idx_ew_clean) > 0 else None, 2),
            "vw": _safe_float(idx_vw.dropna().iloc[-1] if idx_vw.notna().any() else None, 2),
            "chg_1m_pct": _chg_1m(idx_ew_clean),
            "ts_trend": _safe_str(ts_last.get("ts_trend") if hasattr(ts_last, "get") else None),
            "ts_momentum": _safe_float(ts_last.get("ts_momentum") if hasattr(ts_last, "get") else None, 3),
            "mtf": {
                "grade": _safe_str(cv.get("grade")),
                "headline": _safe_str(cv.get("headline")),
                "short_sign": cv.get("short_sign"),
                "mid_sign": cv.get("mid_sign"),
                "long_sign": cv.get("long_sign"),
                "regime": _safe_str(cv.get("regime")),
                "ladder_state": _safe_str(cv.get("ladder_state")),
            },
            "shock_state": _safe_str(ps_last.get("shock_state_price") if hasattr(ps_last, "get") else None),
            "shock_z": _safe_float(ps_last.get("shock_z_price") if hasattr(ps_last, "get") else None, 3),
            "velocity": _vel_dict(idx_vel),
            "benchmarks": bench_snap,
        },
        "breadth": breadth_snap,
        "members": members_snap,
    }

    return snapshot


# --------------------------------------------------------------------------- #
# public: build_and_snapshot
# --------------------------------------------------------------------------- #
def build_and_snapshot(cfg: dict | None = None) -> dict:
    """Convenience: load_members → compute_asset → build_index → snapshot.

    The build script may call build_index directly with a pre-built
    member_results dict to avoid double-compute.
    """
    try:
        from engine import commodity_inputs
        from engine.commodity_signals import compute_asset

        cfg = cfg or config.load()["commodities"]
        members = commodity_inputs.load_members(cfg)
        if not members:
            log.warning("commodity_index.build_and_snapshot: no members loaded")
            return {}

        member_results: dict[str, pd.DataFrame] = {}
        for name, ai in members.items():
            try:
                member_results[name] = compute_asset(ai, cfg)
            except Exception as e:  # noqa: BLE001
                log.warning("commodity_index: compute_asset failed for %s: %s", name, e)

        # benchmarks
        benchmarks: dict[str, pd.Series] = {}
        for tkr in cfg.get("index", {}).get("benchmarks", []):
            try:
                px = commodity_inputs.load_price(tkr)
                benchmarks[tkr] = px["close"].rename(tkr)
            except Exception as e:  # noqa: BLE001
                log.warning("commodity_index: benchmark %s unavailable: %s", tkr, e)

        return build_index(member_results, benchmarks, cfg)

    except Exception as e:  # noqa: BLE001
        log.warning("commodity_index.build_and_snapshot failed: %s", e)
        return {}
