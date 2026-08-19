"""ST/risk-warning board snapshot collector (A-share names under ST/* or risk warning).

ST (Special Treatment) and *ST status are assigned by the exchanges when a company:
  - Posts losses two (ST) or three (*ST) consecutive years
  - Has material going-concern issues
  - Commits major violations

akshare's `stock_zh_a_st_em` hardcodes the geo-blocked `40.push2.eastmoney.com` host so
we go direct to the public push2.eastmoney.com CDN endpoint using the same field list and
filter parameters.

Also pulls goodwill aggregates (ak.stock_sy_profile_em) — whole-market annual series as
macro context for total A-share goodwill impairment risk.

Stored under:
  data/china_st/st_snapshot.parquet  — today's ST board snapshot
  data/china_st/st_history.parquet   — append-only daily (date, ticker, name) from today forward
  data/china_st/goodwill.parquet     — whole-market annual goodwill aggregates

ST additions/removals become detectable once history accrues (from 2026-07 forward).
CONTEXT-ONLY. ST status from public Eastmoney data; goodwill from akshare.
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from lib import config
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_st")

_ST_OUT      = config.data_dir() / "china_st" / "st_snapshot.parquet"
_HIST_OUT    = config.data_dir() / "china_st" / "st_history.parquet"
_GW_OUT      = config.data_dir() / "china_st" / "goodwill.parquet"

# push2.eastmoney.com/api/qt/clist/get was retired upstream and now returns a hard
# 502 for every parameter shape — that is what froze this plane at 2026-07-06. The
# repo's own source probe already classified it dead on 2026-07-25
# (scripts/probe_china_sources.py, cls="dead", expect 502); this collector was
# never moved across. push2delay is the same vendor and the same API contract
# (identical f-code fields), serving delayed quotes — correct for a risk-warning
# BOARD MEMBERSHIP list, which is a daily-granularity disclosure, not a live tape.
_PUSH2_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_ST_PARAMS = {
    "cb": "jQuery",
    "pn": "1",
    # Server caps a page at 100 rows regardless of what pz asks for; ask for what
    # we can actually get and let the paging loop below measure the real page size.
    "pz": "100",
    "po": "1",
    "np": "1",
    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    "fltt": "2",
    "invt": "2",
    "fid": "f3",
    # ST/risk-warning board: SH A-share (m:1 f:4) + SZ A-share (m:0 f:4) with special treatment
    "fs": "m:0 f:4,m:1 f:4",
    "fields": "f12,f14,f2,f3,f4,f5,f6,f9,f10,f18",
    "_": "1",
}
_FIELD_MAP = {
    "f12": "code",
    "f14": "name",
    "f2":  "price",
    "f3":  "pct_chg",
    "f4":  "chg_abs",
    "f5":  "volume",
    "f6":  "turnover",
    "f9":  "pe",
    "f10": "turnover_rate",
    "f18": "prev_close",
}


_MAX_PAGES = 50  # runaway guard; the ST board is ~200 names, so ~2 pages in practice


def _col(cols: list[str], *needles: str) -> str | None:
    for c in cols:
        s = str(c)
        if all(n in s for n in needles):
            return c
    return None


def _fetch_st_board() -> pd.DataFrame | None:
    """Fetch the current ST board via Eastmoney push2 CDN. Returns compact DataFrame."""
    import requests
    headers = {
        "Referer": "https://www.eastmoney.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    rows = []
    page = 1
    while True:
        params = {**_ST_PARAMS, "pn": str(page)}
        try:
            r = requests.get(_PUSH2_URL, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            text = r.text
            # response is jQuery(...) wrapped JSON or bare JSON
            if text.startswith("jQuery"):
                text = text[text.index("(") + 1 : text.rindex(")")]
            import json
            data = json.loads(text)
            diff = (data.get("data") or {}).get("diff") or []
            if not diff:
                break
            for item in diff:
                code = str(item.get("f12") or "")
                if not code:
                    continue
                rows.append({
                    "ticker": to_ticker(code),
                    "code":   code,
                    "name":   str(item.get("f14") or ""),
                    "price":  _num(item.get("f2")),
                    "pct_chg": _num(item.get("f3")),
                })
            # Page against what the server ACTUALLY returned, not against the pz we
            # asked for. The old `page * 500 >= total` test assumed a 500-row page
            # while the server caps at 100, so it broke after page 1 and silently
            # captured 100 of 207 ST names as if that were the whole board.
            total = int((data.get("data") or {}).get("total") or 0)
            if not total or len(rows) >= total or page >= _MAX_PAGES:
                break
            page += 1
            time.sleep(0.8)
        except Exception as e:  # noqa: BLE001
            log.warning("china st: page %d fetch failed (%s)", page, e)
            break

    if not rows:
        # A retired endpoint used to fail exactly like a quiet market: no rows, one
        # debug-level warning, no snapshot, and a plane that silently froze for six
        # weeks. Emit a real Actions annotation so the next outage is visible on the
        # run summary the day it starts. Bare print + flush: a logger prefix would
        # push '::warning' off the line start and GitHub would drop it.
        print(
            "::warning title=china-st-board-empty::"
            f"ST board fetch returned no rows from {_PUSH2_URL} — "
            "the risk-warning plane will not advance today.",
            flush=True,
        )
        return None
    return pd.DataFrame(rows)


def _fetch_goodwill() -> pd.DataFrame | None:
    """Fetch whole-market annual goodwill aggregates (0.86s, keyless akshare)."""
    import akshare as ak
    try:
        df = ak.stock_sy_profile_em()
    except Exception as e:  # noqa: BLE001
        log.warning("china st: goodwill profile fetch failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def refresh() -> int:
    """Fetch ST board snapshot + goodwill. Appends to history. Returns rows written."""
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")

    # Idempotency
    if _ST_OUT.exists():
        try:
            if str(pd.read_parquet(_ST_OUT, columns=["asof"])["asof"].max()) >= today:
                log.info("china st: snapshot already fresh (%s)", today)
                return 0
        except Exception:  # noqa: BLE001
            pass

    total = 0
    _ST_OUT.parent.mkdir(parents=True, exist_ok=True)

    # ── 1. ST snapshot ────────────────────────────────────────────────────────
    df_st = _fetch_st_board()
    time.sleep(1.0)
    if df_st is not None:
        df_st["asof"] = today
        df_st.to_parquet(_ST_OUT, index=False)
        total += len(df_st)
        log.info("china st: snapshot %d names → %s", len(df_st), _ST_OUT)

        # ── 2. Append to history ───────────────────────────────────────────────
        hist_cols = ["date", "ticker", "name"]
        hist_rows = pd.DataFrame({
            "date":   today,
            "ticker": df_st["ticker"],
            "name":   df_st["name"],
        })
        if _HIST_OUT.exists():
            try:
                existing = pd.read_parquet(_HIST_OUT)
                # Remove today's rows if somehow already present (idempotent append)
                existing = existing[existing["date"] != today]
                combined = pd.concat([existing, hist_rows], ignore_index=True)
            except Exception:  # noqa: BLE001
                combined = hist_rows
        else:
            combined = hist_rows
        combined.to_parquet(_HIST_OUT, index=False)
        log.info("china st: history %d total rows → %s", len(combined), _HIST_OUT)
    else:
        log.warning("china st: snapshot fetch returned no data")

    # ── 3. Goodwill profile ───────────────────────────────────────────────────
    df_gw = _fetch_goodwill()
    time.sleep(1.0)
    if df_gw is not None:
        df_gw["asof"] = today
        df_gw.to_parquet(_GW_OUT, index=False)
        total += len(df_gw)
        log.info("china st: goodwill %d rows → %s", len(df_gw), _GW_OUT)
    else:
        log.info("china st: goodwill fetch empty or failed")

    return total


def main() -> int:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description="Fetch A-share ST board snapshot").parse_args()
    n = refresh()
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
