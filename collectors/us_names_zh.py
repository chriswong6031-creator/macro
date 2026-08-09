"""US Chinese-name enricher — fetches ticker→中文名 for the US universe.

WHY
---
The global nav search merges all five market libraries into one universe and
matches a query against ticker, English name and Chinese name.  China and Hong
Kong emit a Chinese name (`z`) per row; the US library did not, so a Chinese
query could never reach a US name: 苹果 / 英伟达 / 特斯拉 returned "No ticker or
company matches this search." against 2,930 indexed US names.  This collector
resolves the Chinese names and persists ``config/us_names_zh.json`` so
``scripts/build_stock_library.py`` can wire `z` into every search row — the same
shape ``collectors/hk_names_zh.py`` already provides for Hong Kong.

SOURCE STRATEGY
---------------
Preferred: Sina's US quote list (``US_CategoryService.getList``) — the same
endpoint akshare's ``stock_us_spot`` wraps, carrying a ``cname`` field with the
Chinese company name.  No API key.  Called directly rather than through akshare
because the convenience readers here carry no timeout, and a hung nightly
collector is worse than a missing one.

Fallback: the committed ``config/us_names_zh.json``, which always provides a
usable baseline.

TICKER FORM
-----------
Our US universe uses the Yahoo class-share form (``BRK-B``); Sina uses the dotted
form (``BRK.B``).  Both are indexed, and lookups fall back across the two.

FAIL-OPEN
---------
A failed or partial enrichment degrades to whatever is already in the JSON.
``load_names_zh()`` always returns a dict (possibly empty), so a missing name →
the row simply carries no `z` and stays searchable by ticker and English name.

RUN
---
  python -m collectors.us_names_zh --refresh     # re-fetch + persist
  python -m collectors.us_names_zh               # report what is committed
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

_CONFIG_JSON = Path(__file__).resolve().parent.parent / "config" / "us_names_zh.json"
_ALIAS_JSON = Path(__file__).resolve().parent.parent / "config" / "us_search_aliases_zh.json"

_WIKIDATA_URL = "https://query.wikidata.org/sparql"
# NYSE (Q13677) + NASDAQ (Q82059) listings carrying a ticker qualifier (P249).
# Simplified variants first — a Traditional-only label is still a fine SEARCH key
# but must never become the displayed name, which is why it lands in the alias file.
_WIKIDATA_QUERY = """
SELECT ?ticker ?lang ?label WHERE {
  ?co p:P414 ?st .
  ?st ps:P414 ?ex ; pq:P249 ?ticker .
  VALUES ?ex { wd:Q13677 wd:Q82059 }
  ?co rdfs:label ?label .
  BIND(LANG(?label) AS ?lang)
  FILTER(?lang IN ("zh-cn","zh-hans","zh-sg","zh"))
}
"""
_WIKIDATA_LANG_RANK = {"zh-cn": 0, "zh-hans": 1, "zh-sg": 2, "zh": 3}

_SINA_URL = (
    "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/"
    "IO.XSRV2.CallbackList['x']/US_CategoryService.getList"
)
_SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://finance.sina.com.cn/",
}
_PAGE_SIZE = 20        # Sina caps a page at 20 rows regardless of `num`
_MAX_PAGES = 1000      # ~18k listed US names; the loop exits on the reported count
_HAS_CJK = re.compile(r"[㐀-鿿]")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _load_map(path: Path, label: str) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except FileNotFoundError:
        log.warning("us_names_zh: %s not found — %s will be None", path.name, label)
        return {}
    except Exception as e:  # noqa: BLE001
        log.warning("us_names_zh: failed to load %s (%s) — %s will be None", path.name, e, label)
        return {}


def load_names_zh() -> dict[str, str]:
    """Return ticker → DISPLAYED Chinese name dict.

    Reads ``config/us_names_zh.json`` (committed + enriched by this collector).
    Always returns a dict; empty when the file is missing / corrupt.

    Usage::

        from collectors.us_names_zh import load_names_zh, lookup
        _NAMES_ZH = load_names_zh()
        name_zh = lookup(_NAMES_ZH, ticker)   # None if not in map
    """
    return _load_map(_CONFIG_JSON, "name_zh")


def load_aliases_zh() -> dict[str, str]:
    """Return ticker → SEARCH-ONLY Chinese alias dict.

    Broader but noisier than :func:`load_names_zh` (Wikidata labels: mixed
    Simplified/Traditional, occasionally a former company name). Good enough to
    make a Chinese query FIND the name, not good enough to be the name we show —
    the builder emits it as `za`, which theme.js matches and never renders.
    """
    return _load_map(_ALIAS_JSON, "search alias")


def lookup(names: dict[str, str], ticker: str) -> str | None:
    """Chinese name for `ticker`, bridging the Yahoo/Sina class-share forms.

    ``BRK-B`` (ours) and ``BRK.B`` (Sina) are the same instrument; a map built
    from either source must answer for both.
    """
    if not ticker:
        return None
    t = str(ticker).strip().upper()
    return names.get(t) or names.get(t.replace("-", ".")) or names.get(t.replace(".", "-"))


# ---------------------------------------------------------------------------
# Live fetch
# ---------------------------------------------------------------------------

def _fetch_sina_names(max_pages: int = _MAX_PAGES) -> dict[str, str]:
    """Walk Sina's US quote list and return ticker → Chinese name.

    Ordered by market cap descending, so a partial walk (network flakiness, an
    early cap) still resolves the names anyone is realistically searching for.
    Returns {} on any failure — never raises.
    """
    try:
        import requests
    except ImportError:  # pragma: no cover — requests is a hard dep here
        log.warning("us_names_zh: requests unavailable — skip live fetch")
        return {}

    out: dict[str, str] = {}
    session = requests.Session()
    session.headers.update(_SINA_HEADERS)
    page, fails, total = 1, 0, None
    while page <= max_pages:
        try:
            r = session.get(
                _SINA_URL,
                params={"page": page, "num": _PAGE_SIZE, "sort": "mktcap", "asc": 0,
                        "market": "", "id": ""},
                timeout=25,
            )
            body = r.text
            start, end = body.find("("), body.rfind(")")
            if start < 0 or end <= start:
                raise ValueError("unparseable JSONP envelope")
            payload = json.loads(body[start + 1:end])
        except Exception as e:  # noqa: BLE001 — one flaky page must not end the walk
            fails += 1
            if fails > 60:
                log.warning("us_names_zh: giving up after %d failed pages (%s)", fails, e)
                break
            time.sleep(0.6)
            continue
        total = total or int(payload.get("count") or 0)
        rows = payload.get("data") or []
        if not rows:
            break
        for row in rows:
            symbol = str(row.get("symbol") or "").strip().upper()
            cname = str(row.get("cname") or "").strip()
            # Sina echoes the English name into `cname` for names it has never
            # translated. Only a genuinely Chinese string helps a Chinese query.
            if symbol and cname and _HAS_CJK.search(cname):
                out[symbol] = cname
        if total and page * _PAGE_SIZE >= total:
            break
        page += 1
    log.info("us_names_zh: Sina returned %d Chinese names over %d pages (%d retries)",
             len(out), page, fails)
    return out


def _fetch_wikidata_aliases() -> dict[str, str]:
    """Wikidata zh labels for NYSE/NASDAQ tickers. Returns {} on any failure."""
    try:
        import requests
    except ImportError:  # pragma: no cover
        return {}
    try:
        r = requests.get(
            _WIKIDATA_URL,
            params={"query": _WIKIDATA_QUERY, "format": "json"},
            headers={"User-Agent": "MacroDashboard/1.0 (US ticker Chinese search aliases)"},
            timeout=180,
        )
        r.raise_for_status()
        rows = r.json()["results"]["bindings"]
    except Exception as e:  # noqa: BLE001 — the committed alias file is the fallback
        log.warning("us_names_zh: Wikidata alias fetch failed (%s)", e)
        return {}
    best: dict[str, tuple[int, str]] = {}
    for row in rows:
        ticker = str(row["ticker"]["value"]).strip().upper()
        label = str(row["label"]["value"]).strip()
        if not ticker or not label or not _HAS_CJK.search(label):
            continue
        rank = _WIKIDATA_LANG_RANK.get(row["lang"]["value"], 9)
        if ticker not in best or rank < best[ticker][0]:
            best[ticker] = (rank, label)
    log.info("us_names_zh: Wikidata returned %d Chinese aliases", len(best))
    return {t: v for t, (_, v) in best.items()}


def enrich_and_persist(tickers: list[str] | None = None,
                       max_pages: int = _MAX_PAGES) -> dict[str, str]:
    """Fetch live names from Sina and merge into config/us_names_zh.json.

    Best-effort: the committed JSON is always the authoritative fallback, so a
    failed live fetch is not fatal and never shrinks the map.

    Parameters
    ----------
    tickers:
        Optional list to restrict the *live* additions to (e.g. the current
        universe).  Committed entries are never dropped.

    Returns the final (merged) ticker → name dict that was persisted.
    """
    existing = load_names_zh()
    live = _fetch_sina_names(max_pages=max_pages)

    def _restrict(m: dict[str, str]) -> dict[str, str]:
        if not tickers:
            return m
        keep: set[str] = set()
        for t in tickers:
            t = str(t).strip().upper()
            keep.update({t, t.replace("-", "."), t.replace(".", "-")})
        return {t: v for t, v in m.items() if t in keep}

    def _persist(path: Path, merged: dict[str, str], default_comment: str) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:  # noqa: BLE001
            raw = {}
        out = {"_comment": raw.get("_comment", default_comment)}
        out.update(dict(sorted(merged.items())))
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    if live:
        merged = {**existing, **_restrict(live)}
        _persist(_CONFIG_JSON, merged, "US universe Chinese company names (Sina cname).")
        log.info("us_names_zh: persisted %d names to config/us_names_zh.json", len(merged))
    else:
        merged = existing
        log.info("us_names_zh: no live update — using %d committed names", len(existing))

    # Search-only aliases are a SEPARATE tier: they widen recall without ever
    # touching the displayed name, so a name already carrying a curated `z` is
    # dropped from the alias map rather than shadowing it.
    live_alias = _fetch_wikidata_aliases()
    if live_alias:
        alias = {**load_aliases_zh(), **_restrict(live_alias)}
        alias = {t: v for t, v in alias.items() if not lookup(merged, t)}
        _persist(_ALIAS_JSON, alias,
                 "US search-only Chinese aliases (Wikidata zh labels). Never displayed.")
        log.info("us_names_zh: persisted %d search aliases to config/us_search_aliases_zh.json",
                 len(alias))

    return merged


# ---------------------------------------------------------------------------
# Standalone / test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-fetch from Sina and persist")
    ap.add_argument("--max-pages", type=int, default=_MAX_PAGES)
    args = ap.parse_args()

    names = enrich_and_persist(max_pages=args.max_pages) if args.refresh else load_names_zh()
    aliases = load_aliases_zh()
    print(f"{len(names)} displayed names + {len(aliases)} search-only aliases")
    for tk in ("AAPL", "NVDA", "TSLA", "MSFT", "BRK-B", "SPY", "META", "CBRE"):
        got = lookup(names, tk) or (lookup(aliases, tk) and f"{lookup(aliases, tk)} (alias)")
        print(f"  {tk}: {got or 'MISSING'}")
