"""Thematic flow-shift detector (DISPLAY-ONLY) — Engine 1 of the two-engine plan.

The SLOW 'where is money rotating' radar, the cross-sectional complement to the fast
regime-snap detector (engine.regime_snap). For each thematic basket it computes a
deterministic FLOW FINGERPRINT — the cross-sectional structure that betrays
institutional rotation FORMING, before the move is obvious — and stages it
EMERGING -> CONFIRMED -> EXHAUSTED. The point is to catch the 2nd inning (emerging),
not the 5th (confirmed, where institutions already are) or the exit (exhausted).

It is market_drivers.py's fingerprint pattern applied to baskets instead of macro
drivers, reusing engine.baskets building blocks (membership, EW level, the S&P-1500
close cache) — ZERO new data.

Legs (all causal/trailing, computed from the group's constituents + its EW level):
  accel       acceleration of relative strength vs SPY — the early-rotation tell
              (the move is SPEEDING UP, not merely already high)
  broadening  change in the % of members above their own 50d MA — broadening =
              healthy rotation; narrowing = a few names carrying it (late)
  cohesion    mean pairwise correlation of member returns, and its change — rising =
              coordinated theme buying / supply-chain spread, not idiosyncratic noise
  persistence how durable the recent relative strength is (not a one-day pop)

DISCIPLINE: display-only, NEVER scored — nothing in axes/regime/macro_risk reads it.
Whether EMERGING actually PRECEDES forward outperformance is an open Phase-0 question
(scripts/group_flow_phase0.py); until it passes, the stage is a descriptive lens
(where flow is concentrating), not a buy list — expect, like residual alpha, a modest
regime-decayed edge at best.
"""
from __future__ import annotations

import collections
import json
import logging

import numpy as np
import pandas as pd

from engine.baskets import _basket_extras, _ew_level, _membership
from engine.equity_factors import _closes, _names_sectors
from engine.indicators import pct_rank_window
from lib import config, store

log = logging.getLogger(__name__)

_DEFAULTS = {
    "rs_window_d": 20,            # window for the relative-strength change / acceleration
    "breadth_ma_d": 50,          # members above their own N-day MA
    "corr_window_d": 40,         # cohesion (mean pairwise correlation) window
    "persist_window_d": 20,      # persistence = fraction of recent days with rising RS
    "z_lookback_d": 252,         # trailing window for causal z-scores / percentiles
    "min_history_d": 150,        # skip a group with too little history to z-score
    "weights": {"accel": 0.40, "broadening": 0.30, "cohesion": 0.15, "persistence": 0.15},
    "emerging_accel_z": 0.5,     # accel z above this (and not yet extended) = EMERGING
    "confirmed_pctile": 0.80,    # RS percentile above this = the move is already extended
    "exhausted_accel_z": -0.5,   # accel z below this (off an elevated RS) = COOLING
    "min_members": 8,            # PIT sector / group minimum live members
    "cohesion_gate_chg": 0.05,   # cohesion_chg above this = group is 'cohering' (context gate)
    "vix_pctile_lookback_d": 504,  # ~2y window for the VIX percentile (stress regime)
    "vix_elevated_pctile": 0.60,   # VIX above this %ile = stress regime (cohesion gate active)
    "cluster_window_d": 60,      # window for the cross-group co-movement (cluster) map
    "basket_confidence_cap": 0.55,  # fallback cap if validation_meta absent
}

# GICS sector -> Chinese label (bilingual display of the unbiased universe)
_SECTOR_ZH = {
    "Information Technology": "信息技术", "Health Care": "医疗保健", "Financials": "金融",
    "Consumer Discretionary": "非必需消费", "Communication Services": "通信服务",
    "Industrials": "工业", "Consumer Staples": "必需消费", "Energy": "能源",
    "Utilities": "公用事业", "Real Estate": "房地产", "Materials": "原材料",
}


def _cfg(cfg: dict | None = None) -> dict:
    if cfg is not None:
        return {**_DEFAULTS, **cfg}
    try:
        c = dict(config.load()["engine"].get("group_flow") or {})
    except Exception:  # noqa: BLE001 — config-less callers fall back to defaults
        c = {}
    return {**_DEFAULTS, **c}


def _causal_z(s: pd.Series, window: int) -> pd.Series:
    m = s.rolling(window, min_periods=window // 3).mean()
    sd = s.rolling(window, min_periods=window // 3).std()
    return (s - m) / sd.replace(0, np.nan)


def _mean_pairwise_corr(rw: pd.DataFrame) -> float | None:
    """Mean off-diagonal correlation of a member-returns window (cohesion). Drops
    all-NaN AND zero-variance (halted / constant-price) members first — one constant
    member otherwise NaNs the whole correlation matrix and silently kills the leg."""
    rw = rw.dropna(axis=1, thresh=int(len(rw) * 0.8))
    rw = rw.loc[:, rw.std(numeric_only=True) > 0]
    if rw.shape[1] < 3 or len(rw) < 10:
        return None
    c = rw.corr().to_numpy()
    n = c.shape[0]
    off = (np.nansum(c) - np.trace(c)) / (n * (n - 1))
    return float(off) if np.isfinite(off) else None


def prep_group(members_closes: pd.DataFrame, lvl: pd.Series, bench: pd.Series,
               cfg: dict) -> dict | None:
    """Vectorise the cheap, full-history legs once per group (the cohesion leg is
    point-wise, computed in fingerprint_at). Returns None if too little history."""
    rs = (lvl / bench)
    if rs.dropna().shape[0] < cfg["min_history_d"]:
        return None
    w, zl = int(cfg["rs_window_d"]), int(cfg["z_lookback_d"])
    rs_chg = rs.pct_change(w, fill_method=None)
    accel_z = _causal_z(rs_chg - rs_chg.shift(w), zl)            # 2nd diff of the rel line
    ma = members_closes.rolling(int(cfg["breadth_ma_d"]), min_periods=int(cfg["breadth_ma_d"]) // 2).mean()
    breadth = (members_closes > ma).where(members_closes.notna() & ma.notna()).mean(axis=1)
    broadening_z = _causal_z(breadth - breadth.shift(w), zl)
    rs_pctile = pct_rank_window(rs, zl)
    rel = rs.pct_change(fill_method=None)
    return {"rs": rs, "accel_z": accel_z, "breadth": breadth,
            "broadening_z": broadening_z, "rs_pctile": rs_pctile, "rel": rel,
            "rets": members_closes.pct_change(fill_method=None)}


def fingerprint_at(prep: dict, i: int, cfg: dict) -> dict | None:
    """Flow fingerprint at integer index position i (default last) — legs, a combined
    flow score (weights renormalised over available legs), and a lifecycle stage."""
    if prep is None or i < 0 or i >= len(prep["rs"]):
        return None
    wt = cfg["weights"]
    cw, pw, rw = int(cfg["corr_window_d"]), int(cfg["persist_window_d"]), int(cfg["rs_window_d"])

    def _at(s):
        v = s.iloc[i]
        return float(v) if pd.notna(v) else None

    accel_z, broadening_z = _at(prep["accel_z"]), _at(prep["broadening_z"])
    rs_pctile, breadth = _at(prep["rs_pctile"]), _at(prep["breadth"])

    rel_win = prep["rel"].iloc[max(0, i - pw + 1):i + 1].dropna()
    persistence = float((rel_win > 0).mean()) if len(rel_win) >= pw // 2 else None

    rets = prep["rets"]
    cohesion = cohesion_chg = None
    if i >= cw:
        cohesion = _mean_pairwise_corr(rets.iloc[i - cw + 1:i + 1])
        prev = _mean_pairwise_corr(rets.iloc[max(0, i - cw + 1 - rw):i + 1 - rw])
        if cohesion is not None and prev is not None:
            cohesion_chg = cohesion - prev

    # combined flow score: weighted mean over the legs that exist (z-like scale)
    legs = {"accel": accel_z, "broadening": broadening_z,
            "cohesion": (cohesion_chg * 3.0) if cohesion_chg is not None else None,
            "persistence": ((persistence - 0.5) * 2.0) if persistence is not None else None}
    num = sum(wt[k] * v for k, v in legs.items() if v is not None)
    den = sum(wt[k] for k, v in legs.items() if v is not None)
    flow_score = (num / den) if den > 0 else None

    stage = _stage(accel_z, rs_pctile, broadening_z, cfg)
    return {"flow_score": round(flow_score, 3) if flow_score is not None else None,
            "stage": stage, "accel_z": _r(accel_z), "broadening_z": _r(broadening_z),
            "breadth": _r(breadth), "cohesion": _r(cohesion), "cohesion_chg": _r(cohesion_chg),
            "persistence": _r(persistence), "rs_pctile": _r(rs_pctile)}


def _r(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 3)


def _stage(accel_z, rs_pctile, broadening_z, cfg) -> str:
    """A DESCRIPTIVE concentration lifecycle (directional=false — validated as
    display-only): EMERGING (concentration building, not yet extended) -> CONFIRMED
    (extended, broad) -> COOLING (rolling over off a high) -> QUIET. NOT a buy/sell;
    'cooling' deliberately carries NO exit connotation (the would-be exit stage tested
    wrong-signed, so it is renamed, not shipped as a sell)."""
    ea, cp, xa = cfg["emerging_accel_z"], cfg["confirmed_pctile"], cfg["exhausted_accel_z"]
    az = accel_z if accel_z is not None else 0.0
    rp = rs_pctile if rs_pctile is not None else 0.5
    bz = broadening_z if broadening_z is not None else 0.0
    if az >= ea and rp < cp and bz >= -0.25:
        return "emerging"
    if rp >= cp and az >= xa:
        return "confirmed"
    if az <= xa and rp >= 0.5:
        return "cooling"
    return "quiet"


# Region aliases -> canonical key. US is the original path (S&P-1500 cache + extras + SPY);
# the others swap the data plane to their regional baskets module. Sectors (the PIT GICS
# frames) stay US-only — non-US callers get the thematic baskets, not sectors.
_REGION_ALIASES = {"us": "us", "usa": "us", "cn": "cn", "china": "cn",
                   "hk": "hk", "hongkong": "hk", "ca": "ca", "canada": "ca"}


def _region_plane(region: str):
    """(_membership, _closes, bench_group, bench_default) for a non-US region, lazily —
    the regional baskets modules already expose exactly these loaders."""
    from engine import baskets_canada, baskets_china, baskets_hk
    planes = {
        "cn": (baskets_china._membership, baskets_china._closes, "china", baskets_china.BENCHMARK_DEFAULT),
        "hk": (baskets_hk._membership, baskets_hk._closes, "hk", baskets_hk.BENCHMARK_DEFAULT),
        "ca": (baskets_canada._membership, baskets_canada._closes, "canada", baskets_canada.BENCHMARK_DEFAULT),
    }
    return planes.get(region)


def _setup(region: str = "us"):
    """Shared close matrix + benchmark LEVEL for a region's thematic baskets.

    region='us' (default) is byte-identical to before: the S&P-1500 close cache unioned with
    baskets/extras, benchmarked to SPY. 'cn'/'hk'/'ca' swap in that region's baskets
    membership + search-cache closes + index benchmark (e.g. CSI 300 / HSI / TSX). The US-only
    PIT GICS sector frames are NOT built for non-US regions (no PIT membership), so non-US
    callers operate on the thematic baskets only."""
    region = _REGION_ALIASES.get((region or "us").lower(), "us")
    if region == "us":
        mem = _membership()
        if not mem or not mem.get("baskets"):
            return None
        closes = _closes()
        if closes is None or closes.empty:
            return None
        extras = _basket_extras()
        if extras is not None and not extras.empty:
            add = [c for c in extras.columns if c not in closes.columns]
            if add:
                closes = closes.join(extras[add], how="left")
        bench_df = store.read("yahoo", "SPY")
    else:
        plane = _region_plane(region)
        if plane is None:
            return None
        mem_fn, closes_fn, bench_group, bench_default = plane
        mem = mem_fn()
        if not mem or not mem.get("baskets"):
            return None
        closes = closes_fn()
        if closes is None or closes.empty:
            return None
        bench_df = store.read(bench_group, mem.get("benchmark", bench_default))
    if bench_df is None or "close" not in bench_df.columns:
        return None
    rets = closes.pct_change(fill_method=None)
    idx = rets.index
    bench_ret = bench_df["close"].reindex(idx).ffill().pct_change(fill_method=None)
    bench = pd.Series(np.nan, index=idx)
    bf = bench_ret.first_valid_index()
    if bf is None:
        return None
    bench.loc[bf:] = (1.0 + bench_ret.loc[bf:].fillna(0.0)).cumprod()
    return {"mem": mem, "closes": closes, "rets": rets, "idx": idx, "bench": bench,
            "region": region}


def _pit_sector_frames(closes: pd.DataFrame, rets: pd.DataFrame,
                       cfg: dict) -> dict[str, dict]:
    """The 11 GICS sectors as POINT-IN-TIME groups — free of the current-snapshot
    look-ahead and survivorship-REDUCED: a name counts toward its sector ONLY on days it
    was actually in the S&P 1500 (data/breadth/sp1500_pit_membership.parquet: ticker,
    start_date, end_date[NaT=still in], possibly multiple intervals). NOT fully
    survivorship-free — the universe is still bounded by names present in the current
    close cache and classified by the current GICS map (fully-departed tickers are
    absent). The EW level is the mean of ACTIVE members' returns each day; member closes
    are NaN-masked off their active windows so breadth/cohesion legs see only live
    members."""
    p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    if not p.exists():
        return {}
    pit = pd.read_parquet(p)
    pit["start_date"] = pd.to_datetime(pit["start_date"])
    pit["end_date"] = pd.to_datetime(pit["end_date"])
    intervals: dict[str, list] = collections.defaultdict(list)
    for t, a, b in zip(pit["ticker"], pit["start_date"], pit["end_date"]):
        intervals[str(t)].append((a, b))
    ns = _names_sectors()
    idx = rets.index
    sec_members: dict[str, list] = collections.defaultdict(list)
    for t, (_nm, s) in ns.items():
        if s and s != "—" and t in closes.columns and t in intervals:
            sec_members[s].append(t)

    out: dict[str, dict] = {}
    minm = int(cfg.get("min_members", 8))
    for s, members in sec_members.items():
        mask = pd.DataFrame(False, index=idx, columns=members)
        for t in members:
            col = np.zeros(len(idx), dtype=bool)
            for a, b in intervals[t]:
                act = np.asarray(idx >= a)
                if pd.notna(b):
                    act = act & np.asarray(idx < b)
                col |= act
            mask[t] = col
        if int(mask.iloc[-1].sum()) < minm:
            continue
        mc = closes[members].where(mask)                      # PIT-masked closes
        ew = rets[members].where(mask).mean(axis=1)           # mean of active members
        lvl = pd.Series(np.nan, index=idx)
        first = ew.first_valid_index()
        if first is not None:
            lvl.loc[first:] = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
        out[s] = {"members_closes": mc, "level": lvl,
                  "n_members": int(mask.iloc[-1].sum())}
    return out


def _load_meta() -> dict:
    """The validation_meta.json that GROUNDS this feature's honesty (verdict, the
    measured/de-confounded cohesion IC, survivorship gap, the AI caveats). Empty ->
    safe display-only defaults."""
    p = config.data_dir() / "group_flow" / "validation_meta.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _vix_regime(cfg: dict) -> dict:
    """VIX percentile context for the STRESS-CONDITIONAL cohesion gate — the only quasi-
    signal works only when VIX is elevated (adversarial finding). Display context."""
    df = store.read("yahoo", "_VIX")
    if df is None or "close" not in df.columns or df["close"].dropna().empty:
        return {"vix": None, "pctile": None, "elevated": False}
    s = df["close"].dropna()
    ps = pct_rank_window(s, int(cfg["vix_pctile_lookback_d"])).dropna() if len(s) >= 40 else pd.Series(dtype=float)
    p = float(ps.iloc[-1]) if len(ps) else None
    return {"vix": round(float(s.iloc[-1]), 1),
            "pctile": round(p, 3) if p is not None else None,
            "elevated": bool(p is not None and p >= cfg["vix_elevated_pctile"])}


def _cluster_map(group_levels: dict, cfg: dict) -> dict | None:
    """Cross-group co-movement structure = the supply-chain / theme-spread read: PC1
    absorption of the GROUP return block (how one-factor the rotation is), the dominant
    co-moving cluster, and the tightest co-moving pair. Reuses cross_asset's absorption
    math at the group level. Descriptive."""
    from engine import cross_asset as ca
    rb = pd.DataFrame({g: lvl.pct_change(fill_method=None) for g, lvl in group_levels.items()})
    win = rb.tail(int(cfg["cluster_window_d"])).dropna(axis=1, how="any")
    if win.shape[1] < 4 or len(win) < 20:
        return None
    cc = win.corr()
    absorp = ca._absorption_ratio(cc.to_numpy())
    pc1 = np.linalg.eigh(cc.to_numpy())[1][:, -1]
    load = pd.Series(np.abs(pc1), index=win.columns).sort_values(ascending=False)
    m = cc.to_numpy(copy=True)
    np.fill_diagonal(m, np.nan)
    mcc = pd.DataFrame(m, index=cc.index, columns=cc.columns)
    pair = mcc.stack().idxmax() if mcc.notna().any().any() else None
    regime = "concentrated" if absorp >= 0.70 else "broad" if absorp < 0.45 else "mixed"
    return {"absorption": round(float(absorp), 2), "regime": regime,
            "dominant_cluster": list(load.head(4).index),
            "top_pair": list(pair) if pair else None,
            "top_pair_corr": round(float(mcc.stack().max()), 2) if pair else None}


def _leadership(members_closes: pd.DataFrame, alpha: dict, names: dict) -> dict:
    """Who is carrying a group's recent move + the ONE-NAME GUARD (HHI). Top members by
    20d contribution; a high HHI flags a single-name mirage (the ASTS +115% class that
    fooled v1) so the AI never reads a one-stock pop as a theme."""
    mc = members_closes.tail(21).dropna(axis=1, how="any")
    if mc.shape[1] < 3:
        return {"top": [], "hhi": None, "n": 0, "breadth": None}
    r20 = mc.iloc[-1] / mc.iloc[0] - 1.0
    tot = float(r20.abs().sum())
    share = (r20.abs() / tot) if tot > 0 else r20 * 0.0
    hhi = float((share ** 2).sum())
    n = int(len(r20))
    top = [{"ticker": t, "name": names.get(t, (t, ""))[0][:22],
            "ret_20d": round(float(r20[t]), 3), "share": round(float(share[t]), 2),
            "alpha": (round(float(alpha[t]), 2) if t in alpha else None)}
           for t in r20.sort_values(ascending=False).head(3).index]
    return {"top": top, "hhi": round(hhi, 3), "n": n,
            "breadth": ("narrow" if hhi > 2.5 / n else "broad")}


def _read_quality(fp: dict, n_members: int, universe_bias: float, narrow: bool) -> float:
    """How reliable the DESCRIPTIVE characterization is (data quality + internal
    coherence) — NOT a directional confidence (the verdict is display_only). Folds
    participation breadth, cohesion level, member count, the one-name guard, and the
    universe-bias cap (sector 1.0, basket capped). `narrow` is the SAME n-relative
    HHI verdict the leadership read shows, so the bar and the ⚠narrow chip agree."""
    q = 0.55
    if fp.get("breadth") is not None:
        q += 0.15 * (fp["breadth"] - 0.5) * 2
    if fp.get("cohesion") is not None:
        q += 0.10 * min(max(fp["cohesion"], 0.0), 1.0)
    if n_members >= 12:
        q += 0.05
    if narrow:                                            # one name dominates the move
        q -= 0.20
    return float(max(0.05, min(1.0, q * universe_bias)))


def _ai_handoff(meta: dict, vix: dict) -> dict:
    """The contract handed to the downstream AI judge: focus on the right groups, but be
    STRUCTURALLY barred from inferring returns the data can't support."""
    return {
        "overall_verdict": meta.get("verdict", "display_only"),
        "reader_contract": (
            "DETECTION + DESCRIPTION layer, not a forecast. flow_score ranks where "
            "cross-sectional flow is CONCENTRATING now; it has NO validated forward edge "
            "(rank-IC ~0 on the unbiased point-in-time sector universe). Use it to FOCUS "
            "qualitative analysis on these groups, then judge durability yourself."),
        "do_not_conclude": [
            "Do NOT infer forward returns or a buy/sell from flow_score or stage.",
            "Do NOT rank sectors against baskets (different universes; baskets are hindsight-curated).",
            "Do NOT narrate the cohesion gate as 'inflows/accumulation' — it is a stress-conditional "
            "dispersion-recovery proxy, 20d only, marginal once de-confounded.",
            "Do NOT treat a narrow / high-HHI (single-name-driven) group move as a theme.",
        ],
        "ai_directive": (
            "Permitted: name what is concentrating, relate co-moving groups (cluster), flag "
            "leadership breadth, and the stress-conditional cohesion context. FORBIDDEN: "
            "directional / return language unless overall_verdict=='validated_directional'."),
        "cohesion_gate": meta.get("cohesion_gate"),
        "stress_regime_now": vix.get("elevated"),
        "survivorship_gap_20d": meta.get("survivorship_gap_20d"),
        "caveats": meta.get("cohesion_caveats", []),
        "residual_risks": meta.get("residual_risks", []),
    }


def compute_group_flows(cfg: dict | None = None) -> dict | None:
    """Latest-day flow CHARACTERIZATION over the unbiased PIT GICS sectors AND the
    thematic baskets — ranked by a DESCRIPTIVE concentration score, staged, enriched
    with the cross-group cluster map + leadership internals, and wrapped in the AI
    handoff contract. DISPLAY-ONLY, never scored (verdict from validation_meta). None
    on shortfall."""
    c = _cfg(cfg)
    s = _setup()
    if s is None:
        return None
    meta = _load_meta()
    nm = _names_sectors()
    bias_cap = float(meta.get("basket_confidence_cap", c["basket_confidence_cap"]))
    vix = _vix_regime(c)
    coh_thr = float(c["cohesion_gate_chg"])

    alpha: dict = {}                                      # residual-alpha leaders (graceful)
    try:
        from engine import residual_alpha as ra
        ral = ra.compute_residual_alpha(closes=s["closes"]) or {}
        scores = ral.get("scores") or ral.get("per_ticker") or {}
        for t, v in scores.items():
            a = v.get("alpha") if isinstance(v, dict) else v
            if a is not None and np.isfinite(a):
                alpha[t] = float(a)
    except Exception as e:  # noqa: BLE001 — leadership alpha is enrichment, never fatal
        log.warning("group_flow leadership alpha unavailable: %s", e)

    sector_levels, groups = {}, []

    def _emit(gid, name, name_zh, category, gtype, members_closes, lvl, bias, n_live):
        prep = prep_group(members_closes, lvl, s["bench"], c)
        if prep is None:
            return None
        fp = fingerprint_at(prep, len(prep["rs"]) - 1, c)
        if fp is None or fp["flow_score"] is None:
            return None
        lead = _leadership(members_closes, alpha, nm)
        narrow = lead.get("breadth") == "narrow"
        cohering = fp.get("cohesion_chg") is not None and fp["cohesion_chg"] >= coh_thr
        fp.update({
            "type": gtype, "id": gid, "name": name, "name_zh": name_zh,
            "category": category, "n_members": int(n_live),   # LIVE count, not all-time columns
            "directional": False,                        # verdict: display_only
            "flow_score_kind": "concentration",          # descriptive intensity, NOT a forecast
            "cohesion_gate": {"cohering": bool(cohering),
                              "stress_conditional": bool(cohering and vix["elevated"]),
                              "tier": "low"},
            "leadership": lead,
            "read_quality": round(_read_quality(fp, int(n_live), bias, narrow), 2),
            "directional_confidence": "low",             # display-only verdict
        })
        return fp

    # PIT GICS sectors — the unbiased integrity universe + a sector-rotation view.
    # members_closes / n_members are already point-in-time (live mask) from _pit_sector_frames.
    for sct, fr in _pit_sector_frames(s["closes"], s["rets"], c).items():
        fp = _emit(sct, sct, _SECTOR_ZH.get(sct, sct), "sector", "sector",
                   fr["members_closes"], fr["level"], 1.0, fr["n_members"])
        if fp:
            groups.append(fp)
            sector_levels[sct] = fr["level"]

    # thematic baskets — the product universe (hindsight-curated -> confidence-capped).
    # Mask each member to its dated [added, removed) window (mirrors baskets._ew_level) so
    # breadth/cohesion/leadership are PIT-consistent with the level leg, and the live count
    # excludes departed members.
    bdict = s["mem"]["baskets"]
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
    for bid, b in items:
        members = b.get("members", [])
        present = [m["ticker"] for m in members if m["ticker"] in s["rets"].columns]
        if len(present) < 3:
            continue
        lvl = _ew_level(s["rets"], members, s["idx"])
        if lvl.dropna().empty:
            continue
        mask = pd.DataFrame(False, index=s["idx"], columns=present)
        for m in members:
            t = m["ticker"]
            if t not in present:
                continue
            act = np.asarray(s["idx"] >= pd.Timestamp(m["added"]))
            if m.get("removed"):
                act = act & np.asarray(s["idx"] < pd.Timestamp(m["removed"]))
            mask[t] = act
        n_live = int(mask.iloc[-1].sum())
        if n_live < 3:
            continue
        fp = _emit(bid, b.get("name", bid), b.get("name_zh", b.get("name", bid)),
                   b.get("category", "Other"), "basket", s["closes"][present].where(mask),
                   lvl, bias_cap, n_live)
        if fp:
            groups.append(fp)

    if not groups:
        return None
    # Rank WITHIN type only — NEVER a combined cross-universe sort. Sectors are unbiased;
    # baskets are hindsight-curated; the AI handoff forbids ranking one against the other,
    # so no flat combined list ever reaches flow.json.
    sectors = sorted([g for g in groups if g["type"] == "sector"],
                     key=lambda g: g["flow_score"], reverse=True)
    baskets = sorted([g for g in groups if g["type"] == "basket"],
                     key=lambda g: g["flow_score"], reverse=True)

    def _stage_of(lst, st):
        return [g for g in lst if g["stage"] == st][:6]

    return {
        "as_of": s["idx"].max().strftime("%Y-%m-%d"),
        "verdict": meta.get("verdict", "display_only"),
        "calibrated": bool(meta.get("calibrated", False)),
        "regime": vix,
        "cluster": _cluster_map(sector_levels, c),
        "n_groups": len(groups),
        "sectors": sectors, "baskets": baskets,
        "emerging": {"sectors": _stage_of(sectors, "emerging"),
                     "baskets": _stage_of(baskets, "emerging")},
        "cooling": {"sectors": _stage_of(sectors, "cooling"),
                    "baskets": _stage_of(baskets, "cooling")},
        "ai_handoff": _ai_handoff(meta, vix),
    }
