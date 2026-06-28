"""Theme-discovery radar — a CANDIDATE GENERATOR for emerging thematic baskets (multi-market).

DISPLAY-ONLY, human-curated. It does NOT trade, score, or auto-add anything. It scans an
equity cross-section for cohesive groups of names that (a) move together strongly, (b)
are TIGHTENING (rising co-movement = a theme forming), (c) are NOT already repackaged
existing exposure (low overlap with our thematic baskets and not just one GICS sector), and
(d) optionally have a recent-IPO cluster (a new-listing wave often marks a nascent theme).
It surfaces those groups for a human to consider curating into membership.json.

HONEST BY CONSTRUCTION (and confirmed by scripts/theme_discovery_phase0.py + the research):
  * detection is feasible but NOISY — ~half of flags are coherent persistent themes;
  * EARLY-ENTRY return edge ≈ 0 and is NEGATIVELY skewed if you buy the stretched names
    (thematic baskets/ETFs launch near the top — Ben-David). So this is a WATCHLIST /
    avoid-the-peak / diversification tool, NOT a front-run-the-theme signal.
  * attention/IPO bursts RAISE the bar (hype = late), they do not lower it.

So the output is framed as "candidate themes for review", never a buy list, and the AI
desk's narrative-scout may turn one into a FALSIFIABLE watch-hypothesis (graded later),
never a thesis. Pure/additive — returns None on shortfall, never raises.

REGION SUPPORT. The US path is unchanged (S&P-1500 breadth cache + GICS labels). China /
Canada / Intl reuse their full search-universe close matrices + a sector column for the
novelty test; Hong Kong runs best-effort off the breadth cache and DEGRADES gracefully to
the basket-overlap-only novelty test when no sector map is present (label "New cluster",
novelty unknown). Any region whose caches are absent simply returns None.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "theme_discovery.v1"
_DEFAULTS = {
    "window_d": 126,             # recent co-movement window
    "min_cluster": 5,            # a theme needs a few names
    "max_cluster": 40,           # bigger = a sector/market factor, not a theme
    "dist_threshold": 0.55,      # 1 - corr distance cut for fcluster (≈ corr ≥ 0.45 to link)
    "min_cohesion": 0.45,        # mean pairwise corr to qualify
    "min_cohesion_chg": 0.03,    # must be TIGHTENING vs the prior window
    "max_basket_overlap": 0.50,  # >half already in a basket → repackaged, skip
    "max_sector_share": 0.80,    # one GICS sector dominates → it's a sector, not a novel theme
    "ipo_lookback_d": 547,       # ~18m for the new-listing-wave corroboration
    "top_k": 6,                  # candidates surfaced
}

REGIONS = ("us", "china", "hk", "canada", "intl")

# region → (engine module, membership accessor) for the "already-basketed" overlap test.
_MEMBERSHIP_SRC = {
    "us": ("engine.baskets", "_membership"),
    "china": ("engine.baskets_china", "_membership"),
    "hk": ("engine.baskets_hk", "_membership"),
    "canada": ("engine.baskets_canada", "_membership"),
    "intl": ("engine.baskets_intl", "_membership"),
}

# region → (closes parquet rel-path, members parquet rel-path | None). US is special-cased
# (it reads the breadth caches via engine.equity_factors); HK has no sector map → None.
_REGION_CACHE = {
    "china": ("china_search/closes.parquet", "china_search/members.parquet"),
    "canada": ("canada_search/closes.parquet", "canada_search/members.parquet"),
    "intl": ("intl_search/closes.parquet", "intl_search/members.parquet"),
    "hk": ("hk_breadth/_closes_cache.parquet", None),
}


def _cfg(cfg: dict | None = None) -> dict:
    if cfg is not None:
        return {**_DEFAULTS, **cfg}
    try:
        return {**_DEFAULTS, **(config.load().get("engine", {}).get("theme_discovery") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def _basket_members(region: str = "us") -> set[str]:
    mod_name, fn_name = _MEMBERSHIP_SRC.get(region, _MEMBERSHIP_SRC["us"])
    try:
        import importlib
        mem = getattr(importlib.import_module(mod_name), fn_name)() or {}
        b = mem.get("baskets") or {}
        items = b.items() if isinstance(b, dict) else [(x.get("id"), x) for x in b]
        return {str(m["ticker"]).upper() for _bid, v in items
                for m in (v.get("members") or []) if m.get("ticker")}
    except Exception:  # noqa: BLE001
        return set()


def _recent_ipos(lookback_d: int, asof: pd.Timestamp) -> set[str]:
    try:
        p = config.data_dir() / "ipo" / "calendar.parquet"
        if not p.exists():
            return set()
        ipo = pd.read_parquet(p)
        col = "priced_date" if "priced_date" in ipo.columns else "expected_date"
        d = pd.to_datetime(ipo[col], errors="coerce")
        cut = asof - pd.Timedelta(days=lookback_d)
        recent = ipo[(d >= cut) & (d <= asof)]
        return {str(t).upper() for t in recent["ticker"].dropna()}
    except Exception:  # noqa: BLE001
        return set()


def _names_sectors_from_parquet(rel: str) -> dict[str, tuple[str, str, str]]:
    """Build {TICKER: (name, sector, name_zh)} from a regional search members.parquet. The
    ticker is the index (or a 'ticker'/'symbol' column); `name` prefers an English/display
    name; `name_zh` carries the native (e.g. Chinese) name when the cache has one, so CJK
    markets can render full local names ('' otherwise). sector falls back to '—' when absent.
    Names are kept full (no truncation). Best-effort; never raises."""
    out: dict[str, tuple[str, str, str]] = {}
    try:
        p = config.data_dir() / rel
        if not p.exists():
            return out
        df = pd.read_parquet(p)
        tcol = next((c for c in ("ticker", "symbol", "code") if c in df.columns), None)
        ncol = next((c for c in ("name_en", "name", "name_zh") if c in df.columns), None)
        zcol = "name_zh" if "name_zh" in df.columns else None
        scol = "sector" if "sector" in df.columns else None
        for idx, row in df.iterrows():
            t = str(row[tcol] if tcol else idx).upper()
            name = str(row[ncol]) if ncol and pd.notna(row.get(ncol)) else t
            name_zh = str(row[zcol]) if zcol and pd.notna(row.get(zcol)) else ""
            sec = str(row[scol]) if scol and pd.notna(row.get(scol)) else "—"
            out.setdefault(t, (name, sec or "—", name_zh))
    except Exception as e:  # noqa: BLE001
        log.warning("theme_discovery: members parquet %s unreadable (%s)", rel, e)
    return out


def _universe(region: str) -> tuple[pd.DataFrame | None, dict[str, tuple[str, str, str]]]:
    """Return (closes [Date × ticker], {TICKER: (name, sector, name_zh)}) for a region, or
    (None, {}). name_zh is '' where the market has no native name (e.g. US)."""
    if region == "us":
        try:
            from engine.equity_factors import _closes, _names_sectors
            return _closes(), {str(k).upper(): (v[0], v[1], "")
                               for k, v in (_names_sectors() or {}).items()}
        except Exception as e:  # noqa: BLE001
            log.warning("theme_discovery: US universe load failed (%s)", e)
            return None, {}
    spec = _REGION_CACHE.get(region)
    if not spec:
        return None, {}
    closes_rel, members_rel = spec
    try:
        p = config.data_dir() / closes_rel
        if not p.exists():
            return None, {}
        closes = pd.read_parquet(p)
        closes.index = pd.DatetimeIndex(closes.index)
        closes = closes.sort_index()
        closes.columns = [str(c).upper() for c in closes.columns]
    except Exception as e:  # noqa: BLE001
        log.warning("theme_discovery: %s closes unreadable (%s)", region, e)
        return None, {}
    ns = _names_sectors_from_parquet(members_rel) if members_rel else {}
    return closes, ns


def _mean_offdiag(c: np.ndarray) -> float:
    n = c.shape[0]
    if n < 2:
        return float("nan")
    return float((np.nansum(c) - np.trace(c)) / (n * (n - 1)))


def _cluster(R: pd.DataFrame, cfg: dict) -> list[list[str]]:
    """Correlation-distance hierarchical clustering → list of ticker groups in size band."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    corr = R.corr().clip(-1, 1)
    d = (1.0 - corr.to_numpy())
    np.fill_diagonal(d, 0.0)
    d = (d + d.T) / 2.0                                   # enforce symmetry for squareform
    try:
        Z = linkage(squareform(d, checks=False), method="average")
    except Exception:  # noqa: BLE001
        return []
    labels = fcluster(Z, t=float(cfg["dist_threshold"]), criterion="distance")
    out = []
    for lab in set(labels):
        members = [corr.columns[i] for i in range(len(labels)) if labels[i] == lab]
        if cfg["min_cluster"] <= len(members) <= cfg["max_cluster"]:
            out.append(members)
    return out


def discover_candidates(region: str = "us", root=None, cfg: dict | None = None,
                        asof=None) -> dict | None:
    """Scan a market's cross-section for candidate emerging themes. Region-parameterized:
    US uses the S&P-1500 breadth cache + GICS labels; China/Canada/Intl reuse their full
    search-universe close matrices + a sector column; HK degrades to overlap-only novelty
    (no sector map). Returns None where the region's caches are absent."""
    region = (region or "us").lower()
    if region not in REGIONS:
        return None
    c = _cfg(cfg)
    try:
        closes, ns = _universe(region)
        if closes is None or closes.empty:
            return None
        if asof is not None:
            closes = closes.loc[:pd.Timestamp(asof)]
        members = _basket_members(region)
        has_sectors = sum(1 for v in ns.values() if v[1] not in ("—", "", "nan")) >= 10
        win = int(c["window_d"])
        R = closes.pct_change(fill_method=None).tail(win)
        R = R.dropna(axis=1, thresh=int(win * 0.8))
        Rp = closes.pct_change(fill_method=None).iloc[-2 * win:-win]   # prior window (change-point)
        if R.shape[1] < 30 or len(R) < win // 2:
            return None
        asof_ts = R.index.max()
        ipos = _recent_ipos(int(c["ipo_lookback_d"]), asof_ts) if region == "us" else set()

        cands = []
        for grp in _cluster(R, c):
            sub = R[grp]
            cohesion = _mean_offdiag(sub.corr().to_numpy())
            if not np.isfinite(cohesion) or cohesion < c["min_cohesion"]:
                continue
            prev_cols = [g for g in grp if g in Rp.columns]
            prev = _mean_offdiag(Rp[prev_cols].corr().to_numpy()) if len(prev_cols) >= 3 else np.nan
            coh_chg = (cohesion - prev) if np.isfinite(prev) else 0.0
            if coh_chg < c["min_cohesion_chg"]:
                continue
            overlap = sum(1 for g in grp if g in members) / len(grp)
            if overlap > c["max_basket_overlap"]:
                continue
            secs = Counter(ns.get(g, (g, "—", ""))[1] for g in grp)
            top_sec, top_n = secs.most_common(1)[0]
            top_share = top_n / len(grp)
            if not has_sectors:
                # no sector map for this region → novelty unknown; rely on overlap + cohesion.
                novel, label = True, "New cluster"
            else:
                novel = top_share < c["max_sector_share"]   # cross-sector = novel theme
                label = "Cross-sector" if novel else top_sec
                covered = overlap > 0.25                     # partly tracked already
                if not novel and covered:
                    continue                                 # a sector we already basket → skip
            ipo_hits = [g for g in grp if g in ipos]
            # recent EW momentum (context only)
            mom = float((1.0 + sub.mean(axis=1)).prod() - 1.0)
            names = [{"ticker": g, "name": ns.get(g, (g, "—", ""))[0],
                      "name_zh": ns.get(g, (g, "—", ""))[2],
                      "sector": ns.get(g, (g, "—", ""))[1]} for g in grp]
            names.sort(key=lambda x: x["ticker"])
            cands.append({
                "n": len(grp), "cohesion": round(cohesion, 3),
                "cohesion_chg": round(coh_chg, 3),
                "label": label,
                "top_sector": top_sec, "top_sector_share": round(top_share, 2),
                "basket_overlap": round(overlap, 2),
                "recent_ipos": sorted(ipo_hits), "ipo_wave": len(ipo_hits) >= 2,
                "mom_window": round(mom, 3), "constituents": names[:14],
            })
        cands.sort(key=lambda x: (-x["cohesion_chg"], -x["cohesion"]))
        cands = cands[: int(c["top_k"])]
        return {
            "schema": SCHEMA, "is_context_only": True, "region": region,
            "as_of": asof_ts.strftime("%Y-%m-%d"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_universe": int(R.shape[1]), "window_d": win,
            "has_sector_map": bool(has_sectors),
            "candidates": cands,
            "verdict": "display_only_candidate_radar",
            "note": ("Coherent, TIGHTENING groups of names not already covered by a basket — "
                     "CANDIDATES for human review, not a buy list. Detection is noisy (~half are "
                     "real, persistent themes) and early-entry return edge is ~0 and negatively "
                     "skewed (themes launch near the top). Use for the watchlist / avoid-the-peak, "
                     "not to front-run. IPO waves RAISE the bar (hype = late)."),
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme_discovery failed: %s", e)
        return None
