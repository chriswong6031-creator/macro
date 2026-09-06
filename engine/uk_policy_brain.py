"""UK policy desk — the latest HM Treasury announcement, read in plain words.

LEAF · GATED · DEFAULT-OFF-WITHOUT-KEY · CONTEXT-ONLY · DEGRADE-NEVER-RAISE.

Second jurisdiction under the engine.whitehouse_brain contract (that module's
docstring :1-27 is the reference; it is NOT imported and NOT refactored here).
Polls GOV.UK's keyless public Search/Content APIs for HM Treasury
announcements, keeps its own dedupe state, and asks the model to do exactly two
non-authoritative things over the fetched text: restate it in one plain
sentence, and classify its stance into a closed four-member set.

The MODEL NEVER ORIGINATES ANYTHING. Jurisdiction, issuing body, headline,
source URL, document type, published time, known-at time, staleness and the
panel state are all engine-derived facts. The model may not name a ticker, a
sector, a sanctions fact, a causal relation, a score, a size, a rank, or any
number that is not already in the quoted source text. Nothing in axes / regime
/ conditions / scoring imports this module; it writes a SEPARATE display
artifact (site/uk_policy.json) that only Fed & Policy Watch reads.

Source: GOV.UK, Crown copyright, reused under the Open Government Licence v3.0.
This is context, never advice and never a trade signal.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from lib import config

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "macro-dashboard/1.0 (+research; uk-policy-desk)")

SEARCH_URL = (
    "https://www.gov.uk/api/search.json?filter_organisations=hm-treasury"
    "&filter_content_purpose_supergroup=news_and_communications"
    "&order=-public_timestamp&count=20"
    "&fields=title,link,public_timestamp,description,content_store_document_type,organisations"
)
CONTENT_URL_BASE = "https://www.gov.uk/api/content"
FALLBACK_ATOM_URL = (
    "https://www.gov.uk/search/news-and-communications.atom"
    "?organisations%5B%5D=hm-treasury"
)

GATE_ENV = "UK_POLICY_DESK_ENABLED"

_STANCES = frozenset({"supportive", "restrictive", "mixed", "routine"})
_STATES = frozenset({"ok", "no_new", "source_outage", "stale", "gate_off"})

_BANNED_TERMS = (
    "sanction", "sanctions", "score", "rank", "buy", "sell", "overweight",
    "underweight", "target", "causes", "because of", "will cause",
)
_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")
_DIGIT_RUN_RE = re.compile(r"\d[\d,.]*")

_DEFAULTS = {
    "enabled": False,
    "max_age_days": 4.0,
    "stale_after_days": 3.0,
    "summary_max_en": 150,
    "summary_max_zh": 70,
    "excerpt_max": 400,
    "timeout": 15,
    "model": "claude-opus-4-8",
}


# --------------------------------------------------------------------------- #
# config + gate
# --------------------------------------------------------------------------- #
def _cfg() -> dict:
    try:
        return {**_DEFAULTS, **(config.load().get("uk_policy_desk") or {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def _provider(cfg: dict) -> tuple[str, str, str] | None:
    """(provider, credential, model) for the first available provider, or None.
    Mirrors engine.whitehouse_brain._provider's ladder exactly."""
    import os

    model = cfg.get("model", _DEFAULTS["model"])
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if tok:
        return ("oauth", tok, model)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return ("anthropic", key, model)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return ("deepseek", key, "deepseek-v4-pro")
    return None


def enabled() -> bool:
    """True only when the desk is switched on AND a model credential exists."""
    import os

    cfg = _cfg()
    on = bool(cfg.get("enabled", False)) or os.environ.get(GATE_ENV) == "1"
    return bool(on and _provider(cfg) is not None)


def provider_label(cfg: dict | None = None) -> str:
    prov = _provider(cfg or _cfg())
    if prov is None:
        return ""
    name, _cred, model = prov
    labels = {"oauth": "Claude (subscription)", "anthropic": "Claude API", "deepseek": "DeepSeek"}
    return f"{labels.get(name, name)} · {model}"


# --------------------------------------------------------------------------- #
# fetch + parse (mirrors engine.whitehouse_feed's shape; not imported/refactored)
# --------------------------------------------------------------------------- #
def _fetch(url: str, timeout: float = 15) -> bytes | None:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.debug("uk_policy fetch failed %s (%s)", url, e)
        return None


def _to_iso(ts: object) -> str:
    raw = str(ts or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return ""


def _clean(text: object, limit: int = 4000) -> str:
    t = str(text or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


def _slug_id(url: str, published: str) -> str:
    try:
        seg = [p for p in urlparse(url).path.split("/") if p]
        slug = seg[-1] if seg else "item"
    except Exception:  # noqa: BLE001
        slug = "item"
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")[:80] or "item"
    day = (published or "")[:10] or "undated"
    return f"uk-{day}-{slug}"


def _parse_search_results(raw: bytes) -> list[dict]:
    out: list[dict] = []
    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        log.debug("uk_policy parse error (%s)", e)
        return out
    for it in (data.get("results") or []):
        title = _clean(it.get("title"))
        link = str(it.get("link") or "")
        if not title or not link:
            continue
        url = link if link.startswith("http") else f"https://www.gov.uk{link}"
        published = _to_iso(it.get("public_timestamp"))
        doc_type = _clean(it.get("content_store_document_type")).replace("_", " ").title()
        body_text = _clean(it.get("description"), limit=4000)
        out.append({
            "id": _slug_id(url, published),
            "title": title,
            "url": url,
            "published": published,
            "section": "news_and_communications",
            "doc_type": doc_type or "News story",
            "body_text": body_text,
        })
    return out


def collect(max_age_days: float = 4.0) -> list[dict]:
    """Current HM Treasury GOV.UK announcements, newest-first, filtered to the
    recent window. Never raises; returns [] on any failure."""
    try:
        raw = _fetch(SEARCH_URL, timeout=_cfg().get("timeout", 15))
        items = _parse_search_results(raw) if raw else []
        if not items:
            raw2 = _fetch(FALLBACK_ATOM_URL, timeout=_cfg().get("timeout", 15))
            items = _parse_atom(raw2) if raw2 else []
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400
        fresh = []
        for it in items:
            try:
                ts = datetime.fromisoformat(it["published"]).timestamp() if it.get("published") else None
            except Exception:  # noqa: BLE001
                ts = None
            if ts is None or ts >= cutoff:
                fresh.append(it)
        fresh.sort(key=lambda x: x.get("published") or "", reverse=True)
        return fresh
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.debug("uk_policy collect failed (%s)", e)
        return []


def _parse_atom(raw: bytes) -> list[dict]:
    out: list[dict] = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            title_el = entry.find("a:title", ns)
            link_el = entry.find("a:link", ns)
            updated_el = entry.find("a:updated", ns)
            summary_el = entry.find("a:summary", ns)
            title = _clean(title_el.text if title_el is not None else "")
            url = link_el.get("href") if link_el is not None else ""
            if not title or not url:
                continue
            published = _to_iso(updated_el.text if updated_el is not None else "")
            out.append({
                "id": _slug_id(url, published),
                "title": title,
                "url": url,
                "published": published,
                "section": "news_and_communications",
                "doc_type": "News story",
                "body_text": _clean(summary_el.text if summary_el is not None else "", limit=4000),
            })
    except Exception as e:  # noqa: BLE001
        log.debug("uk_policy atom parse failed (%s)", e)
    return out


def fetch_body(url: str) -> str:
    """Fetch the fuller body via the GOV.UK Content API. Degrades to '' on failure."""
    try:
        path = urlparse(url).path
        raw = _fetch(f"{CONTENT_URL_BASE}{path}", timeout=_cfg().get("timeout", 15))
        if not raw:
            return ""
        data = json.loads(raw)
        details = data.get("details") or {}
        body = details.get("body") or ""
        return _clean(body, limit=8000)
    except Exception as e:  # noqa: BLE001
        log.debug("uk_policy fetch_body failed (%s)", e)
        return ""


# --------------------------------------------------------------------------- #
# dedupe state
# --------------------------------------------------------------------------- #
def _state_path(root: Path) -> Path:
    return Path(root) / "data" / "uk_policy" / "processed.json"


def load_processed(root: Path) -> dict:
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
    except Exception as e:  # noqa: BLE001
        log.warning("uk_policy: processed.json write failed (%s)", e)


def mark_seen(state: dict, item: dict, **kw) -> None:
    state.setdefault("seen", {})[item["id"]] = {
        "at": datetime.now(timezone.utc).isoformat(),
        **kw,
    }


def new_items(items: list[dict], state: dict) -> list[dict]:
    seen = (state or {}).get("seen", {})
    return [it for it in items if it.get("id") not in seen]


# --------------------------------------------------------------------------- #
# model boundary — clamps enforced in CODE, never trusted from the prompt
# --------------------------------------------------------------------------- #
def _norm_stance(raw: object) -> str:
    s = str(raw or "").strip().lower()
    return s if s in _STANCES else "routine"


def _no_new_numbers(text: object, excerpt: str) -> bool:
    """True if `text` is safe: every digit run in it also appears in `excerpt`."""
    t = str(text or "")
    for m in _DIGIT_RUN_RE.findall(t):
        if m not in excerpt:
            return False
    return True


def _ban_terms(text: object, excerpt: str) -> bool:
    """True if `text` is safe: no banned term, no ticker-shaped token absent from excerpt."""
    t = str(text or "")
    low = t.lower()
    for term in _BANNED_TERMS:
        if term in low:
            return False
    for tok in _TICKER_RE.findall(t):
        if tok not in excerpt:
            return False
    return True


def _sanitize_field(text: object, excerpt: str) -> str | None:
    if text is None:
        return None
    t = str(text).strip()
    if not t:
        return None
    if not _no_new_numbers(t, excerpt):
        return None
    if not _ban_terms(t, excerpt):
        return None
    return t


_PROMPT_TEMPLATE = """You are reading one UK government announcement. Use only the
text provided. Do not add facts, numbers, companies, tickers, sectors, sanctions or
causes. If the text does not support a stance, answer 'routine'.

Title: {title}
Text: {excerpt}

Reply with strict JSON only:
{{"summary_en": "<one plain sentence restating the text, <= {sum_en} chars>",
  "summary_zh": "<translation of summary_en, <= {sum_zh} chars>",
  "stance": "<one of supportive, restrictive, mixed, routine>",
  "watch_en": "<one context/what-to-watch sentence drawn from the text>",
  "watch_zh": "<translation of watch_en>"}}
"""


def _call_model(item: dict, excerpt: str, cfg: dict, call=None) -> dict:
    """Runs the model call (or the injected `call` stub) and returns a raw dict.
    Never raises — any failure returns an empty dict, which evaluate() treats as
    'routine, no summary'."""
    prompt = _PROMPT_TEMPLATE.format(
        title=item.get("title", ""), excerpt=excerpt,
        sum_en=cfg.get("summary_max_en", 150), sum_zh=cfg.get("summary_max_zh", 70),
    )
    try:
        if call is not None:
            raw = call(prompt)
        else:
            prov = _provider(cfg)
            if prov is None:
                return {}
            raw = _call_anthropic_like(prov, prompt, cfg)
        if isinstance(raw, dict):
            return raw
        text = str(raw or "")
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        log.debug("uk_policy model call failed (%s)", e)
        return {}


def _call_anthropic_like(prov: tuple[str, str, str], prompt: str, cfg: dict) -> str:
    """Minimal HTTP call to an Anthropic-compatible endpoint. Degrades to '' on
    any failure — the caller treats an unparseable/empty result as no summary."""
    import urllib.request

    name, cred, model = prov
    try:
        if name == "deepseek":
            url = "https://api.deepseek.com/anthropic/v1/messages"
        else:
            url = "https://api.anthropic.com/v1/messages"
        headers = {"content-type": "application/json", "x-api-key": cred, "anthropic-version": "2023-06-01"}
        if name == "oauth":
            headers = {"content-type": "application/json", "authorization": f"Bearer {cred}",
                       "anthropic-beta": "oauth-2025-04-20", "anthropic-version": "2023-06-01"}
        payload = json.dumps({
            "model": model, "max_tokens": 600,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=cfg.get("timeout", 15)) as r:
            data = json.loads(r.read())
        parts = data.get("content") or []
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    except Exception as e:  # noqa: BLE001
        log.debug("uk_policy llm http call failed (%s)", e)
        return ""


def evaluate(item: dict, cfg: dict | None = None, root=None, call=None) -> dict:
    """Engine facts + model restate/classify, clamped in code. Never raises."""
    cfg = cfg or _cfg()
    excerpt = _clean(item.get("body_text") or item.get("title") or "", limit=cfg.get("excerpt_max", 400))
    raw = _call_model(item, excerpt, cfg, call=call)
    stance = _norm_stance(raw.get("stance"))
    summary_en = _sanitize_field(raw.get("summary_en"), excerpt)
    summary_zh = _sanitize_field(raw.get("summary_zh"), excerpt)
    watch_en = _sanitize_field(raw.get("watch_en"), excerpt)
    watch_zh = _sanitize_field(raw.get("watch_zh"), excerpt)
    now = datetime.now(timezone.utc)
    try:
        pub_dt = datetime.fromisoformat(item["published"]) if item.get("published") else now
    except Exception:  # noqa: BLE001
        pub_dt = now
    age_days = max(0.0, (now - pub_dt).total_seconds() / 86400.0)
    return {
        "schema": "uk_policy/1",
        "jurisdiction_en": "United Kingdom", "jurisdiction_zh": "英国",
        "body_en": "HM Treasury", "body_zh": "英国财政部",
        "source_label": "GOV.UK",
        "headline": item.get("title"),
        "doc_type_en": item.get("doc_type") or "News story", "doc_type_zh": "新闻稿",
        "source_url": item.get("url"),
        "published_iso": item.get("published"),
        "known_at_iso": now.isoformat(),
        "age_days": round(age_days, 2),
        "stance": stance,
        "summary_en": summary_en, "summary_zh": summary_zh,
        "watch_en": watch_en, "watch_zh": watch_zh,
        "excerpt": excerpt,
        "provider_label": provider_label(cfg),
        "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
    }


# --------------------------------------------------------------------------- #
# artifact + state derivation
# --------------------------------------------------------------------------- #
def _artifact_path(root: Path) -> Path:
    return Path(root) / "site" / "uk_policy.json"


def latest(root=None) -> dict | None:
    root = Path(root) if root else config.ROOT
    try:
        d = json.loads(_artifact_path(root).read_text())
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _persist(record: dict, root: Path) -> None:
    try:
        p = _artifact_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        clean = {k: v for k, v in record.items() if k != "raw_text"}
        p.write_text(json.dumps(clean, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("uk_policy persist failed: %s", e)


def run(persist: bool = True, root=None, force: bool = False, call=None) -> dict | None:
    """Gather -> evaluate -> persist. Returns None when the gate is off (unless
    force). NEVER raises into the caller — every failure degrades to a typed
    'source_outage' record when a prior record exists, else None."""
    root = Path(root) if root else config.ROOT
    cfg = _cfg()
    if not force and not enabled():
        return None
    try:
        state = load_processed(root)
        items = collect(cfg.get("max_age_days", 4.0))
        prior = latest(root)
        if not items:
            record = dict(prior) if prior else None
            if record is not None:
                record["state"] = "source_outage"
            if persist and record is not None:
                _persist(record, root)
            return record
        fresh = new_items(items, state)
        if not fresh:
            record = dict(prior) if prior else evaluate(items[0], cfg, root, call=call)
            record["state"] = "no_new"
            if persist:
                _persist(record, root)
            return record
        item = fresh[0]
        if not item.get("body_text"):
            item = dict(item)
            item["body_text"] = fetch_body(item["url"]) or item.get("title", "")
        record = evaluate(item, cfg, root, call=call)
        stale_after = cfg.get("stale_after_days", 3.0)
        record["state"] = "stale" if record.get("age_days", 0.0) > stale_after else "ok"
        mark_seen(state, item)
        if persist:
            save_processed(root, state)
            _persist(record, root)
        return record
    except Exception as e:  # noqa: BLE001 — degrade-never-raise
        log.warning("uk_policy run failed: %s", e)
        try:
            prior = latest(root)
            if prior is not None:
                prior = dict(prior)
                prior["state"] = "source_outage"
                if persist:
                    _persist(prior, root)
                return prior
        except Exception:  # noqa: BLE001
            pass
        return None
