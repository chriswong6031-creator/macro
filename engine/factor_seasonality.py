"""Factor seasonality from the Ken French Data Library (collectors/french.py).

The deep-history answer to "which calendar months has each factor STYLE tended to
pay?" — computed on academic total-US-market long/short factor returns going back
to 1926-1963, decades longer than our ~3yr S&P-1500 price cache. For each French
factor and each calendar month we report mean, median and hit-rate (% of months
positive), over BOTH the full history AND trailing 30-year / 10-year windows.

DELIBERATELY UNSCORED context, mirroring engine/technicals.seasonality: full-sample
seasonal stats peek at the future, so this never enters a calibrated/PIT score —
it is displayed as the long-run seasonal CLIMATE of a style. And it is a DEFINITION
MISMATCH vs our own factors: French HML/RMW/CMA are value-weighted long/short
portfolios over the whole US market, not our winsorized cross-sectional z-score
quintiles over the S&P 1500. The page discloses both caveats.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from lib import store

log = logging.getLogger(__name__)

# our-facing key -> (French column, our live factor or None if context-only, EN label, ZH label, plain_en, plain_zh)
SEASON_MAP = [
    ("value",         "hml",    "value",         "Value (HML)",        "价值 (HML)",      "Cheap stocks (Value)",            "低估值（价值）"),
    ("profitability", "rmw",    "profitability", "Profitability (RMW)", "盈利 (RMW)",      "Strong earners (Profitability)",  "高盈利（盈利质量）"),
    ("investment",    "cma",    "investment",    "Investment (CMA)",   "投资 (CMA)",       "Careful spenders (Investment)",   "稳健投资（投资）"),
    ("momentum",      "mom",    None,            "Momentum (Mom)",     "动量 (Mom)",       "Recent winners (Momentum)",       "近期赢家（动量）"),
    ("size",          "smb",    None,            "Size (SMB)",         "规模 (SMB)",       "Small companies (Size)",          "小盘股（规模）"),
    ("market",        "mkt_rf", None,            "Market (Mkt-RF)",    "市场 (Mkt-RF)",   "The market itself",               "大盘整体"),
]

_TRAILING_YEARS_30 = 30
_TRAILING_YEARS_10 = 10
_MIN_PER_MONTH = 3                      # need at least this many observations of a calendar month
_MIN_PER_MONTH_VERDICT = 8              # need >= this for 10y window to be verdict-grade; else fall to 30y

# Month label tables (month number 1-12)
_MONTHS_EN = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
_MONTHS_EN_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_ZH = ["1月", "2月", "3月", "4月", "5月", "6月",
               "7月", "8月", "9月", "10月", "11月", "12月"]


def _month_stats(s: pd.Series, years: int | None = None) -> dict:
    """Per-calendar-month mean / median / hit-rate / n for a monthly return series."""
    s = s.dropna()
    if years and not s.empty:
        s = s[s.index > s.index.max() - pd.DateOffset(years=years)]
    out = {}
    for m in range(1, 13):
        r = s[s.index.month == m]
        if len(r) >= _MIN_PER_MONTH:
            out[m] = {"mean": round(float(r.mean()), 2),
                      "median": round(float(r.median()), 2),
                      "hit": round(float((r > 0).mean() * 100)),
                      "n": int(len(r))}
    return out


def _streak(recent_obs: list[float]) -> dict:
    """Consecutive same-sign streak from the most recent observation backward.

    recent_obs: list ordered most-recent FIRST (index 0 = newest).
    Returns {sign: int (+1/-1/0), len: int}.
    """
    if not recent_obs:
        return {"sign": 0, "len": 0}
    first = recent_obs[0]
    sign = 1 if first > 0 else -1
    length = 1
    for v in recent_obs[1:]:
        vsign = 1 if v > 0 else -1
        if vsign == sign:
            length += 1
        else:
            break
    return {"sign": sign, "len": length}


def _verdict(y10: dict | None, y30: dict | None) -> tuple[str, str]:
    """Determine verdict + window_used from display.v1 rules.

    Returns (verdict, window_used) where window_used is "trailing_10y" or "trailing_30y".
    Verdict: "headwind" | "tailwind" | "neutral".
    Fallback chain: 10y (n>=8) -> 30y -> "neutral".
    """
    # Try 10y first
    if y10 and y10.get("n", 0) >= _MIN_PER_MONTH_VERDICT:
        s = y10
        window_used = "trailing_10y"
    elif y30:
        s = y30
        window_used = "trailing_30y"
    else:
        return "neutral", "trailing_10y"

    hit = s["hit"]
    mean = s["mean"]
    if hit <= 40 and mean < 0:
        verdict = "headwind"
    elif hit >= 70 and mean > 0:
        verdict = "tailwind"
    else:
        verdict = "neutral"
    return verdict, window_used


def compute_factor_seasonality(today: date | None = None) -> dict | None:
    """Build the factor-seasonality payload (schema: factor_seasonality.v2) from data/french/factors.parquet.

    today: override for tests; defaults to date.today().
    Returns None (panel hides) if the French data is absent — degrade-never-raise.
    """
    df = store.read("french", "factors")
    if df is None or df.empty:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index)

    if today is None:
        today = date.today()

    factors = []
    for key, col, our, label_en, label_zh, plain_en, plain_zh in SEASON_MAP:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        factors.append({
            "key": key, "french": col, "our_factor": our,
            "label_en": label_en, "label_zh": label_zh,
            "plain_en": plain_en, "plain_zh": plain_zh,
            "context_only": our is None,
            "start": s.index.min().strftime("%Y-%m"),
            "n_months": int(len(s)),
            "full": _month_stats(s),
            "trailing_30y": _month_stats(s, years=_TRAILING_YEARS_30),
            "trailing_10y": _month_stats(s, years=_TRAILING_YEARS_10),
        })
    if not factors:
        return None

    # --- now block: current-month spotlight ---
    now_block = _build_now(df, factors, today)

    return {
        "schema": "factor_seasonality.v2",
        "as_of": df.index.max().strftime("%Y-%m"),
        "source": "Ken French Data Library (Dartmouth), monthly factor returns",
        "trailing_years": _TRAILING_YEARS_30,
        "disclosure_en": (
            "These are Ken French TOTAL-US-MARKET academic factor portfolios (value-"
            "weighted long/short, 1926/1963+), NOT our S&P-1500 winsorized z-score "
            "quintiles. A month's seasonal tendency describes the long-run CLIMATE of "
            "the style — it is not a forecast of our daily factor leadership, and it is "
            "deliberately kept out of every calibrated score."),
        "disclosure_zh": (
            "这些是 Ken French 的全市场学术因子组合（市值加权多空，1926/1963 年至今），"
            "并非我们对标普 1500 的去极值 z 分数分位。某月的季节性倾向描述的是该风格的长期"
            "气候，而非对我们每日因子领先的预测，且刻意不纳入任何校准评分。"),
        "factors": factors,
        "now": now_block,
    }


# ---------------------------------------------------------------------------
# Now block helpers
# ---------------------------------------------------------------------------

def _build_now(df: pd.DataFrame, factors: list[dict], today: date) -> dict | None:
    """Build current-month spotlight block. Returns None on any failure (fail-open)."""
    try:
        return _build_now_inner(df, factors, today)
    except Exception:
        log.exception("factor_seasonality.now: failed, returning None")
        return None


def _build_now_inner(df: pd.DataFrame, factors: list[dict], today: date) -> dict | None:
    month = today.month
    month_label_en = _MONTHS_EN[month - 1]
    month_label_zh = _MONTHS_ZH[month - 1]
    month_short = _MONTHS_EN_SHORT[month - 1]

    # Build per-factor now entries
    now_factors = []
    for f in factors:
        key = f["key"]
        if key == "market":
            continue  # market goes into separate top-level key

        s_all = df[f["french"]].dropna()
        y10_stats = f["trailing_10y"].get(month)
        y30_stats = f["trailing_30y"].get(month)
        full_stats = f["full"].get(month)

        verdict, window_used = _verdict(y10_stats, y30_stats)

        # Recent: last 10 same-month observations, most-recent first
        same_month = s_all[s_all.index.month == month].sort_index(ascending=False)
        recent_10 = same_month.head(10)
        recent = [
            {"year": int(ts.year), "ret": round(float(val), 2)}
            for ts, val in zip(recent_10.index, recent_10.values)
        ]

        streak_vals = [r["ret"] for r in recent]
        sk = _streak(streak_vals)

        now_factors.append({
            "key": key,
            "plain_en": f["plain_en"],
            "plain_zh": f["plain_zh"],
            "verdict": verdict,
            "window_used": window_used,
            "y10": y10_stats or {},
            "y30": y30_stats or {},
            "full": full_stats or {},
            "recent": recent,
            "streak": sk,
        })

    # Market block
    mkt_col = "mkt_rf"
    mkt_s = df[mkt_col].dropna() if mkt_col in df.columns else pd.Series([], dtype=float)
    mkt_y10_stats = {}
    if not mkt_s.empty:
        cutoff = mkt_s.index.max() - pd.DateOffset(years=_TRAILING_YEARS_10)
        mkt_10 = mkt_s[mkt_s.index > cutoff]
        mkt_month = mkt_10[mkt_10.index.month == month]
        if len(mkt_month) >= _MIN_PER_MONTH:
            mkt_y10_stats = {
                "mean": round(float(mkt_month.mean()), 2),
                "hit": round(float((mkt_month > 0).mean() * 100)),
                "n": int(len(mkt_month)),
            }

    market_block = mkt_y10_stats

    # Find dominant factor for headline
    mom_entry = next((f for f in now_factors if f["key"] == "momentum"), None)
    headline_en, headline_zh, stance_en, stance_zh, chip_en, chip_zh = _compose_copy(
        mom_entry, now_factors, market_block, month_label_en, month_label_zh, month_short, month
    )

    return {
        "month": month,
        "month_label_en": month_label_en,
        "month_label_zh": month_label_zh,
        "factors": now_factors,
        "market": market_block,
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "stance_en": stance_en,
        "stance_zh": stance_zh,
        "chip_en": chip_en,
        "chip_zh": chip_zh,
        "verdict_rule": "display.v1",
    }


def _compose_copy(
    mom_entry: dict | None,
    now_factors: list[dict],
    market_block: dict,
    month_label_en: str,
    month_label_zh: str,
    month_short: str,
    month: int,
) -> tuple[str | None, str | None, str, str, str | None, str | None]:
    """Return (headline_en, headline_zh, stance_en, stance_zh, chip_en, chip_zh).

    Headline template rule (display.v1, deterministic — no adjectives beyond these templates):
    1. If momentum == headwind: momentum-headwind template.
    2. If momentum == tailwind: momentum-tailwind template.
    3. If momentum neutral but another factor non-neutral: name that factor.
    4. All neutral: generic no-lean copy.
    """
    # Helper: down count from recent list
    def _down_count(recent: list[dict]) -> int:
        return sum(1 for r in recent if r["ret"] < 0)

    mkt_hit = market_block.get("hit", 50)
    mkt_mean = market_block.get("mean", 0.0)
    mkt_up_word_en = "up" if (mkt_mean if mkt_mean is not None else 0) >= 0 else "down"
    mkt_up_word_zh = "上涨" if (mkt_mean if mkt_mean is not None else 0) >= 0 else "下跌"

    if mom_entry and mom_entry["verdict"] == "headwind":
        recent = mom_entry["recent"]
        # recent is capped at 10 rows while y10 n can exceed it on some DateOffset
        # alignments — clamp so the quoted "last N" always matches the counted set
        n = min(mom_entry["y10"].get("n") or len(recent), len(recent))
        down = _down_count(recent[:n])
        sk = mom_entry["streak"]
        streak_suffix_en = ""
        if sk["sign"] < 0 and sk["len"] >= 3:
            streak_suffix_en = f", including the last {sk['len']} straight"
        streak_suffix_zh = ""
        if sk["sign"] < 0 and sk["len"] >= 3:
            streak_suffix_zh = f"（含连续 {sk['len']} 年）"
        headline_en = (
            f"{month_label_en} is usually a rough month for the market's recent winners — "
            f"the momentum style fell in {down} of the last {n} {month_label_en}s"
            f"{streak_suffix_en}, while the market itself was {mkt_up_word_en} in "
            f"{mkt_hit}% of them."
        )
        headline_zh = (
            f"{month_label_zh}通常是市场近期赢家的困难月份——"
            f"动量风格在过去 {n} 个{month_label_zh}中下跌了 {down} 次"
            f"{streak_suffix_zh}，而大盘在其中 {mkt_hit}% 的时间{mkt_up_word_zh}。"
        )
        stance_en = "Watch — don't chase this month's hottest stocks."
        stance_zh = "观望——本月不要追逐最热门的股票。"
        chip_en = (
            f"{month_short}: usually a rough month for hot stocks "
            f"(fell in {down}/{n}) · context only"
        )
        chip_zh = f"{month_label_zh}：热门股历来偏弱（近{n}年{down}次下跌）· 仅供参考"
        return headline_en, headline_zh, stance_en, stance_zh, chip_en, chip_zh

    if mom_entry and mom_entry["verdict"] == "tailwind":
        recent = mom_entry["recent"]
        n = min(mom_entry["y10"].get("n") or len(recent), len(recent))
        up = n - _down_count(recent[:n])
        sk = mom_entry["streak"]
        streak_suffix_en = ""
        if sk["sign"] > 0 and sk["len"] >= 3:
            streak_suffix_en = f", including the last {sk['len']} straight"
        streak_suffix_zh = ""
        if sk["sign"] > 0 and sk["len"] >= 3:
            streak_suffix_zh = f"（含连续 {sk['len']} 年）"
        headline_en = (
            f"{month_label_en} has tended to be kind to the market's recent winners — "
            f"the momentum style rose in {up} of the last {n} {month_label_en}s"
            f"{streak_suffix_en}, while the market itself was {mkt_up_word_en} in "
            f"{mkt_hit}% of them."
        )
        headline_zh = (
            f"{month_label_zh}通常对市场近期赢家较友好——"
            f"动量风格在过去 {n} 个{month_label_zh}中上涨了 {up} 次"
            f"{streak_suffix_zh}，而大盘在其中 {mkt_hit}% 的时间{mkt_up_word_zh}。"
        )
        stance_en = "A seasonally friendlier month for recent winners — still judge each stock on its merits."
        stance_zh = "季节性上对近期赢家较为有利——仍需就每只股票独立判断。"
        chip_en = (
            f"{month_short}: seasonally friendly for hot stocks "
            f"(rose in {up}/{n}) · context only"
        )
        chip_zh = f"{month_label_zh}：热门股历来偏强（近{n}年{up}次上涨）· 仅供参考"
        return headline_en, headline_zh, stance_en, stance_zh, chip_en, chip_zh

    # Momentum neutral — check other factors
    other_non_neutral = next(
        (f for f in now_factors if f["key"] != "momentum" and f["verdict"] != "neutral"),
        None
    )
    if other_non_neutral:
        f_plain_en = other_non_neutral["plain_en"]
        f_plain_zh = other_non_neutral["plain_zh"]
        vdict = other_non_neutral["verdict"]
        recent = other_non_neutral["recent"]
        n = min(other_non_neutral["y10"].get("n") or len(recent), len(recent))
        if vdict == "headwind":
            down = _down_count(recent[:n])
            headline_en = (
                f"{month_label_en} has historically been a rough month for {f_plain_en} — "
                f"fell in {down} of the last {n} {month_label_en}s."
            )
            headline_zh = (
                f"{month_label_zh}历史上对{f_plain_zh}表现偏弱——"
                f"过去 {n} 个{month_label_zh}中下跌了 {down} 次。"
            )
            stance_en = f"Seasonally softer month for {f_plain_en} — judge on the merits."
            stance_zh = f"季节性上{f_plain_zh}较弱——以基本面为准。"
            chip_en = f"{month_short}: seasonal headwind for {f_plain_en} · context only"
            chip_zh = f"{month_label_zh}：{f_plain_zh}季节性偏弱 · 仅供参考"
        else:
            up_count = n - _down_count(recent[:n])
            headline_en = (
                f"{month_label_en} has historically been a friendlier month for {f_plain_en} — "
                f"rose in {up_count} of the last {n} {month_label_en}s."
            )
            headline_zh = (
                f"{month_label_zh}历史上对{f_plain_zh}表现偏强——"
                f"过去 {n} 个{month_label_zh}中上涨了 {up_count} 次。"
            )
            stance_en = f"Seasonally friendlier month for {f_plain_en} — still judge on the merits."
            stance_zh = f"季节性上{f_plain_zh}较强——仍以基本面为准。"
            chip_en = f"{month_short}: seasonal tailwind for {f_plain_en} · context only"
            chip_zh = f"{month_label_zh}：{f_plain_zh}季节性偏强 · 仅供参考"
        return headline_en, headline_zh, stance_en, stance_zh, chip_en, chip_zh

    # All neutral
    headline_en = "No strong seasonal lean this month."
    headline_zh = "本月无明显季节性倾向。"
    stance_en = "Judge on the merits — the calendar has no strong opinion."
    stance_zh = "以基本面为准——日历本月无明显观点。"
    chip_en = None
    chip_zh = None
    return headline_en, headline_zh, stance_en, stance_zh, chip_en, chip_zh
