"""Froth & Fragility — a DISPLAY-ONLY macro top-risk gauge that measures retail
euphoria AND hidden distribution, the two halves a single VIX read cannot see.

WHY this exists (the regime it is built for): an index can be pinned near its high
while it quietly DISTRIBUTES — the mega-cap leaders "take turns" rolling over so the
tape grinds lower without a -5% crash day, and VIX stays asleep because falling
single-stock correlation MASKS the damage (σ_index ≈ √ρ · σ̄_single-name). Meanwhile
the leadership complex (semis / memory / HBM) goes PARABOLIC on retail euphoria — no
fear, no hedging bid. VIX, being coincident index implied-vol, is structurally blind
to this. This gauge fuses the LEADING internals that are not:

  FACE A — EUPHORIA   : how stretched the crowd is (semis/AI parabolicity is the one
                        DEEP, regime-specific SCORED leg; put/call, NAAIM, news, skew,
                        crypto, WSB ride along DISPLAY-ONLY until their history accrues).
  FACE B — FRAGILITY  : hidden distribution under a pinned index — the STEALTH
                        DISTRIBUTION sub-score (dominant), A/D-line non-confirmation,
                        %>200dma divergence, cross-asset absorption.

The honest headline is the 2D DANGER-QUADRANT (Euphoric AND Fragile), with a derived
soft-AND scalar bar and a "stealth-primed" early tier that can light before the first
leg down.

DISCIPLINE — honest by construction (mirrors engine/vol_shock_scorecard.py,
engine/risk_radar.py, engine/conditions.py complacency mirror):
  • DISPLAY-ONLY. It feeds NO score, NO allocation, NO per-ticker signal. The only
    sanctioned response to a firing is SIZING (de-risk), never selection. It writes
    ONLY latest["froth_fragility"] and is read ONLY by scripts/build_site.py. Nothing
    in regime / axes / conditions(_macro_risk_legs) / RORO / MRS / signal_* reads it.
  • Renormalized weighted mean over AVAILABLE legs only (a missing / display-only leg
    drops out of BOTH numerator and denominator), with per-leg `points` that SUM to the
    face score (no black box). Mirrors vol_shock's num/den accumulation.
  • YOUNG / unvalidated legs are HARD-ZEROED (eff_w=0) — structurally unable to move any
    score — and graduate into a scored input only by a deliberate one-flag _SCORED_LEGS
    PR after their forward-log slice beats base-rate over >=30 matured firings.
  • A FORWARD OUTCOME LOG (append/resolve/track_record) accrues each firing against a
    PRE-REGISTERED outcome (QQQ/SMH drawdown OR a VIX jump over h10/h21/h42) so the
    gauge can be GRADED before it is ever allowed to govern anything.

Pure function of the stored dicts + the on-disk price/breadth stores. Deterministic,
unit-testable, wrapped so it NEVER raises into the build (degrade-never-raise).

See research dossier + design panel: this module's weights are PANEL-SET PRIORS.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, nyse_calendar

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Cohorts (basket keys resolved live; see data/baskets/membership.json)
# --------------------------------------------------------------------------- #
PARAB_BASKETS = ["ai_semiconductors", "memory_storage", "semicap_equipment"]  # Face A euphoria
MEGACAP_BASKETS = ["mag7"]                                                    # index-movers: ρ̂ / leaders / VIX-mask
LEADER_BASKETS = ["mag7", "ai_semiconductors", "memory_storage"]             # broader leadership (B3 damage chip)
DEFENSIVE_ETFS = ["XLP", "XLU", "XLV"]
OFFENSE_ETFS = ["XLK", "XLY"]

# --------------------------------------------------------------------------- #
# Config — PANEL-SET PRIORS. Graduation of any display-only leg into a scored
# input is a deliberate one-flag flip in _SCORED_LEGS gated on the forward log.
# --------------------------------------------------------------------------- #
_SCORED_LEGS = {
    # Face A — only semis/AI parabolicity scores (DEEP, regime-specific). The rest are
    # rendered as display-only "accruing/context" chips (eff_w=0, hard-zeroed).
    "A4_parab": True, "A2_naaim": False, "A1_putcall": False, "A3_news": False,
    "A5_rr": False, "A6_crypto": False,
    # Face B — stealth + leadership-distribution + A/D + %>200dma + absorption score.
    "B_stealth": True, "B_leaddist": True, "B1_ad_div": True, "B2_pct200_div": True,
    "B4_absorption": True,
    "B3_med_dd": False, "B5_rsp_spy": False, "B7_complacency": False,
}

_CFG = {
    "weights_face_a": {"A4_parab": 1.00},
    # Two hidden-distribution modes carry the most weight: B_stealth (broad 2000-style
    # breadth-rot; its leg-3 also scores the breadth of leaders below their 50dma) and
    # B_leaddist (the ORTHOGONAL magnitude of the leaders-vs-index drawdown gap). Breadth-
    # of-leaders and gap-magnitude are deliberately split so the two do not double-count.
    "weights_face_b": {
        "B_stealth": 0.28, "B_leaddist": 0.24, "B1_ad_div": 0.22,
        "B2_pct200_div": 0.13, "B4_absorption": 0.13,
    },
    "weights_stealth": {  # legs 2-6 (leg 1 is the gate); renormalized over available
        "S2_breadth": 0.25, "S3_leaders": 0.25, "S4_corr": 0.20,
        "S5_defensives": 0.20, "S6_vix": 0.10,
    },
    # bands on the 0-100 scale (low edge inclusive); mirror vol_shock._band ordering
    "bands": [("calm", 0), ("watch", 55), ("elevated", 68), ("high", 78), ("extreme", 88)],
    "alert_from": "elevated",
    "horizons": {"h10": 10, "h21": 21, "h42": 42},
    "outcome_dd_pct": 8.0, "outcome_vix_mult": 1.5,
    "stealth_fire_score": 60, "stealth_fire_minlit": 4,
    "quadrant_face_thresh": 68, "stealth_primed_face_a": 55,
    "gate_high_prox": 0.94,            # armed within ~6% of the 60d high
    "rotation_prox": 0.88,            # -6%..-12% -> rotation_in_progress band floor
    "cohort_min_rows": 120,           # matches extension_signals min_periods
    "cohort_min_members": 3,
    "parab_min_history": 12,          # below this -> raw-fraction fallback
    "graduation_min_firings": 30,
}

_BAND_ZH = {"calm": "平静", "watch": "关注", "elevated": "升高", "high": "偏高", "extreme": "极端"}
_QUAD_LABELS = {
    "euphoric_fragile": ("Euphoric & Fragile — distribution top risk", "欣喜且脆弱——派发顶部风险"),
    "narrowing_top": ("Euphoric, leaders distributing under a held index — narrowing-top risk",
                      "欣喜，但龙头在被托住的指数下派发——顶部收窄风险"),
    "stealth_primed": ("Stealth-primed (early, uncertain)", "潜伏派发预警（偏早、不确定）"),
    "distribution_in_progress": ("Distribution in progress", "派发进行中"),
    "euphoric_extended": ("Euphoric & extended (not yet distributing)", "欣喜且拉伸（尚未派发）"),
    "visible_stress": ("Visible stress (not stealth)", "压力已显（非潜伏）"),
    "benign": ("Calm & broad", "平静且广泛"),
}


# --------------------------------------------------------------------------- #
# Small defensive helpers
# --------------------------------------------------------------------------- #
def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _band(x: float | None) -> tuple[str | None, str | None]:
    if x is None:
        return None, None
    lab = "calm"
    for name, edge in _CFG["bands"]:
        if x >= edge:
            lab = name
    return lab, _BAND_ZH.get(lab)


def _color(sub01: float | None) -> str:
    if sub01 is None:
        return "#888"
    if sub01 >= 0.70:
        return "#d04545"
    if sub01 >= 0.45:
        return "#e0a030"
    return "#5a9bd4"


def _asof(latest: dict) -> str | None:
    a = (latest or {}).get("date")
    if a:
        return str(a)
    for k in ("cross_asset", "conditions"):
        v = (latest or {}).get(k) or {}
        if isinstance(v, dict) and v.get("asof"):
            return str(v["asof"])
    return None


# --------------------------------------------------------------------------- #
# Price / membership loaders (cached, guarded)
# --------------------------------------------------------------------------- #
_MEMBERSHIP: dict | None = None
_CLOSE_CACHE: dict[str, pd.Series | None] = {}


def _membership() -> dict:
    global _MEMBERSHIP
    if _MEMBERSHIP is None:
        try:
            mj = json.loads((config.data_dir() / "baskets" / "membership.json").read_text())
            _MEMBERSHIP = mj.get("baskets", mj)
        except Exception as e:  # noqa: BLE001
            log.warning("froth_fragility: membership unreadable (%s)", e)
            _MEMBERSHIP = {}
    return _MEMBERSHIP


def _live_members(basket_keys: list[str]) -> list[str]:
    bk = _membership()
    out: list[str] = []
    for key in basket_keys:
        for m in (bk.get(key, {}) or {}).get("members", []) or []:
            if m.get("removed") is None and m.get("ticker"):
                out.append(m["ticker"])
    # de-dupe, preserve order
    seen: set[str] = set()
    return [t for t in out if not (t in seen or seen.add(t))]


def _close(ticker: str) -> pd.Series | None:
    """Daily close for any name/ETF via the canonical loader (deep baskets store ->
    data/stocks -> data/yahoo). Cached. Never raises."""
    if ticker in _CLOSE_CACHE:
        return _CLOSE_CACHE[ticker]
    s: pd.Series | None = None
    try:
        from engine.basket_index import _load_member_ohlcv
        df = _load_member_ohlcv(ticker)
        if df is not None and not df.empty and "close" in df.columns:
            s = df["close"].dropna()
    except Exception as e:  # noqa: BLE001
        log.debug("froth_fragility: close load failed %s (%s)", ticker, e)
        s = None
    _CLOSE_CACHE[ticker] = s
    return s


def _close_at(ticker: str, asof: str | None) -> pd.Series | None:
    """Close truncated to <= asof (point-in-time; no look-ahead under backfill/replay)."""
    s = _close(ticker)
    if s is not None and asof:
        try:
            s = s.loc[:asof]
        except Exception:  # noqa: BLE001
            pass
    return s


def _closes_matrix(tickers: list[str], asof: str | None, min_rows: int) -> pd.DataFrame:
    """date x ticker close matrix, truncated at `asof`, dropping names with < min_rows
    valid observations as of that date. Empty frame on failure."""
    cols = {}
    for t in tickers:
        s = _close(t)
        if s is None or s.empty:
            continue
        if asof:
            try:
                s = s.loc[:asof]
            except Exception:  # noqa: BLE001
                pass
        if s.dropna().shape[0] >= min_rows:
            cols[t] = s
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).sort_index()


# NOTE on cohort choice: the leadership reads (Stealth leg-3, B_leaddist) use the CURRENT
# mega-cap cohort, not point-in-time S&P-1500 membership. For a FORWARD-ONLY gauge this is
# the right read (you watch today's generals; each daily reading is inherently PIT and the
# forward log accrues from today, so there is no survivorship bias in the live signal —
# survivorship would only bias a historical backtest, which this gauge does not run).


# --------------------------------------------------------------------------- #
# FACE A — EUPHORIA  (A4 semis/AI parabolicity is the only scorer)
# --------------------------------------------------------------------------- #
def _parab_path() -> Path:
    return config.data_dir() / "froth_fragility" / "parab_history.parquet"


def _cohort_pct_parab(closes: pd.DataFrame, spy: pd.Series | None) -> float | None:
    """Cohort breadth-of-parabolicity (0-100) for the LIVE members in `closes`, via the
    validated engine.extension + engine.theme_crowding path. None if < 3 graded names."""
    try:
        from engine import extension as _ext
        from engine import theme_crowding as _tc
        if closes is None or closes.shape[1] < _CFG["cohort_min_members"]:
            return None
        ext_map = _ext.extension_signals(closes)
        ext_rows = [ext_map[t] for t in closes.columns if t in ext_map]
        if len(ext_rows) < _CFG["cohort_min_members"]:
            return None
        # residual returns vs SPY (market-residual), and the EW-RS-vs-SPY line
        rets = closes.pct_change(fill_method=None)
        rs = None
        if spy is not None and not spy.empty:
            spy_r = spy.reindex(closes.index).pct_change(fill_method=None)
            resid = rets.sub(spy_r, axis=0)
            ew = (1 + rets.mean(axis=1).fillna(0)).cumprod()
            bench = (1 + spy_r.fillna(0)).cumprod()
            rs = (ew / bench).replace([np.inf, -np.inf], np.nan)
        else:
            resid = rets
        out = _tc.basket_crowding(resid, rs, ext_rows=ext_rows)
        ext = out.get("extension") or {}
        pp = _num(ext.get("pct_parabolic"))
        return pp
    except Exception as e:  # noqa: BLE001
        log.debug("froth_fragility: cohort pct_parab failed (%s)", e)
        return None


def _backcompute_parab_history(closes: pd.DataFrame, spy: pd.Series | None) -> pd.Series:
    """Re-run the cohort parabolicity over a month-end grid (~3-5y) so the gauge has a
    self-referential scale on day one. Leak-free: each grid point uses only closes up to
    that date. Returns a date-indexed Series of pct_parab (0-100)."""
    try:
        grid = closes.resample("ME").last().index
        grid = grid[-60:]  # cap ~5y of month-ends
        pts: dict = {}
        for d in grid:
            sub = closes.loc[:d]
            if sub.dropna(how="all").shape[0] < _CFG["cohort_min_rows"]:
                continue
            # snap the month-end label back to the last ACTUAL trading date <= d so the
            # seeded history never holds a label later than its data (no future-dating)
            label = sub.index[-1]
            sub_spy = spy.loc[:d] if spy is not None else None
            pp = _cohort_pct_parab(sub, sub_spy)
            if pp is not None:
                pts[pd.Timestamp(label)] = pp
        return pd.Series(pts).sort_index()
    except Exception as e:  # noqa: BLE001
        log.debug("froth_fragility: backcompute parab history failed (%s)", e)
        return pd.Series(dtype=float)


def _parab_history(closes: pd.DataFrame, spy: pd.Series | None, asof: str | None,
                   today_val: float | None) -> pd.Series:
    """Load (or seed) the persisted parab history, append today's value idempotently,
    persist, and return the full series. Never raises."""
    p = _parab_path()
    hist = pd.Series(dtype=float)
    try:
        if p.exists():
            df = pd.read_parquet(p)
            col = "pct_parab" if "pct_parab" in df.columns else df.columns[0]
            hist = df[col].dropna()
            hist.index = pd.DatetimeIndex(hist.index)
    except Exception as e:  # noqa: BLE001
        log.debug("froth_fragility: parab history read failed (%s)", e)
        hist = pd.Series(dtype=float)
    if hist.shape[0] < _CFG["parab_min_history"]:
        seeded = _backcompute_parab_history(closes, spy)
        if not seeded.empty:
            hist = seeded.combine_first(hist).sort_index()
    if asof and today_val is not None:
        hist.loc[pd.Timestamp(asof)] = float(today_val)
        hist = hist[~hist.index.duplicated(keep="last")].sort_index()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        hist.rename("pct_parab").to_frame().to_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("froth_fragility: parab history write failed (%s)", e)
    return hist


def _face_a(latest: dict) -> dict:
    """Euphoria face. Returns {score, n_available, thin, legs:[...], low_naaim_flag}."""
    asof = _asof(latest)
    spy = _close_at("SPY", asof)
    closes = _closes_matrix(_live_members(PARAB_BASKETS), asof, _CFG["cohort_min_rows"])
    legs: list[dict] = []
    thin = False

    # A4 — semis/AI parabolicity (the only scorer)
    pp_today = _cohort_pct_parab(closes, spy)
    sub_a4 = None
    a4_val = None
    note = note_zh = None
    if pp_today is not None:
        a4_val = round(pp_today, 0)
        hist = _parab_history(closes, spy, asof, pp_today)
        vals = hist.dropna()
        if vals.shape[0] >= _CFG["parab_min_history"]:
            # rank TODAY's value (not the stored tail) against its own history — leak-free
            emp = float((vals.values <= float(pp_today)).mean())
        else:
            emp = _clip01(pp_today / 100.0)
            thin = True
        # M4 guard: a self-referential percentile on a near-quiet history over-reads a
        # modest absolute reading (10% of a cohort parabolic is NOT a blow-off). Blend the
        # percentile (context) with the ABSOLUTE breadth-of-parabolicity (the euphoria),
        # weighting the absolute term so ~35% of the cohort parabolic = full euphoria.
        absolute = _clip01(pp_today / 35.0)
        sub_a4 = _clip01(0.40 * emp + 0.60 * absolute)
    if sub_a4 is not None:
        if sub_a4 >= 0.80:
            note = f"semis/memory parabolic blow-off — {a4_val:.0f}% of the cohort parabolic"
            note_zh = f"半导体/存储抛物式狂热——{a4_val:.0f}% 成分股抛物化"
        elif sub_a4 >= 0.55:
            note = f"semis/AI extension elevated — {a4_val:.0f}% of the cohort parabolic"
            note_zh = f"半导体/AI 拉伸升高——{a4_val:.0f}% 成分股抛物化"
        else:
            note = f"{a4_val:.0f}% of the semis/AI cohort parabolic (euphoria cooled / cooling)"
            note_zh = f"{a4_val:.0f}% 半导体/AI 成分股抛物化（狂热已降温／正在降温）"
    legs.append(_leg("A4_parab", "Semis/AI parabolicity (blow-off breadth)", "半导体/AI 抛物广度",
                     a4_val, sub_a4, _w_a("A4_parab"), note, note_zh=note_zh,
                     pill=None if _SCORED_LEGS["A4_parab"] else "context", thin=thin))

    # ---- display-only euphoria legs (eff_w=0; render greyed) ----
    low_naaim = _naaim_low_flag()
    legs.append(_display_leg("A2_naaim", "Manager exposure (NAAIM) — context", "管理人仓位（NAAIM）",
                             ("low" if low_naaim else None),
                             "NAAIM low (capitulated) — bottom-tail context, NOT a euphoria score"
                             if low_naaim else "NAAIM mid/high — high exposure is trend-following, scored 0",
                             "NAAIM 偏低（已割肉）——底部尾部背景，并非欣喜评分"
                             if low_naaim else "NAAIM 中/高——高仓位属趋势跟随，计 0"))
    legs.append(_display_leg("A1_putcall", "Equity put/call froth", "股票看跌/看涨比",
                             *_putcall_display()))
    legs.append(_display_leg("A3_news", "News bull-ratio (cohort)", "新闻看多比例",
                             *_news_bull_display(closes)))
    legs.append(_display_leg("A5_rr", "Index put-skew (hedging bid) — context", "指数看跌偏度",
                             *_skew_display()))
    legs.append(_display_leg("A6_crypto", "Crypto Fear & Greed (cross-asset)", "加密恐惧贪婪",
                             *_crypto_fg_display()))

    score, n_avail = _renorm(legs, _CFG["weights_face_a"])
    return {"score": score, "n_available": n_avail, "thin": thin,
            "legs": legs, "low_naaim_flag": bool(low_naaim)}


def _naaim_low_flag() -> bool:
    try:
        df = pd.read_parquet(config.data_dir() / "sentiment" / "naaim.parquet")
        s = df[df.columns[0]].dropna()
        if s.shape[0] < 60:
            return False
        from engine.indicators import expanding_percentile
        p = expanding_percentile(s, min_obs=52).iloc[-1]
        return bool(p is not None and p == p and p < 0.10)
    except Exception:  # noqa: BLE001
        return False


def _putcall_display() -> tuple:
    try:
        df = pd.read_parquet(config.data_dir() / "cboe" / "putcall.parquet")
        # SESSION GUARD (#3721 class, review M2): putcall.parquet carries 13 non-session
        # rows of 39 — the SAME dates as cboe/gex.parquet. This is a 20-row ROLLING MEAN,
        # so ~6-7 of every 20 points averaged in were fabricated recomputes of a day with
        # no trading, EVERY day — not just a bad `.iloc[-1]`.
        df = nyse_calendar.session_rows(df, label="cboe/putcall")
        s = df["equity_pc_ratio"].dropna()
        if s.empty:
            return None, "accruing", "积累中"
        ma = s.rolling(min(20, len(s)), min_periods=1).mean()
        val = round(float(ma.iloc[-1]), 2)
        return val, f"equity put/call {val} (low = call-buying froth) · young series, scored 0", \
            f"股票看跌/看涨 {val}（低=看涨买盘狂热）· 数据尚短，计 0"
    except Exception:  # noqa: BLE001
        return None, "accruing", "积累中"


def _news_bull_display(closes: pd.DataFrame) -> tuple:
    try:
        df = pd.read_parquet(config.data_dir() / "polygon" / "news_sentiment.parquet")
        if closes is None or closes.empty:
            return None, "accruing", "积累中"
        latest_per = df.sort_values("snapshot_date").groupby("ticker").tail(1)
        sub = latest_per[latest_per["ticker"].isin(list(closes.columns))]
        if sub.empty:
            return None, "accruing", "积累中"
        br = round(float(sub["bull_ratio"].dropna().mean()), 2)
        return br, f"cohort news bull-ratio {br} · young series, scored 0", \
            f"成分新闻看多比 {br} · 数据尚短，计 0"
    except Exception:  # noqa: BLE001
        return None, "accruing", "积累中"


def _skew_display() -> tuple:
    try:
        df = pd.read_parquet(config.data_dir() / "options_skew" / "snapshots.parquet")
        # SESSION GUARD (#3721 class, OIP E8 2026-07-29): this store carried 8
        # non-session dates of 28, and a weekend row recomputes IV off a stale spot.
        # `date.max()` below would pick that Saturday as "the latest index put-skew".
        df = nyse_calendar.session_rows(df, "date", label="options_skew/snapshots")
        idx = df[df["underlying"].isin(["SPX", "SPY", "QQQ"])]
        if idx.empty:
            return None, "accruing", "积累中"
        latest_day = idx["date"].max()
        row = idx[idx["date"] == latest_day]
        sk = round(float(row["skew"].dropna().mean()), 3)
        return sk, f"index put-skew {sk} (put_iv − call_iv) · hedging-bid context, scored 0", \
            f"指数看跌偏度 {sk}（看跌IV − 看涨IV）· 对冲买盘背景，计 0"
    except Exception:  # noqa: BLE001
        return None, "accruing", "积累中"


def _crypto_fg_display() -> tuple:
    try:
        df = pd.read_parquet(config.data_dir() / "sentiment_crypto" / "fear_greed.parquet")
        v = int(df["fear_greed"].dropna().iloc[-1])
        tag = "extreme greed" if v >= 80 else ("greed" if v >= 60 else ("fear" if v <= 40 else "neutral"))
        tag_zh = {"extreme greed": "极度贪婪", "greed": "贪婪", "fear": "恐惧",
                  "neutral": "中性"}[tag]
        return v, f"crypto Fear&Greed {v} ({tag}) · cross-asset confirm, scored 0", \
            f"加密恐惧贪婪 {v}（{tag_zh}）· 跨资产确认，计 0"
    except Exception:  # noqa: BLE001
        return None, "accruing", "积累中"


# --------------------------------------------------------------------------- #
# FACE B — FRAGILITY / DISTRIBUTION
# --------------------------------------------------------------------------- #
def _breadth_frame(asof: str | None = None) -> pd.DataFrame | None:
    try:
        bf = pd.read_parquet(config.data_dir() / "breadth" / "breadth.parquet")
        bf.index = pd.DatetimeIndex(bf.index)
        bf = bf.sort_index()
        if asof:
            bf = bf.loc[:asof]
        return bf
    except Exception:  # noqa: BLE001
        return None


def _face_b(latest: dict, stealth: dict) -> dict:
    asof = _asof(latest)
    bf = _breadth_frame(asof)
    spy = _close_at("SPY", asof)
    legs: list[dict] = []

    # B-Stealth (dominant)
    s_sub = (stealth.get("score") / 100.0) if stealth.get("score") is not None else None
    legs.append(_leg("B_stealth", "Stealth distribution", "潜伏派发",
                     stealth.get("score"), s_sub, _w_b("B_stealth"),
                     stealth.get("headline_note"),
                     note_zh=stealth.get("headline_note_zh"), pill=None))

    # B1 — A/D line non-confirmation (persistence over t, t-1, t-2)
    sub_b1, b1_note, b1_zh = _b1_ad_divergence(bf, spy, asof)
    legs.append(_leg("B1_ad_div", "A/D line non-confirmation", "涨跌线未确认",
                     None, sub_b1, _w_b("B1_ad_div"), b1_note, note_zh=b1_zh, pill=None))

    # B2 — %>200dma divergence
    sub_b2, b2_note, b2_zh = _b2_pct200(bf, spy)
    legs.append(_leg("B2_pct200_div", "% > 200dma divergence", "200日均线上方占比背离",
                     None, sub_b2, _w_b("B2_pct200_div"), b2_note, note_zh=b2_zh, pill=None))

    # B-LeadDist — leadership distribution (generals retreating). The ORTHOGONAL half of
    # the leadership read: the magnitude of the median-leader-vs-index 52wk drawdown gap
    # (how much worse the generals are than the index). The "how many leaders are below
    # their 50dma" breadth lives in Stealth leg-3, so the two do NOT double-count.
    sub_ld, ld_note, ld_zh, ld_val = _b_leaddist(asof, spy)
    legs.append(_leg("B_leaddist", "Leadership distribution (generals retreating)", "龙头派发（将帅撤退）",
                     ld_val, sub_ld, _w_b("B_leaddist"), ld_note, note_zh=ld_zh, pill=None))

    # B4 — cross-asset absorption (concentration fragility)
    ar = _num(((latest or {}).get("cross_asset") or {}).get("absorption_pctile_5y"))
    sub_b4 = _clip01((ar - 0.60) / 0.20) if ar is not None else None
    b4_note = (f"cross-asset absorption {ar:.0%} of 5y — markets tightly coupled"
               if ar is not None else "absorption unavailable")
    b4_zh = (f"跨资产吸收比处于 5 年 {ar:.0%} 分位——市场高度耦合"
             if ar is not None else "吸收比不可用")
    legs.append(_leg("B4_absorption", "Cross-asset absorption", "跨资产吸收比",
                     (round(ar, 2) if ar is not None else None), sub_b4,
                     _w_b("B4_absorption"), b4_note, note_zh=b4_zh, pill=None))

    # ---- display-only Face-B chips (eff_w=0) ----
    legs.append(_display_leg("B3_med_dd", "Median-member drawdown vs index", "成分中位回撤 vs 指数",
                             *_b3_median_dd(asof, spy)))
    legs.append(_display_leg("B5_rsp_spy", "Equal-weight vs cap-weight (RSP/SPY) — context",
                             "等权 vs 市值权（RSP/SPY）", *_b5_rsp_spy(asof)))
    legs.append(_display_leg("B7_complacency", "Complacency (hidden fragility)", "自满（隐性脆弱）",
                             *_b7_complacency(latest)))

    # leaders distributing if EITHER the drawdown-gap leg is meaningful OR the breadth of
    # leaders below their 50dma (Stealth leg-3) has lit
    s3_lit = any(l.get("key") == "S3_leaders" and l.get("lit") for l in (stealth.get("legs") or []))
    score, n_avail = _renorm(legs, _CFG["weights_face_b"])
    return {"score": score, "n_available": n_avail, "legs": legs,
            "leaddist_sub": sub_ld,
            "leaders_dist": bool((sub_ld is not None and sub_ld >= 0.5) or s3_lit)}


def _b_leaddist(asof, spy) -> tuple:
    """Generals-retreating MAGNITUDE: how much worse the median mega-cap leader's 52wk
    drawdown is than the index, gated on the index being PINNED (a visible bear is not
    'hidden'). Continuous in the gap; ZERO when leaders are not worse than the index
    (gap<=0). Breadth-below-50dma is deliberately NOT scored here (it is Stealth leg-3) so
    the two leadership reads are orthogonal. Returns (sub01, note_en, note_zh, median_off)."""
    try:
        closes = _closes_matrix(_live_members(MEGACAP_BASKETS), asof, 120)
        if closes.empty or spy is None:
            return None, "leadership cohort unavailable", "龙头数据不可用", None
        n = closes.shape[1]
        ma50 = closes.rolling(50, min_periods=30).mean()
        n_below = int((closes.iloc[-1] < ma50.iloc[-1]).sum())
        roll = closes.rolling(252, min_periods=120).max()
        med_off = float((closes / roll - 1.0).iloc[-1].median())
        idx_off = float(spy.iloc[-1] / spy.rolling(252, min_periods=120).max().iloc[-1] - 1.0)
        prox60 = float(spy.iloc[-1] / spy.tail(60).max())
        gap = idx_off - med_off                       # positive => leaders worse than index
        if prox60 < 0.82:                             # index >18% off highs => visible, not hidden
            return None, f"index {prox60:.0%} of 60d high — distribution now visible, not hidden", \
                f"指数处于 60 日高点 {prox60:.0%}——派发已显性化", round(med_off, 3)
        # continuous ramp on the drawdown gap only: 3pp..20pp -> 0..1, zero below 3pp.
        sub = _clip01((gap - 0.03) / 0.17) if gap > 0 else 0.0
        note = (f"median mega-cap leader {med_off:.0%} off its 52wk-high vs index {idx_off:.0%} "
                f"({gap * 100:+.0f}pp gap; {n_below}/{n} below 50dma) — generals retreating under "
                f"a held index")
        note_zh = (f"龙头中位较 52 周高点回撤 {med_off:.0%}，指数仅 {idx_off:.0%}"
                   f"（差 {gap * 100:+.0f} 个百分点；{n_below}/{n} 跌破 50 日线）——将帅在被托住的指数下撤退")
        return sub, note, note_zh, round(med_off, 3)
    except Exception:  # noqa: BLE001
        return None, "leadership distribution unavailable", "龙头派发不可用", None


def _b1_ad_divergence(bf, spy, asof) -> tuple:
    try:
        from engine.advanced_breadth import divergence
        if bf is None or spy is None or "ad_line" not in bf.columns:
            return None, "breadth unavailable", "广度数据不可用"
        ad = bf["ad_line"]
        idx = ad.dropna().index.intersection(spy.dropna().index)
        if asof:
            idx = idx[idx <= pd.Timestamp(asof)]
        if len(idx) < 70:
            return None, "insufficient breadth history", "广度历史不足"
        lit = 0
        for k in range(3):
            end = idx[-1 - k]
            d = divergence(ad.loc[:end], spy.loc[:end])
            if d and d.get("state") == "bearish_div":
                lit += 1
        if lit >= 2:
            return 1.0, f"A/D line refuses to confirm new highs ({lit}/3 recent sessions diverging)", \
                f"涨跌线拒绝确认新高（近 {lit}/3 个交易日背离）"
        if lit == 1:
            return 0.6, "A/D line diverging today (not yet persistent)", "涨跌线今日背离（尚未持续）"
        return 0.0, "A/D line confirming the tape", "涨跌线确认行情"
    except Exception:  # noqa: BLE001
        return None, "A/D divergence unavailable", "涨跌线背离不可用"


def _b2_pct200(bf, spy) -> tuple:
    try:
        if bf is None or spy is None or "pct_above_200" not in bf.columns:
            return None, "breadth unavailable", "广度数据不可用"
        pa = bf["pct_above_200"].dropna()
        if pa.shape[0] < 130 or spy.dropna().shape[0] < 260:
            return None, "insufficient history", "历史不足"
        last = float(pa.iloc[-1])
        prox = float(spy.iloc[-1] / spy.rolling(252).max().iloc[-1])
        drop = float(pa.rolling(126).max().iloc[-1] - last)
        rising = bool(pa.diff(20).iloc[-1] > 0)
        # suppress only when broad AND rising
        if last > 70 and rising:
            return 0.0, f"{last:.0f}% > 200dma and rising — broad participation", \
                f"{last:.0f}% 高于 200 日线且上升——参与广泛"
        sub = 0.0
        if prox >= _CFG["gate_high_prox"] and last < 70:
            sub = _clip01((drop - 5) / 15.0)
        if 60 <= last <= 70 and drop >= 10 and prox >= 0.98:
            sub = max(sub, 0.40)
        note = (f"{last:.0f}% > 200dma, down {drop:.0f}pp from 6mo peak while index "
                f"{prox:.0%} of highs" if sub > 0 else f"{last:.0f}% > 200dma — no divergence")
        note_zh = (f"{last:.0f}% 高于 200 日线，较半年峰值降 {drop:.0f}pp，而指数处于高点 {prox:.0%}"
                   if sub > 0 else f"{last:.0f}% 高于 200 日线——无背离")
        return sub, note, note_zh
    except Exception:  # noqa: BLE001
        return None, "%>200dma unavailable", "200 日线占比不可用"


def _b3_median_dd(asof, spy) -> tuple:
    try:
        closes = _closes_matrix(_live_members(LEADER_BASKETS), asof, 260)
        if closes.empty or spy is None:
            return None, "leadership cohort unavailable", "龙头数据不可用"
        off = (closes / closes.rolling(252).max() - 1.0).iloc[-1]
        med = float(off.median())
        idx_off = float(spy.iloc[-1] / spy.rolling(252).max().iloc[-1] - 1.0)
        if med <= -0.15 and idx_off >= -0.03:
            return round(med, 3), (f"median leader {med:.0%} off its 52wk-high while the index is "
                                   f"only {idx_off:.0%} off — classic stealth distribution"), \
                (f"龙头中位较 52 周高点回撤 {med:.0%}，而指数仅 {idx_off:.0%}——典型潜伏派发")
        return round(med, 3), f"median leader {med:.0%} off 52wk-high (index {idx_off:.0%})", \
            f"龙头中位较 52 周高点回撤 {med:.0%}（指数 {idx_off:.0%}）"
    except Exception:  # noqa: BLE001
        return None, "median drawdown unavailable", "中位回撤不可用"


def _b5_rsp_spy(asof=None) -> tuple:
    try:
        rsp, spy = _close_at("RSP", asof), _close_at("SPY", asof)
        if rsp is None or spy is None:
            return None, "RSP/SPY unavailable", "RSP/SPY 不可用"
        ratio = (rsp / spy.reindex(rsp.index)).dropna()
        from engine.indicators import pct_rank_window
        p = pct_rank_window(ratio.rolling(252).mean(), 252 * 5).iloc[-1]
        narrow = bool(p is not None and p == p and p < 0.10)
        val = round(float(p), 2) if p == p else None
        if narrow:
            return val, "equal-weight deeply lagging cap-weight — narrow leadership (context, not a trigger)", \
                "等权远落后市值权——领导面收窄（背景，非触发信号）"
        return val, "breadth of leadership not at a narrow extreme", "领导面广度未达收窄极值"
    except Exception:  # noqa: BLE001
        return None, "RSP/SPY unavailable", "RSP/SPY 不可用"


def _b7_complacency(latest) -> tuple:
    c = ((latest or {}).get("conditions") or {}).get("complacency") or {}
    st = c.get("state")
    if not st:
        return None, "complacency unavailable", "自满数据不可用"
    div_en = " · breadth diverging" if c.get("breadth_div") else ""
    div_zh = " · 广度背离" if c.get("breadth_div") else ""
    return st, f"complacency: {st.replace('_', ' ')}{div_en} (display-only, never scored)", \
        f"自满：{st.replace('_', ' ')}{div_zh}（仅展示，从不评分）"


# --------------------------------------------------------------------------- #
# STEALTH DISTRIBUTION sub-score — the crown jewel
# --------------------------------------------------------------------------- #
def _stealth_distribution(latest: dict) -> dict:
    asof = _asof(latest)
    bf = _breadth_frame(asof)
    spy = _close_at("SPY", asof)
    comp = ((latest or {}).get("conditions") or {}).get("complacency") or {}
    legs: list[dict] = []
    breadth_ok = bool(bf is not None and spy is not None and "pct_above_50" in bf.columns)

    # ---- GATE (leg 1, tiered) ----
    prox = _num(comp.get("spy_high_prox"))
    if prox is None and spy is not None and spy.shape[0] >= 60:
        prox = float(spy.iloc[-1] / spy.tail(60).max())
    breadth_neg = False
    if bf is not None and "pct_above_50" in bf.columns:
        pa50 = bf["pct_above_50"].dropna()
        if pa50.shape[0] > 25:
            breadth_neg = bool(pa50.iloc[-1] < 45 and pa50.diff(20).iloc[-1] < 0)
    if prox is None:
        gate_state, gated = "unknown", False
    elif prox >= _CFG["gate_high_prox"]:
        gate_state, gated = "armed", True
    elif prox >= _CFG["rotation_prox"]:
        gate_state, gated = "rotation_in_progress", True
    elif breadth_neg:
        gate_state, gated = "disarmed_visible", False
    else:
        gate_state, gated = "rotation_in_progress", True

    # ---- shared cohort + correlation/dispersion reads ----
    rho_hat, rho_low, rho_falling, disp_rising, vix_decomp, sigma_bar = _rho_dispersion(asof, spy)

    # ---- Leg 2: breadth negative / diverging ----
    l2 = 0
    l2_note = "breadth confirming"
    if breadth_ok:
        pa50 = bf["pct_above_50"].dropna()
        breadth_roc_neg = pa50.shape[0] > 21 and pa50.diff(20).iloc[-1] < 0 and pa50.iloc[-1] < 58
        addiv = False
        try:
            from engine.advanced_breadth import divergence
            d = divergence(bf["ad_line"], spy)
            addiv = bool(d and d.get("state") == "bearish_div")
        except Exception:  # noqa: BLE001
            addiv = False
        if breadth_roc_neg or addiv:
            l2 = 1
            l2_note = "breadth rolling over while price holds (%>50dma falling / A-D diverging)"
    legs.append(_sleg("S2_breadth", "Breadth negative under a pinned tape", l2, l2_note,
                      available=breadth_ok))

    # ---- Leg 3: leaders rolling one-by-one (current leadership cohort) ----
    l3, l3_note, l3_ok = _stealth_leaders(asof, spy)
    legs.append(_sleg("S3_leaders", "Leaders rolling one-by-one", l3, l3_note, available=l3_ok))

    # ---- Leg 4: correlation down / dispersion up ----
    l4_ok = rho_hat is not None
    l4 = 1 if (l4_ok and rho_low and rho_falling and disp_rising) else 0
    l4_note = (f"single-stock correlation low & falling, dispersion rising (ρ̂≈{rho_hat:.2f})"
               if l4 else ("correlation/dispersion not in distribution regime" if l4_ok
                           else "correlation/dispersion unavailable"))
    legs.append(_sleg("S4_corr", "Correlation down / dispersion up", l4, l4_note, available=l4_ok))

    # ---- Leg 5: defensives bid ----
    l5, l5_note, l5_ok = _stealth_defensives(spy, asof)
    legs.append(_sleg("S5_defensives", "Defensives bid under the surface", l5, l5_note, available=l5_ok))

    # ---- Leg 6: VIX asleep (relative to internal dispersion) ----
    vix_pctile = _num(comp.get("vix_pctile"))
    if vix_pctile is None:
        vix_pctile = _vix_pctile_fallback(asof)
    l6_ok = vix_pctile is not None or rho_hat is not None
    n_lit_24 = sum(1 for x in (l2, l3, l4) if x)
    l6 = 1 if l6_ok and ((vix_pctile is not None and vix_pctile < 0.25) or (rho_low and disp_rising)) \
        and n_lit_24 >= 2 else 0
    l6_note = (f"VIX asleep (pctile {vix_pctile:.0%}) while internals deteriorate"
               if l6 and vix_pctile is not None
               else ("VIX not masking (or internals not yet lit)" if l6_ok else "VIX read unavailable"))
    legs.append(_sleg("S6_vix", "VIX asleep vs internal dispersion", l6, l6_note, available=l6_ok))

    # ---- combine over AVAILABLE legs only ----
    score, n_available = _renorm_stealth(legs)
    n_lit = sum(1 for lg in legs if lg.get("available") and lg.get("lit"))
    stealth_fire = bool(score is not None and score >= _CFG["stealth_fire_score"]
                        and n_lit >= _CFG["stealth_fire_minlit"] and gated)

    # ---- unwind escalation (muted until persistent) ----
    escalation = None
    if rho_hat is not None and _rho_flip_persistent(asof, spy) and _delta_ar_high(latest):
        escalation = "unwind_risk"

    headline_note = headline_note_zh = None
    if score is not None:
        if stealth_fire:
            headline_note = f"rotating decline under a pinned, VIX-asleep index ({n_lit}/{n_available} legs lit)"
            headline_note_zh = f"被托住、VIX 沉睡的指数下的轮动式下行（{n_lit}/{n_available} 腿点亮）"
        elif gate_state == "rotation_in_progress":
            headline_note = "early unwind — no longer pure stealth"
            headline_note_zh = "早期解构——已非纯潜伏"
        else:
            headline_note = f"{n_lit}/{n_available} stealth legs lit"
            headline_note_zh = f"{n_lit}/{n_available} 潜伏腿点亮"

    return {"score": score, "gated": gated, "gate_state": gate_state, "n_lit": n_lit,
            "n_available": n_available, "stealth_fire": stealth_fire, "escalation": escalation,
            "vix_decomp": vix_decomp, "headline_note": headline_note,
            "headline_note_zh": headline_note_zh, "legs": legs}


def _cohort_rho_series(asof, win: int = 42):
    """Solnik-style average-correlation proxy among the leadership cohort:
    ρ̂(t) = var(EW-cohort 42d return) / mean(var(member 42d return)). For an equal-weight
    book of N names with avg pairwise corr ρ this ≈ ρ + (1−ρ)/N — a believable [0,1] read,
    UNLIKE dividing the broad market's low variance by a high-vol cohort's (that conflates
    market diversification with intra-cohort dispersion). Computed on the MEGACAP cohort
    (the index-movers) so the √ρ VIX-masking read is index-relevant. Returns (rho_series,
    rets, ew_ret, mean_var_member). All None on shortfall."""
    closes = _closes_matrix(_live_members(MEGACAP_BASKETS), asof, 120)
    if closes.empty:
        return None, None, None, None
    rets = closes.pct_change(fill_method=None)
    ew_ret = rets.mean(axis=1)                       # equal-weight cohort return
    var_ew = ew_ret.rolling(win).var()
    mean_var_member = rets.rolling(win).var().mean(axis=1)
    rho = (var_ew / mean_var_member.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    rho = rho.clip(lower=0, upper=1.2).ewm(span=10, min_periods=10).mean().dropna()
    return rho, rets, ew_ret, mean_var_member


def _rho_dispersion(asof, spy):
    """Cohort correlation ρ̂ (42d realized, EWMA) + dispersion. Low-and-falling ρ̂ with
    rising dispersion = leaders offsetting each other ("taking turns"), which pins the
    cap-weighted index and VIX while every name is volatile. Returns (rho_hat, rho_low,
    rho_falling, disp_rising, decomp_str, sigma_bar)."""
    try:
        win = 42
        rho, rets, ew_ret, mean_var_member = _cohort_rho_series(asof, win)
        if rho is None or rho.shape[0] < 60:
            return None, False, False, False, None, None
        rho_hat = float(rho.iloc[-1])
        tertile = float(rho.tail(252).quantile(1 / 3))
        rho_low = bool(rho_hat <= tertile)
        rho_falling = bool(rho.iloc[-1] < rho.iloc[-6]) if rho.shape[0] > 6 else False
        # dispersion = cross-sectional std of members' 42d cumulative returns (a level);
        # only its DIRECTION (rising) is consumed, so no normalization is needed — and the
        # old divide-by-1d-EW-vol mixed a 42d cumulative std with a 1d std (a horizon/unit
        # mismatch), so it is removed.
        member_42 = rets.add(1).rolling(win).apply(np.prod, raw=True) - 1
        disp = member_42.std(axis=1).dropna()
        disp_rising = bool(disp.shape[0] > 6 and disp.iloc[-1] > disp.iloc[-6])
        # VIX-masking decomposition (annualized, leadership-index level)
        sigma_bar = float(np.sqrt(max(mean_var_member.iloc[-1], 0.0) * 252))
        est = math.sqrt(max(rho_hat, 0.0)) * sigma_bar
        decomp = (f"avg leader vol ≈{sigma_bar:.0%} × √{rho_hat:.2f} ⇒ leadership-index vol "
                  f"~{est:.0%} — the cap-weighted index (and VIX) stays calm because the leaders "
                  f"offset each other; it re-inflates violently if ρ snaps back toward 1. "
                  f"(Conditional fragility, not a dated top.)")
        return rho_hat, rho_low, rho_falling, disp_rising, decomp, sigma_bar
    except Exception:  # noqa: BLE001
        return None, False, False, False, None, None


def _stealth_leaders(asof, spy) -> tuple:
    """Leaders rolling one-by-one OR already broadly broken (saturation) under a PINNED
    index. Fires on a rising count of leaders below 50dma, or on saturation (>=70% below)
    — the end-state of the same process — while the index is still within ~6% of its
    60d high."""
    try:
        closes = _closes_matrix(_live_members(MEGACAP_BASKETS), asof, 60)
        if closes.empty or spy is None:
            return 0, "leadership cohort unavailable", False
        n = closes.shape[1]
        ma50 = closes.rolling(50, min_periods=30).mean()
        below = (closes < ma50)
        n_below = int(below.iloc[-1].sum())
        n_below_5d = int(below.iloc[-6].sum()) if below.shape[0] > 6 else n_below
        share = n_below / n
        rising = n_below > n_below_5d
        idx_pinned = bool(spy.shape[0] >= 60 and spy.iloc[-1] / spy.tail(60).max() >= _CFG["gate_high_prox"])
        if idx_pinned and share >= 0.5 and (rising or share >= 0.7):
            how = "and rising" if rising else "already broadly broken"
            return 1, (f"{n_below} of {n} leaders below their 50dma ({how}) while the index holds "
                       f"— generals retreating under a pinned tape"), True
        return 0, f"{n_below}/{n} leaders below 50dma (not a rolling top under a pinned index)", True
    except Exception:  # noqa: BLE001
        return 0, "leaders read unavailable", False


def _stealth_defensives(spy, asof) -> tuple:
    try:
        defs = [_close_at(t, asof) for t in DEFENSIVE_ETFS]
        offs = [_close_at(t, asof) for t in OFFENSE_ETFS]
        if any(s is None for s in defs + offs) or spy is None:
            return 0, "defensive/offense ETFs unavailable", False
        idx = None
        for s in defs + offs:
            idx = s.index if idx is None else idx.intersection(s.index)
        d = sum(s.reindex(idx) for s in defs)
        o = sum(s.reindex(idx) for s in offs)
        ratio = (d / o).dropna()
        roc = float(ratio.iloc[-1] / ratio.iloc[-22] - 1.0) if ratio.shape[0] > 22 else 0.0
        spy_roc = float(spy.iloc[-1] / spy.iloc[-21] - 1.0) if spy.shape[0] > 21 else 0.0
        rsp = _close_at("RSP", asof)
        rsp_roc = None
        if rsp is not None:
            r = (rsp / spy.reindex(rsp.index)).dropna()
            if r.shape[0] > 22:
                rsp_roc = float(r.iloc[-1] / r.iloc[-22] - 1.0)
        if roc > 0 and spy_roc >= 0 and (rsp_roc is None or rsp_roc < 0):
            return 1, "defensives (staples/utilities/health) bid while the index is flat/up", True
        return 0, "no defensive rotation under the surface", True
    except Exception:  # noqa: BLE001
        return 0, "defensive rotation unavailable", False


def _vix_pctile_fallback(asof) -> float | None:
    try:
        df = pd.read_parquet(config.data_dir() / "fred" / "VIXCLS.parquet")
        s = df["vix_close"].dropna()
        if asof:
            s = s.loc[:asof]
        if s.shape[0] < 252:
            return None
        return float((s.tail(252) <= s.iloc[-1]).mean())
    except Exception:  # noqa: BLE001
        return None


def _rho_flip_persistent(asof, spy) -> bool:
    """+1σ ρ̂ flip-up for >=2 consecutive readings (cry-wolf guard)."""
    try:
        rho, _, _, _ = _cohort_rho_series(asof, 42)
        if rho is None or rho.shape[0] < 60:
            return False
        chg = rho.diff()
        sd = chg.tail(120).std()
        if not sd or sd != sd:
            return False
        return bool((chg.iloc[-1] > sd) and (chg.iloc[-2] > sd))
    except Exception:  # noqa: BLE001
        return False


def _delta_ar_high(latest) -> bool:
    # corroborating absorption spike; absorption_pctile_5y high is the available proxy
    ar = _num(((latest or {}).get("cross_asset") or {}).get("absorption_pctile_5y"))
    return bool(ar is not None and ar >= 0.80)


# --------------------------------------------------------------------------- #
# Leg constructors + renormalization
# --------------------------------------------------------------------------- #
def _w_a(key):
    return float(_CFG["weights_face_a"].get(key, 0.0)) if _SCORED_LEGS.get(key) else 0.0


def _w_b(key):
    return float(_CFG["weights_face_b"].get(key, 0.0)) if _SCORED_LEGS.get(key) else 0.0


def _leg(key, label, label_zh, value, sub01, weight, note, note_zh=None, pill=None, thin=False) -> dict:
    available = sub01 is not None and weight > 0
    return {"key": key, "label": label, "label_zh": label_zh, "value": value,
            "sub": (round(float(sub01) * 100, 1) if sub01 is not None else None),
            "weight": round(float(weight), 3), "available": bool(available),
            "scored": bool(weight > 0), "points": None,
            "note": note, "note_zh": note_zh or note, "color": _color(sub01),
            "pill": pill, "thin": bool(thin)}


def _display_leg(key, label, label_zh, value, note, note_zh=None) -> dict:
    return {"key": key, "label": label, "label_zh": label_zh, "value": value,
            "sub": None, "weight": 0.0, "available": False, "scored": False,
            "points": None, "note": note, "note_zh": note_zh or note, "color": "#888",
            "pill": "accruing" if key.startswith(("A1", "A3", "A5", "A6", "A7")) else "context",
            "thin": False}


def _sleg(key, label, lit, note, available=True) -> dict:
    return {"key": key, "label": label, "lit": bool(lit), "available": bool(available),
            "weight": float(_CFG["weights_stealth"].get(key, 0.0)), "note": note,
            "color": ("#d04545" if lit else "#5a9bd4") if available else "#888"}


def _renorm(legs, weights) -> tuple:
    num = den = 0.0
    n = 0
    for lg in legs:
        if lg.get("available") and lg.get("sub") is not None:
            w = float(lg.get("weight", 0.0))
            if w <= 0:
                continue
            den += w
            num += w * (float(lg["sub"]) / 100.0)
            n += 1
    if den <= 0:
        return None, 0
    score = 100.0 * num / den
    for lg in legs:
        if lg.get("available") and lg.get("sub") is not None and float(lg.get("weight", 0)) > 0:
            lg["points"] = round(float(lg["weight"]) * (float(lg["sub"]) / 100.0) / den * 100.0, 1)
    return round(score, 1), n


def _renorm_stealth(legs) -> tuple:
    """Renormalize the stealth score over AVAILABLE legs only (an unavailable leg drops
    from both numerator and denominator, never counted as 'not lit'). Returns
    (score, n_available)."""
    num = den = 0.0
    n = 0
    for lg in legs:
        if not lg.get("available", True):
            continue
        w = float(lg.get("weight", 0.0))
        if w <= 0:
            continue
        den += w
        num += w * (1.0 if lg.get("lit") else 0.0)
        n += 1
    if den <= 0:
        return None, 0
    return round(100.0 * num / den, 1), n


# --------------------------------------------------------------------------- #
# Headline / quadrant
# --------------------------------------------------------------------------- #
def _headline_scalar(fa, fb, st) -> float | None:
    if fa is None and fb is None:
        return None
    if fa is None or fb is None:
        base = fb if fa is None else fa
    else:
        base = math.sqrt(max(fa, 0.0) * max(fb, 0.0))
    if st.get("stealth_fire") and st.get("gated"):
        base = max(base, fb or 0.0)
    return round(float(base), 1)


def _quadrant(fa, fb, st, leaders_dist=False) -> str:
    T = _CFG["quadrant_face_thresh"]
    gate = st.get("gated")
    fa0, fb0 = (fa or 0.0), (fb or 0.0)
    if fa is not None and fb is not None and fa >= T and fb >= T and gate:
        return "euphoric_fragile"
    if st.get("stealth_fire") and gate and fa0 >= _CFG["stealth_primed_face_a"]:
        return "stealth_primed"
    if not gate and fb0 >= T:
        return "distribution_in_progress"
    # generals distributing under a still-pinned index — the narrowing top — whether the
    # euphoria is still hot OR has already cooled off the blow-off (leaders down, soldiers
    # holding the index up). Independent of the Face-A level by design.
    if leaders_dist and gate:
        return "narrowing_top"
    if fa0 >= T and fb0 < T:
        return "euphoric_extended"
    if fa0 < T and fb0 >= T:
        return "visible_stress"
    return "benign"


# --------------------------------------------------------------------------- #
# THE snapshot
# --------------------------------------------------------------------------- #
_DISCLAIMER_EN = (
    "Display-only / validation-accruing — a FORWARD top-risk gauge fusing retail euphoria "
    "with hidden-distribution precursors, NOT an alpha signal. Edge is MODEST and LOUD+EARLY "
    "by design (weeks-to-months lead, real false positives ~30-45% at h21). It feeds no score "
    "and no allocation; the only sanctioned response is SIZING (de-risk), never selection. Each "
    "firing is logged and graded on forward QQQ/SMH drawdown + VIX jump.")
_DISCLAIMER_ZH = (
    "仅供展示／正在积累验证——融合零售欣喜与隐性派发前兆的「前瞻性顶部风险」计，并非选股信号。"
    "按设计偏早且响亮（提前数周至数月，h21 误报约 30-45%）。不计入任何评分或仓位；唯一被许可的"
    "回应是减仓（降低风险），绝非选股。每次触发都会记录并以未来 QQQ/SMH 回撤与 VIX 跳升评分。")


def snapshot(latest: dict | None) -> dict | None:
    """Compute the full Froth & Fragility gauge off `latest`. Returns the render dict
    (see schema below) or None on total failure / no data. NEVER raises."""
    try:
        if not isinstance(latest, dict) or not latest:
            return None
        asof = _asof(latest)
        stealth = _stealth_distribution(latest)
        face_a = _face_a(latest)
        face_b = _face_b(latest, stealth)

        fa, fb = face_a.get("score"), face_b.get("score")
        if fa is None and fb is None and stealth.get("score") is None:
            return None

        headline = _headline_scalar(fa, fb, stealth)
        leaders_dist = bool(face_b.get("leaders_dist"))
        quadrant = _quadrant(fa, fb, stealth, leaders_dist=leaders_dist)
        band, band_zh = _band(headline)
        # band/quadrant reconciliation: a benign quadrant can never show >elevated bar
        if quadrant == "benign" and band in ("high", "extreme"):
            band, band_zh = "elevated", _BAND_ZH["elevated"]
        # a narrowing-top (leaders distributing under a held index) is a real building
        # risk — floor the band at 'watch' so a healthy broad tape can't read fully calm
        if quadrant == "narrowing_top" and band == "calm":
            band, band_zh = "watch", _BAND_ZH["watch"]

        provisional = _is_provisional()
        quad_en, quad_zh = _QUAD_LABELS.get(quadrant, (quadrant, quadrant))

        return {
            "asof": asof,
            "headline": headline, "band": band, "band_zh": band_zh,
            "quadrant": quadrant, "quadrant_en": quad_en, "quadrant_zh": quad_zh,
            "face_a": face_a, "face_b": face_b, "stealth": stealth,
            "stealth_fire": stealth.get("stealth_fire"),
            "unwind_risk": bool(stealth.get("escalation") == "unwind_risk"),
            "low_naaim_flag": face_a.get("low_naaim_flag"),
            "alert": bool(band in ("elevated", "high", "extreme")
                          or quadrant in ("euphoric_fragile", "stealth_primed",
                                          "narrowing_top", "distribution_in_progress")),
            "provisional": provisional,
            "disclaimer": _DISCLAIMER_EN, "disclaimer_zh": _DISCLAIMER_ZH,
            "provisional_note": ("Face-B led; A4 / Stealth forward record still accruing — "
                                 "read the firing as early & uncertain, not validated."
                                 if provisional else None),
        }
    except Exception as e:  # noqa: BLE001 — degrade-never-raise
        log.warning("froth_fragility snapshot failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# Forward-outcome log (append / resolve / track_record) — mirrors vol_shock
# --------------------------------------------------------------------------- #
def _log_path() -> Path:
    return config.data_dir() / "froth_fragility" / "log.jsonl"


def _read_log(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def _write_log(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")


def _last(series_name: str) -> float | None:
    s = _close(series_name)
    return float(s.iloc[-1]) if s is not None and not s.empty else None


def append_log(snap: dict | None, latest: dict | None = None, path: str | Path | None = None) -> bool:
    """Append today's firing (realized fields filled later by resolve()). Idempotent per
    asof. Bakes anchors + pre-registered EN/ZH HIT labels. Never raises."""
    try:
        if not snap or not snap.get("asof") or snap.get("headline") is None:
            return False
        p = Path(path) if path else _log_path()
        rows = _read_log(p)
        d = snap.get("asof")
        if any(r.get("asof") == d for r in rows):
            return False
        vix = _num((((latest or {}).get("conditions") or {}).get("risk_appetite") or {}).get("vix"))
        if vix is None:
            vix = _vix_anchor(d)
        h = _CFG["horizons"]["h42"]
        # Pre-registered outcome = drawdown ANCHORED at the firing close (worse of QQQ/SMH)
        # over the horizon, OR a VIX jump. (Not claiming a "firing-led" peak-proximity check
        # — the grading in resolve() measures the anchored drawdown, and the label says so.)
        label_en = (f"QQQ or SMH drawdown ≤ −{_CFG['outcome_dd_pct']:.0f}% from the firing close OR "
                    f"VIX intraday-high ≥ {_CFG['outcome_vix_mult']:.2g}× within {h}d")
        label_zh = (f"{h} 日内 QQQ 或 SMH 自触发收盘回撤 ≤ −{_CFG['outcome_dd_pct']:.0f}%"
                    f"或 VIX 日内高点 ≥ {_CFG['outcome_vix_mult']:.2g} 倍")
        st = snap.get("stealth") or {}
        rows.append({
            "asof": d, "headline": snap.get("headline"), "band": snap.get("band"),
            "quadrant": snap.get("quadrant"),
            "face_a": (snap.get("face_a") or {}).get("score"),
            "face_b": (snap.get("face_b") or {}).get("score"),
            "stealth_score": st.get("score"), "stealth_gated": st.get("gated"),
            "stealth_fire": snap.get("stealth_fire"), "unwind_risk": snap.get("unwind_risk"),
            "alert": snap.get("alert"),
            "anchors": {"qqq_px": _last("QQQ"), "smh_px": _last("SMH"),
                        "spy_px": _last("SPY"), "vix": vix},
            "outcome_label_en": label_en, "outcome_label_zh": label_zh,
            "realized": {"h10": None, "h21": None, "h42": None},
            "hit_type": None, "hit": None, "graded": None,
        })
        _write_log(p, rows)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("froth_fragility append_log failed (%s)", e)
        return False


def _vix_anchor(asof: str | None = None) -> float | None:
    try:
        from lib import store
        vix = store.read("yahoo", "^VIX")
        if vix is not None and not vix.empty:
            s = vix["close"].dropna()
            if asof:
                s = s.loc[:asof]
            if not s.empty:
                return float(s.iloc[-1])
    except Exception:  # noqa: BLE001
        pass
    return None


def resolve(qqq_closes: dict, smh_closes: dict | None = None, vix_highs: dict | None = None,
            path: str | Path | None = None) -> int:
    """Grade matured rows from {iso_date: value} maps. HIT per the pre-registered label:
    worse of QQQ/SMH max-drawdown <= -outcome_dd_pct OR VIX intraday-high >= anchor*mult,
    over (t+1..t+h]. Grades only once h42 matures. Idempotent (graded None->dict). Returns
    # newly graded. Never raises."""
    try:
        p = Path(path) if path else _log_path()
        rows = _read_log(p)
        if not rows or not qqq_closes:
            return 0
        qc = qqq_closes
        sc = smh_closes or {}
        vh = vix_highs or {}
        dates = sorted(qc)
        h = _CFG["horizons"]
        dd_thr = _CFG["outcome_dd_pct"] / 100.0
        vix_mult = _CFG["outcome_vix_mult"]
        n = 0
        for r in rows:
            if r.get("graded") is not None or r.get("asof") not in qc:
                continue
            i = dates.index(r["asof"])
            if i + h["h42"] >= len(dates):
                continue  # not matured
            realized = {}
            worst_dd = 0.0
            for hk, hv in h.items():
                window = dates[i + 1: i + hv + 1]
                qref = qc.get(r["asof"])
                qdd = (min(qc[d] for d in window) / qref - 1.0) if qref and window else None
                sref = sc.get(r["asof"])
                sdd = (min(sc[d] for d in window if d in sc) / sref - 1.0) \
                    if sref and any(d in sc for d in window) else None
                dd = min([x for x in (qdd, sdd) if x is not None], default=None)
                realized[hk] = round(dd, 4) if dd is not None else None
                if dd is not None:
                    worst_dd = min(worst_dd, dd)
            vref = _num((r.get("anchors") or {}).get("vix"))
            vix_jump = None
            if vref and vh:
                window = dates[i + 1: i + h["h42"] + 1]
                hs = [vh[d] for d in window if d in vh]
                if hs:
                    vix_jump = max(hs) / vref
            hit_dd = worst_dd <= -dd_thr
            hit_vix = bool(vix_jump is not None and vix_jump >= vix_mult)
            r["realized"] = realized
            r["hit_type"] = "drawdown" if hit_dd else ("vix" if hit_vix else None)
            r["hit"] = bool(hit_dd or hit_vix)
            r["graded"] = {"worst_dd": round(worst_dd, 4),
                           "vix_jump": round(vix_jump, 2) if vix_jump else None}
            n += 1
        if n:
            _write_log(p, rows)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("froth_fragility resolve failed (%s)", e)
        return 0


def resolve_from_store(path: str | Path | None = None) -> int:
    """Convenience: load QQQ/SMH closes + VIX intraday highs from the store and grade any
    matured firings. Lets run.py accrue the forward log in one call. Never raises."""
    try:
        from lib import store
        qqq = store.read("yahoo", "QQQ")
        smh = store.read("yahoo", "SMH")
        vix = store.read("yahoo", "^VIX")
        if qqq is None or qqq.empty:
            return 0
        qc = {d.strftime("%Y-%m-%d"): float(c) for d, c in qqq["close"].dropna().items()}
        sc = ({d.strftime("%Y-%m-%d"): float(c) for d, c in smh["close"].dropna().items()}
              if smh is not None and not smh.empty else {})
        vh = ({d.strftime("%Y-%m-%d"): float(hgh) for d, hgh in vix["high"].dropna().items()}
              if vix is not None and not vix.empty and "high" in vix.columns else {})
        return resolve(qc, sc, vh, path=path)
    except Exception as e:  # noqa: BLE001
        log.warning("froth_fragility resolve_from_store failed (%s)", e)
        return 0


def track_record(path: str | Path | None = None) -> dict:
    """Summarize graded firings: n, hit-rate, by_band, by_quadrant, by_hit_type. Stealth
    and full-quadrant firings graded separately. Never raises."""
    try:
        p = Path(path) if path else _log_path()
        rows = [r for r in _read_log(p) if r.get("hit") is not None]
        prov = _is_provisional()
        if not rows:
            return {"n": 0, "hit_rate": None, "by_band": {}, "by_quadrant": {},
                    "by_hit_type": {}, "provisional": True}
        n = len(rows)
        hits = sum(1 for r in rows if r.get("hit"))

        def _by(field):
            d: dict = {}
            for r in rows:
                k = r.get(field) or "—"
                e = d.setdefault(k, {"n": 0, "hits": 0})
                e["n"] += 1
                e["hits"] += 1 if r.get("hit") else 0
            for k, e in d.items():
                e["hit_rate"] = round(e["hits"] / e["n"], 2) if e["n"] else None
            return d

        ht: dict = {}
        for r in rows:
            if r.get("hit"):
                ht[r.get("hit_type") or "—"] = ht.get(r.get("hit_type") or "—", 0) + 1
        return {"n": n, "hit_rate": round(hits / n, 2),
                "by_band": _by("band"), "by_quadrant": _by("quadrant"),
                "by_hit_type": ht, "provisional": bool(prov or n < _CFG["graduation_min_firings"])}
    except Exception as e:  # noqa: BLE001
        log.warning("froth_fragility track_record failed (%s)", e)
        return {"n": 0, "hit_rate": None, "by_band": {}, "by_quadrant": {},
                "by_hit_type": {}, "provisional": True}


def _is_provisional() -> bool:
    """Provisional until A4 history >= 252 rows AND >= graduation_min_firings graded."""
    try:
        rows = [r for r in _read_log(_log_path()) if r.get("hit") is not None]
        graded_ok = len(rows) >= _CFG["graduation_min_firings"]
        hist_ok = False
        p = _parab_path()
        if p.exists():
            hist_ok = pd.read_parquet(p).shape[0] >= 252
        return not (graded_ok and hist_ok)
    except Exception:  # noqa: BLE001
        return True
