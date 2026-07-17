"""同花顺 (Tonghuashun / 10jqka) concept-board (概念板块) membership fetcher.

THS curates ~370 thematic "concept boards" (concepts like 白酒/baijiu, 人形机器人/humanoid
robots, 固态电池/solid-state battery …) and the A-share members of each. This module pulls the
theme→members map straight from q.10jqka.com.cn so the China thematic-baskets desk can mirror
THS's themes and constituents (see scripts/seed_china_ths_baskets.py).

WHY THIS EXISTS (akshare can't do it any more): akshare exposes the THS concept *names*
(`stock_board_concept_name_ths`) but its members function (`stock_board_concept_cons_ths`) was
removed. The member table is still served on the plain detail page; this module pages through it.

ACCESS NOTES (verified from a non-China datacentre IP, 2026-06):
  • Theme list — akshare `stock_board_concept_name_ths()` (cached to disk here; ~370 names+codes).
  • Members  — page `https://q.10jqka.com.cn/gn/detail/order/desc/page/{N}/ajax/1/code/{code}/`
               (10 rows/page). The `/field/199112/` URL variant 403s from outside China; the
               clean variant above returns 200. An anti-scrape `v` cookie (generated from THS's
               own ths.js via py_mini_racer, exactly as akshare does) is required.
  • Fragile  — rapid sequential requests draw SSL drops / 403s, so every fetch retries with
               backoff and paces between pages; a failed theme is skipped (logged), never fatal.

Output: a dated raw snapshot data/baskets_china_ths/snapshots/<YYYY-MM-DD>.json
        ({theme_name: [{"ticker": "600519.SS", "name": "贵州茅台"}, …]}, full membership incl.
        names outside our price universe — the seed step filters). Re-runnable; the seed step
        accumulates point-in-time `added`/`removed` history by diffing snapshots over time.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from io import StringIO

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

from lib import config

try:  # urllib3 ships with requests; Retry import path is stable
    from urllib3.util.retry import Retry
except Exception:  # noqa: BLE001 — extremely unlikely; degrade to no-retry adapter
    Retry = None  # type: ignore

log = logging.getLogger(__name__)


class ThsTruncated(RuntimeError):
    """A concept's member table could not be fully paged (throttle / SSL drop / partial page).

    Raised instead of returning a PARTIAL member list: a truncated fetch is indistinguishable from
    a genuinely-shorter board, and recording it as authoritative makes the seed step manufacture
    spurious `removed` events on the next diff (which silently breaks the THS baskets page). The
    caller (`snapshot`) treats this like a throttle — the theme is left unresolved and retried on a
    later resume run — so only COMPLETE member lists ever land in a snapshot.
    """


_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36")
_DATA = config.data_dir() / "baskets_china_ths"
_MAP_CACHE = _DATA / "concept_map.json"        # {"asof": iso-date, "map": {name: code}} (refreshed if asof older than _MAP_TTL_DAYS)
_MAP_TTL_DAYS = 7
_PAGE_PAUSE = 1.2                               # seconds between member pages (politeness / SSL stability)
_THEME_PAUSE = 4.0                              # seconds between themes (THS IP-throttles bursts hard)
_MAX_PAGES = 60                                 # hard ceiling (~600 members) — no real concept is bigger
_MAX_CONSEC_EMPTY = 4                           # consecutive empty themes ⇒ assume IP cool-down, stop & resume later


def _new_v() -> str:
    """Generate a FRESH THS anti-scrape `v` cookie from its own ths.js (same recipe akshare uses).

    Deliberately NOT cached: THS throttles bursts that reuse one cookie, so we mint a new one per
    theme. Generation is a sub-second py_mini_racer eval.
    """
    import py_mini_racer
    from akshare.datasets import get_ths_js

    js = py_mini_racer.MiniRacer()
    js.eval(open(get_ths_js("ths.js"), encoding="utf-8").read())
    return js.call("v")


def _session(v: str | None = None) -> requests.Session:
    """A fresh session bound to a (fresh) `v` cookie. New session per theme ⇒ new TCP, new cookie."""
    s = requests.Session()
    if Retry is not None:
        retry = Retry(total=3, backoff_factor=2.0, status_forcelist=[403, 429, 500, 502, 503, 504],
                      allowed_methods=["GET"])
        s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": _UA, "Referer": "https://q.10jqka.com.cn/",
                      "Cookie": f"v={v or _new_v()}"})
    return s


def to_suffixed(code6: str) -> str:
    """Bare 6-digit A-share code -> store ticker with exchange suffix (.SS/.SZ/.BJ).

    Shanghai (.SS): 6xxxxx main/STAR, 900xxx B-shares. Beijing Stock Exchange (.BJ): 8xxxxx,
    4xxxxx, 920xxx. Shenzhen (.SZ): everything else (000/002/003 main, 300 ChiNext, 200 B-shares).
    Beijing names are virtually never in our top-mktcap price cache, so they fall out at the seed
    step's universe filter anyway — but we still label them correctly.
    """
    code6 = str(code6).zfill(6)
    if code6[0] == "6" or code6.startswith("900"):
        return f"{code6}.SS"
    if code6[0] in ("8", "4") or code6.startswith("92"):
        return f"{code6}.BJ"
    return f"{code6}.SZ"


def _read_map_cache() -> tuple[dict[str, str] | None, int | None]:
    """(map, age_days) from the disk cache. Freshness is judged from the blob's
    embedded `asof` stamp, NEVER file mtime — on CI runners a checkout rewrites
    files with mtime = checkout time, so the committed cache always looked
    brand-new by mtime and the refetch short-circuited forever (the
    polygon-universe frozen-cache class, #2690; this map froze at its
    2026-06-27 fill the same way). Legacy stamp-less blobs ({name: code} flat
    dict) return age None — usable as a failure fallback but never fresh."""
    try:
        blob = json.loads(_MAP_CACHE.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("concept_map cache unreadable (%s)", e)
        return None, None
    if isinstance(blob, dict) and isinstance(blob.get("map"), dict):
        try:
            age = (date.today() - date.fromisoformat(str(blob.get("asof")))).days
        except Exception:  # noqa: BLE001
            age = None
        return {str(k): str(v) for k, v in blob["map"].items()}, age
    if isinstance(blob, dict):        # legacy flat {name: code} — stamp-less ⇒ stale
        return {str(k): str(v) for k, v in blob.items()}, None
    return None, None


def concept_code_map(force: bool = False) -> dict[str, str]:
    """{concept_name: ths_code} for every THS concept board (~370). Disk-cached for _MAP_TTL_DAYS.

    Uses akshare's working name endpoint; on failure falls back to a stale cache if present.
    """
    cached: dict[str, str] | None = None
    if _MAP_CACHE.exists():
        cached, age_days = _read_map_cache()
        if (not force and cached
                and age_days is not None and age_days < _MAP_TTL_DAYS):
            return cached
    try:
        import akshare as ak
        df = ak.stock_board_concept_name_ths()
        m = {str(r["name"]): str(r["code"]) for _, r in df.iterrows()}
        if m:
            _DATA.mkdir(parents=True, exist_ok=True)
            _MAP_CACHE.write_text(json.dumps(
                {"asof": date.today().isoformat(), "map": m}, ensure_ascii=False, indent=0))
            log.info("refreshed THS concept map: %d concepts", len(m))
            return m
    except Exception as e:  # noqa: BLE001
        log.error("THS concept-name fetch failed: %s", e)
    if cached:  # better stale than nothing
        log.warning("using STALE THS concept map")
        return cached
    return {}


def concept_members(code: str, session: requests.Session | None = None) -> list[dict]:
    """All members of one THS concept board -> [{"ticker": "600519.SS", "name": "贵州茅台"}, …].

    Pages the detail table until a natural end (a short/empty last page, or no table past the last
    page). COMPLETE-OR-FAIL: any mid-pagination failure — a non-200, a retry-exhausted fetch, a
    missing/interstitial table on a page that should have one, or hitting the `_MAX_PAGES` ceiling
    without a natural end — raises `ThsTruncated` rather than returning the partial rows collected
    so far. Returning a truncated list would let the seed step read it as a genuine board shrink and
    fabricate `removed` events (see ThsTruncated). An empty board (page 1 has no rows) returns [].
    """
    s = session or _session()
    out: list[dict] = []
    seen: set[str] = set()
    for pg in range(1, _MAX_PAGES + 1):
        url = f"https://q.10jqka.com.cn/gn/detail/order/desc/page/{pg}/ajax/1/code/{code}/"
        # THS invalidates the anti-scrape `v` cookie partway through a deep board (a 401 mid-
        # pagination), which the adapter's Retry doesn't cover. Mint a FRESH cookie+session and
        # retry the page once before giving up — this pushes past the mid-board 401 to the real
        # end instead of truncating wherever the first 401 lands.
        r = None
        for attempt in range(2):
            try:
                r = s.get(url, timeout=25)
            except Exception as e:  # noqa: BLE001 — Retry exhausted (SSL drop etc.)
                if attempt == 0:
                    s = _session(); time.sleep(1.5); continue
                raise ThsTruncated(f"{code} page {pg} fetch failed: {e}") from e
            if r.status_code == 200:
                break
            if attempt == 0:                          # anti-scrape block → fresh cookie, retry once
                s = _session(); time.sleep(1.5); continue
            raise ThsTruncated(f"{code} page {pg} → HTTP {r.status_code}")
        try:
            tbl = pd.read_html(StringIO(r.text))[0]
        except ValueError:
            if pg == 1:  # page 1 with no table = throttle/interstitial, NOT an empty board
                raise ThsTruncated(f"{code} page 1 returned no table (throttle/interstitial)")
            break  # no table past the last page → natural end
        cols = {str(c) for c in tbl.columns}
        if "代码" not in cols or "名称" not in cols:
            if pg == 1:
                raise ThsTruncated(f"{code} page 1 had unexpected columns {sorted(cols)[:6]}")
            break  # a trailing non-member table → natural end
        if tbl.empty:
            break  # empty page → natural end
        for _, row in tbl.iterrows():
            t = to_suffixed(str(row["代码"]).split(".")[0])
            if t in seen:
                continue
            seen.add(t)
            out.append({"ticker": t, "name": str(row["名称"]).strip()})
        if len(tbl) < 10:
            break  # last (short) page → natural end
        time.sleep(_PAGE_PAUSE)
    else:  # loop ran all _MAX_PAGES without a natural end → suspiciously large / still paging
        raise ThsTruncated(f"{code} exceeded _MAX_PAGES={_MAX_PAGES} with no end page")
    return out


def snapshot(theme_names: list[str], as_of: str | None = None,
             resume: bool = True) -> dict:
    """Fetch members for the given THS concept names and write a dated raw snapshot — RESUMABLE.

    THS IP-throttles bursts, so a single run rarely fetches every theme: this saves progress after
    each success and, on `_MAX_CONSEC_EMPTY` consecutive empty themes (the throttle signature),
    stops early so a later run can pick up where it left off. With `resume=True` (default) it loads
    today's existing snapshot and skips themes already resolved — so running it a few times across
    cool-downs accumulates full coverage. Each theme uses a fresh session + fresh `v` cookie.

    Returns {theme_name: [{ticker,name}, …]} for every theme resolved so far (this run + prior).
    """
    code_map = concept_code_map()
    if not code_map:
        log.error("no THS concept map — cannot snapshot")
        return {}

    as_of = as_of or date.today().isoformat()
    snap_dir = _DATA / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_p = snap_dir / f"{as_of}.json"

    result: dict[str, list[dict]] = {}
    if resume and snap_p.exists():
        try:
            result = json.loads(snap_p.read_text())
            log.info("resuming today's snapshot — %d themes already resolved", len(result))
        except Exception as e:  # noqa: BLE001
            log.warning("existing snapshot unreadable (%s) — starting fresh", e)

    todo = [n for n in theme_names if n not in result or not result.get(n)]
    consec_empty = 0
    for name in todo:
        code = code_map.get(name)
        if not code:
            log.warning("THS concept name not found (renamed/retired?): %s", name)
            continue
        try:
            members = concept_members(code, _session())   # fresh cookie+session per theme
        except ThsTruncated as e:
            # partial/throttled fetch — do NOT record it (would fabricate `removed` events on the
            # next seed diff). Leave the theme unresolved so a later resume run retries it.
            consec_empty += 1
            log.warning("THS concept '%s' (%s) incomplete: %s (%d/%d consecutive)",
                        name, code, e, consec_empty, _MAX_CONSEC_EMPTY)
            if consec_empty >= _MAX_CONSEC_EMPTY:
                log.error("THS appears to be throttling this IP — stopping; re-run to resume "
                          "(%d/%d themes resolved so far)", len(result), len(theme_names))
                break
            time.sleep(_THEME_PAUSE * 2)              # back off harder after a truncated fetch
            continue
        if not members:
            consec_empty += 1
            log.warning("THS concept '%s' (%s) returned no members (%d/%d consecutive)",
                        name, code, consec_empty, _MAX_CONSEC_EMPTY)
            if consec_empty >= _MAX_CONSEC_EMPTY:
                log.error("THS appears to be throttling this IP — stopping; re-run to resume "
                          "(%d/%d themes resolved so far)", len(result), len(theme_names))
                break
            time.sleep(_THEME_PAUSE * 2)              # back off harder after an empty
            continue
        consec_empty = 0
        result[name] = members
        snap_p.write_text(json.dumps(result, ensure_ascii=False, indent=0))   # persist progress
        log.info("THS concept '%s' (%s): %d members  [%d/%d resolved]",
                 name, code, len(members), len(result), len(theme_names))
        time.sleep(_THEME_PAUSE)

    snap_p.write_text(json.dumps(result, ensure_ascii=False, indent=0))
    log.info("THS snapshot %s — %d/%d themes resolved", as_of, len(result), len(theme_names))
    return result


def main() -> int:
    """Resumably fetch today's snapshot for the curated THS themes (scripts.seed_china_ths_baskets).

    Safe to run repeatedly: each run skips themes already resolved today and stops early if THS
    starts throttling, so a handful of runs across cool-downs fill in full coverage.

    Usage: python -m collectors.china_ths_concepts
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from scripts.seed_china_ths_baskets import CURATED
    names = [row[1] for row in CURATED]
    res = snapshot(names, resume=True)
    return 0 if res else 1


if __name__ == "__main__":
    raise SystemExit(main())
