#!/usr/bin/env python3
"""Collect the historical Southbound (港股通) Stock-Connect eligible-securities
add/remove roster from the SSE 港股通标的调整 announcement archive.

STEP-1 of masterplan battery H-INCL. Produces a DATED add/remove series 2016->
that the CCASS per-date search (1-y rolling window) and the akshare snapshot
CANNOT provide. See research/H_INCL_PREREG.md §0 for the full source-feasibility
record (what was tried and rejected).

Source: https://www.sse.com.cn/services/hkexsc/disclo/announ/  (SSE 港股通公告)
  - list pages  s_list_N.shtml   (N=2..27, 15 notices/page, archive floor ~2015-09)
  - each notice c/c_YYYYMMDD_ID.shtml is a structured table: one <tr> per stock
    with a 调入 (add) / 调出 (remove) action cell + effective-date phrasing.

Output: data/hk_connect_roster/roster.parquet + PROVENANCE.md

Collect-lane only (no render dependency). Idempotent; polite delay between fetches.
"""
from __future__ import annotations
import re
import sys
import time
import pathlib
import datetime as dt

import pandas as pd
import requests

OUT_DIR = pathlib.Path("data/hk_connect_roster")
BASE = "https://www.sse.com.cn/services/hkexsc/disclo/announ"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Referer": BASE + "/",
}
# adjustment notices: bulk 名单/标的调整 (2018->, with 调入/调出 tables) + ad-hoc
# single-name 调入/调出 notices (2015->). Exclude holiday/fee/suspension/ETF notices.
TITLE_EXCLUDE = ("ETF", "交易日安排", "恢复交易", "暂停交易", "延迟开市", "停市",
                 "税率", "交易费", "交易征费", "开市", "印花税", "休市", "投资者教育",
                 "波动调节", "竞价", "额度", "风险提示", "买入申报")


def is_adjustment_title(ti: str) -> bool:
    if any(x in ti for x in TITLE_EXCLUDE):
        return False
    # bulk list-adjustment notices (semi-annual reviews + ad-hoc), all variants:
    #  "港股通标的调整", "港股通股票名单调整", "港股通标的证券定期调整", ...
    if "调整" in ti and ("标的" in ti or "名单" in ti):
        return True
    # ad-hoc single-name notices: "...调出港股通股票的通知" / "...调入港股通..."
    if ("调出港股通" in ti) or ("调入港股通" in ti):
        return True
    return False


def _get(url: str, tries: int = 3, timeout: int = 30) -> str | None:
    for k in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            if r.status_code == 404:
                return None
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                print(f"  FETCH-FAIL {url}: {type(e).__name__} {e}", file=sys.stderr)
        time.sleep(1.2 * (k + 1))
    return None


def list_adjustment_notices() -> list[tuple[str, str, str]]:
    """Return [(notice_url, announce_date_YYYYMMDD, title)] across all list pages."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    # page 1 = s_list.shtml (unpaginated, most-recent), then s_list_2..27
    pages = ["s_list.shtml"] + [f"s_list_{n}.shtml" for n in range(2, 30)]
    for pi, pname in enumerate(pages):
        t = _get(f"{BASE}/{pname}", timeout=25)
        if t is None:
            if pi > 27:
                break
            continue
        items = re.findall(
            r'href="([^"]*c_(\d{8})_\d+\.shtml)"[^>]*title="([^"]*)"', t
        )
        if not items:
            items = [
                (m.group(1), m.group(2), m.group(3))
                for m in re.finditer(
                    r'href="([^"]*c_(\d{8})_\d+\.shtml)"[^>]*>([^<]+)<', t
                )
            ]
        page_hits = 0
        for url, adate, title in items:
            if not is_adjustment_title(title):
                continue
            fname = url.split("/")[-1]
            full = f"{BASE}/c/{fname}"
            if full in seen:
                continue
            seen.add(full)
            out.append((full, adate, title))
            page_hits += 1
        print(f"  {pname}: {page_hits} adjustment notices")
        time.sleep(0.6)
    return out


def parse_notice(url: str, announce_date: str) -> list[dict]:
    """Parse one 标的调整 notice into add/remove rows."""
    t = _get(url, timeout=30)
    if t is None:
        print(f"  PARSE-SKIP (no fetch) {url}", file=sys.stderr)
        return []
    rows: list[dict] = []
    # each data row: <td>CODE(5-digit)</td> <td>NAME</td> ... <td>调入|调出</td>
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
    for tr in trs:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if not cells:
            continue
        text_cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        code = None
        action = None
        for c in text_cells:
            m = re.fullmatch(r"(\d{5})", c)
            if m:
                code = m.group(1)
            if c == "调入":
                action = "add"
            elif c == "调出":
                action = "remove"
        if code and action:
            rows.append({"code5": code, "action": action, "notice_url": url,
                         "announce_date": announce_date})
    return rows


def to_panel_ticker(code5: str) -> str:
    """HKEX 5-digit -> panel form. Panel uses 4-digit .HK for codes < 10000
    (e.g. 00700 -> 0700.HK) and 5-digit for >= 10000 (e.g. 09988 -> 9988.HK).
    The closes_deep columns are like '0700.HK','9988.HK' — strip one leading zero."""
    c = code5.lstrip("0") or "0"
    if len(c) <= 4:
        return c.zfill(4) + ".HK"
    return c + ".HK"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[1/3] enumerating SSE 港股通标的调整 notices ...")
    notices = list_adjustment_notices()
    print(f"  {len(notices)} adjustment notices 2015-09 -> now")

    print("[2/3] parsing add/remove tables ...")
    recs: list[dict] = []
    for i, (url, adate, title) in enumerate(sorted(notices, key=lambda x: x[1])):
        r = parse_notice(url, adate)
        recs.extend(r)
        if (i + 1) % 25 == 0:
            print(f"  parsed {i + 1}/{len(notices)} notices, {len(recs)} rows")
        time.sleep(0.5)

    if not recs:
        print("FATAL: no add/remove rows parsed", file=sys.stderr)
        return 1

    df = pd.DataFrame(recs)
    df["ticker"] = df["code5"].map(to_panel_ticker)
    df["announce_date"] = pd.to_datetime(df["announce_date"], format="%Y%m%d")
    # effective_date = next HK trading day strictly after announce (per prereg).
    # Approximate with the _HSI trading calendar; filled in the analysis step which
    # has the calendar. Here we store announce_date + a naive next-bd as a fallback.
    df["effective_date_fallback"] = df["announce_date"] + pd.offsets.BDay(1)
    df["source"] = "sse"
    df = df.drop_duplicates(subset=["ticker", "action", "announce_date"]).reset_index(drop=True)
    df = df.sort_values(["announce_date", "action", "ticker"]).reset_index(drop=True)

    out = OUT_DIR / "roster.parquet"
    df.to_parquet(out)
    print(f"[3/3] wrote {out}  rows={len(df)}")
    adds = df[df.action == "add"]
    print(f"  add events: {len(adds)}  distinct add tickers: {adds.ticker.nunique()}")
    print(f"  remove events: {(df.action=='remove').sum()}")
    print("  adds/yr:")
    print(adds.groupby(adds.announce_date.dt.year).size().to_string())

    prov = OUT_DIR / "PROVENANCE.md"
    prov.write_text(
        "# HK Connect Southbound Roster — provenance\n\n"
        f"Built {dt.date.today().isoformat()} by scripts/collect_hk_connect_roster.py.\n\n"
        "## Source (usable, dated, free)\n"
        "SSE 港股通公告 archive `sse.com.cn/services/hkexsc/disclo/announ/` — paginated\n"
        "`s_list_N.shtml` (N=2..27, floor ~2015-09), each 关于沪港通下港股通标的调整的通知\n"
        "`c/c_YYYYMMDD_ID.shtml` a structured table with 调入(add)/调出(remove) rows +\n"
        "effective-date phrasing. This is the SH-HK southbound adjustment record.\n\n"
        "## Routes tried and REJECTED (see research/H_INCL_PREREG.md §0)\n"
        "- HKEX View-All-Eligible-Securities: NORTHBOUND (SSE/SZSE) only, no SEHK southbound list.\n"
        "- akshare stock_hk_ggt_components_em: CURRENT snapshot only, no dates; host WAF-blocked.\n"
        "- HKEX CCASS mutualmarket.aspx per-date search: STRICT ~365-day rolling window\n"
        "  (2026/07/03..2025/07/03 populate; 2025/07/02 earlier empty) — cannot reach 2016.\n"
        "- SZSE 深港通 notices parse identically (调入/调出/生效) — robustness cross-check,\n"
        "  not the primary enumeration (annList API 500s to our UA).\n\n"
        "## Columns\n"
        "ticker (NNNN.HK panel form) · action (add|remove) · announce_date · code5 (raw 5-digit) ·\n"
        "effective_date_fallback (announce+1 BDay; the analysis step overrides with the next _HSI\n"
        "trading day) · source · notice_url.\n\n"
        "## Caveat\n"
        "The union southbound roster is SH-HK + SZ-HK (~90% overlapping); this file is the\n"
        "SSE (沪港通) adjustment record, the cleanly-enumerable authoritative source.\n"
    )
    print(f"  wrote {prov}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
