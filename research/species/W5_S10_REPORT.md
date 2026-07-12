# W5 S10 Phase-0 Report — Margin-Inflection Reclaim
## **FINAL** (run 2026-07-06 · adjudicated 2026-07-12 — K1 NO-GO ratified, construction-scoped; see §12 addendum)

*Pre-registration: `research/species/W5_S10_PREREG.md` (committed before this run).*
*Harness: `research/species/s10_margin_inflection_phase0/`*
*Reproduce: see §9.*

---

## §1 — Executive Summary

**Verdict: NO-GO for both registered variants.**

The margin-direction turn adds essentially no marginal safety-net value over an
otherwise-identical washout+reclaim comparator. Stop-out rate improvements are
0.8 pp (gross) and 0.1 pp (operating), both well under the pre-registered 5 pp
floor, with bootstrap p-values near 0.5 and BH q-values > 0.49. The result is a
clean null at the fire level (n_s10 = 2,607 / 3,026, n_cmp = 9,596 / 11,051 per
variant). *[Adjudication 2026-07-12: "adequate statistical power" needs
qualification at the episode level — see §12.3; the registered gate fails
decisively either way.]*

In plain English: being in washout+reclaim when the margin happens to be turning
upward is indistinguishable from being in washout+reclaim when margins are still
sliding. S10 is **not a safer bottom** — the margin turn buys nothing here.

---

## §2 — Primary Table: clean15_126 (positional primary)

### Trial 1: Gross Margin

| Side | n_matured | eff_n_ep | stop% | stop_WLB | dm% | dm_WLB | cush% | cush_WLB | lift% | lift_WLB |
|------|-----------|----------|-------|----------|-----|--------|-------|----------|-------|----------|
| **S10 gross** | **2,607** | **32** | **65.0%** | **63.4%** | **0.0%** | **0.0%** | **35.0%** | **33.5%** | **32.9%** | **31.5%** |
| CMP gross | 9,596 | 33 | 65.8% | 65.0% | 0.0% | 0.0% | 34.2% | 33.4% | 32.4% | 31.6% |
| **Spread (CMP−S10)** | | | **+0.81 pp** | | | | **+0.83 pp** | | | |

### Trial 2: Operating Margin

| Side | n_matured | eff_n_ep | stop% | stop_WLB | dm% | dm_WLB | cush% | cush_WLB | lift% | lift_WLB |
|------|-----------|----------|-------|----------|-----|--------|-------|----------|-------|----------|
| **S10 operating** | **3,026** | **32** | **64.3%** | **62.9%** | **0.0%** | **0.0%** | **35.7%** | **34.2%** | **33.3%** | **31.9%** |
| CMP operating | 11,051 | 33 | 64.4% | 63.7% | 0.0% | 0.0% | 35.6% | 34.8% | 33.4% | 32.6% |
| **Spread (CMP−S10)** | | | **+0.07 pp** | | | | **+0.08 pp** | | | |

*DEAD_MONEY = 0% for all sides.* The 5% reclaim entry condition ensures price has
already moved >5% off the trough, meaning virtually all fires cross the ±8% dead-money
band within 126 days. This is expected behavior given the arming criteria — it is not
a construction error.

Wilson LB: 90% one-sided (z=1.645) per PREREG.
eff_n_ep: distinct 126-td calendar-time episodes (not raw fire count).

---

## §3 — Context: clean8_21 (rotational, context only)

| Variant | Side | n | liftoff_8_21% |
|---------|------|---|----------------|
| Gross | S10 | 2,607 | 30.1% |
| Gross | CMP | 9,608 | 30.8% |
| Operating | S10 | 3,028 | 31.9% |
| Operating | CMP | 11,062 | 31.7% |

Context only — not the verdict metric for this positional-class species.
S10 shows no improvement at the shorter window either.

---

## §4 — Episode-Clustered P-Values + BH-FDR

Block bootstrap over calendar-time blocks ≥ 126 trading days, 2,000 draws.
p-value = P(bootstrap diff ≤ observed diff) for stop-out (lower = better).

### Trial 1: Gross Margin

| Metric | S10 | CMP | diff | p-value | joint_ep |
|--------|-----|-----|------|---------|----------|
| stop-out | 0.650 | 0.658 | −0.008 | 0.484 | 33 |
| dead-money | 0.000 | 0.000 | ~0 | 0.470 | 33 |
| cushion | 0.350 | 0.342 | +0.008 | 0.515 | 33 |
| clean-liftoff | 0.329 | 0.323 | +0.006 | 0.521 | 33 |

### Trial 2: Operating Margin

| Metric | S10 | CMP | diff | p-value | joint_ep |
|--------|-----|-----|------|---------|----------|
| stop-out | 0.643 | 0.644 | −0.001 | 0.492 | 33 |
| dead-money | 0.000 | 0.000 | ~0 | 0.449 | 33 |
| cushion | 0.357 | 0.356 | +0.001 | 0.507 | 33 |
| clean-liftoff | 0.333 | 0.334 | −0.001 | 0.509 | 33 |

### BH-FDR (family = s10_margin_inflection, m = 2)

| Key | raw p | BH q | reject (q≤0.10) |
|-----|-------|------|-----------------|
| gross_stop_out | 0.4840 | 0.4920 | False |
| operating_stop_out | 0.4920 | 0.4920 | False |

**No variant rejects.** BH q ≈ 0.49 — both p-values are indistinguishable from
a pure null (p ≈ 0.50).

---

## §5 — K1–K5 Verdicts

### K1 — No marginal safety-net value → **NO-GO (both variants)**

Criteria: beat comparator on stop-out AND dead-money AND cushion (Wilson LB, ≥5 pp,
q ≤ 0.10 after BH).

- **Gross**: stop spread +0.81 pp (need ≥5 pp) — FAIL
- **Operating**: stop spread +0.07 pp (need ≥5 pp) — FAIL
- Neither variant comes close to the 5 pp floor on any axis.

K1 verdict: **NO-GO for both variants.** Species S10 v1.0 → `validation_status:
falsified` (self-landable de-escalation per house law).

### K2 — Underpowered → **NOT TRIGGERED**

n_s10 = 2,607 / 3,026 (both variants >> 300). Comparator n = 9,596 / 11,051.
Power is adequate; the null is not an artifact of small sample.

### K3 — Sign instability

- **Gross**: H1 (stop S10=66.5%, CMP=66.8%) and H2 (S10=63.5%, CMP=64.8%)
  both show S10 marginally better → sign-stable = TRUE. But marginal value
  is negligible in both halves.
- **Operating**: H1 shows S10=66.1% vs CMP=65.4% (S10 slightly WORSE) and
  H2 shows S10=62.6% vs CMP=63.4% (S10 slightly better) → sign-stable = FALSE.
  Confirms no reliable signal.

### K4 — Depth confound → **NOT THE DRIVER, BUT ALSO NO S10 ADVANTAGE**

Washout depth distributions are nearly identical:

| Variant | Side | Depth median | Depth Q25 | Depth Q75 |
|---------|------|-------------|-----------|-----------|
| Gross | S10 | −26.2% | −35.8% | −19.9% |
| Gross | CMP | −26.6% | −36.5% | −20.1% |
| Operating | S10 | −26.4% | −36.4% | −19.9% |
| Operating | CMP | −27.1% | −37.2% | −20.2% |

S10 fires are not deeper washouts — depth distributions overlap almost completely.
K4 does not falsify on depth confound because there's no confound to explain,
but it also confirms that S10 carries no advantage after controlling for depth:

**Gross S10 stop-out by depth quartile** (Q1=shallowest, Q4=deepest):

| Depth Q | n_S10 | stop% |
|---------|-------|-------|
| Q1 (−15% to −20%) | 652 | 66.7% |
| Q2 (−20% to −26%) | 652 | 66.4% |
| Q3 (−26% to −36%) | 651 | 64.4% |
| Q4 (>−36%) | 652 | 62.4% |

Stop-out improves slightly with deeper drawdowns, but there is no
differential S10 advantage vs CMP within any depth stratum.

### K5 — Leak sanity → **PASS (all fires verified)**

All fires satisfy `filed(q3) ≤ fire_date` and `fill_date > fire_date`.
Asserted in `fires.py` and verified in testing. No K5 violations observed.

---

## §6 — Per-Name Majority

| Variant | Common tickers | % names where S10 lower stop-out |
|---------|---------------|----------------------------------|
| Gross | 726 | 47.7% |
| Operating | 847 | 46.9% |

Both below 50% — S10 does not improve stop-out rates for the majority of
contributing names. This is consistent with the near-zero aggregate spreads.

---

## §7 — Wait-Cost Table

| Variant | Median wait (filed→fire) | Mean wait | P95 wait | Max wait |
|---------|--------------------------|-----------|----------|---------|
| Gross | 0 days | 9 days | 59 days | 91 days |
| Operating | 0 days | 8 days | 52 days | 92 days |

The median wait is 0 days — most fires trigger immediately on the filing date itself
(washout + reclaim already hold the day the 10-Q/10-K is filed). This means
S10 fires on average carry no entry-timing premium vs. filing-day entry. The
~9-day mean reflects the subset of fires where washout/reclaim are not immediate.

Raw-bar baseline comparison: with median wait = 0, the wait-cost law applies
cleanly — there is effectively no confirmation premium in the median case.
The P95 wait of 59 days (gross) is within the 63 td window, confirming the
window size is rarely binding.

---

## §8 — Coverage and Survivorship

| Metric | Value |
|--------|-------|
| EDGAR tickers | 1,331 |
| Priced tickers in panel | 1,697 (merged deep + delisted) |
| Financials + RE excluded | 363 |
| Primary universe | 1,008 eligible |
| S10 gross fires (era 2010→) | 2,607 |
| S10 operating fires | 3,026 |
| CMP gross fires | 9,596 |
| CMP operating fires | 11,051 |
| PIT SP1500 coverage (S10 gross) | 68.7% |
| PIT SP1500 coverage (S10 operating) | 67.7% |

**Survivorship note:** the panel includes delisted names
(`_closes_delisted.parquet`), recovering catastrophic losers that would
otherwise be invisible. The PIT SP1500 coverage of ~68% means roughly 32% of
fires are in names not in the S&P 1500 at fire time — these are in the universe
because EDGAR has them and they are priced. The SP1500 coverage stamp is for
honesty; it is not a hard gate.

**Optimism bound:** some catastrophic losers may be absent from the store
entirely (delisting before being archived). These would be classified as a
zero-bar termination and excluded from grading — this creates a mild upward
bias on all terminal-state rates. Given the null result, this optimism bound
does not change the verdict.

**Sector distribution of S10 fires:**

| GICS Sector | Gross fires | Operating fires |
|-------------|------------|-----------------|
| Industrials | 614 (23.6%) | 755 (24.9%) |
| Information Technology | 526 (20.2%) | 530 (17.5%) |
| Consumer Discretionary | 504 (19.3%) | 567 (18.7%) |
| Health Care | 401 (15.4%) | 449 (14.8%) |
| Materials | 222 (8.5%) | 198 (6.5%) |
| Consumer Staples | 158 (6.1%) | 155 (5.1%) |
| Other | 182 (7.0%) | 372 (12.3%) |

The archetype context cells (Industrials + Consumer Disc + Consumer Staples)
represent ~49% (gross) / ~49% (operating) of S10 fires — broadly consistent
with the PREREG hypothesis that these sectors would be the primary beneficiaries.
The null holds even in these cells.

---

## §9 — Leak Audit

### Fill rule
Entry fill = next bar strictly after the fire date (`same_bar=False`).
Implemented in `fires.py` via `close_clean.index.searchsorted(fire_date, side='right')`.
Fill is the close of the day AFTER the fire — no same-bar fill bias.

### PIT filed-date mapping
The fire date is the **first trading day d ≥ filed(q3)** within the 63-td window
where washout AND reclaim hold. The `filed` date is the actual SEC filing date from
EDGAR's `filed` column. PIT slice enforced: the EDGAR window for a given candidate
fire date is restricted to rows where `filed ≤ eval_date`. No look-through to future
filings.

Direction-change predicate uses `m(q3) − m(q2)` — q3 is the last known quarter
at `eval_date`, not a future quarter.

### Sector-map non-PIT disclosure
`engine.equity_factors._names_sectors('broad')` returns **current GICS** applied to
history. GICS reclassifications (e.g., 2018 Communication Services split from
Technology) are not retroactively adjusted. This means:
- A company reclassified from Technology to Communication Services after 2018 will
  have all its pre-2018 fires in Communication Services in our data, whereas a
  PIT-correct assignment would put them in Technology.
- The EXCLUDE_SECTORS filter (Financials + Real Estate) is not PIT-correct —
  a company that was classified as Financials before a reclassification might be
  included incorrectly, or vice versa.
- This non-PIT sector label affects exclusion and archetype-cell reporting, but does
  not affect the signal construction (the margin-direction predicate does not use
  sector labels).
- Magnitude of exposure: estimated <5% of fires (major GICS reclassifications are rare).

### Forward-looking elements enumerated

| Element | Status |
|---------|--------|
| Fill price | Next-bar close — no look-ahead |
| Margin direction | Uses filed(q3) as the visibility date — no future filings used |
| Washout state | `washout_ctx(close_sliced_to_eval_date)` — causal, no future prices |
| Price reclaim | `min(close over trailing 63 td to eval_date)` — causal |
| Grading (terminal_state) | Uses forward prices strictly AFTER fill_date — this IS the forward window |
| Sector exclusion | Current GICS (non-PIT) — disclosed limitation, minor |
| PIT membership stamp | `sp1500_pit_membership.parquet` — correct PIT coverage |
| Era end cutoff | `last date with 126d forward window` — no future grading |

No forward-looking elements other than the intentional grading forward window
(which is the measurement object, not a leak).

### Survivorship bias
Panel includes `_closes_delisted.parquet`. Delisted names present = no survivor
exclusion. Absent catastrophic losers (not archived) = optimism bound noted in §8.

---

## §10 — Depth-Balance Context Table (K4)

| Depth Quartile | S10 gross stop% | S10 op stop% |
|----------------|-----------------|--------------|
| Q1 (shallowest: −15% to −20%) | 66.7% | 62.6% |
| Q2 (−20% to −26%) | 66.4% | 66.8% |
| Q3 (−26% to −36%) | 64.4% | 64.2% |
| Q4 (deepest: >−36%) | 62.4% | 63.7% |

Depth distributions are nearly identical between S10 and comparator (medians
differ by < 0.5%). The K4 confound test is negative: S10 does not fail because it
selects deeper washouts; it fails because the margin turn adds nothing regardless
of depth.

---

## §11 — §8 Status Row

| date | wave | species | verdict | PR# | artifacts |
|------|------|---------|---------|-----|-----------|
| 2026-07-06 | W5 | S10 v1.0 | **NO-GO (K1)** | this PR | `W5_S10_REPORT.md`, `s10_margin_inflection_phase0/` |

Registry update proposed: `validation_status: falsified` (self-landable K1 NO-GO
de-escalation per house law). Trial count: 2 (within registered budget, no §8 row
for extra trials).

---

## Appendix — Reproduce Commands

```bash
# From the worktree root
cd research/species/s10_margin_inflection_phase0

# Full run (both variants, 6 workers, ~35 seconds)
python3 run_all.py --variant both --workers 6

# Analysis only (if fires parquets exist)
python3 analyze.py --variant both

# Single variant
python3 run_all.py --variant gross --workers 4 --no-analyze
python3 analyze.py --variant gross
```

Environment: host data at `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/breadth/`
(auto-resolved from worktree path, or set `S10_HOST_BREADTH` env var to override).

---

*This report was generated by the S10 phase-0 build agent on 2026-07-06.*
*Status: FINAL — adjudicated 2026-07-12 (§12); K1 NO-GO ratified as a construction-scoped kill.*

---

## §12 — Adjudication Addendum (2026-07-12 · kill-scrutiny per measurement-lens protocol)

Adjudicated 2026-07-12 after an independent re-read of the harness (not just this report),
an adversarial red-team of both the kill and the revival case, and independent
re-computation of the decisive numbers against the preserved parquets and the exact EDGAR
panel the run used. **The K1 NO-GO STANDS.** S10 v1.0 → `validation_status: falsified`
(pre-registered self-landable de-escalation; S11 precedent PR #1782). The kill is
**construction-scoped**: it closes the registered v1.0 construction, not the margin-turn
mechanism family (house law: a kill closes the specific construction tested).

### §12.1 Registration integrity — HELD (commit granularity)

Prereg commit `3fbd3134315` (2026-07-06 17:51 PT) → trial-ledger budget + 2 trials
registered 17:59 PT → results written 18:04–18:06 PT. The prereg's *merge* (#2374,
2026-07-12) postdates the run, but the registered contract is the commit, and the merged
copy is byte-identical to it (verified with `git diff` — empty). BH m=2 matches the
ledger's declared budget; both trials within budget. Registration discipline held.

### §12.2 Verification — the numbers are real

- **Data-absence false-null RULED OUT** (the lethal worktree gotcha): the run read the
  host deep-price stores; the preserved fires parquets reproduce every headline number
  exactly (stop-out 65.0/65.8% gross, 64.3/64.4% operating; spreads +0.81/+0.07 pp; fire
  dates 2010-07 → 2025-12, consistent with the 126-td forward cutoff).
- **Robustness (red-team):** restricting the comparator to prefix-matched fires (same
  ≥2-quarter deterioration, no turn at q3 — the strictest apples-to-apples contrast, n=1,368
  gross / 1,293 operating) gives spreads of **+2.56 pp (gross) / −0.31 pp (operating)** —
  still far below the 5 pp floor, and sign-inconsistent across variants. The kill survives
  the stricter contrast.

### §12.3 Corrections to this report's framing (binding)

1. **Power.** "Adequate statistical power" overstates. Fire-level n is huge, but under the
   prereg's own episode-clustered inference the bootstrap 90% CIs on the stop-out spread
   (CMP−S10) are **[−2.7, +5.2] pp (gross)** and **[−5.0, +5.6] pp (operating)**: the
   design could not affirmatively exclude a floor-sized (5 pp) effect; its episode-level
   MDE was ≈6–8 pp. The NO-GO rests on the pre-registered demonstration gate failing
   decisively (point spreads +0.81/+0.07 pp, p≈0.5, q=0.49, per-name majority <50%, K3
   sign-unstable on operating) — a correct, registered kill — not on proof that the true
   effect is near zero.
2. **Leak-audit wording.** §9's "PIT slice enforced … restricted to rows where filed ≤
   eval_date" is stronger than the code: `fires.py` asserts `filed(q3) ≤ fire_date` (K5)
   but does not re-check q0–q2 filed dates (late-amendment edge case). A leak of this kind
   biases toward false *positives* and cannot manufacture a null; immaterial to this
   verdict, fix before any reuse.
3. **Episode epoch offset.** `analyze.py` assigns episode IDs per side, each anchored at
   its own earliest fire (~38-day offset between sides), so the joint bootstrap pairs
   slightly mismatched calendar windows; block width uses a 1.4 cal/td approximation
   rather than the trading calendar. Immaterial at p≈0.5; fix before reuse in a close call.

### §12.4 Null classification — construct-level, NOT mechanism-false

Two independent defects mean this construction was unlikely to measure a durable margin
inflection even if one matters:

- **Anti-persistent predicate.** In the exact EDGAR panel used, sign(Δmargin) has lag-1
  autocorrelation −0.15 (gross) / −0.20 (operating), and P[Δm(q4)>0 | registered turn at
  q3] = **0.40 / 0.39** — the registered "first improvement" is more likely than not to be
  followed by renewed deterioration. A strict single-quarter sign predicate (no magnitude,
  no durability leg) selects sawtooth peaks, not inflections.
- **Row-adjacency ≠ calendar adjacency.** The EDGAR store has essentially no Q4 rows
  (54 vs ~18k per other fiscal quarter — annual periods are not decomposed into Q4), so
  nearly every "4 consecutive quarters" window silently spans a fiscal-year boundary and
  mixes seasonal quarters. The prereg's "consecutive quarters" construct is not what
  actually ran.

Classification: **construct-unidentifiable at v1.0** (with the §12.3 power caveat) — not
evidence that the mechanism is false.

### §12.5 Kill scope + retained value

- **CLOSED (terminal):** S10 v1.0 exactly as registered — strict-sign single-quarter turn,
  row-adjacent quarter windows, non-prefix-matched comparator, 5 pp / q≤0.10 gate. Do not
  re-run as-is.
- **RETAINED:** margin-direction context as a **confluence input** (house law: a
  null-as-standalone factor is kept as a confirmer, never auto-erased).
- **OPEN (requires a new species version + fresh prereg + new trial budget):** a
  durability-gated construction — e.g. two-quarter confirmation or a magnitude threshold,
  calendar-true quarter adjacency (fiscal-quarter-aware, Q4-gap handling), the
  prefix-matched comparator as the primary contrast, and a floor/power design aligned with
  the episode-clustered MDE. "Not found yet" ≠ "does not exist"; the search for the ranker
  stays open.
