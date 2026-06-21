"""China Government Bond (中债国债) yield-curve term structure — keyless, via akshare.

A SERIES adapter (Stage 1 #11) that pages the ChinaBond national treasury curve
through akshare's ``bond_china_yield(start_date, end_date)``. That endpoint serves
THREE curves per day (国债 / 商业银行普通债 AAA / 中短期票据 AAA); we keep only the
national government curve (曲线名称 contains 中债国债) — the clean risk-free term
structure the China Policy Watch / conditions engines read.

Downstream (engine/china_policy_watch, china_conditions) derives the credit spread
(AAA_5y − CGB_5y, widening = risk-off → RORO leg) and the short-end Δ that confirms
the PBoC corridor; this collector only stores the raw curve.

DISPLAY/CONTEXT-ONLY · keyless. The endpoint caps each call at roughly a one-month
window, so full_history pages monthly windows back ~2 years; an incremental run pulls
the last ~40 days. akshare is imported LAZILY inside fetch() so a missing dep surfaces
as a tracked adapter failure, and the whole curve fetch raises RuntimeError only when
NOTHING is parsed (per the Adapter contract — the runner calls store.upsert, not us).

Stored under group ``china_cgb_curve`` as one parquet ``cgb`` with a datetime index
(from 日期) and columns m3,m6,y1,y3,y5,y7,y10,y30 (from 3月/6月/1年/3年/5年/7年/10年/30年).
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from collectors.base import Adapter

# imported for parity with the other china snapshot/series collectors (the
# integrator may reuse them; _num guards the per-cell numeric coercion here too)
from collectors.china_analyst import _num, to_ticker  # noqa: F401

log = logging.getLogger("china_cgb_curve")

# national government curve discriminator (substring — akshare names drift)
_NATIONAL = "中债国债"

# source tenor column (Chinese, substring-matched) -> stored column
_TENORS = (
    ("3月", "m3"),
    ("6月", "m6"),
    ("1年", "y1"),
    ("3年", "y3"),
    ("5年", "y5"),
    ("7年", "y7"),
    ("10年", "y10"),
    ("30年", "y30"),
)

_THROTTLE_S = 1.2          # akshare politeness floor between windowed calls
_INCREMENTAL_DAYS = 40     # incremental run look-back
_FULL_MONTHS = 24          # full_history walk-back depth (~2 years)


def _col(df: pd.DataFrame, needle: str):
    """First column whose name CONTAINS needle (akshare Chinese column drift)."""
    for c in df.columns:
        if needle in str(c):
            return c
    return None


def _windows(full_history: bool) -> list[tuple[str, str]]:
    """[(start, end)] YYYYMMDD windows. One ~40d window incrementally; monthly
    windows back ~2y for full history (the endpoint caps ~1 month per call)."""
    today = pd.Timestamp.utcnow().normalize()
    if not full_history:
        start = today - pd.Timedelta(days=_INCREMENTAL_DAYS)
        return [(start.strftime("%Y%m%d"), today.strftime("%Y%m%d"))]
    out: list[tuple[str, str]] = []
    end = today
    for _ in range(_FULL_MONTHS):
        start = end - pd.Timedelta(days=31)
        out.append((start.strftime("%Y%m%d"), end.strftime("%Y%m%d")))
        end = start - pd.Timedelta(days=1)
    return out


def _parse_window(df: pd.DataFrame) -> pd.DataFrame | None:
    """Filter to the national curve and reshape one window's raw frame to the
    stored wide layout (datetime index, m3..y30). None if nothing usable."""
    if df is None or df.empty:
        return None
    name_col = _col(df, "曲线名称")
    date_col = _col(df, "日期")
    if name_col is None or date_col is None:
        return None
    nat = df[df[name_col].astype(str).str.contains(_NATIONAL, na=False)].copy()
    if nat.empty:
        return None
    out = pd.DataFrame(index=pd.to_datetime(nat[date_col], errors="coerce"))
    for needle, stored in _TENORS:
        src = _col(nat, needle)
        if src is not None:
            out[stored] = pd.to_numeric(nat[src], errors="coerce").to_numpy()
    out = out[~out.index.isna()].dropna(how="all").sort_index()
    return out if not out.empty else None


class ChinaCgbCurveAdapter(Adapter):
    name = "china_cgb_curve"
    group = "china_cgb_curve"
    stale_after_days = 6        # near-daily but tolerate weekends/holidays + 502s
    # bond endpoints occasionally 502 from a non-CN IP — degrade, don't circuit-break
    expected_failure = "bond_china_yield blocked (non-CN IP / endpoint drift) — CGB curve context only"

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001 — tracked adapter failure
            raise RuntimeError(f"china_cgb_curve: akshare unavailable ({e})") from e

        frames: list[pd.DataFrame] = []
        errors: list[str] = []
        windows = _windows(full_history)
        for i, (start, end) in enumerate(windows):
            try:
                raw = ak.bond_china_yield(start_date=start, end_date=end)
                parsed = _parse_window(raw)
                if parsed is not None:
                    frames.append(parsed)
            except Exception as e:  # noqa: BLE001 — per-window isolation
                errors.append(f"{start}-{end}({e})")
                log.warning("china_cgb_curve window %s-%s failed: %s", start, end, e)
            if i < len(windows) - 1:
                time.sleep(_THROTTLE_S)   # throttle akshare

        if not frames:
            raise RuntimeError(
                "china_cgb_curve: no curve parsed — " + ("; ".join(errors) or "empty"))
        cgb = pd.concat(frames)
        cgb = cgb[~cgb.index.duplicated(keep="last")].sort_index()
        if errors:
            log.info("china_cgb_curve: %d/%d windows ok (skipped: %s)",
                     len(frames), len(windows), "; ".join(errors))
        log.info("china_cgb_curve: fetched %d rows (%s..%s)",
                 len(cgb), cgb.index.min().date(), cgb.index.max().date())
        return {"cgb": cgb}
