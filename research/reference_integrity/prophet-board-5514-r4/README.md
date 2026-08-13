# Prophet Board — R4 closure cycle

Answers the **R3 verdict `REVISE`** (PR #5552), issued over artifact
`6ad6b51bc351bb7e32a77960abe11f6ddb63475c`.

This cycle **self-approves nothing.** It closes the recorded findings, produces a new
frozen SHA, and stops. Approval is possible only from a fresh independent RIG cycle
with new critic receipts — existing receipts went stale the moment the frozen SHA
moved (RIG §3).

## What is in here

| File | What it is |
|---|---|
| `R4_CLOSURE_LEDGER.md` | **Generated.** Every R3 finding, its severity trail, and this cycle's disposition + proof handle. |
| `tools/build_ledger.py` | The generator. Hard-fails unless the record↔disposition join is total in both directions. |
| `r3_source/` | The R3 record, vendored and sha256-pinned. The ledger answers a *frozen* document. |
| `AUTHORITY_INDEPENDENT_VERIFICATION.md` | The R3 claims recomputed from the fixture before building on them, plus the corrections that turned up. |

Regenerate / verify coverage:

```bash
python3 research/reference_integrity/prophet-board-5514-r4/tools/build_ledger.py --check
```

## Why the ledger is generated rather than written

The R3 verdict's own *strongest argument against approval* was not a bad decision — it
was a **coverage** failure:

> "The cycle fixed everything its rationale discussed and moved nothing that appeared on
> no list… a REVIEW ITERATION converging on the parts of the critique that were written
> down as code-shaped conditions while the capability-shaped ones — a link, a stale
> banner, a proof number, a route to 43% of the book — stayed invisible for a third
> consecutive revision."

Coverage failures are invisible to diligence: nobody notices the row that was never
written down. So the ledger makes omission a **build error** rather than a memory
question. A finding cannot be dropped by forgetting it — dropping it breaks the build.
Retiring one costs an explicit written disposition, on the record, with a reason.

Coverage at this SHA: **41 record rows / 41 dispositions / 12 condition-cited ids.**

## Scope discipline

A closure pass, not a redesign. The R3 architecture is preserved deliberately —
chart-first card, live quote/change slot, Priority, plan-book Setups, lifecycle ladder,
one universe / count law, sourced Groups, caution carrier, stance-branched zone,
light-mode card plane, bilingual behaviour, Candidates separation, compact no-prose
philosophy. The R3 verdict affirmed nine preserved strengths; none of them is touched.

## The payload is FROZEN, on purpose

`board-data.js` is **not** rebaked in this cycle. `tools/gen_fixture.py` reads
`git show origin/main:<path>` — a moving ref that takes ~24 nightly `[skip ci]` commits
every two hours — so a rebake would pull a different night's data and silently replace
the population the R3 verdict was issued over. That would take the count law
(62+95+0+0+2 = 159), the 102/179 reachability union, the 20-of-40 chartless ratio and
the 13/15/11/1 stance mix with it, and could make VTC-301 read as "fixed" purely because
a different night had more sparks.

A closure pass may not replace the population it is being judged on. The fixture stays
frozen; freshness and track-record values are added as an explicit additive block; and
`gen_fixture.py` is repaired (repo-relative path, pinned SHA) so the hazard is a fixed
artifact rather than a live trap for the next cycle.

Corollary: **PRC-320 is satisfied without a rebake.** The DESIGN_NOTES numbers were stale
relative to the *already-frozen* payload — §5 said 69 = 28+27+10+2+2 where the page has
been printing 70 = 22+35+12+1, and §0b.1 said 162 live where it is 159. The prose was
wrong, not the data, and the prose is what moved.

## Not waived by this cycle

Two production-migration blockers are **preserved, not weakened**, exactly as the R3
verdict recorded them. Neither is a reason to weaken the reference, and closing a visual
reference does not close either:

- **G-D** (PR #5541) — the plan book's actionability axis reaches 61/179 and enrichment
  45/179. Diagnosed as a *publication* gap, not an availability gap.
- **`overtime_producer_contradiction`** (PR #5540) — a vocabulary defect: `age_days` is
  anchored to `signal_date` while `days_elapsed`/`tau` and horizon expiry are anchored to
  `plan_clock_date()`, so "past its horizon" computed by a reader disagrees with
  `phase=overtime` by construction. Held open, not cured by hiding.

## For the next RIG cycle

The resubmission is the SHA this branch produces. Start from `R4_CLOSURE_LEDGER.md` —
each disposition names the **proof handle** (a `verify.py` check id and/or crop) that
must fail if that closure item is undone, and `tools/mutation_test.py` is the adversarial
instrument that asserts those guards actually bite rather than merely exist.
