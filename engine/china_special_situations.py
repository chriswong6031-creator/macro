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

Data freshness / ordering dependency:
    data/china_filings/filings.parquet is written by the asia-lane collect step
    (collectors/china_filings.py) that runs BEFORE this engine is invoked by
    build_china_special_situations.py. There is NO in-build refresh of china_filings
    — the collector is network-bound and belongs in the collect phase only.
    Running this engine standalone reads whatever filings.parquet was last committed
    by the collector; the asof/status chip surfaces staleness honestly.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_special_sits.v1"
_MAX_ROWS = 8  # capped row count per category — a DISPLAY limit, never a statistic
# "this week" on this desk means an explicit forward calendar window: today through
# today+_WEEK_DAYS inclusive. Any sentence saying "this week" counts only rows inside
# it — it is never inferred from whichever row happens to be soonest.
_WEEK_DAYS = 7


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


def _days_to(date_str: str | None) -> int | None:
    """Whole days from today to a forward date (negative if past). None on parse fail.

    Context-only countdown helper — a factual "how soon", never a directional call.
    """
    if not date_str:
        return None
    try:
        d = date.fromisoformat(str(date_str)[:10])
        return (d - date.today()).days
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Plain-word "so what" characterizations (DESIGN_DOCTRINE Tier-1 glance copy).
#
# These are FACTUAL context labels, NOT stances/scores/calls. They describe the
# magnitude of a disclosed event in plain words ("a real supply event", "still an
# open question") so a reader gets the "so what" without decoding ratios/codes.
# The engine stays is_context_only — no buy/sell/direction language originates
# here (see module docstring + register_claims direction=0). Every label ships as
# an {en, zh} twin so the template dual-emits without dropping raw EN into ZH.
# --------------------------------------------------------------------------- #

def _unlock_note(float_pct: float | None, dtd: int | None) -> dict:
    """Plain-word 'so what' for one unlock event. Factual supply characterization."""
    when = ""
    when_zh = ""
    if dtd is not None:
        if dtd <= 0:
            when, when_zh = "unlocking now", "正在解禁"
        elif dtd == 1:
            when, when_zh = "unlocks tomorrow", "明日解禁"
        else:
            when, when_zh = f"unlocks in {dtd}d", f"{dtd}天后解禁"
    if float_pct is None:
        return {"en": (when or "unlock scheduled"),
                "zh": (when_zh or "解禁在即"), "level": "active"}
    # ratio can exceed 100% for recently-listed small caps (the unlocking tranche is
    # larger than the CURRENT free float). Printing "211% of float" reads absurd — the
    # honest plain reading is "more shares than currently trade freely".
    if float_pct >= 100.0:
        return {"en": "more shares unlock than currently trade freely — a very large supply event"
                       + (f", {when}" if when else ""),
                "zh": "解禁数量超过当前自由流通量——供给量非常大" + (f"，{when_zh}" if when_zh else ""),
                "level": "elevated"}
    if float_pct >= 10.0:
        head = f"{float_pct:.0f}% of float"
        return {"en": f"{head} — a large supply event" + (f", {when}" if when else ""),
                "zh": f"占流通{float_pct:.0f}% — 供给量大" + (f"，{when_zh}" if when_zh else ""),
                "level": "elevated"}
    if float_pct >= 5.0:
        head = f"{float_pct:.0f}% of float"
        return {"en": f"{head} — a real supply event" + (f", {when}" if when else ""),
                "zh": f"占流通{float_pct:.0f}% — 供给可观" + (f"，{when_zh}" if when_zh else ""),
                "level": "elevated"}
    return {"en": f"{float_pct:.0f}% of float — small" + (f", {when}" if when else ""),
            "zh": f"占流通{float_pct:.0f}% — 较小" + (f"，{when_zh}" if when_zh else ""),
            "level": "active"}


# ── Inquiry thread identity ──────────────────────────────────────────────────
# china_filings carries no thread/parent identifier: announcementId is per
# DOCUMENT, and announcement_type_raw is a document-category code, not a thread.
# What the source DOES provide is the filer naming the letter it answers — either
# quoted in 《》 book-title marks or spelled out inline ending at the 函 word.
# That referenced title is the strongest source-native inquiry identity available,
# so it is the join key. Matching is additionally scoped to the same issuer, which
# is what makes the normalisation below safe: a key only has to discriminate
# between DIFFERENT inquiries of the SAME company, so tokens that carry no
# discriminating information inside one issuer (the issuer's own name, the
# exchange, the announcing firm) are stripped rather than left to block a match.
# Deterministic and pure — no inference, no LLM, no ticker-presence heuristic.
_INQ_EXCHANGE_RE = re.compile(
    r"(?:上海证券交易所|深圳证券交易所|北京证券交易所|上交所|深交所|北交所)"
)
_INQ_FN = r"(?:问询函|关注函|监管函|质询函)"
_INQ_BOOK_RE = re.compile(r"《([^《》]+)》")
_INQ_BARE_RE = re.compile(r"([一-鿿0-9A-Za-z（）()]{2,80}?" + _INQ_FN + r")")
# An announcing-party clause: a professional firm or company organ that filed the
# document, running up to the 关于 that introduces the inquiry name proper.
_INQ_PARTY_RE = re.compile(
    r"^.{0,40}?(?:会计师事务所|律师事务所|资产评估|证券股份有限公司|独立董事|监事会|保荐(?:机构|人))"
    r"[^关]{0,20}关于"
)
_INQ_CO_SUFFIX_RE = re.compile(r"(?:股份有限公司|有限责任公司|有限公司)")
_INQ_PUNCT_RE = re.compile(r"[《》（）()\[\]、，,。·\"“”'’：:]")
# 收到 belongs to the RECEIPT framing ("we received X"), not to the inquiry's
# identity — the exchange's own letter and every reply omit it. Leaving it in the
# key made a receipt permanently unmatchable: "关于收到上海证券交易所问询函的公告"
# keyed to …收到问询函 and could never equal any reply's key, so the letter was
# published as an open question while its own reply sat in the same window.
_INQ_FILLER_RE = re.compile(r"(?:关于|对|的|之|有关|相关|事项|申请文件|申请|公司|收到)")
_INQ_MIN_KEY_LEN = 6


def _inquiry_thread_keys(title: str, issuer_name: str = "") -> list[str]:
    """Deterministic inquiry-thread keys referenced by one filing title.

    Returns [] when the title names no inquiry — the caller must then report the
    reply state as 'undetermined' rather than guessing. Pure function.
    """
    text = str(title or "")
    spans = _INQ_BOOK_RE.findall(text) or _INQ_BARE_RE.findall(text)
    issuer = _INQ_CO_SUFFIX_RE.sub("", str(issuer_name or ""))
    issuer = issuer.replace("*ST", "").replace("ST", "").strip()
    keys = set()
    for span in spans:
        s = re.sub(r"\s+", "", span)
        s = _INQ_PARTY_RE.sub("", s)
        s = _INQ_EXCHANGE_RE.sub("", s)
        s = _INQ_CO_SUFFIX_RE.sub("", s)
        if len(issuer) >= 2:
            s = s.replace(issuer, "")
        s = _INQ_PUNCT_RE.sub("", s)
        s = _INQ_FILLER_RE.sub("", s)
        if len(s) >= _INQ_MIN_KEY_LEN:
            keys.add(s)
    return sorted(keys)


# Document role within the inquiry family, derived from the title.
#
# The stored `kind` cannot carry this on its own: collectors.china_filings.
# classify_kind defaults to "letter" for anything lacking 回函/回复/答复/复函/
# 专项说明/核查意见, so 100 of the 140 stored "letter" rows are actually
# reply-side filings (会计师事务所…说明, 独立董事…独立意见, 律师…法律意见书).
# Counting those as open inquiries makes the plane assert unanswered regulatory
# questions that were never asked of the company — and simultaneously discards
# them as the reply evidence they really are. `kind` is baked into the parquet and
# only the nightly may advance it, so the engine derives the role at read time.
#
# 延期回复 ("we are deferring our reply") is the trap in the other direction: it
# contains 回复 and is stored kind="reply" for all 41 such notices, so it would
# otherwise mark an inquiry answered by the very filing that says it is not.
# A deferral is specifically a postponed REPLY. Matching a bare 延期 would also
# swallow a genuine inquiry whose SUBJECT happens to concern a postponement,
# removing it from the letter population and the reply evidence at once; and the
# 延长/推迟/顺延 variants must not fall through to reply_side, where they would
# mark the inquiry answered by the notice saying it has not been.
_INQ_DEFERRAL_RE = re.compile(r"(?:延期|延长|推迟|顺延)回复")
# 意见 is deliberately broad rather than an enumeration of 核查意见/独立意见/
# 法律意见书: the reply side invents new organ and adviser forms constantly
# (独立董事意见, 董事会审计委员会…相关意见, 评估机构…发表意见, 专项法律意见), and
# an enumeration silently re-admits each new one as a fake open inquiry. Measured
# against the full store, broadening to 意见 excludes 18 further reply-side rows
# and leaves 22 survivors that are genuine "关于收到…问询函的公告" receipts or the
# exchange's own "关于对…的问询函" — no exchange-issued letter was lost.
_INQ_REPLY_SIDE_RE = re.compile(r"(?:回复|回函|复函|答复|意见|说明)")


def _inquiry_doc_role(title: Any) -> str:
    """Role of one inquiry-family filing: letter | reply_side | deferral.

    'letter'     — an exchange-issued inquiry (or the company's receipt of one)
    'reply_side' — a reply, or a professional/organ filing made in answer to one
    'deferral'   — a notice that the reply is being POSTPONED; evidence of the
                   opposite of a reply, so it answers nothing and asks nothing.
    Pure function.
    """
    text = str(title or "")
    if _INQ_DEFERRAL_RE.search(text):
        return "deferral"
    if _INQ_REPLY_SIDE_RE.search(text):
        return "reply_side"
    return "letter"


def _dedupe_letters_by_thread(rows: list[tuple[Any, str, list[str]]]) -> list[Any]:
    """Collapse rows describing the SAME inquiry down to one per (issuer, thread).

    One inquiry routinely files twice: the exchange publishes its own letter AND
    the company publishes a receipt announcement for it, with identical thread
    keys (measured on 600683 京投发展, both 2026-05-12). Counting rows rather than
    inquiries reported one question as two. Rows carrying no thread key cannot be
    proven duplicate, so every one is kept. Input order is preserved.
    """
    seen: set[tuple[str, str]] = set()
    out = []
    for row, sec_code, keys in rows:
        if keys:
            ident = {(sec_code, k) for k in keys}
            if ident & seen:
                continue
            seen |= ident
        out.append(row)
    return out


def _resolve_reply_state(
    sec_code: str,
    title: Any,
    issuer_name: Any,
    reply_threads: set[tuple[str, str]],
) -> str:
    """Reply state for one inquiry letter against known (issuer, thread) replies.

    'replied'      — a same-issuer reply-side filing names the same inquiry.
    'open'         — the letter names an inquiry and nothing answered THAT inquiry
                     inside the window.
    'undetermined' — no inquiry name could be extracted, so no honest claim is
                     available. Never silently optimistic: an unmatched letter is
                     never reported as replied.
    """
    keys = _inquiry_thread_keys(title, issuer_name)
    if not keys:
        return "undetermined"
    if any((sec_code, k) in reply_threads for k in keys):
        return "replied"
    return "open"


def _inquiry_note(reply_state: str) -> dict:
    """Plain-word 'so what' for one exchange inquiry letter."""
    if reply_state == "replied":
        return {"en": "the company has replied", "zh": "公司已回复", "level": "active"}
    if reply_state == "undetermined":
        return {"en": "reply status not established from the filing record",
                "zh": "根据公告记录无法确认回复状态", "level": "active"}
    return {"en": "an open question — no reply filed in the window",
            "zh": "该窗口内尚无回复的公开问询", "level": "elevated"}


def _inquiry_glance(n_letters: int, n_open: int, n_undetermined: int = 0) -> dict:
    """Plane glance for exchange inquiry letters. Elevated on any open letter.

    Counts are population counts over the whole 14-day window, never the display
    slice, and the sentence is scoped to that window — a letter answered before
    the window opened is not something this plane can see, so it says "in the last
    14 days" rather than asserting a letter is unanswered outright.
    """
    if n_open:
        return {"level": "elevated",
                "en": (f"{n_open} letter{'s' if n_open > 1 else ''} with no reply "
                       f"filed in the last 14 days."),
                "zh": f"过去14天有{n_open}封问询函未见回复。"}
    if n_undetermined:
        return {"level": "active",
                "en": (f"{n_undetermined} letter{'s' if n_undetermined > 1 else ''} "
                       f"— reply status not established."),
                "zh": f"{n_undetermined}封问询函回复状态无法确认。"}
    if n_letters:
        return {"level": "active",
                "en": f"{n_letters} letter{'s' if n_letters > 1 else ''}, all replied.",
                "zh": f"{n_letters}封问询函，均已回复。"}
    return {"level": "quiet", "en": "No inquiry letters.", "zh": "无问询函。"}


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

        # ── Population statistics, computed BEFORE any display truncation ──
        # `fwd` is the POPULATION (every unlock in the next 30d). `events` below
        # is a DISPLAY slice of _MAX_ROWS. Counting "large" off the slice made the
        # display cap an analytical cap: because `fwd` is sorted by float% desc,
        # the count saturated at _MAX_ROWS and the hero read "8 large unlocks"
        # against a 144-event population. A display limit is never a statistic.
        fwd["_large"] = fwd["_float_pct"].apply(
            lambda x: x is not None and not pd.isna(x) and x >= 5.0
        )
        # "this week" is an explicit calendar window — today .. today+7 inclusive —
        # never "whatever the soonest row happens to be".
        week_end = today_ts + pd.Timedelta(days=_WEEK_DAYS)
        in_week = (fwd[date_col] >= today_ts) & (fwd[date_col] <= week_end)
        # Whether ANY row carries a usable float share at all — distinguishes
        # "measured, none large" from "we could not measure".
        _float_pct_known = bool(
            fwd["_float_pct"].apply(lambda x: x is not None and not pd.isna(x)).any()
        )
        n_events_30d = int(len(fwd))
        n_large_30d = int(fwd["_large"].sum())
        n_events_7d = int(in_week.sum())
        n_large_7d = int((in_week & fwd["_large"]).sum())

        events = []
        for _, row in fwd.head(_MAX_ROWS).iterrows():
            float_pct = _safe_float(row.get("_float_pct")) if "_float_pct" in row.index else None
            unlock_date = row[date_col].strftime("%Y-%m-%d") if pd.notna(row[date_col]) else None
            _dtd = _days_to(unlock_date)
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
                # days_to: whole-day forward countdown (context-only); note: plain-word twin
                "days_to":     _dtd,
                "note":        _unlock_note(float_pct, _dtd),
            }
            # Cycle-context chip (W5): stamp regime quad/liquidity/cycle at unlock date.
            # Muted/descriptive only — no directional language.
            if unlock_date:
                chip = _regime_chip_for_date(unlock_date)
                if chip:
                    ev["regime_chip"] = chip
            events.append(ev)

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

        # Plane glance: elevated when any ≥5%-float ("large") supply event is queued.
        # Every number below comes from the POPULATION (fwd), and each sentence
        # names the window its own count was measured over — a count taken over
        # 30 days may never be described as happening "this week".
        if n_large_7d:
            glance = {
                "level": "elevated",
                "en": (f"{n_large_7d} large unlock{'s' if n_large_7d > 1 else ''} "
                       f"in the next {_WEEK_DAYS} days (≥5% of float)."),
                "zh": f"未来{_WEEK_DAYS}天有{n_large_7d}笔大额解禁（占流通≥5%）。",
            }
        elif n_large_30d:
            glance = {
                "level": "elevated",
                "en": (f"{n_large_30d} large unlock{'s' if n_large_30d > 1 else ''} "
                       f"in the next 30 days (≥5% of float)."),
                "zh": f"未来30天有{n_large_30d}笔大额解禁（占流通≥5%）。",
            }
        elif n_events_30d and not _float_pct_known:
            # No usable float ratio on any row: we can count the events but cannot
            # rank them, so "none large" would be a negative the data cannot support.
            glance = {"level": "active",
                      "en": f"{n_events_30d} unlocks in 30d; float share not reported.",
                      "zh": f"未来30天{n_events_30d}笔解禁；未披露占流通比例。"}
        elif n_events_30d:
            glance = {"level": "active",
                      "en": f"{n_events_30d} unlocks in 30d, none large.",
                      "zh": f"未来30天{n_events_30d}笔解禁，均不大额。"}
        else:
            glance = {"level": "quiet", "en": "No unlocks ahead.", "zh": "近期无解禁。"}

        return {
            "asof": asof, "status": status,
            "events": events,                 # DISPLAY slice, capped at _MAX_ROWS
            "weekly_strip": weekly_strip,
            "n_events_30d": n_events_30d,     # population counts — never display-capped
            "n_large_30d": n_large_30d,
            "n_events_7d": n_events_7d,
            "n_large_7d": n_large_7d,
            "week_days": _WEEK_DAYS,
            # Back-compat alias for existing consumers (china_altdata.html.j2); now
            # carries the true 30d population count instead of the display-slice count.
            "n_large": n_large_30d,
            "n_shown": len(events),
            "glance": glance,
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

            # Reply lookup keyed by (issuer, inquiry thread) — NOT by issuer alone.
            # Keying on the ticker let any reply from a company mark every one of
            # that company's letters answered, including letters belonging to a
            # different inquiry entirely. Replies AND attachments both count as
            # reply-side evidence: a third-party 核查意见 filed against an inquiry
            # is filed because that inquiry is being answered.
            df_filt["_role"] = df_filt["title"].apply(_inquiry_doc_role)
            reply_threads: set[tuple[str, str]] = set()
            _is_evidence = (
                (df_filt["kind"] != "letter") | (df_filt["_role"] == "reply_side")
            ) & (df_filt["_role"] != "deferral")
            for _, rr in df_filt[_is_evidence].iterrows():
                _code = str(rr.get("sec_code") or "")
                for _k in _inquiry_thread_keys(rr.get("title"), rr.get("sec_name")):
                    reply_threads.add((_code, _k))

            # Exchange-issued letters only: `kind` alone would admit reply-side
            # filings (see _inquiry_doc_role), which would then be published as
            # unanswered inquiries.
            _letters_df = df_filt[
                (df_filt["kind"] == "letter") & (df_filt["_role"] == "letter")
            ].sort_values("_date_str", ascending=False, na_position="last")
            # One inquiry, one row (see _dedupe_letters_by_thread).
            letter_rows = _dedupe_letters_by_thread([
                (r, str(r.get("sec_code") or ""),
                 _inquiry_thread_keys(r.get("title"), r.get("sec_name")))
                for _, r in _letters_df.iterrows()
            ])

            # Resolve reply state for the WHOLE letter population first, so the
            # counts below describe the population and not the display slice.
            states = [
                _resolve_reply_state(
                    str(r.get("sec_code") or ""), r.get("title"),
                    r.get("sec_name"), reply_threads,
                )
                for r in letter_rows
            ]

            rows = []
            for r, _state in list(zip(letter_rows, states))[:_MAX_ROWS]:
                letter_date = str(r.get("_date_str") or "")
                # secCode for claim-key: filings uses sec_code
                sec_code_val = str(r.get("sec_code") or "")
                letter: dict = {
                    "secCode":   sec_code_val,
                    "secName":   str(r.get("sec_name") or ""),
                    "title":     str(r.get("title") or ""),
                    "date":      letter_date,
                    "pdf_url":   str(r.get("adjunct_url") or ""),
                    "reply_state": _state,          # replied | open | undetermined
                    # has_reply stays the strict positive claim: True ONLY on a
                    # thread-matched reply. 'undetermined' must never read as replied.
                    "has_reply": _state == "replied",
                    "type_name": str(r.get("announcement_type_raw") or ""),
                    "note":      _inquiry_note(_state),
                    # Note: no 'kind' key — list is letters-only; register_claims must not filter on kind
                }
                if letter_date:
                    chip = _regime_chip_for_date(letter_date[:10])
                    if chip:
                        letter["regime_chip"] = chip
                rows.append(letter)

            n_replies = int(len(df_filt[df_filt["kind"] == "reply"]))
            _n_letters = int(len(letter_rows))
            _n_open = sum(1 for s in states if s == "open")
            _n_undetermined = sum(1 for s in states if s == "undetermined")
            _n_replied = sum(1 for s in states if s == "replied")
            return {
                "asof": asof, "status": status,
                "letters": rows,                    # DISPLAY slice
                "n_letters": _n_letters,            # population counts below
                "n_replies": n_replies,
                "n_replied": _n_replied,
                "n_open": _n_open,
                "n_undetermined": _n_undetermined,
                # Back-compat alias; now the population open count, not a slice count.
                "n_unreplied": _n_open,
                "n_shown": len(rows),
                "glance": _inquiry_glance(_n_letters, _n_open, _n_undetermined),
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

            # Same thread-identity and document-role contract as the filings path.
            df_filt["_role"] = df_filt["announcementTitle"].apply(_inquiry_doc_role)
            reply_threads: set[tuple[str, str]] = set()
            _is_evidence = (
                (df_filt["kind"] != "letter") | (df_filt["_role"] == "reply_side")
            ) & (df_filt["_role"] != "deferral")
            for _, rr in df_filt[_is_evidence].iterrows():
                _code = str(rr.get("secCode") or "")
                for _k in _inquiry_thread_keys(
                    rr.get("announcementTitle"), rr.get("secName")
                ):
                    reply_threads.add((_code, _k))

            _letters_df = df_filt[
                (df_filt["kind"] == "letter") & (df_filt["_role"] == "letter")
            ].sort_values("announcementTime", ascending=False, na_position="last")
            letter_rows = _dedupe_letters_by_thread([
                (r, str(r.get("secCode") or ""),
                 _inquiry_thread_keys(r.get("announcementTitle"), r.get("secName")))
                for _, r in _letters_df.iterrows()
            ])

            states = [
                _resolve_reply_state(
                    str(r.get("secCode") or ""), r.get("announcementTitle"),
                    r.get("secName"), reply_threads,
                )
                for r in letter_rows
            ]

            rows = []
            for r, _state in list(zip(letter_rows, states))[:_MAX_ROWS]:
                letter_date = str(r.get("announcementTime") or "")
                letter: dict = {
                    "secCode":   str(r.get("secCode") or ""),
                    "secName":   str(r.get("secName") or ""),
                    "title":     str(r.get("announcementTitle") or ""),
                    "date":      letter_date,
                    "pdf_url":   str(r.get("adjunctUrl") or ""),
                    "reply_state": _state,
                    "has_reply": _state == "replied",
                    "type_name": str(r.get("announcementTypeName") or ""),
                    "note":      _inquiry_note(_state),
                    # Note: no 'kind' key — list is letters-only
                }
                if letter_date:
                    chip = _regime_chip_for_date(letter_date[:10])
                    if chip:
                        letter["regime_chip"] = chip
                rows.append(letter)

            _n_letters = int(len(letter_rows))
            _n_open = sum(1 for s in states if s == "open")
            _n_undetermined = sum(1 for s in states if s == "undetermined")
            _n_replied = sum(1 for s in states if s == "replied")
            return {
                "asof": asof, "status": status,
                "letters": rows,
                "n_letters": _n_letters,
                "n_replies": int(len(df_filt[df_filt["kind"] == "reply"])),
                "n_replied": _n_replied,
                "n_open": _n_open,
                "n_undetermined": _n_undetermined,
                "n_unreplied": _n_open,
                "n_shown": len(rows),
                "glance": _inquiry_glance(_n_letters, _n_open, _n_undetermined),
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

        _n = len(df)
        glance = ({"level": "active",
                   "en": f"{_n} pre-announcements this season.",
                   "zh": f"本季度{_n}份业绩预告。"} if _n else
                  {"level": "quiet", "en": "No pre-announcements yet.",
                   "zh": "暂无业绩预告。"})
        return {
            "asof": asof, "status": status,
            "by_type": by_type,
            "top_movers": top_movers,
            "n_total": _n,
            "glance": glance,
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
        _na = len(active)
        glance = ({"level": "active",
                   "en": f"{_na} active buyback program{'s' if _na > 1 else ''}.",
                   "zh": f"{_na}项进行中的回购计划。"} if _na else
                  {"level": "quiet", "en": "No active buybacks.", "zh": "无进行中的回购。"})
        return {"asof": asof, "status": status, "top": top, "n_active": _na,
                "glance": glance}
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
        glance = ({"level": "elevated",
                   "en": f"{n_high} name{'s' if n_high > 1 else ''} with heavy pledging (≥50%).",
                   "zh": f"{n_high}只个股质押较重（≥50%）。"} if n_high else
                  {"level": "quiet", "en": "No heavy-pledge names.", "zh": "无重度质押个股。"})
        return {"asof": asof, "status": status, "top": top, "n_high": n_high,
                "quarter": str(df["quarter"].max()) if "quarter" in df.columns else None,
                "glance": glance}
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

        _nadd = len(additions)
        if _nadd:
            glance = {"level": "elevated",
                      "en": f"{_nadd} new name{'s' if _nadd > 1 else ''} flagged for risk.",
                      "zh": f"新增{_nadd}只风险警示个股。"}
        elif count:
            glance = {"level": "active",
                      "en": f"{count} names on the risk-warning board.",
                      "zh": f"风险警示板共{count}只个股。"}
        else:
            glance = {"level": "quiet", "en": "No risk-warning names.", "zh": "无风险警示个股。"}
        return {
            "asof": asof, "status": status,
            "count": count,
            "top_current": top_current,
            "additions": additions,
            "removals": removals,
            "history_note": history_note,
            "glance": glance,
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

        _n_anom = len(top_premium) + len(top_discount)
        glance = ({"level": "active",
                   "en": f"{_n_anom} block-trade price gap{'s' if _n_anom > 1 else ''}.",
                   "zh": f"{_n_anom}笔大宗交易价差异常。"} if _n_anom else
                  {"level": "quiet", "en": "No block-trade anomalies.", "zh": "无大宗交易异常。"})
        return {"asof": asof, "status": status,
                "top_premium": top_premium, "top_discount": top_discount,
                "n_names": len(df), "glance": glance}
    except Exception as e:  # noqa: BLE001
        log.warning("china_special_sits: block trade block failed (%s)", e)
        return None


# ── Goodwill dimensional contract ────────────────────────────────────────────
# The upstream aggregate carries Chinese-keyed columns whose UNITS cannot be
# inferred from magnitude: absolute CNY, fractional ratios (1.0 == 100%) and a
# period string all sit side by side. Emitting them raw forced the template to
# guess from magnitude ("v > 1000 → 亿, else → %"), which printed a −¥51.2bn
# impairment as "-51245300029.70%" and a 2.58% ratio as "0.03%".
# Units now live in the field NAME. Never re-derive a unit from a magnitude.
_GOODWILL_CNY_FIELDS = {          # absolute CNY (yuan), sign-preserving
    "商誉":       "goodwill_cny",
    "商誉减值":   "impairment_cny",
    "净资产":     "net_assets_cny",
    "净利润规模": "net_profit_cny",
}
_GOODWILL_FRACTION_FIELDS = {     # source stores a FRACTION; ×100 exactly once here
    "商誉占净资产比例":     "goodwill_to_net_assets_pct",
    "商誉减值占净资产比例": "impairment_to_net_assets_pct",
    "商誉减值占净利润比例": "impairment_to_net_profit_pct",
}
_GOODWILL_PERIOD_SRC = "报告期"


def _goodwill_row(raw: dict, asof: str | None) -> dict:
    """Project one raw goodwill record onto the typed canonical contract.

    Pure function — no I/O, unit-testable. Every emitted numeric field carries
    its unit in its NAME:
      *_cny  — absolute yuan, sign preserved (a negative impairment stays money)
      *_pct  — percent on a 0-100 scale (source fraction already ×100 here)
    A value the source omits (None/NaN/empty string) emits None, never 0.0 and
    never "" — a missing impairment must not render as a real zero.
    """
    out: dict = {"period": _safe_str(raw.get(_GOODWILL_PERIOD_SRC)) or None}
    for src, dest in _GOODWILL_CNY_FIELDS.items():
        out[dest] = _safe_float(raw.get(src))
    for src, dest in _GOODWILL_FRACTION_FIELDS.items():
        f = _safe_float(raw.get(src))
        out[dest] = None if f is None else f * 100.0
    out["asof"] = asof
    return out


def _goodwill_block() -> dict | None:
    """Whole-market annual goodwill aggregate context chip.

    Emits typed rows (see _goodwill_row) plus the untouched source record under
    `raw` for provenance, so the dimensional projection stays auditable.
    """
    path = _data_dir() / "china_st" / "goodwill.parquet"
    asof, status = _asof_status(path)
    try:
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty:
            return None
        rows = []
        for raw in df.tail(5).to_dict("records"):
            # Coerce provenance copy to JSON-safe scalars (numpy int64 → TypeError).
            prov = {}
            for k, v in raw.items():
                f = _safe_float(v)
                prov[str(k)] = f if f is not None else (_safe_str(v) or None)
            row = _goodwill_row(raw, asof)
            row["raw"] = prov
            rows.append(row)
        return {"asof": asof, "status": status, "annual_rows": rows[:5]}
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

# Plane display order + icon/label metadata for the hero overhang meter.
# label twins are plain-word plane names (no internal/machine vocabulary).
# Plane status vocabulary. `stale` is READABLE but NOT current: it keeps its
# last-known reading visible and dated, and is excluded from aggregate authority.
_PLANE_UNREADABLE = (None, "missing", "no_date_col")
_PLANE_STALE = ("stale",)

_PLANE_META = [
    ("unlocks",      "🔓", {"en": "Unlock supply",   "zh": "解禁供给"}),
    ("inquiry",      "📬", {"en": "Open questions",   "zh": "监管问询"}),
    ("preannounce",  "📋", {"en": "Earnings previews","zh": "业绩预告"}),
    ("buyback",      "🔄", {"en": "Buybacks",         "zh": "股份回购"}),
    ("pledge",       "⛓️", {"en": "Pledge stress",    "zh": "质押压力"}),
    ("st",           "🚨", {"en": "Risk warnings",    "zh": "风险警示"}),
    ("block_trades", "📦", {"en": "Block trades",     "zh": "大宗交易"}),
]


def _build_hero(blocks: dict) -> dict:
    """Aggregate 'overhang glance' hero — context-only, no score/direction.

    Emits: a per-plane segment list (level quiet/active/elevated + plain label),
    the count of elevated planes, a single 'most notable' item, and a plain-word
    stance sentence. All strings are {en, zh} twins. The stance NEVER implies a
    trade — the honest resting state is "watch — don't chase".
    """
    segments = []
    n_elevated = 0
    n_active = 0
    n_stale = 0
    stale_labels: list[dict] = []
    for key, icon, label in _PLANE_META:
        blk = blocks.get(key) or {}
        g = blk.get("glance") if isinstance(blk, dict) else None
        status = blk.get("status") if isinstance(blk, dict) else None
        # A missing/unreadable plane reads 'quiet' visually but is NOT counted as hot.
        level = (g or {}).get("level", "quiet")
        readable = isinstance(blk, dict) and status not in _PLANE_UNREADABLE
        # Fresh == readable AND observed recently enough to describe the market NOW.
        # A stale plane keeps its last-known reading on screen, but it may not lend
        # that reading aggregate authority: a six-week-old ST board answering
        # "what is happening today" is the exact failure this guard exists to stop.
        fresh = readable and status not in _PLANE_STALE
        line = g if g else {"en": "nothing flagged", "zh": "无标记"}
        if not readable:
            level = "quiet"
        elif not fresh:
            n_stale += 1
            stale_labels.append(label)
            # Re-frame the plain line as an observation with a date on it, so the
            # number on screen never reads as a current count.
            _asof = str(blk.get("asof") or "")
            line = {
                "en": f"{line.get('en', '')} Last seen {_asof} — not updated since.".strip(),
                "zh": f"{line.get('zh', '')}最后观测 {_asof}，此后未更新。".strip(),
            }
        # Only FRESH planes count toward the aggregate state.
        if fresh and level == "elevated":
            n_elevated += 1
        elif fresh and level == "active":
            n_active += 1
        segments.append({
            "key": key, "icon": icon, "label": label, "level": level,
            "line": line,
            "status": status,
            "stale": readable and not fresh,
            "readable": readable,
            "asof": blk.get("asof") if isinstance(blk, dict) else None,
            # False when this plane's reading is excluded from the aggregate state.
            "counts_toward_state": bool(fresh),
        })

    # Most notable = soonest large unlock, else an unreplied letter, else new ST,
    # else heavy pledge — the single item a watcher would look at first.
    notable = None

    def _current(key: str) -> dict:
        """A plane's block only if its reading is current.

        `notable` asserts "look at this now", which no frozen observation can
        support — so every candidate source is gated, not just ST.
        """
        blk = blocks.get(key) or {}
        status = blk.get("status") if isinstance(blk, dict) else None
        if status in _PLANE_UNREADABLE or status in _PLANE_STALE:
            return {}
        return blk

    u = _current("unlocks")
    large = [e for e in (u.get("events") or []) if e.get("large_flag")]
    if large:
        large.sort(key=lambda e: (e.get("days_to") if e.get("days_to") is not None else 1e9))
        e = large[0]
        notable = {
            "icon": "🔓", "ticker": e.get("ticker", ""), "name": e.get("name", ""),
            "en": (e.get("note") or {}).get("en", ""),
            "zh": (e.get("note") or {}).get("zh", ""),
            "days_to": e.get("days_to"),
        }
    if notable is None:
        inq = _current("inquiry")
        # Only a letter we positively established as OPEN may be headlined as
        # unanswered; an 'undetermined' letter is not evidence of an open question.
        unreplied = [l for l in (inq.get("letters") or [])
                     if l.get("reply_state") == "open"]
        if unreplied:
            l = unreplied[0]
            notable = {"icon": "📬", "ticker": l.get("secCode", ""), "name": l.get("secName", ""),
                       "en": "an exchange inquiry letter with no reply filed",
                       "zh": "一封未见回复的交易所问询函", "days_to": None}
    if notable is None:
        st = _current("st")
        adds = st.get("additions") or []
        if adds:
            a = adds[0]
            notable = {"icon": "🚨", "ticker": a.get("ticker", ""), "name": a.get("name", ""),
                       "en": "newly flagged for risk-warning", "zh": "新增风险警示",
                       "days_to": None}
    if notable is None:
        pl = _current("pledge")
        tops = pl.get("top") or []
        if tops and (pl.get("n_high") or 0):
            t = tops[0]
            notable = {"icon": "⛓️", "ticker": t.get("ticker", ""), "name": t.get("name", ""),
                       "en": "carrying heavy pledged shares", "zh": "质押比例较重",
                       "days_to": None}

    # Aggregate state + plain stance sentence. Resting stance is always "watch".
    if n_elevated >= 2:
        state = "elevated"
        stance = {
            "en": "Several event fronts are active — elevated overhang. Watch the names below, don't chase.",
            "zh": "多条事件线活跃——事件压力偏高。留意下列个股，不追。",
        }
    elif n_elevated == 1:
        state = "elevated"
        stance = {
            "en": "One event front stands out this week. Worth a look — but this is context, not a trade.",
            "zh": "本周有一条事件线较为突出。值得关注——仅为背景，非交易信号。",
        }
    elif n_active:
        state = "active"
        stance = {
            "en": "Some routine activity, nothing outsized. Nothing to act on — just keeping watch.",
            "zh": "有一些常规动态，无异常规模。无需操作——保持观察。",
        }
    else:
        state = "quiet"
        stance = {
            "en": "A quiet board — no notable event overhang today. Nothing to do.",
            "zh": "整体平静——今日无明显事件压力。无需操作。",
        }

    # Coverage receipt. Tier-1 copy reads this instead of asserting the board is
    # whole: when a plane is stale or unreadable the page must say so in the same
    # breath as the aggregate, not only in a small per-plane chip.
    n_planes = len(_PLANE_META)
    n_unreadable = sum(1 for s in segments if not s["readable"])
    freshness = {
        "n_planes": n_planes,
        "n_fresh": n_planes - n_stale - n_unreadable,
        "n_stale": n_stale,
        "n_unreadable": n_unreadable,
        "all_fresh": n_stale == 0 and n_unreadable == 0,
        "stale_labels": stale_labels,
        # Oldest observation among planes that are readable but no longer current.
        "oldest_stale_asof": min(
            [str(s["asof"]) for s in segments if s["stale"] and s.get("asof")],
            default=None,
        ),
    }
    if not freshness["all_fresh"]:
        stance = {
            "en": (stance["en"] + " Part of the board is not current — "
                   "this read covers the planes that are."),
            "zh": (stance["zh"] + "部分数据线尚未更新——本解读仅覆盖数据为最新的部分。"),
        }

    return {
        "state": state,           # quiet | active | elevated  (drives aurora + accent)
        "n_elevated": n_elevated,
        "n_active": n_active,
        "n_planes": n_planes,
        "n_stale": n_stale,
        "freshness": freshness,
        "segments": segments,
        "notable": notable,
        "stance": stance,
    }


def _track_summary() -> dict | None:
    """Honest track-of-record receipt for the cn_special_sits claim family.

    Reads site/qledger/track_record.json (written by the nightly qledger runner).
    These are SALIENCE-ONLY claims (direction=0): there is no directional hit to
    rate, so we NEVER surface a hit_rate or an excess-return figure — at this n it
    would be noise dressed as a result and would violate 'numbers carry meaning'.
    We surface only: how long we've been watching (n flags, n distinct days) and
    the plain-word maturity state ('still learning' while ACCRUING). Omits (returns
    None) on any read failure so the page degrades gracefully — never fabricates.
    """
    try:
        p = _site_dir() / "qledger" / "track_record.json"
        if not p.exists():
            return None
        doc = json.loads(p.read_text())
        fam = (doc.get("by_family") or {}).get("cn_special_sits")
        if not isinstance(fam, dict) or not fam:
            return None
        # pick the shortest available horizon row (earliest to mature)
        horizon = sorted(fam.keys(), key=lambda k: int(k))[0]
        row = fam.get(horizon) or {}
        n_obs = int(row.get("n_obs") or 0)
        n_dates = int(row.get("n_dates") or 0)
        if n_obs <= 0:
            return None
        state = str(row.get("state") or "ACCRUING")
        maturing = state != "GRADED"
        return {
            "n_obs": n_obs,
            "n_dates": n_dates,
            "state": state,
            "maturing": maturing,
            "en": (
                f"We've tracked {n_obs} flagged event{'s' if n_obs != 1 else ''} "
                f"across {n_dates} day{'s' if n_dates != 1 else ''} so far. "
                "Too few, too soon to say whether flagged names behave differently — "
                "this is a watch list, not a scorecard."
                if maturing else
                f"Tracking {n_obs} flagged events across {n_dates} days."
            ),
            "zh": (
                f"目前已跟踪{n_obs}个标记事件，覆盖{n_dates}个交易日。"
                "样本仍少、时间尚短，还无法判断被标记个股是否表现不同——"
                "这是观察清单，不是成绩单。"
                if maturing else
                f"已跟踪{n_obs}个标记事件，覆盖{n_dates}个交易日。"
            ),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("china_special_sits: track summary read failed (%s)", e)
        return None


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
    hero = _build_hero(blocks)
    track = _track_summary()

    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "asof": _today(),
        "data_asof": data_asof,
        **blocks,
        "hero": hero,
        "track": track,
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


# Cutoff for legacy UTC-basis sidecar keys.
# The legacy collector (collectors/china_inquiry.py) was retired in this PR; its nightly
# dispatch is removed. Sidecar keys written on or before this date may carry UTC-basis
# dates that lag CST by one day. After this date, only canonical CST keys are written.
# The ±1 day variant checks in register_claims are scoped to rows whose canonical event
# date is <= this cutoff (transition-era rows only) — applying them to post-cutoff dates
# would cause over-suppression for genuinely distinct letters from the same company on
# consecutive days (e.g., letter A on date D already registered; distinct letter B with
# canonical date D+1 would check {D+1, D, D+2}, hit A's key D, and be wrongly suppressed).
_LEGACY_UTC_KEY_CUTOFF = "2026-07-06"


def _cst_claim_keys(sec_code: str, date_str: str) -> tuple[str, str, str]:
    """Return (canonical_key, utc_variant_key, cst_plus1_key) for an inquiry claim.

    Canonical key: the claim key derived from date_str as given (for the filings plane
    this is already the CST date; for a legacy-path snap the stored date is a UTC date).

    utc_variant_key: canonical_key with date − 1 day.
        Rationale: the filings plane stores publish_ts in Asia/Shanghai; publish_ts[:10]
        is the CST date (D). The legacy collector stored UTC-basis dates; for events at
        00:00–08:00 CST (prior UTC day), the legacy date was D−1. Checking utc_variant_key
        ensures that a claim registered from the filings path (canonical=D) blocks
        re-registration from the legacy path (which arrives with date D−1 → its
        canonical_key would be inq_{code}_{D-1}).

    cst_plus1_key: canonical_key with date + 1 day.
        Rationale (reverse direction): when the legacy source arrives first with date=D−1
        (UTC date), and the filings source has already written canonical=D to the sidecar,
        the legacy processing sees date=D−1 → canonical=D−1, utc_variant=D−2.  Neither
        matches D in the sidecar. The fix: also check D−1+1 = D (the CST "next day"
        candidate for a UTC-dated row). Legacy UTC date can lag CST by one day, never
        lead; so checking date+1 as an additional sidecar lookup covers that direction.
        Document: "legacy UTC date can lag CST by one day, never lead."

    Dedup contract: register_claims checks ALL THREE keys only for transition-era rows
    (canonical date <= _LEGACY_UTC_KEY_CUTOFF). Post-cutoff rows use canonical key only.
    Registration always writes the canonical key (the date_str as provided by the snap —
    already CST for filings).
    """
    from datetime import date as _date, timedelta as _td
    canonical_key = f"inq_{sec_code}_{date_str}"
    try:
        d = _date.fromisoformat(date_str)
        utc_date = (d - _td(days=1)).isoformat()
        cst_plus1_date = (d + _td(days=1)).isoformat()
    except Exception:  # noqa: BLE001 — malformed date_str; fall back to same key
        utc_date = date_str
        cst_plus1_date = date_str
    utc_variant_key = f"inq_{sec_code}_{utc_date}"
    cst_plus1_key = f"inq_{sec_code}_{cst_plus1_date}"
    return canonical_key, utc_variant_key, cst_plus1_key


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

    Claim-key timezone canonicalization (CST skew fix):
        The canonical claim key uses the Asia/Shanghai (CST) calendar date of the event.
        The legacy collector (collectors/china_inquiry.py) stored UTC-basis dates; for
        events published 00:00–08:00 CST, the legacy UTC date is one day behind the CST
        date. To prevent double-registration across the source switch, when checking the
        sidecar this function tests BOTH the canonical CST-basis key AND the legacy
        UTC-basis key (CST date − 1 day). Registration always writes the canonical key.
        See _cst_claim_keys() for the derivation.

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
        # Canonical key is the date as given; also check date−1 (utc_variant, for
        # filings-first blocking legacy re-registration) and date+1 (cst_plus1, for
        # legacy-first blocking filings re-registration). Legacy UTC date can lag
        # CST by one day, never lead. See _cst_claim_keys() for full derivation.
        event_key, utc_variant_key, cst_plus1_key = _cst_claim_keys(sec_code, announce_date)
        # Scope ±1 variant checks to transition-era rows only.
        # Legacy UTC-basis sidecar keys can only reference event dates <= _LEGACY_UTC_KEY_CUTOFF
        # (the legacy collector was retired in the PR that introduced that cutoff). Applying
        # the variant checks beyond the cutoff date would cause over-suppression: a distinct
        # letter B with canonical date D+1 would check {D+1, D, D+2} and wrongly hit letter
        # A's key D, silently under-counting the cn_special_sits qledger family.
        if event_key in registered_keys:
            continue  # already registered (canonical key match)
        if announce_date <= _LEGACY_UTC_KEY_CUTOFF:
            # Transition-era row: check ±1 day variants to catch UTC/CST skew
            if utc_variant_key in registered_keys or cst_plus1_key in registered_keys:
                continue  # already registered via the other-source date variant
        scope_type, scope_key = _entity_claim("", sec_code)
        try:
            claim_asof = announce_date  # stamp from the event's own date
            pending.append(qledger.make_claim(
                desk=DESK, asof=claim_asof, scope_type=scope_type,
                scope_key=scope_key, direction=0, horizon_d=HORIZON_D,
                horizon_unit=qledger.HORIZON_UNIT_TRADING,   # P0a
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
                horizon_unit=qledger.HORIZON_UNIT_TRADING,   # P0a
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
