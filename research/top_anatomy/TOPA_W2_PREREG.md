# TOPA W2 — Tier-Widening Preregistration (`top_anatomy_w2`)

**Status: FROZEN at commit time.** Results are computed only after this file is on the branch; the commit order is the freeze proof (G0.1). Charter: `reports/top-anatomy-phase0.md` §12 item 2 and the masterplan §11 G0.5 coverage-gate entry (2026-08-10): the phase-0 registered cohort is fast small/mid-caps by construction, the moderate-velocity large-cap / AI-leadership / gold-PGM-miner legs that motivated the program never clear the +50%/126d bar, and **no W1 claim generalizes until W2 reports**. Research/display tier, zero scored authority; AVOID-not-SHORT (`DNR:KILL-DIRECTIONAL-SHORTING`); no rank, no size, no gate, no exit rule.

## §1 Arms — the ONLY moved variable

Two extension-tier arms, each replacing the §4.1 trigger term and nothing else. Both were declared in the phase-0 engine before any phase-0 result existed (`engine/top_anatomy.py` `extended_mask(variant=...)`, constants `EXT_R63_MIN = 0.35`, `EXT_ATRZ_MIN = 6.0`) and ran in phase-0 as count-only sensitivity arms:

| Arm | Trigger | Phase-0 count (EXT days) | Overlap with primary | New EXT days |
|---|---|---|---|---|
| **W2-R63** | `r63 ≥ +0.35` | 151,325 | 95,307 (63.0%) | 56,018 |
| **W2-ATRZ** | `(close − MA200)/ATR63 ≥ 6` | 652,410 | 150,011 (23.0%) | 502,399 |

Everything else in the §4.1 definition is unchanged: near-high term `close ≥ 0.90 × max(close, trailing 252)` on the repaired series, raw-print floors ($3 close / $2M median-21 dollar volume), 260-session in-segment history floor, split-step-day ineligibility, identity segments from the run-3 `sanity-segmented` repair (identity break at residual single-day up-ratio ≥ 3.0; down side deliberately unscreened).

## §2 Frozen from phase-0 run-3 (no re-derivation permitted)

- **Tape:** `data/massive_stock_day`, span 2021-07-06 → **2026-07-02** (1,254 sessions), the SAME vintage as phase-0 — tier definition is the only moved variable. Universe filter unchanged; the NASDAQ test-symbol disclosure (ZTEST/ZVZZT/ZWZZT/ZBZX family) carries forward unchanged — resolving it is a data-plane wave, not this one.
- **Track:** W (registration track, unadjusted prints + sanity-segmented identities) ONLY. The D-track was phase-0's instrument cross-check; W2's question is cohort generalization, not instrument robustness. (Declared here so its absence is a decision, not an omission.)
- **Pipeline:** §4.2 episodes (gap ≤ 21 merge), §4.3 TOPPED/CONTINUED/CENSORED races (−20% from running peak vs +15%, ≤250 sessions), 36 PIT features in 6 families, W4 matched controls (quarter × r126-quintile × rv63-tercile × dvol-tercile, ≤4 NN, episode-first median collapse over the {21,10,5} snapshots), episode-peak-month block bootstrap **B = 2000**, ≥12 distinct peak-month floor, feature coverage floor, min-finite-controls rule, seed **20260810**. Matching **procedure** is frozen; quintile/tercile **bin edges are recomputed within each arm's own candidate pool** (declared: bins are population-relative by construction).
- **E-series:** E1 separation table on both panels of §4; E1b incremental-AUC ruler (grouped + walk-forward, all paired increments printed), E2 lead-time labels, remaining-upside ruler on FULL panels; on DISJOINT panels wherever the ≥12 peak-month floor is met. Every result prints regardless of sign or significance.
- **Instrument:** `engine/top_anatomy.py` byte-frozen at main. `scripts/research_top_anatomy_phase0.py` gains an `--arm {r63,atrz}` path that is plumbing only: variant EXT masks via the existing `extended_mask(variant=...)`, arm-keyed cache identity stamps (the run-3 present-and-equal hard-check extended with the arm name), and W2 summary emission. Per-name FEATURE panels may be shared with the phase-0 cache ONLY if verified EXT-definition-independent (rolling transforms of price/volume, no EXT term); anything downstream of an EXT mask (episodes, races, cases, matching, estimates) is arm-keyed. Any observed jump-day contamination reporting machinery runs unchanged.

## §3 Hypotheses — confirmatory set (declared BEFORE any W2 number exists)

The five phase-0 W-track survivors, tested **one-sided in the phase-0-observed direction**, quoted from `data/research/top_anatomy_p0_summary.json` (run-3, N = 2,154 episodes, 47 peak-months; Δ = topped − matched-continued, episode-first medians):

| Leg | Phase-0 Δ [95% CI] | q | Declared W2 direction |
|---|---|---|---|
| `A4_r252` | −0.128 [−0.178, −0.058] | 0.004 | **negative** (less 252d run-up ⇒ topped) |
| `B2_rsi14` | +1.292 [+0.441, +2.140] | 0.018 | **positive** (hotter RSI14 ⇒ topped) |
| `C6_tr5_over_tr63` | −0.038 [−0.062, −0.006] | 0.066 | **negative** |
| `D1_dvol_z` | −0.071 [−0.147, −0.003] | 0.088 | **negative** |
| `D3_updown_dvol_ratio21` | −0.066 [−0.150, −0.003] | 0.088 | **negative** (phase-0 REGISTERED leg) |

Multiplicity: BH-FDR **q ≤ 0.10 within each (arm × panel) family of 5 one-sided tests**. Four confirmatory families total (2 arms × 2 panels).

**Grades (only the five legs are eligible; nothing else can earn a confirmatory grade in W2):**
- **W2-CONFIRMED** — on the arm's DISJOINT panel: observed sign = declared sign AND q ≤ 0.10.
- **W2-PARTIAL** — confirmed on FULL but not on DISJOINT (overlap-driven by construction; explicitly weak).
- **W2-NOT-CONFIRMED** — neither. Printed with the same prominence as a confirmation.

**Exploratory set:** the remaining 31 features run under phase-0's two-sided within-family BH-FDR machinery on the FULL panels (DISJOINT exploratory tables printed, unranked). Maximum attainable grade: EXPLORATORY-DISCOVERY. No W2 result creates or upgrades a registration; promotion stays gauntlet-gated.

## §4 Panels — where the generalization claim lives

Per arm:
- **FULL** — every arm episode. Contaminated by construction (63.0% / 23.0% of arm EXT days are also phase-0-primary EXT days), so FULL-panel agreement is partial re-measurement of phase-0 episodes. Supporting evidence only.
- **DISJOINT** (**PRIMARY** for every generalization claim) — arm episodes whose (identity-segment, session) EXT-day set shares **zero** days with the phase-0 primary EXT-day set. These are moderate-velocity episodes the phase-0 bar never saw. An episode census (disjoint / partial-overlap / fully-shared) prints in the report.

The matched-control contrast is computed WITHIN each panel, so level shifts from the lower bar (e.g., structurally cooler RSI14 in less-extended names) are absorbed by the matched design; the tested quantity remains the topped-vs-continued contrast.

**Scope of any confirmation (binding report language):** W2-CONFIRMED means the leg **travels across extension tiers on the same 2022H2–2026 tape** — the DISJOINT panels are new episodes, not a new era. Out-of-time replication remains open until the store extends past 2026-07-02. The five legs were selected on phase-0 results from this same tape; W2 tests cohort transfer, not temporal replication.

## §5 Coverage gate — the wave's first question (leads the report, before any statistic)

For each arm: (a) the vintage-date (2026-07-02) extended roster size and its composition; (b) presence/absence BY NAME of the motivating exemplars — AI leaders `NVDA, AVGO, AMD, MU, SMCI, VRT, ANET, MRVL, PLTR, ORCL, ARM, CRDO, ALAB, DELL` and a liquid gold/PGM miner set `NEM, GOLD, AEM, WPM, FNV, RGLD, PAAS, KGC, HL, AGI, SSRM, HMY, GFI, AU, BVN, SBSW`; (c) whether each exemplar has ANY arm episode anywhere on the tape (participation, not just today's roster). If both arms still exclude the miners and AI leaders, the wave's motivating question is unanswered and the report must lead with exactly that sentence — a widened cohort of different small-caps is not the chartered cohort.

## §6 Compute, fallbacks, deliverables

Phase-0 full run: 2,119 s wall. Size ratios put W2-R63 at ≈ primary scale and W2-ATRZ at ≈ 3.9×; both accepted. Declared fallback: if an arm exceeds **12 h wall**, that arm is deferred to its own wave with the reason printed — never a silent cap, never a post-hoc subsample. No new subsampling rule may be introduced after this freeze.

Deliverables: `data/research/top_anatomy_w2_r63_summary.json`, `data/research/top_anatomy_w2_atrz_summary.json`, `reports/top-anatomy-w2.md` (coverage gate first, confirmatory grades second, exploratory third, all nulls printed), masterplan §11 execution entry. **No engine authority changes, no surface changes in this wave** — W1 board widening (separately-stratified libraries / display bands below the frozen bar) is W2b, chartered only after this report exists. Adversarial review (Opus reviewer, G0.5) before presentation; corrections binding.

## §7 Append-only log

- 2026-08-11 — frozen as written; W2 branch `claude/topa-w2-tier-widening` off main 082f7c285c7; store vintage re-verified 2026-07-02 (the staleness chip session has not yet landed a refresh — same-vintage comparability accepted as a feature, not a defect).
- 2026-08-11 (results read; instrument-compatibility note): both arms executed inside the 12 h wall (R63 1,065 s; ATRZ 2,669 s) on the frozen instrument with declared census quantities reproducing exactly; results in `reports/top-anatomy-w2.md`. After both summaries were committed, main landed #5319 (fail-closed refusal of stale-mirror research reads on `massive_stock_day`); the harness threads its explicit override so the deliberately frozen 2026-07-02 vintage keeps running — a compatibility change, no frozen quantity touched, and both runs predate it. Confirmatory outcome recorded for the log: B2_rsi14 W2-CONFIRMED on both arms; A4/D1 W2-PARTIAL both; D3 W2-PARTIAL both (disjoint sign-flip on R63); C6 W2-PARTIAL on R63, W2-NOT-CONFIRMED on ATRZ.
- 2026-08-11 (artifact-provenance correction to the entry above, append-only): the committed arm summaries are no longer the pre-merge runs — both arms were re-run end-to-end on the post-#5319 merged instrument (under its explicit `--allow-stale` override) as a determinism check, and every confirmatory cell reproduced the pre-merge values exactly (verified to 4 decimals; grades identical). The re-run artifacts replace the originals in `data/research/`; a post-hoc `vintage_roster_b2_read` block (descriptive, `post_hoc: true`, own provenance) was appended to each at the commissioning session's request. No frozen quantity, threshold, population, or outcome rule changed.
