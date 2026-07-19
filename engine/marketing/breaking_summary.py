"""engine.marketing.breaking_summary — Summarize-cite lane for breaking items.

Enforces:
- LLM gating EXACTLY mirrors copywriter.write_posts_llm: both
  cfg["breaking"]["llm"]["enabled"] AND env MARKETING_LLM_ENABLED must be set.
  Zero LLM calls in tests (the env guard ensures this).
- validate_summary is STRICTER than validate_copy rule #5: every digit-containing
  token in the summary must appear verbatim in item headline+body_snippet with
  ZERO tolerance (no bare-integer exemption here — this is the citation lane).
- Deterministic fallback = "{headline} — {source_name}" on any LLM failure or
  any validate_summary violation.
- Stance/interpretation vocab banned: no "bullish", "bearish", "buy", "sell",
  "rally" (if not in source), "plunge" (if not in source), no advice phrasing.
- build_breaking_payload produces the outbox-shaped artifact; imports
  render_breaking_card lazily (degrades to card_svg="" if unavailable).

Public API:
    validate_summary(summary_text, item) -> list[str]
    summarize_item(item, cfg) -> dict
    build_breaking_payload(item, cfg, *, root=None) -> dict
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Stance/interpretation vocab banned from summaries (module-level tuple)
# ─────────────────────────────────────────────────────────────────────────────

_STANCE_BANNED: tuple[str, ...] = (
    "bullish",
    "bearish",
    "buy",
    "sell",
    "rally",
    "plunge",
    "surge",
    "soar",
    "crash",
    "explode",
    "rocket",
    "moon",
    "dump",
    "collapse",
    # advice phrasing
    "you should",
    "investors should",
    "consider buying",
    "consider selling",
    "time to buy",
    "time to sell",
    "don't miss",
    "act now",
    "opportunity",  # too interpretive — source must say this word
    "could rise",
    "could fall",
    "likely to",
    "expected to rise",
    "expected to fall",
    "suggests upside",
    "suggests downside",
    "is bullish",
    "is bearish",
    "price target",
    "upgrades",
    "downgrades",
    "outperform",
    "underperform",
)

# Number-like token regex (mirrors copywriter._NUMBER_RE but applied to summaries)
_NUMBER_RE = re.compile(
    r"""
    [+-]?\d+\.?\d*%         # percentage: +0.3% or -1.2%
    |
    \d+\.?\d*x              # multiplier: 2x
    |
    \b\d{2,4}\.\d{2}\b     # price: 226.50
    |
    \b\d+\.\d+\b           # any decimal: 3.1, 0.3
    |
    \b\d{1,}\b             # any bare integer or multi-digit
    """,
    re.VERBOSE,
)

_MAX_SUMMARY_CHARS = 320
_MAX_SUMMARY_SENTENCES = 2


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_number_tokens(text: str) -> list[str]:
    """All number-like tokens in text."""
    return _NUMBER_RE.findall(text)


# Common abbreviations whose periods are NOT sentence boundaries — without
# masking these, "U.S. inflation rose." counts as 2+ sentences and triggers
# needless deterministic fallbacks on exactly the prints this lane targets.
_ABBREV_RE = re.compile(
    r"\b(?:U\.S\.A|U\.S|U\.K|U\.N|E\.U|D\.C|Inc|Corp|Ltd|Co|vs|No|Mr|Mrs|Ms|Dr"
    r"|Jr|Sr|St|Sen|Rep|Gov|Gen|Adm|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct"
    r"|Nov|Dec)\."
)


def _count_sentences(text: str) -> int:
    """Approximate sentence count by terminal punctuation (abbreviation-safe)."""
    masked = _ABBREV_RE.sub(lambda m: m.group(0).replace(".", ""), text.strip())
    # Split on . ! ? followed by whitespace or end-of-string
    sentences = re.split(r"[.!?]+(?:\s|$)", masked)
    return len([s for s in sentences if s.strip()])


# ─────────────────────────────────────────────────────────────────────────────
# validate_summary — adversarial number + stance checker
# ─────────────────────────────────────────────────────────────────────────────

def validate_summary(summary_text: str, item: dict) -> list[str]:
    """Validate a summary against the source item.

    Rules (stricter than validate_copy rule #5):
    1. Every digit-containing token in the summary must appear verbatim in
       item headline + body_snippet. Zero tolerance — no bare-integer exemption.
    2. Stance/interpretation vocab ban (module-level tuple _STANCE_BANNED).
    3. Length: ≤ _MAX_SUMMARY_SENTENCES sentences AND ≤ _MAX_SUMMARY_CHARS chars.
    4. Also runs copywriter.validate_copy (headline="", body=summary_text,
       ctx with type="event", numbers_whitelist from source, emoji_budget=0)
       and merges violations.

    Returns list[str] of violations (empty = clean).
    """
    violations: list[str] = []
    summary_lower = summary_text.lower()

    # Build source corpus for number verification
    source_corpus = (
        (item.get("headline") or "") + " " + (item.get("body_snippet") or "")
    )
    source_numbers = set(_extract_number_tokens(source_corpus))
    # Representation equivalence: official prints spell "0.3 percent" where a
    # summary writes "0.3%" (and vice versa). Admit only the equivalent form of
    # a number ALREADY in the source — this never adds a new digit sequence.
    corpus_lower = source_corpus.lower()
    for tok in list(source_numbers):
        if tok.endswith("%"):
            source_numbers.add(tok[:-1])
        elif re.search(
            re.escape(tok) + r"\s*(?:percent|per cent|percentage points?)\b",
            corpus_lower,
        ):
            source_numbers.add(tok + "%")

    # 1. Number verbatim check (zero tolerance — no bare-integer exemption)
    summary_numbers = _extract_number_tokens(summary_text)
    for token in summary_numbers:
        if token not in source_numbers:
            violations.append(
                f"number '{token}' in summary not present verbatim in source"
            )

    # 2. Stance/interpretation vocab ban
    for word in _STANCE_BANNED:
        word_pat = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
        if re.search(word_pat, summary_lower, re.IGNORECASE):
            # Allow only when the source uses the word STANDALONE too (e.g.
            # source itself says "rally"). Word-boundary here as well —
            # substring presence must not whitelist ("buyback" ⊅ "buy",
            # "sellers" ⊅ "sell").
            if not re.search(word_pat, corpus_lower, re.IGNORECASE):
                violations.append(f"stance/interpretation word '{word}' in summary")

    # 3. Length checks
    if len(summary_text) > _MAX_SUMMARY_CHARS:
        violations.append(
            f"summary too long: {len(summary_text)} chars (max {_MAX_SUMMARY_CHARS})"
        )
    sentence_count = _count_sentences(summary_text)
    if sentence_count > _MAX_SUMMARY_SENTENCES:
        violations.append(
            f"summary too many sentences: {sentence_count} (max {_MAX_SUMMARY_SENTENCES})"
        )

    # 4. Run copywriter.validate_copy on the summary text
    try:
        from engine.marketing.copywriter import validate_copy  # noqa: PLC0415
        cw_violations = validate_copy(
            headline="",
            body=summary_text,
            ctx={
                "type": "event",
                "numbers_whitelist": list(source_numbers),
                "emoji_budget": 0,
            },
        )
        # Filter out cashtag and theme_list rules that don't apply here
        for v in cw_violations:
            if "cashtag" in v or "theme_list" in v:
                continue
            violations.append(f"[validate_copy] {v}")
    except Exception as exc:  # noqa: BLE001
        print(f"[breaking_summary] validate_copy import error: {exc}", file=sys.stderr)

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# LLM-gated summarizer (mirrors copywriter.write_posts_llm gate exactly)
# ─────────────────────────────────────────────────────────────────────────────

def _llm_summarize(item: dict, cfg: dict) -> str | None:
    """Call the LLM to produce a ≤2-sentence restate-only summary.

    Returns the summary string on success, None on any failure.
    NEVER called when MARKETING_LLM_ENABLED is not set (env guard).
    """
    breaking_cfg = cfg if "llm" in cfg else cfg.get("breaking", {})
    llm_cfg = breaking_cfg.get("llm", {})
    enabled = bool(llm_cfg.get("enabled", False))
    env_enabled = os.environ.get("MARKETING_LLM_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled or not env_enabled:
        return None

    try:
        # Resolve model via config.yml llm_models block
        try:
            from lib import config as _config  # noqa: PLC0415
            llm_models = _config.load().get("llm_models", {}) or {}
        except Exception:  # noqa: BLE001
            import yaml as _yaml  # noqa: PLC0415
            _cfgp = Path(__file__).resolve().parents[2] / "config.yml"
            llm_models = (
                (_yaml.safe_load(_cfgp.read_text(encoding="utf-8")) or {})
                .get("llm_models", {}) or {}
            )
        model_key = llm_cfg.get("model_key", "marketing_copy")
        model_id = llm_models.get(model_key, "")
        if not model_id:
            return None

        max_tokens = int(llm_cfg.get("max_tokens", 800))

        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers({}, opus_model=model_id)
        if not providers:
            return None

        system_prompt = (
            "You are a citation rewriter for a market-intelligence publisher. "
            "Your only job: restate the provided headline and snippet in ≤2 "
            "sentences, ≤320 characters. Rules:\n"
            "- ONLY use facts explicitly stated in the source. Never add "
            "interpretation, stance, or numbers not verbatim in the source.\n"
            "- No stance words: bullish, bearish, buy, sell, rally, plunge, etc.\n"
            "- No advice phrasing: 'investors should', 'consider buying', etc.\n"
            "- Do NOT end with a source line — we append that automatically.\n"
            "- Output ONLY the summary text, no JSON, no preamble."
        )

        headline = item.get("headline", "")
        snippet = item.get("body_snippet", "")
        user_msg = f"Source headline: {headline}\n\nSource snippet: {snippet}"

        def _do_call(client, model):
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal"
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            return (text.strip() or None), None

        raw_text, _reason, _provider = llm_auth.make_call(
            providers, _do_call, context="marketing_breaking"
        )
        return raw_text or None

    except Exception as exc:  # noqa: BLE001
        print(f"[breaking_summary] _llm_summarize error: {exc}", file=sys.stderr)
        return None


def _deterministic_summary(item: dict) -> str:
    """Fallback summary: '{headline} — {source_name}'."""
    headline = item.get("headline", "")
    source_name = item.get("source_name", item.get("source", ""))
    return f"{headline} — {source_name}"


_TICKER_STRIP_CAP = 4


def _enrich_tickers(tickers: list[str], root: Path | str | None) -> list[dict]:
    """Attach last close + 1-session % change from the committed close stores.

    The card's related-ticker strip is only as good as its numbers — matched
    tickers with no prices render as bare cashtags, so this pulls the last
    two closes from data/stocks/<T>.parquet (nightly-committed; at poll time
    that is the prior session — honest, not fabricated intraday).

    Fail-soft per ticker: missing store/short history → price/pct None
    (cashtag-only row). Never raises.
    """
    if not tickers:
        return []
    rows: list[dict] = []
    for t in tickers[:_TICKER_STRIP_CAP]:
        price = pct = None
        if root is not None:
            try:
                from engine.marketing.chart_render import load_closes  # noqa: PLC0415
                loaded = load_closes(t, root, n=2)
                if loaded is not None:
                    _dates, closes = loaded
                    if closes:
                        price = float(closes[-1])
                    if len(closes) >= 2 and closes[-2]:
                        pct = (closes[-1] / closes[-2] - 1.0) * 100.0
            except Exception:  # noqa: BLE001
                pass
        rows.append({"ticker": t, "price": price, "pct": pct})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Public summarize_item
# ─────────────────────────────────────────────────────────────────────────────

def summarize_item(
    item: dict,
    cfg: dict,
    *,
    _llm_override: Any = None,  # test seam: pass a callable(item, cfg) -> str|None
) -> dict:
    """Summarize a scored FeedItem; return summary dict.

    Returns:
        {
            summary: str,
            mode: "llm" | "deterministic" | "llm_fallback",
            violations_seen: list[str],
            source_name: str,
            source_tier: str,
            url: str,
            published_at: str,
        }
    """
    source_name = item.get("source_name", item.get("source", ""))
    source_tier = item.get("source_tier", "aggregator")
    url = item.get("url", "")
    published_at = item.get("published_at", "")

    # Try LLM path (or override for tests)
    llm_text: str | None = None
    if _llm_override is not None:
        try:
            llm_text = _llm_override(item, cfg)
        except Exception:  # noqa: BLE001
            llm_text = None
    else:
        llm_text = _llm_summarize(item, cfg)

    violations_seen: list[str] = []
    mode = "deterministic"
    summary = _deterministic_summary(item)

    if llm_text is not None:
        violations = validate_summary(llm_text, item)
        if not violations:
            summary = llm_text
            mode = "llm"
        else:
            violations_seen = violations
            # Validation failed → deterministic fallback
            summary = _deterministic_summary(item)
            mode = "llm_fallback"

    return {
        "summary": summary,
        "mode": mode,
        "violations_seen": violations_seen,
        "source_name": source_name,
        "source_tier": source_tier,
        "url": url,
        "published_at": published_at,
    }


# ─────────────────────────────────────────────────────────────────────────────
# build_breaking_payload — outbox-shaped artifact
# ─────────────────────────────────────────────────────────────────────────────

def build_breaking_payload(
    item: dict,
    cfg: dict,
    *,
    root: Path | str | None = None,
    _llm_override: Any = None,
) -> dict:
    """Build the full outbox-shaped breaking payload.

    Schema (contract with parallel card-renderer agent):
        kind: "breaking"
        id: str
        headline: str
        summary: str
        mode: "llm" | "deterministic" | "llm_fallback"
        source_name: str
        source_tier: str
        url: str
        published_at: str
        event_class: str
        salience: float
        cta_suppress: bool
        tickers: list[str]   # matched tickers from relevance scoring
        card_svg: str        # "" if renderer not available yet
        provenance: {source_url: str, source: str, ingested_at: str}
    """
    summary_result = summarize_item(item, cfg, _llm_override=_llm_override)

    tickers = []
    matched = item.get("matched") or {}
    if isinstance(matched, dict):
        tickers = matched.get("tickers", [])

    # Lazy import of card renderer (degrades gracefully)
    card_svg = ""
    try:
        from engine.marketing.chart_render import render_breaking_card  # noqa: PLC0415
        card_kwargs = dict(
            headline=item.get("headline", ""),
            source_name=item.get("source_name", item.get("source", "")),
            source_tier=item.get("source_tier", "aggregator"),
            published_at=item.get("published_at", ""),
            tickers=_enrich_tickers(tickers, root),
            suppress_cta=bool(item.get("cta_suppress", False)),
            summary=summary_result["summary"],
            logo_root=root,
        )
        try:
            card_svg = render_breaking_card(
                event_class=item.get("event_class"), **card_kwargs
            )
        except TypeError:
            # Older renderer without the event_class kwarg — degrade cleanly.
            card_svg = render_breaking_card(**card_kwargs)
    except Exception:  # noqa: BLE001
        card_svg = ""

    ingested_at = datetime.now(tz=timezone.utc).isoformat()

    return {
        "kind": "breaking",
        "id": item.get("id", ""),
        "headline": item.get("headline", ""),
        "summary": summary_result["summary"],
        "mode": summary_result["mode"],
        "source_name": summary_result["source_name"],
        "source_tier": summary_result["source_tier"],
        "url": summary_result["url"],
        "published_at": summary_result["published_at"],
        "event_class": item.get("event_class", "none"),
        "salience": item.get("salience", 0.0),
        "cta_suppress": bool(item.get("cta_suppress", False)),
        "tickers": tickers,
        "card_svg": card_svg,
        "provenance": {
            "source_url": item.get("url", ""),
            "source": item.get("source", ""),
            "ingested_at": ingested_at,
        },
    }
