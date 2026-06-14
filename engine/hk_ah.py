"""Hong Kong AH-premium computed basket — an HK-native valuation/rotation gauge.

Many large mainland companies are dual-listed: an A-share in Shanghai/Shenzhen
(priced in CNY) and an H-share in Hong Kong (priced in HKD). The AH premium is how
much DEARER the A-share trades vs its HK-listed H twin in a common currency. A high
premium = the H/HK line is the cheaper way to own the same company (and, when it
mean-reverts, the rotation tends to favour HK).

This is a "computed AH basket": for each pair we convert the H close into CNY using
USDCNY/USDHKD, take premium_pct = (A_cny / H_in_cny - 1) * 100, and equal-weight the
mean across pairs into a daily series. We assume 1:1 A/H share-equivalence (no
share-class / float adjustment), so the ABSOLUTE level differs slightly from the
official Hang Seng AH Premium index — lean on the TREND and PERCENTILE, not the level.

Pure pandas over the parquet store; returns plain-Python dicts (ISO-date strings,
float/int/None) or ``None`` if too few pairs resolve, so callers never crash.
"""
from __future__ import annotations

import pandas as pd

from lib import config, store


def _pctile(s: pd.Series, v: float) -> int:
    """Percentile rank (0-100) of v within s."""
    s = s.dropna()
    if s.empty:
        return 0
    return int(round((s <= v).mean() * 100))


def _series(s: pd.Series, last_days: int | None = None, ndigits: int = 3) -> dict:
    """ISO-date + value arrays for a plotly line, optionally trimmed to a tail."""
    s = s.dropna()
    if last_days is not None and not s.empty:
        s = s.loc[s.index.max() - pd.Timedelta(days=last_days):]
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "vals": [round(float(v), ndigits) for v in s]}


def ah_basket() -> dict | None:
    cfg = config.load().get("hk", {})
    pairs = cfg.get("ah_pairs") or {}
    names = cfg.get("names") or {}
    if not pairs:
        return None

    # H-share closes (HKD) — cached parquet outside the group/name store layout.
    try:
        h_closes = pd.read_parquet(config.data_dir() / "hk_breadth" / "_closes_cache.parquet")
    except (FileNotFoundError, OSError):
        return None
    if h_closes is None or h_closes.empty:
        return None

    a_closes = store.read("china_search", "closes")
    if a_closes is None or a_closes.empty:
        return None

    cny = store.read("china", "CNY=X")          # CNY per USD
    hkd = store.read("hk", "HKD=X")             # HKD per USD
    if cny is None or hkd is None or "close" not in cny.columns or "close" not in hkd.columns:
        return None
    usdcny = cny["close"].dropna()
    usdhkd = hkd["close"].dropna()
    if usdcny.empty or usdhkd.empty:
        return None
    cny_per_hkd = (usdcny / usdhkd).dropna()    # ~0.86-0.91
    if cny_per_hkd.empty:
        return None

    per_pair: dict[str, pd.Series] = {}
    latest_rows: list[dict] = []
    for h, a in pairs.items():
        if h not in h_closes.columns or a not in a_closes.columns:
            continue
        hs = h_closes[h].dropna()
        as_ = a_closes[a].dropna()
        if hs.empty or as_.empty:
            continue
        df = pd.concat(
            {"h": hs, "a": as_, "fx": cny_per_hkd}, axis=1, join="inner"
        ).dropna()
        if df.empty:
            continue
        h_in_cny = df["h"] * df["fx"]
        ratio = df["a"] / h_in_cny
        prem = ((ratio - 1.0) * 100.0).dropna()
        prem = prem[prem.index.notna()]
        if prem.empty:
            continue
        per_pair[h] = prem
        latest_rows.append({
            "h": h, "a": a,
            "name": names.get(h, h),
            "premium_pct": round(float(prem.iloc[-1]), 1),
        })

    if len(per_pair) < 3:
        return None

    # equal-weight basket = row-mean of the aligned per-pair premium frame
    basket = pd.concat(per_pair, axis=1).sort_index().mean(axis=1).dropna()
    if basket.empty:
        return None

    latest = float(basket.iloc[-1])
    chg_1y = None
    if len(basket) > 252:
        chg_1y = round(latest - float(basket.iloc[-253]), 1)

    span = f"{basket.index.min().strftime('%Y-%m')} -> {basket.index.max().strftime('%Y-%m')}"

    return {
        "premium_pct": round(latest, 1),
        "pctile": _pctile(basket, latest),
        "chg_1y": chg_1y,
        "n_pairs": len(per_pair),
        "span": span,
        "pairs": sorted(latest_rows, key=lambda r: r["premium_pct"], reverse=True),
        "chart": _series(basket, last_days=1130, ndigits=1),   # ~3y line
    }


if __name__ == "__main__":
    res = ah_basket()
    if res is None:
        print("ah_basket(): None (fewer than 3 pairs resolved)")
    else:
        print(f"computed AH basket: {res['premium_pct']}%  "
              f"(pctile {res['pctile']}, 1y chg {res['chg_1y']}, "
              f"{res['n_pairs']} pairs, {res['span']})")
        print(f"chart points: {len(res['chart']['dates'])}")
        for p in res["pairs"]:
            print(f"  {p['h']:>9}  {p['premium_pct']:>7}%  {p['name']}")
