"""Single-name implied-volatility SPREAD — the Cremers-Weinbaum (2010) deviation-from-
put-call-parity return predictor: when matched-strike CALLS are implied-richer than PUTS,
informed traders are leaning long in the options before the move shows up in the stock, and
the name has historically EARNED higher forward returns (≈ +51bps/wk, top-vs-bottom).

The measure (faithful to the paper):

    ivspread = OI-weighted mean over matched (call, put) pairs at the SAME strike & expiry of
               IV(call) − IV(put),   at the ~30-day tenor, near the money.

Under put-call parity a matched-strike call and put carry the SAME implied vol, so the spread
is centred near zero and a *positive* spread is a genuine informed-demand tilt (NOT the
structurally-negative level of the OTM-put [[options_skew]] — that one needs the change/sign;
this one is usable as a level). It is computed from the per-strike chain snapshots the GEX
desk already persists (data/polygon_gex/chains/<date>.parquet — K, T, iv, oi, volume, is_call,
spot, expiry), so it needs **no trade tape and no NBBO signing** — the parts of options FLOW
that are unaffordable/unreliable for us (see research/OPTIONS_FLOW_DATA.md). This is the one
DIRECTIONAL options signal we can build for $0.

HONEST STATE — DISPLAY-ONLY / NOT SCORED (mirrors options_skew). The chain store covers a
narrow universe over a handful of dates — far below the breadth/history a return-predictor
validation needs. So this builds the SIGNAL + a forward-accruing snapshot ledger + a dormant
validation gate (scripts/validate_options_ivspread.py); the gate stays closed — and the
confirmer stays display-only context — until the panel is wide and long enough to earn a
verdict. The `assess()` confirmer can AMPLIFY or CAUTION a long the price thesis already likes,
never manufacture a buy (the same doctrine as engine/gex_confirm). PURE compute; disk IO is
isolated in snapshot()/load_*.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "options_ivspread.v1"
_TARGET_DAYS = 30.0           # ~1-month tenor (matches the skew leg for comparability)
_MIN_DAYS = 7.0
_MNY_BAND = 0.08             # near-ATM only — where matched call/put IVs are most comparable
#                              (deep-ITM-call vendor IVs are unreliable and pollute the wings)
_MAX_PAIR_SPREAD = 0.50      # drop a matched pair whose |IV_call−IV_put| exceeds this — that is
#                              bad vendor data (e.g. a stale ITM print), not informed demand
_MIN_PAIRS = 3               # need a few matched strikes for a trustworthy weighted mean

# confirmer bands (decimal IV; 0.005 = half a vol point)
DEFAULTS = {
    "min_pairs": _MIN_PAIRS,
    "band": 0.005,            # |spread| past this = a real lean (confirm/caution)
    "band_strong": 0.015,     # |spread| past this = a strong lean
    "chg_band": 0.004,        # spread CHANGE past this = demand actively building
    "confirm_at": 1.0,        # net score >= this -> CONFIRM
    "caution_at": -1.0,       # net score <= this -> CAUTION
}

_LABEL = {
    "confirm": ("Options lean up", "期权偏多"),
    "neutral": ("Options neutral", "期权中性"),
    "caution": ("Options lean down", "期权偏空"),
}
_CAVEAT = ("Cremers-Weinbaum call−put IV spread (matched strikes, ~30d, OI-weighted). Calls "
           "richer than puts = informed bullish lean; puts richer = protection bid. A "
           "CROSS-SECTIONAL context read — dividends/borrow can bias the level, the feed is "
           "delayed EOD, and it is DISPLAY-ONLY until the forward-IC gate validates. It can "
           "amplify or caution a long the price thesis already likes, never create a buy.")
_CAVEAT_ZH = ("Cremers-Weinbaum 看涨−看跌隐含波动率价差（同行权价配对，约30天，按未平仓量加权）。"
              "看涨比看跌更贵 = 知情资金偏多；看跌更贵 = 买入保护。这是横截面参考读数 — 股息/借券"
              "成本会扰动水平，数据为延迟收盘，且在前瞻IC验证通过前仅作展示。它只能放大或警示"
              "价格逻辑本已看好的多头，绝不制造买入信号。")


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (v != v) else v   # NaN-safe


def _nearest_expiry(rows, target_days: float = _TARGET_DAYS, min_days: float = _MIN_DAYS):
    """The single expiry whose tenor is closest to `target_days` (≥ min_days). `rows` is one
    underlying's chain (column T in YEARS). Returns a filtered frame or None."""
    try:
        df = rows.copy()
        df["_days"] = df["T"].astype(float) * 365.0
        cand = df[df["_days"] >= min_days]
        if cand.empty:
            cand = df[df["_days"] > 0]        # all short-dated → take the longest LIVE expiry
        if cand.empty:
            return None
        target_exp = cand.loc[(cand["_days"] - target_days).abs().idxmin(), "expiry"]
        return df[df["expiry"] == target_exp]
    except Exception as e:  # noqa: BLE001
        log.debug("nearest expiry failed (%s)", e)
        return None


def _matched_pairs(leg, spot: float):
    """Matched call/put rows at the same strike within the moneyness band, one row per strike.
    Returns a DataFrame indexed by K with [iv_c, iv_p, spread, oi_w, vol_w] or None."""
    import pandas as pd
    try:
        df = leg.copy()
        df["iv"] = pd.to_numeric(df["iv"], errors="coerce")
        df["K"] = pd.to_numeric(df["K"], errors="coerce")
        df["_is_call"] = df["is_call"].astype(bool)
        df["_oi"] = (pd.to_numeric(df["oi"], errors="coerce").fillna(0.0)
                     if "oi" in df.columns else 0.0)
        df["_vol"] = (pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
                      if "volume" in df.columns else 0.0)
        df = df[(df["iv"] > 0.0) & df["K"].notna()]
        if spot > 0:
            df = df[(df["K"] / spot - 1.0).abs() <= _MNY_BAND]
        if df.empty:
            return None
        calls = (df[df["_is_call"]].groupby("K")
                 .agg(iv_c=("iv", "mean"), oi_c=("_oi", "sum"), vol_c=("_vol", "sum")))
        puts = (df[~df["_is_call"]].groupby("K")
                .agg(iv_p=("iv", "mean"), oi_p=("_oi", "sum"), vol_p=("_vol", "sum")))
        m = calls.join(puts, how="inner")
        if m.empty:
            return None
        m["spread"] = m["iv_c"] - m["iv_p"]
        m = m[m["spread"].abs() <= _MAX_PAIR_SPREAD]    # drop bad-data pairs (stale ITM IVs)
        if m.empty:
            return None
        m["oi_w"] = m["oi_c"] + m["oi_p"]
        m["vol_w"] = m["vol_c"] + m["vol_p"]
        return m
    except Exception as e:  # noqa: BLE001
        log.debug("matched pairs failed (%s)", e)
        return None


def compute_ivspread(rows) -> dict | None:
    """Cremers-Weinbaum IV spread for one underlying's chain frame. PURE.
    Returns {underlying, asof, spot, tenor_days, ivspread, atm_spread, n_pairs, weight}."""
    try:
        if rows is None or getattr(rows, "empty", True):
            return None
        leg = _nearest_expiry(rows)
        if leg is None or leg.empty:
            return None
        spot = float(leg["spot"].iloc[0])
        m = _matched_pairs(leg, spot)
        if m is None or len(m) < 1:
            return None
        w = m["oi_w"]
        weight_kind = "oi"
        if float(w.sum()) <= 0:
            w, weight_kind = m["vol_w"], "volume"
        if float(w.sum()) <= 0:
            import pandas as pd
            w, weight_kind = pd.Series(1.0, index=m.index), "equal"
        ivspread = float((m["spread"] * w).sum() / w.sum())
        atm_k = (m.index.to_series() - spot).abs().idxmin()
        atm_spread = float(m.loc[atm_k, "spread"])
        tenor = float(leg["T"].astype(float).iloc[0] * 365.0)
        asof = leg["asof"].iloc[0]
        asof = str(asof.date()) if hasattr(asof, "date") else str(asof)[:10]
        return {
            "underlying": str(leg["underlying"].iloc[0]).upper(),
            "asof": asof, "spot": round(spot, 4),
            "tenor_days": round(tenor, 1),
            "ivspread": round(ivspread, 5),
            "atm_spread": round(atm_spread, 5),
            "n_pairs": int(len(m)),
            "weight_kind": weight_kind,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("compute_ivspread failed (%s)", e)
        return None


def relativize(names: dict[str, dict]) -> dict[str, dict]:
    """Attach ``ivspread_rel`` = each name's spread MINUS the cross-sectional median of the
    panel. Faithful to CW (the signal is cross-sectional rank, not the absolute level) AND it
    cancels the systematic same-strike call/put-IV offset our vendor IVs carry from dividends /
    American early-exercise — so a name's RELATIVE lean vs peers is the honest read. Mutates in
    place and returns the map. No-op (rel == raw) when fewer than 5 names. PURE."""
    try:
        vals = [m["ivspread"] for m in names.values() if m.get("ivspread") is not None]
        if len(vals) < 5:
            for m in names.values():
                m["ivspread_rel"] = m.get("ivspread")
            return names
        import statistics
        med = statistics.median(vals)
        for m in names.values():
            sp = m.get("ivspread")
            m["ivspread_rel"] = (round(sp - med, 5) if sp is not None else None)
        return names
    except Exception as e:  # noqa: BLE001
        log.debug("relativize failed (%s)", e)
        return names


def ivspread_map(chain, relative: bool = True) -> dict[str, dict]:
    """{underlying: ivspread metrics} over a full chain snapshot (many underlyings). When
    ``relative`` (default), also attaches the cross-sectionally de-meaned ``ivspread_rel`` the
    confirmer scores on. PURE."""
    out: dict[str, dict] = {}
    try:
        if chain is None or getattr(chain, "empty", True) or "underlying" not in chain.columns:
            return out
        for u, g in chain.groupby("underlying"):
            m = compute_ivspread(g)
            if m is not None:
                out[str(u).upper()] = m
    except Exception as e:  # noqa: BLE001
        log.debug("ivspread_map failed (%s)", e)
    return relativize(out) if relative else out


# --------------------------------------------------------------------------- #
# The confirmer — amplify / caution a long the price thesis already likes (never a name pick)
# --------------------------------------------------------------------------- #
def assess(ivs: dict | None, *, direction: str = "up",
           chg: float | None = None, cfg: dict | None = None) -> dict | None:
    """Return the IV-spread confirmer block for a LONG entry, or None when pairs are too thin.

    ``ivs``       — a compute_ivspread() dict (or None).
    ``direction`` — the stock's own price thesis ('up' for the standard long confirmer; 'down'
                    caps the verdict so options can never *confirm* a long on a falling name).
    ``chg``       — recent change in the spread vs the prior snapshot (decimal IV), or None.
    """
    cf = {**DEFAULTS, **(cfg or {})}
    if not ivs:
        return None
    n = ivs.get("n_pairs")
    if n is not None and n < cf["min_pairs"]:
        return None
    raw = _f(ivs.get("ivspread"))
    rel = _f(ivs.get("ivspread_rel"))
    sp = rel if rel is not None else raw      # score on the cross-sectional read when present
    if sp is None:
        return None
    pe, pz = ((" vs peers", "（相对同业）") if (rel is not None and "ivspread_rel" in ivs)
              else ("", ""))

    score = 0.0
    reasons: list[dict] = []

    def add(pts: float, en: str, zh: str, tone: str) -> None:
        nonlocal score
        score += pts
        reasons.append({"en": en, "zh": zh, "tone": tone})

    vp = sp * 100.0   # vol points, for human-readable reasons
    # ---- 1. spread LEVEL (matched-strike deviation from put-call parity) ----
    if sp >= cf["band_strong"]:
        add(1.0, f"calls richer than puts by {vp:+.1f} vol pts{pe} — strong informed bullish lean",
            f"看涨比看跌贵 {vp:+.1f} 个波动点{pz} — 知情资金强烈偏多", "confirm")
    elif sp >= cf["band"]:
        add(0.5, f"calls modestly richer than puts ({vp:+.1f} vol pts{pe}) — mild bullish lean",
            f"看涨略贵于看跌（{vp:+.1f} 个波动点{pz}）— 温和偏多", "confirm")
    elif sp <= -cf["band_strong"]:
        add(-1.0, f"puts richer than calls by {vp:+.1f} vol pts{pe} — protection strongly bid",
            f"看跌比看涨贵 {vp:+.1f} 个波动点{pz} — 保护性看跌被大力买入", "caution")
    elif sp <= -cf["band"]:
        add(-0.5, f"puts modestly richer than calls ({vp:+.1f} vol pts{pe}) — mild downside hedge",
            f"看跌略贵于看涨（{vp:+.1f} 个波动点{pz}）— 温和下行对冲", "caution")

    # ---- 2. spread CHANGE (call demand actively building / fading) ----------
    if chg is not None:
        if chg >= cf["chg_band"]:
            add(0.5, "call-over-put richness building vs the prior session — demand rotating up",
                "看涨相对看跌的溢价较上期上升 — 需求转向上行", "confirm")
        elif chg <= -cf["chg_band"]:
            add(-0.5, "call-over-put richness fading vs the prior session — bid rotating to puts",
                "看涨相对看跌的溢价较上期下降 — 买盘转向看跌", "caution")

    # ---- direction guard: a long confirmer can't be positive on a falling name
    if direction == "down" and score > 0:
        score = 0.0

    verdict = ("confirm" if score >= cf["confirm_at"]
               else "caution" if score <= cf["caution_at"] else "neutral")
    en, zh = _LABEL[verdict]
    return {
        "verdict": verdict, "score": round(score, 2),
        "label": en, "label_zh": zh,
        "reasons": reasons[:3],
        "ivspread": (round(raw, 5) if raw is not None else None),
        "ivspread_rel": (round(rel, 5) if rel is not None else None),
        "atm_spread": _f(ivs.get("atm_spread")),
        "n_pairs": n, "tenor_days": _f(ivs.get("tenor_days")),
        "chg": (round(chg, 5) if chg is not None else None),
        "caveat": _CAVEAT, "caveat_zh": _CAVEAT_ZH,
    }


# --------------------------------------------------------------------------- #
# Disk: forward-accruing snapshot ledger (the apparatus that earns a verdict over time)
# --------------------------------------------------------------------------- #
def _snap_path():
    p = config.data_dir() / "options_ivspread"
    p.mkdir(parents=True, exist_ok=True)
    return p / "snapshots.parquet"


def _latest_chain():
    import glob
    import pandas as pd
    files = sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "chains" / "*.parquet")))
    return pd.read_parquet(files[-1]) if files else None


def snapshot(today: date | None = None, chain=None) -> int:
    """Append today's per-underlying ivspread to the ledger (idempotent by (date, underlying)).
    Returns the number of rows added. This is what accrues the history a validation needs."""
    import pandas as pd
    today = today or date.today()
    if chain is None:
        chain = _latest_chain()
    if chain is None:
        return 0
    # key each row by the chain's OWN as-of date, not wall-clock `today` — a stale chain must
    # not be recorded under today's date (that would duplicate content across two date keys and
    # corrupt any forward-IC computed off the ledger).
    rows = [{"date": (m.get("asof") or today.isoformat()), **m}
            for m in ivspread_map(chain).values()]
    if not rows:
        return 0
    fresh = pd.DataFrame(rows)
    p = _snap_path()
    if p.exists():
        prev = pd.read_parquet(p)
        key = set(zip(prev["date"], prev["underlying"]))
        fresh = fresh[~fresh.apply(lambda r: (r["date"], r["underlying"]) in key, axis=1)]
        if fresh.empty:
            return 0
        combined = pd.concat([prev, fresh], ignore_index=True)
    else:
        combined = fresh
    combined.to_parquet(p)
    return int(len(fresh))


def load_history():
    import pandas as pd
    p = _snap_path()
    return pd.read_parquet(p) if p.exists() else None


def prior_spread_map() -> dict[str, float]:
    """{UPPER underlying: most-recent PRIOR ledger ivspread}. Loaded ONCE so a caller enriching
    many names can read 'call demand building' (current − prior) without re-reading the ledger
    per name. Empty {} when the ledger is absent."""
    try:
        led = load_history()
        if led is None or led.empty:
            return {}
        last = (led.sort_values("date")
                .groupby(led["underlying"].astype(str).str.upper())["ivspread"].last())
        return {str(k): float(v) for k, v in last.items()}
    except Exception:  # noqa: BLE001
        return {}


def load_gate() -> dict | None:
    """The validation verdict (scripts/validate_options_ivspread.py). None → 'measuring'."""
    try:
        import json
        p = config.data_dir() / "options_ivspread" / "validation_gate.json"
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def build_snapshot(today: date | None = None) -> dict:
    """Display payload: latest ivspread per name + the (likely-dormant) gate. CONTEXT-ONLY."""
    today = today or date.today()
    chain = _latest_chain()
    names = ivspread_map(chain) if chain is not None else {}
    gate = load_gate() or {}
    ranked = sorted(names.values(),
                    key=lambda m: (m.get("ivspread_rel") if m.get("ivspread_rel") is not None
                                   else m.get("ivspread") or 0.0), reverse=True)
    return {
        "schema": SCHEMA, "is_context_only": True,
        "scored": bool(gate.get("scored")),
        "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "names": names, "ranked": ranked, "n": len(names),
        "gate_status": gate.get("status", "measuring"),
        "disclaimer": ("Single-name Cremers-Weinbaum IV spread (call−put IV at matched strikes, "
                       "~30d, OI-weighted). DISPLAY-ONLY context: the chain panel is too "
                       "narrow/short to validate as a return predictor — accruing toward a "
                       "verdict. Directional but never a stand-alone buy."),
    }
