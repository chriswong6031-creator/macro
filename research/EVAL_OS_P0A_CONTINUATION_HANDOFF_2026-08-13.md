# Eval OS P0a (horizon-clock contract) — continuation handoff

**Date** 2026-08-13 · **Branch** `claude/evalos-p0a-horizon-clock` (pushed, **no PR**) ·
**Status** PARKED at a pre-committed exit after 5 build→verify rounds. The **contract is sound
and verified**; the **market resolver it depends on has failed five times** and is a separate
task. Recommend a re-scope (§4).

---

## 0. What is DONE and independently verified — do not rebuild

Seven mutation controls were re-run **by the reviewer, from source, each reverted byte-identically
afterwards**. Every one kills the suite, so the tests are not vacuous:

| mutant | result |
|---|---|
| M1 provenance reverted to shape | 10 failed |
| M2 `clock_migration = bool(excluded)` | 3 failed |
| M3 exchange deny-list nulled | 8 failed |
| M4 trading-day stepping → calendar `timedelta` | 17 failed |
| M5 hardcoded-NYSE dispatch | 23 failed |
| M6 control-leg guard removed | 1 failed (the exact target test) |
| M7 zombie/registration clock gate removed | fails |

And the substrate repair itself is real. The defect P0a exists to fix, measured at the start:

```
engine/qledger.py:536   check_by = asof + BusinessDay(horizon_d)
engine/qledger.py       _fwd_ret = fill  + Timedelta(days=horizon_d)   ← calendar
horizon_d=5 → +2d divergence · 7 → +4d · 21 → +10d      (every claim, incl. the 5/21/63 rungs)
```

Also verified and holding: nightly runs clean on the live 46,629-claim corpus (with the pre-fix
control still raising); `check_by == the grader's resolved exit` on the real
`backfill_qledger_us` lanes (a 6-day divergence closed); promotion reachable across a basis split
**without pooling**; `git diff --stat data/qledger` **EMPTY** (legacy immutable);
regression failure set **identical** to baseline; `in_scope_horizons` and `GRADE_HORIZONS`
**untouched** (that is P0b).

Design worth keeping: `lib/nyse_calendar.py` as session source (**not** the price-store index —
the store records what was *collected*, not what the exchange *held*, has known holes, and differs
per ticker, which would hand subject/bench/control three different horizon lengths); one
`resolve_horizon_window`; `_entry_date` → `_entry_anchor` so the DISCLOSURE_DATE embargo applies
to `check_by` **and** the grader or to neither; legacy stamped via the existing
`fill_convention` precedent.

---

## 1. Why it is parked — the market resolver failed FIVE times

`trading_days` needs to know **which exchange calendar** to step. Determining a claim's market has
now failed in five distinct ways, each fix relocating the blocker rather than killing it:

| round | mechanism | how it failed |
|---|---|---|
| 2 | hardcoded NYSE | CN lanes ungradeable on ~26% of windows (5,726 live claims) |
| 3 | "single letter suffix ⇒ US share class" | `.L` (LSE), `.T` (Tokyo), `.F` (Frankfurt) silently US |
| 4 | no-suffix branch ⇒ US | `600519`→US, `000001`→US, `0700`→US, `^HSI`→US |
| 5a | symbolic leg contributes nothing | `^HSI` **still** silently US, and a passing test enshrines it |
| 5b | provenance overrides shape | **`600519.SS` under a US desk resolves US** — a hard Shanghai suffix overridden |

Verified by the orchestrator directly at each round. Round 5's 5b is the sharpest: it is the
mirror image of rounds 3–4. Shape-only was sole-source and failed three times; the fix made
**provenance** sole-source, and it failed immediately.

### The rule that would actually work

> **Provenance and ticker shape are two INDEPENDENT signals. Neither is authoritative alone.
> They must AGREE, or the claim fails closed and is counted.**

A US desk claiming `600519.SS` is not a market to be guessed — it is a **contradiction**, and the
only safe answer is refusal. That rule was never tried; every round so far picked one source and
let it win.

---

## 2. Still open besides the blocker

- **`_placebo_magnitude` control arm disappears.** Round 5 made it SELECT one basis per horizon by
  max `n_grades`, so once the placebo tape carries the stamps P0a adds, the duel's control arm
  silently vanishes for the losing basis. The placebo tape is the credibility anchor of the whole
  programme — it must degrade loudly, never silently.
- **`promotion_check_by_market` grants promotion on the LEGACY clock**: it iterates every key of
  `clock_prior_n_dates`, which is built from all `family_bases` including legacy.
- **The migration banner still flaps**, relocated into the per-market rows this branch wired into
  production.
- **The new refusal reason puts an unbounded ticker in the machine-readable HEAD**, re-creating
  the `by_reason` histogram explosion round 4 fixed.
- **`MARKET_UNDETERMINED_NO_LEG` is unreachable** — a claim with no subject is named US rather
  than refused.
- Acceptance bar 6's flap test is **tautological** (asserts False twice on an unchanged store,
  on a branch that cannot produce True).

---

## 3. Exact next command

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/evalos-p0a-clock"
git log --oneline -1                                    # expect the round-5 commit
python3 -m pytest tests/test_qledger_horizon_clock.py -q # expect green
python3 -c "import sys;sys.path.insert(0,'.');from engine.qledger import resolve_claim_market as r;\
print(r({'desk':'us_importance_v0','claim_family':'us_importance_v0','scope_key':'600519.SS','scope_type':'entity'}))"
# today prints ('US','') — the blocker. It must refuse.
```

---

## 4. RECOMMENDED RE-SCOPE (for CEO ruling)

P0a as specified bundles **two problems of very different difficulty**, and only one of them is
hard:

**P0a-1 — the clock contract, calendar-only.** Explicit `horizon_unit`, ONE resolver shared by
`check_by`/maturity/grading/rendered ruler, legacy immutable and stamped, no cross-basis pooling.
For `calendar_days` this needs **no market at all**. It closes the +2/+4/+10-day internal
ambiguity that affects *every claim in the corpus today*, and it is already built and verified.
**Shippable now.**

**P0a-2 — trading-day support**, which requires market resolution under the agree-or-refuse rule
(§1). Its own task, its own design, its own review.

**Honest consequence, stated plainly:** P0a-1 alone does **not** unblock P3. `stock_desk`,
`thematic_desk` and `demand_chain` all declare **trading** days, so prospective registration still
waits on P0a-2. The split buys a real substrate fix now and stops a five-times-failed classifier
from holding the contract hostage — it does not start the evidence clock.

That is the trade the CEO should rule on: **ship the calendar-only substrate now and treat market
resolution as its own task, or hold the whole contract until the resolver is right.**
