"""TrumpFlow LLM extractor — GROWS the entity graph from unstructured news/filings.

The structured Quiver feeds cannot see private equity-for-partnership stakes, family
LLCs, or pre-IPO/SPAC vehicles — those live only in news/filings. This is the ONE place
an LLM touches raw text, and it is an EXTRACTOR, not an oracle:

  * reads recent Trump-entity items from the Quiver news feed (data/quiver/news.parquet),
  * asks the model for candidate ownership/investment EDGES, each backed by a verbatim
    quote from the source,
  * REJECTS any edge whose citation is not a verbatim substring of the source text
    (reuses catalyst_tone._norm — the anti-hallucination gate), and
  * writes survivors to data/trumpflow/extracted_edges.jsonl as low-confidence,
    INFERRED-provenance CANDIDATES — NEVER auto-merged into the curated graph. A human
    promotes them into intel.json.

Gated (config trumpflow.extract, default off) + degrades to a no-op without an LLM key:
the graph still works from the curated seed; the LLM is an amplifier, not a dependency.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from lib import config
from engine import catalyst_tone as _ct

log = logging.getLogger(__name__)

_RELS = {"CONTROLS", "HOLDS_STAKE", "OPERATED_BY", "FORMED", "LINKED_TO", "MEMBER_OF",
         "ADVISES", "SPUN_OUT", "INVESTS_IN"}

# Trump-family / administration entity keywords used to filter the news feed.
_KEYWORDS = [
    "trump", "eric trump", "donald trump jr", "trump jr", "american bitcoin", "abtc",
    "hut 8", "world liberty", "wlfi", "usd1", "truth social", "trump media", "djt",
    "dominari", "american data centers", "affinity partners", "jared kushner",
]

_SYSTEM = (
    "You extract STRUCTURED ownership / investment relationships involving Donald Trump's "
    "family or the administration from a short news excerpt. Output ONLY JSON: "
    '{"edges":[{"src":"<person or entity>","rel":"<REL>","dst":"<entity>",'
    '"asset_hint":"<what the real asset is, if a brand differs from the underlying>",'
    '"citation":"<a VERBATIM quote from the text that supports this edge>"}]}. '
    f"REL must be one of {sorted(_RELS)}. Emit an edge ONLY if a verbatim quote in the "
    "text supports it; copy that quote exactly into `citation`. Never infer beyond the "
    "text. If nothing investment-relevant is stated, return {\"edges\":[]}."
)


def _cfg() -> dict:
    # reuse the catalyst_tone DeepSeek config (same key / base / model)
    base = dict(_ct._cfg())
    base.update(config.load().get("trumpflow", {}) or {})
    return base


def enabled() -> bool:
    return bool((config.load().get("trumpflow", {}) or {}).get("extract", False))


# --------------------------------------------------------------------------- pure core
def _extract_edges(source_text: str, reply_text: str | None) -> list[dict]:
    """Parse a model reply into verified candidate edges. PURE — no network.
    Any edge whose citation is not a verbatim (normalized) substring of the source is
    dropped (the anti-hallucination gate)."""
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
        if len(cite) < 8 or cite not in src_norm:        # citation must be verbatim in source
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
    return (config.data_dir() if root is None else (root / "data")) / "trumpflow" / "extracted_edges.jsonl"


def load_candidates(root=None) -> list[dict]:
    p = _path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _relevant_news(root=None, limit: int = 40) -> list[dict]:
    try:
        import pandas as pd
        p = (config.data_dir() if root is None else (root / "data")) / "quiver" / "news.parquet"
        if not p.exists():
            return []
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return []
    items = []
    for _, r in df.iterrows():
        text = " ".join(str(r.get(k, "")) for k in ("headline", "summary") if r.get(k))
        low = text.lower()
        if any(k in low for k in _KEYWORDS):
            items.append({"text": text[:2000], "url": _s(r.get("url")), "time": _s(r.get("time"))})
        if len(items) >= limit:
            break
    return items


def _s(v):
    s = str(v).strip() if v is not None else ""
    return s if s and s.lower() not in ("nan", "none") else None


def _call(source_text: str, cfg: dict) -> str | None:
    client = _ct._client(cfg)
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-v4-flash"),
            max_tokens=int(cfg.get("max_tokens", 1200)),
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"<doc>\n{source_text}\n</doc>"}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text") or None
    except Exception as e:  # noqa: BLE001
        log.warning("trumpflow extract model call failed (%s)", e)
        return None


def run(root=None, limit: int = 40) -> dict:
    """Extract candidate edges from recent Trump-entity news. Gated + degrade-never-raise."""
    if not enabled():
        return {"extracted": 0, "reason": "disabled"}
    cfg = _cfg()
    if _ct._client(cfg) is None:
        return {"extracted": 0, "reason": "no_key"}
    existing = {_key(e) for e in load_candidates(root)}
    new = []
    for item in _relevant_news(root, limit):
        reply = _call(item["text"], cfg)
        for e in _extract_edges(item["text"], reply):
            if _key(e) in existing:
                continue
            existing.add(_key(e))
            e["url"], e["source_time"] = item.get("url"), item.get("time")
            e["extracted_at"] = datetime.now(timezone.utc).isoformat()
            new.append(e)
    if new:
        p = _path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as fh:
            for e in new:
                fh.write(json.dumps(e, default=str) + "\n")
        log.info("trumpflow extract: %d new candidate edge(s) for review", len(new))
    return {"extracted": len(new), "reason": "ok"}
