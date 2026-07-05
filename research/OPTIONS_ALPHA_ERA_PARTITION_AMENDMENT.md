# Options-Alpha Era-Partition Registration Amendment

**Status: DRAFT — pre-registration for Fable ratification. NOT yet ratified.**
_Opus drafts (roadmap item P0.5); Fable ratifies. Until Fable ratifies and this line
is updated, no era-partitioned verdict may be reported against these partitions._

Roadmap of record: `research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md` (ruling **R2**).
Canonical program doc: `research/OPTIONS_ALPHA_MASTERPLAN.md` (§4 signal & gate registry).

---

## 1. Purpose

Register — for the FIRST time — the era (time-window) partitions that the S-CWIV, S-XZZ,
S-GEXR, and S-DOI gate harnesses will report per-era verdicts against. Per roadmap R2 these
partitions must be registered **before any gate harness runs** (P1.1 gate re-runs are
explicitly sequenced after this amendment merges), so that the split cannot be read as a
post-hoc goalpost move.

---

## 2. Verification: no prior era partition exists (R2 requirement)

I read `research/OPTIONS_ALPHA_MASTERPLAN.md` §4 ("Signal & gate registry", lines 189–209).
The registry table has one row per signal (S-IVR, S-DOI, S-WALL, S-VOI, S-GEXR, S-CWIV,
S-XZZ, S-COIL2, S-SQZ). **None of these rows specifies any time-window / era split.** Each
gate is registered as a single pooled test:

- S-GEXR — "existing `validate_gex` MIN_PER_BUCKET=30 (repointed W0.3)" — no era split.
- S-CWIV — "existing gate: 120 dates ×15 names, HAC t>2" — no era split.
- S-XZZ — "existing gate, same shape" — no era split.
- S-DOI — "cross-sectional rank-IC vs `fwd_ret_5/10`, HAC t>2 @60 dates + harness bucket" —
  no era split.

The §8 status log (through 2026-07-03, W1.3 SHIPPED) records no era-partition registration
event. **Verified: this amendment REGISTERS a first partition; it does NOT revise a
previously-registered one.** This is a first pre-registration, not goalpost-moving.

---

## 3. Registered era partitions

### 3.1 Greeks/IV-dependent gates — S-CWIV, S-XZZ, S-GEXR

S-GEXR is greeks-dependent (it needs dealer **gamma**); S-CWIV and S-XZZ are IV/skew-based.
All three can only be computed where vendor greeks/IV exist (2017→, see §4).

| Era | Window |
|---|---|
| Era 1 | 2017 – 2019 |
| Era 2 | 2020 – 2022 |
| Era 3 | 2023 → (present) |

IV-rank derivatives (`opt_iv_rank_252`) are usable only from **2018→** (252-trading-day
warm-up on 2017-start IV), which sits inside Era 1; harnesses consuming IV-rank must drop the
2017 warm-up rows and note it.

### 3.2 OI-only gate — S-DOI

S-DOI (ΔOI 5-day persistence) reads open-interest only, which has full history from 2012, so
it carries an additional early era.

| Era | Window |
|---|---|
| Era 0 | 2012 – 2015 |
| Era 1 | 2016 – 2019 |
| Era 2 | 2020 – 2022 |
| Era 3 | 2023 → (present) |

(P/C-OI features share S-DOI's 2012→ availability and inherit this same partition where they
are gated.)

---

## 4. Rationale — why 2017 is the greeks boundary

Per roadmap **F-A** ("Greeks/IV history starts 2017"): the vendor greeks/IV history begins in
2017, not 2012. The recorded evidence in F-A is that **greeks rows = 0 for the 2012–2016
window (SPY), with the first non-zero greeks rows appearing in 2017** — a vendor coverage gap,
not a computation error. Corroborating backfill evidence in the roadmap (§1 row 4): the
SPY backfill covers 2012–2026 and the store carries a large greeks payload (store ~2.8 GB,
greeks ~2.1 GB), yet the greeks-bearing years are the more expensive ones to pull
(346 s/root-year for greeks-bearing SPY years vs 210 s/root-year mean) — consistent with
greeks populating only from 2017 forward.

Consequences (all from F-A):
- S-CWIV / S-XZZ / S-GEXR get **2017→ (~9 years)** of usable history → three eras.
- IV-rank usable **2018→** (252d warm-up) — inside Era 1.
- S-DOI and P/C-OI keep **2012→** (OI is not gap-affected) → four eras.

The era boundaries (2017-19 / 2020-22 / 2023→) are chosen to give roughly comparable-length
windows that also straddle the obvious volatility-regime breaks (the 2020 shock, the 2022
rate-repricing) without being tuned to any observed result — they were fixed here, before the
harness runs.

---

## 5. Decision rule (already in program doctrine)

The following are restated, not newly invented; they bind the per-era reporting:

1. **A claim that is alive only in the pre-2016 era is dead.** If a signal shows an edge only
   in the earliest OI-only window (S-DOI Era 0, 2012–2015) and not in any post-2016 era, it is
   ruled dead — not carried forward as live. (Greeks/IV signals have no pre-2017 era at all,
   so a pre-2016-only survival is structurally impossible for them and, where it appears in
   S-DOI, is disqualifying.)
2. **Per-era results are mandatory.** Each gate reports its verdict broken out by every
   registered era above — not only the pooled statistic. A pooled pass masking a single-era
   driver does not count as a pass.
3. **Post-publication-decay commentary is mandatory.** Every reported edge must be accompanied
   by commentary on how it decays across the eras (does the effect shrink toward the recent
   era? — the expected signature of an alpha that has been arbitraged after the source
   literature published). An edge concentrated in the oldest era with decay toward Era 3 is
   treated as suspect, not as a live signal.

These rules mean the era partition is not merely descriptive: it is the mechanism by which a
literature effect that has decayed post-publication is caught and refused live status.

---

## 6. Scope discipline

- This amendment **registers** windows only. It sets no effect-size expectation and reports no
  result. Verdicts print at P1.1 (gate re-runs), which per roadmap R8 start only after the
  `data/thetadata_eod/` universe backfill `_manifest.json` marks complete.
- FDR families remain as registered in §4; the era split multiplies the tests within each
  family and the P1.1 harness must account for that in its family definition.
- This amendment must merge **before** any of the S-CWIV / S-XZZ / S-GEXR / S-DOI harnesses
  run (roadmap P0.5 sequenced BEFORE P1.1).

---

## 7. Ratification

- **Drafted by:** Opus (P0.5).
- **Ratified by:** _pending Fable._ On ratification, update the status line at the top of this
  file and add a §8 status-log entry in `OPTIONS_ALPHA_MASTERPLAN.md`.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
