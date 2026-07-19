"""engine.marketing.breaking_feed — Breaking-news ingestion adapter seam.

Enforces:
- Zero network calls at import time or in tests (all network lives in poll_source /
  poll_all, guarded by root/session_state so tests pass only fixture text to
  parse_feed).
- Zero writes outside <root>/data/marketing/breaking/ (local-only ledger law).
- Atomic file writes (tmp + os.replace — house law).
- Seen-ledger deduplication and ETag/Last-Modified conditional GET.
- Per-source politeness floor (min interval between polls, from config).

Public API:
    parse_feed(xml_or_json_text, source_cfg) -> list[FeedItem]
    poll_source(source_cfg, *, root, session_state) -> list[FeedItem]
    poll_all(root, cfg) -> list[FeedItem]   # new-only items

FeedItem dict (schema contract — never deviate; parallel card-renderer depends on it):
    id            str   stable sha1 of source_key + (guid or url)
    source        str   adapter key, e.g. "fed_press"
    source_name   str   display name, e.g. "Federal Reserve"
    source_tier   str   "official" | "wire" | "aggregator"
    url           str
    published_at  str   ISO8601 UTC
    headline      str
    body_snippet  str   plain text, first ~600 chars, HTML tags stripped
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict
from urllib.request import Request, urlopen

# ─────────────────────────────────────────────────────────────────────────────
# Public type alias
# ─────────────────────────────────────────────────────────────────────────────

class FeedItem(TypedDict):
    id: str
    source: str
    source_name: str
    source_tier: str
    url: str
    published_at: str
    headline: str
    body_snippet: str


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_SNIPPET_MAX = 600       # max chars in body_snippet
_SEEN_CAP = 5000         # max entries in seen.json (keep newest N)
_DEFAULT_INTERVAL = 300  # seconds between polls per source
_DEFAULT_UA = "MastermindBreakingBot/1.0 (+https://mastermind-x.com)"
_FEED_TIMEOUT = 10       # urllib timeout in seconds
_MAX_FEED_BYTES = 10 * 1024 * 1024  # per-fetch cap — a hostile/broken feed must not OOM the poller

# Strip HTML tags (including script/style content)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</(script|style)>", re.IGNORECASE | re.DOTALL
)
# Collapse whitespace
_WS_RE = re.compile(r"\s+")


# ─────────────────────────────────────────────────────────────────────────────
# HTML/text helpers (pure, no network)
# ─────────────────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Remove HTML/XML tags and unescape entities; collapse whitespace."""
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _snippet(text: str) -> str:
    """Return plain-text snippet capped at _SNIPPET_MAX chars."""
    s = _strip_html(text)
    return s[:_SNIPPET_MAX]


def _make_id(source_key: str, guid_or_url: str) -> str:
    """Stable sha1 id from source_key + identifier."""
    raw = f"{source_key}|{guid_or_url}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_pub_date(raw: str) -> str:
    """Parse RSS pubDate or Atom <updated>/<published> → ISO8601 UTC str.

    Falls back to current UTC if unparseable.
    """
    if not raw:
        return datetime.now(tz=timezone.utc).isoformat()
    raw = raw.strip()
    # Try common RSS formats
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S +0000",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    # Try ISO8601 (Atom)
    try:
        # Replace Z suffix with +00:00
        clean = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    return datetime.now(tz=timezone.utc).isoformat()


def _elem_text(elem: Any) -> str:
    """Safe text extraction from xml.etree.ElementTree element."""
    if elem is None:
        return ""
    return (elem.text or "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# Core parser — pure function (no network, used in tests)
# ─────────────────────────────────────────────────────────────────────────────

def parse_feed(xml_or_json_text: str, source_cfg: dict) -> list[FeedItem]:
    """Parse RSS 2.0, Atom, or JSON feed text into a list of FeedItems.

    Pure function — no network, no filesystem. Tested directly via fixtures.

    Args:
        xml_or_json_text: raw feed content as a string
        source_cfg: dict with keys: key, kind, url, source_name, tier

    Returns:
        list of FeedItem dicts (may be empty on parse error; never raises)
    """
    source_key = source_cfg.get("key", "unknown")
    source_name = source_cfg.get("source_name", source_key)
    source_tier = source_cfg.get("tier", "aggregator")
    kind = source_cfg.get("kind", "rss")

    try:
        if kind == "json":
            return _parse_json_feed(xml_or_json_text, source_key, source_name, source_tier)
        else:
            return _parse_xml_feed(xml_or_json_text, source_key, source_name, source_tier)
    except Exception as exc:  # noqa: BLE001
        print(f"[breaking_feed] parse_feed error ({source_key}): {exc}", file=sys.stderr)
        return []


def _parse_xml_feed(
    text: str, source_key: str, source_name: str, source_tier: str
) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom XML."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415

    root = ET.fromstring(text)

    # Detect Atom vs RSS
    ns = ""
    tag = root.tag
    if "}" in tag:
        ns = tag.split("}")[0][1:]

    atom_ns = "{http://www.w3.org/2005/Atom}"
    # If root tag contains Atom namespace, treat as Atom
    if "w3.org/2005/Atom" in (root.tag + " " + (root.get("xmlns", ""))):
        return _parse_atom(root, source_key, source_name, source_tier, atom_ns)

    # Check for atom:feed child or <feed> element
    if root.tag == f"{atom_ns}feed" or root.tag == "feed":
        return _parse_atom(root, source_key, source_name, source_tier, atom_ns)

    # RSS 2.0: look for <channel><item>
    channel = root.find("channel")
    if channel is None:
        # Try root as channel
        channel = root
    items = channel.findall("item")
    results: list[FeedItem] = []
    for item in items:
        title = _elem_text(item.find("title"))
        link = _elem_text(item.find("link"))
        guid_el = item.find("guid")
        guid = _elem_text(guid_el) if guid_el is not None else link
        pub_el = item.find("pubDate")
        pub_raw = _elem_text(pub_el) if pub_el is not None else ""
        desc_el = item.find("description")
        desc_raw = _elem_text(desc_el) if desc_el is not None else ""
        # Also check content:encoded
        content_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
        if content_el is not None and content_el.text:
            desc_raw = desc_raw + " " + (content_el.text or "")

        if not title and not link:
            continue

        item_id = _make_id(source_key, guid or link)
        results.append(FeedItem(
            id=item_id,
            source=source_key,
            source_name=source_name,
            source_tier=source_tier,
            url=link or guid or "",
            published_at=_parse_pub_date(pub_raw),
            headline=_strip_html(title),
            body_snippet=_snippet(desc_raw),
        ))
    return results


def _parse_atom(
    root: Any, source_key: str, source_name: str, source_tier: str, ns: str
) -> list[FeedItem]:
    """Parse Atom feed (root already an ElementTree Element)."""
    entries = root.findall(f"{ns}entry")
    results: list[FeedItem] = []
    for entry in entries:
        title_el = entry.find(f"{ns}title")
        title = _elem_text(title_el) if title_el is not None else ""

        # Link: prefer rel=alternate or first href
        link = ""
        for link_el in entry.findall(f"{ns}link"):
            rel = link_el.get("rel", "alternate")
            href = link_el.get("href", "")
            if rel == "alternate" and href:
                link = href
                break
            if href and not link:
                link = href

        id_el = entry.find(f"{ns}id")
        entry_id_raw = _elem_text(id_el) if id_el is not None else link

        updated_el = entry.find(f"{ns}updated")
        published_el = entry.find(f"{ns}published")
        pub_raw = _elem_text(updated_el if updated_el is not None else published_el)

        summary_el = entry.find(f"{ns}summary")
        content_el = entry.find(f"{ns}content")
        desc_raw = (
            _elem_text(content_el or summary_el)
            if (content_el is not None or summary_el is not None)
            else ""
        )

        if not title and not link:
            continue

        item_id = _make_id(source_key, entry_id_raw or link)
        results.append(FeedItem(
            id=item_id,
            source=source_key,
            source_name=source_name,
            source_tier=source_tier,
            url=link or entry_id_raw or "",
            published_at=_parse_pub_date(pub_raw),
            headline=_strip_html(title),
            body_snippet=_snippet(desc_raw),
        ))
    return results


def _parse_json_feed(
    text: str, source_key: str, source_name: str, source_tier: str
) -> list[FeedItem]:
    """Parse a JSON Feed (https://jsonfeed.org/version/1.1) or simple array."""
    data = json.loads(text)
    if isinstance(data, list):
        raw_items = data
    elif isinstance(data, dict):
        raw_items = data.get("items", [])
    else:
        return []

    results: list[FeedItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        url = str(item.get("url") or item.get("external_url") or "")
        guid = str(item.get("id") or item.get("guid") or url)
        pub_raw = str(item.get("date_published") or item.get("pubDate") or "")
        content = str(
            item.get("content_text") or item.get("content_html") or
            item.get("description") or item.get("summary") or ""
        )
        if not title and not url:
            continue

        item_id = _make_id(source_key, guid or url)
        results.append(FeedItem(
            id=item_id,
            source=source_key,
            source_name=source_name,
            source_tier=source_tier,
            url=url,
            published_at=_parse_pub_date(pub_raw),
            headline=_strip_html(title),
            body_snippet=_snippet(content),
        ))
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Seen-ledger helpers (filesystem, LOCAL-ONLY, never committed)
# ─────────────────────────────────────────────────────────────────────────────

def _breaking_dir(root: Path | str) -> Path:
    """Return the local-only breaking data dir, creating it if needed."""
    d = Path(root) / "data" / "marketing" / "breaking"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(path: Path, data: Any) -> None:
    """Write JSON atomically via tmp + os.replace (house law)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_seen(root: Path | str) -> dict[str, str]:
    """Load the seen-ledger {id -> first_seen_ts}. Returns {} on any error."""
    path = _breaking_dir(root) / "seen.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_seen(root: Path | str, seen: dict[str, str]) -> None:
    """Persist seen ledger, capped at _SEEN_CAP newest entries."""
    if len(seen) > _SEEN_CAP:
        # Sort by ts (ISO strings sort lexicographically) and keep newest
        pairs = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:_SEEN_CAP]
        seen = dict(pairs)
    _atomic_write(_breaking_dir(root) / "seen.json", seen)


def _load_state(root: Path | str) -> dict[str, Any]:
    """Load per-source state {source_key -> {etag, last_modified, last_poll_ts}}."""
    path = _breaking_dir(root) / "state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(root: Path | str, state: dict[str, Any]) -> None:
    _atomic_write(_breaking_dir(root) / "state.json", state)


def filter_new_items(
    items: list[FeedItem], root: Path | str
) -> tuple[list[FeedItem], dict[str, str]]:
    """Return (new_items, updated_seen_dict) without writing to disk.

    Callers write the ledger after processing all sources.
    """
    seen = _load_seen(root)
    now_ts = datetime.now(tz=timezone.utc).isoformat()
    new_items: list[FeedItem] = []
    for item in items:
        if item["id"] not in seen:
            seen[item["id"]] = now_ts
            new_items.append(item)
    return new_items, seen


# ─────────────────────────────────────────────────────────────────────────────
# Network poller (never called in tests)
# ─────────────────────────────────────────────────────────────────────────────

def poll_source(
    source_cfg: dict,
    *,
    root: Path | str,
    session_state: dict[str, Any] | None = None,
) -> list[FeedItem]:
    """Fetch one source URL and return parsed FeedItems (all, not deduplicated).

    Never called in tests. Network-only function.
    - Respects per-source politeness floor (poll_interval_s from source_cfg or
      breaking.poll_interval_s).
    - Sends conditional GET headers (ETag / Last-Modified) from stored state.
    - Honest User-Agent from source_cfg or config default.
    - Returns [] on any network/parse error (fail-soft, prints to stderr).
    """
    key = source_cfg.get("key", "unknown")
    url = source_cfg.get("url", "")
    kind = source_cfg.get("kind", "rss")
    interval = int(source_cfg.get("poll_interval_s", _DEFAULT_INTERVAL))
    user_agent = str(source_cfg.get("user_agent", _DEFAULT_UA))

    # Scheme allowlist — a mistyped/hostile config entry must never fetch
    # file:// / ftp:// etc.
    if not str(url).lower().startswith(("http://", "https://")):
        print(f"[breaking_feed] {key}: refusing non-http(s) url", file=sys.stderr)
        return []

    if session_state is None:
        session_state = _load_state(root)

    src_state = session_state.get(key, {})
    last_poll = src_state.get("last_poll_ts", 0)
    if (time.time() - float(last_poll)) < interval:
        return []  # politeness floor — too soon

    try:
        req = Request(url, headers={"User-Agent": user_agent})  # noqa: S310
        etag = src_state.get("etag", "")
        last_mod = src_state.get("last_modified", "")
        if etag:
            req.add_header("If-None-Match", etag)
        if last_mod:
            req.add_header("If-Modified-Since", last_mod)

        with urlopen(req, timeout=_FEED_TIMEOUT) as resp:  # noqa: S310
            status = resp.getcode()
            if status == 304:
                # Not modified — update last_poll_ts and return empty
                src_state["last_poll_ts"] = time.time()
                session_state[key] = src_state
                return []
            raw = resp.read(_MAX_FEED_BYTES + 1)
            if len(raw) > _MAX_FEED_BYTES:
                print(
                    f"[breaking_feed] {key}: feed exceeds {_MAX_FEED_BYTES} bytes — dropped",
                    file=sys.stderr,
                )
                src_state["last_poll_ts"] = time.time()
                session_state[key] = src_state
                return []
            text = raw.decode("utf-8", errors="replace")
            new_etag = resp.headers.get("ETag", "")
            new_last_mod = resp.headers.get("Last-Modified", "")

        # Update state
        src_state["last_poll_ts"] = time.time()
        if new_etag:
            src_state["etag"] = new_etag
        if new_last_mod:
            src_state["last_modified"] = new_last_mod
        session_state[key] = src_state

        return parse_feed(text, source_cfg)

    except Exception as exc:  # noqa: BLE001
        print(f"[breaking_feed] poll_source error ({key}): {exc}", file=sys.stderr)
        return []


def poll_all(root: Path | str, cfg: dict) -> list[FeedItem]:
    """Poll all configured sources and return NEW (unseen) items.

    - One dead feed never kills the tick (fail-soft per source).
    - Writes state.json + seen.json atomically after all sources complete.
    - cfg: the full marketing.yml `breaking` block.

    Returns only new items (not previously seen in the ledger).
    """
    breaking_cfg = cfg if "sources" in cfg else cfg.get("breaking", {})
    sources = breaking_cfg.get("sources", [])
    user_agent = breaking_cfg.get("user_agent", _DEFAULT_UA)
    default_interval = int(breaking_cfg.get("poll_interval_s", _DEFAULT_INTERVAL))

    session_state = _load_state(root)
    all_items: list[FeedItem] = []

    for src in sources:
        # Inject top-level defaults into per-source cfg if not present
        merged = {
            "poll_interval_s": default_interval,
            "user_agent": user_agent,
            **src,
        }
        fetched = poll_source(merged, root=root, session_state=session_state)
        all_items.extend(fetched)

    # Deduplicate against seen ledger
    new_items, updated_seen = filter_new_items(all_items, root)

    # Persist state and seen ledger
    _save_state(root, session_state)
    _save_seen(root, updated_seen)

    return new_items
