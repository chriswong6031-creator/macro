"""White House announcement feed — the primary-source policy monitor.

Polls the White House's own keyless WordPress RSS feeds (the `/news/feed/`
aggregate plus the `presidential-actions` and `fact-sheets` sections) and
normalises every item into a stable record carrying the FULL announcement body
(`content:encoded`), so the downstream brain reasons over the real text — not a
one-line excerpt.

It also owns the DEDUPE STATE (`data/whitehouse/processed.json`): a record of
which announcements have already been evaluated, so the (paid) Opus brain is only
ever asked about a genuinely NEW White House post. The hourly sentinel calls
`new_items()` → empty list ⇒ nothing changed ⇒ no commit, no LLM call.

Keyless · cached-free (the sentinel wants fresh) · degrade-NEVER-raise. Nothing
here is a scoring input; it feeds the display-only alert desk.
"""
from __future__ import annotations

import concurrent.futures as cf
import html as _html
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "macro-dashboard/1.0 (+research; whitehouse-monitor)")
_TIMEOUT = 15
_MAX_WORKERS = 4

# The White House publishes a free, keyless RSS feed per section (WordPress
# `/feed/`). `/news/feed/` is the AGGREGATE — it already carries presidential
# actions, fact sheets, statements and releases — but the two section feeds are
# polled too so a post that is slow to reach the aggregate is never missed
# (dedupe by guid collapses the overlap). Each item includes <content:encoded>
# with the full body.
FEEDS: list[tuple[str, str]] = [
    ("https://www.whitehouse.gov/news/feed/", "news"),
    ("https://www.whitehouse.gov/presidential-actions/feed/", "presidential-actions"),
    ("https://www.whitehouse.gov/fact-sheets/feed/", "fact-sheets"),
]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"


# --------------------------------------------------------------------------- #
# fetch + parse
# --------------------------------------------------------------------------- #
def _fetch(url: str) -> bytes | None:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.debug("whitehouse fetch failed %s (%s)", url, e)
        return None


def _to_iso(pubdate: str) -> str:
    if not pubdate:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            # WH publishes in Eastern Time; a bare (naive) pubDate should be
            # treated as ET, not UTC.  Assuming UTC introduced up to a +5h
            # recency error (EST) when the WH omits the timezone offset.
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("America/New_York"))
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def _clean(text: str | None) -> str:
    """Strip HTML tags, decode entities, collapse whitespace (titles / excerpts)."""
    if not text:
        return ""
    return _WS_RE.sub(" ", _html.unescape(_TAG_RE.sub(" ", text))).strip()


def _body_text(html: str | None, limit: int = 12000) -> str:
    """Reduce a content:encoded HTML body to clean paragraph text the LLM can read.
    Block tags become newlines so structure survives; remaining tags are stripped and
    HTML entities decoded. Bounded so one huge proclamation can't blow the prompt."""
    if not html:
        return ""
    t = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|table|ul|ol|blockquote)>", "\n", html)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = _html.unescape(_TAG_RE.sub(" ", t))   # stdlib decodes named + numeric entities
    lines = [_WS_RE.sub(" ", ln).strip() for ln in t.split("\n")]
    return "\n".join(ln for ln in lines if ln)[:limit]


def _child(item, *names):
    for ch in item:
        if ch.tag.split("}")[-1] in names:
            return ch
    return None


def _slug_id(url: str, published: str) -> str:
    """Stable, URL-safe id: <YYYY-MM-DD>-<last-path-segment>. The WH permalink's
    final slug is unique and human-readable; the date prefix keeps the ledger sorted."""
    try:
        seg = [p for p in urlparse(url).path.split("/") if p]
        slug = seg[-1] if seg else "item"
    except Exception:  # noqa: BLE001
        slug = "item"
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:80] or "item"
    day = (published or "")[:10] or "undated"
    return f"wh-{day}-{slug}"


def _parse(raw: bytes, section: str) -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log.debug("whitehouse parse error (%s)", e)
        return out
    for it in root.findall(".//item"):
        title_el = _child(it, "title")
        title = _clean(title_el.text if title_el is not None else "")
        link_el = _child(it, "link")
        url = (link_el.text or link_el.get("href", "")) if link_el is not None else ""
        guid_el = _child(it, "guid")
        guid = (guid_el.text or "").strip() if guid_el is not None else ""
        date_el = _child(it, "pubDate", "updated", "published", "date")
        published = _to_iso(date_el.text if date_el is not None else "")
        desc_el = _child(it, "description")
        excerpt = _clean(desc_el.text if desc_el is not None else "")
        # full body — content:encoded (namespaced) is the real article text
        ce = it.find(_CONTENT_NS)
        body = _body_text(ce.text if ce is not None else None) or excerpt
        cats = [_clean(c.text) for c in it.findall("category") if _clean(c.text)]
        if not title or not url:
            continue
        out.append({
            "id": _slug_id(url, published),
            "guid": guid or url,
            "title": title,
            "url": url,
            "published": published,
            "excerpt": excerpt[:400],
            "body": body,
            "section": section,
            "categories": cats[:8],
        })
    return out


# --------------------------------------------------------------------------- #
# collect + dedupe
# --------------------------------------------------------------------------- #
def collect(max_age_days: float = 4.0) -> list[dict]:
    """All current White House items across the polled feeds, deduped by guid and
    filtered to the recent window (a sentinel must never resurface a week-old post).
    Sorted newest-first. Never raises."""
    def _pull(url, section):
        return _parse(_fetch(url) or b"", section)

    items: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for res in ex.map(lambda f: _pull(*f), FEEDS):
            items.extend(res)

    # dedupe by guid; the aggregate + section feeds overlap heavily
    seen: set[str] = set()
    uniq: list[dict] = []
    for it in items:
        if it["guid"] in seen:
            continue
        seen.add(it["guid"])
        uniq.append(it)

    uniq = _recent(uniq, max_age_days)
    uniq.sort(key=lambda x: x.get("published", ""), reverse=True)
    return uniq


def _recent(items: list[dict], max_age_days: float) -> list[dict]:
    if not max_age_days:
        return items
    now = datetime.now(timezone.utc)
    out = []
    for it in items:
        p = it.get("published", "")
        try:
            dt = datetime.fromisoformat(p) if p else None
        except (TypeError, ValueError):
            dt = None
        if dt is None or (now - dt).total_seconds() <= max_age_days * 86400:
            out.append(it)
    return out


# --------------------------------------------------------------------------- #
# dedupe state — which announcements were already evaluated by the brain
# --------------------------------------------------------------------------- #
def _state_path(root: Path) -> Path:
    return Path(root) / "data" / "whitehouse" / "processed.json"


def load_processed(root: Path) -> dict:
    """{'seen': {guid: {at, id, activated, importance}}}. Missing/corrupt -> empty."""
    p = _state_path(root)
    try:
        d = json.loads(p.read_text())
        if isinstance(d, dict) and isinstance(d.get("seen"), dict):
            return d
    except Exception:  # noqa: BLE001
        pass
    return {"seen": {}}


def save_processed(root: Path, state: dict) -> None:
    p = _state_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2, default=str))
    except Exception as e:  # noqa: BLE001 — never fatal
        log.warning("whitehouse: processed.json write failed (%s)", e)


def mark_seen(state: dict, item: dict, *, activated: bool, importance: int | None) -> None:
    state.setdefault("seen", {})[item["guid"]] = {
        "id": item["id"],
        "at": datetime.now(timezone.utc).isoformat(),
        "activated": bool(activated),
        "importance": importance,
    }


def new_items(items: list[dict], state: dict) -> list[dict]:
    """Items whose guid has not been evaluated before — the brain's worklist."""
    seen = (state or {}).get("seen", {})
    return [it for it in items if it.get("guid") not in seen]
