"""B2 member-conviction accrual — the PIT ledger LABEL_FALTERING_PHASE0 §2 B2 needs.

The pre-registered B2 study ("does a collapse of the member conviction.potential
median LEAD theme-level forward drawdown, out-of-sample?") returned
`no_pit_history_accrue` (data/strategies/baskets_calibration.json →
conviction_demotion_fit): no source carries a dated history of per-basket
member-conviction medians, so the study cannot run. This module IS the accrual
that verdict pre-committed: at render time, archive daily — per basket and per
region — {member conviction.potential median, IQR, n_members, theme score,
label} into data/signal_archive/conviction_<region>.parquet via
engine.signal_archive.archive_snapshot (append-only, keep-first per as-of date).

Re-run bar (pre-registered): >= 180 archived trading days (~2027-04), gates in
research/LABEL_FALTERING_PHASE0.md §2 unchanged. Until then this is a WRITE-ONLY
research ledger: display/research-only, never read back into any score —
_label() / _reco() / allocate() stay untouched.

Callers are the five library builders (scripts/build_*_library.py), each wrapped
best-effort so a failure here can never break a build. Membership comes from the
SAME region loaders the allocation engine uses (narrative_rotation._region_cfg),
so the archived stats cover exactly the member set the theme pages score; theme
score/label are joined from the freshest rendered theme_intel snapshot, whose
own as-of is recorded beside the row as `theme_asof` (an earlier-in-the-pipeline
basket build can be a session behind the library build — recorded, not hidden).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from engine import signal_archive
from lib import config

log = logging.getLogger(__name__)

# region id -> the rendered basket-page JSON carrying theme_intel (score/label).
# US also has the slim data/baskets/latest.json score snapshot, preferred in
# _theme_meta (it is the exact payload the "baskets" archive stream records).
_SITE_BASKET_JSON = {
    "us": "basketdata/baskets.json",
    "china": "chinabasketdata/baskets.json",
    "hk": "hkbasketdata/baskets.json",
    "canada": "canadabasketdata/baskets.json",
    "intl": "intlbasketdata/baskets.json",
}


def _theme_meta(region: str) -> tuple[dict, str | None]:
    """{basket_id: {score, label}} from the freshest theme snapshot, + its as_of.
    Best-effort: ({}, None) when neither source resolves — the conviction stats
    still archive (they are the study's primary series), just without the join."""
    themes: list = []
    asof = None
    if region == "us":
        try:
            slim = json.loads((config.data_dir() / "baskets" / "latest.json").read_text())
            themes, asof = slim.get("themes") or [], slim.get("as_of")
        except Exception:  # noqa: BLE001 — fall through to the site payload
            pass
    if not themes:
        try:
            page = json.loads((config.ROOT / "site" / _SITE_BASKET_JSON[region]).read_text())
            ti = page.get("theme_intel") or {}
            themes, asof = ti.get("themes") or [], ti.get("as_of")
        except Exception:  # noqa: BLE001 — join degrades to None, stats still archive
            pass
    meta: dict[str, dict] = {}
    for t in themes:
        if isinstance(t, dict) and t.get("id"):
            meta[str(t["id"])] = {"score": t.get("score"), "label": t.get("label")}
    return meta, (signal_archive.normalize_asof(asof) or None)


def _stats(vals: list[float]) -> dict:
    """Median + IQR of the member potential scores (the two pre-registered stats)."""
    if not vals:
        return {"median": None, "iqr": None}
    arr = np.asarray(vals, dtype=float)
    return {"median": round(float(np.median(arr)), 2),
            "iqr": round(float(np.percentile(arr, 75) - np.percentile(arr, 25)), 2)}


def archive_member_conviction(region: str, profiles: dict, *, asof: str | None = None,
                              archive_dir: str | Path | None = None) -> bool:
    """Append today's per-basket member-conviction row for `region` (keep-first).

    profiles: {ticker: conviction-profile dict} exactly as the library builders
    hold it in memory after the potential attach — the score is read from
    profile["potential"]["score"]. Returns True when a new row was written,
    False on a keep-first no-op or no usable data (an empty/degenerate build
    never imprints a zero row under keep-first). May raise on genuinely broken
    I/O — call sites wrap (best-effort, never fatal)."""
    from engine.narrative_rotation import _region_cfg  # deferred: heavy import chain
    cfg = _region_cfg(region)
    if not cfg:
        return False
    mem = cfg["membership"]() or {}
    bdict = mem.get("baskets") or {}
    items = list(bdict.items()) if isinstance(bdict, dict) else \
        [(b.get("id"), b) for b in bdict if isinstance(b, dict)]
    if not items:
        return False
    pot: dict[str, float] = {}
    for t, p in (profiles or {}).items():
        s = ((p or {}).get("potential") or {}).get("score") if isinstance(p, dict) else None
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            pot[str(t)] = float(s)
    if not pot:
        return False
    theme_meta, theme_asof = _theme_meta(region)
    baskets: dict[str, dict] = {}
    union: dict[str, float] = {}          # region roll-up dedups cross-basket members
    union_total: set[str] = set()
    for bid, b in items:
        members = [str(m.get("ticker")) for m in (b.get("members") or []) if m.get("ticker")]
        scored = [pot[t] for t in members if t in pot]
        union_total.update(members)
        union.update({t: pot[t] for t in members if t in pot})
        tm = theme_meta.get(str(bid)) or {}
        baskets[str(bid)] = {**_stats(scored), "n": len(scored), "n_total": len(members),
                             "theme_score": tm.get("score"), "label": tm.get("label")}
    asof = signal_archive.normalize_asof(asof) or \
        datetime.now(timezone.utc).date().isoformat()
    snap = {"as_of": asof, "region": region, "theme_asof": theme_asof,
            "n_baskets": len(baskets),
            **_stats(list(union.values())),
            "n": len(union), "n_total": len(union_total),
            "baskets": baskets}
    return signal_archive.archive_snapshot(f"conviction_{region}", snap, asof,
                                           archive_dir=archive_dir)
