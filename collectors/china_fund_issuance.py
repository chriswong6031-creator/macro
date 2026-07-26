"""China new-fund issuance (新发基金) — the retail risk-appetite proxy nobody publishes
as a series. Masterplan W2, research/china_native_data/CHINA_HK_NATIVE_DATA_MASTERPLAN_BY_FABLE.md
§W2. DISPLAY-TIER CONTEXT ONLY: collected and accruing, never scored or ranked.

  issuance  weekly aggregates of newly ESTABLISHED funds (已成立/新成立基金) from
            EastMoney's 天天基金 new-issue table: how many funds actually closed their
            raise that week, how many 亿份 of shares they raised, and the equity-vs-bond
            split. Retail money committing to equity funds is the cleanest free read on
            mainland household risk appetite; a week of bond-only issuance says the
            opposite of a week of 混合/指数 launches.

PIT semantics: each row is dated by the week's FRIDAY, derived from the UPSTREAM
成立日期 (establishment date) — never by collection time. The nightly window covers the
400 most recent rows, so an upsert recomputes only the weeks that window reaches; older
weeks on disk are untouched. Recomputing a recent week is correct rather than lossy: it
is the same aggregation over a fuller row set (new-wins on collision), and a week with
zero parseable establishments is DROPPED rather than written as a zero row. The one
exception is the OLDEST week the window reaches — the window cuts it mid-week, so a
recompute would undercount it; that boundary bin is dropped from every nightly write
(the store keeps the value the week earned while fully inside the window).

Caveats worth stating out loud:
  * the source is a LIVE ROLLING LIST, not an archive — historical completeness for
    long-dead funds is UNVERIFIED, so early weeks in the deep seed may undercount.
  * 募集份额 is in 亿份 (hundreds of millions of SHARES) per the page's own column
    label — shares, not yuan; a share is ~1.00 CNY at launch but that is not a
    guarantee, so nothing here is converted to currency.
  * a fund still raising has an EMPTY 募集份额 and often an empty 成立日期; those rows
    are excluded until they actually close (no zero-fill).

Pacing: one HTTP call per run. --full-history asks the same endpoint for the whole
list in a single shot (page "1,50000") — off the render path by construction.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# VERIFIED live 2026-07-25 (see SOURCE_CATALOG_MARKET.md): t=xcln is the 新成立 tab and
# isbuy=1 is required — without them the endpoint serves an empty/legacy payload.
_FUND_NEW_ISSUE = "https://fund.eastmoney.com/data/FundNewIssue.aspx"
_NIGHTLY_PAGE = "1,400"      # rolling window: the ~400 most recent rows
_FULL_PAGE = "1,50000"       # one-shot deep backfill, --full-history only

# datas[] row positions (VERIFIED against the live 19-field rows).
_I_CODE = 0            # fund code
_I_NAME = 1            # fund name
_I_ISSUER = 2          # fund company
_I_TYPE = 4            # type string, e.g. "混合型-灵活" / "债券型-长债" / "指数型-股票"
_I_SHARES = 5          # 募集份额 in 亿份 — EMPTY STRING while the fund is still raising
_I_ESTABLISHED = 6     # 成立日期 "YYYY-MM-DD" (may be empty)
_I_MANAGER = 8         # 基金经理
_I_STATUS = 9          # 申购状态
_I_WINDOW = 10         # 集中认购期

_EQUITY_KW = ("股票", "混合", "指数")
_BOND_KW = ("债",)

# Bare-key -> quoted-key rewrite for the JS-variable payload (`{datas:[...],curpage:1}`
# is not valid JSON until its keys are quoted).
_BARE_KEY_RE = re.compile(r'([{,])\s*(\w+)\s*:')


def unwrap_js_payload(text: str) -> dict:
    """`var newfunddata={datas:[[...]],curpage:1,pages:1,record:400};` -> dict.

    Strips everything up to the first '=', drops the trailing ';', quotes the bare
    object keys, then json.loads. Pure; raises ValueError on anything that is not a
    JS variable assignment so a changed wrapper fails loudly instead of parsing to {}.
    """
    if "=" not in (text or ""):
        raise ValueError("fund issuance: payload is not a JS variable assignment")
    body = text.split("=", 1)[1].strip()
    body = body.rstrip().rstrip(";").strip()
    body = _BARE_KEY_RE.sub(r'\1"\2":', body)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"fund issuance: unwrapped body is not JSON ({e})") from e
    if not isinstance(payload, dict):
        raise ValueError("fund issuance: unwrapped payload is not an object")
    return payload


def classify_type(type_str: str) -> str:
    """Fund type string -> 'equity' | 'bond' | 'other' (mutually exclusive).

    equity = 股票 / 混合 / 指数, bond = 债. BOND WINS an overlap (偏债混合 carries both
    keyword families and is a bond-tilted product), so the three share columns partition
    shares_yi exactly and other_shares_yi can never go negative. Pure.
    """
    t = str(type_str or "")
    if any(k in t for k in _BOND_KW):
        return "bond"
    if any(k in t for k in _EQUITY_KW):
        return "equity"
    return "other"


def aggregate_weekly(datas: list) -> pd.DataFrame:
    """datas[] rows -> weekly aggregates indexed by the week's FRIDAY (W-FRI bins).

    Keeps only rows with BOTH a parseable 成立日期 and a numeric 募集份额 (a fund still
    raising has neither). Empty weeks inside the span are dropped, never written as a
    zero row. Pure — no I/O, no clock.
    """
    recs: list[dict] = []
    for row in datas or []:
        if not isinstance(row, (list, tuple)) or len(row) <= _I_ESTABLISHED:
            continue
        est = pd.to_datetime(str(row[_I_ESTABLISHED] or "").strip(), errors="coerce")
        shares = pd.to_numeric(str(row[_I_SHARES] or "").strip(), errors="coerce")
        if pd.isna(est) or pd.isna(shares):
            continue
        recs.append({"est": est.normalize(), "shares": float(shares),
                     "cls": classify_type(row[_I_TYPE] if len(row) > _I_TYPE else "")})
    if not recs:
        raise ValueError("fund issuance: no rows carried both a 成立日期 and a 募集份额")
    df = pd.DataFrame(recs).set_index("est").sort_index()
    df["is_equity"] = (df["cls"] == "equity").astype(float)
    for cls, col in (("equity", "_eq"), ("bond", "_bd"), ("other", "_ot")):
        df[col] = df["shares"].where(df["cls"] == cls, 0.0)
    grp = df.groupby(pd.Grouper(freq="W-FRI"))
    out = pd.DataFrame({
        "n_funds": grp.size().astype(float),
        "shares_yi": grp["shares"].sum(),
        "equity_n": grp["is_equity"].sum(),
        "equity_shares_yi": grp["_eq"].sum(),
        "bond_shares_yi": grp["_bd"].sum(),
        "other_shares_yi": grp["_ot"].sum(),
    })
    out = out[out["n_funds"] > 0]        # drop empty W-FRI bins (no zero-fill)
    out.index.name = None
    return out.sort_index()


class ChinaFundIssuanceAdapter(Adapter):
    name = "china_fund_issuance"
    group = "china_fund_issuance"   # 'china_' prefix auto-routes to the asia lane
    stale_after_days = 12           # weekly cadence: one quiet week is not staleness

    def _h(self, referer: str) -> dict:
        return {"User-Agent": _UA, "Referer": referer}

    def _issuance(self, full_history: bool) -> pd.DataFrame:
        params = {"t": "xcln", "sort": "jzrgq,desc", "y": "",
                  "page": _FULL_PAGE if full_history else _NIGHTLY_PAGE,
                  "isbuy": "1"}
        r = self.http_get(_FUND_NEW_ISSUE, params=params, retries=2,
                          headers=self._h("https://fund.eastmoney.com/data/"),
                          timeout=30)
        payload = unwrap_js_payload(r.text)
        out = aggregate_weekly(payload.get("datas") or [])
        if not full_history and len(out) > 1:
            # Boundary-week guard: the OLDEST week inside the rolling 400-row window
            # is only PARTIALLY covered (the window cuts mid-week), so recomputing it
            # would overwrite the fuller aggregate written while it was younger with
            # an undercount (upsert is new-wins). Drop that bin; the store keeps the
            # value it earned when the week was fully inside the window.
            out = out.iloc[1:]
        log.info("china_fund_issuance: %d weekly rows %s..%s (record=%s, page=%s)",
                 len(out), out.index.min().date(), out.index.max().date(),
                 payload.get("record"), params["page"])
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for key, fn in (("issuance", self._issuance),):
            try:
                frames[key] = fn(full_history)
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("china_fund_issuance %s failed: %s", key, e)
        if not frames:
            raise RuntimeError("china_fund_issuance: all series failed — "
                               + " | ".join(errors))
        return frames
