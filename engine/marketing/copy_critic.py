"""engine.marketing.copy_critic — the cold-read critic (Content Studio W1).

Program: ``research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md``
§0 gate 5 ("cold-read critic on every planned post"), §4 (the CRITIC stage of
the nightly pipeline) and §7 (generation-time review). Interface pinned by
``research/marketing_dockets/CONTENT_STUDIO_W1_BUILD_CONTRACT.md`` §Critic.

WHY THIS EXISTS
---------------
Six sessions patched the template generator in four days (#3904 volume, #3907
fragments, #3913 publish faults, #3918 headline gate, #3922 a hand-rewrite of a
whole day's queue, #3928 tail coherence) and the operator still aborted the
2026-07-29 review in disgust. The pattern every time: the patch adds an
enumerated ban, the generator cannot SEE its own output, and the next failure
mode is one synonym away — "screen" was not on the list that banned
"cross-checks". Coherence is not enumerable. Does the tail follow from the fact?
Does "that level" point at anything? Would a stranger scrolling past understand
this at all? The only system that can judge prose is a language model.

So: the deterministic validators check what must never be WRONG (numbers,
cashtags, shape, banned language). This checks what a human would CRINGE at.

THE TWO LAWS THAT BOUND IT
--------------------------
1. **De-escalation only.** The critic returns a verdict and reasons. It never
   rewrites, never proposes copy, and never adds a fact — only the writer writes
   and only the engine originates numbers (CLAUDE.md §Epistemics; masterplan §9).
   That is enforced structurally: this module reads ``verdict`` and ``reasons``
   out of the reply and discards everything else, so a model that "helpfully"
   returns a rewritten post has produced nothing.
2. **A failing critic is not a failing post.** The validators already ran. A
   provider outage, a malformed reply, an absent credential — all of it returns
   ``pass`` with the contracted reason ``["critic_unavailable"]``, the specific
   cause in ``detail``, and ONE ``::warning`` per cause per run. The WRITER lane
   failing is fatal for its item; the critic failing is not.

FRESH CONTEXT IS THE WHOLE POINT
--------------------------------
The critic sees the post, its kind, its shape, its allowed numbers and a
one-line topic. It does NOT see the persona card, the fact packet, the plan, or
the writer's prompt. Authorship bias is the failure it exists to catch: copy is
comprehensible to the desk that wrote it by definition, and every post in the
rejected batch parsed perfectly to the engine that assembled it.

IMPORT-CLOSURE LAW
------------------
**stdlib only at module import.** ``engine.llm_auth``, ``anthropic``, ``yaml``
and ``lib.config`` are imported lazily inside functions. The marketing-engine CI
lane installs pytest + pyyaml + jinja2 and nothing else, so a module-level
``import anthropic`` here turns that lane red at COLLECTION, before a single
test runs. ``tests/test_marketing_copy_v2.py`` scans this file's source to pin
it.

Public API
----------
    cold_read_verdict(text, ctx, cfg) -> {"verdict": str, "reasons": [str]}
        (plus "detail": str on the critic_unavailable path)
    critic_stats() -> dict
    reset_critic_stats() -> None
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading

log = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 200
#: SDK retries defeat the failover walk (the retry re-hits the SAME dead
#: credential before the waterfall even sees it). One attempt per provider, walk
#: on failure — the CHAIN is the retry.
DEFAULT_CLIENT_MAX_RETRIES = 0
DEFAULT_CLIENT_TIMEOUT_S = 30.0

_ENV_FLAG = "MARKETING_LLM_ENABLED"
_TRUTHY = ("1", "true", "yes")

#: The checklist, verbatim from contract §Critic. Kept as a constant so the test
#: suite can pin that the prompt still ships every item — a checklist that
#: quietly loses a line is a gate that quietly stops gating.
CHECKLIST: tuple[str, ...] = (
    "Does it parse with ZERO context? The reader sees only these words: no "
    "chart, no ticker page, no earlier post, no idea what desk wrote it.",
    "Does every 'it', 'that', 'this', 'the level', 'the line' point at "
    "something this post already named?",
    "Is there internal jargon: the screen, the board, graded, the plan, our "
    "model, the system, or a count with no denominator ('18 groups on the "
    "move', which is 18 of how many)?",
    "Is there an orphan hedge: an uncertainty tail ('historical, not a "
    "promise') with no base-rate stat in the post for it to be about?",
    "Does it sound like a person typing, or like a bot? Uniformly clipped "
    "sentences, three fragments in a row, and stacked aphorisms are bot tells.",
    "Does it use advice language on a post that is not a signal (telling the "
    "reader to buy, sell, enter, or size)?",
)

SYSTEM_PROMPT = (
    "You are a cold reader. Someone hands you one post from a finance account "
    "on X. You have never seen this account, this chart, this ticker or any "
    "earlier post. You are the reader scrolling past at speed.\n\n"
    "Your ONLY job is to say whether this post works for that reader. You do "
    "not rewrite it. You do not suggest copy. You do not add facts, numbers or "
    "context. You judge what is in front of you.\n\n"
    # No em dashes anywhere in this prompt, and that is not pedantry: the
    # critic's `reasons` are echoed verbatim into the WRITER's repair turn, and
    # a model that has just read an em dash is a model that writes one. The
    # house dash ban is validator-enforced on copy (banned_language), so a
    # leaked dash would cost a whole post on the repair round.
    "CHECKLIST, reject if any of these fails:\n"
    + "\n".join(f"{i}. {c}" for i, c in enumerate(CHECKLIST, 1))
    + "\n\nBE HONEST BUT NOT PRECIOUS. This register is deadpan, terse and "
    "fragmentary on purpose. Short is not a defect. Dry is not a defect. A "
    "sentence fragment is not a defect. Rejecting good terse copy is as "
    "expensive as passing bad copy, so reject only what a real reader would "
    "actually stumble on or roll their eyes at.\n\n"
    "OUTPUT: one JSON object, exactly {\"verdict\": \"pass\" or \"reject\", "
    "\"reasons\": [\"...\"]}. Reasons are one short phrase each, at most three "
    "of them, and only on a reject. No markdown, no preamble, no other keys."
)


# ─────────────────────────────────────────────────────────────────────────────
# Counters (the dry run's report reads these)
# ─────────────────────────────────────────────────────────────────────────────

_STAT_KEYS = ("calls", "pass", "reject", "unavailable", "off")
_STATS: dict[str, int] = {k: 0 for k in _STAT_KEYS}
#: The WRITER calls this from a ThreadPoolExecutor (one worker per post), so
#: every counter bump here is concurrent. ``d[k] += 1`` is a read-modify-write,
#: not an atomic bytecode: two workers finishing together lose a count and the
#: dry run's reject_rate quietly under-reports. The writer's counters got this
#: lock; the critic's were missed.
_STATS_LOCK = threading.Lock()

#: One provider waterfall per (lane, model, transport) for the whole process.
#: `build_providers` reads config, walks the OAuth pool and the broker, touches
#: the usage ledger and CONSTRUCTS AN HTTP CLIENT — doing that once per post
#: meant N of everything per night, N unclosed clients across the worker pool,
#: and a per-post cost on the lane whose whole job is to be cheap.
_PROVIDER_CACHE: dict[tuple, list] = {}
_PROVIDER_LOCK = threading.Lock()

#: The mute-lane annotation is a statement about the RUN, not about a post. One
#: per process: a credential-less night otherwise printed the identical warning
#: once per planned post, which buries every other annotation in the step.
_WARNED: set[str] = set()


def _bump(key: str, n: int = 1) -> None:
    with _STATS_LOCK:
        _STATS[key] = max(0, _STATS.get(key, 0) + n)


def critic_stats() -> dict:
    """Counters for this process, plus a derived ``reject_rate``. A copy."""
    with _STATS_LOCK:
        out = dict(_STATS)
    judged = out.get("pass", 0) + out.get("reject", 0)
    out["reject_rate"] = round(out.get("reject", 0) / judged, 4) if judged else 0.0
    return out


def reset_critic_stats() -> None:
    """Zero the counters and forget the cached providers. Dry run + tests.

    The provider cache is process-scoped, so a test that monkeypatches
    ``llm_auth.build_providers`` would otherwise inherit the previous test's
    waterfall. Resetting the counters is exactly the moment a caller means "new
    run", so the cache and the once-per-process annotation flag reset with them.
    """
    with _STATS_LOCK:
        for k in _STAT_KEYS:
            _STATS[k] = 0
    with _PROVIDER_LOCK:
        _PROVIDER_CACHE.clear()
        _WARNED.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────

def _critic_cfg(cfg: dict | None) -> dict:
    """Resolve the ``copywriter.llm.critic`` block from whatever `cfg` is.

    Tolerates the full marketing config (has ``copywriter``), the ``copywriter``
    block (has ``llm``), the ``llm`` block (has ``critic``), or the critic block
    itself — the same tolerance ``hot_tape_llm._llm_cfg`` applies, so a caller
    that already narrowed the config cannot silently disarm the gate.
    """
    if not isinstance(cfg, dict):
        return {}
    node: dict = cfg
    for key in ("copywriter", "llm"):
        nxt = node.get(key)
        if isinstance(nxt, dict):
            node = nxt
    critic = node.get("critic")
    if isinstance(critic, dict):
        return critic
    # `node` is already the critic block when the caller narrowed that far.
    return node if ("max_tokens" in node or "enabled" in node) else {}


def _topic_line(ctx: dict) -> str:
    """ONE line of what the post is nominally about. Never the fact packet.

    Handing the critic the facts would recreate the authorship bias it exists to
    break: a reader who has been told the answer can always find it in the post.
    """
    cashtag = str(ctx.get("cashtag") or "").strip()
    if cashtag:
        return f"a post about {cashtag}"
    theme = str(ctx.get("theme_name") or "").strip()
    if theme:
        return f"a post about the {theme} group"
    kind = str(ctx.get("type") or "").strip()
    return f"a {kind} post about the market" if kind else "a market post"


#: Same slice the writer payload takes, so the critic and the writer are looking
#: at the same licensed numbers (copywriter._PAYLOAD_WHITELIST_MAX).
_WHITELIST_MAX = 24


def _build_user_message(text: str, ctx: dict) -> str:
    whitelist = (ctx.get("numbers_whitelist") or [])[:_WHITELIST_MAX]
    return (
        f"KIND: {ctx.get('type') or 'unknown'}\n"
        f"SHAPE: {ctx.get('shape') or 'two_part'}\n"
        f"TOPIC: {_topic_line(ctx)}\n"
        "NUMBERS THE DESK COMPUTED (the post may use these; you are not "
        "checking arithmetic, only whether the post reads):\n"
        + ("\n".join(f"  {n}" for n in whitelist) if whitelist else "  (none)")
        + "\n\nTHE POST:\n"
        + str(text or "")
    )


def _parse_verdict(raw: str) -> dict | None:
    """Pull {"verdict", "reasons"} out of a model reply. None when unusable.

    Everything else in the reply is discarded on purpose: a critic that returns
    a rewritten post has returned nothing this function will read (law 1).
    """
    txt = str(raw or "").strip()
    if not txt:
        return None
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt).strip()
    # raw_decode at each brace, not a greedy `\{.*\}`: a reply carrying two
    # objects (a note, then the verdict) matched from the first brace to the
    # last, failed to parse, and became an "unparseable_reply" pass.
    obj = None
    decoder = json.JSONDecoder()
    for i, ch in enumerate(txt):
        if ch != "{":
            continue
        try:
            candidate, _end = decoder.raw_decode(txt[i:])
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get("verdict") is not None:
            obj = candidate
            break
    if not isinstance(obj, dict):
        return None
    verdict = str(obj.get("verdict") or "").strip().lower()
    if verdict not in ("pass", "reject"):
        return None
    reasons_raw = obj.get("reasons")
    reasons: list[str] = []
    if isinstance(reasons_raw, list):
        reasons = [str(r).strip() for r in reasons_raw if str(r).strip()][:3]
    elif isinstance(reasons_raw, str) and reasons_raw.strip():
        reasons = [reasons_raw.strip()]
    if verdict == "reject" and not reasons:
        # A reject with no reason cannot be repaired against, so it is not a
        # usable verdict. Treat it as an unusable reply rather than dropping a
        # post for an unstated fault.
        reasons = ["critic rejected without a stated reason"]
    return {"verdict": verdict, "reasons": reasons}


#: Contract §Critic pins the reason string a provider failure returns, because
#: it is an interface: Builder B's consumers switch on it. The specific cause
#: travels in ``detail`` so nothing is lost by pinning the reason.
UNAVAILABLE_REASON = "critic_unavailable"


def _unavailable(reason: str, *, annotate: bool = True) -> dict:
    """Pass-with-a-record. The critic failing is never the post's fault.

    Returns exactly ``{"verdict": "pass", "reasons": ["critic_unavailable"],
    "detail": <cause>}`` per contract §Critic. The cause used to be glued onto
    the reason string ("critic_unavailable:no_credential"), which made the
    contracted value unmatchable by equality for every consumer downstream.
    """
    _bump("unavailable")
    if annotate:
        with _PROVIDER_LOCK:
            first = reason not in _WARNED
            _WARNED.add(reason)
        if first:
            # A BARE print at line start with flush: GitHub only parses `::` at
            # column 0, and every logger in this repo prefixes the line, so an
            # annotation routed through log.warning is dropped silently
            # (tests/test_gh_annotation_line_start.py). flush because stdout is
            # block-buffered when piped in Actions. Once per cause per process:
            # the fault is the RUN's, and one alarm per post buries the step.
            print(f"::warning title=marketing_critic_unavailable::The cold-read "
                  f"critic could not judge the planned posts on this run "
                  f"({reason}) and they ship on the deterministic gates alone. "
                  f"Masterplan gate 5 wants a model pass on every planned post; "
                  f"check the provider credentials on this step. This warning "
                  f"is printed once per run, not once per post.", flush=True)
        else:
            log.warning("copy_critic: unavailable (%s) — already annotated once "
                        "for this run", reason)
    return {"verdict": "pass", "reasons": [UNAVAILABLE_REASON], "detail": reason}


def _providers(critic_cfg: dict) -> list:
    """The provider waterfall for this critic config. Built ONCE per process.

    Keyed on everything that changes the waterfall (lane, model, transport
    settings) so a config change still rebuilds. Built inside the lock rather
    than around a check-then-build, because two writer workers racing here is
    exactly how the duplicate clients appeared in the first place.
    """
    key = (
        str(critic_cfg.get("usage_lane", "marketing-critic")),
        _model_id(critic_cfg),
        str(critic_cfg.get("client_max_retries", DEFAULT_CLIENT_MAX_RETRIES)),
        str(critic_cfg.get("client_timeout_s", DEFAULT_CLIENT_TIMEOUT_S)),
    )
    with _PROVIDER_LOCK:
        if key in _PROVIDER_CACHE:
            return _PROVIDER_CACHE[key]
        from engine import llm_auth  # noqa: PLC0415

        providers = llm_auth.build_providers(
            {
                "usage_lane": key[0],
                "client_max_retries": critic_cfg.get(
                    "client_max_retries", DEFAULT_CLIENT_MAX_RETRIES),
                "client_timeout_s": critic_cfg.get(
                    "client_timeout_s", DEFAULT_CLIENT_TIMEOUT_S),
            },
            opus_model=key[1],
        )
        _PROVIDER_CACHE[key] = providers
        return providers


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def cold_read_verdict(text: str, ctx: dict, cfg: dict | None = None) -> dict:
    """Judge one post as a reader with zero context. NEVER raises.

    Returns ``{"verdict": "pass"|"reject", "reasons": [str]}``.

    A ``reject`` costs the writer ONE repair round; a second reject drops the
    post (masterplan §0 gate 5). Every non-judgement returns ``pass`` with the
    reason recorded, because the deterministic validators have already run and a
    silent critic must not become a silent censor:

      lane switched off in config   -> reasons ``["critic_disabled"]``
      env flag absent               -> reasons ``["critic_off"]``
      empty post                    -> reasons ``["critic_skipped:empty"]``
      no credential / provider error / unparseable reply
                                    -> reasons ``["critic_unavailable"]`` plus
                                       ``detail`` (contract §Critic pins the
                                       reason string; the cause travels beside
                                       it so consumers can match on equality).
    """
    _bump("calls")

    critic_cfg = _critic_cfg(cfg)
    if not bool(critic_cfg.get("enabled", True)):
        _bump("off")
        return {"verdict": "pass", "reasons": ["critic_disabled"]}
    if os.environ.get(_ENV_FLAG, "").strip().lower() not in _TRUTHY:
        # Same two-key arming as every other model lane in this package: config
        # says on AND the env flag says on. Tests and local runs never call out.
        _bump("off")
        return {"verdict": "pass", "reasons": ["critic_off"]}

    body = str(text or "").strip()
    if not body:
        return {"verdict": "pass", "reasons": ["critic_skipped:empty"]}

    try:
        providers = _providers(critic_cfg)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"provider_build:{type(exc).__name__}")

    if not providers:
        return _unavailable("no_credential")

    try:
        max_tokens = int(critic_cfg.get("max_tokens", DEFAULT_MAX_TOKENS))
    except (TypeError, ValueError):
        max_tokens = DEFAULT_MAX_TOKENS
    max_tokens = min(max_tokens, DEFAULT_MAX_TOKENS)  # contract: <= 200

    user_msg = _build_user_message(body, ctx or {})

    def _do_call(client, model):
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            return None, "stop_refusal", resp
        out = "".join(b.text for b in resp.content
                      if getattr(b, "type", "") == "text")
        return (out or None), None, resp

    try:
        from engine import llm_auth  # noqa: PLC0415 — import closure law

        raw, reason, _provider = llm_auth.make_call(
            providers, _do_call, context="marketing_critic")
    except Exception as exc:  # noqa: BLE001 — a critic must never break a night
        return _unavailable(f"call:{type(exc).__name__}")

    if not raw:
        return _unavailable(f"empty_reply:{reason or 'none'}")

    verdict = _parse_verdict(raw)
    if verdict is None:
        return _unavailable("unparseable_reply")

    _bump(verdict["verdict"])
    return verdict


def _model_id(critic_cfg: dict) -> str:
    """`llm_models.marketing_critic`, else `marketing_copy`, else the literal.

    A dedicated key lets the operator run the critic on a cheaper or a stronger
    model than the writer without touching code; absent, it rides the writer's.
    """
    if critic_cfg.get("model"):
        return str(critic_cfg["model"])
    models: dict = {}
    try:
        from lib import config as _config  # noqa: PLC0415
        models = (_config.load() or {}).get("llm_models", {}) or {}
    except Exception:  # noqa: BLE001
        try:
            import yaml as _yaml  # noqa: PLC0415
            from pathlib import Path as _Path  # noqa: PLC0415
            _cfgp = _Path(__file__).resolve().parents[2] / "config.yml"
            models = (_yaml.safe_load(
                _cfgp.read_text(encoding="utf-8")) or {}).get("llm_models", {}) or {}
        except Exception:  # noqa: BLE001
            models = {}
    for key in ("marketing_critic", "marketing_copy"):
        if models.get(key):
            return str(models[key])
    return "claude-sonnet-4-6"
