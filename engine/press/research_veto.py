"""engine.press.research_veto — the W2R LLM veto pass.  IT CAN ONLY DEMOTE.

The deterministic W-score (engine/press/research_triage.py) ranks every report
in the vault window.  This module lets the cheapest model in the existing
`engine.llm_auth` waterfall read the RANKED HEAD and say "this one is thin /
paywalled / a duplicate" — and nothing else.

DEMOTE-ONLY IS ENFORCED BY CONSTRUCTION, not by asking nicely:

  * THIS MODULE PERFORMS NO ARITHMETIC ON ANY SCORE.  It returns a mapping of
    ``{report_id: {"reason", "model", "provider"}}``.  There is no rank in the
    return value, no number the model produced, and no code path here that could
    write one.  ``research_triage.apply_vetoes`` is the only function in the
    repo that turns a verdict into a number, and it clamps the multiplier into
    [0, 1] and takes ``min(new, old)``.
  * The ONLY vocabulary honoured is ``research_triage.VETO_REASONS``
    ({thin, paywalled, duplicate}).  Any other verdict word is discarded — a
    model answering off-contract has not earned a rank change in EITHER
    direction, and "promote" is simply not a word this parser knows.
  * Only ids that were IN THE SUBMITTED BATCH are accepted.  A hallucinated id
    cannot demote a report, and cannot reach the ledger.

That is the house epistemics law in its narrowest form: "LLMs may only
de-escalate calibrated keys — never originate signals, scores, or escalations".

SPEND.  Credentials resolve through the existing waterfall (OAuth pool ->
CLAUDE_CODE_OAUTH_TOKEN -> ANTHROPIC_API_KEY -> DEEPSEEK_API_KEY).  Usage is
recorded to the EXISTING lib.ai_costs ledger by ``llm_auth.make_call`` itself,
under the ``usage_lane`` this module passes to ``build_providers`` — no new
spend path, no new ledger.  With no credential visible, ``build_providers``
returns [] and this pass reports ``no_provider`` and demotes NOTHING, which is
the safe direction by construction: an unavailable veto leaves the deterministic
ranking exactly as the engine computed it.

BATCHING.  One call per ``batch_size`` reports over the top ``head_size``, so
covering the head costs a handful of cheap completions a day.  Both are config
keys under config/press.yml ``research_triage.veto``.

NO NETWORK EXCEPT THE MODEL CALL.  No browsing, no fetching, no enrichment — the
fact-anchor law ("every number traces to supplied sources") is why the veto sees
only what the vault already extracted.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Iterable

from engine.press.research_triage import (
    VETO_ELIGIBLE_STATUSES, VETO_REASONS, _VETO_DEFAULTS, _get,
)

log = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)

#: The DeepSeek rung's model when config names none.  `deepseek-v4-flash` is the
#: cheap tier this repo already uses for mechanical work (engine/master_brain.py
#: translate lane); llm_auth's own default is `deepseek-v4-pro`, a tier up.
_DEEPSEEK_FALLBACK = "deepseek-v4-flash"

_SYSTEM = """\
You are a research desk's triage reviewer. You are reviewing candidate
institutional research reports that a DETERMINISTIC ENGINE has already scored
and ranked. You are NOT ranking them and you are NOT scoring them.

YOUR ONLY POWER IS TO DEMOTE. You may flag a report as unsuitable for an
article. You cannot promote one, you cannot re-order the list, and you cannot
assign a number to anything. There is no field in the response format for any
of those, and any such output is discarded unread.

Flag a report ONLY when one of these three is plainly true from the material
shown:

  thin       the extracted points carry no substance to write 500 words about —
             a headline restated, a single vague claim, boilerplate.
  paywalled  the extract is a subscriber-wall stub rather than research content.
  duplicate  it says the same thing as another report in the SAME batch; flag
             the weaker one, never both.

WHEN IN DOUBT, DO NOT FLAG. A report that is merely uninteresting to you is not
thin — the engine's score already handles interest. Flagging costs the desk a
piece it could have written; leaving a mediocre report in place costs it one
place in a reading order.

RESPOND WITH ONE JSON ARRAY AND NOTHING ELSE. No prose, no code fence:

  [{"id": "<report id, copied exactly>", "demote": true,
    "reason": "thin" | "paywalled" | "duplicate"}]

Return [] when nothing should be flagged. That is a normal, common answer.
"""


def _clean(text: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def build_prompt(rows: list[dict], *, max_points: int = 6,
                 point_chars: int = 220) -> tuple[str, str]:
    """(system, user) for one batch.  Deterministic given the same rows."""
    parts: list[str] = ["CANDIDATE REPORTS:", ""]
    for row in rows:
        parts.append(f'- id: {row.get("report_id")}')
        parts.append(f'  institution: {_clean(row.get("institution"), 80)}')
        parts.append(f'  title: {_clean(row.get("title"), 200)}')
        points = list(row.get("summary_points") or [])[:max_points]
        if points:
            parts.append("  extracted points:")
            parts.extend(f"    * {_clean(p, point_chars)}" for p in points)
        else:
            parts.append("  extracted points: (none)")
        parts.append("")
    parts.append("Return the JSON array now.")
    return _SYSTEM, "\n".join(parts)


def parse_verdicts(raw_text: str, allowed_ids: Iterable[str]) -> dict[str, str]:
    """Parse the model's array into ``{report_id: reason}``.

    THE WHOLE PARSER IS A FILTER.  Unknown ids are dropped, unknown reasons are
    dropped, ``demote`` values that are not truthy are dropped, and there is no
    branch anywhere that reads a number.  An unparsable response yields {} — a
    veto pass that cannot be understood demotes nothing.
    """
    allowed = {str(i) for i in allowed_ids}
    text = _FENCE_RE.sub("", str(raw_text or "").strip())
    obj: Any = None
    try:
        obj = json.loads(text)
    except ValueError:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except ValueError:
                return {}
        else:
            return {}

    if isinstance(obj, dict):
        obj = obj.get("demote") or obj.get("verdicts") or obj.get("results") or []
    if not isinstance(obj, list):
        return {}

    out: dict[str, str] = {}
    for entry in obj:
        if not isinstance(entry, dict):
            continue
        rid = str(entry.get("id") or "").strip()
        if rid not in allowed:
            if rid:
                log.warning("research_veto: verdict names unknown report id %r — discarded", rid)
            continue
        if not entry.get("demote", True):
            continue
        reason = str(entry.get("reason") or "").strip().lower()
        if reason not in VETO_REASONS:
            log.warning("research_veto: %s carries unknown reason %r — discarded", rid, reason)
            continue
        out[rid] = reason
    return out


def _model_id(model_key: str) -> str:
    """config.yml llm_models.<key> — the press writer's lookup idiom, verbatim."""
    try:
        from lib import config as _config  # noqa: PLC0415

        return str((_config.load().get("llm_models") or {}).get(model_key, "") or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("research_veto: llm_models lookup failed: %s", exc)
        return ""


def _default_call(system_prompt: str, user_prompt: str, *, model_id: str,
                  max_tokens: int, deepseek_model: str = "") -> tuple[str, str, str]:
    """The real model call.  Returns (text, provider_name, model_id).

    Usage lands in lib.ai_costs through llm_auth.make_call's own capture, under
    the ``usage_lane`` below — no new spend path is created here.
    """
    from engine import llm_auth  # noqa: PLC0415

    # BOTH MODEL PINS, or the cheapest-tier promise only holds on Anthropic
    # (review M12).  `build_providers` takes the Anthropic model through
    # `opus_model` and the DeepSeek rung through `deepseek_model`; passing only
    # the first meant a host with just DEEPSEEK_API_KEY ran this lane on that
    # provider's DEFAULT (`deepseek-v4-pro`) — a lane whose whole economic
    # argument is "the cheapest model that can answer" must not pick a tier by
    # accident.  The two ids are DIFFERENT strings on purpose: an Anthropic
    # model id is not a DeepSeek model id, so the pin is per-provider.
    providers = llm_auth.build_providers(
        {"usage_lane": "press-research-triage-veto"},
        opus_model=model_id,
        deepseek_model=deepseek_model or _DEEPSEEK_FALLBACK)
    if not providers:
        # ARMED BUT MUTE.  A bare print: an annotation behind a prefixing log
        # formatter is not a line start and GitHub drops it silently (house law).
        print("::warning title=research_veto_mute::research triage veto pass is enabled "
              "but no LLM provider credential is visible — the deterministic ranking "
              "stands unmodified (demote-only, so this is the safe direction).",
              flush=True)
        return "", "", model_id

    def _do_call(client, model):
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            return None, "stop_refusal", resp
        text = "".join(b.text for b in resp.content
                       if getattr(b, "type", "") == "text")
        return (text or None), None, resp

    raw, _reason, provider = llm_auth.make_call(
        providers, _do_call, context="press_research_veto")
    return str(raw or ""), str(provider or ""), model_id


def run(result: dict, *, cfg: dict | None = None,
        catalog: dict[str, dict] | None = None,
        call: Callable[..., tuple[str, str, str]] | None = None) -> dict:
    """Run the veto pass over a ranked result.

    `cfg` is the ``research_triage`` block.  `catalog` maps report id -> the
    vault item, so the prompt can show the extracted points the score was
    computed from.  `call` is the injection seam the tests use; production
    leaves it None and gets ``_default_call``.

    Returns::

        {"state": "ok" | "disabled" | "no_head" | "no_provider" | "call_failed",
         "vetoes": {report_id: {"reason", "model", "provider"}},
         "batches": n, "failed_batches": n, "head": n, "model": "..."}

    ``no_provider`` and ``call_failed`` are DISTINCT on purpose: the first sends
    the operator to the credential waterfall, the second to rate limits and
    provider health.  Collapsing them (both produce an empty veto map) would
    misdiagnose a 429 as a missing key.

    NEVER RAISES.  Every failure returns a state and an EMPTY veto map, which is
    the safe direction: the deterministic ranking stands.
    """
    vcfg = (cfg or {}).get("veto") if isinstance(cfg, dict) else None
    vcfg = vcfg if isinstance(vcfg, dict) else {}
    empty = {"state": "disabled", "vetoes": {}, "batches": 0, "failed_batches": 0,
             "head": 0, "model": ""}

    if not bool(_get(vcfg, "enabled", _VETO_DEFAULTS)):
        return empty

    head_size = max(0, int(_get(vcfg, "head_size", _VETO_DEFAULTS)))
    batch_size = max(1, int(_get(vcfg, "batch_size", _VETO_DEFAULTS)))
    max_tokens = max(64, int(_get(vcfg, "max_tokens", _VETO_DEFAULTS)))
    model_key = str(_get(vcfg, "model_key", _VETO_DEFAULTS))

    # ELIGIBILITY IS AN ALLOWLIST, NOT A SINGLE EXCLUSION (review M8).  The
    # first version excluded only `garbage_dropped`, so a row whose P0 gate
    # RAISED — and a row that never entered the ranking at all — reached the
    # model.  `VETO_ELIGIBLE_STATUSES` lives in research_triage so the two
    # modules cannot drift on what "rankable" means.
    head = [r for r in (result.get("rows") or [])
            if r.get("status") in VETO_ELIGIBLE_STATUSES][:head_size]
    if not head:
        return {**empty, "state": "no_head"}

    model_id = _model_id(model_key)
    if not model_id:
        log.warning("research_veto: no model id for llm_models.%s — pass skipped", model_key)
        return {**empty, "state": "no_provider"}

    deepseek_model = str(vcfg.get("deepseek_model") or _DEEPSEEK_FALLBACK)
    caller = call or (lambda s, u: _default_call(
        s, u, model_id=model_id, max_tokens=max_tokens,
        deepseek_model=deepseek_model))

    vetoes: dict[str, dict] = {}
    batches = 0
    failed = 0
    saw_provider = False
    for start in range(0, len(head), batch_size):
        chunk = head[start:start + batch_size]
        rows = []
        for row in chunk:
            item = (catalog or {}).get(str(row.get("report_id"))) or {}
            rows.append({
                "report_id": row.get("report_id"),
                "institution": row.get("institution"),
                "title": row.get("title"),
                "summary_points": item.get("summary_points") or [],
            })
        system_prompt, user_prompt = build_prompt(rows)
        try:
            raw, provider, model = caller(system_prompt, user_prompt)
        except Exception as exc:  # noqa: BLE001 — a veto failure must not stop triage
            log.warning("research_veto: batch %d call failed: %s", batches, exc)
            batches += 1
            failed += 1
            continue
        batches += 1
        if provider:
            saw_provider = True
        for rid, reason in parse_verdicts(raw, [r["report_id"] for r in rows]).items():
            vetoes[rid] = {"reason": reason, "model": str(model or model_id),
                           "provider": str(provider or "")}

    if saw_provider:
        state = "ok"
    elif failed:
        # A provider WAS built and every call to it raised: rate limits, a
        # provider outage, a malformed request. Reporting `no_provider` here
        # would send the operator to the credential waterfall for a 429.
        state = "call_failed"
    else:
        state = "no_provider"
    return {"state": state, "vetoes": vetoes, "batches": batches,
            "failed_batches": failed, "head": len(head), "model": model_id}


__all__ = ["build_prompt", "parse_verdicts", "run"]
