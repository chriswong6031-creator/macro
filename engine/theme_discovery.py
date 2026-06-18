"""Theme-discovery radar — a CANDIDATE GENERATOR for emerging thematic baskets (US).

DISPLAY-ONLY, human-curated. It does NOT trade, score, or auto-add anything. It scans the
US equity cross-section for cohesive groups of names that (a) move together strongly, (b)
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


def _cfg(cfg: dict | None = None) -> dict:
    if cfg is not None:
        return {**_DEFAULTS, **cfg}
    try:
        return {**_DEFAULTS, **(config.load().get("engine", {}).get("theme_discovery") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def _basket_members() -> set[str]:
    try:
        from engine.baskets import _membership
        mem = _membership() or {}
        b = mem.get("baskets") or {}
        items = b.items() if isinstance(b, dict) else [(x["id"], x) for x in b]
        return {m["ticker"] for _bid, v in items for m in v.get("members", [])}
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
    """Scan the US cross-section for candidate emerging themes. region!='us' → None for now
    (US has the GICS sector map needed for the novelty test; regional discovery is a follow-up)."""
    if region != "us":
        return None
    c = _cfg(cfg)
    try:
        from engine.equity_factors import _closes, _names_sectors
        closes = _closes()
        if closes is None or closes.empty:
            return None
        if asof is not None:
            closes = closes.loc[:pd.Timestamp(asof)]
        ns = _names_sectors()
        members = _basket_members()
        win = int(c["window_d"])
        R = closes.pct_change(fill_method=None).tail(win)
        R = R.dropna(axis=1, thresh=int(win * 0.8))
        Rp = closes.pct_change(fill_method=None).iloc[-2 * win:-win]   # prior window (change-point)
        if R.shape[1] < 30 or len(R) < win // 2:
            return None
        asof_ts = R.index.max()
        ipos = _recent_ipos(int(c["ipo_lookback_d"]), asof_ts)

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
            secs = Counter(ns.get(g, (g, "—"))[1] for g in grp)
            top_sec, top_n = secs.most_common(1)[0]
            top_share = top_n / len(grp)
            novel = top_share < c["max_sector_share"]      # cross-sector = novel theme
            covered = overlap > 0.25                        # partly tracked already
            if not novel and covered:
                continue                                    # a sector we already basket → skip
            ipo_hits = [g for g in grp if g in ipos]
            # recent EW momentum (context only)
            mom = float((1.0 + sub.mean(axis=1)).prod() - 1.0)
            names = [{"ticker": g, "name": ns.get(g, (g, ""))[0][:24],
                      "sector": ns.get(g, (g, "—"))[1]} for g in grp]
            names.sort(key=lambda x: x["ticker"])
            cands.append({
                "n": len(grp), "cohesion": round(cohesion, 3),
                "cohesion_chg": round(coh_chg, 3),
                "label": ("Cross-sector" if novel else top_sec),
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
            "candidates": cands,
            "verdict": "display_only_candidate_radar",
            "note": ("Coherent, TIGHTENING groups of US names not already covered by a basket — "
                     "CANDIDATES for human review, not a buy list. Detection is noisy (~half are "
                     "real, persistent themes) and early-entry return edge is ~0 and negatively "
                     "skewed (themes launch near the top). Use for the watchlist / avoid-the-peak, "
                     "not to front-run. IPO waves RAISE the bar (hype = late)."),
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme_discovery failed: %s", e)
        return None
