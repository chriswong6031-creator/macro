"""China Special Situations desk engine.

Fuses six data planes into a schema-versioned, context-only JSON:
  NEW  : unlocks, preannouncements, inquiry letters, ST board + history, goodwill
  EXISTING: buybacks, pledge stress, block-trade anomalies, earnings calendar

Output: site/chinaspecialdata/special.json  (schema: china_special_sits.v1)

Rules:
- Every input degrades independently (try/except → None, log warning)
- Per-input asof + status chips surface staleness
- NO composite scores, NO buy/sell language
- Counts, ranks by DISCLOSED magnitudes, dates, links only
- Direction labels = exchange-reported 预告类型 verbatim
- Inquiry letters = metadata + link only (no body text)
- ST watch labeled "history accrues from 2026-07 forward" until ≥2 dates present

Unlock ratio note: 占解禁前流通市值比例 is a FRACTION (1.0 = 100%). Engine stores
float_pct = ratio * 100 so that float_pct=5.0 means 5% of pre-unlock float.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_special_sits.v1"
_MAX_ROWS = 8  # capped row count per category


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _data_dir() -> Path:
    return config.data_dir()


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def _col(cols: list[str], *needles: str) -> str | None:
    """First column containing ALL needle substrings."""
    for c in cols:
        s = str(c)
        if all(n in s for n in needles):
            return c
    return None


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except Exception:  # noqa: BLE001
        return None


def _safe_str(v: Any) -> str:
    """Coerce to str; never emits raw numpy/int64 types."""
    if v is None:
        return ""
    try:
        f = float(v)
        if pd.isna(f):
            return ""
        # int-like float → no decimal
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(v)


def _today() -> str:
    return date.today().isoformat()


_REGIME_HISTORY_CACHE: dict = {}  # {path_str: DataFrame}


def _regime_chip_for_date(date_str: str) -> dict | None:
    """Look up quad/liquidity/cycle for a given date in regime_history.parquet.

    Returns {quad, quad_name, liquidity, cycle} if found, else None.
    Degrades cleanly: missing parquet or date not in index → None, no exception.
    Neutral/descriptive context only — no directional language.
    """
    try:
        p = config.ROOT / "data" / "china_regime" / "regime_history.parquet"
        pstr = str(p)
        if pstr not in _REGIME_HISTORY_CACHE:
            if not p.exists():
                return None
            _df = pd.read_parquet(p, columns=["quad", "quad_name", "liquidity", "cycle"])
            _df.index = pd.to_datetime(_df.index)
            _REGIME_HISTORY_CACHE[pstr] = _df.sort_index()
        df = _REGIME_HISTORY_CACHE[pstr]
        if df is None or df.empty:
            return None
        # Backward as-of join: latest regime row AT/BEFORE the event date.
        # Exact-match would drop weekend-dated announcements and future-dated
        # unlocks (regime_history is trading-days-only, ends today). PIT-honest:
        # never reads a regime row later than the event date.
        ts = pd.Timestamp(str(date_str)[:10])
        pos = df.index.get_indexer([ts], method="ffill")[0]
        if pos < 0:
            return None  # event predates regime history
        row = df.iloc[pos]
        quad = str(row["quad"])
        quad_name = str(row["quad_name"])
        liquidity = str(row["liquidity"])
        cycle = str(row["cycle"])
        if any(v in ("nan", "", "None", "none") for v in (quad, quad_name)):
            return None
        return {"quad": quad, "quad_name": quad_name, "liquidity": liquidity, "cycle": cycle}
    except Exception as e:  # noqa: BLE001
        log.debug("china_special_sits: regime chip lookup failed (%s)", e)
        return None


def _asof_status(parquet: Path) -> tuple[str | None, str]:
    """Return (asof_str, 'ok'|'missing'|'stale') for a parquet artifact."""
    if not parquet.exists():
        return None, "missing"
    try:
        df = pd.read_parquet(parquet, columns=["asof"])
        asof = str(df["asof"].max())
        today = _today()
        age = (date.fromisoformat(today) - date.fromisoformat(asof[:10])).days
        return asof[:10], ("ok" if age <= 2 else "stale")
    except Exception:  # noqa: BLE001
        return None, "missing"


# --------------------------------------------------------------------------- #
# per-plane readers (each returns None on failure)
# --------------------------------------------------------------------------- #

def _unlock_block() -> dict | None:
    """Next-30d unlock events ranked by float impact; weekly aggregate strip.

    占解禁前流通市值比例 is a FRACTION: 1.0 = 100% of pre-unlock float.
    Engine converts to float_pct (percent, 0-100 scale) on read.
    large_flag fires when float_pct >= 5.0 (≥5% of pre-unlock float).
    """
    det_path = _data_dir() / "china_unlocks" / "detail.parquet"
    sum_path  = _data_dir() / "china_unlocks" / "summary.parquet"
    asof, status = _asof_status(det_path)
    try:
        if not det_path.exists():
            return {"asof": None, "status": "missing", "events": [], "weekly_strip": [],
                    "n_events_30d": 0, "n_large": 0}
        df = pd.read_parquet(det_path)
        if df.empty:
            return {"asof": asof, "status": status, "events": [], "weekly_strip": [],
                    "n_events_30d": 0, "n_large": 0}

        cols = list(df.columns)
        date_col   = _col(cols, "解禁时间") or _col(cols, "时间")
        ratio_col  = _col(cols, "比例") or _col(cols, "流通市值比例")
        qty_col    = _col(cols, "解禁数量")
        mktcap_col = _col(cols, "实际解禁市值")
        type_col   = _col(cols, "限售股类型") or _col(cols, "类型")
        code_col   = _col(cols, "代码") or _col(cols, "股票代码")
        name_col   = _col(cols, "简称") or _col(cols, "名称")

        # Normalise date column (may be datetime.date objects)
        if date_col and date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        else:
            return {"asof": asof, "status": "no_date_col", "events": [], "weekly_strip": [],
                    "n_events_30d": 0, "n_large": 0}

        today_ts = pd.Timestamp.today().normalize()
        cutoff   = today_ts + pd.Timedelta(days=30)
        fwd = df[(df[date_col] >= today_ts) & (df[date_col] <= cutoff)].copy()
        if fwd.empty:
            return {"asof": asof, "status": status, "events": [], "weekly_strip": [],
                    "n_events_30d": 0, "n_large": 0}

        # Build float_pct (percent, 0-100 scale) from ratio column (fraction 0-1 scale)
        # Then sort by float_pct desc
        if ratio_col and ratio_col in fwd.columns:
            fwd["_ratio_raw"] = fwd[ratio_col].apply(_safe_float)
            # ratio is a fraction: multiply by 100 to get percent
            fwd["_float_pct"] = fwd["_ratio_raw"].apply(
                lambda x: x * 100.0 if x is not None else None
            )
        else:
            fwd["_ratio_raw"] = None
            fwd["_float_pct"] = None
        fwd = fwd.sort_values("_float_pct", ascending=False, na_position="last")

        events = []
        for _, row in fwd.head(_MAX_ROWS).iterrows():
            float_pct = _safe_float(row.get("_float_pct")) if "_float_pct" in row.index else None
            unlock_date = row[date_col].strftime("%Y-%m-%d") if pd.notna(row[date_col]) else None
            ev: dict = {
                "ticker":      str(row.get("ticker") or row.get(code_col) or ""),
                "name":        str(row.get(name_col) or ""),
                "unlock_date": unlock_date,
                "lock_type":   str(row.get(type_col) or "") if type_col else "",
                # float_pct: percent (0-100 scale); 5.0 = 5% of pre-unlock float
                "float_pct":   float_pct,
                # kept for backward-compat consumers; same value, same name
                "float_ratio": float_pct,
                "large_flag":  float_pct is not None and float_pct >= 5.0,
                "mktcap_yi":   _safe_float(row.get(mktcap_col)) if mktcap_col else None,
            }
            # Cycle-context chip (W5): stamp regime quad/liquidity/cycle at unlock date.
            # Muted/descriptive only — no directional language.
            if unlock_date:
                chip = _regime_chip_for_date(unlock_date)
                if chip:
                    ev["regime_chip"] = chip
            events.append(ev)

        n_large = sum(1 for e in events if e["large_flag"])

        # Weekly aggregate strip from summary
        # Summary date column is 解禁时间; fall back to 时间, then 日期
        weekly_strip: list[dict] = []
        try:
            if sum_path.exists():
                df_sum = pd.read_parquet(sum_path)
                scols = list(df_sum.columns)
                sdate_col = (
                    _col(scols, "解禁时间") or _col(scols, "时间") or
                    _col(scols, "日期") or _col(scols, "解禁日期")
                )
                smktcap_col = _col(scols, "实际解禁市值") or _col(scols, "市值")
                if sdate_col and smktcap_col:
                    df_sum[sdate_col] = pd.to_datetime(df_sum[sdate_col], errors="coerce")
                    df_sum["_week"] = df_sum[sdate_col].dt.to_period("W")
                    df_sum["_mktcap"] = df_sum[smktcap_col].apply(_safe_float)
                    by_week = df_sum.groupby("_week")["_mktcap"].sum().reset_index()
                    for _, wr in by_week.head(6).iterrows():
                        weekly_strip.append({
                            "week": str(wr["_week"]),
                            "total_mktcap": _safe_float(wr["_mktcap"]),
                        })
        except Exception as e:  # noqa: BLE001
            log.debug("china_special_sits: weekly strip failed (%s)", e)

        return {
            "asof": asof, "status": status,
            "events": events,
            "weekly_strip": weekly_strip,
            "n_events_30d": len(fwd),
            "n_large": n_large,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: unlock block failed (%s)", e)
        return None


def _inquiry_block() -> dict | None:
    """Last-14d exchange-issued letters (kind=letter), newest first + reply status.

    Source: data/china_filings/filings.parquet (category=='inquiry_letter').
    The `kind` column distinguishes letter/reply/attachment within this family
    (same semantics as the legacy china_inquiry collector).

    Returns a list of letter dicts WITHOUT a 'kind' key — the list is
    already letters-only by construction (kind='letter' filtered here).

    Claim-key contract (register_claims): event_key = f"inq_{secCode}_{date[:10]}".
    The output dict exposes `secCode` and `date` (YYYY-MM-DD) so that contract
    is preserved identically across the source switch.

    Fallback: when filings.parquet is absent but the legacy china_inquiry/inquiry.parquet
    still exists, reads from the legacy store. Logs a debug note.
    """
    filings_path = _data_dir() / "china_filings" / "filings.parquet"
    legacy_path  = _data_dir() / "china_inquiry"  / "inquiry.parquet"

    # Prefer filings.parquet; fall back to legacy on missing filings
    if filings_path.exists():
        path = filings_path
        source = "filings"
    else:
        path = legacy_path
        source = "legacy"
        log.debug("china_special_sits: filings.parquet absent; falling back to legacy inquiry.parquet")

    # --- asof derivation ---
    # filings.parquet has no 'asof' column; derive from publish_ts or _collected_at.
    # legacy inquiry.parquet has an 'asof' column — _asof_status() handles it directly.
    if not path.exists():
        return {"asof": None, "status": "missing", "letters": [], "n_letters": 0, "n_replies": 0}

    if source == "filings":
        try:
            _peek = pd.read_parquet(path, columns=["_collected_at"])
            _asof_raw = str(_peek["_collected_at"].max())[:10]
            today = date.today().isoformat()
            _age = (date.fromisoformat(today) - date.fromisoformat(_asof_raw)).days
            asof = _asof_raw
            status = "ok" if _age <= 2 else "stale"
        except Exception:  # noqa: BLE001
            asof, status = None, "missing"
    else:
        asof, status = _asof_status(path)

    try:
        if source == "filings":
            df_raw = pd.read_parquet(path)
            # Narrow to inquiry_letter family only
            if "category" in df_raw.columns:
                df_raw = df_raw[df_raw["category"] == "inquiry_letter"].copy()
            else:
                df_raw = df_raw.copy()

            if df_raw.empty:
                return {"asof": asof, "status": status, "letters": [], "n_letters": 0, "n_replies": 0}

            # Normalise: translate filings column names → legacy field names
            # publish_ts (ISO8601 string with tz) → date string YYYY-MM-DD
            df_raw["_date_str"] = df_raw["publish_ts"].fillna("").apply(
                lambda v: str(v)[:10] if v else ""
            )
            # cutoff: last 14 days
            cutoff = (date.today() - timedelta(days=14)).isoformat()
            df_filt = df_raw[df_raw["_date_str"].fillna("") >= cutoff].copy()

            # Build reply lookup: sec_code → True if there's a reply in the window
            replies = set(df_filt[df_filt["kind"] == "reply"]["sec_code"].dropna().tolist())

            # Letters only
            letters = df_filt[df_filt["kind"] == "letter"].sort_values(
                "_date_str", ascending=False, na_position="last"
            )

            rows = []
            for _, r in letters.head(_MAX_ROWS).iterrows():
                letter_date = str(r.get("_date_str") or "")
                # secCode for claim-key: filings uses sec_code
                sec_code_val = str(r.get("sec_code") or "")
                letter: dict = {
                    "secCode":   sec_code_val,
                    "secName":   str(r.get("sec_name") or ""),
                    "title":     str(r.get("title") or ""),
                    "date":      letter_date,
                    "pdf_url":   str(r.get("adjunct_url") or ""),
                    "has_reply": sec_code_val in replies,
                    "type_name": str(r.get("announcement_type_raw") or ""),
                    # Note: no 'kind' key — list is letters-only; register_claims must not filter on kind
                }
                if letter_date:
                    chip = _regime_chip_for_date(letter_date[:10])
                    if chip:
                        letter["regime_chip"] = chip
                rows.append(letter)

            n_replies = int(len(df_filt[df_filt["kind"] == "reply"]))
            return {
                "asof": asof, "status": status,
                "letters": rows,
                "n_letters": int(len(letters)),
                "n_replies": n_replies,
            }

        else:
            # Legacy path (inquiry.parquet)
            df = pd.read_parquet(path)
            if df.empty:
                return {"asof": asof, "status": status, "letters": [], "n_letters": 0, "n_replies": 0}

            cutoff = (date.today() - timedelta(days=14)).isoformat()
            if "announcementTime" in df.columns:
                df_filt = df[df["announcementTime"].fillna("") >= cutoff].copy()
            else:
                df_filt = df.copy()

            replies = set(df_filt[df_filt["kind"] == "reply"]["secCode"].dropna().tolist())
            letters = df_filt[df_filt["kind"] == "letter"].sort_values(
                "announcementTime", ascending=False, na_position="last"
            )

            rows = []
            for _, r in letters.head(_MAX_ROWS).iterrows():
                letter_date = str(r.get("announcementTime") or "")
                letter: dict = {
                    "secCode":   str(r.get("secCode") or ""),
                    "secName":   str(r.get("secName") or ""),
                    "title":     str(r.get("announcementTitle") or ""),
                    "date":      letter_date,
                    "pdf_url":   str(r.get("adjunctUrl") or ""),
                    "has_reply": str(r.get("secCode") or "") in replies,
                    "type_name": str(r.get("announcementTypeName") or ""),
                    # Note: no 'kind' key — list is letters-only
                }
                if letter_date:
                    chip = _regime_chip_for_date(letter_date[:10])
                    if chip:
                        letter["regime_chip"] = chip
                rows.append(letter)

            return {
                "asof": asof, "status": status,
                "letters": rows,
                "n_letters": len(letters),
                "n_replies": len(df_filt[df_filt["kind"] == "reply"]),
            }
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: inquiry block failed (source=%s, %s)", source, e)
        return None


def _preannounce_block() -> dict | None:
    """Earnings preannouncement counts by type + biggest movers."""
    path = _data_dir() / "china_preannounce" / "forecast.parquet"
    asof, status = _asof_status(path)
    try:
        if not path.exists():
            return {"asof": None, "status": "missing", "by_type": {}, "top_movers": [], "n_total": 0}
        df = pd.read_parquet(path)
        if df.empty:
            return {"asof": asof, "status": status, "by_type": {}, "top_movers": [], "n_total": 0}

        cols = list(df.columns)
        type_col   = _col(cols, "预告类型") or _col(cols, "类型")
        change_col = _col(cols, "业绩变动幅度") or _col(cols, "变动幅度") or _col(cols, "变化幅度")
        name_col   = _col(cols, "简称") or _col(cols, "名称")
        code_col   = _col(cols, "代码") or _col(cols, "股票代码")

        # Counts by type (exchange-reported labels verbatim)
        by_type: dict[str, int] = {}
        if type_col and type_col in df.columns:
            by_type = df[type_col].value_counts().to_dict()
            by_type = {str(k): int(v) for k, v in by_type.items()}

        # Top movers by magnitude (abs)
        top_movers: list[dict] = []
        if change_col and change_col in df.columns:
            df["_change"] = df[change_col].apply(_safe_float)
            df_sorted = df.dropna(subset=["_change"]).sort_values(
                "_change", key=lambda x: x.abs(), ascending=False
            )
            for _, row in df_sorted.head(_MAX_ROWS).iterrows():
                top_movers.append({
                    "ticker":     str(row.get("ticker") or row.get(code_col) or ""),
                    "name":       str(row.get(name_col) or ""),
                    "type":       str(row.get(type_col) or "") if type_col else "",
                    "pct_change": _safe_float(row.get("_change")),
                    "quarter":    str(row.get("quarter") or ""),
                })

        return {
            "asof": asof, "status": status,
            "by_type": by_type,
            "top_movers": top_movers,
            "n_total": len(df),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: preannounce block failed (%s)", e)
        return None


def _buyback_block() -> dict | None:
    """Largest active buyback programs by plan_amt_yi + progress."""
    path = _data_dir() / "china_buyback" / "buyback.parquet"
    asof, status = _asof_status(path)
    try:
        if not path.exists():
            return {"asof": None, "status": "missing", "top": [], "n_active": 0}
        df = pd.read_parquet(path)
        if df.empty:
            return {"asof": asof, "status": status, "top": [], "n_active": 0}

        # Active programs
        if "progress" in df.columns:
            active = df[df["progress"].str.contains("实施中", na=False)].copy()
        else:
            active = df.copy()

        active = active.sort_values("plan_amt_yi", ascending=False, na_position="last")
        top = []
        for _, r in active.head(_MAX_ROWS).iterrows():
            top.append({
                "ticker":       str(r.get("ticker") or ""),
                "name":         str(r.get("name") or ""),
                "plan_amt_yi":  _safe_float(r.get("plan_amt_yi")),
                "done_amt_yi":  _safe_float(r.get("done_amt_yi")),
                "progress":     str(r.get("progress") or ""),
            })
        return {"asof": asof, "status": status, "top": top, "n_active": len(active)}
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: buyback block failed (%s)", e)
        return None


def _pledge_block() -> dict | None:
    """Highest pledge_ratio names (latest quarter)."""
    path = _data_dir() / "china_pledge" / "pledge.parquet"
    asof, status = _asof_status(path)
    try:
        if not path.exists():
            return {"asof": None, "status": "missing", "top": [], "n_high": 0}
        df = pd.read_parquet(path)
        if df.empty:
            return {"asof": asof, "status": status, "top": [], "n_high": 0}

        # Latest quarter only
        if "quarter" in df.columns:
            latest_q = df["quarter"].max()
            df = df[df["quarter"] == latest_q].copy()

        df = df.sort_values("pledge_ratio", ascending=False, na_position="last")
        n_high = int((df["pledge_ratio"] >= 50).sum()) if "pledge_ratio" in df.columns else 0
        top = []
        for _, r in df.head(_MAX_ROWS).iterrows():
            top.append({
                "ticker":          str(r.get("ticker") or ""),
                "name":            str(r.get("name") or ""),
                "pledge_ratio":    _safe_float(r.get("pledge_ratio")),
                "pledge_mktcap_yi": _safe_float(r.get("pledge_mktcap_yi")),
                "quarter":         str(r.get("quarter") or ""),
            })
        return {"asof": asof, "status": status, "top": top, "n_high": n_high,
                "quarter": str(df["quarter"].max()) if "quarter" in df.columns else None}
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: pledge block failed (%s)", e)
        return None


def _st_block() -> dict | None:
    """Current ST count + newest additions (once history accrues)."""
    snap_path = _data_dir() / "china_st" / "st_snapshot.parquet"
    hist_path = _data_dir() / "china_st" / "st_history.parquet"
    asof, status = _asof_status(snap_path)
    try:
        if not snap_path.exists():
            return {"asof": None, "status": "missing", "count": 0, "additions": [],
                    "removals": [], "history_note": "history accrues from 2026-07 forward"}
        df = pd.read_parquet(snap_path)
        count = len(df)

        additions: list[dict] = []
        removals:  list[dict] = []
        history_note = "history accrues from 2026-07 forward"

        if hist_path.exists():
            try:
                hist = pd.read_parquet(hist_path)
                dates = sorted(hist["date"].unique())
                if len(dates) >= 2:
                    history_note = None
                    prev_date = dates[-2]
                    curr_date = dates[-1]
                    prev_set = set(hist[hist["date"] == prev_date]["ticker"].dropna())
                    curr_set = set(hist[hist["date"] == curr_date]["ticker"].dropna())

                    added   = curr_set - prev_set
                    removed = prev_set - curr_set

                    # Get names for additions
                    name_map = {}
                    if "name" in df.columns:
                        name_map = dict(zip(df.get("ticker", []), df.get("name", [])))
                    for tk in list(added)[:_MAX_ROWS]:
                        additions.append({"ticker": tk, "name": name_map.get(tk, "")})
                    for tk in list(removed)[:_MAX_ROWS]:
                        removals.append({"ticker": tk, "name": ""})
            except Exception as e:  # noqa: BLE001
                log.debug("china_special_sits: ST history diff failed (%s)", e)

        top_current = []
        if not df.empty:
            for _, r in df.head(_MAX_ROWS).iterrows():
                top_current.append({
                    "ticker": str(r.get("ticker") or ""),
                    "name":   str(r.get("name") or ""),
                    "pct_chg": _safe_float(r.get("pct_chg")),
                })

        return {
            "asof": asof, "status": status,
            "count": count,
            "top_current": top_current,
            "additions": additions,
            "removals": removals,
            "history_note": history_note,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: ST block failed (%s)", e)
        return None


def _block_trade_block() -> dict | None:
    """Largest premium/discount block-trade anomalies."""
    path = _data_dir() / "china_block_trades" / "detail.parquet"
    asof, status = _asof_status(path)
    try:
        if not path.exists():
            return {"asof": None, "status": "missing", "top_premium": [], "top_discount": []}
        df = pd.read_parquet(path)
        if df.empty:
            return {"asof": asof, "status": status, "top_premium": [], "top_discount": []}

        df = df.copy()
        if "avg_premium_pct" in df.columns:
            df["_abs_prem"] = df["avg_premium_pct"].apply(lambda x: abs(_safe_float(x) or 0))
            df_prem = df[df["avg_premium_pct"].apply(lambda x: (_safe_float(x) or 0) > 0)].sort_values(
                "avg_premium_pct", ascending=False)
            df_disc = df[df["avg_premium_pct"].apply(lambda x: (_safe_float(x) or 0) < 0)].sort_values(
                "avg_premium_pct", ascending=True)
        else:
            df_prem = df_disc = pd.DataFrame()

        def _row(r):
            return {
                "ticker":         str(r.get("ticker") or ""),
                "avg_premium_pct": _safe_float(r.get("avg_premium_pct")),
                "block_amt_yi":   _safe_float(r.get("block_amt_yi")),
                "n_blocks":       int(r.get("n_blocks") or 0),
                "last_date":      str(r.get("last_date") or ""),
            }

        top_premium  = [_row(r) for _, r in df_prem.head(_MAX_ROWS).iterrows()]
        top_discount = [_row(r) for _, r in df_disc.head(_MAX_ROWS).iterrows()]

        return {"asof": asof, "status": status,
                "top_premium": top_premium, "top_discount": top_discount,
                "n_names": len(df)}
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: block trade block failed (%s)", e)
        return None


def _goodwill_block() -> dict | None:
    """Whole-market annual goodwill aggregate context chip."""
    path = _data_dir() / "china_st" / "goodwill.parquet"
    asof, status = _asof_status(path)
    try:
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return None
        # Coerce all values to safe Python scalars (guard against numpy int64 → json.dumps TypeError)
        raw_rows = df.tail(5).to_dict("records")
        coerced_rows = []
        for row in raw_rows:
            coerced = {}
            for k, v in row.items():
                f = _safe_float(v)
                if f is not None:
                    coerced[k] = f
                else:
                    coerced[k] = _safe_str(v) if v is not None else None
            coerced_rows.append(coerced)
        return {"asof": asof, "status": status, "annual_rows": coerced_rows[:5]}
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: goodwill block failed (%s)", e)
        return None


def _by_ticker_rollup(blocks: dict) -> dict:
    """Build per-ticker flags dict for W4's command apparatus."""
    by_ticker: dict[str, dict] = {}

    def _flag(tk: str, category: str) -> None:
        if not tk:
            return
        if tk not in by_ticker:
            by_ticker[tk] = {}
        by_ticker[tk][category] = True

    unlocks = blocks.get("unlocks") or {}
    for ev in (unlocks.get("events") or []):
        if ev.get("large_flag"):
            _flag(ev.get("ticker"), "unlock_large")
        else:
            _flag(ev.get("ticker"), "unlock")

    inquiry = blocks.get("inquiry") or {}
    for ltr in (inquiry.get("letters") or []):
        _flag(ltr.get("secCode"), "inquiry_letter")

    pledge = blocks.get("pledge") or {}
    for r in (pledge.get("top") or []):
        _flag(r.get("ticker"), "high_pledge")

    buyback = blocks.get("buyback") or {}
    for r in (buyback.get("top") or []):
        _flag(r.get("ticker"), "buyback_active")

    st = blocks.get("st") or {}
    for r in (st.get("additions") or []):
        _flag(r.get("ticker"), "st_new")
    for r in (st.get("top_current") or []):
        _flag(r.get("ticker"), "st")

    return by_ticker


# --------------------------------------------------------------------------- #
# public: fuse + emit
# --------------------------------------------------------------------------- #

def scan() -> dict:
    """Assemble the special-situations context snapshot. Never raises."""
    blocks: dict[str, Any] = {}
    block_asofs: list[str] = []

    for key, fn in (
        ("unlocks",      _unlock_block),
        ("inquiry",      _inquiry_block),
        ("preannounce",  _preannounce_block),
        ("buyback",      _buyback_block),
        ("pledge",       _pledge_block),
        ("st",           _st_block),
        ("block_trades", _block_trade_block),
        ("goodwill",     _goodwill_block),
    ):
        try:
            blocks[key] = fn()
        except Exception as e:  # noqa: BLE001
            log.warning("china_special_sits: %s block raised (%s)", key, e)
            blocks[key] = None

        # collect per-block asof for data_asof staleness indicator
        blk = blocks.get(key)
        if isinstance(blk, dict) and blk.get("asof"):
            block_asofs.append(str(blk["asof"]))

    # data_asof = worst (oldest) per-input asof; falls back to today
    data_asof = min(block_asofs) if block_asofs else _today()

    by_ticker = _by_ticker_rollup(blocks)

    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "asof": _today(),
        "data_asof": data_asof,
        **blocks,
        "by_ticker": by_ticker,
        "disclaimer": (
            "Context only — not a signal, score or trade. "
            "Rankings by disclosed magnitudes and exchange-reported labels; "
            "no directional scoring originates here."
        ),
        "disclaimer_zh": (
            "仅作背景，非信号、评分或交易。按披露规模和交易所公布类型排序；"
            "此处不产生任何方向性评分。"
        ),
    }


def register_claims(snap: dict, root: Any = None) -> int:
    """Register salience-only qledger claims for inquiry-letter and large-unlock events.

    Called from the SCHEDULED CI LANE (build_china_special_situations, inside build_china.py
    which runs in asia-close). Gated on CN_LANE=asia to prevent intraday / render-lane
    ledger writes (mirrors the china_standout_track lane guard pattern).

    direction=0 for all claims (salience-only); claim_family=cn_special_sits.

    Deduplication: each event registers exactly ONCE per event identity via an append-only
    sidecar data/china_special_sits/claims_registered.parquet
    (columns: event_key, first_registered).
    event_key: unlock → unlock_{ticker}_{unlock_date}; inquiry → inq_{secCode}_{announce_date}

    Entity scope: scope_type='entity', scope_key=<normalized ticker> (mirrors communique_diff.py
    lines ~431-444). Falls back to macro/510300.SS only when ticker normalization fails.

    Returns count registered; 0 on any failure.
    """
    import os
    if os.environ.get("CN_LANE", "") != "asia":
        log.debug("china_special_sits.register_claims: not in asia lane, skipping ledger write")
        return 0
    try:
        from engine import qledger
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: qledger import failed (%s)", e)
        return 0

    DESK = "china_special_sits"
    CLAIM_FAMILY = "cn_special_sits"
    HORIZON_D = 21

    # ---------------------------------------------------------------------- #
    # load (or create) the claims-registered sidecar
    # ---------------------------------------------------------------------- #
    sidecar_path = _data_dir() / "china_special_sits" / "claims_registered.parquet"
    try:
        if sidecar_path.exists():
            df_sidecar = pd.read_parquet(sidecar_path)
            registered_keys: set[str] = set(df_sidecar["event_key"].dropna().tolist())
        else:
            df_sidecar = pd.DataFrame(columns=["event_key", "first_registered"])
            registered_keys = set()
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: sidecar read failed (%s), starting fresh", e)
        df_sidecar = pd.DataFrame(columns=["event_key", "first_registered"])
        registered_keys = set()

    today = _today()
    pending: list[dict] = []
    new_sidecar_rows: list[dict] = []

    # try to import to_ticker for entity normalization
    try:
        from collectors.china_analyst import to_ticker as _to_ticker
    except Exception:  # noqa: BLE001
        _to_ticker = None

    def _entity_claim(ticker: str, sec_code: str = "") -> tuple[str, str]:
        """Return (scope_type, scope_key) for a claim. Entity path preferred."""
        normalized = None
        # try ticker first (already normalized in unlock events)
        if ticker and "." in ticker:
            normalized = ticker
        # try sec_code via to_ticker
        if normalized is None and sec_code and _to_ticker:
            try:
                normalized = _to_ticker(sec_code)
            except Exception:  # noqa: BLE001
                pass
        if normalized:
            return "entity", normalized
        return "macro", "510300.SS"

    # inquiry letters (per-company salience claims)
    inquiry = snap.get("inquiry") or {}
    for ltr in (inquiry.get("letters") or []):
        # letters list has NO 'kind' key by construction (already filtered to letters-only)
        # do NOT filter on ltr.get('kind') — the list is letters-only
        sec_code = str(ltr.get("secCode") or "")
        if not sec_code:
            continue
        announce_date = str(ltr.get("date") or today)[:10]
        event_key = f"inq_{sec_code}_{announce_date}"
        if event_key in registered_keys:
            continue  # already registered on a previous run
        scope_type, scope_key = _entity_claim("", sec_code)
        try:
            claim_asof = announce_date  # stamp from the event's own date
            pending.append(qledger.make_claim(
                desk=DESK, asof=claim_asof, scope_type=scope_type,
                scope_key=scope_key, direction=0, horizon_d=HORIZON_D,
                timestamp_quality="CRAWL_BOUNDED", bench="510300.SS",
                claim_family=CLAIM_FAMILY,
                extra={
                    "event_kind": "inquiry_letter",
                    "sec_code": sec_code,
                    "sec_name": ltr.get("secName"),
                    "salt": event_key,
                },
            ))
            new_sidecar_rows.append({"event_key": event_key, "first_registered": today})
        except Exception as ex:  # noqa: BLE001
            log.debug("china_special_sits: claim build failed for %s (%s)", sec_code, ex)

    # large-unlock events (≥5% float)
    unlocks = snap.get("unlocks") or {}
    for ev in (unlocks.get("events") or []):
        if not ev.get("large_flag"):
            continue
        ticker = str(ev.get("ticker") or "")
        if not ticker:
            continue
        unlock_date = str(ev.get("unlock_date") or today)[:10]
        event_key = f"unlock_{ticker}_{unlock_date}"
        if event_key in registered_keys:
            continue  # already registered on a previous run
        scope_type, scope_key = _entity_claim(ticker, "")
        try:
            # stamp from first-seen (today, sidecar guarantees uniqueness)
            claim_asof = today
            pending.append(qledger.make_claim(
                desk=DESK, asof=claim_asof, scope_type=scope_type,
                scope_key=scope_key, direction=0, horizon_d=HORIZON_D,
                timestamp_quality="CRAWL_BOUNDED", bench="510300.SS",
                claim_family=CLAIM_FAMILY,
                extra={
                    "event_kind": "large_unlock",
                    "ticker": ticker,
                    "unlock_date": unlock_date,
                    "float_pct": ev.get("float_pct"),
                    "salt": event_key,
                },
            ))
            new_sidecar_rows.append({"event_key": event_key, "first_registered": today})
        except Exception as ex:  # noqa: BLE001
            log.debug("china_special_sits: claim build failed for unlock %s (%s)", ticker, ex)

    if not pending:
        return 0

    try:
        results = qledger.register_batch(pending, root=root)
        n = sum(1 for r in results if r.get("status") != "error")
        log.info("china_special_sits: registered %d/%d qledger claims (asof=%s)",
                 n, len(pending), today)
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: register_batch failed (%s)", e)
        return 0

    # persist sidecar only after successful registration
    if new_sidecar_rows and n > 0:
        try:
            df_new = pd.DataFrame(new_sidecar_rows)
            df_merged = pd.concat([df_sidecar, df_new], ignore_index=True)
            sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            df_merged.to_parquet(sidecar_path, index=False)
            log.debug("china_special_sits: sidecar updated (%d total keys)", len(df_merged))
        except Exception as e:  # noqa: BLE001
            log.warning("china_special_sits: sidecar write failed (%s)", e)

    return n


def build() -> dict | None:
    """Run scan(), write site/chinaspecialdata/special.json, register claims. Returns snapshot or None."""
    try:
        snap = scan()
        out_dir = _site_dir() / "chinaspecialdata"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "special.json").write_text(
            json.dumps(snap, ensure_ascii=False, separators=(",", ":"), default=str)
        )
        log.info("china_special_sits: wrote special.json (schema=%s)", SCHEMA)
        # register qledger claims (gated on CN_LANE=asia — nightly lane only)
        register_claims(snap)
        return snap
    except Exception as e:  # noqa: BLE001
        log.error("china_special_sits build failed (%s)", e)
        return None
