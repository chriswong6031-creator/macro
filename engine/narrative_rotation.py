"""Thematic Narrative-Rotation engine — the "where do I allocate across themes?" brain.

Turns the descriptive thematic baskets (engine.baskets) into a disciplined, HONEST
allocation view built around a single hard-won empirical truth
(scripts/thematic_rotation_phase0.py, 27y of clean sector ETFs):

  * cross-sectional theme MOMENTUM has at best a MODEST forward edge (rank-IC ~0 on the
    unbiased universe) — it is a FOCUS / leadership lens, not alpha;
  * the absolute-TREND gate has NO mean-return edge but it HALVES volatility & drawdown
    (MaxDD -49%→-24%, worst-decile month -7.5%→-4.4%) — the one repeatable edge is
    CRASH / shake-out avoidance, i.e. *staying power*;
  * basket-aggregate crowding/extension does NOT predict basket drawdown (it is a
    per-NAME effect) — so crowding only ever DOWN-SIZES, it never times or fades.

So the engine is a trend-following, vol-aware, crowding-throttled allocator, framed as
DISCIPLINE not prediction. Five subsystems, all PURE/additive (never raise into a build):

  1 IDENTIFY    rank_themes()   residual + raw ensemble momentum, acceleration tilt,
                                absolute-trend eligibility gate  (candidate scored)
  2 DURABILITY  durability()    persistence, breadth, cohesion, rolling Hurst, trend
                                health  (DISPLAY-ONLY — coincident, confirms not forecasts)
  3 CROWDING    engine.theme_crowding  (DISPLAY-ONLY, asymmetric down-size)
  4 ROTATION    rotation_radar()  single-snapshot leadership read (rank-1 vs rank-2
                                  + margin), breadth-of-rotation, one-dominant-narrative
                                  (absorption + HHI)  (DISPLAY)
  5 ALLOCATE    allocate()      the low-turnover ruleset → SUGGESTED target weights

Output (compute_narrative_rotation) is one JSON payload + an ai_handoff contract (the
flow.json pattern) + a deterministic desk read. NEVER feeds axes/regime/macro_risk.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine.baskets import _ew_level
from lib import config, store

log = logging.getLogger(__name__)

# ---- parameters (priors from the literature + the 27y Phase-0; not curve-fit) -------
N_HOLD = 4                       # core themes held (top-4 dual was the best-Sharpe config)
MAX_PER_PARENT = 1               # de-overlap cap: ≤N held per parent super-theme (no "4 flavours of AI")
LOOKBACKS_D = (63, 126, 252)     # ensemble momentum lookbacks (~3/6/12m)
SKIP_D = 21                      # skip the most recent month (short-term reversal)
SMA_TREND_D = 200                # absolute-trend gate MA
VOL_WIN_D = 20                   # realized-vol window for inverse-vol + vol-target
POS_CAP = 0.30                   # max weight to one theme (dominant-narrative cap)
LEV_CAP = 1.4                    # max vol-scale per sleeve
MAX_CASH = 0.60                  # breadth throttle ceiling
ABSORB_DOMINANT = 0.72           # basket-return absorption above this = one-narrative regime
MIN_HISTORY_D = 160              # skip a basket with too little history
CROWD_TRIM = 0.5                 # crowding down-size strength (weight *= 1 - z·CROWD_TRIM)
# Audit #30 validate-before-weight: the crowding trim's own gate (theme_crowding Phase-0) finds
# NO forward-drawdown edge (Spearman ~0.07), so it does NOT bind allocation — DISPLAY-ONLY. Flip
# True only when a forward-drawdown edge is measured on the actual thematic baskets (not the SPDR
# proxy). When on, freed weight is redistributed (water-fill), never leaked to cash.
CROWD_TRIM_SCORED = False


# =========================================================================== #
# regions — the data plane is parameterized (mirrors engine.baskets_region) so the
# SAME engine drives the US, China A-share, Hong Kong and Canada/TSX theme pages.
# Each cfg supplies the loaders + the benchmark store + the Phase-0 artifact to cite.
# =========================================================================== #
REGION_IDS = ("us", "china", "hk", "canada")


def _region_cfg(region: str) -> dict | None:
    region = (region or "us").lower()
    if region == "us":
        from engine.baskets import _basket_extras, _membership
        from engine.equity_factors import _closes
        return {"id": "us", "market_en": "US", "market_zh": "美国",
                "bench_label": "S&P 500", "bench_label_zh": "标普500",
                "group": "yahoo", "bench_default": "SPY", "page": "allocation.html",
                "phase0_file": "thematic_rotation_phase0.json", "phase0_fallback": None,
                "membership": _membership, "closes": _closes, "extras": _basket_extras}
    if region == "china":
        from engine.baskets_china import BENCHMARK_DEFAULT, _closes, _membership
        return {"id": "china", "market_en": "China A-shares", "market_zh": "中国A股",
                "bench_label": "CSI 300", "bench_label_zh": "沪深300",
                "group": "china", "bench_default": BENCHMARK_DEFAULT, "page": "allocation_china.html",
                "phase0_file": "thematic_rotation_phase0_china.json", "phase0_fallback": None,
                "membership": _membership, "closes": _closes, "extras": None}
    if region == "hk":
        from engine.baskets_hk import BENCHMARK_DEFAULT, _closes, _membership
        return {"id": "hk", "market_en": "Hong Kong", "market_zh": "香港",
                "bench_label": "Hang Seng", "bench_label_zh": "恒生指数",
                "group": "hk", "bench_default": BENCHMARK_DEFAULT, "page": "allocation_hk.html",
                # HK sector-ETF coverage is too thin to re-validate locally → cite the US 27y proxy.
                "phase0_file": "thematic_rotation_phase0_hk.json",
                "phase0_fallback": "thematic_rotation_phase0.json",
                "membership": _membership, "closes": _closes, "extras": None}
    if region == "canada":
        from engine.baskets_canada import BENCHMARK_DEFAULT, _closes, _membership
        return {"id": "canada", "market_en": "Canada / TSX", "market_zh": "加拿大",
                "bench_label": "S&P/TSX", "bench_label_zh": "标普/TSX",
                "group": "canada", "bench_default": BENCHMARK_DEFAULT, "page": "allocation_canada.html",
                "phase0_file": "thematic_rotation_phase0_canada.json", "phase0_fallback": None,
                "membership": _membership, "closes": _closes, "extras": None}
    if region == "intl":
        # International (developed ex-US + India). Cross-country universe → the benchmark is a
        # synthetic cap-weighted composite (data/intl/_INTLC.parquet), refreshed by
        # engine.baskets_intl.refresh_composite() before the desk computes. No per-country macro
        # regime snapshot exists → _macro_context degrades to neutral (the macro leg ~0 and the
        # trend/breadth/impulse/crowding legs carry the score).
        from engine.baskets_intl import BENCHMARK_DEFAULT, _closes, _membership
        return {"id": "intl", "market_en": "International", "market_zh": "国际",
                "bench_label": "Intl ex-US", "bench_label_zh": "国际(除美)",
                "group": "intl", "bench_default": BENCHMARK_DEFAULT, "page": "baskets_intl.html",
                "phase0_file": "thematic_rotation_phase0.json", "phase0_fallback": "thematic_rotation_phase0.json",
                "membership": _membership, "closes": _closes, "extras": None}
    return None


def _setup(cfg: dict) -> dict | None:
    """Close matrix + benchmark level + the market-residual return panel for the basket-member
    union (one rolling-beta pass), for the region in `cfg`. Mirrors engine.baskets_region's
    data plane so every market is computed identically."""
    mem = cfg["membership"]()
    if not mem or not mem.get("baskets"):
        return None
    closes = cfg["closes"]()
    if closes is None or closes.empty:
        return None
    if cfg.get("extras"):                                  # US carries off-index members; regions don't
        extras = cfg["extras"]()
        if extras is not None and not extras.empty:
            add = [c for c in extras.columns if c not in closes.columns]
            if add:
                closes = closes.join(extras[add], how="left")
    rets = closes.pct_change(fill_method=None)
    idx = rets.index
    bdf = store.read(cfg["group"], mem.get("benchmark", cfg["bench_default"]))
    if bdf is None or "close" not in getattr(bdf, "columns", []):
        return None
    bench_close = bdf["close"].astype(float)
    bench_ret = bench_close.reindex(idx).ffill().pct_change(fill_method=None)
    bench = pd.Series(np.nan, index=idx)
    bf = bench_ret.first_valid_index()
    bench.loc[bf:] = (1.0 + bench_ret.loc[bf:].fillna(0.0)).cumprod()

    bdict = mem["baskets"]
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
    union = sorted({m["ticker"] for _bid, b in items for m in b.get("members", [])
                    if m["ticker"] in closes.columns})
    resid = _market_residuals(closes[union], bench_ret) if union else pd.DataFrame()
    return {"cfg": cfg, "mem": mem, "items": list(items), "closes": closes, "rets": rets,
            "idx": idx, "bench": bench, "bench_ret": bench_ret, "bench_close": bench_close,
            "resid": resid}


def _market_residuals(closes_sub: pd.DataFrame, spy_ret: pd.Series,
                      win: int = 252, shrink: float = 0.66) -> pd.DataFrame:
    """MARKET-residual returns e_i = r_i − β_i·SPY (causal rolling β, shrunk toward 1).
    Strips ONLY market beta (NOT sector — a single-sector theme's signal must survive),
    so this is Blitz-style residual momentum at the theme level."""
    R = closes_sub.pct_change(fill_method=None)
    m = spy_ret.reindex(R.index)
    minp = max(win // 2, 60)
    var = m.rolling(win, min_periods=minp).var()
    beta = R.rolling(win, min_periods=minp).cov(m).div(var, axis=0).shift(1)
    beta = (shrink * beta + (1.0 - shrink) * 1.0).clip(-2.0, 3.0)
    return R - beta.mul(m, axis=0)


# =========================================================================== #
# per-basket primitives (built once, consumed by every subsystem)
# =========================================================================== #
def _basket_preps(s: dict) -> list[dict]:
    out = []
    for bid, b in s["items"]:
        members = b.get("members", [])
        present = [m["ticker"] for m in members if m["ticker"] in s["rets"].columns]
        if len(present) < 3:
            continue
        lvl = _ew_level(s["rets"], members, s["idx"])
        if lvl.dropna().shape[0] < MIN_HISTORY_D:
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
        live = [t for t in present if bool(mask[t].iloc[-1])]
        if len(live) < 3:
            continue
        rs = lvl / s["bench"]
        resid = s["resid"][[t for t in live if t in s["resid"].columns]].where(mask[live]) \
            if not s["resid"].empty else pd.DataFrame(index=s["idx"])
        out.append({
            "id": bid, "name": b.get("name", bid), "name_zh": b.get("name_zh", b.get("name", bid)),
            "category": b.get("category", "Other"), "thesis": b.get("thesis", ""),
            "parent": b.get("parent", b.get("category", "Other")),
            "etf_proxy": b.get("etf_proxy"), "n_live": len(live), "live": live,
            "lvl": lvl, "rs": rs, "members_closes": s["closes"][live].where(mask[live]),
            "members_resid": resid,
        })
    return out


# =========================================================================== #
# 1 · IDENTIFY — momentum ranker + absolute-trend eligibility
# =========================================================================== #
def _cum_ret(lvl: pd.Series, n: int, skip: int = SKIP_D) -> float | None:
    s = lvl.dropna()
    if len(s) < n + skip + 1:
        return None
    base = s.iloc[-1 - skip - n]
    if base == 0 or not np.isfinite(base):          # cumprod level can't actually hit 0, but guard cleanly
        return None
    v = s.iloc[-1 - skip] / base - 1.0
    return float(v) if np.isfinite(v) else None


def _mom_13612w(lvl: pd.Series) -> float | None:
    s = lvl.dropna()
    if len(s) < 260:
        return None
    p = s.iloc[-1]
    legs = [(12, 21), (4, 63), (2, 126), (1, 252)]
    return float(sum(w * (p / s.iloc[-1 - d] - 1.0) for w, d in legs))


def _accel(rs: pd.Series, w: int = 63) -> float | None:
    s = rs.dropna()
    if len(s) < 2 * w + 1:
        return None
    b, c = s.iloc[-1 - w], s.iloc[-1 - 2 * w]
    if b == 0 or c == 0 or not (np.isfinite(b) and np.isfinite(c)):
        return None
    v = (s.iloc[-1] / b - 1.0) - (b / c - 1.0)
    return float(v) if np.isfinite(v) else None


def _abs_gate(lvl: pd.Series) -> tuple[bool, dict]:
    s = lvl.dropna()
    sma = s.rolling(SMA_TREND_D, min_periods=SMA_TREND_D // 2).mean()
    above = bool(s.iloc[-1] > sma.iloc[-1]) if pd.notna(sma.iloc[-1]) else False
    r12 = _cum_ret(s, 252, skip=0)
    pos12 = bool(r12 is not None and r12 > 0)
    return (above and pos12), {"above_200dma": above, "ret_12m": (round(r12, 4) if r12 is not None else None),
                               "pos_12m": pos12}


def _zscore(d: dict[str, float | None]) -> dict[str, float | None]:
    vals = pd.Series({k: v for k, v in d.items() if v is not None and np.isfinite(v)})
    if len(vals) < 3 or vals.std() == 0:
        return {k: None for k in d}
    z = (vals - vals.mean()) / vals.std()
    return {k: (round(float(z[k]), 2) if k in z.index else None) for k in d}


def rank_themes(preps: list[dict]) -> dict[str, dict]:
    """Cross-sectional momentum rank + eligibility. score = mean(z(resid_mom),
    z(13612W)) + 0.25·z(accel); eligible iff the absolute-trend gate passes.
    Candidate SCORED on the unbiased sector universe; on baskets it is confidence-capped
    (hindsight membership) — the page says so."""
    resid_mom, mom_w, accel, raw_mom = {}, {}, {}, {}
    for p in preps:
        bid = p["id"]
        rl = p["members_resid"]
        rm = None
        if not rl.empty and rl.shape[1] >= 3:
            ew = rl.mean(axis=1).dropna()
            if len(ew) > 252 + SKIP_D:
                rm = float((1.0 + ew.iloc[-(252 + SKIP_D):-SKIP_D]).prod() - 1.0)
        resid_mom[bid] = rm
        mom_w[bid] = _mom_13612w(p["lvl"])
        accel[bid] = _accel(p["rs"])
        legs = [_cum_ret(p["lvl"], n) for n in LOOKBACKS_D]
        raw_mom[bid] = float(np.mean([x for x in legs if x is not None])) if any(x is not None for x in legs) else None

    z_rm, z_mw, z_ac = _zscore(resid_mom), _zscore(mom_w), _zscore(accel)
    out = {}
    for p in preps:
        bid = p["id"]
        elig, gate = _abs_gate(p["lvl"])
        parts = [x for x in (z_rm[bid], z_mw[bid]) if x is not None]
        base = float(np.mean(parts)) if parts else None
        score = None
        if base is not None:
            score = base + (0.25 * z_ac[bid] if z_ac[bid] is not None else 0.0)
        out[bid] = {"score": round(score, 3) if score is not None else None,
                    "z_resid_mom": z_rm[bid], "z_mom_13612w": z_mw[bid], "z_accel": z_ac[bid],
                    "resid_mom": round(resid_mom[bid], 4) if resid_mom[bid] is not None else None,
                    "mom_13612w": round(mom_w[bid], 4) if mom_w[bid] is not None else None,
                    "raw_mom": round(raw_mom[bid], 4) if raw_mom[bid] is not None else None,
                    "eligible": bool(elig), "gate": gate}
    # rank by score (eligible first, then score)
    ranked = sorted(out.items(),
                    key=lambda kv: (kv[1]["score"] is None, -(kv[1]["score"] or -9)))
    for i, (bid, _v) in enumerate(ranked, 1):
        out[bid]["rank"] = i
    return out


# =========================================================================== #
# 2 · DURABILITY — coincident confirmation (DISPLAY-ONLY)
# =========================================================================== #
def _hurst(returns: np.ndarray) -> float | None:
    """Causal R/S Hurst over the window. H>0.55 trending, <0.45 mean-reverting."""
    x = np.asarray(returns, float)
    x = x[np.isfinite(x)]
    N = len(x)
    if N < 80:
        return None
    pts = []
    for n in (N, N // 2, N // 4, N // 8):
        if n < 16:
            continue
        chunks = N // n
        vals = []
        for j in range(chunks):
            seg = x[j * n:(j + 1) * n]
            z = np.cumsum(seg - seg.mean())
            rng = z.max() - z.min()
            sd = seg.std()
            if sd > 0:
                vals.append(rng / sd)
        if vals:
            pts.append((np.log(n), np.log(np.mean(vals))))
    if len(pts) < 3:
        return None
    xs, ys = zip(*pts)
    return float(np.polyfit(xs, ys, 1)[0])


def _mean_pairwise_corr(rw: pd.DataFrame) -> float | None:
    rw = rw.dropna(axis=1, thresh=int(len(rw) * 0.8))
    rw = rw.loc[:, rw.std(numeric_only=True) > 0]
    if rw.shape[1] < 3 or len(rw) < 20:
        return None
    c = rw.corr().to_numpy()
    n = c.shape[0]
    off = (np.nansum(c) - np.trace(c)) / (n * (n - 1))
    return float(off) if np.isfinite(off) else None


def durability(p: dict) -> dict:
    """Coincident trend-health read for one basket. CONFIRMS a regime; does not forecast
    the handoff (rolling estimators lag ~½ window). DISPLAY-ONLY."""
    rs = p["rs"].dropna()
    persistence = None
    if len(rs) >= 21:
        chg = rs.diff().tail(20)
        persistence = float((chg > 0).mean())
    mc = p["members_closes"]
    breadth = None
    if mc.shape[1] >= 3:
        ma50 = mc.rolling(50, min_periods=25).mean()
        b = (mc.iloc[-1] > ma50.iloc[-1])
        breadth = float(b.mean()) if b.notna().any() else None
    rets = mc.pct_change(fill_method=None)
    cohesion = _mean_pairwise_corr(rets.iloc[-60:]) if len(rets) >= 60 else None
    cohesion_prev = _mean_pairwise_corr(rets.iloc[-80:-20]) if len(rets) >= 80 else None
    cohesion_chg = (cohesion - cohesion_prev) if (cohesion is not None and cohesion_prev is not None) else None
    lvl = p["lvl"].dropna()
    hurst = _hurst(lvl.pct_change().dropna().tail(252).to_numpy())
    sma200 = lvl.rolling(SMA_TREND_D, min_periods=SMA_TREND_D // 2).mean()
    above = bool(lvl.iloc[-1] > sma200.iloc[-1]) if pd.notna(sma200.iloc[-1]) else None
    vol = float(lvl.pct_change().tail(VOL_WIN_D).std() * np.sqrt(252)) if len(lvl) > VOL_WIN_D else None
    # composite 0-1 durability bar (display): trend up, broad, cohering, persistent, trending-Hurst
    legs = []
    if above is not None:
        legs.append(1.0 if above else 0.0)
    if breadth is not None:
        legs.append(breadth)
    if persistence is not None:
        legs.append(persistence)
    if hurst is not None:
        legs.append(min(max((hurst - 0.4) / 0.3, 0.0), 1.0))
    bar = round(float(np.mean(legs)), 2) if legs else None
    htag = None if hurst is None else ("trend" if hurst > 0.55 else "mean-revert" if hurst < 0.45 else "mixed")
    return {"persistence": _r(persistence), "breadth": _r(breadth), "cohesion": _r(cohesion),
            "cohesion_chg": _r(cohesion_chg), "hurst": _r(hurst), "hurst_tag": htag,
            "above_200dma": above, "vol_ann": _r(vol), "bar": bar, "directional": False}


def _r(x, nd: int = 3):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), nd)


# =========================================================================== #
# 4 · ROTATION — leadership handoff radar + one-narrative detector (DISPLAY-ONLY)
# =========================================================================== #
def rotation_radar(preps: list[dict], ranks: dict, durab: dict, s: dict) -> dict:
    """Single-snapshot leadership read (rank-1 vs rank-2 + margin) + breadth-of-rotation
    + the one-dominant-narrative (absorption + leadership HHI) regime. NO buffering or
    hysteresis: a leadership flip registers the day the scores cross — `margin` is
    exposed so a consumer MAY buffer on it, but nothing here does. DISPLAY-ONLY —
    never gates allocate(), never predicts the next narrative (Phase-0 /
    Molchanov-Stangl: rotation timing has no edge even with foresight)."""
    ordered = sorted(ranks.items(), key=lambda kv: kv[1].get("rank", 99))
    leader_id = ordered[0][0] if ordered else None
    chall_id = ordered[1][0] if len(ordered) > 1 else None
    byid = {p["id"]: p for p in preps}

    def _nm(bid):
        return (byid[bid]["name"], byid[bid]["name_zh"]) if bid in byid else (bid, bid)

    margin = None
    if leader_id and chall_id:
        ls, cs = ranks[leader_id]["score"], ranks[chall_id]["score"]
        if ls is not None and cs is not None:
            margin = round(ls - cs, 3)

    n_elig = sum(1 for v in ranks.values() if v["eligible"])
    n_tot = len(ranks)
    breadth_frac = round(n_elig / n_tot, 2) if n_tot else None

    # one-dominant-narrative: absorption of the basket-return block + leadership HHI
    absorption = dominant = None
    rb = pd.DataFrame({p["id"]: p["lvl"].pct_change(fill_method=None) for p in preps})
    win = rb.tail(90).dropna(axis=1, how="any")
    if win.shape[1] >= 4 and len(win) >= 40:
        from engine.cross_asset import _absorption_ratio
        absorption = round(float(_absorption_ratio(win.corr().to_numpy())), 2)
    # HHI of positive momentum mass across eligible baskets (concentration of leadership)
    scores = pd.Series({bid: max(0.0, (v["score"] or 0.0)) for bid, v in ranks.items() if v["eligible"]})
    if scores.sum() > 0 and len(scores) >= 2:
        share = scores / scores.sum()
        hhi = float((share ** 2).sum())
        dominant = bool((absorption is not None and absorption >= ABSORB_DOMINANT) or hhi >= 0.5)
    le, lz = _nm(leader_id) if leader_id else (None, None)
    ce, cz = _nm(chall_id) if chall_id else (None, None)
    return {
        "leader": {"id": leader_id, "name": le, "name_zh": lz,
                   "score": ranks[leader_id]["score"] if leader_id else None,
                   "durability_bar": durab.get(leader_id, {}).get("bar")},
        "challenger": {"id": chall_id, "name": ce, "name_zh": cz,
                       "score": ranks[chall_id]["score"] if chall_id else None},
        "margin": margin,
        "breadth_of_rotation": {"eligible": n_elig, "total": n_tot, "frac": breadth_frac,
                                "view": ("broad" if (breadth_frac or 0) >= 0.5 else
                                         "narrowing" if (breadth_frac or 0) >= 0.25 else "narrow")},
        "absorption": absorption,
        "one_narrative": bool(dominant) if dominant is not None else None,
        "directional": False,
    }


# =========================================================================== #
# 5 · ALLOCATE — the low-turnover suggestion ruleset
# =========================================================================== #
def allocate(preps: list[dict], ranks: dict, crowd: dict, rot: dict,
             bench_close: pd.Series | None = None) -> dict:
    """SUGGESTED target weights (display-framed, not advice). Faithful to what the 27y
    Phase-0 actually validated: EQUAL-WEIGHT the top-N themes that pass the absolute-trend
    gate (the dual-momentum book), with a T-bill cash escape for the unfilled slots when
    fewer than N trend. Then two DISPLAY overlays the page labels as such: a crowding
    DOWN-SIZE (freed weight → cash, never redistributed up) and a momentum-crash de-risk.
    Equal-weight (not inverse-vol, not conviction-weight) is the honest choice because the
    rank's forward IC is ~0 — we ride the trending leaders, we do not bet conviction on
    the ordering."""
    byid = {p["id"]: p for p in preps}
    eligible = [bid for bid, v in ranks.items() if v["eligible"] and v["score"] is not None]
    eligible.sort(key=lambda b: ranks[b]["rank"])
    # REAL-ACTIVITY VALIDATION tie-break (upgrade-only-ahead-of-price): a theme whose
    # independent real activity is DIVERGING ahead of price (val_upgrade) is promoted EXACTLY
    # ONE slot earlier among the already-eligible leaders — never relaxing the trend gate, the
    # validated equal-weight math, POS_CAP, the crowding trim, or the crash overlay. No theme
    # flagged → this loop is a pure no-op and the book is byte-identical.
    for i in range(1, len(eligible)):
        if ranks[eligible[i]].get("val_upgrade") and not ranks[eligible[i - 1]].get("val_upgrade"):
            eligible[i - 1], eligible[i] = eligible[i], eligible[i - 1]
    # DE-OVERLAP by parent super-theme: greedily fill the top-N by rank but cap at
    # MAX_PER_PARENT per parent, so the suggested book is diversified (not "4 flavours of
    # AI"). The validated math (trend-gated, ranked by score, equal-weight) is unchanged —
    # this only diversifies WHICH trending leaders fill the slots. Skipped leaders are
    # surfaced so the displacement is transparent.
    top, par_n, deoverlapped = [], {}, []
    for bid in eligible:
        if len(top) >= N_HOLD:
            break
        par = byid.get(bid, {}).get("parent") or "Other"
        if par_n.get(par, 0) >= MAX_PER_PARENT:
            deoverlapped.append({"id": bid, "name": byid.get(bid, {}).get("name", bid),
                                 "parent": par, "rank": ranks[bid]["rank"]})
            continue
        top.append(bid)
        par_n[par] = par_n.get(par, 0) + 1

    vols = {}
    for bid in top:
        lvl = byid[bid]["lvl"].dropna()
        vols[bid] = float(lvl.pct_change().tail(VOL_WIN_D).std() * np.sqrt(252)) if len(lvl) > VOL_WIN_D else None

    # base = equal-weight 1/N over the N slots; unfilled slots (fewer than N trend) = cash
    base = 1.0 / N_HOLD
    weights = {bid: base for bid in top}
    cash = 1.0 - base * len(top)                          # the breadth-driven cash escape

    # crowding DOWN-SIZE overlay — VALIDATE-BEFORE-WEIGHT (audit #30). theme_crowding's OWN
    # Phase-0 study finds basket-aggregate crowding has NO forward-drawdown edge (Spearman ~0.07
    # on 27y); trimming ~half the held themes every run (crowding_z is centered ~0) leaked a
    # persistent one-way drag straight to cash. So:
    #   • the trim is DISPLAY-ONLY (CROWD_TRIM_SCORED=False) — computed and surfaced as a shadow
    #     (crowd_trim_shadow) but NOT applied, until a forward-drawdown edge is measured; and
    #   • if it is ever gated on, freed weight is REDISTRIBUTED across the other held themes
    #     (water-fill), never leaked to cash (a crowding read is not a de-gross signal).
    crowd_trim_shadow = {}
    for bid in top:
        cz = crowd.get(bid, {}).get("crowding_z")
        crowd_trim_shadow[bid] = round(base * min(cz, 1.0) * CROWD_TRIM, 4) \
            if (cz is not None and cz > 0) else 0.0
    if CROWD_TRIM_SCORED:
        freed = 0.0
        for bid in top:
            trim = crowd_trim_shadow.get(bid, 0.0)
            if trim > 0:
                weights[bid] -= trim
                freed += trim
        # redistribute freed weight to the UN-trimmed held themes (water-fill), not to cash
        recipients = [b for b in top if crowd_trim_shadow.get(b, 0.0) <= 0]
        if freed > 0 and recipients:
            add = freed / len(recipients)
            for b in recipients:
                weights[b] += add
        elif freed > 0:                                  # everyone trimmed -> pro-rata back
            tot = sum(weights[b] for b in top) or 1.0
            for b in top:
                weights[b] += freed * (weights[b] / tot)

    # position cap (dominant-narrative cap) — binds only at small N
    for bid in top:
        if weights[bid] > POS_CAP:
            cash += weights[bid] - POS_CAP
            weights[bid] = POS_CAP

    # momentum-crash overlay (Daniel-Moskowitz): bear tape + high vol → halve to cash
    crash = _crash_state(bench_close)
    if crash["active"]:
        for b in list(weights):
            weights[b] *= 0.5
        cash = 1.0 - sum(weights.values())

    sugg = [{"id": b, "name": byid[b]["name"], "name_zh": byid[b]["name_zh"],
             "category": byid[b].get("category"), "parent": byid[b].get("parent"),
             "weight": round(weights[b], 3), "rank": ranks[b]["rank"],
             "vol_ann": _r(vols.get(b)),
             "crowding_z": crowd.get(b, {}).get("crowding_z"),
             "crowded": crowd.get(b, {}).get("crowded", False),
             # display-only shadow: what the crowding trim WOULD subtract (not applied unless
             # CROWD_TRIM_SCORED). Lets the page show the caution without the null-signal drag.
             "crowd_trim_shadow": crowd_trim_shadow.get(b, 0.0),
             "crowd_trim_applied": bool(CROWD_TRIM_SCORED and crowd_trim_shadow.get(b, 0.0) > 0),
             "val_z": ranks[b].get("val_z"), "val_upgrade": bool(ranks[b].get("val_upgrade")),
             "val_state": ranks[b].get("val_state")}
            for b in sorted(top, key=lambda x: ranks[x]["rank"])]
    cash = round(max(0.0, 1.0 - sum(s["weight"] for s in sugg)), 3)   # exact remainder of the rounded book
    vol_overlay = _vol_overlay(top, weights, byid)                    # calibrated de-risk overlay (optional)
    return {"weights": sugg, "cash": cash,
            "n_held": len(top), "crash_overlay": crash,
            "vol_overlay": vol_overlay,
            "de_overlapped": deoverlapped,
            "crowd_trim_gate": {
                "scored": bool(CROWD_TRIM_SCORED),
                "basis": "measured",
                "verdict": ("scored" if CROWD_TRIM_SCORED else "display-only"),
                "note": ("basket-aggregate crowding has NO forward-drawdown edge "
                         "(theme_crowding Phase-0, Spearman ~0.07 / 27y) — trim shown as a "
                         "shadow, not applied; when scored, freed weight redistributes "
                         "(water-fill) rather than leaking to cash"),
                "artifact": "scripts/thematic_rotation_phase0.py"},
            "rule": (f"Equal-weight the top-{N_HOLD} themes above their own 200d trend "
                     "(the validated dual-momentum book), DE-OVERLAPPED to at most "
                     f"{MAX_PER_PARENT} per parent super-theme so the book stays diversified; "
                     "idle slots sit in T-bills; "
                     + ("crowded themes are trimmed and the freed weight is redistributed across "
                        "the other held themes; " if CROWD_TRIM_SCORED else
                        "the crowding trim is display-only (no measured drawdown edge — not "
                        "applied to weight); ")
                     + f"capped at {int(POS_CAP*100)}%/theme."),
            "directional": False}


def _crash_state(bench_close: pd.Series | None = None) -> dict:
    """Broad-market panic gate: the region BENCHMARK's trailing-24m return < 0 AND realized
    vol top-quartile — the Daniel-Moskowitz state where laggard up-beta makes momentum crash.
    `bench_close` is the region index level (SPY / CSI300 / HSI / TSX); defaults to SPY."""
    p = bench_close.astype(float).dropna() if bench_close is not None else None
    if p is None:
        spy = store.read("yahoo", "SPY")
        if spy is None or "close" not in spy.columns:
            return {"active": False}
        p = spy["close"].astype(float).dropna()
    if len(p) < 600:
        return {"active": False}
    r24 = float(p.iloc[-1] / p.iloc[-min(504, len(p) - 1)] - 1.0)
    vol = p.pct_change().tail(21).std() * np.sqrt(252)
    vhist = p.pct_change().rolling(21).std().mul(np.sqrt(252)).dropna()
    vpct = float((vhist <= vol).mean()) if len(vhist) else 0.0
    active = bool(r24 < 0 and vpct >= 0.75)
    return {"active": active, "bench_ret_24m": round(r24, 3), "vol_pctile": round(vpct, 2)}


# =========================================================================== #
# assemble
# =========================================================================== #
def _validation_meta(fname: str = "thematic_rotation_phase0.json") -> dict:
    p = config.data_dir() / "strategies" / fname
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _sizing_calibration() -> dict:
    """The book-level vol-target SIZING verdict from scripts.calibrate_baskets (the 27y
    SPDR-sector proxy). Display-framed; the signal LOGIC is shared cross-region so the
    US-proxy verdict is cited cross-market (as the phase0 already is). {} if absent."""
    try:
        p = config.data_dir() / "strategies" / "baskets_calibration.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        return d.get("sizing", {}) if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _vol_overlay(top: list, weights: dict, byid: dict) -> dict | None:
    """Book-level realized-vol-target DE-RISK overlay (Moreira-Muir), display-framed. Reads
    the calibrated `sizing` block: when the proxy backtest graded it calibratable/display_only
    it scales the whole book by clip(target_vol / trailing book-vol, floor, cap) — a pure
    DRAWDOWN lever (the proxy showed ~7pp shallower MaxDD, beats a trend-only brake, but NO
    Sharpe lift), residual gross to cash. `applied` is True only when calibratable; otherwise
    it is OFFERED with its measured provenance, never forced onto the default book. Wires the
    previously-vestigial LEV_CAP (gross ceiling) + MAX_CASH (de-risk floor). None if absent."""
    cal = _sizing_calibration()
    if not cal or cal.get("verdict") not in ("calibratable", "display_only") or not top:
        return None
    d = cal.get("default") or {}
    vol_win = int(d.get("vol_win", VOL_WIN_D))
    target_mult = float(d.get("target_mult", 0.85))
    cap = min(float(d.get("cap", LEV_CAP)), LEV_CAP)               # wire LEV_CAP as the hard gross ceiling
    floor = float(d.get("floor", 0.0))
    cols = {bid: byid[bid]["lvl"].pct_change() for bid in top if bid in byid}
    w0 = {bid: float(weights.get(bid, 0.0)) for bid in top}
    gross0 = sum(w0.values())
    if not cols or gross0 <= 0:
        return None
    book = pd.DataFrame(cols)
    book_ret = (book * pd.Series(w0)).sum(axis=1) / gross0          # weighted book return
    bv = (book_ret.rolling(vol_win).std() * np.sqrt(252)).dropna()
    if bv.shape[0] <= vol_win:
        return None
    book_vol = float(bv.iloc[-1])
    # RELATIVE target = target_mult x the book's own trailing-median vol — computed with the
    # EXACT same rolling form as scripts.calibrate_baskets._book_voltarget so the live scalar
    # reproduces the backtested one (no faithfulness drift).
    med = bv.rolling(756, min_periods=252).median().iloc[-1]
    target = target_mult * float(med) if pd.notna(med) else None
    if not book_vol or not np.isfinite(book_vol) or not target:
        return None
    # floor matches the BACKTEST (SZ_FLOOR) so the measured DD-reduction applies to what we
    # show; the de-risk-only property comes from cap<=1.0, not the floor. (MAX_CASH governs
    # the rotation cash escape, not this overlay — flooring here would weaken the validated cut.)
    scalar = float(np.clip(target / book_vol, floor, cap))
    derisked = {bid: round(weights[bid] * scalar, 3) for bid in weights}
    new_gross = round(sum(derisked.values()), 3)
    ddci = (cal.get("dd_reduction_ci") or {}).get("dd_reduction_pp_ci") or [None, None, None]
    med = ddci[1]
    return {
        "applied": cal.get("verdict") == "calibratable",
        "scalar": round(scalar, 3), "target_vol": target, "vol_win": vol_win, "cap": cap,
        "book_vol_ann": round(book_vol, 3),
        "gross_before": round(gross0, 3), "gross_after": new_gross,
        "cash_after": round(max(0.0, 1.0 - new_gross), 3),
        "weights": [{"id": b, "name": byid[b]["name"], "name_zh": byid[b].get("name_zh", byid[b]["name"]),
                     "weight": derisked[b]} for b in top],
        "measured": {"verdict": cal.get("verdict"), "dd_reduction_pp_ci": ddci,
                     "beats_trend_brake": cal.get("beats_brake"), "dsr": cal.get("dsr"),
                     "n_trials": cal.get("n_trials")},
        "note_en": (f"Optional de-risk overlay — scale the book toward a ~{int(target * 100)}% vol "
                    f"target. Backtested on 27y of clean sector history it cut max-drawdown by "
                    f"~{med}pp (CI {ddci}) and beat a trend-only brake, but it does NOT lift Sharpe "
                    f"(you trade CAGR for a shallower drawdown) — so it is OFFERED, not forced."),
        "note_zh": (f"可选降风险叠加 — 将组合缩放至约 {int(target * 100)}% 波动率目标。在27年干净行业历史回测中，"
                    f"最大回撤降低约 {med}pp（区间 {ddci}），并优于纯趋势刹车；但不提升夏普（以CAGR换取更浅回撤）"
                    f"— 故为可选项而非强制。"),
        "directional": False,
    }


def _ai_handoff(rot: dict) -> dict:
    return {
        "overall_verdict": "discipline_not_prediction",
        "reader_contract": (
            "This ranks where thematic LEADERSHIP and FLOW are concentrating and suggests a "
            "trend-following, vol-aware allocation. The ONE validated edge (multi-decade sector "
            "backtests) is DRAWDOWN/shake-out avoidance via the absolute-trend gate — NOT return "
            "forecasting. Momentum rank ≈ a focus lens (rank-IC ~0 on clean sectors). Use to "
            "size & de-risk, then judge narrative durability yourself."),
        "do_not_conclude": [
            "Do NOT read the momentum rank as a return forecast or a buy list.",
            "Do NOT treat crowding/extension as a SELL, a SHORT, or a basket-drawdown timer "
            "(it has no basket-level forward edge; it only DOWN-SIZES).",
            "Do NOT fade the dominant theme on a crowding flag — cap it, do not fade it "
            "(reflexivity; fading the leader is the documented failure mode).",
            "Do NOT predict the NEXT narrative — only flag a CONFIRMED leadership handoff.",
            "Do NOT treat thematic-ETF inflows or attention spikes as a BUY (they mark tops).",
        ],
        "ai_directive": (
            "Permitted: name the prevailing narrative, judge its durability from breadth/"
            "cohesion/trend-health, flag crowding as a sizing caution, and describe the "
            "one-narrative-vs-everything structure. Produce ONE falsifiable conditional lean "
            "with a check-by horizon. FORBIDDEN: directional certainty, fade calls, next-theme "
            "prediction, or letting any of this feed a score."),
        "one_narrative_dominant": rot.get("one_narrative"),
        "absorption": rot.get("absorption"),
    }


def _narrate(rot: dict, alloc: dict, ranks: dict, durab: dict, crowd: dict,
             preps: list[dict]) -> dict:
    """Deterministic desk read (no LLM) — the honest synthesis the page leads with."""
    L = rot["leader"]
    byid = {p["id"]: p for p in preps}
    lead_id = L["id"]
    led = durab.get(lead_id, {})
    lcr = crowd.get(lead_id, {})
    # theme_context health-awareness: read breadth/r10/val_state from the leader's row
    _lead_row = ranks.get(lead_id, {}) if isinstance(ranks, dict) else {}
    _lead_breadth = led.get("breadth")   # durability breadth (pct members > 50d MA)
    _lead_r10 = None                      # r10 is in rows not ranks dict — tolerate absence
    _lead_val_state = _lead_row.get("val_state")
    # find the leader's r10 from preps rows (after rank_themes; additive read)
    _lead_prep = byid.get(lead_id)
    if _lead_prep is not None:
        try:
            _lvl = _lead_prep["lvl"]
            _r10_raw = _cum_ret(_lvl, 10, skip=0)
            _lead_r10 = _r10_raw
        except Exception:  # noqa: BLE001
            pass
    _lead_breaking = (
        (_lead_breadth is not None and _lead_breadth <= 0.25)
        or _lead_val_state == "fading"
    )
    bits_en, bits_zh = [], []
    if L["name"]:
        if _lead_breaking:
            # health-aware first clause (contract §narrative_rotation additions)
            bits_en.append(
                f"<b>{L['name']}</b> still ranks first by trailing momentum, "
                "but is breaking down now (few members holding up)"
            )
            bits_zh.append(
                f"<b>{L['name_zh']}</b> 按趋势动量仍居首位，但近期正在走弱（成分股多数转弱）"
            )
        else:
            dbar = led.get("bar")
            dtxt = ("durable" if (dbar or 0) >= 0.66 else "firm" if (dbar or 0) >= 0.4 else "fragile")
            bits_en.append(f"<b>{L['name']}</b> leads the themes (durability {dtxt})")
            bits_zh.append(f"<b>{L['name_zh']}</b> 领跑主题（持续性{ {'durable':'强','firm':'中','fragile':'弱'}[dtxt] }）")
    if rot.get("one_narrative"):
        bits_en.append(f"one narrative dominates (absorption {rot.get('absorption')}) — the leader is "
                       f"capped at {int(POS_CAP*100)}%, not faded, with the remainder routed to "
                       "broadening themes")
        bits_zh.append(f"单一叙事主导（共动 {rot.get('absorption')}）— 领跑者封顶 {int(POS_CAP*100)}%，"
                       "不做反向，其余配置流向扩散中的主题")
    else:
        bov = rot["breadth_of_rotation"]
        bits_en.append(f"leadership is {bov['view']} ({bov['eligible']}/{bov['total']} themes in uptrend)")
        bits_zh.append(f"领跑面 {('广泛' if bov['view']=='broad' else '收窄' if bov['view']=='narrowing' else '狭窄')}"
                       f"（{bov['eligible']}/{bov['total']} 个主题处于上行趋势）")
    if lcr.get("crowded"):
        bits_en.append(f"the leader is crowded (z {lcr.get('crowding_z')}) → sized down, not sold")
        bits_zh.append(f"领跑者拥挤（z {lcr.get('crowding_z')}）→ 降低仓位，而非卖出")
    if alloc["crash_overlay"].get("active"):
        bits_en.append("market in a crash-risk state → exposure halved to cash")
        bits_zh.append("市场处于崩盘风险状态 → 敞口减半至现金")
    cash_pct = int(round(alloc["cash"] * 100))
    bits_en.append(f"suggested cash {cash_pct}%")
    bits_zh.append(f"建议现金 {cash_pct}%")
    return {"en": "; ".join(bits_en) + ".", "zh": "；".join(bits_zh) + "。"}


def compute_narrative_rotation(region: str = "us") -> dict | None:
    """Top-level: assemble the five subsystems into one display payload + AI handoff +
    deterministic desk read, for `region` ∈ {us, china, hk, canada}. PURE/additive —
    returns None on shortfall, never raises."""
    try:
        cfg = _region_cfg(region)
        if cfg is None:
            return None
        s = _setup(cfg)
        if s is None:
            return None
        preps = _basket_preps(s)
        if len(preps) < 4:
            return None

        ranks = rank_themes(preps)

        # REAL-ACTIVITY VALIDATION overlay (display + bounded one-slot tie-break in allocate).
        # Annotates ranks with val_z/val_state/val_upgrade from the Divergence Radar; NEVER
        # touches score/rank/eligible (the price-scored core stays byte-identical). Additive.
        try:
            from engine import theme_validation
            theme_validation.apply_validation(ranks, region)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("theme_validation overlay skipped: %s", e)

        durab, crowd = {}, {}
        from engine import extension as ext_mod
        from engine import theme_crowding as tc
        # short interest snapshot (context only)
        si = None
        sp = config.data_dir() / "finra" / "short_interest.parquet"
        if sp.exists():
            try:
                si = pd.read_parquet(sp)
            except Exception:  # noqa: BLE001
                si = None
        dtc_map = {}
        if si is not None and "days_to_cover" in si.columns:
            col = si.set_index(si.columns[0])["days_to_cover"] if si.index.name is None else si["days_to_cover"]
            try:
                dtc_map = si.set_index(si.columns[0])["days_to_cover"].to_dict()
            except Exception:  # noqa: BLE001
                dtc_map = {}

        for p in preps:
            durab[p["id"]] = durability(p)
            ext_rows = list(ext_mod.extension_signals(p["members_closes"]).values())
            dtc = [dtc_map.get(t) for t in p["live"]] if dtc_map else None
            crowd[p["id"]] = tc.basket_crowding(p["members_resid"], p["rs"], ext_rows, dtc)

        rot = rotation_radar(preps, ranks, durab, s)
        alloc = allocate(preps, ranks, crowd, rot, s["bench_close"])
        narr = _narrate(rot, alloc, ranks, durab, crowd, preps)

        # per-basket table (display)
        byid = {p["id"]: p for p in preps}
        rows = []
        for bid, rk in sorted(ranks.items(), key=lambda kv: kv[1].get("rank", 99)):
            p = byid[bid]
            # fast-tape read: 10d equal-weight basket return with NO skip — exactly the
            # recent window the strategic ensemble excludes by construction (SKIP_D).
            # Built here, after allocate(), so it cannot feed rank/score/eligible/weights.
            r10 = _cum_ret(p["lvl"], 10, skip=0)
            rows.append({
                "id": bid, "name": p["name"], "name_zh": p["name_zh"],
                "category": p["category"], "thesis": p["thesis"], "n_live": p["n_live"],
                "r10": round(r10, 4) if r10 is not None else None,
                "rank": rk["rank"], "score": rk["score"], "eligible": rk["eligible"],
                "z_resid_mom": rk["z_resid_mom"], "z_mom_13612w": rk["z_mom_13612w"],
                "z_accel": rk["z_accel"], "gate": rk["gate"],
                "etf_proxy": p.get("etf_proxy"),       # for the AI desk's scorable theme_rel_return falsifier
                "durability": durab[bid], "crowding": crowd[bid],
                "val_z": rk.get("val_z"), "val_upgrade": bool(rk.get("val_upgrade")),
                "val_state": rk.get("val_state"),     # real-activity validation overlay (display)
            })

        vm = _validation_meta(cfg["phase0_file"])
        sect = (vm.get("universes", {}) or {}).get("sectors", {})
        borrowed_from = None
        if not sect and cfg.get("phase0_fallback"):       # HK: too few sector ETFs → cite US 27y
            fb = _validation_meta(cfg["phase0_fallback"])
            fbsect = (fb.get("universes", {}) or {}).get("sectors", {})
            if fbsect:
                sect, vm, borrowed_from = fbsect, fb, "US — 27-year SPDR sectors"
        bt = {
            "verdict": vm.get("verdict", {}),
            "gate_helps": vm.get("gate_helps"),
            "borrowed_from": borrowed_from,
            "sectors": {
                "span": sect.get("span"),
                "dual": sect.get("algorithm", {}).get("top4_mom12_dual"),
                "rel": sect.get("algorithm", {}).get("top3_mom12_rel"),
                "buyhold": sect.get("algorithm", {}).get("ew_buyhold"),
                "tsmom": sect.get("tsmom_conditional"),
                "rank_ic": sect.get("rank_ic"),
            } if sect else None,
        }

        # headline = the PREVAILING NARRATIVE (rank-1 eligible theme), with its suggested
        # weight — not the largest sleeve. This is the "current best place to allocate".
        headline = None
        wmap = {w["id"]: w for w in alloc["weights"]}
        lead = next((w for w in sorted(alloc["weights"], key=lambda x: x["rank"])), None)
        if lead is not None:
            durb = durab.get(lead["id"], {})
            # Additive health fields (theme_context.v1 contract) — null-safe reads from rows.
            # breadth/r10/val_state only; desk_score attached in build_baskets where theme_intel exists.
            _lead_rows_hit = next((r for r in rows if r.get("id") == lead["id"]), {})
            headline = {"id": lead["id"], "name": lead["name"], "name_zh": lead["name_zh"],
                        "weight": lead["weight"], "cash": alloc["cash"],
                        "durability_bar": durb.get("bar"),
                        "hurst_tag": durb.get("hurst_tag"),
                        "crowded": lead.get("crowded", False),
                        "one_narrative": rot.get("one_narrative"),
                        # health context (additive; null until rows populated)
                        "breadth": (durb.get("breadth")),
                        "r10": _lead_rows_hit.get("r10"),
                        "val_state": _lead_rows_hit.get("val_state")}

        return {
            "as_of": s["idx"].max().strftime("%Y-%m-%d"),
            "region": cfg["id"], "market_en": cfg["market_en"], "market_zh": cfg["market_zh"],
            "bench_label": cfg["bench_label"], "bench_label_zh": cfg["bench_label_zh"],
            "n_themes": len(preps),
            "headline": headline,
            "narration": narr,
            "ranks": rows,
            "rotation": rot,
            "allocation": alloc,
            "backtest": bt,
            "ai_handoff": _ai_handoff(rot),
            "verdict": "discipline_not_prediction",
            "params": {"n_hold": N_HOLD, "lookbacks_d": list(LOOKBACKS_D), "skip_d": SKIP_D,
                       "sma_trend_d": SMA_TREND_D, "pos_cap": POS_CAP, "max_cash": MAX_CASH},
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("compute_narrative_rotation failed: %s", e)
        return None
