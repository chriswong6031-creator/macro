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
    """Append fired divergences (keep-FIRST, one per pair per month). Returns a summary.

    LANE GUARD: only runs in the asia-close nightly lane (CN_LANE=asia env var set by
    .github/workflows/asia-close.yml:89 dashboards step). All other lanes (intraday,
    manual local runs) are no-ops to prevent locally-built rows from freezing the
    nightly event_id dedup for the rest of the month.
    """
    import os
    if os.environ.get("CN_LANE") != "asia":
        path = _path()
        log.debug("china_radar_ledger.accrue: CN_LANE != 'asia' — no-op (ledger unchanged)")
        return {"n_total": int(len(__import__('pandas').read_parquet(path))) if path.exists() else 0, "n_new": 0}
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


def _fwd_venue(pair: str, sign: str, fired: str, horizon: int = HORIZON_DAYS):
    """Realized outcome metric for matured venue entries. Returns float or None.

    Dispatched by pair id:
    - venue_offshore_gap->china: forward (onshore 510300.SS return − offshore equal-weight return)
      graded pass if it moves in the fired direction (onshore catches up after positive fire → convergence).
    - venue_ah_premium->china: forward change of A/H premium toward its 1y trailing mean vs fired sign.
    - venue_southbound->china: forward _HSCE (data/hk) return vs fired sign.

    Returns None if not matured yet.
    """
    try:
        import pandas as pd
        from lib import store
        f = pd.Timestamp(fired)
        end = f + pd.Timedelta(days=horizon)

        def at(s, d):
            sub = s[s.index <= d]
            return float(sub.iloc[-1]) if len(sub) else None

        if pair == "venue_offshore_gap->china":
            # Convergence: onshore return MINUS offshore equal-weight return from fired to end.
            # If positive fire (offshore was leading): pass = onshore outperforms offshore (catches up).
            from lib import config
            csi = store.read("china", "510300.SS")
            if csi is None or "close" not in csi.columns:
                return None
            ca = csi["close"].dropna().sort_index()
            if ca.index.max() < end:
                return None  # not matured
            # offshore equal-weight: need KWEB/MCHI/CQQQ
            OFFSHORE = ["KWEB", "MCHI", "CQQQ"]
            off_rets = []
            for ticker in OFFSHORE:
                df = store.read("yahoo", ticker)
                if df is None:
                    continue
                col = "close" if "close" in df.columns else "close_price"
                if col not in df.columns:
                    continue
                s = df[col].dropna().sort_index()
                s0, s1 = at(s, f), at(s, end)
                if s0 and s1 and s0 > 0:
                    off_rets.append((s1 / s0) - 1.0)
            if not off_rets:
                return None
            on0, on1 = at(ca, f), at(ca, end)
            if None in (on0, on1) or on0 <= 0:
                return None
            on_ret = (on1 / on0) - 1.0
            off_ret_eq = sum(off_rets) / len(off_rets)
            convergence = on_ret - off_ret_eq   # positive = onshore caught up
            return round(convergence * 100, 2)

        elif pair == "venue_ah_premium->china":
            # Forward change of A/H premium toward its 1y trailing mean.
            # If positive fire (premium was elevated): pass = premium reverts lower (toward mean).
            df = store.read("hk_ah_official", "ah_premium")
            if df is None or "hsahp" not in df.columns:
                df = store.read("hk_ah_official", "ah_spot")
            if df is None or "hsahp" not in df.columns:
                return None
            s = pd.to_numeric(df["hsahp"], errors="coerce").dropna().sort_index()
            if s.index.max() < end:
                return None  # not matured
            # 1y mean at fire date
            hist_at_fire = s[s.index <= f].tail(252)
            if len(hist_at_fire) < 60:
                return None
            mean_at_fire = float(hist_at_fire.mean())
            prem_at_fire = at(s, f)
            prem_at_end = at(s, end)
            if None in (prem_at_fire, prem_at_end):
                return None
            # deviation from mean: positive fire = premium was ABOVE mean (z>0)
            dev_at_fire = prem_at_fire - mean_at_fire
            dev_at_end = prem_at_end - mean_at_fire
            # convergence: deviation shrinks → pass
            convergence = dev_at_fire - dev_at_end   # positive = reverted toward mean
            return round(convergence, 2)

        elif pair == "venue_southbound->china":
            # Forward HSCEI return graded vs fired sign.
            hsce = store.read("hk", "_HSCE")
            if hsce is None or "close" not in hsce.columns:
                return None
            h = hsce["close"].dropna().sort_index()
            if h.index.max() < end:
                return None  # not matured
            h0, h1 = at(h, f), at(h, end)
            if None in (h0, h1) or h0 <= 0:
                return None
            return round((h1 / h0 - 1.0) * 100, 2)

        return None
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
            family = getattr(r, "family", None)
            if family == "venue":
                fwd = _fwd_venue(r.pair, r.sign, r.fired_date)
            else:
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
