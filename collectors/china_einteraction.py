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

CONTEXT / INPUT TIER ONLY: nothing here is scored, ranked, promoted, or surfaced on
site/; the leg registers as tier="pending" in engine/china_signal_lab.py (collected +
accruing). Q&A text is stored as an input plane, not a display surface.

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
fetched_at (UTC ISO). Nothing ever deletes or rewrites history.

Politeness + budget: ≥1.0 s + jitter before EVERY request (single host, no parallelism)
and a ~100 s in-collector wall-clock guard that persists the cursor (or the map-build
page) at the TRUE stop position. A 0-row night is a success, never a crash; RuntimeError
is raised only when every leg failed at transport level.
"""
from __future__ import annotations

import argparse
import json
import logging
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
_EMPTY_FEED_BYTES = 300   # a shorter body is an empty feed, not a transport failure
_PACE_S = 1.0
_JITTER_S = 0.3
_TIMEOUT = (10, 20)
_BUDGET_S = 100.0

_QA_COLUMNS = (
    "feed_id",     # 上证e互动 item id — the natural PIT key
    "code",        # 6-digit SS code, parsed from the question's name(code) prefix
    "name",
    "question",
    "answer",      # '' while unanswered
    "q_ts",        # ISO Asia/Shanghai
    "a_ts",
    "q_source",    # 来自 …  (网站 / 手机 / …)
    "a_source",
    "asker_uid",
    "fetched_at",
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

def load_qa() -> pd.DataFrame:
    path = _qa_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_QA_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_einteraction: could not read qa.parquet: %s", e)
    return pd.DataFrame(columns=list(_QA_COLUMNS))


def write_qa(rows: list[dict]) -> int:
    """Append feed rows, dedup feed_id keep-LAST. Returns net-new rows. Never raises."""
    if not rows:
        return 0
    try:
        new_df = pd.DataFrame(rows).reindex(columns=list(_QA_COLUMNS))
        existing = load_qa()
        if existing.empty:
            merged = new_df.drop_duplicates(subset=["feed_id"], keep="last")
            net_new = len(merged)
        else:
            pre = existing["feed_id"].nunique()
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["feed_id"], keep="last")
            net_new = merged["feed_id"].nunique() - pre
        merged = merged.sort_values(["q_ts", "feed_id"], na_position="last").reset_index(drop=True)
        merged.to_parquet(_qa_path(), index=False)
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
        log.info("china_einteraction: universe changed (%d names) — rebuilding cursor order",
                 len(order))
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


def parse_feed_items(html_text: str, fetched_at: str) -> list[dict]:
    """One /ajax/userfeeds.do HTML body → canonical qa.parquet rows. Pure.

    Traversal pinned against the captured live response: the FIRST div.m_feed_detail
    inside a div.m_feed_item[id^="item-"] is the question; the .m_qa sibling (present
    only once answered) is the answer. The question's div.m_feed_txt starts with an
    anchor carrying the "name(code)" prefix, which is stripped from the question body
    and parsed into code/name.
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
        code, name = parse_code_prefix(prefix or raw_q)

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
            "code": code,
            "name": name,
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


def _fetch_feed(session, uid: str, fetched_at: str) -> list[dict]:
    """One feed page for one uid. A sub-300-byte body is an EMPTY feed, not an error."""
    url = (f"{_EP_USERFEEDS}?typeCode=company&type=11&pageSize={_FEED_PAGE_SIZE}"
           f"&uid={uid}&page=1")
    r = _post(session, url)
    if len(r.text) < _EMPTY_FEED_BYTES:
        return []
    return parse_feed_items(r.text, fetched_at)


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
    or the wall-clock guard. Only a natural end stamps complete/resolved_at — a
    truncated build records next_page and continues tomorrow, so a partial map is
    never mistaken for a finished one.
    """
    page = int(state.get("next_page") or 1)
    mapping = dict(state.get("map") or {})
    added = 0
    pages = 0
    complete = False
    while page <= _MAP_PAGE_CAP:
        if _clock() - t0 > _BUDGET_S:
            log.warning(
                "china_einteraction: %.0fs guard hit during map build at page %d "
                "(%d codes so far) — resuming there tomorrow",
                _BUDGET_S, page, len(mapping),
            )
            break
        pairs = _fetch_company_page(session, page)
        pages += 1
        if not pairs:
            complete = True
            log.info("china_einteraction: directory ended at page %d", page)
            break
        added += len({c for c in pairs if c not in mapping})
        mapping.update(pairs)
        page += 1
    else:
        complete = True
        log.warning("china_einteraction: directory hit the %d-page cap — treating the "
                    "map as complete; raise the cap if the venue grew", _MAP_PAGE_CAP)

    state["map"] = mapping
    state["next_page"] = 1 if complete else page
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
    try/except; a name missing from the map is a logged coverage null. RuntimeError
    is raised only when every attempted name failed at transport level.

    Returns the sentinel counters the adapter writes to data/china_einteraction/refresh.parquet.
    """
    import requests  # lazy

    t0 = _clock()
    fetched_at = datetime.now(timezone.utc).isoformat()
    order = board_universe()
    if not order:
        log.warning("china_einteraction: empty SS universe — 0-row night")
        return {"n_new": 0, "n_fetched": 0, "n_failed": 0, "universe": 0,
                "shard": 0, "map_built": 0}

    start_pos = load_cursor(order)
    shard, next_pos = next_shard(order, start_pos, _SHARD_SIZE)
    state = _map_state()
    session = requests.Session()

    if map_needs_build(state, shard):
        log.info("china_einteraction: MAP-BUILD night (complete=%s, next_page=%s) — "
                 "feed pulls skipped tonight", state.get("complete"), state.get("next_page"))
        try:
            state = build_uid_map(session, state, t0)
        except Exception as e:  # noqa: BLE001 — the only leg tonight
            raise RuntimeError(f"china_einteraction: uid-map build failed at transport level: {e}")
        return {"n_new": 0, "n_fetched": int(state.get("_pages") or 0), "n_failed": 0,
                "universe": len(order), "shard": 0, "map_built": 1}

    mapping = state.get("map") or {}
    rows: list[dict] = []
    processed = 0
    attempted = 0
    n_failed = 0
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
            rows.extend(_fetch_feed(session, uid, fetched_at))
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
        "rows=%d net_new=%d%s (next_pos=%d)",
        len(order), len(shard), processed, n_failed, len(missing), len(rows), n_new,
        " [TRUNCATED]" if truncated else "", next_pos,
    )
    return {"n_new": n_new, "n_fetched": len(rows), "n_failed": n_failed,
            "universe": len(order), "shard": len(shard), "map_built": 0}


# ------------------------------------------------------------------ adapter --

class ChinaEInteractionAdapter(Adapter):
    """上证e互动 investor-Q&A drip (W1 CNH) — context/input tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_einteraction`` starts with ``china`` so it is auto-assigned to the asia
    lane. fetch() returns a COVERAGE sentinel — not a bare count — so
    data/china_einteraction/refresh.parquet is a readable run ledger; ``map_built``
    distinguishes a legitimate directory-build night from an empty shard night.
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
             ("n_new", "n_fetched", "n_failed", "universe", "shard", "map_built")},
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
