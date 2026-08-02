"""engine.marketing.copy_auditor — the operator's stand-in over a whole batch.

Operator order 2026-07-30: "Have a LLM auditor approve or disapprove of planned
posts for at least 1 week. You need to ensure that the auditor knows what to look
out for and to be able to stop posts that are bad (bot like posts, doesn't make
sense, has errors, repetitive posts, and other things that you think i would
reject to as well as things that are very obvious errors in our system)."

WHY THIS EXISTS BESIDE THE CRITIC
---------------------------------
``copy_critic.cold_read_verdict`` judges ONE post as a reader with no context.
That catches a post which does not parse on its own. It structurally cannot
catch the defect that actually got a batch rejected:

    Five of six posts closed with the same sentence.

Nor can the deterministic gates. ``stock_closer_violations`` matches known
strings and exact repeats; it passed a batch where four posts said "respect the
strength, don't chase" in four different wordings. That is monotony a human sees
instantly and no regex sees at all.

So this auditor reads the WHOLE DAY AT ONCE and answers a different question:
*if a real person opened this account today and scrolled, would they follow, or
would they smell a bot?*

CONTRACT
--------
DE-ESCALATION ONLY. The auditor may CUT a post and must say why. It may never
rewrite one, never raise a score, never add a post, and never promote anything.
That is the house epistemics law (CLAUDE.md §Epistemics: "LLMs may only
de-escalate calibrated keys — never originate signals, scores, or escalations")
and it is what makes a model safe in a publishing path at all.

NEVER RAISES. Every failure returns verdicts, never an exception. What it does
NOT do is fail silently: an audit that could not run marks every post
``unaudited`` with the reason, and the publisher decides what to do with that.
During the operator's one-week probation the intended reading of ``unaudited``
is "hold", not "ship" — an unaudited batch is exactly the case the probation
exists to prevent.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

logger = logging.getLogger(__name__)

_ENV_FLAG = "MARKETING_LLM_ENABLED"
_TRUTHY = ("1", "true", "yes")

DEFAULT_CLIENT_MAX_RETRIES = 2
DEFAULT_CLIENT_TIMEOUT_S = 90

#: How many posts go into one audit call. The whole point is cross-post
#: comparison, so the window has to be big enough to see repetition — but a
#: window past ~25 posts starts losing the tail of the list in the reply.
_DEFAULT_WINDOW = 20

_PROVIDER_CACHE: dict[tuple, list] = {}
_PROVIDER_LOCK = threading.Lock()

#: The operator's own rejection criteria, in their words where possible. This is
#: the whole value of the auditor: a list written from posts that were actually
#: rejected, not from an abstract idea of quality.
AUDIT_CRITERIA: tuple[tuple[str, str], ...] = (
    ("bot_voice",
     "Reads like a machine. Stock phrases, a closing sentence that could be "
     "pasted onto any post, the same sentence shape every time."),
    ("repetitive",
     "Says what another post in this same batch already said — same closer, "
     "same structure, same idea in different words. Judge the BATCH, not the "
     "post: four posts that each say 'respect the move, don't chase' in "
     "different wordings are three posts too many."),
    ("lectures",
     "Talks down to the reader. Tells them what they get wrong, what 'most "
     "people' fail to grasp, or what they should do. Any whiff of superiority, "
     "ego, or arrogance. These desks are not the smartest person in the room "
     "and must never sound like they think they are."),
    ("no_thesis",
     "A stat dump. Lists numbers with no argument connecting them and no "
     "reason the reader should care. Three sentences that each open with the "
     "same ticker is this defect."),
    ("makes_no_sense",
     "Does not parse for someone who has not seen our screen. Refers to "
     "something it never named. Contradicts itself."),
    ("has_errors",
     "Numbers that disagree with each other or with the stated fact, a broken "
     "cashtag, a mangled date, obvious system output that leaked into the copy "
     "(placeholder text, a template variable, an internal name)."),
    ("no_value",
     "True but worthless. Says nothing a reader could act on, learn from, or "
     "react to. 'I'm watching' with no level and no reason is this."),
    # 2026-08-01. Three macro/event posts cleared every deterministic gate,
    # cleared THIS auditor, were approved, and were then pulled by hand:
    # "4 of 11 sectors green on a day growth data firmed and inflation stayed
    # warm." The owner's words are the definition, verbatim, because the
    # paraphrase is what let it through the first time — `no_value` was already
    # in this list and did not catch it, since the posts do carry a fact and a
    # stance. What they do not carry is a PRINT, and that is the cut.
    ("esoteric",
     "Desk-speak a general reader cannot decode. Gestures at 'growth data', "
     "'inflation readings', 'liquidity' or 'the tape' without ever naming the "
     "actual release and its number, so there is nothing to look up, agree "
     "with or argue against. The owner's own words for this: 'too bland, too "
     "weak, no real value, so esoteric no one knows what it's talking about, "
     "zero engagement, people might even report us cuz only bots/llm write "
     "garbage like this.' A macro read names the print ('jobless claims at "
     "203,000, 8.6% below a year ago') or it is filler. A count of our own "
     "sectors is not a print."),
)

_VERDICT_KEEP = "keep"
_VERDICT_CUT = "cut"


def _audit_cfg(cfg: dict | None) -> dict:
    root = (cfg or {}).get("copywriter") or {}
    llm = root.get("llm") or {}
    node = llm.get("auditor") or {}
    out = dict(node)
    out.setdefault("enabled", True)
    out.setdefault("provider_order", ["codex", "oauth", "anthropic", "deepseek"])
    # TERRA, not Sol: the auditor reads and judges, it never writes. Same
    # reasoning as the cold-read critic, and the cross-model pairing is
    # deliberate — a judge that shares the writer's blind spots is decoration.
    out.setdefault("codex_source_model", "gpt-5.6-terra")
    out.setdefault("codex_reasoning_effort", "medium")
    out.setdefault("oauth_pool_lane", "marketing-auditor")
    out.setdefault("usage_lane", "marketing-auditor")
    out.setdefault("window", _DEFAULT_WINDOW)
    return out


def _armed() -> bool:
    return str(os.environ.get(_ENV_FLAG, "")).strip().lower() in _TRUTHY


def _providers(acfg: dict) -> list:
    order = list(acfg.get("provider_order") or [])
    codex_model = str(acfg.get("codex_source_model", "gpt-5.6-terra"))
    key = (
        str(acfg.get("usage_lane")), str(acfg.get("oauth_pool_lane")),
        ",".join(order), codex_model,
        str(acfg.get("codex_reasoning_effort", "medium")),
    )
    with _PROVIDER_LOCK:
        if key in _PROVIDER_CACHE:
            return _PROVIDER_CACHE[key]
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(
            {
                "usage_lane": key[0],
                "oauth_pool_lane": key[1],
                "provider_order": order,
                "codex_source_model": codex_model,
                "codex_reasoning_effort": acfg.get("codex_reasoning_effort", "medium"),
                "client_max_retries": acfg.get(
                    "client_max_retries", DEFAULT_CLIENT_MAX_RETRIES),
                "client_timeout_s": acfg.get(
                    "client_timeout_s", DEFAULT_CLIENT_TIMEOUT_S),
            },
            opus_model=str(acfg.get("model") or "claude-opus-4-1"),
        )
        _PROVIDER_CACHE[key] = providers
        return providers


def _system_prompt() -> str:
    lines = [
        "You are the final reader before these posts go out on X. You are "
        "standing in for the account owner, who is strict and has rejected "
        "whole batches before.",
        "",
        "You are shown ONE ACCOUNT'S POSTS FOR ONE DAY, numbered. Judge them "
        "TOGETHER. The most important thing you can catch is repetition across "
        "the batch, because no automated check upstream of you can see it.",
        "",
        "Cut a post if ANY of these is true:",
    ]
    for code, desc in AUDIT_CRITERIA:
        lines.append(f"  - {code}: {desc}")
    lines += [
        "",
        "You may ONLY keep or cut. Never rewrite, never suggest replacement "
        "copy, never invent a post. If you are unsure, keep it and say why in "
        "the note — a false cut costs a good post, and the owner would rather "
        "see a borderline post than an empty feed.",
        "",
        "Reply with STRICT JSON and nothing else:",
        '{"verdicts":[{"n":1,"verdict":"keep"|"cut","codes":["bot_voice"],'
        '"note":"one short sentence"}],"batch_note":"one sentence on how the '
        'day reads as a whole"}',
        "",
        "codes must be drawn from the list above. A keep has an empty codes "
        "list. Every cut needs at least one code and a note.",
    ]
    return "\n".join(lines)


def _user_message(posts: list[dict]) -> str:
    out = []
    for i, p in enumerate(posts, 1):
        acct = str(p.get("account") or "?")
        kind = str(p.get("kind") or p.get("type") or "?")
        text = str(p.get("text") or "").strip()
        out.append(f"[{i}] ({acct} · {kind})\n{text}")
    return "\n\n".join(out)


def _parse(raw: str, n: int) -> tuple[list[dict] | None, str]:
    """Parse the auditor reply into per-post verdicts. (None, reason) on failure."""
    s = str(raw or "").strip()
    if not s:
        return None, "empty reply"
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None, "no JSON object in reply"
    try:
        obj = json.loads(m.group(0))
    except Exception as exc:  # noqa: BLE001
        return None, f"unparseable JSON: {exc}"
    rows = obj.get("verdicts")
    if not isinstance(rows, list):
        return None, "no verdicts array"

    by_n: dict[int, dict] = {}
    valid_codes = {c for c, _ in AUDIT_CRITERIA}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("n"))
        except (TypeError, ValueError):
            continue
        if not 1 <= idx <= n:
            continue
        verdict = str(row.get("verdict") or "").strip().lower()
        if verdict not in (_VERDICT_KEEP, _VERDICT_CUT):
            continue
        codes = [str(c).strip() for c in (row.get("codes") or [])
                 if str(c).strip() in valid_codes]
        # A cut with no recognisable code is not actionable — the operator asked
        # for reasons, and "cut because" is not one. Downgrade to keep so a
        # sloppy reply cannot silently delete the day.
        if verdict == _VERDICT_CUT and not codes:
            verdict, codes = _VERDICT_KEEP, []
        by_n[idx] = {
            "verdict": verdict,
            "codes": codes,
            "note": str(row.get("note") or "").strip()[:200],
        }
    if not by_n:
        return None, "no usable verdicts"
    return [by_n.get(i, {"verdict": _VERDICT_KEEP, "codes": [],
                         "note": "not judged"}) for i in range(1, n + 1)], ""


def _unaudited(posts: list[dict], reason: str) -> dict:
    """Every post marked unaudited, with the reason. NOT a pass."""
    print(f"::warning title=marketing-auditor-unavailable::audit did not run "
          f"({reason}); {len(posts)} posts are unaudited", flush=True)
    return {
        "ok": False,
        "reason": reason,
        "verdicts": [
            {"verdict": "unaudited", "codes": [], "note": reason} for _ in posts
        ],
        "kept": len(posts), "cut": 0, "unaudited": len(posts),
        "batch_note": "",
    }


def audit_batch(posts: list[dict], *, cfg: dict | None = None) -> dict:
    """Judge a day's posts together. NEVER raises.

    ``posts`` is a list of ``{"text", "account", "kind"}`` dicts. Returns::

        {"ok": bool, "verdicts": [{"verdict","codes","note"}, ...],
         "kept": int, "cut": int, "unaudited": int, "batch_note": str}

    ``verdicts`` is index-aligned with ``posts``. A verdict is ``keep``, ``cut``
    or ``unaudited`` — the last one is NOT a pass; see the module docstring.
    """
    rows = [p for p in (posts or []) if isinstance(p, dict)]
    if not rows:
        return {"ok": True, "verdicts": [], "kept": 0, "cut": 0,
                "unaudited": 0, "batch_note": "", "reason": "empty batch"}

    acfg = _audit_cfg(cfg)
    if not acfg.get("enabled", True):
        return _unaudited(rows, "auditor disabled in config")
    if not _armed():
        return _unaudited(rows, f"{_ENV_FLAG} not set")

    try:
        providers = _providers(acfg)
    except Exception as exc:  # noqa: BLE001
        return _unaudited(rows, f"provider build failed: {exc}")
    if not providers:
        return _unaudited(rows, "no provider available")

    system = _system_prompt()
    user = _user_message(rows)

    # The waterfall walk belongs to llm_auth.make_call — it owns the pool
    # bookkeeping, the cooling ledger and the per-rung fallback. Hand-rolling a
    # `for provider in providers` loop here would post the calls without the
    # accounting, which is the defect the key ledger exists to make visible.
    def _do_call(client, model):
        resp = client.messages.create(
            model=model,
            max_tokens=int(acfg.get("max_tokens", 1600)),
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            return None, "stop_refusal", resp
        out = "".join(b.text for b in resp.content
                      if getattr(b, "type", "") == "text")
        return (out or None), None, resp

    try:
        from engine import llm_auth  # noqa: PLC0415 — import closure law
        raw, reason, _provider = llm_auth.make_call(
            providers, _do_call, context="marketing_auditor")
    except Exception as exc:  # noqa: BLE001 — an auditor must never break a night
        return _unaudited(rows, f"call failed: {type(exc).__name__}")
    if not str(raw or "").strip():
        return _unaudited(rows, f"no provider returned text ({reason or 'empty'})")

    verdicts, err = _parse(raw, len(rows))
    if verdicts is None:
        return _unaudited(rows, f"unusable reply: {err}")

    batch_note = ""
    try:
        m = re.search(r"\{.*\}", str(raw), re.S)
        batch_note = str(json.loads(m.group(0)).get("batch_note") or "")[:300]
    except Exception:  # noqa: BLE001
        pass

    cut = sum(1 for v in verdicts if v["verdict"] == _VERDICT_CUT)
    return {
        "ok": True,
        "verdicts": verdicts,
        "kept": len(verdicts) - cut,
        "cut": cut,
        "unaudited": 0,
        "batch_note": batch_note,
        "reason": "",
    }


def window_size(cfg: dict | None = None) -> int:
    try:
        n = int(_audit_cfg(cfg).get("window", _DEFAULT_WINDOW))
    except (TypeError, ValueError):
        return _DEFAULT_WINDOW
    return max(2, min(n, 40))


def max_audit_day(cfg: dict | None = None) -> int | None:
    """Deepest plan day the auditor reads. None = the whole horizon.

    The auditor used to be pinned to D1 in code. That silently exempted the
    EVERGREEN forward tail, which is the part of the plan that ships as
    written: ``drop_stale_forward_bookings`` keeps watchlist/receipt copy at the
    full seven-day horizon deliberately, and a forward-booked post really does
    reach its slot. On the 2026-07-30 plan that was 73 unjudged watchlist posts.

    ``0`` (the shipped default) and any non-positive value mean "no limit"; a
    positive N restores a D1..DN cap.
    """
    try:
        n = int(_audit_cfg(cfg).get("max_day", 0))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None
