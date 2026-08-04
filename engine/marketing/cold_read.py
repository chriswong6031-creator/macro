"""engine.marketing.cold_read — can a stranger resolve this post? A VETO, never an editor.

THE GAP THIS FILLS (postmortem 2026-08-04, research/WIRE_COPY_HARDENING_PROGRAM.md §1).
Every copy gate in this repo asks a question about the STRING — under 280 chars,
no banned word, no "@handle", every number present in the source, line 2's tokens
don't overlap line 1's. None asks whether a READER can resolve the post. So this
shipped to the flagship and passed all of them:

    More info on this - South Korea core inflation hits 2-1/2 year high
    despite headline cooling -- wire reports

It is grammatical, sourced, in budget, stance-free, handle-free. It fails exactly
one test — *a reader who sees only this post cannot resolve "this"* — and that
test cannot be written as a rule, because the defect is what is MISSING from the
reader's context rather than anything present in the text. The repo already says
so, in copywriter.jargon_violations: "the open-ended half of this class ... is
not enumerable".

`relay_hygiene` enumerates the defects we have already seen. This is for the next
one.

═══════════════════════════════════════════════════════════════════════════════
WHY A MODEL IS ALLOWED TO DO THIS, AND WHAT KEEPS IT HONEST
═══════════════════════════════════════════════════════════════════════════════

The constitution (A7 / CLAUDE.md epistemics) is explicit: an LLM may only
DE-ESCALATE. It never originates a signal, a score, or an escalation. That is
exactly the shape of this call and the reason it is lawful here:

  * it runs LAST, after every deterministic gate has already decided;
  * its ONLY possible effect is to stop a post. It cannot pass one, promote one,
    rank one, or edit a word of one;
  * it returns no score — a boolean and a category, nothing to sort on.

Three structural guards, because "the model is only allowed to veto" is worth
nothing if the veto is unbounded:

  1. CLOSED CATEGORY ENUM. A block is honoured ONLY when it names one of
     :data:`BLOCK_CATEGORIES`. A model that decides the copy is boring, badly
     punctuated, or wrong about the Fed returns a category we do not recognise,
     and an unrecognised block is DISCARDED. "The model became an editor" is
     therefore inert rather than dangerous — the failure mode is a wasted call,
     not a quarantined post.
  2. FAIL-OPEN, EVERYWHERE. No endpoint, bad JSON, a timeout, a refusal, an
     empty reason, an exception anywhere in this module: not blocked. Post-time
     quarantine in this repo is TERMINAL, so a screen that cannot evaluate must
     let the item through. It may never fail dead.
  3. LANE-SCOPED, from relay_hygiene's own allowlist. Our desks write in the
     first person on purpose; this asks a question only meaningful about copy
     relayed from somebody else's page.

AND IT SHIPS DARK. `action` defaults to "shadow": the verdict is computed and
logged, and NOTHING is blocked. Arming it is a one-line config flip, made after
reading what it would have done — the same probation this program's own charter
demands of a new SOURCE, applied to a new GATE. A model veto wired straight to a
terminal quarantine on day one, with no measured precision, is the exact move
the charter argues against.

Public API:
    cold_read_verdict(text, *, provenance, cfg=None, _call=None) -> dict
    resolve_action(cfg) -> str            # "shadow" | "hold" | "quarantine"
    prompt_for(text) -> tuple[str, str]   # (system, user) — pure, no network
    BLOCK_CATEGORIES: frozenset[str]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Callable

# ─────────────────────────────────────────────────────────────────────────────
# The closed category enum — the whole safety story
# ─────────────────────────────────────────────────────────────────────────────

#: The ONLY grounds on which a post may be vetoed here. Every one is a thing the
#: READER cannot resolve, which is the single question this gate exists to ask.
#: A block naming anything else is discarded by :func:`_coerce_verdict`.
#:
#: Deliberately NOT extensible by config. A config-widened enum is a config-wide
#: editor, and the moment "tone" or "quality" can be a veto category this stops
#: being a de-escalation and starts being the model deciding what we publish.
BLOCK_CATEGORIES: frozenset[str] = frozenset({
    # "More info on this - ..." — a pointer whose antecedent is on the source's
    # page. The live post.
    "dangling_reference",
    # "As noted in the screenshot", "see the chart below" — a reference to
    # something that exists on their page and not in our post.
    "missing_referent",
    # "I'll have more to come on this separately" — a first-person promise from
    # somebody the reader cannot identify, which we are not going to keep.
    "unnamed_promise",
    # "investingLive Americas FX news wrap" — somebody else's masthead worn as
    # if it were ours.
    "foreign_brand",
    # A sentence that stops mid-thought: a clamp that cut a clause, a feed that
    # truncated a title.
    "truncated",
})

#: What the gate DOES with a block. Ships as "shadow" (see the module docstring).
_ACTIONS: frozenset[str] = frozenset({"shadow", "hold", "quarantine"})
_DEFAULT_ACTION = "shadow"

#: Answer budget. The reply is a boolean, a slug and a short clause; anything
#: longer means the model is writing an essay, and we do not read essays here.
_DEFAULT_MAX_TOKENS = 200

#: Local-first by default. This is a SCREEN, not a writer: ~30 relayed posts a
#: day, one short question each, on hardware already paid for. "Is there a
#: 'this' here with no antecedent" is not a frontier-model problem, and billing
#: a hosted rung for it would make the gate something an operator turns off.
_DEFAULT_PROVIDER_ORDER = ("ollama",)


def _norm(text: object) -> str:
    return re.sub(r"[ \t]+", " ", str(text or "")).strip()


# ─────────────────────────────────────────────────────────────────────────────
# The prompt — pure, testable, and the actual design of this module
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM = """You check social posts before they are published.

The reader sees ONLY the post below. No headline above it. No article behind it. \
No previous post. No link. Nothing you can look up.

Answer ONE question: is there something in this post that the reader cannot \
resolve?

Block ONLY for these, and name the one that fits:

  dangling_reference  a pointer with no antecedent in the post itself -- "more \
info on this", "as mentioned", "the above", a bare "this"/"that"/"here" that \
refers to something not in the post.
  missing_referent    a reference to something not shown -- a chart, a \
screenshot, a table, a link, an earlier post, "see below".
  unnamed_promise     a first-person promise or aside from someone the reader \
cannot identify -- "I'll have more later", "we'll cover this", "stay tuned".
  foreign_brand       a publication, desk or byline that is not the poster's, \
written as if it were theirs.
  truncated           a sentence that stops mid-thought or is cut off.

Do NOT block for any of these. They are not your call:
  - being short, plain, or boring
  - lacking background you would personally like to have
  - tone, punctuation, capitalisation, emoji, or formatting
  - whether you agree with it, or think it matters
  - not naming a source (some posts carry no citation on purpose)
  - jargon or numbers you do not recognise

If nothing is unresolvable, pass it. Passing is the normal answer.

Reply with JSON and nothing else:
{"blocked": false, "category": "none", "reason": ""}
or
{"blocked": true, "category": "<one slug from the list>", "reason": "<8 words max>"}"""


def prompt_for(text: str) -> tuple[str, str]:
    """(system, user) for a post. Pure — no network, no config, no model."""
    return _SYSTEM, f"POST:\n{_norm(text)}"


# ─────────────────────────────────────────────────────────────────────────────
# Verdict coercion — where an out-of-contract answer becomes a pass
# ─────────────────────────────────────────────────────────────────────────────

_JSON_RE = re.compile(r"\{.*\}", re.S)


def _coerce_verdict(raw: object) -> dict:
    """Parse a model reply into a verdict, DISCARDING anything out of contract.

    Every failure lands on the same answer — not blocked — and that is the whole
    point. A model that returns prose, invents a category, blocks with no reason,
    or emits nothing at all cannot quarantine a post; it can only waste a call.

    Returned ``category`` is "" when the reply was unusable, so a caller can tell
    "the model passed it" from "the model said something we could not read".
    """
    text = str(raw or "").strip()
    if not text:
        return {"blocked": False, "category": "", "reason": "empty model reply"}

    match = _JSON_RE.search(text)
    if not match:
        return {"blocked": False, "category": "", "reason": "no JSON in reply"}
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return {"blocked": False, "category": "", "reason": "unparseable JSON"}
    if not isinstance(data, dict):
        return {"blocked": False, "category": "", "reason": "reply was not an object"}

    # STRICTLY the JSON boolean `true`, never a truthy value.
    #
    # `bool("yes")` is True, and a model that answers {"blocked": "yes"} instead
    # of {"blocked": true} would have quarantined a clean post through a schema
    # slip. Anything that is not a real boolean is a contract violation, and
    # contract violations fail OPEN here like every other one. The cost of
    # strictness is a missed veto; the cost of leniency is a deleted post.
    blocked = data.get("blocked")
    if blocked is not True:
        if isinstance(blocked, bool):
            return {"blocked": False, "category": "none", "reason": ""}
        return {"blocked": False, "category": "",
                "reason": f"'blocked' was {type(blocked).__name__}, not a boolean"}

    category = str(data.get("category") or "").strip().lower()
    if category not in BLOCK_CATEGORIES:
        # THE GUARD THAT MAKES THIS A VETO AND NOT AN EDITOR. A block on grounds
        # we never authorised ("tone", "too_short", "inaccurate") is discarded.
        return {"blocked": False, "category": "",
                "reason": f"block on unrecognised category {category!r} — discarded"}

    reason = _norm(data.get("reason"))[:120]
    if not reason:
        return {"blocked": False, "category": "",
                "reason": f"block ({category}) carried no reason — discarded"}
    return {"blocked": True, "category": category, "reason": reason}


def resolve_action(cfg: dict | None) -> str:
    """"shadow" | "hold" | "quarantine". Unknown or absent => "shadow"."""
    action = str((cfg or {}).get("action") or _DEFAULT_ACTION).strip().lower()
    return action if action in _ACTIONS else _DEFAULT_ACTION


# ─────────────────────────────────────────────────────────────────────────────
# The call
# ─────────────────────────────────────────────────────────────────────────────

#: Per-process memo, keyed on the post text. The publisher can see the same item
#: across dry-run and live passes in one process, and a gate whose answer changed
#: between two reads of one string would be untestable and unarguable.
#:
#: BOUNDED, because the press fastlane daemon is long-running: an unbounded dict
#: keyed on every post text a process ever saw is a slow leak in the one service
#: that never restarts on its own. Oldest-first eviction — a text evicted and
#: seen again simply costs one more call.
_MEMO: dict[str, dict] = {}
_MEMO_CAP = 512

#: Per-run read budget. The publisher's loop reaches this gate for every item it
#: CONSIDERS, not only the ones it posts, so a slow or wedged local endpoint
#: could otherwise stall a publish sweep one 30-second timeout at a time.
#:
#: A cap that truncates coverage SILENTLY is the defect the hardening charter
#: names ("no silent caps"), so `budget_exhausted` is reported in the verdict
#: and the caller prints what went unread.
_DEFAULT_MAX_READS_PER_RUN = 60
_reads_this_run = 0


def reset_run_budget() -> None:
    """Start a fresh per-run read budget. Called once per publisher sweep."""
    global _reads_this_run
    _reads_this_run = 0


def _text_key(text: str) -> str:
    return hashlib.sha256(_norm(text).encode("utf-8")).hexdigest()


def _providers(cfg: dict) -> list[dict]:
    """Build the provider list. Local-first; [] when nothing is configured."""
    from engine import llm_auth  # noqa: PLC0415

    order = cfg.get("provider_order") or list(_DEFAULT_PROVIDER_ORDER)
    return llm_auth.build_providers(
        {
            "usage_lane": cfg.get("usage_lane", "marketing-cold-read"),
            "oauth_pool_lane": cfg.get("oauth_pool_lane", "marketing-cold-read"),
            "provider_order": list(order),
            "ollama_base_url": cfg.get("ollama_base_url"),
            "ollama_base_url_env": cfg.get("ollama_base_url_env"),
            "ollama_model": cfg.get("ollama_model"),
            "ollama_timeout_s": cfg.get("ollama_timeout_s", 30),
            "ollama_num_ctx": cfg.get("ollama_num_ctx", 4096),
        },
        opus_model=str(cfg.get("model_id") or ""),
    )


def _default_call(text: str, cfg: dict) -> str | None:
    """One model call. Returns the raw reply, or None on ANY failure."""
    try:
        from engine import llm_auth  # noqa: PLC0415

        providers = _providers(cfg)
        if not providers:
            return None
        system, user = prompt_for(text)
        max_tokens = int(cfg.get("max_tokens", _DEFAULT_MAX_TOKENS))

        def _do(client, model):
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal", resp
            out = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            return (out.strip() or None), None, resp

        reply, _why, _prov = llm_auth.make_call(
            providers, _do, context="marketing_cold_read"
        )
        return reply or None
    except Exception:  # noqa: BLE001
        return None


def cold_read_verdict(
    text: str,
    *,
    provenance: str = "",
    cfg: dict | None = None,
    _call: Callable[[str, dict], Any] | None = None,
) -> dict:
    """Would a stranger be left with an unresolvable reference in this post?

    Returns ``{blocked, category, reason, mode, action}``:

      * ``blocked``  True ONLY for an in-contract veto (see BLOCK_CATEGORIES).
      * ``mode``     "off" (disarmed) | "skipped" (lane not relayed / no text) |
                     "unavailable" (no model reachable) | "read" (a verdict).
      * ``action``   what the CALLER should do with a block — resolve_action's
                     answer, carried here so the decision and its policy travel
                     together in one row.

    NEVER RAISES. Every failure path returns ``blocked: False``; post-time
    quarantine is terminal, so a screen that cannot evaluate must not fail dead.

    ``_call`` is the test seam: a callable ``(text, cfg) -> str | None`` standing
    in for the model. Tests never reach the network.
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    action = resolve_action(cfg)
    base = {"blocked": False, "category": "", "reason": "", "mode": "off",
            "action": action}

    if not bool(cfg.get("enabled", False)):
        return base

    body = _norm(text)
    if not body:
        return {**base, "mode": "skipped", "reason": "no text"}

    # LANE SCOPE, from relay_hygiene's single allowlist (never a second copy).
    # Our own desks write in the first person on purpose; "can a stranger resolve
    # this" is a question about copy relayed from somebody else's page.
    try:
        from engine.marketing import relay_hygiene as _rh  # noqa: PLC0415
        if not _rh.lane_is_relayed(provenance):
            return {**base, "mode": "skipped", "reason": "lane is not a relay lane"}
    except Exception:  # noqa: BLE001
        return {**base, "mode": "skipped", "reason": "lane allowlist unreadable"}

    key = _text_key(body)
    if key in _MEMO:
        return {**_MEMO[key], "action": action}

    # `cfg.get(k, default)`, NOT `cfg.get(k) or default`: an explicit "" means
    # "no env gate" and `or` would silently reinstate the default, which is how a
    # deliberate override becomes an absent one.
    env_gate = str(cfg.get("env_gate", "MARKETING_LLM_ENABLED"))
    if env_gate and os.environ.get(env_gate, "").strip().lower() not in ("1", "true", "yes"):
        # Mirrors every other LLM gate in this repo: config AND env. Keeps the
        # test suite and any disarmed run at zero model calls.
        return {**base, "mode": "off", "reason": f"{env_gate} not set"}

    global _reads_this_run
    budget = int(cfg.get("max_reads_per_run", _DEFAULT_MAX_READS_PER_RUN))
    if budget > 0 and _reads_this_run >= budget:
        # SAID OUT LOUD, never silent: a truncated screen that reports nothing
        # reads as a clean run. The caller surfaces this.
        return {**base, "mode": "budget_exhausted",
                "reason": f"per-run read budget of {budget} reached"}

    caller = _call or _default_call
    _reads_this_run += 1
    try:
        reply = caller(body, cfg)
    except Exception:  # noqa: BLE001
        reply = None
    if reply is None:
        # No endpoint, a timeout, a refusal. Unscreened, never dead.
        out = {"blocked": False, "category": "", "reason": "no model reachable",
               "mode": "unavailable"}
        return {**out, "action": action}

    verdict = {**_coerce_verdict(reply), "mode": "read"}
    if len(_MEMO) >= _MEMO_CAP:
        for stale in list(_MEMO)[: _MEMO_CAP // 4]:
            _MEMO.pop(stale, None)
    _MEMO[key] = verdict
    return {**verdict, "action": action}
