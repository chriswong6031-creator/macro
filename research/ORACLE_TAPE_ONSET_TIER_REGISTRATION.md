# Oracle registration — TAPE-ONSET (unconfirmed) display tier

**Status:** REGISTERED — merged before any result is computed (Constitution §I.3)
**Date:** 2026-07-09
**Author:** Fable (Tier 0 generation + pre-registration per Constitution §V model routing)
**Parent program:** `fast-turn` (FTR masterplan W7, `research/FAST_TURN_TWO_SPEED_TAPE_MASTERPLAN_BY_FABLE.md` — see W7) — but this tier lives under **Oracle governance** (NW-U6): Oracle owns kill/keep, FTR waves W2–W5 do not depend on it.
**Verdict vocabulary (pre-bound):** NULL / DISPLAY-WITH-EDGE — as a secondary construction this tier caps at DISPLAY-WITH-EDGE (Constitution §I.4).

## 1. Motivation (incident of record)

2026-07-08: Iran-strike oil spike flipped leadership into semis. Oracle's episode machinery is correct but slow by construction: onset requires `accel_z_5d > 1.0` (5-day-smoothed) and confirmation requires 5 consecutive onset sessions — ≥6 sessions minimum from a regime break to a confirmed banner. The 5-day smoothing exists for a good reason (raw accel_z run median is 2 days, p90=5 — episodes.py:20-22; unsmoothed crossings are mostly noise). This registration does NOT weaken the episode tiers. It registers a *separate, explicitly-unconfirmed display flag* that surfaces the raw crossing on day 1 **with its measured noise rate printed beside it** — detection speed with printed error rates IS the product (Constitution §IV).

## 2. Construction (frozen v1 — truth-in-labeling: this describes exactly what the rule executes)

For each Oracle panel node, on the latest panel row (rotate-IN direction only in v1):

```
tape_onset(t) := raw accel_z(t) >= 1.0            # same threshold as onset, UNSMOOTHED
                 AND vel_1w(t) > vel_3m(t)         # same direction check episodes use
                 AND no active same-direction episode at any tier for this node
```

- Label everywhere it renders: **"TAPE-ONSET (unconfirmed)"** — EN 中文 both carry the unconfirmed qualifier.
- It is NOT an episode state. `engine/oracle/episodes.py` state machine, thresholds, and hysteresis are untouched. The flag lives beside the episode column, never inside it.
- Payload fields (additive, tolerant-reader, banned-substring-checked): `tape_onset_unconfirmed: bool`, `tape_onset_stats: {n_flags, p_onset_5d, p_confirmed_10d, false_positive_5d, window_start, window_end}`.

## 3. Printed error rates (from data, never hardcoded — R4)

Computed nightly from the panel history at render time, over the full available per-node history (coverage watermarks travel inline; breadth/cohesion-derived columns are 2021+ only but accel_z is price-derived and reaches the panel's full span):

- `p_onset_5d` — fraction of historical tape_onset days followed by smoothed onset (accel_z_5d ≥ 1.0) within 5 sessions.
- `p_confirmed_10d` — fraction followed by a CONFIRMED episode within 10 sessions.
- `false_positive_5d` — fraction with NO smoothed onset within 5 sessions (= 1 − p_onset_5d, printed explicitly so the noise rate is never inferred).
- Display copy MUST render the rates next to the flag (e.g. "fires ~N×/yr per node; X% reach onset in 5d, Y% confirm in 10d — measured 1998→"). Descriptive language only; forecast-language ban applies (banned-implication keys enforced in code).

## 4. Forward accrual + evaluation (pre-registered)

- Forward tape: every tape_onset flag appends a row to the Oracle trial-ledger convention (mining is legal because it is counted — Constitution §I.2); accrual starts at ship date, no backfilled gradeable claims (the historical rates in §3 are descriptive display, not claims).
- **Evaluation clock: 2026-10-09** (joint with the FTR grading window). Pre-registered questions, answered on the forward tape only:
  1. Conversion: is forward `p_onset_5d` ≥ the descriptive historical rate's 95% Wilson lower bound? (Sanity that the construction is stationary, not a verdict.)
  2. Lead: median sessions from tape_onset → smoothed onset, for converters (the value proposition is lead time; if median lead ≤ 0 the tier adds nothing over the existing onset display).
  3. Verdict: **NULL** (retire the column, log here) if lead ≤ 0 or forward conversion collapses below half the historical rate; else **DISPLAY-WITH-EDGE remains the ceiling** and the flag keeps accruing. No promotion to rank/gate/size is reachable from this registration (a future promotion attempt is a NEW registration under §I.3 with Harvey-Liu-Zhu width accounting and PS-R8's n≥8 shock-episode gate where shock-conditioned).
- Amendments to thresholds or scope (e.g. adding rotate-OUT direction) are logged amendments to THIS file, PS-R9 style — never drive-by edits.

## 5. Build contract (Sonnet builds; separate PR after this registration merges)

- Additive-only (Constitution §V): new nightly computation appends at END of the oracle nightly step order; payload fields additive; config keys (if any) append at END of config.yml.
- Surfaces: Turn Desk / oracle panel column + subsector_rotation display, bilingual, descriptive copy with §3 rates inline. Alerts (if any later) are state-diff, idempotent, first-run-seeds-silent — NOT in v1 scope.
- `engine/masterminds.py` off-limits (R4). No consumer may rank/gate/size/escalate on the flag (display/context tier; authority block on any new artifact).
- Loud-error pattern; payload validated before write; staleness contract v1.1.0 applies to any new artifact.

## 6. Fences restated

- TI-R5/FT-R3: no beneficiary semantics; the flag names a node's own tape state, never a routing/beneficiary claim.
- Rotation continuation is NULL both directions (§IV) — nothing in this tier's copy may imply continuation; the flag marks a *detection* event, and the printed rates say how often detection was noise.
- Oracle owns this tier. If Oracle governance kills it at the 2026-10-09 read, the FTR program record is updated and the column retires without touching FTR W2–W5.
