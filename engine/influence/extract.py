"""Influence-graph extractor — GROWS the multi-actor graph from news/filings (gated LLM).

The structured Quiver feeds see trades, not the QUALITATIVE affiliations the user cares
about — who an influential actor TALKS_ABOUT, ENDORSES, PARTNERS_WITH, or ADVISES. Those
live only in unstructured text. This is the cheap, high-volume "tagging" half of the LLM
work (Claude HAIKU via the OAuth path); the deep reasoning lives in engine/altdata_brain.

  * reads recent items from the Quiver news feed + tracked-entity SEC filings, filtered to
    the curated actor/entity roster,
  * asks Haiku for candidate affiliation EDGES, each backed by a VERBATIM quote,
  * REJECTS any edge whose citation is not a verbatim substring of the source (reuses
    catalyst_tone._norm — the anti-hallucination gate), and
  * writes survivors to data/altdata/influence_candidates.jsonl as low-confidence,
    INFERRED-provenance CANDIDATES — NEVER auto-merged. A human promotes them into the seed.

Gated (config influence.extract.enabled, default off) + degrades to a no-op without an LLM
token: the graph still works from the curated seed; the LLM is an amplifier, not a dependency.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from lib import config
from engine import catalyst_tone as _ct
from engine.influence import graph as _graph

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_RELS = {"CONTROLS", "HOLDS_STAKE", "OPERATED_BY", "FORMED", "LINKED_TO", "MEMBER_OF",
         "ADVISES", "INVESTS_IN", "TALKS_ABOUT", "AFFILIATES_WITH", "PARTNERS_WITH",
         "ENDORSES", "ATTENDS_EVENT", "MEETS"}

_DEFAULTS = {
    "extract": False,                       # MASTER SWITCH — default off
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "api_key_env": "ANTHROPIC_API_KEY",
    "model": "claude-haiku-4-5-20251001",   # cheap, high-volume tagging
    "max_tokens": 1200,
    "news_limit": 50,
    "filing_limit": 15,
    "oauth_pool_lane": "influence-extract",  # pool key expansion for this lane
    "usage_lane": "influence-extract",       # ai_costs attribution
}

_SYSTEM = (
    "You extract STRUCTURED affiliation relationships between an INFLUENTIAL PERSON (a "
    "politician, founder/CEO, fund manager, or market influencer) and an investable COMPANY "
    "or THEME, from a short news/filing excerpt. Capture not just trades but who a person "
    "TALKS_ABOUT, ENDORSES, ADVISES, PARTNERS_WITH, INVESTS_IN, or CONTROLS.\n"
    "Output ONLY JSON: {\"edges\":[{\"src\":\"<person name>\",\"rel\":\"<REL>\","
    "\"dst\":\"<company name or TICKER or theme>\","
    "\"asset_hint\":\"<the real underlying asset, if a brand differs>\","
    "\"citation\":\"<a VERBATIM quote from the text that supports this edge>\"}]}. "
    f"REL must be one of {sorted(_RELS)}. Emit an edge ONLY if a verbatim quote in the text "
    "supports it; copy that quote EXACTLY into `citation`. Never infer beyond the text. If "
    "nothing investment-relevant about a notable person is stated, return {\"edges\":[]}."
)


def _cfg() -> dict:
    """Read the nested influence.extract stanza, merged over defaults. Never raises."""
    try:
        ex = (config.load().get("influence", {}) or {}).get("extract", {})
        return {**_DEFAULTS, **(ex if isinstance(ex, dict) else {})}
    except Exception:  # noqa: BLE001
        return dict(_DEFAULTS)


def enabled() -> bool:
    cfg = _cfg()
    return bool(cfg.get("extract", cfg.get("enabled", False)))


# --------------------------------------------------------------------------- LLM client
def _call(source_text: str, cfg: dict) -> str | None:
    """Call the LLM for one source text via llm_auth waterfall.  Never raises."""
    try:
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(
            cfg, opus_model=cfg.get("model", "claude-haiku-4-5-20251001"))
    except Exception as e:  # noqa: BLE001
        log.warning("influence extract: provider build failed (%s)", e)
        return None
    if not providers:
        return None
    max_tokens = int(cfg.get("max_tokens", 1200))
    model = cfg.get("model", "claude-haiku-4-5-20251001")

    def _call_fn(client, m: str):
        resp = client.messages.create(
            model=m,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"<doc>\n{source_text}\n</doc>"}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text") or None, None, resp

    model_providers = [{**p, "model": model} for p in providers]
    try:
        text, _, _ = llm_auth.make_call(model_providers, _call_fn,
                                         context="influence_extract")
        return text or None
    except Exception as e:  # noqa: BLE001
        log.warning("influence extract model call failed (%s)", e)
        return None


# --------------------------------------------------------------------------- pure core
def _extract_edges(source_text: str, reply_text: str | None) -> list[dict]:
    """Parse a model reply into verified candidate edges. PURE. Any edge whose citation is
    not a verbatim (normalized) substring of the source is dropped (anti-hallucination)."""
    parsed = _ct._extract_json(reply_text or "")
    if not parsed or not isinstance(parsed.get("edges"), list):
        return []
    src_norm = _ct._norm(source_text or "")
    out = []
    for e in parsed["edges"]:
        if not isinstance(e, dict):
            continue
        rel = str(e.get("rel", "")).strip().upper()
        src, dst = str(e.get("src", "")).strip(), str(e.get("dst", "")).strip()
        cite = _ct._norm(e.get("citation", ""))
        if rel not in _RELS or not src or not dst:
            continue
        if len(cite) < 8 or cite not in src_norm:
            continue
        out.append({
            "src": src, "rel": rel, "dst": dst,
            "asset_hint": str(e.get("asset_hint", "")).strip() or None,
            "citation": str(e.get("citation", "")).strip(),
            "provenance": "INFERRED", "confidence": 0.5, "status": "candidate",
        })
    return out


def _key(e: dict) -> str:
    return f"{e['src'].lower()}|{e['rel']}|{e['dst'].lower()}"


# --------------------------------------------------------------------------- io
def _path(root=None):
    return (config.data_dir() if root is None else (root / "data")) / "altdata" / "influence_candidates.jsonl"


def load_candidates(root=None) -> list[dict]:
    p = _path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _roster_keywords(root=None) -> list[str]:
    """Actor + entity names from the merged seed — the news filter."""
    g = _graph.load_seed(root)
    kws = set()
    for a in g.get("actors", []):
        nm = (a.get("name") or "").lower().strip()
        if len(nm) >= 4:
            kws.add(nm)
    for e in g.get("entities", []):
        nm = (e.get("name") or "").lower().strip()
        if len(nm) >= 4:
            kws.add(nm)
    return sorted(kws)


def _s(v):
    s = str(v).strip() if v is not None else ""
    return s if s and s.lower() not in ("nan", "none") else None


def _news_items(root=None, limit: int = 50) -> list[dict]:
    try:
        import pandas as pd
        p = (config.data_dir() if root is None else (root / "data")) / "quiver" / "news.parquet"
        if not p.exists():
            return []
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return []
    kws = _roster_keywords(root)
    items = []
    for _, r in df.iterrows():
        text = " ".join(str(r.get(k, "")) for k in ("headline", "summary") if r.get(k))
        low = text.lower()
        if any(k in low for k in kws):
            items.append({"text": text[:2000], "url": _s(r.get("url")), "time": _s(r.get("time")),
                          "source_id": "news:" + (_s(r.get("url")) or text[:60]), "source_type": "news"})
        if len(items) >= limit:
            break
    return items


def _seen_path(root=None):
    return (config.data_dir() if root is None else (root / "data")) / "altdata" / "influence_extract_seen.json"


def _load_seen(root=None) -> set:
    p = _seen_path(root)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()) or [])
    except Exception:  # noqa: BLE001
        return set()


def _save_seen(seen: set, root=None) -> None:
    p = _seen_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen)[-5000:]))


def run(root=None, news_limit: int | None = None) -> dict:
    """Extract candidate affiliation edges from recent roster-matched NEWS. Each candidate
    needs a verbatim citation. Gated + degrade-never-raise; watermarked so each source is
    processed once."""
    cfg = _cfg()
    if not enabled():
        return {"extracted": 0, "reason": "disabled"}
    # Pool-aware presence check: build providers and return early only when the
    # list is empty — this mirrors commodity_news's pattern and respects
    # CLAUDE_CODE_OAUTH_TOKEN_N pool keys in addition to the legacy single-key
    # env vars.
    try:
        from engine import llm_auth as _llm_auth  # noqa: PLC0415
        _providers = _llm_auth.build_providers(cfg)
    except Exception:  # noqa: BLE001
        _providers = []
    if not _providers:
        return {"extracted": 0, "reason": "no_token"}
    seen = _load_seen(root)
    existing = {_key(e) for e in load_candidates(root)}
    items = [it for it in _news_items(root, news_limit or int(cfg.get("news_limit", 50)))
             if it["source_id"] not in seen]
    new, processed = [], []
    for item in items:
        processed.append(item["source_id"])
        for e in _extract_edges(item["text"], _call(item["text"], cfg)):
            if _key(e) in existing:
                continue
            existing.add(_key(e))
            e.update({"url": item.get("url"), "source_type": item.get("source_type"),
                      "source_time": item.get("time"),
                      "extracted_at": datetime.now(timezone.utc).isoformat()})
            new.append(e)
    if new:
        p = _path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as fh:
            for e in new:
                fh.write(json.dumps(e, default=str) + "\n")
    if processed:
        _save_seen(seen | set(processed), root)
    log.info("influence extract: %d candidate edge(s) from %d source(s)", len(new), len(processed))
    return {"extracted": len(new), "processed": len(processed), "reason": "ok"}
