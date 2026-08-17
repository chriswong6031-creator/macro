# W3 paired race — pre-registration (FROZEN)

*`WS:PROPHET-CONDITIONAL-FUSION` · PR-3A · frozen 2026-08-16 before any forward
C1-vs-shadow outcome read.*

Charter: [`W3_SHADOW_RACE_RECUT.md`](W3_SHADOW_RACE_RECUT.md). This file is the
decision. The recut is the purpose. Nothing in this freeze inspects newly accrued
rank-IC deltas, top-30 returns, p-values, or “who is winning.” Durable paired-race
N at the audit boundary that commissioned this freeze was **zero**.

Authority: none. C1 / `us_prophet_v3` is already the live US ranker
(`DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER`). W3 is a prospective
measurement/diagnostic program around that ranker, not a promotion contest.

---

## 0. What is frozen

| Item | Freeze |
|---|---|
| Population | Same canonical **buy** population, **paired row only** (`DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW`). One row per `(stamp_date, ticker)` carrying both orders. |
| Canonical columns | `prophet_score` / `score_rank` interpreted under `board_definition=us_prophet_v3` (`published_ranker_output`). Always pair the column with `board_definition`. |
| Shadow columns | `prophet_shadow_score` / `prophet_shadow_score_rank` with `prophet_shadow_definition=us_prophet_v2_shadow` (`retired_shadow_output`). |
| Exclusions | Degraded nights (`us_prophet_v2_fallback`); unpaired rows; rows with null shadow; off-board rows. Fallback nights withhold shadow on purpose — they are not a tie observation. |
| Start boundary | First **durably committed** candidates-store paired stamp **after** #5769 merge SHA `0233445657e8a6e40f3f5260d9cad7af4bb3e456`. Not the override calendar date. Not a Pages-only night. **No backfill** of the lost Pages-only acceptance session. |
| Primary horizon | **H=10**. H=63 only where existing class/episode law already requires it. No new horizon. |
| Outcome / benchmark | `excess_spy` from **one shared grader**: `engine.us_prophet_grades.load_grades`. SPY is the benchmark. No second outcome row. |
| Rank-IC sign | Spearman of **`(-score_rank)`** vs `excess_spy`, so **positive IC = ranker worked** (lower rank number → higher excess). Δ = IC_C1 − IC_shadow. Positive Δ = C1 leads. |
| Top-30 ties | N=30. Names tied at the cutoff are **included**; report n. Secondary only. |
| Honest-N floor | **20 distinct matured H=10 paired sessions**. Grain is `(stamp_date)`, never rows, never fires. Retries of one `as_of` count as one session (keep-first). Guardrail-read floor, **below** the 50-episode promotion floor. Arena `MIN_TEST_DATES=10`; overlapping H=10 ⇒ ~1 independent block per 10 adjacent sessions; 20 sessions ⇒ ≥2 HAC-adjusted blocks. |
| Overlap / dependence | Newey-West HAC on the date-level ΔIC series, lag **L=9 (H−1)**. **t-referenced**; never the normal approximation. df = N_sessions − 1. |
| Primary tripwire | Investigation opens iff the 95% two-sided HAC-t CI for Δ lies **entirely below 0** (shadow leads on rank-IC). A point-estimate lead is not enough. |
| Secondary metric | Top-30 mean `excess_spy`, confirmatory safety only — **not** an OR tripwire. If the primary fires and the secondary disagrees, still open the investigation labelled “rank-IC adverse, top-30 not confirmatory.” |
| Missing / degraded sessions | Gaps remain gaps. No reconstruction. No interpolation. Pages-only nights are not sessions. Fallback nights are excluded, not imputed. |
| Grader | One shared grader. **No second scorer. No second grader.** |
| Promotion arm | **NONE.** No automatic reversion. No C2 trigger. An adverse tripwire opens an investigation record; it does not un-adopt C1 and it does not authorize a C2 fit. |

---

## 1. Population and pairing

The race is a **paired population**: the canonical buy universe already stamped by
production, with both orders on the same row. Valid because population, outcome, and
grader are shared and the shadow holds zero authority.

A row enters the race if and only if all of:

1. `board_definition=us_prophet_v3`
2. `prophet_shadow_definition=us_prophet_v2_shadow`
3. `prophet_score` and `score_rank` non-null
4. `prophet_shadow_score` and `prophet_shadow_score_rank` non-null
5. the row is in the canonical buy population for that stamp

A row is excluded if any of:

- `board_definition` is `us_prophet_v2` or `us_prophet_v2_fallback`
- shadow columns are null
- the night is degraded
- the stamp exists only as a Pages artifact and was never a durably committed
  candidates-store row

Do not copy `prophet_shadow_*` into canonical `prophet_*` columns. Canonical
five-leg `prophet_{signal,entry,edge,runway,quality}` fields are null by design on
v3 (`legacy_v2_decomposition`); that null is attribution, not a missing comparator.

---

## 2. Start boundary

The window opens at the first durably committed post-#5769 paired stamp.

- #5769 merged 2026-08-16 as `0233445657e8a6e40f3f5260d9cad7af4bb3e456`.
- The store forbids retroactive backfill, so nights between the 2026-08-15 override
  and that merge have no shadow columns in git.
- The first accepted v3 board (run 31913143619) was Pages-only after the engine
  push failed. That night is **not** a race session. Do not backfill it.
- Retries of one `as_of` are one session. Keep-first.
- Until that first durable stamp exists, honest-N is 0 and no comparison may be
  printed. “N nights accrued, first lawful read at \<date\>” is the only lawful
  surface sentence.

This freeze does not name a calendar start date by inspecting the candidates
store. The boundary is the git event, not a peeked stamp.

---

## 3. Outcome, grader, horizons

- **Primary horizon:** H=10.
- **Outcome:** `excess_spy` (name excess versus SPY).
- **Grader:** `engine.us_prophet_grades.load_grades`. One shared grader for both
  columns. No second outcome construction, no second return file, no second
  benchmark.
- H=63 remains available only where existing episode/class law already requires
  it. It is not a W3 primary and cannot trip the investigation on its own.

---

## 4. Primary metric and sign convention

For each matured paired session, compute Spearman rank-IC of `(-score_rank)`
against `excess_spy` on the paired buy population, separately for:

- C1: `score_rank` under `board_definition=us_prophet_v3`
- shadow: `prophet_shadow_score_rank` under `prophet_shadow_definition=us_prophet_v2_shadow`

Sign law: **positive IC = ranker worked**. Rank number 1 is best; negating the
rank number makes the Spearman positive when better ranks get higher excess.

Session-level delta: ΔIC = IC_C1 − IC_shadow. Positive Δ = C1 leads.

The race statistic is the HAC-adjusted mean of the date-level ΔIC series.

---

## 5. Secondary metric (not an OR tripwire)

Top-30 mean `excess_spy` on the same paired session, same grader, same SPY
benchmark.

- N=30.
- Names tied at the cutoff are **included**; report the resulting n beside the
  mean.
- Role: confirmatory safety only. It cannot open an investigation by itself, and
  it cannot cancel a primary fire. If primary fires and secondary disagrees, the
  investigation still opens, labelled “rank-IC adverse, top-30 not confirmatory.”

---

## 6. Honest-N, overlap, inference

- Honest-N grain: **distinct matured H=10 paired sessions**, identified by
  `stamp_date`. Never rows. Never fires. Never a 60-name board counted as 60.
- Numeric floor for a guardrail read: **20 distinct matured H=10 paired sessions**.
  Below the 50-episode promotion floor on purpose: this is a tripwire on a
  decision already taken, not a promotion gate.
- Overlapping H=10 returns are temporally dependent. Inference uses **Newey-West
  HAC** on the date-level ΔIC series with lag **L=9 (H−1)**.
- p-values and intervals are **t-referenced** with df = N_sessions − 1. The
  normal approximation is printed if at all as a diagnostic and **never** decides.
- Arena `MIN_TEST_DATES=10` remains the harness floor for a test fold; it is not
  this race’s honest-N.

No comparison, interval, or “who is winning” sentence may be published before
the floor is met. Until then the only lawful sentence is the accrual count.

---

## 7. Primary adverse / investigation tripwire

Investigation opens **iff** the 95% two-sided HAC-t confidence interval for mean
ΔIC lies **entirely below 0**.

That is: shadow leads C1 on the primary rank-IC metric, and the interval excludes
zero on that side.

A point estimate below zero is not enough. A secondary-only lead is not enough.
An investigation is a new AgentOS record. It is **not**:

- automatic reversion of `us_prophet_v3`
- a C2 trigger
- permission to fit, reweight, drop a family, or bump `SELECTION_ERA`
- permission to build another v2 scorer or another grader

---

## 8. Missing-session law

- A gap in durable stamps is a gap. Do not reconstruct it from Pages, from a
  replay of the retired scorer, or from a neighboring night.
- Do not backfill the lost Pages-only v3 session.
- Do not count retries of one `as_of` as multiple nights.
- Do not stamp or impute shadow on `us_prophet_v2_fallback` nights.
- Degraded / fallback nights are excluded from the paired population, not scored
  as ties.

---

## 9. What this freeze does not authorize

- **no promotion arm**
- **no automatic reversion**
- **no C2 trigger**
- **no second scorer**
- **no second grader**
- no LOFO structural diagnostics (PR-3B)
- no W3 durable forward ledgers or nightly workflow wiring (later PRs)
- no W3 display surface that prints a comparison before the floor
- no C2 rebuild/fitting, no C3/C4/C5
- no outcome read at freeze time

Rank deltas and first-night orderings remain **not** alpha evidence.
`FUSION_SCORE_KIND` remains the epistemic boundary: C1 is an unfitted
equal-weight breadth-of-evidence ordering, not a calibrated return forecast.

---

## 10. One-sentence operating rule

Until 20 distinct matured H=10 paired sessions exist after the first durable
post-#5769 stamp, W3 reports accrual only. After that floor, the only registered
decision this wave can take is “open an investigation if the HAC-t CI for ΔIC
lies entirely below 0.” Everything else is a later, separately registered act.
