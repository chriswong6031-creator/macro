"""engine.marketing.breaking_summary — Summarize-cite lane for breaking items.

Enforces:
- LLM gating EXACTLY mirrors copywriter.write_posts_llm: both
  cfg["breaking"]["llm"]["enabled"] AND env MARKETING_LLM_ENABLED must be set.
  Zero LLM calls in tests (the env guard ensures this).
- validate_summary is STRICTER than validate_copy rule #5: every digit-containing
  token in the summary must appear verbatim in item headline+body_snippet with
  ZERO tolerance (no bare-integer exemption here — this is the citation lane).
- Deterministic fallback on any LLM failure or any validate_summary violation:
  "{source lead sentence} -- {source_name}", or "{headline} -- {source_name}"
  when the packet carries no usable body (see _det_lead_sentence). The join is a
  DOUBLE HYPHEN, never an em dash: the publisher quarantines U+2014.
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
# §3 key-phrase / copypasta law — deterministic runtime checks (M2)
#
# The §3 copy law bans a near-verbatim relay of the source. The prompt text alone
# cannot stop an LLM returning the whole source headline in quotes — that passes
# the number/stance/length gates and ships exactly the relay §3 bans. These
# deterministic checks close it:
#   (a) at most ONE double-quoted span;
#   (b) a quoted span is <= 6 words;
#   (c) near-verbatim guard — the summary must not reproduce the source headline.
#       A byte-identical or trivially-reordered headline fails; a genuine
#       restatement (re-sentenced, re-worded framing) passes.
# ─────────────────────────────────────────────────────────────────────────────

# Double-quoted spans: straight and curly quotes. Non-greedy, no embedded quote.
_QUOTED_SPAN_RE = re.compile(r"[\"“]([^\"“”]+)[\"”]")
_MAX_QUOTED_SPANS = 1
_MAX_QUOTED_WORDS = 6

# Near-verbatim thresholds (see the module unit tests for the tuning cases):
#   token-set Jaccard is the containment proxy the copy law names (< 0.7 passes);
#   the bigram-adjacency gate is the discriminator that lets a real restatement
#   through — a relay preserves the headline's word ADJACENCY, a restatement does
#   not. BOTH must trip for a reject, so a legit paraphrase (which re-orders and
#   re-frames) never fails, while a copy / trivial reorder does.
_NEARVERB_JACCARD = 0.7
_NEARVERB_BIGRAM = 0.5


def _content_tokens(text: str) -> list[str]:
    """Lowercased alphanumeric tokens (surface form preserved — no %<->percent
    normalization here, so a relay's exact surface run is what we compare)."""
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _bigram_overlap(a: list[str], b: list[str]) -> float:
    """Jaccard over adjacent token bigrams — measures preserved word ADJACENCY."""
    ba = set(zip(a, a[1:]))
    bb = set(zip(b, b[1:]))
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def _is_near_verbatim(summary_text: str, headline: str) -> bool:
    """True when the summary reproduces the source headline near-verbatim.

    Both gates must trip: high token-set overlap (Jaccard >= 0.7) AND high
    word-adjacency overlap (bigram Jaccard >= 0.5). A byte-identical or
    trivially-reordered headline trips both; a genuine restatement (extra framing
    words, re-sentenced structure) breaks the adjacency gate and passes.
    """
    st = _content_tokens(summary_text)
    ht = _content_tokens(headline)
    if not st or not ht:
        return False
    return (
        _jaccard(set(st), set(ht)) >= _NEARVERB_JACCARD
        and _bigram_overlap(st, ht) >= _NEARVERB_BIGRAM
    )


# ─────────────────────────────────────────────────────────────────────────────
# validate_summary — adversarial number + stance checker
# ─────────────────────────────────────────────────────────────────────────────

def validate_summary(
    summary_text: str,
    item: dict,
    *,
    max_chars: int = _MAX_SUMMARY_CHARS,
    max_sentences: int = _MAX_SUMMARY_SENTENCES,
    skip_length_check: bool = False,
    is_deterministic_fallback: bool = False,
) -> list[str]:
    """Validate a summary against the source item.

    Rules (stricter than validate_copy rule #5):
    1. Every digit-containing token in the summary must appear verbatim in
       item headline + body_snippet. Zero tolerance — no bare-integer exemption.
    2. Stance/interpretation vocab ban (module-level tuple _STANCE_BANNED).
    3. Length: ≤ max_sentences sentences AND ≤ max_chars chars. Defaults are the
       flash budget (2 sentences, 320 chars); the B2-COPY wire_deep format passes
       the wider two-paragraph budget so a rich source body is not force-failed
       back to the deterministic fallback.
    4. §3 key-phrase / copypasta law (M2): (a) at most ONE double-quoted span;
       (b) a quoted span ≤ 6 words; (c) the summary must not reproduce the source
       headline near-verbatim (byte-identical / trivially-reordered fails, a real
       restatement passes).
    5. Also runs copywriter.validate_copy (headline="", body=summary_text,
       ctx with type="event", numbers_whitelist from source, emoji_budget=0)
       and merges violations.

    is_deterministic_fallback (M2): the fallback is source text with attribution
    by construction — the source's own lead sentence, or, when the packet carries
    no usable body, the headline itself. On that second shape it would always trip
    the near-verbatim guard (c), so when True (c) is skipped: the deterministic
    path is an intentional, honest relay of the source, not an LLM near-copy.
    Checks (a)/(b) still run (a fallback carries no quotes, so they are no-ops).

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

    # 3. Length checks. skip_length_check (wire_deep) defers the char/sentence
    #    budget to wire_format.validate_length, which enforces the 400-700 char
    #    two-paragraph budget on the FINAL composed post.
    if not skip_length_check:
        if len(summary_text) > max_chars:
            violations.append(
                f"summary too long: {len(summary_text)} chars (max {max_chars})"
            )
        sentence_count = _count_sentences(summary_text)
        if sentence_count > max_sentences:
            violations.append(
                f"summary too many sentences: {sentence_count} (max {max_sentences})"
            )

    # 4. §3 key-phrase / copypasta law (M2) — deterministic runtime checks.
    #    (a) at most ONE double-quoted span; (b) each ≤ 6 words.
    quoted_spans = _QUOTED_SPAN_RE.findall(summary_text)
    if len(quoted_spans) > _MAX_QUOTED_SPANS:
        violations.append(
            f"too many quoted spans: {len(quoted_spans)} (max {_MAX_QUOTED_SPANS})"
        )
    for span in quoted_spans:
        n_words = len(span.split())
        if n_words > _MAX_QUOTED_WORDS:
            violations.append(
                f"quoted span too long: {n_words} words (max {_MAX_QUOTED_WORDS}) — "
                f"quote the source's strongest SHORT phrase, never a whole sentence"
            )
    #    (c) near-verbatim guard vs the SOURCE HEADLINE. The deterministic fallback
    #    IS the headline (with attribution) by construction, so it is exempt.
    if not is_deterministic_fallback:
        headline = str(item.get("headline") or "")
        if headline and _is_near_verbatim(summary_text, headline):
            violations.append(
                "summary near-verbatim of source headline — restate in your own "
                "words, do not relay the headline"
            )

    # 5. Run copywriter.validate_copy on the summary text
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
        # Filter out cashtag and theme_list rules that don't apply here. In
        # wire_deep mode also drop validate_copy's 275-char social-post length
        # rule — the wide two-paragraph budget is enforced separately (as above),
        # and validate_copy's cap would force every deep body to the fallback.
        for v in cw_violations:
            if "cashtag" in v or "theme_list" in v:
                continue
            if skip_length_check and "too long" in v:
                continue
            violations.append(f"[validate_copy] {v}")
    except Exception as exc:  # noqa: BLE001
        print(f"[breaking_summary] validate_copy import error: {exc}", file=sys.stderr)

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# LLM-gated summarizer (mirrors copywriter.write_posts_llm gate exactly)
# ─────────────────────────────────────────────────────────────────────────────

def _llm_summarize(
    item: dict,
    cfg: dict,
    wire: dict | None = None,
    repair: tuple[str, list[str]] | None = None,
) -> str | None:
    """Call the LLM to produce a ≤2-sentence restate-only summary.

    `repair` (2026-08-04): a ``(previous_text, violations)`` pair turns this into
    a SECOND, corrective attempt — the model is shown its own rejected draft and
    the validator's exact complaints. See :func:`summarize_item` for why one
    retry is worth a call and why there is not a third.

    Returns the summary string on success, None on any failure.
    NEVER called when MARKETING_LLM_ENABLED is not set (env guard).

    `wire` (B2-COPY, optional): when supplied, the summarizer runs in WIRE VOICE
    mode — the model_key is resolved per salience TIER (sonnet flagship / haiku
    volume) via wire_voice.resolve_model_key, and the §3 key-phrase selection law
    is appended to the system prompt. The numbers-whitelist + AI-tell validation
    still runs after generation (this only STEERS the model, never relaxes a gate).
    Absent => the plain B1 breaking summarizer (unchanged).
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
        if wire is not None:
            try:
                from engine.marketing.wire_voice import resolve_model_key  # noqa: PLC0415
                model_key = resolve_model_key(item, cfg=wire)
            except Exception:  # noqa: BLE001
                pass
        model_id = llm_models.get(model_key, "")
        if not model_id:
            return None

        max_tokens = int(llm_cfg.get("max_tokens", 800))

        # CHATGPT-FIRST (operator directive 2026-07-29, recorded on
        # config/marketing.yml copywriter.llm): the attached Codex account leads,
        # Claude follows as the balanced fallback drawn through the key_pool load
        # balancer. Sol — the breaking rewriter produces the published sentence.
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(
            {
                "usage_lane": llm_cfg.get("usage_lane", "marketing-breaking"),
                "oauth_pool_lane": llm_cfg.get("oauth_pool_lane", "marketing-breaking"),
                "provider_order": llm_cfg.get("provider_order")
                or ["codex", "oauth", "anthropic", "deepseek"],
                "codex_source_model": llm_cfg.get("codex_source_model", "gpt-5.6-sol"),
                "codex_reasoning_effort": llm_cfg.get("codex_reasoning_effort", "medium"),
                # LOCAL MODEL RUNG (2026-08-04). Forwarded so a config that lists
                # `ollama` in provider_order actually reaches the local box —
                # build_providers never inserts this rung implicitly, and without
                # these keys the entry silently resolved to nothing.
                #
                # It belongs LAST and only last. A local 9B is a weaker writer
                # than any hosted rung, so it must never take work they can do;
                # but when every hosted rung has failed the alternative is not a
                # better sentence, it is the deterministic relay of a raw RSS
                # title — the exact path that put a publisher's page furniture on
                # the timeline. A restatement from a small local model is a
                # strictly better last resort than no restatement at all.
                "ollama_base_url": llm_cfg.get("ollama_base_url"),
                "ollama_base_url_env": llm_cfg.get("ollama_base_url_env"),
                "ollama_model": llm_cfg.get("ollama_model"),
                "ollama_timeout_s": llm_cfg.get("ollama_timeout_s"),
                "ollama_num_ctx": llm_cfg.get("ollama_num_ctx"),
            },
            opus_model=model_id,
        )
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
            "- Do NOT end with a source line; we append that automatically.\n"
            "- Output ONLY the summary text, no JSON, no preamble."
        )
        # B2-COPY wire voice: append the §3 key-phrase selection law + (for the
        # wire_deep format) the two-paragraph instruction. Steering only — the
        # numbers whitelist + AI-tell validation still runs after generation.
        if wire is not None:
            try:
                from engine.marketing.wire_voice import (  # noqa: PLC0415
                    key_phrase_prompt_law, wire_deep_prompt_law,
                )
                if str(wire.get("_format", "flash")) == "wire_deep":
                    system_prompt += "\n\n" + wire_deep_prompt_law()
                else:
                    system_prompt += "\n\n" + key_phrase_prompt_law()
            except Exception:  # noqa: BLE001
                pass

        headline = item.get("headline", "")
        snippet = item.get("body_snippet", "")
        user_msg = f"Source headline: {headline}\n\nSource snippet: {snippet}"
        if repair is not None:
            prev, violations = repair
            user_msg += (
                "\n\nYour previous attempt was REJECTED by the copy validator.\n"
                f"Rejected draft: {prev}\n"
                "Validator complaints:\n"
                + "\n".join(f"  - {v}" for v in list(violations)[:6])
                + "\n\nWrite a NEW summary that fixes every complaint. Do not "
                  "argue with the validator and do not explain the change — "
                  "output only the corrected summary text."
            )

        def _do_call(client, model):
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal", resp
            text = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            return (text.strip() or None), None, resp

        raw_text, _reason, _provider = llm_auth.make_call(
            providers, _do_call, context="marketing_breaking"
        )
        return raw_text or None

    except Exception as exc:  # noqa: BLE001
        print(f"[breaking_summary] _llm_summarize error: {exc}", file=sys.stderr)
        return None


#: A lead sentence shorter than this is a byline or a datentline fragment ("By
#: Reuters Staff", "WASHINGTON"), not a fact worth relaying.
_DET_LEAD_MIN_WORDS = 6
#: And one longer than this is a paragraph, which blows the flash budget the
#: composed post is measured against (wire_format.flash_budget, 280 chars).
_DET_LEAD_MAX_CHARS = 200

#: How many opening sentences :func:`_det_lead_sentence` may consider before it
#: gives up. Three, because a wire item's useful lead is in the first paragraph
#: or nowhere, and scanning further starts relaying a source's context section as
#: if it were their news. See the scan comment for why this is a scan and never a
#: truncation.
_DET_LEAD_SCAN_SENTENCES = 3

_DET_DASHES = ("—", "–", "―")     # em dash, en dash, horizontal bar
_DET_WS_RE = re.compile(r"\s+")


def _lead_completes_headline(lead: str, headline: str) -> bool:
    """Is the headline a TRUNCATION of this lead — the same statement, cut short?

    The X-relay feed builds ``headline = snippet[:120]`` — a raw slice that can
    end mid-clause or mid-word — while the lead sentence is that same statement
    complete. The near-verbatim guard exists because relaying an echo gains
    nothing, but on this shape it INVERTED its own purpose: rejecting the lead
    sent the fallback to the headline, i.e. it PREFERRED the truncated form over
    the complete sentence already in the packet.

    True when the headline (normalised exactly as the lead was — dashes to the
    house double hyphen, whitespace collapsed) is a strict character prefix of
    the lead AND the extension carries content beyond trailing punctuation. The
    punctuation clause keeps "X." vs "X" a plain echo (headline relay, pinned in
    tests/test_marketing_breaking.py) rather than a "completion" of one period.
    """
    norm_head = str(headline or "")
    for dash in _DET_DASHES:
        norm_head = norm_head.replace(dash, " -- ")
    norm_head = _DET_WS_RE.sub(" ", norm_head).strip()
    if not norm_head or not lead.startswith(norm_head):
        return False
    return bool(lead[len(norm_head):].strip(" .!?,;:"))


def _det_lead_sentence(item: dict) -> str:
    """The source's own first body sentence when it ADDS to the headline, else "".

    W1.5: the keyless body used to be ``{headline} -- {source_name}``, i.e. the
    headline verbatim. The emitted post is ``headline + blank line + body``
    (``outbox.compose_text``), so every keyless press item shipped the SAME
    SENTENCE TWICE in one post -- the headline, then the headline again wearing
    an attribution. ``body_snippet`` (up to 600 chars of the real article, which
    the LLM prompt already reads) is non-echo content ALREADY IN THE PACKET, so
    the fallback relays that instead. Nothing is invented: this is source text,
    the same trust level as the headline it replaces.

    Returns "" -- and the caller keeps the old headline relay -- unless the
    sentence is substantive (>= _DET_LEAD_MIN_WORDS words), short enough to fit
    the flash budget, and NOT a restatement of the headline (the same
    :func:`_is_near_verbatim` gate the LLM path answers to; a wire mirror whose
    body_snippet simply repeats its own headline gains us nothing). ONE carve-out
    (2026-08-02): when the headline is a TRUNCATION of the lead — the X-relay
    ``snippet[:120]`` shape — the lead is the same statement completed, so it is
    relayed rather than rejected (:func:`_lead_completes_headline`); falling back
    to the headline there would prefer the cut-off form over the complete one.

    Em/en dashes are normalised to the house double hyphen. That is punctuation,
    not a fact: source prose is not written to our language law, and the
    publisher's last gate QUARANTINES U+2014, so relaying one verbatim would
    kill the item (tests/test_marketing_press_copy.py pins that choke point).
    """
    raw = str(item.get("body_snippet") or "")
    if not raw.strip():
        return ""
    for dash in _DET_DASHES:
        raw = raw.replace(dash, " -- ")
    text = _DET_WS_RE.sub(" ", raw).strip()
    # SCAN THE OPENING SENTENCES, DON'T STOP AT THE FIRST (2026-08-04 postmortem).
    #
    # This used to take sentence 1 and return "" if it did not fit the budget,
    # which made the fallback WORSE the richer the source: ForexLive handed us a
    # real analyst paragraph whose first sentence ran 274 characters against a
    # 200 cap, so the whole paragraph was discarded and the post fell back to
    # relaying the raw RSS title. On the live feed that cap bit 12 of 25 items.
    # A source that wrote three good sentences should not be punished for
    # putting a long one first — so the scan walks the opening sentences and
    # takes the first that FITS.
    #
    # SCAN, NEVER TRUNCATE. Cutting a sentence at a clause boundary is how a
    # conditional loses its condition ("the Fed is expected to cut in September,
    # unless inflation reaccelerates"), and a wire desk that clips the qualifier
    # off a hedge is inventing a claim. A sentence either fits whole or is
    # skipped whole.
    masked = _ABBREV_RE.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    sentences = re.split(r"(?<=[.!?])\s", masked)[:_DET_LEAD_SCAN_SENTENCES]
    headline = str(item.get("headline") or "").strip()

    for raw_sentence in sentences:
        lead = _DET_WS_RE.sub(" ", raw_sentence.replace("\x00", ".")).strip()
        if not lead:
            continue
        if len(lead) > _DET_LEAD_MAX_CHARS or len(lead.split()) < _DET_LEAD_MIN_WORDS:
            continue
        if headline and _is_near_verbatim(lead, headline) \
                and not _lead_completes_headline(lead, headline):
            continue
        # THE SOURCE'S OWN PAGE VOICE IS NOT OURS. "On the wires: I'll have more
        # to come on this separately, details etc." shipped on the flagship on
        # 2026-08-03 — the ForexLive author's first person, relayed as our line
        # 2, promising a follow-up we were never going to write. This is the one
        # path that puts SOURCE PROSE (not a restatement of it) into a post, so
        # it is the path that has to screen for prose written to a page we are
        # not on. Fail-soft: a broken hygiene import costs the screen, never the
        # wire.
        try:
            from engine.marketing import relay_hygiene as _rh  # noqa: PLC0415
            if _rh.body_defects(lead):
                continue
        except Exception:  # noqa: BLE001
            pass
        return lead
    return ""


def _deterministic_summary(item: dict) -> str:
    """Fallback body: the source's lead sentence, attributed -- else the headline.

    B1: the source clause joins on a DOUBLE HYPHEN. This string is the body that
    ships whenever the LLM is disarmed or fails, so an em dash here is not a style
    slip: the publisher's last-gate language screen quarantines U+2014, which made
    the fallback path unpostable. The double hyphen is also the corpus wire form
    ("...ENVIRONMENTAL REVIEWS -- WSJ").

    The lead sentence comes from :func:`_det_lead_sentence`, which returns "" when
    the packet has no usable body -- and then this falls back to the historical
    ``{headline} -- {source_name}`` relay, which is still the honest thing to send
    when the headline is all we were given.
    """
    headline = item.get("headline", "")
    source_name = item.get("source_name", item.get("source", ""))
    return f"{_det_lead_sentence(item) or headline} -- {source_name}"


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
    wire: dict | None = None,   # B2-COPY: wire-voice tier/prompt config (optional)
) -> dict:
    """Summarize a scored FeedItem; return summary dict.

    Returns:
        {
            summary: str,
            mode: "llm" | "llm_repaired" | "deterministic" | "llm_fallback",
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
        llm_text = _llm_summarize(item, cfg, wire)

    violations_seen: list[str] = []
    mode = "deterministic"
    summary = _deterministic_summary(item)

    # B2-COPY: the wire_deep format is two short paragraphs (400-700 chars), so it
    # validates against the wider budget — otherwise a rich source body is force-
    # failed back to the deterministic fallback and wire_deep can never fill.
    is_deep = (isinstance(wire, dict)
               and str(wire.get("_format", "flash")) == "wire_deep")
    max_chars = _MAX_SUMMARY_CHARS
    max_sentences = _MAX_SUMMARY_SENTENCES
    if is_deep:
        max_chars = int(wire.get("deep_summary_max_chars", 700))
        max_sentences = int(wire.get("deep_summary_max_sentences", 6))

    if llm_text is not None:
        violations = validate_summary(
            llm_text, item, max_chars=max_chars, max_sentences=max_sentences,
            skip_length_check=is_deep,
        )
        if not violations:
            summary = llm_text
            mode = "llm"
        else:
            violations_seen = violations
            # ── ONE REPAIR ATTEMPT (2026-08-04) ───────────────────────────────
            # A rejected draft used to go straight in the bin, and the bin's
            # replacement is the deterministic relay — which on a thin packet is
            # the raw RSS title, page furniture and all. That is the single
            # biggest source of unwritten posts on this lane: the summarizer was
            # armed, paid for, and its output discarded without ever being told
            # what was wrong with it.
            #
            # The validator's complaints are SPECIFIC ("number 4,070 not in
            # source", "summary near-verbatim of source headline"), which makes
            # them a usable instruction rather than a score. One retry, never
            # two: a second failure means the packet cannot support a compliant
            # restatement, and at that point more calls buy drift, not quality.
            #
            # Skipped for the test seam (_llm_override), which is a pure
            # callable with no repair contract.
            repaired: str | None = None
            if _llm_override is None:
                repaired = _llm_summarize(
                    item, cfg, wire, repair=(llm_text, violations)
                )
            if repaired is not None:
                repair_violations = validate_summary(
                    repaired, item, max_chars=max_chars,
                    max_sentences=max_sentences, skip_length_check=is_deep,
                )
                if not repair_violations:
                    summary = repaired
                    mode = "llm_repaired"
                else:
                    violations_seen = violations + [
                        f"repair:{v}" for v in repair_violations
                    ]
                    summary = _deterministic_summary(item)
                    mode = "llm_fallback"
            else:
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
# Restatement gates — "only use illustrations when you have valuable details"
# ─────────────────────────────────────────────────────────────────────────────
#
# Operator defect report 2026-08-02, from live posts. Two distinct failures that
# share one cause: nothing ever compared the card against the words beside it.
#
#   (2) The card printed the same sentence twice. For an X-relay item the feed
#       builds headline = snippet[:120] and body_snippet = the same snippet, so
#       the card's headline and its summary were one string rendered at two
#       sizes.
#   (3) The card restated the post. The gold flash shipped as "On the tape:
#       <headline> -- <credit>" with a card whose only content was <headline>.
#       The reader got the same sentence in two places and learned nothing from
#       the picture.
#
# Both are decided by containment, NOT similarity: the question is "is the card's
# content already IN the other text", and the gold case is a strict subset, which
# a symmetric measure (Jaccard) would score as merely similar. Containment over
# the SHORTER token set answers the question asked.

#: Tokens carrying no information for the restatement test — dropping them stops
#: a shared scaffold of filler from either masking a restatement or inventing a
#: difference. Deliberately small: this is a stop list, not a stemmer.
_RESTATE_STOP: frozenset[str] = frozenset({
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "to", "was",
    "were", "with", "after", "says", "said", "this", "will", "would",
})

#: Above this share of the shorter token set appearing in the longer one, the
#: two texts are the same statement. 0.70 was picked against the real outbox:
#: it drops the restating flashes while keeping every genuinely distinct pair.
_RESTATE_THRESHOLD = 0.70

_RESTATE_WORD_RE = re.compile(r"[a-z0-9$%.]+")

# THE CASHTAG MIRROR IS GONE (2026-08-05). This module used to carry a copy of
# press_lane._CASHTAG_RE so card_earns_attachment could wave every ticker post
# through untested, on the grounds that scripts/marketing_publisher quarantines
# a bare `breaking` post that names tickers. That short-circuit ran BEFORE any
# content check, so a ticker in the copy exempted the card from the card-value
# law entirely — and a ticker is not evidence a card adds value. The publisher's
# quarantine still exists and still fires; the difference is that a restating
# ticker post is now HELD for review instead of shipping a doubled card. The
# regex itself lives on in press_lane (its own gate at :1204 reads it) and in
# marketing_publisher; nothing here reads one, so nothing here defines one.


def restatement_tokens(text: str) -> frozenset[str]:
    """Normalized content tokens for the restatement test. Deterministic.

    Lower-cases, drops emoji/punctuation, strips a leading wire opener and the
    trailing credit clause, and removes stop words. Numbers are KEPT and keep
    their decimal point ("30.32b" stays one token), because a figure is exactly
    the kind of detail that makes two texts genuinely different.
    """
    s = str(text or "").lower()
    # A wire opener and our own credit are scaffolding, not content: leaving them
    # in makes an identical pair look 15% different and defeats the gate.
    s = re.sub(r"^\s*(?:just\s*in|breaking|urgent|alert|developing|flash)\s*[:\-]+\s*",
               " ", s)
    s = re.sub(r"\s+--\s+.*$", " ", s)
    s = re.sub(r"^\s*(?:on the tape|now crossing|heads up)\s*[.:]\s*", " ", s)
    toks = {
        t.strip(".") for t in _RESTATE_WORD_RE.findall(s)
        if t.strip(".") and t.strip(".") not in _RESTATE_STOP
    }
    return frozenset(t for t in toks if len(t) > 1 or t.isdigit())


def containment(inner: str, outer: str) -> float:
    """Share of *inner*'s content tokens that also appear in *outer*. DIRECTIONAL.

    1.0 means "inner says nothing outer does not". The direction is the whole
    point, and getting it backwards is how a gate ends up refusing the cards it
    should keep. Read it as a sentence and the two questions come apart:

      containment(body, post) — does the card BODY add anything to the post?
        1.0 = no. This is the restating-body veto.
      containment(post, body) — is the whole POST inside the card body?
        1.0 on a body that quotes the post and then adds three new figures,
        which is a card we WANT. Never use this one to judge a body.

    Returns 0.0 when either side has no content tokens: an empty side cannot be
    a restatement, and failing open here would drop cards for having no words
    to compare.
    """
    ti, to = restatement_tokens(inner), restatement_tokens(outer)
    if not ti or not to:
        return 0.0
    return len(ti & to) / len(ti)


def restatement_score(a: str, b: str) -> float:
    """Share of the SHORTER text's tokens that also appear in the longer one.

    1.0 means one text says nothing the other does not. Symmetric in its
    arguments — it always measures the smaller token set against the larger, so
    it answers "are these the same statement" without committing to a direction.
    Use :func:`containment` when the direction is the question.
    """
    ta, tb = restatement_tokens(a), restatement_tokens(b)
    if not ta or not tb:
        return 0.0
    return containment(a, b) if len(ta) <= len(tb) else containment(b, a)


class _CardHandleLeak(Exception):
    """A card param carried a foreign @handle — the render is abandoned."""


#: WHY A PAYLOAD CARRIES NO CARD, recorded in `provenance.card_absent_reason`.
#:
#: `card_svg == ""` used to reach the dispatch with no reason attached, and the
#: dispatch has three opposite readings to choose between:
#:
#:   * (no key)        — no card was attempted, or the card is attached. The
#:                       post never claimed a picture.
#:   * RENDER_DEGRADED — a card WAS attempted and the renderer fell through its
#:                       outer fail-soft. An ENVIRONMENT fault: the next tick
#:                       may well succeed, so press_lane refuses the emission
#:                       transiently rather than shipping a ticker post bare
#:                       into the publisher's quarantine.
#:   * POLICY_REFUSED  — a card was built and may not lawfully be drawn (a
#:                       foreign @handle reached a card param). A retry redraws
#:                       exactly the same card, so this is NOT transient.
#:
#: What this key is NOT: a card the value gate withheld for adding nothing. That
#: one is `card_withheld_for_value`, set by press_lane, and it is the only one of
#: the four that stands a downstream gate down.
_CARD_ABSENT_RENDER_DEGRADED = "render_degraded"
_CARD_ABSENT_POLICY_REFUSED = "policy_refused"


def _card_param_violations(card_kwargs: dict) -> list[str]:
    """Foreign @mentions in anything the card would draw. [] = clean.

    Delegates to copywriter.card_input_violations (same allowlist and the same
    regex as the publisher's post-text gate, so the two cannot drift). Fail-SOFT
    on any import/lookup error: this is a backstop behind ingestion-time
    de-handling, and it must never be the reason a card fails to build.
    """
    try:
        from engine.marketing.copywriter import (  # noqa: PLC0415
            card_input_violations,
        )
    except Exception:  # noqa: BLE001
        return []
    try:
        screened = {
            k: v for k, v in card_kwargs.items()
            if k not in ("logo_root", "cta", "suppress_cta")
        }
        return card_input_violations(**screened)
    except Exception:  # noqa: BLE001
        return []


def summary_earns_the_card(headline: str, summary: str) -> bool:
    """Does this summary tell the card anything its headline does not? (defect 2)

    False means the renderer is handed summary=None and omits the block cleanly,
    rather than printing one sentence at two sizes.
    """
    if not str(summary or "").strip():
        return False
    return restatement_score(headline, summary) < _RESTATE_THRESHOLD


def headline_earns_its_line(headline: str, body: str) -> bool:
    """Does the headline prefix tell the POST anything its body does not?

    The post-text sibling of :func:`summary_earns_the_card`, asked by the X
    clamp (``wire_format.clamp_for_x``) BEFORE it joins ``headline + blank line
    + body``. For an X-relay item the deterministic body carries the same
    statement the headline does (the feed builds ``headline = snippet[:120]``
    and ``body_snippet`` = the same snippet), so the joined form printed one
    sentence twice — and the W1.5 echo guard's own fallback
    (``"{headline} -- {source}"``) IS the headline again, which made the guard
    the producer of the very shape it was built to stop.

    False = the headline says nothing the body does not; the post ships ONE
    statement — the body, which keeps the opener, the corroboration credit and
    the tape stamp, and is the exact string the news rail already displays for
    an emitted item. An empty headline has no line to earn (False); an empty
    body cannot absorb one (True). Same containment measure and threshold as
    the card gates, so every restatement surface answers the same question the
    same way.
    """
    if not str(headline or "").strip():
        return False
    if not str(body or "").strip():
        return True
    return restatement_score(headline, body) < _RESTATE_THRESHOLD


def card_earns_attachment(
    post_text: str,
    headline: str,
    summary: str = "",
    tickers: "list[dict] | None" = None,
) -> tuple[bool, str]:
    """Does the card carry information beyond the post text? (defect 3)

    Returns ``(attach?, reason)``. The reason is recorded on the emission
    (``source.card_dropped``) and announced by press_lane, so a dropped card is
    never silent.

    THE GATE MUST BE ABLE TO SAY NO — that is the 2026-08-05 root cause. This
    function used to be APPROVAL-ONLY: its summary branch returned True the
    moment the card body said something the HEADLINE did not, and no branch
    anywhere returned False on the strength of the body. Control then fell
    through to a headline-vs-post comparison and attached. So the India card,
    whose hero was the tweet VERBATIM, shipped on the back of a body its own
    headline happened to differ from, and the ZeroHedge and ForexLive cards
    shipped bodies that were the tweet restated in bigger type. Three surfaces,
    one fact (operator law L1: the tweet, the card headline and the card body
    must not restate each other).

    ORDER MATTERS — THE VETOES RUN FIRST. An affirmative reason cannot buy back
    a surface that restates the post; a card is not 2/3 lawful.

      1. no post text                      -> attach (nothing to compare)
      2. VETO: the hero IS the post again   -> text-only, whatever the body says
      3. VETO: the body adds nothing to it  -> text-only, whatever the hero says
      4. the body adds detail               -> attach
      5. the tape strip carries a reading   -> attach
      6. the hero states something new      -> attach
      7. otherwise                          -> text-only (a card of pure chrome)

    THE TWO VETOES ASK DIFFERENT QUESTIONS, and that asymmetry is load-bearing
    rather than an oversight:

      * the HERO is judged by NEAR-EQUALITY — ``containment(post, hero)`` AND
        ``containment(hero, post)`` both at threshold. It must cover the post
        AND add nothing to it. One direction alone is a strictly wider net than
        the defect: covering-alone drops the additive hero (a terse tweet under
        a hero carrying the figure), adding-nothing-alone is already asked at
        step 6, where a body or a tape reading can lawfully outvote it.
      * the BODY is judged by ``containment(body, post)`` alone — does the body
        add anything the post lacks? Judging it as near-equality would let a
        body that restates the post and pads it with filler through, and judging
        it the other way round would refuse a body that quotes the post and then
        adds prior and consensus, the single most valuable card this lane makes.

    Both texts must be WHAT THE READER SEES. `headline` is the card's rendered
    hero (payload["card_headline"]), not the raw wire field, and `summary` is
    the text the card actually DREW (payload["card_summary_drawn"]) — the box
    holds what chart_render.card_summary_budget_chars() measures (129 chars on
    the 1080 card) against a producer budget of 320, so scoring the full
    body judged a paragraph the card never showed.

    THERE IS NO CASHTAG SHORT-CIRCUIT. A ``$TICKER`` in the copy used to return
    True before any content check, which exempted every ticker post from the
    gate wholesale. A ticker is not evidence a card adds value.

    A VETO SHIPS THE POST TEXT-ONLY. IT DOES NOT KILL THE POST. Removing the
    cashtag short-circuit without saying so downstream did kill it, twice over,
    and both paths were measured end to end on 2026-08-05: value_gate rested a
    breaking post's `hard` proof on HAVING media, so a withheld card came back
    `proof:below_hard` and press_lane refused the item; and with a digit present
    to clear that, marketing_publisher._bare_cashtag_post read the empty media
    list as "this ticker post owes a picture" and quarantined it — terminal,
    re-creating the 2026-07-30 outage the operator's "I'd rather you destroy the
    entire engine than ship text only" was about, from the opposite direction.
    Both gates now read the WITHHELD state (press_lane stamps
    ``source.card_withheld_for_value``), because "we chose not to print a
    redundant picture" and "no picture was ever built" are opposite facts about
    a post's evidence. Any new consumer of ``media == []`` inherits that duty.
    """
    post = str(post_text or "").strip()
    if not post:
        # Nothing to compare against: keep the card rather than strip a post of
        # its only content.
        return True, "no post text to compare"

    head = str(headline or "").strip()
    body = str(summary or "").strip()

    # ── VETO 1 — the card HERO reproduces the post ───────────────────────────
    # Nothing used to ask this. It is exactly the India post: card headline ==
    # tweet, printed at poster scale beside the tweet that already said it.
    #
    # NEAR-EQUALITY, NOT ONE-WAY CONTAINMENT (fixed 2026-08-06). This asked
    # `containment(post, head) >= 0.70` alone — "is the whole post inside the
    # hero" — which is 1.0 whenever the hero is a strict SUPERSET of a terse
    # post. That is the ADDITIVE hero, the best card this lane draws, and the
    # veto was dropping it while logging "the hero is the tweet again" about a
    # hero that said strictly more. Measured on the shipped code:
    #
    #   post "Nvidia beats. -- wire reports"
    #   hero "Nvidia beats on revenue at $46.7B and guides Q3 above the street"
    #     -> 1.00, DROPPED, on a hero carrying a figure the tweet never had.
    #
    # The defect the veto exists for (the India card) is hero == post, i.e.
    # near-equality in BOTH directions. So both questions have to be asked: the
    # hero must cover the post AND add nothing to it. A hero that covers the
    # post while adding a figure is the card, not the defect.
    if head:
        hero_covers = containment(post, head)   # is the whole post in the hero?
        hero_adds = containment(head, post)     # does the hero add anything?
        if hero_covers >= _RESTATE_THRESHOLD and hero_adds >= _RESTATE_THRESHOLD:
            # BOTH numbers, because both are now the reason. The old line named
            # only the covering share and asserted "the hero is the tweet again"
            # on heroes that said strictly more — an operator-facing explanation
            # that misdescribed the drop. It is only printed on near-equality
            # now, so it is finally true.
            return False, (
                f"card headline restates the post text ({hero_covers:.2f} of "
                f"the post is in the hero, {hero_adds:.2f} of the hero is "
                f"already posted) — the hero is the tweet again"
            )

    # ── VETO 2 — the card BODY adds nothing the post does not already say ────
    if body:
        body_score = containment(body, post)
        if body_score >= _RESTATE_THRESHOLD:
            return False, (
                f"card body restates the post text ({body_score:.2f} of its "
                f"words already posted) — one fact, one surface"
            )

    # ── Affirmative reasons, in descending order of what they give a reader ──
    if body and summary_earns_the_card(head, body):
        return True, "card summary adds detail the post text does not carry"

    rows = tickers if isinstance(tickers, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("price", "pct"):
            try:
                val = float(row.get(key))
            except (TypeError, ValueError):
                continue
            if val == val and val not in (float("inf"), float("-inf")):
                return True, "card carries a tape reading (price/move) the copy lacks"

    # The hero survived veto 1, so it is not the whole post — but a hero can
    # still be a bare LABEL whose every word the post already carries, and with
    # no body and no tape that card is a caption in a frame. Attach only when
    # the hero itself says something new.
    if head:
        hero_adds = containment(head, post)
        if hero_adds < _RESTATE_THRESHOLD:
            return True, (
                f"card headline states something the post text does not "
                f"({hero_adds:.2f} of the hero is already posted)"
            )
        return False, (
            f"card headline adds nothing to the post ({hero_adds:.2f} of the "
            f"hero is already posted) and there is no summary or tape reading"
        )

    # No hero, no body, no tape: the card is masthead, rule and footer. Chrome
    # is not information, and this is the branch that keeps an empty-headline
    # item from attaching on a vacuous "the headline differs" reason.
    return False, "card carries no headline, no summary and no tape reading"


# ─────────────────────────────────────────────────────────────────────────────
# build_breaking_payload — outbox-shaped artifact
# ─────────────────────────────────────────────────────────────────────────────

def build_breaking_payload(
    item: dict,
    cfg: dict,
    *,
    root: Path | str | None = None,
    _llm_override: Any = None,
    wire: dict | None = None,   # B2-COPY: wire-voice tier/prompt config (optional)
) -> dict:
    """Build the full outbox-shaped breaking payload.

    Schema (contract with parallel card-renderer agent):
        kind: "breaking"
        id: str
        headline: str        # verbatim from the wire (may be a whole post)
        card_headline: str   # sentence-bounded hero the card renders (W4g)
        summary: str
        mode: "llm" | "llm_repaired" | "deterministic" | "llm_fallback"
        source_name: str
        source_tier: str
        url: str
        published_at: str
        event_class: str
        salience: float
        cta_suppress: bool
        tickers: list[str]   # matched tickers from relevance scoring
        card_svg: str        # "" if renderer not available yet
        card_summary: str|None  # what the CARD was given (None = dropped as a
                                # restatement of the headline)
        card_summary_drawn: str # what the card actually DREW of it (whole
                                # sentences that fit the box; "" = no second
                                # voice was drawn at all). THIS is the string
                                # card_earns_attachment scores — the box holds
                                # what card_summary_budget_chars() measures
                                # (129) and the producer writes 320, so
                                # scoring card_summary judged text no reader saw.
        card_tickers: list[dict]  # enriched rows the card's tape strip drew
        provenance: {source_url: str, source: str, ingested_at: str}

    THERE IS NO `citation` KWARG. One was threaded press_lane ->
    build_breaking_payload -> render_breaking_card -> _break_chip_label so a
    source_authority "no credit" ruling made for the POST BODY would bind the
    picture too. The chip now carries the TIER and never a name
    (chart_render._break_chip_label), so the only output that ruling could
    change no longer exists — mutation-verified before removal: deleting the
    branch it fed changed no test's answer. A kwarg kept "in case" is a dead
    field, and this repo has been bitten by those.
    """
    summary_result = summarize_item(item, cfg, _llm_override=_llm_override, wire=wire)

    tickers = []
    matched = item.get("matched") or {}
    if isinstance(matched, dict):
        tickers = matched.get("tickers", [])

    # ── Upstream card-headline gate (W4g) ────────────────────────────────────
    # The wire's `headline` field is whatever the source carried. For a relay of
    # a Truth Social post that is the ENTIRE post: the 2026-08-02 Iran item
    # arrived 814 characters long, and the card rendered ~156 of them before an
    # ellipsis — cutting mid-sentence, before any actual news. The card gets a
    # DERIVED headline (leading whole sentences, the source's own words, no
    # rewrite, no case change, no ellipsis — relay, never editorialize; F6
    # sentence-case compression, never ALL-CAPS synthesis). `headline` itself is
    # left untouched so the post-text lane's composition is byte-unchanged.
    raw_headline = str(item.get("headline", "") or "")
    card_headline = raw_headline
    headline_chars_dropped = 0
    # DEFECT 2 — the card printed one sentence twice. The summary reaches the
    # renderer only when it says something the headline does not; the POST body
    # keeps the full summary either way (this gate is about what the picture
    # shows, never about what we publish). Decided OUTSIDE the renderer's
    # try/except so the dispatch gate downstream still sees what the card was
    # given even when the render itself degraded. Gated against the RAW headline
    # (the derived W4g hero is a whole-sentence prefix of it, so containment
    # over the shorter token set answers the same for either form) — the raw
    # form is the one that exists before the renderer import can fail.
    card_summary = (
        summary_result["summary"]
        if summary_earns_the_card(raw_headline, summary_result["summary"])
        else None
    )
    card_tickers: list[dict] = []
    # WHAT THE CARD ACTUALLY DRAWS of that summary — filled in by the renderer
    # below (see chart_render.render_breaking_card's `fit` out-param). Defaults
    # to the full text so a degraded render is judged on what the card WAS
    # GIVEN rather than silently scoring an empty string, which would read as
    # "the card has no body" and let a restatement through the gate.
    card_fit_report: dict = {}
    card_summary_drawn = card_summary or ""
    card_headline_drawn = ""
    # WHY THERE IS NO CARD, when there is no card. `card_svg == ""` reaches the
    # dispatch with no reason attached, and the dispatch has to choose between
    # two opposite readings: a picture we DECLINED to print (the post ships
    # text-only) and a picture we FAILED to make (an environment fault). This
    # string is that difference, recorded by the only code that knows it. Empty
    # whenever the render succeeded or was never attempted.
    card_absent_reason = ""

    # Lazy import of card renderer (degrades gracefully)
    card_svg = ""
    try:
        from engine.marketing.chart_render import (  # noqa: PLC0415
            card_summary_budget_chars,
            chart_cta_enabled,
            derive_card_headline,
            render_breaking_card,
        )
        card_headline = derive_card_headline(raw_headline)
        headline_chars_dropped = max(0, len(raw_headline.strip()) - len(card_headline))
        if headline_chars_dropped:
            # COUNTED, never silent: this is text the card does not show. The
            # count is persisted in provenance.card_fit (→ outbox source.card_fit)
            # and announced once per item. Bare line-start print, never a logger.
            print(
                "::warning title=breaking-card-headline-compressed::"
                f"{item.get('id', '?')}: source headline {len(raw_headline.strip())} "
                f"chars -> {len(card_headline)} on the card "
                f"({headline_chars_dropped} dropped, whole-sentence bound); "
                "the post body still carries the full summary",
                flush=True,
            )
        card_tickers = _enrich_tickers(tickers, root) or []
        card_kwargs = dict(
            headline=card_headline,
            source_name=item.get("source_name", item.get("source", "")),
            source_tier=item.get("source_tier", "aggregator"),
            published_at=item.get("published_at", ""),
            tickers=card_tickers,
            suppress_cta=bool(item.get("cta_suppress", False)),
            # Account-wide footer posture (publish.chart_cta_enabled); distinct
            # from the per-item tragedy rule above, which drops the URL too.
            cta=chart_cta_enabled(cfg),
            summary=card_summary,
            logo_root=root,
        )
        # BACKSTOP — no source handle may reach a card surface (operator law
        # 2026-08-02). De-handling happens at ingestion, so this should never
        # fire; it exists because the live defect rendered "@BRICSinfo ·
        # AGGREGATOR" into the card art, and a card is built from params that
        # copywriter.banned_language (the publisher's last gate, which screens
        # POST TEXT) can never see. A leak drops the picture, not the post: the
        # post has its own gate, and shipping no card beats shipping a card that
        # tags a competitor.
        _card_violations = _card_param_violations(card_kwargs)
        if _card_violations:
            print("::warning title=breaking-card-handle-mention::"
                  f"{item.get('id', '')}: {'; '.join(_card_violations[:3])} — "
                  f"card dropped, posting text-only", flush=True)
            raise _CardHandleLeak(_card_violations[0])

        try:
            card_svg = render_breaking_card(
                event_class=item.get("event_class"),
                fit=card_fit_report, **card_kwargs
            )
        except TypeError:
            # Older renderer without the event_class kwarg — degrade cleanly.
            card_svg = render_breaking_card(fit=card_fit_report, **card_kwargs)
        # WHAT THE READER SEES, read back from the renderer.
        #
        # ABSENT KEYS MEAN THE RENDER DEGRADED, AND A DEGRADED CARD DOES NOT
        # SHIP (2026-08-06). render_breaking_card's outer fail-soft returns
        # _break_fallback_svg — a blank "MASTERMIND · Breaking" rectangle — and
        # populates no `fit`. card_svg was then non-empty while
        # card_summary_drawn kept its conservative default (the FULL summary),
        # so the dispatch gate scored a 300-char body that is not on the card,
        # could answer attach=True on it, and a blank placeholder shipped as
        # media with provenance.card_fit reporting summary_source_chars = 0. The
        # docstring claimed "a caller that reads a missing key knows the render
        # degraded"; the caller now ACTS on it. A card nobody can read is not a
        # card, and the post has its own text.
        if "headline_drawn" in card_fit_report:
            card_summary_drawn = str(card_fit_report.get("summary_drawn") or "")
            # THE HERO, READ BACK THE SAME WAY (2026-08-06 review). The gate
            # scored `card_headline` — derive_card_headline's pre-render
            # sentence bound — while the renderer fits that string into its own
            # box and may place less of it. Both texts the gate compares must be
            # what the READER SEES, and only the fit report knows that.
            card_headline_drawn = (
                str(card_fit_report.get("headline_drawn") or "") or card_headline
            )
        elif card_svg:
            # NOT "posting text-only" — that is the dispatch's call, not ours
            # (2026-08-06 review). This is a FAILED render, not a withheld card,
            # and a post that names tickers owes a picture it did not get; the
            # line used to promise a post that press_lane then refused.
            print("::warning title=breaking-card-render-degraded::"
                  f"{item.get('id', '?')}: the renderer returned a card with no "
                  "fit report (fail-soft fallback) — card dropped", flush=True)
            card_svg = ""
            card_summary_drawn = ""
            card_headline_drawn = ""
            card_absent_reason = _CARD_ABSENT_RENDER_DEGRADED
        _sm_dropped = int(card_fit_report.get("summary_chars_dropped", 0) or 0)
        if _sm_dropped:
            # COUNTED, never silent — the sibling of the headline warning above.
            # Discarding this was the 2026-08-05 defect: the summary wrap's
            # overflow flag was thrown away, so the card clipped mid-clause and
            # provenance.card_fit reported zero characters dropped.
            # The BUDGET is named alongside the drop, because the drop is the
            # symptom and the budget mismatch is the cause: the producer writes
            # to _MAX_SUMMARY_CHARS and the box holds well under half of that.
            # An operator tuning the summarizer needs the box's number, not just
            # the count of what fell off this one card.
            print(
                "::warning title=breaking-card-summary-trimmed::"
                f"{item.get('id', '?')}: card summary "
                f"{card_fit_report.get('summary_source_chars', 0)} chars -> "
                f"{card_fit_report.get('summary_card_chars', 0)} on the card "
                f"({_sm_dropped} dropped, whole-sentence bound, never clipped); "
                f"the box holds ~{card_summary_budget_chars()} chars of prose "
                f"against a producer budget of {_MAX_SUMMARY_CHARS}; "
                "the post body still carries the full summary",
                flush=True,
            )
    except _CardHandleLeak:
        # NAMED, not swallowed by the blanket handler below. The card is gone
        # for a reason a retry cannot fix, and the dispatch has to be able to
        # tell that from a renderer that merely fell over — one is worth another
        # tick, the other is not.
        card_svg = ""
        card_summary_drawn = ""
        card_headline_drawn = ""
        card_absent_reason = _CARD_ABSENT_POLICY_REFUSED
    except Exception:  # noqa: BLE001
        card_svg = ""

    ingested_at = datetime.now(tz=timezone.utc).isoformat()

    return {
        "kind": "breaking",
        "id": item.get("id", ""),
        "headline": item.get("headline", ""),
        # The bounded hero the CARD shows. Separate from `headline` on purpose:
        # the post-text lane composes from `headline` and its behaviour is
        # unchanged by this gate. A follow-up may promote this to `headline`
        # once the copy lane's near-dup/payload gates are re-measured against it.
        "card_headline": card_headline,
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
        # What the CARD was actually given — the dispatch gate compares these
        # against the composed post text to decide whether the picture earns its
        # place (card_earns_attachment). card_summary is None when the summary
        # was dropped as a restatement of the headline.
        "card_summary": card_summary,
        # ...and what it DREW of it. The gate scores this one: the summary box
        # holds what chart_render.card_summary_budget_chars() measures while
        # the producer writes to 320, so card_summary is routinely a paragraph
        # the reader never sees. "" means the card drew no second voice at all.
        "card_summary_drawn": card_summary_drawn,
        # ...and the HERO the card drew, read back from the same fit report.
        # `card_headline` is what the producer HANDED the renderer; this is what
        # the renderer placed. The gate must judge the second one.
        "card_headline_drawn": card_headline_drawn,
        "card_tickers": card_tickers,
        "provenance": {
            "source_url": item.get("url", ""),
            "source": item.get("source", ""),
            "ingested_at": ingested_at,
            # WHY THERE IS NO CARD — "" whenever one is attached or none was
            # ever attempted. See _CARD_ABSENT_RENDER_DEGRADED for the contract;
            # press_lane is the reader.
            "card_absent_reason": card_absent_reason,
            # Counted drop, persisted: press_lane merges this dict into the
            # outbox item's `source`, so `source.card_fit` is the durable record
            # of how much source text the card could not show.
            "card_fit": {
                "headline_source_chars": len(raw_headline.strip()),
                "headline_card_chars": len(card_headline),
                "headline_chars_dropped": headline_chars_dropped,
                # The summary half of the same record. It used to be absent,
                # which is why card_fit could report a clean fit for a card that
                # was visibly clipped mid-clause: nothing measured this side.
                "summary_source_chars": int(
                    card_fit_report.get("summary_source_chars", 0) or 0),
                "summary_card_chars": int(
                    card_fit_report.get("summary_card_chars", 0) or 0),
                "summary_chars_dropped": int(
                    card_fit_report.get("summary_chars_dropped", 0) or 0),
            },
        },
    }
