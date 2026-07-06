# W4.7 — Position-v2 axis acceptance study: the verdict

**Wave:** W4.7 (Cycle Intelligence Masterplan), the M3 axis-flip decision (D1_ONTOLOGY.md §7).
**Date:** 2026-07-06.
**Study script:** `scripts/pos_v2_acceptance_phase0.py`.
**Artifact:** `data/cycle_ontology/pos_v2_acceptance_phase0.json`.
**Pre-registered gate:** `cycle-pos-v2-turn-coherence` (D1_ONTOLOGY.md §6).

## VERDICT: **HOLD** — do NOT flip the axis this wave.

The pre-registered peak coherence gate **FAILS** on its declared population. On **all confirmed
turns** (the population the gate names), `pos_v2` at confirmed **peaks** has **IQR = 48.8**, far
above the ≤ 25 bar — essentially identical to legacy `pos` (IQR 49.8). The trough side passes
(pos_v2 IQR 20.6 ≤ 25, median 8.5). A gate that requires **both** sides therefore does **not** pass.

Because the flip is a one-commit, high-blast-radius change to the displayed position semantics on
**all five** cycle pages, and the strict-improvement condition is not met on the pre-registered
population, the correct terminal outcome is to **ship this study and hold the flip** — with a
concrete, testable remediation (below) that a follow-up wave can execute.

## In plain English

We asked: *does the new position number (`pos_v2`, a normal-CDF "how stretched is this vs its own
history" score) mean the same thing on every chart — so that "68" reads as "late/high" for a US
sector, a Brazil ETF, and a China sector alike?* The old number (`pos`, a range-stochastic
oscillator) provably does **not**: at confirmed cyclical peaks it sprawled from near-0 to 100, so a
single threshold was meaningless across instruments.

The answer is **mostly yes, but not cleanly enough to flip yet.** At the turns that actually matter
— the **major** cyclical tops and bottoms — `pos_v2` is clearly tighter and better-centered than the
old number (peak IQR 25.7 vs 37.4; peak median 90.8). **But** the gate we pre-registered scored
**every** ZigZag turn, and ZigZag also marks *lower-highs inside bear markets* as "peaks" — and those
legitimately sit at a **low** position (e.g. the March-2020 crash-rally top in South Africa's EZA is a
"peak" at pos_v2 ≈ 0). Counting those, the peak spread stays wide, and the gate fails. This is not a
bug in `pos_v2` — it is reading those washed-out lower-highs *correctly*. It is a mismatch between the
gate's turn population and what "high position" is supposed to mean.

So we hold. The fix is not to touch `pos_v2`; it is to **re-scope the gate to major/cyclical turns**
(which is arguably what "position at a peak" always meant) and re-run. On that population the gate is
right at the margin (peak IQR 25.7 vs the 25 bar), so a small parameter refit would likely clear it.
Flipping now — on a marginal, population-sensitive result — is exactly the move the masterplan's
conservatism rules forbid.

## What was measured

- **Universe:** the 73 hazard-panel / backfill instruments — 11 US SPDR sectors + 31 country ETFs +
  31 Shenwan L1 CN sectors.
- **Confirmed turns:** detected with `engine.cycle_ontology.detect_turns` on the structure-math basis
  (`close_price` for yahoo; the custodian close for CN), ZigZag pct per `TURN_DETECTOR_DEFAULTS`
  (14% US/country, 18% CN), version 2. Provisional turns dropped.
- **Position at each turn — read, not recomputed:** each turn's **extremum date** is mapped to the
  nearest committed backfill month-end (`data/<engine>/backfill.parquet`, |gap| ≤ 45d; the median
  |gap| is 6 days and gap is uncorrelated with pos_v2, r = −0.015, so the join is not an artifact).
  The `pos` and `pos_v2` at that month-end are the **exact numbers the page displays** — the same PIT
  monthly stamps produced by `scripts/backfill_forward_logs.py`. Turns before the 2010-12 backfill
  window are dropped. This is a pure re-read: **no live-engine recompute, no drift.**

## Leg 1 — COMPARABILITY (the audit's defect, re-measured)

Position spread at CONFIRMED turns, pooled across the two families that carry `pos_v2`
(us_sector + country). `[min, p25, median, p75, max]`, IQR = p75−p25:

| Population | Side | Legacy `pos` (min/p25/med/p75/max, IQR) | `pos_v2` (min/p25/med/p75/max, IQR) |
|---|---|---|---|
| **All confirmed turns** | peak (n=555)   | 0.8 / 42.3 / 71.4 / 92.2 / 100.0 — **IQR 49.8** | 0.1 / 47.2 / 83.5 / 96.0 / 100.0 — **IQR 48.8** |
| **All confirmed turns** | trough (n=557) | 0.0 / 2.2 / 9.3 / 35.6 / 98.5 — **IQR 33.4** | 0.0 / 2.8 / 8.5 / 23.4 / 99.9 — **IQR 20.6** |
| **Major turns only** *(diagnostic, not the prereg population)* | peak (n=417) | 0.8 / 58.6 / 80.8 / 96.0 / 100.0 — **IQR 37.4** | 0.1 / 72.2 / 90.8 / 97.9 / 100.0 — **IQR 25.7** |
| **Major turns only** *(diagnostic)* | trough (n=337) | 0.0 / 1.2 / 4.0 / 12.5 / 87.4 — **IQR 11.3** | 0.0 / 1.3 / 4.5 / 11.3 / 96.8 — **IQR 10.0** |

Per-family peak spread (why the pooled peak stays wide):

| Family | peak legacy IQR | peak pos_v2 IQR | trough legacy IQR | trough pos_v2 IQR | pos_v2? |
|---|---|---|---|---|---|
| us_sector | 46.0 | **15.7** | 17.2 | 32.6 | yes |
| country   | 51.2 | **51.0** | 37.5 | 18.5 | yes |
| cn_sector | 63.0 | (n/a) | 47.2 | (n/a) | **ABSENT** |

Reading:
- **Does `pos_v2` materially tighten peaks?** On US sectors, yes (IQR 46.0 → 15.7). On the **country**
  family, **no** — pos_v2 peak IQR is 51.0, indistinguishable from legacy's 51.2. The country family
  (the larger n) dominates the pool, so the **pooled** peak IQR barely moves (49.8 → 48.8).
- **Troughs** do tighten pooled (33.4 → 20.6) and per-family for country (37.5 → 18.5).
- **The mechanism** is the turn population, verified directly: many country "peaks" are ZigZag
  lower-highs on a downtrend — real directional pivots at genuinely low position. Restrict to
  **major** turns and pos_v2 clearly beats legacy on both sides (peak IQR 37.4 → 25.7; median 80.8 →
  90.8). So `pos_v2` *is* the more comparable measure of cyclical position; the pre-registered gate's
  peak criterion is simply being scored against a population that includes non-cyclical pivots.

**Does "≥ 68 mean the same thing everywhere now?"** For **major** turns — much more so than legacy
(peak IQR shrinks by ~12 points, median lifts to 90.8). For **all** confirmed turns — no; but that is
because "any ZigZag peak" is not the same concept as "high cyclical position," and `pos_v2` reads the
low-position lower-highs correctly.

## Leg 2 — COHERENCE (pass)

`scripts/check_cycle_consistency.py` → **PASS** (7 same-tape groups agree; 25 declared cross-tape
differences). `tests/test_cycle_ontology.py` → **50 passed**, including the W3.6 coherence regression
test (no live record carries `pos_v2 ≥ 85` with a Trough/Recovery `phase_v2` — or the mirror —
without a divergence flag). **0 residual pos_v2/phase_v2 contradictions across live records.** The v2
triple (pos_v2 / phase_v2 / stance) is internally coherent today. Coherence is **not** the blocker.

## Leg 3 — NO-REGRESSION (what the flip *would* change — enumerated, for the follow-up)

The flip is deliberately narrow. On flip (`ONTOLOGY_AXIS = 'v2'`), per page, **only** these change:

- **The numeric position bar** (`site/sector_cycles.js` `.cc-leg-bar` width + `.cyc` position gauge):
  driven off `nw.pos` today → would read `nw.pos_v2`. Sector / country / china cards.
- **The "Cycle position N/100" numeric label** and any axis **tick labels** on the 0–100 position
  scale, relabeled to the canonical z/CDF semantic. Legacy `pos` becomes a labeled "legacy osc"
  hover/stat, not deleted from view.
- **markets.html** (`site/markets_app.js`) and **cycle.html** (`site/cycle_app.js`) position readouts:
  same substitution.

**Unchanged (already v2-driven since W3.6):** every **phase** label, **stance** chip, **divergence**
chip, projection cone, hazard turn-odds line (W4.3), timing state, and all secular/FRAME content.
Phase and stance already read `pos_v2`; the flip only aligns the *displayed number* with the label
that is already derived from it. So the flip is genuinely non-regressing for labels — but it is still
**gated on comparability**, which has not passed.

## Scope caveat that also argues for HOLD: China is un-assessed

The **China sector backfill carries no `pos_v2` column** (the CN engine emits legacy fields only).
So `pos_v2`'s peak/trough comparability **cannot be assessed for the CN family** from committed PIT
data — yet the flip changes `china_sector_cycles.html`. Flipping the axis on a page for which we have
**zero** acceptance evidence would be shipping blind on one of the five pages. Even had the pooled
gate passed, this alone would warrant holding the CN page until its backfill stamps `pos_v2`.

## Remediation (concrete, for the follow-up wave)

1. **Re-scope the gate population to major/cyclical turns** (the detector's `major` flag, or a
   `mag_pct` threshold) and register it as the amended `cycle-pos-v2-turn-coherence` criterion. On
   that population the peak side is IQR 25.7 (median 90.8) and troughs 10.0 — right at / inside the
   bar. This is the single highest-leverage change and is likely sufficient.
2. If (1) still lands the peak IQR marginally over 25, **refit `Z_SCALE` / `trend_span`** in
   `POSITION_PARAMS` (D1_ONTOLOGY §6 named this as the fallback remediation) and re-run — a small
   sharpening of the CDF should pull the peak IQR under 25 without disturbing troughs.
3. **Stamp `pos_v2` into the China sector backfill** (extend `engine.china_sector_cycles` +
   `_stamp_row_china`) so the CN page can be assessed before it is flipped.
4. Re-run this exact study; flip only when the amended gate passes on **both** sides **and** CN is
   assessed.

## Registry

Two experiments accrue (D1_ONTOLOGY §6, N4):
- `cycle-pos-v2-turn-coherence` — **status: FAIL (peak) on all-turns population; PASS on trough**;
  amended-population re-run proposed. Maturation metric reproduced in the artifact.
- `cycle-phase-flap-rate` — not evaluated this wave (requires the confirm_persist flap sweep, a
  separate measurement); carried forward.

**Bottom line:** `pos_v2` is the right long-run position semantic and is coherent today, but on the
pre-registered gate population it is **not** a strict comparability improvement at peaks. Per the
masterplan's conservatism rules, the axis stays on legacy `pos` this wave. HOLD, with a scoped path
to GO.
