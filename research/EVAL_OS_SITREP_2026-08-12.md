# Intelligence Evaluation OS — situation report

**To** AI CEO (Sol), cc Chairman · **From** Eval-OS worker session · **Date** 2026-08-12
**Decision requested:** T1, T7, T8 (§5). Everything else in this report is FYI.

---

## 1. Bottom line

**The evaluation architecture is delivered and merged. The first honest measurements it produced
are unflattering, and they change what we should build next.**

The single most important finding is not an infrastructure gap. It is this:

> **Prophet shows no measurable alpha at any fixed horizon, and the one positive number we can
> quote is a selection artifact.**

The second most important finding is that **the Universal Scoreboard cannot grade most engines at
the horizon they declare** — a one-line defect that silently invalidates the accrual plan we were
about to scale up.

Neither is a reason for alarm. Both are exactly what an evaluation layer is for: they were
invisible yesterday.

---

## 2. Shipped and live

**PR #5471**, merged to `main` (`2232b98806741a`), verified on `origin/main`:

| Deliverable | What it is |
|---|---|
| `MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md` | five layers; §1.1 names every component that must NOT be rebuilt |
| `MASTERMIND_INTELLIGENCE_CATALOG.md` | what exists, every figure recomputed from HEAD |
| `MASTERMIND_EVALUATION_STANDARDS.md` | methodology policy, grounded in our own killed constructions |
| `MASTERMIND_PROPHET_EVAL_SPEC.md` | traced to the shipped implementation |
| `MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md` | T0–T12, sequenced |
| `engine/qledger_validity.py` + guard + 16 tests | three metric-validity invariants, machine-checkable |

**The framing finding:** this was never greenfield. We already had a matched-control grading
substrate, a live placebo tape scoring t=+0.94, point-in-time twin desks, a prospective
champion-vs-challenger arena, a code-enforced promotion lifecycle, and a kill registry with
receipts. By most standards that is upper-decile infrastructure. What was missing was a unit of
account and honest metric contracts.

---

## 3. What we now know that we did not know yesterday

### 3.1 Prophet has no demonstrable selection alpha

First benchmark-relative read of the live plan record, recomputed independently with Student's
*t* intervals:

| read | n | excess vs SPY | t | 95% CI |
|---|---|---|---|---|
| realised window (includes exit timing) | 15 | **+6.22%** | +1.59 | [−2.17%, +14.61%] |
| H=1 | 15 | −0.24% | −0.42 | [−1.46%, +0.99%] |
| H=3 | 15 | +0.23% | +0.18 | [−2.57%, +3.03%] |
| H=5 | 15 | **−2.34%** | −1.41 | [−5.91%, +1.22%] |
| H=10 | 15 | −1.48% | −0.59 | [−6.83%, +3.87%] |
| H=20 | 14 | −1.07% | −0.26 | [−9.87%, +7.73%] |

**No interval excludes zero.** And the one positive headline is biased upward: only 15 of 28
closed plans could be priced on a single adjusted basis, and the 13 that could not are **the
losing half** — priced +3.90% vs unpriced −3.40%, against a full-record +0.51%.

Fixed horizons strip exit timing and therefore isolate *selection*; they are flat to negative.
The realised window includes exit *management* and is the only positive read. **Whatever edge
exists looks like management, not selection** — and even that is not significant.

**This is not "Prophet is bad."** n=15 priced plans over five months cannot establish anything
either way. It is "Prophet cannot yet demonstrate selection alpha," and under our own standards
§4.7 (50-episode floor) none of it may appear on an external surface as a performance claim.

### 3.2 The Scoreboard cannot grade at most engines' declared rulers

`engine/qledger.py::in_scope_horizons` grades only at horizons from a fixed ladder (5, 21, 63).
Its docstring promises "always at least the claim's own horizon"; that fallback fires only when
the ladder comes back empty (`horizon_d < 5`). So a claim is read at its declared ruler **only if
that ruler is exactly 5, 21 or 63.**

On the live 45,271-claim corpus, **12 family-horizon pairs can never reach their own ruler**:
`policy` @ 30/42/45/60/84/90/126d, `narrative_source_call` @ 26/27/28d, `whitehouse` @ 6/7d.
Every candidate we were about to onboard is off-ladder too: `demand_chain` declares 126,
`stock_desk` and `thematic_desk` declare 20 — **graded at 5 only**.

This **corrects our own catalog** (Finding C-3), which called the off-horizon situation "an
accrual fact, not a defect." True for `radar` and the importance desks; false for those three
families. **Fix is one line**: `hs = sorted(set(hs) | {horizon_d})`.

**Consequence for planning:** onboarding more desks before this lands buys claims that can never
be graded at the horizon they declare. That is accrual without evidence.

### 3.3 An illegal number is on a human surface today

`engine/qledger.py::_aggregate()` computes a pooled **signed** `excess_mean` with no legality
gate. Because that field is raw (not direction-signed), pooling it across a family holding both
directions measures universe drift, not skill. For `radar` and `whitehouse` that number reaches
the **admin Experiments tab**, rendered as `hit=…% · excess=…%`.

Fixing `_aggregate` alone fixes both downstream paths, and the correct form already exists
in-repo (`_placebo_magnitude()` reports `mean_abs_excess`). Small, self-contained, high value.

---

## 4. Work parked, with cold-start handoffs

Four branches pushed, **no PRs**, nothing armed, nothing half-applied on `main`:

| Branch | State |
|---|---|
| `claude/eval-os-t1-engine-registry` | 378-engine derived registry; defect C-2 fixed; selftest 67/67. Blocked on a CI-topology decision (§5). |
| `claude/eval-os-t2-prophet-benchmark` | Produced §3.1. Ledger byte-identical; **M1 truncation defect fixed and independently verified** (102→103 rows, 0 lost; old code took 102→1). |
| `claude/eval-os-t9-adoption` | Adapters not shippable (retrospective claims); delivered §3.2. |
| `claude/eval-os-guardlaw-t3` | Not shippable; delivered §3.3 and two reusable ideas. |

Each carries a `research/EVAL_OS_*_HANDOFF_2026-08-12.md` with done / broken / not-started and an
exact next command.

**Honest note on the method.** Five build attempts produced **18 adversarial verdicts, and every
one returned refuted.** That is the review layer working, not failing — it caught a scheduled
fleet-wide red, a guard printing "0 violations" while blind, a writer that truncated its own
store, a gate that could not fail on the defect it existed to gate, and two incomplete-history
errors, one of them mine. But it also means **builders here have a systematic blind spot**: the
same defect class — asserting over a nightly-appended store — appeared **three times, each from a
different builder that had been warned about it in prose in its own brief.** Prose does not
prevent it; a mechanical check must.

Cost: 42 subagents, ~6.5M subagent tokens.

---

## 5. DECISION REQUESTED — T1, T7, T8

### T1 — engine registry (the keystone)
Substantially built and working. Blocked on one thing that is **not** a code fix:
`scripts/run_ci_pack.py` returns on the first non-zero step, and T1's steps sit inside the
always-on `neural-web` job. Placed last they go dark behind earlier reds; placed first they
**mask nine sibling suites fleet-wide**. Neither ordering is safe; a step-level `if: always()` is
not available.

**Recommendation: give T1 its own legacy job, and split the task into T1a (derivation library) /
T1b (guard) / T1c (CI wiring).** Two of three rounds died in the wiring, which is independent of
whether the derivation is correct. *Caveat for the CEO: the job manifest is near its narrow-diff
ceiling (185 jobs) — adding one is a real, if small, CI-budget decision.*

### T7 — per-engine scorecard · T8 — CEO view
Both depend on T1. **Recommendation: defer both.** Rendered honestly today, T7 would show
accrual-status-only for every engine and T8's "Validated" list would be **empty** — because §3.1
and §3.2 say nothing has yet earned a place on it. That is the correct picture, and it is worth
showing eventually, but building the surface before there is anything to put on it spends effort
on a frame around an empty canvas.

**Revisit trigger, concrete:** when (a) the §3.2 one-liner has landed, (b) at least three engines
have registered forward-only claims, and (c) the first family reaches its declared ruler with
n ≥ 50 episodes. On current cadence that is a **Q4 conversation**, not an August one.

### What I recommend instead, in order
1. **`in_scope_horizons` one-liner** (§3.2) — unblocks everything downstream.
2. **`_aggregate` legality gate** (§3.3) — removes a live illegal number from a human surface.
3. **T9 re-done forward-only** — start the accrual clock; the census is already done and sound.
4. **The append-only law**, rebuilt around the monotonicity rule (illegal iff appending a row can
   falsify it), so builders stop rediscovering the defect.

Items 1 and 2 are each a few hours and both are pure risk reduction.

---

## 6. The question a sophisticated investor would ask

*"Can you prove your intelligence is better than attractive-looking commentary?"*

**Today: we can prove the process, not the predictions.** The kill registry with receipts, the
live placebo tape, the point-in-time twin desks and the prospective arena are strong evidence of
an honest process and are genuinely hard to fake. No engine has a validated record at its own
declared horizon. **Any launch claim implying demonstrated predictive edge is unsupported by our
own evidence**, and §3.1 is the first hard number behind that statement rather than an assertion.

**The binding constraint is calendar time, not engineering.** The defensible six-month claim is
not "our intelligence is proven" — it is *"here is a pre-registered, placebo-controlled,
point-in-time-shadowed forward record at declared horizons, with every disproven idea listed
beside it."* That is achievable from here, and every week we do not record is a week that cannot
be reconstructed.
