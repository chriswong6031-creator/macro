# Blind-identity eval — PRE-REGISTRATION

**Registration id:** `XG-W6-BIE-1`
**Registered:** 2026-07-28 (XG-W6, charter §8 assumptions register)
**Status:** `not_run`
**Machine-readable copy:** `engine/marketing/blind_identity.py` → `PREREG`
(a test asserts this document and that dict agree on every number)

---

## 0. What this document is for

The X Growth charter carries a ≥80% blind-identity target. Charter §8 records
why that number cannot be allowed to gate anything yet:

> The ≥80% blind-identity target is a point estimate with no n or CI, judged on
> samples from the generator it polices — pre-register the eval (sample size,
> holdout construction, chance = 20% baseline) in XG-W6 before the number gates
> anything.

So this is the registration, written **before** any run, and
`blind_identity.GATES_NOTHING` is `True`. The figure gates no dial flip, no
promotion, and no publish path. A test greps the tree to keep that true.

## 1. The question

Given a post with every byline, handle, avatar and account-specific cashtag
removed, can a blinded rater assign it to the correct one of five editorial
identities better than chance?

## 2. Chance is 20%, not 50%

Five identities, forced choice, so the baseline is **0.20**. This is stated
twice on purpose. A 55% result *looks* like a coin-flip failure and is in fact
2.75× chance; anchoring on the wrong baseline is how a working system gets
thrown away.

## 3. Sample size (declared in advance)

| Parameter | Value |
|---|---|
| Identities | 5 — `flagship`, `meagan`, `sophia`, `kelly`, `cici` |
| Samples per identity | 30 |
| Total samples | 150 |
| Chance baseline | 0.20 |
| Charter target (reported, **not** a gate) | 0.80 |

Thirty per identity puts the per-persona Wilson interval at roughly ±0.17 at
mid-range — wide, and deliberately declared as wide, because a narrower claim
would need a sample the accounts have not produced yet.

## 4. Holdout construction

- **Stratified**: exactly 30 posts per identity. An identity short of 30 is
  **reported as a shortfall**, never back-filled from another identity —
  back-filling makes the confusion matrix rows unequal and silently changes what
  the accuracy number means.
- **Source**: emitted posts only, from `data/marketing/personas/<id>/phrases.jsonl`.
- **Excluded**: any post whose text was used to tune a codex.
- **Date span**: the trailing 60 days at run time, so no single week dominates.
- **Blinding**: strip handle, byline, signature emoji, account-specific cashtags
  and franchise titles. A franchise title is a label, not a voice — leaving it in
  measures our naming, not our writing. Cashtags **stay**: they are market
  content, and removing them would strip the finance substance the identities are
  supposed to differ in their handling of.
- **Assignment**: deterministic given `(sample_id, seed)`; seed `20260728`. The
  holdout is re-derivable from this document alone.

## 5. Interval

Wilson score interval, 95%. Wilson rather than the normal approximation because
the normal interval is badly wrong exactly where this eval lives — small n,
proportions near 0.20 — and can put the lower bound below zero, which would read
as "worse than impossible".

## 6. Promotion rule

The eval supports a claim **only if both** hold:

1. the Wilson 95% lower bound on **overall** accuracy exceeds 0.20; **and**
2. **no single identity's** per-persona lower bound sits at or below 0.20.

Clause 2 exists because a fleet average carried by two distinctive voices while
three are indistinguishable is exactly the failure a single headline number
hides.

## 7. Multiplicity

Five per-persona intervals plus one overall = six. Report all six. Apply
Bonferroni (α = 0.05/6) to the per-persona claims. Print every null. This is the
charter §8 experiment law's concurrent-arm correction.

## 8. Confound, declared in advance

The obvious rater is a model of the same family as the generator being policed.
A high score is therefore consistent with **both** "the personas are distinct"
**and** "two models share a prior". A human-rater arm is the disambiguator and is
**not** part of this registration; until it runs, a passing result supports the
weaker claim only.

Recording this before the run is the point. Discovered after a favourable
result, it reads as an excuse; recorded here, it is a boundary on what the
result can mean.

## 9. What a result may and may not do

| Outcome | What it licenses |
|---|---|
| `not_run` (today) | Nothing. |
| `not_above_chance` | Nothing is promoted. The nulls are printed. |
| `above_chance_but_uneven` | The named weak identities need work. No fleet-wide claim. |
| `above_chance` | The weak claim in §8 only. |
| `meets_charter_target` | Reported. Still gates nothing — promoting it to a gate is a separate, explicit decision with its own record. |

## 10. Running it

```python
from engine.marketing import blind_identity as bie

holdout = bie.build_holdout(samples)          # samples: [{id, persona, text, date}]
# ... collect {sample_id: guessed_persona} from the blinded rater ...
result  = bie.grade(responses, holdout)
verdict = bie.verdict(result)                 # verdict["gates"] is always []
```

When the eval is run, update `PREREG["status"]` and commit the result alongside
it. Do not edit any other field in `PREREG` — a pre-registration that changes
after the data arrives is not a pre-registration.
