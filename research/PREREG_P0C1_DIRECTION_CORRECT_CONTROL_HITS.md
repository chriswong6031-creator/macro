# Pre-registration — P0c-1: direction-correct `control_only` hit counting

**Registered** 2026-08-13, **before** the repair is written.
**Authority** CEO ruling 2026-08-13 §4. **Scope** `engine/qledger.py::promotion_check`.
**Status** PRE-REGISTERED — outcomes below are declared in advance and will be
printed whether they flatter the engines or not.

---

## 1. The defect

`promotion_check(..., control_only=True)` scores a control hit as:

```python
ctrl_excess = subj - ctrl
if ctrl_excess > 0:
    hits += 1
```

**It never reads the claim's `direction`.** For a `direction=-1` claim a correct
bearish call has `subject_ret < control_ret`, so `subj - ctrl < 0` — and the
correct call is counted a **MISS**. Every wrong bearish call is counted a **HIT**.
The §3 Wilson lower bound, which is the promotion gate, is therefore computed on
an **inverted hit series** for any family holding short claims.

Two further faults in the same branch:

- `bench_ret` is read and gated on (`if ctrl is not None and subj is not None and
  bench is not None`) but **never used**. A row with a control leg but a null
  bench silently falls through to the primary-hit fallback.
- When the control leg is unavailable the row falls back to the **primary** hit
  (`elif hit: hits += 1`) while still counting in the denominator — so a
  control-only reading silently mixes in bench-relative outcomes.

Discovered by adversarial review of #5558. **Pre-existing on `main`** — not
introduced by the P0a work — but it is the gate P0a exists to protect.

## 2. The declared semantic (CEO §4, verbatim intent)

Let `raw_control_excess = subject_ret - control_ret`.

| condition | outcome |
|---|---|
| `direction == +1` | hit iff `raw_control_excess > 0` |
| `direction == -1` | hit iff `raw_control_excess < 0` |
| both above | equivalently **`direction * raw_control_excess > 0`** |
| `direction == 0` | **no directional hit** — salience-only claims have no direction to be right about |
| `subject_ret` or `control_ret` missing | **excluded** from numerator *and* denominator — never converted into a miss |
| `raw_control_excess == 0` exactly | **not a hit** (strict inequality); no existing higher-precedence qledger law says otherwise — checked §5 |

## 3. What changes, and what must NOT

**Changes:** the control-only numerator, and the control-only denominator (a row
with a missing control leg leaves both instead of falling back to the primary hit).

**Must not change:**

- **No historical grade row is rewritten.** `grades.jsonl` is append-only and
  immutable; this is a *derived* readiness calculation and is repaired at read
  time only. `git status data/` must be empty.
- `control_only=False` behaviour is untouched.
- `GRADE_HORIZONS`, `in_scope_horizons` untouched (that is P0b).
- No change to which claims are eligible, only to how their control hits count.

## 4. Pre-declared expected effects — printed whichever way they fall

Registered **before** measurement:

1. **Direction mix.** The live corpus is ~71% `direction == 0` (salience). Those
   rows contribute **no** directional hit under the new rule. For a
   salience-dominated family the control-only hit rate becomes `None`/undefined
   rather than a number — that is the correct answer, and it will **reduce** the
   apparent evidence for several families. This is expected and is not a
   regression.
2. **Bearish families.** Any family holding `direction == -1` claims should see
   its control-only hit rate **move**, and for a family that is mostly short it
   should move a lot. If it does **not** move, the fix did not take effect and
   the repair has failed — that is a falsifier for this change.
3. **Promotion states.** Some family may cross **either way**. A family that was
   `ready=True` on inverted arithmetic may become not-ready. **That is a
   correction, not a loss**, and it will be reported as such rather than quietly
   absorbed.
4. **n may fall.** Excluding missing-control rows instead of falling back to the
   primary hit reduces the control-only denominator. Any family whose `n_dates`
   drops below the 25-date bar as a result will be reported by name.

**Falsifier for the whole change:** if, on the live corpus, no family's
control-only hit rate moves at all, then either no live family holds a non-zero
direction with a control leg — which must then be **stated as the finding** —
or the repair is not wired into the path that computes the gate.

## 5. Precedence check — does a higher qledger law already define the zero case?

Checked before writing the rule, so the "unless an existing higher-precedence law
says otherwise" clause is resolved rather than assumed:

- `grade_claim()` stores `hit=None` for `direction == 0`, so salience claims
  already contribute nothing to any hit rate. Consistent with rule §2.
- `engine/qledger_validity.py` V2 forbids reporting a hit rate for a
  salience-family; the `direction == 0` → no-hit rule is the same law, applied
  one layer down.
- No qledger rule treats an exact-zero excess as a hit. The primary (non-control)
  hit path also uses strict `>`.

**Conclusion: no higher-precedence law overrides. Exact zero is not a hit.**

## 6. Mechanical acceptance (required by CEO §4)

1. **Mirrored fixtures.** The same magnitudes, bullish and bearish: a
   `direction=+1` family whose subject beats its control, and a `direction=-1`
   family whose subject *trails* its control by the same amount, must produce the
   **same** control-only hit rate.
2. **The inversion is caught.** A `direction=-1` family of correct calls must
   score a hit rate of **1.0**, not 0.0.
3. **Salience contributes nothing.** A `direction=0` family yields no directional
   hits and does not inflate the denominator.
4. **Missing legs are excluded, not missed.** A row with a null `control_ret`
   changes neither numerator nor denominator.
5. **Exact zero is not a hit.**
6. **MUTATION (the required negative control):** a mutant that deliberately
   ignores direction — restoring `if ctrl_excess > 0` — **must fail** the suite.
   If it passes, the tests do not gate the defect and the change is not accepted.
7. `git status data/` empty; the full qledger regression set green.

## 7. Out of scope

- Legacy-vs-explicit-clock authority: **P0c-2**, shipped separately.
- Own-ruler grading: **P0b**.
- Rewriting historical grades: **forbidden**, see §3.
