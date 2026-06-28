"""Subsector radar — the bottleneck x revision signature over the FULL Finviz taxonomy
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §6; data/sp500_heatmap/industry_map.json).

WHY. The cascade runs over 18 hand-curated themes. The desk also has a practitioner-grade
classification of the whole S&P 500 — 503 names -> 11 sectors -> 113 sub-industries
(data/sp500_heatmap/industry_map.json, the Finviz heatmap source). These names have analyst
coverage (so T4 revision breadth is real) and EDGAR filings (so the scarcity-language read is
real), which makes them a clean, comprehensive universe to run the desk's core signature over.

This engine generalises the cascade from 18 themes to all 113 sub-industries: for each it rolls
up revision breadth (REUSING engine.theme_revisions.theme_revisions_for over the same
data/revisions store) and counts members reporting manufacturing-SPECIFIC scarcity language
(REUSING the market-wide sweep in data/edgar/emergence_hits.parquet), then applies the cascade
STAGE logic. It is the systematic-coverage complement to engine.theme_emergence (which finds
UNTRACKED small-cap clusters): this scans the KNOWN S&P 500 at sub-industry granularity so you
can see, market-wide, WHERE supply scarcity and estimate revisions are aligning.

HONEST. The bottleneck here is a TEXT-ONLY proxy (EDGAR scarcity language), not a FRED
physical confirmation — so a "PRECIPICE" on this radar is a screen to investigate, not a
confirmed thesis (it would carry the text-only score cap in the curated cascade). DISPLAY-ONLY,
forward-graded, None on shortfall.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

MIN_MEMBERS = 3            # need a few names in the sub-industry
MIN_COVERED = 3           # >= this many analyst-COVERED names — else breadth is a 1-2 name read,
                          # and a "PRECIPICE" on no revision data is a text-only mirage (not ledgered)
MIN_SCARCITY = 2          # >= this many distinct members on scarcity language = a subsector signal
SCARCITY_RECENT_DAYS = 180
TOP_N = 24                # surfaced on the page (full set stays in the JSON)


def _industry_map() -> dict | None:
    """{(sector, sub_industry): [tickers]} from the Finviz classification. None if absent."""
    p = config.data_dir() / "sp500_heatmap" / "industry_map.json"
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("industry_map unreadable: %s", e)
        return None
    groups: dict[tuple[str, str], list[str]] = {}
    for tk, rec in (raw or {}).items():
        if not isinstance(rec, dict):
            continue
        key = (rec.get("sector") or "—", rec.get("sub_industry") or "—")
        groups.setdefault(key, []).append(tk)
    return groups or None


def _scarcity_members() -> set[str]:
    """Distinct tickers reporting manufacturing-SPECIFIC scarcity language recently
    (reuses the market-wide sweep). Empty set if the cache is absent."""
    p = config.data_dir() / "edgar" / "emergence_hits.parquet"
    if not p.exists():
        return set()
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return set()
    if df is None or df.empty or "phrase" not in df.columns or "ticker" not in df.columns:
        return set()
    try:
        from engine.theme_emergence import SPECIFIC_PHRASES
    except Exception:  # noqa: BLE001
        SPECIFIC_PHRASES = set()
    df = df.copy()
    if "file_date" in df.columns:
        df["file_date"] = pd.to_datetime(df["file_date"], errors="coerce")
        if getattr(df["file_date"].dt, "tz", None) is not None:
            df["file_date"] = df["file_date"].dt.tz_localize(None)   # compare tz-naive
        cutoff = pd.Timestamp(date.today() - timedelta(days=SCARCITY_RECENT_DAYS))
        df = df[df["file_date"] >= cutoff]
    df = df[df["phrase"].astype(str).isin(SPECIFIC_PHRASES)]
    return set(df["ticker"].astype(str).unique())


def _scan_rows(imap: dict, latest, hist, scarce: set) -> list[dict]:
    """Pure per-subsector loop: revision rollup x text-scarcity proxy -> STAGE. Ranked by
    edge remaining, scarcity-aligned first, then sharpest |breadth|."""
    from engine import theme_revisions as tr
    from engine.foresight_cascade import _stage, _STAGE_RANK
    rows = []
    for (sector, sub), members in imap.items():
        if len(members) < MIN_MEMBERS:
            continue
        try:
            rev = tr.theme_revisions_for(sub, sub, members, latest, hist)
        except Exception as e:  # noqa: BLE001 — one subsector failing never blocks the rest
            log.warning("subsector_scan[%s] revisions failed: %s", sub, e)
            rev = None
        # require a real revision read (>= MIN_COVERED analyst-covered names) — else breadth is
        # a 1-2 name read and the stage is a text-only mirage. Keeps the radar honest to its
        # "503 names" framing; scarcity-only clusters are the discovery layer's job, not this one.
        if (rev or {}).get("n_covered", 0) < MIN_COVERED:
            continue
        scar_members = sorted(m for m in members if m in scarce)
        n_scar = len(scar_members)
        # text-only bottleneck proxy: >= MIN_SCARCITY distinct members on scarcity language
        bn_proxy = {"band": "TIGHT", "tightness": None} if n_scar >= MIN_SCARCITY else None
        stage, rationale = _stage(bn_proxy, rev)
        rows.append({
            "sector": sector,
            "sub_industry": sub,
            "n_members": len(members),
            "n_covered": (rev or {}).get("n_covered"),
            "breadth": (rev or {}).get("breadth"),
            "level_state": (rev or {}).get("level_state"),
            "est_drift_90d": (rev or {}).get("est_drift_90d"),
            "broadening_state": (rev or {}).get("broadening_state"),
            "n_scarcity": n_scar,
            "scarcity_members": scar_members[:8],
            "stage": stage,
            "rationale": rationale,
            "text_only": True,
        })
    def _key(r):
        b = abs(r["breadth"]) if r["breadth"] is not None else 0.0
        return (_STAGE_RANK.get(r["stage"], 9), 0 if r["n_scarcity"] >= MIN_SCARCITY else 1, -b)
    rows.sort(key=_key)
    return rows


def compute_subsector_scan(write_ledger: bool = True) -> dict | None:
    """Per-subsector bottleneck(text) x revision-breadth STAGE over the 113 Finviz
    sub-industries. DISPLAY-ONLY. None when the taxonomy or revisions store is absent."""
    imap = _industry_map()
    if not imap:
        return None
    try:
        from engine import theme_revisions as tr
        from engine.foresight_cascade import _stage, _STAGE_RANK
    except Exception as e:  # noqa: BLE001
        log.warning("subsector_scan deps unavailable: %s", e)
        return None
    latest = tr._latest()
    if latest is None:
        return None
    hist = tr._history()
    scarce = _scarcity_members()
    rows = _scan_rows(imap, latest, hist, scarce)
    if not rows:
        return None

    payload = {
        "asof": (latest["asof"].max() if "asof" in latest.columns and not latest["asof"].isna().all()
                 else None),
        "n_subsectors": len(rows),
        "n_scarcity_aligned": sum(1 for r in rows if r["n_scarcity"] >= MIN_SCARCITY),
        "subsectors": rows[:TOP_N],
        "all_count": len(rows),
        "note": ("display-only; the cascade signature (text scarcity x revision breadth) over all "
                 "113 Finviz sub-industries. The bottleneck is a TEXT-ONLY proxy (EDGAR scarcity "
                 "language), not FRED-confirmed — a screen to investigate, not a confirmed thesis. "
                 "Complements the curated 18-theme cascade and the small-cap discovery layer."),
    }
    if isinstance(payload["asof"], pd.Timestamp):
        payload["asof"] = str(payload["asof"].date())
    if write_ledger:
        try:
            _append_ledger(payload, rows)
        except Exception as e:  # noqa: BLE001
            log.warning("subsector_scan ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict, rows: list[dict]) -> None:
    """Append-only forward-grading ledger: one row per (sub_industry, asof) for a
    scarcity-aligned PRECIPICE/BROADENING subsector — graded forward (did the subsector
    basket outperform?). Deduped."""
    d = config.data_dir() / "subsector_scan"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("sub_industry"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    ts = datetime.now(timezone.utc).isoformat()
    asof = payload.get("asof")
    lines = []
    for r in rows:
        if (r["stage"] not in ("PRECIPICE", "BROADENING") or r["n_scarcity"] < MIN_SCARCITY
                or (r["sub_industry"], asof) in seen):
            continue
        lines.append(json.dumps({
            "sub_industry": r["sub_industry"], "sector": r["sector"], "asof": asof, "ts": ts,
            "stage": r["stage"], "breadth": r["breadth"], "n_scarcity": r["n_scarcity"],
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
