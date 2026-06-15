"""Treasury supply absorption — is the market digesting US debt smoothly?

ADDITIVE / leaf module — imports nothing from the scoring core, and nothing in the
scoring path imports it. The DEMAND read for the Treasury market, from the keyless
TreasuryDirect auction results (collectors/treasury_auctions.py).

For each recent coupon auction we standardise three demand metrics against the
trailing window of SAME-TENOR auctions (a 10y note vs prior 10y notes — sizes and
yields differ wildly across tenors, so only a same-tenor z-score is meaningful):

  • bid-to-cover           — total bids / amount sold (higher = stronger demand)
  • indirect-bidder share  — indirect / total accepted (foreign & real-money demand)
  • dealer takedown share  — primary-dealer / total accepted (the backstop: a HIGH
                             dealer share means weak end-demand, so it is INVERTED)

absorption_z = mean(z_bid_to_cover, z_indirect, −z_dealer). A soft auction clears with
a low cover, a low indirect share and a high dealer takedown → negative absorption.

We also track the bills-vs-coupons issuance mix: a rising coupon share = more duration
supply hitting the market (duration-hostile), a bill-heavy mix is liquidity-friendly.

WHY DISPLAY-ONLY (never scored, never an MRS leg):
  • the true auction *tail* (stop-out minus the when-issued yield) needs intraday WI
    quotes that are not in any free feed — so we omit it rather than fake it;
  • on a daily-rebuild dashboard the result is public & digested by the close, so it is
    supply-absorption CONTEXT, not a forward signal — and a bad long-bond auction
    often marks a local yield HIGH (concession built in beforehand), so the naive
    "soft auction → higher yields → risk-off" sign is unreliable.
Framed as context; a Phase-0 on the accruing history would gate any future scoring.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# NOMINAL coupons only get per-tenor demand z-scores — a real-yield TIPS or a
# floating FRN auction is a different market and is not comparable to a nominal note.
_NOMINAL = ("Note", "Bond")
_METRICS = ("bid_to_cover", "indirect_share", "dealer_share")

NOTE_EN = ("Auction demand is supply-absorption CONTEXT, not a validated directional "
           "signal — never scored, never an MRS leg. Demand metrics are z-scored vs the "
           "trailing same-tenor auctions. The true auction tail (stop-out minus the "
           "when-issued yield) is omitted: it needs intraday when-issued quotes that are "
           "not freely available. Source: TreasuryDirect auction results (keyless).")
NOTE_ZH = ("拍卖需求是供给吸收的背景信息，而非经validated的方向性信号——从不评分，也非MRS腿。"
           "需求指标相对同期限近期拍卖做z-score。真正的拍卖尾部（中标利率减去when-issued收益率）"
           "予以省略：它需要免费数据中没有的盘中when-issued报价。来源：TreasuryDirect 拍卖结果（无需密钥）。")


def _cfg() -> dict:
    return config.load().get("treasury_auctions", {}) or {}


def _tenor_label(tenor) -> str:
    try:
        return f"{int(tenor)}y"
    except (TypeError, ValueError):
        return "—"


def _z(latest: float | None, hist: list[float], min_n: int) -> float | None:
    """z of `latest` vs the prior-window list `hist` (which excludes latest). PURE."""
    h = [float(x) for x in hist if x is not None and np.isfinite(x)]
    if latest is None or not np.isfinite(latest) or len(h) < min_n:
        return None
    mu = float(np.mean(h))
    sd = float(np.std(h, ddof=1))
    if not np.isfinite(sd) or sd < 1e-9:
        return None
    return round((float(latest) - mu) / sd, 2)


def _tag(absorption_z: float | None, strong: float) -> str:
    if absorption_z is None:
        return "n/a"
    return "strong" if absorption_z >= strong else "soft" if absorption_z <= -strong else "in-line"


def _klass(df: pd.DataFrame) -> pd.Series:
    """Instrument class, tolerating an older parquet without the `klass` column. PURE."""
    if "klass" in df.columns:
        return df["klass"].fillna(df.get("security_type")).astype(str)
    return df.get("security_type", pd.Series("", index=df.index)).astype(str)


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    """Clean + derive demand shares on the NOMINAL-coupon subset. PURE."""
    d = df.copy()
    d["auction_date"] = pd.to_datetime(d["auction_date"])
    d = d[_klass(d).isin(_NOMINAL) & d["tenor"].notna()].copy()
    tot = pd.to_numeric(d.get("total_accepted"), errors="coerce")
    d["indirect_share"] = pd.to_numeric(d.get("indirect_accepted"), errors="coerce") / tot
    d["dealer_share"] = pd.to_numeric(d.get("primary_dealer_accepted"), errors="coerce") / tot
    d["bid_to_cover"] = pd.to_numeric(d.get("bid_to_cover"), errors="coerce")
    return d.sort_values("auction_date").reset_index(drop=True)


def _score_rows(d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Add per-metric z-scores (vs trailing same-tenor) + composite absorption_z. PURE."""
    trailing = int(cfg.get("trailing", 8))
    min_n = int(cfg.get("min_trailing", 5))
    for m in _METRICS:
        d[m + "_z"] = np.nan
    for _, g in d.groupby("tenor"):
        idx = list(g.index)
        for i in range(len(idx)):
            if i < min_n:
                continue
            window = g.iloc[max(0, i - trailing):i]
            cur = g.iloc[i]
            for m in _METRICS:
                z = _z(cur[m], list(window[m]), min_n)
                if z is not None:
                    d.at[idx[i], m + "_z"] = z
    # higher cover & indirect = stronger; higher dealer takedown = weaker (invert)
    d["absorption_z"] = pd.concat(
        [d["bid_to_cover_z"], d["indirect_share_z"], -d["dealer_share_z"]], axis=1
    ).mean(axis=1, skipna=True)
    return d


def _supply_trend(df: pd.DataFrame, cfg: dict) -> dict | None:
    """Gross NOMINAL-coupon (duration) issuance over the trailing window vs the window
    before it. PURE. Coupons only — the free auctioned feed's bill history is too shallow
    (~6 weeks) for a reliable bills-vs-coupons ratio, so we track the duration supply we
    DO have completely. Rising coupon issuance = more duration hitting the market."""
    win = int(cfg.get("mix_window_days", 90))
    d = df.copy()
    d["auction_date"] = pd.to_datetime(d["auction_date"])
    d["amt"] = pd.to_numeric(d.get("total_accepted"), errors="coerce")
    d = d[_klass(d).isin(_NOMINAL) & d["amt"].notna() & (d["amt"] > 0)]
    if d.empty:
        return None
    end = d["auction_date"].max()

    def coupon_bn(lo, hi) -> float | None:
        w = d[(d["auction_date"] > lo) & (d["auction_date"] <= hi)]
        return float(w["amt"].sum() / 1e9) if not w.empty else None

    cur = coupon_bn(end - pd.Timedelta(days=win), end)
    prev = coupon_bn(end - pd.Timedelta(days=2 * win), end - pd.Timedelta(days=win))
    if cur is None:
        return None
    chg = None if not prev else round((cur / prev - 1.0) * 100, 1)
    if chg is None:
        pressure = "neutral"
    elif chg >= 10:
        pressure = "coupon supply rising"      # duration-hostile
    elif chg <= -10:
        pressure = "coupon supply easing"
    else:
        pressure = "stable"
    return {"coupon_bn": round(cur, 0), "coupon_chg_pct": chg,
            "pressure": pressure, "window_days": win}


def compute(df: pd.DataFrame | None, cfg: dict | None = None) -> dict | None:
    """PURE — the accrued auctions frame + config → the supply-absorption panel."""
    cfg = cfg if cfg is not None else _cfg()
    if df is None or df.empty:
        return None
    coup = _prep(df)
    if coup.empty:
        return None
    scored = _score_rows(coup, cfg)
    strong = float(cfg.get("strong_z", 0.6))
    recent_n = int(cfg.get("recent", 10))

    rows = []
    for _, r in scored.sort_values("auction_date", ascending=False).head(recent_n).iterrows():
        az = r["absorption_z"]
        az = None if pd.isna(az) else round(float(az), 2)
        rows.append({
            "date": r["auction_date"].strftime("%Y-%m-%d"),
            "tenor": _tenor_label(r["tenor"]),
            "tenor_n": int(r["tenor"]),
            "type": r["security_type"],
            "reopening": bool(r.get("reopening")),
            "bid_to_cover": None if pd.isna(r["bid_to_cover"]) else round(float(r["bid_to_cover"]), 2),
            "indirect_pct": None if pd.isna(r["indirect_share"]) else round(float(r["indirect_share"]) * 100, 1),
            "dealer_pct": None if pd.isna(r["dealer_share"]) else round(float(r["dealer_share"]) * 100, 1),
            "absorption_z": az,
            "tag": _tag(az, strong),
        })

    scored_recent = [x for x in rows if x["absorption_z"] is not None]
    n = len(scored_recent)
    n_soft = sum(1 for x in scored_recent if x["tag"] == "soft")
    n_strong = sum(1 for x in scored_recent if x["tag"] == "strong")
    if n == 0:
        headline = "insufficient same-tenor history to score recent auctions"
    elif n_soft >= 2 and n_soft >= n_strong:
        headline = f"{n_soft} of last {n} coupon auctions clearing soft — watch duration demand"
    elif n_strong > n_soft:
        headline = f"recent coupon demand firm ({n_strong} of last {n} strong)"
    else:
        headline = f"recent coupon demand in-line ({n} of last {recent_n} scored)"

    asof = scored["auction_date"].max()
    return {
        "asof": None if pd.isna(asof) else asof.strftime("%Y-%m-%d"),
        "built": datetime.now(timezone.utc).isoformat(),
        "rows": rows, "n_scored": n, "n_soft": n_soft, "n_strong": n_strong,
        "headline": headline,
        "supply": _supply_trend(df, cfg),
        "note_en": NOTE_EN, "note_zh": NOTE_ZH,
    }


def snapshot(cfg: dict | None = None) -> dict | None:
    cfg = cfg if cfg is not None else _cfg()
    p = config.data_dir() / "treasury_auctions" / "auctions.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("treasury auctions parquet unreadable: %s", e)
        return None
    return compute(df, cfg)
