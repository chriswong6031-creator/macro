"""China native flash-wire JSON fetchers — 华尔街见闻 · 金十数据 · 格隆汇.

LEAF · KEYLESS · CONTEXT-ONLY. Direct on-the-ground Chinese financial newswires,
fetched from each vendor's public keyless JSON endpoint (no akshare dependency,
no scraping) and normalized into the shared headline-item shape consumed by BOTH
engine/china_news.py (the china_news.html page panel) and
engine/china_news_intel.py (the PIT event bus). One cached fetch per TTL window
serves both consumers.

Live-probed 2026-07-10 (all three return fresh same-minute items):
  • wallstreetcn — https://api-one.wallstcn.com/apiv1/content/lives  (华尔街见闻 7×24)
  • jin10        — https://www.jin10.com/flash_newest.js             (金十数据快讯)
  • gelonghui    — https://www.gelonghui.com/api/live-channels/all/lives (格隆汇快讯)

Known-dead alternatives (do not re-add without a fresh probe): cls.cn nodeapi
(404, and akshare stock_info_global_cls broke Feb-2025 per
research/CHINA_INTEL_POWERHOUSE.md), api.thepaper.cn nodeCont (404),
people.com.cn RSS (frozen at 2025-06-05).

Item contract (every parser returns this shape; time is ISO-8601 WITH tz):
  {title, summary, time, url, source, source_name, domain, source_lang,
   wire_important}

Every public function degrades to [] and NEVER raises into the build. Parsers
are pure (no network / no clock) and unit-tested on committed fixture payloads.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "cn_newswires.v1"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "macro-dashboard/1.0 (research)")

# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
_BRACKET_TITLE = re.compile(r"^【([^】]{4,90})】\s*(.*)$", re.S)
_GLH_PREFIX = re.compile(r"^格隆汇\d{1,2}月\d{1,2}日[｜|丨]\s*")


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text or "")


def _split_flash(content: str) -> tuple[str, str]:
    """(title, summary) from a raw flash body. 【标题】 brackets win; else the first
    sentence (8-90 chars) titles the item and the full body rides as summary. PURE."""
    content = " ".join((content or "").split())
    m = _BRACKET_TITLE.match(content)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    for sep in ("。", "；", "！", "? ", ". "):
        idx = content.find(sep)
        if 8 <= idx <= 90:
            return content[:idx], content
    return content[:90], (content if len(content) > 90 else "")


def _iso_from_epoch(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _iso_from_beijing(s: str) -> str:
    """'YYYY-MM-DD HH:MM:SS' (naive Beijing wall clock) -> ISO-8601 with +08:00."""
    s = (s or "").strip()
    if not re.match(r"^20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}", s):
        return ""
    return s.replace(" ", "T") + "+08:00"


def _item(title: str, summary: str, when: str, url: str, source: str,
          source_name: str, domain: str, important: bool = False) -> dict | None:
    title = " ".join((title or "").split())
    # CJK packs ~2x the information per char — 4 CJK chars (央行公告) is a real
    # title, 4 latin chars is noise.
    if len(title) < (4 if _has_cjk(title) else 12):
        return None
    return {"title": title, "summary": " ".join((summary or "").split())[:280],
            "time": when, "url": url, "source": source, "source_name": source_name,
            "domain": domain, "source_lang": "zh" if _has_cjk(title) else "en",
            "wire_important": bool(important)}


# --------------------------------------------------------------------------- #
# per-source pure parsers (fixture-tested; tolerate schema drift by degrading)
# --------------------------------------------------------------------------- #
def parse_wallstreetcn(payload: dict, cap: int = 80) -> list[dict]:
    """华尔街见闻 7×24 lives. content_text carries the flash; title usually empty;
    display_time is unix epoch; score>=2 flags vendor-marked important items. PURE."""
    out: list[dict] = []
    try:
        items = ((payload or {}).get("data") or {}).get("items") or []
        for raw in items[:cap]:
            if not isinstance(raw, dict):
                continue
            body = str(raw.get("content_text") or "").strip()
            title = str(raw.get("title") or "").strip()
            if title and body:
                summary = body
            else:
                title, summary = _split_flash(title or body)
            it = _item(title, summary, _iso_from_epoch(raw.get("display_time")),
                       str(raw.get("uri") or ""), "wallstreetcn", "华尔街见闻",
                       "wallstreetcn.com",
                       important=(int(raw.get("score") or 1) >= 2))
            if it:
                out.append(it)
    except Exception as e:  # noqa: BLE001 — parser must never raise
        log.debug("cn_newswires.parse_wallstreetcn failed (%s)", e)
    return out


def parse_jin10(js_text: str, cap: int = 80) -> list[dict]:
    """金十数据 flash_newest.js — 'var newest = [...]' JS-wrapped JSON. type==0 are
    text flashes; data.content may open with a 【标题】 bracket; time is naive
    Beijing wall clock; important==1 is the vendor's red-flag. PURE."""
    out: list[dict] = []
    try:
        txt = js_text or ""
        start, end = txt.find("["), txt.rfind("]")
        if start < 0 or end <= start:
            return out
        for raw in json.loads(txt[start:end + 1])[:cap * 2]:
            if len(out) >= cap:
                break
            if not isinstance(raw, dict) or int(raw.get("type") or 0) != 0:
                continue
            data = raw.get("data") or {}
            body = str(data.get("content") or "").strip()
            title = str(data.get("title") or "").strip()
            if not (title and body):
                title, summary = _split_flash(title or body)
            else:
                summary = body
            url = str(data.get("source_link") or "").strip() or \
                f"https://flash.jin10.com/detail/{raw.get('id', '')}"
            it = _item(title, summary, _iso_from_beijing(str(raw.get("time") or "")),
                       url, "jin10", "金十数据", "jin10.com",
                       important=bool(raw.get("important")))
            if it:
                out.append(it)
    except Exception as e:  # noqa: BLE001
        log.debug("cn_newswires.parse_jin10 failed (%s)", e)
    return out


def parse_gelonghui(payload: dict, cap: int = 80) -> list[dict]:
    """格隆汇快讯 live-channel API. content opens with a '格隆汇M月D日｜' stamp
    (stripped); createTime is unix epoch. PURE."""
    out: list[dict] = []
    try:
        for raw in ((payload or {}).get("result") or [])[:cap]:
            if not isinstance(raw, dict):
                continue
            body = _GLH_PREFIX.sub("", str(raw.get("content") or "").strip())
            title = str(raw.get("title") or "").strip()
            if not (title and body):
                title, summary = _split_flash(title or body)
            else:
                summary = body
            url = str(raw.get("link") or "").strip() or \
                f"https://www.gelonghui.com/live/{raw.get('id', '')}"
            it = _item(title, summary, _iso_from_epoch(raw.get("createTime")),
                       url, "gelonghui", "格隆汇", "gelonghui.com")
            if it:
                out.append(it)
    except Exception as e:  # noqa: BLE001
        log.debug("cn_newswires.parse_gelonghui failed (%s)", e)
    return out


# --------------------------------------------------------------------------- #
# source registry + cached fetch
# --------------------------------------------------------------------------- #
_SOURCES: dict[str, dict] = {
    "wallstreetcn": {
        "url": ("https://api-one.wallstcn.com/apiv1/content/lives"
                "?channel=global-channel&client=pc&limit=100"),
        "parse": lambda body, cap: parse_wallstreetcn(json.loads(body), cap),
    },
    "jin10": {
        "url": "https://www.jin10.com/flash_newest.js",
        "parse": lambda body, cap: parse_jin10(body.decode("utf-8", "replace")
                                               if isinstance(body, bytes) else body, cap),
    },
    "gelonghui": {
        "url": "https://www.gelonghui.com/api/live-channels/all/lives?limit=100",
        "parse": lambda body, cap: parse_gelonghui(json.loads(body), cap),
    },
}


def _cfg() -> dict:
    return config.load().get("cn_newswires", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def _cache_path(cfg: dict, d: date) -> Path:
    cdir = config.ROOT / cfg.get("cache_dir", "data/china_news/cn_wire_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"wires_{d.isoformat()}.json"


def _fetch_one(name: str, cap: int, timeout: int = 15) -> list[dict]:
    src = _SOURCES.get(name)
    if not src:
        return []
    try:
        req = urllib.request.Request(src["url"], headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read()
        return src["parse"](body, cap)
    except Exception as e:  # noqa: BLE001 — per-source isolation, degrade to []
        log.warning("cn_newswires %s fetch failed (%s)", name, e)
        return []


def fetch_all(cfg: dict | None = None, today: date | None = None) -> list[dict]:
    """All configured wires, normalized + concatenated. Cached per-day with a TTL
    (one fetch serves both the page panel and the intel bus). NEVER raises."""
    try:
        cfg = cfg if cfg is not None else _cfg()
        if not cfg.get("enabled", True):
            return []
        today = today or date.today()
        cache = _cache_path(cfg, today)
        ttl = int(cfg.get("cache_ttl_hours", 6)) * 3600
        if cache.exists():
            try:
                if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                    return json.loads(cache.read_text()).get("items", [])
            except Exception:  # noqa: BLE001
                pass
        cap = int(cfg.get("max_per_source", 80))
        items: list[dict] = []
        for name in (cfg.get("sources") or list(_SOURCES)):
            items.extend(_fetch_one(str(name), cap))
        try:
            cache.write_text(json.dumps({"schema": SCHEMA, "items": items},
                                        ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass
        return items
    except Exception as e:  # noqa: BLE001
        log.error("cn_newswires.fetch_all failed (%s)", e)
        return []
