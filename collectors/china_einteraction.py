"""上证e互动 (SSE investor-interaction platform) Q&A collector — CONTEXT ONLY (W1 CNH).

上证e互动 is the Shanghai twin of 深交所互动易 (collectors/china_irm.py): investors ask a
listed company a question on the record and the company answers. The SS half of the
board universe (site/factordata/china_setups.json → buy, *.SS) is pulled here; the SZ
half is china_irm's. Store: data/china_einteraction/qa.parquet, one row per feed item.

The platform is a TWO-STEP flow — its feed endpoint is keyed on an internal ``uid``,
not on the stock code — so a code→uid map is built ONCE from the company directory and
cached in uid_map.json:

  MAP-BUILD NIGHT  uid_map.json absent (or incomplete): page the directory ONLY and
                   skip every feed pull that night. The directory is ~72 pages today
                   at ≈1.15 s/page, which nearly fills the whole step budget, so the
                   build is RESUMABLE — a build truncated by the wall-clock guard
                   records next_page and continues tomorrow instead of restarting
                   (and instead of pretending a partial map is complete).
  NORMAL NIGHT     ≤40 SS names, cursor-rotated, one feed page each.
  MAP REFRESH      only when a shard name is missing from the map AND the map is
                   older than 30 days (resolved_at stamp) — a new listing is a logged
                   coverage null until then, never a nightly full re-crawl.

CONTEXT / INPUT TIER ONLY: nothing here is scored, ranked or promoted, and there is no
dedicated surface — the leg appears only as a pending-tier inventory row in the
signal-lab scorecard (engine/china_signal_lab.py, rendered on china_altdata with a 待验
badge). Q&A text is stored as an input plane, not a display surface.

VERIFIED ENDPOINTS (live 2026-07-25, this runner):
  POST /allcompany.do          form {"code":"0","order":"2","areaId":"0","page":N}
       → {"content": "<html fragment>"}; each company is an <a rel='tag' uid=65 …>
         (the uid attribute is UNQUOTED — bs4/lxml handles it) wrapping an
         <img src=".../600000.png?random=…"> whose filename stem is the stock code.
  POST /ajax/userfeeds.do?typeCode=company&type=11&pageSize=30&uid=<uid>&page=1
       ALL params in the query string; the response is PURE HTML (not JSON).
       Each Q&A exchange is a div.m_feed_item[id^="item-"]: the first
       div.m_feed_detail is the question (asker a[rel=face], div.m_feed_txt whose
       leading anchor is the "浦发银行(600000)" prefix, div.m_feed_from carrying
       "2026年06月25日 11:40 来自 网站"); the div.m_feed_detail.m_qa sibling — present
       only once the company has answered — carries the answer text and its own
       div.m_feed_from. A body under ~300 bytes is an empty feed, not a failure.

Store contract: APPEND-ONLY point-in-time from creation, dedup feed_id keep-LAST (an
answer landing days after the question CORRECTS the stored row); every row carries
fetched_at (UTC ISO, "last observed") AND first_seen ("first observed", carried through
every correction). Writes go through a tmp sibling + os.replace, and an
existing-but-unreadable store ABORTS the append instead of being replaced. Nothing ever
deletes or rewrites history. Each row's ``code`` is the code of the shard name we
QUERIED, never one parsed out of the question text (see parse_feed_items).

Politeness + budget: ≥1.0 s + jitter before EVERY request (single host, no parallelism)
and a ~100 s in-collector wall-clock guard that persists the cursor (or the map-build
page) at the TRUE stop position. A 0-row night is a success, never a crash; RuntimeError
is raised only when every leg failed at transport level.

SENTINEL NOTE: ``n_fetched`` counts PAGES on a map-build night (map_built=1) and ROWS on
every other night — the two nights do fundamentally different work, and map_built is the
column that says which one the ledger row describes.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger("china_einteraction")

# ------------------------------------------------------------------ constants --

GROUP = "china_einteraction"
_HOST = "https://sns.sseinfo.com"
_REFERER = "https://sns.sseinfo.com/"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_EP_ALLCOMPANY = _HOST + "/allcompany.do"
_EP_USERFEEDS = _HOST + "/ajax/userfeeds.do"

_SUFFIX = ".SS"
_SHARD_SIZE = 40
_FEED_PAGE_SIZE = 30
_MAP_PAGE_CAP = 90        # today's directory is ~72 pages; the cap is a runaway guard,
                          # deliberately NOT pinned to the observed page count
_MAP_MAX_AGE_DAYS = 30
_MIN_MAP_CODES = 500      # the live directory is ~2,312 codes; a "finished" crawl holding
                          # fewer than this is a parse failure, never a small venue
_EMPTY_FEED_BYTES = 300   # a shorter body is an empty feed, not a transport failure
_PACE_S = 1.0
_JITTER_S = 0.3
_TIMEOUT = (10, 20)
_BUDGET_S = 100.0

_QA_COLUMNS = (
    "feed_id",     # 上证e互动 item id — the natural PIT key
    "code",        # 6-digit SS code of the name we QUERIED (authoritative, not parsed)
    "name",
    "question",
    "answer",      # '' while unanswered
    "q_ts",        # ISO Asia/Shanghai
    "a_ts",
    "q_source",    # 来自 …  (网站 / 手机 / …)
    "a_source",
    "asker_uid",
    "fetched_at",  # LAST observation of this feed_id
    "first_seen",  # FIRST observation — never overwritten by a keep-LAST correction
)

_FROM_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})(?::(\d{2}))?")
_PREFIX_RE = re.compile(r"([^\s:：()（）]+)[（(](\d{6})[）)]")
_AVATAR_RE = re.compile(r"/(\d{6})\.png")


# ------------------------------------------------------------------ paths / sidecars --

def _dir() -> Path:
    p = config.data_dir() / GROUP
    p.mkdir(parents=True, exist_ok=True)
    return p


def _qa_path() -> Path:
    return _dir() / "qa.parquet"


def _uid_map_path() -> Path:
    return _dir() / "uid_map.json"


def _cursor_path() -> Path:
    return _dir() / "cursor.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except Exception:  # noqa: BLE001
        log.warning("china_einteraction: unreadable sidecar %s — starting fresh", path.name)
        return {}


def _save_json(path: Path, payload: dict) -> None:
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    except Exception as e:  # noqa: BLE001
        log.error("china_einteraction: could not write %s: %s", path.name, e)


# ------------------------------------------------------------------ store --

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
        log.error("china_einteraction: %s is present but UNREADABLE (%s)", path.name, e)
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
    time the company answers. Keys absent from ``existing`` keep tonight's stamp.
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


def load_qa() -> pd.DataFrame:
    """Existing qa.parquet, or an empty frame with the canonical schema.

    A present-but-unreadable store also reads as empty HERE — a reader must not
    crash — but write_qa() checks readability separately and aborts, so the empty
    frame can never be written back over the real one.
    """
    df = _read_store(_qa_path(), _QA_COLUMNS)
    return pd.DataFrame(columns=list(_QA_COLUMNS)) if df is None else df


def write_qa(rows: list[dict]) -> int:
    """Append feed rows, dedup feed_id keep-LAST. Returns net-new rows. Never raises.

    first_seen is carried through the merge, so an answer landing days later advances
    fetched_at without destroying the first-observation time. An existing-but-
    UNREADABLE qa.parquet ABORTS the append (returns 0, file left in place for manual
    recovery) rather than being replaced by tonight's shard.
    """
    if not rows:
        return 0
    try:
        existing = _read_store(_qa_path(), _QA_COLUMNS)
        if existing is None:
            log.error("china_einteraction: ABORTING the qa.parquet append — the accrued "
                      "store is unreadable and is left untouched for manual recovery")
            return 0
        new_df = pd.DataFrame(rows).reindex(columns=list(_QA_COLUMNS))
        new_df["first_seen"] = new_df["first_seen"].fillna(new_df["fetched_at"])
        if existing.empty:
            merged = new_df.drop_duplicates(subset=["feed_id"], keep="last")
            net_new = len(merged)
        else:
            pre = existing["feed_id"].nunique()
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["feed_id"], keep="last")
            merged = _restore_first_seen(merged, existing, ["feed_id"])
            net_new = merged["feed_id"].nunique() - pre
        merged = merged.sort_values(["q_ts", "feed_id"], na_position="last").reset_index(drop=True)
        _atomic_write(merged, _qa_path())
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("china_einteraction.write_qa failed: %s", e)
        return 0


# ------------------------------------------------------------------ universe + cursor --

def board_universe() -> list[str]:
    """Sorted 6-digit SS codes of the board universe (china_setups.json → buy).

    Read pattern per collectors/china_fundamentals.py:_high_value_universe. A
    missing/corrupt file is a LOUD empty universe (0-row night), never a crash.
    """
    path = config.site_dir() / "factordata" / "china_setups.json"
    if not path.exists():
        log.warning("china_einteraction: %s absent — empty universe, 0-row night", path)
        return []
    try:
        doc = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("china_einteraction: could not parse china_setups.json (%s)", e)
        return []
    codes = set()
    for r in (doc.get("buy") or []):
        t = r.get("ticker") if isinstance(r, dict) else None
        if t and t.endswith(_SUFFIX):
            head = t.split(".")[0]
            if len(head) == 6 and head.isdigit():
                codes.add(head)
    if not codes:
        log.warning("china_einteraction: no %s names in china_setups.json buy list", _SUFFIX)
    return sorted(codes)


def next_shard(order: list[str], pos: int, size: int) -> tuple[list[str], int]:
    """Tonight's shard + the position to persist after a full shard. Pure; wraps."""
    n = len(order)
    if n == 0:
        return [], 0
    pos = pos % n
    take = min(size, n)
    shard = [order[(pos + i) % n] for i in range(take)]
    return shard, (pos + take) % n


def load_cursor(order: list[str]) -> int:
    state = _load_json(_cursor_path())
    try:
        pos = int(state.get("pos", 0))
    except (TypeError, ValueError):
        pos = 0
    if state.get("order") != order:
        log.info("china_einteraction: universe changed (%d names) — the persisted order "
                 "is stale; clamping the position into tonight's order", len(order))
    return pos % len(order) if order else 0


def save_cursor(order: list[str], pos: int) -> None:
    _save_json(_cursor_path(), {
        "pos": int(pos) % len(order) if order else 0,
        "order": order,
        "updated": datetime.now(timezone.utc).isoformat(),
    })


# ------------------------------------------------------------------ pure parsers --

def parse_feed_from(text: str) -> tuple[str, str]:
    """'2026年06月25日 11:40 来自 网站' → ('2026-06-25T11:40:00+08:00', '网站'). Pure.

    Both halves degrade independently: an unparseable date yields '' (never a
    fabricated timestamp) and a missing 来自 clause yields '' for the source.
    """
    text = text or ""
    ts = ""
    m = _FROM_RE.search(text)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        ts = (f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
              f"T{int(hh):02d}:{mm}:{ss or '00'}+08:00")
    src = text.split("来自", 1)[1].strip() if "来自" in text else ""
    return ts, src


def parse_code_prefix(text: str) -> tuple[str, str]:
    """':浦发银行(600000)' → ('600000', '浦发银行'); ('', '') when absent. Pure."""
    m = _PREFIX_RE.search(text or "")
    return (m.group(2), m.group(1)) if m else ("", "")


def parse_company_page(fragment: str) -> dict[str, str]:
    """One /allcompany.do HTML fragment → {6-digit code: uid}. Pure.

    The uid lives on an UNQUOTED attribute of the <a rel='tag'> wrapper; the stock
    code is only available as the avatar image's filename stem. Entries missing
    either half are skipped (a directory row we cannot key is a coverage null).
    """
    from bs4 import BeautifulSoup  # noqa: PLC0415 — lazy, keeps import cost off the registry

    out: dict[str, str] = {}
    if not fragment:
        return out
    soup = BeautifulSoup(fragment, "lxml")
    for a in soup.select('a[rel="tag"]'):
        uid = a.get("uid")
        img = a.find("img")
        src = (img.get("src") if img else "") or ""
        m = _AVATAR_RE.search(str(src))
        if uid and m:
            out[m.group(1)] = str(uid)
    return out


def parse_feed_items(html_text: str, fetched_at: str,
                     code: str = "", name: str = "") -> list[dict]:
    """One /ajax/userfeeds.do HTML body → canonical qa.parquet rows. Pure.

    Traversal pinned against the captured live response: the FIRST div.m_feed_detail
    inside a div.m_feed_item[id^="item-"] is the question; the .m_qa sibling (present
    only once answered) is the answer. The question's div.m_feed_txt starts with an
    anchor carrying the "name(code)" prefix, which is stripped from the question body.

    ATTRIBUTION: ``code`` is the code of the shard name whose uid we queried, and it
    is AUTHORITATIVE for every row of that feed. The prefix parsed out of the question
    text is only a fallback for a bare-parser call: a question that merely MENTIONS
    another listco carries that other code in its text, and a question with no prefix
    at all carries none — both would mis-key the store, and the collector already
    knows exactly which company it asked for. ``name`` behaves the same way, but
    neither the uid map nor the board universe carries display names today, so it is
    normally left blank and the parsed prefix supplies the name.
    """
    from bs4 import BeautifulSoup  # noqa: PLC0415 — lazy

    rows: list[dict] = []
    if not html_text:
        return rows
    soup = BeautifulSoup(html_text, "lxml")
    for item in soup.select('div.m_feed_item[id^="item-"]'):
        feed_id = str(item.get("id") or "").split("item-", 1)[-1]
        if not feed_id:
            continue
        question_div = None
        answer_div = None
        for detail in item.select("div.m_feed_detail"):
            if "m_qa" in (detail.get("class") or []):
                if answer_div is None:
                    answer_div = detail
            elif question_div is None:
                question_div = detail
        if question_div is None:
            continue

        face = question_div.select_one("a[rel='face']")
        asker_uid = str(face.get("uid") or "") if face else ""

        txt = question_div.select_one("div.m_feed_txt")
        raw_q = txt.get_text(" ", strip=True) if txt else ""
        anchor = txt.select_one("a") if txt else None
        prefix = anchor.get_text(strip=True) if anchor else ""
        question = raw_q[len(prefix):].strip() if prefix and raw_q.startswith(prefix) else raw_q
        parsed_code, parsed_name = parse_code_prefix(prefix or raw_q)

        q_from = question_div.select_one("div.m_feed_from")
        q_ts, q_source = parse_feed_from(q_from.get_text(" ", strip=True) if q_from else "")

        answer, a_ts, a_source = "", "", ""
        if answer_div is not None:
            a_txt = answer_div.select_one("div.m_feed_txt")
            answer = a_txt.get_text(" ", strip=True) if a_txt else ""
            a_from = answer_div.select_one("div.m_feed_from")
            a_ts, a_source = parse_feed_from(a_from.get_text(" ", strip=True) if a_from else "")

        rows.append({
            "feed_id": feed_id,
            "code": code or parsed_code,
            "name": name or parsed_name,
            "question": question,
            "answer": answer,
            "q_ts": q_ts,
            "a_ts": a_ts,
            "q_source": q_source,
            "a_source": a_source,
            "asker_uid": asker_uid,
            "fetched_at": fetched_at,
        })
    return rows


# ------------------------------------------------------------------ HTTP --

def _headers() -> dict:
    return {
        "User-Agent": _UA,
        "Referer": _REFERER,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _pace() -> None:
    """Politeness sleep before EVERY request: ≥1.0 s to the single upstream host."""
    time.sleep(_PACE_S + random.uniform(0.0, _JITTER_S))  # noqa: S311


def _clock() -> float:
    """Monotonic seconds. Indirected so the wall-clock guard is unit-testable."""
    return time.monotonic()


def _post(session, url: str, data: dict | None = None):
    """Paced POST → the raw response. Raises on transport/HTTP failure."""
    _pace()
    r = session.post(url, data=data, headers=_headers(), timeout=_TIMEOUT)
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from {url.split('?')[0]}")
    r.raise_for_status()
    return r


def _fetch_company_page(session, page: int) -> dict[str, str]:
    """One directory page → {code: uid}. Empty dict ends the page loop."""
    r = _post(session, _EP_ALLCOMPANY,
              {"code": "0", "order": "2", "areaId": "0", "page": str(page)})
    try:
        fragment = (r.json() or {}).get("content") or ""
    except Exception:  # noqa: BLE001 — the vendor occasionally answers raw HTML
        fragment = r.text
    return parse_company_page(fragment)


def _fetch_feed(session, uid: str, fetched_at: str, code: str = "") -> tuple[list[dict], bool]:
    """One feed page for one uid → (rows, drift_flag).

    A sub-300-byte body is an EMPTY feed, not an error — the venue serves a stub for a
    company nobody has asked anything. A body ABOVE that floor that parses to ZERO
    items is the HTML-drift tripwire: the markup moved and the rows are silently gone,
    which looks identical to a quiet name from the outside. It is not fatal (one night
    of one name), so it is logged and returned as the drift flag, which refresh() folds
    into n_nulls instead of letting it read as silence.

    ``code`` is passed through as the row-level authoritative attribution (F9).
    """
    url = (f"{_EP_USERFEEDS}?typeCode=company&type=11&pageSize={_FEED_PAGE_SIZE}"
           f"&uid={uid}&page=1")
    r = _post(session, url)
    if len(r.text) < _EMPTY_FEED_BYTES:
        return [], False
    rows = parse_feed_items(r.text, fetched_at, code=code)
    if not rows:
        log.warning("china_einteraction: uid=%s (code=%s) served %d bytes but parsed 0 "
                    "feed items — HTML drift tripwire, counted as a coverage null",
                    uid, code or "?", len(r.text))
        return [], True
    return rows, False


# ------------------------------------------------------------------ uid map --

def _map_state() -> dict:
    state = _load_json(_uid_map_path())
    state.setdefault("map", {})
    state.setdefault("complete", False)
    state.setdefault("next_page", 1)
    state.setdefault("resolved_at", "")
    return state


def _age_days(iso: str) -> float | None:
    try:
        stamped = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamped).total_seconds() / 86400.0


def map_needs_build(state: dict, shard: list[str]) -> bool:
    """True when tonight must be a MAP-BUILD night (feeds skipped). Pure.

    An incomplete map always continues building. A complete map is only rebuilt when
    a shard name is missing from it AND the map is older than 30 days — otherwise the
    missing name is a logged coverage null, not a nightly full re-crawl.
    """
    if not state.get("complete"):
        return True
    missing = [c for c in shard if c not in (state.get("map") or {})]
    if not missing:
        return False
    age = _age_days(str(state.get("resolved_at") or ""))
    return age is None or age > _MAP_MAX_AGE_DAYS


def build_uid_map(session, state: dict, t0: float) -> dict:
    """Page the company directory into state['map']; RESUMABLE across nights.

    Stops on the first page yielding 0 pairs (natural end), the 90-page runaway cap,
    the wall-clock guard, or a transport failure. A truncated build records next_page
    and continues tomorrow, so a partial map is never mistaken for a finished one.

    COMPLETENESS GATE. An empty page is AMBIGUOUS — either the true end of the
    directory or a blank/shape-drifted response — and stamping complete on the wrong
    reading freezes whatever we hold as final for the whole 30-day age window (an
    empty map then means every name is a coverage null and no feed is ever pulled).
    So complete=True takes two independent confirmations:
      1. the map clears _MIN_MAP_CODES — the live directory is ~2,312 codes, so a
         "finished" crawl holding fewer than 500 is a parse failure; and
      2. this crawl actually parsed a non-empty page — UNLESS it was resuming a build
         already in progress (next_page > 1), where the pages were parsed on earlier
         nights and an immediate empty page IS the expected end marker.
    Anything else keeps complete=False, leaves next_page ON the unparseable page so
    tomorrow retries exactly it, and logs loudly.

    DURABILITY. Each page is fetched inside its own try/except: a transport failure
    mid-crawl PERSISTS everything fetched so far at the true page position and returns
    normally, so three flaky nights still make progress instead of restarting from
    scratch each time. Only a from-scratch crawl that cannot fetch its very first page
    raises — there is genuinely nothing to save, and the breaker should see it.
    """
    start_page = int(state.get("next_page") or 1)
    page = start_page
    mapping = dict(state.get("map") or {})
    added = 0
    pages = 0
    parsed_any = False
    ended = False
    while page <= _MAP_PAGE_CAP:
        if _clock() - t0 > _BUDGET_S:
            log.warning(
                "china_einteraction: %.0fs guard hit during map build at page %d "
                "(%d codes so far) — resuming there tomorrow",
                _BUDGET_S, page, len(mapping),
            )
            break
        try:
            pairs = _fetch_company_page(session, page)
        except Exception as e:  # noqa: BLE001 — per-page isolation
            if pages == 0 and not mapping:
                raise  # from-scratch crawl, nothing fetched, nothing to persist
            log.warning("china_einteraction: directory page %d failed (%s) — keeping the "
                        "%d codes fetched so far and resuming at that page tomorrow",
                        page, e, len(mapping))
            break
        pages += 1
        if not pairs:
            ended = True
            log.info("china_einteraction: directory ended at page %d", page)
            break
        parsed_any = True
        added += len({c for c in pairs if c not in mapping})
        mapping.update(pairs)
        page += 1
    else:
        ended = True
        log.warning("china_einteraction: directory hit the %d-page cap — raise the cap "
                    "if the venue grew", _MAP_PAGE_CAP)

    complete = bool(ended and len(mapping) >= _MIN_MAP_CODES
                    and (parsed_any or start_page > 1))
    if ended and not complete:
        log.error(
            "china_einteraction: directory crawl ended at page %d holding %d codes "
            "(parsed a page this crawl: %s, floor: %d) — NOT stamping the map complete. "
            "An empty or shape-drifted page would otherwise freeze this map as final "
            "for %d days and blank out every feed pull; retrying the same page tomorrow",
            page, len(mapping), parsed_any, _MIN_MAP_CODES, _MAP_MAX_AGE_DAYS,
        )

    state["map"] = mapping
    # A completed crawl restarts at 1; so does one that ran past the runaway cap, which
    # would otherwise leave next_page beyond the cap and never enter the loop again.
    state["next_page"] = 1 if (complete or page > _MAP_PAGE_CAP) else page
    state["complete"] = complete
    if complete:
        state["resolved_at"] = datetime.now(timezone.utc).isoformat()
    _save_json(_uid_map_path(), state)
    log.info("china_einteraction: map build pages=%d codes=%d (+%d new) complete=%s",
             pages, len(mapping), added, complete)
    state["_pages"] = pages
    return state


# ------------------------------------------------------------------ nightly refresh --

def refresh() -> dict:
    """Build the uid map or pull tonight's ≤40-name SS feed shard.

    A map-build night returns shard=0 / map_built=1 and writes no Q&A rows — that is
    a SUCCESS, not an empty day. On a normal night each name is isolated in its own
    try/except; a name missing from the map, or one whose feed body parsed to nothing,
    is counted in n_nulls. RuntimeError is raised only when every attempted name failed
    at transport level (or a from-scratch map build could not fetch its first page).

    Returns the sentinel counters the adapter writes to data/china_einteraction/refresh.parquet.
    """
    import requests  # lazy

    t0 = _clock()
    fetched_at = datetime.now(timezone.utc).isoformat()
    order = board_universe()
    if not order:
        log.warning("china_einteraction: empty SS universe — 0-row night")
        return {"n_new": 0, "n_fetched": 0, "n_failed": 0, "n_nulls": 0,
                "universe": 0, "shard": 0, "map_built": 0}

    start_pos = load_cursor(order)
    shard, next_pos = next_shard(order, start_pos, _SHARD_SIZE)
    state = _map_state()
    session = requests.Session()

    if map_needs_build(state, shard):
        log.info("china_einteraction: MAP-BUILD night (complete=%s, next_page=%s) — "
                 "feed pulls skipped tonight", state.get("complete"), state.get("next_page"))
        try:
            state = build_uid_map(session, state, t0)
        except Exception as e:  # noqa: BLE001 — nothing was salvageable; see build_uid_map
            raise RuntimeError(f"china_einteraction: uid-map build failed at transport level: {e}")
        # n_fetched counts PAGES on this night, not rows — map_built=1 says so.
        return {"n_new": 0, "n_fetched": int(state.get("_pages") or 0), "n_failed": 0,
                "n_nulls": 0, "universe": len(order), "shard": 0, "map_built": 1}

    mapping = state.get("map") or {}
    rows: list[dict] = []
    processed = 0
    attempted = 0
    n_failed = 0
    n_drift = 0
    missing: list[str] = []
    truncated = False

    for code in shard:
        if _clock() - t0 > _BUDGET_S:
            truncated = True
            log.warning(
                "china_einteraction: %.0fs wall-clock guard hit after %d/%d names — "
                "stopping mid-shard; cursor persists at the true stop position",
                _BUDGET_S, processed, len(shard),
            )
            break
        uid = str(mapping.get(code) or "")
        if not uid:
            missing.append(code)
            processed += 1
            continue
        try:
            attempted += 1
            # The SHARD's code is the authoritative attribution for every row of this
            # feed — never the code parsed out of the question text (F9).
            feed_rows, drift = _fetch_feed(session, uid, fetched_at, code)
            n_drift += int(drift)
            rows.extend(feed_rows)
        except Exception as e:  # noqa: BLE001 — per-name isolation
            n_failed += 1
            log.warning("china_einteraction: %s (uid=%s) failed: %s", code, uid, e)
        processed += 1

    save_cursor(order, (start_pos + processed) % len(order))
    if missing:
        log.warning("china_einteraction: %d coverage nulls (uid unknown): %s",
                    len(missing), ",".join(missing))
    if attempted > 0 and n_failed >= attempted:
        raise RuntimeError(
            f"china_einteraction: every attempted name failed at transport level "
            f"({n_failed}/{attempted})"
        )

    n_new = write_qa(rows)
    log.info(
        "china_einteraction: universe=%d shard=%d processed=%d failed=%d missing=%d "
        "drift=%d rows=%d net_new=%d%s (next_pos=%d)",
        len(order), len(shard), processed, n_failed, len(missing), n_drift, len(rows),
        n_new, " [TRUNCATED]" if truncated else "", next_pos,
    )
    # Coverage nulls: names with no uid in the map, plus feeds whose body arrived but
    # parsed to nothing. Both produce zero rows while looking exactly like a quiet name.
    return {"n_new": n_new, "n_fetched": len(rows), "n_failed": n_failed,
            "n_nulls": len(missing) + n_drift, "universe": len(order),
            "shard": len(shard), "map_built": 0}


# ------------------------------------------------------------------ adapter --

class ChinaEInteractionAdapter(Adapter):
    """上证e互动 investor-Q&A drip (W1 CNH) — context/input tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_einteraction`` starts with ``china`` so it is auto-assigned to the asia lane.

    fetch() returns a COVERAGE sentinel rather than a bare count, so
    data/china_einteraction/refresh.parquet is a readable run ledger: ``map_built``
    distinguishes a legitimate directory-build night from an empty shard night (and is
    also what says ``n_fetched`` counted PAGES rather than rows), and ``n_nulls`` counts
    the names that produced NO observation — uid missing from the map, or a feed body
    that parsed to nothing. What the sentinel does NOT prove is per-name coverage:
    universe/shard are the sizes ATTEMPTED, not a receipt that each name answered.
    """

    name = "china_einteraction"
    group = GROUP
    stale_after_days = 4

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        # tz-NAIVE normalized UTC day (collectors/china_filings.py precedent).
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        sentinel = pd.DataFrame(
            {k: [float(s[k])] for k in
             ("n_new", "n_fetched", "n_failed", "n_nulls", "universe", "shard",
              "map_built")},
            index=[idx],
        )
        sentinel.index.name = "collected_at"
        return {"refresh": sentinel}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    s = refresh()
    print(f"china_einteraction: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
