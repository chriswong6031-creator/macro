"""PBOC open-market-operation BULLETIN tape — the OBSERVED OMO plane (W3 CNH).

The 人民银行 publishes every open-market operation as a numbered bulletin on
www.pbc.gov.cn. Four columns are polled nightly, each a different document shape:

  trade         公开市场业务交易公告      the DAILY RESULT (a table: 期限/操作利率/投标量/中标量)
  announcement  公开市场业务公告          the PRE-announcement of coming operations
                                          (量价分离: the amounts are stated, the rate is not)
  outright      公开市场买断式逆回购招标公告 the outright reverse-repo tender
  mlf           中期借贷便利招标公告       the MLF tender

This is the OBSERVED plane. It is a different fact from the synthetic FR007-z
events engine/china_policy_transmission.py seeds under ``kind="omo_mlf"``: those
are DERIVED from a rate series, these are what the central bank actually printed.
The two never share a kind — every event this collector appends carries
``kind="omo_observed"`` and ``provenance="pboc_bulletin"`` (W3 red-team ruling),
so a reader can always tell an announced operation from an inferred one.

CONTEXT / DISPLAY TIER ONLY. Nothing here is scored, ranked, sized or promoted,
and nothing gates a risk or state channel.

Two stores under data/china_omo/:
  operations.parquet  one row per (bulletin url, op_date, tenor) — a bulletin that
                      announces four operation days becomes four rows. Dedup
                      keep-LAST so a re-fetched bulletin CORRECTS its row, with
                      first_seen carried through the merge (W1 F8).
  refresh.parquet     the nightly coverage sentinel (written by the adapter).

VERIFIED TRANSPORT (live 2026-07-27, this runner):
  * Use **https://** directly — http:// answers 302 and costs a redirect hop.
  * A browser User-Agent is required (same law as collectors/china_official_corpora.py).
  * The daily 交易公告 lands ~09:20–09:30 Beijing time.
  * List markup mixes quote styles: the sidebar column links are SINGLE-quoted
    (``href='/zhengcehuobisi/...'``) while entry links are double-quoted, so the
    entry regex accepts both (and bare/unquoted, for good measure).
  * Bulletin numbers appear with BOTH bracket families: 交易公告 uses ASCII
    ``[2026]第143号``, 公开市场业务公告 uses full-width ``［2026］第5号``.

UNITS — read this before using amount_bn: the bulletins state sizes in 亿元
(100 million yuan) and the columns store that figure VERBATIM, unconverted.
``amount_bn = 3255`` means 3255亿元 (= CNY 325.5bn). The column name follows the
W3 spec; the unit is 亿元, not billions.

TENOR_DAYS IS NOT COMPARABLE ACROSS COLUMNS — do not join on it. The trade column's
result tables print a bare 期限 label ("6个月"), so tenor_days there is the ×30
CONVENTION (180); the outright tenders print the contractual day count in their own
parentheses ("6个月（184天）"), so tenor_days there is the bulletin's own 184. Two
rows can carry the same tenor_label and different tenor_days for that reason, and a
consumer that keys a maturity ladder on tenor_days will silently mis-bucket the
conventional ones. Key on (column, tenor_label) and treat a ×30 value as an
approximation whose provenance is the missing parenthesis.

Politeness + budget: ≥1.1 s + jitter before EVERY request to the single host
(pbc.gov.cn is shared with the serial china_official_corpora / china_credit
adapters, which is why this collector deliberately stays OUT of
scripts/collect.py ``_CONCURRENT_HOSTS``), a 20-detail-fetch nightly cap and a
~100 s wall-clock guard. Whatever the cap or the guard leaves uncrawled is NOT
stored, is counted in the ``n_deferred`` sentinel column, and is picked up on the
next night — the first night seeds ~35 documents and drains over two nights,
which the sentinel makes visible instead of silently truncating.

A 0-row night is a success. RuntimeError is raised only when EVERY column page
failed at transport level — the honest circuit-breaker signal.
"""
from __future__ import annotations

import argparse
import logging
import math
import os
import random
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger("china_omo")

# ------------------------------------------------------------------ constants --

GROUP = "china_omo"
_HOST = "https://www.pbc.gov.cn"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# The four polled column pages. ``column`` is stored verbatim on every row so a
# reader can always tell which archive a document came from.
COLUMNS: tuple[dict, ...] = (
    {"column": "trade",
     "url": _HOST + "/zhengcehuobisi/125207/125213/125431/125475/index.html",
     "name": "公开市场业务交易公告"},
    {"column": "announcement",
     "url": _HOST + "/zhengcehuobisi/125207/125213/125431/125469/index.html",
     "name": "公开市场业务公告"},
    {"column": "outright",
     "url": _HOST + "/zhengcehuobisi/125207/125213/125431/5492845/index.html",
     "name": "公开市场买断式逆回购业务公告"},
    {"column": "mlf",
     "url": _HOST + "/zhengcehuobisi/125207/125213/125437/125446/125873/index.html",
     "name": "中期借贷便利"},
)

_DETAIL_CAP = 20        # detail fetches per night; the remainder is n_deferred, never dropped
_PACE_S = 1.1           # ≤1 req/s/host, jittered
_JITTER_S = 0.3
_TIMEOUT = (10, 20)     # (connect, read)
_BUDGET_S = 100.0       # in-collector wall-clock guard

PROVENANCE = "pboc_bulletin"
EVENT_KIND = "omo_observed"   # NEVER "omo_mlf" — that namespace holds synthetic FR007-z events

_OPS_COLUMNS: tuple[str, ...] = (
    "announce_date",   # the LIST page's date for the bulletin (document date, never our clock)
    "op_date",         # the operation date the bulletin states
    "bulletin_no",     # "2026-143"; '' for the MLF tenders, whose titles carry no number
    "column",          # trade | announcement | outright | mlf
    "kind",            # reverse_repo | reverse_repo_preannounce | outright_repo_tender | mlf_tender | other
    "tenor_label",     # 7天 / 隔夜 / 6个月 / 1年期 …
    "tenor_days",
    "rate_pct",        # NaN when the bulletin states no rate (量价分离 / 利率招标)
    "amount_bn",       # 亿元, VERBATIM (see the module docstring)
    "bid_bn",          # 投标量 (result bulletins only)
    "awarded_bn",      # 中标量 (result bulletins only)
    "maturity_date",
    "title",
    "url",             # the bulletin URL — part of the dedup key
    "provenance",
    "first_seen",      # FIRST observation — never overwritten by a keep-LAST correction
    "fetched_at",      # LAST observation
)

_KEY = ["url", "op_date", "tenor_label"]

# The nightly coverage sentinel's columns, in order. n_store_abort is the halt flag:
# a night that could not READ the accrued store fetches nothing and appends nothing,
# and this is the column that says so (see refresh()).
_SENTINEL_COLUMNS: tuple[str, ...] = (
    "n_new", "n_fetched", "n_failed", "n_nulls", "n_deferred", "n_store_abort",
    "columns_polled")

# Fields whose absence is a COVERAGE NULL worth counting in the sentinel. bid/awarded
# are deliberately excluded: a pre-announcement has no tender result yet, so counting
# them would make every announcement look like a data gap.
_NULLABLE_CORE = ("op_date", "tenor_days", "rate_pct", "amount_bn")


# ------------------------------------------------------------------ paths / stores --

def _dir() -> Path:
    p = config.data_dir() / GROUP
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ops_path() -> Path:
    return _dir() / "operations.parquet"


def _read_store(path: Path, columns: tuple[str, ...]) -> pd.DataFrame | None:
    """The store reindexed to ``columns``, an EMPTY frame when ABSENT, None when UNREADABLE.

    Three different facts, which is why this is not a plain try/except returning an
    empty frame: "absent" is the first night (append freely), while "present but
    unreadable" means the accrued history is still on disk and we simply cannot see
    it — taking the empty-store branch there would replace all of it with tonight's
    handful of rows. The caller ABORTS on None.
    """
    if not path.exists():
        return pd.DataFrame(columns=list(columns))
    try:
        return pd.read_parquet(path).reindex(columns=list(columns))
    except Exception as e:  # noqa: BLE001
        log.error("china_omo: %s is present but UNREADABLE (%s)", path.name, e)
        return None


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` via a tmp sibling + os.replace — never a truncated store.

    The asia lane runs under a hard job kill that has fired mid-chain before; a
    to_parquet() straight onto the live path turns that kill into a corrupt file.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — never leave a half-written sibling behind
        tmp.unlink(missing_ok=True)
        raise


def _restore_first_seen(merged: pd.DataFrame, existing: pd.DataFrame,
                        key: list[str]) -> pd.DataFrame:
    """Carry each key's ORIGINAL first_seen through the keep-LAST merge. Pure.

    fetched_at means "last observed" and advances on every correction; first_seen
    means "first observed" and must not. It is the one question an append-only PIT
    store exists to answer, and a keep-LAST dedup would otherwise overwrite it every
    time a bulletin is re-fetched. Keys absent from ``existing`` keep tonight's stamp.
    """
    if existing.empty or "first_seen" not in existing.columns:
        return merged
    prior = existing[[*key, "first_seen"]].astype(str)
    prior = prior[prior["first_seen"].str.strip().ne("")
                  & ~prior["first_seen"].isin(("nan", "None", "NaT", "<NA>"))]
    if prior.empty:
        return merged
    prior = prior.sort_values("first_seen").drop_duplicates(subset=key, keep="first")
    lookup = dict(zip(zip(*(prior[c] for c in key)), prior["first_seen"]))
    out = merged.copy()
    out["first_seen"] = [
        lookup.get(k, cur)
        for k, cur in zip(zip(*(out[c].astype(str) for c in key)), out["first_seen"])
    ]
    return out


def load_operations() -> pd.DataFrame:
    """Existing operations.parquet, or an empty frame with the canonical schema.

    A present-but-unreadable store also reads as empty HERE — a reader must not
    crash — but write_operations() checks readability separately and aborts, so the
    empty frame can never be written back over the real one.
    """
    df = _read_store(_ops_path(), _OPS_COLUMNS)
    return pd.DataFrame(columns=list(_OPS_COLUMNS)) if df is None else df


def stored_urls() -> set[str]:
    """URLs already on disk — the diff set that decides which details to fetch."""
    df = load_operations()
    if df.empty or "url" not in df.columns:
        return set()
    return {u for u in df["url"].astype(str) if u and u != "nan"}


def write_operations(rows: list[dict]) -> int:
    """Append operation rows, dedup (url, op_date, tenor_label) keep-LAST. Never raises.

    Keep-LAST is deliberate: the PBOC edits a published bulletin occasionally (a typo
    in an amount, a clarified maturity), and a re-fetch must CORRECT the stored row
    rather than be discarded. first_seen is carried through the merge, so the
    correction advances fetched_at without losing the first-observation time.

    An existing-but-UNREADABLE operations.parquet ABORTS the append (returns 0, file
    left in place for manual recovery): the alternative — reading it as an empty store
    — would replace the entire accrued tape with tonight's handful of bulletins.
    """
    if not rows:
        return 0
    try:
        existing = _read_store(_ops_path(), _OPS_COLUMNS)
        if existing is None:
            log.error("china_omo: ABORTING the operations.parquet append — the accrued "
                      "store is unreadable and is left untouched for manual recovery")
            return 0
        new_df = pd.DataFrame(rows).reindex(columns=list(_OPS_COLUMNS))
        new_df["first_seen"] = new_df["first_seen"].fillna(new_df["fetched_at"])
        for c in _KEY:
            new_df[c] = new_df[c].fillna("").astype(str)
        if existing.empty:
            merged = new_df.drop_duplicates(subset=_KEY, keep="last")
            net_new = len(merged)
        else:
            for c in _KEY:
                existing[c] = existing[c].fillna("").astype(str)
            pre = len(existing.drop_duplicates(subset=_KEY))
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=_KEY, keep="last")
            merged = _restore_first_seen(merged, existing, _KEY)
            net_new = len(merged) - pre
        merged = merged.sort_values(["op_date", "url", "tenor_label"],
                                    na_position="last").reset_index(drop=True)
        _atomic_write(merged, _ops_path())
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("china_omo.write_operations failed: %s", e)
        return 0


# ------------------------------------------------------------------ text helpers --

_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.I)
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")
_WS_RE = re.compile(r"\s+")
_ENTITIES = (("&nbsp;", " "), ("&#160;", " "), ("&amp;", "&"), ("&lt;", "<"),
             ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"))


def _decode(content: bytes, content_type: str = "") -> str:
    """Decode HTML bytes honoring the real charset (gb2312/gbk → gb18030). PURE.

    pbc.gov.cn serves utf-8 today, but the same CMS serves gb2312 on some archived
    columns — the mirror of collectors/china_official_corpora._decode.
    """
    enc = None
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        enc = m.group(1)
    if not enc:
        mm = _META_CHARSET_RE.search(content[:4096])
        if mm:
            enc = mm.group(1).decode("ascii", "ignore")
    enc = (enc or "utf-8").strip().lower()
    if enc in {"gb2312", "gbk", "gb-2312"}:
        enc = "gb18030"
    try:
        return content.decode(enc, errors="replace")
    except (LookupError, TypeError):
        return content.decode("utf-8", errors="replace")


def _plain(html_text: str) -> str:
    """Tags/entities stripped, whitespace COLLAPSED to single spaces. PURE."""
    s = _SCRIPT_STYLE_RE.sub(" ", html_text or "")
    s = _TAG_RE.sub(" ", s)
    for a, b in _ENTITIES:
        s = s.replace(a, b)
    return _WS_RE.sub(" ", s).replace(" ", " ").strip()


def _dense(html_text: str) -> str:
    """Tags/entities stripped and ALL whitespace REMOVED. PURE.

    Load-bearing, not cosmetic: the PBOC CMS splits单个词 across nested <span>s —
    the 143号 result table renders the rate as ``<span>1.</span><span>40</span>``
    and the tenor as ``<span>7</span><span>天</span>``. Collapsing to single spaces
    leaves "1. 40 %" and "7 天"; removing whitespace entirely restores "1.40%" and
    "7天". Safe here because every field parsed from this text is CJK + digits.
    """
    return re.sub(r"\s+", "", _plain(html_text))


def zoom_html(html_text: str) -> str:
    """Inner HTML of the article's ``<div id="zoom">`` body, or ''. PURE.

    Depth-counted rather than "up to the first </div>" so a bulletin that ever wraps
    its table in a nested div does not get truncated mid-document.
    """
    m = re.search(r"""(?is)<div[^>]*\bid\s*=\s*["']?zoom["']?[^>]*>""", html_text or "")
    if not m:
        return ""
    start = m.end()
    depth, pos = 1, start
    token = re.compile(r"(?i)<div\b|</div\s*>")
    while depth > 0:
        t = token.search(html_text, pos)
        if not t:
            return html_text[start:]
        depth += 1 if t.group(0).lower().startswith("<div") else -1
        pos = t.end()
        if depth == 0:
            return html_text[start:t.start()]
    return html_text[start:pos]


# ------------------------------------------------------------------ value parsers --

_FULL_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_CJK_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
               "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _num(text: str):
    """First number in ``text`` as float, NaN when absent. PURE, never raises."""
    m = re.search(r"-?\d+(?:\.\d+)?", (text or "").replace(",", ""))
    if not m:
        return float("nan")
    try:
        return float(m.group(0))
    except ValueError:
        return float("nan")


def _iso(y: int, mo: int, d: int) -> str:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def _cjk_year(text: str) -> int | None:
    """'二〇二六年' → 2026. PURE. Bulletin signature blocks use CJK numerals."""
    m = re.search(r"([〇零一二三四五六七八九]{4})年", text or "")
    if not m:
        return None
    try:
        return int("".join(str(_CJK_DIGITS[c]) for c in m.group(1)))
    except (KeyError, ValueError):
        return None


def document_year(dense_text: str, announce_date: str = "") -> int | None:
    """The YEAR a month/day-only operation date belongs to. PURE.

    Never our clock (house law: document dates come from the document). Preference
    order: the LIST page's announce date → the first ``YYYY年`` in the body → the
    CJK-numeral signature year (``二〇二六年七月二十四日``). None when the document
    states no year at all, in which case the caller emits no dated row.
    """
    if announce_date and len(announce_date) >= 4 and announce_date[:4].isdigit():
        return int(announce_date[:4])
    m = re.search(r"(\d{4})年", dense_text or "")
    if m:
        return int(m.group(1))
    return _cjk_year(dense_text or "")


def _dated(month: int, day: int, year: int, announce_date: str) -> str:
    """(month, day) → ISO, rolling the year across a year boundary in EITHER direction.

    A 12月28日 pre-announcement covering 1月2日 operations is a real shape; naively
    stamping the announcement's year would file that operation eleven months in the
    past. The mirror image is just as real and just as wrong in the other direction: a
    early-January bulletin that REFERS BACK to a 12月30日 operation (a maturity, a
    correction, a settled leg) would otherwise be filed eleven months into the future.

    Both rolls fire only on a >6-month jump, so an ordinary same-month or next-month
    clause is untouched:
      announce 12月, op 1月  → year + 1
      announce 1月,  op 12月 → year − 1
    """
    if announce_date and len(announce_date) >= 7:
        try:
            a_month = int(announce_date[5:7])
            if a_month - month > 6:
                year += 1
            elif month - a_month > 6:
                year -= 1
        except ValueError:
            pass
    return _iso(year, month, day)


def tenor_days(label: str):
    """'7天'→7, '隔夜'→1, '1年期'→365, '6个月（184天）'→184, '6个月'→180. PURE.

    A parenthesized day count is the bulletin's OWN arithmetic and always wins — the
    outright repos are quoted as "6个月（184天）" and 184 is the contractual tenor,
    not 6×30. Months without a stated day count fall back to ×30 (the W3 spec's
    convention), which is why the label is stored alongside: a reader can see that
    180 was derived, not printed.
    """
    s = re.sub(r"\s+", "", label or "")
    if not s:
        return float("nan")
    m = re.search(r"[（(](\d+)天[）)]", s)
    if m:
        return float(m.group(1))
    if "隔夜" in s:
        return 1.0
    m = re.search(r"(\d+)天", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+)个月", s)
    if m:
        return float(m.group(1)) * 30.0
    m = re.search(r"(\d+)年", s)
    if m:
        return float(m.group(1)) * 365.0
    return float("nan")


def bulletin_no(title: str) -> str:
    """'公开市场业务交易公告 [2026]第143号' → '2026-143'; '' when unnumbered. PURE.

    BOTH bracket families occur live: 交易公告 prints ASCII ``[2026]``, 公开市场业务公告
    prints full-width ``［2026］``. The MLF tender titles carry no number at all
    ('2026年7月中期借贷便利招标公告'), which is why the empty string is a legal value
    and never a parse failure.
    """
    m = re.search(r"[\[［]\s*(\d{4})\s*[\]］]\s*第\s*(\d+)\s*号", title or "")
    return f"{m.group(1)}-{int(m.group(2))}" if m else ""


# ------------------------------------------------------------------ list pages --

# href is matched for double-quoted, single-quoted AND bare attributes: the PBOC
# sidebar column links are single-quoted while entry links are double-quoted, and the
# same CMS emits bare hrefs elsewhere. The backreference is empty for the bare case.
_ANCHOR_RE = re.compile(r"""(?is)<a\s[^>]*?href=(["']?)([^"'\s>]+)\1[^>]*>(.*?)</a>""")
# A bulletin LEAF: the column path plus a long numeric document id. Column index
# pages (…/125475/index.html) have no such id and are therefore never entries.
_LEAF_RE = re.compile(r"/zhengcehuobisi/(?:\d+/)+(\d{8,})/index\.html$")
_LIST_DATE_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")


def extract_entries(html_text: str, base_url: str) -> list[dict]:
    """Bulletin leaves on a column/landing page as [{url, title, list_date}]. PURE.

    Document order is preserved (the CMS prints newest first) and URLs are deduped
    keep-first. ``list_date`` comes from the ``<span class="hui12">`` stamp that
    follows each entry — the LIST page's own date, which is what ``announce_date``
    is stamped from. It is '' when the page prints no date rather than being guessed.

    NOTE the entry test is the URL shape plus a non-empty title, NOT "the title
    carries a 第N号 number": the four MLF tenders are titled '2026年7月中期借贷便利
    招标公告' with no number, and a number-requiring filter drops that whole column.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for m in _ANCHOR_RE.finditer(html_text or ""):
        href = m.group(2)
        if not _LEAF_RE.search(href):
            continue
        title = _plain(m.group(3))
        if not title:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        tail = html_text[m.end():m.end() + 300]
        d = _LIST_DATE_RE.search(tail)
        out.append({"url": url, "title": title,
                    "list_date": f"{d.group(1)}-{d.group(2)}-{d.group(3)}" if d else ""})
    return out


# ------------------------------------------------------------------ detail parsers --
#
# Every parser below is PURE, takes the raw detail HTML, and NEVER raises: an
# unexpected bulletin shape returns [] and the caller counts it in n_failed_parse.
# Rows are partial (the operation facts only) — build_rows() adds the document
# identity (url/title/column/provenance/stamps).

_HEADER_FIELDS = (("期限", "tenor"), ("投标量", "bid"), ("中标量", "awarded"))

# Rate-column PRIORITY. A multi-price (利率招标) result table prints THREE rate
# columns — 最高中标利率 / 最低中标利率 / 加权平均中标利率 — and the leftmost of them
# is the HIGHEST accepted bid, not the operation's rate. Taking the first 利率 header
# would publish the tail of the auction as the policy rate. The weighted average is
# the figure the PBOC and every desk quote, so it wins; a single-price table's plain
# 中标利率/操作利率 is the next best; a bare 利率 header is the last resort.
_RATE_PRIORITY = (("加权平均", 0), ("中标利率", 1), ("操作利率", 1), ("利率", 2))

# Table FOOTER labels. A 合计 row sums the tenors above it; stored as a tenor it would
# become a phantom operation whose amount double-counts the whole table.
_FOOTER_TENOR_RE = re.compile(r"^(合计|总计|小计)$")


def _table_rows(table_html: str) -> list[list[str]]:
    """A <table>'s rows as dense cell text. PURE."""
    rows = []
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", table_html or ""):
        cells = [_dense(td) for td in re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)]
        if cells:
            rows.append(cells)
    return rows


def _cell_num(cells: list[str], mapping: dict, field: str) -> float:
    """``cells[mapping[field]]`` as a number, NaN when that column is absent. PURE."""
    j = mapping.get(field, -1)
    return _num(cells[j]) if 0 <= j < len(cells) else float("nan")


def _rate_column(cells: list[str]) -> int:
    """Index of the rate column to read, or -1. PURE.

    Priority, not position (see _RATE_PRIORITY): 加权平均 beats a plain
    中标利率/操作利率 beats a bare 利率, and only ties fall back to leftmost.
    """
    best_j, best_rank = -1, 99
    for j, c in enumerate(cells):
        if "利率" not in c:
            continue
        rank = next((r for token, r in _RATE_PRIORITY if token in c), 2)
        if rank < best_rank:
            best_j, best_rank = j, rank
    return best_j


def _result_table(zoom: str) -> list[dict]:
    """Parse a 逆回购操作情况 result table → one dict per TENOR row. PURE.

    Column positions are read off the HEADER row (期限 / 操作利率 or 中标利率 /
    投标量 / 中标量) rather than assumed, because the PBOC has published the same
    table with and without the 投标量 column — and, on multi-price tenders, with
    three rate columns at once (see _rate_column). A 合计 footer row is skipped.
    """
    out: list[dict] = []
    for table in re.findall(r"(?is)<table[^>]*>(.*?)</table>", zoom or ""):
        rows = _table_rows(table)
        header_i, mapping = -1, {}
        for i, cells in enumerate(rows):
            if not any("期限" in c for c in cells):
                continue
            for j, c in enumerate(cells):
                for token, field in _HEADER_FIELDS:
                    if token in c and field not in mapping:
                        mapping[field] = j
                        break
            rate_j = _rate_column(cells)
            if rate_j >= 0:
                mapping["rate"] = rate_j
            if "tenor" in mapping:
                header_i = i
                break
        if header_i < 0:
            continue
        for cells in rows[header_i + 1:]:
            if len(cells) <= mapping["tenor"]:
                continue
            label = cells[mapping["tenor"]]
            if not label or "期限" in label:
                continue
            if _FOOTER_TENOR_RE.match(label):
                # The table's own sum row. Storing it would add a phantom operation
                # that double-counts every tenor above it.
                continue
            bid = _cell_num(cells, mapping, "bid")
            awarded = _cell_num(cells, mapping, "awarded")
            rate = _cell_num(cells, mapping, "rate")
            amount = awarded if not math.isnan(awarded) else bid
            out.append({"tenor_label": label, "tenor_days": tenor_days(label),
                        "rate_pct": rate, "amount_bn": amount,
                        "bid_bn": bid, "awarded_bn": awarded})
    return out


def parse_trade(html_text: str, announce_date: str = "") -> list[dict]:
    """公开市场业务交易公告 (daily RESULT) → one row per tenor. PURE, never raises.

    Prefers the result TABLE (期限/操作利率/投标量/中标量); falls back to the narrative
    sentence ('开展了3255亿元7天期逆回购操作') when a bulletin ships without one.
    """
    try:
        zoom = zoom_html(html_text) or html_text or ""
        text = _dense(zoom)
        m = _FULL_DATE_RE.search(text)
        op_date = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else ""
        kind = "reverse_repo" if "逆回购" in text else "other"
        rows = _result_table(zoom)
        if not rows:
            n = re.search(r"开展(?:了)?([\d.]+)亿元(?:([^，。]{1,6})期)?逆回购", text)
            if not n:
                return []
            label = (n.group(2) or "").strip()
            rows = [{"tenor_label": label, "tenor_days": tenor_days(label),
                     "rate_pct": float("nan"), "amount_bn": _num(n.group(1)),
                     "bid_bn": float("nan"), "awarded_bn": float("nan")}]
        for r in rows:
            r["op_date"] = op_date
            r["kind"] = kind
            r["maturity_date"] = ""
        return rows
    except Exception as e:  # noqa: BLE001 — an unexpected shape is a counted null, not a crash
        log.warning("china_omo: trade parse failed (%s)", e)
        return []


def parse_announcement(html_text: str, announce_date: str = "") -> list[dict]:
    """公开市场业务公告 (PRE-announcement) → one row per OPERATION DATE. PURE.

    The bulletins state a schedule, not a single operation:
      '7月29日至7月31日每日开展6000亿元，8月3日开展3000亿元'
    which expands to four rows (7-29/7-30/7-31 @6000 + 8-3 @3000). The year is never
    printed on these month/day clauses, so it comes from the LIST page's announce date
    (or the document's own signature year) — see document_year().

    rate_pct is NaN by construction: these are 量价分离 fixed-rate tenders whose rate
    the bulletin does not state. The NaN is counted in the sentinel's n_nulls, never
    zero-filled.
    """
    try:
        zoom = zoom_html(html_text) or html_text or ""
        text = _dense(zoom)
        year = document_year(text, announce_date)
        if year is None:
            return []
        t = re.search(r"开展(隔夜|\d+天|\d+个月|\d+年期?)期?(?:逆回购|回购|操作)", text)
        label = t.group(1) if t else ""
        rate = float("nan")
        r = re.search(r"(?:操作利率|中标利率|利率为)(?:为)?([\d.]+)%", text)
        if r:
            rate = _num(r.group(1))
        out: list[dict] = []
        clause = re.compile(
            r"(\d{1,2})月(\d{1,2})日(?:至(\d{1,2})月(\d{1,2})日)?(?:每日)?开展([\d.]+)亿元")
        for c in clause.finditer(text):
            m1, d1 = int(c.group(1)), int(c.group(2))
            amount = _num(c.group(5))
            start = _dated(m1, d1, year, announce_date)
            if not start:
                continue
            if c.group(3):
                end = _dated(int(c.group(3)), int(c.group(4)), year, announce_date)
                if not end or end < start:
                    dates = [start]
                else:
                    d0 = date.fromisoformat(start)
                    span = (date.fromisoformat(end) - d0).days
                    dates = [(d0 + timedelta(days=i)).isoformat() for i in range(span + 1)]
            else:
                dates = [start]
            for iso in dates:
                out.append({"op_date": iso, "kind": "reverse_repo_preannounce",
                            "tenor_label": label, "tenor_days": tenor_days(label),
                            "rate_pct": rate, "amount_bn": amount,
                            "bid_bn": float("nan"), "awarded_bn": float("nan"),
                            "maturity_date": ""})
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("china_omo: announcement parse failed (%s)", e)
        return []


def parse_outright(html_text: str, announce_date: str = "") -> list[dict]:
    """公开市场买断式逆回购招标公告 → one tender row. PURE, never raises.

    Three dates appear in the body (operation, maturity, signature). The operation
    date is the FIRST — the bulletin opens with it — the maturity is read from its own
    '到期日为' clause, and the signature date is simply never used.

    rate_pct is NaN: these are 利率招标 (rate-discovered) tenders, so the announcement
    states a size and a tenor but no rate.
    """
    try:
        zoom = zoom_html(html_text) or html_text or ""
        text = _dense(zoom)
        m = _FULL_DATE_RE.search(text)
        op_date = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else ""
        amount = float("nan")
        a = re.search(r"开展([\d.]+)亿元", text)
        if a:
            amount = _num(a.group(1))
        raw_tenor = ""
        t = re.search(r"期限(?:为)?([^，。；]{1,16})", text)
        if t:
            raw_tenor = t.group(1)
        days = tenor_days(raw_tenor)
        label = re.sub(r"[（(][^）)]*[）)]", "", raw_tenor)   # '6个月（184天）' → '6个月'
        maturity = ""
        mm = re.search(r"到期日(?:为)?(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        if mm:
            maturity = _iso(int(mm.group(1)), int(mm.group(2)), int(mm.group(3)))
        if not op_date and math.isnan(amount):
            return []
        return [{"op_date": op_date, "kind": "outright_repo_tender",
                 "tenor_label": label, "tenor_days": days,
                 "rate_pct": float("nan"), "amount_bn": amount,
                 "bid_bn": float("nan"), "awarded_bn": float("nan"),
                 "maturity_date": maturity}]
    except Exception as e:  # noqa: BLE001
        log.warning("china_omo: outright parse failed (%s)", e)
        return []


def parse_mlf(html_text: str, announce_date: str = "") -> list[dict]:
    """中期借贷便利招标公告 → one MLF tender row. PURE, never raises.

    Same shape as the outright tender minus the maturity clause. rate_pct is NaN for
    the same reason (利率招标 — the rate is discovered at the tender, not announced).
    """
    try:
        zoom = zoom_html(html_text) or html_text or ""
        text = _dense(zoom)
        m = _FULL_DATE_RE.search(text)
        op_date = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else ""
        amount = float("nan")
        a = re.search(r"开展([\d.]+)亿元", text)
        if a:
            amount = _num(a.group(1))
        raw_tenor = ""
        t = re.search(r"期限(?:为)?([^，。；]{1,16})", text)
        if t:
            raw_tenor = t.group(1)
        if not op_date and math.isnan(amount):
            return []
        return [{"op_date": op_date, "kind": "mlf_tender",
                 "tenor_label": re.sub(r"[（(][^）)]*[）)]", "", raw_tenor),
                 "tenor_days": tenor_days(raw_tenor),
                 "rate_pct": float("nan"), "amount_bn": amount,
                 "bid_bn": float("nan"), "awarded_bn": float("nan"),
                 "maturity_date": ""}]
    except Exception as e:  # noqa: BLE001
        log.warning("china_omo: mlf parse failed (%s)", e)
        return []


_PARSERS = {"trade": parse_trade, "announcement": parse_announcement,
            "outright": parse_outright, "mlf": parse_mlf}


def parse_detail(column: str, html_text: str, announce_date: str = "") -> list[dict]:
    """Dispatch to the column's parser. PURE; unknown columns yield []."""
    fn = _PARSERS.get(column)
    return fn(html_text, announce_date) if fn else []


def build_rows(entry: dict, column: str, html_text: str, fetched_at: str) -> list[dict]:
    """One bulletin's detail HTML → canonical operations.parquet rows. PURE.

    ``entry`` is an extract_entries() row: its list_date becomes announce_date (the
    document's own publication date — never our clock) and also supplies the YEAR for
    the month/day-only pre-announcement clauses.
    """
    announce = str(entry.get("list_date") or "")
    title = str(entry.get("title") or "")
    url = str(entry.get("url") or "")
    rows = parse_detail(column, html_text, announce)
    out = []
    for r in rows:
        out.append({
            "announce_date": announce,
            "op_date": r.get("op_date", "") or announce,
            "bulletin_no": bulletin_no(title),
            "column": column,
            "kind": r.get("kind", "other"),
            "tenor_label": r.get("tenor_label", "") or "",
            "tenor_days": r.get("tenor_days", float("nan")),
            "rate_pct": r.get("rate_pct", float("nan")),
            "amount_bn": r.get("amount_bn", float("nan")),
            "bid_bn": r.get("bid_bn", float("nan")),
            "awarded_bn": r.get("awarded_bn", float("nan")),
            "maturity_date": r.get("maturity_date", "") or "",
            "title": title,
            "url": url,
            "provenance": PROVENANCE,
            "first_seen": fetched_at,
            "fetched_at": fetched_at,
        })
    return out


def count_nulls(rows: list[dict]) -> int:
    """Coverage nulls across the core fields (op_date/tenor_days/rate_pct/amount_bn).

    A pre-announcement contributes one null per row for its unstated rate — that is
    the intended signal: the sentinel prints the gap instead of the store implying a
    rate of zero. PURE.
    """
    n = 0
    for r in rows:
        for f in _NULLABLE_CORE:
            v = r.get(f)
            if v is None or v == "":
                n += 1
            elif isinstance(v, float) and math.isnan(v):
                n += 1
    return n


# ------------------------------------------------------------------ events ledger --

def _fmt(value) -> str:
    """3255.0 → '3255', 1.4 → '1.4'. PURE (compact zh summaries)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(f):
        return ""
    return str(int(f)) if f == int(f) else f"{f:g}"


_KIND_ZH = {"reverse_repo": "逆回购", "reverse_repo_preannounce": "逆回购(预告)",
            "outright_repo_tender": "买断式逆回购招标", "mlf_tender": "MLF招标",
            "other": "公开市场操作"}


_SUMMARY_CLAUSE_CAP = 4


def _clause(row: dict) -> str:
    """One row → its zh clause, e.g. '7天逆回购 3255亿元 @1.40%'. PURE."""
    label = str(row.get("tenor_label") or "")
    kind = _KIND_ZH.get(str(row.get("kind") or "other"), "公开市场操作")
    chunk = f"{label}{kind}"
    amount = _fmt(row.get("amount_bn"))
    if amount:
        chunk += f" {amount}亿元"
    rate = row.get("rate_pct")
    if isinstance(rate, float) and not math.isnan(rate):
        chunk += f" @{rate:.2f}%"
    return chunk.strip()


def summarise(rows: list[dict]) -> str:
    """Compact zh summary of one bulletin's rows, e.g. '7天逆回购 3255亿元 @1.40%'. PURE.

    IDENTICAL clauses are COLLAPSED with a ×N multiplier and every DISTINCT clause is
    shown. A first-three-rows slice reads a four-day pre-announcement as
    '隔夜逆回购(预告) 6000亿元、隔夜逆回购(预告) 6000亿元、隔夜逆回购(预告) 6000亿元、
    等4笔' — three copies of one fact, and the ONE figure a reader needs (the 3000亿元
    fourth day, a different size) hidden behind '等4笔'. The repetition also rides into
    the events.jsonl title, i.e. into the ledger. Grouping fixes both: the same bulletin
    now reads '隔夜逆回购(预告) 6000亿元×3、隔夜逆回购(预告) 3000亿元'.

    '等N笔' survives only when there are MORE THAN _SUMMARY_CLAUSE_CAP distinct clauses
    to show — N is the total operation count, so the reader can tell the summary is a
    head, not the whole document.
    """
    groups: list[tuple[str, int]] = []
    index: dict[str, int] = {}
    for r in rows:
        text = _clause(r)
        if not text:
            continue
        if text in index:
            groups[index[text]] = (text, groups[index[text]][1] + 1)
        else:
            index[text] = len(groups)
            groups.append((text, 1))
    parts = [f"{text}×{n}" if n > 1 else text
             for text, n in groups[:_SUMMARY_CLAUSE_CAP]]
    if len(groups) > _SUMMARY_CLAUSE_CAP:
        parts.append(f"等{len(rows)}笔")
    return "、".join(parts)


def build_event(rows: list[dict]) -> dict | None:
    """One bulletin's rows → ONE events.jsonl row. PURE.

    kind is ALWAYS ``omo_observed`` and provenance ALWAYS ``pboc_bulletin`` (W3 gate
    10): ``omo_mlf`` belongs to engine/china_policy_transmission's SYNTHETIC FR007-z
    events and an observed bulletin must never be mistaken for one. The hash is the
    engine's own _event_hash so the ledger's dedup key stays single-sourced.

    ROW CONFORMANCE: the ledger's documented row shape carries ``sectors`` and
    ``phrase_diff_ref`` (every seeded row in events.jsonl has them), so both are
    emitted here — empty list / None, because a bulletin states neither. Emitting a
    short row instead would make every consumer that reads those keys branch on
    whether the row came from this collector. ``provenance`` is ours on top of the
    contract and stays: it is what tells an OBSERVED row from a derived one.
    """
    if not rows:
        return None
    from engine.china_policy_transmission import _event_hash

    first = rows[0]
    if str(first.get("kind") or "other") == "other":
        return None
    ts = str(first.get("op_date") or first.get("announce_date") or "")
    if not ts:
        return None
    title = str(first.get("title") or "")
    summary = summarise(rows)
    full_title = f"{title} — {summary}" if summary else title
    return {
        "ts": ts,
        "source": "pboc",
        "kind": EVENT_KIND,
        "title": full_title,
        "url": str(first.get("url") or ""),
        "sectors": [],              # a PBOC operation names no sector
        "phrase_diff_ref": None,    # and carries no communiqué phrase-diff anchor
        "provenance": PROVENANCE,
        "_hash": _event_hash(ts, "pboc", EVENT_KIND, full_title),
    }


def append_events(events: list[dict]) -> int:
    """Append events to data/china_policy_transmission/events.jsonl. Never raises.

    Delegates to scripts.build_china_policy_transmission.append_events, which owns the
    read-hashes → append-new-only mechanics (the ledger is never truncated, and a
    re-run of the same night appends nothing). Imported lazily: the module reads
    lib.config.ROOT at call time, which keeps this collector's import cost off the
    collect registry and keeps the path monkeypatchable in tests.
    """
    if not events:
        return 0
    try:
        from scripts.build_china_policy_transmission import append_events as _append
        return int(_append(events))
    except Exception as e:  # noqa: BLE001 — the event ledger never sinks the store write
        log.warning("china_omo: events.jsonl append failed (%s) — store write stands", e)
        return 0


# ------------------------------------------------------------------ HTTP --

def _headers() -> dict:
    return {"User-Agent": _BROWSER_UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"}


def _pace() -> None:
    """Politeness sleep before EVERY request: ≥1.1 s to the single upstream host."""
    time.sleep(_PACE_S + random.uniform(0.0, _JITTER_S))  # noqa: S311


def _clock() -> float:
    """Monotonic seconds. Indirected so the wall-clock guard is unit-testable."""
    return time.monotonic()


def _get(session, url: str) -> str:
    """Paced GET → decoded HTML. Raises on transport/HTTP failure."""
    _pace()
    r = session.get(url, headers=_headers(), timeout=_TIMEOUT)
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from www.pbc.gov.cn")
    r.raise_for_status()
    return _decode(r.content, r.headers.get("Content-Type", ""))


# ------------------------------------------------------------------ nightly refresh --

def refresh() -> dict:
    """Poll the four bulletin columns, fetch NEW detail pages, append, emit events.

    Flow: PROBE THE STORE → fetch each column index (paced) → extract entries → diff
    against the URLs already stored → fetch at most _DETAIL_CAP new details, newest
    first → parse → append to operations.parquet → append one events.jsonl row per new
    bulletin.

    The store probe comes FIRST and halts the whole night when operations.parquet is
    present-but-unreadable. write_operations() already refuses to append in that state,
    but discovering it at the END of the night meant: 24 upstream fetches spent on data
    that cannot be stored, a diff computed against an EMPTY known-set (so every URL
    looks new, every night), and — worst — events.jsonl appended for bulletins the
    store never received, permanently diverging the ledger from the tape. n_store_abort
    is the sentinel column that makes the abort visible; a healthy night carries 0.

    Everything left unfetched (cap or wall-clock guard) stays UNSTORED and is counted
    in n_deferred, so tomorrow picks it up from the same diff. Raises RuntimeError only
    when every column index failed at transport level.

    A bulletin that FETCHES but does not PARSE is likewise not stored, so it stays in
    the diff and is re-attempted on later nights. That is deliberate: the day the
    parser learns its shape, the backlog heals retroactively instead of having been
    silently written off. Newest-first ordering keeps such a tail from starving fresh
    bulletins of cap slots.

    SENTINEL UNITS (data/china_omo/refresh.parquet) — stated because a sentinel whose
    units are folklore cannot be read:
      n_new         net-new STORE ROWS (one bulletin can be several operation rows).
      n_fetched     detail PAGES that answered at transport level.
      n_failed      FAILURES, transport AND parse: a dead column page, a dead detail
                    page, or a fetched document that parsed to no rows. The log line
                    prints the two apart (failed=… parse_failed=…).
      n_nulls       FIELD-LEVEL coverage nulls only — count_nulls() over the stored
                    rows' (op_date, tenor_days, rate_pct, amount_bn). A pre-announced
                    tender's unstated rate is the common case. Documents that failed
                    to parse are NOT in here (they are failures, not fields), which is
                    the unit purity the review asked for.
      n_deferred    new bulletins the cap/guard left for tomorrow.
      n_store_abort 1.0 when the night halted on an unreadable store, else 0.0.
      columns_polled column index pages that answered — NOT a receipt of completeness.
    """
    import requests  # lazy — keeps import-time cost off the collect registry

    t0 = _clock()
    fetched_at = datetime.now(timezone.utc).isoformat()

    if _read_store(_ops_path(), _OPS_COLUMNS) is None:
        log.error("china_omo: ABORTING THE NIGHT — %s is present but UNREADABLE. "
                  "Nothing is fetched, nothing is appended and the events ledger is "
                  "left alone: with the store unreadable the URL diff would treat "
                  "every bulletin as new and the ledger would gain rows the tape "
                  "never got. Recover the file by hand, then re-run.", _ops_path())
        return {"n_new": 0, "n_fetched": 0, "n_failed": 0, "n_nulls": 0,
                "n_deferred": 0, "n_store_abort": 1, "columns_polled": 0}

    session = requests.Session()

    known = stored_urls()
    entries: list[tuple[str, dict]] = []
    n_failed = 0
    cols_ok = 0
    for col in COLUMNS:
        try:
            html_text = _get(session, col["url"])
            found = extract_entries(html_text, col["url"])
            cols_ok += 1
            entries.extend((col["column"], e) for e in found)
            log.info("china_omo: %s column → %d entries", col["column"], len(found))
        except Exception as e:  # noqa: BLE001 — per-column isolation
            n_failed += 1
            log.warning("china_omo: column %s failed: %s", col["column"], e)

    if cols_ok == 0:
        raise RuntimeError(
            f"china_omo: every one of the {len(COLUMNS)} column pages failed at "
            f"transport level")

    # Dedup across columns, first listing wins (COLUMNS order = trade, announcement,
    # outright, mlf). The four archives are disjoint today, but a cross-listed bulletin
    # would otherwise burn two of the twenty cap slots AND let the keep-LAST store dedup
    # decide its `column` provenance by fetch order — an arbitrary value in a field
    # whose whole job is to say which archive the document came from.
    pending: list[tuple[str, dict]] = []
    claimed: set[str] = set()
    for column, entry in entries:
        url = entry["url"]
        if url in known or url in claimed:
            continue
        claimed.add(url)
        pending.append((column, entry))
    # Newest first so a backlog drains from the top: the freshest bulletin is the one
    # a reader needs tonight, and the tail is what n_deferred promises for tomorrow.
    pending.sort(key=lambda ce: ce[1].get("list_date") or "", reverse=True)

    rows: list[dict] = []
    events: list[dict] = []
    n_fetched = 0
    n_failed_parse = 0
    processed = 0
    truncated = False
    for column, entry in pending:
        if processed >= _DETAIL_CAP:
            break
        if _clock() - t0 > _BUDGET_S:
            truncated = True
            log.warning(
                "china_omo: %.0fs wall-clock guard hit after %d/%d new bulletins — "
                "the remainder stays UNSTORED and is picked up next night",
                _BUDGET_S, processed, len(pending))
            break
        processed += 1
        try:
            detail = _get(session, entry["url"])
        except Exception as e:  # noqa: BLE001 — per-document isolation
            n_failed += 1
            log.warning("china_omo: detail %s failed: %s", entry["url"], e)
            continue
        n_fetched += 1
        doc_rows = build_rows(entry, column, detail, fetched_at)
        if not doc_rows:
            n_failed_parse += 1
            log.warning("china_omo: %s parsed to NO rows (unexpected bulletin shape) — "
                        "counted, not stored", entry["url"])
            continue
        rows.extend(doc_rows)
        ev = build_event(doc_rows)
        if ev:
            events.append(ev)

    n_deferred = max(0, len(pending) - processed)
    if n_deferred:
        log.warning("china_omo: %d new bulletin(s) NOT fetched tonight (cap=%d%s) — "
                    "they stay unstored and drain on the next run",
                    n_deferred, _DETAIL_CAP, ", wall-clock guard" if truncated else "")

    n_new = write_operations(rows)
    n_events = append_events(events)
    # UNIT PURITY (review F16): n_nulls counts FIELDS the bulletins did not state.
    # A document that failed to PARSE has no fields at all — it is a failure, and it
    # is counted with the transport failures in n_failed. Folding it into n_nulls made
    # "a night of unstated rates" and "a night the parser broke" the same number.
    n_nulls = count_nulls(rows)
    n_failed_total = n_failed + n_failed_parse
    log.info("china_omo: columns_ok=%d/%d pending=%d fetched=%d rows=%d net_new=%d "
             "events=%d failed=%d (transport=%d parse=%d) nulls=%d deferred=%d",
             cols_ok, len(COLUMNS), len(pending), n_fetched, len(rows), n_new,
             n_events, n_failed_total, n_failed, n_failed_parse, n_nulls, n_deferred)
    return {"n_new": n_new, "n_fetched": n_fetched, "n_failed": n_failed_total,
            "n_nulls": n_nulls, "n_deferred": n_deferred, "n_store_abort": 0,
            "columns_polled": cols_ok}


# ------------------------------------------------------------------ adapter --

class ChinaOmoAdapter(Adapter):
    """PBOC OMO bulletin tape (W3 CNH) — context/display tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_omo`` starts with ``china`` so it is auto-assigned to the asia lane
    (scripts/collect.py group_members).

    fetch() returns a COVERAGE sentinel rather than a bare count, so
    data/china_omo/refresh.parquet is a readable run ledger. Every column's exact unit
    is documented on refresh(); read it there rather than inferring from the name.
    n_store_abort is the one to alarm on: it is 1.0 on a night that halted before
    fetching anything because the accrued store could not be read. What the sentinel
    does NOT prove is that every published bulletin was seen — columns_polled is the
    number of index pages that ANSWERED, not a receipt that their contents are complete.
    """

    name = "china_omo"
    group = GROUP
    stale_after_days = 5   # the 交易公告 prints on operating days only; a long holiday is normal

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        # tz-NAIVE normalized UTC day (collectors/china_filings.py precedent): mixing a
        # tz-aware index into a tz-naive parquet makes store.upsert's combine_first raise.
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        sentinel = pd.DataFrame(
            {k: [float(s[k])] for k in _SENTINEL_COLUMNS},
            index=[idx],
        )
        sentinel.index.name = "collected_at"
        return {"refresh": sentinel}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    s = refresh()
    print(f"china_omo: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
