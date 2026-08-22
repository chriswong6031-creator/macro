"""CNInfo A-share filing / announcement metadata collector (W3.2).

Metadata-only (RUL-4): title, category, ticker, URL, publish-time.
No PDF bodies are ever fetched. Store: data/china_filings/filings.parquet,
keep-FIRST on announcementId. Full stream ~700K rows/yr; this PR collects
forward-only (last 7 days, idempotent re-pull).

VERIFIED ENDPOINT (both SSE + SZSE, including inquiry letters):
    POST http://www.cninfo.com.cn/new/hisAnnouncement/query
    Content-Type: application/x-www-form-urlencoded
    column=sse|szse, tabName=fulltext, seDate=YYYY-MM-DD~YYYY-MM-DD
Response: totalAnnouncement, totalpages, hasMore, announcements[]

Category normalizer: title-keyword → category. Priority order is encoded in
CATEGORY_PRIORITY so investigation > inquiry_letter > other. First-match-wins.

Pacing: 1.5 s + jitter between page requests.

P1-R2 announcement-id integrity (2026-08-22, DSC:CHINA-VISITS-UNTYPED-
ANNOUNCEMENT-ID-DROP): announcementId is this plane's natural key, and a
falsy/NaN/whitespace key used to be dropped SILENTLY — drop_duplicates()
treats every row sharing "" as a duplicate of every other such row, so N
malformed rows collapsed into ONE with no counter, no log, no health note.
key_anomaly()/normalize_announcement_id()/partition_by_key_integrity() below
are the single typed predicate for "is this key malformed, and how";
write_filings() now excludes malformed rows as a TYPED, COUNTED exclusion
(module global LAST_KEY_INTEGRITY, folded into LAST_RUN_OUTCOME) instead of
letting them silently collapse or appending them keyless. collectors/
china_visits.py imports key_anomaly() from here rather than growing its own
opinion, so china_filings' write boundary and china_visits' candidate filter
can never silently diverge on what counts as malformed.
"""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# P1-R1 same-cycle derivation contract: process-local outcome of the MOST RECENT
# fetch() call in THIS process. Read by collectors/china_visits.py when both run in
# one collect invocation (same cninfo host-group thread, china_filings then
# china_visits — see scripts/collect.py _CONCURRENT_HOSTS). None means china_filings
# has not run in this process (e.g. `--only china_visits`) and the derived plane
# then reads the committed store — the legitimate proof/debug path. Set FAIL-CLOSED
# at fetch() entry so an escape (an exception that somehow skips every later
# assignment) reads as a failed refresh, never as "not run". Process-local by
# design, never persisted to disk — a sidecar file would make a later
# `--only china_visits` run inherit a stale verdict from a prior process. Exchange
# budget truncation (_EXCHANGE_BUDGET_S) is deliberately NOT a degradation signal
# here: it is self-healing by design (keep-FIRST dedup + the 3-day re-pull), so a
# truncated-but-successful exchange still counts as ok.
LAST_RUN_OUTCOME: dict | None = None

# P1-R2 announcement-id integrity contract: process-local outcome of the
# key-integrity partition performed by the MOST RECENT write_filings() call in
# THIS process. Never persisted to disk — same rationale as LAST_RUN_OUTCOME
# above (a sidecar would let a later `--only china_visits` run inherit a
# stale verdict from a prior process). Reset fail-closed to None at
# ChinaFilingsAdapter.fetch() entry, same as LAST_RUN_OUTCOME, so a fetch()
# that raises before ever calling write_filings() reads as "unknown", never
# as a false "clean". write_filings() itself sets this on EVERY call (zeros
# when clean) — see its docstring. Canonical shape, every field always
# present when set:
#   {"excluded_total": int, "excluded_by_type": {anomaly: count},
#    "preexisting_unkeyed": int, "at": iso}
LAST_KEY_INTEGRITY: dict | None = None


def _zero_key_integrity(at: str = "") -> dict:
    """Fresh canonical-shape LAST_KEY_INTEGRITY dict, all zeros/empty.

    A function (not a shared module-level constant) so every caller gets its
    own `excluded_by_type` dict / `excluded_rows` list — a shared mutable
    default would let one caller's count (or list mutation) leak into
    another's "zero" reading.

    P1-R3 (durable scoped key-exclusion recovery): `excluded_rows` carries
    THIS call's malformed row dicts verbatim (uncapped — bounded only by
    batch size), so collectors/china_visits.py can harvest them into a
    durable coverage-exception ledger instead of relying on this process-
    local global surviving into the same run china_visits happens to read
    it in. See write_filings()'s docstring for how it is populated.
    """
    return {
        "excluded_total": 0,
        "excluded_by_type": {},
        "preexisting_unkeyed": 0,
        "excluded_rows": [],
        "at": at,
    }


# ------------------------------------------------------------------ constants --

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_REFERER = (
    "http://www.cninfo.com.cn/new/commonUrl/pageByCode"
    "?code=cninfo-tips-announcement"
)
_ENDPOINT = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
_PAGE_SIZE = 30              # server-side clamp: pageSize>30 still returns 30 (verified 2026-07-11)
_NIGHTLY_LOOKBACK_DAYS = 3   # idempotent re-pull: previous 3 calendar days
_INITIAL_LOOKBACK_DAYS = 7   # first-run bootstrap: last 7 days
_PACE_S = 1.5
_JITTER_S = 0.4              # ± uniform jitter on top of _PACE_S
# (connect, read) timeout. CNInfo's gateway failure mode is a SLOW 504: on
# 2026-07-10 (run 29089281652) one szse request trickled for ~4.4 min before the
# 504 landed, burning ~5 min of the asia lane on a day the endpoint was dead.
# A 15s read timeout kills a trickling gateway error fast; healthy pages return
# a ~100KB JSON body in ~1-2s and are unaffected.
_TIMEOUT = (10, 15)
# Wall-clock budget per exchange. Healthy volume today is ~90-170 pages ≈ 3-7 min
# at pace; the budget only truncates pathological days. Partial pages are KEPT
# (keep-FIRST dedup + the 3-day lookback re-pull make truncation self-healing).
_EXCHANGE_BUDGET_S = 480

_EXCHANGES = ("sse", "szse")

# ------------------------------------------------------------------ parquet store --

_COLUMNS = (
    "announcementId",
    "sec_code",
    "sec_name",
    "org_id",
    "title",
    "publish_ts",       # ISO8601, Asia/Shanghai timezone
    "exchange",
    "category",
    "kind",             # nullable; non-null only for inquiry_letter family
    "announcement_type_raw",
    "adjunct_url",
    "adjunct_type",
    "_collected_at",
)


def _store_path() -> Path:
    p = config.data_dir() / "china_filings"
    p.mkdir(parents=True, exist_ok=True)
    return p / "filings.parquet"


def load_filings() -> pd.DataFrame:
    """Read existing parquet, or return an empty frame with the canonical schema.

    A present-but-unreadable store also reads EMPTY here, because a reader must
    not crash. Callers that go on to REWRITE the store must not use this — see
    _read_filings_strict() and write_filings().
    """
    path = _store_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_filings: could not read existing parquet: %s", e)
    return pd.DataFrame(columns=list(_COLUMNS))


def _read_filings_strict() -> pd.DataFrame | None:
    """Like load_filings() but returns None (not empty) for a present-but-
    UNREADABLE store, so write_filings() can ABORT instead of overwriting it.

    Why this exists (P1-R2, adversarial review 2026-08-22): write_filings()
    rewrites the entire accrued tape every night, and it used to source that
    rewrite from load_filings(), which swallows a read error and answers
    EMPTY. A corrupt store therefore read as "no existing rows" and the next
    write REPLACED the whole tape with tonight's batch — measured, a 500-row
    store became 1 row, with net_new reported as 1 and every key-integrity
    instrument reading clean. That is the same class of lie this repair
    exists to close (missing data silently becoming clean authority), just
    with a far larger blast radius than a malformed key. collectors/
    china_visits.py has carried exactly this strict-read + ABORT pattern
    since P1 (_read_store_strict / write_visits); china_filings simply never
    grew one.
    """
    path = _store_path()
    if not path.exists():
        return pd.DataFrame(columns=list(_COLUMNS))
    try:
        return pd.read_parquet(path).reindex(columns=list(_COLUMNS))
    except Exception as e:  # noqa: BLE001
        log.error("china_filings: filings.parquet is present but UNREADABLE (%s)", e)
        return None


# ------------------------------------------------------------------ key integrity (P1-R2) --
#
# announcementId is the natural key of this whole plane — china_visits derives
# its own natural key from it 1:1. drop_duplicates(subset=["announcementId"])
# below treats every row sharing a falsy key ("", None-as-NaN once frame-ified,
# etc.) as a DUPLICATE of every other such row, so N malformed rows silently
# COLLAPSE INTO ONE with no counter, no log, no health note — a real filing
# quietly becomes indistinguishable from "no filing". Recorded as
# DSC:CHINA-VISITS-UNTYPED-ANNOUNCEMENT-ID-DROP. These three functions are the
# single typed predicate for "is this key malformed, and how" — china_visits.py
# imports key_anomaly() from here rather than growing a second opinion, so the
# two boundaries (this module's store write, and china_visits' candidate
# filter) can never silently diverge on what counts as malformed.

_KEY_ANOMALIES = ("missing", "nan", "empty", "whitespace")


def key_anomaly(value) -> str | None:
    """Classify one raw announcementId value's malformation, or None if it is
    well-formed. Pure, and — deliberately — NEVER raises, for any input.

    Returns exactly one of the frozen typed anomaly names:
      "missing"    — value is None (including a dict key that was absent:
                     row.get("announcementId") already yields None for that).
      "nan"        — value is a NaN-like scalar: float('nan'), pd.NA, pd.NaT,
                     np.nan (anything pandas' own pd.isna() calls missing).
      "empty"      — value is a string equal to "".
      "whitespace" — value is a non-empty string that STRIPS to "" — covers
                     plain space, tab, newline, and the ideographic space
                     "　" (U+3000), which .strip() also removes.
    None (well-formed) otherwise — including a non-string scalar that
    coerces to a non-empty string (e.g. an int id): only a string carries
    the empty/whitespace anomalies, and a non-string is never NaN-like once
    the pd.isna() check above has already passed.

    Ordering is load-bearing: the NaN check runs BEFORE any str() coercion,
    because str(float('nan')) == 'nan' — a non-empty string that would
    misread as well-formed if the string branch ran first.

    pd.isna() is guarded rather than trusted: it returns an ARRAY (not a
    scalar bool) for list/array-like input instead of raising, and truth-
    testing that array raises ValueError ("ambiguous"); some object types
    raise TypeError directly. Catch both — a non-scalar value is never
    NaN-like, and this helper must never raise for weird input (a list, a
    dict, a tuple all pass through unharmed).
    """
    if value is None:
        return "missing"
    try:
        if pd.isna(value):
            return "nan"
    except (TypeError, ValueError):
        pass  # non-scalar (list/array/...) input — never NaN-like
    if isinstance(value, str):
        if value == "":
            return "empty"
        if value.strip() == "":
            return "whitespace"
        return None
    return None


def normalize_announcement_id(value) -> str:
    """"" for every malformed form key_anomaly() names; otherwise
    str(value).strip(). Pure, and — like key_anomaly() — NEVER raises.

    The str() coercion is guarded rather than trusted: key_anomaly() answers
    None (well-formed) for any non-string object it cannot call NaN-like,
    including one whose own __str__ raises, so an unguarded str() here would
    be the one path in this pair that can throw. Measured 2026-08-22 by
    probing both helpers over a hostile input table: key_anomaly() survived
    every case, this function raised RuntimeError on an object with a raising
    __str__. No production caller exists today (this helper is the canonical
    normalizer for future callers), but it sits one import away from the C0
    market-critical Asia lane, where a raise is a lane failure — so an
    un-stringable value is treated as exactly what it is, a key we cannot
    read, and normalizes to "".
    """
    if key_anomaly(value) is not None:
        return ""
    try:
        return str(value).strip()
    except Exception:  # noqa: BLE001 — an un-stringable key is an absent key
        return ""


def partition_by_key_integrity(
    rows,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Split row dicts on key_anomaly(row.get("announcementId")). Pure.

    Returns (well_keyed, malformed, counts) — counts maps anomaly name ->
    occurrence count for the anomalies that actually occurred (an anomaly
    name that never fired is omitted, not zero-valued). Each malformed row
    is counted INDIVIDUALLY: three rows sharing "" are three, never one —
    this is the property drop_duplicates lacks and the whole repair exists
    to restore. Input order is preserved within each output list.
    """
    well_keyed: list[dict] = []
    malformed: list[dict] = []
    counts: dict[str, int] = {}
    for row in rows:
        anomaly = key_anomaly(row.get("announcementId"))
        if anomaly is None:
            well_keyed.append(row)
        else:
            malformed.append(row)
            counts[anomaly] = counts.get(anomaly, 0) + 1
    return well_keyed, malformed, counts


def write_filings(new_rows: list[dict]) -> int:
    """Append rows to filings.parquet, keep-FIRST on announcementId.

    Returns the count of net-new rows written (0 when all duplicates).
    Never raises — failures are logged and silently skipped.

    P1-R2: `new_rows` is partitioned by key integrity BEFORE any dedup — only
    well-keyed rows ever enter the keep-FIRST dedup pool. A malformed row is a
    TYPED, COUNTED exclusion, never a silent drop_duplicates collapse and
    never appended keyless (that would grow the store unbounded across the
    3-day re-pull, and minting a fallback key is a forbidden new identity
    system). The ACCRUED store gets the same protection: any row already on
    disk with a malformed key is split off as `preexisting_unkeyed` and
    written back VERBATIM, untouched by the keyed dedup, so a historical
    malformed row can never be silently collapsed into a keyed row's slot
    either. net_new is computed off the KEYED frames only, so a malformed
    row can never inflate or deflate that count.

    Sets module-global LAST_KEY_INTEGRITY on every call (zeros when clean —
    see _zero_key_integrity()). LOUD (log.error + a bare line-start GitHub
    annotation — never through the logger, see
    tests/test_gh_annotation_line_start.py) whenever anything was excluded
    or a pre-existing unkeyed row was carried forward.
    """
    global LAST_KEY_INTEGRITY
    if not new_rows:
        LAST_KEY_INTEGRITY = _zero_key_integrity(datetime.now(timezone.utc).isoformat())
        return 0
    try:
        path = _store_path()
        well_keyed, malformed, new_counts = partition_by_key_integrity(new_rows)
        new_df = pd.DataFrame(well_keyed).reindex(columns=list(_COLUMNS))
        if not new_df.empty:
            # Canonicalize the key of every row that IS well-keyed. Without
            # this, " 1223456789 " and "1223456789" are two distinct keys, so
            # the same filing published once with incidental padding stores
            # TWICE and shows twice in the dossier's recent-visit list — a
            # duplicate-identity bug the malformed-key partition does not
            # catch, because padding that strips to a real value is not
            # malformed. It also coerces any non-string key to its string
            # form, which keeps drop_duplicates() hashable: an unhashable
            # value (a list, a Series) would otherwise raise inside the
            # try/except below and lose the WHOLE batch silently. Measured
            # 2026-08-22: 0 of the 54,078 accrued keys are padded, so this is
            # a no-op on today's tape and pure protection going forward.
            new_df["announcementId"] = new_df["announcementId"].map(
                normalize_announcement_id
            )

        existing = _read_filings_strict()
        if existing is None:
            log.error("china_filings: ABORTING the filings.parquet write — the accrued "
                      "store is unreadable and is left untouched for manual recovery")
            print(
                "::warning title=china-filings-store-unreadable::"
                "filings.parquet is present but unreadable — the nightly write was "
                "ABORTED and the accrued store left untouched for manual recovery",
                flush=True,
            )
            return 0
        # Split the ACCRUED store with a vectorized mask over the SAME
        # predicate, not partition_by_key_integrity(existing.to_dict("records")).
        # The two are semantically identical, but the dict spelling materializes
        # one dict per stored row and rebuilds a frame from them; masking walks
        # the key column once and slices the ORIGINAL frame, so the store keeps
        # its own dtypes and column order untouched. Measured 2026-08-22 on the
        # real 54,078-row store: 0.55s vs 0.01s (~45x), and that cost grows with
        # the store (~2,860 net-new rows/night) on the 4-core-bound runner where
        # the render budget is law. partition_by_key_integrity() still owns the
        # NEW batch, which arrives as dicts and is ~13k rows, not the whole tape.
        unkeyed_mask = existing["announcementId"].map(key_anomaly).notna()
        existing_keyed_df = existing[~unkeyed_mask]
        existing_unkeyed_df = existing[unkeyed_mask]
        preexisting_unkeyed = int(unkeyed_mask.sum())

        if existing_keyed_df.empty:
            # No existing keyed rows: dedup within the new well-keyed batch itself.
            merged_keyed = new_df.drop_duplicates(subset=["announcementId"], keep="first")
            net_new = len(merged_keyed)
        else:
            pre_count = existing_keyed_df["announcementId"].nunique()
            merged_keyed = pd.concat([existing_keyed_df, new_df], ignore_index=True)
            merged_keyed = merged_keyed.drop_duplicates(subset=["announcementId"], keep="first")
            post_count = merged_keyed["announcementId"].nunique()
            net_new = post_count - pre_count

        # Pre-existing unkeyed rows ride along VERBATIM — never subjected to
        # the keyed dedup, never dropped.
        final = pd.concat([existing_unkeyed_df, merged_keyed], ignore_index=True)
        final = final.sort_values(
            ["publish_ts", "announcementId"], na_position="last"
        ).reset_index(drop=True)
        final.to_parquet(path, index=False)

        excluded_total = len(malformed)
        LAST_KEY_INTEGRITY = {
            "excluded_total": excluded_total,
            "excluded_by_type": dict(new_counts),
            "preexisting_unkeyed": preexisting_unkeyed,
            # P1-R3: the malformed row dicts VERBATIM from THIS call's
            # new_rows batch (never the accrued preexisting_unkeyed rows —
            # those are harvested by china_visits' own whole-tape candidate
            # scan instead, origin="visits_candidate"). china_visits.refresh()
            # harvests these as origin="filings_boundary" coverage
            # exceptions. Uncapped — bounded by batch size, not a fixed cap
            # like excluded_identities elsewhere.
            "excluded_rows": list(malformed),
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if excluded_total or preexisting_unkeyed:
            log.error(
                "china_filings: %d malformed announcementId row(s) excluded this "
                "call (%s); %d pre-existing unkeyed row(s) preserved verbatim in "
                "the store (never collapsed by the keyed dedup)",
                excluded_total, new_counts, preexisting_unkeyed,
            )
            # Bare print, NOT log.* — this repo's loggers prefix the line
            # (e.g. "ERROR ..."), which makes GitHub silently drop the
            # annotation because it only parses "::" at column 0
            # (tests/test_gh_annotation_line_start.py).
            print(
                f"::warning title=china-filings-malformed-announcement-id::"
                f"{excluded_total} malformed announcementId row(s) excluded "
                f"this call ({new_counts}); {preexisting_unkeyed} pre-existing "
                f"unkeyed row(s) preserved verbatim in the store",
                flush=True,
            )
        return net_new
    except Exception as e:  # noqa: BLE001
        log.error("china_filings.write_filings failed: %s", e)
        return 0


# ------------------------------------------------------------------ category normalizer --

# Priority-ordered list: (category_key, [zh_keywords]).
# First match wins. Higher entries outrank lower ones.
# Rationale for order: investigation > inquiry_letter rank above generic
# operational categories (buyback, pledge) so that a filing that is both an
# inquiry letter AND mentions 回购 is classified as inquiry_letter, not buyback.
CATEGORY_PRIORITY: list[tuple[str, list[str]]] = [
    ("investigation",       ["立案"]),
    ("inquiry_letter",      ["问询函", "监管函", "关注函"]),
    ("delisting_risk",      ["退市"]),
    ("earnings_preann",     ["业绩预告", "预增", "预减", "预盈", "预亏", "业绩快报"]),
    ("restructuring",       ["重组", "重大资产"]),
    ("major_contract",      ["重大合同", "中标"]),
    ("buyback",             ["回购"]),
    ("pledge",              ["质押"]),
    ("holder_change_down",  ["减持"]),
    ("holder_change_up",    ["增持"]),
    # institutional-visit / IR-activity family (P1, China Alpha Intelligence
    # RIGHTS-0 §1: rights-clear metadata plane, extraction was the gap).
    # Lowest priority among the named categories (only "other" ranks below
    # it) — 调研 is a broad word and this ordering guarantees the addition
    # never reclassifies any filing that already matched a higher-priority
    # category above (investigation/inquiry_letter/... unchanged).
    ("institutional_visit", ["投资者关系活动记录表", "特定对象调研",
                             "分析师会议", "业绩说明会", "调研"]),
]
_OTHER = "other"

# Inquiry-family kind sub-classification keywords.
# Precedence (first-match-wins within the inquiry family):
#   attachment (专项说明/核查意见) > reply (回函/回复/答复) > letter (exchange-issued, default)
# kind is None for all non-inquiry_letter categories.
_KIND_ATTACHMENT_KW = ("专项说明", "核查意见", "专项核查意见")
# 复函 (formal reply letter) added: confirmed in 4 live inquiry.parquet rows
# e.g. "股票交易异常波动问询函的复函-郁敏珺". 答复 kept (deliberate superset ruling).
_KIND_REPLY_KW = ("回函", "回复", "答复", "复函")
# Reply-side forms that the two lists above miss. `letter` used to be the
# fall-through for the whole family, so ANY reply-side document whose title did
# not happen to contain one of the words above was stored as an exchange-issued
# inquiry. Measured 2026-08-19 on data/china_filings/filings.parquet: 100 of the
# 140 rows stored kind="letter" were 会计师事务所…说明, 独立董事…意见,
# 律师…法律意见书 or 评估机构…发表意见 — reply-side filings published as
# unanswered regulatory questions (PR #5975).
#
# 意见 is matched broadly rather than enumerated: the reply side keeps inventing
# organ and adviser forms (独立董事意见, 董事会审计委员会…相关意见, 专项法律意见,
# 评估机构…发表意见), and an enumeration silently re-admits each new one.
_KIND_REPLY_SIDE_KW = ("意见", "说明")
# 延期回复 says the reply is POSTPONED. It contains 回复 and every one of the 41
# such notices in the store was classified `reply`, which is the inverse of the
# truth: the filing announcing that no reply has been made would mark the inquiry
# answered. It is reply-SIDE (not an exchange letter) but it is not a reply.
_KIND_DEFERRAL_RE = re.compile(r"(?:延期|延长|推迟|顺延)回复")


def classify_kind(title: str) -> str | None:
    """Return the inquiry-letter sub-kind for a title, or None if not applicable.

    Only called when the enclosing category is 'inquiry_letter'. Within that
    family precedence is:
      deferral > attachment > reply > reply_side > letter

      'letter'     — an exchange-issued inquiry, or the company's receipt of one
      'reply'      — the company's reply (回函/回复/答复/复函)
      'attachment' — third-party verification note (专项说明/核查意见)
      'reply_side' — any other filing made in ANSWER to an inquiry: an adviser's
                     说明, an organ's 意见, a 法律意见书. Not an inquiry, and not
                     itself the reply.
      'deferral'   — a notice that the reply is postponed; answers nothing.

    `letter` is deliberately no longer the catch-all: a title that names none of
    these forms is an inquiry, and everything else must say what it is.

    Pure function; unit-testable without any I/O.
    """
    if _KIND_DEFERRAL_RE.search(title):
        return "deferral"
    if any(kw in title for kw in _KIND_ATTACHMENT_KW):
        return "attachment"
    if any(kw in title for kw in _KIND_REPLY_KW):
        return "reply"
    if any(kw in title for kw in _KIND_REPLY_SIDE_KW):
        return "reply_side"
    return "letter"


def categorize(title: str) -> str:
    """Map an announcement title to a category key (first-match-wins).

    Priority order: investigation > inquiry_letter > delisting_risk >
    earnings_preann > restructuring > major_contract > buyback > pledge >
    holder_change_down > holder_change_up > institutional_visit > other.

    Pure function; unit-testable without any I/O.
    """
    for category, keywords in CATEGORY_PRIORITY:
        if any(kw in title for kw in keywords):
            return category
    return _OTHER


# ------------------------------------------------------------------ HTTP --

def _headers() -> dict:
    return {
        "User-Agent": _BROWSER_UA,
        "Referer": _REFERER,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _pace() -> None:
    """Sleep _PACE_S + uniform jitter (politeness)."""
    time.sleep(_PACE_S + random.uniform(-_JITTER_S, _JITTER_S))  # noqa: S311


def _unix_ms_to_iso(ts_ms: int | float | None) -> str:
    """Convert Unix-millisecond timestamp to ISO8601 Asia/Shanghai string.

    Returns '' on any failure (malformed row should not crash the collector).
    Pure except for timezone import.
    """
    if ts_ms is None:
        return ""
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415 — lazy
        tz = ZoneInfo("Asia/Shanghai")
        dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=tz)
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _fetch_page(
    exchange: str,
    date_range: str,
    page_num: int,
    session,
) -> dict:
    """POST one page to the CNInfo endpoint. Returns the parsed JSON dict.

    Raises on HTTP error or JSON parse failure so the per-exchange try/except
    in the caller can isolate the exchange.
    """
    data = (
        f"pageNum={page_num}&pageSize={_PAGE_SIZE}"
        f"&column={exchange}&tabName=fulltext"
        f"&plate=&stock=&searchkey=&secid=&category=&trade="
        f"&seDate={date_range}&sortName=&sortType=&isHLtitle=True"
    )
    r = session.post(
        _ENDPOINT,
        data=data,
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from CNInfo exchange={exchange}")
    r.raise_for_status()
    return r.json()


def _parse_announcement(ann: dict, exchange: str, collected_at: str) -> dict:
    """Map one raw announcement dict → canonical row dict. Pure (no I/O).

    announcementId: P1-R2 — a truly ABSENT key must stay None ("missing" per
    key_anomaly()), never get flattened to "" ("empty"). Both are malformed
    and both get typed-excluded at write_filings(), but collapsing "missing"
    into "empty" here would have thrown away the more specific anomaly name
    before it ever reached the partition.
    """
    title = ann.get("announcementTitle") or ""
    ts_ms = ann.get("announcementTime")
    cat = categorize(title)
    kind: str | None = classify_kind(title) if cat == "inquiry_letter" else None
    return {
        "announcementId": ann.get("announcementId"),
        "sec_code": ann.get("secCode", ""),
        "sec_name": ann.get("secName", ""),
        "org_id": ann.get("orgId", ""),
        "title": title,
        "publish_ts": _unix_ms_to_iso(ts_ms),
        "exchange": exchange,
        "category": cat,
        "kind": kind,
        "announcement_type_raw": ann.get("announcementType", ""),
        "adjunct_url": ann.get("adjunctUrl", ""),  # relative path — stored as-is, NEVER fetched
        "adjunct_type": ann.get("adjunctType", ""),
        "_collected_at": collected_at,
    }


# ------------------------------------------------------------------ adapter --

class ChinaFilingsAdapter(Adapter):
    """CNInfo A-share filing / announcement metadata collector.

    Nightly: queries the last _NIGHTLY_LOOKBACK_DAYS calendar days from both
    SSE and SZSE. Each exchange is isolated in its own try/except so a CNInfo
    temporary outage on one exchange never sinks the other. Results are
    deduplicated by announcementId (keep-FIRST) and stored to a single
    filings.parquet.

    The adapter returns a summary DataFrame with a DatetimeIndex (required by
    the base validate() / store.upsert() contract — see china_official_corpora
    fix for precedent).
    """

    name = "china_filings"
    group = "china_filings"  # auto-routed to asia lane by 'china_' prefix
    stale_after_days = 4     # filings are released daily; >4 days = stale

    def _date_range(self, full_history: bool = False) -> str:
        """Return the seDate range string 'YYYY-MM-DD~YYYY-MM-DD'."""
        today = datetime.now(timezone.utc).date()
        lookback = _INITIAL_LOOKBACK_DAYS if full_history else _NIGHTLY_LOOKBACK_DAYS
        start = today - timedelta(days=lookback)
        return f"{start.isoformat()}~{today.isoformat()}"

    def _fetch_exchange(
        self,
        exchange: str,
        date_range: str,
        session,
        collected_at: str,
    ) -> list[dict]:
        """Paginate through all announcement pages for one exchange.

        Each page is paced at 1.5 s + jitter. Returns a list of canonical row dicts.
        Raises on persistent failure so the per-exchange isolation in fetch() fires.
        """
        rows: list[dict] = []
        page_num = 1
        t0 = time.monotonic()
        while True:
            payload = _fetch_page(exchange, date_range, page_num, session)
            anns = payload.get("announcements") or []
            for ann in anns:
                rows.append(_parse_announcement(ann, exchange, collected_at))

            total_pages = int(payload.get("totalpages") or 1)
            # Terminate only when we have consumed all pages per totalpages.
            # hasMore is NOT used as a termination guard: CNInfo's hisAnnouncement
            # endpoint returns hasMore=false inconsistently mid-pagination (known
            # CNInfo quirk), so `or not has_more` would silently truncate a
            # multi-page day to only the first 30 rows.
            if page_num >= total_pages:
                break
            # Wall-clock budget: keep partial rows instead of raising — newest-first
            # ordering means the truncated tail is the OLDEST slice of the window,
            # which tomorrow's 3-day re-pull covers (keep-FIRST dedup).
            if time.monotonic() - t0 > _EXCHANGE_BUDGET_S:
                log.warning(
                    "china_filings: exchange=%s hit %ds budget at page %d/%d — "
                    "keeping %d partial rows (3-day re-pull heals the tail)",
                    exchange, _EXCHANGE_BUDGET_S, page_num, total_pages, len(rows),
                )
                break
            page_num += 1
            _pace()

        log.info(
            "china_filings: exchange=%s date_range=%s pages=%d rows=%d",
            exchange, date_range, page_num, len(rows),
        )
        return rows

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Fetch filing metadata from SSE + SZSE, store, return summary frame.

        Per-exchange try/except isolation: one exchange failure never kills the
        other. Raises only when BOTH exchanges fail (circuit breaker sees it).

        Returns a summary DataFrame with a DatetimeIndex (required by the
        base.validate() contract — must be pd.to_datetime-parseable).
        """
        import requests  # lazy import

        date_range = self._date_range(full_history)
        collected_at = datetime.now(timezone.utc).isoformat()

        global LAST_RUN_OUTCOME, LAST_KEY_INTEGRITY
        LAST_KEY_INTEGRITY = None  # P1-R2: fail-closed at entry, mirrors LAST_RUN_OUTCOME
        LAST_RUN_OUTCOME = {
            "ok": False,
            "errors": ["refresh started but did not complete"],
            "per_exchange": {},
            "at": collected_at,
            "key_integrity": _zero_key_integrity(collected_at),
            # P1-R3: fail-closed at entry, same rationale as every other field
            # here — an escape before either is ever recomputed below must
            # read as "transport unproven" / "integrity unknown", never as a
            # false clean.
            "transport_ok": False,
            "key_integrity_known": False,
        }

        session = requests.Session()
        all_rows: list[dict] = []
        per_exchange: dict[str, int] = {}
        errors: list[str] = []

        for exchange in _EXCHANGES:
            try:
                rows = self._fetch_exchange(
                    exchange, date_range, session, collected_at
                )
                per_exchange[exchange] = len(rows)
                all_rows.extend(rows)
                _pace()  # inter-exchange pause
            except Exception as e:  # noqa: BLE001 — per-exchange isolation
                errors.append(f"{exchange}: {e}")
                per_exchange[exchange] = 0
                log.warning(
                    "china_filings: exchange=%s failed: %s", exchange, e
                )

        if not all_rows and errors:
            LAST_RUN_OUTCOME = {
                "ok": False,
                "errors": errors,
                "per_exchange": per_exchange,
                "at": collected_at,
                "key_integrity": _zero_key_integrity(collected_at),
                # Both exchanges raised -> transport is definitively NOT ok;
                # write_filings() is never reached on this path, so the
                # key-integrity partition is definitively unknown too.
                "transport_ok": False,
                "key_integrity_known": False,
            }
            raise RuntimeError(
                "china_filings: all exchanges failed — " + " | ".join(errors)
            )

        # P1-R3 §9: "no exchange raised" is measured HERE, before any
        # key-integrity errors are appended below — those are a distinct
        # typed cause and must never be folded into transport_ok.
        transport_ok = not errors

        net_new = write_filings(all_rows)
        log.info(
            "china_filings: %d raw rows collected, %d net-new stored (%s)",
            len(all_rows), net_new, per_exchange,
        )

        # P1-R2: write_filings() just set LAST_KEY_INTEGRITY (canonical shape,
        # zeros when clean). Fold it into LAST_RUN_OUTCOME so every consumer
        # reads one stable shape, and — FAIL-SOFT PRESERVED — malformed keys
        # degrade `ok` to False via a typed errors[] entry rather than ever
        # raising; the only raise in this method stays the all-exchanges-
        # failed branch above. Valid sibling rows are still fetched, stored,
        # and returned even when this branch fires.
        # LAST_KEY_INTEGRITY is None ONLY when write_filings() did not reach its
        # own assignment — i.e. its internal try/except fired (a store write or
        # read blew up) and it returned 0 without telling us what it had
        # partitioned. That is UNKNOWN, and `or _zero_key_integrity(...)` alone
        # would silently launder it into "clean": measured 2026-08-22, a batch
        # of 4 rows with 3 malformed and a failing to_parquet folded in
        # excluded_total=0, left ok=True, and china_visits then stamped
        # coverage and advanced last_success_utc over a store that was never
        # written — a false clean absence, the exact failure this repair
        # exists to prevent. Fail closed: name the unknown in errors[] so `ok`
        # degrades, and keep the zero-shape only so consumers still read one
        # stable shape.
        # P1-R3 §9: captured HERE, before the `or _zero_key_integrity(...)`
        # fallback below launders a None into the zero-shape — this is the
        # one moment that distinguishes "write_filings() told us nothing"
        # from "write_filings() told us it was clean". china_visits reads
        # this typed boolean instead of string-sniffing errors[].
        key_integrity_known = LAST_KEY_INTEGRITY is not None
        if LAST_KEY_INTEGRITY is None:
            errors.append(
                "key_integrity: UNKNOWN — write_filings() did not complete its "
                "key-integrity partition, so this run proves nothing about "
                "whether malformed rows were excluded"
            )
        key_integrity = LAST_KEY_INTEGRITY or _zero_key_integrity(collected_at)
        if key_integrity["excluded_total"] or key_integrity["preexisting_unkeyed"]:
            errors.append(
                f"key_integrity: {key_integrity['excluded_total']} malformed "
                f"announcementId row(s) excluded ({key_integrity['excluded_by_type']}); "
                f"{key_integrity['preexisting_unkeyed']} pre-existing unkeyed row(s) "
                "in store"
            )

        LAST_RUN_OUTCOME = {
            "ok": not errors,
            "errors": errors,
            "per_exchange": per_exchange,
            "at": collected_at,
            "key_integrity": key_integrity,
            # P1-R3 §9: typed booleans so china_visits can separate "transport
            # degraded" from "key integrity unknown" without string-sniffing
            # errors[]. `ok` semantics are UNCHANGED for every other consumer.
            "transport_ok": transport_ok,
            "key_integrity_known": key_integrity_known,
        }

        # Summary frame — DatetimeIndex is required by base.validate() /
        # store.upsert(). Follow china_official_corpora precedent (line 468):
        # strip tz-awareness so the index is tz-naive.  Mixing tz-aware with
        # any tz-naive parquet already on disk causes combine_first to raise
        # "Cannot join tz-naive with tz-aware DatetimeIndex".
        idx = pd.Timestamp(collected_at).tz_convert(None)
        summary = pd.DataFrame(
            {f"n_rows_{ex}": [float(per_exchange.get(ex, 0))]
             for ex in _EXCHANGES},
            index=[idx],
        )
        summary["n_rows_total"] = float(len(all_rows))
        summary["n_net_new"] = float(net_new)
        summary.index.name = "collected_at"
        return {"china_filings_summary": summary}


# ------------------------------------------------------------------ CLI (backfill) --

def _cli_backfill(start: str, end: str, categories: list[str]) -> None:
    """Backfill filing metadata for a date range, optionally filtered by category.

    Designed for targeted manual backfills (inquiry_letter + earnings_preann
    only). DOES NOT run as part of nightly — invoke manually on the Mac.

    Usage:
        python -m collectors.china_filings --backfill 2024-01-01 2024-12-31 \\
            --categories inquiry_letter,earnings_preann
    """
    import requests  # lazy

    log.info(
        "china_filings backfill: start=%s end=%s categories=%s",
        start, end, categories,
    )
    date_range = f"{start}~{end}"
    collected_at = datetime.now(timezone.utc).isoformat()
    session = requests.Session()

    adapter = ChinaFilingsAdapter()
    all_rows: list[dict] = []
    for exchange in _EXCHANGES:
        try:
            rows = adapter._fetch_exchange(
                exchange, date_range, session, collected_at
            )
            if categories:
                rows = [r for r in rows if r["category"] in categories]
            all_rows.extend(rows)
            log.info("china_filings backfill: %s → %d rows", exchange, len(rows))
            _pace()
        except Exception as e:  # noqa: BLE001
            log.warning(
                "china_filings backfill: exchange=%s failed: %s", exchange, e
            )

    net_new = write_filings(all_rows)
    print(
        f"Backfill complete: {len(all_rows)} rows fetched, "
        f"{net_new} net-new written."
    )


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description="CNInfo filings collector CLI")
    p.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                   help="Backfill date range YYYY-MM-DD YYYY-MM-DD")
    p.add_argument("--categories", default="",
                   help="Comma-separated categories to keep (empty = all)")
    p.add_argument("--full-history", action="store_true",
                   help="Nightly run with extended lookback (7 days)")
    args = p.parse_args()

    if args.backfill:
        start_date, end_date = args.backfill
        cats = [c.strip() for c in args.categories.split(",") if c.strip()]
        _cli_backfill(start_date, end_date, cats)
        sys.exit(0)

    # Default: run nightly adapter
    from collectors.base import run_adapter
    result = run_adapter(ChinaFilingsAdapter(), full_history=args.full_history)
    print(f"status={result.status} rows={result.rows} last_date={result.last_date}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
        sys.exit(1)
