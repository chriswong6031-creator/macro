"""IPO lock-up expiry overhang — DISPLAY-ONLY, NEVER-SCORED (Phase 2).

The most capturable IPO leg (research/IPO_RADAR.md): when a fresh IPO's 180-day
lock-up expires, insider/PE/VC supply hits a thin float — a documented one-sided
overhang (Field & Hanka 1999: ~−1.5% / −3% VC-backed 3-day abnormal return, ~+40%
volume). The DATE is deterministic and free (prospectus, parsed by
collectors/ipo_prospectus; standard 180 days otherwise), so we publish an
avoid/de-risk-into-the-cliff CALENDAR.

Honest framing (kept on the page): this is NOT a tradeable short — the drift is small
and borrow is scarce/expensive in the lock-up, so the academic edge is not net-of-cost
exploitable. It is a "don't add into the cliff / expect supply" flag. Nothing here is
scored or fed to any axis/allocation (tests assert it).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

SCORED = False
STD_LOCKUP_DAYS = 180     # the market-standard IPO lock-up when the prospectus is silent

# status thresholds on days-to-expiry (expiry_date - today)
APPROACH_DAYS = 45        # expiry within the next 45d → approaching
RECENT_DAYS = 30          # expired within the last 30d → overhang active


def _today() -> "pd.Timestamp":
    return pd.Timestamp(datetime.now(timezone.utc).date())


def _status(days_to: int) -> str:
    if days_to > APPROACH_DAYS:
        return "locked"
    if days_to >= 0:
        return "approaching"
    if days_to >= -RECENT_DAYS:
        return "just-expired"
    return "expired"


def _lockup_days_for(ticker: str, lockups: pd.DataFrame | None) -> tuple[int, str]:
    """(days, source) — prospectus-confirmed when available, else the 180d standard."""
    if lockups is not None and not lockups.empty and ticker in lockups.index:
        v = lockups.loc[ticker].get("lockup_days")
        if v is not None and pd.notna(v):
            return int(v), "confirmed"
    return STD_LOCKUP_DAYS, "estimate"


def lockup_rows(cal: pd.DataFrame, lockups: pd.DataFrame | None = None,
                lookback_days: int = 300) -> list[dict]:
    """Recent priced OPERATING-company IPOs (SPACs excluded — different mechanics)
    with their lock-up expiry, days-to/from, and status. Sorted soonest-first."""
    if cal is None or cal.empty or "status" not in cal:
        return []
    p = cal[(cal["status"] == "priced") & (~cal["is_spac"].astype(bool))].copy()
    if p.empty:
        return []
    today = _today()
    rows = []
    for _, r in p.iterrows():
        pd_iso = r.get("priced_date")
        if not pd_iso:
            continue
        priced = pd.to_datetime(pd_iso, errors="coerce")
        if pd.isna(priced):
            continue
        if (today - priced).days > lookback_days:
            continue
        tkr = r.get("ticker")
        days, source = _lockup_days_for(tkr, lockups)
        expiry = priced + timedelta(days=days)
        days_to = int((expiry.normalize() - today).days)
        rows.append({
            "ticker": tkr, "company": r.get("company"),
            "priced_date": pd_iso, "lockup_days": days, "source": source,
            "expiry_date": expiry.strftime("%Y-%m-%d"), "days_to": days_to,
            "status": _status(days_to), "size_usd": r.get("offer_value_usd"),
        })
    rows.sort(key=lambda x: x["days_to"])
    return rows


def actionable_tickers(cal: pd.DataFrame, lookback_days: int = 300,
                       lo: int = -RECENT_DAYS, hi: int = APPROACH_DAYS) -> list[str]:
    """Tickers whose STANDARD (180d) lock-up expiry falls in the actionable window
    [today-lo, today+hi] — the small set worth confirming via the prospectus
    (keeps the EDGAR fetch bandwidth-bounded to what matters)."""
    out = []
    for r in lockup_rows(cal, None, lookback_days):     # 180d estimate, no fetch
        if r["ticker"] and lo <= r["days_to"] <= hi:
            out.append(r["ticker"])
    return out


def summary(rows: list[dict]) -> dict:
    appr = [r for r in rows if r["status"] == "approaching"]
    recent = [r for r in rows if r["status"] == "just-expired"]
    nxt = appr[0] if appr else None
    return {
        "n": len(rows),
        "approaching": len(appr),
        "just_expired": len(recent),
        "next_ticker": (nxt["ticker"] if nxt else None),
        "next_date": (nxt["expiry_date"] if nxt else None),
        "next_days": (nxt["days_to"] if nxt else None),
        "confirmed": sum(1 for r in rows if r["source"] == "confirmed"),
    }
