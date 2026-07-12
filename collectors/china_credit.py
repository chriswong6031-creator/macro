"""China Total Social Financing (社会融资规模增量) — the single most-watched China macro
lead for equities and commodities.

Source: PBoC direct (www.pbc.gov.cn 调查统计司 → <year>年统计数据 → 社会融资规模 →
社会融资规模增量统计表 .htm attachment), parsed with pandas.read_html (gb18030).
The table carries SINGLE-MONTH increments (亿元) for the calendar year, one row per
month, with the component breakdown; PBoC posts month M's print ~day 10-16 of M+1.

HISTORY (2026-07-11 repair): the original source was mofcom's shrzgmQuery
(data.mofcom.gov.cn, legacy-TLS) — that mirror FROZE at reference month 2026-04:
the endpoint still answers 200-OK but serves 201501..202604 only, and mofcom's
replacement platform (opendata.mofcom.gov.cn) re-publishes the series as xlsx
~2 months late behind a login wall. PBoC is the origin publisher and ~6 weeks
fresher. Overlap months were verified identical per component (totals differ by
≤ a few 亿 where PBoC revised). The store keeps the mofcom-era 2015+ history;
this collector only needs to return recent months — lib.store.upsert merges
(new wins on collision, old-only rows kept). ADDITIVE vs the mofcom feed:
`govt_bonds` (政府债券 — in-scope for TSF since 2019; mofcom never exposed it).

The downstream engine derives the CREDIT IMPULSE (YoY of the trailing-12-month TSF
sum), which historically leads risk assets by a couple of quarters.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone

import pandas as pd
import requests

from collectors.base import Adapter

log = logging.getLogger(__name__)

# Conservative TSF publication-availability model. NBS/PBoC release the prior
# month's Total Social Financing between ~day 9 and day 15 of the FOLLOWING month
# (occasionally slipping later). The parquet is indexed at reference-month START
# (e.g. April data -> 2026-04-01) for other consumers that key on reference dates;
# a print is only actually ACTABLE from its availability date. We stamp that as
# day 16 of the following month — a conservative upper bound on the real release
# so a backtest can never peek at the impulse before the market saw it. Used both
# to populate the additive `availability_date` column here and by the engine's
# `availability_stamp()` re-indexer that the credit legs consume.
TSF_RELEASE_DOM = 16   # day-of-month of the following month (conservative bound)


def tsf_availability_date(reference_month_start: pd.Timestamp) -> pd.Timestamp:
    """Conservative date a reference-month TSF print becomes actable:
    day TSF_RELEASE_DOM of the FOLLOWING calendar month."""
    ref = pd.Timestamp(reference_month_start).normalize()
    nxt = (ref + pd.offsets.MonthBegin(1))            # first of the following month
    return nxt.replace(day=TSF_RELEASE_DOM)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_ROOT = "https://www.pbc.gov.cn"
_INDEX_URL = _ROOT + "/diaochatongjisi/116219/index.html"

# CN column header (whitespace-stripped, startswith match) -> stored column.
# All 亿元, monthly increment. Header row is the one containing 社会融资规模增量.
_COLUMNS = {
    "社会融资规模增量":     "tsf_total",
    "人民币贷款":           "rmb_loans",
    "外币贷款":             "fx_loans",       # full header: 外币贷款（折合人民币）
    "委托贷款":             "entrust",
    "信托贷款":             "trust",
    "未贴现银行承兑汇票":   "accept_bills",
    "企业债券":             "corp_bonds",
    "政府债券":             "govt_bonds",     # additive vs the mofcom-era feed
    "非金融企业境内股票融资": "equity",
}


def _clean(v) -> str:
    """Collapse whitespace/nbsp inside a cell (PBoC pads headers with &nbsp;)."""
    return re.sub(r"[\s\xa0]+", "", str(v))


def _find_link_by_text(html: str, *substrings: str) -> str | None:
    """First <a href> whose visible text contains ALL given substrings."""
    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S):
        txt = re.sub(r"<[^>]+>", " ", m.group(2))
        if all(s in txt for s in substrings):
            return m.group(1)
    return None


def _abs(url: str) -> str:
    return url if url.startswith("http") else _ROOT + url


def _get_text(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    # PBoC serves "Content-Type: text/html" with NO charset → requests would decode
    # ISO-8859-1 and mojibake every Chinese anchor text. Pages are utf-8.
    return r.content.decode("utf-8", errors="replace")


def _find_flow_htm(shrzgm_html: str) -> str | None:
    """The year's 社会融资规模 node lists the 增量统计表 (flow) block first, then the
    存量统计表 (stock) block; each block links htm/xlsx/pdf renditions. Take the
    first .htm AFTER the 增量统计表 heading so we never grab the stock table."""
    i = shrzgm_html.find("增量统计表")
    if i < 0:
        return None
    m = re.search(r'href=["\']([^"\']+\.htm)["\']', shrzgm_html[i:])
    return m.group(1) if m else None


def _header_name(v) -> str:
    """Normalize a header cell: collapse whitespace and strip the 其中/of-which
    prefix PBoC has used on loan sub-components in some vintages."""
    return re.sub("^\u5176\u4e2d[\u003a\uff1a]?", "", _clean(v))


def _build_colmap(cells) -> dict[int, str]:
    colmap: dict[int, str] = {}
    for j, v in enumerate(cells):
        name = _header_name(v)
        for cn, stored in _COLUMNS.items():
            if name.startswith(cn) and stored not in colmap.values():
                colmap[j] = stored
                break
    return colmap


def _parse_one(raw: pd.DataFrame) -> pd.DataFrame | None:
    """Parse one read_html table into month-indexed component columns, or None."""
    hdr = None
    for i in range(min(len(raw), 12)):
        if any(_header_name(v) == "社会融资规模增量" for v in raw.iloc[i]):
            hdr = i
            break
    if hdr is not None:
        colmap = _build_colmap(raw.iloc[hdr])
        first_data_row = hdr + 1
    elif any(_header_name(c) == "社会融资规模增量" for c in raw.columns):
        # read_html promoted a clean <thead> to raw.columns (layout drift)
        colmap = _build_colmap(raw.columns)
        first_data_row = 0
    else:
        return None
    if "tsf_total" not in colmap.values():
        return None
    records: dict[pd.Timestamp, dict] = {}
    for i in range(first_data_row, len(raw)):
        m = re.match(r"^(\d{4})[.年](\d{1,2})月?$", _clean(raw.iat[i, 0]))
        if not m:
            continue
        ts = pd.Timestamp(int(m.group(1)), int(m.group(2)), 1)
        records[ts] = {
            stored: pd.to_numeric(_clean(raw.iat[i, j]).replace(",", ""),
                                  errors="coerce")
            for j, stored in colmap.items()
        }
    if not records:
        return None
    out = pd.DataFrame.from_dict(records, orient="index").sort_index()
    out = out.dropna(how="all")   # unpublished trailing months are all-NaN rows
    if out.empty or "tsf_total" not in out.columns:
        return None
    return out


def _parse_flow_table(content: bytes) -> pd.DataFrame:
    """PBoC attachments are gb18030-encoded .htm with one merged-header table."""
    text = content.decode("gb18030", errors="replace")
    for raw in pd.read_html(io.StringIO(text)):
        out = _parse_one(raw)
        if out is not None:
            return out
    raise ValueError("china_credit: no parsable 增量统计表 in PBoC attachment")


def _fetch_year(session: requests.Session, index_html: str, year: int) -> pd.DataFrame:
    href = _find_link_by_text(index_html, f"{year}年统计数据")
    if not href:
        raise ValueError(f"no {year}年统计数据 node on 调查统计 index")
    year_html = _get_text(session, _abs(href))
    # Anchor text is "社会融资规模 Aggregate Financing to the Real Economy"; require
    # both halves so we never match e.g. 地区社会融资规模增量统计表 article links.
    sh = (_find_link_by_text(year_html, "社会融资规模", "Aggregate Financing")
          or _find_link_by_text(year_html, "社会融资规模"))
    if not sh:
        raise ValueError(f"no 社会融资规模 child under {year}年统计数据")
    htm = _find_flow_htm(_get_text(session, _abs(sh)))
    if not htm:
        raise ValueError(f"no 增量统计表 .htm attachment for {year}")
    r = session.get(_abs(htm), timeout=30)
    r.raise_for_status()
    return _parse_flow_table(r.content)


class ChinaCreditAdapter(Adapter):
    name = "china_credit"
    group = "china_credit"
    # Staleness anchor math: rows are indexed at reference-month START and month M's
    # print lands ~day 10-16 of M+1, so the newest index is ~46d old right AFTER a
    # release and ~77d old just BEFORE the next one (healthy steady state). 85 gives
    # ~1wk of release slippage slack while still flagging a frozen feed ~8 days after
    # the first missed print. (The old 70 flickered stale the last week of each cycle.)
    stale_after_days = 85

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = requests.Session()
        s.headers.update({"User-Agent": _UA})
        index_html = _get_text(s, _INDEX_URL)
        now = datetime.now(timezone.utc)
        # December's print publishes mid-January under the PRIOR year's table, and
        # the new year's node may not exist yet — so in Jan/Feb fetch both years.
        years = [now.year] + ([now.year - 1] if now.month <= 2 else [])
        frames, errs = [], []
        for yr in years:
            try:
                frames.append(_fetch_year(s, index_html, yr))
            except Exception as e:  # noqa: BLE001 — try remaining years, surface below
                errs.append(f"{yr}: {e}")
        if not frames and now.month > 2:
            # current-year node missing/moved — prior year still beats failing dead
            try:
                frames.append(_fetch_year(s, index_html, now.year - 1))
            except Exception as e:  # noqa: BLE001
                errs.append(f"{now.year - 1}: {e}")
        if not frames:
            raise ValueError(f"china_credit: PBoC TSF fetch failed ({'; '.join(errs)})")
        if errs:
            log.warning("china_credit: partial year coverage: %s", "; ".join(errs))
        out = pd.concat(frames).sort_index()
        out = out[~out.index.duplicated(keep="last")]
        # ADDITIVE: keep the reference-month-start index (other consumers key on it),
        # but attach the conservative publication-availability date per row so credit
        # legs can act only AFTER the print was actually released (no ~10d look-ahead).
        out["availability_date"] = [tsf_availability_date(d) for d in out.index]
        return {"tsf": out}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(ChinaCreditAdapter().fetch()["tsf"])
