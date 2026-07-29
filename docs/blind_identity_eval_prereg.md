# Blind-identity eval — PRE-REGISTRATION

**Registration id:** `XG-W6-BIE-1`
**Registered:** 2026-07-28 (XG-W6, charter §8 assumptions register)
**Amended:** 2026-07-28 — see §11
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
| Minimum **answered** per identity | 20 |
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
- **Blinding** — ONE rule (amended 2026-07-28; the original text contradicted
  itself on cashtags and the harness implemented neither half):

  | | |
  |---|---|
  | **STRIP** | bylines · handles · avatars · **account-specific** cashtags · franchise titles · signature emoji |
  | **KEEP** | **generic market cashtags** |

  An account-specific cashtag is an identity tell, not a voice: "the desk that
  always posts `$FXI`" is a byline in cashtag form. The registered per-identity
  list lives in `PREREG["holdout"]["account_specific_cashtags"]`. A franchise
  title is a label, so leaving it in measures our naming rather than our
  writing. Generic market cashtags stay, because they are the finance substance
  the identities are supposed to differ in their **handling** of — stripping
  them would measure topic assignment.
- **Assignment**: deterministic given `(sample_id, seed)`; seed `20260728`. The
  holdout is re-derivable from this document alone.

## 5. Interval

Wilson score interval, 95%. Wilson rather than the normal approximation because
the normal interval is badly wrong exactly where this eval lives — small n,
proportions near 0.20 — and can put the lower bound below zero, which would read
as "worse than impossible".

## 6. Promotion rule

The eval supports a claim **only if all three** hold:

1. the Wilson 95% lower bound on **overall** accuracy exceeds 0.20; **and**
2. **every identity** has at least **20 answered** samples; **and**
3. **no single identity's Bonferroni-corrected** lower bound sits at or below 0.20.

Clause 3 exists because a fleet average carried by two distinctive voices while
three are indistinguishable is exactly the failure a single headline number
hides. Clause 2 exists because an identity the rater skipped entirely would
otherwise drop out of clause 3 and license the claim by absence — absence of
evidence counted as evidence of absence. Below the floor the verdict is
`unmeasured`, never `above_chance`.

## 7. Multiplicity

Five per-persona intervals plus one overall = six. Report all six.

- **Per-persona** intervals are the family and carry Bonferroni: α = 0.05/6,
  two-sided → **z = 2.638**. These are the intervals that feed clause 3.
- The **overall** interval is the single pre-registered primary comparison, so
  it stays at the uncorrected z = 1.96.

Print every null. This is the charter §8 experiment law's concurrent-arm
correction.

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
| `unmeasured` | At least one identity fell below the 20-answer floor. No claim of any kind — the eval did not measure what it registered. |
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

---

## 11. Amendments

### 2026-07-28 — blinding rule made self-consistent; answer floor added

**What changed.**

1. The blinding rule contradicted itself: §4 said "strip account-specific
   cashtags" and also "cashtags stay". That is not a rule, and the harness
   implemented neither half — it stripped no emoji and no franchise titles, so a
   sample could carry `Before New York Wakes 🍵` straight through and the eval
   would have been grading our naming. Replaced with the single strip/keep table
   in §4 and implemented in full in `blind_identity.blind()`.
2. Added `min_answered_per_persona: 20` (§3, §6 clause 2). Without it an
   identity the rater skipped entirely dropped out of the weakness check and
   licensed the fleet claim by absence.
3. Pinned the registered Bonferroni z (2.638) into the per-persona intervals
   (§7). The harness had been running the more lenient uncorrected z = 1.96
   against its own registration.

**Why this is a legitimate amendment and not a rewrite after the fact.**

**The eval has never run.** There is no data this amendment could have been
fitted to — that is the only condition under which amending a pre-registration
is honest. `PREREG["status"]` is still `not_run`. Once it runs, no field in this
document may change.
