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


def _per_pair_premiums() -> tuple[dict[str, pd.Series], list[dict]] | None:
    """Shared core: per dual-listed pair, the computed A/H premium SERIES (1:1
    share-equivalence; lean on trend/percentile, not the absolute level). Returns
    (per_pair {H-ticker -> premium% series}, latest_rows) or None if the inputs are
    missing. Single source of truth for ah_basket / ah_basket_series."""
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
    return per_pair, latest_rows


def ah_basket_series() -> pd.Series | None:
    """The equal-weight computed A/H premium basket as a daily SERIES (the input the
    hk_conditions RORO leg z-scores). None if fewer than 3 pairs resolve."""
    res = _per_pair_premiums()
    if res is None:
        return None
    per_pair, _ = res
    if len(per_pair) < 3:
        return None
    basket = pd.concat(per_pair, axis=1).sort_index().mean(axis=1).dropna()
    return basket if not basket.empty else None


def ah_basket() -> dict | None:
    res = _per_pair_premiums()
    if res is None:
        return None
    per_pair, latest_rows = res
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


def ah_by_ticker() -> dict[str, dict]:
    """Per dual-listed H-share: its A/H premium TODAY, the percentile within that pair's
    OWN history, the 1-year change, and the A twin — for the per-stock A/H panel on the
    HK analyzer. Keyed by H-share ticker (e.g. ``0939.HK``). Empty dict if the inputs are
    missing, so the caller silently hides the panel. Same computed-premium method as
    ``ah_basket`` (1:1 share-equivalence; lean on the trend/percentile, not the level)."""
    cfg = config.load().get("hk", {})
    pairs = cfg.get("ah_pairs") or {}
    names = cfg.get("names") or {}
    if not pairs:
        return {}
    try:
        h_closes = pd.read_parquet(config.data_dir() / "hk_breadth" / "_closes_cache.parquet")
    except (FileNotFoundError, OSError):
        return {}
    a_closes = store.read("china_search", "closes")
    cny = store.read("china", "CNY=X")
    hkd = store.read("hk", "HKD=X")
    if h_closes is None or h_closes.empty or a_closes is None or a_closes.empty:
        return {}
    if cny is None or hkd is None or "close" not in cny.columns or "close" not in hkd.columns:
        return {}
    cny_per_hkd = (cny["close"].dropna() / hkd["close"].dropna()).dropna()
    if cny_per_hkd.empty:
        return {}
    out: dict[str, dict] = {}
    for h, a in pairs.items():
        if h not in h_closes.columns or a not in a_closes.columns:
            continue
        df = pd.concat({"h": h_closes[h].dropna(), "a": a_closes[a].dropna(),
                        "fx": cny_per_hkd}, axis=1, join="inner").dropna()
        if df.empty:
            continue
        prem = ((df["a"] / (df["h"] * df["fx"]) - 1.0) * 100.0).dropna()
        prem = prem[prem.index.notna()]
        if prem.empty:
            continue
        latest = float(prem.iloc[-1])
        chg_1y = round(latest - float(prem.iloc[-253]), 1) if len(prem) > 252 else None
        out[h] = {
            "premium_pct": round(latest, 1),
            "pctile": _pctile(prem, latest),
            "chg_1y": chg_1y,
            "a": a, "name": names.get(h, h),
            "span": f"{prem.index.min():%Y-%m} -> {prem.index.max():%Y-%m}",
        }
    return out



# ---------------------------------------------------------------------------
# Panel reader (masterplan §3 H3, W01A)
# Read data/hk_ah_panel/ produced by scripts/build_ah_panel.py.
# OPTIONAL: if panel not yet on disk, all functions return None/[].
# Existing ah_basket / ah_by_ticker / ah_basket_series are UNCHANGED.
# ---------------------------------------------------------------------------

def _panel_premium():
    """Wide A/H premium panel (date x H-ticker, fractional NOT percent)."""
    path = config.data_dir() / "hk_ah_panel" / "premium.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception:
        return None


def _panel_pairs():
    """Load pairs.json metadata. Returns empty list if not present."""
    import json
    path = config.data_dir() / "hk_ah_panel" / "pairs.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def panel_equal_weight_basket():
    """Equal-weight mean of all valid pair premiums from the deep 25-pair panel.
    Values are FRACTIONAL (0.30 = 30%); returns None if panel unavailable."""
    panel = _panel_premium()
    if panel is None or panel.empty:
        return None
    basket = panel.mean(axis=1).dropna()
    return basket if not basket.empty else None


def panel_pair_premiums(h_tickers=None, since=None):
    """Wide panel of per-pair premiums (fractional) from the deep store.
    Optionally filtered to specific H-tickers or a start date."""
    panel = _panel_premium()
    if panel is None or panel.empty:
        return None
    if h_tickers:
        cols = [c for c in h_tickers if c in panel.columns]
        if not cols:
            return None
        panel = panel[cols]
    if since:
        panel = panel[panel.index >= pd.Timestamp(since)]
    return panel if not panel.empty else None


def panel_summary():
    """Summary dict for the deep panel. Returns None if panel not built yet."""
    panel = _panel_premium()
    pairs = _panel_pairs()
    if panel is None or panel.empty:
        return None
    cutoffs = {"2005": "2005-01-01", "2010": "2010-01-01",
               "2015": "2015-01-01", "2020": "2020-01-01"}
    depth = {}
    for label, iso in cutoffs.items():
        depth["pairs_reaching_" + label] = sum(
            1 for m in pairs
            if m.get("joint_start") and m["joint_start"] <= iso
        )
    latest_nonnan = panel.iloc[-1].dropna()
    return {
        "n_pairs_total": len(panel.columns),
        "n_pairs_today": len(latest_nonnan),
        "date_start": str(panel.index.min().date()),
        "date_end": str(panel.index.max().date()),
        "depth": depth,
        "latest_mean_prem_pct": round(float(latest_nonnan.mean()) * 100, 1) if not latest_nonnan.empty else None,
        "latest_median_prem_pct": round(float(latest_nonnan.median()) * 100, 1) if not latest_nonnan.empty else None,
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

    print("")
    print("--- deep panel reader (new W01A store) ---")
    summary = panel_summary()
    if summary is None:
        print("panel_summary(): None (data/hk_ah_panel/ not built yet)")
    else:
        print(f"panel: {summary['n_pairs_total']} pairs, "
              f"{summary['date_start']} -> {summary['date_end']}")
        print(f"today: {summary['n_pairs_today']} pairs, "
              f"mean premium {summary['latest_mean_prem_pct']}%, "
              f"median {summary['latest_median_prem_pct']}%")
        for k, v in summary["depth"].items():
            print(f"  {k}: {v} pairs")
