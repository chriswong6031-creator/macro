# Roster-cap reconciliation — `max_active_nonscored_lobes: 66` vs. actual 75

**Date:** 2026-08-04 · **Trigger:** Prophet superintelligence census governance sweep
**Status:** Findings final. Code fix (governor wiring) ships with this PR. Cap change
**NOT applied** — `config/metabolism_budget.yml` is operator-ratified (R-V2-8); a
decision on §6 requires a T2 operator tap.

---

## 0. Verdict

- The roster count under the code's own unit (charter entries with
  `lifecycle_state: active` and `tier ∈ {display, shadow, confirmer}` in
  `config/lobe_charters.yml`) is **75**, against an operator-ratified cap of **66**
  (`config/metabolism_budget.yml:93`, directive 2026-07-17).
- The cap was crossed on **2026-07-17** and exceeded five more times through
  **2026-08-01**, entirely via **operator-commissioned session PRs**. The metabolism
  loop has chartered **zero** lobes; the governor never tripped because its
  enforcement point was never wired (production-dark) and session PRs bypass the
  loop's gauntlet entirely.
- The "66 of 66 — FULL" bookkeeping was already stale the day it was written: it was
  computed from the budget file's own comment chain, not from replaying the registry
  (see §3.5).
- Consequence today: the loop's genesis lane (R-V6-3a) is hard-frozen — 75 ≥ 66
  denies every genesis proposal, and even 9 co-pending swaps would not clear it
  (needs 10). No ASK card ever surfaced this to the operator.
- **This PR ships:** the governor's missing enforcement wiring (ASK-emitting,
  never-block — §5). **Awaiting operator T2 tap:** the cap decision (§6; drafted
  diff in §6.1).

## 1. The discrepancy

`config/metabolism_budget.yml:93` (IMMUTABLE, operator directive 2026-07-17):

```yaml
max_active_nonscored_lobes: 66    # 66 of 66 — FULL (PR-W2 adds prophet; SA-W3 was 65; base 63+3)
```

Replaying `engine/metabolism/roster_governor.py`'s exact filter (identical in
`adjudicate._genesis_screen` and `scout._roster_snapshot`) against current
`config/lobe_charters.yml`: **109 charter entries → display 64 + shadow 11 +
confirmer 0 = 75 active non-scored** (34 infrastructure-tier entries excluded).

## 2. Archaeology — every merge that moved the count

`config/lobe_charters.yml` has been touched by exactly 9 commits since inception.
Count replayed at each (governor filter, verbatim):

| Date | PR | Count | Δ entries added (active non-scored) |
|---|---|---|---|
| 2026-07-10 | #2157 V2-C registry created | **63** | baseline (cap set = 63 + 3 headroom) |
| 2026-07-11 | #2262 V4-W5 | 64 | `til` |
| 2026-07-12 | #2451 SA-W3 | 65 | `site-china-standouts` |
| 2026-07-17 | #2781 RIC W3 OPEXRISK | **66 — cap reached** | `opex-windows-forward-log` |
| 2026-07-17 | #2780 RIC W4 EVW | **68 — cap CROSSED** | `event-windows-forward-log`, `event-windows-snapshot` |
| 2026-07-18 | #2856 Prophet W2 | 69 | `prophet` |
| 2026-07-18 | #2926 Marketing lobe | 71 | `marketing-lobe`, `marketing-state` |
| 2026-07-26 | #3588 Chronicle W0 | 74 | `chronicle-events`, `chronicle-manifest`, `chronicle-state-log` |
| 2026-08-01 | #4202 Earnings consumers | **75** | `chronicle-earnings-call-events` |

All 12 additions were session PRs on operator-commissioned programs (RIC, Prophet,
Marketing, Chronicle/agentic_media). None came through the metabolism genesis
gauntlet: the registry holds **0** probation entries and the governance log holds no
charter grants.

## 3. Why the governor never tripped — five stacked causes

1. **`roster_governor.check_charter_budget` is production-dark.** Its only callers
   are tests (`tests/test_metabolism_v2c.py`). The documented enforcement point —
   `scout.py`: *"the cap surfaces as a digest ASK at onboarding (roster_governor)"* —
   was never wired into `applier.consume_charter_proposals`, the onboarding site.
   Classic unrun-suite-rot: the tests exercise the module in isolation and pass
   forever while nothing in production imports it.
2. **Latent unreachability defect.** Even if called, the active-cap ASK could never
   fire for the genesis flow: the branch required
   `proposed_lifecycle_state == "active"`, but genesis proposals arrive as
   `proposed`/`probation`. Meanwhile the live deny gate
   (`adjudicate._genesis_screen`, R-V6-3a) denies on the roster count regardless of
   the proposal's state — so the deny had no matching ASK.
3. **The live gate guards only the loop.** `_genesis_screen` runs inside ADJUDICATE
   and screens `kind=="charter"` proposals. The loop has never proposed one, so the
   gate has never evaluated a real over-cap case.
4. **Session PRs bypass everything.** `lobe_charters.yml` is operator-curated (its
   header says so); PRs edit it directly. No CI check compares the registry count to
   the cap, so nothing red-flags a crossing merge.
5. **The bookkeeping was comment-chain arithmetic, not measurement.** Prophet W2's
   claim "65 → 66 of 66 — FULL" (`config/metabolism_budget.yml:93`,
   `research/PROPHET_MASTERPLAN_BY_FABLE.md:62`) took SA-W3's "65" comment and added
   1. At merge time the registry was already 68 (the two RIC PRs had landed the day
   before/same day); prophet actually took it 68 → 69. Likewise
   `research/RATES_INFLATION_COMMAND_MASTERPLAN_BY_FABLE.md:175` asserted the
   roster governor "has capacity" while RIC's own PRs consumed the last slot and
   crossed the cap. Nobody replayed the registry; each document trusted the previous
   document.

## 4. Granularity — what is a "lobe" here?

Three defensible units, three very different counts:

| Unit | Count | Definition |
|---|---|---|
| **Charter entries** (the code's unit) | **75** | active display/shadow/confirmer rows in `lobe_charters.yml`; 73/75 are synapse **artifact** ids (only `til`, `prophet` are program-level) |
| **Conceptual lobes** (program organs) | **24** | grouping the 75 by `owner_program` — e.g. 7 `causal-*` artifacts = one Causal-Hypothesis-Factory lobe; 4 `chronicle-*` = one Chronicle spine |
| **Loop-manageable lobes** | **6** | entries with dict-form (graded) `fitness_sensors`: `til`, `prophet`, `site-us-standouts`, `site-china-standouts`, `opex-windows-forward-log`, `event-windows-forward-log` |

The registry is **artifact-keyed**, so multi-artifact programs inflate the entry
count without adding conceptual lobes: Chronicle alone is 4 entries, one organ.

**A false belief is written into the registry.** The 6 post-cap Marketing and
Chronicle entries carry notes asserting *"string-form fitness_sensors = no
metabolism roster slot consumed."* No counting code implements that distinction —
every counter (governor, genesis screen, scout snapshot) counts string-form entries.
The 2026-07-10 baseline of 63 was itself almost entirely string-form entries, so the
belief also contradicts the cap's own ratification basis. Those six notes are wrong
as statements about the counting rule (registry text left untouched per the
no-registry-changes mandate; correct or annotate them in the §6 ratification PR).

## 5. What ships in this PR (no ratification required)

Per R-V2-7 the governor's contract is **ASK, never block** — wiring it changes no
admission decision; the hard deny stays in R-V6-3a. Changes:

1. **Wired the enforcement point** — `applier.consume_charter_proposals` (charter
   onboarding) now calls `check_charter_budget` for each charter item on armed
   runs, refreshes the item's `roster_budget` snapshot (already carried onto the
   injected proposal by `_item_to_proposal`), and logs a warning on breach.
   Shadow/dry-run cycles skip it so non-armed runs never write operator surfaces.
2. **Fixed the unreachable active-cap branch** — the ACTIVE cap now fires for any
   charter proposal once the active roster is at/over cap, matching the R-V6-3a
   deny predicate exactly (probation cap unchanged).
3. **Stable ASK card filename** — `tap_roster_cap_<cap_type>.json`, overwritten per
   re-check, so a standing breach yields one standing card instead of one card per
   nightly cycle.
4. **Tests** — genesis-state ASK reachability, filename stability, onboarding
   wiring + never-block, and shadow-mode isolation
   (`tests/test_metabolism_v2c.py::TestRosterGovernor`).

Behavior after merge: nothing fires until the scout next emits a charter proposal
(`data/metabolism/charter_proposals/` is empty today). The first armed onboarding of
one will emit the standing ASK card — that is the governor finally doing its job,
not a regression.

## 6. Recommendation (operator decision — T2 tap)

**Recommended: re-base the cap under the existing unit — raise to 78 (= current 75
+ 3 loop headroom), the exact formula used at ratification (63 + 3).**

- Keeps the unit every counter already implements (charter entries) — no code
  change, no registry re-keying.
- Restores the ratified intent: the cap governs **loop** growth, and the loop gets
  back its 3-slot headroom (currently at −9, genesis frozen).
- With the §5 wiring live, the next time session-PR growth consumes the headroom
  the operator gets a standing ASK instead of silence — the cap stops rotting.

Ranked alternatives:

- **(b) Split into per-unit caps** (e.g. per-`owner_program` conceptual-lobe cap +
  loop-manageable cap): the honest granularity — 24 conceptual lobes is the number
  that means something for attention/budget — but requires a lobe-group field or
  registry re-keying and a redesign of every counter. Right long-term shape; too
  large to smuggle in under a reconciliation.
- **(c) Re-arm at 66 as-is**: requires demoting 9 operator-commissioned display
  organs (or 10 swaps to unfreeze genesis). Punishes shipped, operator-ordered work
  to honor stale bookkeeping. Not defensible.
- **(d) Exclude string-form entries from the count** (make the registry notes'
  belief true): shrinks the roster to 6/66, making the cap vacuous, and contradicts
  the 63-entry basis the operator ratified. Not defensible.

### 6.1 Drafted operator diff (NOT applied — requires T2 tap)

```yaml
# config/metabolism_budget.yml:93 — replace:
max_active_nonscored_lobes: 66    # 66 of 66 — FULL (PR-W2 adds prophet; SA-W3 was 65; base 63+3; operator directive 2026-07-17)
# with:
max_active_nonscored_lobes: 78    # 75 measured + 3 loop headroom (2026-08-04 reconciliation replay; formula unchanged from 2026-07-10 ratification: current+3). Prior "66 of 66 FULL" bookkeeping was comment-chain arithmetic — see research/ROSTER_CAP_RECONCILIATION_2026-08-04.md
```

Optional follow-ups for the same ratification PR (not blockers): a CI **warning**
(`::warning`, non-failing, per the ASK-never-block doctrine) when a PR pushes the
registry count past the cap, closing the session-PR blind spot; corrections to the
six "no roster slot consumed" registry notes; and errata notes in the Prophet and
RIC masterplans (§3.5 citations).

## 7. Evidence

- Replay: `python3 - <<'EOF' … yaml.safe_load("config/lobe_charters.yml") …` count
  of `lifecycle_state=="active" and tier in ("display","shadow","confirmer")` — 75
  at HEAD; per-commit via `git show <sha>:config/lobe_charters.yml` over the 9
  touching commits (`git log --follow -- config/lobe_charters.yml`).
- Governor callers: `grep -rn check_charter_budget --include='*.py'` → tests only.
- Onboarding site: `scripts/metabolism_propose.py:372` →
  `applier.consume_charter_proposals` (docstring contract in
  `engine/metabolism/scout.py:29-31,335-337`).
- Live deny gate: `engine/metabolism/adjudicate.py:432-527` (`_genesis_screen`,
  called at `adjudicate.py:1143`).
- Loop-manageable set: 6 entries with dict-form `fitness_sensors`; false-belief
  notes on `marketing-lobe`, `marketing-state`, `chronicle-events`,
  `chronicle-manifest`, `chronicle-state-log`, `chronicle-earnings-call-events`.
