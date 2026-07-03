"""China Narrative Basket Radar — build_radar() -> dict.

Answers: "which THS narrative basket is running, is its global driver intact,
and which members have clean entries?"

DATA SOURCES
  · data/baskets_china_ths/membership.json  — 50-ish THS concept baskets
  · data/china_search/closes.parquet        — daily closes ~1492 tickers
  · data/yahoo/{SMH,SOXX,TSM}.parquet       — global AI-semis weekly closes
  · engine.china_sector_pathway._position() — washout↔euphoria state (leak-free)
  · engine.cn_ai_semis_confirmer            — validated global-AI signal

HONESTY CONSTRAINTS (cite §754, §773 in output)
  · Narrative momentum (rank_63d) is a descriptive positioning lens.
    Backtest (#754, #773): one-regime momentum; NOT validated alpha; NOT a buy list.
  · global_ai confirmer is a validated WEEKLY DIRECTIONAL confirmer (#773, t=3.27 cpo).
    Per-basket honesty tag:
      ths_cpo:         validated  (t=3.27, pre-2024 split survives)
      ths_pcb:         partial    (survives full, weaker pre-2024)
      ths_storage_chip: 2024+-only (statistically strong, but only post-2024)
      ths_adv_pkg:     2024+-only
      ths_ai:          weak
      ths_liquid_cool: weak
      ths_aidc:        weak
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ─── Global-AI confirmer honesty tags per basket ─────────────────────────────
_GLOBAL_AI_HONESTY: dict[str, str] = {
    "ths_cpo":          "validated",     # t=3.27, pre-2024 survives, horse-race stable (#773)
    "ths_pcb":          "partial",       # survives full sample, weaker pre-2024 split
    "ths_storage_chip": "2024+-only",    # statistically strong but only post-2024
    "ths_adv_pkg":      "2024+-only",    # same
    "ths_ai":           "weak",          # mapped but marginal
    "ths_liquid_cool":  "weak",
    "ths_aidc":         "weak",
}

# Baskets where global_ai is emitted at all
_AI_MAPPED = frozenset(_GLOBAL_AI_HONESTY.keys())

# Minimum active members to include a basket
_MIN_MEMBERS = 3

# Rolling windows (trading days)
_W_63  = 63    # ~3 months momentum
_W_200 = 200   # trend gate (200d SMA)

# Top-N members by 63d return emitted per basket
_TOP_N_MEMBERS = 8


def _read_closes() -> pd.DataFrame:
    """Load china_search closes (daily, all tickers)."""
    p = config.ROOT / "data" / "china_search" / "closes.parquet"
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def _ew_level(closes: pd.DataFrame, tickers: list[str]) -> pd.Series:
    """Equal-weight level from a ticker list; cumprod of mean daily pct-change."""
    cols = [t for t in tickers if t in closes.columns]
    if len(cols) < _MIN_MEMBERS:
        return pd.Series(dtype=float)
    rets = closes[cols].pct_change(fill_method=None).mean(axis=1, skipna=True)
    return (1 + rets.fillna(0)).cumprod()


def _basket_members(basket_val: dict | list) -> list[dict]:
    """Extract member list from a basket entry (dict or legacy list)."""
    if isinstance(basket_val, list):
        rows = basket_val
    else:
        rows = basket_val.get("members") or basket_val.get("tickers") or []
    # Filter out removed members
    out = []
    for r in rows:
        if isinstance(r, dict):
            if r.get("removed") is None:
                out.append(r)
        else:
            out.append({"ticker": str(r), "name_zh": str(r), "added": None, "removed": None})
    return out


def _position(price_series: pd.Series) -> dict:
    """Washout(0)↔euphoria(100) — verbatim from engine.china_sector_pathway._position().

    Imported function used instead of re-implementation to keep the math identical.
    Falls back to local implementation if import fails.
    """
    try:
        from engine.china_sector_pathway import _position as _sp_pos
        return _sp_pos(price_series)
    except Exception:  # noqa: BLE001
        pass
    # Local fallback (identical math)
    s = price_series.dropna()
    dist = (s / s.rolling(200).mean() - 1.0).dropna()
    dd   = (s / s.rolling(252).max() - 1.0).dropna()
    legs = []
    for x in (dist, dd):
        if len(x) >= 60:
            legs.append(float((x.iloc[-1260:] <= x.iloc[-1]).mean()))
    score = round(float(np.mean(legs) * 100), 0) if legs else None
    label_en = label_zh = "—"
    if score is not None:
        bands = [(15, "Beaten down", "深度超跌"), (35, "Recovering", "修复回升"),
                 (65, "Mid-cycle", "周期中段"), (85, "Stretched", "走高偏贵"), (101, "Overheated", "过热")]
        for hi, en, zh in bands:
            if score <= hi:
                label_en, label_zh = en, zh
                break
    return {
        "score": score, "label": label_en, "label_zh": label_zh,
        "dist_200d_pct": round(float(dist.iloc[-1] * 100), 1) if not dist.empty else None,
        "drawdown_pct":  round(float(dd.iloc[-1] * 100), 1)   if not dd.empty  else None,
    }


def _compute_global_ai() -> dict:
    """Compute global AI-semis confirmer chip (reuses existing engine)."""
    try:
        from engine.cn_ai_semis_confirmer import compute as _semis_compute
        return _semis_compute()
    except Exception as e:  # noqa: BLE001
        log.warning("china_narrative_radar: AI-semis confirmer failed: %s", e)
        return {"on": None, "state": "unavailable", "semis_mom_4w": None, "as_of": None}


def build_radar() -> dict:
    """Build the narrative basket radar.

    Returns a JSON-safe dict:
    {
      as_of: str,
      baskets: [ ... ],
      provenance: { momentum: str, global_ai: str }
    }

    Each basket entry:
    {
      id:           str,
      name:         str,       # English display name
      name_zh:      str,
      category:     str,
      category_zh:  str,
      ret_63d:      float | None,
      rank_63d:     int,        # 1 = best (lower is better momentum)
      above_200d:   bool | None,
      state:        { score, label, label_zh, dist_200d_pct, drawdown_pct },
      global_ai:    { mom_4w_pct, direction, validated_tag } | None,
      top_members:  [ { ticker, name_zh, ret_63d } ]
    }
    """
    # ── 1. Load closes ────────────────────────────────────────────────────────
    closes = _read_closes()
    as_of  = str(closes.index[-1].date())

    # ── 2. Load THS membership ────────────────────────────────────────────────
    mem_path = config.ROOT / "data" / "baskets_china_ths" / "membership.json"
    membership_raw = json.loads(mem_path.read_text())
    raw_baskets: dict = membership_raw["baskets"]

    # ── 3. Global AI-semis confirmer (one chip, reused per AI-mapped basket) ─
    ai_chip = _compute_global_ai()
    semis_mom_4w_pct = (
        round(ai_chip["semis_mom_4w"] * 100, 2)
        if ai_chip.get("semis_mom_4w") is not None else None
    )
    ai_direction = (
        "up"   if ai_chip.get("on") is True  else
        "down" if ai_chip.get("on") is False else
        "flat"
    )

    # ── 4. Per-ticker 63d returns (for member ranking) ────────────────────────
    if len(closes) >= _W_63 + 1:
        ticker_ret63: pd.Series = closes.pct_change(_W_63, fill_method=None).iloc[-1]
    else:
        ticker_ret63 = pd.Series(dtype=float)

    # ── 5. Build per-basket records ───────────────────────────────────────────
    records: list[dict] = []
    for bid, bval in raw_baskets.items():
        if not isinstance(bval, (dict, list)):
            continue

        # Meta
        if isinstance(bval, dict):
            name    = bval.get("name", bid)
            name_zh = bval.get("name_zh", bid)
            cat     = bval.get("category", "")
            cat_zh  = bval.get("category_zh", "")
        else:
            name = name_zh = bid
            cat = cat_zh = ""

        members = _basket_members(bval)
        tickers = [m["ticker"] for m in members]

        # Build EW level
        level = _ew_level(closes, tickers)
        if level.empty:
            continue   # fewer than 3 members with price data — skip

        # 63d return
        ret_63d: float | None = None
        if len(level) >= _W_63 + 1:
            ret_63d = round(float(level.iloc[-1] / level.iloc[-(_W_63 + 1)] - 1) * 100, 2)

        # 200d gate
        above_200d: bool | None = None
        if len(level) >= _W_200:
            sma200     = float(level.rolling(_W_200).mean().iloc[-1])
            above_200d = bool(level.iloc[-1] > sma200)

        # Cycle position (washout↔euphoria)
        state = _position(level)

        # Global AI chip (AI-mapped baskets only)
        global_ai: dict | None = None
        if bid in _AI_MAPPED:
            honesty = _GLOBAL_AI_HONESTY[bid]
            global_ai = {
                "mom_4w_pct":    semis_mom_4w_pct,
                "direction":     ai_direction,
                "validated_tag": honesty,
                "as_of":         ai_chip.get("as_of"),
            }

        # Top-N members by 63d return
        member_rets: list[dict] = []
        for m in members:
            t  = m["ticker"]
            nz = m.get("name_zh", t)
            r  = (float(ticker_ret63[t]) * 100) if t in ticker_ret63.index and not pd.isna(ticker_ret63[t]) else None
            member_rets.append({"ticker": t, "name_zh": nz, "ret_63d": (round(r, 2) if r is not None else None)})

        # Sort by ret_63d descending (None last)
        member_rets.sort(key=lambda x: x["ret_63d"] if x["ret_63d"] is not None else -999, reverse=True)
        top_members = member_rets[:_TOP_N_MEMBERS]

        records.append({
            "id":          bid,
            "name":        name,
            "name_zh":     name_zh,
            "category":    cat,
            "category_zh": cat_zh,
            "ret_63d":     ret_63d,
            "above_200d":  above_200d,
            "state":       state,
            "global_ai":   global_ai,
            "top_members": top_members,
        })

    if not records:
        log.warning("china_narrative_radar: no baskets computed — check data paths")
        return {"as_of": as_of, "baskets": [], "provenance": _provenance()}

    # ── 6. Rank by ret_63d (ascending rank = better momentum) ─────────────────
    # Sort: None last, then highest ret_63d = rank 1
    ranked = sorted(
        records,
        key=lambda r: r["ret_63d"] if r["ret_63d"] is not None else -1e9,
        reverse=True,
    )
    for i, r in enumerate(ranked):
        r["rank_63d"] = i + 1

    log.info("china_narrative_radar: %d baskets built, as_of=%s", len(ranked), as_of)
    return {
        "as_of":      as_of,
        "baskets":    ranked,
        "provenance": _provenance(),
    }


def _provenance() -> dict:
    return {
        "momentum": (
            "descriptive positioning lens — one-regime in backtest (#754/#773), "
            "NOT validated alpha"
        ),
        "global_ai": (
            "validated weekly directional confirmer for CPO basket (#773, t=3.27 "
            "cpo; pre-2024 split survives; other AI-supply baskets: partial/2024+-only/weak "
            "— honesty tags per basket)"
        ),
    }
