"""engine/marketing/blind_identity.py — the PRE-REGISTERED blind-identity eval (XG-W6).

Charter §8, assumptions register:

    "The >=80% blind-identity target is a point estimate with no n or CI, judged
     on samples from the generator it polices — pre-register the eval (sample
     size, holdout construction, chance = 20% baseline) in XG-W6 BEFORE the
     number gates anything."

So this module is the pre-registration and the harness, and **nothing else**.
``GATES_NOTHING = True`` is not decoration: the 80% figure gates no dial, no
promotion, and no publish path anywhere in this repo, and
``tests/test_marketing_learning.py`` greps the tree to keep it that way. The
eval has not been run — ``PREREG["status"] == "not_run"`` — and a target that
has never been measured must not be allowed to authorise anything.

**Why the pre-registration matters more than usual here.** The obvious way to
run this eval is to ask a model to guess which persona wrote each sample. That
model is a sibling of the generator being policed, so a good score may mean the
personas are distinct OR that two models share a prior. The prereg therefore
fixes the sample size, the holdout construction, the chance baseline, the
interval, and the promotion rule in advance, and records the confound in the
document rather than in a footnote discovered after a favourable result.

**Chance is 20%, not 50%.** Five personas, forced choice. An eval scoring 55%
looks like a coin-flip failure and is in fact 2.75x chance. Anchoring on the
wrong baseline is how a working system gets thrown away, so the baseline is a
constant here and the doc states it twice.

The companion document is ``docs/blind_identity_eval_prereg.md``, and a test
asserts the document and ``PREREG`` agree on every number — a prereg that can
drift from its own doc is not a prereg.

Public API:
    PREREG / GATES_NOTHING / CHANCE_BASELINE
    build_holdout(samples, *, n_per_persona, seed) -> dict
    grade(responses, holdout) -> dict
    wilson_interval(successes, n, z=1.96) -> (lo, hi)
    verdict(result) -> dict
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Any, Sequence

log = logging.getLogger(__name__)

#: THE ONLY CORRECT READING OF THE 80% NUMBER TODAY. It is a charter-recorded
#: hypothesis, not a gate. Nothing in this repo branches on it.
GATES_NOTHING: bool = True

#: Five personas, forced choice.
N_PERSONAS: int = 5
CHANCE_BASELINE: float = 1.0 / N_PERSONAS  # 0.20

PREREG: dict[str, Any] = {
    "id": "XG-W6-BIE-1",
    "title": "Blind identity discrimination across the five live editorial identities",
    "registered_at": "2026-07-28",
    "registered_by": "XG-W6 (charter §8 assumptions register)",
    "status": "not_run",

    "question": (
        "Given a post with every byline, handle, avatar and account-specific "
        "cashtag removed, can a blinded rater assign it to the correct one of "
        "five editorial identities better than chance?"
    ),

    # Sample size, declared in advance.
    "n_personas": N_PERSONAS,
    "personas": ["flagship", "meagan", "sophia", "kelly", "cici"],
    "n_per_persona": 30,
    "n_samples": 150,
    "chance_baseline": CHANCE_BASELINE,
    "charter_target": 0.80,   # the §8 point estimate — GATES NOTHING until run

    "holdout": {
        "construction": (
            "Stratified: exactly n_per_persona posts per identity, drawn from "
            "EMITTED posts only (persona_memory phrases.jsonl), excluding any "
            "post whose text was used to tune a codex."
        ),
        "blinding": (
            "Strip handle, byline, signature emoji, account-specific cashtags "
            "and franchise titles. A franchise title is a label, not a voice, "
            "and leaving it in measures our naming, not our writing."
        ),
        "date_span": "the trailing 60 days at run time, so no single week dominates",
        "assignment": "deterministic given (sample id, seed) — re-runnable and auditable",
        "seed": 20260728,
    },

    "promotion_rule": (
        "The eval supports a claim ONLY if the Wilson 95% lower bound on overall "
        "accuracy exceeds the 0.20 chance baseline AND no single identity's "
        "per-persona accuracy lower bound is at or below chance. A fleet average "
        "carried by two distinctive voices while three are indistinguishable is "
        "the failure this second clause exists to catch."
    ),
    "multiplicity": (
        "Five per-persona intervals plus one overall: report all six, apply "
        "Bonferroni (alpha 0.05/6) to the per-persona claims, and print every "
        "null. Concurrent-arm correction per charter §8 experiment law."
    ),
    "confound_declared_in_advance": (
        "The rater is a model of the same family as the generator, so a high "
        "score is consistent with 'the personas are distinct' AND with 'two "
        "models share a prior'. A human-rater arm is the disambiguator and is "
        "NOT part of this registration; until it runs, a passing result "
        "supports the weaker claim only."
    ),
    "nulls_printed": True,
    "gates": [],  # deliberately empty — see GATES_NOTHING
}


# ---------------------------------------------------------------------------
# Holdout construction
# ---------------------------------------------------------------------------
def _stable_rank(sample_id: str, seed: int) -> str:
    """Deterministic ordering key. Same (id, seed) always yields the same order,
    so a holdout is reproducible from the registration alone."""
    return hashlib.sha256(f"{seed}|{sample_id}".encode("utf-8")).hexdigest()


def build_holdout(
    samples: Sequence[dict],
    *,
    n_per_persona: int | None = None,
    seed: int | None = None,
) -> dict:
    """Draw the pre-registered stratified holdout from candidate samples.

    ``samples`` = ``[{"id": str, "persona": str, "text": str, "date": str}, ...]``.
    Returns the holdout plus a per-persona shortfall report: an identity with
    too few posts to fill its stratum is REPORTED, never quietly back-filled
    from another identity. Back-filling would make the confusion matrix's rows
    unequal and silently change what the accuracy number means.
    """
    per = int(n_per_persona if n_per_persona is not None else PREREG["n_per_persona"])
    sd = int(seed if seed is not None else PREREG["holdout"]["seed"])
    wanted = list(PREREG["personas"])

    by_persona: dict[str, list[dict]] = {p: [] for p in wanted}
    skipped_unknown = 0
    for s in samples:
        p = str(s.get("persona") or "")
        if p not in by_persona:
            skipped_unknown += 1
            continue
        if not str(s.get("text") or "").strip():
            continue
        by_persona[p].append(dict(s))

    items: list[dict] = []
    shortfall: dict[str, int] = {}
    for persona in wanted:
        pool = sorted(by_persona[persona],
                      key=lambda s: _stable_rank(str(s.get("id") or s.get("text")), sd))
        take = pool[:per]
        if len(take) < per:
            shortfall[persona] = per - len(take)
        for s in take:
            items.append({
                "sample_id": str(s.get("id") or _stable_rank(str(s.get("text")), sd)[:12]),
                "truth": persona,
                "text": blind(str(s.get("text") or ""), persona=persona),
                "date": str(s.get("date") or ""),
            })

    items.sort(key=lambda it: _stable_rank(it["sample_id"], sd))
    return {
        "prereg_id": PREREG["id"],
        "seed": sd,
        "n_per_persona": per,
        "n": len(items),
        "n_target": per * len(wanted),
        "personas": wanted,
        "items": items,
        "shortfall": shortfall,
        "skipped_unknown_persona": skipped_unknown,
        "complete": not shortfall,
    }


_SIGNATURE_MARKS = ("@", "#")


def blind(text: str, *, persona: str = "") -> str:
    """Strip the identity tells the prereg names, leaving only the voice.

    Handles, hashtags and the persona's own name go. Cashtags STAY: they are
    market content, and removing them would strip the finance substance the
    identities are supposed to differ in the handling of.
    """
    out = str(text or "")
    if persona:
        out = out.replace(persona, "").replace(persona.capitalize(), "")
    cleaned: list[str] = []
    for token in out.split():
        if token[:1] in _SIGNATURE_MARKS:
            continue
        cleaned.append(token)
    return " ".join(cleaned).strip()


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. The pre-registered interval for this eval.

    Wilson rather than normal-approximation because the normal interval is
    badly wrong exactly where this eval lives: small n, proportions near the
    0.2 baseline. It can even put the lower bound below zero, which would read
    as "worse than impossible".
    """
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


def grade(responses: dict[str, str], holdout: dict) -> dict:
    """Score a completed run. Returns accuracy, per-persona breakdown, CIs.

    ``responses`` = {sample_id: guessed_persona}. An unanswered sample is
    counted as UNANSWERED and excluded from the denominator, with the count
    printed: scoring a skipped item as wrong would punish a rater for
    abstaining, and a resolution-conditioned denominator is the house rule.
    """
    items = holdout.get("items") or []
    personas = list(holdout.get("personas") or PREREG["personas"])
    confusion: dict[str, dict[str, int]] = {t: {g: 0 for g in personas} for t in personas}
    per_persona: dict[str, dict] = {p: {"n": 0, "correct": 0} for p in personas}
    unanswered = 0
    correct = 0
    answered = 0

    for item in items:
        truth = str(item.get("truth") or "")
        guess = responses.get(str(item.get("sample_id") or ""))
        if guess is None or str(guess).strip() == "":
            unanswered += 1
            continue
        guess = str(guess)
        answered += 1
        if truth in per_persona:
            per_persona[truth]["n"] += 1
        if truth in confusion and guess in confusion[truth]:
            confusion[truth][guess] += 1
        if guess == truth:
            correct += 1
            if truth in per_persona:
                per_persona[truth]["correct"] += 1

    overall_lo, overall_hi = wilson_interval(correct, answered)
    for p, block in per_persona.items():
        lo, hi = wilson_interval(block["correct"], block["n"])
        block["accuracy"] = round(block["correct"] / block["n"], 4) if block["n"] else None
        block["ci95"] = [lo, hi]
        block["above_chance"] = bool(block["n"] and lo > CHANCE_BASELINE)

    return {
        "prereg_id": PREREG["id"],
        "n_items": len(items),
        "n_answered": answered,
        "n_unanswered": unanswered,
        "correct": correct,
        "accuracy": round(correct / answered, 4) if answered else None,
        "ci95": [overall_lo, overall_hi],
        "chance_baseline": CHANCE_BASELINE,
        "charter_target": PREREG["charter_target"],
        "per_persona": per_persona,
        "confusion": confusion,
    }


def verdict(result: dict) -> dict:
    """Apply the PRE-REGISTERED promotion rule. Still gates nothing.

    Both clauses bind: the overall lower bound must clear chance, and no
    identity may sit at or below chance. Meeting the charter's 0.80 target is
    reported separately and explicitly does not authorise anything — the target
    was a point estimate with no n behind it.
    """
    if not result or result.get("accuracy") is None:
        return {
            "status": "not_run",
            "gates": [],
            "note": "no responses graded — the eval has not been run",
        }
    lo = float((result.get("ci95") or [0.0, 1.0])[0])
    per = result.get("per_persona") or {}
    weak = sorted(p for p, b in per.items() if b.get("n") and not b.get("above_chance"))
    overall_ok = lo > CHANCE_BASELINE
    meets_target = float(result.get("accuracy") or 0.0) >= float(PREREG["charter_target"])

    if not overall_ok:
        status = "not_above_chance"
    elif weak:
        status = "above_chance_but_uneven"
    else:
        status = "above_chance"

    return {
        "status": status,
        "overall_lower_bound": lo,
        "chance_baseline": CHANCE_BASELINE,
        "identities_at_or_below_chance": weak,
        "meets_charter_target": meets_target,
        "gates": [],
        "note": (
            "Reported only. The >=80% figure gates nothing in this repo "
            "(blind_identity.GATES_NOTHING) and this run does not change that; "
            "promoting it to a gate is a separate, explicit decision."
        ),
    }


__all__ = [
    "PREREG", "GATES_NOTHING", "CHANCE_BASELINE", "N_PERSONAS",
    "build_holdout", "blind", "wilson_interval", "grade", "verdict",
]
