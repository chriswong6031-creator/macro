"""China Divergence Radar — falsifiable accountability ledger.

LEAF · DISPLAY-ONLY. Accrues each fired divergence on its fire date (keep-FIRST, one entry
per pair per month so re-runs don't double-count) into data/china_radar/ledger.parquet, then
resolves matured entries (~63 trading days ≈ 90 calendar days later) by measuring the sector
ETF's realized relative return vs CSI 300 and marking the hypothesis hit/miss. Honest
accountability — proves whether the radar's calls hold; never a score or a trade. Never raises.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "china_radar_ledger.v1"
HORIZON_DAYS = 90
_COLUMNS = ("event_id", "fired_date", "pair", "signal_key", "family",
            "sector_etf", "sector_en", "sector_zh", "sign", "rs_at_fire", "signal_value")


def _path() -> Path:
    p = config.data_dir() / "china_radar" / "ledger.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def accrue(scan: dict | None, asof: date | str | None = None) -> dict | None:
    """Append fired divergences (keep-FIRST, one per pair per month). Returns a summary."""
    try:
        import pandas as pd
        if not scan or not scan.get("divergences"):
            return None
        asof = str(asof or scan.get("asof") or date.today())
        month = asof[:7]
        recs = []
        for d in scan["divergences"]:
            recs.append({
                "event_id": f"{d['pair']}|{month}", "fired_date": asof,
                "pair": d["pair"], "signal_key": d["signal_key"],
                # family tag: "venue" for cross-venue pairs, None for legacy sector pairs
                # (existing rows on disk carry None and are unaffected)
                "family": d.get("family"),
                "sector_etf": d.get("sector_etf"), "sector_en": d["sector_en"],
                "sector_zh": d.get("sector_zh", d["sector_en"]),
                "sign": d["sign"], "rs_at_fire": d.get("price_rs"),
                "signal_value": d.get("signal_value"),
            })
        new = pd.DataFrame(recs, columns=list(_COLUMNS))
        path = _path()
        old = pd.read_parquet(path) if path.exists() else None
        if old is not None and len(old):
            merged = pd.concat([old.reindex(columns=list(_COLUMNS)), new], ignore_index=True)
        else:
            merged = new
        merged = merged.drop_duplicates(subset=["event_id"], keep="first")
        merged = merged.sort_values(["fired_date", "pair"]).reset_index(drop=True)
        merged.to_parquet(path, index=False)
        return {"n_total": int(len(merged)), "n_new": int(len(merged) - (0 if old is None else len(old)))}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_radar_ledger.accrue failed (%s)", e)
        return None


def _fwd_rel(etf: str | None, fired: str, horizon: int = HORIZON_DAYS):
    """Realized sector-vs-CSI300 relative return from `fired` to fired+horizon. None if young.

    Returns None for venue pairs (etf is None) — venue grading is a future extension
    (each venue pair has a different outcome metric; deferred until n_resolved >= 3).
    """
    if not etf:
        return None   # venue pairs: no ETF-vs-benchmark grading path yet
    try:
        from engine.china_radar import BENCH
        a = store.read("china", etf)
        b = store.read("china", BENCH)
        if a is None or b is None:
            return None
        import pandas as pd
        ca, cb = a["close"].dropna(), b["close"].dropna()
        f = pd.Timestamp(fired)
        end = f + pd.Timedelta(days=horizon)
        if ca.index.max() < end:
            return None                          # not matured yet
        def at(s, d):
            sub = s[s.index <= d]
            return float(sub.iloc[-1]) if len(sub) else None
        a0, a1 = at(ca, f), at(ca, end)
        b0, b1 = at(cb, f), at(cb, end)
        if None in (a0, a1, b0, b1) or a0 <= 0 or b0 <= 0:
            return None
        return round(((a1 / a0) - (b1 / b0)) * 100, 2)
    except Exception:  # noqa: BLE001
        return None


def track_record() -> dict | None:
    """Resolve matured entries → hit/miss + hit rate. Display-only. Never raises."""
    try:
        import pandas as pd
        path = _path()
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return None
        rows, hits, resolved = [], 0, 0
        for r in df.itertuples():
            fwd = _fwd_rel(r.sector_etf, r.fired_date)
            status, hit = "open", None
            if fwd is not None:
                resolved += 1
                hit = (fwd > 0) if r.sign == "positive" else (fwd < 0)
                hits += 1 if hit else 0
                status = "hit" if hit else "miss"
            rows.append({"fired_date": r.fired_date, "pair": r.pair,
                         "signal_key": r.signal_key,
                         "family": getattr(r, "family", None),
                         "sector_en": r.sector_en,
                         "sector_zh": (getattr(r, "sector_zh", None) or r.sector_en),
                         "sign": r.sign, "rs_at_fire": r.rs_at_fire,
                         "fwd_rel": fwd, "status": status})
        rows.sort(key=lambda x: x["fired_date"], reverse=True)
        return {
            "schema": SCHEMA, "is_context_only": True,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "n_total": int(len(df)), "n_resolved": resolved,
            "n_open": int(len(df)) - resolved,
            "hit_rate": round(hits / resolved, 2) if resolved else None,
            "rows": rows,
        }
    except Exception as e:  # noqa: BLE001
        log.error("china_radar_ledger.track_record failed (%s)", e)
        return None
