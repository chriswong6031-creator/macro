# Eval OS T9 (qledger adoption) — continuation handoff

**Date** 2026-08-12 · **Branch** `claude/eval-os-t9-adoption` (pushed, **no PR**) ·
**Status** ADAPTERS NOT SHIPPABLE. But T9 surfaced a **prerequisite defect** that must be fixed
before adoption is worth doing at all, and that finding is the real deliverable of this task.

---

## 0. THE PREREQUISITE — the Scoreboard cannot grade at most engines' declared rulers

`engine/qledger.py::in_scope_horizons` grades a claim only at horizons drawn from a **fixed
ladder**:

```python
GRADE_HORIZONS = (5, 21, 63)

def in_scope_horizons(horizon_d: int) -> list[int]:
    """...and always at least the claim's own horizon (so a horizon_d < 5
    claim still grades once, at its own clock)."""
    hs = [h for h in GRADE_HORIZONS if h <= horizon_d]
    if not hs:
        hs = [horizon_d]
    return hs
```

**The docstring states an intent the code does not implement.** The "always at least the claim's
own horizon" fallback fires *only when the ladder comes back empty*, i.e. only for
`horizon_d < 5`. For every other value, a claim is read at its own ruler **only if that ruler
happens to be exactly 5, 21 or 63.**

Measured on the LIVE corpus (45,271 claims) — 12 family-horizon pairs can **never** be read at
their own declared ruler, no matter how long we wait:

```
policy                @ 30, 42, 45, 60, 84, 90, 126 d
narrative_source_call @ 26, 27, 28 d
whitehouse            @ 6, 7 d
```

And every wave-1 candidate is off-ladder too:

| desk | declares | actually graded at | at its own ruler? |
|---|---|---|---|
| `demand_chain` | 126 | [5, 21, 63] | **NO** |
| `stock_desk` (modal, 409/702 rows) | 20 | **[5]** | **NO** |
| `thematic_desk` | 20 | **[5]** | **NO** |
| `radar` | 63 | [5, 21, 63] | yes |
| importance desks | 5 / 21 | [5, 21] | yes |

A 20-day thesis judged at 5 days is exactly the off-horizon verdict
`DNR:KILL-OFFHORIZON-VERDICTS` forbids — and here it is **structural**, not a maturity wait.

### 0.1 This corrects the catalog

`research/MASTERMIND_INTELLIGENCE_CATALOG.md` Finding C-3 says no family had produced a verdict
at its declared horizon and calls it *"an accrual fact, not a defect."* That is right for `radar`
(63) and the importance desks (5/21). It is **wrong** for `policy`, `whitehouse` and
`narrative_source_call`: those are permanently unreachable. Amend C-3 when this lands.

### 0.2 The fix is one line

```python
hs = sorted(set(hs) | {horizon_d})
```

This makes the code do what its own docstring already promises. Cost: roughly one extra grade
row per claim (~45k rows, ~13 MB on a 16 MB store) — additive and append-only, no existing row
changes. Callers to re-check: `engine/flip_confirmation.py`, `scripts/grade_qledger.py`,
`scripts/backfill_qledger_us.py`, `tests/test_flip_confirmation.py`.

**Ship this as its own small PR before any further adoption work.** Until it lands, registering a
new desk buys a claim that can never be graded at the horizon it declares — which is accrual
without evidence, the appearance of rigour rather than the thing.

---

## 1. What the census got right (keep this)

The candidate selection is sound and reusable. Every candidate carries a **real** `lean` enum, so
no direction is inferred (rule R4 / constitution A7 holds at the adapter boundary):

| engine | store | rows / dates | direction field |
|---|---|---|---|
| `engine/stock_desk.py` | `data/stock_desk/theses.jsonl` | 702 / 32 | `lean ∈ {constructive, neutral, cautious, avoid}` |
| `engine/thematic_desk.py` | `data/thematic_desk/theses.jsonl` | 253 / 35 | `lean ∈ {overweight, underweight, avoid}` |
| `engine/ai_desk.py` | `data/ai_desk/theses.jsonl` | 132 / 23 | `lean` + a `fade-fear` carve-out |
| `engine/demand_ledger.py` | `data/demand_chain/theses.jsonl` | 55 / 14 | rule-derived, **no LLM in the construction** |

`demand_chain` has the cleanest provenance story of the four. `ai_desk` is the most conspicuous
gap: `qledger.py`'s own docstring names it as one of the three ledger patterns it generalises,
and it was never itself registered.

Good adjudication calls worth preserving: `neutral`/`soft` leans are **skipped**, never filed as
`direction=0` (that would inflate the salience share, which is already 71% of the corpus); the
`thematic_desk` scope key is the engine-resolved `subject_ticker`, not the unpriceable theme
label; and the canada/hk/china legs were excluded (no price parquet; and the CN leg needs its own
ruling against `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`).

Dry run: **332 claims, 0 rejected by `_validate_claim`, 0 with `direction==0`, idempotent on a
second run.** The committed `data/qledger/claims.jsonl` was NOT mutated.

---

## 2. Why the adapters are not shippable

3/3 adversarial lenses refuted. Blockers:

- **B1 — R3 violated: the claims are retrospective.** `stock_desk` and `thematic_desk` claims are
  anchored and priced at a close already 1–4 completed sessions in the past when the desk wrote
  the lean. A prediction ledger whose rows are stamped after the fact is not live-forward
  evidence, which is the only thing that makes it worth having.
- **B2 — `thematic_desk_us` would read GRADED from day one** off claims that are 100%
  retrospective.
- **B3 — the `backfilled` provenance flag is decorative.** Nothing in `qledger` reads it, so a
  family made entirely of after-the-fact imports clears the promotion gate exactly like a
  live-forward one. Either give the flag a consumer or do not write backfilled rows.
- **B4 — a second push lane binds `data/qledger/claims.jsonl`** whose conflict resolution can
  **silently discard concurrent upstream claim appends**. Data loss on the forward record.
- **B5 — the new tests never run**: `tests/test_qledger_ui.py` needs `jinja2`, which the
  `outcome-spine` job does not install, and `run_ci_pack` returns on the first non-zero step, so
  the adapter's own test (step 9) is never reached.

Majors: a total registration failure is silent and, for `stock_desk`, permanent; a partially
available ledger degrades to a confidently truncated claim set rather than "could not look"; the
registered falsifier cannot fire inside the Scoreboard because `qledger`'s `hit` is a different
statistic from the desks' own outcome; 23% of thematic claims carry a bench level but no subject
level.

---

## 3. Recommended sequence when this resumes

1. **Ship the `in_scope_horizons` one-liner** (§0.2) as its own PR, with tests. Nothing else here
   matters until a claim can be read at the ruler it declares.
2. Decide the **backfill question** explicitly: either give `backfilled` a real consumer that
   excludes such rows from any forward-record statistic, or register **forward-only** and accept
   a smaller day-one N. My recommendation is forward-only — the ledger's whole value is that its
   rows were written before the outcome existed, and a mixed store with a decorative flag is
   worse than a small honest one.
3. Re-do wave 1 **forward-only**, starting with `demand_chain` (cleanest provenance, no LLM) and
   `ai_desk` (closes the most conspicuous gap).
4. Fix the `outcome-spine` job's dependency list and step ordering before wiring any test there.

---

## 4. Exact next command

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/eval-os-t9-adoption"
python3 -c "import sys;sys.path.insert(0,'.');from engine.qledger import in_scope_horizons as f;print(f(20),f(126))"
# today prints [5] [5, 21, 63] — after the §0.2 fix: [5, 20] [5, 21, 63, 126]
python3 -m pytest tests/test_qledger_desk_adapter.py -q
```
