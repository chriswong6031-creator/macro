# Oracle P3 Gauntlet — Adjudication

*Applied by Fable 2026-07-04 against the pre-bound vocabulary of [ORACLE_GAUNTLET_P3_PREREG.md](ORACLE_GAUNTLET_P3_PREREG.md) (merged before results, #1231). Results: [ORACLE_GAUNTLET_P3_RESULTS.md](ORACLE_GAUNTLET_P3_RESULTS.md) (#1233; 109-trial family; Sonnet-built, Haiku-cross-checked to 1e-9, twice Opus-audited, final verdict approve).*

## Verdicts

| Endpoint | Result | Verdict (pre-bound vocab) |
|---|---|---|
| **P-EXIT** (Tier-S out, confirmed, +21d) | DA mean **−0.15%** (wrong direction), n=388; G1 ✗ G2 ✗ G3 ✗ G4 ✗ G6 ✗ | **NULL** |
| **P-ENTRY** (Tier-S in, confirmed, +21d) | DA mean **−0.17%**, n=355; all gates ✗ | **NULL** |
| ep_out_onset_5d (secondary) | DA +0.50%; G1 ✓ G2 ✓; FDR ✗ | **DISPLAY-WITH-EDGE** (caveats printed) |
| ep_in_onset_21d (secondary) | DA +0.62%, boot_p 0.0075; G1 ✓ G2 ✓; BH-rejected in the 109 family | **DISPLAY-WITH-EDGE** — the ceiling for secondaries; no VALIDATED path exists for non-primary endpoints under this registration |
| Two-sided premium (S2, Tier M) | in the FDR family; watermarked tier | **DISPLAY** (watermark law) |
| Routing cells (S4) — 34 high-VIX BH rejections | **NOT ADJUDICATED** | see Ruling R2 |

## Rulings

**R1 — The registered expectation was falsified, and that is the headline.** I registered "exit passes at confirmed tier; entry weaker." The data says the opposite twice over: *both* confirmed-tier primaries are null (the confirmed tier arrives after the tradeable move), and the *entry* side at onset (+0.62%, the only episode cell to survive the 109-trial FDR) is stronger than the exit side (+0.25%, boot_p 0.0505). Retraction logged. The scientific shape: **the edge concentrates at the earliest, noisiest detection tier and is gone by confirmation.** Detection speed is the product; confirmation is description, not forecast.

**R2 — The 34 routing rejections are refused, on registration grounds.** Prereg §2 S4 registered routing cells to be tested against a **placebo routing distribution**; the harness (both runs) computed bootstrap-p only — no routing placebo was ever run. A block-bootstrap on n=10–22 same-regime, cross-sectionally correlated outcomes is a weak null: it measures resampling variability of the observed sample, not the probability of such cells arising from an unconditional tape. Mass rejections from exactly the cells the registration predicted would fail is a suspicious pattern, not a finding. **Routing cells therefore remain display-grade candidates, accruing n on the live ledger.** A P3b follow-up may run the registered placebo leg (random onset dates → same cell machinery, 200 draws); only that can move routing cells out of candidate status. Until then no routing number may be presented as validated anywhere.

**R3 — Column mislabel noted:** the results table's `q_adj` is a Bonferroni-style m·p (e.g. 109 × 0.0075 = 0.8175 on a BH-rejected cell), not a BH-adjusted q. The BH step-up rejections themselves are computed separately and are arithmetically consistent. Relabel in the next harness touch; no verdict impact.

**R4 — What this changes downstream (binding on P4/P5/P6):**
- `spotlight.theme_tilt → stock_score._axis_tailwind` **stays dark**. Nothing cleared for scoring.
- Alert surfaces fire at **onset tier** and must print the S3 error rates (onset→confirmed conversion, false-start rate) next to every early alert — speed with printed error bars is the honest product.
- The site-wide banner remains gated on **confirmed + breadth** (D7): its claim is descriptive ("a broad rotation is underway" — true at confirmed, per the June cascade), never predictive.
- Mastermind directive stays context/temper-only, unchanged.
- `ep_in_onset_21d` and `ep_out_onset_5d` get forward-ledger rows from day 1 of live operation (Tier-L accrual toward any future re-registration).
- P4 (analogue memory) proceeds as a **descriptive** layer under its own future registration; nothing here licenses a predictive claim for it.

## R2 — RESOLVED (P3b routing placebo, 2026-07-04)

The registered placebo leg ran (200 regime-matched, count-matched draws per cell, seed 20260704; fixes to count-matching/reproducibility/instrumentation applied after adversarial review; final run **independently re-executed by the verifier with byte-identical results**). Outcome:

- **6 of 34** previously-BH-rejected cells survive the placebo (6 of all 90 sufficient cells) — the R2 suspicion was correct in bulk: 28 of the 34 bootstrap rejections were artifacts of the weak small-n null.
- The surviving set is economically coherent and all high-VIX: `software→ai_compute` @5d & @10d (the software→AI cannibalization of this cycle), `ai_compute→energy_commodities` @10d and its reciprocal `energy_commodities→ai_compute` @10d, `consumer_staples_defensive→financials_rates` @5d, `software→financials_rates` @15d.
- **Verdict (mechanical): DISPLAY-WITH-EDGE** for the 6 — the ceiling for secondary endpoints, and independently capped by the Tier-M watermark law (all routing rides the 2021→ survivorship-flagged panel, single era, n=10–22 per cell). They may render on display surfaces WITH the watermark + n printed; they may not feed any score, size, or gate. The other 28 revert to display-accruing candidates.
- All routing cells continue accruing on the Tier-L ledger; a future re-registration on longer PIT-true history is the only path above this ceiling.

## Status
- 2026-07-04 — Adjudicated. Primaries NULL · onset secondaries DISPLAY-WITH-EDGE · routing NOT ADJUDICATED (R2, placebo leg outstanding) · registration deviations and mislabel logged. Program continues to P4/P6 with R4 constraints binding.
- 2026-07-04 (later) — **R2 resolved**: 6 routing cells DISPLAY-WITH-EDGE (placebo survivors, watermark-capped), 28 reverted to accruing candidates. P6 Time Machine shipped (#1239). P4 memory + P5 live wiring in build.
