"""engine.marketing.copy_review — quality review for generated copy.

WHAT WAS MISSING
copywriter.validate_copy runs 20 rules and every one is a pattern match on ONE
post: cashtag present, length, em dash, banned vocab, emoji budget. Two things
it structurally cannot catch:

  1. A post that breaks no rule and still reads like a machine wrote it.
  2. ANYTHING about the batch. The 2026-07-26 incident was not one bad post —
     it was eight posts sharing a skeleton ("$TICKER into the week" x8). Every
     one passed validate_copy individually, because individually each was fine.

  3. A post that is clean, unique, on-voice and simply not DECODABLE. "Four up,
     near highs, VWAP holds" broke no rule anywhere and no reader could parse it
     (2026-07-26 $AAPL). Ambiguity is not repetition and it is not a style
     judgement: it has measurable shapes, so detect_ambiguity() handles it
     mechanically alongside the repetition pass.

The mechanical halves are the important ones and they need no model at all:
repetition and ambiguity are both measurable. detect_repetition() and
detect_ambiguity() run always, cost nothing, and would each have caught their
incident on the first night.

The remaining half is a judgement call, so it is LLM-gated exactly like
write_posts_llm (config copywriter.llm.enabled AND MARKETING_LLM_ENABLED) and
degrades to the mechanical half when unavailable.

REVIEW IS ADVISORY, NEVER A GATE. It stamps findings on items so the operator
sees "reads templated" next to the post in the Outbox. It does not block, and
it does not silently rewrite: a reviewer that quietly drops posts turns one bad
night into an empty queue, and per house epistemics a display-tier signal never
gates. The operator holds the verdict; this just points.

THE LOOP CLOSES HERE. lessons_from_rejections() feeds the operator's own
rejection notes back into the reviewer prompt, so "this reads like a brochure"
written once becomes a thing the reviewer looks for from then on.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

# How many leading words define a post's "shape" for repetition purposes.
_SHAPE_WORDS = 4
# A batch is flagged when this share of posts collide on one shape.
_REPEAT_SHARE = 0.34
# Cap the operator lessons injected into the prompt (recency-weighted).
_MAX_LESSONS = 25

_CASHTAG_RE = re.compile(r"\$[A-Z]{1,5}\b")
_NUM_RE = re.compile(r"\d[\d,.]*")


def _shape(text: str) -> str:
    """A post's opening shape: leading words with tickers/numbers neutralised.

    "$AAPL into the week" and "$TSLA into the week" must collide — the whole
    point is to catch a skeleton whose only variation is the substitutions.
    """
    t = _CASHTAG_RE.sub("$T", text or "")
    t = _NUM_RE.sub("#", t)
    words = re.findall(r"[\w$#'-]+", t.lower())
    return " ".join(words[:_SHAPE_WORDS])


def detect_repetition(posts: list[dict]) -> list[dict]:
    """Batch-level findings. Deterministic, no model, always runs.

    posts: [{"id"?, "headline", "body"}]. Returns findings:
      {"kind": "repeated_headline"|"repeated_opener"|"identical_body",
       "detail": str, "ids": [...], "severity": "high"|"medium"}
    """
    out: list[dict] = []
    n = len(posts or [])
    if n < 3:
        return out          # too small for repetition to mean anything

    def _collide(key_fn, kind, label, severity):
        buckets: dict[str, list[str]] = {}
        for i, p in enumerate(posts):
            k = key_fn(p)
            if not k:
                continue
            buckets.setdefault(k, []).append(str(p.get("id") or i))
        for shape, ids in buckets.items():
            if len(ids) >= max(2, int(n * _REPEAT_SHARE) + 1):
                out.append({
                    "kind": kind, "severity": severity, "ids": ids,
                    "detail": f"{len(ids)} of {n} posts {label}: {shape!r}",
                })

    _collide(lambda p: _shape(p.get("headline", "")),
             "repeated_headline", "open with the same headline shape", "high")
    _collide(lambda p: _shape(p.get("body", "")),
             "repeated_opener", "open the body the same way", "medium")

    # Byte-identical bodies once tickers/numbers are neutralised = twins.
    twins: dict[str, list[str]] = {}
    for i, p in enumerate(posts):
        b = _NUM_RE.sub("#", _CASHTAG_RE.sub("$T", p.get("body", "") or ""))
        if b.strip():
            twins.setdefault(b, []).append(str(p.get("id") or i))
    for _b, ids in twins.items():
        if len(ids) > 1:
            out.append({
                "kind": "identical_body", "severity": "high", "ids": ids,
                "detail": f"{len(ids)} posts are the same sentence with different "
                          f"numbers",
            })
    return out


def detect_ambiguity(posts: list[dict]) -> list[dict]:
    """Per-post clarity findings. Deterministic, no model, always runs.

    The second blind spot, found the same way as the first. detect_repetition
    catches eight posts that share a skeleton; nothing caught ONE post that is
    simply not decodable:

        "Four up, near highs, VWAP holds"
        "... That Jun 26 anchored VWAP has held for 20 sessions. I'm watching a
         close below it, not chasing."

    Clean, unique, on-voice, and unreadable. The operator's reaction was the
    whole spec: "wtf is four up?"

    Unlike detect_repetition this is a PER-POST check, so it runs on batches of
    any size — a bad post is bad alone. It reuses copywriter's detectors, which
    means the marker the operator sees in the Outbox and the rule that rejects
    LLM copy are the same rule, and cannot drift apart. It still applies where
    the validator does not: deterministic floor copy never passes through
    validate_copy, so this is the only clarity check that sees it.

    Returns findings shaped like detect_repetition's:
      {"kind": "headless_count"|"unnamed_level", "detail", "ids", "severity"}
    """
    out: list[dict] = []
    if not posts:
        return out
    try:
        from engine.marketing.copywriter import (  # noqa: PLC0415
            dangling_levels,
            headless_counts,
        )
    except Exception as exc:  # noqa: BLE001 — review must never break generation
        log.warning("copy_review: clarity detectors unavailable: %s", exc)
        return out

    for i, p in enumerate(posts):
        pid = str(p.get("id") or i)
        text = f"{p.get('headline', '') or ''}\n{p.get('body', '') or ''}"
        for clause in headless_counts(text):
            out.append({
                "kind": "headless_count", "severity": "high", "ids": [pid],
                "detail": f"{pid}: {clause!r} is a count with no noun "
                          f"({clause.split()[0].lower()} what?)",
            })
        for sentence in dangling_levels(text):
            out.append({
                "kind": "unnamed_level", "severity": "high", "ids": [pid],
                "detail": f"{pid}: watches a level it never prices: "
                          f"{sentence[:70]!r}",
            })
    return out


def lessons_from_rejections(root=None, *, limit: int = _MAX_LESSONS) -> list[str]:
    """The operator's own rejection notes, newest first. Fail-soft to []."""
    try:
        from engine.marketing import rejections as _rej  # noqa: PLC0415
        rows = _rej._read_rows(root)  # noqa: SLF001 — same package, read-only
        notes = [
            str(r.get("reason") or "").strip()
            for r in rows if r.get("row") == "rejection" and r.get("reason")
        ]
        seen: set[str] = set()
        out: list[str] = []
        for note in reversed(notes):          # newest first
            k = note.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(note)
            if len(out) >= limit:
                break
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("copy_review: could not read rejection lessons: %s", exc)
        return []


def review_posts_llm(posts: list[dict], cfg: dict, *,
                     lessons: list[str] | None = None) -> list[dict] | None:
    """Per-post style critique. Returns None when unavailable (caller degrades).

    Gated identically to copywriter.write_posts_llm so tests and local runs
    never reach the network.
    """
    llm_cfg = (cfg or {}).get("llm") or {}
    if not bool(llm_cfg.get("enabled", False)):
        return None
    if os.environ.get("MARKETING_LLM_ENABLED", "").lower() not in ("1", "true", "yes"):
        return None
    if not posts:
        return []

    try:
        from lib import config as _config  # noqa: PLC0415
        model_id = (_config.load().get("llm_models", {}) or {}).get(
            llm_cfg.get("model_key", "marketing_copy"), "")
        if not model_id:
            return None

        # CHATGPT-FIRST (operator directive 2026-07-29, recorded on
        # config/marketing.yml copywriter.llm): codex leads, the key_pool-balanced
        # Claude oauth rung is the fallback. Sol, same tier as the writer whose
        # prose this pass judges line by line.
        #
        # The POOL LANE is pinned, not threaded: `llm_cfg` here IS
        # `copywriter.llm` (review_batch narrows cfg to the copywriter block), so
        # inheriting its oauth_pool_lane would bill every review to
        # marketing-copywriter and make the two lanes indistinguishable in the
        # key ledger. The codex tier IS threaded because the ruling gives both
        # lanes the same one.
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(
            {
                "usage_lane": "marketing-copy-review",
                "oauth_pool_lane": "marketing-copy-review",
                "provider_order": llm_cfg.get("provider_order")
                or ["codex", "oauth", "anthropic", "deepseek"],
                "codex_source_model": llm_cfg.get("codex_source_model", "gpt-5.6-sol"),
                "codex_reasoning_effort": llm_cfg.get("codex_reasoning_effort", "medium"),
            },
            opus_model=model_id,
        )
        if not providers:
            print("::warning title=marketing_copy_review_mute::Copy review is "
                  "enabled but no LLM provider credential is visible — falling "
                  "back to the mechanical repetition check only.")
            return None

        learned = ""
        if lessons:
            learned = ("\n\nTHE OPERATOR HAS REJECTED POSTS FOR THESE REASONS "
                       "BEFORE. Treat each as a rule:\n"
                       + "\n".join(f"- {l}" for l in lessons))

        system = (
            "You review short trading posts before a human sees them. You are "
            "not the writer and you do not rewrite: you point at what is wrong "
            "so the operator can decide fast.\n\n"
            "Flag ONLY these, and only when you would bet money on it:\n"
            "- reads machine-written: a frame the post is poured into rather "
            "than a thing someone said\n"
            "- says nothing: no level, no stance, no real question\n"
            "- stiff or brochure-ish phrasing, corporate register, cheese\n"
            "- a claim the numbers given do not support\n"
            "- does not survive a cold read: you cannot tell what it means "
            "without already knowing what the writer was looking at. A count "
            "with no noun ('four up' — four what?), a 'that'/'it' pointing at "
            "something never named, a study name the reader would have to look "
            "up, or a level the post says it is watching but never prices.\n\n"
            "Do NOT flag: terseness, informality, fragments, dry humour, an "
            "unexciting take. Those are the house voice, not defects. Unclear is "
            "not the same as short: a two-word post whose meaning lands is fine, "
            "a full sentence nobody can decode is not. A post with nothing wrong "
            "gets an empty issues list, and most posts should." + learned + "\n\n"
            'Return JSON only: [{"i": <index>, "verdict": "ok"|"weak"|"bad", '
            '"issues": ["short specific phrase"]}]'
        )
        payload = [{"i": i, "headline": p.get("headline", ""), "body": p.get("body", "")}
                   for i, p in enumerate(posts)]

        def _call(client, model):
            resp = client.messages.create(
                model=model, max_tokens=2000, system=system,
                messages=[{"role": "user", "content": json.dumps(payload, indent=1)}])
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text")
            return (text or None), None, resp

        raw, _reason, _prov = llm_auth.make_call(providers, _call,
                                                 context="marketing_copy_review")
        if not raw:
            return None
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return None
        parsed = json.loads(m.group())
        if not isinstance(parsed, list):
            return None

        out: list[dict] = [{"verdict": "ok", "issues": []} for _ in posts]
        for row in parsed:
            try:
                i = int(row.get("i"))
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(out):
                issues = [str(x).strip() for x in (row.get("issues") or []) if str(x).strip()]
                out[i] = {"verdict": str(row.get("verdict") or "ok"), "issues": issues[:4]}
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("copy_review.review_posts_llm failed: %s", exc)
        return None


def review_batch(posts: list[dict], cfg: dict | None = None, *, root=None) -> dict:
    """Full review: always-on repetition findings + optional LLM critique.

    Returns {"batch": [findings], "posts": [{verdict, issues}], "mode": str}.
    Never raises — review is advisory and must not break generation.
    """
    result: dict[str, Any] = {
        "batch": [], "posts": [{"verdict": "ok", "issues": []} for _ in (posts or [])],
        "mode": "mechanical",
    }
    if not posts:
        return result
    try:
        result["batch"] = detect_repetition(posts) + detect_ambiguity(posts)
        per = review_posts_llm(posts, (cfg or {}).get("copywriter", {}) or {},
                               lessons=lessons_from_rejections(root))
        if per is not None and len(per) == len(posts):
            result["posts"] = per
            result["mode"] = "llm"
        # Repetition is a per-post problem too: mark the members so the operator
        # sees WHICH posts collide, not just that some do. Clarity findings are
        # already per-post and ride the same path.
        by_id = {str(p.get("id") or i): i for i, p in enumerate(posts)}
        for f in result["batch"]:
            for pid in f.get("ids", []):
                i = by_id.get(str(pid))
                if i is None:
                    continue
                issues = result["posts"][i].setdefault("issues", [])
                if f["kind"] not in issues:
                    issues.append(f["kind"])
                if f.get("severity") == "high":
                    result["posts"][i]["verdict"] = "bad"
                elif result["posts"][i].get("verdict") == "ok":
                    result["posts"][i]["verdict"] = "weak"
    except Exception as exc:  # noqa: BLE001
        log.warning("copy_review.review_batch failed: %s", exc)
    return result
