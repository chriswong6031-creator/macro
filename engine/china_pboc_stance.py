"""PBoC policy-stance classifier — the China sibling of engine/fed_stance.py.

LEAF · DISPLAY/CONTEXT-ONLY · KEYLESS. Reads the rate corridor already on disk — LPR
1Y/5Y + RRR (china_macro), money-market FR007 + SHIBOR (china_pboc/china_macro), FX
reserves + USD/CNY (china_pboc) — and reduces it to a transparent, deterministic
easing / on-hold / tightening read with a bilingual rationale and the recent move log.
Nothing here feeds a score; it powers the China Policy Watch corridor panel + the
machine-readable latest.json the intel bus reads. Never raises.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import store

log = logging.getLogger(__name__)

SCHEMA = "china_pboc_stance.v1"


def _last(group: str, name: str, col: str):
    try:
        df = store.read(group, name)
        if df is None or df.empty or col not in df.columns:
            return None, None
        s = df[col].dropna()
        if s.empty:
            return None, None
        return float(s.iloc[-1]), s.index.max().date()
    except Exception:  # noqa: BLE001
        return None, None


def _change_over(group: str, name: str, col: str, periods: int):
    """latest minus the value `periods` observations ago (None if insufficient)."""
    try:
        df = store.read(group, name)
        if df is None or col not in df.columns:
            return None
        s = df[col].dropna()
        if len(s) <= periods:
            return None
        return float(s.iloc[-1] - s.iloc[-1 - periods])
    except Exception:  # noqa: BLE001
        return None


def _chg_trailing_days(group: str, name: str, col: str, days: int):
    """latest minus the value as-of (latest_date - days). Robust to irregular indexing."""
    try:
        import pandas as pd
        df = store.read(group, name)
        if df is None or col not in df.columns:
            return None
        s = df[col].dropna()
        if s.empty:
            return None
        cutoff = s.index.max() - pd.Timedelta(days=days)
        past = s[s.index <= cutoff]
        if past.empty:
            return None
        return float(s.iloc[-1] - past.iloc[-1])
    except Exception:  # noqa: BLE001
        return None


def _sum_trailing_days(group: str, name: str, col: str, days: int):
    """Sum of a (per-event delta) column over the trailing `days` window. None if empty."""
    try:
        import pandas as pd
        df = store.read(group, name)
        if df is None or col not in df.columns:
            return None
        s = df[col].dropna()
        if s.empty:
            return None
        cutoff = s.index.max() - pd.Timedelta(days=days)
        recent = s[s.index >= cutoff]
        return float(recent.sum()) if not recent.empty else 0.0
    except Exception:  # noqa: BLE001
        return None


def _fr007_vs_trend(window: int = 120):
    try:
        df = store.read("china_pboc", "repo_rates")
        if df is None or "FR007" not in df.columns:
            return None, None
        s = df["FR007"].dropna()
        if len(s) < 30:
            return (float(s.iloc[-1]) if len(s) else None), None
        latest = float(s.iloc[-1])
        mean = float(s.tail(window).mean())
        return latest, latest - mean
    except Exception:  # noqa: BLE001
        return None, None


def _recent_moves() -> list[dict]:
    """Recent LPR + RRR changes as a dated, bilingual move log (newest first)."""
    moves: list[dict] = []
    try:
        df = store.read("china_macro", "rrr")
        if df is not None and "rrr_change" in df.columns:
            ch = df["rrr_change"].dropna()
            ch = ch[ch != 0]
            for d, v in list(ch.items())[-3:]:
                cut = v < 0
                moves.append({
                    "date": str(d.date()), "kind": "RRR",
                    "detail_en": f"RRR {'cut' if cut else 'hike'} {abs(v):.2f}pp",
                    "detail_zh": f"{'降准' if cut else '升准'} {abs(v):.2f}个百分点",
                    "easing": bool(cut)})
    except Exception:  # noqa: BLE001
        pass
    try:
        df = store.read("china_macro", "lpr_rate")
        if df is not None and "lpr_1y" in df.columns:
            s = df["lpr_1y"].dropna()
            d1 = s.diff().dropna()
            d1 = d1[d1 != 0]
            for d, v in list(d1.items())[-3:]:
                cut = v < 0
                moves.append({
                    "date": str(d.date()), "kind": "LPR1Y",
                    "detail_en": f"1Y LPR {'cut' if cut else 'hike'} {abs(v)*100:.0f}bp",
                    "detail_zh": f"1年期LPR{'下调' if cut else '上调'} {abs(v)*100:.0f}个基点",
                    "easing": bool(cut)})
    except Exception:  # noqa: BLE001
        pass
    moves.sort(key=lambda m: m["date"], reverse=True)
    return moves[:5]


def _classify(lpr_chg, rrr_chg, fr_gap) -> tuple[int, str]:
    """Net easing(+) / tightening(-) score → stance key. Deterministic + transparent."""
    score = 0
    if lpr_chg is not None:
        score += 1 if lpr_chg < -0.04 else (-1 if lpr_chg > 0.04 else 0)
    if rrr_chg is not None:
        score += 1 if rrr_chg < 0 else (-1 if rrr_chg > 0 else 0)
    if fr_gap is not None:
        score += 1 if fr_gap < -0.10 else (-1 if fr_gap > 0.10 else 0)
    if score >= 2:
        return score, "easing"
    if score <= -2:
        return score, "tightening"
    return score, "neutral"


_STANCE_LABEL = {
    "easing": ("Easing", "宽松"), "tightening": ("Tightening", "收紧"),
    "neutral": ("On hold / neutral", "按兵不动 / 中性"),
}


def snapshot(asof: date | str | None = None) -> dict | None:
    """The PBoC stance + rate-corridor read. None only on total data absence. Never raises."""
    try:
        lpr1, lpr1_d = _last("china_macro", "lpr_rate", "lpr_1y")
        lpr5, _ = _last("china_macro", "lpr_rate", "lpr_5y")
        rrr, rrr_d = _last("china_macro", "rrr", "rrr_big")
        fr007, fr_gap = _fr007_vs_trend()
        shibor_on, _ = _last("china_macro", "rates", "rate_on")
        shibor_3m, _ = _last("china_macro", "rates", "rate_3m")
        fx, fx_d = _last("china_pboc", "fx_reserves", "fx_reserves")
        fx_mom = _change_over("china_pboc", "fx_reserves", "fx_reserves", 1)
        gold, _ = _last("china_pboc", "fx_reserves", "gold_reserves")
        usdcny, cny_d = _last("china_pboc", "cny_fix", "usd_cny")
        usdcny_chg = _change_over("china_pboc", "cny_fix", "usd_cny", 20)

        if lpr1 is None and rrr is None and fr007 is None:
            return None

        # trailing-12-month LPR change + cumulative RRR easing over ~18 months (the RRR
        # series is event-indexed, so sum the per-event rrr_change deltas, not levels).
        lpr_chg = _chg_trailing_days("china_macro", "lpr_rate", "lpr_1y", 365)
        rrr_chg_recent = _sum_trailing_days("china_macro", "rrr", "rrr_change", 545)
        moves = _recent_moves()

        score, stance = _classify(lpr_chg, rrr_chg_recent, fr_gap)
        lab = _STANCE_LABEL[stance]

        # bilingual rationale
        bits_en, bits_zh = [], []
        if lpr_chg is not None:
            bits_en.append(f"1Y LPR {lpr_chg*100:+.0f}bp / yr")
            bits_zh.append(f"1年期LPR年内{lpr_chg*100:+.0f}基点")
        if rrr_chg_recent is not None:
            bits_en.append(f"RRR {rrr_chg_recent:+.2f}pp")
            bits_zh.append(f"准备金率{rrr_chg_recent:+.2f}个百分点")
        if fr_gap is not None:
            bits_en.append(f"FR007 {fr_gap:+.2f} vs trend")
            bits_zh.append(f"FR007较趋势{fr_gap:+.2f}")
        rationale = {
            "en": f"{lab[0]} bias — " + ", ".join(bits_en) + "." if bits_en else f"{lab[0]} bias.",
            "zh": f"{lab[1]}倾向 — " + "，".join(bits_zh) + "。" if bits_zh else f"{lab[1]}倾向。",
        }

        corridor = [
            {"key": "lpr_1y", "label_en": "1Y LPR", "label_zh": "1年期LPR", "value": lpr1, "unit": "%"},
            {"key": "lpr_5y", "label_en": "5Y LPR", "label_zh": "5年期LPR", "value": lpr5, "unit": "%"},
            {"key": "rrr", "label_en": "RRR (big banks)", "label_zh": "存准率(大行)", "value": rrr, "unit": "%"},
            {"key": "fr007", "label_en": "FR007 (repo)", "label_zh": "FR007回购", "value": fr007, "unit": "%"},
            {"key": "shibor_on", "label_en": "SHIBOR O/N", "label_zh": "隔夜SHIBOR", "value": shibor_on, "unit": "%"},
            {"key": "shibor_3m", "label_en": "SHIBOR 3M", "label_zh": "3个月SHIBOR", "value": shibor_3m, "unit": "%"},
        ]

        return {
            "schema": SCHEMA, "is_context_only": True,
            "asof": str(asof) if asof else str(lpr1_d or date.today()),
            "built": datetime.now(timezone.utc).isoformat(),
            "stance": stance, "stance_en": lab[0], "stance_zh": lab[1], "score": score,
            "rationale": rationale,
            "corridor": [c for c in corridor if c["value"] is not None],
            "fx": {"reserves": fx, "reserves_mom": fx_mom, "gold": gold,
                   "usd_cny": usdcny, "usd_cny_chg_20d": usdcny_chg,
                   "asof_reserves": str(fx_d) if fx_d else None,
                   "asof_cny": str(cny_d) if cny_d else None},
            "last_moves": moves,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_pboc_stance.snapshot failed (%s)", e)
        return None
