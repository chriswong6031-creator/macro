#!/usr/bin/env python3
"""Native China/HK data-source accessibility probe harness.

Re-runnable verification of every load-bearing endpoint in the China/HK
native-data program (research/china_native_data/ — catalogs + masterplan).
Three probe classes:

  candidate   — new sources the masterplan waves build on (must be LIVE)
  integrated  — transports existing collectors already depend on (regression watch)
  dead        — known-blocked endpoints kept for DRIFT detection (a revival is
                actionable news; so is a new death among the live ones)

Verdicts (red-team-hardened 2026-07-25):
  OK      — status matched expectation AND content checks (json_path / contains /
            min_bytes / max_bytes) passed. Status-only probes are deliberately rare: a 200
            wrapping an error envelope is the single most common failure mode on
            Chinese endpoints (thepaper code:99998, cninfo webapi 401-in-200,
            SSE "service is null"), so most probes carry a content check.
  EMPTY   — a date-parameterized probe ("dated") answered 200-but-contentless or
            404: expected on CN/HK holidays, actionable on a known trading day.
            Counted separately; does NOT fail the run.
  FLAKY   — a known-unstable endpoint (flaky=True) failed at the network layer;
            within baseline, counted separately, does NOT fail the run.
  CHANGED — reachable but different status/content than the pinned expectation
            (e.g. a "dead" endpoint reviving, or a live one starting to error).
  ERR     — unexpected network-layer failure.

Exit code is 1 only when CHANGED/ERR > 0.

Accessibility is a function of THIS machine's egress (2026-07-25 baseline:
datacenter egress via Zenlayer/US — see SOURCE_CATALOG_MACRO_POLICY_HK.md §top).
If the runner's network posture changes, re-run and re-baseline before trusting
any hard-coded live/dead claim.

NOT wired into any nightly lane (render budget law): run manually —
    python3 scripts/probe_china_sources.py [--json OUT.json] [--only FAMILY]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.parse

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
TIMEOUT = 12
HOST_THROTTLE_S = 1.0  # courtesy ≤1 req/s/host — same law the collectors follow


def _last_weekday(fmt: str) -> str:
    # Sat/Sun only — no CN holiday calendar here, which is why date-parameterized
    # probes report EMPTY (not CHANGED) on contentless days: Golden Week etc.
    d = dt.date.today() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.strftime(fmt)


def _weekday_back(n: int, fmt: str) -> str:
    d = dt.date.today() - dt.timedelta(days=1)
    seen = 0
    while True:
        if d.weekday() < 5:
            seen += 1
            if seen >= n:
                return d.strftime(fmt)
        d -= dt.timedelta(days=1)


def _prev_month(fmt: str) -> str:
    first = dt.date.today().replace(day=1)
    return (first - dt.timedelta(days=1)).strftime(fmt)


def _dig(obj, path):
    cur = obj
    for k in path:
        cur = cur[k]
    return cur


_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.I)


def _page_text(r: "requests.Response") -> str:
    """Body decoded with the PAGE's own charset, for the `contains` check.

    Not ``r.text``: requests falls back to ISO-8859-1 for an HTML response that
    carries no charset in its Content-Type, which turns every CJK content check into
    a false CHANGED. CN portals also still serve gb2312/gbk (→ gb18030), so the meta
    tag is sniffed the same way the collectors do.
    """
    raw = r.content
    enc = None
    m = re.search(r"charset=([\w\-]+)", r.headers.get("Content-Type", "") or "", re.I)
    if m:
        enc = m.group(1)
    if not enc:
        mm = _META_CHARSET_RE.search(raw[:4096])
        if mm:
            enc = mm.group(1).decode("ascii", "ignore")
    enc = (enc or "utf-8").strip().lower()
    if enc in {"gb2312", "gbk", "gb-2312"}:
        enc = "gb18030"
    try:
        return raw.decode(enc, errors="replace")
    except (LookupError, TypeError):
        return raw.decode("utf-8", errors="replace")


# Each probe: name, family, cls, method, url, headers?, data?, flaky?, dated?,
# head_only?, expect{statuses, json_path?, contains?, min_bytes?, max_bytes?, error?}
#   contains — an HTML endpoint has no envelope to dig into, so the content check is
#   that the page still carries the LABEL the parser keys on (a column heading, a
#   table caption). Stable across days, unlike any document id, and absent from the
#   200-wrapped error shells these CMSes serve.
def build_probes() -> list[dict]:
    d8 = _last_weekday("%Y%m%d")
    d_iso = _last_weekday("%Y-%m-%d")
    d_iso_7 = _weekday_back(5, "%Y-%m-%d")   # 5 weekdays back ≈ a working-week window (W1 report probe)
    d8_10ago = _weekday_back(10, "%Y%m%d")
    m_iso = _prev_month("%Y-%m") + "-01"
    ym = _prev_month("%Y%m")
    yyyy = _last_weekday("%Y")
    dc = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    return [
        # ---- candidates (new sources the masterplan builds on) ----
        dict(name="em_report_list", family="sellside", cls="candidate", method="GET",
             url=("https://reportapi.eastmoney.com/report/list?industryCode=*&pageSize=3"
                  "&pageNo=1&reportType=&beginTime=" + m_iso + "&endTime=" + d_iso + "&qType=0"),
             expect=dict(statuses=[200], json_path=["hits"])),
        dict(name="em_holdernum", family="positioning", cls="candidate", method="GET",
             url=(dc + "?reportName=RPT_HOLDERNUMLATEST&columns=SECURITY_CODE,HOLDER_NUM,END_DATE"
                  "&pageSize=3&pageNumber=1&sortColumns=HOLDER_NUM&sortTypes=-1&source=WEB&client=WEB"),
             expect=dict(statuses=[200], json_path=["result", "data", 0, "HOLDER_NUM"])),
        dict(name="irm_cninfo_qa", family="interaction", cls="candidate", method="POST",
             url="https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
             data={"keyWord": "000001"},
             expect=dict(statuses=[200], json_path=["data", 0, "secid"])),
        # W1: the org-id resolve above only proves the KEYBOARD search. This anchors the
        # actual per-name Q&A pull collectors/china_irm.py drips nightly — note every
        # parameter rides in the query string with an empty POST body (the endpoint's
        # real contract), so a shape change here breaks the probe, not the nightly.
        dict(name="irm_company_question", family="interaction", cls="candidate", method="POST",
             url=("https://irm.cninfo.com.cn/newircs/company/question?_t=1691142650&stockcode=000001"
                  "&orgId=gssz0000001&pageSize=3&pageNum=1&keyWord=&startDay=&endDay="),
             expect=dict(statuses=[200], json_path=["rows", 0, "indexId"])),
        # W1: the market-wide 互动易 question total (velocity.parquet's only input).
        dict(name="irm_index_search", family="interaction", cls="candidate", method="POST",
             url="https://irm.cninfo.com.cn/newircs/index/search?_t=1691142650",
             data={"pageNo": "1", "pageSize": "3", "searchTypes": "1,11", "keyWord": ""},
             expect=dict(statuses=[200], json_path=["totalRecord"])),
        # W1 build anchor: min_bytes-only was status-adjacent now that
        # collectors/china_einteraction.py builds its uid map from this fragment —
        # json_path pins the envelope and min_bytes pins that it carries real markup.
        # Params corrected W1: the W0 probe posted {pageSize,page}, which is NOT the
        # endpoint's contract and intermittently answers a near-empty envelope (~375B);
        # {code,order,areaId,page} is the verified production param set the collector
        # sends (a full page-1 roster is ~11.6KB).
        dict(name="sse_einteraction", family="interaction", cls="candidate", method="POST",
             url="https://sns.sseinfo.com/allcompany.do",
             data={"code": "0", "order": "2", "areaId": "0", "page": "1"},
             headers={"Referer": "https://sns.sseinfo.com/"},
             expect=dict(statuses=[200], json_path=["content"], min_bytes=2000)),
        # W1: the per-name feed is PURE HTML (no JSON envelope), so min_bytes is the
        # only content check available; uid=65 (浦发银行) is the pinned live anchor.
        dict(name="sse_userfeeds", family="interaction", cls="candidate", method="POST",
             url="https://sns.sseinfo.com/ajax/userfeeds.do?typeCode=company&type=11&pageSize=5&uid=65&page=1",
             headers={"Referer": "https://sns.sseinfo.com/"},
             expect=dict(statuses=[200], min_bytes=2000)),
        # W1: the windowed sell-side report tape (em_report_list above probes the
        # month-window shape; this one pins the exact ~7-day window + row key the
        # collectors/china_reports.py nightly pull depends on).
        dict(name="em_report_window", family="sellside", cls="candidate", method="GET", dated=True,
             url=("https://reportapi.eastmoney.com/report/list?industryCode=*&pageSize=3&industry=*&rating=*"
                  "&ratingChange=*&beginTime=" + d_iso_7 + "&endTime=" + d_iso + "&pageNo=1&fields=&qType=0"
                  "&orgCode=&code=*&rcode=&p=1&pageNum=1&pageNumber=1"),
             expect=dict(statuses=[200], json_path=["data", 0, "infoCode"])),
        # W1: em_holdernum above probes a 3-column slice; this pins the FULL column set
        # collectors/china_holder_counts.py stores, incl. the QoQ ratio.
        dict(name="em_holdernum_full", family="positioning", cls="candidate", method="GET",
             url=(dc + "?sortColumns=HOLD_NOTICE_DATE,SECURITY_CODE&sortTypes=-1,-1&pageSize=3&pageNumber=1"
                  "&reportName=RPT_HOLDERNUMLATEST&columns=SECURITY_CODE,SECURITY_NAME_ABBR,END_DATE,"
                  "INTERVAL_CHRATE,AVG_MARKET_CAP,AVG_HOLD_NUM,TOTAL_MARKET_CAP,TOTAL_A_SHARES,HOLD_NOTICE_DATE,"
                  "HOLDER_NUM,PRE_HOLDER_NUM,HOLDER_NUM_CHANGE,HOLDER_NUM_RATIO,PRE_END_DATE&source=WEB&client=WEB"),
             expect=dict(statuses=[200], json_path=["result", "data", 0, "HOLDER_NUM_RATIO"])),
        dict(name="em_hsgt_quota", family="connect", cls="candidate", method="GET",
             url=(dc + "?reportName=RPT_MUTUAL_QUOTA&columns=ALL&source=WEB&client=WEB"
                  "&pageSize=6&sortColumns=TRADE_DATE&sortTypes=-1"),
             expect=dict(statuses=[200], json_path=["result", "data", 0, "FUNDS_DIRECTION"])),
        dict(name="chinamoney_frr_csv", family="rates", cls="candidate", method="GET",
             url="https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/frr-chrt.csv",
             expect=dict(statuses=[200], min_bytes=10000)),
        # W2 anchors carry shape checks on the exact leaves the collectors parse
        # (collectors/china_funding.py): records[].frValueMap and records[].contraRate.
        dict(name="chinamoney_frrhis", family="rates", cls="candidate", method="GET",
             url="https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/FrrHis?startDate=" + m_iso + "&endDate=" + d_iso,
             expect=dict(statuses=[200], min_bytes=2000,
                         json_path=["records", 0, "frValueMap", "FR007"])),
        dict(name="chinamoney_mm_quotes", family="rates", cls="candidate", method="POST",
             url="https://www.chinamoney.com.cn/ags/ms/cm-u-md-bond/CbMktMakQuot",
             expect=dict(statuses=[200], min_bytes=5000,
                         json_path=["records", 0, "contraRate"])),
        dict(name="jin10_shibor_cdn", family="rates", cls="candidate", method="GET",
             url="https://cdn.jin10.com/data_center/reports/il_1.json",
             expect=dict(statuses=[200], min_bytes=100000, json_path=["values"])),
        # Pinned to its observed state: 502-flaky from datacenter egress (one 200 with
        # real payload on the 2026-07-25 lane run, 502 on every same-day retry). The
        # stable path is the cdn.jin10.com mirror above. A 200 here = stabilized —
        # surfaces as CHANGED, which is exactly the news we want.
        dict(name="jin10_reports_api", family="calendar", cls="candidate", method="GET",
             url="https://datacenter-api.jin10.com/reports/list_v2?category=ec&attr_id=1&max_date=",
             headers={"x-app-id": "rU6QIu7JHe2gOUeR", "x-csrf-token": "x-csrf-token"},
             expect=dict(statuses=[502])),
        dict(name="cpca_chartlist", family="altdata", cls="candidate", method="GET",
             url="http://data.cpcadata.com/api/chartlist?charttype=1",
             expect=dict(statuses=[200], json_path=[0, "category"])),
        # W3 TIGHTENED: the old json_path pinned data.data.hasMore, a PAGINATION FLAG
        # that is present (and False) on an empty envelope — the probe would have gone
        # green on a feed carrying no news at all. The first item's newsUniqueId is the
        # leaf engine/cn_newswires.py actually keys on.
        dict(name="futu_flash", family="wire", cls="candidate", method="GET",
             url="https://news.futunn.com/news-site-api/main/get-flash-list?type=1&page=1&pageSize=3",
             expect=dict(statuses=[200], json_path=["data", "data", "news", 0, "newsUniqueId"])),
        # W3 TIGHTENED: this endpoint now REQUIRES the realtimenews Referer. Without it
        # the server drops the connection outright (empty reply, curl exit 52) — verified
        # 2026-07-27, and the W0 probe passed without it, so treat it as a tightened
        # upstream contract rather than a probe bug. The production wire sends the same
        # header; a probe that omits it would report a death the collector does not have.
        dict(name="ths_push_news", family="wire", cls="candidate", method="GET",
             url="https://news.10jqka.com.cn/tapp/news/push/stock",
             headers={"Referer": "https://news.10jqka.com.cn/realtimenews.html"},
             expect=dict(statuses=[200], json_path=["data", "list", 0, "title"])),
        # ---- W3 CNH: PBOC open-market bulletin columns (collectors/china_omo.py) ----
        # https:// deliberately — http:// answers 302. Content checks pin the COLUMN
        # NAME rather than a document id: the newest bulletin's number changes daily,
        # the column heading does not, and min_bytes catches the CMS serving a shell.
        dict(name="pboc_omo_trade_col", family="policy", cls="candidate", method="GET",
             url="https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html",
             headers={"Accept-Language": "zh-CN,zh;q=0.9"},
             expect=dict(statuses=[200], min_bytes=20000, contains="公开市场业务交易公告")),
        dict(name="pboc_omo_ann_col", family="policy", cls="candidate", method="GET",
             url="https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125469/index.html",
             headers={"Accept-Language": "zh-CN,zh;q=0.9"},
             expect=dict(statuses=[200], min_bytes=20000, contains="公开市场业务公告")),
        dict(name="pboc_omo_outright_col", family="policy", cls="candidate", method="GET",
             url="https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/5492845/index.html",
             headers={"Accept-Language": "zh-CN,zh;q=0.9"},
             expect=dict(statuses=[200], min_bytes=20000, contains="买断式逆回购")),
        dict(name="pboc_mlf_col", family="policy", cls="candidate", method="GET",
             url="https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125437/125446/125873/index.html",
             headers={"Accept-Language": "zh-CN,zh;q=0.9"},
             expect=dict(statuses=[200], min_bytes=20000, contains="中期借贷便利")),
        # W3 CNH: GACC monthly bulletin index (collectors/china_trade_detail.py). The
        # by-country row's own label is the content check — a 200 serving the site's
        # error shell has none of it.
        dict(name="gacc_monthly_bulletin", family="macro", cls="candidate", method="GET",
             url="http://english.customs.gov.cn/statics/report/monthly.html",
             expect=dict(statuses=[200], min_bytes=15000, contains="by Country")),
        # W3 CNH: the State Council policy library's static sidecar — the transport that
        # replaced the dead search API below (collectors/china_official_corpora.py,
        # organ gov_policy_library). json_path pins a DATED leaf, so a feed that goes
        # structurally valid-but-empty reads CHANGED, not OK.
        dict(name="govcn_zuixin_feed", family="policy", cls="candidate", method="GET",
             url="https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json",
             expect=dict(statuses=[200], min_bytes=50000,
                         json_path=[0, "DOCRELPUBTIME"])),
        dict(name="hkma_monetary_base", family="hk", cls="candidate", method="GET",
             url=("https://api.hkma.gov.hk/public/market-data-and-statistics/"
                  "daily-monetary-statistics/daily-figures-monetary-base?pagesize=3"),
             expect=dict(statuses=[200], json_path=["result", "records", 0, "end_of_date"])),
        # NB: this bulletin family publishes daily observations MONTHLY (latest record
        # = prior month-end). Probe checks transport, not freshness — see masterplan W5.
        dict(name="hkma_hibor_bulletin", family="hk", cls="candidate", method="GET",
             url=("https://api.hkma.gov.hk/public/market-data-and-statistics/"
                  "monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily?pagesize=3"),
             expect=dict(statuses=[200], json_path=["result", "records", 0, "end_of_day"])),
        dict(name="em_cb_list", family="bonds", cls="candidate", method="GET",
             url=(dc + "?reportName=RPT_BOND_CB_LIST&columns=SECURITY_CODE,RATING&pageSize=3"
                  "&pageNumber=1&sortColumns=PUBLIC_START_DATE&sortTypes=-1&source=WEB&client=WEB"),
             expect=dict(statuses=[200], json_path=["result", "count"])),
        # W2 anchor (collectors/china_cb.py): the KEYLESS equal-weight index history —
        # dict-of-aligned-arrays keyed by price_dt. The login-capped cb_list_new list
        # endpoint stays out of posture (CNH-R5/R6) and is deliberately NOT probed.
        dict(name="jisilu_cb_index", family="bonds", cls="candidate", method="GET",
             url="https://www.jisilu.cn/webapi/cb/index_history/",
             expect=dict(statuses=[200], min_bytes=10000,
                         json_path=["data", "price_dt", 0])),
        dict(name="sse_etf_scale", family="flows", cls="candidate", method="GET", dated=True,
             url=("https://query.sse.com.cn/commonQuery.do?sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L"
                  "&STAT_DATE=" + d_iso),
             headers={"Referer": "https://www.sse.com.cn/"},
             expect=dict(statuses=[200], min_bytes=5000)),
        dict(name="szse_etf_scale_xlsx", family="flows", cls="candidate", method="GET",
             url="https://fund.szse.cn/api/report/ShowReport?SHOWTYPE=xlsx&CATALOGID=1000_lf",
             headers={"Referer": "https://fund.szse.cn/"},
             expect=dict(statuses=[200], min_bytes=10000)),
        dict(name="fund_new_issue", family="flows", cls="candidate", method="GET",
             url="https://fund.eastmoney.com/data/FundNewIssue.aspx?t=xcln&sort=jzrgq,desc&page=1,3&isbuy=1",
             expect=dict(statuses=[200], min_bytes=300)),
        # UNSTABLE from this egress: verified 200/732B once (2026-07-25 lane run),
        # then connection-refused on every same-day retry. Opportunistic backup to
        # the gated Tushare moneyflow plane only — no wave may anchor on it.
        dict(name="em_fflow_daykline", family="flows", cls="candidate", method="GET",
             url="https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid=1.600519&klt=101&lmt=5&fields1=f1,f2,f3,f7&fields2=f51,f52,f53",
             expect=dict(statuses=[200]), flaky=True),
        # Keyless probe returns an empty envelope (rc:102, data:null) from this
        # egress even on trading days — the production zt_pool collector runs this
        # host with the gated EASTMONEY_UT_TOKEN and is fresh nightly. EMPTY here
        # is the expected keyless state; it turns OK if the anon path ever opens.
        dict(name="em_zt_pool", family="microstructure", cls="candidate", method="GET", dated=True,
             url="https://push2ex.eastmoney.com/getTopicZTPool?dpt=wz.ztzt&date=" + d8,
             expect=dict(statuses=[200], json_path=["data", "pool", 0, "c"])),
        dict(name="csindex_perf", family="index", cls="candidate", method="GET", dated=True,
             url=("https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode=000300"
                  "&startDate=" + d8_10ago + "&endDate=" + d8),
             expect=dict(statuses=[200], min_bytes=1000)),
        dict(name="czce_daily_txt", family="futures", cls="candidate", method="GET", dated=True,
             url="http://www.czce.com.cn/cn/DFSStaticFiles/Future/" + yyyy + "/" + d8 + "/FutureDataDaily.txt",
             expect=dict(statuses=[200], min_bytes=5000)),
        dict(name="shfe_daily_dat", family="futures", cls="candidate", method="GET", dated=True,
             url="https://www.shfe.com.cn/data/tradedata/future/dailydata/kx" + d8 + ".dat",
             expect=dict(statuses=[200], min_bytes=5000)),
        dict(name="cffex_month_zip", family="futures", cls="candidate", method="GET",
             url="http://www.cffex.com.cn/sj/historysj/" + ym + "/zip/" + ym + ".zip",
             head_only=True,  # ~480KB zip; magic-check the first bytes, don't download
             expect=dict(statuses=[200])),
        dict(name="gacc_english", family="macro", cls="candidate", method="GET",
             url="http://english.customs.gov.cn/",
             expect=dict(statuses=[200], min_bytes=5000)),
        # DEAD TO UNAUTHENTICATED CALLERS as of 2026-07-27: the API answers 200 and
        # echoes every parameter back, with searchVO.totalCount pinned at 0 — verified
        # across three param variants, with a cookie warm-up and with the site referer.
        # KEPT as a candidate rather than deleted (probe-revival law CNH-R5): a nonzero
        # totalCount here is actionable news. The live replacement transport is
        # govcn_zuixin_feed above, which is what W3 actually built on.
        dict(name="govcn_policy_search", family="policy", cls="candidate", method="GET",
             url="https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary&q=%E5%88%A9%E7%8E%87&timetype=timeqb&mintime=&maxtime=&sort=score&sortType=1&searchfield=title&pcodeJiguan=&childtype=&subchildtype=&tsbq=&pubtimeyear=&puborg=&pcodeYear=&pcodeNum=&filetype=&p=1&n=5",
             expect=dict(statuses=[200], json_path=["searchVO", "totalCount"])),
        # ---- integrated transports (regression watch on existing collectors) ----
        dict(name="cninfo_hisannouncement", family="disclosure", cls="integrated", method="POST",
             url="http://www.cninfo.com.cn/new/hisAnnouncement/query",
             data={"pageNum": "1", "pageSize": "3", "column": "szse", "tabName": "fulltext",
                   "seDate": d_iso + "~" + d_iso},
             expect=dict(statuses=[200], min_bytes=100)),
        dict(name="em_datacenter_lhb", family="microstructure", cls="integrated", method="GET",
             url=(dc + "?reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&pageSize=3&pageNumber=1"
                  "&sortColumns=TRADE_DATE&sortTypes=-1&source=WEB&client=WEB"),
             expect=dict(statuses=[200], json_path=["result", "data", 0, "TRADE_DATE"])),
        dict(name="sina_hq_quote", family="quotes", cls="integrated", method="GET",
             url="https://hq.sinajs.cn/list=sh600519",
             headers={"Referer": "https://finance.sina.com.cn/"},
             expect=dict(statuses=[200], min_bytes=100)),
        dict(name="wallstreetcn_feed", family="wire", cls="integrated", method="GET",
             url="https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=3",
             expect=dict(statuses=[200], json_path=["data", "items", 0, "id"])),
        dict(name="hkexnews_search", family="hk", cls="integrated", method="GET",
             url="https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en",
             expect=dict(statuses=[200], min_bytes=5000)),
        # ---- known-dead (drift detection: a change here is actionable) ----
        dict(name="nbs_easyquery", family="macro", cls="dead", method="POST",
             url="https://data.stats.gov.cn/easyquery.htm", data={"m": "getTree"},
             expect=dict(statuses=[403])),
        dict(name="em_push2_clist", family="quotes", cls="dead", method="GET",
             url="https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=3&fs=m:0+t:6&fid=f3&fields=f12,f14",
             expect=dict(statuses=[502])),
        dict(name="cls_nodeapi", family="wire", cls="dead", method="GET",
             url="https://www.cls.cn/nodeapi/telegraphList",
             expect=dict(statuses=[404])),
        # thepaper answers 200 wrapping a tiny error envelope ({"code":99998,
        # 系统繁忙}, ~84B). max_bytes pins that state: a REAL revival (200 with
        # content) exceeds the cap and surfaces as CHANGED.
        dict(name="thepaper_api", family="wire", cls="dead", method="GET",
             url="https://api.thepaper.cn/contentapi/nodeCont/getByChannelId",
             expect=dict(statuses=[200, 403, 404], max_bytes=500)),
        dict(name="xueqiu_quote_noauth", family="sentiment", cls="dead", method="GET",
             url="https://stock.xueqiu.com/v5/stock/quote.json?symbol=SH600519",
             expect=dict(statuses=[400, 401, 403])),
        dict(name="mofcom_data_tls", family="macro", cls="dead", method="GET",
             url="https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery",
             expect=dict(error=True)),
        dict(name="shibor_org_dns", family="rates", cls="dead", method="GET",
             url="https://www.shibor.org/",
             expect=dict(error=True)),
    ]


def _content_checks(p: dict, r: requests.Response, out: dict) -> str:
    """Apply json_path/min_bytes/max_bytes. Returns verdict."""
    exp = p.get("expect", {})
    nbytes = len(r.content)
    if exp.get("max_bytes") is not None and nbytes > exp["max_bytes"]:
        out["field"] = f"bytes>{exp['max_bytes']} (possible revival/real content)"
        return "CHANGED"
    content_ok = True
    if exp.get("min_bytes") is not None and nbytes < exp["min_bytes"]:
        out["field"] = f"bytes<{exp['min_bytes']}"
        content_ok = False
    # `contains`: the HTML analogue of json_path. An HTML endpoint has no envelope to
    # dig into, so the check is that the page still carries the LABEL the parser keys
    # on (a column heading, a table caption) — stable across days, unlike any document
    # id, and absent from the error shells these CMSes serve with a 200.
    needle = exp.get("contains")
    if content_ok and needle:
        found = needle in _page_text(r)
        out["field"] = (("contains " if found else "MISSING ") + needle
                        ).encode("ascii", "backslashreplace").decode()
        content_ok = found
    jp = exp.get("json_path")
    if content_ok and jp:
        try:
            val = _dig(r.json(), jp)
            if val is None:
                raise KeyError("null leaf")
            out["field"] = str(val)[:60].encode("ascii", "backslashreplace").decode()
        except Exception:
            out["field"] = "JSON-SHAPE-MISMATCH"
            content_ok = False
    if content_ok:
        return "OK"
    # Dated probes go contentless on CN/HK holidays — informative, not a failure.
    return "EMPTY" if p.get("dated") else "CHANGED"


def run_probe(p: dict, _attempt: int = 0) -> dict:
    h = dict(UA)
    h.update(p.get("headers") or {})
    out = dict(name=p["name"], family=p["family"], cls=p["cls"], url=p["url"])
    exp = p.get("expect", {})
    try:
        if p.get("head_only"):
            r = requests.get(p["url"], headers=h, timeout=TIMEOUT, stream=True)
            first = next(r.iter_content(chunk_size=4), b"")
            out["status"], out["bytes"] = r.status_code, len(first)
            out["field"] = "magic=" + first[:4].hex()
            r.close()
            out["verdict"] = "OK" if r.status_code in exp.get("statuses", [200]) else "CHANGED"
            return out
        r = requests.request(p["method"], p["url"], headers=h, data=p.get("data"),
                             timeout=TIMEOUT)
        out["status"] = r.status_code
        out["bytes"] = len(r.content)
        if exp.get("error"):
            out["verdict"] = "CHANGED"  # expected a network error, got an HTTP response
            return out
        if r.status_code not in exp.get("statuses", [200]):
            # Dated file endpoints legitimately 404 on holidays.
            out["verdict"] = "EMPTY" if (p.get("dated") and r.status_code == 404) else "CHANGED"
            return out
        out["verdict"] = _content_checks(p, r, out)
        return out
    except requests.RequestException as e:
        # One polite retry for endpoints NOT expected to error: distinguishes a
        # transient edge drop from a hard block (DNS/TLS deaths fail both times).
        if _attempt == 0 and not exp.get("error") and not p.get("flaky"):
            time.sleep(3.0)
            return run_probe(p, _attempt=1)
        out["status"] = None
        out["error"] = type(e).__name__
        if exp.get("error"):
            out["verdict"] = "OK"
        elif p.get("flaky"):
            out["verdict"] = "FLAKY"
            out["note"] = "known-flaky endpoint; network error within baseline"
        else:
            out["verdict"] = "ERR"
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", help="write structured results to this path")
    ap.add_argument("--only", help="probe family filter (e.g. wire, rates, hk)")
    args = ap.parse_args()

    probes = build_probes()
    if args.only:
        families = sorted({p["family"] for p in probes})
        if args.only not in families:
            raise SystemExit(
                f"unknown family {args.only!r}; valid families: {', '.join(families)}"
            )
        probes = [p for p in probes if p["family"] == args.only]

    results = []
    counts = {"OK": 0, "EMPTY": 0, "FLAKY": 0, "CHANGED": 0, "ERR": 0}
    last_hit: dict[str, float] = {}
    for p in probes:
        host = urllib.parse.urlparse(p["url"]).netloc
        wait = HOST_THROTTLE_S - (time.monotonic() - last_hit.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        res = run_probe(p)
        last_hit[host] = time.monotonic()
        results.append(res)
        counts[res["verdict"]] = counts.get(res["verdict"], 0) + 1
        note = res.get("field") or res.get("error") or ""
        print(f"{res['cls']:10s} {res['name']:26s} {str(res.get('status')):>4s} "
              f"{res['verdict']:7s} {res.get('bytes', ''):>8} {note}")

    deviating = counts["CHANGED"] + counts["ERR"]
    print(f"\n{len(results)} probes: {counts['OK']} ok / {counts['EMPTY']} empty-dated "
          f"(holiday or upstream change — investigate if a trading day) / "
          f"{counts['FLAKY']} flaky-degraded / {deviating} deviating.")
    if args.json:
        payload = dict(
            schema="china_source_probe.v2",
            probed_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            note="verdicts are egress-relative; see script docstring",
            counts=counts,
            results=results,
        )
        with open(args.json, "w") as fh:
            json.dump(payload, fh, indent=1, ensure_ascii=True)
        print(f"wrote {args.json}")
    return 0 if deviating == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
