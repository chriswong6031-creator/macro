"""Fed policy path — the market-implied rate path vs the FOMC dot-plot.

ADDITIVE / leaf module — imports nothing from the scoring core, and nothing in the
scoring path imports it. It assembles a DISPLAY block (bonds.html + the latest.json
LLM-context vector) from three free, keyless feeds:

  • the FOMC dot-plot median (FRED FEDTARMD) — the Fed's own projected path,
  • the live target range (FRED DFEDTARU/DFEDTARL) — where policy is set today,
  • the ZQ/SR3 futures-implied path (collectors/rate_futures.py) — where the market
    prices the funds rate at 1/3/6/12 months out,

plus the curve primitives already in the frame (near-term forward spread, the
term-premium-adjusted slope, the us2y−funds rate-expectations proxy).

DISCIPLINE — display / context ONLY. The implied path LEVEL is a market PRICE, not a
forecast edge, and repricing is REACTIVE (the curve moves *after* data and the Fed,
it does not lead it). There is therefore NO scored leg and NO MRS entry — this only
enlarges the facts the read can cite. See research/DATA_SIGNAL_EXPANSION_2026.md #2.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

_QUARTER = 0.25  # one 25bp move


def _cfg() -> dict:
    return config.load().get("rate_futures", {}) or {}


def _r(v, nd: int = 2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _interp_horizon(path_row: dict, horizons: list[int], h: float) -> float | None:
    """Linear-interpolate the implied rate at horizon `h` months from a path row
    keyed ``m{H}`` over the available horizons (e.g. {m1, m3, m6, m12})."""
    pts = [(hm, path_row.get(f"m{hm}")) for hm in horizons]
    pts = [(x, y) for x, y in pts if y is not None and np.isfinite(y)]
    if not pts:
        return None
    pts.sort()
    if h <= pts[0][0]:
        return pts[0][1]
    if h >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        if h <= pts[i][0]:
            x0, x1, y0, y1 = pts[i - 1][0], pts[i][0], pts[i - 1][1], pts[i][1]
            return y0 + (y1 - y0) * (h - x0) / (x1 - x0) if x1 != x0 else y1
    return pts[-1][1]


def _dots_by_year(dot_series: pd.Series | None, this_year: int) -> list[dict]:
    """Forward dot-plot medians keyed by projection year. FRED stamps each SEP
    projection at the year-end it projects, overwriting on each release, so the
    latest value per year IS the current dot path. Keeps years >= this year."""
    if dot_series is None:
        return []
    s = dot_series.dropna()
    if s.empty:
        return []
    by_year: dict[int, float] = {}
    for ts, v in s.items():
        by_year[pd.Timestamp(ts).year] = float(v)  # last write per year wins
    return [{"year": y, "median": round(by_year[y], 3)}
            for y in sorted(by_year) if y >= this_year]


def _lean(gap_bp: float | None) -> tuple[str, str]:
    if gap_bp is None:
        return ("—", "—")
    if abs(gap_bp) < 13:  # < ~half a 25bp move = essentially aligned
        return ("market ≈ the Fed", "市场与美联储基本一致")
    if gap_bp < 0:        # market prices a LOWER rate than the Fed projects
        return ("market more dovish than the Fed", "市场比美联储更鸽派")
    return ("market more hawkish than the Fed", "市场比美联储更鹰派")


def compute(*, asof, policy_rate, target_low, target_high, dot_series,
            zq_path_row, sofr_path_row, zq_front_implied,
            ntfs, curve_tp_adj, rate_exp_proxy, cfg=None) -> dict | None:
    """PURE — assemble the policy-path display block from already-extracted inputs.

    `zq_path_row` / `sofr_path_row` are the latest implied-path rows (dicts keyed
    ``m{H}``) from collectors/rate_futures.py; `dot_series` is the raw FEDTARMD
    series. Returns None only when there is genuinely nothing to show."""
    cfg = cfg if cfg is not None else _cfg()
    horizons = list(cfg.get("horizons_m", [1, 3, 6, 12]))
    asof_ts = pd.Timestamp(asof)

    tmid = None
    if target_low is not None and target_high is not None:
        tmid = round((target_low + target_high) / 2, 3)
    pol = policy_rate if policy_rate is not None else tmid

    # --- the market-implied path: prefer ZQ (fed funds), else SOFR; the ZQ front
    # implied rate (100 − ZQ=F) is the always-available near anchor.
    path_row, path_src, path_src_zh = None, None, None
    if zq_path_row and any(v is not None for v in zq_path_row.values()):
        path_row, path_src, path_src_zh = zq_path_row, "ZQ fed-funds futures", "ZQ 联邦基金期货"
    elif sofr_path_row and any(v is not None for v in sofr_path_row.values()):
        path_row, path_src, path_src_zh = sofr_path_row, "SR3 SOFR futures", "SR3 SOFR 期货"

    implied = {"now": _r(pol)}
    if path_row:
        for h in horizons:
            implied[f"m{h}"] = _r(path_row.get(f"m{h}"))
    elif zq_front_implied is not None:
        # degraded: only the ~1-month ZQ front is available (no dated strip)
        implied["m1"] = _r(zq_front_implied)
        path_src, path_src_zh = "ZQ front (30d) only", "仅 ZQ 近月 (30天)"

    m12 = implied.get("m12")
    m6 = implied.get("m6")
    implied_bp_12m = round((m12 - pol) * 100) if (m12 is not None and pol is not None) else None
    implied_cuts_12m = round((pol - m12) / _QUARTER) if (m12 is not None and pol is not None) else None
    implied_cuts_6m = round((pol - m6) / _QUARTER) if (m6 is not None and pol is not None) else None

    # --- the dot-plot path + the Fed-vs-market gap at the nearest projection horizon
    dots = _dots_by_year(dot_series, asof_ts.year)
    gap = None
    if dots and path_row:
        dot = dots[0]                                       # nearest forward year
        months = (dot["year"] - asof_ts.year) * 12 + (12 - asof_ts.month)
        months = max(1, months)
        if months <= max(horizons):                         # only compare within the strip
            mkt = _interp_horizon(path_row, horizons, months)
            if mkt is not None:
                gap_bp = round((mkt - dot["median"]) * 100)
                lean_en, lean_zh = _lean(gap_bp)
                gap = {
                    "horizon_label": f"end-{dot['year']}", "horizon_months": months,
                    "fed_dot": dot["median"], "market": _r(mkt), "gap_bp": gap_bp,
                    "lean_en": lean_en, "lean_zh": lean_zh,
                }

    # --- honest narrative -----------------------------------------------------
    cut_word = None
    if implied_cuts_12m is not None:
        n = implied_cuts_12m
        cut_word = (f"{n} cut{'s' if n != 1 else ''}" if n > 0
                    else f"{-n} hike{'s' if n != -1 else ''}" if n < 0 else "no change")
    head_en = head_zh = None
    if cut_word and pol is not None:
        head_en = f"Market prices ~{cut_word} over the next 12m (funds {pol:.2f}% → {m12:.2f}%)"
        head_zh = f"市场为未来12个月定价约{('降息' if implied_cuts_12m>0 else '加息' if implied_cuts_12m<0 else '不变')}{abs(implied_cuts_12m) if implied_cuts_12m else ''}次（基金利率 {pol:.2f}% → {m12:.2f}%）"
    elif pol is not None:
        head_en = f"Policy set at {pol:.2f}%"
        head_zh = f"政策利率设定于 {pol:.2f}%"

    read_en, read_zh = [], []
    if gap:
        read_en.append(f"At {gap['horizon_label']} the market implies {gap['market']:.2f}% vs the Fed's {gap['fed_dot']:.2f}% median dot ({gap['gap_bp']:+d}bp — {gap['lean_en']}).")
        read_zh.append(f"在{gap['horizon_label']}，市场隐含 {gap['market']:.2f}% 对比美联储 {gap['fed_dot']:.2f}% 的中位点（{gap['gap_bp']:+d}基点 — {gap['lean_zh']}）。")
    if ntfs is not None:
        ntfs_msg_en = ("The near-term forward spread is negative — the market prices cuts ~18m out"
                       if ntfs < 0 else "The near-term forward spread is positive — no cuts priced near-term")
        ntfs_msg_zh = ("近端远期利差为负——市场为约18个月后的降息定价" if ntfs < 0
                       else "近端远期利差为正——近端未为降息定价")
        read_en.append(f"{ntfs_msg_en} ({ntfs:+.2f}pp).")
        read_zh.append(f"{ntfs_msg_zh}（{ntfs:+.2f}个百分点）。")

    out = {
        "asof": str(asof_ts.date()),
        "built": datetime.now(timezone.utc).isoformat(),
        "policy_rate": _r(policy_rate), "target_low": _r(target_low),
        "target_high": _r(target_high), "target_mid": _r(tmid),
        "implied": implied, "implied_source_en": path_src, "implied_source_zh": path_src_zh,
        "implied_bp_12m": implied_bp_12m, "implied_cuts_12m": implied_cuts_12m,
        "implied_cuts_6m": implied_cuts_6m,
        "sofr_path": ({f"m{h}": _r(sofr_path_row.get(f"m{h}")) for h in horizons}
                      if sofr_path_row else None),
        "dots": dots, "gap": gap,
        "ntfs": _r(ntfs), "curve_tp_adj": _r(curve_tp_adj),
        "rate_exp_proxy": _r(rate_exp_proxy),
        "headline_en": head_en, "headline_zh": head_zh,
        "read_en": " ".join(read_en) or None, "read_zh": "".join(read_zh) or None,
        "note_en": ("Display / LLM-context only. The implied path is a market PRICE (the "
                    "futures-implied funds rate), not a forecast edge, and repricing is "
                    "REACTIVE — it moves after data and the Fed, it does not lead. Never "
                    "scored, never an MRS leg. ZQ/SR3 = keyless CME futures; dots = FRED "
                    "FEDTARMD (FOMC SEP median). Cite the CME/FRED."),
        "note_zh": ("仅供展示 / LLM 上下文。隐含路径是市场价格（期货隐含的基金利率），"
                    "并非预测优势，且重新定价是被动的——它在数据和美联储之后变动，并不领先。"
                    "从不评分，从不作为 MRS 项。ZQ/SR3=无需密钥的 CME 期货；点阵图=FRED FEDTARMD"
                    "（FOMC SEP 中位数）。请注明 CME/FRED。"),
    }
    # nothing worth showing?
    if (out["policy_rate"] is None and not dots and not path_row
            and zq_front_implied is None):
        return None
    return out


def _read_path_row(store_key: str) -> tuple[dict | None, str | None]:
    """Latest implied-path row (dict keyed m{H}) from data/rate_futures/."""
    df = store.read("rate_futures", store_key)
    if df is None or df.empty:
        return None, None
    row = df.dropna(how="all").iloc[-1]
    asof = str(df.dropna(how="all").index[-1].date())
    return {c: (None if pd.isna(row[c]) else float(row[c])) for c in df.columns}, asof


def snapshot(f: pd.DataFrame, cfg: dict | None = None) -> dict | None:
    """Live wiring: pull every input from the feature frame + the store, then
    delegate to the pure compute(). Degrade-never-raise."""
    from engine.bonds import near_term_forward_spread
    cfg = cfg if cfg is not None else _cfg()

    asof = f.dropna(how="all").index.max() if len(f) else pd.Timestamp.utcnow()
    policy_rate = _last(f["fed_funds"]) if "fed_funds" in f else None
    target_low = _last(f["fed_target_lower"]) if "fed_target_lower" in f else None
    target_high = _last(f["fed_target_upper"]) if "fed_target_upper" in f else None
    zq_front_implied = _last(f["zq_implied_rate"]) if "zq_implied_rate" in f else None
    rate_exp_proxy = _last(f["rate_expectations_proxy"]) if "rate_expectations_proxy" in f else None
    curve_tp_adj = _last(f["curve_tp_adj"]) if "curve_tp_adj" in f else None
    try:
        ntfs = _last(near_term_forward_spread(f))
    except Exception:  # noqa: BLE001 — additive, never fatal
        ntfs = None

    # dot-plot path: read the RAW FRED series (the frame ffill collapses its horizons)
    dot_df = store.read("fred", "FEDTARMD")
    dot_series = dot_df.iloc[:, 0] if dot_df is not None and not dot_df.empty else None
    if dot_series is None and "fed_dot_median" in f:  # frame fallback (single dot)
        dot_series = f["fed_dot_median"].dropna()

    zq_row, _ = _read_path_row("zq_path")
    sofr_row, _ = _read_path_row("sofr_path")

    return compute(asof=asof, policy_rate=policy_rate, target_low=target_low,
                   target_high=target_high, dot_series=dot_series,
                   zq_path_row=zq_row, sofr_path_row=sofr_row,
                   zq_front_implied=zq_front_implied, ntfs=ntfs,
                   curve_tp_adj=curve_tp_adj, rate_exp_proxy=rate_exp_proxy, cfg=cfg)
