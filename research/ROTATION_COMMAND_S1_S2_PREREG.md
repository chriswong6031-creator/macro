# Rotation Command — S1 (handoff stance override) + S2 (reclaim entry lane) — PRE-REGISTRATION

**Program:** Rotation Command (research/ROTATION_COMMAND_MASTERPLAN_BY_FABLE.md, #2286; W1
shipped #2319/#2320/#2322). **Wave:** W2 (RC-R9). **Author:** Fable.
**Status:** PRE-REGISTERED — committed BEFORE the RC-R8 replay's outcome columns are computed
or looked at. The event CENSUS (which pairs fired, when) may be inspected before results; the
FORWARD-RETURN columns may not, and the evaluation script computes them only after this doc
is merged.

**Why these studies exist.** W1's rotation events are display-tier. The stance layer that
caused the 2026-06-25 miss (COUNTERTREND/HIGH-RISK BOUNCE labels + the "flat: sell" marker
gate) can only change through evidence. S1 asks whether the rotate-IN leg after an event is
actually worth a different label; S2 asks whether a fast entry at event creation beats
waiting. GO here does NOT ship a gate — it opens the RC-R12 flag-gated experiment lane.

---

## 1. Hypotheses (one-sided, frozen)

**S1-H1 (primary).** At rotation-EPISODE creation (§2.4), the rotate-IN leg earns POSITIVE
excess return vs its own SECTOR ETF over the forward 20 sessions (fwd20). One-sided long.
**S1-H0:** episode-level mean/median excess fwd20 = 0.

**S2-H1 (primary).** Entering the rotate-IN leg at episode creation beats entering the same
leg 10 sessions later (the "wait for confirmation" counterfactual) on fwd20-from-entry,
paired per episode. One-sided (creation-entry better).
**S2-H0:** paired median difference = 0.

**Family + multiplicity:** exactly TWO primary hypotheses; BH-FDR at q=0.10 across {S1,S2}.
Everything in §5 marked *descriptive* is non-gated and uncorrected. Detector configuration
is the single W1-frozen parameter set (engine/rotation_events.PARAMS as of #2322) — no
sweeps were run, n_trials=1 configuration; the two calibrations informed by the June-2026
episode (abs-runup path, reclaim_len=5) are handled by the §2.5 exclusion.

---

## 2. Constructions (exact, frozen)

### 2.1 Replay
`engine.rotation_events.step_pairs` VERBATIM (the production lifecycle: creation, lapse,
ratio-exit, TTL, lockout), stepped daily over the union of registered sector-ETF sessions,
each evaluation on the trailing **420-bar** window of every series (all signature lookbacks
≤ ~370 bars, so windowing is behavior-identical to full history). Legs and ETFs from
`config/sector_legs.json` via `engine.sector_legs.sector_closes()` — basket legs equal-weight,
CURRENT membership over full history (pit=False). Warmup from 2014-01; events COUNTED from
**2015-01-01**.

### 2.2 Survivorship honesty (binding disclosure)
Leg membership is hindsight-curated (baskets seeded 2023-05-09; `ai_semiconductors` was not
a nameable cohort in 2016). Every statistic is therefore reported on two eras:
**modern** (started ≥ 2023-05-01) and **reconstructed** (2015-01→2023-04, watermarked
"membership as of 2026 — approximation"). The S1 GO additionally requires the modern subset
not to contradict (§4). No claim is made that reconstructed-era events were detectable
point-in-time as named cohorts.

### 2.3 Outcome basis
Signals are computed from session-T closes → actionable T+1. All forward returns are
measured **from the first close AFTER creation (T+1 close)** to T+1+h close:
`fwd_h = to_leg[T+1+h]/to_leg[T+1] − 1`. Excess legs on the same basis:
`x_sector_h = fwd_h(to_leg) − fwd_h(sector ETF)`; `x_spy_h = fwd_h(to_leg) − fwd_h(SPY)`.
`maxdd20` = worst `to_leg[t]/to_leg[T+1] − 1` for t in (T+1, T+21]. Basket legs are
equal-weight composites — results are cohort reads, not tradable-instrument backtests
(stated, not corrected).

### 2.4 Episode clustering (effective-N; the non-overlap law)
Multiple pairs fire on one market handoff (June 2026: five XLK pairs = ONE handoff). An
EPISODE = the union of a sector's events whose [started, closed] session-intervals overlap
(transitively). One observation per episode. **Representative pair (frozen):** highest
severity, tie → earliest `started`, tie → lexicographically first pair id. Episode creation
date = the representative's creation session. Statistics run on episodes only; per-event
rows are descriptive.

### 2.5 Universe + exclusions (frozen)
- Episodes with representative `started` in [2015-01-01, 2026-04-30].
- **EXCLUDED: anything started ≥ 2026-05-01** — the June-2026 handoff is case zero AND
  informed two detector calibrations; it earns no credit here and is graded prospectively
  by the nightly ledger (RC-R15).
- fwd20 must complete within the replay range (it does, given the 2026-04-30 cap).
- Minimum matured episodes for a verdict: **n ≥ 20** per study; below that the verdict is
  ACCRUE (no promotion, no kill), revisited when the prospective ledger matures.

### 2.6 Baselines
1. **Sector ETF** (primary excess basis) — did the leg beat its own sector.
2. **SPY** (secondary).
3. **Unconditional same-leg distribution** (context): for each episode, the to-leg's fwd20
   from every session in [2015-01, 2026-04] → the episode's percentile within it
   (descriptive; answers "is this just the leg's normal behavior").
4. **S2 delayed-entry**: same leg, entry at T+11 close, fwd20 to T+31. DISCLOSED PROXY for
   the marker lane — the actual signal_gate simulation on leg composites is a follow-up
   study iff S2 passes; a GO on S2 alone ships nothing.

## 3. Statistics (frozen)
- Median and mean of `x_sector_20` (S1) / paired `Δfwd20 = creation − delayed` (S2), on
  episodes.
- Win rate: share of episodes with the statistic > 0.
- **p-value:** one-sided bootstrap (10,000 resamples of episodes, percentile of 0) for S1;
  one-sided exact sign test + bootstrap for S2. HAC machinery is unnecessary at episode
  grain (episodes are non-overlapping by construction §2.4; any residual cross-sector
  same-month clustering is reported as a count, not corrected).
- False-fire rate (S1): share of episodes with absolute fwd20 < −5%.

## 4. Verdict bars (frozen)
**S1 GO** requires ALL: n ≥ 20; median `x_sector_20` ≥ +1.0pp; WR ≥ 55%; BH-adjusted
p < 0.10; false-fire ≤ 25%; modern-era median `x_sector_20` ≥ 0 (n_modern ≥ 5, else the
modern clause is ACCRUE and caps the verdict at ACCRUE).
**S1 KILL** if n ≥ 20 and median `x_sector_20` ≤ −1.0pp. Otherwise **NO-GO** (rail stays,
no relabel) or **ACCRUE** (n < 20).
**S2 GO** requires ALL: n ≥ 20 paired episodes; median Δfwd20 ≥ +1.0pp; BH-adjusted
p < 0.10; median maxdd20(creation-entry) not worse than delayed-entry by > 2pp.
**S2 KILL** if n ≥ 20 and median Δfwd20 ≤ −1.0pp. Else NO-GO / ACCRUE as above.

**What GO buys (and only this):** S1-GO → W3 may ship the "HANDOFF CANDIDATE" display
relabel on event days (copy only; stance machinery untouched) and opens the RC-R12
flag-gated stance experiment with its own prereg. S2-GO → authorizes the follow-up
marker-lane-simulation study. Neither GO ranks, gates, sizes, or escalates anything.

## 5. Descriptive outputs (non-gated, uncorrected)
- **RC-R10 episode ruler:** distribution (p25/median/p75) of the to-leg's max run from
  `started` close within 30 sessions, and sessions-to-peak — powering the honest
  "at +X% of the median +Y% handoff run" display copy. All eras, watermarked.
- Per-sector and per-pair event counts, durations, close reasons; severity mix;
  false-fire table; fwd60 columns (fewer matured, descriptive only).

## 6. Clock + provenance
Evaluation runs once, immediately after this doc merges, on the RC-R8 replay artifacts
(`data/rotation_events/replay_census.parquet` + `replay_forward.parquet`); results are
appended to this file in a separate commit as **RESULTS (post-registration)** with the
artifact hashes. The prospective nightly ledger (events.jsonl, from 2026-07-12) re-runs
the same rulers at 2026-10 with matured live outcomes.

---

## RESULTS (post-registration — 2026-07-12, replay run AFTER #2351 merged)

**Artifacts** (`scripts/replay_rotation_events.py`, sha256/16): replay_census
`c9ea719775526b48` · replay_episodes `25825f40c366aac2` · replay_forward
`3978433ee13c82ac`. Replay: 2,935 sessions (2014-11→2026-07), 61 events → **15 episodes**
(§2.4 clustering), 13 in the S1/S2 universe (§2.5 excludes the two June/July-2026
case-zero episodes).

### Verdicts: **S1 ACCRUE · S2 ACCRUE** (n = 13 < 20 floor; no promotion, no kill)

| | n | median | mean | WR | false-fire | p (raw) | p (BH-adj) |
|---|---|---|---|---|---|---|---|
| S1 `x_sector_20` | 13 | **−0.24pp** | +0.67pp | 46.2% | 15.4% | 0.61 | 0.71 |
| S1 modern only | 6 | −0.66pp | +1.18pp | 50.0% | 16.7% | 0.56 | — |
| S2 Δfwd20 (creation − delayed) | 13 | **−1.97pp** | — | 46.2% | 0.71 (sign) | 0.71 |

Point estimates are NULL-to-weak-negative at a sample size that cannot distinguish
anything — exactly the expected-NULL posture the ledger was declared under. **No stance
relabel and no entry lane is authorized.** The display tier remains the home of rotation
events until the ledger matures.

### What the census DID establish (descriptive, non-gated)

1. **The detector is rare and sane.** ~1.3 episodes/yr; the list reads as real history:
   2018-04 memory→mag7 (the 2018 memory top), 2020-03 mega-cap-consumer handoff,
   2022-04/05 mega-cap derating cluster (major, 12 pairs), 2024-08-13 mag7→ai_semis
   (the yen-carry V-bottom), the 2025-11→2026-03 memory-saga legs, and the excluded
   2026-06/07 case-zero cluster. Zero events most years — quiet is the normal state,
   which supports MAJOR severity mattering when it prints.
2. **RC-R10 episode ruler** (episode_ruler.json, surfaced on the rail): modern era (n=8)
   median to-leg run **+7.8%** off the started close (p25 +3.4 / p75 +11.0), peaking
   ~**9 sessions** in; reconstructed era much weaker (median +1.4%, survivorship-
   watermarked). The masterplan's guessed "+12% median" was too generous — the honest
   ruler is now measured, and it still shows the class-boundary point: a cohort at +5%
   on day 3 of a median 9-session +7.8% run is MID-run, not "late".
3. **Accrual reality:** at ~1.3 episodes/yr, the n≥20 floor is ~5 years away on
   prospective accrual alone. The honest paths to a verdict sooner: (a) widen the census
   universe (more sectors/legs — a NEW prereg, not a peek), or (b) accept the display
   tier as the permanent home. No threshold from this doc may be tuned against these
   results — any change is a new registration.

**Case zero (prospective):** the 2026-07-02 ai_semis→mag7 major episode (13 pairs) and
its 2026-06-15 precursor grade in the NIGHTLY ledger at 2026-10 per §6 — untouched by
this evaluation.
