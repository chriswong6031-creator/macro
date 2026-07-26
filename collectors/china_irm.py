"""互动易 (SZSE investor-interaction platform) Q&A collector — CONTEXT ONLY (W1 CNH).

深交所互动易 is the mandatory disclosure channel where retail investors ask a listed
company a question and the 董秘 (board secretary) answers ON THE RECORD. Two planes
are collected, both keyless and both machine-fields-only:

  qa.parquet        per-name question/answer tape for the SZ half of the board
                    universe (site/factordata/china_setups.json → buy, *.SZ), pulled
                    as a ≤40-names/night SHARD with a persisted cursor — a full
                    per-name sweep does not fit one collect step (masterplan §W1
                    "IRM budget arithmetic").
  velocity.parquet  ONE market-wide observation per collection day: the total
                    question count the platform's search index reports plus the
                    newest publish timestamp on page 1. The RAW observation is
                    stored, never a delta — an ES total wobbles, and a stored delta
                    would bake one night's wobble into history forever.

CONTEXT / INPUT TIER ONLY. Nothing here is scored, ranked, promoted, or surfaced on
site/; the 互动易 legs register as tier="pending" in engine/china_signal_lab.py
(collected + accruing). Q&A text is stored as an input plane for downstream context
work, not as a display surface.

VERIFIED ENDPOINTS (live 2026-07-25, this runner):
  POST /newircs/index/queryKeyboardInfo?_t=…   form {"keyWord": "<6-digit code>"}
       → {"data": [{"stockCode","shortName","secid",…}]}; secid ("gssz0000001") is
         the orgId the Q&A endpoint needs. Resolved ONCE per name, cached in org_ids.json.
  POST /newircs/company/question?_t=…&stockcode=…&orgId=…&pageSize=100&pageNum=1
       &keyWord=&startDay=&endDay=            ALL params in the QUERY STRING, empty body
       → {"total", "totalPage", "rows": [...]}. ONE page per name per night — pageSize
         100 covers any realistic nightly delta and the indexId dedup absorbs overlap.
  POST /newircs/index/search?_t=…             form {"pageNo","pageSize","searchTypes","keyWord"}
       → {"totalRecord": 94789, "results": [...]} — the market-wide velocity read.

Store contract: APPEND-ONLY point-in-time from creation. qa.parquet dedups on
indexId keep-LAST (a same-day re-pull that now carries the company's answer CORRECTS
the row); velocity.parquet dedups on date keep-LAST. Nothing ever deletes or rewrites
history; every row carries fetched_at (UTC ISO).

Politeness + budget: ≥1.0 s + jitter before EVERY request (single host, no parallelism)
and a ~100 s in-collector wall-clock guard. When the guard fires mid-shard the cursor is
persisted at the TRUE stop position, so tomorrow resumes exactly where tonight stopped.
A 0-row night is a success (n_new=0), never a crash; RuntimeError is raised only when
every leg failed at transport level, which is what the circuit breaker should see.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
# ONE epoch-ms → Asia/Shanghai ISO convention across the China collectors.
from collectors.china_filings import _unix_ms_to_iso
from lib import config

log = logging.getLogger("china_irm")

# ------------------------------------------------------------------ constants --

GROUP = "china_irm"
_HOST = "https://irm.cninfo.com.cn"
_REFERER = "https://irm.cninfo.com.cn/"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_EP_KEYBOARD = _HOST + "/newircs/index/queryKeyboardInfo?_t=1691144074"
_EP_QUESTION = _HOST + "/newircs/company/question"
_EP_SEARCH = _HOST + "/newircs/index/search?_t=1691142650"

_SUFFIX = ".SZ"        # 互动易 is the SHENZHEN interaction venue; SS names go to china_einteraction
_SHARD_SIZE = 40       # names per night (masterplan §W1 budget arithmetic)
_PAGE_SIZE = 100       # one page per name per night
_PACE_S = 1.0          # ≥1 req/s/host, jittered
_JITTER_S = 0.3
_TIMEOUT = (10, 20)    # (connect, read)
_BUDGET_S = 100.0      # in-collector wall-clock guard; there is NO harness-level timeout

_QA_COLUMNS = (
    "index_id",     # 互动易 indexId — the natural PIT key
    "code",         # 6-digit SZ code
    "name",
    "question",     # mainContent
    "answer",       # attachedContent ('' while unanswered)
    "answered",
    "qa_status",    # raw qaStatus, stored as text (vendor mixes "0" and 2)
    "q_ts",         # ISO Asia/Shanghai
    "a_ts",         # ISO Asia/Shanghai; '' when the vendor leaves attachedPubDate null
    "update_ts",
    "industry",     # trade[0]
    "source",       # raw pubClient
    "fetched_at",
)
_VELOCITY_COLUMNS = ("date", "total_record", "max_pub_ts_page1", "asof")


# ------------------------------------------------------------------ paths / sidecars --

def _dir() -> Path:
    p = config.data_dir() / GROUP
    p.mkdir(parents=True, exist_ok=True)
    return p


def _qa_path() -> Path:
    return _dir() / "qa.parquet"


def _velocity_path() -> Path:
    return _dir() / "velocity.parquet"


def _org_ids_path() -> Path:
    return _dir() / "org_ids.json"


def _cursor_path() -> Path:
    return _dir() / "cursor.json"


def _load_json(path: Path) -> dict:
    """Read a sidecar JSON, or {} when absent/corrupt (never raises)."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()) or {}
    except Exception:  # noqa: BLE001
        log.warning("china_irm: unreadable sidecar %s — starting fresh", path.name)
        return {}


def _save_json(path: Path, payload: dict) -> None:
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    except Exception as e:  # noqa: BLE001 — a sidecar write must never sink the night
        log.error("china_irm: could not write %s: %s", path.name, e)


# ------------------------------------------------------------------ stores --

def load_qa() -> pd.DataFrame:
    """Existing qa.parquet, or an empty frame with the canonical schema."""
    path = _qa_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_QA_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_irm: could not read qa.parquet: %s", e)
    return pd.DataFrame(columns=list(_QA_COLUMNS))


def write_qa(rows: list[dict]) -> int:
    """Append Q&A rows, dedup index_id keep-LAST. Returns net-new rows.

    Keep-LAST is deliberate: 互动易 answers land days after the question, so a
    re-pull of the same indexId carrying attachedContent must CORRECT the stored
    row rather than be discarded. Never raises — a store failure is logged.
    """
    if not rows:
        return 0
    try:
        new_df = pd.DataFrame(rows).reindex(columns=list(_QA_COLUMNS))
        existing = load_qa()
        if existing.empty:
            merged = new_df.drop_duplicates(subset=["index_id"], keep="last")
            net_new = len(merged)
        else:
            pre = existing["index_id"].nunique()
            merged = pd.concat([existing, new_df], ignore_index=True)
            merged = merged.drop_duplicates(subset=["index_id"], keep="last")
            net_new = merged["index_id"].nunique() - pre
        merged = merged.sort_values(["q_ts", "index_id"], na_position="last").reset_index(drop=True)
        merged.to_parquet(_qa_path(), index=False)
        return int(net_new)
    except Exception as e:  # noqa: BLE001
        log.error("china_irm.write_qa failed: %s", e)
        return 0


def load_velocity() -> pd.DataFrame:
    path = _velocity_path()
    if path.exists():
        try:
            return pd.read_parquet(path).reindex(columns=list(_VELOCITY_COLUMNS))
        except Exception as e:  # noqa: BLE001
            log.warning("china_irm: could not read velocity.parquet: %s", e)
    return pd.DataFrame(columns=list(_VELOCITY_COLUMNS))


def write_velocity(row: dict | None) -> int:
    """Append one market-wide velocity observation, dedup date keep-LAST.

    ``None`` (the endpoint answered but carried no totalRecord) writes NOTHING —
    the gap is logged by the caller, never zero-filled.
    """
    if not row:
        return 0
    try:
        new_df = pd.DataFrame([row]).reindex(columns=list(_VELOCITY_COLUMNS))
        existing = load_velocity()
        merged = new_df if existing.empty else pd.concat([existing, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"], keep="last")
        merged = merged.sort_values("date").reset_index(drop=True)
        merged.to_parquet(_velocity_path(), index=False)
        return 1
    except Exception as e:  # noqa: BLE001
        log.error("china_irm.write_velocity failed: %s", e)
        return 0


# ------------------------------------------------------------------ universe + cursor --

def board_universe() -> list[str]:
    """Sorted 6-digit SZ codes of the board universe (china_setups.json → buy).

    Read pattern per collectors/china_fundamentals.py:_high_value_universe — the
    names actually surfaced on the China board. A missing/corrupt file is a LOUD
    empty universe (0-row night), never a crash.
    """
    path = config.site_dir() / "factordata" / "china_setups.json"
    if not path.exists():
        log.warning("china_irm: %s absent — empty universe, 0-row night", path)
        return []
    try:
        doc = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("china_irm: could not parse china_setups.json (%s) — empty universe", e)
        return []
    codes = set()
    for r in (doc.get("buy") or []):
        t = r.get("ticker") if isinstance(r, dict) else None
        if t and t.endswith(_SUFFIX):
            head = t.split(".")[0]
            if len(head) == 6 and head.isdigit():
                codes.add(head)
    if not codes:
        log.warning("china_irm: no %s names in china_setups.json buy list", _SUFFIX)
    return sorted(codes)


def next_shard(order: list[str], pos: int, size: int) -> tuple[list[str], int]:
    """Tonight's shard plus the position to persist AFTER a full shard. Pure.

    Wraps around the end of ``order``: with 50 names, pos=40 and size=40 the shard
    is order[40:50] + order[0:30] and the next position is 30.
    """
    n = len(order)
    if n == 0:
        return [], 0
    pos = pos % n
    take = min(size, n)
    shard = [order[(pos + i) % n] for i in range(take)]
    return shard, (pos + take) % n


def load_cursor(order: list[str]) -> int:
    """Persisted position, clamped into ``order``.

    A universe that changed size (names enter/leave the board) rebuilds the order
    and clamps the position rather than dropping the rotation to zero.
    """
    state = _load_json(_cursor_path())
    try:
        pos = int(state.get("pos", 0))
    except (TypeError, ValueError):
        pos = 0
    if state.get("order") != order:
        log.info("china_irm: universe changed (%d names) — rebuilding cursor order",
                 len(order))
    return pos % len(order) if order else 0


def save_cursor(order: list[str], pos: int) -> None:
    _save_json(_cursor_path(), {
        "pos": int(pos) % len(order) if order else 0,
        "order": order,
        "updated": datetime.now(timezone.utc).isoformat(),
    })


# ------------------------------------------------------------------ pure parsers --

def pick_org_id(payload: dict, code: str) -> str:
    """secid of the entry whose stockCode == ``code``; '' when no match. Pure.

    queryKeyboardInfo is a fuzzy keyboard search: '000001' also returns 000001 的
    neighbours, so the exact-code match is mandatory (a fuzzy first-hit would pin
    the wrong company's Q&A tape forever).
    """
    for row in ((payload or {}).get("data") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("stockCode") or "").strip() == str(code).strip():
            return str(row.get("secid") or "")
    return ""


def _text(value) -> str:
    """None-safe text: keeps a literal 0 (the vendor mixes "0" and 0 in qaStatus)."""
    return "" if value is None else str(value)


def parse_question_row(raw: dict, fetched_at: str) -> dict:
    """One /company/question row → one canonical qa.parquet row. Pure (no I/O)."""
    answer = _text(raw.get("attachedContent")).strip()
    trade = raw.get("trade")
    industry = str(trade[0]) if isinstance(trade, list) and trade else ""
    return {
        "index_id": _text(raw.get("indexId")),
        "code": _text(raw.get("stockCode")),
        "name": _text(raw.get("companyShortName")),
        "question": _text(raw.get("mainContent")),
        "answer": answer,
        "answered": bool(answer),
        "qa_status": _text(raw.get("qaStatus")),
        "q_ts": _unix_ms_to_iso(raw.get("pubDate")),
        "a_ts": _unix_ms_to_iso(raw.get("attachedPubDate")),
        "update_ts": _unix_ms_to_iso(raw.get("updateDate")),
        "industry": industry,
        "source": _text(raw.get("pubClient")),
        "fetched_at": fetched_at,
    }


def parse_velocity(payload: dict, fetched_at: str) -> dict | None:
    """/index/search page-1 envelope → one velocity row, or None when unusable.

    None means "the endpoint answered but carried no totalRecord" — the caller logs
    the gap and writes nothing. A fabricated 0 would read as "nobody asked anything
    today", which is a very different claim from "we did not observe the total".
    """
    total = (payload or {}).get("totalRecord")
    try:
        total_record = int(total)
    except (TypeError, ValueError):
        return None
    pub_ts = [
        _unix_ms_to_iso(r.get("pubDate"))
        for r in ((payload or {}).get("results") or [])
        if isinstance(r, dict)
    ]
    return {
        "date": fetched_at[:10],
        "total_record": total_record,
        "max_pub_ts_page1": max([t for t in pub_ts if t], default=""),
        "asof": fetched_at,
    }


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


def _post_json(session, url: str, data: dict | None = None) -> dict:
    """Paced POST → parsed JSON. Raises on transport/HTTP/JSON failure."""
    _pace()
    r = session.post(url, data=data, headers=_headers(), timeout=_TIMEOUT)
    if r.status_code in (429, 500, 502, 503, 504):
        raise IOError(f"HTTP {r.status_code} from {url.split('?')[0]}")
    r.raise_for_status()
    return r.json()


def _resolve_org_id(session, code: str) -> str:
    """One queryKeyboardInfo call → secid for ``code`` ('' when unmatched)."""
    payload = _post_json(session, _EP_KEYBOARD, {"keyWord": code})
    return pick_org_id(payload, code)


def _fetch_questions(session, code: str, org_id: str) -> list[dict]:
    """One /company/question page for one name. ALL params in the query string."""
    url = (f"{_EP_QUESTION}?_t=1691142650&stockcode={code}&orgId={org_id}"
           f"&pageSize={_PAGE_SIZE}&pageNum=1&keyWord=&startDay=&endDay=")
    payload = _post_json(session, url)
    return [r for r in (payload.get("rows") or []) if isinstance(r, dict)]


def _fetch_velocity(session) -> dict:
    return _post_json(session, _EP_SEARCH, {
        "pageNo": "1", "pageSize": "3", "searchTypes": "1,11", "keyWord": "",
    })


# ------------------------------------------------------------------ nightly refresh --

def refresh() -> dict:
    """Pull tonight's 互动易 shard + the market-wide velocity observation.

    Flow: load the SZ board universe → take the cursor's ≤40-name shard → per name
    resolve the org-id once (cached) and pull one Q&A page → append → one velocity
    call → persist the cursor at the TRUE stop position.

    Per-name try/except isolation: one dead name never sinks the night, and a name
    whose org-id will not resolve is logged as a coverage null and skipped. Raises
    RuntimeError ONLY when every attempted name AND the velocity call failed at
    transport level — the honest circuit-breaker signal.

    Returns the sentinel counters the adapter turns into data/china_irm/refresh.parquet.
    """
    import requests  # lazy — keeps import-time cost off the collect registry

    t0 = _clock()
    fetched_at = datetime.now(timezone.utc).isoformat()
    order = board_universe()
    if not order:
        log.warning("china_irm: empty SZ universe — 0-row night (nothing to fetch)")
        return {"n_new": 0, "n_fetched": 0, "n_failed": 0, "universe": 0, "shard": 0}

    start_pos = load_cursor(order)
    shard, _ = next_shard(order, start_pos, _SHARD_SIZE)
    org_ids = _load_json(_org_ids_path())
    session = requests.Session()

    rows: list[dict] = []
    processed = 0
    n_failed = 0
    unresolved: list[str] = []
    truncated = False

    for code in shard:
        if _clock() - t0 > _BUDGET_S:
            truncated = True
            log.warning(
                "china_irm: %.0fs wall-clock guard hit after %d/%d names — stopping "
                "mid-shard; cursor persists at the true stop position",
                _BUDGET_S, processed, len(shard),
            )
            break
        try:
            org_id = str(org_ids.get(code) or "")
            if not org_id:
                org_id = _resolve_org_id(session, code)
                if org_id:
                    org_ids[code] = org_id
                else:
                    unresolved.append(code)
                    processed += 1
                    continue
            rows.extend(parse_question_row(r, fetched_at)
                        for r in _fetch_questions(session, code, org_id))
        except Exception as e:  # noqa: BLE001 — per-name isolation
            n_failed += 1
            log.warning("china_irm: %s failed: %s", code, e)
        processed += 1

    _save_json(_org_ids_path(), org_ids)
    save_cursor(order, (start_pos + processed) % len(order))
    if unresolved:
        log.warning("china_irm: %d coverage nulls (org-id unresolved): %s",
                    len(unresolved), ",".join(unresolved))

    # One cheap market-wide call, independent of the shard outcome.
    velocity_ok = False
    velocity_row = None
    try:
        velocity_row = parse_velocity(_fetch_velocity(session), fetched_at)
        velocity_ok = True
        if velocity_row is None:
            log.warning("china_irm: velocity endpoint answered without totalRecord — "
                        "gap logged, nothing written (never zero-filled)")
    except Exception as e:  # noqa: BLE001
        log.warning("china_irm: velocity call failed: %s", e)

    attempted = processed - len(unresolved)
    if attempted > 0 and n_failed >= attempted and not velocity_ok:
        raise RuntimeError(
            f"china_irm: every leg failed at transport level "
            f"({n_failed}/{attempted} names + velocity)"
        )

    n_new = write_qa(rows)
    write_velocity(velocity_row)
    log.info(
        "china_irm: universe=%d shard=%d processed=%d failed=%d unresolved=%d "
        "rows=%d net_new=%d velocity=%s%s",
        len(order), len(shard), processed, n_failed, len(unresolved), len(rows),
        n_new, "ok" if velocity_ok else "MISSING", " [TRUNCATED]" if truncated else "",
    )
    return {
        "n_new": n_new,
        "n_fetched": len(rows),
        "n_failed": n_failed,
        "universe": len(order),
        "shard": len(shard),
    }


# ------------------------------------------------------------------ adapter --

class ChinaIrmAdapter(Adapter):
    """互动易 investor-Q&A drip (W1 CNH) — context/input tier, never scored.

    Wraps refresh() in the standard run_adapter / circuit-breaker machinery. Group
    ``china_irm`` starts with ``china`` so it is auto-assigned to the asia lane
    (scripts/collect.py group_members). fetch() returns a COVERAGE sentinel — not a
    bare count — so data/china_irm/refresh.parquet is a readable run ledger
    (vacuous-green law: a count alone cannot distinguish "nothing new" from
    "nothing fetched").
    """

    name = "china_irm"
    group = GROUP
    stale_after_days = 4

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        s = refresh()
        # tz-NAIVE normalized UTC day (collectors/china_filings.py precedent): mixing a
        # tz-aware index into a tz-naive parquet makes store.upsert's combine_first raise.
        idx = pd.Timestamp.now("UTC").normalize().tz_localize(None)
        sentinel = pd.DataFrame(
            {k: [float(s[k])] for k in ("n_new", "n_fetched", "n_failed", "universe", "shard")},
            index=[idx],
        )
        sentinel.index.name = "collected_at"
        return {"refresh": sentinel}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    s = refresh()
    print(f"china_irm: {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
